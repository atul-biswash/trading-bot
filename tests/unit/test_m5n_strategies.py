"""The six M5n candidates (R-DY) under R-DX and R-DZ, on synthetic frames with hand-worked values.

Every frame is built here from literals. A "decision frame" is what the strategy interface gets:
OHLCV rows indexed by each bar's open time. Expected figures are literals or are worked in the test
from the literals that build the frame, never by the code under test.
"""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
from pathlib import Path

import pandas as pd
import pytest

import trading_bot.strategies.m5n  # noqa: F401  (registers the six candidates)
import trading_bot.strategies.registry as registry
from trading_bot.core.enums import SignalAction
from trading_bot.core.exceptions import DataError
from trading_bot.core.models import Candle, Signal
from trading_bot.strategies.registry import available_strategies, create_strategy

FREQ = {"4h": "4h", "1d": "1D"}
WIDTH = {"4h": timedelta(hours=4), "1d": timedelta(days=1)}
PAIRS = ("BTCUSDT", "ETHUSDT")
DONCHIANS = [
    ("donchian_1d_20", "1d", 20),
    ("donchian_1d_55", "1d", 55),
    ("donchian_4h_20", "4h", 20),
]


def build(
    timeframe: str,
    closes: list[float],
    *,
    highs: list[float] | None = None,
    lows: list[float] | None = None,
    volume: float = 1.0,
) -> pd.DataFrame:
    index = pd.date_range("2023-01-01", periods=len(closes), freq=FREQ[timeframe], tz="UTC")
    index.name = "open_time"
    return pd.DataFrame(
        {
            "open": closes,
            "high": highs if highs is not None else closes,
            "low": lows if lows is not None else closes,
            "close": closes,
            "volume": volume,
        },
        index=index,
    )


def last_candle(symbol: str, timeframe: str, frame: pd.DataFrame) -> Candle:
    opened = frame.index[-1].to_pydatetime()
    row = frame.iloc[-1]
    return Candle(
        symbol=symbol,
        timeframe=timeframe,
        open_time=opened,
        close_time=opened + WIDTH[timeframe] - timedelta(milliseconds=1),
        open=str(row["close"]),
        high=str(row.get("high", row["close"])),
        low=str(row.get("low", row["close"])),
        close=str(row["close"]),
        volume="1",
    )


def decide(
    name: str, timeframe: str, frame: pd.DataFrame, *, symbol: str = "BTCUSDT", enforce: bool = True
) -> Signal | None:
    strategy = create_strategy(name, enforce_gaps=enforce)
    return strategy.generate_signal(
        symbol, frame, last_candle=last_candle(symbol, timeframe, frame)
    )


def without(frame: pd.DataFrame, *positions: int) -> pd.DataFrame:
    return frame.drop(frame.index[list(positions)])


def fires_over_prefixes(name: str, timeframe: str, frame: pd.DataFrame, first: int) -> list[int]:
    return [
        n
        for n in range(first, len(frame) + 1)
        if decide(name, timeframe, frame.iloc[:n]) is not None
    ]


def donchian_frame(
    timeframe: str,
    period: int,
    *,
    last_close: float,
    last_high: float | None = None,
    prev_close: float = 9.5,
    prev_high: float = 10.0,
    extra: int = 0,
) -> pd.DataFrame:
    """period + 2 rows (plus ``extra`` older ones): highs of 10, a previous bar, then the decision bar."""
    flat = period + 1 + extra
    closes = [9.5] * (flat - 1) + [prev_close, last_close]
    highs = [10.0] * (flat - 1) + [prev_high, last_high if last_high is not None else last_close]
    lows = [9.0] * (flat + 1)
    return build(timeframe, closes, highs=highs, lows=lows)


SIX_NAMES = (
    "donchian_1d_20",
    "donchian_1d_55",
    "sma_cross_1d_50_200",
    "donchian_4h_20",
    "keltner_4h_20_2",
    "tsmom_1d_90",
)


