"""The D1 trailing stop as a pure function (N4a, ruling R-EA).

D1's exit is a single trailing ``STOP_LOSS`` sell. On the venue it has a ``trailingDelta`` in basis
points and no ``stopPrice``, so it begins tracking at the next trade and triggers when the price
has fallen ``delta`` basis points from the highest trade price since submission. This module walks
the 1m path of one position and says where that trail is hit. It reads nothing, writes nothing and
has no clock: the bars are handed in, every figure is a ``Decimal``, and the same arguments give the
same answer.

**The rules, each with its source.**

* **The trigger** is ``peak x (1 - delta / 10000)`` (R-EA; the Binance trailing-stop FAQ's 700 BIPS
  from 45,500 is 42,315). ``delta`` is an integer number of basis points that the caller has already
  rounded down and clamped (D1); this module only refuses one that cannot make a trigger.
* **The peak starts at the entry fill price** (R-EA (1)) and **the entry minute's high counts toward
  it** (R-EB, which corrects P143's reading that only the fill price counted): trades earlier in the
  minute may have come before the fill, the documentation does not settle them, and R-EB takes the
  earlier exit. That minute's low is tested against the trigger from that peak, and a hit exits at
  the trigger less the slippage. The open of the entry minute predates the position, so that minute
  has no gap case.
* **Each later bar** first tests its open against the trigger in force BEFORE the bar: an open at or
  below it is a gap, the fill is the open less the slippage (R-EA (2), the fill model's R-P1 and
  R-W), the gap flag is set, and the bar's high does not enter the peak. Otherwise the peak takes the
  bar's high, the trigger is recomputed, and a low at or below the new trigger exits at that trigger
  less the slippage. The order of a minute's high and low is unknown, so a bar that makes a new peak
  and trades below the new trigger exits (R-EA (1)): the bias is toward more and earlier exits.
* **A low exactly at the trigger triggers**, as the fill model has it for a stop, and an open exactly
  at it is a gap.
* **The slippage** is a whole percent in the fill model's convention (1.20 is 1.20%), charged against
  the seller. Prices are not rounded to the tick (R-AB).
* **The first exit ends the walk** and the iterator is not advanced past it. A path that ends first is
  ``OPEN`` with the peak so far; an empty path is ``OPEN`` with the fill price as the peak.

**What this module does not know.** A missing minute in the path, partial execution, fees and the
size of the position are the caller's (charter section 16, reading 6, and R-EA (3) and (4)).
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime, timedelta
from decimal import Decimal
from enum import Enum

from pydantic import BaseModel, ConfigDict, model_validator

from trading_bot.core.models import Candle, Money

__all__ = ["TrailOutcome", "TrailStatus", "resolve_trail", "trigger_price"]

_ONE = Decimal(1)
_HUNDRED = Decimal(100)
_BASIS_POINTS = Decimal(10000)
_MAX_DELTA_BPS = 9999
_MINUTE = timedelta(minutes=1)


class TrailStatus(str, Enum):
    """Whether the trail was hit before the path ended."""

    OPEN = "open"
    EXITED = "exited"


class TrailOutcome(BaseModel):
    """Where the trail was hit, or that it was not.

    ``exit_minute`` is the open time of the bar on which the exit happened, ``exit_price`` the fill
    price, ``gap`` whether the fill was a gapped open, and ``peak`` the highest price the trail had
    seen at that point. For an ``OPEN`` outcome there is no exit minute and no exit price, the gap
    flag is clear, and ``peak`` is the peak at the end of the path.
    """

    model_config = ConfigDict(frozen=True)

    status: TrailStatus
    exit_minute: datetime | None
    exit_price: Money | None
    gap: bool
    peak: Money

    @model_validator(mode="after")
    def _check_shape(self) -> TrailOutcome:
        exited = self.status is TrailStatus.EXITED
        if exited != (self.exit_minute is not None and self.exit_price is not None):
            raise ValueError(
                "an exited trail has an exit minute and price, an open one has neither"
            )
        if not exited and (self.exit_minute is not None or self.exit_price is not None or self.gap):
            raise ValueError("an open trail has no exit minute, no exit price and no gap")
        return self


def _require_decimal(name: str, value: Decimal) -> None:
    if type(value) is not Decimal:
        raise TypeError(f"{name} must be a Decimal, not {type(value).__name__}")
    if not value.is_finite():
        raise ValueError(f"{name} must be finite, got {value}")


def _require_delta(delta_bps: int) -> None:
    if type(delta_bps) is not int:
        raise TypeError(f"delta_bps must be an int, not {type(delta_bps).__name__}")
    if not 1 <= delta_bps <= _MAX_DELTA_BPS:
        raise ValueError(f"delta_bps must be between 1 and {_MAX_DELTA_BPS}, got {delta_bps}")


def _require_aware(name: str, moment: datetime) -> None:
    if moment.tzinfo is None:
        raise ValueError(f"{name} must be timezone-aware")


def trigger_price(peak: Decimal, delta_bps: int) -> Decimal:
    """The price at which a trail ``delta_bps`` basis points below ``peak`` triggers.

    :raises TypeError: ``peak`` is not a ``Decimal`` or ``delta_bps`` is not an ``int``.
    :raises ValueError: ``peak`` is not positive and finite, or ``delta_bps`` is outside 1..9999.
    """
    _require_decimal("peak", peak)
    if peak <= 0:
        raise ValueError(f"peak must be positive, got {peak}")
    _require_delta(delta_bps)
    return peak * (_ONE - Decimal(delta_bps) / _BASIS_POINTS)


def _sell_at(price: Decimal, stop_slippage_percent: Decimal) -> Decimal:
    return price * (_ONE - stop_slippage_percent / _HUNDRED)


def _exited(minute: datetime, price: Decimal, gap: bool, peak: Decimal) -> TrailOutcome:
    return TrailOutcome(
        status=TrailStatus.EXITED, exit_minute=minute, exit_price=price, gap=gap, peak=peak
    )


def _check_bar(bar: Candle, previous_open: datetime | None) -> None:
    if bar.timeframe != "1m":
        raise ValueError(f"the trail walks 1m bars, got a {bar.timeframe!r} bar")
    _require_aware("a bar's open time", bar.open_time)
    if previous_open is not None and bar.open_time <= previous_open:
        raise ValueError(
            f"bar open times must strictly increase: {bar.open_time} follows {previous_open}"
        )


def resolve_trail(
    *,
    entry_time: datetime,
    entry_price: Decimal,
    delta_bps: int,
    stop_slippage_percent: Decimal,
    bars: Iterable[Candle],
) -> TrailOutcome:
    """Walk ``bars`` from the entry minute and say where the trail is hit, or that it is not.

    :param entry_time: the instant of the entry fill, inside the first bar's minute.
    :param entry_price: the entry fill price, the first peak.
    :param delta_bps: the trail in integer basis points, already rounded and clamped by D1.
    :param stop_slippage_percent: the adverse move on the exit, a whole percent in [0, 100).
    :param bars: 1m bars in strictly increasing order, the first being the entry minute.
    :raises TypeError: a figure has the wrong type (a ``float`` among them).
    :raises ValueError: a figure is out of range, a time is naive, a bar is not a 1m bar, the bars
        do not strictly increase, or the first bar's minute does not contain ``entry_time``.
    """
    _require_aware("entry_time", entry_time)
    _require_decimal("entry_price", entry_price)
    if entry_price <= 0:
        raise ValueError(f"entry_price must be positive, got {entry_price}")
    _require_delta(delta_bps)
    _require_decimal("stop_slippage_percent", stop_slippage_percent)
    if not 0 <= stop_slippage_percent < _HUNDRED:
        raise ValueError(
            f"stop_slippage_percent must be at least 0 and below 100, got {stop_slippage_percent}"
        )

    peak = entry_price
    previous_open: datetime | None = None
    for bar in bars:
        _check_bar(bar, previous_open)
        if previous_open is None:
            if not bar.open_time <= entry_time < bar.open_time + _MINUTE:
                raise ValueError(
                    f"entry_time {entry_time} is not inside the first bar's minute {bar.open_time}"
                )
            peak = max(peak, bar.high)
            trigger = trigger_price(peak, delta_bps)
            if bar.low <= trigger:
                return _exited(bar.open_time, _sell_at(trigger, stop_slippage_percent), False, peak)
        else:
            trigger = trigger_price(peak, delta_bps)
            if bar.open <= trigger:
                return _exited(bar.open_time, _sell_at(bar.open, stop_slippage_percent), True, peak)
            peak = max(peak, bar.high)
            trigger = trigger_price(peak, delta_bps)
            if bar.low <= trigger:
                return _exited(bar.open_time, _sell_at(trigger, stop_slippage_percent), False, peak)
        previous_open = bar.open_time
    return TrailOutcome(
        status=TrailStatus.OPEN, exit_minute=None, exit_price=None, gap=False, peak=peak
    )
