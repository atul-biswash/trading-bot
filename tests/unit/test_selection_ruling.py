"""R-CM (amendment 3): the two variants the P118 rehearsal read in the reserved window are ineligible for selection.

The ruling: ``sma_crossover`` at 4h, ``fast_period`` 10 and ``slow_period`` 50, the trend filter off and on, "are
ineligible for selection. They are still swept and counted in S7's variant denominator." The declaration holds them
in ``selection.ineligible_variants``; the rules are read from the REAL ``PROTOCOL.md``, and the refusals are driven by
editing that declaration. Worked scenarios, by hand:

* In the cell ``sma_crossover 4h filter off`` the ruled variant has 300 wins and 20 losses (a return profit factor of
  30) and every other point 300 wins and 100 losses (6); the cell's candidate is the first OTHER point, because the
  ruled one is ineligible whatever its figures, and its assessment lists every reason it fails, ``ruled_ineligible``
  among them.
* The 216 are unchanged: the sweep still has 216 runs, the ledger declares 216, and the cell still holds 9 points
  of which 8 are eligible.
"""

from __future__ import annotations

from dataclasses import replace
from decimal import Decimal
from typing import Any

import pytest

from tests.unit.protocol_world import PROTOCOL
from tests.unit.selection_world import RULES, bulk, full_ledger, point, with_selection
from trading_bot.backtesting import selection as sel
from trading_bot.backtesting.protocol import Variant

D = Decimal
OFF = Variant("sma_crossover", "4h", False, {"fast_period": "10", "slow_period": "50"})
ON = Variant(
    "sma_crossover",
    "4h",
    True,
    {"fast_period": "10", "slow_period": "50", "trend_filter_period": "200"},
)


def good_item(**changes: Any) -> dict[str, Any]:
    item: dict[str, Any] = {
        "family": "sma_crossover",
        "timeframe": "4h",
        "filtered": False,
        "params": {"fast_period": "10", "slow_period": "50"},
        "ruling": "R-CM",
    }
    item.update(changes)
    return item


class TestTheDeclaration:
    def test_the_real_protocol_rules_exactly_those_two_ineligible(self) -> None:
        assert RULES.ineligible_variants == {sel.variant_key(OFF), sel.variant_key(ON)}

    def test_both_are_declared_points_so_the_denominator_is_untouched(self) -> None:
        declared = {sel.variant_key(v) for v in PROTOCOL.variants()}
        assert sel.variant_key(OFF) in declared and sel.variant_key(ON) in declared
        assert len(declared) == 216

    @pytest.mark.parametrize(
        ("change", "message"),
        [
            (lambda d: d["selection"].update(ineligible_variants="R-CM"), "not a list"),
            (lambda d: d["selection"].update(ineligible_variants=[1]), "not exactly"),
            (
                lambda d: d["selection"].update(ineligible_variants=[good_item(extra=1)]),
                "not exactly",
            ),
            (
                lambda d: d["selection"].update(ineligible_variants=[good_item(filtered="no")]),
                "mistyped field",
            ),
            (
                lambda d: d["selection"].update(
                    ineligible_variants=[good_item(params={"fast_period": 10, "slow_period": "50"})]
                ),
                "mistyped field",
            ),
            (
                lambda d: d["selection"].update(ineligible_variants=[good_item(ruling="")]),
                "mistyped field",
            ),
            (
                lambda d: d["selection"].update(
                    ineligible_variants=[
                        good_item(params={"fast_period": "11", "slow_period": "50"})
                    ]
                ),
                "not a declared point",
            ),
            (
                lambda d: d["selection"].update(ineligible_variants=[good_item(), good_item()]),
                "ineligible twice",
            ),
        ],
    )
    def test_a_list_that_is_not_the_protocols_is_refused(self, change: Any, message: str) -> None:
        with pytest.raises(sel.SelectionRulesError, match=message):
            sel.parse_rules(with_selection(change))

    def test_the_key_is_required_so_an_edit_cannot_drop_the_ruling_silently(self) -> None:
        with pytest.raises(sel.SelectionRulesError, match="has keys"):
            sel.parse_rules(with_selection(lambda d: d["selection"].pop("ineligible_variants")))

    def test_an_empty_list_is_a_valid_declaration(self) -> None:
        rules = sel.parse_rules(
            with_selection(lambda d: d["selection"].update(ineligible_variants=[]))
        )
        assert rules.ineligible_variants == frozenset()


