"""Market-data provider: REST history + live stream -> rolling OHLCV frames.

:class:`BufferedMarketDataProvider` implements
:class:`trading_bot.core.interfaces.MarketDataProvider`. It seeds a bounded
in-memory buffer of closed candles per ``(symbol, timeframe)`` from the REST
client, keeps it current from the WebSocket stream, and materialises it as the
``pandas`` DataFrame strategies consume.

The Decimal -> float boundary
-----------------------------
Money is :class:`~decimal.Decimal` everywhere in the domain. Indicator maths,
however, runs on NumPy, which has no Decimal fast path. This module is the one
place in the system where that conversion happens, and it is one-directional:
the *buffer* stores full-precision :class:`~trading_bot.core.models.Candle`
objects, and only the derived DataFrame is ``float64``. Execution and risk read
prices via :meth:`BufferedMarketDataProvider.last_candle`, so no money value is
ever round-tripped through a binary float.

Ordering and de-duplication
---------------------------
Every candle — seeded or streamed — passes through the single gate
:meth:`BufferedMarketDataProvider._append`, which enforces the buffer's one
invariant: *strictly increasing ``open_time``, closed candles only*. Because the
invariant holds on write, :meth:`get_dataframe` never has to sort or de-duplicate
on read. Three cases:

* ``open_time > last`` — a brand-new bar; append.
* ``open_time == last`` — the same bar re-delivered (a reconnect replay, or the
  closed version of a bar seeded while still forming); replace in place.
* ``open_time < last`` — stale; drop. Binance replays recent bars after a
  reconnect, so this is routine, not an error.

**Gaps are not backfilled.** If the stream is down longer than one bar, the
missing bars stay missing until the process restarts and re-seeds; the buffer
stays *correct* (ordered, no duplicates) but may be *incomplete*. Gap detection
plus a REST backfill on reconnect is the natural next hardening step.

Concurrency
-----------
State is mutated only from inside the asyncio event loop — by ``start()`` during
seeding and by the stream's dispatch task afterwards — and :meth:`get_dataframe`
is synchronous with no ``await`` in it, so it cannot be preempted mid-read. No
locks are needed and none are used. That guarantee is *structural*, not
incidental: a future consumer running on another thread (a dashboard, say) must
marshal onto the loop with ``loop.call_soon_threadsafe`` rather than call these
methods directly.
"""

from __future__ import annotations

from collections import deque
from collections.abc import Sequence
from typing import TYPE_CHECKING, Final

import numpy as np
import pandas as pd

from trading_bot.core.exceptions import DataError
from trading_bot.core.interfaces import (
    CandleHandler,
    ExchangeClient,
    MarketDataProvider,
    MarketDataStream,
)
from trading_bot.core.models import Candle
from trading_bot.utils.logger import get_logger

if TYPE_CHECKING:  # pragma: no cover - typing only
    from trading_bot.config.settings import Settings

_log = get_logger(__name__)

#: Columns of every frame produced here, in order. Also the ``Candle`` field
#: names, which is what lets the builder read them generically.
OHLCV_COLUMNS: Final[tuple[str, ...]] = ("open", "high", "low", "close", "volume")

#: Name of the DataFrame index (the candle's opening time, tz-aware UTC).
INDEX_NAME: Final = "open_time"

# Defaults for direct construction; ``create()`` overrides them from DataConfig.
_DEFAULT_HISTORY_LIMIT: Final = 500
_DEFAULT_BUFFER_SIZE: Final = 1000

_Key = tuple[str, str]


def _key(symbol: str, timeframe: str) -> _Key:
    """Normalise a pair to its buffer key.

    Symbols are upper-cased so ``track("btcusdt", "1m")`` and
    ``get_dataframe("BTCUSDT", "1m")` address the same buffer; this matches the
    normalisation :class:`~trading_bot.exchange.websocket_client.BinanceMarketDataStream`
    applies when routing candles to handlers.
    """
    return (symbol.upper(), timeframe)


