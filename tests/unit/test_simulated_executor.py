"""The simulated executor (M5m S2): each sentence of R-AA and R-W(d), proved, hand-computed.

Every figure is worked by hand from the ruled default percents -- entry and ``CLOSE`` slippage
0.05%, stop slippage 1.20%, fee 0.1% a leg -- on one order of 0.5 with a limit of 100.10, a stop
at 98 and a take-profit at 104, signalled on the bar at ``T0`` and filled on the bar after it:

* the entry at an open of 100: price 100.05, notional 50.025, fee 0.050025, quote total
  50.075025, so the free quote falls from 10000 to 9949.924975
* the stop: 98 x 0.988 = 96.824, gross 48.412, fee 0.048412, realised
  48.412 - 50.075025 - 0.048412 = -1.711437
* the take-profit: 104 x 0.988 = 102.752, gross 51.376, fee 0.051376, realised 1.249599
* a ``CLOSE`` at an open of 101: 101 x 0.9995 = 100.9495, gross 50.47475, fee 0.05047475,
  realised 0.34925025
* the stop gapped through at an open of 97: 97 x 0.988 = 95.836, gross 47.918, fee 0.047918,
  realised -2.204943
"""

from __future__ import annotations

import ast
import hashlib
from collections.abc import Sequence
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

import pytest

from trading_bot.backtesting import simulated_executor
from trading_bot.backtesting.fill_model import FillParameters
from trading_bot.backtesting.simulated_executor import (
    EntryResult,
    SimulatedExecutor,
    SimulatedExit,
    trade_log_digest,
    trade_rows,
)
from trading_bot.core.assessment import EntryIntent, ExitIntent, RiskAssessment
from trading_bot.core.enums import PositionSide, ProtectionState, RefusalStage, SignalAction
from trading_bot.core.interfaces import Dispatcher
from trading_bot.core.models import Candle, Position, ProtectiveLevels, Signal
from trading_bot.core.portfolio import Portfolio

D = Decimal
T0 = datetime(2024, 3, 1, tzinfo=timezone.utc)
HOUR = timedelta(hours=1)
STEP = {"1m": timedelta(minutes=1), "5m": timedelta(minutes=5), "1h": HOUR}
FREE = D(10000)
ENTRY_TOTAL = D("50.075025")


def bar(
    *,
    at: datetime,
    open: str,
    high: str,
    low: str,
    symbol: str = "BTCUSDT",
    tf: str = "1h",
    short: bool = False,
) -> Candle:
    step = STEP[tf]
    closed = at + step / 2 if short else at + step - timedelta(milliseconds=1)
    return Candle(
        symbol=symbol,
        timeframe=tf,
        open_time=at,
        close_time=closed,
        open=D(open),
        high=D(high),
        low=D(low),
        close=D(open),
        volume=D(1),
    )


def entry_assessment(
    symbol: str = "BTCUSDT",
    *,
    quantity: str = "0.5",
    limit: str = "100.10",
    stop: str | None = "98",
    take: str | None = "104",
) -> RiskAssessment:
    levels = ProtectiveLevels(
        symbol=symbol,
        side=PositionSide.LONG,
        entry_price=D(limit),
        stop_loss=None if stop is None else D(stop),
        take_profit=None if take is None else D(take),
        stop_distance=None if stop is None else D(limit) - D(stop),
        basis="test",
    )
    intent = EntryIntent(
        symbol=symbol,
        quantity=D(quantity),
        reference_price=D("100"),
        entry_limit=D(limit),
        levels=levels,
    )
    return RiskAssessment(
        symbol=symbol, approved=True, reason="approved", stage=None, intent=intent
    )


def exit_assessment(symbol: str = "BTCUSDT", *, quantity: str = "0.5") -> RiskAssessment:
    intent = ExitIntent(symbol=symbol, quantity=D(quantity), reference_price=D("100"))
    return RiskAssessment(
        symbol=symbol, approved=True, reason="approved", stage=None, intent=intent
    )


def refused_assessment(symbol: str = "BTCUSDT") -> RiskAssessment:
    return RiskAssessment(
        symbol=symbol, approved=False, reason="refused", stage=RefusalStage.NO_MARK_PRICE
    )


