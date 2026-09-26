"""Startup provenance: the git runner, the executable it trusts, the status parser.

Git is replaced at ``subprocess.run`` in the runner tests, and a planted
binary is found by the real ``shutil.which`` in the executable tests.

Test numbers follow the P54/P55/P56 plan so each mutation's predicted killers
can be named.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from trading_bot.utils import provenance
from trading_bot.utils.provenance import (
    GIT_TIMEOUT_S,
    GitOutput,
    GitUnknown,
    child_environment,
    parse_porcelain,
    resolve_git,
    run_git,
)

_WINDOWS_ONLY = pytest.mark.skipif(os.name != "nt", reason="Windows executable search only")


class _RunSpy:
    """Replaces ``subprocess.run``: records each call and scripts its effect."""

    def __init__(self, effect: Callable[[list[str], dict[str, Any]], int] | None = None) -> None:
        self.effect = effect
        self.calls: list[tuple[list[str], dict[str, Any]]] = []

    def __call__(self, command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[bytes]:
        self.calls.append((command, kwargs))
        code = 0 if self.effect is None else self.effect(command, kwargs)
        return subprocess.CompletedProcess(command, code)


def _patch_run(monkeypatch: pytest.MonkeyPatch, spy: Callable[..., Any]) -> None:
    monkeypatch.setattr(provenance.subprocess, "run", spy)


# --------------------------------------------------------------------------
# The checkout: status, rename, dirty, clean
# --------------------------------------------------------------------------
def test_rename_entry_consumes_two_z_fields() -> None:
    """Test 3. A rename's original path is a second field, consumed and not reported.

    MUTATION m5: consume one field. ``old.py`` is then read as an entry of its
    own, which has no ``XY `` prefix, and the parse fails as malformed.
    """
    assert parse_porcelain(b"R  new.py\0old.py\0 M x.py\0") == ("new.py", "x.py")
    assert parse_porcelain(b"C  copy.py\0orig.py\0") == ("copy.py",)
    assert parse_porcelain(b"R  new.py\0") is None
    assert parse_porcelain(b"") == ()


# --------------------------------------------------------------------------
# Every failure is unknown
# --------------------------------------------------------------------------
def test_timeout_is_unknown(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Test 6. A timed-out call is ``git_timeout``.

    MUTATION m1: map a timeout to an empty success. The runner then returns
    ``GitOutput(b"")``, which the status parser reads as clean.
    """

    def _raise(command: list[str], kwargs: dict[str, Any]) -> int:
        raise subprocess.TimeoutExpired(command, GIT_TIMEOUT_S)

    _patch_run(monkeypatch, _RunSpy(_raise))
    assert run_git(Path("git.exe"), ["status"], tmp_path) == GitUnknown("git_timeout")


