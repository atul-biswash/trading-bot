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

**AND SOURCE THAT WILL NOT PARSE IS NEITHER -- IT ABORTS THE RUN.** The
mutated file is ``compile``d before pytest is dispatched, and a ``SyntaxError``
raises :exc:`HarnessAnchorError`. A mutation is a claim about BEHAVIOUR, and
unparseable source expresses none, so there is nothing to score: it is not a
kill, not an abstention, and not a row in the summary. This is a NARROWING of
the paragraph above rather than an exception to it -- a crash at RUNTIME is
still an abstention, because the mutation was at least valid Python. MEASURED,
``M5i-086``: before this check such a mutation reached pytest, failed at
collection, and classified ABSTAINED, which reads as *"the mutation applied and
nothing noticed"* and is a coverage gap that does not exist. ``CLAUDE.md`` names
a false abstention as the expensive direction.

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


class HarnessAnchorError(Exception):
    """The mutated source does not parse, so the anchor was wrong.

    **THIS IS A HARNESS FAULT, NOT A RESULT, AND THE DISTINCTION IS THE WHOLE
    POINT.** A mutation is a claim about BEHAVIOUR; source that will not compile
    expresses no behaviour at all, so the experiment did not happen. It is not a
    kill, not an abstention, and not a scored row -- it aborts the run.

    **WHY NOT AN ABSTENTION, WHICH IS WHERE IT USED TO LAND.** Before this,
    unparseable source reached ``run_suite``, pytest failed at collection, and
    the ``ERROR`` lines classified the row ABSTAINED. That reads as *"the
    mutation applied and no test noticed"* -- a coverage gap that does not
    exist. ``CLAUDE.md`` names that direction as the expensive one: *"a false
    ABSTENTION reports tests as BLIND WHEN THEY BIT ... a false abstention is
    filed as coverage that does not exist and nobody revisits a green test."*

    MEASURED, ``M5i-086``: M9 of the ``bookability`` survey anchored on an
    f-string's SOURCE text -- the ``f"`` prefix and the closing quote included
    -- so the replacement left bare tokens. mypy reported *"Invalid syntax.
    Perhaps you forgot a comma?"* and pytest exited 2 at collection. Re-run with
    the anchor on the string CONTENT, that mutation killed exactly the one test
    predicted. An anchor that is one quote character wrong is not an unusual
    mistake; it is the ordinary one.

    **AND THE REGION PRINT CANNOT CATCH IT.** That print is this harness's
    proof that the right mutation ran, and it is honest -- but it shows the
    bytes removed and written, not whether what remains parses. A rewording
    mutation prints a perfectly convincing region and still leaves a syntax
    error two characters away. Only the compiler knows.
    """


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

    **PARSED FROM THE SHORT SUMMARY SECTION ONLY, AND ``ERROR`` IS WHY.** A
    first version scanned the whole of stdout for lines beginning ``FAILED ``
    or ``ERROR ``. ``ERROR`` is AMBIGUOUS in pytest output: it prefixes a
    collection error in the short summary, and it is also the LEVEL PREFIX on
    every captured-log line a failing test emits. MEASURED against this tree --
    the boot path calls ``_log.error("%s is BLOCKED: ...")``, so four
    mutations that killed tests correctly were reported as ABSTAINED on the
    strength of the log lines their own failures printed, and the real
    ``FAILED`` list was computed and discarded. A survey that turns kills into
    abstentions is worse than no survey: it reports the tests as blind when
    they bit.

    Two guards, because either alone still admits a mistake. The scan starts
    after the ``short test summary info`` banner, which is the one section
    whose lines are all verdicts. And an id must contain ``::``, which every
    pytest node id does and no log line does.

    **THE DECODE IS PINNED TO UTF-8 WITH ``errors="replace"``, AND BOTH HALVES
    ARE LOAD-BEARING.** ``text=True`` alone decodes with the locale encoding,
    which on this machine is ``cp1252``. MEASURED: a mutation that fails enough
    tests for pytest to echo captured bytes outside that codepage killed the
    reader thread with ``UnicodeDecodeError``, leaving ``proc.stdout`` as
    ``None`` and the harness raising ``AttributeError`` on the next line.

    **The failure mode is what makes this worth pinning rather than patching.**
    The crash lands AFTER the mutation has been applied and the suite has run,
    so the run is wasted -- and a crash is an ABSTENTION, never a kill, so a
    mutation that bit hardest is the one most likely to destroy its own
    evidence. The restore is unaffected: it runs in a ``finally`` and its md5
    was verified on the crashing run.

    ``errors="replace"`` rather than ``strict`` because this function reads only
    ASCII node ids out of the summary section; a mangled byte inside some
    unrelated test's captured output must not be able to void a survey.
    """
    proc = subprocess.run(
        [sys.executable, "-m", "pytest"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    body = proc.stdout.splitlines()
    start = next((i for i, line in enumerate(body) if "short test summary info" in line), len(body))
    summary = body[start:]

    def ids(prefix: str) -> tuple[str, ...]:
        return tuple(
            line.split(" ", 1)[1].strip()
            for line in summary
            if line.startswith(prefix) and "::" in line
        )

    return proc.returncode, ids("FAILED "), ids("ERROR ")


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

    # DOES WHAT WE JUST WROTE EVEN PARSE? Read back from disk rather than
    # compiling the buffer, so this speaks for the bytes the suite would have
    # imported. It runs BEFORE the `--dry-run` return on purpose: checking
    # anchors cheaply is exactly what that flag is for.
    try:
        compile(mutated, str(target), "exec")
    except SyntaxError as exc:
        print("  --- ABORTED: the mutated source does not parse ---")
        print(f"      {type(exc).__name__}: {exc.msg} at line {exc.lineno}")
        print("      The anchor was wrong, so no experiment was performed.")
        print("      NOT a kill, NOT an abstention, NOT a scored row.")
        raise HarnessAnchorError(
            f"{mutation.id}: mutated source does not parse -- {exc.msg} "
            f"at line {exc.lineno}. The anchor matched once but produced invalid "
            f"Python, so the mutation expressed no behaviour to measure."
        ) from exc

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
    # Set only by `HarnessAnchorError`. Caught here rather than allowed to
    # propagate so the run ends with this file's own refusal code and a legible
    # message, the way every other refusal above does -- a traceback would bury
    # the one line that says which anchor was wrong.
    aborted = ""
    try:
        for mutation in mutations:
            try:
                result = apply_and_report(target, mutation, dry_run=args.dry_run)
                if result is not None:
                    results.append(result)
            except HarnessAnchorError as exc:
                aborted = str(exc)
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
            if dirty or aborted:
                break
    finally:
        backup.unlink(missing_ok=True)

    if dirty:
        return 2

    if aborted:
        # NO SUMMARY IS PRINTED. Rows already scored before the bad anchor are
        # discarded deliberately: a survey is read as a set, and publishing a
        # partial one invites the reader to treat the gap as an abstention --
        # which is the exact misreading this check exists to prevent.
        print(f"\n{'=' * 74}\nRUN ABORTED -- HARNESS FAULT\n{'=' * 74}")
        print(f"  {aborted}")
        print(f"  {len(results)} earlier result(s) discarded; fix the anchor and re-run.")
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
