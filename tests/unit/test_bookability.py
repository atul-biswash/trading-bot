"""The shared bookability predicate: its ladder, and every fact it states.

**THIS IS THE ONLY PLACE THE FULL ORDER IS OBSERVABLE**, which is why the
predicate is tested directly rather than only through the three call sites
(ii)b integrates. ``_bookable_total`` returns a bare ``None`` from all four
refusals and so is order-blind; ``_sell_and_book`` maps a SET of facts onto one
action; and neither of those two can produce ``POSITION_ABSENT`` at all, since
both hold a non-optional ``Position``. Only the driver's three operator
messages ever showed an ordering, and they show it for three facts of the four.

**FOUR OF THE SIX PAIRWISE RELATIONS ARE TESTED HERE. THE OTHER TWO ARE HELD BY
MYPY**, and the split is structural rather than a gap. ``POSITION_ABSENT`` is a
NULL GUARD THAT BINDS THE NAME: ``PARTIAL_FILL`` reads ``position.quantity``
and ``NO_COST_BASIS`` reads ``position.entry_fill_price``, so placing either
ahead of it is a static type error, never a different ordering. MEASURED: of
the 24 orderings of the four facts, exactly EIGHT type-check under this
project's mypy -- precisely those with A before both P and C. ``CLAUDE.md``
names this coverage kind: *"enforcement by Python itself (swapping a null-guard
that also binds the name yields NameError)"*.

So ``A < P`` and ``A < C`` cannot be tested and do not need to be; the four
relations that CAN vary are pinned by ``test_the_ladder_decides_when_two_rungs_fire``,
and between the suite and gate step 3 no relation is unheld. MEASURED: all
seven non-canonical runnable orderings are killed by at least one of its four
items.

**THE TWO INCONSTRUCTIBLE PAIRS ARE DECLARED HERE RATHER THAN DISCOVERED
LATER.** ``A and P`` and ``A and C`` have no test because they have no input:
with no position there is no ``position.quantity`` and no
``position.entry_fill_price`` to be wrong about, so the conjunctions are
UNDEFINED rather than merely false. ``CLAUDE.md`` asks for abstentions to be
declared in advance with cause, and asks for the fourth answer -- *do not write
the test* -- wherever two conditions cannot both hold.

**REASON ASSERTIONS HOLD THEIR OWN LITERALS, DELIBERATELY.** They do NOT read
``bookability``'s reason constants. A test that asserts the code's own constant
against itself passes under every rewording of it -- the mutation moves both
sides of the comparison at once and the pin is blind by construction. The
duplication is the pin. This is ``W6`` (``M5i-015``) taken at its word: *"A
future logger serving two outcomes from one call inherits the identical
exposure with no test to catch it"* -- and ``classify_bookability`` serves FIVE
outcomes from one ``reason`` field.
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

import pytest

from trading_bot.core.enums import PositionSide, ProtectionState
from trading_bot.core.models import Money, Position
from trading_bot.execution.bookability import (
    BookabilityOutcome,
    BookabilityVerdict,
    classify_bookability,
)

#: Run 3's own shape -- the project's first complete trade -- so the fixtures
#: are a size the venue really produced rather than round numbers.
QTY = Decimal("0.02257000")
PARTIAL = Decimal("0.01000000")
TOTAL = Decimal("1786.22691640")
ENTRY_FILL = Decimal("80756.69")
ENTRY_LIMIT = Decimal("80700.00")
BAR = datetime(2026, 8, 15, 11, 0, tzinfo=timezone.utc)
STOP = Decimal("44117.09")


def _position(*, entry_fill_price: Decimal | None = ENTRY_FILL) -> Position:
    """A position sized like run 3's, with or without its cost basis."""
    return Position(
        symbol="BTCUSDT",
        side=PositionSide.LONG,
        quantity=QTY,
        entry_price=ENTRY_LIMIT,
        entry_fill_price=entry_fill_price,
        entry_bar_time=BAR,
        protection=ProtectionState.UNKNOWN,
        order_list_id="tb1-BTCUSDT-1786694400000-0-L",
        last_reconciled_at=None,
        stop_loss=STOP,
    )


def _classify(
    *,
    position: Position | None,
    filled_quantity: Money = QTY,
    filled_quote_quantity: Money | None = TOTAL,
) -> BookabilityVerdict:
    """One call, so a case reads as the three facts it varies."""
    return classify_bookability(
        position=position,
        filled_quantity=filled_quantity,
        filled_quote_quantity=filled_quote_quantity,
    )


# --------------------------------------------------------------------------
# T1 -- one fact true at a time.
# --------------------------------------------------------------------------


