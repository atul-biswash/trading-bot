"""Domain models — the vocabulary the whole bot speaks.

Design notes
------------
* **Money is ``Decimal``, never ``float``.** Prices, quantities and P&L use
  :class:`decimal.Decimal` to avoid binary floating-point rounding errors in
  accounting. Indicator maths (pandas/NumPy) works in ``float`` on the way in;
  the boundary is deliberate and lives in the data layer.
* Value objects (candles, tickers, signals) are **frozen**. Stateful objects
  that accumulate over a trade's life (``Position``) are mutable.
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Annotated

from pydantic import (
    AfterValidator,
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    model_validator,
)

from trading_bot.core.enums import (
    OrderSide,
    OrderStatus,
    OrderType,
    PositionSide,
    ProtectionState,
    RiskRule,
    SignalAction,
    TimeInForce,
)


def _utcnow() -> datetime:
    """Timezone-aware UTC now (used as a pydantic default factory)."""
    return datetime.now(timezone.utc)


def _reject_float(value: object) -> object:
    """Refuse to build a money value out of a binary float.

    Pydantic would otherwise accept one silently: ``Decimal(65050.1)`` via
    pydantic's coercion yields ``Decimal('65050.1')``, which *looks* right and
    has already lost whatever precision the exchange actually sent. Every price
    in this system originates as an exchange-supplied decimal string, so a
    ``float`` arriving here means someone round-tripped money through the
    indicator layer -- the one place floats legitimately live.

    ``numpy.float64`` is a ``float`` subclass and is rejected by the same check,
    which is the common case: it is what ``DataFrame.iloc`` hands back.

    ``int`` and ``str`` are allowed through: both convert to ``Decimal``
    exactly, so neither can lose precision.
    """
    if isinstance(value, float):
        raise ValueError(
            f"money must not be built from a float (got {value!r}); "
            "pass a Decimal or a decimal string. If this came from the OHLCV "
            "frame, take the value from the Candle instead."
        )
    return value


#: A ``Decimal`` money field that refuses to be constructed from a ``float``.
#: Used for every price, quantity and balance in the domain.
Money = Annotated[Decimal, BeforeValidator(_reject_float)]

#: Types ``Signal.metadata`` may carry. Matched by **exact type**, not
#: ``isinstance`` -- see :func:`_reject_exotic_metadata`. ``bool`` is listed
#: explicitly because ``type(True) is int`` is ``False``; it is admitted because
#: it serialises cleanly in both log sinks and in JSON.
_METADATA_SCALARS: tuple[type, ...] = (str, int, float, bool)


def _reject_exotic_metadata(value: dict[str, object]) -> dict[str, object]:
    """Keep ``Signal.metadata`` to plain scalars, rejecting NumPy lookalikes.

    Metadata is persisted and logged, so a value that merely *looks* like a
    number is a durable problem. It is checked by **exact type** rather than
    ``isinstance``, which is a deliberate departure from :func:`_reject_float`
    and worth explaining, because the two guards need opposite discriminations:

    * ``_reject_float`` rejects the whole ``float`` family, so ``isinstance``
      is exactly right -- ``numpy.float64`` is a ``float`` subclass and is
      caught for free.
    * Here ``float`` is *allowed* and ``numpy.float64`` is not, and no
      ``isinstance`` test can separate them. ``type(x) is float`` can.

    The pleasant consequence is that this rejects every NumPy scalar without
    ``core/`` importing, or even naming, NumPy -- which is what keeps the
    innermost layer free of the data stack. It costs the ability to accept
    deliberate subclasses (a ``str``-based ``Enum`` member, say), and that is the
    right trade: the fix at such a call site is to pass ``.value``, which is what
    lands in the log anyway.

    ``None`` is permitted so a field can be present and empty rather than
    absent, which keeps a structured log line's shape stable across records.
    """
    for key, item in value.items():
        if item is None or type(item) in _METADATA_SCALARS:
            continue
        raise ValueError(
            f"metadata[{key!r}] must be a plain int/float/str/bool or None, got "
            f"{type(item).__name__} ({item!r}). NumPy scalars are the usual cause: "
            "they reach here from indicator maths and would be persisted, and "
            "serialised into logs, as a repr like 'np.float64(1.5)' rather than "
            "failing. Convert with float(x) / int(x) at the strategy boundary."
        )
    return value


#: ``Signal.metadata``: a str-keyed mapping of plain scalars. Keys are enforced
#: by pydantic from the ``dict[str, object]`` annotation; the values are what
#: this guard covers. ``AfterValidator`` so the dict shape is already validated.
Metadata = Annotated[dict[str, object], AfterValidator(_reject_exotic_metadata)]


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True)


class Candle(_Frozen):
    """A single OHLCV bar for one symbol/timeframe."""

    symbol: str
    timeframe: str
    open_time: datetime
    close_time: datetime
    open: Money
    high: Money
    low: Money
    close: Money
    volume: Money
    is_closed: bool = True


class Ticker(_Frozen):
    """Latest best bid/ask and last price for a symbol."""

    symbol: str
    bid: Money
    ask: Money
    last: Money
    timestamp: datetime

    @property
    def mid(self) -> Decimal:
        return (self.bid + self.ask) / Decimal(2)


class Balance(_Frozen):
    """Free and locked balance for a single asset."""

    asset: str
    free: Money
    locked: Money

    @property
    def total(self) -> Decimal:
        return self.free + self.locked


class MarketLotSize(_Frozen):
    """The ``MARKET_LOT_SIZE`` filter. Optional -- not every symbol reports it.

    Binance applies this filter to orders that execute *at market*. Whether it
    also binds an order that becomes a market order on trigger -- a
    ``STOP_LOSS`` -- is **not stated** by the exchange response or by
    ``python-binance``, both of which carry the values and no semantics. Sizing
    therefore takes the stricter of this and ``LOT_SIZE`` rather than guessing;
    see :attr:`SymbolInfo.effective_step_size`.

    **The "0 means no constraint" convention is per-field, not filter-wide.**
    ``min_qty`` and ``step_size`` follow it. ``max_qty`` does **not**: a symbol
    can report a real maximum alongside zeroed min/step, and both Binance Spot
    Testnet and mainnet do exactly that for BTCUSDT. Applying one rule to all
    three would either discard a live maximum or refuse every trade.

    ``max_qty`` is therefore parsed for fidelity to the wire and deliberately
    **not read**: nothing in this system enforces a maximum quantity today, and
    ``limits.max_position_size_percent`` already bounds size from above. It is
    here so the mapper is tested against the whole filter rather than a
    convenient subset.
    """

    min_qty: Money  # MARKET_LOT_SIZE minQty; 0 means unconstrained
    max_qty: Money  # MARKET_LOT_SIZE maxQty; parsed, not read -- see above
    step_size: Money  # MARKET_LOT_SIZE stepSize; 0 means unconstrained


class PercentPriceBySide(_Frozen):
    """The ``PERCENT_PRICE_BY_SIDE`` filter. Optional -- not every symbol has it.

    Bounds every order price to a band around the *average* price of the last
    :attr:`avg_price_mins` minutes, evaluated at submission. A violation refuses
    the **whole order list**, so a take-profit that drifts outside kills the
    entry and the stop with it.

    **Four multipliers, not two.** BTCUSDT and ETHUSDT both report a symmetric
    band -- ``2`` up and ``0.5`` down on each side -- and collapsing the four
    fields to two would encode that symmetry as a property of the *filter*
    rather than of those two symbols. It is not one: the wire carries a
    per-side structure and nothing promises the sides agree. Same
    fidelity-to-the-wire reasoning that keeps :attr:`MarketLotSize.max_qty`
    parsed and unread.

    **``Decimal``, not ``Money``.** These are ratios that will multiply a price,
    not prices. ``Money`` exists to stop a price being built from a float;
    applying it to a band multiplier is a category error, and the same logic
    already types ``max_entry_slippage`` as a plain ``Decimal``. The wire sends
    them **unpadded** -- ``"2"`` and ``"0.5"``, not the eight-place form every
    other decimal on this payload uses -- and both convert exactly.
    """

    bid_multiplier_up: Decimal
    bid_multiplier_down: Decimal
    ask_multiplier_up: Decimal
    ask_multiplier_down: Decimal
    #: Minutes of average price the band is measured against. Arrives as a JSON
    #: number, not a string. It is the measured input to the band-margin
    #: question -- the interval over which the average can move between the bar
    #: close that computes a level and the submission that is judged against it.
    avg_price_mins: int


class SymbolInfo(_Frozen):
    """Trading rules (filters) for a symbol, needed to size and round orders."""

    symbol: str
    base_asset: str
    quote_asset: str
    price_tick: Money  # PRICE_FILTER tickSize
    step_size: Money  # LOT_SIZE stepSize
    min_qty: Money  # LOT_SIZE minQty
    min_notional: Money  # MIN_NOTIONAL / NOTIONAL
    #: ``MARKET_LOT_SIZE``, when the symbol reports it. ``None`` is normal.
    market_lot: MarketLotSize | None = None
    #: ``PERCENT_PRICE_BY_SIDE``, when the symbol reports it. ``None`` is normal.
    percent_price: PercentPriceBySide | None = None
    #: ``MAX_NUM_ALGO_ORDERS.maxNumAlgoOrders``. A protected position costs two
    #: of these -- a stop-market and a take-profit-market. Parsed, not read.
    max_num_algo_orders: int | None = None
    #: ``MAX_NUM_ORDER_LISTS.maxNumOrderLists``. Under the order-list design
    #: every protected position *is* a list, so this is a second ceiling on the
    #: same thing. Parsed, not read -- captured precisely because no design
    #: document mentions it, which is how a ceiling gets discovered by hitting
    #: it. Both configured symbols report 20.
    max_num_order_lists: int | None = None

    @property
    def effective_step_size(self) -> Decimal:
        """The coarser of the two lot steps -- the conservative one.

        A larger step is stricter, and ``max`` also disposes of the "0 means
        unconstrained" case for free: a zeroed market step can never win.
        """
        if self.market_lot is None:
            return self.step_size
        return max(self.step_size, self.market_lot.step_size)

    @property
    def effective_min_qty(self) -> Decimal:
        """The higher of the two minimum quantities -- the conservative one.

        Same reasoning as :attr:`effective_step_size`: a higher floor is
        stricter, and a zeroed market minimum cannot win.
        """
        if self.market_lot is None:
            return self.min_qty
        return max(self.min_qty, self.market_lot.min_qty)


class OrderRequest(_Frozen):
    """An intent to trade, produced by execution before hitting the exchange."""

    symbol: str
    side: OrderSide
    type: OrderType
    quantity: Money
    price: Money | None = None  # required for LIMIT orders
    stop_price: Money | None = None  # required for STOP/TAKE_PROFIT orders
    client_order_id: str | None = None
    #: What this order asks for, when it asks for something other than the
    #: dispatch default. ``None`` means "not stated", and the mapper's own
    #: default applies -- so every request written before this field existed
    #: keeps behaving exactly as it did. A working ``LIMIT`` leg needs ``FOK``,
    #: which the request had no way to say.
    time_in_force: TimeInForce | None = None


class Order(_Frozen):
    """The exchange's view of an order at a point in time."""

    order_id: str
    symbol: str
    side: OrderSide
    type: OrderType
    status: OrderStatus
    quantity: Money
    filled_quantity: Money = Decimal(0)
    price: Money | None = None
    average_price: Money | None = None
    #: The venue's own quote-currency total for the fill -- the wire's
    #: ``cummulativeQuoteQty``, carried whole rather than only as the quotient
    #: :attr:`average_price` derives from it.
    #:
    #: **THE QUOTIENT IS NOT A LOSSLESS STAND-IN, WHICH IS THE WHOLE REASON
    #: THIS FIELD EXISTS.** ``average_price`` is ``cummulativeQuoteQty /
    #: executedQty``, computed in the ambient ``decimal`` context, so a division
    #: that does not terminate is silently rounded to 28 significant digits
    #: before anything sees it. MEASURED: leg
    #: ``tb1-BTCUSDT-1787982059999-0-SL`` returned
    #: ``75872.09601025202904741563434`` -- **28** significant digits, which is
    #: the context precision exactly, from wire operands of eight or fewer. (An
    #: earlier finding recorded that value as twenty-nine. It is 28, and 29 was
    #: never possible: the default context precision IS 28, so a quotient
    #: cannot exceed it. The wrong number contradicted the mechanism it was
    #: offered as evidence for.) Booking realised P&L needs the TOTAL: proceeds
    #: are a
    #: quote amount the venue has already added up, and re-deriving them by
    #: multiplying a rounded quotient reintroduces the error the exchange's own
    #: accounting does not have.
    #:
    #: **``None`` means THE VENUE DID NOT REPORT IT; zero means it reported
    #: nothing filled.** The two are kept apart deliberately, and this field is
    #: the first in this model to keep them apart: :attr:`filled_quantity`
    #: defaults to ``Decimal(0)`` and so reads identically for an absent key and
    #: a genuine zero.
    #:
    #: **A RESTING PROTECTIVE LEG REPORTS status=NEW, filled_quantity=0 AND
    #: average_price=None** -- MEASURED on 2026-09-02 across two symbols and
    #: both leg types: ``tb1-BTCUSDT-1788347519999-0-SL``,
    #: ``tb1-BTCUSDT-1788347519999-0-TP`` and
    #: ``tb1-ETHUSDT-1788353399999-0-SL``. So **a consumer must branch on
    #: ``status``, never on ``average_price is None``**: absent-because-resting
    #: and absent-because-unreported are the same value, and only ``status``
    #: separates them.
    filled_quote_quantity: Money | None = None
    created_at: datetime | None = None
    client_order_id: str | None = None
    #: The trigger price on a stop-type order. ``None`` on an order that has
    #: none, following ``price``'s convention rather than carrying the
    #: exchange's ``"0.00000000"`` into the domain as a real zero.
    stop_price: Money | None = None
    #: Which order list this order belongs to, or ``None`` when it belongs to
    #: none. The exchange spells "no list" as ``-1``; that is a sentinel, not a
    #: list identity, and it is not carried into the domain.
    order_list_id: str | None = None


