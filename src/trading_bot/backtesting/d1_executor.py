"""The D1 executor: the backtest's stand-in for the live executor when the exit is the D1 trailing stop.

It satisfies :class:`~trading_bot.core.interfaces.Dispatcher` exactly as
:class:`~trading_bot.backtesting.simulated_executor.SimulatedExecutor` does, so the signal chain
(strategy, ``RiskManager.evaluate``, the one signal handler) is the live code and only the executor
differs. It is chosen only for a strategy that declares the D1 exit (``declares_d1_exit``); every other
strategy keeps the simulated executor, untouched. It owns no price rule: the entry fill is
``fill_model.fill_entry`` unchanged, the exit is :func:`~trading_bot.backtesting.d1_trail.resolve_trail`,
and fees come from ``fill_model.book_entry`` and ``book_exit``.

**What differs from the simulated executor, and why.**

* **The exit is not tested against the decision bar.** A D1 position is protected by one trailing stop
  that the venue triggers intrabar, so it is walked over the 1m path (R-DV) from the first TRADED minute
  of the entry bar (a minute with volume, section 80), at the entry fill price, with the signal's own
  ``trail_delta_bps`` (charter section 17). The decision bars are the archive 4h and 1d series the replay
  already serves.
* **The exit is SCHEDULED, not discovered.** Every candidate emits ``BUY`` and never ``CLOSE``, so a
  position's exit is a function of its 1m path alone and nothing a later decision does can change it.
  The walk is therefore done once, at the fill, and the exit is booked at the end of its minute (the exit
  minute's open plus one minute) when the simulated clock reaches it. Exits are processed in time order
  across both pairs, and an exit is booked BEFORE any decision whose nominal end is at or after it, so no
  decision sees an exit that is still in its future and none misses one that has passed.
* **The initial stop is the trail's first trigger.** ``Position.stop_loss`` is
  ``fill x (1 - delta / 10000)``, the level the unchanged risk manager prices committed risk from; it is
  not trailed, because nothing places a trailing level at the venue (CLAUDE.md, the committed-risk
  supersession).
* **It tallies what the research run prints and nothing else:** per symbol the signals, the refusals by
  stage and by the rule that refused (R-DT-3e), the queued entries whose size the position cap limited
  (R-DT-3f), the clamps and the deltas. It records no figure of money beyond what the ledger needs.

**What one decision bar does, in this order** (``__call__``): observe the bar; book the exits at or
before the bar's open; settle a pending entry against it (booking first any exit at or before the entry
minute); book the exits at or before the bar's nominal end; stamp every open position. The bar is
observed first so that a trade is flagged as spanning a gap when the gap lies between its entry and
the bar that books it; the flag may also fire for a gap that follows an exit by less than one bar.

A missing 1m minute while a position is open is skipped, not filled: the walk reads the traded minutes
it is given, so a fall inside a gap meets the gap rule at the next traded open, the worse exit
(R-EB). A decision-bar gap is handled as in the simulated executor: an entry whose next slot is missing
EXPIRES.
"""

from __future__ import annotations

import dataclasses
import heapq
import itertools
from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import Decimal

from trading_bot.backtesting.d1_trail import TrailStatus, resolve_trail, trigger_price
from trading_bot.backtesting.fill_model import (
    EntryBooking,
    EntryFill,
    EntryOutcome,
    FillParameters,
    book_entry,
    book_exit,
    fill_entry,
)
from trading_bot.backtesting.simulated_executor import (
    Clock,
    EntryAttempt,
    EntryResult,
    ExecutorCounts,
    SimulatedExit,
    SimulatedTrade,
)
from trading_bot.core.assessment import EntryIntent, RiskAssessment
from trading_bot.core.enums import PositionSide, ProtectionState, RefusalStage, RiskRule
from trading_bot.core.exceptions import TradingBotError
from trading_bot.core.models import Candle, Fee, Position, Signal
from trading_bot.core.portfolio import Portfolio
from trading_bot.data.historical import HistoricalStore
from trading_bot.utils.helpers import timeframe_to_ms
from trading_bot.utils.logger import get_logger

