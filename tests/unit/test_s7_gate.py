"""``scripts/s7_gate.py``: the command that judges the candidates read out of sample.

Driven through ``main(argv)`` over run directories and entries written by ``gate_world`` and the REAL
``PROTOCOL.md`` copied to ``<tmp>/research/PROTOCOL.md`` with the entries beside it, which is where the
command looks by default. The default candidate PASSES (see ``gate_world``).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

import s7_gate

from tests.unit.gate_world import ENTRY_ID, build_candidate
from tests.unit.protocol_world import PROTOCOL_TEXT


def setup(tmp_path: Path, **kwargs: Any) -> tuple[Path, Path, Path, dict[str, Any]]:
    """The protocol, an entries directory holding the candidate's entry, and the backtests directory."""
    research = tmp_path / "research"
    entries = research / "entries"
    entries.mkdir(parents=True)
    protocol = research / "PROTOCOL.md"
    protocol.write_text(PROTOCOL_TEXT, encoding="utf-8", newline="\n")
    _, backtests, body = build_candidate(tmp_path / "clone", **kwargs)
    write_entry(entries, body)
    return protocol, entries, backtests, body


def write_entry(entries: Path, body: dict[str, Any]) -> None:
    (entries / f"{body['id']}.json").write_text(
        json.dumps(body, indent=2) + "\n", encoding="ascii", newline="\n"
    )


def run(*args: str | Path) -> int:
    return s7_gate.main([str(a) for a in args])


