"""Tests for the risk manager -- limits, the ATR bridge, and the composed path.

Hermetic: no network, no real time, no patching. The clock is injected, the
market-data provider is a scripted fake, and the exchange filters are a plain
dict -- the manager performs no I/O, so nothing has to be mocked to keep it
offline.

Exact ``Decimal`` assertions in money code. A result that is merely *close* is a
bug, and a tolerant assertion cannot detect the float leak the ``Money`` guard
exists to prevent.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import TYPE_CHECKING

import numpy as np
import pandas as pd
import pytest
from pydantic import ValidationError

from trading_bot.config.models import (
    PositionSizingConfig,
    RiskConfig,
    RiskLimitsConfig,
    StopLossConfig,
    TakeProfitConfig,
    TrailingStopConfig,
)
from trading_bot.core.enums import (
    OrderSide,
    PositionSide,
    PositionSizingMethod,
    RefusalStage,
    RiskRule,
    SignalAction,
    StopType,
    TakeProfitType,
)
from trading_bot.core.interfaces import MarketDataProvider
from trading_bot.core.models import Candle, Position, RiskDecision, Signal, SymbolInfo
from trading_bot.core.portfolio import Portfolio
from trading_bot.risk.manager import PairContext, RiskAssessment, RiskManager, TradeIntent
from trading_bot.risk.rules import ExitReason

if TYPE_CHECKING:  # pragma: no cover - typing only
    from collections.abc import Callable, Mapping

    from trading_bot.core.interfaces import CandleHandler

D = Decimal

#: A fixed instant every test measures from. Midday UTC, so a test can advance
#: hours in either direction without accidentally crossing a day boundary.
NOW = datetime(2026, 7, 25, 12, 0, tzinfo=timezone.utc)

SYMBOL = "BTCUSDT"
TIMEFRAME = "1m"


# --------------------------------------------------------------------------
# Fakes and builders
# --------------------------------------------------------------------------
class FakeClock:
    """An injectable clock the test advances explicitly."""

    def __init__(self, now: datetime = NOW) -> None:
        self.now = now

    def __call__(self) -> datetime:
        return self.now

    def advance(self, **delta: float) -> None:
        self.now += timedelta(**delta)


class FakeProvider(MarketDataProvider):
    """Port-conformant provider serving canned frames and candles.

    ``candle_count`` is derived from the frame length so ``is_ready`` -- the
    concrete method the manager's ATR gate calls -- behaves exactly as it does
    in production rather than being stubbed out.
    """

    def __init__(
        self,
        frames: Mapping[str, pd.DataFrame] | None = None,
        candles: Mapping[str, Candle | None] | None = None,
    ) -> None:
        self._frames = dict(frames or {})
        self._candles = dict(candles or {})

    def track(self, symbol: str, timeframe: str) -> None:
        pass

    def on_candle(self, handler: CandleHandler) -> None:
        pass

    async def start(self) -> None:
        pass

    async def stop(self) -> None:
        pass

    def get_dataframe(self, symbol: str, timeframe: str) -> pd.DataFrame:
        return self._frames.get(symbol, ohlcv(0))

    def candle_count(self, symbol: str, timeframe: str) -> int:
        return len(self._frames.get(symbol, ohlcv(0)))

    def last_candle(self, symbol: str, timeframe: str) -> Candle | None:
        return self._candles.get(symbol)


def ohlcv(
    bars: int, *, high: float = 101.0, low: float = 99.0, close: float = 100.0
) -> pd.DataFrame:
    """A float64 OHLCV frame shaped like the provider's, with a constant range.

    A constant ``high``/``low``/``close`` makes the true range constant too, so
    ATR equals that range exactly and the expected stop can be written down.
    """
    index = pd.DatetimeIndex(
        [NOW - timedelta(minutes=bars - i) for i in range(bars)], name="open_time", tz="UTC"
    )
    return pd.DataFrame(
        {
            "open": np.full(bars, close),
            "high": np.full(bars, high),
            "low": np.full(bars, low),
            "close": np.full(bars, close),
            "volume": np.full(bars, 1.0),
        },
        index=index,
    )


def candle(close: str = "100", *, symbol: str = SYMBOL) -> Candle:
    return Candle(
        symbol=symbol,
        timeframe=TIMEFRAME,
        open_time=NOW,
        close_time=NOW,
        open=D("100"),
        high=D("101"),
        low=D("99"),
        close=D(close),
        volume=D("1"),
    )


def symbol_info(
    *,
    symbol: str = SYMBOL,
    price_tick: str = "0.01",
    step_size: str = "0.001",
    min_qty: str = "0.001",
    min_notional: str = "10",
) -> SymbolInfo:
    return SymbolInfo(
        symbol=symbol,
        base_asset=symbol[:3],
        quote_asset="USDT",
        price_tick=D(price_tick),
        step_size=D(step_size),
        min_qty=D(min_qty),
        min_notional=D(min_notional),
    )


def risk_config(
    *,
    method: PositionSizingMethod = PositionSizingMethod.FIXED_FRACTION,
    stop_loss: StopLossConfig | None = None,
    take_profit: TakeProfitConfig | None = None,
    trailing_stop: TrailingStopConfig | None = None,
    max_position_size_percent: str = "100",
    max_open_positions: int = 3,
    max_daily_loss_percent: str = "5.0",
    cooldown_minutes: int = 15,
) -> RiskConfig:
    """A RiskConfig with the caps opened up unless a test narrows them.

    ``max_position_size_percent`` defaults to 100 so that a test exercising a
    sizing method sees that method's own answer rather than the cap's.
    """
    return RiskConfig(
        position_sizing=PositionSizingConfig(method=method),
        stop_loss=stop_loss or StopLossConfig(),
        take_profit=take_profit or TakeProfitConfig(),
        trailing_stop=trailing_stop or TrailingStopConfig(),
        limits=RiskLimitsConfig(
            max_position_size_percent=D(max_position_size_percent),
            max_open_positions=max_open_positions,
            max_daily_loss_percent=D(max_daily_loss_percent),
            cooldown_minutes=cooldown_minutes,
        ),
    )


def multi_pairs(*symbols: str) -> dict[str, PairContext]:
    """A pairs mapping covering several symbols, all on the same timeframe."""
    return {
        symbol: PairContext(timeframe=TIMEFRAME, symbol_info=symbol_info(symbol=symbol))
        for symbol in symbols
    }


def build_manager(
    *,
    config: RiskConfig | None = None,
    provider: MarketDataProvider | None = None,
    pairs: Mapping[str, PairContext] | None = None,
    clock: FakeClock | None = None,
) -> tuple[RiskManager, FakeClock]:
    the_clock = clock or FakeClock()
    manager = RiskManager(
        config=config or risk_config(),
        provider=provider or FakeProvider(frames={SYMBOL: ohlcv(50)}, candles={SYMBOL: candle()}),
        pairs=pairs or {SYMBOL: PairContext(timeframe=TIMEFRAME, symbol_info=symbol_info())},
        clock=the_clock,
    )
    return manager, the_clock


def buy(price: str = "100.00", *, symbol: str = SYMBOL) -> Signal:
    return Signal(symbol=symbol, action=SignalAction.BUY, price=D(price), timestamp=NOW)


def long_position(
    *,
    symbol: str = SYMBOL,
    quantity: str = "1",
    entry: str = "100",
    stop_loss: Decimal | None = None,
    take_profit: Decimal | None = None,
) -> Position:
    return Position(
        symbol=symbol,
        side=PositionSide.LONG,
        quantity=D(quantity),
        entry_price=D(entry),
        opened_at=NOW,
        stop_loss=stop_loss,
        take_profit=take_profit,
    )


# --------------------------------------------------------------------------
# Portfolio: equity, the daily ledger, cooldown
# --------------------------------------------------------------------------
class TestPortfolio:
    def test_equity_is_free_quote_plus_mark_to_market(self) -> None:
        """Equity is total value, not free balance -- the distinction the sizer
        documents, and the difference between a stable position size and one
        that shrinks as capital deploys."""
        portfolio = Portfolio(
            free_quote=D("2500.50"),
            positions={SYMBOL: long_position(quantity="0.5", entry="90")},
        )
        assert portfolio.equity({SYMBOL: D("120.40")}) == D("2560.70")

    def test_equity_ignores_a_closed_position(self) -> None:
        portfolio = Portfolio(
            free_quote=D("1000"),
            positions={
                SYMBOL: Position(
                    symbol=SYMBOL, side=PositionSide.FLAT, quantity=D("0"), entry_price=D("100")
                )
            },
        )
        assert portfolio.equity({}) == D("1000")
        assert portfolio.position_count == 0

    def test_equity_raises_when_a_position_cannot_be_marked(self) -> None:
        """Defaulting to entry price or zero would misstate the denominator of
        every sizing and daily-loss decision."""
        portfolio = Portfolio(free_quote=D("1000"), positions={SYMBOL: long_position()})
        with pytest.raises(ValueError, match="no mark price"):
            portfolio.equity({})

    def test_realised_pnl_accrues_and_resets_on_the_utc_day_boundary(self) -> None:
        portfolio = Portfolio(free_quote=D("1000"))
        portfolio.record_realised_pnl(D("-120.25"), now=NOW)
        assert portfolio.realised_today(NOW) == D("-120.25")

        # Same UTC day, 11 hours later: still accruing into the same bucket.
        portfolio.record_realised_pnl(D("-10"), now=NOW + timedelta(hours=11))
        assert portfolio.realised_today(NOW + timedelta(hours=11)) == D("-130.25")

        # Past midnight UTC: a fresh day, rolled lazily on read.
        assert portfolio.realised_today(NOW + timedelta(hours=13)) == D("0")

    def test_daily_loss_threshold_is_a_percent_of_equity(self) -> None:
        portfolio = Portfolio(free_quote=D("10000"))
        limit = D("5.0")  # 5% of 10000 == 500

        portfolio.record_realised_pnl(D("-499.99"), now=NOW)
        assert not portfolio.daily_loss_exceeded(limit_percent=limit, equity=D("10000"), now=NOW)

        portfolio.record_realised_pnl(D("-0.01"), now=NOW)
        assert portfolio.daily_loss_exceeded(limit_percent=limit, equity=D("10000"), now=NOW)

    def test_cooldown_expires_by_comparison_not_by_sweep(self) -> None:
        portfolio = Portfolio(free_quote=D("1000"))
        portfolio.start_cooldown(SYMBOL, now=NOW, minutes=15)

        assert portfolio.in_cooldown(SYMBOL, NOW + timedelta(minutes=14, seconds=59))
        assert not portfolio.in_cooldown(SYMBOL, NOW + timedelta(minutes=15))
        assert not portfolio.in_cooldown("ETHUSDT", NOW)

    def test_zero_minute_cooldown_records_nothing(self) -> None:
        """`cooldown_minutes: 0` is a supported config and must never block."""
        portfolio = Portfolio(free_quote=D("1000"))
        portfolio.start_cooldown(SYMBOL, now=NOW, minutes=0)
        assert portfolio.cooldown_expiry(SYMBOL) is None
        assert not portfolio.in_cooldown(SYMBOL, NOW)

    def test_naive_datetime_is_rejected(self) -> None:
        """A naive value would be read as local time, moving the UTC day
        boundary by the host's offset."""
        portfolio = Portfolio(free_quote=D("1000"))
        with pytest.raises(ValueError, match="timezone-aware"):
            portfolio.realised_today(datetime(2026, 7, 25, 12, 0))

    def test_money_fields_reject_a_float_on_assignment(self) -> None:
        """validate_assignment closes the leak plain pydantic models leave open:
        construction is guarded, and so is every later write."""
        portfolio = Portfolio(free_quote=D("1000"))
        with pytest.raises(ValidationError, match="must not be built from a float"):
            portfolio.free_quote = 1000.5  # type: ignore[assignment]


