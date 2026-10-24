#!/usr/bin/env python
"""EXPLORATORY E2 (R-DL): the S4 comparison with latch intervals excluded as well as downtime, figures only.

``scripts/s4_compare.py`` is frozen and compares the pre-registered window as it stands (R-DK). This script runs the
same comparison on the same inputs and differs in one thing: the intervals it excludes on BOTH sides are the frozen
``down_intervals`` unioned with the LATCH intervals the project owner ruled at P128 and P129 (R-DM, R-DO, R-DP,
``docs/S4_CORRECTION_P128.md``, ``docs/S4_CORRECTION_P129.md``, ``docs/S4_CORRECTION_P130.md``). It prints the three
figures and the per-cause disagreement counts under the header ``EXPLORATORY E2 (R-DL)``, names no verdict, and cannot
change R-DK's recorded outcome. Everything it computes from the frozen tool it imports and runs as it stands.

**THE LATCH INTERVAL, from log lines only.** A run starts at the first ``reconciliation_untrusted`` line of a pass and
is the sequence of reconciliation passes of that process from there. It BREAKS at the first later pass of the same
process whose reported position count equals the open-position inventory at that instant (``order_placed`` lines less
``close_booked``, ``exit_booked`` and ``boot_exit_booked`` lines, in file order) and whose every reported state is in
the trusted set (R-DP). A pass that covered fewer positions than the inventory breaks nothing, and a state outside the
trusted set, named or not, breaks nothing. The run is an EPISODE only if a ``committed_risk_unknown`` or a
``close_halted`` refusal is logged while it is unbroken. Its end is the breaking pass or, when it never breaks, the
last log line of the process; a process that has neither a clean-stop line nor a successor in the capture gives an open
interval, closed at the window's end (M).

**THE TRUSTED SET IS IMPORTED, NOT RESTATED.** ``TRUSTED_STATES`` is built from ``core.portfolio._TRUSTED_PROTECTION``
of the interpreter that runs the script, so the rule follows the code that refuses entries; run with the S4 clone's
interpreter it is the set at ``45547f1`` that R-DP names.

Inputs, refusals and exit statuses are ``s4_compare.py``'s own: a path under ``logs/`` is refused before a byte is read,
the live boots and the backtest record go through the evidence door, and the same arguments are accepted.
"""

from __future__ import annotations

import re
import sys
from bisect import bisect_left
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from typing import Final

from run_census import CaptureRefusedError, digest_of, reject_live_log
from s4_compare import (
    _INPUT_EXIT,
    _REFUSED_EXIT,
    BACKTEST_LOG_NAME,
    TRADES_NAME,
    DownInterval,
    InputError,
    SeriesChecks,
    _build_parser,
    _data_dir,
    _timeframe_of,
    backtest_view_of,
    carried_in,
    diagnose,
    down_intervals,
    exclude_downtime,
    figures_of,
    in_downtime,
    live_boots,
    live_entries,
    load_backtest,
    match_entries,
    read_signals,
    render,
    render_diagnosis,
    require_live_run_eligible,
    strategy_facts,
    timeframe_delta,
    unfilled_placements,
    within,
)
from trade_census import build_trades, parse_capture

from trading_bot.backtesting.evidence import RUN_RECORD_NAME, EvidenceRefusedError
from trading_bot.core.portfolio import _TRUSTED_PROTECTION
from trading_bot.data.historical import HistoricalStore

__all__ = [
    "TRUSTED_STATES",
    "LatchEpisode",
    "LogRow",
    "ReconPass",
    "attach_untrusted",
    "build_passes",
    "can_break",
    "latch_episodes",
    "latch_intervals",
    "main",
    "merge_intervals",
    "parse_states",
    "read_rows",
    "render_latches",
]

HEADER: Final = "EXPLORATORY E2 (R-DL)"
TRUSTED_STATES: Final = frozenset(state.value for state in _TRUSTED_PROTECTION)

_ROW = re.compile(r"^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})Z \| [A-Z]+\s*\| pid=(\d+) \|")
_SYMBOL = re.compile(r"symbol=(\w+)")
_SYMBOLS = re.compile(r"symbols=(\S+)")
_POSITIONS = re.compile(r"positions=(\d+)")
_STATES = re.compile(r'states="([^"]*)"')
_PASS: Final = "event=reconciliation_pass"
_UNTRUSTED: Final = "event=reconciliation_untrusted"
_OPENED: Final = "event=order_placed"
_CLOSED: Final = ("event=close_booked", "event=exit_booked", "event=boot_exit_booked")
_STOPPED: Final = "event=engine_stopped clean_shutdown=True"
_NEAR: Final = timedelta(seconds=15)
_SECONDS_PER_HOUR: Final = Decimal(3600)


