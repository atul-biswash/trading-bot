"""Tests for the pure protection classifier.

No I/O and no ``Position``: the classifier takes requested levels and a compare
set and returns a frozen verdict, so every case here is built from those two.

The trigger prices deliberately carry the WIRE's padding -- the venue returns
``"40917.83"`` as ``"40917.83000000"`` -- because comparing them as strings is
the specific mistake Q-C section 7 warns manufactures divergence every cycle,
and a fixture using matched reprs could not express it.
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

import pytest

from trading_bot.core.enums import OrderSide, OrderStatus, OrderType, ProtectionState
from trading_bot.core.models import Order
from trading_bot.exchange.ids import ClientOrderIdParts, OrderListLeg, client_order_id
from trading_bot.execution.reconciliation import ProtectionAssessment, classify_protection

SYMBOL = "BTCUSDT"
BAR = datetime(2026, 8, 14, 12, 0, tzinfo=timezone.utc)
GEN = 0
QTY = Decimal("0.00100000")
LIST_ID = "91590"

# Requested unpadded, as `risk/rules.py` produces them after tick rounding.
STOP = Decimal("44117.09")
TARGET = Decimal("50419.53")


def _leg(
    leg: OrderListLeg,
    *,
    stop_price: str | None,
    status: OrderStatus = OrderStatus.NEW,
    quantity: Decimal = QTY,
    filled: Decimal = Decimal(0),
    list_id: str | None = LIST_ID,
    bar: datetime = BAR,
    generation: int = GEN,
    symbol: str = SYMBOL,
) -> tuple[ClientOrderIdParts, Order]:
    """One entry of the compare set, as `get_own_open_orders` returns it."""
    parts = ClientOrderIdParts(symbol=symbol, entry_bar_time=bar, generation=generation, leg=leg)
    order = Order(
        order_id="1",
        symbol=symbol,
        side=OrderSide.SELL,
        type=OrderType.STOP_LOSS if leg is OrderListLeg.STOP_LOSS else OrderType.TAKE_PROFIT,
        status=status,
        quantity=quantity,
        filled_quantity=filled,
        stop_price=Decimal(stop_price) if stop_price is not None else None,
        order_list_id=list_id,
        client_order_id=client_order_id(symbol, bar, leg, generation=generation),
    )
    return parts, order


def _classify(**overrides: object) -> ProtectionAssessment:
    kwargs: dict[str, object] = {
        "symbol": SYMBOL,
        "entry_bar_time": BAR,
        "generation": GEN,
        "quantity": QTY,
        "order_list_id": LIST_ID,
        "stop_loss": STOP,
        "take_profit": TARGET,
        "resting": [],
    }
    kwargs.update(overrides)
    return classify_protection(**kwargs)  # type: ignore[arg-type]


def _both_legs_resting(**leg_kwargs: object) -> list[tuple[ClientOrderIdParts, Order]]:
    return [
        _leg(OrderListLeg.STOP_LOSS, stop_price="44117.09000000", **leg_kwargs),  # type: ignore[arg-type]
        _leg(OrderListLeg.TAKE_PROFIT, stop_price="50419.53000000", **leg_kwargs),  # type: ignore[arg-type]
    ]


def test_every_requested_leg_resting_at_its_price_is_active() -> None:
    """Also the padding test, and the two are the same test on purpose.

    The venue returns `44117.09000000` for a requested `44117.09`. Those are
    equal as `Decimal` and unequal as strings, so a string comparison would
    report divergence on protection that is exactly right -- every cycle, on
    every position. There is no separate "padding" case because every realistic
    case IS the padded one.
    """
    result = _classify(resting=_both_legs_resting())

    assert result.state is ProtectionState.ACTIVE
    assert result.unresolved == ()
    assert SYMBOL in result.reason


def test_a_stop_resting_at_the_wrong_price_is_divergence() -> None:
    """Requested and does not rest AS REQUESTED -- section 7's divergence."""
    resting = [
        _leg(OrderListLeg.STOP_LOSS, stop_price="44000.00000000"),
        _leg(OrderListLeg.TAKE_PROFIT, stop_price="50419.53000000"),
    ]

    result = _classify(resting=resting)

    assert result.state is ProtectionState.DIVERGED
    assert "44000" in result.reason and "44117.09" in result.reason