class OtocoOrderListRequest(_Frozen):
    """An entry with both protective legs: Q-C section 2's ``stop + TP`` row.

    **Sixteen wire parameters, five domain facts, and the compression is the
    point.** Section 3's OTOCO set spells one quantity twice
    (``workingQuantity`` and ``pendingQuantity``), fixes six values that are
    design constants rather than caller decisions (``workingType=LIMIT``,
    ``workingSide=BUY``, ``workingTimeInForce=FOK``, ``pendingSide=SELL``,
    ``pendingAboveType=TAKE_PROFIT``, ``pendingBelowType=STOP_LOSS``), and
    carries four client order IDs that section 6 makes *derivable*. None of
    those is a fact about the trade, so none is a field here. A domain type
    holding ``pendingAboveStopPrice`` under that name would have leaked the wire
    inward; the mapper owns the spelling.

    **The four forbidden fields are unrepresentable, not rejected.**
    ``pendingAbovePrice``, ``pendingAboveTimeInForce``, ``pendingBelowPrice``
    and ``pendingBelowTimeInForce`` each yield ``-1106``. Both protective legs
    are stop-market, so each carries exactly **one** price here and there is no
    second price field to become a limit; and this type has **no** time-in-force
    field at all. A mapper enumerating these fields has nothing to emit them
    from -- which is stronger than a check, because a check can be deleted.

    **Two types rather than one with an optional take-profit.** Section 2 calls
    the arity branch irreducible, and it dispatches to a different endpoint, so
    the shape is a *type* distinction. An optional field would push that branch
    into every consumer and make "OTOCO with no take-profit" representable --
    a request the venue has no endpoint for.

    They do not share a base. The shared part is five field declarations, not
    logic: the invariants differ, and a public base in the domain layer is a
    decision `CLAUDE.md` records as deliberately deferred.
    """

    symbol: str
    quantity: Money
    #: The working leg's price -- a derived marketable limit, not the bar close.
    entry_limit: Money
    #: The below leg's trigger. Below ``entry_limit`` for a long.
    stop_price: Money
    #: The above leg's trigger. Above ``entry_limit`` for a long.
    take_profit: Money
    #: Identity seed, with :attr:`generation`. Section 6 derives all four client
    #: order IDs from ``(symbol, entry_bar_time, generation, leg)``, so carrying
    #: the IDs themselves would put four wire strings in the domain and create a
    #: second source of truth for something guaranteed derivable.
    entry_bar_time: datetime
    #: Bounded below only. The 0..99 ceiling is derived from the venue's
    #: 36-character client-order-ID limit and lives in ``exchange/ids.py``;
    #: ``core/`` must not encode a venue constraint. A request above it
    #: constructs and fails at ID generation, at the boundary that owns it.
    generation: int = Field(0, ge=0)

    @model_validator(mode="after")
    def _check_invariants(self) -> OtocoOrderListRequest:
        _check_order_list_entry(self.quantity, self.entry_limit, self.entry_bar_time)
        if self.stop_price <= 0:
            raise ValueError(f"stop_price must be > 0, got {self.stop_price}")
        if self.take_profit <= 0:
            raise ValueError(f"take_profit must be > 0, got {self.take_profit}")
        # The ORDERING is what makes the leg assignment unfakeable. Swap the two
        # and the mapper would place the stop above and the target below --
        # accepted by the venue, and the position would be closed at a loss the
        # moment it moved in our favour.
        if self.stop_price >= self.entry_limit:
            raise ValueError(
                f"stop_price {self.stop_price} is not below entry_limit "
                f"{self.entry_limit}; a long's stop is the BELOW leg"
            )
        if self.take_profit <= self.entry_limit:
            raise ValueError(
                f"take_profit {self.take_profit} is not above entry_limit "
                f"{self.entry_limit}; a long's target is the ABOVE leg"
            )
        return self


