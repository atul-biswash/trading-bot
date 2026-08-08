"""Exchange-specific mapping: Binance REST payloads <-> domain models.

Every function here is **pure** and free of I/O: given a Binance response
(already parsed into Python dicts/lists by ``python-binance``) it returns one of
the frozen, ``Decimal``-based domain models from
:mod:`trading_bot.core.models`; given an :class:`OrderRequest` it produces the
keyword arguments for a Binance order call. Keeping these transformations pure
makes them exhaustively testable against recorded JSON with no mocking.

Money is parsed straight from Binance's decimal *strings* into
:class:`decimal.Decimal` — never through ``float`` — so no precision is lost.

:func:`translate_binance_error` maps the library's exception zoo onto the
project's :mod:`trading_bot.core.exceptions` hierarchy so callers reason about
failures in domain terms.
"""

from __future__ import annotations

import asyncio
from collections.abc import Sequence
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any

import aiohttp
from binance.exceptions import (
    BinanceAPIException,
    BinanceOrderException,
    BinanceRequestException,
)

from trading_bot.core.enums import OrderSide, OrderStatus, OrderType, TimeInForce
from trading_bot.core.exceptions import (
    ExchangeAPIError,
    ExchangeConnectionError,
    ExchangeError,
    InsufficientBalanceError,
    OrderError,
    RateLimitError,
    TradingBotError,
)
from trading_bot.core.models import (
    Balance,
    Candle,
    MarketLotSize,
    Order,
    OrderRequest,
    PercentPriceBySide,
    SymbolInfo,
    Ticker,
)

_EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)

# Binance error codes we can classify precisely; anything else falls through to
# a generic ExchangeAPIError that carries the original code.
_RATE_LIMIT_CODE = -1003
_INSUFFICIENT_BALANCE_CODE = -2010
_ORDER_REJECT_CODES = frozenset({-1013, -1100, -1111, -2010, -2011})
_RATE_LIMIT_STATUS = frozenset({429, 418})

# Exceptions the client layer should catch and route through
# translate_binance_error(). Programming errors (KeyError, TypeError, ...) are
# deliberately NOT included so genuine bugs surface instead of being masked.
BINANCE_EXCEPTIONS: tuple[type[Exception], ...] = (
    BinanceAPIException,
    BinanceOrderException,
    BinanceRequestException,
    aiohttp.ClientError,
    asyncio.TimeoutError,
    ConnectionError,
)


# --------------------------------------------------------------------------
# Small conversion primitives
# --------------------------------------------------------------------------
def _dec(value: Any) -> Decimal:
    """Parse a Binance numeric field (usually a string) into ``Decimal``."""
    return Decimal(str(value))


def _opt_dec(value: Any) -> Decimal | None:
    return None if value is None else _dec(value)


def _ms_to_dt(ms: Any) -> datetime:
    """Convert a Binance millisecond epoch into a UTC ``datetime`` (exact)."""
    return _EPOCH + timedelta(milliseconds=int(ms))


def _first_ms(raw: dict[str, Any], *keys: str) -> datetime | None:
    """Return the first present timestamp among ``keys`` as a datetime."""
    for key in keys:
        if raw.get(key) is not None:
            return _ms_to_dt(raw[key])
    return None


def format_decimal(value: Decimal) -> str:
    """Render a ``Decimal`` as a plain (non-scientific) string for the API.

    Binance rejects scientific notation (e.g. ``1E-3``); ``format(value, "f")``
    always yields fixed-point text such as ``"0.001"``.
    """
    return format(value, "f")


# --------------------------------------------------------------------------
# Account / balances
# --------------------------------------------------------------------------
def to_balance(raw: dict[str, Any]) -> Balance:
    return Balance(
        asset=raw["asset"],
        free=_dec(raw["free"]),
        locked=_dec(raw["locked"]),
    )


def to_balances(account: dict[str, Any]) -> list[Balance]:
    """Map a ``get_account`` payload into every asset balance (zeros included).

    The full list is returned faithfully; display-time filtering (e.g. only
    non-zero balances) is the caller's responsibility.
    """
    return [to_balance(b) for b in account.get("balances", [])]


