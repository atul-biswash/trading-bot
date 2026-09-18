#!/usr/bin/env python
"""Mechanise the run census that ``docs/RUN_LEDGER.md`` prints by hand.

**IT READS A CAPTURE, AND IT REFUSES TO READ THE LIVE LOG.** A path resolving
under a ``logs/`` directory is rejected before a byte is read, and there is no
default argument at all -- the capture is always named explicitly. Reading
``logs/trading_bot.log`` is the one mistake this tool exists to prevent: the
bot appends to it while it runs, so two invocations a second apart measure two
different files, and a figure derived from it is attached to nothing a later
reader can reproduce. Every existing tool in ``scripts/`` that takes input takes
it through ``argparse``; this follows that convention rather than inventing one.

**EVERY FIGURE CARRIES THE DIGEST OF THE FILE IT CAME FROM.** ``RUN_LEDGER.md``
section 2 states a SHA-256 and says a reader holding a different digest holds a
different file; this prints that digest beside the numbers so the pairing
survives being copied out of the terminal. A census without its digest is a
number whose instrument is unstated.

**THE METRIC SET IS THE LEDGER'S, NOT A NEW ONE.** Four tables there are
mechanised here and nothing else is invented: the capture identity of section 2
(bytes, lines, digest), the pid census of sections 3 and 9 (distinct pids, and
the first line carrying the field), the per-event totals of section 6, and the
per-pid line counts of section 5. "Substantial" means 100 or more log lines,
which is section 5's own definition and separates a working session from a boot
that exited within seconds.
"""

from __future__ import annotations

import argparse
import hashlib
import re
from collections import Counter
from pathlib import Path

_EVENT_PATTERN = re.compile(r"event=([a-z0-9_]+)")
_PID_PATTERN = re.compile(r"pid=(\d+)")
_SUBSTANTIAL_LINES = 100
_READ_CHUNK = 1 << 20


class CaptureRefusedError(Exception):
    """Raised when the requested path is the live log rather than a capture."""


def reject_live_log(path: Path) -> None:
    """Refuse a path lying under a ``logs/`` directory.

    Keyed on the resolved path's parts rather than on the file name, so
    ``logs/trading_bot.log``, ``logs/archive/trading_bot.log`` and an absolute
    form of either are all refused, while a capture whose name happens to
    contain "logs" is not.
    """
    if any(part == "logs" for part in path.resolve().parts):
        raise CaptureRefusedError(
            f"{path} lies under a logs/ directory and is refused: this tool reads a frozen "
            "capture, never the live log a running bot appends to. Copy the file out by a "
            "share-mode read first, then name the copy."
        )


def digest_of(path: Path) -> str:
    """Return the SHA-256 of ``path``, read in chunks."""
    sha = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(_READ_CHUNK):
            sha.update(chunk)
    return sha.hexdigest()


def census(lines: list[str]) -> tuple[Counter[str], Counter[str], str | None]:
    """Return per-event counts, per-pid line counts, and the first pid line."""
    events: Counter[str] = Counter()
    pids: Counter[str] = Counter()
    first_pid_line: str | None = None
    for line in lines:
        event = _EVENT_PATTERN.search(line)
        if event is not None:
            events[event.group(1)] += 1
        pid = _PID_PATTERN.search(line)
        if pid is not None:
            pids[pid.group(1)] += 1
            if first_pid_line is None:
                first_pid_line = line.rstrip("\n")
    return events, pids, first_pid_line


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="run_census.py",
        description="Census a frozen capture of the bot's log. Never reads the live log.",
    )
    parser.add_argument(
        "capture",
        type=Path,
        help="path to a frozen capture; a path under logs/ is refused",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    capture: Path = args.capture

    try:
        reject_live_log(capture)
    except CaptureRefusedError as exc:
        print(f"REFUSED: {exc}")
        return 2

    if not capture.is_file():
        print(f"REFUSED: {capture} is not a file")
        return 2

    raw = capture.read_bytes()
    lines = capture.read_text(encoding="utf-8", errors="replace").splitlines()
    sha = digest_of(capture)
    events, pids, first_pid_line = census(lines)
    substantial = [pid for pid, count in pids.items() if count >= _SUBSTANTIAL_LINES]

    print(f"{'=' * 74}\nCAPTURE\n{'=' * 74}")
    print(f"  path   : {capture}")
    print(f"  bytes  : {len(raw)}")
    print(f"  lines  : {len(lines)}")
    print(f"  sha256 : {sha}")

    print(f"\n{'=' * 74}\nPID CENSUS  [sha256 {sha}]\n{'=' * 74}")
    print(f"  distinct pids          : {len(pids)}")
    print(f"  substantial (>= {_SUBSTANTIAL_LINES} lines): {len(substantial)}")
    if first_pid_line is None:
        print("  first line carrying pid= : NONE -- no record in this capture carries the field")
    else:
        print(f"  first line carrying pid= : {first_pid_line[:110]}")

    print(f"\n{'=' * 74}\nPER-PID LINE COUNTS  [sha256 {sha}]\n{'=' * 74}")
    for pid, count in sorted(pids.items(), key=lambda item: (-item[1], item[0])):
        mark = "substantial" if count >= _SUBSTANTIAL_LINES else ""
        print(f"  pid={pid:<8} lines={count:<7} {mark}")

    print(f"\n{'=' * 74}\nPER-EVENT TOTALS  [sha256 {sha}]\n{'=' * 74}")
    if not events:
        print("  none -- no record in this capture carries an event= field")
    for event, count in sorted(events.items(), key=lambda item: (-item[1], item[0])):
        print(f"  {count:<7} {event}")

    print(f"\n{'=' * 74}\nTOTALS  [sha256 {sha}]\n{'=' * 74}")
    print(f"  distinct events   : {len(events)}")
    print(f"  event records     : {sum(events.values())}")
    print(f"  distinct pids     : {len(pids)}")
    print(f"  substantial runs  : {len(substantial)}")
    return 0


if __name__ == "__main__":  # pragma: no cover - CLI entry point
    raise SystemExit(main())
