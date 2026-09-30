"""The pure boot classifier, C31 of P-3k: one decision per record, and why.

Every test drives ``classify`` or ``reads_needed`` with the real record types --
the store's ``PositionRecord`` and the executor's ``PendingPlacement`` -- so the
``Requested`` protocol is exercised by what the boot will actually pass.

The quantity is ``0.02310000`` and the ``LOT_SIZE`` step ``0.00001000``, so the
three base bands -- below the step, from the step to below the quantity, and at
least the quantity -- are each wide enough to hold a fixture with room on both
sides. A partial fill is ``0.01000000``, strictly inside ``(0, quantity)``.
"""

from __future__ import annotations

import itertools
from datetime import datetime, timezone
from decimal import Decimal

from trading_bot.core.enums import OrderSide, OrderStatus, OrderType
from trading_bot.core.models import Balance, Order, OrderList, OrderListEntry, SymbolInfo
from trading_bot.exchange.ids import OrderListLeg, client_order_id, list_client_order_id
from trading_bot.execution import resolution, restoration
from trading_bot.execution.executor import PendingPlacement
from trading_bot.execution.restoration import (
    DECISION_TYPES,
    BookExit,
    Decision,
    DropExpired,
    DropNotPlaced,
    Gone,
    RefuseBoot,
    Restore,
    RestoreAndClose,
    classify,
    reads_needed,
    refuse_disabled,
)
from trading_bot.persistence.store import PositionRecord

D = Decimal

SYMBOL = "BTCUSDT"
OTHER = "ETHUSDT"
BAR = datetime(2026, 9, 20, 10, 0, tzinfo=timezone.utc)
QTY = D("0.02310000")
STEP = D("0.00001000")
PART = D("0.01000000")
ZERO = D("0")
FILL = D("60100.12000000")
QUOTE = D("1388.3127720000")
W, SL, TP = OrderListLeg.WORKING, OrderListLeg.STOP_LOSS, OrderListLeg.TAKE_PROFIT

FILTERS = {
    symbol: SymbolInfo(
        symbol=symbol,
        base_asset=symbol.removesuffix("USDT"),
        quote_asset="USDT",
        price_tick=D("0.01"),
        step_size=STEP,
        min_qty=STEP,
        min_notional=D("5"),
    )
    for symbol in (SYMBOL, OTHER)
}

_TYPES = {W: OrderType.LIMIT, SL: OrderType.STOP_LOSS, TP: OrderType.TAKE_PROFIT}


def record(symbol: str = SYMBOL, *, take_profit: bool = True) -> PositionRecord:
    return PositionRecord(
        kind="position",
        symbol=symbol,
        entry_bar_time=BAR,
        generation=0,
        quantity=QTY,
        entry_limit=D("60123.45000000"),
        stop_loss=D("58000.00000000"),
        take_profit=D("63000.00000000") if take_profit else None,
    )


def pending(symbol: str = SYMBOL, *, take_profit: bool = True) -> PendingPlacement:
    return PendingPlacement(
        symbol=symbol,
        entry_bar_time=BAR,
        generation=0,
        quantity=QTY,
        entry_limit=D("60123.45000000"),
        stop_loss=D("58000.00000000"),
        take_profit=D("63000.00000000") if take_profit else None,
    )


def venue_id(symbol: str, leg: OrderListLeg, list_tag: str = "") -> str:
    return f"{symbol}-{leg.value}{list_tag}"


def order_list(
    symbol: str = SYMBOL,
    status: str | None = "ALL_DONE",
    *,
    legs: tuple[OrderListLeg, ...] = (W, SL, TP),
    list_tag: str = "",
    client_ids: dict[OrderListLeg, str] | None = None,
) -> OrderList:
    """Our list for ``symbol``, carrying our derived list and leg ids."""
    ids = client_ids or {leg: client_order_id(symbol, BAR, leg) for leg in legs}
    return OrderList(
        order_list_id=f"4242{list_tag}",
        symbol=symbol,
        list_client_order_id=list_client_order_id(symbol, BAR),
        list_status_type="ALL_DONE" if status == "ALL_DONE" else "EXEC_STARTED",
        list_order_status=status,
        orders=tuple(
            OrderListEntry(
                symbol=symbol,
                order_id=venue_id(symbol, leg, list_tag),
                client_order_id=ids[leg],
            )
            for leg in legs
        ),
    )


