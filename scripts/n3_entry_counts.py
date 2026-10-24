#!/usr/bin/env python
"""Count the entry events of the six M5n candidates over the in-sample archive series (N3, P142).

Usage:
    python scripts/n3_entry_counts.py                      # the committed window, the committed store
    python scripts/n3_entry_counts.py --data-dir DIR       # another store, same window

What it reads. The canonical store's archive 1d and 4h series for BTCUSDT and ETHUSDT, through
``HistoricalStore``, which only reads. The window is the half-open span
``[2017-08-17, 2024-01-01)`` of the research config (R-DT: no bar at or after the boundary is
read). ``--start`` and ``--end`` may NARROW it and may not widen it; a request outside it exits 2
before the store is opened. The script has no fetcher and makes no request of any venue.

What it prints. Counts, and nothing else: per series the bars stored, the grid slots the window
holds, the slots missing and the runs of gaps; per candidate and pair the entry events with the
gap rule on (R-DZ), the entry events with it off, the events the rule suppresses and the events
only the rule's recursive re-seeding creates. No price, no timestamp list and no return
(R-DT-3a), and no trade: an entry event is an UPPER BOUND on a trade, because a trade needs N4's
trailing exit and the one-position-per-pair rule.

How it counts. Each candidate is evaluated once per decision bar on the history up to that bar,
twice: ``enforce_gaps=True``, which is the candidate, and ``enforce_gaps=False``, which reads the
same rows as though they were consecutive. A non-recursive candidate reads only its window of
trailing rows, so it is handed exactly those; a recursive one (Keltner) is handed the whole
prefix, because its value depends on where the series was seeded. A bar before the candidate's
warm-up is skipped: neither reading can fire there.

Exit codes: 0 counted; 1 a stored series is unreadable or empty; 2 the requested window is outside
the committed one.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import TextIO

import numpy as np

import trading_bot.strategies.m5n  # noqa: F401  (registers the six candidates)
from trading_bot.core.models import Candle
from trading_bot.data.historical import (
    INTERVAL_MS,
    HistoricalDataError,
    HistoricalStore,
    StoredFileError,
)
from trading_bot.data.market_data import _build_frame
from trading_bot.strategies.m5n.base import M5nStrategy
from trading_bot.strategies.registry import create_strategy

DEFAULT_DATA_DIR = "data/historical"
IN_SAMPLE_START = datetime(2017, 8, 17, tzinfo=timezone.utc)
IN_SAMPLE_END = datetime(2024, 1, 1, tzinfo=timezone.utc)
PAIRS = ("BTCUSDT", "ETHUSDT")
TIMEFRAMES = ("1d", "4h")

#: The six candidates in R-DY's order, C1 to C6, with the timeframe each decides on.
CANDIDATES: tuple[tuple[str, str, str], ...] = (
    ("C1", "donchian_1d_20", "1d"),
    ("C2", "donchian_1d_55", "1d"),
    ("C3", "sma_cross_1d_50_200", "1d"),
    ("C4", "donchian_4h_20", "4h"),
    ("C5", "keltner_4h_20_2", "4h"),
    ("C6", "tsmom_1d_90", "1d"),
)


@dataclass(frozen=True)
class SeriesFacts:
    """What one stored series holds inside the window, as counts."""

    symbol: str
    timeframe: str
    bars: int
    slots: int
    missing: int
    gap_runs: int


@dataclass(frozen=True)
class EntryCounts:
    """Entry events of one candidate on one pair, with the gap rule on and off."""

    label: str
    name: str
    symbol: str
    timeframe: str
    gated: int
    ungated: int
    suppressed: int
    gated_only: int


def load_series(
    store: HistoricalStore, symbol: str, timeframe: str, start: datetime, end: datetime
) -> list[Candle]:
    """The stored closed candles of one series in ``[start, end)``, checked against the window.

    :raises ValueError: the window is not inside the committed in-sample span.
    :raises StoredFileError: a month file is missing or no longer matches its manifest.
    """
    check_window(start, end)
    found = list(store.candles(symbol, timeframe, start, end))
    for candle in found:
        if not start <= candle.open_time < end:
            raise ValueError(f"{symbol} {timeframe}: a bar outside [start, end) was served")
    return found


def check_window(start: datetime, end: datetime) -> None:
    """Refuse a window that is not a non-empty narrowing of the committed in-sample span."""
    if start.tzinfo is None or end.tzinfo is None:
        raise ValueError("start and end must be timezone-aware")
    if start < IN_SAMPLE_START or end > IN_SAMPLE_END or not start < end:
        raise ValueError(
            "the window must lie inside [2017-08-17, 2024-01-01) and be non-empty (R-DT)"
        )


def series_facts(
    candles: Sequence[Candle], symbol: str, timeframe: str, end: datetime
) -> SeriesFacts:
    """Bars, grid slots and gaps of one series: slots run from its first bar to ``end``, exclusive."""
    if not candles:
        return SeriesFacts(symbol, timeframe, 0, 0, 0, 0)
    width = INTERVAL_MS[timeframe]
    first_ms = int(candles[0].open_time.timestamp() * 1000)
    end_ms = int(end.timestamp() * 1000)
    slots = -((first_ms - end_ms) // width)
    opens = np.array([int(c.open_time.timestamp() * 1000) for c in candles], dtype=np.int64)
    steps = np.diff(opens)
    return SeriesFacts(
        symbol=symbol,
        timeframe=timeframe,
        bars=len(candles),
        slots=slots,
        missing=slots - len(candles),
        gap_runs=int(np.count_nonzero(steps != width)),
    )


def _strategy(name: str, *, enforce_gaps: bool) -> M5nStrategy:
    built = create_strategy(name, enforce_gaps=enforce_gaps)
    if not isinstance(built, M5nStrategy):
        raise TypeError(f"{name} is not an M5n candidate")
    return built


def count_entries(
    candles: Sequence[Candle], label: str, name: str, symbol: str, timeframe: str
) -> EntryCounts:
    """Entry events of one candidate over one series, gap rule on and off, bar by bar."""
    gated_rule = _strategy(name, enforce_gaps=True)
    plain_rule = _strategy(name, enforce_gaps=False)
    frame = _build_frame(candles)
    warmup = gated_rule.warmup_period
    recursive = gated_rule.recursive
    gated = ungated = suppressed = gated_only = 0
    for i in range(warmup - 1, len(candles)):
        start = 0 if recursive else i + 1 - warmup
        view = frame.iloc[start : i + 1]
        on = gated_rule.generate_signal(symbol, view, last_candle=candles[i]) is not None
        off = plain_rule.generate_signal(symbol, view, last_candle=candles[i]) is not None
        gated += on
        ungated += off
        suppressed += off and not on
        gated_only += on and not off
    return EntryCounts(label, name, symbol, timeframe, gated, ungated, suppressed, gated_only)


def render(facts: Sequence[SeriesFacts], counts: Sequence[EntryCounts]) -> list[str]:
    """The printed report: counts only."""
    lines = [
        "N3 entry-event counts. Each is an UPPER BOUND on trades: a trade needs N4's trailing exit",
        "and the one-position-per-pair rule. An event is an edge (true now, false on the bar before).",
        "",
        f"{'series':<16}{'bars':>7}{'slots':>7}{'missing':>9}{'gap_runs':>10}",
    ]
    lines += [
        f"{f'{f.symbol} {f.timeframe}':<16}{f.bars:>7}{f.slots:>7}{f.missing:>9}{f.gap_runs:>10}"
        for f in facts
    ]
    lines += [
        "",
        f"{'candidate':<24}{'pair':<10}{'events':>8}{'no_rdz':>8}{'suppressed':>12}{'gated_only':>12}",
    ]
    lines += [
        f"{f'{c.label} {c.name}':<24}{c.symbol:<10}{c.gated:>8}{c.ungated:>8}"
        f"{c.suppressed:>12}{c.gated_only:>12}"
        for c in counts
    ]
    lines += [
        "",
        "events = the candidate (R-DZ on); no_rdz = the same rows read as consecutive;",
        "suppressed = an event no_rdz has and the candidate lacks; gated_only = the converse.",
    ]
    return lines


def run(root: Path, start: datetime, end: datetime) -> list[str]:
    """Count every candidate on every pair over ``[start, end)`` and return the report."""
    store = HistoricalStore(root)
    series: dict[tuple[str, str], list[Candle]] = {}
    for symbol in PAIRS:
        for timeframe in TIMEFRAMES:
            found = load_series(store, symbol, timeframe, start, end)
            if not found:
                raise StoredFileError(f"{symbol} {timeframe}: no bars in the window")
            series[(symbol, timeframe)] = found
    facts = [
        series_facts(series[(symbol, timeframe)], symbol, timeframe, end)
        for timeframe in TIMEFRAMES
        for symbol in PAIRS
    ]
    counts = [
        count_entries(series[(symbol, timeframe)], label, name, symbol, timeframe)
        for label, name, timeframe in CANDIDATES
        for symbol in PAIRS
    ]
    return render(facts, counts)


def _utc(text: str) -> datetime:
    return datetime.strptime(text, "%Y-%m-%d").replace(tzinfo=timezone.utc)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0] if __doc__ else None)
    parser.add_argument("--data-dir", default=DEFAULT_DATA_DIR, help="backtesting.data_dir")
    parser.add_argument(
        "--start", default="2017-08-17", help="window start, YYYY-MM-DD, may narrow"
    )
    parser.add_argument("--end", default="2024-01-01", help="window end, exclusive, may narrow")
    return parser


def main(argv: Sequence[str] | None = None, out: TextIO | None = None) -> int:
    sink = out if out is not None else sys.stdout
    args = _parser().parse_args(argv)
    try:
        start, end = _utc(args.start), _utc(args.end)
        check_window(start, end)
    except ValueError as exc:
        print(f"refused: {exc}", file=sys.stderr)
        return 2
    try:
        report = run(Path(args.data_dir), start, end)
    except HistoricalDataError as exc:
        print(f"unreadable: {exc}", file=sys.stderr)
        return 1
    print("\n".join(report), file=sink)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