class OtoOrderListRequest(_Frozen):
    """An entry with a stop and no target: Q-C section 2's ``stop only`` row.

    Thirteen wire parameters, four domain facts. Identical to
    :class:`OtocoOrderListRequest` minus the above leg -- and note the wire
    spelling differs by more than that omission: section 3's OTO set uses the
    plain ``pending*`` prefix where OTOCO uses ``pendingAbove*``/
    ``pendingBelow*``. That difference is the mapper's to know; nothing here
    mirrors it.

    The ``TP only`` row of section 2's table has no type because it is refused
    at config load, and the ``neither`` row has none because it stays a plain
    :class:`OrderRequest` -- M5a gave that type ``time_in_force`` precisely so a
    working ``LIMIT`` leg could ask for ``FOK`` itself.
    """

    symbol: str
    quantity: Money
    entry_limit: Money
    #: The pending leg's trigger. Below ``entry_limit`` for a long.
    stop_price: Money
    #: See :attr:`OtocoOrderListRequest.entry_bar_time`.
    entry_bar_time: datetime
    generation: int = Field(0, ge=0)

    @model_validator(mode="after")
    def _check_invariants(self) -> OtoOrderListRequest:
        _check_order_list_entry(self.quantity, self.entry_limit, self.entry_bar_time)
        if self.stop_price <= 0:
            raise ValueError(f"stop_price must be > 0, got {self.stop_price}")
        if self.stop_price >= self.entry_limit:
            raise ValueError(
                f"stop_price {self.stop_price} is not below entry_limit "
                f"{self.entry_limit}; a long's stop is the BELOW leg"
            )
        return self


