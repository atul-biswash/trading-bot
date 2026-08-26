#!/usr/bin/env python
"""Sell a Binance **Spot Testnet** base holding, to clear the entry refusal.

``engine.modes._snapshot_unmanaged_holdings`` records any material base holding
the account already carries and ``RiskManager.evaluate`` then refuses every
entry on that symbol under ``RefusalStage.UNMANAGED_HOLDING``. A Testnet account
is faucet-funded with hundreds of assets, so both configured pairs are refused
and a supervised run dispatches nothing. The Testnet website exposes no trading
UI, so clearing the holding has to go through the API. That is what this is for,
and it is the whole of what it is for.

**TESTNET ONLY, and by construction rather than by flag.** Three layers:

1. ``testnet=True`` is a literal in the one ``AsyncClient.create`` call. There
   is no ``--mode``, no environment override, and no ``config.yaml`` key on any
   path here -- the script never loads ``config.yaml`` at all.
2. Credentials come from the **testnet slot only**.
   :func:`_testnet_credentials` reads ``BINANCE_TESTNET_API_KEY`` /
   ``BINANCE_TESTNET_API_SECRET`` and refuses when either is empty. It
   deliberately does **not** call ``Settings.binance_credentials()``, which
   falls back to the LIVE key slot when the testnet slot is blank -- a
   convenience for a read-only probe and a hazard for a seller. The live slot is
   never read, so even a mis-built client has nothing to authenticate with.
3. :func:`build_client` asserts ``client.testnet is True`` before any signed
   call, reading the library's own state rather than trusting the argument.

Layer 1 is the guarantee and layers 2 and 3 are what survive an edit to it.
``tests/unit/test_clear_testnet_holdings.py`` pins all three, because a
hardcoded constant and a parameter look identical to every gate this project
runs.

**It does NOT trade.** It never buys, never cancels, never touches an order
list, never sells a symbol outside :data:`ALLOWED_SYMBOLS`, and never sells a
partial amount by choice -- it sells the whole roundable free balance or
nothing. It does not retry a rejected sell.

**Dry run by default.** Without ``--execute`` every sale is validated at the
venue through ``create_test_order`` (``POST /api/v3/order/test``), which applies
the real filters and places nothing. That is a stronger check than printing
intent, because ``NOTIONAL.applyMinToMarket`` is true on both configured symbols
and is evaluated against a 5-minute average this script never fetches.

Examples
--------
    python scripts/clear_testnet_holdings.py --symbol BTCUSDT
    python scripts/clear_testnet_holdings.py --symbol BTCUSDT --symbol ETHUSDT
    python scripts/clear_testnet_holdings.py --symbol BTCUSDT --execute
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from decimal import Decimal
from typing import TYPE_CHECKING, Any, Protocol

from trading_bot.config.settings import Secrets
from trading_bot.core.exceptions import ConfigError, TradingBotError
from trading_bot.exchange.models import format_decimal, to_symbol_info
from trading_bot.utils.helpers import round_step_size

if TYPE_CHECKING:  # pragma: no cover - typing only
    from collections.abc import Awaitable, Callable, Sequence

    from trading_bot.core.models import SymbolInfo

#: The only symbols this script may sell. A hardcoded allowlist rather than an
#: open argument: the purpose is exactly these two, and an open seller committed
#: to a trading repository is a general-purpose liquidator. Adding a third is a
#: code change and a gate run, which is correct -- it is a decision.
ALLOWED_SYMBOLS = frozenset({"BTCUSDT", "ETHUSDT"})

#: Matches the shipped ``config.yaml`` defaults. Hardcoded rather than read,
#: because this script deliberately loads no config: a value that cannot be
#: configured cannot be configured wrongly.
_RECV_WINDOW_MS = 5000
_REQUEST_TIMEOUT_S = 10.0

_SIDE_SELL = "SELL"
_TYPE_MARKET = "MARKET"


class TestnetAPI(Protocol):
    """The EXACT library surface this script uses -- the write-surface whitelist.

    Declared as a Protocol rather than described in a comment so **mypy
    enforces it**: reaching for a method not listed here fails the type gate
    rather than a review. It also lets the tests supply a fake without a
    network.

    **Exactly one member writes: :meth:`order_market_sell`.**
    ``create_test_order`` posts to ``order/test``, which validates and places
    nothing. Everything else reads.
    """

    testnet: bool

    async def get_account(self, **params: Any) -> dict[str, Any]: ...
    async def get_symbol_info(self, symbol: str) -> dict[str, Any] | None: ...
    async def get_symbol_ticker(self, **params: Any) -> dict[str, Any]: ...
    async def get_open_orders(self, **params: Any) -> list[dict[str, Any]]: ...
    async def v3_get_open_order_list(self, **params: Any) -> list[dict[str, Any]]: ...
    async def create_test_order(self, **params: Any) -> dict[str, Any]: ...
    async def order_market_sell(self, **params: Any) -> dict[str, Any]: ...
    async def close_connection(self) -> None: ...


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="clear-testnet-holdings",
        description="Sell a Binance Spot TESTNET base holding. Testnet only, dry run by default.",
    )
    parser.add_argument(
        "--symbol",
        action="append",
        required=True,
        metavar="SYMBOL",
        help=(
            "Symbol to clear; repeatable. Required, and validated against the allowlist "
            f"({', '.join(sorted(ALLOWED_SYMBOLS))}). There is no implicit 'all'."
        ),
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Actually place the market sells. Without it every sale is validated only.",
    )
    return parser


def validate_symbols(requested: Sequence[str]) -> list[str]:
    """Upper-case and check ``requested`` against :data:`ALLOWED_SYMBOLS`.

    Raises rather than skipping: a symbol outside the allowlist is a mistake at
    the call site, not a market state, and quietly ignoring it would report
    success for a holding nobody cleared.
    """
    symbols = [name.strip().upper() for name in requested if name.strip()]
    if not symbols:
        raise ConfigError("no symbols given; --symbol is required and takes a symbol name")
    unknown = [name for name in symbols if name not in ALLOWED_SYMBOLS]
    if unknown:
        raise ConfigError(
            f"refusing {', '.join(unknown)}: this script sells only "
            f"{', '.join(sorted(ALLOWED_SYMBOLS))}. Adding a symbol is a code change."
        )
    # Preserve order, drop repeats: `--symbol BTCUSDT --symbol BTCUSDT` should
    # sell once, not twice.
    return list(dict.fromkeys(symbols))


def _testnet_credentials(secrets: Secrets | None = None) -> tuple[str, str]:
    """The TESTNET key pair, and never the live one.

    **This is not ``Settings.binance_credentials()`` and must not become it.**
    That function reads ``binance_api_key`` when the testnet slot is empty,
    which is a sensible fallback for a read-only probe and the wrong behaviour
    for a script whose only action is a sale. Refusing here means the live
    credential is never in memory on this path.

    ``secrets`` is injectable so the tests can express a populated live slot
    beside an empty testnet slot without touching ``.env``.
    """
    resolved = Secrets() if secrets is None else secrets
    key = resolved.binance_testnet_api_key
    secret = resolved.binance_testnet_api_secret
    if not key or not secret:
        raise ConfigError(
            "BINANCE_TESTNET_API_KEY and BINANCE_TESTNET_API_SECRET must both be set. "
            "This script reads the testnet slot only and will not fall back to the live "
            "keys, so a blank testnet slot is a refusal rather than a live connection."
        )
    return key, secret


async def build_client(
    create: Callable[..., Awaitable[TestnetAPI]],
    *,
    secrets: Secrets | None = None,
) -> TestnetAPI:
    """Construct the Testnet client. ``testnet=True`` is a literal, not a variable.

    ``create`` is injected so the tests can assert what is passed without a
    network call. Production hands it ``AsyncClient.create``.

    The post-construction check reads ``client.testnet``, which the library
    assigns once in ``__init__`` and never reassigns -- so a true reading means
    every signed call resolves to ``https://testnet.binance.vision``.
    """
    api_key, api_secret = _testnet_credentials(secrets)
    client = await create(
        api_key=api_key,
        api_secret=api_secret,
        testnet=True,
        requests_params={"timeout": _REQUEST_TIMEOUT_S},
    )
    if client.testnet is not True:
        raise ConfigError(
            "refusing to continue: the constructed client does not report testnet=True, "
            "so a signed call would not be guaranteed to reach the Testnet endpoint"
        )
    return client


def free_balance(account: dict[str, Any], asset: str) -> Decimal:
    """Free balance for ``asset``, as ``Decimal``. Absent means zero.

    ``str`` -> ``Decimal`` at the ingest boundary, matching the mappers'
    ``_dec``. No float is created anywhere on this path, so no float can reach
    a quantity.
    """
    for entry in account.get("balances", ()):
        if entry.get("asset", "").upper() == asset.upper():
            return Decimal(str(entry["free"]))
    return Decimal(0)


def plan_sale(info: SymbolInfo, *, free: Decimal, price: Decimal) -> tuple[Decimal, Decimal, bool]:
    """Return ``(quantity, remainder, remainder_is_dust)`` for one holding.

    Quantity is rounded **DOWN** to ``effective_step_size`` -- the coarser of
    ``LOT_SIZE`` and ``MARKET_LOT_SIZE``, which is what bounds a MARKET order.
    Down rather than up because a quantity above the free balance is unfillable;
    the cost is a residue strictly smaller than one step.

    The residue's dust test is the same comparison
    ``_snapshot_unmanaged_holdings`` makes, in the same direction and with the
    same strictness: ``value < min_notional`` is dust, and the strict side is
    the dust side. That is what decides whether one pass clears the holding.

    MEASURED at M5g-025: ``MARKET_LOT_SIZE`` is present and **zeroed** on both
    configured symbols, so the effective step equals the raw ``LOT_SIZE`` step
    and the residue is dust with six- and twenty-fold headroom. This function
    recomputes it per run rather than trusting that, because a filter is the
    venue's to change.
    """
    quantity = round_step_size(free, info.effective_step_size)
    remainder = free - quantity
    return quantity, remainder, remainder * price < info.min_notional


def _sell_params(symbol: str, quantity: Decimal) -> dict[str, Any]:
    """Wire parameters for one market sell.

    ``format_decimal`` rather than ``str``: ``str(Decimal("0.00001"))`` renders
    ``1E-5`` and Binance rejects scientific notation, so a correct quantity can
    still produce a rejected order.
    """
    return {
        "symbol": symbol,
        "quantity": format_decimal(quantity),
        "recvWindow": _RECV_WINDOW_MS,
    }


async def _refuse_on_resting_orders(client: TestnetAPI, symbols: Sequence[str]) -> None:
    """Refuse the whole run if anything rests at the venue.

    **Not tidiness.** A resting SELL locks base, so ``free`` understates the
    holding and the sale would leave a remainder that is not dust while
    reporting success. A live order list is worse: it can fill *after* the sale
    and re-acquire base, silently undoing the clearing. Both are read-only
    checks and both were measured empty on this account, so the refusal costs
    nothing today and guards a state that is real.
    """
    for symbol in symbols:
        resting = await client.get_open_orders(symbol=symbol, recvWindow=_RECV_WINDOW_MS)
        if resting:
            raise ConfigError(
                f"refusing: {len(resting)} order(s) rest on {symbol}. A resting order locks "
                "base, so the free balance understates the holding and one pass would not "
                "clear it. Cancel them yourself, then re-run."
            )
    lists = await client.v3_get_open_order_list(recvWindow=_RECV_WINDOW_MS)
    if lists:
        raise ConfigError(
            f"refusing: {len(lists)} order list(s) are open on this account. One could fill "
            "after the sale and re-acquire base. Resolve them yourself, then re-run."
        )


async def _clear_symbol(
    client: TestnetAPI,
    symbol: str,
    account: dict[str, Any],
    *,
    execute: bool,
) -> bool:
    """Clear one symbol. Returns ``True`` when nothing failed.

    A skip is not a failure: a holding that is already absent or already dust
    needs no sale and reports ``True``. Each skip carries its **own** message,
    because merging them sends an operator to the wrong cause.
    """
    print(f"  {symbol}:")
    raw = await client.get_symbol_info(symbol)
    if raw is None:
        print(f"    UNSUPPORTED: the venue does not list {symbol}")
        return False
    info = to_symbol_info(raw)

    ticker = await client.get_symbol_ticker(symbol=symbol)
    price = Decimal(str(ticker["price"]))
    free = free_balance(account, info.base_asset)

    print(
        f"    free={free} {info.base_asset}  last={price}  "
        f"effective_step={info.effective_step_size}  min_qty={info.effective_min_qty}  "
        f"min_notional={info.min_notional}"
    )

    if free == 0:
        print(f"    SKIP: no free {info.base_asset} to sell")
        return True

    quantity, remainder, dust = plan_sale(info, free=free, price=price)
    verdict = "DUST" if dust else "NOT DUST"
    print(
        f"    sell={quantity}  projected remainder={remainder} "
        f"(worth {remainder * price}) vs min_notional={info.min_notional} -> {verdict}"
    )
    if not dust:
        print(
            "    WARNING: the residue would still block entries on this symbol. "
            "One pass will not clear it; report this rather than re-running."
        )

    if quantity < info.effective_min_qty:
        print(
            f"    SKIP: {quantity} is below the effective minimum quantity "
            f"{info.effective_min_qty}; the venue would reject it"
        )
        return True
    if quantity * price < info.min_notional:
        print(
            f"    SKIP: {quantity} at {price} is worth {quantity * price}, below "
            f"min_notional {info.min_notional}; this holding is already dust"
        )
        return True

    params = _sell_params(symbol, quantity)
    await client.create_test_order(side=_SIDE_SELL, type=_TYPE_MARKET, **params)
    print("    validated at the venue (create_test_order accepted it)")

    if not execute:
        print("    DRY RUN: nothing placed. Re-run with --execute to sell.")
        return True

    response = await client.order_market_sell(**params)
    print(
        f"    SOLD: status={response.get('status')} "
        f"executedQty={response.get('executedQty')} orderId={response.get('orderId')}"
    )
    return True


async def _run(symbols: Sequence[str], *, execute: bool) -> int:
    from binance import AsyncClient

    client = await build_client(AsyncClient.create)
    failures: list[str] = []
    try:
        print("Connected to Binance TESTNET (hardcoded; this script has no live path).")
        await _refuse_on_resting_orders(client, symbols)

        account = await client.get_account(recvWindow=_RECV_WINDOW_MS)
        mode = "EXECUTE" if execute else "DRY RUN"
        print(f"Mode: {mode}. Symbols: {', '.join(symbols)}")

        for symbol in symbols:
            # Per-symbol isolation: one failing symbol must not abort the rest,
            # and the failure must name itself or a short report reads as a
            # complete one.
            try:
                if not await _clear_symbol(client, symbol, account, execute=execute):
                    failures.append(symbol)
            except TradingBotError as exc:
                code = getattr(exc, "code", None)
                print(f"    FAILED {symbol}: {type(exc).__name__} code={code}: {exc}")
                failures.append(symbol)
            # Broad on purpose: the library raises its own exception family and
            # a clearing run must report a failure rather than crash out of the
            # loop, leaving the other symbol untouched and unexplained.
            except Exception as exc:
                code = getattr(exc, "code", None)
                print(f"    FAILED {symbol}: {type(exc).__name__} code={code}: {exc}")
                failures.append(symbol)

        if execute:
            after = await client.get_account(recvWindow=_RECV_WINDOW_MS)
            print("Balances after:")
            for symbol in symbols:
                base = symbol.removesuffix("USDT")
                print(f"    {base}  free={free_balance(after, base)}")
    finally:
        await client.close_connection()

    if failures:
        print(f"Completed with failure(s): {', '.join(failures)}", file=sys.stderr)
        return 1
    print("Done.")
    return 0


def main(argv: list[str] | None = None) -> int:
    """Entry point. Returns a process exit code (0 ok, 1 exchange, 2 config)."""
    args = _build_parser().parse_args(argv)
    try:
        symbols = validate_symbols(args.symbol)
    except ConfigError as exc:
        print(f"Configuration error: {exc}", file=sys.stderr)
        return 2

    try:
        return asyncio.run(_run(symbols, execute=args.execute))
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
