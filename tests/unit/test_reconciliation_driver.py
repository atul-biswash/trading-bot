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
from trading_bot.core.models import Candle, Order, Position
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
    ) -> None:
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


async def test_a_pass_with_no_fill_books_nothing_and_saves_nothing() -> None:
    """Row 4 -- the ordinary healthy pass, and the commonest bar there is.

    MUTATION: book unconditionally, or save once per pass regardless of
    `booked`. The second is the one worth catching: an unconditional save
    fsyncs the file every bar on a bot that is doing nothing.
    """
    portfolio = _portfolio(_booking_position())
    client = _StubClient({"BTCUSDT": [_order("BTCUSDT", OrderListLeg.STOP_LOSS)]})
    writer = _RecordingWriter()

    await _driver(portfolio, client, persist_ledger=writer)(_candle())

    assert portfolio.ledger is None
    assert "BTCUSDT" in portfolio.positions
    assert writer.calls == []


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
        driver._book_exits([(stranger, assessment)], now=NOW)

    # And through `__call__` the same failure is contained, not raised.
    with caplog.at_level(logging.ERROR):
        await driver(_candle())
    assert portfolio.ledger is None
