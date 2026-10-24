#!/usr/bin/env python
"""DIAGNOSTIC R-DR/R-DS: annotate each entry in a disagreement list with whether a wick occurred while it was held.

``scripts/s4_compare.py`` is frozen and its comparison is the pre-registered one (R-DK). This script rebuilds the
disagreement list of ONE analysis, the primary, E1 or E2 (``--analysis``), through the frozen functions and the committed
E2 wrapper, and annotates every entry in it, as the project owner ruled at P134 (R-DR, ``docs/S4_CORRECTION_P134.md``)
and P135 (R-DS, ``docs/S4_CORRECTION_P135.md``). It recomputes no A, B or C figure, excludes nothing, is not an
exploratory analysis under R-DL, and names no verdict.

**THE ANNOTATION.** A 1m bar of the entry's pair is WIDE when ``(high - low) / open >= 3%`` and its open is positive: the
inequality is not strict at the bound, so 3% is wide and 2.999% is not. The interval is R-DS's: for a matched entry the
union of the live and the backtest holding periods, for a backtest-only entry the backtest's, for a live-only entry the
live one. A holding period is HALF OPEN, ``[entry bar open, exit bar close)``, and a 1m bar is inside it when its open
time is at or after the start and before the end. The exit bar's close is, on the backtest side, the ``exit_bar_open``
column plus the pair's timeframe; live, for a strategy ``CLOSE`` the booking's candle time plus one millisecond (the
signal bar's close), and for a protective-leg fill the close of the pair-timeframe bar that contains the fill instant.
A side with no exit instant is read as open at M, and M is ``--window-end``. An interval that holds no 1m bar of the pair
in the store is ``unknown``, never ``no``.

Inputs, refusals and exit statuses are ``s4_compare.py``'s own, plus ``--analysis``: a path under ``logs/`` is refused
before a byte is read, the live boots and the backtest record go through the evidence door, and the recorded 1m series
is read through the repository's own historical-store reader, never written. Run it with the S4 clone's interpreter
from the development tree's script path, as for E2.
"""

from __future__ import annotations

import csv
import sys
from collections import Counter
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from typing import Final

from run_census import CaptureRefusedError, digest_of, reject_live_log
from s4_compare import (
    _INPUT_EXIT,
    _REFUSED_EXIT,
    BACKTEST_LOG_NAME,
    CAUSES,
    TRADES_NAME,
    BacktestEntry,
    Disagreement,
    InputError,
    Matching,
    SeriesChecks,
    _build_parser,
    _data_dir,
    _instant,
    _timeframe_of,
    carried_in,
    diagnose,
    down_intervals,
    exclude_downtime,
    live_boots,
    live_entries,
    load_backtest,
    match_entries,
    read_signals,
    require_live_run_eligible,
    strategy_facts,
    timeframe_delta,
    within,
)
from s4_latch_compare import latch_episodes, latch_intervals, merge_intervals
from trade_census import Route, Trade, build_trades, parse_capture

from trading_bot.backtesting.evidence import (
    RUN_RECORD_NAME,
    EvidenceRefusedError,
    require_evidence_eligible,
)
from trading_bot.data.historical import HistoricalDataError, HistoricalStore

__all__ = [
    "ANALYSES",
    "HEADER",
    "WIDE_THRESHOLD",
    "Analysis",
    "Annotation",
    "Bar",
    "Holding",
    "Row",
    "annotate",
    "annotate_rows",
    "backtest_exit_closes",
    "bar_range",
    "build_analysis",
    "floor_to_bar",
    "live_exit_close",
    "live_exit_closes",
    "main",
    "render",
    "store_reader",
]

HEADER: Final = "DIAGNOSTIC R-DR/R-DS"
ANALYSES: Final = ("primary", "e1", "e2")
WIDE_THRESHOLD: Final = Decimal("0.03")
_ONE_MS: Final = timedelta(milliseconds=1)
_EPOCH: Final = datetime(1970, 1, 1, tzinfo=timezone.utc)
_PERCENT_PLACES: Final = Decimal("0.000001")
_HUNDRED: Final = Decimal(100)
_SERIES: Final = "1m"


