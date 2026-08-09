"""The quality gate, as an executable definition.

``make check`` was the documented gate for five phases, and on a Windows
development machine without ``make`` installed it had never once been executed
as written -- only its individual commands, retyped by hand. A gate that cannot
be run where the work happens is a gate in name only, so the definition moves
here: Python is unconditionally available, behaves identically on Windows, Linux
and any future CI runner, and is the interpreter the tools already live in.

The Makefile keeps its targets as one-line delegations, so there is one
definition rather than two that drift.

Run it::

    python scripts/check.py              # all four steps
    python scripts/check.py lint         # ruff check + ruff format --check
    python scripts/check.py type         # mypy
    python scripts/check.py test         # pytest
    python scripts/check.py --fail-fast  # stop at the first failing step

Two deliberate divergences from ``make``'s semantics, both recorded in the
commit that introduced this file:

* **Run-all by default.** ``make`` halts a target at its first non-zero command.
  That answers "is it green?", but the common case mid-milestone is wanting
  *every* failure in one pass rather than re-running four times to discover them
  serially. ``--fail-fast`` restores the old behaviour for CI.
* **Delegated ``make lint`` no longer halts** between ``ruff check`` and
  ``ruff format --check``, inheriting the run-all default above.

Every tool is invoked as ``sys.executable -m <tool>`` so the checks always run in
the interpreter that launched them -- never a different Python that happens to
be earlier on ``PATH``. All three resolve this way, ``ruff`` included.

The interpreter guard
---------------------
That last paragraph is correct and was not sufficient. ``sys.executable`` is
whatever launched this file, and ``python scripts/check.py`` resolves through
``PATH`` -- on a Windows machine with the Store Python earlier on it, the gate
ran four tools in an interpreter that had never heard of this project. It failed
loudly only because that interpreter happened to carry none of them. **Had it
carried any, the gate would have reported PASS against the wrong environment,
with an identical-looking summary block.**

This is the third time the gate was correct and its invocation was not: ``make
check`` was the documented gate for five phases and could not run on the machine
where the work happened, and ``| tail`` masked a non-zero exit twice.

:func:`interpreter_refusal` closes it, and the key it uses is deliberately *not*
a location test -- not "am I in a venv", not "is my prefix under the repo".
Either would refuse a legitimate CI runner, container or relocated venv while
still passing any unrelated venv, which is the case that matters. It asks the
only question the gate's claim rests on: **are the four tools about to measure
this tree?** An interpreter that cannot import this checkout's ``trading_bot``
cannot be running this checkout's tests, whatever its summary says.

There are exactly three ways to satisfy it, and all three deliberately bind this
interpreter to this checkout: ``pip install -e .`` from here (the documented
setup -- see README), a ``PYTHONPATH`` entry pointing at this ``src/``, or a
``.pth`` doing the same. None of them happens by PATH precedence or by
activating the wrong environment, which is how all three historical failures
arrived.

The unread-output guard
-----------------------
``| tail`` has masked a non-zero exit from this gate **twice**. A shell
pipeline's status is the *last* stage's unless ``pipefail`` is set, so
``python scripts/check.py | tail`` reports ``tail``'s success whatever the gate
did -- and the truncation discarded the pytest summary that named the cause,
both times.

:func:`pipe_refusal` closes it, and the predicate is **a pipe specifically**,
not "not a terminal". The obvious test, ``sys.stdout.isatty()``, was rejected on
a measurement rather than on taste: on this machine ``isatty()`` is ``False``
for a pipe, for ``> gate.log`` under both cmd.exe and git-bash, *and* for the
tool harness the work is actually done through. A guard on it would refuse
every one of those, and the first thing it would refuse is a redirect to a file
-- which launders nothing (the exit status survives) and truncates nothing (the
file has every byte). A guard that refuses correct usage is one people delete.

``stat.S_ISFIFO`` separates the three cases that matter. Measured, because
Windows is where this runs and its file-type reporting is not something to
assume::

    cmd.exe  ... | findstr    st_mode 0o10000    ISFIFO   <- refused
    git-bash ... | tail       st_mode 0o10000    ISFIFO   <- refused
    cmd.exe  ... > file       st_mode 0o100666   ISREG    <- allowed
    git-bash ... > file       st_mode 0o100666   ISREG    <- allowed
    os.pipe() write end       st_mode 0o10000    ISFIFO

The last row is why the test can be honest: an ``os.pipe()`` write end is
byte-for-byte the same ``st_mode`` as a real shell pipe here, so the test
exercises the case rather than a model of it.

**What it cannot do, stated so nobody reads it larger than it is.** Nothing this
process does can repair ``$?`` -- under ``| tail`` the refusal's own exit status
is laundered too. What is bought is that the run does not happen and the
operator gets a refusal instead of a plausible summary. Weaker than the
interpreter guard, which prevents a wrong measurement; this one only prevents a
right measurement from being silently thrown away.

Two consequences follow from that limit. The refusal is raised as
:class:`SystemExit`, so Python writes it to **stderr** -- had it gone to stdout,
``| head -1`` would swallow the refusal as well. And a legitimate non-interactive
consumer that reads the process's own status (CI, a pre-commit hook, an editor
task) needs a way through, because no portable test distinguishes a pipe to
``tail`` from a pipe to a log collector: ``CHECK_ALLOW_PIPE`` is it. An
environment variable rather than a flag, deliberately -- ``--allow-pipe | tail``
would be one keystroke away from the habit this exists to break. There is no
automatic ``CI=true`` exemption either: a developer with ``CI`` exported for some
other tool would be silently unguarded.
"""

