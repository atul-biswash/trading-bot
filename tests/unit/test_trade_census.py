"""``scripts/trade_census.py``: the matcher, the figures, and the refusals.

Every log here is a few synthetic lines whose figures are worked by hand in the test,
because a census whose expected values were taken from its own output proves nothing.
The expensive failures are silent ones: a booking paired with the wrong placement, and
a profit factor with the wrong sign or denominator, each yield a plausible table. The
tests for those two are written so that each plausible-looking mutation changes a
figure a test pins.
"""

from __future__ import annotations

import hashlib
import sys
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

import trade_census as tc

from trading_bot.engine.modes import _EVENT_EXIT_BOOKED as MODES_EXIT_BOOKED
from trading_bot.execution.executor import _EVENT_CLOSE_BOOKED as EXECUTOR_CLOSE_BOOKED
from trading_bot.execution.executor import _EVENT_PLACED as EXECUTOR_PLACED
from trading_bot.execution.reconciliation_driver import _EVENT_BOOKED as DRIVER_BOOKED

D = Decimal
UTC = timezone.utc
ZONED = "2026-09-10T01:00:03Z"
BAR = "2026-09-10T00:00:59.999000+00:00"
CANDLE = "2026-09-10T01:00:59.999000+00:00"


def placed(
    symbol: str = "BTCUSDT",
    quantity: str = "1",
    entry: str = "100",
    stop: str = "98",
    bar: str = BAR,
    stamp: str = "2026-09-10T00:01:03Z",
) -> str:
    return (
        f"{stamp} | INFO     | pid=1 | trading_bot.execution.executor | Order list placed "
        f"event=order_placed symbol={symbol} quantity={quantity} entry={entry} "
        f"stop_loss={stop} order_list_id=7 list_client_order_id=tb1-{symbol}-1-0-L "
        f"entry_bar_time={bar}"
    )


def closed(
    symbol: str = "BTCUSDT",
    order_id: str = "11",
    quantity: str = "1",
    total: str = "101",
    realised: str = "1",
    candle: str = CANDLE,
    stamp: str = ZONED,
    extra: str = "",
) -> str:
    return (
        f"{stamp} | INFO     | pid=1 | trading_bot.execution.executor | Closed {symbol} "
        f"event=close_booked symbol={symbol} order_id={order_id} quantity={quantity} "
        f"quote_total={total} realised={realised} candle_time={candle}{extra}"
    )


def exited(
    symbol: str = "BTCUSDT",
    order_id: str = "21",
    quantity: str = "1",
    total: str = "95",
    realised: str = "-5",
    stamp: str = ZONED,
    extra: str = "",
) -> str:
    return (
        f"{stamp} | INFO     | pid=1 | trading_bot.execution.reconciliation_driver | "
        f"Booked exit for {symbol} event=exit_booked symbol={symbol} order_id={order_id} "
        f"quantity={quantity} quote_total={total} realised={realised}{extra}"
    )


def booted(
    symbol: str = "BTCUSDT",
    order_id: str = "31",
    quantity: str = "1",
    total: str = "95",
    realised: str = "-5",
    stamp: str = ZONED,
    extra: str = " leg=SL",
) -> str:
    return (
        f"{stamp} | WARNING  | pid=1 | trading_bot.engine.modes | an exit that filled while "
        f"the bot was down was BOOKED at boot event=boot_exit_booked symbol={symbol} "
        f"order_id={order_id} quantity={quantity} quote_total={total} realised={realised}"
        f"{extra}"
    )


def trades_of(lines: list[str], quote_asset: str = "USDT") -> tuple[tc.Trade, ...]:
    return tc.build_trades(tc.parse_capture(lines), quote_asset)


