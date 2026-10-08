"""The simulated executor: the backtest's stand-in for ``OrderExecutor``.

It satisfies :class:`~trading_bot.core.interfaces.Dispatcher`, the two entry points the live
executor has, so the signal chain (strategy, ``RiskManager.evaluate``, the one signal handler)
is the live code and only this object differs. It owns no price rule. Every price and fee comes
from :mod:`trading_bot.backtesting.fill_model`; what is decided HERE is the sequencing: which
bar an order is handed, what happens on a bar, in what order, and what a pass leaves behind.
The rules are the owner's R-AA (M5m P106), R-W and R-P1, and each is stated where it is used.

**The two seams.**

* :meth:`SimulatedExecutor.dispatch` is the signal side. It never fills anything. It records an
  approved entry, or an approved ``CLOSE``, to be settled on a LATER bar. A signal is decided on
  a bar that has already closed, so the first price it can trade at is the next open.
* :meth:`SimulatedExecutor.__call__` is the candle side. Registered ahead of the engine's own
  hook, it runs first on every bar of every pair, so the strategy deciding on a bar already sees
  that bar's fills booked, as it does live ("reconcile, then decide").

**What one bar does, in this order** (``__call__``):

1. Observe the bar: a jump in open time since the pair's previous bar is a GAP, and a bar whose
   archived close is earlier than its slot is a registered SHORT bar. Both only flag trades.
2. Settle a pending ENTRY against this bar, if the pair has one. The bar must be the one whose
   open time is the signal bar's open plus one interval; if that slot is missing the entry
   EXPIRES (R-AA, R-W(d)). It fills at the open plus slippage iff that is within the entry
   limit; otherwise the ``FOK`` is refused. ``intent.quantity`` is filled as it stands and is
   never re-sized (R-AA).
3. Settle the pair's open position against this bar. **Protection is active from the entry
   bar's open**, so a position opened in step 2 is tested against the same bar's high and low
   (R-AA). A queued ``CLOSE`` is settled here too, below.
4. Stamp every open position of every pair: ``ACTIVE`` when protective legs were requested,
   ``ABSENT_BY_DESIGN`` when none were, and ``last_reconciled_at`` set to the simulated instant.
   The live reconciler does this on any pair's candle, and ``RiskManager.evaluate`` refuses
   every entry unless every open position is trusted and fresh, so without the pass an ETH 5m
   position would read stale on BTC's 1m bars and refuse all BTC entries (R-AA).

**A ``CLOSE`` and a gap.** A ``CLOSE`` queued on bar ``t`` sells at the open of bar ``t + 1``,
less slippage, with no protective test first: live cancels the protective legs before it
sells. If ``t + 1`` is missing, nothing could trade, so the ``CLOSE`` queues to the first bar
after the gap and **protection stays in force across it**. On that bar the stop's gap-through
check runs BEFORE the ``CLOSE``: an open already at or through the stop fills the stop at the
open less the stop slippage, and the ``CLOSE`` has nothing left to sell (R-AA). Only the stop's
check is run first, as ruled. A take-profit the open gapped over is not tested, so the ``CLOSE``
sells at that open less the entry slippage, which is no worse for the strategy than the
take-profit's own fill: a bias IN its favour, stated so a result is not read as free of it.

**Time.** There is no wall clock in this module. ``clock`` is the simulated instant (the replay
stream's ``now``): a bar's open plus its interval, its NOMINAL END, read once per bar. Exits are
booked at it (R-AA), so a bar that opens at 23:00 books its exit into the NEXT day's ledger.
``Position.opened_at`` is set to the entry bar's open time (R-AA); its default is the wall
clock, which would make two runs of the same history differ.

**Money.** The entry fee is charged in quote and folded into the entry quote total, which is the
figure the unchanged ``Portfolio`` books the entry against, so ``realised = exit total - entry
total - exit fee`` is the live booking identity. An entry whose quote total, fee included,
exceeds the free quote is not opened (``UNAFFORDABLE``): the live fee is taken from the base
asset, so the sizer never allowed for a quote fee, and an executor that must not re-size
refuses rather than overdraw.

**Deliberately absent.** No cooldown (``Portfolio.start_cooldown`` has no live caller either,
R-X), no trailing stop (nothing places one live), no partial fill, no rounding of any price to
the tick (R-AB) and no re-check of the exchange's filters (the sizer applied the stored ones).
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from enum import Enum

from trading_bot.backtesting.fill_model import (
    EntryBooking,
    EntryFill,
    EntryOutcome,
    FillParameters,
    ProtectiveFill,
    book_entry,
    book_exit,
    fill_close,
    fill_entry,
    fill_protective,
)
from trading_bot.core.assessment import EntryIntent, RiskAssessment
from trading_bot.core.enums import PositionSide, ProtectionState
from trading_bot.core.models import Candle, Fee, Position, Signal
from trading_bot.core.portfolio import Portfolio
from trading_bot.utils.helpers import timeframe_to_ms
from trading_bot.utils.logger import get_logger

__all__ = [
    "Clock",
    "EntryAttempt",
    "EntryResult",
    "ExecutorCounts",
    "SimulatedExecutor",
    "SimulatedExit",
    "SimulatedTrade",
    "trade_log_digest",
    "trade_rows",
]

_log = get_logger(__name__)

#: The simulated instant. In a replay it is :meth:`ReplayStream.now`.
Clock = Callable[[], datetime]

_MILLISECOND = timedelta(milliseconds=1)


class SimulatedExit(str, Enum):
    """Why a simulated position ended."""

    STOP_LOSS = "stop_loss"
    TAKE_PROFIT = "take_profit"
    CLOSE = "close"


class EntryResult(str, Enum):
    """What became of an approved entry."""

    FILLED = "filled"
    #: The next bar's open plus slippage was above the entry limit, so the ``FOK`` was refused.
    REFUSED = "refused"
    #: The next slot was missing, or the data ended, so the ``FOK`` found no bar to fill on.
    EXPIRED = "expired"
    #: The quote total, entry fee included, was more than the free quote.
    UNAFFORDABLE = "unaffordable"


@dataclass(frozen=True)
class EntryAttempt:
    """One approved entry and its outcome. ``price`` is set only when it ``FILLED``."""

    symbol: str
    timeframe: str
    signal_bar_open: datetime
    placed_at: datetime
    entry_limit: Decimal
    result: EntryResult
    detail: str
    #: The open time of the bar the order was settled on, or ``None`` if there was none.
    settled_bar_open: datetime | None
    price: Decimal | None


@dataclass(frozen=True)
class SimulatedTrade:
    """One closed round trip, with the entry fee kept visible (R-W(c)).

    ``realised`` is what ``Portfolio.close_position`` returned: the exit total less the entry
    quote total (the entry fee inside it) less the exit fee. ``entry_fee + exit_fee`` is what
    S3 sums. ``spans_gap`` and ``spans_short_bar`` flag a trade that touched a gap or a
    registered short bar between its entry bar and its exit bar, both included (R-P1).
    """

    symbol: str
    timeframe: str
    signal_bar_open: datetime
    entry_bar_open: datetime
    quantity: Decimal
    entry_limit: Decimal
    entry_price: Decimal
    entry_notional: Decimal
    entry_fee: Decimal
    entry_quote_total: Decimal
    stop_loss: Decimal | None
    take_profit: Decimal | None
    exit_reason: SimulatedExit
    exit_bar_open: datetime
    exit_time: datetime
    exit_price: Decimal
    #: The level a protective exit triggered at, or ``None`` for a ``CLOSE``.
    exit_trigger: Decimal | None
    exit_open_through_trigger: bool
    exit_gross: Decimal
    exit_fee: Decimal
    realised: Decimal
    spans_gap: bool
    spans_short_bar: bool


@dataclass
class ExecutorCounts:
    """What the executor saw, for the run record. A snapshot is a detached copy."""

    dispatched: int = 0
    refused_by_risk: int = 0
    entries_queued: int = 0
    entries_ignored: int = 0
    entries_filled: int = 0
    entries_refused: int = 0
    entries_expired: int = 0
    entries_unaffordable: int = 0
    closes_queued: int = 0
    closes_ignored: int = 0
    exits_stop_loss: int = 0
    exits_take_profit: int = 0
    exits_close: int = 0
    bars_seen: int = 0
    gaps_seen: int = 0
    short_bars_seen: int = 0


@dataclass
class _Track:
    """One pair's bar-to-bar bookkeeping."""

    last_open: datetime | None = None
    gaps: int = 0
    shorts: int = 0


