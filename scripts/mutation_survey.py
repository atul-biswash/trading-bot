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

**A CRASH IS NEVER A KILL.** ``CLAUDE.md``: *"Confirm the test that fails is
the one meant to, and that it reports the wrong value -- a wrong stage, not an
``AttributeError`` or a collection error. A crash means the mutation broke
something else on the way and the assertion was never reached; that is not
coverage."*

**THAT SENTENCE USED TO READ "IS AN ABSTENTION", AND THE TWO CASES HAVE NOW
SEPARATED** -- ``M5i-103``. They are different states and only one of them was
ever implemented:

* the SUITE produced no verdict -- ``ERROR`` lines, or an exit status that is
  neither 0 nor 1 -- and the row is ABSTAINED, as before. Nothing ran.
* a TEST was reached and died somewhere other than an assertion. The suite
  produced a verdict; that test simply proved nothing. It is scored **0** and
  reported as a CRASH beside the kills, because it is neither coverage nor an
  abstention.

Until this commit the second case was counted as a KILL. MEASURED: commit A's
D4 reported 4 where two were a ``KeyError`` and a ``ValueError`` at unguarded
unpacks, and only a hand pass separated them. :func:`classify_failure` is what
separates them now, and the definition of a kill is THREE exception types
rather than one -- see its constant for why, and why one type was the wrong
answer in the expensive direction.

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

**RESTORE IS A BYTE COPY, VERIFIED BY SHA-256, IN A ``finally``.** Never
``read_text``/``write_text``: that round-trips newlines and produces a byte
mismatch against this LF-pinned tree -- content-identical, checksum-different,
and indistinguishable from real corruption until diffed.

**AND THE BACKUP LIVES OUTSIDE THE TREE.** It sat beside its target until
``M5i-084`` was mechanised -- inside `src/`, and removed in a ``finally``
INCLUDING on the path where the restore had just failed, which is precisely
when a clean copy is wanted. It is now a temp file whose path is printed before
the first byte moves, and it is KEPT when a restore fails. A mismatch raises
:exc:`HarnessStateError`.

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
import os
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final

import pytest
from check import pipe_refusal

ROOT = Path(__file__).resolve().parent.parent

#: Lines of context printed either side of the mutated line.
CONTEXT = 6

#: pytest exit statuses that represent a completed run whose verdict can be
#: read. 0 is all-passed, 1 is tests-failed. Everything else -- interrupted,
#: internal error, usage error, nothing collected -- means no verdict.
_READABLE_EXITS = frozenset({0, 1})

#: **WHAT COUNTS AS A KILL, and it is THREE types rather than one.** `M5i-115`.
#:
#: ``CLAUDE.md`` asks whether *"the failing statement is a test assertion"*. The
#: obvious reading -- credit only ``AssertionError`` -- is WRONG, and wrong in
#: the expensive direction. Three pytest constructs are assertions and only one
#: of them raises ``AssertionError``:
#:
#: * a bare ``assert x``                     -> ``AssertionError``
#: * an unmet ``pytest.raises(...)``         -> ``Failed`` ("DID NOT RAISE")
#: * ``pytest.fail(...)``                    -> ``Failed``
#:
#: And a test whose contract is *"this must NOT raise"* fails by letting the
#: exception ESCAPE, so it can never report an ``AssertionError`` at all --
#: ``SystemExit`` is the case this repository actually has, in the guard tests.
#: MEASURED at the guard commit: under an ``AssertionError``-only rule, H3
#: credited 1 of 4 real kills and H4 credited 1 of 2. Those are FALSE
#: ABSTENTIONS, which ``CLAUDE.md`` names as the direction that costs most --
#: coverage that exists, filed as coverage that does not.
#:
#: **`pytest.fail.Exception` RATHER THAN `from _pytest.outcomes import
#: Failed`.** They are the SAME OBJECT -- measured, ``is`` -- but one is public
#: and one is not. ``pytest.fail`` is documented API and pytest sets
#: ``.Exception`` on it itself, so a reorganisation of ``_pytest.outcomes``
#: carries the attribute with it. If pytest ever removed the attribute this
#: module would raise ``AttributeError`` AT IMPORT, loudly, before any survey
#: scored anything -- rather than silently reclassifying every `Failed` as a
#: crash, which is what a stale private import would do.
#:
#: Note ``Failed`` and ``SystemExit`` are ``BaseException`` and NOT
#: ``Exception``; ``issubclass`` spans both, a bare ``except Exception`` would
#: not.
_KILL_EXCEPTIONS: Final[tuple[type[BaseException], ...]] = (
    AssertionError,
    pytest.fail.Exception,
    SystemExit,
)

