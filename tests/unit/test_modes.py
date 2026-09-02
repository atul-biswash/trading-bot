"""Tests for the composition root -- boot, teardown, and the observable stream.

Hermetic: no network and no real time. Both leaf adapters are injected --
``client`` is a scripted :class:`FakeRootClient` and ``stream`` a
:class:`FakeStream`-- so the boot path under test is byte-for-byte the one
production takes. Injecting a whole *provider* would skip the step that wires
the provider to the client, and that step is exactly what the ownership
behaviour depends on.

The ten refusal stages are driven through the **real** ``RiskManager.evaluate``
rather than hand-built assessments, and that stays the point of the test even
now that ``evaluate`` reports the stage itself. A hand-built assessment asserts
only that pydantic stored what it was handed; making ``evaluate`` actually take
each branch is what pins the label to the code path. Its fixtures are borrowed
from ``test_risk_manager`` for the same reason -- they are the setups already
proven to reach those branches.
"""

from __future__ import annotations

import logging
from contextlib import contextmanager
from dataclasses import FrozenInstanceError
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import TYPE_CHECKING, Any

import pytest

from tests.unit.test_live_engine import FakeMarketDataProvider, ScriptedStrategy
from tests.unit.test_live_engine import candle as engine_candle
from tests.unit.test_risk_manager import (
    NOW,
    SYMBOL,
    TIMEFRAME,
    FakeProvider,
    build_manager,
    buy,
    candle,
    entry_levels,
    long_position,
    multi_pairs,
    ohlcv,
    risk_config,
    symbol_info,
)
from trading_bot.config.models import StopLossConfig, TakeProfitConfig
from trading_bot.core.assessment import EntryIntent
from trading_bot.core.enums import (
    OrderSide,
    PositionSide,
    PositionSizingMethod,
    ProtectionState,
    RefusalStage,
    RiskRule,
    SignalAction,
    StopType,
)
from trading_bot.core.exceptions import (
    ConfigError,
    ExchangeAPIError,
    StrategyNotFoundError,
    TradingBotError,
)
from trading_bot.core.interfaces import (
    CandleHandler,
    ExchangeClient,
    MarketDataStream,
)
from trading_bot.core.models import (
    Balance,
    Candle,
    Order,
    OrderList,
    OrderRequest,
    OtocoOrderListRequest,
    OtoOrderListRequest,
    Position,
    Signal,
    SymbolInfo,
    Ticker,
)
from trading_bot.core.portfolio import Ledger, Portfolio
from trading_bot.engine.live_engine import TradingEngine
from trading_bot.engine.modes import (
    IntentLogger,
    LiveSystem,
    _build_signal_handler,
    _pair_timeframes,
    _seed_portfolio,
    live_system,
)
from trading_bot.exchange.ids import list_client_order_id
from trading_bot.execution.executor import PendingPlacement
from trading_bot.persistence import store
from trading_bot.risk.manager import PairContext, RiskAssessment, RiskManager
from trading_bot.utils.instance_lock import acquire as acquire_instance_lock
from trading_bot.utils.logger import surplus_fields

if TYPE_CHECKING:  # pragma: no cover - typing only
    from collections.abc import Iterator, Mapping, Sequence
    from pathlib import Path

D = Decimal

_KEY = (SYMBOL, TIMEFRAME)

#: The only logger whose records these tests own. Other collaborators log into
#: the same caplog buffer, so records are always selected by name.
_MODES_LOGGER = "trading_bot.engine.modes"