@dataclass(frozen=True)
class _PendingEntry:
    intent: EntryIntent
    timeframe: str
    signal_bar_open: datetime
    #: The signal bar's close time, which is what a live ``Position.entry_bar_time`` holds.
    signal_bar_close: datetime
    #: The signal bar's NOMINAL end: the instant the order goes in.
    placed_at: datetime


@dataclass(frozen=True)
class _QueuedClose:
    #: The signal bar's nominal end. A settling bar that opens later than this followed a gap.
    queued_at: datetime


@dataclass(frozen=True)
class _Held:
    """What the executor remembers of an open position beyond what ``Position`` carries."""

    intent: EntryIntent
    timeframe: str
    signal_bar_open: datetime
    entry_bar_open: datetime
    booking: EntryBooking
    requested_legs: bool
    gaps_before: int
    shorts_before: int


class SimulatedExecutor:
    """Sequences the fill model against a ``Portfolio``; satisfies ``Dispatcher``.

    :param portfolio: the unchanged live ledger. The executor opens and closes positions on it
        through ``open_position`` and ``close_position``, and nothing else writes it.
    :param params: the three fill percents.
    :param clock: the simulated instant; read once per bar, and never a wall clock.
    """

    def __init__(self, *, portfolio: Portfolio, params: FillParameters, clock: Clock) -> None:
        self._portfolio = portfolio
        self._params = params
        self._clock = clock
        self._tracks: dict[str, _Track] = {}
        self._pending: dict[str, _PendingEntry] = {}
        self._closes: dict[str, _QueuedClose] = {}
        self._held: dict[str, _Held] = {}
        self._trades: list[SimulatedTrade] = []
        self._attempts: list[EntryAttempt] = []
        self._counts = ExecutorCounts()

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
        """What was still in flight: open positions, pending entries and queued closes."""
        return {
            "open_positions": tuple(sorted(self._held)),
            "pending_entries": tuple(sorted(self._pending)),
            "queued_closes": tuple(sorted(self._closes)),
        }

    # -- the signal side --------------------------------------------------------
    async def dispatch(self, signal: Signal, assessment: RiskAssessment, candle: Candle) -> None:
        """Record an approved entry or ``CLOSE`` for a later bar. Never fills anything."""
        self._counts.dispatched += 1
        intent = assessment.intent
        if not assessment.approved or intent is None:
            self._counts.refused_by_risk += 1
            return
        step = timedelta(milliseconds=timeframe_to_ms(candle.timeframe))
        placed_at = candle.open_time + step
        symbol = intent.symbol
        if isinstance(intent, EntryIntent):
            if symbol in self._pending or symbol in self._held:
                self._counts.entries_ignored += 1
                _log.warning(
                    "Entry for %s ignored: an entry is pending or a position is held",
                    symbol,
                    extra={"signal_action": signal.action.value},
                )
                return
            self._pending[symbol] = _PendingEntry(
                intent=intent,
                timeframe=candle.timeframe,
                signal_bar_open=candle.open_time,
                signal_bar_close=candle.close_time,
                placed_at=placed_at,
            )
            self._counts.entries_queued += 1
            return
        if symbol not in self._held or symbol in self._closes:
            self._counts.closes_ignored += 1
            _log.warning("CLOSE for %s ignored: no open position, or one is already queued", symbol)
            return
        self._closes[symbol] = _QueuedClose(queued_at=placed_at)
        self._counts.closes_queued += 1

    # -- the candle side --------------------------------------------------------
    async def __call__(self, candle: Candle) -> None:
        """Settle what this bar settles, then stamp every open position."""
        now = self._clock()
        track = self._tracks.setdefault(candle.symbol, _Track())
        gaps_before, shorts_before = track.gaps, track.shorts
        self._observe(track, candle)
        self._settle_entry(candle, gaps_before=gaps_before, shorts_before=shorts_before)
        self._settle_exit(candle, now=now)
        self._stamp(now)

    def finish(self) -> None:
        """The data has ended: a pending entry has no next bar, so it EXPIRES. Idempotent.

        An open position and a queued ``CLOSE`` are left as they are and reported by
        :attr:`unsettled`; a run that ends mid-trade has not decided that trade.
        """
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
        booking = book_entry(quantity=intent.quantity, price=fill.price, params=self._params)
        if booking.quote_total > self._portfolio.free_quote:
            self._counts.entries_unaffordable += 1
            self._attempts.append(
                self._attempt(
                    pending,
                    EntryResult.UNAFFORDABLE,
                    f"the quote total {booking.quote_total} is more than the free quote "
                    f"{self._portfolio.free_quote}",
                    settled_on=candle,
                )
            )
            return
        # UNKNOWN at construction, as the live executor builds every position; the pass at the
        # end of this call promotes it. opened_at is the entry bar's open, never the wall clock.
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
            stop_loss=intent.levels.stop_loss,
            take_profit=intent.levels.take_profit,
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
            requested_legs=(
                intent.levels.stop_loss is not None or intent.levels.take_profit is not None
            ),
            gaps_before=gaps_before,
            shorts_before=shorts_before,
        )

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

    def _settle_exit(self, candle: Candle, *, now: datetime) -> None:
        symbol = candle.symbol
        held = self._held.get(symbol)
        position = self._portfolio.positions.get(symbol)
        if held is None or position is None:
            return
        stop, target = position.stop_loss, position.take_profit
        queued = self._closes.get(symbol)
        if queued is None:
            protective = fill_protective(
                stop_loss=stop, take_profit=target, bar=candle, params=self._params
            )
            if protective is not None:
                self._exit_protective(candle, held, protective, now=now)
            return
        followed_a_gap = candle.open_time > queued.queued_at
        if followed_a_gap and stop is not None and candle.open <= stop:
            # Protection stayed in force across the gap, and the open is already through the stop.
            gapped = fill_protective(
                stop_loss=stop, take_profit=None, bar=candle, params=self._params
            )
            if gapped is None:  # pragma: no cover - low <= open <= stop, so it always fires
                raise RuntimeError(f"{symbol}: an open at or below the stop did not trigger it")
            self._exit_protective(candle, held, gapped, now=now)
            return
        self._book_exit(
            candle,
            held,
            reason=SimulatedExit.CLOSE,
            price=fill_close(bar=candle, params=self._params),
            trigger=None,
            through=False,
            now=now,
        )

    def _exit_protective(
        self, candle: Candle, held: _Held, fill: ProtectiveFill, *, now: datetime
    ) -> None:
        self._book_exit(
            candle,
            held,
            reason=SimulatedExit(fill.reason.value),
            price=fill.price,
            trigger=fill.trigger,
            through=fill.open_through_trigger,
            now=now,
        )

    def _book_exit(
        self,
        candle: Candle,
        held: _Held,
        *,
        reason: SimulatedExit,
        price: Decimal,
        trigger: Decimal | None,
        through: bool,
        now: datetime,
    ) -> None:
        symbol = candle.symbol
        position = self._portfolio.positions[symbol]
        booking = book_exit(quantity=position.quantity, price=price, params=self._params)
        realised = self._portfolio.close_position(
            symbol,
            exit_quote_total=booking.gross,
            now=now,
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
                stop_loss=held.intent.levels.stop_loss,
                take_profit=held.intent.levels.take_profit,
                exit_reason=reason,
                exit_bar_open=candle.open_time,
                exit_time=now,
                exit_price=price,
                exit_trigger=trigger,
                exit_open_through_trigger=through,
                exit_gross=booking.gross,
                exit_fee=booking.fee,
                realised=realised,
                spans_gap=track.gaps > held.gaps_before,
                spans_short_bar=track.shorts > held.shorts_before,
            )
        )
        del self._held[symbol]
        self._closes.pop(symbol, None)
        if reason is SimulatedExit.STOP_LOSS:
            self._counts.exits_stop_loss += 1
        elif reason is SimulatedExit.TAKE_PROFIT:
            self._counts.exits_take_profit += 1
        else:
            self._counts.exits_close += 1

    def _stamp(self, now: datetime) -> None:
        for symbol, held in self._held.items():
            position = self._portfolio.positions.get(symbol)
            if position is None:
                continue
            state = (
                ProtectionState.ACTIVE if held.requested_legs else ProtectionState.ABSENT_BY_DESIGN
            )
            position.record_reconciliation(protection=state, at=now)


# --------------------------------------------------------------------------
# The trade log
# --------------------------------------------------------------------------
def _cell(value: object) -> object:
    """One field as it is written to the log: exact, and the same on every run."""
    if value is None or isinstance(value, bool):
        return value
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, str):
        return value
    raise TypeError(f"a trade-log cell cannot be a {type(value).__name__}")


def trade_rows(trades: Sequence[SimulatedTrade]) -> list[dict[str, object]]:
    """The trade log as rows of plain values: a ``Decimal`` as its exact ``str``, a time ISO."""
    return [
        {field.name: _cell(getattr(trade, field.name)) for field in dataclasses.fields(trade)}
        for trade in trades
    ]


def trade_log_digest(trades: Sequence[SimulatedTrade]) -> str:
    """The SHA-256 of the trade log, one canonical JSON line per trade.

    Two runs of the same history, configuration and code must return the same digest, which
    is the determinism test. A ``Decimal`` is hashed as its exact ``str``, so a run that
    differed only in a trailing zero would differ here.
    """
    lines = (json.dumps(row, sort_keys=True, separators=(",", ":")) for row in trade_rows(trades))
    return hashlib.sha256("\n".join(lines).encode("utf-8")).hexdigest()