class Rig:
    """An executor over a real ``Portfolio``, with a clock the test moves one bar at a time."""

    def __init__(self, *, free: Decimal = FREE, params: FillParameters | None = None) -> None:
        self.now = T0
        self.portfolio = Portfolio(quote_asset="USDT", free_quote=free)
        self.executor = SimulatedExecutor(
            portfolio=self.portfolio, params=params or FillParameters(), clock=lambda: self.now
        )

    def position(self, symbol: str = "BTCUSDT") -> Position:
        """The open position, asserted present: a missing one is an AssertionError and not the
        ``KeyError`` of a bare lookup, which a mutation survey cannot count as a kill."""
        assert self.portfolio.has_position(symbol), f"no open position for {symbol}"
        return self.portfolio.positions[symbol]

    async def feed(self, candle: Candle) -> None:
        """Deliver ``candle`` with the simulated instant at its nominal end, as the replay does."""
        self.now = candle.open_time + STEP[candle.timeframe]
        await self.executor(candle)

    async def buy(self, signal_bar: Candle, assessment: RiskAssessment | None = None) -> None:
        signal = Signal(
            symbol=signal_bar.symbol,
            action=SignalAction.BUY,
            timestamp=signal_bar.close_time,
            price=signal_bar.close,
        )
        await self.executor.dispatch(
            signal, assessment or entry_assessment(signal_bar.symbol), signal_bar
        )

    async def sell(self, signal_bar: Candle, assessment: RiskAssessment | None = None) -> None:
        signal = Signal(
            symbol=signal_bar.symbol,
            action=SignalAction.CLOSE,
            timestamp=signal_bar.close_time,
            price=signal_bar.close,
        )
        await self.executor.dispatch(
            signal, assessment or exit_assessment(signal_bar.symbol), signal_bar
        )


def only[T](items: Sequence[T]) -> T:
    """The one item, asserted rather than unpacked: a wrong count is an AssertionError here, and
    a tuple-unpack would raise ``ValueError``, which a mutation survey cannot count as a kill."""
    assert len(items) == 1, items
    return items[0]


SIGNAL_BAR = bar(at=T0, open="100", high="101", low="99")
ENTRY_BAR = T0 + HOUR


def quiet(at: datetime, **kw: str | bool) -> Candle:
    """A bar that touches neither the stop at 98 nor the take-profit at 104."""
    return bar(at=at, open="100", high="101", low="99", **kw)  # type: ignore[arg-type]


async def opened(**kw: str | None) -> Rig:
    """A rig holding the base position: signalled at ``T0``, filled on the bar after it."""
    rig = Rig()
    await rig.buy(SIGNAL_BAR, entry_assessment(**kw))
    await rig.feed(quiet(ENTRY_BAR))
    rig.position()  # the entry must have filled; every test built on this starts from it
    return rig


