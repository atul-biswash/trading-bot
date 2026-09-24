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
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover - typing only
    from datetime import datetime
    from decimal import Decimal

    from trading_bot.core.models import ExitSettlement

__all__ = ["settlement_fields"]


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
