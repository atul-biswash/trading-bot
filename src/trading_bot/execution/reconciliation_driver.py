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

**Inert until something opens a position.** ``Position`` is constructed nowhere
in ``src/`` today, so ``open_positions`` is empty and every pass is a no-op.
The reconciler ships before the first order by design, not by accident.
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
    from trading_bot.core.portfolio import Portfolio
    from trading_bot.execution.reconciliation import ProtectionAssessment

__all__ = ["ReconciliationBudget", "ReconciliationDriver"]

_log = get_logger(__name__)

#: The three ``event`` values, one constant each so a rename cannot leave the
#: emitter and its test disagreeing silently. Mirrors ``engine/modes.py``.
_EVENT_PASS = "reconciliation_pass"
_EVENT_UNTRUSTED = "reconciliation_untrusted"
_EVENT_PHASE_FAILED = "reconciliation_phase_failed"

_PHASE_PASS = "reconciliation_pass"
_PHASE_RESOLUTION = "leg_resolution"

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
    ) -> None:
        self._portfolio = portfolio
        self._client = client
        self._budget = budget
        self._clock = clock

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
