"""S3 metrics: hand figures for every definition, and parity with ``scripts/trade_census.py``.

Every expected figure is arithmetic the reader can do from the numbers written in the test:
five trades whose wins, losses and break-even are spelled out, equity paths whose worst decline
is found by eye, and daily returns of exactly +2%, +2% and -2% whose Sharpe and Sortino have a
closed form. The ratios that need a square root are compared to twenty decimal places against
that closed form, which is a different computation from the one under test.
"""

from __future__ import annotations

import json
import random
import sys
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from typing import ClassVar

import pytest

from trading_bot.backtesting.metrics import (
    DAYS_PER_YEAR,
    DENOMINATORS,
    UNLABELLED,
    Z_95,
    EquityCurve,
    EquitySummary,
    TradeFacts,
    compute_metrics,
    daily_returns,
    downside_deviation,
    exposure_fraction,
    group_metrics,
    load_trades_csv,
    median,
    return_stats,
    sharpe_ratio,
    sortino_ratio,
    trade_return_pct,
)
from trading_bot.backtesting.regimes import RegimeTable

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

import trade_census as census

D = Decimal
T0 = datetime(2024, 3, 1, tzinfo=timezone.utc)
TWENTY = D("1e-20")


def at(minutes: int, *, start: datetime = T0) -> datetime:
    return start + timedelta(minutes=minutes)


def trade(
    symbol: str = "BTCUSDT",
    *,
    entry: datetime = T0,
    seconds: int = 60,
    notional: str = "1000",
    fee: str = "1",
    exit_gross: str = "1040",
    exit_fee: str = "1.04",
) -> TradeFacts:
    total = D(notional) + D(fee)
    return TradeFacts(
        symbol=symbol,
        entry_time=entry,
        exit_time=entry + timedelta(seconds=seconds),
        entry_notional=D(notional),
        entry_fee=D(fee),
        entry_quote_total=total,
        exit_gross=D(exit_gross),
        exit_fee=D(exit_fee),
        realised=D(exit_gross) - total - D(exit_fee),
    )


def five_trades() -> list[TradeFacts]:
    """Two wins, two losses and a break-even, with holdings of 60, 120, 180, 240 and 300 s."""
    return [
        trade(seconds=60),  # +37.96 net, +40 gross
        trade(seconds=120, exit_gross="990", exit_fee="0.99"),  # -11.99, -10
        trade(
            seconds=180, notional="500", fee="0.5", exit_gross="520", exit_fee="0.52"
        ),  # +18.98, +20
        trade(
            seconds=240, notional="500", fee="0.5", exit_gross="450", exit_fee="0.45"
        ),  # -50.95, -50
        trade(
            seconds=300, notional="200", fee="0.2", exit_gross="200.4", exit_fee="0.2"
        ),  # 0, +0.4
    ]


def curve(initial: str, *points: tuple[int, str, int]) -> EquitySummary:
    """An equity curve started at T0 with ``(minute, equity, positions opened that minute)`` samples."""
    made = EquityCurve(D(initial), T0)
    for minute, equity, opened in points:
        made.observe(at(minute), D(equity), open_since=[at(minute)] * opened)
    return made.summary()


def summary_with_closes(initial: str, closes: dict[date, str]) -> EquitySummary:
    first = min(closes)
    return EquitySummary(
        initial=D(initial),
        final=D(closes[max(closes)]),
        start=datetime(first.year, first.month, first.day, tzinfo=timezone.utc),
        last_at=datetime(2024, 3, 31, tzinfo=timezone.utc),
        samples=len(closes),
        drawdown_peak=D(initial),
        drawdown_trough=D(initial),
        drawdown_peak_at=T0,
        drawdown_trough_at=T0,
        daily_closes=tuple((day, D(close)) for day, close in sorted(closes.items())),
        open_since=(),
        span_seconds=D(0),
    )


