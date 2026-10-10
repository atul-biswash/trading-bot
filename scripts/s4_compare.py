#!/usr/bin/env python
"""Compare S4's backtest with the live run it replays, and print FIGURES, never a verdict.

S4 asks one question: does the backtester agree with the venue (Testnet)? A live run of the committed
bot produced a frozen log capture; a backtest of the same window over klines recorded from the same
venue produced a run directory. This script lines them up and prints what it measured. **It prints no
PASS, no FAIL and no INCONCLUSIVE** (R-BE's principle, applied here): the acceptance tests and what
counts as a pass are written in ``docs/S4_PREREGISTRATION.md`` before the run, and a reader holds the
figures against them.

**BOTH SIDES GO THROUGH THE EVIDENCE DOOR FIRST (R-AR).** The backtest's ``run.json`` is read with
``load_eligible_record``, which refuses a record whose ``evidence_eligible`` is not exactly ``True``.
The live side has no ``run.json``; its record is the ``boot_provenance`` line of each boot in the
capture, judged by ``is_evidence_eligible`` -- the same function that sets the backtest's flag -- and
passed to ``require_evidence_eligible``. A capture with no such line is refused, because nothing
shows what code ran. Either refusal exits 2 before a figure is computed.

**WHAT IS COMPARED, AND ON WHAT KEY.** A live ENTRY is an ``order_placed`` line matched to its booking
by ``scripts/trade_census.py``; its entry bar is the bar after the signal bar, so its open is
``entry_bar_time + 1 ms``. A backtest entry is a ``trades.csv`` row with its ``entry_bar_open``. They
match when ``symbol`` and the entry bar's open are equal, each side used once. Everything is scoped to
one half-open window ``[--window-start, --window-end)`` on the entry bar's open.

**THE THREE R-C FIGURES**, and nothing is derived by dividing money: (1) the share of the live entries
that the backtest reproduced on the same symbol and entry bar; (2) the backtest's per-trade mean return
beside the live run's 95% interval (the census tool's: mean +/- 1.96 standard errors); (3) the two trade
counts and their difference as a share of the live count. A return is ``realised / entry quote total``
as a percentage, the census's own definition, so a fee of zero (S4's) makes gross and net the same.

Never reads the live log: a path under ``logs/`` is refused before a byte is read.
"""

from __future__ import annotations

import argparse
import csv
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path

from run_census import CaptureRefusedError, digest_of, reject_live_log
from trade_census import ReturnStats, Trade, build_trades, parse_capture, return_stats

from trading_bot.backtesting.evidence import (
    EVIDENCE_KEY,
    RUN_RECORD_NAME,
    EvidenceRefusedError,
    is_evidence_eligible,
    load_eligible_record,
    require_evidence_eligible,
)

__all__ = [
    "BacktestEntry",
    "Boot",
    "Figures",
    "InputError",
    "LiveEntry",
    "Matching",
    "figures_of",
    "live_boots",
    "live_entries",
    "load_backtest",
    "main",
    "match_entries",
    "read_backtest_trades",
    "render",
    "require_live_run_eligible",
]

TRADES_NAME = "trades.csv"
_REFUSED_EXIT = 2
_INPUT_EXIT = 3
_HUNDRED = Decimal(100)
_ONE_MS = timedelta(milliseconds=1)

_PID = re.compile(r"\|\s*pid=(\d+)\s*\|")
_STAMP = re.compile(r"^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})Z")
_BOOT = re.compile(r"event=boot_provenance verdict=(\S+) refusal_reasons=(\S+)")


class InputError(Exception):
    """An input is missing, malformed or contradicts itself; nothing is compared."""


@dataclass(frozen=True)
class Boot:
    """One ``boot_provenance`` line of the live capture."""

    line_no: int
    pid: str | None
    verdict: str
    refusal_reasons: str


@dataclass(frozen=True)
class LiveEntry:
    """A live entry that was booked, keyed by its symbol and the open of its entry bar."""

    symbol: str
    entry_bar_open: datetime
    signal_bar_close: datetime
    quantity: Decimal
    entry_quote_total: Decimal | None
    return_pct: Decimal | None
    realised: Decimal
    exit_price: Decimal
    exit_kind: str


@dataclass(frozen=True)
class BacktestEntry:
    """One ``trades.csv`` row, reduced to what the comparison reads."""

    symbol: str
    signal_bar_open: datetime
    entry_bar_open: datetime
    entry_price: Decimal
    entry_quote_total: Decimal
    realised: Decimal
    return_pct: Decimal
    exit_reason: str
    exit_price: Decimal


