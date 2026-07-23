"""Technical-indicator functions built directly on pandas / NumPy.

Indicators (SMA, EMA, RSI, MACD, Bollinger Bands, ATR) are implemented here as
small, pure, unit-tested functions rather than pulled from a third-party
library. This keeps a bot that can trade real money free of heavyweight,
fast-moving dependencies (e.g. numba/LLVM) and makes every calculation
auditable.

Contract
--------
Every function is **pure**: no I/O, no state, no configuration, and the caller's
input is never mutated. Input is one or more numeric :class:`pandas.Series`;
output is a ``float64`` Series -- or a frozen result object holding several --
carrying the *input index unchanged*. The same functions therefore run
untouched in live, paper and backtest modes.

Warmup is expressed as leading ``NaN``, never zero and never back-filled, so a
strategy can neither read nor act on a half-formed indicator. The exact number
of leading NaNs is part of the contract and is asserted in the tests:

======================================  ==============================
Function                                Leading NaNs (clean input)
======================================  ==============================
``sma(period=n)``                       ``n - 1``
``ema(period=n)``                       ``n - 1``
``rsi(period=n)``                       ``n``
``macd(...)`` -- ``line``               ``slow_period - 1``
``macd(...)`` -- ``signal``/``hist``    ``slow_period + signal_period - 2``
``bollinger_bands(period=n)``           ``n - 1``
``true_range()``                        ``1``
``atr(period=n)``                       ``n``
======================================  ==============================

Definitions that implementations disagree on -- pinned here deliberately,
because a silent disagreement is a money bug:

* **RSI and ATR use Wilder's smoothing** (``alpha = 1 / period``), the original
  definition used by TA-Lib, TradingView and most charting platforms -- *not* a
  standard EMA (``alpha = 2 / (period + 1)``). The two produce visibly
  different numbers.
* **EMA is SMA-seeded with ``adjust=False``**: the first ``period - 1`` values
  are NaN and the value at ``period - 1`` is the simple average of the first
  ``period`` observations, after which the usual recursion runs. pandas'
  default (``adjust=True``) instead defines the EMA from the very first bar and
  yields materially different early values.
* **Bollinger bands use the population standard deviation** (``ddof = 0``).
  pandas defaults to the *sample* deviation (``ddof = 1``), which widens the
  bands and does not match any charting platform.
* **True range is undefined on the first bar** (no previous close), so it is
  ``NaN`` rather than ``high - low``. This matches TA-Lib and keeps ATR's
  warmup consistent with RSI's; Wilder's original book uses ``high - low``
  there because he had no earlier close available.
* **A perfectly flat window gives RSI 50.0**, not 100 and not NaN -- see
  :func:`rsi`.

Errors
------
* :class:`ValueError` for invalid *parameters* (``period < 1``,
  ``fast_period >= slow_period``, ``num_std <= 0``). These are programming or
  configuration mistakes and should crash loudly at startup.
* :class:`~trading_bot.core.exceptions.DataError` for *malformed* input:
  non-numeric dtype, or OHLC series that do not share one index.
* **Insufficient** data is *not* an error: a series shorter than ``period``
  returns all-NaN, exactly like the warmup region. Raising there would turn a
  transient, self-healing condition ("not enough candles yet") into a strategy
  exception, which the live engine counts toward its consecutive-failure
  quarantine -- permanently disabling a pair that merely needed to wait.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from pandas.api.types import is_numeric_dtype

from trading_bot.core.exceptions import DataError

__all__ = [
    "BollingerBandsResult",
    "MacdResult",
    "atr",
    "bollinger_bands",
    "ema",
    "macd",
    "rsi",
    "sma",
    "true_range",
]

#: Output dtype of every indicator. Fixed so a strategy never has to branch on
#: dtype, and so integer input (e.g. a hand-written test fixture) cannot make an
#: indicator return integers and silently truncate.
_FLOAT64 = "float64"


# ---------------------------------------------------------------------------
# Multi-output result objects
# ---------------------------------------------------------------------------
# Frozen dataclasses rather than a NamedTuple or a DataFrame:
#
# * A NamedTuple supports positional unpacking, so ``lower, middle, upper =
#   bollinger_bands(...)`` would silently invert the band logic. A dataclass
#   cannot be unpacked, forcing ``bands.upper`` / ``bands.lower`` -- the kind of
#   mistake that must be impossible in software that sends orders.
# * A DataFrame is stringly-typed (``result["macd_signal"]``): typos surface at
#   runtime, mypy cannot help, and the column names leak into every caller.
# * ``eq=False`` because the generated ``__eq__`` would compare Series with
#   ``==``, producing an elementwise Series and then "truth value is ambiguous".
#   Identity comparison is predictable; use ``pandas.testing`` to compare values.


@dataclass(frozen=True, slots=True, eq=False)
class MacdResult:
    """The three MACD outputs, sharing the index of the input series.

    :ivar line: ``EMA(fast) - EMA(slow)``.
    :ivar signal: EMA of :attr:`line` over ``signal_period``.
    :ivar histogram: ``line - signal``.
    """

    line: pd.Series
    signal: pd.Series
    histogram: pd.Series

    def to_frame(self) -> pd.DataFrame:
        """Return the three series as one DataFrame (inspection, plotting)."""
        return pd.concat([self.line, self.signal, self.histogram], axis=1)


@dataclass(frozen=True, slots=True, eq=False)
class BollingerBandsResult:
    """The three Bollinger bands, sharing the index of the input series.

    :ivar upper: ``middle + num_std * stdev``.
    :ivar middle: the ``period``-bar simple moving average.
    :ivar lower: ``middle - num_std * stdev``.
    """

    upper: pd.Series
    middle: pd.Series
    lower: pd.Series

    def to_frame(self) -> pd.DataFrame:
        """Return the three series as one DataFrame (inspection, plotting)."""
        return pd.concat([self.upper, self.middle, self.lower], axis=1)


# ---------------------------------------------------------------------------
# Validation helpers
# ---------------------------------------------------------------------------
def _check_period(period: int, *, label: str = "period") -> None:
    """Reject a non-positive lookback.

    A ``ValueError`` (not a ``DataError``) because the period comes from code or
    config, never from the market: it is a programming mistake, and the project
    already signals those with ``ValueError`` (see ``BufferedMarketDataProvider``
    and ``TradingEngine``).
    """
    if period < 1:
        raise ValueError(f"{label} must be >= 1, got {period}")


def _numeric_float(series: pd.Series, *, label: str) -> pd.Series:
    """Return ``series`` as ``float64``, rejecting non-numeric input.

    ``copy=False`` makes this a no-op for the float64 frames the market-data
    provider produces; nothing downstream mutates the result, so no aliasing
    can leak back to the caller.
    """
    if not bool(is_numeric_dtype(series)):
        raise DataError(f"{label} must be numeric, got dtype {series.dtype}")
    return series.astype(_FLOAT64, copy=False)


def _aligned_ohlc(
    high: pd.Series, low: pd.Series, close: pd.Series
) -> tuple[pd.Series, pd.Series, pd.Series]:
    """Validate and normalise the three OHLC series used by range indicators.

    Misaligned indices are rejected rather than aligned: pandas would silently
    take the *union* and fill the gaps with NaN, quietly producing a true range
    computed from bars that never coexisted.
    """
    if not high.index.equals(low.index) or not high.index.equals(close.index):
        raise DataError(
            f"high/low/close must share one index; got lengths {len(high)}/{len(low)}/{len(close)}"
        )
    return (
        _numeric_float(high, label="high"),
        _numeric_float(low, label="low"),
        _numeric_float(close, label="close"),
    )


def _nan_like(series: pd.Series) -> pd.Series:
    """An all-NaN ``float64`` Series carrying ``series``'s index."""
    return pd.Series(np.nan, index=series.index, dtype=_FLOAT64)


