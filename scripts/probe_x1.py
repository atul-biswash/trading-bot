#!/usr/bin/env python
"""Read two order-list legs by client order id and report what actually filled.

**This script exists to close X1**, the measurement `docs/NEXT_MILESTONE.md`
records as the first step of exit booking: *does a venue-TRIGGERED stop leg
populate ``cummulativeQuoteQty``, so that ``Order.average_price`` is
non-``None``?* That question has been DOCUMENTED, NOT MEASURED through two
complete stop-outs, because ``average_price`` has zero readers in ``src/`` --
the reconciler's *"the fill PRICE is unmeasured"* is a static string, not a
report that the field came back empty. Nothing observed it. This observes it.

**Why TWO legs and not one.** The account's move across a trade is one
equation in two unknowns: the entry was a marketable ``LIMIT`` that may have
filled anywhere between its reference and its limit, and the exit is the
stop-market whose fill is the unknown being measured. Querying the stop alone
cannot attribute the move; querying both can, or can prove it still cannot.

Example ids, from the run whose numbers motivated this. **These are an
EXAMPLE, never a default** -- the operator supplies the ids, because a probe
with a hardcoded target is a probe that answers last week's question::

    --symbol ETHUSDT
    --entry-leg tb1-ETHUSDT-1787930999999-0-W
    --exit-leg  tb1-ETHUSDT-1787930999999-0-SL
    --account-delta 34.99550500

**The symbol is an ARGUMENT, never inferred from the id.**
``parse_list_client_order_id`` exists, but it parses the LIST-level id, and a
leg id carries a different shape -- a suffix this script would have to know
about. Depending on that coupling would make a probe fail when a leg-naming
decision changes somewhere it does not read.

**READ-ONLY, and by construction rather than by flag.** The only venue call is
:meth:`ExchangeClient.get_order`, whose own docstring states *"This is a
READ"*. There is no create, no cancel, no amend, and no other endpoint on any
path.

**TESTNET ONLY, with no live path at all.** The mode is the literal
``TradingMode.TESTNET`` assigned in code; there is no ``--mode`` flag and no
``config.yaml`` key that can reach it. That is stricter than
``check_testnet.py``, which offers ``--mode live --confirm-live``, and the
reason is that this script has one purpose on one account: surface that cannot
be reached cannot be reached by accident.

**IT LOGS, THROUGH THE BOT'S OWN ``setup_logging``, AND THAT IS THE POINT.**
``check_testnet.py`` takes no lock and writes no log, so a full run of it
leaves the log and the lock file byte-identical -- a venue contact with no
trace anywhere in the repository. This script writes to
``logs/trading_bot.log`` exactly as the bot does, so the measurement it makes
is recoverable from the tree afterwards rather than only from whoever ran it.
``config.yaml`` is loaded for the logging configuration alone; the mode it
carries is ignored.

**IT DOES NOT TAKE THE INSTANCE LOCK, deliberately.** The lock exists to stop
two processes trading one account. This one writes nothing at the venue, so it
cannot cause the failure the lock prevents -- and taking it would refuse a
running bot, or be refused by one, for a read. A read that can block a boot is
the wrong trade. The cost is stated rather than hidden: two concurrent runs of
this script are possible and harmless.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from decimal import Decimal
from typing import TYPE_CHECKING

from trading_bot.config.settings import get_settings
from trading_bot.core.enums import TradingMode
from trading_bot.core.exceptions import ConfigError, OrderNotFoundError, TradingBotError
from trading_bot.exchange import BinanceClient
from trading_bot.utils.logger import get_logger, setup_logging

if TYPE_CHECKING:  # pragma: no cover - typing only
    from collections.abc import Sequence

    from trading_bot.core.models import Order

_log = get_logger(__name__)

_EVENT_LEG = "probe_x1_leg"
_EVENT_MISSING = "probe_x1_leg_missing"
_EVENT_SUMMARY = "probe_x1_summary"


class LegResult:
    """One leg's answer: the order, or the fact that the venue has no such id.

    ``found=False`` is an ANSWER and not a failure, which is the port's own
    reading of ``OrderNotFoundError``: *"the venue has no such order -- which
    is an ANSWER, not a failure, and callers are expected to act on it."*
    """

    def __init__(self, label: str, client_order_id: str, order: Order | None) -> None:
        self.label = label
        self.client_order_id = client_order_id
        self.order = order

    @property
    def found(self) -> bool:
        return self.order is not None


def notional(order: Order | None) -> Decimal | None:
    """``average_price x filled_quantity``, or ``None`` if either is absent.

    **This RECONSTRUCTS the venue's ``cummulativeQuoteQty``; it does not read
    it.** ``to_order`` derives ``average_price`` as
    ``cummulativeQuoteQty / executedQty`` and keeps neither operand, so the
    port hands back a quotient and the raw quote total is gone. Multiplying
    back is exact in ``Decimal`` only when the division was; where it was not,
    this is the venue's figure to within that rounding and must not be read as
    the wire value.
    """
    if order is None or order.average_price is None:
        return None
    return order.average_price * order.filled_quantity


def _print_every_field(order: Order) -> None:
    """Print every field the returned object carries, enumerated not assumed.

    Enumerated from the model rather than named one by one, because a probe
    that prints the fields it expects cannot show a field it did not expect --
    and the whole reason to run this is that nothing has looked before.
    """
    print("      every field on the returned Order:")
    for field in type(order).model_fields:
        print(f"        {field:>20} = {getattr(order, field)!r}")


def _report_leg(result: LegResult) -> None:
    """Print one leg, then the four values X1 turns on."""
    print(f"    {result.label}: {result.client_order_id}")
    if result.order is None:
        print("      NOT FOUND at the venue -- which is an answer, not a failure.")
        return

    order = result.order
    _print_every_field(order)
    reconstructed = notional(order)
    print("      the four values X1 turns on:")
    print(f"        status                     = {order.status.value}")
    print(f"        executed (filled) quantity = {order.filled_quantity}")
    print(
        "        cummulativeQuoteQty        = "
        + (
            f"{reconstructed} (RECONSTRUCTED as average_price x filled_quantity;"
            " the port does not carry the wire field)"
            if reconstructed is not None
            else "NOT RECOVERABLE -- average_price is None"
        )
    )
    print(
        "        average_price              = "
        + (
            f"{order.average_price}  -> NON-NULL: X1 answered YES for this leg"
            if order.average_price is not None
            else "None  -> X1 answered NO for this leg"
        )
    )


def _report_arithmetic(entry: LegResult, exit_: LegResult, delta: Decimal | None) -> None:
    """The two-leg arithmetic, and whether it attributes the account's move."""
    print("  two-leg arithmetic:")
    spent = notional(entry.order)
    received = notional(exit_.order)
    print(f"    entry notional (quote spent)    = {spent if spent is not None else 'UNKNOWN'}")
    print(
        f"    exit notional (quote received)  = {received if received is not None else 'UNKNOWN'}"
    )

    if spent is None or received is None:
        print(
            "    VERDICT: UNDERDETERMINED. At least one leg has no average_price, so the"
            "\n             account's move cannot be attributed to fills from these two"
            "\n             reads alone."
        )
        return

    net = received - spent
    print(f"    net (received - spent)          = {net}")
    if delta is None:
        print(
            "    VERDICT: both legs priced. No --account-delta given, so no comparison"
            "\n             was made; pass one to check attribution."
        )
        return

    residual = net + delta
    print(f"    account delta supplied          = -{delta}")
    print(f"    residual (net + delta)          = {residual}")
    if residual == 0:
        print("    VERDICT: ATTRIBUTED EXACTLY. The two fills account for the whole move.")
    else:
        print(
            "    VERDICT: NOT fully attributed -- a residual remains. It is a real"
            "\n             discrepancy, not rounding, unless it is below the quote"
            "\n             asset's precision."
        )


