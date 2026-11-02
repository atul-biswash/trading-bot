"""Entry settlement (``execution/settlement.py``): the derivation, the paging and the retry.

M5o H1. Hermetic: a scripted fake client, an injected sleep that records and never
sleeps, no network and no clock. Exact ``Decimal`` assertions, compared as
``str`` wherever the exponent is part of the claim (the venue writes ``quoteQty``
at exponent -8 and the ledger has been bitten by the exponent before: ``M5l-209``).

**THE EXPECTED VALUES WERE DERIVED BEFORE THE CODE EXISTED**, by ``derive2.py`` in
the P161 scratchpad, with plain ``Decimal`` and importing no project module, and
committed in ``docs/RUN_LEDGER.md`` section 87 (R-T, R-DQ). Each ``quote`` string
below is the exact product of its quantity and price at the venue's exponent -8.
The names F1 to F9f are that section's.
"""

from __future__ import annotations

import decimal
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any

import pytest

from trading_bot.core.enums import OrderSide, OrderStatus, OrderType
from trading_bot.core.exceptions import (
    EntryFillsIncompleteError,
    EntryFillsInconsistentError,
    ExchangeConnectionError,
    NonBuyFillError,
)
from trading_bot.core.models import Fee, Order, Trade
from trading_bot.execution.dispatch_budget import CallBounds
from trading_bot.execution.settlement import (
    DEFAULT_RETRY,
    SINGLE_ATTEMPT,
    SettlementBudgetSpentError,
    SettlementStatus,
    base_asset_of,
    derive_entry_settlement,
    read_order_fills,
    settle_entry,
)

D = Decimal
SYMBOL = "BTCUSDT"
ORDER_ID = "1001"
CLIENT_ID = "tb1-BTCUSDT-1790000000000-0-W"
T0 = datetime(2026, 11, 3, 12, 0, tzinfo=timezone.utc)

# (trade id, quantity, price, quoteQty, commission, commission asset)
Fill = tuple[str, str, str, str, str, str]

# fmt: off
F1: list[Fill] = [("9001", "0.02000000", "80000.00", "1600.00000000", "0.00000000", "BTC")]
F2A: list[Fill] = [
    ("9101", "0.00700000", "80123.45", "560.86415000", "0.00000000", "BTC"),
    ("9102", "0.00800000", "80123.40", "640.98720000", "0.00000000", "BTC"),
    ("9103", "0.00500000", "80123.38", "400.61690000", "0.00000000", "BTC"),
]
F2B: list[Fill] = [
    ("9201", "0.00700000", "80123.45", "560.86415000", "0.00000000", "BTC"),
    ("9202", "0.00800000", "80123.41", "640.98728000", "0.00000000", "BTC"),
    ("9203", "0.00400000", "80123.39", "320.49356000", "0.00000000", "BTC"),
]
F3: list[Fill] = [
    ("9301", "0.01200000", "80000.00", "960.00000000", "0.00001200", "BTC"),
    ("9302", "0.00800000", "80010.00", "640.08000000", "0.00000800", "BTC"),
]
F4: list[Fill] = [("9401", "0.02000000", "80000.00", "1600.00000000", "1.60000000", "USDT")]
F5: list[Fill] = [("9501", "0.02000000", "80000.00", "1600.00000000", "0.00150000", "BNB")]
F5B: list[Fill] = [
    ("9511", "0.01000000", "80000.00", "800.00000000", "0.00001000", "BTC"),
    ("9512", "0.01000000", "80000.00", "800.00000000", "0.00075000", "BNB"),
    ("9513", "0.00500000", "80000.00", "400.00000000", "0.00000500", "BTC"),
]
# fmt: on


def trade(
    fill: Fill,
    *,
    order_id: str = ORDER_ID,
    side: OrderSide = OrderSide.BUY,
    when: datetime = T0,
) -> Trade:
    trade_id, quantity, price, quote, commission, asset = fill
    return Trade(
        trade_id=trade_id,
        order_id=order_id,
        symbol=SYMBOL,
        side=side,
        quantity=D(quantity),
        price=D(price),
        quote_quantity=D(quote),
        fee=Fee(amount=D(commission), asset=asset),
        filled_at=when,
    )


