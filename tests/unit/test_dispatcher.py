"""Tests for the ``Dispatcher`` Protocol that replaced the unused abstract ``OrderExecutor``.

The owner's R-U (resolving U6): the abstract ``OrderExecutor`` in ``core/interfaces.py``
declared ``execute(request: OrderRequest) -> Order`` and had no implementer and no user
(``M5m-124``). It is replaced by a Protocol declaring the two entry points the live
executor really has, ``dispatch(signal, assessment, candle)`` and ``__call__(candle)``,
and ``_build_signal_handler`` takes one.
"""

from __future__ import annotations

import inspect
import logging
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from trading_bot.core import interfaces
from trading_bot.core.enums import SignalAction
from trading_bot.core.interfaces import Dispatcher
from trading_bot.core.models import Candle, Signal
from trading_bot.core.portfolio import Portfolio
from trading_bot.engine.modes import _COLLABORATOR_EXECUTOR, _build_signal_handler
from trading_bot.execution.executor import OrderExecutor

_T0 = datetime(2024, 1, 1, tzinfo=timezone.utc)


class _Stub:
    """A dispatcher that is not the live class: it records what it is handed."""

    def __init__(self) -> None:
        self.dispatched: list[tuple[object, object, object]] = []
        self.candles: list[Candle] = []

    async def dispatch(self, signal: Signal, assessment: object, candle: Candle) -> None:
        self.dispatched.append((signal, assessment, candle))

    async def __call__(self, candle: Candle) -> None:
        self.candles.append(candle)


class _OnlyDispatch:
    async def dispatch(self, signal: Signal, assessment: object, candle: Candle) -> None:
        return None


class _OnlyCall:
    async def __call__(self, candle: Candle) -> None:
        return None


class _TheDeadExecute:
    """The shape of the abstract class this replaced: it has neither live entry point."""

    async def execute(self, request: object) -> object:
        return None


class _Raises(_Stub):
    async def dispatch(self, signal: Signal, assessment: object, candle: Candle) -> None:
        raise RuntimeError("the dispatcher failed")


class _Risk:
    def __init__(self, assessment: object) -> None:
        self.assessment = assessment
        self.seen: list[tuple[Signal, Portfolio]] = []

    def evaluate(self, signal: Signal, *, portfolio: Portfolio) -> object:
        self.seen.append((signal, portfolio))
        return self.assessment


class _Recorder:
    def __init__(self) -> None:
        self.recorded: list[tuple[Signal, object]] = []

    async def record(self, signal: Signal, assessment: object) -> None:
        self.recorded.append((signal, assessment))


def _signal() -> Signal:
    return Signal(
        symbol="BTCUSDT",
        action=SignalAction.BUY,
        timestamp=_T0 + timedelta(minutes=1) - timedelta(milliseconds=1),
        price=Decimal("100"),
        reason="test",
    )


def _candle() -> Candle:
    return Candle(
        symbol="BTCUSDT",
        timeframe="1m",
        open_time=_T0,
        close_time=_T0 + timedelta(minutes=1) - timedelta(milliseconds=1),
        open=Decimal("100"),
        high=Decimal("101"),
        low=Decimal("99"),
        close=Decimal("100"),
        volume=Decimal("1"),
    )