@dataclass(frozen=True)
class LogRow:
    """One stamped, pid-carrying line of the capture and its place in the file."""

    number: int
    stamp: datetime
    pid: str
    text: str


@dataclass(frozen=True)
class ReconPass:
    """One ``reconciliation_pass`` line: how many positions it covered, what the inventory held, the states."""

    row: LogRow
    positions: int
    inventory: frozenset[str]
    states: tuple[tuple[str, int], ...] | None


@dataclass(frozen=True)
class Attachment:
    """The untrusted symbols one pass named and the file line of the first untrusted line that named them."""

    symbols: frozenset[str]
    first_line: int


@dataclass(frozen=True)
class LatchEpisode:
    """One latch: a qualifying run, its interval, how that interval ended, and what it contained."""

    pid: str
    symbols: tuple[str, ...]
    start: datetime
    end: datetime
    end_kind: str
    passes: int
    refusals: int


@dataclass
class _Run:
    pid: str
    start: datetime
    passes: int = 0
    symbols: set[str] = field(default_factory=set)


def read_rows(lines: Sequence[str]) -> list[LogRow]:
    """Every line that carries a zoned stamp and a pid, in file order."""
    rows: list[LogRow] = []
    for number, text in enumerate(lines, start=1):
        found = _ROW.match(text)
        if found is None:
            continue
        year, month, day, hour, minute, second = (int(part) for part in found.groups()[:6])
        stamp = datetime(year, month, day, hour, minute, second, tzinfo=timezone.utc)
        rows.append(LogRow(number, stamp, found.group(7), text))
    return rows


def parse_states(text: str) -> tuple[tuple[str, int], ...] | None:
    """The ``states="active=1,unknown=1"`` field as (name, count) pairs, or ``None`` when absent or unreadable."""
    found = _STATES.search(text)
    if found is None:
        return None
    pairs: list[tuple[str, int]] = []
    for item in found.group(1).split(","):
        name, separator, count = item.partition("=")
        if not separator or not name or not count.isdigit():
            return None
        pairs.append((name, int(count)))
    return tuple(pairs) if pairs else None


def build_passes(rows: Sequence[LogRow]) -> list[ReconPass]:
    """Every pass with the inventory of open positions at that instant, kept per process from the log alone."""
    held: dict[str, set[str]] = {}
    passes: list[ReconPass] = []
    for row in rows:
        inventory = held.setdefault(row.pid, set())
        symbol = _SYMBOL.search(row.text)
        if _OPENED in row.text:
            if symbol is not None:
                inventory.add(symbol.group(1))
        elif any(marker in row.text for marker in _CLOSED):
            if symbol is not None:
                inventory.discard(symbol.group(1))
        elif _PASS in row.text:
            count = _POSITIONS.search(row.text)
            positions = int(count.group(1)) if count is not None else -1
            passes.append(ReconPass(row, positions, frozenset(inventory), parse_states(row.text)))
    return passes


def can_break(candidate: ReconPass, trusted: frozenset[str] = TRUSTED_STATES) -> bool:
    """R-DP: the pass covered every open position and reported only trusted states."""
    if candidate.states is None or candidate.positions < 1:
        return False
    if candidate.positions != len(candidate.inventory):
        return False
    return all(name in trusted for name, _count in candidate.states)


def attach_untrusted(rows: Sequence[LogRow], passes: Sequence[ReconPass]) -> dict[int, Attachment]:
    """Give each untrusted line to the nearest pass of its own process within fifteen seconds, by pass line number."""
    by_pid: dict[str, list[ReconPass]] = {}
    for candidate in passes:
        by_pid.setdefault(candidate.row.pid, []).append(candidate)
    ordered = {
        pid: sorted(group, key=lambda item: (item.row.stamp, item.row.number))
        for pid, group in by_pid.items()
    }
    stamps = {pid: [item.row.stamp for item in group] for pid, group in ordered.items()}
    symbols: dict[int, set[str]] = {}
    first_line: dict[int, int] = {}
    for row in rows:
        if _UNTRUSTED not in row.text or row.pid not in ordered:
            continue
        low = bisect_left(stamps[row.pid], row.stamp - _NEAR)
        near: list[ReconPass] = []
        for candidate in ordered[row.pid][low:]:
            if candidate.row.stamp > row.stamp + _NEAR:
                break
            near.append(candidate)
        if not near:
            continue
        pick = min(
            near,
            key=lambda item: (abs(item.row.stamp - row.stamp), abs(item.row.number - row.number)),
        )
        named = _SYMBOLS.search(row.text)
        names = set(named.group(1).split(",")) if named is not None else set()
        symbols.setdefault(pick.row.number, set()).update(names)
        first_line[pick.row.number] = min(first_line.get(pick.row.number, row.number), row.number)
    return {
        number: Attachment(frozenset(names), first_line[number])
        for number, names in symbols.items()
    }


