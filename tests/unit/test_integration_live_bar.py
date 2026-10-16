"""``tests/integration/live_bar.py``: the assertion the live market-data test makes about the first live candle (M5m P126, R-DI).

The integration test itself needs credentials, the network and a minute boundary, so what it asserts is shown here on fabricated
frames: the appended bar, the replaced bar that differs, the replaced bar that is IDENTICAL (the case P125's gate failed on), and
the ways a buffer can be wrong.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pandas as pd
import pytest

from tests.integration.live_bar import assert_last_bar_is_the_live_candle
from trading_bot.core.models import Candle

UTC = timezone.utc
OPEN = datetime(2026, 10, 16, 11, 8, tzinfo=UTC)
MINUTE = timedelta(minutes=1)


def candle(open_time: datetime = OPEN, *, close: str = "82320.00") -> Candle:
    return Candle(
        symbol="BTCUSDT",
        timeframe="1m",
        open_time=open_time,
        close_time=open_time + MINUTE - timedelta(milliseconds=1),
        open=Decimal("82318.01"),
        high=Decimal("82320.00"),
        low=Decimal("82308.00"),
        close=Decimal(close),
        volume=Decimal("0.11608"),
    )


def frame(*bars: tuple[datetime, float, float, float, float, float]) -> pd.DataFrame:
    return pd.DataFrame(
        [list(b[1:]) for b in bars],
        columns=["open", "high", "low", "close", "volume"],
        index=pd.DatetimeIndex([b[0] for b in bars], name="open_time"),
    )


SEED_ROW = (OPEN - MINUTE, 82300.0, 82305.0, 82295.0, 82301.0, 1.0)
LIVE_ROW = (OPEN, 82318.01, 82320.0, 82308.0, 82320.0, 0.11608)


class TestWhatItAccepts:
    def test_an_appended_bar_that_is_the_live_candle(self) -> None:
        assert_last_bar_is_the_live_candle(frame(SEED_ROW, LIVE_ROW), candle())

    def test_an_identical_replacement_is_correct(self) -> None:
        # P125's gate: the REST seed was fetched after the bar closed, so it already held the final values and the
        # stream delivered the same ones. Seed and live are the same row, and nothing is wrong.
        assert_last_bar_is_the_live_candle(frame(LIVE_ROW), candle())

    def test_float_noise_is_tolerated_in_every_column(self) -> None:
        noisy = (OPEN, 82318.01 + 1e-9, 82320.0 - 1e-9, 82308.0, 82320.0 + 1e-9, 0.11608 + 1e-15)
        assert_last_bar_is_the_live_candle(frame(SEED_ROW, noisy), candle())


class TestWhatItRefuses:
    def test_a_buffer_that_dropped_the_bar_and_still_holds_the_seeds_different_one(self) -> None:
        stale = (OPEN, 82318.01, 82319.0, 82308.0, 82319.0, 0.05)
        with pytest.raises(AssertionError, match="last high"):
            assert_last_bar_is_the_live_candle(frame(SEED_ROW, stale), candle())

    def test_a_buffer_whose_last_bar_is_another_bar(self) -> None:
        with pytest.raises(AssertionError, match="opens"):
            assert_last_bar_is_the_live_candle(frame(SEED_ROW), candle())

    @pytest.mark.parametrize("column", ["open", "high", "low", "close", "volume"])
    def test_each_of_the_five_values_is_checked(self, column: str) -> None:
        values = dict(zip(["open", "high", "low", "close", "volume"], LIVE_ROW[1:], strict=True))
        values[column] += 1.0
        wrong = (
            OPEN,
            values["open"],
            values["high"],
            values["low"],
            values["close"],
            values["volume"],
        )
        with pytest.raises(AssertionError, match=f"last {column}"):
            assert_last_bar_is_the_live_candle(frame(SEED_ROW, wrong), candle())

    def test_the_close_alone_differing_by_a_tick_is_caught(self) -> None:
        with pytest.raises(AssertionError, match="last close"):
            assert_last_bar_is_the_live_candle(frame(SEED_ROW, LIVE_ROW), candle(close="82320.01"))