# --------------------------------------------------------------------------
# approve: each limit independently, with the clock advanced explicitly
# --------------------------------------------------------------------------
class TestApprove:
    def test_approves_within_every_limit(self) -> None:
        manager, _ = build_manager()
        decision = manager.approve(buy(), portfolio=Portfolio(free_quote=D("10000")))
        assert decision.approved
        assert decision.rule is None

    def test_max_open_positions(self) -> None:
        portfolio = Portfolio(
            free_quote=D("1000"),
            positions={
                "ETHUSDT": long_position(symbol="ETHUSDT"),
                "BNBUSDT": long_position(symbol="BNBUSDT"),
            },
        )
        manager, _ = build_manager(
            config=risk_config(max_open_positions=2),
            provider=FakeProvider(
                candles={"ETHUSDT": candle(symbol="ETHUSDT"), "BNBUSDT": candle(symbol="BNBUSDT")}
            ),
            pairs=multi_pairs(SYMBOL, "ETHUSDT", "BNBUSDT"),
        )

        decision = manager.approve(buy(), portfolio=portfolio)
        assert not decision.approved
        assert decision.rule is RiskRule.MAX_OPEN_POSITIONS
        assert "2" in decision.reason

    def test_daily_loss_halt_and_its_release_at_the_next_utc_day(self) -> None:
        manager, clock = build_manager(config=risk_config(max_daily_loss_percent="5.0"))
        portfolio = Portfolio(free_quote=D("10000"))
        portfolio.record_realised_pnl(D("-500"), now=NOW)

        halted = manager.approve(buy(), portfolio=portfolio)
        assert not halted.approved
        assert halted.rule is RiskRule.DAILY_LOSS_HALT

        # Still the same UTC day 11 hours on: still halted.
        clock.advance(hours=11)
        assert not manager.approve(buy(), portfolio=portfolio).approved

        # Past midnight UTC the ledger rolls and trading resumes.
        clock.advance(hours=2)
        assert manager.approve(buy(), portfolio=portfolio).approved

    def test_cooldown(self) -> None:
        manager, clock = build_manager(config=risk_config(cooldown_minutes=15))
        portfolio = Portfolio(free_quote=D("10000"))
        portfolio.start_cooldown(SYMBOL, now=NOW, minutes=15)

        blocked = manager.approve(buy(), portfolio=portfolio)
        assert not blocked.approved
        assert blocked.rule is RiskRule.COOLDOWN

        clock.advance(minutes=15)
        assert manager.approve(buy(), portfolio=portfolio).approved

    def test_already_in_position(self) -> None:
        manager, _ = build_manager()
        portfolio = Portfolio(free_quote=D("10000"), positions={SYMBOL: long_position()})
        decision = manager.approve(buy(), portfolio=portfolio)
        assert not decision.approved
        assert decision.rule is RiskRule.ALREADY_IN_POSITION

    def test_unmarkable_position_blocks_rather_than_raising(self) -> None:
        """Equity is unknown, so no limit can be evaluated -- but the path runs
        on every signal, so it refuses instead of raising."""
        manager, _ = build_manager(
            provider=FakeProvider(candles={SYMBOL: None}),
            pairs={SYMBOL: PairContext(timeframe=TIMEFRAME, symbol_info=symbol_info())},
        )
        portfolio = Portfolio(free_quote=D("10000"), positions={SYMBOL: long_position()})
        decision = manager.approve(buy(), portfolio=portfolio)
        assert not decision.approved
        assert decision.rule is RiskRule.NO_MARK_PRICE

    def test_zero_equity(self) -> None:
        manager, _ = build_manager()
        decision = manager.approve(buy(), portfolio=Portfolio(free_quote=D("0")))
        assert not decision.approved
        assert decision.rule is RiskRule.NO_EQUITY

    @pytest.mark.parametrize(
        ("rule", "portfolio_factory"),
        [
            (
                RiskRule.DAILY_LOSS_HALT,
                lambda: _with_loss(Portfolio(free_quote=D("10000")), D("-9999")),
            ),
            (
                RiskRule.ALREADY_IN_POSITION,
                lambda: Portfolio(free_quote=D("10000"), positions={SYMBOL: long_position()}),
            ),
            (
                RiskRule.COOLDOWN,
                lambda: _with_cooldown(Portfolio(free_quote=D("10000"))),
            ),
        ],
    )
    def test_every_rejection_names_the_rule_that_fired(
        self, rule: RiskRule, portfolio_factory: Callable[[], Portfolio]
    ) -> None:
        """A refusal an operator cannot act on is the failure RiskDecision
        exists to prevent: the rule and a human-readable reason, always."""
        manager, _ = build_manager()
        decision = manager.approve(buy(), portfolio=portfolio_factory())
        assert not decision.approved
        assert decision.rule is rule
        assert decision.reason