def _is_refusal(text: str) -> bool:
    crk = "event=risk_refused" in text and "stage=committed_risk_unknown" in text
    halted = "event=dispatch_refused" in text and "reason=close_halted" in text
    return crk or halted


def latch_episodes(lines: Sequence[str], *, closed_at: datetime) -> tuple[LatchEpisode, ...]:
    """The latch episodes of a capture under R-DM, R-DO and R-DP, in start order.

    ``closed_at`` is M: the end of an interval whose process has neither a clean-stop line nor a successor.
    """
    rows = read_rows(lines)
    by_number = {row.number: row for row in rows}
    order: list[str] = []
    last: dict[str, datetime] = {}
    clean: set[str] = set()
    for row in rows:
        if row.pid not in last:
            order.append(row.pid)
        last[row.pid] = max(last.get(row.pid, row.stamp), row.stamp)
        if _STOPPED in row.text:
            clean.add(row.pid)
    refusals = [row for row in rows if _is_refusal(row.text)]
    passes = build_passes(rows)
    attached = attach_untrusted(rows, passes)
    by_pid: dict[str, list[ReconPass]] = {}
    for candidate in passes:
        by_pid.setdefault(candidate.row.pid, []).append(candidate)

    episodes: list[LatchEpisode] = []

    def close(run: _Run, broken_at: datetime | None) -> None:
        limit = broken_at if broken_at is not None else last[run.pid]
        seen = sum(1 for row in refusals if row.pid == run.pid and run.start <= row.stamp <= limit)
        if not seen:
            return
        stopped = run.pid in clean or order.index(run.pid) + 1 < len(order)
        if broken_at is not None:
            end, kind = broken_at, "breaking pass"
        elif stopped:
            end, kind = last[run.pid], "last line of the process"
        else:
            end, kind = closed_at, "open, closed at M"
        episodes.append(
            LatchEpisode(
                run.pid, tuple(sorted(run.symbols)), run.start, end, kind, run.passes, seen
            )
        )

    for pid in order:
        current: _Run | None = None
        for candidate in by_pid.get(pid, []):
            if current is not None and can_break(candidate):
                close(current, candidate.row.stamp)
                current = None
            attachment = attached.get(candidate.row.number)
            if attachment is None:
                continue
            if current is None:
                current = _Run(pid, by_number[attachment.first_line].stamp)
            current.passes += 1
            current.symbols |= attachment.symbols
        if current is not None:
            close(current, None)
    return tuple(sorted(episodes, key=lambda episode: (episode.start, episode.pid)))


def latch_intervals(episodes: Sequence[LatchEpisode]) -> list[DownInterval]:
    """The episodes as the frozen tool's own interval type, so its exclusion applies to them unchanged."""
    return [
        DownInterval(episode.start, episode.end, episode.pid, episode.pid) for episode in episodes
    ]


def merge_intervals(intervals: Sequence[DownInterval]) -> tuple[DownInterval, ...]:
    """Sort by start and merge intervals that overlap or abut, keeping the first's start and the last's end."""
    merged: list[DownInterval] = []
    for interval in sorted(intervals, key=lambda item: (item.start, item.end)):
        if merged and interval.start <= merged[-1].end:
            previous = merged[-1]
            merged[-1] = DownInterval(
                previous.start,
                max(previous.end, interval.end),
                previous.before_pid,
                interval.after_pid if interval.end >= previous.end else previous.after_pid,
            )
        else:
            merged.append(interval)
    return tuple(merged)


def _hours(delta: timedelta) -> Decimal:
    return (Decimal(delta.total_seconds()) / _SECONDS_PER_HOUR).quantize(Decimal("0.001"))


