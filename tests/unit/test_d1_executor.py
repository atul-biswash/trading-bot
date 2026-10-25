"""The D1 executor (N4b): an entry fills on the next decision bar, the trail is walked over the traded
1m minutes from that bar, and the exit is booked when the simulated clock reaches it.

Every figure is worked by hand from one setup: fee 0.10% a leg, no entry slippage, stop slippage 1.00%,
an order of 0.5, a limit of 100.10, and a trail of 500 basis points from a fill at 100. The entry
costs 50 + 0.05 = 50.05 and leaves 9949.95 free; the initial stop is 95. A trail that triggers at 95
sells at 95 x 0.99 = 94.05, gross 47.025, fee 0.047025, realised 47.025 - 50.05 - 0.047025 =
-3.072025. Decision bars are 4h, the signal bar opens at 00:00 and the entry bar at 04:00; minute
``n`` of the 1m store is ``n`` minutes after 00:00, so the entry bar is minutes 240 to 479.
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping, Sequence
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from tests.unit.d1_world import Minute, at, build_minutes, flat
from trading_bot.backtesting import d1_executor
from trading_bot.backtesting.d1_executor import D1Executor, D1ExecutorError, SymbolTally
from trading_bot.backtesting.fill_model import FillParameters
from trading_bot.backtesting.simulated_executor import (
    EntryResult,
    SimulatedExit,
    trade_log_digest,
)
from trading_bot.core.assessment import EntryIntent, ExitIntent, RiskAssessment
from trading_bot.core.enums import (
    PositionSide,
    ProtectionState,
    RefusalStage,
    RiskRule,
    SignalAction,
)
from trading_bot.core.interfaces import Dispatcher
from trading_bot.core.models import Candle, Position, ProtectiveLevels, RiskDecision, Signal
from trading_bot.core.portfolio import Portfolio
from trading_bot.data.historical import HistoricalStore
from trading_bot.strategies.m5n import trail

D = Decimal
FOUR_HOURS = timedelta(hours=4)
PARAMS = FillParameters(fee_percent=D("0.1"), slippage_percent=D("0"), stop_slippage_percent=D("1"))
FREE = D(10000)
WINDOW_END = at(720)
DROP: Minute = ("100", "100", "94", "95", "1")


def bar(hour: int, *, symbol: str = "BTCUSDT", open: str = "100") -> Candle:
    opened = at(hour * 60)
    return Candle(
        symbol=symbol,
        timeframe="4h",
        open_time=opened,
        close_time=opened + FOUR_HOURS - timedelta(milliseconds=1),
        open=D(open),
        high=D(open),
        low=D(open),
        close=D(open),
        volume=D(1),
    )


def entry_assessment(symbol: str = "BTCUSDT", *, limit: str = "100.10") -> RiskAssessment:
    levels = ProtectiveLevels(
        symbol=symbol,
        side=PositionSide.LONG,
        entry_price=D(limit),
        stop_loss=None,
        take_profit=None,
        stop_distance=None,
        basis="test",
    )
    intent = EntryIntent(
        symbol=symbol,
        quantity=D("0.5"),
        reference_price=D("100"),
        entry_limit=D(limit),
        levels=levels,
    )
    return RiskAssessment(
        symbol=symbol, approved=True, reason="approved", stage=None, intent=intent
    )


def refused(stage: RefusalStage, symbol: str = "BTCUSDT") -> RiskAssessment:
    return RiskAssessment(symbol=symbol, approved=False, reason="refused", stage=stage)


def refused_by(
    rule: RiskRule, symbol: str = "BTCUSDT", *, stage: RefusalStage = RefusalStage.LIMIT_REFUSED
) -> RiskAssessment:
    """A refusal that names the rule that fired, as the manager's limit check and mark check do."""
    decision = RiskDecision(symbol=symbol, approved=False, reason="refused", rule=rule)
    return RiskAssessment(
        symbol=symbol, approved=False, reason="refused", stage=stage, decision=decision
    )


def refused_after_the_limits(stage: RefusalStage, symbol: str = "BTCUSDT") -> RiskAssessment:
    """A refusal after the limits passed (sizing, affordability): a decision with no rule."""
    decision = RiskDecision(symbol=symbol, approved=True, reason="within all risk limits")
    return RiskAssessment(
        symbol=symbol, approved=False, reason="refused", stage=stage, decision=decision
    )