class TestTheReturnOfATradeAndItsInterval:
    def test_a_return_is_the_realised_over_the_entry_quote_total_in_percent(self) -> None:
        assert trade_return_pct(D("25"), D("1000")) == D("2.5")
        assert trade_return_pct(D("-10"), D("500")) == D("-2")
        assert trade_return_pct(D("0"), D("500")) == D("0")

    @pytest.mark.parametrize("total", [D("0"), D("-1")])
    def test_a_non_positive_entry_total_is_refused(self, total: Decimal) -> None:
        with pytest.raises(ValueError, match="must be positive"):
            trade_return_pct(D("1"), total)

    def test_four_returns_have_a_hand_mean_a_sample_sd_and_a_196_interval(self) -> None:
        stats = return_stats([D("1"), D("2"), D("3"), D("4")])
        assert stats.n == 4
        assert stats.mean == D("2.5")
        # sample variance = (2.25 + 0.25 + 0.25 + 2.25) / 3 = 5 / 3
        assert stats.sd == (D(5) / D(3)).sqrt()
        assert stats.se is not None and stats.sd is not None
        assert stats.se == stats.sd / D(2)
        assert stats.low == D("2.5") - Z_95 * stats.se
        assert stats.high == D("2.5") + Z_95 * stats.se
        assert D("1.96") == Z_95

    def test_the_sd_divides_by_n_minus_one_and_not_by_n(self) -> None:
        population = D("1.25").sqrt()  # what a divide-by-n would give for 1, 2, 3, 4
        stats = return_stats([D("1"), D("2"), D("3"), D("4")])
        assert stats.sd != population

    def test_one_value_has_a_mean_and_nothing_else_and_none_has_nothing(self) -> None:
        assert return_stats([D("3")]) == return_stats([D("3")])
        one = return_stats([D("3")])
        assert (one.n, one.mean, one.sd, one.se, one.low, one.high) == (
            1,
            D("3"),
            None,
            None,
            None,
            None,
        )
        none = return_stats([])
        assert (none.n, none.mean, none.low) == (0, None, None)

    def test_the_median_takes_the_midpoint_of_an_even_count(self) -> None:
        assert median([]) is None
        assert median([D("3"), D("1"), D("2")]) == D("2")
        assert median([D("4"), D("1"), D("3"), D("2")]) == D("2.5")


class TestParityWithTheCensus:
    """R-AK: the return and its interval are the census's, on a shared set of trades."""

    @staticmethod
    def shared_trades() -> list[TradeFacts]:
        rng = random.Random(11)
        out = []
        for _ in range(40):
            notional = D(rng.randint(100_000, 500_000)) / D(100)
            fee = notional / D(1000)
            gross = notional * D(rng.randint(9_500, 10_700)) / D(10_000)
            out.append(
                trade(
                    notional=str(notional),
                    fee=str(fee),
                    exit_gross=str(gross),
                    exit_fee=str(gross / D(1000)),
                )
            )
        return out

    @staticmethod
    def census_trades(trades: list[TradeFacts]) -> tuple[census.Trade, ...]:
        lines = [
            f"2026-01-01T00:00:{i % 60:02d}Z | INFO | pid=1 | x | event=close_booked "
            f"symbol=BTCUSDT order_id={i} quantity=1 quote_total={t.exit_gross} "
            f"realised={t.realised} entry_quote_total={t.entry_quote_total}"
            for i, t in enumerate(trades, start=1)
        ]
        parsed = census.parse_capture(lines)
        assert parsed.anomalies == ()
        return census.build_trades(parsed, "USDT")

    def test_each_trades_return_is_the_census_return_exactly(self) -> None:
        trades = self.shared_trades()
        theirs = [t.return_pct for t in self.census_trades(trades)]
        mine = [trade_return_pct(t.realised, t.entry_quote_total) for t in trades]
        assert theirs == mine
        assert all(isinstance(value, D) for value in mine)

    def test_the_mean_sd_se_and_interval_are_the_census_exactly(self) -> None:
        trades = self.shared_trades()
        theirs = census.return_stats([t.return_pct for t in self.census_trades(trades)])
        mine = group_metrics(trades).returns
        assert (mine.n, mine.mean, mine.sd, mine.se, mine.low, mine.high) == (
            theirs.n,
            theirs.mean,
            theirs.sd,
            theirs.se,
            theirs.low,
            theirs.high,
        )
        assert mine.sd is not None and mine.n == 40

    def test_parity_holds_on_the_degenerate_sets_too(self) -> None:
        for count in (0, 1, 2):
            trades = self.shared_trades()[:count]
            theirs = census.return_stats(
                [t.return_pct for t in self.census_trades(trades)] if trades else []
            )
            mine = group_metrics(trades).returns
            assert (mine.n, mine.mean, mine.sd, mine.low) == (
                theirs.n,
                theirs.mean,
                theirs.sd,
                theirs.low,
            )


