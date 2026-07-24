"""Small, dependency-light, pure helpers.

Kept free of exchange/pandas imports so they are trivially unit-testable and
usable from anywhere (including at import time).
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import ROUND_DOWN, Decimal

# Binance timeframe strings -> milliseconds.
_TIMEFRAME_MS: dict[str, int] = {
    "1m": 60_000,
    "3m": 180_000,
    "5m": 300_000,
    "15m": 900_000,
    "30m": 1_800_000,
    "1h": 3_600_000,
    "2h": 7_200_000,
    "4h": 14_400_000,
    "6h": 21_600_000,
    "8h": 28_800_000,
    "12h": 43_200_000,
    "1d": 86_400_000,
    "3d": 259_200_000,
    "1w": 604_800_000,
}


def utc_now() -> datetime:
    """Timezone-aware current UTC time."""
    return datetime.now(timezone.utc)


def timeframe_to_ms(timeframe: str) -> int:
    """Convert a Binance interval string (e.g. ``"15m"``) to milliseconds."""
    try:
        return _TIMEFRAME_MS[timeframe]
    except KeyError as exc:
        raise ValueError(f"Unsupported timeframe: {timeframe!r}") from exc


def round_step_size(quantity: Decimal, step_size: Decimal) -> Decimal:
    """Round ``quantity`` DOWN to a multiple of ``step_size``.

    Binance rejects orders whose quantity is not a multiple of the symbol's
    LOT_SIZE ``stepSize``. Rounding down (never up) guarantees we never try to
    trade more than intended.
    """
    if step_size <= 0:
        return quantity
    return (quantity / step_size).to_integral_value(rounding=ROUND_DOWN) * step_size


def round_price(price: Decimal, tick_size: Decimal) -> Decimal:
    """Round ``price`` DOWN to the symbol's PRICE_FILTER ``tickSize``."""
    if tick_size <= 0:
        return price
    return (price / tick_size).to_integral_value(rounding=ROUND_DOWN) * tick_size


def round_to_tick(price: Decimal, tick_size: Decimal, *, rounding: str) -> Decimal:
    """Round ``price`` to a multiple of ``tick_size`` using ``rounding``.

    ``rounding`` is a ``decimal`` rounding mode (e.g. ``ROUND_FLOOR`` /
    ``ROUND_CEILING``). :func:`round_price` is the fixed-``ROUND_DOWN`` special
    case used by order dispatch; protective-exit levels instead choose the
    direction per level -- a stop rounds *toward its reference* so the realized
    distance never exceeds the configured one -- so they call this directly. As
    with :func:`round_price`, a non-positive ``tick_size`` is a no-op.
    """
    if tick_size <= 0:
        return price
    return (price / tick_size).to_integral_value(rounding=rounding) * tick_size


def clamp(value: float, low: float, high: float) -> float:
    """Constrain ``value`` to the inclusive range ``[low, high]``."""
    return max(low, min(value, high))
