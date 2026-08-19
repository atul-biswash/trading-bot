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
#: A take-profit, so a position can request TWO protective legs. The
#: reservation is a leg COUNT, and a one-leg fixture cannot express that.
TAKE = Decimal("52000.00")
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
        #: The per-call transport bound each call was given. RECORDED rather
        #: than swallowed into ``**kwargs``: a fixture that accepts an argument
        #: and discards it cannot express a mutation that stops forwarding it,
        #: so every bound test written against such a fixture abstains while
        #: appearing to cover the thing. Naming the parameters also turns an
        #: unexpected keyword into a ``TypeError`` here rather than silence.
        self.bounds: list[tuple[float | None, int | None]] = []
        self.query_bounds: list[tuple[float | None, int | None]] = []

    async def get_own_open_orders(
        self, symbol: str, *, timeout_s: float | None = None, attempts: int | None = None
    ) -> list[Order]:
        self.asked.append(symbol)
        self.bounds.append((timeout_s, attempts))
        if symbol not in self.books:
            raise AssertionError(
                f"no book configured for {symbol!r}. Configure one explicitly -- an implicit "
                "empty list is a classification, not an absence of one."
            )
        return self.books[symbol]

    async def get_order(
        self,
        symbol: str,
        *,
        client_order_id: str | None = None,
        timeout_s: float | None = None,
        attempts: int | None = None,
    ) -> Order:
        key = client_order_id or ""
        self.queried.append(key)
        self.query_bounds.append((timeout_s, attempts))
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


def _position(
    symbol: str,
    *,
    stamp: datetime | None,
    stop_loss: Decimal | None = STOP,
    take_profit: Decimal | None = None,
) -> Position:
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
        take_profit=take_profit,
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
        portfolio=_portfolio(position),
        client=client,
        now=NOW,
        dedup_interval=DEDUP,
        max_calls=3,
        timeout_s=None,
        attempts=None,
    )

    assert client.asked == ["BTCUSDT"]


async def test_positions_are_visited_oldest_stamp_first() -> None:
    """A pass cut short by the budget must advance the STALEST, not a fixed
    tail. Unstamped sorts first, having waited longest by definition.

    **Every book RESTS deliberately.** Empty books would classify unresolved,
    which arms the last-call reservation and cuts the pass to two symbols --
    confounding the ordering claim with a budget one. The reservation has its
    own tests; this one must be able to see all three.
    """
    fresh = _position("ETHUSDT", stamp=NOW - timedelta(minutes=5))
    stale = _position("BTCUSDT", stamp=NOW - timedelta(minutes=30))
    never = _position("SOLUSDT", stamp=None)
    client = _StubClient(
        {
            symbol: [_order(symbol, OrderListLeg.STOP_LOSS)]
            for symbol in ("SOLUSDT", "BTCUSDT", "ETHUSDT")
        }
    )

    await reconcile_open_positions(
        portfolio=_portfolio(fresh, stale, never),
        client=client,
        now=NOW,
        dedup_interval=DEDUP,
        max_calls=3,
        timeout_s=None,
        attempts=None,
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
        portfolio=_portfolio(fresh, stale),
        client=client,
        now=NOW,
        dedup_interval=DEDUP,
        max_calls=3,
        timeout_s=None,
        attempts=None,
    )

    assert [position.symbol for position, _assessment in results] == client.asked


async def test_a_fresh_stamp_is_not_re_read() -> None:
    """Deduplication: two pairs closing on the same minute pay for one pass."""
    position = _position("BTCUSDT", stamp=NOW - timedelta(seconds=10))
    client = _StubClient({"BTCUSDT": []})

    results = await reconcile_open_positions(
        portfolio=_portfolio(position),
        client=client,
        now=NOW,
        dedup_interval=DEDUP,
        max_calls=3,
        timeout_s=None,
        attempts=None,
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
        portfolio=_portfolio(position),
        client=client,
        now=NOW,
        dedup_interval=DEDUP,
        max_calls=3,
        timeout_s=None,
        attempts=None,
    )

    assert client.asked == ["BTCUSDT"]