# ---------------------------------------------------------------------------
# Shared smoothing core
# ---------------------------------------------------------------------------
def _seeded_recursive_mean(values: pd.Series, period: int, alpha: float) -> pd.Series:
    """SMA-seeded recursive mean -- the engine behind EMA, RSI and ATR.

    The recursion ``y[i] = alpha * x[i] + (1 - alpha) * y[i-1]`` needs a first
    value. Seeding it with the simple average of the first ``period``
    observations (rather than with ``x[0]``, or with pandas' ``adjust=True``
    weighting) is what TA-Lib and the charting platforms do, and it is the only
    seed that makes "leading NaN means not enough data" true.

    ``values`` may itself start with NaN -- RSI feeds it a ``diff()`` and ATR a
    true range, both undefined on the first bar. The seed is therefore placed at
    the end of the first *complete, NaN-free* window, which ``rolling`` locates
    and computes in one pass.

    A NaN *after* the seed is re-masked on the way out: pandas' ``ewm`` carries
    the previous value forward at NaN inputs, which would present a stale number
    as a fresh reading. Downstream bars recover once real data resumes rather
    than being poisoned forever, so one bad tick cannot permanently disable a
    pair.
    """
    seeds = values.rolling(period, min_periods=period).mean()
    seed_positions = np.flatnonzero(seeds.notna().to_numpy())
    if seed_positions.size == 0:
        # Fewer than `period` consecutive valid observations: nothing to seed
        # from. Not an error -- just not enough data yet.
        return _nan_like(values)

    seed_pos = int(seed_positions[0])
    work = values.to_numpy(dtype=np.float64, copy=True)
    work[:seed_pos] = np.nan
    work[seed_pos] = seeds.to_numpy()[seed_pos]

    smoothed = (
        pd.Series(work, index=values.index).ewm(alpha=alpha, adjust=False, ignore_na=False).mean()
    )
    return smoothed.where(values.notna())


