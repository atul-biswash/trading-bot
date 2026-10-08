"""The fill model (M5m S2): P99, R-B2, R-P1 and R-W as pure functions, hand-computed.

Every expected figure below is worked by hand from the ruled default percents -- entry and
``CLOSE`` slippage 0.05%, stop slippage 1.20%, fee 0.1% a leg -- so a test fails on the
arithmetic and not on a re-derivation of it:

* a stop at 98 filled at the trigger: 98 x 0.988 = 96.824
* the same stop gapped through at an open of 97: 97 x 0.988 = 95.836
* a take-profit at 104: 104 x 0.988 = 102.752 (never 105 x 0.988 = 103.74 on a gap over it)
* an entry at an open of 100: 100 x 1.0005 = 100.05
* a ``CLOSE`` at an open of 100: 100 x 0.9995 = 99.95
"""

from __future__ import annotations

import ast
import dataclasses
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

import pytest

from trading_bot.backtesting import fill_model
from trading_bot.backtesting.fill_model import (
    EntryOutcome,
    FillParameters,
    book_entry,
    book_exit,
    fill_close,
    fill_entry,
    fill_protective,
)
from trading_bot.config.models import BacktestConfig
from trading_bot.core.enums import PositionSide, ProtectionState
from trading_bot.core.models import Candle, Fee, Position
from trading_bot.core.portfolio import Portfolio
from trading_bot.risk.rules import ExitReason, should_exit

D = Decimal
T0 = datetime(2024, 3, 1, tzinfo=timezone.utc)
HOUR = timedelta(hours=1)
PARAMS = FillParameters()


def bar(
    *, open: str, high: str, low: str, close: str | None = None, opened: datetime = T0
) -> Candle:
    return Candle(
        symbol="BTCUSDT",
        timeframe="1h",
        open_time=opened,
        close_time=opened + HOUR - timedelta(milliseconds=1),
        open=D(open),
        high=D(high),
        low=D(low),
        close=D(close if close is not None else open),
        volume=D(1),
    )


class TestTheParametersAndTheirDefaults:
    def test_the_defaults_are_the_rulings(self) -> None:
        assert PARAMS.fee_percent == D("0.1")
        assert PARAMS.slippage_percent == D("0.05")
        assert PARAMS.stop_slippage_percent == D("1.20")
        for name in ("fee_percent", "slippage_percent", "stop_slippage_percent"):
            assert type(getattr(PARAMS, name)) is D

    def test_they_come_from_a_backtest_config(self) -> None:
        config = BacktestConfig(
            start_date="2024-01-01",
            end_date="2024-02-01",
            fee_percent=0.075,
            slippage_percent=0.2,
            stop_slippage_percent=0.66,
        )
        params = FillParameters.from_config(config)
        assert (params.fee_percent, params.slippage_percent, params.stop_slippage_percent) == (
            D("0.075"),
            D("0.2"),
            D("0.66"),
        )

    @pytest.mark.parametrize("name", ("fee_percent", "slippage_percent", "stop_slippage_percent"))
    def test_a_float_is_refused_not_coerced(self, name: str) -> None:
        with pytest.raises(TypeError, match=f"{name} must be a Decimal"):
            FillParameters(**{name: 0.1})

    @pytest.mark.parametrize("name", ("fee_percent", "slippage_percent", "stop_slippage_percent"))
    @pytest.mark.parametrize("bad", (D("-0.01"), D(100), D("NaN"), D("Infinity")))
    def test_a_percent_outside_zero_to_below_a_hundred_is_refused(
        self, name: str, bad: Decimal
    ) -> None:
        with pytest.raises(ValueError, match=name):
            FillParameters(**{name: bad})

    @pytest.mark.parametrize("name", ("fee_percent", "slippage_percent", "stop_slippage_percent"))
    def test_zero_and_just_under_a_hundred_are_accepted(self, name: str) -> None:
        assert getattr(FillParameters(**{name: D(0)}), name) == D(0)
        assert getattr(FillParameters(**{name: D("99.99")}), name) == D("99.99")

    def test_the_parameters_are_frozen(self) -> None:
        with pytest.raises(dataclasses.FrozenInstanceError):
            PARAMS.fee_percent = D(0)


