"""Exchange-specific mapping: Binance REST payloads <-> domain models.

Every **mapper** here is pure and free of I/O, save the two scoped log lines
named below: given a Binance response (already
parsed into Python dicts/lists by ``python-binance``) it returns one of the
frozen, ``Decimal``-based domain models from :mod:`trading_bot.core.models`;
given an :class:`OrderRequest` it produces the keyword arguments for a Binance
order call. Keeping these transformations pure makes them exhaustively testable
against recorded JSON with no mocking.

**There are two exceptions, and each claim is scoped rather than quietly
broken.** :func:`translate_binance_error` emits a single ``ERROR`` log line when
a code it classifies by message arrives with a message none of its rules
recognise -- the alternative being to reclassify silently, which is the failure
message-matching exists to prevent. :func:`to_order` emits one ``WARNING`` when
the venue reports a negative ``cummulativeQuoteQty``, which it documents as
unavailable -- the alternative being to carry a negative total that booking
would read as present. Each is still a pure function of its argument in every
other respect: same input, same returned value -- the exception, or the
``Order`` -- and no I/O on any path that decides it.

Money is parsed straight from Binance's decimal *strings* into
:class:`decimal.Decimal` — never through ``float`` — so no precision is lost.

:func:`translate_binance_error` maps the library's exception zoo onto the
project's :mod:`trading_bot.core.exceptions` hierarchy so callers reason about
failures in domain terms.
"""

from __future__ import annotations

import asyncio
import re
from collections.abc import Callable, Sequence
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, NamedTuple

import aiohttp
from binance.exceptions import (
    BinanceAPIException,
    BinanceOrderException,
    BinanceRequestException,
)
from pydantic import BaseModel, ConfigDict

from trading_bot.core.enums import OrderSide, OrderStatus, OrderType, TimeInForce
from trading_bot.core.exceptions import (
    ClientFilterRejectedError,
    ClientOrderError,
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
    TradingBotError,
)
from trading_bot.core.models import (
    Balance,
    Candle,
    Fee,
    MarketLotSize,
    Money,
    Order,
    OrderList,
    OrderListEntry,
    OrderRequest,
    OtocoOrderListRequest,
    OtoOrderListRequest,
    PercentPriceBySide,
    SymbolInfo,
    Ticker,
    Trade,
)
from trading_bot.exchange.ids import OrderListLeg, client_order_id, list_client_order_id
from trading_bot.utils.helpers import round_price, round_step_size
from trading_bot.utils.logger import get_logger

_log = get_logger(__name__)

_EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)

#: The ``event`` of :func:`to_order`'s one WARNING: the venue reported a
#: negative ``cummulativeQuoteQty`` and the total was read as absent.
_EVENT_QUOTE_TOTAL_UNAVAILABLE = "venue_quote_total_unavailable"
#: Its ``reason``, naming the venue's documented meaning of a negative total.
_REASON_QUOTE_TOTAL_UNAVAILABLE = (
    "the venue documents a cummulativeQuoteQty below zero as data not available "
    "for this order record"
)

# Binance error codes we can classify precisely; anything else falls through to
# a generic ExchangeAPIError that carries the original code.
_RATE_LIMIT_CODE = -1003
_UNKNOWN_ORDER_CODE = -2011
_FILTER_FAILURE_CODE = -1013
_MALFORMED_REQUEST_CODE = -1100
# The contract group: our request is structurally wrong for the endpoint.
# CODE-ONLY rows, because no verbatim message text for any of them exists in
# this repository and acquiring one is an unbounded search. What each MEANS is
# recorded on ContractViolationError, which is the only record there is.
_CONTRACT_VIOLATION_CODES = (-1106, -1159, -1158)
# -2010 is OVERLOADED and the name says so. It carries at least two unrelated
# meanings, both measured verbatim at M5c: "Account has insufficient balance for
# requested action." and "Duplicate order sent." Only the message separates them,
# which is why this code needs message rules rather than a single mapping -- and
# why the constant is no longer named after one of its meanings.
_OVERLOADED_ORDER_CODE = -2010
# THE LADDER'S THIRD BAND, and what it catches is easy to lose: A KEYED CODE
# WHOSE MESSAGE MATCHED NO ROW. The rows above fire only on a match; a reworded
# or unrecognised message on one of these four falls past them to here.
#
# **All four members are live and ten tests depend on this.** Three
# falls-through-to-the-reject-set tests, five near-miss tests and the two
# loud-fallthrough tests all assert that such a message stays an ``OrderError``
# rather than degrading to ``ExchangeAPIError``. That is what makes the arc's
# near-miss behaviour A REFUSAL TO GUESS rather than a reclassification: we stop
# claiming to know which meaning arrived, without pretending we no longer know
# it was an order rejection.
#
# ``-1111`` was removed at M5c C6. It was never observed, never documented and
# never tested -- it arrived inside this set in a commit whose entire message is
# "phase 2" -- so it now falls to ``ExchangeAPIError``, which PRESERVES its code
# where ``OrderError`` discarded it.
_ORDER_REJECT_CODES = frozenset({-1013, -1100, -2010, -2011})
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