async def test_the_pass_writes_the_state_and_the_stamp() -> None:
    position = _position("BTCUSDT", stamp=None)
    client = _StubClient({"BTCUSDT": [_order("BTCUSDT", OrderListLeg.STOP_LOSS)]})

    await reconcile_open_positions(
        portfolio=_portfolio(position),
        client=client,
        now=NOW,
        dedup_interval=DEDUP,
        max_calls=3,
        timeout_s=None,
        attempts=None,
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
        portfolio=_portfolio(position),
        client=client,
        now=NOW,
        dedup_interval=DEDUP,
        max_calls=3,
        timeout_s=None,
        attempts=None,
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
            portfolio=_portfolio(position),
            client=client,
            now=NOW,
            dedup_interval=DEDUP,
            max_calls=3,
            timeout_s=None,
            attempts=None,
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
        portfolio=_portfolio(flat),
        client=client,
        now=NOW,
        dedup_interval=DEDUP,
        max_calls=3,
        timeout_s=None,
        attempts=None,
    )

    assert client.asked == []
    assert results == ()


# --------------------------------------------------------------------------
# The phase budget, and the last call it holds back
# --------------------------------------------------------------------------
def _resting(*symbols: str) -> dict[str, list[Order]]:
    """Books in which every requested leg rests, so nothing is unresolved."""
    return {symbol: [_order(symbol, OrderListLeg.STOP_LOSS)] for symbol in symbols}


async def test_the_pass_forwards_its_per_call_bound_to_the_client() -> None:
    """A caller on a deadline must be able to bound this THROUGH the pass.
    Omitting the bound inherits the client-wide policy -- four attempts at the
    general timeout -- inside a slot reserved at `reconcile_deadline_s`, which
    silently blows the only guarantee the coherence validator computes."""
    position = _position("BTCUSDT", stamp=None)
    client = _StubClient(_resting("BTCUSDT"))

    await reconcile_open_positions(
        portfolio=_portfolio(position),
        client=client,
        now=NOW,
        dedup_interval=DEDUP,
        max_calls=3,
        timeout_s=3.0,
        attempts=1,
    )

    assert client.bounds == [(3.0, 1)]


async def test_the_pass_stops_at_max_calls() -> None:
    """The plain cap: total calls never exceed the reservation the coherence
    validator computed, which is met with equality and never exceeded."""
    positions = [_position(symbol, stamp=None) for symbol in ("BTCUSDT", "ETHUSDT", "SOLUSDT")]
    client = _StubClient(_resting("BTCUSDT", "ETHUSDT", "SOLUSDT"))

    results = await reconcile_open_positions(
        portfolio=_portfolio(*positions),
        client=client,
        now=NOW,
        dedup_interval=DEDUP,
        max_calls=2,
        timeout_s=None,
        attempts=None,
    )

    assert client.asked == ["BTCUSDT", "ETHUSDT"]
    assert len(results) == 2


async def test_the_pass_reserves_its_last_call_once_a_leg_is_unresolved() -> None:
    """Positions are keyed by SYMBOL, so at the position limit the pass would
    otherwise consume the whole budget and leave resolution zero -- every
    cycle, and precisely when there is most protection to verify."""
    positions = [_position(symbol, stamp=None) for symbol in ("BTCUSDT", "ETHUSDT", "SOLUSDT")]
    books = _resting("ETHUSDT", "SOLUSDT")
    books["BTCUSDT"] = []  # first visited, and nothing of ours rests

    results = await reconcile_open_positions(
        portfolio=_portfolio(*positions),
        client=_StubClient(books),
        now=NOW,
        dedup_interval=DEDUP,
        max_calls=3,
        timeout_s=None,
        attempts=None,
    )

    assert len(results) == 2  # one call held back: the absent position needs L=1


async def test_the_reservation_is_the_first_positions_leg_count_not_one() -> None:
    """L, not 1. Completing an L-leg position costs 1 enumeration + L queries,
    so reserving a single call leaves a two-leg position permanently
    unfinishable -- it re-queries the same first leg every cycle, never
    completes, never gets stamped, and therefore sorts first forever while the
    positions behind it are never read.

    The contrast with the test above is the point: identical shape, one absent
    leg there and two here, and the pass stops one call earlier.
    """
    positions = [
        _position("BTCUSDT", stamp=None, take_profit=TAKE),
        _position("ETHUSDT", stamp=None),
        _position("SOLUSDT", stamp=None),
    ]
    books = _resting("ETHUSDT", "SOLUSDT")
    books["BTCUSDT"] = []

    results = await reconcile_open_positions(
        portfolio=_portfolio(*positions),
        client=_StubClient(books),
        now=NOW,
        dedup_interval=DEDUP,
        max_calls=3,
        timeout_s=None,
        attempts=None,
    )

    assert len(results) == 1  # two calls held back, because L is two


