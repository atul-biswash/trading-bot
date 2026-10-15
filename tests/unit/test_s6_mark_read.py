"""``scripts/s6_mark_read.py`` and ``backtesting/readmark.py``: owner step O7, marking entries ``read`` (R-CP).

R-CP: entries are marked read by the tool, which "verifies each out-of-sample record through the evidence door and
writes the three record digests into the entry; it refuses an entry already read, a record that fails the door, and a
set other than exactly the three declared arms." The world is ``gate_world``: run directories written the way the
engine writes them (schema 6, passing the door), so a marked entry is also handed to ``gate.evaluate`` and judged,
which joins this tool to the gate that reads what it writes. Every refusal also asserts that NOTHING was written.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

import s6_mark_read as tool

from tests.unit.gate_world import (
    ARMS,
    ENTRY_ID,
    GATE_RULES,
    VARIANT,
    candidate_effective,
    make_oos_run,
)
from tests.unit.protocol_world import PROTOCOL_TEXT
from trading_bot.backtesting import gate, readmark
from trading_bot.backtesting.candidate import candidate_digest
from trading_bot.backtesting.protocol import parse_entry

OTHER_ID = "s6-sma_crossover-1h-on"


def pending(
    entry_id: str = ENTRY_ID, digest: str | None = None, spelling: str = "1.2"
) -> dict[str, Any]:
    return {
        "entry_schema": 1,
        "id": entry_id,
        "kind": "candidate",
        "ref": "sma_crossover",
        "candidate_digest": digest or candidate_digest(candidate_effective("1.2")),
        "arms": ["0.05", "0.66", spelling],
        "status": "pending",
        "oos": None,
        "selection": {"variant": VARIANT},
    }


class Clone:
    """A clone's files: the protocol, the entries directory and the backtests directory."""

    def __init__(self, root: Path) -> None:
        self.protocol = root / "docs" / "research" / "PROTOCOL.md"
        self.entries = root / "docs" / "research" / "entries"
        self.backtests = root / "data" / "backtests"
        self.entries.mkdir(parents=True)
        self.backtests.mkdir(parents=True)
        self.protocol.write_bytes(PROTOCOL_TEXT.encode("utf-8"))

    def entry(self, body: dict[str, Any]) -> Path:
        path = self.entries / f"{body['id']}.json"
        path.write_bytes(readmark.entry_bytes(body))
        return path

    def runs(self, entry_id: str = ENTRY_ID, *, arms: tuple[str, ...] = ARMS, **over: Any) -> None:
        for index, arm in enumerate(arms):
            name = f"20260101T00000{index}000000Z-{entry_id}-{arm}"
            make_oos_run(self.backtests, name, arm=arm, entry_id=entry_id, **over)

    def argv(self, *rest: str) -> list[str]:
        return [
            "--backtests",
            str(self.backtests),
            "--protocol",
            str(self.protocol),
            "--entries-dir",
            str(self.entries),
            *rest,
        ]

    def snapshot(self) -> dict[str, bytes]:
        return {p.name: p.read_bytes() for p in self.entries.iterdir()}


@pytest.fixture
def clone(tmp_path: Path) -> Clone:
    return Clone(tmp_path / "clone")


