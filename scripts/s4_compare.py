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
from itertools import pairwise
from pathlib import Path

from run_census import CaptureRefusedError, digest_of, reject_live_log
from trade_census import Placement, ReturnStats, Trade, build_trades, parse_capture, return_stats

from trading_bot.backtesting.evidence import (
    EVIDENCE_KEY,
    RUN_RECORD_NAME,
    EvidenceRefusedError,
    is_evidence_eligible,
    load_eligible_record,
    require_evidence_eligible,
)
from trading_bot.data.historical import HistoricalDataError, HistoricalStore

__all__ = [
    "CAUSES",
    "BacktestEntry",
    "Boot",
    "Disagreement",
    "DownInterval",
    "Figures",
    "InputError",
    "LiveEntry",
    "Matching",
    "SeriesChecks",
    "Signal",
    "backtest_view_of",
    "carried_in",
    "diagnose",
    "down_intervals",
    "exclude_downtime",
    "figures_of",
    "in_downtime",
    "live_boots",
    "live_entries",
    "load_backtest",
    "main",
    "match_entries",
    "read_backtest_trades",
    "read_signals",
    "render",
    "render_diagnosis",
    "require_live_run_eligible",
    "timeframe_delta",
    "unfilled_placements",
]

TRADES_NAME = "trades.csv"
BACKTEST_LOG_NAME = "backtest.log"
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


def strategy_facts(record: Mapping[str, object]) -> tuple[dict[str, str], int, int]:
    """Each pair's timeframe and the strategy's two periods, as the run record states them.

    :raises InputError: the record lacks a pair list or the two periods (it is not a record this
        tool can read), so no diagnosis is guessed from defaults.
    """
    pairs = record.get("pairs")
    timeframes: dict[str, str] = {}
    if isinstance(pairs, list):
        for pair in pairs:
            if isinstance(pair, dict) and isinstance(pair.get("symbol"), str):
                timeframes[str(pair["symbol"])] = str(pair.get("timeframe"))
    strategy = record.get("strategy")
    params = strategy.get("params") if isinstance(strategy, dict) else None
    fast = params.get("fast_period") if isinstance(params, dict) else None
    slow = params.get("slow_period") if isinstance(params, dict) else None
    if not timeframes or not isinstance(fast, int) or not isinstance(slow, int):
        raise InputError(
            "the run record names no pairs or no fast_period and slow_period, so the ties and the "
            "downtime bars cannot be computed"
        )
    return timeframes, fast, slow


def _data_dir(record: Mapping[str, object]) -> str:
    window = record.get("window")
    value = window.get("data_dir") if isinstance(window, dict) else None
    if not isinstance(value, str):
        raise InputError("the run record names no window.data_dir; pass --store")
    return value


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
# Diagnosis: bot downtime, signals, ties and gaps (R-BA, R-AO D)
# --------------------------------------------------------------------------------------
#: The closed list of causes (docs/S4_PREREGISTRATION.md, D). Every disagreement gets exactly one.
CAUSES = (
    "recorded-gap",
    "bar differs",
    "exact-decimal tie",
    "window-edge",
    "risk refusal differs",
    "fok-unfilled",
    "fill-model",
    "unexplained",
)
#: A signal whose bar closes inside a bot-down interval, or this many bars after it, is excluded.
EXCLUDED_BARS_AFTER_DOWNTIME = 2

_LOG_LINE = re.compile(
    r"^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})Z \| [A-Z]+\s*\| pid=(\d+) \|"
)
_FIELD = re.compile(r"(?<![\w.])([a-z][a-z0-9_]*)=(\S+)")
_SIGNAL_EVENT = re.compile(r"event=(intent_dispatched|risk_refused)\b")
_PASS_EVENT = "event=reconciliation_pass"
_TIMEFRAME = re.compile(r"(\d+)([mhd])")
_UNIT_MS = {"m": 60_000, "h": 3_600_000, "d": 86_400_000}


@dataclass(frozen=True)
class DownInterval:
    """From the last line one process wrote to the first reconciliation pass of the next."""

    start: datetime
    end: datetime
    before_pid: str
    after_pid: str


@dataclass(frozen=True)
class Signal:
    """What one side did with one ``BUY`` signal bar: dispatched an intent, or refused it."""

    symbol: str
    signal_close: datetime
    outcome: str
    stage: str | None
    reference: Decimal | None