def trades(fills: list[Fill], **kwargs: Any) -> list[Trade]:
    return [trade(fill, **kwargs) for fill in fills]


def derive(fills: list[Fill], executed: str, **kwargs: Any) -> Any:
    return derive_entry_settlement(
        trades(fills, **kwargs),
        order_id=ORDER_ID,
        executed_quantity=D(executed),
        base_asset="BTC",
        quote_asset="USDT",
    )


# --------------------------------------------------------------------------------------
# The derivation, F1 to F5b
# --------------------------------------------------------------------------------------
@pytest.mark.parametrize(
    ("fills", "quantity", "quote", "price", "fees", "third", "count"),
    [
        pytest.param(F1, "0.02000000", "1600.00000000", "80000", [("BTC", "0E-8")], (), 1, id="F1"),
        pytest.param(
            F2A, "0.02000000", "1602.46825000", "80123.4125", [("BTC", "0E-8")], (), 3, id="F2a"
        ),
        pytest.param(
            F2B,
            "0.01900000",
            "1522.34499000",
            "80123.42052631578947368421053",
            [("BTC", "0E-8")],
            (),
            3,
            id="F2b",
        ),
        pytest.param(
            F3, "0.02000000", "1600.08000000", "80004", [("BTC", "0.00002000")], (), 2, id="F3"
        ),
        pytest.param(
            F4, "0.02000000", "1600.00000000", "80000", [("USDT", "1.60000000")], (), 1, id="F4"
        ),
        pytest.param(
            F5,
            "0.02000000",
            "1600.00000000",
            "80000",
            [("BNB", "0.00150000")],
            ("BNB",),
            1,
            id="F5",
        ),
        pytest.param(
            F5B,
            "0.02500000",
            "2000.00000000",
            "80000",
            [("BNB", "0.00075000"), ("BTC", "0.00001500")],
            ("BNB",),
            3,
            id="F5b",
        ),
    ],
)
def test_the_settlement_equals_the_hand_derived_figures(
    fills: list[Fill],
    quantity: str,
    quote: str,
    price: str,
    fees: list[tuple[str, str]],
    third: tuple[str, ...],
    count: int,
) -> None:
    """Every figure, compared as a string so the EXPONENT is part of the claim.

    MUTATION: divide the other way round; sum the fees across assets; drop the
    sort; take the price from the first fill; compute the quote as `qty x price`
    (exponent -10 and not -8, so the `str` comparison fails where `==` would not).
    """
    settlement = derive(fills, quantity)

    assert str(settlement.quantity) == quantity
    assert str(settlement.quote_quantity) == quote
    assert str(settlement.price) == price
    assert [(fee.asset, str(fee.amount)) for fee in settlement.fees] == fees
    assert settlement.unmeasured_fee_assets == third
    assert settlement.fill_count == count
    assert settlement.order_id == ORDER_ID


def test_the_vwap_is_taken_under_its_own_context_whatever_the_caller_runs() -> None:
    """The 28-digit, half-even VWAP does not inherit the ambient decimal context.

    F2b's quotient is non-terminating, so a caller running at 5 digits, or rounding
    down, would get a different figure. MUTATION: drop the `localcontext`, which
    leaves the VWAP at the caller's precision.
    """
    with decimal.localcontext() as ambient:
        ambient.prec = 5
        ambient.rounding = decimal.ROUND_DOWN
        settlement = derive(F2B, "0.01900000")

    assert str(settlement.price) == "80123.42052631578947368421053"


def test_the_exact_quote_total_is_what_the_price_times_the_quantity_returns() -> None:
    """For F2b the derivation showed `vwap x quantity == quote` (delta 0E-24).

    The figure a booking subtracts is the quote total, and it is exact; this pins
    that the price is not lossy at this size, so carrying it is not a distortion.
    """
    settlement = derive(F2B, "0.01900000")

    assert settlement.price * settlement.quantity == settlement.quote_quantity


