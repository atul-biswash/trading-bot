"""Tests for the shipped strategies: SMA crossover and RSI mean reversion.

No network, no real time. Frames are hand-built to the exact shape
``BufferedMarketDataProvider.get_dataframe`` produces -- ``float64`` OHLCV on a
tz-aware UTC ``DatetimeIndex`` named ``open_time`` -- so a strategy that passes
here cannot be relying on a shape the live provider does not hand it.

Signals are collected by replaying a series one bar at a time
(:func:`scan_signals`), feeding each prefix as if it were the buffer at that
moment. That is what makes "fires exactly once" a real assertion rather than a
claim: a level-triggered implementation would re-emit on every subsequent bar of
the same condition and the counts would blow up.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from datetime import timedelta
from decimal import Decimal
from typing import Any

import numpy as np
import pandas as pd
import pytest

from tests.unit.test_live_engine import FakeMarketDataProvider
from trading_bot.config.models import DataConfig
from trading_bot.core.enums import SignalAction
from trading_bot.core.exceptions import DataError, StrategyConfigError
from trading_bot.core.interfaces import Strategy
from trading_bot.core.models import Candle, Signal
from trading_bot.engine.live_engine import TradingEngine
from trading_bot.indicators import rsi, sma
from trading_bot.strategies.base import BaseStrategy
from trading_bot.strategies.examples.rsi_strategy import RsiStrategy
from trading_bot.strategies.examples.sma_crossover import SmaCrossoverStrategy
from trading_bot.strategies.registry import create_strategy, register_strategy

_SYMBOL = "BTCUSDT"
_TIMEFRAME = "1m"
_BAR = timedelta(minutes=1)


# --------------------------------------------------------------------------
# Fixtures: frames and candles shaped exactly like the live provider's
# --------------------------------------------------------------------------
def make_frame(closes: Sequence[float]) -> pd.DataFrame:
    """An OHLCV frame whose every column tracks ``closes``.

    Open/high/low mirror the close because none of the M2 strategies reads
    them; giving them distinct values would imply a dependency that does not
    exist. ``float64`` and the tz-aware ``open_time`` index are not incidental
    -- they are the provider's documented output contract.
    """
    index = pd.date_range(
        "2024-01-01", periods=len(closes), freq="1min", tz="UTC", name="open_time"
    )
    values = np.asarray(closes, dtype=np.float64)
    return pd.DataFrame(
        {
            "open": values,
            "high": values,
            "low": values,
            "close": values,
            "volume": np.ones(len(values), dtype=np.float64),
        },
        index=index,
    )


def make_candle(frame: pd.DataFrame, index: int = -1) -> Candle:
    """The frame's bar at ``index``, rebuilt with ``Decimal`` prices.

    Prices are formatted to eight decimal places, which is how Binance sends
    them on the wire and what ``ws_kline_to_candle`` parses. The trailing zeros
    matter to :func:`test_signal_price_is_the_candles_decimal_not_a_float`:
    ``Decimal("100.00000000")`` and a float round-trip of it compare ``==`` but
    do not share a string form, so the exponent is what exposes a float that
    sneaked into the domain.
    """
    open_time = frame.index[index].to_pydatetime()
    price = Decimal(f"{frame['close'].iloc[index]:.8f}")
    return Candle(
        symbol=_SYMBOL,
        timeframe=_TIMEFRAME,
        open_time=open_time,
        close_time=open_time + _BAR - timedelta(milliseconds=1),
        open=price,
        high=price,
        low=price,
        close=price,
        volume=Decimal("1.00000000"),
    )


def scan_signals(strategy: Strategy, closes: Sequence[float]) -> list[tuple[int, Signal]]:
    """Replay ``closes`` bar by bar, returning ``(bar_index, signal)`` for each hit.

    Each iteration hands the strategy the prefix ending at that bar, which is
    exactly what the engine does on bar close, and the candle for that same bar.
    """
    frame = make_frame(closes)
    hits: list[tuple[int, Signal]] = []
    for position in range(len(closes)):
        window = frame.iloc[: position + 1]
        signal = strategy.generate_signal(_SYMBOL, window, last_candle=make_candle(window))
        if signal is not None:
            hits.append((position, signal))
    return hits


# Flat, then a rally that pulls the fast SMA above the slow one and holds it
# there for nine bars, then a sell-off that pulls it back below and holds. The
# sustained stretches are the point: a level-triggered strategy would fire on
# every one of them.
# fmt: off
SMA_CLOSES: tuple[float, ...] = (
    100.0, 100.0, 100.0, 100.0, 100.0, 100.0, 100.0, 100.0,   # 0-7   flat
    101.0, 103.0, 106.0, 110.0, 115.0, 121.0,                 # 8-13  rally
    122.0, 122.0, 122.0,                                      # 14-16 plateau
    118.0, 112.0, 105.0,  97.0,  90.0,  84.0,                 # 17-22 sell-off
     83.0,  83.0,  83.0,                                      # 23-25 floor
)
# fmt: on
SMA_GOLDEN_CROSS_BAR = 8
SMA_DEATH_CROSS_BAR = 17

# Flat (RSI pinned at 50), then a relentless sell-off, then a relentless rally.
# RSI stays under 30 for seven bars and over 70 for five, so both thresholds get
# a long sustained region in which a second signal must not appear.
# fmt: off
RSI_CLOSES: tuple[float, ...] = (
    100.0, 100.0, 100.0, 100.0, 100.0, 100.0, 100.0, 100.0,   # 0-7   flat
     97.0,  94.0,  91.0,  88.0,  85.0,  82.0,  79.0,          # 8-14  sell-off
     82.0,  86.0,  91.0,  97.0, 104.0, 112.0, 121.0, 131.0,   # 15-22 rally
)
# fmt: on
RSI_PERIOD = 5
RSI_OVERSOLD_BAR = 8
RSI_OVERBOUGHT_BAR = 18


def sma_strategy() -> SmaCrossoverStrategy:
    return SmaCrossoverStrategy(fast_period=3, slow_period=5)


def rsi_strategy() -> RsiStrategy:
    return RsiStrategy(period=RSI_PERIOD)


# --------------------------------------------------------------------------
# SMA crossover: what fires, when, and how often
# --------------------------------------------------------------------------
def test_sma_emits_one_buy_on_the_golden_cross_and_one_close_on_the_death_cross() -> None:
    hits = scan_signals(sma_strategy(), SMA_CLOSES)

    assert [(bar, signal.action) for bar, signal in hits] == [
        (SMA_GOLDEN_CROSS_BAR, SignalAction.BUY),
        (SMA_DEATH_CROSS_BAR, SignalAction.CLOSE),
    ]


def test_sma_stays_silent_while_the_crossed_condition_persists() -> None:
    """Edge-triggered, not level-triggered.

    Bars 9-16 all have fast > slow and bars 18-25 all have fast < slow. Emitting
    on those would place a duplicate order every bar once execution lands.
    """
    fired_on = {bar for bar, _ in scan_signals(sma_strategy(), SMA_CLOSES)}

    assert fired_on.isdisjoint(range(SMA_GOLDEN_CROSS_BAR + 1, SMA_DEATH_CROSS_BAR))
    assert fired_on.isdisjoint(range(SMA_DEATH_CROSS_BAR + 1, len(SMA_CLOSES)))


def test_sma_is_silent_throughout_the_warmup_region() -> None:
    strategy = sma_strategy()
    hits = scan_signals(strategy, SMA_CLOSES)

    assert all(bar + 1 >= strategy.warmup_period for bar, _ in hits)


def test_sma_exit_is_close_never_sell() -> None:
    """Spot has no short side; ``SELL`` would mean "open one"."""
    actions = {signal.action for _, signal in scan_signals(sma_strategy(), SMA_CLOSES)}

    assert actions <= {SignalAction.BUY, SignalAction.CLOSE}
    assert SignalAction.SELL not in actions


def test_sma_flat_market_produces_nothing() -> None:
    assert scan_signals(sma_strategy(), [100.0] * 40) == []


def test_sma_warmup_period_is_derived_from_the_indicator_nan_contract() -> None:
    """Two consecutive non-NaN slow-SMA values, counted from the indicator itself.

    Deliberately not a hardcoded ``51``: if ``sma``'s warmup ever changes, this
    recomputes and the strategy's constant is caught rather than rubber-stamped.
    """
    strategy = SmaCrossoverStrategy(fast_period=3, slow_period=5)
    slow = sma(pd.Series(np.arange(1.0, 41.0)), strategy.slow_period)

    first_valid = slow.first_valid_index()
    assert first_valid is not None
    assert strategy.warmup_period == first_valid + 2


@pytest.mark.parametrize(
    ("fast", "slow"),
    [
        (0, 50),  # fast below 1
        (20, 0),  # slow below 1
        (-1, 50),  # negative
        (50, 50),  # equal periods: the two SMAs would be the same series
        (60, 50),  # inverted
    ],
)
def test_sma_rejects_bad_periods_at_construction(fast: int, slow: int) -> None:
    with pytest.raises(ValueError):
        SmaCrossoverStrategy(fast_period=fast, slow_period=slow)


# --------------------------------------------------------------------------
# RSI: what fires, when, and how often
# --------------------------------------------------------------------------
def test_rsi_emits_buy_crossing_into_oversold_and_close_crossing_into_overbought() -> None:
    hits = scan_signals(rsi_strategy(), RSI_CLOSES)

    assert [(bar, signal.action) for bar, signal in hits] == [
        (RSI_OVERSOLD_BAR, SignalAction.BUY),
        (RSI_OVERBOUGHT_BAR, SignalAction.CLOSE),
    ]


def test_rsi_stays_silent_while_it_remains_past_the_threshold() -> None:
    """The trigger is the crossing, not the state of being past the threshold."""
    fired_on = {bar for bar, _ in scan_signals(rsi_strategy(), RSI_CLOSES)}

    assert fired_on.isdisjoint(range(RSI_OVERSOLD_BAR + 1, RSI_OVERBOUGHT_BAR))
    assert fired_on.isdisjoint(range(RSI_OVERBOUGHT_BAR + 1, len(RSI_CLOSES)))


def test_rsi_is_silent_throughout_the_warmup_region() -> None:
    strategy = rsi_strategy()
    hits = scan_signals(strategy, RSI_CLOSES)

    assert all(bar + 1 >= strategy.warmup_period for bar, _ in hits)


def test_rsi_exit_is_close_never_sell() -> None:
    actions = {signal.action for _, signal in scan_signals(rsi_strategy(), RSI_CLOSES)}

    assert actions <= {SignalAction.BUY, SignalAction.CLOSE}
    assert SignalAction.SELL not in actions


def test_rsi_flat_market_produces_nothing() -> None:
    """A flat series gives RSI exactly 50.0, which crosses neither threshold.

    This is the test that pins the indicator layer's flat-window convention to
    a behaviour anyone can see. Had RSI returned 100 on a flat window, the first
    bar of a dead market would have looked like a screaming exit signal.
    """
    closes = [100.0] * 40
    assert scan_signals(rsi_strategy(), closes) == []
    assert float(rsi(pd.Series(closes), RSI_PERIOD).iloc[-1]) == 50.0


def test_rsi_warmup_period_is_derived_from_the_indicator_nan_contract() -> None:
    """Two consecutive non-NaN RSI values -- one more bar than a level test needs."""
    strategy = RsiStrategy(period=RSI_PERIOD)
    values = rsi(pd.Series(np.arange(1.0, 41.0)), strategy.period)

    first_valid = values.first_valid_index()
    assert first_valid is not None
    assert strategy.warmup_period == first_valid + 2
    # A level test ("is RSI below 30 right now?") needs only the one value.
    assert strategy.warmup_period == first_valid + 1 + 1


@pytest.mark.parametrize(
    ("period", "oversold", "overbought"),
    [
        (0, 30.0, 70.0),  # period below 1
        (14, -1.0, 70.0),  # oversold below the range
        (14, 30.0, 101.0),  # overbought above the range
        (14, 70.0, 30.0),  # inverted
        (14, 50.0, 50.0),  # equal
        (14, 0.0, 70.0),  # RSI saturates at 0: unreachable, silently inert
        (14, 30.0, 100.0),  # RSI saturates at 100: likewise
    ],
)
def test_rsi_rejects_bad_parameters_at_construction(
    period: int, oversold: float, overbought: float
) -> None:
    with pytest.raises(ValueError):
        RsiStrategy(period=period, oversold=oversold, overbought=overbought)


# --------------------------------------------------------------------------
# The Decimal boundary
# --------------------------------------------------------------------------
@pytest.mark.parametrize("strategy_closes", [("sma", SMA_CLOSES), ("rsi", RSI_CLOSES)])
def test_signal_price_is_the_candles_decimal_not_a_float(
    strategy_closes: tuple[str, Sequence[float]],
) -> None:
    """Prices must be *copied* from the candle, never rebuilt from the frame.

    Comparing with ``==`` is not enough -- ``Decimal("100.00000000")`` equals
    ``Decimal("100.0")``. The string form carries the exponent, so it is what
    catches a value that has been through ``float`` and back. Pydantic will not
    catch it: it coerces a float to ``Decimal`` without complaint.
    """
    name, closes = strategy_closes
    strategy = sma_strategy() if name == "sma" else rsi_strategy()
    frame = make_frame(closes)

    hits = scan_signals(strategy, closes)
    assert hits, "fixture produced no signals"

    for bar, signal in hits:
        expected = make_candle(frame.iloc[: bar + 1]).close
        assert signal.price == expected
        assert str(signal.price) == str(expected)  # exponent intact => never a float
        # ...and the check above has teeth: a float round-trip *is* visible in
        # the string form, even though `==` would happily call the two equal.
        round_tripped = Decimal(str(float(expected)))
        assert round_tripped == expected
        assert str(round_tripped) != str(expected)


@pytest.mark.parametrize("strategy_closes", [("sma", SMA_CLOSES), ("rsi", RSI_CLOSES)])
def test_signal_timestamp_is_the_bar_close_not_wall_clock(
    strategy_closes: tuple[str, Sequence[float]],
) -> None:
    """Otherwise every backtested signal would be stamped with today's date."""
    name, closes = strategy_closes
    strategy = sma_strategy() if name == "sma" else rsi_strategy()
    frame = make_frame(closes)

    for bar, signal in scan_signals(strategy, closes):
        assert signal.timestamp == make_candle(frame.iloc[: bar + 1]).close_time
        assert signal.timestamp.year == 2024