def _wilder_mean(values: pd.Series, period: int) -> pd.Series:
    """Wilder's smoothing: :func:`_seeded_recursive_mean` with ``alpha = 1/n``.

    Wilder's own recursion is ``y[i] = (y[i-1] * (n - 1) + x[i]) / n``, which is
    algebraically identical to an EWM with ``alpha = 1/n``; using the same core
    keeps one seeding rule -- and one set of tests -- for every indicator.
    """
    return _seeded_recursive_mean(values, period, alpha=1.0 / period)


# ---------------------------------------------------------------------------
# Trend
# ---------------------------------------------------------------------------
def sma(series: pd.Series, period: int) -> pd.Series:
    """Simple moving average over ``period`` bars.

    :param series: numeric series, typically a frame's ``close`` column.
    :param period: lookback in bars; must be ``>= 1``.
    :returns: ``float64`` Series named ``sma_<period>``, first ``period - 1``
        values NaN, sharing ``series``'s index.
    :raises ValueError: if ``period < 1``.
    :raises DataError: if ``series`` is not numeric.

    >>> sma(pd.Series([1.0, 2.0, 3.0, 4.0]), 2).tolist()
    [nan, 1.5, 2.5, 3.5]
    """
    _check_period(period)
    values = _numeric_float(series, label="series")
    result = values.rolling(period, min_periods=period).mean()
    return result.rename(f"sma_{period}")


def ema(series: pd.Series, period: int) -> pd.Series:
    """Exponential moving average, SMA-seeded, ``alpha = 2 / (period + 1)``.

    :param series: numeric series, typically a frame's ``close`` column.
    :param period: lookback in bars; must be ``>= 1``.
    :returns: ``float64`` Series named ``ema_<period>``, first ``period - 1``
        values NaN, sharing ``series``'s index.
    :raises ValueError: if ``period < 1``.
    :raises DataError: if ``series`` is not numeric.
    """
    _check_period(period)
    values = _numeric_float(series, label="series")
    result = _seeded_recursive_mean(values, period, alpha=2.0 / (period + 1.0))
    return result.rename(f"ema_{period}")


