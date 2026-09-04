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
    ExchangeConnectionError,
    FilterRejectedError,
    SymbolInfoNotPrimedError,
)
from trading_bot.core.models import (
    Candle,
    Order,
    OrderList,
    OtocoOrderListRequest,
    OtoOrderListRequest,
    Position,
    ProtectiveLevels,
    Signal,
)
from trading_bot.core.portfolio import Portfolio
from trading_bot.execution.dispatch_budget import DispatchBudget
from trading_bot.execution.executor import OrderExecutor, PendingClose, PendingPlacement
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
    ) -> None:
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
        """
        client = FakeClient(leg_answers={"SL": _leg("0"), "TP": _leg("0")})
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

    **NOTHING IN ``src/`` CONSTRUCTS A ``PendingClose``** -- the dispatch path
    that would is Q-C section 4b's, and the executor still refuses ``CLOSE``.
    These tests reach the shape through ``restored_pending``, which is the only
    door into ``_pending`` that does not go through dispatch.
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
        """
        executor, client, _ = build()
        executor._pending[SYMBOL] = _close()

        with caplog.at_level(logging.ERROR):
            await executor(candle())

        assert _records(caplog, "collaborator_failed") == []
        assert client.venue_calls == []
        assert executor._pending[SYMBOL] == _close()

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
            restored_pending=(_close(),),
        )

        assert executor._pending == {SYMBOL: _close()}


# --------------------------------------------------------------------------
# Q-C section 4b's READ half -- plan, report, refuse
# --------------------------------------------------------------------------
CLOSE_QTY = D("0.5")


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


def _held(*, stop: str | None = "95", target: str | None = "110") -> Portfolio:
    """A portfolio holding the position `close_signal` would close.

    `build()`'s default portfolio holds NOTHING, so a close against it refuses
    at `close_no_position` and makes zero reads -- which cannot express any row
    of the decision table. This is the fixture that can.
    """
    return Portfolio(
        free_quote=D("10000"),
        positions={
            SYMBOL: Position(
                symbol=SYMBOL,
                side=PositionSide.LONG,
                quantity=CLOSE_QTY,
                entry_price=D("100"),
                entry_bar_time=BAR,
                protection=ProtectionState.UNKNOWN,
                order_list_id="tb1-BTCUSDT-1714564800000-0-L",
                stop_loss=D(stop) if stop is not None else None,
                take_profit=D(target) if target is not None else None,
            )
        },
    )


def _plan_records(caplog: pytest.LogCaptureFixture) -> list[logging.LogRecord]:
    return _records(caplog, "close_planned")


class TestTheClosePlan:
    """The read half runs, reports and refuses. NOTHING IRREVERSIBLE HAPPENS."""

    async def test_no_leg_executed_plans_a_sell_and_refuses_it(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Section 4b row one, and the reason says the sell is RESERVED.

        MUTATION: return `CloseAction.SELL`'s reason for every verdict.

        The refusal reason is what an operator acts on: a reserved sell is work
        waiting on the next commit, where a halt is a state nobody may sell
        against. Asserting the specific string is what separates them.
        """
        client = FakeClient(leg_answers={"SL": _leg("0"), "TP": _leg("0")})
        executor, _, _ = build(client=client, portfolio=_held())

        with caplog.at_level(logging.DEBUG, logger=_EXEC_LOGGER):
            await executor.dispatch(close_signal(), exit_assessment(), candle())

        plans = _plan_records(caplog)
        assert len(plans) == 1
        assert plans[0].decision == "sell"  # type: ignore[attr-defined]
        refusals = _records(caplog, "dispatch_refused")
        assert refusals[0].reason == "close_sell_reserved"  # type: ignore[attr-defined]

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
        """
        client = FakeClient(leg_answers={"SL": _leg("0"), "TP": _leg("0")})
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
        client = FakeClient(leg_answers={"SL": _leg("0")})
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
        client = FakeClient(leg_answers={"SL": _leg("0"), "TP": _leg("0")})
        executor, _, _ = build(client=client, portfolio=_held())

        await executor.dispatch(close_signal(), exit_assessment(), candle())

        assert client.venue_calls == ["get_order", "get_order"]
        assert client.otoco == [] and client.oto == []

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