class TestEventNamesMirrorTheTree:
    """The arming condition on S0: renaming one of the four constants must fail a test."""

    def test_each_event_name_equals_the_constant_it_mirrors(self) -> None:
        assert tc.EVENT_PLACED == EXECUTOR_PLACED
        assert tc.EVENT_CLOSE_BOOKED == EXECUTOR_CLOSE_BOOKED
        assert tc.EVENT_EXIT_BOOKED == DRIVER_BOOKED
        assert tc.EVENT_BOOT_EXIT_BOOKED == MODES_EXIT_BOOKED

    def test_the_four_names_are_distinct(self) -> None:
        names = {
            tc.EVENT_PLACED,
            tc.EVENT_CLOSE_BOOKED,
            tc.EVENT_EXIT_BOOKED,
            tc.EVENT_BOOT_EXIT_BOOKED,
        }
        assert len(names) == 4


class TestParsing:
    def test_a_placement_is_read_exactly_as_decimals(self) -> None:
        parsed = tc.parse_capture(["unrelated banner line", placed(quantity="0.02310000")])
        (placement,) = parsed.placements
        assert placement.symbol == "BTCUSDT"
        assert placement.quantity == D("0.02310000")
        assert type(placement.quantity) is D
        assert placement.entry == D("100")
        assert placement.stop_loss == D("98")
        assert placement.entry_bar_time == datetime(2026, 9, 10, 0, 0, 59, 999000, tzinfo=UTC)
        assert placement.line_no == 2
        assert parsed.bookings == ()
        assert parsed.anomalies == ()

    def test_a_booking_is_read_with_its_optional_fields_absent_not_defaulted(self) -> None:
        parsed = tc.parse_capture([closed()])
        (booking,) = parsed.bookings
        assert booking.fee is None
        assert booking.fee_asset is None
        assert booking.entry_quote_total is None
        assert booking.filled_at is None
        assert booking.leg_label is None
        assert booking.candle_time == datetime(2026, 9, 10, 1, 0, 59, 999000, tzinfo=UTC)

    def test_a_zoned_and_a_naive_stamp_are_both_read_and_kept_distinct(self) -> None:
        parsed = tc.parse_capture(
            [
                closed(stamp="2026-09-06T00:15:03Z"),
                closed(order_id="12", stamp="2026-09-06 06:15:03"),
            ]
        )
        zoned, naive = parsed.bookings
        assert zoned.stamp == datetime(2026, 9, 6, 0, 15, 3, tzinfo=UTC)
        assert naive.stamp == datetime(2026, 9, 6, 6, 15, 3)
        assert naive.stamp.tzinfo is None

    def test_every_booking_event_is_a_booking_and_nothing_else_is(self) -> None:
        other = "2026-09-10T01:00:03Z | INFO     | x | y | z event=engine_stopped clean=True"
        parsed = tc.parse_capture([other, closed(), exited(), booted()])
        assert [booking.event for booking in parsed.bookings] == [
            "close_booked",
            "exit_booked",
            "boot_exit_booked",
        ]

    @pytest.mark.parametrize(
        ("line", "reason"),
        [
            (closed().replace(" quote_total=101", ""), "missing field quote_total"),
            (closed(total="oops"), "is not a decimal"),
            (closed(total="NaN"), "is not finite"),
            (closed(total="Infinity"), "is not finite"),
            (closed(quantity="0"), "is not positive"),
            (closed(quantity="-1"), "is not positive"),
            (closed(candle="2026-09-10T01:00:59"), "carries no zone"),
            (closed(candle="not-a-time"), "is not a timestamp"),
            ("event=close_booked symbol=BTCUSDT", "missing field order_id"),
            (closed(stamp="garbled"), "no leading timestamp"),
        ],
    )
    def test_a_line_that_cannot_be_read_is_an_anomaly_and_not_a_booking(
        self, line: str, reason: str
    ) -> None:
        parsed = tc.parse_capture([line])
        assert parsed.bookings == ()
        (anomaly,) = parsed.anomalies
        assert reason in anomaly.reason
        assert anomaly.line_no == 1

    def test_a_placement_with_a_non_positive_stop_is_an_anomaly(self) -> None:
        parsed = tc.parse_capture([placed(stop="0")])
        assert parsed.placements == ()
        assert "is not positive" in parsed.anomalies[0].reason

    def test_a_placement_with_no_entry_bar_time_is_an_anomaly(self) -> None:
        line = placed().replace(f" entry_bar_time={BAR}", "")
        parsed = tc.parse_capture([line])
        assert parsed.placements == ()
        assert parsed.anomalies[0].reason == "missing field entry_bar_time"

    def test_a_second_booking_of_the_same_order_is_an_anomaly_and_is_not_counted(self) -> None:
        parsed = tc.parse_capture([closed(), closed(), closed(symbol="ETHUSDT")])
        assert len(parsed.bookings) == 2
        (anomaly,) = parsed.anomalies
        assert anomaly.line_no == 2
        assert "duplicate booking of BTCUSDT order 11" in anomaly.reason


