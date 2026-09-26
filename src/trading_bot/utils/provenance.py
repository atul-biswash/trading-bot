"""Startup provenance: which code runs, from which checkout, on which config.

``CLAUDE.md``'s deployment doctrine rules that the bot is never launched from a
development working tree, and that every boot logs the commit and dirty state
of what it runs. This module gathers the facts for that one boot line, and
decides whether ``run`` may proceed.

**THREE SOURCES, BECAUSE NO ONE OF THEM IS ENOUGH.**

* *The install*, from the distribution's PEP 610 ``direct_url.json``. A VCS
  install records the commit pip built from a fresh clone, so it names the
  installed code without git at runtime (``M5l-004``). An editable install says
  so (``M5l-003``), which names the doctrine's trap directly.
* *The installed files*, from RECORD. Every ``trading_bot/`` row carrying a
  sha256 is re-hashed, so an installed tree edited after the install does not
  pass for its commit (``M5l-017``). Compiled ``.pyc`` rows carry no hash and
  are not covered (``M5l-025``, accepted: the threat is accidental execution of
  the wrong code, not tampering).
* *The launch checkout*, from git in the working directory. The config, the
  secrets, the store and the lock are all resolved against the cwd
  (``M5l-007``), so the checkout the bot is launched from decides its behaviour
  even when the code was installed from elsewhere.

**EVERY FAILURE IS UNKNOWN, AND UNKNOWN IS NEVER CLEAN.** A git call returns a
tagged value, :class:`GitOutput` or :class:`GitUnknown`, and ``dirty=false`` is
derivable only from a :class:`GitOutput` status read with zero entries. What
this module cannot establish renders as ``unknown`` and refuses.

**NOTHING HERE CAN BE SWITCHED OFF.** No flag, environment variable or config
key reaches :attr:`Provenance.refusal_reasons`.
"""

from __future__ import annotations

import base64
import csv
import hashlib
import json
import os
import platform
import re
import shutil
import subprocess
import tempfile
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from enum import Enum
from importlib import metadata
from pathlib import Path
from typing import Final

import trading_bot

__all__ = [
    "DISTRIBUTION_NAME",
    "GIT_TIMEOUT_S",
    "CheckoutFacts",
    "GitOutcome",
    "GitOutput",
    "GitUnknown",
    "InstallFacts",
    "InstallKind",
    "Provenance",
    "RecordCheck",
    "child_environment",
    "classify_install",
    "collect_checkout",
    "collect_provenance",
    "parse_porcelain",
    "refusal_message",
    "resolve_git",
    "run_git",
    "verify_record",
]

DISTRIBUTION_NAME: Final = "binance-trading-bot"
GIT_TIMEOUT_S = 5.0
_GIT_PREFIX: tuple[str, ...] = ("-c", "core.fsmonitor=false", "--no-optional-locks")
_PACKAGE_INIT: Final = "trading_bot/__init__.py"
_PACKAGE_PREFIX: Final = "trading_bot/"
_COMMIT = re.compile(r"[0-9a-f]{40}")
_DIRTY_PATHS_SHOWN: Final = 20
_JOIN: Final = ";"
_NONE: Final = "none"
_UNKNOWN: Final = "unknown"


class InstallKind(str, Enum):
    """How the distribution was installed, read from its ``direct_url.json``."""

    EDITABLE = "editable"
    VCS = "vcs"
    DIR = "dir"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class GitOutput:
    """A git call that exited 0, with its standard output."""

    stdout: bytes


@dataclass(frozen=True)
class GitUnknown:
    """A git call, or the choice of which git to call, that established nothing."""

    reason: str


GitOutcome = GitOutput | GitUnknown
GitRunner = Callable[[Path, Sequence[str], Path], GitOutcome]
GitResolver = Callable[[Path], Path | GitUnknown]
DistributionFinder = Callable[[str], metadata.Distribution]


@dataclass(frozen=True)
class InstallFacts:
    """The install's kind, its commit when it records one, and why if unknown."""

    kind: InstallKind
    commit: str | None
    reason: str | None
    distribution: metadata.Distribution | None