@dataclass(frozen=True)
class Disagreement:
    """One entry, or one pair, on which the two sides differ, with its single cause."""

    kind: str
    symbol: str
    signal_close: datetime
    cause: str
    evidence: str


def timeframe_delta(timeframe: str) -> timedelta:
    """``1m`` -> one minute. Only the units the bot trades are accepted."""
    found = _TIMEFRAME.fullmatch(timeframe)
    if found is None:
        raise InputError(f"unreadable timeframe {timeframe!r}")
    return timedelta(milliseconds=int(found.group(1)) * _UNIT_MS[found.group(2)])


def _stamp_of(match: re.Match[str]) -> datetime:
    year, month, day, hour, minute, second = (int(part) for part in match.groups()[:6])
    return datetime(year, month, day, hour, minute, second, tzinfo=timezone.utc)


def down_intervals(lines: Sequence[str]) -> tuple[DownInterval, ...]:
    """Every span between one process's last line and the next process's first reconciliation pass.

    Processes are ordered by their first line. A process that never reaches a pass is taken to have
    resumed at its first line, so the interval is never longer than the evidence supports. A span
    with no length is not an interval.
    """
    order: list[str] = []
    first: dict[str, datetime] = {}
    last: dict[str, datetime] = {}
    first_pass: dict[str, datetime] = {}
    for line in lines:
        found = _LOG_LINE.match(line)
        if found is None:
            continue
        pid, stamp = found.group(7), _stamp_of(found)
        if pid not in first:
            first[pid] = stamp
            order.append(pid)
        last[pid] = max(last.get(pid, stamp), stamp)
        if _PASS_EVENT in line and pid not in first_pass:
            first_pass[pid] = stamp
    intervals: list[DownInterval] = []
    for before, after in pairwise(order):
        resumed = first_pass.get(after, first[after])
        if resumed > last[before]:
            intervals.append(DownInterval(last[before], resumed, before, after))
    return tuple(intervals)


def in_downtime(
    signal_close: datetime, intervals: Sequence[DownInterval], bar: timedelta
) -> DownInterval | None:
    """The interval a signal bar's close falls in, or within two bars after, or ``None``."""
    for interval in intervals:
        if interval.start <= signal_close < interval.end + EXCLUDED_BARS_AFTER_DOWNTIME * bar:
            return interval
    return None


def read_signals(lines: Sequence[str]) -> dict[tuple[str, datetime], Signal]:
    """Every ``BUY`` signal either side logged, keyed by (symbol, signal bar close); first wins."""
    signals: dict[tuple[str, datetime], Signal] = {}
    for line in lines:
        found = _SIGNAL_EVENT.search(line)
        if found is None:
            continue
        fields: dict[str, str] = {}
        for key, value in _FIELD.findall(line):
            fields.setdefault(key, value)
        if fields.get("action") != "BUY" or "symbol" not in fields or "signal_ts" not in fields:
            continue
        try:
            close = datetime.fromisoformat(fields["signal_ts"]).astimezone(timezone.utc)
            reference = Decimal(fields["reference"]) if "reference" in fields else None
        except (ValueError, InvalidOperation):
            continue
        dispatched = found.group(1) == "intent_dispatched"
        signals.setdefault(
            (fields["symbol"], close),
            Signal(
                symbol=fields["symbol"],
                signal_close=close,
                outcome="dispatched" if dispatched else "refused",
                stage=None if dispatched else fields.get("stage"),
                reference=reference,
            ),
        )
    return signals


