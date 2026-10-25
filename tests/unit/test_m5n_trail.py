"""The D1 trailing distance a candidate fixes at signal time (N4b): ``floor(10000 x 3 x ATR(20) / close)``
clamped to ``[10, 2000]``.

The arithmetic tests hand the function an ATR it did not compute, by replacing ``atr`` with a series
whose last value is a literal, so each expected figure is worked here from two literals and the
function's own indicator is not on the path. A second group runs the real indicator over frames of
constant range, where the ATR is the range up to float rounding, with a margin that rounding cannot
cross. The last group drives the six registered candidates through ``generate_signal`` and pins that
each signal carries the distance and each class declares the exit.
"""

from __future__ import annotations

import math
from datetime import timedelta
from decimal import Decimal

import pandas as pd
import pytest

import trading_bot.strategies.m5n  # noqa: F401  (registers the six candidates)
from trading_bot.core.models import Candle
from trading_bot.strategies import registry
from trading_bot.strategies.base import BaseStrategy
from trading_bot.strategies.m5n import trail
from trading_bot.strategies.m5n.base import M5nStrategy
from trading_bot.strategies.m5n.trail import TrailClamp, TrailDelta, trail_delta
from trading_bot.strategies.registry import create_strategy

SIX = (
    "donchian_1d_20",
    "donchian_1d_55",
    "sma_cross_1d_50_200",
    "donchian_4h_20",
    "keltner_4h_20_2",
    "tsmom_1d_90",
)


def constant_range(rows: int, close: float, width: float) -> pd.DataFrame:
    """Bars that close where they started and span ``width``, so every true range is ``width``."""
    closes = [close] * rows
    return pd.DataFrame(
        {
            "open": closes,
            "high": [close + width / 2] * rows,
            "low": [close - width / 2] * rows,
            "close": closes,
        }
    )


def with_atr(monkeypatch: pytest.MonkeyPatch, value: float, rows: int = 40) -> pd.DataFrame:
    """A frame whose indicator is replaced so the last ATR is exactly ``value``."""
    series = pd.Series([math.nan] * (rows - 1) + [value], dtype="float64")
    monkeypatch.setattr(trail, "atr", lambda high, low, close, period: series)
    return constant_range(rows, 100.0, 1.0)