def test_default_runner_uses_list_no_shell_timeout_cwd(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Test 8. The call's shape: a list, no shell, a timeout, a pinned cwd, files.

    MUTATIONS m2 (drop ``timeout=``), m3 (``shell=True``) and m16 (pipes in
    place of temporary files) each change one asserted keyword.
    """
    spy = _RunSpy()
    _patch_run(monkeypatch, spy)
    git = tmp_path / "git.exe"

    assert run_git(git, ["status"], tmp_path) == GitOutput(b"")

    assert len(spy.calls) == 1
    command, kwargs = spy.calls[0]
    assert isinstance(command, list)
    assert command == [str(git), "-c", "core.fsmonitor=false", "--no-optional-locks", "status"]
    assert kwargs.get("shell") is False
    assert kwargs.get("timeout") == GIT_TIMEOUT_S
    assert kwargs.get("cwd") == tmp_path
    assert kwargs.get("stdin") is subprocess.DEVNULL
    for stream in ("stdout", "stderr"):
        assert kwargs.get(stream) not in (None, subprocess.PIPE)
        assert callable(getattr(kwargs.get(stream), "fileno", None))


# --------------------------------------------------------------------------
# The git executable and its call
# --------------------------------------------------------------------------
@_WINDOWS_ONLY
@pytest.mark.parametrize("cwd_search", ["implicit", "explicit"])
def test_git_inside_checkout_is_untrusted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, cwd_search: str
) -> None:
    """Test 19. A git planted in the launch directory is never the one called.

    ``[implicit]`` unsets ``NoDefaultCurrentDirectoryInExePath``, so Windows
    searches the cwd first and ``which`` returns a RELATIVE ``.\\git.EXE``
    (P55 S0.1). ``[explicit]`` sets it, so the implicit search is off, and puts
    the cwd on ``PATH`` instead, so ``which`` returns an ABSOLUTE path inside
    it. The harness this was written under sets the variable (``M5l-022``), so
    each case controls it rather than inheriting it.

    MUTATION m13: drop the location check. ``[explicit]`` then trusts the
    planted binary; ``[implicit]`` is still refused by the absolute-path check.
    """
    checkout = tmp_path / "checkout"
    checkout.mkdir()
    shutil.copy2(sys.executable, checkout / "git.exe")
    monkeypatch.chdir(checkout)
    if cwd_search == "implicit":
        monkeypatch.delenv("NoDefaultCurrentDirectoryInExePath", raising=False)
    else:
        monkeypatch.setenv("NoDefaultCurrentDirectoryInExePath", "1")
        monkeypatch.setenv("PATH", f"{checkout}{os.pathsep}{os.environ.get('PATH', '')}")

    found = shutil.which("git")
    assert found is not None
    assert Path(found).resolve() == (checkout / "git.exe").resolve()

    assert resolve_git(checkout) == GitUnknown("git_untrusted_path")


def test_non_exe_git_is_untrusted(tmp_path: Path) -> None:
    """Test 28. On Windows only a ``.exe`` is called; ``.cmd`` goes through ``cmd.exe``.

    MUTATION m20: remove the suffix check. ``git.cmd`` is then trusted.
    """
    tools = tmp_path / "tools"
    tools.mkdir()
    cwd = tmp_path / "cwd"
    cwd.mkdir()
    cmd = tools / "git.cmd"
    exe = tools / "git.EXE"

    assert resolve_git(cwd, which=lambda _n: str(cmd), windows=True) == GitUnknown(
        "git_untrusted_path"
    )
    assert resolve_git(cwd, which=lambda _n: str(exe), windows=True) == exe.resolve()
    assert (
        resolve_git(cwd, which=lambda _n: str(tools / "git"), windows=False)
        == (tools / "git").resolve()
    )


def test_child_env_has_no_git_variables(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Test 20. No ``GIT_*`` variable reaches the child, whatever its case.

    MUTATION m14: pass ``GIT_*`` through. ``GIT_DIR`` reaches the child.
    """
    assert child_environment({"GIT_DIR": "x", "git_trace": "1", "PATH": "p"}) == {"PATH": "p"}

    monkeypatch.setenv("GIT_DIR", str(tmp_path / "elsewhere"))
    monkeypatch.setenv("GIT_WORK_TREE", str(tmp_path))
    spy = _RunSpy()
    _patch_run(monkeypatch, spy)

    run_git(tmp_path / "git.exe", ["status"], tmp_path)

    assert len(spy.calls) == 1
    env = spy.calls[0][1].get("env") or {}
    assert [key for key in env if key.upper().startswith("GIT_")] == []
    assert any(key.upper() == "PATH" for key in env)


def test_grandchild_holding_output_returns_within_timeout(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Test 24. P55 S0.2: a grandchild holding the output cannot outlast the timeout.

    The fake git starts a grandchild that inherits its output and sleeps, then
    sleeps itself. Through pipes, ``subprocess.run`` would wait for the
    grandchild after killing the child; through files it does not.

    MUTATION m16: pipes in place of files. The call then takes about twenty
    seconds. MUTATION m2: no timeout. The call waits for the fake itself.
    """
    script = tmp_path / "fake_git.py"
    script.write_text(
        "import subprocess, sys, time\n"
        "subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(20)'],"
        " stdout=sys.stdout, stderr=sys.stderr)\n"
        "time.sleep(20)\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(provenance, "_GIT_PREFIX", ())
    monkeypatch.setattr(provenance, "GIT_TIMEOUT_S", 1.0)

    start = time.monotonic()
    outcome = run_git(Path(sys.executable), [str(script)], tmp_path)
    elapsed = time.monotonic() - start

    assert outcome == GitUnknown("git_timeout")
    assert elapsed < 5.0
