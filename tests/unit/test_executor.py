"""The order executor -- dispatch, the two refusals, and Option 4 resolution.

Fixture expressiveness, stated because it decides what these can catch:

* A double whose placements always succeed **cannot express the ambiguous
  write**. ``FakeClient`` therefore takes an explicit ``place_error`` so a
  failing placement is a first-class fixture rather than an afterthought.
* A fixture that never emits ``CLOSE`` **cannot express its refusal**, so
  ``exit_assessment`` builds a real ``ExitIntent`` -- the shape
  ``RiskManager.evaluate`` produces today, not a stand-in.
* A budget whose deadline never expires cannot express exhaustion, so
  ``DispatchBudget(deadline_s=0.0)`` is used where that is the subject.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any

import pytest

from trading_bot.core.assessment import EntryIntent, ExitIntent, RiskAssessment
from trading_bot.core.enums import (
    OrderSide,
    PositionSide,
    ProtectionState,
    RefusalStage,
    SignalAction,
)
from trading_bot.core.models import (
    Candle,
    OrderList,
    OtocoOrderListRequest,
    OtoOrderListRequest,
    ProtectiveLevels,
    Signal,
)
from trading_bot.core.portfolio import Portfolio
from trading_bot.execution.dispatch_budget import DispatchBudget
from trading_bot.execution.executor import OrderExecutor, PendingPlacement
from trading_bot.execution.resolution import PlacementOutcome, PlacementVerdict

D = Decimal

SYMBOL = "BTCUSDT"
BAR = datetime(2024, 5, 1, 12, 0, tzinfo=timezone.utc)
_EXEC_LOGGER = "trading_bot.execution.executor"


# --------------------------------------------------------------------------
# Fixtures
# --------------------------------------------------------------------------
def candle(*, close_time: datetime = BAR) -> Candle:
    return Candle(
        symbol=SYMBOL,
        timeframe="1m",
        open_time=close_time - timedelta(minutes=1),
        close_time=close_time,
        open=D("100"),
        high=D("101"),
        low=D("99"),
        close=D("100"),
        volume=D("10"),
        is_closed=True,
    )


def buy() -> Signal:
    return Signal(
        symbol=SYMBOL, action=SignalAction.BUY, price=D("100"), timestamp=BAR, strategy="t"
    )


def close_signal() -> Signal:
    return Signal(
        symbol=SYMBOL, action=SignalAction.CLOSE, price=D("100"), timestamp=BAR, strategy="t"
    )


def levels(*, stop: str | None = "95", target: str | None = "110") -> ProtectiveLevels:
    return ProtectiveLevels(
        symbol=SYMBOL,
        side=PositionSide.LONG,
        entry_price=D("100"),
        stop_loss=D(stop) if stop is not None else None,
        take_profit=D(target) if target is not None else None,
        stop_distance=D("5") if stop is not None else None,
        basis="test",
    )


def entry_assessment(*, stop: str | None = "95", target: str | None = "110") -> RiskAssessment:
    intent = EntryIntent(
        symbol=SYMBOL,
        side=OrderSide.BUY,
        quantity=D("0.5"),
        reference_price=D("100"),
        entry_limit=D("100"),
        levels=levels(stop=stop, target=target),
    )
    return RiskAssessment(
        symbol=SYMBOL, approved=True, reason="ok", stage=None, intent=intent, levels=intent.levels
    )


def exit_assessment() -> RiskAssessment:
    intent = ExitIntent(
        symbol=SYMBOL, side=OrderSide.SELL, quantity=D("0.5"), reference_price=D("100")
    )
    return RiskAssessment(symbol=SYMBOL, approved=True, reason="ok", stage=None, intent=intent)


def refused_assessment() -> RiskAssessment:
    return RiskAssessment(
        symbol=SYMBOL, approved=False, reason="no", stage=RefusalStage.LIMIT_REFUSED
    )


def placed_list(list_id: str = "tb1-BTCUSDT-1714564800000-0-L") -> OrderList:
    return OrderList(
        order_list_id="1",
        list_client_order_id=list_id,
        list_order_status="EXECUTING",
        list_status_type="EXEC_STARTED",
        symbol=SYMBOL,
        orders=(),
    )


class FakeClient:
    """Records placements; can be made to fail, which is what expresses S-ambiguous."""

    def __init__(self, *, place_error: Exception | None = None) -> None:
        self.place_error = place_error
        self.otoco: list[OtocoOrderListRequest] = []
        self.oto: list[OtoOrderListRequest] = []
        self.bounds: list[tuple[float | None, int | None]] = []

    async def create_otoco_order_list(
        self,
        request: OtocoOrderListRequest,
        *,
        timeout_s: float | None = None,
        attempts: int | None = None,
    ) -> OrderList:
        self.bounds.append((timeout_s, attempts))
        if self.place_error is not None:
            raise self.place_error
        self.otoco.append(request)
        return placed_list()

    async def create_oto_order_list(
        self,
        request: OtoOrderListRequest,
        *,
        timeout_s: float | None = None,
        attempts: int | None = None,
    ) -> OrderList:
        self.bounds.append((timeout_s, attempts))
        if self.place_error is not None:
            raise self.place_error
        self.oto.append(request)
        return placed_list()


def build(
    *, client: Any = None, deadline_s: float = 9.0, portfolio: Portfolio | None = None
) -> tuple[OrderExecutor, FakeClient, Portfolio]:
    resolved_client = client if client is not None else FakeClient()
    resolved_portfolio = portfolio if portfolio is not None else Portfolio(free_quote=D("10000"))
    executor = OrderExecutor(
        client=resolved_client,  # type: ignore[arg-type]
        portfolio=resolved_portfolio,
        budget=DispatchBudget(deadline_s=deadline_s),
    )
    return executor, resolved_client, resolved_portfolio


def _records(caplog: pytest.LogCaptureFixture, event: str) -> list[logging.LogRecord]:
    """By logger NAME, never by position -- caplog captures collaborators too."""
    return [
        r for r in caplog.records if r.name == _EXEC_LOGGER and getattr(r, "event", None) == event
    ]


# --------------------------------------------------------------------------
# Dispatch, happy path
# --------------------------------------------------------------------------
class TestDispatch:
    async def test_an_approved_entry_places_an_otoco_list(self) -> None:
        executor, client, _ = build()

        await executor.dispatch(buy(), entry_assessment(), candle())

        assert len(client.otoco) == 1
        assert client.otoco[0].symbol == SYMBOL

    async def test_a_stop_only_entry_places_an_oto_list(self) -> None:
        executor, client, _ = build()

        await executor.dispatch(buy(), entry_assessment(target=None), candle())

        assert len(client.oto) == 1
        assert client.otoco == []

    async def test_the_per_call_bounds_reach_the_client(self) -> None:
        """The dispatch budget is SPENT, not merely held."""
        executor, client, _ = build()

        await executor.dispatch(buy(), entry_assessment(), candle())

        timeout_s, attempts = client.bounds[0]
        assert timeout_s is not None and timeout_s > 0
        assert attempts == 1

    async def test_the_seed_is_the_candles_close_time_not_the_signals_timestamp(self) -> None:
        """R20. The signal carries a DIFFERENT time here, so the two are
        distinguishable -- a fixture where they agreed could not express this,
        and `Signal.timestamp` defaults to wall-clock when a strategy omits it.
        """
        executor, client, _ = build()
        other_bar = BAR + timedelta(minutes=7)

        await executor.dispatch(buy(), entry_assessment(), candle(close_time=other_bar))

        assert client.otoco[0].entry_bar_time == other_bar

    async def test_a_refused_assessment_dispatches_nothing(self) -> None:
        executor, client, _ = build()

        await executor.dispatch(buy(), refused_assessment(), candle())

        assert client.otoco == [] and client.oto == []


# --------------------------------------------------------------------------
# R19 -- position construction
# --------------------------------------------------------------------------
class TestPositionConstruction:
    async def test_the_position_is_constructed_unknown(self) -> None:
        """M5e-075. A placement response is not an observation of what rests."""
        executor, _, portfolio = build()

        await executor.dispatch(buy(), entry_assessment(), candle())

        position = portfolio.positions[SYMBOL]
        assert position.protection is ProtectionState.UNKNOWN

    async def test_the_position_carries_the_requested_levels_and_the_list_id(self) -> None:
        """Reconciliation is keyed off what was REQUESTED, so the position must
        carry them or the reconciler is structurally silent on it."""
        executor, _, portfolio = build()

        await executor.dispatch(buy(), entry_assessment(), candle())

        position = portfolio.positions[SYMBOL]
        assert position.stop_loss == D("95")
        assert position.take_profit == D("110")
        assert position.order_list_id == "tb1-BTCUSDT-1714564800000-0-L"
        assert position.entry_bar_time == BAR

    async def test_no_position_is_recorded_when_the_placement_fails(self) -> None:
        executor, _, portfolio = build(client=FakeClient(place_error=TimeoutError("reset")))

        await executor.dispatch(buy(), entry_assessment(), candle())

        assert SYMBOL not in portfolio.positions


# --------------------------------------------------------------------------
# R21 -- the two dispatch-site refusals
# --------------------------------------------------------------------------
class TestRefusals:
    async def test_close_is_refused_loudly_and_by_name(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """`RiskManager.evaluate` produces an `ExitIntent` today, so this is
        reachable. A DROPPED signal is how an operator finds the gap by not
        seeing an exit; the refusal must name itself."""
        executor, client, _ = build()

        with caplog.at_level(logging.DEBUG, logger=_EXEC_LOGGER):
            await executor.dispatch(close_signal(), exit_assessment(), candle())

        refusals = _records(caplog, "dispatch_refused")
        assert len(refusals) == 1
        assert refusals[0].reason == "close_not_implemented"  # type: ignore[attr-defined]
        assert refusals[0].action == "CLOSE"  # type: ignore[attr-defined]
        assert client.otoco == [] and client.oto == []

    async def test_the_unprotected_branch_is_refused(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Both-disabled stays LEGAL at config load; only dispatch is refused."""
        executor, client, _ = build()

        with caplog.at_level(logging.DEBUG, logger=_EXEC_LOGGER):
            await executor.dispatch(buy(), entry_assessment(stop=None, target=None), candle())

        refusals = _records(caplog, "dispatch_refused")
        assert len(refusals) == 1
        assert refusals[0].reason == "unprotected_branch"  # type: ignore[attr-defined]
        assert client.otoco == [] and client.oto == []

    async def test_an_exhausted_budget_refuses_rather_than_dispatching(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """A budget may refuse to BEGIN work; it must never abandon one in flight."""
        executor, client, _ = build(deadline_s=0.0)

        with caplog.at_level(logging.DEBUG, logger=_EXEC_LOGGER):
            await executor.dispatch(buy(), entry_assessment(), candle())

        assert len(_records(caplog, "dispatch_refused")) == 1
        assert client.otoco == []


# --------------------------------------------------------------------------
# R22 -- Option 4 resolution
# --------------------------------------------------------------------------
class TestOptionFourResolution:
    async def test_a_failed_placement_leaves_a_pending_record(self) -> None:
        executor, _, _ = build(client=FakeClient(place_error=TimeoutError("reset")))

        await executor.dispatch(buy(), entry_assessment(), candle())

        assert executor._pending[SYMBOL] == PendingPlacement(
            symbol=SYMBOL, entry_bar_time=BAR, generation=0
        )

    async def test_a_successful_placement_leaves_no_pending_record(self) -> None:
        executor, _, _ = build()

        await executor.dispatch(buy(), entry_assessment(), candle())

        assert executor._pending == {}

    async def test_a_second_dispatch_is_refused_while_one_is_pending(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Narrows the orphan window to the process-death case."""
        client = FakeClient(place_error=TimeoutError("reset"))
        executor, _, _ = build(client=client)
        await executor.dispatch(buy(), entry_assessment(), candle())
        client.place_error = None

        with caplog.at_level(logging.DEBUG, logger=_EXEC_LOGGER):
            await executor.dispatch(buy(), entry_assessment(), candle())

        assert client.otoco == []
        refusals = _records(caplog, "dispatch_refused")
        assert len(refusals) == 1
        # ITS OWN REASON, not the budget's. Reusing "budget_exhausted" here --
        # which this code did until the mutation survey prompted a re-read --
        # sends an operator to tune the deadline for a cause that is not it.
        assert refusals[0].reason == "placement_pending"  # type: ignore[attr-defined]

    async def test_the_next_bar_resolves_and_clears_the_record(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        executor, _, _ = build(client=FakeClient(place_error=TimeoutError("reset")))
        await executor.dispatch(buy(), entry_assessment(), candle())

        async def _resolved(*_a: Any, **_k: Any) -> PlacementVerdict:
            return PlacementVerdict(outcome=PlacementOutcome.NOT_PLACED, reason="nothing rests")

        monkeypatch.setattr("trading_bot.execution.executor.resolve_placement", _resolved)
        await executor(candle(close_time=BAR + timedelta(minutes=1)))

        assert executor._pending == {}

    async def test_an_unresolved_verdict_keeps_the_record_and_does_not_re_place(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """FAIL-CLOSED. `CLAUDE.md`'s locked rule says re-place; the owner
        ruled the opposite and this is where that becomes live code."""
        client = FakeClient(place_error=TimeoutError("reset"))
        executor, _, _ = build(client=client)
        await executor.dispatch(buy(), entry_assessment(), candle())
        client.place_error = None

        async def _unresolved(*_a: Any, **_k: Any) -> PlacementVerdict:
            return PlacementVerdict(outcome=PlacementOutcome.UNRESOLVED, reason="query failed")

        monkeypatch.setattr("trading_bot.execution.executor.resolve_placement", _unresolved)
        await executor(candle(close_time=BAR + timedelta(minutes=1)))

        assert SYMBOL in executor._pending
        assert client.otoco == []  # NOT re-placed

    async def test_a_raising_resolver_is_contained_and_the_record_survives(
        self, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        executor, _, _ = build(client=FakeClient(place_error=TimeoutError("reset")))
        await executor.dispatch(buy(), entry_assessment(), candle())

        async def _boom(*_a: Any, **_k: Any) -> PlacementVerdict:
            raise RuntimeError("resolver down")

        monkeypatch.setattr("trading_bot.execution.executor.resolve_placement", _boom)
        with caplog.at_level(logging.DEBUG, logger=_EXEC_LOGGER):
            await executor(candle())  # must not raise

        assert SYMBOL in executor._pending
        assert len(_records(caplog, "collaborator_failed")) == 1

    async def test_a_bar_with_nothing_pending_queries_nothing(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Predicted to be the cheap path: no pending record, no I/O at all."""
        executor, _, _ = build()
        calls: list[int] = []

        async def _spy(*_a: Any, **_k: Any) -> PlacementVerdict:
            calls.append(1)
            return PlacementVerdict(outcome=PlacementOutcome.NOT_PLACED, reason="x")

        monkeypatch.setattr("trading_bot.execution.executor.resolve_placement", _spy)
        await executor(candle())

        assert calls == []