async def _query(
    client: BinanceClient, symbol: str, label: str, client_order_id: str, failures: list[str]
) -> LegResult:
    """One ``get_order`` for one leg. Never raises for a missing order.

    ``OrderNotFoundError`` is separated from every other ``TradingBotError``
    on purpose: the first is the venue answering, the second is the probe
    failing, and a script that reported them alike would make "the id is
    wrong" indistinguishable from "the network is down".
    """
    try:
        order = await client.get_order(symbol, client_order_id=client_order_id)
    except OrderNotFoundError:
        _log.warning(
            "Leg not found at the venue",
            extra={
                "event": _EVENT_MISSING,
                "symbol": symbol,
                "leg": label,
                "client_order_id": client_order_id,
            },
        )
        return LegResult(label, client_order_id, None)
    except TradingBotError as exc:
        print(f"  !! {label} FAILED: {type(exc).__name__}: {exc}", file=sys.stderr)
        failures.append(label)
        return LegResult(label, client_order_id, None)

    _log.info(
        "Leg read",
        extra={
            "event": _EVENT_LEG,
            "symbol": symbol,
            "leg": label,
            "client_order_id": client_order_id,
            "status": order.status.value,
            "filled_quantity": order.filled_quantity,
            "average_price": order.average_price,
            # The leg's TRIGGER, closing a documented absence: every prior run
            # of this probe logged status, quantity and fill price and never
            # this, so whether a resting TAKE_PROFIT reports its trigger the
            # way a STOP_LOSS does has never been observed here. `Money | None`
            # -- both `Decimal` and `None` are in the `extra=` admissible set,
            # so it crosses unconverted, exactly as `average_price` above does.
            "stop_price": order.stop_price,
        },
    )
    return LegResult(label, client_order_id, order)