def signal_for(
    candle: Candle,
    *,
    delta: object = 500,
    clamp: str = "none",
    action: SignalAction = SignalAction.BUY,
) -> Signal:
    metadata: dict[str, Any] = {"trail_clamp": clamp}
    if delta is not None:
        metadata["trail_delta_bps"] = delta
    return Signal(
        symbol=candle.symbol,
        action=action,
        timestamp=candle.close_time,
        price=candle.close,
        metadata=metadata,
    )


class SpyStore(HistoricalStore):
    """Records every window the executor asks the store for."""

    def __init__(self, root: Path) -> None:
        super().__init__(root)
        self.asked: list[tuple[str, str, datetime, datetime]] = []

    def candles(
        self, symbol: str, interval: str, start: datetime, end: datetime
    ) -> Iterator[Candle]:
        self.asked.append((symbol, interval, start, end))
        return super().candles(symbol, interval, start, end)


class Rig:
    """An executor over a real ``Portfolio`` and a real 1m store, with a clock the test moves."""

    def __init__(
        self,
        tmp_path: Path,
        *,
        paths: Mapping[str, Mapping[int, Minute]] | None = None,
        count: int = 720,
        omit: frozenset[int] = frozenset(),
        free: Decimal = FREE,
        window_end: datetime = WINDOW_END,
    ) -> None:
        root = tmp_path / "hist"
        for symbol, minutes in (paths or {"BTCUSDT": {}}).items():
            build_minutes(root, symbol, count=count, minutes=minutes, omit=omit)
        self.store = SpyStore(root)
        self.now = at(0)
        self.portfolio = Portfolio(quote_asset="USDT", free_quote=free)
        self.executor = D1Executor(
            portfolio=self.portfolio,
            params=PARAMS,
            clock=lambda: self.now,
            store=self.store,
            window_end=window_end,
        )

    def position(self, symbol: str = "BTCUSDT") -> Position:
        assert self.portfolio.has_position(symbol), f"no open position for {symbol}"
        return self.portfolio.positions[symbol]

    async def feed(self, candle: Candle) -> None:
        self.now = candle.open_time + FOUR_HOURS
        await self.executor(candle)

    async def buy(
        self,
        candle: Candle,
        assessment: RiskAssessment | None = None,
        *,
        delta: object = 500,
        clamp: str = "none",
    ) -> None:
        await self.executor.dispatch(
            signal_for(candle, delta=delta, clamp=clamp),
            assessment or entry_assessment(candle.symbol),
            candle,
        )

    async def enter(self, symbol: str = "BTCUSDT") -> None:
        """Signal on the 00:00 bar and feed the 04:00 bar, which fills the entry."""
        await self.buy(bar(0, symbol=symbol))
        await self.feed(bar(4, symbol=symbol))


def only[T](items: Sequence[T]) -> T:
    assert len(items) == 1, items
    return items[0]


class TestTheExitInTheEntryBar:
    async def test_a_trail_that_triggers_in_the_entry_bar_is_booked_in_that_callback(
        self, tmp_path: Path
    ) -> None:
        rig = Rig(tmp_path, paths={"BTCUSDT": {300: DROP}})
        await rig.enter()
        trade = only(rig.executor.trades)
        assert trade.exit_reason is SimulatedExit.STOP_LOSS
        assert trade.exit_bar_open == at(300)
        assert trade.exit_time == at(301)
        assert trade.exit_price == D("94.05")
        assert trade.exit_trigger == D("95")
        assert trade.exit_open_through_trigger is False
        assert trade.entry_price == D("100")
        assert trade.stop_loss == D("95")
        assert trade.take_profit is None
        assert trade.realised == D("-3.072025")
        assert rig.portfolio.free_quote == D("9996.927975")
        assert not rig.portfolio.has_position("BTCUSDT")
        assert rig.executor.counts.exits_stop_loss == 1
        assert rig.executor.unsettled["open_positions"] == ()

    async def test_the_entry_minutes_high_counts_toward_the_peak(self, tmp_path: Path) -> None:
        up_and_back: Minute = ("100", "110", "100", "105", "1")
        rig = Rig(tmp_path, paths={"BTCUSDT": {240: up_and_back}})
        await rig.enter()
        trade = only(rig.executor.trades)
        assert trade.exit_bar_open == at(240)
        assert trade.exit_time == at(241)
        assert trade.exit_price == D("103.455")
        assert trade.exit_trigger == D("104.5")
        assert trade.realised == D("1.6257725")