class SeriesChecks:
    """The recorded closes behind a signal: a gap near it, a bar that differs, an exact tie.

    Every method answers ``None`` when the store cannot answer (no store, an unreadable or short
    series), and a cause that needs an answer then falls through to ``unexplained`` -- never to a
    guess. Money is ``Decimal`` from the stored strings; a simple moving average here is a sum over
    the window divided by its length, exact, so two averages are equal when they are equal.
    """

    def __init__(
        self, store: HistoricalStore | None, timeframes: Mapping[str, str], fast: int, slow: int
    ) -> None:
        self._store = store
        self._timeframes = dict(timeframes)
        self._fast = fast
        self._slow = slow

    def _bar(self, symbol: str) -> timedelta | None:
        timeframe = self._timeframes.get(symbol)
        return None if timeframe is None else timeframe_delta(timeframe)

    def _closes(
        self, symbol: str, signal_close: datetime, count: int
    ) -> list[tuple[datetime, Decimal]] | None:
        bar = self._bar(symbol)
        if self._store is None or bar is None:
            return None
        signal_open = signal_close + _ONE_MS - bar
        try:
            candles = list(
                self._store.candles(
                    symbol, self._timeframes[symbol], signal_open - bar * count, signal_open + bar
                )
            )
        except HistoricalDataError:
            return None
        return [(candle.open_time, candle.close) for candle in candles]

    def recorded_close(self, symbol: str, signal_close: datetime) -> Decimal | None:
        """The recorded close of the signal bar itself, or ``None`` if the store has no such bar."""
        closes = self._closes(symbol, signal_close, 0)
        bar = self._bar(symbol)
        if closes is None or bar is None:
            return None
        signal_open = signal_close + _ONE_MS - bar
        for opened, close in closes:
            if opened == signal_open:
                return close
        return None

    def gap_near(self, symbol: str, signal_close: datetime) -> bool | None:
        """Whether the series has a missing bar in the ``slow`` bars up to the signal bar."""
        bar = self._bar(symbol)
        closes = self._closes(symbol, signal_close, self._slow)
        if closes is None or bar is None:
            return None
        signal_open = signal_close + _ONE_MS - bar
        have = {opened for opened, _ in closes}
        return any(signal_open - bar * back not in have for back in range(self._slow))

    def tie_near(self, symbol: str, signal_close: datetime) -> bool | None:
        """Whether the exact fast and slow averages are equal at the signal bar or the bar before it."""
        bar = self._bar(symbol)
        closes = self._closes(symbol, signal_close, self._slow + 1)
        if closes is None or bar is None or len(closes) < self._slow + 1:
            return None
        values = [close for _, close in closes]
        for end in (len(values), len(values) - 1):
            fast_mean = sum(values[end - self._fast : end], Decimal(0)) / self._fast
            slow_mean = sum(values[end - self._slow : end], Decimal(0)) / self._slow
            if fast_mean == slow_mean:
                return True
        return False


def carried_in(trades: Sequence[Trade], start: datetime) -> tuple[tuple[str, datetime | None], ...]:
    """Live positions opened before the window and still open at its start: (symbol, exit time).

    The backtest starts flat at the window's start, so a signal the live bot refused with
    ``already_in_position`` on such a symbol is the window's edge and not a disagreement of the models.
    """
    carried: list[tuple[str, datetime | None]] = []
    for trade in trades:
        placement = trade.placement
        if placement is None or placement.entry_bar_time + _ONE_MS >= start:
            continue
        if trade.exit_time is None or trade.exit_time > start:
            carried.append((placement.symbol, trade.exit_time))
    return tuple(carried)


def _input_cause(
    symbol: str, signal_close: datetime, checks: SeriesChecks, *, live_reference: Decimal | None
) -> tuple[str, str]:
    """Why two sides saw different signals on one bar, from the recorded series alone.

    Precedence, stated because a bar can be several things: a missing bar first (the series is
    not the one the live bot saw), then a recorded close that differs from the close the live bot
    logged, then an exact tie of the two averages, else nothing explains it.
    """
    if checks.gap_near(symbol, signal_close):
        return "recorded-gap", "a bar is missing from the recorded series near the signal bar"
    if live_reference is not None:
        recorded = checks.recorded_close(symbol, signal_close)
        if recorded is not None and recorded != live_reference:
            return (
                "bar differs",
                f"recorded close {recorded}, the live signal's reference {live_reference}",
            )
    if checks.tie_near(symbol, signal_close):
        return (
            "exact-decimal tie",
            "the exact fast and slow averages are equal at the bar or the one before",
        )
    unchecked = checks.gap_near(symbol, signal_close) is None
    return (
        "unexplained",
        "the recorded series could not be read" if unchecked else "no recorded input explains it",
    )