def test_filled_at_is_the_latest_fill_not_the_first_or_the_last_listed() -> None:
    rows = [
        trade(F2A[0], when=T0 + timedelta(seconds=5)),
        trade(F2A[1], when=T0 + timedelta(seconds=9)),
        trade(F2A[2], when=T0 + timedelta(seconds=1)),
    ]

    settlement = derive_entry_settlement(
        rows, order_id=ORDER_ID, executed_quantity=D("0.02"), base_asset="BTC", quote_asset="USDT"
    )

    assert settlement.filled_at == T0 + timedelta(seconds=9)


def test_a_fill_of_another_order_is_ignored() -> None:
    rows = [
        *trades(F1),
        trade(("9999", "5.00000000", "1.00", "5.00000000", "0", "BTC"), order_id="7"),
    ]

    settlement = derive_entry_settlement(
        rows, order_id=ORDER_ID, executed_quantity=D("0.02"), base_asset="BTC", quote_asset="USDT"
    )

    assert settlement.fill_count == 1


# --------------------------------------------------------------------------------------
# What it refuses, F9 to F9f
# --------------------------------------------------------------------------------------
def test_fills_short_of_the_executed_quantity_refuse_and_never_settle() -> None:
    """F9. The fills sum to 0.015 against 0.02 executed.

    MUTATION: compare with `==` only on the over side, or default a short list to
    settled. The error is the retried kind.
    """
    short: list[Fill] = [("9701", "0.01500000", "80000.00", "1200.00000000", "0E-8", "BTC")]

    with pytest.raises(EntryFillsIncompleteError, match="incomplete"):
        derive(short, "0.02000000")


def test_no_fills_for_the_order_is_incomplete_not_empty_success() -> None:
    """F9b's derivation half: index lag looks exactly like this, and is retried."""
    with pytest.raises(EntryFillsIncompleteError, match="no fills for order 1001"):
        derive_entry_settlement(
            [],
            order_id=ORDER_ID,
            executed_quantity=D("0.02"),
            base_asset="BTC",
            quote_asset="USDT",
        )


def test_fills_over_the_executed_quantity_are_inconsistent() -> None:
    """F9d. 0.025 of fills against 0.02 executed is a state the venue cannot produce."""
    over: list[Fill] = [("9801", "0.02500000", "80000.00", "2000.00000000", "0E-8", "BTC")]

    with pytest.raises(EntryFillsInconsistentError, match="MORE than"):
        derive(over, "0.02000000")


def test_a_repeated_trade_id_is_inconsistent_and_is_reported_as_one() -> None:
    """F9e. The same fill twice would double-count; reported as a duplicate, not as an over-fill."""
    twice = [*F1, *F1]

    with pytest.raises(EntryFillsInconsistentError, match="repeat trade id"):
        derive(twice, "0.02000000")


def test_a_sell_under_the_entry_order_id_is_refused() -> None:
    """F9f. An entry settles buys only. MUTATION: drop the side check."""
    with pytest.raises(NonBuyFillError, match="non-BUY"):
        derive(F1, "0.02000000", side=OrderSide.SELL)


def test_a_non_positive_executed_quantity_is_a_programming_error() -> None:
    with pytest.raises(ValueError, match="positive executed quantity"):
        derive(F1, "0")


@pytest.mark.parametrize(
    ("symbol", "base"),
    [("BTCUSDT", "BTC"), ("ETHUSDT", "ETH"), ("SOLUSDT", "SOL")],
)
def test_the_base_asset_is_read_off_the_quote_suffix(symbol: str, base: str) -> None:
    assert base_asset_of(symbol, "USDT") == base


@pytest.mark.parametrize("symbol", ["BTCEUR", "USDT", ""])
def test_a_symbol_without_the_quote_suffix_has_no_base_asset(symbol: str) -> None:
    """Refused, because a wrong base would mislabel a base commission as a third-asset one."""
    with pytest.raises(ValueError, match="cannot read the base asset"):
        base_asset_of(symbol, "USDT")