class TestAnEntryFillsAtTheNextOpenPlusSlippage:
    def test_it_fills_at_the_open_plus_slippage_not_at_the_limit(self) -> None:
        fill = fill_entry(
            entry_limit=D("101"),
            placed_at=T0,
            next_bar=bar(open="100.00", high="101", low="99", close="100.5"),
            params=PARAMS,
        )
        assert fill.outcome is EntryOutcome.FILLED
        assert fill.price == D("100.05")  # 100 x 1.0005, and not the limit of 101

    def test_the_bars_close_and_high_are_not_the_fill(self) -> None:
        fill = fill_entry(
            entry_limit=D("110"),
            placed_at=T0,
            next_bar=bar(open="100.00", high="106", low="99", close="105"),
            params=PARAMS,
        )
        assert fill.price == D("100.05")

    def test_a_price_exactly_at_the_limit_fills(self) -> None:
        """100.00 x 1.001 is exactly 100.10, the limit: the comparison is at-or-below."""
        fill = fill_entry(
            entry_limit=D("100.10"),
            placed_at=T0,
            next_bar=bar(open="100.00", high="101", low="99"),
            params=FillParameters(slippage_percent=D("0.10")),
        )
        assert fill.outcome is EntryOutcome.FILLED
        assert fill.price == D("100.100")

    def test_a_price_a_tick_above_the_limit_is_refused(self) -> None:
        """100.01 x 1.001 is 100.11001, above 100.10: the FOK is refused, as live."""
        fill = fill_entry(
            entry_limit=D("100.10"),
            placed_at=T0,
            next_bar=bar(open="100.01", high="101", low="99"),
            params=FillParameters(slippage_percent=D("0.10")),
        )
        assert fill.outcome is EntryOutcome.REFUSED
        assert fill.price is None
        assert "100.11001" in fill.detail

    def test_a_wide_gap_up_is_refused_not_filled_later_in_the_bar(self) -> None:
        fill = fill_entry(
            entry_limit=D("100.10"),
            placed_at=T0,
            next_bar=bar(open="105", high="106", low="100", close="100.05"),
            params=PARAMS,
        )
        assert fill.outcome is EntryOutcome.REFUSED

    def test_slippage_is_adverse_to_a_buyer_and_zero_slippage_is_the_open(self) -> None:
        loose = fill_entry(
            entry_limit=D("200"),
            placed_at=T0,
            next_bar=bar(open="100", high="101", low="99"),
            params=FillParameters(slippage_percent=D(0)),
        )
        assert loose.price == D("100")
        wide = fill_entry(
            entry_limit=D("200"),
            placed_at=T0,
            next_bar=bar(open="100", high="101", low="99"),
            params=FillParameters(slippage_percent=D(2)),
        )
        assert wide.price == D("102.00")

    def test_a_missing_next_bar_expires_the_order(self) -> None:
        fill = fill_entry(entry_limit=D("101"), placed_at=T0, next_bar=None, params=PARAMS)
        assert fill.outcome is EntryOutcome.EXPIRED
        assert fill.price is None

    def test_a_next_bar_after_a_missing_slot_expires_the_order(self) -> None:
        """The slot at T0 is missing and the next bar opens an hour later: no fill, even though
        that bar's price would be inside the limit."""
        fill = fill_entry(
            entry_limit=D("101"),
            placed_at=T0,
            next_bar=bar(open="100", high="101", low="99", opened=T0 + HOUR),
            params=PARAMS,
        )
        assert fill.outcome is EntryOutcome.EXPIRED
        assert fill.price is None
        assert "missing" in fill.detail

    def test_a_bar_that_opened_before_the_order_is_a_caller_error(self) -> None:
        with pytest.raises(ValueError, match="before the order was placed"):
            fill_entry(
                entry_limit=D("101"),
                placed_at=T0,
                next_bar=bar(open="100", high="101", low="99", opened=T0 - HOUR),
                params=PARAMS,
            )

    def test_a_limit_that_is_not_positive_is_refused(self) -> None:
        with pytest.raises(ValueError, match="entry_limit"):
            fill_entry(
                entry_limit=D(0),
                placed_at=T0,
                next_bar=bar(open="100", high="101", low="99"),
                params=PARAMS,
            )


