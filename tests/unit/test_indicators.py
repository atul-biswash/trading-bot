"""Tests for the hand-written technical indicators.

Hermetic: no network, no real time, no files. Every expected value is
**independently computed** — never with the code under test:

* Anchors (the first value of each indicator) are worked out by hand in the
  comments, from a deliberately hand-checkable price series of whole numbers.
* Full expected series come from a separate pure-Python reference written from
  the textbook definitions with explicit loops and :mod:`statistics` — a
  different code path from the vectorised pandas implementation, so a wrong
  ``alpha``, a wrong seed, a wrong ``ddof`` or an off-by-one in the warmup
  cannot cancel out on both sides. They are quoted to 6 decimals and compared
  with a matching absolute tolerance.
* Definition disagreements that would otherwise pass silently (Wilder vs EMA
  smoothing, population vs sample stdev, SMA-seeded vs ``adjust=True``) are
  asserted from both sides: the value must match the intended definition *and*
  differ from the plausible-but-wrong one.
"""

from __future__ import annotations

import dataclasses
from itertools import pairwise
from statistics import fmean, pstdev
from typing import Any

import numpy as np
import pandas as pd
import pytest

from trading_bot.core.exceptions import DataError
from trading_bot.data.market_data import INDEX_NAME, OHLCV_COLUMNS
from trading_bot.indicators import (
    BollingerBandsResult,
    MacdResult,
    atr,
    bollinger_bands,
    ema,
    macd,
    rsi,
    sma,
    true_range,
)

# ---------------------------------------------------------------------------
# Fixture data
# ---------------------------------------------------------------------------
# 40 whole-number closes with two clear up-legs and two pull-backs. Whole
# numbers keep every seed exactly representable, so the anchor tests below are
# real hand arithmetic rather than copied output.
# fmt: off — the grid layout is the point: it keeps the fixture and the golden
# values below readable and diffable. One number per line would not be.
_CLOSES: tuple[float, ...] = tuple(
    float(value)
    for value in (
        100,
        101,
        102,
        103,
        102,
        101,
        100,
        99,
        100,
        102,
        104,
        106,
        105,
        104,
        103,
        105,
        107,
        109,
        111,
        110,
        108,
        107,
        109,
        112,
        115,
        114,
        113,
        111,
        110,
        112,
        114,
        117,
        119,
        118,
        116,
        115,
        117,
        120,
        122,
        121,
    )
)
# fmt: on

# Highs and lows straddle the close by alternating whole-number offsets, so
# every true range is an integer and the ATR seed is a checkable fraction.
_HIGHS: tuple[float, ...] = tuple(
    close + (2.0 if i % 2 == 0 else 1.0) for i, close in enumerate(_CLOSES)
)
_LOWS: tuple[float, ...] = tuple(
    close - (1.0 if i % 3 == 0 else 2.0) for i, close in enumerate(_CLOSES)
)

#: Absolute tolerance matching the 6-decimal precision of the quoted literals.
_TOL = 1e-6


def _index(length: int) -> pd.DatetimeIndex:
    """A tz-aware UTC index shaped exactly like the market-data provider's."""
    return pd.date_range("2024-01-01", periods=length, freq="1min", tz="UTC", name=INDEX_NAME)


def _series(values: tuple[float, ...] | list[float], name: str = "close") -> pd.Series:
    return pd.Series(values, index=_index(len(values)), dtype="float64", name=name)


def closes() -> pd.Series:
    return _series(_CLOSES, "close")


def highs() -> pd.Series:
    return _series(_HIGHS, "high")


def lows() -> pd.Series:
    return _series(_LOWS, "low")


def _defined(series: pd.Series) -> list[float]:
    """The non-NaN tail of ``series`` as plain floats."""
    return [float(value) for value in series.to_numpy() if not np.isnan(value)]


def _leading_nans(series: pd.Series) -> int:
    values = series.to_numpy()
    return int(np.argmax(~np.isnan(values))) if np.isnan(values).any() else 0


def _assert_close(actual: pd.Series, expected: tuple[float, ...]) -> None:
    assert _defined(actual) == pytest.approx(list(expected), abs=_TOL)
    assert len(_defined(actual)) == len(expected)


