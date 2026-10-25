#!/usr/bin/env python
"""Count the trades of the six M5n candidates over the in-sample span, and print counts only (N4b, P144).

Usage:
    python scripts/n4_trade_counts.py                    # config.m5n.yaml, data/historical, the committed window
    python scripts/n4_trade_counts.py --config PATH --data-dir DIR

What it runs. Each of the six candidates (R-DY) is run once through the backtester over BTCUSDT and
ETHUSDT on its own decision timeframe, with the D1 trail as the exit (charter section 17), over
``[2017-08-17, 2024-01-01)`` (R-DT: ``--start`` and ``--end`` may NARROW the window and may not widen it;
a request outside it exits 2 before the store is opened). The simulation computes P&L, equity and risk
state internally, because sizing and the risk refusals need them, and **prints, logs and persists none
of it** (R-DT-3d).

What it prints. A fixed schema of integers and nothing else: per candidate and pair the signals, the
trades, the positions OPEN at the end, the entry outcomes, the clamp counts, the refusal counts by
``RefusalStage`` and the delta quantiles in basis points. There is no price, no return, no equity, no
balance and no realised figure, and no run record or trade file is written: ``write_run`` is never
called and this script opens nothing for writing.

Logging. ``trading_bot.utils.logger.get_logger`` configures the root logger at INFO with a stderr handler
the first time any module asks for a logger, and at INFO the risk manager and the intent logger write the
size and price of every order. So before the first candidate runs this script takes every handler off the
root logger, sets it to WARNING, and attaches one handler of its own that keeps each record's message in
memory and prints nothing; the handlers and the level are put back afterwards. Nothing the run logs
reaches a terminal or a file, and what was kept is scanned.

The scan. Every line is built as text first and checked BEFORE anything is printed, against a grammar of
the line shapes above, a vocabulary of forbidden words and a bound on every integer; so are the records
that logging captured at WARNING and above. A line that fails is never printed, and the verdict names
only how many failed. The output ends with the SHA-256 of every line before it.

Exit codes: 0 counted and the scan clean; 1 a run was incomplete or the scan failed; 2 the requested
window is outside the committed one, or the config or store could not be read.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import logging
import re
import sys
import traceback
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path
from typing import TextIO

import trading_bot.strategies.m5n  # noqa: F401  (registers the six candidates)
from trading_bot.backtesting.d1_executor import D1Executor
from trading_bot.backtesting.engine import backtest_system
from trading_bot.backtesting.overrides import apply_overrides, build_overrides
from trading_bot.backtesting.simulated_executor import EntryResult
from trading_bot.config.settings import Secrets, Settings, get_settings
from trading_bot.core.enums import RefusalStage
from trading_bot.core.exceptions import TradingBotError

DEFAULT_CONFIG = "config.m5n.yaml"
DEFAULT_DATA_DIR = "data/historical"
IN_SAMPLE_START = datetime(2017, 8, 17, tzinfo=timezone.utc)
IN_SAMPLE_END = datetime(2024, 1, 1, tzinfo=timezone.utc)
PAIRS = ("BTCUSDT", "ETHUSDT")
QUANTILES = (10, 25, 50, 75, 90)

#: The six candidates in R-DY's order, C1 to C6, with the timeframe each decides on.
CANDIDATES: tuple[tuple[str, str, str], ...] = (
    ("C1", "donchian_1d_20", "1d"),
    ("C2", "donchian_1d_55", "1d"),
    ("C3", "sma_cross_1d_50_200", "1d"),
    ("C4", "donchian_4h_20", "4h"),
    ("C5", "keltner_4h_20_2", "4h"),
    ("C6", "tsmom_1d_90", "1d"),
)

_STAGES = tuple(stage.value for stage in RefusalStage)
_MAX_INTEGER = 99_999
_WORDS = re.compile(
    r"(?<![A-Za-z])(prices?|pnl|p&l|returns?|equity|balances?|realis\w*|profits?|loss(es)?|fees?|"
    r"cash|notional|quote|drawdown|sharpe|free|cost|gross|net)(?![A-Za-z])",
    re.IGNORECASE,
)
_TIMESTAMP = re.compile(r"\d{4}-\d{2}-\d{2}([T ]\d{2}:\d{2}(:\d{2}(\.\d+)?)?)?(\+\d{2}:\d{2}|Z)?")
_DECIMAL = re.compile(r"\d+\.\d+")
_LONG_INTEGER = re.compile(r"\d{4,}")
_INTEGER = re.compile(r"\d+")

_I = r"\d{1,5}"
_LINE_SHAPES: tuple[re.Pattern[str], ...] = (
    re.compile(r"N4b trade counts \(R-DT-3d outputs only\)"),
    re.compile(r"window \[\d{4}-\d{2}-\d{2}, \d{4}-\d{2}-\d{2}\)"),
    re.compile(r"candidate C[1-6] [a-z0-9_]+ \((1d|4h)\)"),
    re.compile(r"  run complete=(yes|no) problems=" + _I),
    re.compile(
        r"  [A-Z]{6,12} signals="
        + _I
        + r" trades="
        + _I
        + r" open_at_end="
        + _I
        + r" entries_filled="
        + _I
        + r" fok_refused="
        + _I
        + r" expired="
        + _I
        + r" unaffordable="
        + _I
        + r" clamp_upper="
        + _I
        + r" clamp_lower="
        + _I
    ),
    re.compile(
        r"  [A-Z]{6,12} refusals( [a-z_]+=" + _I + r")+",
    ),
    re.compile(r"  [A-Z]{6,12} delta_bps n=0"),
    re.compile(
        r"  [A-Z]{6,12} delta_bps n=" + _I + r"( p\d{2}=" + _I + r")+ min=" + _I + r" max=" + _I
    ),
    re.compile(
        r"scan verdict=(CLEAN|FAILED) output_lines="
        + _I
        + r" log_records="
        + _I
        + r"( violations="
        + _I
        + r")?"
    ),
    re.compile(r"output_sha256=[0-9a-f]{64}"),
)
_HASH_LINE = re.compile(r"output_sha256=[0-9a-f]{64}")


class WindowError(ValueError):
    """The requested window is not a non-empty narrowing of the committed in-sample span."""


def check_window(start: datetime, end: datetime) -> None:
    """Refuse a window that is not a non-empty narrowing of the committed in-sample span."""
    if start.tzinfo is None or end.tzinfo is None:
        raise WindowError("start and end must be timezone-aware")
    if start < IN_SAMPLE_START or end > IN_SAMPLE_END or not start < end:
        raise WindowError(
            "the window must lie inside [2017-08-17, 2024-01-01) and be non-empty (R-DT)"
        )


@dataclass(frozen=True)
class PairCounts:
    """One candidate on one pair, as counts."""

    symbol: str
    signals: int
    trades: int
    open_at_end: int
    entries_filled: int
    fok_refused: int
    expired: int
    unaffordable: int
    clamp_upper: int
    clamp_lower: int
    refusals: tuple[tuple[str, int], ...]
    deltas: tuple[int, ...]


@dataclass(frozen=True)
class CandidateCounts:
    label: str
    name: str
    timeframe: str
    complete: bool
    problems: int
    pairs: tuple[PairCounts, ...] = field(default_factory=tuple)


def quantile(sorted_values: Sequence[int], percent: int) -> int:
    """The nearest-rank quantile of an ascending, non-empty sequence."""
    rank = -(-percent * len(sorted_values) // 100)
    return sorted_values[max(rank, 1) - 1]


def render(window: tuple[date, date], results: Sequence[CandidateCounts]) -> list[str]:
    """The output lines, as the fixed schema; nothing but integers, symbols, stage names and dates."""
    lines = [
        "N4b trade counts (R-DT-3d outputs only)",
        f"window [{window[0].isoformat()}, {window[1].isoformat()})",
    ]
    for result in results:
        lines.append(f"candidate {result.label} {result.name} ({result.timeframe})")
        lines.append(
            f"  run complete={'yes' if result.complete else 'no'} problems={result.problems}"
        )
        for pair in result.pairs:
            lines.append(
                f"  {pair.symbol} signals={pair.signals} trades={pair.trades}"
                f" open_at_end={pair.open_at_end} entries_filled={pair.entries_filled}"
                f" fok_refused={pair.fok_refused} expired={pair.expired}"
                f" unaffordable={pair.unaffordable} clamp_upper={pair.clamp_upper}"
                f" clamp_lower={pair.clamp_lower}"
            )
            lines.append(
                f"  {pair.symbol} refusals "
                + " ".join(f"{stage}={count}" for stage, count in pair.refusals)
            )
            ordered = sorted(pair.deltas)
            if not ordered:
                lines.append(f"  {pair.symbol} delta_bps n=0")
            else:
                cuts = " ".join(f"p{p:02d}={quantile(ordered, p)}" for p in QUANTILES)
                lines.append(
                    f"  {pair.symbol} delta_bps n={len(ordered)} {cuts}"
                    f" min={ordered[0]} max={ordered[-1]}"
                )
    return lines


def scan_lines(lines: Sequence[str]) -> int:
    """How many output lines break the grammar, the vocabulary or the integer bound."""
    bad = 0
    for line in lines:
        if not line.isascii() or not any(shape.fullmatch(line) for shape in _LINE_SHAPES):
            bad += 1
            continue
        if _HASH_LINE.fullmatch(line):
            continue
        stripped = _TIMESTAMP.sub("", line)
        if (
            _forbidden_word(line)
            or _DECIMAL.search(stripped)
            or any(int(token) > _MAX_INTEGER for token in _INTEGER.findall(stripped))
        ):
            bad += 1
    return bad


def _forbidden_word(text: str) -> bool:
    """A forbidden word outside a stage name: ``no_mark_price`` is a stage, ``price`` is a figure."""
    without_stages = text
    for stage in _STAGES:
        without_stages = without_stages.replace(f"{stage}=", "=")
    return _WORDS.search(without_stages) is not None


def scan_log(message: str) -> bool:
    """``True`` when a captured log message looks as if it carries a figure it must not."""
    text = _TIMESTAMP.sub("", message)
    return bool(
        "$" in text or _forbidden_word(text) or _DECIMAL.search(text) or _LONG_INTEGER.search(text)
    )


class _Capture(logging.Handler):
    """Keeps the formatted message of every record at WARNING and above; prints nothing."""

    def __init__(self) -> None:
        super().__init__(level=logging.WARNING)
        self.messages: list[str] = []

    def emit(self, record: logging.LogRecord) -> None:
        try:
            self.messages.append(record.getMessage())
        except Exception:
            self.messages.append(str(record.msg))


def _pair_counts(
    symbol: str, executor: D1Executor, trades: Counter[str], open_symbols: set[str]
) -> PairCounts:
    tally = executor.tallies.get(symbol)
    attempts = [a for a in executor.attempts if a.symbol == symbol]
    by_result = Counter(a.result for a in attempts)
    refusals = tally.refusals if tally is not None else {}
    return PairCounts(
        symbol=symbol,
        signals=0 if tally is None else tally.signals,
        trades=trades[symbol],
        open_at_end=1 if symbol in open_symbols else 0,
        entries_filled=by_result[EntryResult.FILLED],
        fok_refused=by_result[EntryResult.REFUSED],
        expired=by_result[EntryResult.EXPIRED],
        unaffordable=by_result[EntryResult.UNAFFORDABLE],
        clamp_upper=0 if tally is None else tally.clamp_upper,
        clamp_lower=0 if tally is None else tally.clamp_lower,
        refusals=tuple((stage, refusals.get(RefusalStage(stage), 0)) for stage in _STAGES),
        deltas=() if tally is None else tuple(tally.deltas),
    )


async def run_candidate(
    base: Settings, label: str, name: str, timeframe: str, window_args: dict[str, object]
) -> CandidateCounts:
    """Run one candidate over both pairs; keep only its counts."""
    effective = apply_overrides(base.config, build_overrides(strategy=name, timeframe=timeframe))
    settings = Settings(
        effective,
        Secrets(),
        config_path=base.config_path,
        config_sha256=base.config_sha256,
    )
    window = effective.backtesting.model_copy(update=window_args)
    async with backtest_system(
        settings,
        window=window,
        exchange_info_environment=effective.backtesting.exchange_info_environment,
        code_facts=lambda: {},
    ) as system:
        result = await system.run()
        executor = system.executor
        if not isinstance(executor, D1Executor):
            raise TradingBotError(f"{name} did not take the D1 executor")
        trades = Counter(trade.symbol for trade in result.trades)
        open_symbols = set(executor.unsettled["open_positions"])
        pairs = tuple(_pair_counts(symbol, executor, trades, open_symbols) for symbol in PAIRS)
        return CandidateCounts(
            label=label,
            name=name,
            timeframe=timeframe,
            complete=result.complete,
            problems=len(result.problems),
            pairs=pairs,
        )


def _parse_date(text: str) -> date:
    return date.fromisoformat(text)


def _dates(args: argparse.Namespace) -> tuple[date, date]:
    start = _parse_date(args.start) if args.start else IN_SAMPLE_START.date()
    end = _parse_date(args.end) if args.end else IN_SAMPLE_END.date()
    return start, end


def _midnight(day: date) -> datetime:
    return datetime(day.year, day.month, day.day, tzinfo=timezone.utc)


def main(argv: Sequence[str] | None = None, out: TextIO | None = None) -> int:
    stream = out if out is not None else sys.stdout
    parser = argparse.ArgumentParser(description="Count M5n trades; counts only (N4b).")
    parser.add_argument("--config", default=DEFAULT_CONFIG)
    parser.add_argument("--data-dir", default=DEFAULT_DATA_DIR)
    parser.add_argument("--start")
    parser.add_argument("--end")
    args = parser.parse_args(argv)
    start_day, end_day = _dates(args)
    try:
        check_window(_midnight(start_day), _midnight(end_day))
    except WindowError as exc:
        print(f"refused: {exc}", file=sys.stderr)
        return 2
    capture = _Capture()
    root = logging.getLogger()
    saved_handlers, saved_level = list(root.handlers), root.level
    for handler in saved_handlers:
        root.removeHandler(handler)
    root.setLevel(logging.WARNING)
    root.addHandler(capture)
    try:
        base = get_settings(args.config)
        window_args: dict[str, object] = {
            "data_dir": args.data_dir,
            "start_date": start_day,
            "end_date": end_day,
        }
        results = [
            asyncio.run(run_candidate(base, label, name, timeframe, window_args))
            for label, name, timeframe in CANDIDATES
        ]
    except Exception as exc:
        frame = traceback.extract_tb(exc.__traceback__)[-1]
        print(
            f"error: {type(exc).__name__} at {Path(frame.filename).name}:{frame.lineno}",
            file=sys.stderr,
        )
        return 2
    finally:
        root.removeHandler(capture)
        root.setLevel(saved_level)
        for handler in saved_handlers:
            root.addHandler(handler)
    lines = render((start_day, end_day), results)
    flagged_lines = scan_lines(lines)
    flagged_logs = sum(1 for message in capture.messages if scan_log(message))
    clean = flagged_lines == 0 and flagged_logs == 0
    verdict = (
        f"scan verdict={'CLEAN' if clean else 'FAILED'} output_lines={len(lines)}"
        f" log_records={len(capture.messages)}"
    )
    if not clean:
        verdict += f" violations={flagged_lines + flagged_logs}"
        print(verdict, file=stream)
        return 1
    digest = hashlib.sha256("".join(f"{line}\n" for line in [*lines, verdict]).encode("ascii"))
    for line in (*lines, verdict, f"output_sha256={digest.hexdigest()}"):
        print(line, file=stream)
    return 0 if all(result.complete for result in results) else 1


if __name__ == "__main__":
    sys.exit(main())