class TestAVerdictIsAnOutcomeNotAnError:
    def test_a_passing_candidate_prints_its_figures_and_pass_and_exits_zero(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        protocol, _, backtests, _ = setup(tmp_path)
        assert run("--backtests", backtests, "--protocol", protocol) == 0
        out = capsys.readouterr()
        assert "S7 DECISION GATE" in out.out and f"CANDIDATE {ENTRY_ID}" in out.out
        assert "S7: PASS" in out.out and "S7 SUMMARY: 1 of 1 candidates read PASS" in out.out
        assert "variants declared 216" in out.out and out.err == ""
        assert all(ord(c) < 128 for c in out.out)

    def test_a_failing_candidate_also_exits_zero_and_says_fail(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        protocol, _, backtests, _ = setup(tmp_path, per_arm={"1.2": {"drawdown": "0.5"}})
        assert run("--backtests", backtests, "--protocol", protocol) == 0
        out = capsys.readouterr().out
        assert "S7: FAIL" in out and "NOT MET  maximum drawdown" in out

    def test_the_output_is_the_same_twice(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        protocol, _, backtests, _ = setup(tmp_path)
        run("--backtests", backtests, "--protocol", protocol)
        first = capsys.readouterr().out
        run("--backtests", backtests, "--protocol", protocol)
        assert capsys.readouterr().out == first


class TestARefusalPrintsNoVerdictForAnyone:
    def two_candidates(self, tmp_path: Path) -> tuple[Path, Path]:
        protocol, entries, backtests, body = setup(tmp_path)
        broken = {
            **body,
            "id": "s6-rsi-4h-on",
            "candidate_digest": "a" * 64,
            "oos": {
                "records": {
                    arm: {"run": "no-such-run", "run_json_sha256": "0" * 64}
                    for arm in ("0.05", "0.66", "1.20")
                }
            },
        }
        write_entry(entries, broken)
        return protocol, backtests

    def test_one_refused_candidate_withholds_the_verdict_of_the_good_one(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        protocol, backtests = self.two_candidates(tmp_path)
        assert run("--backtests", backtests, "--protocol", protocol) == 2
        out = capsys.readouterr()
        assert out.out == "", "no verdict, not even the good candidate's"
        assert "REFUSED: s6-rsi-4h-on: refusal 1, not evidence" in out.err

    def test_every_refusal_is_listed_not_only_the_first(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        protocol, backtests = self.two_candidates(tmp_path)
        other = json.loads(
            (protocol.parent / "entries" / "s6-rsi-4h-on.json").read_text(encoding="ascii")
        )
        other.update(id="s6-rsi-1h-on", candidate_digest="b" * 64)
        write_entry(protocol.parent / "entries", other)
        run("--backtests", backtests, "--protocol", protocol)
        err = capsys.readouterr().err
        assert err.count("REFUSED:") == 2 and "s6-rsi-1h-on" in err and "s6-rsi-4h-on" in err

    def test_a_refusal_by_a_rule_names_the_rule(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        window = {
            "start_date": "2017-08-17",
            "end_date": "2026-10-01",
            "start": "2017-08-17T00:00:00+00:00",
            "end": "2026-10-01T00:00:00+00:00",
        }
        protocol, _, backtests, _ = setup(tmp_path, per_arm={"1.2": {"window": window}})
        assert run("--backtests", backtests, "--protocol", protocol) == 2
        assert "refusal 4 (R-BW)" in capsys.readouterr().err


class TestWhichCandidatesAreJudged:
    def test_a_pending_candidate_is_listed_and_a_baseline_is_ignored(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        protocol, entries, backtests, body = setup(tmp_path)
        write_entry(
            entries,
            {
                **body,
                "id": "s6-rsi-4h-on",
                "candidate_digest": "a" * 64,
                "status": "pending",
                "oos": None,
            },
        )
        write_entry(
            entries, {**body, "id": "s5-baseline", "kind": "baseline", "candidate_digest": "b" * 64}
        )
        assert run("--backtests", backtests, "--protocol", protocol) == 0
        out = capsys.readouterr().out
        assert "candidates read 1; still pending 1" in out and "PENDING s6-rsi-4h-on" in out
        assert "s5-baseline" not in out

    def test_entry_restricts_the_judgement_to_the_named_candidates(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        protocol, entries, backtests, body = setup(tmp_path)
        write_entry(
            entries,
            {
                **body,
                "id": "s6-rsi-4h-on",
                "candidate_digest": "a" * 64,
                "status": "pending",
                "oos": None,
            },
        )
        assert run("--backtests", backtests, "--protocol", protocol, "--entry", ENTRY_ID) == 0
        out = capsys.readouterr().out
        assert "candidates read 1; still pending 0" in out and "s6-rsi-4h-on" not in out

    def test_an_entry_that_does_not_exist_is_refused(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        protocol, _, backtests, _ = setup(tmp_path)
        assert run("--backtests", backtests, "--protocol", protocol, "--entry", "nope") == 2
        assert "no such entry: nope" in capsys.readouterr().err

    def test_no_entries_at_all_is_a_report_of_nothing_not_a_verdict(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        protocol, entries, backtests, body = setup(tmp_path)
        (entries / f"{body['id']}.json").unlink()
        assert run("--backtests", backtests, "--protocol", protocol) == 0
        out = capsys.readouterr().out
        assert "candidates read 0; still pending 0" in out and "S7 SUMMARY: 0 of 0" in out


class TestTheInputsMustBeUsable:
    def test_the_entries_directory_defaults_to_the_one_beside_the_protocol(
        self, tmp_path: Path
    ) -> None:
        protocol, entries, backtests, _ = setup(tmp_path)
        assert protocol.parent / "entries" == entries
        assert run("--backtests", backtests, "--protocol", protocol) == 0

    def test_an_explicit_entries_directory_is_used(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        protocol, entries, backtests, _ = setup(tmp_path)
        moved = tmp_path / "elsewhere"
        entries.rename(moved)
        assert run("--backtests", backtests, "--protocol", protocol, "--entries-dir", moved) == 0
        assert f"CANDIDATE {ENTRY_ID}" in capsys.readouterr().out

    def test_a_missing_backtests_directory_is_refused(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        protocol, _, _, _ = setup(tmp_path)
        assert run("--backtests", tmp_path / "nope", "--protocol", protocol) == 2
        assert "is not a directory" in capsys.readouterr().err

    def test_a_protocol_that_cannot_be_read_is_refused(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        _, _, backtests, _ = setup(tmp_path)
        assert run("--backtests", backtests, "--protocol", tmp_path / "nope.md") == 2
        assert "cannot be used" in capsys.readouterr().err

    def test_a_declaration_with_no_s7_block_is_refused(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        protocol, _, backtests, _ = setup(tmp_path)
        text = PROTOCOL_TEXT
        start = text.index('  "s7": {')
        end = text.index("  },\n", start) + len("  },\n")  # the block's closing line
        protocol.write_text(text[:start] + text[end:], encoding="utf-8", newline="\n")
        assert run("--backtests", backtests, "--protocol", protocol) == 2
        assert "s7 block is absent" in capsys.readouterr().err