#: Where the in-subprocess hook writes its verdicts. Set by :func:`run_suite`.
_VERDICT_ENV = "MUTATION_SURVEY_VERDICTS"


def classify_failure(*, when: str, exc_type: type[BaseException]) -> bool:
    """``True`` when this failure is a KILL rather than a crash.

    Pure, and separate from the hook for the reason :func:`check.pipe_refusal`
    is separate from its caller: the decision is then testable against
    synthetic inputs without running pytest at all.

    **``when`` MUST BE ``"call"``.** A failure in ``setup`` or ``teardown`` is
    a fixture that broke, which pytest reports as ``ERROR`` rather than
    ``FAILED`` -- the mutation never reached the test body, so nothing was
    measured. ``CLAUDE.md``: *"A crash means the mutation broke something else
    on the way and the assertion was never reached; that is not coverage."*

    **THE FRAME THE EXCEPTION COMES FROM IS NOT THE TEST.** Location is the
    tempting discriminator and it is the wrong one, in both directions.
    ``(record,) = records`` raises ``ValueError`` INSIDE the test file and is a
    crash -- `M5i-104` is the measured case. An unmet ``pytest.raises`` raises
    ``Failed`` from inside pytest, OUTSIDE the test file, and is a kill. Only
    the TYPE separates them.
    """
    return when == "call" and issubclass(exc_type, _KILL_EXCEPTIONS)


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item: Any, call: Any) -> Any:
    """Record the real exception CLASS for every failing test.

    **A HOOKWRAPPER BECAUSE ``call.excinfo`` DOES NOT SURVIVE THE REPORT.** The
    report is built to be serialisable, so the traceback object is discarded
    and only a rendered string remains. Wrapping ``makereport`` is the one
    place the live exception is still in hand.

    **AND THE ALTERNATIVE -- PARSING PYTEST'S OUTPUT -- WAS MEASURED AND
    REJECTED.** At this repository's node-id lengths the short summary's
    ``- <reason>`` is TRUNCATED AWAY entirely under capture, because the
    default width is 80 columns when stdout is not a terminal. And even when
    it survives, a bare ``assert x == y`` renders as ``assert 0 == 1`` with no
    type name in it at all, so any text discriminator must special-case
    pytest's assertion rewriting. A class needs no special case.

    This module is loaded into the subprocess as a plugin by :func:`run_suite`;
    outside that, ``_VERDICT_ENV`` is unset and the hook records nothing, so
    importing this file has no effect on an ordinary pytest run.
    """
    outcome = yield
    report = outcome.get_result()
    destination = os.environ.get(_VERDICT_ENV)
    if destination is None or not report.failed or call.excinfo is None:
        return
    exc_type = call.excinfo.type
    row = {
        "nodeid": report.nodeid,
        "when": call.when,
        "type": exc_type.__name__,
        "kill": classify_failure(when=call.when, exc_type=exc_type),
    }
    with open(destination, "a", encoding="utf-8") as handle:
        handle.write(json.dumps(row) + "\n")


class HarnessStateError(Exception):
    """The target was not restored to the bytes the run began with.

    **A HARNESS FAULT OF THE WORST KIND: THE TREE IS DIRTY AND THE SURVEY IS
    OVER.** Distinct from :exc:`HarnessAnchorError`, which means nothing was
    measured; this means something was measured and the file under `src/` no
    longer matches what it was. `M5i-084` is the measured case -- a survey
    piped through ``head`` left `src/` mutated on disk, and recovery depended
    on a copy someone had taken by hand.

    The backup is NOT deleted when this raises. Its path is printed at the top
    of every run precisely so a hard kill, or this, is recoverable by hand.
    """


#: Set to any non-empty value to allow a piped run. **PRESENCE IS THE WHOLE
#: SIGNAL, so ``SURVEY_ALLOW_PIPE=0`` ALLOWS the pipe.** The spelling invites
#: the opposite reading and is stated here because nothing reports it: anyone
#: exporting it as ``0`` believing they have disabled the hatch has enabled it.
#: The reason is `check.py`'s and is unchanged -- a parser for falsey spellings
#: would be a second thing to keep true for no gain.
#:
#: **DELIBERATELY NOT `CHECK_ALLOW_PIPE`, and the two must not be merged.**
#: That one exists so a legitimate consumer of the GATE's exit status -- CI, a
#: pre-commit hook, an editor task -- can pipe it. Those consumers have no
#: business unlocking a script that REWRITES `src/` in place, and an operator
#: who exported the gate's name for a CI task would otherwise be silently
#: unguarded here. One mechanism, two switches: the decision function is
#: imported from `check.py` rather than copied, so there is one implementation
#: of what a pipe is, and two independent answers to whether it is allowed.
_ALLOW_PIPE_ENV = "SURVEY_ALLOW_PIPE"