# --------------------------------------------------------------------------
# Symbol info (trading filters)
# --------------------------------------------------------------------------
def _filters_by_type(raw: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {f["filterType"]: f for f in raw.get("filters", [])}


def to_symbol_info(raw: dict[str, Any]) -> SymbolInfo:
    """Map an exchange-info symbol entry into :class:`SymbolInfo`.

    Extracts the trading filters needed to size and round orders. Binance
    renamed ``MIN_NOTIONAL`` to ``NOTIONAL``; both spellings are accepted.
    Raises :class:`ExchangeAPIError` if a mandatory filter is missing.

    ``MARKET_LOT_SIZE``, ``PERCENT_PRICE_BY_SIDE``, ``MAX_NUM_ALGO_ORDERS`` and
    ``MAX_NUM_ORDER_LISTS`` are all **optional**, and absence is a normal symbol
    rather than a malformed payload -- so each is fetched with ``get`` and left
    as ``None``, while ``PRICE_FILTER`` and ``LOT_SIZE`` keep raising.

    The counts arrive as JSON **numbers** and the band multipliers as
    **unpadded strings** (``"2"``, ``"0.5"``), unlike every other decimal on
    this payload; both convert exactly.
    """
    filters = _filters_by_type(raw)
    try:
        price_filter = filters["PRICE_FILTER"]
        lot_size = filters["LOT_SIZE"]
    except KeyError as exc:
        raise ExchangeAPIError(
            f"Malformed symbol info for {raw.get('symbol')!r}: missing {exc.args[0]}"
        ) from exc

    notional = filters.get("NOTIONAL") or filters.get("MIN_NOTIONAL") or {}
    raw_market_lot = filters.get("MARKET_LOT_SIZE")
    market_lot = (
        MarketLotSize(
            min_qty=_dec(raw_market_lot["minQty"]),
            max_qty=_dec(raw_market_lot["maxQty"]),
            step_size=_dec(raw_market_lot["stepSize"]),
        )
        if raw_market_lot is not None
        else None
    )
    raw_percent_price = filters.get("PERCENT_PRICE_BY_SIDE")
    percent_price = (
        PercentPriceBySide(
            bid_multiplier_up=_dec(raw_percent_price["bidMultiplierUp"]),
            bid_multiplier_down=_dec(raw_percent_price["bidMultiplierDown"]),
            ask_multiplier_up=_dec(raw_percent_price["askMultiplierUp"]),
            ask_multiplier_down=_dec(raw_percent_price["askMultiplierDown"]),
            avg_price_mins=int(raw_percent_price["avgPriceMins"]),
        )
        if raw_percent_price is not None
        else None
    )
    algo = filters.get("MAX_NUM_ALGO_ORDERS")
    order_lists = filters.get("MAX_NUM_ORDER_LISTS")
    return SymbolInfo(
        symbol=raw["symbol"],
        base_asset=raw["baseAsset"],
        quote_asset=raw["quoteAsset"],
        price_tick=_dec(price_filter["tickSize"]),
        step_size=_dec(lot_size["stepSize"]),
        min_qty=_dec(lot_size["minQty"]),
        min_notional=_dec(notional.get("minNotional", "0")),
        market_lot=market_lot,
        percent_price=percent_price,
        max_num_algo_orders=None if algo is None else int(algo["maxNumAlgoOrders"]),
        max_num_order_lists=None if order_lists is None else int(order_lists["maxNumOrderLists"]),
    )


# --------------------------------------------------------------------------
# Ticker (24-hour statistics)
# --------------------------------------------------------------------------
def to_ticker(raw: dict[str, Any]) -> Ticker:
    """Map a 24-hour ticker payload into :class:`Ticker`.

    The 24-hour ticker is the single REST call that yields bid, ask, last, and
    an exchange-provided timestamp together.
    """
    return Ticker(
        symbol=raw["symbol"],
        bid=_dec(raw["bidPrice"]),
        ask=_dec(raw["askPrice"]),
        last=_dec(raw["lastPrice"]),
        timestamp=_ms_to_dt(raw["closeTime"]),
    )


# --------------------------------------------------------------------------
# Klines / candles
# --------------------------------------------------------------------------
# Index layout of a Binance kline array.
(
    _K_OPEN_TIME,
    _K_OPEN,
    _K_HIGH,
    _K_LOW,
    _K_CLOSE,
    _K_VOLUME,
    _K_CLOSE_TIME,
) = range(7)


def to_candle(raw: Sequence[Any], *, symbol: str, timeframe: str) -> Candle:
    """Map a single Binance kline array into a :class:`Candle`.

    ``is_closed`` defaults to ``True`` here to keep the mapper pure and
    deterministic; the client flips the final, still-forming candle based on the
    wall clock.
    """
    return Candle(
        symbol=symbol,
        timeframe=timeframe,
        open_time=_ms_to_dt(raw[_K_OPEN_TIME]),
        close_time=_ms_to_dt(raw[_K_CLOSE_TIME]),
        open=_dec(raw[_K_OPEN]),
        high=_dec(raw[_K_HIGH]),
        low=_dec(raw[_K_LOW]),
        close=_dec(raw[_K_CLOSE]),
        volume=_dec(raw[_K_VOLUME]),
    )


def to_candles(raw: Sequence[Sequence[Any]], *, symbol: str, timeframe: str) -> list[Candle]:
    return [to_candle(k, symbol=symbol, timeframe=timeframe) for k in raw]


# --------------------------------------------------------------------------
# WebSocket kline streams
# --------------------------------------------------------------------------
# The streaming kline payload is shaped very differently from the REST kline
# *array* above: it is a JSON object that nests the bar under a ``"k"`` key whose
# fields are single-letter codes. These constants name those codes so the mapper
# reads clearly and the ``"t"``/``"T"`` (open/close time) and ``"v"``/``"V"``
# (volume/taker-buy volume) look-alikes cannot be confused. See the payload in
# ``BinanceSocketManager.kline_socket``'s docstring for the full field list.
_WS_KLINE = "k"  # the nested kline object within a kline event
_WSK_SYMBOL = "s"  # symbol, e.g. "BTCUSDT"
_WSK_INTERVAL = "i"  # interval, e.g. "1m"
_WSK_OPEN_TIME = "t"  # bar start time (ms epoch)
_WSK_CLOSE_TIME = "T"  # bar close time (ms epoch)
_WSK_OPEN = "o"
_WSK_HIGH = "h"
_WSK_LOW = "l"
_WSK_CLOSE = "c"
_WSK_VOLUME = "v"  # base-asset volume
_WSK_IS_CLOSED = "x"  # whether this bar is final


def unwrap_stream_message(msg: dict[str, Any]) -> dict[str, Any]:
    """Return the inner event from a combined-stream envelope, or ``msg`` as-is.

    Binance's *combined* (multiplex) streams wrap every event as
    ``{"stream": "<name>", "data": {<event>}}``, whereas a *single* raw stream
    delivers the event unwrapped. Normalising both to the bare event here lets
    the stream layer map either shape with one code path. A message that carries
    a ``"stream"`` key but no ``"data"`` is malformed and is left to raise
    ``KeyError`` (a bug, not a routine condition), consistent with the other
    mappers in this module.
    """
    if "stream" in msg:
        data: dict[str, Any] = msg["data"]
        return data
    return msg


def ws_kline_to_candle(event: dict[str, Any]) -> Candle:
    """Map a Binance WebSocket kline *event* into a :class:`Candle`.

    ``event`` is the raw kline event (``{"e": "kline", ..., "k": {...}}``); for
    combined/multiplex streams, unwrap the ``{"stream", "data"}`` envelope first
    with :func:`unwrap_stream_message`.

    Unlike the REST :func:`to_candle` — which cannot know whether the most recent
    bar is still forming and so always marks ``is_closed=True`` — the streaming
    payload reports finality directly via the ``"x"`` flag, so ``is_closed`` is
    taken straight from the wire here. Money fields are parsed from Binance's
    decimal *strings* into :class:`~decimal.Decimal`, never through ``float``.
    """
    k = event[_WS_KLINE]
    return Candle(
        symbol=k[_WSK_SYMBOL],
        timeframe=k[_WSK_INTERVAL],
        open_time=_ms_to_dt(k[_WSK_OPEN_TIME]),
        close_time=_ms_to_dt(k[_WSK_CLOSE_TIME]),
        open=_dec(k[_WSK_OPEN]),
        high=_dec(k[_WSK_HIGH]),
        low=_dec(k[_WSK_LOW]),
        close=_dec(k[_WSK_CLOSE]),
        volume=_dec(k[_WSK_VOLUME]),
        is_closed=bool(k[_WSK_IS_CLOSED]),
    )


# --------------------------------------------------------------------------
# Orders
# --------------------------------------------------------------------------
def to_order(raw: dict[str, Any]) -> Order:
    """Map any Binance order payload (create / cancel / query) into :class:`Order`.

    ``average_price`` is derived from the exchange's own fill accounting
    (``cummulativeQuoteQty / executedQty``); it is ``None`` while nothing has
    filled. A market order's reported ``price`` of ``"0.00000000"`` maps to
    ``None`` so the average price is the single source of truth for fill price.
    ``stopPrice`` follows the same convention, for the same reason: an order
    with no trigger reports zero, and a zero trigger price is not a price.

    ``orderListId`` is ``-1`` for an order that belongs to no list. That is a
    sentinel rather than an identity, so it maps to ``None`` -- otherwise every
    ordinary order would appear to belong to list "-1", and a reconciler keyed
    on list membership would group them together.
    """
    executed = _dec(raw.get("executedQty", "0"))
    cummulative = _dec(raw.get("cummulativeQuoteQty", "0"))  # Binance's spelling
    average_price = cummulative / executed if executed > 0 and cummulative > 0 else None

    price = _opt_dec(raw.get("price"))
    if price is not None and price == 0:
        price = None

    stop_price = _opt_dec(raw.get("stopPrice"))
    if stop_price is not None and stop_price == 0:
        stop_price = None

    raw_list_id = raw.get("orderListId")
    order_list_id = None if raw_list_id is None or int(raw_list_id) == -1 else str(raw_list_id)

    return Order(
        order_id=str(raw["orderId"]),
        symbol=raw["symbol"],
        side=OrderSide(raw["side"]),
        type=OrderType(raw["type"]),
        status=OrderStatus(raw["status"]),
        quantity=_dec(raw["origQty"]),
        filled_quantity=executed,
        price=price,
        average_price=average_price,
        created_at=_first_ms(raw, "transactTime", "time", "updateTime"),
        client_order_id=raw.get("clientOrderId"),
        stop_price=stop_price,
        order_list_id=order_list_id,
    )


_NEEDS_PRICE = frozenset({OrderType.LIMIT, OrderType.STOP_LOSS_LIMIT, OrderType.TAKE_PROFIT_LIMIT})
_NEEDS_STOP = frozenset(
    {
        OrderType.STOP_LOSS,
        OrderType.STOP_LOSS_LIMIT,
        OrderType.TAKE_PROFIT,
        OrderType.TAKE_PROFIT_LIMIT,
    }
)


def order_request_to_params(
    request: OrderRequest, *, time_in_force: TimeInForce = TimeInForce.GTC
) -> dict[str, Any]:
    """Translate an :class:`OrderRequest` into keyword args for ``create_order``.

    Validates that the price/stop fields required by the order type are present,
    raising :class:`OrderError` before any network call is attempted.

    ``request.time_in_force`` wins when the request states one; the keyword is
    the fallback for requests that do not. Both exist deliberately: the keyword
    is the caller's default and predates the field, so every existing call site
    keeps its behaviour, while a request that must be ``FOK`` -- the working leg
    of an order list -- can now say so itself instead of relying on whoever
    happens to translate it.
    """
    params: dict[str, Any] = {
        "symbol": request.symbol,
        "side": request.side.value,
        "type": request.type.value,
        "quantity": format_decimal(request.quantity),
    }

    if request.type in _NEEDS_PRICE:
        if request.price is None:
            raise OrderError(f"{request.type.value} order requires a price")
        params["price"] = format_decimal(request.price)
        params["timeInForce"] = (request.time_in_force or time_in_force).value

    if request.type in _NEEDS_STOP:
        if request.stop_price is None:
            raise OrderError(f"{request.type.value} order requires a stop_price")
        params["stopPrice"] = format_decimal(request.stop_price)

    if request.client_order_id is not None:
        params["newClientOrderId"] = request.client_order_id

    return params


# --------------------------------------------------------------------------
# Error translation
# --------------------------------------------------------------------------
def translate_binance_error(exc: Exception) -> TradingBotError:
    """Map a ``python-binance`` / transport exception onto the domain hierarchy.

    * 429/418 or code ``-1003`` -> :class:`RateLimitError`
    * ``-2010`` "insufficient balance" -> :class:`InsufficientBalanceError`
    * filter / precision / order-reject codes -> :class:`OrderError`
    * any other API error -> :class:`ExchangeAPIError` (carries the code)
    * transport failures -> :class:`ExchangeConnectionError`
    """
    if isinstance(exc, BinanceAPIException):
        code = getattr(exc, "code", None)
        status = getattr(exc, "status_code", None)
        message = getattr(exc, "message", "") or str(exc)
        if status in _RATE_LIMIT_STATUS or code == _RATE_LIMIT_CODE:
            return RateLimitError(message)
        if code == _INSUFFICIENT_BALANCE_CODE and "insufficient balance" in message.lower():
            return InsufficientBalanceError(message)
        if code in _ORDER_REJECT_CODES:
            return OrderError(message)
        return ExchangeAPIError(message, code=code if isinstance(code, int) else None)

    if isinstance(exc, BinanceOrderException):
        message = getattr(exc, "message", str(exc))
        if "insufficient balance" in message.lower():
            return InsufficientBalanceError(message)
        return OrderError(message)

    if isinstance(exc, BinanceRequestException):
        return ExchangeAPIError(str(exc))

    if isinstance(exc, (aiohttp.ClientError, asyncio.TimeoutError, ConnectionError)):
        return ExchangeConnectionError(str(exc))

    return ExchangeError(str(exc))
