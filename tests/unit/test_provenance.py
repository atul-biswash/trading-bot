"""Startup provenance: the facts, the verdict, and that no failure reads as clean.

The distribution is modelled with REAL ``importlib.metadata.PathDistribution``
objects over a site directory written into ``tmp_path`` -- a ``METADATA``, a
``RECORD`` with real urlsafe-base64 sha256 rows, and a ``direct_url.json`` --
so the classifier and the RECORD check run the same code path a real install
does. Git is a scripted runner everywhere except test 15, which drives the
real one in a temporary repository, and the runner tests, which replace
``subprocess.run``.

Test numbers follow the P54/P55/P56 plan so each mutation's predicted killers
can be named.
"""

from __future__ import annotations

import base64
import dataclasses
import hashlib
import json
import logging
import os
import shutil
import subprocess
import sys
import time
from collections.abc import Callable, Sequence
from importlib import metadata
from pathlib import Path
from typing import Any

import pytest

from trading_bot.utils import provenance
from trading_bot.utils.logger import _DATE_FORMAT, _PLAIN_FORMAT, JsonFormatter, PlainFormatter
from trading_bot.utils.provenance import (
    GIT_TIMEOUT_S,
    GitOutcome,
    GitOutput,
    GitUnknown,
    InstallKind,
    Provenance,
    child_environment,
    classify_install,
    collect_provenance,
    parse_porcelain,
    resolve_git,
    run_git,
)

_COMMIT_A = "a" * 40
_COMMIT_B = "b" * 40
_SHA = "0" * 64
_PACKAGE = {
    "trading_bot/__init__.py": b'__version__ = "0.1.0"\n',
    "trading_bot/main.py": b"VALUE = 1\n",
}
_WINDOWS_ONLY = pytest.mark.skipif(os.name != "nt", reason="Windows executable search only")


def _vcs(commit: str = _COMMIT_A) -> dict[str, Any]:
    return {"url": "file:///checkout", "vcs_info": {"vcs": "git", "commit_id": commit}}


def _record_hash(data: bytes) -> str:
    return base64.urlsafe_b64encode(hashlib.sha256(data).digest()).rstrip(b"=").decode("ascii")


def _site(
    root: Path,
    *,
    direct_url: dict[str, Any] | None,
    files: dict[str, bytes] | None = None,
    hashed: bool = True,
) -> tuple[Path, Path]:
    """Write an installed distribution under ``root``; return its dist-info and init file."""
    package = _PACKAGE if files is None else files
    dist_info = root / "binance_trading_bot-0.1.0.dist-info"
    dist_info.mkdir(parents=True)
    rows = []
    for name, data in package.items():
        target = root / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        rows.append(f"{name},sha256={_record_hash(data)},{len(data)}" if hashed else f"{name},,")
    rows.append("trading_bot/__pycache__/__init__.cpython-312.pyc,,")
    rows.append(f"{dist_info.name}/METADATA,,")
    rows.append(f"{dist_info.name}/RECORD,,")
    (dist_info / "METADATA").write_text(
        "Metadata-Version: 2.1\nName: binance-trading-bot\nVersion: 0.1.0\n", encoding="utf-8"
    )
    (dist_info / "RECORD").write_text("\n".join(rows) + "\n", encoding="utf-8")
    if direct_url is not None:
        (dist_info / "direct_url.json").write_text(json.dumps(direct_url), encoding="utf-8")
    return dist_info, root / "trading_bot" / "__init__.py"


def _finder(dist_info: Path) -> Callable[[str], metadata.Distribution]:
    def find(name: str) -> metadata.Distribution:
        assert name == "binance-trading-bot"
        return metadata.PathDistribution(dist_info)

    return find


def _missing(name: str) -> metadata.Distribution:
    raise metadata.PackageNotFoundError(name)


class _Git:
    """A scripted runner keyed by git subcommand, recording every call."""

    def __init__(self, outcomes: dict[str, GitOutcome]) -> None:
        self.outcomes = outcomes
        self.calls: list[list[str]] = []

    def __call__(self, git: Path, args: Sequence[str], cwd: Path) -> GitOutcome:
        self.calls.append(list(args))
        return self.outcomes[args[0]]


