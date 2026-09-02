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
from typing import TYPE_CHECKING

from trading_bot.core.assessment import EntryIntent
from trading_bot.core.enums import PositionSide, ProtectionState
from trading_bot.core.exceptions import ClientRefusalError
from trading_bot.core.models import (
    Money,
    OrderRequest,
    OtocoOrderListRequest,
    OtoOrderListRequest,
    Position,
)
from trading_bot.execution.dispatch_budget import DispatchBudget
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

__all__ = ["OrderExecutor", "PendingPlacement"]


def _matched_list_id(verdict: PlacementVerdict) -> str | None:
    """The list id of the single live match, or ``None``.

    ``matched`` can hold more than one -- MEASURED, a Testnet census found one
    ``listClientOrderId`` mapping to three lists -- but ``PLACED_LIVE`` is only
    returned when exactly one of them is live, so the id is unambiguous here.
    ``None`` rather than a guess if the shape is ever otherwise: an absent
    ``order_list_id`` on the position is honest, where a wrong one would send
    the reconciler to compare against somebody else's legs.
    """
    live = [ol for ol in verdict.matched if ol.list_order_status in _LIVE_LIST_STATUSES]
    if len(live) != 1:
        return None
    return live[0].list_client_order_id


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

_REASON_CLOSE = "close_not_implemented"
_REASON_UNPROTECTED = "unprotected_branch"
_REASON_NO_BUDGET = "budget_exhausted"
_REASON_PENDING = "placement_pending"
_REASON_CLIENT_REFUSAL = "client_refusal"
#: ITS OWN REASON, never the budget's and never the pending guard's. An
#: operator reading this must be sent to the DISK; reusing another string here
#: would send them to `dispatch_deadline_s` for a cause that is not there.
_REASON_STORE_UNWRITABLE = "store_unwritable"


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
    #: ``PendingPlacement``, which is defined immediately above it. A forward
    #: reference would need a quoted name, and this project's style forbids
    #: those in new code.
    PendingWriter = Callable[[tuple[PendingPlacement, ...]], None]


class OrderExecutor:
    """Dispatches approved entries; resolves ambiguous writes on the next bar."""

    def __init__(
        self,
        *,
        client: ExchangeClient,
        portfolio: Portfolio,
        budget: DispatchBudget,
        persist_pending: PendingWriter | None = None,
        restored_pending: Sequence[PendingPlacement] = (),
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
        self._pending: dict[str, PendingPlacement] = {
            record.symbol: record for record in restored_pending
        }

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
            bounds = self._budget.bounds_for_next_call(started_at=started_at, now=utc_now())
            if bounds is None:
                # Out of budget this bar. The record survives to the next one --
                # that is the whole point of holding it.
                break
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
                self._open_position(
                    symbol=symbol,
                    quantity=record.quantity,
                    entry_limit=record.entry_limit,
                    stop_loss=record.stop_loss,
                    take_profit=record.take_profit,
                    entry_bar_time=record.entry_bar_time,
                    order_list_id=_matched_list_id(verdict),
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

        # R21, refusal one: CLOSE is not implemented, and is refused BY NAME.
        # `RiskManager.evaluate` produces an `ExitIntent` today, so this is a
        # reachable state and not a defensive branch. A dropped signal is how an
        # operator discovers the gap by not seeing an exit; a named refusal is
        # how they discover it by reading one line. CLOSE dispatch is M5g's.
        if not isinstance(intent, EntryIntent):
            self._refuse(signal, _REASON_CLOSE, candle)
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
        self._open_position(
            symbol=intent.symbol,
            quantity=intent.quantity,
            entry_limit=intent.entry_limit,
            stop_loss=intent.levels.stop_loss,
            take_profit=intent.levels.take_profit,
            entry_bar_time=entry_bar_time,
            order_list_id=order_list.list_client_order_id,
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

    def _open_position(
        self,
        *,
        symbol: str,
        quantity: Money,
        entry_limit: Money,
        stop_loss: Money | None,
        take_profit: Money | None,
        entry_bar_time: datetime,
        order_list_id: str | None,
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
        position = Position(
            symbol=symbol,
            side=PositionSide.LONG,
            quantity=quantity,
            entry_price=entry_limit,
            entry_bar_time=entry_bar_time,
            protection=ProtectionState.UNKNOWN,
            order_list_id=order_list_id,
            stop_loss=stop_loss,
            take_profit=take_profit,
        )
        self._portfolio.open_position(position, cost=quantity * entry_limit)

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

    def _persist_quietly(self, records: tuple[PendingPlacement, ...], symbol: str) -> None:
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