def _with_loss(portfolio: Portfolio, amount: Decimal) -> Portfolio:
    portfolio.record_realised_pnl(amount, now=NOW)
    return portfolio


def _with_cooldown(portfolio: Portfolio) -> Portfolio:
    portfolio.start_cooldown(SYMBOL, now=NOW, minutes=30)
    return portfolio


# --------------------------------------------------------------------------
# The ATR bridge -- warmup must never hand a NaN to rules.py
# --------------------------------------------------------------------------
class TestAtrBridge:
    def atr_config(self, *, period: int = 14, multiplier: str = "2.0") -> RiskConfig:
        return risk_config(
            stop_loss=StopLossConfig(
                type=StopType.ATR, atr_period=period, atr_multiplier=D(multiplier)
            ),
            take_profit=TakeProfitConfig(enabled=False),
        )

    def test_atr_stop_uses_the_computed_atr(self) -> None:
        """A constant 2.00 true range gives ATR 2.0, so a 2x stop sits 4 below
        entry. The ATR value crosses as a float and lands as an exact Decimal."""
        manager, _ = build_manager(
            config=self.atr_config(),
            provider=FakeProvider(frames={SYMBOL: ohlcv(50)}, candles={SYMBOL: candle()}),
        )
        assessment = manager.evaluate(buy("100.00"), portfolio=Portfolio(free_quote=D("10000")))

        assert assessment.approved
        assert assessment.levels is not None
        assert assessment.levels.stop_loss == D("96.00")
        assert assessment.levels.stop_distance == D("4.00")

    def test_warmup_refuses_without_raising(self) -> None:
        """ATR needs period + 1 bars; rules.py raises on a non-finite ATR, so
        the bridge must gate rather than pass a NaN across."""
        manager, _ = build_manager(
            config=self.atr_config(period=14),
            provider=FakeProvider(frames={SYMBOL: ohlcv(14)}, candles={SYMBOL: candle()}),
        )
        assessment = manager.evaluate(buy(), portfolio=Portfolio(free_quote=D("10000")))

        assert not assessment.approved
        assert "atr" in assessment.reason.lower()
        # It got past the limits: this is a data-readiness refusal, not a limit.
        assert assessment.decision is not None
        assert assessment.decision.approved
        assert assessment.levels is None

    def test_one_more_bar_clears_warmup(self) -> None:
        manager, _ = build_manager(
            config=self.atr_config(period=14),
            provider=FakeProvider(frames={SYMBOL: ohlcv(15)}, candles={SYMBOL: candle()}),
        )
        assert manager.evaluate(buy(), portfolio=Portfolio(free_quote=D("10000"))).approved

    def test_a_gap_after_warmup_is_caught_by_the_finiteness_check(self) -> None:
        """Bar count alone is not sufficient: the indicator re-masks NaN inputs
        after the seed, so one bad tick yields a NaN long past warmup.

        The NaN goes on the final bar's ``high``, which enters that bar's own
        true range. A NaN *close* would not do it -- true range compares against
        the *previous* close, so a bad close only poisons the following bar.
        """
        frame = ohlcv(50)
        frame.iloc[-1, frame.columns.get_loc("high")] = np.nan
        manager, _ = build_manager(
            config=self.atr_config(),
            provider=FakeProvider(frames={SYMBOL: frame}, candles={SYMBOL: candle()}),
        )
        assessment = manager.evaluate(buy(), portfolio=Portfolio(free_quote=D("10000")))

        assert not assessment.approved
        assert "atr" in assessment.reason.lower()

    def test_a_percent_stop_never_inherits_the_atr_warmup_gate(self) -> None:
        """No ATR is needed, so an empty buffer must not block the entry."""
        manager, _ = build_manager(
            provider=FakeProvider(frames={SYMBOL: ohlcv(0)}, candles={SYMBOL: candle()})
        )
        assert manager.evaluate(buy(), portfolio=Portfolio(free_quote=D("10000"))).approved


