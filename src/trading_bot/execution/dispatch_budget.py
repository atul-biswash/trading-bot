"""What one dispatch sequence may spend, as a DEADLINE rather than a call count.

**There is no ``max_calls`` here, and its absence is the design.** Three
authorisations assumed a divisor before one was retired by arithmetic:
``max_calls x timeout_s = D`` is **INVARIANT** for every divisor, because
``timeout_s`` was defined as ``D / max_calls``. A count therefore never sized the
reservation -- it only decided how the same ``D`` was sliced, and how many calls
fitted before it was gone. Since the reservation was never what a count bought,
and since the count itself has been **measured wrong twice** (Q-C section 4b's
three *steps* read as three *calls*; the measured worst cases are OTOCO 5, OTO 4,
unprotected 1, and the recovery-bearing entry path 3), the count is not carried.

**Each call takes the whole remainder.** The total is bounded by ``D`` *by
construction*, without anyone having to know the call count in advance -- which
is precisely the fact nobody has got right yet.

**The first call of a sequence therefore gets the LOOSEST bound available, and
that is not an accident of the arithmetic but the reason to prefer it.** The
first call of an entry sequence is the placement, and a placement's timeout is
the one that manufactures the ambiguous write -- ``docs/M5_NUMBERS.md`` section 5:
*"Too tight costs: a timed-out placement that in fact placed -- the ambiguous
write... it is the most expensive path in the system."* Under any divisor that
call was bounded at ``D / n``; here it is bounded at ``D``. What is spent early
is taken from calls whose failure mode is a query returning nothing, not from the
one whose failure mode is an order resting that the ledger does not know about.

**A budget may refuse to BEGIN work; it must never abandon work in flight.**
``CLAUDE.md``, quoted: *"A placement that runs past its share overruns; the
overrun is charged to the next invocation's dispatch share. Abandoning a
submission mid-flight produces a state nobody can read."* So
:meth:`DispatchBudget.bounds_for_next_call` is consulted **before** a call and
returns ``None`` when there is nothing left to spend. Nothing here cancels, and
nothing here can: a call already issued runs to its own bound.

**A POSITIVE refusal floor is DEFERRED, not decided.** The refusal fires at
``remaining <= 0``, so a call may begin with a bound too small to complete -- it
will simply time out, having begun. A floor (*"do not begin a write with less
than X left"*) would prevent that, and choosing ``X`` needs a placement latency
this project does not have. *Arming condition, in caller terms:* **the executor's
spend site** -- the first caller that must decide whether to begin a write with
little time left. Not an event, and not "the first timeout": the decision belongs
to whoever writes the loop, and it exists the moment that loop is written.

**The state is WITHIN one sequence, and that is a different thing from the
cross-pass state the reconciliation driver refused to hold.** That refusal,
quoted from ``docs/QB_ESCALATION.md``: *"a driver that remembers position state
becomes a second source of truth for a fact the position already owns, and the
stamp is that fact."* The distinction is **whether anything else owns the
fact**. A position's freshness is owned by ``Position.last_reconciled_at``, so a
driver caching it would be a second copy that goes stale. How much of *this*
sequence's deadline is gone is owned by nothing else -- it does not survive the
sequence, nothing else can read it, and there is no other copy to disagree with.
This type does not even hold it: the instants are passed in.

**The clock is not read here.** ``started_at`` and ``now`` are supplied by the
caller, following ``RiskManager.evaluate``'s hoisted reading -- *"``now`` is
SUPPLIED rather than read here... hoisted it so that the staleness guard and the
daily-loss and cooldown comparisons all measure against one instant. Two readings
would let a signal be fresh against one and in cooldown against another."* The
same applies to a sequence: two readings inside one dispatch would let two calls
disagree about how much of the deadline is left.

**``risk.dispatch_deadline_s`` is PLACEHOLDER -- NOT MEASURED, and the arithmetic
here is enforced on that unmeasured base.** This is the reconciler's precedent
exactly: ``ReconciliationBudget`` derives from ``reconcile_deadline_s``, which
carries the same mark, and no status mark moved when it did.

**Worse than unmeasured: NO PLACEMENT HAS EVER BEEN TIMED IN THIS PROJECT.** The
only latency samples in existence are six ``get_open_orders`` **reads** against
Testnet -- ``180.6, 451.6, 446.2, 182.3, 181.9, 452.5`` ms, bimodal, one host,
one session. They bound a read, not a write, and nothing here is validated
against a sample of the call it bounds.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from trading_bot.config.models import AppConfig

__all__ = ["CallBounds", "DispatchBudget"]


@dataclass(frozen=True, slots=True)
class CallBounds:
    """What one call may spend: a transport bound and an attempt count.

    Shaped to be handed straight to the adapter's ``timeout_s`` / ``attempts``
    keywords, which is why it is two plain numbers and not a richer object.
    """

    #: Bound on ONE HTTP round trip, in seconds. The whole remaining deadline.
    timeout_s: float
    #: Attempts for that call.
    attempts: int


@dataclass(frozen=True, slots=True)
class DispatchBudget:
    """The deadline one dispatch sequence may spend, derived from config.

    **A frozen dataclass rather than a pydantic model**, and the reasoning is
    ``ReconciliationBudget``'s: the one field is derived from config that
    ``AppConfig`` has already validated (``dispatch_deadline_s`` carries
    ``gt=0``), so a validator here would re-check what the config layer
    guarantees, and no field is money. It also avoids adding a private
    ``_Frozen`` base to a tree whose count of those is a recorded open item --
    now four, not the three that item states.
    """

    #: The whole sequence's deadline in seconds -- never a per-call share.
    deadline_s: float

    @classmethod
    def from_config(cls, config: AppConfig) -> DispatchBudget:
        """Derive the budget from validated config.

        Takes the whole ``AppConfig`` rather than the float, mirroring
        ``ReconciliationBudget.from_config``: a budget is derived *from config*,
        and a caller that has to reach in and pass one field has to know which
        field, which is the knowledge this method exists to hold.
        """
        return cls(deadline_s=config.risk.dispatch_deadline_s)

    def remaining_s(self, *, started_at: datetime, now: datetime) -> float:
        """Seconds left in the sequence. May be zero or negative.

        Negative is a real answer, not an error: it says by how much the
        sequence has already overrun, which is what the next invocation's share
        is charged. Callers that want the refusal should ask
        :meth:`bounds_for_next_call` rather than comparing this themselves --
        two comparisons of one fact drift apart.

        :raises ValueError: either instant is naive. A naive value would be read
            as local time and shift the arithmetic by the host's offset, which
            is a caller bug detectable without doing anything.
        :raises ValueError: ``now`` precedes ``started_at``. That would make the
            remainder EXCEED the deadline and hand a call a looser bound than
            ``D``, which is the one thing this type exists to prevent. It is a
            caller bug -- a clock read backwards, or the wrong pair of instants
            -- and it is refused rather than clamped, because clamping would
            hide it and the bound would still be wrong for the next call.
        """
        _require_aware(started_at, "started_at")
        _require_aware(now, "now")
        elapsed = (now - started_at).total_seconds()
        if elapsed < 0:
            raise ValueError(
                f"now {now.isoformat()} precedes started_at {started_at.isoformat()}; "
                "the remainder would exceed the deadline and bound a call looser than "
                "risk.dispatch_deadline_s"
            )
        return self.deadline_s - elapsed

    def bounds_for_next_call(self, *, started_at: datetime, now: datetime) -> CallBounds | None:
        """What the next call may spend, or ``None`` to refuse beginning it.

        **``None`` rather than a reason-carrying value object**, which is a
        departure from the ``SizingDecision`` idiom and a deliberate one: there
        is exactly one reason -- the deadline is spent -- and it is recoverable
        for free by calling :meth:`remaining_s` with the same instants, which is
        pure. A single-membered reason enum would be surface with no consumer
        and a second place for the same fact to live.

        **``attempts`` is 1, and it is FORCED rather than chosen.**
        ``attempts x timeout_s <= remaining`` with ``timeout_s`` set to the whole
        remainder admits exactly one attempt, for every deadline and at every
        point in a sequence. Splitting the remainder into a per-attempt share
        would be a tail claim, and ``ReconciliationBudget.from_config`` already
        records that the only samples in existence cannot support one. The retry
        does not vanish: for the reconciler it moved to the cadence, and here the
        equivalent is that a refused or failed placement is a missed trade the
        next bar may re-signal -- which Q-C section 4 already rules, in
        *"Unfilled entry: log ``entry_unfilled``, drop the signal. No retry, no
        chase -- the edge was on that bar."*

        :raises ValueError: as :meth:`remaining_s`.
        """
        remaining = self.remaining_s(started_at=started_at, now=now)
        if remaining <= 0:
            return None
        return CallBounds(timeout_s=remaining, attempts=1)


def _require_aware(value: datetime, name: str) -> None:
    """Refuse a naive instant, matching ``_check_order_list_entry``'s guard."""
    if value.tzinfo is None or value.tzinfo.utcoffset(value) is None:
        raise ValueError(f"{name} must be timezone-aware, got naive {value!r}")
