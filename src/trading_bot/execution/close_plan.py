"""Decide what a discretionary close should do next -- *sell, or not?*

Q-C section 4b fixes the sequence as **cancel, then confirm by query, then
sell**, and it is the CONFIRMING QUERY that decides what happens next. This
module is that decision, and nothing else: given what the protective legs
reported, it returns SELL, ALREADY_CLOSED or HALT.

**IT DECIDES AND IT DOES NOT ACT.** Pure -- no client, no I/O, no clock, no
portfolio. It neither cancels nor sells nor books, and it holds no reference to
anything that could. That is what lets the whole table be exercised over
fabricated leg states with no venue and no fake, which matters because two of
its rows are states this project has never observed.

**NOTHING CALLS IT.** The caller is Q-C section 4b's dispatch path, which does
not exist: ``OrderExecutor`` still refuses ``SignalAction.CLOSE`` by name. This
is the decision arriving before the actor, the same shape ``persist_pending``
and ``persist_ledger`` each had one commit before their callers.

**Why the cancel is not modelled here.** Section 4b's cancel-failure table has
three rows, and two of them -- success and ``-2011 'Unknown order sent.'`` --
converge on the SAME next step: confirm by query, then act on what the query
says. The third, any other failure, means the venue state is unknown and
nothing may be sold. So the cancel's outcome does not survive into this
decision except as *"was a query obtained at all"*, which arrives here as a leg
whose state could not be read. Modelling the cancel separately would duplicate
a branch that has already collapsed.

**``executedQty``, NOT merely ``status``.** Section 4b is explicit, and the
reason is measured elsewhere in this tree: a list read-back carries neither
``status`` nor ``executedQty`` per leg, so the confirm step is a per-order
query and the quantity is the field it exists to obtain. A leg that reports
``FILLED`` with nothing executed and a leg that reports ``CANCELED`` with a
partial fill are different facts, and only the quantity separates them.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import Enum

__all__ = ["CloseAction", "ClosePlan", "LegReport", "plan_close"]


class CloseAction(str, Enum):
    """What the close path should do once its legs have been read.

    ``str, Enum`` rather than ``StrEnum``, per the project-wide ``UP042``
    suppression: ``str(member)`` stays qualified, so any log line carrying one
    passes ``.value``.

    **Three members, because section 4b names three outcomes.** There is no
    ``UNKNOWN`` and no ``RETRY``: an unreadable leg is a reason to HALT, which
    is a decision, and adding a fourth member for "I could not tell" would be
    an unreachable value within reach of whoever is nearest a construction
    site -- the hazard ``CLAUDE.md`` records for ``RefusalStage``.
    """

    #: No leg executed. The position is still open, so dispatch the sell.
    SELL = "sell"
    #: A leg executed in full. The position is already closed at the venue --
    #: record the exit, dispatch NOTHING.
    ALREADY_CLOSED = "already_closed"
    #: Do not sell. Something is either partially filled or unreadable, and
    #: section 4b treats both as ``CRITICAL`` with entries halted.
    HALT = "halt"


@dataclass(frozen=True, slots=True)
class LegReport:
    """What the confirming query said about ONE protective leg.

    **``executed`` IS ``None`` WHEN THE LEG COULD NOT BE READ**, and that is a
    third state rather than a zero. A leg that answered "nothing executed" and
    a leg that did not answer are opposite facts: the first permits a sell, the
    second forbids one. Collapsing them into ``Decimal(0)`` would turn a failed
    query into a licence to sell, which is the one direction this decision may
    not err in.

    ``requested`` is the quantity the leg was placed for -- our own arithmetic,
    known before any venue contact -- so a full fill is ``executed ==
    requested`` rather than a comparison against something the venue chose.

    ``status`` is carried for the REASON STRING only and is deliberately not
    read by the decision. Section 4b: the query "reads ``executedQty`` on each
    leg, not merely ``status``". A leg reporting ``FILLED`` with nothing
    executed is decided by the quantity, not by the word.
    """

    #: Which leg this is, for the reason string. A leg code, never an enum
    #: member interpolated raw -- see ``exchange/ids.py`` for that trap.
    leg: str
    #: Base quantity the venue reports executed, or ``None`` if unreadable.
    executed: Decimal | None
    #: What we asked this leg to protect.
    requested: Decimal
    #: The venue's word for it. Reported, never decided on.
    status: str | None = None


@dataclass(frozen=True, slots=True)
class ClosePlan:
    """The decision, carrying its reason -- never a bare enum.

    The house shape: a verdict is a value carrying why, so an operator meeting
    a HALT is not left to re-derive which leg caused it. Same form as
    ``ProtectionAssessment``, ``PlacementVerdict`` and ``SizingDecision``.
    """

    action: CloseAction
    reason: str


def plan_close(legs: tuple[LegReport, ...]) -> ClosePlan:
    """Q-C section 4b's confirming-query table, and nothing else.

    ``legs`` is the protective legs the confirm step read -- the ones that were
    requested, in a stable order. The working leg is not among them: it is the
    entry, it has already filled (that is why a position exists), and section
    4b's table is about protection.

    The table, in the order the rows are tested and with the reason each is
    tested where it is:

    ==============================  ==========================================
    what the legs report            plan
    ==============================  ==========================================
    any leg unreadable              ``HALT`` -- the venue state is unknown
    any leg partially executed      ``HALT`` -- UNMEASURED, section 10
    any leg executed in full        ``ALREADY_CLOSED`` -- record, do not sell
    no leg executed                 ``SELL`` -- the position is still open
    no legs at all                  ``HALT`` -- see below
    ==============================  ==========================================

    **UNREADABLE IS TESTED FIRST, and the order is load-bearing rather than
    stylistic.** A pass that checked full fills first would answer
    ``ALREADY_CLOSED`` for a set in which one leg filled and another could not
    be read -- asserting the position is closed on the strength of an
    incomplete picture. Testing the unknown first means no positive conclusion
    is ever drawn over a set containing an unanswered leg.

    **PARTIAL IS ``HALT``, NOT A SELL OF THE REMAINDER**, and section 4b says
    why: the state is UNMEASURED, deferred to section 10, and ``FOK`` removes
    partial fills from the entry path but NOT from a triggered protective leg.
    Selling the remainder would be acting on arithmetic nobody has verified
    against a venue.

    **AN EMPTY TUPLE IS ``HALT``, and it is the row most likely to be got
    wrong.** "No leg executed" and "no leg was asked about" are different
    facts, and only the first permits a sell. An empty set reaching here means
    the caller either requested no protection -- in which case there was
    nothing to cancel and this decision does not apply -- or lost its legs
    between asking and reading. Returning ``SELL`` on it would make the
    permissive answer the DEFAULT for a caller bug, which is the fake-default
    shape this project refuses everywhere else. `CLAUDE.md`: take the reading
    whose wrong answer is reversible -- a refused close costs a missed exit,
    a wrong sell cannot be un-placed.

    **Over-execution falls into the full-fill row, deliberately.** A leg
    reporting more than it was asked for is not a state the venue can produce,
    and the comparison is ``>=`` rather than ``==`` so it lands on
    ``ALREADY_CLOSED`` rather than slipping past every row into ``SELL``. The
    unreachable state gets the conservative answer without a row of its own.
    """
    if not legs:
        return ClosePlan(
            action=CloseAction.HALT,
            reason=(
                "the confirming query reported no protective legs at all. That is not the "
                "same fact as 'no leg executed', and only the second permits a sell"
            ),
        )

    unreadable = [leg for leg in legs if leg.executed is None]
    if unreadable:
        return ClosePlan(
            action=CloseAction.HALT,
            reason=(
                f"leg(s) {', '.join(leg.leg for leg in unreadable)} could not be read, so the "
                "venue state is unknown. An unread leg is not a leg that executed nothing"
            ),
        )

    # Every `executed` is non-None from here; the comprehension above is what
    # establishes it, and the local rebind is what lets mypy see it.
    read = [(leg, leg.executed) for leg in legs if leg.executed is not None]

    partial = [(leg, qty) for leg, qty in read if Decimal(0) < qty < leg.requested]
    if partial:
        return ClosePlan(
            action=CloseAction.HALT,
            reason=(
                "leg(s) "
                + ", ".join(f"{leg.leg} executed {qty} of {leg.requested}" for leg, qty in partial)
                + ". A partially executed protective leg is UNMEASURED (Q-C section 10) and is "
                "never sold against"
            ),
        )

    full = [(leg, qty) for leg, qty in read if qty >= leg.requested]
    if full:
        return ClosePlan(
            action=CloseAction.ALREADY_CLOSED,
            reason=(
                "leg(s) "
                + ", ".join(f"{leg.leg} executed {qty} of {leg.requested}" for leg, qty in full)
                + ". The position is already closed at the venue; record the exit and dispatch "
                "nothing"
            ),
        )

    return ClosePlan(
        action=CloseAction.SELL,
        reason=(
            f"no protective leg executed across {len(read)} leg(s); the position is still open "
            "and the sell may be dispatched"
        ),
    )
