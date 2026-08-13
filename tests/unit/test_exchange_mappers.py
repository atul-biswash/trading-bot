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
    ContractViolationError,
    DuplicateOrderError,
    ExchangeAPIError,
    ExchangeConnectionError,
    ExchangeError,
    FilterRejectedError,
    InsufficientBalanceError,
    MalformedRequestError,
    OrderError,
    OrderNotFoundError,
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

# The whole filters array as Binance Spot TESTNET returns it for BTCUSDT --
# measured, not composed, and laid out in wire order with every filter present
# rather than reduced to the four the mapper reads. Reducing it is what hid
# LOT_SIZE.maxQty and NOTIONAL.applyMinToMarket from this suite for five
# phases: a fixture trimmed to what the mapper consumes cannot show what the
# mapper ignores.
#
# Two shapes here are the wire's and must not be tidied. The band multipliers
# arrive UNPADDED -- "2" and "0.5" -- unlike every other decimal on this
# payload, which carries eight places. avgPriceMins, the four maxNum* limits
# and ICEBERG_PARTS.limit arrive as JSON *numbers*, not strings.
# fmt: off
SYMBOL_FULL_TESTNET = {
    "symbol": "BTCUSDT",
    "baseAsset": "BTC",
    "quoteAsset": "USDT",
    "filters": [
        {"filterType": "PRICE_FILTER",
         "minPrice": "0.01000000", "maxPrice": "1000000.00000000",
         "tickSize": "0.01000000"},
        {"filterType": "LOT_SIZE",
         "minQty": "0.00001000", "maxQty": "9000.00000000",
         "stepSize": "0.00001000"},
        {"filterType": "ICEBERG_PARTS", "limit": 100},
        {"filterType": "MARKET_LOT_SIZE",
         "minQty": "0.00000000", "maxQty": "141.67845966",
         "stepSize": "0.00000000"},
        {"filterType": "TRAILING_DELTA",
         "minTrailingAboveDelta": 10, "maxTrailingAboveDelta": 2000,
         "minTrailingBelowDelta": 10, "maxTrailingBelowDelta": 2000},
        {"filterType": "PERCENT_PRICE_BY_SIDE",
         "bidMultiplierUp": "2", "bidMultiplierDown": "0.5",
         "askMultiplierUp": "2", "askMultiplierDown": "0.5",
         "avgPriceMins": 5},
        {"filterType": "NOTIONAL",
         "minNotional": "5.00000000", "applyMinToMarket": True,
         "maxNotional": "9000000.00000000", "applyMaxToMarket": False,
         "avgPriceMins": 5},
        {"filterType": "MAX_NUM_ORDERS", "maxNumOrders": 200},
        {"filterType": "MAX_NUM_ORDER_LISTS", "maxNumOrderLists": 20},
        {"filterType": "MAX_NUM_ALGO_ORDERS", "maxNumAlgoOrders": 5},
        {"filterType": "MAX_NUM_ORDER_AMENDS", "maxNumOrderAmends": 10},
    ],
}
# fmt: on

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


def test_percent_price_by_side_keeps_all_four_multipliers() -> None:
    """Four fields, not two. BTCUSDT and ETHUSDT both report a symmetric band,
    and collapsing to two would encode that symmetry as a property of the
    *filter* rather than of those two symbols. Nothing on the wire promises the
    sides agree.
    """
    info = m.to_symbol_info(SYMBOL_FULL_TESTNET)
    assert info.percent_price is not None
    band = info.percent_price
    assert band.bid_multiplier_up == Decimal("2")
    assert band.bid_multiplier_down == Decimal("0.5")
    assert band.ask_multiplier_up == Decimal("2")
    assert band.ask_multiplier_down == Decimal("0.5")


