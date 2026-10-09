"""``sma`` is window-only (R-AQ, R-AX): a value depends on its own window and on nothing before it.

The defect (M5m-184, M5m-185): pandas' ``rolling().mean()`` keeps a running sum, so its last digit depends on
every row ahead of the window. An exact tie of two averages -- SMA(20) equals SMA(50) in the decimal closes --
was decided by that noise and flipped with the buffer's length, which differs between a live buffer, a restarted
one and a backtest's. These tests prove the property three ways (buffer starts, the whole series, chunk
boundaries), pin the NaN and index contract, and reproduce the M5m-184 bar from 120 real ETHUSDT 5m closes.

Every comparison of two floats here is BITWISE (``tobytes``), never ``==`` or a tolerance: a result that is
merely close is exactly the thing the defect was.
"""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

import numpy as np
import pandas as pd
import pytest

import trading_bot.indicators.indicators as indicators_module
from trading_bot.core.exceptions import DataError
from trading_bot.core.models import Candle
from trading_bot.indicators import sma
from trading_bot.strategies.examples.sma_crossover import SmaCrossoverStrategy
from trading_bot.strategies.helpers import crossed_above, crossed_below, last_two

#: The 120 ETHUSDT 5m closes ending at the bar that opens 2024-03-05T03:30:00Z (the last), from the stored
#: mainnet series. At that bar SMA(20) and SMA(50) are both 3627.774 in the decimal closes.
TIE_BAR_CLOSES = [
    3564.72, 3571.32, 3551.33, 3556.73, 3543.64, 3557.78, 3545.41, 3555.28,
    3560.1, 3556.14, 3532.99, 3550.84, 3560.85, 3561.0, 3567.79, 3581.76,
    3596.41, 3585.92, 3594.34, 3590.0, 3586.94, 3591.59, 3604.99, 3594.81,
    3592.2, 3589.07, 3589.01, 3589.67, 3593.01, 3592.26, 3587.0, 3588.25,
    3584.45, 3583.65, 3579.74, 3579.93, 3590.79, 3589.16, 3585.47, 3583.44,
    3583.37, 3582.17, 3576.16, 3568.6, 3563.78, 3564.07, 3564.41, 3565.31,
    3572.28, 3566.27, 3571.0, 3572.4, 3580.4, 3586.55, 3588.61, 3582.11,
    3582.36, 3567.81, 3574.87, 3570.99, 3586.98, 3594.62, 3592.59, 3599.25,
    3608.48, 3624.61, 3631.6, 3634.81, 3629.4, 3625.93, 3623.23, 3612.55,
    3636.57, 3627.47, 3626.6, 3626.3, 3627.76, 3625.39, 3629.4, 3627.0,
    3629.48, 3625.0, 3617.71, 3609.17, 3615.42, 3635.8, 3624.31, 3628.26,
    3618.94, 3617.89, 3621.41, 3620.97, 3620.0, 3629.35, 3636.85, 3639.92,
    3644.99, 3638.49, 3648.1, 3648.89, 3642.72, 3633.26, 3637.56, 3629.97,
    3623.78, 3633.26, 3621.48, 3615.47, 3610.06, 3617.27, 3625.1, 3624.45,
    3623.1, 3619.02, 3619.5, 3615.32, 3627.4, 3640.18, 3643.5, 3653.08,
]  # fmt: skip
BUFFER_LENGTHS = (52, 60, 80, 120)
LENGTHS = (51, 52, 60, 80, 120, 200, 300, 400, 543, 700, 831, 900, 1000)


def bits(value: float) -> bytes:
    return np.float64(value).tobytes()


def tie_window(rows: int) -> pd.Series:
    assert len(TIE_BAR_CLOSES) == 120
    return pd.Series(TIE_BAR_CLOSES[-rows:], dtype="float64")


def walks() -> dict[str, pd.Series]:
    rng = np.random.default_rng(20261009)
    walk = 3600 + np.cumsum(rng.normal(0, 3.0, 2500))
    ticks = np.round(walk, 2)
    plateaus = np.round(3600 + np.cumsum(rng.integers(-1, 2, 2500)) * 0.01, 2)
    holes = ticks.copy()
    holes[rng.integers(0, 2500, 25)] = np.nan
    return {
        "a random walk in full floats": pd.Series(walk),
        "a random walk on a 0.01 tick": pd.Series(ticks),
        "plateaus with many exact repeats": pd.Series(plateaus),
        "a tick walk with 25 NaN": pd.Series(holes),
    }