def leg(
    which: OrderListLeg,
    status: OrderStatus,
    filled: Decimal = ZERO,
    *,
    symbol: str = SYMBOL,
    list_tag: str = "",
) -> Order:
    """One leg as ``get_order`` returns it. A FILLED working leg carries its price."""
    priced = which is W and filled > 0
    return Order(
        order_id=venue_id(symbol, which, list_tag),
        symbol=symbol,
        side=OrderSide.BUY if which is W else OrderSide.SELL,
        type=_TYPES[which],
        status=status,
        quantity=QTY,
        filled_quantity=filled,
        average_price=FILL if priced else None,
        filled_quote_quantity=QUOTE if priced else None,
        client_order_id=client_order_id(symbol, BAR, which),
    )


def base(free: Decimal, locked: Decimal = ZERO, asset: str = "BTC") -> list[Balance]:
    return [Balance(asset=asset, free=free, locked=locked)]


def one(decisions: tuple[Decision, ...]) -> Decision:
    """Length first, then the index -- a missing decision fails as an assertion."""
    assert len(decisions) == 1, decisions
    return decisions[0]


def decide(
    orders: list[Order],
    *,
    lists: list[OrderList] | None = None,
    balances: list[Balance] | None = None,
    subject: PositionRecord | None = None,
) -> Decision:
    """Classify one position record against one list of ours."""
    return one(
        classify(
            [subject or record()],
            [],
            [order_list()] if lists is None else lists,
            orders,
            balances or [],
            FILTERS,
        )
    )


_FILLED_W = leg(W, OrderStatus.FILLED, QTY)
_CANCELLED = [leg(SL, OrderStatus.CANCELED), leg(TP, OrderStatus.CANCELED)]


class TestDecisions:
    """One test per decision the table names."""

    def test_a_live_list_with_a_filled_entry_restores_with_the_legs_economics(self) -> None:
        """R2: the fill price and quote total are the working leg's, never the request's."""
        decision = decide(
            [_FILLED_W, leg(SL, OrderStatus.NEW), leg(TP, OrderStatus.PENDING_NEW)],
            lists=[order_list(status="EXECUTING")],
        )

        assert isinstance(decision, Restore)
        assert decision.entry_fill_price == FILL
        assert decision.entry_quote_total == QUOTE
        assert decision.order_list.order_list_id == "4242"

    def test_a_stop_that_filled_while_down_is_booked(self) -> None:
        decision = decide(
            [_FILLED_W, leg(SL, OrderStatus.FILLED, QTY), leg(TP, OrderStatus.EXPIRED)]
        )

        assert isinstance(decision, BookExit)
        assert decision.leg is SL
        assert decision.order_id == venue_id(SYMBOL, SL)
        assert decision.entry_fill_price == FILL

    def test_a_take_profit_that_filled_while_down_is_booked(self) -> None:
        """The other leg CANCELED rather than EXPIRED is admitted too."""
        decision = decide(
            [_FILLED_W, leg(SL, OrderStatus.CANCELED), leg(TP, OrderStatus.FILLED, QTY)]
        )

        assert isinstance(decision, BookExit)
        assert decision.leg is TP
        assert decision.order_id == venue_id(SYMBOL, TP)

    def test_cancelled_protection_with_the_base_free_restores_and_closes(self) -> None:
        """R3 and Q4(b): free base at least the quantity."""
        decision = decide([_FILLED_W, *_CANCELLED], balances=base(QTY))

        assert isinstance(decision, RestoreAndClose)
        assert decision.base_free == QTY
        assert decision.entry_fill_price == FILL

    def test_cancelled_protection_with_no_base_is_gone(self) -> None:
        """An asset the balances do not list holds zero."""
        decision = decide([_FILLED_W, *_CANCELLED], balances=[])

        assert isinstance(decision, Gone)

    def test_an_expired_entry_drops(self) -> None:
        decision = decide(
            [
                leg(W, OrderStatus.EXPIRED),
                leg(SL, OrderStatus.EXPIRED),
                leg(TP, OrderStatus.EXPIRED),
            ]
        )

        assert isinstance(decision, DropExpired)