async def test_only_the_first_unresolved_positions_legs_are_reserved() -> None:
    """FIRST-WINS, and the two positions must need DIFFERENT numbers of legs.

    Reserving for every unresolved position would shrink the pass until it read
    almost nothing; completing them one at a time is what makes progress
    monotone. But with two one-leg positions, first-wins, last-wins and
    accumulate-all are indistinguishable at a budget this size -- the fixture
    would read as covering the rule while being blind to both inversions. So
    the first unresolved position needs ONE leg and the second needs TWO:
    first-wins reserves 1 and reads all three, last-wins reserves 2 and stops
    at two, accumulate reserves 3 and also stops at two.
    """
    positions = [
        _position("BTCUSDT", stamp=None),
        _position("ETHUSDT", stamp=None, take_profit=TAKE),
        _position("SOLUSDT", stamp=None),
    ]
    books = _resting("SOLUSDT")
    books["BTCUSDT"] = []
    books["ETHUSDT"] = []

    results = await reconcile_open_positions(
        portfolio=_portfolio(*positions),
        client=_StubClient(books),
        now=NOW,
        dedup_interval=DEDUP,
        max_calls=4,
        timeout_s=None,
        attempts=None,
    )

    assert len(results) == 3


async def test_the_pass_never_leaves_less_than_it_reserved() -> None:
    """THE GUARANTEE, asserted directly rather than inferred from a count.
    The loop continues only while `len(results) + reserved < max_calls`, so the
    remainder the caller derives is at least what the first unresolved position
    needs -- and the total the phase can spend never exceeds the reservation
    the coherence validator computed.
    """
    positions = [
        _position("BTCUSDT", stamp=None, take_profit=TAKE),
        _position("ETHUSDT", stamp=None),
        _position("SOLUSDT", stamp=None),
    ]
    books = _resting("ETHUSDT", "SOLUSDT")
    books["BTCUSDT"] = []
    max_calls = 3

    results = await reconcile_open_positions(
        portfolio=_portfolio(*positions),
        client=_StubClient(books),
        now=NOW,
        dedup_interval=DEDUP,
        max_calls=max_calls,
        timeout_s=None,
        attempts=None,
    )

    outstanding = sum(len(assessment.unresolved) for _p, assessment in results)
    assert max_calls - len(results) >= outstanding


async def test_a_budget_below_one_plus_l_cannot_complete_the_position() -> None:
    """THE BOUNDARY, pinned so the rule is not read as universal. Completing an
    L-leg position costs 1 + L calls, so at `max_calls = 2` a two-leg position
    cannot be finished by any scheme respecting `total <= max_calls`. That is
    arithmetic, not a weakness in the reservation -- and it makes
    `max_open_positions >= L + 1` a config relation nothing validates. See
    `docs/NEXT_MILESTONE.md` item 13.
    """
    positions = [
        _position("BTCUSDT", stamp=None, take_profit=TAKE),
        _position("ETHUSDT", stamp=None),
    ]
    books = _resting("ETHUSDT")
    books["BTCUSDT"] = []

    results = await reconcile_open_positions(
        portfolio=_portfolio(*positions),
        client=_StubClient(books),
        now=NOW,
        dedup_interval=DEDUP,
        max_calls=2,
        timeout_s=None,
        attempts=None,
    )

    ((_position_out, assessment),) = results
    assert len(assessment.unresolved) == 2
    assert 2 - len(results) < len(assessment.unresolved)  # the remainder cannot cover it


async def test_a_late_discovered_unresolved_position_self_corrects_next_cycle() -> None:
    """The one asymmetric case, and why it needs no lookahead. A first
    unresolved position discovered LAST sets the reservation after every call
    is spent, so the resolver may get nothing that cycle -- but the position is
    left unstamped, sorts first next cycle, and is then discovered on call one
    with its full share still unspent.
    """
    healthy = _position("ETHUSDT", stamp=NOW - timedelta(minutes=30))
    broken = _position("BTCUSDT", stamp=NOW - timedelta(minutes=5), take_profit=TAKE)
    books = _resting("ETHUSDT")
    books["BTCUSDT"] = []
    client = _StubClient(books)
    portfolio = _portfolio(healthy, broken)

    first = await reconcile_open_positions(
        portfolio=portfolio,
        client=client,
        now=NOW,
        dedup_interval=DEDUP,
        max_calls=3,
        timeout_s=None,
        attempts=None,
    )
    assert client.asked == ["ETHUSDT", "BTCUSDT"]
    assert 3 - len(first) == 1  # discovered last: only one call left, and it needs two

    client.asked.clear()
    second = await reconcile_open_positions(
        portfolio=portfolio,
        client=client,
        now=NOW + timedelta(minutes=2),
        dedup_interval=DEDUP,
        max_calls=3,
        timeout_s=None,
        attempts=None,
    )

    assert client.asked == ["BTCUSDT"]  # oldest stamp, so first -- and the pass stops
    assert 3 - len(second) == 2  # its full share is left over