def test_percent_price_multipliers_parse_exactly_from_the_unpadded_wire_form() -> None:
    """The wire sends ``"2"`` and ``"0.5"``, not the eight-place form every
    other decimal on this payload uses. Both convert exactly, and the value is
    a ratio rather than money -- so it is a plain ``Decimal``.
    """
    band = m.to_symbol_info(SYMBOL_FULL_TESTNET).percent_price
    assert band is not None
    assert band.bid_multiplier_down * Decimal("100") == Decimal("50")  # exact, no 49.999...
    assert band.ask_multiplier_up == 2


def test_avg_price_mins_is_an_int_from_a_json_number() -> None:
    """It arrives as a JSON number, not a string, and it is the interval the
    band-margin question is about -- how far the average can move between the
    bar close that computes a level and the submission judged against it.
    """
    band = m.to_symbol_info(SYMBOL_FULL_TESTNET).percent_price
    assert band is not None
    assert band.avg_price_mins == 5
    assert isinstance(band.avg_price_mins, int)


def test_the_two_order_count_ceilings_are_parsed() -> None:
    """Both are parsed-but-unread, like ``max_qty``. ``MAX_NUM_ORDER_LISTS`` is
    captured precisely because no design document mentions it: under the
    order-list design every protected position *is* a list, so it is a second
    ceiling on the same thing.
    """
    info = m.to_symbol_info(SYMBOL_FULL_TESTNET)
    assert info.max_num_algo_orders == 5  # a protected position costs two
    assert info.max_num_order_lists == 20


def test_the_new_filters_are_optional_like_market_lot_size() -> None:
    """A payload without them is a normal symbol, not a malformed one -- the
    same rule ``MARKET_LOT_SIZE`` already follows, and the reason none of them
    may join ``PRICE_FILTER`` / ``LOT_SIZE`` in raising.
    """
    info = m.to_symbol_info(SYMBOL_NOTIONAL)  # carries none of the three
    assert info.percent_price is None
    assert info.max_num_algo_orders is None
    assert info.max_num_order_lists is None


def test_the_full_testnet_payload_still_maps_the_four_filters_we_read() -> None:
    """The measured payload carries eleven filters and the mapper reads four.
    Parsing it end to end proves the seven it ignores do not disturb the four
    it does -- which a fixture reduced to those four cannot show.
    """
    info = m.to_symbol_info(SYMBOL_FULL_TESTNET)
    assert info.price_tick == Decimal("0.01")
    assert info.step_size == Decimal("0.00001")
    assert info.min_qty == Decimal("0.00001")
    assert info.min_notional == Decimal("5")
    assert info.market_lot is not None
    assert info.market_lot.max_qty == Decimal("141.67845966")


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


def test_filter_failure_maps_to_filter_rejected_with_the_name_captured() -> None:
    """Retargeted at C3 -- the arc-wide ``isinstance`` ruling's first real bite.

    This asserted ``isinstance(result, OrderError)``, which C3 hollows out:
    ``FilterRejectedError`` **is** an ``OrderError``, so the assertion would keep
    passing while exercising nothing. It now asserts the exact type, the captured
    name, and the ancestry the refinement must preserve.
    """
    exc = _api_error(code=-1013, status=400, message="Filter failure: LOT_SIZE")
    result = m.translate_binance_error(exc)
    assert type(result) is FilterRejectedError
    assert result.filter_name == "LOT_SIZE"
    assert isinstance(result, OrderError)


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


# --------------------------------------------------------------------------
# Error translation -- dispatch ORDER, not merely each mapping
#
# The classifier's order is load-bearing and was implicit in an if-ladder until
# it became a rule table. These three pin the order itself, so a reordering
# fails here rather than silently reclassifying a live venue response.
# --------------------------------------------------------------------------
def test_rate_limit_status_wins_over_a_reject_code() -> None:
    """A 429 carrying an order-reject code is a rate limit, not an order error.

    Pins the status guard ahead of the rule table and the reject set. The
    existing status tests pair 418/429 with ``-1003``, where both conditions
    point the same way and the order is unobservable; this one makes them
    disagree.
    """
    exc = _api_error(code=-2010, status=429, message="Too many requests")
    assert isinstance(m.translate_binance_error(exc), RateLimitError)