# ---------------------------------------------------------------------------
# Expected values — from the independent pure-Python reference (defined tail
# only; the NaN warmup is asserted separately by count).
# ---------------------------------------------------------------------------
# fmt: off
_EXPECTED_SMA_5 = (
    101.6, 101.8, 101.6, 101.0, 100.4, 100.4,
    101.0, 102.2, 103.4, 104.2, 104.4, 104.6,
    104.8, 105.6, 107.0, 108.4, 109.0, 109.0,
    109.0, 109.2, 110.2, 111.4, 112.6, 113.0,
    112.6, 112.0, 112.0, 112.8, 114.4, 116.0,
    116.8, 117.0, 117.0, 117.2, 118.0, 119.0,
)

_EXPECTED_EMA_5 = (
    101.6, 101.4, 100.933333, 100.288889, 100.192593, 100.795062,
    101.863374, 103.24225, 103.828166, 103.885444, 103.590296, 104.060197,
    105.040132, 106.360088, 107.906725, 108.604483, 108.402989, 107.935326,
    108.290217, 109.526812, 111.351208, 112.234138, 112.489426, 111.99295,
    111.328634, 111.552422, 112.368282, 113.912188, 115.608125, 116.405417,
    116.270278, 115.846852, 116.231235, 117.48749, 118.99166, 119.661107,
)

_EXPECTED_RSI_14 = (
    58.823529, 63.453815, 67.401488, 70.798443, 73.744841, 69.94474,
    62.957211, 59.74345, 63.731101, 68.734071, 72.777956, 69.54886,
    66.377213, 60.440606, 57.663607, 61.475963, 64.881604, 69.269999,
    71.799962, 68.75212, 62.99277, 60.274002, 63.652835, 68.04347,
    70.593761, 67.685198,
)

_EXPECTED_MACD_LINE = (
    4.249955, 4.206679, 3.96529, 3.651207, 3.523065, 3.542065,
    3.755901, 4.040179, 4.137089, 4.006326, 3.778447, 3.716395,
    3.864743, 4.096472, 4.15157,
)

_EXPECTED_MACD_SIGNAL = (
    3.896826, 3.918726, 3.89067, 3.855815, 3.857601, 3.905375,
    3.954614,
)

_EXPECTED_MACD_HIST = (
    0.240264, 0.0876, -0.112222, -0.13942, 0.007143, 0.191097,
    0.196956,
)

_EXPECTED_BB_UPPER = (
    110.455738, 110.879381, 111.134983, 111.674594, 112.752483, 114.36528,
    115.410668, 115.965328, 115.870961, 115.595066, 115.674594, 116.174594,
    117.325955, 118.685353, 119.436504, 119.420337, 119.343568, 119.669824,
    120.649828, 122.011638, 122.902381,
)

_EXPECTED_BB_MIDDLE = (
    103.7, 104.1, 104.4, 104.75, 105.2, 105.85,
    106.5, 107.15, 107.75, 108.25, 108.75, 109.25,
    109.8, 110.5, 111.2, 111.85, 112.35, 112.85,
    113.4, 113.95, 114.5,
)

_EXPECTED_BB_LOWER = (
    96.944262, 97.320619, 97.665017, 97.825406, 97.647517, 97.33472,
    97.589332, 98.334672, 99.629039, 100.904934, 101.825406, 102.325406,
    102.274045, 102.314647, 102.963496, 104.279663, 105.356432, 106.030176,
    106.150172, 105.888362, 106.097619,
)

_EXPECTED_TRUE_RANGE = (
    3.0, 4.0, 2.0, 4.0, 3.0, 3.0, 3.0, 4.0, 3.0, 4.0,
    3.0, 3.0, 3.0, 4.0, 3.0, 4.0, 3.0, 4.0, 3.0, 4.0,
    2.0, 4.0, 4.0, 5.0, 3.0, 4.0, 3.0, 4.0, 3.0, 4.0,
    4.0, 4.0, 2.0, 4.0, 3.0, 4.0, 4.0, 4.0, 2.0,
)

_EXPECTED_ATR_14 = (
    3.285714, 3.265306, 3.317784, 3.295085, 3.345436, 3.320762,
    3.369279, 3.271474, 3.323511, 3.371832, 3.48813, 3.453263,
    3.492316, 3.45715, 3.495925, 3.460502, 3.499038, 3.534821,
    3.568048, 3.456044, 3.494898, 3.459549, 3.498152, 3.533998,
    3.567284, 3.455335,
)
# fmt: on