def test_a_pending_leg_is_accepted_and_not_yet_active() -> None:
    """Acceptance is not activation: a pending leg becomes live only when the
    working order fills, so it is its own state rather than a weak ACTIVE."""
    result = _classify(resting=_both_legs_resting(status=OrderStatus.PENDING_NEW))

    assert result.state is ProtectionState.PENDING
    assert "not yet activated" in result.reason


def test_an_absent_leg_is_unresolved_and_names_the_query() -> None:
    """Never resolved directly. Absence is never-placed, cancelled or filled,
    and only a point query separates them -- so the verdict names the id."""
    result = _classify(resting=[_leg(OrderListLeg.TAKE_PROFIT, stop_price="50419.53000000")])

    assert result.state is ProtectionState.UNKNOWN
    assert [item.leg for item in result.unresolved] == [OrderListLeg.STOP_LOSS]
    assert result.unresolved[0].client_order_id == client_order_id(
        SYMBOL, BAR, OrderListLeg.STOP_LOSS, generation=GEN
    )


def test_a_filled_leg_is_refused_rather_than_interpreted() -> None:
    """No instrument in this tree has observed a filled protective leg. UNKNOWN
    is untrusted, so this refuses entries -- reversible, and it makes the
    missing measurement visible in behaviour rather than hiding it."""
    resting = [
        _leg(OrderListLeg.STOP_LOSS, stop_price="44117.09000000", status=OrderStatus.FILLED),
        _leg(OrderListLeg.TAKE_PROFIT, stop_price="50419.53000000"),
    ]

    result = _classify(resting=resting)

    assert result.state is ProtectionState.UNKNOWN
    assert "unmeasured" in result.reason


def test_a_partial_fill_is_refused_on_the_same_grounds() -> None:
    """A different branch from the FILLED status check, and deliberately so: an
    executed quantity above zero is the same unmeasured path arriving by
    another route."""
    resting = [
        _leg(
            OrderListLeg.STOP_LOSS,
            stop_price="44117.09000000",
            status=OrderStatus.PARTIALLY_FILLED,
            filled=Decimal("0.00050000"),
        ),
        _leg(OrderListLeg.TAKE_PROFIT, stop_price="50419.53000000"),
    ]

    result = _classify(resting=resting)

    assert result.state is ProtectionState.UNKNOWN
    assert "0.00050000" in result.reason


def test_a_filled_working_leg_is_not_a_reason_to_refuse() -> None:
    """`-W` IS THE ENTRY, so by the time a position exists it has filled by
    definition. Judged by the fill rule it would make every correctly protected
    position read `UNKNOWN` -- untrusted, therefore uncomputable, therefore a
    portfolio-wide refusal. The interlock firing on the healthy path.

    Correct under both answers to the open question of whether a filled leg
    stays visible to `get_open_orders`: if it does, this prevents the refusal;
    if it does not, the leg is never in the compare set and the skip is inert.
    """
    resting = [
        _leg(OrderListLeg.WORKING, stop_price=None, status=OrderStatus.FILLED, filled=QTY),
        *_both_legs_resting(),
    ]

    result = _classify(resting=resting)

    assert result.state is ProtectionState.ACTIVE


