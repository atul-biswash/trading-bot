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

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, model_validator

from trading_bot.core.enums import (
    OrderSide,
    OrderStatus,
    OrderType,
    PositionSide,
    RiskRule,
    SignalAction,
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


class SymbolInfo(_Frozen):
    """Trading rules (filters) for a symbol, needed to size and round orders."""

    symbol: str
    base_asset: str
    quote_asset: str
    price_tick: Money        # PRICE_FILTER tickSize
    step_size: Money         # LOT_SIZE stepSize
    min_qty: Money           # LOT_SIZE minQty
    min_notional: Money      # MIN_NOTIONAL / NOTIONAL


class OrderRequest(_Frozen):
    """An intent to trade, produced by execution before hitting the exchange."""

    symbol: str
    side: OrderSide
    type: OrderType
    quantity: Money
    price: Money | None = None            # required for LIMIT orders
    stop_price: Money | None = None       # required for STOP/TAKE_PROFIT orders
    client_order_id: str | None = None


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
    validator would see the intermediate state between them. Either make the
    invariant tolerant of that, or write both fields in one ``model_copy``.
    """

    model_config = ConfigDict(validate_assignment=True)

    symbol: str
    side: PositionSide
    quantity: Money
    entry_price: Money
    opened_at: datetime = Field(default_factory=_utcnow)
    stop_loss: Money | None = None
    take_profit: Money | None = None
    trailing_stop: Money | None = None
    highest_price: Money | None = None  # for trailing-stop bookkeeping (long)
    lowest_price: Money | None = None   # for trailing-stop bookkeeping (short)

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
    quantity: Money            # exchange-compliant; Decimal(0) means "do not trade"
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


class RiskDecision(_Frozen):
    """Whether acting on a signal respects the configured risk limits -- and if
    not, which rule refused it.

    Returned by :meth:`trading_bot.core.interfaces.RiskManager.approve`, which
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
    price: Money | None = None            # reference price at signal time
    strength: float = 1.0                   # 0..1 confidence, strategy-defined
    reason: str = ""                        # human-readable explanation for logs
    metadata: dict[str, object] = Field(default_factory=dict)