def diagnose(
    matching: Matching,
    *,
    live_signals: Mapping[tuple[str, datetime], Signal],
    backtest_signals: Mapping[tuple[str, datetime], Signal],
    checks: SeriesChecks,
    carried: Sequence[tuple[str, datetime | None]],
    timeframes: Mapping[str, str],
) -> tuple[Disagreement, ...]:
    """One cause from the closed list for every entry only one side has, and every pair whose exits differ."""
    found: list[Disagreement] = []
    for live in matching.live_only:
        key = (live.symbol, live.signal_bar_close)
        other = backtest_signals.get(key)
        mine = live_signals.get(key)
        if other is None:
            cause, evidence = _input_cause(
                live.symbol,
                live.signal_bar_close,
                checks,
                live_reference=None if mine is None else mine.reference,
            )
        elif other.outcome == "refused":
            cause, evidence = (
                "risk refusal differs",
                f"the backtest refused at {other.stage}; the live bot dispatched",
            )
        else:
            cause, evidence = "fill-model", "the backtest dispatched and did not fill"
        found.append(Disagreement("live only", live.symbol, live.signal_bar_close, cause, evidence))
    for bt in matching.backtest_only:
        close = bt.entry_bar_open - _ONE_MS
        key = (bt.symbol, close)
        other = live_signals.get(key)
        edge = any(
            symbol == bt.symbol and (exit_time is None or exit_time > close)
            for symbol, exit_time in carried
        )
        if other is None:
            cause, evidence = _input_cause(bt.symbol, close, checks, live_reference=None)
        elif other.outcome == "refused" and other.stage == "already_in_position" and edge:
            cause, evidence = (
                "window-edge",
                "the live bot still held a position opened before the window",
            )
        elif other.outcome == "refused":
            cause, evidence = (
                "risk refusal differs",
                f"the live bot refused at {other.stage}; the backtest filled",
            )
        else:
            cause, evidence = (
                "fok-unfilled",
                "the live bot placed and nothing was booked (the venue read is the daily capture's)",
            )
        found.append(Disagreement("backtest only", bt.symbol, close, cause, evidence))
    for live, bt in matching.matched:
        if _exit_class(live.exit_kind) != _exit_class(bt.exit_reason):
            found.append(
                Disagreement(
                    "different exit",
                    live.symbol,
                    live.signal_bar_close,
                    "fill-model",
                    f"live {live.exit_kind} at {live.exit_price}, backtest {bt.exit_reason} at {bt.exit_price}",
                )
            )
    return tuple(found)


def _exit_class(kind: str) -> str:
    """Live ``SL``/``TP``/``CLOSE`` and the backtest's ``stop_loss``/``take_profit``/``close`` as one vocabulary."""
    lowered = kind.strip().lower()
    return {"sl": "stop", "stop_loss": "stop", "tp": "target", "take_profit": "target"}.get(
        lowered, lowered
    )


def exclude_downtime(
    live: Sequence[LiveEntry],
    backtest: Sequence[BacktestEntry],
    intervals: Sequence[DownInterval],
    timeframes: Mapping[str, str],
) -> tuple[
    tuple[LiveEntry, ...],
    tuple[BacktestEntry, ...],
    tuple[tuple[str, str, datetime, DownInterval], ...],
]:
    """Drop, on BOTH sides, every entry whose signal bar closed in a bot-down interval or just after it.

    The bot could not have acted on a signal it was down for, and the backtester would have, so the
    entry is a fact about the outage and not about the models. Returns the kept entries and one row
    per exclusion: (side, symbol, signal bar close, the interval).
    """
    excluded: list[tuple[str, str, datetime, DownInterval]] = []
    kept_live: list[LiveEntry] = []
    for entry in live:
        bar = timeframe_delta(_timeframe_of(timeframes, entry.symbol))
        interval = in_downtime(entry.signal_bar_close, intervals, bar)
        if interval is None:
            kept_live.append(entry)
        else:
            excluded.append(("live", entry.symbol, entry.signal_bar_close, interval))
    kept_backtest: list[BacktestEntry] = []
    for bt in backtest:
        bar = timeframe_delta(_timeframe_of(timeframes, bt.symbol))
        close = bt.entry_bar_open - _ONE_MS
        interval = in_downtime(close, intervals, bar)
        if interval is None:
            kept_backtest.append(bt)
        else:
            excluded.append(("backtest", bt.symbol, close, interval))
    return tuple(kept_live), tuple(kept_backtest), tuple(excluded)


