"""Tests for :class:`BinanceClient` using an injected async mock.

No network: the underlying ``AsyncClient`` is replaced with an ``AsyncMock`` so
we can assert exactly which method is called with which parameters, that
responses are mapped to domain models, that symbol info is cached, that the
forming last candle is flagged, and that the retry policy behaves differently
for idempotent reads versus order placement.
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any
from unittest.mock import AsyncMock

import aiohttp
import pytest
from binance.exceptions import BinanceAPIException
from freezegun import freeze_time

from trading_bot.core.enums import OrderSide, OrderStatus, OrderType
from trading_bot.core.exceptions import (
    ExchangeAPIError,
    ExchangeConnectionError,
    FilterRejectedError,
    InsufficientBalanceError,
    OrderError,
)
from trading_bot.core.models import OrderRequest, OtocoOrderListRequest, OtoOrderListRequest
from trading_bot.exchange.binance_client import BinanceClient
from trading_bot.exchange.ids import OrderListLeg, parse_client_order_id

# --------------------------------------------------------------------------
# Recorded payloads (trimmed to fields the mappers read)
# --------------------------------------------------------------------------
ACCOUNT = {
    "balances": [
        {"asset": "BTC", "free": "0.00150000", "locked": "0.00000000"},
        {"asset": "USDT", "free": "1000.00000000", "locked": "0.00000000"},
    ]
}
TICKER = {
    "symbol": "BTCUSDT",
    "lastPrice": "65000.50000000",
    "bidPrice": "65000.00000000",
    "askPrice": "65001.00000000",
    "closeTime": 1_700_000_000_123,
}
SYMBOL = {  # step/minQty equal; minNotional 5
    "symbol": "BTCUSDT",
    "baseAsset": "BTC",
    "quoteAsset": "USDT",
    "filters": [
        {"filterType": "PRICE_FILTER", "tickSize": "0.01000000"},
        {"filterType": "LOT_SIZE", "stepSize": "0.00001000", "minQty": "0.00001000"},
        {"filterType": "NOTIONAL", "minNotional": "5.00000000"},
    ],
}
SYMBOL_HIGH_MINQTY = {  # minQty (0.001) larger than step (0.00001)
    "symbol": "BTCUSDT",
    "baseAsset": "BTC",
    "quoteAsset": "USDT",
    "filters": [
        {"filterType": "PRICE_FILTER", "tickSize": "0.01000000"},
        {"filterType": "LOT_SIZE", "stepSize": "0.00001000", "minQty": "0.00100000"},
        {"filterType": "NOTIONAL", "minNotional": "0.00000000"},
    ],
}
SYMBOL_COARSE_MARKET_STEP = {  # MARKET_LOT_SIZE step (0.001) coarser than LOT_SIZE (0.00001)
    "symbol": "BTCUSDT",
    "baseAsset": "BTC",
    "quoteAsset": "USDT",
    "filters": [
        {"filterType": "PRICE_FILTER", "tickSize": "0.01000000"},
        {"filterType": "LOT_SIZE", "stepSize": "0.00001000", "minQty": "0.00001000"},
        {
            "filterType": "MARKET_LOT_SIZE",
            "minQty": "0.00001000",
            "maxQty": "100.00000000",
            "stepSize": "0.00100000",
        },
        {"filterType": "NOTIONAL", "minNotional": "0.00000000"},
    ],
}
SYMBOL_HIGH_MARKET_MINQTY = {  # MARKET_LOT_SIZE minQty (0.001) above LOT_SIZE's (0.00001)
    "symbol": "BTCUSDT",
    "baseAsset": "BTC",
    "quoteAsset": "USDT",
    "filters": [
        {"filterType": "PRICE_FILTER", "tickSize": "0.01000000"},
        {"filterType": "LOT_SIZE", "stepSize": "0.00001000", "minQty": "0.00001000"},
        {
            "filterType": "MARKET_LOT_SIZE",
            "minQty": "0.00100000",
            "maxQty": "100.00000000",
            "stepSize": "0.00001000",
        },
        {"filterType": "NOTIONAL", "minNotional": "0.00000000"},
    ],
}
# Binance kline arrays are positional, and these fixtures deliberately keep that
# raw shape rather than being built by a helper: the mapper under test is what
# turns position into meaning, so a fixture that already knew the field names
# would be testing the helper instead of the mapper. Row 1 is
# open_time / open / high / low / close / volume; row 2 is
# close_time / quote_volume / trades / taker_base / taker_quote / ignore.
# fmt: off
KLINE_1 = [
    1_700_000_000_000, "65000.00", "65100.00", "64950.00", "65050.00", "12.5",
    1_700_000_059_999, "0", 100, "0", "0", "0",
]
KLINE_2 = [
    1_700_000_060_000, "65050.00", "65200.00", "65000.00", "65180.00", "9.1",
    1_700_000_119_999, "0", 80, "0", "0", "0",
]
# fmt: on
ORDER_LIMIT_NEW = {
    "symbol": "BTCUSDT",
    "orderId": 123456,
    "clientOrderId": "myclient-1",
    "transactTime": 1_700_000_000_123,
    "price": "64000.00000000",
    "origQty": "0.00100000",
    "executedQty": "0.00000000",
    "cummulativeQuoteQty": "0.00000000",
    "status": "NEW",
    "type": "LIMIT",
    "side": "BUY",
}
# CAPTURED VERBATIM from M5e's probe 2: `DELETE /api/v3/order` via
# `cancel_order`, Binance Spot TESTNET, symbol BTCUSDT, orderId 3219508,
# 2026-08-15. A plain LIMIT/GTC/BUY placed 40% under the best bid so it could
# not cross, then cancelled from `NEW`; nothing filled. Untrimmed -- all
# sixteen keys, in wire order.
#
# This replaces a COMPOSED fixture, `{**ORDER_LIMIT_NEW, "status": "CANCELED"}`,
# which was a CREATE payload with one key overwritten. It carried no
# `origClientOrderId` at all, so no assertion written against it could have
# failed on the substitution below -- the fixture was unpinnable, not merely
# unpinned.
#
# Fenced because the LAYOUT is the correspondence: `origClientOrderId` second
# carrying OURS, against `clientOrderId` fifth carrying a fresh venue-generated
# value. Regrouping the keys for readability would destroy the one thing this
# fixture exists to show.
# fmt: off
ORDER_CANCELED = {
    "symbol":                  "BTCUSDT",
    "origClientOrderId":       "tb1-BTCUSDT-1786764420000-0-W",
    "orderId":                 3219508,
    "orderListId":             -1,
    "clientOrderId":           "CfM1Bg0XtkHHVaJQAE7J14",
    "transactTime":            1786764481669,
    "price":                   "37863.05000000",
    "origQty":                 "0.00020000",
    "executedQty":             "0.00000000",
    "origQuoteOrderQty":       "0.00000000",
    "cummulativeQuoteQty":     "0.00000000",
    "status":                  "CANCELED",
    "timeInForce":             "GTC",
    "type":                    "LIMIT",
    "side":                    "BUY",
    "selfTradePreventionMode": "EXPIRE_MAKER",
}
# fmt: on
OPEN_ORDER = {
    "symbol": "BTCUSDT",
    "orderId": 111,
    "clientOrderId": "resting-1",
    "price": "64000.00000000",
    "origQty": "0.00200000",
    "executedQty": "0.00000000",
    "cummulativeQuoteQty": "0.00000000",
    "status": "NEW",
    "type": "LIMIT",
    "side": "BUY",
    "time": 1_700_000_000_000,
    "updateTime": 1_700_000_000_000,
}


async def _no_sleep(_seconds: float) -> None:
    """Injectable sleep that makes retries instantaneous."""


def _rate_limit_error() -> BinanceAPIException:
    exc = BinanceAPIException.__new__(BinanceAPIException)
    exc.code = -1003
    exc.status_code = 429
    exc.message = "Too many requests"
    return exc


def _insufficient_balance_error() -> BinanceAPIException:
    exc = BinanceAPIException.__new__(BinanceAPIException)
    exc.code = -2010
    exc.status_code = 400
    exc.message = "Account has insufficient balance for requested action."
    return exc


def _make(client: AsyncMock, **kwargs: Any) -> BinanceClient:
    kwargs.setdefault("sleep", _no_sleep)
    return BinanceClient(client, **kwargs)


def _limit_req() -> OrderRequest:
    return OrderRequest(
        symbol="BTCUSDT",
        side=OrderSide.BUY,
        type=OrderType.LIMIT,
        quantity=Decimal("0.001"),
        price=Decimal("64000.00"),
        client_order_id="myclient-1",
    )


# --------------------------------------------------------------------------
# Account / market data
# --------------------------------------------------------------------------
async def test_get_balances_calls_get_account_and_maps() -> None:
    client = AsyncMock()
    client.get_account.return_value = ACCOUNT
    bc = _make(client)

    balances = await bc.get_balances()

    client.get_account.assert_awaited_once_with(recvWindow=5000)
    assert balances[1].asset == "USDT"
    assert balances[1].free == Decimal("1000.00000000")


async def test_get_ticker_passes_symbol_and_maps() -> None:
    client = AsyncMock()
    client.get_ticker.return_value = TICKER
    bc = _make(client)

    ticker = await bc.get_ticker("BTCUSDT")

    client.get_ticker.assert_awaited_once_with(symbol="BTCUSDT")
    assert ticker.last == Decimal("65000.50")


@freeze_time("2023-11-15 00:00:00")  # after both candles have closed
async def test_get_klines_passes_params_and_all_candles_closed() -> None:
    client = AsyncMock()
    client.get_klines.return_value = [KLINE_1, KLINE_2]
    bc = _make(client)

    candles = await bc.get_klines("BTCUSDT", "1m", limit=2)

    client.get_klines.assert_awaited_once_with(symbol="BTCUSDT", interval="1m", limit=2)
    assert [c.is_closed for c in candles] == [True, True]


@freeze_time("2023-11-14 22:15:00")  # inside the final candle's interval
async def test_get_klines_flags_forming_last_candle() -> None:
    client = AsyncMock()
    client.get_klines.return_value = [KLINE_1, KLINE_2]
    bc = _make(client)

    candles = await bc.get_klines("BTCUSDT", "1m", limit=2)

    assert candles[0].is_closed is True
    assert candles[-1].is_closed is False  # close_time is in the future


# --------------------------------------------------------------------------
# Symbol-info cache
# --------------------------------------------------------------------------
async def test_symbol_info_is_cached_after_first_fetch() -> None:
    client = AsyncMock()
    client.get_symbol_info.return_value = SYMBOL
    bc = _make(client)

    first = await bc.get_symbol_info("BTCUSDT")
    second = await bc.get_symbol_info("BTCUSDT")

    assert first == second
    client.get_symbol_info.assert_awaited_once_with("BTCUSDT")


async def test_refresh_symbol_info_refetches() -> None:
    client = AsyncMock()
    client.get_symbol_info.return_value = SYMBOL
    bc = _make(client)

    await bc.get_symbol_info("BTCUSDT")
    await bc.refresh_symbol_info("BTCUSDT")

    assert client.get_symbol_info.await_count == 2


async def test_unknown_symbol_raises() -> None:
    client = AsyncMock()
    client.get_symbol_info.return_value = None
    bc = _make(client)

    with pytest.raises(ExchangeAPIError):
        await bc.get_symbol_info("NOPEUSDT")


# --------------------------------------------------------------------------
# Orders — happy path and filter enforcement
# --------------------------------------------------------------------------
async def test_create_order_sends_expected_params_and_maps() -> None:
    client = AsyncMock()
    client.create_order.return_value = ORDER_LIMIT_NEW
    bc = _make(client, enforce_filters=False)

    order = await bc.create_order(_limit_req())

    kwargs = client.create_order.await_args.kwargs
    assert kwargs["symbol"] == "BTCUSDT"
    assert kwargs["side"] == "BUY"
    assert kwargs["type"] == "LIMIT"
    assert kwargs["quantity"] == "0.001"
    assert kwargs["price"] == "64000.00"
    assert kwargs["timeInForce"] == "GTC"
    assert kwargs["newClientOrderId"] == "myclient-1"
    assert kwargs["recvWindow"] == 5000
    assert order.order_id == "123456"
    assert order.status is OrderStatus.NEW


async def test_create_order_rounds_to_filters() -> None:
    client = AsyncMock()
    client.get_symbol_info.return_value = SYMBOL
    client.create_order.return_value = ORDER_LIMIT_NEW
    bc = _make(client, enforce_filters=True)

    req = OrderRequest(
        symbol="BTCUSDT",
        side=OrderSide.BUY,
        type=OrderType.LIMIT,
        quantity=Decimal("0.0012345"),
        price=Decimal("64000.017"),
    )
    await bc.create_order(req)

    # Values are rounded DOWN to the filter's precision. Binance's stepSize /
    # tickSize strings carry 8 decimals, so the emitted params carry that exact
    # scale (never more precision than the filter permits).
    kwargs = client.create_order.await_args.kwargs
    assert kwargs["quantity"] == "0.00123000"  # step 0.00001000, floored
    assert kwargs["price"] == "64000.01000000"  # tick 0.01000000, floored
    assert Decimal(kwargs["quantity"]) == Decimal("0.00123")
    assert Decimal(kwargs["price"]) == Decimal("64000.01")


async def test_create_order_rejects_below_min_notional_without_dispatch() -> None:
    client = AsyncMock()
    client.get_symbol_info.return_value = SYMBOL  # minNotional 5
    bc = _make(client, enforce_filters=True)

    req = OrderRequest(
        symbol="BTCUSDT",
        side=OrderSide.BUY,
        type=OrderType.LIMIT,
        quantity=Decimal("0.00001"),
        price=Decimal("100.00"),  # notional 0.001
    )
    with pytest.raises(OrderError):
        await bc.create_order(req)

    client.create_order.assert_not_awaited()


async def test_create_order_rejects_below_min_qty_without_dispatch() -> None:
    client = AsyncMock()
    client.get_symbol_info.return_value = SYMBOL_HIGH_MINQTY  # minQty 0.001
    bc = _make(client, enforce_filters=True)

    req = OrderRequest(
        symbol="BTCUSDT",
        side=OrderSide.BUY,
        type=OrderType.LIMIT,
        quantity=Decimal("0.0005"),
        price=Decimal("64000.00"),
    )
    with pytest.raises(OrderError):
        await bc.create_order(req)

    client.create_order.assert_not_awaited()


async def test_create_order_rejects_an_off_tick_stop_price_without_dispatch() -> None:
    """``stop_price`` is REJECTED where ``price`` is rounded, and the asymmetry
    is the point. ``price`` is derived here; ``stop_price`` arrives from
    ``risk.rules`` already tick-rounded by contract, so an off-tick trigger is
    an upstream contract violation, not a market state.

    Rounding it instead would be worse than leaving the gap: ``ROUND_DOWN`` on a
    long's stop moves it *away* from entry, silently widening the risk past the
    configured budget -- through the component that exists to catch that.
    """
    client = AsyncMock()
    client.get_symbol_info.return_value = SYMBOL  # tickSize 0.01
    bc = _make(client, enforce_filters=True)

    req = OrderRequest(
        symbol="BTCUSDT",
        side=OrderSide.SELL,
        type=OrderType.STOP_LOSS,
        quantity=Decimal("0.001"),
        stop_price=Decimal("63700.0049"),  # not a multiple of 0.01
    )
    with pytest.raises(FilterRejectedError) as excinfo:
        await bc.create_order(req)

    # The venue would have named this filter too; the local refusal and the
    # remote one must read as the same condition.
    assert excinfo.value.filter_name == "PRICE_FILTER"
    client.create_order.assert_not_awaited()


async def test_create_order_accepts_an_on_tick_stop_price_untouched() -> None:
    """The guard must fire only on a genuine violation. Every request from a
    correct upstream is an exact multiple and passes through unchanged -- so
    tightening this check into rejecting valid requests turns this red.
    """
    client = AsyncMock()
    client.get_symbol_info.return_value = SYMBOL  # tickSize 0.01
    client.create_order.return_value = ORDER_LIMIT_NEW
    bc = _make(client, enforce_filters=True)

    req = OrderRequest(
        symbol="BTCUSDT",
        side=OrderSide.SELL,
        type=OrderType.STOP_LOSS,
        quantity=Decimal("0.001"),
        stop_price=Decimal("63700.00"),  # exactly on tick
    )
    await bc.create_order(req)

    assert client.create_order.await_args.kwargs["stopPrice"] == "63700.00"


async def test_create_order_rejects_a_stop_market_below_min_notional() -> None:
    """The exchange evaluates ``stopPrice * quantity`` for a stop-type order,
    and a stop resting below the entry carries the *smaller* notional -- so it
    is the leg rejected first. Skipping the check whenever ``price`` was absent
    sent every stop-type order out unchecked.
    """
    client = AsyncMock()
    client.get_symbol_info.return_value = SYMBOL  # minNotional 5
    bc = _make(client, enforce_filters=True)

    req = OrderRequest(
        symbol="BTCUSDT",
        side=OrderSide.SELL,
        type=OrderType.STOP_LOSS,
        quantity=Decimal("0.00001"),
        stop_price=Decimal("100.00"),  # notional 0.001, far below 5
    )
    with pytest.raises(OrderError, match="below min_notional"):
        await bc.create_order(req)

    client.create_order.assert_not_awaited()


async def test_create_order_allows_a_stop_market_that_clears_min_notional() -> None:
    client = AsyncMock()
    client.get_symbol_info.return_value = SYMBOL  # minNotional 5
    client.create_order.return_value = ORDER_LIMIT_NEW
    bc = _make(client, enforce_filters=True)

    req = OrderRequest(
        symbol="BTCUSDT",
        side=OrderSide.SELL,
        type=OrderType.STOP_LOSS,
        quantity=Decimal("0.001"),
        stop_price=Decimal("64000.00"),  # notional 64, clears 5
    )
    await bc.create_order(req)

    client.create_order.assert_awaited_once()


async def test_a_plain_market_order_is_still_not_notional_checked() -> None:
    """Documented limit, not an oversight. A ``MARKET`` order has no
    client-side price to multiply, and the exchange judges it against a
    5-minute average this method never fetches -- so the check cannot run here
    even though ``NOTIONAL.applyMinToMarket`` is true on both configured
    symbols. It can therefore still be rejected at the venue.
    """
    client = AsyncMock()
    client.get_symbol_info.return_value = SYMBOL  # minNotional 5
    client.create_order.return_value = ORDER_LIMIT_NEW
    bc = _make(client, enforce_filters=True)

    req = OrderRequest(
        symbol="BTCUSDT",
        side=OrderSide.BUY,
        type=OrderType.MARKET,
        quantity=Decimal("0.00001"),  # worth far less than 5 at any real price
    )
    await bc.create_order(req)

    client.create_order.assert_awaited_once()


async def test_create_order_rounds_to_the_effective_step_not_the_raw_lot_step() -> None:
    """``_enforce`` is the last line of defence in front of sizing, so it must
    not be *weaker* than the sizing it re-checks. Sizing rounds to
    ``effective_step_size`` -- the coarser of ``LOT_SIZE`` and
    ``MARKET_LOT_SIZE`` -- and reading the raw step here let a quantity through
    that the sizer would have refused.
    """
    client = AsyncMock()
    client.get_symbol_info.return_value = SYMBOL_COARSE_MARKET_STEP
    client.create_order.return_value = ORDER_LIMIT_NEW
    bc = _make(client, enforce_filters=True)

    req = OrderRequest(
        symbol="BTCUSDT",
        side=OrderSide.BUY,
        type=OrderType.LIMIT,
        quantity=Decimal("0.0012345"),
        price=Decimal("64000.00"),
    )
    await bc.create_order(req)

    # Raw LOT_SIZE would floor this to 0.00123; the market step floors it to 0.001.
    assert client.create_order.await_args.kwargs["quantity"] == "0.00100000"


async def test_create_order_rejects_below_the_effective_min_qty() -> None:
    """Same divergence, the other filter: 0.0005 clears ``LOT_SIZE``'s 0.00001
    minimum and is refused by ``MARKET_LOT_SIZE``'s 0.001. The lot steps are
    equal here on purpose, so the rounding guard cannot fire first and claim
    the credit.
    """
    client = AsyncMock()
    client.get_symbol_info.return_value = SYMBOL_HIGH_MARKET_MINQTY
    bc = _make(client, enforce_filters=True)

    req = OrderRequest(
        symbol="BTCUSDT",
        side=OrderSide.BUY,
        type=OrderType.LIMIT,
        quantity=Decimal("0.0005"),
        price=Decimal("64000.00"),
    )
    with pytest.raises(OrderError, match="below min_qty"):
        await bc.create_order(req)

    client.create_order.assert_not_awaited()


async def test_validate_order_uses_test_endpoint_only() -> None:
    client = AsyncMock()
    client.create_test_order.return_value = {}
    bc = _make(client, enforce_filters=False)

    await bc.validate_order(_limit_req())

    client.create_test_order.assert_awaited_once()
    client.create_order.assert_not_awaited()


async def test_cancel_order_sends_integer_order_id() -> None:
    client = AsyncMock()
    client.cancel_order.return_value = ORDER_CANCELED
    bc = _make(client)

    order = await bc.cancel_order("BTCUSDT", "123456")

    client.cancel_order.assert_awaited_once_with(symbol="BTCUSDT", orderId=123456, recvWindow=5000)
    assert order.status is OrderStatus.CANCELED


async def test_a_cancelled_order_carries_our_id_not_the_venues() -> None:
    """MEASURED on BOTH cancel endpoints: a cancel response reports OUR id in
    `origClientOrderId` and a FRESH VENUE-GENERATED value in `clientOrderId`.

    Reading `clientOrderId` alone hands the caller an identifier it never sent,
    on the one response that confirms the cancel -- and reconciliation is keyed
    off what was REQUESTED, by our own ID, so that is precisely the response it
    cannot afford to mismatch.

    **This is the assertion the previous fixture could not carry.** It was
    `{**ORDER_LIMIT_NEW, "status": "CANCELED"}` -- a create payload with no
    `origClientOrderId` -- so the substitution was not merely unasserted, it was
    unrepresentable. The test above still abstains on it by asserting only
    `status`; this one is what bites.
    """
    client = AsyncMock()
    client.cancel_order.return_value = ORDER_CANCELED
    bc = _make(client)

    order = await bc.cancel_order("BTCUSDT", "3219508")

    assert order.client_order_id == "tb1-BTCUSDT-1786764420000-0-W"
    # Named explicitly rather than left to the equality above: the failure this
    # pins is the venue's id arriving in its place, not merely a wrong string.
    assert order.client_order_id != ORDER_CANCELED["clientOrderId"]


async def test_get_open_orders_without_symbol_omits_symbol_param() -> None:
    client = AsyncMock()
    client.get_open_orders.return_value = [OPEN_ORDER]
    bc = _make(client)

    orders = await bc.get_open_orders()

    client.get_open_orders.assert_awaited_once_with(recvWindow=5000)
    assert orders[0].order_id == "111"


async def test_get_open_orders_with_symbol_includes_symbol_param() -> None:
    client = AsyncMock()
    client.get_open_orders.return_value = []
    bc = _make(client)

    await bc.get_open_orders("BTCUSDT")

    client.get_open_orders.assert_awaited_once_with(recvWindow=5000, symbol="BTCUSDT")


async def test_close_and_context_manager() -> None:
    client = AsyncMock()
    bc = _make(client)

    async with bc as entered:
        assert entered is bc

    client.close_connection.assert_awaited_once()


async def test_close_translates_a_transport_failure() -> None:
    """A transport failure at close arrives classified, not raw.

    ``close()`` is reached from ``live_system``'s unconditional ``finally``
    (``engine/modes.py:635``), so a raw ``aiohttp.ClientError`` here propagates
    over the boot error that caused the teardown -- the masking the nested
    teardown exists to prevent. Four of the five ``close()`` call sites sit in a
    ``finally`` or a failure path, so this is the ordinary case rather than a
    corner.

    ``aiohttp.ClientConnectionError`` rather than a bare ``ConnectionError``
    deliberately: it is the family the defect was recorded against, and the one
    ``translate_binance_error`` is measured on elsewhere in this suite.
    """
    client = AsyncMock()
    client.close_connection.side_effect = aiohttp.ClientConnectionError("session gone")
    bc = _make(client)

    with pytest.raises(ExchangeConnectionError):
        await bc.close()

    # One attempt, not four: `idempotent=False` keeps `ExchangeConnectionError`
    # out of the retry predicate, so no backoff is spent inside a teardown.
    assert client.close_connection.await_count == 1


async def test_close_is_safe_to_call_twice() -> None:
    """A regression guard on our own future code, not on the adapter today.

    ``close()``'s idempotence is **inherited**, not implemented: it rests
    entirely on ``AsyncClient.close_connection()`` tolerating a second call,
    which ``engine/modes.py:69-70`` asserts and whose nested teardown depends
    on -- and **nothing in the unit suite pins it**. This test does, so a
    ``close()`` that later grows state cannot break teardown silently.

    It deliberately does **not** bite on the ``_call`` routing: an ``AsyncMock``
    neither raises nor is routed differently, so it abstains on that mutation by
    construction. That is stated rather than discovered, per the rule that a
    test absent from every mutation's failure set is abstaining, not passing.
    """
    client = AsyncMock()
    bc = _make(client)

    await bc.close()
    await bc.close()  # must not raise

    # Passed through both times: the idempotence is the underlying client's, and
    # papering over it with a "did I already close?" flag would be a second
    # source of truth for a fact that object already owns.
    assert client.close_connection.await_count == 2


# --------------------------------------------------------------------------
# Retry policy
# --------------------------------------------------------------------------
async def test_read_retries_on_connection_error_then_succeeds() -> None:
    client = AsyncMock()
    client.get_ticker.side_effect = [
        ConnectionError("reset"),
        ConnectionError("reset"),
        TICKER,
    ]
    bc = _make(client)  # default 4 attempts

    ticker = await bc.get_ticker("BTCUSDT")

    assert client.get_ticker.await_count == 3
    assert ticker.last == Decimal("65000.50")


async def test_read_exhausts_retries_and_raises_connection_error() -> None:
    client = AsyncMock()
    client.get_ticker.side_effect = ConnectionError("down")
    bc = _make(client, retry_attempts=2)

    with pytest.raises(ExchangeConnectionError):
        await bc.get_ticker("BTCUSDT")

    assert client.get_ticker.await_count == 2


async def test_create_order_retries_on_rate_limit() -> None:
    client = AsyncMock()
    client.create_order.side_effect = [_rate_limit_error(), ORDER_LIMIT_NEW]
    bc = _make(client, enforce_filters=False)

    order = await bc.create_order(_limit_req())

    assert client.create_order.await_count == 2  # retried after 429
    assert order.order_id == "123456"


async def test_create_order_does_not_retry_on_connection_error() -> None:
    client = AsyncMock()
    client.create_order.side_effect = ConnectionError("reset")
    bc = _make(client, enforce_filters=False)

    with pytest.raises(ExchangeConnectionError):
        await bc.create_order(_limit_req())

    # Non-idempotent: a timeout might have landed, so it must NOT be resent.
    assert client.create_order.await_count == 1


async def test_create_order_translates_insufficient_balance() -> None:
    client = AsyncMock()
    client.create_order.side_effect = _insufficient_balance_error()
    bc = _make(client, enforce_filters=False)

    with pytest.raises(InsufficientBalanceError):
        await bc.create_order(_limit_req())

    assert client.create_order.await_count == 1


# --------------------------------------------------------------------------
# Order-list placement
# --------------------------------------------------------------------------
# CAPTURED VERBATIM from M5d's probe 2: `POST /api/v3/orderList/otoco` via
# `v3_post_order_list_otoco`, Binance Spot TESTNET, 2026-08-14, order list
# 91590, placed and cancelled within seconds. Trimmed only by dropping the two
# pending `orderReports` entries, which this mapper does not read -- the
# `orders` array and every list-level field are exactly as returned.
#
# It carries BOTH `orders` (identity triples) and `orderReports` (full orders),
# which is what M5d-066 measured and what makes `to_order_list` -- keyed on
# `orders` -- correct for the placement response as well as the read-back.
# fmt: off
ORDER_LIST_PLACED = {
    "orderListId":       91590,
    "contingencyType":   "OTO",
    "listStatusType":    "EXEC_STARTED",
    "listOrderStatus":   "EXECUTING",
    "listClientOrderId": "tb1-BTCUSDT-1786693560000-0-L",
    "transactionTime":   1786693572160,
    "symbol":            "BTCUSDT",
    "orders": [
        {"symbol": "BTCUSDT", "orderId": 2950175,
         "clientOrderId": "tb1-BTCUSDT-1786693560000-0-W"},
        {"symbol": "BTCUSDT", "orderId": 2950176,
         "clientOrderId": "tb1-BTCUSDT-1786693560000-0-SL"},
        {"symbol": "BTCUSDT", "orderId": 2950177,
         "clientOrderId": "tb1-BTCUSDT-1786693560000-0-TP"},
    ],
    "orderReports": [
        {"symbol": "BTCUSDT", "orderId": 2950175, "orderListId": 91590,
         "clientOrderId": "tb1-BTCUSDT-1786693560000-0-W",
         "transactTime": 1786693572160, "price": "47268.31000000",
         "origQty": "0.00100000", "executedQty": "0.00000000",
         "cummulativeQuoteQty": "0.00000000", "status": "NEW",
         "timeInForce": "GTC", "type": "LIMIT", "side": "BUY",
         "workingTime": 1786693572160, "selfTradePreventionMode": "EXPIRE_MAKER"},
    ],
}
# fmt: on

LIST_BAR = datetime(2026, 8, 14, 12, 0, tzinfo=timezone.utc)


def _otoco_request(**overrides: object) -> OtocoOrderListRequest:
    kwargs: dict[str, object] = {
        "symbol": "BTCUSDT",
        "quantity": Decimal("0.001"),
        "entry_limit": Decimal("47268.31"),
        "stop_price": Decimal("44117.09"),
        "take_profit": Decimal("50419.53"),
        "entry_bar_time": LIST_BAR,
    }
    kwargs.update(overrides)
    return OtocoOrderListRequest(**kwargs)  # type: ignore[arg-type]


def _oto_request(**overrides: object) -> OtoOrderListRequest:
    kwargs: dict[str, object] = {
        "symbol": "BTCUSDT",
        "quantity": Decimal("0.001"),
        "entry_limit": Decimal("47268.31"),
        "stop_price": Decimal("44117.09"),
        "entry_bar_time": LIST_BAR,
    }
    kwargs.update(overrides)
    return OtoOrderListRequest(**kwargs)  # type: ignore[arg-type]


def _list_client(**mock_kwargs: object) -> AsyncMock:
    client = AsyncMock()
    client.get_symbol_info.return_value = SYMBOL
    client.v3_post_order_list_otoco.return_value = ORDER_LIST_PLACED
    client.v3_post_order_list_oto.return_value = ORDER_LIST_PLACED
    for name, value in mock_kwargs.items():
        getattr(client, name).side_effect = value
    return client


async def test_creating_an_otoco_list_posts_the_mapped_params() -> None:
    """The whole M5d chain in one call: request -> enforcement -> mapper ->
    endpoint. The parameter set is section 3's sixteen plus ``recvWindow``."""
    client = _list_client()
    bc = _make(client)

    await bc.create_otoco_order_list(_otoco_request())

    sent = client.v3_post_order_list_otoco.await_args.kwargs
    assert sent["workingType"] == "LIMIT"
    assert sent["workingTimeInForce"] == "FOK"
    assert sent["workingPrice"] == "47268.31"
    assert sent["pendingAboveStopPrice"] == "50419.53"
    assert sent["pendingBelowStopPrice"] == "44117.09"
    assert sent["recvWindow"] == 5000
    assert len(sent) == 17  # section 3's sixteen, plus recvWindow