@dataclass(frozen=True)
class RecordCheck:
    """RECORD verification: ``intact`` is ``None`` when nothing could be checked.

    ``reason`` says why when ``intact`` is ``None``, and for one ``False``: an
    unlisted file, ``unrecorded_file``.
    """

    intact: bool | None
    checked: int
    reason: str | None


@dataclass(frozen=True)
class CheckoutFacts:
    """What git reports about the launch directory's checkout."""

    root: Path | None
    commit: str | None
    dirty_paths: tuple[str, ...] | None
    config_tracked: bool | None
    reasons: tuple[str, ...]


def _tri(value: bool | None) -> str:
    if value is None:
        return _UNKNOWN
    return "true" if value else "false"


def _joined(items: Sequence[str]) -> str:
    return _JOIN.join(items) if items else _NONE


@dataclass(frozen=True)
class Provenance:
    """Every fact the boot line carries, and the verdict they imply.

    ``None`` in any optional field means UNKNOWN, and every unknown refuses:
    see :attr:`refusal_reasons`, the only place a verdict is decided.
    """

    install_kind: InstallKind
    code_commit: str | None
    code_intact: bool | None
    code_files_checked: int
    module_file: Path
    checkout_root: Path | None
    checkout_commit: str | None
    dirty_paths: tuple[str, ...] | None
    commits_agree: bool | None
    config_path: Path | None
    config_sha256: str | None
    config_tracked: bool | None
    python_version: str
    package_version: str
    unknown_reasons: tuple[str, ...]

    @property
    def checkout_dirty(self) -> bool | None:
        """``False`` only from a status read that returned zero entries."""
        if self.dirty_paths is None:
            return None
        return len(self.dirty_paths) > 0

    @property
    def refusal_reasons(self) -> tuple[str, ...]:
        """Why ``run`` may not start; empty exactly when it may.

        Accepted only if ALL hold: a VCS install, its RECORD intact, a clean
        checkout, the checkout at the installed commit, a tracked config, and
        the config's digest known. Each test is against the one accepting
        value, so ``None`` -- unknown -- fails every one of them.
        """
        reasons: list[str] = []
        if self.install_kind is not InstallKind.VCS:
            reasons.append(f"install_kind={self.install_kind.value}")
        if self.code_intact is not True:
            reasons.append(f"code_intact={_tri(self.code_intact)}")
        if self.checkout_dirty is not False:
            reasons.append(f"checkout_dirty={_tri(self.checkout_dirty)}")
        if self.commits_agree is not True:
            reasons.append(f"commits_agree={_tri(self.commits_agree)}")
        if self.config_tracked is not True:
            reasons.append(f"config_tracked={_tri(self.config_tracked)}")
        if self.config_sha256 is None:
            reasons.append(f"config_sha256={_UNKNOWN}")
        return tuple(reasons)

    @property
    def accepted(self) -> bool:
        return not self.refusal_reasons

    def log_fields(self) -> dict[str, str | int | bool]:
        """The boot line's ``extra=`` fields: ``str`` and ``int`` values only.

        A list is joined with a semicolon, which forces no quoting in the plain
        sink where a space does (P55 S0.5): ordinary paths stay readable, and a
        path containing a space quotes the whole field. At most
        ``_DIRTY_PATHS_SHOWN`` dirty paths are named; ``dirty_count`` is the
        total.
        """
        dirty_count: str | int = _UNKNOWN if self.dirty_paths is None else len(self.dirty_paths)
        dirty_paths = (
            _UNKNOWN if self.dirty_paths is None else _joined(self.dirty_paths[:_DIRTY_PATHS_SHOWN])
        )
        return {
            "verdict": "accepted" if self.accepted else "refused",
            "refusal_reasons": _joined(self.refusal_reasons),
            "unknown_reasons": _joined(self.unknown_reasons),
            "install_kind": self.install_kind.value,
            "code_commit": self.code_commit or _UNKNOWN,
            "code_intact": _tri(self.code_intact),
            "code_files_checked": self.code_files_checked,
            "module_file": str(self.module_file),
            "checkout_root": _UNKNOWN if self.checkout_root is None else str(self.checkout_root),
            "checkout_commit": self.checkout_commit or _UNKNOWN,
            "checkout_dirty": _tri(self.checkout_dirty),
            "dirty_count": dirty_count,
            "dirty_paths": dirty_paths,
            "commits_agree": _tri(self.commits_agree),
            "config_path": _UNKNOWN if self.config_path is None else str(self.config_path),
            "config_sha256": self.config_sha256 or _UNKNOWN,
            "config_tracked": _tri(self.config_tracked),
            "python_version": self.python_version,
            "package_version": self.package_version,
        }