def _check_order_list_entry(quantity: Money, entry_limit: Money, entry_bar_time: datetime) -> None:
    """The working-leg invariants both order-list shapes share.

    A free function rather than a shared base class: what the two types have in
    common is these three checks, and factoring the *logic* leaves the field
    declarations readable top-to-bottom in each type.
    """
    if quantity <= 0:
        raise ValueError(f"quantity must be > 0, got {quantity}")
    if entry_limit <= 0:
        raise ValueError(f"entry_limit must be > 0, got {entry_limit}")
    # This field's whole purpose is to seed a RESTART-STABLE identity. A naive
    # value would be read as local time and shift the millisecond segment by the
    # host's offset, so the same bar would derive a different ID on a different
    # machine -- and the recovery path's premise is that it does not.
    if entry_bar_time.tzinfo is None or entry_bar_time.tzinfo.utcoffset(entry_bar_time) is None:
        raise ValueError(f"entry_bar_time must be timezone-aware, got naive {entry_bar_time!r}")


class OrderListEntry(_Frozen):
    """One leg as a ``v3_get_order_list`` read-back reports it: an identity only.

    **Three fields, because the endpoint returns three** -- MEASURED against a
    captured payload: ``{"symbol", "orderId", "clientOrderId"}`` and nothing
    else. No status, no quantity, no price. Q-C section 7's compare set
    (``status``, ``executedQty``, ``origQty``, legally-sendable prices) is
    therefore **not obtainable from a list read-back at all**; it needs a
    per-order query per leg.

    **It does not compete with :class:`~trading_bot.exchange.ids.
    ClientOrderIdParts`, and the rule that keeps it from doing so is that it
    carries the RAW ``client_order_id`` string and none of the parsed fields.**
    The two answer different questions: ``ClientOrderIdParts`` decomposes an ID
    *we generated* into ``(symbol, entry_bar_time, generation, leg)``; this
    records what the *venue* reports. You get the first by parsing the second.
    Duplicating ``leg`` or ``generation`` here would create a second source of
    truth for a fact the ID already carries.
    """

    symbol: str
    order_id: str
    client_order_id: str