class TestTheEquityCurve:
    def test_the_worst_peak_to_trough_decline_is_found_by_eye(self) -> None:
        # peak 110 -> 99 is 10%; peak 110 -> 90 is 18.18%; the later rise to 120 does not erase it.
        found = curve(
            "100", (1, "110", 0), (2, "99", 0), (3, "105", 0), (4, "90", 0), (5, "120", 0)
        )
        assert (found.drawdown_peak, found.drawdown_trough) == (D(110), D(90))
        assert found.max_drawdown == D(20) / D(110)
        assert found.max_drawdown_amount == D(20)
        assert (found.drawdown_peak_at, found.drawdown_trough_at) == (at(1), at(4))

    def test_the_decline_is_measured_from_the_running_peak_and_not_from_the_start(self) -> None:
        found = curve("100", (1, "120", 0), (2, "110", 0))
        assert (found.drawdown_peak, found.drawdown_trough) == (D(120), D(110))
        assert found.max_drawdown == D(10) / D(120)  # not 10 / 100

    def test_a_run_that_only_ever_falls_measures_from_the_initial_balance(self) -> None:
        found = curve("100", (1, "95", 0), (2, "90", 0))
        assert found.max_drawdown == D("0.1")
        assert (found.drawdown_peak, found.drawdown_trough) == (D(100), D(90))
        assert (found.drawdown_peak_at, found.drawdown_trough_at) == (T0, at(2))

    def test_a_run_that_never_declines_has_no_drawdown(self) -> None:
        found = curve("100", (1, "101", 0), (2, "105", 0))
        assert found.max_drawdown == 0 and found.max_drawdown_amount == 0

    def test_the_fraction_decides_and_not_the_amount(self) -> None:
        """100 -> 85 is 15 down (15%); 1000 -> 900 is 100 down (10%). The 15% is the worst."""
        found = curve("100", (1, "85", 0), (2, "1000", 0), (3, "900", 0))
        assert (found.drawdown_peak, found.drawdown_trough) == (D(100), D(85))
        assert found.max_drawdown == D("0.15")

    def test_a_later_decline_of_the_same_fraction_does_not_replace_the_first(self) -> None:
        found = curve("100", (1, "90", 0), (2, "200", 0), (3, "180", 0))
        assert (found.drawdown_peak, found.drawdown_trough) == (D(100), D(90))

    def test_a_decline_bigger_in_fraction_replaces_the_first(self) -> None:
        found = curve("100", (1, "90", 0), (2, "200", 0), (3, "170", 0))
        assert (found.drawdown_peak, found.drawdown_trough) == (D(200), D(170))
        assert found.max_drawdown == D("0.15")

    def test_the_comparison_is_exact_where_a_rounded_quotient_would_tie(self) -> None:
        """1/3 and 1e-30 below 1/3 print the same to 28 digits; cross-multiplying tells them apart."""
        third_down = D(3)  # 3 -> 2 is a decline of exactly 1/3
        found = curve(
            "3",
            (1, "2", 0),
            (2, "3000000000000000000000000000000", 0),
            (3, "2000000000000000000000000000001", 0),
        )
        assert (found.drawdown_peak, found.drawdown_trough) == (third_down, D(2))
        assert found.max_drawdown == D(1) / D(3)

    def test_samples_must_not_go_back_in_time_but_may_share_an_instant(self) -> None:
        made = EquityCurve(D("100"), T0)
        made.observe(at(5), D("101"), open_since=[])
        made.observe(at(5), D("102"), open_since=[])
        with pytest.raises(ValueError, match="follows one at"):
            made.observe(at(4), D("100"), open_since=[])
        assert made.summary().samples == 2

    def test_a_negative_equity_and_a_non_positive_start_are_refused(self) -> None:
        with pytest.raises(ValueError, match="initial equity must be positive"):
            EquityCurve(D("0"), T0)
        made = EquityCurve(D("100"), T0)
        with pytest.raises(ValueError, match="cannot be negative"):
            made.observe(at(1), D("-1"), open_since=[])

    def test_a_day_closes_on_the_last_sample_in_it_and_midnight_belongs_to_the_day_before(
        self,
    ) -> None:
        made = EquityCurve(D("100"), T0)
        made.observe(datetime(2024, 3, 1, 12, tzinfo=timezone.utc), D("101"), open_since=[])
        made.observe(datetime(2024, 3, 2, 0, 0, tzinfo=timezone.utc), D("102"), open_since=[])
        made.observe(datetime(2024, 3, 2, 0, 0, tzinfo=timezone.utc), D("103"), open_since=[])
        made.observe(datetime(2024, 3, 2, 0, 1, tzinfo=timezone.utc), D("104"), open_since=[])
        assert made.summary().daily_closes == (
            (date(2024, 3, 1), D("103")),
            (date(2024, 3, 2), D("104")),
        )

    def test_the_positions_open_after_the_last_sample_are_the_ones_it_remembers(self) -> None:
        made = EquityCurve(D("100"), T0)
        made.observe(at(1), D("100"), open_since=[at(1)])
        made.observe(at(2), D("100"), open_since=[at(7), at(1)])
        assert made.summary().open_since == (at(1), at(7))  # sorted, and the last sample's alone
        made.observe(at(3), D("100"), open_since=[])
        assert made.summary().open_since == ()

    def test_no_samples_means_no_span_and_no_exposure(self) -> None:
        found = EquityCurve(D("100"), T0).summary()
        assert found.span_seconds == 0 and exposure_fraction([], found) is None
        assert (found.samples, found.final, found.max_drawdown) == (0, D(100), 0)

    def test_the_summary_survives_a_record_round_trip(self) -> None:
        found = curve("100", (1, "110", 1), (2, "99", 1), (1440, "105", 0))
        again = EquitySummary.from_record(json.loads(json.dumps(found.to_record())))
        assert again == found


