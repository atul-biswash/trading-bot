"""Tests for the gate's two invocation guards.

``scripts/`` is not importable as a package (pytest's ``pythonpath`` is ``src``
only), so the module under test is loaded by path. That is deliberate: the guards
exist to protect ``scripts/check.py`` specifically, and reaching it the way a
caller would -- by file location -- keeps the test honest about what it covers.

Each guard's decision is a pure function precisely so it can be exercised here.
Testing the interpreter guard end to end would need a second interpreter, which
is the thing it exists to stop the suite from depending on.

**The two sets are NOT symmetric, and the difference is worth knowing before
reading them as equivalent coverage.** The interpreter guard has a false-refusal
test against live reality -- ``test_the_real_interpreter_running_this_suite_is_
accepted`` passes the actual running interpreter's ``trading_bot.__file__``. The
unread-output guard has no analogue, because pytest replaces ``sys.stdout`` with
a capture object for the duration of the run, so there is no real terminal
descriptor here to assert is accepted. Its negative controls use a regular file
and a character device instead: real descriptors, but not *the* descriptor.
"""

from __future__ import annotations

import importlib.util
import os
import stat
import sys
from pathlib import Path
from types import ModuleType

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
_CHECK_PY = _REPO_ROOT / "scripts" / "check.py"


def _load_check_module() -> ModuleType:
    """Import ``scripts/check.py`` by path, without putting it on ``sys.path``."""
    spec = importlib.util.spec_from_file_location("_check_under_test", _CHECK_PY)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


check = _load_check_module()


# ---------------------------------------------------------------------------
# The interpreter guard
# ---------------------------------------------------------------------------
def test_the_real_interpreter_running_this_suite_is_accepted() -> None:
    """The guard must not refuse the environment the gate actually runs in.

    This is the false-refusal test, and it is the one that matters most: a guard
    that refuses a correct setup is worse than no guard, because the fix people
    reach for is deleting it.
    """
    import trading_bot

    assert check.interpreter_refusal(trading_bot.__file__, expected_src=check._SRC) is None


def test_an_interpreter_that_cannot_import_the_package_is_refused() -> None:
    """The Store-interpreter case: no ``trading_bot`` at all.

    Refused on the import, before any tool runs -- so it is caught whether or not
    that interpreter happens to carry ruff, mypy or pytest. The historical
    failure was loud only by luck.
    """
    refusal = check.interpreter_refusal(None, expected_src=check._SRC)

    assert refusal is not None
    assert "not importable" in refusal
    assert "pip install -e ." in refusal


def test_a_package_resolved_outside_this_checkout_is_refused(tmp_path: Path) -> None:
    """The silent case the guard exists for: importable, but a different tree.

    An interpreter carrying a *copy* of the package -- another checkout, a
    non-editable site-packages install -- would run all four tools green against
    something that is not this working tree.
    """
    stranger = tmp_path / "elsewhere" / "src" / "trading_bot" / "__init__.py"
    stranger.parent.mkdir(parents=True)
    stranger.write_text("", encoding="utf-8")

    refusal = check.interpreter_refusal(str(stranger), expected_src=check._SRC)

    assert refusal is not None
    assert str(tmp_path) in refusal


def test_the_refusal_names_both_paths_and_the_interpreter() -> None:
    """A refusal an operator cannot act on is a refusal they will delete."""
    refusal = check.interpreter_refusal(None, expected_src=check._SRC)

    assert refusal is not None
    assert sys.executable in refusal
    assert str(_REPO_ROOT / "src") in refusal


def test_expected_src_is_derived_from_the_script_location() -> None:
    """A copy of the repo checks itself, not the original it was copied from."""
    assert check._SRC == _REPO_ROOT / "src"