class TestTheSixAreRegisteredAndIndependent:
    def test_the_six_names_are_registered(self) -> None:
        for name in SIX_NAMES:
            assert create_strategy(name).name == name

    def test_they_are_listed_once_imported_and_the_registry_does_not_import_them(self) -> None:
        listed = [name for name in available_strategies() if name in SIX_NAMES]
        assert sorted(listed) == sorted(SIX_NAMES)
        source = Path(registry.__file__).read_text(encoding="utf-8")
        assert "m5n" not in source

    @pytest.mark.parametrize(
        ("name", "bars"),
        [
            ("donchian_1d_20", 22),
            ("donchian_1d_55", 57),
            ("sma_cross_1d_50_200", 201),
            ("donchian_4h_20", 22),
            ("keltner_4h_20_2", 22),
            ("tsmom_1d_90", 92),
        ],
    )
    def test_the_warmup_is_the_window_the_edge_reads(self, name: str, bars: int) -> None:
        assert create_strategy(name).warmup_period == bars

    def test_gap_enforcement_defaults_on_and_must_be_a_bool(self) -> None:
        assert create_strategy("tsmom_1d_90").enforce_gaps is True
        with pytest.raises(ValueError, match="enforce_gaps must be a bool"):
            create_strategy("tsmom_1d_90", enforce_gaps=1)


@pytest.mark.parametrize(("name", "timeframe", "period"), DONCHIANS)
class TestDonchian:
    def test_a_close_above_the_prior_highs_fires_on_that_bar(
        self, name: str, timeframe: str, period: int
    ) -> None:
        found = decide(name, timeframe, donchian_frame(timeframe, period, last_close=10.5))
        assert found is not None
        assert found.action is SignalAction.BUY
        assert found.price == Decimal("10.5")
        assert found.metadata["donchian_high"] == 10.0
        assert found.metadata["period"] == period

    def test_a_close_equal_to_the_highest_high_does_not(
        self, name: str, timeframe: str, period: int
    ) -> None:
        assert decide(name, timeframe, donchian_frame(timeframe, period, last_close=10.0)) is None

    def test_one_tick_above_does(self, name: str, timeframe: str, period: int) -> None:
        assert (
            decide(name, timeframe, donchian_frame(timeframe, period, last_close=10.01)) is not None
        )

    def test_a_close_below_does_not(self, name: str, timeframe: str, period: int) -> None:
        assert decide(name, timeframe, donchian_frame(timeframe, period, last_close=9.9)) is None

    def test_a_run_of_new_highs_signals_once_not_on_every_bar(
        self, name: str, timeframe: str, period: int
    ) -> None:
        frame = donchian_frame(timeframe, period, last_close=11.0, prev_close=10.5, prev_high=10.6)
        assert decide(name, timeframe, frame) is None

    def test_a_previous_close_equal_to_its_threshold_counts_as_not_above(
        self, name: str, timeframe: str, period: int
    ) -> None:
        frame = donchian_frame(timeframe, period, last_close=10.5, prev_close=10.0, prev_high=10.0)
        assert decide(name, timeframe, frame) is not None

    def test_it_fires_on_the_crossing_bar_and_on_no_other(
        self, name: str, timeframe: str, period: int
    ) -> None:
        rising = [10.5, 10.8, 11.1, 11.4]
        closes = [*([9.5] * (period + 3)), *rising]
        highs = [*([10.0] * (period + 3)), *rising]
        frame = build(timeframe, closes, highs=highs, lows=[9.0] * len(closes))
        assert fires_over_prefixes(name, timeframe, frame, period + 2) == [period + 4]

    def test_fewer_rows_than_the_window_give_no_signal(
        self, name: str, timeframe: str, period: int
    ) -> None:
        frame = donchian_frame(timeframe, period, last_close=10.5)
        assert decide(name, timeframe, frame.iloc[1:]) is None
        assert decide(name, timeframe, frame) is not None

    def test_a_missing_bar_inside_the_window_gives_no_signal_until_the_window_is_clean(
        self, name: str, timeframe: str, period: int
    ) -> None:
        frame = without(donchian_frame(timeframe, period, last_close=10.5, extra=1), 3)
        assert decide(name, timeframe, frame) is None
        assert decide(name, timeframe, frame, enforce=False) is not None

    def test_a_missing_bar_before_the_window_does_not_matter(
        self, name: str, timeframe: str, period: int
    ) -> None:
        frame = without(donchian_frame(timeframe, period, last_close=10.5, extra=2), 1)
        assert decide(name, timeframe, frame) is not None

    def test_the_volume_column_changes_nothing(
        self, name: str, timeframe: str, period: int
    ) -> None:
        base = donchian_frame(timeframe, period, last_close=10.5)
        wanted = decide(name, timeframe, base)
        assert wanted is not None
        for volume in (0.0, float("nan"), 1e12):
            changed = base.assign(volume=volume)
            assert decide(name, timeframe, changed) == wanted
        assert decide(name, timeframe, base.drop(columns="volume")) == wanted

    @pytest.mark.parametrize("symbol", PAIRS)
    def test_the_signal_carries_the_pair_the_candle_price_and_the_close_time(
        self, name: str, timeframe: str, period: int, symbol: str
    ) -> None:
        frame = donchian_frame(timeframe, period, last_close=10.5)
        found = decide(name, timeframe, frame, symbol=symbol)
        assert found is not None
        candle = last_candle(symbol, timeframe, frame)
        assert (found.symbol, found.price, found.timestamp) == (
            symbol,
            candle.close,
            candle.close_time,
        )
        assert found.strength == 1.0
        assert found.metadata["strategy"] == name
        assert all(type(value) in (str, int, float) for value in found.metadata.values())

    def test_a_candle_of_another_timeframe_is_refused(
        self, name: str, timeframe: str, period: int
    ) -> None:
        frame = donchian_frame(timeframe, period, last_close=10.5)
        other = "4h" if timeframe == "1d" else "1d"
        strategy = create_strategy(name)
        with pytest.raises(DataError, match="decides on"):
            strategy.generate_signal(
                "BTCUSDT", frame, last_candle=last_candle("BTCUSDT", other, frame)
            )

    def test_a_frame_with_no_high_column_is_a_data_error(
        self, name: str, timeframe: str, period: int
    ) -> None:
        frame = donchian_frame(timeframe, period, last_close=10.5).drop(columns="high")
        with pytest.raises(DataError, match="no 'high' column"):
            decide(name, timeframe, frame)