class TestExposure:
    """Minutes 0 to 100 are the span; each case is a union of intervals drawn on that line."""

    SPAN = curve("100", (100, "100", 0))

    @staticmethod
    def held(begin: int, end: int) -> TradeFacts:
        return trade(entry=at(begin), seconds=(end - begin) * 60)

    def test_one_trade_is_its_interval_over_the_span(self) -> None:
        assert exposure_fraction([self.held(10, 40)], self.SPAN) == D(30) / D(100)

    def test_overlapping_trades_count_once(self) -> None:
        assert exposure_fraction([self.held(10, 40), self.held(30, 60)], self.SPAN) == D(50) / D(
            100
        )

    def test_a_trade_inside_another_adds_nothing(self) -> None:
        assert exposure_fraction([self.held(10, 60), self.held(20, 30)], self.SPAN) == D(50) / D(
            100
        )

    def test_disjoint_trades_add(self) -> None:
        assert exposure_fraction([self.held(10, 20), self.held(30, 40)], self.SPAN) == D(20) / D(
            100
        )

    def test_trades_that_touch_end_to_end_are_one_interval(self) -> None:
        assert exposure_fraction([self.held(10, 20), self.held(20, 30)], self.SPAN) == D(20) / D(
            100
        )

    def test_the_order_the_trades_are_given_in_does_not_matter(self) -> None:
        assert exposure_fraction([self.held(30, 60), self.held(10, 40)], self.SPAN) == D(50) / D(
            100
        )

    def test_a_position_still_open_at_the_end_runs_to_the_last_bar(self) -> None:
        still = curve("100", (80, "100", 0), (100, "100", 0))
        still = EquitySummary(**{**still.__dict__, "open_since": (at(70),)})
        assert exposure_fraction([], still) == D(30) / D(100)

    def test_an_interval_is_clipped_to_the_span(self) -> None:
        assert exposure_fraction([self.held(-10, 10)], self.SPAN) == D(10) / D(100)
        assert exposure_fraction([self.held(90, 130)], self.SPAN) == D(10) / D(100)

    def test_no_trade_and_nothing_open_is_zero_exposure_not_none(self) -> None:
        assert exposure_fraction([], self.SPAN) == D(0)

    def test_a_trade_counts_from_its_entry_bars_open(self) -> None:
        """A one-hour bar opened at minute 0 and the trade held to minute 90: ninety minutes."""
        assert exposure_fraction([self.held(0, 90)], self.SPAN) == D(90) / D(100)


