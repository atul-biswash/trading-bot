"""The registry sidecar, the manifest's optional keys, the deep re-check and the gap kinds.

Owner's rulings R-L and R-N: a row that was set aside is recorded with its raw line, shape and
source, and the bars it leaves missing are reported as ``quarantined`` where the archive's own
omissions are ``omitted``. The rows used are the real ones the P102 census quoted; a synthetic
row says so.
"""

from __future__ import annotations

import hashlib
import io
import json
import zipfile
from datetime import datetime, timezone
from itertools import pairwise
from pathlib import Path
from typing import ClassVar

import pytest

import trading_bot.data.historical as hist
from trading_bot.data.historical import (
    REGISTRY_NAME,
    Gap,
    GapKind,
    HistoricalStore,
    IrregularRow,
    KindedGap,
    ManifestEntry,
    ManifestError,
    RegistryEntry,
    RegistryKind,
    Row,
    RowShape,
    StoredFileError,
    check_stored,
    classify_gaps,
    ingest_zip,
    write_month,
)

SOURCE = "https://data.binance.vision/data/spot/monthly/klines/BTCUSDT/1m/BTCUSDT-1m-2017-12.zip"
MINUTE = 60_000
DAY = 86_400_000
DEC_1 = 1512086400000  # 2017-12-01T00:00Z

# BTCUSDT 1m 2017-12, lines 4681 and 4682 of the archive file, verbatim (M5m-071).
SHORT_1M = (
    "1512367200000,11476.87000000,11478.00000000,11476.87000000,11478.00000000,0.28948500,"
    "1512367220798,3322.46567959,4,0.28948500,3322.46567959,37184.18214844"
)
OFF_GRID_1M = (
    "1512367220799,11478.00000000,11478.00000000,11478.00000000,11478.00000000,0.00000000,"
    "1512367280798,0.00000000,0,0.00000000,0.00000000,37184.17978073"
)
CLEAN_HEADER = "open_time_ms,open,high,low,close,volume,close_time_ms"


def regular(opened: int, step: int = MINUTE) -> Row:
    return Row(
        opened,
        "10.00000000",
        "12.00000000",
        "9.00000000",
        "11.00000000",
        "1.00000000",
        opened + step - 1,
    )


def short_row() -> Row:
    return Row(
        1512367200000,
        "11476.87000000",
        "11478.00000000",
        "11476.87000000",
        "11478.00000000",
        "0.28948500",
        1512367220798,
    )


def irregular(line: int, shape: RowShape, raw: str) -> IrregularRow:
    return IrregularRow(line, shape, int(raw.split(",")[0]), raw)


def store(
    root: Path,
    month: str = "2017-12",
    *,
    rows: list[Row] | None = None,
    registered: list[IrregularRow] | None = None,
    quarantined: list[IrregularRow] | None = None,
    interval: str = "1m",
    source_url: str = SOURCE,
) -> ManifestEntry:
    """Store a month. With no arguments: a regular bar, a short bar, and one off-grid row."""
    default = rows is None
    return write_month(
        root,
        "BTCUSDT",
        interval,
        month,
        [regular(DEC_1), short_row()] if default else rows or [],
        source_url=source_url,
        zip_sha256="a" * 64,
        registered=[irregular(2, RowShape.SHORT_BAR, SHORT_1M)]
        if default and registered is None
        else registered or [],
        quarantined=[irregular(3, RowShape.OFF_GRID, OFF_GRID_1M)]
        if default and quarantined is None
        else quarantined or [],
    )


def series(root: Path, interval: str = "1m") -> Path:
    return root / "BTCUSDT" / interval


def registry_lines(root: Path, interval: str = "1m") -> list[dict[str, object]]:
    path = series(root, interval) / REGISTRY_NAME
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def manifest_lines(root: Path, interval: str = "1m") -> list[str]:
    return (series(root, interval) / "MANIFEST.jsonl").read_text(encoding="utf-8").splitlines()


def sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def kinds(report: hist.StoredReport) -> list[str]:
    return [problem.kind for problem in report.problems]


