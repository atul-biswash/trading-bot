"""The D1 trailing distance a candidate fixes at signal time (N4b, charter section 17).

``delta = floor(10000 x 3 x ATR(20) / signal-bar close)`` basis points, clamped to ``[10, 2000]``,
fixed when the signal is made and never changed after. The ATR is Wilder's, of the candidate's own
decision timeframe, over the gap-free run of decision bars that ends at the signal bar (the R-DZ
run), so a missing bar never feeds it. It crosses from ``float64`` to ``Decimal`` once, through
``risk.rules._atr_to_decimal``, the named boundary; the close is the signal bar's ``Decimal`` close.

A candidate that cannot form the ATR returns ``None`` and the caller signals nothing. Every
candidate's window is at least 22 rows and the ATR needs 21, so that is a guard and not a state a
signal can be in; ``tests/unit/test_m5n_trail.py`` pins it for all six.

The result rides on ``Signal.metadata`` as two plain values, so the simulated executor reads it from
the signal it is handed and the engine enriches nothing.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from decimal import ROUND_FLOOR, Decimal
from enum import Enum
from typing import TYPE_CHECKING, Final

from trading_bot.indicators.indicators import atr
from trading_bot.risk.rules import _atr_to_decimal

if TYPE_CHECKING:  # pragma: no cover - typing only
    import pandas as pd

__all__ = [
    "MAX_DELTA_BPS",
    "MIN_DELTA_BPS",
    "TRAIL_ATR_PERIOD",
    "TRAIL_CLAMP_KEY",
    "TRAIL_DELTA_KEY",
    "TRAIL_MULTIPLE",
    "TrailClamp",
    "TrailDelta",
    "trail_delta",
]

TRAIL_ATR_PERIOD: Final = 20
TRAIL_MULTIPLE: Final = 3
MIN_DELTA_BPS: Final = 10
MAX_DELTA_BPS: Final = 2000
TRAIL_DELTA_KEY: Final = "trail_delta_bps"
TRAIL_CLAMP_KEY: Final = "trail_clamp"
_BASIS_POINTS: Final = Decimal(10000)


class TrailClamp(str, Enum):
    """Which bound, if any, the raw distance fell outside."""

    NONE = "none"
    UPPER = "upper"
    LOWER = "lower"


@dataclass(frozen=True)
class TrailDelta:
    """The clamped distance in basis points and whether the clamp moved it."""

    bps: int
    clamp: TrailClamp


def trail_delta(run: pd.DataFrame, close: Decimal) -> TrailDelta | None:
    """The trailing distance for a signal on the last row of ``run``, or ``None`` without an ATR.

    :param run: the gap-free run of decision bars ending at the signal bar, with ``high``, ``low``
        and ``close`` columns.
    :param close: the signal bar's ``Decimal`` close.
    :raises ValueError: ``close`` is not positive.
    """
    if close <= 0:
        raise ValueError(f"close must be positive, got {close}")
    if len(run) < TRAIL_ATR_PERIOD + 1:
        return None
    last = float(atr(run["high"], run["low"], run["close"], TRAIL_ATR_PERIOD).iloc[-1])
    if not math.isfinite(last):
        return None
    raw = _BASIS_POINTS * TRAIL_MULTIPLE * _atr_to_decimal(last) / close
    bps = int(raw.to_integral_value(rounding=ROUND_FLOOR))
    if bps > MAX_DELTA_BPS:
        return TrailDelta(MAX_DELTA_BPS, TrailClamp.UPPER)
    if bps < MIN_DELTA_BPS:
        return TrailDelta(MIN_DELTA_BPS, TrailClamp.LOWER)
    return TrailDelta(bps, TrailClamp.NONE)
