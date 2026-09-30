"""What became of each durable record's order list while the bot was down -- PURE.

P-3k's boot classifier, C31 of the owner's P78 rulings. The boot (C32) reads
the venue, hands the answers here, and acts on what comes back; nothing in
this module performs I/O, reads a clock or writes anything. Two calls split
the work around the reads:

* :func:`reads_needed` says which orders to GET -- by the VENUE ``orderId`` of
  each matched list's legs, the owner's Q10(b) -- and which records are
  already refused without a read.
* :func:`classify` returns exactly one decision per record and per pending
  placement, from the lists, the orders read, the balances and the symbol
  filters.

:func:`refuse_disabled` is the owner's R5, separate because it needs nothing
from the venue and runs before any venue call.

**MATCHING IS :func:`~trading_bot.execution.resolution.resolve_placement`'S,
WITH ONE ROW STRICTER.** A record's list is found by the list id we derive
from its seeds, never by a remembered one. Several matches refuse the boot
here even when exactly one is live, where ``resolve_placement`` would answer
``PLACED_LIVE``: the prompt that ordered this module rules "several match" a
refusal outright, and at boot a refusal costs a restart rather than a trade.

**EVERY LEG IS READ, NOT ONLY THE WORKING LEG.** The owner's Q11 refuses the
boot on a partial execution of ANY leg, and a live list's protective leg can
only be seen partly filled by reading it. So a live record costs one GET per
leg, not the one the P77 specification's boot table (S3) listed
(``M5l-123``).

**THE DECISION TABLE**, per matched list. "0 executed" is ``filled_quantity ==
0``; "FILLED" is status ``FILLED`` with ``filled_quantity`` equal to the
record's quantity. Anything not listed refuses the boot.

====================================  ========================================
list and legs                         decision
====================================  ========================================
no list carries our id                record: ``RefuseBoot`` (Q6(a));
                                      pending placement: ``DropNotPlaced``
several carry it                      ``RefuseBoot``
leg ids differ from those we derive   ``RefuseBoot``
a leg was not read                    ``RefuseBoot``
live; working FILLED; protective      ``Restore``
legs NEW or PENDING_NEW, 0 executed
live; working not FILLED              ``RefuseBoot``
ALL_DONE; working EXPIRED, 0          ``DropExpired``
executed; protective EXPIRED, 0
ALL_DONE; working FILLED; one         ``BookExit``
protective FILLED; the other EXPIRED
or CANCELED, 0 executed
ALL_DONE; working FILLED; protective  base total below the ``LOT_SIZE`` step:
all CANCELED, 0 executed              ``Gone``; else base free at least the
                                      quantity: ``RestoreAndClose``; else
                                      ``RefuseBoot`` (Q4(b), Q11)
any leg partly executed               ``RefuseBoot`` (Q11)
====================================  ========================================

**A PENDING PLACEMENT TAKES THE SAME TABLE** (the owner's Q3(a)), except that
no match means it never placed. A terminal list whose working leg FILLED is
therefore a ``BookExit`` or its siblings, never a drop -- which is
``M5l-104``: ``resolve_placement`` answers ``PLACED_TERMINAL`` for it without
reading the working leg. Pending CLOSE records are not classified here; Site B
resolves them on the first candle (the owner's Q13).

**TWO BASE FIGURES, AND THE DIFFERENCE IS DELIBERATE (``M5l-122``).** ``Gone``
reads the base's TOTAL, so base locked by some other order is never mistaken
for base that left. ``RestoreAndClose`` reads the FREE base, because it
implies a sell of ``quantity``, and base that is locked cannot be sold. Base
that is held but not free enough refuses.

**ONLY :class:`RestoreAndClose` IMPLIES A VENUE WRITE**, R3's market sell. It
is the one class whose ``writes_to_venue`` is true, so a caller can refuse to
act on the flag rather than on a remembered class name.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import TYPE_CHECKING, ClassVar, Protocol

from trading_bot.core.enums import OrderStatus
from trading_bot.exchange.ids import OrderListLeg, client_order_id, list_client_order_id

if TYPE_CHECKING:
    from collections.abc import Collection, Iterable, Mapping, Sequence
    from datetime import datetime

    from trading_bot.core.models import Balance, Order, OrderList, SymbolInfo

__all__ = [
    "DECISION_TYPES",
    "BookExit",
    "Decision",
    "DropExpired",
    "DropNotPlaced",
    "Gone",
    "ReadPlan",
    "RefuseBoot",
    "Requested",
    "Restore",
    "RestoreAndClose",
    "classify",
    "reads_needed",
    "refuse_disabled",
]

#: `list_order_status` values that mean a list is still working. The same set
#: as `resolution._LIVE_STATUSES`, and a test pins that the two agree.
_LIVE_STATUSES = frozenset({"EXECUTING", "EXEC_STARTED"})
#: A terminal list. MEASURED 2026-08-21 on six expired FOK lists.
_DONE_STATUS = "ALL_DONE"
_PROTECTIVE = (OrderListLeg.STOP_LOSS, OrderListLeg.TAKE_PROFIT)
#: A protective leg of a live list that has not triggered.
_RESTING = frozenset({OrderStatus.NEW, OrderStatus.PENDING_NEW})


class Requested(Protocol):
    """What a record REQUESTED, which is all this module reads of it.

    A protocol rather than a type, so the store's ``PositionRecord`` and the
    executor's ``PendingPlacement`` both satisfy it without this module
    importing either: ``execution/`` imports no store, and this module imports
    nothing ``resolution.py``'s own imports do not already reach.
    """

    @property
    def symbol(self) -> str: ...

    @property
    def entry_bar_time(self) -> datetime: ...

    @property
    def generation(self) -> int: ...

    @property
    def quantity(self) -> Decimal: ...

    @property
    def stop_loss(self) -> Decimal | None: ...

    @property
    def take_profit(self) -> Decimal | None: ...


@dataclass(frozen=True, slots=True)
class Restore:
    """A live list whose working leg FILLED: restore the position, UNKNOWN, no debit.

    The entry economics come from the working leg (the owner's R2): its
    ``average_price`` and its ``filled_quote_quantity``, either of which the
    venue may omit. ``order_list`` is the one list matched, carried so the
    caller need not match again.
    """

    writes_to_venue: ClassVar[bool] = False
    record: Requested
    order_list: OrderList
    entry_fill_price: Decimal | None
    entry_quote_total: Decimal | None


@dataclass(frozen=True, slots=True)
class BookExit:
    """A protective leg FILLED while the bot was down: book it, ledger only.

    ``leg`` and ``order_id`` name the filled leg, whose fills settle the exit.
    The entry economics are carried as :class:`Restore` carries them, because
    booking the exit needs the cost basis and the classifier already read it.
    """

    writes_to_venue: ClassVar[bool] = False
    record: Requested
    order_list: OrderList
    leg: OrderListLeg
    order_id: str
    entry_fill_price: Decimal | None
    entry_quote_total: Decimal | None


@dataclass(frozen=True, slots=True)
class RestoreAndClose:
    """Protection is gone and the base is held: restore, then SELL it (R3, Q4(b)).

    **THE ONLY DECISION THAT IMPLIES A VENUE WRITE.** ``base_free`` is the
    free base this was decided on, at least the record's quantity.
    """

    writes_to_venue: ClassVar[bool] = True
    record: Requested
    order_list: OrderList
    entry_fill_price: Decimal | None
    entry_quote_total: Decimal | None
    base_free: Decimal


@dataclass(frozen=True, slots=True)
class Gone:
    """Protection is gone and so is the base: nothing to restore, nothing to sell.

    Dropped unbooked. Who sold it is not searched for: the owner's R6 forbids a
    query made to search for an explanation.
    """

    writes_to_venue: ClassVar[bool] = False
    record: Requested
    order_list: OrderList


@dataclass(frozen=True, slots=True)
class DropExpired:
    """The entry's FOK expired with nothing executed: nothing happened."""

    writes_to_venue: ClassVar[bool] = False
    record: Requested
    order_list: OrderList


@dataclass(frozen=True, slots=True)
class DropNotPlaced:
    """A pending placement no list carries: it never reached the venue."""

    writes_to_venue: ClassVar[bool] = False
    record: Requested


@dataclass(frozen=True, slots=True)
class RefuseBoot:
    """Anything the table does not name. ``reason`` names the symbol, our list id
    and the shape seen."""

    writes_to_venue: ClassVar[bool] = False
    record: Requested
    reason: str


Decision = Restore | BookExit | RestoreAndClose | Gone | DropExpired | DropNotPlaced | RefuseBoot
#: Every decision class, for a caller or a test that must enumerate them.
DECISION_TYPES: tuple[type[Decision], ...] = (
    Restore,
    BookExit,
    RestoreAndClose,
    Gone,
    DropExpired,
    DropNotPlaced,
    RefuseBoot,
)


@dataclass(frozen=True, slots=True)
class ReadPlan:
    """The venue order ids to GET, and the refusals already decided."""

    order_ids: tuple[str, ...]
    refusals: tuple[RefuseBoot, ...]


def refuse_disabled(
    records: Iterable[Requested], enabled_symbols: Collection[str]
) -> tuple[RefuseBoot, ...]:
    """The owner's R5: a record on a pair that is not enabled refuses the boot.

    Needs no venue answer, so the boot calls it before any venue call.
    """
    return tuple(
        _refuse(record, "its pair is not enabled")
        for record in records
        if record.symbol not in enabled_symbols
    )


def reads_needed(
    records: Sequence[Requested],
    pending_placements: Sequence[Requested],
    order_lists: Sequence[OrderList],
) -> ReadPlan:
    """The orders :func:`classify` needs, and the refusals it will make without them.

    One GET per leg of each list that exactly one record or pending placement
    matches, by the leg's venue ``orderId`` (Q10(b)), each id once, in input
    order. A pending placement that matches nothing needs no read and is not a
    refusal.
    """
    order_ids: list[str] = []
    refusals: list[RefuseBoot] = []
    for record, pending in [(r, False) for r in records] + [(p, True) for p in pending_placements]:
        found = _match(record, order_lists, pending=pending)
        if isinstance(found, RefuseBoot):
            refusals.append(found)
        elif isinstance(found, _Matched):
            order_ids.extend(i for i in found.leg_order_ids.values() if i not in order_ids)
    return ReadPlan(order_ids=tuple(order_ids), refusals=tuple(refusals))


def classify(
    records: Sequence[Requested],
    pending_placements: Sequence[Requested],
    order_lists: Sequence[OrderList],
    orders: Iterable[Order],
    balances: Iterable[Balance],
    filters: Mapping[str, SymbolInfo],
) -> tuple[Decision, ...]:
    """Exactly one decision per record, then one per pending placement, in input order.

    ``orders`` are the answers to :func:`reads_needed`'s GETs, found by
    ``order_id``. ``balances`` is the boot's one ``get_balances`` read; an asset
    it does not list holds zero. ``filters`` maps a symbol to its
    ``SymbolInfo``, whose ``step_size`` is the ``LOT_SIZE`` step.
    """
    by_id = {order.order_id: order for order in orders}
    held = {balance.asset: balance for balance in balances}
    decisions: list[Decision] = [
        _decide(record, order_lists, by_id, held, filters, pending=False) for record in records
    ]
    for pending in pending_placements:
        decisions.append(_decide(pending, order_lists, by_id, held, filters, pending=True))
    return tuple(decisions)


# -- internals ---------------------------------------------------------------
@dataclass(frozen=True, slots=True)
class _Matched:
    order_list: OrderList
    leg_order_ids: dict[OrderListLeg, str]


def _list_id(record: Requested) -> str:
    return list_client_order_id(record.symbol, record.entry_bar_time, generation=record.generation)


def _refuse(record: Requested, shape: str) -> RefuseBoot:
    return RefuseBoot(
        record=record, reason=f"{record.symbol}, order list {_list_id(record)}: {shape}"
    )


def _expected_legs(record: Requested) -> dict[OrderListLeg, str]:
    """Our leg client ids for the list the record's seeds derive, by leg."""
    legs = [OrderListLeg.WORKING]
    if record.stop_loss is not None:
        legs.append(OrderListLeg.STOP_LOSS)
    if record.take_profit is not None:
        legs.append(OrderListLeg.TAKE_PROFIT)
    return {
        leg: client_order_id(
            record.symbol, record.entry_bar_time, leg, generation=record.generation
        )
        for leg in legs
    }


def _match(
    record: Requested, order_lists: Sequence[OrderList], *, pending: bool
) -> _Matched | RefuseBoot | DropNotPlaced:
    """Find the record's list and its legs, or decide without a read."""
    wanted = _list_id(record)
    matched = [ol for ol in order_lists if ol.list_client_order_id == wanted]
    if not matched:
        if pending:
            return DropNotPlaced(record=record)
        return _refuse(record, "no order list on the account carries this id")
    if len(matched) > 1:
        return _refuse(
            record,
            f"{len(matched)} order lists carry this id "
            f"({', '.join(ol.order_list_id for ol in matched)}), and none may be chosen",
        )
    only = matched[0]
    expected = _expected_legs(record)
    by_client_id = {entry.client_order_id: entry.order_id for entry in only.orders}
    if sorted(by_client_id) != sorted(expected.values()) or len(only.orders) != len(expected):
        return _refuse(
            record,
            f"list {only.order_list_id} holds legs {sorted(by_client_id)}, "
            f"not the {len(expected)} this record derives",
        )
    return _Matched(
        order_list=only,
        leg_order_ids={leg: by_client_id[client_id] for leg, client_id in expected.items()},
    )


def _filled(order: Order, quantity: Decimal) -> bool:
    """FILLED, and for exactly the quantity requested."""
    return order.status is OrderStatus.FILLED and order.filled_quantity == quantity


def _unexecuted(order: Order) -> bool:
    return order.filled_quantity == 0


def _shape(order_list: OrderList, legs: Mapping[OrderListLeg, Order]) -> str:
    parts = ", ".join(
        f"{leg.value} {order.status.value} {order.filled_quantity}/{order.quantity}"
        for leg, order in legs.items()
    )
    return f"list {order_list.order_list_id} {order_list.list_order_status}: {parts}"


def _decide(
    record: Requested,
    order_lists: Sequence[OrderList],
    orders: Mapping[str, Order],
    balances: Mapping[str, Balance],
    filters: Mapping[str, SymbolInfo],
    *,
    pending: bool,
) -> Decision:
    found = _match(record, order_lists, pending=pending)
    if not isinstance(found, _Matched):
        return found
    order_list = found.order_list
    legs: dict[OrderListLeg, Order] = {}
    for leg, order_id in found.leg_order_ids.items():
        order = orders.get(order_id)
        if order is None:
            return _refuse(record, f"leg {leg.value} (order {order_id}) was not read")
        legs[leg] = order
    working = legs[OrderListLeg.WORKING]
    protective = [legs[leg] for leg in _PROTECTIVE if leg in legs]
    quantity = record.quantity
    shape = _shape(order_list, legs)

    if any(order.quantity != quantity for order in legs.values()):
        return _refuse(record, f"a leg's quantity is not {quantity}; {shape}")

    status = order_list.list_order_status or ""
    if status in _LIVE_STATUSES:
        if _filled(working, quantity) and all(
            order.status in _RESTING and _unexecuted(order) for order in protective
        ):
            return Restore(
                record=record,
                order_list=order_list,
                entry_fill_price=working.average_price,
                entry_quote_total=working.filled_quote_quantity,
            )
    elif status == _DONE_STATUS:
        if (
            working.status is OrderStatus.EXPIRED
            and _unexecuted(working)
            and all(
                order.status is OrderStatus.EXPIRED and _unexecuted(order) for order in protective
            )
        ):
            return DropExpired(record=record, order_list=order_list)
        if _filled(working, quantity) and protective:
            exits = [leg for leg in _PROTECTIVE if leg in legs and _filled(legs[leg], quantity)]
            others = [legs[leg] for leg in _PROTECTIVE if leg in legs and leg not in exits]
            if len(exits) == 1 and all(
                order.status in (OrderStatus.EXPIRED, OrderStatus.CANCELED) and _unexecuted(order)
                for order in others
            ):
                return BookExit(
                    record=record,
                    order_list=order_list,
                    leg=exits[0],
                    order_id=legs[exits[0]].order_id,
                    entry_fill_price=working.average_price,
                    entry_quote_total=working.filled_quote_quantity,
                )
            if all(
                order.status is OrderStatus.CANCELED and _unexecuted(order) for order in protective
            ):
                return _unprotected(record, order_list, working, balances, filters, shape)

    if any(0 < order.filled_quantity < order.quantity for order in legs.values()):
        return _refuse(record, f"a leg is partly executed; {shape}")
    if status in _LIVE_STATUSES and not _filled(working, quantity):
        return _refuse(record, f"the list is live and its working leg is not FILLED; {shape}")
    return _refuse(record, f"no decision covers this shape; {shape}")


def _unprotected(
    record: Requested,
    order_list: OrderList,
    working: Order,
    balances: Mapping[str, Balance],
    filters: Mapping[str, SymbolInfo],
    shape: str,
) -> Decision:
    """Both protective legs cancelled unexecuted: what the base says (R3, Q4(b))."""
    info = filters.get(record.symbol)
    if info is None:
        return _refuse(record, f"no symbol filters to judge the base against; {shape}")
    balance = balances.get(info.base_asset)
    total = balance.total if balance is not None else Decimal(0)
    free = balance.free if balance is not None else Decimal(0)
    if total < info.step_size:
        return Gone(record=record, order_list=order_list)
    if free >= record.quantity:
        return RestoreAndClose(
            record=record,
            order_list=order_list,
            entry_fill_price=working.average_price,
            entry_quote_total=working.filled_quote_quantity,
            base_free=free,
        )
    return _refuse(
        record,
        f"{info.base_asset} total {total}, free {free}: held, but below the quantity "
        f"{record.quantity}; {shape}",
    )