async def test_the_pass_spends_every_call_when_nothing_is_unresolved() -> None:
    """The other direction, and what makes the reservation FREE: at steady
    state there is nothing to resolve, so holding a call back would tax
    reconciliation permanently for a resolver with no work.

    DECLARED ABSTENTION: this fixture cannot express a mutation that removes
    the reservation, because nothing here is ever unresolved. The test above is
    what bites for that direction.
    """
    positions = [_position(symbol, stamp=None) for symbol in ("BTCUSDT", "ETHUSDT", "SOLUSDT")]

    results = await reconcile_open_positions(
        portfolio=_portfolio(*positions),
        client=_StubClient(_resting("BTCUSDT", "ETHUSDT", "SOLUSDT")),
        now=NOW,
        dedup_interval=DEDUP,
        max_calls=3,
        timeout_s=None,
        attempts=None,
    )

    assert len(results) == 3


async def test_the_first_call_is_never_reserved_away() -> None:
    """Nothing can be unresolved before the first call, so the reservation
    cannot starve the pass to nothing -- not even at `max_calls=1`, where the
    reserved slot and the only slot are the same one."""
    position = _position("BTCUSDT", stamp=None)
    client = _StubClient({"BTCUSDT": []})

    results = await reconcile_open_positions(
        portfolio=_portfolio(position),
        client=client,
        now=NOW,
        dedup_interval=DEDUP,
        max_calls=1,
        timeout_s=None,
        attempts=None,
    )

    assert client.asked == ["BTCUSDT"]
    assert len(results) == 1


async def test_one_call_per_result_is_what_lets_the_caller_derive_the_remainder() -> None:
    """The caller derives the resolver's budget as `max_calls - len(results)`
    and keeps no counter. That derivation is only sound because the pass makes
    exactly one call per returned assessment, so the correspondence is pinned
    rather than assumed.

    DECLARED ABSTENTION: this test failed under NONE of commit 1's eleven
    mutations, and that is a property of what it pins rather than a gap. The
    correspondence is COVERAGE BY CONSTRUCTION -- the loop issues one call and
    appends one result on the same pass, with no branch between them -- so
    breaking it needs the loop restructured, not a line changed. It is here
    because a later restructuring is exactly what would break it silently, and
    because an arithmetic in another module depends on it.
    """
    positions = [_position(symbol, stamp=None) for symbol in ("BTCUSDT", "ETHUSDT")]
    client = _StubClient(_resting("BTCUSDT", "ETHUSDT"))

    results = await reconcile_open_positions(
        portfolio=_portfolio(*positions),
        client=client,
        now=NOW,
        dedup_interval=DEDUP,
        max_calls=3,
        timeout_s=None,
        attempts=None,
    )

    assert len(results) == len(client.asked)


async def test_a_position_with_unresolved_legs_keeps_its_verdict_and_loses_its_stamp() -> None:
    """Both halves, together. The verdict is real and is written; the stamp is
    withheld because the position was not fully reconciled. This is the state
    `record_reconciliation`'s ordering exists to prefer, now produced on
    purpose rather than only by an interrupted write."""
    position = _position("BTCUSDT", stamp=None)
    client = _StubClient({"BTCUSDT": []})

    await reconcile_open_positions(
        portfolio=_portfolio(position),
        client=client,
        now=NOW,
        dedup_interval=DEDUP,
        max_calls=3,
        timeout_s=None,
        attempts=None,
    )

    assert position.protection is ProtectionState.UNKNOWN
    assert position.last_reconciled_at is None