class TestAnEntryIsHandedTheNextBar:
    async def test_dispatch_fills_nothing(self) -> None:
        rig = Rig()
        await rig.buy(SIGNAL_BAR)
        assert rig.portfolio.free_quote == FREE
        assert not rig.portfolio.has_position("BTCUSDT")
        assert rig.executor.unsettled["pending_entries"] == ("BTCUSDT",)
        assert rig.executor.attempts == ()

    async def test_the_next_slot_fills_at_its_open_plus_slippage(self) -> None:
        rig = Rig()
        await rig.buy(SIGNAL_BAR)
        await rig.feed(bar(at=ENTRY_BAR, open="100", high="101", low="99"))
        position = rig.position()
        assert position.entry_fill_price == D("100.05")
        assert position.entry_quote_total == ENTRY_TOTAL
        assert rig.portfolio.free_quote == D("9949.924975")
        assert position.side is PositionSide.LONG
        assert position.quantity == D("0.5")
        assert position.entry_price == D("100.10")  # what was REQUESTED, not what filled
        assert (position.stop_loss, position.take_profit) == (D("98"), D("104"))
        attempt = only(rig.executor.attempts)
        assert attempt.result is EntryResult.FILLED
        assert attempt.settled_bar_open == ENTRY_BAR
        assert attempt.price == D("100.05")
        assert rig.executor.counts.entries_filled == 1

    async def test_the_entry_is_not_filled_at_the_signal_bars_own_prices(self) -> None:
        """The signal bar closed at 100 with a low of 99; the entry bar opens at 102. The fill
        is 102 x 1.0005 and nothing about it comes from the bar the signal was decided on."""
        rig = Rig()
        await rig.buy(SIGNAL_BAR, entry_assessment(limit="103"))
        await rig.feed(bar(at=ENTRY_BAR, open="102", high="103", low="101"))
        assert rig.position().entry_fill_price == D("102.051")

    async def test_a_missing_next_slot_expires_the_entry(self) -> None:
        """R-W(d): the slot at T0 + 1 h is missing; the next bar opens at T0 + 2 h, and it would
        have filled inside the limit. No position, no debit."""
        rig = Rig()
        await rig.buy(SIGNAL_BAR)
        await rig.feed(quiet(T0 + 2 * HOUR))
        assert not rig.portfolio.has_position("BTCUSDT")
        assert rig.portfolio.free_quote == FREE
        attempt = only(rig.executor.attempts)
        assert attempt.result is EntryResult.EXPIRED
        assert "missing" in attempt.detail
        assert rig.executor.counts.entries_expired == 1
        assert rig.executor.unsettled["pending_entries"] == ()

    async def test_an_entry_the_fok_refuses_opens_nothing(self) -> None:
        """An open of 100.20 plus slippage is 100.2501, above the limit of 100.10."""
        rig = Rig()
        await rig.buy(SIGNAL_BAR)
        await rig.feed(bar(at=ENTRY_BAR, open="100.20", high="101", low="99"))
        assert not rig.portfolio.has_position("BTCUSDT")
        assert rig.portfolio.free_quote == FREE
        attempt = only(rig.executor.attempts)
        assert attempt.result is EntryResult.REFUSED
        assert attempt.price is None
        assert rig.executor.counts.entries_refused == 1

    async def test_the_quantity_is_filled_as_sized_and_never_re_sized(self) -> None:
        """A quantity off every step, and a free quote that would buy far more: both stay."""
        rig = Rig()
        await rig.buy(SIGNAL_BAR, entry_assessment(quantity="0.123456789"))
        await rig.feed(quiet(ENTRY_BAR))
        assert rig.position().quantity == D("0.123456789")

    async def test_an_entry_whose_fee_overdraws_the_free_quote_is_not_opened(self) -> None:
        """The quote total is 50.075025; a free quote of 50.07 covers the notional (50.025) and
        not the fee on top, and the executor does not re-size to fit."""
        rig = Rig(free=D("50.07"))
        await rig.buy(SIGNAL_BAR)
        await rig.feed(quiet(ENTRY_BAR))
        assert not rig.portfolio.has_position("BTCUSDT")
        assert rig.portfolio.free_quote == D("50.07")
        attempt = only(rig.executor.attempts)
        assert attempt.result is EntryResult.UNAFFORDABLE
        assert rig.executor.counts.entries_unaffordable == 1

    async def test_a_free_quote_equal_to_the_quote_total_is_enough(self) -> None:
        """The boundary: 50.075025 free buys an entry that costs 50.075025, leaving nothing."""
        rig = Rig(free=ENTRY_TOTAL)
        await rig.buy(SIGNAL_BAR)
        await rig.feed(quiet(ENTRY_BAR))
        assert rig.portfolio.has_position("BTCUSDT")
        assert rig.portfolio.free_quote == D(0)
        assert only(rig.executor.attempts).result is EntryResult.FILLED

    async def test_the_data_ending_expires_a_pending_entry_and_finish_is_idempotent(self) -> None:
        rig = Rig()
        await rig.buy(SIGNAL_BAR)
        rig.executor.finish()
        rig.executor.finish()
        attempt = only(rig.executor.attempts)
        assert attempt.result is EntryResult.EXPIRED
        assert attempt.settled_bar_open is None
        assert rig.executor.counts.entries_expired == 1
        assert rig.executor.unsettled["pending_entries"] == ()

    async def test_a_second_entry_while_one_is_pending_or_held_is_ignored(self) -> None:
        rig = Rig()
        await rig.buy(SIGNAL_BAR)
        await rig.buy(SIGNAL_BAR)
        assert rig.executor.counts.entries_queued == 1
        assert rig.executor.counts.entries_ignored == 1
        await rig.feed(quiet(ENTRY_BAR))
        await rig.buy(quiet(ENTRY_BAR))
        assert rig.executor.counts.entries_ignored == 2

    async def test_a_refused_assessment_does_nothing(self) -> None:
        rig = Rig()
        await rig.buy(SIGNAL_BAR, refused_assessment())
        assert rig.executor.counts.dispatched == 1
        assert rig.executor.counts.refused_by_risk == 1
        assert rig.executor.unsettled["pending_entries"] == ()