# --------------------------------------------------------------------------
# A None stop: disabled (intended) vs sub-tick (transient)
# --------------------------------------------------------------------------
class TestNoPlaceableStop:
    @pytest.mark.parametrize(
        "method",
        [
            PositionSizingMethod.FIXED_FRACTION,
            PositionSizingMethod.FIXED_AMOUNT,
            PositionSizingMethod.RISK_PER_TRADE,
        ],
    )
    def test_sub_tick_stop_skips_the_entry_for_every_sizing_method(
        self, method: PositionSizingMethod
    ) -> None:
        """A 0.1% stop on a 1.00 tick collapses onto entry. The operator asked
        for a stop, so no method enters without one -- and this is also what
        keeps a None stop away from the sizer's contract check, which raises."""
        manager, _ = build_manager(
            config=risk_config(
                method=method,
                stop_loss=StopLossConfig(percent=D("0.1")),
                take_profit=TakeProfitConfig(enabled=False),
            ),
            pairs={
                SYMBOL: PairContext(timeframe=TIMEFRAME, symbol_info=symbol_info(price_tick="1.00"))
            },
        )
        assessment = manager.evaluate(buy("100"), portfolio=Portfolio(free_quote=D("10000")))

        assert not assessment.approved
        assert "not entering unprotected" in assessment.reason
        assert assessment.levels is not None
        assert assessment.levels.stop_loss is None
        assert assessment.sizing is None  # refused before sizing

    @pytest.mark.parametrize(
        "method",
        [PositionSizingMethod.FIXED_FRACTION, PositionSizingMethod.FIXED_AMOUNT],
    )
    def test_a_disabled_stop_is_an_instruction_and_is_honoured(
        self, method: PositionSizingMethod
    ) -> None:
        """Stops off is the operator's explicit choice, not a transient state,
        so the entry proceeds unprotected."""
        manager, _ = build_manager(
            config=risk_config(
                method=method,
                stop_loss=StopLossConfig(enabled=False),
                take_profit=TakeProfitConfig(type=TakeProfitType.PERCENT),
            )
        )
        assessment = manager.evaluate(buy(), portfolio=Portfolio(free_quote=D("10000")))

        assert assessment.approved
        assert assessment.levels is not None
        assert assessment.levels.stop_loss is None
        assert assessment.levels.take_profit == D("104.00")

    def test_risk_per_trade_with_stops_disabled_is_rejected_at_config_load(self) -> None:
        """The combination never reaches the manager: it fails fast at startup,
        which is why the sizer's raise stays a contract check rather than a
        condition the live path has to handle."""
        with pytest.raises(ValidationError, match="risk_per_trade"):
            risk_config(
                method=PositionSizingMethod.RISK_PER_TRADE,
                stop_loss=StopLossConfig(enabled=False),
                take_profit=TakeProfitConfig(enabled=False),
            )