def refusal_message(facts: Provenance) -> str:
    """The text ``main`` exits with when ``run`` is refused. ASCII, no trailing newline."""
    return (
        f"FATAL: startup provenance refused: {', '.join(facts.refusal_reasons)}.\n"
        "The bot runs only from a VCS install of a pushed commit, launched from a clean "
        "checkout of that same commit with a tracked config.\n"
        "CLAUDE.md: THE BOT IS NEVER LAUNCHED FROM A DEVELOPMENT WORKING TREE. "
        "Startup refused."
    )


def _within(path: Path, root: Path) -> bool:
    """Whether ``path`` is ``root`` or below it, compared case-insensitively on Windows."""
    child = os.path.normcase(os.path.abspath(path))
    parent = os.path.normcase(os.path.abspath(root))
    try:
        return os.path.commonpath([child, parent]) == parent
    except ValueError:
        return False


def child_environment(environ: Mapping[str, str]) -> dict[str, str]:
    """``environ`` without any ``GIT_*`` variable.

    ``GIT_DIR``, ``GIT_WORK_TREE`` and ``GIT_INDEX_FILE`` would each point git
    at a different repository or index than the directory it is asked about,
    and the answer would describe that instead, with nothing to say so.
    """
    return {key: value for key, value in environ.items() if not key.upper().startswith("GIT_")}


def run_git(git: Path, args: Sequence[str], cwd: Path) -> GitOutcome:
    """Run one git call, bounded, and return a tagged result. Never raises.

    **OUTPUT GOES TO TEMPORARY FILES, NOT PIPES**, because a pipe does not
    close while any grandchild still holds it, and on Windows
    ``subprocess.run`` waits for that close after killing a timed-out child.
    Measured at P55 S0.2: ``timeout=1`` returned after 30.14 s through pipes
    and after 1.02 s through files (``M5l-014``). A temporary file needs no
    close from anyone else.

    **BOUNDED, SO STARTUP CANNOT HANG ON GIT**: ``GIT_TIMEOUT_S`` per call,
    and the boot makes at most three calls.

    **EVERY CALL IS PREFIXED** with ``-c core.fsmonitor=false``, so ``status``
    starts no monitor daemon and runs no hook (``M5l-020``), and with
    ``--no-optional-locks``, so it does not rewrite the checkout's index
    (``M5l-015``): a boot check must not write to the tree it describes.
    """
    command = [str(git), *_GIT_PREFIX, *args]
    try:
        with tempfile.TemporaryFile() as out, tempfile.TemporaryFile() as err:
            completed = subprocess.run(
                command,
                shell=False,
                cwd=cwd,
                stdin=subprocess.DEVNULL,
                stdout=out,
                stderr=err,
                timeout=GIT_TIMEOUT_S,
                env=child_environment(os.environ),
                check=False,
            )
            out.seek(0)
            stdout = out.read()
    except FileNotFoundError:
        return GitUnknown("git_not_found")
    except subprocess.TimeoutExpired:
        return GitUnknown("git_timeout")
    except OSError:
        return GitUnknown("os_error")
    if completed.returncode != 0:
        return GitUnknown(f"git_exit_{completed.returncode}")
    return GitOutput(stdout)


