"""Tests for :class:`BinanceMarketDataStream` using a scripted fake socket.

No network and no real time: the Binance socket is replaced by a
``FakeSocketSource`` that yields scripted messages (and can inject the
max-reconnect error sentinel or raise), and the backoff ``sleep``/``random_fn``
are injected so reconnection is deterministic. Assertions cover subscription
routing, closed-vs-forming filtering, multiplex-envelope handling, capped
exponential backoff with jitter, counter reset after a good message,
infinite-vs-bounded retry semantics, and per-handler exception isolation.
"""

from __future__ import annotations

import asyncio
from decimal import Decimal
from random import Random
from typing import Any

import pytest

from trading_bot.core.models import Candle
from trading_bot.exchange.websocket_client import BinanceMarketDataStream


# --------------------------------------------------------------------------
# Recorded WebSocket payloads (single-letter kline codes; "x" is finality)
# --------------------------------------------------------------------------
# The "k" object keeps the wire's single-letter keys rather than being built from
# named fields: the mapper under test is what translates them, so a fixture that
# already spelled them out would be testing the translation with itself. Grouped
# by meaning, one concern per row --
# t/T: start & close time · s/i: symbol & interval · o/c/h/l: OHLC ·
# v: base volume · n: trade count · x: finality.
# fmt: off
def _kline_event(*, close: str, is_closed: bool, symbol: str = "BTCUSDT",
                 interval: str = "1m") -> dict[str, Any]:
    return {
        "e": "kline",
        "E": 1_700_000_060_001,
        "s": symbol,
        "k": {
            "t": 1_700_000_000_000, "T": 1_700_000_059_999,
            "s": symbol, "i": interval,
            "o": "65000.00", "c": close, "h": "65100.00", "l": "64950.00",
            "v": "12.50000000", "n": 100, "x": is_closed,
        },
    }
# fmt: on


BTC_CLOSED = _kline_event(close="65050.00", is_closed=True)
BTC_CLOSED_2 = _kline_event(close="65075.00", is_closed=True)
BTC_FORMING = _kline_event(close="65010.00", is_closed=False)
ETH_CLOSED = _kline_event(close="3500.00", is_closed=True, symbol="ETHUSDT")
# The same closed event as delivered by a combined (multiplex) stream.
BTC_COMBINED = {"stream": "btcusdt@kline_1m", "data": BTC_CLOSED}
# The sentinel ReconnectingWebsocket pushes once it exhausts its own reconnects.
ERROR_SENTINEL = {
    "e": "error", "type": "BinanceWebsocketUnableToConnect", "m": "max reconnects",
}
# A non-kline control frame (e.g. a subscription ack) that must be ignored.
NON_KLINE = {"result": None, "id": 1}


# --------------------------------------------------------------------------
# Scripted fakes
# --------------------------------------------------------------------------
class FakeSocket:
    """An async-context-manager socket that replays scripted ``recv`` actions.

    Each action is either a ``dict`` (returned from ``recv``) or a
    ``BaseException`` (raised from ``recv``). When the script is exhausted it
    either parks forever (``park_when_empty=True``, for lifecycle tests driven
    via start/stop) or raises to surface a test-scripting mistake.
    """

    def __init__(self, actions: list[Any], *, park_when_empty: bool = False) -> None:
        self._actions = list(actions)
        self._park = park_when_empty
        self.entered = 0
        self.exited = 0

    async def __aenter__(self) -> FakeSocket:
        self.entered += 1
        return self

    async def __aexit__(self, exc_type: object, exc: object, tb: object) -> bool:
        self.exited += 1
        return False

    async def recv(self) -> dict[str, Any]:
        if not self._actions:
            if self._park:
                await asyncio.Event().wait()  # until the task is cancelled
            raise AssertionError("recv() called with no scripted actions left")
        action = self._actions.pop(0)
        if isinstance(action, BaseException):
            raise action
        return action


class FakeSocketSource:
    """Hands out scripted sockets and records how it was driven."""

    def __init__(self, sockets: list[FakeSocket]) -> None:
        self._sockets = list(sockets)
        self.multiplex_calls: list[list[str]] = []
        self.aclose_calls = 0

    def multiplex(self, streams: list[str]) -> FakeSocket:
        self.multiplex_calls.append(list(streams))
        if not self._sockets:
            raise AssertionError("multiplex() called with no scripted sockets left")
        return self._sockets.pop(0)

    async def aclose(self) -> None:
        self.aclose_calls += 1


def _raising_socket(exc: BaseException) -> FakeSocket:
    return FakeSocket([exc])


