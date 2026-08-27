#!/usr/bin/env python
"""Cancel one live Binance **Spot Testnet** order list that this bot placed.

``engine.modes._snapshot_live_order_lists`` blocks any enabled symbol carrying
an order list of ours that still works, and ``_require_something_tradeable``
then exits the boot when every enabled symbol is blocked. **Nothing in the bot
clears that block and nothing in the bot cancels the list** (M5g-056), and the
Testnet website exposes no trading UI -- so the remedy has to go through the
API. That is what this is for, and it is the whole of what it is for.

**The precondition is the INVERSE of ``clear_testnet_holdings.py``'s.** That
script refuses to run while anything rests at the venue, because a resting
order locks base and makes ``free`` understate the holding. This one has work
only when something *does* rest. The two must not be merged: a merged script
would need one guard that both requires and refuses the same state.

**Cancelling ALONE does not restore the bot.** Cancelling collapses the whole
list (MEASURED at M5c: cancelling one leg of an OTO takes the list with it),
which unlocks the base. Free base is no longer dust, so
``_snapshot_unmanaged_holdings`` blocks the same symbol under
``RefusalStage.UNMANAGED_HOLDING`` instead. The forced sequence is::

    cancel (this script)  ->  sell (clear_testnet_holdings.py)  ->  boot

This script performs the first step only. It prints the next one and stops.

**TESTNET ONLY, and by construction rather than by flag.** Three layers, the
same three ``clear_testnet_holdings.py`` carries and for the same reasons:

1. ``testnet=True`` is a literal in the one ``AsyncClient.create`` call. There
   is no ``--mode``, no environment override, and no ``config.yaml`` key on any
   path here -- the script never loads ``config.yaml`` at all.
2. Credentials come from the **testnet slot only**.
   :func:`_testnet_credentials` reads ``BINANCE_TESTNET_API_KEY`` /
   ``BINANCE_TESTNET_API_SECRET`` and refuses when either is empty. It
   deliberately does **not** call ``Settings.binance_credentials()``, which
   falls back to the LIVE key slot when the testnet slot is blank.
3. :func:`build_client` asserts ``client.testnet is True`` before any signed
   call, reading the library's own state rather than trusting the argument.

The guard in layer 2 is **duplicated** from ``clear_testnet_holdings.py``
rather than shared. ``tests/unit/test_clear_testnet_holdings.py`` records the
decision that a script is a script and not library code, and a testnet
guarantee belongs in the file an operator is auditing rather than one import
away. Each copy carries its own test.

**It cancels, and does nothing else.** It never buys, never sells, never
amends, never places an order of any kind, and never touches a symbol outside
:data:`ALLOWED_SYMBOLS`. **No quantity is ever sent to the venue**: the single
write carries ``symbol``, ``orderListId`` and ``recvWindow``, and nothing more.

**The one write is ``v3_delete_order_list``** -- ``DELETE /api/v3/orderList``,
signed (MEASURED from python-binance 1.0.37). ``cancel_order`` is deliberately
**absent from** :class:`TestnetCancelAPI`. Cancelling a single leg does collapse
the list, but it does so as a side effect where the list-level endpoint says
what it does; leaving the leg route out of the protocol makes it
unrepresentable rather than merely discouraged.

Departures from ``clear_testnet_holdings.py``, each deliberate
-------------------------------------------------------------
**1. The dry run is DISPLAY-ONLY, and is weaker than the clearer's.** That
script validates every sale at the venue through ``create_test_order``
(``POST /api/v3/order/test``), which applies the real filters and places
nothing. **There is no ``order/test`` equivalent for a cancel.** So this dry run
verifies four things against real venue state -- that the target exists, that
it is ours, that it is not already terminal, and that its symbol is allowlisted
-- and it **cannot** verify that the venue would accept the ``DELETE``. A reader
carrying the clearer's expectation across would be wrong, which is why this is
stated rather than implied.

**2. The plan costs ``1 + N`` reads.** One ``v3_get_order_list``, then one
``get_order`` per leg. MEASURED: a list read-back carries ``symbol``,
``orderId`` and ``clientOrderId`` per leg and **no** ``status`` and **no**
``executedQty`` -- which is ``OrderListEntry``'s documented property, that
Q-C section 7's compare set "needs a per-order query per leg". The per-leg
status is not decoration: cancelling a list whose **working leg has already
filled** leaves the base holding unprotected and free, and the operator has to
see that before authorising it.

**3. It holds the bot's instance lock**, ``utils.instance_lock.acquire()``.
Cancelling protection under a running bot pulls the resting legs out from
under a ``Position`` the reconciler may have classified ``ACTIVE``; committed
risk would then price off a ``stop_loss`` that rests nowhere, and the bot would
keep trading on a position it believes is protected until the next pass. The
lock is the bot's, and it is the right instrument here precisely because the
process being excluded is the bot.

The lock is taken for the **whole** run, including the read-only enumeration.
That costs a false refusal -- an operator cannot list open lists while the bot
runs -- and it is accepted rather than branched on, for two reasons: a plan
built against a venue the bot is concurrently mutating is stale by the time it
is authorised, and a lock taken in some modes and not others is a second rule
to keep true. It is keyed on ``logs/.bot.lock`` relative to the working
directory, so **run this from the project root**, as the bot is run.

Examples
--------
    python scripts/cancel_testnet_order_list.py
    python scripts/cancel_testnet_order_list.py --order-list-id 255471
    python scripts/cancel_testnet_order_list.py --order-list-id 255471 --execute
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from decimal import Decimal
from typing import TYPE_CHECKING, Any, NamedTuple, Protocol

from trading_bot.config.settings import Secrets
from trading_bot.core.exceptions import ConfigError, TradingBotError
from trading_bot.exchange.ids import (
    OrderListLeg,
    parse_client_order_id,
    parse_list_client_order_id,
)
from trading_bot.exchange.models import format_decimal
from trading_bot.utils.instance_lock import acquire as acquire_instance_lock

if TYPE_CHECKING:  # pragma: no cover - typing only
    from collections.abc import Awaitable, Callable, Sequence

#: The only symbols whose lists this script may cancel. A hardcoded allowlist
#: rather than an open argument, matching ``clear_testnet_holdings.py``: the
#: purpose is exactly these two, and an open canceller committed to a trading
#: repository cancels anything. Adding a third is a code change and a gate run.
ALLOWED_SYMBOLS = frozenset({"BTCUSDT", "ETHUSDT"})

#: Matches the shipped ``config.yaml`` defaults. Hardcoded rather than read,
#: because this script deliberately loads no config: a value that cannot be
#: configured cannot be configured wrongly.
_RECV_WINDOW_MS = 5000
_REQUEST_TIMEOUT_S = 10.0

#: List statuses from which nothing further can happen. **The same set and the
#: same BLACKLIST direction as ``engine.modes._TERMINAL_LIST_STATUSES``**, and
#: deliberately not imported from it -- that name is private to a ``src/``
#: module, and this project's scripts import only public helpers.
#:
#: The direction agrees with the boot block's; the REASON does not, and saying
#: so is the point. There, an unrecognised status must block because
#: fail-closed on trading is cheap. Here, an unrecognised status is treated as
#: **cancellable**, because the two errors are not symmetric: attempting to
#: cancel something already terminal is refused by the venue and costs one
#: round trip, while refusing to cancel something live strands the operator
#: with no remedy at all -- Testnet has no trading UI. The venue is the
#: backstop, so the cheap error is to ask it.
_TERMINAL_LIST_STATUSES = frozenset({"ALL_DONE", "REJECT"})


class TestnetCancelAPI(Protocol):
    """The EXACT library surface this script uses -- the write-surface whitelist.

    Declared as a Protocol rather than described in a comment so **mypy
    enforces it**: reaching for a method not listed here fails the type gate
    rather than a review. It also lets the tests supply a fake without a
    network.

    **Exactly one member writes: :meth:`v3_delete_order_list`.** Everything
    else is a signed GET. ``cancel_order``, ``order_market_sell`` and every
    ``create_*`` are absent, so the leg-cancel route and every trading route
    are unrepresentable here rather than merely unused.
    """

    testnet: bool

    async def get_order(self, **params: Any) -> dict[str, Any]: ...
    async def v3_get_open_order_list(self, **params: Any) -> list[dict[str, Any]]: ...
    async def v3_get_order_list(self, **params: Any) -> dict[str, Any]: ...
    async def v3_delete_order_list(self, **params: Any) -> dict[str, Any]: ...
    async def close_connection(self) -> None: ...


class LegState(NamedTuple):
    """One leg of a list, as the ``1 + N`` read reports it.

    ``leg`` is ``None`` when the leg's own client order id does not parse as
    ours. That is **reported, not refused**: ownership of the LIST is what
    authorises the cancel, and refusing over an unrecognisable leg id would
    block cancelling a list we can demonstrably prove we placed.
    """

    client_order_id: str
    order_id: int
    leg: OrderListLeg | None
    status: str
    executed_qty: Decimal
    orig_qty: Decimal


class Exposure(NamedTuple):
    """What cancelling this list would leave behind.

    ``identified`` is ``False`` when no leg parsed as the working leg, in which
    case ``executed`` carries no information. The two are separate because
    "nothing was filled" and "we could not tell" must not print the same way --
    the second is not a safe verdict.
    """

    executed: Decimal
    identified: bool


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="cancel-testnet-order-list",
        description=(
            "Cancel one Binance Spot TESTNET order list placed by this bot. "
            "Testnet only, dry run by default."
        ),
    )
    parser.add_argument(
        "--order-list-id",
        type=int,
        default=None,
        metavar="ID",
        help=(
            "The VENUE numeric order list id, as printed by the boot refusal. "
            "Omit it to enumerate what is open and exit. There is no implicit 'all'."
        ),
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Actually cancel. Without it the plan is printed and nothing is written.",
    )
    return parser


def _testnet_credentials(secrets: Secrets | None = None) -> tuple[str, str]:
    """The TESTNET key pair, and never the live one.

    **This is not ``Settings.binance_credentials()`` and must not become it.**
    That function reads ``binance_api_key`` when the testnet slot is empty,
    which is a sensible fallback for a read-only probe and the wrong behaviour
    for a script that writes. Refusing here means the live credential is never
    in memory on this path.

    ``secrets`` is injectable so the tests can express a populated live slot
    beside an empty testnet slot without touching ``.env``.
    """
    resolved = Secrets() if secrets is None else secrets
    key = resolved.binance_testnet_api_key
    secret = resolved.binance_testnet_api_secret
    if not key or not secret:
        raise ConfigError(
            "BINANCE_TESTNET_API_KEY and BINANCE_TESTNET_API_SECRET must both be set. "
            "This script reads the testnet slot only and will not fall back to the live "
            "keys, so a blank testnet slot is a refusal rather than a live connection."
        )
    return key, secret


async def build_client(
    create: Callable[..., Awaitable[TestnetCancelAPI]],
    *,
    secrets: Secrets | None = None,
) -> TestnetCancelAPI:
    """Construct the Testnet client. ``testnet=True`` is a literal, not a variable.

    ``create`` is injected so the tests can assert what is passed without a
    network call. Production hands it ``AsyncClient.create``.

    The post-construction check reads ``client.testnet``, which the library
    assigns once in ``__init__`` and never reassigns -- so a true reading means
    every signed call resolves to ``https://testnet.binance.vision``.
    """
    api_key, api_secret = _testnet_credentials(secrets)
    client = await create(
        api_key=api_key,
        api_secret=api_secret,
        testnet=True,
        requests_params={"timeout": _REQUEST_TIMEOUT_S},
    )
    if client.testnet is not True:
        raise ConfigError(
            "refusing to continue: the constructed client does not report testnet=True, "
            "so a signed call would not be guaranteed to reach the Testnet endpoint"
        )
    return client


def owning_symbol(list_client_order_id: str | None) -> str:
    """The symbol this list belongs to, proved from OUR id. Raises otherwise.

    **RECOGNITION IS BY PARSING, NEVER BY PREFIX**, and this uses the same
    :func:`parse_list_client_order_id` that ``_snapshot_live_order_lists`` uses
    -- so the canceller and the boot block agree by construction rather than by
    coincidence. A raw ``startswith("tb1-")`` would admit ``tb1-garbage``.

    **An absent id is a refusal, not a pass.** ``OrderList.list_client_order_id``
    documents that ``None`` "carries no meaning" on a *placement response*; on a
    read-back it is what proves the list is ours, and a cancel authorised by
    nothing is exactly what the allowlist and the parser exist to prevent.

    Only the symbol is returned. ``entry_bar_time`` and ``generation`` parse but
    are **unverifiable** after a restart -- the bar a previous process traded on
    lived only in that process's memory -- and the parser's own docstring names
    a caller that matches on them as the misuse.
    """
    if not list_client_order_id:
        raise ConfigError(
            "refusing: this list carries no listClientOrderId, so there is nothing to "
            "prove it was placed by this bot. Only lists carrying one of our own ids "
            "may be cancelled here."
        )
    parts = parse_list_client_order_id(list_client_order_id)
    if parts is None:
        raise ConfigError(
            f"refusing: listClientOrderId {list_client_order_id!r} is not one of ours. "
            "It is matched by parsing, not by prefix, so a foreign id that merely starts "
            "with our prefix is refused here too."
        )
    return parts.symbol


def check_symbol_allowed(symbol: str) -> None:
    """Refuse a target outside :data:`ALLOWED_SYMBOLS`.

    Raises rather than skipping, for ``validate_symbols``' reason next door: a
    symbol outside the allowlist is a mistake at the call site, not a market
    state, and quietly ignoring it would report success for a list nobody
    cancelled.
    """
    if symbol not in ALLOWED_SYMBOLS:
        raise ConfigError(
            f"refusing {symbol}: this script cancels lists only on "
            f"{', '.join(sorted(ALLOWED_SYMBOLS))}. Adding a symbol is a code change."
        )


def is_terminal(list_order_status: str | None) -> bool:
    """Whether nothing further can happen to this list.

    See :data:`_TERMINAL_LIST_STATUSES` for why an unrecognised status reads as
    **cancellable** here and as blocking at boot.
    """
    return list_order_status in _TERMINAL_LIST_STATUSES


def to_leg_state(raw: dict[str, Any]) -> LegState:
    """Map one ``get_order`` payload into a :class:`LegState`.

    ``str`` -> ``Decimal`` at the ingest boundary, matching the mappers' ``_dec``.
    No float is created anywhere on this path.
    """
    client_id = str(raw.get("clientOrderId", ""))
    parts = parse_client_order_id(client_id)
    return LegState(
        client_order_id=client_id,
        order_id=int(raw["orderId"]),
        leg=None if parts is None else parts.leg,
        status=str(raw.get("status", "")),
        executed_qty=Decimal(str(raw.get("executedQty", "0"))),
        orig_qty=Decimal(str(raw.get("origQty", "0"))),
    )


def working_exposure(legs: Sequence[LegState]) -> Exposure:
    """How much base the working leg has already taken on.

    Sums ``executedQty`` over working legs rather than testing
    ``status == "FILLED"``: a **partially** filled working leg also leaves base
    behind, and a status test would call that case clean.
    """
    working = [leg for leg in legs if leg.leg is OrderListLeg.WORKING]
    if not working:
        return Exposure(executed=Decimal(0), identified=False)
    return Exposure(
        executed=sum((leg.executed_qty for leg in working), Decimal(0)), identified=True
    )


async def _read_legs(
    client: TestnetCancelAPI, symbol: str, payload: dict[str, Any]
) -> list[LegState]:
    """The ``N`` of the ``1 + N`` reads: one ``get_order`` per leg.

    MEASURED: the list read-back carries no ``status`` and no ``executedQty``,
    so this is the only way to learn whether the working leg has filled.
    """
    legs: list[LegState] = []
    for entry in payload.get("orders", ()):
        raw = await client.get_order(
            symbol=symbol,
            orderId=int(entry["orderId"]),
            recvWindow=_RECV_WINDOW_MS,
        )
        legs.append(to_leg_state(raw))
    return legs


def _print_legs(legs: Sequence[LegState]) -> None:
    for leg in legs:
        # `.value`, never the member: `str()` of a `str, Enum` yields the
        # qualified name, which is the trap `exchange/ids.py` is built around.
        name = "??" if leg.leg is None else leg.leg.value
        print(
            f"    leg {name:<2} id={leg.client_order_id} orderId={leg.order_id} "
            f"status={leg.status} executed={format_decimal(leg.executed_qty)}"
            f"/{format_decimal(leg.orig_qty)}"
        )


def _print_consequence(symbol: str, exposure: Exposure) -> None:
    """Say, in words, what cancelling would leave behind."""
    base = symbol.removesuffix("USDT")
    if not exposure.identified:
        print(
            "    UNKNOWN: no leg parsed as the working leg, so whether cancelling leaves "
            f"{base} behind cannot be determined from these ids. Treat as if it does."
        )
        return
    if exposure.executed > 0:
        print(
            f"    WARNING: the working leg has executed {format_decimal(exposure.executed)} "
            f"{base}. Cancelling removes the resting protection, leaving that {base} "
            "UNPROTECTED and FREE -- which is no longer dust, so it will block this symbol "
            "under UNMANAGED_HOLDING at the next boot. Sell it before booting the bot."
        )
        return
    print(
        f"    The working leg has executed nothing, so cancelling leaves no {base} behind "
        "and no holding to clear afterwards."
    )


async def _enumerate(client: TestnetCancelAPI) -> int:
    """The no-target path: report what is open, write nothing, exit 0.

    **Nothing open is a NORMAL outcome, not an error.** It is the state the
    whole cancel-then-sell sequence exists to reach, and reporting it as a
    failure would make a correct account look broken.
    """
    lists = await client.v3_get_open_order_list(recvWindow=_RECV_WINDOW_MS)
    if not lists:
        print("No order lists are open on this account. Nothing to cancel.")
        return 0
    print(f"{len(lists)} order list(s) open on this account:")
    for payload in lists:
        print(
            f"    orderListId={payload.get('orderListId')} symbol={payload.get('symbol')} "
            f"status={payload.get('listOrderStatus')} "
            f"listClientOrderId={payload.get('listClientOrderId')}"
        )
    print("Name one with --order-list-id to see the plan for cancelling it.")
    return 0


async def _cancel_one(client: TestnetCancelAPI, order_list_id: int, *, execute: bool) -> int:
    """Plan, and on ``--execute`` cancel, one order list."""
    payload = await client.v3_get_order_list(orderListId=order_list_id, recvWindow=_RECV_WINDOW_MS)
    status = payload.get("listOrderStatus")
    print(f"  orderListId={order_list_id} symbol={payload.get('symbol')} status={status}")

    symbol = owning_symbol(payload.get("listClientOrderId"))
    check_symbol_allowed(symbol)
    print(f"    ours: listClientOrderId={payload.get('listClientOrderId')} -> {symbol}")

    if is_terminal(status):
        print(
            f"    NOTHING TO CANCEL: this list is already {status}. A terminal list rests "
            "nothing at the venue and blocks no symbol."
        )
        return 0

    legs = await _read_legs(client, symbol, payload)
    _print_legs(legs)
    _print_consequence(symbol, working_exposure(legs))

    if not execute:
        print("    DRY RUN: nothing cancelled. Re-run with --execute to cancel.")
        print(
            "    Note: this dry run is DISPLAY-ONLY. There is no order/test equivalent "
            "for a cancel, so the venue has not been asked whether it would accept it."
        )
        return 0

    response = await client.v3_delete_order_list(
        symbol=symbol, orderListId=order_list_id, recvWindow=_RECV_WINDOW_MS
    )
    print(f"    CANCELLED: listOrderStatus={response.get('listOrderStatus')}")

    after = await client.v3_get_order_list(orderListId=order_list_id, recvWindow=_RECV_WINDOW_MS)
    after_status = after.get("listOrderStatus")
    if not is_terminal(after_status):
        print(
            f"    WARNING: the list still reads {after_status} on re-read. It may not be "
            "cancelled; check the venue before booting the bot.",
            file=sys.stderr,
        )
        return 1
    print(f"    confirmed: the list re-reads {after_status}")
    return 0


async def _run(order_list_id: int | None, *, execute: bool) -> int:
    from binance import AsyncClient

    client = await build_client(AsyncClient.create)
    try:
        print("Connected to Binance TESTNET (hardcoded; this script has no live path).")
        if order_list_id is None:
            return await _enumerate(client)
        mode = "EXECUTE" if execute else "DRY RUN"
        print(f"Mode: {mode}. Target: order list {order_list_id}")
        return await _cancel_one(client, order_list_id, execute=execute)
    finally:
        await client.close_connection()


def main(argv: list[str] | None = None) -> int:
    """Entry point. Returns a process exit code (0 ok, 1 exchange, 2 config).

    The instance lock wraps everything, including the client construction: it
    must be held before any venue call, not merely before the write.
    ``InstanceLockedError`` is a ``ConfigError``, so a held lock exits 2 through
    the handler already here and introduces no second exit convention. Its
    message names the holder's PID.
    """
    args = _build_parser().parse_args(argv)
    try:
        with acquire_instance_lock():
            return asyncio.run(_run(args.order_list_id, execute=args.execute))
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