def resolve_git(
    cwd: Path,
    *,
    which: Callable[[str], str | None] = shutil.which,
    windows: bool = os.name == "nt",
) -> Path | GitUnknown:
    """The git executable to trust, or why none is trusted.

    ALL of these must hold: ``which`` finds one; what it returns is already
    absolute; it lies outside the working directory; and on Windows its suffix
    is ``.exe``. The checkout half of "outside" is checked by
    :func:`collect_checkout`, once git has said where the checkout is.

    **Absolute as RETURNED, not after resolving.** On Windows the working
    directory is searched first unless ``NoDefaultCurrentDirectoryInExePath``
    is set, and what comes back is relative -- ``.\\git.EXE`` (P55 S0.1,
    ``M5l-018``). Resolving it first would turn a planted binary into an
    absolute path that looks like any other.

    **``.exe`` on Windows**, because a ``.cmd`` or ``.bat`` is run through
    ``cmd.exe``, which re-parses the arguments.
    """
    found = which("git")
    if found is None:
        return GitUnknown("git_not_found")
    candidate = Path(found)
    if not candidate.is_absolute():
        return GitUnknown("git_untrusted_path")
    resolved = candidate.resolve()
    if _within(resolved, cwd.resolve()):
        return GitUnknown("git_untrusted_path")
    if windows and resolved.suffix.lower() != ".exe":
        return GitUnknown("git_untrusted_path")
    return resolved


def parse_porcelain(stdout: bytes) -> tuple[str, ...] | None:
    """Paths from ``git status --porcelain=v1 -z``, or ``None`` if malformed.

    Each entry is ``XY PATH``. A rename or copy is followed by one more field,
    the original path, which is consumed and not reported: the entry's own
    path is the one in the tree now.
    """
    fields = stdout.split(b"\0")
    if fields[-1] == b"":
        fields.pop()
    paths: list[str] = []
    index = 0
    while index < len(fields):
        entry = fields[index]
        index += 1
        if len(entry) < 4 or entry[2:3] != b" ":
            return None
        status = entry[:2]
        try:
            paths.append(entry[3:].decode("utf-8"))
        except UnicodeDecodeError:
            return None
        if b"R" in status or b"C" in status:
            if index >= len(fields):
                return None
            index += 1
    return tuple(paths)


def classify_install(module_file: Path, find_distribution: DistributionFinder) -> InstallFacts:
    """Classify the install from ``direct_url.json``; never reads its ``url``.

    **The ``url`` is never read**, because a VCS URL can carry credentials in
    ``user:token@`` form and nothing read is at risk of being logged.

    **THE SHADOW GUARD COVERS EVERY KIND BUT EDITABLE.** The distribution
    found by name need not be the code imported: a copy of ``trading_bot``
    earlier on ``sys.path`` imports instead while the metadata still names the
    installed commit (``M5l-016``). So the file the distribution says it
    installed must be the file imported, by ``os.path.samefile`` -- the same
    file, not the same spelling. An editable install is exempt because its
    files never live where the distribution points (``M5l-023``); it is
    refused by its kind, so the exemption admits nothing.
    """
    unknown = InstallKind.UNKNOWN
    try:
        dist = find_distribution(DISTRIBUTION_NAME)
    except metadata.PackageNotFoundError:
        return InstallFacts(unknown, None, "no_distribution", None)
    try:
        raw = dist.read_text("direct_url.json")
    except OSError:
        return InstallFacts(unknown, None, "direct_url_unreadable", dist)
    if raw is None:
        return InstallFacts(unknown, None, "no_direct_url", dist)
    try:
        direct = json.loads(raw)
    except ValueError:
        return InstallFacts(unknown, None, "direct_url_unreadable", dist)
    if not isinstance(direct, dict):
        return InstallFacts(unknown, None, "direct_url_unreadable", dist)
    dir_info = direct.get("dir_info")
    if isinstance(dir_info, dict) and dir_info.get("editable") is True:
        return InstallFacts(InstallKind.EDITABLE, None, None, dist)
    try:
        same = os.path.samefile(str(dist.locate_file(_PACKAGE_INIT)), module_file)
    except OSError:
        return InstallFacts(unknown, None, "shadow_check_failed", dist)
    if not same:
        return InstallFacts(unknown, None, "shadowed", dist)
    vcs_info = direct.get("vcs_info")
    if isinstance(vcs_info, dict):
        commit = vcs_info.get("commit_id")
        if (
            vcs_info.get("vcs") == "git"
            and isinstance(commit, str)
            and _COMMIT.fullmatch(commit) is not None
        ):
            return InstallFacts(InstallKind.VCS, commit, None, dist)
        return InstallFacts(unknown, None, "vcs_commit_invalid", dist)
    if isinstance(dir_info, dict):
        return InstallFacts(InstallKind.DIR, None, None, dist)
    return InstallFacts(unknown, None, "direct_url_unrecognised", dist)