__all__ = ["D1Executor", "D1ExecutorError", "SymbolTally"]

_log = get_logger(__name__)

#: The metadata keys ``strategies.m5n.trail`` writes; a test pins that the two agree.
DELTA_KEY = "trail_delta_bps"
CLAMP_KEY = "trail_clamp"
#: What ``risk.position_sizing.calculate_position_size`` writes into a sizing reason when the quantity was
#: cut by ``max_position_size_percent`` (R-DT-3f). The unchanged manager exposes no flag for it:
#: ``SizingDecision`` carries the requested and the final quantity, but the cap is knowable numerically
#: only with the equity this executor does not hold. A test calls the real sizer to pin that the marker
#: is present when the cap binds and absent when it does not.
CAP_MARKER = ", capped at "
_MILLISECOND = timedelta(milliseconds=1)
_MINUTE = timedelta(minutes=1)
_BASIS_POINTS = Decimal(10000)


class D1ExecutorError(TradingBotError):
    """A signal reached the D1 executor in a shape a D1 strategy never produces."""


@dataclass
class SymbolTally:
    """What one pair's signals came to. A snapshot is a detached copy."""

    signals: int = 0
    refusals: dict[RefusalStage, int] = field(default_factory=dict)
    #: The rule that refused, for a refusal that carries one (R-DT-3e): the five limit rules under
    #: ``limit_refused`` and ``no_mark_price`` under its own stage. A refusal after the limits passed
    #: (sizing, affordability) carries no rule and appears under ``refusals`` only.
    rules: dict[RiskRule, int] = field(default_factory=dict)
    #: Queued entries whose size ``max_position_size_percent`` limited (R-DT-3f).
    size_capped: int = 0
    clamp_upper: int = 0
    clamp_lower: int = 0
    deltas: list[int] = field(default_factory=list)


@dataclass
class _Track:
    last_open: datetime | None = None
    gaps: int = 0
    shorts: int = 0


@dataclass(frozen=True)
class _PendingEntry:
    intent: EntryIntent
    timeframe: str
    signal_bar_open: datetime
    signal_bar_close: datetime
    placed_at: datetime
    delta_bps: int


@dataclass(frozen=True)
class _Held:
    intent: EntryIntent
    timeframe: str
    signal_bar_open: datetime
    entry_bar_open: datetime
    booking: EntryBooking
    delta_bps: int
    gaps_before: int
    shorts_before: int


@dataclass(frozen=True)
class _Scheduled:
    booking_time: datetime
    exit_minute: datetime
    price: Decimal
    trigger: Decimal
    gap: bool