def cross_frame(last: float, *, count: int = 200, base: float = 100.0) -> pd.DataFrame:
    return build("1d", [base] * count + [last])


class TestSmaCross:
    NAME = "sma_cross_1d_50_200"

    def test_the_fast_average_crossing_above_the_slow_fires_on_that_bar(self) -> None:
        found = decide(self.NAME, "1d", cross_frame(160.0))
        assert found is not None
        assert found.action is SignalAction.BUY
        assert found.metadata["fast_sma"] == pytest.approx((49 * 100.0 + 160.0) / 50)
        assert found.metadata["slow_sma"] == pytest.approx((199 * 100.0 + 160.0) / 200)
        assert found.metadata["prev_fast_sma"] == 100.0
        assert found.metadata["prev_slow_sma"] == 100.0

    def test_equal_averages_on_both_bars_do_not_fire(self) -> None:
        assert decide(self.NAME, "1d", cross_frame(100.0)) is None

    def test_a_fast_average_already_above_does_not_fire_again(self) -> None:
        closes = [100.0] * 150 + [110.0] * 50 + [120.0]
        assert decide(self.NAME, "1d", build("1d", closes)) is None

    def test_a_fast_average_below_and_staying_below_does_not_fire(self) -> None:
        closes = [100.0] * 150 + [90.0] * 50 + [91.0]
        assert decide(self.NAME, "1d", build("1d", closes)) is None

    def test_it_fires_on_the_crossing_bar_and_on_no_other(self) -> None:
        frame = build("1d", [100.0] * 200 + [160.0, 160.0, 160.0, 160.0])
        assert fires_over_prefixes(self.NAME, "1d", frame, 201) == [201]

    def test_fewer_than_slow_plus_one_rows_give_no_signal(self) -> None:
        assert decide(self.NAME, "1d", build("1d", [100.0] * 199 + [160.0])) is None

    def test_a_missing_bar_inside_the_window_gives_no_signal(self) -> None:
        frame = without(build("1d", [100.0] * 201 + [160.0]), 100)
        assert decide(self.NAME, "1d", frame) is None
        assert decide(self.NAME, "1d", frame, enforce=False) is not None

    def test_a_missing_bar_before_the_window_does_not_matter(self) -> None:
        frame = without(build("1d", [100.0] * 202 + [160.0]), 1)
        assert decide(self.NAME, "1d", frame) is not None

    @pytest.mark.parametrize("symbol", PAIRS)
    def test_both_pairs_and_the_volume_column(self, symbol: str) -> None:
        base = cross_frame(160.0)
        wanted = decide(self.NAME, "1d", base, symbol=symbol)
        assert wanted is not None
        assert wanted.symbol == symbol
        for volume in (0.0, float("nan"), 1e12):
            assert decide(self.NAME, "1d", base.assign(volume=volume), symbol=symbol) == wanted
        assert decide(self.NAME, "1d", base.drop(columns="volume"), symbol=symbol) == wanted

    def test_a_4h_candle_is_refused(self) -> None:
        frame = cross_frame(160.0)
        strategy = create_strategy(self.NAME)
        with pytest.raises(DataError, match="decides on 1d"):
            strategy.generate_signal(
                "BTCUSDT", frame, last_candle=last_candle("BTCUSDT", "4h", frame)
            )


