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
from trading_bot.core.portfolio import Portfolio
from trading_bot.exchange.ids import OrderListLeg, client_order_id
from trading_bot.execution import reconciliation_driver as driver_module
from trading_bot.execution.reconciliation_driver import (
    ReconciliationBudget,
    ReconciliationDriver,
)

NOW = datetime(2026, 8, 15, 12, 0, tzinfo=timezone.utc)
BAR = datetime(2026, 8, 15, 11, 0, tzinfo=timezone.utc)
QTY = Decimal("0.00100000")
STOP = Decimal("44117.09")
LIST_ID = "91590"

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
        order_list_id=LIST_ID,
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
        order_list_id=LIST_ID,
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
