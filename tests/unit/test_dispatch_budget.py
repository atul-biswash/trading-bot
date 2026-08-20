"""Tests for the dispatch budget, which is a DEADLINE and not a call count.

No I/O and no clock: the type does not read one, so every case supplies both
instants. That is the hoisted-clock precedent from `RiskManager.evaluate`,
applied within a sequence instead of within an evaluation.

**The fixture deadline is 9.0 and every step is binary-exact** -- 0.5, 1.0, 2.0,
3.0, 4.5. Float subtraction is not associative and a remainder derived from
0.1-like values lands at 0.0009999999999994458 rather than 0.001 (MEASURED), so
inexact steps would force approximate assertions on a type whose whole job is a
bound. The exactness is the fixture's, not the type's.

**The config helper builds an AppConfig with NO PAIRS on purpose.** The coherence
validator returns early on an empty enabled-pair set, so a non-default deadline
can be set here without tripping a constraint that is not under test. It is
written locally rather than imported from `test_config.py`: `CLAUDE.md` records
the one existing test-to-test import as the only such coupling in the tree, and
a second would make an import-time break in one file fail two.
"""

from __future__ import annotations

from dataclasses import fields
from datetime import datetime, timedelta, timezone

import pytest

from trading_bot.config.models import (
    AppConfig,
    BacktestConfig,
    RiskConfig,
    StrategyConfig,
    TradingConfig,
)
from trading_bot.execution.dispatch_budget import CallBounds, DispatchBudget

T0 = datetime(2026, 8, 20, 12, 0, 0, tzinfo=timezone.utc)
NAIVE = datetime(2026, 8, 20, 12, 0, 0)
DEADLINE = 9.0


def _config(*, dispatch_deadline_s: float = DEADLINE) -> AppConfig:
    """An AppConfig carrying only what the budget reads. No pairs -- see above."""
    return AppConfig(
        strategy=StrategyConfig(name="sma_crossover"),
        backtesting=BacktestConfig(start_date="2024-01-01", end_date="2024-02-01"),
        trading=TradingConfig(pairs=[]),
        risk=RiskConfig(dispatch_deadline_s=dispatch_deadline_s),
    )


def _at(seconds: float) -> datetime:
    """An instant `seconds` after the sequence started."""
    return T0 + timedelta(seconds=seconds)


class TestDerivingTheBudget:
    """`from_config`, and that it reads the field rather than knowing a number."""

    def test_the_budget_is_the_whole_sequence_deadline(self) -> None:
        """The shipped default, so the derivation is pinned against a known value.

        Pins the value only. That it is READ rather than remembered is the next
        test's job, and this one deliberately cannot tell the difference.
        """
        assert DispatchBudget.from_config(_config()).deadline_s == DEADLINE

    @pytest.mark.parametrize("configured", [0.5, 9.0, 100.0], ids=["tiny", "shipped", "large"])
    def test_the_deadline_tracks_the_config_field_not_a_constant(self, configured: float) -> None:
        """Three values including the default, because a derivation that returned
        the default as a literal would pass a single-value test and fail this
        one. `risk.dispatch_deadline_s` is PLACEHOLDER -- NOT MEASURED, so the
        value it happens to carry today is exactly what must not be baked in."""
        assert DispatchBudget.from_config(_config(dispatch_deadline_s=configured)).deadline_s == (
            configured
        )

    def test_reading_the_dispatch_field_and_not_the_reconcile_one(self) -> None:
        """Two deadlines live side by side in `RiskConfig` and the shipped values
        differ (9.0 against 3.0), so reading the wrong one is silent and wrong by
        a factor of three."""
        config = _config()
        assert config.risk.reconcile_deadline_s != config.risk.dispatch_deadline_s
        assert DispatchBudget.from_config(config).deadline_s == config.risk.dispatch_deadline_s


class TestThereIsNoCallCount:
    """The absence is the design, so it is asserted rather than left implicit."""

    def test_the_budget_carries_exactly_one_field_and_it_is_the_deadline(self) -> None:
        """An anti-rot test for the whole shape. `max_calls x timeout_s = D` is
        INVARIANT under every divisor, so a call count never sized the
        reservation -- it only sliced it -- and the count itself has been
        measured wrong twice. Reintroducing one here fails this immediately
        rather than quietly restoring the shape that was retired.
        """
        assert tuple(f.name for f in fields(DispatchBudget)) == ("deadline_s",)