# ---------------------------------------------------------------------------
# Golden values
# ---------------------------------------------------------------------------
def test_sma_matches_reference() -> None:
    _assert_close(sma(closes(), 5), _EXPECTED_SMA_5)


def test_ema_matches_reference() -> None:
    _assert_close(ema(closes(), 5), _EXPECTED_EMA_5)


def test_rsi_matches_reference() -> None:
    _assert_close(rsi(closes(), 14), _EXPECTED_RSI_14)


def test_macd_matches_reference() -> None:
    result = macd(closes())
    _assert_close(result.line, _EXPECTED_MACD_LINE)
    _assert_close(result.signal, _EXPECTED_MACD_SIGNAL)
    _assert_close(result.histogram, _EXPECTED_MACD_HIST)


def test_bollinger_matches_reference() -> None:
    bands = bollinger_bands(closes(), period=20, num_std=2.0)
    _assert_close(bands.upper, _EXPECTED_BB_UPPER)
    _assert_close(bands.middle, _EXPECTED_BB_MIDDLE)
    _assert_close(bands.lower, _EXPECTED_BB_LOWER)


def test_true_range_matches_reference() -> None:
    _assert_close(true_range(highs(), lows(), closes()), _EXPECTED_TRUE_RANGE)


def test_atr_matches_reference() -> None:
    _assert_close(atr(highs(), lows(), closes(), 14), _EXPECTED_ATR_14)


# ---------------------------------------------------------------------------
# Hand-computed anchors
# ---------------------------------------------------------------------------
def test_sma_first_value_is_hand_computed() -> None:
    # (100 + 101 + 102 + 103 + 102) / 5 = 508 / 5
    assert sma(closes(), 5).iloc[4] == pytest.approx(508 / 5)


def test_ema_seed_is_the_simple_average_then_recurses() -> None:
    result = ema(closes(), 5)
    # Seed = SMA(5) of the first five closes = 508 / 5 = 101.6 ...
    assert result.iloc[4] == pytest.approx(508 / 5)
    # ... then y = alpha*x + (1-alpha)*y_prev with alpha = 2/(5+1) = 1/3:
    # (1/3)*101 + (2/3)*101.6 = 101.4
    assert result.iloc[5] == pytest.approx((1 / 3) * 101 + (2 / 3) * 101.6)


def test_rsi_first_value_is_hand_computed() -> None:
    # The first 14 changes are +1 +1 +1 -1 -1 -1 -1 +1 +2 +2 +2 -1 -1 -1:
    # gains sum to 10 and losses to 7, so with Wilder's seed (a plain average
    # over 14) RSI = 100 * (10/14) / (10/14 + 7/14) = 1000 / 17.
    assert rsi(closes(), 14).iloc[14] == pytest.approx(1000 / 17)


def test_atr_first_value_is_the_average_of_the_first_14_true_ranges() -> None:
    # True ranges 1..14 are 3,4,2,4,3,3,3,4,3,4,3,3,3,4 -> 46; seed = 46/14.
    assert sum(_EXPECTED_TRUE_RANGE[:14]) == 46
    assert atr(highs(), lows(), closes(), 14).iloc[14] == pytest.approx(46 / 14)


def test_true_range_uses_the_previous_close_across_a_gap() -> None:
    # A bar that gaps up: range 1.0 intraday, but 6.0 measured from the
    # previous close. Taking the intraday range would understate volatility.
    high = _series([10.0, 16.0])
    low = _series([9.0, 15.0])
    close = _series([10.0, 15.5])
    result = true_range(high, low, close)
    assert np.isnan(result.iloc[0])
    assert result.iloc[1] == pytest.approx(6.0)


def test_bollinger_middle_is_the_simple_average_of_the_window() -> None:
    assert bollinger_bands(closes(), period=20).middle.iloc[19] == pytest.approx(
        fmean(_CLOSES[:20])
    )


