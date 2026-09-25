"""What a booking line says about the settlement it was booked net of.

**ONE FIELD SET FOR THREE EMITTERS.** The reconciliation driver's
``exit_booked`` and both of the executor's ``close_booked`` lines book an exit
through ``Portfolio.close_position`` net of an
:class:`~trading_bot.core.models.ExitSettlement`, and until this module each
wrote its own subset of that settlement: the driver five fields, the sell site
four, and the resolved-close site two. A reader of one line could not tell
which of the others it resembled without knowing which path ran. Ruled by the
project owner: one helper, one field set, every site.

**EVERY FIELD COMES FROM THE SETTLEMENT, SO EVERY FIELD IS PROVABLE AT EVERY
SITE** -- except one. ``order_created_at`` is the venue's timestamp for the
ORDER RECORD, which the settlement does not carry, so the caller supplies it;
when the venue sent none it is OMITTED, never emitted as ``null``. That is the
log schema's rule: a field that would have to lie is absent.

**``order_id`` AND ``quantity`` ARE THE SETTLEMENT'S, AND AT THE TWO SITES
THAT ALREADY LOGGED THEM THEY ARE EQUAL BY CONSTRUCTION.**
:func:`~trading_bot.core.portfolio.settle_exit` is called with the order id and
executed quantity those sites used to log; it keeps only the fills carrying
that order id, returns it as ``order_id``, and refuses unless the fills sum to
exactly that quantity. ``Decimal`` compares numerically, so the equality is of
VALUE; the exponent is the venue's in both sources.

**Whitelist types only**, per the ``extra=`` rule: ``Decimal`` for money and
quantity, ``str`` for ids and ``.isoformat()`` times, ``int`` for the count.
Nothing here performs I/O and nothing here logs; each caller emits its own line
at its own level.

**THE HOLD LINE LIVES HERE TOO** (R2): an exit that filled and cannot be
booked is held at three sites, and :func:`hold_fields` is their one field set,
for the reason ``settlement_fields`` is the booking lines'.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Final

if TYPE_CHECKING:  # pragma: no cover - typing only
    from datetime import datetime
    from decimal import Decimal

    from trading_bot.core.models import ExitSettlement, HeldExit

__all__ = ["EVENT_SETTLEMENT_HELD", "HOLD_MESSAGE", "hold_fields", "settlement_fields"]

#: The event of the one CRITICAL an exit hold emits, at whichever site holds
#: it -- the reconciliation driver, the executor's sell, or its resolution. R2.
EVENT_SETTLEMENT_HELD: Final = "exit_settlement_held"
#: Its message. ``%s`` is the symbol, so every site passes the same arguments.
HOLD_MESSAGE: Final = (
    "%s: an exit FILLED and cannot be booked -- NOTHING WAS BOOKED and the position is "
    "HELD until an operator acts"
)


def settlement_fields(
    settlement: ExitSettlement, *, order_created_at: datetime | None
) -> dict[str, Decimal | str | int]:
    """The settlement's fields for a booking line, as ``extra=`` may carry them.

    Seven when the order record carried a timestamp, six when it did not:
    ``order_created_at`` is OMITTED rather than ``null``. A caller spreads the
    result into its own ``extra=`` and must not emit any of these keys itself --
    a dict display keeps the LAST of two equal keys silently.
    """
    fields: dict[str, Decimal | str | int] = {
        "order_id": settlement.order_id,
        "quantity": settlement.quantity,
        "fee": settlement.fee.amount,
        "fee_asset": settlement.fee.asset,
        "fills": settlement.fill_count,
        "filled_at": settlement.filled_at.isoformat(),
    }
    if order_created_at is not None:
        fields["order_created_at"] = order_created_at.isoformat()
    return fields


def hold_fields(
    held: HeldExit, *, quote_asset: str, quantity: Decimal, quote_total: Decimal | None
) -> dict[str, Decimal | str]:
    """The hold line's fields, as ``extra=`` may carry them. R2.

    ONE field set for the three sites that hold, rendered from one
    :class:`~trading_bot.core.models.HeldExit`, so the line cannot disagree
    with the refusal it reports. ``fees`` renders each amount BESIDE its
    asset, never a bare ``Decimal``, and ``str()`` keeps the venue's exponent.
    ``quote_total`` is OMITTED when the venue gave none -- never ``null``.
    """
    fields: dict[str, Decimal | str] = {
        "order_id": held.order_id,
        "cause": held.cause,
        "quantity": quantity,
        "fees": "; ".join(f"{fee.amount} {fee.asset}" for fee in held.fees),
        "reason": held.reason,
        "resolution": (
            "THE EXIT FILLED and IT CANNOT BE BOOKED: the fees field names what the venue "
            f"charged, and this ledger subtracts only {quote_asset} from a quote total with "
            "no converter -- or a fill of this order is not a sell. NOTHING WAS BOOKED. THE "
            "BASE IS ALREADY SOLD: DO NOT SELL IT BY HAND. The position is HELD in memory "
            "with untrusted protection and is no longer reconciled, so ENTRIES ARE REFUSED "
            "PORTFOLIO-WIDE until an operator acts -- as committed risk unknown at first, "
            "then as a stale position once it ages. Enter this trade by hand, then restart. "
            "A restart releases the hold, because the position is not persisted: after it the "
            "trade is in the ledger only if it was entered by hand."
        ),
    }
    if quote_total is not None:
        fields["quote_total"] = quote_total
    return fields
