"""Donchian, Keltner and momentum: hand-worked values, the NaN contract and purity.

Every expected figure is worked by hand in the test from the literals that build the input,
never by the code under test.
"""

from __future__ import annotations

import inspect
import math

import pandas as pd
import pytest

from trading_bot.core.exceptions import DataError
from trading_bot.indicators import atr, breakout, donchian_high, ema, keltner_upper, momentum


def series(values: list[float], name: str = "x") -> pd.Series:
    return pd.Series(
        values, index=pd.date_range("2023-01-01", periods=len(values), freq="D"), name=name
    )


def nan_positions(result: pd.Series) -> list[int]:
    return [i for i, value in enumerate(result.tolist()) if math.isnan(value)]


class TestDonchianHigh:
    def test_it_is_the_highest_high_of_the_prior_bars(self) -> None:
        result = donchian_high(series([1.0, 3.0, 2.0, 5.0, 4.0]), 2)
        assert nan_positions(result) == [0, 1]
        assert result.tolist()[2:] == [3.0, 3.0, 5.0]

    def test_the_current_bar_is_not_in_its_own_window(self) -> None:
        result = donchian_high(series([1.0, 1.0, 10.0]), 2)
        assert result.iloc[2] == 1.0

    def test_the_first_period_values_are_nan_and_the_next_is_not(self) -> None:
        result = donchian_high(series([float(i) for i in range(10)]), 4)
        assert nan_positions(result) == [0, 1, 2, 3]
        assert result.iloc[4] == 3.0

    def test_a_window_holding_a_nan_gives_nan(self) -> None:
        result = donchian_high(series([1.0, math.nan, 3.0, 4.0, 5.0]), 2)
        assert nan_positions(result) == [0, 1, 2, 3]
        assert result.iloc[4] == 4.0

    def test_a_period_of_one_is_the_previous_high(self) -> None:
        result = donchian_high(series([5.0, 2.0, 9.0]), 1)
        assert nan_positions(result) == [0]
        assert result.tolist()[1:] == [5.0, 2.0]

    def test_the_input_is_not_mutated_and_the_index_and_dtype_are_kept(self) -> None:
        values = series([1.0, 3.0, 2.0, 5.0])
        before = values.copy()
        result = donchian_high(values, 2)
        pd.testing.assert_series_equal(values, before)
        assert result.index.equals(values.index)
        assert str(result.dtype) == "float64"
        assert result.name == "donchian_high_2"

    def test_integer_input_gives_floats(self) -> None:
        result = donchian_high(pd.Series([1, 2, 3, 4]), 2)
        assert str(result.dtype) == "float64"
        assert result.iloc[3] == 3.0

    def test_a_period_below_one_is_refused(self) -> None:
        with pytest.raises(ValueError, match="period must be >= 1"):
            donchian_high(series([1.0, 2.0]), 0)

    def test_a_non_numeric_series_is_refused(self) -> None:
        with pytest.raises(DataError):
            donchian_high(pd.Series(["a", "b", "c"]), 2)


class TestMomentum:
    def test_it_is_the_series_minus_itself_period_bars_earlier(self) -> None:
        result = momentum(series([1.0, 3.0, 6.0, 10.0]), 2)
        assert nan_positions(result) == [0, 1]
        assert result.tolist()[2:] == [5.0, 7.0]

    def test_a_period_of_one_is_the_first_difference(self) -> None:
        result = momentum(series([1.0, 3.0, 6.0, 10.0]), 1)
        assert nan_positions(result) == [0]
        assert result.tolist()[1:] == [2.0, 3.0, 4.0]

    def test_a_flat_series_has_zero_momentum_and_a_falling_one_negative(self) -> None:
        assert momentum(series([5.0, 5.0, 5.0, 5.0]), 2).tolist()[2:] == [0.0, 0.0]
        assert momentum(series([9.0, 8.0, 7.0, 6.0]), 2).tolist()[2:] == [-2.0, -2.0]

    def test_a_nan_input_gives_nan_where_it_is_read(self) -> None:
        result = momentum(series([1.0, math.nan, 3.0, 4.0]), 1)
        assert nan_positions(result) == [0, 1, 2]
        assert result.iloc[3] == 1.0

    def test_the_input_is_not_mutated_and_the_name_and_dtype_are_set(self) -> None:
        values = series([1.0, 3.0, 6.0])
        before = values.copy()
        result = momentum(values, 1)
        pd.testing.assert_series_equal(values, before)
        assert (result.name, str(result.dtype)) == ("momentum_1", "float64")

    def test_a_period_below_one_is_refused(self) -> None:
        with pytest.raises(ValueError, match="period must be >= 1"):
            momentum(series([1.0, 2.0]), 0)


