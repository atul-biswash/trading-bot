"""R-BS (M5m P113 C5): the trend filter on the two shipped strategies -- an entry only while the close is above its SMA.

``trend_filter_period`` is an optional strategy parameter. ``None`` (the default) is the strategy as it was, bit
for bit; a period makes a ``BUY`` conditional on the bar's close being STRICTLY above its SMA of that period, and
changes nothing else: ``CLOSE`` is never filtered, the signal's price and timestamp are still the candle's, and
the warmup grows to cover the filter. The frames, candles and replay helper are ``test_strategies.py``'s (imported,
as ``test_modes.py`` imports ``test_risk_manager.py``'s fixtures: an import-time break there fails this file too).
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from decimal import Decimal
from pathlib import Path

import pytest

from tests.unit.backtest_world import make_settings
from tests.unit.protocol_world import PROTOCOL, effective
from tests.unit.test_strategies import (
    RSI_CLOSES,
    RSI_OVERSOLD_BAR,
    SMA_CLOSES,
    SMA_DEATH_CROSS_BAR,
    SMA_GOLDEN_CROSS_BAR,
    make_candle,
    make_frame,
    scan_signals,
)
from trading_bot.backtesting.candidate import candidate_digest
from trading_bot.backtesting.overrides import apply_overrides, build_overrides
from trading_bot.backtesting.protocol import grid_point
from trading_bot.core.enums import SignalAction
from trading_bot.core.exceptions import ConfigError
from trading_bot.indicators import sma
from trading_bot.strategies.examples.rsi_strategy import RsiStrategy
from trading_bot.strategies.examples.sma_crossover import SmaCrossoverStrategy
from trading_bot.strategies.helpers import trend_allows_entry, validate_trend_filter_period
from trading_bot.strategies.registry import create_strategy


def sma_with(period: int | None) -> SmaCrossoverStrategy:
    return SmaCrossoverStrategy(fast_period=3, slow_period=5, trend_filter_period=period)


def rsi_with(period: int | None) -> RsiStrategy:
    return RsiStrategy(period=5, trend_filter_period=period)


def actions(hits: Sequence[tuple[int, object]]) -> list[tuple[int, object]]:
    return [(bar, getattr(signal, "action", None)) for bar, signal in hits]


# A long climb and a short sharp dip: after the dip the close is far above its long SMA and below its short one.
DIP_CLOSES: tuple[float, ...] = (
    *(100.0 + 1.5 * i for i in range(70)),
    203.0,
    197.0,
    191.0,
    185.0,
    179.0,
    173.0,
)


# A plateau, a collapse to a floor, then a small bounce: fast(3) crosses above slow(5) on the first bounce bar while
# the close (101) is far below its 20-bar SMA (about 145), which the plateau still dominates.
BOUNCE_CLOSES: tuple[float, ...] = (*([200.0] * 12), *([100.0] * 10), 101.0, 104.0, 108.0)
BOUNCE_BAR = 22


class TestTheHelper:
    def test_a_close_above_its_sma_allows_the_entry_and_returns_the_sma(self) -> None:
        close = make_frame([1.0, 2.0, 3.0, 4.0, 10.0])["close"]
        allowed, average = trend_allows_entry(close, 4)
        assert allowed is True
        assert average == float(sma(close, 4).iloc[-1]) == 4.75

    def test_a_close_below_its_sma_does_not(self) -> None:
        close = make_frame([10.0, 10.0, 10.0, 1.0])["close"]
        assert trend_allows_entry(close, 4) == (False, 7.75)

    def test_a_close_equal_to_its_sma_does_not_because_above_is_strict(self) -> None:
        close = make_frame([100.0] * 10)["close"]
        assert trend_allows_entry(close, 10) == (False, 100.0)

    def test_fewer_bars_than_the_period_is_unmeasurable_not_an_error(self) -> None:
        close = make_frame([1.0, 2.0, 3.0])["close"]
        assert trend_allows_entry(close, 4) == (False, None)

    def test_a_nan_close_is_unmeasurable(self) -> None:
        close = make_frame([1.0, 2.0, 3.0, float("nan")])["close"]
        assert trend_allows_entry(close, 3) == (False, None)

    def test_the_numbers_are_plain_floats(self) -> None:
        close = make_frame([1.0, 2.0, 3.0, 4.0])["close"]
        allowed, average = trend_allows_entry(close, 3)
        assert type(allowed) is bool and type(average) is float

    @pytest.mark.parametrize("period", [None, 2, 200])
    def test_a_valid_period_is_returned_as_given(self, period: int | None) -> None:
        assert validate_trend_filter_period(period) == period

    @pytest.mark.parametrize(
        "period",
        [0, 1, -5, 200.0, True, "200", [200]],
        ids=["zero", "one", "negative", "float", "bool", "text", "list"],
    )
    def test_anything_else_is_refused(self, period: object) -> None:
        with pytest.raises(ValueError, match="trend_filter_period"):
            validate_trend_filter_period(period)


class TestTheCrossoverFilter:
    def test_no_filter_is_the_strategy_as_it_was(self) -> None:
        hits = scan_signals(sma_with(None), SMA_CLOSES)
        assert actions(hits) == [
            (SMA_GOLDEN_CROSS_BAR, SignalAction.BUY),
            (SMA_DEATH_CROSS_BAR, SignalAction.CLOSE),
        ]
        for _, signal in hits:
            assert "trend_sma" not in signal.metadata
            assert "trend_filter_period" not in signal.metadata

    def test_a_cross_above_the_trend_is_a_buy_that_says_so(self) -> None:
        hits = scan_signals(sma_with(8), SMA_CLOSES)
        buys = [(bar, s) for bar, s in hits if s.action is SignalAction.BUY]
        assert [bar for bar, _ in buys] == [SMA_GOLDEN_CROSS_BAR]
        signal = buys[0][1]
        expected = float(
            sma(make_frame(SMA_CLOSES[: SMA_GOLDEN_CROSS_BAR + 1])["close"], 8).iloc[-1]
        )
        assert signal.metadata["trend_filter_period"] == 8
        assert signal.metadata["trend_sma"] == expected
        assert "close above SMA(8)" in signal.reason

    def test_a_cross_below_the_trend_is_no_entry(self) -> None:
        unfiltered = [
            bar
            for bar, s in scan_signals(sma_with(None), BOUNCE_CLOSES)
            if s.action is SignalAction.BUY
        ]
        assert unfiltered == [BOUNCE_BAR], "the fixture must hold exactly the golden cross refused"
        close = make_frame(BOUNCE_CLOSES[: BOUNCE_BAR + 1])["close"]
        assert trend_allows_entry(close, 20)[0] is False
        assert (BOUNCE_BAR, SignalAction.BUY) not in actions(
            scan_signals(sma_with(20), BOUNCE_CLOSES)
        )

    def test_a_cross_that_the_trend_refuses_is_not_taken_later_when_the_trend_turns(self) -> None:
        hits = scan_signals(sma_with(20), BOUNCE_CLOSES)
        assert [s for _, s in hits if s.action is SignalAction.BUY] == []

    def test_the_death_cross_is_a_close_whatever_the_trend_says(self) -> None:
        closes = [
            bar
            for bar, s in scan_signals(sma_with(None), BOUNCE_CLOSES)
            if s.action is SignalAction.CLOSE
        ]
        assert closes, "the fixture must hold a death cross"
        for bar in closes:
            frame = make_frame(BOUNCE_CLOSES[: bar + 1])
            assert (
                trend_allows_entry(frame["close"], 8)[0] is False
            )  # an entry here would be refused
        for period in (
            8,
            20,
            200,
        ):  # a measurable trend, a barely measurable one, and one never measurable
            filtered = [
                bar
                for bar, s in scan_signals(sma_with(period), BOUNCE_CLOSES)
                if s.action is SignalAction.CLOSE
            ]
            assert filtered == closes

    def test_a_trend_not_yet_measurable_allows_no_entry(self) -> None:
        # the golden cross is at bar 8, i.e. 9 bars; a 12-bar trend is not measurable there
        hits = scan_signals(sma_with(12), SMA_CLOSES)
        assert (SMA_GOLDEN_CROSS_BAR, SignalAction.BUY) not in actions(hits)

    def test_the_warmup_is_the_larger_of_the_crossover_and_the_filter(self) -> None:
        assert sma_with(None).warmup_period == 6
        assert sma_with(3).warmup_period == 6
        assert sma_with(6).warmup_period == 6
        assert sma_with(8).warmup_period == 8
        assert sma_with(200).warmup_period == 200

    def test_the_price_and_timestamp_are_still_the_candles(self) -> None:
        frame = make_frame(SMA_CLOSES[: SMA_GOLDEN_CROSS_BAR + 1])
        candle = make_candle(frame)
        signal = sma_with(8).generate_signal("BTCUSDT", frame, last_candle=candle)
        assert signal is not None
        assert signal.price == candle.close and type(signal.price) is Decimal
        assert signal.timestamp == candle.close_time

    def test_the_frame_is_not_mutated(self) -> None:
        frame = make_frame(SMA_CLOSES[: SMA_GOLDEN_CROSS_BAR + 1])
        before = frame.copy()
        sma_with(8).generate_signal("BTCUSDT", frame, last_candle=make_candle(frame))
        assert frame.equals(before)

    def test_the_metadata_survives_serialisation(self) -> None:
        for _, signal in scan_signals(sma_with(8), SMA_CLOSES):
            assert json.loads(json.dumps(signal.metadata)) == signal.metadata

    @pytest.mark.parametrize("period", [0, 1, 6.0, True])
    def test_a_bad_period_is_refused_at_construction(self, period: object) -> None:
        with pytest.raises(ValueError, match="trend_filter_period"):
            SmaCrossoverStrategy(fast_period=3, slow_period=5, trend_filter_period=period)  # type: ignore[arg-type]

    def test_the_registry_builds_it_from_a_config_parameter(self) -> None:
        strategy = create_strategy(
            "sma_crossover", fast_period=3, slow_period=5, trend_filter_period=8
        )
        assert isinstance(strategy, SmaCrossoverStrategy)
        assert strategy.trend_filter_period == 8
        assert strategy.params["trend_filter_period"] == 8

    def test_without_the_parameter_the_recorded_params_are_unchanged(self) -> None:
        assert "trend_filter_period" not in sma_with(None).params


class TestTheRsiFilter:
    def test_no_filter_is_the_strategy_as_it_was(self) -> None:
        hits = scan_signals(rsi_with(None), RSI_CLOSES)
        assert (RSI_OVERSOLD_BAR, SignalAction.BUY) in actions(hits)
        for _, signal in hits:
            assert "trend_sma" not in signal.metadata

    def test_an_oversold_crossing_below_the_trend_is_no_entry(self) -> None:
        # RSI_CLOSES sells off from a flat 100: at the crossing the close is below its 8-bar SMA
        close = make_frame(RSI_CLOSES[: RSI_OVERSOLD_BAR + 1])["close"]
        assert trend_allows_entry(close, 8)[0] is False
        hits = scan_signals(rsi_with(8), RSI_CLOSES)
        assert (RSI_OVERSOLD_BAR, SignalAction.BUY) not in actions(hits)

    def test_an_oversold_dip_inside_an_uptrend_is_an_entry_and_says_so(self) -> None:
        unfiltered = [
            (bar, s)
            for bar, s in scan_signals(rsi_with(None), DIP_CLOSES)
            if s.action is SignalAction.BUY
        ]
        assert unfiltered, "the fixture must contain an oversold crossing"
        bar, _ = unfiltered[0]
        filtered = [
            (b, s)
            for b, s in scan_signals(rsi_with(50), DIP_CLOSES)
            if s.action is SignalAction.BUY
        ]
        assert [b for b, _ in filtered] == [bar]
        signal = filtered[0][1]
        assert signal.metadata["trend_filter_period"] == 50
        assert signal.metadata["trend_sma"] == float(
            sma(make_frame(DIP_CLOSES[: bar + 1])["close"], 50).iloc[-1]
        )

    def test_the_same_dip_is_refused_by_a_trend_it_has_already_fallen_through(self) -> None:
        unfiltered = [
            (bar, s)
            for bar, s in scan_signals(rsi_with(None), DIP_CLOSES)
            if s.action is SignalAction.BUY
        ]
        bar, _ = unfiltered[0]
        close = make_frame(DIP_CLOSES[: bar + 1])["close"]
        assert trend_allows_entry(close, 5)[0] is False
        assert not [
            s for _, s in scan_signals(rsi_with(5), DIP_CLOSES) if s.action is SignalAction.BUY
        ]

    def test_the_overbought_crossing_is_a_close_whatever_the_trend_says(self) -> None:
        plain = [
            (b, s.action)
            for b, s in scan_signals(rsi_with(None), RSI_CLOSES)
            if s.action is SignalAction.CLOSE
        ]
        assert plain, "the fixture must contain an overbought crossing"
        filtered = [
            (b, s.action)
            for b, s in scan_signals(rsi_with(200), RSI_CLOSES)
            if s.action is SignalAction.CLOSE
        ]
        assert filtered == plain

    def test_the_warmup_is_the_larger_of_the_crossing_and_the_filter(self) -> None:
        assert rsi_with(None).warmup_period == 7
        assert rsi_with(5).warmup_period == 7
        assert rsi_with(50).warmup_period == 50

    def test_the_frame_is_not_mutated(self) -> None:
        frame = make_frame(DIP_CLOSES)
        before = frame.copy()
        rsi_with(50).generate_signal("BTCUSDT", frame, last_candle=make_candle(frame))
        assert frame.equals(before)

    @pytest.mark.parametrize("period", [0, 1, 50.0, True])
    def test_a_bad_period_is_refused_at_construction(self, period: object) -> None:
        with pytest.raises(ValueError, match="trend_filter_period"):
            RsiStrategy(period=5, trend_filter_period=period)  # type: ignore[arg-type]

    def test_the_registry_builds_it_and_without_it_the_params_are_unchanged(self) -> None:
        strategy = create_strategy("rsi", period=5, trend_filter_period=50)
        assert isinstance(strategy, RsiStrategy) and strategy.trend_filter_period == 50
        assert "trend_filter_period" not in rsi_with(None).params


class TestTheProtocolAndTheCommandAgree:
    """The filter the research protocol declares is the parameter these strategies take."""

    def test_every_one_of_the_216_declared_variants_builds(self) -> None:
        built = 0
        for variant in PROTOCOL.variants():
            params = {name: json.loads(value) for name, value in variant.params.items()}
            strategy = create_strategy(variant.family, **params)
            assert (getattr(strategy, "trend_filter_period", None) is not None) == variant.filtered
            built += 1
        assert built == 216

    def test_the_declared_filter_is_the_parameter_name_and_value_the_strategies_take(self) -> None:
        assert PROTOCOL.filter_param == "trend_filter_period"
        assert json.loads(PROTOCOL.filter_value) == 200
        assert create_strategy("rsi", trend_filter_period=200).warmup_period == 200

    def test_the_filter_makes_a_different_candidate(self) -> None:
        plain = effective(params={"fast_period": 20, "slow_period": 100})
        filtered = effective(
            params={"fast_period": 20, "slow_period": 100, "trend_filter_period": 200}
        )
        assert candidate_digest(plain) != candidate_digest(filtered)
        variant = grid_point(PROTOCOL, filtered)
        assert variant is not None and variant.filtered is True
        plain_variant = grid_point(PROTOCOL, plain)
        assert plain_variant is not None and plain_variant.filtered is False

    def test_the_command_line_takes_it_as_an_integer_and_refuses_a_float(
        self, tmp_path: Path
    ) -> None:
        config = make_settings(tmp_path, tmp_path / "hist").config
        got = apply_overrides(config, build_overrides(params=["trend_filter_period=200"]))
        assert got.strategy.params["trend_filter_period"] == 200
        with pytest.raises(ConfigError, match="cannot be built"):
            apply_overrides(config, build_overrides(params=["trend_filter_period=200.0"]))