async def test_an_unstamped_position_sorts_first_on_the_next_pass() -> None:
    """THE MECHANISM IS THE STAMP, not memory. Withholding it is what makes the
    next pass visit the unresolved position first, which is what arms the
    reservation early enough to fund the query it missed. Nothing carries state
    between passes."""
    healthy = _position("ETHUSDT", stamp=NOW - timedelta(minutes=30))
    broken = _position("BTCUSDT", stamp=NOW - timedelta(minutes=5))
    books = _resting("ETHUSDT")
    books["BTCUSDT"] = []
    client = _StubClient(books)

    await reconcile_open_positions(
        portfolio=_portfolio(healthy, broken),
        client=client,
        now=NOW,
        dedup_interval=DEDUP,
        max_calls=3,
        timeout_s=None,
        attempts=None,
    )
    assert client.asked == ["ETHUSDT", "BTCUSDT"]

    client.asked.clear()
    await reconcile_open_positions(
        portfolio=_portfolio(healthy, broken),
        client=client,
        now=NOW + timedelta(minutes=2),
        dedup_interval=DEDUP,
        max_calls=3,
        timeout_s=None,
        attempts=None,
    )

    assert client.asked[0] == "BTCUSDT"


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
        assessments=[_unresolved(OrderListLeg.STOP_LOSS)],
        client=client,
        max_queries=4,
        now=NOW,
        timeout_s=None,
        attempts=None,
    )

    assert assessment.state is ProtectionState.DIVERGED
    assert "CANCELED" in assessment.reason


async def test_an_unknown_order_is_divergence_with_its_cause_recorded() -> None:
    """Same conclusion as CANCELED, different cause -- and the cause goes in the
    reason, because `-2011` cannot distinguish never-placed from
    placed-and-since-purged and order retention is unmeasured."""
    client = _StubClient(orders={SL_ID: OrderNotFoundError("Unknown order sent.")})

    ((_p, assessment),) = await resolve_unresolved_legs(
        assessments=[_unresolved(OrderListLeg.STOP_LOSS)],
        client=client,
        max_queries=4,
        now=NOW,
        timeout_s=None,
        attempts=None,
    )

    assert assessment.state is ProtectionState.DIVERGED
    assert "no such order" in assessment.reason
    assert "retention is unmeasured" in assessment.reason


async def test_a_filled_leg_is_refused_rather_than_interpreted() -> None:
    """Consistent with the classifier: the fill path is UNMEASURED, so this
    refuses to read it rather than guessing."""
    client = _StubClient(orders={SL_ID: _queried(OrderStatus.FILLED, filled=QTY)})

    ((_p, assessment),) = await resolve_unresolved_legs(
        assessments=[_unresolved(OrderListLeg.STOP_LOSS)],
        client=client,
        max_queries=4,
        now=NOW,
        timeout_s=None,
        attempts=None,
    )

    assert assessment.state is ProtectionState.UNKNOWN
    assert "unmeasured" in assessment.reason


async def test_a_partially_filled_leg_is_refused_on_the_same_grounds() -> None:
    client = _StubClient(
        orders={SL_ID: _queried(OrderStatus.PARTIALLY_FILLED, filled=Decimal("0.0005"))}
    )

    ((_p, assessment),) = await resolve_unresolved_legs(
        assessments=[_unresolved(OrderListLeg.STOP_LOSS)],
        client=client,
        max_queries=4,
        now=NOW,
        timeout_s=None,
        attempts=None,
    )

    assert assessment.state is ProtectionState.UNKNOWN


@pytest.mark.parametrize("status", [OrderStatus.NEW, OrderStatus.PENDING_NEW])
async def test_a_live_leg_is_an_instrument_disagreement(status: OrderStatus) -> None:
    """Absent from the enumeration and live on a point query. Two views of one
    leg disagree and nothing measured says which to believe, so neither is acted
    on -- the reading whose wrong answer is reversible."""
    client = _StubClient(orders={SL_ID: _queried(status)})

    ((_p, assessment),) = await resolve_unresolved_legs(
        assessments=[_unresolved(OrderListLeg.STOP_LOSS)],
        client=client,
        max_queries=4,
        now=NOW,
        timeout_s=None,
        attempts=None,
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
        now=NOW,
        timeout_s=None,
        attempts=None,
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
        now=NOW,
        timeout_s=None,
        attempts=None,
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
        now=NOW,
        timeout_s=None,
        attempts=None,
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

    refined = await resolve_unresolved_legs(
        assessments=passthrough,
        client=client,
        max_queries=4,
        now=NOW,
        timeout_s=None,
        attempts=None,
    )

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
            assessments=[_unresolved(OrderListLeg.STOP_LOSS)],
            client=client,
            max_queries=4,
            now=NOW,
            timeout_s=None,
            attempts=None,
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
            now=NOW,
            timeout_s=None,
            attempts=None,
        )
        producible.add(assessment.state)
    # The cap path, which returns without querying anything.
    ((_p, capped),) = await resolve_unresolved_legs(
        assessments=[_unresolved(OrderListLeg.STOP_LOSS)],
        client=_StubClient(),
        max_queries=0,
        now=NOW,
        timeout_s=None,
        attempts=None,
    )
    producible.add(capped.state)

    assert producible == {ProtectionState.DIVERGED, ProtectionState.UNKNOWN}
    assert producible & _TRUSTED_PROTECTION == set()


