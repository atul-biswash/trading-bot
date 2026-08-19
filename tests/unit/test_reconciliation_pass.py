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
from trading_bot.core.exceptions import ContractViolationError
from trading_bot.core.models import Order, Position
from trading_bot.core.portfolio import Portfolio
from trading_bot.exchange.ids import OrderListLeg, client_order_id
from trading_bot.execution.reconciliation import reconcile_open_positions

NOW = datetime(2026, 8, 15, 12, 0, tzinfo=timezone.utc)
BAR = datetime(2026, 8, 15, 11, 0, tzinfo=timezone.utc)
DEDUP = timedelta(minutes=1)
QTY = Decimal("0.00100000")
STOP = Decimal("44117.09")
LIST_ID = "91590"


class _StubClient:
    """Records every symbol it was asked for, in order.

    Only ``get_own_open_orders`` is reachable from the pass; anything else being
    called would be a bug this stub surfaces as an ``AttributeError`` rather
    than silently answering.
    """

    def __init__(self, books: dict[str, list[Order]] | None = None) -> None:
        self.books = books or {}
        self.asked: list[str] = []

    async def get_own_open_orders(self, symbol: str, **_kwargs: Any) -> list[Order]:
        self.asked.append(symbol)
        return self.books.get(symbol, [])


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
    client = _StubClient()

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
    client = _StubClient()

    results = await reconcile_open_positions(
        portfolio=_portfolio(fresh, stale), client=client, now=NOW, dedup_interval=DEDUP
    )

    assert [position.symbol for position, _assessment in results] == client.asked


async def test_a_fresh_stamp_is_not_re_read() -> None:
    """Deduplication: two pairs closing on the same minute pay for one pass."""
    position = _position("BTCUSDT", stamp=NOW - timedelta(seconds=10))
    client = _StubClient()

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
    client = _StubClient()

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
    client = _StubClient()  # nothing rests: the stop is unresolved

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
    client = _StubClient()

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
