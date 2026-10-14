"""``scripts/s6_select.py``: the command that turns an in-sample sweep into one candidate per cell.

The command is driven through ``main(argv)`` as an operator drives it, over run directories written the way
the engine writes them (``selection_world.make_run``) and the REAL ``PROTOCOL.md``. Two kinds of sweep:

* a HEAVY sweep, built once: all 216 variants, each with 400 trades on a quote of 1,000 (300 wins of +20 and
  100 losses of -10, a return profit factor of 6), except variant 3 (fast 20, slow 50), which has 50 losses
  (a return profit factor of 12) and so is the first cell's one candidate;
* a LIGHT sweep: all 216 variants with two trades each, which is a complete ledger in which no point is
  eligible (two trades are under 250), for the refusals and the listings.
"""

from __future__ import annotations

import hashlib
import json
import sys
from datetime import timedelta
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

import s6_select

from tests.unit.protocol_world import PROTOCOL, REPO
from tests.unit.selection_world import at, make_run
from trading_bot.backtesting.protocol import PROTOCOL_PATH, load_entries

PROTOCOL_FILE = REPO / PROTOCOL_PATH
BEST_INDEX = 3


def rows_for(wins: int, losses: int) -> list[tuple[str, str, str]]:
    """``wins`` wins of +20 then ``losses`` losses of -10, hourly from 2018-01-01, alternating pairs."""
    start = at("2018-01-01T00:00:00")
    out = []
    for index in range(wins + losses):
        symbol = "BTCUSDT" if index % 2 == 0 else "ETHUSDT"
        out.append(
            (symbol, (start + timedelta(hours=index)).isoformat(), "20" if index < wins else "-10")
        )
    return out


def build_sweep(
    root: Path, *, heavy: bool, skip: tuple[int, ...] = (), flag_false: tuple[int, ...] = ()
) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    for index, variant in enumerate(PROTOCOL.variants()):
        if index in skip:
            continue
        if heavy:
            rows = rows_for(300, 50 if index == BEST_INDEX else 100)
            make_run(root, f"20260101T{index:06d}000000Z-{index:012d}", variant=variant, rows=rows)
        else:
            make_run(
                root,
                f"20260101T{index:06d}000000Z-{index:012d}",
                variant=variant,
                flag=index not in flag_false,
            )
    return root


