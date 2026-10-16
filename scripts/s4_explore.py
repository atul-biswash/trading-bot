#!/usr/bin/env python
"""EXPLORATORY: how much of S4's run is "bot down" under two rules, and which entries each would exclude (M5m P123, R-DC).

Usage:

    .venv\\Scripts\\python.exe scripts\\s4_explore.py CAPTURE --window-start 2026-10-11T00:00:00Z --window-end 2026-10-17T00:00:00Z

R-DC, verbatim: *"scripts/s4_explore.py computes, for a frozen capture, the excluded intervals under the frozen
down_intervals and under a corrected rule (from each process's last record to the next process's first closed candle),
and the entries each would exclude. Its output is exploratory under the ratified CHOSEN line 5 and never replaces
s4_compare.py's result."* Nothing here is a gate, a verdict or an input to ``scripts/s4_compare.py``, which is not
edited and whose ``down_intervals`` this imports and runs as it stands.

**THE TWO RULES.**

* **Frozen** (``scripts/s4_compare.py``, ``down_intervals``): processes are ordered by the first line each wrote; an
  interval runs from one process's last line to the NEXT PROCESS'S FIRST ``reconciliation_pass`` (its first line if it
  never logs one). Because a pass is logged only while a position is open, a restart with nothing open is "down" until
  the first position, and a ``strategies`` verification boot or a refused boot is a process of its own.
* **Corrected** (R-DC): only a TRADING process counts, one whose log carries ``Trading engine started: <pairs>``. A
  ``strategies`` boot and a refused boot never start an engine, so they are neither a process that goes down nor one that
  resumes: the downtime between two trading processes runs from the first one's LAST RECORD to the second's FIRST CLOSED
  CANDLE, and a refused boot between them lies inside it. The first closed candle is inferred, because the log has no
  line for a candle: it is the first boundary of the SHORTEST timeframe in the engine-started line (UTC-aligned) strictly
  after that line's stamp. For BTCUSDT 1m and ETHUSDT 5m that is the next whole minute; ETHUSDT's own first 5m close can be
  up to four minutes later, which the two bars every entry rule adds after an interval (ten minutes for a 5m pair)
  already covers.

**THE ENTRIES.** The live entries of the window are ``scripts/s4_compare.py``'s own (``live_entries`` over
``scripts/trade_census.py``'s booked trades: an ``order_placed`` matched to its booking, its entry bar opening in
``[start, end)``). An entry is excluded by a rule when its signal bar's close falls in one of that rule's intervals or in
the two bars after it (``in_downtime``, the frozen function, applied to both rules so that ONLY the intervals differ).
**This is the live side only**: the frozen comparison also drops the backtest entries that fall in the same intervals, and
a capture alone has no backtest.

**WHAT IT DOES NOT DO.** It does not read the live log (a path under ``logs/`` is refused before a byte is read), writes
nothing, opens no socket and imports nothing from the bot beyond what ``scripts/s4_compare.py`` imports. A pid is taken
to be one process: Windows reusing a pid inside one capture would merge two processes, as the frozen rule's does.
"""

from __future__ import annotations

import argparse
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from itertools import pairwise
from pathlib import Path

from run_census import CaptureRefusedError, digest_of, reject_live_log
from s4_compare import (
    EXCLUDED_BARS_AFTER_DOWNTIME,
    DownInterval,
    InputError,
    LiveEntry,
    down_intervals,
    in_downtime,
    live_entries,
    timeframe_delta,
)
from trade_census import build_trades, parse_capture

_LOG_LINE = re.compile(
    r"^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})Z \| [A-Z]+\s*\| pid=(\d+) \| ([\w.]+) \| (.*)$"
)
_ENGINE_STARTED = re.compile(r"Trading engine started: (\S+/\S+(?:, \S+/\S+)*)\s*$")
_PASS_EVENT = "event=reconciliation_pass"
_CLEAN_STOP = "event=engine_stopped clean_shutdown=True"
_REFUSED_EXIT = 2
_INPUT_EXIT = 3
_RULE_FROZEN = "frozen"
_RULE_CORRECTED = "corrected"
FLOOR_BOOKINGS = 100