class VenueFill(BaseModel):
    """One record from ``GET /api/v3/myTrades``: a single fill, as the venue books it.

    **IT TERMINATES AT THE WIRE AND IS NOT A DOMAIN TYPE.** It carries the
    venue's shape, including fields the domain has no use for, because the
    adapter's job is to report what arrived rather than to decide what matters.
    What crosses into ``core/`` is a later ruling, not this one's.

    **THE FEE IS AN AMOUNT PAIRED WITH ITS ASSET, AND NEITHER HALF IS
    OPTIONAL.** ``CLAUDE.md`` rules that a money figure crosses a boundary only
    with its denomination, because ``Decimal`` encodes precision and not
    currency -- subtracting a BNB fee from a USDT total succeeds silently and
    writes a plausible wrong number. Both fields are required here, so a
    ``VenueFill`` carrying a fee of unknown denomination cannot be constructed
    at all. That is the invariant enforced rather than documented, and it is
    why neither field has a default.

    **THE PAIRING IS CARRIED, NOT JUDGED.** A fee denominated in something
    other than the quote asset is a normal record and is mapped faithfully:
    MEASURED against the capture whose SHA-256 is ``111d1c15a3c5fff56148f172
    bfbcbec85baf5aabe2128f34fb622cafe5463970``, the venue denominates the fee
    in the asset RECEIVED, so all 128 buy fills carry ``BTC`` and all 178 sell
    fills carry ``USDT``. Refusing a cross-denominated fee is a LEDGER
    behaviour and belongs to whoever books one; a wire mapper that refused it
    would be discarding what the venue actually said.

    **MONEY FIELDS TAKE THE VENUE'S RAW STRING, NOT ``_dec``'s OUTPUT.**
    MEASURED: ``_dec(0.1)`` returns ``Decimal('0.1')``, so a float routed
    through it reaches a ``Money`` field as a ``Decimal`` and ``_reject_float``
    never sees the float it exists to refuse. A string reaches the field
    unmodified, converts exactly, and leaves the guard live. MEASURED against
    the same capture: all four money keys arrive as JSON strings on all 306
    records, so this is correct against the wire rather than against an
    assumption.

    ``isBestMatch`` is deliberately not carried: it is a matching-engine detail
    with no consumer here or downstream, and it is ``true`` on every record of
    the capture, so it discriminates nothing.
    """

    model_config = ConfigDict(frozen=True)

    trade_id: str
    order_id: str
    order_list_id: str | None
    symbol: str
    price: Money
    quantity: Money
    quote_quantity: Money
    commission: Money
    commission_asset: str
    is_buyer: bool
    is_maker: bool
    filled_at: datetime


def to_venue_fill(raw: dict[str, Any]) -> VenueFill:
    """Map one ``myTrades`` record into :class:`VenueFill`.

    **A MISSING FEE FIELD REFUSES; IT DOES NOT DEFAULT.** ``commission`` and
    ``commissionAsset`` are read by subscript inside the guard below, in the
    shape :func:`to_symbol_info` already uses for a mandatory filter. Reading
    them with ``.get`` and a fallback would book a zero fee in an empty
    currency, which is the interim stub ``CLAUDE.md`` forbids by name -- and
    worse here than there, because the call site would look wired.

    **``quoteQty`` IS READ INSIDE THE SAME GUARD**, and for the reason the
    guard exists: it is the figure a booking sums. Read by a bare subscript
    outside it, a record missing the key raised ``KeyError``, which no
    ``except ExchangeError`` above this mapper catches, so it escaped the
    settlement fetch as an unclassified crash rather than a venue error.

    **AN UNREAD KEY IS SILENTLY IGNORED, AS EVERYWHERE IN THIS MODULE.** No
    mapper here does ``Model(**raw)``, so pydantic's ``extra`` setting never
    engages and a key the venue adds later arrives unnoticed. That is the
    M5d-053 shape and the reason the acceptance test asserts the full
    thirteen-key set against captured bytes rather than against a fixture
    written from documentation.

    ``orderListId`` is ``-1`` for a fill belonging to no list, which is a
    sentinel rather than an identity -- mapped to ``None`` exactly as
    :func:`to_order` maps the same key, so the two agree on what "no list"
    looks like. It arrives as a JSON NUMBER and the identity form is a
    ``str``, which is :func:`to_order`'s convention for every id it carries.

    :raises ExchangeAPIError: the record omits ``commission``,
        ``commissionAsset`` or ``quoteQty``.
    """
    try:
        commission = raw["commission"]
        commission_asset = raw["commissionAsset"]
        quote_quantity = raw["quoteQty"]
    except KeyError as exc:
        raise ExchangeAPIError(
            f"Malformed trade record for {raw.get('symbol')!r} "
            f"trade {raw.get('id')!r}: missing {exc.args[0]}"
        ) from exc

    raw_list_id = raw.get("orderListId")
    order_list_id = None if raw_list_id is None or int(raw_list_id) == -1 else str(raw_list_id)

    return VenueFill(
        trade_id=str(raw["id"]),
        order_id=str(raw["orderId"]),
        order_list_id=order_list_id,
        symbol=raw["symbol"],
        price=raw["price"],
        quantity=raw["qty"],
        quote_quantity=quote_quantity,
        commission=commission,
        commission_asset=commission_asset,
        is_buyer=bool(raw["isBuyer"]),
        is_maker=bool(raw["isMaker"]),
        filled_at=_ms_to_dt(raw["time"]),
    )


def to_venue_fills(raw: Sequence[dict[str, Any]]) -> list[VenueFill]:
    """Map a ``myTrades`` array, preserving the venue's order.

    An empty array maps to an empty list, which is the honest answer for a
    symbol with no fills rather than a defect. Unlike :func:`to_order_list`,
    there is no nested key to get wrong: the array IS the payload, so the
    M5d-053 failure has no foothold here.
    """
    return [to_venue_fill(entry) for entry in raw]


