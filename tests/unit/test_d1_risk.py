"""The D1 risk manager (N5): the unchanged ``RiskManager`` sized from each signal's own clamped trail.

Hermetic, on synthetic fixtures: an injected clock, a scripted provider and a plain pairs mapping. The
base ``RiskManager`` is not under test and is not read here for its own sake; what is pinned is that
``D1RiskManager`` hands it a percent stop equal to the signal's delta and nothing else, so 1 percent of
equity is risked at the clamped trail, and that every rule the base class applies still refuses.

Worked numbers, all exact ``Decimal`` (the money rule), on a 0.01 tick, a 0.001 step, equity 10,000
and a signal close of 100.00. The entry limit is the close widened by the 0.1 percent entry tolerance
and rounded UP to the tick: 100.10. The stop is rounded TOWARD the entry. Risk is 1 percent of equity,
100; the cap is 20 percent of equity, 2,000 of notional, 19.98 units at the limit.

* delta 2000 (the upper bound): stop at 100.10 x 0.80 = 80.08, distance 20.02, quantity 100 / 20.02 =
  4.995004... rounded down to 4.995.
* delta 1000: stop 90.09, distance 10.01, quantity 9.990 (9.990009... rounded down).
* delta 10 (the lower bound): raw stop 99.9999 rounds up to 100.00, distance 0.10, requested 1000
  units, which the 20 percent cap cuts to 19.980.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime, timezone
from decimal import Decimal
from typing import ClassVar

import pandas as pd
import pytest

from trading_bot.backtesting.d1_executor import CAP_MARKER
from trading_bot.backtesting.d1_risk import D1RiskManager
from trading_bot.config.models import (
    PositionSizingConfig,
    RiskConfig,
    RiskLimitsConfig,
    StopLossConfig,
    TakeProfitConfig,
    TrailingStopConfig,
)
from trading_bot.core.assessment import EntryIntent
from trading_bot.core.enums import (
    PositionSide,
    PositionSizingMethod,
    ProtectionState,
    RefusalStage,
    RiskRule,
    SignalAction,
    StopType,
)
from trading_bot.core.interfaces import CandleHandler, MarketDataProvider
from trading_bot.core.models import Candle, Position, Signal, SymbolInfo
from trading_bot.core.portfolio import Portfolio
from trading_bot.risk.manager import PairContext, RiskManager

D = Decimal
NOW = datetime(2026, 7, 25, 12, 0, tzinfo=timezone.utc)
BTC = "BTCUSDT"
ETH = "ETHUSDT"


class ScriptedProvider(MarketDataProvider):
    """Serves the last candle of each symbol and nothing else; the manager reads nothing more here."""

    def __init__(self, closes: Mapping[str, str]) -> None:
        self._candles = {symbol: candle(symbol, close) for symbol, close in closes.items()}

    def track(self, symbol: str, timeframe: str) -> None:
        pass

    def on_candle(self, handler: CandleHandler) -> None:
        pass

    async def start(self) -> None:
        pass

    async def stop(self) -> None:
        pass

    def get_dataframe(self, symbol: str, timeframe: str) -> pd.DataFrame:
        return pd.DataFrame()

    def candle_count(self, symbol: str, timeframe: str) -> int:
        return 0

    def last_candle(self, symbol: str, timeframe: str) -> Candle | None:
        return self._candles.get(symbol)

    def bars_since_gap(self, symbol: str, timeframe: str) -> int | None:
        return None


def candle(symbol: str, close: str) -> Candle:
    return Candle(
        symbol=symbol,
        timeframe="1d",
        open_time=NOW,
        close_time=NOW,
        open=D(close),
        high=D(close),
        low=D(close),
        close=D(close),
        volume=D("1"),
    )


def info(symbol: str) -> SymbolInfo:
    return SymbolInfo(
        symbol=symbol,
        base_asset=symbol[:3],
        quote_asset="USDT",
        price_tick=D("0.01"),
        step_size=D("0.001"),
        min_qty=D("0.001"),
        min_notional=D("10"),
    )


def config(
    *,
    stops: bool = True,
    max_open_positions: int = 3,
    stop_type: StopType = StopType.PERCENT,
) -> RiskConfig:
    """The N5 shape: ``risk_per_trade`` at 1 percent, a percent stop whose 20.0 is only a placeholder,
    and every other setting at its default (cap 20, daily loss 5, cooldown 15, entry tolerance 0.001)."""
    return RiskConfig(
        position_sizing=PositionSizingConfig(
            method=PositionSizingMethod.RISK_PER_TRADE
            if stops
            else PositionSizingMethod.FIXED_FRACTION,
            risk_per_trade=D("0.01"),
            fraction=D("0.02"),
        ),
        stop_loss=StopLossConfig(enabled=stops, type=stop_type, percent=D("20.0")),
        take_profit=TakeProfitConfig(enabled=False),
        trailing_stop=TrailingStopConfig(enabled=False),
        limits=RiskLimitsConfig(max_open_positions=max_open_positions),
    )


def manager(
    cfg: RiskConfig | None = None, *, closes: Mapping[str, str] | None = None
) -> D1RiskManager:
    marks = {BTC: "100", ETH: "100"} if closes is None else closes
    return D1RiskManager(
        config=cfg or config(),
        provider=ScriptedProvider(marks),
        pairs={s: PairContext(timeframe="1d", symbol_info=info(s)) for s in (BTC, ETH)},
        clock=lambda: NOW,
    )


def buy(delta: object = 1000, *, symbol: str = BTC, price: str = "100.00") -> Signal:
    metadata: dict[str, object] = {"trail_clamp": "none"}
    if delta is not None:
        metadata["trail_delta_bps"] = delta
    return Signal(
        symbol=symbol,
        action=SignalAction.BUY,
        price=D(price),
        timestamp=NOW,
        metadata=metadata,
    )


def held(
    symbol: str = ETH,
    *,
    quantity: str = "10",
    entry: str = "100",
    stop: str | None = "90",
    protection: ProtectionState = ProtectionState.ACTIVE,
) -> Position:
    return Position(
        symbol=symbol,
        side=PositionSide.LONG,
        quantity=D(quantity),
        entry_price=D(entry),
        entry_fill_price=D(entry),
        entry_bar_time=NOW,
        protection=protection,
        opened_at=NOW,
        stop_loss=None if stop is None else D(stop),
        take_profit=None,
        last_reconciled_at=NOW,
    )


def flat_portfolio(free: str = "10000") -> Portfolio:
    return Portfolio(free_quote=D(free))


def entry(manager_: D1RiskManager, signal: Signal, portfolio: Portfolio) -> EntryIntent:
    assessment = manager_.evaluate(signal, portfolio=portfolio)
    assert assessment.approved, (assessment.stage, assessment.reason)
    assert isinstance(assessment.intent, EntryIntent)
    return assessment.intent


class TestOnePercentAtTheClampedTrail:
    def test_the_upper_bound_risks_one_percent_at_a_stop_twenty_percent_below(self) -> None:
        intent = entry(manager(), buy(2000), flat_portfolio())
        assert intent.entry_limit == D("100.10")
        assert intent.levels.stop_loss == D("80.08")
        assert intent.levels.stop_distance == D("20.02")
        assert intent.quantity == D("4.995")

    def test_a_middle_trail(self) -> None:
        intent = entry(manager(), buy(1000), flat_portfolio())
        assert intent.levels.stop_loss == D("90.09")
        assert intent.quantity == D("9.990")

    def test_the_lower_bound_is_cut_by_the_twenty_percent_position_cap(self) -> None:
        assessment = manager().evaluate(buy(10), portfolio=flat_portfolio())
        assert assessment.approved
        assert assessment.levels is not None
        assert assessment.levels.stop_loss == D("100.00")
        assert assessment.levels.stop_distance == D("0.10")
        assert assessment.sizing is not None
        # One percent of equity over a ten-cent stop is 1,000 units; the cap says 19.98.
        assert assessment.sizing.requested_quantity == D("1000")
        assert assessment.sizing.quantity == D("19.980")
        assert "capped at 20% of equity" in assessment.sizing.reason

    def test_the_loss_at_the_stop_is_at_most_one_percent_of_equity_when_the_cap_is_slack(
        self,
    ) -> None:
        for delta in (600, 1000, 1500, 2000):
            intent = entry(manager(), buy(delta), flat_portfolio())
            assert intent.levels.stop_loss is not None
            loss = intent.quantity * (intent.entry_limit - intent.levels.stop_loss)
            assert D("99") < loss <= D("100"), (delta, loss)

    def test_the_stop_is_the_signals_delta_and_not_the_placeholder(self) -> None:
        # The configured percent is 20.0, which is what delta 2000 means; 1000 must not see it.
        intent = entry(manager(), buy(1000), flat_portfolio())
        assert intent.levels.stop_distance == D("10.01")

    def test_the_stop_type_in_the_file_does_not_matter(self) -> None:
        by_atr = manager(config(stop_type=StopType.ATR))
        assert entry(by_atr, buy(1000), flat_portfolio()).levels.stop_loss == D("90.09")

    def test_a_delta_is_an_exact_decimal_percent(self) -> None:
        intent = entry(manager(), buy(1289, price="1000.00"), flat_portfolio())
        # 12.89 percent of 1001.00 is 129.0289; the raw stop 871.9711 rounds up to 871.98.
        assert intent.entry_limit == D("1001.00")
        assert intent.levels.stop_loss == D("871.98")


class TestTheQuoteBalanceRefusesAndDoesNotShrink:
    def test_a_size_the_free_quote_cannot_pay_for_is_refused_at_unaffordable(self) -> None:
        # Equity is 100 free plus a held ETH position worth 10,000 at its mark, so the 1 percent
        # risk is sized against 10,100 while only 100 can be spent.
        portfolio = Portfolio(free_quote=D("100"), positions={ETH: held(quantity="100", stop="99")})
        assessment = manager().evaluate(buy(2000), portfolio=portfolio)
        assert not assessment.approved
        assert assessment.stage is RefusalStage.UNAFFORDABLE
        assert assessment.sizing is not None
        assert assessment.sizing.quantity > 0
        assert assessment.intent is None

    def test_the_same_size_is_approved_when_the_cash_is_there(self) -> None:
        portfolio = Portfolio(free_quote=D("1000"), positions={ETH: held(quantity="90", stop="99")})
        intent = entry(manager(), buy(2000), portfolio)
        assert intent.quantity * intent.entry_limit <= D("1000")


class TestEveryRuleStillRefuses:
    def refusal(self, portfolio: Portfolio, cfg: RiskConfig | None = None) -> RiskRule:
        assessment = manager(cfg).evaluate(buy(1000), portfolio=portfolio)
        assert not assessment.approved
        assert assessment.stage is RefusalStage.LIMIT_REFUSED
        assert assessment.decision is not None
        assert assessment.decision.rule is not None
        return assessment.decision.rule

    def test_no_equity(self) -> None:
        assert self.refusal(flat_portfolio("0")) is RiskRule.NO_EQUITY

    def test_daily_loss_halt_from_realised_loss(self) -> None:
        portfolio = flat_portfolio()
        portfolio.record_realised_pnl(D("-600"), now=NOW)
        assert self.refusal(portfolio) is RiskRule.DAILY_LOSS_HALT

    def test_daily_loss_halt_from_committed_risk_alone_on_an_untrailed_stop(self) -> None:
        # M5n-091. ETH was bought at 100 with the stop at 90 and now marks at 200: nothing is
        # realised, nothing is lost, and the unmoved stop still commits (90 - 200) x 10 = -1,100
        # against a threshold of 5 percent of 11,000.
        portfolio = Portfolio(free_quote=D("9000"), positions={ETH: held()})
        assert portfolio.realised_today(NOW) == 0
        verdict = manager(closes={BTC: "100", ETH: "200"}).evaluate(buy(1000), portfolio=portfolio)
        assert verdict.decision is not None
        assert verdict.decision.rule is RiskRule.DAILY_LOSS_HALT

    def test_the_halt_is_checked_before_already_in_position(self) -> None:
        # M5n-126. BTC itself is held in the same state, and the refusal is the halt.
        portfolio = Portfolio(free_quote=D("9000"), positions={BTC: held(BTC), ETH: held(ETH)})
        marks = {BTC: "200", ETH: "200"}
        verdict = manager(closes=marks).evaluate(buy(1000, symbol=BTC), portfolio=portfolio)
        assert verdict.decision is not None
        assert verdict.decision.rule is RiskRule.DAILY_LOSS_HALT

    def test_already_in_position(self) -> None:
        portfolio = Portfolio(free_quote=D("9000"), positions={BTC: held(BTC)})
        assert self.refusal(portfolio) is RiskRule.ALREADY_IN_POSITION

    def test_cooldown(self) -> None:
        portfolio = flat_portfolio()
        portfolio.start_cooldown(BTC, now=NOW, minutes=15)
        assert self.refusal(portfolio) is RiskRule.COOLDOWN

    def test_max_open_positions(self) -> None:
        portfolio = Portfolio(free_quote=D("9000"), positions={ETH: held(ETH)})
        assert self.refusal(portfolio, config(max_open_positions=1)) is RiskRule.MAX_OPEN_POSITIONS

    def test_no_mark_price(self) -> None:
        portfolio = Portfolio(free_quote=D("9000"), positions={ETH: held(ETH)})
        verdict = manager(closes={BTC: "100"}).evaluate(buy(1000), portfolio=portfolio)
        assert verdict.stage is RefusalStage.NO_MARK_PRICE
        assert verdict.decision is not None
        assert verdict.decision.rule is RiskRule.NO_MARK_PRICE


class TestWhatItLeavesToTheBaseClass:
    def test_it_overrides_evaluate_and_nothing_else_of_the_base(self) -> None:
        # `_abc_impl` is the abstract-base machinery every subclass of an ABC carries.
        own = {name for name in vars(D1RiskManager) if not name.startswith(("__", "_abc"))}
        assert own == {"evaluate", "_manager_for"}
        assert issubclass(D1RiskManager, RiskManager)
        assert "__init__" in vars(D1RiskManager)

    def test_a_signal_without_a_delta_is_evaluated_by_the_base_configuration(self) -> None:
        # The placeholder 20.0 percent applies, because nothing replaced it.
        intent = entry(manager(), buy(None), flat_portfolio())
        assert intent.levels.stop_distance == D("20.02")

    @pytest.mark.parametrize("delta", [True, "1000", 1000.0])
    def test_only_an_integer_delta_is_a_delta(self, delta: object) -> None:
        intent = entry(manager(), buy(delta), flat_portfolio())
        assert intent.levels.stop_distance == D("20.02")

    def test_a_non_buy_is_evaluated_by_the_base_class(self) -> None:
        close = Signal(
            symbol=BTC,
            action=SignalAction.CLOSE,
            price=D("100"),
            timestamp=NOW,
            metadata={"trail_delta_bps": 1000},
        )
        assessment = manager().evaluate(close, portfolio=flat_portfolio())
        assert assessment.stage is RefusalStage.NOTHING_TO_CLOSE

    def test_with_stops_off_it_is_the_base_manager_exactly(self) -> None:
        cfg = config(stops=False)
        portfolio = flat_portfolio()
        ours = manager(cfg).evaluate(buy(1000), portfolio=portfolio)
        base = RiskManager(
            config=cfg,
            provider=ScriptedProvider({BTC: "100", ETH: "100"}),
            pairs={s: PairContext(timeframe="1d", symbol_info=info(s)) for s in (BTC, ETH)},
            clock=lambda: NOW,
        ).evaluate(buy(1000), portfolio=portfolio)
        assert ours == base
        assert ours.intent is not None
        assert ours.intent.quantity == D("1.998")

    @pytest.mark.parametrize("delta", [0, -5])
    def test_a_delta_that_is_not_a_distance_raises(self, delta: int) -> None:
        with pytest.raises(ValueError, match="not a distance below the entry"):
            manager().evaluate(buy(delta), portfolio=flat_portfolio())

    def test_one_manager_is_kept_per_delta(self) -> None:
        the_manager = manager()
        first = the_manager._manager_for(1000)
        assert the_manager._manager_for(1000) is first
        assert the_manager._manager_for(1001) is not first
        assert type(first) is RiskManager


class TestTheCapMarkerIsTheManagersOwn:
    """R-DT-3f. The executor counts a capped entry by a marker in the sizing reason, because the
    unchanged manager exposes no flag; these call the REAL sizer so the marker cannot drift from it."""

    def test_the_marker_is_in_the_reason_when_the_cap_binds(self) -> None:
        assessment = manager().evaluate(buy(10), portfolio=flat_portfolio())
        assert assessment.sizing is not None
        assert CAP_MARKER in assessment.sizing.reason
        assert assessment.sizing.requested_quantity > assessment.sizing.quantity

    def test_the_marker_is_absent_when_it_does_not(self) -> None:
        for delta in (600, 1000, 2000):
            assessment = manager().evaluate(buy(delta), portfolio=flat_portfolio())
            assert assessment.sizing is not None
            assert CAP_MARKER not in assessment.sizing.reason, delta

    def test_a_delta_of_exactly_five_hundred_binds_on_the_tick(self) -> None:
        """The stop rounds toward the entry, shrinking the distance below 5 percent, so the 1 percent
        risk asks for a hair over 20 percent of equity: delta 500 is capped and 501 is not."""
        at = manager().evaluate(buy(500), portfolio=flat_portfolio())
        above = manager().evaluate(buy(501), portfolio=flat_portfolio())
        assert at.sizing is not None and above.sizing is not None
        assert CAP_MARKER in at.sizing.reason
        assert CAP_MARKER not in above.sizing.reason


class TestTheManagersHoldNoStateThatEvaluateChanges:
    """P146 step 1 (M5n-152): the owner's acceptance of D1RiskManager rests on this, so it is pinned."""

    ATTRIBUTES: ClassVar[set[str]] = {"_config", "_provider", "_pairs", "_clock"}

    @staticmethod
    def snapshot(
        target: RiskManager,
    ) -> tuple[dict[str, int], dict[str, object], dict[str, object]]:
        identities = {name: id(value) for name, value in vars(target).items()}
        return identities, dict(target._pairs), target._config.model_dump()

    def scenarios(self) -> list[tuple[Portfolio, str]]:
        halted = Portfolio(free_quote=D("9000"), positions={ETH: held()})
        realised = flat_portfolio()
        realised.record_realised_pnl(D("-600"), now=NOW)
        cooling = flat_portfolio()
        cooling.start_cooldown(BTC, now=NOW, minutes=15)
        return [
            (flat_portfolio(), "100"),
            (flat_portfolio("0"), "100"),
            (halted, "200"),
            (Portfolio(free_quote=D("9000"), positions={BTC: held(BTC)}), "100"),
            (realised, "100"),
            (cooling, "100"),
            (flat_portfolio(), "100"),
        ]

    def test_a_plain_manager_changes_nothing_across_every_kind_of_verdict(self) -> None:
        for portfolio, eth_close in self.scenarios():
            target = RiskManager(
                config=config(),
                provider=ScriptedProvider({BTC: "100", ETH: eth_close}),
                pairs={s: PairContext(timeframe="1d", symbol_info=info(s)) for s in (BTC, ETH)},
                clock=lambda: NOW,
            )
            before = self.snapshot(target)
            assert set(vars(target)) == self.ATTRIBUTES
            for _ in range(3):
                target.evaluate(buy(1000), portfolio=portfolio)
            target.evaluate(buy(None), portfolio=portfolio)
            assert self.snapshot(target) == before
            assert set(vars(target)) == self.ATTRIBUTES

    def test_the_per_delta_instances_differ_only_in_the_stop(self) -> None:
        base = manager()
        before = self.snapshot(base)[2]
        for delta in (10, 1000, 2000):
            base.evaluate(buy(delta), portfolio=flat_portfolio())
        assert set(base._by_delta) == {10, 1000, 2000}
        for delta, instance in base._by_delta.items():
            assert set(vars(instance)) == self.ATTRIBUTES
            assert instance._provider is base._provider
            assert instance._clock is base._clock
            assert instance._pairs == base._pairs
            assert all(instance._pairs[s] is base._pairs[s] for s in base._pairs)
            shared = [f for f in type(base._config).model_fields if f != "stop_loss"]
            assert all(getattr(instance._config, f) is getattr(base._config, f) for f in shared)
            assert instance._config.stop_loss.percent == D(delta) / D(100)
        # and the base configuration, placeholder included, is exactly as it was
        assert base._config.model_dump() == before
        assert base._config.stop_loss.percent == D("20.0")
