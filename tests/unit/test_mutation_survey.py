"""The mutation survey's unread-output guard.

``scripts/`` is not importable as a package (pytest's ``pythonpath`` is ``src``
only), so the module under test is loaded by path -- the same idiom
``test_check_script.py`` uses, and for the same reason.

**ONE DIFFERENCE FROM THAT MODULE, AND IT IS DELIBERATE: THIS ONE PUTS
``scripts/`` ON ``sys.path`` BEFORE LOADING.** ``check.py`` imports nothing from
beside it, so loading it in isolation is honest. This script imports
``pipe_refusal`` from ``check``, and at runtime that resolves because
``sys.path[0]`` is ``scripts/`` for ``python scripts/mutation_survey.py`` --
MEASURED. Loading it without that path is therefore loading it under a
condition it never actually meets, which would be testing the wrong state.

**EVERY TEST HERE DRIVES ``_require_readable_output``, NEVER ``pipe_refusal``
DIRECTLY.** The decision function belongs to ``check.py`` and is already
covered by ``test_check_script.py``; asserting against it here would test that
module's code and report it as this one's coverage. What is this script's own
is that it CALLS the decision at all, that it calls it with ITS OWN opt-out,
and that it calls it before the first byte is written.

The guard's subject is a reporting convention, not a correctness one -- but the
thing it protects is a script that rewrites a file under ``src/`` in place.
``M5i-084`` and ``M5i-097``: four breaches this milestone, one of which left
``src/`` mutated on disk with the output destroyed.
"""

from __future__ import annotations

import importlib.util
import json
import os
import shutil
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SCRIPTS = _REPO_ROOT / "scripts"
_SURVEY_PY = _SCRIPTS / "mutation_survey.py"


def _load_survey_module() -> ModuleType:
    """Import ``scripts/mutation_survey.py`` by path, with ``scripts/`` reachable.

    The ``sys.path`` insertion reproduces the interpreter state a direct
    ``python scripts/mutation_survey.py`` produces; without it the module's
    ``from check import pipe_refusal`` raises ``ModuleNotFoundError``, which is
    a fact about this loader rather than about the script.

    **AND THE MODULE IS REGISTERED IN ``sys.modules`` BEFORE IT IS EXECUTED,
    WHICH ``test_check_script.py`` DOES NOT NEED TO DO.** ``@dataclass`` reads
    ``sys.modules[cls.__module__].__dict__`` while it processes the class, so a
    module executed before it is registered fails inside ``dataclasses`` with
    ``AttributeError: 'NoneType' object has no attribute '__dict__'`` -- an
    error that names neither this loader nor the import it is really about.
    ``check.py`` has no dataclass, so the shorter idiom is complete for it and
    incomplete here. MEASURED: without this line, collection of this module
    fails at ``@dataclass(frozen=True)`` on ``Mutation``.
    """
    if str(_SCRIPTS) not in sys.path:
        sys.path.insert(0, str(_SCRIPTS))
    spec = importlib.util.spec_from_file_location("_survey_under_test", _SURVEY_PY)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


survey = _load_survey_module()


class _FakeStdout:
    """A stdout whose ``fileno`` is ours to choose.

    **IT IS A WRITABLE STREAM, AND THAT IS NOT DECORATION.** The guard only
    ever calls ``fileno``, so a fake with nothing else passes every test while
    the guard works -- and fails with ``AttributeError`` the moment a REGRESSED
    guard lets ``main`` reach its first ``print``. MEASURED: without ``write``,
    ``test_the_guard_runs_before_any_mutation_is_applied`` crashes in the
    fixture instead of reaching its own assertion, so it scores as a crash
    rather than a kill. A fake that is only as capable as the happy path needs
    is a fake that cannot express the failure.
    """

    def __init__(self, fd: int | None) -> None:
        self._fd = fd
        self.written: list[str] = []

    def fileno(self) -> int:
        if self._fd is None:
            raise ValueError("I/O operation on closed file")
        return self._fd

    def write(self, text: str) -> int:
        self.written.append(text)
        return len(text)

    def flush(self) -> None:
        return None


def _guard(monkeypatch: pytest.MonkeyPatch, fd: int | None, **env: str | None) -> None:
    """Run the guard with this descriptor and this environment."""
    monkeypatch.setattr(survey.sys, "stdout", _FakeStdout(fd))
    monkeypatch.delenv(survey._ALLOW_PIPE_ENV, raising=False)
    monkeypatch.delenv("CHECK_ALLOW_PIPE", raising=False)
    for name, value in env.items():
        if value is None:
            monkeypatch.delenv(name, raising=False)
        else:
            monkeypatch.setenv(name, value)
    survey._require_readable_output()