class TestTheEntryBookingFoldsTheFeeIntoTheQuoteTotal:
    def test_the_entry_figures_are_hand_computed(self) -> None:
        booking = book_entry(quantity=D("0.5"), price=D("100.05"), params=PARAMS)
        assert booking.notional == D("50.025")  # 0.5 x 100.05
        assert booking.fee == D("0.050025")  # 0.1% of 50.025
        assert booking.quote_total == D("50.075025")  # the notional plus the fee
        assert (booking.quantity, booking.price) == (D("0.5"), D("100.05"))

    def test_the_fee_is_on_the_notional_and_the_total_includes_it(self) -> None:
        booking = book_entry(
            quantity=D(2), price=D(10), params=FillParameters(fee_percent=D("0.5"))
        )
        assert booking.fee == D("0.100")  # 0.5% of 20
        assert booking.quote_total == D("20.100")

    def test_a_zero_fee_leaves_the_total_equal_to_the_notional(self) -> None:
        booking = book_entry(quantity=D(2), price=D(10), params=FillParameters(fee_percent=D(0)))
        assert booking.fee == D(0)
        assert booking.quote_total == booking.notional == D(20)

    @pytest.mark.parametrize(("quantity", "price"), ((D(0), D(1)), (D(1), D(0)), (D(-1), D(1))))
    def test_a_non_positive_entry_quantity_or_price_is_refused(
        self, quantity: Decimal, price: Decimal
    ) -> None:
        with pytest.raises(ValueError):
            book_entry(quantity=quantity, price=price, params=PARAMS)


class TestAStopFillsAtItsTriggerOrAtAnOpenThatGappedThroughIt:
    STOP, TAKE = D("98"), D("104")

    def test_nothing_touched_is_none(self) -> None:
        assert (
            fill_protective(
                stop_loss=self.STOP,
                take_profit=self.TAKE,
                bar=bar(open="100", high="103", low="99"),
                params=PARAMS,
            )
            is None
        )

    def test_a_low_through_the_stop_fills_at_the_trigger_less_slippage(self) -> None:
        fill = fill_protective(
            stop_loss=self.STOP,
            take_profit=self.TAKE,
            bar=bar(open="100", high="101", low="97.5"),
            params=PARAMS,
        )
        assert fill is not None
        assert fill.reason is ExitReason.STOP_LOSS
        assert fill.price == D("96.824")  # 98 x 0.988
        assert fill.trigger == D("98")
        assert fill.open_through_trigger is False

    def test_a_low_exactly_at_the_stop_triggers_it(self) -> None:
        fill = fill_protective(
            stop_loss=self.STOP,
            take_profit=None,
            bar=bar(open="100", high="101", low="98"),
            params=PARAMS,
        )
        assert fill is not None
        assert fill.price == D("96.824")

    def test_a_low_a_tick_above_the_stop_does_not(self) -> None:
        assert (
            fill_protective(
                stop_loss=self.STOP,
                take_profit=None,
                bar=bar(open="100", high="101", low="98.01"),
                params=PARAMS,
            )
            is None
        )

    def test_an_open_below_the_stop_fills_at_the_open_less_slippage(self) -> None:
        """R-P1 and R-W(b): the open is the first price the stop could trade at, and the stop
        slippage is charged on it as well. The double count is accepted and documented."""
        fill = fill_protective(
            stop_loss=self.STOP,
            take_profit=self.TAKE,
            bar=bar(open="97", high="97.5", low="96"),
            params=PARAMS,
        )
        assert fill is not None
        assert fill.price == D("95.836")  # 97 x 0.988, and not 98 x 0.988
        assert fill.open_through_trigger is True

    def test_an_open_exactly_at_the_stop_counts_as_through_it(self) -> None:
        """The price is the same either way, 98 x 0.988, so only the flag shows the branch."""
        fill = fill_protective(
            stop_loss=self.STOP,
            take_profit=None,
            bar=bar(open="98", high="99", low="97"),
            params=PARAMS,
        )
        assert fill is not None
        assert fill.price == D("96.824")
        assert fill.open_through_trigger is True

    def test_the_gap_rule_applies_on_every_bar_not_only_after_a_data_gap(self) -> None:
        """R-W(b): the bar here follows the previous slot with no missing bar at all."""
        fill = fill_protective(
            stop_loss=self.STOP,
            take_profit=None,
            bar=bar(open="90", high="91", low="89", opened=T0 + HOUR),
            params=PARAMS,
        )
        assert fill is not None
        assert fill.price == D("88.920")  # 90 x 0.988

    def test_the_stop_slippage_is_the_stop_parameter_alone(self) -> None:
        wild = FillParameters(slippage_percent=D(5), fee_percent=D(5))
        fill = fill_protective(
            stop_loss=self.STOP,
            take_profit=None,
            bar=bar(open="100", high="101", low="97"),
            params=wild,
        )
        assert fill is not None
        assert fill.price == D("96.824")

    def test_zero_stop_slippage_fills_exactly_at_the_trigger(self) -> None:
        fill = fill_protective(
            stop_loss=self.STOP,
            take_profit=None,
            bar=bar(open="100", high="101", low="97"),
            params=FillParameters(stop_slippage_percent=D(0)),
        )
        assert fill is not None
        assert fill.price == D("98")

    def test_a_different_stop_slippage_moves_the_price(self) -> None:
        fill = fill_protective(
            stop_loss=self.STOP,
            take_profit=None,
            bar=bar(open="100", high="101", low="97"),
            params=FillParameters(stop_slippage_percent=D("0.66")),
        )
        assert fill is not None
        assert fill.price == D("97.3532")  # 98 x 0.9934 = 98 - 0.6468


