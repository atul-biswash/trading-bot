"""R-BT, S6: ``local_reads``, the clone's own memory of what it has read out of sample.

``check_run`` refuses a second read of a candidate at an arm because the caller hands it the
``(candidate_digest, arm)`` pairs this clone already holds a record of. These tests judge the scan that
builds that set: what it counts, what it skips unjudged, and what it refuses to guess about.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from tests.unit.protocol_world import PROTOCOL, effective
from trading_bot.backtesting.candidate import candidate_digest, settings_digest
from trading_bot.backtesting.protocol import ProtocolError, local_reads

OOS_WINDOW = ("2024-01-01", "2026-10-01")
IN_SAMPLE_WINDOW = ("2017-08-17", "2024-01-01")
STRADDLING_WINDOW = ("2023-06-01", "2025-01-01")


def run_record(
    eff: dict[str, Any],
    window: tuple[str, str],
    *,
    flag: bool = True,
    schema: int = 6,
) -> dict[str, Any]:
    """A record as a run writes one, by hand: schema 5 or later carries the block and its digests."""
    body: dict[str, Any] = {
        "schema": schema,
        "provenance": {"verdict": "accepted" if flag else "refused"},
        "evidence_eligible": flag,
        "window": {"start_date": window[0], "end_date": window[1]},
        "protocol": {"window_class": "out_of_sample"},
    }
    if schema >= 5:
        body["effective"] = eff
        body["candidate_digest"] = candidate_digest(eff)
        body["settings_digest"] = settings_digest(eff)
    return body


def put(runs: Path, name: str, content: object) -> Path:
    """Write ``<runs>/<name>/run.json``; text is written as given, anything else as JSON."""
    directory = runs / name
    directory.mkdir(parents=True)
    path = directory / "run.json"
    text = content if isinstance(content, str) else json.dumps(content)
    path.write_text(text, encoding="utf-8")
    return path


class TestWhatItCounts:
    def test_an_absent_or_empty_directory_holds_no_read(self, tmp_path: Path) -> None:
        assert local_reads(PROTOCOL, tmp_path / "none") == frozenset()
        (tmp_path / "runs").mkdir()
        assert local_reads(PROTOCOL, tmp_path / "runs") == frozenset()

    def test_an_out_of_sample_record_is_the_candidates_digest_and_its_arm(
        self, tmp_path: Path
    ) -> None:
        eff = effective()
        put(tmp_path, "r1", run_record(eff, OOS_WINDOW))
        assert local_reads(PROTOCOL, tmp_path) == {(candidate_digest(eff), "1.2")}

    def test_each_arm_of_one_candidate_is_its_own_read(self, tmp_path: Path) -> None:
        put(tmp_path, "r1", run_record(effective(arm="0.05"), OOS_WINDOW))
        put(tmp_path, "r2", run_record(effective(arm="0.66"), OOS_WINDOW))
        digest = candidate_digest(effective())
        assert local_reads(PROTOCOL, tmp_path) == {(digest, "0.05"), (digest, "0.66")}

    def test_two_candidates_are_two_reads(self, tmp_path: Path) -> None:
        other = effective(params={"fast_period": 10, "slow_period": 50})
        put(tmp_path, "r1", run_record(effective(), OOS_WINDOW))
        put(tmp_path, "r2", run_record(other, OOS_WINDOW))
        assert len(local_reads(PROTOCOL, tmp_path)) == 2

    def test_a_window_that_straddles_the_boundary_touched_it_and_counts(
        self, tmp_path: Path
    ) -> None:
        put(tmp_path, "r1", run_record(effective(), STRADDLING_WINDOW))
        assert len(local_reads(PROTOCOL, tmp_path)) == 1

    def test_a_directory_with_no_record_is_not_a_read(self, tmp_path: Path) -> None:
        """``-running`` and ``-failed`` directories hold no ``run.json``: the record is written last."""
        (tmp_path / "20261008T120000000000Z-running").mkdir()
        (tmp_path / "20261008T120001000000Z-failed").mkdir()
        assert local_reads(PROTOCOL, tmp_path) == frozenset()


class TestWhatItSkipsUnjudged:
    def test_an_in_sample_record_is_skipped_whether_or_not_it_is_evidence(
        self, tmp_path: Path
    ) -> None:
        put(tmp_path, "r1", run_record(effective(), IN_SAMPLE_WINDOW))
        put(tmp_path, "r2", run_record(effective(arm="0.05"), IN_SAMPLE_WINDOW, flag=False))
        put(tmp_path, "r3", run_record(effective(), IN_SAMPLE_WINDOW, schema=4))
        try:
            found = local_reads(PROTOCOL, tmp_path)
        except ProtocolError as exc:
            pytest.fail(f"an in-sample record was judged: {exc}")
        assert found == frozenset()


class TestWhatItRefusesToGuess:
    def test_an_out_of_sample_record_that_is_not_evidence_refuses_the_scan(
        self, tmp_path: Path
    ) -> None:
        put(tmp_path, "r1", run_record(effective(), OOS_WINDOW, flag=False))
        with pytest.raises(ProtocolError, match="not evidence"):
            local_reads(PROTOCOL, tmp_path)

    def test_an_out_of_sample_record_with_no_effective_block_refuses_the_scan(
        self, tmp_path: Path
    ) -> None:
        put(tmp_path, "r1", run_record(effective(), OOS_WINDOW, schema=4))
        with pytest.raises(ProtocolError, match="not evidence"):
            local_reads(PROTOCOL, tmp_path)

    def test_a_block_whose_digest_was_edited_refuses_the_scan(self, tmp_path: Path) -> None:
        body = run_record(effective(), OOS_WINDOW)
        body["candidate_digest"] = "0" * 64
        put(tmp_path, "r1", body)
        with pytest.raises(ProtocolError, match="not evidence"):
            local_reads(PROTOCOL, tmp_path)

    @pytest.mark.parametrize(
        "content",
        ["{not json", "[]", "{}", '{"window": {"start_date": "2024-01-01"}}'],
        ids=["not-json", "not-an-object", "no-window", "half-a-window"],
    )
    def test_a_record_it_cannot_place_in_time_refuses_the_scan(
        self, tmp_path: Path, content: str
    ) -> None:
        put(tmp_path, "r1", content)
        with pytest.raises(ProtocolError, match="run record"):
            local_reads(PROTOCOL, tmp_path)

    def test_a_date_that_is_not_a_date_refuses_the_scan(self, tmp_path: Path) -> None:
        put(tmp_path, "r1", run_record(effective(), ("2024-13-45", "2026-10-01")))
        with pytest.raises(ProtocolError, match="readable window"):
            local_reads(PROTOCOL, tmp_path)

    def test_one_bad_record_among_good_ones_still_refuses(self, tmp_path: Path) -> None:
        put(tmp_path, "r1", run_record(effective(), OOS_WINDOW))
        put(tmp_path, "r2", "{not json")
        with pytest.raises(ProtocolError):
            local_reads(PROTOCOL, tmp_path)
