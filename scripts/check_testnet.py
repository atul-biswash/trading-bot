#!/usr/bin/env python
"""Standalone Binance connectivity check — **testnet by default**.

Verifies that credentials are wired correctly and that the REST adapter can
reach the exchange, by pinging, listing non-zero balances, and fetching a
ticker. It is intended as the first thing you run after adding API keys.

It also answers the precondition a supervised run depends on: **whether the
account already holds the base assets of the configured pairs.**
``engine.modes._snapshot_unmanaged_holdings`` turns such a holding into a
permanent per-symbol entry refusal at boot, so a bot pointed at a pre-funded
account can sit green for an hour and dispatch nothing. The alphabetical
balance sample below is capped at twenty rows, and a Testnet account funded
with hundreds of assets pushes BTC, ETH and USDT far outside that window --
which is why they are reported separately and uncapped.

**Read-only, and by construction rather than by flag.** Every venue call it
makes is a read: ``ping``, ``get_balances``, ``get_ticker``,
``get_symbol_info``, ``get_open_orders``, ``get_all_order_lists``. It places
nothing, cancels nothing, amends nothing and writes no file. A non-terminal
order list is reported and deliberately left alone.

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
from collections import Counter
from decimal import Decimal
from typing import TYPE_CHECKING

from trading_bot.config.settings import get_settings
from trading_bot.core.enums import TradingMode
from trading_bot.core.exceptions import ConfigError, TradingBotError
from trading_bot.exchange import BinanceClient

if TYPE_CHECKING:  # pragma: no cover - typing only
    from collections.abc import Awaitable, Sequence

    from trading_bot.core.models import Balance, Order, OrderList, SymbolInfo

#: Reported individually and without a display cap. The sample below is capped
#: and alphabetical, so on a Testnet account these three fall outside it -- and
#: they are the three a supervised run's viability turns on. Printed whether
#: held or not: a zero is an answer, and an omitted row is not.
_REPORTED_ASSETS = ("BTC", "ETH", "USDT")

#: The shipped ``config.yaml`` pair list. Their filters and their
#: unmanaged-holding arithmetic decide whether the bot can enter at all.
_REPORTED_SYMBOLS = ("BTCUSDT", "ETHUSDT")

#: Default survey for ``--candidates``: does ANY pair reachable by
#: configuration alone hold a base balance small enough to be dust, and so
#: escape the ``UNMANAGED_HOLDING`` refusal?
#:
#: Selected as USDT-quoted spot pairs listed on Binance for years and among the
#: most liquid by volume, spanning large through mid cap so the survey is not
#: all one tier. **The two configured pairs are included on purpose**: their
#: answer is already known, and a survey carrying no known answer is an
#: uncalibrated instrument. ``MATICUSDT`` is included expecting it to be
#: absent, so the unsupported-symbol path is exercised rather than assumed.
_CANDIDATE_SYMBOLS = (
    "BTCUSDT",
    "ETHUSDT",
    "BNBUSDT",
    "XRPUSDT",
    "SOLUSDT",
    "ADAUSDT",
    "DOGEUSDT",
    "TRXUSDT",
    "LTCUSDT",
    "LINKUSDT",
    "DOTUSDT",
    "MATICUSDT",
    "AVAXUSDT",
    "ATOMUSDT",
    "UNIUSDT",
)

#: List statuses from which nothing further happens. A **blacklist**, matching
#: the direction :class:`~trading_bot.core.enums.OrderStatus` takes: a status
#: nobody has classified is reported as live. Over-reporting a resting list
#: costs one line of output; under-reporting one hides money at the venue.
#: ``OrderList.list_order_status`` is carried as text, so there is no enum to
#: exhaust here.
_TERMINAL_LIST_STATUSES = frozenset({"ALL_DONE"})

#: Rows of the alphabetical balance sample. Unchanged behaviour, kept beside
#: the uncapped report rather than replaced by it.
_SAMPLE_ROWS = 20


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
    parser.add_argument(
        "--candidates",
        default=",".join(_CANDIDATE_SYMBOLS),
        help=(
            "Comma-separated USDT-quoted symbols to survey for a dust-sized base "
            "holding (default: a fifteen-symbol liquid set including both configured pairs)."
        ),
    )
    return parser


async def _step[T](label: str, call: Awaitable[T], failures: list[str]) -> T | None:
    """Await one labelled venue read, recording a failure rather than raising.

    A probe exists to gather facts, so one failed call must not discard the
    facts the others already returned. It must still be **named**, or a short
    report is indistinguishable from a complete one -- which is the failure
    this script exists to avoid rather than commit.
    """
    try:
        return await call
    except TradingBotError as exc:
        print(f"  !! {label} FAILED: {type(exc).__name__}: {exc}", file=sys.stderr)
        failures.append(label)
        return None


def _print_key_balances(balances: Sequence[Balance]) -> None:
    """Free, locked and total for each of :data:`_REPORTED_ASSETS`, uncapped."""
    held = {balance.asset.upper(): balance for balance in balances}
    print("  key balances (uncapped):")
    for asset in _REPORTED_ASSETS:
        balance = held.get(asset)
        if balance is None:
            print(f"    {asset:>6}  free=0  locked=0  total=0   (not held)")
            continue
        print(
            f"    {asset:>6}  free={balance.free}  locked={balance.locked}  total={balance.total}"
        )


def _print_filters(info: SymbolInfo) -> None:
    """The four filters sizing and dispatch are bounded by."""
    print(
        f"    filters: min_notional={info.min_notional}  tick_size={info.price_tick}  "
        f"step_size={info.step_size}  min_qty={info.min_qty}"
    )


def _holding_verdict(info: SymbolInfo, *, free_base: Decimal, last: Decimal) -> str:
    """``DUST`` or ``BLOCKS`` for one holding. **The only copy of the test.**

    Reproduced in the same direction and with the same strictness as the
    comparison it mirrors, in ``engine.modes._snapshot_unmanaged_holdings``::

        if balance.free * price < pairs[symbol].symbol_info.min_notional:
            continue  # dust: too small to sell, so it must not block the pair

    So ``<`` is DUST and ``>=`` BLOCKS, and the **strict** side is the dust
    side. ``free`` rather than ``total``, because materiality there is
    sellability and locked base cannot be sold. All-``Decimal`` throughout:
    ``free_base`` and ``last`` are both ``Money``, so no float enters the
    product.

    Both the per-pair report and the candidate survey call this rather than
    repeating the comparison, so there is one place for it to be wrong.
    """
    return "DUST" if free_base * last < info.min_notional else "BLOCKS"


def _print_holding_verdict(info: SymbolInfo, *, free_base: Decimal, last: Decimal) -> None:
    """Show the arithmetic :func:`_holding_verdict` performs, not just its answer."""
    value = free_base * last
    short = _holding_verdict(info, free_base=free_base, last=last)
    verdict = "DUST (does not block)" if short == "DUST" else "BLOCKS entries"
    print(
        f"    unmanaged holding: free={free_base} x last={last} = {value} "
        f"vs min_notional={info.min_notional}  ->  {verdict}"
    )


def _print_open_orders(orders: Sequence[Order]) -> None:
    """Every resting order on the symbol, ours and anyone else's."""
    print(f"    open orders: {len(orders)}")
    for order in orders:
        print(
            f"      {order.symbol}  {order.side.value}  {order.type.value}  "
            f"{order.status.value}  client_order_id={order.client_order_id}"
        )