@dataclass(frozen=True)
class Bar:
    """One recorded 1m bar: its open time and the three prices the range reads."""

    open_time: datetime
    open: Decimal
    high: Decimal
    low: Decimal


@dataclass(frozen=True)
class Holding:
    """A holding period, half open: from the entry bar's open to the exit bar's close."""

    start: datetime
    end: datetime


@dataclass(frozen=True)
class Annotation:
    """Whether a wide bar lay inside a holding period, and the widest range found there."""

    wide: str
    widest: Decimal | None
    bars: int


@dataclass(frozen=True)
class Row:
    """One disagreement, the interval R-DS gives it and its annotation."""

    kind: str
    symbol: str
    entry_bar_open: datetime
    cause: str
    holding: Holding
    annotation: Annotation


@dataclass(frozen=True)
class Analysis:
    """One analysis's matching and the disagreement list the frozen ``diagnose`` returned for it."""

    name: str
    matching: Matching
    disagreements: tuple[Disagreement, ...]


BarReader = Callable[[str, datetime, datetime], Sequence[Bar] | None]
ExitTable = Mapping[tuple[str, datetime], datetime]


def bar_range(bar: Bar) -> Decimal | None:
    """``(high - low) / open``, or ``None`` for a bar whose open is not positive."""
    if bar.open <= 0:
        return None
    return (bar.high - bar.low) / bar.open


def annotate(
    bars: Sequence[Bar] | None, holding: Holding, *, threshold: Decimal = WIDE_THRESHOLD
) -> Annotation:
    """``yes`` when a bar opening in ``[start, end)`` has range at or above the threshold, ``unknown`` with no bar."""
    if bars is None:
        return Annotation("unknown", None, 0)
    ranges: list[Decimal] = []
    for bar in bars:
        if holding.start <= bar.open_time < holding.end:
            value = bar_range(bar)
            if value is not None:
                ranges.append(value)
    if not ranges:
        return Annotation("unknown", None, 0)
    widest = max(ranges)
    return Annotation("yes" if widest >= threshold else "no", widest, len(ranges))


