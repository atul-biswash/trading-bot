"""Tests for the pure Binance <-> domain mappers and error translation.

These are hermetic: recorded Binance JSON in, domain models out, no network and
no mocking. Money assertions use ``Decimal`` throughout.
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

import aiohttp
import pytest
from binance.exceptions import (
    BinanceAPIException,
    BinanceOrderException,
    BinanceRequestException,
)

from trading_bot.core.enums import OrderSide, OrderStatus, OrderType, TimeInForce
from trading_bot.core.exceptions import (
    ExchangeAPIError,
    ExchangeConnectionError,
    InsufficientBalanceError,
    OrderError,
    RateLimitError,
)
from trading_bot.core.models import OrderRequest
from trading_bot.exchange import models as m

# --------------------------------------------------------------------------
# Recorded Binance payloads (trimmed to the fields the mappers read)
# --------------------------------------------------------------------------
ACCOUNT = {
    "makerCommission": 10,
    "balances": [
        {"asset": "BTC", "free": "0.00150000", "locked": "0.00050000"},
        {"asset": "USDT", "free": "1000.00000000", "locked": "50.00000000"},
        {"asset": "ETH", "free": "0.00000000", "locked": "0.00000000"},
    ],
}

SYMBOL_NOTIONAL = {
    "symbol": "BTCUSDT",
    "baseAsset": "BTC",
    "quoteAsset": "USDT",
    "filters": [
        {"filterType": "PRICE_FILTER", "tickSize": "0.01000000"},
        {"filterType": "LOT_SIZE", "stepSize": "0.00001000", "minQty": "0.00001000"},
        {"filterType": "NOTIONAL", "minNotional": "5.00000000"},
    ],
}

SYMBOL_MIN_NOTIONAL = {  # legacy MIN_NOTIONAL spelling
    "symbol": "ETHUSDT",
    "baseAsset": "ETH",
    "quoteAsset": "USDT",
    "filters": [
        {"filterType": "PRICE_FILTER", "tickSize": "0.01000000"},
        {"filterType": "LOT_SIZE", "stepSize": "0.00010000", "minQty": "0.00010000"},
        {"filterType": "MIN_NOTIONAL", "minNotional": "10.00000000"},
    ],
}

# MARKET_LOT_SIZE comes in three shapes and all three are live. Absent is a
# normal symbol; the zeroed shape is what Binance Spot Testnet *and* mainnet
# both return for BTCUSDT (a real maxQty beside zeroed min/step); the populated
# shape is the one where the filter actually binds.
SYMBOL_MARKET_LOT_ZEROED = {
    "symbol": "BTCUSDT",
    "baseAsset": "BTC",
    "quoteAsset": "USDT",
    "filters": [
        {"filterType": "PRICE_FILTER", "tickSize": "0.01000000"},
        {"filterType": "LOT_SIZE", "stepSize": "0.00001000", "minQty": "0.00001000"},
        {"filterType": "NOTIONAL", "minNotional": "5.00000000"},
        {
            "filterType": "MARKET_LOT_SIZE",
            "minQty": "0.00000000",
            "maxQty": "146.30917125",
            "stepSize": "0.00000000",
        },
    ],
}

SYMBOL_MARKET_LOT_POPULATED = {
    "symbol": "BTCUSDT",
    "baseAsset": "BTC",
    "quoteAsset": "USDT",
    "filters": [
        {"filterType": "PRICE_FILTER", "tickSize": "0.01000000"},
        {"filterType": "LOT_SIZE", "stepSize": "0.00001000", "minQty": "0.00001000"},
        {"filterType": "NOTIONAL", "minNotional": "5.00000000"},
        {
            "filterType": "MARKET_LOT_SIZE",
            "minQty": "0.00100000",
            "maxQty": "100.00000000",
            "stepSize": "0.00100000",
        },
    ],
}

TICKER_24H = {
    "symbol": "BTCUSDT",
    "lastPrice": "65000.50000000",
    "bidPrice": "65000.00000000",
    "askPrice": "65001.00000000",
    "closeTime": 1_700_000_000_123,
}

# Binance kline arrays are positional, and these fixtures deliberately keep that
# raw shape rather than being built by a helper: `to_candle` is precisely what
# turns position into meaning, so a fixture that already knew the field names
# would be testing the helper instead of the mapper. Row 1 is
# open_time / open / high / low / close / volume; row 2 is
# close_time / quote_volume / trades / taker_base / taker_quote / ignore.
# fmt: off
KLINE_1 = [
    1_700_000_000_000, "65000.00", "65100.00", "64950.00", "65050.00", "12.50000000",
    1_700_000_059_999, "812345.6", 100, "6.0", "390000.0", "0",
]
KLINE_2 = [
    1_700_000_060_000, "65050.00", "65200.00", "65000.00", "65180.00", "9.10000000",
    1_700_000_119_999, "593210.1", 80, "4.5", "292000.0", "0",
]
# fmt: on

# Recorded WebSocket kline events. Times/OHLCV mirror KLINE_1 so the WS and REST
# mappers can be cross-checked for agreement. The "k" object nests the bar; "x"
# is the finality flag.
#
# Like KLINE_1/KLINE_2 above, the "k" object keeps the wire's single-letter keys
# rather than being built from named fields: `to_candle_from_ws` is what
# translates them, so a fixture that already spelled them out would be testing
# the translation with itself. Grouped by meaning, one concern per row --
# t/T: start & close time · s/i: symbol & interval · f/L: first & last trade id ·
# o/c/h/l: OHLC · v/n/x: base volume, trade count, finality ·
# q/V/Q/B: quote volume, taker base, taker quote, ignore.
# fmt: off
WS_KLINE_CLOSED = {  # a *final* bar (x == true) — the only kind handlers should see
    "e": "kline",
    "E": 1_700_000_060_001,
    "s": "BTCUSDT",
    "k": {
        "t": 1_700_000_000_000, "T": 1_700_000_059_999,
        "s": "BTCUSDT", "i": "1m",
        "f": 100, "L": 200,
        "o": "65000.00", "c": "65050.00", "h": "65100.00", "l": "64950.00",
        "v": "12.50000000", "n": 100, "x": True,
        "q": "812345.6", "V": "6.0", "Q": "390000.0", "B": "0",
    },
}

WS_KLINE_FORMING = {  # a still-forming bar (x == false)
    "e": "kline",
    "E": 1_700_000_030_000,
    "s": "BTCUSDT",
    "k": {
        "t": 1_700_000_000_000, "T": 1_700_000_059_999,
        "s": "BTCUSDT", "i": "1m",
        "f": 100, "L": 150,
        "o": "65000.00", "c": "65010.00", "h": "65020.00", "l": "64990.00",
        "v": "6.20000000", "n": 51, "x": False,
        "q": "402000.0", "V": "3.0", "Q": "195000.0", "B": "0",
    },
}
# fmt: on

# The same closed event as delivered by a *combined* (multiplex) stream.
WS_KLINE_COMBINED = {"stream": "btcusdt@kline_1m", "data": WS_KLINE_CLOSED}

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
    "fills": [],
}

ORDER_MARKET_FILLED = {
    "symbol": "BTCUSDT",
    "orderId": 123457,
    "clientOrderId": "myclient-2",
    "transactTime": 1_700_000_000_456,
    "price": "0.00000000",
    "origQty": "0.00100000",
    "executedQty": "0.00100000",
    "cummulativeQuoteQty": "65.05000000",
    "status": "FILLED",
    "type": "MARKET",
    "side": "BUY",
    "fills": [
        {"price": "65050.00", "qty": "0.00100000", "commission": "0.00000100"},
    ],
}

OPEN_ORDER = {  # get_open_orders uses "time"/"updateTime", not "transactTime"
    "symbol": "BTCUSDT",
    "orderId": 111,
    "clientOrderId": "resting-1",
    "price": "64000.00000000",
    "origQty": "0.00200000",
    "executedQty": "0.00050000",
    "cummulativeQuoteQty": "32.00000000",
    "status": "PARTIALLY_FILLED",
    "type": "LIMIT",
    "side": "BUY",
    "time": 1_700_000_000_000,
    "updateTime": 1_700_000_030_000,
}


def _api_error(*, code: int, status: int, message: str) -> BinanceAPIException:
    """Build a BinanceAPIException without depending on its constructor shape."""
    exc = BinanceAPIException.__new__(BinanceAPIException)
    exc.code = code
    exc.status_code = status
    exc.message = message
    return exc


# --------------------------------------------------------------------------
# Balances
# --------------------------------------------------------------------------
def test_to_balances_maps_all_assets_including_zero() -> None:
    balances = m.to_balances(ACCOUNT)
    assert len(balances) == 3
    btc = balances[0]
    assert btc.asset == "BTC"
    assert btc.free == Decimal("0.00150000")
    assert btc.locked == Decimal("0.00050000")
    assert btc.total == Decimal("0.00200000")
    assert balances[2].total == Decimal("0")  # zero balance preserved


def test_to_balances_uses_decimal_not_float() -> None:
    usdt = m.to_balances(ACCOUNT)[1]
    assert isinstance(usdt.free, Decimal)
    assert usdt.free == Decimal("1000.00000000")


# --------------------------------------------------------------------------
# Symbol info
# --------------------------------------------------------------------------
def test_to_symbol_info_extracts_filters() -> None:
    info = m.to_symbol_info(SYMBOL_NOTIONAL)
    assert info.symbol == "BTCUSDT"
    assert info.base_asset == "BTC"
    assert info.quote_asset == "USDT"
    assert info.price_tick == Decimal("0.01")
    assert info.step_size == Decimal("0.00001")
    assert info.min_qty == Decimal("0.00001")
    assert info.min_notional == Decimal("5")


def test_to_symbol_info_accepts_legacy_min_notional() -> None:
    info = m.to_symbol_info(SYMBOL_MIN_NOTIONAL)
    assert info.min_notional == Decimal("10")


def test_to_symbol_info_missing_required_filter_raises() -> None:
    broken = {
        "symbol": "BTCUSDT",
        "baseAsset": "BTC",
        "quoteAsset": "USDT",
        "filters": [{"filterType": "LOT_SIZE", "stepSize": "0.001", "minQty": "0.001"}],
    }
    with pytest.raises(ExchangeAPIError):
        m.to_symbol_info(broken)


# --------------------------------------------------------------------------
# MARKET_LOT_SIZE: optional, and its three live shapes
# --------------------------------------------------------------------------
def test_market_lot_size_absent_is_normal_not_malformed() -> None:
    """An absent MARKET_LOT_SIZE must not raise the way a missing LOT_SIZE does."""
    info = m.to_symbol_info(SYMBOL_NOTIONAL)
    assert info.market_lot is None
    # With no market filter, effective == LOT_SIZE.
    assert info.effective_step_size == Decimal("0.00001")
    assert info.effective_min_qty == Decimal("0.00001")


def test_market_lot_size_zeroed_keeps_a_real_max_qty() -> None:
    """The shape Testnet and mainnet both return: zeroed min/step, live maxQty.

    A uniform "0 means absent" rule would discard the maximum; the per-field
    convention is why ``max_qty`` is parsed rather than folded into the
    effective values.
    """
    info = m.to_symbol_info(SYMBOL_MARKET_LOT_ZEROED)
    assert info.market_lot is not None
    assert info.market_lot.min_qty == Decimal("0")
    assert info.market_lot.step_size == Decimal("0")
    assert info.market_lot.max_qty == Decimal("146.30917125")
    # Zeroed market values can never win the max(), so LOT_SIZE stands.
    assert info.effective_step_size == Decimal("0.00001")
    assert info.effective_min_qty == Decimal("0.00001")


def test_market_lot_size_populated_wins_when_stricter() -> None:
    """The case the conservative rule exists for."""
    info = m.to_symbol_info(SYMBOL_MARKET_LOT_POPULATED)
    assert info.market_lot is not None
    assert info.effective_step_size == Decimal("0.001")  # market step is coarser
    assert info.effective_min_qty == Decimal("0.001")  # market floor is higher
    # The raw LOT_SIZE values are untouched -- effective is derived, not stored.
    assert info.step_size == Decimal("0.00001")
    assert info.min_qty == Decimal("0.00001")


# --------------------------------------------------------------------------
# Ticker
# --------------------------------------------------------------------------
def test_to_ticker_maps_bid_ask_last_and_timestamp() -> None:
    t = m.to_ticker(TICKER_24H)
    assert t.symbol == "BTCUSDT"
    assert t.bid == Decimal("65000.00")
    assert t.ask == Decimal("65001.00")
    assert t.last == Decimal("65000.50")
    assert t.timestamp == datetime(2023, 11, 14, 22, 13, 20, 123000, tzinfo=timezone.utc)
    assert t.mid == Decimal("65000.50")


# --------------------------------------------------------------------------
# Klines
# --------------------------------------------------------------------------
def test_to_candle_maps_ohlcv_and_times() -> None:
    c = m.to_candle(KLINE_1, symbol="BTCUSDT", timeframe="1m")
    assert c.symbol == "BTCUSDT"
    assert c.timeframe == "1m"
    assert c.open == Decimal("65000.00")
    assert c.high == Decimal("65100.00")
    assert c.low == Decimal("64950.00")
    assert c.close == Decimal("65050.00")
    assert c.volume == Decimal("12.5")
    assert c.open_time == datetime(2023, 11, 14, 22, 13, 20, tzinfo=timezone.utc)
    assert c.close_time == datetime(2023, 11, 14, 22, 14, 19, 999000, tzinfo=timezone.utc)
    assert c.is_closed is True  # mapper always marks closed; client flips last


def test_to_candles_preserves_order_and_count() -> None:
    candles = m.to_candles([KLINE_1, KLINE_2], symbol="BTCUSDT", timeframe="1m")
    assert [c.close for c in candles] == [Decimal("65050.00"), Decimal("65180.00")]


# --------------------------------------------------------------------------
# WebSocket kline streams
# --------------------------------------------------------------------------
def test_ws_kline_to_candle_maps_ohlcv_times_and_closed_flag() -> None:
    c = m.ws_kline_to_candle(WS_KLINE_CLOSED)
    assert c.symbol == "BTCUSDT"
    assert c.timeframe == "1m"
    assert c.open == Decimal("65000.00")
    assert c.high == Decimal("65100.00")
    assert c.low == Decimal("64950.00")
    assert c.close == Decimal("65050.00")
    assert c.volume == Decimal("12.5")
    assert c.open_time == datetime(2023, 11, 14, 22, 13, 20, tzinfo=timezone.utc)
    assert c.close_time == datetime(2023, 11, 14, 22, 14, 19, 999000, tzinfo=timezone.utc)
    assert c.is_closed is True  # taken from the wire ("x"), not defaulted


def test_ws_kline_to_candle_reads_forming_flag() -> None:
    c = m.ws_kline_to_candle(WS_KLINE_FORMING)
    assert c.is_closed is False
    assert c.close == Decimal("65010.00")


def test_ws_kline_to_candle_uses_decimal_not_float() -> None:
    c = m.ws_kline_to_candle(WS_KLINE_CLOSED)
    assert isinstance(c.open, Decimal)
    assert isinstance(c.volume, Decimal)
    # A value chosen so a float round-trip would lose precision.
    event = {"k": {**WS_KLINE_CLOSED["k"], "c": "65050.10000001"}}
    assert m.ws_kline_to_candle(event).close == Decimal("65050.10000001")


def test_ws_and_rest_mappers_agree_on_shared_bar() -> None:
    """The WS and REST mappers must yield identical OHLCV/times for one bar.

    ``is_closed`` is the sole intentional difference (the WS ``"x"`` flag is
    authoritative; the REST mapper always marks closed), so it is excluded.
    """
    rest = m.to_candle(KLINE_1, symbol="BTCUSDT", timeframe="1m")
    ws = m.ws_kline_to_candle(WS_KLINE_CLOSED)
    fields = (
        "symbol",
        "timeframe",
        "open_time",
        "close_time",
        "open",
        "high",
        "low",
        "close",
        "volume",
    )
    assert {f: getattr(ws, f) for f in fields} == {f: getattr(rest, f) for f in fields}


def test_unwrap_stream_message_extracts_combined_payload() -> None:
    inner = m.unwrap_stream_message(WS_KLINE_COMBINED)
    assert inner is WS_KLINE_CLOSED
    # ...and the unwrapped event maps to the same candle as the raw one.
    assert m.ws_kline_to_candle(inner) == m.ws_kline_to_candle(WS_KLINE_CLOSED)


def test_unwrap_stream_message_passes_through_single_stream() -> None:
    # A raw event (no "stream" key) is returned unchanged.
    assert m.unwrap_stream_message(WS_KLINE_CLOSED) is WS_KLINE_CLOSED


# --------------------------------------------------------------------------
# Orders (response -> domain)
# --------------------------------------------------------------------------
def test_to_order_limit_new_has_price_and_no_average() -> None:
    o = m.to_order(ORDER_LIMIT_NEW)
    assert o.order_id == "123456"
    assert o.client_order_id == "myclient-1"
    assert o.side is OrderSide.BUY
    assert o.type is OrderType.LIMIT
    assert o.status is OrderStatus.NEW
    assert o.quantity == Decimal("0.001")
    assert o.filled_quantity == Decimal("0")
    assert o.price == Decimal("64000.00")
    assert o.average_price is None
    assert o.created_at == datetime(2023, 11, 14, 22, 13, 20, 123000, tzinfo=timezone.utc)


def test_to_order_market_filled_derives_average_and_nulls_price() -> None:
    o = m.to_order(ORDER_MARKET_FILLED)
    assert o.type is OrderType.MARKET
    assert o.status is OrderStatus.FILLED
    assert o.price is None  # market reports "0.00000000"
    assert o.average_price == Decimal("65050.00")  # 65.05 / 0.001
    assert o.filled_quantity == Decimal("0.001")


def test_to_order_reads_time_when_transacttime_absent() -> None:
    o = m.to_order(OPEN_ORDER)
    assert o.status is OrderStatus.PARTIALLY_FILLED
    assert o.created_at == datetime(2023, 11, 14, 22, 13, 20, tzinfo=timezone.utc)
    assert o.average_price == Decimal("64000.00")  # 32.0 / 0.0005


@pytest.mark.parametrize(
    ("wire_status", "expected"),
    [
        ("PENDING_NEW", OrderStatus.PENDING_NEW),
        ("EXPIRED_IN_MATCH", OrderStatus.EXPIRED_IN_MATCH),
    ],
)
def test_to_order_maps_the_order_list_statuses(wire_status: str, expected: OrderStatus) -> None:
    """``to_order`` calls ``OrderStatus(raw["status"])`` bare, so an unmodelled
    status raises an **untranslated** ``ValueError`` rather than a domain error.
    Both of these arrive on any order-list read-back, so without them no later
    milestone can read one back at all.
    """
    raw = {**ORDER_LIMIT_NEW, "status": wire_status}
    assert m.to_order(raw).status is expected


def test_to_order_reads_stop_price_and_order_list_id() -> None:
    raw = {**ORDER_LIMIT_NEW, "stopPrice": "63100.00000000", "orderListId": 987}
    o = m.to_order(raw)
    assert o.stop_price == Decimal("63100.00")
    assert o.order_list_id == "987"


def test_to_order_treats_the_exchange_sentinels_as_absent() -> None:
    """An ordinary order reports ``stopPrice`` ``"0.00000000"`` and
    ``orderListId`` ``-1``. Neither is a value: a zero trigger price is not a
    price, and ``-1`` is "no list", not list number -1. Carrying either into
    the domain would make every plain order look like a stop order belonging
    to a shared list.
    """
    o = m.to_order({**ORDER_LIMIT_NEW, "stopPrice": "0.00000000", "orderListId": -1})
    assert o.stop_price is None
    assert o.order_list_id is None


def test_to_order_leaves_both_absent_when_the_payload_omits_them() -> None:
    o = m.to_order(ORDER_LIMIT_NEW)  # neither key present
    assert o.stop_price is None
    assert o.order_list_id is None


def test_a_request_states_its_own_time_in_force_over_the_default() -> None:
    """The working leg of an order list must be ``FOK``, and until this field
    existed the request had no way to say so -- the translation default decided
    for it.
    """
    req = OrderRequest(
        symbol="BTCUSDT",
        side=OrderSide.BUY,
        type=OrderType.LIMIT,
        quantity=Decimal("0.001"),
        price=Decimal("64000.00"),
        time_in_force=TimeInForce.FOK,
    )
    assert m.order_request_to_params(req)["timeInForce"] == "FOK"
    # The explicit keyword still loses to the request's own statement.
    assert m.order_request_to_params(req, time_in_force=TimeInForce.GTC)["timeInForce"] == "FOK"


def test_a_request_that_states_nothing_keeps_the_translation_default() -> None:
    req = OrderRequest(
        symbol="BTCUSDT",
        side=OrderSide.BUY,
        type=OrderType.LIMIT,
        quantity=Decimal("0.001"),
        price=Decimal("64000.00"),
    )
    assert m.order_request_to_params(req)["timeInForce"] == "GTC"
    assert m.order_request_to_params(req, time_in_force=TimeInForce.IOC)["timeInForce"] == "IOC"


# --------------------------------------------------------------------------
# OrderRequest -> Binance params
# --------------------------------------------------------------------------
def test_market_order_params_are_minimal() -> None:
    req = OrderRequest(
        symbol="BTCUSDT", side=OrderSide.BUY, type=OrderType.MARKET, quantity=Decimal("0.001")
    )
    params = m.order_request_to_params(req)
    assert params == {"symbol": "BTCUSDT", "side": "BUY", "type": "MARKET", "quantity": "0.001"}
    assert "price" not in params and "timeInForce" not in params


def test_limit_order_params_include_price_and_tif() -> None:
    req = OrderRequest(
        symbol="BTCUSDT",
        side=OrderSide.SELL,
        type=OrderType.LIMIT,
        quantity=Decimal("0.001"),
        price=Decimal("64000.00"),
        client_order_id="cid-1",
    )
    params = m.order_request_to_params(req)
    assert params["price"] == "64000.00"
    assert params["timeInForce"] == "GTC"
    assert params["newClientOrderId"] == "cid-1"


def test_stop_loss_limit_params_include_stop_price() -> None:
    req = OrderRequest(
        symbol="BTCUSDT",
        side=OrderSide.SELL,
        type=OrderType.STOP_LOSS_LIMIT,
        quantity=Decimal("0.001"),
        price=Decimal("63000.00"),
        stop_price=Decimal("63100.00"),
    )
    params = m.order_request_to_params(req)
    assert params["price"] == "63000.00"
    assert params["stopPrice"] == "63100.00"
    assert params["timeInForce"] == "GTC"


def test_stop_loss_market_params_have_stop_but_no_price() -> None:
    req = OrderRequest(
        symbol="BTCUSDT",
        side=OrderSide.SELL,
        type=OrderType.STOP_LOSS,
        quantity=Decimal("0.001"),
        stop_price=Decimal("63100.00"),
    )
    params = m.order_request_to_params(req)
    assert params["stopPrice"] == "63100.00"
    assert "price" not in params and "timeInForce" not in params


def test_limit_order_without_price_raises() -> None:
    req = OrderRequest(
        symbol="BTCUSDT", side=OrderSide.BUY, type=OrderType.LIMIT, quantity=Decimal("0.001")
    )
    with pytest.raises(OrderError):
        m.order_request_to_params(req)


def test_stop_order_without_stop_price_raises() -> None:
    req = OrderRequest(
        symbol="BTCUSDT", side=OrderSide.SELL, type=OrderType.TAKE_PROFIT, quantity=Decimal("0.001")
    )
    with pytest.raises(OrderError):
        m.order_request_to_params(req)


def test_format_decimal_avoids_scientific_notation() -> None:
    assert m.format_decimal(Decimal("1E-3")) == "0.001"
    assert m.format_decimal(Decimal("100")) == "100"
    assert m.format_decimal(Decimal("0.00100000")) == "0.00100000"


# --------------------------------------------------------------------------
# Error translation
# --------------------------------------------------------------------------
def test_rate_limit_by_http_status() -> None:
    exc = _api_error(code=-1000, status=429, message="Too many requests")
    assert isinstance(m.translate_binance_error(exc), RateLimitError)


def test_rate_limit_by_code() -> None:
    exc = _api_error(code=-1003, status=200, message="Too much request weight used")
    assert isinstance(m.translate_binance_error(exc), RateLimitError)


def test_ip_ban_status_418_is_rate_limit() -> None:
    exc = _api_error(code=-1003, status=418, message="IP banned")
    assert isinstance(m.translate_binance_error(exc), RateLimitError)


def test_insufficient_balance_maps_specifically() -> None:
    exc = _api_error(
        code=-2010, status=400, message="Account has insufficient balance for requested action."
    )
    assert isinstance(m.translate_binance_error(exc), InsufficientBalanceError)


def test_filter_failure_maps_to_order_error() -> None:
    exc = _api_error(code=-1013, status=400, message="Filter failure: LOT_SIZE")
    assert isinstance(m.translate_binance_error(exc), OrderError)


def test_generic_api_error_preserves_code() -> None:
    exc = _api_error(code=-1121, status=400, message="Invalid symbol.")
    result = m.translate_binance_error(exc)
    assert isinstance(result, ExchangeAPIError)
    assert result.code == -1121


def test_binance_order_exception_maps_to_order_error() -> None:
    exc = BinanceOrderException(-1013, "Stop price would trigger immediately.")
    assert isinstance(m.translate_binance_error(exc), OrderError)


def test_binance_order_exception_insufficient_balance() -> None:
    exc = BinanceOrderException(-2010, "Account has insufficient balance.")
    assert isinstance(m.translate_binance_error(exc), InsufficientBalanceError)


def test_binance_request_exception_maps_to_api_error() -> None:
    exc = BinanceRequestException("Invalid Response: not json")
    assert isinstance(m.translate_binance_error(exc), ExchangeAPIError)


def test_connection_error_maps_to_connection_error() -> None:
    assert isinstance(
        m.translate_binance_error(aiohttp.ClientConnectionError("down")),
        ExchangeConnectionError,
    )


def test_timeout_maps_to_connection_error() -> None:
    assert isinstance(m.translate_binance_error(TimeoutError()), ExchangeConnectionError)