# --------------------------------------------------------------------------------------
# The fake client, the paging and the retry
# --------------------------------------------------------------------------------------
def order(
    *,
    status: OrderStatus = OrderStatus.FILLED,
    executed: str = "0.02000000",
    order_id: str = ORDER_ID,
) -> Order:
    return Order(
        order_id=order_id,
        symbol=SYMBOL,
        side=OrderSide.BUY,
        type=OrderType.LIMIT,
        status=status,
        quantity=D("0.02000000"),
        filled_quantity=D(executed),
        client_order_id=CLIENT_ID,
    )


class FakeClient:
    """Scripts `get_order` and `get_my_trades`; honours `from_id` and `limit` like the venue."""

    def __init__(
        self,
        *,
        reply: Order | None = None,
        order_errors: list[Exception | None] | None = None,
        rows: list[Trade] | None = None,
        trade_errors: list[Exception | None] | None = None,
    ) -> None:
        self.reply = reply
        self._order_errors = list(order_errors or [])
        self.rows = list(rows or [])
        self._trade_errors = list(trade_errors or [])
        self.calls: list[str] = []
        self.pages: list[dict[str, Any]] = []

    async def get_order(self, symbol: str, **kwargs: Any) -> Order:
        self.calls.append("get_order")
        if self._order_errors:
            error = self._order_errors.pop(0)
            if error is not None:
                raise error
        assert self.reply is not None
        return self.reply

    async def get_my_trades(self, symbol: str, **kwargs: Any) -> list[Trade]:
        self.calls.append("get_my_trades")
        self.pages.append({key: kwargs.get(key) for key in ("order_id", "limit", "from_id")})
        if self._trade_errors:
            error = self._trade_errors.pop(0)
            if error is not None:
                raise error
        floor = int(kwargs["from_id"]) if kwargs.get("from_id") is not None else 0
        rows = sorted(
            (
                t
                for t in self.rows
                if t.order_id == kwargs.get("order_id") and int(t.trade_id) >= floor
            ),
            key=lambda t: int(t.trade_id),
        )
        limit = kwargs.get("limit")
        return rows if limit is None else rows[:limit]


class Sleeps:
    """An injected sleep that records the waits and never waits."""

    def __init__(self) -> None:
        self.waits: list[float] = []

    async def __call__(self, seconds: float) -> None:
        self.waits.append(seconds)


def roomy() -> CallBounds | None:
    return CallBounds(timeout_s=2.0, attempts=1)


async def settle(client: FakeClient, sleeps: Sleeps, **kwargs: Any) -> Any:
    return await settle_entry(
        client,  # type: ignore[arg-type]
        SYMBOL,
        client_order_id=CLIENT_ID,
        base_asset="BTC",
        quote_asset="USDT",
        bounds=kwargs.pop("bounds", roomy),
        sleep=sleeps,
        **kwargs,
    )


def seven_fills() -> list[Trade]:
    """F8: ids 9801 to 9807, six of 0.003 and one of 0.002, summing to 0.02."""
    rows: list[Fill] = [
        (str(9800 + n), "0.00300000", "80000.00", "240.00000000", "0E-8", "BTC")
        for n in range(1, 7)
    ]
    rows.append(("9807", "0.00200000", "80000.00", "160.00000000", "0E-8", "BTC"))
    return trades(rows)


def six_fills() -> list[Trade]:
    """F8b: ids 9811 to 9816, six of 0.003, summing to 0.018."""
    return trades(
        [
            (str(9810 + n), "0.00300000", "80000.00", "240.00000000", "0E-8", "BTC")
            for n in range(1, 7)
        ]
    )