class TestATakeProfitFillsAtItsTriggerAndNeverAtABetterOpen:
    STOP, TAKE = D("98"), D("104")

    def test_a_high_through_the_target_fills_at_the_trigger_less_stop_slippage(self) -> None:
        fill = fill_protective(
            stop_loss=self.STOP,
            take_profit=self.TAKE,
            bar=bar(open="100", high="104.5", low="99"),
            params=PARAMS,
        )
        assert fill is not None
        assert fill.reason is ExitReason.TAKE_PROFIT
        assert fill.price == D("102.752")  # 104 x 0.988, R-W(a)
        assert fill.trigger == D("104")
        assert fill.open_through_trigger is False

    def test_a_high_exactly_at_the_target_triggers_it(self) -> None:
        fill = fill_protective(
            stop_loss=None,
            take_profit=self.TAKE,
            bar=bar(open="100", high="104", low="99"),
            params=PARAMS,
        )
        assert fill is not None
        assert fill.price == D("102.752")

    def test_a_high_a_tick_below_the_target_does_not(self) -> None:
        assert (
            fill_protective(
                stop_loss=None,
                take_profit=self.TAKE,
                bar=bar(open="100", high="103.99", low="99"),
                params=PARAMS,
            )
            is None
        )

    def test_an_open_over_the_target_is_not_credited_the_gap(self) -> None:
        """R-P1: filled at the trigger. 105 x 0.988 = 103.74 would credit the gap."""
        fill = fill_protective(
            stop_loss=self.STOP,
            take_profit=self.TAKE,
            bar=bar(open="105", high="106", low="104.5"),
            params=PARAMS,
        )
        assert fill is not None
        assert fill.price == D("102.752")
        assert fill.open_through_trigger is True

    def test_an_open_exactly_at_the_target_counts_as_through_it(self) -> None:
        """The price is the trigger's either way, so only the flag shows the branch."""
        fill = fill_protective(
            stop_loss=None,
            take_profit=self.TAKE,
            bar=bar(open="104", high="105", low="103"),
            params=PARAMS,
        )
        assert fill is not None
        assert fill.price == D("102.752")
        assert fill.open_through_trigger is True

    def test_the_take_profit_is_charged_the_stop_slippage_not_the_entry_slippage(self) -> None:
        fill = fill_protective(
            stop_loss=None,
            take_profit=self.TAKE,
            bar=bar(open="100", high="105", low="99"),
            params=FillParameters(slippage_percent=D(9), stop_slippage_percent=D(1)),
        )
        assert fill is not None
        assert fill.price == D("102.96")  # 104 x 0.99

    def test_zero_slippage_fills_a_target_exactly_at_the_trigger(self) -> None:
        fill = fill_protective(
            stop_loss=None,
            take_profit=self.TAKE,
            bar=bar(open="100", high="105", low="99"),
            params=FillParameters(stop_slippage_percent=D(0)),
        )
        assert fill is not None
        assert fill.price == D("104")