@dataclass(frozen=True)
class Matching:
    """The entries both sides share on (symbol, entry bar open), and each side's remainder."""

    matched: tuple[tuple[LiveEntry, BacktestEntry], ...]
    live_only: tuple[LiveEntry, ...]
    backtest_only: tuple[BacktestEntry, ...]


@dataclass(frozen=True)
class Figures:
    """R-C's three figures, with the inputs they are computed from."""

    live_count: int
    backtest_count: int
    matched: int
    reproduction_pct: Decimal | None
    live_returns: ReturnStats
    backtest_returns: ReturnStats
    backtest_mean_position: str
    count_difference: int
    count_difference_pct: Decimal | None


# --------------------------------------------------------------------------------------
# The live side
# --------------------------------------------------------------------------------------
def live_boots(lines: Sequence[str]) -> tuple[Boot, ...]:
    """Every ``boot_provenance`` line in the capture, in file order."""
    boots: list[Boot] = []
    for line_no, line in enumerate(lines, start=1):
        found = _BOOT.search(line)
        if found is None:
            continue
        pid = _PID.search(line)
        boots.append(
            Boot(
                line_no=line_no,
                pid=None if pid is None else pid.group(1),
                verdict=found.group(1),
                refusal_reasons=found.group(2),
            )
        )
    return tuple(boots)


def require_live_run_eligible(boots: Sequence[Boot]) -> None:
    """Refuse the live run unless every boot in the capture was an accepted one.

    The live run has no ``run.json``, so each boot's record is built from its line with the SAME
    judgement that sets a backtest's flag (``is_evidence_eligible``) and handed to the SAME door
    (``require_evidence_eligible``). A restart is a boot, so one refused boot refuses the run.

    :raises EvidenceRefusedError: the capture holds no boot line, or one boot is not accepted.
    """
    if not boots:
        raise EvidenceRefusedError(
            "the live capture holds no boot_provenance line, so nothing shows which code ran; a run "
            "is evidence only from a deployment clone whose boot_provenance verdict is accepted"
        )
    for boot in boots:
        provenance: dict[str, object] = {
            "verdict": boot.verdict,
            "refusal_reasons": boot.refusal_reasons,
        }
        record: dict[str, object] = {
            "schema": "live-boot",
            "provenance": provenance,
            EVIDENCE_KEY: is_evidence_eligible(provenance),
        }
        require_evidence_eligible(
            record, source=f"the live boot at capture line {boot.line_no} (pid {boot.pid})"
        )


def live_entries(
    trades: Sequence[Trade], *, start: datetime, end: datetime
) -> tuple[tuple[LiveEntry, ...], int]:
    """The booked entries whose entry bar opens in ``[start, end)``, and the unplaced bookings.

    A booking with no matched placement cannot be keyed (its entry bar is unknown) and is counted
    and reported, never dropped quietly.
    """
    entries: list[LiveEntry] = []
    unplaced = 0
    for trade in trades:
        placement = trade.placement
        if placement is None:
            unplaced += 1
            continue
        entry_open = placement.entry_bar_time + _ONE_MS
        if not start <= entry_open < end:
            continue
        kind = trade.route.value if trade.leg is None else trade.leg.value
        entries.append(
            LiveEntry(
                symbol=placement.symbol,
                entry_bar_open=entry_open,
                signal_bar_close=placement.entry_bar_time,
                quantity=trade.booking.quantity,
                entry_quote_total=trade.entry_quote_total,
                return_pct=trade.return_pct,
                realised=trade.booking.realised,
                exit_price=trade.exit_price,
                exit_kind=kind,
            )
        )
    return tuple(entries), unplaced


# --------------------------------------------------------------------------------------
# The backtest side
# --------------------------------------------------------------------------------------
def _decimal(row: Mapping[str, str], key: str, where: str) -> Decimal:
    try:
        value = Decimal(row[key])
    except (KeyError, InvalidOperation) as exc:
        raise InputError(f"{where}: column {key!r} is missing or not a decimal") from exc
    if not value.is_finite():
        raise InputError(f"{where}: column {key!r} is not finite")
    return value


def _instant(row: Mapping[str, str], key: str, where: str) -> datetime:
    try:
        value = datetime.fromisoformat(row[key])
    except (KeyError, ValueError) as exc:
        raise InputError(f"{where}: column {key!r} is missing or not a timestamp") from exc
    if value.tzinfo is None:
        raise InputError(f"{where}: column {key!r} carries no zone")
    return value.astimezone(timezone.utc)


