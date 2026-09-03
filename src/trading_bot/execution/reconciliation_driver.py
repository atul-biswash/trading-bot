"""Drive the reconciliation pass from the candle subscription, within a budget.

**This is the caller ``reconciliation.py`` deliberately does not contain.** That
module's docstring places driving outside it in those words; this is where it
lives, because driving is execution's job and a budget is the driver's to set.

**It subscribes to CANDLES, not to signals.** Reconciliation runs over every
open position on *any* pair's candle, so staleness is bounded by the shortest
configured timeframe rather than by the slowest position's -- and ``on_signal``
skips quiet bars, which is most of them. That places this on the provider's
``_notify`` layer, the middle of the three isolation layers, and its isolation
is what contains a failure here rather than the engine's.

**It must never raise**, for the reason the signal handler must not: a
subscriber that raises is caught and logged by ``_notify`` with no structured
fields, once per bar, forever, and no counter anywhere quarantines it. So each
phase gets its own ``try`` and its own name in the log line.

**IT ALSO BOOKS THE EXITS IT OBSERVES**, and that is a third phase rather than
a detail of the second. Seven trades closed at the venue before this existed and
none was booked: ``Portfolio.close_position`` had ZERO callers in ``src/``, so
``record_realised_pnl`` -- whose only call site is inside it -- never ran, and
``realised_today`` returned ``Decimal(0)`` forever while the daily-loss limit
wore its name and measured nothing but committed risk. The driver is where
booking belongs because it is the object that already holds the ``Portfolio``,
already receives every assessment and already owns the durable write; the two
classifiers stay pure. See :meth:`ReconciliationDriver._book_exits`.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import TYPE_CHECKING

# A PRIVATE name, imported across modules deliberately. The alternative is a
# second definition of "which protection states may be trusted", and two
# sources of truth for that is the drift this project guards hardest against --
# the whitelist decides whether a position counts as uncomputable, which
# decides whether entries are refused portfolio-wide. Note the useful
# consequence: admitting `ACTIVE` to it later quiets this warning for healthy
# positions automatically, because the line and the refusal are then keyed off
# the same fact. Making it public is a `core/` decision and is not taken here.
from trading_bot.core.portfolio import _TRUSTED_PROTECTION
from trading_bot.execution.reconciliation import (
    reconcile_open_positions,
    resolve_unresolved_legs,
)
from trading_bot.utils.helpers import timeframe_to_ms, utc_now
from trading_bot.utils.logger import get_logger

if TYPE_CHECKING:  # pragma: no cover - typing only
    from collections.abc import Mapping, Sequence

    from trading_bot.config.models import AppConfig
    from trading_bot.core.interfaces import ExchangeClient
    from trading_bot.core.models import Candle, Position
    from trading_bot.core.portfolio import Ledger, Portfolio
    from trading_bot.execution.reconciliation import ProtectionAssessment

    #: Writes the accrued ledger durably. **Raising means the write did NOT
    #: happen**, and the caller must treat the ledger as unpersisted.
    #:
    #: A callable rather than an imported module, so ``execution/`` never
    #: depends on ``persistence/``: `CLAUDE.md` has outer layers "depend inward
    #: only", and the composition root is the one layer permitted to know both.
    #: The argument is ``core.portfolio.Ledger``, an INWARD type this module
    #: may name; ``store.LedgerRecord`` never crosses this boundary.
    #:
    #: It is also what keeps the whole-file ``store.save`` safe -- the root owns
    #: the pending set this driver never sees, and carries it across every
    #: ledger write.
    LedgerWriter = Callable[[Ledger], None]

__all__ = ["ReconciliationBudget", "ReconciliationDriver"]

_log = get_logger(__name__)

#: The ``event`` values, one constant each so a rename cannot leave the
#: emitter and its test disagreeing silently. Mirrors ``engine/modes.py``.
_EVENT_PASS = "reconciliation_pass"
_EVENT_UNTRUSTED = "reconciliation_untrusted"
_EVENT_PHASE_FAILED = "reconciliation_phase_failed"
_EVENT_BOOKED = "exit_booked"
_EVENT_BOOK_REFUSED = "exit_book_refused"
_EVENT_LEDGER_UNWRITABLE = "ledger_unwritable"

_PHASE_PASS = "reconciliation_pass"
_PHASE_RESOLUTION = "leg_resolution"
_PHASE_BOOKING = "exit_booking"

#: A clock, injected. Shaped exactly like ``risk.manager.Clock`` and
#: deliberately NOT imported from there: ``execution/`` taking a dependency on
#: ``risk/`` for a type alias buys nothing, since nothing else here needs that
#: module and the alias carries no behaviour. A shared clock type belongs in
#: ``core/``, which both layers already import; moving it there is a domain-layer
#: decision rather than this module's, so the duplication is recorded instead of
#: made someone else's problem.
_Clock = Callable[[], datetime]


@dataclass(frozen=True, slots=True)
class ReconciliationBudget:
    """What one reconciliation phase may spend, derived from config.

    **A frozen dataclass rather than a pydantic model.** Every field is derived
    from config that ``AppConfig`` has already validated, so a validator here
    would re-check what the config layer guarantees, and no field is money.
    That is ``LiveSystem``'s reasoning in the module that constructs this one.
    It also avoids adding a **fourth** private ``_Frozen`` base to a tree whose
    existing three are a recorded open item -- growing that count in passing is
    exactly the drift the item exists to notice.

    **The total is a CALL COUNT, and the count is the guarantee.** The coherence
    validator reserves ``max_open_positions x reconcile_deadline_s`` for
    reconciliation and every call is bounded by ``reconcile_deadline_s``, so the
    reservation admits exactly ``max_open_positions`` calls. The pass and the
    point queries share that, met with equality and never exceeded.
    """

    #: How stale a position's stamp must be before it is re-read. The shortest
    #: enabled timeframe: the driver fires on any pair's candle, so a shorter
    #: interval would re-read on a bar that taught it nothing.
    dedup_interval: timedelta
    #: Total calls the whole phase may make, pass plus point queries.
    max_calls: int
    #: Bound on ONE call, in seconds.
    timeout_s: float
    #: Attempts per call.
    attempts: int

    @classmethod
    def from_config(
        cls, config: AppConfig, *, timeframes: Mapping[str, str]
    ) -> ReconciliationBudget:
        """Derive the budget from validated config and the boot's timeframe map.

        ``timeframes`` is what ``_pair_timeframes`` already built, so the
        shortest bar is derived once. Re-deriving it from ``trading.pairs``
        would duplicate that function's duplicate-symbol and empty-set refusals
        beside it, and two refusals for one condition drift apart.

        **``attempts = 1`` is FORCED, and what makes it safe is different from
        what makes it forced.** Forced: ``attempts x timeout_s <= T_recon``
        admits exactly one attempt at the full deadline, and splitting
        ``T_recon`` into a per-attempt share would be a tail claim that the only
        samples in existence -- six, bimodal, from one host -- cannot support.
        Safe: **the retry is not removed, it moves to the CADENCE.** A transient
        connection failure leaves the position unstamped, so it sorts first and
        is re-read on the next bar. The retry still exists; it is one bar long
        instead of 3.5 s of backoff.

        **THAT COVERS THE PASS AND NOT THE RESOLVER.** An unstamped position is
        re-read next bar, so a failed enumeration costs one cycle. A failed
        POINT QUERY leaves that leg unqueried, and under the all-or-nothing
        behaviour recorded as ``M5e-053`` a position whose single leftover call
        fails may never complete rather than waiting a bar -- because the next
        cycle re-derives the same leg order and spends the same one call on the
        same first leg. "One bar long" is a statement about the pass only. The
        L-leg reservation closes it by making resolution complete a position in
        one cycle.

        Two alternatives are rejected rather than unconsidered. ``attempts = 2``
        at ``timeout_s = 1.25`` clears the observed slow mode but is the tail
        claim above. Budgeting point queries *additionally* to
        ``max_open_positions x reconcile_deadline_s`` would break the only
        guarantee the coherence validator computes, and break it silently.

        :raises ValueError: ``timeframes`` is empty. That is a programming
            error rather than a config one -- ``_pair_timeframes`` refuses an
            empty enabled-pair set at boot, with a message naming
            ``config.yaml``, before this is reached.
        """
        if not timeframes:
            raise ValueError(
                "ReconciliationBudget.from_config needs at least one timeframe; an empty "
                "enabled-pair set is refused at boot by _pair_timeframes, so reaching here "
                "with none means the root was bypassed."
            )
        shortest_ms = min(timeframe_to_ms(timeframe) for timeframe in timeframes.values())
        return cls(
            dedup_interval=timedelta(milliseconds=shortest_ms),
            max_calls=config.risk.limits.max_open_positions,
            timeout_s=config.risk.reconcile_deadline_s,
            attempts=1,
        )


class ReconciliationDriver:
    """Runs the pass and the resolver on every candle, and never raises.

    The candle is a **trigger, not a subject**: its symbol is ignored, because
    reconciliation visits every open position on any pair's bar. It is carried
    into the failure log so an operator can tell which bar a failure fell on.
    """

    def __init__(
        self,
        *,
        portfolio: Portfolio,
        client: ExchangeClient,
        budget: ReconciliationBudget,
        clock: _Clock = utc_now,
        persist_ledger: LedgerWriter | None = None,
    ) -> None:
        self._portfolio = portfolio
        self._client = client
        self._budget = budget
        self._clock = clock
        #: Writes the accrued ledger durably. ``None`` means DO NOT PERSIST,
        #: and that default is what keeps every existing construction and test
        #: byte-for-byte unchanged. The composition root supplies the real
        #: writer.
        #:
        #: **`_book_exits` CALLS IT**, once per pass that booked anything. It
        #: was a mechanism with no caller for exactly one commit -- the same
        #: shape `OrderExecutor.persist_pending` had at C8 -- and this is the
        #: caller arriving.
        self._persist_ledger = persist_ledger

    async def __call__(self, candle: Candle) -> None:
        """One reconciliation phase. A ``CandleHandler``; never raises.

        **One clock reading, passed to both phases.** A two-phase
        reconciliation records the cycle it belongs to rather than the moment
        its second half happened to finish, and the pass's dedup arithmetic and
        the resolver's stamp then agree by construction instead of by luck.

        **A failed pass SKIPS the resolver; it does not call it with an empty
        tuple.** The two are distinguished by CONTROL FLOW, not by a value: the
        exception path returns. An empty tuple handed to the resolver is
        indistinguishable from a successful pass with nothing to resolve, which
        is the fake-default rule one level up -- an empty enumeration is a real
        classification, so the honest signal for "no answer" is never a value
        that also means something else.

        A failed *resolver* is different: the pass has already written what it
        learned, so its verdicts are reported unsharpened rather than
        discarded.
        """
        now = self._clock()

        try:
            assessments = await reconcile_open_positions(
                portfolio=self._portfolio,
                client=self._client,
                now=now,
                dedup_interval=self._budget.dedup_interval,
                max_calls=self._budget.max_calls,
                timeout_s=self._budget.timeout_s,
                attempts=self._budget.attempts,
            )
        except Exception as exc:  # the driver must never raise; see the docstring
            self._log_phase_failure(_PHASE_PASS, candle, exc)
            return

        if not assessments:
            # Nothing was due. Silent on purpose: this fires every bar on every
            # pair, and a line per quiet bar is how an operator learns to skim
            # the ones that mean something.
            return

        # Sound only because the pass makes exactly one call per returned
        # assessment, which its own tests pin.
        remainder = self._budget.max_calls - len(assessments)
        try:
            reported: Sequence[
                tuple[Position, ProtectionAssessment]
            ] = await resolve_unresolved_legs(
                assessments=assessments,
                client=self._client,
                max_queries=remainder,
                now=now,
                timeout_s=self._budget.timeout_s,
                attempts=self._budget.attempts,
            )
        except Exception as exc:  # the driver must never raise; see the docstring
            self._log_phase_failure(_PHASE_RESOLUTION, candle, exc)
            reported = assessments

        self._report(reported, queries=remainder)

        # BOOKING RUNS AFTER RESOLUTION, and the ordering is forced by where an
        # `ExitFill` can come from. There are two fill sites: one inside
        # `classify_protection`, for a protective leg the enumeration still
        # shows, and one inside the resolver's `_refine`, for a leg ABSENT from
        # the enumeration that a point query finds `FILLED`. A stop that
        # triggered and left the book is the second -- run 3's own shape -- so
        # booking ahead of the resolver would miss the commonest real exit.
        # `reported` is the resolver's output on the success path and the
        # pass's on the resolver-failure path, so one call covers both.
        #
        # AFTER `_report`, not before, because `_report` describes what
        # RECONCILIATION observed and booking is the response to it. A pass that
        # saw a filled stop genuinely did see untrusted protection; the warning
        # is true, and the booking line that follows says what was done about it.
        try:
            self._book_exits(reported, now=now)
        except Exception as exc:  # the driver must never raise; see the docstring
            self._log_phase_failure(_PHASE_BOOKING, candle, exc)

    def _report(
        self,
        results: Sequence[tuple[Position, ProtectionAssessment]],
        *,
        queries: int,
    ) -> None:
        """One summary line, and one warning line if anything is untrusted.

        **PER PASS, NOT PER POSITION, and that is the whole design.** A
        persistently unresolved position is a persistent condition, and
        repeating it once per position per bar is precisely what Q-B site 4's
        deferred design exists to avoid -- it escalates a *self-clearing*
        condition at a **distinct marker** and promotes it to terminal only
        after N cycles, on the grounds that escalating a self-clearing
        condition at the same level as a terminal one is how a ``CRITICAL``
        line stops being read. Until that escalation exists, one warning per
        pass naming every affected symbol is the honest interim: an operator
        gets the whole picture once rather than a fragment repeatedly.

        **This is the first consumer of the reasons the pass returns.** They
        cannot be recovered from a written ``Position``, which is why the pass
        hands them back, and a portfolio-wide refusal is exactly the situation
        an operator is owed a cause for.

        **Counts by state cross as a SINGLE STRING FIELD.** The ``extra=``
        whitelist admits only ``str``/``int``/``float``/``bool``/``None``/
        ``Decimal``; a mapping would reach the JSON sink as an object and the
        plain sink as a Python ``repr`` via ``default=str``, which is the
        two-sink disagreement the whitelist exists to prevent. Enum members
        cross as ``.value`` for the same reason.
        """
        counts = Counter(assessment.state.value for _position, assessment in results)
        _log.info(
            "Reconciled %d position(s)",
            len(results),
            extra={
                "event": _EVENT_PASS,
                "positions": len(results),
                "calls": len(results),
                "queries": queries,
                "states": ",".join(f"{state}={n}" for state, n in sorted(counts.items())),
            },
        )

        untrusted = [
            (position, assessment)
            for position, assessment in results
            if assessment.state not in _TRUSTED_PROTECTION
        ]
        if not untrusted:
            return
        _log.warning(
            "%d position(s) carry protection this bot does not trust",
            len(untrusted),
            extra={
                "event": _EVENT_UNTRUSTED,
                "count": len(untrusted),
                "symbols": ",".join(position.symbol for position, _a in untrusted),
                "detail": "; ".join(assessment.reason for _p, assessment in untrusted),
            },
        )

    def _book_exits(
        self,
        results: Sequence[tuple[Position, ProtectionAssessment]],
        *,
        now: datetime,
    ) -> None:
        """Book every COMPLETE protective fill this pass saw, then save once.

        **THE DRIVER BOOKS, AND NEITHER CLASSIFIER DOES.** ``classify_protection``
        and ``_refine`` are pure functions over what the venue reported: they
        take no ``Portfolio``, hold no clock and write nothing, which is what
        lets them be tested over fabricated payloads with no state at all.
        Booking mutates the ledger, credits ``free_quote`` and deletes a
        position -- so it belongs to the object that already holds the
        ``Portfolio``, already receives every assessment, and already owns the
        durable write. Moving it into a classifier would give a pure function a
        portfolio argument and a persistence side effect, which is two seams
        broken to save one loop.

        **IDEMPOTENCY IS BY DELETION -- no flag and no memo.**
        ``reconcile_open_positions`` builds its work list from
        ``portfolio.open_positions``, which reads ``self.positions.values()``
        afresh on every call. ``close_position`` removes the symbol from
        ``positions``, so the next pass cannot enumerate it, cannot assess it
        and cannot hand it back here. A "already booked" flag would be a second
        source of truth for a fact the portfolio already expresses by the
        position's absence, and it would go stale the moment anything else
        closed a position.

        **THE FIVE STATES, all decided here.** A fill with a quote total, a
        complete quantity and a known cost basis is BOOKED. A fill whose
        ``filled_quote_quantity`` is ``None`` is REFUSED and escalated -- that
        absence means *a leg filled and cannot be priced*, which is a different
        fact from ``exit_fill is None`` and must not pass silently. A PARTIAL
        fill is not booked: it keeps ``UNKNOWN``, which is today's behaviour,
        and the existing ``COMMITTED_RISK_UNKNOWN`` interlock refuses
        portfolio-wide. No ``exit_fill`` at all is the ordinary healthy pass and
        says nothing. And a position with no ``entry_fill_price`` is REFUSED --
        checked HERE rather than caught from ``close_position``, so
        ``unrealized_pnl``'s raise is never used as control flow.

        **THE COMPLETENESS TEST IS ``!=``, NOT ``<``.** They differ only on an
        over-fill, which the venue cannot produce: a leg's ``executedQty``
        cannot exceed its ``origQty``, and that is the position's quantity.
        ``<`` would BOOK such a fill; ``!=`` refuses it. The unreachable state
        gets the conservative answer without inventing a row for it. Exponent
        does not enter into it -- ``Decimal`` compares numerically, so
        ``0.02257`` and ``0.02257000`` are equal here and differ only where a
        division is involved.

        **THE ORPHAN CHECK GUARDS A CURRENTLY-UNREACHABLE STATE.** An orphan is
        an order list resting at the venue with no ``Position`` tracking it, so
        it has nothing to pair with an assessment: every entry in ``results``
        came from ``portfolio.open_positions``, and orphans bypass this
        structurally rather than by a test. The check exists for the future edit
        that routes one here anyway -- it refuses loudly instead of calling
        ``close_position`` for a symbol the portfolio does not hold, which would
        return ``Decimal(0)`` and look like a clean no-op. A ``raise`` and not an
        ``assert``, which vanishes under ``-O``; the caller's ``try`` turns it
        into a logged phase failure, so the driver's never-raise contract holds.

        **ONE SAVE PER PASS, AFTER ALL BOOKINGS.** ``store.save`` is whole-file
        and fsync'd -- ~41.6 ms median on this volume -- and a pass can close
        more than one position, so a save per booking pays that cost per
        position for a file whose final content is identical.

        **APPLY, THEN SAVE, and the residual is named rather than implied.**
        Memory is authoritative and the disk write follows it. On a crash
        BETWEEN the two, disk is one pass stale -- and nothing revisits it,
        because the position is already gone from ``positions`` and no later
        pass can enumerate it. The realised figure for that trade is lost. The
        alternative, saving before applying, writes a ledger the portfolio does
        not hold and is stale in the direction that UNDER-reports nothing but
        over-reports a booking that then failed; neither ordering is free, and
        this one keeps the durable file a subset of what actually happened.

        **THE C12 RESIDUAL, AND THIS COMMIT IS WHAT ARMS IT.**
        ``close_position`` credits ``free_quote`` before it accrues, so an
        accrual that raises leaves the proceeds credited and the position alive
        -- and the next pass would credit them again. That was recorded as
        acceptable partly because NOTHING CALLED ``close_position``. This method
        is that caller. It is documented rather than closed: reaching it needs a
        non-finite total, which ``Money`` is what rejects, and the surviving
        position makes the failure visible and repeating rather than silent.
        """
        booked = 0
        for position, assessment in results:
            fill = assessment.exit_fill
            if fill is None:
                # Row 4: the ordinary healthy pass. Silent, like a pass with
                # nothing due -- this is most bars on most positions.
                continue

            if self._portfolio.positions.get(position.symbol) is not position:
                raise ValueError(
                    f"{position.symbol} reached exit booking without being the portfolio's own "
                    "position for that symbol. An orphan has no Position and cannot arrive here; "
                    "reaching this means a caller now pairs assessments with something other than "
                    "portfolio.open_positions, and booking it would silently no-op"
                )

            if fill.filled_quote_quantity is None:
                # Row 2. Distinct from row 4 by construction: a leg DID fill and
                # the venue gave no quote total for it, so a position has closed
                # and cannot be priced. Escalated rather than skipped.
                self._refuse_booking(
                    position.symbol,
                    fill.order_id,
                    "the venue reported a fill with no quote total, so the exit cannot be priced "
                    "and the position is closed at the venue with nothing booked",
                )
                continue

            if fill.filled_quantity != position.quantity:
                # Row 3. Not booked, and NOT a new refusal state: the position
                # keeps `UNKNOWN` from the assessment, and the existing
                # committed-risk interlock refuses entries portfolio-wide. This
                # commit narrows booking to complete fills; it adds no path.
                self._refuse_booking(
                    position.symbol,
                    fill.order_id,
                    f"the fill is partial -- {fill.filled_quantity} executed against a position "
                    f"of {position.quantity} -- so it is not booked and the position keeps its "
                    "untrusted protection",
                )
                continue

            if position.entry_fill_price is None:
                # Row 5, checked BEFORE the call. `entry_price` is NOT a
                # substitute -- it is the requested limit, measured wrong by up
                # to 76.65 per unit, and a ledger is permanent.
                self._refuse_booking(
                    position.symbol,
                    fill.order_id,
                    "the position has no entry_fill_price, so its cost basis is unknown; the "
                    "requested entry_price is not a substitute and would write a permanent "
                    "distortion into the ledger",
                )
                continue

            # Row 1. THE TOTAL PASSES STRAIGHT THROUGH -- no division into a
            # unit price and no re-multiplication. MEASURED, that round trip is
            # lossy: run 3's own shape, 0.02257000 against 35.38691640, returns
            # a delta of -1E-26, and `_dump_money` writes such a residual into
            # `data/state.json` verbatim.
            realised = self._portfolio.close_position(
                position.symbol,
                exit_quote_total=fill.filled_quote_quantity,
                now=now,
            )
            booked += 1
            _log.info(
                "Booked exit for %s",
                position.symbol,
                extra={
                    "event": _EVENT_BOOKED,
                    "symbol": position.symbol,
                    "order_id": fill.order_id,
                    "quantity": fill.filled_quantity,
                    "quote_total": fill.filled_quote_quantity,
                    "realised": realised,
                    "venue_time": (
                        fill.venue_time.isoformat() if fill.venue_time is not None else None
                    ),
                },
            )

        ledger = self._portfolio.ledger
        if booked == 0 or self._persist_ledger is None or ledger is None:
            # `ledger is None` is mypy narrowing, not a branch: `booked > 0`
            # means `record_realised_pnl` ran, and it assigns `self.ledger`
            # unconditionally. The same shape that method's own body uses.
            return
        try:
            self._persist_ledger(ledger)
        except Exception as exc:
            # CRITICAL, and a level above the executor's persist failures
            # deliberately. Those refuse before the venue call and cost one
            # trade; this one happens AFTER the position is gone from memory,
            # so there is nothing left to refuse and no pass that can retry --
            # the apply-then-save residual, arriving.
            _log.critical(
                "Booked exits could not be persisted; the ledger on disk is one pass stale",
                extra={
                    "event": _EVENT_LEDGER_UNWRITABLE,
                    "booked": booked,
                    "realised_pnl": ledger.realised_pnl,
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                },
            )

    @staticmethod
    def _refuse_booking(symbol: str, order_id: str, reason: str) -> None:
        """One line for a fill that was seen and not booked.

        ``WARNING`` rather than ``CRITICAL``: every refusal here leaves the
        position PRESENT and untrusted, so the committed-risk interlock is
        already refusing entries portfolio-wide and the condition is both
        visible and self-announcing on the next pass. Q-B reserves ``CRITICAL``
        for a log line AND a halt, and a halt flag does not exist.
        """
        _log.warning(
            "Exit fill for %s was not booked",
            symbol,
            extra={
                "event": _EVENT_BOOK_REFUSED,
                "symbol": symbol,
                "order_id": order_id,
                "reason": reason,
            },
        )

    def _log_phase_failure(self, phase: str, candle: Candle, exc: Exception) -> None:
        """Report a phase that raised, naming which one and which bar.

        ``exc`` crosses as its type name and its ``str``, never as the object:
        the same ``extra=`` whitelist as above.
        """
        _log.exception(
            "Reconciliation phase %s failed on %s/%s; continuing",
            phase,
            candle.symbol,
            candle.timeframe,
            extra={
                "event": _EVENT_PHASE_FAILED,
                "phase": phase,
                "symbol": candle.symbol,
                "timeframe": candle.timeframe,
                "error_type": type(exc).__name__,
                "error": str(exc),
            },
        )