def _print_order_lists(lists: Sequence[OrderList]) -> None:
    """Total, a breakdown by list status, and every non-terminal list."""
    print(f"  order lists: {len(lists)} on the account")
    counts = Counter(entry.list_order_status or "(absent)" for entry in lists)
    for status, count in sorted(counts.items()):
        print(f"    {status}: {count}")

    live = [
        entry
        for entry in lists
        if (entry.list_order_status or "(absent)") not in _TERMINAL_LIST_STATUSES
    ]
    if not live:
        print("    none outside a terminal status")
        return
    print(f"    {len(live)} NOT terminal -- reported only; nothing here is cancelled or touched:")
    for entry in live:
        print(
            f"      list_id={entry.order_list_id}  symbol={entry.symbol}  "
            f"order_status={entry.list_order_status}  status_type={entry.list_status_type}"
        )


async def _report_symbol(
    client: BinanceClient,
    symbol: str,
    balances: Sequence[Balance],
    failures: list[str],
) -> None:
    """Filters, the unmanaged-holding arithmetic, and open orders for one pair."""
    print(f"  {symbol}:")
    info = await _step(f"{symbol} get_symbol_info", client.get_symbol_info(symbol), failures)
    if info is not None:
        _print_filters(info)

    ticker = await _step(f"{symbol} get_ticker", client.get_ticker(symbol), failures)
    if info is not None and ticker is not None:
        held = {balance.asset.upper(): balance for balance in balances}
        base = held.get(info.base_asset.upper())
        free_base = base.free if base is not None else Decimal(0)
        _print_holding_verdict(info, free_base=free_base, last=ticker.last)

    orders = await _step(f"{symbol} get_open_orders", client.get_open_orders(symbol), failures)
    if orders is not None:
        _print_open_orders(orders)