async def test_paging_starts_at_zero_and_continues_from_the_last_id_plus_one() -> None:
    """F8: pages of 3 over seven fills ask from 0, 9804 and 9807, and stop on the short page.

    MUTATION: start with no `from_id` (the venue then returns the MOST RECENT page);
    continue from the last id and not the last id plus one (a duplicate fill, which
    the derivation refuses); never stop on a short page.
    """
    client = FakeClient(rows=seven_fills())

    fills = await read_order_fills(
        client,  # type: ignore[arg-type]
        SYMBOL,
        order_id=ORDER_ID,
        bounds=roomy,
        page_limit=3,
    )

    assert [p["from_id"] for p in client.pages] == ["0", "9804", "9807"]
    assert all(p["limit"] == 3 and p["order_id"] == ORDER_ID for p in client.pages)
    assert len(fills) == 7


async def test_a_full_last_page_is_ended_by_an_empty_one() -> None:
    """F8b: six fills in pages of 3 need a third, empty, call to know they are all there."""
    client = FakeClient(rows=six_fills())

    fills = await read_order_fills(
        client,  # type: ignore[arg-type]
        SYMBOL,
        order_id=ORDER_ID,
        bounds=roomy,
        page_limit=3,
    )

    assert [p["from_id"] for p in client.pages] == ["0", "9814", "9817"]
    assert len(fills) == 6


async def test_the_page_cap_returns_a_short_list_and_the_derivation_refuses_it() -> None:
    """F8c: capped at 2 pages of 3 a seven-fill order reads 6; the sum is 0.018 against 0.02."""
    client = FakeClient(rows=seven_fills())

    fills = await read_order_fills(
        client,  # type: ignore[arg-type]
        SYMBOL,
        order_id=ORDER_ID,
        bounds=roomy,
        page_limit=3,
        max_pages=2,
    )

    assert len(fills) == 6
    # BOTH refusal types are accepted by the `raises` and the TYPE is asserted after, so a
    # derivation that refuses with the WRONG error fails as an assertion on the wrong value
    # and not as a crash: under a cursor that repeats a fill the survey's q08 saw the
    # inconsistent-error escape an `EntryFillsIncompleteError`-only `raises` (`M5o-063`).
    with pytest.raises((EntryFillsIncompleteError, EntryFillsInconsistentError)) as raised:
        derive_entry_settlement(
            fills,
            order_id=ORDER_ID,
            executed_quantity=D("0.02000000"),
            base_asset="BTC",
            quote_asset="USDT",
        )
    assert type(raised.value) is EntryFillsIncompleteError
    assert "0.01800000 against 0.02000000" in str(raised.value)


async def test_paged_fills_settle_end_to_end() -> None:
    """F8 through `settle_entry`: the paged list is summed and settled, once."""
    client = FakeClient(reply=order(), rows=seven_fills())

    outcome = await settle(client, Sleeps(), page_limit=3)

    assert outcome.status is SettlementStatus.SETTLED
    assert (outcome.settlement.fill_count, str(outcome.settlement.quantity)) == (7, "0.02000000")
    assert client.calls == ["get_order", "get_my_trades", "get_my_trades", "get_my_trades"]


async def test_a_read_with_no_budget_is_not_begun() -> None:
    client = FakeClient(rows=seven_fills())

    with pytest.raises(SettlementBudgetSpentError):
        await read_order_fills(
            client,  # type: ignore[arg-type]
            SYMBOL,
            order_id=ORDER_ID,
            bounds=lambda: None,
        )

    assert client.calls == []


async def test_a_clean_entry_costs_one_order_read_and_one_fills_read() -> None:
    """F1 through the wrapper: `["get_order", "get_my_trades"]`, the +1 call and +5 weight of section 87."""
    client = FakeClient(reply=order(), rows=trades(F1))
    sleeps = Sleeps()

    outcome = await settle(client, sleeps)

    assert outcome.status is SettlementStatus.SETTLED
    assert outcome.attempts == 1
    assert client.calls == ["get_order", "get_my_trades"]
    assert sleeps.waits == []
    assert str(outcome.settlement.price) == "80000"


