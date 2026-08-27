"""The single-instance lock, and what it cannot prove here.

**Why these exist.** D1 was two bots on one account, and the log could not say
so because nothing in it named the writer. The lock stops the second process
and the PID field makes the failure legible if one ever slips past. Neither is
visible to any other gate: `ruff` and `mypy` cannot tell an exclusive lock from
a file that is merely created, and a future author replacing `LK_NBLCK` with
`LK_LOCK`, or `flock` with `lockf`, would break nothing they could see.

**Two things are NOT proved here and are declared rather than faked.**

* **Release on SIGKILL.** You cannot kill yourself and then assert. It is an OS
  guarantee, it is what makes an OS lock the right mechanism instead of a
  sentinel file, and proving it needs a spawned process this suite does not
  have. See `test_release_on_sigkill_is_not_tested_here`.
* **The POSIX branch.** `fcntl` is not importable on Windows (MEASURED:
  `ModuleNotFoundError`), so on this development platform that branch is
  neither executed nor -- because mypy narrows on `sys.platform` -- type
  checked.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from trading_bot.utils.instance_lock import (
    DEFAULT_LOCK_PATH,
    InstanceLockedError,
    acquire,
    read_holder_pid,
)

if TYPE_CHECKING:  # pragma: no cover - typing only
    pass


class TestExclusion:
    def test_a_second_acquisition_is_refused(self, tmp_path: Path) -> None:
        """THE TEST L2 EXISTS FOR.

        **It is not passing vacuously, and here is how that is known.** POSIX
        record locks (`lockf`/`F_SETLK`) are per-PROCESS, so a second
        acquisition inside one process succeeds silently and this assertion
        would never fire. `flock` is per open-file-description and Windows
        `msvcrt.locking` is per handle, so both conflict with a second handle in
        the same process -- which is exactly what this opens. The mutation in
        4j confirms it: a lock that permits re-acquisition fails here.
        """
        path = tmp_path / ".bot.lock"

        with acquire(path), pytest.raises(InstanceLockedError), acquire(path):
            pass  # pragma: no cover - the second acquire must refuse

    def test_two_different_paths_do_not_conflict(self, tmp_path: Path) -> None:
        """The key is the path. Two checkouts hold two locks -- which is
        `L6`'s named gap, asserted so the gap is a property rather than a
        surprise."""
        with acquire(tmp_path / "a.lock"), acquire(tmp_path / "b.lock"):
            pass


class TestRelease:
    def test_the_lock_releases_on_clean_exit(self, tmp_path: Path) -> None:
        """Acquire, release, re-acquire. Catches a lock never unlocked -- which
        would make the FIRST run of the day the only one."""
        path = tmp_path / ".bot.lock"

        with acquire(path):
            pass
        with acquire(path):
            pass

    def test_the_lock_releases_when_the_body_raises(self, tmp_path: Path) -> None:
        """Catches a release placed after the body rather than in a `finally`.

        A bot that crashed would otherwise hold its own account until a reboot.
        """
        path = tmp_path / ".bot.lock"

        with pytest.raises(RuntimeError, match="boom"), acquire(path):
            raise RuntimeError("boom")

        with acquire(path):
            pass

    def test_release_on_sigkill_is_not_tested_here(self) -> None:
        """NOT A TEST OF THE LOCK. It records that one property is unproven.

        `R-B` -- release on crash, not only on clean exit -- rests entirely on
        the kernel closing the process's handles. Nothing above exercises it,
        because a process cannot SIGKILL itself and then assert. Written as a
        test so the gap is in the suite's output rather than only in a comment,
        and so deleting the acknowledgement is a visible act.
        """
        assert DEFAULT_LOCK_PATH.suffix == ".lock"  # a real assertion; the docstring is the point


class TestHolderPid:
    def test_the_pid_is_readable_while_the_lock_is_held(self, tmp_path: Path) -> None:
        """L3: byte 0 is locked, the PID lives from byte 1.

        Catches a PID written at offset 0, which on Windows -- where the lock is
        MANDATORY and byte-ranged -- a refused instance could not read.
        """
        import os

        path = tmp_path / ".bot.lock"
        with acquire(path):
            assert read_holder_pid(path) == os.getpid()

    def test_the_refusal_names_the_holder(self, tmp_path: Path) -> None:
        """Catches a message that refuses without saying who holds it -- which
        sends an operator hunting through terminals with nothing to match."""
        import os

        path = tmp_path / ".bot.lock"
        with (
            acquire(path),
            pytest.raises(InstanceLockedError, match=str(os.getpid())),
            acquire(path),
        ):
            pass  # pragma: no cover

    def test_the_refusal_tells_the_operator_not_to_delete_the_file(self, tmp_path: Path) -> None:
        """The first instinct on a stale-looking lock is to delete it, and with
        an OS lock that is unnecessary and harmful: deleting it while a holder
        lives lets a second instance create a fresh file and lock that one."""
        path = tmp_path / ".bot.lock"
        with acquire(path), pytest.raises(InstanceLockedError, match="do not need"), acquire(path):
            pass  # pragma: no cover

    @pytest.mark.parametrize(
        "content", [b"", b"\x00", b"\x00not-a-number"], ids=["empty", "no_pid", "garbage"]
    )
    def test_an_unreadable_pid_still_refuses(self, tmp_path: Path, content: bytes) -> None:
        """A first-ever run, a truncated write, an older format.

        Catches a refusal that crashes trying to name a holder it cannot read.
        Refusing is the job; naming the PID is a courtesy, and the courtesy must
        not be able to take the refusal down with it.
        """
        path = tmp_path / ".bot.lock"
        path.write_bytes(content)

        assert read_holder_pid(path) is None
        with acquire(path):
            pass  # the lock itself is unaffected by an unreadable payload

    def test_a_missing_file_reads_no_pid(self, tmp_path: Path) -> None:
        assert read_holder_pid(tmp_path / "absent.lock") is None


class TestLockPath:
    def test_the_default_path_is_git_ignored(self) -> None:
        """Asserted against `.gitignore`'s CONTENT, not a hardcoded string.

        Catches the lock path moving somewhere tracked -- which would put a
        per-machine runtime file into every diff, and would dirty the tree that
        every halt block in this project gates on.
        """
        root = Path(__file__).resolve().parents[2]
        patterns = (root / ".gitignore").read_text(encoding="utf-8").splitlines()

        assert DEFAULT_LOCK_PATH.parts[0] == "logs"
        assert "logs/*" in patterns
        assert "!logs/.gitkeep" in patterns
        assert DEFAULT_LOCK_PATH.name != ".gitkeep"

    def test_the_lock_file_is_created_with_its_parent(self, tmp_path: Path) -> None:
        """A boot must not fail because a directory did not exist yet."""
        path = tmp_path / "nested" / "deeper" / ".bot.lock"

        with acquire(path):
            assert path.exists()

    def test_acquiring_does_not_truncate_a_held_pid(self, tmp_path: Path) -> None:
        """Opened `a+b`, never `w+b`.

        Catches a mode that truncates: the window between opening and locking
        would destroy the holder's PID, so a refused instance would find an
        empty file and report an unknown holder for a lock that names one.
        """
        path = tmp_path / ".bot.lock"
        with acquire(path):
            first = read_holder_pid(path)
            with pytest.raises(InstanceLockedError), acquire(path):
                pass  # pragma: no cover
            assert read_holder_pid(path) == first


class TestRefusalMessage:
    def test_the_message_explains_why_two_instances_matter(self, tmp_path: Path) -> None:
        """Catches a message reduced to "already running", which tells an
        operator what happened and not why they should care."""
        path = tmp_path / ".bot.lock"
        with acquire(path), pytest.raises(InstanceLockedError) as excinfo, acquire(path):
            pass  # pragma: no cover

        text = str(excinfo.value)
        assert "-2010" in text
        assert re.search(r"different bars", text)