def _head(root: Path, commit: str = _COMMIT_A) -> GitOutput:
    return GitOutput(f"{root.as_posix()}\n{commit}\n".encode())


def _clean_git(root: Path, commit: str = _COMMIT_A, status: bytes = b"") -> _Git:
    return _Git(
        {
            "rev-parse": _head(root, commit),
            "status": GitOutput(status),
            "ls-files": GitOutput(b"config.yaml\0"),
        }
    )


def _checkout(tmp_path: Path) -> Path:
    root = tmp_path / "checkout"
    root.mkdir(parents=True)
    (root / "config.yaml").write_text("mode: testnet\n", encoding="utf-8")
    return root


def _outside_git(tmp_path: Path) -> Path:
    return tmp_path / "tools" / "git.exe"


def _collect(
    tmp_path: Path,
    *,
    git: _Git | None = None,
    direct_url: dict[str, Any] | None = None,
    module_file: Path | None = None,
    config_path: Path | None = None,
    find: Callable[[str], metadata.Distribution] | None = None,
    runner: Callable[[Path, Sequence[str], Path], GitOutcome] | None = None,
) -> Provenance:
    """An accepted collection unless a keyword says otherwise."""
    root = tmp_path / "checkout"
    if not root.exists():
        _checkout(tmp_path)
    dist_info, init = _site(tmp_path / "site", direct_url=direct_url or _vcs())
    return collect_provenance(
        root / "config.yaml" if config_path is None else config_path,
        _SHA,
        cwd=root,
        module_file=init if module_file is None else module_file,
        find_distribution=_finder(dist_info) if find is None else find,
        resolve=lambda _cwd: _outside_git(tmp_path),
        runner=(_clean_git(root) if git is None else git) if runner is None else runner,
    )


def _accepted_facts() -> Provenance:
    return Provenance(
        install_kind=InstallKind.VCS,
        code_commit=_COMMIT_A,
        code_intact=True,
        code_files_checked=2,
        module_file=Path("site/trading_bot/__init__.py"),
        checkout_root=Path("checkout"),
        checkout_commit=_COMMIT_A,
        dirty_paths=(),
        commits_agree=True,
        config_path=Path("checkout/config.yaml"),
        config_sha256=_SHA,
        config_tracked=True,
        python_version="3.12.10",
        package_version="0.1.0",
        unknown_reasons=(),
    )


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
def test_clean_checkout_reports_commit_and_clean(tmp_path: Path) -> None:
    """Test 1. Every fact known and accepting: the verdict is accepted."""
    facts = _collect(tmp_path)
    fields = facts.log_fields()

    assert facts.accepted is True
    assert facts.refusal_reasons == ()
    assert facts.checkout_commit == _COMMIT_A
    assert facts.checkout_dirty is False
    assert fields["verdict"] == "accepted"
    assert fields["checkout_dirty"] == "false"
    assert fields["dirty_count"] == 0
    assert fields["dirty_paths"] == "none"
    assert fields["commits_agree"] == "true"
    assert fields["config_tracked"] == "true"
    assert fields["code_intact"] == "true"
    assert fields["code_files_checked"] == 2


