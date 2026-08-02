"""Tests for the composition root -- boot, teardown, and the observable stream.

Hermetic: no network and no real time. Both leaf adapters are injected --
``client`` is a scripted :class:`FakeRootClient` and ``stream`` a
:class:`FakeStream`-- so the boot path under test is byte-for-byte the one
production takes. Injecting a whole *provider* would skip the step that wires
the provider to the client, and that step is exactly what the ownership
behaviour depends on.

The ten refusal stages are driven through the **real** ``RiskManager.evaluate``
rather than hand-built assessments, and that stays the point of the test even
now that ``evaluate`` reports the stage itself. A hand-built assessment asserts
only that pydantic stored what it was handed; making ``evaluate`` actually take
each branch is what pins the label to the code path. Its fixtures are borrowed
from ``test_risk_manager`` for the same reason -- they are the setups already
proven to reach those branches.
"""

from __future__ import annotations

import logging
from dataclasses import FrozenInstanceError
from decimal import Decimal
from typing import TYPE_CHECKING, Any

import pytest

from tests.unit.test_live_engine import FakeMarketDataProvider, ScriptedStrategy
from tests.unit.test_live_engine import candle as engine_candle
from tests.unit.test_risk_manager import (
    NOW,
    SYMBOL,
    TIMEFRAME,
    FakeProvider,
    build_manager,
    buy,
    candle,
    long_position,
    multi_pairs,
    ohlcv,
    risk_config,
    symbol_info,
)
from trading_bot.config.models import StopLossConfig, TakeProfitConfig
from trading_bot.core.enums import (
    OrderSide,
    PositionSizingMethod,
    RefusalStage,
    RiskRule,
    SignalAction,
    StopType,
)
from trading_bot.core.exceptions import (
    ConfigError,
    ExchangeAPIError,
    StrategyNotFoundError,
    TradingBotError,
)
from trading_bot.core.interfaces import (
    CandleHandler,
    ExchangeClient,
    MarketDataStream,
)
from trading_bot.core.models import (
    Balance,
    Candle,
    Order,
    OrderRequest,
    Signal,
    SymbolInfo,
    Ticker,
)
from trading_bot.core.portfolio import Portfolio
from trading_bot.engine.live_engine import TradingEngine
from trading_bot.engine.modes import (
    IntentLogger,
    LiveSystem,
    _build_signal_handler,
    _pair_timeframes,
    _seed_portfolio,
    live_system,
)
from trading_bot.risk.manager import PairContext, RiskAssessment, RiskManager
from trading_bot.utils.logger import surplus_fields

if TYPE_CHECKING:  # pragma: no cover - typing only
    from collections.abc import Mapping
    from pathlib import Path

D = Decimal

_KEY = (SYMBOL, TIMEFRAME)

#: The only logger whose records these tests own. Other collaborators log into
#: the same caplog buffer, so records are always selected by name.
_MODES_LOGGER = "trading_bot.engine.modes"


# --------------------------------------------------------------------------
# Scripted fakes
# --------------------------------------------------------------------------
class FakeRootClient(ExchangeClient):
    """Serves the two boot calls -- symbol info and balances -- and counts closes."""

    def __init__(
        self,
        *,
        balances: list[Balance] | None = None,
        unknown_symbols: frozenset[str] = frozenset(),
        journal: list[str] | None = None,
        balances_error: Exception | None = None,
    ) -> None:
        self._balances = (
            balances
            if balances is not None
            else [Balance(asset="USDT", free=D("5000"), locked=D("0"))]
        )
        self._unknown = unknown_symbols
        self._journal = journal if journal is not None else []
        self._balances_error = balances_error
        self.symbol_info_calls: list[str] = []
        self.close_calls = 0

    async def get_symbol_info(self, symbol: str) -> SymbolInfo:
        self.symbol_info_calls.append(symbol)
        self._journal.append(f"symbol_info:{symbol}")
        if symbol in self._unknown:
            raise ExchangeAPIError(f"Unknown symbol: {symbol!r}")
        return symbol_info(symbol=symbol)

    async def get_balances(self) -> list[Balance]:
        self._journal.append("balances")
        if self._balances_error is not None:
            raise self._balances_error
        return list(self._balances)

    async def get_klines(self, symbol: str, timeframe: str, *, limit: int = 500) -> list[Candle]:
        self._journal.append(f"seed:{symbol}/{timeframe}")
        return []

    async def close(self) -> None:
        self.close_calls += 1
        self._journal.append("close_client")

    # Unused by the root; present to satisfy the port.
    async def get_ticker(self, symbol: str) -> Ticker:  # pragma: no cover - not exercised
        raise NotImplementedError

    async def create_order(self, request: OrderRequest) -> Order:  # pragma: no cover
        raise NotImplementedError

    async def cancel_order(self, symbol: str, order_id: str) -> Order:  # pragma: no cover
        raise NotImplementedError

    async def get_open_orders(self, symbol: str | None = None) -> list[Order]:  # pragma: no cover
        raise NotImplementedError


class FakeStream(MarketDataStream):
    """Records lifecycle calls so teardown ordering is observable."""

    def __init__(self, journal: list[str] | None = None) -> None:
        self._journal = journal if journal is not None else []
        self.handlers: dict[tuple[str, str], CandleHandler] = {}
        self.start_calls = 0
        self.stop_calls = 0

    def subscribe(self, symbol: str, timeframe: str, handler: CandleHandler) -> None:
        self.handlers[(symbol, timeframe)] = handler

    async def start(self) -> None:
        self.start_calls += 1
        self._journal.append("stream_start")

    async def stop(self) -> None:
        self.stop_calls += 1
        self._journal.append("stream_stop")