@dataclass(frozen=True)
class Process:
    """One pid of the capture: what it wrote, and when it started to trade."""

    pid: str
    first: datetime
    last: datetime
    engine_started: datetime | None
    pairs: tuple[tuple[str, str], ...]
    first_pass: datetime | None
    clean_stop: bool
    first_candle: datetime | None


def _stamp_of(match: re.Match[str]) -> datetime:
    year, month, day, hour, minute, second = (int(part) for part in match.groups()[:6])
    return datetime(year, month, day, hour, minute, second, tzinfo=timezone.utc)


def first_closed_candle(started: datetime, pairs: Sequence[tuple[str, str]]) -> datetime:
    """The first UTC-aligned boundary of the shortest timeframe strictly after ``started``."""
    step = min(timeframe_delta(timeframe) for _, timeframe in pairs).total_seconds()
    boundary = (int(started.timestamp() // step) + 1) * step
    return datetime.fromtimestamp(boundary, tz=timezone.utc)


def read_processes(lines: Sequence[str]) -> tuple[Process, ...]:
    """Every pid in the capture, ordered by the first line it wrote (the frozen rule's order)."""
    order: list[str] = []
    first: dict[str, datetime] = {}
    last: dict[str, datetime] = {}
    started: dict[str, datetime] = {}
    pairs: dict[str, tuple[tuple[str, str], ...]] = {}
    first_pass: dict[str, datetime] = {}
    stopped: set[str] = set()
    for line in lines:
        found = _LOG_LINE.match(line)
        if found is None:
            continue
        pid, stamp, message = found.group(7), _stamp_of(found), found.group(9)
        if pid not in first:
            first[pid] = stamp
            order.append(pid)
        last[pid] = max(last.get(pid, stamp), stamp)
        engine = _ENGINE_STARTED.search(message)
        if engine is not None and pid not in started:
            started[pid] = stamp
            pairs[pid] = tuple(
                (symbol, timeframe)
                for symbol, _, timeframe in (
                    item.partition("/") for item in engine.group(1).split(", ")
                )
            )
        if _PASS_EVENT in message and pid not in first_pass:
            first_pass[pid] = stamp
        if _CLEAN_STOP in message:
            stopped.add(pid)
    return tuple(
        Process(
            pid=pid,
            first=first[pid],
            last=last[pid],
            engine_started=started.get(pid),
            pairs=pairs.get(pid, ()),
            first_pass=first_pass.get(pid),
            clean_stop=pid in stopped,
            first_candle=(
                first_closed_candle(started[pid], pairs[pid]) if pid in started else None
            ),
        )
        for pid in order
    )


def corrected_intervals(processes: Sequence[Process]) -> tuple[DownInterval, ...]:
    """From each trading process's last record to the next trading process's first closed candle."""
    trading = [(p, p.first_candle) for p in processes if p.first_candle is not None]
    intervals: list[DownInterval] = []
    for (before, _), (after, resumed) in pairwise(trading):
        if resumed is not None and resumed > before.last:
            intervals.append(DownInterval(before.last, resumed, before.pid, after.pid))
    return tuple(intervals)


def timeframes_of(processes: Sequence[Process]) -> dict[str, str]:
    """Symbol to timeframe, from the engine-started lines. Two lines that disagree are an input error."""
    found: dict[str, str] = {}
    for process in processes:
        for symbol, timeframe in process.pairs:
            if found.setdefault(symbol, timeframe) != timeframe:
                raise InputError(
                    f"pid {process.pid} trades {symbol} on {timeframe} and an earlier process on {found[symbol]}"
                )
    return found


def total_time(intervals: Sequence[DownInterval]) -> timedelta:
    return sum((i.end - i.start for i in intervals), timedelta(0))


def clipped_time(intervals: Sequence[DownInterval], start: datetime, end: datetime) -> timedelta:
    """The part of the intervals that lies in ``[start, end)``."""
    inside = timedelta(0)
    for interval in intervals:
        low, high = max(interval.start, start), min(interval.end, end)
        if high > low:
            inside += high - low
    return inside


def excluded_entries(
    entries: Sequence[LiveEntry], intervals: Sequence[DownInterval], timeframes: Mapping[str, str]
) -> tuple[tuple[LiveEntry, DownInterval], ...]:
    """The entries whose signal bar closed in an interval or in the two bars after it, with the interval."""
    out: list[tuple[LiveEntry, DownInterval]] = []
    for entry in entries:
        try:
            timeframe = timeframes[entry.symbol]
        except KeyError as exc:
            raise InputError(f"the capture names no timeframe for {entry.symbol}") from exc
        interval = in_downtime(entry.signal_bar_close, intervals, timeframe_delta(timeframe))
        if interval is not None:
            out.append((entry, interval))
    return tuple(out)


def utc_text(value: datetime) -> str:
    return value.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def duration_text(delta: timedelta) -> str:
    total = int(delta.total_seconds())
    hours, rest = divmod(total, 3600)
    minutes, seconds = divmod(rest, 60)
    return f"{hours}:{minutes:02d}:{seconds:02d}"


def _interval_lines(
    name: str, intervals: Sequence[DownInterval], start: datetime, end: datetime
) -> list[str]:
    out = [
        f"{name}: {len(intervals)} interval(s), total {duration_text(total_time(intervals))}, "
        f"inside the window {duration_text(clipped_time(intervals, start, end))}"
    ]
    for interval in intervals:
        out.append(
            f"  {utc_text(interval.start)} -> {utc_text(interval.end)}  "
            f"{duration_text(interval.end - interval.start)}  pid {interval.before_pid} -> pid {interval.after_pid}"
        )
    return out


def render(
    *,
    path: Path,
    size: int,
    line_count: int,
    sha: str,
    window: tuple[datetime, datetime],
    processes: Sequence[Process],
    frozen: Sequence[DownInterval],
    corrected: Sequence[DownInterval],
    entries: Sequence[LiveEntry],
    unplaced: int,
    frozen_out: Sequence[tuple[LiveEntry, DownInterval]],
    corrected_out: Sequence[tuple[LiveEntry, DownInterval]],
    bookings_in_window: int,
) -> list[str]:
    start, end = window
    rule = "=" * 74
    out = [
        rule,
        "EXPLORATORY (the ratified CHOSEN line 5): never replaces scripts/s4_compare.py's result",
        rule,
        f"  capture : {path}",
        f"  bytes   : {size}",
        f"  lines   : {line_count}",
        f"  sha256  : {sha}",
        f"  window  : [{utc_text(start)}, {utc_text(end)})",
        "",
        f"PROCESSES ({len(processes)}), ordered by first line",
    ]
    for p in processes:
        started = (
            "none (not a trading process)"
            if p.engine_started is None
            else utc_text(p.engine_started)
        )
        candle = "none" if p.first_candle is None else utc_text(p.first_candle)
        first_pass = "none" if p.first_pass is None else utc_text(p.first_pass)
        out.append(
            f"  pid {p.pid:<6} first {utc_text(p.first)}  last {utc_text(p.last)}  engine started {started}  "
            f"first pass {first_pass}  first closed candle {candle}  clean stop {'yes' if p.clean_stop else 'no'}"
        )
    out += ["", "EXCLUDED INTERVALS"]
    out += _interval_lines("frozen rule (down_intervals, imported)", frozen, start, end)
    out += _interval_lines("corrected rule (R-DC)", corrected, start, end)
    frozen_keys = {(e.symbol, e.signal_bar_close) for e, _ in frozen_out}
    corrected_keys = {(e.symbol, e.signal_bar_close) for e, _ in corrected_out}
    both = frozen_keys & corrected_keys
    out += [
        "",
        f"ENTRIES whose entry bar opens in the window: {len(entries)} (bookings with no matched placement: {unplaced})",
        f"  excluded under the frozen rule    : {len(frozen_keys)}, kept {len(entries) - len(frozen_keys)}",
        f"  excluded under the corrected rule : {len(corrected_keys)}, kept {len(entries) - len(corrected_keys)}",
        f"  excluded under both               : {len(both)}",
        f"  only under the frozen rule        : {len(frozen_keys - corrected_keys)}",
        f"  only under the corrected rule     : {len(corrected_keys - frozen_keys)}",
        f"  (each rule adds the {EXCLUDED_BARS_AFTER_DOWNTIME} bars after an interval; the live side only)",
    ]
    listed = sorted(frozen_keys | corrected_keys, key=lambda key: (key[1], key[0]))
    for symbol, close in listed:
        which = [
            name
            for name, keys in ((_RULE_FROZEN, frozen_keys), (_RULE_CORRECTED, corrected_keys))
            if (symbol, close) in keys
        ]
        out.append(
            f"    {symbol:<8} signal bar closes {utc_text(close)}  excluded under: {' and '.join(which)}"
        )
    out += [
        "",
        f"COUNT ARITHMETIC against R-AZ's floor of {FLOOR_BOOKINGS} (facts, not a verdict)",
        f"  bookings made in the window (booking time)  : {bookings_in_window}",
        f"  entries in the window                       : {len(entries)}",
    ]
    for name, excluded in ((_RULE_FROZEN, frozen_keys), (_RULE_CORRECTED, corrected_keys)):
        comparable = len(entries) - len(excluded)
        out += [
            f"  {name} rule: excluded {len(excluded)}",
            f"    bookings in the window - excluded       : {bookings_in_window - len(excluded)}"
            f"  ({'at or above' if bookings_in_window - len(excluded) >= FLOOR_BOOKINGS else 'below'} {FLOOR_BOOKINGS})",
            f"    entries in the window - excluded        : {comparable}"
            f"  ({'at or above' if comparable >= FLOOR_BOOKINGS else 'below'} {FLOOR_BOOKINGS})",
        ]
    return out


def _utc_instant(raw: str) -> datetime:
    try:
        value = datetime.fromisoformat(raw)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"not an ISO timestamp: {raw!r}") from exc
    if value.tzinfo is None:
        raise argparse.ArgumentTypeError(f"carries no zone, write it as ...Z: {raw!r}")
    return value.astimezone(timezone.utc)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="s4_explore.py",
        description="EXPLORATORY: S4's excluded intervals under the frozen and a corrected rule, and the entries each excludes.",
    )
    parser.add_argument(
        "capture", type=Path, help="a frozen live log capture; a path under logs/ is refused"
    )
    parser.add_argument("--window-start", type=_utc_instant, required=True)
    parser.add_argument("--window-end", type=_utc_instant, required=True)
    parser.add_argument("--quote-asset", default="USDT")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    start, end = args.window_start, args.window_end
    if end <= start:
        print("REFUSED: --window-end must be after --window-start")
        return _REFUSED_EXIT
    capture: Path = args.capture
    try:
        reject_live_log(capture)
    except CaptureRefusedError as exc:
        print(f"REFUSED: {exc}")
        return _REFUSED_EXIT
    if not capture.is_file():
        print(f"REFUSED: {capture} is not a file")
        return _REFUSED_EXIT
    size = capture.stat().st_size
    lines = capture.read_text(encoding="utf-8", errors="replace").splitlines()
    try:
        processes = read_processes(lines)
        timeframes = timeframes_of(processes)
        parsed = parse_capture(lines)
        trades = build_trades(parsed, args.quote_asset)
        entries, unplaced = live_entries(trades, start=start, end=end)
        frozen = down_intervals(lines)
        corrected = corrected_intervals(processes)
        frozen_out = excluded_entries(entries, frozen, timeframes)
        corrected_out = excluded_entries(entries, corrected, timeframes)
    except InputError as exc:
        print(f"INPUT ERROR: {exc}")
        return _INPUT_EXIT
    bookings_in_window = sum(
        1
        for booking in parsed.bookings
        if booking.stamp.tzinfo is not None and start <= booking.stamp < end
    )
    for line in render(
        path=capture,
        size=size,
        line_count=len(lines),
        sha=digest_of(capture),
        window=(start, end),
        processes=processes,
        frozen=frozen,
        corrected=corrected,
        entries=entries,
        unplaced=unplaced,
        frozen_out=frozen_out,
        corrected_out=corrected_out,
        bookings_in_window=bookings_in_window,
    ):
        print(line)
    return 0


if __name__ == "__main__":  # pragma: no cover - CLI entry point
    raise SystemExit(main())