class TestWhenOneBarTouchesBothTheStopWins:
    STOP, TAKE = D("98"), D("104")

    def test_both_touched_is_a_stop_at_the_stops_price(self) -> None:
        fill = fill_protective(
            stop_loss=self.STOP,
            take_profit=self.TAKE,
            bar=bar(open="100", high="104.5", low="97.5"),
            params=PARAMS,
        )
        assert fill is not None
        assert fill.reason is ExitReason.STOP_LOSS
        assert fill.price == D("96.824")

    def test_an_open_over_the_target_with_a_low_through_the_stop_is_still_a_stop(self) -> None:
        fill = fill_protective(
            stop_loss=self.STOP,
            take_profit=self.TAKE,
            bar=bar(open="105", high="106", low="97"),
            params=PARAMS,
        )
        assert fill is not None
        assert fill.reason is ExitReason.STOP_LOSS
        assert fill.open_through_trigger is False
        assert fill.price == D("96.824")

    @pytest.mark.parametrize(
        ("open_", "high", "low"),
        (
            ("100", "103", "99"),  # neither
            ("100", "101", "97.5"),  # the stop only
            ("100", "104.5", "99"),  # the target only
            ("100", "104.5", "97.5"),  # both
            ("97", "97.5", "96"),  # the open gapped through the stop
            ("105", "106", "104.5"),  # the open gapped over the target
            ("100", "104", "98"),  # both touched exactly
        ),
    )
    def test_the_decision_agrees_with_the_live_should_exit(
        self, open_: str, high: str, low: str
    ) -> None:
        """``should_exit`` decides which rule fires at ONE price and prefers the stop. The
        backtest tests the stop at the bar's low, then the target at its high, and the two
        must name the same rule."""
        position = Position(
            symbol="BTCUSDT",
            side=PositionSide.LONG,
            quantity=D("0.5"),
            entry_price=D("100.10"),
            entry_bar_time=T0,
            protection=ProtectionState.ACTIVE,
            stop_loss=self.STOP,
            take_profit=self.TAKE,
        )
        the_bar = bar(open=open_, high=high, low=low)
        live = should_exit(position=position, price=the_bar.low) or should_exit(
            position=position, price=the_bar.high
        )
        ours = fill_protective(
            stop_loss=self.STOP, take_profit=self.TAKE, bar=the_bar, params=PARAMS
        )
        assert (None if ours is None else ours.reason) == (None if live is None else live.reason)


class TestOnlyTheConfiguredLegsAreEvaluated:
    def test_with_no_levels_nothing_ever_triggers(self) -> None:
        assert (
            fill_protective(
                stop_loss=None,
                take_profit=None,
                bar=bar(open="100", high="1000", low="1"),
                params=PARAMS,
            )
            is None
        )

    def test_with_only_a_stop_a_high_over_any_target_is_ignored(self) -> None:
        assert (
            fill_protective(
                stop_loss=D("98"),
                take_profit=None,
                bar=bar(open="100", high="1000", low="99"),
                params=PARAMS,
            )
            is None
        )

    def test_with_only_a_target_a_low_under_any_stop_is_ignored(self) -> None:
        assert (
            fill_protective(
                stop_loss=None,
                take_profit=D("104"),
                bar=bar(open="100", high="103", low="1"),
                params=PARAMS,
            )
            is None
        )

    @pytest.mark.parametrize(
        ("stop", "take"),
        ((D(0), D(104)), (D(-1), D(104)), (D(98), D(0)), (D(104), D(98)), (D(100), D(100))),
    )
    def test_levels_that_are_not_positive_or_not_ordered_are_refused(
        self, stop: Decimal, take: Decimal
    ) -> None:
        with pytest.raises(ValueError):
            fill_protective(
                stop_loss=stop,
                take_profit=take,
                bar=bar(open="100", high="101", low="99"),
                params=PARAMS,
            )


class TestACloseSellsAtTheNextOpenLessSlippage:
    def test_it_is_the_open_less_the_entry_slippage(self) -> None:
        assert fill_close(
            bar=bar(open="100", high="101", low="99", close="100.5"), params=PARAMS
        ) == (
            D("99.9500")  # 100 x 0.9995
        )

    def test_the_close_and_low_are_not_the_fill(self) -> None:
        price = fill_close(bar=bar(open="100", high="110", low="90", close="95"), params=PARAMS)
        assert price == D("99.9500")

    def test_the_stop_slippage_does_not_apply(self) -> None:
        price = fill_close(
            bar=bar(open="100", high="101", low="99"),
            params=FillParameters(slippage_percent=D(1), stop_slippage_percent=D(50)),
        )
        assert price == D("99.00")

    def test_zero_slippage_is_the_open(self) -> None:
        assert fill_close(
            bar=bar(open="100", high="101", low="99"),
            params=FillParameters(slippage_percent=D(0)),
        ) == D("100")


