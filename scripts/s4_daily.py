#!/usr/bin/env python
"""The owner's daily check for the rest of S4 (M5m P122, R-CZ). Read only, and it reports no verdict.

Usage, from the repository root, once a day:

    .venv\\Scripts\\python.exe scripts\\s4_daily.py

**IT TOUCHES NOTHING IN ANY CLONE.** The bot's log is read by copying its bytes, once, with a read-only open
that the writer's own open does not exclude, and every later figure is taken from that frozen copy. The
only files it writes are the freeze itself and the report, under ``F:\\trading bot\\scratch\\s4\\<UTC date>\\``,
and :func:`require_outside_every_clone` refuses a destination that lies under a ``logs/`` directory, under
either clone, or under any directory that has a ``.git`` entry among its ancestors. It starts no process
beyond two read-only PowerShell queries (the process list and the scheduled task's last result), and it
opens no socket and no ``.env``.

**THE ONE WAY IT COULD TOUCH THE BOT, STATED RATHER THAN HIDDEN.** Python's read open on Windows does not grant
others the right to rename the file while it is open, and the bot's rotating handler renames the active log at
10 MB. The file is held for the length of one ``read()`` (milliseconds) and the log grows by about 0.2 MB a day,
so the window is a few milliseconds in several weeks; a rename that lost it would fail inside the bot's logging
handler, which prints the error to stderr, loses that one log line and goes on.

**WHAT IT REPORTS, AND NOTHING ELSE** (the stop rule and the booking definition are
``docs/S4_PREREGISTRATION.md`` section 3, R-AY):

1. whether the bot process is alive, and how old the log's last line is;
2. the recorder task's last result, and the newest stored bar of every recorded series;
3. every boot since ``T0`` with its pid, marked ``run`` when that pid went on to log ``Starting in <MODE> mode``
   and ``other`` when it did not (a ``strategies`` verification boot logs ``boot_provenance`` and no such line,
   so it is neither ``T0`` nor a run boot);
4. the bookings since ``T0``, counted by ``scripts/trade_census.py`` over the frozen capture;
5. the stop rule's arithmetic: days since ``T0``, bookings against 150, the earliest stop and the cap.

**THE FREEZE IS R-BM.** Every ``trading_bot.log*`` file in the log directory is copied and hashed. The capture
is the rotated files (``trading_bot.log.N``, the highest N oldest) concatenated oldest first and then the
active file, and its SHA-256 is the capture digest. A file whose name has any other suffix is frozen and
listed as outside the capture, because there is no order to put it in. A freeze never overwrites: every
file name carries the time of this invocation.

**THE ARITHMETIC IS NOT A VERDICT.** It states the instants and the counts and which of the rule's conditions
each one meets as of this invocation. It does not say whether S4 has ended, because the rule stops at a UTC
midnight and this runs at no midnight in particular.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Final

from run_census import CaptureRefusedError, reject_live_log
from trade_census import (
    EVENT_BOOT_EXIT_BOOKED,
    EVENT_CLOSE_BOOKED,
    EVENT_EXIT_BOOKED,
    parse_capture,
)

CLONE: Final = Path(r"F:\trading bot\deploy\45547f107715")
RECORDER_ROOT: Final = Path(r"F:\trading bot\recorder\45547f107715\data\historical_testnet")
SCRATCH_ROOT: Final = Path(r"F:\trading bot\scratch\s4")
TASK_NAME: Final = "tb-recorder"
T0: Final = datetime(2026, 10, 10, 6, 5, 20, tzinfo=timezone.utc)
MINIMUM_DAYS: Final = 21
CAP_DAYS: Final = 35
REQUIRED_BOOKINGS: Final = 150
FLOOR_BOOKINGS: Final = 100

LOG_NAME: Final = "trading_bot.log"
RUN_COMMAND_MARK: Final = "-m trading_bot run"
_QUERY_TIMEOUT_S: Final = 60
_EXIT_INPUT: Final = 2

_LOG_LINE = re.compile(
    r"^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})Z \| (\w+)\s*\| pid=(\d+) \| ([\w.]+) \| (.*)$"
)
_BOOKING_EVENT = re.compile(
    rf"event=({EVENT_CLOSE_BOOKED}|{EVENT_EXIT_BOOKED}|{EVENT_BOOT_EXIT_BOOKED})\b"
)
_VERDICT = re.compile(r"event=boot_provenance verdict=(\S+)")
_STARTING = re.compile(r"^Starting in (\w+) mode$")
_ROTATED = re.compile(r"^trading_bot\.log\.(\d+)$")
_INTERVAL = re.compile(r"^(\d+)([mhd])$")
_UNIT = {"m": timedelta(minutes=1), "h": timedelta(hours=1), "d": timedelta(days=1)}

_RECORDER_EXIT_MEANING: Final = {
    0: "extended, or already current",
    1: "a request failed or its answer was malformed (transient)",
    2: "the venue's history was discarded or rewritten; nothing written",
    3: "a bar with no class, or a page that repeated; nothing written",
    4: "what is stored does not verify, so it was not extended",
    5: "another recorder holds the lock",
    64: "a usage error",
}


class ProbeError(Exception):
    """A read-only query could not be answered; the report says so and goes on."""


class FreezeRefusedError(Exception):
    """The freeze destination or the log directory is not usable."""


@dataclass(frozen=True)
class ProcessInfo:
    """One row of the process list."""

    pid: int
    parent_pid: int
    name: str
    command_line: str


@dataclass(frozen=True)
class TaskInfo:
    """The scheduled task's last result, as the scheduler reports it."""

    last_run: datetime | None
    last_result: int | None
    next_run: datetime | None
    missed_runs: int | None