@pytest.fixture(autouse=True)
def _isolate_run_artefacts(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Point every relative run-artefact path at ``tmp_path``, for the whole module.

    **AUTOUSE AND MODULE-WIDE, because it is not a convenience.**
    ``live_system`` now calls ``store.load()``, whose default
    ``DEFAULT_STORE_PATH`` is the RELATIVE ``data/state.json``. Without this,
    every boot test in this file would read the operator's real state file --
    so the suite's result would depend on an untracked artefact that only a
    live run produces. A valid one would seed the executor with somebody's
    pending placements; a corrupt one would fail this entire file with
    ``StoreCorruptError`` and name a cause that has nothing to do with the
    tree.

    That is not hypothetical in the ordinary sense: ``data/state.json`` does
    not exist today precisely because nothing has written it yet, and the
    commit adding this is the one that gives it a reader.

    ``DEFAULT_LOCK_PATH`` is relative for the same reason and is covered by the
    same ``chdir``, which is defence rather than a fix -- no test in this file
    reaches the unparameterised ``acquire_instance_lock()`` today.

    ``chdir`` rather than patching ``DEFAULT_STORE_PATH``: a default argument
    is bound at function definition, so rebinding the module constant would
    not change what ``load()`` reads, and a test that patched it would pass
    while pinning nothing.
    """
    monkeypatch.chdir(tmp_path)


# --------------------------------------------------------------------------
# Scripted fakes
# --------------------------------------------------------------------------
#: Module-level so it can be a default argument: ruff's B008 forbids calling a
#: function in a signature default.
_DEFAULT_TICKER_LAST = D("100")

#: Distinguishes "no client id was given, derive one" from an explicit ``None``,
#: which is a real venue state -- the placement response returns ``null`` when a
#: list terminates in the same call.
_UNSET_CLIENT_ID = "<derive>"

#: A bar far enough in the past to be unmistakably not "now" -- the boot scan
#: must match on SYMBOL alone, since `entry_bar_time` is unknowable after a
#: restart, and a fixture whose bar happened to be current could hide a matcher
#: that compared it.
_LIST_BAR = datetime(2026, 8, 14, 12, 0, tzinfo=timezone.utc)


def _live_list_for(
    symbol: str,
    *,
    status: str = "EXECUTING",
    client_id: str | None = _UNSET_CLIENT_ID,
) -> OrderList:
    """One entry of the boot scan's enumeration, as `get_all_order_lists` returns it.

    ``client_id`` defaults to a correctly derived id for ``symbol``. Passing one
    explicitly is how a fixture expresses a list that is NOT ours -- which is
    the only way the prefix-matching regression can be caught.
    """
    return OrderList(
        order_list_id="255471",
        symbol=symbol,
        list_client_order_id=(
            list_client_order_id(symbol, _LIST_BAR) if client_id is _UNSET_CLIENT_ID else client_id
        ),
        list_status_type="EXEC_STARTED",
        list_order_status=status,
    )


class FakeRootClient(ExchangeClient):
    """Serves the boot calls -- symbol info, balances, tickers -- and counts closes."""

    def __init__(
        self,
        *,
        balances: list[Balance] | None = None,
        unknown_symbols: frozenset[str] = frozenset(),
        journal: list[str] | None = None,
        balances_error: Exception | None = None,
        ticker_last: Decimal = _DEFAULT_TICKER_LAST,
        order_lists: list[OrderList] | None = None,
        order_lists_error: Exception | None = None,
    ) -> None:
        self._balances = (
            balances
            if balances is not None
            else [Balance(asset="USDT", free=D("5000"), locked=D("0"))]
        )
        self._unknown = unknown_symbols
        self._journal = journal if journal is not None else []
        self._balances_error = balances_error
        self._ticker_last = ticker_last
        self._order_lists = order_lists if order_lists is not None else []
        self._order_lists_error = order_lists_error
        self.symbol_info_calls: list[str] = []
        self.order_list_calls = 0
        self.close_calls = 0

    async def get_symbol_info(self, symbol: str) -> SymbolInfo:
        self.symbol_info_calls.append(symbol)
        self._journal.append(f"symbol_info:{symbol}")
        if symbol in self._unknown:
            raise ExchangeAPIError(f"Unknown symbol: {symbol!r}")
        return symbol_info(symbol=symbol)

    async def get_balances(self) -> list[Balance]:
        self._journal.append("balances")
        if self._balances_error is not None:
            raise self._balances_error
        return list(self._balances)

    async def get_klines(self, symbol: str, timeframe: str, *, limit: int = 500) -> list[Candle]:
        self._journal.append(f"seed:{symbol}/{timeframe}")
        return []

    async def close(self) -> None:
        self.close_calls += 1
        self._journal.append("close_client")

    async def get_ticker(self, symbol: str) -> Ticker:
        self._journal.append(f"ticker:{symbol}")
        return Ticker(
            symbol=symbol,
            bid=D("100"),
            ask=D("100"),
            last=self._ticker_last,
            timestamp=NOW,
        )

    async def create_order(self, request: OrderRequest) -> Order:  # pragma: no cover
        raise NotImplementedError

    async def cancel_order(self, symbol: str, order_id: str) -> Order:  # pragma: no cover
        raise NotImplementedError

    async def get_open_orders(self, symbol: str | None = None) -> list[Order]:  # pragma: no cover
        raise NotImplementedError

    async def get_own_open_orders(  # pragma: no cover
        self,
        symbol: str,
        *,
        timeout_s: float | None = None,
        attempts: int | None = None,
    ) -> list[Order]:
        raise NotImplementedError

    async def get_order(  # pragma: no cover
        self,
        symbol: str,
        *,
        order_id: str | None = None,
        client_order_id: str | None = None,
        timeout_s: float | None = None,
        attempts: int | None = None,
    ) -> Order:
        raise NotImplementedError

    async def get_all_order_lists(
        self,
        *,
        timeout_s: float | None = None,
        attempts: int | None = None,
    ) -> list[OrderList]:
        """The boot's live-order-list scan. Empty by default: the ordinary boot.

        It stopped being ``NotImplementedError`` when ``live_system`` began
        calling it -- every test of the boot path reaches it now, so a raise
        here would make the fixture, not the code, decide the result.
        """
        self.order_list_calls += 1
        self._journal.append("order_lists")
        if self._order_lists_error is not None:
            raise self._order_lists_error
        return list(self._order_lists)

    async def create_otoco_order_list(  # pragma: no cover
        self,
        request: OtocoOrderListRequest,
        *,
        timeout_s: float | None = None,
        attempts: int | None = None,
    ) -> OrderList:
        raise NotImplementedError

    async def create_oto_order_list(  # pragma: no cover
        self,
        request: OtoOrderListRequest,
        *,
        timeout_s: float | None = None,
        attempts: int | None = None,
    ) -> OrderList:
        raise NotImplementedError


class FakeStream(MarketDataStream):
    """Records lifecycle calls so teardown ordering is observable."""

    def __init__(self, journal: list[str] | None = None) -> None:
        self._journal = journal if journal is not None else []
        self.handlers: dict[tuple[str, str], CandleHandler] = {}
        self.start_calls = 0
        self.stop_calls = 0

    def subscribe(self, symbol: str, timeframe: str, handler: CandleHandler) -> None:
        self.handlers[(symbol, timeframe)] = handler

    async def start(self) -> None:
        self.start_calls += 1
        self._journal.append("stream_start")

    async def stop(self) -> None:
        self.stop_calls += 1
        self._journal.append("stream_stop")


class BoomRiskManager(RiskManager):
    """A risk manager whose ``evaluate`` raises, to exercise the handler's catch."""

    def evaluate(self, signal: Signal, *, portfolio: Portfolio) -> RiskAssessment:
        raise RuntimeError("risk exploded")


class BoomIntentLogger(IntentLogger):
    """An intent logger whose ``record`` raises."""

    async def record(self, signal: Signal, assessment: RiskAssessment) -> None:
        raise RuntimeError("logger exploded")


# --------------------------------------------------------------------------
# Settings builder
# --------------------------------------------------------------------------
_PAIRS_BLOCK = """    - symbol: {symbol}
      timeframe: {timeframe}
      enabled: {enabled}
"""


def write_settings(
    tmp_path: Path,
    *,
    pairs: tuple[tuple[str, str, bool], ...] = ((SYMBOL, TIMEFRAME, True),),
    base_currency: str = "USDT",
    mode: str = "testnet",
    strategy: str = "sma_crossover",
) -> Any:
    """Write a minimal config.yaml and load it through the real settings path."""
    from trading_bot.config.settings import get_settings

    # An empty tuple has to render as an explicit `[]`: a bare `pairs:` with no
    # block under it parses as None, which pydantic rejects for a list field --
    # so the test would fail at config load rather than reaching the guard.
    block = (
        "  pairs: []\n"
        if not pairs
        else "  pairs:\n"
        + "".join(
            _PAIRS_BLOCK.format(symbol=symbol, timeframe=timeframe, enabled=str(enabled).lower())
            for symbol, timeframe, enabled in pairs
        )
    )
    path = tmp_path / "modes_config.yaml"
    path.write_text(
        f"mode: {mode}\n"
        "trading:\n"
        f"  base_currency: {base_currency}\n"
        f"{block}"
        f"strategy:\n  name: {strategy}\n"
        "backtesting:\n  start_date: '2024-01-01'\n  end_date: '2024-02-01'\n"
        "logging:\n  console: false\n  file:\n    enabled: false\n",
        encoding="utf-8",
    )
    get_settings.cache_clear()
    return get_settings(str(path))


def default_pairs() -> dict[str, PairContext]:
    return {SYMBOL: PairContext(timeframe=TIMEFRAME, symbol_info=symbol_info())}


# --------------------------------------------------------------------------
# The ten refusal paths, driven through the real evaluate()
# --------------------------------------------------------------------------
Case = tuple[Signal, RiskAssessment, "Mapping[str, PairContext]"]


def _case_unknown_pair() -> Case:
    manager, _ = build_manager()
    signal = buy(symbol="DOGEUSDT")
    return (
        signal,
        manager.evaluate(signal, portfolio=Portfolio(free_quote=D("10000"))),
        default_pairs(),
    )


def _case_no_reference_price() -> Case:
    manager, _ = build_manager()
    signal = Signal(symbol=SYMBOL, action=SignalAction.BUY, timestamp=NOW)
    return (
        signal,
        manager.evaluate(signal, portfolio=Portfolio(free_quote=D("10000"))),
        default_pairs(),
    )


def _case_nothing_to_close() -> Case:
    manager, _ = build_manager()
    signal = Signal(symbol=SYMBOL, action=SignalAction.CLOSE, price=D("100"), timestamp=NOW)
    return (
        signal,
        manager.evaluate(signal, portfolio=Portfolio(free_quote=D("1000"))),
        default_pairs(),
    )


def _case_unsupported_action() -> Case:
    manager, _ = build_manager()
    signal = Signal(symbol=SYMBOL, action=SignalAction.SELL, price=D("100"), timestamp=NOW)
    return (
        signal,
        manager.evaluate(signal, portfolio=Portfolio(free_quote=D("10000"))),
        default_pairs(),
    )


def _case_no_mark_price() -> Case:
    """An open ETHUSDT position the provider has no candle for: equity is unknown."""
    pairs = multi_pairs(SYMBOL, "ETHUSDT")
    manager, _ = build_manager(provider=FakeProvider(candles={}), pairs=pairs)
    portfolio = Portfolio(
        free_quote=D("10000"), positions={"ETHUSDT": long_position(symbol="ETHUSDT")}
    )
    signal = buy()
    return signal, manager.evaluate(signal, portfolio=portfolio), pairs


def _case_committed_risk_unknown() -> Case:
    """A PRICEABLE open position with no computable stop, while stops are ON.

    Distinct from `_case_no_mark_price` in exactly one fact: the provider has a
    candle for the position, so equity is knowable and only its *forward* risk
    is not. The signal names a different symbol so `ALREADY_IN_POSITION` cannot
    be what fires.
    """
    pairs = multi_pairs(SYMBOL, "ETHUSDT")
    manager, _ = build_manager(
        provider=FakeProvider(candles={SYMBOL: candle(), "ETHUSDT": candle(symbol="ETHUSDT")}),
        pairs=pairs,
    )
    portfolio = Portfolio(
        free_quote=D("10000"),
        positions={"ETHUSDT": long_position(symbol="ETHUSDT")},  # no stop level
    )
    signal = buy()
    return signal, manager.evaluate(signal, portfolio=portfolio), pairs


def _case_position_stale() -> Case:
    """A priceable, TRUSTED position whose last complete reconciliation is old.

    Built on an OLD STAMP rather than `None`, deliberately. `None` is maximally
    stale too, but folding both into one case would make a mutation of the
    `None` branch and a mutation of the comparison indistinguishable here; each
    gets its own test in `test_risk_manager.py` so each stays attributable.

    `ABSENT_BY_DESIGN` with a stop level is the pairing that reaches the pricing
    arm, so this position is computable and cannot be what
    `COMMITTED_RISK_UNKNOWN` fires on -- this case must isolate staleness, and
    the adjacency between the two guards is pinned separately by an input that
    trips both.
    """
    pairs = multi_pairs(SYMBOL, "ETHUSDT")
    manager, _ = build_manager(
        provider=FakeProvider(candles={SYMBOL: candle(), "ETHUSDT": candle(symbol="ETHUSDT")}),
        pairs=pairs,
    )
    portfolio = Portfolio(
        free_quote=D("10000"),
        positions={
            "ETHUSDT": long_position(
                symbol="ETHUSDT",
                stop_loss=D("90"),
                protection=ProtectionState.ABSENT_BY_DESIGN,
                last_reconciled_at=NOW - timedelta(hours=1),
            )
        },
    )
    signal = buy()
    return signal, manager.evaluate(signal, portfolio=portfolio), pairs


def _case_unmanaged_holding() -> Case:
    """A material base holding the bot did not open, on the signal's symbol.

    `positions` is empty and that is doing double duty: it keeps NO_MARK_PRICE
    and COMMITTED_RISK_UNKNOWN silent (nothing to price, nothing uncomputable),
    and it keeps ALREADY_IN_POSITION silent -- which is precisely the hazard
    this refusal exists for. Without it the BUY would pyramid onto the holding.
    """
    pairs = default_pairs()
    manager, _ = build_manager(pairs=pairs)
    portfolio = Portfolio(
        free_quote=D("10000"),
        positions={},
        unmanaged_holdings={SYMBOL: D("0.5")},
    )
    signal = buy()
    return signal, manager.evaluate(signal, portfolio=portfolio), pairs


def _case_live_order_list() -> Case:
    """An order list of OURS still working at the venue on the signal's symbol.

    `positions` is empty and doing the same double duty as the unmanaged-holding
    case: nothing to price, nothing uncomputable, and `ALREADY_IN_POSITION`
    silent -- which is exactly the hazard. A restart forgets the `Position`, so
    the BUY would pyramid onto a live list without this guard.
    """
    pairs = default_pairs()
    manager, _ = build_manager(pairs=pairs)
    portfolio = Portfolio(
        free_quote=D("10000"),
        positions={},
        blocked_symbols={SYMBOL: "venue list 255471 is still working"},
    )
    signal = buy()
    return signal, manager.evaluate(signal, portfolio=portfolio), pairs


def _case_limit_refused() -> Case:
    manager, _ = build_manager()
    signal = buy()
    return signal, manager.evaluate(signal, portfolio=Portfolio(free_quote=D("0"))), default_pairs()


def _case_atr_unavailable() -> Case:
    """ATR needs period + 1 clean bars; 14 bars for a 14-period ATR is one short."""
    pairs = default_pairs()
    manager, _ = build_manager(
        config=risk_config(
            stop_loss=StopLossConfig(type=StopType.ATR, atr_period=14),
            take_profit=TakeProfitConfig(enabled=False),
        ),
        provider=FakeProvider(frames={SYMBOL: ohlcv(14)}, candles={SYMBOL: candle()}),
        pairs=pairs,
    )
    signal = buy()
    return signal, manager.evaluate(signal, portfolio=Portfolio(free_quote=D("10000"))), pairs


def _case_stop_unplaceable() -> Case:
    """A 0.1% stop on a 1.00 tick collapses onto entry: representable, not a raise."""
    pairs = {SYMBOL: PairContext(timeframe=TIMEFRAME, symbol_info=symbol_info(price_tick="1.00"))}
    manager, _ = build_manager(
        config=risk_config(
            stop_loss=StopLossConfig(percent=D("0.1")),
            take_profit=TakeProfitConfig(enabled=False),
        ),
        pairs=pairs,
    )
    signal = buy("100")
    return signal, manager.evaluate(signal, portfolio=Portfolio(free_quote=D("10000"))), pairs


def _case_size_not_tradeable() -> Case:
    pairs = {SYMBOL: PairContext(timeframe=TIMEFRAME, symbol_info=symbol_info(min_notional="5000"))}
    manager, _ = build_manager(pairs=pairs)
    signal = buy()
    return signal, manager.evaluate(signal, portfolio=Portfolio(free_quote=D("500"))), pairs


def _case_unaffordable() -> Case:
    """Equity is 10050, almost all deployed in ETHUSDT; a 100-quote order still won't fit."""
    pairs = multi_pairs(SYMBOL, "ETHUSDT")
    manager, _ = build_manager(
        config=risk_config(method=PositionSizingMethod.FIXED_AMOUNT),
        provider=FakeProvider(candles={"ETHUSDT": candle(symbol="ETHUSDT")}),
        pairs=pairs,
    )
    portfolio = Portfolio(
        free_quote=D("50"),
        # A trusted stop, so this case refuses on affordability rather than on
        # an uncomputable committed risk one guard earlier.
        positions={
            "ETHUSDT": long_position(
                symbol="ETHUSDT",
                quantity="100",
                entry="100",
                stop_loss=D("99"),
                protection=ProtectionState.ABSENT_BY_DESIGN,
            )
        },
    )
    signal = buy()
    return signal, manager.evaluate(signal, portfolio=portfolio), pairs


# Fourteen paths, one row each. Defined at module level rather than inline in
# `parametrize` so the correspondence to `evaluate`'s branches stays readable.
_STAGE_CASES = [
    (RefusalStage.UNKNOWN_PAIR, _case_unknown_pair),
    (RefusalStage.NO_REFERENCE_PRICE, _case_no_reference_price),
    (RefusalStage.NOTHING_TO_CLOSE, _case_nothing_to_close),
    (RefusalStage.UNSUPPORTED_ACTION, _case_unsupported_action),
    (RefusalStage.NO_MARK_PRICE, _case_no_mark_price),
    (RefusalStage.POSITION_STALE, _case_position_stale),
    (RefusalStage.COMMITTED_RISK_UNKNOWN, _case_committed_risk_unknown),
    (RefusalStage.LIMIT_REFUSED, _case_limit_refused),
    (RefusalStage.LIVE_ORDER_LIST, _case_live_order_list),
    (RefusalStage.UNMANAGED_HOLDING, _case_unmanaged_holding),
    (RefusalStage.ATR_UNAVAILABLE, _case_atr_unavailable),
    (RefusalStage.STOP_UNPLACEABLE, _case_stop_unplaceable),
    (RefusalStage.SIZE_NOT_TRADEABLE, _case_size_not_tradeable),
    (RefusalStage.UNAFFORDABLE, _case_unaffordable),
]


class TestRefusalStages:
    """What `evaluate` reports, and -- for inputs that trip two guards -- which
    guard it reports.

    The stage is now read off the assessment rather than inferred from it, so
    these tests assert `evaluate`'s own answer. What they still have to pin is
    its **guard order**: an input satisfying one guard cannot detect a reorder,
    because whichever guard runs first is the one that fires either way. Only an
    input satisfying *two* guards distinguishes the orderings, and each ordering
    test below supplies one.
    """

    @pytest.mark.parametrize(
        ("expected", "build"), _STAGE_CASES, ids=[stage.value for stage, _ in _STAGE_CASES]
    )
    def test_every_refusal_path_reports_its_stage(self, expected: RefusalStage, build: Any) -> None:
        """The anti-rot test: each case makes the real evaluate() take one branch."""
        _signal, assessment, _pairs = build()

        assert not assessment.approved
        assert assessment.stage is expected

    def test_the_cases_cover_every_stage(self) -> None:
        """Every member is a reachable path -- there is no unreachable value
        left in the enum for a future refusal to default into."""
        covered = {stage for stage, _ in _STAGE_CASES}
        assert covered == set(RefusalStage)

    def test_a_close_for_an_unknown_symbol_is_unknown_pair_not_nothing_to_close(self) -> None:
        """Pins the pair-context check ahead of the CLOSE dispatch.

        Both guards hold for this input. `evaluate` resolves the pair context
        first, which is right: a CLOSE for a symbol it has no filters for cannot
        be priced or sized, so "we do not know this pair" is the more
        fundamental answer than "there is nothing open in it".
        """
        manager, _ = build_manager()
        signal = Signal(symbol="DOGEUSDT", action=SignalAction.CLOSE, price=D("100"), timestamp=NOW)
        assessment = manager.evaluate(signal, portfolio=Portfolio(free_quote=D("1000")))

        assert assessment.stage is RefusalStage.UNKNOWN_PAIR

    def test_an_unknown_symbol_without_a_price_is_unknown_pair(self) -> None:
        """Pins the pair-context check ahead of the reference-price check.

        Both guards hold for this input. The ten parametrized cases each satisfy
        exactly one guard, so none of them can detect this swap.
        """
        manager, _ = build_manager()
        signal = Signal(symbol="DOGEUSDT", action=SignalAction.BUY, timestamp=NOW)
        assessment = manager.evaluate(signal, portfolio=Portfolio(free_quote=D("10000")))

        assert assessment.stage is RefusalStage.UNKNOWN_PAIR

    def test_a_close_without_a_price_is_no_reference_price(self) -> None:
        """Pins the reference-price check ahead of the CLOSE dispatch.

        Both guards hold for this input, and the price check winning is right:
        an exit still needs a price to be priced at.
        """
        manager, _ = build_manager()
        signal = Signal(symbol=SYMBOL, action=SignalAction.CLOSE, timestamp=NOW)
        assessment = manager.evaluate(signal, portfolio=Portfolio(free_quote=D("10000")))

        assert assessment.stage is RefusalStage.NO_REFERENCE_PRICE

    def test_a_limit_refusal_beats_an_unavailable_atr(self) -> None:
        """Pins the limit check ahead of the ATR bridge.

        Both guards hold: the portfolio already holds BTCUSDT, which trips
        ALREADY_IN_POSITION in `_approve`, *and* the buffer is one bar short of
        what a 14-period ATR needs, so `_atr_value` returns None. The limits win,
        which is right -- there is no point pricing a stop for an entry that is
        refused outright, and the ATR bridge is the more expensive check.

        This is the only adjacent pair on the approved path that is separately
        satisfiable; `decision` is bound before both guards, so a swap still
        compiles and reports the wrong stage rather than crashing. See the M4b
        entry in docs/PHASE_HISTORY.md for the pairs left unpinned and why.
        """
        pairs = {SYMBOL: PairContext(timeframe=TIMEFRAME, symbol_info=symbol_info())}
        manager, _ = build_manager(
            config=risk_config(
                stop_loss=StopLossConfig(type=StopType.ATR, atr_period=14),
                take_profit=TakeProfitConfig(enabled=False),
            ),
            # 14 bars is one short of the atr_period + 1 the bridge demands.
            provider=FakeProvider(frames={SYMBOL: ohlcv(14)}, candles={SYMBOL: candle()}),
            pairs=pairs,
        )
        # A trusted stop, so committed risk is computable and the pair under
        # test is genuinely limits-versus-ATR.
        portfolio = Portfolio(
            free_quote=D("10000"),
            positions={
                SYMBOL: long_position(
                    stop_loss=D("99"), protection=ProtectionState.ABSENT_BY_DESIGN
                )
            },
        )

        assessment = manager.evaluate(buy(), portfolio=portfolio)

        assert assessment.stage is RefusalStage.LIMIT_REFUSED
        assert assessment.decision is not None
        assert assessment.decision.rule is RiskRule.ALREADY_IN_POSITION


# --------------------------------------------------------------------------
# The log schema
# --------------------------------------------------------------------------
def _records(caplog: pytest.LogCaptureFixture, event: str) -> list[logging.LogRecord]:
    return [r for r in caplog.records if getattr(r, "event", None) == event]


def _fields(record: logging.LogRecord) -> dict[str, object]:
    return surplus_fields(record)


async def _emit_one(
    caplog: pytest.LogCaptureFixture, signal: Signal, assessment: RiskAssessment, pairs: Any
) -> logging.LogRecord:
    """Emit one assessment and return the record *this module* produced.

    Filtered by logger name rather than taking ``caplog.records[0]``:
    ``at_level`` lowers the capture handler's level globally, so a collaborator
    that logs on its own -- ``RiskManager.evaluate`` emits "Risk approved" at
    INFO -- lands in the same buffer whenever an earlier test has left the root
    level low. That made this helper pass in isolation and fail in a full run.
    """
    logger = IntentLogger(pairs=pairs)
    with caplog.at_level(logging.DEBUG, logger=_MODES_LOGGER):
        await logger.record(signal, assessment)
    mine = [record for record in caplog.records if record.name == _MODES_LOGGER]
    assert len(mine) == 1
    return mine[0]


class TestLogSchema:
    async def test_a_refusal_carries_the_full_refusal_field_set(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        signal, assessment, pairs = _case_limit_refused()

        record = await _emit_one(caplog, signal, assessment, pairs)

        assert _fields(record) == {
            "event": "risk_refused",
            "symbol": SYMBOL,
            "timeframe": TIMEFRAME,
            "action": "BUY",
            "signal_ts": NOW.isoformat(),
            "stage": "limit_refused",
            "rule_fired": "no_equity",
            "reason": assessment.reason,
        }

    async def test_rule_fired_is_present_on_a_limit_refusal(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        signal, assessment, pairs = _case_no_mark_price()

        record = await _emit_one(caplog, signal, assessment, pairs)

        assert _fields(record)["rule_fired"] == "no_mark_price"

    @pytest.mark.parametrize(
        "build",
        [
            _case_atr_unavailable,
            _case_stop_unplaceable,
            _case_size_not_tradeable,
            _case_unaffordable,
        ],
        ids=["atr", "stop", "sizing", "affordability"],
    )
    async def test_rule_fired_is_absent_on_the_post_approve_refusals(
        self, caplog: pytest.LogCaptureFixture, build: Any
    ) -> None:
        """These four carry a decision whose `approved` is True and whose rule is
        None, which is why the schema branches on `approved` and never on rule
        presence. Absent, not null."""
        signal, assessment, pairs = build()

        record = await _emit_one(caplog, signal, assessment, pairs)

        assert assessment.decision is not None
        assert assessment.decision.approved
        assert "rule_fired" not in _fields(record)

    async def test_timeframe_is_absent_when_the_pair_is_unknown(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Signal carries no timeframe, so it is resolved through `pairs` -- and
        an unknown pair is precisely the case that has no entry there."""
        signal, assessment, pairs = _case_unknown_pair()

        record = await _emit_one(caplog, signal, assessment, pairs)

        assert "timeframe" not in _fields(record)
        assert _fields(record)["stage"] == "unknown_pair"

    async def test_an_approved_entry_carries_the_intent_field_set(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        manager, _ = build_manager()
        signal = buy("100.00")
        assessment = manager.evaluate(signal, portfolio=Portfolio(free_quote=D("10000")))
        assert assessment.approved

        record = await _emit_one(caplog, signal, assessment, default_pairs())

        fields = _fields(record)
        assert fields["event"] == "intent_dispatched"
        assert fields["side"] == "BUY"
        assert fields["order_type"] == "LIMIT"
        # NOT asserted equal to each other: `entry_limit` is a placeholder equal
        # to the reference until the commit that derives it, and a test that
        # pinned the equality would encode the placeholder as correct. That the
        # two are distinct FIELDS from distinct sources is pinned below, on an
        # intent built with them unequal.
        assert fields["entry"] == assessment.intent.entry_limit
        assert fields["reference"] == assessment.intent.reference_price
        # Priced off the derived limit 100.10, not the close: 2% and 4% of it.
        assert fields["stop"] == D("98.10")
        assert fields["take_profit"] == D("104.10")
        assert "stage" not in fields
        assert "rule_fired" not in fields

    async def test_the_entry_line_reports_the_limit_and_the_reference_separately(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Applied slippage must be visible in one record rather than inferred
        from two, so `entry` and `reference` are two fields from two sources.

        Built directly with them UNEQUAL, which the type permits -- the
        invariant is `entry_limit >= reference_price`, not equality. The manager
        cannot yet produce an unequal pair, so a test routed through it could
        not tell one field read twice from two fields read once.
        """
        levels = entry_levels(entry="100.10")
        intent = EntryIntent(
            symbol=SYMBOL,
            side=OrderSide.BUY,
            quantity=D("1"),
            reference_price=D("100.00"),
            entry_limit=D("100.10"),
            levels=levels,
        )
        assessment = RiskAssessment(
            symbol=SYMBOL, approved=True, reason="ok", stage=None, intent=intent
        )
        signal = Signal(symbol=SYMBOL, action=SignalAction.BUY, price=D("100.00"), timestamp=NOW)

        record = await _emit_one(caplog, signal, assessment, default_pairs())

        fields = _fields(record)
        assert fields["entry"] == D("100.10")
        assert fields["reference"] == D("100.00")
        assert fields["entry"] != fields["reference"]

    async def test_an_approved_exit_omits_the_protective_levels(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """An exit closes a position rather than opening one to protect, so its
        intent carries no levels -- absent fields, not null ones."""
        manager, _ = build_manager()
        portfolio = Portfolio(free_quote=D("0"), positions={SYMBOL: long_position(quantity="0.75")})
        signal = Signal(symbol=SYMBOL, action=SignalAction.CLOSE, price=D("123.45"), timestamp=NOW)
        assessment = manager.evaluate(signal, portfolio=portfolio)
        assert assessment.intent is not None
        assert assessment.intent.side is OrderSide.SELL

        record = await _emit_one(caplog, signal, assessment, default_pairs())

        fields = _fields(record)
        assert fields["side"] == "SELL"
        assert fields["quantity"] == D("0.75")
        assert fields["order_type"] == "MARKET"
        assert "stop" not in fields
        assert "take_profit" not in fields
        # A CLOSE dispatches MARKET, so "at what price" is unknown until it
        # fills and a field that would have to lie is omitted. Absent, not null.
        # Until this commit nothing asserted these -- the exit line carried
        # `entry` and no test would have failed if it stopped, or started.
        assert "entry" not in fields
        assert "reference" not in fields

    async def test_no_field_is_ever_null(self, caplog: pytest.LogCaptureFixture) -> None:
        """Absent, not null -- checked across every refusal path at once."""
        for _stage, build in _STAGE_CASES:
            caplog.clear()
            signal, assessment, pairs = build()
            record = await _emit_one(caplog, signal, assessment, pairs)
            assert None not in _fields(record).values()

    async def test_enums_cross_as_values_so_both_sinks_agree(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """A `str, Enum` member reaches JSON as its value but text as
        `str(member)`. Passing `.value` is what keeps `action=BUY` from becoming
        `action=SignalAction.BUY` in exactly one of the two sinks."""
        from trading_bot.utils.logger import JsonFormatter, PlainFormatter

        signal, assessment, pairs = _case_limit_refused()
        record = await _emit_one(caplog, signal, assessment, pairs)

        assert "action=BUY" in PlainFormatter("%(message)s").format(record)
        assert '"action": "BUY"' in JsonFormatter().format(record)
        assert "SignalAction" not in PlainFormatter("%(message)s").format(record)

    async def test_the_pid_reaches_both_sinks_with_the_same_value(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """D5, and it needs the two-sink shape for the reason the enum test does.

        `record.process` is a NATIVE LogRecord attribute, so `surplus_fields`
        filters it out and it cannot arrive through `extra=`. Each sink
        therefore needs its own line -- `%(process)d` in the plain format, an
        explicit `"pid"` key in the JSON payload -- and two independent lines
        are exactly what can disagree. Catches either one being removed, and
        catches them rendering different values.
        """
        import os

        from trading_bot.utils.logger import _PLAIN_FORMAT, JsonFormatter, PlainFormatter

        signal, assessment, pairs = _case_limit_refused()
        record = await _emit_one(caplog, signal, assessment, pairs)

        plain = PlainFormatter(_PLAIN_FORMAT).format(record)
        rendered = JsonFormatter().format(record)

        assert f"pid={os.getpid()}" in plain
        assert f'"pid": {os.getpid()}' in rendered

    async def test_decimals_render_identically_and_exactly_in_both_sinks(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        from trading_bot.utils.logger import JsonFormatter, PlainFormatter

        manager, _ = build_manager()
        signal = buy("100.00")
        assessment = manager.evaluate(signal, portfolio=Portfolio(free_quote=D("10000")))
        record = await _emit_one(caplog, signal, assessment, default_pairs())

        # 100.10, not 100.00: `entry` is the derived limit. The close is on the
        # same record as `reference`, and both render exactly in both sinks.
        assert "entry=100.10" in PlainFormatter("%(message)s").format(record)
        assert '"entry": "100.10"' in JsonFormatter().format(record)
        assert "reference=100.00" in PlainFormatter("%(message)s").format(record)

    async def test_no_log_field_collides_with_a_reserved_record_attribute(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """`Logger.makeRecord` raises at the call site on a reserved name, so a
        collision would surface as a KeyError from inside the handler."""
        emitted: set[str] = set()
        for _stage, build in _STAGE_CASES:
            caplog.clear()
            signal, assessment, pairs = build()
            emitted |= set(_fields(await _emit_one(caplog, signal, assessment, pairs)))

        reserved = frozenset(logging.LogRecord("", 0, "", 0, "", (), None).__dict__) | {
            "message",
            "asctime",
        }
        assert emitted & reserved == set()


# --------------------------------------------------------------------------
# The chained handler
# --------------------------------------------------------------------------
def build_handler(
    *,
    risk: RiskManager | None = None,
    intent_logger: IntentLogger | None = None,
    portfolio: Portfolio | None = None,
    pairs: Mapping[str, PairContext] | None = None,
    executor: Any = None,
) -> Any:
    resolved_pairs = pairs if pairs is not None else default_pairs()
    manager, _ = build_manager(pairs=resolved_pairs)
    return _build_signal_handler(
        risk=risk if risk is not None else manager,
        intent_logger=intent_logger
        if intent_logger is not None
        else IntentLogger(pairs=resolved_pairs),
        portfolio=portfolio if portfolio is not None else Portfolio(free_quote=D("10000")),
        pairs=resolved_pairs,
        executor=executor,
    )


class TestChainedHandler:
    async def test_an_approved_signal_reaches_the_intent_logger(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        handler = build_handler()
        with caplog.at_level(logging.DEBUG, logger=_MODES_LOGGER):
            await handler(buy("100.00"), candle())

        assert len(_records(caplog, "intent_dispatched")) == 1

    async def test_a_raising_risk_manager_is_named_and_contained(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        pairs = default_pairs()
        boom, _ = build_manager(pairs=pairs)
        handler = build_handler(
            risk=BoomRiskManager(
                config=risk_config(),
                provider=FakeProvider(frames={SYMBOL: ohlcv(50)}, candles={SYMBOL: candle()}),
                pairs=pairs,
            ),
            pairs=pairs,
        )
        assert boom is not None

        with caplog.at_level(logging.DEBUG, logger=_MODES_LOGGER):
            await handler(buy(), candle())  # must not raise

        failures = _records(caplog, "collaborator_failed")
        assert len(failures) == 1
        assert _fields(failures[0])["collaborator"] == "risk_manager"
        assert _fields(failures[0])["error_type"] == "RuntimeError"
        # The chain stopped: nothing downstream ran.
        assert _records(caplog, "intent_dispatched") == []

    async def test_a_raising_intent_logger_is_named_and_contained(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        pairs = default_pairs()
        handler = build_handler(intent_logger=BoomIntentLogger(pairs=pairs), pairs=pairs)

        with caplog.at_level(logging.DEBUG, logger=_MODES_LOGGER):
            await handler(buy("100.00"), candle())  # must not raise

        failures = _records(caplog, "collaborator_failed")
        assert len(failures) == 1
        assert _fields(failures[0])["collaborator"] == "intent_logger"

    async def test_the_engines_own_catch_never_fires(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """The load-bearing assertion. `_emit` catches with a bare
        `except Exception` and no structured fields, and the engine's failure
        counter is fed only from `_evaluate` -- so anything escaping this handler
        would be an unstructured traceback every bar, forever, with no
        quarantine. Driven through the real engine so the catch is the real one.
        """
        pairs = default_pairs()
        provider = FakeMarketDataProvider({_KEY: 100})
        strategy = ScriptedStrategy(result=buy("100.00"))
        engine = TradingEngine(provider, {_KEY: strategy})
        engine.on_signal(build_handler(intent_logger=BoomIntentLogger(pairs=pairs), pairs=pairs))
        await engine.start()

        with caplog.at_level(logging.DEBUG):
            await provider.emit(engine_candle())

        assert "Signal handler failed" not in caplog.text
        assert len(_records(caplog, "collaborator_failed")) == 1


# --------------------------------------------------------------------------
# Boot: the fail-fast refusals
# --------------------------------------------------------------------------
class TestBootRefusals:
    async def test_a_non_live_mode_is_refused_as_missing_not_forbidden(
        self, tmp_path: Path
    ) -> None:
        settings = write_settings(tmp_path, mode="paper")
        client = FakeRootClient()

        with pytest.raises(ConfigError, match="No composition root exists for mode 'paper'"):
            async with live_system(settings, client=client, stream=FakeStream()):
                pass  # pragma: no cover - the refusal precedes the body

        # Refused before anything was built, so there is nothing to close.
        assert client.close_calls == 0

    def test_a_duplicate_symbol_refuses_and_names_both_timeframes(self, tmp_path: Path) -> None:
        settings = write_settings(tmp_path, pairs=((SYMBOL, "1m", True), (SYMBOL, "5m", True)))

        with pytest.raises(ConfigError) as exc_info:
            _pair_timeframes(settings)

        message = str(exc_info.value)
        assert SYMBOL in message
        assert "1m" in message
        assert "5m" in message

    async def test_a_duplicate_symbol_refuses_the_boot(self, tmp_path: Path) -> None:
        settings = write_settings(tmp_path, pairs=((SYMBOL, "1m", True), (SYMBOL, "5m", True)))
        client = FakeRootClient()

        with pytest.raises(ConfigError, match="two timeframes"):
            async with live_system(settings, client=client, stream=FakeStream()):
                pass  # pragma: no cover - the refusal precedes the body

        # Pure check, so it costs no round trip -- and the client still closes.
        assert client.symbol_info_calls == []
        assert client.close_calls == 1

    def test_a_disabled_duplicate_does_not_refuse(self, tmp_path: Path) -> None:
        """`enabled_pairs` filters first, so a disabled second entry is not a clash."""
        settings = write_settings(tmp_path, pairs=((SYMBOL, "1m", True), (SYMBOL, "5m", False)))
        assert _pair_timeframes(settings) == {SYMBOL: "1m"}

    def test_no_pairs_at_all_refuses_and_says_the_list_is_empty(self, tmp_path: Path) -> None:
        """`TradingEngine.start` already rejects this, but with a bare ValueError
        -- not a TradingBotError -- several steps later, with a REST client and a
        WebSocket already open. Refusing here is the same answer, earlier, in a
        vocabulary that names config.yaml."""
        settings = write_settings(tmp_path, pairs=())

        with pytest.raises(ConfigError) as exc_info:
            _pair_timeframes(settings)

        message = str(exc_info.value)
        assert "trading.pairs is empty" in message
        assert "config.yaml" in message

    def test_all_pairs_disabled_refuses_and_says_so_distinctly(self, tmp_path: Path) -> None:
        """The two empty cases need opposite fixes, so they must not share a
        message. This is the one an operator hits after toggling a pair off to
        debug something and forgetting to toggle it back."""
        settings = write_settings(tmp_path, pairs=((SYMBOL, "1m", False), ("ETHUSDT", "5m", False)))

        with pytest.raises(ConfigError) as exc_info:
            _pair_timeframes(settings)

        message = str(exc_info.value)
        assert "all 2 configured pair(s) have enabled: false" in message
        assert "trading.pairs is empty" not in message

    def test_one_enabled_pair_is_enough(self, tmp_path: Path) -> None:
        settings = write_settings(tmp_path, pairs=((SYMBOL, "1m", True), ("ETHUSDT", "5m", False)))
        assert _pair_timeframes(settings) == {SYMBOL: "1m"}

    @pytest.mark.parametrize(
        ("pairs", "expected"),
        [
            ((), "trading.pairs is empty"),
            (((SYMBOL, "1m", False),), "have enabled: false"),
        ],
        ids=["empty", "all-disabled"],
    )
    async def test_an_empty_pair_set_refuses_the_boot(
        self, tmp_path: Path, pairs: Any, expected: str
    ) -> None:
        settings = write_settings(tmp_path, pairs=pairs)
        client = FakeRootClient()

        with pytest.raises(ConfigError, match=expected):
            async with live_system(settings, client=client, stream=FakeStream()):
                pass  # pragma: no cover - the refusal precedes the body

        # Pure check: refused before any round trip, and the client still closes.
        assert client.symbol_info_calls == []
        assert client.close_calls == 1

    async def test_an_unprimeable_symbol_refuses_the_boot(self, tmp_path: Path) -> None:
        settings = write_settings(tmp_path, pairs=(("DOGEUSDT", "1m", True),))
        client = FakeRootClient(unknown_symbols=frozenset({"DOGEUSDT"}))

        with pytest.raises(ExchangeAPIError, match="DOGEUSDT"):
            async with live_system(settings, client=client, stream=FakeStream()):
                pass  # pragma: no cover - the refusal precedes the body

        assert client.close_calls == 1

    async def test_a_missing_quote_asset_refuses_the_boot(self, tmp_path: Path) -> None:
        settings = write_settings(tmp_path, base_currency="BUSD")
        client = FakeRootClient(balances=[Balance(asset="USDT", free=D("5000"), locked=D("0"))])

        with pytest.raises(ConfigError, match="BUSD"):
            async with live_system(settings, client=client, stream=FakeStream()):
                pass  # pragma: no cover - the refusal precedes the body

        assert client.close_calls == 1

    async def test_a_zero_balance_is_a_valid_state_and_boots(self, tmp_path: Path) -> None:
        """get_balances returns every asset including zeros, so absent means
        absent -- and zero is a state the account can legitimately be in."""
        settings = write_settings(tmp_path)
        client = FakeRootClient(balances=[Balance(asset="USDT", free=D("0"), locked=D("0"))])

        async with live_system(settings, client=client, stream=FakeStream()) as system:
            assert system.portfolio.free_quote == D("0")


class TestQuoteAssetMatching:
    """`_seed_portfolio` takes a snapshot rather than reading one, so these need
    no client at all -- the boot reads balances once and hands the sequence to
    both consumers."""

    def test_matching_is_case_insensitive_on_both_sides(self) -> None:
        """`trading.base_currency` carries no validator of its own, so this code
        has to be correct standing alone. The Commit-2 validator is defence in
        depth, not a substitute."""
        balances = [Balance(asset="usdt", free=D("12"), locked=D("0"))]

        portfolio = _seed_portfolio(balances, quote_asset="uSdT")

        assert portfolio.free_quote == D("12")

    def test_the_normalised_form_is_what_lands_on_the_portfolio(self) -> None:
        """It is interpolated into refusal messages and future code will compare it."""
        balances = [Balance(asset="usdt", free=D("1"), locked=D("0"))]

        portfolio = _seed_portfolio(balances, quote_asset="usdt")

        assert portfolio.quote_asset == "USDT"

    async def test_a_lowercase_base_currency_in_config_still_boots(self, tmp_path: Path) -> None:
        settings = write_settings(tmp_path, base_currency="usdt")
        client = FakeRootClient()

        async with live_system(settings, client=client, stream=FakeStream()) as system:
            assert system.portfolio.quote_asset == "USDT"
            assert system.portfolio.free_quote == D("5000")


class TestTheBootReadsBalancesOnce:
    """One account read, shared by the seeded portfolio and the holdings
    snapshot. The saved round trip is the smaller half: two reads could disagree
    if a balance moved between them, and the two consumers would then describe
    different accounts."""

    async def test_the_boot_reads_balances_exactly_once(self, tmp_path: Path) -> None:
        """Arity. `FakeRootClient` journals every call, so a second read is
        visible as a second entry rather than inferred from a counter."""
        settings = write_settings(tmp_path)
        journal: list[str] = []
        client = FakeRootClient(
            balances=[
                Balance(asset="USDT", free=D("5000"), locked=D("0")),
                Balance(asset="BTC", free=D("0.5"), locked=D("0")),
            ],
            journal=journal,
        )

        async with live_system(settings, client=client, stream=FakeStream()) as system:
            # Both consumers ran: the portfolio is seeded AND the holding was
            # snapshotted, so the single read fed both rather than one of them.
            assert system.portfolio.free_quote == D("5000")
            assert system.portfolio.unmanaged_holdings == {SYMBOL: D("0.5")}

        assert journal.count("balances") == 1

    async def test_both_consumers_receive_the_same_snapshot_object(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """IDENTITY, not arity, and the two are different claims.

        One `get_balances` call can still hand the consumers different objects
        -- a defensive copy at either call site would do it -- and two objects
        are free to diverge later even though they agree now. Counting calls
        cannot see that; `is` can.

        The fixture can express it: `FakeRootClient.get_balances` returns
        `list(self._balances)`, a NEW list per call, so under a second read the
        two consumers would genuinely hold different objects and this assertion
        would fail rather than coincidentally hold.
        """
        from trading_bot.engine import modes

        seen: list[Sequence[Balance]] = []
        real_seed = modes._seed_portfolio
        real_snapshot = modes._snapshot_unmanaged_holdings

        # The signature is MIRRORED here, so it is a second place it lives.
        # `ledger` is forwarded rather than dropped: swallowing it would make
        # this wrapper silently disable the restore for every test that
        # monkeypatches through it.
        def recording_seed(
            balances: Sequence[Balance], *, quote_asset: str, ledger: Ledger | None = None
        ) -> Portfolio:
            seen.append(balances)
            return real_seed(balances, quote_asset=quote_asset, ledger=ledger)

        async def recording_snapshot(
            client: ExchangeClient,
            *,
            balances: Sequence[Balance],
            pairs: Mapping[str, PairContext],
            portfolio: Portfolio,
        ) -> None:
            seen.append(balances)
            await real_snapshot(client, balances=balances, pairs=pairs, portfolio=portfolio)

        monkeypatch.setattr(modes, "_seed_portfolio", recording_seed)
        monkeypatch.setattr(modes, "_snapshot_unmanaged_holdings", recording_snapshot)

        settings = write_settings(tmp_path)
        client = FakeRootClient(
            balances=[
                Balance(asset="USDT", free=D("5000"), locked=D("0")),
                Balance(asset="BTC", free=D("0.5"), locked=D("0")),
            ]
        )

        async with live_system(settings, client=client, stream=FakeStream()):
            pass

        assert len(seen) == 2
        assert seen[0] is seen[1]


class TestUnmanagedHoldings:
    """The boot snapshot. Counted toward equity, never adopted as positions."""

    async def test_a_material_base_holding_is_recorded_but_never_a_position(
        self, tmp_path: Path
    ) -> None:
        """Adopting would manufacture the stopless state at every boot and would
        eventually have the bot sell an asset a human bought. Ignoring it would
        let a BUY pass ALREADY_IN_POSITION and pyramid onto it."""
        settings = write_settings(tmp_path)
        client = FakeRootClient(
            balances=[
                Balance(asset="USDT", free=D("5000"), locked=D("0")),
                Balance(asset="BTC", free=D("0.5"), locked=D("0")),
            ]
        )

        async with live_system(settings, client=client, stream=FakeStream()) as system:
            assert system.portfolio.unmanaged_holdings == {SYMBOL: D("0.5")}
            assert system.portfolio.positions == {}  # never adopted
            assert not system.portfolio.has_position(SYMBOL)
            assert system.portfolio.has_unmanaged_holding(SYMBOL)

    async def test_the_recorded_quantity_is_total_because_equity_asks_what_is_owned(
        self, tmp_path: Path
    ) -> None:
        """Locked base is owned. Excluding it understates the denominator every
        sizing decision divides by."""
        settings = write_settings(tmp_path)
        client = FakeRootClient(
            balances=[
                Balance(asset="USDT", free=D("5000"), locked=D("0")),
                Balance(asset="BTC", free=D("0.4"), locked=D("0.1")),
            ]
        )

        async with live_system(settings, client=client, stream=FakeStream()) as system:
            assert system.portfolio.unmanaged_holdings == {SYMBOL: D("0.5")}

    async def test_materiality_uses_free_because_dust_means_unsellable(
        self, tmp_path: Path
    ) -> None:
        """The two thresholds do NOT agree, and the asymmetry is deliberate.
        Equity asks what is owned (`total`); materiality asks whether this is
        dust, and dust is defined by sellability -- locked base cannot be sold,
        so it cannot help clear the threshold. Here free x 100 = 1 is below the
        symbol's min_notional of 10, so the holding does not block the pair even
        though its total value is 100.
        """
        settings = write_settings(tmp_path)
        client = FakeRootClient(
            balances=[
                Balance(asset="USDT", free=D("5000"), locked=D("0")),
                Balance(asset="BTC", free=D("0.01"), locked=D("0.99")),
            ]
        )

        async with live_system(settings, client=client, stream=FakeStream()) as system:
            assert system.portfolio.unmanaged_holdings == {}

    async def test_dust_below_min_notional_does_not_block_the_pair(self, tmp_path: Path) -> None:
        """A holding too small to sell must not refuse a symbol forever."""
        settings = write_settings(tmp_path)
        client = FakeRootClient(
            balances=[
                Balance(asset="USDT", free=D("5000"), locked=D("0")),
                Balance(asset="BTC", free=D("0.000001"), locked=D("0")),
            ]
        )

        async with live_system(settings, client=client, stream=FakeStream()) as system:
            assert system.portfolio.unmanaged_holdings == {}

    # ----------------------------------------------------------------------
    # The boot-time live-order-list scan (B2) and the nothing-tradeable exit (V2)
    # ----------------------------------------------------------------------
    async def test_a_live_list_of_ours_blocks_only_its_own_symbol(self, tmp_path: Path) -> None:
        """B2 refuses ONE symbol. Catches B1 -- a whole-boot refusal -- creeping in.

        Two pairs enabled, one carrying a live list of ours: the boot completes
        and the other pair stays tradeable. A B1 implementation would raise here.
        """
        settings = write_settings(
            tmp_path, pairs=((SYMBOL, TIMEFRAME, True), ("ETHUSDT", TIMEFRAME, True))
        )
        client = FakeRootClient(order_lists=[_live_list_for(SYMBOL)])

        async with live_system(settings, client=client, stream=FakeStream()) as system:
            assert set(system.portfolio.blocked_symbols) == {SYMBOL}
            assert not system.portfolio.is_blocked("ETHUSDT")
            assert client.order_list_calls == 1  # one call, account-wide

    async def test_a_terminal_list_does_not_block(self, tmp_path: Path) -> None:
        """Catches the liveness test inverted -- the whole mechanism firing on
        the fourteen finished lists this account already carries."""
        settings = write_settings(tmp_path)
        client = FakeRootClient(order_lists=[_live_list_for(SYMBOL, status="ALL_DONE")])

        async with live_system(settings, client=client, stream=FakeStream()) as system:
            assert system.portfolio.blocked_symbols == {}

    async def test_an_unrecognised_list_status_blocks(self, tmp_path: Path) -> None:
        """R-LV: the TERMINAL test is a blacklist, so an unknown status blocks.

        Catches a reviewer or author reaching for `resolution._is_live`, whose
        whitelist defaults the other way -- correctly, for its own caller.

        TWO pairs, so V2 does not fire and swallow the property under test. A
        one-pair fixture asserts B2 and V2 at once and cannot tell them apart --
        which it did, on the first run of this test.
        """
        settings = write_settings(
            tmp_path, pairs=((SYMBOL, TIMEFRAME, True), ("ETHUSDT", TIMEFRAME, True))
        )
        client = FakeRootClient(order_lists=[_live_list_for(SYMBOL, status="SOME_NEW_STATE")])

        async with live_system(settings, client=client, stream=FakeStream()) as system:
            assert system.portfolio.is_blocked(SYMBOL)
            assert not system.portfolio.is_blocked("ETHUSDT")

    async def test_a_failed_enumeration_blocks_every_enabled_symbol(self, tmp_path: Path) -> None:
        """R-FC, and the highest-value mutation here: catches FAIL-OPEN.

        The call is account-wide, so its failure carries no symbol-specific
        information. Blocking one symbol -- or none -- would assert knowledge
        about the others that the boot does not have.
        """
        settings = write_settings(
            tmp_path, pairs=((SYMBOL, TIMEFRAME, True), ("ETHUSDT", TIMEFRAME, True))
        )
        client = FakeRootClient(order_lists_error=ExchangeAPIError("venue unreachable"))

        with pytest.raises(ConfigError, match="every enabled pair is blocked"):
            async with live_system(settings, client=client, stream=FakeStream()):
                pass  # pragma: no cover - the boot refuses before the body runs

    async def test_a_foreign_list_id_does_not_block(self, tmp_path: Path) -> None:
        """Catches prefix matching. `tb1-garbage` is ours-looking and is not ours;
        the library's own tag is not either. Refusing a symbol on somebody else's
        string is the failure the parse-don't-prefix rule exists to prevent."""
        settings = write_settings(tmp_path)
        client = FakeRootClient(
            order_lists=[
                _live_list_for(SYMBOL, client_id="x-HNA2TXFJ7f3a91"),
                _live_list_for(SYMBOL, client_id="tb1-garbage"),
                _live_list_for(SYMBOL, client_id=None),
            ]
        )

        async with live_system(settings, client=client, stream=FakeStream()) as system:
            assert system.portfolio.blocked_symbols == {}

    async def test_a_live_list_on_an_unconfigured_symbol_warns_and_blocks_nothing(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        """R-NE. `evaluate` already refuses an unconfigured symbol at
        UNKNOWN_PAIR, so a block would be a second mechanism for a refusal that
        already happens -- but the operator still needs telling."""
        settings = write_settings(tmp_path)
        client = FakeRootClient(order_lists=[_live_list_for("DOGEUSDT")])

        with caplog.at_level(logging.WARNING):
            async with live_system(settings, client=client, stream=FakeStream()) as system:
                assert system.portfolio.blocked_symbols == {}

        records = [r for r in caplog.records if r.name == "trading_bot.engine.modes"]
        assert any(getattr(r, "symbol", None) == "DOGEUSDT" for r in records)

    async def test_a_blocked_symbol_is_not_priced_and_not_counted_in_equity(self) -> None:
        """M2, and it catches M1 creeping back.

        `unmanaged_holdings` is summed by `equity` and enumerated by
        `marked_symbols`, and a symbol it cannot price refuses PORTFOLIO-WIDE
        under NO_MARK_PRICE. A block must not buy that coupling.
        """
        portfolio = Portfolio(
            free_quote=D("1000"),
            blocked_symbols={SYMBOL: "venue list 255471 is still working"},
        )

        assert portfolio.is_blocked(SYMBOL)
        assert portfolio.marked_symbols() == []
        assert portfolio.equity({}) == D("1000")

    async def test_the_boot_survives_when_one_pair_of_two_is_blocked(self, tmp_path: Path) -> None:
        """V2 is a FLOOR, not a policy: it fires only when nothing is left."""
        settings = write_settings(
            tmp_path, pairs=((SYMBOL, TIMEFRAME, True), ("ETHUSDT", TIMEFRAME, True))
        )
        client = FakeRootClient(order_lists=[_live_list_for(SYMBOL)])

        async with live_system(settings, client=client, stream=FakeStream()) as system:
            assert system.portfolio.is_blocked(SYMBOL)

    async def test_the_boot_exits_when_every_enabled_pair_is_blocked(self, tmp_path: Path) -> None:
        """V2. A bot with nothing tradeable would otherwise connect, seed, and
        refuse every signal silently -- `M5_NUMBERS.md`'s "looks healthy while
        never trading". The message names each blocked symbol and its reason."""
        settings = write_settings(tmp_path)
        client = FakeRootClient(order_lists=[_live_list_for(SYMBOL)])

        with pytest.raises(ConfigError, match="nothing this bot can trade") as excinfo:
            async with live_system(settings, client=client, stream=FakeStream()):
                pass  # pragma: no cover - the boot refuses before the body runs

        assert SYMBOL in str(excinfo.value)
        assert "255471" in str(excinfo.value)

    # ----------------------------------------------------------------------
    # The single-instance lock's wiring (D1). The lock itself is pinned in
    # tests/unit/test_instance_lock.py; these two pin where it sits.
    # ----------------------------------------------------------------------
    async def test_an_injected_client_does_not_take_the_lock(self, tmp_path: Path) -> None:
        """L1. Catches unconditional acquisition.

        An injected client authenticates nothing, so there is no venue access to
        serialise -- and acquiring anyway would make every test in this file
        contend for one lock file, serialising a suite over a resource that
        exists to serialise PROCESSES. That this test's own neighbours all pass
        is the other half of the evidence.
        """
        settings = write_settings(tmp_path)

        async with live_system(settings, client=FakeRootClient(), stream=FakeStream()):
            # Nothing holds it, so a bystander can take it.
            with acquire_instance_lock(tmp_path / ".bot.lock"):
                pass

    async def test_the_lock_is_taken_before_the_client_is_built(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """R-ORDER, and R-C beneath it: a refused instance must never authenticate.

        Catches the acquisition moved after client construction -- which reads
        as harmless and is not: a second process would sign in, prime symbols
        and read balances before being told to stop.

        `client=None` is what makes this reachable at all, since L1 gates
        acquisition on exactly that.
        """
        order: list[str] = []
        settings = write_settings(tmp_path)
        lock_path = tmp_path / ".bot.lock"

        from trading_bot.engine import modes as modes_module

        real_acquire = modes_module.acquire_instance_lock

        @contextmanager
        def recording_acquire(path: Path = lock_path) -> Iterator[None]:
            order.append("lock")
            with real_acquire(lock_path):
                yield

        class RecordingBinanceClient:
            @staticmethod
            async def create(_settings: Any) -> FakeRootClient:
                order.append("client")
                return FakeRootClient()

        monkeypatch.setattr(modes_module, "acquire_instance_lock", recording_acquire)
        monkeypatch.setattr(
            "trading_bot.exchange.binance_client.BinanceClient", RecordingBinanceClient
        )

        async with live_system(settings, stream=FakeStream()):
            pass

        assert order == ["lock", "client"]

    async def test_the_quote_asset_is_never_counted_as_an_unmanaged_holding(
        self, tmp_path: Path
    ) -> None:
        """It is already `free_quote`; counting it here would double it into equity."""
        settings = write_settings(tmp_path)
        client = FakeRootClient(balances=[Balance(asset="USDT", free=D("5000"), locked=D("0"))])

        async with live_system(settings, client=client, stream=FakeStream()) as system:
            assert system.portfolio.unmanaged_holdings == {}
            assert system.portfolio.free_quote == D("5000")

    async def test_an_unpriceable_asset_is_ignored_with_a_warning_not_a_refusal(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Refusing the boot over an asset the bot does not trade is overreach.
        The resulting equity error is conservative -- understated -- and the
        warning is what stops it being invisible.

        **ROUTED, NOT WEAKENED (`M5g-080`).** This asserted the per-asset line
        at WARNING. Those lines are now DEBUG and one WARNING summary carries
        the fact, so the assertion follows the detail down a level rather than
        being dropped: it still demands the asset be NAMED, which is the half
        an operator can act on.
        """
        settings = write_settings(tmp_path)
        client = FakeRootClient(
            balances=[
                Balance(asset="USDT", free=D("5000"), locked=D("0")),
                Balance(asset="DOGE", free=D("1000"), locked=D("0")),  # no enabled pair
            ]
        )

        with caplog.at_level(logging.DEBUG, logger="trading_bot.engine.modes"):
            async with live_system(settings, client=client, stream=FakeStream()) as system:
                assert system.portfolio.unmanaged_holdings == {}

        messages = [r.getMessage() for r in caplog.records if r.name == "trading_bot.engine.modes"]
        assert any("DOGE" in m and "EXCLUDED FROM EQUITY" in m for m in messages)

    async def test_many_excluded_assets_produce_exactly_one_warning(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        """THE DEFECT (`M5g-080`). Catches the collapse being reverted.

        Run 2 put 501 of these into a 609-line log -- 82.3% of the run, and 501
        of its 503 WARNING lines -- so a B2 block line would have sat among them
        at an adjacent level. EXACT count, never `>=`: `M5g-097` is what an
        inequality costs, and over-counting is the direction this defect failed
        in.
        """
        settings = write_settings(tmp_path)
        client = FakeRootClient(
            balances=[
                Balance(asset="USDT", free=D("5000"), locked=D("0")),
                *(Balance(asset=f"COIN{n}", free=D("1000"), locked=D("0")) for n in range(25)),
            ]
        )

        with caplog.at_level(logging.WARNING, logger="trading_bot.engine.modes"):
            async with live_system(settings, client=client, stream=FakeStream()):
                pass

        # **The assertion is on EVERY warning this logger emitted, not on the
        # summaries.** Filtering by event name first would count one summary
        # whether or not 25 per-asset lines came back beside it -- the flood is
        # exactly what must fail here, so the total is what is asserted.
        warned = [
            r
            for r in caplog.records
            if r.name == "trading_bot.engine.modes" and r.levelno == logging.WARNING
        ]
        assert len(warned) == 1
        assert getattr(warned[0], "event", None) == "boot_assets_excluded"
        assert warned[0].excluded_count == 25  # type: ignore[attr-defined]
        assert "25 asset(s) are EXCLUDED FROM EQUITY" in warned[0].getMessage()

    async def test_no_excluded_assets_produce_no_summary_at_all(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Catches a summary that reports zero.

        Silence is the pass, matching the B2 scan beside it. A line saying
        "0 asset(s) excluded" would fire on every healthy boot forever, which is
        the banner this collapse exists to remove rather than relocate.
        """
        settings = write_settings(tmp_path)
        client = FakeRootClient(balances=[Balance(asset="USDT", free=D("5000"), locked=D("0"))])

        with caplog.at_level(logging.DEBUG, logger="trading_bot.engine.modes"):
            async with live_system(settings, client=client, stream=FakeStream()):
                pass

        assert [
            r for r in caplog.records if getattr(r, "event", None) == "boot_assets_excluded"
        ] == []

    async def test_the_per_asset_detail_is_complete_at_debug(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Catches the detail being sampled into the summary, or dropped.

        An operator debugging equity needs every excluded asset, not an
        arbitrary five of five hundred -- a sample reads as the whole set. The
        full list survives at DEBUG; the summary carries no names at all.
        """
        settings = write_settings(tmp_path)
        client = FakeRootClient(
            balances=[
                Balance(asset="USDT", free=D("5000"), locked=D("0")),
                Balance(asset="DOGE", free=D("1000"), locked=D("0")),
                Balance(asset="SHIB", free=D("2000"), locked=D("0")),
            ]
        )

        with caplog.at_level(logging.DEBUG, logger="trading_bot.engine.modes"):
            async with live_system(settings, client=client, stream=FakeStream()):
                pass

        debug = [
            r.getMessage()
            for r in caplog.records
            if r.name == "trading_bot.engine.modes" and r.levelno == logging.DEBUG
        ]
        assert any("DOGE" in m and "EXCLUDED FROM EQUITY" in m for m in debug)
        assert any("SHIB" in m and "EXCLUDED FROM EQUITY" in m for m in debug)

    async def test_a_non_ascii_asset_name_cannot_break_the_summary(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Catches an asset name being interpolated back into the summary.

        Run 2's account really held assets named `这是测试币` and `币安人生`. The
        summary is unbreakable by them because it carries NO name -- only a
        count and the quote asset -- and this pins that property rather than
        trusting it. The DEBUG line does carry the name, and must survive it.
        """
        settings = write_settings(tmp_path)
        client = FakeRootClient(
            balances=[
                Balance(asset="USDT", free=D("5000"), locked=D("0")),
                Balance(asset="这是测试币", free=D("999"), locked=D("0")),
            ]
        )

        with caplog.at_level(logging.DEBUG, logger="trading_bot.engine.modes"):
            async with live_system(settings, client=client, stream=FakeStream()):
                pass

        summaries = [
            r for r in caplog.records if getattr(r, "event", None) == "boot_assets_excluded"
        ]
        assert len(summaries) == 1
        assert "这是测试币" not in summaries[0].getMessage()
        assert "1 asset(s) are EXCLUDED FROM EQUITY" in summaries[0].getMessage()

        debug = [
            r.getMessage()
            for r in caplog.records
            if r.name == "trading_bot.engine.modes" and r.levelno == logging.DEBUG
        ]
        assert any("这是测试币" in m for m in debug)

    async def test_the_escalation_is_a_boot_warning_never_critical(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        """An unmanaged holding is an ordinary state of a shared account and will
        be true on many boots. At CRITICAL it would train an operator to skim the
        level that carries the one condition nothing can resolve."""
        settings = write_settings(tmp_path)
        client = FakeRootClient(
            balances=[
                Balance(asset="USDT", free=D("5000"), locked=D("0")),
                Balance(asset="BTC", free=D("0.5"), locked=D("0")),
            ]
        )

        with caplog.at_level(logging.WARNING, logger="trading_bot.engine.modes"):
            async with live_system(settings, client=client, stream=FakeStream()):
                pass

        ours = [r for r in caplog.records if r.name == "trading_bot.engine.modes"]
        assert any(r.levelno == logging.WARNING and SYMBOL in r.getMessage() for r in ours)
        assert not any(r.levelno >= logging.CRITICAL for r in ours)

    async def test_the_snapshot_is_taken_before_any_socket(self, tmp_path: Path) -> None:
        """It joins the other four boot refusals ahead of anything going live.

        It has to be priced over REST for exactly this reason: the provider's
        buffers are empty until `start()`, and `start()` runs after this context
        manager has yielded -- so `last_candle` has nothing to give at boot.
        """
        settings = write_settings(tmp_path)
        journal: list[str] = []
        stream = FakeStream(journal=journal)
        client = FakeRootClient(
            balances=[
                Balance(asset="USDT", free=D("5000"), locked=D("0")),
                Balance(asset="BTC", free=D("0.5"), locked=D("0")),
            ],
            journal=journal,
        )

        async with live_system(settings, client=client, stream=stream) as system:
            assert system.portfolio.unmanaged_holdings == {SYMBOL: D("0.5")}
            assert journal.index("balances") < journal.index(f"ticker:{SYMBOL}")
            # Nothing has gone live: the snapshot is complete and the stream has
            # never been started.
            assert stream.start_calls == 0
            assert "stream_start" not in journal

    def test_a_close_on_an_unmanaged_symbol_finds_nothing_to_close(self) -> None:
        """ "The bot never sells it" is enforced by the EXISTING code path -- no
        Position is constructed, so `_exit_assessment` takes its NOTHING_TO_CLOSE
        branch. No new guard, which is the point."""
        manager, _ = build_manager()
        portfolio = Portfolio(free_quote=D("10000"), unmanaged_holdings={SYMBOL: D("0.5")})

        assessment = manager.evaluate(
            Signal(symbol=SYMBOL, action=SignalAction.CLOSE, price=D("100"), timestamp=NOW),
            portfolio=portfolio,
        )

        assert assessment.stage is RefusalStage.NOTHING_TO_CLOSE

    def test_an_unmanaged_holding_counts_toward_equity(self) -> None:
        """The denominator of every sizing decision and of the daily-loss cap."""
        portfolio = Portfolio(free_quote=D("1000"), unmanaged_holdings={SYMBOL: D("2")})
        assert portfolio.equity({SYMBOL: D("150")}) == D("1300")

    def test_equity_raises_when_an_unmanaged_holding_cannot_be_marked(self) -> None:
        portfolio = Portfolio(free_quote=D("1000"), unmanaged_holdings={SYMBOL: D("2")})
        with pytest.raises(ValueError, match="no mark price for unmanaged holding"):
            portfolio.equity({})


# --------------------------------------------------------------------------
# Boot: what gets assembled
# --------------------------------------------------------------------------
class TestBootAssembly:
    async def test_the_container_carries_every_collaborator(self, tmp_path: Path) -> None:
        settings = write_settings(tmp_path)

        async with live_system(settings, client=FakeRootClient(), stream=FakeStream()) as system:
            assert isinstance(system, LiveSystem)
            assert system.settings is settings
            assert isinstance(system.engine, TradingEngine)
            assert isinstance(system.risk, RiskManager)
            assert isinstance(system.intent_logger, IntentLogger)
            assert system.pairs.keys() == {SYMBOL}
            assert system.pairs[SYMBOL].timeframe == TIMEFRAME

    async def test_the_container_is_frozen(self, tmp_path: Path) -> None:
        settings = write_settings(tmp_path)

        async with live_system(settings, client=FakeRootClient(), stream=FakeStream()) as system:
            with pytest.raises(FrozenInstanceError):
                system.portfolio = Portfolio()  # type: ignore[misc]

    async def test_symbol_info_is_fetched_once_per_distinct_symbol(self, tmp_path: Path) -> None:
        """One round trip per symbol, not per pair: the cache is symbol-keyed."""
        settings = write_settings(tmp_path, pairs=((SYMBOL, "1m", True), ("ETHUSDT", "5m", True)))
        client = FakeRootClient()

        async with live_system(settings, client=client, stream=FakeStream()):
            pass

        assert client.symbol_info_calls == [SYMBOL, "ETHUSDT"]

    async def test_exactly_one_signal_handler_is_registered(self, tmp_path: Path) -> None:
        settings = write_settings(tmp_path)

        async with live_system(settings, client=FakeRootClient(), stream=FakeStream()) as system:
            handlers = system.engine._signal_handlers
            assert len(handlers) == 1

    async def test_the_wired_handler_produces_the_intent_stream(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        """End to end through the assembled root: a signal in, a schema line out."""
        settings = write_settings(tmp_path)

        async with live_system(settings, client=FakeRootClient(), stream=FakeStream()) as system:
            with caplog.at_level(logging.DEBUG, logger=_MODES_LOGGER):
                await system.engine._emit(buy("100.00"), candle())

        assert len(_records(caplog, "intent_dispatched")) == 1

    async def test_the_portfolio_is_a_boot_snapshot(self, tmp_path: Path) -> None:
        """Nothing mutates it in M4a; it is a photograph, not yet a ledger."""
        settings = write_settings(tmp_path)
        client = FakeRootClient(balances=[Balance(asset="USDT", free=D("777"), locked=D("3"))])

        async with live_system(settings, client=client, stream=FakeStream()) as system:
            before = system.portfolio.free_quote
            await system.engine._emit(buy("100.00"), candle())
            assert system.portfolio.free_quote == before == D("777")


class _ReadableRootClient(FakeRootClient):
    """A root client that also answers the reconciler's enumeration.

    ``FakeRootClient`` raises ``NotImplementedError`` for it, which is right for
    every test that must not reach the venue. The reconciler does reach it, so
    this narrows the fake exactly as far as the driver needs and no further.
    """

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.enumerations: list[str] = []

    async def get_own_open_orders(
        self, symbol: str, *, timeout_s: float | None = None, attempts: int | None = None
    ) -> list[Order]:
        self.enumerations.append(symbol)
        return []


def _unprotected_position(symbol: str) -> Position:
    """An open position with nothing requested: classifies ABSENT_BY_DESIGN.

    Chosen because that is the one verdict the pass STAMPS on a first read, so
    ``last_reconciled_at`` moves from ``None`` to a datetime and gives the
    behavioural test below an observable marker that no other collaborator
    writes.
    """
    return Position(
        symbol=symbol,
        side=PositionSide.LONG,
        quantity=D("0.001"),
        entry_price=D("47000"),
        entry_bar_time=NOW,
        protection=ProtectionState.UNKNOWN,
    )


class TestReconcileThenDecide:
    """The reconciler subscribes to candles, and it subscribes FIRST."""

    async def test_candle_subscribers_run_reconcile_then_resolve_then_decide(
        self, tmp_path: Path
    ) -> None:
        """Registration order, which is a consequence of WHERE each registration
        happens: this root subscribes before it yields, and `TradingEngine.start`
        subscribes only when `run()` is called afterwards. Nothing asserted that,
        and an inversion's symptom -- evaluation reading a bar-old ledger -- is
        silent.

        THREE subscribers now, and the middle one is what makes Option 4
        correct: the executor resolves an ambiguous write from the previous bar
        out of THIS bar's fresh budget, before the engine can dispatch anything
        new. Moving it after the engine's hook would resolve the ambiguity only
        after a second placement had already been decided on a portfolio that
        does not know about the first.
        """
        settings = write_settings(tmp_path)

        async with live_system(
            settings, client=_ReadableRootClient(), stream=FakeStream()
        ) as system:
            await system.engine.start()

            handlers = system.provider._handlers  # type: ignore[attr-defined]
            assert handlers[0] is system.reconciler
            assert handlers[1] is system.executor
            assert handlers[2].__self__ is system.engine  # type: ignore[attr-defined]

    async def test_a_later_subscriber_already_sees_the_reconciliation_from_the_same_candle(
        self, tmp_path: Path
    ) -> None:
        """THE PROPERTY THE OTHER TWO TESTS EXIST TO PROTECT, and neither pins it.

        Registration order and `_notify`'s iteration order can both hold while
        evaluation on bar N still reads bar N-1's ledger -- a driver that
        SCHEDULED its work instead of performing it inline would satisfy both
        and break this. So this observes the effect rather than the order: a spy
        registered immediately after the reconciler, with no intervening await
        for a scheduled task to sneak through, reads the marker the pass writes.

        The spy sits at index 2, after the reconciler and the executor,
        and the engine's hook at index 3, so a write
        visible to the spy was necessarily complete before the engine ran --
        `_notify` awaits its subscribers in turn.
        """
        settings = write_settings(tmp_path)
        stream = FakeStream()
        seen_by_spy: list[datetime | None] = []

        async with live_system(settings, client=_ReadableRootClient(), stream=stream) as system:
            position = _unprotected_position(SYMBOL)
            system.portfolio.positions[SYMBOL] = position

            async def spy(candle: Candle) -> None:
                seen_by_spy.append(position.last_reconciled_at)

            system.provider.on_candle(spy)
            await system.engine.start()

            assert position.last_reconciled_at is None
            await stream.handlers[(SYMBOL, TIMEFRAME)](engine_candle())

        assert len(seen_by_spy) == 1, "the spy did not run: the candle never reached _notify"
        assert seen_by_spy[0] is not None


# --------------------------------------------------------------------------
# Teardown and ownership
# --------------------------------------------------------------------------
class TestTeardown:
    async def test_the_client_is_closed_exactly_once_on_the_normal_path(
        self, tmp_path: Path
    ) -> None:
        settings = write_settings(tmp_path)
        client = FakeRootClient()

        async with live_system(settings, client=client, stream=FakeStream()):
            assert client.close_calls == 0

        assert client.close_calls == 1

    async def test_the_provider_does_not_close_an_injected_client(self, tmp_path: Path) -> None:
        """`owns_client = client is None`, so under injection the provider closes
        nothing -- which is exactly why the root has to."""
        settings = write_settings(tmp_path)
        client = FakeRootClient()

        async with live_system(settings, client=client, stream=FakeStream()) as system:
            await system.provider.stop()
            assert client.close_calls == 0

        assert client.close_calls == 1

    async def test_the_stream_stops_before_the_client_closes(self, tmp_path: Path) -> None:
        journal: list[str] = []
        settings = write_settings(tmp_path)
        client = FakeRootClient(journal=journal)
        stream = FakeStream(journal)

        async with live_system(settings, client=client, stream=stream) as system:
            await system.engine.start()
        assert journal.index("stream_stop") < journal.index("close_client")
        assert journal[-1] == "close_client"

    async def test_the_client_closes_when_the_body_raises(self, tmp_path: Path) -> None:
        settings = write_settings(tmp_path)
        client = FakeRootClient()

        with pytest.raises(RuntimeError, match="body exploded"):
            async with live_system(settings, client=client, stream=FakeStream()):
                raise RuntimeError("body exploded")

        assert client.close_calls == 1

    async def test_the_client_closes_when_engine_construction_raises(self, tmp_path: Path) -> None:
        """The window the nested `finally` exists for: the provider is built and
        its stream owns a second connection, but `engine` is never bound. A
        single `finally` naming `engine` would raise UnboundLocalError here and
        mask the real error."""
        settings = write_settings(tmp_path, strategy="no_such_strategy")
        client = FakeRootClient()
        stream = FakeStream()

        with pytest.raises(StrategyNotFoundError, match="no_such_strategy"):
            async with live_system(settings, client=client, stream=stream):
                pass  # pragma: no cover - construction fails first

        assert client.close_calls == 1
        assert stream.stop_calls == 1  # the provider was still torn down

    async def test_a_balances_failure_closes_the_client(self, tmp_path: Path) -> None:
        settings = write_settings(tmp_path)
        client = FakeRootClient(balances_error=ExchangeAPIError("account unavailable"))

        with pytest.raises(ExchangeAPIError, match="account unavailable"):
            async with live_system(settings, client=client, stream=FakeStream()):
                pass  # pragma: no cover - the refusal precedes the body

        assert client.close_calls == 1

    async def test_stopping_a_never_started_engine_does_not_raise(self, tmp_path: Path) -> None:
        """The root's inner `finally` runs whether or not `run()` was ever
        called, so `stop()` has to tolerate an engine that never started.

        **The assertion was `>= 1` and is now exact (`M5g-093`).** It drove this
        path all along and could see only half of it: `>= 1` catches a teardown
        that never happened and is blind to one that happened three times, which
        is precisely the direction the missing idempotence guards failed in. An
        expressive fixture whose assertion did not look.

        One is the whole count, and it is reached the long way: both
        `engine.stop()` calls return early -- the engine never started, so it
        started no provider and has nothing to release -- and the single
        `stream.stop()` comes from the root's own `provider.stop()`.
        """
        settings = write_settings(tmp_path)
        stream = FakeStream()

        async with live_system(settings, client=FakeRootClient(), stream=stream) as system:
            assert stream.start_calls == 0
            await system.engine.stop()  # explicit, before the finally does it again

        assert stream.stop_calls == 1


# --------------------------------------------------------------------------
# A refusal has to fail *cleanly*, all the way out to the process exit code
# --------------------------------------------------------------------------
class TestBootRefusalsReachTheCli:
    """A fail-fast that fails ugly is half-built.

    Every boot refusal now propagates out of an ``async with``, through
    ``asyncio.run``, to ``main``'s ``except TradingBotError``. What the operator
    must see is the message and a non-zero status -- not a traceback.
    """

    @pytest.mark.parametrize(
        "exc_type",
        [ConfigError, ExchangeAPIError, StrategyNotFoundError],
        ids=["config", "exchange", "strategy"],
    )
    def test_every_refusal_type_is_caught_by_the_cli_handler(self, exc_type: type) -> None:
        """All four refusal classes raise one of these, and `main` catches the
        common base -- so none of them can reach the user as a traceback."""
        assert issubclass(exc_type, TradingBotError)

    def test_the_cli_exits_non_zero_without_a_traceback(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Driven through the real ``main``: parser, settings, logging, dispatch.

        The paper-mode refusal is the one that needs no client at all, so this
        stays hermetic while exercising the identical except-clause every other
        refusal lands in.
        """
        from trading_bot.main import main

        path = tmp_path / "cli_config.yaml"
        path.write_text(
            "mode: paper\n"
            "strategy:\n  name: sma_crossover\n"
            "backtesting:\n  start_date: '2024-01-01'\n  end_date: '2024-02-01'\n"
            "logging:\n  console: false\n  file:\n    enabled: false\n",
            encoding="utf-8",
        )

        root = logging.getLogger()
        saved_handlers, saved_level = list(root.handlers), root.level
        try:
            code = main(["--config", str(path), "run"])
        finally:
            root.handlers[:] = saved_handlers
            root.setLevel(saved_level)

        assert code == 1
        assert "Traceback" not in capsys.readouterr().err


# --------------------------------------------------------------------------
# The store's reader
# --------------------------------------------------------------------------
#: The seven values a restored record carries, written once so the test that
#: saves them and the test that reads them back cannot drift apart. Every money
#: value keeps trailing zeros, so a `str` comparison catches a `Decimal` that
#: round-tripped through a `float` and came back numerically equal.
_STORED = store.PendingRecord(
    symbol=SYMBOL,
    entry_bar_time=_LIST_BAR,
    generation=0,
    quantity=D("0.02310000"),
    entry_limit=D("60123.45000000"),
    stop_loss=D("58000.00000000"),
    take_profit=D("63000.00000000"),
)

#: The same seven values in the executor's type. Written out rather than mapped
#: by a helper: a helper here would be the mapping under test, comparing it
#: against itself.
_EXPECTED = PendingPlacement(
    symbol=SYMBOL,
    entry_bar_time=_LIST_BAR,
    generation=0,
    quantity=D("0.02310000"),
    entry_limit=D("60123.45000000"),
    stop_loss=D("58000.00000000"),
    take_profit=D("63000.00000000"),
)


class TestTheStoreIsReadAtBoot:
    """Piece 1 gains a reader: the root restores what a dead process could not resolve.

    The previous commit made the executor WRITE its pending set through a
    callable the root injects, and nothing read it -- a write path with no
    reader, deliberately. These pin the other half.

    **Every test here writes through the store's own ``save``**, at its own
    default path, which under the module's ``chdir`` fixture lands inside
    ``tmp_path``. Hand-writing JSON would pin this file's idea of the format
    rather than the format, and the round trip is the thing being tested.
    """

    async def test_a_ledger_dated_today_reaches_realised_today_through_the_root(
        self, tmp_path: Path
    ) -> None:
        """The restore's whole point: a same-day restart no longer forgets.

        MUTATION: drop the `ledger=` argument from the `_seed_portfolio` call,
        which is the state every run before this commit was in. `realised_today`
        then reads `Decimal(0)` and the daily-loss limit's realised term is back
        to being structurally dead.

        Driven through `live_system` rather than `_restore_ledger` alone,
        because the mapping being correct and the mapping being CALLED are
        different claims and only the second was ever missing.
        """
        settings = write_settings(tmp_path)
        today = datetime.now(timezone.utc)
        stored = store.LedgerRecord(realised_pnl=D("-35.38691640"), pnl_date=today.date())
        store.save(store.PersistedState(ledger=stored))

        async with live_system(settings, client=FakeRootClient(), stream=FakeStream()) as system:
            assert system.portfolio.ledger == Ledger(
                realised_pnl=D("-35.38691640"), pnl_date=today.date()
            )
            assert system.portfolio.realised_today(today) == D("-35.38691640")
            # Exactness, not equality: a value that lost its scale through a
            # float hop would still compare equal.
            assert str(system.portfolio.realised_today(today)) == "-35.38691640"

    async def test_a_ledger_dated_yesterday_reads_zero_but_is_still_held(
        self, tmp_path: Path
    ) -> None:
        """Restore is UNCONDITIONAL; staleness is a read-side derivation.

        MUTATION: filter by date in `_restore_ledger` -- return `None` for a
        ledger not dated today. `realised_today` would still read zero, so a
        test asserting only the read would PASS. The `ledger ==` assertion is
        the one that bites, and both are here for exactly that reason.

        Why it matters that the record survives: a boot-time filter cannot tell
        "yesterday, correctly zero today" from "today, wrongly discarded" when
        the clock or the file is off by a boundary, and the discarded figure has
        no other record.
        """
        settings = write_settings(tmp_path)
        now = datetime.now(timezone.utc)
        yesterday = (now - timedelta(days=1)).date()
        stored = store.LedgerRecord(realised_pnl=D("-99.5"), pnl_date=yesterday)
        store.save(store.PersistedState(ledger=stored))

        async with live_system(settings, client=FakeRootClient(), stream=FakeStream()) as system:
            # HELD, not discarded.
            assert system.portfolio.ledger == Ledger(realised_pnl=D("-99.5"), pnl_date=yesterday)
            # And READ as zero, because the day has rolled.
            assert system.portfolio.realised_today(now) == D("0")

    async def test_a_missing_store_leaves_the_ledger_absent(self, tmp_path: Path) -> None:
        """ABSENT, not zero, and the boot writes nothing.

        MUTATION: have `_restore_ledger` return `Ledger(realised_pnl=D("0"),
        ...)` for a missing store. Every reader would behave identically --
        `realised_today` returns zero either way -- so only the `is None`
        assertion can catch it, and the distinction is the one `store.py`
        documents as load-bearing.
        """
        settings = write_settings(tmp_path)
        assert not (tmp_path / "data" / "state.json").exists()

        async with live_system(settings, client=FakeRootClient(), stream=FakeStream()) as system:
            assert system.portfolio.ledger is None
            assert system.portfolio.realised_today(datetime.now(timezone.utc)) == D("0")

        # Boot performs NO write: the store is untouched until a placement.
        assert not (tmp_path / "data" / "state.json").exists()

    async def test_a_restored_record_reaches_the_executor_field_for_field(
        self, tmp_path: Path
    ) -> None:
        """The whole point: a record survives the process that could not resolve it.

        Equality on a frozen dataclass compares ALL SEVEN fields, so this cannot
        rot when an eighth is added -- it fails instead, which is the correct
        response to a field the mapping forgot.

        **It also pins that NOTHING RESOLVES AT BOOT, and does so for free.**
        ``resolve_placement`` reaches ``get_own_open_orders`` and ``get_order``,
        which ``FakeRootClient`` raises ``NotImplementedError`` on. Boot-time
        resolution would therefore not merely change a value here; it would
        raise out of ``__aenter__``. The fixture is the assertion.
        """
        settings = write_settings(tmp_path)
        store.save(store.PersistedState(pending=(_STORED,)))
        # The isolation is asserted, not assumed: this is what proves the module
        # fixture redirected the read away from the repository's own `data/`.
        assert (tmp_path / "data" / "state.json").exists()

        async with live_system(settings, client=FakeRootClient(), stream=FakeStream()) as system:
            assert list(system.executor._pending) == [SYMBOL]
            restored = system.executor._pending[SYMBOL]
            assert restored == _EXPECTED
            # Exactness, not equality: `Decimal("0.0231") == Decimal("0.02310000")`
            # is True, so `==` alone would not catch a value that lost its scale
            # on the way through JSON.
            assert str(restored.quantity) == "0.02310000"
            assert str(restored.entry_limit) == "60123.45000000"
            assert str(restored.stop_loss) == "58000.00000000"
            assert str(restored.take_profit) == "63000.00000000"
            assert restored.entry_bar_time.tzinfo is not None

    async def test_a_corrupt_store_refuses_the_boot_before_any_venue_call(
        self, tmp_path: Path
    ) -> None:
        """The ruling: refuse, and refuse before a socket, a signature or a credential.

        **The journal is what makes this a real ordering assertion.** An
        exception raised after the client had primed symbols and read balances
        would satisfy ``pytest.raises`` identically, so asserting only that
        ``StoreCorruptError`` escaped would pin the refusal and not its
        position. ``FakeRootClient`` records every call it serves; the
        assertion is that it served none.

        ``close_calls == 0`` is deliberate and is NOT a leak this commit
        introduces. The refusal happens before ``resolved_client`` is bound, so
        there is nothing to close -- exactly as the mode-check refusal above it
        has always behaved. An injected client on this path is the caller's to
        close, because the root never took it.
        """
        settings = write_settings(tmp_path)
        (tmp_path / "data").mkdir()
        (tmp_path / "data" / "state.json").write_text("{ truncated", encoding="utf-8")
        journal: list[str] = []
        client = FakeRootClient(journal=journal)

        with pytest.raises(store.StoreCorruptError) as excinfo:
            async with live_system(settings, client=client, stream=FakeStream()):
                pass  # pragma: no cover - the boot must not reach here

        assert "not valid JSON" in str(excinfo.value)
        assert journal == []
        assert client.symbol_info_calls == []
        assert client.order_list_calls == 0
        assert client.close_calls == 0

    async def test_a_truncated_record_refuses_the_boot_too(self, tmp_path: Path) -> None:
        """A parseable file can still be corrupt, and this is the case that motivated it.

        ``stop_loss`` and ``take_profit`` are REQUIRED keys carrying a nullable
        type. A record missing them is valid JSON and would have parsed as an
        UNPROTECTED placement had they defaulted -- silently, in the direction
        that under-states protection. This drives that through the root rather
        than through ``load`` alone, so the refusal is pinned where an operator
        meets it.
        """
        settings = write_settings(tmp_path)
        (tmp_path / "data").mkdir()
        (tmp_path / "data" / "state.json").write_text(
            '{"schema": 1, "ledger": null, "pending": [{"symbol": "BTCUSDT", '
            '"entry_bar_time": "2026-08-14T12:00:00+00:00", "generation": 0, '
            '"quantity": "1", "entry_limit": "2"}]}',
            encoding="utf-8",
        )
        client = FakeRootClient()

        with pytest.raises(store.StoreCorruptError):
            async with live_system(settings, client=client, stream=FakeStream()):
                pass  # pragma: no cover - the boot must not reach here

        assert client.symbol_info_calls == []

    async def test_no_store_is_a_first_boot_and_not_corruption(self, tmp_path: Path) -> None:
        """``load`` returns ``None`` for a missing file, and that path must be ordinary.

        Conflating it with corruption would refuse every first boot, which is
        the failure a store that raises on everything would produce.
        """
        settings = write_settings(tmp_path)
        assert not (tmp_path / "data" / "state.json").exists()

        async with live_system(settings, client=FakeRootClient(), stream=FakeStream()) as system:
            assert system.executor._pending == {}

    async def test_a_restored_ledger_survives_the_next_pending_write(self, tmp_path: Path) -> None:
        """The root owns the WHOLE state, and owning it means not erasing half of it.

        ``store.save`` is whole-file. The executor supplies only ``pending``, so
        a root that started from a fresh ``PersistedState()`` when a store
        existed would write the first placement and silently DELETE the
        ledger -- the whole-file clobber this ownership exists to prevent,
        arriving from inside the owner.

        The ledger value is run 3's real realised loss, so a reader of this test
        can see what would have been lost.

        **Now also asserts the DOMAIN side.** Until the restore this could only
        check that the bytes survived a round trip through a store nothing read;
        the same ledger must now reach ``Portfolio`` as well, so the two halves
        -- durable and in-memory -- are pinned in one place.
        """
        settings = write_settings(tmp_path)
        ledger = store.LedgerRecord(realised_pnl=D("-35.38691640"), pnl_date=date(2026, 8, 27))
        store.save(store.PersistedState(ledger=ledger))

        async with live_system(settings, client=FakeRootClient(), stream=FakeStream()) as system:
            assert system.portfolio.ledger == Ledger(
                realised_pnl=D("-35.38691640"), pnl_date=date(2026, 8, 27)
            )
            writer = system.executor._persist_pending
            assert writer is not None
            writer((_EXPECTED,))

        after = store.load()
        assert after is not None
        assert after.ledger == ledger
        assert str(after.ledger.realised_pnl) == "-35.38691640"
        assert after.pending == (_STORED,)

    async def test_a_restored_record_is_rewritten_not_dropped_by_the_next_write(
        self, tmp_path: Path
    ) -> None:
        """A restored record is in ``_pending``, so it is in what the writer writes.

        Catches a restore that seeds a SEPARATE collection: the executor would
        resolve the record correctly and then erase it from disk on the next
        write, reintroducing the crash window the restore exists to close.
        """
        settings = write_settings(tmp_path)
        store.save(store.PersistedState(pending=(_STORED,)))

        async with live_system(settings, client=FakeRootClient(), stream=FakeStream()) as system:
            writer = system.executor._persist_pending
            assert writer is not None
            writer(tuple(system.executor._pending.values()))

        after = store.load()
        assert after is not None
        assert after.pending == (_STORED,)