class TestProtectionActsFromTheEntryBarsOpen:
    async def test_a_stop_acts_on_the_entry_bars_own_low(self) -> None:
        rig = Rig()
        await rig.buy(SIGNAL_BAR)
        await rig.feed(bar(at=ENTRY_BAR, open="100", high="101", low="97.5"))
        trade = only(rig.executor.trades)
        assert trade.exit_reason is SimulatedExit.STOP_LOSS
        assert trade.exit_bar_open == ENTRY_BAR == trade.entry_bar_open
        assert trade.exit_price == D("96.824")
        assert trade.exit_trigger == D("98")
        assert trade.exit_open_through_trigger is False
        assert trade.realised == D("-1.711437")
        assert not rig.portfolio.has_position("BTCUSDT")
        assert rig.executor.unsettled["open_positions"] == ()
        counts = rig.executor.counts
        assert (counts.exits_stop_loss, counts.exits_take_profit, counts.exits_close) == (1, 0, 0)

    async def test_a_take_profit_acts_on_the_entry_bars_own_high(self) -> None:
        rig = Rig()
        await rig.buy(SIGNAL_BAR)
        await rig.feed(bar(at=ENTRY_BAR, open="100", high="104.5", low="99"))
        trade = only(rig.executor.trades)
        assert trade.exit_reason is SimulatedExit.TAKE_PROFIT
        assert trade.exit_price == D("102.752")
        assert trade.realised == D("1.249599")
        counts = rig.executor.counts
        assert (counts.exits_stop_loss, counts.exits_take_profit, counts.exits_close) == (0, 1, 0)

    async def test_a_trade_row_carries_every_field_of_the_round_trip(self) -> None:
        rig = Rig()
        await rig.buy(SIGNAL_BAR)
        await rig.feed(bar(at=ENTRY_BAR, open="100", high="101", low="97.5"))
        trade = only(rig.executor.trades)
        assert (trade.symbol, trade.timeframe) == ("BTCUSDT", "1h")
        assert (trade.signal_bar_open, trade.entry_bar_open) == (T0, ENTRY_BAR)
        assert (trade.quantity, trade.entry_limit) == (D("0.5"), D("100.10"))
        assert (trade.entry_price, trade.entry_notional) == (D("100.05"), D("50.025"))
        assert (trade.entry_fee, trade.entry_quote_total) == (D("0.050025"), ENTRY_TOTAL)
        assert (trade.stop_loss, trade.take_profit) == (D("98"), D("104"))
        assert (trade.exit_gross, trade.exit_fee) == (D("48.412"), D("0.048412"))
        assert trade.exit_time == ENTRY_BAR + HOUR

    async def test_a_bar_touching_both_is_a_stop(self) -> None:
        rig = Rig()
        await rig.buy(SIGNAL_BAR)
        await rig.feed(bar(at=ENTRY_BAR, open="100", high="104.5", low="97.5"))
        trade = only(rig.executor.trades)
        assert trade.exit_reason is SimulatedExit.STOP_LOSS
        assert trade.exit_price == D("96.824")

    async def test_an_entry_bar_that_opens_through_the_stop_fills_at_its_open(self) -> None:
        """Entry at 97 x 1.0005 = 97.0485 (inside the limit), then the stop gapped through at
        97 x 0.988 = 95.836. Quote total 48.57277425; realised -0.70269225."""
        rig = Rig()
        await rig.buy(SIGNAL_BAR)
        await rig.feed(bar(at=ENTRY_BAR, open="97", high="97.5", low="96"))
        trade = only(rig.executor.trades)
        assert trade.entry_price == D("97.0485")
        assert trade.entry_quote_total == D("48.57277425")
        assert trade.exit_price == D("95.836")
        assert trade.exit_open_through_trigger is True
        assert trade.realised == D("-0.70269225")

    async def test_a_quiet_entry_bar_leaves_the_position_open(self) -> None:
        rig = await opened()
        assert rig.portfolio.has_position("BTCUSDT")
        assert rig.executor.trades == ()
        assert rig.executor.unsettled["open_positions"] == ("BTCUSDT",)

    async def test_a_later_bar_is_tested_against_the_levels_set_at_entry(self) -> None:
        rig = await opened()
        await rig.feed(bar(at=ENTRY_BAR + HOUR, open="100", high="101", low="97.5"))
        trade = only(rig.executor.trades)
        assert trade.exit_bar_open == ENTRY_BAR + HOUR
        assert trade.entry_bar_open == ENTRY_BAR
        assert trade.exit_price == D("96.824")


