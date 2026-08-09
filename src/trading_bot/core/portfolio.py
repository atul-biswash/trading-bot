"""Portfolio state -- the account the risk manager reads and execution updates.

Design notes
------------
**State lives here; policy lives in ``risk/``.** :class:`Portfolio` holds what
the account *is* (open positions, free quote balance, the day's realised P&L,
per-symbol cooldowns); ``RiskManager`` holds what the operator *configured* and
decides what to do about it. Splitting them that way means the manager stays a
reconstructible, I/O-free policy object, persistence in a later phase has one
object to serialise instead of reaching into a risk component, and backtest and
paper modes reuse the same ledger rather than growing a second one.

**Mutable, by the same rule that makes ``Position`` mutable.** Value objects in
this system are frozen; objects that accumulate over a trade's -- or a run's --
life are not. A frozen snapshot rebuilt per signal would also have nowhere to
record "cooldown started at T", which is a write.

``validate_assignment`` is on, so the ``Money`` guard applies to *assignment*
and not just construction: ``portfolio.free_quote = 1.5`` raises instead of
quietly seeding the account with a binary float. Plain pydantic models only
validate at construction, which leaves exactly the leak path the guard exists
to close.

**Nothing here reads a clock.** Every time-dependent method takes ``now``
explicitly, which keeps the ledger a pure function of its inputs and leaves one
component -- the manager -- knowing what time it is. That is what makes the
daily-loss and cooldown tests hermetic without patching anything. A naive
``datetime`` is rejected rather than assumed to be UTC: guessing a timezone is
how a day boundary silently moves by hours.

**No mark prices are stored.** :meth:`Portfolio.equity` takes them per call.
The alternative -- holding a ``MarketDataProvider`` -- would be an import cycle
(``core.interfaces`` imports this module) and would put I/O behind an attribute
read; passing them in keeps equity a pure calculation over numbers.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import TYPE_CHECKING

from pydantic import BaseModel, ConfigDict, Field

from trading_bot.core.enums import PositionSide, ProtectionState
from trading_bot.core.models import Money, Position

if TYPE_CHECKING:  # pragma: no cover - typing only
    from collections.abc import Mapping

#: Divisor for the whole-percent config fields (``5.0`` means 5%).
_PERCENT = Decimal(100)

#: Protection states in which a position's recorded stop level may be trusted
#: to actually rest at the exchange.
#:
#: **A whitelist, and the direction is the opposite of ``OrderStatus``'s -- on
#: purpose.** There, a blacklist of terminal states makes a new member default
#: to *open*, so the error costs one wasted round trip. Here, a new member
#: defaulting to *trusted* would make committed risk **understate**, which is
#: the error that lets an entry through on the strength of protection that does
#: not exist. Each field takes the direction whose wrong answer is the cheap
#: one, and for this field that means an unclassified state is not trusted.
#:
#: **The ``protection`` half of this test is FIXTURE-ONLY today.** Nothing in
#: ``src/`` populates ``Position.protection`` until the reconciler exists, so
#: today the discriminating condition in practice is the absent stop level.
#: This does **not** close the defect it anticipates -- a position whose
#: requested stop was found not to be resting still prices off that stop until
#: a writer sets a state outside this set.
_TRUSTED_PROTECTION = frozenset({ProtectionState.ABSENT_BY_DESIGN})


def _require_aware(name: str, moment: datetime) -> datetime:
    """Reject a naive ``datetime``.

    A naive value would be interpreted as local time by ``astimezone``, moving
    the UTC day boundary by the host's offset -- a daily-loss halt that resets
    at the wrong hour, on a machine whose timezone nobody thought about.
    """
    if moment.tzinfo is None or moment.tzinfo.utcoffset(moment) is None:
        raise ValueError(f"{name} must be timezone-aware, got naive {moment!r}")
    return moment


def _utc_day(name: str, moment: datetime) -> date:
    """The UTC calendar day ``moment`` falls on, rejecting a naive value.

    One definition, shared by the accrual path and the read path. Two copies of
    ``astimezone(timezone.utc).date()`` would be a duplicated predicate -- they
    answer the same question, "which day is this?", and an edit that reached one
    and missed the other would let a read disagree with the write it describes.
    """
    return _require_aware(name, moment).astimezone(timezone.utc).date()


class Portfolio(BaseModel):
    """Open positions, free balance, and the limit state the risk rules read.

    Constructed by the composition root and passed to
    :meth:`~trading_bot.core.interfaces.RiskManager.approve` per call. The risk
    manager only ever *reads* it; the mutators below are called by execution
    when an order actually fills.
    """

    model_config = ConfigDict(validate_assignment=True)

    #: Currency every balance, P&L and equity figure here is denominated in.
    quote_asset: str = "USDT"
    #: Unencumbered quote balance -- what an order can actually spend. Never
    #: negative: with ``validate_assignment`` on, an over-spend raises here
    #: rather than leaving the ledger describing an account that cannot exist.
    free_quote: Money = Field(Decimal(0), ge=0)
    #: Open positions by symbol. One position per symbol: this system does not
    #: pyramid, and a second entry would have to merge or overwrite.
    positions: dict[str, Position] = Field(default_factory=dict)
    #: Realised P&L accrued on :attr:`pnl_date`. Negative is a loss.
    realised_pnl: Money = Decimal(0)
    #: UTC date :attr:`realised_pnl` belongs to; ``None`` until the first accrual.
    pnl_date: date | None = None
    #: Per-symbol instants before which no new entry is allowed.
    cooldown_until: dict[str, datetime] = Field(default_factory=dict)
    #: Material base holdings the account had at boot that this bot did not
    #: open, keyed by the **symbol** they are priced against -- so the same
    #: ``marks`` mapping that values positions values these too. The quantity is
    #: the **total** balance, free plus locked, because equity asks what the
    #: account owns.
    #:
    #: **Counted toward equity, never adopted as positions, and their symbols
    #: refuse entries.** Adopting them would manufacture a stopless position at
    #: every boot and would eventually have the bot sell an asset a human
    #: bought; ignoring them entirely would let a ``BUY`` pass
    #: ``ALREADY_IN_POSITION`` and pyramid onto the holding, sized against an
    #: equity that excludes it.
    #:
    #: **Immutable for the process lifetime -- by convention, not enforcement.**
    #: ``validate_assignment`` re-validates a *reassignment* of this field but
    #: cannot see an in-place mutation of the dict, so nothing here stops a
    #: caller adding a key. The snapshot is taken once, at boot, before any
    #: ``Position`` exists, and that timing is the correctness argument: taken
    #: later it would count base held by positions the bot opened, which
    #: ``equity`` would then double-count and the refusal would mislabel.
    unmanaged_holdings: dict[str, Money] = Field(default_factory=dict)

    # -- positions ----------------------------------------------------------
    @property
    def open_positions(self) -> list[Position]:
        """Positions with a non-zero size on a real side (never ``FLAT``)."""
        return [position for position in self.positions.values() if position.is_open]

    @property
    def position_count(self) -> int:
        """How many positions count against ``max_open_positions``."""
        return len(self.open_positions)

    def has_position(self, symbol: str) -> bool:
        """Whether ``symbol`` already has an open position."""
        position = self.positions.get(symbol)
        return position is not None and position.is_open

    def has_unmanaged_holding(self, symbol: str) -> bool:
        """Whether ``symbol``'s base asset carries a holding the bot did not open."""
        return symbol in self.unmanaged_holdings

    def marked_symbols(self) -> list[str]:
        """Every symbol ``equity`` needs a mark for, open positions first.

        Both open positions and unmanaged holdings are valued, so both must be
        priced. Returned in a stable order and de-duplicated, so a caller
        reporting which symbols it could not price reports them deterministically.
        """
        symbols: list[str] = []
        seen: set[str] = set()
        for symbol in [p.symbol for p in self.open_positions] + list(self.unmanaged_holdings):
            if symbol not in seen:
                seen.add(symbol)
                symbols.append(symbol)
        return symbols

    def open_position(self, position: Position, *, cost: Decimal) -> None:
        """Record ``position`` and debit ``cost`` from the free quote balance.

        **The debit happens first, and the order is load-bearing.**
        ``free_quote`` carries ``ge=0`` under ``validate_assignment``, so an
        over-spend raises on that assignment. Debiting first means such a raise
        leaves the ledger untouched; inserting first would leave a position in
        the book with its cost unaccounted for -- a ledger that has already
        stopped matching the account. Affordability is checked upstream by the
        risk manager, so reaching the raise is a bug rather than a market state,
        which is exactly why it must not half-apply.

        ``cost`` is passed rather than derived from ``entry_price x quantity``
        because the two are not the same number once fees exist, and the ledger
        must track what actually left the balance.
        """
        self.free_quote = self.free_quote - cost
        self.positions[position.symbol] = position

    def close_position(
        self,
        symbol: str,
        *,
        exit_price: Decimal,
        now: datetime,
        fee: Decimal = Decimal(0),
    ) -> Decimal:
        """Close ``symbol``, credit the proceeds, and book the realised P&L.

        Returns the realised P&L (negative for a loss), or ``Decimal(0)`` when
        there was no position to close -- which is a normal outcome, not an
        error, since a `CLOSE` can arrive for a symbol the bot does not hold.

        **``fee`` is subtracted from the realised P&L**, because the reason the
        ledger holds realised facts only is that it must match an exchange
        statement -- and a statement is net of fees. A gross-only close would
        fail the test that rule sets for itself.

        Accrual goes through :meth:`record_realised_pnl` rather than assigning
        :attr:`realised_pnl` directly, so there is one accrual path and one day
        roll. Cooldown is **not** started here: ``cooldown_minutes`` is
        configuration, and this object holds none.
        """
        position = self.positions.pop(symbol, None)
        if position is None:
            return Decimal(0)

        pnl = position.unrealized_pnl(exit_price) - fee
        self.free_quote = self.free_quote + position.quantity * exit_price - fee
        self.record_realised_pnl(pnl, now=now)
        return pnl

    def equity(self, marks: Mapping[str, Decimal]) -> Decimal:
        """Total portfolio value in the quote currency.

        Free quote balance **plus** the mark-to-market value of every open
        position -- the definition ``size_position`` documents, and the
        difference between "2% of equity per position" meaning a stable size and
        one that shrinks as capital deploys.

        ``marks`` must price every open position. A missing mark raises rather
        than defaulting to the entry price or to zero: both would silently
        misstate equity, and equity is the denominator of every sizing and
        daily-loss decision. The caller (the manager) checks first and turns the
        condition into a representable refusal, so this raise is a contract
        violation, not a market state.

        Raises:
            ValueError: if a position cannot be marked, or is not ``LONG``.
        """
        total = self.free_quote
        for position in self.open_positions:
            if position.side is not PositionSide.LONG:
                raise ValueError(
                    f"cannot value a {position.side.value} position in {position.symbol}: "
                    "spot holdings are long-only"
                )
            mark = marks.get(position.symbol)
            if mark is None:
                raise ValueError(
                    f"no mark price for open position {position.symbol}; equity is unknown"
                )
            total += position.quantity * mark
        for symbol, quantity in self.unmanaged_holdings.items():
            # An unmanaged holding is the account's, not the bot's, but it is
            # still the account's value -- and equity is the denominator of
            # every sizing decision and of the daily-loss threshold.
            mark = marks.get(symbol)
            if mark is None:
                raise ValueError(f"no mark price for unmanaged holding {symbol}; equity is unknown")
            total += quantity * mark
        return total

    # -- daily realised P&L -------------------------------------------------
    def _roll_day(self, now: datetime) -> None:
        """Reset the ledger if ``now`` falls on a different UTC day than it covers.

        Rolled lazily, on the accrual path, rather than by a scheduled reset. A
        bot that trades nothing overnight would otherwise carry yesterday's halt
        into a new day and refuse to trade until something happened to poke it
        -- and nothing would. :meth:`realised_today` reaches the same outcome
        without a write, by deriving it.
        """
        today = _utc_day("now", now)
        if self.pnl_date != today:
            self.realised_pnl = Decimal(0)
            self.pnl_date = today

    def realised_today(self, now: datetime) -> Decimal:
        """Realised P&L for the UTC day containing ``now``. Negative is a loss.

        **Derived, never assigned.** A ledger whose :attr:`pnl_date` has gone
        stale reads as zero for the new day without being rewritten, so this is
        a read in the sense the port docstring claims: it cannot change what a
        later caller sees. Resetting belongs to :meth:`record_realised_pnl`,
        which is a write already, and which is what a bot that trades nothing
        overnight never reaches -- so the derivation, not the reset, is what
        releases yesterday's daily-loss halt.
        """
        return self.realised_pnl if self.pnl_date == _utc_day("now", now) else Decimal(0)

    def record_realised_pnl(self, amount: Decimal, *, now: datetime) -> None:
        """Accrue ``amount`` of realised P&L into the day containing ``now``.

        Called by execution when a position closes. Negative for a loss.
        """
        self._roll_day(now)
        self.realised_pnl = self.realised_pnl + amount

    @staticmethod
    def _binding_stop(position: Position) -> Decimal | None:
        """The stop that actually protects ``position``, or ``None`` if none does.

        **The tie-break is the one ``should_exit`` uses -- the candidate set is
        not.** ``should_exit`` maxes over the stops that have *triggered* at a
        given price; there is no price here and no trigger, so this maxes over
        the stops that are *present*. Reusing the triggered set literally would
        return ``None`` for every healthy position and report a committed risk
        of zero, which is the exact inversion the uncomputable count exists to
        prevent.

        Reading ``stop_loss`` directly instead would price a trailed position
        off a level that is no longer operative, and would **overstate** --
        refusing entries for risk that is not there.
        """
        levels = [
            level for level in (position.stop_loss, position.trailing_stop) if level is not None
        ]
        if not levels:
            return None
        return max(levels) if position.side is PositionSide.LONG else min(levels)

    def committed_risk(self, marks: Mapping[str, Decimal]) -> tuple[Decimal, int]:
        """Forward loss already committed by resting stops, and what could not be priced.

        Returns ``(total, uncomputable_count)``. ``total`` is negative or zero.

        **Mark-to-stop, never entry-to-stop**, and the reason is basis coherence
        rather than magnitude. The daily-loss check already compares two
        quantities: realised P&L measured *from the start of today to now*, and
        a percentage of equity measured *as of now*. ``(binding_stop - mark)``
        measures *from now, forward to the stop* -- the same anchor, so the
        comparison stays at two bases. ``(binding_stop - entry)`` would measure
        from whenever the position opened, a third window that can span days.
        It would also double-count: the entry-to-mark move is already unrealised
        P&L, so ``equity(now)`` has already reduced the threshold by
        ``limit_percent`` of it on the right-hand side, and entry-to-stop would
        put the same move on the left at full weight. The overlap is
        ``1 + limit_percent``, not ``2x``.

        **An uncomputable position is counted, not silently zeroed.** A position
        whose forward risk cannot be priced contributes ``0`` to a sum, which
        tells the caller that an unprotected position carries *no* forward risk
        -- the exact inverse of the truth. So the count comes back beside the
        total and the caller refuses on it. Whether a non-zero count *should*
        refuse is policy, and lives in the risk manager: this object holds no
        config and does not know whether stops are enabled.
        """
        total = Decimal(0)
        uncomputable = 0
        for position in self.open_positions:
            stop = self._binding_stop(position)
            mark = marks.get(position.symbol)
            if stop is None or mark is None or position.protection not in _TRUSTED_PROTECTION:
                uncomputable += 1
                continue
            # min(0, ...) so a stop already better than the mark commits nothing.
            # Long-only by construction: `equity` raises on any other side.
            total += min(Decimal(0), (stop - mark) * position.quantity)
        return total, uncomputable

    def daily_loss_exceeded(
        self,
        *,
        limit_percent: Decimal,
        equity: Decimal,
        now: datetime,
        marks: Mapping[str, Decimal],
    ) -> bool:
        """Whether today's realised loss *plus committed risk* has breached the cap.

        An account 4% down realised, holding a position whose resting stop
        commits another 2%, is not "4% down" for the purposes of a 5% cap. A
        limit that counted only money already gone would break its own promise
        **structurally**: it would permit opening position N+1 while position
        N's committed loss was still unbooked, and it would do so on a perfect
        feed rather than merely under polling.

        Only the committed *sum* is consumed here. The uncomputable *count* is
        checked upstream, before the limits are consulted at all, because an
        inability to compute is not a limit's verdict.

        ``equity`` is the value *now*, not at the start of the day. That is a
        deliberate approximation with a known direction: after a 5% loss equity
        is 95% of where it started, so a 5% cap sits at 4.75% of the original
        and the halt fires marginally **early**. Erring early is the correct
        posture for a loss limit -- the alternative approximation errs late,
        which is the one that costs money. Exact start-of-day semantics would
        require the ledger to be handed mark prices at the day roll, which can
        fall when no signal is in flight.

        ``realised_pnl`` is untouched by any of this. The committed term lives
        in the check, never in the ledger -- which is what keeps the ledger
        matching an exchange statement.
        """
        committed, _uncomputable = self.committed_risk(marks)
        threshold = -(equity * limit_percent / _PERCENT)
        return self.realised_today(now) + committed <= threshold

    # -- cooldown -----------------------------------------------------------
    def start_cooldown(self, symbol: str, *, now: datetime, minutes: int) -> None:
        """Block new entries in ``symbol`` for ``minutes`` after ``now``.

        Called by execution when a position closes -- the "do not immediately
        re-enter what just stopped you out" rule. ``minutes == 0`` is a
        supported configuration and records nothing, so no entry is ever blocked
        by a zero-length window.
        """
        _require_aware("now", now)
        if minutes <= 0:
            return
        self.cooldown_until[symbol] = now + timedelta(minutes=minutes)

    def cooldown_expiry(self, symbol: str) -> datetime | None:
        """When ``symbol``'s cooldown ends, or ``None`` if it is not cooling down."""
        return self.cooldown_until.get(symbol)

    def in_cooldown(self, symbol: str, now: datetime) -> bool:
        """Whether ``symbol`` is still cooling down at ``now``.

        Expiry is lazy -- a comparison, not a sweep. There is no timer to run
        and no task to leak, and the number of stale keys is bounded by the
        number of symbols traded.
        """
        _require_aware("now", now)
        expiry = self.cooldown_until.get(symbol)
        return expiry is not None and now < expiry