def _recording_sleep(recorded: list[float]):
    async def sleep(delay: float) -> None:
        recorded.append(delay)

    return sleep


def _stopping_sleep(holder: list[Any], recorded: list[float], stop_after: int):
    """A sleep that records delays and stops the stream after ``stop_after``."""

    async def sleep(delay: float) -> None:
        recorded.append(delay)
        if len(recorded) >= stop_after:
            holder[0]._running = False

    return sleep


def _make(source: FakeSocketSource, **kwargs: Any) -> BinanceMarketDataStream:
    kwargs.setdefault("sleep", _recording_sleep([]))
    kwargs.setdefault("random_fn", lambda: 1.0)  # equal-jitter -> full ceiling
    return BinanceMarketDataStream(source, **kwargs)


# --------------------------------------------------------------------------
# Construction / validation
# --------------------------------------------------------------------------
def test_rejects_backoff_max_below_base() -> None:
    with pytest.raises(ValueError):
        BinanceMarketDataStream(FakeSocketSource([]), backoff_base_s=10, backoff_max_s=5)


def test_rejects_negative_max_retries() -> None:
    with pytest.raises(ValueError):
        BinanceMarketDataStream(FakeSocketSource([]), max_retries=-1)


# --------------------------------------------------------------------------
# Subscription / stream names
# --------------------------------------------------------------------------
def test_subscribe_uppercases_symbol_and_builds_lowercase_stream_name() -> None:
    stream = _make(FakeSocketSource([]))
    stream.subscribe("btcusdt", "1m", _null_handler)
    stream.subscribe("EthUsdt", "5m", _null_handler)
    assert stream.stream_names == ["btcusdt@kline_1m", "ethusdt@kline_5m"]


def test_subscribe_dedupes_stream_names() -> None:
    stream = _make(FakeSocketSource([]))
    stream.subscribe("BTCUSDT", "1m", _null_handler)
    stream.subscribe("BTCUSDT", "1m", _null_handler)  # same key, second handler
    assert stream.stream_names == ["btcusdt@kline_1m"]


async def test_start_without_subscription_raises() -> None:
    stream = _make(FakeSocketSource([]))
    with pytest.raises(ValueError):
        await stream.start()


async def test_start_is_idempotent() -> None:
    source = FakeSocketSource([FakeSocket([BTC_FORMING], park_when_empty=True)])
    stream = _make(source)
    stream.subscribe("BTCUSDT", "1m", _null_handler)
    try:
        await stream.start()
        first_task = stream._task
        await asyncio.sleep(0)  # let the task connect (one multiplex call)
        await stream.start()  # no-op: same task, no second socket opened
        assert stream._task is first_task
    finally:
        await stream.stop()
    assert source.multiplex_calls == [["btcusdt@kline_1m"]]


# --------------------------------------------------------------------------
# Dispatch (driven through the public start/stop lifecycle)
# --------------------------------------------------------------------------
async def _null_handler(_candle: Candle) -> None:
    return None


async def _drain(source: FakeSocketSource, subscriptions, script, *, expected):
    """Start a stream over ``script`` and return the candles it dispatches.

    ``expected`` is how many handler calls to await before stopping; the socket
    parks after the script so ``stop`` cleanly cancels it.
    """
    received: list[Candle] = []
    done = asyncio.Event()

    async def handler(candle: Candle) -> None:
        received.append(candle)
        if len(received) >= expected:
            done.set()

    stream = _make(source)
    for symbol, timeframe in subscriptions:
        stream.subscribe(symbol, timeframe, handler)
    await stream.start()
    try:
        await asyncio.wait_for(done.wait(), timeout=2.0)
    finally:
        await stream.stop()
    return received, stream


async def test_only_closed_candles_reach_handlers() -> None:
    source = FakeSocketSource(
        [FakeSocket([BTC_FORMING, BTC_CLOSED], park_when_empty=True)]
    )
    received, _ = await _drain(source, [("BTCUSDT", "1m")], None, expected=1)
    assert [c.is_closed for c in received] == [True]
    assert received[0].close == Decimal("65050.00")  # the forming bar was dropped


async def test_multiplex_envelope_is_unwrapped() -> None:
    source = FakeSocketSource([FakeSocket([BTC_COMBINED], park_when_empty=True)])
    received, _ = await _drain(source, [("BTCUSDT", "1m")], None, expected=1)
    assert received[0].symbol == "BTCUSDT"
    assert received[0].close == Decimal("65050.00")


