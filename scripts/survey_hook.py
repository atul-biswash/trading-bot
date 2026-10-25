"""The pytest plugin a worktree mutation survey loads: the import proof and the class of every failure.

``scripts/worktree_survey.py`` loads it into the survey's pytest subprocess as ``-p survey_hook`` with
``scripts/`` on ``PYTHONPATH``. It does two jobs and each is a defect that was found in a scratch
harness this replaces.

**The import proof.** At session start it writes where each named package was imported from. A survey
that runs in a relocated tree and appears to kill nothing is indistinguishable from one whose mutation
never loaded (``CLAUDE.md``, harness trap 4), so the survey reads this file before any result counts.

**The real class of every failure (M5n-088).** The scratch harness read the exception types off the
text of pytest's output, scanning for names that end in ``Error``, ``Failed`` or ``Exception``. A crash
named ``decimal.InvalidOperation`` or ``StopIteration`` ends in none of them, so it printed as an
assertion: a false kill, in the cheap-to-catch direction, found only because the predicted types were
written down in advance. This hook records the class itself, from ``call.excinfo``, qualified by its
module, and decides kill or crash by the class and by nothing in any text, with the same
:func:`mutation_survey.classify_failure` the in-place harness uses, so there is one definition of a kill.

Nothing is written unless the survey set the environment variables below, so importing or loading this
module in an ordinary pytest run has no effect.
"""

from __future__ import annotations

import importlib
import json
import os
from pathlib import Path
from typing import Any

import pytest
from mutation_survey import classify_failure

__all__ = ["qualified_name"]

VERDICTS_ENV = "SURVEY_VERDICTS"
PROOF_OUT_ENV = "SURVEY_PROOF_OUT"
PROOF_MODULES_ENV = "SURVEY_PROOF_MODULES"
_DEFAULT_PROOF_MODULES = "trading_bot,tests"


def qualified_name(exc_type: type[BaseException]) -> str:
    """The class name with its module, bare for a builtin: ``ValueError``, ``decimal.InvalidOperation``."""
    module = exc_type.__module__
    if module == "builtins":
        return exc_type.__qualname__
    return f"{module}.{exc_type.__qualname__}"


def pytest_sessionstart(session: object) -> None:
    destination = os.environ.get(PROOF_OUT_ENV)
    if destination is None:
        return
    names = os.environ.get(PROOF_MODULES_ENV, _DEFAULT_PROOF_MODULES).split(",")
    lines = [f"{name}={importlib.import_module(name).__file__}" for name in names if name]
    with Path(destination).open("a", encoding="utf-8", newline="") as handle:
        handle.write("\n".join(lines) + "\n")


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item: Any, call: Any) -> Any:
    outcome = yield
    report = outcome.get_result()
    destination = os.environ.get(VERDICTS_ENV)
    if destination is None or not report.failed or call.excinfo is None:
        return
    exc_type = call.excinfo.type
    row = {
        "nodeid": report.nodeid,
        "when": call.when,
        "type": qualified_name(exc_type),
        "kill": classify_failure(when=call.when, exc_type=exc_type),
    }
    with Path(destination).open("a", encoding="utf-8", newline="") as handle:
        handle.write(json.dumps(row) + "\n")