async def test_an_error_then_success_settles_on_the_second_attempt() -> None:
    """F6: the first fills read fails, the second succeeds; one wait of 0.25 s.

    MUTATION: do not retry; wait before the first attempt; or count the failed
    attempt as not made.
    """
    client = FakeClient(
        reply=order(), rows=trades(F1), trade_errors=[ExchangeConnectionError("reset"), None]
    )
    sleeps = Sleeps()

    outcome = await settle(client, sleeps)

    assert outcome.status is SettlementStatus.SETTLED
    assert outcome.attempts == 2
    assert sleeps.waits == [0.25]
    assert client.calls == ["get_order", "get_my_trades", "get_order", "get_my_trades"]


async def test_an_order_read_that_fails_is_retried_the_same_way() -> None:
    client = FakeClient(
        reply=order(), rows=trades(F1), order_errors=[ExchangeConnectionError("reset"), None]
    )
    sleeps = Sleeps()

    outcome = await settle(client, sleeps)

    assert (outcome.status, outcome.attempts, sleeps.waits) == (SettlementStatus.SETTLED, 2, [0.25])
    assert client.calls == ["get_order", "get_order", "get_my_trades"]


async def test_a_persistent_error_is_pending_after_three_attempts_and_two_waits() -> None:
    """F7: three failures, waits of 0.25 s then 0.5 s, PENDING and not an expiry.

    MUTATION: report a persistent failure as EXPIRED (which would REFUSE a filled
    entry and orphan its protection); wait after the last attempt.
    """
    errors: list[Exception | None] = [ExchangeConnectionError("reset")] * 3
    client = FakeClient(reply=order(), rows=trades(F1), trade_errors=errors)
    sleeps = Sleeps()

    outcome = await settle(client, sleeps)

    assert outcome.status is SettlementStatus.PENDING
    assert outcome.attempts == 3
    assert sleeps.waits == [0.25, 0.5]
    assert outcome.settlement is None
    assert outcome.failure is not None and outcome.failure.startswith("ExchangeConnectionError")


async def test_an_expired_order_is_an_answer_and_reads_no_fills() -> None:
    """F9c: the venue says nothing executed. EXPIRED after one `get_order` and zero fills reads."""
    client = FakeClient(reply=order(status=OrderStatus.EXPIRED, executed="0"))
    sleeps = Sleeps()

    outcome = await settle(client, sleeps)

    assert outcome.status is SettlementStatus.EXPIRED
    assert outcome.attempts == 1
    assert client.calls == ["get_order"]
    assert outcome.order is not None and outcome.order.status is OrderStatus.EXPIRED


async def test_an_order_still_open_with_nothing_executed_is_retried_not_expired() -> None:
    """An FOK should never rest, but if the venue says NEW the entry is not known to have expired."""
    client = FakeClient(reply=order(status=OrderStatus.NEW, executed="0"))
    sleeps = Sleeps()

    outcome = await settle(client, sleeps)

    assert outcome.status is SettlementStatus.PENDING
    assert outcome.attempts == 3


async def test_fills_not_yet_indexed_are_retried_and_end_pending() -> None:
    """F9b: the order says 0.02 executed and the fills list is empty. Index lag looks like this."""
    client = FakeClient(reply=order(), rows=[])
    sleeps = Sleeps()

    outcome = await settle(client, sleeps)

    assert outcome.status is SettlementStatus.PENDING
    assert outcome.attempts == 3
    assert sleeps.waits == [0.25, 0.5]
    assert outcome.failure is not None and "EntryFillsIncompleteError" in outcome.failure
    assert client.calls == ["get_order", "get_my_trades"] * 3


async def test_short_fills_end_pending_and_never_settle() -> None:
    """F9 through the wrapper."""
    short: list[Fill] = [("9701", "0.01500000", "80000.00", "1200.00000000", "0E-8", "BTC")]
    client = FakeClient(reply=order(), rows=trades(short))

    outcome = await settle(client, Sleeps())

    assert outcome.status is SettlementStatus.PENDING
    assert outcome.settlement is None