async def test_non_kline_messages_are_ignored() -> None:
    source = FakeSocketSource(
        [FakeSocket([NON_KLINE, BTC_CLOSED], park_when_empty=True)]
    )
    received, _ = await _drain(source, [("BTCUSDT", "1m")], None, expected=1)
    assert len(received) == 1  # the control frame did not crash or reconnect
    assert received[0].close == Decimal("65050.00")


async def test_routes_candles_by_symbol_and_timeframe() -> None:
    btc: list[Candle] = []
    eth: list[Candle] = []
    done = asyncio.Event()

    async def on_btc(c: Candle) -> None:
        btc.append(c)
        if btc and eth:
            done.set()

    async def on_eth(c: Candle) -> None:
        eth.append(c)
        if btc and eth:
            done.set()

    source = FakeSocketSource(
        [FakeSocket([BTC_CLOSED, ETH_CLOSED], park_when_empty=True)]
    )
    stream = _make(source)
    stream.subscribe("BTCUSDT", "1m", on_btc)
    stream.subscribe("ETHUSDT", "1m", on_eth)
    await stream.start()
    try:
        await asyncio.wait_for(done.wait(), timeout=2.0)
    finally:
        await stream.stop()

    assert [c.symbol for c in btc] == ["BTCUSDT"]
    assert [c.symbol for c in eth] == ["ETHUSDT"]


async def test_a_failing_handler_does_not_stop_the_feed() -> None:
    good: list[Candle] = []
    done = asyncio.Event()

    async def bad(_c: Candle) -> None:
        raise RuntimeError("boom")

    async def good_handler(c: Candle) -> None:
        good.append(c)
        if len(good) >= 2:
            done.set()

    source = FakeSocketSource(
        [FakeSocket([BTC_CLOSED, BTC_CLOSED_2], park_when_empty=True)]
    )
    stream = _make(source)
    stream.subscribe("BTCUSDT", "1m", bad)          # raises every time
    stream.subscribe("BTCUSDT", "1m", good_handler)  # must still receive both
    await stream.start()
    try:
        await asyncio.wait_for(done.wait(), timeout=2.0)
    finally:
        await stream.stop()

    assert [c.close for c in good] == [Decimal("65050.00"), Decimal("65075.00")]
    assert source.multiplex_calls == [["btcusdt@kline_1m"]]  # no reconnect happened


# --------------------------------------------------------------------------
# Reconnection / backoff (driving _run directly for determinism)
# --------------------------------------------------------------------------
async def test_capped_exponential_backoff_sequence() -> None:
    recorded: list[float] = []
    holder: list[Any] = [None]
    source = FakeSocketSource([_raising_socket(ConnectionError("down")) for _ in range(6)])
    stream = BinanceMarketDataStream(
        source, backoff_base_s=1.0, backoff_max_s=5.0, max_retries=None,
        sleep=_stopping_sleep(holder, recorded, stop_after=6), random_fn=lambda: 1.0,
    )
    holder[0] = stream
    stream.subscribe("BTCUSDT", "1m", _null_handler)
    stream._running = True
    await stream._run()

    # base*2**n capped at 5: 1, 2, 4, 5, 5, 5 (full ceiling because r == 1.0).
    assert recorded == [1.0, 2.0, 4.0, 5.0, 5.0, 5.0]
    assert len(source.multiplex_calls) == 6  # a fresh socket per reconnect


async def test_counter_resets_after_a_good_message() -> None:
    recorded: list[float] = []
    holder: list[Any] = [None]
    received: list[Candle] = []

    async def handler(c: Candle) -> None:
        received.append(c)

    source = FakeSocketSource([
        _raising_socket(ConnectionError("down")),   # attempt 0 -> 1.0
        _raising_socket(ConnectionError("down")),   # attempt 1 -> 2.0
        _raising_socket(ConnectionError("down")),   # attempt 2 -> 4.0
        FakeSocket([BTC_CLOSED, ERROR_SENTINEL]),   # good msg resets, then drop
    ])
    stream = BinanceMarketDataStream(
        source, backoff_base_s=1.0, backoff_max_s=60.0, max_retries=None,
        sleep=_stopping_sleep(holder, recorded, stop_after=4), random_fn=lambda: 1.0,
    )
    holder[0] = stream
    stream.subscribe("BTCUSDT", "1m", handler)
    stream._running = True
    await stream._run()

    # The 4th delay is back to 1.0 (base), proving the counter reset on the
    # good candle rather than continuing 1, 2, 4, 8.
    assert recorded == [1.0, 2.0, 4.0, 1.0]
    assert [c.close for c in received] == [Decimal("65050.00")]