class OrderList(_Frozen):
    """An order list as the ``v3_get_order_list`` read-back reports it.

    **Scoped to the READ-BACK, deliberately.** The placement response is a
    different shape and its leg array is UNMEASURED -- ``orderReports`` is a
    measured *absence* from this endpoint and an assumption about that one. The
    two are not unified here on the strength of a guess; a placement-response
    mapper is separate work behind a separate measurement.

    **What is carried is what Q-C section 7 compares**, and the omissions are
    decisions rather than gaps.

    ``contingencyType`` is **deliberately absent.** It reads ``"OTO"`` on every
    payload of *both* shapes and never once ``"OTOCO"`` (MEASURED), so its only
    measured property is that it is uninformative -- and a consumer that
    switched on it would read every OTOCO list as an OTO, seeing two legs where
    three exist. Section 7 fixes shape identification to **leg count or our own
    IDs**, and the leg suffix in a ``tb1-`` ID is what makes the second
    available. Carrying a field whose only use is a wrong one is an invitation;
    leaving it out makes the misuse unrepresentable.

    ``price`` and ``timeInForce`` on a stop-market leg are excluded from
    comparison for a different reason and are still present on :class:`Order`:
    section 3 forbids *sending* them, so the values returned are the venue's own
    defaults and there is nothing of ours to compare them against. That is a
    rule for whoever compares, not a reason to drop fields from the leg model.
    """

    order_list_id: str
    symbol: str
    #: **``None`` carries no meaning.** The placement response returns this as
    #: ``null`` deterministically when a list terminates in the same call, while
    #: the leg IDs in that same payload are correct (MEASURED, T1). Absence is a
    #: property of the response shape, not of the list -- which costs nothing,
    #: because the value is derived from seeds and we always know what we sent.
    list_client_order_id: str | None = None
    #: Carried as text, not an enum. Measured members exist (``EXEC_STARTED``,
    #: ``ALL_DONE``, ``EXECUTING``) but the full set is not established, and
    #: nothing branches on them yet -- so an enum here would ship members
    #: without writers and a default direction nobody had chosen.
    list_status_type: str | None = None
    list_order_status: str | None = None
    #: A tuple, because this model is frozen and a list would not be. Empty is a
    #: real state -- a payload with no leg array -- but on the measured read-back
    #: shape it is NOT the normal case: a captured three-leg list maps to three
    #: entries, and zero from a payload that has legs is the M5d-053 defect.
    orders: tuple[OrderListEntry, ...] = ()


class Trade(_Frozen):
    """A completed fill (or an aggregated round-trip in backtests)."""

    symbol: str
    side: OrderSide
    quantity: Money
    price: Money
    fee: Money = Decimal(0)
    fee_asset: str = ""
    timestamp: datetime = Field(default_factory=_utcnow)
    order_id: str | None = None
    pnl: Money | None = None  # realized P&L when this fill closes exposure