class TestTheBaseBands:
    """Below the step is gone; from the step to below the quantity refuses."""

    def test_the_gone_boundary_base_exactly_at_the_step_refuses(self) -> None:
        """At the step is held: not gone, and not enough to sell."""
        decision = decide([_FILLED_W, *_CANCELLED], balances=base(STEP))

        assert isinstance(decision, RefuseBoot)
        assert "below the quantity" in decision.reason

    def test_base_held_below_the_quantity_refuses(self) -> None:
        """Q4(b) and Q11. MUTATION: RestoreAndClose when base < quantity."""
        decision = decide([_FILLED_W, *_CANCELLED], balances=base(PART))

        assert isinstance(decision, RefuseBoot)
        assert "below the quantity" in decision.reason

    def test_base_that_is_locked_is_neither_gone_nor_sold(self) -> None:
        """M5l-122: gone reads the TOTAL, the sell reads what is FREE."""
        decision = decide([_FILLED_W, *_CANCELLED], balances=base(D("0"), locked=QTY))

        assert isinstance(decision, RefuseBoot)
        assert "free 0" in decision.reason


class TestRefusals:
    """One test per refusal reason, each asserting the reason names its shape."""

    def test_no_list_carrying_our_id_refuses(self) -> None:
        """Q6(a)."""
        decision = decide([], lists=[])

        assert isinstance(decision, RefuseBoot)
        assert "no order list" in decision.reason

    def test_several_lists_carrying_our_id_refuse(self) -> None:
        """MUTATION: pick the first. The first list is a clean live one, so a
        classifier that picked it would Restore rather than refuse."""
        lists = [order_list(status="EXECUTING"), order_list(list_tag="b")]
        orders = [
            _FILLED_W,
            leg(SL, OrderStatus.NEW),
            leg(TP, OrderStatus.NEW),
            leg(W, OrderStatus.EXPIRED, list_tag="b"),
            leg(SL, OrderStatus.EXPIRED, list_tag="b"),
            leg(TP, OrderStatus.EXPIRED, list_tag="b"),
        ]

        decision = decide(orders, lists=lists)

        assert isinstance(decision, RefuseBoot)
        assert "2 order lists" in decision.reason

    def test_a_partly_executed_protective_leg_refuses(self) -> None:
        """Q11. MUTATION: BookExit accepts a partly executed leg."""
        decision = decide(
            [_FILLED_W, leg(SL, OrderStatus.PARTIALLY_FILLED, PART), leg(TP, OrderStatus.EXPIRED)]
        )

        assert isinstance(decision, RefuseBoot)
        assert "partly executed" in decision.reason

    def test_an_expired_entry_that_executed_refuses(self) -> None:
        """Q11. MUTATION: DropExpired accepts working EXPIRED with executed > 0."""
        decision = decide(
            [
                leg(W, OrderStatus.EXPIRED, PART),
                leg(SL, OrderStatus.EXPIRED),
                leg(TP, OrderStatus.EXPIRED),
            ]
        )

        assert isinstance(decision, RefuseBoot)
        assert "partly executed" in decision.reason

    def test_a_live_list_whose_entry_is_not_filled_refuses(self) -> None:
        decision = decide(
            [leg(W, OrderStatus.NEW), leg(SL, OrderStatus.PENDING_NEW), leg(TP, OrderStatus.NEW)],
            lists=[order_list(status="EXECUTING")],
        )

        assert isinstance(decision, RefuseBoot)
        assert "working leg is not FILLED" in decision.reason

    def test_a_combination_the_table_does_not_name_refuses(self) -> None:
        """Both protective legs FILLED: not one exit, and not cancelled."""
        decision = decide(
            [_FILLED_W, leg(SL, OrderStatus.FILLED, QTY), leg(TP, OrderStatus.FILLED, QTY)]
        )

        assert isinstance(decision, RefuseBoot)
        assert "no decision covers this shape" in decision.reason

    def test_legs_other_than_ours_refuse(self) -> None:
        foreign = {W: client_order_id(SYMBOL, BAR, W), SL: "someone-else", TP: "another"}

        decision = decide([], lists=[order_list(client_ids=foreign)])

        assert isinstance(decision, RefuseBoot)
        assert "holds legs" in decision.reason

    def test_a_leg_that_was_not_read_refuses(self) -> None:
        decision = decide([_FILLED_W, leg(SL, OrderStatus.FILLED, QTY)])

        assert isinstance(decision, RefuseBoot)
        assert "was not read" in decision.reason

    def test_the_reason_names_the_symbol_our_list_id_and_the_shape(self) -> None:
        decision = decide(
            [_FILLED_W, leg(SL, OrderStatus.FILLED, QTY), leg(TP, OrderStatus.FILLED, QTY)]
        )

        assert isinstance(decision, RefuseBoot)
        assert SYMBOL in decision.reason
        assert list_client_order_id(SYMBOL, BAR) in decision.reason
        assert "SL FILLED 0.02310000/0.02310000" in decision.reason