class TestDailyReturns:
    CLOSES: ClassVar[dict[date, str]] = {
        date(2024, 3, 1): "102",
        date(2024, 3, 2): "104.04",
        date(2024, 3, 3): "101.9592",
    }

    def test_each_day_is_its_close_over_the_previous_and_the_first_over_the_initial(self) -> None:
        assert daily_returns(summary_with_closes("100", self.CLOSES)) == (
            D("0.02"),
            D("0.02"),
            D("-0.02"),
        )

    def test_a_day_with_no_bar_keeps_the_previous_close_and_returns_zero(self) -> None:
        sparse = {date(2024, 3, 1): "102", date(2024, 3, 3): "104.04"}
        assert daily_returns(summary_with_closes("100", sparse)) == (D("0.02"), D("0"), D("0.02"))

    def test_no_closes_give_no_returns(self) -> None:
        assert daily_returns(summary_with_closes("100", {date(2024, 3, 1): "100"})) == (D("0"),)
        empty = EquityCurve(D("100"), T0).summary()
        assert daily_returns(empty) == ()


class TestSharpeAndSortino:
    RETURNS = (D("0.02"), D("0.02"), D("-0.02"))

    def test_sharpe_is_mean_over_sample_sd_times_root_365(self) -> None:
        # mean 1/150, sample variance 1/1875, so sharpe = sqrt(1095) / 6 in closed form.
        sharpe = sharpe_ratio(self.RETURNS)
        assert sharpe is not None
        assert sharpe.quantize(TWENTY) == (D(1095).sqrt() / D(6)).quantize(TWENTY)
        assert DAYS_PER_YEAR == 365

    def test_sortino_is_mean_over_the_downside_deviation_times_root_365(self) -> None:
        # downside deviation 0.02 / sqrt(3), so sortino = sqrt(1095) / 3 in closed form.
        sortino = sortino_ratio(self.RETURNS)
        assert sortino is not None
        assert sortino.quantize(TWENTY) == (D(1095).sqrt() / D(3)).quantize(TWENTY)

    def test_the_downside_deviation_counts_every_day_and_only_losses(self) -> None:
        assert downside_deviation(self.RETURNS).quantize(TWENTY) == (
            D("0.0004") / D(3)
        ).sqrt().quantize(TWENTY)
        assert downside_deviation((D("0.02"), D("0.03"))) == 0
        assert downside_deviation(()) == 0

    def test_a_year_of_252_days_would_give_a_different_number(self) -> None:
        sharpe = sharpe_ratio(self.RETURNS)
        assert sharpe is not None
        assert sharpe.quantize(TWENTY) != (D(1050).sqrt() / D(6)).quantize(
            TWENTY
        )  # sqrt(252 * ...)

    def test_undefined_cases_are_none_and_not_zero(self) -> None:
        assert sharpe_ratio((D("0.02"),)) is None
        assert sharpe_ratio(()) is None
        assert sharpe_ratio((D("0.01"), D("0.01"))) is None  # zero sd
        assert sortino_ratio((D("0.02"),)) is None
        assert sortino_ratio((D("0.02"), D("0.01"))) is None  # no losing day

    def test_a_flat_mean_gives_zero_not_none(self) -> None:
        assert sharpe_ratio((D("0.01"), D("-0.01"))) == D(0)


