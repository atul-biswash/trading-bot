"""The backtest composition root: the live decision path over stored history.

``backtest_system`` assembles the SAME collaborators ``engine.modes.live_system`` assembles --
the buffered market-data provider, the trading engine, the risk manager, the intent logger and
the one signal handler -- and swaps only the three things a backtest has no business sharing
with a venue: a :class:`~trading_bot.backtesting.replay.ReplayClient` for the REST seed, a
:class:`~trading_bot.backtesting.replay.ReplayStream` for the feed, and a
:class:`~trading_bot.backtesting.simulated_executor.SimulatedExecutor` for the order placer. The
risk manager reads the replay's simulated instant, never the wall clock. No venue call is
possible: the replay client refuses all but ``get_klines``, the filters come from stored
``exchangeInfo`` files (the owner's R-Z), and the credentials are never read.

**Ownership: this root closes the client unconditionally**, as ``live_system`` does and for the
reason ``CLAUDE.md`` gives. Teardown is nested, one scope per object, opened immediately after
that object is bound; the provider is built with ``owns_client=False``, so its ``stop`` closes
nothing and the root's own ``finally`` does.

**Registration order is the contract.** The executor registers on the provider BEFORE the
engine does, because ``TradingEngine.start`` registers the engine's hook, so the executor runs
first on every bar and the strategy deciding on a bar already sees that bar's fills booked.
That order is also what hands an entry the bar AFTER its signal bar (R-AA): were the executor
to meet the signal bar after the engine had decided on it, ``fill_entry`` would be handed a bar
that opened before the order was placed and would raise.

**A run that raised somewhere is not a result.** The provider, the engine and the signal
handler each isolate a failing subscriber, logging it and carrying on, so a run could finish
having skipped fills. The system therefore counts every record logged at ``ERROR`` or above
while it runs, and the stream's own handler failures, and reports both. :attr:`BacktestResult.
complete` is true only if neither occurred, every pair served at least one bar, and the cash
identity below holds.

**The cash identity.** ``initial balance + the sum of realised - the quote total of every
position still open = the free quote``, exactly. It is the booking identity of the unchanged
``Portfolio`` summed over the run, and the record carries its residual.

**The run record** is a JSON object (:func:`write_run` also writes the trades as CSV). It names
the code that ran (commit, dirty state, install kind), the config's digest, the digests of
every series' manifest and registry, the digests of the ``exchangeInfo`` files, the resolved
window, every fill parameter, the strategy, the library versions, what each pair served, and
what came of the run. Everything outside ``wall_clock`` is a function of the code, the config
and the stored bars, so two runs of one history differ only there (:func:`record_digest`).
"""

from __future__ import annotations

import csv
import dataclasses
import hashlib
import json
import logging
import time
from collections.abc import AsyncIterator, Callable, Mapping, Sequence
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from importlib import metadata
from pathlib import Path

from trading_bot.backtesting.exchange_info import Snapshot, SnapshotError, load_snapshot
from trading_bot.backtesting.fill_model import FillParameters
from trading_bot.backtesting.replay import ReplayClient, ReplayStream
from trading_bot.backtesting.simulated_executor import (
    EntryAttempt,
    EntryResult,
    SimulatedExecutor,
    SimulatedTrade,
    trade_log_digest,
    trade_rows,
)
from trading_bot.config.models import BacktestConfig, PairConfig
from trading_bot.config.settings import Secrets, Settings
from trading_bot.core.assessment import PairContext
from trading_bot.core.exceptions import ConfigError, TradingBotError
from trading_bot.core.models import Candle
from trading_bot.core.portfolio import Portfolio
from trading_bot.data.historical import MANIFEST_NAME, REGISTRY_NAME, HistoricalStore, RegistryKind
from trading_bot.data.historical import series_dir as stored_series_dir
from trading_bot.data.market_data import BufferedMarketDataProvider
from trading_bot.engine.live_engine import TradingEngine
from trading_bot.engine.modes import (
    IntentLogger,
    _build_signal_handler,
    _pair_timeframes,
    _require_one_quote_asset,
)
from trading_bot.risk.manager import RiskManager
from trading_bot.utils.helpers import utc_now
from trading_bot.utils.logger import get_logger
from trading_bot.utils.provenance import collect_provenance