class TestOneFactAtATime:
    """Each refusal is reachable on its own, and none of them carries a total.

    **THESE ABSTAIN FROM EVERY ORDERING MUTATION, BY FIXTURE**, and it is
    declared here rather than found afterwards. Exactly one fact is true in
    each case, so no ordering between facts is observable to them -- the
    abstention is a property of the INPUT, not of what the test is named for.
    """

    @pytest.mark.parametrize(
        ("case", "position", "filled", "quote", "expected"),
        [
            (
                "position_absent",
                None,
                QTY,
                TOTAL,
                BookabilityOutcome.POSITION_ABSENT,
            ),
            (
                "no_quote_total",
                _position(),
                QTY,
                None,
                BookabilityOutcome.NO_QUOTE_TOTAL,
            ),
            (
                "partial_fill",
                _position(),
                PARTIAL,
                TOTAL,
                BookabilityOutcome.PARTIAL_FILL,
            ),
            (
                "no_cost_basis",
                _position(entry_fill_price=None),
                QTY,
                TOTAL,
                BookabilityOutcome.NO_COST_BASIS,
            ),
        ],
        ids=lambda value: value if isinstance(value, str) else "",
    )
    def test_each_condition_alone_yields_its_own_outcome(
        self,
        case: str,
        position: Position | None,
        filled: Money,
        quote: Money | None,
        expected: BookabilityOutcome,
    ) -> None:
        """Every fact refuses, and every refusal refuses to carry a figure.

        MUTATION: have a refusal return ``total=filled_quote_quantity``.

        ``total is None`` is the half that bites there. A refusal carrying a
        total would let a caller book a figure the predicate just refused --
        and ``BookabilityVerdict`` documents ``total`` as set on ``BOOKABLE``
        alone, which is a docstring until something checks it.
        """
        verdict = _classify(position=position, filled_quantity=filled, filled_quote_quantity=quote)

        assert verdict.outcome is expected
        assert verdict.total is None, "a refusal must not carry a bookable figure"


# --------------------------------------------------------------------------
# T2 -- two facts true at once. THE LADDER.
# --------------------------------------------------------------------------


class TestTheLadderDecidesWhenTwoFactsHold:
    """``A > Q > P > C``, pinned on inputs where the losing fact is ALSO true.

    **BOTH POLARITIES, AND THE ABSENT HALF IS THE WHOLE TEST.** A reorder does
    not stop a refusal happening -- it makes the OTHER fact answer. So each
    case asserts the winner AND that the loser did not win; asserting merely
    that some refusal occurred passes under every reordering.
    """

    @pytest.mark.parametrize(
        ("case", "position", "filled", "quote", "winner", "loser"),
        [
            (
                "a_beats_q",
                None,
                QTY,
                None,
                BookabilityOutcome.POSITION_ABSENT,
                BookabilityOutcome.NO_QUOTE_TOTAL,
            ),
            (
                "q_beats_p",
                _position(),
                PARTIAL,
                None,
                BookabilityOutcome.NO_QUOTE_TOTAL,
                BookabilityOutcome.PARTIAL_FILL,
            ),
            (
                "q_beats_c",
                _position(entry_fill_price=None),
                QTY,
                None,
                BookabilityOutcome.NO_QUOTE_TOTAL,
                BookabilityOutcome.NO_COST_BASIS,
            ),
            (
                "p_beats_c",
                _position(entry_fill_price=None),
                PARTIAL,
                TOTAL,
                BookabilityOutcome.PARTIAL_FILL,
                BookabilityOutcome.NO_COST_BASIS,
            ),
        ],
        ids=lambda value: value if isinstance(value, str) else "",
    )
    def test_the_ladder_decides_when_two_rungs_fire(
        self,
        case: str,
        position: Position | None,
        filled: Money,
        quote: Money | None,
        winner: BookabilityOutcome,
        loser: BookabilityOutcome,
    ) -> None:
        """Four cases, and together they determine the whole order.

        MUTATION: transpose any two rungs that mypy permits transposing.

        The four relations here plus the two mypy enforces are all six
        relations of a total order on four facts. MEASURED: every one of the
        seven non-canonical orderings that type-checks is killed by at least
        one of these four items.

        **Outcome only, never ``reason``** -- deliberately, so that a reworded
        message and a reordered ladder have DISJOINT failure sets and each
        prediction is exact rather than approximate.
        """
        verdict = _classify(position=position, filled_quantity=filled, filled_quote_quantity=quote)

        assert verdict.outcome is winner
        assert verdict.outcome is not loser, (
            f"{case}: both facts hold and the ladder reported the lower one"
        )


# --------------------------------------------------------------------------
# T3 -- W6. The exact words of each fact.
# --------------------------------------------------------------------------