# --------------------------------------------------------------------------
# Signal payload
# --------------------------------------------------------------------------
@pytest.mark.parametrize("strategy_closes", [("sma", SMA_CLOSES), ("rsi", RSI_CLOSES)])
def test_signals_carry_the_symbol_and_a_specific_reason(
    strategy_closes: tuple[str, Sequence[float]],
) -> None:
    """``reason`` is what the engine writes to the log; it has to say something."""
    name, closes = strategy_closes
    strategy = sma_strategy() if name == "sma" else rsi_strategy()

    hits = scan_signals(strategy, closes)
    assert hits

    for _, signal in hits:
        assert signal.symbol == _SYMBOL
        assert len(signal.reason) > 20
        assert any(char.isdigit() for char in signal.reason)  # carries the numbers
        assert signal.strength == 1.0  # no fabricated confidence


@pytest.mark.parametrize("strategy_closes", [("sma", SMA_CLOSES), ("rsi", RSI_CLOSES)])
def test_metadata_is_plain_python_and_survives_serialisation(
    strategy_closes: tuple[str, Sequence[float]],
) -> None:
    """Phase 8 persists this. NumPy scalars in it would be a problem there.

    ``np.float64`` happens to be a ``float`` subclass and so slips through
    ``json.dumps``, but ``np.int64`` does not, and either would repr as
    ``np.float64(1.5)`` in a log line. Coercing at the boundary is cheaper than
    finding out later.
    """
    name, closes = strategy_closes
    strategy = sma_strategy() if name == "sma" else rsi_strategy()

    hits = scan_signals(strategy, closes)
    assert hits

    for _, signal in hits:
        assert signal.metadata["strategy"] == strategy.name
        for key, value in signal.metadata.items():
            assert type(value) in (int, float, str), f"{key} is {type(value)!r}"
        json.dumps(signal.metadata)