def _record_digest(data: bytes) -> str:
    """RECORD's hash encoding: urlsafe base64 of the sha256 digest, unpadded."""
    return base64.urlsafe_b64encode(hashlib.sha256(data).digest()).rstrip(b"=").decode("ascii")


def _unrecorded_files(dist: metadata.Distribution, recorded: set[str]) -> list[str]:
    """Every ``.py`` under the installed package that RECORD has no row for."""
    package = Path(str(dist.locate_file(_PACKAGE_PREFIX.rstrip("/"))))
    unrecorded: list[str] = []
    for path in package.rglob("*.py"):
        relative = path.relative_to(package)
        if "__pycache__" in relative.parts or not path.is_file():
            continue
        name = f"{_PACKAGE_PREFIX}{relative.as_posix()}"
        if name not in recorded:
            unrecorded.append(name)
    return unrecorded


def verify_record(dist: metadata.Distribution) -> RecordCheck:
    """Re-hash every ``trading_bot/`` RECORD row that carries a sha256.

    Zero such rows is unknown, not intact: a check that examined nothing has
    established nothing. A missing file or a mismatch is ``False``.

    **RECORD IS READ HERE, NOT THROUGH ``Distribution.files``**, because on
    Python 3.12 that property filters its rows through ``skip_missing_files``:
    a file deleted after the install leaves the list silently, and a check
    built on it reports intact (``M5l-026``).

    **AND A FILE RECORD DOES NOT LIST IS NOT INTACT EITHER.** Checking the
    listed rows sees an edit and a deletion but never an ADDITION: a module
    dropped into the installed package after the install is importable and
    unlisted (``M5l-028``). So every ``.py`` under the installed
    ``trading_bot/`` must have a row, hashed or not, or the check is ``False``
    with reason ``unrecorded_file``. ``__pycache__`` and ``.pyc`` are out of
    scope, as RECORD's ``.pyc`` rows are (``M5l-025``).
    """
    try:
        text = dist.read_text("RECORD")
    except OSError:
        text = None
    if text is None:
        return RecordCheck(None, 0, "record_missing")
    checked = 0
    recorded: set[str] = set()
    for row in csv.reader(text.splitlines()):
        if len(row) < 2 or not row[0].startswith(_PACKAGE_PREFIX):
            continue
        recorded.add(row[0])
        mode, _, value = row[1].partition("=")
        if mode != "sha256" or not value:
            continue
        checked += 1
        try:
            data = Path(str(dist.locate_file(row[0]))).read_bytes()
        except OSError:
            return RecordCheck(False, checked, None)
        if _record_digest(data) != value:
            return RecordCheck(False, checked, None)
    if _unrecorded_files(dist, recorded):
        return RecordCheck(False, checked, "unrecorded_file")
    if checked == 0:
        return RecordCheck(None, 0, "record_unhashed")
    return RecordCheck(True, checked, None)


def _parse_rev_parse(stdout: bytes) -> tuple[Path, str] | None:
    try:
        lines = stdout.decode("utf-8").splitlines()
    except UnicodeDecodeError:
        return None
    if len(lines) != 2 or _COMMIT.fullmatch(lines[1]) is None:
        return None
    return Path(lines[0]), lines[1]