class TestEachRefusalStatesItsOwnFact:
    """The four reason strings, pinned to the byte, against local literals.

    **THE LITERALS ARE COPIED ON PURPOSE.** Reading ``bookability``'s own
    constants here would move both sides of the comparison under any rewording
    and pin nothing at all.
    """

    @pytest.mark.parametrize(
        ("case", "position", "filled", "quote", "expected"),
        [
            (
                "position_absent",
                None,
                QTY,
                TOTAL,
                "no position is held for this symbol, so there is no cost basis to price "
                "the exit against",
            ),
            (
                "no_quote_total",
                _position(),
                QTY,
                None,
                "the venue reported a fill with no quote total, so the exit cannot be priced",
            ),
            (
                "partial_fill",
                _position(),
                PARTIAL,
                TOTAL,
                "the fill is partial -- 0.01000000 executed against a position of 0.02257000",
            ),
            (
                "no_cost_basis",
                _position(entry_fill_price=None),
                QTY,
                TOTAL,
                "the position has no entry_fill_price, so its cost basis is unknown; the "
                "requested entry_price is not a substitute and would write a permanent "
                "distortion into the ledger",
            ),
        ],
        ids=lambda value: value if isinstance(value, str) else "",
    )
    def test_each_refusal_states_its_own_fact(
        self,
        case: str,
        position: Position | None,
        filled: Money,
        quote: Money | None,
        expected: str,
    ) -> None:
        """One call site serves five outcomes; this is what makes it say five.

        MUTATION: reword any one fact half.

        **AND NO FACT MAY CARRY A CONSEQUENCE** -- ``M5i-068``. The driver's
        partial-fill message ends *"and the position keeps its untrusted
        protection"*, which is TRUE at ``_refuse_booking`` and the exact
        inverse at ``_go_naked``, where protection is cancelled. The equality
        below is what keeps such a clause out: it cannot be appended here
        without failing.
        """
        verdict = _classify(position=position, filled_quantity=filled, filled_quote_quantity=quote)

        assert verdict.reason == expected

    def test_no_fact_half_carries_a_callers_consequence(self) -> None:
        """The clauses that belong to a CALLER, absent from every fact.

        MUTATION: fold a driver consequence into any fact half.

        **`M5i-068`, AND ONE OF THESE CLAUSES IS FALSE AT A REAL CALLER.**
        ``_book_exits`` appends *"the position keeps its untrusted
        protection"*, which is true there -- ``_refuse_booking`` leaves the
        position present and untrusted. The same fact at ``_sell_and_book``
        reaches ``_go_naked``, whose docstring reads *"Protection is cancelled
        and the position is not closed"*. A module carrying that clause would
        assert, from shared code, the opposite of what one of its own callers
        does.

        **ABSENCE IS THE ONLY POLARITY THAT CATCHES AN APPEND.** The
        exact-string assertions above each speak for ONE string, so a clause
        added to a different fact slips past all four; and a substring census
        cannot read the ``not in`` around an assertion. Both halves are why
        this is a separate test rather than more equalities.
        """
        consequences = (
            # `_book_exits`, via `_BOOK_REFUSAL_CONSEQUENCE`.
            "keeps its untrusted protection",
            "closed at the venue with nothing booked",
            # `_go_naked`, at `_sell_and_book`.
            "still open",
            "selling the base",
        )
        verdicts = (
            _classify(position=None),
            _classify(position=_position(), filled_quote_quantity=None),
            _classify(position=_position(), filled_quantity=PARTIAL),
            _classify(position=_position(entry_fill_price=None)),
            _classify(position=_position()),
        )

        for verdict in verdicts:
            for clause in consequences:
                assert clause not in verdict.reason, (
                    f"{verdict.outcome.value} states a CALLER's consequence: {clause!r}"
                )


# --------------------------------------------------------------------------
# T4 / T5 -- the bookable case, and what it carries.
# --------------------------------------------------------------------------


class TestABookableFill:
    """The happy path, and the figure it hands back.

    Without these two, ``BOOKABLE`` is reachable in no test and every mutation
    below abstains from the whole class -- *"a test absent from EVERY
    mutation's failure set is abstaining, not passing."*
    """

    def test_a_complete_priced_fill_against_a_priced_position_is_bookable(self) -> None:
        """All four facts false, so the verdict books.

        MUTATION: return ``total=None`` on the bookable branch.
        """
        verdict = _classify(position=_position())

        assert verdict.outcome is BookabilityOutcome.BOOKABLE
        assert verdict.total == TOTAL

    def test_a_bookable_total_is_the_venues_own_figure_verbatim(self) -> None:
        """IDENTITY, not equality -- the venue's object, never a computation.

        MUTATION: return ``position.quantity * position.entry_fill_price``, or
        any other reconstruction of the total.

        Equality alone would survive a round trip through a unit price, and
        MEASURED that round trip is lossy: run 3's own shape, ``0.02257000``
        against ``35.38691640``, returns a delta of ``-1E-26``, which
        ``_dump_money`` then writes into ``data/state.json`` verbatim.
        ``CLAUDE.md``: a stop booked at its trigger under-reported 137.36 of
        241.15 USDT across three exits. **The booked figure is the venue's or
        there is no booked figure.**
        """
        quote = Decimal("1786.22691640")
        verdict = _classify(position=_position(), filled_quote_quantity=quote)

        assert verdict.total is quote