def test_a_2010_matching_no_rule_falls_through_to_the_reject_set() -> None:
    """``-2010`` is overloaded, and the message is what separates its meanings.

    Both rules are narrow on purpose, so a ``-2010`` carrying a third meaning
    falls past both to the reject set.

    **Retargeted at C1, deliberately.** This test was written at C0 using
    ``"Duplicate order sent."``, whose docstring said it pinned today's
    behaviour "precisely where that change will land, and must be updated
    deliberately rather than drifting". C1 is that change: the duplicate now
    has its own rule, so the fall-through case needs a message that matches
    neither rule, or the test would silently stop testing fall-through while
    still passing -- ``DuplicateOrderError`` is an ``OrderError``.
    """
    exc = _api_error(code=-2010, status=400, message="Some other -2010 condition.")
    result = m.translate_binance_error(exc)
    assert type(result) is OrderError


def test_the_rule_table_declares_its_order() -> None:
    """The table's order is data, and this asserts the data.

    Reordering the rows is the mutation this exists to catch: it produces a
    wrong *classification* rather than an error, which no other test in this
    file would report.

    **The factory is asserted alongside the code, not the code alone.** From C1
    two rows share ``-2010``, so a code-only assertion could no longer tell them
    apart -- which is the moment this test stops being pedantry.
    """
    assert [(rule.code, rule.produces) for rule in m._API_RULES] == [
        (-1003, RateLimitError),
        (-2010, InsufficientBalanceError),
        (-2010, DuplicateOrderError),
        (-2011, OrderNotFoundError),
        (-1013, FilterRejectedError),
        (-1100, MalformedRequestError),
        (-1106, ContractViolationError),
        (-1159, ContractViolationError),
        (-1158, ContractViolationError),
    ]


# --------------------------------------------------------------------------
# Error translation -- the contract group, and the code that is NOT in it
#
# CODE-ONLY rows: no verbatim message text for -1106/-1158/-1159 exists in this
# repository, so these rows key on the code alone, following -1003's precedent.
# The three mandated string tests are therefore UNWRITABLE for this family and
# are not faked -- there is no measured string to map and no rewording to miss.
# --------------------------------------------------------------------------
@pytest.mark.parametrize("code", [-1106, -1159, -1158])
def test_a_contract_code_maps_to_contract_violation_with_the_code_kept(code: int) -> None:
    """Exact type, not ancestry alone, and the code preserved.

    The code is the only identity these errors have: their message text was
    never captured, so what each row MEANS lives in
    ``ContractViolationError``'s docstring and nowhere else.
    """
    exc = _api_error(code=code, status=400, message="whatever the venue said")
    result = m.translate_binance_error(exc)
    assert type(result) is ContractViolationError
    assert result.code == code
    assert not isinstance(result, OrderError)


def test_1128_is_deliberately_unclassified_and_keeps_its_code() -> None:
    """RULED (b): ``-1128`` is NOT classified, and this test is what enforces it.

    Two arguments were rejected and both are instructive. Classifying it with
    the group is an argument from **adjacency** -- it appears beside the other
    three in one sentence of one document, and that is the whole of the case;
    ``EXPIRED_IN_MATCH`` is on the record that moving a meaning requires a
    measurement, not an argument from a name. Measuring it first is not a
    request but a **search**: no call is known to provoke it, forbidden fields
    yield ``-1106``, so finding one is an unbounded discovery loop for a code
    with no consumer.

    Nothing is lost by leaving it: ``ExchangeAPIError`` carries the code, so an
    operator sees ``-1128`` and can look it up. **Arming condition: the first
    time a ``-1128`` is actually observed.**

    Without this test the ruling is recorded and unenforced -- a later hand
    could add ``-1128`` to ``_CONTRACT_VIOLATION_CODES`` and nothing would say
    it had classified a code nobody has ever seen.
    """
    exc = _api_error(code=-1128, status=400, message="whatever the venue said")
    result = m.translate_binance_error(exc)
    assert type(result) is ExchangeAPIError
    assert result.code == -1128