class TestMatching:
    """A booking takes the latest placement of its symbol after the symbol's last booking."""

    def match(self, lines: list[str]) -> list[int | None]:
        parsed = tc.parse_capture(lines)
        matched = tc.match_placements(parsed.placements, parsed.bookings)
        result: list[int | None] = []
        for booking in parsed.bookings:
            placement = matched[booking.line_no]
            result.append(None if placement is None else placement.line_no)
        return result

    def test_alternating_placements_and_bookings_pair_one_to_one(self) -> None:
        lines = [placed(), closed(), placed(), closed(order_id="12")]
        assert self.match(lines) == [1, 3]

    def test_a_placement_that_never_filled_is_skipped_not_paired(self) -> None:
        lines = [placed(quantity="2"), placed(quantity="3"), placed(quantity="1"), closed()]
        assert self.match(lines) == [3]

    def test_the_latest_placement_wins_among_equals(self) -> None:
        lines = [placed(entry="100"), placed(entry="101"), closed()]
        assert self.match(lines) == [2]

    def test_a_booking_with_no_placement_after_the_previous_booking_is_unmatched(self) -> None:
        lines = [placed(), placed(), closed(), closed(order_id="12")]
        assert self.match(lines) == [2, None]

    def test_an_equal_quantity_beats_a_later_placement_of_another_quantity(self) -> None:
        lines = [placed(quantity="1"), placed(quantity="5"), closed(quantity="1")]
        assert self.match(lines) == [1]

    def test_with_no_equal_quantity_the_latest_is_taken_and_flagged(self) -> None:
        lines = [placed(quantity="2"), placed(quantity="3"), closed(quantity="1")]
        (trade,) = trades_of(lines)
        assert trade.placement is not None
        assert trade.placement.quantity == D("3")
        assert trade.quantity_matches is False

    def test_an_exact_quantity_match_is_recorded_as_one(self) -> None:
        (trade,) = trades_of([placed(), closed()])
        assert trade.quantity_matches is True

    def test_two_symbols_interleaved_do_not_pair_across(self) -> None:
        lines = [
            placed(symbol="BTCUSDT"),
            placed(symbol="ETHUSDT", quantity="4"),
            closed(symbol="ETHUSDT", order_id="12", quantity="4", total="204", realised="4"),
            closed(symbol="BTCUSDT"),
        ]
        assert self.match(lines) == [2, 1]

    def test_two_symbols_with_the_same_quantity_do_not_pair_across(self) -> None:
        lines = [placed(symbol="BTCUSDT"), placed(symbol="ETHUSDT"), closed(symbol="BTCUSDT")]
        assert self.match(lines) == [1]

    def test_a_second_booking_with_no_placement_since_the_first_is_not_given_the_first_ones(
        self,
    ) -> None:
        lines = [placed(), closed(), closed(order_id="12")]
        assert self.match(lines) == [1, None]

    def test_a_boot_booking_is_matched_like_any_other(self) -> None:
        lines = [placed(), booted()]
        assert self.match(lines) == [1]


