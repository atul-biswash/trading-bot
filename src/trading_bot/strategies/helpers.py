"""Shared, side-effect-free helpers for strategy implementations.

Every strategy faces the same three chores before it can form an opinion: pull
the close series out of the frame, read the last two values of an indicator, and
decide whether one series crossed another. Writing those three times invites
three subtly different answers to "did it cross?" in software that trades money,
so they live here once.

All functions are pure -- Series and scalars in, plain Python values out.
Nothing here imports the exchange, the engine, or :class:`~decimal.Decimal`:
**no money value passes through this module.** Everything it touches is
``float``, which is correct for indicator maths and wrong for prices, and
keeping the two apart is easier when one module can only ever see one of them.
"""

from __future__ import annotations

from math import isnan
from typing import TYPE_CHECKING

from trading_bot.core.exceptions import DataError

if TYPE_CHECKING:  # pragma: no cover - typing only
    import pandas as pd

__all__ = ["close_series", "crossed_above", "crossed_below", "last_two"]

# The last two values of an indicator, oldest first: ``(previous, current)``.
Pair = tuple[float, float]


def close_series(candles: pd.DataFrame) -> pd.Series:
    """Return the ``close`` column of an OHLCV frame.

    Raises :class:`DataError` rather than letting a bare ``KeyError`` escape.
    The engine catches whatever a strategy throws and counts it toward the
    quarantine budget, so the exception message is the only diagnostic that
    survives -- ``KeyError: 'close'`` and "this frame has columns [...] and no
    'close'" are the difference between a five-minute fix and an outage nobody
    can explain.
    """
    if "close" not in candles.columns:
        raise DataError(
            f"OHLCV frame has no 'close' column; got {sorted(str(c) for c in candles.columns)}"
        )
    return candles["close"]


def last_two(series: pd.Series) -> Pair | None:
    """The final two values of ``series`` as ``(previous, current)``, or ``None``.

    ``None`` means "not answerable": fewer than two values, or either value
    ``NaN``.

    **This is the single NaN gate for every strategy.** The indicator layer
    expresses warmup as leading ``NaN`` -- never zero, never back-filled -- so
    "``None`` from this function" and "not enough data yet" are the same
    statement. A strategy that reads its indicators only through this function
    cannot act on a warmup value, which is a property of the code rather than a
    rule someone has to remember.

    Returning ``None`` (rather than raising) mirrors the indicator layer's
    "insufficient data is not an error" rule: the engine quarantines a pair
    after ``max_strategy_errors`` consecutive exceptions, so raising here would
    permanently disable a pair that only needed more candles.

    Values are coerced to built-in ``float``. ``Series.iloc`` yields
    ``numpy.float64``, which *is* a ``float`` subclass but reprs as
    ``np.float64(1.5)``; leaking that into ``Signal.metadata`` would put NumPy
    types into log lines and into the persistence layer for no benefit.
    """
    if len(series) < 2:
        return None
    previous = float(series.iloc[-2])
    current = float(series.iloc[-1])
    if isnan(previous) or isnan(current):
        return None
    return previous, current


def crossed_above(series: Pair, reference: Pair) -> bool:
    """True when ``series`` was at or below ``reference`` and is now strictly above.

    The asymmetry (``<=`` on the previous bar, ``>`` on the current) is what
    makes the crossing fire **exactly once** per transition: on the following
    bar the previous value is already strictly above, so the first clause is
    false. Using ``<`` on both sides would miss a transition that pauses at
    equality for a bar; using ``>=`` on the current would re-fire for as long as
    the two stay equal.

    A constant threshold is just a flat reference series -- pass
    ``(level, level)``.
    """
    return series[0] <= reference[0] and series[1] > reference[1]


def crossed_below(series: Pair, reference: Pair) -> bool:
    """True when ``series`` was at or above ``reference`` and is now strictly below.

    The exact mirror of :func:`crossed_above`; see its note on why the
    comparison is asymmetric.
    """
    return series[0] >= reference[0] and series[1] < reference[1]