class BoomRiskManager(RiskManager):
    """A risk manager whose ``evaluate`` raises, to exercise the handler's catch."""

    def evaluate(self, signal: Signal, *, portfolio: Portfolio) -> RiskAssessment:
        raise RuntimeError("risk exploded")


class BoomIntentLogger(IntentLogger):
    """An intent logger whose ``record`` raises."""

    async def record(self, signal: Signal, assessment: RiskAssessment) -> None:
        raise RuntimeError("logger exploded")


# --------------------------------------------------------------------------
# Settings builder
# --------------------------------------------------------------------------
_PAIRS_BLOCK = """    - symbol: {symbol}
      timeframe: {timeframe}
      enabled: {enabled}
"""


def write_settings(
    tmp_path: Path,
    *,
    pairs: tuple[tuple[str, str, bool], ...] = ((SYMBOL, TIMEFRAME, True),),
    base_currency: str = "USDT",
    mode: str = "testnet",
    strategy: str = "sma_crossover",
) -> Any:
    """Write a minimal config.yaml and load it through the real settings path."""
    from trading_bot.config.settings import get_settings

    # An empty tuple has to render as an explicit `[]`: a bare `pairs:` with no
    # block under it parses as None, which pydantic rejects for a list field --
    # so the test would fail at config load rather than reaching the guard.
    block = (
        "  pairs: []\n"
        if not pairs
        else "  pairs:\n"
        + "".join(
            _PAIRS_BLOCK.format(symbol=symbol, timeframe=timeframe, enabled=str(enabled).lower())
            for symbol, timeframe, enabled in pairs
        )
    )
    path = tmp_path / "modes_config.yaml"
    path.write_text(
        f"mode: {mode}\n"
        "trading:\n"
        f"  base_currency: {base_currency}\n"
        f"{block}"
        f"strategy:\n  name: {strategy}\n"
        "backtesting:\n  start_date: '2024-01-01'\n  end_date: '2024-02-01'\n"
        "logging:\n  console: false\n  file:\n    enabled: false\n",
        encoding="utf-8",
    )
    get_settings.cache_clear()
    return get_settings(str(path))


def default_pairs() -> dict[str, PairContext]:
    return {SYMBOL: PairContext(timeframe=TIMEFRAME, symbol_info=symbol_info())}


# --------------------------------------------------------------------------
# The ten refusal paths, driven through the real evaluate()
# --------------------------------------------------------------------------
Case = tuple[Signal, RiskAssessment, "Mapping[str, PairContext]"]


def _case_unknown_pair() -> Case:
    manager, _ = build_manager()
    signal = buy(symbol="DOGEUSDT")
    return (
        signal,
        manager.evaluate(signal, portfolio=Portfolio(free_quote=D("10000"))),
        default_pairs(),
    )


def _case_no_reference_price() -> Case:
    manager, _ = build_manager()
    signal = Signal(symbol=SYMBOL, action=SignalAction.BUY, timestamp=NOW)
    return (
        signal,
        manager.evaluate(signal, portfolio=Portfolio(free_quote=D("10000"))),
        default_pairs(),
    )


def _case_nothing_to_close() -> Case:
    manager, _ = build_manager()
    signal = Signal(symbol=SYMBOL, action=SignalAction.CLOSE, price=D("100"), timestamp=NOW)
    return (
        signal,
        manager.evaluate(signal, portfolio=Portfolio(free_quote=D("1000"))),
        default_pairs(),
    )


def _case_unsupported_action() -> Case:
    manager, _ = build_manager()
    signal = Signal(symbol=SYMBOL, action=SignalAction.SELL, price=D("100"), timestamp=NOW)
    return (
        signal,
        manager.evaluate(signal, portfolio=Portfolio(free_quote=D("10000"))),
        default_pairs(),
    )


def _case_no_mark_price() -> Case:
    """An open ETHUSDT position the provider has no candle for: equity is unknown."""
    pairs = multi_pairs(SYMBOL, "ETHUSDT")
    manager, _ = build_manager(provider=FakeProvider(candles={}), pairs=pairs)
    portfolio = Portfolio(
        free_quote=D("10000"), positions={"ETHUSDT": long_position(symbol="ETHUSDT")}
    )
    signal = buy()
    return signal, manager.evaluate(signal, portfolio=portfolio), pairs


def _case_limit_refused() -> Case:
    manager, _ = build_manager()
    signal = buy()
    return signal, manager.evaluate(signal, portfolio=Portfolio(free_quote=D("0"))), default_pairs()


def _case_atr_unavailable() -> Case:
    """ATR needs period + 1 clean bars; 14 bars for a 14-period ATR is one short."""
    pairs = default_pairs()
    manager, _ = build_manager(
        config=risk_config(
            stop_loss=StopLossConfig(type=StopType.ATR, atr_period=14),
            take_profit=TakeProfitConfig(enabled=False),
        ),
        provider=FakeProvider(frames={SYMBOL: ohlcv(14)}, candles={SYMBOL: candle()}),
        pairs=pairs,
    )
    signal = buy()
    return signal, manager.evaluate(signal, portfolio=Portfolio(free_quote=D("10000"))), pairs


