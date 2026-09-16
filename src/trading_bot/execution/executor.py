"""Order executor -- the first thing in ``src/`` that places an order.

**What it is.** A terminal collaborator on the signal chain, after
:class:`~trading_bot.engine.modes.IntentLogger`. It takes an approved
:class:`~trading_bot.core.assessment.EntryIntent`, maps it to a placement
shape with :func:`~trading_bot.execution.placement.build_placement`, spends a
:class:`~trading_bot.execution.dispatch_budget.DispatchBudget`, dispatches,
and records a :class:`~trading_bot.core.models.Position`.

**It is ALSO a candle subscriber**, and that is not a second job bolted on: it
is where Option 4 resolution runs. See :meth:`__call__`.

**It must never raise.** Both entry points are reached from isolation layers
that catch, log without structured fields, and continue -- forever, once per
bar, with no counter quarantining anything. So every phase carries its own
``try`` and its own name in the log line, exactly as
``ReconciliationDriver`` and the signal handler do.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Final, Literal

from trading_bot.core.assessment import EntryIntent
from trading_bot.core.enums import OrderSide, OrderType, PositionSide, ProtectionState
from trading_bot.core.exceptions import ClientRefusalError, OrderNotFoundError
from trading_bot.core.models import (
    Money,
    Order,
    OrderRequest,
    OtocoOrderListRequest,
    OtoOrderListRequest,
    Position,
)
from trading_bot.exchange.ids import OrderListLeg, client_order_id, close_client_order_id
from trading_bot.execution.bookability import BookabilityOutcome, classify_bookability
from trading_bot.execution.close_plan import CloseAction, LegReport, plan_close
from trading_bot.execution.dispatch_budget import CallBounds, DispatchBudget
from trading_bot.execution.placement import build_placement
from trading_bot.execution.resolution import (
    _LIVE_STATUSES as _LIVE_LIST_STATUSES,
)
from trading_bot.execution.resolution import (
    PlacementOutcome,
    PlacementVerdict,
    resolve_placement,
)
from trading_bot.utils.helpers import utc_now
from trading_bot.utils.logger import get_logger

if TYPE_CHECKING:  # pragma: no cover - typing only
    from collections.abc import Callable, Sequence
    from datetime import datetime

    from trading_bot.core.assessment import RiskAssessment
    from trading_bot.core.interfaces import ExchangeClient
    from trading_bot.core.models import Candle, OrderList, Signal
    from trading_bot.core.portfolio import Portfolio

__all__ = ["OrderExecutor", "Pending", "PendingClose", "PendingPlacement"]


def _matched_list_id(verdict: PlacementVerdict) -> str | None:
    """The list id of the single live match, or ``None``.

    ``matched`` can hold more than one -- MEASURED, a Testnet census found one
    ``listClientOrderId`` mapping to three lists -- but ``PLACED_LIVE`` is only
    returned when exactly one of them is live, so the id is unambiguous here.
    ``None`` rather than a guess if the shape is ever otherwise: an absent
    ``order_list_id`` on the position is honest, where a wrong one would send
    the reconciler to compare against somebody else's legs.
    """
    live = _single_live(verdict)
    if live is None:
        return None
    return live.list_client_order_id


def _matched_venue_list_id(verdict: PlacementVerdict) -> int | None:
    """The VENUE's numeric id of the single live match, or ``None``.

    The sibling of :func:`_matched_list_id`, and deliberately a second function
    rather than a second return value: the two identifier spaces stay separate
    all the way to the ``Position``, and a caller that wants both asks twice.
    Returning a pair would put them in one expression, which is where the run-1
    defect came from -- see :attr:`Position.order_list_id`.

    **Both answer ``None`` on the SAME condition**, because the selection is
    shared: if no single live list can be identified, neither id may be taken,
    and taking one without the other would leave a position half-identified.
    """
    live = _single_live(verdict)
    if live is None:
        return None
    return _venue_list_id(live)


def _single_live(verdict: PlacementVerdict) -> OrderList | None:
    """The one live list this verdict matched, or ``None`` if not exactly one.

    Factored out so the two id accessors above cannot drift in WHICH list they
    describe. Two copies of this filter would be two answers to "which list is
    this position's", and the whole point of the pair is that there is one.
    """
    live = [ol for ol in verdict.matched if ol.list_order_status in _LIVE_LIST_STATUSES]
    if len(live) != 1:
        return None
    return live[0]


def _venue_list_id(order_list: OrderList) -> int | None:
    """``OrderList.order_list_id`` as the integer the venue issued.

    ``to_order_list`` stringifies ``orderListId`` for the domain, and the cancel
    and read-back endpoints take it back as a number -- the adapter already
    writes ``params["orderListId"] = int(order_list_id)``. This is that same
    conversion, at the one place a ``Position`` acquires the value.

    **``None`` rather than a raise on a non-numeric id, and the error direction
    decides it.** Reaching here means a placement has ALREADY LANDED at the
    venue. Raising would abandon the ``Position`` for a list that exists,
    producing an orphan -- the direction :func:`_matched_list_id` already
    refuses in its own words. A missing number costs the close path one
    enumeration; a missing position costs the list entirely.

    Unreachable on every payload measured: ``orderListId`` is an integer on the
    read-back, the list history and the placement response alike.
    """
    try:
        return int(order_list.order_list_id)
    except ValueError:
        _log.error(
            "Order list id is not numeric",
            extra={
                "event": _EVENT_NON_NUMERIC_LIST_ID,
                "symbol": order_list.symbol,
                "order_list_id": order_list.order_list_id,
            },
        )
        return None


_log = get_logger(__name__)

_EVENT_PLACED = "order_placed"
_EVENT_REFUSED = "dispatch_refused"
_EVENT_AMBIGUOUS = "placement_ambiguous"
_EVENT_RESOLVED = "placement_resolved"
#: A resolution ATTEMPT that did not resolve. Its own event name rather than
#: `_EVENT_RESOLVED` carrying an `outcome` field, because that is the schema
#: convention everywhere else in `src/`: `IntentLogger` emits `risk_refused`
#: or `intent_dispatched` from ONE call site depending on the outcome, and
#: `ReconciliationDriver` splits `reconciliation_pass` from
#: `reconciliation_untrusted`. Nowhere does one name carry an outcome field
#: to distinguish outcomes a reader acts on differently.
_EVENT_UNRESOLVED = "placement_unresolved"
#: A resolution that found nothing and will not be retried -- the trade is gone.
#: Its own name for the same reason `_EVENT_UNRESOLVED` has one, and at ERROR
#: rather than the INFO it shared with a successful resolution: `placement_
#: unresolved` is SELF-CLEARING (retried next bar) while this is TERMINAL, and
#: Q-B's rule is that escalating a self-clearing condition at the same level as
#: a terminal one "is how a `CRITICAL` line stops being read". Read the other
#: way it says a terminal condition must not hide at a self-clearing one's
#: level. Not CRITICAL: Q-B reserves that for a log line AND A HALT, and this
#: halts nothing.
_EVENT_MISSED = "dispatch_missed"
#: The entry leg reported no fill. Its own name rather than a failure event:
#: the query SUCCEEDED and the venue's answer was "nothing filled", which is a
#: different fact from "we could not ask" -- and the two are the first two of
#: `entry_fill_price`'s three `None` meanings. A reader who cannot separate
#: them cannot tell an expired FOK from a network fault.
_EVENT_NO_ENTRY_FILL = "entry_fill_absent"
#: `free_quote` was debited from the REQUESTED limit because no fill price was
#: obtained. Its own name rather than a field on `entry_fill_absent`: that one
#: reports what the venue said, this one reports the MONEY CONSEQUENCE, and an
#: operator reconciling a balance needs the second without having to infer it
#: from the first. It also fires on the query-failure path, which
#: `entry_fill_absent` does not.
_EVENT_DEBIT_ESTIMATED = "debit_from_requested_limit"
#: Q-C section 4b's confirming query ran and its decision table answered. **The
#: ONLY instrument that will ever report how long that costs**, because the
#: close branch sits ahead of `dispatch`'s single budget sample -- see
#: `_plan_close`. `elapsed_s` is the field the whole read half exists to
#: produce.
_EVENT_CLOSE_PLANNED = "close_planned"
#: An ``orderListId`` that will not parse as an integer. Unreachable on every
#: payload this project has measured, and named rather than silent because the
#: consequence is a position the close path cannot cancel by number.
_EVENT_NON_NUMERIC_LIST_ID = "order_list_id_not_numeric"
#: Q-C section 4b's unprotected window OPENS. There is no matching close event,
#: and `_go_naked` says why: the state it can leave behind does not resolve
#: in-process, so there is nothing in-process to report its end.
_EVENT_CLOSE_WINDOW_OPEN = "close_window_open"
_EVENT_CLOSE_CANCEL_TERMINAL = "close_cancel_already_terminal"
_EVENT_CLOSE_CANCEL_FAILED = "close_cancel_failed"
#: The re-query after a successful cancel disagreed with the plan. Its own
#: event, because the plan's `close_planned` already said SELL and a reader
#: needs to see that the second look changed the answer.
_EVENT_CLOSE_ABANDONED = "close_abandoned_after_cancel"
_EVENT_CLOSE_BOOKED = "close_booked"
_EVENT_CLOSE_BOOK_FAILED = "close_book_failed"
_EVENT_CLOSE_NAKED = "close_position_naked"
#: A pending close record was resolved: the venue was asked what became of the
#: sell and whatever was learned was LOGGED. Its own event rather than reusing
#: `close_position_naked`, because that one describes a position this process
#: still holds and re-observes every pass, and this one describes a record this
#: process is letting go of. An operator filtering for the first and finding the
#: second would look for a position that is not there.
#:
#: **THIS COMMENT SAID "A RESTORED close record" AND "the record was DROPPED",
#: AND BOTH WERE FALSE** -- `M5i-011` and `M5i-007`, the same two falsehoods the
#: log message carried, in a second location. Restored: nothing here knows the
#: provenance. Dropped: under ruling 5 a confirmed fill against an in-memory
#: position is BOOKED, and on the unconfirmed branch the position is RETAINED.
#: Corrected in place rather than annotated, because it is a claim about the
#: tree; see `_log_close_resolved` for the argument.
_EVENT_CLOSE_RESOLVED = "close_record_resolved"
#: The sell was dispatched and the client never learned its outcome. Its own
#: event, and the separation is a SAFETY property rather than tidiness:
#: `close_position_naked` tells an operator to sell the base by hand, and on
#: this branch the sell MAY ALREADY HAVE FILLED, so acting on that instruction
#: would sell twice. An operator filtering for one and finding the other would
#: take the one action this state cannot survive.
_EVENT_CLOSE_SELL_UNCONFIRMED = "close_sell_unconfirmed"
#: The bot's OWN close sell completed and cannot be priced, so the position is
#: dropped without booking. **B-i.** Its own event rather than reusing
#: `close_record_resolved`, on the grounds `_go_naked_retaining` already states
#: for its own name: that one describes a record RESTORED and resolved a bar
#: later, this one a sell this process just sent, and an operator filtering for
#: one must not find the other. What it must NOT reuse is
#: `close_position_naked` -- that line says the position is still open and
#: instructs a manual sale, and both are false here because the base is gone.
_EVENT_CLOSE_SOLD_UNBOOKED = "close_sold_unbooked"

#: The working leg expired: the venue ANSWERED and said nothing filled, so no
#: trade happened. Its own reason rather than reusing an existing one, because
#: an operator meeting it must not go looking for a rejected order -- the
#: placement was accepted and the FOK simply found no counterparty.
_REASON_ENTRY_EXPIRED = "entry_leg_expired"

#: The close path PLANNED and did not act. One reason per verdict, because an
#: operator acts differently on each: a reserved sell is work waiting on C5, an
#: already-closed position is the reconciler's to book, and a halt is a state
#: nobody may sell against. Reusing one string would collapse three responses
#: into one line -- the shape `_REASON_PENDING`'s comment already rejects.
_REASON_CLOSE_SELL_RESERVED = "close_sell_reserved"
_REASON_CLOSE_ALREADY_CLOSED = "close_already_closed"
_REASON_CLOSE_HALTED = "close_halted"
#: The portfolio holds nothing for this symbol by the time dispatch runs.
#: Distinct from `RiskManager`'s `nothing_to_close`, which is the CORRECT
#: refusal made at evaluate time; this one means the position left between the
#: two, and an operator meeting it should look for what removed it.
_REASON_CLOSE_NO_POSITION = "close_no_position"
#: No numeric list id, so the cancel cannot be addressed. Ruling 1: the
#: documented `listClientOrderId` alternative has never been sent by this
#: project and an irreversible write does not gamble on an unmeasured wire
#: parameter.
_REASON_CLOSE_NO_VENUE_ID = "close_no_venue_list_id"
_REASON_CLOSE_CANCEL_FAILED = "close_cancel_failed"
#: The sell PROVABLY did not happen: this process refused to send it, so no
#: request left here and nothing can be resting. Its meaning NARROWED at B1 --
#: it used to cover every exception out of the sell, including the ones where
#: the venue may have filled. It now names only the class the marker
#: `ClientRefusalError` identifies, which is the one case where "failed" is a
#: fact rather than an assumption about a venue we could not reach.
_REASON_CLOSE_SELL_FAILED = "close_sell_failed"
#: The sell was SENT and its outcome is unknown. Deliberately NOT
#: `_REASON_CLOSE_SELL_FAILED`: "failed" asserts a venue state this client does
#: not possess, and an operator who reads a failure acts as though nothing was
#: sold. Ruling 2.
_REASON_CLOSE_SELL_UNCONFIRMED = "close_sell_unconfirmed"
_REASON_CLOSE_PARTIAL_FILL = "close_partial_fill"

#: One refusal reason per verdict, as a total mapping rather than a chain of
#: ``if``s. Exhaustive by construction: `CloseAction` has three members and a
#: fourth would raise `KeyError` at the site rather than falling through to a
#: default, which is the same reason `plan_close` has no trailing ``else``.
_CLOSE_REFUSALS: Final[dict[CloseAction, str]] = {
    CloseAction.SELL: _REASON_CLOSE_SELL_RESERVED,
    CloseAction.ALREADY_CLOSED: _REASON_CLOSE_ALREADY_CLOSED,
    CloseAction.HALT: _REASON_CLOSE_HALTED,
}

#: The generation the confirm step derives leg ids at. Zero, and NOT read off
#: the position -- `Position` carries no generation. The same constant
#: `reconcile_open_positions` uses under the same name-in-spirit, for the same
#: stated reason: nothing in this tree computes a non-zero generation yet.
_CLOSE_GENERATION: Final = 0

_REASON_UNPROTECTED = "unprotected_branch"
_REASON_NO_BUDGET = "budget_exhausted"
_REASON_PENDING = "placement_pending"
_REASON_CLIENT_REFUSAL = "client_refusal"
#: ITS OWN REASON, never the budget's and never the pending guard's. An
#: operator reading this must be sent to the DISK; reusing another string here
#: would send them to `dispatch_deadline_s` for a cause that is not there.
_REASON_STORE_UNWRITABLE = "store_unwritable"


@dataclass(frozen=True, slots=True)
class _CloseResolutionText:
    """Everything ONE close-resolution outcome says, as ONE value.

    **THE THREE FIELDS ARE ONE FACT AND MUST MOVE TOGETHER.** They are the
    machine-readable discriminator, the operator's instruction and the log
    line's human-readable headline -- three renderings of a single question,
    *what became of this close?* Holding them apart is what let the headline
    describe a design two commits old while the other two described the
    current one; see `_log_close_resolved` for what that cost.

    Same argument as `_EntryFill` below, from the other side: that type exists
    because one value collapsed two facts, this one because three values held
    one fact. Both are the file's answer to the same hazard.

    `message` carries its own ``%s`` for the symbol, so every branch takes the
    identical argument list -- which is the constraint that keeps the call site
    free of a second branch.
    """

    outcome: str
    resolution: str
    message: str


#: The sell filled and ruling 5 booked it.
_RESOLVED_BOOKED: Final = _CloseResolutionText(
    outcome="filled_and_booked",
    resolution=(
        "THE SELL FILLED and THIS BOT HAS BOOKED IT. The position is closed, the "
        "proceeds are credited and the realised P&L is accrued from the VENUE'S "
        "own quote total. The pending record is gone from memory and from the "
        "store. DO NOT enter this trade by hand -- the ledger already carries it. "
        "Trading continues."
    ),
    message=(
        "%s: a pending close record was resolved -- the sell FILLED and the trade is "
        "BOOKED; the venue's figures are recorded below"
    ),
)

#: The sell filled and could not be priced, so it is dropped without booking.
#:
#: **READ FROM TWO SITES, AND THAT IS WHY THE BALANCE-SHEET SENTENCE LIVES
#: HERE.** `_log_close_resolved` renders it for a record resolved a bar later,
#: and `_sold_unbooked` reads `outcome` and `resolution` off it for the bot's
#: own completed sell -- ruling 1 requires the two to present the IDENTICAL
#: operational surface, and sharing the value is what makes that true by
#: construction rather than by two strings kept in step by hand. So the
#: sentence is added ONCE. Do not copy it to a second site.
#:
#: **THE BALANCE-SHEET SENTENCE IS `M5i-042`, MEASURED at `52.250000000`** on
#: the close suite's own figures: `51.25000000` of proceeds never credited plus
#: `1.000000000` of open-time over-debit, the latter fired by this very state
#: because `_open_position` falls back to the REQUESTED limit when there is no
#: fill price. Every reader of `free_quote` moves CONSERVATIVELY on it --
#: affordability refuses, `equity` understates, sizing shrinks and the
#: daily-loss threshold tightens -- so it costs opportunity, never safety. It
#: is said anyway: an operator watching entries be refused has nothing else
#: connecting that to this line.
_RESOLVED_RELEASED: Final = _CloseResolutionText(
    outcome="filled_and_released",
    resolution=(
        "THE SELL FILLED and NOTHING WAS BOOKED by this bot. The position is "
        "released and the pending record is gone from memory and from the store. "
        "That trade is NOT in the ledger -- enter the executed quantity and quote "
        "total below by hand. Trading continues. NOTE THE BALANCE SHEET: the free "
        "quote balance is NOT credited here, so it stays short by those proceeds "
        "until the next restart re-seeds it from the venue -- entries may be "
        "refused or under-sized until then."
    ),
    message=(
        "%s: a pending close record was resolved -- the sell FILLED and was DROPPED "
        "UNBOOKED; the venue's figures are recorded below for manual accounting"
    ),
)

#: Nothing confirms the sell. **The message may not claim a venue answer**: this
#: branch is reached both when the venue answered with nothing filled AND when
#: the query raised and there is no answer at all -- `M5i-012`. "what is known"
#: is true of both; "the venue's answer" is false of the second.
_RESOLVED_RETAINED: Final = _CloseResolutionText(
    outcome="unconfirmed_position_retained",
    resolution=(
        "THE SELL IS UNCONFIRMED, so BASE INVENTORY MAY STILL BE AT THE VENUE. "
        "NOTHING WAS BOOKED, and whether anything was SOLD is exactly what is "
        "unknown. The pending record is gone, but "
        "the POSITION IS RETAINED with its protection marked UNKNOWN -- so entries "
        "on this symbol are refused, AND entries on EVERY symbol are refused while "
        "committed risk cannot be summed. Exits are still permitted. Check the "
        "account: sell the base by hand if it is there, then restart."
    ),
    message=(
        "%s: a pending close record was resolved -- the sell is UNCONFIRMED and the "
        "POSITION IS RETAINED; what is known is recorded below"
    ),
)

#: The sell filled, booking was ATTEMPTED, and the write FAILED. **The fourth
#: outcome, and it exists because the label became a CONSEQUENCE** -- `M5i-055`.
#:
#: **IT CANNOT REUSE `_RESOLVED_RELEASED`, and the reason is one clause.** That
#: text opens *"The position is released"*, which is TRUE when booking was never
#: attempted and FALSE here: `close_position` raised, so the symbol is still in
#: `positions`. Reusing it would swap a label that lies about the ledger for one
#: that lies about the position -- the same trade `M5i-007` refused one commit
#: earlier, in the other direction.
#:
#: **AND IT IS THE STATE `M5h-370`/W1 SAYS NOTHING COULD SEPARATE.** V2, booking
#: never ran, and V5, booking ran and wrote nothing, leave IDENTICAL portfolio
#: state and were indistinguishable from any assertion over it. They are not the
#: same fact: V5 may carry the C12 residual, because `close_position` credits
#: `free_quote` BEFORE it accrues, so the proceeds can land with the P&L
#: unaccrued. This label is what separates them.
#:
#: The wording is the ARCHITECT'S ruling, not the project owner's: it is new
#: text for a state that has never occurred, and it is reversible in one commit.
_RESOLVED_BOOK_FAILED: Final = _CloseResolutionText(
    outcome="filled_and_book_failed",
    resolution=(
        "THE SELL FILLED and BOOKING IT FAILED. That is NOT the same as nothing "
        "being booked: the write was ATTEMPTED, so the ledger may be HALF-APPLIED. "
        "Booking credits the free quote balance BEFORE it accrues the realised "
        "P&L, so the proceeds may be credited with the P&L unaccrued. DO NOT "
        "assume the ledger is untouched, and DO NOT assume it holds this trade. "
        "THE POSITION IS STILL IN MEMORY while the venue is flat, so this bot's "
        "book and the account disagree about what is held. Check the free quote "
        "balance and the realised P&L against the venue before acting; the error "
        "that caused this is recorded below."
    ),
    message=(
        "%s: a pending close record was resolved -- the sell FILLED and BOOKING IT "
        "FAILED; the POSITION SURVIVES and the ledger may be half-applied"
    ),
)


@dataclass(frozen=True, slots=True)
class PendingPlacement:
    """A placement whose outcome we did not observe, awaiting resolution.

    **Every field is something WE REQUESTED, never something the venue
    reported.** That is the line this type is drawn along, and it is the whole
    of why the record is safe to hold.

    The first three are ID SEEDS: Q-C section 6 makes a generation-0 client
    order id derivable from ``(symbol, entry_bar_time, generation)`` by pure
    computation, so they are *reconstructible input* -- what the query needs to
    re-derive the ids we would have sent.

    **The last four are the requested ECONOMICS** -- ``quantity``,
    ``entry_limit`` and the two protective levels -- and they sit on the same
    side of that line for the same reason. Every one is computed by our own
    risk layer BEFORE any venue contact, so carrying them forward is carrying
    our own arithmetic, not an observation. Q-C keys reconciliation off what
    was **requested** rather than off what the venue holds, which is precisely
    the category these belong to. R23, ruled by the reviewer under delegation.

    **THE LINE, STATED SO IT CAN BE ENFORCED: a record of OUR INTENT, never a
    shadow of venue state.** ``executedQty``, a fill price, a leg status or an
    ``orderId`` fall on the OTHER side and **must never be added here**. Those
    are facts a ``Position`` or the venue owns, and duplicating one into this
    record is exactly the second-source-of-truth the reconciliation driver
    refused to become.

    This widens the type's own justification rather than contradicting it: an
    earlier version of this docstring said "three fields, and every one of them
    is a SEED", which was true of what it then held and stated the boundary
    more narrowly than the boundary actually is.

    **Why this is NOT the cross-pass state the reconciliation driver refused.**
    That refusal is quoted in ``docs/NEXT_MILESTONE.md`` in these words: the
    N-cycle counter "needs cross-pass state, which the driver commit
    deliberately refused to hold, on the grounds that **a driver holding
    position state becomes a second source of truth for a fact the position
    already owns**." The operative words are *position state*. This record
    exists precisely because **there is no position** -- whether one was opened
    is the unknown it exists to resolve -- so there is no owner for it to
    duplicate and no second source of truth to create. It is deleted the moment
    the question is answered, in either direction.
    """

    symbol: str
    entry_bar_time: datetime
    generation: int
    quantity: Money
    entry_limit: Money
    stop_loss: Money | None
    take_profit: Money | None
    #: The union tag. LAST because it has a default and the others do not, and
    #: defaulted so every existing construction in this tree and its tests is
    #: unchanged -- the tag adds a discriminator without adding a keyword to
    #: forty call sites.
    kind: Literal["placement"] = "placement"


@dataclass(frozen=True, slots=True)
class PendingClose:
    """A discretionary close whose outcome we did not observe.

    **The sibling of :class:`PendingPlacement`, and it holds FOUR fields where
    that holds seven.** The difference is not economy: an exit HAS no
    ``entry_limit``, because Q-C section 4b dispatches a ``MARKET`` sell, and
    it has no ``stop_loss`` or ``take_profit``, because it removes protection
    rather than requesting it. ``PendingPlacement``'s line is *"every field is
    something WE REQUESTED"*; a limit price on a market order is not something
    anyone requested, so carrying one would be a fabricated value in the one
    type whose whole justification is that it holds none.

    That is why this is a sibling rather than a widening. Making
    ``entry_limit`` optional on ``PendingPlacement`` would put three fields
    that are meaningless for half its instances into one type, and would erase
    the inclusion test that makes the record safe to hold.

    **The first three fields are the ID SEEDS**, exactly as they are next door,
    and they carry the same guarantee: ``close_client_order_id`` derives the
    sell's identity from ``(symbol, entry_bar_time, generation)`` by pure
    computation, so a restarted process can query the ID it *would have sent*
    without ever having stored it. ``entry_bar_time`` is the POSITION'S entry
    bar -- see that function for why the close's own bar cannot serve.

    ``quantity`` is the fourth and is the requested economics in full: what we
    asked the venue to sell. It falls on the requested side of the line.

    **What must never be added here is what must never be added there**:
    ``executedQty``, a fill price, an order status or an ``orderId``. Those are
    venue facts, and this type is a record of our intent.

    **TWO SITES CONSTRUCT ONE, AND THIS PARAGRAPH SAID NONE DID.
    ``M5i-018``.** It read *"NOTHING CONSTRUCTS ONE. The dispatch path that
    would is Q-C section 4b's, and the executor still refuses ``CLOSE`` by
    name"* -- true when written, false since the close path landed. The two
    doors are :meth:`OrderExecutor._execute_close`, which records the sell it
    just sent, and ``engine/modes.py``'s boot restore, which rebuilds one from
    the store. They produce IDENTICAL objects: no field distinguishes them, and
    :meth:`OrderExecutor._resolve_close` therefore cannot know which door a
    record came through -- which is why its log line says "a pending close
    record" and not "a restored" one (``M5i-011``).

    **WHY IT WENT STALE IS A MECHANISM, NOT AN OVERSIGHT -- ``M5i-025``.** The
    struck sentence ended *"this is the shape arriving before its writer, as
    ``persist_pending`` and ``persist_ledger`` each did one commit before
    theirs"*. That pattern is deliberate and is declared in four docstrings
    here; what it does not carry is anything that schedules the correction when
    the writer lands. Two of the four were stale when surveyed. The `tests/`
    side of this one WAS corrected, in ``TestThePendingUnion``'s docstring,
    and this copy was not -- the commit doing the work edits the test and
    leaves the type alone.
    """

    symbol: str
    entry_bar_time: datetime
    generation: int
    quantity: Money
    #: The union tag; see :attr:`PendingPlacement.kind`.
    kind: Literal["close"] = "close"


#: One unresolved write against one symbol, of either kind.
#:
#: **ONE KEYSPACE, and that is the ruling rather than a convenience.** Both
#: kinds live in ``OrderExecutor._pending``, keyed by symbol, because the
#: EXISTING guard -- ``if signal.symbol in self._pending`` -- then refuses an
#: entry while an exit is unresolved with no rewrite of entry gating at all. A
#: separate dictionary for closes would leave that guard blind to them, and an
#: entry could dispatch on a symbol the bot is midway through exiting.
#:
#: Discriminated by ``kind`` rather than by ``isinstance``, so a narrowing that
#: forgets a member fails the TYPE CHECK rather than falling through at
#: runtime.
Pending = PendingPlacement | PendingClose


if TYPE_CHECKING:  # pragma: no cover - typing only
    #: Writes the WHOLE pending set durably. **Raising means the write did NOT
    #: happen**, and the caller must treat the record as non-existent.
    #:
    #: A callable rather than an imported module, so ``execution/`` never
    #: depends on ``persistence/``: `CLAUDE.md` has outer layers "depend inward
    #: only", and the composition root is the one layer permitted to know both.
    #: It is also what keeps the whole-file ``store.save`` safe -- the root owns
    #: the ledger this executor never sees.
    #:
    #: Declared HERE rather than in the import block above because it names
    #: ``Pending``, which is defined immediately above it. A forward reference
    #: would need a quoted name, and this project's style forbids those in new
    #: code.
    #:
    #: **It takes the UNION, so the root's closure must map both kinds.** That
    #: is contravariance doing useful work: a closure written for placements
    #: alone stops satisfying this alias, and mypy names the site rather than
    #: letting a close reach a mapper that would drop it.
    PendingWriter = Callable[[tuple[Pending, ...]], None]


@dataclass(frozen=True, slots=True)
class _EntryFill:
    """What the working-leg query established -- THREE states, not two.

    **A bare ``Money | None`` collapsed two facts that want opposite actions**,
    which is why this type exists. ``None`` meant both "the venue answered and
    the leg did not fill" and "we could not ask", and the guard below must
    refuse on the first and proceed on the second. This is the project's
    ordinary idiom for the same reason ``SizingDecision`` and
    ``ProtectionAssessment`` are values carrying their reason: a verdict is
    never a bare ``None``.

    * ``price`` set                     -- FILLED. Open the position.
    * ``price`` ``None``, answered      -- EXPIRED. No trade happened.
    * ``price`` ``None``, not answered  -- UNKNOWN. The venue did not say.
    """

    price: Money | None
    #: Whether the venue answered at all. ``False`` means the query failed, so
    #: nothing about the leg is known -- NOT that the leg did not fill.
    answered: bool

    @property
    def expired(self) -> bool:
        """The venue answered and the leg did not fill. The only refusable state."""
        return self.answered and self.price is None


class OrderExecutor:
    """Dispatches approved entries; resolves ambiguous writes on the next bar."""

    def __init__(
        self,
        *,
        client: ExchangeClient,
        portfolio: Portfolio,
        budget: DispatchBudget,
        persist_pending: PendingWriter | None = None,
        restored_pending: Sequence[Pending] = (),
    ) -> None:
        """Build the executor, optionally seeded with records from a prior process.

        **A RESTORED RECORD IS A QUESTION, NOT AN ANSWER.** It says only that
        some earlier process sent a placement and never learned the outcome --
        exactly what ``PendingPlacement`` means in the running process. It is
        **not** evidence that a list rests at the venue, and it must never be
        read as one: ``NOT_PLACED`` is a real and expected verdict for a
        restored record, because the request may never have reached the venue
        at all.

        **The answer comes from the existing first-candle path.** :meth:`__call__`
        runs ``resolve_placement`` over each record out of that bar's fresh
        dispatch budget and acts on the verdict -- ``PLACED_LIVE`` opens the
        position, ``NOT_PLACED`` deletes the record and reports a missed trade,
        ``UNRESOLVED`` keeps it for the next bar and re-places nothing. Nothing
        resolves at construction, and nothing here performs I/O.

        **What restoring buys, stated as the failure it removes.** Without it a
        process that died between an ambiguous write and its resolution lost the
        only record that a list might be resting -- in-process state, gone with
        the process, and ``reconcile_open_positions`` structurally silent
        because it iterates positions and there was none. That is named in
        ``CLAUDE.md`` as the whole of what fail-closed could not bound: *"a
        crash between the ambiguous write and the next bar loses the only record
        that a list may be resting."* The bound is now a restart rather than
        nothing.

        **``dispatch`` refuses a symbol carrying a restored record**, by the
        same pending guard that refuses one placed this session -- the guard
        reads ``_pending`` and does not care where an entry came from. So a
        restored record cannot be pyramided onto while it is unresolved.

        ``restored_pending`` defaults to empty, so every caller and test that
        predates it is unchanged. **Records are keyed by symbol**, matching the
        dict this executor has always kept; the store is written from that same
        dict and so cannot produce two records for one symbol, but a
        hand-edited file could, and the later one would win silently.
        """
        self._client = client
        self._portfolio = portfolio
        self._budget = budget
        #: ``None`` means DO NOT PERSIST, and that default is what keeps every
        #: existing test and any caller not yet updated byte-for-byte
        #: unchanged. The composition root supplies the real writer.
        self._persist_pending = persist_pending
        self._pending: dict[str, Pending] = {record.symbol: record for record in restored_pending}

    # -- Option 4 resolution, on the candle subscription --------------------
    async def __call__(self, candle: Candle) -> None:
        """Resolve any ambiguous placement, at the START of the bar.

        **This is Option 4, and the ordering is structural rather than
        remembered.** ``_notify`` runs candle subscribers in registration
        order and the engine registers its own hook inside ``start()`` -- after
        the composition root has yielded -- so subscribers registered at boot
        always run before any signal is evaluated. Registering the reconciler
        then this executor gives, on every bar: reconcile, resolve, then decide.
        A resolution therefore lands **before any new dispatch**, out of this
        invocation's fresh ``D`` rather than out of the exhausted budget of the
        invocation that created the ambiguity.

        **THE ORPHAN WINDOW, which is Option 4's whole cost.** Between the
        ambiguous write and this resolution -- up to one bar, 60s on the
        shipped 1-minute pair list -- an order list may be resting at the venue
        while ``has_position`` is false for that symbol. What that permits is
        specific: a second ``BUY`` on the same symbol in that window passes
        ``ALREADY_IN_POSITION``, because the guard reads a portfolio that has
        no position in it. Nothing here closes that; :meth:`dispatch` refuses
        while a placement is pending, which narrows it to the case where the
        process dies inside the window.

        **Under FAIL-CLOSED, an ``UNRESOLVED`` verdict means NO RE-PLACE.** The
        record is kept and retried on the following bar; it is never resolved
        by resending. See the findings block of the commit that added this for
        the ``CLAUDE.md`` rule that says the opposite and is not edited here.

        A ``CandleHandler``; never raises.
        """
        if not self._pending:
            return
        now = utc_now()
        started_at = now
        for symbol, record in list(self._pending.items()):
            # BOUNDS FIRST, BECAUSE BOTH KINDS NOW MAKE A VENUE CALL. This sat
            # BELOW the kind guard while a close did nothing, so the close
            # branch had no bounds to spend and none to be refused by. Hoisting
            # it puts both resolutions under one budget and preserves the skip
            # rule: a record that cannot BEGIN survives to the next bar, which
            # is the same thing an exhausted budget has always done to it.
            bounds = self._budget.bounds_for_next_call(started_at=started_at, now=utc_now())
            if bounds is None:
                # Out of budget this bar. The record survives to the next one --
                # that is the whole point of holding it.
                break
            if record.kind != "placement":
                # A CLOSE IS RESOLVED BY A DIFFERENT INSTRUMENT, and this
                # branch used to say so and then do nothing.
                #
                # `resolve_placement` cannot answer for one. It derives the
                # `listClientOrderId` of the ENTRY's order list -- a DIFFERENT
                # id from the close sell's, which carries the `CL` suffix -- so
                # it answers about the entry throughout. MEASURED against the
                # real function with close-shaped arguments: three answers,
                # none about the sell. `NOT_PLACED` when no list is enumerated;
                # `PLACED_TERMINAL` reasoning "no position was opened" when the
                # cancelled entry list is still enumerable; and `PLACED_LIVE`
                # when the cancel has not landed, which reaches the branch
                # below that RECORDS A POSITION -- for a symbol being closed.
                #
                # `_resolve_close` asks the right question instead: a
                # `get_order` against the derived close id. What it does with
                # the answer is LOG it. The action -- clear the lock, drop the
                # position unbooked, escalate -- is the same whatever comes
                # back, including nothing.
                #
                # WRAPPED LIKE THE PLACEMENT CALL BELOW, and for the same
                # reason: this method is a `CandleHandler` and NEVER RAISES.
                # `_resolve_close` is written not to, but it is one `finally`
                # deep and the promise belongs to this loop rather than to the
                # method it calls.
                try:
                    await self._resolve_close(record, candle, bounds=bounds)
                except Exception as exc:  # never raises; see the module docstring
                    self._log_failure("resolve-close", symbol, exc)
                continue
            try:
                verdict = await resolve_placement(
                    self._client,
                    symbol=symbol,
                    entry_bar_time=record.entry_bar_time,
                    generation=record.generation,
                    timeout_s=bounds.timeout_s,
                    attempts=bounds.attempts,
                )
            except Exception as exc:  # never raises; see the module docstring
                self._log_failure("resolve", symbol, exc)
                continue

            if verdict.outcome is PlacementOutcome.UNRESOLVED:
                # Fail-closed: keep the record, do NOT re-place.
                #
                # ITS OWN EVENT NAME. Under fail-closed this is the branch that
                # LEAVES AN ORPHANED LIST -- the record survives, nothing is
                # re-placed, and a list may be resting at the venue that the
                # portfolio does not know about. A reader filtering on
                # `placement_resolved` and counting this as one of them is wrong
                # in the expensive direction: they would see a resolution rate
                # of 100% while every attempt was failing.
                _log.warning(
                    "Placement still unresolved",
                    extra={
                        "event": _EVENT_UNRESOLVED,
                        "symbol": symbol,
                        "outcome": verdict.outcome.value,
                        "reason": verdict.reason,
                        "candle_time": candle.close_time.isoformat(),
                    },
                )
                continue

            # R24. A LIVE list means the working leg FILLED, so a position
            # exists and this is where it gets recorded.
            #
            # WHAT THIS CLOSES. Until R24 every branch here merely deleted the
            # record. A placement that landed but whose response we never saw
            # therefore left a live list at the venue with NO `Position` and NO
            # debit: `has_position` false, so a later `BUY` pyramids onto it;
            # `free_quote` overstated by the committed cost, so every subsequent
            # size is computed against money already spent; and nothing for
            # `reconcile_open_positions` to iterate, because it iterates
            # `portfolio.open_positions`. UNBOUNDED, because the record was
            # deleted and nothing retried.
            #
            # THAT IS THE OUTCOME FAIL-CLOSED EXISTS TO PREVENT, reached through
            # the branch that SUCCEEDS rather than the one that fails. The
            # `UNRESOLVED` branch above is careful never to strand a list; this
            # one stranded every list it successfully found.
            #
            # WHY LIVE AND TERMINAL ARE NOT ONE BRANCH. Q-C section 3 fixes the
            # working leg as `LIMIT`+`FOK`, which cannot rest -- it fills or
            # expires at once. So a list still EXECUTING has passed its working
            # leg and its pendings are live: capital is committed. A TERMINAL
            # list is the opposite and it is MEASURED: six probe lists with a
            # FOK working leg read ALL_DONE/ALL_DONE, every leg EXPIRED,
            # `executedQty` 0. Constructing a position there would INVENT one
            # and debit `free_quote` for money never spent. The S5 reading of
            # terminal -- filled, then protection triggered (M5f-037) -- agrees
            # on the treatment for a different reason: that position has already
            # closed, so opening one now would also be wrong.
            #
            # THE LIVE HALF IS INFERRED, NOT MEASURED, and C3 said so when it
            # shipped the classifier: "a falsification of the live half lands on
            # the RISK PATH." This is that path.
            if verdict.outcome is PlacementOutcome.PLACED_LIVE:
                # THE RECOVERY PATH QUERIES TOO, and without it every restored
                # position would be permanently unbookable. `PendingPlacement`
                # carries only what we REQUESTED -- that is the line the type
                # is drawn along -- so a fill price can never come from the
                # record and must come from the venue.
                #
                # Charged to this bar's budget, unlike the dispatch path's:
                # the loop above re-reads the clock, so this call really is
                # bounded by what remains.
                fill = await self._entry_fill_price(
                    symbol=symbol,
                    entry_bar_time=record.entry_bar_time,
                    generation=record.generation,
                    timeout_s=bounds.timeout_s,
                    attempts=bounds.attempts,
                )
                # NO EXPIRY GUARD HERE, DELIBERATELY, and it is not an
                # oversight. The verdict already IS the guard: `PLACED_LIVE`
                # means the list is live at the venue, and a live list "has
                # passed its working leg and its pendings are live: capital is
                # committed" -- an expired FOK yields `PLACED_TERMINAL`, whose
                # branch constructs nothing. Refusing here on a leg query that
                # disagreed with the verdict would discard a position
                # `resolve_placement` proved exists, which is the orphan
                # direction. The purpose-built instrument wins over the
                # follow-up read.
                self._open_position(
                    symbol=symbol,
                    quantity=record.quantity,
                    entry_limit=record.entry_limit,
                    entry_fill_price=fill.price,
                    stop_loss=record.stop_loss,
                    take_profit=record.take_profit,
                    entry_bar_time=record.entry_bar_time,
                    # A RESTORED POSITION GETS BOTH, and that was not obvious.
                    # `PendingPlacement` carries only what we requested, so the
                    # venue's number cannot come from the record -- but
                    # `resolve_placement` enumerates real `OrderList` objects
                    # from the venue, and the one it matched carries it. So the
                    # recovery path is no worse off than the dispatch path.
                    order_list_id=_matched_list_id(verdict),
                    venue_order_list_id=_matched_venue_list_id(verdict),
                )

            del self._pending[symbol]
            self._persist_after_removal(symbol)

            if verdict.outcome is PlacementOutcome.NOT_PLACED:
                # THE TRADE IS GONE, NOT DEFERRED, and it now says so.
                #
                # `NOT_PLACED` IS AN INFERENCE, NOT AN OBSERVATION. It means
                # "no list on the account carried our id", which covers at
                # least THREE venue states that want different things:
                #   1. the request never reached the venue -- nothing created;
                #   2. it reached the venue and was REJECTED at submission --
                #      band, filter, -1106, insufficient balance -- so no list
                #      was ever created;
                #   3. a list WAS created but is absent from the enumeration.
                #      `get_all_order_lists` passes no `limit` and no `fromId`,
                #      and the window's size is UNMEASURED in this tree.
                # Do not read the event name as "confirmed not placed". State
                # 3 is the one in which something may be resting right now.
                #
                # WHY IT IS FINAL. `CLAUDE.md`: strategies are "**Edge-
                # triggered, not level-triggered.** A cross fires on the
                # transition bar and is silent while the condition persists".
                # So the signal will NOT be re-emitted on the next bar: this is
                # not a deferral, it is a trade the bot decided to take and did
                # not. Counting these against `order_placed` is the only way an
                # operator sees that rate at all.
                #
                # WHETHER TO RE-PLACE IS UNRULED. `CLAUDE.md`'s locked
                # timed-out-write rule prescribes the opposite of this branch
                # -- "Not found => nothing rests; re-place at the same
                # generation." Which is right is reserved to the project owner.
                # THIS COMMIT DELIBERATELY DOES NOT SETTLE IT: the branch still
                # deletes the record and re-places nothing. Only what it SAYS
                # has changed.
                _log.error(
                    "Dispatch missed; the trade will not be retried",
                    extra={
                        "event": _EVENT_MISSED,
                        "symbol": symbol,
                        "quantity": record.quantity,
                        "entry": record.entry_limit,
                        "stop_loss": record.stop_loss,
                        "entry_bar_time": record.entry_bar_time.isoformat(),
                        "reason": verdict.reason,
                        "candle_time": candle.close_time.isoformat(),
                    },
                )
                continue

            _log.info(
                "Placement resolved",
                extra={
                    "event": _EVENT_RESOLVED,
                    "symbol": symbol,
                    "outcome": verdict.outcome.value,
                    "reason": verdict.reason,
                    "quantity": record.quantity,
                    "entry": record.entry_limit,
                    "stop_loss": record.stop_loss,
                    "candle_time": candle.close_time.isoformat(),
                },
            )

    # -- dispatch, on the signal chain --------------------------------------
    async def dispatch(self, signal: Signal, assessment: RiskAssessment, candle: Candle) -> None:
        """Place the order ``assessment`` approved, if it is one this can place.

        ``candle`` supplies ``entry_bar_time``; see ``SignalHandler`` for why it
        is forwarded rather than re-read, and why ``Signal.timestamp`` is not
        used.
        """
        if not assessment.approved:
            return
        intent = assessment.intent

        # Refusal one: CLOSE is PLANNED AND REPORTED, and still refused.
        #
        # This branch used to refuse by name under `close_not_implemented`,
        # which fired 27 times across 8 supervised runs while saying nothing
        # about what an exit would have done. It now runs Q-C section 4b's READ
        # half -- confirm, then decide -- and refuses the sell.
        #
        # **NOTHING IRREVERSIBLE HAPPENS HERE.** No cancel, no sell, no
        # booking. The two point queries are reads. Every write in section 4b's
        # sequence is reserved.
        if not isinstance(intent, EntryIntent):
            await self._plan_close(signal, candle)
            return

        # R21, refusal two: the unprotected branch. Q-C section 2's fourth row
        # maps to a bare LIMIT+FOK with nothing resting behind it.
        #
        # THE CONFIGURATION REMAINS LEGAL AND CONSTRUCTIBLE -- this refuses
        # DISPATCH, not the config, and the distinction is the whole ruling.
        # Config load exists to refuse INCOHERENT configurations: a take-profit
        # sized off a stop distance that does not exist, a trailing level
        # nothing places. Both-disabled is not incoherent. It is a coherent
        # style the project deliberately supports -- `SignalAction.CLOSE`
        # exists so a strategy can own its exits -- and only DISPATCH makes it
        # dangerous, because only dispatch can leave money at the venue with
        # nothing protecting it. Refusing it at load would delete the style;
        # refusing it here deletes only the unprotected order.
        if intent.levels.stop_loss is None:
            self._refuse(signal, _REASON_UNPROTECTED, candle)
            return

        if signal.symbol in self._pending:
            # An unresolved placement for this symbol is outstanding. Dispatching
            # now could open a second position against the first -- the orphan
            # window narrowed to the process-death case. See __call__.
            #
            # ITS OWN REASON, not the budget's. This refusal and the one below
            # both stop a dispatch, and reusing one string for both would send
            # an operator to tune `dispatch_deadline_s` when the actual cause is
            # a placement nobody has resolved yet -- a wrong diagnosis reached
            # by reading a correct log line.
            self._refuse(signal, _REASON_PENDING, candle)
            return

        started_at = utc_now()
        bounds = self._budget.bounds_for_next_call(started_at=started_at, now=started_at)
        if bounds is None:
            self._refuse(signal, _REASON_NO_BUDGET, candle)
            return

        entry_bar_time = candle.close_time
        request = build_placement(intent, entry_bar_time=entry_bar_time)
        if isinstance(request, OrderRequest):  # pragma: no cover - unreachable
            # build_placement returns this only for the unprotected branch,
            # which the guard above has already refused. Defensive and named
            # rather than silent, because a future fourth branch would land here.
            self._refuse(signal, _REASON_UNPROTECTED, candle)
            return

        # Mark BEFORE the venue write. A record created after a call that never
        # returned would not exist, which is the exact state it is for.
        record = PendingPlacement(
            symbol=signal.symbol,
            entry_bar_time=entry_bar_time,
            generation=0,
            quantity=intent.quantity,
            entry_limit=intent.entry_limit,
            stop_loss=intent.levels.stop_loss,
            take_profit=intent.levels.take_profit,
        )
        # THE DURABLE WRITE GOES FIRST, because it is the FALLIBLE step and the
        # dict assignment is not. `CLAUDE.md`'s locked ordering -- "The fallible
        # step precedes the irreversible one ... Everything that can raise runs
        # first, so a failure leaves the object exactly as it was" -- applied
        # across two STORES rather than two fields. That is what makes the
        # refusal below need no rollback.
        if self._persist_pending is not None:
            try:
                self._persist_pending((*self._pending.values(), record))
            except Exception as exc:
                # REFUSE, never proceed. Placing without a durable record
                # recreates the unbounded state the store exists to close: an
                # order list resting at the venue that nothing knows about.
                # Nothing is marked and nothing has been sent, so this costs
                # exactly one trade. A full disk therefore HALTS ENTRIES on
                # every symbol until it is cleared -- the recoverable
                # direction, against an unrecorded live order list which has no
                # bound at all.
                self._log_failure("persist", signal.symbol, exc)
                self._refuse(signal, _REASON_STORE_UNWRITABLE, candle)
                return
        self._pending[signal.symbol] = record
        try:
            order_list = await self._place(request, bounds.timeout_s, bounds.attempts)
        except ClientRefusalError as exc:
            # NO REQUEST LEFT THIS PROCESS, so there is nothing to resolve.
            # Ruled by the PROJECT OWNER as "e3-narrow, at full scope".
            #
            # WHAT THIS BUYS. Every surviving pending record is now AMBIGUOUS
            # BY CONSTRUCTION with respect to client-side failure: the only
            # records that exist are ones where a request may have reached the
            # venue. A future re-place rule operating on records is therefore
            # already scoped to the failure `CLAUDE.md`'s locked timed-out-write
            # rule was written about -- WITHOUT retaining any classification on
            # the record. That is why (e2), retaining the failure reason on
            # `PendingPlacement`, was held rather than ruled: this delivers its
            # purpose as a side effect of recording less.
            #
            # THE ERROR DIRECTION, which is why only this half was ruled.
            # Misclassifying a client refusal as ambiguous costs one wasted
            # resolver call next bar. Misclassifying a VENUE failure as
            # client-side SKIPS RECOVERY on a placement that may have landed,
            # and no later edit un-places an order. The marker's silent failure
            # is the cheap one: an unmarked client refusal simply looks
            # venue-side and keeps its record.
            #
            # THE CASE THAT MOTIVATED THE RULING. `SymbolInfoNotPrimedError`
            # was added at C4-b to keep an UNBOUNDED call out of a BOUNDED
            # dispatch sequence -- and then caused a resolver call on the next
            # bar asking the venue about an id that was never sent. A fix
            # producing the cost it was written to prevent, one branch over.
            #
            # THE MARKER MEANS "NEVER SENT", NOT "OUR REFUSAL", and the
            # distinction is not decorative. Three client-side refusals in
            # `src/` deliberately do NOT carry it -- an unknown symbol after
            # `get_symbol_info` RETURNED, a malformed `exchangeInfo` after the
            # payload arrived, and an unparseable client order id on an order
            # the venue SENT US. In each the venue answered and the refusal is
            # ours. None of the three is on the placement path.
            self._pending.pop(signal.symbol, None)
            self._persist_after_removal(signal.symbol)
            _log.warning(
                "Dispatch refused before any request left the process",
                extra={
                    "event": _EVENT_REFUSED,
                    "symbol": signal.symbol,
                    "action": signal.action.value,
                    "reason": _REASON_CLIENT_REFUSAL,
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                    "candle_time": candle.close_time.isoformat(),
                },
            )
            return
        except Exception as exc:  # never raises; see the module docstring
            # EVERYTHING NOT MARKED KEEPS ITS RECORD, including venue refusals
            # that almost certainly did not land. That half is UNRULED and rests
            # on `CLAUDE.md`'s "a 429 is rejected pre-acceptance", which is
            # REASONING rather than measurement -- settling it needs a measured
            # rate-limited placement showing no order was created. And
            # `BinanceRequestException` is raised only AFTER a 2xx, when the
            # body will not parse, so for a placement the venue ACCEPTED and we
            # cannot read what it said: it leans toward LANDED and must keep its
            # record.
            #
            # U2 IS RULED, AND THIS IS READING A: THE DURABLE RECORD IS
            # DROPPED, THE IN-PROCESS RECORD IS KEPT. "Never persist
            # unconfirmed refusals" is satisfied literally -- nothing
            # unconfirmed reaches disk -- while `__call__` still resolves this
            # on the next bar. Only a restart forgets, which is exactly the
            # exposure that existed before this commit.
            #
            # THERE IS NO `pop` HERE, DELIBERATELY, and the reason is that this
            # branch is NOT a refusal branch. MEASURED: it catches three
            # classes. Venue refusals where nothing rests
            # (`InsufficientBalanceError`, `FilterRejectedError`,
            # `MalformedRequestError`, `ContractViolationError`,
            # `RateLimitError`, `OrderError`); UNKNOWN outcomes where a list
            # MAY be resting (`ExchangeConnectionError`, and the
            # `BinanceRequestException` raised only AFTER a 2xx); and
            # `DuplicateOrderError`, which Q-C section 8 classifies as a
            # SUCCESS signal -- a duplicate means the FIRST one landed.
            # Dropping the in-process record would remove the only mechanism
            # that ever finds such a list, on every occurrence rather than only
            # on a crash.
            #
            # So the two stores deliberately DISAGREE here and nowhere else:
            # disk forgets, memory remembers.
            self._persist_dropping(signal.symbol)
            _log.warning(
                "Placement outcome unknown; resolution deferred to the next bar",
                extra={
                    "event": _EVENT_AMBIGUOUS,
                    "symbol": signal.symbol,
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                    "entry_bar_time": entry_bar_time.isoformat(),
                },
            )
            return

        self._pending.pop(signal.symbol, None)
        self._persist_after_removal(signal.symbol)
        # THE SECOND AND LAST VENUE CALL OF AN ENTRY DISPATCH. The count is
        # pinned by a test on the fake client, because the coherence validator
        # contains no call count and cannot guard one -- and because this
        # project's own `dispatch_budget.py` records the dispatch call count as
        # having been MEASURED WRONG TWICE.
        #
        # It reuses `bounds` rather than asking for fresh ones, which is
        # honest about what the budget currently is: `bounds_for_next_call` is
        # consulted once on this path, with `now == started_at`, so nothing
        # re-measures and a second consultation would return the same numbers
        # while implying otherwise.
        fill = await self._entry_fill_price(
            symbol=intent.symbol,
            entry_bar_time=entry_bar_time,
            generation=0,
            timeout_s=bounds.timeout_s,
            attempts=bounds.attempts,
        )
        # P6, CLOSED HERE. Until this guard, a `Position` was constructed
        # unconditionally after a successful placement -- so an FOK that
        # EXPIRED produced a holding the account does not have.
        #
        # NOTHING RESTS, SO THERE IS NOTHING TO UNWIND. MEASURED, and the
        # resolution path above already says it: "six probe lists with a FOK
        # working leg read ALL_DONE/ALL_DONE, every leg EXPIRED, `executedQty`
        # 0." The pending record was popped and the durable set rewritten
        # before the query, which is already correct for this outcome: there
        # is no list to resolve on a later bar.
        #
        # THE SAME REASONING ALREADY RAN ON THE OTHER PATH. `PLACED_TERMINAL`
        # refuses to construct for exactly this, in those words -- "Constructing
        # a position there would INVENT one and debit `free_quote` for money
        # never spent". Dispatch simply never asked the question.
        #
        # ONLY A POSITIVE "DID NOT FILL" REFUSES. A failed query is NOT an
        # expiry: `fill.expired` requires the venue to have ANSWERED. Treating
        # silence as an expiry would refuse to record a position that may be
        # filled and protected at the venue -- an orphan of our own making,
        # which `M5h-097` names as the worst state this milestone recorded.
        # The opposite error, a phantom, is bounded: it is unbookable because
        # `unrealized_pnl` raises on an absent fill price, and the next boot
        # re-seeds `free_quote` from the venue.
        if fill.expired:
            self._refuse(signal, _REASON_ENTRY_EXPIRED, candle)
            return
        self._open_position(
            symbol=intent.symbol,
            quantity=intent.quantity,
            entry_limit=intent.entry_limit,
            entry_fill_price=fill.price,
            stop_loss=intent.levels.stop_loss,
            take_profit=intent.levels.take_profit,
            entry_bar_time=entry_bar_time,
            order_list_id=order_list.list_client_order_id,
            venue_order_list_id=_venue_list_id(order_list),
        )
        _log.info(
            "Order list placed",
            extra={
                "event": _EVENT_PLACED,
                "symbol": signal.symbol,
                "quantity": intent.quantity,
                "entry": intent.entry_limit,
                "stop_loss": intent.levels.stop_loss,
                # BOTH IDS, UNDER DISTINCT KEYS. `order_list_id` used to carry
                # the CLIENT id, which is how the first live run printed
                # `order_list_id=tb1-BTCUSDT-...-0-L` -- a venue-sounding key
                # holding a value the venue never issued. `order_list_id` now
                # means what it means everywhere else in this tree (`Order`,
                # `OrderList`, and `docs/QB_ESCALATION.md`'s CRITICAL schema):
                # the venue's numeric id. Ours gets its own key. Emitting both
                # rather than renaming one is what lets an operator move
                # between our log and the venue's UI without a lookup.
                "order_list_id": order_list.order_list_id,
                "list_client_order_id": order_list.list_client_order_id,
                "entry_bar_time": entry_bar_time.isoformat(),
            },
        )

    # -- internals ----------------------------------------------------------
    async def _place(
        self,
        request: OtocoOrderListRequest | OtoOrderListRequest,
        timeout_s: float,
        attempts: int,
    ) -> OrderList:
        """Dispatch by request type. No ``else`` here can occur."""
        if isinstance(request, OtocoOrderListRequest):
            return await self._client.create_otoco_order_list(
                request, timeout_s=timeout_s, attempts=attempts
            )
        return await self._client.create_oto_order_list(
            request, timeout_s=timeout_s, attempts=attempts
        )

    async def _entry_fill_price(
        self,
        *,
        symbol: str,
        entry_bar_time: datetime,
        generation: int,
        timeout_s: float,
        attempts: int,
    ) -> _EntryFill:
        """What the working leg actually filled at, and whether the venue said.

        **The working leg is TERMINAL by the time the placement returns, and
        that is why this belongs here rather than on a later bar.** Q-C
        section 3 fixes it as ``LIMIT``+``FOK``: fill-or-kill cannot rest, so
        it has filled completely or expired before the venue answers. A
        resting ``LIMIT`` would make a query at this moment useless.

        **REASONED, NOT MEASURED.** No entry leg has ever been point-queried
        in this project. The measured resting-leg shape -- ``status=NEW``,
        ``filled_quantity=0``, ``average_price=None``, observed on a
        ``STOP_LOSS`` and a ``TAKE_PROFIT`` across two symbols on 2026-09-02
        -- describes PROTECTIVE legs, which do rest, and must not be read as
        describing this one. What is measured is the leg TYPE; that FOK is
        terminal at return follows from it.

        **NEVER FALLS BACK TO THE REQUESTED LIMIT.** ``None`` on any failure,
        any timeout, and any leg reporting no fill. The limit is measured
        wrong by 76.65 and 2.09 per unit, and commit 4 made the ledger
        durable, so a fallback would write a permanent distortion that is
        afterwards indistinguishable from a correct figure. A refused booking
        is visible and recoverable; a corrupt one is neither.

        **Never raises.** A dispatch that placed successfully must not be
        turned into a failure by a follow-up read: the order list is already
        at the venue, and the position must be recorded whatever this returns.
        """
        try:
            order = await self._client.get_order(
                symbol,
                client_order_id=client_order_id(
                    symbol, entry_bar_time, OrderListLeg.WORKING, generation=generation
                ),
                timeout_s=timeout_s,
                attempts=attempts,
            )
        except Exception as exc:  # never raises; see the docstring
            # NOT ANSWERED. Nothing is known about the leg -- which is a
            # different fact from "it did not fill", and the caller acts on the
            # difference.
            self._log_failure("entry-fill-query", symbol, exc)
            return _EntryFill(price=None, answered=False)

        # A fill total with no quantity cannot yield a price, and an FOK that
        # expired reports exactly that. `average_price` is the venue's own
        # quotient; `filled_quote_quantity` is the total it came from. The
        # total is preferred nowhere here because a PRICE is what a position
        # stores -- the total's exactness matters at BOOKING, which divides
        # nothing.
        if order.filled_quantity <= 0 or order.average_price is None:
            _log.warning(
                "Entry leg reports no fill; the position's cost basis is unknown",
                extra={
                    "event": _EVENT_NO_ENTRY_FILL,
                    "symbol": symbol,
                    "status": order.status.value,
                    "filled_quantity": order.filled_quantity,
                },
            )
            # ANSWERED, and the answer was no. An FOK that found no
            # counterparty: no trade happened, and the caller refuses.
            return _EntryFill(price=None, answered=True)
        return _EntryFill(price=order.average_price, answered=True)

    def _open_position(
        self,
        *,
        symbol: str,
        quantity: Money,
        entry_limit: Money,
        entry_fill_price: Money | None,
        stop_loss: Money | None,
        take_profit: Money | None,
        entry_bar_time: datetime,
        order_list_id: str | None,
        venue_order_list_id: int | None,
    ) -> None:
        """Construct the position this placement opened, UNKNOWN until reconciled.

        **R19 / M5e-075: every ``Position`` is constructed with
        ``ProtectionState.UNKNOWN``.** M5e's grounds, and they are not restated
        loosely because the direction is the whole argument: a position wrongly
        marked ``UNKNOWN`` costs entries until the next pass corrects it, while
        one wrongly marked ``ACTIVE`` is priced off a stop nobody confirmed.

        **ONE CONSTRUCTION SITE, TWO CALLERS.** The dispatch success path and
        the ``PLACED_LIVE`` resolution branch both arrive here, taking values
        rather than an ``EntryIntent`` because the second has no intent -- it
        has the requested economics carried on its ``PendingPlacement``. A
        second construction site would be a second place for M5e-075's ruling
        to be forgotten.

        **A placement response is NOT an observation of what rests.**
        Acceptance is not activation. The venue has accepted a list; whether
        both protective legs are resting at their requested triggers for the
        requested quantity is a different question, answered only by reading
        what is there.

        **The reconciler is what promotes it.**
        ``reconcile_open_positions`` reads the venue, classifies, and writes
        ``ACTIVE`` when every requested leg is found. Until it does, this
        position counts as uncomputable committed risk and REFUSES ENTRIES
        portfolio-wide. **That is the designed behaviour, not a defect** -- it
        is why the reconciler shipped before the first order rather than after
        it, and why ``ACTIVE`` was admitted to ``_TRUSTED_PROTECTION``.
        """
        # **P6 IS CLOSED, AND NOT HERE.** This method still constructs
        # whatever it is asked to; the guard lives at the DISPATCH call site,
        # which is the only one that can reach an expired FOK. The other
        # caller, the `PLACED_LIVE` branch, is guarded by its verdict.
        #
        # It is deliberately NOT a guard on this method. `_open_position` takes
        # values rather than an outcome, and giving it one would move a
        # dispatch decision into a recorder -- the same reason
        # `Portfolio.open_position` takes a `cost` it does not compute.
        #
        # What survives from the pre-fix note: a position carrying
        # `entry_fill_price=None` is UNBOOKABLE, because `unrealized_pnl`
        # raises. That is now the fail-closed floor under the ambiguous case
        # rather than under the phantom, since the phantom no longer reaches
        # here.
        position = Position(
            symbol=symbol,
            side=PositionSide.LONG,
            quantity=quantity,
            entry_price=entry_limit,
            entry_fill_price=entry_fill_price,
            entry_bar_time=entry_bar_time,
            protection=ProtectionState.UNKNOWN,
            # BOTH IDENTIFIER SPACES, under names that say which is which. The
            # first is ours and the second is the venue's; see
            # `Position.order_list_id` for the run-1 defect that conflating them
            # produced, and why the differing types are load-bearing rather than
            # incidental.
            order_list_id=order_list_id,
            venue_order_list_id=venue_order_list_id,
            stop_loss=stop_loss,
            take_profit=take_profit,
        )
        # THE DEBIT USES WHAT THE VENUE ACTUALLY CHARGED. `Portfolio.
        # open_position` has always said `cost` must be "what actually left
        # the balance" and takes it as an argument for exactly that reason;
        # this caller was the one passing the wrong number. MEASURED apart by
        # 76.65 and 2.09 per unit -- 1.81 and 1.59 USDT on 2026-09-02's two
        # positions.
        #
        # WHERE THE ERROR WENT, and it is NOT the ledger. `close_position`
        # derives realised P&L from `unrealized_pnl`, which reads
        # `entry_fill_price` and never this debit -- so `realised_pnl` was
        # already correct once 6a landed. The debit's error lands in
        # `free_quote`, and closing credits back `quantity * exit_price`, so
        # it NEVER UNWINDS: a permanent per-trade drift for the life of the
        # process, bounded only by the next boot re-seeding from the venue.
        # `free_quote` feeds `equity`, which feeds sizing and the daily-loss
        # threshold.
        #
        # THE FALLBACK IS THE REQUEST, and the alternative was rejected.
        # `entry_fill_price` can be `None` -- a failed query, or an FOK that
        # expired -- so a debit must still be chosen. Refusing to record the
        # position instead would leave a filled entry and two resting
        # protective legs at the venue with nothing tracking them: an orphan
        # of our own making, which `M5h-097` records as the state persistence
        # exists to close. Falling back is wrong by a measured amount in the
        # CONSERVATIVE direction -- the request exceeded the fill on all five
        # measured instances, so the over-debit under-states `free_quote` --
        # and the position is UNBOOKABLE anyway, because `unrealized_pnl`
        # raises on an absent fill price. So the fallback's error cannot reach
        # the ledger.
        cost_basis = entry_fill_price
        if cost_basis is None:
            cost_basis = entry_limit
            _log.warning(
                "Debited at the REQUESTED limit; the fill price is unknown",
                extra={
                    "event": _EVENT_DEBIT_ESTIMATED,
                    "symbol": symbol,
                    "entry_limit": entry_limit,
                    "quantity": quantity,
                },
            )
        self._portfolio.open_position(position, cost=quantity * cost_basis)

    def _persist_after_removal(self, symbol: str) -> None:
        """Rewrite the durable set after ``symbol``'s record left ``_pending``."""
        self._persist_quietly(tuple(self._pending.values()), symbol)

    def _persist_dropping(self, symbol: str) -> None:
        """Rewrite the durable set WITHOUT ``symbol``, which stays in ``_pending``.

        The one site where the two stores disagree on purpose: U2's Reading A
        drops the durable record for an unconfirmed outcome while the
        in-process record survives to be resolved on the next bar. A separate
        method rather than a flag, because the two situations are genuinely
        different and the name is where that difference is stated.
        """
        self._persist_quietly(
            tuple(record for key, record in self._pending.items() if key != symbol), symbol
        )

    def _persist_quietly(self, records: tuple[Pending, ...], symbol: str) -> None:
        """Write ``records`` durably. **NEVER raises.**

        Deliberately the OPPOSITE of the write path's refusal, and the
        asymmetry is principled rather than pragmatic: it turns on which side
        of the venue call the failure falls.

        A failed WRITE happens BEFORE the call -- nothing is at the venue, so
        refusing costs one trade. A failed DELETE happens AFTER it: the order
        exists, there is nothing left to refuse, and the only cost of a stale
        record is one resolver call at the next boot, which queries the venue,
        gets an answer and removes it. Self-correcting, where a failed write is
        not. `CLAUDE.md`: a budget may refuse to BEGIN work, and must never
        abandon a write in flight.
        """
        if self._persist_pending is None:
            return
        try:
            self._persist_pending(records)
        except Exception as exc:  # never raises; see the module docstring
            self._log_failure("persist-delete", symbol, exc)

    async def _plan_close(self, signal: Signal, candle: Candle) -> None:
        """Q-C section 4b's READ half: confirm by query, decide, report, refuse.

        **IT PLANS AND IT DOES NOT ACT.** Section 4b's sequence is cancel ->
        confirm -> sell, and only the middle step runs here. No cancel is sent,
        no sell is dispatched, and nothing is booked. Every irreversible step is
        the commit that supplies the caller for `cancel_order_list`, which is
        deliberately still undeclared on the port -- finding GG binds a port
        declaration to its production caller, and this method is not one.

        **WHY IT RUNS AT ALL, given that it refuses either way.** The one thing
        nobody can answer from the tree is what section 4b's confirm step COSTS.
        `dispatch_deadline_s = 9.0` is a PLACEHOLDER, its four-call derivation
        is arithmetic rather than observation, and no close has ever run. This
        emits `elapsed_s` on every CLOSE signal, so the duration is measured in
        production before anything irreversible is written against it.

        **THE BUDGET WILL NOT MEASURE IT, WHICH IS WHY THIS DOES.** `dispatch`
        samples once, at ``bounds_for_next_call(started_at=x, now=x)`` -- zero
        elapsed, the full deadline granted -- and that sample is taken THIRTY
        LINES BELOW the branch that reaches here. So these reads are charged
        against nothing at runtime and would lengthen the candle pipeline
        unobserved. The elapsed field is the only instrument that will ever see
        them.

        **THEY ARE BOUNDED ANYWAY, and that is a locked decision rather than a
        precaution.** `CLAUDE.md`: *"the candle pipeline must never be blocked
        by latency we do not bound ourselves -- a budget, not an abstinence."*
        A fresh `started_at` opens a sequence, each read takes the remainder,
        and a read that cannot begin is refused rather than started. That is the
        same shape a full close will need, exercised early on its read half.

        **TWO READS, AND THE COUNT IS RULED.** The confirm step queries the
        PROTECTIVE legs only. The working leg is `LIMIT`+`FOK` and terminal at
        placement, so a point query on it costs a round trip and yields no
        protection state. A leg that was never requested is not queried, because
        it has no id to query -- so an OTO position reads once and a
        both-disabled position reads not at all, which `plan_close` answers with
        HALT on its empty-set row.

        **A LEG THAT CANNOT BE READ IS `executed=None`, NEVER `Decimal(0)`.**
        The verdict it produces is HALT, but the LOG distinguishes it from a leg
        that answered: an unreadable leg carries a null status and its error type
        appears beside it. Section 4b reads `executedQty`, not merely `status`,
        and `LegReport.executed` is the field that carries it -- a leg reporting
        FILLED with nothing executed decides on the quantity.

        **NOTHING CALLS `close_position` HERE, INCLUDING ON `ALREADY_CLOSED`.**
        A protective leg that filled while we were deciding means the position
        is gone at the venue -- and booking it is the next commit's, not this
        one's. The position stays in `portfolio.positions`, which is not a leak:
        the reconciliation driver's booking path is already live for exactly
        this shape, and it will see the filled leg on its next pass and book it.
        Doing it here would be a SECOND booking path racing that one.
        """
        position = self._portfolio.positions.get(signal.symbol)
        if position is None:
            # `RiskManager._exit_assessment` already refuses when nothing is
            # held, so reaching here means the position left between evaluate
            # and dispatch. Its own reason, not that one's: an operator meeting
            # this should look for what removed it.
            self._refuse(signal, _REASON_CLOSE_NO_POSITION, candle)
            return

        started_at = utc_now()
        legs, failures = await self._confirm_protective_legs(position, started_at=started_at)
        elapsed_s = (utc_now() - started_at).total_seconds()

        plan = plan_close(legs)
        reason = _CLOSE_REFUSALS[plan.action]

        extra: dict[str, object] = {
            "event": _EVENT_CLOSE_PLANNED,
            "symbol": signal.symbol,
            "decision": plan.action.value,
            "detail": plan.reason,
            "reads": len(legs),
            "elapsed_s": elapsed_s,
            "refused_as": reason,
            "candle_time": candle.close_time.isoformat(),
        }
        if position.order_list_id is not None:
            extra["list_client_order_id"] = position.order_list_id
        for report in legs:
            # ABSENT means the leg was never requested; NULL means it was
            # requested and could not be read. Two different facts, and the log
            # schema's absent-not-null rule is what keeps them apart.
            extra[f"{report.leg.lower()}_status"] = report.status
            extra[f"{report.leg.lower()}_executed"] = report.executed
        for leg_code, error in failures.items():
            extra[f"{leg_code.lower()}_error"] = error

        _log.info(
            "Close planned for %s: %s",
            signal.symbol,
            plan.action.value,
            extra=extra,
        )

        if plan.action is not CloseAction.SELL:
            # ALREADY_CLOSED and HALT both stop here, and neither books. A
            # filled leg means the reconciliation driver's booking path will
            # see it on its next pass; booking it here would be a SECOND path
            # racing that one.
            self._refuse(signal, reason, candle)
            return
        await self._execute_close(signal, position, candle)

    async def _execute_close(self, signal: Signal, position: Position, candle: Candle) -> None:
        """Q-C section 4b's IRREVERSIBLE half: cancel, re-confirm, sell, book.

        **THE FIRST PLACE THIS BOT WRITES AT A VENUE OF ITS OWN VOLITION.**
        Everything before it either read, or wrote an order the strategy asked
        for. This cancels protection and sells a position, and neither can be
        un-sent.

        **THE ORDER IS FORCED, and section 4b argues it rather than asserting
        it.** Sell-then-cancel leaves the position flat with a live protective
        leg, which can sell base no longer held. Cancel-then-sell leaves it open
        and unprotected between two calls we are actively making.
        *"Unprotected-and-known is preferable to protected-against-nothing."*

        **THE POSITION IS RE-CHECKED, and the state it guards is currently
        UNREACHABLE.** `_book_exits` runs at subscriber ZERO and may delete a
        position earlier in the same bar; dispatch is later. That cannot bite
        today, because `RiskManager._exit_assessment` then answers
        `nothing_to_close` and no `ExitIntent` is approved -- and because the
        whole chain runs on ONE task, so nothing interleaves with the awaits
        above. **Both of those are properties of other files.** D1 locked the
        single-task model precisely so `Portfolio` is not written from a task
        that is not reading it; if that ever changes, this guard is what stops a
        cancel being sent for a position that no longer exists -- a venue write
        against nothing.

        **THE UNPROTECTED WINDOW IS LOGGED ON ENTRY AND NOT ON EXIT**, and that
        is half of what section 4b asks for. There is no in-process exit event
        because the naked-position state does not resolve in-process; see
        :meth:`_go_naked`. Recorded rather than quietly dropped.
        """
        if self._portfolio.positions.get(signal.symbol) is not position:
            # See the docstring: unreachable today, guarded because the write
            # below is irreversible and the reasoning that makes it unreachable
            # lives in three other files.
            self._refuse(signal, _REASON_CLOSE_NO_POSITION, candle)
            return

        if position.venue_order_list_id is None:
            # RULING 1. The cancel endpoint takes the venue's numeric id, and
            # Binance documents `listClientOrderId` as an alternative --
            # **which this project has never sent.** Falling back to it would
            # stake an irreversible write on an unmeasured wire parameter when
            # the verified path is simply absent here. A refused close costs a
            # missed exit and the position keeps its protection; a cancel that
            # silently addressed nothing would leave both.
            self._refuse(signal, _REASON_CLOSE_NO_VENUE_ID, candle)
            return

        record = PendingClose(
            symbol=signal.symbol,
            entry_bar_time=position.entry_bar_time,
            generation=_CLOSE_GENERATION,
            quantity=position.quantity,
        )
        # RULING 3: THE DURABLE WRITE PRECEDES THE **CANCEL**, not the sell --
        # and that is a departure from `dispatch`'s ordering worth stating.
        # There, the record covers one venue write and precedes it. Here it
        # covers a SEQUENCE, and the first irreversible step is the cancel. A
        # persist that failed after the cancel would leave a position with its
        # protection gone and no durable trace that anything was attempted;
        # refusing here costs nothing, because nothing has been sent.
        if self._persist_pending is not None:
            try:
                self._persist_pending((*self._pending.values(), record))
            except Exception as exc:
                self._log_failure("persist-close", signal.symbol, exc)
                self._refuse(signal, _REASON_STORE_UNWRITABLE, candle)
                return
        self._pending[signal.symbol] = record

        _log.warning(
            "Cancelling protection to close %s; the position is unprotected from here",
            signal.symbol,
            extra={
                "event": _EVENT_CLOSE_WINDOW_OPEN,
                "symbol": signal.symbol,
                "venue_order_list_id": position.venue_order_list_id,
                "quantity": position.quantity,
                "candle_time": candle.close_time.isoformat(),
            },
        )

        started_at = utc_now()
        if not await self._cancel_protection(
            signal,
            position,
            candle,
            # Bound as an ``int`` at the one site that proved it is not ``None``,
            # so the narrowing travels with the value rather than being
            # re-established -- or asserted -- further down.
            venue_order_list_id=position.venue_order_list_id,
            started_at=started_at,
        ):
            return

        # RULING 4: RE-QUERY AFTER THE CANCEL. The plan's reads were taken
        # BEFORE it and cannot see a leg that filled DURING it -- which is the
        # one state that makes selling wrong, because the position would already
        # be closed. Section 4b places the confirm after the cancel for exactly
        # this, and `-2011` cannot distinguish already-cancelled from
        # already-filled, so the cancel's own response can never serve.
        legs, _failures = await self._confirm_protective_legs(position, started_at=started_at)
        confirmed = plan_close(legs)
        if confirmed.action is not CloseAction.SELL:
            _log.warning(
                "Close abandoned after cancel for %s: %s",
                signal.symbol,
                confirmed.action.value,
                extra={
                    "event": _EVENT_CLOSE_ABANDONED,
                    "symbol": signal.symbol,
                    "decision": confirmed.action.value,
                    "detail": confirmed.reason,
                    "candle_time": candle.close_time.isoformat(),
                },
            )
            # The legs are gone and nothing was sold. On ALREADY_CLOSED the
            # venue closed the position for us and the reconciler books it; on
            # HALT the state is unknown. Either way protection no longer rests,
            # so this is the naked state whether or not a sell was attempted.
            self._go_naked(signal, position, candle, _CLOSE_REFUSALS[confirmed.action])
            return

        await self._sell_and_book(signal, position, candle, started_at=started_at)

    async def _cancel_protection(
        self,
        signal: Signal,
        position: Position,
        candle: Candle,
        *,
        venue_order_list_id: int,
        started_at: datetime,
    ) -> bool:
        """Cancel the whole list. ``True`` to continue, ``False`` to stop.

        **ONE CALL, NOT THREE.** MEASURED at M5c: cancelling one leg
        auto-cancelled the others and the follow-up cancels returned ``-2011``.
        A close path driving three cancels to success would treat its own normal
        teardown as two errors.

        **``-2011`` IS NORMAL AND CONTINUES.** It means the list was already
        terminal -- and it cannot say whether that was a cancel or a FILL, which
        demand opposite actions. That ambiguity is not resolved here and must
        not be: the caller re-queries the legs immediately after, which is the
        only thing that separates them.

        **ANY OTHER FAILURE STOPS, AND PROTECTION IS LEFT IN PLACE.** The venue
        state is unknown, so selling could sell against a live stop. `CRITICAL`
        rather than a warning because entries are not blocked by this -- the
        position keeps whatever protection it has and nothing marks it -- so the
        log line is the only thing an operator gets.
        """
        bounds = self._budget.bounds_for_next_call(started_at=started_at, now=utc_now())
        if bounds is None:
            self._refuse(signal, _REASON_NO_BUDGET, candle)
            return False

        try:
            await self._client.cancel_order_list(
                position.symbol,
                venue_order_list_id,
                timeout_s=bounds.timeout_s,
                attempts=bounds.attempts,
            )
        except OrderNotFoundError:
            # `-2011`: already terminal. NORMAL, and the re-query decides what
            # it meant. Logged at INFO because it is an expected teardown
            # outcome rather than a fault.
            _log.info(
                "Order list for %s was already terminal at cancel",
                signal.symbol,
                extra={
                    "event": _EVENT_CLOSE_CANCEL_TERMINAL,
                    "symbol": signal.symbol,
                    "venue_order_list_id": venue_order_list_id,
                    "candle_time": candle.close_time.isoformat(),
                },
            )
            return True
        except Exception as exc:  # dispatch must never raise
            _log.critical(
                "Cancel failed for %s; the venue state is unknown and nothing was sold",
                signal.symbol,
                extra={
                    "event": _EVENT_CLOSE_CANCEL_FAILED,
                    "symbol": signal.symbol,
                    "venue_order_list_id": position.venue_order_list_id,
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                    "candle_time": candle.close_time.isoformat(),
                },
            )
            self._release_close(signal.symbol)
            self._refuse(signal, _REASON_CLOSE_CANCEL_FAILED, candle)
            return False
        return True

    async def _sell_and_book(
        self, signal: Signal, position: Position, candle: Candle, *, started_at: datetime
    ) -> None:
        """Send the MARKET sell and book what it returns. Never raises.

        **THE SELL IS `MARKET`**, which section 4b rules as *"the one place the
        design accepts unbounded slippage for certainty of exit"* -- a limit
        that missed would leave the position held AND unprotected, which is the
        state this whole sequence exists to minimise.

        **IT CARRIES A DERIVABLE CLIENT ID**, so a timed-out sell is resolvable
        by querying the id we WOULD have sent. C1 built that derivation; this is
        its first caller.

        **THE QUOTE TOTAL IS THE VENUE'S, NEVER A DERIVED PRICE.** Booking takes
        `exit_quote_total`, because recovering a price by dividing is MEASURED
        lossy -- run 3's own shape round-trips to a 28-digit residual, and
        `_dump_money` writes such a residual into `data/state.json` verbatim.

        **THE TAIL HAS THREE OUTCOMES, NOT TWO, AND THE ORDER OF THE LAST TWO IS
        LOAD-BEARING.** A partial or unpriced fill fails closed into
        `_go_naked`; a COMPLETE, PRICED fill against a position carrying no
        `entry_fill_price` is dropped UNBOOKED by `_sold_unbooked`; everything
        else books. The middle one is B-i and it is checked SECOND, after the
        partial guard -- `M5i-043`. MEASURED, three states driven through the
        pre-B-i tree: a partial fill with no cost basis reaches `_go_naked` with
        `close_partial_fill` and that is CORRECT, because base remains at the
        venue and the manual sale it instructs is the right action for the
        remainder. Reversing the two would convert that correct line into a
        claim the position was fully sold.

        **WHAT IT REPLACED WAS NOT A WORDING DEFECT** -- `M5i-045`. Before B-i
        this state fell through to `_book_close`, where `close_position` raised
        `ValueError` from `_realised_from_total` and the handler reported
        `close_book_failed`. MEASURED: the POSITION SURVIVED, in memory, for
        base already sold. Its legs were cancelled, so the classifier answers
        `DIVERGED` and re-stamps it every pass -- `POSITION_STALE` never fires,
        nothing books it, and `UNKNOWN` outside `_TRUSTED_PROTECTION` refuses
        entries PORTFOLIO-WIDE until a restart. That is `_go_naked`'s
        self-refreshing trap arriving without `_go_naked` being called.
        """
        bounds = self._budget.bounds_for_next_call(started_at=started_at, now=utc_now())
        if bounds is None:
            self._go_naked(signal, position, candle, _REASON_NO_BUDGET)
            return

        request = OrderRequest(
            symbol=position.symbol,
            side=OrderSide.SELL,
            type=OrderType.MARKET,
            quantity=position.quantity,
            client_order_id=close_client_order_id(
                position.symbol, position.entry_bar_time, generation=_CLOSE_GENERATION
            ),
        )
        try:
            # **THE SELL IS THE ONE CALL IN THIS SEQUENCE NOT BOUNDED BY `D`,
            # AND THE REASON IS THE PORT.** `ExchangeClient.create_order` takes
            # a request and nothing else -- no `timeout_s`, no `attempts` --
            # where the ADAPTER's own method accepts both. So the bounds
            # computed above cannot be handed to it, and the sell runs under the
            # client's default policy instead: `idempotent=False`, so retries
            # only on a rate limit, but up to `retry_attempts` at
            # `requests_timeout_s` each. `CLAUDE.md` records that worst case as
            # 43.5s, which EXCEEDS `dispatch_deadline_s = 9.0`.
            #
            # Not widened here: the port change is a separate decision and this
            # commit is authorised for one port method. Named rather than left
            # for a reader to discover, because "the sequence is bounded" is
            # true of three calls out of four and the fourth is the write.
            order = await self._client.create_order(request)
        except Exception as exc:  # dispatch must never raise
            self._log_failure("close-sell", signal.symbol, exc)
            # **THE PREDICATE IS THE MARKER, AND IT IS DELIBERATELY WIDE.**
            # `ClientRefusalError` means *no request left this process*, so the
            # sell provably did not happen: nothing rests, and the naked,
            # operator-only state `_go_naked` describes is the true one.
            # EVERYTHING ELSE retains, including outcomes the venue plainly
            # rejected.
            #
            # Wide on purpose, and the asymmetry decides it. Over-retaining
            # costs ONE query and ONE log line, because retention is
            # SINGLE-SHOT -- `_resolve_close`'s `finally` releases the record on
            # every branch, so a record held for an order that does not exist is
            # gone one bar later. Under-retaining discards the only tracking
            # handle for a position that MAY BE LIVE, and there is no third
            # option: `ExchangeAPIError` is produced BOTH by an unclassified
            # venue rejection AND by `BinanceRequestException`, which the
            # library raises only after a 2xx whose body will not parse -- the
            # most ambiguous outcome there is. `translate_binance_error` says so
            # at its own site and marks the split UNRULED, and `.code` cannot
            # separate them either.
            if isinstance(exc, ClientRefusalError):
                self._go_naked(signal, position, candle, _REASON_CLOSE_SELL_FAILED)
            else:
                self._go_naked_retaining(signal, position, candle)
            return

        total = order.filled_quote_quantity
        if total is None:
            # P-c's fallback. `newOrderRespType` is set NOWHERE in this tree, so
            # the response type is the venue's default and the shape is
            # DOCUMENTED rather than measured here -- the only MARKET payload
            # this repository holds is a hand-written fixture. So the total is
            # not assumed: the sell is re-read by the id it was sent under.
            total = await self._requery_sell_total(position, bounds)

        # **THE POST-REQUERY `total` IS WHAT THE PREDICATE IS FED**, never
        # `order.filled_quote_quantity`. The requery above is I/O and runs
        # first; handing the predicate the raw field would ask it about a
        # total this method has already improved on.
        verdict = classify_bookability(
            position=position,
            filled_quantity=order.filled_quantity,
            filled_quote_quantity=total,
        )

        if total is None or verdict.outcome is BookabilityOutcome.PARTIAL_FILL:
            # RULING 5: A PARTIAL FILL FAILS CLOSED, and it must, because it
            # CANNOT BE REPRESENTED. `close_position` deletes the whole entry
            # and credits one total; there is no partial-close path and no way
            # to express "0.3 of 0.5 sold". Booking it would delete a position
            # that still exists at the venue and credit proceeds for base still
            # held -- a corrupted ledger, in the direction that cannot be
            # noticed. An unpriceable full fill takes the same branch for the
            # same reason: there is nothing safe to book.
            #
            # **`total is None` IS A TYPE NARROWING, NOT A SECOND BOOKABILITY
            # DECISION** -- the same category as `order is None` at
            # `_bookable_total`, and kept for the same reason. It COINCIDES
            # exactly with `NO_QUOTE_TOTAL`, because `Q` precedes `P` in
            # `A > Q > P > C`, so this disjunction is the shipped guard
            # unchanged. mypy cannot narrow a local through a verdict object,
            # and `_sold_unbooked` and `_book_close` both take `Money`.
            #
            # **`PARTIAL_FILL` AND `NO_QUOTE_TOTAL` SHARE ONE REASON CODE, AND
            # THAT IS A DEFERRAL RATHER THAN AN ACCIDENT.** The predicate
            # separates the two facts for the first time; this site still
            # collapses them onto `close_partial_fill`, which on a COMPLETE
            # fill the venue never priced says "partial" and is wrong. Ruled
            # deferred to `M5i-020`. Observable behaviour here is invariant
            # across (ii)b, which is the mandate.
            #
            # `POSITION_ABSENT` cannot arrive: `position` is a non-optional
            # parameter. It reaches neither branch rather than being given one
            # nothing can enter, which is the lazy-default shape `CLAUDE.md`
            # locks against for enums.
            #
            # **THE RESIDUAL, NAMED: `Position.quantity` IS NOW OVERSTATED.**
            # It says what was held before the partial sell, and nothing in this
            # design corrects it -- correcting it would need the partial-close
            # path that does not exist. The operator path in `_go_naked` is what
            # resolves it.
            self._go_naked(signal, position, candle, _REASON_CLOSE_PARTIAL_FILL)
            return

        if verdict.outcome is BookabilityOutcome.NO_COST_BASIS:
            # B-i. COMPLETE, PRICED and UNPRICEABLE are three separate facts and
            # only the third arrives here. **THE LADDER PUTS `NO_COST_BASIS`
            # LAST** -- `M5i-043` -- so a partial fill with no cost basis
            # answers `PARTIAL_FILL` and left above, where `_go_naked`'s "still
            # open" and "sell the base by hand" are TRUE because base remains at
            # the venue. Reaching here means the sell was COMPLETE, so telling
            # the operator to sell again would instruct a SECOND sale of an
            # asset already gone -- `M5i-035` measured exactly that when the two
            # were collapsed.
            self._sold_unbooked(signal, position, candle, total=total, order=order)
            self._release_close(signal.symbol)
            return

        self._book_close(signal, position, candle, total=total, order=order)
        self._release_close(signal.symbol)

    async def _requery_sell_total(self, position: Position, bounds: CallBounds) -> Money | None:
        """The sell's quote total, read back by the id we sent. ``None`` if not.

        Its own method so the fallback is one call with one failure mode, and so
        a reader can see that the total is never invented -- it is either the
        venue's or absent.
        """
        try:
            sold = await self._client.get_order(
                position.symbol,
                client_order_id=close_client_order_id(
                    position.symbol, position.entry_bar_time, generation=_CLOSE_GENERATION
                ),
                timeout_s=bounds.timeout_s,
                attempts=bounds.attempts,
            )
        except Exception as exc:  # never raises; the caller fails closed
            self._log_failure("close-sell-requery", position.symbol, exc)
            return None
        return sold.filled_quote_quantity

    def _book_close(
        self,
        signal: Signal,
        position: Position,
        candle: Candle,
        *,
        total: Money,
        order: Order,
    ) -> bool:
        """Credit, accrue and delete -- the bot's own exit reaching the ledger.

        **IT RETURNS WHETHER IT WROTE. Option 3, half (i).** ``True`` only past
        the write; ``False`` from the ``except``. The verdict is what lets a
        CALLER report the booking as a CONSEQUENCE rather than predict it, which
        is `M5h-371`'s fix -- and this method never had that defect, because its
        own success line already sits past the write (`M5i-010`).

        **SO THIS RETURN IS FOR SYMMETRY AND FOR (ii), NOT FOR A CALLER TODAY.**
        `_sell_and_book` emits no resolution label and ignores it, so nothing
        here changes behaviour. It is typed now rather than later because the
        two booking methods are one contract and a verdict on only one of them
        is the drift this file keeps finding.

        **A `bool` RATHER THAN A VALUE OBJECT, deliberately.** `CLAUDE.md`
        requires a frozen object carrying its reason where a refusal has
        REASONS to carry -- `SizingDecision` is the worked case. This has one:
        the write landed, or it raised and the exception is already logged at
        this site with its type and message. A second carrier would duplicate
        what the CRITICAL beside it holds.

        **THE SECOND BOOKING PATH, AND DELETION IS WHAT KEEPS THEM APART.**
        `_book_exits` books venue-triggered fills from a `ProtectionAssessment`;
        this books a sell the bot itself sent, which that path can never see --
        cancelled legs classify `DIVERGED` and carry no `ExitFill`. Both end in
        `close_position`, which deletes the symbol, and
        `reconcile_open_positions` builds its work list from `open_positions` --
        so whichever books first makes the other structurally blind.

        **THIS IS THE BOOKING DELETION. THE OTHER ONE DOES NOT BOOK.**
        `_drop_position_unbooked` also removes from `portfolio.positions`, and
        credits nothing: it is the C5c resolution letting go of a record whose
        cost basis no longer exists. Named at both sites rather than at one,
        because a second way to remove from a collection is the second-source-
        of-truth shape `CLAUDE.md` warns about, and a reader who opens only one
        of them would not know the other was there.

        **THAT OTHER ONE NOW HAS TWO CALLERS, AND THE SECOND IS ON THIS PATH.**
        `_sold_unbooked` sits between this method and `_go_naked` in
        `_sell_and_book`'s tail: a complete, priced sell whose position carries
        no `entry_fill_price` is dropped there instead of reaching here. So the
        deletion inventory is unchanged at TWO paths and the caller count is
        three -- `_book_close`, `_book_resolved_close` and `_sold_unbooked`.
        """
        try:
            realised = self._portfolio.close_position(
                position.symbol, exit_quote_total=total, now=utc_now()
            )
        except Exception as exc:
            # The credit may have landed and the accrual raised -- the C12
            # residual, and this is a second caller of it. The position survives,
            # so the failure is visible and repeating rather than silent.
            _log.critical(
                "Booking the close of %s failed after the sell landed",
                signal.symbol,
                extra={
                    "event": _EVENT_CLOSE_BOOK_FAILED,
                    "symbol": signal.symbol,
                    "quote_total": total,
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                },
            )
            return False

        _log.info(
            "Closed %s",
            signal.symbol,
            extra={
                "event": _EVENT_CLOSE_BOOKED,
                "symbol": signal.symbol,
                "order_id": order.order_id,
                "quantity": order.filled_quantity,
                "quote_total": total,
                "realised": realised,
                "candle_time": candle.close_time.isoformat(),
            },
        )
        return True

    def _sold_unbooked(
        self,
        signal: Signal,
        position: Position,
        candle: Candle,
        *,
        total: Money,
        order: Order,
    ) -> None:
        """The sell COMPLETED and cannot be priced. Drop it, say so. **B-i.**

        **RULING 1 REQUIRES THE IDENTICAL OPERATIONAL SURFACE TO PATH A**, and
        this reads `_RESOLVED_RELEASED` rather than restating it -- the same
        value `_log_close_resolved` renders for a record resolved a bar later.
        Sharing the constant is what makes "identical" a property instead of a
        promise: there is one string, so the two cannot drift, and the
        `M5i-042` balance-sheet sentence reached both paths in one edit.

        **IT DOES NOT CALL `_log_close_resolved`, DELIBERATELY.** That method is
        `M5h-371`'s and option 3's territory, and giving it a second caller
        would widen a scope option 3 has not been written against. Reading a
        constant is not routing through the method; only `message` is this
        method's own, and it must be, because path A's headline says *"a pending
        close record was resolved"* and nothing was restored here.

        **IT DOES NOT CALL `_refuse`.** The close SUCCEEDED -- the position is
        flat at the venue and the signal got what it asked for. `_go_naked`
        refuses because the position is still open; emitting `dispatch_refused`
        here would log a refusal against a `CLOSE` that did exactly its job.

        **AND IT DELETES THROUGH `_drop_position_unbooked`, NEVER A DIRECT
        `pop`.** `_book_close` above asserts the tree has exactly two ways a
        position leaves `positions`; a third would be the second-source-of-truth
        shape `CLAUDE.md` warns about, and this is that method's second call
        site rather than a new path.

        **THE THIRD COPY OF THE COST-BASIS CRITERION IS UPSTREAM OF HERE, AND
        IT IS A DEBT.** Ruling 2 authorises it only because option 3 is mandated
        to deliver one shared bookability predicate consumed by
        `_bookable_total`, by `_sell_and_book` and by `reconciliation_driver`'s
        row ladder. `test_bookability_criterion_census.py` holds the count at
        three so the debt cannot quietly become four.
        """
        _log.critical(
            "%s: the close sell FILLED and was DROPPED UNBOOKED -- this bot has no cost "
            "basis for the position, so the venue's figures below are the only record",
            signal.symbol,
            extra={
                "event": _EVENT_CLOSE_SOLD_UNBOOKED,
                "symbol": signal.symbol,
                "quantity": position.quantity,
                "entry_bar_time": position.entry_bar_time.isoformat(),
                "generation": _CLOSE_GENERATION,
                "close_client_order_id": close_client_order_id(
                    position.symbol, position.entry_bar_time, generation=_CLOSE_GENERATION
                ),
                "candle_time": candle.close_time.isoformat(),
                # THE TWO FIELDS RULING 1 BINDS. Read, never restated.
                "outcome": _RESOLVED_RELEASED.outcome,
                "resolution": _RESOLVED_RELEASED.resolution,
                "status": order.status.value,
                "executed_qty": order.filled_quantity,
                "quote_total": total,
                # THE ONE FIELD PATH A CANNOT SUPPLY. `_log_close_resolved`
                # emits no `order_id` even when it holds an `Order`; here the
                # sell is ours and its venue id is the handle an operator
                # reconciles by.
                "order_id": order.order_id,
            },
        )
        self._drop_position_unbooked(signal.symbol)

    def _go_naked(self, signal: Signal, position: Position, candle: Candle, reason: str) -> None:
        """Protection is cancelled and the position is not closed. RULING 6.

        **EVERYTHING BELOW IS SCOPED TO A SELL THAT PROVABLY DID NOT HAPPEN,
        AND ONE BRANCH NO LONGER COMES HERE.** A sell that was SENT and whose
        outcome is unknown goes to `_go_naked_retaining` instead. The argument
        in this docstring -- self-refreshing, operator-only, sell the base by
        hand -- is FALSE there: a pending record survives, so `_resolve_close`
        asks the venue on the next candle, and the base may already be sold.
        The split exists because one method cannot carry both arguments, and
        the wrong one of the two is the one that loses money.

        The sell's `except` routes on `ClientRefusalError`: marked comes here,
        unmarked goes to the sibling. Every OTHER caller of this method -- the
        exhausted budget, the abandoned plan, the partial fill -- is unchanged
        and correctly described below.

        **THE OTHER WRITER OF `protection` IN THIS CLASS IS
        `_retain_position_unprotected`**, which reaches the same state from the
        RESOLUTION path. Neither can call the other: this one takes a `Signal`
        and ends in `_refuse(signal, ...)`, and a resolution is candle-driven
        and has none. Named at both sites so a reader of either knows the other
        exists -- everything below about what the state costs applies equally to
        it.

        **NO SPECULATIVE RETRY.** A second sell could double-sell if the first
        landed and its answer was lost, and nothing here can tell those apart.

        **THE STATE IS SELF-REFRESHING AND DOES NOT RESOLVE IN-PROCESS**, which
        is stated here because "the reconciler will handle it" is the natural
        assumption and it is FALSE. TRACED: the legs are cancelled, so
        `classify_protection` finds them missing and the resolver point-queries
        them; `CANCELED` is terminal and not open, so `_refine` answers
        `DIVERGED` with NO `ExitFill`. Both legs resolve, so nothing is carried,
        so `record_reconciliation` STAMPS the position -- meaning
        `last_reconciled_at` refreshes every pass and `POSITION_STALE` never
        fires either. `_book_exits` books nothing. `DIVERGED` is outside
        `_TRUSTED_PROTECTION`, so committed risk is uncomputable and entries are
        refused PORTFOLIO-WIDE, indefinitely.

        So the exit is an operator: sell the base by hand, then RESTART -- the
        store holds no `Position`, so a fresh boot reseeds from balances and the
        naked position ceases to exist. **That trade's realised P&L is lost**,
        because the sale happens outside the bot and nothing books it.

        `protection = UNKNOWN` rather than `DIVERGED`: the classifier owns
        `DIVERGED` and will write it on the next pass anyway, and `UNKNOWN` is
        what this path actually knows -- whether the position is still held is
        precisely the open question.
        """
        position.protection = ProtectionState.UNKNOWN
        _log.critical(
            "%s is UNPROTECTED and still open; entries are blocked until an operator clears it",
            signal.symbol,
            extra={
                "event": _EVENT_CLOSE_NAKED,
                "symbol": signal.symbol,
                "reason": reason,
                "quantity": position.quantity,
                "venue_order_list_id": position.venue_order_list_id,
                "resolution": (
                    "SELF-REFRESHING: cancelled legs classify DIVERGED every pass, the position "
                    "is re-stamped so POSITION_STALE never fires, and nothing books it. Cleared "
                    "only by selling the base manually and restarting."
                ),
                "candle_time": candle.close_time.isoformat(),
            },
        )
        self._release_close(signal.symbol)
        self._refuse(signal, reason, candle)

    def _go_naked_retaining(self, signal: Signal, position: Position, candle: Candle) -> None:
        """The sell was SENT and its outcome is unknown. **Rulings 1-3.**

        `_go_naked`'s sibling, and the ONE difference in behaviour is that this
        does not call `_release_close`: the `PendingClose` written before the
        cancel stays in memory and on disk, so `__call__`'s resolution loop --
        which iterates every record regardless of origin -- hands it to
        `_resolve_close` on the next candle, where a `get_order` against the
        derived `close_client_order_id` asks the venue what actually happened.

        **A SIBLING RATHER THAN A FLAG ON `_go_naked`, and the reason is its
        DOCSTRING rather than its code.** The two bodies differ by one line;
        the arguments they carry are incompatible. `_go_naked` argues at length
        that the state is self-refreshing, resolves for nobody, and is cleared
        only by an operator selling the base by hand. Every clause of that is
        false here. A flag would leave one method asserting both.

        **WHY IT STILL MARKS `UNKNOWN`. Ruling 3.** The order list was cancelled
        BEFORE the sell was dispatched, so the asset is physically unprotected
        whatever the sell did -- that fact is independent of the sell's outcome
        and is not in question. Marking is also what refuses entries
        portfolio-wide for the one bar until resolution runs, via
        `_TRUSTED_PROTECTION`, and it costs nothing on either resolution branch:
        a confirmed fill drops the position, and an unconfirmed one has
        `_retain_position_unprotected` write the same value again.

        **THE LOG MUST NOT SAY WHAT `_go_naked`'s SAYS, and that is ruling 1's
        whole point rather than a wording preference.** `close_position_naked`
        instructs an operator to sell the base manually. On this branch the sell
        may ALREADY have filled -- the socket expired, or a 2xx would not parse
        -- so following that instruction sells twice. The three claims it must
        not make are each MEASURED false here: the state is not self-refreshing
        (a pending record resolves it), it is not operator-only (the next candle
        acts), and the position is not known to be open (the sell may have
        completed). Its own event name keeps an operator filtering for one from
        finding the other.

        **NO RETRY, unchanged.** Nothing re-sends the sell. The record is a
        handle for ASKING, never for resending -- `_resolve_close` queries and
        logs, and Commit B2 rules what it may do with a confirmed fill.

        **SINGLE-SHOT, and that is what stops retention wedging a symbol.**
        `_resolve_close` releases the record in a `finally` on every branch
        including a failed query, so this holds the symbol for exactly one bar.
        """
        position.protection = ProtectionState.UNKNOWN
        _log.critical(
            "%s close sell is UNCONFIRMED -- the order was sent and the outcome is unknown",
            signal.symbol,
            extra={
                "event": _EVENT_CLOSE_SELL_UNCONFIRMED,
                "symbol": signal.symbol,
                "reason": _REASON_CLOSE_SELL_UNCONFIRMED,
                "quantity": position.quantity,
                "venue_order_list_id": position.venue_order_list_id,
                "close_client_order_id": close_client_order_id(
                    position.symbol, position.entry_bar_time, generation=_CLOSE_GENERATION
                ),
                "resolution": (
                    "DO NOT INTERVENE and DO NOT SELL THIS BASE BY HAND. The sell was sent "
                    "and may have filled. The pending record is RETAINED, and verification "
                    "runs on the next candle: the venue is asked for this close order id and "
                    "the outcome is logged as close_record_resolved. Protection is gone "
                    "either way, so entries are blocked meanwhile. Wait for that line."
                ),
                "candle_time": candle.close_time.isoformat(),
            },
        )
        self._refuse(signal, _REASON_CLOSE_SELL_UNCONFIRMED, candle)

    def _release_close(self, symbol: str) -> None:
        """Drop the pending close now its outcome is known, durably if we can.

        Mirrors `_persist_after_removal`: the in-memory record goes first
        because it gates the next bar's dispatch, and the durable rewrite is
        best-effort because a stale record on disk is self-correcting where a
        stuck in-memory one is not.
        """
        self._pending.pop(symbol, None)
        self._persist_after_removal(symbol)

    async def _resolve_close(
        self, record: PendingClose, candle: Candle, *, bounds: CallBounds
    ) -> None:
        """Ask the venue what became of a restored close, report it, let it go.

        **THE ACTION IS INVARIANT AND THE QUERY DECIDES NOTHING.** Whatever the
        venue says -- FILLED, absent, or nothing at all because the call raised
        -- this clears the lock from memory and from disk, drops any local
        position UNBOOKED, and emits one CRITICAL carrying what was learned.
        The query enriches the log for an operator doing the accounting by hand;
        it does not select a branch. That is the ruling, and it is what makes
        the escalation safe: there is no answer this code can get wrong.

        **NOTHING IS SOLD AND NOTHING IS BOOKED.** No `create_order`, no
        `close_position`, no `record_realised_pnl`. A position still open at the
        venue is left to the BOOT SNAPSHOTS -- a live order list blocks the
        symbol, and free base above `min_notional` records an unmanaged holding
        -- rather than to a runtime write of `blocked_symbols`, which that
        field's own docstring forbids for the process lifetime.

        **FAIL-SAFE BY CONSTRUCTION, NOT BY CARE.** The clear sits in a
        ``finally``. No exception path, no early return, and no later edit
        inside the body can skip it, which is a different guarantee from three
        call sites each remembering to call it. `_read_close_outcome` already
        swallows its own failure; the ``finally`` is what makes that belt and
        braces rather than a single point.

        **TWO POSITION CASES, AND NEITHER IS AN ERROR.** After a restart there
        is no `Position` at all -- it is in-process only and boot reconstructs
        none -- so the drop finds nothing and that is the ORDINARY case. Within
        one process the position is present. "No position found" is not a
        failure and must never be logged as one.

        **THE ACTION IS NO LONGER INVARIANT ON THE CONFIRMED-FILL BRANCH, AND
        THAT IS A DELIBERATE REVERSAL. Ruling 5.** This docstring used to say
        the query decides nothing, and for R1 (no sell) and the retain branch it
        still decides nothing. A confirmed fill against a position still in
        memory now BOOKS: `_book_resolved_close` credits the proceeds and
        accrues the realised P&L through `Portfolio.close_position`.

        **AND THE CRITICAL IS NOW EMITTED LAST, FROM THE ``finally``, WHICH IS
        OPTION 3 HALF (i).** It used to sit in the ``try``, computing its label
        from ``total is not None`` -- the INTENTION to book -- and running before
        any of the branches below. `M5h-371`: a booking that then failed left a
        line already claiming `filled_and_booked`, with a separate
        `close_book_failed` CRITICAL contradicting it two records later. Each
        branch now selects its own :class:`_CloseResolutionText` beside its own
        action, and the booking branch selects between TWO on the verdict
        `_book_resolved_close` returns. **The label can no longer describe an
        intention the write did not carry out.**

        **THE LOG IS THE ``finally``'s LAST STATEMENT, AFTER `_release_close`,
        AND THAT ORDERING IS DELIBERATE** -- `M5i-056`. While the log sat in the
        ``try``, a raise inside it still reached this ``finally`` and the record
        was still cleared. Moving it here removes that protection, so it goes
        after the clear instead: there is nothing left to strand. ``order`` and
        ``failure`` are pre-bound with ``filled`` and ``total`` for the same
        reason -- the ``finally`` reads all four now.

        **R2 IS NOT CONTRADICTED, because R2 rested on a constraint that does
        not hold here.** Its grounds were that after a restart there is no
        `Position` and `PendingCloseRecord` carries no `entry_price`, so the
        figure was UNRECONSTRUCTABLE -- an engineering limit, never a policy of
        forfeiting valid accounting. In-process both are present, so the figure
        is computable and the venue's own quote total is the input. The restart
        case is unchanged and still drops unbooked.
        """
        symbol = record.symbol
        # THE CONSERVATIVE DEFAULT, and it is load-bearing rather than tidy.
        # The `finally` below reads this, so it must be bound before anything
        # that could fail to bind it -- and the value it defaults to is RETAIN,
        # which refuses entries. An unbound-local or a crash therefore lands on
        # the safe branch rather than on the one that lets the bot re-enter.
        filled = False
        # Bound with `filled`, and for the same reason: the `finally` reads it,
        # so it must exist before anything that could fail to bind it. `None`
        # is the conservative value -- it books nothing.
        total: Money | None = None
        # **BOUND HERE FROM OPTION 3, AND FOR THE SAME REASON AS THE TWO ABOVE**
        # -- `M5i-056`. These were bound INSIDE the `try` while the log was
        # there too. The log is now the `finally`'s last statement, so the
        # `finally` reads them, and an unbound local there would raise over the
        # real error instead of reporting it. `_read_close_outcome` is written
        # never to raise; this does not depend on that remaining true.
        order: Order | None = None
        failure: Exception | None = None
        try:
            order, failure = await self._read_close_outcome(record, bounds=bounds)
            # A FILL IS `executedQty`, NOT THE MERE PRESENCE OF AN ANSWER.
            # `_plan_close` already holds this line -- "Section 4b reads
            # `executedQty`, not merely `status`" -- and the same reasoning
            # binds here: a CANCELED or EXPIRED order comes back as an `Order`
            # and sold nothing, so treating any answer as a fill would drop a
            # position whose base is still at the venue.
            filled = order is not None and order.filled_quantity > 0
            if filled:
                total = self._bookable_total(symbol, order)
        finally:
            # **THE QUERY NOW DECIDES THE DROP AND, ON ONE BRANCH, A LEDGER
            # WRITE.** Two commits ago it decided nothing at all. The CLEAR and
            # the CRITICAL are still unconditional on every answer including a
            # failed one; what reads the venue is the choice between booking,
            # dropping and retaining.
            #
            # **EACH BRANCH NOW NAMES ITS OWN TEXT, BESIDE ITS OWN ACTION.**
            # That is `M5h-371`'s fix and the whole of Option 3 half (i): the
            # label is SELECTED HERE, where the write happens, so it cannot
            # describe an intention the write did not carry out. It used to be
            # computed in the `try` from `total is not None` -- the intention to
            # book -- and emitted before any of this ran.
            if total is not None:
                # Confirmed flat, in process, priced by the venue: the capital
                # is back and the trade belongs in the ledger. **THE ONLY BRANCH
                # WITH TWO OUTCOMES**, because it is the only one that writes.
                texts = (
                    _RESOLVED_BOOKED
                    if self._book_resolved_close(symbol, candle, total=total)
                    else _RESOLVED_BOOK_FAILED
                )
            elif filled:
                # Confirmed flat but not bookable -- no position to price it
                # against, a partial, or no quote total reported.
                self._drop_position_unbooked(symbol)
                texts = _RESOLVED_RELEASED
            else:
                self._retain_position_unprotected(symbol)
                texts = _RESOLVED_RETAINED
            self._release_close(symbol)
            # **LAST, AND AFTER THE RELEASE** -- `M5i-056`. Moving the log into
            # this `finally` removed the protection the `try` used to give it: a
            # raise in the logger no longer lands on a `finally` that clears the
            # record. Putting it after `_release_close` restores that -- there
            # is nothing left to strand.
            self._log_close_resolved(record, candle, order=order, failure=failure, texts=texts)

    def _retain_position_unprotected(self, symbol: str) -> None:
        """Keep the position and mark its protection UNKNOWN. **P2/P4.**

        **WHY IT IS KEPT.** The sell is unconfirmed, so base inventory may still
        be sitting at the venue. Dropping it removed the only in-process record
        of that -- `has_position` went false, `unmanaged_holdings` is a BOOT
        snapshot and knows nothing of inventory that appeared mid-run, and
        nothing else refuses -- so the next signal could open a SECOND entry on
        top of the first. MEASURED before this commit: after a P2/P4 resolution
        `RiskManager.evaluate` returned `approved=True` and an OTOCO list was
        actually placed.

        **WHAT KEEPING IT RESTORES, and the second one is the point.**
        `ALREADY_IN_POSITION` refuses a fresh entry on this symbol, and marking
        protection UNKNOWN puts it outside `_TRUSTED_PROTECTION`, so
        `committed_risk` cannot be summed and `COMMITTED_RISK_UNKNOWN` refuses
        entries PORTFOLIO-WIDE. That breadth is deliberate: an unconfirmed sell
        means the account's true exposure is unknown, and a limit computed from
        a number nobody can compute is worse than a refusal.

        **EXITS STAY PERMITTED.** No limit gates a `CLOSE` -- `CLAUDE.md`: a
        limit that could trap an open position would be a risk rule that
        creates risk -- so the operator, or the strategy, can still close this.

        **THE SECOND `protection` ASSIGNMENT IN THIS CLASS, and it cannot reuse
        the first.** `_go_naked` writes the same value for the in-process naked
        case, but it takes a `Signal` and ends in `_refuse(signal, ...)`; a
        resolution is candle-driven and HAS no signal, so calling it would mean
        fabricating one and logging a refusal against a signal nobody sent.
        Both produce the same state and neither can call the other; each names
        the other so a reader of one knows the other exists.

        **UNKNOWN RATHER THAN DIVERGED**, matching `_go_naked` for its stated
        reason: the classifier owns `DIVERGED` and will write it on the next
        pass anyway. Both are outside `_TRUSTED_PROTECTION`, so the refusal is
        the same either way.

        Absent is ORDINARY here, not an error: after a restart there is no
        `Position` to retain, and the boot snapshots cover that case instead.
        """
        position = self._portfolio.positions.get(symbol)
        if position is not None:
            position.protection = ProtectionState.UNKNOWN

    async def _read_close_outcome(
        self, record: PendingClose, *, bounds: CallBounds
    ) -> tuple[Order | None, Exception | None]:
        """The venue's word on the close sell, or the reason there is none.

        The same call `_requery_sell_total` makes, by the same derived id: the
        close ID is pure computation over ``(symbol, entry_bar_time,
        generation)``, which is precisely what lets it run after the process
        that sent the order is gone.

        Returns a pair rather than raising, because BOTH halves reach the log
        and neither changes what happens. Never raises.
        """
        try:
            order = await self._client.get_order(
                record.symbol,
                client_order_id=close_client_order_id(
                    record.symbol, record.entry_bar_time, generation=record.generation
                ),
                timeout_s=bounds.timeout_s,
                attempts=bounds.attempts,
            )
        except Exception as exc:  # never raises; the caller acts regardless
            return None, exc
        return order, None

    def _bookable_total(self, symbol: str, order: Order | None) -> Money | None:
        """The venue's quote total, or ``None`` when this fill must not be booked.

        **THE FOUR CONDITIONS NOW LIVE IN `classify_bookability`**, which is
        the single shared predicate option 3 half (ii) delivered. This method
        asks it and returns the total it blesses; it decides nothing itself.
        Read `execution/bookability.py` for the facts, their canonical order
        `A > Q > P > C`, and why only two of that order's six relations are a
        choice. What remains here is the history, because it is this method's.

        **THE POSITION MUST BE IN MEMORY**, because it carries the cost basis.
        `close_position` prices realised P&L off `entry_fill_price`, and after a
        restart there is no `Position` and `PendingCloseRecord` carries none --
        so the figure is unreconstructable rather than merely unknown. That is
        the restart case and it still drops unbooked.

        **AND THE POSITION MUST CARRY THAT COST BASIS**, which is a SEPARATE
        condition from being in memory and was missing until M5i. A `Position`
        is constructed with `entry_fill_price=None` whenever the working-leg
        query failed or the FOK expired -- `_open_position` says so and calls
        such a position UNBOOKABLE -- so "in memory" and "priceable" are two
        facts, and this method checked only the first.

        **WHAT THAT COST, MEASURED at M5i phase 1b.** The fill was judged
        bookable, `booked=True` reached the log, and the CRITICAL read
        `filled_and_booked` with *"DO NOT enter this trade by hand -- the
        ledger already carries it"*. `close_position` then raised `ValueError`
        from `_realised_from_total` BEFORE crediting anything;
        `_book_resolved_close` caught it and emitted `close_book_failed`. So
        the ledger was short a real trade and the operator had been told not to
        fix it -- a permanent under-report, the one direction a control may not
        err in. `M5i-001`.

        **IT IS DECIDED BEFORE THE CALL RATHER THAN CAUGHT FROM THE RAISE.**
        Until (ii)b that was a property each of the three sites held
        separately; it is now a property of the one predicate they share. A
        refusal decided before the call yields the right label; an exception
        caught after it yields a label already emitted and wrong.

        **THE FILL MUST BE WHOLE.** `close_position` deletes the entire entry
        and credits one total; there is no partial-close path and no way to say
        "0.3 of 0.5 sold". Booking a partial would delete a position whose base
        is still at the venue and credit proceeds for it -- a corrupted ledger
        in the direction nobody notices. Ruling 5 in `_sell_and_book` fails
        closed on exactly this and so does this path.

        **THE VENUE MUST HAVE REPORTED THE TOTAL.** `filled_quote_quantity` is
        `cummulativeQuoteQty` carried verbatim, and `None` there means the venue
        did not report it -- kept distinct from a genuine zero by that field's
        own design. There is no fallback: deriving a total by multiplying
        `average_price` reintroduces the quotient error the exchange's own
        accounting does not have, and `CLAUDE.md` records a stop booked at its
        trigger under-reporting 137.36 of 241.15 USDT across three exits.
        **The booked figure is the venue's or there is no booked figure.**
        """
        if order is None:
            # NOT one of the four facts -- a TYPE NARROWING, and `M5i-052` is
            # why the predicate has no `order` parameter to carry it. It is
            # runtime-unreachable: the only call site is guarded by
            # `filled = order is not None and order.filled_quantity > 0`, and
            # mypy will not narrow through that intermediate bool.
            return None
        return classify_bookability(
            position=self._portfolio.positions.get(symbol),
            filled_quantity=order.filled_quantity,
            filled_quote_quantity=order.filled_quote_quantity,
        ).total

    def _book_resolved_close(self, symbol: str, candle: Candle, *, total: Money) -> bool:
        """Book a resolved close. **Ruling 5, and the R2 reversal lives here.**

        **IT RETURNS WHETHER IT WROTE, AND THAT IS WHAT CLOSES `M5h-371`.**
        ``True`` only past `close_position`; ``False`` from the ``except``.
        `_resolve_close` reads it to SELECT the resolution text, so the label is
        now a consequence of the write rather than a prediction made before it.
        Two paragraphs down this docstring used to end *"the log line has already
        been emitted by then, claiming the trade was booked"* -- that is the
        defect, and it is gone: the log is now emitted AFTER this returns.

        **THIS IS THE ONE PLACE THE RESOLUTION PATH MOVES A FIGURE**, and it does
        not contradict R2 -- it retires the constraint R2 rested on. R2 said the
        resolution books nothing *because the figure was unreconstructable*:
        after a restart there is no `Position` and the record carries no
        `entry_price`. That is an engineering limit, not a policy of forfeiting
        valid accounting, and it simply does not hold when the position is in
        memory. Where it still holds -- the restart case -- nothing changed.

        **NO THIRD DELETION PATH.** This deletes through
        `Portfolio.close_position`, which is the SAME path `_book_close` uses
        for the live close, so the tree still has exactly two ways a position
        leaves `positions`:

        * `close_position` -- credits, accrues, deletes. `_book_close` for the
          bot's own completed sell, and this for one confirmed a bar later.
        * `_drop_position_unbooked` -- deletes and credits NOTHING, for a fill
          that cannot be priced.

        **IT CANNOT REUSE `_book_close`**, for the reason `_retain_position_-
        unprotected` cannot reuse `_go_naked`: that one takes a `Signal` and
        logs against it, and a resolution is candle-driven and has none.
        Fabricating a signal to reach it would log a decision nobody made.

        **THE C12 RESIDUAL IS INHERITED, not introduced.** `close_position`
        credits `free_quote` before accruing, so an accrual that raises leaves
        the proceeds credited and the position present -- visible and repeating
        rather than silent. `_book_close` carries the same residual and says so;
        this is its second caller.

        **THAT SENTENCE USED TO END DIFFERENTLY, and the change is the commit.**
        It read *"Note the log line has already been emitted by then, claiming
        the trade was booked, so a failure here is reported by this CRITICAL
        rather than by that one."* True when written and false now: the
        resolution line is emitted after this method returns and reads
        `_RESOLVED_BOOK_FAILED` on this branch. Corrected in place because it is
        a claim about the tree. The CRITICAL here still fires -- it carries the
        exception, which the resolution line does not -- so the failure is
        reported TWICE and agrees with itself, where before it was reported
        twice and contradicted itself.
        """
        try:
            realised = self._portfolio.close_position(symbol, exit_quote_total=total, now=utc_now())
        except Exception as exc:
            _log.critical(
                "Booking the resolved close for %s FAILED; the position survives and the "
                "ledger may be short this trade",
                symbol,
                extra={
                    "event": _EVENT_CLOSE_BOOK_FAILED,
                    "symbol": symbol,
                    "quote_total": total,
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                    "candle_time": candle.close_time.isoformat(),
                },
            )
            return False
        _log.critical(
            "Booked the resolved close for %s",
            symbol,
            extra={
                "event": _EVENT_CLOSE_BOOKED,
                "symbol": symbol,
                "quote_total": total,
                "realised": realised,
                "candle_time": candle.close_time.isoformat(),
            },
        )
        return True

    def _drop_position_unbooked(self, symbol: str) -> None:
        """Forget a position WITHOUT booking it. **The second deletion path.**

        **`close_position` BOOKS AND THIS ONE DOES NOT**, and that is the whole
        distinction between the two sites that delete from
        `portfolio.positions`:

        * `Portfolio.close_position` -- credits the proceeds, accrues realised
          P&L, then deletes. Reached from `_book_close` for the bot's own
          completed sell and from `_book_resolved_close` for one confirmed a bar
          later. Two callers, ONE deletion path.
        * here -- deletes and credits NOTHING. TWO callers from M5i commit 3b:
          `_resolve_close`'s `finally`, and `_sold_unbooked` on the live close
          path. Still ONE deletion path; only the caller count moved.

        A second way to remove from a collection is the "second source of truth"
        shape `CLAUDE.md` warns about, so it is named at both sites rather than
        left for a reader to infer from which one they happened to open.

        **THIS IS NOW THE UNPRICEABLE-FILL PATH, AND THE JUSTIFICATION BELOW IS
        REWRITTEN RATHER THAN LEFT STANDING.** It used to read *"IT CANNOT BOOK,
        AND THAT IS STRUCTURAL RATHER THAN CHOSEN"*, on the grounds that after a
        restart there is no position and `PendingCloseRecord` carries no
        `entry_price`. That argument is sound for the restart case and was
        MEASURED false for the in-process one, where the `Position` and its
        `entry_fill_price` are both present -- `M5h-364`. Keeping the old prose
        beside ruling 5's behaviour would ship the stale-justification defect
        this project keeps finding, so it is corrected in place: it is a claim
        about the tree, and annotate-never-delete governs findings.

        **WHAT REACHES HERE NOW, all five unbookable and for different
        reasons.** The first four are `_bookable_total`'s four conditions on the
        RESOLUTION path; the fifth is B-i on the LIVE close path. A claim about
        the tree, so it is corrected in place rather than annotated -- the list
        read "all three" until M5i commit 3a added the fourth and 3b the fifth.

        * no `Position` in memory -- the RESTART case, where the cost basis is
          unreconstructable and the old argument holds exactly as written;
        * a PARTIAL fill -- `close_position` deletes the whole entry and credits
          one total, so booking it would credit proceeds for base still held;
        * the venue reported no `cummulativeQuoteQty` -- and a total is never
          derived, because a quotient reintroduces the error the exchange's own
          accounting does not have;
        * the position is present and carries NO `entry_fill_price`, so it is in
          memory and still unpriceable -- two facts, `M5i-001`;
        * and from `_sold_unbooked`, that same absent cost basis on a sell this
          process just sent and watched complete.

        In all five the proceeds are in the CRITICAL line instead, for an
        operator to enter by hand.

        **NO LONGER UNCONDITIONAL.** It ran on every answer until M5h-321a;
        it then ran on every CONFIRMED FILL, and from ruling 5 it runs on the
        confirmed fills that cannot be priced. The unconfirmed answers go to
        `_retain_position_unprotected` instead, because dropping a position
        whose base may still be at the venue is what let a second entry through.
        That paragraph describes the RESOLUTION caller and is unchanged by B-i.

        **ABSENT IS ORDINARY FROM ONE CALLER AND IMPOSSIBLE FROM THE OTHER**, so
        the tolerance is kept and its scope is now stated. After a restart there
        is no `Position` to drop and `_resolve_close` reaches here anyway -- see
        that method. `_sold_unbooked` holds the `Position` it just sold, so a
        miss there would mean something removed it mid-sequence; the `pop` still
        tolerates it, because a deletion helper that raises inside a dispatch
        path buys nothing the enclosing handler would not swallow.
        """
        self._portfolio.positions.pop(symbol, None)

    def _log_close_resolved(
        self,
        record: PendingClose,
        candle: Candle,
        *,
        order: Order | None,
        failure: Exception | None,
        texts: _CloseResolutionText,
    ) -> None:
        """One CRITICAL carrying everything the manual accounting needs.

        CRITICAL rather than WARNING: the bot is dropping a record of money it
        moved, and no later pass will revisit it. `Decimal` crosses ``extra=``
        directly per the money rule; the datetime goes as ``.isoformat()`` and
        the exception as its type and message, because neither is on the
        whitelist that may cross unconverted.

        **THE THREE OUTCOMES MUST BE TELLABLE APART FROM THE LINE ALONE**, and
        one CRITICAL saying only "resolved" would not manage it. They ask
        different things of the operator. A confirmed fill that was BOOKED asks
        nothing -- the ledger carries the trade and the line is a record. A
        confirmed fill that was NOT booked means a trade is missing from the
        ledger, so the work is bookkeeping. An unconfirmed one means inventory
        may still be at the venue and the bot has just stopped trading
        everything, so the work is to look at the account. `outcome` carries the
        discriminator and `resolution` spells out what follows from it.

        **THE BOOKED BRANCH EXISTS BECAUSE THE OLD TEXT BECAME FALSE**, not to
        add a label. It read *"NOTHING WAS BOOKED by this bot ... enter the
        executed quantity and quote total below by hand"*, and under ruling 5
        an operator following that would enter a trade the ledger already holds
        -- the double-entry counterpart of B1's double-sell, reached the same
        way, by acting on a line that describes the previous design.

        **AND THE COMMIT THAT WROTE THAT PARAGRAPH LEFT THE HEADLINE SAYING THE
        VERY THING IT CONDEMNS.** `outcome` and `resolution` were corrected;
        the ``_log.critical`` message was not, and went on reading *"a restored
        close record was resolved and DROPPED UNBOOKED"* on every branch --
        including the booked one, where an operator reading the headline would
        make the entry the resolution forbids two fields away. `M5i-007`,
        MEASURED: the three were observed disagreeing inside one record.

        **SO THE THREE FIELDS ARE NOW ONE VALUE**, :class:`_CloseResolutionText`,
        selected by ONE ternary. A branch cannot update two of them and miss the
        third, because there are no longer three things to update.

        **THAT COLLAPSES TWO DISCRIMINATORS TO ONE, AND THAT IS THE POINT OF
        DOING IT HERE RATHER THAN LATER.** This method used to evaluate the
        ``booked``/``filled`` chain TWICE -- once for `outcome`, once for
        `resolution` -- so it already held two copies before a third was
        contemplated (`M5i-014`). The eventual fix for `M5h-371` makes the
        discriminator a CONSEQUENCE of the write rather than a prediction of it;
        whatever shape that takes, it now has ONE expression to convert in this
        method instead of two, and cannot convert one and leave the other.

        **THAT FIX IS OPTION 3, IT HAS LANDED, AND THE ONE EXPRESSION MOVED
        RATHER THAN MULTIPLIED.** This method no longer discriminates at all: it
        takes a :class:`_CloseResolutionText` and renders it. The selection sits
        in `_resolve_close`'s ``finally``, beside the write whose answer it
        reads, because a label computed anywhere else is a PREDICTION -- which
        is exactly what `M5h-371` was. `M5i-014`'s constraint is honoured by
        RELOCATION, not by extension: there is still exactly one site that turns
        state into text, and this method is no longer it.

        **WHAT THIS NO LONGER FAILS TO FIX.** The paragraph here used to warn
        that *"the label itself can still lie"* -- the booked `resolution`
        asserting credited proceeds and accrued P&L while `_book_resolved_close`
        swallowed its own failure. That is closed: the booking returns a verdict
        and a failed write selects `_RESOLVED_BOOK_FAILED`, which claims neither.
        Corrected in place because it is a claim about the tree. `M5i-001` and
        `M5i-008` are closed with it on this path. What remains open is `(ii)`,
        the shared bookability predicate, which is a different obligation.

        **``restored`` WAS DROPPED BECAUSE NOTHING HERE CAN KNOW IT**
        (`M5i-011`). :class:`PendingClose` carries no provenance field, and the
        two sites that build one -- ``modes.py``'s boot restore and
        `_execute_close` -- produce identical objects; ``restored_pending`` is
        flattened into ``_pending`` with no marker surviving. A string asserting
        provenance the code cannot determine is a different defect from one
        asserting an outcome it got wrong, and it was false on all three
        branches rather than one. The replacement says "a pending close record",
        which is true of both doors.

        **FOUR OUTCOMES NOW, NOT THREE**, and the fourth is not a relabelling.
        `_RESOLVED_BOOK_FAILED` describes a state the other three cannot: the
        write was ATTEMPTED and failed, so the position SURVIVES and the ledger
        may be half-applied. `M5h-370`/W1 named that state as one nothing could
        distinguish -- V2, booking never ran, and V5, booking ran and wrote
        nothing, leave identical portfolio state. The label is what separates
        them, and it is the reason this method's three-way ternary could not
        simply have grown a fourth branch here.
        """
        extra: dict[str, object] = {
            "event": _EVENT_CLOSE_RESOLVED,
            "symbol": record.symbol,
            "quantity": record.quantity,
            "entry_bar_time": record.entry_bar_time.isoformat(),
            "generation": record.generation,
            "close_client_order_id": close_client_order_id(
                record.symbol, record.entry_bar_time, generation=record.generation
            ),
            "candle_time": candle.close_time.isoformat(),
            "outcome": texts.outcome,
            "resolution": texts.resolution,
        }
        if order is not None:
            extra["status"] = order.status.value
            extra["executed_qty"] = order.filled_quantity
            extra["quote_total"] = order.filled_quote_quantity
        if failure is not None:
            extra["error_type"] = type(failure).__name__
            extra["error"] = str(failure)
        _log.critical(texts.message, record.symbol, extra=extra)

    async def _confirm_protective_legs(
        self, position: Position, *, started_at: datetime
    ) -> tuple[tuple[LegReport, ...], dict[str, str]]:
        """Point-query each REQUESTED protective leg. Reads only; never raises.

        Returns the reports and, separately, the error type per leg that could
        not be read -- separately because `LegReport` is the DECISION's input and
        an exception's type is not something the decision may branch on. It
        belongs in the log beside the null, not in the value the table reads.

        The ids are derived, not remembered: Q-C section 6 makes a generation-0
        leg id pure computation over ``(symbol, entry_bar_time, leg)``, and
        `Position` carries the bar. **`generation` is 0 and is NOT read off the
        position, because `Position` does not carry one** -- the same constant
        `reconcile_open_positions` uses, for the same reason: nothing in this
        tree computes a non-zero generation yet, and the first re-placement is
        what arms it.
        """
        requested = [
            (OrderListLeg.STOP_LOSS, position.stop_loss),
            (OrderListLeg.TAKE_PROFIT, position.take_profit),
        ]
        reports: list[LegReport] = []
        failures: dict[str, str] = {}

        for leg, level in requested:
            if level is None:
                # Never requested, so there is no id and nothing to ask. Not a
                # failure and not an unreadable leg -- it is absent from the
                # report set entirely, which is what keeps `plan_close`'s
                # unreadable row about legs that were actually asked for.
                continue

            bounds = self._budget.bounds_for_next_call(started_at=started_at, now=utc_now())
            if bounds is None:
                # The sequence is spent. REFUSED TO BEGIN, never abandoned
                # mid-flight -- and the leg is reported unreadable rather than
                # skipped, so the decision sees a hole instead of a clean set.
                failures[leg.value] = "budget_exhausted"
                reports.append(LegReport(leg=leg.value, executed=None, requested=position.quantity))
                continue

            try:
                order = await self._client.get_order(
                    position.symbol,
                    client_order_id=client_order_id(
                        position.symbol,
                        position.entry_bar_time,
                        leg,
                        generation=_CLOSE_GENERATION,
                    ),
                    timeout_s=bounds.timeout_s,
                    attempts=bounds.attempts,
                )
            except Exception as exc:  # dispatch must never raise; see the module docstring
                self._log_failure("close-confirm", position.symbol, exc)
                failures[leg.value] = type(exc).__name__
                reports.append(LegReport(leg=leg.value, executed=None, requested=position.quantity))
                continue

            reports.append(
                LegReport(
                    leg=leg.value,
                    executed=order.filled_quantity,
                    requested=position.quantity,
                    status=order.status.value,
                )
            )

        return tuple(reports), failures

    def _refuse(self, signal: Signal, reason: str, candle: Candle) -> None:
        _log.warning(
            "Dispatch refused",
            extra={
                "event": _EVENT_REFUSED,
                "symbol": signal.symbol,
                "action": signal.action.value,
                "reason": reason,
                "candle_time": candle.close_time.isoformat(),
            },
        )

    @staticmethod
    def _log_failure(phase: str, symbol: str, exc: Exception) -> None:
        _log.error(
            "Executor phase failed",
            extra={
                "event": "collaborator_failed",
                "phase": phase,
                "symbol": symbol,
                "error_type": type(exc).__name__,
                "error": str(exc),
            },
        )
