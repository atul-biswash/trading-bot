"""Replay stored bars through the unchanged live market-data provider.

M5m S2 runs the live decision path over history. The path starts at
:class:`~trading_bot.data.market_data.BufferedMarketDataProvider`, which is composed from two
ports, an :class:`~trading_bot.core.interfaces.ExchangeClient` for its REST seed and a
:class:`~trading_bot.core.interfaces.MarketDataStream` for live bars, and whose own docstring
names *"a replay harness"* as something it works unchanged against. This module is that
harness, and the provider is not edited: the buffer, the append gate, the gap record, the
memoised frame and the order in which subscribers are called are the live code.

**What that buys.** The live gap guard is ``TradingEngine._window_spans_a_gap`` reading
``provider.bars_since_gap``, and the provider records a gap whenever a bar's open time is more
than one timeframe after the one before it. Neither knows WHY a bar is missing, so a stretch
the archive omitted and a stretch whose rows were quarantined both appear as missing bars and
both refuse a ``BUY`` whose warm-up window spans them (the owner's R-P1, ``M5m-120``). A
registered short bar is stored with its archive close time and its open time is on the grid, so
it is an ordinary bar here as it is in the store.

:class:`ReplayClient` answers the one REST call the provider makes, ``get_klines``, from the
store, and refuses every other method: a backtest places no order and asks the venue nothing.
:class:`ReplayStream` delivers the stored bars to the handler the provider subscribed, in the
order the live feed would have delivered them across pairs, and keeps the simulated instant.

**Time.** There is no wall clock in this module. :meth:`ReplayStream.now` is the instant the
bar being delivered CLOSES, nominally: its open time plus its timeframe. It is not the bar's
archived close time, which is one millisecond short of that on a regular bar and earlier still
on a registered short bar, and a clock that followed the archive would run backwards across an
irregular bar. A consumer that needs "now" (the risk manager's clock, a stamp on a position)
reads it, and it is set BEFORE the handler runs.

**Order across pairs.** A bar is delivered at its nominal close, and bars closing at the same
instant are delivered in the order their pairs were subscribed, which is the order the provider
tracked them, which is the order of the config. Live, two bars closing in the same second arrive
in whatever order the network gives; this is a deterministic choice among the orders live could
have shown, and it is stated so a result is not read as depending on it by accident.

**A handler that raises is isolated, as in the live stream** (``BinanceMarketDataStream.
_dispatch``): logged, counted in :attr:`ReplayStream.failures`, and the replay continues. The
count is exposed because a silent continue is the wrong default for a run whose result is a
number: a root should refuse a run that reports any.
"""

from __future__ import annotations

import heapq
from collections.abc import Iterator
from datetime import datetime, timedelta
from typing import Any

from trading_bot.core.interfaces import CandleHandler, ExchangeClient, MarketDataStream
from trading_bot.core.models import (
    Balance,
    Candle,
    Order,
    OrderList,
    OtocoOrderListRequest,
    OtoOrderListRequest,
    SymbolInfo,
    Ticker,
    Trade,
)
from trading_bot.data.historical import HistoricalStore
from trading_bot.utils.helpers import timeframe_to_ms
from trading_bot.utils.logger import get_logger

__all__ = ["ReplayClient", "ReplayError", "ReplayStream", "ReplayUnsupportedError"]

_log = get_logger(__name__)

#: The seed search never reaches back past this instant: the archive starts in 2017.
_EARLIEST = datetime.fromisoformat("2017-01-01T00:00:00+00:00")
_EPOCH = datetime.fromisoformat("1970-01-01T00:00:00+00:00")
_MILLISECOND = timedelta(milliseconds=1)

_Key = tuple[str, str]


class ReplayError(Exception):
    """The replay was driven wrongly: before it had a bar, or with nothing subscribed."""


class ReplayUnsupportedError(ReplayError):
    """A venue call that a backtest has no business making was made on the replay client."""


def _unsupported(name: str) -> ReplayUnsupportedError:
    return ReplayUnsupportedError(
        f"ReplayClient.{name}: a backtest places no order and asks the venue nothing. The "
        "replay client serves get_klines from the store, and that is all it serves"
    )