def read_backtest_trades(path: Path) -> tuple[BacktestEntry, ...]:
    """Read ``trades.csv`` as ``write_run`` wrote it.

    :raises InputError: the file is unreadable, or a row lacks a column or holds a bad value.
    """
    try:
        with path.open(encoding="utf-8", newline="") as handle:
            rows = list(csv.DictReader(handle))
    except OSError as exc:
        raise InputError(f"{path} cannot be read: {exc}") from exc
    entries: list[BacktestEntry] = []
    for number, row in enumerate(rows, start=2):
        where = f"{path} line {number}"
        quote_total = _decimal(row, "entry_quote_total", where)
        if quote_total <= 0:
            raise InputError(f"{where}: entry_quote_total is not positive")
        realised = _decimal(row, "realised", where)
        entries.append(
            BacktestEntry(
                symbol=row.get("symbol", ""),
                signal_bar_open=_instant(row, "signal_bar_open", where),
                entry_bar_open=_instant(row, "entry_bar_open", where),
                entry_price=_decimal(row, "entry_price", where),
                entry_quote_total=quote_total,
                realised=realised,
                return_pct=realised / quote_total * _HUNDRED,
                exit_reason=row.get("exit_reason", ""),
                exit_price=_decimal(row, "exit_price", where),
            )
        )
    return tuple(entries)


def load_backtest(run_dir: Path) -> tuple[dict[str, object], tuple[BacktestEntry, ...]]:
    """The run record, through the evidence door, and its trades.

    :raises EvidenceRefusedError: the record is not evidence (R-AR).
    :raises InputError: ``trades.csv`` is unreadable or disagrees with the record's trade count.
    """
    record = load_eligible_record(run_dir / RUN_RECORD_NAME)
    trades = read_backtest_trades(run_dir / TRADES_NAME)
    results = record.get("results")
    declared = results.get("trades") if isinstance(results, dict) else None
    if declared != len(trades):
        raise InputError(
            f"{run_dir}: the record declares {declared!r} trade(s) and trades.csv holds {len(trades)}"
        )
    return record, trades


def within(
    entries: Sequence[BacktestEntry], *, start: datetime, end: datetime
) -> tuple[BacktestEntry, ...]:
    """The backtest entries whose entry bar opens in ``[start, end)``."""
    return tuple(entry for entry in entries if start <= entry.entry_bar_open < end)


# --------------------------------------------------------------------------------------
# The comparison
# --------------------------------------------------------------------------------------
def _by_key(entries: Sequence[tuple[str, datetime]], side: str) -> dict[tuple[str, datetime], int]:
    keys: dict[tuple[str, datetime], int] = {}
    for index, key in enumerate(entries):
        if key in keys:
            raise InputError(
                f"the {side} side holds two entries on {key[0]} at entry bar {key[1].isoformat()}; "
                "a symbol cannot be re-entered while held, so the input is not what it claims"
            )
        keys[key] = index
    return keys


def match_entries(live: Sequence[LiveEntry], backtest: Sequence[BacktestEntry]) -> Matching:
    """Pair entries on (symbol, entry bar open), each used once, keeping each side's file order."""
    live_keys = _by_key([(e.symbol, e.entry_bar_open) for e in live], "live")
    backtest_keys = _by_key([(e.symbol, e.entry_bar_open) for e in backtest], "backtest")
    matched = tuple(
        (live[live_keys[key]], backtest[backtest_keys[key]])
        for key in live_keys
        if key in backtest_keys
    )
    live_only = tuple(
        entry for entry in live if (entry.symbol, entry.entry_bar_open) not in backtest_keys
    )
    backtest_only = tuple(
        entry for entry in backtest if (entry.symbol, entry.entry_bar_open) not in live_keys
    )
    return Matching(matched=matched, live_only=live_only, backtest_only=backtest_only)


def figures_of(
    live: Sequence[LiveEntry], backtest: Sequence[BacktestEntry], matching: Matching
) -> Figures:
    """R-C's three figures. The comparison of the means to the interval is a position, not a verdict."""
    live_stats = return_stats([e.return_pct for e in live if e.return_pct is not None])
    backtest_stats = return_stats([e.return_pct for e in backtest])
    position = "no interval"
    if (
        backtest_stats.mean is not None
        and live_stats.low is not None
        and live_stats.high is not None
    ):
        if backtest_stats.mean < live_stats.low:
            position = "below"
        elif backtest_stats.mean > live_stats.high:
            position = "above"
        else:
            position = "inside"
    live_count, backtest_count = len(live), len(backtest)
    difference = abs(backtest_count - live_count)
    return Figures(
        live_count=live_count,
        backtest_count=backtest_count,
        matched=len(matching.matched),
        reproduction_pct=(
            Decimal(len(matching.matched)) / Decimal(live_count) * _HUNDRED if live_count else None
        ),
        live_returns=live_stats,
        backtest_returns=backtest_stats,
        backtest_mean_position=position,
        count_difference=difference,
        count_difference_pct=(
            Decimal(difference) / Decimal(live_count) * _HUNDRED if live_count else None
        ),
    )