class TestGroupMetrics:
    def test_the_five_trades_have_the_hand_figures(self) -> None:
        group = group_metrics(five_trades())
        assert (group.trades, group.wins, group.losses) == (5, 2, 2)
        assert group.net_pnl == D("-6.00")
        assert group.gross_pnl == D("0.4")
        assert group.entry_fees == D("3.2") and group.exit_fees == D("3.20")
        assert group.fees_paid == D("6.40")
        assert group.fee_residual == 0  # gross - entry fees - exit fees = net
        assert group.win_rate == D("0.4")
        assert group.average_win == D("28.47")  # (37.96 + 18.98) / 2
        assert group.average_loss == D("-31.47")  # (-11.99 - 50.95) / 2

    def test_profit_factor_is_gains_over_absolute_losses_net_and_gross_separately(self) -> None:
        group = group_metrics(five_trades())
        assert group.profit_factor_net == D("56.94") / D("62.94")
        assert group.profit_factor_gross == D("60.4") / D("60")
        assert group.profit_factor_net is not None and group.profit_factor_net < 1
        assert group.profit_factor_gross is not None and group.profit_factor_gross > 1

    def test_fees_are_the_difference_between_the_two_profit_factors(self) -> None:
        only_winner = group_metrics([trade(), trade(exit_gross="1001", exit_fee="1.001")])
        # net and gross both have a loss only if a trade loses; one that wins gross and loses net:
        assert only_winner.profit_factor_net is not None
        assert only_winner.profit_factor_gross is None  # no gross loss at all

    def test_a_set_with_no_loss_has_no_profit_factor_and_one_with_no_win_has_no_average_win(
        self,
    ) -> None:
        winners = group_metrics([trade(), trade(seconds=90)])
        assert winners.profit_factor_net is None and winners.average_loss is None
        losers = group_metrics([trade(exit_gross="900", exit_fee="0.9")])
        assert losers.average_win is None and losers.win_rate == 0
        assert losers.profit_factor_net == D(0)

    def test_the_holding_period_is_exit_minus_entry_mean_and_median(self) -> None:
        group = group_metrics(five_trades())
        assert group.mean_holding_s == D(180)
        assert group.median_holding_s == D(180)
        even = group_metrics(five_trades()[:4])
        assert even.mean_holding_s == D(150) and even.median_holding_s == D(150)
        skew = group_metrics([trade(seconds=10), trade(seconds=20), trade(seconds=1000)])
        assert skew.mean_holding_s == D("1030") / D(3) and skew.median_holding_s == D(20)

    def test_a_fee_identity_that_does_not_hold_leaves_a_visible_residual(self) -> None:
        broken = TradeFacts(
            symbol="BTCUSDT",
            entry_time=T0,
            exit_time=at(1),
            entry_notional=D("1000"),
            entry_fee=D("1"),
            entry_quote_total=D("1001"),
            exit_gross=D("1040"),
            exit_fee=D("1.04"),
            realised=D("40"),  # should be 37.96
        )
        assert group_metrics([broken]).fee_residual == D("-2.04")

    def test_an_empty_set_has_zero_counts_and_no_ratios(self) -> None:
        group = group_metrics([])
        assert (group.trades, group.net_pnl, group.fees_paid) == (0, D(0), D(0))
        assert group.win_rate is None and group.average_win is None
        assert group.profit_factor_net is None and group.mean_holding_s is None
        assert group.returns.n == 0

    def test_the_per_trade_returns_use_the_entry_quote_total_as_the_denominator(self) -> None:
        # entry quote totals of 100 and realised 1, 2, 3, 4: returns of 1%, 2%, 3% and 4%.
        trades = [
            TradeFacts("BTCUSDT", T0, at(1), D(99), D(1), D(100), D(100) + D(r), D(0), D(r))
            for r in (1, 2, 3, 4)
        ]
        returns = group_metrics(trades).returns
        assert returns.mean == D("2.5")
        assert returns.sd == (D(5) / D(3)).sqrt()


