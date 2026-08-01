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
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import time
from typing import TYPE_CHECKING, NamedTuple

if TYPE_CHECKING:  # pragma: no cover - typing only
    from collections.abc import Sequence


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