class TestEntryTotalAndReturn:
    def test_without_a_fee_or_a_stated_total_it_is_the_exit_total_less_the_realised(self) -> None:
        (trade,) = trades_of([placed(), closed(total="101", realised="1")])
        assert trade.entry_quote_total == D("100")
        assert trade.entry_total_source == "derived"
        assert trade.return_pct == D("1")

    def test_a_fee_in_the_quote_asset_is_taken_out_of_the_identity(self) -> None:
        extra = " fee=0.5 fee_asset=USDT"
        (trade,) = trades_of([placed(), closed(total="101", realised="0.5", extra=extra)])
        assert trade.entry_quote_total == D("100")

    def test_a_zero_fee_at_the_venue_exponent_changes_nothing(self) -> None:
        extra = " fee=0E-8 fee_asset=USDT"
        (trade,) = trades_of([placed(), closed(total="101", realised="1", extra=extra)])
        assert trade.entry_quote_total == D("100")

    def test_a_fee_in_another_asset_leaves_the_total_and_the_return_unknown(self) -> None:
        extra = " fee=0.001 fee_asset=BNB"
        (trade,) = trades_of([placed(), closed(extra=extra)])
        assert trade.entry_quote_total is None
        assert trade.return_pct is None
        assert "fee not in the quote asset" in trade.entry_total_source

    def test_the_quote_asset_is_a_parameter(self) -> None:
        extra = " fee=0.001 fee_asset=BNB"
        (trade,) = trades_of([placed(), closed(extra=extra)], quote_asset="BNB")
        assert trade.entry_quote_total is not None

    def test_a_stated_entry_total_is_used_and_not_re_derived(self) -> None:
        extra = " entry_quote_total=99"
        (trade,) = trades_of([placed(), closed(total="101", realised="1", extra=extra)])
        assert trade.entry_quote_total == D("99")
        assert trade.entry_total_source == "line"
        assert trade.return_pct == D("1") / D("99") * 100

    def test_the_return_is_realised_over_the_entry_total_as_a_percentage(self) -> None:
        (trade,) = trades_of([placed(), exited(total="95", realised="-5")])
        assert trade.return_pct == D("-5")

    def test_every_derived_figure_is_a_decimal(self) -> None:
        (trade,) = trades_of([placed(), exited()])
        for value in (
            trade.entry_quote_total,
            trade.return_pct,
            trade.exit_price,
            trade.slippage_pct,
            trade.stop_distance_pct,
            trade.exit_move_pct,
        ):
            assert type(value) is D


class TestRouteAndLeg:
    def test_a_close_booked_line_is_a_close(self) -> None:
        (trade,) = trades_of([placed(), closed()])
        assert trade.route is tc.Route.CLOSE
        assert trade.leg is None

    def test_an_exit_booked_line_is_a_protective_leg(self) -> None:
        (trade,) = trades_of([placed(), exited()])
        assert trade.route is tc.Route.LEG

    def test_a_boot_booking_of_the_bots_own_sell_is_a_close(self) -> None:
        extra = " close_client_order_id=tb1-BTCUSDT-9-C"
        (trade,) = trades_of([placed(), booted(extra=extra)])
        assert trade.route is tc.Route.CLOSE

    @pytest.mark.parametrize(
        ("label", "leg"), [("SL", tc.Leg.STOP_LOSS), ("TP", tc.Leg.TAKE_PROFIT)]
    )
    def test_a_stated_leg_is_taken_as_stated_whatever_the_prices_say(
        self, label: str, leg: tc.Leg
    ) -> None:
        (trade,) = trades_of([placed(), booted(total="105", realised="5", extra=f" leg={label}")])
        assert trade.leg is leg

    def test_an_unlabelled_exit_below_the_entry_price_is_a_stop_loss(self) -> None:
        (trade,) = trades_of([placed(), exited(total="95", realised="-5")])
        assert trade.leg is tc.Leg.STOP_LOSS

    def test_an_unlabelled_exit_above_the_entry_price_is_a_take_profit(self) -> None:
        (trade,) = trades_of([placed(entry="100"), exited(total="104", realised="4")])
        assert trade.leg is tc.Leg.TAKE_PROFIT

    def test_an_unlabelled_exit_at_the_entry_price_is_unclassified(self) -> None:
        (trade,) = trades_of([placed(), exited(total="100", realised="0")])
        assert trade.leg is None


