"""Tests for the reconciliation driver -- the budget, and the never-raising phases.

Separate from ``test_reconciliation_pass.py``, which tests the two functions
this drives. Nothing here asserts what a verdict *is*; it asserts what the
driver spends, what it swallows, and what it says.

No network and no clock: the client is a stub and the clock is injected.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from trading_bot.core.enums import (
    OrderSide,
    OrderStatus,
    OrderType,
    PositionSide,
    ProtectionState,
)
from trading_bot.core.exceptions import ExchangeConnectionError, OrderNotFoundError
from trading_bot.core.models import Candle, Fee, Order, Position, Trade
from trading_bot.core.portfolio import Ledger, Portfolio
from trading_bot.exchange.ids import OrderListLeg, client_order_id
from trading_bot.execution import reconciliation_driver as driver_module
from trading_bot.execution.reconciliation import ExitFill, ProtectionAssessment
from trading_bot.execution.reconciliation_driver import (
    ReconciliationBudget,
    ReconciliationDriver,
)

NOW = datetime(2026, 8, 15, 12, 0, tzinfo=timezone.utc)
BAR = datetime(2026, 8, 15, 11, 0, tzinfo=timezone.utc)
QTY = Decimal("0.00100000")
STOP = Decimal("44117.09")
#: THE VENUE's numeric list id -- what `to_order` puts on `Order.order_list_id`.
VENUE_LIST_ID = "91590"
#: OURS, derived -- the shape `Position.order_list_id` carries in production.
#: Distinct from VENUE_LIST_ID on purpose: they were one constant until
#: M5g-14, and that is why no fixture could express the mismatch.
CLIENT_LIST_ID = "tb1-BTCUSDT-1786694400000-0-L"

BUDGET = ReconciliationBudget(
    dedup_interval=timedelta(minutes=1),
    max_calls=3,
    timeout_s=3.0,
    attempts=1,
)


def _candle(symbol: str = "BTCUSDT", timeframe: str = "1m") -> Candle:
    return Candle(
        symbol=symbol,
        timeframe=timeframe,
        open_time=BAR,
        open=Decimal("47000"),
        high=Decimal("47100"),
        low=Decimal("46900"),
        close=Decimal("47050"),
        volume=Decimal("10"),
        close_time=BAR + timedelta(minutes=1),
    )


class _StubClient:
    """Answers the enumeration, records the bounds, and refuses what it was not told.

    Point-query answers must be configured explicitly for the same reason the
    pass's stub demands a book: an empty or default answer from a venue call is
    a real classification, and a test getting one by default passes for a reason
    nobody chose.
    """

    def __init__(
        self,
        books: dict[str, list[Order]] | None = None,
        orders: dict[str, Order | Exception] | None = None,
        *,
        enumerate_error: Exception | None = None,
        trades: dict[str, list[Trade] | Exception] | None = None,
    ) -> None:
        #: Settlement answers by order id. An order id NOT here is answered by
        #: one fill mirroring the filled leg this stub already serves -- fee
        #: `0.00000000` USDT, the measured value -- and an order id with no
        #: such leg RAISES, so a call nobody configured cannot pass quietly.
        self._trades = trades or {}
        #: Every order id `get_my_trades` was asked for, IN ORDER. The instrument
        #: for R6: zero on diverged, partial and healthy passes, one per booking.
        self.settled: list[str] = []
        self.books = books if books is not None else {}
        self.orders = orders or {}
        self._enumerate_error = enumerate_error
        self.asked: list[str] = []
        self.queried: list[str] = []
        self.bounds: list[tuple[float | None, int | None]] = []

    async def get_own_open_orders(
        self, symbol: str, *, timeout_s: float | None = None, attempts: int | None = None
    ) -> list[Order]:
        self.asked.append(symbol)
        self.bounds.append((timeout_s, attempts))
        if self._enumerate_error is not None:
            raise self._enumerate_error
        return self.books[symbol]

    async def get_order(
        self,
        symbol: str,
        *,
        order_id: str | None = None,
        client_order_id: str | None = None,
        timeout_s: float | None = None,
        attempts: int | None = None,
    ) -> Order:
        key = client_order_id or ""
        self.queried.append(key)
        self.bounds.append((timeout_s, attempts))
        answer = self.orders[key]
        if isinstance(answer, Exception):
            raise answer
        return answer

    async def get_my_trades(
        self,
        symbol: str,
        *,
        order_id: str | None = None,
        limit: int | None = None,
        timeout_s: float | None = None,
        attempts: int | None = None,
    ) -> list[Trade]:
        self.settled.append(order_id or "")
        self.bounds.append((timeout_s, attempts))
        if order_id in self._trades:
            answer = self._trades[order_id]
            if isinstance(answer, Exception):
                raise answer
            return list(answer)
        served = [*self.books.get(symbol, []), *self.orders.values()]
        for order in served:
            if (
                isinstance(order, Order)
                and order.order_id == order_id
                and order.filled_quantity > 0
            ):
                assert order.filled_quote_quantity is not None
                return [
                    Trade(
                        trade_id="1",
                        order_id=order.order_id,
                        symbol=symbol,
                        side=OrderSide.SELL,
                        quantity=order.filled_quantity,
                        price=STOP,
                        quote_quantity=order.filled_quote_quantity,
                        fee=Fee(amount=Decimal("0.00000000"), asset="USDT"),
                        filled_at=NOW,
                    )
                ]
        raise AssertionError(f"get_my_trades({order_id!r}) was not configured")


def _order(symbol: str, leg: OrderListLeg) -> Order:
    return Order(
        order_id="1",
        symbol=symbol,
        side=OrderSide.SELL,
        type=OrderType.STOP_LOSS,
        status=OrderStatus.NEW,
        quantity=QTY,
        stop_price=STOP,
        order_list_id=VENUE_LIST_ID,
        client_order_id=client_order_id(symbol, BAR, leg, generation=0),
    )


def _position(
    symbol: str,
    *,
    stamp: datetime | None = None,
    stop_loss: Decimal | None = STOP,
) -> Position:
    return Position(
        symbol=symbol,
        side=PositionSide.LONG,
        quantity=QTY,
        entry_price=Decimal("47000.00"),
        entry_bar_time=BAR,
        protection=ProtectionState.UNKNOWN,
        order_list_id=CLIENT_LIST_ID,
        last_reconciled_at=stamp,
        stop_loss=stop_loss,
    )


def _portfolio(*positions: Position) -> Portfolio:
    return Portfolio(
        free_quote=Decimal("10000"),
        positions={position.symbol: position for position in positions},
    )


def _driver(portfolio: Portfolio, client: _StubClient, **kwargs: object) -> ReconciliationDriver:
    return ReconciliationDriver(
        portfolio=portfolio,
        client=client,  # type: ignore[arg-type]  # a scripted fake, deliberately partial
        budget=kwargs.pop("budget", BUDGET),  # type: ignore[arg-type]
        clock=kwargs.pop("clock", lambda: NOW),  # type: ignore[arg-type]
        persist_ledger=kwargs.pop("persist_ledger", None),  # type: ignore[arg-type]
    )


# --------------------------------------------------------------------------
# The budget
# --------------------------------------------------------------------------
class TestBudget:
    def test_the_dedup_interval_is_the_shortest_enabled_timeframe(self, tmp_path) -> None:  # type: ignore[no-untyped-def]
        """The driver fires on ANY pair's candle, so the shortest bar is what
        bounds staleness. Taking the longest would re-read on bars that taught
        it nothing about the fast pair."""
        from tests.unit.test_modes import write_settings

        settings = write_settings(tmp_path)

        budget = ReconciliationBudget.from_config(
            settings.config, timeframes={"BTCUSDT": "1m", "ETHUSDT": "5m"}
        )

        assert budget.dedup_interval == timedelta(minutes=1)

    def test_max_calls_is_the_position_limit(self, tmp_path) -> None:  # type: ignore[no-untyped-def]
        """The coherence validator reserves `max_open_positions x
        reconcile_deadline_s` and every call is bounded by that deadline, so the
        reservation admits exactly that many calls."""
        from tests.unit.test_modes import write_settings

        settings = write_settings(tmp_path)

        budget = ReconciliationBudget.from_config(settings.config, timeframes={"BTCUSDT": "1m"})

        assert budget.max_calls == settings.config.risk.limits.max_open_positions

    def test_the_per_call_bound_is_the_reconcile_deadline_at_one_attempt(self, tmp_path) -> None:  # type: ignore[no-untyped-def]
        """`attempts x timeout_s <= T_recon` admits exactly one attempt at the
        full deadline. The retry is not removed -- it moves to the CADENCE, since
        an unstamped position sorts first and is re-read next bar. That covers
        the PASS and not the resolver; see the docstring on `from_config`."""
        from tests.unit.test_modes import write_settings

        settings = write_settings(tmp_path)

        budget = ReconciliationBudget.from_config(settings.config, timeframes={"BTCUSDT": "1m"})

        assert budget.timeout_s == settings.config.risk.reconcile_deadline_s
        assert budget.attempts == 1

    def test_an_empty_timeframe_map_is_a_programming_error(self, tmp_path) -> None:  # type: ignore[no-untyped-def]
        """`_pair_timeframes` refuses an empty enabled-pair set at boot, naming
        config.yaml. Reaching here with none means the root was bypassed, so this
        raises rather than inventing a second refusal for one condition."""
        from tests.unit.test_modes import write_settings

        settings = write_settings(tmp_path)

        with pytest.raises(ValueError, match="at least one timeframe"):
            ReconciliationBudget.from_config(settings.config, timeframes={})


# --------------------------------------------------------------------------
# What the driver spends
# --------------------------------------------------------------------------
async def test_the_budget_reaches_the_client_on_every_call() -> None:
    """Both phases run inside one reserved slot, so both take the same bound.
    Omitting it inherits the client-wide policy -- tens of seconds -- and nothing
    reports that."""
    position = _position("BTCUSDT")
    client = _StubClient(
        {"BTCUSDT": []},
        orders={
            client_order_id("BTCUSDT", BAR, OrderListLeg.STOP_LOSS, generation=0): _order(
                "BTCUSDT", OrderListLeg.STOP_LOSS
            )
        },
    )

    await _driver(_portfolio(position), client)(_candle())

    assert client.bounds == [(3.0, 1), (3.0, 1)]


async def test_resolution_gets_the_calls_the_pass_did_not_spend(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """`max_queries = max_calls - len(results)`, which is sound only because the
    pass makes exactly one call per returned assessment.

    **The REMAINDER is asserted through the log, not through the query count.**
    One position with one absent leg makes one query whether the remainder is
    two or three, so counting queries cannot see the subtraction at all. The
    summary carries the figure the driver actually computed.
    """
    position = _position("BTCUSDT")
    sl = client_order_id("BTCUSDT", BAR, OrderListLeg.STOP_LOSS, generation=0)
    client = _StubClient({"BTCUSDT": []}, orders={sl: _order("BTCUSDT", OrderListLeg.STOP_LOSS)})

    with caplog.at_level(logging.INFO):
        await _driver(_portfolio(position), client)(_candle())

    assert client.asked == ["BTCUSDT"]
    assert client.queried == [sl]
    summary = next(r for r in caplog.records if r.event == "reconciliation_pass")  # type: ignore[attr-defined]
    assert summary.queries == BUDGET.max_calls - 1  # type: ignore[attr-defined]


async def test_the_candle_is_a_trigger_not_a_subject() -> None:
    """Reconciliation visits every open position on ANY pair's bar, so a
    BTCUSDT candle reconciles the ETHUSDT position too. That is what bounds
    staleness by the SHORTEST timeframe rather than the slowest position's."""
    client = _StubClient(
        {"BTCUSDT": [_order("BTCUSDT", OrderListLeg.STOP_LOSS)], "ETHUSDT": []},
        orders={
            client_order_id("ETHUSDT", BAR, OrderListLeg.STOP_LOSS, generation=0): _order(
                "ETHUSDT", OrderListLeg.STOP_LOSS
            )
        },
    )

    await _driver(_portfolio(_position("BTCUSDT"), _position("ETHUSDT")), client)(
        _candle(symbol="BTCUSDT")
    )

    assert sorted(client.asked) == ["BTCUSDT", "ETHUSDT"]