def test_1111_is_unclassified_and_its_code_survives() -> None:
    """The counterpart to ``-1128``'s test, from the opposite direction.

    ``-1128`` was never classified and M5c ruled not to start. ``-1111`` WAS
    classified -- silently, inside ``_ORDER_REJECT_CODES``, by a commit whose
    entire message is "phase 2" -- and was never observed, documented or tested.
    Ruling them differently would have made the ``-1128`` ruling a preference
    rather than a rule.

    **The gain is the identifier surviving**, which is why the code's VALUE is
    asserted and not merely the presence of the attribute: ``OrderError`` takes
    no code and discarded it, ``ExchangeAPIError`` carries it. This is not
    "classify it less" -- it is stop asserting a meaning and start reporting the
    fact.
    """
    exc = _api_error(code=-1111, status=400, message="whatever the venue said")
    result = m.translate_binance_error(exc)
    assert type(result) is ExchangeAPIError
    assert result.code == -1111


# --------------------------------------------------------------------------
# The hierarchy pass -- claims the arc made and never pinned
# --------------------------------------------------------------------------
@pytest.mark.parametrize(
    ("code", "message", "expected"),
    [
        (-1003, "too much request weight used", RateLimitError),
        (-2010, "Account has insufficient balance for requested action.", InsufficientBalanceError),
        (-2010, "Duplicate order sent.", DuplicateOrderError),
        (-2011, "Unknown order sent.", OrderNotFoundError),
        (-1013, "Filter failure: NOTIONAL", FilterRejectedError),
        (-1100, "Illegal characters found in parameter 'symbol'; x", MalformedRequestError),
        (-1106, "whatever the venue said", ContractViolationError),
    ],
)
def test_every_classified_venue_error_preserves_the_code(
    code: int, message: str, expected: type[Exception]
) -> None:
    """The defect the hierarchy pass exists to fix, and it had no test.

    Before the pass, SIX of seven classified outcomes discarded the exchange's
    code while the *unclassified* fallthrough kept it -- so the better we
    classified, the less machine-readable identity survived. An exception
    reaches a log line as ``type(exc).__name__`` plus ``str(exc)``, and for the
    measured families the message is a fixed English sentence containing no
    digits, so an operator correlating with Binance's tables had our vocabulary
    and not theirs.

    Asserts the code's VALUE, not that the attribute exists: the surviving
    identifier is the whole point.
    """
    exc = _api_error(code=code, status=400, message=message)
    result = m.translate_binance_error(exc)
    assert type(result) is expected
    assert result.code == code


def test_duplicate_order_error_is_catchable_without_catching_every_order_error() -> None:
    """M5e's recovery path depends on this and nothing pinned it.

    Q-C section 8 makes ``-2010 'Duplicate order sent.'`` a *success* signal for
    the timed-out-write recovery: a re-place that collides proves the original
    landed and is still working. That is only usable if the duplicate can be
    caught on its own -- catching it via ``OrderError`` would also swallow
    genuine rejections and turn a failure into a success.

    Verified by execution in a Phase 1 report, which is not a test.
    """
    duplicate = _api_error(code=-2010, status=400, message="Duplicate order sent.")
    other = _api_error(code=-2011, status=400, message="Unknown order sent.")

    try:
        raise m.translate_binance_error(duplicate)
    except DuplicateOrderError as exc:
        assert exc.code == -2010
    else:  # pragma: no cover - defensive
        pytest.fail("the duplicate was not catchable as DuplicateOrderError")

    with pytest.raises(OrderNotFoundError):
        try:
            raise m.translate_binance_error(other)
        except DuplicateOrderError:  # pragma: no cover - must not catch
            pytest.fail("except DuplicateOrderError swallowed a -2011")