class TestStopSlippage:
    def test_slippage_is_beyond_the_stop_as_a_percentage_of_the_stop(self) -> None:
        (trade,) = trades_of([placed(stop="98"), exited(total="95", realised="-5")])
        assert trade.slippage_pct == (D("98") - D("95")) / D("98") * 100

    def test_a_fill_better_than_the_stop_has_negative_slippage(self) -> None:
        (trade,) = trades_of([placed(stop="98"), exited(total="99", realised="-1")])
        assert trade.slippage_pct == (D("98") - D("99")) / D("98") * 100
        assert trade.slippage_pct is not None
        assert trade.slippage_pct < 0

    def test_the_stop_distance_and_exit_move_are_from_the_placements_entry_limit(self) -> None:
        (trade,) = trades_of([placed(entry="100", stop="98"), exited(total="95", realised="-5")])
        assert trade.stop_distance_pct == D("2")
        assert trade.exit_move_pct == D("-5")

    def test_a_two_percent_stop_filled_4_21_percent_beyond_exits_6_13_percent_below(self) -> None:
        stop = "98"
        total = str(D(stop) * (1 - D("0.0421")))
        (trade,) = trades_of([placed(entry="100", stop=stop), exited(total=total, realised="-6")])
        assert trade.exit_move_pct is not None
        assert D("-6.13") < trade.exit_move_pct < D("-6.12")

    def test_an_exit_with_no_placement_has_no_slippage_but_keeps_its_return(self) -> None:
        (trade,) = trades_of([exited(total="95", realised="-5")])
        assert trade.placement is None
        assert trade.slippage_pct is None
        assert trade.return_pct == D("-5")

    def test_a_take_profit_has_no_slippage_figure(self) -> None:
        (trade,) = trades_of([placed(), exited(total="104", realised="4")])
        assert trade.leg is tc.Leg.TAKE_PROFIT
        assert trade.slippage_pct is None


class TestTime:
    def test_the_offset_is_inferred_from_naive_bookings_and_their_candles(self) -> None:
        naive = closed(stamp="2026-09-06 06:15:03", candle="2026-09-06T00:14:59.999000+00:00")
        parsed = tc.parse_capture([naive])
        estimate = tc.infer_local_offset(parsed.bookings)
        assert estimate == tc.OffsetEstimate(timedelta(hours=6), 1, 1)

    def test_the_smallest_gap_is_taken_so_a_late_booking_does_not_shift_the_offset(self) -> None:
        prompt = closed(stamp="2026-09-06 06:15:03", candle="2026-09-06T00:14:59.999000+00:00")
        late = closed(
            order_id="12",
            stamp="2026-09-06 06:40:03",
            candle="2026-09-06T00:14:59.999000+00:00",
        )
        estimate = tc.infer_local_offset(tc.parse_capture([late, prompt]).bookings)
        assert estimate is not None
        assert estimate.offset == timedelta(hours=6)
        assert (estimate.lines_used, estimate.lines_agreeing) == (2, 2)

    def test_a_line_outside_the_window_is_not_counted_as_agreeing(self) -> None:
        prompt = closed(stamp="2026-09-06 06:15:03", candle="2026-09-06T00:14:59.999000+00:00")
        far = closed(
            order_id="12",
            stamp="2026-09-06 09:15:03",
            candle="2026-09-06T00:14:59.999000+00:00",
        )
        estimate = tc.infer_local_offset(tc.parse_capture([prompt, far]).bookings)
        assert estimate is not None
        assert (estimate.lines_used, estimate.lines_agreeing) == (2, 1)

    def test_with_no_naive_booking_there_is_no_offset(self) -> None:
        assert tc.infer_local_offset(tc.parse_capture([closed()]).bookings) is None

    def test_a_naive_booking_is_shifted_to_utc_and_its_day_follows_the_shifted_time(self) -> None:
        naive = closed(stamp="2026-09-07 02:00:03", candle="2026-09-06T20:00:00+00:00")
        (trade,) = trades_of([placed(), naive])
        assert trade.booked_at == datetime(2026, 9, 6, 20, 0, 3, tzinfo=UTC)
        assert trade.booked_day == date(2026, 9, 6)

    def test_a_naive_booking_with_no_offset_is_unattributed_not_guessed(self) -> None:
        (trade,) = trades_of([exited(stamp="2026-09-07 02:00:03")])
        assert trade.booked_at is None
        assert trade.booked_day is None

    def test_a_booking_day_is_the_booking_time_and_never_the_candle_time(self) -> None:
        line = closed(stamp="2026-09-11T00:00:05Z", candle="2026-09-10T23:59:59.999000+00:00")
        (trade,) = trades_of([placed(), line])
        assert trade.booked_day == date(2026, 9, 11)

    def test_a_boot_booking_states_its_own_day_and_it_is_used(self) -> None:
        line = booted(stamp="2026-09-11T00:00:05Z", extra=" leg=SL booked_day=2026-09-10")
        (trade,) = trades_of([placed(), line])
        assert trade.booked_day == date(2026, 9, 10)

    def test_a_close_is_held_from_the_entry_bar_to_its_candle_not_from_the_line_stamp(self) -> None:
        naive = closed(stamp="2026-09-10 07:00:03", candle=CANDLE)
        (trade,) = trades_of([placed(bar=BAR), naive])
        assert trade.entry_time == datetime(2026, 9, 10, 0, 0, 59, 999000, tzinfo=UTC)
        assert trade.exit_time == datetime(2026, 9, 10, 1, 0, 59, 999000, tzinfo=UTC)
        assert tc._hold(trade) == timedelta(hours=1)

    def test_a_leg_is_held_to_its_fill_and_has_no_duration_without_one(self) -> None:
        with_fill = exited(extra=" filled_at=2026-09-10T00:30:59.999000+00:00")
        trades = trades_of([placed(), with_fill])
        assert tc._hold(trades[0]) == timedelta(minutes=30)
        assert tc._hold(trades_of([placed(), exited()])[0]) is None