class TestTheExitIsScheduled:
    async def test_an_exit_after_the_bar_is_not_booked_until_the_clock_reaches_it(
        self, tmp_path: Path
    ) -> None:
        rig = Rig(tmp_path, paths={"BTCUSDT": {500: DROP}})
        await rig.enter()
        assert rig.executor.trades == ()
        assert rig.executor.unsettled["open_positions"] == ("BTCUSDT",)
        assert rig.portfolio.free_quote == D("9949.95")
        await rig.feed(bar(8))
        trade = only(rig.executor.trades)
        assert trade.exit_bar_open == at(500)
        assert trade.exit_time == at(501)
        assert trade.realised == D("-3.072025")
        assert rig.executor.unsettled["open_positions"] == ()

    async def test_an_exit_at_exactly_the_clock_is_booked(self, tmp_path: Path) -> None:
        rig = Rig(tmp_path, paths={"BTCUSDT": {479: DROP}})
        await rig.enter()
        assert only(rig.executor.trades).exit_time == at(480)

    async def test_an_exit_one_minute_past_the_clock_waits(self, tmp_path: Path) -> None:
        rig = Rig(tmp_path, paths={"BTCUSDT": {480: DROP}})
        await rig.enter()
        assert rig.executor.trades == ()

    async def test_the_exit_is_booked_before_a_signal_on_the_next_bar_can_see_it(
        self, tmp_path: Path
    ) -> None:
        rig = Rig(tmp_path, paths={"BTCUSDT": {500: DROP}})
        await rig.enter()
        await rig.feed(bar(8))
        assert not rig.portfolio.has_position("BTCUSDT")
        await rig.buy(bar(8))
        assert rig.executor.unsettled["pending_entries"] == ("BTCUSDT",)

    async def test_two_pairs_book_in_time_order_not_in_callback_order(self, tmp_path: Path) -> None:
        rig = Rig(
            tmp_path,
            paths={"BTCUSDT": {560: DROP}, "ETHUSDT": {540: DROP}},
        )
        await rig.buy(bar(0, symbol="BTCUSDT"))
        await rig.buy(bar(0, symbol="ETHUSDT"))
        await rig.feed(bar(4, symbol="BTCUSDT"))
        await rig.feed(bar(4, symbol="ETHUSDT"))
        assert rig.executor.trades == ()
        assert set(rig.executor.unsettled["open_positions"]) == {"BTCUSDT", "ETHUSDT"}
        await rig.feed(bar(8, symbol="BTCUSDT"))
        assert [t.symbol for t in rig.executor.trades] == ["ETHUSDT", "BTCUSDT"]
        assert [t.exit_time for t in rig.executor.trades] == [at(541), at(561)]

    async def test_overlapping_positions_hold_one_ledger(self, tmp_path: Path) -> None:
        rig = Rig(tmp_path, paths={"BTCUSDT": {}, "ETHUSDT": {}})
        await rig.buy(bar(0, symbol="BTCUSDT"))
        await rig.buy(bar(0, symbol="ETHUSDT"))
        await rig.feed(bar(4, symbol="BTCUSDT"))
        await rig.feed(bar(4, symbol="ETHUSDT"))
        assert rig.portfolio.free_quote == D("9899.9")
        assert rig.portfolio.has_position("BTCUSDT") and rig.portfolio.has_position("ETHUSDT")


class TestAPositionThatNeverTriggers:
    async def test_it_stays_open_at_the_end(self, tmp_path: Path) -> None:
        rig = Rig(tmp_path)
        await rig.enter()
        await rig.feed(bar(8))
        rig.executor.finish()
        assert rig.executor.trades == ()
        assert rig.executor.unsettled["open_positions"] == ("BTCUSDT",)
        assert rig.position().protection is ProtectionState.ACTIVE

    async def test_a_trigger_after_the_window_end_is_never_read(self, tmp_path: Path) -> None:
        rig = Rig(tmp_path, paths={"BTCUSDT": {750: DROP}}, count=800)
        await rig.enter()
        await rig.feed(bar(8))
        rig.executor.finish()
        assert rig.executor.trades == ()
        assert rig.executor.unsettled["open_positions"] == ("BTCUSDT",)
        assert rig.store.asked
        for _, interval, _, end in rig.store.asked:
            assert interval == "1m"
            assert end <= WINDOW_END

    async def test_finish_is_idempotent(self, tmp_path: Path) -> None:
        rig = Rig(tmp_path, paths={"BTCUSDT": {500: DROP}})
        await rig.enter()
        rig.executor.finish()
        once = rig.executor.trades
        rig.executor.finish()
        assert rig.executor.trades == once
        assert len(once) == 1