def test_rsi_metadata_reports_distance_past_the_threshold() -> None:
    """Exposed as diagnostics, deliberately *not* as ``strength``.

    On the crossing bar this number is near zero by construction; shipping it as
    ``strength`` would invite a later phase to size real entries to nothing.
    """
    hits = dict(scan_signals(rsi_strategy(), RSI_CLOSES))

    buy = hits[RSI_OVERSOLD_BAR]
    assert buy.metadata["threshold_kind"] == "oversold"
    assert 0.0 < float(buy.metadata["threshold_distance"]) <= 1.0  # type: ignore[arg-type]

    close = hits[RSI_OVERBOUGHT_BAR]
    assert close.metadata["threshold_kind"] == "overbought"
    assert 0.0 < float(close.metadata["threshold_distance"]) <= 1.0  # type: ignore[arg-type]


# --------------------------------------------------------------------------
# Robustness
# --------------------------------------------------------------------------
@pytest.mark.parametrize("factory", [sma_strategy, rsi_strategy])
def test_short_series_returns_none_rather_than_raising(factory: Any) -> None:
    """Insufficient data is not an error.

    Raising would count toward the engine's quarantine budget and permanently
    disable a pair whose only problem was that it had not warmed up yet.
    """
    strategy = factory()
    frame = make_frame([100.0, 101.0])

    assert strategy.generate_signal(_SYMBOL, frame, last_candle=make_candle(frame)) is None