async def test_error_sentinel_triggers_a_fresh_socket() -> None:
    recorded: list[float] = []
    holder: list[Any] = [None]
    received: list[Candle] = []

    async def handler(c: Candle) -> None:
        received.append(c)
        holder[0]._running = False  # stop once we prove the reconnect delivered

    source = FakeSocketSource([
        FakeSocket([ERROR_SENTINEL]),  # library gave up -> reconnect
        FakeSocket([BTC_CLOSED]),      # fresh socket delivers a candle
    ])
    stream = BinanceMarketDataStream(
        source, backoff_base_s=1.0, backoff_max_s=60.0, max_retries=None,
        sleep=_recording_sleep(recorded), random_fn=lambda: 1.0,
    )
    holder[0] = stream
    stream.subscribe("BTCUSDT", "1m", handler)
    stream._running = True
    await stream._run()

    assert recorded == [1.0]                    # exactly one backoff for the drop
    assert len(source.multiplex_calls) == 2     # a fresh socket after the sentinel
    assert [c.close for c in received] == [Decimal("65050.00")]


async def test_zero_max_retries_reconnects_indefinitely() -> None:
    recorded: list[float] = []
    holder: list[Any] = [None]
    source = FakeSocketSource(
        [_raising_socket(ConnectionError("down")) for _ in range(20)]
    )
    stream = BinanceMarketDataStream(
        source, backoff_base_s=1.0, backoff_max_s=5.0, max_retries=0,  # 0 == infinite
        sleep=_stopping_sleep(holder, recorded, stop_after=20), random_fn=lambda: 1.0,
    )
    holder[0] = stream
    stream.subscribe("BTCUSDT", "1m", _null_handler)
    stream._running = True
    await stream._run()  # returns because our sleep stopped it, not a give-up

    assert len(source.multiplex_calls) == 20  # kept reconnecting past any finite cap


async def test_bounded_max_retries_gives_up_and_raises() -> None:
    recorded: list[float] = []
    source = FakeSocketSource(
        [_raising_socket(ConnectionError("down")) for _ in range(3)]
    )
    stream = BinanceMarketDataStream(
        source, backoff_base_s=1.0, backoff_max_s=5.0, max_retries=2,
        sleep=_recording_sleep(recorded), random_fn=lambda: 1.0,
    )
    stream.subscribe("BTCUSDT", "1m", _null_handler)
    stream._running = True
    with pytest.raises(ConnectionError):
        await stream._run()

    assert len(recorded) == 2              # backed off twice, then gave up
    assert len(source.multiplex_calls) == 3


def test_backoff_delay_applies_equal_jitter_and_caps() -> None:
    floor = BinanceMarketDataStream(
        FakeSocketSource([]), backoff_base_s=4.0, backoff_max_s=10.0,
        random_fn=lambda: 0.0,
    )
    full = BinanceMarketDataStream(
        FakeSocketSource([]), backoff_base_s=4.0, backoff_max_s=10.0,
        random_fn=lambda: 1.0,
    )
    assert floor._backoff_delay(0) == 2.0   # ceiling(4) * 0.5
    assert full._backoff_delay(0) == 4.0    # ceiling(4) * 1.0
    assert full._backoff_delay(1) == 8.0    # ceiling(8)
    assert full._backoff_delay(2) == 10.0   # min(10, 16) capped

    rng = Random(0)
    jittered = BinanceMarketDataStream(
        FakeSocketSource([]), backoff_base_s=1.0, backoff_max_s=5.0,
        random_fn=rng.random,
    )
    for attempt in range(8):
        ceiling = min(5.0, 1.0 * 2**attempt)
        delay = jittered._backoff_delay(attempt)
        assert ceiling * 0.5 <= delay <= ceiling


# --------------------------------------------------------------------------
# stop() lifecycle
# --------------------------------------------------------------------------
async def test_stop_without_start_closes_the_source() -> None:
    source = FakeSocketSource([])
    stream = _make(source)
    await stream.stop()  # must not raise even though start() was never called
    assert source.aclose_calls == 1


async def test_stop_cancels_the_task_and_closes_the_source() -> None:
    socket = FakeSocket([BTC_FORMING], park_when_empty=True)
    source = FakeSocketSource([socket])
    stream = _make(source)
    stream.subscribe("BTCUSDT", "1m", _null_handler)
    await stream.start()
    await asyncio.sleep(0)  # let the task connect and park
    await stream.stop()

    assert stream._task is None
    assert socket.entered == 1 and socket.exited == 1  # opened then cleanly closed
    assert source.aclose_calls == 1
