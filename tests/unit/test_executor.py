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

import ast
import inspect
import logging
from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from trading_bot.core.assessment import EntryIntent, ExitIntent, RiskAssessment
from trading_bot.core.enums import (
    OrderSide,
    OrderStatus,
    OrderType,
    PositionSide,
    ProtectionState,
    RefusalStage,
    SignalAction,
)
from trading_bot.core.exceptions import (
    ClientFilterRejectedError,
    ExchangeConnectionError,
    FilterRejectedError,
    OrderNotFoundError,
    SymbolInfoNotPrimedError,
)
from trading_bot.core.models import (
    Candle,
    Fee,
    Order,
    OrderList,
    OrderRequest,
    OtocoOrderListRequest,
    OtoOrderListRequest,
    Position,
    ProtectiveLevels,
    Signal,
    Trade,
)
from trading_bot.core.portfolio import Portfolio
from trading_bot.execution.dispatch_budget import CallBounds, DispatchBudget
from trading_bot.execution.executor import (
    OrderExecutor,
    Pending,
    PendingClose,
    PendingPlacement,
)
from trading_bot.execution.resolution import PlacementOutcome, PlacementVerdict

D = Decimal

SYMBOL = "BTCUSDT"
BAR = datetime(2024, 5, 1, 12, 0, tzinfo=timezone.utc)
_EXEC_LOGGER = "trading_bot.execution.executor"
#: The settlement bound the composition root derives from
#: `reconcile_deadline_s` at one attempt, at the shipped value.
SETTLEMENT_BOUNDS = CallBounds(timeout_s=3.0, attempts=1)


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


#: THE VENUE's numeric list id -- the real one from the first live run.
#:
#: **It was ``"1"`` until M5h, and ``"1"`` cannot express the bug the two id
#: fields exist to prevent.** A one-character numeric string sits close enough
#: to any placeholder that a test asserting it could pass for the wrong reason;
#: this value is unmistakably the venue's and unmistakably not a ``tb1-`` id.
VENUE_LIST_ID = "255471"
#: OURS, derived. Deliberately a different SHAPE, not merely a different value.
CLIENT_LIST_ID = "tb1-BTCUSDT-1714564800000-0-L"


def placed_list(list_id: str = CLIENT_LIST_ID, *, venue_id: str = VENUE_LIST_ID) -> OrderList:
    return OrderList(
        order_list_id=venue_id,
        list_client_order_id=list_id,
        list_order_status="EXECUTING",
        list_status_type="EXEC_STARTED",
        symbol=SYMBOL,
        orders=(),
    )


def live_verdict(list_id: str = "tb1-BTCUSDT-1714564800000-0-L") -> PlacementVerdict:
    """A PLACED_LIVE verdict carrying the list it matched.

    A fake whose resolver always returns NOT_PLACED cannot express any of the
    R24 behaviour, which is why this exists: until it did, all three resolution
    tests returned NOT_PLACED and the live branch was driven by nothing.
    """
    return PlacementVerdict(
        outcome=PlacementOutcome.PLACED_LIVE,
        reason="one live match",
        matched=(placed_list(list_id),),
    )


def terminal_verdict() -> PlacementVerdict:
    return PlacementVerdict(
        outcome=PlacementOutcome.PLACED_TERMINAL,
        reason="one terminal match",
        matched=(
            OrderList(
                order_list_id="2",
                list_client_order_id="tb1-BTCUSDT-1714564800000-0-L",
                list_order_status="ALL_DONE",
                list_status_type="ALL_DONE",
                symbol=SYMBOL,
                orders=(),
            ),
        ),
    )


class FakeClient:
    """Records placements; can be made to fail, which is what expresses S-ambiguous.

    **It serves ``get_order`` because dispatch now calls it**, and a raise here
    would make the fixture rather than the code decide the result -- the same
    reasoning ``FakeRootClient.get_all_order_lists`` records for the boot scan.
    ``venue_calls`` counts EVERY method that stands for a venue round trip, so
    the call-count guard has one number to assert against.

    **The fill price is BELOW the intent's limit of 100 and COHERENT with it,
    which it was not until the debit used it.** It was a real measured figure,
    ``76649.80``, against an ``entry_limit`` of 100 -- fine while the fill only
    landed on a field, and a 38,324.90 debit against a 10,000 balance once it
    drove the money. Realism about the VALUE mattered less than realism about
    the RELATIONSHIP: request above fill, which is what all five measured
    instances show.
    """

    def __init__(
        self,
        *,
        place_error: Exception | None = None,
        fill_price: str | None = "98.00000000",
        filled_quantity: str = "0.5",
        order_error: Exception | None = None,
        leg_answers: dict[str, Order | Exception] | None = None,
        cancel_answer: Exception | None = None,
        sell_answer: Order | Exception | None = None,
        trades_answers: list[list[Trade] | Exception] | None = None,
    ) -> None:
        #: What `get_my_trades` answers, in order; the LAST answer repeats.
        #: ``None`` answers one fill mirroring the default sell -- the whole
        #: executed quantity at the venue's total, fee `0.00000000` USDT, the
        #: measured value -- so a close that only needs to book settles.
        self._trades_answers = trades_answers
        #: ``(order_id, timeout_s, attempts)`` per settlement fetch.
        self.settlements: list[tuple[str | None, float | None, int | None]] = []
        #: What the list cancel does. ``None`` succeeds; an exception is raised.
        #: `OrderNotFoundError` is how a test says ``-2011``, which is NORMAL on
        #: this path rather than a failure.
        self._cancel_answer = cancel_answer
        #: What the MARKET sell returns, or raises. ``None`` fills completely at
        #: a quote total, which is the ordinary case.
        #:
        #: **THESE TWO ARE WRITES AND EVERY EXISTING TEST LEAVES THEM ALONE.**
        #: Defaults keep the fake's behaviour identical for anything that does
        #: not close a position; only the close tests configure them.
        self._sell_answer = sell_answer
        #: PER-LEG answers for the close path's confirming query, keyed by leg
        #: code (``"SL"`` / ``"TP"``).
        #:
        #: **THE FLAT FIELDS BELOW CANNOT EXPRESS THE CLOSE TABLE, and that is
        #: why this exists.** `fill_price` and `filled_quantity` are shared by
        #: every `get_order` answer, so a fake carrying only those returns the
        #: SAME order for both protective legs -- it cannot say "the stop filled
        #: and the target did not", which is the row that decides
        #: ALREADY_CLOSED, and it cannot make one leg unreadable while the other
        #: answers, which is the row that decides HALT.
        #:
        #: ``None`` keeps the flat behaviour exactly, so every test written
        #: before the close path is unchanged.
        self._leg_answers = leg_answers
        self.place_error = place_error
        #: ``None`` makes the entry leg report no fill -- an expired FOK.
        self.fill_price = fill_price
        self.filled_quantity = filled_quantity
        #: Makes the fill query itself fail, which is a different `None` than
        #: the one above and must stay separately expressible.
        self.order_error = order_error
        self.otoco: list[OtocoOrderListRequest] = []
        self.oto: list[OtoOrderListRequest] = []
        self.bounds: list[tuple[float | None, int | None]] = []
        self.order_queries: list[str] = []
        #: Every venue round trip this fake served, in order.
        self.venue_calls: list[str] = []
        #: ``(symbol, order_list_id)`` per cancel, and the SELL requests.
        self.cancelled: list[tuple[str, int]] = []
        self.sold: list[OrderRequest] = []

    async def get_order(
        self,
        symbol: str,
        *,
        order_id: str | None = None,
        client_order_id: str | None = None,
        timeout_s: float | None = None,
        attempts: int | None = None,
    ) -> Order:
        self.venue_calls.append("get_order")
        self.order_queries.append(client_order_id or "")
        if self._leg_answers is not None:
            # Keyed off the id's own leg suffix, so a test states its answers in
            # the vocabulary the code derives rather than restating a full id.
            leg = (client_order_id or "").rsplit("-", 1)[-1]
            answer = self._leg_answers[leg]
            if isinstance(answer, Exception):
                raise answer
            return answer
        if self.order_error is not None:
            raise self.order_error
        filled = D(self.filled_quantity) if self.fill_price is not None else D("0")
        return Order(
            order_id="1",
            symbol=symbol,
            side=OrderSide.BUY,
            type=OrderType.LIMIT,
            status=OrderStatus.FILLED if self.fill_price is not None else OrderStatus.EXPIRED,
            quantity=D(self.filled_quantity),
            filled_quantity=filled,
            average_price=None if self.fill_price is None else D(self.fill_price),
            client_order_id=client_order_id,
        )

    async def create_otoco_order_list(
        self,
        request: OtocoOrderListRequest,
        *,
        timeout_s: float | None = None,
        attempts: int | None = None,
    ) -> OrderList:
        self.venue_calls.append("place")
        self.bounds.append((timeout_s, attempts))
        if self.place_error is not None:
            raise self.place_error
        self.otoco.append(request)
        return placed_list()

    async def cancel_order_list(
        self,
        symbol: str,
        order_list_id: int,
        *,
        timeout_s: float | None = None,
        attempts: int | None = None,
    ) -> OrderList:
        """The list cancel. Records the numeric id it was actually given.

        Recording the id is what lets a test assert the close cancelled by the
        VENUE's number rather than by ours -- the substitution that cost 28
        false verdicts in run 1 and that `Position` now separates by type.
        """
        self.venue_calls.append("cancel_order_list")
        self.cancelled.append((symbol, order_list_id))
        if self._cancel_answer is not None:
            raise self._cancel_answer
        return placed_list()

    async def create_order(self, request: OrderRequest) -> Order:
        """The MARKET sell. Records the request so its shape can be asserted."""
        self.venue_calls.append("create_order")
        self.sold.append(request)
        if isinstance(self._sell_answer, Exception):
            raise self._sell_answer
        if self._sell_answer is not None:
            return self._sell_answer
        return sell_fill()

    async def get_my_trades(
        self,
        symbol: str,
        *,
        order_id: str | None = None,
        limit: int | None = None,
        timeout_s: float | None = None,
        attempts: int | None = None,
    ) -> list[Trade]:
        """The settlement read. Counted in `venue_calls` like every round trip."""
        self.venue_calls.append("get_my_trades")
        self.settlements.append((order_id, timeout_s, attempts))
        if self._trades_answers is None:
            return [sell_trade(order_id=order_id or "777")]
        answer = (
            self._trades_answers.pop(0)
            if len(self._trades_answers) > 1
            else self._trades_answers[0]
        )
        if isinstance(answer, Exception):
            raise answer
        return list(answer)

    async def get_all_order_lists(
        self,
        *,
        timeout_s: float | None = None,
        attempts: int | None = None,
    ) -> list[OrderList]:
        """The enumeration ``resolve_placement`` asks.

        **IT EXISTS SO A ROUTING MISTAKE IS OBSERVABLE**, and it was added
        because a mutation proved invisible without it. Before it, this fake
        had no such method: a record wrongly routed to ``resolve_placement``
        made the call raise ``AttributeError``, which that function catches
        INTERNALLY and converts to an ``UNRESOLVED`` verdict -- so nothing
        escaped, nothing was logged, and ``venue_calls`` stayed empty. A close
        that was resolved-and-failed looked exactly like one that was skipped.

        Returning empty rather than raising, for ``FakeRootClient``'s stated
        reason: an unconfigured answer from a venue call is a real
        classification, and a raise would let the fixture decide the result.
        """
        self.venue_calls.append("get_all_order_lists")
        return []

    async def create_oto_order_list(
        self,
        request: OtoOrderListRequest,
        *,
        timeout_s: float | None = None,
        attempts: int | None = None,
    ) -> OrderList:
        self.venue_calls.append("place")
        self.bounds.append((timeout_s, attempts))
        if self.place_error is not None:
            raise self.place_error
        self.oto.append(request)
        return placed_list()


class RecordingWriter:
    """Captures every durable write; can be made to fail.

    Stands in for the composition root's closure. It records the tuple it was
    handed on every call, so a test can assert what reached DISK independently
    of what remains in memory -- which is the whole of what U2's Reading A
    turns on.
    """

    def __init__(self, *, error: Exception | None = None, fail_from: int = 0) -> None:
        self.error = error
        #: Index of the first call that raises. ``0`` fails the durable write
        #: before the venue call; ``1`` lets that one through and fails the
        #: rewrite after removal -- which is the only way to reach FORK 3's
        #: path, since FORK 1 puts the write first.
        self.fail_from = fail_from
        self.calls: list[tuple[PendingPlacement, ...]] = []

    def __call__(self, records: tuple[PendingPlacement, ...]) -> None:
        index = len(self.calls)
        self.calls.append(records)
        if self.error is not None and index >= self.fail_from:
            raise self.error

    def symbols(self, index: int = -1) -> list[str]:
        return [record.symbol for record in self.calls[index]]