async def test_creating_an_oto_list_posts_the_plain_pending_prefix() -> None:
    client = _list_client()
    bc = _make(client)

    await bc.create_oto_order_list(_oto_request())

    sent = client.v3_post_order_list_oto.await_args.kwargs
    assert sent["pendingType"] == "STOP_LOSS"
    assert sent["pendingStopPrice"] == "44117.09"
    assert not any(k.startswith(("pendingAbove", "pendingBelow")) for k in sent)
    assert len(sent) == 14  # section 3's thirteen, plus recvWindow


async def test_each_shape_posts_only_to_its_own_endpoint() -> None:
    """ENDPOINT SELECTION, and there is no branch to get it wrong: two methods
    mirroring the two mappers, so the caller chooses by choosing the request
    type. A single method over a union would need an ``else`` that cannot
    occur."""
    client = _list_client()
    bc = _make(client)

    await bc.create_otoco_order_list(_otoco_request())
    assert client.v3_post_order_list_otoco.await_count == 1
    assert client.v3_post_order_list_oto.await_count == 0

    await bc.create_oto_order_list(_oto_request())
    assert client.v3_post_order_list_otoco.await_count == 1
    assert client.v3_post_order_list_oto.await_count == 1


@pytest.mark.parametrize(
    ("endpoint", "call"),
    [
        ("v3_post_order_list_otoco", lambda bc: bc.create_otoco_order_list(_otoco_request())),
        ("v3_post_order_list_oto", lambda bc: bc.create_oto_order_list(_oto_request())),
    ],
    ids=["otoco", "oto"],
)
async def test_a_list_placement_is_not_retried_on_a_connection_error(
    endpoint: str, call: object
) -> None:
    """``idempotent=False``, and this is the write the rule exists for. A
    connection timeout MAY HAVE LANDED, so resending could open a second
    position; the recovery is to QUERY the IDs we would have sent, which Q-C
    section 6 makes derivable without persistence."""
    client = _list_client(**{endpoint: ConnectionError("reset")})
    bc = _make(client)

    with pytest.raises(ExchangeConnectionError):
        await call(bc)  # type: ignore[operator]

    assert getattr(client, endpoint).await_count == 1


