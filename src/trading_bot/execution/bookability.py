"""May this fill be booked, and if not, WHICH fact refuses it?

**ONE PREDICATE, WHERE THERE WERE THREE.** ``_bookable_total``,
``_sell_and_book``'s tail and ``reconciliation_driver``'s row ladder each
decided bookability independently, asking overlapping subsets of the same four
questions in three different orders. That divergence is not hypothetical: it
already cost ``M5i-001``, where one of the three was missing the cost-basis
question entirely and booked a fill it could not price. Option 3 half (ii) is
the mandate to retire the copies; this module is the thing they collapse into.

**IT SHIPS WITH ZERO CALLERS IN** ``src/``. That is deliberate and it is
finding GG's shape -- *"a port method sat with no production caller across two
milestones, accumulating the P2 gap that made deleting it a prerequisite rather
than a tidy-up."* The bound is that (ii)b integrates all three call sites as
the NEXT commit. **That bound is a plan, and a plan is not a mechanism.** If
(ii)b is deferred this is dead ``src/`` code of exactly GG's shape, and the
honest reading of the census at four rather than three is that the debt has
been MOVED and counted, not paid.

THE FOUR FACTS
--------------

Named rather than numbered, because the three call sites numbered their rows
differently and the numbers were never the same fact twice.

* **A** -- ``POSITION_ABSENT``. No position is held, so there is no cost basis
  in memory at all. After a restart there is no ``Position`` and
  ``PendingCloseRecord`` carries none, so the figure is UNRECONSTRUCTABLE
  rather than merely unknown.
* **Q** -- ``NO_QUOTE_TOTAL``. The venue reported a fill and gave no
  ``cummulativeQuoteQty`` for it -- or gave a negative one, which the venue
  documents as unavailable and the adapter's ``to_order`` reads as absent.
  There is no fallback: deriving a total by
  multiplying an average price reintroduces the quotient error the exchange's
  own accounting does not have. **The booked figure is the venue's or there is
  no booked figure.**
* **P** -- ``PARTIAL_FILL``. ``close_position`` deletes the whole entry and
  credits one total; there is no partial-close path and no way to express
  "0.3 of 0.5 sold". Booking a partial would delete a position whose base is
  still at the venue.
* **C** -- ``NO_COST_BASIS``. The position is present and carries no
  ``entry_fill_price``, which is a SEPARATE fact from being absent: a
  ``Position`` is constructed with ``entry_fill_price=None`` whenever the
  working-leg query failed or the FOK expired.

THE ORDER IS ``A > Q > P > C``, AND ONLY TWO OF ITS SIX RELATIONS ARE A CHOICE
-----------------------------------------------------------------------------

**A IS A NULL GUARD THAT BINDS THE NAME, NOT A PEER RUNG.** P reads
``position.quantity`` and C reads ``position.entry_fill_price``, so either one
placed ahead of A is a STATIC TYPE ERROR rather than a different ordering.
MEASURED: of the 24 orderings of the four facts, exactly **8** type-check under
this project's mypy -- precisely those with A before both P and C. So the
relations ``A < P`` and ``A < C`` are enforced by gate step 3 and cannot be
tested; ``CLAUDE.md`` names this coverage kind, *"enforcement by Python itself
(swapping a null-guard that also binds the name yields NameError)"*. The four
remaining relations are held by assertions in ``tests/unit/test_bookability.py``.
Between the two, no relation is unheld.

**A BEFORE Q is the one genuinely free choice, and it is ruled deliberately.**
With no position in memory the quote total is unusable EVEN WHEN PRESENT, so
reporting Q ahead of A puts a repairable-sounding obstacle -- ``_sell_and_book``
literally holds a ``_requery_sell_total`` -- in front of an unrepairable one.
That is the cause-before-consequence principle ``CLAUDE.md`` already applies to
the staleness guard: *"staleness names the CAUSE where committed-risk-unknown
names the CONSEQUENCE."* Ruled by the project owner.

**Q > P > C is MEASURED, not chosen.** It is the order
``reconciliation_driver``'s ladder already runs, and that ladder's three
operator messages are the only place the order was ever observable. The five
pins written at ``61919ce`` exist precisely so (ii) could not silently reorder
it; this module adopts what they pinned.

THE REASON IS A FACT. THE CONSEQUENCE BELONGS TO THE CALLER
----------------------------------------------------------

Every ``reason`` below states WHAT IS TRUE OF THE FILL and stops there. What
follows from it differs per caller and **must not** be written here --
``M5i-068``, MEASURED. The driver's partial-fill message ends *"and the position
keeps its untrusted protection"*, which is true at ``_refuse_booking``, whose
docstring says *"every refusal here leaves the position PRESENT and untrusted"*.
The same input at ``_sell_and_book`` reaches ``_go_naked``, whose docstring
reads **"Protection is cancelled and the position is not closed"** -- the exact
inverse. A shared module carrying that clause would assert, from shared code,
the opposite of what one of its own callers does.

So a caller appends its own consequence. ``_bookable_total`` appends nothing
because it discards the reason entirely.

**EVERY FACT HALF IS PINNED BY AN EXACT-STRING ASSERTION**, which is ``W6``
(``M5i-015``) taken at its word: *"A future logger serving two outcomes from one
call inherits the identical exposure with no test to catch it."* This function
serves FIVE outcomes from one ``reason`` field -- one degree worse than
``_log_close_resolved``, the only site in ``src/`` that has ever disagreed with
itself. Q's and C's wording is the driver's current text VERBATIM and P's is
that text minus its trailing consequence, so (ii)b is a substitution rather than
a rewrite and every reason assertion written at ``61919ce`` stays green
untouched.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from trading_bot.core.models import Money, Position

__all__ = ["BookabilityOutcome", "BookabilityVerdict", "classify_bookability"]


class BookabilityOutcome(str, Enum):
    """Whether this fill may be booked, and which fact refuses it.

    **NO ``UNCLASSIFIED`` MEMBER**, matching the ruling already locked for
    ``RefusalStage``: *"every member is reachable, and an unreachable one
    invites defensive branching and becomes a lazy default for the next refusal
    added."* Each of the four refusals is reachable from at least one of the
    three call sites (ii)b integrates.
    """

    #: The fill is complete, priced by the venue, and the position holding its
    #: cost basis is in memory. :attr:`BookabilityVerdict.total` carries the
    #: figure and is set on this outcome alone.
    BOOKABLE = "bookable"
    #: No position is held for this symbol. **A**, and it is first.
    POSITION_ABSENT = "position_absent"
    #: The venue reported a fill with no quote total. **Q**.
    NO_QUOTE_TOTAL = "no_quote_total"
    #: Less executed than the position holds. **P**.
    PARTIAL_FILL = "partial_fill"
    #: The position is present and carries no ``entry_fill_price``. **C**.
    NO_COST_BASIS = "no_cost_basis"


@dataclass(frozen=True, slots=True)
class BookabilityVerdict:
    """The outcome, the fact behind it, and -- only when bookable -- the figure.

    A verdict is a **value carrying its reason**, the shape ``PlacementVerdict``
    and ``ProtectionAssessment`` already use in this package: *"'the stop rests
    one tick low' and 'the stop is not there at all' are different facts that
    would otherwise arrive as the same word."*

    **WHY :attr:`total` IS CARRIED, AND IT IS NOT A TYPING ARGUMENT.**
    ``M5i-073`` claimed it removes ``_bookable_total``'s last narrowing.
    MEASURED under this project's ``--strict`` mypy with a control that fired:
    it does not. A caller that re-reads ``order.filled_quote_quantity`` itself
    type-checks CLEAN, because ``_bookable_total`` returns ``Money | None`` and
    that field is already ``Money | None``. The only narrowing mypy demands
    there is ``order is None``, which is not one of the four facts and stays at
    the call site.

    What carrying the total actually buys is **single-sourcing**: without it,
    *"the predicate said BOOKABLE"* and *"this is the figure to book"* become
    two facts held in two places with nothing binding them. The alternative
    type-checks and is worse code, which is the case where mypy is not the
    instrument. ``M5i-075``.
    """

    outcome: BookabilityOutcome
    reason: str
    #: The venue's own quote total, passed through unchanged. ``None`` on every
    #: refusal, and never derived -- see the module docstring's **Q**.
    total: Money | None = None


#: The fact halves, as module constants to keep the long ones out of the
#: ladder's control flow.
#:
#: **A TEST MUST NOT ASSERT AGAINST THESE**, and the temptation to is why the
#: warning sits here rather than only in the test module. An assertion reading
#: the constant compares the code against itself: a rewording moves BOTH sides
#: at once and the pin is blind by construction, passing under the exact
#: mutation it was written for. ``tests/unit/test_bookability.py`` holds its own
#: literals, and that duplication IS the pin.
REASON_POSITION_ABSENT = (
    "no position is held for this symbol, so there is no cost basis to price the exit against"
)
REASON_NO_QUOTE_TOTAL = (
    "the venue reported a fill with no quote total, so the exit cannot be priced"
)
REASON_NO_COST_BASIS = (
    "the position has no entry_fill_price, so its cost basis is unknown; the requested "
    "entry_price is not a substitute and would write a permanent distortion into the ledger"
)


def classify_bookability(
    *,
    position: Position | None,
    filled_quantity: Money,
    filled_quote_quantity: Money | None,
) -> BookabilityVerdict:
    """Classify one exit fill against the position it claims to close.

    **PURE.** No clock, no portfolio, no venue. It takes the position rather
    than a symbol because fetching one would hand a pure predicate a
    ``Portfolio``, and it takes the position WHOLE rather than destructured
    because ``quantity`` and ``entry_fill_price`` must come from the SAME
    position -- passing them separately creates a pair the type no longer binds.

    **THERE IS NO ``order`` PARAMETER, AND THAT IS THE POINT** -- ``M5i-052``.
    ``_bookable_total`` opens ``if order is None or ...``, and that disjunct is
    RUNTIME-UNREACHABLE: its only call site is guarded by
    ``filled = order is not None and order.filled_quantity > 0``. Rather than
    carry a fifth outcome no caller can reach, the signature makes the question
    unaskable: ``filled_quantity`` is ``Money``, non-optional, which both
    ``Order`` (defaulting to zero) and ``ExitFill`` (*"Never None"*) satisfy.
    A caller cannot ask this about an order it does not have.

    Taking ``Order`` was rejected for a second reason as well: the reconciler
    holds an ``ExitFill``, not an ``Order``, so the parameter could not have
    been satisfied at one of the three sites at all.

    :param position: The position this fill claims to close, or ``None`` when
        none is held. Reachable as ``None`` only from ``_bookable_total``; the
        other two sites hold a non-optional ``Position`` by construction.
    :param filled_quantity: Base quantity the venue reports executed.
    :param filled_quote_quantity: The venue's own quote total, or ``None`` when
        it reported none. Never a figure we computed.
    """
    if position is None:
        return BookabilityVerdict(BookabilityOutcome.POSITION_ABSENT, REASON_POSITION_ABSENT)
    if filled_quote_quantity is None:
        return BookabilityVerdict(BookabilityOutcome.NO_QUOTE_TOTAL, REASON_NO_QUOTE_TOTAL)
    if filled_quantity != position.quantity:
        # Interpolated rather than constant, because the two quantities ARE the
        # fact -- "partial" without them tells an operator nothing actionable.
        # The driver's current message carries both and its pin asserts on the
        # word alone, so (ii)b keeps that assertion green.
        return BookabilityVerdict(
            BookabilityOutcome.PARTIAL_FILL,
            f"the fill is partial -- {filled_quantity} executed against a position "
            f"of {position.quantity}",
        )
    if position.entry_fill_price is None:
        return BookabilityVerdict(BookabilityOutcome.NO_COST_BASIS, REASON_NO_COST_BASIS)
    # THE TOTAL PASSES STRAIGHT THROUGH -- no division into a unit price and no
    # re-multiplication. MEASURED, that round trip is lossy: run 3's own shape,
    # 0.02257000 against 35.38691640, returns a delta of -1E-26.
    return BookabilityVerdict(
        BookabilityOutcome.BOOKABLE,
        "the fill is complete, priced by the venue, and the position carries its cost basis",
        total=filled_quote_quantity,
    )
