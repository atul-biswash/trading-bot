"""Resolve a placement whose outcome we do not know -- *did it place?*

`CLAUDE.md`: a timed-out write is resolved by QUERY, never by retry. A
connection timeout on an order-list submission may have landed, so the recovery
asks the venue for the ids it would have sent -- which Q-C section 6 makes
derivable at generation 0 by pure computation, no persistence and no I/O.

**LIST-ONLY, and the docstring says so because the gap is silent.** Q-C section
2's fourth row -- neither protective level enabled -- places a single
``OrderRequest`` through ``create_order``, and ``get_all_order_lists`` will
never show it. This function has no answer for that shape and does not pretend
to; the branch is out of scope and its recovery is unruled.

**THE QUERY IS AN ENUMERATION AND THE ANSWER IS A SET.** R13 rules out a point
query by our own id because the venue chooses which of several it returns, and
the choice is undefined. Enumerating hands that choice to us -- and choosing
wrongly here is the same defect one layer in, so this reasons about the whole
set rather than picking a member.

That is not hypothetical. MEASURED on Testnet, 2026-08-21: a census of the
probe account found **14 order lists carrying 12 distinct**
``listClientOrderId`` **values, with one id mapping to THREE lists** --
``72321``, ``72322`` and ``72324``, all ``ALL_DONE``. The probe's own findability
check keyed a dict on that id and escaped only because that session's six ids
happened to be unique. A mapping keyed on the id is therefore not merely
imprecise; it discards evidence this account demonstrably holds.

**Why several lists can share one id, and what constrains the set.** Q-C section
6, MEASURED: *a client order id is unique against LIVE orders only; a terminal
order's id is RELEASED and immediately reusable.* So the set may hold any number
of TERMINAL lists and **at most one LIVE** one. Every rule below is derived from
that single constraint.

**The FOK inference, and its two halves are marked separately so the measured
one does not launder the inferred one.**

* TERMINAL half -- **MEASURED, this project, 2026-08-21.** Six OTOCO lists placed
  with a working ``LIMIT``+``FOK`` 30% below the ask each read
  ``list_order_status='ALL_DONE'`` / ``list_status_type='ALL_DONE'``, were
  findable by our derived id, carried leg ids byte-for-byte, and reported every
  leg ``EXPIRED`` with ``executedQty='0.00000000'``. A terminal list means the
  working leg did not fill.
* LIVE half -- **INFERRED, not measured here.** That a live list implies a FILLED
  working leg rests on Q-C section 8's note that a ``FOK`` leg cannot rest and so
  cannot produce a live list without a fill, and on M5c's arm-10 measurement of a
  live list, whose working leg was ``LIMIT``+**GTC** rather than section 3's
  ``FOK``. Nothing in this session observed a live list.

**C4 reads this classification to decide whether to construct a ``Position``**,
so a falsification of the live half lands on the risk path rather than in a log
line. That is why the halves are labelled rather than merged.

**FUNDING IS NOT DECIDED HERE.** ``timeout_s`` and ``attempts`` are parameters.
How a caller pays for this call is UNRULED and reserved to the project owner,
with four options on the table: reserve a slice before the placement; run
outside the dispatch budget; accept no recovery on that bar; or resolve at the
start of the next candle-handler invocation out of its fresh deadline. This
module chooses none and builds no mechanism that presupposes one.

What the cost actually is, MEASURED 2026-08-21, wire round trips in order:
``POST /api/v3/orderList/otoco`` gave ``452.4, 471.2, 182.6, 181.7, 451.8,
454.1`` ms and ``GET /api/v3/allOrderList`` gave ``189.9, 459.9, 450.1, 184.1,
182.3, 196.3`` ms. Both are the SAME bimodal distribution -- roughly 182 and
roughly 452, with nothing between -- so **a resolver call costs what a placement
costs**. Any funding rule that assumed a read was cheaper than a write was
assuming something the samples do not support. Six samples from one host bound
no tail.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum

from trading_bot.core.interfaces import ExchangeClient
from trading_bot.core.models import OrderList
from trading_bot.exchange.ids import list_client_order_id

__all__ = ["PlacementOutcome", "PlacementVerdict", "resolve_placement"]

#: `list_order_status` values that mean the list is still working. MEASURED at
#: M5c on a live list; a terminal one reads `ALL_DONE` (MEASURED 2026-08-21).
_LIVE_STATUSES = frozenset({"EXECUTING", "EXEC_STARTED"})


class PlacementOutcome(str, Enum):
    """What the venue says about a placement whose outcome we did not see."""

    #: A list carrying our derived id is working. Under the FOK inference the
    #: entry FILLED and protection is live. Do not re-place: a duplicate against
    #: a live id is refused with `-2010`.
    PLACED_LIVE = "placed_live"
    #: A list carrying our derived id exists and is terminal. Under the FOK
    #: inference the entry EXPIRED, so nothing rests and no position was opened.
    PLACED_TERMINAL = "placed_terminal"
    #: No list carries our derived id. Nothing rests.
    NOT_PLACED = "not_placed"
    #: The venue's answer does not identify our placement.
    #:
    #: **A MEMBER, NOT AN ABSENCE, and it carries its reason.** The reconciler
    #: settled this shape already, in ``UnresolvedLeg``: *"Absence is not an
    #: answer."* And in ``resolve_unresolved_legs``, on why the two must not
    #: collapse: *"'Every leg was queried' and 'the budget ran out' are
    #: different facts with different consequences -- only the first may stamp
    #: -- and a caller cannot act on a distinction that exists only in a
    #: sentence."* The same holds here: "no list matched" and "several matched
    #: and none can be attributed" are different facts, and only one of them is
    #: an answer.
    #:
    #: **FAIL-CLOSED: the caller does NOT re-place on this.** Ruled by the
    #: project owner. A re-place under ambiguity risks a second entry, and the
    #: cost of not re-placing is a missed trade -- a refusal, a value, logged.
    UNRESOLVED = "unresolved"


@dataclass(frozen=True, slots=True)
class PlacementVerdict:
    """The outcome and why, plus the lists the query actually matched.

    A verdict is a **value carrying its reason**, mirroring
    ``ProtectionAssessment``: *"'the stop rests one tick low' and 'the stop is
    not there at all' are different facts that would otherwise arrive as the
    same word."*

    ``matched`` is every list carrying our derived id, in the order the venue
    returned them. It is carried rather than reduced because a multi-match is
    the evidence for :attr:`PlacementOutcome.UNRESOLVED` and a caller that has
    to escalate needs to name what it saw.
    """

    outcome: PlacementOutcome
    reason: str
    matched: tuple[OrderList, ...] = ()


def _is_live(order_list: OrderList) -> bool:
    """Whether a list is still working, by its own reported status."""
    return (order_list.list_order_status or "") in _LIVE_STATUSES


async def resolve_placement(
    client: ExchangeClient,
    *,
    symbol: str,
    entry_bar_time: datetime,
    generation: int = 0,
    timeout_s: float | None = None,
    attempts: int | None = None,
) -> PlacementVerdict:
    """Ask the venue whether the list we would have sent exists.

    The id is DERIVED, not remembered -- ``(symbol, entry_bar_time, generation)``
    is all it takes, which is what lets this run after a timeout that destroyed
    every local record of the attempt.

    **The rules, each derived from one measured constraint: at most one LIVE
    list may hold an id at a time, while any number of TERMINAL ones may.**

    ========================  ===================================================
    matches                   verdict
    ========================  ===================================================
    none                      ``NOT_PLACED`` -- nothing rests
    exactly one, live         ``PLACED_LIVE``
    exactly one, terminal     ``PLACED_TERMINAL``
    several, exactly one live ``PLACED_LIVE`` -- the live one is unambiguous
    several, none live        ``UNRESOLVED`` -- cannot attribute
    several live              ``UNRESOLVED`` -- the measured rule is violated
    the query raised          ``UNRESOLVED`` -- no answer was obtained
    ========================  ===================================================

    **Why several-all-terminal is UNRESOLVED rather than PLACED_TERMINAL, since
    it is the one row that could go either way.** Terminal ids are released and
    reusable, so a terminal match may be this attempt's or a previous one's, and
    nothing in the payload separates them -- ``OrderList`` carries no timestamp,
    and ordering by ``order_list_id`` would be the venue choosing under another
    name, which R13 exists to avoid. Reporting ``PLACED_TERMINAL`` would assert
    "our placement landed and expired", which is not known.

    It costs nothing to be honest here, and that is what decides it: under the
    fail-closed ruling both verdicts lead the caller to the same action -- do not
    re-place -- so ``UNRESOLVED`` keeps the distinction in the record at no
    operational price. Under fail-closed, guessing is the one thing unavailable.

    **Several-live is UNRESOLVED because the premise is broken, not the data.**
    The uniqueness rule says it cannot happen; if it does, every other rule here
    rests on a measurement that no longer holds, and proceeding would be
    reasoning from a falsified premise.

    :raises ValueError: propagated from id derivation -- a naive
        ``entry_bar_time`` or a generation outside ``0..99``. Both are caller
        bugs detectable without any I/O, so they are NOT converted to
        ``UNRESOLVED``: a verdict means the venue was asked.
    """
    wanted = list_client_order_id(symbol, entry_bar_time, generation=generation)

    try:
        listings = await client.get_all_order_lists(timeout_s=timeout_s, attempts=attempts)
    except Exception as exc:
        return PlacementVerdict(
            outcome=PlacementOutcome.UNRESOLVED,
            reason=(
                f"the did-it-place query for {wanted} failed with "
                f"{type(exc).__name__}: {exc}. Nothing is known about the placement, "
                "which is different from knowing nothing rests"
            ),
        )

    matched = tuple(ol for ol in listings if ol.list_client_order_id == wanted)
    live = tuple(ol for ol in matched if _is_live(ol))

    if not matched:
        return PlacementVerdict(
            outcome=PlacementOutcome.NOT_PLACED,
            reason=(
                f"no order list on the account carries {wanted}, across "
                f"{len(listings)} enumerated; nothing rests"
            ),
        )

    if len(live) > 1:
        return PlacementVerdict(
            outcome=PlacementOutcome.UNRESOLVED,
            reason=(
                f"{len(live)} LIVE lists carry {wanted}, and a client order id is "
                "measured unique against live orders -- so the constraint every "
                "other rule here rests on does not hold, and no verdict derived "
                "from it can be trusted"
            ),
            matched=matched,
        )

    if live:
        return PlacementVerdict(
            outcome=PlacementOutcome.PLACED_LIVE,
            reason=(
                f"{wanted} is working as order list {live[0].order_list_id} "
                f"({live[0].list_order_status}); at most one live list may hold an "
                f"id, so this one is unambiguous among the {len(matched)} matched"
            ),
            matched=matched,
        )

    if len(matched) > 1:
        return PlacementVerdict(
            outcome=PlacementOutcome.UNRESOLVED,
            reason=(
                f"{len(matched)} terminal lists carry {wanted} "
                f"({', '.join(ol.order_list_id for ol in matched)}) and none is live. "
                "A terminal id is released and reusable, so any of them may be this "
                "attempt's or an earlier one's, and nothing in the payload separates "
                "them; nothing rests either way"
            ),
            matched=matched,
        )

    only = matched[0]
    return PlacementVerdict(
        outcome=PlacementOutcome.PLACED_TERMINAL,
        reason=(
            f"{wanted} is order list {only.order_list_id}, terminal "
            f"({only.list_order_status}); under the FOK working leg the entry did "
            "not fill, so nothing rests and no position was opened"
        ),
        matched=matched,
    )