async def test_a_list_placement_is_retried_on_a_rate_limit() -> None:
    """A 429 is rejected BEFORE acceptance, so nothing landed and resending is
    safe -- the one exception ``_NON_IDEMPOTENT_RETRY`` admits."""
    client = _list_client()
    client.v3_post_order_list_otoco.side_effect = [_rate_limit_error(), ORDER_LIST_PLACED]
    bc = _make(client)

    await bc.create_otoco_order_list(_otoco_request())

    assert client.v3_post_order_list_otoco.await_count == 2


async def test_filters_are_enforced_before_any_network_call() -> None:
    """An off-tick price is REJECTED, not rounded, and the assertion that earns
    its place is that the endpoint was never reached: enforcement is a
    pre-dispatch gate, not a post-hoc complaint."""
    client = _list_client()
    bc = _make(client)

    with pytest.raises(FilterRejectedError):
        await bc.create_otoco_order_list(_otoco_request(entry_limit=Decimal("47268.315")))

    assert client.v3_post_order_list_otoco.await_count == 0


async def test_the_quantity_is_sized_before_sending() -> None:
    """Enforcement rounds the quantity DOWN to the step and the SENT value is
    the rounded one -- so the wire never carries a quantity the sizer refused."""
    client = _list_client()
    bc = _make(client)

    await bc.create_otoco_order_list(_otoco_request(quantity=Decimal("0.0012345678")))

    sent = client.v3_post_order_list_otoco.await_args.kwargs
    # The step's exponent survives the rounding, so the wire carries
    # "0.00123000" rather than "0.00123". Both are the same number; the literal
    # is asserted because it is what the venue actually receives.
    assert sent["workingQuantity"] == "0.00123000"
    assert sent["pendingQuantity"] == "0.00123000"


