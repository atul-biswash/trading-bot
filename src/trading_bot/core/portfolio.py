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
#: **``ACTIVE`` is the one member admitted against that default, and it is
#: admitted because it is EARNED rather than assumed.** Every other state is
#: trusted or not on the strength of what nobody checked; ``ACTIVE`` is
#: returned only when every requested leg was found resting at the venue, at
#: its requested trigger, for the requested quantity, under the requested list
#: id, with nothing executed. It is the only member whose truth is measured, so
#: it is the only one that may carry the expensive error direction.
#:
#: **What it unblocks is TRADING, not a defect.** Left out, a correctly
#: protected position counts uncomputable, which refuses every entry
#: portfolio-wide -- the interlock firing on the healthy path. Q-C section 7's
#: site 3 was already closed by the ``DIVERGED`` write plus this whitelist's
#: default, one commit earlier.
#:
#: **MEMBERSHIP HERE SAYS NOTHING ABOUT WHEN THE PROTECTION WAS LAST
#: VERIFIED**, and admitting ``ACTIVE`` is what makes that matter. The check in
#: :meth:`Portfolio.committed_risk` reads this set and does not read
#: ``last_reconciled_at``: before this member existed every reconciler-written
#: state was untrusted, so stale and fresh both counted uncomputable and the
#: omission was invisible. Now a position classified ``ACTIVE`` and never
#: re-read -- a dropped feed, a budget-skipped pass -- stays trusted
#: indefinitely and is priced off a stop that may no longer rest.
#: ``risk.max_position_staleness_s`` is the guarantee that would close it and
#: **it has no reader**; see ``docs/NEXT_MILESTONE.md`` item 14.
_TRUSTED_PROTECTION = frozenset({ProtectionState.ABSENT_BY_DESIGN, ProtectionState.ACTIVE})


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


def _ledger_is_stale(covered: date | None, now_day: date) -> bool:
    """Whether a ledger covering ``covered`` is out of date at ``now_day``.

    **Strictly later, not merely different, and that is the whole decision.**
    A ``now`` that moves *backwards* across midnight -- an NTP correction, or an
    out-of-order replay -- makes the two days differ without the ledger being
    stale at all. Read as "different", the write path resets a day of booked
    realised facts and back-dates what survives, and the read path reports zero
    for a day whose loss is still recorded, releasing the daily-loss halt on a
    loss that really happened. Read as "later", the same backwards ``now``
    accrues into the day the ledger already covers and reads that day's figure:
    the wrong day, conservatively, rather than no day at all.

    ``covered is None`` is the first accrual of a run, before any day is
    recorded, and it is not an edge case to tolerate but the guard that makes
    the comparison legal -- ``date > None`` raises ``TypeError``.

    One definition for both paths, for the reason :func:`_utc_day` is one: the
    comparison direction is now the thing that could drift between the read and
    the write of the same field, and it is exactly the thing being fixed here.
    """
    return covered is None or now_day > covered