def floor_to_bar(moment: datetime, bar: timedelta) -> datetime:
    """The open of the epoch-aligned bar that contains ``moment``."""
    return _EPOCH + ((moment - _EPOCH) // bar) * bar


def live_exit_close(trade: Trade, bar: timedelta, window_end: datetime) -> datetime:
    """The close of the exit bar of a live booking; ``window_end`` when the booking has no exit instant."""
    moment = trade.exit_time
    if moment is None:
        return window_end
    if moment.tzinfo is None:
        raise InputError(f"booking line {trade.booking.line_no}: the exit instant carries no zone")
    if trade.route is Route.CLOSE:
        return moment + _ONE_MS
    return floor_to_bar(moment, bar) + bar


def live_exit_closes(
    trades: Sequence[Trade], timeframes: Mapping[str, str], window_end: datetime
) -> dict[tuple[str, datetime], datetime]:
    """Each placed live trade's exit bar close, keyed on (symbol, entry bar open)."""
    closes: dict[tuple[str, datetime], datetime] = {}
    for trade in trades:
        placement = trade.placement
        if placement is None:
            continue
        bar = timeframe_delta(_timeframe_of(timeframes, placement.symbol))
        closes[(placement.symbol, placement.entry_bar_time + _ONE_MS)] = live_exit_close(
            trade, bar, window_end
        )
    return closes


def backtest_exit_closes(path: Path, window_end: datetime) -> dict[tuple[str, datetime], datetime]:
    """Each ``trades.csv`` row's exit bar close, keyed on (symbol, entry bar open).

    :raises InputError: the file is unreadable or a row lacks a column the interval needs.
    """
    try:
        with path.open(encoding="utf-8", newline="") as handle:
            rows = list(csv.DictReader(handle))
    except OSError as exc:
        raise InputError(f"{path} cannot be read: {exc}") from exc
    closes: dict[tuple[str, datetime], datetime] = {}
    for number, row in enumerate(rows, start=2):
        where = f"{path} line {number}"
        key = (row.get("symbol", ""), _instant(row, "entry_bar_open", where))
        raw = row.get("exit_bar_open")
        if raw is None:
            raise InputError(f"{where}: column 'exit_bar_open' is missing")
        if not raw.strip():
            closes[key] = window_end
            continue
        timeframe = row.get("timeframe")
        if not timeframe:
            raise InputError(f"{where}: column 'timeframe' is missing or empty")
        closes[key] = _instant(row, "exit_bar_open", where) + timeframe_delta(timeframe)
    return closes


def store_reader(store: HistoricalStore | None) -> BarReader:
    """A reader of the recorded 1m series; ``None`` for a store that is absent or cannot serve the range."""

    def read(symbol: str, start: datetime, end: datetime) -> Sequence[Bar] | None:
        if store is None:
            return None
        try:
            return [
                Bar(candle.open_time, candle.open, candle.high, candle.low)
                for candle in store.candles(symbol, _SERIES, start, end)
            ]
        except HistoricalDataError:
            return None

    return read


def build_analysis(
    analysis: str,
    *,
    lines: Sequence[str],
    all_trades: Sequence[Trade],
    all_backtest: Sequence[BacktestEntry],
    backtest_lines: Sequence[str],
    timeframes: Mapping[str, str],
    fast: int,
    slow: int,
    store: HistoricalStore | None,
    start: datetime,
    end: datetime,
) -> Analysis:
    """Rebuild one analysis's disagreement list exactly as the frozen tool or the E2 wrapper does."""
    if analysis not in ANALYSES:
        raise InputError(f"unknown analysis {analysis!r}")
    intervals = down_intervals(lines)
    if analysis == "e2":
        intervals = merge_intervals(
            [*intervals, *latch_intervals(latch_episodes(lines, closed_at=end))]
        )
    live_in, _unplaced = live_entries(all_trades, start=start, end=end)
    backtest_in = within(all_backtest, start=start, end=end)
    live, backtest, _excluded = exclude_downtime(live_in, backtest_in, intervals, timeframes)
    matching = match_entries(live, backtest)
    disagreements = diagnose(
        matching,
        live_signals=read_signals(lines),
        backtest_signals=read_signals(backtest_lines),
        checks=SeriesChecks(store, timeframes, fast, slow),
        carried=carried_in(all_trades, start),
        timeframes=timeframes,
    )
    return Analysis(analysis, matching, disagreements)


def annotate_rows(
    analysis: Analysis,
    *,
    live_closes: ExitTable,
    backtest_closes: ExitTable,
    read_bars: BarReader,
) -> tuple[Row, ...]:
    """One annotated row per disagreement, in the list's own order.

    :raises InputError: a disagreement names an entry that neither side's exit table holds.
    """
    rows: list[Row] = []
    for item in analysis.disagreements:
        start = item.signal_close + _ONE_MS
        key = (item.symbol, start)
        by_kind: dict[str, tuple[ExitTable, ...]] = {
            "live only": (live_closes,),
            "backtest only": (backtest_closes,),
            "different exit": (live_closes, backtest_closes),
        }
        sides = by_kind.get(item.kind)
        if sides is None:
            raise InputError(f"unknown disagreement kind {item.kind!r}")
        ends: list[datetime] = []
        for table in sides:
            if key not in table:
                raise InputError(
                    f"{item.kind} {item.symbol} entry bar {start.isoformat()} has no exit bar close"
                )
            ends.append(table[key])
        holding = Holding(start, max(ends))
        rows.append(
            Row(
                item.kind,
                item.symbol,
                start,
                item.cause,
                holding,
                annotate(read_bars(item.symbol, holding.start, holding.end), holding),
            )
        )
    return tuple(rows)


def _percent(value: Decimal | None) -> str:
    if value is None:
        return "none"
    return f"{(value * _HUNDRED).quantize(_PERCENT_PLACES)}%"


def render(
    analysis: str,
    rows: Sequence[Row],
    *,
    window: tuple[datetime, datetime],
    sources: Mapping[str, str],
) -> list[str]:
    """The header, the sources, one row per disagreement and the counts by cause."""
    rule = "=" * 74
    out = [rule, HEADER, rule]
    out.append(f"  analysis                : {analysis}")
    out.append(f"  window (entry bar open) : [{window[0].isoformat()}, {window[1].isoformat()})")
    for name, value in sources.items():
        out.append(f"  {name:<23} : {value}")
    out.append(
        "  rulings applied         : R-DR (docs/S4_CORRECTION_P134.md), R-DS (docs/S4_CORRECTION_P135.md)"
    )
    out.append(
        f"  wide bar                : a 1m bar of the pair with (high - low) / open >= {WIDE_THRESHOLD * _HUNDRED}%"
    )
    out.append(
        "  interval                : half open [entry bar open, exit bar close) on 1m bar opens; "
        f"M is {window[1].isoformat()}"
    )
    out.append("  annotation only: no A, B or C figure is computed and nothing here is a verdict")
    out.append("")
    out.append(f"ANNOTATED DISAGREEMENTS ({len(rows)})")
    for row in rows:
        out.append(
            f"  {row.symbol} entry bar {row.entry_bar_open.isoformat()} [{row.cause}] {row.kind} "
            f"interval [{row.holding.start.isoformat()}, {row.holding.end.isoformat()}) "
            f"wide={row.annotation.wide} max_range={_percent(row.annotation.widest)}"
        )
    out.append("")
    out.append(f"COUNTS BY CAUSE ({len(rows)})")
    causes = [*CAUSES, *sorted({row.cause for row in rows} - set(CAUSES))]
    for cause in causes:
        tally = Counter(row.annotation.wide for row in rows if row.cause == cause)
        out.append(
            f"  {cause:<22}: {sum(tally.values())} "
            f"(wide yes {tally['yes']}, wide no {tally['no']}, unknown {tally['unknown']})"
        )
    return out


def main(argv: Sequence[str] | None = None) -> int:
    parser = _build_parser()
    parser.prog = "s4_wick_annotate.py"
    parser.description = HEADER + ": annotate a disagreement list with the wicks held through."
    parser.add_argument("--analysis", choices=ANALYSES, required=True)
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
        require_evidence_eligible(record, source=str(args.run / RUN_RECORD_NAME))
    except (CaptureRefusedError, EvidenceRefusedError) as exc:
        print(f"REFUSED: {exc}")
        return _REFUSED_EXIT
    except InputError as exc:
        print(f"INPUT ERROR: {exc}")
        return _INPUT_EXIT
    all_trades = build_trades(parse_capture(lines), args.quote_asset)
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
        analysis = build_analysis(
            args.analysis,
            lines=lines,
            all_trades=all_trades,
            all_backtest=all_backtest,
            backtest_lines=backtest_lines,
            timeframes=timeframes,
            fast=fast,
            slow=slow,
            store=store,
            start=start,
            end=end,
        )
        rows = annotate_rows(
            analysis,
            live_closes=live_exit_closes(all_trades, timeframes, end),
            backtest_closes=backtest_exit_closes(args.run / TRADES_NAME, end),
            read_bars=store_reader(store),
        )
    except InputError as exc:
        print(f"INPUT ERROR: {exc}")
        return _INPUT_EXIT
    sources = {
        "capture sha256": digest_of(args.capture),
        "run.json sha256": digest_of(args.run / RUN_RECORD_NAME),
        "trades.csv sha256": digest_of(args.run / TRADES_NAME),
        "recorded series": "unreadable" if store is None else str(store_root),
    }
    for text in render(args.analysis, rows, window=(start, end), sources=sources):
        print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