@pytest.mark.parametrize(
    ("rows", "error"),
    [
        pytest.param(
            [trade(("9801", "0.02500000", "80000.00", "2000.00000000", "0E-8", "BTC"))],
            "EntryFillsInconsistentError",
            id="F9d-over",
        ),
        pytest.param([*trades(F1), *trades(F1)], "EntryFillsInconsistentError", id="F9e-duplicate"),
        pytest.param(trades(F1, side=OrderSide.SELL), "NonBuyFillError", id="F9f-sell"),
    ],
)
async def test_a_contradiction_is_not_retried(rows: list[Trade], error: str) -> None:
    """F9d to F9f: waiting cannot cure these, so one attempt, no wait, PENDING.

    MUTATION: fold them into the retried `except Exception` branch (attempts 3 and
    two waits).
    """
    client = FakeClient(reply=order(), rows=rows)
    sleeps = Sleeps()

    outcome = await settle(client, sleeps)

    assert outcome.status is SettlementStatus.PENDING
    assert outcome.attempts == 1
    assert sleeps.waits == []
    assert outcome.failure is not None and outcome.failure.startswith(error)


async def test_no_budget_at_the_start_begins_nothing() -> None:
    """A budget may refuse to BEGIN work: zero calls, zero attempts, PENDING."""
    client = FakeClient(reply=order(), rows=trades(F1))
    sleeps = Sleeps()

    outcome = await settle(client, sleeps, bounds=lambda: None)

    assert outcome.status is SettlementStatus.PENDING
    assert outcome.attempts == 0
    assert client.calls == []
    assert outcome.failure is not None and "SettlementBudgetSpentError" in outcome.failure


async def test_a_budget_spent_between_attempts_stops_without_waiting() -> None:
    """The deadline is never waited past: after the first failed attempt the budget is gone.

    The bounds function allows exactly the two calls of attempt one. MUTATION:
    sleep before consulting the budget.
    """
    allowed = iter([roomy(), roomy()])

    def bounds() -> CallBounds | None:
        return next(allowed, None)

    client = FakeClient(
        reply=order(), rows=trades(F1), trade_errors=[ExchangeConnectionError("reset")]
    )
    sleeps = Sleeps()

    outcome = await settle(client, sleeps, bounds=bounds)

    assert outcome.status is SettlementStatus.PENDING
    assert outcome.attempts == 1
    assert sleeps.waits == []


async def test_a_single_attempt_policy_is_the_reconciliation_drivers_shape() -> None:
    """One attempt, no wait: the retry of the driver is the next pass, not a sleep."""
    client = FakeClient(
        reply=order(), rows=trades(F1), trade_errors=[ExchangeConnectionError("reset")]
    )
    sleeps = Sleeps()

    outcome = await settle(client, sleeps, policy=SINGLE_ATTEMPT)

    assert (outcome.status, outcome.attempts, sleeps.waits) == (SettlementStatus.PENDING, 1, [])


def test_the_default_policy_is_three_attempts_with_a_doubling_wait() -> None:
    assert DEFAULT_RETRY.max_attempts == 3
    assert [DEFAULT_RETRY.delay_before(n) for n in (1, 2, 3)] == [0.0, 0.25, 0.5]


@pytest.mark.parametrize(
    "kwargs",
    [{"max_attempts": 0}, {"backoff_s": -1.0}, {"multiplier": 0.5}],
)
def test_an_incoherent_policy_is_refused(kwargs: dict[str, Any]) -> None:
    from trading_bot.execution.settlement import RetryPolicy

    with pytest.raises(ValueError):
        RetryPolicy(**kwargs)


def test_a_third_asset_commission_is_recorded_and_marked_not_converted() -> None:
    """F5 and R-OC: BNB is recorded exactly, beside its asset, and marks the trade UNMEASURED.

    The mark names the asset and nothing is subtracted or converted.
    """
    settlement = derive(F5, "0.02000000")

    assert [(f.asset, str(f.amount)) for f in settlement.fees] == [("BNB", "0.00150000")]
    assert settlement.unmeasured_fee_assets == ("BNB",)
    assert str(settlement.quote_quantity) == "1600.00000000"