class TestACloseSellsAtTheNextOpen:
    async def test_it_sells_at_the_next_bars_open_less_the_entry_slippage(self) -> None:
        rig = await opened()
        await rig.sell(quiet(ENTRY_BAR))
        assert rig.portfolio.has_position("BTCUSDT")  # dispatch sells nothing
        await rig.feed(bar(at=ENTRY_BAR + HOUR, open="101", high="102", low="100"))
        trade = only(rig.executor.trades)
        assert trade.exit_reason is SimulatedExit.CLOSE
        assert trade.exit_price == D("100.9495")
        assert trade.exit_trigger is None
        assert trade.realised == D("0.34925025")
        counts = rig.executor.counts
        assert (counts.exits_stop_loss, counts.exits_take_profit, counts.exits_close) == (0, 0, 1)

    async def test_the_protective_legs_are_cancelled_at_the_close_on_the_very_next_bar(
        self,
    ) -> None:
        """No gap: live cancels the legs before it sells, so an open of 97, below the stop at
        98, is sold at 97 x 0.9995 = 96.9515 and not stopped at 97 x 0.988."""
        rig = await opened()
        await rig.sell(quiet(ENTRY_BAR))
        await rig.feed(bar(at=ENTRY_BAR + HOUR, open="97", high="97.5", low="96"))
        trade = only(rig.executor.trades)
        assert trade.exit_reason is SimulatedExit.CLOSE
        assert trade.exit_price == D("96.9515")
        assert trade.realised == D("-1.64775075")

    async def test_a_close_over_a_gap_leaves_the_stop_in_force_until_the_bar_after_it(self) -> None:
        rig = await opened()
        await rig.sell(quiet(ENTRY_BAR))
        assert rig.position().stop_loss == D("98")
        assert rig.position().take_profit == D("104")
        assert rig.executor.unsettled["queued_closes"] == ("BTCUSDT",)

    async def test_over_a_gap_an_open_above_the_stop_sells_at_the_open_not_the_low(self) -> None:
        """The slot at ENTRY_BAR + 1 h is missing. The next bar opens at 101 and its low, 97, is
        below the stop: the CLOSE still sells at the open, before the bar's range."""
        rig = await opened()
        await rig.sell(quiet(ENTRY_BAR))
        await rig.feed(bar(at=ENTRY_BAR + 2 * HOUR, open="101", high="102", low="97"))
        trade = only(rig.executor.trades)
        assert trade.exit_reason is SimulatedExit.CLOSE
        assert trade.exit_price == D("100.9495")
        assert trade.realised == D("0.34925025")

    async def test_over_a_gap_the_stops_gap_through_check_runs_before_the_close(self) -> None:
        """The next bar after the gap opens at 97, through the stop at 98: the stop fills at
        97 x 0.988 = 95.836 and the CLOSE has nothing left to sell."""
        rig = await opened()
        await rig.sell(quiet(ENTRY_BAR))
        await rig.feed(bar(at=ENTRY_BAR + 2 * HOUR, open="97", high="97.5", low="96"))
        trade = only(rig.executor.trades)
        assert trade.exit_reason is SimulatedExit.STOP_LOSS
        assert trade.exit_price == D("95.836")
        assert trade.exit_open_through_trigger is True
        assert trade.realised == D("-2.204943")
        assert rig.executor.unsettled["queued_closes"] == ()
        await rig.feed(quiet(ENTRY_BAR + 3 * HOUR))
        assert len(rig.executor.trades) == 1

    async def test_over_a_gap_an_open_exactly_at_the_stop_is_through_it(self) -> None:
        """The boundary: an open of 98, equal to the stop, is stopped at 98 x 0.988 = 96.824,
        where a CLOSE would have sold at 98 x 0.9995 = 97.951."""
        rig = await opened()
        await rig.sell(quiet(ENTRY_BAR))
        await rig.feed(bar(at=ENTRY_BAR + 2 * HOUR, open="98", high="99", low="97"))
        trade = only(rig.executor.trades)
        assert trade.exit_reason is SimulatedExit.STOP_LOSS
        assert trade.exit_price == D("96.824")

    async def test_over_a_gap_a_take_profit_the_open_gapped_over_is_not_tested_first(self) -> None:
        """Only the stop's check runs before the CLOSE, as ruled. An open of 106, over the
        target at 104, sells at 106 x 0.9995 = 105.947 -- a bias in the strategy's favour,
        since the target would have filled at 104 x 0.988 = 102.752."""
        rig = await opened()
        await rig.sell(quiet(ENTRY_BAR))
        await rig.feed(bar(at=ENTRY_BAR + 2 * HOUR, open="106", high="107", low="105"))
        trade = only(rig.executor.trades)
        assert trade.exit_reason is SimulatedExit.CLOSE
        assert trade.exit_price == D("105.947")
        assert trade.realised == D("2.8455015")

    async def test_a_second_close_while_one_is_queued_is_ignored(self) -> None:
        rig = await opened()
        await rig.sell(quiet(ENTRY_BAR))
        await rig.sell(quiet(ENTRY_BAR))
        assert rig.executor.counts.closes_queued == 1
        assert rig.executor.counts.closes_ignored == 1

    async def test_a_close_with_no_position_is_ignored(self) -> None:
        rig = Rig()
        await rig.sell(SIGNAL_BAR)
        assert rig.executor.counts.closes_queued == 0
        assert rig.executor.counts.closes_ignored == 1