class TestFigures:
    def test_totals_count_sum_win_rate_and_profit_factor(self) -> None:
        figures = tc.totals([D("1"), D("-5"), D("4")])
        assert figures.count == 3
        assert figures.realised == D("0")
        assert figures.wins == 2
        assert figures.gross_win == D("5")
        assert figures.gross_loss == D("5")
        assert figures.win_rate_pct == D(2) / D(3) * 100
        assert figures.profit_factor == D("1")

    def test_profit_factor_is_gross_wins_over_gross_losses_as_a_positive_number(self) -> None:
        figures = tc.totals([D("30"), D("-5"), D("-5")])
        assert figures.gross_loss == D("10")
        assert figures.profit_factor == D("3")

    def test_profit_factor_ignores_how_many_trades_won_and_lost(self) -> None:
        figures = tc.totals([D("1"), D("1"), D("1"), D("1"), D("-8")])
        assert figures.profit_factor == D("0.5")

    def test_profit_factor_is_below_one_for_a_losing_set_and_above_for_a_winning_one(self) -> None:
        assert tc.totals([D("2"), D("-4")]).profit_factor == D("0.5")
        assert tc.totals([D("4"), D("-2")]).profit_factor == D("2")

    def test_with_no_losing_booking_the_profit_factor_is_absent_not_infinite(self) -> None:
        assert tc.totals([D("1"), D("2")]).profit_factor is None
        assert tc.totals([]).profit_factor is None

    def test_a_zero_is_neither_a_win_nor_a_loss(self) -> None:
        figures = tc.totals([D("0"), D("3"), D("-1")])
        assert figures.wins == 1
        assert figures.gross_loss == D("1")

    def test_no_bookings_have_no_win_rate(self) -> None:
        assert tc.totals([]).win_rate_pct is None

    def test_the_standard_deviation_is_the_sample_one_with_n_minus_one(self) -> None:
        stats = tc.return_stats([D("1"), D("2"), D("3")])
        assert stats.n == 3
        assert stats.mean == D("2")
        assert stats.sd == D("1")
        assert stats.se == D("1") / D("3").sqrt()

    def test_the_interval_is_the_mean_plus_or_minus_1_96_standard_errors(self) -> None:
        stats = tc.return_stats([D("1"), D("2"), D("3")])
        assert stats.se is not None
        assert stats.low == D("2") - D("1.96") * stats.se
        assert stats.high == D("2") + D("1.96") * stats.se

    def test_one_return_has_a_mean_and_no_spread(self) -> None:
        stats = tc.return_stats([D("5")])
        assert (stats.n, stats.mean) == (1, D("5"))
        assert stats.sd is None
        assert stats.low is None

    def test_no_returns_have_nothing(self) -> None:
        assert tc.return_stats([]) == tc.ReturnStats(0, None, None, None, None, None)

    def test_the_median_of_an_odd_and_an_even_count(self) -> None:
        assert tc.median([D("3"), D("1"), D("2")]) == D("2")
        assert tc.median([D("4"), D("1"), D("3"), D("2")]) == D("2.5")
        assert tc.median([]) is None

    def test_the_net_mean_takes_the_fee_off_both_sides_of_the_round_trip(self) -> None:
        assert tc.net_mean(D("-0.0553"), D("0.1")) == D("-0.2553")


