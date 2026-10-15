"""``backtesting/selection.py``: the selection over all 216, the walk-forward, reading a run, and the output.

Every figure is worked by hand beside the assertion that pins it. The rules, the statistic and the ledger are
in ``test_selection_rules.py``; the builders are in ``selection_world.py``.

The walk-forward scenario, rules with a 3-trade minimum. Point A (training before 2020: +10, -5, +5 on a quote of
100, so a training profit factor of 15 / 5 = 3) and point B (+2, -4, +1: 3 / 4 = 0.75). In 2020 A has -10 and +4
(forward profit factor 4 / 10 = 0.4) and B has +20 and -2 (forward 10). For the 2021 fold the training trades
include 2020: A has gains 10 + 5 + 4 = 19 over losses 5 + 10 = 15 (1.2666...) and B gains 2 + 1 + 20 = 23 over
losses 4 + 2 = 6 (3.8333...), so B is picked.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
from dataclasses import replace
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from tests.unit.protocol_world import PROTOCOL, effective
from tests.unit.selection_world import (
    GRID,
    RULES,
    bulk,
    full_ledger,
    make_run,
    point,
    trade,
    variant_for,
)
from trading_bot.backtesting import selection as sel
from trading_bot.backtesting.candidate import candidate_digest
from trading_bot.backtesting.protocol import parse_entry

D = Decimal


# --------------------------------------------------------------------------------------
# The selection over all 216
# --------------------------------------------------------------------------------------
class TestSelect:
    def test_an_incomplete_sweep_is_refused_and_the_message_counts_it(self) -> None:
        found = [
            point(v, bulk(300, 100), run=f"r{i}")
            for i, v in enumerate(list(PROTOCOL.variants())[:200])
        ]
        ledger = sel.reconcile(PROTOCOL, found)
        with pytest.raises(
            sel.SelectionRefusedError, match="16 of 216 declared variants have no run"
        ):
            sel.select(PROTOCOL, RULES, ledger)

    def test_a_conflict_is_refused(self) -> None:
        v = next(iter(PROTOCOL.variants()))
        found = [
            point(w, bulk(300, 100), run=f"r{i:03d}") for i, w in enumerate(PROTOCOL.variants())
        ]
        found.append(point(v, bulk(300, 100), run="zz", log="b"))
        with pytest.raises(sel.SelectionRefusedError, match="disagree on the trade log"):
            sel.select(PROTOCOL, RULES, sel.reconcile(PROTOCOL, found))

    def test_twelve_cells_in_the_declared_order_each_with_its_points(self) -> None:
        selection = sel.select(PROTOCOL, RULES, full_ledger())
        labels = [c.cell.label for c in selection.cells]
        assert len(labels) == 12 and labels[0] == "sma_crossover 1h filter off"
        assert labels[1] == "sma_crossover 1h filter on" and labels[-1] == "rsi 1d filter on"
        assert [len(c.assessments) for c in selection.cells] == [9] * 6 + [27] * 6
        assert sum(len(c.assessments) for c in selection.cells) == 216

    def test_each_cell_picks_its_own_best_point_and_ties_go_to_the_first(self) -> None:
        variants = list(PROTOCOL.variants())
        cell_first = variants[0]
        better = variants[3]
        special = {sel.variant_key(better): bulk(300, 50)}
        selection = sel.select(PROTOCOL, RULES, full_ledger(special))
        first_cell = selection.cells[0]
        assert first_cell.candidate is not None
        assert sel.variant_key(first_cell.candidate.variant) == sel.variant_key(better)
        # every other cell: all 27 or 9 points tie, so the first point of the cell wins
        second_cell = selection.cells[1]
        assert second_cell.candidate is not None
        assert sel.variant_key(second_cell.candidate.variant) == sel.variant_key(variants[9])
        assert cell_first is not better

    def test_a_cell_whose_every_point_is_ineligible_has_no_candidate_and_the_rest_do(self) -> None:
        variants = list(PROTOCOL.variants())
        first_cell = [v for v in variants if sel.cell_of(v) == sel.cell_of(variants[0])]
        special = {sel.variant_key(v): bulk(10, 5) for v in first_cell}
        selection = sel.select(PROTOCOL, RULES, full_ledger(special))
        assert selection.cells[0].candidate is None and selection.cells[0].eligible_count == 0
        assert len(selection.candidates) == 11
        assert all(c.candidate is not None for c in selection.cells[1:])

    def test_a_ruined_point_is_not_chosen_though_it_has_the_best_statistic(self) -> None:
        variants = list(PROTOCOL.variants())
        ruined = variants[2]
        found = [
            point(
                v,
                bulk(300, 20) if v is ruined else bulk(300, 100),
                run=f"r{i:03d}",
                drawdown="0.99" if v is ruined else "0.5",
            )
            for i, v in enumerate(variants)
        ]
        selection = sel.select(PROTOCOL, RULES, sel.reconcile(PROTOCOL, found))
        candidate = selection.cells[0].candidate
        assert candidate is not None and sel.variant_key(candidate.variant) == sel.variant_key(
            variants[0]
        )
        reasons = {a.run: a.reasons for a in selection.cells[0].assessments}
        assert reasons["r002"] == (sel.Ineligible.RUINED,)

    def test_the_selection_never_looks_at_the_usdt_profit_factor(self) -> None:
        variants = list(PROTOCOL.variants())
        found = [
            point(v, bulk(300, 100), run=f"r{i:03d}", usdt="99" if i == 4 else "1")
            for i, v in enumerate(variants)
        ]
        selection = sel.select(PROTOCOL, RULES, sel.reconcile(PROTOCOL, found))
        candidate = selection.cells[0].candidate
        assert candidate is not None and candidate.run == "r000"
        assert candidate.usdt_profit_factor == D(1)

    def test_it_carries_the_protocols_digest_and_the_rules(self) -> None:
        selection = sel.select(PROTOCOL, RULES, full_ledger())
        assert selection.protocol_sha256 == PROTOCOL.sha256 and selection.rules == RULES
        assert len(selection.candidates) == 12


# --------------------------------------------------------------------------------------
# The walk-forward (R-CF)
# --------------------------------------------------------------------------------------
SMALL = replace(RULES, min_trades=3)
A, B = variant_for(0), variant_for(1)


def walk_points() -> list[sel.PointRun]:
    a = (
        trade("2018-03-01T00:00:00", "10"),
        trade("2018-06-01T00:00:00", "-5"),
        trade("2019-03-01T00:00:00", "5"),
        trade("2020-02-01T00:00:00", "-10"),
        trade("2020-05-01T00:00:00", "4"),
        trade("2021-03-01T00:00:00", "-1"),
        trade("2021-06-01T00:00:00", "2"),
    )
    b = (
        trade("2018-03-01T00:00:00", "2"),
        trade("2018-06-01T00:00:00", "-4"),
        trade("2019-03-01T00:00:00", "1"),
        trade("2020-02-01T00:00:00", "20"),
        trade("2020-05-01T00:00:00", "-2"),
        trade("2021-03-01T00:00:00", "3"),
        trade("2021-06-01T00:00:00", "-1"),
    )
    return [point(A, a, run="A"), point(B, b, run="B")]


class TestDailyCloseDrawdown:
    def test_the_peak_starts_at_the_initial_balance(self) -> None:
        closes = ((date(2020, 1, 1), D(90)), (date(2020, 1, 2), D(80)))
        assert sel.daily_close_drawdown(D(100), closes, date(2021, 1, 1)) == D("0.2")

    def test_the_largest_fall_from_the_running_peak(self) -> None:
        closes = ((date(2020, 1, 1), D(110)), (date(2020, 1, 2), D(55)), (date(2020, 1, 3), D(60)))
        assert sel.daily_close_drawdown(D(100), closes, date(2021, 1, 1)) == D("0.5")

    def test_days_on_or_after_the_cutoff_are_not_read(self) -> None:
        closes = ((date(2020, 1, 1), D(100)), (date(2020, 1, 2), D(1)))
        assert sel.daily_close_drawdown(D(100), closes, date(2020, 1, 2)) == D(0)
        assert sel.daily_close_drawdown(D(100), closes, date(2020, 1, 3)) == D("0.99")

    def test_no_closes_is_no_drawdown(self) -> None:
        assert sel.daily_close_drawdown(D(100), (), date(2021, 1, 1)) == D(0)


class TestTheWalkForward:
    def test_the_first_fold_picks_from_training_alone_and_reports_the_forward_year(self) -> None:
        folds = sel.walk_forward(walk_points(), SMALL, B)
        first = folds[0]
        assert first.year == 2020 and first.eligible_points == 2
        assert first.picked == A and first.picked_run == "A"
        assert first.training_statistic == D(3)
        assert first.forward_trades == 2 and first.forward_statistic == D("0.4")
        assert first.is_candidate is False

    def test_training_widens_with_each_fold_and_the_pick_can_change(self) -> None:
        folds = sel.walk_forward(walk_points(), SMALL, B)
        second = folds[1]
        assert second.year == 2021 and second.picked == B
        assert second.training_statistic == D(23) / D(6)
        assert second.forward_trades == 2 and second.forward_statistic == D(3)
        assert second.is_candidate is True

    def test_all_four_folds_are_reported_in_order(self) -> None:
        folds = sel.walk_forward(walk_points(), SMALL, None)
        assert [f.year for f in folds] == [2020, 2021, 2022, 2023]
        assert all(f.is_candidate is False for f in folds)

    def test_a_fold_with_no_forward_trades_reports_none(self) -> None:
        folds = sel.walk_forward(walk_points(), SMALL, None)
        assert (
            folds[2].year == 2022
            and folds[2].forward_trades == 0
            and folds[2].forward_statistic is None
        )

    def test_the_trade_minimum_is_not_scaled_to_the_training_window(self) -> None:
        folds = sel.walk_forward(walk_points(), replace(SMALL, min_trades=4), None)
        assert folds[0].picked is None and folds[0].eligible_points == 0
        assert folds[0].forward_trades == 0 and folds[0].training_statistic is None
        assert folds[1].eligible_points == 2

    def test_a_point_ruined_before_the_fold_is_ineligible_in_it_but_a_later_ruin_is_not_seen(
        self,
    ) -> None:
        points = walk_points()
        crash = ((date(2019, 6, 1), D(10000)), (date(2019, 7, 1), D(400)))
        points[0] = dataclasses.replace(points[0], daily_closes=crash)
        folds = sel.walk_forward(points, SMALL, None)
        assert folds[0].picked == B and folds[0].eligible_points == 1
        later = ((date(2020, 6, 1), D(10000)), (date(2020, 7, 1), D(400)))
        points[0] = dataclasses.replace(points[0], daily_closes=later)
        folds = sel.walk_forward(points, SMALL, None)
        assert folds[0].picked == A and folds[0].eligible_points == 2
        assert folds[1].eligible_points == 1 and folds[1].picked == B

    def test_a_tie_in_training_goes_to_the_first_point(self) -> None:
        twin = point(B, walk_points()[0].trades, run="twin")
        folds = sel.walk_forward([walk_points()[0], twin], SMALL, None)
        assert folds[0].picked_run == "A"

    def test_a_training_window_with_no_losing_trade_is_ineligible(self) -> None:
        wins = tuple(trade(f"2018-0{m}-01T00:00:00", "5") for m in range(1, 5))
        folds = sel.walk_forward([point(A, wins, run="W")], SMALL, None)
        assert folds[0].picked is None

    def test_trades_are_split_by_entry_time_at_midnight_utc(self) -> None:
        edge = (
            trade("2019-12-31T23:59:59", "10"),
            trade("2019-06-01T00:00:00", "-5"),
            trade("2019-03-01T00:00:00", "5"),
            trade("2020-01-01T00:00:00", "-3"),
            trade("2020-12-31T23:59:59", "6"),
            trade("2021-01-01T00:00:00", "9"),
        )
        folds = sel.walk_forward([point(A, edge, run="E")], SMALL, None)
        assert folds[0].training_statistic == D(3)
        assert folds[0].forward_trades == 2 and folds[0].forward_statistic == D(2)

    def test_the_folds_above_one_are_counted_on_the_cell(self) -> None:
        cell = sel.CellResult(
            sel.cell_of(A), (), None, sel.walk_forward(walk_points(), SMALL, None)
        )
        assert cell.folds_above_one == 1


# --------------------------------------------------------------------------------------
# Reading a run directory through the door
# --------------------------------------------------------------------------------------
class TestReadRun:
    def test_an_evidence_eligible_in_sample_grid_run_at_the_gate_arm_is_a_point_run(
        self, tmp_path: Path
    ) -> None:
        directory = make_run(tmp_path)
        got = sel.read_run(directory, PROTOCOL, RULES)
        assert isinstance(got, sel.PointRun)
        assert got.variant == GRID and got.run == directory.name
        assert (
            got.record_sha256 == hashlib.sha256((directory / "run.json").read_bytes()).hexdigest()
        )
        assert len(got.trades) == 2 and got.max_drawdown == D("0.31")
        assert got.usdt_profit_factor == D("0.8") and got.trade_log_sha256 == "e" * 64
        assert got.initial_balance == D(10000) and got.candidate_digest == candidate_digest(
            effective(params={"fast_period": 10, "slow_period": 50}, timeframe="1h")
        )
        assert [d for d, _ in got.daily_closes] == [
            date(2017, 8, 17),
            date(2020, 1, 1),
            date(2023, 12, 31),
        ]

    def test_a_record_that_is_not_evidence_is_skipped_and_named(self, tmp_path: Path) -> None:
        got = sel.read_run(make_run(tmp_path, flag=False), PROTOCOL, RULES)
        assert isinstance(got, sel.SkippedRun) and got.reason is sel.SkipReason.NOT_EVIDENCE

    def test_a_directory_still_named_running_is_never_a_point_run_even_with_its_record(
        self, tmp_path: Path
    ) -> None:
        """The command writes the record, THEN renames the directory: a power cut between leaves both."""
        got = sel.read_run(make_run(tmp_path, "20260101T000000000000Z-running"), PROTOCOL, RULES)
        assert isinstance(got, sel.SkippedRun) and got.reason is sel.SkipReason.NOT_SEALED
        assert "never renamed" in got.detail

    def test_a_running_directory_with_no_record_is_not_sealed_either(self, tmp_path: Path) -> None:
        unsealed = tmp_path / "20260101T000000000000Z-running"
        unsealed.mkdir()
        got = sel.read_run(unsealed, PROTOCOL, RULES)
        assert isinstance(got, sel.SkippedRun) and got.reason is sel.SkipReason.NOT_SEALED

    def test_a_directory_with_no_record_is_skipped_as_not_evidence(self, tmp_path: Path) -> None:
        failed = tmp_path / "20261014T154834857585Z-failed"
        failed.mkdir()
        got = sel.read_run(failed, PROTOCOL, RULES)
        assert isinstance(got, sel.SkippedRun) and got.reason is sel.SkipReason.NOT_EVIDENCE

    def test_a_schema_before_the_guards_decision_is_skipped(self, tmp_path: Path) -> None:
        got = sel.read_run(make_run(tmp_path, schema=5), PROTOCOL, RULES)
        assert isinstance(got, sel.SkippedRun) and got.reason is sel.SkipReason.NOT_EVIDENCE

    def test_no_protocol_block_is_skipped(self, tmp_path: Path) -> None:
        got = sel.read_run(make_run(tmp_path, protocol=None), PROTOCOL, RULES)
        assert isinstance(got, sel.SkippedRun) and got.reason is sel.SkipReason.NO_PROTOCOL_BLOCK

    @pytest.mark.parametrize("window_class", ["out_of_sample", "straddling"])
    def test_a_run_that_touched_the_out_of_sample_window_is_never_a_point_run(
        self, tmp_path: Path, window_class: str
    ) -> None:
        got = sel.read_run(
            make_run(tmp_path, protocol={"window_class": window_class}), PROTOCOL, RULES
        )
        assert isinstance(got, sel.SkippedRun) and got.reason is sel.SkipReason.NOT_IN_SAMPLE

    def test_an_in_sample_run_over_a_shorter_window_is_skipped(self, tmp_path: Path) -> None:
        window = {"start_date": "2017-08-17", "end_date": "2017-08-20"}
        got = sel.read_run(make_run(tmp_path, window=window), PROTOCOL, RULES)
        assert isinstance(got, sel.SkippedRun) and got.reason is sel.SkipReason.OTHER_WINDOW

    def test_an_in_sample_run_that_starts_late_is_skipped(self, tmp_path: Path) -> None:
        window = {"start_date": "2018-01-01", "end_date": "2024-01-01"}
        got = sel.read_run(make_run(tmp_path, window=window), PROTOCOL, RULES)
        assert isinstance(got, sel.SkippedRun) and got.reason is sel.SkipReason.OTHER_WINDOW

    @pytest.mark.parametrize("arm", ["0.05", "0.66"])
    def test_a_run_at_an_information_arm_is_not_a_selection_run(
        self, tmp_path: Path, arm: str
    ) -> None:
        got = sel.read_run(make_run(tmp_path, arm=arm), PROTOCOL, RULES)
        assert isinstance(got, sel.SkippedRun) and got.reason is sel.SkipReason.OTHER_ARM

    def test_a_run_the_guard_gave_no_variant_is_off_grid(self, tmp_path: Path) -> None:
        block = {"window_class": "in_sample", "protocol_sha256": PROTOCOL.sha256, "arm": "1.2"}
        got = sel.read_run(make_run(tmp_path, protocol=block), PROTOCOL, RULES)
        assert isinstance(got, sel.SkippedRun) and got.reason is sel.SkipReason.OFF_GRID

    def test_a_run_made_under_another_protocol_digest_is_never_a_point_run(
        self, tmp_path: Path
    ) -> None:
        """PROTOCOL.md section 10: a run made before an amendment is not re-read under it."""
        got = sel.read_run(make_run(tmp_path, protocol_sha="0" * 64), PROTOCOL, RULES)
        assert isinstance(got, sel.SkippedRun) and got.reason is sel.SkipReason.OTHER_PROTOCOL
        assert "not re-read under it" in got.detail

    def test_a_record_that_names_no_protocol_digest_is_not_one_either(self, tmp_path: Path) -> None:
        block = {
            "window_class": "in_sample",
            "arm": "1.2",
            "variant": {
                "family": "sma_crossover",
                "timeframe": "1h",
                "filtered": False,
                "params": {"fast_period": "10", "slow_period": "50"},
            },
        }
        got = sel.read_run(make_run(tmp_path, protocol=block), PROTOCOL, RULES)
        assert isinstance(got, sel.SkippedRun) and got.reason is sel.SkipReason.OTHER_PROTOCOL

    def test_a_record_with_problems_is_skipped(self, tmp_path: Path) -> None:
        got = sel.read_run(make_run(tmp_path, problems=["error_log_records=2"]), PROTOCOL, RULES)
        assert isinstance(got, sel.SkippedRun) and got.reason is sel.SkipReason.UNREADABLE

    def test_a_trade_log_that_does_not_hold_the_counted_trades_is_skipped(
        self, tmp_path: Path
    ) -> None:
        got = sel.read_run(make_run(tmp_path, declared=3), PROTOCOL, RULES)
        assert isinstance(got, sel.SkippedRun) and got.reason is sel.SkipReason.UNREADABLE
        assert "holds 2" in got.detail

    def test_a_trade_with_a_naive_entry_time_is_skipped(self, tmp_path: Path) -> None:
        rows = [("BTCUSDT", "2018-03-01T00:00:00", "10")]
        got = sel.read_run(make_run(tmp_path, rows=rows), PROTOCOL, RULES)
        assert isinstance(got, sel.SkippedRun) and got.reason is sel.SkipReason.UNREADABLE
        assert "time zone" in got.detail


# --------------------------------------------------------------------------------------
# The selection file and the entries
# --------------------------------------------------------------------------------------
class TestTheOutput:
    def selection(self) -> sel.Selection:
        return sel.select(
            PROTOCOL, RULES, full_ledger({sel.variant_key(variant_for(3)): bulk(300, 50)})
        )

    def test_the_file_is_deterministic_ascii_with_one_trailing_lf(self) -> None:
        one = sel.selection_bytes(sel.selection_document(self.selection()))
        two = sel.selection_bytes(sel.selection_document(self.selection()))
        assert one == two and one.endswith(b"}\n") and b"\r" not in one
        assert all(byte < 128 for byte in one)

    def test_the_file_states_what_was_declared_what_ran_and_what_each_cell_chose(self) -> None:
        doc = sel.selection_document(self.selection())
        assert doc["selection_schema"] == sel.SELECTION_SCHEMA == 2
        assert doc["protocol_sha256"] == PROTOCOL.sha256
        assert (
            doc["variants_declared"],
            doc["variants_with_a_run"],
            doc["cells_with_a_candidate"],
        ) == (216, 216, 12)
        assert doc["rules"]["ruin_max_drawdown"] == "0.95" and doc["rules"]["min_trades"] == 250
        assert doc["rules"]["window"] == ["2017-08-17", "2024-01-01"]
        assert len(doc["cells"]) == 12 and doc["cells"][0]["entry_id"] == "s6-sma_crossover-1h-off"
        first = doc["cells"][0]
        assert first["candidate"]["variant"]["params"] == {"fast_period": "20", "slow_period": "50"}
        assert len(first["assessments"]) == 9 and len(first["walk_forward"]) == 4
        assert first["assessments"][0]["ineligible"] == [] and first["points"] == 9

    def test_numbers_are_exact_text_and_never_floats(self) -> None:
        data = sel.selection_bytes(sel.selection_document(self.selection()))
        cells = [r for r in sel.selection_records(data) if r["record"] == "cell"]
        assert cells[0]["candidate"]["return_profit_factor"] == str(
            sel.return_profit_factor(bulk(300, 50))
        )
        assert cells[0]["candidate"]["max_drawdown"] == "0.5"

    def file(self) -> tuple[bytes, dict[str, Any], list[dict[str, Any]]]:
        document = sel.selection_document(self.selection())
        data = sel.selection_bytes(document)
        return data, document, sel.selection_records(data)

    def test_the_file_is_one_record_a_line_and_a_line_per_variant_and_per_cell(self) -> None:
        """R-CU: 216 variants and 12 cells are 229 lines and a header, not 5,549 lines, and a commit of it fits."""
        data, document, records = self.file()
        lines = data.decode("ascii").split("\n")[:-1]
        extra = len(document["duplicates"]) + len(document["skipped"])
        assert len(lines) == len(records) == 1 + 216 + 12 + extra
        assert len(lines) < 1500
        kinds = [r["record"] for r in records]
        assert kinds[0] == "header" and kinds.count("header") == 1
        assert (kinds.count("variant"), kinds.count("cell")) == (216, 12)
        assert all(
            line == json.dumps(json.loads(line), sort_keys=True, ensure_ascii=True)
            for line in lines
        )

    def test_each_cells_variants_come_before_its_pick_and_carry_its_id(self) -> None:
        _, document, records = self.file()
        order: list[tuple[str, str]] = []
        for record in records[1:]:
            if record["record"] in ("variant", "cell"):
                order.append((str(record["record"]), str(record["entry_id"])))
        expected: list[tuple[str, str]] = []
        for cell in document["cells"]:
            expected += [("variant", cell["entry_id"])] * len(cell["assessments"])
            expected.append(("cell", cell["entry_id"]))
        assert order == expected

    def test_no_record_drops_or_invents_a_figure_of_the_document(self) -> None:
        """The change alters no pick: every digest and statistic of the document is in the file, unchanged."""
        _, document, records = self.file()
        header = records[0]
        assert {k: v for k, v in header.items() if k != "record"} == {
            k: v for k, v in document.items() if k not in ("cells", "duplicates", "skipped")
        }
        variants = [r for r in records if r["record"] == "variant"]
        want = [
            {"record": "variant", "entry_id": cell["entry_id"], **point}
            for cell in document["cells"]
            for point in cell["assessments"]
        ]
        assert variants == want
        picks = [r for r in records if r["record"] == "cell"]
        assert picks == [
            {"record": "cell", **{k: v for k, v in cell.items() if k != "assessments"}}
            for cell in document["cells"]
        ]
        assert all("assessments" not in p for p in picks)

    def test_duplicates_and_skipped_directories_are_records_of_their_own(self) -> None:
        found: list[sel.PointRun | sel.SkippedRun] = [
            point(v, bulk(300, 100), run=f"r{i:03d}") for i, v in enumerate(PROTOCOL.variants())
        ]
        found.append(sel.SkippedRun("x-running", sel.SkipReason.NOT_SEALED, "never sealed"))
        found.append(point(next(iter(PROTOCOL.variants())), bulk(300, 100), run="r999"))
        selection = sel.select(PROTOCOL, RULES, sel.reconcile(PROTOCOL, found))
        records = sel.selection_records(sel.selection_bytes(sel.selection_document(selection)))
        assert [r["record"] for r in records[-2:]] == ["duplicate", "skipped"]
        assert records[-1]["run"] == "x-running" and records[-1]["reason"] == "not_sealed"
        assert records[-2]["runs"] == ["r000", "r999"]

    @pytest.mark.parametrize(
        ("data", "why"),
        [
            (b'{"record": "header"}', "line feed"),
            (b'{"record": "header"}\n\n', "Expecting value"),
            (b"[1]\n", "line 1 is not a record"),
            (b'{"x": 1}\n', "line 1 is not a record"),
            (b'{"record": "header"}\n{"record": 3}\n', "line 2 is not a record"),
            ('{"record": "h", "x": "é"}\n'.encode(), "ascii"),
        ],
        ids=[
            "no_line_feed",
            "blank_line",
            "not_an_object",
            "no_kind",
            "kind_not_text",
            "non_ascii",
        ],
    )
    def test_a_file_that_is_not_records_is_refused_with_its_line(
        self, data: bytes, why: str
    ) -> None:
        with pytest.raises(ValueError, match=why):
            sel.selection_records(data)

    def test_a_candidate_entry_is_one_the_guard_parses_and_binds_to_the_runs_digest(self) -> None:
        selection = self.selection()
        cell = selection.cells[0]
        assert cell.candidate is not None
        body = sel.candidate_entry(cell, selection_sha256="c" * 64, arms=PROTOCOL.arms)
        entry = parse_entry(json.dumps(body))
        assert entry.id == "s6-sma_crossover-1h-off" and entry.kind == "candidate"
        assert entry.status == "pending" and entry.oos is None
        assert entry.candidate_digest == cell.candidate.candidate_digest
        assert sorted(entry.arms) == sorted(PROTOCOL.arms)
        assert body["selection"]["in_sample_run_json_sha256"] == cell.candidate.record_sha256
        assert body["selection"]["selection_file_sha256"] == "c" * 64
        assert body["selection"]["trades"] == 350 and body["ref"] == "sma_crossover"

    def test_entry_ids_are_distinct_across_the_twelve_cells(self) -> None:
        ids = {sel.entry_id(c.cell) for c in self.selection().cells}
        assert len(ids) == 12

    def test_a_cell_without_a_candidate_has_no_entry(self) -> None:
        variants = list(PROTOCOL.variants())
        first_cell = [v for v in variants if sel.cell_of(v) == sel.cell_of(variants[0])]
        selection = sel.select(
            PROTOCOL, RULES, full_ledger({sel.variant_key(v): bulk(1, 1) for v in first_cell})
        )
        with pytest.raises(sel.SelectionRefusedError, match="has no candidate"):
            sel.candidate_entry(selection.cells[0], selection_sha256="c" * 64, arms=PROTOCOL.arms)

    def test_the_report_names_the_candidates_the_ineligible_cells_and_the_walk_forward(
        self,
    ) -> None:
        text = sel.render_report(self.selection())
        assert "S6 SELECTION" in text and "no out-of-sample record is read" in text
        assert "CELL sma_crossover 1h filter off: 9 of 9 points eligible" in text
        assert "CANDIDATE sma_crossover 1h filter off (fast_period=20, slow_period=50)" in text
        assert "a report, not a gate" in text
        assert "folds with a forward return PF above 1" in text
        assert "variants declared 216; with a run 216" in text

    def test_the_report_says_when_a_cell_has_no_candidate(self) -> None:
        variants = list(PROTOCOL.variants())
        first_cell = [v for v in variants if sel.cell_of(v) == sel.cell_of(variants[0])]
        selection = sel.select(
            PROTOCOL, RULES, full_ledger({sel.variant_key(v): bulk(1, 1) for v in first_cell})
        )
        text = sel.render_report(selection)
        assert "0 of 9 points eligible" in text and "  no candidate" in text
        assert "no eligible point in training" in text

    def test_every_skipped_directory_is_in_the_report(self) -> None:
        found: list[sel.PointRun | sel.SkippedRun] = [
            point(v, bulk(300, 100), run=f"r{i:03d}") for i, v in enumerate(PROTOCOL.variants())
        ]
        found.append(
            sel.SkippedRun(
                "20261014T154834857585Z-failed", sel.SkipReason.NOT_EVIDENCE, "cannot be read"
            )
        )
        selection = sel.select(PROTOCOL, RULES, sel.reconcile(PROTOCOL, found))
        assert (
            "SKIPPED 20261014T154834857585Z-failed: not_evidence: cannot be read"
            in sel.render_report(selection)
        )
        doc = sel.selection_document(selection)
        assert doc["skipped"] == [
            {
                "run": "20261014T154834857585Z-failed",
                "reason": "not_evidence",
                "detail": "cannot be read",
            }
        ]
