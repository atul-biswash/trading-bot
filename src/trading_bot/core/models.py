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

from pydantic import BaseModel, ConfigDict, Field


def _utcnow() -> datetime:
    """Timezone-aware UTC now (used as a pydantic default factory)."""
    return datetime.now(timezone.utc)

from trading_bot.core.enums import (
    OrderSide,
    OrderStatus,
    OrderType,
    PositionSide,
    SignalAction,
)


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True)


class Candle(_Frozen):
    """A single OHLCV bar for one symbol/timeframe."""

    symbol: str
    timeframe: str
    open_time: datetime
    close_time: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal
    is_closed: bool = True


class Ticker(_Frozen):
    """Latest best bid/ask and last price for a symbol."""

    symbol: str
    bid: Decimal
    ask: Decimal
    last: Decimal
    timestamp: datetime

    @property
    def mid(self) -> Decimal:
        return (self.bid + self.ask) / Decimal(2)


class Balance(_Frozen):
    """Free and locked balance for a single asset."""

    asset: str
    free: Decimal
    locked: Decimal

    @property
    def total(self) -> Decimal:
        return self.free + self.locked


class SymbolInfo(_Frozen):
    """Trading rules (filters) for a symbol, needed to size and round orders."""

    symbol: str
    base_asset: str
    quote_asset: str
    price_tick: Decimal        # PRICE_FILTER tickSize
    step_size: Decimal         # LOT_SIZE stepSize
    min_qty: Decimal           # LOT_SIZE minQty
    min_notional: Decimal      # MIN_NOTIONAL / NOTIONAL


class OrderRequest(_Frozen):
    """An intent to trade, produced by execution before hitting the exchange."""

    symbol: str
    side: OrderSide
    type: OrderType
    quantity: Decimal
    price: Decimal | None = None            # required for LIMIT orders
    stop_price: Decimal | None = None       # required for STOP/TAKE_PROFIT orders
    client_order_id: str | None = None


class Order(_Frozen):
    """The exchange's view of an order at a point in time."""

    order_id: str
    symbol: str
    side: OrderSide
    type: OrderType
    status: OrderStatus
    quantity: Decimal
    filled_quantity: Decimal = Decimal(0)
    price: Decimal | None = None
    average_price: Decimal | None = None
    created_at: datetime | None = None
    client_order_id: str | None = None


class Trade(_Frozen):
    """A completed fill (or an aggregated round-trip in backtests)."""

    symbol: str
    side: OrderSide
    quantity: Decimal
    price: Decimal
    fee: Decimal = Decimal(0)
    fee_asset: str = ""
    timestamp: datetime = Field(default_factory=_utcnow)
    order_id: str | None = None
    pnl: Decimal | None = None  # realized P&L when this fill closes exposure


class Position(BaseModel):
    """An open position and its protective levels. Mutable by design."""

    symbol: str
    side: PositionSide
    quantity: Decimal
    entry_price: Decimal
    opened_at: datetime = Field(default_factory=_utcnow)
    stop_loss: Decimal | None = None
    take_profit: Decimal | None = None
    trailing_stop: Decimal | None = None
    highest_price: Decimal | None = None  # for trailing-stop bookkeeping (long)
    lowest_price: Decimal | None = None   # for trailing-stop bookkeeping (short)

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


class Signal(_Frozen):
    """A strategy's decision for one symbol on one candle."""

    symbol: str
    action: SignalAction
    timestamp: datetime = Field(default_factory=_utcnow)
    price: Decimal | None = None            # reference price at signal time
    strength: float = 1.0                   # 0..1 confidence, strategy-defined
    reason: str = ""                        # human-readable explanation for logs
    metadata: dict[str, object] = Field(default_factory=dict)