def macd(
    series: pd.Series,
    *,
    fast_period: int = 12,
    slow_period: int = 26,
    signal_period: int = 9,
) -> MacdResult:
    """Moving Average Convergence/Divergence.

    Keyword-only periods: three same-typed lookbacks in a row are exactly the
    kind of argument list that gets transposed by accident.

    The signal line is the EMA of the MACD line, seeded once the line has
    ``signal_period`` valid values -- so it starts at
    ``slow_period + signal_period - 2``, not at ``signal_period - 1``.

    :param series: numeric series, typically a frame's ``close`` column.
    :param fast_period: short EMA lookback; must be ``>= 1`` and ``< slow_period``.
    :param slow_period: long EMA lookback; must be ``>= 1``.
    :param signal_period: EMA lookback applied to the MACD line; must be ``>= 1``.
    :returns: :class:`MacdResult` of three ``float64`` Series named ``macd``,
        ``macd_signal`` and ``macd_hist``.
    :raises ValueError: if any period is ``< 1``, or ``fast_period >= slow_period``.
    :raises DataError: if ``series`` is not numeric.
    """
    _check_period(fast_period, label="fast_period")
    _check_period(slow_period, label="slow_period")
    _check_period(signal_period, label="signal_period")
    if fast_period >= slow_period:
        raise ValueError(f"fast_period must be < slow_period, got {fast_period} >= {slow_period}")

    values = _numeric_float(series, label="series")
    line = (ema(values, fast_period) - ema(values, slow_period)).rename("macd")
    signal = _seeded_recursive_mean(line, signal_period, alpha=2.0 / (signal_period + 1.0)).rename(
        "macd_signal"
    )
    histogram = (line - signal).rename("macd_hist")
    return MacdResult(line=line, signal=signal, histogram=histogram)


# ---------------------------------------------------------------------------
# Momentum
# ---------------------------------------------------------------------------
def rsi(series: pd.Series, period: int = 14) -> pd.Series:
    """Relative Strength Index using **Wilder's** smoothing (``alpha = 1/n``).

    Computed as ``100 * avg_gain / (avg_gain + avg_loss)``, which is
    algebraically identical to Wilder's ``100 - 100 / (1 + RS)`` but never
    divides by zero: a window with no losses yields exactly ``100.0`` instead of
    ``inf``.

    The remaining singularity is a **perfectly flat window**, where both
    averages are ``0`` and the ratio is genuinely undefined. That returns
    ``50.0``. The naive formula would produce ``100`` there -- "maximally
    overbought" for a market that has not moved at all -- which is precisely how
    a stale or frozen feed manufactures a sell signal out of nothing. ``50.0``
    is the neutral midpoint and can never cross an overbought/oversold
    threshold. (NaN is the defensible alternative; it was rejected so that RSI
    stays defined wherever it has enough data, leaving NaN to mean exactly one
    thing: "not enough data".)

    :param series: numeric series, typically a frame's ``close`` column.
    :param period: lookback in bars; must be ``>= 1``. Needs ``period + 1``
        prices to produce its first value.
    :returns: ``float64`` Series named ``rsi_<period>`` bounded to ``[0, 100]``,
        first ``period`` values NaN, sharing ``series``'s index.
    :raises ValueError: if ``period < 1``.
    :raises DataError: if ``series`` is not numeric.
    """
    _check_period(period)
    values = _numeric_float(series, label="series")

    delta = values.diff()
    # `clip` preserves NaN; `where(delta > 0, 0.0)` would silently turn an
    # unknown price change into "no change", inventing data.
    gains = delta.clip(lower=0.0)
    losses = (-delta).clip(lower=0.0)

    avg_gain = _wilder_mean(gains, period)
    avg_loss = _wilder_mean(losses, period)
    total = avg_gain + avg_loss

    result = 100.0 * avg_gain / total
    # `mask` (not `where`) so a NaN `total` stays NaN: `NaN == 0.0` is False,
    # whereas the inverted `where(total != 0.0, 50.0)` reads far less obviously.
    return result.mask(total == 0.0, 50.0).rename(f"rsi_{period}")