async def _survey_one(
    client: BinanceClient,
    symbol: str,
    held: dict[str, Balance],
    failures: list[str],
) -> None:
    """One candidate row: does its base holding block, or is it dust?

    **A symbol the venue does not list is reported, not fatal.** One absent
    candidate must not abort the survey, so ``get_symbol_info`` is caught here
    rather than routed through :func:`_step`: an unlisted symbol is an answer
    about the venue, not a failed read, and counting it as a failure would make
    the exit code report a problem that is not one. The exception text is
    printed beside the label so a transport failure stays distinguishable from
    a genuinely unlisted symbol -- the label alone would merge them.

    **No ticker is fetched when free base is exactly zero.** Zero is dust at
    every price, so the call would buy nothing; on a survey this is most of the
    round trips.
    """
    try:
        info = await client.get_symbol_info(symbol)
    except TradingBotError as exc:
        print(f"    {symbol:<10}  UNSUPPORTED ON TESTNET  ({type(exc).__name__}: {exc})")
        return

    balance = held.get(info.base_asset.upper())
    free_base = balance.free if balance is not None else Decimal(0)
    if free_base == 0:
        print(
            f"    {symbol:<10}  free=0  min_notional={info.min_notional}  "
            f"->  DUST  (zero is dust at any price; no ticker fetched)"
        )
        return

    ticker = await _step(f"{symbol} get_ticker", client.get_ticker(symbol), failures)
    if ticker is None:
        return
    verdict = _holding_verdict(info, free_base=free_base, last=ticker.last)
    print(
        f"    {symbol:<10}  free={free_base} x last={ticker.last} = "
        f"{free_base * ticker.last}  vs min_notional={info.min_notional}  ->  {verdict}"
    )


async def _survey_candidates(
    client: BinanceClient,
    symbols: Sequence[str],
    balances: Sequence[Balance],
    failures: list[str],
) -> None:
    """Ask of every candidate whether its base holding would refuse entries."""
    print(f"  candidate survey ({len(symbols)} symbol(s)):")
    held = {balance.asset.upper(): balance for balance in balances}
    for symbol in symbols:
        await _survey_one(client, symbol, held, failures)


async def _check(
    mode: TradingMode, symbol: str, config: str | None, candidates: Sequence[str]
) -> int:
    settings = get_settings(config)
    # Force the mode from the CLI (see module docstring: this utility ignores
    # the configured mode on purpose).
    settings.mode = mode

    # Fail fast with a clear message if keys are missing, before opening a
    # session.
    settings.binance_credentials()

    print(f"Connecting to Binance {mode.value.upper()} ...")
    client = await BinanceClient.create(settings)
    failures: list[str] = []
    try:
        await client.ping()
        print("  ping: OK")

        balances = await client.get_balances()
        nonzero = [b for b in balances if b.total > 0]
        print(f"  balances: {len(nonzero)} asset(s) with a non-zero balance")
        # Of those, how many are spendable. `free` is what the dust test reads,
        # so a holding that is entirely locked is dust however large it is.
        free_zero = sum(1 for b in nonzero if b.free == 0)
        print(
            f"    of those: {len(nonzero) - free_zero} with free > 0, "
            f"{free_zero} with free exactly zero (fully locked)"
        )
        for balance in sorted(nonzero, key=lambda b: b.asset)[:_SAMPLE_ROWS]:
            print(f"    {balance.asset:>6}  free={balance.free}  locked={balance.locked}")

        _print_key_balances(balances)

        ticker = await client.get_ticker(symbol)
        print(f"  {symbol} last={ticker.last}  bid={ticker.bid}  ask={ticker.ask}")

        for pair in _REPORTED_SYMBOLS:
            await _report_symbol(client, pair, balances, failures)

        await _survey_candidates(client, candidates, balances, failures)

        lists = await _step("get_all_order_lists", client.get_all_order_lists(), failures)
        if lists is not None:
            _print_order_lists(lists)
    finally:
        await client.close()

    if failures:
        print(
            f"Completed with {len(failures)} failed step(s): {', '.join(failures)}",
            file=sys.stderr,
        )
        return 1

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

    candidates = [name.strip().upper() for name in args.candidates.split(",") if name.strip()]

    try:
        return asyncio.run(_check(mode, args.symbol, args.config, candidates))
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