class TestBreakdowns:
    TABLE = RegimeTable.from_document(
        {
            "quarters": [
                {"quarter": "2024Q1", "regime": "rising"},
                {"quarter": "2024Q2", "regime": "falling"},
                {"quarter": "2024Q3", "regime": None},
            ]
        }
    )

    def metrics(
        self, trades: list[TradeFacts], *, regimes: RegimeTable | None = TABLE
    ) -> dict[str, object]:
        equity = curve("10000", (1, "10000", 0))
        return compute_metrics(trades, equity, quote_asset="USDT", regimes=regimes).to_record()

    def test_trades_split_by_pair_in_order_of_first_trade(self) -> None:
        mixed = [
            trade("ETHUSDT"),
            trade("BTCUSDT", exit_gross="900", exit_fee="0.9"),
            trade("ETHUSDT"),
        ]
        found = compute_metrics(mixed, curve("10000"), quote_asset="USDT")
        assert list(found.by_pair) == ["ETHUSDT", "BTCUSDT"]
        assert found.by_pair["ETHUSDT"].trades == 2 and found.by_pair["BTCUSDT"].trades == 1
        assert found.by_pair["BTCUSDT"].wins == 0
        assert found.overall.trades == 3

    def test_the_pairs_net_pnl_adds_up_to_the_whole(self) -> None:
        mixed = [
            trade("ETHUSDT"),
            trade("BTCUSDT", exit_gross="900", exit_fee="0.9"),
            trade("ETHUSDT"),
        ]
        found = compute_metrics(mixed, curve("10000"), quote_asset="USDT")
        assert sum((g.net_pnl for g in found.by_pair.values()), D(0)) == found.overall.net_pnl

    def test_a_trade_is_in_the_regime_of_the_quarter_of_its_entry_bar(self) -> None:
        last_day_of_q1 = datetime(2024, 3, 31, 23, 59, tzinfo=timezone.utc)
        first_day_of_q2 = datetime(2024, 4, 1, 0, 0, tzinfo=timezone.utc)
        in_partial = datetime(2024, 8, 1, tzinfo=timezone.utc)
        outside = datetime(2030, 1, 1, tzinfo=timezone.utc)
        trades = [
            trade(entry=last_day_of_q1),
            trade(entry=first_day_of_q2),
            trade(entry=first_day_of_q2, seconds=90),
            trade(entry=in_partial),
            trade(entry=outside),
        ]
        found = compute_metrics(trades, curve("10000"), quote_asset="USDT", regimes=self.TABLE)
        assert found.by_regime is not None
        assert {name: group.trades for name, group in found.by_regime.items()} == {
            "rising": 1,
            "falling": 2,
            "sideways": 0,
            UNLABELLED: 2,
        }
        assert list(found.by_regime) == ["rising", "falling", "sideways", UNLABELLED]

    def test_with_no_table_there_is_no_regime_breakdown_at_all(self) -> None:
        found = compute_metrics([trade()], curve("10000"), quote_asset="USDT", regimes=None)
        assert found.by_regime is None
        assert self.metrics([trade()], regimes=None)["by_regime"] is None

    def test_the_regimes_cover_every_trade_exactly_once(self) -> None:
        trades = [
            trade(entry=datetime(2024, month, 15, tzinfo=timezone.utc))
            for month in (1, 2, 4, 5, 8, 9)
        ]
        found = compute_metrics(trades, curve("10000"), quote_asset="USDT", regimes=self.TABLE)
        assert found.by_regime is not None
        assert sum(group.trades for group in found.by_regime.values()) == len(trades)


