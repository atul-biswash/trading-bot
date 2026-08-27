"""One running bot per checkout, enforced by an OS-level advisory file lock.

**The failure this exists to prevent, measured.** On 2026-08-27 two processes
ran against one Testnet account, nine minutes apart, both writing to one log
file with nothing in it saying which was which. Both received the same closed
bar, both signalled, both dispatched, and only the venue's ``-2010 'Duplicate
order sent.'`` stopped a second order list existing -- because both derived the
SAME client order id from the same ``entry_bar_time``. **That protection is
accidental and does not generalise:** two processes signalling one bar apart
derive different ids, and the venue accepts both.

**Why an OS lock rather than a sentinel file.** The lock must release when the
holder DIES, not only when it exits cleanly. A plain file left behind by a
``SIGKILL`` blocks every later start until someone deletes it, and the deletion
habit that then forms is precisely what makes a sentinel useless. Both platform
mechanisms here are released by the kernel when the process's handles are
closed, however it ended.

**The key is the PATH, and that is a real limitation rather than an oversight.**
See :func:`acquire`.
"""

from __future__ import annotations

import os
import sys
from contextlib import contextmanager, suppress
from pathlib import Path
from typing import TYPE_CHECKING

from trading_bot.core.exceptions import ConfigError

if TYPE_CHECKING:  # pragma: no cover - typing only
    from collections.abc import Iterator
    from io import BufferedRandom

__all__ = ["DEFAULT_LOCK_PATH", "acquire", "read_holder_pid"]

#: Under ``logs/``, which ``.gitignore`` already covers with ``logs/*`` and
#: ``!logs/.gitkeep``, and which ``setup_logging`` guarantees exists by the time
#: a boot reaches this module. Using ``data/`` would work identically; ``logs/``
#: wins only because it is created earlier.
DEFAULT_LOCK_PATH = Path("logs/.bot.lock")

#: **Byte 0 is locked; the PID is written from byte 1.** On Windows the lock is
#: MANDATORY and byte-ranged -- other processes' reads of the locked range fail
#: -- so a refused instance could not read a PID stored at offset 0. Splitting
#: them is what lets the refusal name its holder.
_LOCK_OFFSET = 0
_LOCK_LENGTH = 1
_PID_OFFSET = 1

#: **``sys.platform == "win32"`` is written INLINE at every branch, never
#: hoisted into a constant, and that is a type-checking requirement rather than
#: a style choice.** mypy narrows on a literal ``sys.platform`` comparison and
#: treats the other branch as unreachable; it does NOT narrow on a boolean
#: variable holding the same result. Hoisted, the POSIX branch is type-checked
#: on Windows against an empty ``fcntl`` stub and reports
#: ``Module has no attribute "flock"``.
#:
#: The alternative -- ``# type: ignore[attr-defined]`` -- is worse: this project
#: sets ``warn_unused_ignores``, so an ignore that is needed on Windows becomes
#: an ERROR on POSIX where the attribute exists. A platform-conditional
#: suppression cannot be correct on both platforms at once.
#:
#: **The cost, stated: on Windows the POSIX branch is neither executed nor
#: type-checked.** Nothing in this repository verifies it.


class InstanceLockedError(ConfigError):
    """Another process on this checkout already holds the instance lock.

    A :class:`ConfigError` rather than a new family, so it joins the five
    existing boot refusals and ``main.py`` maps it to exit code 2 through the
    ``TradingBotError`` handler it already has. **No second exit convention is
    introduced**; see :func:`acquire` on why the ruling's "Exit 1" is satisfied
    by the codebase's existing mapping rather than by a bare ``sys.exit``.
    """


def _try_lock(handle: BufferedRandom) -> bool:
    """Take an exclusive, non-blocking lock on byte 0. ``False`` if held.

    **``LK_NBLCK``, never ``LK_LOCK``.** ``LK_LOCK`` retries for roughly ten
    seconds before raising, so a refusal would present to an operator as a hang.
    **``flock``, never ``lockf``.** POSIX record locks are per-PROCESS, so a
    second acquisition inside one process succeeds silently -- which would make
    the double-acquire test pass while proving nothing.

    **The POSIX branch cannot execute on this development platform.** ``fcntl``
    is not importable on Windows (MEASURED: ``ModuleNotFoundError``), so nothing
    here exercises it and no test in this repository proves it. It is written to
    the documented ``flock`` contract and marked as unexercised rather than
    presented as covered.
    """
    if sys.platform == "win32":
        import msvcrt

        handle.seek(_LOCK_OFFSET)
        try:
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, _LOCK_LENGTH)
        except OSError:
            return False
        return True

    import fcntl  # pragma: no cover - POSIX only; unreachable on the dev platform

    try:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        return False
    return True