from __future__ import annotations

import argparse
import os
import stat
import subprocess
import sys
import time
from pathlib import Path
from typing import TYPE_CHECKING, NamedTuple

if TYPE_CHECKING:  # pragma: no cover - typing only
    from collections.abc import Sequence

#: This checkout's ``src/`` -- the directory a correct interpreter must resolve
#: ``trading_bot`` inside. Derived from this file's own location, so a copy of
#: the repo elsewhere checks itself rather than the original.
_SRC = Path(__file__).resolve().parents[1] / "src"

_WRONG_INTERPRETER = (
    "\nRefusing to run: this interpreter is not the one that would measure this "
    "tree.\n\n"
    "  interpreter : {executable}\n"
    "  trading_bot : {found}\n"
    "  expected in : {expected}\n\n"
    "The gate runs every tool as `sys.executable -m <tool>`, so a PASS from an "
    "interpreter\nthat cannot import this checkout's package would be a PASS "
    "against a different\nenvironment -- and the summary block looks identical "
    "either way.\n\n"
    "Run it through the project environment:\n"
    "    .venv/Scripts/python.exe scripts/check.py     (Windows)\n"
    "    .venv/bin/python scripts/check.py             (POSIX)\n\n"
    "If this IS the project environment, the editable install is missing:\n"
    "    pip install -e .\n"
)


def interpreter_refusal(module_file: str | None, *, expected_src: Path) -> str | None:
    """The refusal message for this interpreter, or ``None`` if it is the right one.

    ``module_file`` is ``trading_bot.__file__`` -- ``None`` both when the import
    failed and when the module is a namespace package, which is the same answer
    for our purposes: nothing importable resolves to this tree.

    Kept pure and separate from :func:`_require_project_interpreter` so the
    decision is testable without a second interpreter to run it in.
    """
    found = "<not importable>" if module_file is None else str(Path(module_file).resolve().parent)
    if module_file is not None and Path(module_file).resolve().parents[1] == expected_src:
        return None
    return _WRONG_INTERPRETER.format(executable=sys.executable, found=found, expected=expected_src)


#: Set to any non-empty value to allow a piped run. Presence is the whole
#: signal -- ``CHECK_ALLOW_PIPE=0`` allows it too, because a parser for
#: falsey spellings would be a second thing to keep true for no gain.
_ALLOW_PIPE_ENV = "CHECK_ALLOW_PIPE"

_UNREAD_OUTPUT = (
    "\nRefusing to run: this gate's output is being piped, so its exit status is "
    "not the one\nyou will read.\n\n"
    "  stdout : a pipe (FIFO)\n"
    f"  set    : {_ALLOW_PIPE_ENV} is unset\n\n"
    "A shell pipeline reports the LAST stage's status unless `set -o pipefail` is "
    "in force,\nso `python scripts/check.py | tail` reports tail's success no matter "
    "what the gate did.\nThat has masked a non-zero exit here twice, and both times "
    "the truncation also discarded\nthe diagnostic naming the cause.\n\n"
    "Run it bare and read its own summary:\n"
    "    python scripts/check.py\n\n"
    "Or redirect to a file, which keeps both the exit status and every line:\n"
    "    python scripts/check.py > gate.log\n\n"
    "If the caller reads this process's own exit status (CI, a pre-commit hook, an "
    "editor\ntask), say so explicitly:\n"
    f"    {_ALLOW_PIPE_ENV}=1 python scripts/check.py | your-consumer\n"
)


def pipe_refusal(st_mode: int, *, allow_pipe: bool) -> str | None:
    """The refusal message for this stdout, or ``None`` if it may be used.

    ``st_mode`` is ``os.fstat(stdout).st_mode``. Only a FIFO is refused: a
    regular file (``> gate.log``) preserves both the exit status and every line,
    and a character device is a terminal or ``os.devnull``.

    Kept pure and separate from :func:`_require_readable_output` so the decision
    is testable against synthetic and real descriptors alike, mirroring
    :func:`interpreter_refusal`.
    """
    if allow_pipe or not stat.S_ISFIFO(st_mode):
        return None
    return _UNREAD_OUTPUT