class TestTheRemainder:
    """`remaining_s`, including the two instants it refuses."""

    @pytest.mark.parametrize(
        ("elapsed", "expected"),
        [(0.0, 9.0), (0.5, 8.5), (2.0, 7.0), (9.0, 0.0)],
        ids=["start", "half-second-in", "mid", "exactly-spent"],
    )
    def test_the_remainder_is_the_deadline_less_elapsed(
        self, elapsed: float, expected: float
    ) -> None:
        """**No case may have `elapsed == expected`.** A midpoint case does, and
        a mutation returning `elapsed` instead of the remainder would pass it --
        the fixture cannot express the defect it exists to catch. `4.5` was the
        original third case and was replaced for exactly that reason.
        """
        assert elapsed != expected
        budget = DispatchBudget(deadline_s=DEADLINE)
        assert budget.remaining_s(started_at=T0, now=_at(elapsed)) == expected

    def test_an_overrun_is_reported_as_a_negative_remainder_not_raised(self) -> None:
        """A real answer, not an error: it says by how much the sequence has
        already overrun, and `CLAUDE.md` charges that overrun to the next
        invocation's dispatch share. Raising would destroy the quantity the next
        invocation needs.
        """
        budget = DispatchBudget(deadline_s=DEADLINE)
        assert budget.remaining_s(started_at=T0, now=_at(11.0)) == -2.0

    @pytest.mark.parametrize(
        ("started_at", "now", "match"),
        [(NAIVE, T0, "started_at"), (T0, NAIVE, "now")],
        ids=["naive_started_at", "naive_now"],
    )
    def test_a_naive_instant_is_refused_on_either_argument(
        self, started_at: datetime, now: datetime, match: str
    ) -> None:
        """Both, and the message names which. A naive value is read as local time
        and shifts the arithmetic by the host's offset, so the bound would differ
        by machine -- silently, and only where the offset is non-zero."""
        with pytest.raises(ValueError, match=f"{match} must be timezone-aware"):
            DispatchBudget(deadline_s=DEADLINE).remaining_s(started_at=started_at, now=now)

    def test_time_running_backwards_is_refused_rather_than_clamped(self) -> None:
        """The one input that would hand a call a bound LOOSER than the deadline,
        which is the single thing this type exists to prevent. Refused rather
        than clamped to zero: clamping hides the caller bug and the next call's
        bound is wrong either way.
        """
        with pytest.raises(ValueError, match="precedes started_at"):
            DispatchBudget(deadline_s=DEADLINE).remaining_s(started_at=T0, now=_at(-1.0))


class TestTheNextCallsBounds:
    """What a call may spend, and when the sequence refuses to begin one."""

    def test_the_first_call_gets_the_whole_deadline(self) -> None:
        """The loosest bound available, and the reason to prefer this shape. The
        first call of an entry sequence is the placement, whose timeout is the
        one that manufactures the ambiguous write. Under any divisor it was
        bounded at D/n; here it is bounded at D.
        """
        bounds = DispatchBudget(deadline_s=DEADLINE).bounds_for_next_call(started_at=T0, now=T0)
        assert bounds == CallBounds(timeout_s=DEADLINE, attempts=1)

    @pytest.mark.parametrize(
        ("elapsed", "expected"),
        [(0.5, 8.5), (3.0, 6.0), (8.0, 1.0)],
        ids=["early", "mid", "late"],
    )
    def test_each_later_call_gets_only_what_is_left(self, elapsed: float, expected: float) -> None:
        """Same fixture rule as the remainder cases: no case may have
        `elapsed == expected`, or a mutation returning elapsed passes it."""
        assert elapsed != expected
        bounds = DispatchBudget(deadline_s=DEADLINE).bounds_for_next_call(
            started_at=T0, now=_at(elapsed)
        )
        assert bounds is not None
        assert bounds.timeout_s == expected

    @pytest.mark.parametrize(
        "elapsed", [9.0, 9.5, 20.0], ids=["exactly-spent", "just-over", "well-over"]
    )
    def test_a_spent_deadline_refuses_to_begin_a_call(self, elapsed: float) -> None:
        """The refusal is at `remaining <= 0`, so EXACTLY spent refuses too.
        Included because `< 0` and `<= 0` differ on precisely one input and it is
        the one a sequence lands on when its calls sum to the deadline.
        """
        assert (
            DispatchBudget(deadline_s=DEADLINE).bounds_for_next_call(
                started_at=T0, now=_at(elapsed)
            )
            is None
        )

    def test_a_sliver_of_deadline_still_permits_a_call(self) -> None:
        """The complement of the refusal, and it is what makes the deferred
        POSITIVE floor legible rather than invisible: a call may begin with a
        bound far too small to complete, and will simply time out having begun.
        Choosing a floor needs a placement latency this project does not have.
        """
        bounds = DispatchBudget(deadline_s=DEADLINE).bounds_for_next_call(
            started_at=T0, now=_at(8.5)
        )
        assert bounds is not None
        assert bounds.timeout_s == 0.5

    @pytest.mark.parametrize("deadline", [0.5, 9.0, 100.0], ids=["tiny", "shipped", "large"])
    def test_attempts_is_one_and_stays_one(self, deadline: float) -> None:
        """FORCED and INVARIANT, not chosen. `attempts x timeout_s <= remaining`
        with `timeout_s` set to the whole remainder admits exactly one attempt --
        for every deadline and at every point in a sequence. Asserted across
        three deadlines and three positions because a constant someone typed and
        a value the arithmetic forces are indistinguishable at a single point.
        """
        budget = DispatchBudget(deadline_s=deadline)
        observed = set()
        for fraction in (0.0, 0.5, 0.9):
            bounds = budget.bounds_for_next_call(started_at=T0, now=_at(deadline * fraction))
            assert bounds is not None
            observed.add(bounds.attempts)
        assert observed == {1}


