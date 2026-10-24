"""R-DZ: windows over a decision series that are gap-free, or are not given at all.

A decision series is a frame of closed bars at one timeframe whose index is each bar's open time.
A bar the venue did not publish is a **gap**: two neighbouring rows more than one bar width apart.
R-DZ rules that an indicator whose window contains a gap yields no value and that no signal is
taken until the window is gap-free. This module answers the two questions that rule needs:

* ``gap_free_tail``: are the last ``bars`` rows consecutive bars, and what are they? A
  non-recursive indicator (a rolling maximum, a simple average, a lagged difference) reads exactly
  that window.
* ``gap_free_run``: where does the gap-free run that ends at the last row begin? A recursive
  indicator (an EMA, a Wilder ATR) is seeded again after a gap, so its window is the whole run, and
  it has no value until the run holds its own warm-up.

Both are conservative: a repeated or out-of-order open time is not one bar width after its
predecessor, so it counts as a gap. Neither fills, interpolates or invents a bar.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Final

import numpy as np

from trading_bot.core.exceptions import DataError

if TYPE_CHECKING:  # pragma: no cover - typing only
    import pandas as pd
    from numpy.typing import NDArray

__all__ = ["BAR_WIDTH_MS", "gap_free_run", "gap_free_tail"]

#: The width of one bar in milliseconds, for the two decision timeframes of M5n. The same figures as
#: ``INTERVAL_MS`` in ``data/historical.py``, which this layer does not import; a test pins them equal.
BAR_WIDTH_MS: Final[dict[str, int]] = {"4h": 14_400_000, "1d": 86_400_000}


def _width(timeframe: str) -> np.timedelta64:
    try:
        return np.timedelta64(BAR_WIDTH_MS[timeframe], "ms")
    except KeyError:
        raise DataError(
            f"not a decision timeframe: {timeframe!r}; expected {sorted(BAR_WIDTH_MS)}"
        ) from None


def _spaced(index: pd.DatetimeIndex, timeframe: str) -> NDArray[np.bool_]:
    """For each row after the first, whether it opens exactly one bar width after the row before."""
    return np.asarray(np.diff(index.values) == _width(timeframe), dtype=np.bool_)


def gap_free_tail(candles: pd.DataFrame, timeframe: str, bars: int) -> pd.DataFrame | None:
    """The last ``bars`` rows if there are that many and they are consecutive bars, else ``None``.

    :raises ValueError: if ``bars < 1``.
    :raises DataError: if ``timeframe`` is not ``"4h"`` or ``"1d"``.
    """
    if bars < 1:
        raise ValueError(f"bars must be >= 1, got {bars}")
    width = _width(timeframe)
    if len(candles) < bars:
        return None
    tail = candles.iloc[-bars:]
    if bool(np.all(np.diff(tail.index.values) == width)):
        return tail
    return None


def gap_free_run(candles: pd.DataFrame, timeframe: str) -> pd.DataFrame:
    """The rows from the most recent gap onward: the gap-free run that ends at the last row.

    The whole frame when there is no gap, and the last row alone when the last row follows one.
    An empty frame is returned as it is.

    :raises DataError: if ``timeframe`` is not ``"4h"`` or ``"1d"``.
    """
    if len(candles) < 2:
        _width(timeframe)
        return candles
    broken = np.nonzero(~_spaced(candles.index, timeframe))[0]
    if broken.size == 0:
        return candles
    return candles.iloc[int(broken[-1]) + 1 :]