async def _probe(symbol: str, entry_id: str, exit_id: str, delta: Decimal | None) -> int:
    """Read both legs and report. Returns a process exit code."""
    settings = get_settings()
    # A literal, not a variable, and not read from config: see the module
    # docstring. There is no live path here to select.
    settings.mode = TradingMode.TESTNET
    setup_logging(settings.config.logging)
    settings.binance_credentials()

    print("Connecting to Binance TESTNET (hardcoded; this script has no live path).")
    client = await BinanceClient.create(settings)
    failures: list[str] = []
    try:
        print(f"  symbol: {symbol}")
        entry = await _query(client, symbol, "entry leg", entry_id, failures)
        exit_ = await _query(client, symbol, "exit leg", exit_id, failures)
        print("  legs:")
        _report_leg(entry)
        _report_leg(exit_)
        _report_arithmetic(entry, exit_, delta)
        # Logged INSIDE the try, before the teardown. After the `finally` it
        # would reference names an earlier failure may have left unbound, and
        # raise `UnboundLocalError` over the real error -- the masking the
        # composition root's nested teardown exists to prevent.
        _log.info(
            "Probe complete",
            extra={
                "event": _EVENT_SUMMARY,
                "symbol": symbol,
                "entry_found": entry.found,
                "exit_found": exit_.found,
                "failed_steps": len(failures),
            },
        )
    finally:
        await client.close()

    if failures:
        print(
            f"Completed with {len(failures)} failed step(s): {', '.join(failures)}", file=sys.stderr
        )
        return 1
    print("Probe complete.")
    return 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--symbol", required=True, help="Trading pair, e.g. ETHUSDT. Never inferred from an id."
    )
    parser.add_argument(
        "--entry-leg", required=True, help="Client order id of the working (entry) leg."
    )
    parser.add_argument(
        "--exit-leg", required=True, help="Client order id of the protective leg that filled."
    )
    parser.add_argument(
        "--account-delta",
        default=None,
        help=(
            "Quote-asset amount the account MOVED across the trade, positive for a "
            "loss. Optional: without it both notionals are still printed, but no "
            "attribution is claimed."
        ),
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point. Returns a process exit code (0 ok, 1 exchange, 2 config)."""
    args = _build_parser().parse_args(argv)
    try:
        delta = Decimal(args.account_delta) if args.account_delta is not None else None
    except ArithmeticError:
        print(f"--account-delta is not a number: {args.account_delta!r}", file=sys.stderr)
        return 2

    try:
        return asyncio.run(_probe(args.symbol.upper(), args.entry_leg, args.exit_leg, delta))
    except ConfigError as exc:
        print(f"Configuration error: {exc}", file=sys.stderr)
        return 2
    except TradingBotError as exc:
        print(f"Exchange error: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:  # pragma: no cover
        print("Interrupted.", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
