"""Binance market-data WebSocket stream.

Implements :class:`trading_bot.core.interfaces.MarketDataStream`: subscribes to
kline streams, emits **closed** :class:`~trading_bot.core.models.Candle` objects
to registered handlers, and stays connected 24/7 by rebuilding the socket after
any drop.

Why an outer reconnection loop
------------------------------
``python-binance``'s :class:`ReconnectingWebsocket` reconnects on its own, but
only up to ``MAX_RECONNECTS`` (5) attempts; once exhausted it pushes an error
*sentinel* (``{"e": "error", "type": "BinanceWebsocketUnableToConnect", ...}``)
onto its queue and stops — ``recv()`` returns the sentinel rather than raising,
and any further ``recv()`` raises ``ReadLoopClosed``. A long outage would
therefore silently kill a naive feed. :class:`BinanceMarketDataStream` wraps the
socket in its own loop: on the sentinel (or any error) it tears the socket down,
backs off, and opens a **fresh** socket — which resets the library's internal
attempt counter, giving effectively unbounded reconnection.

Testability seam
----------------
The Binance socket is reached only through the :class:`KlineSocketSource` /
:class:`KlineSocket` Protocols, so unit tests drive the whole reconnect/dispatch
loop with a scripted fake and an injected ``sleep`` — no network, no real time.
The real :class:`ReconnectingWebsocket` satisfies :class:`KlineSocket`
structurally (it is an async context manager exposing ``recv``).
"""

from __future__ import annotations

import asyncio
import contextlib
import random
from collections.abc import Callable
from typing import TYPE_CHECKING, Any, Protocol

from trading_bot.core.enums import TradingMode
from trading_bot.core.interfaces import CandleHandler, MarketDataStream
from trading_bot.exchange.base import SleepFn
from trading_bot.exchange.models import unwrap_stream_message, ws_kline_to_candle
from trading_bot.utils.logger import get_logger

if TYPE_CHECKING:  # pragma: no cover - typing only
    from trading_bot.config.settings import Settings

_log = get_logger(__name__)

# Wire-level event markers on a stream message.
_WS_EVENT_TYPE = "e"
_WS_EVENT_KLINE = "kline"
# The sentinel ReconnectingWebsocket emits once it exhausts its own reconnects.
_WS_EVENT_ERROR = "error"

# Returns a float in [0, 1); mirrors ``random.random`` and is injectable so the
# jittered backoff is deterministic under test.
RandomFn = Callable[[], float]

# Backoff defaults (seconds) used when the stream is built directly rather than
# from config. ``create()`` overrides these from :class:`EngineConfig`.
_DEFAULT_BACKOFF_BASE_S = 5.0
_DEFAULT_BACKOFF_MAX_S = 60.0
# Clamp the exponent so ``base * 2**attempt`` never turns into pathological
# big-int arithmetic during a very long outage; the ceiling caps it long before.
_MAX_BACKOFF_EXPONENT = 32


class _StreamDisconnectedError(Exception):
    """Internal signal: the socket delivered the max-reconnect error sentinel.

    Raised inside the receive loop so the sentinel and a genuine transport
    exception funnel through the same "tear down and reconnect" path.
    """


# --------------------------------------------------------------------------
# Testability seam
# --------------------------------------------------------------------------
class KlineSocket(Protocol):
    """An open kline websocket: an async context manager yielding messages."""

    async def __aenter__(self) -> KlineSocket: ...

    async def __aexit__(self, exc_type: object, exc: object, tb: object) -> object: ...

    async def recv(self) -> dict[str, Any]: ...


class KlineSocketSource(Protocol):
    """Opens kline sockets and owns the underlying connection's lifecycle."""

    def multiplex(self, streams: list[str]) -> KlineSocket:
        """Open one combined stream for all of ``streams`` (not yet connected)."""

    async def aclose(self) -> None:
        """Release the underlying connection/client."""