# --------------------------------------------------------------------------
# evaluate: preconditions, sizing refusals, affordability, exits
# --------------------------------------------------------------------------
class TestEvaluate:
    def test_unknown_pair_is_refused(self) -> None:
        manager, _ = build_manager()
        assessment = manager.evaluate(
            buy(symbol="DOGEUSDT"), portfolio=Portfolio(free_quote=D("10000"))
        )
        assert not assessment.approved
        assert "DOGEUSDT" in assessment.reason

    def test_a_signal_without_a_price_is_refused(self) -> None:
        """Every level and size derives from it, and Signal.price is optional."""
        manager, _ = build_manager()
        signal = Signal(symbol=SYMBOL, action=SignalAction.BUY, timestamp=NOW)
        assessment = manager.evaluate(signal, portfolio=Portfolio(free_quote=D("10000")))
        assert not assessment.approved
        assert "reference price" in assessment.reason

    def test_sell_is_unreachable_on_spot(self) -> None:
        manager, _ = build_manager()
        signal = Signal(symbol=SYMBOL, action=SignalAction.SELL, price=D("100"), timestamp=NOW)
        assessment = manager.evaluate(signal, portfolio=Portfolio(free_quote=D("10000")))
        assert not assessment.approved
        assert "short" in assessment.reason

    def test_too_small_to_trade_carries_the_sizing_reason(self) -> None:
        """A tiny account is a routine outcome, not an error -- and the refusal
        is the sizer's own explanation, not a paraphrase."""
        manager, _ = build_manager(
            pairs={
                SYMBOL: PairContext(
                    timeframe=TIMEFRAME, symbol_info=symbol_info(min_notional="5000")
                )
            }
        )
        assessment = manager.evaluate(buy(), portfolio=Portfolio(free_quote=D("500")))

        assert not assessment.approved
        assert assessment.sizing is not None
        assert not assessment.sizing.is_tradeable
        assert assessment.reason == assessment.sizing.reason
        assert "min_notional" in assessment.reason

    def test_an_unaffordable_order_is_refused(self) -> None:
        """Equity is total value; free balance is what can be spent. The sizer
        documents that confirming the difference is the caller's job.

        Equity here is 10050 -- almost all of it already deployed in ETHUSDT --
        so the fixed 100-quote order sizes cleanly and is still unaffordable.
        """
        manager, _ = build_manager(
            config=risk_config(method=PositionSizingMethod.FIXED_AMOUNT),
            provider=FakeProvider(candles={"ETHUSDT": candle(symbol="ETHUSDT")}),
            pairs=multi_pairs(SYMBOL, "ETHUSDT"),
        )
        portfolio = Portfolio(
            free_quote=D("50"),
            positions={"ETHUSDT": long_position(symbol="ETHUSDT", quantity="100", entry="100")},
        )
        assessment = manager.evaluate(buy(), portfolio=portfolio)

        assert not assessment.approved
        assert "is free" in assessment.reason
        assert assessment.sizing is not None
        assert assessment.sizing.is_tradeable  # sizing succeeded; the balance did not

    def test_close_produces_an_exit_intent_bypassing_the_limits(self) -> None:
        """An exit is not a new risk. A limit that could trap an open position
        would be a risk rule that creates risk."""
        manager, _ = build_manager(config=risk_config(max_open_positions=1))
        portfolio = Portfolio(free_quote=D("0"), positions={SYMBOL: long_position(quantity="0.75")})
        portfolio.start_cooldown(SYMBOL, now=NOW, minutes=60)
        portfolio.record_realised_pnl(D("-99999"), now=NOW)

        signal = Signal(symbol=SYMBOL, action=SignalAction.CLOSE, price=D("123.45"), timestamp=NOW)
        assessment = manager.evaluate(signal, portfolio=portfolio)

        assert assessment.approved
        assert assessment.intent is not None
        assert assessment.intent.side is OrderSide.SELL
        assert assessment.intent.quantity == D("0.75")
        assert assessment.intent.levels is None

    def test_close_with_nothing_open_is_refused(self) -> None:
        manager, _ = build_manager()
        signal = Signal(symbol=SYMBOL, action=SignalAction.CLOSE, price=D("100"), timestamp=NOW)
        assessment = manager.evaluate(signal, portfolio=Portfolio(free_quote=D("1000")))
        assert not assessment.approved
        assert "nothing to close" in assessment.reason

    def test_an_approval_reports_no_stage(self) -> None:
        """The approval half of the stage invariant, through the real path.

        The log-schema test asserting `"stage" not in fields` sits downstream of
        IntentLogger's early return, which never reads `stage` -- it passes
        whatever the domain does. This one goes through evaluate.

        Pins evaluate's *behaviour*. The validator's raise is a separate claim
        with its own test in TestMoneyGuard; neither implies the other.
        """
        manager, _ = build_manager()
        assessment = manager.evaluate(buy("100.00"), portfolio=Portfolio(free_quote=D("10000")))

        assert assessment.approved
        assert assessment.stage is None