# ---------------------------------------------------------------------------
# Volatility
# ---------------------------------------------------------------------------
def bollinger_bands(
    series: pd.Series, period: int = 20, num_std: float = 2.0
) -> BollingerBandsResult:
    """Bollinger Bands: an SMA with a population-stdev envelope.

    ``ddof=0`` is passed explicitly. pandas defaults to the *sample* standard
    deviation (``ddof=1``), which is wider by a factor of ``sqrt(n/(n-1))`` and
    matches no charting platform -- a difference small enough to look like
    rounding and large enough to move a breakout signal.

    :param series: numeric series, typically a frame's ``close`` column.
    :param period: lookback in bars; must be ``>= 1``.
    :param num_std: band width in standard deviations; must be ``> 0``.
    :returns: :class:`BollingerBandsResult` of three ``float64`` Series named
        ``bb_upper``, ``bb_middle`` and ``bb_lower``, first ``period - 1``
        values NaN.
    :raises ValueError: if ``period < 1`` or ``num_std <= 0``.
    :raises DataError: if ``series`` is not numeric.
    """
    _check_period(period)
    if num_std <= 0:
        raise ValueError(f"num_std must be > 0, got {num_std}")

    values = _numeric_float(series, label="series")
    window = values.rolling(period, min_periods=period)
    middle = window.mean()
    deviation = window.std(ddof=0) * num_std
    return BollingerBandsResult(
        upper=(middle + deviation).rename("bb_upper"),
        middle=middle.rename("bb_middle"),
        lower=(middle - deviation).rename("bb_lower"),
    )


def true_range(high: pd.Series, low: pd.Series, close: pd.Series) -> pd.Series:
    """Wilder's true range: ``max(h - l, |h - prev_close|, |l - prev_close|)``.

    The first bar has no previous close, so its true range is **NaN** rather
    than ``high - low``: with a gap, the intraday range understates the true
    range, and seeding ATR with a knowingly-too-small value biases every reading
    that follows. NaN keeps "unknown" and "known" distinguishable.

    :param high: numeric high series.
    :param low: numeric low series.
    :param close: numeric close series; must share ``high``'s index.
    :returns: ``float64`` Series named ``true_range``, first value NaN.
    :raises DataError: if the three series are misaligned or non-numeric.
    """
    high_f, low_f, close_f = _aligned_ohlc(high, low, close)
    previous_close = close_f.shift(1)
    components = pd.concat(
        [
            high_f - low_f,
            (high_f - previous_close).abs(),
            (low_f - previous_close).abs(),
        ],
        axis=1,
    )
    # skipna=False: with the default, the first bar's two NaN components are
    # dropped and `high - low` silently becomes the answer.
    return components.max(axis=1, skipna=False).rename("true_range")


def atr(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14) -> pd.Series:
    """Average True Range: **Wilder's** smoothing of :func:`true_range`.

    Wilder's ``alpha = 1 / period``, not an EMA's ``2 / (period + 1)``. Since
    the first true range is NaN, the first ATR lands at position ``period``,
    matching :func:`rsi` -- both need ``period + 1`` bars.

    :param high: numeric high series.
    :param low: numeric low series.
    :param close: numeric close series; must share ``high``'s index.
    :param period: lookback in bars; must be ``>= 1``.
    :returns: non-negative ``float64`` Series named ``atr_<period>``, first
        ``period`` values NaN.
    :raises ValueError: if ``period < 1``.
    :raises DataError: if the three series are misaligned or non-numeric.
    """
    _check_period(period)
    ranges = true_range(high, low, close)
    return _wilder_mean(ranges, period).rename(f"atr_{period}")