class TestMarking:
    def test_an_entry_with_its_three_records_becomes_read_with_their_digests(
        self, clone: Clone
    ) -> None:
        path = clone.entry(pending())
        clone.runs()
        assert tool.main(clone.argv()) == 0
        body = json.loads(path.read_text("utf-8"))
        assert body["status"] == "read"
        records = body["oos"]["records"]
        assert list(records) == ["0.05", "0.66", "1.2"]
        for arm, key in zip(ARMS, records, strict=True):
            run = clone.backtests / f"20260101T00000{ARMS.index(arm)}000000Z-{ENTRY_ID}-{arm}"
            assert records[key] == {
                "run": run.name,
                "run_json_sha256": hashlib.sha256((run / "run.json").read_bytes()).hexdigest(),
            }

    def test_everything_else_in_the_entry_is_kept_and_the_file_is_the_selections_shape(
        self, clone: Clone
    ) -> None:
        original = pending()
        path = clone.entry(original)
        clone.runs()
        assert tool.main(clone.argv()) == 0
        data = path.read_bytes()
        body = json.loads(data)
        assert {k: v for k, v in body.items() if k not in ("status", "oos")} == {
            k: v for k, v in original.items() if k not in ("status", "oos")
        }
        assert data == (json.dumps(body, indent=2) + "\n").encode("ascii")
        assert b"\r" not in data
        assert parse_entry(data.decode("ascii")).status == "read"

    def test_the_marked_entry_is_one_the_gate_reads_and_passes(self, clone: Clone) -> None:
        path = clone.entry(pending())
        clone.runs()
        assert tool.main(clone.argv()) == 0
        entry = parse_entry(path.read_text("utf-8"))
        report = gate.evaluate([entry], clone.backtests, GATE_RULES)
        assert [r.entry_id for r in report.results] == [ENTRY_ID] and report.results[0].passed

    def test_the_entrys_own_spelling_of_an_arm_is_the_key(self, clone: Clone) -> None:
        path = clone.entry(pending(spelling="1.20"))
        clone.runs()
        assert tool.main(clone.argv()) == 0
        assert list(json.loads(path.read_text("utf-8"))["oos"]["records"]) == [
            "0.05",
            "0.66",
            "1.20",
        ]

    def test_in_sample_records_and_unsealed_directories_are_ignored(self, clone: Clone) -> None:
        clone.entry(pending())
        clone.runs()
        make_oos_run(
            clone.backtests,
            "20260101T000009000000Z-in",
            entry_id=ENTRY_ID,
            window_class="in_sample",
        )
        (clone.backtests / "20260101T000010000000Z-running").mkdir()
        assert tool.main(clone.argv()) == 0

    def test_a_dry_run_verifies_and_prints_and_writes_nothing(
        self, clone: Clone, capsys: pytest.CaptureFixture[str]
    ) -> None:
        clone.entry(pending())
        clone.runs()
        before = clone.snapshot()
        assert tool.main(clone.argv("--dry-run")) == 0
        out = capsys.readouterr().out
        assert "would be marked read" in out and "dry run: nothing was written" in out
        assert clone.snapshot() == before

    def test_the_output_names_each_arm_run_and_digest_in_ascii(
        self, clone: Clone, capsys: pytest.CaptureFixture[str]
    ) -> None:
        clone.entry(pending())
        clone.runs()
        assert tool.main(clone.argv()) == 0
        out = capsys.readouterr().out
        assert out.isascii() and out.count("record sha256") == 3
        assert "arm 0.05" in out and "arm 1.2" in out and "next: git add" in out

    def test_entry_filters_select_one_and_leave_the_other_alone(self, clone: Clone) -> None:
        first = clone.entry(pending())
        second = clone.entry(pending(OTHER_ID))
        clone.runs()
        clone.runs(OTHER_ID)
        other_before = second.read_bytes()
        assert tool.main(clone.argv("--entry", ENTRY_ID)) == 0
        assert json.loads(first.read_text("utf-8"))["status"] == "read"
        assert second.read_bytes() == other_before

    def test_two_entries_are_both_marked_when_both_are_complete(self, clone: Clone) -> None:
        clone.entry(pending())
        clone.entry(pending(OTHER_ID))
        clone.runs()
        clone.runs(OTHER_ID)
        assert tool.main(clone.argv()) == 0
        assert {json.loads(b)["status"] for b in clone.snapshot().values()} == {"read"}


