"""Tests for the gate's interpreter guard.

``scripts/`` is not importable as a package (pytest's ``pythonpath`` is ``src``
only), so the module under test is loaded by path. That is deliberate: the guard
exists to protect ``scripts/check.py`` specifically, and reaching it the way a
caller would -- by file location -- keeps the test honest about what it covers.

The guard's decision is a pure function precisely so it can be exercised here.
Testing it end to end would need a second interpreter, which is the thing the
guard exists to stop the suite from depending on.
"""

from __future__ import annotations

import importlib.util
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