@dataclass(frozen=True)
class Environment:
    """Everything that comes from outside the files, so a test supplies it."""

    now: datetime
    list_processes: Callable[[], list[ProcessInfo]]
    read_task: Callable[[str], TaskInfo]


@dataclass(frozen=True)
class LogFamily:
    """The log files, in the order the capture concatenates them, and the ones it cannot place."""

    ordered: tuple[Path, ...]
    outside: tuple[Path, ...]


@dataclass(frozen=True)
class FrozenFile:
    """One copied file: where it came from, where the copy is, and the copy's digest."""

    source: Path
    copy: Path
    size: int
    sha256: str


@dataclass(frozen=True)
class Freeze:
    """The result of freezing the family."""

    directory: Path
    stamp: str
    files: tuple[FrozenFile, ...]
    capture: Path
    capture_size: int
    capture_sha256: str
    outside: tuple[FrozenFile, ...]
    family_changed: bool


@dataclass
class _BootBuilder:
    line_no: int
    stamp: datetime
    pid: int
    verdict: str
    mode: str | None = None
    clean_stop: bool = False
    last_stamp: datetime | None = None
    lines: int = 0


@dataclass(frozen=True)
class Boot:
    """One ``boot_provenance`` line and what its pid did afterwards."""

    line_no: int
    stamp: datetime
    pid: int
    verdict: str
    kind: str
    mode: str | None
    clean_stop: bool
    last_stamp: datetime | None
    lines: int


@dataclass(frozen=True)
class LogFacts:
    """What the capture's lines say, before any T0 is applied."""

    last_stamp: datetime | None
    last_pid: int | None
    last_line_no: int
    boots: tuple[Boot, ...]


@dataclass(frozen=True)
class SeriesBar:
    """The newest stored bar of one recorded series."""

    symbol: str
    interval: str
    open_time: datetime | None
    close_time: datetime | None
    problem: str | None


@dataclass(frozen=True)
class BotStatus:
    """Whether the process that wrote the log's last line is alive."""

    last_pid: int | None
    pid_alive: bool
    launcher_pids: tuple[int, ...]


@dataclass(frozen=True)
class StopArithmetic:
    """The stop rule's instants and counts as of ``now``; no verdict."""

    t0: datetime
    now: datetime
    elapsed: timedelta
    bookings: int
    required: int
    bookings_short: int
    earliest_stop: datetime
    cap: datetime
    next_midnight: datetime
    bookings_meet_required: bool
    now_at_or_after_earliest: bool
    next_midnight_at_or_after_earliest: bool
    stops_at_next_midnight: bool
    now_at_or_after_cap: bool
    bookings_meet_floor: bool