def test_contract_violation_catches_a_malformed_request() -> None:
    """ "Catch our bug as a class" was inexpressible until this pass.

    Their nearest common ancestor was ``ExchangeError``, which also catches rate
    limits and order rejections. ``-1100`` is a contract violation that happens
    to name a parameter, so it specialises rather than resembles.
    """
    exc = _api_error(code=-1100, status=400, message="Illegal characters found in parameter 'a'; b")
    result = m.translate_binance_error(exc)
    assert type(result) is MalformedRequestError
    assert isinstance(result, ContractViolationError)
    assert result.parameter == "a"
    assert result.code == -1100


def test_a_code_only_row_captures_its_message_at_debug(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """CAPTURE, not detection -- the answer to the guard hole M5c-AC recorded.

    A code-only row has no message expectation, so the loud ERROR guard cannot
    reach it and these codes are the one family without rot detection. There is
    nothing to *detect*; but the message can be RECORDED, and the first one seen
    in the wild is exactly what would let someone write a pattern row and close
    the gap. That makes a permanent hole a self-closing one.
    """
    exc = _api_error(code=-1106, status=400, message="some wording nobody has seen")
    with caplog.at_level("DEBUG", logger=m.__name__):
        m.translate_binance_error(exc)

    records = [r for r in caplog.records if r.name == m.__name__]
    assert len(records) == 1
    assert "some wording nobody has seen" in records[0].getMessage()


def test_a_pattern_row_does_not_capture_at_debug(caplog: pytest.LogCaptureFixture) -> None:
    """The negative case: a capture that fired on every call would capture nothing.

    Pattern rows already know their message, so recording it is noise -- and a
    positive-only test would pass for a log statement placed outside the
    code-only branch entirely.
    """
    exc = _api_error(code=-2010, status=400, message="Duplicate order sent.")
    with caplog.at_level("DEBUG", logger=m.__name__):
        m.translate_binance_error(exc)

    assert [r for r in caplog.records if r.name == m.__name__] == []


def test_a_contract_code_does_not_log(caplog: pytest.LogCaptureFixture) -> None:
    """The guard cannot fire for a code-only row, and this documents the gap.

    The loud guard reports a *pattern* that failed. A row with no pattern always
    returns on its code, so it never reaches the guard -- which means this
    family is the one place in the classifier where a second meaning arriving on
    a known code would be classified as the first with nothing firing. Recorded
    as a finding rather than resolved here.
    """
    exc = _api_error(code=-1106, status=400, message="anything at all")
    with caplog.at_level("ERROR", logger=m.__name__):
        m.translate_binance_error(exc)

    assert [r for r in caplog.records if r.name == m.__name__] == []


# --------------------------------------------------------------------------
# Error translation -- -1100, the family that leaves OrderError
#
# `-1013` is the venue refusing a TRADE; `-1100` is the venue refusing to PARSE.
# Both were OrderError through the reject set, and Q-C section 8 requires them
# to separate sharply: one is a value a caller handles, one is our own bug.
# `MalformedRequestError` therefore sits under ExchangeError, so an
# `except OrderError` written for routine rejections cannot swallow it.
# --------------------------------------------------------------------------
def test_the_measured_malformed_message_maps_with_the_parameter_captured() -> None:
    """MEASURED verbatim, Testnet, 2026-08-12: an over-long client order ID.

    The embedded regex in the tail is deliberately outside the pattern, so the
    fixture carries it to prove the prefix match survives a body full of
    metacharacters.
    """
    exc = _api_error(
        code=-1100,
        status=400,
        message=(
            "Illegal characters found in parameter 'workingClientOrderId'; "
            "legal range is '^[a-zA-Z0-9-_]{1,36}$'."
        ),
    )
    result = m.translate_binance_error(exc)
    assert type(result) is MalformedRequestError
    assert result.parameter == "workingClientOrderId"


def test_a_malformed_request_is_not_an_order_error() -> None:
    """The one family in the classifier that is NOT under ``OrderError``.

    Paired with the exact-type assertion above rather than standing alone: this
    is the assertion that would silently stop biting if the parent changed, and
    it is the whole point of the family, so it is asserted both ways.
    """
    exc = _api_error(
        code=-1100, status=400, message="Illegal characters found in parameter 'symbol'; x"
    )
    result = m.translate_binance_error(exc)
    assert type(result) is MalformedRequestError
    assert not isinstance(result, OrderError)
    assert isinstance(result, ExchangeError)


def test_a_reworded_malformed_message_does_not_map_to_malformed_request() -> None:
    """Prefix-anchored, so a reworded prefix fails it rather than squeezing past."""
    exc = _api_error(code=-1100, status=400, message="Bad characters in parameter 'symbol'.")
    result = m.translate_binance_error(exc)
    assert not isinstance(result, MalformedRequestError)
    assert type(result) is OrderError


def test_a_different_1100_rendering_falls_through_loudly(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """The pattern claims a family MEMBER, not the family -- M5c-X, harder.

    What is measured is ONE rendering of ``-1100``, from one parameter, in one
    failure mode. ``-1100`` is a general malformed-request code and other
    renderings certainly exist. They must fall through to today's behaviour AND
    fire the guard, rather than being claimed by a pattern that never saw them.
    """
    exc = _api_error(code=-1100, status=400, message="Combination of optional parameters invalid.")
    with caplog.at_level("ERROR", logger=m.__name__):
        result = m.translate_binance_error(exc)

    assert type(result) is OrderError
    records = [r for r in caplog.records if r.name == m.__name__]
    assert len(records) == 1
    assert "Combination of optional parameters invalid." in records[0].getMessage()


def test_the_measured_1100_message_does_not_log(caplog: pytest.LogCaptureFixture) -> None:
    """Quiet on the happy path, per the arc's standard."""
    exc = _api_error(
        code=-1100, status=400, message="Illegal characters found in parameter 'symbol'; x"
    )
    with caplog.at_level("ERROR", logger=m.__name__):
        m.translate_binance_error(exc)

    assert [r for r in caplog.records if r.name == m.__name__] == []


# --------------------------------------------------------------------------
# Error translation -- -1013, the first row that CAPTURES
#
# "Filter failure: NOTIONAL" is the first measured message with a variable tail,
# so this row parses rather than anchoring on the whole string. The captured
# spelling is what makes a parsed venue rejection and `_enforce`'s local refusal
# legible as the same condition -- `_enforce` raises filter_name="PRICE_FILTER"
# and the capture yields "PRICE_FILTER" byte-for-byte.
# --------------------------------------------------------------------------
def test_the_captured_filter_name_matches_the_local_refusals_spelling() -> None:
    """The legibility constraint, asserted rather than left to inspection.

    ``BinanceClient._enforce`` raises ``FilterRejectedError(...,
    filter_name="PRICE_FILTER")`` locally. A venue rejection naming the same
    filter must produce the same string, or one condition has two spellings and
    an operator correlating them cannot tell they are the same thing.
    """
    exc = _api_error(code=-1013, status=400, message="Filter failure: PRICE_FILTER")
    result = m.translate_binance_error(exc)
    assert type(result) is FilterRejectedError
    assert result.filter_name == "PRICE_FILTER"


def test_a_reworded_filter_failure_does_not_map_to_filter_rejected() -> None:
    """Anchored either side of the capture, so a reworded prefix or tail fails it."""
    exc = _api_error(code=-1013, status=400, message="Order failed filter: LOT_SIZE")
    result = m.translate_binance_error(exc)
    assert not isinstance(result, FilterRejectedError)
    assert type(result) is OrderError


def test_a_1013_matching_no_rule_falls_through_to_the_reject_set() -> None:
    """``-1013`` with an unrecognised message keeps today's classification."""
    exc = _api_error(code=-1013, status=400, message="Some other -1013 condition.")
    assert type(m.translate_binance_error(exc)) is OrderError


def test_a_filter_name_outside_the_character_class_falls_through_loudly(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """The capture's OWN failure mode, which nothing else pins.

    ``[A-Z_]+`` is justified by the eleven filter names ``exchangeInfo`` reports,
    but their rendering inside a ``-1013`` is measured for ``NOTIONAL`` alone. A
    name carrying anything else -- a digit, a hyphen, lower case -- must fall
    through **loudly**, because silently degrading to a generic order error is
    exactly what the guard exists to prevent.
    """
    exc = _api_error(code=-1013, status=400, message="Filter failure: LOT_SIZE_2")
    with caplog.at_level("ERROR", logger=m.__name__):
        result = m.translate_binance_error(exc)

    assert type(result) is OrderError
    records = [r for r in caplog.records if r.name == m.__name__]
    assert len(records) == 1
    assert "LOT_SIZE_2" in records[0].getMessage()


def test_the_measured_1013_message_does_not_log(caplog: pytest.LogCaptureFixture) -> None:
    """Quiet on the happy path, per the arc's standard."""
    exc = _api_error(code=-1013, status=400, message="Filter failure: NOTIONAL")
    with caplog.at_level("ERROR", logger=m.__name__):
        m.translate_binance_error(exc)

    assert [r for r in caplog.records if r.name == m.__name__] == []


# --------------------------------------------------------------------------
# Error translation -- -2011, the cancel path's routine answer
#
# MEASURED on a real OTO teardown: cancelling the working leg auto-cancelled
# both pending legs, and the follow-up cancels for those two each returned
# "Unknown order sent." So section 4b's cancel step is ONE call, not three, and
# a close path driving three cancels to success would read its own normal
# teardown as two errors. That is why this family is benign rather than
# exceptional -- on a cancel path.
# --------------------------------------------------------------------------
def test_the_measured_unknown_order_message_maps_to_order_not_found() -> None:
    """The exact type AND the ancestry, both asserted, per the arc-wide ruling.

    ``type(...) is`` is the arc's default because every family here is a
    subclass refinement and ``isinstance`` is structurally blind to it. Where
    the subclass relation is genuinely wanted -- as it is here, since ``-2011``
    already classified as an ``OrderError`` and this commit must not move it --
    both are asserted so the intent is visible rather than inferred from the
    weaker one.
    """
    exc = _api_error(code=-2011, status=400, message="Unknown order sent.")
    result = m.translate_binance_error(exc)
    assert type(result) is OrderNotFoundError
    assert isinstance(result, OrderError)


def test_a_reworded_unknown_order_message_does_not_map_to_order_not_found() -> None:
    """Anchored on the whole measured string, so a rewording fails it loudly."""
    exc = _api_error(code=-2011, status=400, message="Unknown order sent for this symbol.")
    result = m.translate_binance_error(exc)
    assert not isinstance(result, OrderNotFoundError)
    assert type(result) is OrderError


def test_a_2011_matching_no_rule_falls_through_to_the_reject_set() -> None:
    """``-2011`` with an unrecognised message keeps today's classification."""
    exc = _api_error(code=-2011, status=400, message="Some other -2011 condition.")
    assert type(m.translate_binance_error(exc)) is OrderError


def test_an_unmatched_2011_message_logs_loudly(caplog: pytest.LogCaptureFixture) -> None:
    """The guard covers every keyed code, and that is asserted per family."""
    exc = _api_error(code=-2011, status=400, message="Some other -2011 condition.")
    with caplog.at_level("ERROR", logger=m.__name__):
        m.translate_binance_error(exc)

    records = [r for r in caplog.records if r.name == m.__name__]
    assert len(records) == 1
    assert "-2011" in records[0].getMessage()


def test_the_measured_2011_message_does_not_log(caplog: pytest.LogCaptureFixture) -> None:
    """Quiet on the happy path: a guard that fired every call would train a skim."""
    exc = _api_error(code=-2011, status=400, message="Unknown order sent.")
    with caplog.at_level("ERROR", logger=m.__name__):
        m.translate_binance_error(exc)

    assert [r for r in caplog.records if r.name == m.__name__] == []


# --------------------------------------------------------------------------
# Error translation -- the -2010 split, and the anti-rot pair per family
#
# `-2010` carries two unrelated meanings, both measured verbatim at M5c. Only
# the message separates them. Each family gets: the measured string maps, and a
# REWORDED NEAR-MISS does not. The near-miss is the one that matters -- a
# pattern loose enough to survive a rewording is a pattern that will silently
# reclassify when Binance rewords.
# --------------------------------------------------------------------------
def test_the_measured_duplicate_message_maps_to_duplicate_order_error() -> None:
    """MEASURED verbatim, Testnet, 2026-08-12 -- single order and order list.

    **Strengthened at C4** from ``isinstance`` to the exact type plus the
    ancestry, matching C2 and C3. The pairing is what makes the ancestry claim
    load-bearing: asserted alone it is blind (see the test below).
    """
    exc = _api_error(code=-2010, status=400, message="Duplicate order sent.")
    result = m.translate_binance_error(exc)
    assert type(result) is DuplicateOrderError
    assert isinstance(result, OrderError)


def test_duplicate_order_error_is_an_order_error() -> None:
    """DOCUMENTATION, NOT COVERAGE -- this assertion is blind by construction.

    It states the intent: the venue did reject an order, so classifying a
    duplicate under ``OrderError`` is a refinement and every existing
    ``except OrderError`` keeps catching it.

    **It pins nothing.** An ancestry-only assertion survives any mutation that
    reclassifies its subject to another descendant of the same base, and this
    one was *proved* blind at C3: a mutation that returned plain ``OrderError``
    for this exact input broke eight tests and left this one passing. The
    assertion it needs in order to bite lives in the test above, which now
    carries both. Kept for the intent it records, marked so no reader counts it
    as protection.
    """
    exc = _api_error(code=-2010, status=400, message="Duplicate order sent.")
    assert isinstance(m.translate_binance_error(exc), OrderError)


def test_a_reworded_duplicate_message_does_not_map_to_duplicate() -> None:
    """The pattern is anchored on the whole measured string, so a rewording fails it.

    This is the anti-rot half. If Binance ever appends to the message, this
    stops matching and the caller gets a generic order error plus a loud log --
    which is the intended failure, and is strictly better than a pattern loose
    enough to keep matching something it no longer understands.
    """
    exc = _api_error(code=-2010, status=400, message="Duplicate order sent for this symbol.")
    result = m.translate_binance_error(exc)
    assert not isinstance(result, DuplicateOrderError)
    assert type(result) is OrderError


def test_a_reworded_balance_message_does_not_map_to_insufficient_balance() -> None:
    """The balance rule is a narrow fragment, and a rewording still has to contain it.

    ``"Account balance is insufficient ..."`` carries the same meaning to a human
    and does not contain the fragment ``"insufficient balance"``, so it falls
    through rather than being silently classified on a guess.
    """
    exc = _api_error(
        code=-2010, status=400, message="Account balance is insufficient for requested action."
    )
    result = m.translate_binance_error(exc)
    assert not isinstance(result, InsufficientBalanceError)
    assert type(result) is OrderError


def test_an_unmatched_message_on_a_keyed_code_logs_loudly(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A silent-reclassification guard whose own failure is silent is worth nothing.

    Selected by logger name rather than by position: ``caplog.at_level`` lowers
    the capture handler's level globally, so any collaborator logging on its own
    lands in the same buffer.
    """
    exc = _api_error(code=-2010, status=400, message="Some unrecognised wording.")
    with caplog.at_level("ERROR", logger=m.__name__):
        m.translate_binance_error(exc)

    records = [r for r in caplog.records if r.name == m.__name__]
    assert len(records) == 1
    assert "-2010" in records[0].getMessage()
    assert "Some unrecognised wording." in records[0].getMessage()


def test_a_matched_message_does_not_log(caplog: pytest.LogCaptureFixture) -> None:
    """The guard must stay quiet on the happy path, or it trains an operator to skim it."""
    exc = _api_error(code=-2010, status=400, message="Duplicate order sent.")
    with caplog.at_level("ERROR", logger=m.__name__):
        m.translate_binance_error(exc)

    assert [r for r in caplog.records if r.name == m.__name__] == []