async def test_the_placement_response_maps_to_an_order_list() -> None:
    """MEASURED at M5d probe 2: the placement response carries both ``orders``
    and ``orderReports``, and its ``orders`` entries are the same identity
    triples the read-back returns -- which is what makes ``to_order_list``
    correct here without a second mapper."""
    client = _list_client()
    bc = _make(client)

    result = await bc.create_otoco_order_list(_otoco_request())

    assert result.order_list_id == "91590"
    assert result.list_order_status == "EXECUTING"
    assert [e.client_order_id for e in result.orders] == [
        "tb1-BTCUSDT-1786693560000-0-W",
        "tb1-BTCUSDT-1786693560000-0-SL",
        "tb1-BTCUSDT-1786693560000-0-TP",
    ]


async def test_enforcement_can_be_disabled_and_then_nothing_is_checked() -> None:
    """``enforce_filters=False`` is the injected-adapter escape hatch the other
    order paths already have; an off-tick price then reaches the wire."""
    client = _list_client()
    bc = _make(client, enforce_filters=False)

    await bc.create_otoco_order_list(_otoco_request(entry_limit=Decimal("47268.315")))

    assert client.v3_post_order_list_otoco.await_args.kwargs["workingPrice"] == "47268.315"


# --------------------------------------------------------------------------
# Order-list reads: the list read-back and the prefix enumeration
# --------------------------------------------------------------------------
# CAPTURED from M5d probe 1: `v3_get_order_list(orderListId=72321)`, TESTNET,
# 2026-08-14. Identity triples, no compare set -- which is why enumeration uses
# `get_open_orders` instead.
# fmt: off
LIST_READBACK = {
    "orderListId":       72321,
    "contingencyType":   "OTO",
    "listStatusType":    "ALL_DONE",
    "listOrderStatus":   "ALL_DONE",
    "listClientOrderId": "tb1-BTCUSDT-1786534736813-0-L",
    "transactionTime":   1786534737092,
    "symbol":            "BTCUSDT",
    "orders": [
        {"symbol": "BTCUSDT", "orderId": 2089800,
         "clientOrderId": "tb1-BTCUSDT-1786534736813-0-W"},
    ],
}

