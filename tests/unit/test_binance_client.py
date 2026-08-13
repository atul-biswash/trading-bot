"""Tests for :class:`BinanceClient` using an injected async mock.

No network: the underlying ``AsyncClient`` is replaced with an ``AsyncMock`` so
we can assert exactly which method is called with which parameters, that
responses are mapped to domain models, that symbol info is cached, that the
forming last candle is flagged, and that the retry policy behaves differently
for idempotent reads versus order placement.
"""

from __future__ import annotations

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
from trading_bot.core.models import OrderRequest
from trading_bot.exchange.binance_client import BinanceClient

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
ORDER_CANCELED = {**ORDER_LIMIT_NEW, "status": "CANCELED"}
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