class TestTsmom:
    NAME = "tsmom_1d_90"

    def test_momentum_turning_from_zero_to_positive_fires(self) -> None:
        found = decide(self.NAME, "1d", build("1d", [100.0] * 91 + [101.0]))
        assert found is not None
        assert found.action is SignalAction.BUY
        assert found.metadata["momentum"] == 1.0
        assert found.metadata["prev_momentum"] == 0.0

    def test_momentum_turning_from_negative_to_positive_fires(self) -> None:
        found = decide(self.NAME, "1d", build("1d", [100.0] * 90 + [99.0, 101.0]))
        assert found is not None
        assert found.metadata["prev_momentum"] == -1.0

    def test_a_close_equal_to_the_close_90_bars_earlier_does_not_fire(self) -> None:
        assert decide(self.NAME, "1d", build("1d", [100.0] * 92)) is None

    def test_momentum_already_positive_does_not_fire_again(self) -> None:
        assert decide(self.NAME, "1d", build("1d", [100.0] * 90 + [101.0, 102.0])) is None

    def test_negative_momentum_does_not_fire(self) -> None:
        assert decide(self.NAME, "1d", build("1d", [100.0] * 91 + [99.0])) is None

    def test_it_fires_on_the_crossing_bar_and_on_no_other(self) -> None:
        frame = build("1d", [100.0] * 91 + [101.0, 102.0, 103.0, 104.0])
        assert fires_over_prefixes(self.NAME, "1d", frame, 92) == [92]

    def test_fewer_than_lookback_plus_two_rows_give_no_signal(self) -> None:
        assert decide(self.NAME, "1d", build("1d", [100.0] * 90 + [101.0])) is None

    def test_a_missing_bar_inside_the_window_gives_no_signal(self) -> None:
        frame = without(build("1d", [100.0] * 92 + [101.0]), 40)
        assert decide(self.NAME, "1d", frame) is None
        assert decide(self.NAME, "1d", frame, enforce=False) is not None

    def test_a_missing_bar_before_the_window_does_not_matter(self) -> None:
        assert decide(self.NAME, "1d", without(build("1d", [100.0] * 93 + [101.0]), 1)) is not None

    @pytest.mark.parametrize("symbol", PAIRS)
    def test_both_pairs_and_the_volume_column(self, symbol: str) -> None:
        base = build("1d", [100.0] * 91 + [101.0])
        wanted = decide(self.NAME, "1d", base, symbol=symbol)
        assert wanted is not None
        assert wanted.symbol == symbol
        for volume in (0.0, float("nan"), 1e12):
            assert decide(self.NAME, "1d", base.assign(volume=volume), symbol=symbol) == wanted
        assert decide(self.NAME, "1d", base.drop(columns="volume"), symbol=symbol) == wanted


def volatile(count: int, *, tail: tuple[float, float, float] | None = None) -> pd.DataFrame:
    """High 101, low 99, close 100 for ``count`` bars, then optionally one (high, low, close) bar."""
    highs, lows, closes = [101.0] * count, [99.0] * count, [100.0] * count
    if tail is not None:
        highs.append(tail[0])
        lows.append(tail[1])
        closes.append(tail[2])
    return build("4h", closes, highs=highs, lows=lows)