def test_dirty_paths_are_counted_and_named(tmp_path: Path) -> None:
    """Test 2. Modified, untracked and added entries all count, and all are named.

    MUTATION m4: skip ``??`` entries. ``notes.txt`` disappears from the list
    and the count drops to 2.
    """
    root = _checkout(tmp_path)
    status = b" M config.yaml\0?? notes.txt\0A  src/new.py\0"
    facts = _collect(tmp_path, git=_clean_git(root, status=status))
    fields = facts.log_fields()

    assert facts.dirty_paths == ("config.yaml", "notes.txt", "src/new.py")
    assert fields["dirty_count"] == 3
    assert fields["dirty_paths"] == "config.yaml;notes.txt;src/new.py"
    assert fields["checkout_dirty"] == "true"
    assert "checkout_dirty=true" in facts.refusal_reasons

    many = b"".join(f"?? f{index:02d}.txt\0".encode() for index in range(25))
    many_fields = _collect(
        tmp_path / "many", git=_clean_git(_checkout(tmp_path / "many"), status=many)
    ).log_fields()
    assert many_fields["dirty_count"] == 25
    assert isinstance(many_fields["dirty_paths"], str)
    assert len(many_fields["dirty_paths"].split(";")) == 20


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
def test_git_missing_is_unknown_not_clean(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Test 4. No git, at resolution or at execution: unknown, never clean."""

    def _raise(command: list[str], kwargs: dict[str, Any]) -> int:
        raise FileNotFoundError(command[0])

    _patch_run(monkeypatch, _RunSpy(_raise))
    assert run_git(Path("git.exe"), ["status"], tmp_path) == GitUnknown("git_not_found")
    assert resolve_git(tmp_path, which=lambda _name: None) == GitUnknown("git_not_found")

    root = _checkout(tmp_path)
    dist_info, init = _site(tmp_path / "site", direct_url=_vcs())
    facts = collect_provenance(
        root / "config.yaml",
        _SHA,
        cwd=root,
        module_file=init,
        find_distribution=_finder(dist_info),
        resolve=lambda _cwd: GitUnknown("git_not_found"),
        runner=_clean_git(root),
    )
    assert facts.checkout_dirty is None
    assert facts.log_fields()["checkout_dirty"] == "unknown"
    assert "git_not_found" in facts.unknown_reasons
    assert facts.accepted is False


def test_not_a_repository_is_unknown(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Test 5. A non-zero exit is ``git_exit_<rc>``, and the checkout is unknown."""
    _patch_run(monkeypatch, _RunSpy(lambda _command, _kwargs: 128))
    assert run_git(Path("git.exe"), ["rev-parse"], tmp_path) == GitUnknown("git_exit_128")

    root = _checkout(tmp_path)
    git = _Git({"rev-parse": GitUnknown("git_exit_128")})
    facts = _collect(tmp_path, git=git)
    assert facts.checkout_root is None
    assert facts.checkout_commit is None
    assert facts.checkout_dirty is None
    assert facts.config_tracked is None
    assert facts.unknown_reasons == ("git_exit_128",)
    assert git.calls == [["rev-parse", "--show-toplevel", "HEAD"]]
    assert root.exists()


def test_timeout_is_unknown(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Test 6. A timed-out call is ``git_timeout``.

    MUTATION m1: map a timeout to an empty success. The runner then returns
    ``GitOutput(b"")``, which the status parser reads as clean.
    """

    def _raise(command: list[str], kwargs: dict[str, Any]) -> int:
        raise subprocess.TimeoutExpired(command, GIT_TIMEOUT_S)

    _patch_run(monkeypatch, _RunSpy(_raise))
    assert run_git(Path("git.exe"), ["status"], tmp_path) == GitUnknown("git_timeout")


def test_unknown_never_renders_as_clean(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Test 7. Through the real runner: a status that timed out renders unknown.

    Only the status call times out; the head and the config reads succeed, so
    the one thing that could make ``checkout_dirty`` read ``false`` is the
    timeout being taken for an empty answer. MUTATION m1 does exactly that.
    """
    root = _checkout(tmp_path)

    def _effect(command: list[str], kwargs: dict[str, Any]) -> int:
        if "rev-parse" in command:
            kwargs["stdout"].write(f"{root.as_posix()}\n{_COMMIT_A}\n".encode())
        elif "status" in command:
            raise subprocess.TimeoutExpired(command, GIT_TIMEOUT_S)
        else:
            kwargs["stdout"].write(b"config.yaml\0")
        return 0

    _patch_run(monkeypatch, _RunSpy(_effect))
    facts = _collect(tmp_path, runner=run_git)
    fields = facts.log_fields()

    assert fields["checkout_dirty"] == "unknown"
    assert fields["dirty_count"] == "unknown"
    assert fields["dirty_paths"] == "unknown"
    assert "git_timeout" in facts.unknown_reasons
    assert "checkout_dirty=unknown" in facts.refusal_reasons
    assert fields["verdict"] == "refused"


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
# The install
# --------------------------------------------------------------------------
@pytest.mark.parametrize(
    ("direct_url", "found", "kind", "commit"),
    [
        ({"url": "file:///src", "dir_info": {"editable": True}}, True, InstallKind.EDITABLE, None),
        (_vcs(), True, InstallKind.VCS, _COMMIT_A),
        ({"url": "file:///src", "dir_info": {}}, True, InstallKind.DIR, None),
        (_vcs(), False, InstallKind.UNKNOWN, None),
    ],
    ids=["editable", "vcs", "dir", "no_distribution"],
)
def test_install_kind_from_direct_url(
    tmp_path: Path,
    direct_url: dict[str, Any],
    found: bool,
    kind: InstallKind,
    commit: str | None,
) -> None:
    """Test 9. The kind, and a commit only from a VCS install.

    MUTATION m10: invert the editable flag. ``[editable]`` falls through to the
    kind checks and ``[dir]`` is labelled editable.
    """
    dist_info, init = _site(tmp_path, direct_url=direct_url)
    facts = classify_install(init, _finder(dist_info) if found else _missing)

    assert facts.kind is kind
    assert facts.commit == commit
    if not found:
        assert facts.reason == "no_distribution"


def test_commits_agree_is_unknown_when_either_side_unknown(tmp_path: Path) -> None:
    """Test 12. Agreement is true, false, or unknown -- never true by default.

    MUTATION m7: agree when either side is unknown. The two unknown cases
    render ``true``.
    """
    no_commit = _collect(tmp_path / "a", direct_url={"url": "file:///src", "dir_info": {}})
    assert no_commit.code_commit is None
    assert no_commit.commits_agree is None

    root_b = _checkout(tmp_path / "b")
    no_head = _collect(tmp_path / "b", git=_Git({"rev-parse": GitUnknown("git_exit_128")}))
    assert no_head.checkout_commit is None
    assert no_head.commits_agree is None
    assert root_b.exists()

    root_c = _checkout(tmp_path / "c")
    differ = _collect(tmp_path / "c", git=_clean_git(root_c, commit=_COMMIT_B))
    assert differ.commits_agree is False

    same = _collect(tmp_path / "d")
    assert same.commits_agree is True

    rendered = [f.log_fields()["commits_agree"] for f in (no_commit, no_head, differ, same)]
    assert rendered == ["unknown", "unknown", "false", "true"]


def test_shadowed_distribution_is_unknown(tmp_path: Path) -> None:
    """Test 16. P55 S0.4's variant: a copy of ``trading_bot`` imported ahead of the install.

    The copy sits in its own directory with no egg-info beside it, so the
    metadata still names the installed commit while the code imported is the
    copy. The commit must NOT be reported.

    MUTATION m11: remove the shadow guard. The install reads VCS with the
    commit of code that is not running.
    """
    shadow = tmp_path / "shadow" / "trading_bot" / "__init__.py"
    shadow.parent.mkdir(parents=True)
    shadow.write_bytes(_PACKAGE["trading_bot/__init__.py"])

    facts = _collect(tmp_path, module_file=shadow)

    assert facts.install_kind is InstallKind.UNKNOWN
    assert facts.code_commit is None
    assert "shadowed" in facts.unknown_reasons
    assert facts.log_fields()["code_commit"] == "unknown"
    assert facts.accepted is False


def test_record_mismatch_is_not_intact(tmp_path: Path) -> None:
    """Test 17. An installed file edited, or deleted, after the install is not intact.

    The deleted case is what found ``M5l-026``: through ``Distribution.files``
    the deleted file's row vanished and the check reported intact.

    MUTATION m12: skip the hash comparison. The edited file then passes.
    """
    dist_info, init = _site(tmp_path / "site", direct_url=_vcs())
    (tmp_path / "site" / "trading_bot" / "main.py").write_bytes(b"VALUE = 2\n")
    edited = provenance.verify_record(metadata.PathDistribution(dist_info))
    assert edited.intact is False

    dist_gone, _init = _site(tmp_path / "gone", direct_url=_vcs())
    (tmp_path / "gone" / "trading_bot" / "main.py").unlink()
    missing = provenance.verify_record(metadata.PathDistribution(dist_gone))
    assert missing.intact is False

    root = _checkout(tmp_path)
    facts = collect_provenance(
        root / "config.yaml",
        _SHA,
        cwd=root,
        module_file=init,
        find_distribution=_finder(dist_info),
        resolve=lambda _cwd: _outside_git(tmp_path),
        runner=_clean_git(root),
    )
    assert facts.code_intact is False
    assert "code_intact=false" in facts.refusal_reasons


def test_zero_hashed_record_entries_is_unknown(tmp_path: Path) -> None:
    """Test 18. A RECORD with nothing to verify establishes nothing: unknown."""
    dist_info, init = _site(tmp_path / "site", direct_url=_vcs(), hashed=False)
    root = _checkout(tmp_path)
    facts = collect_provenance(
        root / "config.yaml",
        _SHA,
        cwd=root,
        module_file=init,
        find_distribution=_finder(dist_info),
        resolve=lambda _cwd: _outside_git(tmp_path),
        runner=_clean_git(root),
    )

    assert facts.code_intact is None
    assert facts.code_files_checked == 0
    assert "record_unhashed" in facts.unknown_reasons
    assert "code_intact=unknown" in facts.refusal_reasons


def test_missing_direct_url_is_unknown_with_reason(tmp_path: Path) -> None:
    """Test 30. No ``direct_url.json`` -- the repository's ``src`` on ``sys.path`` (S0.4).

    MUTATION m22: treat a missing file as a plain directory install. The kind
    becomes ``dir`` and the reason disappears.
    """
    dist_info, init = _site(tmp_path, direct_url=None)
    facts = classify_install(init, _finder(dist_info))

    assert facts.kind is InstallKind.UNKNOWN
    assert facts.reason == "no_direct_url"
    assert facts.commit is None


def test_editable_install_keeps_label_and_refuses(tmp_path: Path) -> None:
    """Test 27. An editable install is labelled editable, and refused for it.

    Modelled on P55 S0.3b: the distribution's files are not where it points,
    because an editable install places none there, and the imported module is
    in a separate source tree.

    MUTATION m19: apply the shadow guard to editable. The label becomes
    ``unknown`` with a shadow reason.
    """
    source = tmp_path / "src" / "trading_bot" / "__init__.py"
    source.parent.mkdir(parents=True)
    source.write_bytes(_PACKAGE["trading_bot/__init__.py"])
    dist_info, _init = _site(
        tmp_path / "editable_site",
        direct_url={"url": "file:///src", "dir_info": {"editable": True}},
        files={},
    )

    facts = _collect(tmp_path, module_file=source, find=_finder(dist_info))

    assert facts.install_kind is InstallKind.EDITABLE
    assert facts.log_fields()["install_kind"] == "editable"
    assert "install_kind=editable" in facts.refusal_reasons
    assert "shadowed" not in facts.unknown_reasons
    assert "shadow_check_failed" not in facts.unknown_reasons
    assert facts.accepted is False


def test_shadow_guard_uses_samefile_not_string_equality(tmp_path: Path) -> None:
    """Test 29. The same file under a different path is the same file.

    A hard link gives two paths whose resolved strings differ and which
    ``os.path.samefile`` knows to be one file.

    MUTATION m21: compare ``str(resolve())``. The hard link reads as shadowed.
    """
    dist_info, init = _site(tmp_path / "site", direct_url=_vcs())
    alias = tmp_path / "alias" / "trading_bot" / "__init__.py"
    alias.parent.mkdir(parents=True)
    try:
        os.link(init, alias)
    except OSError as exc:
        pytest.skip(f"hard links unavailable here: {exc}")
    assert os.path.samefile(init, alias)
    assert str(init.resolve()) != str(alias.resolve())

    facts = classify_install(alias, _finder(dist_info))

    assert facts.kind is InstallKind.VCS
    assert facts.commit == _COMMIT_A


def test_url_never_appears_in_record(tmp_path: Path) -> None:
    """Test 25. A credential in ``direct_url.json``'s url reaches neither sink.

    MUTATION m17: log the url. The token then appears in both renderings.
    """
    secret = "SECRET-TOKEN-must-never-be-logged"
    url = f"git+https://user:{secret}@example.invalid/r.git"
    cases = (
        {"url": url, "vcs_info": {"vcs": "git", "commit_id": _COMMIT_A}},
        {"url": url, "vcs_info": {"vcs": "hg"}},
    )
    for index, direct_url in enumerate(cases):
        facts = _collect(tmp_path / str(index), direct_url=direct_url)
        record = logging.makeLogRecord(
            {"name": "trading_bot.main", "msg": "Startup provenance", **facts.log_fields()}
        )
        rendered = [
            PlainFormatter(_PLAIN_FORMAT, _DATE_FORMAT).format(record),
            JsonFormatter().format(record),
        ]
        assert len(rendered) == 2
        for line in rendered:
            assert secret not in line
            assert "example.invalid" not in line
        assert secret not in provenance.refusal_message(facts)


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


def test_git_inside_checkout_root_is_untrusted(tmp_path: Path) -> None:
    """Test 19b. A git under the checkout's top, found from a subdirectory, is untrusted.

    The cwd check cannot see it, because the cwd is a subdirectory and the
    binary is beside it. Once git names the checkout's top, the result is
    discarded.
    """
    root = _checkout(tmp_path)
    sub = root / "sub"
    sub.mkdir()
    dist_info, init = _site(tmp_path / "site", direct_url=_vcs())
    git = _clean_git(root)

    facts = collect_provenance(
        root / "config.yaml",
        _SHA,
        cwd=sub,
        module_file=init,
        find_distribution=_finder(dist_info),
        resolve=lambda _cwd: root / "tools" / "git.exe",
        runner=git,
    )

    assert facts.checkout_root is None
    assert facts.checkout_dirty is None
    assert "git_untrusted_path" in facts.unknown_reasons
    assert git.calls == [["rev-parse", "--show-toplevel", "HEAD"]]


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


def test_status_args_force_untracked_and_disable_fsmonitor(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Test 21. ``status`` overrides ``showUntrackedFiles``; every call disables fsmonitor.

    MUTATION m15: drop ``--untracked-files=normal``. A repository configured
    with ``status.showUntrackedFiles=no`` would then hide untracked files.
    """
    root = _checkout(tmp_path)
    git = _clean_git(root)
    _collect(tmp_path, git=git)

    assert len(git.calls) == 3
    assert git.calls[1] == ["status", "--porcelain=v1", "-z", "--untracked-files=normal"]

    spy = _RunSpy()
    _patch_run(monkeypatch, spy)
    run_git(tmp_path / "git.exe", ["status"], tmp_path)
    assert len(spy.calls) == 1
    assert spy.calls[0][0][1:4] == ["-c", "core.fsmonitor=false", "--no-optional-locks"]


@pytest.mark.parametrize("case", ["outside", "untracked", "unparseable"])
def test_config_outside_checkout_or_untracked_refuses(tmp_path: Path, case: str) -> None:
    """Test 22. A config the checkout does not track refuses.

    Outside the checkout no ``ls-files`` call is made at all.
    """
    root = _checkout(tmp_path)
    git = _clean_git(root)
    config = root / "config.yaml"
    if case == "outside":
        config = tmp_path / "elsewhere" / "config.yaml"
        config.parent.mkdir()
        config.write_text("mode: testnet\n", encoding="utf-8")
    elif case == "untracked":
        git.outcomes["ls-files"] = GitOutput(b"")
    else:
        git.outcomes["ls-files"] = GitOutput(b"other.yaml\0")

    facts = _collect(tmp_path, git=git, config_path=config)

    assert facts.accepted is False
    if case == "unparseable":
        assert facts.config_tracked is None
        assert "ls_files_unparseable" in facts.unknown_reasons
        assert "config_tracked=unknown" in facts.refusal_reasons
    else:
        assert facts.config_tracked is False
        assert "config_tracked=false" in facts.refusal_reasons
    if case == "outside":
        assert [call[0] for call in git.calls] == ["rev-parse", "status"]


@pytest.mark.parametrize(
    ("field", "value", "reason"),
    [
        ("install_kind", InstallKind.UNKNOWN, "install_kind=unknown"),
        ("code_intact", None, "code_intact=unknown"),
        ("dirty_paths", None, "checkout_dirty=unknown"),
        ("commits_agree", None, "commits_agree=unknown"),
        ("config_tracked", None, "config_tracked=unknown"),
        ("config_sha256", None, "config_sha256=unknown"),
    ],
)
def test_every_unknown_refuses(field: str, value: object, reason: str) -> None:
    """Test 23. Each field, alone unknown, refuses -- and says which.

    MUTATION m18: accept an unknown. The field's own case passes.
    """
    baseline = _accepted_facts()
    assert baseline.accepted is True

    facts = dataclasses.replace(baseline, **{field: value})

    assert facts.accepted is False
    assert facts.refusal_reasons == (reason,)
    assert facts.log_fields()["verdict"] == "refused"


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


# --------------------------------------------------------------------------
# End to end, with the real git
# --------------------------------------------------------------------------
def _git(repo: Path, *args: str) -> str:
    env = child_environment(os.environ)
    completed = subprocess.run(
        ["git", "-c", "user.name=probe", "-c", "user.email=probe@invalid", *args],
        cwd=repo,
        env=env,
        capture_output=True,
        check=True,
        timeout=60,
    )
    return completed.stdout.decode("utf-8").strip()


@pytest.mark.skipif(shutil.which("git") is None, reason="git is not installed")
def test_real_git_temporary_repository_end_to_end(tmp_path: Path) -> None:
    """Test 15. The real resolver and runner against a real repository.

    The repository sets ``status.showUntrackedFiles=no``, the trap
    ``M5l-019`` names, so an untracked file is visible only because the call
    overrides it. Collected from the top and from a subdirectory, because the
    config pathspec is anchored at the top whatever the working directory.
    """
    repo = tmp_path / "checkout"
    (repo / "sub").mkdir(parents=True)
    _git(repo, "init", "-q")
    _git(repo, "config", "status.showUntrackedFiles", "no")
    config = repo / "config.yaml"
    config.write_bytes(b"mode: testnet\n")
    (repo / "sub" / "keep.txt").write_bytes(b"keep\n")
    _git(repo, "add", "config.yaml", "sub/keep.txt")
    _git(repo, "commit", "-q", "-m", "init")
    commit = _git(repo, "rev-parse", "HEAD")
    dist_info, init = _site(tmp_path / "site", direct_url=_vcs(commit))

    def collect(cwd: Path) -> Provenance:
        return collect_provenance(
            config.resolve(),
            _SHA,
            cwd=cwd,
            module_file=init,
            find_distribution=_finder(dist_info),
        )

    for cwd in (repo, repo / "sub"):
        clean = collect(cwd)
        assert clean.refusal_reasons == (), clean.unknown_reasons
        assert clean.checkout_commit == commit
        assert clean.checkout_root is not None
        assert os.path.samefile(clean.checkout_root, repo)
        assert clean.config_tracked is True

    config.write_bytes(b"mode: paper\n")
    (repo / "notes.txt").write_bytes(b"untracked\n")
    dirty = collect(repo)

    assert dirty.checkout_dirty is True
    assert dirty.dirty_paths is not None
    assert set(dirty.dirty_paths) == {"config.yaml", "notes.txt"}
    assert "checkout_dirty=true" in dirty.refusal_reasons