class TestTheManifestStaysCompatible:
    REQUIRED: ClassVar[set[str]] = {
        "symbol",
        "interval",
        "month",
        "file",
        "source_url",
        "zip_sha256",
        "rows",
        "first_open_time_ms",
        "last_open_time_ms",
        "csv_sha256",
    }

    def test_a_month_with_nothing_irregular_writes_exactly_the_pre_registry_keys(
        self, tmp_path: Path
    ) -> None:
        store(tmp_path, rows=[regular(DEC_1)], registered=[], quarantined=[])
        (line,) = manifest_lines(tmp_path)
        assert set(json.loads(line)) == self.REQUIRED

    def test_a_line_written_before_the_registry_existed_verifies_and_reads_as_no_lines(
        self, tmp_path: Path
    ) -> None:
        body = (
            CLEAN_HEADER
            + "\n1512086400000,10.00000000,12.00000000,9.00000000,11.00000000,1.00000000,"
            "1512086459999\n"
        )
        path = series(tmp_path) / "BTCUSDT-1m-2017-12.csv"
        path.parent.mkdir(parents=True)
        path.write_bytes(body.encode("ascii"))
        record = {
            "symbol": "BTCUSDT",
            "interval": "1m",
            "month": "2017-12",
            "file": "BTCUSDT/1m/BTCUSDT-1m-2017-12.csv",
            "source_url": SOURCE,
            "zip_sha256": "a" * 64,
            "rows": 1,
            "first_open_time_ms": DEC_1,
            "last_open_time_ms": DEC_1,
            "csv_sha256": sha(body),
        }
        (series(tmp_path) / "MANIFEST.jsonl").write_text(
            json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8"
        )
        report = check_stored(tmp_path, "BTCUSDT", "1m", rows=True)
        assert report.problems == ()
        entry = report.entries["2017-12"]
        assert (entry.registered, entry.quarantined, entry.registry_sha256) == (0, 0, "")

    def test_recording_a_month_with_registry_lines_leaves_an_earlier_line_byte_identical(
        self, tmp_path: Path
    ) -> None:
        store(tmp_path, "2017-11", rows=[regular(1509494400000)], registered=[], quarantined=[])
        (before,) = manifest_lines(tmp_path)
        store(tmp_path, "2017-12")
        lines = manifest_lines(tmp_path)
        assert lines[0] == before
        assert len(lines) == 2

    def test_an_optional_key_at_its_default_is_left_out_of_the_line(self, tmp_path: Path) -> None:
        store(
            tmp_path,
            rows=[regular(DEC_1), short_row()],
            registered=[irregular(2, RowShape.SHORT_BAR, SHORT_1M)],
            quarantined=[],
        )
        (line,) = manifest_lines(tmp_path)
        record = json.loads(line)
        assert record["registered"] == 1
        assert "quarantined" not in record
        assert len(record["registry_sha256"]) == 64

    def test_the_whole_manifest_is_rewritten_with_the_new_keys_where_they_apply(
        self, tmp_path: Path
    ) -> None:
        store(tmp_path)
        (line,) = manifest_lines(tmp_path)
        record = json.loads(line)
        assert (record["registered"], record["quarantined"]) == (1, 1)

    @pytest.mark.parametrize(
        "change",
        [
            {"surprise": 1},
            {"registered": "1"},
            {"registered": True},
            {"quarantined": -1, "registry_sha256": "b" * 64},
            {"registry_sha256": 5},
            {"registry_sha256": "b" * 64},
            {"registered": 1},
            {"registered": 1, "registry_sha256": "not a digest"},
        ],
    )
    def test_a_line_the_registry_keys_cannot_explain_is_refused(
        self, tmp_path: Path, change: dict[str, object]
    ) -> None:
        store(tmp_path, rows=[regular(DEC_1)], registered=[], quarantined=[])
        path = series(tmp_path) / "MANIFEST.jsonl"
        record = json.loads(path.read_text(encoding="utf-8"))
        record.update(change)
        path.write_text(json.dumps(record) + "\n", encoding="utf-8")
        report = check_stored(tmp_path, "BTCUSDT", "1m")
        assert report.entries == {}
        assert "bad_manifest_line" in kinds(report)

    def test_a_missing_required_key_is_still_refused(self, tmp_path: Path) -> None:
        store(tmp_path, rows=[regular(DEC_1)], registered=[], quarantined=[])
        path = series(tmp_path) / "MANIFEST.jsonl"
        record = json.loads(path.read_text(encoding="utf-8"))
        del record["csv_sha256"]
        path.write_text(json.dumps(record) + "\n", encoding="utf-8")
        assert "bad_manifest_line" in kinds(check_stored(tmp_path, "BTCUSDT", "1m"))