# ---------------------------------------------------------------------------
# Warmup / NaN semantics
# ---------------------------------------------------------------------------
def _all_outputs() -> list[tuple[str, pd.Series, int]]:
    """``(label, series, expected_leading_nans)`` for every indicator."""
    result = macd(closes())
    bands = bollinger_bands(closes(), period=20)
    return [
        ("sma_5", sma(closes(), 5), 4),
        ("ema_5", ema(closes(), 5), 4),
        ("ema_12", ema(closes(), 12), 11),
        ("rsi_14", rsi(closes(), 14), 14),
        ("macd_line", result.line, 25),
        ("macd_signal", result.signal, 33),
        ("macd_hist", result.histogram, 33),
        ("bb_upper", bands.upper, 19),
        ("bb_middle", bands.middle, 19),
        ("bb_lower", bands.lower, 19),
        ("true_range", true_range(highs(), lows(), closes()), 1),
        ("atr_14", atr(highs(), lows(), closes(), 14), 14),
    ]


@pytest.mark.parametrize(
    ("label", "series", "expected"),
    [pytest.param(*case, id=case[0]) for case in _all_outputs()],
)
def test_warmup_is_exactly_this_many_leading_nans(
    label: str, series: pd.Series, expected: int
) -> None:
    """Warmup length is part of the contract: a strategy sets its
    ``warmup_period`` from it, so a silent off-by-one would let it act on a
    half-formed indicator."""
    assert _leading_nans(series) == expected


@pytest.mark.parametrize(
    ("label", "series", "expected"),
    [pytest.param(*case, id=case[0]) for case in _all_outputs()],
)
def test_no_nan_survives_past_the_warmup(label: str, series: pd.Series, expected: int) -> None:
    assert not series.iloc[expected:].isna().any()


@pytest.mark.parametrize(
    ("label", "series", "expected"),
    [pytest.param(*case, id=case[0]) for case in _all_outputs()],
)
def test_warmup_is_nan_never_zero_or_backfilled(
    label: str, series: pd.Series, expected: int
) -> None:
    assert series.iloc[:expected].isna().all()


# ---------------------------------------------------------------------------
# Definition pinning: the classic silent-disagreement bugs
# ---------------------------------------------------------------------------
def _wilder_by_hand(values: list[float], period: int) -> list[float]:
    """Wilder's own recursion ``y = (y_prev*(n-1) + x) / n``, written out."""
    seed = fmean(values[:period])
    out = [seed]
    for value in values[period:]:
        out.append((out[-1] * (period - 1) + value) / period)
    return out


def test_rsi_uses_wilder_smoothing_not_a_standard_ema() -> None:
    """``alpha = 1/n`` (Wilder), not ``2/(n+1)`` (EMA) — the two disagree by
    whole RSI points, which is the difference between a signal and no signal."""
    period = 14
    changes = [later - earlier for earlier, later in pairwise(_CLOSES)]
    gains = [max(change, 0.0) for change in changes]
    losses = [max(-change, 0.0) for change in changes]

    wilder_gain = _wilder_by_hand(gains, period)
    wilder_loss = _wilder_by_hand(losses, period)
    expected = [
        100.0 * gain / (gain + loss) for gain, loss in zip(wilder_gain, wilder_loss, strict=True)
    ]
    assert _defined(rsi(closes(), period)) == pytest.approx(expected, abs=_TOL)

    # The EMA-smoothed variant is a *different* number, so this test would fail
    # if the implementation silently switched.
    ema_gain = _defined(ema(pd.Series(gains), period))
    ema_loss = _defined(ema(pd.Series(losses), period))
    ema_rsi = [100.0 * gain / (gain + loss) for gain, loss in zip(ema_gain, ema_loss, strict=True)]
    assert ema_rsi[0] == pytest.approx(expected[0])  # identical seed ...
    assert abs(ema_rsi[-1] - expected[-1]) > 1.0  # ... then visibly diverges


def test_atr_uses_wilder_smoothing_not_a_standard_ema() -> None:
    period = 14
    ranges = list(_EXPECTED_TRUE_RANGE)
    expected = _wilder_by_hand(ranges, period)
    assert _defined(atr(highs(), lows(), closes(), period)) == pytest.approx(expected, abs=_TOL)

    ema_atr = _defined(ema(pd.Series([np.nan, *ranges]), period))
    assert ema_atr[0] == pytest.approx(expected[0])
    assert ema_atr[-1] != pytest.approx(expected[-1], abs=1e-3)