__all__ = [
    "RUN_RECORD_SCHEMA",
    "BacktestError",
    "BacktestResult",
    "BacktestSystem",
    "backtest_system",
    "record_digest",
    "run_backtest",
    "select_pairs",
    "write_run",
]

_log = get_logger(__name__)

#: The shape of the run record. Bump it when a key is added, renamed or removed.
RUN_RECORD_SCHEMA = 1

_EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)
_MILLISECOND = timedelta(milliseconds=1)

#: Libraries whose versions a run records, by distribution name.
_LIBRARIES = ("pandas", "numpy", "pydantic", "pydantic-settings", "PyYAML", "python-binance")

#: How many ERROR messages the record keeps, so a failed run says what failed.
_ERRORS_KEPT = 5

#: Facts about the code that ran, as ``collect_provenance`` reports them.
CodeFacts = Callable[[], Mapping[str, str | int | bool]]

_CODE_KEYS = (
    "install_kind",
    "code_commit",
    "checkout_commit",
    "checkout_dirty",
    "dirty_count",
    "commits_agree",
    "python_version",
    "package_version",
)


class BacktestError(TradingBotError):
    """A backtest was driven wrongly: run twice, or asked for what it cannot serve."""


@dataclass(frozen=True)
class BacktestResult:
    """What a run produced. ``record`` is the JSON-ready run record."""

    record: dict[str, object]
    trades: tuple[SimulatedTrade, ...]
    attempts: tuple[EntryAttempt, ...]
    trade_log_sha256: str
    #: Empty when the run is a result; otherwise what made it not one.
    problems: tuple[str, ...]

    @property
    def complete(self) -> bool:
        return not self.problems


class _BarTally:
    """Counts what each pair served; registered as a passive candle subscriber."""

    def __init__(self) -> None:
        self.bars: dict[tuple[str, str], int] = {}
        self.first: dict[tuple[str, str], Candle] = {}
        self.last: dict[tuple[str, str], Candle] = {}

    async def __call__(self, candle: Candle) -> None:
        key = (candle.symbol, candle.timeframe)
        self.bars[key] = self.bars.get(key, 0) + 1
        self.first.setdefault(key, candle)
        self.last[key] = candle


class _ErrorTally(logging.Handler):
    """Counts every record at ERROR or above while attached to the root logger."""

    def __init__(self) -> None:
        super().__init__(level=logging.ERROR)
        self.count = 0
        self.first: list[str] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.count += 1
        if len(self.first) < _ERRORS_KEPT:
            try:
                message = record.getMessage()
            except Exception:  # a malformed log call must not become a second failure
                message = str(record.msg)
            self.first.append(f"{record.name}: {message[:200]}")


@dataclass(frozen=True, slots=True, eq=False)
class BacktestSystem:
    """The assembled backtest, built and torn down by :func:`backtest_system`.

    ``eq=False``: identity is the only meaningful equality for stateful collaborators.
    :meth:`run` may be called once.
    """

    settings: Settings
    window: BacktestConfig
    params: FillParameters
    store: HistoricalStore
    client: ReplayClient
    stream: ReplayStream
    provider: BufferedMarketDataProvider
    engine: TradingEngine
    risk: RiskManager
    portfolio: Portfolio
    pairs: Mapping[str, PairContext]
    executor: SimulatedExecutor
    snapshots: Mapping[str, Snapshot]
    _state: dict[str, object]
    _tally: _BarTally
    _errors: _ErrorTally
    _code_facts: CodeFacts

    async def run(self) -> BacktestResult:
        """Start the engine, replay the window, and describe what happened.

        :raises BacktestError: this system has already run.
        """
        if self._state.get("ran"):
            raise BacktestError("this backtest has already run; build a new system to run again")
        self._state["ran"] = True
        started = utc_now()
        clock_start = time.monotonic()
        root = logging.getLogger()
        root.addHandler(self._errors)
        try:
            # The engine registers its hook here, AFTER the executor's: see the module docstring.
            await self.engine.start()
            delivered = await self.stream.pump(self.window.window_start, self.window.window_end)
            self.executor.finish()
        finally:
            root.removeHandler(self._errors)
        wall_seconds = time.monotonic() - clock_start
        return _describe(
            self,
            delivered=delivered,
            started=started.isoformat(),
            finished=utc_now().isoformat(),
            wall_seconds=wall_seconds,
        )


def _sha256_of(path: Path) -> str | None:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return None