# One of ours, one a human's, one PREFIXED BUT UNPARSEABLE. The third is what
# separates a raw `startswith("tb1-")` filter from a parsing one.
OPEN_ORDERS_MIXED = [
    {**OPEN_ORDER, "orderId": 2950175,
     "clientOrderId": "tb1-BTCUSDT-1786693560000-0-W"},
    {**OPEN_ORDER, "orderId": 999001,
     "clientOrderId": "someHumanOrder"},
    {**OPEN_ORDER, "orderId": 999002,
     "clientOrderId": "tb1-garbage"},
]
# fmt: on


async def test_get_order_list_queries_by_the_venue_id() -> None:
    client = AsyncMock()
    client.v3_get_order_list.return_value = LIST_READBACK
    bc = _make(client)

    result = await bc.get_order_list(order_list_id="72321")

    client.v3_get_order_list.assert_awaited_once_with(recvWindow=5000, orderListId=72321)
    assert result.order_list_id == "72321"
    assert result.list_order_status == "ALL_DONE"


async def test_get_order_list_queries_by_our_derived_id() -> None:
    """The recovery path holds OUR id, derived from seeds, and never the
    venue's -- so querying by `origClientOrderId` is the branch it uses."""
    client = AsyncMock()
    client.v3_get_order_list.return_value = LIST_READBACK
    bc = _make(client)

    await bc.get_order_list(list_client_order_id="tb1-BTCUSDT-1786534736813-0-L")

    client.v3_get_order_list.assert_awaited_once_with(
        recvWindow=5000, origClientOrderId="tb1-BTCUSDT-1786534736813-0-L"
    )