def build(
    *,
    client: Any = None,
    deadline_s: float = 9.0,
    portfolio: Portfolio | None = None,
    persist: Any = None,
) -> tuple[OrderExecutor, FakeClient, Portfolio]:
    resolved_client = client if client is not None else FakeClient()
    resolved_portfolio = portfolio if portfolio is not None else Portfolio(free_quote=D("10000"))
    executor = OrderExecutor(
        client=resolved_client,  # type: ignore[arg-type]
        portfolio=resolved_portfolio,
        budget=DispatchBudget(deadline_s=deadline_s),
        settlement_bounds=SETTLEMENT_BOUNDS,
        persist_pending=persist,
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
        seeing an exit; the refusal must name itself.

        **THE REASON MOVED FROM `close_not_implemented` TO A PER-VERDICT
        STRING**, because the close path now PLANS before it refuses. What this
        test pins is unchanged and is the part that must not regress: a CLOSE
        still places nothing, and it still refuses under a name. Which name
        depends on what the confirming query found, and the verdicts have their
        own tests in `TestTheClosePlan`.

        Driven against a portfolio holding the position, so the plan runs; the
        no-position path is pinned separately.

        **DRIVEN TO A HALT VERDICT SINCE M5h's C5.** A `SELL` plan no longer
        refuses -- it cancels, re-confirms and sells. The refusal-by-name
        contract still holds for every verdict that does NOT sell, which is what
        this asserts; the executing path has its own suite.
        """
        client = FakeClient(leg_answers={"SL": _leg("0.2"), "TP": _leg("0")})
        executor, _, _ = build(client=client, portfolio=_held())

        with caplog.at_level(logging.DEBUG, logger=_EXEC_LOGGER):
            await executor.dispatch(close_signal(), exit_assessment(), candle())

        refusals = _records(caplog, "dispatch_refused")
        assert len(refusals) == 1
        assert refusals[0].reason.startswith("close_")  # type: ignore[attr-defined]
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
        """A budget may refuse to BEGIN work; it must never abandon one in flight.

        THE REASON IS ASSERTED, not only the refusal. A swap mutation --
        exchanging this reason with the pending-placement one -- returned 1
        rather than 2, and the 1 was the finding: an assertion on the COUNT
        survives being handed the wrong reason, so the two refusals were pinned
        as distinguishable in one direction only. This is the other direction.
        """
        executor, client, _ = build(deadline_s=0.0)

        with caplog.at_level(logging.DEBUG, logger=_EXEC_LOGGER):
            await executor.dispatch(buy(), entry_assessment(), candle())

        refusals = _records(caplog, "dispatch_refused")
        assert len(refusals) == 1
        assert refusals[0].reason == "budget_exhausted"  # type: ignore[attr-defined]
        assert client.otoco == []


# --------------------------------------------------------------------------
# R22 -- Option 4 resolution
# --------------------------------------------------------------------------
class TestOptionFourResolution:
    async def test_a_failed_placement_leaves_a_pending_record(self) -> None:
        executor, _, _ = build(client=FakeClient(place_error=TimeoutError("reset")))

        await executor.dispatch(buy(), entry_assessment(), candle())

        assert executor._pending[SYMBOL] == PendingPlacement(
            symbol=SYMBOL,
            entry_bar_time=BAR,
            generation=0,
            quantity=D("0.5"),
            entry_limit=D("100"),
            stop_loss=D("95"),
            take_profit=D("110"),
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

    async def test_the_two_resolution_outcomes_carry_distinct_event_names(
        self, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        """A non-resolution is the branch that leaves an orphaned list.

        Both outcomes shared one event name until now, so a reader filtering on
        `placement_resolved` counted failures as successes -- and would have
        seen a 100% resolution rate while every attempt failed. Nothing pinned
        either name: neither literal appeared anywhere outside `executor.py`.
        """
        executor, _, _ = build(client=FakeClient(place_error=TimeoutError("reset")))
        await executor.dispatch(buy(), entry_assessment(), candle())

        async def _unresolved(*_a: Any, **_k: Any) -> PlacementVerdict:
            return PlacementVerdict(outcome=PlacementOutcome.UNRESOLVED, reason="query failed")

        monkeypatch.setattr("trading_bot.execution.executor.resolve_placement", _unresolved)
        with caplog.at_level(logging.DEBUG, logger=_EXEC_LOGGER):
            await executor(candle())

        assert len(_records(caplog, "placement_unresolved")) == 1
        assert _records(caplog, "placement_resolved") == []

        async def _resolved(*_a: Any, **_k: Any) -> PlacementVerdict:
            # PLACED_TERMINAL, not NOT_PLACED: the latter is a MISSED DISPATCH
            # and has its own event now, so it can no longer stand for "a
            # resolution that succeeded".
            return terminal_verdict()

        monkeypatch.setattr("trading_bot.execution.executor.resolve_placement", _resolved)
        caplog.clear()
        with caplog.at_level(logging.DEBUG, logger=_EXEC_LOGGER):
            await executor(candle())

        assert len(_records(caplog, "placement_resolved")) == 1
        assert _records(caplog, "placement_unresolved") == []

    async def test_a_live_resolution_records_the_position_it_learned_exists(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """R24. Until this, a placement that LANDED but whose response we never
        saw left a live list with no Position -- unbounded, because the record
        was deleted and nothing retried.
        """
        executor, _, portfolio = build(client=FakeClient(place_error=TimeoutError("reset")))
        await executor.dispatch(buy(), entry_assessment(), candle())
        assert SYMBOL not in portfolio.positions

        async def _live(*_a: Any, **_k: Any) -> PlacementVerdict:
            return live_verdict()

        monkeypatch.setattr("trading_bot.execution.executor.resolve_placement", _live)
        await executor(candle(close_time=BAR + timedelta(minutes=1)))

        position = portfolio.positions[SYMBOL]
        assert position.protection is ProtectionState.UNKNOWN
        assert position.quantity == D("0.5")
        assert position.entry_price == D("100")
        assert position.stop_loss == D("95")
        assert position.take_profit == D("110")
        assert position.entry_bar_time == BAR
        assert position.order_list_id == "tb1-BTCUSDT-1714564800000-0-L"
        assert executor._pending == {}
        # THE RECOVERY PATH QUERIES TOO, per the owner's ruling 2. Without it
        # every restored position would be permanently unbookable:
        # `PendingPlacement` carries only what was REQUESTED, so a fill price
        # can never come from the record.
        #
        # MUTATION: drop the query from the `PLACED_LIVE` branch. The position
        # is still recorded, so every assertion above still passes -- only
        # this one bites.
        assert position.entry_fill_price == D("98.00000000")

    async def test_a_live_resolution_debits_the_portfolio(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """THE DEBIT, asserted separately from the Position.

        A membership assertion cannot express it: `open_position` both inserts
        and debits, so a mutation deleting only the debit would leave every
        Position assertion passing. `free_quote` overstated by the committed
        cost is what makes every SUBSEQUENT size wrong, not just this one.
        """
        portfolio = Portfolio(free_quote=D("10000"))
        executor, _, _ = build(
            client=FakeClient(place_error=TimeoutError("reset")), portfolio=portfolio
        )
        await executor.dispatch(buy(), entry_assessment(), candle())
        assert portfolio.free_quote == D("10000")  # nothing charged yet

        async def _live(*_a: Any, **_k: Any) -> PlacementVerdict:
            return live_verdict()

        monkeypatch.setattr("trading_bot.execution.executor.resolve_placement", _live)
        await executor(candle(close_time=BAR + timedelta(minutes=1)))

        # THE FILL, not the request -- 98 against a limit of 100. This test
        # caught the debit change on the RECOVERY path, which is the half a
        # dispatch-only test cannot reach, so the value is asserted against the
        # fill explicitly rather than merely updated.
        assert portfolio.free_quote == D("10000") - D("0.5") * D("98")
        assert portfolio.free_quote != D("10000") - D("0.5") * D("100")

    async def test_a_terminal_resolution_records_no_position(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Live and terminal are NOT one branch.

        A terminal list is MEASURED to mean the FOK expired with `executedQty`
        0 -- nothing rests and no capital moved. Constructing a position here
        would invent one and debit for money never spent. The S5 reading
        (filled, then protection triggered) agrees on the treatment: that
        position has already closed.
        """
        portfolio = Portfolio(free_quote=D("10000"))
        executor, _, _ = build(
            client=FakeClient(place_error=TimeoutError("reset")), portfolio=portfolio
        )
        await executor.dispatch(buy(), entry_assessment(), candle())

        async def _terminal(*_a: Any, **_k: Any) -> PlacementVerdict:
            return terminal_verdict()

        monkeypatch.setattr("trading_bot.execution.executor.resolve_placement", _terminal)
        await executor(candle(close_time=BAR + timedelta(minutes=1)))

        assert SYMBOL not in portfolio.positions
        assert portfolio.free_quote == D("10000")
        assert executor._pending == {}

    async def test_a_missed_dispatch_has_its_own_event_and_is_not_a_resolution(
        self, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        """A trade the bot decided to take and did not.

        It shared `placement_resolved` at INFO with the outcomes that SUCCEEDED,
        so an operator counting resolutions counted losses among them.
        """
        executor, _, _ = build(client=FakeClient(place_error=TimeoutError("reset")))
        await executor.dispatch(buy(), entry_assessment(), candle())

        async def _missed(*_a: Any, **_k: Any) -> PlacementVerdict:
            return PlacementVerdict(outcome=PlacementOutcome.NOT_PLACED, reason="nothing rests")

        monkeypatch.setattr("trading_bot.execution.executor.resolve_placement", _missed)
        with caplog.at_level(logging.DEBUG, logger=_EXEC_LOGGER):
            await executor(candle(close_time=BAR + timedelta(minutes=1)))

        assert len(_records(caplog, "dispatch_missed")) == 1
        assert _records(caplog, "placement_resolved") == []
        assert executor._pending == {}  # the branch still deletes and re-places nothing

    async def test_a_missed_dispatch_carries_the_economics_it_attempted(
        self, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Countable against `order_placed`, or the miss rate cannot be computed."""
        executor, _, _ = build(client=FakeClient(place_error=TimeoutError("reset")))
        await executor.dispatch(buy(), entry_assessment(), candle())

        async def _missed(*_a: Any, **_k: Any) -> PlacementVerdict:
            return PlacementVerdict(outcome=PlacementOutcome.NOT_PLACED, reason="nothing rests")

        monkeypatch.setattr("trading_bot.execution.executor.resolve_placement", _missed)
        with caplog.at_level(logging.DEBUG, logger=_EXEC_LOGGER):
            await executor(candle(close_time=BAR + timedelta(minutes=1)))

        record = _records(caplog, "dispatch_missed")[0]
        assert record.quantity == D("0.5")  # type: ignore[attr-defined]
        assert record.entry == D("100")  # type: ignore[attr-defined]
        assert record.stop_loss == D("95")  # type: ignore[attr-defined]
        assert record.entry_bar_time == BAR.isoformat()  # type: ignore[attr-defined]

    async def test_a_missed_dispatch_outranks_a_self_clearing_one(
        self, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        """THE LEVEL IS ASSERTED, and M5f-058 is why.

        That finding measured that no test in this file asserted a log level at
        all -- a mutation demoting the orphan-leaving branch to INFO passed the
        whole suite. Level is the other property an operator filters on, so a
        terminal outcome hiding at a self-clearing one's level is invisible in
        exactly the view that matters.
        """
        executor, _, _ = build(client=FakeClient(place_error=TimeoutError("reset")))
        await executor.dispatch(buy(), entry_assessment(), candle())

        async def _missed(*_a: Any, **_k: Any) -> PlacementVerdict:
            return PlacementVerdict(outcome=PlacementOutcome.NOT_PLACED, reason="nothing rests")

        monkeypatch.setattr("trading_bot.execution.executor.resolve_placement", _missed)
        with caplog.at_level(logging.DEBUG, logger=_EXEC_LOGGER):
            await executor(candle(close_time=BAR + timedelta(minutes=1)))

        assert _records(caplog, "dispatch_missed")[0].levelno == logging.ERROR
        assert logging.ERROR > logging.WARNING  # the self-clearing branch's level

    async def test_a_client_refusal_leaves_no_pending_record(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """No request left the process, so there is nothing to resolve.

        The motivating case: `SymbolInfoNotPrimedError` was added to keep an
        unbounded call out of a bounded sequence, and then caused a resolver
        call next bar about an id that was never sent.
        """
        executor, _client, _ = build(
            client=FakeClient(place_error=SymbolInfoNotPrimedError("cold cache"))
        )

        with caplog.at_level(logging.DEBUG, logger=_EXEC_LOGGER):
            await executor.dispatch(buy(), entry_assessment(), candle())

        assert executor._pending == {}
        refusals = _records(caplog, "dispatch_refused")
        assert len(refusals) == 1
        assert refusals[0].reason == "client_refusal"  # type: ignore[attr-defined]
        assert refusals[0].error_type == "SymbolInfoNotPrimedError"  # type: ignore[attr-defined]
        assert _records(caplog, "placement_ambiguous") == []

    async def test_a_venue_refusal_still_keeps_its_pending_record(self) -> None:
        """THE DIRECTION THAT MATTERS, and the one the ruling deliberately
        left alone.

        A venue refusal is UNMARKED, so it keeps its record and resolves next
        bar. Treating it as client-side would skip recovery on a placement that
        may have landed -- and this family is the sharp case, because
        `FilterRejectedError` is raised BOTH locally and by the venue on -1013.
        Only the venue-side one reaches here unmarked.
        """
        venue = FilterRejectedError(
            "Filter failure: PRICE_FILTER", filter_name="PRICE_FILTER", code=-1013
        )
        executor, _, _ = build(client=FakeClient(place_error=venue))

        await executor.dispatch(buy(), entry_assessment(), candle())

        assert SYMBOL in executor._pending

    async def test_a_transport_failure_still_keeps_its_pending_record(self) -> None:
        """The genuinely unknown case, untouched by this split."""
        executor, _, _ = build(client=FakeClient(place_error=ExchangeConnectionError("reset")))

        await executor.dispatch(buy(), entry_assessment(), candle())

        assert SYMBOL in executor._pending

    async def test_a_client_refusal_does_not_block_the_next_bar(self) -> None:
        """No record means no pending guard, so the symbol is dispatchable again
        immediately rather than after a bar."""
        client = FakeClient(place_error=SymbolInfoNotPrimedError("cold cache"))
        executor, _, _ = build(client=client)
        await executor.dispatch(buy(), entry_assessment(), candle())

        client.place_error = None
        await executor.dispatch(buy(), entry_assessment(), candle())

        assert len(client.otoco) == 1

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


# --------------------------------------------------------------------------
# The durable pending record
# --------------------------------------------------------------------------
class TestDurablePendingRecord:
    """What reaches DISK, asserted separately from what stays in memory.

    The two are the same at every site but one, and that one is U2's ruling.
    """

    async def test_the_durable_write_precedes_the_in_process_mark(self) -> None:
        """FORK 1. The durable write is the FALLIBLE step, so it runs first and
        a failure leaves ``_pending`` exactly as it was -- no rollback."""
        executor, client, _ = build(persist=RecordingWriter(error=OSError("disk full")))

        await executor.dispatch(buy(), entry_assessment(), candle())

        assert executor._pending == {}
        assert client.otoco == []
        assert client.oto == []

    async def test_a_save_failure_refuses_with_its_own_reason(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Its own reason string: an operator must be sent to the disk, not to
        ``dispatch_deadline_s``."""
        executor, _, _ = build(persist=RecordingWriter(error=OSError("disk full")))

        with caplog.at_level(logging.DEBUG, logger=_EXEC_LOGGER):
            await executor.dispatch(buy(), entry_assessment(), candle())

        assert [r.reason for r in _records(caplog, "dispatch_refused")] == ["store_unwritable"]
        assert len(_records(caplog, "collaborator_failed")) == 1

    async def test_the_record_written_matches_the_in_process_record(self) -> None:
        writer = RecordingWriter()
        executor, _, _ = build(client=FakeClient(place_error=TimeoutError("reset")), persist=writer)

        await executor.dispatch(buy(), entry_assessment(), candle())

        assert writer.calls[0] == (executor._pending[SYMBOL],)

    async def test_a_successful_placement_leaves_nothing_durable(self) -> None:
        writer = RecordingWriter()
        executor, _, _ = build(persist=writer)

        await executor.dispatch(buy(), entry_assessment(), candle())

        assert writer.symbols(0) == [SYMBOL]
        assert writer.calls[-1] == ()
        assert executor._pending == {}

    async def test_a_client_refusal_leaves_nothing_durable(self) -> None:
        """59cf256's ruling, now enforced on disk as well as in memory."""
        writer = RecordingWriter()
        executor, _, _ = build(
            client=FakeClient(place_error=SymbolInfoNotPrimedError("not primed")), persist=writer
        )

        await executor.dispatch(buy(), entry_assessment(), candle())

        assert writer.calls[-1] == ()
        assert executor._pending == {}

    async def test_a_venue_exception_drops_the_durable_record_and_keeps_the_in_process_one(
        self,
    ) -> None:
        """U2, READING A -- BOTH halves asserted, because the ruling IS that
        the two stores disagree here.

        ``TimeoutError`` is the case that makes it matter: the branch catches
        outcomes where a list MAY be resting, and the in-process record is the
        only thing that would ever find it.
        """
        writer = RecordingWriter()
        executor, _, _ = build(client=FakeClient(place_error=TimeoutError("reset")), persist=writer)

        await executor.dispatch(buy(), entry_assessment(), candle())

        assert writer.calls[-1] == ()  # disk forgets
        assert SYMBOL in executor._pending  # memory remembers

    async def test_placed_live_removes_the_durable_record(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        writer = RecordingWriter()
        executor, _, _ = build(client=FakeClient(place_error=TimeoutError("reset")), persist=writer)
        await executor.dispatch(buy(), entry_assessment(), candle())

        async def _live(*_a: Any, **_k: Any) -> PlacementVerdict:
            return live_verdict()

        monkeypatch.setattr("trading_bot.execution.executor.resolve_placement", _live)
        await executor(candle(close_time=BAR + timedelta(minutes=1)))

        assert writer.calls[-1] == ()

    async def test_not_placed_removes_the_durable_record(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        writer = RecordingWriter()
        executor, _, _ = build(client=FakeClient(place_error=TimeoutError("reset")), persist=writer)
        await executor.dispatch(buy(), entry_assessment(), candle())

        async def _gone(*_a: Any, **_k: Any) -> PlacementVerdict:
            return PlacementVerdict(outcome=PlacementOutcome.NOT_PLACED, reason="nothing rests")

        monkeypatch.setattr("trading_bot.execution.executor.resolve_placement", _gone)
        await executor(candle(close_time=BAR + timedelta(minutes=1)))

        assert writer.calls[-1] == ()

    async def test_unresolved_writes_nothing_further_and_keeps_the_record(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Fail-closed: the record stays, so there is nothing to rewrite."""
        writer = RecordingWriter()
        executor, _, _ = build(client=FakeClient(place_error=TimeoutError("reset")), persist=writer)
        await executor.dispatch(buy(), entry_assessment(), candle())
        writes_after_dispatch = len(writer.calls)

        async def _unresolved(*_a: Any, **_k: Any) -> PlacementVerdict:
            return PlacementVerdict(outcome=PlacementOutcome.UNRESOLVED, reason="query failed")

        monkeypatch.setattr("trading_bot.execution.executor.resolve_placement", _unresolved)
        await executor(candle(close_time=BAR + timedelta(minutes=1)))

        assert len(writer.calls) == writes_after_dispatch
        assert SYMBOL in executor._pending

    async def test_a_delete_failure_logs_and_continues_without_raising(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """FORK 3, the opposite of FORK 2: the failure falls on the far side of
        the venue call, the order exists, and a stale record self-corrects."""
        writer = RecordingWriter(error=OSError("disk full"), fail_from=1)
        executor, _, portfolio = build(persist=writer)

        with caplog.at_level(logging.DEBUG, logger=_EXEC_LOGGER):
            await executor.dispatch(buy(), entry_assessment(), candle())  # must not raise

        assert [r.phase for r in _records(caplog, "collaborator_failed")] == ["persist-delete"]
        assert portfolio.has_position(SYMBOL)  # the placement still landed

    async def test_no_writer_means_no_durable_write_at_all(self) -> None:
        """The ``None`` default is byte-for-byte the behaviour before this
        commit, which is what lets every other test in this file stand."""
        executor, client, _ = build()

        await executor.dispatch(buy(), entry_assessment(), candle())

        assert executor._persist_pending is None
        assert len(client.otoco) == 1


class TestTheEntryFillPrice:
    """The entry's true cost, queried at open because ``FOK`` is terminal there.

    Q-C section 3 fixes the working leg as ``LIMIT``+``FOK``: fill-or-kill
    cannot rest, so by the time the placement returns it has filled completely
    or expired. That is REASONED from the leg type -- no entry leg has ever
    been point-queried in this project -- and it is what makes a dispatch-time
    query answerable at all. A resting ``LIMIT`` would make it useless.
    """

    async def test_the_entry_dispatch_makes_exactly_two_venue_calls(self) -> None:
        """THE CALL-COUNT GUARD, per the owner's ruling.

        MUTATION: add any venue call to the entry path -- a retry, a read-back,
        a second query. All of them break this and nothing else would catch
        them: the coherence validator contains NO call count and cannot guard
        one, and `dispatch_budget.py`'s own docstring records this count as
        having been MEASURED WRONG TWICE.

        It counts calls on the FAKE, not timing, so it is deterministic and
        says which calls in which order rather than only how many.
        """
        executor, client, _ = build()

        await executor.dispatch(buy(), entry_assessment(), candle())

        assert client.venue_calls == ["place", "get_order"]
        assert len(client.venue_calls) == 2

    async def test_a_filled_entry_records_what_it_actually_cost(self) -> None:
        """MUTATION: pass `entry_limit` as the fill price, or drop the argument.

        The fill and the request DIFFER here, so a fallback to the request
        fails rather than passing on a fixture where they agree. `entry_price`
        must still hold the request -- the protective geometry was derived
        from it.
        """
        executor, client, portfolio = build()

        await executor.dispatch(buy(), entry_assessment(), candle())

        position = portfolio.positions[SYMBOL]
        assert position.entry_fill_price == D("98.00000000")
        assert position.entry_price != position.entry_fill_price  # request vs fill
        # Queried by OUR id for the WORKING leg, not the list's and not a stop's.
        assert client.order_queries[0].endswith("-0-W")

    async def test_a_failed_query_leaves_the_price_absent_and_still_opens(self) -> None:
        """MUTATION: raise out of the query, or fall back to `entry_limit`.

        A dispatch that PLACED must not be turned into a failure by a
        follow-up read -- the order list is at the venue either way, and the
        position has to be recorded. `None` is the honest answer and booking
        refuses on it later.
        """
        executor, _, portfolio = build()
        executor._client.order_error = ExchangeConnectionError("boom")  # type: ignore[attr-defined]

        await executor.dispatch(buy(), entry_assessment(), candle())

        assert portfolio.has_position(SYMBOL)
        assert portfolio.positions[SYMBOL].entry_fill_price is None

    async def test_the_debit_uses_the_fill_and_not_the_requested_limit(self) -> None:
        """MUTATION: revert to `cost=quantity * entry_limit`.

        The request (100) and the fill (98) are set APART, so the two debits
        differ: 50 against 49. A fixture where they agreed could not express
        this at all -- which is the state `long_position(entry_fill=None)`
        leaves `test_risk_manager.py`'s helper in, deliberately, and the reason
        this test lives here instead.

        `free_quote` after the open must equal the VENUE-CHARGED amount.
        """
        executor, _, portfolio = build()

        await executor.dispatch(buy(), entry_assessment(), candle())

        # 10000 - (0.5 * 98) = 9951, not 10000 - (0.5 * 100) = 9950.
        assert portfolio.free_quote == D("9951.00")
        assert portfolio.positions[SYMBOL].entry_fill_price == D("98.00000000")
        assert portfolio.positions[SYMBOL].entry_price == D("100")  # request, unchanged

    async def test_an_absent_fill_debits_the_request_and_says_so(self, caplog) -> None:  # type: ignore[no-untyped-def]
        """R1(c) option 1, and the alternative was rejected on error direction.

        MUTATION: refuse to open the position when the fill is unknown, or
        fall back silently.

        Refusing would leave a filled entry and two resting protective legs at
        the venue with nothing tracking them -- an orphan of our own making.
        Falling back is wrong by a measured amount in the CONSERVATIVE
        direction (request above fill on all five measured instances, so the
        over-debit under-states `free_quote`), and the position is unbookable
        anyway because `unrealized_pnl` raises -- so the error cannot reach the
        ledger.

        Its own event, because `entry_fill_absent` reports what the VENUE said
        and this reports the MONEY CONSEQUENCE. It also fires on the
        query-FAILURE path, which the other does not -- asserted here by
        failing the query rather than expiring the leg.
        """
        executor, _, portfolio = build()
        executor._client.order_error = ExchangeConnectionError("boom")  # type: ignore[attr-defined]

        with caplog.at_level(logging.DEBUG, logger=_EXEC_LOGGER):
            await executor.dispatch(buy(), entry_assessment(), candle())

        assert portfolio.has_position(SYMBOL)  # NEVER an orphan of our own making
        assert portfolio.free_quote == D("9950.00")  # the request: 0.5 * 100
        records = _records(caplog, "debit_from_requested_limit")
        assert [r.entry_limit for r in records] == [D("100")]
        # And the ledger is protected regardless: this position cannot book.
        with pytest.raises(ValueError, match="cost basis is unknown"):
            portfolio.positions[SYMBOL].unrealized_pnl(D("110"))

    async def test_an_expired_fok_constructs_no_position_and_debits_nothing(
        self,
        caplog,  # type: ignore[no-untyped-def]
    ) -> None:
        """P6, CLOSED. This test asserted the DEFECT until this commit.

        MUTATION: remove the `if fill.expired` guard from `dispatch`.

        The query SUCCEEDED and the venue said nothing filled -- an FOK that
        found no counterparty, so no trade happened. Until the guard a
        `Position` was constructed anyway: a holding the account does not
        have, and since `31fc12d` a DEBIT of real capital against it.

        **`free_quote` is asserted, not merely `positions`.** A guard that
        skipped the construction but still debited would leave `positions`
        empty and the balance wrong, and only the money assertion sees that.

        Nothing rests to unwind: MEASURED, six probe lists with a FOK working
        leg read ALL_DONE/ALL_DONE, every leg EXPIRED, `executedQty` 0.
        """
        executor, _, portfolio = build()
        executor._client.fill_price = None  # type: ignore[attr-defined]

        with caplog.at_level(logging.DEBUG, logger=_EXEC_LOGGER):
            await executor.dispatch(buy(), entry_assessment(), candle())

        assert SYMBOL not in portfolio.positions  # no phantom
        assert portfolio.free_quote == D("10000")  # and no money moved
        assert [r.status for r in _records(caplog, "entry_fill_absent")] == ["EXPIRED"]
        assert [r.reason for r in _records(caplog, "dispatch_refused")] == ["entry_leg_expired"]
        # The pending record is gone: it was popped before the query, which is
        # already right for this outcome -- there is no list to resolve later.
        assert executor._pending == {}

    async def test_a_failed_query_is_not_an_expiry(self, caplog) -> None:  # type: ignore[no-untyped-def]
        """THE AMBIGUOUS CASE, and the two errors are opposite.

        MUTATION: guard on `fill.price is None` instead of `fill.expired`.

        That mutation reads as a simplification and inverts the decision:
        silence from the venue would refuse a position that may be filled and
        protected, stranding an order list nothing tracks -- an orphan of our
        own making, which `M5h-097` names as the worst state this milestone
        recorded. Only a POSITIVE "did not fill" may refuse.

        The opposite error is bounded: a phantom is unbookable, because
        `unrealized_pnl` raises, and the next boot re-seeds `free_quote`.
        """
        executor, _, portfolio = build()
        executor._client.order_error = ExchangeConnectionError("boom")  # type: ignore[attr-defined]

        with caplog.at_level(logging.DEBUG, logger=_EXEC_LOGGER):
            await executor.dispatch(buy(), entry_assessment(), candle())

        assert portfolio.has_position(SYMBOL)  # RECORDED, never an orphan
        assert _records(caplog, "dispatch_refused") == []  # and not refused
        assert portfolio.positions[SYMBOL].entry_fill_price is None
        # Fail-closed regardless: this position cannot reach the ledger.
        with pytest.raises(ValueError, match="cost basis is unknown"):
            portfolio.positions[SYMBOL].unrealized_pnl(D("110"))


# --------------------------------------------------------------------------
# The pending UNION -- one keyspace, two kinds
# --------------------------------------------------------------------------
def _close(symbol: str = SYMBOL) -> PendingClose:
    """A pending close against the same position the entry fixtures open."""
    return PendingClose(symbol=symbol, entry_bar_time=BAR, generation=0, quantity=D("0.5"))


class TestThePendingUnion:
    """Both kinds share ``_pending``, and the existing guards still bind.

    **THERE ARE TWO DOORS INTO ``_pending`` FOR A CLOSE, AND THIS DOCSTRING
    USED TO CLAIM THERE WERE NONE.** It read *"NOTHING IN ``src/`` CONSTRUCTS
    A ``PendingClose``"*, and that the tests reach the shape through
    ``restored_pending``, *"the only door into ``_pending`` that does not go
    through dispatch"*. Both were true when written and both went stale when
    the close path landed: ``_execute_close`` constructs a ``PendingClose``
    and writes it into ``_pending``, so it is a second door and a production
    one.

    What the tests below do is unchanged -- they still reach the shape through
    ``restored_pending``, which is still the cheapest door for a unit test.
    Only the claim that it is the ONLY one is struck.
    """

    def test_both_kinds_carry_a_tag_and_the_tags_differ(self) -> None:
        """The discriminator, asserted on the values a narrowing branches on.

        MUTATION: give ``PendingClose.kind`` the default ``"placement"``.

        Under it every narrowing in the tree silently takes the entry branch --
        including the resolver's -- and a close would be handed to
        ``resolve_placement``. Asserting the pair is what makes the tag a fact
        rather than a convention.
        """
        assert _close().kind == "close"
        assert (
            PendingPlacement(
                symbol=SYMBOL,
                entry_bar_time=BAR,
                generation=0,
                quantity=D("0.5"),
                entry_limit=D("100"),
                stop_loss=D("95"),
                take_profit=D("110"),
            ).kind
            == "placement"
        )

    def test_a_close_carries_no_entry_economics(self) -> None:
        """Four fields, and the three an exit has no business holding are absent.

        MUTATION: add ``entry_limit`` to ``PendingClose``.

        ``PendingPlacement``'s line is *"every field is something WE
        REQUESTED"*. A MARKET sell requests no limit price, so a limit here
        would be a fabricated value in the one type whose justification is that
        it holds none. Asserted over ``__slots__`` rather than by a raise: the
        dataclass is ``slots=True``, so the field's absence is structural.
        """
        assert set(PendingClose.__slots__) == {
            "symbol",
            "entry_bar_time",
            "generation",
            "quantity",
            "kind",
        }

    async def test_an_entry_is_refused_while_a_close_is_pending(self) -> None:
        """**THE REASON FOR ONE KEYSPACE, and the whole of it.**

        MUTATION: key closes in a separate dict from ``_pending``.

        The guard is ``if signal.symbol in self._pending`` and it was written
        for placements. Putting closes in the same keyspace means it refuses an
        entry during an unresolved exit with NO rewrite of entry gating -- a
        separate dict would leave it blind, and an entry could dispatch on a
        symbol the bot is midway through exiting.

        DECLARED: this passes today only because the union shares the dict.
        Nothing else in the tree would report the separation.
        """
        executor, client, _ = build()
        executor._pending[SYMBOL] = _close()

        await executor.dispatch(buy(), entry_assessment(), candle())

        assert client.otoco == []
        assert client.oto == []
        assert client.venue_calls == []

    async def test_a_pending_close_is_skipped_by_placement_resolution(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """The resolver does not answer for a close, and says nothing rather
        than answering wrongly.

        MUTATION: delete the ``kind != "placement"`` guard in ``__call__``.

        Under it a close reaches ``resolve_placement``, which asks
        ``get_all_order_lists`` whether a LIST bearing our
        ``listClientOrderId`` rests. A discretionary close is a standalone
        MARKET sell and is not a list, so that query answers ``NOT_PLACED``
        whatever actually happened -- and on the fail-closed path a wrong
        answer confidently given is worse than none.

        **WHAT ACTUALLY CATCHES THE MUTATION IS PYTHON, NOT THESE
        ASSERTIONS -- stated plainly, because two wrong predictions were spent
        establishing it and the honest answer is not the flattering one.**
        Remove the guard and the close reaches the placement branch, which
        reads ``record.entry_limit``; ``PendingClose`` has no such attribute,
        so it raises ``AttributeError`` DURING ``await executor(candle())``,
        before any assertion below is reached. That is this project's third
        kind of coverage -- enforcement by the interpreter -- and it is the
        strongest of the three, because no future edit to a test can delete
        it. It is not, however, an assertion, and the difference is recorded
        rather than glossed.

        **Two earlier attempts failed for two DIFFERENT reasons, both worth
        keeping.** The first asserted only ``venue_calls == []`` and did not
        bite: ``FakeClient`` had no ``get_all_order_lists``, so the call raised
        inside ``resolve_placement``, which catches internally and returns
        ``UNRESOLVED`` -- nothing escaped, nothing was logged, and no venue
        call was recorded because the fake was never entered. A
        resolved-and-failed close looked exactly like a skipped one. The fake
        gained the method for that reason; see it. The second added the
        ``collaborator_failed`` assertion on the theory that the exception
        escapes to ``__call__``, which it does not -- ``resolve_placement``
        swallows it one layer down.

        The three assertions below pin the INTENDED behaviour, which is worth
        pinning on its own terms: no venue call, no failure logged, record
        preserved.

        **SUPERSEDED BY `TestTheCloseResolution` BELOW.** All three assertions
        inverted when the branch stopped doing nothing: the query IS made, a
        CRITICAL IS logged, and the record is deliberately NOT preserved. What
        survives from this test is its subject -- `resolve_placement` must not
        be the instrument -- and the replacement pins that by asserting the
        derived id the query actually carries.
        """
        executor, client, _ = build(client=_resolving_client())
        executor._pending[SYMBOL] = _close()

        with caplog.at_level(logging.CRITICAL):
            await executor(candle())

        # `resolve_placement`'s instrument is `get_all_order_lists`; the close
        # resolution's is `get_order`. Asserting which call was made is what
        # keeps this test on its original subject.
        assert "get_all_order_lists" not in client.venue_calls
        assert client.venue_calls == ["get_order"]

    async def test_a_restored_close_reaches_the_pending_set(self) -> None:
        """The restore door, which is how a close survives a process death.

        MUTATION: narrow ``restored_pending`` back to ``PendingPlacement``.

        mypy is the instrument for the annotation; this pins the runtime half
        -- that the record arrives keyed by its symbol and is the same object,
        so the guard above has something to find.
        """
        executor = OrderExecutor(
            client=FakeClient(),  # type: ignore[arg-type]
            portfolio=Portfolio(free_quote=D("10000")),
            budget=DispatchBudget(deadline_s=9.0),
            settlement_bounds=SETTLEMENT_BOUNDS,
            restored_pending=(_close(),),
        )

        assert executor._pending == {SYMBOL: _close()}


# --------------------------------------------------------------------------
# Q-C section 4b's READ half -- plan, report, refuse
# --------------------------------------------------------------------------
CLOSE_QTY = D("0.5")
#: The venue's own quote total for a complete sell.
#:
#: **DELIBERATELY NOT `CLOSE_QTY * entry_fill`.** Entry is 98.00000000 x 0.5 =
#: 49.0; this is 51.25, so the realised figure is a non-zero +2.25 and a booking
#: that credited the wrong number, or booked nothing, changes it. A total equal
#: to the cost basis would make every P&L assertion pass at zero.
SELL_TOTAL = D("51.25000000")


def sell_fill(*, executed: Decimal = CLOSE_QTY, total: Decimal | None = SELL_TOTAL) -> Order:
    """The MARKET sell's response.

    ``total=None`` is the shape that forces the point-query fallback: the tree
    sets ``newOrderRespType`` NOWHERE, so a response carrying no
    ``cummulativeQuoteQty`` is a state the design must handle rather than
    assume away.
    """
    return Order(
        order_id="777",
        symbol=SYMBOL,
        side=OrderSide.SELL,
        type=OrderType.MARKET,
        status=OrderStatus.FILLED,
        quantity=CLOSE_QTY,
        filled_quantity=executed,
        filled_quote_quantity=total,
    )


#: THE MEASURED FEE, not a stub -- see `sell_trade`.
USDT_ZERO_FEE = Fee(amount=D("0.00000000"), asset="USDT")


def sell_trade(
    *,
    order_id: str = "777",
    quantity: Decimal = CLOSE_QTY,
    quote: Decimal = SELL_TOTAL,
    fee: Fee = USDT_ZERO_FEE,
    trade_id: str = "1",
) -> Trade:
    """One fill of the MARKET sell, as `get_my_trades` returns it.

    The default fee is `0.00000000` USDT, the value MEASURED on every SELL fill
    in the capture whose SHA-256 is
    111d1c15a3c5fff56148f172bfbcbec85baf5aabe2128f34fb622cafe5463970. Tests whose
    subject is the fee pass a FABRICATED non-zero one, said so where they do.
    """
    return Trade(
        trade_id=trade_id,
        order_id=order_id,
        symbol=SYMBOL,
        side=OrderSide.SELL,
        quantity=quantity,
        price=D("102.50000000"),
        quote_quantity=quote,
        fee=fee,
        filled_at=BAR,
    )


def _leg(executed: str, status: OrderStatus = OrderStatus.NEW) -> Order:
    """One protective leg's point-query answer."""
    return Order(
        order_id="9",
        symbol=SYMBOL,
        side=OrderSide.SELL,
        type=OrderType.STOP_LOSS,
        status=status,
        quantity=CLOSE_QTY,
        filled_quantity=D(executed),
    )


def _held(
    *,
    stop: str | None = "95",
    target: str | None = "110",
    venue_id: int | None = int(VENUE_LIST_ID),
    entry_fill: str | None = "98.00000000",
    protection: ProtectionState = ProtectionState.UNKNOWN,
    quantity: Decimal = CLOSE_QTY,
) -> Portfolio:
    """A portfolio holding the position `close_signal` would close.

    `build()`'s default portfolio holds NOTHING, so a close against it refuses
    at `close_no_position` and makes zero reads -- which cannot express any row
    of the decision table.

    **`venue_id` DEFAULTS TO PRESENT, and it did not used to exist.** Without it
    every close refuses at `close_no_venue_list_id` before the cancel, so no
    test could reach the executing path at all -- the fixture, not the
    assertions, would have been the limit. It is parameterised so ruling 1's
    refusal is reachable too.

    **`entry_fill` likewise**: booking reads `entry_fill_price` and
    `close_position` refuses without one, so a fixture that omitted it could
    express a sell but never a BOOKED close.

    **`protection` DEFAULTS TO `UNKNOWN` AND IS PARAMETERISED, and the reason
    is a mutation that could not otherwise be killed.** Every close path here
    marks or expects `UNKNOWN`, so a fixture fixed at that value cannot express
    "the mark was never written" -- the mutation removing it changes nothing
    observable. `ACTIVE` is in `_TRUSTED_PROTECTION`, so a position starting
    there has computable committed risk, and losing the mark is then the
    difference between entries refused portfolio-wide and entries permitted.
    """
    return Portfolio(
        free_quote=D("10000"),
        positions={
            SYMBOL: Position(
                symbol=SYMBOL,
                side=PositionSide.LONG,
                quantity=quantity,
                entry_price=D("100"),
                entry_fill_price=D(entry_fill) if entry_fill is not None else None,
                entry_bar_time=BAR,
                protection=protection,
                order_list_id=CLIENT_LIST_ID,
                venue_order_list_id=venue_id,
                stop_loss=D(stop) if stop is not None else None,
                take_profit=D(target) if target is not None else None,
            )
        },
    )


def _plan_records(caplog: pytest.LogCaptureFixture) -> list[logging.LogRecord]:
    return _records(caplog, "close_planned")


class TestTheClosePlan:
    """The read half runs, reports and refuses. NOTHING IRREVERSIBLE HAPPENS."""

    async def test_no_leg_executed_plans_a_sell_and_proceeds(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Section 4b row one. **The plan says SELL and the sell now HAPPENS.**

        MUTATION: keep C4b's refusal on the SELL branch.

        This test read `..._and_refuses_it` until C5 and asserted
        `close_sell_reserved`. That reason no longer exists on this path: a
        `SELL` verdict proceeds to cancel, re-confirm and sell. What survives is
        the plan record itself, which is still emitted before anything
        irreversible.
        """
        client = FakeClient(leg_answers={"SL": _leg("0"), "TP": _leg("0")})
        executor, _, _ = build(client=client, portfolio=_held())

        with caplog.at_level(logging.DEBUG, logger=_EXEC_LOGGER):
            await executor.dispatch(close_signal(), exit_assessment(), candle())

        plans = _plan_records(caplog)
        assert len(plans) == 1
        assert plans[0].decision == "sell"  # type: ignore[attr-defined]
        assert _records(caplog, "dispatch_refused") == []
        assert client.sold  # it really sold

    async def test_a_filled_leg_plans_already_closed_and_books_nothing(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Section 4b row two -- and the half that matters is what does NOT happen.

        MUTATION: call `close_position` on the ALREADY_CLOSED branch.

        Booking a bot-sent close is the NEXT commit's. The position stays in
        `portfolio.positions` deliberately: the reconciliation driver's booking
        path is already live for a venue-triggered fill and will see this leg on
        its next pass. Booking here would be a second path racing that one, and
        the two would double-book. Asserted on the ledger AND on `positions`,
        because a booking that credited without deleting would pass the second
        alone.
        """
        portfolio = _held()
        client = FakeClient(
            leg_answers={
                "SL": _leg("0.5", status=OrderStatus.FILLED),
                "TP": _leg("0", status=OrderStatus.EXPIRED),
            }
        )
        executor, _, _ = build(client=client, portfolio=portfolio)

        with caplog.at_level(logging.DEBUG, logger=_EXEC_LOGGER):
            await executor.dispatch(close_signal(), exit_assessment(), candle())

        assert _plan_records(caplog)[0].decision == "already_closed"  # type: ignore[attr-defined]
        refusals = _records(caplog, "dispatch_refused")
        assert refusals[0].reason == "close_already_closed"  # type: ignore[attr-defined]
        # NOTHING WAS BOOKED.
        assert portfolio.ledger is None
        assert SYMBOL in portfolio.positions
        assert portfolio.free_quote == D("10000")

    async def test_a_partial_fill_plans_a_halt(self, caplog: pytest.LogCaptureFixture) -> None:
        """Section 4b's UNMEASURED row, reached through the real decision table.

        MUTATION: pass `order.quantity` as `requested` instead of the position's.

        A leg's `origQty` and the position's quantity agree today, so that
        mutation is invisible to a fixture where they match -- this one sets the
        executed quantity BETWEEN zero and the position size, which is what
        makes the partial row reachable at all.
        """
        client = FakeClient(
            leg_answers={"SL": _leg("0.2", status=OrderStatus.FILLED), "TP": _leg("0")}
        )
        executor, _, _ = build(client=client, portfolio=_held())

        with caplog.at_level(logging.DEBUG, logger=_EXEC_LOGGER):
            await executor.dispatch(close_signal(), exit_assessment(), candle())

        assert _plan_records(caplog)[0].decision == "halt"  # type: ignore[attr-defined]
        refusals = _records(caplog, "dispatch_refused")
        assert refusals[0].reason == "close_halted"  # type: ignore[attr-defined]

    async def test_an_unreadable_leg_is_distinguishable_from_one_that_answered(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """**A query failure is not a separate verdict -- it is a NULL that the
        table reads as unreadable, and the LOG is what tells the two apart.**

        MUTATION: report a failed read as `executed=Decimal(0)`.

        Under it the verdict flips from HALT to SELL -- a failed query becomes a
        licence to sell, the one direction this may not err in -- and the log
        would show `sl_executed=0` beside `tp_executed=0`, indistinguishable
        from two legs that both answered "nothing executed". Asserting the null
        AND the error field is what makes the distinction visible; asserting the
        verdict alone would pass for a fake whose other leg happened to halt.
        """
        client = FakeClient(leg_answers={"SL": ExchangeConnectionError("reset"), "TP": _leg("0")})
        executor, _, _ = build(client=client, portfolio=_held())

        with caplog.at_level(logging.DEBUG, logger=_EXEC_LOGGER):
            await executor.dispatch(close_signal(), exit_assessment(), candle())

        plan = _plan_records(caplog)[0]
        assert plan.decision == "halt"  # type: ignore[attr-defined]
        # The unreadable leg: null status, null quantity, and a named cause.
        assert plan.sl_status is None  # type: ignore[attr-defined]
        assert plan.sl_executed is None  # type: ignore[attr-defined]
        assert plan.sl_error == "ExchangeConnectionError"  # type: ignore[attr-defined]
        # The leg that ANSWERED, on the same record, saying something different.
        assert plan.tp_status == "NEW"  # type: ignore[attr-defined]
        assert plan.tp_executed == D("0")  # type: ignore[attr-defined]
        assert not hasattr(plan, "tp_error")

    async def test_exactly_two_venue_reads_are_made(self) -> None:
        """THE READ COUNT, ruled at two and asserted on the fake.

        MUTATION: query the working leg as well.

        A third read would cost a round trip on the candle pipeline and yield no
        protection state -- the entry leg is `LIMIT`+`FOK` and terminal at
        placement. Asserted as an exact list, not a count, so a read of the
        WRONG leg fails here too.

        Driven to a HALT verdict, so the PLAN's read count is what is measured
        rather than the whole sequence -- a SELL now continues into a cancel and
        two more reads, and the full sequence is asserted in its own test.
        """
        client = FakeClient(leg_answers={"SL": _leg("0.2"), "TP": _leg("0")})
        executor, _, _ = build(client=client, portfolio=_held())

        await executor.dispatch(close_signal(), exit_assessment(), candle())

        assert client.venue_calls == ["get_order", "get_order"]
        assert [q.rsplit("-", 1)[-1] for q in client.order_queries] == ["SL", "TP"]

    async def test_a_leg_that_was_never_requested_is_never_queried(self) -> None:
        """An OTO position has one protective leg, so it reads once.

        MUTATION: query both legs unconditionally.

        A leg that was never requested has no id at the venue, so querying it
        spends a call to be told `-2011`. The read count follows what was
        REQUESTED, which is the same key Q-C reconciles on.
        """
        client = FakeClient(leg_answers={"SL": _leg("0.2")})
        executor, _, _ = build(client=client, portfolio=_held(target=None))

        await executor.dispatch(close_signal(), exit_assessment(), candle())

        assert client.venue_calls == ["get_order"]

    async def test_no_position_refuses_without_reading_anything(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """The position left between evaluate and dispatch.

        MUTATION: drop the `position is None` guard.

        Without it the derivation raises `AttributeError` inside a method the
        module docstring says must never raise. Asserting zero reads is what
        pins that the refusal happens BEFORE any venue contact.
        """
        executor, client, _ = build()  # default portfolio holds nothing

        with caplog.at_level(logging.DEBUG, logger=_EXEC_LOGGER):
            await executor.dispatch(close_signal(), exit_assessment(), candle())

        refusals = _records(caplog, "dispatch_refused")
        assert refusals[0].reason == "close_no_position"  # type: ignore[attr-defined]
        assert client.venue_calls == []
        assert _plan_records(caplog) == []

    async def test_the_elapsed_time_of_the_reads_is_logged(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """**THE FIELD THE WHOLE READ HALF EXISTS TO PRODUCE.**

        MUTATION: drop `elapsed_s` from the record.

        `dispatch` samples its budget once, with `now == started_at`, THIRTY
        LINES BELOW the branch that reaches the close path -- so these reads are
        charged against nothing and the budget will never report their cost.
        This field is the only instrument that will. Asserted as a real
        non-negative float, because a string would cross `extra=` unnoticed
        (`default=str` is a catch-all) and both sinks would render it plausibly.
        """
        client = FakeClient(leg_answers={"SL": _leg("0"), "TP": _leg("0")})
        executor, _, _ = build(client=client, portfolio=_held())

        with caplog.at_level(logging.DEBUG, logger=_EXEC_LOGGER):
            await executor.dispatch(close_signal(), exit_assessment(), candle())

        elapsed = _plan_records(caplog)[0].elapsed_s  # type: ignore[attr-defined]
        assert isinstance(elapsed, float)
        assert elapsed >= 0.0

    async def test_the_close_path_writes_nothing_at_the_venue(self) -> None:
        """No cancel, no sell -- asserted behaviourally AND by reading the source.

        MUTATION: call `create_order` or a cancel from the close path.

        **THE BEHAVIOURAL HALF ALONE IS NOT ENOUGH, which is why the source is
        read too.** A write on a branch this fixture does not reach would
        satisfy every assertion above it: `venue_calls` records only what ran.

        **AND THE SOURCE CHECK IS AN AST WALK, NOT A TEXT GREP -- the grep was
        written first and it FAILED, on this method's own prose.** `_plan_close`
        documents that it sends no cancel and that `cancel_order_list` is
        undeclared, so the substring `cancel` appears in it several times while
        no such call exists. A text search over source counts DOCUMENTATION as
        code, and it would have failed for as long as the docstring said the
        right thing. Collecting the called attribute names is the direct
        observation the proxy stood for.

        Scoped to the two close methods rather than the file, so the ENTRY
        path's own placements cannot mask a write here.
        """
        client = FakeClient(leg_answers={"SL": _leg("0.2"), "TP": _leg("0")})
        executor, _, _ = build(client=client, portfolio=_held())

        await executor.dispatch(close_signal(), exit_assessment(), candle())

        assert client.venue_calls == ["get_order", "get_order"]
        assert client.otoco == [] and client.oto == []
        assert client.cancelled == [] and client.sold == []

        tree = ast.parse(Path(inspect.getfile(OrderExecutor)).read_text(encoding="utf-8"))
        closers = [
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.AsyncFunctionDef | ast.FunctionDef)
            and node.name in {"_plan_close", "_confirm_protective_legs"}
        ]
        assert len(closers) == 2, "both close methods must be found, or this pins nothing"

        called = {
            node.func.attr
            for fn in closers
            for node in ast.walk(fn)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
        }
        assert called & {"get_order"}, "the confirm step must actually query"
        assert not called & {
            "create_order",
            "create_otoco_order_list",
            "create_oto_order_list",
            "cancel_order",
            "cancel_order_list",
            "close_position",
            "open_position",
            "record_realised_pnl",
        }, sorted(called)

    def test_the_whole_close_path_touches_exactly_three_venue_methods(self) -> None:
        """**THE CENSUS OF EVERY IRREVERSIBLE THING THIS COMMIT CAN DO.**

        MUTATION: call any other client method from the close path.

        The test above scopes to the PLAN, which still writes nothing. This one
        covers the executing half too, and it is the assertion that says what
        the bot can now do at a venue of its own volition: cancel a list, query
        an order, place an order. Nothing else.

        An AST walk over the named methods, **never a text grep**: a grep for
        forbidden call names matched this file's own docstrings twice this
        milestone, because a docstring saying "no cancel is sent" contains the
        word. Collecting CALLED attribute names is the direct observation the
        grep was standing in for.

        `create_otoco_order_list` and `create_oto_order_list` stay forbidden
        here: an exit may never open a position.
        """
        tree = ast.parse(Path(inspect.getfile(OrderExecutor)).read_text(encoding="utf-8"))
        close_methods = {
            "_plan_close",
            "_execute_close",
            "_confirm_protective_legs",
            "_cancel_protection",
            "_sell_and_book",
            "_requery_sell_total",
            "_book_close",
            "_go_naked",
        }
        found = [
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.AsyncFunctionDef | ast.FunctionDef)
            and node.name in close_methods
        ]
        assert {fn.name for fn in found} == close_methods, "a close method was renamed or lost"

        called = {
            node.func.attr
            for fn in found
            for node in ast.walk(fn)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
        }
        assert called & {"cancel_order_list", "get_order", "create_order"} == {
            "cancel_order_list",
            "get_order",
            "create_order",
        }
        assert not called & {
            "create_otoco_order_list",
            "create_oto_order_list",
            "cancel_order",
            "cancel_all_open_orders",
            "get_all_order_lists",
        }, sorted(called)


# --------------------------------------------------------------------------
# The two identifier spaces -- ours and the venue's
# --------------------------------------------------------------------------
class TestTheTwoListIdentifiers:
    """A ``Position`` carries BOTH ids, under names and types that separate them.

    **THE FIXTURE IS WHAT MAKES THESE EXPRESSIVE**, and it did not used to be.
    ``placed_list`` returned ``order_list_id="1"`` -- a value close enough to a
    placeholder that a test asserting it could pass for the wrong reason. It now
    returns the venue's real ``255471`` beside our ``tb1-...-0-L``: different
    values, different SHAPES, and different types on the model. A fixture whose
    two ids were interchangeable could not express the substitution these tests
    exist to catch.
    """

    async def test_a_placed_position_carries_both_ids_and_they_differ(self) -> None:
        """THE CENTRAL ASSERTION. Both populated, and NOT equal.

        MUTATION: populate `venue_order_list_id` from `list_client_order_id`.

        That is the exact confusion `classify_protection` made in run 1 -- 28
        consecutive false `DIVERGED` verdicts, because both fields were `str`
        and no type could see it. Asserting each value AND their inequality is
        what makes a substitution fail here rather than at the venue.
        """
        executor, _, portfolio = build()

        await executor.dispatch(buy(), entry_assessment(), candle())

        position = portfolio.positions[SYMBOL]
        assert position.order_list_id == CLIENT_LIST_ID
        assert position.venue_order_list_id == int(VENUE_LIST_ID)
        assert str(position.venue_order_list_id) != position.order_list_id

    async def test_the_venue_id_is_an_int_not_a_string(self) -> None:
        """The type is load-bearing, so it is asserted rather than assumed.

        MUTATION: declare `venue_order_list_id: str | None`.

        Two `str` fields side by side is precisely the shape that let run 1's
        substitution happen unseen. `int` makes the swap a TYPE error, which is
        an instrument the earlier defect had none of. `is True` on the isinstance
        rather than a truthy check, because `bool` is an `int` subclass and a
        stray `True` would satisfy a looser assertion.
        """
        executor, _, portfolio = build()

        await executor.dispatch(buy(), entry_assessment(), candle())

        assert isinstance(portfolio.positions[SYMBOL].venue_order_list_id, int) is True
        assert not isinstance(portfolio.positions[SYMBOL].venue_order_list_id, bool)

    async def test_a_restored_position_also_carries_the_venue_id(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """**THE RECOVERY PATH IS NOT WORSE OFF, and that was not obvious.**

        MUTATION: pass `venue_order_list_id=None` on the `PLACED_LIVE` branch.

        `PendingPlacement` carries only what we REQUESTED, so the venue's number
        cannot come from the record -- which is what made this look like a hole.
        It is not: `resolve_placement` enumerates real `OrderList` objects from
        the venue, and the one it matched carries the id. Without this test the
        design would have to assume a restored position cannot be cancelled by
        number, which is the assumption the close path would then be built on.
        """
        executor, _, portfolio = build(client=FakeClient(place_error=TimeoutError("reset")))
        await executor.dispatch(buy(), entry_assessment(), candle())
        assert SYMBOL in executor._pending

        async def _live(*_a: Any, **_k: Any) -> PlacementVerdict:
            return live_verdict()

        executor._client = FakeClient()  # type: ignore[assignment]
        monkeypatch.setattr("trading_bot.execution.executor.resolve_placement", _live)
        await executor(candle(close_time=BAR + timedelta(minutes=1)))

        position = portfolio.positions[SYMBOL]
        assert position.order_list_id == CLIENT_LIST_ID
        assert position.venue_order_list_id == int(VENUE_LIST_ID)

    def test_both_ids_are_none_together_when_no_single_live_list_matched(self) -> None:
        """They answer `None` on the SAME condition, never one without the other.

        MUTATION: give `_matched_venue_list_id` its own filter.

        A position half-identified -- our id present, the venue's absent, or the
        reverse -- would be worse than one with neither, because a caller would
        reasonably read the presence of one as evidence about the other. The
        shared `_single_live` is what makes that unrepresentable; this pins it
        over the two shapes that produce it.
        """
        from trading_bot.execution.executor import _matched_list_id, _matched_venue_list_id

        none_live = PlacementVerdict(
            outcome=PlacementOutcome.PLACED_TERMINAL, reason="terminal", matched=()
        )
        two_live = PlacementVerdict(
            outcome=PlacementOutcome.UNRESOLVED,
            reason="several live",
            matched=(placed_list(), placed_list(venue_id="255472")),
        )

        for verdict in (none_live, two_live):
            assert _matched_list_id(verdict) is None
            assert _matched_venue_list_id(verdict) is None

    def test_a_non_numeric_list_id_is_none_and_logged_not_raised(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """The error direction, on a state no measured payload produces.

        MUTATION: let the `int()` raise instead of returning `None`.

        Reaching here means a placement has ALREADY LANDED. Raising would
        abandon the `Position` for a list that exists -- an orphan, the
        direction `_matched_list_id` already refuses in its own words. A missing
        number costs the close path one enumeration; a missing position costs
        the list. Asserted with the log, because a silent `None` here would be a
        fake default.
        """
        from trading_bot.execution.executor import _venue_list_id

        with caplog.at_level(logging.ERROR, logger=_EXEC_LOGGER):
            result = _venue_list_id(placed_list(venue_id="not-a-number"))

        assert result is None
        assert _records(caplog, "order_list_id_not_numeric")

    def test_a_position_defaults_the_venue_id_to_none(self) -> None:
        """Every existing construction still works, unchanged.

        MUTATION: make `venue_order_list_id` required.

        `Position` is constructed in fixtures across this suite and in `src/`
        only by `_open_position`. A required field would break every one of
        them -- which is the LOUD direction, but it would also force a value at
        sites that genuinely have none. `None` is a real state here; see the
        field's docstring for the two facts it covers.
        """
        position = Position(
            symbol=SYMBOL,
            side=PositionSide.LONG,
            quantity=D("0.5"),
            entry_price=D("100"),
            entry_bar_time=BAR,
            protection=ProtectionState.UNKNOWN,
        )

        assert position.venue_order_list_id is None
        assert position.order_list_id is None


# --------------------------------------------------------------------------
# Q-C section 4b's IRREVERSIBLE half -- cancel, re-confirm, sell, book
# --------------------------------------------------------------------------
#: The whole sequence, in order. Two plan reads, one cancel, two CONFIRM reads,
#: one sell. **The two read pairs are not the same reads** -- ruling 4 requires
#: the second pair be taken AFTER the cancel, because a read taken before it
#: cannot see a leg that filled during it.
FULL_CLOSE = [
    "get_order",
    "get_order",
    "cancel_order_list",
    "get_order",
    "get_order",
    "create_order",
]


def _selling_client(**kwargs: Any) -> FakeClient:
    """A fake whose legs are quiet, so the plan says SELL and the path runs."""
    kwargs.setdefault("leg_answers", {"SL": _leg("0"), "TP": _leg("0")})
    return FakeClient(**kwargs)


class TestTheCloseExecutes:
    """The cancel, the re-confirm, the sell and the booking.

    **THIS IS THE ONLY SUITE COVERING IRREVERSIBLE VENUE WRITES THE BOT SENDS
    OF ITS OWN VOLITION**, and none of it has run against a venue.
    """

    async def test_the_full_sequence_is_six_calls_then_one_settlement_read(self) -> None:
        """**THE ORDERING, asserted as a list rather than a count.**

        MUTATION: sell before cancelling; or skip the re-confirm.

        Section 4b forces cancel-then-sell: the reverse leaves the position flat
        with a live protective leg, which can sell base no longer held. A count
        would pass under a reordering; the list will not. And the two `get_order`
        pairs straddling the cancel are what ruling 4 requires -- collapsing them
        into one pair passes a count of six and fails this.

        This read `..._is_exactly_six_calls_in_order` until the fee commit, which
        adds the SEVENTH call: the settlement read, after the sell and before the
        booking. The name is corrected because it describes the tree.
        """
        client = _selling_client()
        executor, _, _ = build(client=client, portfolio=_held())

        await executor.dispatch(close_signal(), exit_assessment(), candle())

        assert client.venue_calls == [*FULL_CLOSE, "get_my_trades"]

    async def test_a_close_is_refused_while_a_close_record_is_pending(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """THE CLOSE GUARD. A second CLOSE is refused BEFORE any venue read.

        MUTATION: drop the guard, or move it below `_plan_close`. Either way the
        cancelled legs below report nothing executed, the plan is SELL, and the
        path reads, cancels and sells -- a second MARKET sell.

        **THE LEGS MUST BE CANCELED WITH NOTHING EXECUTED**, because that is
        exactly what a symbol whose close is pending reports, and it is the
        only fixture under which the unguarded path SELLS. The next test is
        its control: the same fixture with no record does sell.
        """
        client = _selling_client(
            leg_answers={
                "SL": _leg("0", OrderStatus.CANCELED),
                "TP": _leg("0", OrderStatus.CANCELED),
            }
        )
        executor, _, portfolio = build(client=client, portfolio=_held())
        record = _close()
        executor._pending[SYMBOL] = record

        with caplog.at_level(logging.DEBUG, logger=_EXEC_LOGGER):
            await executor.dispatch(close_signal(), exit_assessment(), candle())

        assert client.venue_calls == []
        assert client.sold == []
        assert client.cancelled == []
        assert [r.reason for r in _records(caplog, "dispatch_refused")] == ["close_pending"]
        assert executor._pending[SYMBOL] is record
        assert SYMBOL in portfolio.positions

    async def test_a_close_with_no_pending_record_still_proceeds(self) -> None:
        """The guard's CONTROL: the same fixture, no record, and the sell goes out.

        This is what proves the fixture above plans SELL -- without it, a
        refusal there could come from the plan rather than the guard.
        MUTATION: refuse every CLOSE, or refuse on any pending record.
        """
        client = _selling_client(
            leg_answers={
                "SL": _leg("0", OrderStatus.CANCELED),
                "TP": _leg("0", OrderStatus.CANCELED),
            }
        )
        executor, _, _ = build(client=client, portfolio=_held())

        await executor.dispatch(close_signal(), exit_assessment(), candle())

        assert client.venue_calls == [*FULL_CLOSE, "get_my_trades"]
        assert len(client.sold) == 1

    async def test_the_cancel_uses_the_venue_numeric_id(self) -> None:
        """MUTATION: cancel with `position.order_list_id`.

        That is the run-1 substitution, now on an irreversible write. The fake
        records what it was actually handed, so a cancel addressed by our
        `tb1-...` id fails here rather than at the venue -- where it would
        either error or, worse, address someone else's list.
        """
        client = _selling_client()
        executor, _, _ = build(client=client, portfolio=_held())

        await executor.dispatch(close_signal(), exit_assessment(), candle())

        assert client.cancelled == [(SYMBOL, int(VENUE_LIST_ID))]

    async def test_a_missing_venue_id_refuses_before_any_call(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """RULING 1. **No fallback to the documented client id.**

        MUTATION: fall back to `listClientOrderId` when the number is absent.

        Binance documents that alternative and this project has NEVER SENT ONE.
        Staking an irreversible write on an unmeasured wire parameter, when the
        verified path is simply absent, is the gamble the refusal exists to
        refuse. Asserting ZERO calls is the point: the refusal precedes the
        cancel, so nothing is at the venue to undo.
        """
        client = _selling_client()
        executor, _, _ = build(client=client, portfolio=_held(venue_id=None))

        with caplog.at_level(logging.DEBUG, logger=_EXEC_LOGGER):
            await executor.dispatch(close_signal(), exit_assessment(), candle())

        refusals = _records(caplog, "dispatch_refused")
        assert refusals[-1].reason == "close_no_venue_list_id"  # type: ignore[attr-defined]
        assert client.cancelled == [] and client.sold == []

    async def test_a_persist_failure_refuses_before_the_cancel(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """**RULING 3, and the assertion that matters is `cancelled == []`.**

        MUTATION: move the persist to after the cancel.

        `dispatch`'s entry path persists before ONE venue write. Here the record
        covers a SEQUENCE whose first irreversible step is the cancel -- so a
        persist that failed after it would leave a position with its protection
        gone and no durable trace anything was attempted. Refusing here costs
        nothing because nothing has been sent, which is exactly what the empty
        `cancelled` list says.
        """

        def _boom(_records: object) -> None:
            raise OSError("no space left on device")

        client = _selling_client()
        executor, _, _ = build(client=client, portfolio=_held(), persist=_boom)

        with caplog.at_level(logging.DEBUG, logger=_EXEC_LOGGER):
            await executor.dispatch(close_signal(), exit_assessment(), candle())

        refusals = _records(caplog, "dispatch_refused")
        assert refusals[-1].reason == "store_unwritable"  # type: ignore[attr-defined]
        assert client.cancelled == []
        assert client.sold == []

    async def test_a_pending_close_is_written_before_the_cancel(self) -> None:
        """The record exists by the time the first venue write goes out.

        MUTATION: write the record after the sell.

        Asserted on what the WRITER received rather than on `_pending`, because
        the in-memory dict is cleared on success and would show nothing
        afterwards -- so a test reading it would pass for a record that was
        never persisted at all.

        **IT RECORDS THE VENUE CALLS AS THEY STOOD WHEN THE WRITE HAPPENED, and
        the first draft did not.** That draft asserted the record's CONTENT
        only, so it could not fail the very mutation it is named for -- moving
        the persist after the cancel leaves the content identical. The gap was
        found by predicting the mutation's failure set and noticing this test
        was not in it. Capturing the call log inside the writer turns the name
        into an assertion.
        """
        written: list[tuple[Pending, ...]] = []
        seen_at_write: list[list[str]] = []
        client = _selling_client()

        def _persist(records: tuple[Pending, ...]) -> None:
            written.append(records)
            seen_at_write.append(list(client.venue_calls))

        executor, _, _ = build(client=client, portfolio=_held(), persist=_persist)

        await executor.dispatch(close_signal(), exit_assessment(), candle())

        assert written, "nothing was ever persisted"
        first = written[0]
        assert [r.kind for r in first] == ["close"]
        assert first[0].symbol == SYMBOL
        assert first[0].quantity == CLOSE_QTY
        # THE ORDERING: only the plan's two reads had happened. No cancel.
        assert seen_at_write[0] == ["get_order", "get_order"]

    async def test_minus_2011_is_normal_and_proceeds_to_the_requery(self) -> None:
        """`-2011` means already terminal, NOT an error.

        MUTATION: treat `OrderNotFoundError` like any other cancel failure.

        Section 4b: *"A close path written to drive three cancels to success
        would treat its own normal teardown as two errors."* And `-2011` cannot
        distinguish already-cancelled from already-FILLED, which demand opposite
        actions -- so it must proceed to the re-query, which is the only thing
        that separates them.
        """
        client = _selling_client(cancel_answer=OrderNotFoundError("Unknown order sent."))
        executor, _, _ = build(client=client, portfolio=_held())

        await executor.dispatch(close_signal(), exit_assessment(), candle())

        assert client.venue_calls == [*FULL_CLOSE, "get_my_trades"]

    async def test_any_other_cancel_failure_does_not_sell(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """The venue state is unknown, so selling could sell against a live stop.

        MUTATION: proceed to the sell on any cancel failure.

        `CRITICAL` rather than a warning because nothing else marks this: the
        position keeps whatever protection it has and entries are not blocked,
        so the log line is all an operator gets.
        """
        client = _selling_client(cancel_answer=ExchangeConnectionError("reset"))
        executor, _, _ = build(client=client, portfolio=_held())

        with caplog.at_level(logging.DEBUG, logger=_EXEC_LOGGER):
            await executor.dispatch(close_signal(), exit_assessment(), candle())

        assert client.sold == []
        assert [r.levelno for r in _records(caplog, "close_cancel_failed")] == [logging.CRITICAL]

    async def test_a_leg_that_filled_during_the_cancel_abandons_the_sell(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """**RULING 4's WHOLE POINT, and only the second read can see it.**

        MUTATION: reuse the plan's reads instead of re-querying.

        The fake answers quietly on the first pair and FILLED on the second, so
        the plan says SELL and the confirm says ALREADY_CLOSED. Under the
        mutation the sell goes out against a position the venue has already
        closed -- a double sell, which is the failure section 4b's ordering
        exists to prevent. A fixture that answered the same both times could not
        express it.
        """

        class _ChangingClient(FakeClient):
            def __init__(self) -> None:
                super().__init__(leg_answers={"SL": _leg("0"), "TP": _leg("0")})
                self._pairs = 0

            async def get_order(self, symbol: str, **kwargs: Any) -> Order:
                order = await super().get_order(symbol, **kwargs)
                self._pairs += 1
                if self._pairs > 2:  # the SECOND pair, taken after the cancel
                    return _leg("0.5", status=OrderStatus.FILLED)
                return order

        client = _ChangingClient()
        executor, _, portfolio = build(client=client, portfolio=_held())

        with caplog.at_level(logging.DEBUG, logger=_EXEC_LOGGER):
            await executor.dispatch(close_signal(), exit_assessment(), candle())

        assert client.sold == []
        assert _records(caplog, "close_abandoned_after_cancel")
        assert portfolio.ledger is None  # and nothing was booked here

    async def test_a_full_fill_books_the_venues_exact_quote_total(self) -> None:
        """**THE BOT'S OWN EXIT REACHING THE LEDGER.**

        MUTATION: book `quantity * a derived price` instead of the total.

        The total is the venue's own figure and booking takes it verbatim --
        recovering a price by dividing is MEASURED lossy to 28 digits, and
        `_dump_money` writes such a residual into `data/state.json`. The fixture
        sets the total APART from the cost basis (51.25 against 49.0), so the
        realised figure is a non-zero +2.25 and a wrong or absent booking moves
        it.
        """
        client = _selling_client()
        executor, _, portfolio = build(client=client, portfolio=_held())

        await executor.dispatch(close_signal(), exit_assessment(), candle())

        assert portfolio.ledger is not None
        assert portfolio.ledger.realised_pnl == D("2.25000000")
        assert portfolio.free_quote == D("10000") + SELL_TOTAL
        assert SYMBOL not in portfolio.positions

    async def test_a_response_without_the_total_is_point_queried(self) -> None:
        """P-c's fallback. **The total is never invented.**

        MUTATION: book `Decimal(0)` when the response carries no total.

        `newOrderRespType` is set NOWHERE in this tree, so the response shape is
        DOCUMENTED and never measured here -- the only MARKET payload the
        repository holds is a hand-written fixture. So a missing total is a real
        possibility, and the answer is to re-read the sell by the id it was sent
        under, which is what C1's `close_client_order_id` was built for.
        """
        client = _selling_client(sell_answer=sell_fill(total=None))
        # The re-read answers with the total; keyed by the close leg suffix.
        client._leg_answers = {  # type: ignore[assignment]
            "SL": _leg("0"),
            "TP": _leg("0"),
            "CL": sell_fill(),
        }
        executor, _, portfolio = build(client=client, portfolio=_held())

        await executor.dispatch(close_signal(), exit_assessment(), candle())

        assert client.venue_calls == [*FULL_CLOSE, "get_order", "get_my_trades"]
        assert client.order_queries[-1].endswith("-CL")
        assert portfolio.ledger is not None
        assert portfolio.ledger.realised_pnl == D("2.25000000")

    async def test_a_complete_fill_the_venue_never_priced_reaches_the_naked_guard(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """**Q AT SITE 2. The PATH and the STATE -- deliberately not the label.**

        MUTATION: route this state to `_sold_unbooked`; drop the position.

        **THE SIBLING OF THE TEST ABOVE WITH ONE AXIS CHANGED.** That one lets
        the requery ANSWER with a total; this one lets it answer with none. The
        create-order response is byte-identical between them, so a pass here
        and there together say the tail discriminates on the POST-REQUERY total
        rather than on the response's own field -- which is the ordering
        `_sell_and_book` states and nothing else pins.

        **THE `"CL"` KEY IS PRESENT AND EXPLICIT, AND THAT IS LOAD-BEARING.**
        `_selling_client` seeds only `SL` and `TP`, and `FakeClient.get_order`
        subscripts that dict, so omitting `CL` reaches `None` by `KeyError`
        through `_requery_sell_total`'s bare ``except``. The path would then be
        driven by a FIXTURE DEFECT rather than by the venue answer the test
        claims to model -- the fake deciding the result, which is the hazard
        `FakeRootClient.get_all_order_lists` already records.

        **NOTHING IN THE TREE REACHED THIS BRANCH BEFORE THIS TEST.** MEASURED
        by instrumenting the three tail exits across the whole module: 15 tests
        reach the tail, 2 of them go naked, and BOTH arrive via `PARTIAL_FILL`.
        The `NO_QUOTE_TOTAL` disjunct had zero coverage -- `M5i-098`.

        **IT ASSERTS NO LABEL, ON PURPOSE.** Commit B corrects the reason code
        and the operator text; this test must survive that untouched, so it
        pins only what B preserves. Its sibling `..._is_reported_as_partial_-
        today` pins the label and IS rewritten by B. One instrument, one
        measurement, kept apart so a failure says which moved.
        """
        client = _selling_client(sell_answer=sell_fill(total=None))
        # The re-read answers, and STILL carries no total -- so the venue
        # priced this complete fill neither time.
        client._leg_answers = {  # type: ignore[assignment]
            "SL": _leg("0"),
            "TP": _leg("0"),
            "CL": sell_fill(total=None),
        }
        executor, _, portfolio = build(client=client, portfolio=_held())

        with caplog.at_level(logging.DEBUG, logger=_EXEC_LOGGER):
            await executor.dispatch(close_signal(), exit_assessment(), candle())

        # THE SELL REALLY HAPPENED, and the fallback really ran.
        assert client.venue_calls == [*FULL_CLOSE, "get_order"]
        assert client.order_queries[-1].endswith("-CL")

        # THE GUARD BOUND, and the drop-unbooked branch did not.
        assert len(_records(caplog, "close_sold_unpriced")) == 1
        assert _records(caplog, "close_sold_unbooked") == []

        # THE POSITION IS RETAINED, and nothing was booked.
        assert SYMBOL in portfolio.positions
        assert portfolio.ledger is None

    async def test_a_complete_fill_the_venue_never_priced_says_so_and_nothing_else(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """**B6, AND BOTH POLARITIES -- the absent half is the one that cost.**

        MUTATION: revert the reason to `close_partial_fill`; restore
        `_go_naked`'s wording on this branch; emit under
        `close_position_naked`.

        **THIS TEST REPLACED ONE THAT ASSERTED THE OPPOSITE, DELIBERATELY.**
        Commit A shipped this state under `close_partial_fill` and pinned it
        that way, in a test whose docstring said in words that every assertion
        in it was a falsehood. That was a BEFORE-measurement: a fixture written
        after a change agrees with the code beside it and demonstrates nothing,
        so the diff between that test's assertions and these is the evidence
        that the label moved. A reader finding both versions in the history is
        seeing that method, not a reversal.

        **THE THREE FALSEHOODS, EACH ASSERTED ABSENT BY NAME.** On a COMPLETE
        fill `close_partial_fill` says "partial" of a whole sell, *"still
        open"* describes base that is gone, and *"selling the base manually"*
        instructs a SECOND sale of an asset already sold -- `M5i-035`'s
        measured money bug, reached through a second branch. A test asserting
        only what is present would pass with the false phrase beside the true
        one, which is the state `M5i-007` found.

        **AND THE EVENT NAME IS ASSERTED TWICE OVER**, because an operator
        filtering on `close_position_naked` must not find this record and one
        filtering on `close_sold_unbooked` must not either: that branch DROPS
        the position and this one keeps it, so the two cannot share a name
        without sending a reader to look for a position that is or is not
        there.

        `dispatch_refused` is asserted ABSENT. The close SUCCEEDED -- the venue
        is flat and the signal got what it asked for -- so a refusal here would
        be logged against a `CLOSE` that did its job. That is `_sold_unbooked`'s
        stated discriminator, and `_go_naked_retaining` refuses instead because
        ITS sell may never have happened.
        """
        client = _selling_client(sell_answer=sell_fill(total=None))
        client._leg_answers = {  # type: ignore[assignment]
            "SL": _leg("0"),
            "TP": _leg("0"),
            "CL": sell_fill(total=None),
        }
        executor, _, portfolio = build(client=client, portfolio=_held())

        with caplog.at_level(logging.DEBUG, logger=_EXEC_LOGGER):
            await executor.dispatch(close_signal(), exit_assessment(), candle())

        records = _records(caplog, "close_sold_unpriced")
        assert len(records) == 1, "B6's branch did not fire; the Q exit is gone"
        (record,) = records
        message = record.getMessage()
        resolution = record.resolution  # type: ignore[attr-defined]

        assert record.levelno == logging.CRITICAL
        # ITS OWN NAME. Neither neighbour may claim this record.
        assert _records(caplog, "close_position_naked") == []
        assert _records(caplog, "close_sold_unbooked") == []
        # ...and no refusal, because the close did what it was asked.
        assert _records(caplog, "dispatch_refused") == []

        # MUST NOT call a whole fill partial.
        assert record.reason == "close_no_quote_total"  # type: ignore[attr-defined]
        assert "partial" not in message
        assert "partial" not in resolution
        # MUST NOT say the position is still open at the venue.
        assert "still open" not in message
        assert "still open" not in resolution
        # MUST NOT instruct a second sale of base already gone. THE EXPENSIVE ONE.
        assert "selling the base" not in resolution
        assert "SELF-REFRESHING" not in resolution

        # ...and MUST say what is actually known, which is four things.
        assert "FILLED" in message
        assert "NO QUOTE TOTAL" in message
        assert "NOTHING WAS BOOKED" in resolution
        assert "DO NOT SELL THIS BASE AGAIN" in resolution
        assert "trade history" in resolution
        # The handle an operator reconciles by.
        assert record.close_client_order_id.endswith("-CL")  # type: ignore[attr-defined]

        # THE POSITION IS KEPT and marked, which is what refuses entries.
        assert SYMBOL in portfolio.positions
        assert portfolio.positions[SYMBOL].protection is ProtectionState.UNKNOWN
        assert portfolio.ledger is None

    async def test_an_unpriced_partial_sell_goes_naked_with_zero_calls_after_the_sell(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """**DECISION 1 AT SITE A: P is decided before any requery.**

        MUTATION: restore `A > Q > P > C`; or move the requery back ahead of
        the classification.

        FABRICATED: the sell's response carries no total, which no capture
        holds (`M5k-093`). **THE FAKE WOULD RECORD A REQUERY**: `get_order`
        appends to `venue_calls` before it answers, and the `"CL"` answer is
        configured -- priced, so a requery made here would even succeed -- so
        `venue_calls == FULL_CLOSE` fails on the one extra call either mutation
        spends. Until 3b-2a this input was re-read and reached `_sold_unpriced`,
        whose line says the sell FILLED IN FULL; `close_sold_unpriced` is
        asserted absent for that reason.
        """
        client = _selling_client(sell_answer=sell_fill(executed=D("0.2"), total=None))
        client._leg_answers = {  # type: ignore[assignment]
            "SL": _leg("0"),
            "TP": _leg("0"),
            "CL": sell_fill(executed=D("0.2")),
        }
        executor, _, portfolio = build(client=client, portfolio=_held())

        with caplog.at_level(logging.DEBUG, logger=_EXEC_LOGGER):
            await executor.dispatch(close_signal(), exit_assessment(), candle())

        assert client.venue_calls == FULL_CLOSE
        naked = _records(caplog, "close_position_naked")
        assert len(naked) == 1, "the partial did not go naked"
        assert vars(naked[0]).get("reason") == "close_partial_fill"
        assert _records(caplog, "close_sold_unpriced") == []
        # Base remains at the venue, so the position is KEPT, untrusted.
        assert SYMBOL in portfolio.positions
        assert portfolio.positions[SYMBOL].protection is ProtectionState.UNKNOWN
        assert portfolio.ledger is None

    async def test_an_unpriced_cost_basis_less_sell_is_dropped_with_zero_calls_after_the_sell(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """**THE PROJECT OWNER'S PIN-1: drop through `_sold_unbooked`, no requery.**

        MUTATION: keep the unpriced position instead of dropping it; restore
        `A > Q > P > C`; or move the requery back ahead of the classification.

        FABRICATED: no capture holds an absent total (`M5k-093`). The fake
        would record a requery, and its `"CL"` answer is priced, so a requery
        spent here would succeed and still fail `venue_calls == FULL_CLOSE`.
        Until 3b-2a this input was re-read and KEPT by `_sold_unpriced`.

        **THE LINE OMITS `quote_total`, NEVER NULL** -- asserted on the key,
        through `vars(record)`, beside `executed_qty`, which shows the order
        reached the line: an absent key on a line that dropped the order too
        would prove nothing.
        """
        portfolio = _held(entry_fill=None)
        client = _selling_client(sell_answer=sell_fill(total=None))
        client._leg_answers = {  # type: ignore[assignment]
            "SL": _leg("0"),
            "TP": _leg("0"),
            "CL": sell_fill(),
        }
        executor, _, _ = build(client=client, portfolio=portfolio)

        with caplog.at_level(logging.DEBUG, logger=_EXEC_LOGGER):
            await executor.dispatch(close_signal(), exit_assessment(), candle())

        assert client.venue_calls == FULL_CLOSE
        dropped = _records(caplog, "close_sold_unbooked")
        assert len(dropped) == 1, "the cost-basis-less sell was not dropped"
        fields = vars(dropped[0])
        assert fields.get("executed_qty") == CLOSE_QTY
        assert "quote_total" not in fields
        assert fields.get("outcome") == "filled_and_released"
        assert _records(caplog, "close_sold_unpriced") == []
        # DROPPED, not booked, and the record released.
        assert SYMBOL not in portfolio.positions
        assert portfolio.ledger is None
        assert portfolio.free_quote == D("10000")
        assert executor._pending == {}

    async def test_an_unpriced_whole_sell_with_its_cost_basis_still_requeries_then_is_kept(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """**THE CONTROL for the two zero-call tests above: Q still requeries.**

        MUTATION: skip the requery on Q.

        The same fake shape with both other facts false, so what reached the
        requery there would reach it here -- and here it MUST. The response and
        the re-read both carry no total (FABRICATED, `M5k-093`), so the sell
        reaches `_sold_unpriced` exactly as before 3b-2a. DECLARED: this
        overlaps `..._never_priced_reaches_the_naked_guard` on purpose, and it
        abstains from every reorder mutation, because Q wins on this input
        under either order.
        """
        client = _selling_client(sell_answer=sell_fill(total=None))
        client._leg_answers = {  # type: ignore[assignment]
            "SL": _leg("0"),
            "TP": _leg("0"),
            "CL": sell_fill(total=None),
        }
        executor, _, portfolio = build(client=client, portfolio=_held())

        with caplog.at_level(logging.DEBUG, logger=_EXEC_LOGGER):
            await executor.dispatch(close_signal(), exit_assessment(), candle())

        assert client.venue_calls == [*FULL_CLOSE, "get_order"]
        assert client.order_queries[-1].endswith("-CL")
        unpriced = _records(caplog, "close_sold_unpriced")
        assert len(unpriced) == 1, "the whole unpriced sell did not reach _sold_unpriced"
        assert vars(unpriced[0]).get("reason") == "close_no_quote_total"
        assert _records(caplog, "close_sold_unbooked") == []
        assert SYMBOL in portfolio.positions
        assert portfolio.ledger is None

    async def test_a_partial_fill_books_nothing_and_goes_naked(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """**RULING 5, and it must fail closed because a partial CANNOT BE
        REPRESENTED.**

        MUTATION: book the partial's total.

        `close_position` deletes the whole entry and credits one total; there is
        no partial-close path and no way to say "0.3 of 0.5 sold". Booking it
        would delete a position that still exists at the venue and credit
        proceeds for base still held -- a corrupted ledger, in the direction
        nobody notices.

        DECLARED RESIDUAL: `Position.quantity` is now OVERSTATED, and this
        design cannot close that. It is asserted here so the defect is pinned
        rather than merely described.
        """
        client = _selling_client(sell_answer=sell_fill(executed=D("0.2")))
        executor, _, portfolio = build(client=client, portfolio=_held())

        with caplog.at_level(logging.DEBUG, logger=_EXEC_LOGGER):
            await executor.dispatch(close_signal(), exit_assessment(), candle())

        assert portfolio.ledger is None
        assert portfolio.free_quote == D("10000")
        assert portfolio.positions[SYMBOL].protection is ProtectionState.UNKNOWN
        # THE RESIDUAL, pinned: the position still claims the whole size.
        assert portfolio.positions[SYMBOL].quantity == CLOSE_QTY

    async def test_a_client_refused_sell_leaves_the_position_naked_and_says_so(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """**RULING 6, NOW SCOPED TO A SELL THAT PROVABLY DID NOT HAPPEN.**

        MUTATION: retry the sell, or leave `protection` untouched, or send a
        `ClientRefusalError` down the retaining branch.

        **THIS TEST'S INPUT CHANGED AT B1 AND ITS SUBJECT DID NOT.** It drove
        `ExchangeConnectionError` when every exception out of the sell came
        here; that input now takes the RETAINING branch, because the socket
        expiring does not mean the venue refused. `ClientFilterRejectedError`
        carries the `ClientRefusalError` marker -- *no request left this
        process* -- so the sell provably did not happen, nothing rests, and the
        self-refreshing operator-only state below is the true one.

        No retry: a second sell could double-sell if the first landed and
        nothing here can tell those apart. `UNKNOWN` is what blocks entries
        portfolio-wide, which is the only automatic consequence this state has.

        The `resolution` field is asserted because ruling 6 requires the log to
        SAY the state is self-refreshing -- a `CRITICAL` that did not would
        leave an operator waiting for a reconciler that never resolves it. On
        THIS branch that instruction is correct, and the sibling test in
        `TestAnUnconfirmedSellIsRetained` asserts it is absent on the other.
        """
        client = _selling_client(
            sell_answer=ClientFilterRejectedError("off tick", filter_name="PRICE_FILTER")
        )
        executor, _, portfolio = build(client=client, portfolio=_held())

        with caplog.at_level(logging.DEBUG, logger=_EXEC_LOGGER):
            await executor.dispatch(close_signal(), exit_assessment(), candle())

        naked = _records(caplog, "close_position_naked")
        assert [r.levelno for r in naked] == [logging.CRITICAL]
        assert naked[0].reason == "close_sell_failed"  # type: ignore[attr-defined]
        assert "SELF-REFRESHING" in naked[0].resolution  # type: ignore[attr-defined]
        assert "restarting" in naked[0].resolution  # type: ignore[attr-defined]
        assert portfolio.positions[SYMBOL].protection is ProtectionState.UNKNOWN
        assert portfolio.ledger is None
        # RELEASED, as before: there is nothing at the venue to ask about.
        assert executor._pending == {}

    async def test_the_unprotected_window_is_logged_on_entry(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Section 4b requires the window logged. **Entry only; see the site.**

        MUTATION: drop the window log.

        There is no exit event because the naked state does not resolve
        in-process -- half-satisfiable as designed, and recorded rather than
        quietly dropped. The entry log is emitted BEFORE the cancel, so it
        exists even when the process dies during the sequence.
        """
        client = _selling_client()
        executor, _, _ = build(client=client, portfolio=_held())

        with caplog.at_level(logging.DEBUG, logger=_EXEC_LOGGER):
            await executor.dispatch(close_signal(), exit_assessment(), candle())

        opened = _records(caplog, "close_window_open")
        assert len(opened) == 1
        assert opened[0].venue_order_list_id == int(VENUE_LIST_ID)  # type: ignore[attr-defined]

    async def test_a_booked_close_releases_the_pending_record(self) -> None:
        """The symbol is not blocked forever once the outcome is known.

        MUTATION: leave the record in `_pending`.

        The pending guard refuses every later dispatch on a symbol that has one,
        so a record never released would block the symbol permanently.

        **THE SECOND HALF OF THIS ARGUMENT EXPIRED and is corrected in place
        rather than annotated, because it is a claim about the tree.** It read
        *"`__call__` deliberately skips a `PendingClose`, so nothing else would
        clear it either"*, which was true when written and false since
        C5c-EXEC: `__call__` hands a close to `_resolve_close`, whose `finally`
        releases it. So a record left here is cleared one candle later rather
        than never -- which is exactly what B1's retention relies on, and
        leaving the opposite claim standing beside it would mislead the next
        reader of either. What survives is the first half: releasing HERE, on a
        booked close, is what stops a symbol whose outcome is already known
        from costing a resolution query at all.
        """
        client = _selling_client()
        executor, _, _ = build(client=client, portfolio=_held())

        await executor.dispatch(close_signal(), exit_assessment(), candle())

        assert executor._pending == {}


class TestAnUnbookableSellIsDropped:
    """B-i. The bot's OWN sell completed and cannot be priced.

    **THIS SUITE REMOVES A LIVE PERMANENT HALT, NOT A LOG-LINE
    INCONSISTENCY** -- `M5i-045`. MEASURED at `24d0a7c`, before B-i: this exact
    input emitted `close_book_failed` and LEFT THE POSITION IN MEMORY for base
    already sold at the venue. Its legs were cancelled, so `classify_protection`
    answers `DIVERGED` and re-stamps it on every pass -- `POSITION_STALE` never
    fires, nothing books it, and `UNKNOWN` outside `_TRUSTED_PROTECTION` refuses
    entries PORTFOLIO-WIDE until a restart. Commit 3a's body called that
    behaviour *"SAFER than the naive fix"*, which is true and narrower than it
    reads: safer than routing to `_go_naked`, and not safe.

    **NO EXISTING FIXTURE COULD EXPRESS THIS.** `_held(entry_fill=None)` was
    read by exactly ONE test in the tree before this class, and it is path A's.
    So adding the branch alone was invisible to every test that existed, and a
    green run would have been no evidence whatever -- `M5i-037`/`M5i-038`'s
    shape a second time, on the second path.
    """

    async def test_a_sold_position_with_no_cost_basis_is_dropped_unbooked(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """The branch binds, and the two OLD disjuncts are pinned ABSENT.

        MUTATION: delete the branch; invert its condition.

        `_sell_and_book`'s guard at `:1789` has two disjuncts and BOTH return
        the same way, into `_go_naked`. So a pass here could mean either fired
        unless each is excluded, and the exclusions are asserted rather than
        argued:

        * the sell reached the venue at all -- the full six-call sequence, so no
          pre-sell refusal fired;
        * nothing went naked -- which excludes BOTH disjuncts at once, since
          both route there;
        * the fill is whole -- `executed_qty` against the fixture's own
          quantity, not a literal, excluding the partial disjunct positively;
        * the venue priced it -- `quote_total`, excluding `total is None`.

        Only then does the outcome mean the cost-basis check bound.

        **`close_book_failed` ABSENT IS A REAL DISCRIMINATOR HERE, NOT A VACUOUS
        ONE.** The pre-B-i tree emitted it on this exact input, MEASURED -- so
        this assertion distinguishes "the raise is not reached" from "the raise
        is handled", which is the whole difference between deciding before the
        call and catching after it.
        """
        portfolio = _held(entry_fill=None)
        held_quantity = portfolio.positions[SYMBOL].quantity
        client = _selling_client()
        executor, _, _ = build(client=client, portfolio=portfolio)

        with caplog.at_level(logging.CRITICAL):
            await executor.dispatch(close_signal(), exit_assessment(), candle())

        # THE TWO OLD DISJUNCTS, PINNED ABSENT.
        assert client.venue_calls == FULL_CLOSE  # the sell really happened
        assert _records(caplog, "close_position_naked") == []  # neither disjunct

        (record,) = _records(caplog, "close_sold_unbooked")
        assert record.levelno == logging.CRITICAL
        assert record.executed_qty == held_quantity  # whole, not partial
        assert record.quote_total == SELL_TOTAL  # the venue priced it

        # ...so only the absent cost basis can explain the refusal to book.
        assert record.outcome == "filled_and_released"  # type: ignore[attr-defined]
        assert "NOTHING WAS BOOKED by this bot" in record.resolution  # type: ignore[attr-defined]

        # DROPPED, not booked and not half-booked.
        assert SYMBOL not in portfolio.positions
        assert portfolio.ledger is None
        assert portfolio.free_quote == D("10000")
        assert executor._pending == {}

        # THE RAISE IS NO LONGER REACHED, where the pre-B-i tree reported it
        # from `_book_close`'s except arm on this same input.
        assert _records(caplog, "close_book_failed") == []
        # The close SUCCEEDED. `_sold_unbooked` must not call `_refuse`.
        assert _records(caplog, "dispatch_refused") == []

    async def test_the_unbookable_sell_critical_makes_none_of_the_three_forbidden_claims(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """`M5i-035`'s three falsehoods, each asserted absent. **BOTH POLARITIES.**

        MUTATION: route this state to `_go_naked` instead.

        `_go_naked`'s line says the position is *"UNPROTECTED and still open"*,
        carries `reason=close_partial_fill`, and instructs *"selling the base
        manually"*. All three are false once a complete sell has filled, and the
        third is the money bug: the base is already gone, so an operator
        following it sells twice.

        **A TEST ASSERTING ONLY WHAT IS PRESENT WOULD PASS WITH THE FALSE
        PHRASE BESIDE THE TRUE ONE**, which is precisely the state `M5i-007`
        found one commit ago. So the absences are the load-bearing half.

        The `selling the base` anchor is chosen over `manually` deliberately:
        path A's own message ends *"for manual accounting"*, so the shorter
        anchor would forbid a phrase that is correct elsewhere in the family and
        make this test fail for the wrong reason.
        """
        portfolio = _held(entry_fill=None)
        executor, _, _ = build(client=_selling_client(), portfolio=portfolio)

        with caplog.at_level(logging.CRITICAL):
            await executor.dispatch(close_signal(), exit_assessment(), candle())

        (record,) = _records(caplog, "close_sold_unbooked")
        message = record.getMessage()
        resolution = record.resolution  # type: ignore[attr-defined]

        # MUST NOT say the position is still open.
        assert "still open" not in message
        assert "still open" not in resolution
        assert "UNPROTECTED" not in message
        # MUST NOT carry a partial-fill reason.
        assert getattr(record, "reason", None) != "close_partial_fill"
        assert "partial" not in message
        # MUST NOT instruct a second sale of base that is already gone.
        assert "selling the base" not in resolution
        assert "SELF-REFRESHING" not in resolution

        # ...and MUST say the three things the operator acts on.
        assert "FILLED" in message
        assert "DROPPED UNBOOKED" in message
        assert "That trade is NOT in the ledger" in resolution
        assert "enter it by hand: the executed quantity below" in resolution
        # `M5i-042`: the balance sheet, which no line said before commit 3b.
        assert "free quote balance is NOT credited" in resolution

    async def test_a_partial_fill_with_no_cost_basis_still_goes_naked(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """**THE ORDERING TEST. `M5i-043`, and nothing else in the tree pins it.**

        MUTATION: move B-i's branch ABOVE the `:1789` guard.

        The architect's Phase 1 specified that placement, and a three-state
        probe falsified it. A partial fill with no cost basis is REACHABLE, and
        for it `_go_naked` is CORRECT: `0.3` of the base is still at the venue,
        so *"still open"* is TRUE and the manual sale it instructs is the right
        action for the remainder. B-i's branch placed above the guard captures
        this state and tells the operator the base was fully sold and released
        -- a fresh falsehood in `M5i-035`'s family, pointing the other way.

        **THE FIXTURE VARIES THE ONE AXIS THE ORDERING TURNS ON.** It is the
        sibling of the test above with `executed` changed and nothing else, so a
        pass here and there together say the branch discriminates on whole-fill
        rather than on cost basis alone. Either test alone would be satisfied by
        a check in the wrong place.
        """
        portfolio = _held(entry_fill=None)
        client = _selling_client(sell_answer=sell_fill(executed=D("0.2")))
        executor, _, _ = build(client=client, portfolio=portfolio)

        with caplog.at_level(logging.CRITICAL):
            await executor.dispatch(close_signal(), exit_assessment(), candle())

        (naked,) = _records(caplog, "close_position_naked")
        assert naked.reason == "close_partial_fill"  # type: ignore[attr-defined]
        assert "still open" in naked.getMessage()
        assert "selling the base manually" in naked.resolution  # type: ignore[attr-defined]

        # B-i did NOT fire, and the position is KEPT because base remains.
        assert _records(caplog, "close_sold_unbooked") == []
        assert SYMBOL in portfolio.positions
        assert portfolio.ledger is None


class TestBothPathsPresentTheIdenticalSurface:
    """Ruling 1's requirement, made falsifiable instead of documented.

    **THE RULING IS A CONSTRAINT BETWEEN TWO FILES' WORTH OF BEHAVIOUR AND
    NOTHING ENFORCED IT.** Path A reaches its released branch through
    `_log_close_resolved`; path B reaches the same physical reality through
    `_sold_unbooked`, which deliberately does NOT call that method -- widening
    it would give `M5h-371`'s target a second caller option 3 was not scoped
    for. Two renderings of one state, in two methods, is exactly where a
    wording drifts.

    **SO THE TWO READ ONE VALUE.** `_RESOLVED_RELEASED` is the shared
    `_CloseResolutionText`, and this asserts BYTE-EQUALITY of `outcome` and
    `resolution` across the two emitted records rather than similarity. A test
    comparing each against a literal would pass while the two drifted apart
    from each other, which is the one thing the ruling forbids.
    """

    async def test_outcome_and_resolution_are_byte_equal_across_both_paths(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """MUTATION: restate either string at one site instead of sharing it.

        **NOT `==` AGAINST A LITERAL.** The subject is the AGREEMENT, so the two
        records are compared against EACH OTHER. A literal on both sides would
        turn one test into two independent ones and stop reporting drift the
        moment either literal was updated alongside its site.

        The headline is deliberately NOT compared: path A says *"a pending close
        record was resolved"*, which is false of a live sell, and forcing those
        to match would be the identical-surface requirement misread as identical
        text.
        """
        # PATH A -- a restored record resolved a bar later.
        portfolio_a = _held(entry_fill=None)
        executor_a, _, _ = build(client=_resolving_client(), portfolio=portfolio_a)
        executor_a._pending[SYMBOL] = _close()
        with caplog.at_level(logging.CRITICAL):
            await executor_a(candle())
        (record_a,) = _records(caplog, "close_record_resolved")

        caplog.clear()

        # PATH B -- the bot's own sell, this bar.
        portfolio_b = _held(entry_fill=None)
        executor_b, _, _ = build(client=_selling_client(), portfolio=portfolio_b)
        with caplog.at_level(logging.CRITICAL):
            await executor_b.dispatch(close_signal(), exit_assessment(), candle())
        (record_b,) = _records(caplog, "close_sold_unbooked")

        assert record_a.outcome == record_b.outcome  # type: ignore[attr-defined]
        assert record_a.resolution == record_b.resolution  # type: ignore[attr-defined]

        # The physical reality is identical, so the ledger answer must be too.
        assert portfolio_a.ledger is None and portfolio_b.ledger is None
        assert SYMBOL not in portfolio_a.positions
        assert SYMBOL not in portfolio_b.positions


def _sold(executed: str = "0.5", quote: str = "1810.57726950") -> Order:
    """The venue's answer for a close sell that FILLED."""
    return Order(
        order_id="77",
        symbol=SYMBOL,
        side=OrderSide.SELL,
        type=OrderType.MARKET,
        status=OrderStatus.FILLED,
        quantity=D("0.5"),
        filled_quantity=D(executed),
        filled_quote_quantity=D(quote),
    )


def _resolving_client(answer: Order | Exception | None = None) -> FakeClient:
    """A fake that answers the CLOSE id's point query and nothing else.

    Keyed on the `CL` leg suffix, so a test states its answer in the vocabulary
    the code DERIVES rather than restating a 36-character id -- and a resolution
    that queried some other id would raise `KeyError` here rather than quietly
    getting an answer meant for a different order.
    """
    return FakeClient(leg_answers={"CL": answer if answer is not None else _sold()})


class TestTheCloseResolution:
    """A restored close is resolved: asked about, reported, and let go.

    **THE ACTION IS INVARIANT AND THE QUERY DECIDES NOTHING**, which is the
    ruling and is what these tests are shaped around. Whatever the venue says --
    filled, absent, or nothing at all because the call raised -- the lock is
    cleared from memory AND disk, any local position is dropped UNBOOKED, and
    one CRITICAL carries what was learned. So the tests differ in what they
    assert about the LOG and agree on everything they assert about the ACTION.

    **EVERY TEST DRIVES `await executor(candle())` END TO END.** Not `dispatch`,
    and not a direct `_pending` assignment as the assertion path. The pending
    union's older tests reach `_pending` by assignment and assert `dispatch`,
    which insulates them from how the record is consumed -- exactly the
    blindness that let `test_a_pending_close_is_skipped_by_placement_resolution`
    pin an absence nothing could disturb.

    **WHAT IS ASSERTED BY ABSENCE, and why that needs saying.** Three of the
    rulings are prohibitions -- no sell, no booking, no runtime
    `blocked_symbols` write -- so the tests for them count calls that must be
    zero and inspect a dict that must be empty. An absence is invisible to every
    instrument that searches for a presence, so the mutation survey is the only
    thing that confirms these bite; its verdict is in the commit message.
    """

    async def test_a_filled_close_in_process_is_reported_and_booked(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """**6a, REVERSED BY RULING 5.** The venue says FILLED and we BOOK it.

        MUTATION: drop unbooked here; or book from a derived figure.

        **THIS TEST'S ASSERTION FLIPPED AND ITS SUBJECT DID NOT.** It read
        *"log it, drop it, book NOTHING"*, with `realised_pnl` asserted UNMOVED
        as what separated "reported" from "booked", and its stated mutation was
        *"route the position drop through `close_position`"* -- which is now the
        REQUIRED behaviour. It was correct under R2, whose grounds were that the
        figure is unreconstructable after a restart. In process it is not: the
        `Position` and its `entry_fill_price` are both here. So the test is
        rewritten rather than deleted, and the ledger assertion flips from
        unmoved to moved-by-the-venue's-own-number.

        The fill details still reach the log, and they are still the record an
        operator reads -- but now to CHECK the booking rather than to perform it.
        The restart case keeps the old behaviour and is pinned by
        `test_no_position_present_is_ordinary_and_logs_no_failure` beside it.
        """
        writer = RecordingWriter()
        portfolio = _held()
        executor, client, _ = build(client=_resolving_client(), portfolio=portfolio, persist=writer)
        executor._pending[SYMBOL] = _close()

        with caplog.at_level(logging.CRITICAL):
            await executor(candle())

        (record,) = _records(caplog, "close_record_resolved")
        assert record.levelno == logging.CRITICAL
        assert record.status == "FILLED"
        assert record.executed_qty == D("0.5")
        assert record.quote_total == D("1810.57726950")
        assert record.close_client_order_id.endswith("-CL")
        # The id is DERIVED, and the query carried it.
        assert client.order_queries == [record.close_client_order_id]

        # Nothing was SOLD -- the resolution never dispatches, R1 is untouched.
        assert "create_order" not in client.venue_calls
        # But the trade is now IN THE LEDGER, priced by the venue's own total.
        assert portfolio.ledger is not None
        assert portfolio.ledger.realised_pnl == _EXPECTED_RESOLVED_PNL
        assert portfolio.ledger.trades_count == 1
        # MEASURED: `lifetime_realised` stays `None` after a same-day accrual --
        # it accumulates on the DAY ROLL, and the day has not rolled. Asserted
        # rather than omitted so the absence is deliberate; ABSENT IS NOT ZERO.
        assert portfolio.lifetime_realised is None
        assert portfolio.daily_history == {}
        assert SYMBOL not in portfolio.positions
        # The operator is told NOT to enter it by hand.
        assert record.outcome == "filled_and_booked"
        assert "DO NOT enter this trade by hand" in record.resolution

        # 6e: the lock is gone from memory AND from what reached disk.
        assert executor._pending == {}
        assert writer.calls, "the durable set was never rewritten"
        assert all(r.symbol != SYMBOL for r in writer.calls[-1])

    async def test_a_position_still_open_clears_without_blocking_the_symbol(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """**6b.** P2/P4: the sell never happened, and NOTHING is blocked here.

        MUTATION: write `blocked_symbols[symbol]` on this branch.

        The ruling routes a still-open position to the BOOT SNAPSHOTS -- a live
        order list blocks the symbol, free base above `min_notional` records an
        unmanaged holding -- rather than to a runtime write, which
        `blocked_symbols`' own docstring forbids for the process lifetime.
        `blocked_symbols == {}` is therefore the assertion that pins the ruling,
        and it pins an ABSENCE: only a mutation adding the write can confirm it.
        """
        writer = RecordingWriter()
        portfolio = _held()
        executor, client, _ = build(
            client=_resolving_client(OrderNotFoundError("Order does not exist.")),
            portfolio=portfolio,
            persist=writer,
        )
        executor._pending[SYMBOL] = _close()

        with caplog.at_level(logging.CRITICAL):
            await executor(candle())

        (record,) = _records(caplog, "close_record_resolved")
        assert record.error_type == "OrderNotFoundError"
        assert not hasattr(record, "status")

        # **RETAINED, NOT DROPPED** -- M5h-321a. The sell is unconfirmed, so
        # base inventory may still be at the venue, and the position is the
        # only in-process record of that.
        assert SYMBOL in portfolio.positions
        assert portfolio.positions[SYMBOL].protection is ProtectionState.UNKNOWN

        # THE RULING: no runtime block, no sell, no booking.
        assert portfolio.blocked_symbols == {}
        assert "create_order" not in client.venue_calls
        assert portfolio.ledger is None

        assert executor._pending == {}
        assert writer.calls
        assert all(r.symbol != SYMBOL for r in writer.calls[-1])

    async def test_a_failed_query_still_clears_and_still_escalates(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """**6c.** THE `finally` IS THE SUBJECT, and this is the test for it.

        MUTATION: move the clear out of `finally` into the `try` body.

        Under it a raising query skips the clear, the record survives, and the
        symbol stays locked for ever -- the wedge this whole sequence exists to
        end, reintroduced through the one path nobody drives by hand. The query
        failing is not an exceptional case here: it is the case in which the
        action must be provably unconditional.
        """
        writer = RecordingWriter()
        portfolio = _held()
        executor, client, _ = build(
            client=_resolving_client(TimeoutError("connection reset")),
            portfolio=portfolio,
            persist=writer,
        )
        executor._pending[SYMBOL] = _close()

        with caplog.at_level(logging.CRITICAL):
            await executor(candle())

        (record,) = _records(caplog, "close_record_resolved")
        assert record.error_type == "TimeoutError"
        assert record.error == "connection reset"
        assert executor._pending == {}
        assert writer.calls
        # **RETAINED, NOT DROPPED.** A failed query is not a fill, and this
        # assertion inverted at M5h-321a: it read `SYMBOL not in positions`
        # while the drop was unconditional. An unanswered query is the state
        # where dropping is least defensible -- nothing is known, so the base
        # may still be at the venue.
        assert SYMBOL in portfolio.positions
        assert portfolio.positions[SYMBOL].protection is ProtectionState.UNKNOWN
        # THE PROHIBITIONS HOLD HERE TOO, and they are asserted here rather
        # than only on the not-found branch because an unanswered query is the
        # state in which acting would be least defensible: nothing is known.
        assert "create_order" not in client.venue_calls
        assert portfolio.blocked_symbols == {}
        assert portfolio.ledger is None

    async def test_no_position_present_is_ordinary_and_logs_no_failure(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """**6d.** THE RESTART CASE, which is the one this path exists for.

        MUTATION: treat a missing position as an error.

        `Position` is in-process only and boot reconstructs none, so a record
        restored from the store ALWAYS resolves against an empty
        `portfolio.positions`. That is the ordinary case, not a degraded one,
        and logging it as a failure would put a `collaborator_failed` line on
        every clean recovery -- training an operator to ignore the level that
        carries the real ones.
        """
        writer = RecordingWriter()
        # `build()`'s default portfolio holds NOTHING -- the restart shape.
        executor, _, portfolio = build(client=_resolving_client(), persist=writer)
        executor._pending[SYMBOL] = _close()

        with caplog.at_level(logging.DEBUG):
            await executor(candle())

        assert _records(caplog, "collaborator_failed") == []
        assert len(_records(caplog, "close_record_resolved")) == 1
        assert executor._pending == {}
        assert portfolio.positions == {}

    async def test_a_pending_placement_still_resolves_as_a_placement(self) -> None:
        """**6f.** The close branch must not have captured the other kind.

        MUTATION: make the kind guard admit both -- `if True:`.

        Under it a placement reaches `_resolve_close`, which queries a CLOSE id
        for an order that was never a close, and the placement's own resolution
        never runs. The two instruments are asserted apart: a placement's is
        `get_all_order_lists`, a close's is `get_order`.
        """
        executor, client, _ = build()
        executor._pending[SYMBOL] = PendingPlacement(
            symbol=SYMBOL,
            entry_bar_time=BAR,
            generation=0,
            quantity=D("0.5"),
            entry_limit=D("100"),
            stop_loss=D("95"),
            take_profit=D("110"),
        )

        await executor(candle())

        assert "get_all_order_lists" in client.venue_calls
        assert "get_order" not in client.venue_calls

    async def test_a_trusted_position_is_marked_unknown_when_retained(self) -> None:
        """**THE MARK ITSELF, separated from the retention.**

        MUTATION: retain the position but leave `protection` as it was.

        **THIS TEST EXISTS BECAUSE THE OTHERS CANNOT KILL THAT MUTATION**, and
        that was established before it was written rather than discovered
        afterwards. `_held()` builds its position at `UNKNOWN` already, so every
        other test here asserts a value the fixture supplied -- dropping the
        mark changes nothing they can see, and the entry refusal they imply
        would still fire on `ALREADY_IN_POSITION` alone.

        Starting at `ACTIVE` is what separates them. `ACTIVE` is in
        `_TRUSTED_PROTECTION`, so a position left there has COMPUTABLE
        committed risk and entries are permitted portfolio-wide; marked
        `UNKNOWN` it is untrusted, committed risk cannot be summed, and
        `COMMITTED_RISK_UNKNOWN` refuses every symbol. The mark is the whole
        difference between a one-symbol guard and a portfolio-wide one.
        """
        portfolio = _held(protection=ProtectionState.ACTIVE)
        executor, _, _ = build(
            client=_resolving_client(OrderNotFoundError("Order does not exist.")),
            portfolio=portfolio,
        )
        executor._pending[SYMBOL] = _close()

        await executor(candle())

        assert SYMBOL in portfolio.positions
        assert portfolio.positions[SYMBOL].protection is ProtectionState.UNKNOWN


class _RefusingPortfolio(Portfolio):
    """A real `Portfolio` whose booking write RAISES. **The V5 seam.**

    **IT EXISTS BECAUSE V5 HAD NO FIXTURE AT ALL** -- `M5i-057`. Nothing in the
    tree forced `close_position` to raise, so the state `M5h-371` names had
    never been reachable by any test; it was measured once, by hand, at phase
    1b. A mutation returning a booked verdict from a path that wrote nothing
    killed ZERO tests before this class existed.

    **A SUBCLASS RATHER THAN A FAKE, and that is the fence.** `portfolio.py` is
    fenced for this commit, so nothing there is edited and nothing is
    reimplemented here: this constructs the REAL type, inherits every field,
    validator and invariant, and overrides ONE method to raise. A hand-built
    stand-in would be a second implementation of the ledger inside `tests/`,
    which is the shape that made a mapper test defend a mapper defect at M5d.

    **THE RAISE IS `ValueError`, matching the real failure.** `close_position`'s
    reachable raise comes from `_realised_from_total` and from `free_quote`'s
    `ge=0` under `validate_assignment` -- both `ValueError`. Choosing an exotic
    type would test the `except Exception` breadth rather than the verdict.
    """

    def close_position(self, *args: Any, **kwargs: Any) -> Decimal:
        raise ValueError("the ledger write failed")


def _refusing(**kwargs: Any) -> _RefusingPortfolio:
    """`_held()`'s shape, with a booking write that raises."""
    base = _held(**kwargs)
    return _RefusingPortfolio(
        free_quote=base.free_quote,
        positions=dict(base.positions),
    )


def _no_portfolio() -> None:
    """The RESTART shape: `build()` is handed no portfolio at all.

    A named function rather than a ``lambda`` so the parametrised case reads as
    a state with a name, and so a failure names it too.
    """
    return None


def _resolution_text_selectors() -> set[str]:
    """Every function in `executor.py` that names a `_RESOLVED_*` constant."""
    tree = ast.parse(Path(inspect.getfile(OrderExecutor)).read_text(encoding="utf-8"))
    return {
        fn.name
        for fn in ast.walk(tree)
        if isinstance(fn, ast.AsyncFunctionDef | ast.FunctionDef)
        for node in ast.walk(fn)
        if isinstance(node, ast.Name) and node.id.startswith("_RESOLVED_")
    }


class TestTheLabelHasExactlyOneSelectionSite:
    """`M5i-014`'s constraint, held by a number instead of by a docstring.

    **THE HAZARD IS A SECOND CONVERSION POINT, NOT A BIGGER ONE.** Commit 1
    collapsed `_log_close_resolved`'s two evaluations of the booked/filled chain
    into one, because two copies of one discriminator are what let the headline
    describe a design two commits old. Option 3 MOVES that one expression to
    `_resolve_close`, beside the write whose answer it now reads. It must not
    leave a copy behind, and it must not grow one.

    **THE INSTRUMENT PHASE 1 PROPOSED DOES NOT WORK, and it is corrected here
    rather than quietly dropped** -- `M5i-060`. That was *"module-wide
    `ast.IfExp` count unchanged"*. MEASURED: it went 2 to 1, because a
    three-way NESTED ternary is two `IfExp` nodes and the two-way verdict
    ternary replacing it is one. Only a four-way ternary would have held the
    count -- which would mean a selection structure parallel to the `if/elif/
    else` that performs the actions, and two structures that must agree is the
    exact shape commit 1 removed. **The count was the wrong proxy for the
    thing being protected.**
    """

    def test_exactly_two_functions_name_a_resolution_text(self) -> None:
        """MUTATION: leave the ternary in `_log_close_resolved` as well.

        Both failure directions land on one assertion. A DUPLICATED selection
        makes the set three; a selection LEFT BEHIND puts `_log_close_resolved`
        back in it. `_sold_unbooked` is the second member and is not a second
        discriminator -- it reads ONE constant unconditionally, which is what
        ruling 1's identical-surface requirement asked for at commit 3b.
        """
        assert _resolution_text_selectors() == {"_resolve_close", "_sold_unbooked"}

    def test_the_renderer_no_longer_discriminates(self) -> None:
        """MUTATION: put any conditional expression back in the renderer.

        `_log_close_resolved` now takes a `_CloseResolutionText` and renders it.
        Zero `IfExp` is the checkable form of *"it no longer chooses"*, and it
        is asserted separately from the set above because the two catch
        different things: the set catches a copy anywhere, this catches a
        conditional HERE even if it selected nothing.
        """
        tree = ast.parse(Path(inspect.getfile(OrderExecutor)).read_text(encoding="utf-8"))
        renderer = next(
            fn
            for fn in ast.walk(tree)
            if isinstance(fn, ast.AsyncFunctionDef | ast.FunctionDef)
            and fn.name == "_log_close_resolved"
        )
        assert [n for n in ast.walk(renderer) if isinstance(n, ast.IfExp)] == []


class TestTheBookingVerdictDecidesTheLabel:
    """Option 3, half (i). **`M5h-371` and `M5h-370`/W1.**

    **THE LABEL WAS A PREDICTION AND IS NOW A CONSEQUENCE.** It was computed in
    `_resolve_close`'s `try` from `total is not None` -- the INTENTION to book --
    and emitted before the write ran. A booking that then failed left a CRITICAL
    reading `filled_and_booked` with *"DO NOT enter this trade by hand"*, and a
    separate `close_book_failed` contradicting it two records later.

    **AND NOTHING COULD SEE IT.** `M5h-370`/W1: V2, booking never ran, and V5,
    booking ran and wrote nothing, leave IDENTICAL portfolio state, so no
    assertion over the portfolio separates them. The fourth outcome is what
    does, and `_RefusingPortfolio` is what makes V5 reachable at all.
    """

    async def test_a_booking_that_failed_is_not_labelled_booked(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """**V5. THE MANDATE'S OWN MUTATION MADE KILLABLE.**

        MUTATION: return a booked verdict from `_book_resolved_close`'s
        `except`; or select the text from `total is not None` again.

        Both are the `M5h-371` regression, and before this test neither killed
        anything. The assertions are ordered so a pass can only mean the write
        was ATTEMPTED and FAILED:

        * the booking was reached -- `close_book_failed` is PRESENT, which no
          other resolution branch emits;
        * and the label agrees with it -- `filled_and_book_failed`, not
          `filled_and_booked`.

        Either alone is weak. `close_book_failed` alone was already emitted
        before this commit, beside a label claiming success; the label alone
        could be reached by a branch that never called the writer.
        """
        portfolio = _refusing()
        executor, _, _ = build(client=_resolving_client(), portfolio=portfolio)
        executor._pending[SYMBOL] = _close()

        with caplog.at_level(logging.CRITICAL):
            await executor(candle())

        # THE WRITE WAS ATTEMPTED, and only this branch reports that.
        (failure,) = _records(caplog, "close_book_failed")
        assert failure.error_type == "ValueError"  # type: ignore[attr-defined]

        (record,) = _records(caplog, "close_record_resolved")
        assert record.outcome == "filled_and_book_failed"  # type: ignore[attr-defined]
        # ...and it claims NONE of the three things it must not.
        resolution = record.resolution  # type: ignore[attr-defined]
        assert "DO NOT enter this trade by hand" not in resolution
        assert "the ledger already carries it" not in resolution
        assert "The position is released" not in resolution
        # What it DOES say, per the architect's ruling on the wording.
        assert "BOOKING IT FAILED" in resolution
        assert "HALF-APPLIED" in resolution
        assert "STILL IN MEMORY" in resolution
        # Forbidden across the whole close family: no second sale, no partial.
        assert "selling the base" not in resolution
        assert "partial" not in resolution

        # THE POSITION SURVIVES -- which is why the released text cannot be
        # reused, and is the fact the label now carries.
        assert SYMBOL in portfolio.positions
        assert executor._pending == {}

    async def test_the_label_distinguishes_a_booking_that_never_ran_from_one_that_failed(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """**`M5h-370`/W1 CLOSED, and it is closed by comparison, not assertion.**

        MUTATION: map the failed write to `_RESOLVED_RELEASED`.

        V2 and V5 are driven on one page with the SAME client and the SAME
        answer; the only difference is whether the write raises. Their portfolio
        states are then asserted to differ in the one way they can -- the
        position survives V5 and not V2 -- and their labels to differ at all.

        **THE LABELS ARE COMPARED TO EACH OTHER, NOT TO LITERALS.** A test
        asserting each against its own string would keep passing if both were
        mapped to the same text, which is precisely the mutation. Inequality is
        the subject; the literals are checked in the sibling test above.
        """
        # V2: booking never runs, because the cost basis is absent.
        never_ran = _held(entry_fill=None)
        executor_a, _, _ = build(client=_resolving_client(), portfolio=never_ran)
        executor_a._pending[SYMBOL] = _close()
        with caplog.at_level(logging.CRITICAL):
            await executor_a(candle())
        (v2,) = _records(caplog, "close_record_resolved")
        v2_outcome = v2.outcome  # type: ignore[attr-defined]
        assert _records(caplog, "close_book_failed") == []  # it never ran

        caplog.clear()

        # V5: booking runs and writes nothing.
        ran_and_failed = _refusing()
        executor_b, _, _ = build(client=_resolving_client(), portfolio=ran_and_failed)
        executor_b._pending[SYMBOL] = _close()
        with caplog.at_level(logging.CRITICAL):
            await executor_b(candle())
        (v5,) = _records(caplog, "close_record_resolved")
        v5_outcome = v5.outcome  # type: ignore[attr-defined]
        assert len(_records(caplog, "close_book_failed")) == 1  # it ran

        # THE LEDGER CANNOT TELL THEM APART -- both left it untouched.
        assert never_ran.ledger is None and ran_and_failed.ledger is None
        # THE LABEL CAN.
        assert v2_outcome != v5_outcome
        assert v2_outcome == "filled_and_released"
        assert v5_outcome == "filled_and_book_failed"
        # And the one portfolio fact that does differ agrees with the labels.
        assert SYMBOL not in never_ran.positions
        assert SYMBOL in ran_and_failed.positions


class TestAnUnconfirmedSellIsRetained:
    """The sell was SENT and its outcome is unknown. **Rulings 1-3.**

    **THE SUITE EXISTS BECAUSE ONE STATE BECAME TWO.** Until B1 every exception
    out of the MARKET sell reached `_go_naked`, which tells an operator to sell
    the base by hand. That instruction is safe only when the sell provably did
    not happen. When the socket expires -- or a 2xx will not parse -- the sell
    may already have filled, and following it sells twice. So the branch splits
    on `ClientRefusalError`, and these tests hold the split still.

    `TestTheCloseExecutes::test_a_client_refused_sell_leaves_the_position_naked_and_says_so`
    is this class's negative control and lives there rather than here, beside
    the other close-dispatch tests.
    """

    async def test_a_timeout_class_failure_retains_the_record_in_memory_and_on_disk(
        self,
    ) -> None:
        """**RULING 1. Both halves, because memory alone is not retention.**

        MUTATION: release on every branch; or drop the durable rewrite.

        A record held only in memory is lost to a restart, and the restart is
        exactly the case C5c's boot gate and `_resolve_close` were built for --
        the deterministic close id is what makes the sell resolvable after the
        process dies. So the durable write is asserted through
        `RecordingWriter`, which stands in for the composition root's closure,
        independently of what `_pending` holds.
        """
        client = _selling_client(sell_answer=ExchangeConnectionError("reset"))
        writer = RecordingWriter()
        executor, _, _ = build(client=client, portfolio=_held(), persist=writer)

        await executor.dispatch(close_signal(), exit_assessment(), candle())

        # MEMORY: the lock is held, and it is the close record rather than a
        # placement -- the two share `_pending` and only one is resolvable here.
        assert SYMBOL in executor._pending
        assert executor._pending[SYMBOL].kind == "close"
        # DISK: the last thing written still carries the symbol. Asserted on the
        # writer rather than on `_pending` so a change that kept memory and
        # dropped the rewrite cannot pass.
        assert SYMBOL in writer.symbols(-1)

    async def test_a_client_refusal_releases_where_a_sent_sell_retains(self) -> None:
        """**RULING 1's predicate, both directions in one test.**

        MUTATION: invert the predicate; or drop it so everything retains.

        The two arms differ ONLY in the exception class, so nothing but the
        predicate can explain a difference in outcome. `ClientFilterRejectedError`
        is a real subclass carrying the marker -- measured in this commit's Step
        1, along with `ClientOrderError`, as the two classes `_enforce` raises --
        rather than a hand-rolled stand-in that could drift from the hierarchy
        the predicate actually reads.
        """
        refused = _selling_client(
            sell_answer=ClientFilterRejectedError("off tick", filter_name="PRICE_FILTER")
        )
        executor_a, _, _ = build(client=refused, portfolio=_held())
        await executor_a.dispatch(close_signal(), exit_assessment(), candle())
        assert executor_a._pending == {}

        sent = _selling_client(sell_answer=ExchangeConnectionError("reset"))
        executor_b, _, _ = build(client=sent, portfolio=_held())
        await executor_b.dispatch(close_signal(), exit_assessment(), candle())
        assert SYMBOL in executor_b._pending

    async def test_protection_is_marked_unknown_on_the_retained_branch(self) -> None:
        """**RULING 3**, and the fixture starts at ACTIVE deliberately.

        MUTATION: stop marking protection on the retained branch.

        `_held()` defaults to `UNKNOWN`, so a test taking the default CANNOT
        express this mutation -- the assertion would hold whether or not the
        code wrote anything. That is the masking `M5h-321a` hit one commit ago,
        and the fixture is parameterised precisely so it can be avoided here.

        Ruling 3's grounds, pinned by the assertion rather than only described:
        the order list was cancelled BEFORE the sell, so the asset is physically
        unprotected whatever the sell did. The mark is independent of the sell's
        outcome.
        """
        client = _selling_client(sell_answer=ExchangeConnectionError("reset"))
        executor, _, portfolio = build(
            client=client, portfolio=_held(protection=ProtectionState.ACTIVE)
        )

        await executor.dispatch(close_signal(), exit_assessment(), candle())

        assert portfolio.positions[SYMBOL].protection is ProtectionState.UNKNOWN

    async def test_the_critical_forbids_intervening_and_never_says_sell_by_hand(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """**THE LOG SAFETY TEST. This is what ruling 1 exists for.**

        MUTATION: restore `_go_naked`'s wording on the retained branch; or emit
        under `close_position_naked`.

        **BOTH POLARITIES ARE ASSERTED, and the absent half is the load-bearing
        one.** A test that only checked the new guidance was present would pass
        with the manual-sell instruction sitting beside it, which is the exact
        failure: an operator reading "sell the base manually" after a sell that
        already filled sells twice. So the three claims `_go_naked` makes and
        this branch must not are each asserted ABSENT by name.

        The event name is asserted too, because an operator filtering on
        `close_position_naked` must not find this record at all.
        """
        client = _selling_client(sell_answer=ExchangeConnectionError("reset"))
        executor, _, _ = build(client=client, portfolio=_held())

        with caplog.at_level(logging.DEBUG, logger=_EXEC_LOGGER):
            await executor.dispatch(close_signal(), exit_assessment(), candle())

        # It is NOT filed under the naked event.
        assert _records(caplog, "close_position_naked") == []

        unconfirmed = _records(caplog, "close_sell_unconfirmed")
        assert [r.levelno for r in unconfirmed] == [logging.CRITICAL]
        resolution = unconfirmed[0].resolution  # type: ignore[attr-defined]

        # PRESENT: the guidance ruling 2 requires.
        assert "DO NOT INTERVENE" in resolution
        assert "DO NOT SELL THIS BASE BY HAND" in resolution
        assert "next candle" in resolution
        assert "close_record_resolved" in resolution

        # ABSENT: every claim measured false on this branch.
        assert "manually" not in resolution
        assert "SELF-REFRESHING" not in resolution
        assert "restarting" not in resolution
        assert unconfirmed[0].reason == "close_sell_unconfirmed"  # type: ignore[attr-defined]
        # "failed" asserts a venue state this client does not possess.
        assert "failed" not in unconfirmed[0].reason  # type: ignore[attr-defined]

    async def test_the_retained_record_is_resolved_on_the_next_candle(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """**RULING 1's point: retention is for ASKING.**

        MUTATION: release on the retained branch, so nothing survives to resolve.

        `__call__`'s loop iterates every record in `_pending` regardless of how
        it got there, so an in-process retention reaches `_resolve_close` on the
        next candle exactly as a restored one does. Driven END TO END -- dispatch
        then `await executor(candle())` -- rather than by asserting the record
        exists and trusting the loop, because the loop is the claim.

        The `CL` answer is supplied so the point query has something to return;
        `_resolving_client`'s keying means a resolution that asked for any other
        id would `KeyError` here rather than quietly getting an answer meant for
        a different order.
        """
        client = _selling_client(
            sell_answer=ExchangeConnectionError("reset"),
            leg_answers={"SL": _leg("0"), "TP": _leg("0"), "CL": _sold()},
        )
        executor, _, _ = build(client=client, portfolio=_held())

        with caplog.at_level(logging.DEBUG, logger=_EXEC_LOGGER):
            await executor.dispatch(close_signal(), exit_assessment(), candle())
            assert SYMBOL in executor._pending  # survived the bar that created it
            await executor(candle())

        resolved = _records(caplog, "close_record_resolved")
        assert [r.levelno for r in resolved] == [logging.CRITICAL]
        # `filled_and_BOOKED` since ruling 5: this fixture holds the position in
        # memory, so the confirmed fill is priced and accrued rather than
        # dropped. It read `filled_and_released` at B1, when the resolution
        # booked nothing; the restart case still carries that label.
        assert resolved[0].outcome == "filled_and_booked"  # type: ignore[attr-defined]

    async def test_retention_is_single_shot_on_every_resolution_branch(self) -> None:
        """**Retention must not be able to wedge a symbol.**

        MUTATION: make the release conditional on the venue's answer.

        `_resolve_close` clears the lock in a `finally`, so one bar is the whole
        of what a retained record costs -- on a confirmed fill, on a venue that
        says nothing, and on a query that raises. All three are driven here
        because a release placed on the success path only would pass a test of
        the first alone, and the third is the one that would otherwise hold the
        symbol for ever.

        Disk is asserted as well as memory: a record cleared from `_pending` but
        left in the store would be restored by the next boot and block the
        symbol there instead, which is the same wedge one restart away.
        """
        for answer in (_sold(), _leg("0"), ExchangeConnectionError("query down")):
            client = _selling_client(
                sell_answer=ExchangeConnectionError("reset"),
                leg_answers={"SL": _leg("0"), "TP": _leg("0"), "CL": answer},
            )
            writer = RecordingWriter()
            executor, _, _ = build(client=client, portfolio=_held(), persist=writer)

            await executor.dispatch(close_signal(), exit_assessment(), candle())
            await executor(candle())

            assert executor._pending == {}, f"memory still locked after {answer!r}"
            assert SYMBOL not in writer.symbols(-1), f"disk still locked after {answer!r}"


#: Realised P&L for the DEFAULT resolution fixture, computed the way
#: `close_position` computes it: the venue's own quote total minus the cost
#: basis. `1810.57726950 - (98.00000000 x 0.5)`. Written out rather than
#: derived in the test, so a test that agreed with a broken derivation by
#: sharing it cannot pass.
_EXPECTED_RESOLVED_PNL = D("1761.577269500")

#: A fixture whose quotient does NOT round-trip, for the money rule.
#: `100.00000000 / 0.3` is `333.3333333333333333333333333` and multiplying back
#: gives `99.99999999999999999999999999` -- MEASURED, different from the total.
#: The DEFAULT fixture round-trips exactly (`1810.57726950 / 0.5 x 0.5` is
#: itself), so a division-derived figure is INVISIBLE there: a test using it
#: could not express the mutation at all. This is the fixture-expressiveness
#: rule applied before predicting rather than after.
_LOSSY_QTY = D("0.3")
_LOSSY_TOTAL = "100.00000000"
#: `100.00000000 - (98.00000000 x 0.3)`.
_EXPECTED_LOSSY_PNL = D("70.600000000")


class TestAResolvedFillIsBooked:
    """Ruling 5: a confirmed fill against an in-memory position reaches the ledger.

    **THIS REVERSES A STANDING PROPERTY AND THE SUITE SAYS SO.** Every C5c
    ruling rested on the resolution path moving no figure -- R1 no sell, R2 no
    booking, the query decides nothing. R2's grounds were that after a restart
    there is no `Position` and `PendingCloseRecord` carries no `entry_price`, so
    the figure was UNRECONSTRUCTABLE. That is an engineering constraint, not a
    policy of forfeiting valid accounting, and it does not hold in process.

    So the split is by what is KNOWABLE, not by what happened: position in
    memory and a whole fill priced by the venue means book; anything else means
    drop unbooked, exactly as before. The restart case is unchanged, and the
    tests below pin both sides.
    """

    async def test_an_unconfirmed_sell_confirmed_next_bar_moves_the_ledger(self) -> None:
        """**5a, END TO END from B1's retention.** The whole point of retaining.

        MUTATION: drop unbooked on the confirmed-fill branch.

        Driven through the real sequence -- the sell times out, the record is
        retained, the next candle asks the venue and gets a fill -- rather than
        by seeding `_pending`, because the claim is that B1's retention and B2's
        booking compose. A test that seeded the record would pass with the two
        halves wired to nothing.

        The FIGURE is asserted, not merely that something was written: a booking
        that credited zero would satisfy "the ledger moved".
        """
        client = _selling_client(
            sell_answer=ExchangeConnectionError("reset"),
            leg_answers={"SL": _leg("0"), "TP": _leg("0"), "CL": _sold()},
        )
        executor, _, portfolio = build(client=client, portfolio=_held())

        await executor.dispatch(close_signal(), exit_assessment(), candle())
        assert portfolio.ledger is None, "nothing may be booked before the venue answers"
        await executor(candle())

        assert portfolio.ledger is not None
        assert portfolio.ledger.realised_pnl == _EXPECTED_RESOLVED_PNL
        assert portfolio.ledger.trades_count == 1
        assert SYMBOL not in portfolio.positions
        # The proceeds reached the balance too -- 10000 + 1810.57726950.
        assert portfolio.free_quote == D("11810.57726950")

    async def test_the_booked_figure_is_the_venues_total_and_never_a_quotient(self) -> None:
        """**5d. THE MONEY RULE, on a fixture that can express its violation.**

        MUTATION: derive the total as `quote_total / filled_qty x quantity`.

        `CLAUDE.md` records an exit booked from a derived price under-reporting
        137.36 of 241.15 USDT across three exits, and `filled_quote_quantity` is
        `cummulativeQuoteQty` carried verbatim precisely so nothing re-derives
        it. The default fixture CANNOT catch a re-derivation -- `1810.57726950 /
        0.5 x 0.5` is exactly itself -- so this one uses `100.00000000 / 0.3`,
        whose quotient is non-terminating and whose round trip is
        `99.99999999999999999999999999`.

        Asserted with `==` on `Decimal`, never a tolerance: a figure that is
        merely close is the bug, and a tolerant assertion could not see it.
        """
        portfolio = _held(quantity=_LOSSY_QTY)
        client = _resolving_client(_sold(executed=str(_LOSSY_QTY), quote=_LOSSY_TOTAL))
        # The settlement must account for the whole lossy quantity, or it is
        # refused as incomplete and the close defers instead of booking.
        client._trades_answers = [
            [sell_trade(order_id="77", quantity=_LOSSY_QTY, quote=D(_LOSSY_TOTAL))]
        ]
        executor, _, _ = build(client=client, portfolio=portfolio)
        executor._pending[SYMBOL] = _close()

        await executor(candle())

        assert portfolio.ledger is not None
        assert portfolio.ledger.realised_pnl == _EXPECTED_LOSSY_PNL
        # The credit is the venue's total EXACTLY, to the last place.
        assert portfolio.free_quote == D("10000") + D(_LOSSY_TOTAL)

    async def test_no_position_in_memory_drops_unbooked_and_leaves_the_ledger_absent(
        self,
    ) -> None:
        """**5b. THE RESTART CASE, whose behaviour is deliberately UNCHANGED.**

        MUTATION: book when the position is absent.

        `Position` is in-process only and boot reconstructs none, so a record
        restored from the store always resolves against an empty
        `portfolio.positions`. There is no cost basis and `PendingCloseRecord`
        carries no `entry_price`, so the figure is unreconstructable -- R2's
        original grounds, still holding here and only here.

        **ABSENT IS NOT ZERO**, which is why `ledger is None` is asserted rather
        than `realised_pnl == 0`. A ledger that exists carrying zero would say
        the bot booked a flat trade; `None` says it booked nothing at all, and
        the two are different facts about the day.
        """
        # `build()`'s default portfolio holds NOTHING -- the restart shape.
        executor, client, portfolio = build(client=_resolving_client())
        executor._pending[SYMBOL] = _close()

        await executor(candle())

        assert portfolio.ledger is None
        assert portfolio.free_quote == D("10000")
        assert portfolio.positions == {}
        # A RESTART STARTS WITH NO RETENTION COUNT AND FETCHES NO SETTLEMENT:
        # with no position the fill classifies POSITION_ABSENT, the record is
        # released on this first candle, and the in-memory bound is not needed.
        assert "get_my_trades" not in client.venue_calls
        assert executor._pending == {}
        assert executor._settlement_deferrals == {}

    async def test_a_partial_fill_books_nothing_here_as_it_does_on_the_live_path(
        self,
    ) -> None:
        """**5c. FAIL CLOSED, and for the reason ruling 5 fails closed.**

        MUTATION: book the partial's total.

        `close_position` deletes the WHOLE entry and credits one total; there is
        no partial-close path and no way to express "0.2 of 0.5 sold". Booking
        it would delete a position whose base is still at the venue and credit
        proceeds for it -- a corrupted ledger in the direction nobody notices.
        `_sell_and_book` already fails closed on exactly this and the resolution
        path now agrees with it rather than having its own opinion.

        The DROP is unchanged and pre-existing: a partial has counted as
        `filled` since `M5h-321a` and went to `_drop_position_unbooked` then
        too. This commit does not touch that; it only refuses to BOOK it.
        """
        portfolio = _held()
        client = _resolving_client(_sold(executed="0.2"))
        executor, _, _ = build(client=client, portfolio=portfolio)
        executor._pending[SYMBOL] = _close()

        await executor(candle())

        assert portfolio.ledger is None
        assert portfolio.free_quote == D("10000")

    async def test_a_fill_with_no_quote_total_reported_books_nothing(self) -> None:
        """A fill the venue priced for nobody. **No total, no booking.**

        MUTATION: fall back to a derived figure when the total is absent.

        `filled_quote_quantity` is `Money | None` and that field's own docstring
        keeps the two apart: `None` means THE VENUE DID NOT REPORT IT, where
        zero means it reported nothing filled. There is no fallback by design --
        `close_position` would have to be handed a number this process invented.

        Unreachable through `_sold()`, which always carries a total, so the
        `Order` is built here directly. That is the point: the branch exists for
        a venue response shape the happy-path fixture cannot produce.
        """
        portfolio = _held()
        unpriced = Order(
            order_id="78",
            symbol=SYMBOL,
            side=OrderSide.SELL,
            type=OrderType.MARKET,
            status=OrderStatus.FILLED,
            quantity=CLOSE_QTY,
            filled_quantity=CLOSE_QTY,
            filled_quote_quantity=None,
        )
        executor, _, _ = build(client=_resolving_client(unpriced), portfolio=portfolio)
        executor._pending[SYMBOL] = _close()

        await executor(candle())

        assert portfolio.ledger is None
        assert portfolio.free_quote == D("10000")
        # Still dropped -- the fill is confirmed, only its price is not.
        assert SYMBOL not in portfolio.positions

    @staticmethod
    def _unpriced_sold() -> Order:
        """A whole close fill the venue reported with NO quote total.

        FABRICATED: no capture holds an absent total (`M5k-093`), and `_sold()`
        always carries one, so the `Order` is built here directly.
        """
        return Order(
            order_id="78",
            symbol=SYMBOL,
            side=OrderSide.SELL,
            type=OrderType.MARKET,
            status=OrderStatus.FILLED,
            quantity=CLOSE_QTY,
            filled_quantity=CLOSE_QTY,
            filled_quote_quantity=None,
        )

    async def test_the_resolution_line_omits_an_absent_quote_total(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """**J: `quote_total` is OMITTED when the venue reported none, never null.**

        MUTATION: write `quote_total` unconditionally, as `_log_close_resolved`
        did until 3b-2a.

        EXPRESSIVE: the order IS on the line -- `status` and `executed_qty` are
        asserted -- so the branch that writes `quote_total` is reached, and only
        the figure's absence keeps the key off it. Read through `vars(record)`,
        because `getattr` on a key written as `None` and on one never written
        answers the same.
        """
        executor, _, _ = build(client=_resolving_client(self._unpriced_sold()), portfolio=_held())
        executor._pending[SYMBOL] = _close()

        with caplog.at_level(logging.CRITICAL):
            await executor(candle())

        resolved = _records(caplog, "close_record_resolved")
        assert len(resolved) == 1, "the close record was not resolved"
        fields = vars(resolved[0])
        assert fields.get("status") == "FILLED"
        assert fields.get("executed_qty") == CLOSE_QTY
        assert "quote_total" not in fields
        assert fields.get("outcome") == "filled_and_released"

    async def test_the_released_text_sends_the_operator_to_the_venue_for_an_absent_total(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """**PIN-10: the released text no longer promises a figure "below".**

        MUTATION: restore `_RESOLVED_RELEASED`'s old wording.

        It read *"enter the executed quantity and quote total below by hand"*,
        and on this line -- after J -- there is no quote total below. The text
        now points at the line's `quote_total` when present and at the order's
        own trades at the venue when not; both halves are asserted, and the old
        promise ABSENT, since a test asserting only presence would pass with the
        stale clause left beside the new one.
        """
        executor, _, _ = build(client=_resolving_client(self._unpriced_sold()), portfolio=_held())
        executor._pending[SYMBOL] = _close()

        with caplog.at_level(logging.CRITICAL):
            await executor(candle())

        resolved = _records(caplog, "close_record_resolved")
        assert len(resolved) == 1, "the close record was not resolved"
        resolution = vars(resolved[0]).get("resolution")
        assert isinstance(resolution, str)
        assert "from this line's quote_total when it is present" in resolution
        assert "from the order's own trades at the venue" in resolution
        assert "quote total below" not in resolution

    async def test_booking_deletes_through_close_position_not_a_third_path(self) -> None:
        """**There are TWO deletion paths and this commit adds none.**

        MUTATION: replace `close_position` with a bare `positions.pop`.

        A bare delete would remove the position and leave the ledger untouched,
        which is `_drop_position_unbooked`'s behaviour reached by a third route
        -- the "second source of truth" shape `CLAUDE.md` warns about. The
        assertion that separates them is the LEDGER, not the position: both
        routes end with the symbol gone.
        """
        portfolio = _held()
        executor, _, _ = build(client=_resolving_client(), portfolio=portfolio)
        executor._pending[SYMBOL] = _close()

        await executor(candle())

        assert SYMBOL not in portfolio.positions
        assert portfolio.ledger is not None, "a bare delete would leave this None"
        assert portfolio.ledger.realised_pnl == _EXPECTED_RESOLVED_PNL

    async def test_b1s_retention_and_wording_still_hold(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """**5e. Booking must not have unpicked B1.**

        MUTATION: release on the unconfirmed branch; or restore the manual-sell
        wording.

        Narrow on purpose -- B1's own suite pins these in detail. What this adds
        is that they survive ALONGSIDE booking, since B2 rewrote the resolution
        branch they depend on and the log they share.
        """
        client = _selling_client(
            sell_answer=ExchangeConnectionError("reset"),
            leg_answers={"SL": _leg("0"), "TP": _leg("0"), "CL": _sold()},
        )
        executor, _, _ = build(client=client, portfolio=_held())

        with caplog.at_level(logging.DEBUG, logger=_EXEC_LOGGER):
            await executor.dispatch(close_signal(), exit_assessment(), candle())

            # RETAINED, and the wording does not tell anyone to sell anything.
            assert SYMBOL in executor._pending
            (unconfirmed,) = _records(caplog, "close_sell_unconfirmed")
            assert "DO NOT SELL THIS BASE BY HAND" in unconfirmed.resolution
            assert "manually" not in unconfirmed.resolution

            await executor(candle())

        # SINGLE-SHOT: one bar, then gone, even though this one booked.
        assert executor._pending == {}

    async def test_a_position_with_no_cost_basis_is_released_not_booked(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """**THE FOURTH EXCLUSION. `M5i-001`, and it is the first test in the
        tree to reach ANY booking path with an absent cost basis.**

        MUTATION: delete the `entry_fill_price is None` check that
        `_bookability` asks; or invert it.

        **THE THREE OLD EXCLUSIONS ARE ASSERTED ABSENT, and that is what makes
        a pass mean anything.** `_bookability`'s total is `None` on four
        conditions and this fixture must fail exactly one of them. A test
        asserting only "nothing was booked" would pass whether the NEW check
        fired or one of the three old ones did -- and `M5i-038` measured that
        the existing suite cannot tell the difference at all, because no
        fixture in it reaches this path with `entry_fill_price is None`. So
        each old exclusion is pinned NOT to have fired:

        * the order is present and FILLED -- `record.status`;
        * the venue reported a total -- `record.quote_total`, to the last place;
        * the position is present AND the fill is whole -- `executed_qty`
          equals the quantity `_held` built, asserted against the fixture's own
          value rather than a literal.

        Only with all three provably absent does `filled_and_released` mean the
        cost-basis check bound.

        **WHAT WAS MEASURED BEFORE THE CHECK EXISTED.** This same input emitted
        `filled_and_booked` and *"DO NOT enter this trade by hand"*, then
        `close_position` raised and `close_book_failed` followed -- the ledger
        short a real trade, the operator told not to fix it. Both halves are
        asserted here: the label is right, and `close_book_failed` is now
        ABSENT because the raise is no longer reached.

        **STILL SCOPED TO PATH A, AND THE REASON CHANGED AT COMMIT 3b.** It read
        *"`_sell_and_book`'s own guard is untouched and is pinned to the project
        owner"*, which was true at 3a and is false now: B-i landed, and path B
        drops such a sell through `_sold_unbooked`. Corrected in place because
        it is a claim about the tree. What SURVIVES is the scoping itself and
        `M5i-035`'s reason for it -- the guard at `:1789` is STILL untouched and
        B-i sits AFTER it (`M5i-043`), because folding the condition into that
        guard routes a completed sell to `_go_naked`, whose CRITICAL instructs a
        second sale. Path B's own coverage is `TestAnUnbookableSellIsDropped`.
        """
        portfolio = _held(entry_fill=None)
        held_quantity = portfolio.positions[SYMBOL].quantity
        executor, _, _ = build(client=_resolving_client(), portfolio=portfolio)
        executor._pending[SYMBOL] = _close()

        with caplog.at_level(logging.CRITICAL):
            await executor(candle())

        (record,) = _records(caplog, "close_record_resolved")

        # THE THREE OLD EXCLUSIONS, EACH PINNED ABSENT.
        assert record.status == "FILLED"  # an order came back
        assert record.quote_total == D("1810.57726950")  # the venue priced it
        assert record.executed_qty == held_quantity  # present, and whole

        # ...so only the cost basis can explain the refusal.
        assert record.outcome == "filled_and_released"  # type: ignore[attr-defined]
        assert "NOTHING WAS BOOKED by this bot" in record.resolution  # type: ignore[attr-defined]
        assert "by hand" in record.resolution  # type: ignore[attr-defined]

        # NOT booked, and NOT half-booked: `close_position` is never reached,
        # so `free_quote` cannot carry the C12 residual either.
        assert portfolio.ledger is None
        assert portfolio.free_quote == D("10000")
        # Dropped, not retained -- the fill is confirmed, so the base is gone.
        assert SYMBOL not in portfolio.positions
        assert executor._pending == {}

        # THE RAISE IS NO LONGER REACHED. Before the check this input emitted
        # `close_book_failed` from `_book_resolved_close`'s except arm; a
        # refusal decided BEFORE the call emits nothing at all.
        assert _records(caplog, "close_book_failed") == []


class TestTheResolutionLineAgreesWithItself:
    """`outcome`, `resolution` and `message` say ONE thing. **`M5i-007`.**

    **THE MESSAGE WAS UNCONDITIONAL AND THE OTHER TWO WERE NOT**, so the
    headline described a design two commits old while the fields beside it
    described the current one. MEASURED in one record: `outcome` read
    `filled_and_booked` and `resolution` said *"DO NOT enter this trade by
    hand"* while the message said *"DROPPED UNBOOKED"* -- the two instructions
    an operator can act on, pointing opposite ways, in the same CRITICAL.

    **NOTHING IN `tests/` READ A LOG MESSAGE FROM THIS MODULE BEFORE THIS
    CLASS** (`M5i-015`): no `getMessage()`, no `.message`, no `caplog.text` in
    this file at all. So every format string in `executor.py` was unpinned by
    construction, and the mutation that swaps a message between branches killed
    ZERO tests -- it was not even expressible, since there was one string and no
    branch to swap it across.

    **`getMessage()` RATHER THAN `.message`**, per `test_live_engine.py`:
    `logging.Formatter.format` assigns `.message` while rendering, and a
    captured record has not been rendered. It is populated here only because
    `caplog`'s handler happens to format, which is the fragile path.

    **WHAT THIS CLASS DOES NOT PIN, said plainly because the line now looks
    trustworthy.** That the booked branch's claim is TRUE. It asserts the three
    fields AGREE; whether what they agree on happened is `M5h-371`, and Phase 1b
    MEASURED the booked `resolution` false when the position carries no
    `entry_fill_price`. Agreement is not correctness, and no test here reaches
    the ledger.
    """

    @pytest.mark.parametrize(
        (
            "answer",
            "make_portfolio",
            "outcome",
            "resolution_says",
            "resolution_lacks",
            "message_says",
            "message_lacks",
        ),
        [
            pytest.param(
                _sold(),
                _held,
                "filled_and_booked",
                "DO NOT enter this trade by hand",
                # `_RESOLVED_RELEASED`'s instruction and `_RESOLVED_BOOK_FAILED`'s
                # warning, both FALSE here: the ledger carries this trade and the
                # write completed. Each is verbatim from the sibling that states
                # it, so a constant swap makes it appear.
                ("That trade is NOT in the ledger", "HALF-APPLIED"),
                "the trade is BOOKED",
                # `M5i-007`: the headline said this on the branch that booked.
                # `M5i-011`: provenance nothing here can know.
                ("DROPPED", "restored"),
                id="booked",
            ),
            pytest.param(
                _sold(),
                # No position in memory -- the RESTART shape, where the cost
                # basis is unreconstructable and the fill is released unbooked.
                _no_portfolio,
                "filled_and_released",
                "enter it by hand: the executed quantity below",
                # `_RESOLVED_BOOKED`'s instruction inverts this branch's own --
                # an operator who reads it leaves a real trade out of the ledger
                # for ever. `STILL IN MEMORY` is `_RESOLVED_BOOK_FAILED`'s and is
                # false here: this branch DROPS the position.
                ("DO NOT enter this trade by hand", "STILL IN MEMORY"),
                "DROPPED UNBOOKED",
                ("restored",),
                id="released",
            ),
            pytest.param(
                OrderNotFoundError("Order does not exist."),
                _held,
                "unconfirmed_position_retained",
                # **`M5i-020`'s FIX, PINNED.** The string used to say "Nothing
                # was sold" one sentence after "BASE INVENTORY MAY STILL BE AT
                # THE VENUE" -- a certainty this branch does not hold, since it
                # is reached BOTH when the venue reported nothing filled AND
                # when the query raised and there is no answer at all. Without
                # this line the correction would ship unpinned: nothing in the
                # tree read that sentence.
                "whether anything was SOLD is exactly what is unknown",
                # **TWO PHRASES, TWO MUTATION CLASSES, and only the second
                # catches a constant swap.** "Nothing was sold" is carried by no
                # branch once the fix lands, so no swap can make it appear -- it
                # is the REVERT pin, and the only thing that fires if the fix is
                # backed out. "THE SELL FILLED" opens the other three constants
                # and is exactly the claim this branch may not make, so it
                # catches the swap. Keeping one would leave a class uncovered --
                # `M5i-101`.
                ("Nothing was sold", "THE SELL FILLED"),
                "the sell is UNCONFIRMED and the POSITION IS RETAINED",
                # `M5i-013`: nothing was DROPPED -- the position is retained.
                # `M5i-012`: the query RAISED, so there is no venue answer to
                # record, and the headline may not claim one.
                ("DROPPED", "restored", "the venue's"),
                id="retained",
            ),
            pytest.param(
                _sold(),
                _refusing,
                "filled_and_book_failed",
                "the write was ATTEMPTED, so the ledger may be HALF-APPLIED",
                # **DELIBERATELY THE SAME TWO `test_a_booking_that_failed_is_-
                # not_labelled_booked` ASSERTS, and that duplication is the
                # file's own convention**: the parametrised test pins the whole
                # mapping, the narrow test pins one branch. `The position is
                # released` is the clause `_RESOLVED_BOOK_FAILED`'s own comment
                # names as the reason it cannot reuse `_RESOLVED_RELEASED`.
                ("The position is released", "the ledger already carries it"),
                "BOOKING IT FAILED",
                # THE FOURTH CASE, and every phrase here is a claim it must not
                # make. `BOOKED`: the write failed, and "BOOKING" does not
                # contain it, so this bites. `DROPPED`/`released`: the position
                # SURVIVES -- `M5i-055`, which is why it cannot reuse
                # `_RESOLVED_RELEASED`. `restored`: `M5i-011`, as on every
                # branch.
                ("BOOKED", "DROPPED", "released", "restored"),
                id="book_failed",
            ),
        ],
    )
    async def test_the_message_agrees_with_the_outcome_on_every_branch(
        self,
        caplog: pytest.LogCaptureFixture,
        answer: Order | Exception,
        make_portfolio: Callable[[], Portfolio | None],
        outcome: str,
        resolution_says: str,
        resolution_lacks: tuple[str, ...],
        message_says: str,
        message_lacks: tuple[str, ...],
    ) -> None:
        """All FOUR branches, all three fields. **The agreement is the subject.**

        MUTATION: swap two of the four `_CloseResolutionText` constants at their
        selection sites; or restore the single unconditional message.

        **THE FOURTH CASE ARRIVED WITH OPTION 3, AND IT IS NOT A RELABELLING.**
        `book_failed` is the state `M5h-370`/W1 said nothing could distinguish:
        booking RAN and wrote nothing, where `released` means it never ran. Its
        portfolio is a `_RefusingPortfolio`, because no other fixture in the
        tree can reach a failed write -- `M5i-057`.

        **AND THE PORTFOLIO PARAMETER IS NOW A FACTORY, not a `held` flag.** A
        bool could express two portfolios and this needs three; a prebuilt
        `Portfolio` in the param list would be MUTABLE STATE SHARED BETWEEN
        PARAMETRISED ITEMS, constructed once at collection and written by
        whichever case ran first.

        Driven end to end through `await executor(candle())` rather than by
        calling the logger, because the claim is that the branch SELECTED is the
        one REPORTED -- a test calling `_log_close_resolved` directly would pass
        with the selection wired to anything.

        **THE TWO `_lacks` COLUMNS ARE THE LOAD-BEARING HALF**, and there are
        two of them since `M5i-020`: `message_lacks` carries three separate
        findings, and `resolution_lacks` was added when the retained branch's
        `resolution` was found asserting "Nothing was sold" on a path that
        cannot know it. A test asserting only what is present would pass with
        the false phrase sitting beside the true one, which is exactly the state
        this class was opened on.

        Every `resolution_lacks` phrase is VERBATIM from a sibling constant, so
        a swap at the selection site makes it appear. The one exception is
        declared where it sits: "Nothing was sold" is carried by no branch and
        pins the REVERT rather than a swap.
        """
        executor, _, _ = build(client=_resolving_client(answer), portfolio=make_portfolio())
        executor._pending[SYMBOL] = _close()

        with caplog.at_level(logging.CRITICAL):
            await executor(candle())

        (record,) = _records(caplog, "close_record_resolved")
        message = record.getMessage()

        assert record.outcome == outcome  # type: ignore[attr-defined]
        resolution = record.resolution  # type: ignore[attr-defined]
        assert resolution_says in resolution
        for phrase in resolution_lacks:
            assert phrase not in resolution, f"{phrase!r} survived in: {resolution!r}"
        assert message_says in message
        for phrase in message_lacks:
            assert phrase not in message, f"{phrase!r} survived in: {message!r}"

        # The symbol reached the headline: the message carries its own `%s` so
        # every branch takes the identical argument list, and a constant that
        # dropped the placeholder would leave it out silently.
        assert message.startswith(f"{SYMBOL}: ")

    async def test_a_booked_resolution_never_says_dropped_unbooked(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """**BOTH POLARITIES, and the absent half is the one that cost money.**

        MUTATION: restore the unconditional message.

        Narrower than the parametrised test above and kept separate on purpose.
        That one pins the whole mapping; this one pins the single sentence whose
        presence contradicts the instruction two fields away. An operator reading
        `DROPPED UNBOOKED` enters the trade by hand, and `resolution` on this
        branch says the ledger already carries it -- the double-entry counterpart
        of B1's double-sell, which is the failure `_log_close_resolved`'s own
        docstring says the booked branch was added to prevent.

        The three fields are asserted TOGETHER rather than the message alone,
        because the defect was never a wrong string in isolation: it was two
        fields agreeing and a third dissenting.
        """
        executor, _, _ = build(client=_resolving_client(), portfolio=_held())
        executor._pending[SYMBOL] = _close()

        with caplog.at_level(logging.CRITICAL):
            await executor(candle())

        (record,) = _records(caplog, "close_record_resolved")
        message = record.getMessage()

        # ABSENT: the sentence that sends an operator to do the bookkeeping.
        assert "DROPPED UNBOOKED" not in message
        assert "DROPPED" not in message
        # PRESENT: what the other two fields already say.
        assert "the trade is BOOKED" in message
        assert record.outcome == "filled_and_booked"  # type: ignore[attr-defined]
        assert "DO NOT enter this trade by hand" in record.resolution  # type: ignore[attr-defined]


# --------------------------------------------------------------------------
# The fee commit: settlement at Site A and Site B, and the retention tracker
# --------------------------------------------------------------------------
_BTC_FEE = Fee(amount=D("0.00000100"), asset="BTC")

#: The booking line's settlement fields: one set, shared with the driver's
#: `exit_booked` through `execution/booking_line.py`.
_SEVEN = ("order_id", "quantity", "fee", "fee_asset", "fills", "filled_at", "order_created_at")


def _two_fills() -> tuple[Trade, Trade]:
    """The sell's two fills: fees and times DIFFERENT, the later time apart from the candle's.

    FABRICATED fees `0.15000000` and `0.10000000` USDT -- every captured SELL fee
    is zero -- so a line logging one fill's fee, the earliest time or a fixed
    count fails. The quantities sum to `CLOSE_QTY`, so the settlement is complete.
    """
    first = sell_trade(
        quantity=D("0.3"),
        quote=D("30.75000000"),
        fee=Fee(amount=D("0.15000000"), asset="USDT"),
    ).model_copy(update={"filled_at": BAR + timedelta(seconds=3)})
    second = sell_trade(
        quantity=D("0.2"),
        quote=D("20.50000000"),
        fee=Fee(amount=D("0.10000000"), asset="USDT"),
        trade_id="2",
    ).model_copy(update={"filled_at": BAR + timedelta(seconds=9)})
    return first, second


def _settling_client(*answers: list[Trade] | Exception) -> FakeClient:
    """A close whose sell FILLS, whose settlement reads answer IN ORDER (the last
    repeats), and whose close id re-reads that same sell -- so Site B can pick a
    deferred close up on a later candle."""
    return _selling_client(
        trades_answers=list(answers),
        leg_answers={"SL": _leg("0"), "TP": _leg("0"), "CL": sell_fill()},
    )


def _bar(minute: int) -> Candle:
    return candle(close_time=BAR + timedelta(minutes=minute))


class TestSettlement:
    async def test_the_close_reads_its_fills_once_after_the_sell_and_books_net_of_the_fee(
        self,
    ) -> None:
        """Site A: one read, after the sell, at the settlement bound, and the fee subtracted.

        FABRICATED fee `0.25000000` USDT: every captured fee is zero. MUTATION:
        skip the read, bound it by the dispatch budget, or ignore the fee.
        """
        client = _settling_client([sell_trade(fee=Fee(amount=D("0.25000000"), asset="USDT"))])
        executor, _, portfolio = build(client=client, portfolio=_held())

        await executor.dispatch(close_signal(), exit_assessment(), candle())

        assert client.venue_calls == [*FULL_CLOSE, "get_my_trades"]
        assert client.settlements == [("777", 3.0, 1)]
        assert portfolio.ledger is not None
        assert portfolio.ledger.realised_pnl == D("2.00000000")  # 2.25 gross, less 0.25
        assert SYMBOL not in executor._pending

    @pytest.mark.parametrize(
        "answer",
        [
            [],
            [sell_trade(quantity=D("0.25"))],
            ExchangeConnectionError("timed out"),
        ],
        ids=["empty", "incomplete", "transport"],
    )
    async def test_every_settlement_failure_after_the_sell_defers(
        self, answer: list[Trade] | Exception, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Ruling 3: the sell SUCCEEDED, so nothing is dropped and nothing booked -- the record waits.

        FABRICATED answers. These replace P22's two drop-at-Site-A tests, which
        ruling 3 withdrew. MUTATION: drop unbooked, release the record, or book.

        **The `foreign_asset` row LEFT at R2**: a fee this ledger cannot
        subtract is terminal and is HELD, not deferred -- see
        `test_a_foreign_fee_at_the_sell_holds_and_does_not_defer`.
        """
        writer = RecordingWriter()
        executor, _, portfolio = build(
            client=_settling_client(answer), portfolio=_held(), persist=writer
        )

        with caplog.at_level(logging.DEBUG, logger=_EXEC_LOGGER):
            await executor.dispatch(close_signal(), exit_assessment(), candle())

        assert executor._pending[SYMBOL].kind == "close"
        assert SYMBOL in writer.symbols()  # still on disk: no removal write
        assert portfolio.positions[SYMBOL].protection is ProtectionState.UNKNOWN
        assert portfolio.ledger is None
        assert len(_records(caplog, "close_settlement_deferred")) == 1
        assert _records(caplog, "close_sold_unbooked") == []

    async def test_a_deferred_close_is_booked_by_the_next_bar(self) -> None:
        """Site A defers; Site B re-reads the sell by its derived id, settles and books it.

        MUTATION: release the record at the deferral -- nothing is left to resolve.
        """
        client = _settling_client([], [sell_trade()])
        executor, _, portfolio = build(client=client, portfolio=_held())

        await executor.dispatch(close_signal(), exit_assessment(), candle())
        await executor(_bar(1))

        assert client.venue_calls[-3:] == ["get_my_trades", "get_order", "get_my_trades"]
        assert portfolio.ledger is not None
        assert portfolio.ledger.realised_pnl == D("2.25000000")
        assert SYMBOL not in executor._pending

    async def test_a_resolved_close_books_net_of_its_fee(self) -> None:
        """Site B, FABRICATED fee `0.25000000` USDT. MUTATION: book it gross."""
        client = _settling_client([sell_trade(fee=Fee(amount=D("0.25000000"), asset="USDT"))])
        executor, _, portfolio = build(client=client, portfolio=_held())
        executor._pending[SYMBOL] = _close()

        await executor(candle())

        assert portfolio.ledger is not None
        assert portfolio.ledger.realised_pnl == D("2.00000000")

    async def test_the_close_booked_line_carries_all_seven_settlement_fields(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Site A's `close_booked`: the seven fields every booking line now shares.

        Answers `M5k-052` at Site A. TWO fills whose fees and times differ, the
        later time apart from the candle's, so a line logging one fill's fee,
        the earliest time, the candle time or a fixed count fails. FABRICATED
        fees. MUTATION: drop any of the seven fields, or take `min` of the times.

        **`order_created_at` FLIPPED FROM ABSENT TO PRESENT, BY RULING R1.** It
        was pinned absent as found (`M5k-066`); this line now carries the
        MARKET sell's own record time. The sell is given one, FABRICATED at
        `BAR+1s`, because the default response carries none -- the MARKET
        payload's shape is documented here, never measured. Read through
        `vars()`, so an absent field fails the assertion rather than raising
        `AttributeError` (R3).
        """
        first, second = _two_fills()
        sold = sell_fill().model_copy(update={"created_at": BAR + timedelta(seconds=1)})
        client = _selling_client(trades_answers=[[first, second]], sell_answer=sold)
        executor, _, portfolio = build(client=client, portfolio=_held())

        with caplog.at_level(logging.DEBUG, logger=_EXEC_LOGGER):
            await executor.dispatch(close_signal(), exit_assessment(), candle())

        assert portfolio.ledger is not None
        assert portfolio.ledger.realised_pnl == D("2.00000000")  # 2.25 gross, less 0.25
        booked = _records(caplog, "close_booked")
        assert len(booked) == 1
        line = vars(booked[0])
        assert {key: line.get(key) for key in _SEVEN} == {
            "order_id": "777",
            "quantity": D("0.5"),
            "fee": D("0.25000000"),
            "fee_asset": "USDT",
            "fills": 2,
            "filled_at": (BAR + timedelta(seconds=9)).isoformat(),
            "order_created_at": (BAR + timedelta(seconds=1)).isoformat(),
        }
        assert str(line.get("fee")) == "0.25000000"  # the exponent, which `==` cannot see

    async def test_the_resolved_close_booked_line_carries_all_seven_settlement_fields(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Site B's `close_booked` (CRITICAL): the SAME seven fields as Site A's.

        Answers `M5k-052` at Site B. FABRICATED fees, the same two fills as
        Site A's test. MUTATION: drop any of the seven fields, or hand
        `_book_resolved_close` the fee alone again.

        **FOUR FIELDS FLIPPED FROM ABSENT TO PRESENT, BY RULING R1.** This line
        carried fee and fee_asset only (`M5k-066`), because `_resolve_close`
        handed `_book_resolved_close` the settlement's fee and nothing else. It
        now takes the settlement and the re-read sell's record time, whose
        value is FABRICATED at `BAR+1s` on the re-read. Read through `vars()`
        (R3).
        """
        first, second = _two_fills()
        resold = sell_fill().model_copy(update={"created_at": BAR + timedelta(seconds=1)})
        client = _selling_client(
            trades_answers=[[first, second]],
            leg_answers={"SL": _leg("0"), "TP": _leg("0"), "CL": resold},
        )
        executor, _, _ = build(client=client, portfolio=_held())
        executor._pending[SYMBOL] = _close()

        with caplog.at_level(logging.DEBUG, logger=_EXEC_LOGGER):
            await executor(candle())

        booked = _records(caplog, "close_booked")
        assert len(booked) == 1
        assert booked[0].levelno == logging.CRITICAL
        line = vars(booked[0])
        assert {key: line.get(key) for key in _SEVEN} == {
            "order_id": "777",
            "quantity": D("0.5"),
            "fee": D("0.25000000"),
            "fee_asset": "USDT",
            "fills": 2,
            "filled_at": (BAR + timedelta(seconds=9)).isoformat(),
            "order_created_at": (BAR + timedelta(seconds=1)).isoformat(),
        }
        assert str(line.get("fee")) == "0.25000000"

    @pytest.mark.parametrize(
        "answer",
        [ExchangeConnectionError("timed out"), [], [sell_trade(quantity=D("0.25"))]],
        ids=["transport", "empty", "incomplete"],
    )
    async def test_a_resolved_close_keeps_its_record_on_a_settlement_it_cannot_read(
        self, answer: list[Trade] | Exception, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Rulings 1 and 2 (Variant L): kept under the tracker at WARNING, not dropped.

        MUTATION: drop at CRITICAL as R-j literally read, or release the record.
        """
        executor, _, portfolio = build(client=_settling_client(answer), portfolio=_held())
        executor._pending[SYMBOL] = _close()

        with caplog.at_level(logging.DEBUG, logger=_EXEC_LOGGER):
            await executor(candle())

        assert SYMBOL in executor._pending
        assert SYMBOL in portfolio.positions
        assert len(_records(caplog, "close_settlement_deferred")) == 1
        assert _records(caplog, "close_record_resolved") == []

    async def test_a_resolved_close_with_a_foreign_fee_holds(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Site B, R2: waiting cannot change a fee's asset, so it is HELD -- not retried, not dropped.

        FABRICATED BTC fee. This read `..._drops_as_fee_unresolvable` until R2,
        which removed that outcome. Starts ACTIVE -- P34's probe measured this
        fixture reaching the hold as `'active'` -- so PIN-5's `UNKNOWN` write is
        observable. MUTATION: restore the drop, retain it under the tracker, or
        delete the hold's protection write.
        """
        executor, _, portfolio = build(
            client=_settling_client([sell_trade(fee=_BTC_FEE)]),
            portfolio=_held(protection=ProtectionState.ACTIVE),
        )
        record = _close()
        executor._pending[SYMBOL] = record
        position = portfolio.positions[SYMBOL]
        assert position.protection is ProtectionState.ACTIVE

        with caplog.at_level(logging.DEBUG, logger=_EXEC_LOGGER):
            await executor(candle())

        assert _records(caplog, "close_record_resolved") == []
        assert executor._pending.get(SYMBOL) is record
        assert portfolio.positions.get(SYMBOL) is position
        assert position.protection is ProtectionState.UNKNOWN
        assert position.settlement_hold is True
        held = _records(caplog, "exit_settlement_held")
        assert [(r.levelno, vars(r).get("site")) for r in held] == [
            (logging.CRITICAL, "resolution")
        ]
        assert vars(held[0]).get("cause") == "foreign_fee_asset"
        assert SYMBOL not in executor._settlement_deferrals
        assert portfolio.ledger is None

    async def test_a_foreign_fee_at_the_sell_holds_and_does_not_defer(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Site A, R2: the sell FILLED and its fee is BTC -- HELD, not deferred, and said once.

        FABRICATED BTC fee. Starts ACTIVE -- P34's probe measured this fixture
        reaching the hold as `'active'` -- so PIN-5's `UNKNOWN` write is
        observable. The record stays in memory AND on disk: it is what refuses a
        second sell. MUTATION: defer instead of holding, or delete the hold's
        protection write.
        """
        writer = RecordingWriter()
        executor, _, portfolio = build(
            client=_settling_client([sell_trade(fee=_BTC_FEE)]),
            portfolio=_held(protection=ProtectionState.ACTIVE),
            persist=writer,
        )
        position = portfolio.positions[SYMBOL]
        assert position.protection is ProtectionState.ACTIVE

        with caplog.at_level(logging.DEBUG, logger=_EXEC_LOGGER):
            await executor.dispatch(close_signal(), exit_assessment(), candle())

        assert getattr(executor._pending.get(SYMBOL), "kind", None) == "close"
        assert SYMBOL in writer.symbols()
        assert portfolio.positions.get(SYMBOL) is position
        assert position.protection is ProtectionState.UNKNOWN
        assert position.settlement_hold is True
        assert _records(caplog, "close_settlement_deferred") == []
        assert _records(caplog, "dispatch_refused") == []
        held = _records(caplog, "exit_settlement_held")
        assert [(r.levelno, vars(r).get("site")) for r in held] == [(logging.CRITICAL, "sell")]
        assert vars(held[0]).get("cause") == "foreign_fee_asset"
        assert vars(held[0]).get("fees") == "0.00000100 BTC"
        assert SYMBOL not in executor._settlement_deferrals
        assert portfolio.ledger is None

    async def test_a_held_close_makes_no_venue_call_on_any_later_bar(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """R2: a held close is skipped BEFORE `get_order`, on every bar, and says nothing more.

        Nine bars, past `_SETTLEMENT_RETRY_BARS` -- a held close must never
        time out into the unbooked drop. MUTATION: delete `__call__`'s skip.
        """
        client = _settling_client([sell_trade(fee=_BTC_FEE)])
        executor, _, portfolio = build(client=client, portfolio=_held())

        with caplog.at_level(logging.DEBUG, logger=_EXEC_LOGGER):
            await executor.dispatch(close_signal(), exit_assessment(), candle())
            calls = list(client.venue_calls)
            for minute in range(1, 10):
                await executor(_bar(minute))

        assert client.venue_calls == calls
        assert SYMBOL in executor._pending
        assert SYMBOL in portfolio.positions
        assert len(_records(caplog, "exit_settlement_held")) == 1
        assert _records(caplog, "close_record_resolved") == []

    async def test_a_hold_after_deferrals_is_never_dropped_and_leaves_the_tracker(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Deferred twice, then HELD at Site B on bar 2: out of the count, never dropped.

        The settlement answers transport at the sell and on bar 1, BTC on bar
        2, and transport for ever after -- so a held record that were still
        resolved would keep deferring, and one still counted would time out.
        Bars 3 to 10 run past `_SETTLEMENT_RETRY_BARS`. FABRICATED answers.
        MUTATION: delete the tracker pop, delete `__call__`'s skip, or restore
        the drop.
        """
        timeout = ExchangeConnectionError("timed out")
        client = _settling_client(timeout, timeout, [sell_trade(fee=_BTC_FEE)], timeout)
        executor, _, portfolio = build(client=client, portfolio=_held())
        position = portfolio.positions[SYMBOL]

        with caplog.at_level(logging.DEBUG, logger=_EXEC_LOGGER):
            await executor.dispatch(close_signal(), exit_assessment(), candle())
            await executor(_bar(1))
            await executor(_bar(2))
            # Read off the object, never re-looked-up: a KeyError is a crash.
            assert position.settlement_hold is True
            calls = list(client.venue_calls)
            for minute in range(3, 11):
                await executor(_bar(minute))

        assert client.venue_calls == calls
        assert SYMBOL in executor._pending
        assert SYMBOL in portfolio.positions
        assert SYMBOL not in executor._settlement_deferrals
        assert _records(caplog, "close_record_resolved") == []
        assert len(_records(caplog, "exit_settlement_held")) == 1

    @pytest.mark.parametrize(
        "failure", [ExchangeConnectionError("timed out"), []], ids=["transport", "empty"]
    )
    async def test_a_deferred_close_is_kept_through_bar_five_and_dropped_at_bar_six(
        self, failure: list[Trade] | Exception, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Ruling 1: five bars of the symbol's OWN candles, then CRITICAL `settlement_timeout`.

        Bar 1 is Site A's deferral; bars 2 to 6 are resolution attempts. The
        `empty` row is Variant L's retention, bounded by the same count.
        MUTATION: N of 4 or 6, `>` for `>=`, or no bound at all.
        """
        client = _settling_client([], failure)
        executor, _, portfolio = build(client=client, portfolio=_held())

        with caplog.at_level(logging.DEBUG, logger=_EXEC_LOGGER):
            await executor.dispatch(close_signal(), exit_assessment(), candle())
            for bar in range(2, 6):
                await executor(_bar(bar - 1))
                assert SYMBOL in executor._pending, f"dropped early, at bar {bar}"
            assert _records(caplog, "close_record_resolved") == []
            await executor(_bar(5))

        (record,) = _records(caplog, "close_record_resolved")
        assert record.levelno == logging.CRITICAL
        assert record.outcome == "settlement_timeout"  # type: ignore[attr-defined]
        assert "COULD NOT BE SETTLED" in record.resolution  # type: ignore[attr-defined]
        assert SYMBOL not in executor._pending
        assert SYMBOL not in portfolio.positions
        assert portfolio.ledger is None

    async def test_a_booking_on_bar_three_clears_the_count(self) -> None:
        """The count leaves with the record, so a LATER close on the symbol starts from zero.

        MUTATION: keep the count after booking -- the second close then drops two
        bars early, at minute 12 instead of minute 14.
        """
        timeout = ExchangeConnectionError("timed out")
        client = _settling_client([], timeout, [sell_trade()], [], timeout)
        executor, _, portfolio = build(client=client, portfolio=_held())

        await executor.dispatch(close_signal(), exit_assessment(), candle())
        await executor(_bar(1))
        await executor(_bar(2))
        assert SYMBOL not in portfolio.positions  # booked on bar 3

        portfolio.positions[SYMBOL] = _held().positions[SYMBOL]
        await executor.dispatch(close_signal(), exit_assessment(), _bar(9))
        for minute in range(10, 14):
            await executor(_bar(minute))
            assert SYMBOL in executor._pending, f"dropped early, at minute {minute}"
        await executor(_bar(14))
        assert SYMBOL not in executor._pending

    async def test_another_symbols_candles_do_not_advance_the_count(self) -> None:
        """Counted on the symbol's OWN candles. MUTATION: count every call -- the
        record then drops on the fifth ETHUSDT candle."""
        executor, _, _ = build(
            client=_settling_client([], ExchangeConnectionError("timed out")), portfolio=_held()
        )

        await executor.dispatch(close_signal(), exit_assessment(), candle())
        eth = _bar(1).model_copy(update={"symbol": "ETHUSDT"})
        for _ in range(10):
            await executor(eth)
        assert SYMBOL in executor._pending

        for minute in range(2, 6):
            await executor(_bar(minute))
        assert SYMBOL in executor._pending
        await executor(_bar(6))
        assert SYMBOL not in executor._pending

    async def test_the_settlement_timeout_text_no_longer_promises_a_total_below(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """**PIN-10, the timeout text.** MUTATION: restore its old wording.

        It read *"enter the executed quantity, the quote total below and the
        commission the venue reports for it by hand"*. The text now points at
        the line's `quote_total` when present and at the order's own trades at
        the venue when not, and still names the commission. Driven to the
        timeout the way the bar-six test drives it: bar 1 defers, bars 2 to 5
        retain, bar 6 drops.
        """
        client = _settling_client([], ExchangeConnectionError("timed out"))
        executor, _, _ = build(client=client, portfolio=_held())

        with caplog.at_level(logging.DEBUG, logger=_EXEC_LOGGER):
            await executor.dispatch(close_signal(), exit_assessment(), candle())
            for minute in range(1, 6):
                await executor(_bar(minute))

        resolved = _records(caplog, "close_record_resolved")
        assert len(resolved) == 1, "the deferred close did not time out"
        fields = vars(resolved[0])
        assert fields.get("outcome") == "settlement_timeout"
        resolution = fields.get("resolution")
        assert isinstance(resolution, str)
        assert "from this line's quote_total when it is present" in resolution
        assert "from the order's own trades at the venue" in resolution
        assert "commission the venue reports" in resolution
        assert "the quote total below" not in resolution


class TestTheCloseGuard:
    """Ruling B: a CLOSE for a HELD position is refused, before any read."""

    async def test_a_close_on_a_reconciler_held_position_is_refused_before_any_read(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """The reconciler-held case: a held position and NO close record.

        `close_pending` cannot see it -- there is no record -- so only ruling
        B's guard stands between this CLOSE and `_plan_close`, whose quiet legs
        here plan SELL. MUTATION: delete the held guard.
        """
        client = _selling_client()
        executor, _, portfolio = build(client=client, portfolio=_held())
        portfolio.positions[SYMBOL].hold_settlement()

        with caplog.at_level(logging.DEBUG, logger=_EXEC_LOGGER):
            await executor.dispatch(close_signal(), exit_assessment(), candle())

        assert client.venue_calls == []
        assert client.sold == []
        assert [r.reason for r in _records(caplog, "dispatch_refused")] == ["close_settlement_held"]
        assert SYMBOL in portfolio.positions

    async def test_a_close_on_an_executor_held_position_is_refused_once_as_close_pending(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """The executor-held case holds a close record TOO: ONE refusal, `close_pending`.

        The guard ORDER is the architect's: `close_pending` first leaves the
        older guard unchanged and names the record. MUTATION: put the held
        guard first -- the reason then reads `close_settlement_held`.
        """
        client = _settling_client([sell_trade(fee=_BTC_FEE)])
        executor, _, _ = build(client=client, portfolio=_held())
        await executor.dispatch(close_signal(), exit_assessment(), candle())
        assert len(client.sold) == 1

        with caplog.at_level(logging.DEBUG, logger=_EXEC_LOGGER):
            await executor.dispatch(close_signal(), exit_assessment(), _bar(1))

        assert [r.reason for r in _records(caplog, "dispatch_refused")] == ["close_pending"]
        assert len(client.sold) == 1