SAMPLE_LOG = (
    "banner",
    placed(),
    closed(),
    placed(symbol="BTCUSDT", stamp="2026-09-10T02:01:03Z"),
    exited(stamp="2026-09-10T03:00:00Z"),
    placed(symbol="ETHUSDT", quantity="2", entry="50", stop="49"),
    exited(
        symbol="ETHUSDT",
        order_id="22",
        quantity="2",
        total="104",
        realised="4",
        stamp="2026-09-10T04:00:00Z",
    ),
)


class TestRestrictUntil:
    def trades(self) -> tuple[tc.Trade, ...]:
        lines = [
            placed(),
            closed(order_id="1", stamp="2026-09-10T01:00:00Z"),
            placed(stamp="2026-09-10T01:10:00Z"),
            closed(order_id="2", stamp="2026-09-10T02:00:00Z"),
            placed(stamp="2026-09-10T02:10:00Z"),
            closed(order_id="3", stamp="2026-09-10T03:00:01Z"),
        ]
        return trades_of(lines)

    def test_the_instant_itself_is_inside_the_window(self) -> None:
        kept, excluded = tc.restrict_until(
            self.trades(), datetime(2026, 9, 10, 2, 0, 0, tzinfo=UTC)
        )
        assert [trade.booking.order_id for trade in kept] == ["1", "2"]
        assert excluded == 1

    def test_a_second_before_the_instant_leaves_it_outside(self) -> None:
        kept, excluded = tc.restrict_until(
            self.trades(), datetime(2026, 9, 10, 1, 59, 59, tzinfo=UTC)
        )
        assert [trade.booking.order_id for trade in kept] == ["1"]
        assert excluded == 2

    def test_a_window_after_everything_keeps_everything(self) -> None:
        kept, excluded = tc.restrict_until(self.trades(), datetime(2027, 1, 1, tzinfo=UTC))
        assert len(kept) == 3
        assert excluded == 0

    def test_a_booking_that_cannot_be_dated_is_dropped_and_counted(self) -> None:
        undated = trades_of([exited(stamp="2026-09-07 02:00:03")])
        kept, excluded = tc.restrict_until(undated, datetime(2030, 1, 1, tzinfo=UTC))
        assert kept == ()
        assert excluded == 1