def _version(distribution: str) -> str:
    try:
        return metadata.version(distribution)
    except metadata.PackageNotFoundError:
        return "unknown"


def _default_code_facts(settings: Settings) -> CodeFacts:
    def collect() -> Mapping[str, str | int | bool]:
        fields = collect_provenance(settings.config_path, settings.config_sha256).log_fields()
        return {key: fields[key] for key in _CODE_KEYS}

    return collect


def select_pairs(settings: Settings, symbols: Sequence[str] | None) -> list[PairConfig]:
    """The enabled pairs a run replays: all of them, or the named ones.

    Public so a command can refuse an unenabled symbol BEFORE it makes a run directory.

    :raises ConfigError: a named symbol is not an enabled pair.
    """
    enabled = settings.config.trading.enabled_pairs
    if symbols is None:
        return list(enabled)
    wanted = [symbol.upper() for symbol in symbols]
    known = {pair.symbol for pair in enabled}
    missing = [symbol for symbol in wanted if symbol not in known]
    if missing:
        raise ConfigError(
            f"asked to backtest {', '.join(missing)}, which config.yaml does not enable; the "
            f"enabled pairs are {', '.join(sorted(known)) or 'none'}"
        )
    return [pair for pair in enabled if pair.symbol in wanted]


@asynccontextmanager
async def backtest_system(
    settings: Settings,
    *,
    window: BacktestConfig | None = None,
    symbols: Sequence[str] | None = None,
    exchange_info_environment: str = "mainnet",
    code_facts: CodeFacts | None = None,
) -> AsyncIterator[BacktestSystem]:
    """Assemble the backtest, yield it, and tear it down.

    :param window: the window and costs; ``settings.config.backtesting`` if omitted.
    :param symbols: the enabled pairs to replay; all of them if omitted.
    :param exchange_info_environment: which stored ``exchangeInfo`` to size with; the
        mainnet files for a backtest on mainnet klines, the Testnet ones for S4.
    :param code_facts: how the run names the code that ran; injected by tests, since the
        default runs ``git``.

    :raises ConfigError: a requested symbol is not enabled, no pair is, a symbol is enabled
        on two timeframes, or a pair is quoted in an asset other than the base currency.
    :raises SnapshotError: a symbol has no usable stored ``exchangeInfo``.
    """
    resolved_window = window if window is not None else settings.config.backtesting
    config = settings.config
    selected = select_pairs(settings, symbols)
    effective = Settings(
        config.model_copy(
            update={"trading": config.trading.model_copy(update={"pairs": selected})}
        ),
        Secrets(),
        config_path=settings.config_path,
        config_sha256=settings.config_sha256,
    )
    timeframes = _pair_timeframes(effective)
    root = Path(resolved_window.data_dir)
    snapshots: dict[str, Snapshot] = {}
    for symbol in timeframes:
        try:
            snapshots[symbol] = load_snapshot(root, exchange_info_environment, symbol)
        except SnapshotError as exc:
            raise ConfigError(str(exc)) from exc
    pairs = {
        symbol: PairContext(timeframe=timeframe, symbol_info=snapshots[symbol].symbol_info)
        for symbol, timeframe in timeframes.items()
    }
    quote_asset = config.trading.base_currency
    _require_one_quote_asset(pairs, quote_asset)

    store = HistoricalStore(root)
    client = ReplayClient(store, resolved_window.window_start)
    try:
        stream = ReplayStream(store)
        provider = BufferedMarketDataProvider(
            client,
            stream,
            history_limit=config.data.history_limit,
            buffer_size=config.data.buffer_size,
            owns_client=False,
        )
        for pair in selected:
            provider.track(pair.symbol, pair.timeframe)
        try:
            engine = await TradingEngine.create(effective, provider=provider)
            try:
                portfolio = Portfolio(
                    quote_asset=quote_asset, free_quote=resolved_window.initial_balance
                )
                params = FillParameters.from_config(resolved_window)
                risk = RiskManager(
                    config=config.risk, provider=provider, pairs=pairs, clock=stream.now
                )
                executor = SimulatedExecutor(portfolio=portfolio, params=params, clock=stream.now)
                engine.on_signal(
                    _build_signal_handler(
                        risk=risk,
                        intent_logger=IntentLogger(pairs=pairs),
                        portfolio=portfolio,
                        pairs=pairs,
                        executor=executor,
                    )
                )
                tally = _BarTally()
                provider.on_candle(executor)
                provider.on_candle(tally)
                _log.info(
                    "Backtest ready: %d pair(s), %s %s free, window %s to %s",
                    len(pairs),
                    portfolio.free_quote,
                    portfolio.quote_asset,
                    resolved_window.start_date.isoformat(),
                    resolved_window.end_date.isoformat(),
                )
                yield BacktestSystem(
                    settings=effective,
                    window=resolved_window,
                    params=params,
                    store=store,
                    client=client,
                    stream=stream,
                    provider=provider,
                    engine=engine,
                    risk=risk,
                    portfolio=portfolio,
                    pairs=pairs,
                    executor=executor,
                    snapshots=snapshots,
                    _state={},
                    _tally=tally,
                    _errors=_ErrorTally(),
                    _code_facts=code_facts or _default_code_facts(effective),
                )
            finally:
                await engine.stop()
        finally:
            await provider.stop()
    finally:
        await client.close()