class TestTheWholeMetrics:
    def test_the_equity_measures_come_from_the_curve_and_the_trade_measures_from_the_trades(
        self,
    ) -> None:
        equity = curve("1000", (1, "1100", 1), (2, "990", 1), (1440, "1050", 0))
        found = compute_metrics(five_trades(), equity, quote_asset="USDT")
        assert found.initial_balance == D(1000) and found.final_equity == D(1050)
        assert found.max_drawdown == D(110) / D(1100)
        assert found.max_drawdown_amount == D(110)
        assert found.exposure == exposure_fraction(five_trades(), equity)
        assert found.days == 1
        assert found.overall.trades == 5

    def test_the_drawdown_comes_from_the_equity_and_not_from_the_closed_trades(self) -> None:
        """Equity falls 40% inside a trade that closes at a profit: the trades alone show none."""
        equity = curve("1000", (1, "600", 1), (2, "1100", 0))
        profit = [trade(exit_gross="1100", exit_fee="1.1")]
        found = compute_metrics(profit, equity, quote_asset="USDT")
        assert found.overall.net_pnl > 0
        assert found.max_drawdown == D("0.4")

    def test_the_record_is_json_serialisable_and_carries_every_denominator(self) -> None:
        equity = curve("1000", (1, "1100", 1), (1440, "1050", 0))
        record = compute_metrics(
            five_trades(), equity, quote_asset="USDT", regimes=TestBreakdowns.TABLE
        ).to_record()
        text = json.dumps(record)
        assert json.loads(text) == record
        assert record["denominators"] == DENOMINATORS
        assert record["quote_asset"] == "USDT"
        overall = record["overall"]
        assert isinstance(overall, dict)
        assert overall["net_pnl"] == "-6.00" and overall["fees_paid"] == "6.40"
        assert isinstance(overall["returns_pct"], dict) and overall["returns_pct"]["n"] == 5

    def test_every_figure_the_record_states_has_a_denominator_entry(self) -> None:
        for key in (
            "net_pnl",
            "gross_pnl",
            "win_rate",
            "average_win",
            "average_loss",
            "profit_factor_net",
            "profit_factor_gross",
            "trade_return_pct",
            "max_drawdown",
            "daily_return",
            "sharpe_ratio",
            "sortino_ratio",
            "exposure",
            "holding_period",
        ):
            assert DENOMINATORS[key]


class TestTheTradesFile:
    HEADER = (
        "symbol,timeframe,signal_bar_open,entry_bar_open,quantity,entry_limit,entry_price,"
        "entry_notional,entry_fee,entry_quote_total,stop_loss,take_profit,exit_reason,"
        "exit_bar_open,exit_time,exit_price,exit_trigger,exit_open_through_trigger,exit_gross,"
        "exit_fee,realised,spans_gap,spans_short_bar"
    )

    def test_a_trades_csv_is_read_back_to_the_facts_it_was_written_from(
        self, tmp_path: Path
    ) -> None:
        row = (
            "BTCUSDT,1h,2024-03-01T00:00:00+00:00,2024-03-01T01:00:00+00:00,0.01,100,100.05,1.0005,"
            "0.001,1.0015,98,104,close,2024-03-01T05:00:00+00:00,2024-03-01T06:00:00+00:00,103.9,,False,"
            "1.039,0.001039,0.036461,False,False"
        )
        path = tmp_path / "trades.csv"
        path.write_text(self.HEADER + "\n" + row + "\n", encoding="utf-8", newline="")
        (loaded,) = load_trades_csv(path)
        assert loaded == TradeFacts(
            symbol="BTCUSDT",
            entry_time=datetime(2024, 3, 1, 1, tzinfo=timezone.utc),
            exit_time=datetime(2024, 3, 1, 6, tzinfo=timezone.utc),
            entry_notional=D("1.0005"),
            entry_fee=D("0.001"),
            entry_quote_total=D("1.0015"),
            exit_gross=D("1.039"),
            exit_fee=D("0.001039"),
            realised=D("0.036461"),
        )
        assert loaded.holding == timedelta(hours=5)
        assert loaded.gross_pnl == D("0.0385")

    def test_a_file_with_only_a_header_has_no_trades(self, tmp_path: Path) -> None:
        path = tmp_path / "trades.csv"
        path.write_text(self.HEADER + "\n", encoding="utf-8", newline="")
        assert load_trades_csv(path) == ()