def test_a_real_pipe_is_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    """A real FIFO, not a synthetic ``st_mode``.

    MUTATION: drop the `pipe_refusal` call; allow a FIFO.

    ``os.pipe()``'s write end reports byte-for-byte the same ``st_mode`` as a
    shell pipe on this platform -- ``check.py`` measured that and records the
    table -- so this exercises the guard against the descriptor it exists for.
    """
    read_fd, write_fd = os.pipe()
    try:
        with pytest.raises(SystemExit):
            _guard(monkeypatch, write_fd)
    finally:
        os.close(read_fd)
        os.close(write_fd)


def test_a_regular_file_is_not_refused(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """**THE NEGATIVE CONTROL THAT MATTERS, and it is not a formality.**

    MUTATION: refuse anything that is not a character device.

    EVERY survey in this milestone was run as
    ``python scripts/mutation_survey.py <spec> > survey.txt`` and every one must
    keep working. A redirect to a regular file preserves the exit status AND
    every line, which is the whole reason only a FIFO is refused -- so a guard
    that caught this would break the one workflow that was already correct, and
    the fix people reach for is deleting the guard.
    """
    path = tmp_path / "survey.txt"
    path.write_text("", encoding="utf-8")
    with path.open("w", encoding="utf-8") as handle:
        _guard(monkeypatch, handle.fileno())


def test_a_character_device_is_not_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    """A terminal and ``os.devnull`` are the same kind of descriptor.

    MUTATION: refuse anything that is not a regular file.

    There is no real terminal in a pytest run, so ``os.devnull`` stands in: a
    character device, which is what an interactive stdout also is.
    """
    with open(os.devnull, "w", encoding="utf-8") as handle:
        _guard(monkeypatch, handle.fileno())


def test_the_opt_out_lets_a_pipe_through(monkeypatch: pytest.MonkeyPatch) -> None:
    """The documented hatch, for a caller that reads this process's own status.

    MUTATION: ignore the environment variable.
    """
    read_fd, write_fd = os.pipe()
    try:
        _guard(monkeypatch, write_fd, **{survey._ALLOW_PIPE_ENV: "1"})
    finally:
        os.close(read_fd)
        os.close(write_fd)


def test_the_opt_out_triggers_on_presence_so_zero_permits(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """**``SURVEY_ALLOW_PIPE=0`` ALLOWS THE PIPE, and that is pinned, not fixed.**

    MUTATION: parse the value, so ``0`` disables the hatch.

    The spelling invites the opposite reading, so the behaviour is asserted
    rather than left to the comment beside the constant. It is deliberate and
    matches ``check.py``: a parser for falsey spellings would be a second thing
    to keep true for no gain. This test exists so that anyone who "fixes" it
    into a parser is told they are changing a decision, not a defect.
    """
    read_fd, write_fd = os.pipe()
    try:
        _guard(monkeypatch, write_fd, **{survey._ALLOW_PIPE_ENV: "0"})
    finally:
        os.close(read_fd)
        os.close(write_fd)


def test_the_gates_opt_out_does_not_unlock_the_survey(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """**The two switches are SEPARATE, and this is what makes that true.**

    MUTATION: read `CHECK_ALLOW_PIPE` here, or share one constant.

    ``CHECK_ALLOW_PIPE`` exists so a legitimate consumer of the GATE's exit
    status can pipe it. Such a consumer has no business unlocking a script that
    rewrites `src/` in place, and an operator who exported the gate's name for a
    CI task would otherwise be silently unguarded here. One implementation of
    what a pipe IS -- imported, not copied -- and two independent answers to
    whether it is allowed.
    """
    read_fd, write_fd = os.pipe()
    try:
        with pytest.raises(SystemExit):
            _guard(monkeypatch, write_fd, CHECK_ALLOW_PIPE="1")
    finally:
        os.close(read_fd)
        os.close(write_fd)


def test_an_unstattable_stdout_is_allowed_rather_than_crashing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Degrade to allow, never to crash.

    MUTATION: let the exception propagate.

    A captured stream with no real descriptor raises on ``fileno()``. What this
    guard protects is a reporting convention; aborting a two-minute survey
    because a file descriptor could not be inspected would trade that for a
    real loss, and is how guards get deleted.
    """
    _guard(monkeypatch, None)


def test_the_refusal_names_the_cause_the_remedy_and_its_own_opt_out(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The message an operator actually reads. **BOTH POLARITIES.**

    MUTATION: reuse `check.py`'s `_UNREAD_OUTPUT` instead of writing one.

    The absent half is the load-bearing one: `pipe_refusal` RETURNS the gate's
    message, so reusing what it hands back would produce a refusal telling the
    operator to run `scripts/check.py` and to set `CHECK_ALLOW_PIPE` -- fluent,
    plausible, and wrong about which script refused and which switch releases
    it.

    **AND IT MUST NAME POWERSHELL, because the obvious remedy does not work
    there and the operator would otherwise conclude the guard is broken.**
    MEASURED: PowerShell routes a native command's stdout through an anonymous
    pipe and writes the file itself, so `> survey.txt` hands this process a
    FIFO -- ``st_mode`` ``0o10000``, against ``0o100666`` from cmd.exe and
    git-bash. Every survey in commits A and B was run that way. A message
    offering `> survey.txt` without that caveat sends an operator to a remedy
    that refuses again, and the fix people reach for then is deleting the
    guard.
    """
    read_fd, write_fd = os.pipe()
    try:
        with pytest.raises(SystemExit) as excinfo:
            _guard(monkeypatch, write_fd)
    finally:
        os.close(read_fd)
        os.close(write_fd)

    message = str(excinfo.value)
    # PRESENT: whose refusal, why, and the way out.
    assert "mutation_survey.py" in message
    assert survey._ALLOW_PIPE_ENV in message
    assert "> survey.txt" in message
    assert "MUTATED ON DISK" in message
    # PRESENT: the platform caveat, without which remedy 2 sends the operator
    # straight back into the refusal.
    assert "POWERSHELL IS NOT ONE OF THEM" in message
    assert "cmd.exe" in message
    assert "git-bash" in message
    # ABSENT: the gate's story, which is not this script's.
    assert "CHECK_ALLOW_PIPE" not in message
    assert "scripts/check.py" not in message


def test_the_guard_runs_before_any_mutation_is_applied(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """**A refusal leaves the tree untouched, and that is an ORDERING claim.**

    MUTATION: move the guard below `load_spec`, or to the top of the mutation
    loop.

    Asserted by a recorder rather than by re-reading the target, because a
    restore would hide the defect: `main` copies the file back in a ``finally``
    on every branch, so a target mutated and restored is byte-identical to one
    never touched. What separates them is whether `apply_and_report` was ever
    reached.

    The recorder also keeps this test FAST. Without it a regressed guard would
    let `main` run the real suite -- two minutes inside a unit test, and the
    assertion would still pass, so the test would be slow AND blind.
    """
    target = tmp_path / "victim.py"
    target.write_text("x = 1\n", encoding="utf-8", newline="\n")
    spec = tmp_path / "spec.json"
    spec.write_text(
        '{"target": "' + target.as_posix() + '", "mutations": []}',
        encoding="utf-8",
        newline="\n",
    )

    reached: list[str] = []
    monkeypatch.setattr(
        survey,
        "apply_and_report",
        lambda *a, **k: reached.append("applied"),  # pragma: no cover - must not run
    )
    monkeypatch.setattr(survey.sys, "argv", ["mutation_survey.py", str(spec)])
    # `main` prints `target.relative_to(ROOT)` before it reaches any mutation,
    # which raises `ValueError` for a target outside the repo. Under the CORRECT
    # code the guard refuses long before that line, so this is inert -- it
    # exists so that a REGRESSED guard fails this test at its own assertion
    # below instead of crashing in `pathlib`. `M5i-104`'s shape, in this file.
    monkeypatch.setattr(survey, "ROOT", tmp_path)

    refused = False
    read_fd, write_fd = os.pipe()
    try:
        monkeypatch.setattr(survey.sys, "stdout", _FakeStdout(write_fd))
        monkeypatch.delenv(survey._ALLOW_PIPE_ENV, raising=False)
        try:
            survey.main()
        except SystemExit:
            refused = True
    finally:
        os.close(read_fd)
        os.close(write_fd)

    # CAUGHT EXPLICITLY RATHER THAN THROUGH `pytest.raises`, so every failure
    # direction lands on an `assert`. `pytest.raises` reports a missing
    # exception as `Failed`, which is not an `AssertionError` -- and a harness
    # that credits a kill only at an `AssertionError` would score this test as
    # a CRASH and file real coverage as none.
    assert refused, "the guard did not refuse a piped stdout"
    assert reached == [], "the survey reached a mutation before refusing the pipe"
    assert target.read_text(encoding="utf-8") == "x = 1\n"


# ---------------------------------------------------------------------------
# The crash-vs-kill discriminator. `M5i-103`.
# ---------------------------------------------------------------------------
#: A target with one mutable answer, and a probe test that reads it.
#:
#: **REAL PYTEST, AGAINST A THROWAWAY TARGET.** `run_suite`'s default runs the
#: whole suite; four of those inside a unit test is eight minutes. Its `args`
#: parameter exists so these cost about half a second each, which is the only
#: reason they can be tests at all rather than a procedure someone remembers.
_VICTIM = "def answer() -> int:\n    return 1\n"

#: The probe's assertion is a BARE `assert`, deliberately. `assert x, "msg"`
#: renders as `AssertionError: msg`; this renders as `assert 2 == 1`, with no
#: type name in it anywhere. A text discriminator would have to special-case
#: that, and would score the commonest shape in this tree as a crash.
_PROBE = (
    "import sys\n"
    "from pathlib import Path\n"
    "\n"
    "sys.path.insert(0, str(Path(__file__).resolve().parent))\n"
    "\n"
    "from victim import answer\n"
    "\n"
    "\n"
    "def test_the_answer_is_one() -> None:\n"
    "    assert answer() == 1\n"
)


def _mutant(tmp_path: Path, replacement: str) -> tuple[Path, Any, list[str]]:
    """A victim, a probe test that reads it, and the mutation to apply."""
    victim = tmp_path / "victim.py"
    victim.write_text(_VICTIM, encoding="utf-8", newline="\n")
    probe = tmp_path / "test_probe.py"
    probe.write_text(_PROBE, encoding="utf-8", newline="\n")
    mutation = survey.Mutation(
        id="SELF",
        name="the self-test's mutant",
        anchor=b"    return 1\n",
        replacement=replacement.encode("utf-8"),
    )
    return victim, mutation, [str(probe)]


def test_a_crashing_mutant_scores_no_kill(tmp_path: Path) -> None:
    """**THE ONE ASSERTION THAT PINS THE WHOLE FIX.** `M5i-103`.

    MUTATION: make the discriminator always answer "kill".

    The victim raises `KeyError` where the probe expects a number, so the test
    IS reached and dies somewhere other than an assertion. pytest reports one
    `FAILED`; the classifier must score it ZERO.

    **IT ASSERTS ON `kills`, NEVER ON `len(failed)`, AND THAT IS THE POINT.**
    On `len(failed)` this test passes under a discriminator hardwired to
    "kill", and the defect being fixed would ship unpinned beside a test that
    looks like it covers it. Both numbers are asserted so what is pinned is the
    DIVERGENCE -- one raw failure, zero kills -- rather than either alone.

    MEASURED, commit A's D4: raw 4, of which two were a `KeyError` and a
    `ValueError` at unguarded unpacks. A hand pass separated them; nothing in
    the harness did.
    """
    victim, mutation, args = _mutant(tmp_path, '    return {}["missing"]\n')
    result = survey.apply_and_report(victim, mutation, dry_run=False, suite_args=args)

    assert result is not None
    assert not result.abstained, "the suite ran; this is a verdict, not an abstention"
    assert len(result.failed) == 1, "exactly one test failed"
    assert result.kills == 0, "a KeyError is not an assertion and must score nothing"
    assert result.crashes == 1


def test_an_assertion_mutant_scores_one_kill(tmp_path: Path) -> None:
    """A bare `assert` is the shape pytest's own summary cannot name.

    MUTATION: make the discriminator always answer "crash".

    The victim returns the wrong number, so the probe's bare `assert` fails.
    That is a real kill and must be credited -- and it is exactly the case a
    text discriminator gets wrong.
    """
    victim, mutation, args = _mutant(tmp_path, "    return 2\n")
    result = survey.apply_and_report(victim, mutation, dry_run=False, suite_args=args)

    assert result is not None
    assert not result.abstained
    assert len(result.failed) == 1
    assert result.kills == 1, "a bare assert IS an assertion and must be credited"
    assert result.crashes == 0


def test_an_unparseable_mutant_aborts_without_running_the_suite(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`HarnessAnchorError`, and pytest is never dispatched.

    MUTATION: move the `compile()` pre-check below `run_suite`.

    **ASSERTED BY A RECORDING DOUBLE, NOT BY TIMING.** "It was fast" is not
    evidence; a flag set inside the replacement is. Under the mutation the
    suite runs first and the abort still happens, so the exception alone cannot
    separate the two orderings -- only whether `run_suite` was reached.

    The double RETURNS A REAL `SuiteOutcome` rather than `None`: `M5i-114` says
    a fake only as capable as the happy path cannot express the failure, and
    one returning `None` would crash the caller with `AttributeError` before
    any assertion -- turning the kill this test exists to score into a crash.
    """
    victim, mutation, _args = _mutant(tmp_path, "    return (\n")

    reached: list[str] = []

    def _recording_run_suite(*, args: Any = ()) -> Any:
        reached.append("ran")
        return survey.SuiteOutcome(exit_code=0, failed=(), errored=(), kills=0, crashes=0, total=0)

    monkeypatch.setattr(survey, "run_suite", _recording_run_suite)

    with pytest.raises(survey.HarnessAnchorError):
        survey.apply_and_report(victim, mutation, dry_run=False)

    assert reached == [], "the suite was dispatched against source that does not parse"


def test_a_survivor_scores_nothing_and_does_not_abstain(tmp_path: Path) -> None:
    """Zero kills is a RESULT, and it is not the same as an abstention.

    MUTATION: report a survivor as abstained; or credit a kill with no failure.

    The mutation changes a comment and nothing else, so every test passes. That
    is the state a survey most needs to read correctly: an abstention says the
    experiment could not run, a survivor says it ran and nothing noticed, and
    only the second is a coverage finding.
    """
    victim = tmp_path / "victim.py"
    victim.write_text("# a comment\n" + _VICTIM, encoding="utf-8", newline="\n")
    probe = tmp_path / "test_probe.py"
    probe.write_text(_PROBE, encoding="utf-8", newline="\n")
    mutation = survey.Mutation(
        id="SELF",
        name="a comment, and nothing observable",
        anchor=b"# a comment\n",
        replacement=b"# a different comment\n",
    )

    result = survey.apply_and_report(victim, mutation, dry_run=False, suite_args=[str(probe)])

    assert result is not None
    assert not result.abstained, "the suite ran and returned a verdict"
    assert result.failed == ()
    assert result.kills == 0
    assert result.crashes == 0


def test_a_corrupted_restore_raises_rather_than_returning(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """**The snapshot's verification, pinned.** `M5i-084`.

    MUTATION: make the restore's hash comparison always pass.

    A restore that silently failed would leave a file under `src/` mutated and
    report success -- the exact state that cost this project a recovery by
    hand. So the comparison may not be decorative: this drives `main` with a
    `copy2` that stops copying, and requires `HarnessStateError`.

    **AND IT REQUIRES THE BACKUP TO SURVIVE.** Deleting it on the failure path
    was the old behaviour and it destroyed the only clean copy at the one
    moment it was wanted, so the message must still name a file that EXISTS. A
    remedy pointing at a deleted path is worse than no remedy.

    Added by the implementer rather than named in the change set: item 2
    specifies the raise, and without this the mutation defeating it kills
    nothing.
    """
    victim = tmp_path / "victim.py"
    victim.write_text(_VICTIM, encoding="utf-8", newline="\n")
    spec = tmp_path / "spec.json"
    spec.write_text(
        json.dumps(
            {
                "target": str(victim),
                # **THE MUTATION MUST ACTUALLY CHANGE BYTES**, or this test
                # cannot express its own subject: a no-op replacement leaves the
                # file matching baseline whether the restore ran or not, so the
                # hash agrees for the wrong reason and nothing raises. MEASURED
                # -- the first version of this test used `return 1` for both and
                # passed the verification it was written to break.
                "mutations": [
                    {
                        "id": "S",
                        "name": "one that really moves a byte",
                        "anchor": "return 1",
                        "replacement": "return 2",
                    }
                ],
            }
        ),
        encoding="utf-8",
        newline="\n",
    )

    monkeypatch.setattr(survey.sys, "argv", ["mutation_survey.py", str(spec)])
    monkeypatch.setattr(survey, "ROOT", tmp_path)
    monkeypatch.setattr(survey, "_require_readable_output", lambda: None)
    monkeypatch.setattr(survey, "run_suite", lambda **_: survey.SuiteOutcome(0, (), (), 0, 0, 0))

    real_copy = shutil.copy2
    calls: list[int] = []

    def _copy_that_stops_restoring(src: Any, dst: Any, **kwargs: Any) -> Any:
        calls.append(1)
        if len(calls) == 1:  # the backup itself must be a real copy
            return real_copy(src, dst, **kwargs)
        return dst  # the RESTORE silently does nothing

    monkeypatch.setattr(survey.shutil, "copy2", _copy_that_stops_restoring)

    with pytest.raises(survey.HarnessStateError) as excinfo:
        survey.main()

    message = str(excinfo.value)
    assert "was not restored" in message
    backup_path = message.rsplit("A clean copy is at ", 1)[-1].rstrip(".")
    assert Path(backup_path).exists(), f"the backup was deleted: {backup_path}"
