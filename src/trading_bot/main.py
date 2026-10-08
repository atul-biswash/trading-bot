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
    python -m trading_bot strategies          # list registered strategies
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import signal
import sys
from datetime import date
from pathlib import Path
from typing import TYPE_CHECKING

from pydantic import ValidationError

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
from trading_bot.utils.logger import get_logger, setup_logging
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
    sub.add_parser("strategies", help="List available (registered) strategies.")
    return parser


def _iso_date(text: str) -> date:
    """``YYYY-MM-DD`` as a date, for argparse; a malformed one is a usage error."""
    try:
        return date.fromisoformat(text)
    except ValueError:
        raise argparse.ArgumentTypeError(f"not a YYYY-MM-DD date: {text!r}") from None


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


def _cmd_backtest(
    settings: Settings, start: date | None, end: date | None, symbols: list[str] | None
) -> int:
    """Replay the window, write the run record, and say whether it is a result.

    The window the run used is the RESOLVED one -- the flags laid over the config -- and it is
    what the record names. Returns 1 for a run that is not a result: a handler failure, an
    ERROR logged, a pair that served nothing, or a cash identity that does not close.
    """
    from trading_bot.backtesting.engine import run_backtest, write_run

    log = get_logger(__name__)
    window = _resolve_window(settings.config.backtesting, start, end)
    log.info(
        "Backtest window: %s -> %s, symbols %s",
        window.start_date,
        window.end_date,
        "all enabled" if symbols is None else ",".join(symbols),
    )
    result = asyncio.run(run_backtest(settings, window=window, symbols=symbols))
    # Microseconds, so two runs of one history started within a second do not name one directory.
    stamp = utc_now().strftime("%Y%m%dT%H%M%S%fZ")
    directory = (
        Path(window.data_dir).parent / "backtests" / f"{stamp}-{result.trade_log_sha256[:12]}"
    )
    run_path, trades_path = write_run(result, directory)
    log.info(
        "Backtest %s: %d trade(s), trade log %s; record %s, trades %s",
        "complete" if result.complete else "INCOMPLETE",
        len(result.trades),
        result.trade_log_sha256,
        run_path,
        trades_path,
    )
    for problem in result.problems:
        log.error("Backtest problem: %s", problem)
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

    setup_logging(settings.config.logging)
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
            return _cmd_backtest(settings, args.start, args.end, args.symbols)
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