class TestAValueDependsOnItsWindowAlone:
    @pytest.mark.parametrize("period", [20, 50])
    def test_the_last_value_is_the_same_bits_whatever_the_buffer_holds_ahead_of_the_window(
        self, period: int
    ) -> None:
        rng = np.random.default_rng(period)
        for label, series in walks().items():
            ends = rng.integers(1100, len(series) - 1, 40)
            for end in ends:
                seen = set()
                for rows in LENGTHS:
                    window = series.iloc[end + 1 - rows : end + 1]
                    seen.add(bits(sma(window, period).iloc[-1]))
                assert len(seen) == 1, (label, period, int(end), len(seen))

    @pytest.mark.parametrize("period", [20, 50])
    def test_every_value_equals_the_value_computed_from_the_whole_series(self, period: int) -> None:
        rng = np.random.default_rng(period + 1)
        for label, series in walks().items():
            whole = sma(series, period).to_numpy()
            for end in rng.integers(period, len(series) - 1, 60):
                for rows in (period, period + 1, 77, 333, int(end) + 1):
                    rows = min(rows, int(end) + 1)
                    value = sma(series.iloc[end + 1 - rows : end + 1], period).iloc[-1]
                    assert bits(value) == bits(whole[end]), (label, period, int(end), rows)

    def test_a_window_is_summed_the_same_whichever_chunk_it_falls_in(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        series = walks()["a random walk on a 0.01 tick"]
        whole = sma(series, 20).to_numpy().copy()
        for budget in (20, 21, 40, 41, 100, 777):
            monkeypatch.setattr(indicators_module, "_WINDOW_BUDGET", budget)
            small = sma(series, 20).to_numpy()
            assert small.tobytes() == whole.tobytes(), budget

    def test_a_series_the_budget_cannot_hold_in_one_block_is_still_computed(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(indicators_module, "_WINDOW_BUDGET", 1)
        try:
            out = sma(pd.Series(np.arange(1.0, 11.0)), 4)
        except (
            Exception
        ) as exc:  # a failure to cope must be a FAILURE of this test, not a crash in it
            pytest.fail(f"a budget below one window raised {type(exc).__name__}: {exc}")
        assert out.iloc[3:].tolist() == [2.5, 3.5, 4.5, 5.5, 6.5, 7.5, 8.5]


class TestTheM5m184Bar:
    """ETHUSDT 5m at 2024-03-05T03:30:00Z, the bar the owner's R-AQ names."""

    def last_two_averages(self, rows: int) -> tuple[tuple[float, float], tuple[float, float]]:
        window = tie_window(rows)
        fast = last_two(sma(window, 20))
        slow = last_two(sma(window, 50))
        assert fast is not None and slow is not None
        return fast, slow

    def test_the_fixture_can_express_the_defect_pandas_rolling_flips_with_the_buffer(self) -> None:
        """The legacy computation, called directly: two outcomes across four buffer lengths."""
        outcomes = set()
        for rows in BUFFER_LENGTHS:
            window = tie_window(rows)
            fast = last_two(window.rolling(20, min_periods=20).mean())
            slow = last_two(window.rolling(50, min_periods=50).mean())
            assert fast is not None and slow is not None
            outcomes.add(crossed_below(fast, slow))
        assert outcomes == {True, False}

    def test_the_window_only_averages_are_the_same_bits_at_every_buffer_length(self) -> None:
        answers = {
            tuple(bits(v) for pair in self.last_two_averages(rows) for v in pair)
            for rows in BUFFER_LENGTHS
        }
        assert len(answers) == 1

    def test_the_outcome_is_one_answer_and_the_spurious_death_cross_is_gone(self) -> None:
        for rows in BUFFER_LENGTHS:
            fast, slow = self.last_two_averages(rows)
            assert crossed_below(fast, slow) is False
            assert crossed_above(fast, slow) is False

    def test_the_strategy_emits_the_same_signal_at_every_buffer_length(self) -> None:
        strategy = SmaCrossoverStrategy(fast_period=20, slow_period=50)
        for rows in BUFFER_LENGTHS:
            closes = TIE_BAR_CLOSES[-rows:]
            index = pd.date_range(
                end="2024-03-05T03:30:00Z", periods=rows, freq="5min", name="open_time"
            )
            frame = pd.DataFrame({"close": closes}, index=index)
            close_time = index[-1].to_pydatetime() + timedelta(minutes=5, milliseconds=-1)
            last = Candle(
                symbol="ETHUSDT",
                timeframe="5m",
                open_time=index[-1].to_pydatetime(),
                close_time=close_time,
                open=Decimal("3643.50"),
                high=Decimal("3653.08"),
                low=Decimal("3643.50"),
                close=Decimal("3653.08"),
                volume=Decimal("1"),
            )
            assert strategy.generate_signal("ETHUSDT", frame, last_candle=last) is None, rows


class TestTheContractIsKept:
    def test_the_first_period_minus_one_values_are_nan_and_the_rest_are_means(self) -> None:
        out = sma(pd.Series([1.0, 2.0, 3.0, 4.0, 5.0]), 3)
        assert out.isna().tolist() == [True, True, False, False, False]
        assert out.iloc[2:].tolist() == [2.0, 3.0, 4.0]

    def test_a_window_holding_a_nan_is_nan_and_the_average_recovers_after_it(self) -> None:
        out = sma(pd.Series([1.0, 2.0, np.nan, 4.0, 5.0, 6.0, 7.0]), 3)
        assert out.isna().tolist() == [True, True, True, True, True, False, False]
        assert out.iloc[5:].tolist() == [5.0, 6.0]

    def test_a_short_or_empty_series_is_all_nan_not_an_error(self) -> None:
        assert sma(pd.Series([1.0, 2.0]), 3).isna().all()
        assert len(sma(pd.Series([], dtype="float64"), 3)) == 0
        assert sma(pd.Series([1.0, 2.0, 3.0]), 3).iloc[-1] == 2.0
        assert sma(pd.Series([7.0]), 1).tolist() == [7.0]

    def test_infinities_follow_the_arithmetic_and_do_not_outlive_their_window(self) -> None:
        out = sma(pd.Series([1.0, np.inf, 3.0, -np.inf, 5.0, 6.0]), 2)
        assert out.iloc[1:5].tolist() == [np.inf, np.inf, -np.inf, -np.inf]
        assert out.iloc[5] == 5.5
        assert np.isnan(sma(pd.Series([np.inf, -np.inf]), 2).iloc[1])

    def test_the_index_the_name_and_the_dtype_are_the_inputs(self) -> None:
        index = pd.date_range("2024-03-01", periods=6, freq="1min", tz="UTC", name="open_time")
        out = sma(pd.Series([1, 2, 3, 4, 5, 6], index=index), 2)  # integers in, floats out
        assert out.index.equals(index) and out.index.name == "open_time"
        assert out.name == "sma_2" and str(out.dtype) == "float64"
        assert out.iloc[1:].tolist() == [1.5, 2.5, 3.5, 4.5, 5.5]

    def test_the_input_is_not_changed(self) -> None:
        series = pd.Series([1.0, 2.0, 3.0, 4.0, 5.0], name="close")
        before = series.copy()
        sma(series, 3)
        pd.testing.assert_series_equal(series, before)

    def test_a_non_positive_period_and_a_non_numeric_series_are_refused(self) -> None:
        for period in (0, -3):
            try:
                sma(pd.Series([1.0, 2.0, 3.0]), period)
            except ValueError as exc:
                assert "period" in str(exc), str(exc)
            except Exception as exc:  # the guard's own error or nothing: not a ZeroDivisionError
                pytest.fail(
                    f"period {period} raised {type(exc).__name__}, not the guard's ValueError"
                )
            else:
                pytest.fail(f"period {period} was accepted")
        with pytest.raises(DataError):
            sma(pd.Series(["a", "b", "c"]), 2)

    def test_it_agrees_with_pandas_rolling_to_the_last_few_digits_on_a_long_series(self) -> None:
        series = walks()["a random walk in full floats"]
        ours = sma(series, 50).to_numpy()
        theirs = series.rolling(50, min_periods=50).mean().to_numpy()
        assert np.isnan(ours[:49]).all() and np.isnan(theirs[:49]).all()
        np.testing.assert_allclose(ours[49:], theirs[49:], rtol=1e-12, atol=0)
        assert ours.tobytes() != theirs.tobytes()  # not bit-equal: that is the point

    def test_a_year_long_series_is_computed_in_bounded_blocks(self) -> None:
        series = pd.Series(
            3600 + np.cumsum(np.random.default_rng(3).normal(0, 1.0, 120_000)),
            index=pd.date_range("2024-01-01", periods=120_000, freq="1min", tz="UTC"),
        )
        out = sma(series, 200)
        assert out.isna().sum() == 199
        tail = sma(series.iloc[-250:], 200)
        assert bits(out.iloc[-1]) == bits(tail.iloc[-1])
        assert out.index.equals(series.index)
