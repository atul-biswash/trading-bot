"""Channel and momentum indicators for the M5n candidates: Donchian, Keltner and n-bar momentum.

They follow the contract of ``indicators.py`` (pure functions over ``float64`` Series, the
caller's input never mutated, the input index carried unchanged, warm-up expressed as leading
``NaN`` and never zero or back-filled), and live in a module of their own because that module
documents a table of leading NaNs that a new function would have to join.

========================================  ================================
Function                                  Leading NaNs (clean input)
========================================  ================================
``donchian_high(high, n)``                ``n``
``keltner_upper(h, l, c, e, a, m)``       ``max(e - 1, a)``
``momentum(series, n)``                   ``n``
========================================  ================================

``donchian_high`` is the highest high of the *prior* ``n`` bars and does not include the current
bar, because a breakout is the current close against what the market had already done; with the
current bar in the window a close could never exceed it. ``keltner_upper`` composes the existing
``ema`` and ``atr`` and adds nothing of its own to their warm-up. None of the three reads a
volume.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from trading_bot.indicators.indicators import (
    _aligned_ohlc,
    _check_period,
    _numeric_float,
    atr,
    ema,
)

if TYPE_CHECKING:  # pragma: no cover - typing only
    import pandas as pd

__all__ = ["donchian_high", "keltner_upper", "momentum"]


def donchian_high(high: pd.Series, period: int) -> pd.Series:
    """The highest high of the prior ``period`` bars, excluding the current bar.

    :param high: numeric series of highs.
    :param period: lookback in bars; must be ``>= 1``.
    :returns: ``float64`` Series named ``donchian_high_<period>``, first ``period`` values NaN,
        sharing ``high``'s index. A window holding a NaN gives NaN.
    :raises ValueError: if ``period < 1``.
    :raises DataError: if ``high`` is not numeric.
    """
    _check_period(period)
    values = _numeric_float(high, label="high")
    result = values.shift(1).rolling(period, min_periods=period).max()
    return result.rename(f"donchian_high_{period}")


def keltner_upper(
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    ema_period: int = 20,
    atr_period: int = 20,
    multiplier: float = 2.0,
) -> pd.Series:
    """The EMA of the close plus ``multiplier`` times the Wilder ATR.

    :returns: ``float64`` Series named ``keltner_upper_<ema>_<atr>_<multiplier>``, first
        ``max(ema_period - 1, atr_period)`` values NaN, sharing the input index.
    :raises ValueError: if a period is below 1 or ``multiplier`` is not positive.
    :raises DataError: if an input is not numeric or the three indices differ.
    """
    _check_period(ema_period, label="ema_period")
    _check_period(atr_period, label="atr_period")
    if not multiplier > 0:
        raise ValueError(f"multiplier must be > 0, got {multiplier}")
    high_f, low_f, close_f = _aligned_ohlc(high, low, close)
    result = ema(close_f, ema_period) + multiplier * atr(high_f, low_f, close_f, atr_period)
    return result.rename(f"keltner_upper_{ema_period}_{atr_period}_{multiplier:g}")


def momentum(series: pd.Series, period: int) -> pd.Series:
    """The series minus itself ``period`` bars earlier.

    :returns: ``float64`` Series named ``momentum_<period>``, first ``period`` values NaN,
        sharing ``series``'s index.
    :raises ValueError: if ``period < 1``.
    :raises DataError: if ``series`` is not numeric.
    """
    _check_period(period)
    values = _numeric_float(series, label="series")
    return (values - values.shift(period)).rename(f"momentum_{period}")