def test_ema_is_sma_seeded_and_not_pandas_adjust_true() -> None:
    """pandas' default ``adjust=True`` defines the EMA from the first bar and
    gives different early values; the SMA seed is what charting platforms use."""
    series = closes()
    result = ema(series, 5)
    adjusted = series.ewm(span=5, adjust=True).mean()
    unseeded = series.ewm(span=5, adjust=False).mean()

    assert np.isnan(result.iloc[0])
    assert not np.isnan(adjusted.iloc[0])  # would expose a bar-0 value
    assert not np.isnan(unseeded.iloc[0])
    assert result.iloc[4] != pytest.approx(adjusted.iloc[4], abs=1e-3)
    assert result.iloc[4] != pytest.approx(unseeded.iloc[4], abs=1e-3)


def test_bollinger_uses_population_stdev_not_the_pandas_sample_default() -> None:
    period = 20
    bands = bollinger_bands(closes(), period=period, num_std=2.0)
    window = list(_CLOSES[:period])
    expected_upper = fmean(window) + 2.0 * pstdev(window)
    assert bands.upper.iloc[period - 1] == pytest.approx(expected_upper, abs=_TOL)

    sample_upper = closes().rolling(period).mean() + 2.0 * closes().rolling(period).std(ddof=1)
    assert bands.upper.iloc[period - 1] != pytest.approx(sample_upper.iloc[period - 1], abs=1e-3)


# ---------------------------------------------------------------------------
# Structural invariants
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    ("label", "series", "expected"),
    [pytest.param(*case, id=case[0]) for case in _all_outputs()],
)
def test_index_and_dtype_are_preserved(label: str, series: pd.Series, expected: int) -> None:
    assert series.dtype == np.float64
    assert series.index.equals(_index(len(_CLOSES)))
    assert series.index.name == INDEX_NAME
    assert series.index.tz is not None


def test_outputs_are_named_for_what_they_are() -> None:
    result = macd(closes())
    bands = bollinger_bands(closes(), period=20)
    assert sma(closes(), 5).name == "sma_5"
    assert ema(closes(), 12).name == "ema_12"
    assert rsi(closes(), 14).name == "rsi_14"
    assert (result.line.name, result.signal.name, result.histogram.name) == (
        "macd",
        "macd_signal",
        "macd_hist",
    )
    assert (bands.upper.name, bands.middle.name, bands.lower.name) == (
        "bb_upper",
        "bb_middle",
        "bb_lower",
    )
    assert true_range(highs(), lows(), closes()).name == "true_range"
    assert atr(highs(), lows(), closes(), 14).name == "atr_14"


def test_input_series_are_never_mutated() -> None:
    close, high, low = closes(), highs(), lows()
    before = (close.copy(), high.copy(), low.copy())
    sma(close, 5)
    ema(close, 5)
    rsi(close, 14)
    macd(close)
    bollinger_bands(close, period=20)
    atr(high, low, close, 14)
    for original, current in zip(before, (close, high, low), strict=True):
        pd.testing.assert_series_equal(original, current)


def test_bollinger_middle_equals_sma_and_bands_are_ordered() -> None:
    period = 20
    bands = bollinger_bands(closes(), period=period)
    pd.testing.assert_series_equal(bands.middle, sma(closes(), period), check_names=False)
    valid = bands.middle.notna()
    assert (bands.upper[valid] >= bands.middle[valid]).all()
    assert (bands.middle[valid] >= bands.lower[valid]).all()


def test_macd_histogram_is_line_minus_signal() -> None:
    result = macd(closes())
    pd.testing.assert_series_equal(
        result.histogram, (result.line - result.signal).rename("macd_hist")
    )


def test_atr_and_true_range_are_non_negative() -> None:
    ranges = true_range(highs(), lows(), closes())
    average = atr(highs(), lows(), closes(), 14)
    assert (ranges.dropna() >= 0).all()
    assert (average.dropna() >= 0).all()


def test_rsi_is_bounded_to_zero_hundred() -> None:
    values = rsi(closes(), 14).dropna()
    assert values.between(0.0, 100.0).all()


def test_result_objects_are_frozen_and_expose_a_frame() -> None:
    result = macd(closes())
    bands = bollinger_bands(closes(), period=20)
    assert isinstance(result, MacdResult)
    assert isinstance(bands, BollingerBandsResult)
    with pytest.raises(dataclasses.FrozenInstanceError):
        result.line = closes()  # type: ignore[misc]
    with pytest.raises(dataclasses.FrozenInstanceError):
        bands.upper = closes()  # type: ignore[misc]
    assert list(result.to_frame().columns) == ["macd", "macd_signal", "macd_hist"]
    assert list(bands.to_frame().columns) == ["bb_upper", "bb_middle", "bb_lower"]