def render_latches(
    episodes: Sequence[LatchEpisode],
    union: Sequence[DownInterval],
    *,
    closed_at: datetime,
) -> list[str]:
    """The header, the rulings it applies, the trusted set, the episodes and the union that is excluded."""
    out = ["=" * 74, f"{HEADER}: the S4 comparison with latch intervals excluded too", "=" * 74]
    out.append("  figures only: no verdict, and nothing here changes the primary result (R-DK)")
    out.append("  rulings applied: R-DM, R-DO, R-DP (docs/S4_CORRECTION_P128.md, P129, P130)")
    out.append(
        f"  trusted states (core/portfolio.py _TRUSTED_PROTECTION): {', '.join(sorted(TRUSTED_STATES))}"
    )
    out.append(f"  an open interval is closed at M = {closed_at.isoformat()}")
    out.append("")
    out.append(f"LATCH EPISODES ({len(episodes)})")
    for episode in episodes:
        out.append(
            f"  {'/'.join(episode.symbols) or '-'} pid {episode.pid}: {episode.start.isoformat()} to "
            f"{episode.end.isoformat()} ({episode.end_kind}), {_hours(episode.end - episode.start)} h, "
            f"{episode.passes} untrusted pass(es), {episode.refusals} refusal(s)"
        )
    out.append("")
    out.append(f"EXCLUDED INTERVALS, the frozen downtime unioned with the latches ({len(union)})")
    for interval in union:
        out.append(f"  {interval.start.isoformat()} to {interval.end.isoformat()}")
    out.append("")
    return out


def main(argv: Sequence[str] | None = None) -> int:
    parser = _build_parser()
    parser.prog = "s4_latch_compare.py"
    parser.description = (
        "EXPLORATORY E2 (R-DL): compare S4's backtest with its live run, excluding latch intervals "
        "as well as downtime, and print figures, never a verdict."
    )
    args = parser.parse_args(argv)
    start, end = args.window_start, args.window_end
    if end <= start:
        print("REFUSED: --window-end must be after --window-start")
        return _REFUSED_EXIT
    try:
        reject_live_log(args.capture)
        if not args.capture.is_file():
            raise InputError(f"{args.capture} is not a file")
        lines = args.capture.read_text(encoding="utf-8", errors="replace").splitlines()
        boots = live_boots(lines)
        require_live_run_eligible(boots)
        record, all_backtest = load_backtest(args.run)
    except (CaptureRefusedError, EvidenceRefusedError) as exc:
        print(f"REFUSED: {exc}")
        return _REFUSED_EXIT
    except InputError as exc:
        print(f"INPUT ERROR: {exc}")
        return _INPUT_EXIT
    parsed = parse_capture(lines)
    all_trades = build_trades(parsed, args.quote_asset)
    log_path = args.backtest_log if args.backtest_log is not None else args.run / BACKTEST_LOG_NAME
    try:
        timeframes, fast, slow = strategy_facts(record)
        backtest_lines = (
            log_path.read_text(encoding="utf-8", errors="replace").splitlines()
            if log_path.is_file()
            else []
        )
        store_root = args.store if args.store is not None else Path(_data_dir(record))
        store = HistoricalStore(store_root) if store_root.is_dir() else None
        episodes = latch_episodes(lines, closed_at=end)
        union = merge_intervals([*down_intervals(lines), *latch_intervals(episodes)])
        live_in, unplaced = live_entries(all_trades, start=start, end=end)
        backtest_in = within(all_backtest, start=start, end=end)
        live, backtest, excluded = exclude_downtime(live_in, backtest_in, union, timeframes)
        matching = match_entries(live, backtest)
        checks = SeriesChecks(store, timeframes, fast, slow)
        backtest_signals = read_signals(backtest_lines)
        disagreements = diagnose(
            matching,
            live_signals=read_signals(lines),
            backtest_signals=backtest_signals,
            checks=checks,
            carried=carried_in(all_trades, start),
            timeframes=timeframes,
        )
        unfilled = [
            (placement, backtest_view_of(placement, backtest, backtest_signals))
            for placement in unfilled_placements(
                parsed.placements, all_trades, start=start, end=end
            )
            if in_downtime(
                placement.entry_bar_time,
                union,
                timeframe_delta(_timeframe_of(timeframes, placement.symbol)),
            )
            is None
        ]
    except InputError as exc:
        print(f"INPUT ERROR: {exc}")
        return _INPUT_EXIT
    figures = figures_of(live, backtest, matching)
    sources = {
        "capture sha256": digest_of(args.capture),
        "run.json sha256": digest_of(args.run / RUN_RECORD_NAME),
        "trades.csv sha256": digest_of(args.run / TRADES_NAME),
        "record schema": str(record.get("schema")),
        "recorded series": "unreadable" if store is None else str(store_root),
    }
    for text in render_latches(episodes, union, closed_at=end):
        print(text)
    for text in render(
        figures, matching, boots=boots, unplaced=unplaced, sources=sources, window=(start, end)
    ):
        print(text)
    for text in render_diagnosis(
        intervals=union, excluded=excluded, unfilled=unfilled, disagreements=disagreements
    ):
        print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