# --------------------------------------------------------------------------
# Exits: the pure predicate, driven with a deliberate price
# --------------------------------------------------------------------------
class TestExits:
    def test_check_exit_uses_the_bar_close_not_its_low(self) -> None:
        """The bot reacts at bar close and fills near it. Triggering on the low
        would claim a fill at a price that has already gone."""
        manager, _ = build_manager()
        position = long_position(stop_loss=D("98"))

        # Low pierces the stop but the bar closed above it: no exit yet.
        pierced = Candle(
            symbol=SYMBOL,
            timeframe=TIMEFRAME,
            open_time=NOW,
            close_time=NOW,
            open=D("100"),
            high=D("100"),
            low=D("97"),
            close=D("99"),
            volume=D("1"),
        )
        assert manager.check_exit(position, pierced) is None

        assert manager.check_exit(position, candle("97.5")) is not None

    def test_a_stop_beats_the_take_profit_on_one_bar(self) -> None:
        manager, _ = build_manager()
        position = long_position(stop_loss=D("98"), take_profit=D("104"))
        decision = manager.check_exit(position, candle("97"))
        assert decision is not None
        assert decision.reason is ExitReason.STOP_LOSS
        assert decision.price == D("98")

    def test_advance_trailing_stop_stores_the_new_state(self) -> None:
        manager, _ = build_manager(
            config=risk_config(
                trailing_stop=TrailingStopConfig(
                    enabled=True, activation_percent=D("1.0"), trail_percent=D("1.0")
                )
            )
        )
        position = long_position(entry="100")

        update = manager.advance_trailing_stop(position, candle("110"))
        assert update is not None
        assert update.activated
        assert position.highest_price == D("110")
        assert position.trailing_stop == D("108.90")

        # A lower close cannot drag the stop back down.
        manager.advance_trailing_stop(position, candle("105"))
        assert position.highest_price == D("110")
        assert position.trailing_stop == D("108.90")

    def test_trailing_disabled_returns_none_and_touches_nothing(self) -> None:
        manager, _ = build_manager()
        position = long_position()
        assert manager.advance_trailing_stop(position, candle("110")) is None
        assert position.trailing_stop is None
        assert position.highest_price is None