async def test_both_phases_share_one_clock_reading() -> None:
    """A two-phase reconciliation records the CYCLE it belongs to, not the moment
    its second half finished. The pass's dedup arithmetic and the resolver's
    stamp then agree by construction.

    **The fixture must be a position the RESOLVER stamps.** A position with
    nothing requested is stamped by the pass and never reaches the resolver's
    clock at all, so that fixture cannot express a second reading -- measured:
    the obvious version of this test passed unchanged under a mutation that gave
    the resolver its own `self._clock()` call. So this one requests a stop, has
    it come back absent, and lets the point query complete the reconciliation.
    """
    readings = iter([NOW, NOW + timedelta(hours=1)])
    position = _position("BTCUSDT")
    sl = client_order_id("BTCUSDT", BAR, OrderListLeg.STOP_LOSS, generation=0)
    client = _StubClient({"BTCUSDT": []}, orders={sl: OrderNotFoundError("Unknown order sent.")})

    await _driver(_portfolio(position), client, clock=lambda: next(readings))(_candle())

    assert position.protection is ProtectionState.DIVERGED
    assert position.last_reconciled_at == NOW


# --------------------------------------------------------------------------
# What the driver swallows
# --------------------------------------------------------------------------
async def test_a_failed_pass_skips_the_resolver_entirely(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """ADDITION 3, and the two states are distinguished by CONTROL FLOW rather
    than by a value: the exception path returns. Handing the resolver an empty
    tuple would be indistinguishable from a successful pass with nothing to
    resolve -- the fake-default rule one level up, where an empty enumeration is
    a real classification rather than the absence of one.

    **The assertion is on INVOCATION, not on queries made.** Asserting
    ``client.queried == []`` would pass whether the resolver was skipped or
    called with an empty tuple, because an empty tuple makes no queries -- the
    test would then be blind to precisely the distinction it exists to draw.
    That is the same defect one level up, reproduced in the instrument.
    """
    called = False

    async def spy(**_kwargs: object) -> tuple[()]:
        nonlocal called
        called = True
        return ()

    monkeypatch.setattr(driver_module, "resolve_unresolved_legs", spy)
    client = _StubClient(enumerate_error=ExchangeConnectionError("reset"))

    await _driver(_portfolio(_position("BTCUSDT")), client)(_candle())

    assert called is False


async def test_a_failed_pass_does_not_escape_the_driver() -> None:
    """`_notify` catches a raising subscriber and logs an unstructured traceback,
    once per bar, forever, with no counter anywhere quarantining it. So the
    driver reports rather than raises."""
    client = _StubClient(enumerate_error=ExchangeConnectionError("reset"))

    await _driver(_portfolio(_position("BTCUSDT")), client)(_candle())


async def test_a_failed_resolver_does_not_escape_and_the_pass_verdicts_survive(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Different from a failed pass: the pass has already written what it
    learned, so its verdicts are reported unsharpened rather than discarded."""
    sl = client_order_id("BTCUSDT", BAR, OrderListLeg.STOP_LOSS, generation=0)
    client = _StubClient({"BTCUSDT": []}, orders={sl: ExchangeConnectionError("reset")})

    with caplog.at_level(logging.INFO):
        await _driver(_portfolio(_position("BTCUSDT")), client)(_candle())

    records = [r for r in caplog.records if r.name.endswith("reconciliation_driver")]
    assert [r.event for r in records] == [  # type: ignore[attr-defined]
        "reconciliation_phase_failed",
        "reconciliation_pass",
        "reconciliation_untrusted",
    ]


# --------------------------------------------------------------------------
# What the driver says
# --------------------------------------------------------------------------
async def test_a_pass_with_nothing_due_says_nothing(caplog: pytest.LogCaptureFixture) -> None:
    """This fires every bar on every pair. A line per quiet bar is how an
    operator learns to skim the ones that mean something."""
    position = _position("BTCUSDT", stamp=NOW)  # stamped now, so not due
    client = _StubClient({"BTCUSDT": []})

    with caplog.at_level(logging.DEBUG):
        await _driver(_portfolio(position), client)(_candle())

    assert [r for r in caplog.records if r.name.endswith("reconciliation_driver")] == []


async def test_a_pass_that_did_work_logs_one_summary_with_counts_by_state(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Counts cross as a SINGLE STRING FIELD: the `extra=` whitelist admits no
    mapping, and one would reach the JSON sink as an object and the plain sink as
    a Python repr -- the two-sink disagreement the whitelist exists to prevent."""
    client = _StubClient(
        {
            "BTCUSDT": [_order("BTCUSDT", OrderListLeg.STOP_LOSS)],
            "ETHUSDT": [_order("ETHUSDT", OrderListLeg.STOP_LOSS)],
        }
    )

    with caplog.at_level(logging.INFO):
        await _driver(_portfolio(_position("BTCUSDT"), _position("ETHUSDT")), client)(_candle())

    summaries = [
        r
        for r in caplog.records
        if r.name.endswith("reconciliation_driver") and r.event == "reconciliation_pass"  # type: ignore[attr-defined]
    ]
    assert len(summaries) == 1
    assert summaries[0].states == "active=2"  # type: ignore[attr-defined]
    assert summaries[0].positions == 2  # type: ignore[attr-defined]


async def test_untrusted_protection_warns_once_per_pass_naming_every_symbol(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """PER PASS, NOT PER POSITION. Repeating a persistent condition once per
    position per bar is what Q-B site 4's deferred design exists to avoid: it
    escalates a self-clearing condition at a DISTINCT MARKER and promotes it to
    terminal only after N cycles, because escalating a self-clearing condition at
    the same level as a terminal one is how a CRITICAL line stops being read.

    This is also the first consumer of the reasons the pass returns -- they
    cannot be recovered from a written Position, and a portfolio-wide refusal is
    exactly the situation an operator is owed a cause for.

    **TWO untrusted positions, deliberately.** With one, a per-position loop and
    a per-pass line emit exactly one record each and the fixture cannot express
    the difference -- the test would read as covering the rule while being blind
    to its inversion.
    """
    eth_sl = client_order_id("ETHUSDT", BAR, OrderListLeg.STOP_LOSS, generation=0)
    client = _StubClient(
        {"BTCUSDT": [], "ETHUSDT": [], "SOLUSDT": []},
        orders={eth_sl: OrderNotFoundError("Unknown order sent.")},
    )

    with caplog.at_level(logging.WARNING):
        await _driver(
            _portfolio(
                _position("BTCUSDT", stop_loss=None),
                _position("ETHUSDT"),
                _position("SOLUSDT"),
            ),
            client,
            budget=ReconciliationBudget(
                dedup_interval=timedelta(minutes=1), max_calls=4, timeout_s=3.0, attempts=1
            ),
        )(_candle())

    warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert len(warnings) == 1
    assert warnings[0].symbols == "ETHUSDT,SOLUSDT"  # type: ignore[attr-defined]
    assert warnings[0].count == 2  # type: ignore[attr-defined]
    assert "no such order" in warnings[0].detail  # type: ignore[attr-defined]


async def test_a_fully_trusted_pass_does_not_warn(caplog: pytest.LogCaptureFixture) -> None:
    """The other direction. `ABSENT_BY_DESIGN` is the only trusted state today,
    so this is what a quiet pass looks like -- and when `ACTIVE` is admitted to
    the whitelist this line stops firing for healthy positions automatically,
    because the warning and the entry refusal are keyed off the same fact.

    DECLARED, and the obvious version of this note was BACKWARDS. Every verdict
    here being trusted is exactly what makes a WIDENED predicate visible -- a
    warning appears where none should, and measured, this test does fail when
    the predicate is forced true. What it cannot express is a NARROWED one:
    nothing here is untrusted, so removing states from the untrusted side is
    invisible. The test above is what bites for that direction.
    """
    client = _StubClient({"BTCUSDT": []})

    with caplog.at_level(logging.WARNING):
        await _driver(_portfolio(_position("BTCUSDT", stop_loss=None)), client)(_candle())

    assert [r for r in caplog.records if r.levelno == logging.WARNING] == []


# --------------------------------------------------------------------------
# Booking the exit
# --------------------------------------------------------------------------
#: RUN 3's OWN SHAPE, and the choice is a fixture-expressiveness decision
#: rather than flavour. The module's `QTY` of `0.00100000` divides EXACTLY into
#: any 8-dp total -- MEASURED -- so a test built on it computes the same answer
#: whether booking passes the venue's total through or derives a unit price
#: from it, and could not fail a mutation that swapped one for the other. This
#: quantity does not divide exactly, so the two routes give different figures
#: and the assertion below distinguishes them.
#:
#: The EXPONENT is load-bearing: `Decimal("0.02257")` is numerically equal to
#: this and does NOT reproduce the inexactness.
BOOK_QTY = Decimal("0.02257000")
#: What the entry actually cost, per unit. DELIBERATELY APART from the implied
#: exit price of ~79141.64, so a mutation that drops the entry term or books a
#: gross figure moves the answer instead of cancelling.
BOOK_ENTRY_FILL = Decimal("80756.69")
#: The REQUESTED limit, different again -- so a mutation reading `entry_price`
#: in place of `entry_fill_price` is visible rather than silently equal.
BOOK_ENTRY_LIMIT = Decimal("80700.00")
#: The venue's own `cummulativeQuoteQty` for the exit.
BOOK_TOTAL = Decimal("1786.22691640")
#: `total - entry_fill_price * quantity`, the exact route.
BOOK_EXACT = Decimal("-36.4515769000")
#: `((total / quantity) - entry_fill_price) * quantity`, the lossy route. It is
#: asserted NOT to be the answer, which is what makes the pass-through a
#: property of the code rather than of the numbers.
BOOK_VIA_DIVISION = Decimal("-36.45157689999999999999999998")


def _filled_leg(
    symbol: str,
    *,
    filled_quantity: Decimal = BOOK_QTY,
    filled_quote_quantity: Decimal | None = BOOK_TOTAL,
    leg: OrderListLeg = OrderListLeg.STOP_LOSS,
) -> Order:
    """A protective leg the venue reports as FILLED.

    Routed through the REAL `classify_protection`, not a fabricated assessment:
    the driver calls the pass for real, so a fixture that hand-built an
    `ExitFill` would test the booking against a shape the classifier might
    never produce.
    """
    return Order(
        order_id="777",
        symbol=symbol,
        side=OrderSide.SELL,
        type=OrderType.STOP_LOSS,
        status=OrderStatus.FILLED,
        quantity=BOOK_QTY,
        filled_quantity=filled_quantity,
        filled_quote_quantity=filled_quote_quantity,
        stop_price=STOP,
        order_list_id=VENUE_LIST_ID,
        client_order_id=client_order_id(symbol, BAR, leg, generation=0),
        created_at=NOW,
    )


def _booking_position(
    symbol: str = "BTCUSDT", *, entry_fill_price: Decimal | None = BOOK_ENTRY_FILL
) -> Position:
    """A position that can be booked: sized like run 3's, with a cost basis."""
    return Position(
        symbol=symbol,
        side=PositionSide.LONG,
        quantity=BOOK_QTY,
        entry_price=BOOK_ENTRY_LIMIT,
        entry_fill_price=entry_fill_price,
        entry_bar_time=BAR,
        protection=ProtectionState.UNKNOWN,
        order_list_id=CLIENT_LIST_ID,
        last_reconciled_at=None,
        stop_loss=STOP,
    )


class _RecordingWriter:
    """Counts ledger writes and keeps what each one carried."""

    def __init__(self, error: Exception | None = None) -> None:
        self.calls: list[Ledger] = []
        self._error = error

    def __call__(self, ledger: Ledger) -> None:
        self.calls.append(ledger)
        if self._error is not None:
            raise self._error


async def test_a_complete_fill_books_the_venues_own_total_not_a_derived_price() -> None:
    """Row 1, and the assertion that makes the pass-through a code property.

    MUTATION: in `_book_exits`, replace
    `exit_quote_total=fill.filled_quote_quantity` with
    `exit_price=fill.filled_quote_quantity / fill.filled_quantity`.

    Both routes are asserted -- the exact one holds, the division one is
    asserted ABSENT -- so the test cannot be satisfied by a shape where they
    happen to agree. That is why `BOOK_QTY` is not the module's `QTY`.
    """
    portfolio = _portfolio(_booking_position())
    client = _StubClient({"BTCUSDT": [_filled_leg("BTCUSDT")]})
    writer = _RecordingWriter()

    await _driver(portfolio, client, persist_ledger=writer)(_candle())

    assert portfolio.ledger is not None
    assert portfolio.ledger.realised_pnl == BOOK_EXACT
    assert portfolio.ledger.realised_pnl != BOOK_VIA_DIVISION


async def test_a_booking_credits_the_total_verbatim_and_the_position_leaves() -> None:
    """The other two writes `close_position` makes, both asserted exactly.

    MUTATION: credit `fill.filled_quantity * (total / filled_quantity)` instead
    of the total, or drop the `del self.positions[symbol]`.
    """
    portfolio = _portfolio(_booking_position())
    client = _StubClient({"BTCUSDT": [_filled_leg("BTCUSDT")]})

    await _driver(portfolio, client, persist_ledger=_RecordingWriter())(_candle())

    assert portfolio.free_quote == Decimal("10000") + BOOK_TOTAL
    assert "BTCUSDT" not in portfolio.positions
    assert portfolio.open_positions == []


async def test_a_second_pass_over_the_same_fill_books_nothing() -> None:
    """Idempotency BY DELETION -- no flag and no memo.

    MUTATION: make `close_position` leave the symbol in `positions`.

    The venue still reports the same filled leg on the second pass, which is
    exactly what a real one would do until the order ages out. Nothing else
    stops a double booking: `reconcile_open_positions` builds its work list
    from `portfolio.open_positions`, so the deleted symbol is never enumerated
    again.
    """
    portfolio = _portfolio(_booking_position())
    client = _StubClient({"BTCUSDT": [_filled_leg("BTCUSDT")]})
    writer = _RecordingWriter()
    driver = _driver(portfolio, client, persist_ledger=writer)

    await driver(_candle())
    booked_once = portfolio.ledger
    credited_once = portfolio.free_quote

    await driver(_candle())

    assert portfolio.ledger == booked_once
    assert portfolio.free_quote == credited_once
    assert len(writer.calls) == 1  # the second pass had nothing to save
    assert client.asked == ["BTCUSDT"]  # and nothing to enumerate


async def test_a_fill_with_no_quote_total_refuses_and_does_not_book(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Row 2 -- a leg filled and CANNOT BE PRICED.

    MUTATION: fall through to booking with `exit_price=None`, or collapse this
    branch into the `exit_fill is None` skip.

    Distinct from row 4 by construction: the position closed at the venue and
    nothing can be booked for it, which is the state an operator most needs
    told. Asserted on the reason text, because collapsing the two absences
    would still produce a refusal -- just a silent one.
    """
    portfolio = _portfolio(_booking_position())
    client = _StubClient({"BTCUSDT": [_filled_leg("BTCUSDT", filled_quote_quantity=None)]})

    with caplog.at_level(logging.WARNING):
        await _driver(portfolio, client, persist_ledger=_RecordingWriter())(_candle())

    refusals = [r for r in caplog.records if getattr(r, "event", None) == "exit_book_refused"]
    assert len(refusals) == 1
    assert "no quote total" in refusals[0].reason  # type: ignore[attr-defined]
    assert portfolio.ledger is None
    assert "BTCUSDT" in portfolio.positions  # nothing was closed


async def test_a_partial_fill_is_not_booked(caplog: pytest.LogCaptureFixture) -> None:
    """Row 3 -- today's behaviour, preserved rather than extended.

    MUTATION: change the completeness test from `!=` to `<`, or delete it.

    The position keeps `UNKNOWN`, so the existing `COMMITTED_RISK_UNKNOWN`
    interlock refuses entries portfolio-wide. This commit adds no
    `RefusalStage`; it NARROWS booking to complete fills.
    """
    portfolio = _portfolio(_booking_position())
    partial = Decimal("0.01000000")
    client = _StubClient({"BTCUSDT": [_filled_leg("BTCUSDT", filled_quantity=partial)]})

    with caplog.at_level(logging.WARNING):
        await _driver(portfolio, client, persist_ledger=_RecordingWriter())(_candle())

    refusals = [r for r in caplog.records if getattr(r, "event", None) == "exit_book_refused"]
    assert len(refusals) == 1
    assert "partial" in refusals[0].reason  # type: ignore[attr-defined]
    assert portfolio.ledger is None
    assert portfolio.positions["BTCUSDT"].protection is ProtectionState.UNKNOWN
    assert client.settled == []  # R-h: a partial makes no settlement call


async def test_an_over_fill_is_refused_by_the_same_test() -> None:
    """The `!=` half a `<` test would BOOK, on a state the venue cannot produce.

    MUTATION: `filled_quantity < position.quantity`.

    DECLARED: this asserts the conservative answer on an UNREACHABLE state --
    a leg's `executedQty` cannot exceed its `origQty`. It exists so the choice
    of `!=` over `<` is pinned rather than incidental, and it is the only test
    that distinguishes them.
    """
    portfolio = _portfolio(_booking_position())
    over = BOOK_QTY + Decimal("0.00000001")
    client = _StubClient({"BTCUSDT": [_filled_leg("BTCUSDT", filled_quantity=over)]})

    await _driver(portfolio, client, persist_ledger=_RecordingWriter())(_candle())

    assert portfolio.ledger is None
    assert "BTCUSDT" in portfolio.positions


async def test_a_position_with_no_entry_fill_price_refuses_before_it_calls(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Row 5 -- checked HERE, so `unrealized_pnl`'s raise is never control flow.

    MUTATION: delete the `entry_fill_price is None` guard.

    Under it the call still refuses, because `_realised_from_total` raises --
    but it raises INTO the driver's phase `try`, which logs a phase failure and
    abandons every later booking in the pass. Asserted on the event name, which
    is what separates a decision from a caught exception.
    """
    portfolio = _portfolio(_booking_position(entry_fill_price=None))
    client = _StubClient({"BTCUSDT": [_filled_leg("BTCUSDT")]})

    with caplog.at_level(logging.WARNING):
        await _driver(portfolio, client, persist_ledger=_RecordingWriter())(_candle())

    events = [getattr(r, "event", None) for r in caplog.records]
    assert "exit_book_refused" in events
    assert "reconciliation_phase_failed" not in events
    assert portfolio.ledger is None
    assert "BTCUSDT" in portfolio.positions


# --------------------------------------------------------------------------
# The ladder's ORDER, pinned. `M5i-054`.
#
# **THIS IS THE ONE SITE WHERE THE BOOKABILITY CRITERIA'S ORDER IS
# OBSERVABLE**, because the three refusals carry three distinct operator
# messages. Everywhere else the criteria are checked the branches are
# indistinguishable -- `_bookable_total` returns `None` from all four of its
# exclusions, and `_sell_and_book` maps two reasons onto one action.
#
# **AND IT WAS COMPLETELY UNPINNED UNTIL THESE TESTS.** Every driver fixture
# above varies exactly ONE axis, so no input makes two conditions true at once
# and a reorder of the ladder passed the entire suite in silence. MEASURED: all
# three pairwise transpositions killed ZERO tests before this block.
#
# **THEY EXIST TO MAKE A REORDER FAIL LOUDLY**, and the reorder is coming.
# `M5i-053`: the driver's order is the CANONICAL one a shared bookability
# predicate must adopt, because it is the only order that preserves every
# caller's observable behaviour -- `_bookable_total` is order-blind and
# `_sell_and_book` maps a SET of reasons to one action, so the driver's
# messages are the only thing a canonical order can break. Whoever writes
# Option 3 half (ii) should find that constraint from a failing test here, not
# from memory.
#
# The order, DRIVEN rather than read off the source: no-quote-total beats
# partial beats absent-cost-basis. Q > P > C.
# --------------------------------------------------------------------------

#: A fill smaller than `BOOK_QTY`, so the completeness test fails.
BOOK_PARTIAL = Decimal("0.01000000")


def _two_condition_refusal(
    caplog: pytest.LogCaptureFixture,
) -> str:
    """The single refusal reason emitted by a two-condition pass.

    Asserting there is exactly ONE is part of the pin: a ladder that fell
    through and refused twice would be a different defect from one that
    refused in the wrong order, and this separates them.
    """
    refusals = [r for r in caplog.records if getattr(r, "event", None) == "exit_book_refused"]
    assert len(refusals) == 1, f"expected one refusal, got {len(refusals)}"
    return str(refusals[0].reason)  # type: ignore[attr-defined]


async def test_no_quote_total_beats_a_partial_fill(caplog: pytest.LogCaptureFixture) -> None:
    """Q + P both true. **Row 2 wins.** `M5i-054`.

    MUTATION: swap rows 2 and 3 in the ladder; or swap rows 2 and 5.

    **THE ABSENT HALF IS THE LOAD-BEARING ONE HERE, and unusually it is the
    whole test.** A reorder does not stop a refusal happening -- it makes the
    OTHER message fire -- so an assertion that only checked for a refusal, or
    only for row 2's presence alongside whatever else came out, would pass
    under the swap. Only asserting row 3's message ABSENT catches it.
    """
    portfolio = _portfolio(_booking_position())
    client = _StubClient(
        {
            "BTCUSDT": [
                _filled_leg("BTCUSDT", filled_quantity=BOOK_PARTIAL, filled_quote_quantity=None)
            ]
        }
    )

    with caplog.at_level(logging.WARNING):
        await _driver(portfolio, client, persist_ledger=_RecordingWriter())(_candle())

    reason = _two_condition_refusal(caplog)
    assert "no quote total" in reason
    assert "partial" not in reason
    assert portfolio.ledger is None
    assert "BTCUSDT" in portfolio.positions


async def test_a_partial_fill_beats_an_absent_cost_basis(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """P + C both true. **Row 3 wins.** `M5i-054`.

    MUTATION: swap rows 3 and 5 in the ladder; or swap rows 2 and 5.

    The pair that matters most operationally: a partial fill means BASE IS
    STILL AT THE VENUE, where an absent cost basis says only that this bot
    cannot price what already happened. Reporting the cost basis here would
    describe a bookkeeping problem to an operator whose position is still
    half open.
    """
    portfolio = _portfolio(_booking_position(entry_fill_price=None))
    client = _StubClient({"BTCUSDT": [_filled_leg("BTCUSDT", filled_quantity=BOOK_PARTIAL)]})

    with caplog.at_level(logging.WARNING):
        await _driver(portfolio, client, persist_ledger=_RecordingWriter())(_candle())

    reason = _two_condition_refusal(caplog)
    assert "partial" in reason
    assert "entry_fill_price" not in reason
    assert portfolio.ledger is None
    assert "BTCUSDT" in portfolio.positions


async def test_no_quote_total_beats_an_absent_cost_basis(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Q + C both true. **Row 2 wins.** `M5i-054`.

    MUTATION: swap rows 2 and 5 in the ladder.

    The two rows are NOT adjacent, so this is the transposition the other two
    tests cannot both catch between them -- swapping the ends leaves the middle
    row in place and every single-axis test green.
    """
    portfolio = _portfolio(_booking_position(entry_fill_price=None))
    client = _StubClient({"BTCUSDT": [_filled_leg("BTCUSDT", filled_quote_quantity=None)]})

    with caplog.at_level(logging.WARNING):
        await _driver(portfolio, client, persist_ledger=_RecordingWriter())(_candle())

    reason = _two_condition_refusal(caplog)
    assert "no quote total" in reason
    assert "entry_fill_price" not in reason
    assert portfolio.ledger is None
    assert "BTCUSDT" in portfolio.positions


async def test_all_three_conditions_at_once_report_the_first(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Q + P + C all true. **Row 2 wins.** The whole priority in one input.

    MUTATION: any reorder that does not leave row 2 first.

    The three pairwise tests pin the order by transposition; this pins the
    WINNER outright, so a rotation -- which is two transpositions and could
    leave each pair looking locally right -- still fails here.
    """
    portfolio = _portfolio(_booking_position(entry_fill_price=None))
    client = _StubClient(
        {
            "BTCUSDT": [
                _filled_leg("BTCUSDT", filled_quantity=BOOK_PARTIAL, filled_quote_quantity=None)
            ]
        }
    )

    with caplog.at_level(logging.WARNING):
        await _driver(portfolio, client, persist_ledger=_RecordingWriter())(_candle())

    reason = _two_condition_refusal(caplog)
    assert "no quote total" in reason
    assert "partial" not in reason
    assert "entry_fill_price" not in reason


async def test_the_absent_cost_basis_refusal_names_the_cost_basis(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Row 5's MESSAGE, which nothing asserted until now. `M5i-054`.

    MUTATION: give row 5 row 2's or row 3's text.

    `test_a_position_with_no_entry_fill_price_refuses_before_it_calls` above
    asserts only that `exit_book_refused` occurred, because its subject is that
    the refusal is a DECISION rather than a caught exception. So rows 2 and 3
    had their reasons pinned and row 5 did not -- and a shared predicate that
    merged row 5's text into another row's would have passed.

    It also pins what the text must NOT say. The requested `entry_price` is
    measured wrong by up to 76.65 per unit, so the message names it as not a
    substitute; a reader told only "cannot be priced" might reach for it.
    """
    portfolio = _portfolio(_booking_position(entry_fill_price=None))
    client = _StubClient({"BTCUSDT": [_filled_leg("BTCUSDT")]})

    with caplog.at_level(logging.WARNING):
        await _driver(portfolio, client, persist_ledger=_RecordingWriter())(_candle())

    reason = _two_condition_refusal(caplog)
    assert "entry_fill_price" in reason
    assert "not a substitute" in reason
    # ...and it is NOT either of its neighbours.
    assert "no quote total" not in reason
    assert "partial" not in reason


async def test_each_refusal_states_this_callers_consequence(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """The half the predicate does NOT supply. **Nothing pinned this before.**

    MUTATION: drop the consequence and emit `verdict.reason` alone; or give
    both rows the same clause.

    **MEASURED at (ii)b's phase 1: dropping the consequence half killed ZERO
    of the 15 reason assertions in this module.** Every one of them matches on
    a FACT substring -- "no quote total", "partial", "entry_fill_price", "not
    a substitute" -- and all four live in `classify_bookability`. So the whole
    caller-owned half of every refusal message was unheld, and a rewiring that
    silently dropped it would have shipped green. This is that hole.

    **BOTH ROWS, BECAUSE THE TWO CLAUSES ARE DIFFERENT OPERATOR FACTS.** Row 2
    says the position is CLOSED AT THE VENUE; row 3 says it KEEPS ITS
    UNTRUSTED PROTECTION. Collapsing them onto one clause loses the first
    entirely, and asserting only one would not catch that.
    """
    # Row 2 -- a fill the venue never priced.
    portfolio = _portfolio(_booking_position())
    client = _StubClient({"BTCUSDT": [_filled_leg("BTCUSDT", filled_quote_quantity=None)]})
    with caplog.at_level(logging.WARNING):
        await _driver(portfolio, client, persist_ledger=_RecordingWriter())(_candle())
    no_total = _two_condition_refusal(caplog)
    assert "no quote total" in no_total, "the FACT half, from the predicate"
    assert "closed at the venue with nothing booked" in no_total, (
        "row 2's CONSEQUENCE half, which belongs to this caller and not to the module"
    )

    caplog.clear()

    # Row 3 -- a partial fill.
    portfolio = _portfolio(_booking_position())
    client = _StubClient({"BTCUSDT": [_filled_leg("BTCUSDT", filled_quantity=BOOK_PARTIAL)]})
    with caplog.at_level(logging.WARNING):
        await _driver(portfolio, client, persist_ledger=_RecordingWriter())(_candle())
    partial = _two_condition_refusal(caplog)
    assert "partial" in partial, "the FACT half, from the predicate"
    assert "keeps its untrusted protection" in partial, (
        "row 3's CONSEQUENCE half -- TRUE here, and the exact inverse at `_go_naked`"
    )
    # ...and the two consequences are NOT interchangeable.
    assert "closed at the venue" not in partial
    assert "keeps its untrusted protection" not in no_total


async def test_a_pass_with_no_fill_books_nothing_and_saves_nothing() -> None:
    """Row 4 -- no leg reported a fill, so nothing is booked and nothing saved.

    MUTATION: book unconditionally, or save once per pass regardless of
    `booked`. The second is the one worth catching: an unconditional save
    fsyncs the file every bar on a bot that is doing nothing.

    **THIS FIXTURE CLASSIFIES `DIVERGED`, NOT HEALTHY, AND ITS NAME SAID
    OTHERWISE UNTIL `M5k-007`.** `_booking_position` carries `BOOK_QTY`
    0.02257000 where `_order` rests `QTY` 0.00100000, so the quantity
    comparison in `classify_protection` diverges. The assertions below are
    unchanged and still pin what the name says -- both meanings of row 4 have
    `exit_fill is None` -- but the healthy pass is pinned by
    `test_a_healthy_active_pass_escalates_nothing`, not here.
    """
    portfolio = _portfolio(_booking_position())
    client = _StubClient({"BTCUSDT": [_order("BTCUSDT", OrderListLeg.STOP_LOSS)]})
    writer = _RecordingWriter()

    await _driver(portfolio, client, persist_ledger=writer)(_candle())

    assert portfolio.ledger is None
    assert "BTCUSDT" in portfolio.positions
    assert writer.calls == []


async def test_a_diverged_pass_with_no_fill_escalates_at_critical(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Row 4's sixth state -- A5, and the branch that did not exist before it.

    MUTATION: delete the `_escalate_unbookable_divergence` call, or lower the
    level to WARNING.

    The fixture is the producer-(b) shape: a requested stop absent from the
    enumeration, which a point query answers `OrderNotFoundError`, so the
    resolver returns `DIVERGED` carrying no `ExitFill`. Nothing reported a
    fill, so nothing can be priced and the position may describe base the
    account no longer holds.

    ABSTENTION DECLARED: this cannot tell a branch keyed on
    `assessment.state` from one keyed on `exit_fill is None` alone, because
    both fire here. `test_a_healthy_active_pass_escalates_nothing` is what
    separates them.
    """
    position = _position("BTCUSDT")
    sl = client_order_id("BTCUSDT", BAR, OrderListLeg.STOP_LOSS, generation=0)
    client = _StubClient({"BTCUSDT": []}, orders={sl: OrderNotFoundError("Unknown order sent.")})

    with caplog.at_level(logging.CRITICAL):
        await _driver(_portfolio(position), client)(_candle())

    escalations = [r for r in caplog.records if getattr(r, "event", None) == "exit_unbookable"]
    assert len(escalations) == 1
    assert escalations[0].levelno == logging.CRITICAL
    assert getattr(escalations[0], "symbol", None) == "BTCUSDT"


async def test_a_healthy_active_pass_escalates_nothing(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """The HARD CONSTRAINT: the branch reads the state, not the absent fill.

    MUTATION: widen the guard to `exit_fill is None` alone.

    Row 4 covers the ordinary healthy pass -- ACTIVE, PENDING,
    ABSENT_BY_DESIGN -- which is most bars on most positions, so a guard keyed
    on the absent fill alone would emit CRITICAL every minute on a bot doing
    nothing. This fixture rests the requested stop at its requested trigger
    for the requested quantity, which classifies ACTIVE.
    """
    position = _position("BTCUSDT")
    client = _StubClient({"BTCUSDT": [_order("BTCUSDT", OrderListLeg.STOP_LOSS)]})

    with caplog.at_level(logging.DEBUG):
        await _driver(_portfolio(position), client)(_candle())

    assert [r for r in caplog.records if getattr(r, "event", None) == "exit_unbookable"] == []
    assert [r for r in caplog.records if r.levelno >= logging.CRITICAL] == []
    assert position.protection is ProtectionState.ACTIVE
    assert client.settled == []  # a pass with no fill makes no settlement call


async def test_the_escalation_books_nothing_and_saves_nothing() -> None:
    """R6: zero venue calls inside `_book_exits`, and the ledger untouched.

    MUTATION: route the diverged case into `close_position`, or save once per
    pass regardless of `booked`.

    A DIVERGED pass has no fill, so there is no quote total to book and no
    figure to accrue. The position is RETAINED -- deleting it would assert
    that the venue closed it, which is the one thing this state does not
    establish.
    """
    position = _position("BTCUSDT")
    sl = client_order_id("BTCUSDT", BAR, OrderListLeg.STOP_LOSS, generation=0)
    client = _StubClient({"BTCUSDT": []}, orders={sl: OrderNotFoundError("Unknown order sent.")})
    portfolio = _portfolio(position)
    writer = _RecordingWriter()

    await _driver(portfolio, client, persist_ledger=writer)(_candle())

    assert portfolio.ledger is None
    assert "BTCUSDT" in portfolio.positions
    assert writer.calls == []
    # THE CALL THE R6 CLAIM IS ABOUT, read at last: until the fee commit this
    # test named "zero venue calls" and asserted nothing that read one.
    assert client.settled == []


async def test_the_escalation_crosses_the_state_as_a_value_not_a_member(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """`ProtectionState` is a `str, Enum`, so equality cannot pin this.

    MUTATION: pass `assessment.state` where `assessment.state.value` is sent.

    A member compares EQUAL to its own value, so `record.state == "diverged"`
    passes under the exact mutation it would be written for. Only the type
    separates them: `json.dumps` emits the value while `PlainFormatter` calls
    `str()` and gets `ProtectionState.DIVERGED`, and the two sinks then
    disagree about one field.
    """
    position = _position("BTCUSDT")
    sl = client_order_id("BTCUSDT", BAR, OrderListLeg.STOP_LOSS, generation=0)
    client = _StubClient({"BTCUSDT": []}, orders={sl: OrderNotFoundError("Unknown order sent.")})

    with caplog.at_level(logging.CRITICAL):
        await _driver(_portfolio(position), client)(_candle())

    (escalation,) = [r for r in caplog.records if getattr(r, "event", None) == "exit_unbookable"]
    state = escalation.state  # type: ignore[attr-defined]
    assert type(state) is str
    assert state == ProtectionState.DIVERGED.value


async def test_the_ledger_is_saved_once_per_pass_not_once_per_booking() -> None:
    """Ruling 7, and it needs TWO closing positions to express.

    MUTATION: move the `self._persist_ledger(ledger)` call inside the loop.

    `store.save` is whole-file and fsync'd at ~41.6 ms median on this volume,
    and a save per booking writes a file whose final content is identical. A
    one-position fixture cannot tell the two apart -- which is why this test
    carries two and asserts the COUNT, not merely that a save happened.
    """
    portfolio = _portfolio(_booking_position("BTCUSDT"), _booking_position("ETHUSDT"))
    client = _StubClient(
        {
            "BTCUSDT": [_filled_leg("BTCUSDT")],
            "ETHUSDT": [_filled_leg("ETHUSDT")],
        }
    )
    writer = _RecordingWriter()

    await _driver(portfolio, client, persist_ledger=writer)(_candle())

    assert portfolio.positions == {}
    # BOTH booked into one day, so the ledger carries their sum...
    assert portfolio.ledger is not None
    assert portfolio.ledger.realised_pnl == BOOK_EXACT * 2
    # ...and reached disk exactly once.
    assert len(writer.calls) == 1
    assert writer.calls[0].realised_pnl == BOOK_EXACT * 2


async def test_a_raising_save_logs_critical_and_leaves_memory_booked(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Ruling 6, and the residual it names rather than hides.

    MUTATION: let the save exception escape, or log it at ERROR.

    APPLY, THEN SAVE: the booking is already in memory when the write fails, so
    the position is gone and no later pass can enumerate it. Disk is one pass
    stale and nothing revisits it. CRITICAL is a level above the executor's
    persist failures deliberately -- those refuse BEFORE the venue call and
    cost one trade, this one has nothing left to refuse.
    """
    portfolio = _portfolio(_booking_position())
    client = _StubClient({"BTCUSDT": [_filled_leg("BTCUSDT")]})
    writer = _RecordingWriter(error=OSError("no space left on device"))

    with caplog.at_level(logging.CRITICAL):
        await _driver(portfolio, client, persist_ledger=writer)(_candle())

    critical = [r for r in caplog.records if r.levelno == logging.CRITICAL]
    assert len(critical) == 1
    assert getattr(critical[0], "event", None) == "ledger_unwritable"
    assert getattr(critical[0], "error_type", None) == "OSError"
    # Memory is booked; only the durable copy is behind.
    assert portfolio.ledger is not None
    assert portfolio.ledger.realised_pnl == BOOK_EXACT
    assert "BTCUSDT" not in portfolio.positions


async def test_booking_without_a_writer_is_the_pre_commit_behaviour() -> None:
    """A driver with no `persist_ledger` still books; it just persists nothing.

    MUTATION: raise or skip the booking when `_persist_ledger is None`.

    The default is `None`, so every existing construction in this file goes
    through this path -- and booking is a portfolio concern, not a persistence
    one. Getting this backwards would make the ledger depend on whether a
    writer happened to be wired.
    """
    portfolio = _portfolio(_booking_position())
    client = _StubClient({"BTCUSDT": [_filled_leg("BTCUSDT")]})

    await _driver(portfolio, client)(_candle())

    assert portfolio.ledger is not None
    assert portfolio.ledger.realised_pnl == BOOK_EXACT


async def test_a_position_that_is_not_the_portfolios_own_refuses_loudly(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """The orphan guard, on a state that is CURRENTLY UNREACHABLE.

    MUTATION: delete the identity check.

    An orphan is an order list resting at the venue with no `Position`, so it
    cannot pair with an assessment -- every entry in `results` came from
    `portfolio.open_positions`. Orphans bypass booking STRUCTURALLY. This
    forces the state a future edit could create, by swapping the portfolio's
    object for an equal-but-distinct one after the pass has run, and asserts it
    is refused rather than silently no-ops through `close_position`'s
    absent-symbol return.

    DECLARED: it drives `_book_exits` directly. The pass cannot produce this
    input, so a test going through `__call__` would be asserting against a
    fixture the code path forbids.
    """
    portfolio = _portfolio(_booking_position())
    assessment = ProtectionAssessment(
        state=ProtectionState.UNKNOWN,
        reason="forced",
        exit_fill=ExitFill(
            order_id="777",
            filled_quantity=BOOK_QTY,
            filled_quote_quantity=BOOK_TOTAL,
        ),
    )
    stranger = _booking_position()  # equal in value, not the portfolio's object
    driver = _driver(portfolio, _StubClient({"BTCUSDT": []}))

    with pytest.raises(ValueError, match="orphan"):
        await driver._book_exits([(stranger, assessment)], now=NOW)

    # And through `__call__` the same failure is contained, not raised.
    with caplog.at_level(logging.ERROR):
        await driver(_candle())
    assert portfolio.ledger is None


# --------------------------------------------------------------------------
# Settlement: one fetch per bookable exit, net of the fee, and what a failure does
# --------------------------------------------------------------------------
_ZERO_USDT = Fee(amount=Decimal("0.00000000"), asset="USDT")

#: The booking line's settlement fields: one set, shared with both executor
#: lines through `execution/booking_line.py`.
_SEVEN = ("order_id", "quantity", "fee", "fee_asset", "fills", "filled_at", "order_created_at")


def _trade(
    *,
    order_id: str = "777",
    quantity: Decimal = BOOK_QTY,
    quote: Decimal = BOOK_TOTAL,
    fee: Fee = _ZERO_USDT,
) -> Trade:
    """One fill of `_filled_leg`'s order. The zero USDT fee is the MEASURED value."""
    return Trade(
        trade_id="1",
        order_id=order_id,
        symbol="BTCUSDT",
        side=OrderSide.SELL,
        quantity=quantity,
        price=STOP,
        quote_quantity=quote,
        fee=fee,
        filled_at=NOW,
    )


async def test_a_bookable_exit_fetches_once_and_books_net_of_its_fee() -> None:
    """ONE settlement read, bounded like every reconciliation call, and the fee subtracted.

    FABRICATED fee `0.37000000` USDT -- every captured fee is zero, so a real
    one could not tell a booking net of the fee from one that ignores it.
    MUTATION: fetch twice, drop the bound, or book without the fee.
    """
    portfolio = _portfolio(_booking_position())
    fee = Fee(amount=Decimal("0.37000000"), asset="USDT")
    client = _StubClient({"BTCUSDT": [_filled_leg("BTCUSDT")]}, trades={"777": [_trade(fee=fee)]})

    await _driver(portfolio, client, persist_ledger=_RecordingWriter())(_candle())

    assert client.settled == ["777"]
    assert client.bounds[-1] == (BUDGET.timeout_s, BUDGET.attempts)
    assert portfolio.ledger is not None
    assert portfolio.ledger.realised_pnl == BOOK_EXACT - Decimal("0.37000000")
    assert portfolio.free_quote == Decimal("10000") + BOOK_TOTAL - Decimal("0.37000000")


async def test_the_booking_line_carries_the_settlement_it_was_booked_net_of(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """`exit_booked` carries all SEVEN settlement fields, read so an absent one FAILS.

    Answers `M5k-052`: until this test nothing read the line. TWO fills whose
    fees and times differ from each other and from the leg's creation time,
    so a line that logged one fill's fee, the EARLIEST fill time, the creation
    time as the fill time, or a fixed count would each fail. FABRICATED fees:
    every captured fee is zero. MUTATION: drop any of the seven fields, swap
    `order_created_at` and `filled_at`, or take `min` where `settle_exit`
    takes `max`.

    **READ THROUGH `vars()`, NOT BY ATTRIBUTE -- R3.** An `extra=` field is an
    instance attribute of the `LogRecord`, so `line.fee_asset` on a line that
    lacks it raises `AttributeError` before any comparison runs: a CRASH, not
    a kill, under `M5i-115`, and P29 measured exactly that. `.get()` turns the
    absence into a `None` the `==` rejects, as an `AssertionError`.
    """
    portfolio = _portfolio(_booking_position())
    first_quote = Decimal("1582.84000000")
    early = _trade(
        quantity=Decimal("0.02000000"),
        quote=first_quote,
        fee=Fee(amount=Decimal("0.30000000"), asset="USDT"),
    ).model_copy(update={"filled_at": NOW + timedelta(seconds=2)})
    late = _trade(
        quantity=Decimal("0.00257000"),
        quote=BOOK_TOTAL - first_quote,
        fee=Fee(amount=Decimal("0.07000000"), asset="USDT"),
    ).model_copy(update={"trade_id": "2", "filled_at": NOW + timedelta(seconds=5)})
    client = _StubClient({"BTCUSDT": [_filled_leg("BTCUSDT")]}, trades={"777": [early, late]})

    with caplog.at_level(logging.INFO):
        await _driver(portfolio, client, persist_ledger=_RecordingWriter())(_candle())

    booked = [r for r in caplog.records if getattr(r, "event", None) == "exit_booked"]
    assert len(booked) == 1
    line = vars(booked[0])
    assert {key: line.get(key) for key in _SEVEN} == {
        "order_id": "777",
        # The settlement's own sum, 0.02000000 + 0.00257000.
        "quantity": BOOK_QTY,
        "fee": Decimal("0.37000000"),
        "fee_asset": "USDT",
        "fills": 2,
        # The LATEST fill's matching-engine time ...
        "filled_at": (NOW + timedelta(seconds=5)).isoformat(),
        # ... and the leg's CREATION time, from `_filled_leg`, which is neither.
        "order_created_at": NOW.isoformat(),
    }
    assert str(line.get("fee")) == "0.37000000"  # the exponent, which `==` cannot see


async def test_an_unknown_order_creation_time_is_absent_from_exit_booked(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A leg record with no timestamp: the key is ABSENT, never `null`.

    MUTATION: emit `"order_created_at": None` -- the driver's own behaviour
    until the helper, and what `.get()` alone could not tell from absence.
    The other six fields are asserted present, so a line missing entirely
    cannot pass by containing nothing.
    """
    portfolio = _portfolio(_booking_position())
    leg = _filled_leg("BTCUSDT").model_copy(update={"created_at": None})
    client = _StubClient({"BTCUSDT": [leg]}, trades={"777": [_trade()]})

    with caplog.at_level(logging.INFO):
        await _driver(portfolio, client, persist_ledger=_RecordingWriter())(_candle())

    (record,) = [r for r in caplog.records if getattr(r, "event", None) == "exit_booked"]
    line = vars(record)
    assert "order_created_at" not in line
    assert {key: key in line for key in _SEVEN if key != "order_created_at"} == {
        key: True for key in _SEVEN if key != "order_created_at"
    }


@pytest.mark.parametrize("failing", ["BTCUSDT", "ETHUSDT"])
async def test_a_failed_settlement_skips_that_position_and_books_the_other(failing: str) -> None:
    """R-g: SKIP AND CONTINUE. Parametrised over which symbol fails, so one run has it FIRST.

    MUTATION: `return` where the skip continues -- the later symbol then books
    nothing in the run where the failure comes first.
    """
    eth_leg = _filled_leg("ETHUSDT").model_copy(update={"order_id": "778"})
    portfolio = _portfolio(_booking_position("BTCUSDT"), _booking_position("ETHUSDT"))
    failing_id = "777" if failing == "BTCUSDT" else "778"
    client = _StubClient(
        {"BTCUSDT": [_filled_leg("BTCUSDT")], "ETHUSDT": [eth_leg]},
        trades={failing_id: ExchangeConnectionError("timed out")},
    )
    writer = _RecordingWriter()

    await _driver(portfolio, client, persist_ledger=writer)(_candle())

    booked = "ETHUSDT" if failing == "BTCUSDT" else "BTCUSDT"
    assert failing in portfolio.positions
    assert booked not in portfolio.positions
    assert sorted(client.settled) == ["777", "778"]
    assert len(writer.calls) == 1


async def test_the_save_runs_when_a_later_position_raises() -> None:
    """The persist sits in a `finally`: an exit booked before a raise still reaches disk.

    MUTATION: move `_persist_booked` out of the `finally`. DECLARED: drives
    `_book_exits` directly, as the orphan-guard test above does, because the
    pass cannot hand it an orphan.
    """
    position = _booking_position()
    portfolio = _portfolio(position)
    client = _StubClient({"BTCUSDT": []}, trades={"777": [_trade()]})
    writer = _RecordingWriter()
    fill = ExitFill(order_id="777", filled_quantity=BOOK_QTY, filled_quote_quantity=BOOK_TOTAL)
    filled = ProtectionAssessment(state=ProtectionState.UNKNOWN, reason="filled", exit_fill=fill)
    driver = _driver(portfolio, client, persist_ledger=writer)

    with pytest.raises(ValueError, match="orphan"):
        await driver._book_exits(
            [(position, filled), (_booking_position("ETHUSDT"), filled)], now=NOW
        )

    assert "BTCUSDT" not in portfolio.positions
    assert len(writer.calls) == 1


@pytest.mark.parametrize(
    "trades",
    [
        [],
        [_trade(quantity=Decimal("0.02000000"))],
    ],
    ids=["no_fills", "short_fills"],
)
async def test_a_settlement_the_ledger_refuses_skips_and_keeps_the_position(
    trades: list[Trade], caplog: pytest.LogCaptureFixture
) -> None:
    """Ruling 5: caught around `settle_exit` at WARNING, and the position waits for a later pass.

    FABRICATED rows. MUTATION: let `FeeFillsIncompleteError` propagate -- the
    pass then logs a phase failure instead of a refusal -- or book anyway.

    **The `foreign_fee` row LEFT at R2**: a fee in an asset this ledger
    cannot subtract is terminal and is HELD, not refused -- see
    `test_an_unbookable_settlement_is_held_after_one_fetch`.
    """
    portfolio = _portfolio(_booking_position())
    client = _StubClient({"BTCUSDT": [_filled_leg("BTCUSDT")]}, trades={"777": trades})

    with caplog.at_level(logging.WARNING):
        await _driver(portfolio, client)(_candle())

    watched = {"exit_book_refused", "reconciliation_phase_failed"}
    events = [getattr(r, "event", None) for r in caplog.records]
    assert [e for e in events if e in watched] == ["exit_book_refused"]
    assert "BTCUSDT" in portfolio.positions
    assert portfolio.ledger is None


async def test_a_lagging_fill_list_is_retried_and_books_on_the_next_pass() -> None:
    """A short list on one pass, the whole list on the next: kept, then booked once.

    MUTATION: drop the position on a short list, or never re-fetch it.
    """
    portfolio = _portfolio(_booking_position())
    answers: dict[str, list[Trade] | Exception] = {"777": [_trade(quantity=Decimal("0.02000000"))]}
    client = _StubClient({"BTCUSDT": [_filled_leg("BTCUSDT")]}, trades=answers)
    ticks = iter([NOW, NOW + timedelta(minutes=2)])
    driver = _driver(portfolio, client, clock=lambda: next(ticks))

    await driver(_candle())
    assert "BTCUSDT" in portfolio.positions

    answers["777"] = [_trade()]
    await driver(_candle())

    assert client.settled == ["777", "777"]
    assert "BTCUSDT" not in portfolio.positions
    assert portfolio.ledger is not None
    assert portfolio.ledger.realised_pnl == BOOK_EXACT


# --------------------------------------------------------------------------
# R2 with ruling A: a terminal refusal HOLDS the position, and no pass visits it again
# --------------------------------------------------------------------------
#: The two terminal refusals, FABRICATED -- no captured SELL fill carries a
#: non-USDT fee, and none is a buy. Each is otherwise a complete fill of
#: `_filled_leg`'s order, so only the refusal's cause differs.
_TERMINAL = {
    "foreign_fee": [_trade(fee=Fee(amount=Decimal("0.00000100"), asset="BTC"))],
    "non_sell": [_trade().model_copy(update={"side": OrderSide.BUY})],
}
_CAUSE = {"foreign_fee": "foreign_fee_asset", "non_sell": "non_sell_fill"}


def _held_lines(caplog: pytest.LogCaptureFixture) -> list[logging.LogRecord]:
    return [r for r in caplog.records if getattr(r, "event", None) == "exit_settlement_held"]


@pytest.mark.parametrize("refusal", ["foreign_fee", "non_sell"])
async def test_an_unbookable_settlement_is_held_after_one_fetch(
    refusal: str, caplog: pytest.LogCaptureFixture
) -> None:
    """R2 + RULING A: one fetch, one CRITICAL, the mark -- then nothing, on any later pass.

    Pass 2 runs two minutes on, past the one-minute dedup interval, so the
    position is DUE: only ruling A keeps the pass away from it. MUTATION:
    refuse at WARNING instead of holding, or drop ruling A's filter.

    **THE PROTECTION ASSERTION PINS THE STATE, NOT THE HOLD'S WRITE.** The
    reconciliation pass already wrote `UNKNOWN` before `_book_exits` ran:
    `classify_protection`'s filled-leg branch returns it, and the resolver's
    verdicts are `UNKNOWN` or `DIVERGED` only. So this assertion CANNOT
    detect deletion of `hold_settlement`'s protection write -- MEASURED by
    P34's out-of-tree probe, `SITE C start=ACTIVE`, pre-hold `'unknown'`.
    `test_the_driver_hold_writes_unknown_over_a_trusted_state` pins the write.
    """
    position = _booking_position()
    portfolio = _portfolio(position)
    client = _StubClient({"BTCUSDT": [_filled_leg("BTCUSDT")]}, trades={"777": _TERMINAL[refusal]})
    ticks = iter([NOW, NOW + timedelta(minutes=2)])
    driver = _driver(portfolio, client, clock=lambda: next(ticks))

    with caplog.at_level(logging.DEBUG):
        await driver(_candle())

        assert client.settled == ["777"]
        lines = _held_lines(caplog)
        assert len(lines) == 1  # asserted, never unpacked: a ValueError is a crash (M5i-115)
        line = lines[0]
        assert line.levelno == logging.CRITICAL
        assert vars(line).get("cause") == _CAUSE[refusal]
        assert vars(line).get("order_id") == "777"
        assert position.settlement_hold is True
        assert position.protection is ProtectionState.UNKNOWN
        assert portfolio.positions["BTCUSDT"] is position
        assert portfolio.ledger is None
        asked, queried = list(client.asked), list(client.queried)

        await driver(_candle())

    assert client.asked == asked
    assert client.queried == queried
    assert client.settled == ["777"]
    assert len(_held_lines(caplog)) == 1
    assert [r for r in caplog.records if getattr(r, "event", None) == "exit_book_refused"] == []


def _cancelled_leg() -> Order:
    """The stop leg as the executor's close leaves it: CANCELED, nothing executed."""
    return Order(
        order_id="9",
        symbol="BTCUSDT",
        side=OrderSide.SELL,
        type=OrderType.STOP_LOSS,
        status=OrderStatus.CANCELED,
        quantity=BOOK_QTY,
        filled_quantity=Decimal("0"),
        stop_price=STOP,
        order_list_id=VENUE_LIST_ID,
        client_order_id=client_order_id("BTCUSDT", BAR, OrderListLeg.STOP_LOSS, generation=0),
    )


async def test_a_held_position_with_cancelled_legs_is_never_escalated(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """RULING A precedes classification: a held position never reaches the DIVERGED escalation.

    The executor-held shape -- its list cancelled by the close, nothing
    resting, the stop point-queried as CANCELED -- classifies DIVERGED with no
    fill, which escalates `exit_unbookable` at CRITICAL on EVERY pass for an
    unheld position (P30's measurement). Two due passes here, and none of it
    happens. MUTATION: drop ruling A's filter.
    """
    position = _booking_position()
    position.hold_settlement()
    sl = client_order_id("BTCUSDT", BAR, OrderListLeg.STOP_LOSS, generation=0)
    client = _StubClient({"BTCUSDT": []}, orders={sl: _cancelled_leg()})
    ticks = iter([NOW, NOW + timedelta(minutes=2)])
    driver = _driver(_portfolio(position), client, clock=lambda: next(ticks))

    with caplog.at_level(logging.DEBUG):
        await driver(_candle())
        await driver(_candle())

    assert [r for r in caplog.records if getattr(r, "event", None) == "exit_unbookable"] == []
    assert (client.asked, client.queried, client.settled) == ([], [], [])


async def test_the_driver_stores_nothing_across_passes() -> None:
    """M5e: the hold is on the POSITION; the driver's own attributes are untouched by it.

    MUTATION: remember the held symbol on the driver instead -- a new
    attribute, whatever else it still does.
    """
    portfolio = _portfolio(_booking_position())
    client = _StubClient(
        {"BTCUSDT": [_filled_leg("BTCUSDT")]}, trades={"777": _TERMINAL["foreign_fee"]}
    )
    driver = _driver(portfolio, client)
    before = set(vars(driver))

    await driver(_candle())

    assert portfolio.positions["BTCUSDT"].settlement_hold is True
    assert set(vars(driver)) == before


@pytest.mark.parametrize("refusal", ["foreign_fee", "non_sell"])
async def test_the_driver_hold_writes_unknown_over_a_trusted_state(
    refusal: str, caplog: pytest.LogCaptureFixture
) -> None:
    """PIN-5 at the driver: `_settle`'s hold writes `UNKNOWN` over a TRUSTED state.

    **A trusted state is UNREACHABLE at this site in production.** The
    resolver's verdicts are `UNKNOWN` or `DIVERGED` only, and
    `classify_protection`'s filled-leg branch returns `UNKNOWN`, so every
    pass writes an untrusted state before `_book_exits` hands `_settle` a
    fill. This test pins the write as DEFENCE IN DEPTH, per the project
    owner's ruling PIN-5, by driving `_settle` directly below the pass --
    precedent: `test_the_save_runs_when_a_later_position_raises`, which
    drives `_book_exits` the same way. MUTATION: delete the protection write
    from `hold_settlement`.
    """
    position = _booking_position().model_copy(update={"protection": ProtectionState.ACTIVE})
    portfolio = _portfolio(position)
    client = _StubClient({"BTCUSDT": []}, trades={"777": _TERMINAL[refusal]})
    fill = ExitFill(order_id="777", filled_quantity=BOOK_QTY, filled_quote_quantity=BOOK_TOTAL)
    driver = _driver(portfolio, client)
    assert position.protection is ProtectionState.ACTIVE

    with caplog.at_level(logging.DEBUG):
        result = await driver._settle("BTCUSDT", fill)

    assert result is None
    assert position.protection is ProtectionState.UNKNOWN
    assert position.settlement_hold is True
    lines = _held_lines(caplog)
    assert len(lines) == 1
    assert lines[0].levelno == logging.CRITICAL
    assert vars(lines[0]).get("cause") == _CAUSE[refusal]