def alternating(count: int) -> tuple[pd.Series, pd.Series, pd.Series]:
    """High 101, low 99, close 100 on every bar: a true range of 2 from the second bar on."""
    return series([101.0] * count), series([99.0] * count), series([100.0] * count)


class TestKeltnerUpper:
    def test_a_constant_range_gives_the_close_plus_two_ranges(self) -> None:
        high, low, close = alternating(40)
        result = keltner_upper(high, low, close, 20, 20, 2.0)
        assert nan_positions(result) == list(range(20))
        assert result.iloc[20:].tolist() == pytest.approx([104.0] * 20)

    def test_the_first_value_lands_at_the_longer_of_the_two_warm_ups(self) -> None:
        high, low, close = alternating(40)
        assert nan_positions(keltner_upper(high, low, close, 10, 30, 2.0)) == list(range(30))
        assert nan_positions(keltner_upper(high, low, close, 30, 10, 2.0)) == list(range(29))

    def test_a_flat_market_has_a_band_equal_to_the_ema(self) -> None:
        flat = series([100.0] * 30)
        result = keltner_upper(flat, flat, flat, 20, 20, 2.0)
        assert result.iloc[20:].tolist() == pytest.approx([100.0] * 10)

    def test_a_breakout_bar_is_worked_from_the_wilder_atr_and_the_ema(self) -> None:
        high = series([101.0] * 40 + [106.0])
        low = series([99.0] * 41)
        close = series([100.0] * 40 + [106.0])
        result = keltner_upper(high, low, close, 20, 20, 2.0)
        true_range = 7.0
        wilder = (19 * 2.0 + true_range) / 20
        smoothed = 100.0 + (2.0 / 21.0) * (106.0 - 100.0)
        assert wilder == pytest.approx(2.25)
        assert result.iloc[-1] == pytest.approx(smoothed + 2.0 * wilder)
        assert result.iloc[-1] == pytest.approx(105.0714285714)

    def test_it_is_the_existing_ema_plus_the_multiple_of_the_existing_atr(self) -> None:
        high, low, close = alternating(40)
        close = close + series([float(i % 5) for i in range(40)])
        high, low = high + (close - 100.0), low + (close - 100.0)
        built = keltner_upper(high, low, close, 20, 14, 1.5)
        expected = ema(close, 20) + 1.5 * atr(high, low, close, 14)
        pd.testing.assert_series_equal(built, expected, check_names=False)

    def test_the_input_is_not_mutated_and_the_name_and_index_are_set(self) -> None:
        high, low, close = alternating(30)
        before = close.copy()
        result = keltner_upper(high, low, close, 20, 20, 2.0)
        pd.testing.assert_series_equal(close, before)
        assert result.index.equals(close.index)
        assert result.name == "keltner_upper_20_20_2"

    def test_a_period_below_one_or_a_multiplier_not_above_zero_is_refused(self) -> None:
        high, low, close = alternating(30)
        with pytest.raises(ValueError, match="ema_period must be >= 1"):
            keltner_upper(high, low, close, 0, 20, 2.0)
        with pytest.raises(ValueError, match="atr_period must be >= 1"):
            keltner_upper(high, low, close, 20, 0, 2.0)
        for bad in (0.0, -1.0, math.nan):
            with pytest.raises(ValueError, match="multiplier must be > 0"):
                keltner_upper(high, low, close, 20, 20, bad)

    def test_misaligned_indices_are_refused(self) -> None:
        high, low, close = alternating(30)
        with pytest.raises(DataError):
            keltner_upper(high, low.iloc[1:], close, 20, 20, 2.0)

    def test_it_takes_no_volume(self) -> None:
        assert list(inspect.signature(keltner_upper).parameters) == [
            "high",
            "low",
            "close",
            "ema_period",
            "atr_period",
            "multiplier",
        ]


class TestTheModuleReadsNoVolume:
    def test_no_function_here_has_a_volume_parameter(self) -> None:
        for name in breakout.__all__:
            parameters = inspect.signature(getattr(breakout, name)).parameters
            assert not any("volume" in parameter for parameter in parameters)

    def test_the_three_functions_are_exported_from_the_package(self) -> None:
        assert set(breakout.__all__) == {"donchian_high", "keltner_upper", "momentum"}