# --------------------------------------------------------------------------
# M1 + M2 + M3 composed, end to end
# --------------------------------------------------------------------------
class TestComposedPath:
    def test_realised_risk_at_the_stop_equals_the_configured_budget(self) -> None:
        """The end-to-end invariant the whole milestone exists to produce:
        quantity * realised stop distance <= equity * risk_per_trade.

        Realised, not configured: the stop that matters is the one after
        directional rounding, which is why ProtectiveLevels carries the distance
        rather than letting sizing recompute it.
        """
        config = risk_config(method=PositionSizingMethod.RISK_PER_TRADE)
        manager, _ = build_manager(config=config)
        portfolio = Portfolio(free_quote=D("10000"))

        assessment = manager.evaluate(buy("100.00"), portfolio=portfolio)

        assert assessment.approved
        assert assessment.intent is not None
        assert assessment.levels is not None
        assert assessment.levels.stop_distance is not None

        budget = D("10000") * config.position_sizing.risk_per_trade
        realised = assessment.intent.quantity * assessment.levels.stop_distance
        assert realised == budget == D("100")
        assert assessment.intent.quantity == D("50")
        assert assessment.levels.stop_loss == D("98.00")

    def test_an_awkward_tick_keeps_realised_risk_inside_the_budget(self) -> None:
        """On a tick that does not divide the stop distance the stop rounds
        *toward entry*, so the realised risk can only come in under budget --
        never over it."""
        config = risk_config(method=PositionSizingMethod.RISK_PER_TRADE)
        manager, _ = build_manager(
            config=config,
            pairs={
                SYMBOL: PairContext(timeframe=TIMEFRAME, symbol_info=symbol_info(price_tick="0.13"))
            },
        )
        assessment = manager.evaluate(buy("100"), portfolio=Portfolio(free_quote=D("10000")))

        assert assessment.approved
        assert assessment.intent is not None
        assert assessment.levels is not None
        assert assessment.levels.stop_loss == D("98.02")  # rounded up, toward entry
        assert assessment.levels.stop_distance is not None

        budget = D("10000") * config.position_sizing.risk_per_trade
        realised = assessment.intent.quantity * assessment.levels.stop_distance
        assert realised <= budget

    def test_the_position_cap_binds_before_the_sizing_method(self) -> None:
        config = risk_config(
            method=PositionSizingMethod.RISK_PER_TRADE, max_position_size_percent="20"
        )
        manager, _ = build_manager(config=config)
        assessment = manager.evaluate(buy("100.00"), portfolio=Portfolio(free_quote=D("10000")))

        assert assessment.approved
        assert assessment.intent is not None
        # 20% of 10000 equity at 100 == 20 units, below the method's own 50.
        assert assessment.intent.quantity == D("20")
        assert assessment.sizing is not None
        assert "capped" in assessment.sizing.reason


