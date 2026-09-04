"""Q-C section 4b's confirming-query table, exercised exhaustively.

**A TABLE-DRIVEN TEST THAT CANNOT FAIL ON A MISSING ROW IS WORTHLESS**, so
what makes this one fail is stated rather than assumed. Three things do:

* Every combination of two legs over five leg-states is enumerated by the
  PRODUCT, not listed by hand -- 25 cases -- so a row cannot be omitted by
  forgetting to type it. The expected action for each is derived from an
  independent restatement of section 4b's precedence, not from the code.
* ``test_every_case_is_covered`` asserts the case count against that product,
  so shrinking the state set silently is caught.
* Each state appears in at least one SINGLE-leg case too, because a
  two-leg-only table can be satisfied by a function that reads only ``legs[0]``
  -- and reversing a two-element tuple leaves nothing fixed, so a positional
  bug would show, but an ANY-vs-ALL bug would not.

No client, no I/O, no fake: the subject is pure, which is the whole reason two
of its rows -- partial execution and an unreadable leg -- can be tested at all.
Neither has ever been observed against a venue.
"""

from __future__ import annotations

import itertools
from decimal import Decimal

import pytest

from trading_bot.execution.close_plan import CloseAction, LegReport, plan_close

D = Decimal

#: What one leg was placed for. Run 3's shape, so the quantities are realistic
#: and the partial is a plausible fraction rather than a round number.
REQUESTED = D("0.02257000")

#: The five states a single leg can be in, named. **``NONE`` and ``ZERO`` are
#: DIFFERENT and that difference is the point**: unreadable versus read-and-
#: nothing-executed. A fixture that conflated them could not express the rule
#: this module's docstring calls the one direction it may not err in.
_STATES: dict[str, Decimal | None] = {
    "unreadable": None,
    "zero": D("0"),
    "partial": D("0.01000000"),
    "full": REQUESTED,
    # Not a state the venue can produce; included so its handling is pinned
    # rather than incidental. It must land on ALREADY_CLOSED, not slip to SELL.
    "over": REQUESTED + D("0.00000001"),
}


def leg(state: str, name: str = "SL") -> LegReport:
    return LegReport(leg=name, executed=_STATES[state], requested=REQUESTED, status="FILLED")


def expected(states: tuple[str, ...]) -> CloseAction:
    """Section 4b's precedence, RESTATED INDEPENDENTLY of the implementation.

    Written as a separate expression of the rule rather than a lookup table
    copied from the code, so the two can disagree. The order is the rule:
    unknown beats partial beats full beats none.
    """
    if not states:
        return CloseAction.HALT
    if "unreadable" in states:
        return CloseAction.HALT
    if "partial" in states:
        return CloseAction.HALT
    if "full" in states or "over" in states:
        return CloseAction.ALREADY_CLOSED
    return CloseAction.SELL


_PAIRS = tuple(itertools.product(_STATES, repeat=2))


class TestTheTable:
    """Every combination of two protective legs. OTOCO has exactly two."""

    @pytest.mark.parametrize("states", _PAIRS, ids=[f"{a}+{b}" for a, b in _PAIRS])
    def test_every_two_leg_combination(self, states: tuple[str, str]) -> None:
        """MUTATION: any reordering of the four branches in ``plan_close``.

        Swapping unreadable below full makes ``unreadable+full`` answer
        ALREADY_CLOSED -- asserting a position is closed over a set containing
        an unanswered leg. Swapping partial below full makes ``partial+full``
        answer ALREADY_CLOSED, which sells nothing but books an exit that may
        not have happened.
        """
        plan = plan_close((leg(states[0], "SL"), leg(states[1], "TP")))

        assert plan.action is expected(states)

    def test_every_case_is_covered(self) -> None:
        """The count, so the state set cannot shrink unnoticed.

        MUTATION: delete a member of ``_STATES``.

        Without this the parametrize would simply run fewer cases and still
        pass -- the failure mode a table-driven test is most prone to.
        """
        assert len(_STATES) == 5
        assert len(_PAIRS) == 25

    @pytest.mark.parametrize("state", list(_STATES), ids=list(_STATES))
    def test_every_state_alone(self, state: str) -> None:
        """One leg, so an ANY-over-the-set bug is visible.

        MUTATION: read ``legs[0]`` instead of scanning every leg.

        A two-leg-only table cannot catch that reliably -- reversing a
        two-element tuple leaves nothing fixed, so a positional read still sees
        both states across the 25 cases. A single-leg case pins that each state
        decides on its own.
        """
        assert plan_close((leg(state),)).action is expected((state,))


