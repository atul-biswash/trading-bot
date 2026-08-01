"""Command-line entry point.

Responsibilities kept deliberately small: parse arguments, load & validate
settings, initialise logging, then hand off to the appropriate runner. Heavy
imports (engine, backtester) are deferred into the dispatch functions so
``python -m trading_bot --help`` stays fast and works without the full stack.

Examples
--------
    python -m trading_bot run                 # uses mode from config.yaml
    python -m trading_bot run --mode paper
    python -m trading_bot backtest
    python -m trading_bot strategies          # list registered strategies
"""

from __future__ import annotations

import argparse
import asyncio
import signal
import sys
from typing import TYPE_CHECKING

from trading_bot.config.settings import Settings, get_settings
from trading_bot.core.enums import TradingMode
from trading_bot.core.exceptions import TradingBotError
from trading_bot.utils.logger import get_logger, setup_logging

if TYPE_CHECKING:  # pragma: no cover - typing only
    from trading_bot.engine.live_engine import TradingEngine

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

    sub.add_parser("backtest", help="Run the backtesting engine over historical data.")
    sub.add_parser("strategies", help="List available (registered) strategies.")
    return parser


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

    log.info("Starting in %s mode", settings.mode.value.upper())
    if settings.mode is TradingMode.LIVE:
        log.warning("LIVE mode uses REAL funds. Ensure you understand the risks.")

    # Validate that credentials exist for modes needing a live connection.
    if settings.mode.is_live_connection:
        settings.binance_credentials()  # raises ConfigError if missing

    return asyncio.run(_run_engine(settings))


def _cmd_backtest(settings: Settings) -> int:
    log = get_logger(__name__)
    log.info(
        "Backtest window: %s -> %s",
        settings.config.backtesting.start_date,
        settings.config.backtesting.end_date,
    )
    log.error("Backtesting engine is not implemented yet (scaffolding phase).")
    return 0


def _cmd_strategies() -> int:
    from trading_bot.strategies.registry import available_strategies

    print("Registered strategies:")
    for name in available_strategies():
        print(f"  - {name}")
    return 0


def main(argv: list[str] | None = None) -> int:
    """Program entry point. Returns a process exit code."""
    args = _build_parser().parse_args(argv)

    try:
        settings = get_settings(args.config)
    except TradingBotError as exc:
        print(f"Configuration error: {exc}", file=sys.stderr)
        return 2

    setup_logging(settings.config.logging)
    log = get_logger(__name__)
    log.info("%s", _BANNER)

    try:
        if args.command == "run":
            return _cmd_run(settings, args.mode)
        if args.command == "backtest":
            return _cmd_backtest(settings)
        if args.command == "strategies":
            return _cmd_strategies()
    except TradingBotError as exc:
        log.error("%s", exc)
        return 1
    except KeyboardInterrupt:  # pragma: no cover
        log.info("Interrupted by user. Shutting down.")
        return 130

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
