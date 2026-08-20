"""Map an approved entry intent to the placement shape the venue needs.

**Pure: no I/O, no clock, no config, no exchange filters.** Given the same
intent and the same seeds this returns the same request. That is what lets the
timed-out-write recovery re-derive what it *would have sent* without having
stored it, and it is why the function takes its identity seeds as arguments
rather than reading a clock.

**The branch is Q-C section 2's, and section 2 calls it irreducible.**
``PERCENT_PRICE_BY_SIDE`` bounds every pending price and refuses the whole list
at submission (MEASURED), so a "never fills" dummy leg cannot be used to force
one shape and collapse the branch. Three rows are reachable:

* stop and take-profit -- :class:`OtocoOrderListRequest`, three legs.
* stop only -- :class:`OtoOrderListRequest`, two legs.
* neither -- a plain :class:`OrderRequest`, ``LIMIT`` at ``entry_limit`` with
  ``FOK``. The entry mechanic is a property of the entry, not of the protection
  around it, so the unprotected branch uses the same one.

The fourth row -- take-profit with no stop -- is refused at config load by
``RiskConfig._check_protective_coverage`` and so cannot arrive here. It raises
rather than falling through, because a fall-through would silently place an
unprotected entry for an operator who asked for a target.

**The side is read, not assumed, and the check is not redundant.** Q-C section 3
fixes ``workingSide=BUY`` and ``pendingSide=SELL`` on both list shapes, so
long-only is a measured contract fact -- but a mapper that ignores a field it
was handed is how a short intent becomes a long position. ``EntryIntent``'s own
validator already refuses a non-``BUY`` side at construction, and MEASURED,
that guard is bypassable: ``model_copy(update={"side": OrderSide.SELL})`` and
``model_construct`` both yield a ``SELL`` entry intent, and ``model_copy`` with
an update is this tree's normal idiom for "return a corrected copy" -- there are
four such call sites in ``src/`` today. So the intent reaching this function is
not guaranteed to have passed its own validator, and every branch reads
``intent.side``.

**Branches one and two pass an identity SEED; branch four passes a finished ID.
The asymmetry is structural, not an inconsistency.** Q-C section 6 derives all
four of a list's client order IDs from ``(symbol, entry_bar_time, generation,
leg)``, so the list request types carry the seeds and the parameter mappers
generate the strings -- holding the IDs in the domain would be a second source
of truth for something guaranteed derivable. A single order has exactly one ID
and **no list-level ID at all**, so there is no family to derive and
:class:`OrderRequest` has a ``client_order_id`` field and no seed fields. This
function is the only place that holds both the request and the seeds, so it is
where that one ID is computed.

Two consequences follow from that asymmetry and are worth knowing before
debugging a failure. Branch four is the **only** branch that can raise
``ContractViolationError`` from ``exchange/ids.py``'s output guard, since it is
the only one that assembles an ID here. And a naive ``entry_bar_time`` is
refused on every branch but by two different mechanisms -- the request types'
own validator on branches one and two, the ID generator on branch four -- so
the message differs while the outcome does not.

**``entry_bar_time`` is a parameter because the intent does not carry it.**
``EntryIntent`` holds ``symbol``, ``side``, ``quantity``, ``reference_price``,
``entry_limit`` and ``levels``, and none of those is the restart-stable seed
Q-C section 6 needs. Its only source today is ``Signal.timestamp``, which both
shipped strategies set to ``last_candle.close_time`` -- correctly, but by
convention: ``Signal.timestamp`` carries ``default_factory=_utcnow``, so a
strategy that omits it seeds the IDs from wall-clock and the derivability
guarantee fails silently. Passing it explicitly puts that choice at the call
site rather than hiding it behind a field access.

Importing ``exchange/ids.py`` from ``execution/`` follows
``execution/reconciliation.py``, which does the same for the same reason: the ID
scheme is a venue contract and belongs to the adapter layer, while ``core/``
must not encode one.
"""

from __future__ import annotations

from datetime import datetime

from trading_bot.core.assessment import EntryIntent
from trading_bot.core.enums import OrderSide, OrderType, TimeInForce
from trading_bot.core.models import (
    OrderRequest,
    OtocoOrderListRequest,
    OtoOrderListRequest,
)
from trading_bot.exchange.ids import OrderListLeg, client_order_id

__all__ = ["PlacementRequest", "build_placement"]


type PlacementRequest = OtocoOrderListRequest | OtoOrderListRequest | OrderRequest
"""What a placement dispatch may be asked to send: one of Q-C section 2's three
reachable shapes. A union rather than a common base, because the shapes dispatch
to three different endpoints and share no behaviour -- only field names."""


def build_placement(
    intent: EntryIntent,
    *,
    entry_bar_time: datetime,
    generation: int = 0,
) -> PlacementRequest:
    """Return the placement request ``intent`` calls for.

    ``entry_bar_time`` is the close time of the bar the entry was decided on --
    the restart-stable identity seed, never ``opened_at`` and never a clock
    reading. ``generation`` is 0 for a first placement; a caller that has
    recovered a higher one from the venue may pass it.

    **No level ordering is checked here.** ``stop_price < entry_limit <
    take_profit`` is enforced by the request types' own validators, which is
    where it belongs -- re-checking it would be a second copy of an invariant
    that already refuses to construct.

    :raises ValueError: ``intent.side`` is not ``BUY``; or the intent carries a
        take-profit with no stop, which config load refuses and this function
        therefore treats as a bypassed validator rather than a shape to map.
        Both are caller bugs detectable without building anything.
    :raises ValueError: propagated from the request types -- a non-positive
        quantity or price, a stop that is not below ``entry_limit``, a target
        that is not above it, or a naive ``entry_bar_time``.
    :raises ContractViolationError: propagated from ``exchange/ids.py`` on the
        unprotected branch only, when the assembled client order ID violates the
        venue's measured rule.
    """
    if intent.side is not OrderSide.BUY:
        raise ValueError(
            f"an entry opens a long on spot, so it is a BUY; got {intent.side}. "
            "Q-C section 3 fixes workingSide=BUY and pendingSide=SELL on both list "
            "shapes, so there is no short shape to map this onto"
        )

    stop_loss = intent.levels.stop_loss
    take_profit = intent.levels.take_profit

    if stop_loss is not None and take_profit is not None:
        return OtocoOrderListRequest(
            symbol=intent.symbol,
            quantity=intent.quantity,
            entry_limit=intent.entry_limit,
            stop_price=stop_loss,
            take_profit=take_profit,
            entry_bar_time=entry_bar_time,
            generation=generation,
        )

    if stop_loss is not None:
        return OtoOrderListRequest(
            symbol=intent.symbol,
            quantity=intent.quantity,
            entry_limit=intent.entry_limit,
            stop_price=stop_loss,
            entry_bar_time=entry_bar_time,
            generation=generation,
        )

    if take_profit is not None:
        raise ValueError(
            f"{intent.symbol} carries a take-profit at {take_profit} and no stop. "
            "RiskConfig._check_protective_coverage refuses that at config load, so "
            "this shape has no endpoint and no branch here; reaching it means the "
            "config validator was bypassed or has regressed"
        )

    return OrderRequest(
        symbol=intent.symbol,
        side=intent.side,
        type=OrderType.LIMIT,
        quantity=intent.quantity,
        price=intent.entry_limit,
        time_in_force=TimeInForce.FOK,
        client_order_id=client_order_id(
            intent.symbol,
            entry_bar_time,
            OrderListLeg.WORKING,
            generation=generation,
        ),
    )
