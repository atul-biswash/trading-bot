#!/usr/bin/env python
"""Standalone Binance connectivity check — **testnet by default**.

Verifies that credentials are wired correctly and that the REST adapter can
reach the exchange, by pinging, listing non-zero balances, and fetching a
ticker. It is intended as the first thing you run after adding API keys.

Safety
------
* The mode is taken **only** from ``--mode`` (default ``testnet``); this script
  deliberately ignores the mode in ``config.yaml`` / ``BOT_MODE`` so a stray
  ``live`` there can never cause an accidental live connection.
* ``--mode live`` additionally requires ``--confirm-live``.

Examples
--------
    python scripts/check_testnet.py
    python scripts/check_testnet.py --symbol ETHUSDT
    python scripts/check_testnet.py --mode live --confirm-live
"""

from __future__ import annotations

import argparse
import asyncio
import sys

from trading_bot.config.settings import get_settings
from trading_bot.core.enums import TradingMode
from trading_bot.core.exceptions import ConfigError, TradingBotError
from trading_bot.exchange import BinanceClient


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="check-testnet",
        description="Verify Binance REST connectivity and credentials (testnet by default).",
    )
    parser.add_argument(
        "--mode",
        choices=["testnet", "live"],
        default="testnet",
        help="Environment to connect to (default: testnet).",
    )
    parser.add_argument(
        "--confirm-live",
        action="store_true",
        help="Required acknowledgement when --mode live is used.",
    )
    parser.add_argument(
        "--symbol",
        default="BTCUSDT",
        help="Symbol to fetch a ticker for (default: BTCUSDT).",
    )
    parser.add_argument(
        "--config",
        default=None,
        help="Path to config.yaml (default: config.yaml or $BOT_CONFIG_PATH).",
    )
    return parser


async def _check(mode: TradingMode, symbol: str, config: str | None) -> int:
    settings = get_settings(config)
    # Force the mode from the CLI (see module docstring: this utility ignores
    # the configured mode on purpose).
    settings.mode = mode

    # Fail fast with a clear message if keys are missing, before opening a
    # session.
    settings.binance_credentials()

    print(f"Connecting to Binance {mode.value.upper()} ...")
    client = await BinanceClient.create(settings)
    try:
        await client.ping()
        print("  ping: OK")

        balances = await client.get_balances()
        nonzero = [b for b in balances if b.total > 0]
        print(f"  balances: {len(nonzero)} asset(s) with a non-zero balance")
        for balance in sorted(nonzero, key=lambda b: b.asset)[:20]:
            print(f"    {balance.asset:>6}  free={balance.free}  locked={balance.locked}")

        ticker = await client.get_ticker(symbol)
        print(f"  {symbol} last={ticker.last}  bid={ticker.bid}  ask={ticker.ask}")
    finally:
        await client.close()

    print("All checks passed.")
    return 0


def main(argv: list[str] | None = None) -> int:
    """Entry point. Returns a process exit code (0 ok, 1 exchange, 2 config)."""
    args = _build_parser().parse_args(argv)
    mode = TradingMode.LIVE if args.mode == "live" else TradingMode.TESTNET

    if mode is TradingMode.LIVE and not args.confirm_live:
        print(
            "Refusing to connect to LIVE without explicit confirmation.\n"
            "Re-run with:  python scripts/check_testnet.py --mode live --confirm-live",
            file=sys.stderr,
        )
        return 2
    if mode is TradingMode.LIVE:
        print("!! LIVE selected — connecting to real Binance with real funds.")

    try:
        return asyncio.run(_check(mode, args.symbol, args.config))
    except ConfigError as exc:
        print(f"Configuration error: {exc}", file=sys.stderr)
        return 2
    except TradingBotError as exc:
        print(f"Exchange error: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:  # pragma: no cover
        print("Interrupted.", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
