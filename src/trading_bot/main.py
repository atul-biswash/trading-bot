"""Command-line entry point.

Responsibilities kept deliberately small: parse arguments, load & validate
settings, initialise logging, record startup provenance -- and refuse ``run``
when it does not establish a clean, installed, pushed commit -- then hand off
to the appropriate runner. Heavy
imports (engine, backtester) are deferred into the dispatch functions so
``python -m trading_bot --help`` stays fast and works without the full stack.

Examples
--------
    python -m trading_bot run                 # uses mode from config.yaml
    python -m trading_bot run --mode paper
    python -m trading_bot backtest            # the configured window, every enabled pair
    python -m trading_bot backtest --start 2024-03-01 --end 2024-04-01 --symbols BTCUSDT
    python -m trading_bot backtest --stop-slippage 0.66 --strategy rsi --timeframe 1h --param period=14
    python -m trading_bot strategies          # list registered strategies
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import logging
import signal
import sys
import time
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import TYPE_CHECKING

from pydantic import ValidationError

from trading_bot.backtesting.overrides import (
    Overrides,
    apply_overrides,
    build_overrides,
    parse_percent,
)
from trading_bot.backtesting.regimes import RegimeTable
from trading_bot.config.models import BacktestConfig
from trading_bot.config.settings import (
    LIVE_TRADING_BLOCKED_MESSAGE,
    Settings,
    get_settings,
    refuse_live_trading,
)
from trading_bot.core.enums import TradingMode
from trading_bot.core.exceptions import ConfigError, LiveTradingBlockedError, TradingBotError
from trading_bot.utils.helpers import utc_now
from trading_bot.utils.logger import (
    CONSOLE_HANDLER_NAME,
    DeferredFileHandler,
    get_logger,
    setup_logging,
)
from trading_bot.utils.provenance import Provenance, collect_provenance, refusal_message

if TYPE_CHECKING:  # pragma: no cover - typing only
    from trading_bot.engine.live_engine import TradingEngine

_EVENT_BOOT_PROVENANCE = "boot_provenance"

_PROVENANCE_GATED = frozenset({"run"})

_BANNER = r"""
  ____  _                            ____        _
 | __ )(_)_ __   __ _ _ __   ___ ___| __ )  ___ | |_
 |  _ \| | '_ \ / _` | '_ \ / __/ _ \  _ \ / _ \| __|
 | |_) | | | | | (_| | | | | (_|  __/ |_) | (_) | |_
 |____/|_|_| |_|\__,_|_| |_|\___\___|____/ \___/ \__|
"""


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="trading-bot", description="Binance Spot trading bot (testnet-first)."
    )
    parser.add_argument(
        "--config",
        default=None,
        help="Path to config.yaml (default: config.yaml or $BOT_CONFIG_PATH).",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    run_cmd = sub.add_parser("run", help="Run the live/testnet/paper trading loop.")
    run_cmd.add_argument(
        "--mode",
        type=TradingMode,
        choices=list(TradingMode),
        default=None,
        help="Override the mode from config.yaml.",
    )

    backtest_cmd = sub.add_parser(
        "backtest", help="Replay stored historical bars through the live decision path."
    )
    backtest_cmd.add_argument(
        "--start",
        type=_iso_date,
        default=None,
        help="First day replayed, YYYY-MM-DD, UTC (default: backtesting.start_date).",
    )
    backtest_cmd.add_argument(
        "--end",
        type=_iso_date,
        default=None,
        help="Day the replay stops BEFORE, YYYY-MM-DD, UTC (default: backtesting.end_date).",
    )
    backtest_cmd.add_argument(
        "--symbols",
        nargs="+",
        default=None,
        metavar="SYMBOL",
        help="Enabled pairs to replay (default: every enabled pair).",
    )
    backtest_cmd.add_argument(
        "--stop-slippage",
        type=_percent,
        default=None,
        metavar="PERCENT",
        help="Stop slippage in percent, the arm (default: backtesting.stop_slippage_percent).",
    )
    backtest_cmd.add_argument(
        "--strategy",
        default=None,
        metavar="NAME",
        help="Replace strategy.name; the configured parameters are dropped with it.",
    )
    backtest_cmd.add_argument(
        "--timeframe",
        default=None,
        metavar="TIMEFRAME",
        help="Replace every pair's timeframe; the staleness bound is raised to fit it.",
    )
    backtest_cmd.add_argument(
        "--param",
        action="append",
        default=None,
        metavar="KEY=VALUE",
        help="Set one strategy parameter; repeatable. Numbers and booleans are read as JSON.",
    )
    sub.add_parser("strategies", help="List available (registered) strategies.")
    return parser


def _iso_date(text: str) -> date:
    """``YYYY-MM-DD`` as a date, for argparse; a malformed one is a usage error."""
    try:
        return date.fromisoformat(text)
    except ValueError:
        raise argparse.ArgumentTypeError(f"not a YYYY-MM-DD date: {text!r}") from None


def _percent(text: str) -> Decimal:
    """A non-negative percentage as an exact ``Decimal``, for argparse; a bad one is a usage error."""
    try:
        return parse_percent(text)
    except ConfigError as exc:
        raise argparse.ArgumentTypeError(str(exc)) from None


def _install_shutdown_handlers(engine: TradingEngine) -> None:
    """Route SIGINT/SIGTERM to a graceful engine shutdown on every platform.

    ``loop.add_signal_handler`` is POSIX-only. Letting Windows fall through to
    the default ``KeyboardInterrupt`` behaviour is not equivalent: that cancels
    the running task, and a *second* Ctrl-C arriving while the WebSocket and
    REST connections are closing aborts that cleanup half-way and leaks them.
    The plain ``signal.signal`` fallback below hands off to the loop instead, so
    both platforms take the same graceful path and repeated Ctrl-C is harmless.

    ``call_soon_threadsafe`` is the one asyncio API documented as safe to call
    from a signal handler. The logging deliberately happens in the callback it
    schedules — which runs on the loop — because ``logging`` takes locks and is
    not async-signal-safe.
    """
    loop = asyncio.get_running_loop()
    log = get_logger(__name__)

    def request_stop(signal_name: str) -> None:
        log.info("Received %s; shutting down gracefully", signal_name)
        engine.request_stop()

    for name in ("SIGINT", "SIGTERM"):
        sig = getattr(signal, name, None)
        if sig is None:  # pragma: no cover - platform dependent
            continue
        try:
            loop.add_signal_handler(sig, request_stop, name)
        except NotImplementedError:  # pragma: no cover - Windows

            def _handler(signum: int, frame: object, _name: str = name) -> None:
                loop.call_soon_threadsafe(request_stop, _name)

            try:
                signal.signal(sig, _handler)
            except ValueError:
                # signal.signal() only works on the main thread; if the engine
                # is driven from a worker thread we simply keep the default
                # behaviour rather than failing to start.
                log.debug("Could not install a %s handler off the main thread", name)


async def _run_engine(settings: Settings) -> int:
    """Build, run, and shut down the whole live system.

    The composition root owns assembly and teardown order; this function only
    says *when*. ``live_system``'s ``finally`` closes the REST client after the
    engine (and through it the provider and stream) has stopped, so a
    ``KeyboardInterrupt`` mid-run still releases every connection.
    """
    # Deferred import: the composition root pulls in pandas/NumPy and the
    # Binance adapters, so it loads only when actually running. `modes` is
    # deliberately not re-exported from `trading_bot.engine` for the same reason.
    from trading_bot.engine.modes import live_system

    async with live_system(settings) as system:
        _install_shutdown_handlers(system.engine)
        await system.engine.run()
    return 0


def _cmd_run(settings: Settings, mode_override: TradingMode | None) -> int:
    log = get_logger(__name__)
    if mode_override is not None:
        settings.mode = mode_override
    # THE LIVE GUARD FOR `--mode`, the one route `main` cannot see: the CLI
    # override lands here, after `main` has already checked the configured
    # mode. It replaces the warning that used to be this branch's whole
    # response to LIVE, and it runs before the "Starting in" line so a refused
    # run never announces itself as starting. `main` translates the raise.
    refuse_live_trading(settings.mode)

    log.info("Starting in %s mode", settings.mode.value.upper())

    # Validate that credentials exist for modes needing a live connection.
    if settings.mode.is_live_connection:
        settings.binance_credentials()  # raises ConfigError if missing

    return asyncio.run(_run_engine(settings))


def _resolve_window(
    configured: BacktestConfig, start: date | None, end: date | None
) -> BacktestConfig:
    """The configured window and costs, with the flags laid over the two dates.

    Rebuilt through validation rather than copied, so a reversed or empty window from the
    flags is refused here as it would be at load.
    """
    update: dict[str, object] = {}
    if start is not None:
        update["start_date"] = start
    if end is not None:
        update["end_date"] = end
    try:
        return BacktestConfig.model_validate({**configured.model_dump(), **update})
    except ValidationError as exc:
        raise ConfigError(f"Invalid backtest window: {exc}") from exc


BACKTEST_LOG_NAME = "backtest.log"

#: How many times a run reads the clock for a free working-directory name before it gives up.
_RUN_CLAIM_ATTEMPTS = 1000


def _claim_run_directory(base: Path) -> tuple[str, Path]:
    """Create this run's ``<stamp>-running`` directory under ``base``; return the stamp and the directory.

    The stamp is read in microseconds, so two runs of one history started within a second do not name one
    directory. But the clock TICKS more coarsely than that (on Windows by as much as about 15 ms), so two
    runs started together, as the S6 sweep's parallel workers are, can read the SAME stamp. ``mkdir`` is
    atomic: exactly one of them wins, and the loser reads the clock again and takes a later stamp. Before this
    the loser died on ``FileExistsError`` after its research-protocol guard and its regime-label load had
    run, and left no record (the rehearsal of P118 met it in R-CH's own parallel check).

    :raises FileExistsError: no name was free after ``_RUN_CLAIM_ATTEMPTS`` reads of the clock.
    """
    base.mkdir(parents=True, exist_ok=True)
    for _ in range(_RUN_CLAIM_ATTEMPTS):
        stamp = utc_now().strftime("%Y%m%dT%H%M%S%fZ")
        working = base / f"{stamp}-running"
        try:
            working.mkdir()
        except FileExistsError:
            time.sleep(0.001)
            continue
        return stamp, working
    raise FileExistsError(
        f"no free run directory name under {base} after {_RUN_CLAIM_ATTEMPTS} reads of the clock"
    )


#: The committed quarterly regime labels (R-AI), relative to the launch directory.
REGIME_LABELS_PATH = Path("docs") / "REGIME_LABELS.json"


def _load_regimes(log: logging.Logger) -> RegimeTable | None:
    """The committed labels, or ``None`` with a warning if the file is absent.

    A file that is present and does not match its digest file is a ``ConfigError``: a run
    must not be labelled by regimes nobody can vouch for.
    """
    if not REGIME_LABELS_PATH.is_file():
        log.warning(
            "No regime labels at %s; the metrics carry no per-regime breakdown", REGIME_LABELS_PATH
        )
        return None
    try:
        return RegimeTable.from_file(REGIME_LABELS_PATH)
    except ValueError as exc:
        raise ConfigError(f"Invalid regime labels: {exc}") from exc


def _seal_run_directory(run_log: DeferredFileHandler, working: Path, suffix: str) -> None:
    """Close the run's log and rename its working directory, best effort.

    Used when a run did not finish: the directory holds only its log, and a name ending in
    ``suffix`` says so. A rename that fails (an antivirus scan, a name already taken) leaves
    the ``-running`` name, which is still true.
    """
    run_log.close_file()
    with contextlib.suppress(OSError):
        working.rename(working.with_name(working.name.removesuffix("-running") + f"-{suffix}"))


def _check_protocol(
    settings: Settings,
    window: BacktestConfig,
    symbols: list[str] | None,
    given: Overrides,
    facts: Provenance,
    runs: Path,
) -> dict[str, object]:
    """Ask the research-protocol guard (R-BT) whether this run may be made; return what it decided.

    Runs BEFORE any run directory exists, so a refusal leaves nothing on disk. The effective block it
    judges is built here from the same pieces the engine builds the record's from (the effective
    config, the resolved window, the selected pairs in order, the overrides as given), and a test
    holds the two digests equal. The protocol and the entries are read from the launch directory,
    which is the repository root of the clone the run is made from.

    :param runs: this clone's run directories, scanned for a prior out-of-sample read only when the
        window touches the out-of-sample window.
    :raises ProtocolRefusalError: the guard refuses the run; ``.reason`` names the rule.
    :raises ProtocolError: the protocol, an entry or a prior record cannot be read.
    """
    from trading_bot.backtesting.candidate import effective_settings
    from trading_bot.backtesting.engine import select_pairs
    from trading_bot.backtesting.protocol import (
        WindowClass,
        check_run,
        classify_window,
        load_entries,
        load_protocol,
        local_reads,
    )

    protocol = load_protocol()
    entries = load_entries()
    effective = effective_settings(
        settings.config,
        window,
        [(pair.symbol, pair.timeframe) for pair in select_pairs(settings, symbols)],
        config_sha256=settings.config_sha256,
        overrides=given.record(),
    )
    touches = classify_window(protocol, window.start_date, window.end_date) is not (
        WindowClass.IN_SAMPLE
    )
    decision = check_run(
        protocol,
        entries,
        effective=effective,
        window_start=window.start_date,
        window_end=window.end_date,
        provenance_accepted=facts.accepted,
        local_reads=local_reads(protocol, runs) if touches else frozenset(),
    )
    return decision.record()


def _cmd_backtest(
    settings: Settings,
    start: date | None,
    end: date | None,
    symbols: list[str] | None,
    run_log: DeferredFileHandler,
    facts: Provenance,
    overrides: Overrides | None = None,
) -> int:
    """Replay the window, write the run record, and return whether it is a result.

    The window the run used is the RESOLVED one -- the flags laid over the config -- and it is
    what the record names. **The settings are the EFFECTIVE ones (R-BR):** ``overrides`` (the
    stop-slippage arm, the strategy, the timeframe, the strategy parameters) are laid over the
    config and the result re-validated BEFORE anything else, so an override the config's own
    checks refuse leaves no directory; the record's ``effective`` block holds what was used.
    **The research-protocol guard (R-BT) runs in the same place, before any directory exists**: a
    window that touches the out-of-sample window is made only if :func:`_check_protocol` allows it,
    and what it decided is the record's ``protocol`` block.
    Returns 1 for a run that is not a result: a handler failure, an
    ERROR logged, a pair that served nothing, or a cash identity that does not close. It prints
    nothing on success (R-BE) and never names the record file (R-BF).

    **The log (R-AG) goes to ``<run directory>/backtest.log`` and nowhere else on disk**:
    ``main`` has switched the config's file sink off for this command and attached
    ``run_log``, which has held every record since the banner. The directory is made, and the
    log opened, only after the window and the symbols are validated, so a refusal leaves no
    directory. It is made as ``<stamp>-running`` and renamed to ``<stamp>-<digest>`` once the
    record is written, or to ``<stamp>-failed`` if the run raised.

    **The record carries the boot line (R-AH)**: ``facts`` is the very ``Provenance`` that
    ``main`` logged as ``boot_provenance``, handed to the run, so the record's ``provenance``
    block is that line's verdict and fields and not a second collection that could differ.
    """
    from trading_bot.backtesting.engine import run_backtest, select_pairs, write_run

    log = get_logger(__name__)
    given = overrides if overrides is not None else Overrides()
    settings = settings.with_config(apply_overrides(settings.config, given))
    window = _resolve_window(settings.config.backtesting, start, end)
    if not given.is_empty:
        log.info("Backtest overrides: %s", given.record())
    log.info(
        "Backtest window: %s -> %s, symbols %s",
        window.start_date,
        window.end_date,
        "all enabled" if symbols is None else ",".join(symbols),
    )
    select_pairs(settings, symbols)  # refuse an unenabled symbol before any directory exists
    base = Path(window.data_dir).parent / "backtests"
    # R-BT: the research-protocol guard, likewise before any directory exists.
    decision = _check_protocol(settings, window, symbols, given, facts, base)
    log.info(
        "Research protocol: window %s, arm %s, entry %s",
        decision["window_class"],
        decision["arm"],
        decision["entry_id"],
    )
    regimes = _load_regimes(log)  # likewise: a label file that does not verify refuses here
    stamp, working = _claim_run_directory(base)
    run_log.open(working / BACKTEST_LOG_NAME)
    try:
        result = asyncio.run(
            run_backtest(
                settings,
                window=window,
                symbols=symbols,
                exchange_info_environment=window.exchange_info_environment,
                code_facts=facts.log_fields,
                regimes=regimes,
                overrides=given.record(),
                protocol=decision,
            )
        )
        final = base / f"{stamp}-{result.trade_log_sha256[:12]}"
        write_run(result, working, existing=True)
        log.info(
            "Backtest %s: %d trade(s), trade log %s; run directory %s, trades %s, log %s",
            "complete" if result.complete else "INCOMPLETE",
            len(result.trades),
            result.trade_log_sha256,
            final,
            final / "trades.csv",
            final / BACKTEST_LOG_NAME,
        )
        for problem in result.problems:
            log.error("Backtest problem: %s", problem)
    except BaseException as exc:
        log.error("Backtest aborted: %s: %s", type(exc).__name__, exc)
        _seal_run_directory(run_log, working, "failed")
        raise
    run_log.close_file()
    working.rename(final)
    # R-BE: nothing is printed here. A backtest prints figures, not a verdict, and its figures are
    # in the run directory's log and record; the exit status says whether it is a result.
    return 0 if result.complete else 1


def _cmd_strategies() -> int:
    from trading_bot.strategies.registry import available_strategies

    print("Registered strategies:")
    for name in available_strategies():
        print(f"  - {name}")
    return 0


def _log_provenance(log: logging.Logger, facts: Provenance) -> None:
    """The boot line: ``INFO`` when accepted, ``ERROR`` when refused."""
    fields = facts.log_fields()
    log.log(
        logging.INFO if facts.accepted else logging.ERROR,
        "Startup provenance %s",
        fields["verdict"],
        extra={"event": _EVENT_BOOT_PROVENANCE, **fields},
    )


def main(argv: list[str] | None = None) -> int:
    """Program entry point. Returns a process exit code."""
    args = _build_parser().parse_args(argv)

    try:
        settings = get_settings(args.config)
    except TradingBotError as exc:
        print(f"Configuration error: {exc}", file=sys.stderr)
        return 2

    # THE LIVE GUARD FOR `config.yaml` AND `BOT_MODE`, on every subcommand, and
    # AHEAD OF `setup_logging` so a refused start opens no log file. Live
    # trading is blocked by architectural invariant (CLAUDE.md); nothing
    # overrides it. `SystemExit` with a string exits 1 and prints the ruled
    # message to stderr, unadorned.
    try:
        refuse_live_trading(settings.mode)
    except LiveTradingBlockedError:
        raise SystemExit(LIVE_TRADING_BLOCKED_MESSAGE) from None

    # R-AG: a backtest logs only to a file in its own run directory, never to the bot's
    # `logs/trading_bot.log`. So for `backtest` the config's file sink is switched off and a
    # deferred handler holds every record until `_cmd_backtest` has made the directory.
    run_log: DeferredFileHandler | None = None
    logging_config = settings.config.logging
    if args.command == "backtest":
        no_file = logging_config.file.model_copy(update={"enabled": False})
        setup_logging(logging_config.model_copy(update={"file": no_file}))
        run_log = DeferredFileHandler(json_format=logging_config.file.json_format)
        logging.getLogger().addHandler(run_log)
        _quiet_console()  # R-AS: WARNING and above on the console, everything in the file
    else:
        setup_logging(logging_config)
    try:
        return _dispatch(args, settings, run_log)
    finally:
        if run_log is not None:
            logging.getLogger().removeHandler(run_log)
            run_log.close()


def _quiet_console() -> None:
    """R-AS: raise the console handler ``setup_logging`` built to WARNING.

    The owner's ruling, verbatim: *"During a backtest the console carries WARNING and above;
    the full log goes to the run directory's file."* The root logger's own level is not
    touched, so every record still reaches the run log; only the handler that prints is
    raised, and one already above WARNING keeps its level. The handler is found by the name
    ``setup_logging`` gives it, so a handler somebody else attached (a test's capture, say) is
    never touched. A backtest logs about 1.1 MB at INFO (M5m-191), which on the console buried
    the warnings an operator needs.
    """
    for handler in logging.getLogger().handlers:
        if handler.get_name() == CONSOLE_HANDLER_NAME:
            handler.setLevel(max(handler.level, logging.WARNING))


def _dispatch(
    args: argparse.Namespace, settings: Settings, run_log: DeferredFileHandler | None
) -> int:
    """Log the banner and the provenance line, then run the subcommand."""
    log = get_logger(__name__)
    log.info("%s", _BANNER)
    facts = collect_provenance(settings.config_path, settings.config_sha256)
    _log_provenance(log, facts)
    if args.command in _PROVENANCE_GATED and not facts.accepted:
        raise SystemExit(refusal_message(facts))

    try:
        if args.command == "run":
            return _cmd_run(settings, args.mode)
        if args.command == "backtest":
            if run_log is None:  # main attaches it for exactly this command
                raise RuntimeError("backtest dispatched without its run log")
            overrides = build_overrides(
                stop_slippage=args.stop_slippage,
                strategy=args.strategy,
                timeframe=args.timeframe,
                params=args.param,
            )
            return _cmd_backtest(
                settings, args.start, args.end, args.symbols, run_log, facts, overrides
            )
        if args.command == "strategies":
            return _cmd_strategies()
    except LiveTradingBlockedError:
        # AHEAD of the generic clause below, which would log it and return 1
        # with a different text. Reached by `_cmd_run`'s `--mode` guard, and by
        # `Settings.binance_credentials` if any path ever skipped both guards.
        raise SystemExit(LIVE_TRADING_BLOCKED_MESSAGE) from None
    except TradingBotError as exc:
        log.error("%s", exc)
        return 1
    except KeyboardInterrupt:  # pragma: no cover
        log.info("Interrupted by user. Shutting down.")
        return 130

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