class TestTheSelectionHonoursIt:
    def test_a_ruled_variant_with_the_best_figures_is_not_the_cells_candidate(self) -> None:
        ledger = full_ledger({sel.variant_key(OFF): bulk(300, 20)})
        selection = sel.select(PROTOCOL, RULES, ledger)
        cell = next(c for c in selection.cells if c.cell == sel.cell_of(OFF))
        assert cell.candidate is not None
        assert sel.variant_key(cell.candidate.variant) != sel.variant_key(OFF)
        assert cell.candidate.statistic == D(6)
        assert cell.eligible_count == 8 and len(cell.assessments) == 9

    def test_the_ruled_variant_lists_every_reason_it_fails_ruled_ineligible_among_them(
        self,
    ) -> None:
        ledger = full_ledger({sel.variant_key(OFF): bulk(10, 5)})
        selection = sel.select(PROTOCOL, RULES, ledger)
        cell = next(c for c in selection.cells if c.cell == sel.cell_of(OFF))
        ruled = next(
            a for a in cell.assessments if sel.variant_key(a.variant) == sel.variant_key(OFF)
        )
        assert ruled.reasons == (sel.Ineligible.TOO_FEW_TRADES, sel.Ineligible.RULED_INELIGIBLE)

    def test_a_ruled_variant_whose_every_figure_is_perfect_is_still_ineligible(self) -> None:
        item = point(OFF, bulk(300, 20))
        assessment = sel.assess(item, RULES)
        assert assessment.reasons == (sel.Ineligible.RULED_INELIGIBLE,) and not assessment.eligible
        assert sel.assess(item, replace(RULES, ineligible_variants=frozenset())).eligible

    def test_both_ruled_variants_are_still_swept_and_counted(self) -> None:
        selection = sel.select(PROTOCOL, RULES, full_ledger())
        assert selection.ledger.declared == 216 and len(selection.ledger.points) == 216
        assert sum(len(c.assessments) for c in selection.cells) == 216
        assert sum(c.eligible_count for c in selection.cells) == 214
        assert len(selection.candidates) == 12

    def test_a_walk_forward_fold_never_picks_a_ruled_variant(self) -> None:
        trades = (
            *bulk(300, 20),
            *tuple(replace(t, entry_time=t.entry_time.replace(year=2019)) for t in bulk(300, 20)),
        )
        other = Variant("sma_crossover", "4h", False, {"fast_period": "20", "slow_period": "50"})
        points = [point(OFF, trades, run="ruled"), point(other, bulk(300, 100), run="other")]
        small = replace(RULES, min_trades=3)
        folds = sel.walk_forward(points, small, None)
        assert all(f.picked != OFF for f in folds)
        assert folds[0].picked == other and folds[0].eligible_points == 1
        free = sel.walk_forward(points, replace(small, ineligible_variants=frozenset()), None)
        assert free[0].picked == OFF


class TestTheFileAndTheReportSayIt:
    def test_the_selection_file_records_the_ruled_variants_among_the_rules(self) -> None:
        document = sel.selection_document(sel.select(PROTOCOL, RULES, full_ledger()))
        listed = document["rules"]["ineligible_variants"]
        assert [(v["family"], v["timeframe"], v["filtered"]) for v in listed] == [
            ("sma_crossover", "4h", False),
            ("sma_crossover", "4h", True),
        ]
        assert listed[0]["params"] == {"fast_period": "10", "slow_period": "50"}

    def test_the_report_counts_them(self) -> None:
        text = sel.render_report(sel.select(PROTOCOL, RULES, full_ledger()))
        assert "ruled ineligible by the owner (R-CM), still run and counted: 2" in text