def test_require_project_interpreter_raises_system_exit(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The wrapper exits rather than returning, so no step can run past it."""
    monkeypatch.setattr(check, "_SRC", tmp_path / "not-this-tree")

    with pytest.raises(SystemExit) as excinfo:
        check._require_project_interpreter()

    assert "Refusing to run" in str(excinfo.value)


# ---------------------------------------------------------------------------
# The unread-output guard
# ---------------------------------------------------------------------------
# Every case below stats a REAL descriptor rather than synthesising an
# ``st_mode``. That is what makes these a standing measurement of how this
# platform reports file types, not an assumption about it -- and Windows, where
# this gate is actually run, is the platform whose answer could not be assumed.


def test_a_real_pipe_is_refused() -> None:
    """The historical failure: ``python scripts/check.py | tail``.

    An ``os.pipe()`` write end reports the same ``st_mode`` as a shell pipe on
    this platform (measured: ``0o10000`` under cmd.exe, git-bash and here), so
    this exercises the case rather than a model of it.
    """
    read_fd, write_fd = os.pipe()
    try:
        st_mode = os.fstat(write_fd).st_mode
    finally:
        os.close(read_fd)
        os.close(write_fd)

    assert stat.S_ISFIFO(st_mode), "os.pipe() must report a FIFO or this guard cannot work"
    assert check.pipe_refusal(st_mode, allow_pipe=False) is not None


def test_a_regular_file_is_not_refused(tmp_path: Path) -> None:
    """``> gate.log`` launders nothing and truncates nothing, so it stays legal.

    This is the case an ``isatty()`` guard would have refused: measured on this
    machine, a file redirect reports ``isatty()`` false under both cmd.exe and
    git-bash.
    """
    target = tmp_path / "gate.log"
    with target.open("w", encoding="utf-8") as handle:
        st_mode = os.fstat(handle.fileno()).st_mode

    assert stat.S_ISREG(st_mode)
    assert check.pipe_refusal(st_mode, allow_pipe=False) is None


def test_a_character_device_is_not_refused() -> None:
    """The stand-in for a terminal: ``os.devnull`` is a character device.

    Not the same claim as "the terminal the gate runs in is accepted" -- see the
    module docstring on why that test cannot exist here.
    """
    # `open`, not `Path.open`: os.devnull names a device, not a filesystem path.
    with open(os.devnull, "w", encoding="utf-8") as handle:
        st_mode = os.fstat(handle.fileno()).st_mode

    assert stat.S_ISCHR(st_mode)
    assert check.pipe_refusal(st_mode, allow_pipe=False) is None


def test_the_opt_out_lets_a_pipe_through() -> None:
    """CI and pre-commit read this process's own status; no test can tell them apart."""
    read_fd, write_fd = os.pipe()
    try:
        st_mode = os.fstat(write_fd).st_mode
    finally:
        os.close(read_fd)
        os.close(write_fd)

    assert check.pipe_refusal(st_mode, allow_pipe=True) is None


def test_the_refusal_names_the_cause_the_remedy_and_the_opt_out() -> None:
    """A refusal an operator cannot act on is a refusal they will delete."""
    read_fd, write_fd = os.pipe()
    try:
        refusal = check.pipe_refusal(os.fstat(write_fd).st_mode, allow_pipe=False)
    finally:
        os.close(read_fd)
        os.close(write_fd)

    assert refusal is not None
    assert "pipefail" in refusal
    assert "python scripts/check.py" in refusal
    assert check._ALLOW_PIPE_ENV in refusal


def test_require_readable_output_raises_system_exit(monkeypatch: pytest.MonkeyPatch) -> None:
    """The wrapper exits rather than returning, so no step can run past it.

    ``sys.stdout`` is pointed at a real pipe for the duration, because the
    wrapper's job is precisely to go from a descriptor to a decision -- asserting
    on the pure function again would skip the half under test.
    """
    read_fd, write_fd = os.pipe()
    monkeypatch.delenv(check._ALLOW_PIPE_ENV, raising=False)
    try:
        with os.fdopen(write_fd, "w", encoding="utf-8") as piped:
            monkeypatch.setattr(sys, "stdout", piped)
            with pytest.raises(SystemExit) as excinfo:
                check._require_readable_output()
    finally:
        os.close(read_fd)

    assert "Refusing to run" in str(excinfo.value)


def test_an_unstattable_stdout_is_allowed_rather_than_crashing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Degrade to allow: a guard that crashes the gate is one people delete.

    pytest's own captured stdout is such a stream, so this is the state the guard
    is in for every other test in this suite -- not a hypothetical.
    """

    class _NoDescriptor:
        def fileno(self) -> int:
            raise OSError("captured stream has no descriptor")

    monkeypatch.setattr(sys, "stdout", _NoDescriptor())

    assert check._require_readable_output() is None