async def run_backtest(
    settings: Settings,
    *,
    window: BacktestConfig | None = None,
    symbols: Sequence[str] | None = None,
    exchange_info_environment: str = "mainnet",
    code_facts: CodeFacts | None = None,
) -> BacktestResult:
    """Build a system, run it once, tear it down, and return what it produced."""
    async with backtest_system(
        settings,
        window=window,
        symbols=symbols,
        exchange_info_environment=exchange_info_environment,
        code_facts=code_facts,
    ) as system:
        return await system.run()


# --------------------------------------------------------------------------
# The run record
# --------------------------------------------------------------------------
def _pair_record(system: BacktestSystem, symbol: str, timeframe: str) -> dict[str, object]:
    key = (symbol, timeframe)
    tally = system._tally
    directory = stored_series_dir(system.store.root, symbol, timeframe)
    start_ms = _ms(system.window.window_start)
    end_ms = _ms(system.window.window_end)
    registry = (
        system.store.registry(symbol, timeframe) if (directory / REGISTRY_NAME).is_file() else ()
    )
    in_window = [line for line in registry if start_ms <= line.open_time_ms < end_ms]
    first, last = tally.first.get(key), tally.last.get(key)
    return {
        "symbol": symbol,
        "timeframe": timeframe,
        "bars_served": tally.bars.get(key, 0),
        "first_open_time": None if first is None else first.open_time.isoformat(),
        "last_open_time": None if last is None else last.open_time.isoformat(),
        "manifest_sha256": _sha256_of(directory / MANIFEST_NAME),
        "registry_sha256": _sha256_of(directory / REGISTRY_NAME),
        "registry_quarantined_in_window": sum(
            1 for line in in_window if line.kind is RegistryKind.QUARANTINED
        ),
        "registry_registered_in_window": sum(
            1 for line in in_window if line.kind is RegistryKind.REGISTERED
        ),
    }


def _ms(moment: datetime) -> int:
    """Exact integer milliseconds since the epoch; a float timestamp would round off the grid."""
    return (moment - _EPOCH) // _MILLISECOND