class Position(BaseModel):
    """An open position and its protective levels. Mutable by design.

    ``validate_assignment`` is what makes the ``Money`` guard survive that
    mutability. Pydantic validates at construction only unless asked otherwise,
    so without it ``position.trailing_stop = 98.5`` stores a binary ``float`` in
    a ``Money`` field -- silently, and on the one model in the domain that is
    written to on every bar. The trailing stop is advanced from a NumPy-derived
    world, which is exactly the leak path ``_reject_float`` exists to close, so
    the guard has to cover the write and not just the birth.

    Note for anyone adding a cross-field validator here: with
    ``validate_assignment`` on, a ``model_validator(mode="after")`` re-runs on
    *every* assignment. ``RiskManager.advance_trailing_stop`` writes
    ``highest_price`` and ``trailing_stop`` in two separate statements, so such a
    validator would see the intermediate state between them. The fix is to
    collapse those writes into **one method on this class**, so the invariant
    holds at every point an outside caller can observe. Do *not* weaken the
    validator to tolerate partial state: an invariant that accepts the halfway
    position is not an invariant, and it would silently accept a trailing stop
    that had genuinely drifted away from its high-water mark.

    **Two timestamps, and they answer different questions.** ``opened_at`` is
    wall-clock: when this process created the object. ``entry_bar_time`` is the
    close time of the bar the entry was decided on, and it is what seeds a
    deterministic client order ID -- so it must survive a restart, which
    ``opened_at`` does not. Neither replaces the other.
    """

    model_config = ConfigDict(validate_assignment=True)

    symbol: str
    side: PositionSide
    quantity: Money
    #: What was REQUESTED: the marketable limit sent to the venue. **Not what
    #: the entry filled at** -- see :attr:`entry_fill_price`. Kept unchanged
    #: because the protective geometry was derived from it: a stop is below
    #: THIS number and a target above it, and the validators on
    #: :class:`ProtectiveLevels` check exactly that.
    entry_price: Money
    #: What the entry ACTUALLY filled at, or ``None``.
    #:
    #: **P&L is computed against this and never against
    #: :attr:`entry_price`.** MEASURED: the requested limit over-stated the
    #: true fill by 76.65 and 2.09 per unit on the two positions of
    #: 2026-09-02 -- 1.81 and 1.59 USDT of cost the account never paid.
    #: Booking against the request would write that distortion into a durable
    #: ledger, where it is afterwards indistinguishable from a correct figure.
    #:
    #: **``None`` IS THREE DIFFERENT FACTS SHARING ONE VALUE, and a reader
    #: must not collapse them:**
    #:
    #: 1. **The query failed** -- a timeout, a transport error, or the venue
    #:    not answering. The entry may well have filled; we do not know at
    #:    what.
    #: 2. **The leg reported no fill** -- the working leg is ``LIMIT``+``FOK``,
    #:    so it either filled at once or expired. An expired one leaves a
    #:    position that should not exist; see the note at
    #:    ``OrderExecutor._open_position``.
    #: 3. **Nothing ever queried** -- a construction site that takes the
    #:    default. Every fixture, and every position built before the query
    #:    existed.
    #:
    #: They are not distinguished here and this field cannot distinguish
    #: them. What they share is the only thing a consumer may act on: **the
    #: cost basis is unknown**, so :meth:`unrealized_pnl` raises rather than
    #: substituting a number. Telling them apart needs the log line at the
    #: site that failed.
    entry_fill_price: Money | None = None
    #: Close time of the bar this entry was decided on. Deterministic across a
    #: restart, unlike :attr:`opened_at`, which is why it -- not ``opened_at``
    #: -- seeds a derivable client order ID.
    entry_bar_time: datetime
    #: What is known about this position's protective orders. **Required and
    #: non-nullable on purpose:** the tempting default asserts "no protection is
    #: expected here", which switches the divergence detector off for this
    #: position, and a site that forgot the field would be one the reconciler
    #: had been told to ignore -- instructed by nobody.
    protection: ProtectionState
    #: Wall-clock creation time of this object. Not restart-stable; see
    #: :attr:`entry_bar_time`.
    opened_at: datetime = Field(default_factory=_utcnow)
    #: **OUR derived ``listClientOrderId`` -- ``tb1-BTCUSDT-<ms>-0-L`` -- and
    #: NOT the exchange's own identity.** This line read *"the exchange's
    #: order-list identity"* until M5h and was false: both writers pass
    #: :attr:`OrderList.list_client_order_id`, which is the id WE computed from
    #: Q-C section 6's seeds and sent, and the venue never issues one.
    #:
    #: **The two identifier spaces are distinct and conflating them has already
    #: cost this project a live defect.** ``classify_protection`` compared this
    #: field against the venue's numeric ``orderListId`` and read every
    #: correctly protected position as ``DIVERGED`` -- 28 consecutive false
    #: verdicts in run 1, fixed at ``3970968``. Both are ``str | None`` there,
    #: so no type could see it. Here they cannot be confused by type either:
    #: this is ``str`` and :attr:`venue_order_list_id` is ``int``.
    order_list_id: str | None = None
    #: **THE VENUE'S OWN numeric ``orderListId``** -- ``255471`` in the first
    #: live run -- as distinct from :attr:`order_list_id` directly above.
    #:
    #: It exists because the cancel endpoint takes THIS one. ``DELETE
    #: /api/v3/orderList`` is addressed by ``orderListId``, so a close path
    #: holding only our derived id cannot cancel the list it is closing, and
    #: would have to spend an extra enumeration to find the number.
    #:
    #: ``int`` rather than ``str``, and the type is doing work: it makes the two
    #: spaces **structurally** unconfusable, where two ``str`` fields would sit
    #: side by side inviting exactly the substitution that produced run 1's
    #: defect. The adapter already round-trips the value through ``int`` when it
    #: addresses a list by number, so nothing is lost.
    #:
    #: **``None`` covers TWO DIFFERENT FACTS and a reader must not collapse
    #: them.** *No list was identified* -- the ``PLACED_LIVE`` branch found
    #: several matches or none live, so it takes neither id and both fields are
    #: ``None`` together. Or *the construction site supplied none* -- a test, or
    #: a future caller. What it never means is "the venue issued no id": every
    #: :class:`OrderList` carries one, because ``to_order_list`` reads
    #: ``orderListId`` as a required key.
    venue_order_list_id: int | None = None
    #: When this position was last read back from the exchange. ``None`` means
    #: never, which is what a freshly opened position reports until the first
    #: reconciliation pass reaches it.
    last_reconciled_at: datetime | None = None
    stop_loss: Money | None = None
    take_profit: Money | None = None
    trailing_stop: Money | None = None
    highest_price: Money | None = None  # for trailing-stop bookkeeping (long)
    lowest_price: Money | None = None  # for trailing-stop bookkeeping (short)

    @property
    def is_open(self) -> bool:
        return self.side is not PositionSide.FLAT and self.quantity > 0

    def unrealized_pnl(self, price: Decimal) -> Decimal:
        """Mark-to-market P&L at ``price`` (quote currency).

        **Computed against :attr:`entry_fill_price`, never
        :attr:`entry_price`.** The requested limit is not what the account
        paid, and this figure reaches a durable ledger through
        ``Portfolio.close_position``.

        :raises ValueError: :attr:`entry_fill_price` is ``None``.

        **FAIL CLOSED, and the alternative was rejected on its error
        direction.** Falling back to ``entry_price`` would always produce a
        number, and that number is wrong by a MEASURED amount in a direction
        that over-states a loss -- conservative for the daily-loss limit, and
        permanent once written. A raise costs a refused booking, which is
        visible and recoverable; a silent fallback corrupts a file that
        survives every restart and cannot be told apart from a correct one
        afterwards.

        ``ValueError`` rather than a ``TradingBotError``, following
        ``_require_positive`` in ``risk/rules.py`` and the twenty-five sites
        in this module: those types are venue and config conditions a caller
        catches and acts on, where this is an invariant violation -- an
        unpriceable position reached a pricing call, which is a defect in the
        caller, not a market state.
        """
        if self.entry_fill_price is None:
            raise ValueError(
                f"{self.symbol} has no entry_fill_price, so its cost basis is unknown and "
                "P&L cannot be computed. This is one of three states -- the fill query "
                "failed, the working leg reported no fill, or nothing ever queried -- and "
                "the requested entry_price is NOT a substitute: it is measured wrong by up "
                "to 76.65 per unit and would write a permanent distortion into the ledger"
            )
        if self.side is PositionSide.LONG:
            return (price - self.entry_fill_price) * self.quantity
        if self.side is PositionSide.SHORT:
            return (self.entry_fill_price - price) * self.quantity
        return Decimal(0)

    def record_reconciliation(self, *, protection: ProtectionState, at: datetime) -> None:
        """Record what a reconciliation pass found, and when.

        **One method rather than two assignments**, which is what this class's
        note above prescribes for every multi-field write: with
        ``validate_assignment`` on, two statements are observable between each
        other, and collapsing them is the prerequisite for any cross-field
        invariant this model might later carry.

        **``protection`` first, the stamp LAST, and the order is the point.** A
        write interrupted between them leaves the position reading *never
        reconciled* rather than *reconciled but stale* -- and the stamp is what
        the staleness refusal trusts, so a stamp landing ahead of the state it
        summarises would claim currency for a fact not yet written. Erring
        toward "never" costs a re-read; erring toward "current" costs the
        refusal that would have caught it.

        **This ordering is UNPROVABLE by mutation, and is done for the reason
        above rather than because a test demands it.** Both assignments succeed,
        the final state is identical either way, and no fixture can observe the
        instant between two plain assignments without patching the model itself.
        A proof that cannot fail is not a proof, so none is claimed.

        :raises ValueError: ``at`` is naive. A naive value would be read as
            local time and move every staleness comparison by the host's offset.
        """
        if at.tzinfo is None or at.tzinfo.utcoffset(at) is None:
            raise ValueError(f"record_reconciliation requires an aware datetime, got {at!r}")
        self.protection = protection
        self.last_reconciled_at = at

    def record_partial_reconciliation(self, *, protection: ProtectionState) -> None:
        """Record what was learned, and DELIBERATELY not the stamp.

        **This is the first deliberate use of the ordering ruled unprovable
        above.** That ruling prefers "never reconciled" to "reconciled but
        stale" for a write interrupted between the two fields; this method
        produces exactly that state on purpose and durably, for a position
        whose protective legs could not all be resolved. The state the ordering
        was chosen to favour therefore becomes observable -- and testable --
        for the first time.

        Note precisely what that does and does not buy, because the tempting
        over-statement is one notch stronger than the truth: the *ordering*
        remains unprovable, since swapping the two assignments inside
        :meth:`record_reconciliation` is still unobservable. What is now
        observable is the *state*, not the sequence that reaches it.

        **A sibling method rather than a flag on the other one.** A boolean
        parameter that silently changes which fields a method writes is a
        second meaning hidden inside one name; a caller reading
        ``record_reconciliation(..., stamp=False)`` learns nothing about why.
        This name says what happened, and greps as the deliberate case.

        **The consequence is the point, not a side effect.** An unstamped
        position is maximally stale by every reader of
        ``last_reconciled_at``, is always due, and sorts first -- so the next
        pass visits it before anything else and the reservation fires early
        enough to leave a query for it. The stamp is the state; nothing else
        has to remember.
        """
        self.protection = protection