def to_trade(fill: VenueFill) -> Trade:
    """Translate one wire fill into the domain's :class:`Trade`.

    **IT LIVES ON THE ADAPTER SIDE BECAUSE IT MUST.** :class:`VenueFill` is an
    ``exchange/`` type and :class:`Trade` is a ``core/`` one; ``exchange`` may
    import from ``core`` and never the reverse, so this module is the only
    layer that can see both. ``core/interfaces.py`` declares over
    :class:`Trade` alone and never learns that :class:`VenueFill` exists.

    **NO ARITHMETIC HAPPENS HERE.** Every money figure is carried across
    unchanged -- no division, no summation, no re-derivation -- so the domain
    receives exactly what the venue sent. The fee's amount and its asset cross
    together as a :class:`Fee`, which is what makes the denomination
    impossible to drop between the two layers.

    ``side`` is the one translation, and it is a vocabulary change rather than
    a computation: the wire says ``isBuyer``, the domain says
    :class:`OrderSide`.
    """
    return Trade(
        trade_id=fill.trade_id,
        order_id=fill.order_id,
        symbol=fill.symbol,
        side=OrderSide.BUY if fill.is_buyer else OrderSide.SELL,
        quantity=fill.quantity,
        price=fill.price,
        quote_quantity=fill.quote_quantity,
        fee=Fee(amount=fill.commission, asset=fill.commission_asset),
        filled_at=fill.filled_at,
        order_list_id=fill.order_list_id,
        is_maker=fill.is_maker,
    )