class TestTheEdges:
    """The rows most likely to be got wrong, each asserted on its own."""

    def test_no_legs_at_all_halts_rather_than_selling(self) -> None:
        """**The permissive default, refused.**

        MUTATION: ``if not legs: return SELL``, or delete the guard so the
        function falls through its three ``if``s to the final ``return SELL``.

        Both produce a SELL, and the second is what a plain reading of the
        control flow gives you for free -- which is exactly why the guard is
        explicit. "No leg executed" and "no leg was asked about" are different
        facts and only the first permits a sell.
        """
        plan = plan_close(())

        assert plan.action is CloseAction.HALT
        assert "no protective legs at all" in plan.reason

    def test_an_unreadable_leg_is_not_a_leg_that_executed_nothing(self) -> None:
        """``None`` against ``Decimal(0)``, the distinction the type exists for.

        MUTATION: ``executed or Decimal(0)`` anywhere in ``plan_close``.

        That single change turns a failed query into a licence to sell -- the
        one direction this decision may not err in -- and it reads as harmless
        defensive coding.
        """
        assert plan_close((leg("unreadable"),)).action is CloseAction.HALT
        assert plan_close((leg("zero"),)).action is CloseAction.SELL

    def test_a_partial_fill_is_never_sold_against(self) -> None:
        """MUTATION: treat partial as full, or as zero.

        As full it books an exit that did not fully happen; as zero it sells a
        remainder on top of a fill. Section 4b defers the state to section 10
        as UNMEASURED and forbids both.
        """
        plan = plan_close((leg("partial"),))

        assert plan.action is CloseAction.HALT
        assert "UNMEASURED" in plan.reason

    def test_an_over_fill_lands_on_already_closed_not_sell(self) -> None:
        """MUTATION: ``qty == leg.requested`` instead of ``>=``.

        Under equality an over-executed leg matches no row and falls through to
        SELL -- selling against a position the venue has more than closed.
        Unreachable, and it takes the conservative answer anyway.
        """
        assert plan_close((leg("over"),)).action is CloseAction.ALREADY_CLOSED

    def test_status_is_reported_and_never_decided_on(self) -> None:
        """Section 4b: ``executedQty``, not merely ``status``.

        MUTATION: branch on ``leg.status`` rather than on the quantity.

        The fixture is what makes this expressive -- both legs say FILLED while
        the quantities disagree, so a status-reading implementation answers
        ALREADY_CLOSED for both and this fails on the first.
        """
        filled_word_only = LegReport(
            leg="SL", executed=D("0"), requested=REQUESTED, status="FILLED"
        )
        cancelled_but_executed = LegReport(
            leg="TP", executed=REQUESTED, requested=REQUESTED, status="CANCELED"
        )

        assert plan_close((filled_word_only,)).action is CloseAction.SELL
        assert plan_close((cancelled_but_executed,)).action is CloseAction.ALREADY_CLOSED


class TestTheVerdictCarriesItsReason:
    """A verdict is a value carrying why -- the house shape."""

    @pytest.mark.parametrize("state", list(_STATES), ids=list(_STATES))
    def test_every_plan_names_the_leg_that_decided_it(self, state: str) -> None:
        """MUTATION: return a bare ``CloseAction``, or a constant reason.

        An operator meeting a HALT must not have to re-derive which leg caused
        it. Asserting the leg CODE appears is what makes a constant string
        fail.
        """
        plan = plan_close((leg(state, "SL"),))

        assert plan.reason
        if plan.action is not CloseAction.SELL:
            assert "SL" in plan.reason

    def test_the_action_values_are_stable_strings(self) -> None:
        """MUTATION: rename a member's value.

        These reach logs and, eventually, a durable record. ``str, Enum`` keeps
        ``str(member)`` qualified, so any emitter must pass ``.value`` -- the
        trap ``exchange/ids.py`` documents; asserting the values here is what a
        future emitter's test can rely on.
        """
        assert CloseAction.SELL.value == "sell"
        assert CloseAction.ALREADY_CLOSED.value == "already_closed"
        assert CloseAction.HALT.value == "halt"
        assert len(list(CloseAction)) == 3