def test_no_state_this_can_return_is_trusted_except_absent_by_design() -> None:
    """What makes `DIVERGED` a REFUSAL rather than a label -- and the mechanism
    is two modules away, which is why it is pinned here.

    Nothing in the classifier says "refuse". `committed_risk` counts any state
    outside `_TRUSTED_PROTECTION` as uncomputable, and that whitelist lives in
    `core/portfolio.py`. A reader of either file alone cannot see the decision,
    so this test is the tripwire across the gap.

    Admitting `ACTIVE` to the whitelist later is a real decision with a real
    cost -- a position would be priced off a stop on the strength of a
    classification -- and it must fail HERE first rather than land quietly.

    **IT DID, and the admission has since been made deliberately.** The test is
    NARROWED rather than retired: `ACTIVE` joins the trusted side because it is
    the one state measured against the venue rather than assumed, and the three
    that remain must still be forbidden. A tripwire deleted once the thing it
    guarded happened would leave the next admission unguarded, which is the
    whole reason it existed.

    So the claim is now stated in BOTH directions. The intersection says what
    may be trusted; the difference says what may not, by name, so a fourth
    member arriving on the trusted side fails against a list rather than
    against an inference.
    """
    from trading_bot.core.portfolio import _TRUSTED_PROTECTION

    producible = {
        _classify(resting=_both_legs_resting()).state,
        _classify(resting=_both_legs_resting(status=OrderStatus.PENDING_NEW)).state,
        _classify(resting=_both_legs_resting(list_id="99999")).state,
        _classify(resting=[]).state,
        _classify(stop_loss=None, take_profit=None).state,
    }

    trusted = producible & _TRUSTED_PROTECTION
    assert trusted == {ProtectionState.ABSENT_BY_DESIGN, ProtectionState.ACTIVE}
    assert producible - _TRUSTED_PROTECTION == {
        ProtectionState.DIVERGED,
        ProtectionState.PENDING,
        ProtectionState.UNKNOWN,
    }


def test_nothing_requested_and_nothing_resting_is_absent_by_design() -> None:
    result = _classify(stop_loss=None, take_profit=None)

    assert result.state is ProtectionState.ABSENT_BY_DESIGN
    assert result.unresolved == ()


def test_nothing_requested_but_legs_resting_is_not_absent_by_design() -> None:
    """`ABSENT_BY_DESIGN` is the off-switch for the divergence detector on this
    position. Asserting it while our own legs rest would switch the detector off
    over a story nobody has established."""
    result = _classify(
        stop_loss=None,
        take_profit=None,
        resting=[_leg(OrderListLeg.STOP_LOSS, stop_price="44117.09000000")],
    )

    assert result.state is ProtectionState.UNKNOWN


def test_legs_from_another_bar_are_not_attributed_to_this_position() -> None:
    """One symbol read serves every position on it, so the compare set carries
    other bars' legs routinely. Reading them as ours would report protection
    that belongs to a different entry."""
    other = datetime(2026, 8, 14, 11, 0, tzinfo=timezone.utc)

    result = _classify(resting=_both_legs_resting(bar=other))

    assert result.state is ProtectionState.UNKNOWN
    assert {item.leg for item in result.unresolved} == {
        OrderListLeg.STOP_LOSS,
        OrderListLeg.TAKE_PROFIT,
    }


def test_a_leg_on_the_wrong_order_list_is_divergence() -> None:
    result = _classify(resting=_both_legs_resting(list_id="99999"))

    assert result.state is ProtectionState.DIVERGED
    assert "99999" in result.reason


def test_the_verdict_is_frozen() -> None:
    """A refusal is a value, and a value nobody can edit after the fact."""
    result = _classify(resting=_both_legs_resting())

    with pytest.raises(Exception):  # noqa: B017 - pydantic's frozen error type
        result.state = ProtectionState.ACTIVE  # type: ignore[misc]


def test_every_protection_state_has_a_writer_here() -> None:
    """The derived half of ``test_models.py``'s literal, kept where it costs no
    coupling. That one asserts the enum's membership; this asserts that every
    member is REACHABLE from this function -- which is the property the
    members-arrive-with-their-writers rule actually cares about.

    A member added ahead of its writer passes there and fails here.
    """
    produced = {
        _classify(resting=_both_legs_resting()).state,
        _classify(resting=_both_legs_resting(status=OrderStatus.PENDING_NEW)).state,
        _classify(resting=_both_legs_resting(list_id="99999")).state,
        _classify(resting=[]).state,
        _classify(stop_loss=None, take_profit=None).state,
    }

    assert produced == set(ProtectionState)