class TestAPassLeavesEveryPositionStamped:
    async def test_protection_is_active_when_legs_were_requested(self) -> None:
        rig = await opened()
        position = rig.position()
        assert position.protection is ProtectionState.ACTIVE
        assert position.last_reconciled_at == ENTRY_BAR + HOUR

    async def test_a_stop_alone_is_still_active(self) -> None:
        rig = await opened(take=None)
        assert rig.position().protection is ProtectionState.ACTIVE

    async def test_protection_is_absent_by_design_when_no_leg_was_requested(self) -> None:
        rig = await opened(stop=None, take=None)
        position = rig.position()
        assert position.protection is ProtectionState.ABSENT_BY_DESIGN
        assert position.last_reconciled_at == ENTRY_BAR + HOUR

    async def test_a_position_is_never_left_unknown_by_a_pass(self) -> None:
        """It is built UNKNOWN, as the live executor builds every position, and the pass that
        opened it promotes it before the call returns."""
        for kw in ({}, {"stop": None}, {"take": None}, {"stop": None, "take": None}):
            rig = await opened(**kw)
            assert rig.position().protection is not ProtectionState.UNKNOWN

    async def test_another_pairs_candle_stamps_every_open_position(self) -> None:
        """An ETH 5m position is stamped at T0 + 10 m, the nominal end of its entry bar. A BTC
        1m bar opening at T0 + 10 m ends at T0 + 11 m, and that becomes the ETH position's
        stamp, and the next BTC bar's end the one after. Without the pass the ETH stamp would
        stay at T0 + 10 m and age with every 1m bar until ``RiskManager.evaluate`` read it as
        stale and refused every BTC entry."""
        rig = Rig()
        eth_signal = bar(at=T0, open="100", high="101", low="99", symbol="ETHUSDT", tf="5m")
        await rig.buy(eth_signal, entry_assessment("ETHUSDT"))
        await rig.feed(
            bar(
                at=T0 + timedelta(minutes=5),
                open="100",
                high="101",
                low="99",
                symbol="ETHUSDT",
                tf="5m",
            )
        )
        eth = rig.position("ETHUSDT")
        assert eth.last_reconciled_at == T0 + timedelta(minutes=10)
        await rig.feed(
            bar(at=T0 + timedelta(minutes=10), open="100", high="101", low="99", tf="1m")
        )
        assert eth.last_reconciled_at == T0 + timedelta(minutes=11)
        await rig.feed(
            bar(at=T0 + timedelta(minutes=11), open="100", high="101", low="99", tf="1m")
        )
        assert eth.last_reconciled_at == T0 + timedelta(minutes=12)
        assert eth.protection is ProtectionState.ACTIVE