class TestEndToEnd:
    def write(self, tmp_path: Path, lines: list[str] | None = None) -> Path:
        path = tmp_path / "capture.log"
        path.write_bytes(("\n".join(lines or SAMPLE_LOG) + "\n").encode())
        return path

    def test_the_report_carries_the_hand_worked_figures_and_the_digest(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        path = self.write(tmp_path)
        assert tc.main([str(path)]) == 0
        out = capsys.readouterr().out
        sha = hashlib.sha256(path.read_bytes()).hexdigest()
        assert f"sha256 : {sha}" in out
        assert out.count(f"[sha256 {sha}]") == 4
        assert "bookings   : 3" in out
        assert "closes by CLOSE: 1   by a protective leg: 2 (SL 1, TP 1, unclassified 0)" in out
        assert "realised gross      : 0.0000 USDT" in out
        assert "win rate            : 66.7% (2 of 3)" in out
        assert "profit factor       : 1.00" in out
        assert "mean                : 0.0000%" in out
        assert "net mean at 0.1% a side : -0.2000%" in out
        assert "bookings matched to a placement : 3 of 3" in out
        assert "placements never booked          : 0" in out

    def test_the_slippage_section_lists_each_stop_loss_leg(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        tc.main([str(self.write(tmp_path))])
        out = capsys.readouterr().out
        assert "stop-loss legs      : 1 (1 with a matched placement)" in out
        assert "filled beyond trigger: 1" in out
        assert "slippage 3.0612%" in out
        assert "exit move -5.0000%" in out

    def test_the_fee_percent_option_moves_only_the_net_figure(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        tc.main([str(self.write(tmp_path)), "--fee-percent", "0.25"])
        out = capsys.readouterr().out
        assert "net mean at 0.25% a side : -0.5000%" in out
        assert "profit factor       : 1.00" in out

    @pytest.mark.parametrize("value", ["-0.1", "nan", "inf", "abc"])
    def test_a_fee_percent_that_is_negative_or_not_a_finite_decimal_is_refused(
        self, tmp_path: Path, value: str
    ) -> None:
        with pytest.raises(SystemExit) as raised:
            tc.main([str(self.write(tmp_path)), "--fee-percent", value])
        assert raised.value.code == 2

    def test_an_anomaly_is_listed_and_the_exit_status_says_so(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        status = tc.main(
            [str(self.write(tmp_path, [*SAMPLE_LOG, closed(total="oops", order_id="99")]))]
        )
        out = capsys.readouterr().out
        assert status == 1
        assert "anomalies  : 1" in out
        assert "is not a decimal" in out

    def test_until_counts_only_bookings_at_or_before_the_instant(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        tc.main([str(self.write(tmp_path)), "--until", "2026-09-10T03:00:00Z"])
        out = capsys.readouterr().out
        assert (
            "restricted to bookings at or before 2026-09-10T03:00:00Z : kept 2, excluded 1" in out
        )
        assert "bookings   : 3" in out
        assert "bookings matched to a placement : 2 of 2" in out
        assert "placements never booked          : 0" in out
        assert "realised gross      : -4.0000 USDT" in out
        assert "closes by CLOSE: 1   by a protective leg: 1 (SL 1, TP 0, unclassified 0)" in out

    def test_without_until_nothing_is_restricted(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        tc.main([str(self.write(tmp_path))])
        assert "restricted to" not in capsys.readouterr().out

    @pytest.mark.parametrize("value", ["2026-09-10T03:00:00", "garbage", "2026-13-40T00:00:00Z"])
    def test_an_until_that_is_naive_or_not_a_timestamp_is_refused(
        self, tmp_path: Path, value: str
    ) -> None:
        with pytest.raises(SystemExit) as raised:
            tc.main([str(self.write(tmp_path)), "--until", value])
        assert raised.value.code == 2

    def test_it_is_read_only(self, tmp_path: Path) -> None:
        path = self.write(tmp_path)
        before = (
            path.read_bytes(),
            path.stat().st_mtime_ns,
            sorted(p.name for p in tmp_path.iterdir()),
        )
        tc.main([str(path)])
        after = (
            path.read_bytes(),
            path.stat().st_mtime_ns,
            sorted(p.name for p in tmp_path.iterdir()),
        )
        assert before == after

    def test_a_path_under_logs_is_refused_before_a_byte_is_read(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        live = tmp_path / "logs" / "trading_bot.log"
        live.parent.mkdir()
        live.write_bytes(b"x")
        assert tc.main([str(live)]) == 2
        out = capsys.readouterr().out
        assert "REFUSED" in out
        assert "sha256" not in out

    def test_a_missing_file_is_refused(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        assert tc.main([str(tmp_path / "absent.log")]) == 2
        assert "is not a file" in capsys.readouterr().out

    def test_an_empty_capture_reports_zero_and_does_not_crash(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        assert tc.main([str(self.write(tmp_path, ["nothing here"]))]) == 0
        out = capsys.readouterr().out
        assert "bookings   : 0" in out
        assert "profit factor       : n/a (no losing booking)" in out