def _require_readable_output() -> None:
    """Exit non-zero when stdout is a pipe and no opt-out was given.

    Degrades to *allow* when stdout cannot be stat'd -- a captured stream with no
    real descriptor raises on ``fileno()``. A guard that crashes the gate because
    it could not inspect a file descriptor is a guard people delete, and the
    thing being protected is a reporting convention rather than a correctness
    one.
    """
    try:
        st_mode = os.fstat(sys.stdout.fileno()).st_mode
    except (AttributeError, OSError, ValueError):
        return
    refusal = pipe_refusal(st_mode, allow_pipe=bool(os.environ.get(_ALLOW_PIPE_ENV)))
    if refusal is not None:
        raise SystemExit(refusal)


def _require_project_interpreter() -> None:
    """Exit non-zero unless this interpreter resolves ``trading_bot`` to this tree."""
    try:
        import trading_bot
    except ModuleNotFoundError:
        found = None
    else:
        found = trading_bot.__file__
    # `_SRC` is read as a global here rather than bound as a default on
    # `interpreter_refusal`, so a test can point it at another tree.
    refusal = interpreter_refusal(found, expected_src=_SRC)
    if refusal is not None:
        raise SystemExit(refusal)


class Step(NamedTuple):
    """One gate step. ``group`` is the Makefile target that selects it."""

    group: str
    label: str
    args: tuple[str, ...]


#: The gate, in order. Ordering is load-bearing: the two ruff steps take seconds
#: and pytest takes over a minute, so a formatting failure surfaces immediately
#: instead of after the full suite.
#:
#: Scopes are the specification, adopted from the Makefile targets they replace.
#: ruff takes explicit paths; mypy is config-driven (`files` in pyproject.toml)
#: and pytest is config-driven (`testpaths`), so neither takes paths here --
#: passing them would create a second source of truth for coverage.
STEPS: tuple[Step, ...] = (
    Step("lint", "ruff check", ("-m", "ruff", "check", "src", "tests", "scripts")),
    Step(
        "lint",
        "ruff format --check",
        ("-m", "ruff", "format", "--check", "src", "tests", "scripts"),
    ),
    Step("type", "mypy", ("-m", "mypy")),
    Step("test", "pytest", ("-m", "pytest")),
)

GROUPS: tuple[str, ...] = ("lint", "type", "test")

_PASS = "PASS"
_FAIL = "FAIL"
_SKIPPED = "SKIPPED"


def run_step(step: Step) -> bool:
    """Run one step, echoing the exact command. ``True`` when it exits zero."""
    command = [sys.executable, *step.args]
    print(f"\n=== {step.label} ===", flush=True)
    print(f"$ {' '.join(command)}", flush=True)
    completed = subprocess.run(command, check=False)
    return completed.returncode == 0


def _status(label: str, results: dict[str, bool]) -> str:
    """PASS/FAIL for a step that ran, SKIPPED for one ``--fail-fast`` cut short.

    Absence and failure are distinguished deliberately: a step that never ran is
    not a step that passed, and reporting it as either would misstate what was
    actually checked.
    """
    if label not in results:
        return _SKIPPED
    return _PASS if results[label] else _FAIL


def _summary(selected: Sequence[Step], results: dict[str, bool], elapsed: float) -> None:
    print("\n" + "=" * 60)
    for step in selected:
        print(f"  {_status(step.label, results):<8} {step.label}")
    print("=" * 60)
    print(f"  {elapsed:.1f}s total")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="check.py", description="Run the project quality gate.")
    parser.add_argument(
        "group",
        nargs="?",
        choices=GROUPS,
        default=None,
        help="run only this group of steps (default: all)",
    )
    parser.add_argument(
        "--fail-fast",
        action="store_true",
        help="stop at the first failing step instead of running them all",
    )
    namespace = parser.parse_args(argv)

    # Two refusals before any step, both after argument parsing so `--help`
    # still works anywhere. Order is not load-bearing -- both are pure, both
    # exit, both reach stderr. The invocation is checked first because it is the
    # one the operator fixes by re-typing the command they just typed; the
    # interpreter is a property of the environment. See the module docstring.
    _require_readable_output()
    _require_project_interpreter()

    selected = [s for s in STEPS if namespace.group is None or s.group == namespace.group]
    results: dict[str, bool] = {}
    started = time.monotonic()

    for step in selected:
        results[step.label] = run_step(step)
        if not results[step.label] and namespace.fail_fast:
            break

    _summary(selected, results, time.monotonic() - started)

    # This script's own exit code, never a subprocess's return code verbatim: a
    # tool that exits 2 for "usage error" would otherwise be indistinguishable
    # from one that exits 2 for "findings", and callers only need pass/fail.
    return 0 if all(results.get(s.label, False) for s in selected) else 1


if __name__ == "__main__":
    raise SystemExit(main())