def test_results_cannot_be_unpacked_positionally() -> None:
    """A NamedTuple would allow ``lower, middle, upper = ...`` and silently
    invert the bands; the dataclass makes that a TypeError."""
    with pytest.raises(TypeError):
        _lower, _middle, _upper = bollinger_bands(closes(), period=20)  # type: ignore[misc]


def test_runs_on_a_provider_shaped_frame() -> None:
    """The provider's frame is the real input: float64 OHLCV on a tz-aware UTC
    ``DatetimeIndex``. Indicators must consume it without any adaptation."""
    frame = pd.DataFrame(
        {
            "open": _CLOSES,
            "high": _HIGHS,
            "low": _LOWS,
            "close": _CLOSES,
            "volume": [1.0] * len(_CLOSES),
        },
        index=_index(len(_CLOSES)),
    )
    assert list(frame.columns) == list(OHLCV_COLUMNS)
    assert sma(frame["close"], 5).iloc[-1] == pytest.approx(_EXPECTED_SMA_5[-1])
    assert atr(frame["high"], frame["low"], frame["close"], 14).iloc[-1] == pytest.approx(
        _EXPECTED_ATR_14[-1]
    )


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------
def test_empty_series_returns_empty_output_not_an_error() -> None:
    empty = pd.Series([], dtype="float64", index=_index(0))
    for result in (sma(empty, 5), ema(empty, 5), rsi(empty, 14)):
        assert len(result) == 0
        assert result.dtype == np.float64
    assert len(macd(empty).line) == 0
    assert len(bollinger_bands(empty, period=20).middle) == 0
    assert len(atr(empty, empty, empty, 14)) == 0


@pytest.mark.parametrize("length", [0, 1, 3])
def test_series_shorter_than_period_is_all_nan_not_an_error(length: int) -> None:
    """A short buffer is a transient condition, not a failure: raising here
    would count against the engine's consecutive-failure quarantine and
    permanently disable a pair that only needed more candles."""
    short = _series(list(_CLOSES[:length]))
    assert sma(short, 5).isna().all()
    assert ema(short, 5).isna().all()
    assert rsi(short, 14).isna().all()
    assert macd(short).line.isna().all()
    assert bollinger_bands(short, period=20).middle.isna().all()
    assert atr(short, short, short, 14).isna().all()


def test_period_one_degenerates_sensibly() -> None:
    series = closes()
    pd.testing.assert_series_equal(sma(series, 1), series.rename("sma_1"))
    pd.testing.assert_series_equal(ema(series, 1), series.rename("ema_1"))
    # ATR(1) is just the true range.
    pd.testing.assert_series_equal(
        atr(highs(), lows(), series, 1),
        true_range(highs(), lows(), series).rename("atr_1"),
    )
    # A one-bar window has zero deviation, so the bands collapse onto the SMA.
    bands = bollinger_bands(series, period=1)
    pd.testing.assert_series_equal(bands.upper, series.rename("bb_upper"))
    pd.testing.assert_series_equal(bands.lower, series.rename("bb_lower"))
    # RSI(1) sees a single change per bar: fully up, fully down, or flat.
    assert set(rsi(series, 1).dropna().unique()) <= {0.0, 50.0, 100.0}


def test_flat_series_gives_rsi_fifty_not_a_division_blowup() -> None:
    """Both averages are zero. The naive ``100 - 100/(1+RS)`` would produce
    100 — "maximally overbought" for a market that never moved — which is how a
    frozen feed manufactures a signal."""
    flat = _series([100.0] * 20)
    result = rsi(flat, 14)
    assert not result.dropna().empty
    assert (result.dropna() == 50.0).all()


def test_monotonic_series_saturate_rsi_without_infinities() -> None:
    rising = _series([100.0 + i for i in range(20)])
    falling = _series([100.0 - i for i in range(20)])
    assert (rsi(rising, 14).dropna() == 100.0).all()
    assert (rsi(falling, 14).dropna() == 0.0).all()
    assert np.isfinite(rsi(rising, 14).dropna()).all()


def test_flat_series_gives_zero_width_bollinger_bands() -> None:
    flat = _series([100.0] * 25)
    bands = bollinger_bands(flat, period=20)
    assert (bands.upper.dropna() == 100.0).all()
    assert (bands.lower.dropna() == 100.0).all()