class TestPendingPlacements:
    """Q3(a): the same table, except that no match means it never placed."""

    def test_a_pending_placement_no_list_carries_never_placed(self) -> None:
        """MUTATION: omit a decision for one record -- this one."""
        decisions = classify([], [pending()], [], [], [], FILTERS)

        decision = one(decisions)
        assert isinstance(decision, DropNotPlaced)

    def test_a_pending_placement_on_a_live_list_restores(self) -> None:
        decisions = classify(
            [],
            [pending()],
            [order_list(status="EXECUTING")],
            [_FILLED_W, leg(SL, OrderStatus.NEW), leg(TP, OrderStatus.NEW)],
            [],
            FILTERS,
        )

        assert isinstance(one(decisions), Restore)

    def test_m5l_104_an_entry_that_filled_and_exited_while_down_is_booked(self) -> None:
        """M5l-104: a TERMINAL list is not proof the FOK expired. MUTATION: treat
        a terminal list whose working leg FILLED as DropExpired."""
        decisions = classify(
            [],
            [pending()],
            [order_list()],
            [_FILLED_W, leg(SL, OrderStatus.FILLED, QTY), leg(TP, OrderStatus.EXPIRED)],
            [],
            FILTERS,
        )

        decision = one(decisions)
        assert isinstance(decision, BookExit)
        assert decision.leg is SL

    def test_a_pending_placement_whose_fok_expired_drops(self) -> None:
        decisions = classify(
            [],
            [pending()],
            [order_list()],
            [
                leg(W, OrderStatus.EXPIRED),
                leg(SL, OrderStatus.EXPIRED),
                leg(TP, OrderStatus.EXPIRED),
            ],
            [],
            FILTERS,
        )

        assert isinstance(one(decisions), DropExpired)


class TestRefuseDisabled:
    def test_every_record_off_the_enabled_pairs_is_refused_in_order(self) -> None:
        """R5. MUTATION: ignore a record. Two are disabled, so skipping either
        one -- the first or the last -- changes the answer."""
        eth, sol, btc = record(OTHER), record("SOLUSDT"), record()

        refusals = refuse_disabled([eth, btc, sol], {SYMBOL})

        assert [r.record for r in refusals] == [eth, sol]
        assert all("not enabled" in r.reason for r in refusals)
        assert list_client_order_id(OTHER, BAR) in refusals[0].reason


