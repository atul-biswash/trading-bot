"""``backtesting/selection.py``: the rules, the statistic, the eligibility rules, the tie-break and the ledger.

Every figure is worked by hand beside the assertion that pins it: a selection whose expected values came from
its own output proves nothing. The rules are read from the REAL ``PROTOCOL.md`` (``selection_world``) and the
refusals are driven by editing that declaration. The selection over all 216 variants, the walk-forward, the
reading of a run directory and the output are in ``test_selection_pipeline.py``.

The worked scenarios of this module.

* A trade is ``(entry, realised, quote total)``. Returns are ``realised / quote * 100``.
* Statistic: returns +10, -5, +5 give gains 15 over losses 5 = 3. The same trades with quote totals 10 and 1,000
  (realised +10 and -50) give returns +100 and -5, a return profit factor of 20, while the profit factor in USDT is
  10 / 50 = 0.2: the two measure different things, and R-CB selects on the first.
* Eligibility: 250 trades are enough and 249 are not; a drawdown of exactly 0.95 is not ruined and 0.9500001 is.
* Tie-break: 1.2500001 and 1.2500004 are the same to six places, so the first in the declared order wins; 1.0000004
  and 1.0000006 round to 1.000000 and 1.000001, so they are not tied.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import date
from decimal import Decimal
from typing import Any

import pytest

from tests.unit.protocol_world import PROTOCOL
from tests.unit.selection_world import (
    RULES,
    bulk,
    full_ledger,
    point,
    trade,
    variant_for,
    with_selection,
)
from trading_bot.backtesting import selection as sel
from trading_bot.backtesting.protocol import ProtocolError, Variant

D = Decimal


# --------------------------------------------------------------------------------------
# The rules
# --------------------------------------------------------------------------------------
class TestTheRulesAreTheRulings:
    def test_the_real_protocol_gives_the_numbers_the_owner_ruled(self) -> None:
        """R-CB to R-CF as numbers: 0.95 (R-CC), 250 (R-CD), the 1.20 arm (R-CE), four folds (R-CF)."""
        assert RULES.statistic == "return_profit_factor"
        assert RULES.arm == "1.2" == PROTOCOL.gate_arm
        assert RULES.ruin_max_drawdown == D("0.95")
        assert RULES.min_trades == 250 == PROTOCOL.min_in_sample_trades
        assert RULES.tie_places == 6
        assert RULES.train_start == date(2017, 8, 17) == PROTOCOL.history_start
        assert RULES.test_years == (2020, 2021, 2022, 2023)
        assert RULES.boundary == date(2024, 1, 1)

    @pytest.mark.parametrize(
        ("change", "message"),
        [
            (lambda d: d.pop("selection"), "is absent"),
            (lambda d: d["selection"].update(extra=1), "has keys"),
            (lambda d: d["selection"].pop("tie_places"), "has keys"),
            (
                lambda d: d["selection"].update(statistic="usdt_profit_factor"),
                "only 'return_profit_factor'",
            ),
            (lambda d: d["selection"].update(arm="0.66"), "selects on arm 0.66"),
            (lambda d: d["selection"].update(arm="x"), "not a number"),
            (lambda d: d["selection"].update(arm=1.2), "written as text"),
            (lambda d: d["selection"].update(ruin_max_drawdown="0"), r"outside \(0, 1\)"),
            (lambda d: d["selection"].update(ruin_max_drawdown="1"), r"outside \(0, 1\)"),
            (lambda d: d["selection"].update(ruin_max_drawdown="NaN"), "not finite"),
            (lambda d: d["selection"].update(tie_places=0), "outside 1 to 12"),
            (lambda d: d["selection"].update(tie_places=13), "outside 1 to 12"),
            (lambda d: d["selection"].update(tie_places=True), "not an integer"),
            (lambda d: d["selection"].update(tie_places="6"), "not an integer"),
            (lambda d: d["selection"]["walk_forward"].update(extra=1), "not exactly"),
            (
                lambda d: d["selection"]["walk_forward"].update(train_start="2018-01-01"),
                "history starts",
            ),
            (
                lambda d: d["selection"]["walk_forward"].update(train_start="soon"),
                "not an ISO date",
            ),
            (lambda d: d["selection"]["walk_forward"].update(test_years=[]), "no test_years"),
            (
                lambda d: d["selection"]["walk_forward"].update(test_years=[2021, 2020]),
                "strictly increasing",
            ),
            (
                lambda d: d["selection"]["walk_forward"].update(test_years=[2020, 2020]),
                "strictly increasing",
            ),
            (
                lambda d: d["selection"]["walk_forward"].update(test_years=[2017]),
                "no training window",
            ),
            (
                lambda d: d["selection"]["walk_forward"].update(test_years=[2020, 2024]),
                "ends after the boundary",
            ),
            (
                lambda d: d["selection"]["walk_forward"].update(test_years=["2020"]),
                "not an integer",
            ),
        ],
    )
    def test_a_selection_block_that_is_not_the_protocols_is_refused(
        self, change: Any, message: str
    ) -> None:
        with pytest.raises(sel.SelectionRulesError, match=message):
            sel.parse_rules(with_selection(change))

    def test_a_declaration_the_protocol_parser_refuses_is_refused_as_that(self) -> None:
        with pytest.raises(ProtocolError):
            sel.parse_rules("no declaration here")

    def test_the_trade_minimum_is_read_from_the_declaration_not_restated(self) -> None:
        rules = sel.parse_rules(with_selection(lambda d: d.update(min_in_sample_trades=7)))
        assert rules.min_trades == 7


# --------------------------------------------------------------------------------------
# The statistic (R-CB)
# --------------------------------------------------------------------------------------
class TestTheReturnProfitFactor:
    def test_gains_over_losses_of_the_returns_worked_by_hand(self) -> None:
        trades = (
            trade("2020-01-01T00:00:00", "10"),
            trade("2020-01-02T00:00:00", "-5"),
            trade("2020-01-03T00:00:00", "5"),
        )
        assert sel.return_profit_factor(trades) == D(3)

    def test_it_is_a_profit_factor_of_returns_not_of_usdt(self) -> None:
        """R-CB: +10 on a quote of 10 is +100 percent and -50 on 1,000 is -5 percent: 20, where USDT gives 0.2."""
        trades = (
            trade("2020-01-01T00:00:00", "10", quote="10"),
            trade("2020-01-02T00:00:00", "-50", quote="1000"),
        )
        assert sel.return_profit_factor(trades) == D(20)
        usdt = sum(t.realised for t in trades if t.realised > 0) / -sum(
            t.realised for t in trades if t.realised < 0
        )
        assert usdt == D("0.2")

    def test_a_zero_return_is_neither_a_gain_nor_a_loss(self) -> None:
        trades = (
            trade("2020-01-01T00:00:00", "4"),
            trade("2020-01-02T00:00:00", "0"),
            trade("2020-01-03T00:00:00", "-2"),
        )
        assert sel.return_profit_factor(trades) == D(2)

    def test_no_losing_trade_has_no_statistic(self) -> None:
        assert sel.return_profit_factor((trade("2020-01-01T00:00:00", "4"),)) is None
        assert sel.return_profit_factor((trade("2020-01-01T00:00:00", "0"),)) is None
        assert sel.return_profit_factor(()) is None

    def test_only_losses_give_zero(self) -> None:
        assert sel.return_profit_factor((trade("2020-01-01T00:00:00", "-2"),)) == D(0)

    def test_it_is_exact_decimal_arithmetic(self) -> None:
        trades = (trade("2020-01-01T00:00:00", "1"), trade("2020-01-02T00:00:00", "-3"))
        assert sel.return_profit_factor(trades) == D(1) / D(3)


# --------------------------------------------------------------------------------------
# Eligibility (R-CC, R-CD) and the choice with its tie-break
# --------------------------------------------------------------------------------------
class TestEligibility:
    def test_a_run_at_exactly_the_ruin_level_is_not_ruined(self) -> None:
        """R-CC says a drawdown that EXCEEDS 0.95 is ruined: 0.95 itself is not."""
        a = sel.assess(point(variant_for(), bulk(300, 100), drawdown="0.95"), RULES)
        assert a.eligible and a.reasons == ()

    def test_a_run_above_the_ruin_level_is_ruined(self) -> None:
        a = sel.assess(point(variant_for(), bulk(300, 100), drawdown="0.9500001"), RULES)
        assert a.reasons == (sel.Ineligible.RUINED,) and not a.eligible

    def test_two_hundred_and_fifty_trades_are_enough_and_two_forty_nine_are_not(self) -> None:
        assert sel.assess(point(variant_for(), bulk(200, 50)), RULES).eligible
        short = sel.assess(point(variant_for(), bulk(200, 49)), RULES)
        assert short.reasons == (sel.Ineligible.TOO_FEW_TRADES,) and short.trades == 249

    def test_a_run_with_no_losing_trade_is_ineligible_not_first(self) -> None:
        a = sel.assess(point(variant_for(), bulk(300, 0)), RULES)
        assert a.reasons == (sel.Ineligible.NO_LOSING_TRADE,) and a.statistic is None

    def test_every_failing_reason_is_recorded_not_only_the_first(self) -> None:
        a = sel.assess(point(variant_for(), bulk(3, 0), drawdown="0.99"), RULES)
        assert a.reasons == (
            sel.Ineligible.RUINED,
            sel.Ineligible.TOO_FEW_TRADES,
            sel.Ineligible.NO_LOSING_TRADE,
        )

    def test_the_figures_are_carried_whether_or_not_it_is_eligible(self) -> None:
        a = sel.assess(point(variant_for(), bulk(10, 5), drawdown="0.97", usdt="0.8"), RULES)
        assert (a.trades, a.max_drawdown, a.usdt_profit_factor) == (15, D("0.97"), D("0.8"))
        assert a.statistic == D(4)

    def test_the_minimum_comes_from_the_rules_not_a_constant(self) -> None:
        small = replace(RULES, min_trades=5)
        assert sel.assess(point(variant_for(), bulk(4, 1)), small).eligible
        assert not sel.assess(point(variant_for(), bulk(3, 1)), small).eligible


def assessed(value_pf: str, *, index: int, eligible: bool = True) -> sel.Assessment:
    """An assessment whose statistic is ``value_pf``, for the choice tests."""
    v = variant_for(index)
    return sel.Assessment(
        variant=v,
        run=f"r{index}",
        record_sha256="0" * 64,
        candidate_digest="1" * 64,
        trades=300,
        max_drawdown=D("0.5"),
        statistic=D(value_pf),
        usdt_profit_factor=None,
        reasons=() if eligible else (sel.Ineligible.RUINED,),
    )


class TestChoose:
    def test_the_highest_eligible_statistic_wins(self) -> None:
        items = [assessed("1.1", index=0), assessed("1.5", index=1), assessed("1.2", index=2)]
        chosen = sel.choose(items, 6)
        assert chosen is not None and chosen.run == "r1"

    def test_an_ineligible_point_never_wins_however_high(self) -> None:
        items = [assessed("1.1", index=0), assessed("9.9", index=1, eligible=False)]
        chosen = sel.choose(items, 6)
        assert chosen is not None and chosen.run == "r0"

    def test_a_tie_to_six_places_goes_to_the_first_in_the_declared_order(self) -> None:
        items = [assessed("1.2500001", index=0), assessed("1.2500004", index=1)]
        chosen = sel.choose(items, 6)
        assert chosen is not None and chosen.run == "r0"

    def test_the_order_is_the_order_given_so_swapping_swaps_the_winner(self) -> None:
        items = [assessed("1.2500004", index=1), assessed("1.2500001", index=0)]
        chosen = sel.choose(items, 6)
        assert chosen is not None and chosen.run == "r1"

    def test_values_that_round_apart_are_not_tied(self) -> None:
        """1.0000004 rounds to 1.000000 and 1.0000006 to 1.000001: the later, higher one wins."""
        items = [assessed("1.0000004", index=0), assessed("1.0000006", index=1)]
        chosen = sel.choose(items, 6)
        assert chosen is not None and chosen.run == "r1"

    def test_the_places_come_from_the_rules(self) -> None:
        items = [assessed("1.2501", index=0), assessed("1.2504", index=1)]
        wide = sel.choose(items, 6)
        narrow = sel.choose(items, 3)
        assert wide is not None and wide.run == "r1"
        assert narrow is not None and narrow.run == "r0"

    def test_a_tie_on_a_later_point_does_not_displace_an_earlier_better_one(self) -> None:
        items = [assessed("2", index=0), assessed("1", index=1), assessed("2", index=2)]
        chosen = sel.choose(items, 6)
        assert chosen is not None and chosen.run == "r0"

    def test_no_eligible_point_gives_none(self) -> None:
        assert sel.choose([assessed("1.5", index=0, eligible=False)], 6) is None
        assert sel.choose([], 6) is None


# --------------------------------------------------------------------------------------
# The ledger
# --------------------------------------------------------------------------------------
class TestTheLedger:
    def test_a_sweep_with_every_declared_variant_is_complete(self) -> None:
        ledger = full_ledger()
        assert ledger.declared == 216 and len(ledger.points) == 216
        assert ledger.missing == () and ledger.conflicts == () and ledger.duplicates == ()
        assert ledger.complete

    def test_a_missing_variant_is_named_and_the_ledger_is_incomplete(self) -> None:
        variants = list(PROTOCOL.variants())
        gone = variants[100]
        found = [
            point(v, bulk(300, 100), run=f"r{i}") for i, v in enumerate(variants) if v is not gone
        ]
        ledger = sel.reconcile(PROTOCOL, found)
        assert [sel.variant_key(v) for v in ledger.missing] == [sel.variant_key(gone)]
        assert not ledger.complete and len(ledger.points) == 215

    def test_a_variant_run_twice_with_the_same_trade_log_is_a_duplicate_and_the_first_name_stands(
        self,
    ) -> None:
        v = list(PROTOCOL.variants())[5]
        found = [
            point(w, bulk(300, 100), run=f"r{i:03d}") for i, w in enumerate(PROTOCOL.variants())
        ]
        found.append(point(v, bulk(300, 100), run="a-first"))
        ledger = sel.reconcile(PROTOCOL, found)
        assert ledger.complete
        ((dup_variant, names),) = ledger.duplicates
        assert sel.variant_key(dup_variant) == sel.variant_key(v) and names == ("a-first", "r005")
        assert ledger.points[sel.variant_key(v)].run == "a-first"

    def test_two_runs_of_a_variant_that_disagree_are_a_conflict(self) -> None:
        v = list(PROTOCOL.variants())[5]
        found = [
            point(w, bulk(300, 100), run=f"r{i:03d}") for i, w in enumerate(PROTOCOL.variants())
        ]
        found.append(point(v, bulk(300, 100), run="zz", log="b"))
        ledger = sel.reconcile(PROTOCOL, found)
        assert not ledger.complete
        ((conflict_variant, names),) = ledger.conflicts
        assert sel.variant_key(conflict_variant) == sel.variant_key(v) and names == ("r005", "zz")

    def test_a_point_run_of_an_undeclared_variant_is_listed_off_grid_and_does_not_count(
        self,
    ) -> None:
        odd = Variant("sma_crossover", "1h", False, {"fast_period": "15", "slow_period": "50"})
        found = [
            point(w, bulk(300, 100), run=f"r{i:03d}") for i, w in enumerate(PROTOCOL.variants())
        ]
        found.append(point(odd, bulk(300, 100), run="odd"))
        ledger = sel.reconcile(PROTOCOL, found)
        assert ledger.complete and len(ledger.points) == 216
        assert [(s.run, s.reason) for s in ledger.skipped] == [("odd", sel.SkipReason.OFF_GRID)]

    def test_skipped_directories_pass_through_sorted_by_name(self) -> None:
        found: list[sel.PointRun | sel.SkippedRun] = [
            sel.SkippedRun("b", sel.SkipReason.OTHER_ARM, "x"),
            sel.SkippedRun("a", sel.SkipReason.NOT_EVIDENCE, "y"),
        ]
        ledger = sel.reconcile(PROTOCOL, found)
        assert [s.run for s in ledger.skipped] == ["a", "b"]
        assert len(ledger.missing) == 216