class TestTheProtocolReplacesTheAbstractClass:
    def test_the_abstract_order_executor_is_gone_from_the_interfaces(self) -> None:
        assert not hasattr(interfaces, "OrderExecutor")

    def test_the_two_entry_points_are_coroutines_with_the_live_parameter_names(self) -> None:
        assert inspect.iscoroutinefunction(Dispatcher.dispatch)
        assert inspect.iscoroutinefunction(Dispatcher.__call__)
        assert list(inspect.signature(Dispatcher.dispatch).parameters) == [
            "self",
            "signal",
            "assessment",
            "candle",
        ]
        assert list(inspect.signature(Dispatcher.__call__).parameters) == ["self", "candle"]

    def test_the_live_executor_has_the_same_two_signatures(self) -> None:
        """A drift in a parameter NAME on either side would break a keyword caller silently
        in a duck-typed double, so the names are compared, not only the members."""
        for member in ("dispatch", "__call__"):
            assert list(inspect.signature(getattr(OrderExecutor, member)).parameters) == list(
                inspect.signature(getattr(Dispatcher, member)).parameters
            )
            assert inspect.iscoroutinefunction(getattr(OrderExecutor, member))

    def test_the_live_executor_class_satisfies_it_without_subclassing_it(self) -> None:
        assert issubclass(OrderExecutor, Dispatcher)
        assert Dispatcher not in OrderExecutor.__mro__


class TestWhatSatisfiesIt:
    def test_a_stub_with_both_members_does(self) -> None:
        assert isinstance(_Stub(), Dispatcher)

    def test_a_class_with_only_dispatch_does_not(self) -> None:
        assert not isinstance(_OnlyDispatch(), Dispatcher)

    def test_a_class_with_only_call_does_not(self) -> None:
        assert not isinstance(_OnlyCall(), Dispatcher)

    def test_a_class_with_only_the_dead_execute_does_not(self) -> None:
        assert not isinstance(_TheDeadExecute(), Dispatcher)


class TestTheSignalHandlerTakesAnyDispatcher:
    """``_build_signal_handler`` is typed ``Dispatcher | None``; these drive it with a stub."""

    async def test_the_exact_objects_reach_the_dispatcher(self) -> None:
        assessment = object()
        stub, recorder, risk = _Stub(), _Recorder(), _Risk(assessment)
        portfolio = Portfolio()
        handle = _build_signal_handler(
            risk=risk,
            intent_logger=recorder,
            portfolio=portfolio,
            pairs={},
            executor=stub,
        )
        signal, candle = _signal(), _candle()
        await handle(signal, candle)
        assert len(risk.seen) == 1
        assert risk.seen[0][0] is signal
        assert risk.seen[0][1] is portfolio
        assert len(stub.dispatched) == 1
        assert stub.dispatched[0][0] is signal
        assert stub.dispatched[0][1] is assessment
        assert stub.dispatched[0][2] is candle
        assert stub.candles == []

    async def test_the_decision_is_recorded_before_it_is_dispatched(self) -> None:
        order: list[str] = []
        assessment = object()

        class _Logger(_Recorder):
            async def record(self, signal: Signal, assessment: object) -> None:
                order.append("record")

        class _Ordered(_Stub):
            async def dispatch(self, signal: Signal, assessment: object, candle: Candle) -> None:
                order.append("dispatch")

        handle = _build_signal_handler(
            risk=_Risk(assessment),
            intent_logger=_Logger(),
            portfolio=Portfolio(),
            pairs={},
            executor=_Ordered(),
        )
        await handle(_signal(), _candle())
        assert order == ["record", "dispatch"]

    async def test_a_raising_dispatcher_cannot_escape_the_handler(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        recorder = _Recorder()
        handle = _build_signal_handler(
            risk=_Risk(object()),
            intent_logger=recorder,
            portfolio=Portfolio(),
            pairs={},
            executor=_Raises(),
        )
        with caplog.at_level(logging.ERROR):
            await handle(_signal(), _candle())
        assert len(recorder.recorded) == 1
        failures = [r for r in caplog.records if vars(r).get("event") == "collaborator_failed"]
        assert len(failures) == 1
        assert vars(failures[0]).get("collaborator") == _COLLABORATOR_EXECUTOR

    async def test_without_a_dispatcher_the_decision_is_still_recorded(self) -> None:
        recorder = _Recorder()
        handle = _build_signal_handler(
            risk=_Risk(object()),
            intent_logger=recorder,
            portfolio=Portfolio(),
            pairs={},
        )
        await handle(_signal(), _candle())
        assert len(recorder.recorded) == 1