class TestTheRegistryFile:
    def test_each_irregular_row_is_one_sorted_line_with_its_raw_text_and_source(
        self, tmp_path: Path
    ) -> None:
        store(tmp_path)
        assert registry_lines(tmp_path) == [
            {
                "kind": "registered",
                "line": 2,
                "month": "2017-12",
                "open_time_ms": 1512367200000,
                "raw": SHORT_1M,
                "shape": "short_bar",
                "source_url": SOURCE,
            },
            {
                "kind": "quarantined",
                "line": 3,
                "month": "2017-12",
                "open_time_ms": 1512367220799,
                "raw": OFF_GRID_1M,
                "shape": "off_grid",
                "source_url": SOURCE,
            },
        ]

    def test_lines_are_written_in_file_order_whatever_order_they_were_given(
        self, tmp_path: Path
    ) -> None:
        store(
            tmp_path,
            rows=[regular(DEC_1), short_row()],
            registered=[irregular(2, RowShape.SHORT_BAR, SHORT_1M)],
            quarantined=[
                irregular(5, RowShape.OFF_GRID, OFF_GRID_1M),
                irregular(1, RowShape.CLOSE_NOT_AFTER_OPEN, OFF_GRID_1M),
            ],
        )
        assert [(r["line"], r["kind"]) for r in registry_lines(tmp_path)] == [
            (1, "quarantined"),
            (2, "registered"),
            (5, "quarantined"),
        ]

    def test_the_manifest_states_the_counts_and_the_digest_of_the_months_lines(
        self, tmp_path: Path
    ) -> None:
        entry = store(tmp_path)
        text = (series(tmp_path) / REGISTRY_NAME).read_text(encoding="utf-8")
        assert (entry.registered, entry.quarantined) == (1, 1)
        assert entry.registry_sha256 == sha(text)

    def test_a_month_with_nothing_irregular_writes_no_sidecar(self, tmp_path: Path) -> None:
        store(tmp_path, rows=[regular(DEC_1)], registered=[], quarantined=[])
        assert not (series(tmp_path) / REGISTRY_NAME).exists()

    def test_months_share_one_sidecar_in_month_order(self, tmp_path: Path) -> None:
        store(tmp_path, "2017-12")
        store(
            tmp_path,
            "2017-11",
            rows=[regular(1509494400000)],
            registered=[],
            quarantined=[irregular(7, RowShape.OFF_GRID, OFF_GRID_1M)],
        )
        assert [(r["month"], r["line"]) for r in registry_lines(tmp_path)] == [
            ("2017-11", 7),
            ("2017-12", 2),
            ("2017-12", 3),
        ]

    def test_storing_a_month_again_replaces_its_lines_and_leaves_the_others(
        self, tmp_path: Path
    ) -> None:
        store(tmp_path, "2017-12")
        store(
            tmp_path,
            "2017-11",
            rows=[regular(1509494400000)],
            registered=[],
            quarantined=[irregular(7, RowShape.OFF_GRID, OFF_GRID_1M)],
        )
        store(
            tmp_path,
            "2017-12",
            rows=[regular(DEC_1), short_row()],
            registered=[irregular(2, RowShape.SHORT_BAR, SHORT_1M)],
            quarantined=[],
        )
        assert [(r["month"], r["line"], r["kind"]) for r in registry_lines(tmp_path)] == [
            ("2017-11", 7, "quarantined"),
            ("2017-12", 2, "registered"),
        ]
        assert [json.loads(line)["month"] for line in manifest_lines(tmp_path)] == [
            "2017-11",
            "2017-12",
        ]

    def test_storing_a_month_again_with_nothing_irregular_removes_its_lines_then_the_file(
        self, tmp_path: Path
    ) -> None:
        store(tmp_path, "2017-12")
        store(tmp_path, "2017-12", rows=[regular(DEC_1)], registered=[], quarantined=[])
        assert not (series(tmp_path) / REGISTRY_NAME).exists()
        report = check_stored(tmp_path, "BTCUSDT", "1m", rows=True)
        assert report.problems == ()

    def test_no_temporary_file_is_left_behind(self, tmp_path: Path) -> None:
        store(tmp_path)
        assert sorted(p.name for p in series(tmp_path).iterdir()) == [
            "BTCUSDT-1m-2017-12.csv",
            REGISTRY_NAME,
            "MANIFEST.jsonl",
        ]

    def test_an_unreadable_sidecar_is_not_extended_and_nothing_is_written(
        self, tmp_path: Path
    ) -> None:
        directory = series(tmp_path)
        directory.mkdir(parents=True)
        (directory / REGISTRY_NAME).write_text("not json\n", encoding="utf-8")
        with pytest.raises(ManifestError, match="unreadable"):
            store(tmp_path)
        assert sorted(p.name for p in directory.iterdir()) == [REGISTRY_NAME]
        assert (directory / REGISTRY_NAME).read_text(encoding="utf-8") == "not json\n"

    def test_a_failed_manifest_write_leaves_orphan_lines_and_the_rerun_repairs_them(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def broken(*_args: object) -> None:
            raise OSError("the manifest could not be written")

        with monkeypatch.context() as patch:
            patch.setattr(hist, "_record", broken)
            with pytest.raises(OSError, match="manifest"):
                store(tmp_path)
        report = check_stored(tmp_path, "BTCUSDT", "1m")
        assert report.entries == {}
        assert sorted(kinds(report)) == ["orphan_registry", "unlisted_file"]
        store(tmp_path)
        assert check_stored(tmp_path, "BTCUSDT", "1m", rows=True).problems == ()


class TestCheckStoredReadsTheRegistry:
    def test_a_clean_month_verifies_and_carries_its_lines(self, tmp_path: Path) -> None:
        entry = store(tmp_path)
        report = check_stored(tmp_path, "BTCUSDT", "1m")
        assert report.problems == ()
        assert report.entries == {"2017-12": entry}
        assert [(line.kind, line.shape) for line in report.registry["2017-12"]] == [
            (RegistryKind.REGISTERED, RowShape.SHORT_BAR),
            (RegistryKind.QUARANTINED, RowShape.OFF_GRID),
        ]

    def test_an_edited_registry_line_is_a_mismatch_and_the_month_is_not_verified(
        self, tmp_path: Path
    ) -> None:
        store(tmp_path)
        path = series(tmp_path) / REGISTRY_NAME
        path.write_text(
            path.read_text(encoding="utf-8").replace("11478.00000000", "11479.00000000", 1),
            encoding="utf-8",
        )
        report = check_stored(tmp_path, "BTCUSDT", "1m")
        assert report.entries == {}
        assert kinds(report) == ["registry_mismatch"]
        assert "digest differs" in report.problems[0].detail

    def test_a_deleted_sidecar_is_a_mismatch(self, tmp_path: Path) -> None:
        store(tmp_path)
        (series(tmp_path) / REGISTRY_NAME).unlink()
        report = check_stored(tmp_path, "BTCUSDT", "1m")
        assert kinds(report) == ["registry_mismatch"]
        assert "states 1 registered and 1 quarantined, the registry holds 0 and 0" in (
            report.problems[0].detail
        )

    def test_a_line_removed_from_the_sidecar_is_a_mismatch(self, tmp_path: Path) -> None:
        store(tmp_path)
        path = series(tmp_path) / REGISTRY_NAME
        first = path.read_text(encoding="utf-8").splitlines()[0]
        path.write_text(first + "\n", encoding="utf-8")
        assert kinds(check_stored(tmp_path, "BTCUSDT", "1m")) == ["registry_mismatch"]

    def test_an_unreadable_registry_line_is_reported(self, tmp_path: Path) -> None:
        store(tmp_path)
        path = series(tmp_path) / REGISTRY_NAME
        path.write_text(path.read_text(encoding="utf-8") + "garbage\n", encoding="utf-8")
        assert "bad_registry_line" in kinds(check_stored(tmp_path, "BTCUSDT", "1m"))

    def test_a_quarantined_line_with_a_stored_shape_is_refused(self, tmp_path: Path) -> None:
        store(tmp_path)
        path = series(tmp_path) / REGISTRY_NAME
        records = registry_lines(tmp_path)
        records[1]["shape"] = "short_bar"
        path.write_text(
            "".join(json.dumps(r, sort_keys=True, separators=(",", ":")) + "\n" for r in records),
            encoding="utf-8",
        )
        assert "bad_registry_line" in kinds(check_stored(tmp_path, "BTCUSDT", "1m"))

    @pytest.mark.parametrize(
        "change",
        [{"line": 0}, {"line": "2"}, {"month": "2017-13"}, {"kind": "other"}, {"extra": 1}],
    )
    def test_a_registry_line_with_a_bad_field_is_refused(
        self, tmp_path: Path, change: dict[str, object]
    ) -> None:
        store(tmp_path)
        path = series(tmp_path) / REGISTRY_NAME
        records = registry_lines(tmp_path)
        records[0].update(change)
        path.write_text(
            "".join(json.dumps(r, sort_keys=True, separators=(",", ":")) + "\n" for r in records),
            encoding="utf-8",
        )
        assert "bad_registry_line" in kinds(check_stored(tmp_path, "BTCUSDT", "1m"))

    def test_lines_for_a_month_the_manifest_does_not_list_are_orphans(self, tmp_path: Path) -> None:
        store(tmp_path)
        (series(tmp_path) / "MANIFEST.jsonl").write_text("", encoding="utf-8")
        report = check_stored(tmp_path, "BTCUSDT", "1m")
        assert ("orphan_registry", "2017-12") in [(p.kind, p.month) for p in report.problems]

    def test_a_sidecar_that_is_not_utf8_is_reported_not_raised(self, tmp_path: Path) -> None:
        store(tmp_path)
        (series(tmp_path) / REGISTRY_NAME).write_bytes(b"\xff\xfe\x00")
        assert "bad_registry_line" in kinds(check_stored(tmp_path, "BTCUSDT", "1m"))


class TestDeepVerificationOfTheStoredRows:
    def test_a_month_with_registered_and_quarantined_rows_is_clean_in_depth(
        self, tmp_path: Path
    ) -> None:
        store(tmp_path)
        assert HistoricalStore(tmp_path).verify("BTCUSDT", "1m") == ()

    def test_the_shallow_check_does_not_read_rows_and_the_deep_one_does(
        self, tmp_path: Path
    ) -> None:
        store(tmp_path, rows=[regular(DEC_1), short_row()], registered=[], quarantined=[])
        assert check_stored(tmp_path, "BTCUSDT", "1m").problems == ()
        deep = HistoricalStore(tmp_path).verify("BTCUSDT", "1m")
        assert [p.kind for p in deep] == ["registry_rows_mismatch"]

    def test_a_stored_irregular_row_registered_under_another_shape_is_a_mismatch(
        self, tmp_path: Path
    ) -> None:
        store(
            tmp_path,
            rows=[regular(DEC_1), short_row()],
            registered=[irregular(2, RowShape.WHOLE_SECOND, SHORT_1M)],
            quarantined=[],
        )
        assert [p.kind for p in HistoricalStore(tmp_path).verify("BTCUSDT", "1m")] == [
            "registry_rows_mismatch"
        ]

    def test_a_registered_row_that_is_stored_regular_is_a_mismatch(self, tmp_path: Path) -> None:
        store(
            tmp_path,
            rows=[regular(DEC_1)],
            registered=[irregular(1, RowShape.SHORT_BAR, SHORT_1M)],
            quarantined=[],
        )
        assert [p.kind for p in HistoricalStore(tmp_path).verify("BTCUSDT", "1m")] == [
            "registry_rows_mismatch"
        ]

    @pytest.mark.parametrize(
        ("row", "detail"),
        [
            (Row(DEC_1 + 1, "10.0", "12.0", "9.0", "11.0", "1.0", DEC_1 + MINUTE), "off_grid"),
            (Row(DEC_1, "10.0", "12.0", "9.0", "11.0", "1.0", DEC_1), "close_not_after_open"),
            (Row(DEC_1, "0", "12.0", "9.0", "11.0", "1.0", DEC_1 + MINUTE - 1), "not positive"),
            (Row(DEC_1, "10.0", "12.0", "10.5", "11.0", "1.0", DEC_1 + MINUTE - 1), "enclose"),
            (Row(DEC_1, "10.0", "12.0", "9.0", "11.0", "1.0", DEC_1 + MINUTE + 5), "no class"),
        ],
    )
    def test_a_stored_row_the_ingest_rule_would_not_store_is_reported(
        self, tmp_path: Path, row: Row, detail: str
    ) -> None:
        store(tmp_path, rows=[row], registered=[], quarantined=[])
        problems = HistoricalStore(tmp_path).verify("BTCUSDT", "1m")
        assert [p.kind for p in problems][:1] == ["bad_stored_row"]
        assert detail in problems[0].detail
        assert problems[0].detail.startswith("row 1: ")

    def test_rows_that_do_not_ascend_or_leave_the_month_are_reported(self, tmp_path: Path) -> None:
        store(
            tmp_path,
            rows=[regular(DEC_1 + MINUTE), regular(DEC_1), regular(DEC_1 - MINUTE)],
            registered=[],
            quarantined=[],
        )
        details = [p.detail for p in HistoricalStore(tmp_path).verify("BTCUSDT", "1m")]
        assert any("row 2" in d and "does not increase" in d for d in details)
        assert any("row 3" in d and "outside the month" in d for d in details)

    def test_the_problems_of_one_month_are_capped_at_five(self, tmp_path: Path) -> None:
        rows = [regular(DEC_1 + i * MINUTE + 1) for i in range(12)]
        store(tmp_path, rows=rows, registered=[], quarantined=[])
        problems = HistoricalStore(tmp_path).verify("BTCUSDT", "1m")
        assert [p.kind for p in problems] == ["bad_stored_row"] * 5

    def test_a_month_that_fails_the_shallow_check_is_not_read_again(self, tmp_path: Path) -> None:
        entry = store(tmp_path)
        path = tmp_path / entry.file
        path.write_bytes(path.read_bytes().replace(b"11476.87", b"11476.88", 1))
        assert [p.kind for p in HistoricalStore(tmp_path).verify("BTCUSDT", "1m")] == [
            "hash_mismatch"
        ]


class TestClassifyGaps:
    STEP = MINUTE

    def run(self, gaps: list[Gap], opens: list[int]) -> tuple[KindedGap, ...]:
        try:
            return classify_gaps(gaps, opens, self.STEP)
        except ValueError as exc:
            pytest.fail(f"gaps on the grid were refused: {exc}")

    def test_with_nothing_quarantined_every_gap_is_one_omitted_run(self) -> None:
        gaps = [Gap(10 * MINUTE, 20 * MINUTE, 10), Gap(30 * MINUTE, 31 * MINUTE, 1)]
        assert self.run(gaps, []) == (
            KindedGap(10 * MINUTE, 20 * MINUTE, 10, GapKind.OMITTED),
            KindedGap(30 * MINUTE, 31 * MINUTE, 1, GapKind.OMITTED),
        )

    def test_a_quarantined_row_splits_a_gap_into_three_runs(self) -> None:
        got = self.run([Gap(10 * MINUTE, 20 * MINUTE, 10)], [14 * MINUTE + 20_000])
        assert got == (
            KindedGap(10 * MINUTE, 14 * MINUTE, 4, GapKind.OMITTED),
            KindedGap(14 * MINUTE, 15 * MINUTE, 1, GapKind.QUARANTINED),
            KindedGap(15 * MINUTE, 20 * MINUTE, 5, GapKind.OMITTED),
        )

    def test_consecutive_slots_are_one_quarantined_run(self) -> None:
        opens = [12 * MINUTE + 5_000, 13 * MINUTE + 5_000, 14 * MINUTE + 5_000]
        got = self.run([Gap(10 * MINUTE, 20 * MINUTE, 10)], opens)
        assert [(g.start_ms, g.end_ms, g.kind) for g in got] == [
            (10 * MINUTE, 12 * MINUTE, GapKind.OMITTED),
            (12 * MINUTE, 15 * MINUTE, GapKind.QUARANTINED),
            (15 * MINUTE, 20 * MINUTE, GapKind.OMITTED),
        ]

    def test_slots_that_are_not_consecutive_are_separate_runs(self) -> None:
        got = self.run([Gap(10 * MINUTE, 20 * MINUTE, 10)], [12 * MINUTE, 14 * MINUTE])
        assert [g.kind for g in got] == [
            GapKind.OMITTED,
            GapKind.QUARANTINED,
            GapKind.OMITTED,
            GapKind.QUARANTINED,
            GapKind.OMITTED,
        ]
        assert [g.missing for g in got] == [2, 1, 1, 1, 5]

    def test_a_quarantined_first_or_last_slot_leaves_no_empty_omitted_run(self) -> None:
        got = self.run([Gap(10 * MINUTE, 13 * MINUTE, 3)], [10 * MINUTE + 1, 12 * MINUTE + 59_999])
        assert got == (
            KindedGap(10 * MINUTE, 11 * MINUTE, 1, GapKind.QUARANTINED),
            KindedGap(11 * MINUTE, 12 * MINUTE, 1, GapKind.OMITTED),
            KindedGap(12 * MINUTE, 13 * MINUTE, 1, GapKind.QUARANTINED),
        )

    def test_a_gap_covered_entirely_by_quarantined_slots_is_one_quarantined_run(self) -> None:
        opens = [10 * MINUTE + 1, 11 * MINUTE + 1, 12 * MINUTE + 1]
        assert self.run([Gap(10 * MINUTE, 13 * MINUTE, 3)], opens) == (
            KindedGap(10 * MINUTE, 13 * MINUTE, 3, GapKind.QUARANTINED),
        )

    def test_several_rows_in_one_slot_count_once(self) -> None:
        got = self.run([Gap(10 * MINUTE, 12 * MINUTE, 2)], [10 * MINUTE + 1, 10 * MINUTE + 59_000])
        assert [(g.missing, g.kind) for g in got] == [
            (1, GapKind.QUARANTINED),
            (1, GapKind.OMITTED),
        ]

    def test_a_row_outside_every_gap_changes_nothing(self) -> None:
        gaps = [Gap(10 * MINUTE, 12 * MINUTE, 2)]
        assert self.run(gaps, [5 * MINUTE, 12 * MINUTE, 40 * MINUTE]) == (
            KindedGap(10 * MINUTE, 12 * MINUTE, 2, GapKind.OMITTED),
        )

    def test_a_row_in_the_slot_at_the_gaps_end_belongs_after_it(self) -> None:
        gaps = [Gap(10 * MINUTE, 12 * MINUTE, 2)]
        assert [g.kind for g in self.run(gaps, [12 * MINUTE + 1])] == [GapKind.OMITTED]

    def test_gaps_are_classified_independently_and_in_order(self) -> None:
        gaps = [Gap(10 * MINUTE, 12 * MINUTE, 2), Gap(20 * MINUTE, 22 * MINUTE, 2)]
        got = self.run(gaps, [21 * MINUTE + 5, 10 * MINUTE + 5])
        assert [(g.start_ms // MINUTE, g.end_ms // MINUTE, g.kind.value) for g in got] == [
            (10, 11, "quarantined"),
            (11, 12, "omitted"),
            (20, 21, "omitted"),
            (21, 22, "quarantined"),
        ]
        assert sum(g.missing for g in got) == sum(g.missing for g in gaps)

    def test_the_runs_of_a_gap_add_up_to_the_gap(self) -> None:
        opens = [13 * MINUTE + 7, 14 * MINUTE + 7, 17 * MINUTE + 7, 30 * MINUTE]
        gap = Gap(10 * MINUTE, 20 * MINUTE, 10)
        got = self.run([gap], opens)
        assert sum(g.missing for g in got) == gap.missing
        assert got[0].start_ms == gap.start_ms and got[-1].end_ms == gap.end_ms
        assert all(a.end_ms == b.start_ms for a, b in pairwise(got))

    @pytest.mark.parametrize(
        "gap", [Gap(10 * MINUTE + 1, 20 * MINUTE, 9), Gap(10 * MINUTE, 20 * MINUTE + 1, 9)]
    )
    def test_a_gap_off_the_grid_is_refused(self, gap: Gap) -> None:
        with pytest.raises(ValueError, match="grid"):
            classify_gaps([gap], [], self.STEP)

    def test_the_2017_12_shifted_run_is_20400_quarantined_bars_then_13_omitted(self) -> None:
        # BTCUSDT 1m: after the short bar of 2017-12-04T06:00 the archive's bars open at
        # :20.799 past the minute until 2017-12-18T10:00:20.799, and then nothing until 10:14.
        gap = Gap(1512367260000, 1513592040000, 20413)
        opens = [1512367220799 + k * MINUTE for k in range(20401)]
        got = self.run([gap], opens)
        assert got == (
            KindedGap(1512367260000, 1513591260000, 20400, GapKind.QUARANTINED),
            KindedGap(1513591260000, 1513592040000, 13, GapKind.OMITTED),
        )


class TestCoverageSplitsGapsByKind:
    """Daily bars so that a month is a few rows and a day is a bar."""

    D1 = 1733011200000  # 2024-12-01T00:00Z

    def day(self, n: int) -> Row:
        return regular(self.D1 + (n - 1) * DAY, DAY)

    def off_grid_raw(self, n: int) -> str:
        opened = self.D1 + (n - 1) * DAY + 6 * 3_600_000
        return f"{opened},10.0,12.0,9.0,11.0,1.0,{opened + DAY - 1},0,0,0,0,0"

    def stored(self, root: Path) -> None:
        write_month(
            root,
            "BTCUSDT",
            "1d",
            "2024-12",
            [self.day(1), self.day(2), self.day(6)],
            source_url=SOURCE,
            zip_sha256="a" * 64,
            quarantined=[irregular(3, RowShape.OFF_GRID, self.off_grid_raw(3))],
        )

    def until(self) -> datetime:
        return datetime(2024, 12, 9, tzinfo=timezone.utc)

    def test_a_quarantined_day_is_not_an_omitted_one(self, tmp_path: Path) -> None:
        self.stored(tmp_path)
        coverage = HistoricalStore(tmp_path).coverage("BTCUSDT", "1d")
        assert coverage.gaps == (Gap(self.D1 + 2 * DAY, self.D1 + 5 * DAY, 3),)
        assert coverage.kinded_gaps == (
            KindedGap(self.D1 + 2 * DAY, self.D1 + 3 * DAY, 1, GapKind.QUARANTINED),
            KindedGap(self.D1 + 3 * DAY, self.D1 + 5 * DAY, 2, GapKind.OMITTED),
        )
        assert (coverage.quarantined_bars, coverage.omitted_bars, coverage.missing) == (1, 2, 3)

    def test_rows_plus_missing_equal_the_grid_and_missing_splits_exactly(
        self, tmp_path: Path
    ) -> None:
        self.stored(tmp_path)
        coverage = HistoricalStore(tmp_path).coverage("BTCUSDT", "1d", until=self.until())
        assert coverage.grid_bars == 8
        assert coverage.bars + coverage.missing == coverage.grid_bars
        assert coverage.omitted_bars + coverage.quarantined_bars == coverage.missing
        assert (coverage.omitted_bars, coverage.quarantined_bars) == (4, 1)

    def test_the_registry_rows_are_counted(self, tmp_path: Path) -> None:
        self.stored(tmp_path)
        coverage = HistoricalStore(tmp_path).coverage("BTCUSDT", "1d")
        assert (coverage.registered_rows, coverage.quarantined_rows) == (0, 1)

    def test_a_month_that_is_not_stored_is_omitted(self, tmp_path: Path) -> None:
        write_month(
            tmp_path, "BTCUSDT", "1d", "2024-11", [regular(1730419200000, DAY)],
            source_url=SOURCE, zip_sha256="a" * 64,
        )  # fmt: skip
        write_month(
            tmp_path, "BTCUSDT", "1d", "2025-01", [regular(1735689600000, DAY)],
            source_url=SOURCE, zip_sha256="a" * 64,
        )  # fmt: skip
        coverage = HistoricalStore(tmp_path).coverage("BTCUSDT", "1d")
        assert [g.kind for g in coverage.kinded_gaps] == [GapKind.OMITTED]
        assert coverage.omitted_bars == coverage.missing == 60

    def test_a_series_with_nothing_quarantined_has_only_omitted_gaps(self, tmp_path: Path) -> None:
        write_month(
            tmp_path, "BTCUSDT", "1d", "2024-12", [self.day(1), self.day(4)],
            source_url=SOURCE, zip_sha256="a" * 64,
        )  # fmt: skip
        coverage = HistoricalStore(tmp_path).coverage("BTCUSDT", "1d")
        assert coverage.quarantined_bars == 0
        assert coverage.omitted_bars == 2

    def test_an_empty_store_has_no_kinded_gaps(self, tmp_path: Path) -> None:
        coverage = HistoricalStore(tmp_path).coverage("BTCUSDT", "1d")
        assert (coverage.kinded_gaps, coverage.omitted_bars, coverage.quarantined_bars) == (
            (),
            0,
            0,
        )

    def test_a_month_with_an_edited_registry_is_not_counted_and_is_reported(
        self, tmp_path: Path
    ) -> None:
        self.stored(tmp_path)
        path = series(tmp_path, "1d") / REGISTRY_NAME
        path.write_text(
            path.read_text(encoding="utf-8").replace("off_grid", "off_grid ", 1), encoding="utf-8"
        )
        coverage = HistoricalStore(tmp_path).coverage("BTCUSDT", "1d")
        assert coverage.months == ()
        assert sorted(p.kind for p in coverage.problems) == [
            "bad_registry_line",
            "registry_mismatch",
        ]


class TestTheStoreReadsTheRegistry:
    def test_every_line_comes_back_by_month_then_line(self, tmp_path: Path) -> None:
        store(tmp_path)
        lines = HistoricalStore(tmp_path).registry("BTCUSDT", "1m")
        assert lines == (
            RegistryEntry(
                "2017-12",
                2,
                RegistryKind.REGISTERED,
                RowShape.SHORT_BAR,
                1512367200000,
                SHORT_1M,
                SOURCE,
            ),
            RegistryEntry(
                "2017-12",
                3,
                RegistryKind.QUARANTINED,
                RowShape.OFF_GRID,
                1512367220799,
                OFF_GRID_1M,
                SOURCE,
            ),
        )

    def test_a_series_never_stored_has_no_lines(self, tmp_path: Path) -> None:
        assert HistoricalStore(tmp_path).registry("BTCUSDT", "1m") == ()

    def test_an_unreadable_sidecar_is_a_stored_file_error(self, tmp_path: Path) -> None:
        directory = series(tmp_path)
        directory.mkdir(parents=True)
        (directory / REGISTRY_NAME).write_text("nope\n", encoding="utf-8")
        with pytest.raises(StoredFileError, match="registry"):
            HistoricalStore(tmp_path).registry("BTCUSDT", "1m")


class TestIngestPersistsWhatItSetAside:
    def zip_for(self, text: str) -> tuple[bytes, str]:
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("BTCUSDT-1m-2017-12.csv", text.encode("utf-8"))
        data = buffer.getvalue()
        return data, hashlib.sha256(data).hexdigest()

    def test_the_registry_holds_what_the_ingest_returned_with_its_zip_as_the_source(
        self, tmp_path: Path
    ) -> None:
        regular_line = (
            "1512086400000,10.00000000,12.00000000,9.00000000,11.00000000,1.00000000,"
            "1512086459999,11.0,1,0.5,5.5,0"
        )
        data, digest = self.zip_for("\n".join([regular_line, SHORT_1M, OFF_GRID_1M]) + "\n")
        try:
            result = ingest_zip(
                data,
                expected_sha256=digest,
                root=tmp_path,
                symbol="BTCUSDT",
                interval="1m",
                month="2017-12",
                source_url=SOURCE,
            )
        except hist.HistoricalDataError as exc:
            pytest.fail(f"a month of known classes was refused: {exc}")
        stored = HistoricalStore(tmp_path).registry("BTCUSDT", "1m")
        assert [(e.kind.value, e.shape.value, e.line, e.raw, e.source_url) for e in stored] == [
            ("registered", "short_bar", 2, SHORT_1M, SOURCE),
            ("quarantined", "off_grid", 3, OFF_GRID_1M, SOURCE),
        ]
        assert (result.entry.registered, result.entry.quarantined) == (1, 1)
        assert HistoricalStore(tmp_path).verify("BTCUSDT", "1m") == ()