@pytest.fixture(scope="module")
def heavy(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return build_sweep(tmp_path_factory.mktemp("heavy") / "backtests", heavy=True)


@pytest.fixture
def light(tmp_path: Path) -> Path:
    return build_sweep(tmp_path / "backtests", heavy=False)


def run(*args: str | Path) -> int:
    return s6_select.main([str(a) for a in args])


class TestAReportAndNothingWritten:
    def test_without_out_it_prints_the_report_and_writes_nothing(
        self, heavy: Path, capsys: pytest.CaptureFixture[str], tmp_path: Path
    ) -> None:
        before = sorted(p.name for p in heavy.iterdir())
        assert run("--backtests", heavy, "--protocol", PROTOCOL_FILE) == 0
        out = capsys.readouterr().out
        assert "S6 SELECTION" in out and "no out-of-sample record is read" in out
        assert "CELL sma_crossover 1h filter off: 9 of 9 points eligible" in out
        assert "CANDIDATE sma_crossover 1h filter off (fast_period=20, slow_period=50)" in out
        assert "a report, not a gate" in out and "cells with a candidate 12 of 12" in out
        assert sorted(p.name for p in heavy.iterdir()) == before
        assert list(tmp_path.iterdir()) == []

    def test_the_report_is_ascii(self, heavy: Path, capsys: pytest.CaptureFixture[str]) -> None:
        run("--backtests", heavy, "--protocol", PROTOCOL_FILE)
        assert all(ord(c) < 128 for c in capsys.readouterr().out)


class TestTheSelectionFile:
    def test_it_is_written_with_its_digest_printed_and_holds_the_choice(
        self, heavy: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        target = tmp_path / "selection.json"
        assert run("--backtests", heavy, "--protocol", PROTOCOL_FILE, "--out", target) == 0
        data = target.read_bytes()
        printed = capsys.readouterr().out
        digest = hashlib.sha256(data).hexdigest()
        assert f"selection file {target} sha256 {digest} ({len(data)} bytes)" in printed
        assert data.endswith(b"}\n") and b"\r" not in data and all(b < 128 for b in data)
        loaded = json.loads(data)
        assert (loaded["variants_declared"], loaded["variants_with_a_run"]) == (216, 216)
        assert loaded["cells_with_a_candidate"] == 12 and len(loaded["cells"]) == 12
        assert loaded["cells"][0]["candidate"]["variant"]["params"] == {
            "fast_period": "20",
            "slow_period": "50",
        }
        assert loaded["cells"][0]["candidate"]["return_profit_factor"] == "12"
        assert loaded["protocol_sha256"] == PROTOCOL.sha256

    def test_two_runs_of_the_command_write_identical_bytes(
        self, heavy: Path, tmp_path: Path
    ) -> None:
        run("--backtests", heavy, "--protocol", PROTOCOL_FILE, "--out", tmp_path / "a.json")
        run("--backtests", heavy, "--protocol", PROTOCOL_FILE, "--out", tmp_path / "b.json")
        assert (tmp_path / "a.json").read_bytes() == (tmp_path / "b.json").read_bytes()

    def test_it_will_not_overwrite_an_existing_selection_file(
        self, heavy: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        target = tmp_path / "selection.json"
        target.write_bytes(b"made earlier\n")
        entries = tmp_path / "entries"
        code = run(
            "--backtests",
            heavy,
            "--protocol",
            PROTOCOL_FILE,
            "--out",
            target,
            "--entries-dir",
            entries,
        )
        assert code == 2 and "will not overwrite" in capsys.readouterr().err
        assert target.read_bytes() == b"made earlier\n" and not entries.exists()


class TestTheEntries:
    def test_one_pending_entry_per_candidate_bound_by_the_runs_digest(
        self, heavy: Path, tmp_path: Path
    ) -> None:
        target, entries = tmp_path / "selection.json", tmp_path / "entries"
        code = run(
            "--backtests",
            heavy,
            "--protocol",
            PROTOCOL_FILE,
            "--out",
            target,
            "--entries-dir",
            entries,
        )
        assert code == 0
        loaded = load_entries(entries)
        assert len(loaded) == 12 and all(e.status == "pending" and e.oos is None for e in loaded)
        assert all(
            e.kind == "candidate" and sorted(e.arms) == sorted(PROTOCOL.arms) for e in loaded
        )
        digest = hashlib.sha256(target.read_bytes()).hexdigest()
        first = json.loads((entries / "s6-sma_crossover-1h-off.json").read_text(encoding="ascii"))
        assert first["selection"]["selection_file_sha256"] == digest
        best = json.loads(
            (heavy / f"20260101T{BEST_INDEX:06d}000000Z-{BEST_INDEX:012d}" / "run.json").read_text()
        )
        assert first["candidate_digest"] == best["candidate_digest"]
        assert (
            first["selection"]["in_sample_run"]
            == f"20260101T{BEST_INDEX:06d}000000Z-{BEST_INDEX:012d}"
        )

    def test_one_existing_entry_stops_everything_before_a_byte_is_written(
        self, heavy: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        entries = tmp_path / "entries"
        entries.mkdir()
        (entries / "s6-rsi-4h-on.json").write_bytes(b"mine\n")
        code = run(
            "--backtests",
            heavy,
            "--protocol",
            PROTOCOL_FILE,
            "--out",
            tmp_path / "s.json",
            "--entries-dir",
            entries,
        )
        assert code == 2 and "will not overwrite" in capsys.readouterr().err
        assert not (tmp_path / "s.json").exists()
        assert [p.name for p in entries.iterdir()] == ["s6-rsi-4h-on.json"]
        assert (entries / "s6-rsi-4h-on.json").read_bytes() == b"mine\n"

    def test_entries_without_out_are_refused(
        self, heavy: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        code = run(
            "--backtests", heavy, "--protocol", PROTOCOL_FILE, "--entries-dir", tmp_path / "e"
        )
        assert code == 2 and "--entries-dir needs --out" in capsys.readouterr().err
        assert not (tmp_path / "e").exists()


class TestAnIncompleteSweepIsNotSelectedOver:
    def test_a_missing_variant_is_refused_and_named_and_nothing_is_written(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        sweep = build_sweep(tmp_path / "backtests", heavy=False, skip=(10,))
        target = tmp_path / "s.json"
        assert run("--backtests", sweep, "--protocol", PROTOCOL_FILE, "--out", target) == 2
        err = capsys.readouterr().err
        assert (
            "REFUSED" in err
            and "1 of 216 declared variants have no run" in err
            and "MISSING" in err
        )
        assert not target.exists()

    def test_a_record_that_is_not_evidence_leaves_its_variant_missing_and_is_listed(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        sweep = build_sweep(tmp_path / "backtests", heavy=False, flag_false=(7,))
        assert run("--backtests", sweep, "--protocol", PROTOCOL_FILE) == 2
        err = capsys.readouterr().err
        assert "1 of 216 declared variants have no run" in err
        assert "SKIPPED 20260101T000007000000Z-000000000007: not_evidence" in err

    def test_two_runs_of_a_variant_that_disagree_are_refused(
        self, light: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        make_run(light, "zz-again", variant=next(iter(PROTOCOL.variants())), log="f" * 64)
        assert run("--backtests", light, "--protocol", PROTOCOL_FILE) == 2
        assert "disagree on the trade log" in capsys.readouterr().err

    def test_a_missing_backtests_directory_is_refused(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        assert run("--backtests", tmp_path / "nope", "--protocol", PROTOCOL_FILE) == 2
        assert "is not a directory" in capsys.readouterr().err


class TestWhatIsListedAndDoesNotBlock:
    def test_a_failed_directory_an_information_arm_and_an_out_of_sample_run_are_listed(
        self, light: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        (light / "20261014T154834857585Z-failed").mkdir()
        make_run(light, "info-arm", variant=next(iter(PROTOCOL.variants())), arm="0.66")
        make_run(
            light,
            "oos",
            variant=next(iter(PROTOCOL.variants())),
            protocol={"window_class": "out_of_sample"},
        )
        (light / "notes.txt").write_text("not a run\n", encoding="utf-8")
        target = tmp_path / "s.json"
        assert run("--backtests", light, "--protocol", PROTOCOL_FILE, "--out", target) == 0
        out = capsys.readouterr().out
        assert "SKIPPED 20261014T154834857585Z-failed: not_evidence" in out
        assert "SKIPPED info-arm: other_arm" in out and "SKIPPED oos: not_in_sample" in out
        assert "notes.txt" not in out
        skipped = {s["run"]: s["reason"] for s in json.loads(target.read_bytes())["skipped"]}
        assert skipped == {
            "20261014T154834857585Z-failed": "not_evidence",
            "info-arm": "other_arm",
            "oos": "not_in_sample",
        }

    def test_a_sweep_in_which_nothing_is_eligible_writes_a_file_with_no_candidate_and_no_entry(
        self, light: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        entries = tmp_path / "entries"
        code = run(
            "--backtests",
            light,
            "--protocol",
            PROTOCOL_FILE,
            "--out",
            tmp_path / "s.json",
            "--entries-dir",
            entries,
        )
        assert code == 0
        assert "cells with a candidate 0 of 12" in capsys.readouterr().out
        assert json.loads((tmp_path / "s.json").read_bytes())["cells_with_a_candidate"] == 0
        assert list(entries.iterdir()) == []

    def test_a_variant_run_twice_with_the_same_trade_log_is_listed_as_a_duplicate(
        self, light: Path, tmp_path: Path
    ) -> None:
        make_run(light, "00-again", variant=next(iter(PROTOCOL.variants())))
        assert (
            run("--backtests", light, "--protocol", PROTOCOL_FILE, "--out", tmp_path / "s.json")
            == 0
        )
        duplicates = json.loads((tmp_path / "s.json").read_bytes())["duplicates"]
        assert len(duplicates) == 1
        assert duplicates[0]["runs"] == ["00-again", "20260101T000000000000Z-000000000000"]


class TestTheProtocolMustBeUsable:
    def test_a_protocol_file_that_is_missing_is_refused(
        self, light: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        assert run("--backtests", light, "--protocol", tmp_path / "nope.md") == 2
        assert "the protocol cannot be used" in capsys.readouterr().err

    def test_a_declaration_with_no_selection_block_is_refused(
        self, light: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        text = PROTOCOL_FILE.read_text(encoding="utf-8")
        start = text.index('  "selection": {')
        stop = text.index('  "s7": {')
        broken = tmp_path / "PROTOCOL.md"
        broken.write_text(text[:start] + text[stop:], encoding="utf-8", newline="\n")
        assert run("--backtests", light, "--protocol", broken) == 2
        assert "selection block is absent" in capsys.readouterr().err


def test_the_module_sweep_fixture_is_not_modified_by_any_test(heavy: Path) -> None:
    """The heavy sweep is shared; every command above only reads it."""
    assert len(list(heavy.iterdir())) == 216
    assert all((p / "run.json").is_file() and (p / "trades.csv").is_file() for p in heavy.iterdir())