def _describe(
    system: BacktestSystem, *, delivered: int, started: str, finished: str, wall_seconds: float
) -> BacktestResult:
    executor = system.executor
    trades, attempts, counts = executor.trades, executor.attempts, executor.counts
    unsettled = executor.unsettled
    digest = trade_log_digest(trades)
    portfolio = system.portfolio
    initial = system.window.initial_balance
    realised = sum((trade.realised for trade in trades), Decimal(0))
    open_cost = sum(
        (
            position.entry_quote_total if position.entry_quote_total is not None else Decimal(0)
            for position in portfolio.open_positions
        ),
        Decimal(0),
    )
    residual = initial + realised - open_cost - portfolio.free_quote
    pair_rows = [
        _pair_record(system, symbol, context.timeframe) for symbol, context in system.pairs.items()
    ]
    problems: list[str] = []
    if system.stream.failures:
        problems.append(f"stream_handler_failures={system.stream.failures}")
    if system._errors.count:
        problems.append(f"error_log_records={system._errors.count}")
    problems.extend(
        f"{row['symbol']} {row['timeframe']} served no bars"
        for row in pair_rows
        if row["bars_served"] == 0
    )
    if residual != 0:
        problems.append(f"cash_identity_residual={residual}")
    by_result = dict.fromkeys(EntryResult, 0)
    for attempt in attempts:
        by_result[attempt.result] += 1
    strategy = system.settings.config.strategy
    record: dict[str, object] = {
        "schema": RUN_RECORD_SCHEMA,
        "code": dict(system._code_facts()),
        "config": {
            "path": None
            if system.settings.config_path is None
            else str(system.settings.config_path),
            "sha256": system.settings.config_sha256,
        },
        "window": {
            "start_date": system.window.start_date.isoformat(),
            "end_date": system.window.end_date.isoformat(),
            "start": system.window.window_start.isoformat(),
            "end": system.window.window_end.isoformat(),
            "data_dir": system.window.data_dir,
        },
        "fill_parameters": {
            "fee_percent": str(system.params.fee_percent),
            "slippage_percent": str(system.params.slippage_percent),
            "stop_slippage_percent": str(system.params.stop_slippage_percent),
            "initial_balance": str(initial),
        },
        "strategy": {"name": strategy.name, "params": dict(strategy.params)},
        "exchange_info": {
            symbol: {"environment": snap.environment, "sha256": snap.sha256}
            for symbol, snap in system.snapshots.items()
        },
        "pairs": pair_rows,
        "libraries": {name: _version(name) for name in _LIBRARIES},
        "stream": {"bars_delivered": delivered, "handler_failures": system.stream.failures},
        "executor": {name: getattr(counts, name) for name in counts.__dataclass_fields__},
        "entries": {result.value: n for result, n in by_result.items()},
        "results": {
            "trades": len(trades),
            "trades_spanning_a_gap": sum(1 for t in trades if t.spans_gap),
            "trades_spanning_a_short_bar": sum(1 for t in trades if t.spans_short_bar),
            "realised_total": str(realised),
            "entry_fees_total": str(sum((t.entry_fee for t in trades), Decimal(0))),
            "exit_fees_total": str(sum((t.exit_fee for t in trades), Decimal(0))),
            "final_free_quote": str(portfolio.free_quote),
            "open_positions_at_end": list(unsettled["open_positions"]),
            "pending_entries_at_end": list(unsettled["pending_entries"]),
            "queued_closes_at_end": list(unsettled["queued_closes"]),
            "cash_identity_residual": str(residual),
            "trade_log_sha256": digest,
        },
        "error_log_records": {"count": system._errors.count, "first": list(system._errors.first)},
        "problems": list(problems),
        "wall_clock": {
            "started_at_utc": started,
            "finished_at_utc": finished,
            "wall_seconds": round(wall_seconds, 3),
        },
    }
    return BacktestResult(
        record=record,
        trades=trades,
        attempts=attempts,
        trade_log_sha256=digest,
        problems=tuple(problems),
    )


def record_digest(record: Mapping[str, object]) -> str:
    """The SHA-256 of a run record without its ``wall_clock`` block.

    Everything else is a function of the code, the config and the stored bars, so two runs of
    one history return the same digest and a changed fill parameter does not.
    """
    stable = {key: value for key, value in record.items() if key != "wall_clock"}
    text = json.dumps(stable, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def write_run(
    result: BacktestResult, directory: Path, *, existing: bool = False
) -> tuple[Path, Path]:
    """Write ``run.json`` and ``trades.csv`` into ``directory``; return their paths.

    By default ``directory`` must be NEW. With ``existing=True`` it must already exist, as
    the directory a command made to hold its own log does; either way each file is created
    with mode ``x``, so no earlier run's file is ever overwritten.

    :raises FileExistsError: ``directory`` exists (default), or one of the two files does.
    :raises FileNotFoundError: ``existing`` is set and ``directory`` does not exist.
    """
    if existing:
        if not directory.is_dir():
            raise FileNotFoundError(directory)
    else:
        directory.mkdir(parents=True, exist_ok=False)
    run_path = directory / "run.json"
    with run_path.open("x", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(result.record, sort_keys=True, indent=2) + "\n")
    trades_path = directory / "trades.csv"
    with trades_path.open("x", encoding="utf-8", newline="") as handle:
        # The header is the dataclass's, so a run with no trade still writes the columns.
        names = [field.name for field in dataclasses.fields(SimulatedTrade)]
        writer = csv.DictWriter(handle, fieldnames=names, lineterminator="\n")
        writer.writeheader()
        writer.writerows(trade_rows(result.trades))
    return run_path, trades_path