@pytest.mark.parametrize(
    "kwargs",
    [{}, {"order_list_id": "72321", "list_client_order_id": "tb1-x"}],
    ids=["neither", "both"],
)
async def test_get_order_list_requires_exactly_one_identifier(kwargs: dict[str, str]) -> None:
    """The venue accepts either and we do not guess which was meant. Both
    directions are refused, because "both" is as ambiguous as "neither"."""
    client = AsyncMock()
    bc = _make(client)

    with pytest.raises(ValueError, match="exactly one"):
        await bc.get_order_list(**kwargs)

    assert client.v3_get_order_list.await_count == 0


async def test_a_list_read_is_retried_on_a_connection_error() -> None:
    """IDEMPOTENT -- the opposite classification from the placement methods, and
    deliberately so: re-reading cannot create anything, so a connection error is
    retried under `_IDEMPOTENT_RETRY`."""
    client = AsyncMock()
    client.v3_get_order_list.side_effect = [ConnectionError("reset"), LIST_READBACK]
    bc = _make(client)

    await bc.get_order_list(order_list_id="72321")

    assert client.v3_get_order_list.await_count == 2


async def test_the_enumeration_uses_get_open_orders_not_the_list_endpoint() -> None:
    """ENDPOINT SELECTION, settled by measurement: only `get_open_orders`
    returns full order objects carrying section 7's compare set. The list
    read-back returns identity triples (M5d-052) and cannot supply it."""
    client = AsyncMock()
    client.get_open_orders.return_value = OPEN_ORDERS_MIXED
    bc = _make(client)

    await bc.get_own_open_orders("BTCUSDT")

    client.get_open_orders.assert_awaited_once_with(symbol="BTCUSDT", recvWindow=5000)
    assert client.v3_get_order_list.await_count == 0


async def test_the_enumeration_returns_only_our_orders() -> None:
    """Section 6's whole purpose: `get_open_orders` returns EVERY order on the
    symbol, ours and otherwise, and only the prefix distinguishes them."""
    client = AsyncMock()
    client.get_open_orders.return_value = OPEN_ORDERS_MIXED
    bc = _make(client)

    found = await bc.get_own_open_orders("BTCUSDT")

    assert [order.order_id for order in found] == ["2950175"]


async def test_a_prefixed_but_unparseable_id_is_not_ours() -> None:
    """THE TEST THAT SEPARATES THE TWO FILTERS. `tb1-garbage` passes a raw
    `startswith("tb1-")` and fails the parser. Treating a human's order as ours
    is the failure section 6 exists to prevent, and parsing is strictly narrower
    than the prefix it replaces.
    """
    client = AsyncMock()
    client.get_open_orders.return_value = [
        {**OPEN_ORDER, "orderId": 999002, "clientOrderId": "tb1-garbage"}
    ]
    bc = _make(client)

    assert await bc.get_own_open_orders("BTCUSDT") == []


async def test_the_raw_id_survives_so_a_caller_can_re_parse() -> None:
    """WHAT THE NARROWED RETURN TYPE COSTS, AND WHAT IT DOES NOT.

    This method used to hand back each order paired with its parsed identity,
    and section 6's generation recovery -- "take the highest seen" -- was part
    of why it parsed at all. It now returns orders alone, so nobody receives the
    parsed generation.

    The ABILITY survives, which is what this pins: the raw `client_order_id`
    rides on every `Order`, so a caller re-parses and gets the same answer.
    Parsing twice is the price of a port type `core/` can express.
    """
    client = AsyncMock()
    client.get_open_orders.return_value = OPEN_ORDERS_MIXED
    bc = _make(client)

    found = await bc.get_own_open_orders("BTCUSDT")

    assert found[0].client_order_id == "tb1-BTCUSDT-1786693560000-0-W"
    parts = parse_client_order_id(found[0].client_order_id or "")
    assert parts is not None
    assert parts.symbol == "BTCUSDT"
    assert parts.generation == 0
    assert parts.leg is OrderListLeg.WORKING


async def test_an_empty_book_enumerates_to_nothing() -> None:
    """Zero of ours is a state, not an error -- and it is what the recovery path
    reads as "nothing rests"."""
    client = AsyncMock()
    client.get_open_orders.return_value = []
    bc = _make(client)

    assert await bc.get_own_open_orders("BTCUSDT") == []


# --------------------------------------------------------------------------
# The per-call transport bound -- pinned against the REAL library
# --------------------------------------------------------------------------
# These four exercise `python-binance`'s own `_request` and
# `_get_request_kwargs`, with only the aiohttp session replaced. That is
# deliberate and is the point of them: the per-call timeout rides a PRIVATE
# library channel -- `data["requests_params"]` merged into the transport
# kwargs -- which no public API promises. `python-binance` is pinned `==`
# because a pin here encodes a VERIFIED version, and these tests are what make
# that verification real: a version that stopped honouring the channel would
# silently unbound every deadline the executor sets, and instead turns the gate
# red.
#
# No network. `AsyncClient.__init__` and `BaseClient.__init__` were read and do
# no I/O; the real session they build is closed in a `finally`.


class _FakeResponse:
    """The narrow slice of `aiohttp.ClientResponse` that `_handle_response` uses."""

    status = 200

    async def text(self) -> str:
        return "{}"

    async def json(self) -> dict[str, Any]:
        return {}

    async def __aenter__(self) -> _FakeResponse:
        return self

    async def __aexit__(self, *exc: object) -> bool:
        return False


class _RecordingSession:
    """Stands in for the aiohttp session, capturing what `_request` hands it."""

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def _record(self, method: str):  # type: ignore[no-untyped-def]
        def call(url: object, **kwargs: Any) -> _FakeResponse:
            self.calls.append({"method": method, "url": str(url), **kwargs})
            return _FakeResponse()

        return call

    def __getattr__(self, name: str):  # type: ignore[no-untyped-def]
        return self._record(name)


async def _library_client(**client_kwargs: Any):  # type: ignore[no-untyped-def]
    """A real `AsyncClient` with a recording session. Caller closes the real one."""
    from binance import AsyncClient

    client = AsyncClient(api_key="k", api_secret="s", testnet=True, **client_kwargs)
    real_session = client.session
    recorder = _RecordingSession()
    client.session = recorder  # type: ignore[assignment]
    return client, recorder, real_session


async def test_a_per_call_timeout_reaches_the_transport() -> None:
    """The channel works end to end through the library's own `_request`."""
    client, recorder, real_session = await _library_client()
    try:
        await client.get_open_orders(symbol="BTCUSDT", requests_params={"timeout": 2.5})
    finally:
        await real_session.close()

    assert len(recorder.calls) == 1
    assert recorder.calls[0]["timeout"] == 2.5


async def test_nothing_but_timeout_is_injected_into_the_transport_call() -> None:
    """The merge is `kwargs.update()` over EVERY key, so the helper's restraint
    is the only thing standing between us and arbitrary aiohttp arguments. This
    pins the whole keyword set, not just `timeout`'s presence."""
    client, recorder, real_session = await _library_client()
    try:
        await client.get_open_orders(symbol="BTCUSDT", requests_params={"timeout": 2.5})
    finally:
        await real_session.close()

    assert set(recorder.calls[0]) == {"method", "url", "proxy", "headers", "data", "timeout"}


async def test_a_per_call_timeout_overrides_the_client_wide_one() -> None:
    """`exchange.requests_timeout_s` is merged first; the per-call value wins."""
    client, recorder, real_session = await _library_client(requests_params={"timeout": 10})
    try:
        await client.get_open_orders(symbol="BTCUSDT", requests_params={"timeout": 1.5})
        await client.get_open_orders(symbol="BTCUSDT")
    finally:
        await real_session.close()

    assert recorder.calls[0]["timeout"] == 1.5
    assert recorder.calls[1]["timeout"] == 10


