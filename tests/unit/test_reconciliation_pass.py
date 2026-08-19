"""Tests for the reconciliation pass -- the impure half.

Separate from ``test_reconciliation.py``, whose docstring declares "No I/O and
no ``Position``". These need both: a ``Portfolio`` holding real ``Position``
objects and a fake client. Rewriting that file's scoping sentence to
accommodate them, rather than separating, is the stale-justification pattern
this milestone has recorded three times.

No network and no clock: the client is a stub recording what it was asked, and
``now`` is a parameter.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any

import pytest

from trading_bot.core.enums import (
    OrderSide,
    OrderStatus,
    OrderType,
    PositionSide,
    ProtectionState,
)
from trading_bot.core.exceptions import (
    ContractViolationError,
    ExchangeConnectionError,
    OrderNotFoundError,
)
from trading_bot.core.models import Order, Position
from trading_bot.core.portfolio import Portfolio
from trading_bot.exchange.ids import OrderListLeg, client_order_id
from trading_bot.execution.reconciliation import (
    ProtectionAssessment,
    UnresolvedLeg,
    reconcile_open_positions,
    resolve_unresolved_legs,
)

NOW = datetime(2026, 8, 15, 12, 0, tzinfo=timezone.utc)
BAR = datetime(2026, 8, 15, 11, 0, tzinfo=timezone.utc)
DEDUP = timedelta(minutes=1)
QTY = Decimal("0.00100000")
STOP = Decimal("44117.09")
LIST_ID = "91590"


class _StubClient:
    """Records what it was asked, and REFUSES to answer what it was not told.

    **A fake's default answer must be one the venue could not give
    ambiguously.** An empty list from an enumeration is indistinguishable from
    "nothing of ours rests" -- a real classification with real consequences,
    since absence classifies `UNKNOWN`, which is untrusted, which refuses
    entries. A test getting that by default passes for a reason nobody chose.
    Raising is distinguishable from everything.

    So a book must be configured, even when the intended book is empty: an
    explicit ``{"BTCUSDT": []}`` says "nothing rests" on purpose.
    """

    def __init__(
        self,
        books: dict[str, list[Order]] | None = None,
        orders: dict[str, Order | Exception] | None = None,
    ) -> None:
        self.books = books if books is not None else {}
        self.orders = orders or {}
        self.asked: list[str] = []
        self.queried: list[str] = []

    async def get_own_open_orders(self, symbol: str, **_kwargs: Any) -> list[Order]:
        self.asked.append(symbol)
        if symbol not in self.books:
            raise AssertionError(
                f"no book configured for {symbol!r}. Configure one explicitly -- an implicit "
                "empty list is a classification, not an absence of one."
            )
        return self.books[symbol]

    async def get_order(
        self, symbol: str, *, client_order_id: str | None = None, **_kwargs: Any
    ) -> Order:
        key = client_order_id or ""
        self.queried.append(key)
        if key not in self.orders:
            raise AssertionError(
                f"no point-query answer configured for {key!r}. A point query has no empty "
                "answer: absence there is OrderNotFoundError, an exception, not a value."
            )
        answer = self.orders[key]
        if isinstance(answer, Exception):
            raise answer
        return answer


def _order(
    symbol: str,
    leg: OrderListLeg,
    *,
    stop_price: str | None = "44117.09000000",
    status: OrderStatus = OrderStatus.NEW,
    cid: str | None = None,
) -> Order:
    return Order(
        order_id="1",
        symbol=symbol,
        side=OrderSide.SELL,
        type=OrderType.STOP_LOSS,
        status=status,
        quantity=QTY,
        stop_price=Decimal(stop_price) if stop_price is not None else None,
        order_list_id=LIST_ID,
        client_order_id=cid if cid is not None else client_order_id(symbol, BAR, leg, generation=0),
    )


def _position(symbol: str, *, stamp: datetime | None, stop_loss: Decimal | None = STOP) -> Position:
    return Position(
        symbol=symbol,
        side=PositionSide.LONG,
        quantity=QTY,
        entry_price=Decimal("47000.00"),
        entry_bar_time=BAR,
        protection=ProtectionState.UNKNOWN,
        order_list_id=LIST_ID,
        last_reconciled_at=stamp,
        stop_loss=stop_loss,
    )


def _portfolio(*positions: Position) -> Portfolio:
    return Portfolio(
        free_quote=Decimal("10000"),
        positions={position.symbol: position for position in positions},
    )


async def test_one_call_per_symbol_for_a_due_position() -> None:
    position = _position("BTCUSDT", stamp=None)
    client = _StubClient({"BTCUSDT": [_order("BTCUSDT", OrderListLeg.STOP_LOSS)]})

    await reconcile_open_positions(
        portfolio=_portfolio(position), client=client, now=NOW, dedup_interval=DEDUP
    )

    assert client.asked == ["BTCUSDT"]


async def test_positions_are_visited_oldest_stamp_first() -> None:
    """A pass cut short by the budget must advance the STALEST, not a fixed
    tail. Unstamped sorts first, having waited longest by definition."""
    fresh = _position("ETHUSDT", stamp=NOW - timedelta(minutes=5))
    stale = _position("BTCUSDT", stamp=NOW - timedelta(minutes=30))
    never = _position("SOLUSDT", stamp=None)
    client = _StubClient({"SOLUSDT": [], "BTCUSDT": [], "ETHUSDT": []})

    await reconcile_open_positions(
        portfolio=_portfolio(fresh, stale, never),
        client=client,
        now=NOW,
        dedup_interval=DEDUP,
    )

    assert client.asked == ["SOLUSDT", "BTCUSDT", "ETHUSDT"]


async def test_the_returned_order_matches_the_visit_order() -> None:
    """A CORRESPONDENCE, not an ordering -- deliberately. Reversing the visit
    order flips both sides together and cannot be seen here; the test above is
    what pins the order itself."""
    fresh = _position("ETHUSDT", stamp=NOW - timedelta(minutes=5))
    stale = _position("BTCUSDT", stamp=NOW - timedelta(minutes=30))
    client = _StubClient({"BTCUSDT": [], "ETHUSDT": []})

    results = await reconcile_open_positions(
        portfolio=_portfolio(fresh, stale), client=client, now=NOW, dedup_interval=DEDUP
    )

    assert [position.symbol for position, _assessment in results] == client.asked


async def test_a_fresh_stamp_is_not_re_read() -> None:
    """Deduplication: two pairs closing on the same minute pay for one pass."""
    position = _position("BTCUSDT", stamp=NOW - timedelta(seconds=10))
    client = _StubClient({"BTCUSDT": []})

    results = await reconcile_open_positions(
        portfolio=_portfolio(position), client=client, now=NOW, dedup_interval=DEDUP
    )

    assert client.asked == []
    assert results == ()
    assert position.last_reconciled_at == NOW - timedelta(seconds=10)


async def test_a_never_reconciled_position_is_read() -> None:
    """`None` re-reads. A DEDUP decision only: one call, and it cannot be wrong.
    What `None` means for the STALENESS REFUSAL is a separate open ruling and
    nothing here is precedent for it."""
    position = _position("BTCUSDT", stamp=None)
    client = _StubClient({"BTCUSDT": []})

    await reconcile_open_positions(
        portfolio=_portfolio(position), client=client, now=NOW, dedup_interval=DEDUP
    )

    assert client.asked == ["BTCUSDT"]


async def test_the_pass_writes_the_state_and_the_stamp() -> None:
    position = _position("BTCUSDT", stamp=None)
    client = _StubClient({"BTCUSDT": [_order("BTCUSDT", OrderListLeg.STOP_LOSS)]})

    await reconcile_open_positions(
        portfolio=_portfolio(position), client=client, now=NOW, dedup_interval=DEDUP
    )

    assert position.protection is ProtectionState.ACTIVE
    assert position.last_reconciled_at == NOW


async def test_the_pass_returns_the_reason_and_the_unresolved_legs() -> None:
    """NEITHER IS RECOVERABLE FROM A WRITTEN POSITION. Resolving an absent leg
    would have to re-derive the whole classification, escalation needs a cause
    for its detail field, and an operator facing a portfolio-wide refusal is
    owed one. So the pass hands them back rather than discarding them.
    """
    position = _position("BTCUSDT", stamp=None)
    client = _StubClient({"BTCUSDT": []})  # nothing rests, ON PURPOSE

    ((_position_out, assessment),) = await reconcile_open_positions(
        portfolio=_portfolio(position), client=client, now=NOW, dedup_interval=DEDUP
    )

    assert assessment.state is ProtectionState.UNKNOWN
    assert "SL" in assessment.reason
    assert [item.leg for item in assessment.unresolved] == [OrderListLeg.STOP_LOSS]
    assert assessment.unresolved[0].client_order_id == client_order_id(
        "BTCUSDT", BAR, OrderListLeg.STOP_LOSS, generation=0
    )


async def test_an_unparseable_id_is_a_contract_violation() -> None:
    """The implementation filters by parsing, so an order reaching the pass with
    an unparseable id means OUR adapter is broken -- our bug, not a venue state.

    Aborting is survivable: unvisited positions keep old stamps, go stale and
    refuse entries, which is identical to a budget-cut-short pass. Oldest-first
    ordering puts that loss on the freshest.
    """
    position = _position("BTCUSDT", stamp=None)
    client = _StubClient({"BTCUSDT": [_order("BTCUSDT", OrderListLeg.STOP_LOSS, cid="not-ours")]})

    with pytest.raises(ContractViolationError, match="does not parse"):
        await reconcile_open_positions(
            portfolio=_portfolio(position), client=client, now=NOW, dedup_interval=DEDUP
        )


async def test_a_closed_position_is_not_visited() -> None:
    flat = Position(
        symbol="BTCUSDT",
        side=PositionSide.FLAT,
        quantity=Decimal(0),
        entry_price=Decimal("47000.00"),
        entry_bar_time=BAR,
        protection=ProtectionState.UNKNOWN,
    )
    client = _StubClient({"BTCUSDT": []})

    results = await reconcile_open_positions(
        portfolio=_portfolio(flat), client=client, now=NOW, dedup_interval=DEDUP
    )

    assert client.asked == []
    assert results == ()


def test_record_reconciliation_rejects_a_naive_stamp() -> None:
    """A naive value reads as local time and moves every staleness comparison by
    the host's offset. Guarded on the field's own writer, so it holds for every
    caller and not just the pass."""
    position = _position("BTCUSDT", stamp=None)

    with pytest.raises(ValueError, match="aware datetime"):
        position.record_reconciliation(
            protection=ProtectionState.ACTIVE, at=datetime(2026, 8, 15, 12, 0)
        )


# --------------------------------------------------------------------------
# Resolving an absent leg by point query
# --------------------------------------------------------------------------
# The pass leaves an absent leg UNRESOLVED and names the query. These cover the
# other half: what each answer means, and what happens when the budget runs out
# before the questions do.

SL_ID = client_order_id("BTCUSDT", BAR, OrderListLeg.STOP_LOSS, generation=0)
TP_ID = client_order_id("BTCUSDT", BAR, OrderListLeg.TAKE_PROFIT, generation=0)


def _unresolved(*legs: OrderListLeg) -> tuple[Position, ProtectionAssessment]:
    """A position whose named legs came back unresolved from the pass."""
    return (
        _position("BTCUSDT", stamp=None),
        ProtectionAssessment(
            state=ProtectionState.UNKNOWN,
            reason="absent from the enumeration",
            unresolved=tuple(
                UnresolvedLeg(
                    leg=leg,
                    client_order_id=client_order_id("BTCUSDT", BAR, leg, generation=0),
                )
                for leg in legs
            ),
        ),
    )


def _queried(status: OrderStatus, *, filled: Decimal = Decimal(0)) -> Order:
    return Order(
        order_id="1",
        symbol="BTCUSDT",
        side=OrderSide.SELL,
        type=OrderType.STOP_LOSS,
        status=status,
        quantity=QTY,
        filled_quantity=filled,
        stop_price=STOP,
        client_order_id=SL_ID,
    )


async def test_a_cancelled_leg_is_divergence() -> None:
    """Requested, and does not rest. The clearest case there is."""
    client = _StubClient(orders={SL_ID: _queried(OrderStatus.CANCELED)})

    ((_p, assessment),) = await resolve_unresolved_legs(
        assessments=[_unresolved(OrderListLeg.STOP_LOSS)], client=client, max_queries=4
    )

    assert assessment.state is ProtectionState.DIVERGED
    assert "CANCELED" in assessment.reason


async def test_an_unknown_order_is_divergence_with_its_cause_recorded() -> None:
    """Same conclusion as CANCELED, different cause -- and the cause goes in the
    reason, because `-2011` cannot distinguish never-placed from
    placed-and-since-purged and order retention is unmeasured."""
    client = _StubClient(orders={SL_ID: OrderNotFoundError("Unknown order sent.")})

    ((_p, assessment),) = await resolve_unresolved_legs(
        assessments=[_unresolved(OrderListLeg.STOP_LOSS)], client=client, max_queries=4
    )

    assert assessment.state is ProtectionState.DIVERGED
    assert "no such order" in assessment.reason
    assert "retention is unmeasured" in assessment.reason


async def test_a_filled_leg_is_refused_rather_than_interpreted() -> None:
    """Consistent with the classifier: the fill path is UNMEASURED, so this
    refuses to read it rather than guessing."""
    client = _StubClient(orders={SL_ID: _queried(OrderStatus.FILLED, filled=QTY)})

    ((_p, assessment),) = await resolve_unresolved_legs(
        assessments=[_unresolved(OrderListLeg.STOP_LOSS)], client=client, max_queries=4
    )

    assert assessment.state is ProtectionState.UNKNOWN
    assert "unmeasured" in assessment.reason


async def test_a_partially_filled_leg_is_refused_on_the_same_grounds() -> None:
    client = _StubClient(
        orders={SL_ID: _queried(OrderStatus.PARTIALLY_FILLED, filled=Decimal("0.0005"))}
    )

    ((_p, assessment),) = await resolve_unresolved_legs(
        assessments=[_unresolved(OrderListLeg.STOP_LOSS)], client=client, max_queries=4
    )

    assert assessment.state is ProtectionState.UNKNOWN


@pytest.mark.parametrize("status", [OrderStatus.NEW, OrderStatus.PENDING_NEW])
async def test_a_live_leg_is_an_instrument_disagreement(status: OrderStatus) -> None:
    """Absent from the enumeration and live on a point query. Two views of one
    leg disagree and nothing measured says which to believe, so neither is acted
    on -- the reading whose wrong answer is reversible."""
    client = _StubClient(orders={SL_ID: _queried(status)})

    ((_p, assessment),) = await resolve_unresolved_legs(
        assessments=[_unresolved(OrderListLeg.STOP_LOSS)], client=client, max_queries=4
    )

    assert assessment.state is ProtectionState.UNKNOWN
    assert "INSTRUMENT DISAGREEMENT" in assessment.reason


async def test_the_cap_bounds_the_number_of_queries() -> None:
    """Point queries are a separate budget line the driver spends, so the cap is
    a parameter and the function must honour it."""
    client = _StubClient(orders={SL_ID: _queried(OrderStatus.CANCELED)})

    await resolve_unresolved_legs(
        assessments=[_unresolved(OrderListLeg.STOP_LOSS, OrderListLeg.TAKE_PROFIT)],
        client=client,
        max_queries=1,
    )

    assert client.queried == [SL_ID]


async def test_an_unqueried_leg_reads_differently_from_a_resolved_one() -> None:
    """ "Not yet queried" and "queried and unresolved" are different facts. An
    operator who cannot tell them apart cannot tell whether spending more budget
    would help."""
    client = _StubClient(orders={SL_ID: _queried(OrderStatus.CANCELED)})

    ((_p, assessment),) = await resolve_unresolved_legs(
        assessments=[_unresolved(OrderListLeg.STOP_LOSS, OrderListLeg.TAKE_PROFIT)],
        client=client,
        max_queries=1,
    )

    assert "NOT YET QUERIED" in assessment.reason
    assert assessment.state is ProtectionState.UNKNOWN


async def test_the_weaker_answer_wins_when_legs_disagree() -> None:
    """One leg provably gone and another unresolved is not a position we
    understand. `DIVERGED` is what section 7 answers with re-placement, and that
    must not run on partial knowledge."""
    client = _StubClient(
        orders={SL_ID: _queried(OrderStatus.CANCELED), TP_ID: _queried(OrderStatus.NEW)}
    )

    ((_p, assessment),) = await resolve_unresolved_legs(
        assessments=[_unresolved(OrderListLeg.STOP_LOSS, OrderListLeg.TAKE_PROFIT)],
        client=client,
        max_queries=4,
    )

    assert assessment.state is ProtectionState.UNKNOWN


async def test_an_assessment_with_nothing_unresolved_is_passed_through() -> None:
    """No unresolved legs, no queries. ACTIVE and ABSENT_BY_DESIGN both arrive
    here and must leave untouched."""
    client = _StubClient()
    passthrough = [
        (
            _position("BTCUSDT", stamp=None),
            ProtectionAssessment(state=ProtectionState.ACTIVE, reason="all rest"),
        ),
        (
            _position("ETHUSDT", stamp=None),
            ProtectionAssessment(state=ProtectionState.ABSENT_BY_DESIGN, reason="none requested"),
        ),
    ]

    refined = await resolve_unresolved_legs(assessments=passthrough, client=client, max_queries=4)

    assert refined == tuple(passthrough)
    assert client.queried == []


async def test_a_failure_to_get_an_answer_propagates() -> None:
    """THE PRINCIPLE, not a list of types. `OrderNotFoundError` is an ANSWER --
    the venue saying the order does not exist. A transport failure is a FAILURE
    TO GET ONE, and turning that into a verdict is exactly what the classifier
    refuses to do with absence. A verdict must rest on something the venue said.
    """
    client = _StubClient(orders={SL_ID: ExchangeConnectionError("reset")})

    with pytest.raises(ExchangeConnectionError):
        await resolve_unresolved_legs(
            assessments=[_unresolved(OrderListLeg.STOP_LOSS)], client=client, max_queries=4
        )


async def test_no_state_resolution_can_return_is_trusted() -> None:
    """R1a's invariant, extended to the second producer of `ProtectionState`.

    The classifier's version guards `classify_protection`; this guards
    `resolve_unresolved_legs`, which reaches states by an entirely different
    route -- a point-query answer rather than a compare set -- and could
    therefore widen the trusted set without the other test noticing.

    `ABSENT_BY_DESIGN` is not in this set at all: resolution only ever touches
    assessments carrying unresolved legs, and a position with nothing requested
    has none. So EVERY state this can return must be untrusted, with no
    exception clause.
    """
    from trading_bot.core.portfolio import _TRUSTED_PROTECTION

    answers: dict[str, Order | Exception] = {
        SL_ID: _queried(OrderStatus.CANCELED),
        TP_ID: _queried(OrderStatus.NEW),
    }
    producible = set()
    for key, answer in answers.items():
        ((_p, assessment),) = await resolve_unresolved_legs(
            assessments=[
                _unresolved(OrderListLeg.STOP_LOSS if key == SL_ID else OrderListLeg.TAKE_PROFIT)
            ],
            client=_StubClient(orders={key: answer}),
            max_queries=4,
        )
        producible.add(assessment.state)
    # The cap path, which returns without querying anything.
    ((_p, capped),) = await resolve_unresolved_legs(
        assessments=[_unresolved(OrderListLeg.STOP_LOSS)],
        client=_StubClient(),
        max_queries=0,
    )
    producible.add(capped.state)

    assert producible == {ProtectionState.DIVERGED, ProtectionState.UNKNOWN}
    assert producible & _TRUSTED_PROTECTION == set()


async def test_resolution_does_not_write_to_the_position() -> None:
    """Every state this can return is untrusted exactly as the `UNKNOWN` the
    pass wrote is untrusted, so the ledger's answer does not change -- only the
    report sharpens. Writing would also re-stamp a dedup clock the pass just
    set."""
    position, assessment = _unresolved(OrderListLeg.STOP_LOSS)
    position.record_reconciliation(protection=ProtectionState.UNKNOWN, at=NOW)
    client = _StubClient(orders={SL_ID: _queried(OrderStatus.CANCELED)})

    await resolve_unresolved_legs(
        assessments=[(position, assessment)], client=client, max_queries=4
    )

    assert position.protection is ProtectionState.UNKNOWN
    assert position.last_reconciled_at == NOW
