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
import contextlib
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
    """Ask the engine to stop on SIGINT/SIGTERM where the platform allows it.

    ``add_signal_handler`` is POSIX-only — on Windows it raises
    ``NotImplementedError``, and Ctrl-C arrives as a ``KeyboardInterrupt`` at
    the current await instead. Both paths converge on the same clean shutdown
    because :meth:`TradingEngine.run` stops the engine from a ``finally``.
    """
    loop = asyncio.get_running_loop()
    for signal_name in ("SIGINT", "SIGTERM"):
        sig = getattr(signal, signal_name, None)
        if sig is None:  # pragma: no cover - platform dependent
            continue
        # Windows raises NotImplementedError here; Ctrl-C still works via
        # KeyboardInterrupt, which _run_engine handles.
        with contextlib.suppress(NotImplementedError):
            loop.add_signal_handler(sig, engine.request_stop)


async def _run_engine(settings: Settings) -> int:
    """Build, run, and shut down the trading engine."""
    # Deferred import: the engine (and its heavy deps) load only when running.
    from trading_bot.engine.live_engine import TradingEngine

    log = get_logger(__name__)
    engine = await TradingEngine.create(settings)
    _install_shutdown_handlers(engine)
    try:
        await engine.run()
    except KeyboardInterrupt:  # pragma: no cover - interactive
        log.info("Interrupted by user. Shutting down.")
    return 0


def _cmd_run(settings, mode_override: TradingMode | None) -> int:
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


def _cmd_backtest(settings) -> int:
    log = get_logger(__name__)
    log.info("Backtest window: %s -> %s", settings.config.backtesting.start_date,
             settings.config.backtesting.end_date)
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
