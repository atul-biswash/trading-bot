"""Tests for the feed watchdog (P-3l, C45): silence, event-loop lag, slow handler chains.

No real time: the watchdog reads an injected monotonic clock and sleeps on an
injected sleep, so every threshold is crossed by assignment. Records are selected
by logger name and event and never by position.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from tests.unit.test_live_engine import FakeMarketDataProvider, ScriptedStrategy
from trading_bot.core.models import Candle
from trading_bot.data.watchdog import FeedWatchdog
from trading_bot.engine.live_engine import TradingEngine

_LOGGER = "trading_bot.data.watchdog"
_BTC = ("BTCUSDT", "1m")
_ETH = ("ETHUSDT", "5m")
_OPEN = datetime(2026, 10, 2, 12, 0, tzinfo=timezone.utc)


class Clock:
    """A monotonic clock the test moves by hand."""

    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


def bar(symbol: str = "BTCUSDT", timeframe: str = "1m") -> Candle:
    return Candle(
        symbol=symbol,
        timeframe=timeframe,
        open_time=_OPEN,
        close_time=_OPEN + timedelta(minutes=1),
        open=Decimal("100"),
        high=Decimal("101"),
        low=Decimal("99"),
        close=Decimal("100"),
        volume=Decimal("1"),
    )


def lines(caplog: pytest.LogCaptureFixture, event: str) -> list[logging.LogRecord]:
    return [
        record
        for record in caplog.records
        if record.name == _LOGGER and vars(record).get("event") == event
    ]


def armed(*pairs: tuple[str, str]) -> tuple[FeedWatchdog, Clock]:
    clock = Clock()
    watchdog = FeedWatchdog(clock=clock)
    watchdog.arm(pairs or (_BTC,))
    return watchdog, clock


def test_a_silent_pair_warns_at_one_and_a_half_bars_then_goes_critical_at_five(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """1m: 90 s warns, 300 s is CRITICAL, and each is logged once however often it looks.

    MUTATIONS: the warn threshold moved to 3 bars -- nothing at 90 s and this
    fails; the critical threshold moved to 10 bars -- nothing at 300 s and this
    fails.
    """
    watchdog, clock = armed()
    with caplog.at_level(logging.INFO, logger=_LOGGER):
        clock.now = 89.9
        watchdog.check()
        assert lines(caplog, "feed_silent") == []
        clock.now = 90.0
        watchdog.check()
        clock.now = 150.0
        watchdog.check()
        watchdog.check()
        assert len(lines(caplog, "feed_silent")) == 1
        assert lines(caplog, "feed_silent_critical") == []
        clock.now = 299.9
        watchdog.check()
        assert lines(caplog, "feed_silent_critical") == []
        clock.now = 300.0
        watchdog.check()
        clock.now = 900.0
        watchdog.check()

    assert len(lines(caplog, "feed_silent")) == 1
    critical = lines(caplog, "feed_silent_critical")
    assert len(critical) == 1
    assert critical[0].levelno == logging.CRITICAL
    assert vars(critical[0]).get("symbol") == "BTCUSDT"
    assert vars(critical[0]).get("silent_s") == 300.0
    assert lines(caplog, "feed_silent")[0].levelno == logging.WARNING


def test_a_bar_clears_the_episode_and_logs_how_long_it_lasted(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """The first bar after a silence says the feed is back, with the gap it measured.

    The episode resets: a second silence warns again. MUTATION: no recovery line --
    nothing is logged on the bar and this fails.
    """
    watchdog, clock = armed()
    with caplog.at_level(logging.INFO, logger=_LOGGER):
        clock.now = 350.0
        watchdog.check()
        watchdog.on_chain(bar(), 350.0, 350.2)
        watchdog.check()
        resumed = lines(caplog, "feed_resumed")
        assert len(resumed) == 1
        assert vars(resumed[0]).get("gap_s") == 350.0
        assert resumed[0].levelno == logging.INFO
        clock.now = 350.0 + 90.0
        watchdog.check()

    assert len(lines(caplog, "feed_silent_critical")) == 1
    assert len(lines(caplog, "feed_silent")) == 1  # the 350 s check went straight critical
    assert vars(lines(caplog, "feed_silent")[0]).get("silent_s") == 90.0


def test_a_bar_that_arrives_on_time_logs_nothing(caplog: pytest.LogCaptureFixture) -> None:
    """No episode, no recovery line: a healthy feed leaves the watchdog silent."""
    watchdog, clock = armed()
    with caplog.at_level(logging.INFO, logger=_LOGGER):
        for minute in range(1, 6):
            clock.now = minute * 60.0
            watchdog.check()
            watchdog.on_chain(bar(), clock.now, clock.now + 0.1)

    assert [r for r in caplog.records if r.name == _LOGGER] == []


def test_each_pair_is_judged_by_its_own_timeframe(caplog: pytest.LogCaptureFixture) -> None:
    """100 s is silent for a 1m pair and perfectly normal for a 5m one."""
    watchdog, clock = armed(_BTC, _ETH)
    with caplog.at_level(logging.INFO, logger=_LOGGER):
        clock.now = 100.0
        watchdog.check()

    silent = lines(caplog, "feed_silent")
    assert [vars(r).get("symbol") for r in silent] == ["BTCUSDT"]


def test_a_late_tick_warns_once_and_recovers(caplog: pytest.LogCaptureFixture) -> None:
    """Event-loop lag over 5 s warns once per episode; an on-time tick ends it.

    MUTATION: the lag threshold set to 50 s -- 5.1 s no longer warns and this fails.
    """
    watchdog, _clock = armed()
    with caplog.at_level(logging.INFO, logger=_LOGGER):
        watchdog.observe_tick(5.0)
        assert lines(caplog, "event_loop_lagging") == []
        watchdog.observe_tick(5.1)
        watchdog.observe_tick(9.0)
        assert len(lines(caplog, "event_loop_lagging")) == 1
        watchdog.observe_tick(0.2)
        watchdog.observe_tick(0.1)
        assert len(lines(caplog, "event_loop_recovered")) == 1
        watchdog.observe_tick(7.0)

    assert len(lines(caplog, "event_loop_lagging")) == 2
    assert vars(lines(caplog, "event_loop_lagging")[0]).get("lag_s") == 5.1


async def test_the_loop_measures_lag_and_runs_the_checks(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """``_run`` sleeps one tick, reads the clock and reports how late it woke.

    The fake sleep advances the clock by the tick plus 6 s on its second call, so
    the loop sees a 6 s lag, and by then the pair has crossed 1.5 bars, so the
    same iteration's ``check`` warns.
    """
    clock = Clock()
    calls: list[float] = []

    async def sleep(delay: float) -> None:
        calls.append(delay)
        clock.now += delay + (95.0 if len(calls) == 2 else 0.0)
        if len(calls) == 3:
            raise asyncio.CancelledError

    watchdog = FeedWatchdog(clock=clock, sleep=sleep)
    watchdog.arm([_BTC])
    with caplog.at_level(logging.INFO, logger=_LOGGER), pytest.raises(asyncio.CancelledError):
        await watchdog._run()

    assert calls == [1.0, 1.0, 1.0]
    assert len(lines(caplog, "event_loop_lagging")) == 1
    assert vars(lines(caplog, "event_loop_lagging")[0]).get("lag_s") == 95.0
    assert len(lines(caplog, "feed_silent")) == 1


def test_a_slow_handler_chain_warns_once_and_recovers(caplog: pytest.LogCaptureFixture) -> None:
    """Over half a bar (30 s on 1m) warns once; a chain back under it says so.

    MUTATION: the limit set to a whole bar -- 30.1 s no longer warns and this fails.
    """
    watchdog, clock = armed()
    with caplog.at_level(logging.INFO, logger=_LOGGER):
        clock.now = 60.0
        watchdog.on_chain(bar(), 60.0, 90.0)
        assert lines(caplog, "handler_chain_slow") == []
        clock.now = 120.0
        watchdog.on_chain(bar(), 120.0, 150.1)
        watchdog.on_chain(bar(), 180.0, 220.0)
        assert len(lines(caplog, "handler_chain_slow")) == 1
        watchdog.on_chain(bar(), 240.0, 250.0)

    assert len(lines(caplog, "handler_chain_recovered")) == 1
    slow = lines(caplog, "handler_chain_slow")[0]
    assert vars(slow).get("chain_s") == 30.1
    assert vars(slow).get("limit_s") == 30.0
    assert slow.levelno == logging.WARNING


def test_a_slow_chain_uses_the_pairs_own_bar(caplog: pytest.LogCaptureFixture) -> None:
    """40 s is slow for a 1m bar and nothing for a 5m one (limit 150 s)."""
    watchdog, _clock = armed(_BTC, _ETH)
    with caplog.at_level(logging.INFO, logger=_LOGGER):
        watchdog.on_chain(bar("ETHUSDT", "5m"), 0.0, 40.0)

    assert lines(caplog, "handler_chain_slow") == []


def test_a_bar_for_an_unwatched_pair_is_ignored(caplog: pytest.LogCaptureFixture) -> None:
    watchdog, _clock = armed()
    with caplog.at_level(logging.INFO, logger=_LOGGER):
        watchdog.on_chain(bar("SOLUSDT", "1m"), 0.0, 99.0)

    assert [r for r in caplog.records if r.name == _LOGGER] == []
    assert watchdog.last_arrival("SOLUSDT", "1m") is None


def test_the_thresholds_must_be_ordered() -> None:
    with pytest.raises(ValueError, match="warn_factor"):
        FeedWatchdog(warn_factor=5.0, critical_factor=1.5)


async def test_the_engine_arms_starts_and_stops_the_watchdog() -> None:
    """The watchdog is torn down with the engine, and stopping twice is safe."""
    watchdog = FeedWatchdog()
    provider = FakeMarketDataProvider({_BTC: 100})
    engine = TradingEngine(provider, {_BTC: ScriptedStrategy()}, watchdog=watchdog)

    await engine.start()
    assert watchdog.running
    assert watchdog.watched == [_BTC]
    assert engine.watchdog is watchdog

    await engine.stop()
    assert not watchdog.running
    await engine.stop()
    await watchdog.stop()


async def test_an_engine_without_a_watchdog_starts_and_stops_as_before() -> None:
    provider = FakeMarketDataProvider({_BTC: 100})
    engine = TradingEngine(provider, {_BTC: ScriptedStrategy()})

    await engine.start()
    await engine.stop()

    assert engine.watchdog is None