@pytest.mark.parametrize("factory", [sma_strategy, rsi_strategy])
def test_strategies_do_not_mutate_the_frame(factory: Any) -> None:
    strategy = factory()
    frame = make_frame(SMA_CLOSES)
    before = frame.copy(deep=True)

    strategy.generate_signal(_SYMBOL, frame, last_candle=make_candle(frame))

    pd.testing.assert_frame_equal(frame, before)


@pytest.mark.parametrize("factory", [sma_strategy, rsi_strategy])
def test_missing_close_column_raises_a_named_data_error(factory: Any) -> None:
    """A bare ``KeyError`` in the engine log would be far harder to diagnose."""
    strategy = factory()
    frame = make_frame(SMA_CLOSES)
    candle = make_candle(frame)

    with pytest.raises(DataError, match="close"):
        strategy.generate_signal(_SYMBOL, frame.drop(columns=["close"]), last_candle=candle)


# --------------------------------------------------------------------------
# Registry and configuration wiring
# --------------------------------------------------------------------------
def test_registry_builds_both_strategies_with_params() -> None:
    crossover = create_strategy("sma_crossover", fast_period=3, slow_period=5)
    mean_reversion = create_strategy("rsi", period=7, oversold=25.0, overbought=75.0)

    assert isinstance(crossover, SmaCrossoverStrategy)
    assert crossover.warmup_period == 6
    assert isinstance(mean_reversion, RsiStrategy)
    assert mean_reversion.warmup_period == 9

    frame = make_frame(SMA_CLOSES)
    candle = make_candle(frame)
    assert crossover.generate_signal(_SYMBOL, frame, last_candle=candle) is None
    assert mean_reversion.generate_signal(_SYMBOL, frame, last_candle=candle) is None


