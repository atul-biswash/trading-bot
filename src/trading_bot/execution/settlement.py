"""Entry settlement: what an entry order's own fills say it cost, and in what.

**M5O H1. THE CAPABILITY THE SURVEY FOUND SHARED** (``docs/RUN_LEDGER.md``
section 84, ``M5o-001`` and ``M5o-002``): the entry used to be read by ONE
``get_order``, never retried, carrying neither a commission nor its asset, and a
read that failed left a position with no cost basis for good (U13). This module
settles an entry the way ``settle_exit`` settles an exit, from the order's
fills, and adds the bounded retry the single read lacked.

**TWO PARTS, AND THE SPLIT IS THE DESIGN.**

* :func:`derive_entry_settlement` is **pure**: a list of :class:`Trade`, an order
  id, the quantity the order executed, and the two assets, in; an
  :class:`EntrySettlement` out, or a refusal. It takes its order id as an
  argument and assumes nothing about the environment, a client order id or the
  bot (``M5o-035``): the owner's OR-3 evidence path reads the fills of a trade
  placed by hand on another venue through exactly this function.
* :func:`settle_entry` is the **I/O wrapper**: ``get_order`` for whether and how
  much executed, ``get_my_trades`` for the fills, a bounded retry with backoff.

**WHY THE ORDER READ STAYS INSIDE IT** (``M5o-038``). A ``get_my_trades``-only
read cannot tell an expired FOK from fills the index has not shown yet, and the
old ``get_order`` answered expiry positively. So the order read is the authority
on *whether* and *how much*, and the fills supply the cost and the commission.

**SUMMING, NEVER DIVIDING, EXCEPT ONE NAMED QUOTIENT.** Quantity, quote total and
every commission are sums of the fills' exact figures. The one division is the
VWAP, ``quote / quantity``, taken under a 28-digit context rounded half-even
whatever context the caller runs in (a test pins that), carried because
``Position.entry_fill_price`` is a unit price. The booking uses the quote total.

**IT REFUSES; IT DOES NOT SETTLE ON A GUESS.** Fills summing short of the executed
quantity refuse (:class:`EntryFillsIncompleteError`, retried), and so do fills
summing over it, a duplicate trade id and a non-buy (terminal, not retried).

**A COMMISSION IN ANY ASSET IS RECORDED EXACTLY** (R-OC): one :class:`Fee` per
asset, summed, each amount beside its asset, with the assets that are neither
base nor quote named as the UNMEASURED mark. A base-asset commission is **not**
deducted from anything here (R-OE); it is reflected through the netted
quantity, which is H4's.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from decimal import ROUND_HALF_EVEN, Decimal, localcontext
from enum import Enum

from trading_bot.core.enums import OrderSide
from trading_bot.core.exceptions import (
    EntryFillsIncompleteError,
    EntryFillsInconsistentError,
    NonBuyFillError,
    TradingBotError,
)
from trading_bot.core.interfaces import ExchangeClient
from trading_bot.core.models import EntrySettlement, Fee, Order, Trade
from trading_bot.execution.dispatch_budget import CallBounds

__all__ = [
    "DEFAULT_MAX_PAGES",
    "DEFAULT_PAGE_LIMIT",
    "DEFAULT_RETRY",
    "SINGLE_ATTEMPT",
    "RetryPolicy",
    "SettlementBudgetSpentError",
    "SettlementOutcome",
    "SettlementStatus",
    "base_asset_of",
    "derive_entry_settlement",
    "read_order_fills",
    "settle_entry",
]

#: The venue's documented maximum for ``limit`` on ``myTrades``
#: (``docs/RUN_LEDGER.md`` section 87, ``M5o-037``). A full page is the signal to
#: ask for the next one.
DEFAULT_PAGE_LIMIT = 1000

#: A cap on pages for ONE order, so a defect cannot loop. Ten pages of 1000 is
#: ten thousand fills of a single order, which no entry reaches; hitting it
#: returns the list read so far and the derivation refuses it as short.
DEFAULT_MAX_PAGES = 10

#: The VWAP's context, stated here and not inherited from the caller's thread.
_VWAP_PRECISION = 28


class SettlementBudgetSpentError(TradingBotError):
    """The caller's budget had nothing left, so a call was not BEGUN.

    A budget may refuse to begin work and must never abandon work in flight
    (``CLAUDE.md``); this is the refusal, raised before the call it would have
    made. Not an ``ExchangeError``: nothing reached the venue.
    """


def base_asset_of(symbol: str, quote_asset: str) -> str:
    """The base asset of ``symbol``, read off its quote suffix.

    Binance spot symbols are the base and the quote concatenated, and the
    composition root passes the executor and the driver no symbol info. Refused
    rather than guessed when the symbol does not end in the quote asset, or is
    nothing but it: a wrong base asset would mislabel a base commission as a
    third-asset one.

    :raises ValueError: ``symbol`` does not end with ``quote_asset`` or equals it.
    """
    if not symbol.endswith(quote_asset) or symbol == quote_asset:
        raise ValueError(
            f"cannot read the base asset of {symbol!r}: it does not end with the quote "
            f"asset {quote_asset!r}"
        )
    return symbol[: -len(quote_asset)]


def derive_entry_settlement(
    trades: Sequence[Trade],
    *,
    order_id: str,
    executed_quantity: Decimal,
    base_asset: str,
    quote_asset: str,
) -> EntrySettlement:
    """Aggregate one entry order's fills into what a position needs. Refuses, never guesses.

    Pure: no I/O, no clock, no portfolio. Fills of OTHER orders in ``trades`` are
    ignored, as ``settle_exit`` ignores them.

    **THE ORDER OF THE CHECKS IS THE ORDER OF THEIR CAUSES.** No fills, then a
    duplicate id (which would double-count in the sums), then a non-buy, then the
    quantity comparison: a duplicate is reported as a duplicate and not as an
    over-fill it also happens to produce.

    :param executed_quantity: what the ORDER says executed, from ``get_order``.
        Fills summing to less are incomplete; to more, inconsistent.
    :raises ValueError: ``executed_quantity`` is not positive.
    :raises EntryFillsIncompleteError: no fill carries ``order_id``, or the fills
        sum to less than ``executed_quantity``. Waiting can cure this.
    :raises EntryFillsInconsistentError: a trade id repeats, or the fills sum to
        more than ``executed_quantity``. Waiting cannot cure this.
    :raises NonBuyFillError: a fill is not a buy. Waiting cannot cure this.
    """
    if executed_quantity <= 0:
        raise ValueError(f"an entry settles a positive executed quantity, got {executed_quantity}")
    fills = [trade for trade in trades if trade.order_id == order_id]
    if not fills:
        raise EntryFillsIncompleteError(
            f"the venue reported no fills for order {order_id}; a fill list the venue has "
            "not finished indexing looks exactly like this"
        )
    ids = [trade.trade_id for trade in fills]
    if len(set(ids)) != len(ids):
        repeated = sorted({i for i in ids if ids.count(i) > 1})
        raise EntryFillsInconsistentError(
            f"order {order_id}'s fills repeat trade id(s) {repeated}; summing them would "
            "count a fill twice"
        )
    if any(trade.side is not OrderSide.BUY for trade in fills):
        raise NonBuyFillError(
            f"order {order_id} carries a non-BUY fill; an entry settles buys only"
        )

    # EVERY SUM AND THE QUOTIENT RUN UNDER THIS CONTEXT, not only the division. A
    # caller running at a lower precision would otherwise round the QUOTE TOTAL
    # itself on the way in -- the first draft protected the VWAP alone, and the
    # test that sets an ambient precision of 5 caught the sum rounding (M5o-046).
    with localcontext() as context:
        context.prec = _VWAP_PRECISION
        context.rounding = ROUND_HALF_EVEN
        quantity = sum((trade.quantity for trade in fills), Decimal(0))
        quote = sum((trade.quote_quantity for trade in fills), Decimal(0))
        totals: dict[str, Decimal] = {}
        for trade in fills:
            totals[trade.fee.asset] = totals.get(trade.fee.asset, Decimal(0)) + trade.fee.amount
        price = quote / quantity if quantity > 0 else Decimal(0)

    if quantity < executed_quantity:
        raise EntryFillsIncompleteError(
            f"order {order_id}'s fills sum to {quantity} against {executed_quantity} "
            "executed; the fill list is incomplete"
        )
    if quantity > executed_quantity:
        raise EntryFillsInconsistentError(
            f"order {order_id}'s fills sum to {quantity}, MORE than the {executed_quantity} "
            "the order executed"
        )

    fees = tuple(Fee(amount=amount, asset=asset) for asset, amount in sorted(totals.items()))
    unmeasured = tuple(sorted(asset for asset in totals if asset not in {base_asset, quote_asset}))
    return EntrySettlement(
        order_id=order_id,
        quantity=quantity,
        quote_quantity=quote,
        price=price,
        fees=fees,
        unmeasured_fee_assets=unmeasured,
        filled_at=max(trade.filled_at for trade in fills),
        fill_count=len(fills),
    )


#: What the caller hands to bound each call. ``None`` means nothing is left.
BoundsFn = Callable[[], CallBounds | None]


async def read_order_fills(
    client: ExchangeClient,
    symbol: str,
    *,
    order_id: str,
    bounds: BoundsFn,
    page_limit: int = DEFAULT_PAGE_LIMIT,
    max_pages: int = DEFAULT_MAX_PAGES,
) -> list[Trade]:
    """Every fill of one order, paged from the first.

    **THE FIRST PAGE ASKS FROM TRADE ID 0**, because without ``fromId`` the venue
    returns the MOST RECENT trades, and an order with more fills than the page
    would lose its earliest (``M5o-039``). Each later page asks from the last id
    received plus one (``fromId`` is inclusive). A page shorter than ``page_limit``
    is the last; reaching ``max_pages`` returns what was read, and the derivation
    refuses a list that is short.

    Each call asks ``bounds`` first; ``None`` raises
    :class:`SettlementBudgetSpentError` before the call is begun. A venue error
    propagates for the caller's retry.
    """
    trades: list[Trade] = []
    cursor = "0"
    for _ in range(max_pages):
        call = bounds()
        if call is None:
            raise SettlementBudgetSpentError(f"no budget left to read {symbol} order {order_id}")
        page = await client.get_my_trades(
            symbol,
            order_id=order_id,
            limit=page_limit,
            from_id=cursor,
            timeout_s=call.timeout_s,
            attempts=call.attempts,
        )
        trades.extend(page)
        if len(page) < page_limit:
            return trades
        cursor = str(max(int(trade.trade_id) for trade in page) + 1)
    return trades


class SettlementStatus(str, Enum):
    """How one settlement call ended. ``str, Enum``: log it with ``.value``."""

    #: The fills were read and the settlement derived.
    SETTLED = "settled"
    #: The venue ANSWERED that the order executed nothing: an expired FOK. A fact,
    #: not a failure, and the only outcome on which an entry is refused.
    EXPIRED = "expired"
    #: The fills could not be read. NOT an expiry: the entry may well have filled.
    PENDING = "pending"


@dataclass(frozen=True, slots=True)
class SettlementOutcome:
    """The verdict of one :func:`settle_entry` call, carrying its reason.

    The house shape (``PlacementVerdict``, ``BookabilityVerdict``): a value that
    says why, never a bare ``None``. ``attempts`` counts the attempts that
    BEGAN, so a budget refusal before the first call is zero.
    """

    status: SettlementStatus
    attempts: int
    #: Present exactly when ``status`` is ``SETTLED``.
    settlement: EntrySettlement | None = None
    #: The last order read, when one succeeded. On ``EXPIRED`` it is the answer.
    order: Order | None = None
    #: ``"<type>: <message>"`` of the last failure, on ``PENDING`` only.
    failure: str | None = None

    def __post_init__(self) -> None:
        if (self.status is SettlementStatus.SETTLED) != (self.settlement is not None):
            raise ValueError("a settlement is present exactly when the status is SETTLED")
        if (self.status is SettlementStatus.PENDING) != (self.failure is not None):
            raise ValueError("a failure is present exactly when the status is PENDING")


@dataclass(frozen=True, slots=True)
class RetryPolicy:
    """How many attempts and how long to wait between them. M5o H1's proposal.

    **The numbers are the executing session's, and OR-4 leaves them the owner's to
    overrule** (``docs/M5O_CHARTER_DRAFT.md`` section 11, reading 4). Three
    attempts and waits of 0.25 s and 0.5 s keep the whole sequence far inside
    ``dispatch_deadline_s``, which gates every attempt anyway: a budget may refuse
    to begin work, so the retry stops when the deadline does. The reconciliation
    driver uses one attempt and no wait, because its retry is the next pass.
    """

    max_attempts: int = 3
    backoff_s: float = 0.25
    multiplier: float = 2.0

    def __post_init__(self) -> None:
        if self.max_attempts < 1:
            raise ValueError("a policy makes at least one attempt")
        if self.backoff_s < 0 or self.multiplier < 1:
            raise ValueError("backoff_s must be >= 0 and multiplier >= 1")

    def delay_before(self, attempt: int) -> float:
        """Seconds to wait before attempt number ``attempt`` (the first waits none)."""
        if attempt <= 1:
            return 0.0
        return self.backoff_s * self.multiplier ** (attempt - 2)


DEFAULT_RETRY = RetryPolicy()
SINGLE_ATTEMPT = RetryPolicy(max_attempts=1)


async def _attempt(
    client: ExchangeClient,
    symbol: str,
    *,
    client_order_id: str,
    base_asset: str,
    quote_asset: str,
    bounds: BoundsFn,
    page_limit: int,
    max_pages: int,
) -> tuple[EntrySettlement | None, Order]:
    """One pass: the order, then (if it executed) its fills. ``(None, order)`` is an expiry."""
    call = bounds()
    if call is None:
        raise SettlementBudgetSpentError(f"no budget left to read {symbol} {client_order_id}")
    order = await client.get_order(
        symbol,
        client_order_id=client_order_id,
        timeout_s=call.timeout_s,
        attempts=call.attempts,
    )
    if order.filled_quantity <= 0:
        if order.status.is_open:
            # Not terminal and nothing executed: not an expiry, and not something to
            # settle yet. Retried; an FOK should never rest.
            raise EntryFillsIncompleteError(
                f"{client_order_id} reports {order.status.value} with nothing executed"
            )
        return None, order
    trades = await read_order_fills(
        client,
        symbol,
        order_id=order.order_id,
        bounds=bounds,
        page_limit=page_limit,
        max_pages=max_pages,
    )
    settlement = derive_entry_settlement(
        trades,
        order_id=order.order_id,
        executed_quantity=order.filled_quantity,
        base_asset=base_asset,
        quote_asset=quote_asset,
    )
    return settlement, order


async def settle_entry(
    client: ExchangeClient,
    symbol: str,
    *,
    client_order_id: str,
    base_asset: str,
    quote_asset: str,
    bounds: BoundsFn,
    policy: RetryPolicy | None = None,
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    page_limit: int = DEFAULT_PAGE_LIMIT,
    max_pages: int = DEFAULT_MAX_PAGES,
) -> SettlementOutcome:
    """Settle one entry order, retrying a failure waiting may cure. NEVER RAISES a venue error.

    Per attempt: ``get_order`` by the derivable client id (the authority on whether
    and how much executed), and if something did, the order's fills paged from the
    first. The outcome is ``SETTLED``, ``EXPIRED`` (the venue answered that nothing
    executed) or ``PENDING`` (it could not be read).

    **RETRIED:** any exception from the client, and
    :class:`EntryFillsIncompleteError` (index lag, an order still reporting open
    with nothing executed). **NOT RETRIED:** :class:`EntryFillsInconsistentError`
    and :class:`NonBuyFillError`, which waiting cannot cure -- they end the call as
    ``PENDING`` after the attempt that found them. **BUDGET:** every call asks
    ``bounds`` first and an exhausted budget ends the call as ``PENDING`` without
    beginning another; the wait before a retry is skipped when the budget is
    already spent, so a deadline is never waited past.

    ``sleep`` is injected, as ``BaseExchangeClient`` injects its own, so a test
    records the waits and never sleeps. ``asyncio.CancelledError`` is not caught.
    """
    policy = DEFAULT_RETRY if policy is None else policy
    attempts = 0
    failure = "no attempt was made"
    for number in range(1, policy.max_attempts + 1):
        if number > 1:
            if bounds() is None:
                failure = "SettlementBudgetSpentError: the dispatch budget was spent"
                break
            await sleep(policy.delay_before(number))
        try:
            settlement, order = await _attempt(
                client,
                symbol,
                client_order_id=client_order_id,
                base_asset=base_asset,
                quote_asset=quote_asset,
                bounds=bounds,
                page_limit=page_limit,
                max_pages=max_pages,
            )
        except SettlementBudgetSpentError as exc:
            failure = f"{type(exc).__name__}: {exc}"
            break
        except (EntryFillsInconsistentError, NonBuyFillError) as exc:
            attempts += 1
            failure = f"{type(exc).__name__}: {exc}"
            break
        except Exception as exc:  # a venue or transport failure; retried below
            attempts += 1
            failure = f"{type(exc).__name__}: {exc}"
            continue
        attempts += 1
        if settlement is None:
            return SettlementOutcome(SettlementStatus.EXPIRED, attempts, order=order)
        return SettlementOutcome(
            SettlementStatus.SETTLED, attempts, settlement=settlement, order=order
        )
    return SettlementOutcome(SettlementStatus.PENDING, attempts, failure=failure)