def _config_tracked(
    git: Path, cwd: Path, root: Path, config_path: Path, runner: GitRunner
) -> tuple[bool | None, str | None]:
    """Whether git tracks the config, asked with a pathspec anchored at the top.

    Outside the checkout it is not tracked by it, and no call is made. Inside,
    ``:(top,literal)`` anchors the path at the checkout's top whatever the
    working directory, and ``--full-name`` prints it the same way, so the
    answer is compared byte for byte: empty is untracked, the path is tracked.
    """
    if not _within(config_path, root):
        return False, None
    relative = Path(os.path.relpath(config_path, root)).as_posix()
    outcome = runner(git, ["ls-files", "-z", "--full-name", "--", f":(top,literal){relative}"], cwd)
    if isinstance(outcome, GitUnknown):
        return None, outcome.reason
    if outcome.stdout == b"":
        return False, None
    if outcome.stdout == relative.encode("utf-8") + b"\0":
        return True, None
    return None, "ls_files_unparseable"


def collect_checkout(
    cwd: Path,
    config_path: Path | None,
    *,
    resolve: GitResolver,
    runner: GitRunner,
) -> CheckoutFacts:
    """At most three git calls against ``cwd``; every failure is unknown."""
    git = resolve(cwd)
    if isinstance(git, GitUnknown):
        return CheckoutFacts(None, None, None, None, (git.reason,))
    head = runner(git, ["rev-parse", "--show-toplevel", "HEAD"], cwd)
    if isinstance(head, GitUnknown):
        return CheckoutFacts(None, None, None, None, (head.reason,))
    parsed = _parse_rev_parse(head.stdout)
    if parsed is None:
        return CheckoutFacts(None, None, None, None, ("rev_parse_unparseable",))
    root, commit = parsed
    if _within(git, root.resolve()):
        return CheckoutFacts(None, None, None, None, ("git_untrusted_path",))
    reasons: list[str] = []
    status = runner(git, ["status", "--porcelain=v1", "-z", "--untracked-files=normal"], cwd)
    dirty_paths: tuple[str, ...] | None
    if isinstance(status, GitUnknown):
        dirty_paths = None
        reasons.append(status.reason)
    else:
        dirty_paths = parse_porcelain(status.stdout)
        if dirty_paths is None:
            reasons.append("status_unparseable")
    tracked: bool | None
    if config_path is None:
        tracked = None
        reasons.append("config_path_unknown")
    else:
        tracked, reason = _config_tracked(git, cwd, root, config_path, runner)
        if reason is not None:
            reasons.append(reason)
    return CheckoutFacts(root, commit, dirty_paths, tracked, tuple(reasons))


def _agree(code_commit: str | None, checkout_commit: str | None) -> bool | None:
    if code_commit is None or checkout_commit is None:
        return None
    return code_commit == checkout_commit


def collect_provenance(
    config_path: Path | None,
    config_sha256: str | None,
    *,
    cwd: Path | None = None,
    module_file: Path | None = None,
    find_distribution: DistributionFinder = metadata.distribution,
    resolve: GitResolver = resolve_git,
    runner: GitRunner = run_git,
) -> Provenance:
    """Gather every fact the boot line carries. Never raises for an environment it meets."""
    launch = Path.cwd() if cwd is None else cwd
    module = Path(trading_bot.__file__) if module_file is None else module_file
    install = classify_install(module, find_distribution)
    reasons: list[str] = []
    if install.reason is not None:
        reasons.append(install.reason)
    record = RecordCheck(None, 0, None)
    if install.kind is InstallKind.VCS and install.distribution is not None:
        record = verify_record(install.distribution)
        if record.reason is not None:
            reasons.append(record.reason)
    checkout = collect_checkout(launch, config_path, resolve=resolve, runner=runner)
    reasons.extend(checkout.reasons)
    if config_sha256 is None:
        reasons.append("config_sha256_unknown")
    return Provenance(
        install_kind=install.kind,
        code_commit=install.commit,
        code_intact=record.intact,
        code_files_checked=record.checked,
        module_file=module.resolve(),
        checkout_root=checkout.root,
        checkout_commit=checkout.commit,
        dirty_paths=checkout.dirty_paths,
        commits_agree=_agree(install.commit, checkout.commit),
        config_path=config_path,
        config_sha256=config_sha256,
        config_tracked=checkout.config_tracked,
        python_version=platform.python_version(),
        package_version=trading_bot.__version__,
        unknown_reasons=tuple(dict.fromkeys(reasons)),
    )