class TestTimeAndTheLedger:
    async def test_opened_at_is_the_entry_bars_open_time_and_not_the_wall_clock(self) -> None:
        rig = await opened()
        assert rig.position().opened_at == ENTRY_BAR

    async def test_entry_bar_time_is_the_signal_bars_close_time(self) -> None:
        rig = await opened()
        assert rig.position().entry_bar_time == SIGNAL_BAR.close_time

    async def test_an_exit_is_booked_at_the_bars_nominal_end(self) -> None:
        """The entry bar opens at 23:00 on 1 March, so its nominal end is 00:00 on 2 March. The
        exit is booked into the ledger of the day it ends in, and not the day it opened in."""
        rig = Rig()
        signal = bar(
            at=datetime(2024, 3, 1, 22, tzinfo=timezone.utc), open="100", high="101", low="99"
        )
        await rig.buy(signal)
        entry = bar(
            at=datetime(2024, 3, 1, 23, tzinfo=timezone.utc), open="100", high="101", low="97.5"
        )
        await rig.feed(entry)
        trade = only(rig.executor.trades)
        assert trade.exit_bar_open == datetime(2024, 3, 1, 23, tzinfo=timezone.utc)
        assert trade.exit_time == datetime(2024, 3, 2, tzinfo=timezone.utc)
        assert rig.portfolio.ledger is not None
        assert rig.portfolio.ledger.pnl_date == date(2024, 3, 2)

    async def test_the_booking_identity_is_the_lives(self) -> None:
        """realised = exit total - entry quote total - exit fee, through the unchanged
        Portfolio, and the cash moves by exactly that."""
        rig = Rig()
        await rig.buy(SIGNAL_BAR)
        await rig.feed(bar(at=ENTRY_BAR, open="100", high="101", low="97.5"))
        trade = only(rig.executor.trades)
        assert trade.entry_quote_total == trade.entry_notional + trade.entry_fee == ENTRY_TOTAL
        assert trade.realised == trade.exit_gross - trade.entry_quote_total - trade.exit_fee
        assert trade.realised == D("-1.711437")
        assert rig.portfolio.free_quote == FREE + trade.realised == D("9998.288563")
        assert rig.portfolio.ledger is not None
        assert rig.portfolio.ledger.realised_pnl == trade.realised
        assert trade.entry_fee + trade.exit_fee == D("0.098437")