_UNREAD_SURVEY = (
    "\nRefusing to run: this survey's output is being piped, so the record of what "
    "was\nmutated is not the one you will read.\n\n"
    "  stdout : a pipe (FIFO)\n"
    f"  set    : {_ALLOW_PIPE_ENV} is unset\n\n"
    "THIS SCRIPT REWRITES A FILE UNDER `src/` AND RESTORES IT. Its output is the "
    "only\nrecord of which mutation ran, and a pipeline's exit status is the LAST "
    "stage's,\nso a truncated run reports success no matter what happened to the "
    "tree. That has\nalready cost this project a file left MUTATED ON DISK with "
    "its output destroyed:\nthe survey was piped through `head`, the run could not "
    "be repeated, and recovery\ndepended on a copy taken by hand beforehand.\n\n"
    "1. RUN IT BARE in the terminal, and read its own summary:\n"
    "       python scripts/mutation_survey.py <spec.json>\n\n"
    "2. Or REDIRECT FROM A SHELL THAT PASSES A GENUINE FILE DESCRIPTOR -- cmd.exe\n"
    "   or git-bash. A real file keeps both the exit status and every line:\n"
    "       python scripts/mutation_survey.py <spec.json> > survey.txt\n\n"
    "   POWERSHELL IS NOT ONE OF THEM, AND THIS GUARD IS NOT MISFIRING. PowerShell\n"
    "   routes a native command's stdout through an ANONYMOUS PIPE and writes the\n"
    "   file itself, so the descriptor this process is handed really is a FIFO and\n"
    "   is indistinguishable from `| head`. MEASURED on this machine: PowerShell\n"
    "   `> file` reports st_mode 0o10000 (FIFO) where cmd.exe and git-bash both\n"
    "   report 0o100666 (regular file).\n\n"
    "3. Or, LAST and deliberately, for a PowerShell redirect or a caller that reads\n"
    "   this process's own exit status:\n"
    f"       $env:{_ALLOW_PIPE_ENV}=1; python scripts/mutation_survey.py <spec.json> > survey.txt\n"
)


def _require_readable_output() -> None:
    """Exit non-zero when stdout is a pipe and no opt-out was given.

    **THE DECISION IS `check.py`'s, IMPORTED RATHER THAN COPIED.**
    :func:`check.pipe_refusal` is already pure for exactly this reason -- its
    own docstring says it is kept separate *"so the decision is testable
    against synthetic and real descriptors alike"* -- and a second copy of
    "what counts as a pipe" is a second thing to keep true. Only a FIFO is
    refused: a regular file (``> survey.txt``) preserves both the exit status
    and every line, and a character device is a terminal or ``os.devnull``.
    **Every survey in this milestone redirected to a file, and every one still
    runs.**

    Its RETURN VALUE is used as a predicate and its message is discarded,
    which is deliberate rather than wasteful: that string names the gate, its
    remedy and ``CHECK_ALLOW_PIPE``, and none of those is this script's story.

    Degrades to *allow* when stdout cannot be stat'd, matching
    :func:`check._require_readable_output`: a captured stream with no real
    descriptor raises on ``fileno()``, and a guard that crashes the survey
    because it could not inspect a file descriptor is a guard people delete.

    **WHY THIS EXISTS AT ALL.** `M5i-084` and `M5i-097`: four breaches of the
    no-piping rule in this milestone, against a rule every party could quote,
    with `check.py` refusing and this script not. The worst left `src/`
    mutated on disk. A rule that lives only in prose is one this project has
    now watched fail four times.
    """
    try:
        st_mode = os.fstat(sys.stdout.fileno()).st_mode
    except (AttributeError, OSError, ValueError):
        return
    if pipe_refusal(st_mode, allow_pipe=bool(os.environ.get(_ALLOW_PIPE_ENV))) is not None:
        raise SystemExit(_UNREAD_SURVEY)


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
    #: Failures at a test ASSERTION. This is the score. `M5i-103`.
    kills: int = 0
    #: Failures that reached the test and died elsewhere. Scored 0, printed
    #: anyway: a crash is a test that was reached and proved nothing, which is
    #: different from a test that was never reached and from one that passed.
    crashes: int = 0