@dataclass(frozen=True)
class Bookings:
    """The census's count of bookings, split at ``T0``."""

    since_t0: int
    before_t0: int
    unzoned: int
    anomalies: int
    by_event: tuple[tuple[str, int], ...]
    raw_lines_since_t0: int


@dataclass
class Report:
    """The report's lines, collected in order."""

    lines: list[str] = field(default_factory=list)

    def add(self, text: str = "") -> None:
        self.lines.append(text)


def utc_text(value: datetime | None) -> str:
    """An instant as ``YYYY-MM-DDTHH:MM:SSZ``, or ``none``."""
    if value is None:
        return "none"
    return value.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def duration_text(delta: timedelta) -> str:
    """A span as ``1d 02h 03m 04s``, with a leading minus when it is negative."""
    sign = "-" if delta < timedelta(0) else ""
    total = abs(int(delta.total_seconds()))
    days, rest = divmod(total, 86_400)
    hours, rest = divmod(rest, 3_600)
    minutes, seconds = divmod(rest, 60)
    return f"{sign}{days}d {hours:02d}h {minutes:02d}m {seconds:02d}s"


def next_utc_midnight(instant: datetime) -> datetime:
    """The first UTC midnight strictly after ``instant``."""
    base = instant.astimezone(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    return base + timedelta(days=1)


def first_midnight_at_or_after(instant: datetime) -> datetime:
    """The first UTC midnight at or after ``instant``; ``instant`` itself when it is one."""
    utc = instant.astimezone(timezone.utc)
    midnight = utc.replace(hour=0, minute=0, second=0, microsecond=0)
    return midnight if midnight == utc else midnight + timedelta(days=1)


def stop_arithmetic(
    *,
    t0: datetime,
    now: datetime,
    bookings: int,
    minimum_days: int = MINIMUM_DAYS,
    cap_days: int = CAP_DAYS,
    required: int = REQUIRED_BOOKINGS,
    floor: int = FLOOR_BOOKINGS,
) -> StopArithmetic:
    """R-AY's instants and counts. The stop is the first UTC midnight at or after ``t0 + 21 d``
    with at least ``required`` bookings by then; the cap is ``t0 + 35 d``."""
    earliest = first_midnight_at_or_after(t0 + timedelta(days=minimum_days))
    cap = t0 + timedelta(days=cap_days)
    midnight = next_utc_midnight(now)
    meets = bookings >= required
    return StopArithmetic(
        t0=t0,
        now=now,
        elapsed=now - t0,
        bookings=bookings,
        required=required,
        bookings_short=max(0, required - bookings),
        earliest_stop=earliest,
        cap=cap,
        next_midnight=midnight,
        bookings_meet_required=meets,
        now_at_or_after_earliest=now >= earliest,
        next_midnight_at_or_after_earliest=midnight >= earliest,
        stops_at_next_midnight=meets and midnight >= earliest,
        now_at_or_after_cap=now >= cap,
        bookings_meet_floor=bookings >= floor,
    )


def log_family(directory: Path) -> LogFamily:
    """Every ``trading_bot.log*`` file in ``directory``, the capture's order first."""
    found = sorted(p for p in directory.glob(LOG_NAME + "*") if p.is_file())
    rotated: list[tuple[int, Path]] = []
    active: Path | None = None
    outside: list[Path] = []
    for path in found:
        if path.name == LOG_NAME:
            active = path
            continue
        match = _ROTATED.match(path.name)
        if match is None:
            outside.append(path)
        else:
            rotated.append((int(match.group(1)), path))
    ordered = [path for _, path in sorted(rotated, key=lambda item: item[0], reverse=True)]
    if active is not None:
        ordered.append(active)
    return LogFamily(tuple(ordered), tuple(outside))


def require_outside_every_clone(destination: Path, protected: Sequence[Path]) -> None:
    """Refuse a freeze destination that is, or lies under, anything a clone owns."""
    resolved = destination.resolve()
    try:
        reject_live_log(resolved)
    except CaptureRefusedError as exc:
        raise FreezeRefusedError(str(exc)) from exc
    for root in protected:
        base = root.resolve()
        if resolved == base or base in resolved.parents:
            raise FreezeRefusedError(f"{destination} lies under {root}, which is a clone")
    for ancestor in (resolved, *resolved.parents):
        if (ancestor / ".git").exists():
            raise FreezeRefusedError(
                f"{destination} lies under {ancestor}, which holds a .git entry"
            )


def _read_bytes(path: Path) -> bytes:
    with path.open("rb") as handle:
        return handle.read()


def _write_new(path: Path, data: bytes) -> None:
    try:
        with path.open("xb") as handle:
            handle.write(data)
    except FileExistsError as exc:
        raise FreezeRefusedError(f"{path} exists already, and a freeze never overwrites") from exc


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def freeze_family(
    log_directory: Path, destination: Path, now: datetime, protected: Sequence[Path]
) -> Freeze:
    """Copy every log file, hash each copy, and write the capture. Nothing is ever overwritten."""
    require_outside_every_clone(destination, protected)
    if not log_directory.is_dir():
        raise FreezeRefusedError(f"{log_directory} is not a directory")
    before = log_family(log_directory)
    if not before.ordered and not before.outside:
        raise FreezeRefusedError(f"{log_directory} holds no {LOG_NAME}* file")
    destination.mkdir(parents=True, exist_ok=True)
    stamp = now.astimezone(timezone.utc).strftime("%H%M%SZ")

    def copy_one(path: Path) -> tuple[FrozenFile, bytes]:
        data = _read_bytes(path)
        target = destination / f"{stamp}-{path.name}"
        _write_new(target, data)
        return FrozenFile(path, target, len(data), _sha256(data)), data

    copied: list[tuple[FrozenFile, bytes]] = [copy_one(path) for path in before.ordered]
    outside = tuple(copy_one(path)[0] for path in before.outside)
    capture_bytes = b"".join(data for _, data in copied)
    capture = destination / f"{stamp}-capture.log"
    _write_new(capture, capture_bytes)
    sums = [f"{item.sha256}  {item.copy.name}" for item, _ in copied]
    sums += [f"{item.sha256}  {item.copy.name}  (outside the capture)" for item in outside]
    sums.append(f"{_sha256(capture_bytes)}  {capture.name}  (the capture digest)")
    _write_new(destination / f"{stamp}-SHA256SUMS.txt", ("\n".join(sums) + "\n").encode("ascii"))
    after = log_family(log_directory)
    return Freeze(
        directory=destination,
        stamp=stamp,
        files=tuple(item for item, _ in copied),
        capture=capture,
        capture_size=len(capture_bytes),
        capture_sha256=_sha256(capture_bytes),
        outside=outside,
        family_changed=after != before,
    )


def _line_stamp(match: re.Match[str]) -> datetime:
    year, month, day, hour, minute, second = (int(part) for part in match.groups()[:6])
    return datetime(year, month, day, hour, minute, second, tzinfo=timezone.utc)


def read_log(lines: Sequence[str]) -> LogFacts:
    """Last stamped line, and every boot with its pid's later behaviour."""
    last_stamp: datetime | None = None
    last_pid: int | None = None
    last_line_no = 0
    builders: list[_BootBuilder] = []
    current: dict[int, _BootBuilder] = {}
    undecided: set[int] = set()
    for line_no, line in enumerate(lines, start=1):
        match = _LOG_LINE.match(line)
        if match is None:
            continue
        stamp = _line_stamp(match)
        pid = int(match.group(8))
        logger, message = match.group(9), match.group(10)
        last_stamp, last_pid, last_line_no = stamp, pid, line_no
        if "event=boot_provenance" in message:
            verdict = _VERDICT.search(message)
            builder = _BootBuilder(line_no, stamp, pid, verdict.group(1) if verdict else "unread")
            builders.append(builder)
            current[pid] = builder
            undecided.add(pid)
        builder_now = current.get(pid)
        if builder_now is not None:
            builder_now.last_stamp = stamp
            builder_now.lines += 1
            if pid in undecided and logger == "trading_bot.main":
                starting = _STARTING.match(message)
                if starting is not None:
                    builder_now.mode = starting.group(1)
                    undecided.discard(pid)
            if "event=engine_stopped" in message and "clean_shutdown=True" in message:
                builder_now.clean_stop = True
    boots = tuple(
        Boot(
            line_no=b.line_no,
            stamp=b.stamp,
            pid=b.pid,
            verdict=b.verdict,
            kind="run" if b.mode is not None else "other",
            mode=b.mode,
            clean_stop=b.clean_stop,
            last_stamp=b.last_stamp,
            lines=b.lines,
        )
        for b in builders
    )
    return LogFacts(last_stamp, last_pid, last_line_no, boots)


def first_run_boot(boots: Sequence[Boot]) -> Boot | None:
    """The first boot that went on to say ``Starting in <MODE> mode``; ``other`` boots never count."""
    return next((boot for boot in boots if boot.kind == "run"), None)


def boots_since(boots: Sequence[Boot], t0: datetime) -> tuple[Boot, ...]:
    """Every boot at or after ``t0``, of either kind."""
    return tuple(boot for boot in boots if boot.stamp >= t0)


def bot_status(processes: Sequence[ProcessInfo], clone: Path, last_pid: int | None) -> BotStatus:
    """The log's last pid alive means a process of that number whose command line is a ``run``."""
    alive = last_pid is not None and any(
        p.pid == last_pid and RUN_COMMAND_MARK in p.command_line for p in processes
    )
    clone_text = str(clone).lower()
    launchers = tuple(
        p.pid
        for p in processes
        if RUN_COMMAND_MARK in p.command_line and clone_text in p.command_line.lower()
    )
    return BotStatus(last_pid, alive, launchers)


def count_bookings(lines: Sequence[str], t0: datetime) -> Bookings:
    """The census's bookings (``scripts/trade_census.py``'s own parser), split at ``t0``."""
    parsed = parse_capture(lines)
    since: list[datetime] = []
    events: dict[str, int] = {}
    before = 0
    unzoned = 0
    for booking in parsed.bookings:
        if booking.stamp.tzinfo is None:
            unzoned += 1
        elif booking.stamp >= t0:
            since.append(booking.stamp)
            events[booking.event] = events.get(booking.event, 0) + 1
        else:
            before += 1
    raw = sum(
        1
        for line in lines
        if _BOOKING_EVENT.search(line)
        and (m := _LOG_LINE.match(line)) is not None
        and _line_stamp(m) >= t0
    )
    return Bookings(
        since_t0=len(since),
        before_t0=before,
        unzoned=unzoned,
        anomalies=len(parsed.anomalies),
        by_event=tuple(sorted(events.items())),
        raw_lines_since_t0=raw,
    )


def interval_delta(interval: str) -> timedelta:
    """``1m`` as a minute, ``5m`` as five, ``1h``, ``1d``."""
    match = _INTERVAL.match(interval)
    if match is None:
        raise ProbeError(f"unreadable interval {interval!r}")
    return int(match.group(1)) * _UNIT[match.group(2)]


def newest_bars(root: Path) -> tuple[SeriesBar, ...]:
    """The newest stored bar of every ``<root>/<SYMBOL>/<interval>/`` series, by its last CSV row."""
    if not root.is_dir():
        raise ProbeError(f"{root} is not a directory")
    bars: list[SeriesBar] = []
    for symbol_dir in sorted(
        p for p in root.iterdir() if p.is_dir() and not p.name.startswith("_")
    ):
        for interval_dir in sorted(p for p in symbol_dir.iterdir() if p.is_dir()):
            bars.append(_newest_bar(symbol_dir.name, interval_dir))
    return tuple(bars)


def _newest_bar(symbol: str, directory: Path) -> SeriesBar:
    interval = directory.name
    files = sorted(directory.glob("*.csv"))
    if not files:
        return SeriesBar(symbol, interval, None, None, "no csv file")
    try:
        step = interval_delta(interval)
        rows = [r for r in _read_bytes(files[-1]).decode("ascii").splitlines() if r.strip()]
        if len(rows) < 2:
            return SeriesBar(symbol, interval, None, None, f"{files[-1].name} holds no row")
        open_ms = int(rows[-1].split(",")[0])
    except (ProbeError, ValueError, UnicodeDecodeError) as exc:
        return SeriesBar(symbol, interval, None, None, f"{files[-1].name}: {exc}")
    opened = datetime.fromtimestamp(open_ms / 1000, tz=timezone.utc)
    return SeriesBar(symbol, interval, opened, opened + step, None)


def _powershell() -> str:
    found = shutil.which("powershell")
    if found is None or not Path(found).is_absolute():
        raise ProbeError("powershell was not found as an absolute path")
    return found


def _query(script: str) -> object:
    try:
        done = subprocess.run(
            [_powershell(), "-NoProfile", "-NonInteractive", "-Command", script],
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            timeout=_QUERY_TIMEOUT_S,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ProbeError(f"{type(exc).__name__}: {exc}") from exc
    if done.returncode != 0:
        raise ProbeError(f"powershell exit {done.returncode}: {done.stderr.strip()[:200]}")
    try:
        return json.loads(done.stdout)
    except ValueError as exc:
        raise ProbeError(f"powershell printed no JSON: {done.stdout.strip()[:200]!r}") from exc


def real_processes() -> list[ProcessInfo]:
    """Python processes, from ``Win32_Process``; read only."""
    script = (
        "$rows = @(Get-CimInstance Win32_Process | Where-Object { $_.Name -match 'python' } | "
        "ForEach-Object { [pscustomobject]@{ pid = [int]$_.ProcessId; ppid = [int]$_.ParentProcessId; "
        "name = [string]$_.Name; cmd = [string]$_.CommandLine } }); "
        "ConvertTo-Json -Compress -InputObject $rows"
    )
    answer = _query(script)
    rows = answer if isinstance(answer, list) else [answer]
    processes: list[ProcessInfo] = []
    for row in rows:
        if not isinstance(row, dict):
            raise ProbeError(f"a process row is not an object: {row!r:.80}")
        processes.append(
            ProcessInfo(
                int(row["pid"]),
                int(row["ppid"]),
                str(row["name"]),
                str(row["cmd"] or ""),
            )
        )
    return processes


def real_task(name: str) -> TaskInfo:
    """The scheduled task's last result; read only. Times are converted to UTC by the query."""
    quoted = name.replace("'", "''")
    script = (
        f"$i = Get-ScheduledTaskInfo -TaskName '{quoted}' -ErrorAction Stop; "
        "[pscustomobject]@{ last = $i.LastRunTime.ToUniversalTime().ToString('o'); "
        "result = [int64]$i.LastTaskResult; next = $i.NextRunTime.ToUniversalTime().ToString('o'); "
        "missed = [int]$i.NumberOfMissedRuns } | ConvertTo-Json -Compress"
    )
    answer = _query(script)
    if not isinstance(answer, dict):
        raise ProbeError("the task query answered something other than an object")

    def instant(key: str) -> datetime | None:
        raw = answer.get(key)
        if not raw:
            return None
        text = str(raw)
        parsed = datetime.fromisoformat(re.sub(r"(\.\d{6})\d+", r"\1", text).replace("Z", "+00:00"))
        return parsed.astimezone(timezone.utc) if parsed.year > 1999 else None

    try:
        return TaskInfo(
            instant("last"),
            int(answer["result"]),
            instant("next"),
            int(answer["missed"]),
        )
    except (KeyError, ValueError) as exc:
        raise ProbeError(f"the task answer is unreadable: {exc}") from exc


def real_environment() -> Environment:
    return Environment(datetime.now(timezone.utc), real_processes, real_task)


def _section(report: Report, title: str) -> None:
    report.add()
    report.add(f"== {title} ==")


def render(
    *,
    env: Environment,
    clone: Path,
    recorder_root: Path,
    task_name: str,
    t0: datetime,
    freeze: Freeze,
    facts: LogFacts,
    bookings: Bookings,
) -> list[str]:
    """The report. Facts, with their instruments named; no verdict anywhere."""
    report = Report()
    now = env.now
    report.add(f"s4_daily  now {utc_text(now)}  T0 {utc_text(t0)}  clone {clone}")

    _section(report, "freeze (R-BM)")
    report.add(f"directory  : {freeze.directory}")
    for item in freeze.files:
        report.add(f"  {item.sha256}  {item.size:>10}  {item.source.name}  ->  {item.copy.name}")
    for item in freeze.outside:
        report.add(
            f"  {item.sha256}  {item.size:>10}  {item.source.name}  ->  {item.copy.name}"
            "  (outside the capture: no order to place it in)"
        )
    report.add(f"capture    : {freeze.capture.name}  {freeze.capture_size} bytes")
    report.add(f"capture sha256 : {freeze.capture_sha256}")
    if freeze.family_changed:
        report.add("WARNING: the set of log files changed while it was being copied; run it again")

    _section(report, "bot process")
    try:
        status = bot_status(env.list_processes(), clone, facts.last_pid)
        report.add(f"last pid in the log : {status.last_pid}")
        report.add(
            f"that pid alive as a '{RUN_COMMAND_MARK}' process : {'yes' if status.pid_alive else 'no'}"
        )
        report.add(f"launcher pids for this clone : {list(status.launcher_pids)}")
    except ProbeError as exc:
        report.add(f"process list unavailable: {exc}")
    if facts.last_stamp is None:
        report.add("log's last line : none (the capture holds no stamped line)")
    else:
        report.add(
            f"log's last line : {utc_text(facts.last_stamp)} (capture line {facts.last_line_no}), "
            f"{duration_text(now - facts.last_stamp)} before now"
        )

    _section(report, "recorder")
    try:
        task = env.read_task(task_name)
        meaning = _RECORDER_EXIT_MEANING.get(
            task.last_result if task.last_result is not None else -1, ""
        )
        report.add(
            f"task {task_name}: last run {utc_text(task.last_run)}, last result {task.last_result}"
            f"{' (' + meaning + ')' if meaning else ''}, next run {utc_text(task.next_run)}, "
            f"missed runs {task.missed_runs}"
        )
    except ProbeError as exc:
        report.add(f"task {task_name} unavailable: {exc}")
    try:
        for bar in newest_bars(recorder_root):
            if bar.open_time is None or bar.close_time is None:
                report.add(f"  {bar.symbol} {bar.interval}: unreadable ({bar.problem})")
            else:
                report.add(
                    f"  {bar.symbol} {bar.interval}: newest bar opens {utc_text(bar.open_time)}, "
                    f"closed {duration_text(now - bar.close_time)} before now"
                )
    except ProbeError as exc:
        report.add(f"recorder store unavailable: {exc}")

    _section(report, "boots since T0")
    since = boots_since(facts.boots, t0)
    from_log = first_run_boot(facts.boots)
    report.add(
        f"T0 from the log (first run boot) : {utc_text(from_log.stamp) if from_log else 'none'}"
        f"  pid {from_log.pid if from_log else 'none'}"
        f"  {'= the ruled T0' if from_log and from_log.stamp == t0 else 'DIFFERS from the ruled T0'}"
    )
    report.add(
        f"boots at or after T0 : {len(since)} ({sum(1 for b in since if b.kind == 'run')} run)"
    )
    for boot in since:
        counted = "run boot" if boot.kind == "run" else "other (not a run boot, not T0)"
        report.add(
            f"  {utc_text(boot.stamp)}  pid {boot.pid}  verdict={boot.verdict}  {counted}"
            f"  last line {utc_text(boot.last_stamp)}  clean stop marker {'yes' if boot.clean_stop else 'no'}"
        )

    _section(report, "bookings since T0 (scripts/trade_census.py over the capture)")
    report.add(f"bookings since T0 : {bookings.since_t0}")
    for event, count in bookings.by_event:
        report.add(f"  {event} : {count}")
    report.add(
        f"booking event lines since T0 (raw count of the three events) : {bookings.raw_lines_since_t0}"
    )
    report.add(f"bookings before T0 : {bookings.before_t0}   unzoned stamps : {bookings.unzoned}")
    report.add(f"census anomalies : {bookings.anomalies}")

    _section(report, "stop rule arithmetic (R-AY), not a verdict")
    arithmetic = stop_arithmetic(t0=t0, now=now, bookings=bookings.since_t0)
    report.lines.extend(render_arithmetic(arithmetic))
    return report.lines


def render_arithmetic(a: StopArithmetic) -> list[str]:
    def yes(flag: bool) -> str:
        return "yes" if flag else "no"

    return [
        f"days since T0 : {duration_text(a.elapsed)}  ({a.elapsed.total_seconds() / 86_400:.3f} d)",
        f"bookings since T0 : {a.bookings} against {a.required}  (short by {a.bookings_short})",
        f"earliest stop : {utc_text(a.earliest_stop)}  (first UTC midnight at or after T0 + {MINIMUM_DAYS} d)",
        f"cap : {utc_text(a.cap)}  (T0 + {CAP_DAYS} d; evaluated at the cap if at least {FLOOR_BOOKINGS} bookings)",
        f"next UTC midnight : {utc_text(a.next_midnight)}",
        f"bookings >= {a.required} now : {yes(a.bookings_meet_required)}",
        f"now at or after the earliest stop : {yes(a.now_at_or_after_earliest)}",
        f"next UTC midnight at or after the earliest stop : {yes(a.next_midnight_at_or_after_earliest)}",
        f"both conditions met at the next UTC midnight on the bookings so far : {yes(a.stops_at_next_midnight)}",
        f"now at or after the cap : {yes(a.now_at_or_after_cap)}",
        f"bookings >= {FLOOR_BOOKINGS} now (the cap's floor) : {yes(a.bookings_meet_floor)}",
    ]


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="s4_daily.py",
        description="Read-only daily check of the S4 live run. Freezes the log outside every clone; "
        "reports without a verdict.",
    )
    parser.add_argument("--clone", type=Path, default=CLONE, help="the S4 deployment clone")
    parser.add_argument("--recorder-root", type=Path, default=RECORDER_ROOT)
    parser.add_argument("--task", default=TASK_NAME, help="the recorder's scheduled task")
    parser.add_argument(
        "--scratch", type=Path, default=SCRATCH_ROOT, help="where freezes are written"
    )
    return parser


def run(
    args: argparse.Namespace, env: Environment, *, t0: datetime = T0, protected: Sequence[Path] = ()
) -> tuple[int, list[str]]:
    """Freeze, read, render. Returns the exit status and the report lines."""
    clone: Path = args.clone
    destination = args.scratch / env.now.astimezone(timezone.utc).strftime("%Y-%m-%d")
    guards = (clone, args.recorder_root, Path(__file__).resolve().parent.parent, *protected)
    try:
        freeze = freeze_family(clone / "logs", destination, env.now, guards)
    except FreezeRefusedError as exc:
        return _EXIT_INPUT, [f"REFUSED: {exc}"]
    lines = freeze.capture.read_text(encoding="utf-8", errors="replace").splitlines()
    facts = read_log(lines)
    bookings = count_bookings(lines, t0)
    report = render(
        env=env,
        clone=clone,
        recorder_root=args.recorder_root,
        task_name=args.task,
        t0=t0,
        freeze=freeze,
        facts=facts,
        bookings=bookings,
    )
    text = ("\n".join(report) + "\n").encode("utf-8", errors="replace")
    _write_new(destination / f"{freeze.stamp}-report.txt", text)
    return 0, report


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    status, report = run(args, real_environment())
    for line in report:
        print(line)
    return status


if __name__ == "__main__":
    sys.exit(main())
