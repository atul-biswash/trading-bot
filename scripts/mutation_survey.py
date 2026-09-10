#!/usr/bin/env python
"""Run a mutation survey from a spec file, and prove which mutation ran.

``CLAUDE.md`` requires three things of a mutation proof and this exists because
the first of them was the one repeatedly got wrong::

    A mutation proof asserts the mutated CONTENT, not merely that content
    changed. Verifying by checksum proves that **a** mutation applied; it does
    not prove that **the** mutation applied.

**THE DEFECT THIS CLOSES, MEASURED.** M5h's C3 survey ran six mutations through
a scratchpad harness whose region print RE-SEARCHED the mutated file for a
needle derived from the replacement text. For a deletion the needle was gone, so
a hardcoded fallback list picked an unrelated line. For one replacement the
needle was a bare ``)`` and it matched the closing paren of an **import block**
at line 152 -- 1200 lines from the mutation, printed with no warning, looking
exactly like a correct region print. Three of that survey's six mutations were
therefore established by anchor-uniqueness and a deterministic replace ALONE,
with the content print contributing nothing. That gap was declared as
``M5h-289``; this script is what closes it.

**THE FIX IS TO STOP SEARCHING.** ``bytes.index`` already returns the offset of
the match, so the location is known before the file is written and needs no
recovery afterwards. Every print here is derived from that offset:

* the exact bytes removed, and the exact bytes written in their place, as
  ``repr`` so whitespace and newlines are visible;
* the byte offset and the line number it falls on, computed from the offset
  rather than looked up;
* the region as it stands AFTER the mutation, centred on that same line.

A deletion is printed exactly as informatively as a replacement, which matters
because deletions are the majority of every survey this project has run.

**A CRASH IS AN ABSTENTION, NEVER A KILL.** ``CLAUDE.md``: *"Confirm the test
that fails is the one meant to, and that it reports the wrong value -- a wrong
stage, not an ``AttributeError`` or a collection error. A crash means the
mutation broke something else on the way and the assertion was never reached;
that is not coverage."* A pytest run reporting ``ERROR`` lines, or exiting with
a status that is neither 0 nor 1, is reported as ABSTAINED and its failure count
is not counted as a kill.

**RESTORE IS A BYTE COPY, VERIFIED BY MD5, IN A ``finally``.** Never
``read_text``/``write_text``: that round-trips newlines and produces a byte
mismatch against this LF-pinned tree -- content-identical, checksum-different,
and indistinguishable from real corruption until diffed.

Usage::

    python scripts/mutation_survey.py <spec.json>
    python scripts/mutation_survey.py <spec.json> --dry-run

``--dry-run`` applies and prints each mutation, then restores, WITHOUT running
the suite. Use it to check anchors and prints before spending the runtime; it
reports no kills and must not be read as a survey result.

Spec format -- JSON, with ``anchor`` and ``replacement`` as ordinary strings
(encoded UTF-8 here; ``\\n`` in JSON is a real newline)::

    {
      "target": "src/trading_bot/engine/modes.py",
      "mutations": [
        {
          "id": "M1",
          "name": "drop trades_count from _restore_ledger",
          "anchor": "        trades_count=state.ledger.trades_count,\\n",
          "replacement": ""
        }
      ]
    }

``target`` and the spec path are resolved against the repository root, which is
this file's parent's parent. The suite is run from that root with the same
interpreter that runs this script, so it inherits the checkout's venv.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

#: Lines of context printed either side of the mutated line.
CONTEXT = 6

#: pytest exit statuses that represent a completed run whose verdict can be
#: read. 0 is all-passed, 1 is tests-failed. Everything else -- interrupted,
#: internal error, usage error, nothing collected -- means no verdict.
_READABLE_EXITS = frozenset({0, 1})


@dataclass(frozen=True)
class Mutation:
    """One experiment: what to replace, with what, and what to call it."""

    id: str
    name: str
    anchor: bytes
    replacement: bytes

    @property
    def is_deletion(self) -> bool:
        return not self.replacement


@dataclass(frozen=True)
class Result:
    """What one mutation produced. ``abstained`` outranks the failure count."""

    id: str
    name: str
    failed: tuple[str, ...]
    errored: tuple[str, ...]
    exit_code: int
    abstained: bool
    abstain_cause: str


def md5(path: Path) -> str:
    return hashlib.md5(path.read_bytes()).hexdigest()


def line_of(data: bytes, offset: int) -> int:
    """The 1-based line number ``offset`` falls on.

    Computed FROM THE OFFSET the match reported -- never by searching the file
    for the anchor's text, which is the defect this script exists to close.
    """
    return data.count(b"\n", 0, offset) + 1


def show_bytes(label: str, raw: bytes) -> None:
    """Print bytes as repr, one source line per output line.

    ``repr`` rather than the decoded text: trailing whitespace and the presence
    or absence of a final newline are exactly what a reader needs to see, and
    both are invisible when printed plainly.

    **``splitlines(keepends=True)``, and the alternative was caught shipping.**
    A first version split on ``"\\n"`` and re-appended one to every part, which
    printed a trailing newline on an anchor that ends mid-line -- displaying a
    byte that is not there, in the one function whose whole job is to report
    the bytes faithfully. Keeping the ends means each line is shown exactly as
    it is, and a final part with no newline is visibly missing one.
    """
    if not raw:
        print(f"    {label}: <empty>")
        return
    print(f"    {label}: {len(raw)} bytes")
    for part in raw.decode("utf-8").splitlines(keepends=True):
        print(f"      {part!r}")


def print_region(data: bytes, line_no: int, marker: str) -> None:
    """Print the file around ``line_no``, marking it."""
    lines = data.decode("utf-8").splitlines()
    lo = max(0, line_no - 1 - CONTEXT)
    hi = min(len(lines), line_no - 1 + CONTEXT + 1)
    for n in range(lo, hi):
        flag = marker if n == line_no - 1 else "  "
        print(f"    {flag} {n + 1:5d} {lines[n]}")


def load_spec(path: Path) -> tuple[Path, list[Mutation]]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    target = ROOT / str(raw["target"])
    mutations = [
        Mutation(
            id=str(entry["id"]),
            name=str(entry["name"]),
            anchor=str(entry["anchor"]).encode("utf-8"),
            replacement=str(entry.get("replacement", "")).encode("utf-8"),
        )
        for entry in raw["mutations"]
    ]
    return target, mutations


def run_suite() -> tuple[int, tuple[str, ...], tuple[str, ...]]:
    """Run pytest from the repo root; return exit code, FAILED and ERROR ids.

    Output is CAPTURED, never piped through a filter: a pipeline's exit status
    is the LAST stage's, and the status is what decides whether this run
    produced a verdict at all. Capturing keeps both.
    """
    proc = subprocess.run(
        [sys.executable, "-m", "pytest"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    body = proc.stdout.splitlines()
    failed = tuple(x.split(" ", 1)[1].strip() for x in body if x.startswith("FAILED "))
    errored = tuple(x.split(" ", 1)[1].strip() for x in body if x.startswith("ERROR "))
    return proc.returncode, failed, errored


def apply_and_report(target: Path, mutation: Mutation, *, dry_run: bool) -> Result | None:
    """Apply one mutation, print it exactly, and run the suite.

    Returns ``None`` when the anchor did not match exactly once -- in which case
    nothing was written -- and under ``--dry-run``, which produces no verdict.

    **THE CALLER RESTORES, NOT THIS FUNCTION**, so that a restore happens even
    on a path that raises here. See ``main``'s inner ``finally``.
    """
    print(f"\n{'=' * 74}")
    kind = "DELETION" if mutation.is_deletion else "REPLACEMENT"
    print(f"{mutation.id}: {mutation.name}   [{kind}]")
    print(f"{'=' * 74}")

    data = target.read_bytes()
    count = data.count(mutation.anchor)
    print(f"  anchor matches: {count}")
    if count != 1:
        print("  REFUSED: an anchor must match exactly once. Nothing written.")
        print("  A re-anchored mutation is a NEW mutation; its failure set must")
        print("  be re-derived rather than carried across.")
        return None

    offset = data.index(mutation.anchor)
    line_no = line_of(data, offset)
    print(f"  offset        : {offset} (byte), line {line_no}")
    show_bytes("REMOVED ", mutation.anchor)
    show_bytes("WRITTEN ", mutation.replacement)

    target.write_bytes(data[:offset] + mutation.replacement + data[offset + len(mutation.anchor) :])

    mutated = target.read_bytes()
    print(f"  mutated md5   : {md5(target)}")
    print(f"  --- region AFTER mutation, at line {line_no} ---")
    print_region(mutated, line_no, ">>")

    if dry_run:
        print("  (--dry-run: the suite was not run; this is not a survey result)")
        return None

    exit_code, failed, errored = run_suite()
    abstained = bool(errored) or exit_code not in _READABLE_EXITS
    cause = ""
    if errored:
        cause = f"{len(errored)} pytest ERROR(s) -- the suite could not run the assertions"
    elif exit_code not in _READABLE_EXITS:
        cause = f"pytest exited {exit_code}, which is neither all-passed nor tests-failed"

    if abstained:
        print(f"  --- ABSTAINED: {cause}")
        print("      A crash proves nothing: the mutation broke something on the")
        print("      way and the intended assertion was never reached.")
        for line in errored:
            print(f"      ERROR  {line}")
    else:
        print(f"  --- {len(failed)} KILLED ---")
        for line in failed:
            print(f"      FAILED {line}")
    return Result(
        id=mutation.id,
        name=mutation.name,
        failed=failed,
        errored=errored,
        exit_code=exit_code,
        abstained=abstained,
        abstain_cause=cause,
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument("spec", type=Path, help="path to the JSON mutation spec")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="apply, print and restore each mutation WITHOUT running the suite",
    )
    args = parser.parse_args()

    spec_path = args.spec if args.spec.is_absolute() else ROOT / args.spec
    target, mutations = load_spec(spec_path)
    if not target.exists():
        print(f"REFUSED: target {target} does not exist")
        return 2

    baseline = md5(target)
    backup = target.with_suffix(target.suffix + ".mutation-backup")
    print(f"target        : {target.relative_to(ROOT).as_posix()}")
    print(f"baseline md5  : {baseline}")
    print(f"mutations     : {len(mutations)}")

    shutil.copy2(target, backup)
    if md5(backup) != baseline:
        print("REFUSED: the byte copy does not match the original")
        backup.unlink(missing_ok=True)
        return 2

    results: list[Result] = []
    # Set only by a failed restore. A `return` from inside the `finally` below
    # would silence any exception in flight (ruff B012), and a restore failure
    # is exactly the moment a real exception is most likely to be travelling.
    dirty = False
    try:
        for mutation in mutations:
            try:
                result = apply_and_report(target, mutation, dry_run=args.dry_run)
                if result is not None:
                    results.append(result)
            finally:
                shutil.copy2(backup, target)
                restored = md5(target)
                print(f"  original md5  : {baseline}")
                print(f"  restored md5  : {restored}")
                if restored == baseline:
                    print("  restore verified by md5")
                else:
                    print("  FAILED TO RESTORE -- THE TREE IS DIRTY. Stopping.")
                    dirty = True
            if dirty:
                break
    finally:
        backup.unlink(missing_ok=True)

    if dirty:
        return 2

    if results:
        print(f"\n{'=' * 74}\nSUMMARY\n{'=' * 74}")
        for result in results:
            if result.abstained:
                print(f"  {result.id}: ABSTAINED -- {result.abstain_cause}")
            else:
                names = [f.split("::")[-1] for f in result.failed]
                print(f"  {result.id}: {len(result.failed)} killed -- {names}")
    return 0


if __name__ == "__main__":  # pragma: no cover - CLI entry point
    raise SystemExit(main())