class Portfolio(BaseModel):
    """Open positions, free balance, and the limit state the risk rules read.

    Constructed by the composition root and passed to
    :meth:`~trading_bot.core.interfaces.RiskManager.evaluate` per call. The risk
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

    #: Symbols this bot may not enter because an order list of **ours** is still
    #: working at the venue, mapped to the reason an operator needs. Recorded at
    #: boot by ``engine.modes._snapshot_live_order_lists``.
    #:
    #: **NOT ``unmanaged_holdings``, and the separation is load-bearing rather
    #: than tidy.** That dict is summed by :meth:`equity` and enumerated by
    #: :meth:`marked_symbols`, so writing a symbol into it makes the whole bot
    #: depend on being able to price that symbol -- and ``NO_MARK_PRICE``
    #: refuses **portfolio-wide**, not just for the symbol it could not price.
    #: A blocking mechanism that can halt every pair is the wrong instrument for
    #: "do not enter this one".
    #:
    #: **A ``str`` value, not a quantity, because there is no honest quantity to
    #: store.** The bot holds no ``Position`` for the list -- that is the whole
    #: problem -- and the enumeration carries identity only:
    #: ``OrderListEntry`` is ``{symbol, order_id, client_order_id}`` with no
    #: size. What the operator needs is which list, not how much.
    #:
    #: **Immutable for the process lifetime, by the same convention as
    #: ``unmanaged_holdings``**: recorded once at boot, and cleared only by
    #: cancelling the list at the venue and restarting.
    blocked_symbols: dict[str, str] = Field(default_factory=dict)

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

    def is_blocked(self, symbol: str) -> bool:
        """Whether an order list of ours is still working on ``symbol``.

        Deliberately NOT reflected in :meth:`marked_symbols` or :meth:`equity`:
        see :attr:`blocked_symbols` for why a blocking mechanism that can halt
        every pair is the wrong instrument for one symbol.
        """
        return symbol in self.blocked_symbols

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

        **Nothing is written until everything that can fail has run** -- the
        discipline :meth:`open_position` states from the other side. The
        arithmetic raises on a ``float`` operand and ``now`` must be
        timezone-aware, so both run while the ledger is still untouched; the
        credit then goes first, because ``free_quote`` carries ``ge=0``. Note
        the two methods look opposite -- one debits first, one credits first --
        and are the same rule: in both, the fallible step precedes the
        irreversible one. Reaching any of these raises is a bug rather than a
        market state, which is exactly why it must not half-apply: a position
        removed with its proceeds unaccounted for is a ledger that has already
        stopped matching the account.

        **THE DELETION IS LAST, AND UNTIL M5h IT WAS NOT.** This paragraph used
        to call ``free_quote`` *"the one commit step that can still raise"*, and
        that premise was false: :meth:`record_realised_pnl` can raise too --
        ``Money`` rejects a non-finite total, and the accrual's own docstring
        depends on exactly that. It ran AFTER ``del self.positions[symbol]``, so
        a raise there left the proceeds credited, the position gone and the loss
        unbooked.

        **What made that unrecoverable is retryability, not the write itself.**
        ``reconcile_open_positions`` iterates ``portfolio.open_positions``, so a
        symbol removed from ``positions`` is never visited again -- there is no
        later pass that could notice the omission and no state from which to
        retry. A permanent, silent under-report, which is the one direction a
        risk control may not err in. With the deletion last, the same failure
        leaves the position PRESENT and the next pass can try again.

        **The credit stays first, deliberately, and the alternative was
        rejected on its error direction.** Moving the accrual ahead of the
        credit would protect against a non-finite total, which is barely
        reachable -- but it would write ``realised_pnl`` before ``free_quote``
        raises, and ``free_quote`` raising IS reachable: an over-large ``fee``
        or a negative ``exit_price`` both drive ``proceeds`` below zero, and
        both are covered rows in
        ``test_a_failed_close_leaves_the_ledger_untouched``. So accrual-first
        would touch the ledger on the failures that actually happen in order to
        guard one that does not.

        **The residual, stated rather than hidden.** If the accrual raises after
        the credit lands, ``free_quote`` has been credited and the position
        survives -- so a retry would credit it twice. That is accepted: it needs
        a non-finite total to reach, the position surviving makes the failure
        visible and repeating, and the alternative is losing the position
        outright. ``CLAUDE.md``'s rule is *"the fallible step precedes the
        irreversible one ... Everything that can raise runs first, so a failure
        leaves the object exactly as it was"*; with three writes and two of them
        fallible, no ordering satisfies it completely, and this is the one whose
        worst case is recoverable.
        """
        position = self.positions.get(symbol)
        if position is None:
            return Decimal(0)

        pnl = position.unrealized_pnl(exit_price) - fee
        proceeds = self.free_quote + position.quantity * exit_price - fee
        _require_aware("now", now)

        self.free_quote = proceeds
        self.record_realised_pnl(pnl, now=now)
        # LAST, because it is the only irreversible step: nothing revisits a
        # symbol that has left `positions`.
        del self.positions[symbol]
        return pnl

    def equity(self, marks: Mapping[str, Decimal]) -> Decimal:
        """Total portfolio value in the quote currency.

        **Three terms, not two.** Free quote balance, **plus** the
        mark-to-market value of every open position, **plus** the
        mark-to-market value of every unmanaged base holding -- the definition
        ``size_position`` documents, and the difference between "2% of equity
        per position" meaning a stable size and one that shrinks as capital
        deploys.

        **The third term is easy to miss and this docstring used to omit it.**
        An unmanaged holding is counted for the reason the body's own comment
        gives: it is the account's rather than the bot's, but it is still the
        account's value, and equity is the denominator of every sizing decision
        and of the daily-loss threshold.

        Note the asymmetry with the boot step that records one.
        ``engine.modes._snapshot_unmanaged_holdings`` stores ``balance.total``
        into :attr:`unmanaged_holdings`, which is what this sums, while
        deciding materiality on ``balance.free``. Both are right and they
        answer different questions: equity asks what the account **owns**,
        where dust asks what it could **sell**.

        ``marks`` must price every open position **and every unmanaged
        holding** -- :meth:`marked_symbols` returns exactly that union, which is
        why it exists. A missing mark raises rather than defaulting to the entry
        price or to zero: both would silently misstate equity, and equity is the
        denominator of every sizing and daily-loss decision. The caller (the
        manager) checks first and turns the condition into a representable
        refusal, so these raises are a contract violation, not a market state.

        Raises:
            ValueError: if an open position cannot be marked, if an unmanaged
                holding cannot be marked, or if a position is not ``LONG``.
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
    def realised_today(self, now: datetime) -> Decimal:
        """Realised P&L for the UTC day containing ``now``. Negative is a loss.

        **Derived, never assigned.** A ledger whose :attr:`pnl_date` has gone
        stale reads as zero for the new day without being rewritten, so this is
        a read in the sense the port docstring claims: it cannot change what a
        later caller sees. Resetting belongs to :meth:`record_realised_pnl`,
        which is a write already, and which is what a bot that trades nothing
        overnight never reaches -- so the derivation, not the reset, is what
        releases yesterday's daily-loss halt.

        Zero is returned only for a **later** day. A ``now`` that has moved
        backwards still reads the recorded figure: answering zero there would
        hide a booked loss from the daily-loss check and permit an entry the
        account is halted for.
        """
        if _ledger_is_stale(self.pnl_date, _utc_day("now", now)):
            return Decimal(0)
        return self.realised_pnl

    def record_realised_pnl(self, amount: Decimal, *, now: datetime) -> None:
        """Accrue ``amount`` of realised P&L into the day containing ``now``.

        Called by execution when a position closes. Negative for a loss.

        **This is the only place the day rolls**, and the roll is lazy rather
        than scheduled: a bot that trades nothing overnight would otherwise
        carry yesterday's halt into a new day with nothing to poke it.
        :meth:`realised_today` reaches the same outcome on the read side
        without writing, by deriving it -- which is what makes it usable here
        as the base this accrual adds to, so the roll's effect has one
        expression rather than two. Note the consequence: a public read is
        load-bearing for a write, so a side effect added to
        :meth:`realised_today` would break both.

        **Nothing is written until everything that can fail has run.** The
        addition raises on a ``float``, a ``numpy.float64`` or a ``str``
        operand, and the assignment raises on a non-finite result -- ``Money``
        rejects those independently of the float guard. Both run first, so a
        failed accrual leaves the ledger exactly as it was. Committing the roll
        first, as this method did until M5b, left a zeroed new day that nothing
        was ever booked into: the previous day's realised facts destroyed by a
        write that then failed.

        ``pnl_date`` moves **only** when the ledger is stale. Assigning it
        unconditionally would back-date on a ``now`` that has moved backwards,
        which is the defect :func:`_ledger_is_stale` exists to prevent.
        """
        today = _utc_day("now", now)
        rolled = _ledger_is_stale(self.pnl_date, today)
        total = self.realised_today(now) + amount

        self.realised_pnl = total
        if rolled:
            self.pnl_date = today

    @staticmethod
    def _binding_stop(position: Position) -> Decimal | None:
        """The stop that actually protects ``position``, or ``None`` if none does.

        **Committed risk prices off what RESTS AT THE VENUE.** That is the rule;
        the set of resting levels is a consequence of it rather than a
        preference. Q-C section 3 fixes the order list at three legs -- the
        working ``LIMIT``, the ``STOP_LOSS`` and the ``TAKE_PROFIT`` -- so today
        that set is exactly ``{stop_loss}``. When venue-side trailing lands, a
        trailing level starts resting and becomes eligible here **without
        re-opening this decision**.

        ``trailing_stop`` is therefore excluded, and the exclusion is about
        where the level lives rather than about which is nearer. It is written
        by ``RiskManager.advance_trailing_stop`` and read by ``should_exit``;
        nothing places or amends an order for it, and Q-C section 5 retains the
        field "pending the trailing milestone".

        **The asymmetry with ``should_exit`` is deliberate: the two answer
        different questions.** ``should_exit`` asks whether to exit *now*, so it
        prefers the trail, which is the level a live bot would act on.
        ``_binding_stop`` asks what happens if the bot **stops running** -- and
        only the second is what committed risk means. A trailed position whose
        process dies is protected at ``stop_loss``, not at the trail.

        This supersedes the earlier reasoning that reading ``stop_loss``
        directly "would price off a level no longer operative and OVERSTATE".
        That is correct about its mechanism and wrong about this system: it
        assumed the trailing level is operative, and it landed before the design
        that would make it so. Overstating is also the error this codebase
        chooses -- Q-C section 7: the error that refuses an entry costs a missed
        trade, the error that trusts a stop that is not there costs the
        position.

        **Q-C section 7's site-3 defect is NOT closed here.** A position whose
        *requested* ``stop_loss`` was found not to be resting still prices off
        it, because that level is non-``None`` by definition -- that is how the
        divergence was detected. Its discriminator is ``protection``, not level
        selection, and closing it remains M5d's.
        """
        return position.stop_loss

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
        committed: Decimal,
    ) -> bool:
        """Whether today's realised loss *plus committed risk* has breached the cap.

        An account 4% down realised, holding a position whose resting stop
        commits another 2%, is not "4% down" for the purposes of a 5% cap. A
        limit that counted only money already gone would break its own promise
        **structurally**: it would permit opening position N+1 while position
        N's committed loss was still unbooked, and it would do so on a perfect
        feed rather than merely under polling.

        ``committed`` is supplied rather than computed, for the same reason
        ``equity`` is: both are derived from the same ``marks`` mapping by the
        caller, and computing one here while taking the other as an argument
        was the asymmetry that made ``committed_risk`` run twice per
        evaluation. The caller keeps the uncomputable *count* from that one
        computation and checks it upstream, before the limits are consulted at
        all, because an inability to compute is not a limit's verdict.

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
