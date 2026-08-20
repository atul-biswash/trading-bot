"""Tests for the pure placement-shape mapper.

No I/O, no clock, no exchange client: every case is an ``EntryIntent`` and two
seeds in, one request out.

**The fixture discriminates ``reference_price`` from ``entry_limit`` on
purpose** -- ``100.00`` against ``100.10``. A fixture where the two agreed could
not express a mapper that priced from the bar close instead of the marketable
limit, and that substitution is exactly the one Q-C section 4 says makes
realised risk exceed configured risk. Settled by choosing the fixture, and
MEASURED: under the substitution the OTOCO request still constructs, so the
defect arrives as a wrong price rather than as a refusal.

**Branch four is the only branch with no validator behind it.**
``OtocoOrderListRequest`` and ``OtoOrderListRequest`` each carry a
``model_validator`` enforcing ``stop_price < entry_limit < take_profit`` and a
timezone-aware seed; ``OrderRequest`` carries none at all. So on the two list
shapes these tests are a second line behind the domain, and on the unprotected
shape they are the only line.
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

import pytest
from pydantic import ValidationError

from trading_bot.core.assessment import EntryIntent
from trading_bot.core.enums import OrderSide, OrderType, PositionSide, TimeInForce
from trading_bot.core.models import (
    OrderRequest,
    OtocoOrderListRequest,
    OtoOrderListRequest,
    ProtectiveLevels,
)
from trading_bot.exchange.ids import OrderListLeg, client_order_id
from trading_bot.execution.placement import build_placement

D = Decimal

SYMBOL = "BTCUSDT"
BAR = datetime(2026, 8, 20, 12, 0, tzinfo=timezone.utc)
QTY = D("1.5")

# Deliberately unequal -- see the module docstring.
REFERENCE = D("100.00")
ENTRY_LIMIT = D("100.10")

STOP = D("98.00")
TARGET = D("104.00")


def _levels(*, stop: D | None, target: D | None) -> ProtectiveLevels:
    """Requested levels, priced at ``entry_limit`` as ``EntryIntent`` requires.

    ``stop_distance`` is derived rather than passed, because ``ProtectiveLevels``
    validates it against ``|entry - stop|`` and a fixture that got it wrong would
    fail for a reason unrelated to placement.
    """
    return ProtectiveLevels(
        symbol=SYMBOL,
        side=PositionSide.LONG,
        entry_price=ENTRY_LIMIT,
        stop_loss=stop,
        take_profit=target,
        stop_distance=(ENTRY_LIMIT - stop) if stop is not None else None,
        basis="fixture",
    )


def _intent(*, stop: D | None, target: D | None) -> EntryIntent:
    """An approved entry intent carrying the requested levels for one branch."""
    return EntryIntent(
        symbol=SYMBOL,
        side=OrderSide.BUY,
        quantity=QTY,
        reference_price=REFERENCE,
        entry_limit=ENTRY_LIMIT,
        levels=_levels(stop=stop, target=target),
    )


#: The three branches that return a request, by the levels that select them.
_CONSTRUCTING = {
    "otoco": (STOP, TARGET, OtocoOrderListRequest),
    "oto": (STOP, None, OtoOrderListRequest),
    "unprotected": (None, None, OrderRequest),
}


class TestTheFourWayBranch:
    """Q-C section 2's table, one test per row. Section 2 calls the arity branch
    irreducible: ``PERCENT_PRICE_BY_SIDE`` refuses a whole list at submission, so
    a never-filling dummy leg cannot force one shape."""

    def test_both_levels_map_to_an_otoco_request(self) -> None:
        """Routing only. The field values are pinned by the tests below, so this
        one deliberately asserts nothing but which shape was selected."""
        result = build_placement(_intent(stop=STOP, target=TARGET), entry_bar_time=BAR)
        assert type(result) is OtocoOrderListRequest

    def test_stop_alone_maps_to_an_oto_request(self) -> None:
        """Routing only, as above. The two list shapes are separate TYPES rather
        than one type with an optional target, because they dispatch to different
        endpoints -- so selecting the shape is selecting the endpoint."""
        result = build_placement(_intent(stop=STOP, target=None), entry_bar_time=BAR)
        assert type(result) is OtoOrderListRequest

    def test_neither_level_maps_to_a_fok_limit_order(self) -> None:
        """The unprotected branch, asserted in full because nothing else checks
        it: ``OrderRequest`` carries no ``model_validator``, so every field here
        is unguarded outside this test.

        ``FOK`` matters most. The entry mechanic is a property of the entry, not
        of the protection around it -- a ``GTC`` limit on the unprotected branch
        would rest at the venue with nothing watching it, which is the one place
        a divergent mechanic would be least visible.
        """
        result = build_placement(_intent(stop=None, target=None), entry_bar_time=BAR)
        assert type(result) is OrderRequest
        assert result.type is OrderType.LIMIT
        assert result.time_in_force is TimeInForce.FOK
        assert result.side is OrderSide.BUY
        assert result.price == ENTRY_LIMIT
        assert result.stop_price is None
        assert result.quantity == QTY

    def test_take_profit_without_a_stop_is_unreachable_and_says_so(self) -> None:
        """The fourth row raises rather than falling through to the unprotected
        branch. A fall-through would place a bare entry for an operator who asked
        for a target -- unprotected, and silently.

        The message names ``_check_protective_coverage`` because reaching this
        branch means that validator was bypassed or has regressed, and the reader
        needs to know where to look rather than that a shape was unsupported.
        """
        with pytest.raises(ValueError, match="_check_protective_coverage"):
            build_placement(_intent(stop=None, target=TARGET), entry_bar_time=BAR)


class TestTheSideIsRead:
    """``EntryIntent`` already refuses a non-``BUY`` side in its own validator.
    This layer refuses it again, and the duplication is deliberate: MEASURED,
    ``model_copy(update=...)`` and ``model_construct`` both bypass that validator
    and yield a ``SELL`` entry intent -- and ``model_copy(update=...)`` is this
    tree's normal idiom for returning a corrected copy, with four call sites in
    ``src/`` today. An intent arriving here has not necessarily passed its own
    validator."""

    @pytest.mark.parametrize("branch", list(_CONSTRUCTING), ids=list(_CONSTRUCTING))
    def test_a_buy_intent_maps_normally_on_every_branch(self, branch: str) -> None:
        """The refusal must not cost the ordinary path. Without this, a guard
        inverted to refuse ``BUY`` would fail only the negative test."""
        stop, target, expected = _CONSTRUCTING[branch]
        result = build_placement(_intent(stop=stop, target=target), entry_bar_time=BAR)
        assert type(result) is expected

    @pytest.mark.parametrize("branch", list(_CONSTRUCTING), ids=list(_CONSTRUCTING))
    def test_a_non_buy_intent_is_refused_on_every_branch(self, branch: str) -> None:
        """Every branch, not just the first. Q-C section 3 fixes
        ``workingSide=BUY`` and ``pendingSide=SELL``, so there is no short shape
        to map onto -- but a mapper that ignored the field it was handed would
        turn a short intent into a long position, and it would do so on whichever
        branch the levels happened to select.

        The intent is built through ``model_copy(update=...)`` because that is
        the only route that produces one: ordinary construction and assignment
        are both refused (MEASURED).
        """
        stop, target, _ = _CONSTRUCTING[branch]
        short = _intent(stop=stop, target=target).model_copy(update={"side": OrderSide.SELL})
        assert short.side is OrderSide.SELL  # the bypass worked; the case is real

        with pytest.raises(ValueError, match="Q-C section 3"):
            build_placement(short, entry_bar_time=BAR)

    def test_the_refusal_precedes_the_unreachable_take_profit_branch(self) -> None:
        """Ordering, on an input that satisfies both refusals. The side check is
        about what we would send; the take-profit check is about a validator
        upstream having failed. A non-``BUY`` intent is the more fundamental
        wrongness and must be what the operator is told."""
        short = _intent(stop=None, target=TARGET).model_copy(update={"side": OrderSide.SELL})
        with pytest.raises(ValueError, match="Q-C section 3"):
            build_placement(short, entry_bar_time=BAR)


class TestWhatEachFieldIsTakenFrom:
    """The mapper copies; it does not compute. These pin which source each field
    is copied from."""

    @pytest.mark.parametrize("branch", list(_CONSTRUCTING), ids=list(_CONSTRUCTING))
    def test_every_price_comes_from_entry_limit_not_reference_price(self, branch: str) -> None:
        """Q-C section 4: ``entry_limit`` is the reference for both protective
        levels and for sizing. Pricing the working leg from the bar close instead
        would let a fill at ``entry_limit`` produce a realised entry-to-stop
        distance larger than the one sizing used -- realised risk quietly
        exceeding configured risk.

        The fixture's two prices differ, so the substitution is expressible here;
        MEASURED, it also still constructs, so it would arrive as a wrong price
        rather than as a refusal.
        """
        stop, target, _ = _CONSTRUCTING[branch]
        result = build_placement(_intent(stop=stop, target=target), entry_bar_time=BAR)
        price = result.price if isinstance(result, OrderRequest) else result.entry_limit
        assert price == ENTRY_LIMIT
        assert price != REFERENCE

    def test_the_stop_and_target_are_carried_by_name_not_by_position(self) -> None:
        """Asserted separately rather than as a tuple, so a swap is visible as a
        wrong value on a named field.

        Note what this does NOT pin, because the answer is enforcement rather
        than a test: ``OtocoOrderListRequest`` validates ``stop_price <
        entry_limit < take_profit``, so a swapped mapper cannot construct one at
        all. MEASURED: under a swap mutation this test reports a
        ``ValidationError``, not a mislabelled leg. That is stronger coverage --
        enforcement rather than assertion -- but it means this test proves it
        reaches branch one, not that it would catch a mislabelling, and no test
        here tries to assert a swapped request's contents.
        """
        result = build_placement(_intent(stop=STOP, target=TARGET), entry_bar_time=BAR)
        assert isinstance(result, OtocoOrderListRequest)
        assert result.stop_price == STOP
        assert result.take_profit == TARGET

    def test_the_id_seed_is_the_caller_supplied_bar_time(self) -> None:
        """The seed is the argument, never ``opened_at`` and never a clock. It is
        a parameter precisely because ``EntryIntent`` does not carry it, and the
        restart-stability of every derived client order ID rests on it."""
        other = datetime(2026, 1, 2, 3, 4, tzinfo=timezone.utc)
        for bar in (BAR, other):
            result = build_placement(_intent(stop=STOP, target=TARGET), entry_bar_time=bar)
            assert isinstance(result, OtocoOrderListRequest)
            assert result.entry_bar_time == bar

    def test_a_naive_bar_time_is_refused_on_every_branch(self) -> None:
        """All four branches refuse it, by two different mechanisms: the request
        types' own validator on the list shapes, ``exchange/ids.py`` on the
        unprotected one. Pinned together because the outcome is what matters and
        the messages differ.

        A naive value would be read as local time and shift the millisecond
        segment by the host's offset, so the same bar would derive a different ID
        on a different machine -- and the recovery path's premise is that it does
        not.

        **DECLARED ABSTENTION: this is the one test in this module that appears
        in no mutation's failure set** -- measured across seven, including one
        that inverts the side guard and fails 22 of the other 23. It abstains
        because no mutation targets timezone handling, and because it asserts
        only that *a* refusal happened: it cannot distinguish which of the two
        mechanisms produced it, so a mutation disabling one would be masked by
        the other. That is deliberate -- the outcome is what matters and the
        messages differ -- but it means this test documents a property rather
        than guarding a line, and a future mutation survey should not read its
        silence as coverage.
        """
        naive = datetime(2026, 8, 20, 12, 0)
        for stop, target, _ in _CONSTRUCTING.values():
            with pytest.raises((ValueError, ValidationError)):
                build_placement(_intent(stop=stop, target=target), entry_bar_time=naive)

    def test_generation_defaults_to_zero_and_is_carried(self) -> None:
        """Generation 0 is the derivable one -- pure computation from
        ``(symbol, entry_bar_time)``, which is what the timed-out-write recovery
        queries. A default of anything else would make a first placement
        unrecoverable without persistence."""
        default = build_placement(_intent(stop=STOP, target=TARGET), entry_bar_time=BAR)
        assert isinstance(default, OtocoOrderListRequest)
        assert default.generation == 0

        raised = build_placement(
            _intent(stop=STOP, target=TARGET), entry_bar_time=BAR, generation=3
        )
        assert isinstance(raised, OtocoOrderListRequest)
        assert raised.generation == 3

    @pytest.mark.parametrize("branch", list(_CONSTRUCTING), ids=list(_CONSTRUCTING))
    def test_quantity_is_carried_exactly_and_not_recomputed(self, branch: str) -> None:
        """Identity, not equality, and the difference is the point: MEASURED,
        pydantic preserves the ``Decimal`` object through validation, so ``is``
        holds for a value that was copied and fails for one that was computed.
        Any arithmetic introduced here -- a rounding, a filter application --
        breaks this while an equality assertion might not.

        Filters are applied in sizing and again at dispatch; this layer is not
        one of the places that may move a quantity.
        """
        stop, target, _ = _CONSTRUCTING[branch]
        intent = _intent(stop=stop, target=target)
        result = build_placement(intent, entry_bar_time=BAR)
        assert result.quantity is intent.quantity


class TestTheIdAsymmetry:
    """Branches one and two carry an identity SEED; branch four carries a
    finished ID. A list has four derivable IDs and a list-level one; a single
    order has exactly one and no list-level ID at all, so there is no family to
    derive and nothing for the mapper layer to generate later."""

    def test_the_unprotected_branch_carries_a_working_leg_client_order_id(self) -> None:
        """Generated here, and generated as the WORKING leg -- the same code the
        list shapes' parameter mappers use for their working leg, so a recovery
        path querying "the ID we would have sent" finds one form, not two."""
        result = build_placement(_intent(stop=None, target=None), entry_bar_time=BAR)
        assert isinstance(result, OrderRequest)
        assert result.client_order_id == client_order_id(
            SYMBOL, BAR, OrderListLeg.WORKING, generation=0
        )

    def test_the_list_shapes_carry_seeds_and_no_identifiers(self) -> None:
        """The complement, asserted rather than left implicit: holding the ID
        strings in the domain would be a second source of truth for something
        Q-C section 6 guarantees derivable. Proved by the absence of the field
        rather than by its value."""
        result = build_placement(_intent(stop=STOP, target=TARGET), entry_bar_time=BAR)
        assert not hasattr(result, "client_order_id")
        assert result.entry_bar_time == BAR
        assert result.generation == 0