def _empty_frame() -> pd.DataFrame:
    """An empty OHLCV frame that still satisfies the dtype/tz contract.

    ``pd.DatetimeIndex([])`` is tz-*naive*, so the timezone must be stated
    explicitly. Without this, a strategy that ran before the first candle
    arrived would see a differently-typed index than one that ran after.
    """
    return pd.DataFrame(
        {name: np.empty(0, dtype=np.float64) for name in OHLCV_COLUMNS},
        index=pd.DatetimeIndex([], tz="UTC", name=INDEX_NAME),
    )


def _build_frame(candles: Sequence[Candle]) -> pd.DataFrame:
    """Materialise buffered candles as a float64 OHLCV frame.

    No sorting or de-duplication happens here: the append gate guarantees the
    buffer is already ordered and unique, so this is a straight O(n) projection.
    """
    rows = list(candles)
    if not rows:
        return _empty_frame()
    return pd.DataFrame(
        {
            name: np.fromiter(
                (float(getattr(candle, name)) for candle in rows),
                dtype=np.float64,
                count=len(rows),
            )
            for name in OHLCV_COLUMNS
        },
        index=pd.DatetimeIndex([candle.open_time for candle in rows], name=INDEX_NAME),
    )


class BufferedMarketDataProvider(MarketDataProvider):
    """Rolling-buffer market-data provider over any exchange client + stream.

    Named for *what it does* rather than for Binance: it is composed purely from
    the :class:`~trading_bot.core.interfaces.ExchangeClient` and
    :class:`~trading_bot.core.interfaces.MarketDataStream` ports, so it works
    unchanged against a different exchange, a replay harness, or the scripted
    fakes the unit tests drive it with.
    """

    def __init__(
        self,
        client: ExchangeClient,
        stream: MarketDataStream,
        *,
        history_limit: int = _DEFAULT_HISTORY_LIMIT,
        buffer_size: int = _DEFAULT_BUFFER_SIZE,
        owns_client: bool = False,
    ) -> None:
        """Build a provider over injected ports.

        ``owns_client`` decides whether :meth:`stop` closes ``client``. It is
        ``True`` only when :meth:`create` built the client itself; an injected
        client belongs to the caller, and silently closing someone else's
        connection pool is a nasty surprise in a long-lived process.
        """
        if history_limit < 1:
            raise ValueError("history_limit must be >= 1")
        if buffer_size < history_limit:
            raise ValueError("buffer_size must be >= history_limit")

        self._client = client
        self._stream = stream
        self._history_limit = history_limit
        self._buffer_size = buffer_size
        self._owns_client = owns_client

        self._buffers: dict[_Key, deque[Candle]] = {}
        # Memoised frames. Presence == clean; the key is dropped on every
        # accepted append. See get_dataframe() for why this is worth caching.
        self._frames: dict[_Key, pd.DataFrame] = {}
        self._handlers: list[CandleHandler] = []
        self._started = False

    # -- construction -------------------------------------------------------
    @classmethod
    async def create(
        cls,
        settings: Settings,
        *,
        client: ExchangeClient | None = None,
        stream: MarketDataStream | None = None,
    ) -> BufferedMarketDataProvider:
        """Build a provider wired to Binance from :class:`Settings`.

        Sizing comes from ``settings.config.data``; every enabled pair in
        ``settings.config.trading`` is tracked automatically, so callers do not
        repeat the pair list. Both adapters honour ``settings.mode``, so the
        default is Testnet and live trading requires an explicit mode change.

        Passing ``client``/``stream`` injects pre-built ports instead (used by
        the engine when it already owns a client, and by integration tests).
        """
        # Imported lazily, mirroring BinanceClient.create: keeps python-binance
        # and aiohttp off the import path of anything that only needs the
        # provider's types, including the hermetic unit tests.
        from trading_bot.exchange.binance_client import BinanceClient
        from trading_bot.exchange.websocket_client import BinanceMarketDataStream

        data = settings.config.data
        owns_client = client is None
        resolved_client = client if client is not None else await BinanceClient.create(settings)
        try:
            resolved_stream = (
                stream if stream is not None else await BinanceMarketDataStream.create(settings)
            )
        except Exception:
            # Don't leak the client we just opened if the stream fails to build.
            if owns_client:
                await resolved_client.close()
            raise

        provider = cls(
            resolved_client,
            resolved_stream,
            history_limit=data.history_limit,
            buffer_size=data.buffer_size,
            owns_client=owns_client,
        )
        for pair in settings.config.trading.enabled_pairs:
            provider.track(pair.symbol, pair.timeframe)
        return provider

    # -- registration -------------------------------------------------------
    def track(self, symbol: str, timeframe: str) -> None:
        """Register a pair for seeding and live updates. Idempotent.

        Must be called before :meth:`start`. Tracking afterwards would create a
        buffer that is never seeded and never subscribed, so it raises instead
        of silently producing a pair that looks tracked but stays empty.
        """
        if self._started:
            raise RuntimeError("track() must be called before start()")
        self._buffers.setdefault(_key(symbol, timeframe), deque(maxlen=self._buffer_size))

    def on_candle(self, handler: CandleHandler) -> None:
        """Register a callback fired after each newly accepted closed candle.

        This is the engine's wake-up signal: rather than polling, the trading
        loop subscribes here and evaluates strategies when a bar actually
        closes. Handlers run in registration order and are isolated from each
        other (see :meth:`_notify`).
        """
        self._handlers.append(handler)

    @property
    def tracked_pairs(self) -> list[_Key]:
        """The ``(symbol, timeframe)`` pairs currently tracked, in insertion order."""
        return list(self._buffers)

    # -- lifecycle ----------------------------------------------------------
    async def start(self) -> None:
        """Seed history, wire the stream, and go live. Idempotent.

        Ordering matters and is deliberate: **seed everything first, then
        subscribe, then start the stream.** Seeding before the feed is live
        means no live candle can race ahead of the history it belongs after, so
        there is no interleaving to reason about.

        The cost of that ordering is a small blind window between the last REST
        response and the first WebSocket message — a bar closing inside it is
        missed and not backfilled (see the module docstring). The window is
        bounded by the seeding round-trips, typically well under a second for a
        handful of pairs, which is far shorter than the shortest supported bar.
        """
        if self._started:
            return
        if not self._buffers:
            raise ValueError("no tracked pairs; call track() before start()")

        for symbol, timeframe in list(self._buffers):
            await self._seed(symbol, timeframe)

        for symbol, timeframe in self._buffers:
            self._stream.subscribe(symbol, timeframe, self._make_handler((symbol, timeframe)))

        await self._stream.start()
        self._started = True
        _log.info("Market-data provider started for %d pair(s)", len(self._buffers))

    async def stop(self) -> None:
        """Stop the stream and release owned resources. Safe to call any time.

        The client is closed in a ``finally`` so a stream that fails to shut
        down cleanly still cannot leak the REST connection pool.
        """
        self._started = False
        try:
            await self._stream.stop()
        finally:
            if self._owns_client:
                await self._client.close()

    # -- reads --------------------------------------------------------------
    def get_dataframe(self, symbol: str, timeframe: str) -> pd.DataFrame:
        """Return the rolling OHLCV window as a time-ordered float64 frame.

        The frame is memoised and invalidated on append, then **copied** on the
        way out. Both halves earn their keep: the copy stops one strategy's
        ``df["sma"] = ...`` from corrupting what every other consumer sees, and
        the memo means repeated reads within a bar skip the expensive part —
        rebuilding converts every Decimal and every datetime, which measures
        ~140x the cost of copying the finished frame at a 1000-bar buffer.
        """
        key = self._require(symbol, timeframe)
        frame = self._frames.get(key)
        if frame is None:
            frame = _build_frame(self._buffers[key])
            self._frames[key] = frame
        return frame.copy()

    def candle_count(self, symbol: str, timeframe: str) -> int:
        return len(self._buffers[self._require(symbol, timeframe)])

    def last_candle(self, symbol: str, timeframe: str) -> Candle | None:
        buffer = self._buffers[self._require(symbol, timeframe)]
        return buffer[-1] if buffer else None

    def _require(self, symbol: str, timeframe: str) -> _Key:
        """Resolve a pair to its key, or fail loudly if it was never tracked.

        Raising beats returning an empty frame: a strategy handed silence
        indistinguishable from "the market is quiet" could act on a typo in
        config.yaml. A *tracked* pair with no candles yet is a different, valid
        state and does return an empty frame.
        """
        key = _key(symbol, timeframe)
        if key not in self._buffers:
            raise DataError(f"{symbol}/{timeframe} is not tracked; call track() first")
        return key

    # -- writes -------------------------------------------------------------
    async def _seed(self, symbol: str, timeframe: str) -> None:
        """Fill one buffer with REST history."""
        candles = await self._client.get_klines(symbol, timeframe, limit=self._history_limit)
        accepted = sum(1 for candle in candles if self._append((symbol, timeframe), candle))

        # A trailing still-forming bar is the normal case, not an anomaly: REST
        # history is almost always fetched mid-bar. Warning about it would fire
        # on every startup and teach the operator to ignore warnings, so it is
        # separated out and only genuinely out-of-order data is escalated.
        forming = sum(1 for candle in candles if not candle.is_closed)
        out_of_order = len(candles) - accepted - forming
        if out_of_order > 0:
            _log.warning(
                "Seeding %s/%s dropped %d out-of-order candle(s) of %d; history came back unsorted",
                symbol,
                timeframe,
                out_of_order,
                len(candles),
            )
        if forming:
            _log.debug(
                "Ignored %d still-forming candle(s) while seeding %s/%s",
                forming,
                symbol,
                timeframe,
            )
        _log.info("Seeded %s/%s with %d closed candle(s)", symbol, timeframe, accepted)

    def _append(self, key: _Key, candle: Candle) -> bool:
        """Insert ``candle`` into its buffer, upholding the ordering invariant.

        Returns ``True`` if the buffer changed. Forming candles are rejected
        here rather than at the call sites so seeding and streaming cannot drift
        apart: the stream already filters them, but REST history can end on a
        bar that is still open, and a strategy must never see a partial bar as
        final.
        """
        if not candle.is_closed:
            return False

        buffer = self._buffers[key]
        if buffer and candle.open_time < buffer[-1].open_time:
            return False  # stale replay after a reconnect
        if buffer and candle.open_time == buffer[-1].open_time:
            buffer[-1] = candle  # same bar re-delivered, possibly corrected
        else:
            buffer.append(candle)  # the normal case: a new bar
        self._frames.pop(key, None)  # invalidate the memoised frame
        return True

    def _make_handler(self, key: _Key) -> CandleHandler:
        """Build the stream callback for one pair.

        The key is bound at subscribe time rather than re-derived from the
        candle, so a candle can only ever land in the buffer that was seeded
        for it.
        """

        async def handler(candle: Candle) -> None:
            if not self._append(key, candle):
                _log.debug(
                    "Ignored non-advancing candle for %s/%s at %s",
                    key[0],
                    key[1],
                    candle.open_time,
                )
                return
            await self._notify(candle)

        return handler

    async def _notify(self, candle: Candle) -> None:
        """Fan a new candle out to subscribers, isolating failures.

        Mirrors the stream's handler isolation: a buggy consumer must not be
        able to kill the data feed the rest of the bot depends on.
        """
        for handler in self._handlers:
            try:
                await handler(candle)
            except Exception:
                _log.exception(
                    "Market-data candle handler failed for %s/%s; continuing",
                    candle.symbol,
                    candle.timeframe,
                )
