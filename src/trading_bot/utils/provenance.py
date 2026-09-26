"""Startup provenance: which code runs, from which checkout, on which config.

``CLAUDE.md``'s deployment doctrine rules that the bot is never launched from a
development working tree, and that every boot logs the commit and dirty state
of what it runs. This module gathers the facts for that one boot line.

**THIS PART READS THE LAUNCH CHECKOUT**, from git in the working directory.
The config, the secrets, the store and the lock are all resolved against the
cwd (``M5l-007``), so the checkout the bot is launched from decides its
behaviour even when the code was installed from elsewhere.

**EVERY FAILURE IS UNKNOWN, AND UNKNOWN IS NEVER CLEAN.** A git call returns a
tagged value, :class:`GitOutput` or :class:`GitUnknown`, and ``dirty_paths`` is
empty only from a :class:`GitOutput` status read with zero entries.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

__all__ = [
    "GIT_TIMEOUT_S",
    "CheckoutFacts",
    "GitOutcome",
    "GitOutput",
    "GitUnknown",
    "child_environment",
    "collect_checkout",
    "parse_porcelain",
    "resolve_git",
    "run_git",
]

GIT_TIMEOUT_S = 5.0
_GIT_PREFIX: tuple[str, ...] = ("-c", "core.fsmonitor=false", "--no-optional-locks")
_COMMIT = re.compile(r"[0-9a-f]{40}")


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


@dataclass(frozen=True)
class CheckoutFacts:
    """What git reports about the launch directory's checkout."""

    root: Path | None
    commit: str | None
    dirty_paths: tuple[str, ...] | None
    config_tracked: bool | None
    reasons: tuple[str, ...]


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