class TestTheArithmetic:
    def test_it_is_ten_thousand_times_three_atr_over_the_close(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        frame = with_atr(monkeypatch, 0.5)
        assert trail_delta(frame, Decimal("300")) == TrailDelta(50, TrailClamp.NONE)

    def test_it_rounds_down(self, monkeypatch: pytest.MonkeyPatch) -> None:
        frame = with_atr(monkeypatch, 0.1)
        assert trail_delta(frame, Decimal("7")) == TrailDelta(428, TrailClamp.NONE)

    def test_it_floors_and_does_not_round_to_nearest(self, monkeypatch: pytest.MonkeyPatch) -> None:
        frame = with_atr(monkeypatch, 0.1)
        assert trail_delta(frame, Decimal("6.5")) == TrailDelta(461, TrailClamp.NONE)

    def test_it_uses_the_close_it_is_given(self, monkeypatch: pytest.MonkeyPatch) -> None:
        frame = with_atr(monkeypatch, 3.0)
        at_100 = trail_delta(frame, Decimal("100"))
        at_150 = trail_delta(frame, Decimal("150"))
        assert at_100 is not None and at_150 is not None
        assert (at_100.bps, at_150.bps) == (900, 600)

    def test_the_upper_bound_is_not_a_clamp(self, monkeypatch: pytest.MonkeyPatch) -> None:
        frame = with_atr(monkeypatch, 2.0)
        assert trail_delta(frame, Decimal("30")) == TrailDelta(2000, TrailClamp.NONE)

    def test_above_the_upper_bound_clamps_to_it(self, monkeypatch: pytest.MonkeyPatch) -> None:
        frame = with_atr(monkeypatch, 2.0)
        assert trail_delta(frame, Decimal("29")) == TrailDelta(2000, TrailClamp.UPPER)

    def test_the_lower_bound_is_not_a_clamp(self, monkeypatch: pytest.MonkeyPatch) -> None:
        frame = with_atr(monkeypatch, 0.01)
        assert trail_delta(frame, Decimal("30")) == TrailDelta(10, TrailClamp.NONE)

    def test_below_the_lower_bound_clamps_to_it(self, monkeypatch: pytest.MonkeyPatch) -> None:
        frame = with_atr(monkeypatch, 0.01)
        assert trail_delta(frame, Decimal("31")) == TrailDelta(10, TrailClamp.LOWER)

    def test_a_zero_atr_clamps_to_the_lower_bound(self, monkeypatch: pytest.MonkeyPatch) -> None:
        frame = with_atr(monkeypatch, 0.0)
        assert trail_delta(frame, Decimal("100")) == TrailDelta(10, TrailClamp.LOWER)

    def test_the_result_is_a_plain_int(self, monkeypatch: pytest.MonkeyPatch) -> None:
        frame = with_atr(monkeypatch, 0.5)
        found = trail_delta(frame, Decimal("300"))
        assert found is not None
        assert type(found.bps) is int


class TestWhatItRefuses:
    def test_a_nan_atr_is_no_distance(self, monkeypatch: pytest.MonkeyPatch) -> None:
        frame = with_atr(monkeypatch, math.nan)
        assert trail_delta(frame, Decimal("100")) is None

    def test_an_infinite_atr_is_no_distance(self, monkeypatch: pytest.MonkeyPatch) -> None:
        frame = with_atr(monkeypatch, math.inf)
        assert trail_delta(frame, Decimal("100")) is None

    def test_twenty_rows_cannot_form_an_atr_of_twenty(self) -> None:
        assert trail_delta(constant_range(20, 100.0, 2.0), Decimal("100")) is None

    def test_twenty_one_rows_can(self) -> None:
        found = trail_delta(constant_range(21, 100.0, 2.0), Decimal("101"))
        assert found is not None

    @pytest.mark.parametrize("bad", ["0", "-1"])
    def test_a_close_that_is_not_positive_is_refused(self, bad: str) -> None:
        with pytest.raises(ValueError, match="close must be positive"):
            trail_delta(constant_range(30, 100.0, 2.0), Decimal(bad))


class TestTheRealIndicator:
    def test_a_constant_range_gives_that_range(self) -> None:
        found = trail_delta(constant_range(60, 100.0, 2.0), Decimal("101"))
        assert found == TrailDelta(594, TrailClamp.NONE)

    def test_a_wide_range_clamps_high(self) -> None:
        found = trail_delta(constant_range(60, 100.0, 10.0), Decimal("100"))
        assert found == TrailDelta(2000, TrailClamp.UPPER)

    def test_a_narrow_range_clamps_low(self) -> None:
        found = trail_delta(constant_range(60, 1000.0, 0.01), Decimal("1000"))
        assert found == TrailDelta(10, TrailClamp.LOWER)

    def test_the_input_frame_is_not_changed(self) -> None:
        frame = constant_range(60, 100.0, 2.0)
        before = frame.copy()
        trail_delta(frame, Decimal("101"))
        pd.testing.assert_frame_equal(frame, before)


def decision_frame(timeframe: str, closes: list[float], width: float = 1.0) -> pd.DataFrame:
    freq = {"4h": "4h", "1d": "1D"}[timeframe]
    index = pd.date_range("2023-01-01", periods=len(closes), freq=freq, tz="UTC")
    index.name = "open_time"
    return pd.DataFrame(
        {
            "open": closes,
            "high": [c + width / 2 for c in closes],
            "low": [c - width / 2 for c in closes],
            "close": closes,
            "volume": 1.0,
        },
        index=index,
    )


def candle_of(frame: pd.DataFrame, timeframe: str) -> Candle:
    step = {"4h": timedelta(hours=4), "1d": timedelta(days=1)}[timeframe]
    opened = frame.index[-1].to_pydatetime()
    row = frame.iloc[-1]
    return Candle(
        symbol="BTCUSDT",
        timeframe=timeframe,
        open_time=opened,
        close_time=opened + step - timedelta(milliseconds=1),
        open=str(row["close"]),
        high=str(row["high"]),
        low=str(row["low"]),
        close=str(row["close"]),
        volume="1",
    )


class TestTheSignalCarriesIt:
    def test_a_donchian_breakout_carries_the_distance_of_its_own_frame(self) -> None:
        closes = [100.0] * 30 + [110.0]
        frame = decision_frame("1d", closes)
        strategy = create_strategy("donchian_1d_20")
        signal = strategy.generate_signal("BTCUSDT", frame, last_candle=candle_of(frame, "1d"))
        assert signal is not None
        expected = trail_delta(frame, Decimal("110.0"))
        assert expected is not None
        assert signal.metadata["trail_delta_bps"] == expected.bps
        assert signal.metadata["trail_clamp"] == expected.clamp.value
        assert type(signal.metadata["trail_delta_bps"]) is int

    def test_the_distance_is_taken_from_the_signal_bars_close(self) -> None:
        closes = [100.0] * 30 + [110.0]
        frame = decision_frame("1d", closes)
        signal = create_strategy("donchian_1d_20").generate_signal(
            "BTCUSDT", frame, last_candle=candle_of(frame, "1d")
        )
        assert signal is not None
        run = frame
        last_atr = float(trail.atr(run["high"], run["low"], run["close"], 20).iloc[-1])
        assert signal.metadata["trail_delta_bps"] == int(10000 * 3 * last_atr / 110.0)

    def test_the_gap_free_run_feeds_the_atr_and_not_the_rows_before_a_gap(self) -> None:
        wide = decision_frame("4h", [100.0] * 30, width=20.0)
        quiet = decision_frame("4h", [100.0] * 30 + [101.0], width=1.0)
        quiet.index = pd.date_range(
            wide.index[-1].to_pydatetime() + timedelta(hours=8),
            periods=len(quiet),
            freq="4h",
            tz="UTC",
            name="open_time",
        )
        joined = pd.concat([wide, quiet])
        signal = create_strategy("donchian_4h_20").generate_signal(
            "BTCUSDT", joined, last_candle=candle_of(joined, "4h")
        )
        assert signal is not None
        assert signal.metadata["trail_delta_bps"] < 1000

    def test_a_signal_without_a_distance_is_no_signal(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import trading_bot.strategies.m5n.base as base_module

        monkeypatch.setattr(base_module, "trail_delta", lambda run, close: None)
        frame = decision_frame("1d", [100.0] * 30 + [110.0])
        strategy = create_strategy("donchian_1d_20")
        assert (
            strategy.generate_signal("BTCUSDT", frame, last_candle=candle_of(frame, "1d")) is None
        )


class TestEveryCandidateCanFormTheDistance:
    @pytest.mark.parametrize("name", SIX)
    def test_its_window_holds_enough_rows_for_the_atr(self, name: str) -> None:
        strategy = create_strategy(name)
        assert isinstance(strategy, M5nStrategy)
        assert strategy.warmup_period >= trail.TRAIL_ATR_PERIOD + 1


class TestTheDeclaration:
    @pytest.mark.parametrize("name", SIX)
    def test_each_m5n_candidate_declares_the_d1_exit(self, name: str) -> None:
        assert create_strategy(name).declares_d1_exit is True

    def test_the_base_class_does_not(self) -> None:
        assert BaseStrategy.declares_d1_exit is False

    def test_no_other_registered_strategy_declares_it(self) -> None:
        others = [n for n in registry.available_strategies() if n not in SIX]
        assert others
        for name in others:
            assert create_strategy(name).declares_d1_exit is False, name

    def test_the_metadata_keys_are_the_ones_the_executor_reads(self) -> None:
        assert trail.TRAIL_DELTA_KEY == "trail_delta_bps"
        assert trail.TRAIL_CLAMP_KEY == "trail_clamp"