# --------------------------------------------------------------------------
# Structural: no result can be built from a float
# --------------------------------------------------------------------------
class TestMoneyGuard:
    def test_trade_intent_rejects_a_float_quantity(self) -> None:
        with pytest.raises(ValidationError, match="must not be built from a float"):
            TradeIntent(symbol=SYMBOL, side=OrderSide.BUY, quantity=1.5, price=D("100"))  # type: ignore[arg-type]

    def test_trade_intent_rejects_a_numpy_float(self) -> None:
        """numpy.float64 is what DataFrame.iloc hands back -- the realistic leak
        path, and a float subclass, so the same guard catches it."""
        with pytest.raises(ValidationError, match="must not be built from a float"):
            TradeIntent(
                symbol=SYMBOL,
                side=OrderSide.BUY,
                quantity=np.float64(1.5),  # type: ignore[arg-type]
                price=D("100"),
            )

    def test_an_intent_must_carry_a_positive_quantity(self) -> None:
        """'Do not trade' is an assessment with no intent, never a zero-size one."""
        with pytest.raises(ValidationError, match="positive quantity"):
            TradeIntent(symbol=SYMBOL, side=OrderSide.BUY, quantity=D("0"), price=D("100"))

    def test_levels_must_match_the_intent_they_protect(self) -> None:
        manager, _ = build_manager()
        assessment = manager.evaluate(buy("100.00"), portfolio=Portfolio(free_quote=D("10000")))
        assert assessment.intent is not None
        assert assessment.intent.levels is not None

        with pytest.raises(ValidationError, match="priced at"):
            TradeIntent(
                symbol=SYMBOL,
                side=OrderSide.BUY,
                quantity=D("1"),
                price=D("999"),
                levels=assessment.intent.levels,
            )

    def test_a_risk_decision_refusal_must_name_a_rule(self) -> None:
        with pytest.raises(ValidationError, match="must name the rule"):
            RiskDecision(symbol=SYMBOL, approved=False, reason="because")

    def test_a_risk_decision_approval_must_not_name_a_rule(self) -> None:
        with pytest.raises(ValidationError, match="must name the rule"):
            RiskDecision(symbol=SYMBOL, approved=True, reason="fine", rule=RiskRule.COOLDOWN)

    def test_a_risk_assessment_stage_must_agree_with_its_verdict(self) -> None:
        """Both directions of the invariant mirroring `rule` two tests above --
        and the two places RiskAssessment cannot mirror RiskDecision's shape.

        `stage` is **required**, so the refusal direction passes ``None``
        explicitly: omitting it raises pydantic's own ``missing`` and never
        reaches this validator, where `rule`'s default of ``None`` lets the
        sibling above omit it.

        The approval direction needs a real intent, because `_check_invariants`
        binds `intent` to `approved` *first* -- without one it refuses for the
        wrong reason and this test would pass on the wrong error.
        """
        with pytest.raises(ValidationError, match="must name the stage"):
            RiskAssessment(symbol=SYMBOL, approved=False, reason="because", stage=None)

        with pytest.raises(ValidationError, match="must name the stage"):
            RiskAssessment(
                symbol=SYMBOL,
                approved=True,
                reason="fine",
                stage=RefusalStage.LIMIT_REFUSED,
                intent=TradeIntent(
                    symbol=SYMBOL, side=OrderSide.BUY, quantity=D("1"), price=D("100")
                ),
            )