class SizingDecision(_Frozen):
    """How much to trade -- or, when the answer is nothing, why.

    Returned by :meth:`trading_bot.core.interfaces.RiskManager.size_position`.

    A quantity of zero is a **normal, expected** outcome, not an error: an
    account too small to clear a symbol's ``min_notional`` produces one on every
    signal, and raising there would turn a routine condition into exception
    control flow in the hot path. Returning a bare ``Decimal(0)`` instead would
    be silent -- arithmetic carries it forward happily. Wrapping the number is
    what makes zero safe: a caller cannot reach ``quantity`` without also seeing
    ``reason``, and cannot hand this object to an ``OrderRequest`` by accident.

    ``requested_quantity`` is the size the configured method asked for, before
    the ``max_position_size_percent`` cap and before lot rounding. It is what
    answers an operator's first question -- "how close were we?" -- numerically,
    rather than by parsing it back out of ``reason``.
    """

    symbol: str
    quantity: Money  # exchange-compliant; Decimal(0) means "do not trade"
    requested_quantity: Money  # pre-cap, pre-rounding size, for diagnostics
    reason: str

    @property
    def is_tradeable(self) -> bool:
        """``True`` when this decision authorises a non-zero order."""
        return self.quantity > 0

    @model_validator(mode="after")
    def _check_invariants(self) -> SizingDecision:
        """Enforce the three things a caller is entitled to assume.

        The last one is the load-bearing check: sizing may cap and may round,
        and both only ever *reduce*. Asserting ``quantity <= requested_quantity``
        here makes "sizing never rounds up" a property of the type rather than a
        claim in a docstring -- a rounding bug that inflated an order would fail
        at construction instead of at the exchange.
        """
        if self.quantity < 0:
            raise ValueError(f"quantity must not be negative, got {self.quantity}")
        if self.requested_quantity < 0:
            raise ValueError(
                f"requested_quantity must not be negative, got {self.requested_quantity}"
            )
        if not self.reason:
            raise ValueError("reason must explain the decision, including a zero quantity")
        if self.quantity > self.requested_quantity:
            raise ValueError(
                f"quantity {self.quantity} exceeds requested {self.requested_quantity}; "
                "sizing may cap and round down, never up"
            )
        return self