class D1Executor:
    """Sequences the fill model and the D1 trail against a ``Portfolio``; satisfies ``Dispatcher``.

    :param portfolio: the unchanged live ledger.
    :param params: the three fill percents.
    :param clock: the simulated instant, the replay stream's ``now``; read once per bar.
    :param store: where the 1m path is read from. It only reads.
    :param window_end: the exclusive end of the window; the 1m path is bounded here, so no bar at or
        after it is ever read.
    """

    def __init__(
        self,
        *,
        portfolio: Portfolio,
        params: FillParameters,
        clock: Clock,
        store: HistoricalStore,
        window_end: datetime,
    ) -> None:
        self._portfolio = portfolio
        self._params = params
        self._clock = clock
        self._store = store
        self._window_end = window_end
        self._tracks: dict[str, _Track] = {}
        self._pending: dict[str, _PendingEntry] = {}
        self._held: dict[str, _Held] = {}
        self._heap: list[tuple[datetime, int, str]] = []
        self._scheduled: dict[str, _Scheduled] = {}
        self._sequence = itertools.count()
        self._trades: list[SimulatedTrade] = []
        self._attempts: list[EntryAttempt] = []
        self._counts = ExecutorCounts()
        self._tallies: dict[str, SymbolTally] = {}

    # -- what the run produced ------------------------------------------------
    @property
    def trades(self) -> tuple[SimulatedTrade, ...]:
        """Every closed round trip, in the order they closed."""
        return tuple(self._trades)

    @property
    def attempts(self) -> tuple[EntryAttempt, ...]:
        """Every approved entry that was settled, in the order it settled."""
        return tuple(self._attempts)

    @property
    def counts(self) -> ExecutorCounts:
        """A detached snapshot of the counters."""
        return dataclasses.replace(self._counts)

    @property
    def unsettled(self) -> dict[str, tuple[str, ...]]:
        """What was still in flight. A D1 executor queues no ``CLOSE``, so that list is empty."""
        return {
            "open_positions": tuple(sorted(self._held)),
            "pending_entries": tuple(sorted(self._pending)),
            "queued_closes": (),
        }

    @property
    def tallies(self) -> dict[str, SymbolTally]:
        """A detached copy of each pair's signal tally."""
        return {
            symbol: SymbolTally(
                signals=tally.signals,
                refusals=dict(tally.refusals),
                rules=dict(tally.rules),
                size_capped=tally.size_capped,
                clamp_upper=tally.clamp_upper,
                clamp_lower=tally.clamp_lower,
                deltas=list(tally.deltas),
            )
            for symbol, tally in self._tallies.items()
        }

    # -- the signal side --------------------------------------------------------
    async def dispatch(self, signal: Signal, assessment: RiskAssessment, candle: Candle) -> None:
        """Tally the signal, and record an approved entry for the next bar. Never fills anything.

        :raises D1ExecutorError: the signal carries no integer ``trail_delta_bps``, or an approved
            intent is an exit; a D1 strategy emits neither. The handler that calls this isolates the
            raise and logs it, which makes the run incomplete.
        """
        self._counts.dispatched += 1
        raw = signal.metadata.get(DELTA_KEY)
        if type(raw) is not int:
            raise D1ExecutorError(f"{signal.symbol}: the signal carries no integer {DELTA_KEY}")
        tally = self._tallies.setdefault(signal.symbol, SymbolTally())
        tally.signals += 1
        tally.deltas.append(raw)
        clamp = signal.metadata.get(CLAMP_KEY)
        if clamp == "upper":
            tally.clamp_upper += 1
        elif clamp == "lower":
            tally.clamp_lower += 1
        intent = assessment.intent
        if not assessment.approved or intent is None:
            self._counts.refused_by_risk += 1
            if assessment.stage is not None:
                tally.refusals[assessment.stage] = tally.refusals.get(assessment.stage, 0) + 1
            rule = None if assessment.decision is None else assessment.decision.rule
            if rule is not None:
                tally.rules[rule] = tally.rules.get(rule, 0) + 1
            return
        if not isinstance(intent, EntryIntent):
            raise D1ExecutorError(f"{signal.symbol}: a D1 strategy never asks to close")
        symbol = intent.symbol
        if symbol in self._pending or symbol in self._held:
            self._counts.entries_ignored += 1
            _log.warning("Entry for %s ignored: an entry is pending or a position is held", symbol)
            return
        step = timedelta(milliseconds=timeframe_to_ms(candle.timeframe))
        self._pending[symbol] = _PendingEntry(
            intent=intent,
            timeframe=candle.timeframe,
            signal_bar_open=candle.open_time,
            signal_bar_close=candle.close_time,
            placed_at=candle.open_time + step,
            delta_bps=raw,
        )
        self._counts.entries_queued += 1
        if assessment.sizing is not None and CAP_MARKER in assessment.sizing.reason:
            tally.size_capped += 1

    # -- the candle side --------------------------------------------------------
    async def __call__(self, candle: Candle) -> None:
        """Book what is due, settle a pending entry, book what is due again, then stamp."""
        now = self._clock()
        track = self._tracks.setdefault(candle.symbol, _Track())
        gaps_before, shorts_before = track.gaps, track.shorts
        self._observe(track, candle)
        self._book_through(candle.open_time)
        self._settle_entry(candle, gaps_before=gaps_before, shorts_before=shorts_before)
        self._book_through(now)
        self._stamp(now)

    def finish(self) -> None:
        """The data has ended: a pending entry has no next bar and EXPIRES, and every scheduled exit
        inside the window is booked. A position whose trail never triggered stays open. Idempotent."""
        for symbol in sorted(self._pending):
            pending = self._pending.pop(symbol)
            fill = fill_entry(
                entry_limit=pending.intent.entry_limit,
                placed_at=pending.placed_at,
                next_bar=None,
                params=self._params,
            )
            self._counts.entries_expired += 1
            self._attempts.append(self._attempt(pending, EntryResult.EXPIRED, fill.detail, None))
        self._book_through(self._window_end)

    def _observe(self, track: _Track, candle: Candle) -> None:
        step = timedelta(milliseconds=timeframe_to_ms(candle.timeframe))
        self._counts.bars_seen += 1
        if track.last_open is not None and candle.open_time != track.last_open + step:
            track.gaps += 1
            self._counts.gaps_seen += 1
        if candle.close_time < candle.open_time + step - _MILLISECOND:
            track.shorts += 1
            self._counts.short_bars_seen += 1
        track.last_open = candle.open_time

    def _traded_minutes(self, symbol: str, start: datetime) -> Iterator[Candle]:
        for minute in self._store.candles(symbol, "1m", start, self._window_end):
            if minute.volume > 0:
                yield minute

    def _settle_entry(self, candle: Candle, *, gaps_before: int, shorts_before: int) -> None:
        pending = self._pending.pop(candle.symbol, None)
        if pending is None:
            return
        intent = pending.intent
        fill = fill_entry(
            entry_limit=intent.entry_limit,
            placed_at=pending.placed_at,
            next_bar=candle,
            params=self._params,
        )
        if fill.outcome is not EntryOutcome.FILLED or fill.price is None:
            self._record_unfilled(pending, fill, settled_on=candle)
            return
        minutes = self._traded_minutes(intent.symbol, candle.open_time)
        first = next(minutes, None)
        step = timedelta(milliseconds=timeframe_to_ms(candle.timeframe))
        if first is None or first.open_time >= candle.open_time + step:
            self._counts.entries_expired += 1
            self._attempts.append(
                self._attempt(
                    pending,
                    EntryResult.EXPIRED,
                    "no minute traded inside the entry bar, so there is no fill to trail",
                    candle,
                )
            )
            return
        self._book_through(first.open_time)
        booking = book_entry(quantity=intent.quantity, price=fill.price, params=self._params)
        if booking.quote_total > self._portfolio.free_quote:
            self._counts.entries_unaffordable += 1
            self._attempts.append(
                self._attempt(
                    pending,
                    EntryResult.UNAFFORDABLE,
                    f"the quote total {booking.quote_total} is more than the free quote "
                    f"{self._portfolio.free_quote}",
                    candle,
                )
            )
            return
        stop = fill.price * (1 - Decimal(pending.delta_bps) / _BASIS_POINTS)
        position = Position(
            symbol=intent.symbol,
            side=PositionSide.LONG,
            quantity=intent.quantity,
            entry_price=intent.entry_limit,
            entry_fill_price=fill.price,
            entry_quote_total=booking.quote_total,
            entry_bar_time=pending.signal_bar_close,
            protection=ProtectionState.UNKNOWN,
            opened_at=candle.open_time,
            stop_loss=stop,
            take_profit=None,
        )
        self._portfolio.open_position(position, cost=booking.quote_total)
        self._counts.entries_filled += 1
        self._attempts.append(self._attempt(pending, EntryResult.FILLED, fill.detail, candle, fill))
        self._held[intent.symbol] = _Held(
            intent=intent,
            timeframe=pending.timeframe,
            signal_bar_open=pending.signal_bar_open,
            entry_bar_open=candle.open_time,
            booking=booking,
            delta_bps=pending.delta_bps,
            gaps_before=gaps_before,
            shorts_before=shorts_before,
        )
        outcome = resolve_trail(
            entry_time=first.open_time,
            entry_price=fill.price,
            delta_bps=pending.delta_bps,
            stop_slippage_percent=self._params.stop_slippage_percent,
            bars=itertools.chain((first,), minutes),
        )
        if outcome.status is TrailStatus.EXITED and outcome.exit_minute is not None:
            assert outcome.exit_price is not None
            booked_at = outcome.exit_minute + _MINUTE
            self._scheduled[intent.symbol] = _Scheduled(
                booking_time=booked_at,
                exit_minute=outcome.exit_minute,
                price=outcome.exit_price,
                trigger=trigger_price(outcome.peak, pending.delta_bps),
                gap=outcome.gap,
            )
            heapq.heappush(self._heap, (booked_at, next(self._sequence), intent.symbol))

    def _record_unfilled(
        self, pending: _PendingEntry, fill: EntryFill, *, settled_on: Candle
    ) -> None:
        if fill.outcome is EntryOutcome.REFUSED:
            result = EntryResult.REFUSED
            self._counts.entries_refused += 1
        else:
            result = EntryResult.EXPIRED
            self._counts.entries_expired += 1
        self._attempts.append(self._attempt(pending, result, fill.detail, settled_on))

    def _attempt(
        self,
        pending: _PendingEntry,
        result: EntryResult,
        detail: str,
        settled_on: Candle | None,
        fill: EntryFill | None = None,
    ) -> EntryAttempt:
        return EntryAttempt(
            symbol=pending.intent.symbol,
            timeframe=pending.timeframe,
            signal_bar_open=pending.signal_bar_open,
            placed_at=pending.placed_at,
            entry_limit=pending.intent.entry_limit,
            result=result,
            detail=detail,
            settled_bar_open=None if settled_on is None else settled_on.open_time,
            price=None if fill is None else fill.price,
        )

    def _book_through(self, limit: datetime) -> None:
        while self._heap and self._heap[0][0] <= limit:
            _, _, symbol = heapq.heappop(self._heap)
            self._book(symbol, self._scheduled.pop(symbol))

    def _book(self, symbol: str, due: _Scheduled) -> None:
        held = self._held[symbol]
        position = self._portfolio.positions[symbol]
        booking = book_exit(quantity=position.quantity, price=due.price, params=self._params)
        realised = self._portfolio.close_position(
            symbol,
            exit_quote_total=booking.gross,
            now=due.booking_time,
            fee=Fee(amount=booking.fee, asset=self._portfolio.quote_asset),
        )
        track = self._tracks[symbol]
        self._trades.append(
            SimulatedTrade(
                symbol=symbol,
                timeframe=held.timeframe,
                signal_bar_open=held.signal_bar_open,
                entry_bar_open=held.entry_bar_open,
                quantity=held.booking.quantity,
                entry_limit=held.intent.entry_limit,
                entry_price=held.booking.price,
                entry_notional=held.booking.notional,
                entry_fee=held.booking.fee,
                entry_quote_total=held.booking.quote_total,
                stop_loss=position.stop_loss,
                take_profit=None,
                exit_reason=SimulatedExit.STOP_LOSS,
                exit_bar_open=due.exit_minute,
                exit_time=due.booking_time,
                exit_price=due.price,
                exit_trigger=due.trigger,
                exit_open_through_trigger=due.gap,
                exit_gross=booking.gross,
                exit_fee=booking.fee,
                realised=realised,
                spans_gap=track.gaps > held.gaps_before,
                spans_short_bar=track.shorts > held.shorts_before,
            )
        )
        del self._held[symbol]
        self._counts.exits_stop_loss += 1

    def _stamp(self, now: datetime) -> None:
        for symbol in self._held:
            position = self._portfolio.positions.get(symbol)
            if position is not None:
                position.record_reconciliation(protection=ProtectionState.ACTIVE, at=now)