def _case_stop_unplaceable() -> Case:
    """A 0.1% stop on a 1.00 tick collapses onto entry: representable, not a raise."""
    pairs = {SYMBOL: PairContext(timeframe=TIMEFRAME, symbol_info=symbol_info(price_tick="1.00"))}
    manager, _ = build_manager(
        config=risk_config(
            stop_loss=StopLossConfig(percent=D("0.1")),
            take_profit=TakeProfitConfig(enabled=False),
        ),
        pairs=pairs,
    )
    signal = buy("100")
    return signal, manager.evaluate(signal, portfolio=Portfolio(free_quote=D("10000"))), pairs


def _case_size_not_tradeable() -> Case:
    pairs = {SYMBOL: PairContext(timeframe=TIMEFRAME, symbol_info=symbol_info(min_notional="5000"))}
    manager, _ = build_manager(pairs=pairs)
    signal = buy()
    return signal, manager.evaluate(signal, portfolio=Portfolio(free_quote=D("500"))), pairs


def _case_unaffordable() -> Case:
    """Equity is 10050, almost all deployed in ETHUSDT; a 100-quote order still won't fit."""
    pairs = multi_pairs(SYMBOL, "ETHUSDT")
    manager, _ = build_manager(
        config=risk_config(method=PositionSizingMethod.FIXED_AMOUNT),
        provider=FakeProvider(candles={"ETHUSDT": candle(symbol="ETHUSDT")}),
        pairs=pairs,
    )
    portfolio = Portfolio(
        free_quote=D("50"),
        positions={"ETHUSDT": long_position(symbol="ETHUSDT", quantity="100", entry="100")},
    )
    signal = buy()
    return signal, manager.evaluate(signal, portfolio=portfolio), pairs


# Ten paths, one row each. Defined at module level rather than inline in
# `parametrize` so the correspondence to `evaluate`'s branches stays readable.
_STAGE_CASES = [
    (RefusalStage.UNKNOWN_PAIR, _case_unknown_pair),
    (RefusalStage.NO_REFERENCE_PRICE, _case_no_reference_price),
    (RefusalStage.NOTHING_TO_CLOSE, _case_nothing_to_close),
    (RefusalStage.UNSUPPORTED_ACTION, _case_unsupported_action),
    (RefusalStage.NO_MARK_PRICE, _case_no_mark_price),
    (RefusalStage.LIMIT_REFUSED, _case_limit_refused),
    (RefusalStage.ATR_UNAVAILABLE, _case_atr_unavailable),
    (RefusalStage.STOP_UNPLACEABLE, _case_stop_unplaceable),
    (RefusalStage.SIZE_NOT_TRADEABLE, _case_size_not_tradeable),
    (RefusalStage.UNAFFORDABLE, _case_unaffordable),
]


class TestRefusalStages:
    """What `evaluate` reports, and -- for inputs that trip two guards -- which
    guard it reports.

    The stage is now read off the assessment rather than inferred from it, so
    these tests assert `evaluate`'s own answer. What they still have to pin is
    its **guard order**: an input satisfying one guard cannot detect a reorder,
    because whichever guard runs first is the one that fires either way. Only an
    input satisfying *two* guards distinguishes the orderings, and each ordering
    test below supplies one.
    """

    @pytest.mark.parametrize(
        ("expected", "build"), _STAGE_CASES, ids=[stage.value for stage, _ in _STAGE_CASES]
    )
    def test_every_refusal_path_reports_its_stage(self, expected: RefusalStage, build: Any) -> None:
        """The anti-rot test: each case makes the real evaluate() take one branch."""
        _signal, assessment, _pairs = build()

        assert not assessment.approved
        assert assessment.stage is expected

    def test_the_cases_cover_every_stage(self) -> None:
        """Every member is a reachable path -- there is no unreachable value
        left in the enum for a future refusal to default into."""
        covered = {stage for stage, _ in _STAGE_CASES}
        assert covered == set(RefusalStage)

    def test_a_close_for_an_unknown_symbol_is_unknown_pair_not_nothing_to_close(self) -> None:
        """Pins the pair-context check ahead of the CLOSE dispatch.

        Both guards hold for this input. `evaluate` resolves the pair context
        first, which is right: a CLOSE for a symbol it has no filters for cannot
        be priced or sized, so "we do not know this pair" is the more
        fundamental answer than "there is nothing open in it".
        """
        manager, _ = build_manager()
        signal = Signal(symbol="DOGEUSDT", action=SignalAction.CLOSE, price=D("100"), timestamp=NOW)
        assessment = manager.evaluate(signal, portfolio=Portfolio(free_quote=D("1000")))

        assert assessment.stage is RefusalStage.UNKNOWN_PAIR

    def test_an_unknown_symbol_without_a_price_is_unknown_pair(self) -> None:
        """Pins the pair-context check ahead of the reference-price check.

        Both guards hold for this input. The ten parametrized cases each satisfy
        exactly one guard, so none of them can detect this swap.
        """
        manager, _ = build_manager()
        signal = Signal(symbol="DOGEUSDT", action=SignalAction.BUY, timestamp=NOW)
        assessment = manager.evaluate(signal, portfolio=Portfolio(free_quote=D("10000")))

        assert assessment.stage is RefusalStage.UNKNOWN_PAIR

    def test_a_close_without_a_price_is_no_reference_price(self) -> None:
        """Pins the reference-price check ahead of the CLOSE dispatch.

        Both guards hold for this input, and the price check winning is right:
        an exit still needs a price to be priced at.
        """
        manager, _ = build_manager()
        signal = Signal(symbol=SYMBOL, action=SignalAction.CLOSE, timestamp=NOW)
        assessment = manager.evaluate(signal, portfolio=Portfolio(free_quote=D("10000")))

        assert assessment.stage is RefusalStage.NO_REFERENCE_PRICE

    def test_a_limit_refusal_beats_an_unavailable_atr(self) -> None:
        """Pins the limit check ahead of the ATR bridge.

        Both guards hold: the portfolio already holds BTCUSDT, which trips
        ALREADY_IN_POSITION in `_approve`, *and* the buffer is one bar short of
        what a 14-period ATR needs, so `_atr_value` returns None. The limits win,
        which is right -- there is no point pricing a stop for an entry that is
        refused outright, and the ATR bridge is the more expensive check.

        This is the only adjacent pair on the approved path that is separately
        satisfiable; `decision` is bound before both guards, so a swap still
        compiles and reports the wrong stage rather than crashing. See the M4b
        entry in docs/PHASE_HISTORY.md for the pairs left unpinned and why.
        """
        pairs = {SYMBOL: PairContext(timeframe=TIMEFRAME, symbol_info=symbol_info())}
        manager, _ = build_manager(
            config=risk_config(
                stop_loss=StopLossConfig(type=StopType.ATR, atr_period=14),
                take_profit=TakeProfitConfig(enabled=False),
            ),
            # 14 bars is one short of the atr_period + 1 the bridge demands.
            provider=FakeProvider(frames={SYMBOL: ohlcv(14)}, candles={SYMBOL: candle()}),
            pairs=pairs,
        )
        portfolio = Portfolio(free_quote=D("10000"), positions={SYMBOL: long_position()})

        assessment = manager.evaluate(buy(), portfolio=portfolio)

        assert assessment.stage is RefusalStage.LIMIT_REFUSED
        assert assessment.decision is not None
        assert assessment.decision.rule is RiskRule.ALREADY_IN_POSITION