class TestAGapInTheMinutePath:
    async def test_a_fall_inside_the_gap_exits_at_the_next_traded_open(
        self, tmp_path: Path
    ) -> None:
        rig = Rig(
            tmp_path,
            paths={"BTCUSDT": {420: flat("90")}},
            omit=frozenset(range(400, 420)),
        )
        await rig.enter()
        trade = only(rig.executor.trades)
        assert trade.exit_bar_open == at(420)
        assert trade.exit_price == D("89.1")
        assert trade.exit_open_through_trigger is True
        assert trade.exit_trigger == D("95")

    async def test_a_gap_that_recovers_leaves_the_position_open(self, tmp_path: Path) -> None:
        rig = Rig(tmp_path, omit=frozenset(range(400, 420)))
        await rig.enter()
        assert rig.executor.trades == ()
        assert rig.position()

    async def test_a_decision_bar_gap_flags_the_trade(self, tmp_path: Path) -> None:
        rig = Rig(tmp_path, paths={"BTCUSDT": {620: DROP}})
        await rig.buy(bar(0))
        await rig.feed(bar(4))
        await rig.feed(bar(12))
        trade = only(rig.executor.trades)
        assert trade.spans_gap is True
        assert rig.executor.counts.gaps_seen == 1


class TestZeroVolumeMinutes:
    async def test_a_filler_minute_is_not_a_trade_and_is_not_walked(self, tmp_path: Path) -> None:
        filler: Minute = ("100", "100", "90", "100", "0")
        rig = Rig(tmp_path, paths={"BTCUSDT": {240: filler}})
        await rig.enter()
        assert rig.executor.trades == ()
        assert rig.position()

    async def test_a_bar_with_no_traded_minute_cannot_fill(self, tmp_path: Path) -> None:
        silent = dict.fromkeys(range(240, 480), ("100", "100", "100", "100", "0"))
        rig = Rig(tmp_path, paths={"BTCUSDT": silent})
        await rig.enter()
        attempt = only(rig.executor.attempts)
        assert attempt.result is EntryResult.EXPIRED
        assert "no minute traded" in attempt.detail
        assert not rig.portfolio.has_position("BTCUSDT")
        assert rig.portfolio.free_quote == FREE
        assert rig.executor.counts.entries_expired == 1


class TestAnEntryThatDoesNotFill:
    async def test_an_open_above_the_limit_is_refused(self, tmp_path: Path) -> None:
        rig = Rig(tmp_path)
        await rig.buy(bar(0))
        await rig.feed(bar(4, open="101"))
        assert only(rig.executor.attempts).result is EntryResult.REFUSED
        assert rig.executor.counts.entries_refused == 1
        assert not rig.portfolio.has_position("BTCUSDT")

    async def test_a_missing_next_slot_expires_the_entry(self, tmp_path: Path) -> None:
        rig = Rig(tmp_path)
        await rig.buy(bar(0))
        await rig.feed(bar(8))
        assert only(rig.executor.attempts).result is EntryResult.EXPIRED
        assert rig.executor.counts.entries_expired == 1

    async def test_an_entry_the_data_ends_on_expires(self, tmp_path: Path) -> None:
        rig = Rig(tmp_path)
        await rig.buy(bar(0))
        rig.executor.finish()
        assert only(rig.executor.attempts).result is EntryResult.EXPIRED
        assert rig.executor.unsettled["pending_entries"] == ()

    async def test_an_entry_the_ledger_cannot_pay_for_is_unaffordable(self, tmp_path: Path) -> None:
        rig = Rig(tmp_path, free=D(10))
        await rig.enter()
        assert only(rig.executor.attempts).result is EntryResult.UNAFFORDABLE
        assert rig.executor.counts.entries_unaffordable == 1
        assert not rig.portfolio.has_position("BTCUSDT")
        assert rig.portfolio.free_quote == D(10)

    async def test_a_second_entry_while_one_is_pending_is_ignored(self, tmp_path: Path) -> None:
        rig = Rig(tmp_path)
        await rig.buy(bar(0))
        await rig.buy(bar(0))
        assert rig.executor.counts.entries_queued == 1
        assert rig.executor.counts.entries_ignored == 1