async def test_the_per_call_timeout_is_removed_before_the_signature_is_computed() -> None:
    """If `requests_params` survived into the signed payload the signature would
    cover it, and every request carrying a deadline would be rejected. Pinned by
    recomputing the signature over the params WITHOUT it and matching."""
    client, recorder, real_session = await _library_client()
    try:
        await client.get_open_orders(symbol="BTCUSDT", requests_params={"timeout": 2.5})
    finally:
        await real_session.close()

    query = recorder.calls[0]["url"].split("?", 1)[1]
    sent = dict(pair.split("=", 1) for pair in query.split("&"))
    assert "requests_params" not in query
    signature = sent.pop("signature")
    assert signature == client._generate_signature(sent)


# --------------------------------------------------------------------------
# The helper, and the per-call attempt bound
# --------------------------------------------------------------------------
def test_the_timeout_helper_emits_exactly_one_key() -> None:
    """A second key would be forwarded verbatim to aiohttp and fail there with a
    `TypeError` rather than as a domain error."""
    out = BinanceClient._with_call_timeout({"symbol": "BTCUSDT"}, 2.5)

    assert out["requests_params"] == {"timeout": 2.5}
    assert out == {"symbol": "BTCUSDT", "requests_params": {"timeout": 2.5}}


def test_the_timeout_helper_never_hands_back_the_caller_s_dict() -> None:
    """`_get_request_kwargs` deletes `requests_params` from what it is given, so
    a shared or reused mapping would be mutated under its owner."""
    original = {"symbol": "BTCUSDT"}

    bounded = BinanceClient._with_call_timeout(original, 2.5)
    unbounded = BinanceClient._with_call_timeout(original, None)

    assert original == {"symbol": "BTCUSDT"}
    assert bounded is not original
    assert unbounded is not original
    assert unbounded == original


async def test_a_per_call_attempt_bound_changes_the_attempt_count() -> None:
    """The per-call half of the retry budget: a caller on a deadline spends
    fewer attempts than the client's default, without a second client."""
    client = AsyncMock()
    client.get_open_orders.side_effect = ConnectionError("down")
    bc = _make(client)  # client default is 4 attempts

    with pytest.raises(ExchangeConnectionError):
        await bc.get_own_open_orders("BTCUSDT", attempts=2)

    assert client.get_open_orders.await_count == 2


async def test_omitting_the_attempt_bound_keeps_the_client_default() -> None:
    """`None` means "the client's policy", which is what every call site uses
    today -- so nothing changed behaviour when the parameter was added."""
    client = AsyncMock()
    client.get_open_orders.side_effect = ConnectionError("down")
    bc = _make(client)

    with pytest.raises(ExchangeConnectionError):
        await bc.get_own_open_orders("BTCUSDT")

    assert client.get_open_orders.await_count == 4


# --------------------------------------------------------------------------
# The seam between the two: that an adapter method actually USES the helper
# --------------------------------------------------------------------------
# These two exist because a mutation prediction was WRONG. Mutating the helper
# to emit a second key was predicted to fail both the helper test above and the
# transport test above it; it failed only the helper test. The transport tests
# build `requests_params` inline against the library client, so they are not
# downstream of the helper at all -- an expressiveness miss, caught only by the
# prediction being checked against the observation.
#
# The hole that miss exposed is real and is what these close: the helper was
# pinned in isolation, the library channel was pinned in isolation, and NOTHING
# pinned that a call site joins them. A method that quietly stopped calling
# `_with_call_timeout` would have failed no test.


async def test_an_adapter_method_routes_its_timeout_through_the_helper() -> None:
    """The per-call deadline reaches the wire as the channel, from a call site."""
    client = AsyncMock()
    client.get_open_orders.return_value = []
    bc = _make(client)

    await bc.get_own_open_orders("BTCUSDT", timeout_s=2.5)

    client.get_open_orders.assert_awaited_once_with(
        symbol="BTCUSDT", recvWindow=5000, requests_params={"timeout": 2.5}
    )


async def test_an_adapter_method_sends_no_channel_when_it_has_no_deadline() -> None:
    """The other direction: a caller without a deadline must not have one
    injected, or every call would carry a bound nobody chose."""
    client = AsyncMock()
    client.get_open_orders.return_value = []
    bc = _make(client)

    await bc.get_own_open_orders("BTCUSDT")

    client.get_open_orders.assert_awaited_once_with(symbol="BTCUSDT", recvWindow=5000)


# --------------------------------------------------------------------------
# The read surface R13 and the classifier need -- point query and list history
# --------------------------------------------------------------------------
# CAPTURED VERBATIM from M5e's probe 2: `GET /api/v3/order` via `v3_get_order`,
# Binance Spot TESTNET, symbol BTCUSDT, orderId 3219508, 2026-08-15, read
# IMMEDIATELY AFTER the cancel. Untrimmed -- all twenty keys, in wire order.
#
# It is here to pin the asymmetry the reconciler's classifier turns on: the same
# order is ABSENT from `get_open_orders` at this moment and PRESENT here with
# `status` CANCELED. Note `clientOrderId` carries OUR id -- the substitution is
# a property of the cancel RESPONSE, not of the order, so a query is where our
# identifier survives.
#
# `isWorking` is `true` on a cancelled order. It is kept because the wire sent
# it; nothing reads it, and it does not report liveness.
# fmt: off
ORDER_QUERY_CANCELED = {
    "symbol":                  "BTCUSDT",
    "orderId":                 3219508,
    "orderListId":             -1,
    "clientOrderId":           "tb1-BTCUSDT-1786764420000-0-W",
    "price":                   "37863.05000000",
    "origQty":                 "0.00020000",
    "executedQty":             "0.00000000",
    "cummulativeQuoteQty":     "0.00000000",
    "status":                  "CANCELED",
    "timeInForce":             "GTC",
    "type":                    "LIMIT",
    "side":                    "BUY",
    "stopPrice":               "0.00000000",
    "icebergQty":              "0.00000000",
    "time":                    1786764478581,
    "updateTime":              1786764481669,
    "isWorking":               True,
    "workingTime":             1786764478581,
    "origQuoteOrderQty":       "0.00000000",
    "selfTradePreventionMode": "EXPIRE_MAKER",
}
# fmt: on

