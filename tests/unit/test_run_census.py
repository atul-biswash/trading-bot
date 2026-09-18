"""Tests for ``scripts/run_census.py``.

Each test states what it would fail on, because a test whose negation is not
named is one nobody can tell is abstaining. Both halves of expressiveness are
checked per test: whether the INPUT can express the defect, and whether the
ASSERTION reads the thing the defect moves.
"""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

from run_census import CaptureRefusedError, census, digest_of, main, reject_live_log

_SUBSTANTIAL = 100


def _capture(tmp_path: Path, lines: list[str]) -> Path:
    path = tmp_path / "capture.log"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def test_a_logs_path_is_refused_before_the_file_is_read(tmp_path: Path) -> None:
    """The refusal precedes every read, so a path under logs/ need not exist.

    EXPRESSIVENESS: the input is a path under ``logs/`` that is NOT created, so
    a refusal keyed on reading the file could not pass this.
    FAILS ON: deleting ``reject_live_log``; keying it on the file NAME rather
    than the directory; or moving it below the ``is_file`` check, which would
    report "is not a file" and hide that the live log was the real objection.
    """
    live = tmp_path / "logs" / "trading_bot.log"

    with pytest.raises(CaptureRefusedError, match="logs/ directory"):
        reject_live_log(live)

    assert not live.exists()


def test_a_refused_path_exits_two_and_names_the_reason(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The CLI surfaces the refusal rather than raising through it.

    EXPRESSIVENESS: the same un-created logs/ path drives the real entry point.
    FAILS ON: returning 0 on a refusal, or swallowing the message so an operator
    sees an empty run and reads it as a clean one.
    """
    live = tmp_path / "logs" / "trading_bot.log"

    code = main([str(live)])

    out = capsys.readouterr().out
    assert code == 2
    assert "REFUSED" in out
    assert "logs/" in out


def test_a_capture_outside_logs_is_accepted(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The refusal is narrow: only a logs/ DIRECTORY is refused.

    EXPRESSIVENESS: the file is named ``capture.log`` -- a ``.log`` suffix and
    the substring "log" both present -- so a refusal keyed on either would fire
    here and fail the test.
    FAILS ON: widening the refusal to match the extension or a bare substring,
    which would make the tool unable to read any capture.
    """
    capture = _capture(tmp_path, ["2026-01-01T00:00:00Z | INFO | pid=1 | m | x event=alpha"])

    code = main([str(capture)])

    assert code == 0
    assert "REFUSED" not in capsys.readouterr().out


def test_the_digest_reported_is_the_digest_of_the_file_read(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The printed digest is computed from the bytes on disk, not from a name.

    EXPRESSIVENESS: the content is arbitrary and its SHA-256 is computed in the
    test independently, so a tool printing any fixed or wrong digest fails.
    FAILS ON: printing a digest of a different file, caching one across runs, or
    dropping the field -- which would leave every figure without its instrument.
    """
    capture = _capture(tmp_path, ["pid=7 event=alpha", "pid=7 event=beta"])
    expected = hashlib.sha256(capture.read_bytes()).hexdigest()

    assert digest_of(capture) == expected

    main([str(capture)])

    assert expected in capsys.readouterr().out


def test_the_digest_accompanies_each_figure_section(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Every figure block carries the digest, not only the header.

    EXPRESSIVENESS: the input produces a pid census, a per-event block and a
    totals block, so a tool printing the digest once would be visible here.
    FAILS ON: printing the digest only in the CAPTURE header, which is the shape
    that lets a figure be copied out of the terminal without its instrument.
    """
    capture = _capture(tmp_path, ["pid=7 event=alpha"])
    expected = hashlib.sha256(capture.read_bytes()).hexdigest()

    main([str(capture)])

    out = capsys.readouterr().out
    assert out.count(expected) >= 4


def test_event_and_pid_counts_are_read_from_the_lines(tmp_path: Path) -> None:
    """The census counts what the lines carry.

    EXPRESSIVENESS: two pids with different line counts and three event records
    across two names, so a miscount in either dimension moves a number here.
    FAILS ON: a regex that stops at the first match per line, that misses a
    digit-bearing event name, or that counts pids as records rather than lines.
    """
    events, pids, first = census(
        [
            "pid=11 event=probe_x1_leg",
            "pid=11 event=probe_x1_leg",
            "pid=12 event=close_booked",
            "pid=12 no event field here",
        ]
    )

    assert events == {"probe_x1_leg": 2, "close_booked": 1}
    assert pids == {"11": 2, "12": 2}
    assert first is not None
    assert first.startswith("pid=11")


def test_a_capture_with_no_pid_field_reports_none_rather_than_crashing(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The pre-``pid=`` era of the log is representable.

    EXPRESSIVENESS: the input carries no ``pid=`` at all, which is the real
    shape of this project's oldest records.
    FAILS ON: unpacking or indexing a first-line that is ``None``, which would
    raise rather than report the absence.
    """
    capture = _capture(tmp_path, ["2026-01-01 | INFO | no pid here event=alpha"])

    code = main([str(capture)])

    out = capsys.readouterr().out
    assert code == 0
    assert "NONE" in out


def test_substantial_is_a_hundred_lines_and_the_boundary_is_inclusive(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """``RUN_LEDGER`` section 5 defines substantial as 100 or more lines.

    EXPRESSIVENESS: one pid sits exactly ON the boundary at 100 and the other
    one BELOW it at 99, so an off-by-one moves the count and a different
    threshold moves it further.
    FAILS ON: ``> 100`` instead of ``>= 100``, or any threshold that is not 100.
    """
    lines = [f"pid=100 line {n}" for n in range(_SUBSTANTIAL)]
    lines += [f"pid=99 line {n}" for n in range(_SUBSTANTIAL - 1)]
    capture = _capture(tmp_path, lines)

    main([str(capture)])

    out = capsys.readouterr().out
    assert "substantial runs  : 1" in out


def test_a_directory_is_refused_rather_than_read(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A path that is not a file refuses with the same exit code.

    EXPRESSIVENESS: a real directory outside logs/, so the logs/ refusal cannot
    be what fires.
    FAILS ON: letting ``read_bytes`` raise an unhandled ``IsADirectoryError``.
    """
    code = main([str(tmp_path)])

    assert code == 2
    assert "not a file" in capsys.readouterr().out