@pytest.mark.parametrize("position", [5, 20])
def test_a_nan_mid_series_stays_nan_and_then_recovers(position: int) -> None:
    """pandas' ``ewm`` carries the previous value forward at a NaN input, which
    would present a stale number as a fresh reading. It must read NaN — and the
    bars after it must recover rather than being poisoned forever."""
    values = list(_CLOSES)
    values[position] = float("nan")
    holed = _series(values)

    for result in (sma(holed, 5), ema(holed, 5), rsi(holed, 14)):
        assert np.isnan(result.iloc[position])
        assert not np.isnan(result.iloc[-1])

    # A rolling window is unusable while it overlaps the hole, then recovers.
    smoothed = sma(holed, 5)
    assert smoothed.iloc[position : position + 5].isna().all()
    assert not np.isnan(smoothed.iloc[position + 5])


def test_a_nan_in_a_price_is_not_silently_read_as_no_change() -> None:
    """``delta.where(delta > 0, 0.0)`` would turn an unknown change into a zero
    gain; ``clip`` keeps it NaN. Guards the RSI gain/loss split."""
    values = list(_CLOSES)
    values[6] = float("nan")
    result = rsi(_series(values), 14)
    assert np.isnan(result.iloc[6])


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------
def _call_with_period(name: str, period: int) -> Any:
    series = closes()
    calls = {
        "sma": lambda: sma(series, period),
        "ema": lambda: ema(series, period),
        "rsi": lambda: rsi(series, period),
        "bollinger_bands": lambda: bollinger_bands(series, period=period),
        "atr": lambda: atr(highs(), lows(), series, period),
        "macd_fast": lambda: macd(series, fast_period=period),
        "macd_slow": lambda: macd(series, slow_period=period),
        "macd_signal": lambda: macd(series, signal_period=period),
    }
    return calls[name]()


@pytest.mark.parametrize(
    "name",
    [
        "sma",
        "ema",
        "rsi",
        "bollinger_bands",
        "atr",
        "macd_fast",
        "macd_slow",
        "macd_signal",
    ],
)
@pytest.mark.parametrize("period", [0, -1])
def test_non_positive_period_raises_value_error(name: str, period: int) -> None:
    with pytest.raises(ValueError, match="must be >= 1"):
        _call_with_period(name, period)


def test_macd_rejects_a_fast_period_at_or_above_the_slow_one() -> None:
    with pytest.raises(ValueError, match="fast_period must be < slow_period"):
        macd(closes(), fast_period=26, slow_period=26)
    with pytest.raises(ValueError, match="fast_period must be < slow_period"):
        macd(closes(), fast_period=30, slow_period=26)


@pytest.mark.parametrize("num_std", [0.0, -1.0])
def test_bollinger_rejects_a_non_positive_width(num_std: float) -> None:
    with pytest.raises(ValueError, match="num_std must be > 0"):
        bollinger_bands(closes(), period=20, num_std=num_std)


def test_non_numeric_series_raises_data_error() -> None:
    text = pd.Series(["100", "101", "102"], index=_index(3))
    with pytest.raises(DataError, match="must be numeric"):
        sma(text, 2)
    with pytest.raises(DataError, match="must be numeric"):
        rsi(text, 2)
    with pytest.raises(DataError, match="must be numeric"):
        atr(text, text, text, 2)


def test_misaligned_ohlc_raises_data_error() -> None:
    """pandas would take the union of the indices and fill the gaps with NaN,
    quietly computing a range from bars that never coexisted."""
    high = _series([10.0, 11.0, 12.0])
    low = _series([9.0, 10.0, 11.0])
    close = pd.Series([9.5, 10.5], index=_index(2))
    with pytest.raises(DataError, match="must share one index"):
        true_range(high, low, close)
    with pytest.raises(DataError, match="must share one index"):
        atr(high, low, close, 2)

    shifted = pd.Series([9.5, 10.5, 11.5], index=_index(4)[1:])
    with pytest.raises(DataError, match="must share one index"):
        true_range(high, low, shifted)


def test_integer_input_is_promoted_to_float() -> None:
    integers = pd.Series([1, 2, 3, 4, 5], index=_index(5))
    result = sma(integers, 2)
    assert result.dtype == np.float64
    assert result.iloc[1] == pytest.approx(1.5)
