"""R-DZ's windows: the last rows if they are consecutive bars, and the run since the last gap."""

from __future__ import annotations

import pandas as pd
import pytest

from trading_bot.core.exceptions import DataError
from trading_bot.data.historical import INTERVAL_MS
from trading_bot.strategies.m5n.gaps import BAR_WIDTH_MS, gap_free_run, gap_free_tail

FREQ = {"4h": "4h", "1d": "1D"}


def frame(timeframe: str, count: int) -> pd.DataFrame:
    index = pd.date_range("2023-01-01", periods=count, freq=FREQ[timeframe], tz="UTC")
    return pd.DataFrame({"close": [float(i) for i in range(count)]}, index=index)


def without(candles: pd.DataFrame, *positions: int) -> pd.DataFrame:
    return candles.drop(candles.index[list(positions)])


class TestTheWidths:
    def test_they_equal_the_stores_interval_widths(self) -> None:
        assert {"4h": INTERVAL_MS["4h"], "1d": INTERVAL_MS["1d"]} == BAR_WIDTH_MS


@pytest.mark.parametrize("timeframe", ["4h", "1d"])
class TestGapFreeTail:
    def test_consecutive_bars_give_the_last_rows(self, timeframe: str) -> None:
        candles = frame(timeframe, 10)
        tail = gap_free_tail(candles, timeframe, 4)
        assert tail is not None
        assert tail["close"].tolist() == [6.0, 7.0, 8.0, 9.0]

    def test_exactly_the_rows_asked_for_are_enough(self, timeframe: str) -> None:
        candles = frame(timeframe, 4)
        tail = gap_free_tail(candles, timeframe, 4)
        assert tail is not None
        assert len(tail) == 4

    def test_fewer_rows_than_asked_for_give_none(self, timeframe: str) -> None:
        assert gap_free_tail(frame(timeframe, 3), timeframe, 4) is None

    def test_a_missing_bar_inside_the_tail_gives_none(self, timeframe: str) -> None:
        candles = without(frame(timeframe, 10), 7)
        assert len(candles) == 9
        assert gap_free_tail(candles, timeframe, 4) is None

    def test_a_missing_bar_before_the_tail_gives_the_tail(self, timeframe: str) -> None:
        candles = without(frame(timeframe, 10), 2)
        tail = gap_free_tail(candles, timeframe, 4)
        assert tail is not None
        assert tail["close"].tolist() == [6.0, 7.0, 8.0, 9.0]

    def test_a_gap_exactly_at_the_tails_first_row_is_inside_it(self, timeframe: str) -> None:
        candles = without(frame(timeframe, 10), 5)
        assert gap_free_tail(candles, timeframe, 4) is not None
        assert gap_free_tail(candles, timeframe, 5) is None

    def test_one_row_is_always_gap_free(self, timeframe: str) -> None:
        candles = without(frame(timeframe, 10), 4, 7)
        tail = gap_free_tail(candles, timeframe, 1)
        assert tail is not None
        assert tail["close"].tolist() == [9.0]

    def test_a_repeated_open_time_is_a_gap(self, timeframe: str) -> None:
        candles = frame(timeframe, 6)
        repeated = pd.concat([candles.iloc[:4], candles.iloc[3:]])
        assert gap_free_tail(repeated, timeframe, 4) is None

    def test_an_out_of_order_row_is_a_gap(self, timeframe: str) -> None:
        candles = frame(timeframe, 6)
        shuffled = candles.iloc[[0, 1, 3, 2, 4, 5]]
        assert gap_free_tail(shuffled, timeframe, 4) is None

    def test_the_input_is_not_mutated(self, timeframe: str) -> None:
        candles = frame(timeframe, 10)
        before = candles.copy()
        gap_free_tail(candles, timeframe, 4)
        pd.testing.assert_frame_equal(candles, before)

    def test_zero_bars_is_refused(self, timeframe: str) -> None:
        with pytest.raises(ValueError, match="bars must be >= 1"):
            gap_free_tail(frame(timeframe, 4), timeframe, 0)


class TestTheWidthIsThatOfTheTimeframe:
    def test_four_hour_bars_are_consecutive_in_a_4h_frame_and_gaps_in_a_1d_frame(self) -> None:
        assert gap_free_tail(frame("4h", 5), "4h", 5) is not None
        assert gap_free_tail(frame("4h", 5), "1d", 5) is None

    def test_daily_bars_are_consecutive_in_a_1d_frame_and_gaps_in_a_4h_frame(self) -> None:
        assert gap_free_tail(frame("1d", 5), "1d", 5) is not None
        assert gap_free_tail(frame("1d", 5), "4h", 5) is None

    @pytest.mark.parametrize("timeframe", ["1m", "1h", "1w", ""])
    def test_another_timeframe_is_refused(self, timeframe: str) -> None:
        with pytest.raises(DataError, match="not a decision timeframe"):
            gap_free_tail(frame("1d", 5), timeframe, 2)
        with pytest.raises(DataError, match="not a decision timeframe"):
            gap_free_run(frame("1d", 5), timeframe)

    def test_another_timeframe_is_refused_even_for_a_frame_too_short_to_have_a_gap(self) -> None:
        with pytest.raises(DataError):
            gap_free_run(frame("1d", 1), "1h")


@pytest.mark.parametrize("timeframe", ["4h", "1d"])
class TestGapFreeRun:
    def test_no_gap_gives_the_whole_frame(self, timeframe: str) -> None:
        candles = frame(timeframe, 10)
        pd.testing.assert_frame_equal(gap_free_run(candles, timeframe), candles)

    def test_the_run_starts_after_the_last_gap(self, timeframe: str) -> None:
        candles = without(frame(timeframe, 12), 3, 7)
        run = gap_free_run(candles, timeframe)
        assert run["close"].tolist() == [8.0, 9.0, 10.0, 11.0]

    def test_a_last_row_that_follows_a_gap_is_a_run_of_one(self, timeframe: str) -> None:
        candles = without(frame(timeframe, 10), 8)
        run = gap_free_run(candles, timeframe)
        assert run["close"].tolist() == [9.0]

    def test_an_empty_or_one_row_frame_is_returned_as_it_is(self, timeframe: str) -> None:
        assert len(gap_free_run(frame(timeframe, 0), timeframe)) == 0
        assert len(gap_free_run(frame(timeframe, 1), timeframe)) == 1

    def test_a_repeated_open_time_ends_the_run_before_it(self, timeframe: str) -> None:
        candles = frame(timeframe, 6)
        repeated = pd.concat([candles.iloc[:4], candles.iloc[3:]])
        run = gap_free_run(repeated, timeframe)
        assert run["close"].tolist() == [3.0, 4.0, 5.0]

    def test_the_input_is_not_mutated(self, timeframe: str) -> None:
        candles = without(frame(timeframe, 12), 3)
        before = candles.copy()
        gap_free_run(candles, timeframe)
        pd.testing.assert_frame_equal(candles, before)