async def test_resolution_stamps_a_position_whose_every_leg_it_queried() -> None:
    """THE COMPLETING HALF of a two-phase reconciliation.

    The pass deliberately withheld the stamp because legs were outstanding.
    Once none are, the position has in fact been reconciled -- in two calls
    rather than one -- and the stamp records that. This is not a re-stamp: the
    superseded objection assumed the pass had already set a dedup clock, and
    for exactly the positions reaching here it has not.

    The verdict is written too, because `DIVERGED` is strictly more informative
    than the `UNKNOWN` absence produced, and both are untrusted -- so no risk
    answer changes, only the report.
    """
    position, assessment = _unresolved(OrderListLeg.STOP_LOSS)
    position.record_partial_reconciliation(protection=ProtectionState.UNKNOWN)
    client = _StubClient(orders={SL_ID: _queried(OrderStatus.CANCELED)})

    await resolve_unresolved_legs(
        assessments=[(position, assessment)],
        client=client,
        max_queries=4,
        now=NOW,
        timeout_s=None,
        attempts=None,
    )

    assert position.protection is ProtectionState.DIVERGED
    assert position.last_reconciled_at == NOW


async def test_resolution_leaves_a_position_with_legs_left_over_unstamped() -> None:
    """The opposite direction, and the one that keeps the scheme live.

    A position still carrying an unqueried leg has NOT been reconciled, so it
    keeps a `None` stamp, sorts first next cycle, and is what the reservation
    funds. Stamping it here would deduplicate it out of the very pass that
    would finish the job.
    """
    position, assessment = _unresolved(OrderListLeg.STOP_LOSS, OrderListLeg.TAKE_PROFIT)
    client = _StubClient(orders={SL_ID: _queried(OrderStatus.CANCELED)})

    await resolve_unresolved_legs(
        assessments=[(position, assessment)],
        client=client,
        max_queries=1,
        now=NOW,
        timeout_s=None,
        attempts=None,
    )

    assert position.last_reconciled_at is None


async def test_unqueried_legs_are_carried_back_rather_than_left_in_the_prose() -> None:
    """ "Every leg was queried" and "the budget ran out" are different facts with
    different consequences -- only the first may stamp. Before this they were
    distinguishable only by reading a sentence, which no caller can act on."""
    client = _StubClient(orders={SL_ID: _queried(OrderStatus.CANCELED)})

    ((_p, assessment),) = await resolve_unresolved_legs(
        assessments=[_unresolved(OrderListLeg.STOP_LOSS, OrderListLeg.TAKE_PROFIT)],
        client=client,
        max_queries=1,
        now=NOW,
        timeout_s=None,
        attempts=None,
    )

    assert [item.leg for item in assessment.unresolved] == [OrderListLeg.TAKE_PROFIT]


async def test_a_fully_queried_position_carries_nothing_back() -> None:
    """The negative of the test above: with budget to spare, nothing is
    outstanding and the tuple is empty -- which is what licenses the stamp."""
    client = _StubClient(
        orders={SL_ID: _queried(OrderStatus.CANCELED), TP_ID: _queried(OrderStatus.CANCELED)}
    )

    ((_p, assessment),) = await resolve_unresolved_legs(
        assessments=[_unresolved(OrderListLeg.STOP_LOSS, OrderListLeg.TAKE_PROFIT)],
        client=client,
        max_queries=4,
        now=NOW,
        timeout_s=None,
        attempts=None,
    )

    assert assessment.unresolved == ()


async def test_the_resolver_forwards_its_per_call_bound_to_the_client() -> None:
    """A point query runs inside the same reserved slot as the enumeration, so
    it takes the same bound. Omitting it inherits the client-wide policy --
    four attempts at the general timeout -- which is tens of seconds inside a
    slot reserved at `reconcile_deadline_s`, and nothing reports that."""
    client = _StubClient(orders={SL_ID: _queried(OrderStatus.CANCELED)})

    await resolve_unresolved_legs(
        assessments=[_unresolved(OrderListLeg.STOP_LOSS)],
        client=client,
        max_queries=4,
        now=NOW,
        timeout_s=3.0,
        attempts=1,
    )

    assert client.query_bounds == [(3.0, 1)]