class TestThePositionItOpens:
    async def test_the_initial_stop_is_the_fill_less_the_trail(self, tmp_path: Path) -> None:
        rig = Rig(tmp_path)
        await rig.buy(bar(0), delta=1200)
        await rig.feed(bar(4))
        position = rig.position()
        assert position.stop_loss == D("88")
        assert position.take_profit is None
        assert position.entry_fill_price == D("100")
        assert position.opened_at == at(240)

    async def test_it_is_stamped_active_at_the_simulated_instant(self, tmp_path: Path) -> None:
        rig = Rig(tmp_path)
        await rig.enter()
        position = rig.position()
        assert position.protection is ProtectionState.ACTIVE
        assert position.last_reconciled_at == at(480)

    async def test_a_position_on_another_pair_is_stamped_on_every_bar(self, tmp_path: Path) -> None:
        rig = Rig(tmp_path, paths={"BTCUSDT": {}, "ETHUSDT": {}})
        await rig.enter("BTCUSDT")
        await rig.feed(bar(4, symbol="ETHUSDT"))
        await rig.feed(bar(8, symbol="ETHUSDT"))
        assert rig.position("BTCUSDT").last_reconciled_at == at(720)


class TestTheTally:
    async def test_every_signal_is_counted_with_its_delta_and_clamp(self, tmp_path: Path) -> None:
        rig = Rig(tmp_path)
        await rig.buy(bar(0), refused(RefusalStage.LIMIT_REFUSED), delta=1200)
        await rig.buy(bar(0), delta=2000, clamp="upper")
        await rig.buy(bar(4), refused(RefusalStage.LIMIT_REFUSED), delta=10, clamp="lower")
        tally = rig.executor.tallies["BTCUSDT"]
        assert tally.signals == 3
        assert tally.deltas == [1200, 2000, 10]
        assert (tally.clamp_upper, tally.clamp_lower) == (1, 1)
        assert tally.refusals == {RefusalStage.LIMIT_REFUSED: 2}

    @pytest.mark.parametrize("stage", list(RefusalStage))
    async def test_a_refusal_from_each_stage_is_counted_under_that_stage(
        self, tmp_path: Path, stage: RefusalStage
    ) -> None:
        rig = Rig(tmp_path)
        await rig.buy(bar(0), refused(stage))
        assert rig.executor.tallies["BTCUSDT"].refusals == {stage: 1}
        assert rig.executor.counts.refused_by_risk == 1
        assert rig.executor.unsettled["pending_entries"] == ()

    @pytest.mark.parametrize("rule", list(RiskRule))
    async def test_a_refusal_is_counted_under_the_rule_that_fired(
        self, tmp_path: Path, rule: RiskRule
    ) -> None:
        """R-DT-3e. ``no_mark_price`` refuses at its own stage and the other five under the limits."""
        stage = (
            RefusalStage.NO_MARK_PRICE
            if rule is RiskRule.NO_MARK_PRICE
            else RefusalStage.LIMIT_REFUSED
        )
        rig = Rig(tmp_path)
        await rig.buy(bar(0), refused_by(rule, stage=stage))
        await rig.buy(bar(4), refused_by(rule, stage=stage))
        tally = rig.executor.tallies["BTCUSDT"]
        assert tally.rules == {rule: 2}
        assert tally.refusals == {stage: 2}

    @pytest.mark.parametrize("stage", [RefusalStage.SIZE_NOT_TRADEABLE, RefusalStage.UNAFFORDABLE])
    async def test_a_refusal_after_the_limits_carries_no_rule(
        self, tmp_path: Path, stage: RefusalStage
    ) -> None:
        rig = Rig(tmp_path)
        await rig.buy(bar(0), refused_after_the_limits(stage))
        tally = rig.executor.tallies["BTCUSDT"]
        assert tally.rules == {}
        assert tally.refusals == {stage: 1}

    async def test_a_refusal_with_no_decision_carries_no_rule(self, tmp_path: Path) -> None:
        rig = Rig(tmp_path)
        await rig.buy(bar(0), refused(RefusalStage.UNKNOWN_PAIR))
        assert rig.executor.tallies["BTCUSDT"].rules == {}

    async def test_an_approved_entry_adds_no_rule(self, tmp_path: Path) -> None:
        rig = Rig(tmp_path)
        await rig.buy(bar(0))
        assert rig.executor.tallies["BTCUSDT"].rules == {}

    async def test_rules_are_tallied_per_pair_and_the_snapshot_is_a_copy(
        self, tmp_path: Path
    ) -> None:
        rig = Rig(tmp_path)
        await rig.buy(bar(0), refused_by(RiskRule.DAILY_LOSS_HALT))
        await rig.buy(bar(0, symbol="ETHUSDT"), refused_by(RiskRule.COOLDOWN, "ETHUSDT"))
        snapshot = rig.executor.tallies
        snapshot["BTCUSDT"].rules.clear()
        again = rig.executor.tallies
        assert again["BTCUSDT"].rules == {RiskRule.DAILY_LOSS_HALT: 1}
        assert again["ETHUSDT"].rules == {RiskRule.COOLDOWN: 1}

    async def test_pairs_are_tallied_apart(self, tmp_path: Path) -> None:
        rig = Rig(tmp_path)
        await rig.buy(bar(0, symbol="BTCUSDT"), refused(RefusalStage.NO_MARK_PRICE, "BTCUSDT"))
        await rig.buy(bar(0, symbol="ETHUSDT"), refused(RefusalStage.POSITION_STALE, "ETHUSDT"))
        tallies = rig.executor.tallies
        assert tallies["BTCUSDT"].refusals == {RefusalStage.NO_MARK_PRICE: 1}
        assert tallies["ETHUSDT"].refusals == {RefusalStage.POSITION_STALE: 1}

    async def test_the_snapshot_is_a_copy(self, tmp_path: Path) -> None:
        rig = Rig(tmp_path)
        await rig.buy(bar(0), refused(RefusalStage.NO_MARK_PRICE))
        snapshot: dict[str, SymbolTally] = rig.executor.tallies
        snapshot["BTCUSDT"].deltas.append(1)
        snapshot["BTCUSDT"].refusals.clear()
        again = rig.executor.tallies["BTCUSDT"]
        assert again.deltas == [500]
        assert again.refusals == {RefusalStage.NO_MARK_PRICE: 1}