def _unlock(handle: BufferedRandom) -> None:
    """Release byte 0. Best-effort: the OS releases it on close regardless."""
    if sys.platform == "win32":
        import msvcrt

        handle.seek(_LOCK_OFFSET)
        # Suppressed: the OS releases on close regardless, so an already-released
        # region is not a failure worth propagating out of a teardown path.
        with suppress(OSError):
            msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, _LOCK_LENGTH)
        return

    import fcntl  # pragma: no cover - POSIX only; unreachable on the dev platform

    with suppress(OSError):
        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def read_holder_pid(path: Path) -> int | None:
    """The PID written at byte 1, or ``None`` when it cannot be read.

    **``None`` is a normal answer, not a failure.** The file may be brand new,
    truncated by a crash mid-write, written by an older format, or unreadable
    for a reason that has nothing to do with the holder. A refusal must still
    refuse in every one of those cases -- it simply cannot name a PID -- so this
    never raises and the caller never depends on it.

    **It SEEKS past byte 0 and never reads it**, which is the whole reason the
    PID lives at offset 1. On Windows the lock is MANDATORY, so a read covering
    the locked byte FAILS -- and a naive ``path.read_bytes()`` covers it,
    returning ``None`` for every held lock and leaving the refusal permanently
    unable to name its holder. Not hypothetical: this function was written that
    way first, and ``test_the_refusal_names_the_holder`` caught it.
    """
    try:
        with open(path, "rb") as handle:
            handle.seek(_PID_OFFSET)
            raw = handle.read().strip()
    except OSError:
        return None
    try:
        return int(raw)
    except ValueError:
        return None


@contextmanager
def acquire(path: Path = DEFAULT_LOCK_PATH) -> Iterator[None]:
    """Hold the single-instance lock for the duration of the block.

    **Keyed on the PATH, deliberately, and here is what that fails to catch.**
    Nothing identifies the ACCOUNT without either reading a secret or making a
    venue call, and the lock must be taken before any client exists. So the key
    is this checkout's lock file, and two cases fall outside it:

    * **Two checkouts, one account** -- both acquire their own lock and both
      run. NOT CAUGHT. The fix would be a truncated hash of the API key in the
      filename; it is deliberately not done, because it puts secret-derived
      material on disk to buy one case a disciplined operator does not hit.
    * **Two accounts, one checkout** -- the second is refused although it is
      legitimate. A FALSE REFUSAL, and the cheaper error of the two.

    Neither is closed here. Both are named so the next reader meets the gap
    rather than an apparently complete guarantee.

    **Release on crash is an OS GUARANTEE and is NOT TESTED IN THIS
    REPOSITORY.** The ``finally`` below covers a clean exit and an exception; a
    ``SIGKILL`` runs none of it, and the lock is released only because the
    kernel closes the process's handles. That property is what makes an OS lock
    the right mechanism instead of a sentinel file, and proving it needs a
    spawned process that this suite deliberately does not have -- you cannot
    kill yourself and then assert. It is documented rather than covered.

    :raises InstanceLockedError: another process holds it.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    # `a+b` creates without truncating: truncation would destroy the holder's
    # PID in the window before the lock is even attempted.
    handle = open(path, "a+b")  # noqa: SIM115 - released in the finally below
    try:
        if not _try_lock(handle):
            raise InstanceLockedError(_refusal_message(path, read_holder_pid(path)))
        handle.seek(_PID_OFFSET)
        handle.truncate(_PID_OFFSET)
        handle.write(str(os.getpid()).encode("ascii"))
        handle.flush()
        try:
            yield
        finally:
            _unlock(handle)
    finally:
        handle.close()


def _refusal_message(path: Path, holder: int | None) -> str:
    """What an operator who has forgotten a terminal needs, in one message.

    The closing paragraph is not politeness. The first instinct on meeting a
    stale-looking lock file is to delete it, and with an OS-level lock that is
    both unnecessary -- the kernel already released it if the holder died -- and
    harmful, because deleting it while a holder lives lets a second instance
    create a fresh file and acquire a lock on that one instead.
    """
    held_by = f"held by PID: {holder}" if holder is not None else "held by PID: unknown"
    return (
        "Refusing to start: another instance of this bot is already running.\n\n"
        f"  lock file  : {path}\n"
        f"  {held_by}\n\n"
        "Two instances on one account is what produced the duplicate placement on\n"
        "2026-08-27: both derived the same client order id, and only the venue's\n"
        "-2010 refusal stopped a second order list existing. That protection does\n"
        "not hold if the two signal on different bars.\n\n"
        "Check your other terminals. If you are certain no bot is running, the\n"
        "lock is released automatically when the holder exits -- you do not need\n"
        "to delete the file."
    )