class TestTheTradeLogAndItsFlags:
    async def test_a_trade_across_a_gap_is_flagged(self) -> None:
        rig = await opened()
        await rig.feed(quiet(ENTRY_BAR + 2 * HOUR))  # the slot at ENTRY_BAR + 1 h is missing
        await rig.feed(bar(at=ENTRY_BAR + 3 * HOUR, open="100", high="101", low="97.5"))
        trade = only(rig.executor.trades)
        assert trade.spans_gap is True
        assert trade.spans_short_bar is False
        assert rig.executor.counts.gaps_seen == 1

    async def test_a_gap_before_the_entry_does_not_flag_the_trade(self) -> None:
        rig = Rig()
        await rig.feed(quiet(T0 - 2 * HOUR))
        await rig.feed(SIGNAL_BAR)  # the slot at T0 - 1 h is missing: a gap, before the entry
        await rig.buy(SIGNAL_BAR)
        await rig.feed(bar(at=ENTRY_BAR, open="100", high="101", low="97.5"))
        trade = only(rig.executor.trades)
        assert trade.spans_gap is False
        assert rig.executor.counts.gaps_seen == 1

    async def test_a_registered_short_exit_bar_flags_the_trade(self) -> None:
        rig = await opened()
        await rig.feed(bar(at=ENTRY_BAR + HOUR, open="100", high="101", low="97.5", short=True))
        trade = only(rig.executor.trades)
        assert trade.spans_short_bar is True
        assert trade.spans_gap is False
        assert rig.executor.counts.short_bars_seen == 1

    async def test_a_short_entry_bar_flags_the_trade(self) -> None:
        rig = Rig()
        await rig.buy(SIGNAL_BAR)
        await rig.feed(bar(at=ENTRY_BAR, open="100", high="101", low="97.5", short=True))
        trade = only(rig.executor.trades)
        assert trade.spans_short_bar is True

    async def test_a_short_bar_before_the_entry_does_not_flag_the_trade(self) -> None:
        rig = Rig()
        await rig.feed(bar(at=T0 - HOUR, open="100", high="101", low="99", short=True))
        await rig.buy(SIGNAL_BAR)
        await rig.feed(bar(at=ENTRY_BAR, open="100", high="101", low="97.5"))
        trade = only(rig.executor.trades)
        assert trade.spans_short_bar is False

    async def test_a_trade_touching_neither_is_flagged_for_neither(self) -> None:
        rig = Rig()
        await rig.buy(SIGNAL_BAR)
        await rig.feed(bar(at=ENTRY_BAR, open="100", high="101", low="97.5"))
        trade = only(rig.executor.trades)
        assert (trade.spans_gap, trade.spans_short_bar) == (False, False)

    async def test_the_counts_are_a_detached_snapshot(self) -> None:
        rig = Rig()
        await rig.buy(SIGNAL_BAR)
        snapshot = rig.executor.counts
        snapshot.dispatched = 99
        assert rig.executor.counts.dispatched == 1

    async def test_rows_carry_exact_strings_and_iso_times(self) -> None:
        rig = Rig()
        await rig.buy(SIGNAL_BAR)
        await rig.feed(bar(at=ENTRY_BAR, open="100", high="101", low="97.5"))
        row = only(trade_rows(rig.executor.trades))
        assert row["exit_reason"] == "stop_loss"
        assert row["exit_time"] == "2024-03-01T02:00:00+00:00"
        assert row["exit_trigger"] == "98"
        assert row["take_profit"] == "104"
        assert row["spans_gap"] is False
        assert D(str(row["realised"])) == D("-1.711437")

    async def test_the_digest_is_stable_and_sensitive(self) -> None:
        async def run(params: FillParameters) -> str:
            rig = Rig(params=params)
            await rig.buy(SIGNAL_BAR)
            await rig.feed(bar(at=ENTRY_BAR, open="100", high="101", low="97.5"))
            return trade_log_digest(rig.executor.trades)

        first = await run(FillParameters())
        assert first == await run(FillParameters())
        assert first != await run(FillParameters(fee_percent=D("0.2")))
        assert len(first) == 64

    def test_the_digest_of_an_empty_log_is_the_digest_of_nothing(self) -> None:
        assert trade_log_digest([]) == hashlib.sha256(b"").hexdigest()

    def test_a_cell_cannot_be_a_float(self) -> None:
        with pytest.raises(TypeError, match="float"):
            simulated_executor._cell(1.5)


class TestTheModule:
    def test_it_satisfies_the_dispatcher_the_signal_chain_takes(self) -> None:
        assert isinstance(Rig().executor, Dispatcher)

    def test_it_reads_no_clock_of_its_own(self) -> None:
        source = Path(simulated_executor.__file__).read_text(encoding="utf-8")
        tree = ast.parse(source)
        attributes = {node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)}
        assert not attributes & {"now", "utcnow", "today", "monotonic", "perf_counter", "sleep"}
        assert "utc_now" not in source

    def test_every_position_it_builds_names_its_opened_at(self) -> None:
        """``Position.opened_at`` defaults to the wall clock, which would make two runs of the
        same history differ; the one construction site must pass it."""
        source = Path(simulated_executor.__file__).read_text(encoding="utf-8")
        calls = [
            node
            for node in ast.walk(ast.parse(source))
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "Position"
        ]
        assert len(calls) == 1
        assert "opened_at" in {keyword.arg for keyword in calls[0].keywords}