class TestRefusals:
    """Each is R-CP's or the plan's, and each leaves every entry byte-for-byte as it was."""

    def refused(
        self, clone: Clone, capsys: pytest.CaptureFixture[str], message: str, *rest: str
    ) -> None:
        before = clone.snapshot()
        assert tool.main(clone.argv(*rest)) == tool.EXIT_REFUSED
        err = capsys.readouterr().err
        assert err.startswith("REFUSED: ") and message in err, err
        assert clone.snapshot() == before

    def test_an_entry_already_read_is_refused(
        self, clone: Clone, capsys: pytest.CaptureFixture[str]
    ) -> None:
        clone.entry(pending())
        clone.runs()
        assert tool.main(clone.argv()) == 0
        capsys.readouterr()
        self.refused(clone, capsys, "is already read", "--entry", ENTRY_ID)

    def test_one_read_entry_refuses_the_whole_run_so_nothing_half_marks(
        self, clone: Clone, capsys: pytest.CaptureFixture[str]
    ) -> None:
        clone.entry(pending())
        clone.runs()
        assert tool.main(clone.argv()) == 0
        clone.entry(pending(OTHER_ID))
        clone.runs(OTHER_ID)
        capsys.readouterr()
        self.refused(clone, capsys, "is already read")

    @pytest.mark.parametrize(
        ("over", "message"),
        [
            ({"flag": False}, "fails the evidence door"),
            ({"schema": 5}, "fails the evidence door"),
        ],
    )
    def test_a_record_that_fails_the_door_refuses_everything(
        self, clone: Clone, capsys: pytest.CaptureFixture[str], over: dict[str, Any], message: str
    ) -> None:
        clone.entry(pending())
        clone.runs()
        make_oos_run(clone.backtests, "20260101T000008000000Z-bad", entry_id=ENTRY_ID, **over)
        self.refused(clone, capsys, message)

    def test_a_record_that_cannot_be_read_fails_the_door_too(
        self, clone: Clone, capsys: pytest.CaptureFixture[str]
    ) -> None:
        clone.entry(pending())
        clone.runs()
        broken = clone.backtests / "20260101T000008000000Z-broken"
        broken.mkdir()
        (broken / "run.json").write_text("{not json", encoding="utf-8")
        self.refused(clone, capsys, "fails the evidence door")

    def test_a_missing_arm_is_refused_and_named(
        self, clone: Clone, capsys: pytest.CaptureFixture[str]
    ) -> None:
        clone.entry(pending())
        clone.runs(arms=("0.05", "1.2"))
        self.refused(clone, capsys, "missing ['0.66']")

    def test_no_records_at_all_is_a_set_other_than_the_three(
        self, clone: Clone, capsys: pytest.CaptureFixture[str]
    ) -> None:
        clone.entry(pending())
        self.refused(clone, capsys, "needs exactly one out-of-sample record at each of")

    def test_an_arm_the_protocol_does_not_declare_is_refused(
        self, clone: Clone, capsys: pytest.CaptureFixture[str]
    ) -> None:
        clone.entry(pending())
        clone.runs()
        make_oos_run(clone.backtests, "20260101T000007000000Z-extra", arm="0.5", entry_id=ENTRY_ID)
        self.refused(clone, capsys, "not declared ['0.5']")

    def test_two_records_at_one_arm_are_refused(
        self, clone: Clone, capsys: pytest.CaptureFixture[str]
    ) -> None:
        clone.entry(pending())
        clone.runs()
        make_oos_run(clone.backtests, "20260101T000007000000Z-twice", arm="1.2", entry_id=ENTRY_ID)
        self.refused(clone, capsys, "two records at arm 1.2")

    @pytest.mark.parametrize(
        ("over", "message"),
        [
            ({"protocol_sha": "d" * 64}, "was made under protocol"),
            (
                {
                    "window": {
                        "start_date": "2024-01-01",
                        "end_date": "2026-07-01",
                        "start": "2024-01-01T00:00:00+00:00",
                        "end": "2026-07-01T00:00:00+00:00",
                    }
                },
                "covers 2024-01-01 to 2026-07-01",
            ),
        ],
    )
    def test_a_record_that_is_not_this_entrys_is_refused(
        self, clone: Clone, capsys: pytest.CaptureFixture[str], over: dict[str, Any], message: str
    ) -> None:
        clone.entry(pending())
        clone.runs(**over)
        self.refused(clone, capsys, message)

    def test_a_record_of_another_candidate_than_the_entry_binds_is_refused(
        self, clone: Clone, capsys: pytest.CaptureFixture[str]
    ) -> None:
        clone.entry(pending(digest="c" * 64))
        clone.runs()
        self.refused(clone, capsys, "has candidate digest")

    def test_an_entry_that_lists_other_arms_than_the_protocol_is_refused(
        self, clone: Clone, capsys: pytest.CaptureFixture[str]
    ) -> None:
        body = pending()
        body["arms"] = ["0.05", "0.66"]
        clone.entry(body)
        clone.runs()
        self.refused(clone, capsys, "lists arms ['0.05', '0.66']")

    def test_a_record_with_no_protocol_block_is_refused(
        self, clone: Clone, capsys: pytest.CaptureFixture[str]
    ) -> None:
        clone.entry(pending())
        clone.runs()
        make_oos_run(
            clone.backtests, "20260101T000006000000Z-bare", entry_id=ENTRY_ID, protocol=None
        )
        self.refused(clone, capsys, "carries no protocol block")

    def test_a_record_naming_an_entry_that_is_not_committed_is_refused(
        self, clone: Clone, capsys: pytest.CaptureFixture[str]
    ) -> None:
        clone.entry(pending())
        clone.runs()
        clone.runs("s6-ghost")
        self.refused(clone, capsys, "not committed: s6-ghost")

    def test_one_incomplete_entry_leaves_the_complete_one_unmarked(
        self, clone: Clone, capsys: pytest.CaptureFixture[str]
    ) -> None:
        clone.entry(pending())
        clone.entry(pending(OTHER_ID))
        clone.runs()
        clone.runs(OTHER_ID, arms=("0.05",))
        self.refused(clone, capsys, "missing")

    def test_an_unknown_entry_flag_and_a_clone_with_no_candidate_are_refused(
        self, clone: Clone, capsys: pytest.CaptureFixture[str]
    ) -> None:
        clone.entry(pending())
        clone.runs()
        self.refused(clone, capsys, "no such entry: nope", "--entry", "nope")
        baseline = pending("s5-baseline")
        baseline["kind"] = "baseline"
        clone.entry(baseline)
        for p in clone.entries.glob(f"{ENTRY_ID}.json"):
            p.unlink()
        self.refused(clone, capsys, "no candidate entry to mark")

    def test_a_missing_backtests_directory_is_refused(
        self, clone: Clone, capsys: pytest.CaptureFixture[str]
    ) -> None:
        clone.entry(pending())
        args = clone.argv()
        args[1] = str(clone.backtests.parent / "absent")
        assert tool.main(args) == tool.EXIT_REFUSED
        assert "is not a directory" in capsys.readouterr().err