# --------------------------------------------------------------------------------------
# The report
# --------------------------------------------------------------------------------------
def _pct(value: Decimal | None, places: int = 4) -> str:
    if value is None:
        return "n/a"
    return f"{value.quantize(Decimal(1).scaleb(-places))}%"


def render(
    figures: Figures,
    matching: Matching,
    *,
    boots: Sequence[Boot],
    unplaced: int,
    sources: Mapping[str, str],
    window: tuple[datetime, datetime],
) -> list[str]:
    """The report, one line per element. Figures and the entries they rest on; no verdict."""
    start, end = window
    out = ["=" * 74, "S4 COMPARISON -- figures only", "=" * 74]
    out.append(f"  window (entry bar open) : [{start.isoformat()}, {end.isoformat()})")
    for name, digest in sources.items():
        out.append(f"  {name:<24}: {digest}")
    out.append("")
    out.append("ELIGIBILITY (R-AR)")
    out.append("  backtest run record     : evidence_eligible true")
    for boot in boots:
        out.append(
            f"  live boot line {boot.line_no:>7}   : pid {boot.pid} verdict {boot.verdict} "
            f"(refusal reasons {boot.refusal_reasons})"
        )
    out.append("")
    out.append("R-C FIGURES")
    out.append(f"  live entries booked          : {figures.live_count}")
    out.append(f"  backtest entries             : {figures.backtest_count}")
    out.append(
        f"  reproduced on symbol and bar : {figures.matched} of {figures.live_count} "
        f"= {_pct(figures.reproduction_pct, 2)}"
    )
    live = figures.live_returns
    out.append(
        f"  live per-trade mean (n={live.n})  : {_pct(live.mean)}  95% interval "
        f"[{_pct(live.low)}, {_pct(live.high)}]"
    )
    out.append(
        f"  backtest per-trade mean (n={figures.backtest_returns.n}) : "
        f"{_pct(figures.backtest_returns.mean)}  position against that interval: "
        f"{figures.backtest_mean_position}"
    )
    out.append(
        f"  trade counts                 : {figures.backtest_count} against {figures.live_count}, "
        f"difference {figures.count_difference} = {_pct(figures.count_difference_pct, 2)} of live"
    )
    out.append(f"  live bookings with no placement (not keyable): {unplaced}")
    out.append("")
    out.append(f"LIVE ONLY ({len(matching.live_only)})")
    for live_entry in matching.live_only:
        out.append(
            f"  {live_entry.symbol} entry bar {live_entry.entry_bar_open.isoformat()} "
            f"qty {live_entry.quantity} exit {live_entry.exit_kind} at {live_entry.exit_price} "
            f"realised {live_entry.realised}"
        )
    out.append("")
    out.append(f"BACKTEST ONLY ({len(matching.backtest_only)})")
    for bt_entry in matching.backtest_only:
        out.append(
            f"  {bt_entry.symbol} entry bar {bt_entry.entry_bar_open.isoformat()} "
            f"price {bt_entry.entry_price} exit {bt_entry.exit_reason} at {bt_entry.exit_price} "
            f"realised {bt_entry.realised}"
        )
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
        prog="s4_compare.py",
        description="Compare S4's backtest with its live run and print figures, never a verdict.",
    )
    parser.add_argument("--run", type=Path, required=True, help="the backtest run directory")
    parser.add_argument("--capture", type=Path, required=True, help="a frozen live log capture")
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
    live, unplaced = live_entries(build_trades(parsed, args.quote_asset), start=start, end=end)
    backtest = within(all_backtest, start=start, end=end)
    try:
        matching = match_entries(live, backtest)
    except InputError as exc:
        print(f"INPUT ERROR: {exc}")
        return _INPUT_EXIT
    figures = figures_of(live, backtest, matching)
    sources = {
        "capture sha256": digest_of(args.capture),
        "run.json sha256": digest_of(args.run / RUN_RECORD_NAME),
        "trades.csv sha256": digest_of(args.run / TRADES_NAME),
        "record schema": str(record.get("schema")),
    }
    for line in render(
        figures, matching, boots=boots, unplaced=unplaced, sources=sources, window=(start, end)
    ):
        print(line)
    return 0


if __name__ == "__main__":  # pragma: no cover - CLI entry point
    raise SystemExit(main())