class TestTheExitBooking:
    def test_the_exit_figures_are_hand_computed(self) -> None:
        booking = book_exit(quantity=D("0.5"), price=D("96.824"), params=PARAMS)
        assert booking.gross == D("48.412")  # 0.5 x 96.824, the exit quote total
        assert booking.fee == D("0.048412")  # 0.1% of the gross
        assert booking.net == D("48.363588")
        assert (booking.quantity, booking.price) == (D("0.5"), D("96.824"))

    def test_the_fee_is_on_the_gross_and_not_on_the_net(self) -> None:
        booking = book_exit(quantity=D(1), price=D(1000), params=FillParameters(fee_percent=D(10)))
        assert booking.fee == D(100)  # 10% of 1000; 10% of the net would be 90
        assert booking.net == D(900)

    def test_a_zero_fee_leaves_the_net_equal_to_the_gross(self) -> None:
        booking = book_exit(quantity=D(2), price=D(10), params=FillParameters(fee_percent=D(0)))
        assert booking.net == booking.gross == D(20)

    @pytest.mark.parametrize(("quantity", "price"), ((D(0), D(1)), (D(1), D(0)), (D(1), D(-1))))
    def test_a_non_positive_exit_quantity_or_price_is_refused(
        self, quantity: Decimal, price: Decimal
    ) -> None:
        with pytest.raises(ValueError):
            book_exit(quantity=quantity, price=price, params=PARAMS)


class TestTheBookingsComposeThroughThePortfolio:
    def test_a_stopped_out_round_trip_is_net_of_both_fees(self) -> None:
        """Entry at 100.05 for 0.5, stopped at 98: the entry costs 50.075025 with its fee, the
        exit returns 48.412 less a fee of 0.048412, and the realised loss is
        48.412 - 50.075025 - 0.048412 = -1.711437."""
        entry = book_entry(quantity=D("0.5"), price=D("100.05"), params=PARAMS)
        fill = fill_protective(
            stop_loss=D("98"),
            take_profit=D("104"),
            bar=bar(open="100", high="101", low="97.5"),
            params=PARAMS,
        )
        assert fill is not None
        exit_ = book_exit(quantity=D("0.5"), price=fill.price, params=PARAMS)

        portfolio = Portfolio(quote_asset="USDT", free_quote=D(10000))
        portfolio.open_position(
            Position(
                symbol="BTCUSDT",
                side=PositionSide.LONG,
                quantity=D("0.5"),
                entry_price=D("100.10"),
                entry_fill_price=entry.price,
                entry_quote_total=entry.quote_total,
                entry_bar_time=T0,
                protection=ProtectionState.ACTIVE,
            ),
            cost=entry.quote_total,
        )
        assert portfolio.free_quote == D("9949.924975")
        realised = portfolio.close_position(
            "BTCUSDT",
            exit_quote_total=exit_.gross,
            now=T0 + HOUR,
            fee=Fee(amount=exit_.fee, asset="USDT"),
        )
        assert realised == D("-1.711437")
        assert portfolio.free_quote == D("9998.288563")
        assert entry.fee + exit_.fee == D("0.098437")  # what S3 sums from the trade log


class TestTheModuleIsPure:
    SOURCE = Path(fill_model.__file__).read_text(encoding="utf-8")

    def test_it_reads_no_clock(self) -> None:
        tree = ast.parse(self.SOURCE)
        imported = {
            alias.name.split(".")[0]
            for node in ast.walk(tree)
            if isinstance(node, ast.Import)
            for alias in node.names
        } | {
            (node.module or "").split(".")[0]
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom)
        }
        assert "time" not in imported
        assert "utc_now" not in self.SOURCE
        attributes = {node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)}
        assert not attributes & {"now", "utcnow", "today", "monotonic", "perf_counter", "sleep"}

    def test_it_contains_no_float_literal(self) -> None:
        tree = ast.parse(self.SOURCE)
        floats = [
            node.value
            for node in ast.walk(tree)
            if isinstance(node, ast.Constant) and isinstance(node.value, float)
        ]
        assert floats == []

    def test_it_performs_no_input_or_output(self) -> None:
        tree = ast.parse(self.SOURCE)
        called = {
            node.func.id
            for node in ast.walk(tree)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
        }
        assert not called & {"open", "print", "input", "exec", "eval"}