def to_trades(raw: Sequence[dict[str, Any]]) -> list[Trade]:
    """Map a ``myTrades`` array straight to the domain, preserving venue order.

    The two steps are kept separate -- :func:`to_venue_fill` parses the wire
    and :func:`to_trade` translates the layer -- because only the first can
    refuse a malformed record, and folding them would make the refusal
    indistinguishable from a translation failure.
    """
    return [to_trade(fill) for fill in to_venue_fills(raw)]


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

    **BOTH THE TOTAL AND THE QUOTIENT ARE CARRIED, and the derivation above is
    unchanged.** ``filled_quote_quantity`` is the wire's
    ``cummulativeQuoteQty`` verbatim, save a negative value (below);
    ``average_price`` stays the quotient it has always been. That is not
    redundancy: the division runs in the ambient
    ``decimal`` context, so a quotient that does not terminate is rounded to 28
    significant digits, and booking realised P&L needs the total the venue
    itself added up rather than a figure re-derived from a rounded one.

    **THE MISSPELLING STOPS AT THE WIRE.** The venue spells it
    ``cummulativeQuoteQty``, with one ``m`` too many; the domain field is
    ``filled_quote_quantity``, named for what it is and parallel to
    ``filled_quantity`` -- the same fill, in the other currency. This is the
    convention every other field here already follows: ``executedQty`` became
    ``filled_quantity``, ``origQty`` became ``quantity``.

    **AND THE TOTAL DISTINGUISHES TWO STATES THE QUOTIENT CANNOT.** The guard
    below is ``executed > 0 and cummulative > 0``, so a payload reporting a
    non-zero ``executedQty`` with a zero quote total yields ``average_price is
    None`` -- the same value as "nothing filled". ``filled_quote_quantity``
    tells them apart: ``Decimal(0)`` beside a non-zero ``filled_quantity`` is
    visible, where ``None`` from the quotient is not. It uses ``_opt_dec``
    rather than ``_dec(..., "0")`` precisely so an ABSENT key stays ``None``
    instead of becoming a reported zero.

    **A NEGATIVE TOTAL IS ABSENT, by the project owner's Decision 3.** The
    venue documents, for ``GET /api/v3/order``, that on some historical orders
    ``cummulativeQuoteQty`` is below zero, meaning the data is not available at
    this time. Carried verbatim it would be a PRESENT total, and a booking site
    would credit a negative quote amount. So a value strictly below zero becomes
    ``None`` -- the absent-key state exactly -- and ONE ``WARNING``, event
    ``venue_quote_total_unavailable``, names the order and the raw value.
    Downstream the verdict is ``NO_QUOTE_TOTAL``, never a negative booking. Zero
    is unchanged: ``"0.00000000"`` is what a resting order reports, a real
    quantity. The returned ``Order`` is identical to the one the same payload
    gives with the key removed; the WARNING is the only difference.

    **THE OTHER READ OF THE KEY IS LEFT AS IT IS.** ``cummulative`` above
    defaults a missing key to zero for the division, and its guard
    ``executed > 0 and cummulative > 0`` already yields ``average_price is
    None`` for a negative total, so no negative price can arise from it. It is
    left alone because it is already safe, and because the two reads answer
    different questions: a zero default is right for a division and wrong for
    the total, which is why they were separate reads in the first place.

    ``orderListId`` is ``-1`` for an order that belongs to no list. That is a
    sentinel rather than an identity, so it maps to ``None`` -- otherwise every
    ordinary order would appear to belong to list "-1", and a reconciler keyed
    on list membership would group them together.

    **A CANCEL RESPONSE NAMES THE ORDER DIFFERENTLY FROM EVERY OTHER SHAPE**, so
    ``client_order_id`` prefers ``origClientOrderId``. On a cancel the venue puts
    a fresh identifier of its own in ``clientOrderId`` and returns ours under
    ``origClientOrderId``; create and query responses carry ours in
    ``clientOrderId`` and no ``origClientOrderId``. Reading ``clientOrderId``
    alone therefore hands the caller an identifier it never sent, on the one
    response that confirms a cancel -- which is the response a reconciler keyed
    on our own IDs most needs to match.
    """
    executed = _dec(raw.get("executedQty", "0"))
    cummulative = _dec(raw.get("cummulativeQuoteQty", "0"))  # Binance's spelling
    average_price = cummulative / executed if executed > 0 and cummulative > 0 else None
    # The TOTAL, carried whole and separately from the quotient above. `_opt_dec`
    # rather than the defaulted `_dec` on purpose: an absent key must stay
    # `None` -- "the venue did not report it" -- and never become a zero the
    # venue never sent.
    filled_quote_quantity = _opt_dec(raw.get("cummulativeQuoteQty"))
    if filled_quote_quantity is not None and filled_quote_quantity < 0:
        # DECISION 3 (the project owner): the venue documents a total below zero
        # as UNAVAILABLE, so it is read as absent -- never carried as a present,
        # negative figure a booking site would credit. Strictly `< 0`: zero is
        # what a resting order reports, and stays present.
        _log.warning(
            "%s order %s: the venue reported cummulativeQuoteQty %s, which it documents as "
            "unavailable; the quote total is read as ABSENT",
            raw["symbol"],
            raw["orderId"],
            raw["cummulativeQuoteQty"],
            extra={
                "event": _EVENT_QUOTE_TOTAL_UNAVAILABLE,
                "symbol": raw["symbol"],
                "order_id": str(raw["orderId"]),
                "raw_quote_total": str(raw["cummulativeQuoteQty"]),
                "reason": _REASON_QUOTE_TOTAL_UNAVAILABLE,
            },
        )
        filled_quote_quantity = None

    price = _opt_dec(raw.get("price"))
    if price is not None and price == 0:
        price = None

    stop_price = _opt_dec(raw.get("stopPrice"))
    if stop_price is not None and stop_price == 0:
        stop_price = None

    raw_list_id = raw.get("orderListId")
    order_list_id = None if raw_list_id is None or int(raw_list_id) == -1 else str(raw_list_id)

    # MEASURED on BOTH cancel endpoints -- `DELETE /api/v3/order` and
    # `DELETE /api/v3/orderList` -- a cancel response reports OUR id in
    # `origClientOrderId` and a FRESH VENUE-GENERATED value in `clientOrderId`.
    # Create and query shapes carry ours in `clientOrderId` and no
    # `origClientOrderId` at all, so preferring the latter key is correct for
    # all four shapes rather than a special case bolted on for one.
    #
    # `is not None` rather than `or`: an empty string is not a value the venue
    # is measured to send, and falling through on one would reintroduce the
    # substitution silently.
    orig_client_order_id = raw.get("origClientOrderId")
    client_order_id = (
        orig_client_order_id if orig_client_order_id is not None else raw.get("clientOrderId")
    )

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
        filled_quote_quantity=filled_quote_quantity,
        created_at=_first_ms(raw, "transactTime", "time", "updateTime"),
        client_order_id=client_order_id,
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


#: The leg-array key on a ``v3_get_order_list`` read-back. **MEASURED** against
#: a captured payload, which also enumerated the full top-level key set --
#: ``orderReports`` is a measured ABSENCE from this endpoint.
#:
#: It was ``"orderReports"`` until M5d's probe, assumed from the general Binance
#: schema because nothing in this repository had captured a payload. The wrong
#: key mapped ZERO legs from a three-leg response WITHOUT RAISING (M5d-053), and
#: a test asserting the empty result defended it. That is why the three-leg
#: assertion below exists: a silent zero must be impossible to reintroduce.
_LEG_ARRAY_KEY = "orders"


def to_order_list(raw: dict[str, Any]) -> OrderList:
    """Map an order-list payload into :class:`OrderList`.

    **SCOPED TO THE READ-BACK.** The placement response is a different shape and
    its leg array is UNMEASURED; this mapper is not it. Unifying the two on an
    assumption is what produced M5d-053.

    **The list-history endpoint returns this same shape, per element** -- eight
    list-level keys and three-key identity legs, MEASURED against a captured
    ``v3_get_all_order_list`` payload and identical to the read-back's. So
    ``get_all_order_lists`` maps each entry through here rather than through a
    mapper of its own. Recorded because the scoping sentence above would
    otherwise read as excluding a caller it does in fact cover.

    **Legs are IDENTITIES, not orders.** A read-back leg carries exactly
    ``{"symbol", "orderId", "clientOrderId"}`` (MEASURED, captured payload), so
    :func:`to_order` cannot map one -- it raises ``KeyError: 'side'``. Section
    7's compare set therefore needs a per-order query per leg; a list read-back
    cannot supply it, however the legs are typed.

    **No numeric field passes through ``float`` because no numeric field is
    read.** ``orderId`` is stringified for the domain, as ``to_order`` does.

    **An absent leg array maps to an empty tuple**, which is a real state for a
    payload that has no legs -- and is the M5d-053 defect for one that does. The
    three-leg assertion in the tests is what separates them.

    ``contingencyType`` is read from the payload by nothing here; see
    :class:`OrderList` for why it is not carried.
    """
    entries = raw.get(_LEG_ARRAY_KEY) or ()
    return OrderList(
        order_list_id=str(raw["orderListId"]),
        symbol=raw["symbol"],
        list_client_order_id=raw.get("listClientOrderId"),
        list_status_type=raw.get("listStatusType"),
        list_order_status=raw.get("listOrderStatus"),
        orders=tuple(
            OrderListEntry(
                symbol=entry["symbol"],
                order_id=str(entry["orderId"]),
                client_order_id=entry["clientOrderId"],
            )
            for entry in entries
        ),
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
            raise ClientOrderError(f"{request.type.value} order requires a price")
        params["price"] = format_decimal(request.price)
        params["timeInForce"] = (request.time_in_force or time_in_force).value

    if request.type in _NEEDS_STOP:
        if request.stop_price is None:
            raise ClientOrderError(f"{request.type.value} order requires a stop_price")
        params["stopPrice"] = format_decimal(request.stop_price)

    if request.client_order_id is not None:
        params["newClientOrderId"] = request.client_order_id

    return params


def otoco_request_to_params(request: OtocoOrderListRequest) -> dict[str, Any]:
    """Translate an OTOCO request into keyword args for ``v3_post_order_list_otoco``.

    **Sixteen keys, laid out in Q-C section 3's own grouping.** The fence is
    load-bearing: the grouping is the correspondence to the measured parameter
    set, and a formatter free to rewrap it would destroy the only thing that
    makes the two checkable against each other by eye.

    **No dispatch, by design.** OTO has its own function rather than a shared
    one with a branch. A single mapper over a union would need an ``else`` that
    cannot occur -- a branch nothing can test -- and the caller already knows
    which shape it built.

    **The four ``-1106`` fields are absent because nothing here can produce
    them**, not because anything rejects them. Both protective legs are
    stop-market so each carries one price, and the request type has no
    time-in-force field, so ``pendingAbovePrice``, ``pendingAboveTimeInForce``,
    ``pendingBelowPrice`` and ``pendingBelowTimeInForce`` have no source to be
    read from. A guard here would imply they were reachable.

    Every price and quantity goes through :func:`format_decimal`. ``str()`` on a
    ``Decimal`` yields scientific notation at the extremes -- ``1E-8``,
    ``1E+3`` -- which Binance rejects.
    """
    seeds = (request.symbol, request.entry_bar_time)
    generation = request.generation
    # fmt: off
    return {
        "symbol":                    request.symbol,
        "listClientOrderId":         list_client_order_id(*seeds, generation=generation),

        "workingType":               OrderType.LIMIT.value,
        "workingSide":               OrderSide.BUY.value,
        "workingPrice":              format_decimal(request.entry_limit),
        "workingQuantity":           format_decimal(request.quantity),
        "workingTimeInForce":        TimeInForce.FOK.value,
        "workingClientOrderId":      client_order_id(
            *seeds, OrderListLeg.WORKING, generation=generation
        ),

        "pendingSide":               OrderSide.SELL.value,
        "pendingQuantity":           format_decimal(request.quantity),

        "pendingAboveType":          OrderType.TAKE_PROFIT.value,
        "pendingAboveStopPrice":     format_decimal(request.take_profit),
        "pendingAboveClientOrderId": client_order_id(
            *seeds, OrderListLeg.TAKE_PROFIT, generation=generation
        ),

        "pendingBelowType":          OrderType.STOP_LOSS.value,
        "pendingBelowStopPrice":     format_decimal(request.stop_price),
        "pendingBelowClientOrderId": client_order_id(
            *seeds, OrderListLeg.STOP_LOSS, generation=generation
        ),
    }
    # fmt: on


def oto_request_to_params(request: OtoOrderListRequest) -> dict[str, Any]:
    """Translate an OTO request into keyword args for ``v3_post_order_list_oto``.

    **Thirteen keys, and the prefix differs by more than the missing leg.**
    Section 3 flags it: OTO uses the plain ``pending*`` prefix where OTOCO uses
    ``pendingAbove*``/``pendingBelow*``. The keys are written out literally here
    rather than shared with OTOCO under a prefix parameter, on three grounds --
    the shapes differ in *arity* as well as spelling, so a prefix parameter
    would assert a sameness that is not there; a computed prefix turns a
    measured constant into a string a typo can corrupt, failing only at the
    venue and under ``-1100``'s misleading message; and literal keys are
    checkable by eye against section 3, which is why that block is fenced.
    """
    seeds = (request.symbol, request.entry_bar_time)
    generation = request.generation
    # fmt: off
    return {
        "symbol":               request.symbol,
        "listClientOrderId":    list_client_order_id(*seeds, generation=generation),

        "workingType":          OrderType.LIMIT.value,
        "workingSide":          OrderSide.BUY.value,
        "workingPrice":         format_decimal(request.entry_limit),
        "workingQuantity":      format_decimal(request.quantity),
        "workingTimeInForce":   TimeInForce.FOK.value,
        "workingClientOrderId": client_order_id(
            *seeds, OrderListLeg.WORKING, generation=generation
        ),

        "pendingType":          OrderType.STOP_LOSS.value,
        "pendingSide":          OrderSide.SELL.value,
        "pendingQuantity":      format_decimal(request.quantity),
        "pendingStopPrice":     format_decimal(request.stop_price),
        "pendingClientOrderId": client_order_id(
            *seeds, OrderListLeg.STOP_LOSS, generation=generation
        ),
    }
    # fmt: on


# --------------------------------------------------------------------------
# Error translation
# --------------------------------------------------------------------------
class _ApiRule(NamedTuple):
    """One row of the ``BinanceAPIException`` dispatch table.

    ``code`` and ``pattern`` are each optional and are ANDed: a row with both
    matches only when the code equals *and* the message matches. ``pattern`` is
    searched, not fullmatched, so a row can key on a stable fragment of a
    message whose tail varies.

    A row exists so the **order** of classification is data rather than the
    shape of an ``if`` ladder. That matters because the order here is
    load-bearing and always was -- ``-2010`` reaches
    :class:`InsufficientBalanceError` only because its message rule is
    consulted before the order-reject fallback, and inverting the two silently
    reclassifies a balance failure as a generic order rejection.
    """

    code: int | None
    pattern: re.Pattern[str] | None
    #: What this row classifies as. Named for the classification rather than for
    #: the call, because a row that needs the match uses ``build`` instead -- so
    #: this field stays the answer to "what does this row mean?" either way, and
    #: it is what the declared-order test asserts.
    produces: type[ExchangeAPIError]
    #: Used instead of ``produces(message, code=code)`` when the exception needs
    #: something parsed out of the message.
    #:
    #: **ONE hook, taking everything a row can classify on.** C3 added a
    #: message-shaped hook and C5 added a code-shaped one; the hierarchy pass
    #: retired both rather than widening the pair a third time, because two hooks
    #: made the caller choose which axis mattered when the answer is "either, and
    #: sometimes both". ``match`` is ``None`` exactly on a code-only row.
    #:
    #: **The invariant a row must satisfy:** if ``produces`` needs more than
    #: ``(message, code)`` -- as :class:`FilterRejectedError` and
    #: :class:`MalformedRequestError` do -- the row MUST supply ``build``.
    #: Nothing enforces it structurally; a row that broke it would raise
    #: ``TypeError`` on its first matching response rather than fail silently,
    #: and every row has a test.
    build: Callable[[str, int | None, re.Match[str] | None], TradingBotError] | None = None

    def keys_on(self, code: object) -> bool:
        """Whether this row is about ``code`` at all."""
        return self.code is None or code == self.code


#: Matched against the message of a ``-2010``. Kept as a narrow fragment rather
#: than the whole sentence deliberately: the measured text is "Account has
#: insufficient balance for requested action." (MEASURED, Testnet, 2026-08-12,
#: identical for a BUY exceeding quote and a SELL exceeding base), and matching
#: the fragment survives a rewording of the surrounding sentence while still
#: distinguishing this meaning of -2010 from the others that share the code.
_INSUFFICIENT_BALANCE_RE = re.compile("insufficient balance", re.IGNORECASE)

#: Matched against the message of a ``-2010`` that is *not* a balance failure.
#: Anchored on the **complete** measured message, which has no variable part:
#: "Duplicate order sent." (MEASURED, Testnet, 2026-08-12 -- identical for a
#: single order and for an order list). Anchoring is affordable precisely
#: because the string is whole; a rewording must fail this pattern rather than
#: squeeze past it, which is what the near-miss tests pin.
_DUPLICATE_ORDER_RE = re.compile(r"^Duplicate order sent\.$", re.IGNORECASE)

#: Matched against the message of a ``-2011``. Anchored on the complete measured
#: message for the same reason the duplicate is: "Unknown order sent." (MEASURED,
#: Testnet, 2026-08-12, on an OTO teardown -- cancelling the working leg
#: auto-cancelled both pending legs and the follow-up cancels each returned it).
_UNKNOWN_ORDER_RE = re.compile(r"^Unknown order sent\.$", re.IGNORECASE)

#: The first message with a VARIABLE TAIL, so the first row that captures
#: rather than anchoring on the whole string. Measured shape:
#: "Filter failure: NOTIONAL" (MEASURED, Testnet, on a stop leg below
#: min_notional). The character class is justified by the ELEVEN filter names
#: ``exchangeInfo`` reports for BTCUSDT -- every one matches ``[A-Z_]+`` --
#: but note what is and is not measured: the NAMES are measured from
#: ``exchangeInfo``, while their RENDERING inside a -1013 is measured for
#: ``NOTIONAL`` alone. A name outside the class falls through and is logged,
#: which is the guard's case and is pinned by its own test.
_FILTER_FAILURE_RE = re.compile(r"^Filter failure: (?P<filter>[A-Z_]+)$")


#: Matched against the message of a ``-1100``. **Only the narrow stable prefix**:
#: the measured message ends with the venue's own regex --
#: ``legal range is '^[a-zA-Z0-9-_]{1,36}$'`` -- which is pure metacharacters and
#: MUST NEVER enter this pattern. Admitting it would require escaping a foreign
#: regex correctly on every future reword, and getting that wrong silently stops
#: the row matching at all.
#:
#: **This pattern claims a family MEMBER, not the family.** ``-1100`` is a
#: general malformed-request code and other renderings certainly exist that this
#: will not match; those fall through to today's behaviour and fire the loud
#: guard, which is correct and is tested.
_MALFORMED_PARAM_RE = re.compile(r"^Illegal characters found in parameter '(?P<param>[^']+)'")


def _contract_violation(
    message: str, code: int | None, _match: re.Match[str] | None
) -> TradingBotError:
    """Build a :class:`ContractViolationError` carrying the code.

    **A CODE-ONLY row, and the qualifier matters more than the row.** It is
    valid only while its code carries ONE meaning, and there is no measurement
    saying these do -- only an absence of evidence that they do not. ``-2010``
    was not known overloaded either until M5c measured two meanings on it.

    **The way it fails is SILENT**: a second meaning arriving on ``-1106``,
    ``-1158`` or ``-1159`` would be classified as the first, with nothing firing
    -- the loud guard reports an unmatched *pattern*, and a row with no pattern
    cannot reach it. So this is the one family in the classifier outside the
    guard's reach.
    """
    return ContractViolationError(message, code=code)


def _malformed_request(
    message: str, code: int | None, match: re.Match[str] | None
) -> TradingBotError:
    """Build a :class:`MalformedRequestError` carrying the offending parameter."""
    # A pattern row always has a match; this narrows the Optional for mypy.
    assert match is not None
    return MalformedRequestError(message, parameter=match.group("param"), code=code)


def _filter_rejected(
    message: str, code: int | None, match: re.Match[str] | None
) -> TradingBotError:
    """Build a :class:`FilterRejectedError` carrying the captured filter name.

    The captured spelling is the exchange's own, which is what makes a parsed
    venue rejection and ``BinanceClient._enforce``'s local refusal legible as
    the same condition: ``_enforce`` raises ``filter_name='PRICE_FILTER'``,
    and this capture yields ``'PRICE_FILTER'`` byte-for-byte from
    "Filter failure: PRICE_FILTER".
    """
    # A pattern row always has a match; this narrows the Optional for mypy.
    assert match is not None
    return FilterRejectedError(message, filter_name=match.group("filter"), code=code)


#: The dispatch table, consulted in order; first match wins. Anything unmatched
#: falls through to the ladder below, which is still the authority for the
#: order-reject code set and for the generic case. Rows are added here as each
#: error family lands; nothing is removed from the fallback until a row covers
#: it.
_API_RULES: tuple[_ApiRule, ...] = (
    _ApiRule(_RATE_LIMIT_CODE, None, RateLimitError),
    _ApiRule(_OVERLOADED_ORDER_CODE, _INSUFFICIENT_BALANCE_RE, InsufficientBalanceError),
    _ApiRule(_OVERLOADED_ORDER_CODE, _DUPLICATE_ORDER_RE, DuplicateOrderError),
    _ApiRule(_UNKNOWN_ORDER_CODE, _UNKNOWN_ORDER_RE, OrderNotFoundError),
    _ApiRule(_FILTER_FAILURE_CODE, _FILTER_FAILURE_RE, FilterRejectedError, _filter_rejected),
    _ApiRule(
        _MALFORMED_REQUEST_CODE, _MALFORMED_PARAM_RE, MalformedRequestError, _malformed_request
    ),
    *(_ApiRule(code, None, ContractViolationError) for code in _CONTRACT_VIOLATION_CODES),
)


def translate_binance_error(exc: Exception) -> TradingBotError:
    """Map a ``python-binance`` / transport exception onto the domain hierarchy.

    * 429/418 or code ``-1003`` -> :class:`RateLimitError`
    * ``-2010`` "insufficient balance" -> :class:`InsufficientBalanceError`
    * filter / precision / order-reject codes -> :class:`OrderError`
    * any other API error -> :class:`ExchangeAPIError` (carries the code)
    * transport failures -> :class:`ExchangeConnectionError`

    **Every venue-side route that HOLDS a code now carries it.** The reasoning
    is :class:`ExchangeAPIError`'s own and predates this: *"a classification
    that discards the code leaves an operator holding our vocabulary instead of
    Binance's"*, and *"the better we classified, the less machine-readable
    identity survived, which is backwards"*. Three routes did not follow it --
    the reject-set fallback and both ``BinanceOrderException`` branches -- and
    now do. M5c fixed the same defect once from the other side, by removing
    ``-1111`` from the reject set so its code would survive; this fixes the set
    itself rather than its membership.

    **THIS DOES NOT MAKE ``code is None`` A DISCRIMINATOR FOR "never reached the
    venue", and must not be read as doing so.** Two venue-side routes still
    produce ``None``, and neither is an oversight:

    * ``BinanceRequestException`` carries **no code at all** -- and it is raised
      by the library only AFTER a 2xx, when the body will not parse. For a
      placement that means **the venue returned success and we cannot read what
      it said**, which is the most ambiguous outcome there is. UNRULED: it needs
      a representation ``int | None`` cannot express.
    * the non-int fallback below nulls a code the venue *did* respond with, when
      its error body parsed but carried no ``code`` key.

    A caller wanting "did this reach the venue?" cannot get it from ``.code``.

    ``BinanceAPIException`` is dispatched through :data:`_API_RULES` first and
    falls through to the ladder below; every other family is ladder-only,
    because none of them carries a code to key a row on.
    """
    if isinstance(exc, BinanceAPIException):
        code = getattr(exc, "code", None)
        status = getattr(exc, "status_code", None)
        message = getattr(exc, "message", "") or str(exc)
        # Not a (code, message) rule and so not a row: 429/418 classify on the
        # HTTP status alone, and such a response carries no body worth
        # matching. Checked first, exactly where the ladder checked it.
        if status in _RATE_LIMIT_STATUS:
            return RateLimitError(message)
        keyed_but_unmatched = False
        for rule in _API_RULES:
            if not rule.keys_on(code):
                continue
            match = rule.pattern.search(message) if rule.pattern is not None else None
            if rule.pattern is not None and match is None:
                keyed_but_unmatched = True
                continue
            code_int = code if isinstance(code, int) else None
            if rule.pattern is None:
                # CAPTURE, not detection. A code-only row has no message
                # expectation, so the loud guard below cannot reach it and
                # these codes are the one family without rot detection. There
                # is nothing to detect -- but the message can be RECORDED, and
                # the first one seen in the wild is exactly what would let
                # someone write a pattern row and close the gap.
                _log.debug("Binance code %s classified without a message rule: %r", code, message)
            if rule.build is not None:
                return rule.build(message, code_int, match)
            return rule.produces(message, code=code_int)
        if keyed_but_unmatched:
            # A code we claim to classify by message, carrying a message none of
            # its rules recognise. Silently falling through is the failure mode
            # message-matching exists to prevent -- Binance rewords, the pattern
            # stops matching, and a family quietly becomes a generic error. So
            # say so, loudly, and then fall through anyway.
            #
            # Logged, never raised, and deliberately not an `assert`: this runs
            # inside error handling, where raising would replace the caller's
            # real failure with ours. Same shape as `IntentLogger`'s
            # `stage is None` branch.
            _log.error(
                "Unclassified message for Binance code %s: %r. A rule keys on this "
                "code but no pattern matched, so it falls through to a generic "
                "error -- the wording may have changed at the venue.",
                code,
                message,
            )
        if code in _ORDER_REJECT_CODES:
            # THE CODE IS CARRIED, and this is the site where discarding it
            # cost most. Reaching here means a rule KEYED on this code and its
            # message pattern did not match -- the loud guard above has just
            # said so -- so the wording is by definition unrecognised and the
            # code is the ONLY identity left. `OrderError` inherits
            # `ExchangeAPIError`'s `code`; it simply was never passed one.
            return OrderError(message, code=code if isinstance(code, int) else None)
        return ExchangeAPIError(message, code=code if isinstance(code, int) else None)

    if isinstance(exc, BinanceOrderException):
        message = getattr(exc, "message", str(exc))
        # `BinanceOrderException.__init__(self, code, message)` -- the library
        # carries a code here and this branch never read it. Read from `exc`
        # rather than the local `code`: that local is bound inside the
        # `BinanceAPIException` branch, which returns on every path, so it is
        # UNBOUND here and a bare `code` would be a `NameError`.
        order_code = getattr(exc, "code", None)
        order_code = order_code if isinstance(order_code, int) else None
        if "insufficient balance" in message.lower():
            return InsufficientBalanceError(message, code=order_code)
        return OrderError(message, code=order_code)

    if isinstance(exc, BinanceRequestException):
        return ExchangeAPIError(str(exc))

    if isinstance(exc, (aiohttp.ClientError, asyncio.TimeoutError, ConnectionError)):
        return ExchangeConnectionError(str(exc))

    return ExchangeError(str(exc))


# --------------------------------------------------------------------------
# Order-list filter enforcement -- per leg, pure
# --------------------------------------------------------------------------
def _enforce_order_list_legs(
    symbol: str,
    quantity: Decimal,
    legs: Sequence[tuple[str, Decimal]],
    info: SymbolInfo,
) -> Decimal:
    """Check every leg against the symbol's filters and return the sized quantity.

    Pure, and separate from any client method on purpose: the decision is
    testable without an ``AsyncMock``, and the ``await get_symbol_info`` that
    feeds it belongs to whoever dispatches.

    **Every price is REJECTED off-tick; none is rounded.** ``_enforce`` rounds
    an ``OrderRequest``'s ``price`` because that price is *derived at dispatch*
    -- a candle close times a slippage multiplier. That premise expired at M5b
    commit 10: ``entry_limit`` now arrives from ``risk.rules.derive_entry_limit``
    already tick-rounded under ``ROUND_CEILING``. Rounding it DOWN here would
    move it below the reference price and invert ``EntryIntent``'s
    ``entry_limit >= reference_price`` invariant -- the one thing D3 identified
    as able to invert silently. The protective triggers arrive rounded toward
    their reference for the older reason: ``ROUND_DOWN`` on a long's stop moves
    it *away* from entry and grows the realised stop distance, an unbooked
    breach of ``risk_per_trade`` arriving through the guard meant to catch it.
    Rejecting names the upstream break instead of papering over it.

    **The notional is checked against the LOWEST leg price, once.** For a long
    the request type already guarantees ``stop_price < entry_limit <
    take_profit``, so the below leg carries the smallest notional and is the
    only leg that can bind -- a per-leg loop would add two branches that cannot
    fire while that invariant holds. This is ``binding_price = min(price,
    stop_price)`` generalised to three legs.

    **``effective_*``, never raw ``LOT_SIZE``.** The stricter of ``LOT_SIZE``
    and ``MARKET_LOT_SIZE`` is what ``risk.position_sizing`` sizes against, so
    reading the raw fields would make this guard weaker than the sizing it
    re-checks. Whether ``MARKET_LOT_SIZE`` binds a *triggered* stop is
    UNRESOLVED (Q-C section 10); this is the reading that survives either
    answer, because relaxing later widens what is accepted while tightening
    later means everything in between was checked by a weaker guard.
    """
    for leg, price in legs:
        if round_price(price, info.price_tick) != price:
            raise ClientFilterRejectedError(
                f"{leg} price {price} for {symbol} is not a multiple of tickSize "
                f"{info.price_tick}; order-list prices arrive tick-rounded, so this "
                "is an upstream contract violation rather than a market state",
                filter_name="PRICE_FILTER",
            )

    sized = round_step_size(quantity, info.effective_step_size)
    if sized <= 0:
        raise ClientOrderError(
            f"Quantity for {symbol} rounds to zero at step {info.effective_step_size}"
        )
    if sized < info.effective_min_qty:
        raise ClientOrderError(
            f"Quantity {sized} below min_qty {info.effective_min_qty} for {symbol}"
        )

    if info.min_notional > 0:
        leg, price = min(legs, key=lambda item: item[1])
        notional = sized * price
        if notional < info.min_notional:
            raise ClientOrderError(
                f"Notional {notional} on the {leg} leg is below min_notional "
                f"{info.min_notional} for {symbol}"
            )

    return sized


def enforce_otoco_filters(
    request: OtocoOrderListRequest, info: SymbolInfo
) -> OtocoOrderListRequest:
    """Filter-check all three OTOCO legs, returning the request with a sized quantity.

    One quantity is shared by every leg, so it is rounded once and the result
    applies to all three -- which is also why the wire spells it twice from a
    single field.
    """
    sized = _enforce_order_list_legs(
        request.symbol,
        request.quantity,
        [
            ("working", request.entry_limit),
            ("below", request.stop_price),
            ("above", request.take_profit),
        ],
        info,
    )
    return request.model_copy(update={"quantity": sized})


def enforce_oto_filters(request: OtoOrderListRequest, info: SymbolInfo) -> OtoOrderListRequest:
    """Filter-check both OTO legs, returning the request with a sized quantity.

    Its own function rather than a branch shared with OTOCO: the caller knows
    which shape it built, and a single checker over a union would need an
    ``else`` that cannot occur.
    """
    sized = _enforce_order_list_legs(
        request.symbol,
        request.quantity,
        [("working", request.entry_limit), ("pending", request.stop_price)],
        info,
    )
    return request.model_copy(update={"quantity": sized})
