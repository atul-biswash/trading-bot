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
from trading_bot.core.models import (
    OrderRequest,
    OtocoOrderListRequest,
    OtoOrderListRequest,
    Position,
)
from trading_bot.execution.dispatch_budget import DispatchBudget
from trading_bot.execution.placement import build_placement
from trading_bot.execution.resolution import PlacementOutcome, resolve_placement
from trading_bot.utils.helpers import utc_now
from trading_bot.utils.logger import get_logger

if TYPE_CHECKING:  # pragma: no cover - typing only
    from datetime import datetime

    from trading_bot.core.assessment import RiskAssessment
    from trading_bot.core.interfaces import ExchangeClient
    from trading_bot.core.models import Candle, OrderList, Signal
    from trading_bot.core.portfolio import Portfolio

__all__ = ["OrderExecutor", "PendingPlacement"]

_log = get_logger(__name__)

_EVENT_PLACED = "order_placed"
_EVENT_REFUSED = "dispatch_refused"
_EVENT_AMBIGUOUS = "placement_ambiguous"
_EVENT_RESOLVED = "placement_resolved"

_REASON_CLOSE = "close_not_implemented"
_REASON_UNPROTECTED = "unprotected_branch"
_REASON_NO_BUDGET = "budget_exhausted"
_REASON_PENDING = "placement_pending"


@dataclass(frozen=True, slots=True)
class PendingPlacement:
    """A placement whose outcome we did not observe, awaiting resolution.

    **Three fields, and every one of them is a SEED rather than a fact about a
    position.** Q-C section 6 makes a generation-0 client order id derivable
    from ``(symbol, entry_bar_time, generation)`` by pure computation, so this
    record is *reconstructible input*, not persisted state -- it carries what
    the query needs to re-derive the ids we would have sent, and nothing else.

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


class OrderExecutor:
    """Dispatches approved entries; resolves ambiguous writes on the next bar."""

    def __init__(
        self,
        *,
        client: ExchangeClient,
        portfolio: Portfolio,
        budget: DispatchBudget,
    ) -> None:
        self._client = client
        self._portfolio = portfolio
        self._budget = budget
        self._pending: dict[str, PendingPlacement] = {}

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
                _log.warning(
                    "Placement still unresolved",
                    extra={
                        "event": _EVENT_RESOLVED,
                        "symbol": symbol,
                        "outcome": verdict.outcome.value,
                        "reason": verdict.reason,
                        "candle_time": candle.close_time.isoformat(),
                    },
                )
                continue

            del self._pending[symbol]
            _log.info(
                "Placement resolved",
                extra={
                    "event": _EVENT_RESOLVED,
                    "symbol": symbol,
                    "outcome": verdict.outcome.value,
                    "reason": verdict.reason,
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

        # Mark BEFORE the write. A record created after a call that never
        # returned would not exist, which is the exact state it is for.
        self._pending[signal.symbol] = PendingPlacement(
            symbol=signal.symbol, entry_bar_time=entry_bar_time, generation=0
        )
        try:
            order_list = await self._place(request, bounds.timeout_s, bounds.attempts)
        except Exception as exc:  # never raises; see the module docstring
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
        self._record(intent, order_list, entry_bar_time=entry_bar_time)
        _log.info(
            "Order list placed",
            extra={
                "event": _EVENT_PLACED,
                "symbol": signal.symbol,
                "quantity": intent.quantity,
                "entry": intent.entry_limit,
                "stop_loss": intent.levels.stop_loss,
                "order_list_id": order_list.list_client_order_id,
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

    def _record(
        self, intent: EntryIntent, order_list: OrderList, *, entry_bar_time: datetime
    ) -> None:
        """Construct the position this placement opened, UNKNOWN until reconciled.

        **R19 / M5e-075: every ``Position`` is constructed with
        ``ProtectionState.UNKNOWN``.** M5e's grounds, and they are not restated
        loosely because the direction is the whole argument: a position wrongly
        marked ``UNKNOWN`` costs entries until the next pass corrects it, while
        one wrongly marked ``ACTIVE`` is priced off a stop nobody confirmed.

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
            symbol=intent.symbol,
            side=PositionSide.LONG,
            quantity=intent.quantity,
            entry_price=intent.entry_limit,
            entry_bar_time=entry_bar_time,
            protection=ProtectionState.UNKNOWN,
            order_list_id=order_list.list_client_order_id,
            stop_loss=intent.levels.stop_loss,
            take_profit=intent.levels.take_profit,
        )
        self._portfolio.open_position(position, cost=intent.quantity * intent.entry_limit)

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