def test_registry_names_the_accepted_parameters_on_a_config_typo() -> None:
    """A typo used to surface as a bare TypeError naming neither strategy nor field."""
    with pytest.raises(StrategyConfigError) as caught:
        create_strategy("sma_crossover", fast_perio=20, slow_period=50)

    message = str(caught.value)
    assert "sma_crossover" in message
    assert "fast_perio" in message
    assert "fast_period, slow_period" in message  # tells you what it wanted


def test_a_typeerror_from_inside_a_constructor_is_not_mislabelled() -> None:
    """Binding the signature first keeps a real bug distinguishable from a typo."""

    @register_strategy("_exploding_for_test")
    class Exploding(BaseStrategy):
        def __init__(self, period: int = 1) -> None:
            super().__init__(period=period)
            raise TypeError("a genuine bug inside the constructor")

        def generate_signal(
            self, symbol: str, candles: pd.DataFrame, *, last_candle: Candle
        ) -> Signal | None:  # pragma: no cover - never reached
            return None

    with pytest.raises(TypeError) as caught:
        create_strategy("_exploding_for_test", period=2)
    assert not isinstance(caught.value, StrategyConfigError)
    assert "genuine bug" in str(caught.value)


def test_default_warmups_fit_the_default_history_limit() -> None:
    """Otherwise the engine warns at startup and the pair waits hours to trade."""
    history_limit = DataConfig().history_limit

    assert SmaCrossoverStrategy().warmup_period == 51 <= history_limit
    assert RsiStrategy().warmup_period == 16 <= history_limit


# --------------------------------------------------------------------------
# End to end through the engine
# --------------------------------------------------------------------------
async def test_real_signal_reaches_a_signal_handler_through_the_engine() -> None:
    """The whole M2 point: a shipped strategy driving the real engine seam.

    The frame is advanced one bar between emissions, which is what the live
    provider does, so this also proves edge-triggering survives the round trip
    -- the golden cross arrives once even though the condition holds afterwards.
    """
    key = (_SYMBOL, _TIMEFRAME)
    strategy = sma_strategy()
    provider = FakeMarketDataProvider({key: 500})
    engine = TradingEngine(provider, {key: strategy}, max_strategy_errors=2)

    received: list[Signal] = []

    async def collect(signal: Signal, candle: Candle) -> None:
        received.append(signal)

    engine.on_signal(collect)
    await engine.start()

    frame = make_frame(SMA_CLOSES)
    for position in range(len(SMA_CLOSES)):
        window = frame.iloc[: position + 1]
        provider.frames[key] = window
        await provider.emit(make_candle(window))

    assert [signal.action for signal in received] == [SignalAction.BUY, SignalAction.CLOSE]
    assert received[0].symbol == _SYMBOL
    assert received[0].price == make_candle(frame.iloc[: SMA_GOLDEN_CROSS_BAR + 1]).close
    assert "golden cross" in received[0].reason
    # Every bar was still evaluated: nothing was quarantined.
    assert len(provider.dataframe_calls) == len(SMA_CLOSES)