class TestTheTotalIsBoundedWithoutACallCount:
    """The property that replaced the divisor, and the reason the count is gone."""

    @pytest.mark.parametrize("calls", [1, 3, 5, 20], ids=["one", "three", "five", "twenty"])
    def test_no_granted_bound_can_run_past_the_deadline(self, calls: int) -> None:
        """The guarantee, stated as the thing that must never happen: a call
        granted at time t with bound b must satisfy `t + b <= start + D`.

        Driven over 1, 3, 5 and 20 calls because the whole point is that the
        count is not known in advance -- Q-C section 4b's sequence has been
        counted as 3 and measured as 5, and 20 is included to show the property
        does not depend on the count being plausible.

        **`granted` is asserted, and without it this test abstains.** A mutation
        that made the first call return `None` would satisfy the loop
        vacuously -- it breaks immediately, asserts nothing, and passes. A
        never-granting budget bounds the deadline perfectly and is useless, so
        the guarantee has to be paired with evidence that work was permitted.
        """
        budget = DispatchBudget(deadline_s=DEADLINE)
        limit = T0 + timedelta(seconds=DEADLINE)
        now = T0
        granted = 0
        for _ in range(calls):
            bounds = budget.bounds_for_next_call(started_at=T0, now=now)
            if bounds is None:
                break
            granted += 1
            assert now + timedelta(seconds=bounds.timeout_s) <= limit
            now += timedelta(seconds=0.4)
        assert granted == calls

    def test_a_sequence_whose_calls_exhaust_the_deadline_stops_beginning_them(self) -> None:
        """Three calls each taking 3.0 s exactly spend the 9.0 s deadline, and
        the fourth is refused. MEASURED as the shape a real sequence lands in:
        it is the refusal, not a timeout, that ends it.
        """
        budget = DispatchBudget(deadline_s=DEADLINE)
        now = T0
        begun = 0
        for _ in range(10):
            if budget.bounds_for_next_call(started_at=T0, now=now) is None:
                break
            begun += 1
            now += timedelta(seconds=3.0)
        assert begun == 3
        assert now == T0 + timedelta(seconds=DEADLINE)

    def test_one_hung_call_consumes_the_whole_deadline(self) -> None:
        """The cost of giving the first call the loosest bound, stated rather
        than discovered: a call that runs to its full bound leaves nothing. The
        budget refuses the next one rather than abandoning the hung one --
        `CLAUDE.md`: "A budget may refuse to BEGIN work. It must never abandon a
        write in flight."
        """
        budget = DispatchBudget(deadline_s=DEADLINE)
        first = budget.bounds_for_next_call(started_at=T0, now=T0)
        assert first is not None
        assert first.timeout_s == DEADLINE

        hung_until = _at(first.timeout_s)
        assert budget.bounds_for_next_call(started_at=T0, now=hung_until) is None