def sha256(path: Path) -> str:
    """The target's digest. **SHA-256, and the width is the point.**

    It replaced md5 with the snapshot. Nothing here is adversarial, so md5's
    weakness was never the objection -- what a wider digest buys is that
    "restored == baseline" cannot be doubted for the one reason a reader would
    otherwise have to consider. This runs twice per mutation on one file.
    """
    return hashlib.sha256(path.read_bytes()).hexdigest()


@dataclass(frozen=True)
class SuiteOutcome:
    """One pytest run, summarised BOTH ways.

    The two halves are deliberately kept side by side rather than collapsed.
    ``failed``/``errored`` come from the short summary, parsed at column 0, and
    are unchanged and still correct -- they are the CROSS-CHECK. ``kills`` and
    ``crashes`` come from the in-process hook and are what the summary cannot
    carry: a ``FAILED`` line says a test failed and never says whether it
    failed at an assertion.

    ``total`` is the classified failure count. It should equal ``len(failed)``
    and a divergence is worth reporting rather than smoothing: it would mean
    the hook and the summary disagree about what failed.
    """

    exit_code: int
    failed: tuple[str, ...]
    errored: tuple[str, ...]
    kills: int
    crashes: int
    total: int


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


def run_suite(*, args: Sequence[str] = ()) -> SuiteOutcome:
    """Run pytest from the repo root and classify every failure.

    ``args`` are appended to the pytest command line. **THE DEFAULT IS EMPTY,
    so every existing survey is unchanged** -- it still runs the whole suite
    from ``testpaths``. The parameter exists because the self-tests cannot: four
    whole-suite runs inside a unit test is eight minutes, where a throwaway
    target is under half a second.

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
    scratch = Path(tempfile.mkdtemp(prefix="mutation-survey-verdicts-"))
    verdicts = scratch / "verdicts.jsonl"
    env = dict(os.environ)
    env[_VERDICT_ENV] = str(verdicts)
    # THIS MODULE IS THE PLUGIN. `scripts/` is not a package, so the subprocess
    # is told where to find it rather than being expected to guess -- the same
    # path `sys.path[0]` supplies for a direct invocation. Loading the harness
    # into the runner keeps the hook beside the code that reads its output;
    # a separate plugin file would be a second thing to keep in step.
    env["PYTHONPATH"] = os.pathsep.join([str(ROOT / "scripts"), env.get("PYTHONPATH", "")]).rstrip(
        os.pathsep
    )
    try:
        proc = subprocess.run(
            [sys.executable, "-m", "pytest", "-p", "mutation_survey", *args],
            cwd=ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=env,
            check=False,
        )
        rows = (
            [
                json.loads(line)
                for line in verdicts.read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
            if verdicts.exists()
            else []
        )
    finally:
        shutil.rmtree(scratch, ignore_errors=True)

    body = proc.stdout.splitlines()
    start = next((i for i, line in enumerate(body) if "short test summary info" in line), len(body))
    summary = body[start:]

    def ids(prefix: str) -> tuple[str, ...]:
        return tuple(
            line.split(" ", 1)[1].strip()
            for line in summary
            if line.startswith(prefix) and "::" in line
        )

    kills = sum(1 for row in rows if row["kill"])
    return SuiteOutcome(
        exit_code=proc.returncode,
        failed=ids("FAILED "),
        errored=ids("ERROR "),
        kills=kills,
        crashes=len(rows) - kills,
        total=len(rows),
    )


def apply_and_report(
    target: Path,
    mutation: Mutation,
    *,
    dry_run: bool,
    suite_args: Sequence[str] = (),
) -> Result | None:
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
    print(f"  mutated sha   : {sha256(target)}")
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

    outcome = run_suite(args=suite_args)
    exit_code, failed, errored = outcome.exit_code, outcome.failed, outcome.errored
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
        # **THE CLASSIFIED COUNT IS THE RESULT; `len(failed)` IS THE RAW ONE.**
        # `M5i-103`: this line read `len(failed)` and scored a crash as a kill.
        # MEASURED at commit A -- D4 reported 4 where two were a `KeyError` and
        # a `ValueError` at unguarded unpacks, and only a hand pass separated
        # them. Both numbers are printed because a DIVERGENCE is the finding:
        # the crashes are tests that were reached and proved nothing.
        print(f"  --- {outcome.kills} KILLED ---  (raw FAILED: {len(failed)})")
        if outcome.crashes:
            print(f"      {outcome.crashes} CRASHED -- reached, proved nothing, scored 0")
        if outcome.total != len(failed):
            print(
                f"      NOTE: the hook saw {outcome.total} failures and the summary "
                f"{len(failed)}; they should agree."
            )
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
        kills=outcome.kills,
        crashes=outcome.crashes,
    )


def describe_vcs_state(target: Path) -> str:
    """Whether the target is tracked and clean. **ADVISORY, NEVER A REFUSAL.**

    **A DIRTY TARGET IS THE NORMAL CASE, not a warning sign.** Commits A and B
    both surveyed uncommitted edits, and they had to: surveying the committed
    version would measure the PREVIOUS commit, which is not the thing under
    review. A harness that refused here would refuse every survey this
    milestone actually ran.

    So this reports and returns. `M5i-084`'s rule is satisfied by the
    out-of-tree backup above rather than by interrogating git -- the snapshot
    exists whatever git says, which is the stronger guarantee. If the owner
    later rules that an untracked target must be refused, that is one ``if``
    at the call site and this function already computes the fact.

    Never raises: git may be absent, the tree may not be a checkout, and
    neither is a reason to abandon a survey.
    """
    try:
        tracked = subprocess.run(
            ["git", "ls-files", "--error-unmatch", str(target)],
            cwd=ROOT,
            capture_output=True,
            check=False,
        )
        if tracked.returncode != 0:
            return "target is UNTRACKED -- the out-of-tree backup is the only copy"
        dirty = subprocess.run(
            ["git", "diff", "--quiet", "HEAD", "--", str(target)],
            cwd=ROOT,
            capture_output=True,
            check=False,
        )
    except OSError as exc:  # git missing, or not a checkout
        return f"vcs state unknown ({type(exc).__name__}) -- backup taken regardless"
    if dirty.returncode == 0:
        return "target is tracked and clean"
    return "target has uncommitted edits -- normal for a survey of work in progress"


def main() -> int:
    # FIRST, BEFORE THE SPEC IS EVEN PARSED. A refusal must leave the tree
    # exactly as it found it, and the only way to guarantee that is to refuse
    # before anything is read, copied or written -- there is no backup to
    # restore from yet, and no mutation to undo.
    _require_readable_output()
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

    baseline = sha256(target)
    # **OUT OF THE TREE, AND THAT IS `M5i-084`'s RULE MECHANISED.** The backup
    # sat BESIDE its target until now -- inside `src/`, deleted in a `finally`
    # including on the path where the restore had just FAILED, which is exactly
    # when it is wanted. A temp directory survives that, survives a hard kill,
    # and cannot be mistaken for a source file by anything that walks `src/`.
    backup_dir = Path(tempfile.mkdtemp(prefix="mutation-survey-backup-"))
    backup = backup_dir / target.name
    print(f"target        : {target.relative_to(ROOT).as_posix()}")
    print(f"baseline sha  : {baseline}")
    print(f"mutations     : {len(mutations)}")
    # PRINTED BEFORE THE FIRST BYTE MOVES, so a process killed mid-run leaves
    # an operator a path rather than a puzzle.
    print(f"backup        : {backup}")
    print(f"vcs           : {describe_vcs_state(target)}")

    shutil.copy2(target, backup)
    if sha256(backup) != baseline:
        print("REFUSED: the byte copy does not match the original")
        shutil.rmtree(backup_dir, ignore_errors=True)
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
                restored = sha256(target)
                print(f"  original sha  : {baseline}")
                print(f"  restored sha  : {restored}")
                if restored == baseline:
                    print("  restore verified by BYTE IDENTITY")
                else:
                    print("  FAILED TO RESTORE -- THE TREE IS DIRTY. Stopping.")
                    dirty = True
            if dirty or aborted:
                break
    finally:
        # **THE BACKUP IS KEPT WHEN THE RESTORE FAILED.** Deleting it there was
        # the old behaviour and it destroyed the only clean copy at the one
        # moment it was needed. `M5i-084`.
        if not dirty:
            shutil.rmtree(backup_dir, ignore_errors=True)
        else:
            print(f"\n  THE BACKUP IS KEPT: {backup}")
            print("  Copy it back over the target by hand before doing anything else.")

    if dirty:
        # **RAISED AFTER THE LOOP, NEVER FROM INSIDE THE `finally`.** A raise
        # there replaces whatever exception is in flight, and a restore failure
        # is precisely when a real one is most likely to be travelling -- the
        # same reasoning the `dirty` flag already carries for `return`.
        raise HarnessStateError(
            f"{target} was not restored: expected {baseline}, found {restored}. "
            f"A clean copy is at {backup}."
        )

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
                crashed = f", {result.crashes} crashed" if result.crashes else ""
                print(f"  {result.id}: {result.kills} killed{crashed} -- {names}")
    return 0


if __name__ == "__main__":  # pragma: no cover - CLI entry point
    raise SystemExit(main())
