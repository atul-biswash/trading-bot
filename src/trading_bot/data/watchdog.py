"""Feed watchdog: says when the candle pipeline goes quiet, late or slow (P-3l).

Three things can stop the bot knowing what the market is doing, and until this
module none of them left a line:

* **a pair goes silent** -- no closed bar accepted for longer than the pair's
  timeframe allows, because the socket died, the library is reconnecting, or the
  consumer is stalled;
* **the event loop lags** -- everything on the loop, the library's read loop and
  every handler included, runs late;
* **a handler chain is slow** -- one candle's subscribers (reconciler, executor,
  engine) take a large part of a bar to finish, which holds the next bar in the
  library's queue.

**It REPORTS and nothing else.** No halt, no reconnect, no refusal: the project
owner's ruling at P91 accepted reporting without repair for the outage under P76,
and ``CRITICAL`` here is a log line, the shape ``docs/QB_ESCALATION.md`` ratified
for every ``CRITICAL`` in this tree. Every line is emitted ONCE PER EPISODE, so a
feed that stays silent for an hour logs one warning and one critical, and every
episode ends with an ``INFO`` line carrying how long it lasted.

**It touches no ``Portfolio`` and writes nothing the decision path reads**, which
is why a background task is safe here where a timer that reconciled would not be:
the single-writer argument in ``CLAUDE.md`` ("Dispatch stays inline") concerns a
task that mutates shared state, and this one only logs.

Time is read from an injected monotonic clock and slept on an injected sleep, so
every threshold is tested without real time. A fully blocked event loop cannot run
this task either; what it can do is report the lag the moment the loop resumes,
which is the measurement the stall in ``M5l-198`` has been missing.
"""

from __future__ import annotations

import asyncio
import contextlib
import time
from collections.abc import Awaitable, Callable, Iterable
from dataclasses import dataclass

from trading_bot.core.models import Candle
from trading_bot.utils.helpers import timeframe_to_ms
from trading_bot.utils.logger import get_logger

__all__ = ["FeedWatchdog"]

_log = get_logger(__name__)

_Key = tuple[str, str]
Clock = Callable[[], float]

#: A pair is silent from this multiple of its timeframe with no accepted bar.
WARN_FACTOR = 1.5
#: ... and critically silent from this multiple. The P91 pin 5 numbers.
CRITICAL_FACTOR = 5.0
#: The event loop is lagging when a tick is this many seconds late.
LAG_WARN_S = 5.0
#: A handler chain is slow when one candle's subscribers take more than this
#: fraction of the bar.
SLOW_CHAIN_FRACTION = 0.5
#: How often the watchdog looks, in seconds. Fine enough that 1.5 x 60 s is
#: reported within a second of crossing, and cheap: a dict walk.
_TICK_S = 1.0

_EVENT_SILENT = "feed_silent"
_EVENT_CRITICAL = "feed_silent_critical"
_EVENT_RESUMED = "feed_resumed"
_EVENT_LAG = "event_loop_lagging"
_EVENT_LAG_OVER = "event_loop_recovered"
_EVENT_SLOW = "handler_chain_slow"
_EVENT_SLOW_OVER = "handler_chain_recovered"


@dataclass(slots=True)
class _PairState:
    """One pair's heartbeat. ``last_arrival`` is the start of the last accepted bar's chain."""

    period_s: float
    last_arrival: float
    warned: bool = False
    critical: bool = False
    slow: bool = False