# --------------------------------------------------------------------------
# The log schema
# --------------------------------------------------------------------------
def _records(caplog: pytest.LogCaptureFixture, event: str) -> list[logging.LogRecord]:
    return [r for r in caplog.records if getattr(r, "event", None) == event]


def _fields(record: logging.LogRecord) -> dict[str, object]:
    return surplus_fields(record)


async def _emit_one(
    caplog: pytest.LogCaptureFixture, signal: Signal, assessment: RiskAssessment, pairs: Any
) -> logging.LogRecord:
    """Emit one assessment and return the record *this module* produced.

    Filtered by logger name rather than taking ``caplog.records[0]``:
    ``at_level`` lowers the capture handler's level globally, so a collaborator
    that logs on its own -- ``RiskManager.evaluate`` emits "Risk approved" at
    INFO -- lands in the same buffer whenever an earlier test has left the root
    level low. That made this helper pass in isolation and fail in a full run.
    """
    logger = IntentLogger(pairs=pairs)
    with caplog.at_level(logging.DEBUG, logger=_MODES_LOGGER):
        await logger.record(signal, assessment)
    mine = [record for record in caplog.records if record.name == _MODES_LOGGER]
    assert len(mine) == 1
    return mine[0]


class TestLogSchema:
    async def test_a_refusal_carries_the_full_refusal_field_set(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        signal, assessment, pairs = _case_limit_refused()

        record = await _emit_one(caplog, signal, assessment, pairs)

        assert _fields(record) == {
            "event": "risk_refused",
            "symbol": SYMBOL,
            "timeframe": TIMEFRAME,
            "action": "BUY",
            "signal_ts": NOW.isoformat(),
            "stage": "limit_refused",
            "rule_fired": "no_equity",
            "reason": assessment.reason,
        }

    async def test_rule_fired_is_present_on_a_limit_refusal(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        signal, assessment, pairs = _case_no_mark_price()

        record = await _emit_one(caplog, signal, assessment, pairs)

        assert _fields(record)["rule_fired"] == "no_mark_price"

    @pytest.mark.parametrize(
        "build",
        [
            _case_atr_unavailable,
            _case_stop_unplaceable,
            _case_size_not_tradeable,
            _case_unaffordable,
        ],
        ids=["atr", "stop", "sizing", "affordability"],
    )
    async def test_rule_fired_is_absent_on_the_post_approve_refusals(
        self, caplog: pytest.LogCaptureFixture, build: Any
    ) -> None:
        """These four carry a decision whose `approved` is True and whose rule is
        None, which is why the schema branches on `approved` and never on rule
        presence. Absent, not null."""
        signal, assessment, pairs = build()

        record = await _emit_one(caplog, signal, assessment, pairs)

        assert assessment.decision is not None
        assert assessment.decision.approved
        assert "rule_fired" not in _fields(record)

    async def test_timeframe_is_absent_when_the_pair_is_unknown(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Signal carries no timeframe, so it is resolved through `pairs` -- and
        an unknown pair is precisely the case that has no entry there."""
        signal, assessment, pairs = _case_unknown_pair()

        record = await _emit_one(caplog, signal, assessment, pairs)

        assert "timeframe" not in _fields(record)
        assert _fields(record)["stage"] == "unknown_pair"

    async def test_an_approved_entry_carries_the_intent_field_set(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        manager, _ = build_manager()
        signal = buy("100.00")
        assessment = manager.evaluate(signal, portfolio=Portfolio(free_quote=D("10000")))
        assert assessment.approved

        record = await _emit_one(caplog, signal, assessment, default_pairs())

        fields = _fields(record)
        assert fields["event"] == "intent_dispatched"
        assert fields["side"] == "BUY"
        assert fields["entry"] == D("100.00")
        assert fields["stop"] == D("98.00")
        assert fields["take_profit"] == D("104.00")
        assert "stage" not in fields
        assert "rule_fired" not in fields

    async def test_an_approved_exit_omits_the_protective_levels(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """An exit closes a position rather than opening one to protect, so its
        intent carries no levels -- absent fields, not null ones."""
        manager, _ = build_manager()
        portfolio = Portfolio(free_quote=D("0"), positions={SYMBOL: long_position(quantity="0.75")})
        signal = Signal(symbol=SYMBOL, action=SignalAction.CLOSE, price=D("123.45"), timestamp=NOW)
        assessment = manager.evaluate(signal, portfolio=portfolio)
        assert assessment.intent is not None
        assert assessment.intent.side is OrderSide.SELL

        record = await _emit_one(caplog, signal, assessment, default_pairs())

        fields = _fields(record)
        assert fields["side"] == "SELL"
        assert fields["quantity"] == D("0.75")
        assert "stop" not in fields
        assert "take_profit" not in fields

    async def test_no_field_is_ever_null(self, caplog: pytest.LogCaptureFixture) -> None:
        """Absent, not null -- checked across every refusal path at once."""
        for _stage, build in _STAGE_CASES:
            caplog.clear()
            signal, assessment, pairs = build()
            record = await _emit_one(caplog, signal, assessment, pairs)
            assert None not in _fields(record).values()

    async def test_enums_cross_as_values_so_both_sinks_agree(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """A `str, Enum` member reaches JSON as its value but text as
        `str(member)`. Passing `.value` is what keeps `action=BUY` from becoming
        `action=SignalAction.BUY` in exactly one of the two sinks."""
        from trading_bot.utils.logger import JsonFormatter, PlainFormatter

        signal, assessment, pairs = _case_limit_refused()
        record = await _emit_one(caplog, signal, assessment, pairs)

        assert "action=BUY" in PlainFormatter("%(message)s").format(record)
        assert '"action": "BUY"' in JsonFormatter().format(record)
        assert "SignalAction" not in PlainFormatter("%(message)s").format(record)

    async def test_decimals_render_identically_and_exactly_in_both_sinks(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        from trading_bot.utils.logger import JsonFormatter, PlainFormatter

        manager, _ = build_manager()
        signal = buy("100.00")
        assessment = manager.evaluate(signal, portfolio=Portfolio(free_quote=D("10000")))
        record = await _emit_one(caplog, signal, assessment, default_pairs())

        assert "entry=100.00" in PlainFormatter("%(message)s").format(record)
        assert '"entry": "100.00"' in JsonFormatter().format(record)

    async def test_no_log_field_collides_with_a_reserved_record_attribute(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """`Logger.makeRecord` raises at the call site on a reserved name, so a
        collision would surface as a KeyError from inside the handler."""
        emitted: set[str] = set()
        for _stage, build in _STAGE_CASES:
            caplog.clear()
            signal, assessment, pairs = build()
            emitted |= set(_fields(await _emit_one(caplog, signal, assessment, pairs)))

        reserved = frozenset(logging.LogRecord("", 0, "", 0, "", (), None).__dict__) | {
            "message",
            "asctime",
        }
        assert emitted & reserved == set()


# --------------------------------------------------------------------------
# The chained handler
# --------------------------------------------------------------------------
def build_handler(
    *,
    risk: RiskManager | None = None,
    intent_logger: IntentLogger | None = None,
    portfolio: Portfolio | None = None,
    pairs: Mapping[str, PairContext] | None = None,
) -> Any:
    resolved_pairs = pairs if pairs is not None else default_pairs()
    manager, _ = build_manager(pairs=resolved_pairs)
    return _build_signal_handler(
        risk=risk if risk is not None else manager,
        intent_logger=intent_logger
        if intent_logger is not None
        else IntentLogger(pairs=resolved_pairs),
        portfolio=portfolio if portfolio is not None else Portfolio(free_quote=D("10000")),
        pairs=resolved_pairs,
    )


class TestChainedHandler:
    async def test_an_approved_signal_reaches_the_intent_logger(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        handler = build_handler()
        with caplog.at_level(logging.DEBUG, logger=_MODES_LOGGER):
            await handler(buy("100.00"))

        assert len(_records(caplog, "intent_dispatched")) == 1

    async def test_a_raising_risk_manager_is_named_and_contained(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        pairs = default_pairs()
        boom, _ = build_manager(pairs=pairs)
        handler = build_handler(
            risk=BoomRiskManager(
                config=risk_config(),
                provider=FakeProvider(frames={SYMBOL: ohlcv(50)}, candles={SYMBOL: candle()}),
                pairs=pairs,
            ),
            pairs=pairs,
        )
        assert boom is not None

        with caplog.at_level(logging.DEBUG, logger=_MODES_LOGGER):
            await handler(buy())  # must not raise

        failures = _records(caplog, "collaborator_failed")
        assert len(failures) == 1
        assert _fields(failures[0])["collaborator"] == "risk_manager"
        assert _fields(failures[0])["error_type"] == "RuntimeError"
        # The chain stopped: nothing downstream ran.
        assert _records(caplog, "intent_dispatched") == []

    async def test_a_raising_intent_logger_is_named_and_contained(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        pairs = default_pairs()
        handler = build_handler(intent_logger=BoomIntentLogger(pairs=pairs), pairs=pairs)

        with caplog.at_level(logging.DEBUG, logger=_MODES_LOGGER):
            await handler(buy("100.00"))  # must not raise

        failures = _records(caplog, "collaborator_failed")
        assert len(failures) == 1
        assert _fields(failures[0])["collaborator"] == "intent_logger"

    async def test_the_engines_own_catch_never_fires(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """The load-bearing assertion. `_emit` catches with a bare
        `except Exception` and no structured fields, and the engine's failure
        counter is fed only from `_evaluate` -- so anything escaping this handler
        would be an unstructured traceback every bar, forever, with no
        quarantine. Driven through the real engine so the catch is the real one.
        """
        pairs = default_pairs()
        provider = FakeMarketDataProvider({_KEY: 100})
        strategy = ScriptedStrategy(result=buy("100.00"))
        engine = TradingEngine(provider, {_KEY: strategy})
        engine.on_signal(build_handler(intent_logger=BoomIntentLogger(pairs=pairs), pairs=pairs))
        await engine.start()

        with caplog.at_level(logging.DEBUG):
            await provider.emit(engine_candle())

        assert "Signal handler failed" not in caplog.text
        assert len(_records(caplog, "collaborator_failed")) == 1


# --------------------------------------------------------------------------
# Boot: the fail-fast refusals
# --------------------------------------------------------------------------
class TestBootRefusals:
    async def test_a_non_live_mode_is_refused_as_missing_not_forbidden(
        self, tmp_path: Path
    ) -> None:
        settings = write_settings(tmp_path, mode="paper")
        client = FakeRootClient()

        with pytest.raises(ConfigError, match="No composition root exists for mode 'paper'"):
            async with live_system(settings, client=client, stream=FakeStream()):
                pass  # pragma: no cover - the refusal precedes the body

        # Refused before anything was built, so there is nothing to close.
        assert client.close_calls == 0

    def test_a_duplicate_symbol_refuses_and_names_both_timeframes(self, tmp_path: Path) -> None:
        settings = write_settings(tmp_path, pairs=((SYMBOL, "1m", True), (SYMBOL, "5m", True)))

        with pytest.raises(ConfigError) as exc_info:
            _pair_timeframes(settings)

        message = str(exc_info.value)
        assert SYMBOL in message
        assert "1m" in message
        assert "5m" in message

    async def test_a_duplicate_symbol_refuses_the_boot(self, tmp_path: Path) -> None:
        settings = write_settings(tmp_path, pairs=((SYMBOL, "1m", True), (SYMBOL, "5m", True)))
        client = FakeRootClient()

        with pytest.raises(ConfigError, match="two timeframes"):
            async with live_system(settings, client=client, stream=FakeStream()):
                pass  # pragma: no cover - the refusal precedes the body

        # Pure check, so it costs no round trip -- and the client still closes.
        assert client.symbol_info_calls == []
        assert client.close_calls == 1

    def test_a_disabled_duplicate_does_not_refuse(self, tmp_path: Path) -> None:
        """`enabled_pairs` filters first, so a disabled second entry is not a clash."""
        settings = write_settings(tmp_path, pairs=((SYMBOL, "1m", True), (SYMBOL, "5m", False)))
        assert _pair_timeframes(settings) == {SYMBOL: "1m"}

    def test_no_pairs_at_all_refuses_and_says_the_list_is_empty(self, tmp_path: Path) -> None:
        """`TradingEngine.start` already rejects this, but with a bare ValueError
        -- not a TradingBotError -- several steps later, with a REST client and a
        WebSocket already open. Refusing here is the same answer, earlier, in a
        vocabulary that names config.yaml."""
        settings = write_settings(tmp_path, pairs=())

        with pytest.raises(ConfigError) as exc_info:
            _pair_timeframes(settings)

        message = str(exc_info.value)
        assert "trading.pairs is empty" in message
        assert "config.yaml" in message

    def test_all_pairs_disabled_refuses_and_says_so_distinctly(self, tmp_path: Path) -> None:
        """The two empty cases need opposite fixes, so they must not share a
        message. This is the one an operator hits after toggling a pair off to
        debug something and forgetting to toggle it back."""
        settings = write_settings(tmp_path, pairs=((SYMBOL, "1m", False), ("ETHUSDT", "5m", False)))

        with pytest.raises(ConfigError) as exc_info:
            _pair_timeframes(settings)

        message = str(exc_info.value)
        assert "all 2 configured pair(s) have enabled: false" in message
        assert "trading.pairs is empty" not in message

    def test_one_enabled_pair_is_enough(self, tmp_path: Path) -> None:
        settings = write_settings(tmp_path, pairs=((SYMBOL, "1m", True), ("ETHUSDT", "5m", False)))
        assert _pair_timeframes(settings) == {SYMBOL: "1m"}

    @pytest.mark.parametrize(
        ("pairs", "expected"),
        [
            ((), "trading.pairs is empty"),
            (((SYMBOL, "1m", False),), "have enabled: false"),
        ],
        ids=["empty", "all-disabled"],
    )
    async def test_an_empty_pair_set_refuses_the_boot(
        self, tmp_path: Path, pairs: Any, expected: str
    ) -> None:
        settings = write_settings(tmp_path, pairs=pairs)
        client = FakeRootClient()

        with pytest.raises(ConfigError, match=expected):
            async with live_system(settings, client=client, stream=FakeStream()):
                pass  # pragma: no cover - the refusal precedes the body

        # Pure check: refused before any round trip, and the client still closes.
        assert client.symbol_info_calls == []
        assert client.close_calls == 1

    async def test_an_unprimeable_symbol_refuses_the_boot(self, tmp_path: Path) -> None:
        settings = write_settings(tmp_path, pairs=(("DOGEUSDT", "1m", True),))
        client = FakeRootClient(unknown_symbols=frozenset({"DOGEUSDT"}))

        with pytest.raises(ExchangeAPIError, match="DOGEUSDT"):
            async with live_system(settings, client=client, stream=FakeStream()):
                pass  # pragma: no cover - the refusal precedes the body

        assert client.close_calls == 1

    async def test_a_missing_quote_asset_refuses_the_boot(self, tmp_path: Path) -> None:
        settings = write_settings(tmp_path, base_currency="BUSD")
        client = FakeRootClient(balances=[Balance(asset="USDT", free=D("5000"), locked=D("0"))])

        with pytest.raises(ConfigError, match="BUSD"):
            async with live_system(settings, client=client, stream=FakeStream()):
                pass  # pragma: no cover - the refusal precedes the body

        assert client.close_calls == 1

    async def test_a_zero_balance_is_a_valid_state_and_boots(self, tmp_path: Path) -> None:
        """get_balances returns every asset including zeros, so absent means
        absent -- and zero is a state the account can legitimately be in."""
        settings = write_settings(tmp_path)
        client = FakeRootClient(balances=[Balance(asset="USDT", free=D("0"), locked=D("0"))])

        async with live_system(settings, client=client, stream=FakeStream()) as system:
            assert system.portfolio.free_quote == D("0")


class TestQuoteAssetMatching:
    async def test_matching_is_case_insensitive_on_both_sides(self) -> None:
        """`trading.base_currency` carries no validator of its own, so this code
        has to be correct standing alone. The Commit-2 validator is defence in
        depth, not a substitute."""
        client = FakeRootClient(balances=[Balance(asset="usdt", free=D("12"), locked=D("0"))])

        portfolio = await _seed_portfolio(client, quote_asset="uSdT")

        assert portfolio.free_quote == D("12")

    async def test_the_normalised_form_is_what_lands_on_the_portfolio(self) -> None:
        """It is interpolated into refusal messages and future code will compare it."""
        client = FakeRootClient(balances=[Balance(asset="usdt", free=D("1"), locked=D("0"))])

        portfolio = await _seed_portfolio(client, quote_asset="usdt")

        assert portfolio.quote_asset == "USDT"

    async def test_a_lowercase_base_currency_in_config_still_boots(self, tmp_path: Path) -> None:
        settings = write_settings(tmp_path, base_currency="usdt")
        client = FakeRootClient()

        async with live_system(settings, client=client, stream=FakeStream()) as system:
            assert system.portfolio.quote_asset == "USDT"
            assert system.portfolio.free_quote == D("5000")


# --------------------------------------------------------------------------
# Boot: what gets assembled
# --------------------------------------------------------------------------
class TestBootAssembly:
    async def test_the_container_carries_every_collaborator(self, tmp_path: Path) -> None:
        settings = write_settings(tmp_path)

        async with live_system(settings, client=FakeRootClient(), stream=FakeStream()) as system:
            assert isinstance(system, LiveSystem)
            assert system.settings is settings
            assert isinstance(system.engine, TradingEngine)
            assert isinstance(system.risk, RiskManager)
            assert isinstance(system.intent_logger, IntentLogger)
            assert system.pairs.keys() == {SYMBOL}
            assert system.pairs[SYMBOL].timeframe == TIMEFRAME

    async def test_the_container_is_frozen(self, tmp_path: Path) -> None:
        settings = write_settings(tmp_path)

        async with live_system(settings, client=FakeRootClient(), stream=FakeStream()) as system:
            with pytest.raises(FrozenInstanceError):
                system.portfolio = Portfolio()  # type: ignore[misc]

    async def test_symbol_info_is_fetched_once_per_distinct_symbol(self, tmp_path: Path) -> None:
        """One round trip per symbol, not per pair: the cache is symbol-keyed."""
        settings = write_settings(tmp_path, pairs=((SYMBOL, "1m", True), ("ETHUSDT", "5m", True)))
        client = FakeRootClient()

        async with live_system(settings, client=client, stream=FakeStream()):
            pass

        assert client.symbol_info_calls == [SYMBOL, "ETHUSDT"]

    async def test_exactly_one_signal_handler_is_registered(self, tmp_path: Path) -> None:
        settings = write_settings(tmp_path)

        async with live_system(settings, client=FakeRootClient(), stream=FakeStream()) as system:
            handlers = system.engine._signal_handlers
            assert len(handlers) == 1

    async def test_the_wired_handler_produces_the_intent_stream(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        """End to end through the assembled root: a signal in, a schema line out."""
        settings = write_settings(tmp_path)

        async with live_system(settings, client=FakeRootClient(), stream=FakeStream()) as system:
            with caplog.at_level(logging.DEBUG, logger=_MODES_LOGGER):
                await system.engine._emit(buy("100.00"))

        assert len(_records(caplog, "intent_dispatched")) == 1

    async def test_the_portfolio_is_a_boot_snapshot(self, tmp_path: Path) -> None:
        """Nothing mutates it in M4a; it is a photograph, not yet a ledger."""
        settings = write_settings(tmp_path)
        client = FakeRootClient(balances=[Balance(asset="USDT", free=D("777"), locked=D("3"))])

        async with live_system(settings, client=client, stream=FakeStream()) as system:
            before = system.portfolio.free_quote
            await system.engine._emit(buy("100.00"))
            assert system.portfolio.free_quote == before == D("777")


# --------------------------------------------------------------------------
# Teardown and ownership
# --------------------------------------------------------------------------
class TestTeardown:
    async def test_the_client_is_closed_exactly_once_on_the_normal_path(
        self, tmp_path: Path
    ) -> None:
        settings = write_settings(tmp_path)
        client = FakeRootClient()

        async with live_system(settings, client=client, stream=FakeStream()):
            assert client.close_calls == 0

        assert client.close_calls == 1

    async def test_the_provider_does_not_close_an_injected_client(self, tmp_path: Path) -> None:
        """`owns_client = client is None`, so under injection the provider closes
        nothing -- which is exactly why the root has to."""
        settings = write_settings(tmp_path)
        client = FakeRootClient()

        async with live_system(settings, client=client, stream=FakeStream()) as system:
            await system.provider.stop()
            assert client.close_calls == 0

        assert client.close_calls == 1

    async def test_the_stream_stops_before_the_client_closes(self, tmp_path: Path) -> None:
        journal: list[str] = []
        settings = write_settings(tmp_path)
        client = FakeRootClient(journal=journal)
        stream = FakeStream(journal)

        async with live_system(settings, client=client, stream=stream) as system:
            await system.engine.start()
        assert journal.index("stream_stop") < journal.index("close_client")
        assert journal[-1] == "close_client"

    async def test_the_client_closes_when_the_body_raises(self, tmp_path: Path) -> None:
        settings = write_settings(tmp_path)
        client = FakeRootClient()

        with pytest.raises(RuntimeError, match="body exploded"):
            async with live_system(settings, client=client, stream=FakeStream()):
                raise RuntimeError("body exploded")

        assert client.close_calls == 1

    async def test_the_client_closes_when_engine_construction_raises(self, tmp_path: Path) -> None:
        """The window the nested `finally` exists for: the provider is built and
        its stream owns a second connection, but `engine` is never bound. A
        single `finally` naming `engine` would raise UnboundLocalError here and
        mask the real error."""
        settings = write_settings(tmp_path, strategy="no_such_strategy")
        client = FakeRootClient()
        stream = FakeStream()

        with pytest.raises(StrategyNotFoundError, match="no_such_strategy"):
            async with live_system(settings, client=client, stream=stream):
                pass  # pragma: no cover - construction fails first

        assert client.close_calls == 1
        assert stream.stop_calls == 1  # the provider was still torn down

    async def test_a_balances_failure_closes_the_client(self, tmp_path: Path) -> None:
        settings = write_settings(tmp_path)
        client = FakeRootClient(balances_error=ExchangeAPIError("account unavailable"))

        with pytest.raises(ExchangeAPIError, match="account unavailable"):
            async with live_system(settings, client=client, stream=FakeStream()):
                pass  # pragma: no cover - the refusal precedes the body

        assert client.close_calls == 1

    async def test_stopping_a_never_started_engine_does_not_raise(self, tmp_path: Path) -> None:
        """The root's inner `finally` runs whether or not `run()` was ever
        called, so `stop()` has to tolerate an engine that never started."""
        settings = write_settings(tmp_path)
        stream = FakeStream()

        async with live_system(settings, client=FakeRootClient(), stream=stream) as system:
            assert stream.start_calls == 0
            await system.engine.stop()  # explicit, before the finally does it again

        assert stream.stop_calls >= 1


# --------------------------------------------------------------------------
# A refusal has to fail *cleanly*, all the way out to the process exit code
# --------------------------------------------------------------------------
class TestBootRefusalsReachTheCli:
    """A fail-fast that fails ugly is half-built.

    Every boot refusal now propagates out of an ``async with``, through
    ``asyncio.run``, to ``main``'s ``except TradingBotError``. What the operator
    must see is the message and a non-zero status -- not a traceback.
    """

    @pytest.mark.parametrize(
        "exc_type",
        [ConfigError, ExchangeAPIError, StrategyNotFoundError],
        ids=["config", "exchange", "strategy"],
    )
    def test_every_refusal_type_is_caught_by_the_cli_handler(self, exc_type: type) -> None:
        """All four refusal classes raise one of these, and `main` catches the
        common base -- so none of them can reach the user as a traceback."""
        assert issubclass(exc_type, TradingBotError)

    def test_the_cli_exits_non_zero_without_a_traceback(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Driven through the real ``main``: parser, settings, logging, dispatch.

        The paper-mode refusal is the one that needs no client at all, so this
        stays hermetic while exercising the identical except-clause every other
        refusal lands in.
        """
        from trading_bot.main import main

        path = tmp_path / "cli_config.yaml"
        path.write_text(
            "mode: paper\n"
            "strategy:\n  name: sma_crossover\n"
            "backtesting:\n  start_date: '2024-01-01'\n  end_date: '2024-02-01'\n"
            "logging:\n  console: false\n  file:\n    enabled: false\n",
            encoding="utf-8",
        )

        root = logging.getLogger()
        saved_handlers, saved_level = list(root.handlers), root.level
        try:
            code = main(["--config", str(path), "run"])
        finally:
            root.handlers[:] = saved_handlers
            root.setLevel(saved_level)

        assert code == 1
        assert "Traceback" not in capsys.readouterr().err