class ReplayClient(ExchangeClient):
    """The REST seed, from the store; every other call is refused.

    ``get_klines`` returns what the live REST call returns for the same moment: the last
    ``limit`` CLOSED bars that opened before ``window_start``, oldest first. It does not
    stop at a gap: like REST, it returns the most recent ``limit`` bars there are, so a hole
    inside the seed reaches the provider's append gate and is recorded there as a gap, as a
    hole inside live history would be. Fewer than ``limit`` come back only when the store
    holds fewer before ``window_start``.

    The store is read lazily, one month file at a time, hash-checked as it is read.
    """

    def __init__(self, store: HistoricalStore, window_start: datetime) -> None:
        if window_start.tzinfo is None:
            raise ValueError(f"window_start must be timezone-aware, not naive: {window_start!r}")
        self._store = store
        self._window_start = window_start

    async def get_klines(self, symbol: str, timeframe: str, *, limit: int = 500) -> list[Candle]:
        if limit < 1:
            raise ValueError(f"limit must be at least 1, got {limit}")
        step = timedelta(milliseconds=timeframe_to_ms(timeframe))
        lookback = limit
        while True:
            start = max(self._window_start - lookback * step, _EARLIEST)
            bars = list(self._store.candles(symbol, timeframe, start, self._window_start))
            if len(bars) >= limit or start <= _EARLIEST:
                return bars[-limit:]
            lookback *= 2

    async def close(self) -> None:
        """Nothing is held. Idempotent."""

    # -- everything below is refused ----------------------------------------
    async def get_balances(self, *args: Any, **kwargs: Any) -> list[Balance]:
        raise _unsupported("get_balances")

    async def get_symbol_info(self, *args: Any, **kwargs: Any) -> SymbolInfo:
        raise _unsupported("get_symbol_info")

    async def get_ticker(self, *args: Any, **kwargs: Any) -> Ticker:
        raise _unsupported("get_ticker")

    async def create_order(self, *args: Any, **kwargs: Any) -> Order:
        raise _unsupported("create_order")

    async def cancel_order(self, *args: Any, **kwargs: Any) -> Order:
        raise _unsupported("cancel_order")

    async def get_open_orders(self, *args: Any, **kwargs: Any) -> list[Order]:
        raise _unsupported("get_open_orders")

    async def get_own_open_orders(self, *args: Any, **kwargs: Any) -> list[Order]:
        raise _unsupported("get_own_open_orders")

    async def get_order(self, *args: Any, **kwargs: Any) -> Order:
        raise _unsupported("get_order")

    async def get_my_trades(self, *args: Any, **kwargs: Any) -> list[Trade]:
        raise _unsupported("get_my_trades")

    async def get_all_order_lists(self, *args: Any, **kwargs: Any) -> list[OrderList]:
        raise _unsupported("get_all_order_lists")

    async def create_otoco_order_list(
        self, request: OtocoOrderListRequest, *args: Any, **kwargs: Any
    ) -> OrderList:
        raise _unsupported("create_otoco_order_list")

    async def create_oto_order_list(
        self, request: OtoOrderListRequest, *args: Any, **kwargs: Any
    ) -> OrderList:
        raise _unsupported("create_oto_order_list")

    async def cancel_order_list(self, *args: Any, **kwargs: Any) -> OrderList:
        raise _unsupported("cancel_order_list")


class ReplayStream(MarketDataStream):
    """Delivers stored bars to the handlers subscribed, in live order, and keeps the instant.

    :meth:`subscribe` and :meth:`start` and :meth:`stop` have the live stream's contract, so
    the provider drives them unchanged: it subscribes every tracked pair, then starts the
    stream. :meth:`start` delivers nothing. Delivery is :meth:`pump`, called by whoever owns
    the run once the provider has seeded and the engine has registered its hook, because a bar
    delivered before that would find no subscriber.
    """

    def __init__(self, store: HistoricalStore) -> None:
        self._store = store
        self._handlers: dict[_Key, list[CandleHandler]] = {}
        self._order: list[_Key] = []
        self._now: datetime | None = None
        self._stopped = False
        self._failures = 0

    # -- the MarketDataStream port ------------------------------------------
    def subscribe(self, symbol: str, timeframe: str, handler: CandleHandler) -> None:
        """Register ``handler`` for the bars of one pair; handlers run in subscription order."""
        key = (symbol.upper(), timeframe)
        timeframe_to_ms(timeframe)  # a timeframe this system cannot step is refused now
        if key not in self._handlers:
            self._order.append(key)
        self._handlers.setdefault(key, []).append(handler)

    async def start(self) -> None:
        """Check that something is subscribed, as the live stream does. Delivers nothing."""
        if not self._handlers:
            raise ValueError("no subscriptions; call subscribe() before start()")

    async def stop(self) -> None:
        """Make a running :meth:`pump` return after the bar it is delivering. Idempotent."""
        self._stopped = True

    # -- the replay ---------------------------------------------------------
    @property
    def failures(self) -> int:
        """How many handler calls raised, and were logged and skipped."""
        return self._failures

    def now(self) -> datetime:
        """The instant the bar being delivered closes, nominally: open time plus timeframe.

        Set before the handlers run, and left standing after the last bar. Raises
        :class:`ReplayError` before any bar has been delivered.
        """
        if self._now is None:
            raise ReplayError("the replay has delivered no bar yet, so it has no instant")
        return self._now

    async def pump(self, start: datetime, end: datetime) -> int:
        """Deliver every stored bar with ``start <= open_time < end``; return how many.

        Bars of all subscribed pairs are merged by their nominal close time, ties going to
        the pair subscribed first. Returns early, after the bar in hand, if :meth:`stop`
        was called. A pump after :meth:`stop` delivers nothing.

        :raises ReplayError: nothing is subscribed.
        """
        if not self._handlers:
            raise ReplayError("nothing is subscribed; the provider subscribes when it starts")
        streams = [self._keyed(index, key, start, end) for index, key in enumerate(self._order)]
        delivered = 0
        for _, _, candle in heapq.merge(*streams):
            if self._stopped:
                break
            self._now = candle.open_time + timedelta(milliseconds=timeframe_to_ms(candle.timeframe))
            for handler in self._handlers[(candle.symbol, candle.timeframe)]:
                try:
                    await handler(candle)
                except Exception:  # isolate a bad handler, as the live stream does
                    self._failures += 1
                    _log.exception(
                        "Candle handler failed for %s/%s at %s; continuing",
                        candle.symbol,
                        candle.timeframe,
                        candle.open_time,
                    )
            delivered += 1
        return delivered

    def _keyed(
        self, index: int, key: _Key, start: datetime, end: datetime
    ) -> Iterator[tuple[int, int, Candle]]:
        """One pair's bars as ``(nominal close in ms, subscription index, bar)``."""
        symbol, timeframe = key
        step = timeframe_to_ms(timeframe)
        for candle in self._store.candles(symbol, timeframe, start, end):
            # Exact integer milliseconds: a float timestamp would round off the grid.
            yield (candle.open_time - _EPOCH) // _MILLISECOND + step, index, candle