def _timeframe_of(timeframes: Mapping[str, str], symbol: str) -> str:
    try:
        return timeframes[symbol]
    except KeyError as exc:
        raise InputError(f"the run record names no timeframe for {symbol}") from exc


def unfilled_placements(
    placements: Sequence[Placement],
    trades: Sequence[Trade],
    *,
    start: datetime,
    end: datetime,
) -> tuple[Placement, ...]:
    """Live placements in the window that no booking in the capture claims (R-BA).

    The log cannot say WHY none was booked (a FOK that expired, or a position still open when the
    capture ends); the venue read the pre-registration takes daily is what separates them.
    """
    booked = {trade.placement.line_no for trade in trades if trade.placement is not None}
    return tuple(
        placement
        for placement in placements
        if placement.line_no not in booked and start <= placement.entry_bar_time + _ONE_MS < end
    )


def backtest_view_of(
    placement: Placement,
    backtest: Sequence[BacktestEntry],
    backtest_signals: Mapping[tuple[str, datetime], Signal],
) -> str:
    """What the backtester did with the bar on which the live bot placed an order nobody booked."""
    entry_open = placement.entry_bar_time + _ONE_MS
    if any(e.symbol == placement.symbol and e.entry_bar_open == entry_open for e in backtest):
        return "backtest FILLED"
    signal = backtest_signals.get((placement.symbol, placement.entry_bar_time))
    if signal is None:
        return "backtest emitted no signal"
    if signal.outcome == "refused":
        return f"backtest refused at {signal.stage}"
    return "backtest dispatched and did not fill"


def render_diagnosis(
    *,
    intervals: Sequence[DownInterval],
    excluded: Sequence[tuple[str, str, datetime, DownInterval]],
    unfilled: Sequence[tuple[Placement, str]],
    disagreements: Sequence[Disagreement],
) -> list[str]:
    """The downtime, the unfilled placements and the causes, each listed."""
    out = ["", "BOT DOWNTIME (R-AP)"]
    for interval in intervals:
        out.append(
            f"  pid {interval.before_pid} -> pid {interval.after_pid}: "
            f"{interval.start.isoformat()} to {interval.end.isoformat()}"
        )
    out.append(
        f"  excluded on both sides ({len(excluded)}): signal bar closed in or within "
        f"{EXCLUDED_BARS_AFTER_DOWNTIME} bars after an interval"
    )
    for side, symbol, close, _interval in excluded:
        out.append(f"    {side} {symbol} signal bar close {close.isoformat()}")
    out.append("")
    out.append(
        f"LIVE PLACEMENTS WITH NO BOOKING IN THE CAPTURE ({len(unfilled)}) -- R-BA, reported"
    )
    for placement, view in unfilled:
        out.append(
            f"  {placement.symbol} entry bar {(placement.entry_bar_time + _ONE_MS).isoformat()}: {view}"
        )
    out.append("")
    out.append(f"DISAGREEMENTS ({len(disagreements)}), one cause each from the closed list")
    for cause in CAUSES:
        count = sum(1 for d in disagreements if d.cause == cause)
        out.append(f"  {cause:<22}: {count}")
    for d in disagreements:
        out.append(
            f"  [{d.cause}] {d.kind} {d.symbol} signal bar {d.signal_close.isoformat()}: {d.evidence}"
        )
    return out


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
    parser.add_argument(
        "--store",
        type=Path,
        default=None,
        help="the recorded series the backtest ran over (default: the record's window.data_dir)",
    )
    parser.add_argument(
        "--backtest-log",
        type=Path,
        default=None,
        help="the backtest's own log (default: backtest.log in the run directory)",
    )
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
        intervals = down_intervals(lines)
        live_in, unplaced = live_entries(all_trades, start=start, end=end)
        backtest_in = within(all_backtest, start=start, end=end)
        live, backtest, excluded = exclude_downtime(live_in, backtest_in, intervals, timeframes)
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
                intervals,
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
    for line in render(
        figures, matching, boots=boots, unplaced=unplaced, sources=sources, window=(start, end)
    ):
        print(line)
    for line in render_diagnosis(
        intervals=intervals, excluded=excluded, unfilled=unfilled, disagreements=disagreements
    ):
        print(line)
    return 0


if __name__ == "__main__":  # pragma: no cover - CLI entry point
    raise SystemExit(main())