class TestWhatItRefusesToDispatch:
    @pytest.mark.parametrize("delta", [None, 500.0, "500", True])
    async def test_a_signal_without_an_integer_delta_raises(
        self, tmp_path: Path, delta: object
    ) -> None:
        rig = Rig(tmp_path)
        with pytest.raises(D1ExecutorError, match="trail_delta_bps"):
            await rig.executor.dispatch(signal_for(bar(0), delta=delta), entry_assessment(), bar(0))
        assert rig.executor.tallies == {}

    async def test_an_approved_exit_raises(self, tmp_path: Path) -> None:
        rig = Rig(tmp_path)
        intent = ExitIntent(symbol="BTCUSDT", quantity=D("0.5"), reference_price=D("100"))
        approved = RiskAssessment(
            symbol="BTCUSDT", approved=True, reason="approved", stage=None, intent=intent
        )
        with pytest.raises(D1ExecutorError, match="never asks to close"):
            await rig.executor.dispatch(
                signal_for(bar(0), action=SignalAction.CLOSE), approved, bar(0)
            )


class TestTheContract:
    def test_it_satisfies_the_dispatcher_port(self, tmp_path: Path) -> None:
        assert isinstance(Rig(tmp_path).executor, Dispatcher)

    def test_the_metadata_keys_are_the_ones_the_strategies_write(self) -> None:
        assert d1_executor.DELTA_KEY == trail.TRAIL_DELTA_KEY
        assert d1_executor.CLAMP_KEY == trail.TRAIL_CLAMP_KEY

    async def test_two_runs_of_the_same_history_give_the_same_trade_log(
        self, tmp_path: Path
    ) -> None:
        digests = []
        for name in ("a", "b"):
            rig = Rig(tmp_path / name, paths={"BTCUSDT": {500: DROP}})
            await rig.enter()
            await rig.feed(bar(8))
            digests.append(trade_log_digest(rig.executor.trades))
        assert digests[0] == digests[1]
        assert len(digests[0]) == 64

    def test_the_module_reads_no_wall_clock(self) -> None:
        source = Path(d1_executor.__file__).read_text(encoding="utf-8")
        for word in (".now(", ".utcnow(", "time.time", "sleep("):
            assert word not in source, word
