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
    entry_price: Money
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
    #: The exchange's order-list identity, once one is known.
    order_list_id: str | None = None
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
        """Mark-to-market P&L at ``price`` (quote currency)."""
        if self.side is PositionSide.LONG:
            return (price - self.entry_price) * self.quantity
        if self.side is PositionSide.SHORT:
            return (self.entry_price - price) * self.quantity
        return Decimal(0)


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
        """Make "levels sit on the correct side of entry" a property of the type."""
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