class _BinanceSocketSource:
    """Real :class:`KlineSocketSource` over a dedicated ``AsyncClient``.

    A private ``AsyncClient`` is used purely for a clean, independent lifecycle:
    this source issues no REST calls, so it never contends with the trading
    :class:`~trading_bot.exchange.binance_client.BinanceClient`, and closing it
    tears down only the stream's socket manager.
    """

    def __init__(self, client: Any, socket_manager: Any) -> None:
        self._client = client
        self._manager = socket_manager

    @classmethod
    async def create(cls, settings: Settings) -> _BinanceSocketSource:
        from binance import AsyncClient
        from binance.ws.streams import BinanceSocketManager

        api_key, api_secret = settings.binance_credentials()
        exchange = settings.config.exchange
        # Point the feed at the SAME environment as the REST client
        # (BinanceClient.create): testnet only in TESTNET mode, so REST history
        # and the live stream never come from different price universes.
        testnet = settings.mode is TradingMode.TESTNET
        client = await AsyncClient.create(
            api_key=api_key,
            api_secret=api_secret,
            testnet=testnet,
            requests_params={"timeout": exchange.requests_timeout_s},
        )
        return cls(client, BinanceSocketManager(client))

    def multiplex(self, streams: list[str]) -> KlineSocket:
        # multiplex_socket returns a ReconnectingWebsocket (typed Any here
        # because python-binance ships no stubs); bind it to the Protocol.
        socket: KlineSocket = self._manager.multiplex_socket(streams)
        return socket

    async def aclose(self) -> None:
        await self._client.close_connection()