class FeedWatchdog:
    """Watches arrival, loop lag and handler-chain time, and reports each once per episode."""

    def __init__(
        self,
        *,
        clock: Clock = time.monotonic,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        tick_s: float = _TICK_S,
        warn_factor: float = WARN_FACTOR,
        critical_factor: float = CRITICAL_FACTOR,
        lag_warn_s: float = LAG_WARN_S,
        slow_chain_fraction: float = SLOW_CHAIN_FRACTION,
    ) -> None:
        if not 0 < warn_factor < critical_factor:
            raise ValueError("need 0 < warn_factor < critical_factor")
        if tick_s <= 0 or lag_warn_s <= 0 or not 0 < slow_chain_fraction <= 1:
            raise ValueError("tick_s and lag_warn_s must be > 0; slow_chain_fraction in (0, 1]")
        self._clock = clock
        self._sleep = sleep
        self._tick_s = tick_s
        self._warn_factor = warn_factor
        self._critical_factor = critical_factor
        self._lag_warn_s = lag_warn_s
        self._slow_fraction = slow_chain_fraction
        self._pairs: dict[_Key, _PairState] = {}
        self._lagging = False
        self._lag_started: float | None = None
        self._task: asyncio.Task[None] | None = None

    # -- wiring -------------------------------------------------------------
    def arm(self, pairs: Iterable[_Key]) -> None:
        """Start watching ``pairs``, each from NOW, so boot time is not counted as silence."""
        now = self._clock()
        for symbol, timeframe in pairs:
            key = (symbol.upper(), timeframe)
            self._pairs[key] = _PairState(
                period_s=timeframe_to_ms(timeframe) / 1000.0, last_arrival=now
            )

    def on_chain(self, candle: Candle, started_at: float, finished_at: float) -> None:
        """The provider's observer: one call per accepted bar, after its handler chain ran.

        ``started_at`` is when the bar was accepted and the chain began; the pair's
        arrival is that instant, not the chain's end, so a slow chain cannot make
        the next silence look shorter than it was.
        """
        state = self._pairs.get((candle.symbol.upper(), candle.timeframe))
        if state is None:
            return
        silent_for = started_at - state.last_arrival
        if state.warned:
            _log.info(
                "%s/%s: bars flowing again after %.1fs without one",
                candle.symbol,
                candle.timeframe,
                silent_for,
                extra={
                    "event": _EVENT_RESUMED,
                    "symbol": candle.symbol,
                    "timeframe": candle.timeframe,
                    "gap_s": round(silent_for, 3),
                },
            )
        state.last_arrival = started_at
        state.warned = False
        state.critical = False

        chain_s = finished_at - started_at
        limit_s = state.period_s * self._slow_fraction
        if chain_s > limit_s and not state.slow:
            state.slow = True
            _log.warning(
                "%s/%s: the handler chain took %.1fs, over %.1fs (%.0f%% of the bar)",
                candle.symbol,
                candle.timeframe,
                chain_s,
                limit_s,
                self._slow_fraction * 100,
                extra={
                    "event": _EVENT_SLOW,
                    "symbol": candle.symbol,
                    "timeframe": candle.timeframe,
                    "chain_s": round(chain_s, 3),
                    "limit_s": round(limit_s, 3),
                },
            )
        elif chain_s <= limit_s and state.slow:
            state.slow = False
            _log.info(
                "%s/%s: the handler chain is back under %.1fs (took %.1fs)",
                candle.symbol,
                candle.timeframe,
                limit_s,
                chain_s,
                extra={
                    "event": _EVENT_SLOW_OVER,
                    "symbol": candle.symbol,
                    "timeframe": candle.timeframe,
                    "chain_s": round(chain_s, 3),
                    "limit_s": round(limit_s, 3),
                },
            )

    # -- the checks ---------------------------------------------------------
    def check(self) -> None:
        """Report every pair that has been silent too long. Once per episode each."""
        now = self._clock()
        for (symbol, timeframe), state in self._pairs.items():
            silent_for = now - state.last_arrival
            if silent_for >= state.period_s * self._critical_factor:
                if not state.critical:
                    state.critical = True
                    state.warned = True
                    _log.critical(
                        "%s/%s: NO CLOSED BAR for %.0fs (%.1f bars); the bot is not seeing "
                        "this market, and reconciliation, which runs on candles, is stopped",
                        symbol,
                        timeframe,
                        silent_for,
                        silent_for / state.period_s,
                        extra={
                            "event": _EVENT_CRITICAL,
                            "symbol": symbol,
                            "timeframe": timeframe,
                            "silent_s": round(silent_for, 3),
                            "threshold_s": round(state.period_s * self._critical_factor, 3),
                        },
                    )
            elif silent_for >= state.period_s * self._warn_factor and not state.warned:
                state.warned = True
                _log.warning(
                    "%s/%s: no closed bar for %.0fs (%.1f bars)",
                    symbol,
                    timeframe,
                    silent_for,
                    silent_for / state.period_s,
                    extra={
                        "event": _EVENT_SILENT,
                        "symbol": symbol,
                        "timeframe": timeframe,
                        "silent_s": round(silent_for, 3),
                        "threshold_s": round(state.period_s * self._warn_factor, 3),
                    },
                )

    def observe_tick(self, lag_s: float) -> None:
        """Report event-loop lag: a tick that arrived ``lag_s`` seconds later than asked for."""
        if lag_s > self._lag_warn_s:
            if not self._lagging:
                self._lagging = True
                _log.warning(
                    "The event loop is %.1fs behind; everything on it, the market-data "
                    "reader and every handler included, is running late",
                    lag_s,
                    extra={
                        "event": _EVENT_LAG,
                        "lag_s": round(lag_s, 3),
                        "threshold_s": self._lag_warn_s,
                    },
                )
        elif self._lagging:
            self._lagging = False
            _log.info(
                "The event loop is back on time (%.1fs behind)",
                lag_s,
                extra={"event": _EVENT_LAG_OVER, "lag_s": round(lag_s, 3)},
            )

    @property
    def running(self) -> bool:
        """Whether the watchdog task is alive."""
        return self._task is not None

    def last_arrival(self, symbol: str, timeframe: str) -> float | None:
        """When the pair's last accepted bar arrived, or ``None`` if it is not watched."""
        state = self._pairs.get((symbol.upper(), timeframe))
        return None if state is None else state.last_arrival

    @property
    def watched(self) -> list[_Key]:
        """The pairs being watched."""
        return list(self._pairs)

    # -- lifecycle ----------------------------------------------------------
    async def start(self) -> None:
        """Start the watchdog task. Idempotent."""
        if self._task is not None:
            return
        self._task = asyncio.create_task(self._run(), name="feed-watchdog")

    async def stop(self) -> None:
        """Cancel the task. Idempotent, and safe if :meth:`start` was never called."""
        task, self._task = self._task, None
        if task is None:
            return
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError, Exception):
            await task

    async def _run(self) -> None:
        while True:
            before = self._clock()
            await self._sleep(self._tick_s)
            self.observe_tick(self._clock() - before - self._tick_s)
            self.check()