class ProtectiveLevels(_Frozen):
    """The stop-loss and take-profit computed for a position at entry.

    ``None`` for either level is a legitimate, expected outcome (the rule is
    disabled in config), representable rather than smuggled as a sentinel price.
    The ``Money`` field types mean no level can be built from a ``float``.
    """

    symbol: str
    side: PositionSide
    entry_price: Money
    stop_loss: Money | None = None
    take_profit: Money | None = None
    #: Realized (post-rounding) ``|entry - stop_loss|``; what an ``rr`` take-profit
    #: and ``risk_per_trade`` sizing must both use. ``None`` iff no stop.
    stop_distance: Money | None = None
    basis: str

    @model_validator(mode="after")
    def _check_sides(self) -> ProtectiveLevels:
        """Make "levels sit on the correct side of entry" a property of the type.

        **``entry_price`` HERE IS THE REQUESTED LIMIT AND MUST STAY THAT WAY.**
        This type carries its own ``entry_price`` and has no fill price; the
        one :class:`Position` gained at M5h is a different field on a
        different type. Substituting a fill price would be wrong even if one
        were available: these levels were DERIVED from the request, so a stop
        placed correctly below the requested limit could fail this check
        merely because the entry filled lower than it.
        """
        if self.side is PositionSide.LONG:
            if self.stop_loss is not None and not self.stop_loss < self.entry_price:
                raise ValueError(
                    f"long stop_loss {self.stop_loss} must be below entry {self.entry_price}"
                )
            if self.take_profit is not None and not self.take_profit > self.entry_price:
                raise ValueError(
                    f"long take_profit {self.take_profit} must be above entry {self.entry_price}"
                )
        elif self.side is PositionSide.SHORT:
            if self.stop_loss is not None and not self.stop_loss > self.entry_price:
                raise ValueError(
                    f"short stop_loss {self.stop_loss} must be above entry {self.entry_price}"
                )
            if self.take_profit is not None and not self.take_profit < self.entry_price:
                raise ValueError(
                    f"short take_profit {self.take_profit} must be below entry {self.entry_price}"
                )
        else:
            raise ValueError("ProtectiveLevels requires an open long or short position")

        if (self.stop_loss is None) != (self.stop_distance is None):
            raise ValueError("stop_loss and stop_distance must both be set or both be None")
        if self.stop_loss is not None and self.stop_distance is not None:
            expected = abs(self.entry_price - self.stop_loss)
            if self.stop_distance != expected:
                raise ValueError(f"stop_distance {self.stop_distance} != |entry - stop| {expected}")
        return self


class RiskDecision(_Frozen):
    """Whether acting on a signal respects the configured risk limits -- and if
    not, which rule refused it.

    Carried on :attr:`~trading_bot.core.assessment.RiskAssessment.decision`,
    reached through
    :meth:`~trading_bot.core.interfaces.RiskManager.evaluate`. The limit check
    returned a bare ``bool`` until Phase 5 M3. The change applies the same rule
    :class:`SizingDecision` and ``ProtectiveLevels`` already follow: "no trade"
    is a frozen value object carrying its reason, never a bare sentinel. A
    ``False`` tells an operator that the bot will not enter; it cannot tell them
    the account is halted for the day rather than merely at its position cap,
    and those two demand completely different responses.

    ``rule`` is set on refusal and ``None`` on approval, so the two fields
    cannot drift: a rejection always names the rule that fired, enforced below
    rather than asserted in a docstring.
    """

    symbol: str
    approved: bool
    reason: str
    rule: RiskRule | None = None

    @model_validator(mode="after")
    def _check_invariants(self) -> RiskDecision:
        if not self.reason:
            raise ValueError("reason must explain the decision, including an approval")
        if self.approved != (self.rule is None):
            raise ValueError(
                f"approved={self.approved} contradicts rule={self.rule!r}; a refusal "
                "must name the rule that fired and an approval must name none"
            )
        return self


class Signal(_Frozen):
    """A strategy's decision for one symbol on one candle."""

    symbol: str
    action: SignalAction
    timestamp: datetime = Field(default_factory=_utcnow)
    price: Money | None = None  # reference price at signal time
    strength: float = 1.0  # 0..1 confidence, strategy-defined
    reason: str = ""  # human-readable explanation for logs
    metadata: Metadata = Field(default_factory=dict)