# --------------------------------------------------------------------------
# Stream
# --------------------------------------------------------------------------
class BinanceMarketDataStream(MarketDataStream):
    """Live kline feed that delivers closed candles to per-symbol handlers."""

    def __init__(
        self,
        source: KlineSocketSource,
        *,
        backoff_base_s: float = _DEFAULT_BACKOFF_BASE_S,
        backoff_max_s: float = _DEFAULT_BACKOFF_MAX_S,
        max_retries: int | None = None,
        sleep: SleepFn | None = None,
        random_fn: RandomFn | None = None,
    ) -> None:
        """Build a stream over ``source``.

        ``max_retries`` bounds *consecutive* failed reconnects; ``None`` or ``0``
        means retry indefinitely (the 24/7 default). The counter resets after any
        message is received, so a feed that reconnects successfully never
        accumulates toward the cap. ``sleep`` and ``random_fn`` are injectable to
        make the jittered backoff deterministic in tests.
        """
        if backoff_base_s <= 0:
            raise ValueError("backoff_base_s must be > 0")
        if backoff_max_s < backoff_base_s:
            raise ValueError("backoff_max_s must be >= backoff_base_s")
        if max_retries is not None and max_retries < 0:
            raise ValueError("max_retries must be >= 0 or None")

        self._source = source
        self._backoff_base_s = backoff_base_s
        self._backoff_max_s = backoff_max_s
        # Normalise the "0 == infinite" convention to None internally.
        self._max_retries: int | None = max_retries or None
        self._sleep: SleepFn = sleep or asyncio.sleep
        self._random: RandomFn = random_fn or random.random

        self._handlers: dict[tuple[str, str], list[CandleHandler]] = {}
        self._stream_names: dict[tuple[str, str], str] = {}
        self._task: asyncio.Task[None] | None = None
        self._running = False

    @classmethod
    async def create(
        cls,
        settings: Settings,
        *,
        sleep: SleepFn | None = None,
        random_fn: RandomFn | None = None,
    ) -> BinanceMarketDataStream:
        """Build a stream from :class:`Settings` (testnet unless mode is LIVE).

        Backoff and retry limits come from ``settings.config.engine``; a
        ``reconnect_max_retries`` of ``0`` maps to indefinite retrying.
        """
        engine = settings.config.engine
        source = await _BinanceSocketSource.create(settings)
        return cls(
            source,
            backoff_base_s=engine.reconnect_backoff_s,
            backoff_max_s=engine.reconnect_backoff_max_s,
            max_retries=engine.reconnect_max_retries,
            sleep=sleep,
            random_fn=random_fn,
        )

    # -- subscription -------------------------------------------------------
    def subscribe(self, symbol: str, timeframe: str, handler: CandleHandler) -> None:
        """Register ``handler`` for closed candles of ``symbol``/``timeframe``.

        Symbols are normalised to upper case for routing; the Binance stream name
        uses the lower-case convention (e.g. ``btcusdt@kline_1m``). Multiple
        handlers may share a symbol/timeframe and are invoked in subscription
        order. Subscribe before :meth:`start`; a subscription added while running
        is picked up on the next reconnect.
        """
        key = (symbol.upper(), timeframe)
        self._handlers.setdefault(key, []).append(handler)
        self._stream_names[key] = f"{symbol.lower()}@kline_{timeframe}"

    @property
    def stream_names(self) -> list[str]:
        """The distinct Binance stream names for all current subscriptions."""
        return sorted(set(self._stream_names.values()))

    # -- lifecycle ----------------------------------------------------------
    async def start(self) -> None:
        """Start the background receive/dispatch task. Idempotent."""
        if self._task is not None:
            return
        if not self._stream_names:
            raise ValueError("no subscriptions; call subscribe() before start()")
        self._running = True
        self._task = asyncio.create_task(self._run(), name="binance-market-data-stream")

    async def stop(self) -> None:
        """Cancel the receive task and release the underlying connection.

        Safe to call more than once and even if :meth:`start` was never called.
        """
        self._running = False
        task, self._task = self._task, None
        if task is not None:
            task.cancel()
            # The task may have already ended with an error (e.g. a bounded
            # retry give-up, already logged); swallow whatever surfaces here.
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await task
        await self._source.aclose()

    # -- reconnection -------------------------------------------------------
    def _backoff_delay(self, attempt: int) -> float:
        """Capped exponential backoff with *equal jitter*.

        The ceiling grows as ``base * 2**attempt`` up to ``backoff_max_s``. Equal
        jitter (half fixed + half random) keeps the delay within
        ``[ceiling/2, ceiling)`` so reconnections never hot-spin against a downed
        endpoint yet stay de-correlated across bot instances.
        """
        exponent = min(attempt, _MAX_BACKOFF_EXPONENT)
        ceiling = min(self._backoff_max_s, self._backoff_base_s * (2.0**exponent))
        return ceiling * (0.5 + 0.5 * self._random())

    async def _run(self) -> None:
        """Own the feed for its lifetime: connect, receive, dispatch, reconnect."""
        attempt = 0
        while self._running:
            try:
                # Recompute each cycle so a reconnect picks up late subscriptions.
                socket = self._source.multiplex(self.stream_names)
                async with socket as active:
                    while self._running:
                        message = await active.recv()
                        if message.get(_WS_EVENT_TYPE) == _WS_EVENT_ERROR:
                            # Library gave up its own reconnects; rebuild fresh.
                            raise _StreamDisconnectedError(
                                str(message.get("type", _WS_EVENT_ERROR))
                            )
                        # A good message means the connection is healthy again.
                        attempt = 0
                        await self._dispatch(message)
            except asyncio.CancelledError:
                # stop() cancelled us — not a reconnectable condition.
                raise
            except Exception as exc:  # any failure => reconnect
                if not self._running:
                    break
                if self._max_retries is not None and attempt >= self._max_retries:
                    _log.error(
                        "Market-data stream giving up after %d consecutive reconnect attempts: %s",
                        self._max_retries,
                        exc,
                    )
                    raise
                delay = self._backoff_delay(attempt)
                _log.warning(
                    "Market-data stream disconnected (%s); reconnecting in %.1fs (attempt %d)",
                    exc,
                    delay,
                    attempt + 1,
                )
                await self._sleep(delay)
                attempt += 1

    async def _dispatch(self, message: dict[str, Any]) -> None:
        """Map one message to a candle and fan it out to closed-candle handlers.

        Non-kline messages are ignored. Forming candles are dropped (the handler
        contract is closed candles only). Each handler is isolated: an exception
        from one is logged and the rest still run, so a buggy handler cannot kill
        the feed.
        """
        event = unwrap_stream_message(message)
        if event.get(_WS_EVENT_TYPE) != _WS_EVENT_KLINE:
            _log.debug("Ignoring non-kline stream message: %r", event.get(_WS_EVENT_TYPE))
            return

        candle = ws_kline_to_candle(event)
        if not candle.is_closed:
            return

        key = (candle.symbol, candle.timeframe)
        for handler in self._handlers.get(key, ()):
            try:
                await handler(candle)
            except Exception:  # isolate a bad handler
                _log.exception(
                    "Candle handler failed for %s/%s; continuing",
                    candle.symbol,
                    candle.timeframe,
                )