class TestKeltner:
    NAME = "keltner_4h_20_2"

    def test_a_close_above_the_band_fires_with_the_hand_worked_band(self) -> None:
        found = decide(self.NAME, "4h", volatile(40, tail=(106.0, 99.0, 106.0)))
        assert found is not None
        assert found.action is SignalAction.BUY
        assert found.metadata["upper_band"] == pytest.approx(105.0714285714)
        assert found.metadata["prev_upper_band"] == pytest.approx(104.0)

    def test_the_band_sits_between_a_close_that_fails_and_one_that_passes(self) -> None:
        below = decide(self.NAME, "4h", volatile(40, tail=(104.8, 99.0, 104.8)))
        above = decide(self.NAME, "4h", volatile(40, tail=(104.9, 99.0, 104.9)))
        assert below is None
        assert above is not None
        assert above.metadata["upper_band"] == pytest.approx(100.0 + (2 / 21) * 4.9 + 2 * 2.195)

    def test_a_close_inside_the_band_does_not_fire(self) -> None:
        assert decide(self.NAME, "4h", volatile(40, tail=(103.0, 99.0, 103.0))) is None

    def test_a_close_already_above_does_not_fire_again(self) -> None:
        frame = volatile(40, tail=(106.0, 99.0, 106.0))
        frame.loc[frame.index[-1] + timedelta(hours=4)] = [107.0, 107.0, 99.0, 107.0, 1.0]
        assert decide(self.NAME, "4h", frame) is None

    def test_it_fires_on_the_crossing_bar_and_on_no_other(self) -> None:
        base = volatile(40, tail=(106.0, 99.0, 106.0))
        index = pd.date_range(base.index[0], periods=43, freq="4h", tz="UTC")
        frame = pd.DataFrame(
            {
                "open": [*base["close"], 107.0, 108.0],
                "high": [*base["high"], 107.0, 108.0],
                "low": [*base["low"], 99.0, 99.0],
                "close": [*base["close"], 107.0, 108.0],
                "volume": 1.0,
            },
            index=index,
        )
        assert fires_over_prefixes(self.NAME, "4h", frame, 22) == [41]

    def test_a_run_of_21_bars_has_no_previous_band_so_no_signal(self) -> None:
        assert decide(self.NAME, "4h", volatile(20, tail=(106.0, 99.0, 106.0))) is None

    def test_a_run_of_22_bars_is_enough(self) -> None:
        assert decide(self.NAME, "4h", volatile(21, tail=(106.0, 99.0, 106.0))) is not None

    def test_a_gap_leaves_a_short_run_and_no_signal_until_it_is_long_enough(self) -> None:
        frame = without(volatile(60, tail=(106.0, 99.0, 106.0)), 45)
        assert len(gap_run(frame)) == 15
        assert decide(self.NAME, "4h", frame) is None
        assert decide(self.NAME, "4h", frame, enforce=False) is not None

    def test_after_a_gap_the_band_is_the_one_the_run_alone_would_give(self) -> None:
        frame = without(volatile(60, tail=(106.0, 99.0, 106.0)), 20)
        run_alone = volatile(40, tail=(106.0, 99.0, 106.0))
        gated = decide(self.NAME, "4h", frame)
        fresh = decide(self.NAME, "4h", run_alone)
        assert gated is not None
        assert fresh is not None
        assert gated.metadata["upper_band"] == fresh.metadata["upper_band"]

    @pytest.mark.parametrize("symbol", PAIRS)
    def test_both_pairs_and_the_volume_column(self, symbol: str) -> None:
        base = volatile(40, tail=(106.0, 99.0, 106.0))
        wanted = decide(self.NAME, "4h", base, symbol=symbol)
        assert wanted is not None
        assert wanted.symbol == symbol
        for volume in (0.0, float("nan"), 1e12):
            assert decide(self.NAME, "4h", base.assign(volume=volume), symbol=symbol) == wanted
        assert decide(self.NAME, "4h", base.drop(columns="volume"), symbol=symbol) == wanted

    def test_a_frame_with_no_low_column_is_a_data_error(self) -> None:
        with pytest.raises(DataError, match="no 'low' column"):
            decide(self.NAME, "4h", volatile(40, tail=(106.0, 99.0, 106.0)).drop(columns="low"))

    def test_a_1d_candle_is_refused(self) -> None:
        frame = volatile(40, tail=(106.0, 99.0, 106.0))
        strategy = create_strategy(self.NAME)
        with pytest.raises(DataError, match="decides on 4h"):
            strategy.generate_signal(
                "BTCUSDT", frame, last_candle=last_candle("BTCUSDT", "1d", frame)
            )


def gap_run(frame: pd.DataFrame) -> pd.DataFrame:
    from trading_bot.strategies.m5n.gaps import gap_free_run

    return gap_free_run(frame, "4h")
