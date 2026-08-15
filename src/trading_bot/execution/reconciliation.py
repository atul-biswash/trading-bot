"""Classify a position's protection from what rests at the venue.

Pure. No I/O, no config, no clock, no ``Position`` -- the caller supplies the
requested levels and the legs it has already read, and receives a frozen
verdict carrying its reason. Driving this from the candle subscription, and
performing the queries it asks for, belong to whoever owns the reconciler.

**Keyed off what was REQUESTED, never off what is absent.** Divergence is
"protection was requested and does not rest", not "no legs are resting" -- so a
position with nothing requested is not diverged, and a requested leg that has
vanished is not diverged either. It is *unresolved*, which is a different
answer and a weaker one.

**Why this module rather than ``core/``.** The compare set carries
:class:`~trading_bot.exchange.ids.ClientOrderIdParts`, and ``core/`` may not
import an outer layer. It is also not risk policy: nothing here decides what to
do about a verdict, only what the verdict is.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict

from trading_bot.core.enums import OrderStatus, ProtectionState
from trading_bot.core.models import Order
from trading_bot.exchange.ids import ClientOrderIdParts, OrderListLeg, client_order_id

__all__ = ["ProtectionAssessment", "UnresolvedLeg", "classify_protection"]


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True)


class UnresolvedLeg(_Frozen):
    """A requested leg that is absent from the compare set, and how to resolve it.

    **Absence is not an answer.** A leg missing from ``get_open_orders`` may
    never have been placed, may have been cancelled, or may have filled, and
    MEASURED at M5e: after a cancel the enumeration returned ``[]`` while a
    point query by ``origClientOrderId`` still reported ``CANCELED``. The two
    endpoints are different instruments and only the second separates those
    cases.

    So this names the query rather than guessing its result. The identifier is
    derived by pure computation from the same seeds that generated it, which is
    what makes a classifier able to say "ask about *this*" without any I/O.
    """

    leg: OrderListLeg
    client_order_id: str


class ProtectionAssessment(_Frozen):
    """What is known about one position's protection, and why.

    A verdict is a **value carrying its reason**, never an exception and never a
    bare enum: "the stop rests one tick low" and "the stop is not there at all"
    are different facts that would otherwise arrive as the same word.

    ``unresolved`` is non-empty only for :attr:`ProtectionState.UNKNOWN` reached
    through absence, and it is the caller's work list.
    """

    state: ProtectionState
    reason: str
    unresolved: tuple[UnresolvedLeg, ...] = ()


def _requested(
    stop_loss: Decimal | None, take_profit: Decimal | None
) -> dict[OrderListLeg, Decimal]:
    """The protective legs that were asked for, by leg code.

    The working leg is deliberately absent: it is the entry, not protection, and
    it is *expected* to leave the book when it fills.
    """
    asked: dict[OrderListLeg, Decimal] = {}
    if stop_loss is not None:
        asked[OrderListLeg.STOP_LOSS] = stop_loss
    if take_profit is not None:
        asked[OrderListLeg.TAKE_PROFIT] = take_profit
    return asked


def classify_protection(
    *,
    symbol: str,
    entry_bar_time: datetime,
    generation: int,
    quantity: Decimal,
    order_list_id: str | None,
    stop_loss: Decimal | None,
    take_profit: Decimal | None,
    resting: Sequence[tuple[ClientOrderIdParts, Order]],
) -> ProtectionAssessment:
    """Compare requested protection against what rests, and say what is known.

    ``resting`` is the symbol's own ``tb1-`` compare set. Legs belonging to
    another bar or another generation are ignored here rather than filtered by
    the caller, so a caller reading one symbol cannot accidentally attribute a
    neighbouring position's legs to this one.

    **The compared set, and its two deliberate exclusions.** Existence, status,
    ``executedQty``, ``origQty``, ``orderListId`` and the trigger price are
    compared; the client order id is compared implicitly, since it is what
    selects a leg at all. ``price`` and ``timeInForce`` on a stop-market leg are
    **server defaults and are excluded entirely** -- comparing them manufactures
    divergence on every pass.

    **The trigger is compared NUMERICALLY.** The venue pads what it returns --
    ``"40917.83"`` comes back ``"40917.83000000"`` -- so a string comparison
    would report divergence every cycle on protection that is perfectly correct.
    ``Order.stop_price`` is already ``Decimal`` and ``Decimal`` equality is
    numeric, which is the whole mechanism; it is stated because it is invisible.

    :returns: a frozen verdict. Never raises for an ordinary venue state -- an
        unreadable one is a value, because a reconciler that raised on a state
        it did not expect would take the pass down with it.
    """
    asked = _requested(stop_loss, take_profit)
    mine = {
        parts.leg: order
        for parts, order in resting
        if parts.symbol == symbol
        and parts.entry_bar_time == entry_bar_time
        and parts.generation == generation
    }

    if not asked:
        # `ABSENT_BY_DESIGN` asserts that no protection is EXPECTED, which is
        # the off-switch for the divergence detector on this position. Assert it
        # only when nothing of ours rests either; legs resting under a position
        # that asked for none is a story nobody has established, and switching
        # the detector off over it is exactly the silent wrong value.
        protective = {leg: order for leg, order in mine.items() if leg is not OrderListLeg.WORKING}
        if protective:
            return ProtectionAssessment(
                state=ProtectionState.UNKNOWN,
                reason=(
                    f"no protection was requested for {symbol}, yet "
                    f"{len(protective)} protective leg(s) rest under our own ids"
                ),
            )
        return ProtectionAssessment(
            state=ProtectionState.ABSENT_BY_DESIGN,
            reason=f"no protective levels were requested for {symbol}",
        )

    # A fill is refused rather than interpreted, and BEFORE any price
    # comparison, so a filled leg carrying a stale trigger is not mislabelled a
    # price divergence. Nothing in this tree has ever observed a filled
    # protective leg -- the fill path is UNMEASURED -- so the honest answer is
    # that the story is not established. `UNKNOWN` is untrusted, which refuses
    # entries: reversible, and it makes the missing measurement visible in
    # behaviour instead of hiding it inside an assumption.
    for leg, order in sorted(mine.items(), key=lambda item: item[0].value):
        if order.status is OrderStatus.FILLED or order.filled_quantity > 0:
            return ProtectionAssessment(
                state=ProtectionState.UNKNOWN,
                reason=(
                    f"{symbol} leg {leg.value} reports status {order.status.value} with "
                    f"{order.filled_quantity} executed; the fill path is unmeasured, so this "
                    "state is refused rather than interpreted"
                ),
            )

    missing = tuple(
        UnresolvedLeg(
            leg=leg,
            client_order_id=client_order_id(symbol, entry_bar_time, leg, generation=generation),
        )
        for leg in sorted(asked, key=lambda leg: leg.value)
        if leg not in mine
    )
    if missing:
        return ProtectionAssessment(
            state=ProtectionState.UNKNOWN,
            reason=(
                f"{symbol} requested leg(s) "
                f"{', '.join(item.leg.value for item in missing)} are absent from what rests; "
                "absence is never-placed, cancelled or filled and only a point query separates "
                "them"
            ),
            unresolved=missing,
        )

    for leg in sorted(asked, key=lambda leg: leg.value):
        order = mine[leg]
        wanted = asked[leg]
        if order.stop_price != wanted:
            return ProtectionAssessment(
                state=ProtectionState.DIVERGED,
                reason=(
                    f"{symbol} leg {leg.value} rests at trigger {order.stop_price} where "
                    f"{wanted} was requested"
                ),
            )
        if order.quantity != quantity:
            return ProtectionAssessment(
                state=ProtectionState.DIVERGED,
                reason=(
                    f"{symbol} leg {leg.value} rests for {order.quantity} where {quantity} "
                    "was requested"
                ),
            )
        if order_list_id is not None and order.order_list_id != order_list_id:
            return ProtectionAssessment(
                state=ProtectionState.DIVERGED,
                reason=(
                    f"{symbol} leg {leg.value} belongs to list {order.order_list_id} where "
                    f"{order_list_id} was requested"
                ),
            )

    pending = tuple(
        leg.value
        for leg in sorted(asked, key=lambda leg: leg.value)
        if mine[leg].status is OrderStatus.PENDING_NEW
    )
    if pending:
        return ProtectionAssessment(
            state=ProtectionState.PENDING,
            reason=(
                f"{symbol} leg(s) {', '.join(pending)} are accepted and not yet activated; "
                "a pending leg becomes live only when the working order fills"
            ),
        )

    return ProtectionAssessment(
        state=ProtectionState.ACTIVE,
        reason=f"{symbol}: every requested protective leg rests at its requested trigger",
    )