# CAPTURED VERBATIM from M5e's probe 1: `GET /api/v3/allOrderList` via
# `v3_get_all_order_list`, Binance Spot TESTNET, symbol BTCUSDT, 2026-08-14.
# UNTRIMMED -- all five lists the account held, in wire order, including two
# from M5c's duplicate-order-list probe whose leg ids are its control arms.
#
# Kept whole rather than reduced to the one list under test, per the precedent
# that a fixture trimmed to what the mapper consumes cannot show what the mapper
# ignores. The point it exists to make needs the whole set anyway: list 94177 is
# LIVE, `EXEC_STARTED`/`EXECUTING`, sitting among four `ALL_DONE` ones -- which
# is what lets R13's recovery tell "placed and still working" from "placed and
# already gone" without trusting a point query on a reusable id.
# fmt: off
ALL_ORDER_LISTS = [
    {
        "orderListId":       72324,
        "contingencyType":   "OTO",
        "listStatusType":    "ALL_DONE",
        "listOrderStatus":   "ALL_DONE",
        "listClientOrderId": "tb1-BTCUSDT-1786534736813-0-L",
        "transactionTime":   1786534738385,
        "symbol":            "BTCUSDT",
        "orders": [
            {"symbol": "BTCUSDT", "orderId": 2089811,
             "clientOrderId": "tb1-BTCUSDT-1786534736813-0-W9"},
            {"symbol": "BTCUSDT", "orderId": 2089812,
             "clientOrderId": "tb1-BTCUSDT-1786534736813-0-SL9"},
            {"symbol": "BTCUSDT", "orderId": 2089813,
             "clientOrderId": "tb1-BTCUSDT-1786534736813-0-TP9"},
        ],
    },
    {
        "orderListId":       72325,
        "contingencyType":   "OTO",
        "listStatusType":    "ALL_DONE",
        "listOrderStatus":   "ALL_DONE",
        "listClientOrderId": "tb1-BTCUSDT-1786534736813-0-Lz36",
        "transactionTime":   1786534738568,
        "symbol":            "BTCUSDT",
        "orders": [
            {"symbol": "BTCUSDT", "orderId": 2089814,
             "clientOrderId": "tb1-ovl-xxxxxxxxxxxxxxxxxxxxxxxxxxxx"},
            {"symbol": "BTCUSDT", "orderId": 2089815,
             "clientOrderId": "tb1-BTCUSDT-1786534736813-0-SLz36"},
            {"symbol": "BTCUSDT", "orderId": 2089816,
             "clientOrderId": "tb1-BTCUSDT-1786534736813-0-TPz36"},
        ],
    },
    {
        "orderListId":       72432,
        "contingencyType":   "OTO",
        "listStatusType":    "ALL_DONE",
        "listOrderStatus":   "ALL_DONE",
        "listClientOrderId": "tb1-BTCUSDT-1786535515318-0-L",
        "transactionTime":   1786535515573,
        "symbol":            "BTCUSDT",
        "orders": [
            {"symbol": "BTCUSDT", "orderId": 2093412,
             "clientOrderId": "tb1-BTCUSDT-1786535515318-0-W"},
            {"symbol": "BTCUSDT", "orderId": 2093413,
             "clientOrderId": "tb1-BTCUSDT-1786535515318-0-SL"},
            {"symbol": "BTCUSDT", "orderId": 2093414,
             "clientOrderId": "tb1-BTCUSDT-1786535515318-0-TP"},
        ],
    },
    {
        "orderListId":       91590,
        "contingencyType":   "OTO",
        "listStatusType":    "ALL_DONE",
        "listOrderStatus":   "ALL_DONE",
        "listClientOrderId": "tb1-BTCUSDT-1786693560000-0-L",
        "transactionTime":   1786693572160,
        "symbol":            "BTCUSDT",
        "orders": [
            {"symbol": "BTCUSDT", "orderId": 2950175,
             "clientOrderId": "tb1-BTCUSDT-1786693560000-0-W"},
            {"symbol": "BTCUSDT", "orderId": 2950176,
             "clientOrderId": "tb1-BTCUSDT-1786693560000-0-SL"},
            {"symbol": "BTCUSDT", "orderId": 2950177,
             "clientOrderId": "tb1-BTCUSDT-1786693560000-0-TP"},
        ],
    },
    {
        "orderListId":       94177,
        "contingencyType":   "OTO",
        "listStatusType":    "EXEC_STARTED",
        "listOrderStatus":   "EXECUTING",
        "listClientOrderId": "tb1-BTCUSDT-1786714260000-0-L",
        "transactionTime":   1786714265455,
        "symbol":            "BTCUSDT",
        "orders": [
            {"symbol": "BTCUSDT", "orderId": 3028164,
             "clientOrderId": "tb1-BTCUSDT-1786714260000-0-W"},
            {"symbol": "BTCUSDT", "orderId": 3028165,
             "clientOrderId": "tb1-BTCUSDT-1786714260000-0-SL"},
            {"symbol": "BTCUSDT", "orderId": 3028166,
             "clientOrderId": "tb1-BTCUSDT-1786714260000-0-TP"},
        ],
    },
]
# fmt: on


async def test_get_order_queries_by_the_venue_id() -> None:
    client = AsyncMock()
    client.v3_get_order.return_value = ORDER_QUERY_CANCELED
    bc = _make(client)

    order = await bc.get_order("BTCUSDT", order_id="3219508")

    client.v3_get_order.assert_awaited_once_with(symbol="BTCUSDT", orderId=3219508, recvWindow=5000)
    assert order.order_id == "3219508"


async def test_get_order_queries_by_our_client_order_id() -> None:
    """Our id goes out as `origClientOrderId`, exactly as the list read-back's
    does -- the venue's spelling for "the id the order was created with"."""
    client = AsyncMock()
    client.v3_get_order.return_value = ORDER_QUERY_CANCELED
    bc = _make(client)

    await bc.get_order("BTCUSDT", client_order_id="tb1-BTCUSDT-1786764420000-0-W")

    client.v3_get_order.assert_awaited_once_with(
        symbol="BTCUSDT",
        origClientOrderId="tb1-BTCUSDT-1786764420000-0-W",
        recvWindow=5000,
    )


@pytest.mark.parametrize(
    "kwargs",
    [{}, {"order_id": "3219508", "client_order_id": "tb1-x"}],
    ids=["neither", "both"],
)
async def test_get_order_requires_exactly_one_identifier(kwargs: dict[str, str]) -> None:
    client = AsyncMock()
    bc = _make(client)

    with pytest.raises(ValueError, match="exactly one"):
        await bc.get_order("BTCUSDT", **kwargs)

    assert client.v3_get_order.await_count == 0


async def test_a_point_query_resolves_an_order_enumeration_cannot_see() -> None:
    """The asymmetry the classifier turns on, pinned. `get_open_orders` returned
    `[]` for this very order at this very moment; the point query reports it
    CANCELED, under OUR id."""
    client = AsyncMock()
    client.v3_get_order.return_value = ORDER_QUERY_CANCELED
    bc = _make(client)

    order = await bc.get_order("BTCUSDT", order_id="3219508")

    assert order.status is OrderStatus.CANCELED
    assert order.client_order_id == "tb1-BTCUSDT-1786764420000-0-W"
    assert order.order_list_id is None  # `orderListId` -1 is a sentinel


async def test_get_order_carries_a_per_call_timeout() -> None:
    client = AsyncMock()
    client.v3_get_order.return_value = ORDER_QUERY_CANCELED
    bc = _make(client)

    await bc.get_order("BTCUSDT", order_id="3219508", timeout_s=2.5)

    client.v3_get_order.assert_awaited_once_with(
        symbol="BTCUSDT",
        orderId=3219508,
        recvWindow=5000,
        requests_params={"timeout": 2.5},
    )


async def test_get_all_order_lists_maps_every_list() -> None:
    client = AsyncMock()
    client.v3_get_all_order_list.return_value = ALL_ORDER_LISTS
    bc = _make(client)

    lists = await bc.get_all_order_lists()

    client.v3_get_all_order_list.assert_awaited_once_with(recvWindow=5000)
    assert [x.order_list_id for x in lists] == ["72324", "72325", "72432", "91590", "94177"]
    assert all(len(x.orders) == 3 for x in lists)


async def test_a_live_list_is_distinguishable_from_terminal_ones() -> None:
    """R13's whole purpose: tell "placed and still working" from "placed and
    already gone", without a point query on an id that may have been reused."""
    client = AsyncMock()
    client.v3_get_all_order_list.return_value = ALL_ORDER_LISTS
    bc = _make(client)

    lists = await bc.get_all_order_lists()

    live = [x for x in lists if x.list_order_status == "EXECUTING"]
    assert [x.order_list_id for x in live] == ["94177"]
    assert live[0].list_client_order_id == "tb1-BTCUSDT-1786714260000-0-L"
    assert {x.list_order_status for x in lists if x.order_list_id != "94177"} == {"ALL_DONE"}


async def test_get_all_order_lists_honours_a_per_call_attempt_bound() -> None:
    client = AsyncMock()
    client.v3_get_all_order_list.side_effect = ConnectionError("down")
    bc = _make(client)  # client default is 4 attempts

    with pytest.raises(ExchangeConnectionError):
        await bc.get_all_order_lists(attempts=2)

    assert client.v3_get_all_order_list.await_count == 2


async def test_get_all_order_lists_carries_a_per_call_timeout() -> None:
    client = AsyncMock()
    client.v3_get_all_order_list.return_value = []
    bc = _make(client)

    await bc.get_all_order_lists(timeout_s=2.5)

    client.v3_get_all_order_list.assert_awaited_once_with(
        recvWindow=5000, requests_params={"timeout": 2.5}
    )