class TestReadsNeeded:
    def test_every_leg_of_each_single_match_is_read_by_venue_id(self) -> None:
        """Q10(b): by orderId, one GET per leg, each once, in input order."""
        plan = reads_needed(
            [record()],
            [pending(OTHER, take_profit=False)],
            [order_list(), order_list(OTHER, legs=(W, SL))],
        )

        assert plan.order_ids == (
            venue_id(SYMBOL, W),
            venue_id(SYMBOL, SL),
            venue_id(SYMBOL, TP),
            venue_id(OTHER, W),
            venue_id(OTHER, SL),
        )
        assert plan.refusals == ()

    def test_the_refusals_decidable_without_a_read_are_returned(self) -> None:
        """No match and several matches refuse; a pending with no match does not."""
        missing, doubled = record(), record(OTHER)

        plan = reads_needed(
            [missing, doubled],
            [pending("SOLUSDT")],
            [order_list(OTHER), order_list(OTHER, list_tag="b")],
        )

        assert plan.order_ids == ()
        assert [r.record for r in plan.refusals] == [missing, doubled]


class TestExactlyOneDecision:
    def test_every_input_gets_exactly_one_decision_in_input_order(self) -> None:
        """Records first, then pending placements, each object exactly once.

        MUTATION: omit a decision for one record. DECLARED: this pins count and
        identity, not which decision -- the tests above pin that.
        """
        records = [record(), record(OTHER), record("SOLUSDT")]
        pendings = [pending("XRPUSDT"), pending("ADAUSDT")]
        lists = [order_list(), order_list("ADAUSDT", status="EXECUTING")]
        orders = [
            _FILLED_W,
            leg(SL, OrderStatus.FILLED, QTY),
            leg(TP, OrderStatus.EXPIRED),
            leg(W, OrderStatus.FILLED, QTY, symbol="ADAUSDT"),
            leg(SL, OrderStatus.NEW, symbol="ADAUSDT"),
            leg(TP, OrderStatus.NEW, symbol="ADAUSDT"),
        ]

        decisions = classify(records, pendings, lists, orders, [], FILTERS)

        assert len(decisions) == len(records) + len(pendings)
        assert all(
            d.record is expected
            for d, expected in zip(decisions, [*records, *pendings], strict=True)
        )

    def test_one_decision_for_every_leg_state_the_venue_can_report(self) -> None:
        """A sweep: list status by each leg's (status, executed), 4 x 6^3 = 864
        shapes, and every one yields exactly one decision naming its record."""
        states = [
            (OrderStatus.NEW, D("0")),
            (OrderStatus.FILLED, QTY),
            (OrderStatus.CANCELED, D("0")),
            (OrderStatus.EXPIRED, D("0")),
            (OrderStatus.PARTIALLY_FILLED, PART),
            (OrderStatus.EXPIRED, PART),
        ]
        shapes = 0
        for status, w, s, t in itertools.product(
            ("EXECUTING", "ALL_DONE", "REJECT", None), states, states, states
        ):
            subject = record()
            orders = [leg(W, *w), leg(SL, *s), leg(TP, *t)]

            decisions = classify(
                [subject], [], [order_list(status=status)], orders, base(QTY), FILTERS
            )

            assert len(decisions) == 1
            assert decisions[0].record is subject
            shapes += 1
        assert shapes == 864


class TestTheWriteFlag:
    def test_only_restore_and_close_writes_to_the_venue(self) -> None:
        assert [t for t in DECISION_TYPES if t.writes_to_venue] == [RestoreAndClose]
        assert len(DECISION_TYPES) == 7


def test_the_live_statuses_agree_with_resolution() -> None:
    """One criterion for "live" in two modules: the classifier's must not drift
    from ``resolve_placement``'s."""
    assert restoration._LIVE_STATUSES == resolution._LIVE_STATUSES
