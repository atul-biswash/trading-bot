#!/usr/bin/env python
"""Print S5's figures from backtest run directories, in sample and out of sample SEPARATELY, and never a verdict.

R-BT, verbatim: *"S5's report gives in-sample and out-of-sample figures separately."* This script takes the run
directories of one candidate (S5's baseline, or an S6 candidate), one per stop-slippage arm, and prints what they
hold, with the trades split at the protocol's boundary (``2024-01-01``, R-BP) by the open of their ENTRY bar.
**It prints no PASS, no FAIL and no INCONCLUSIVE**, the principle of ``scripts/s4_compare.py`` and R-BE: the
decision is S7's, made against thresholds written down before any run, and a reader holds these figures against
them. The S7 section lists the four quantities beside their ruled thresholds and says nothing about which side
of each the figure falls.

**EVERY RECORD GOES THROUGH THE EVIDENCE DOOR FIRST (R-AR, R-BR).** ``load_eligible_record`` refuses a record
whose ``evidence_eligible`` is not exactly ``True``, whose schema is below 6, or whose effective settings and
digests do not match; this script then also refuses a record with no ``protocol`` block (no guard decided it),
a run that carries ``problems`` (it is not a result), a ``trades.csv`` whose row count is not the record's, runs
of different candidates, two runs of one arm, and an arm the protocol does not declare. Any refusal exits 2
before a figure is printed.

**WHAT IS AND IS NOT SPLIT.** Trades are split exactly, by entry time. Equity is split by UTC day on the record's
``daily_closes``: each segment starts from the equity at the end of the day before it (the initial balance for
the first), and its drawdown is **the maximum drawdown of the DAILY closes**, labelled as such. The record's
per-bar drawdown (R-AJ) covers the whole run and cannot be split afterwards, so it is printed once, labelled
"whole run", beside them; the daily-close figure is a lower bound on a per-bar figure over the same days.
Sharpe and Sortino are computed from the segment's daily returns by ``trading_bot.backtesting.metrics``.

**Regime breakdowns** read the committed labels (``docs/REGIME_LABELS.json``, verified against its digest file)
and require the digest to be the one the record names; a record that names none has no regime section.

Nothing is derived by dividing money except the ratios the metrics module already defines; every money figure is
printed as the exact ``Decimal`` string the record holds.
"""

from __future__ import annotations

import argparse
import hashlib
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Final

from trading_bot.backtesting.evidence import (
    RUN_RECORD_NAME,
    EvidenceRefusedError,
    load_eligible_record,
)
from trading_bot.backtesting.metrics import (
    UNLABELLED,
    EquitySummary,
    GroupMetrics,
    TradeFacts,
    group_metrics,
    load_trades_csv,
    sharpe_ratio,
    sortino_ratio,
)
from trading_bot.backtesting.protocol import PROTOCOL_PATH, Protocol, ProtocolError, load_protocol
from trading_bot.backtesting.regimes import RegimeTable
from trading_bot.core.exceptions import TradingBotError

__all__ = [
    "MIN_SCHEMA",
    "S7_THRESHOLDS",
    "ReportRefusedError",
    "Run",
    "Segment",
    "daily_close_drawdown",
    "load_run",
    "main",
    "render",
    "segments_of",
]

#: The first run-record schema that carries the research-protocol guard's decision (R-BT, C4).
MIN_SCHEMA: Final = 6

#: S7's ruled thresholds (M5m P99), printed beside the figures and never applied to them.
S7_THRESHOLDS: Final = {
    "profit_factor_net": Decimal("1.3"),
    "trades": 100,
    "max_drawdown": Decimal("0.20"),
    "regimes_positive": 2,
}

_REGIMES: Final = ("rising", "falling", "sideways")
_TRADES_NAME: Final = "trades.csv"
_REGIME_LABELS_PATH: Final = Path("docs") / "REGIME_LABELS.json"


class ReportRefusedError(TradingBotError):
    """The inputs are not a set of evidence-eligible runs of one candidate, so no figure is printed."""


@dataclass(frozen=True)
class Run:
    """One run directory, read through the evidence door."""

    directory: Path
    record: Mapping[str, object]
    trades: tuple[TradeFacts, ...]
    arm: Decimal
    record_sha256: str


@dataclass(frozen=True)
class Segment:
    """One side of the boundary: its trades, its daily closes and the equity it started from."""

    name: str
    trades: tuple[TradeFacts, ...]
    start_equity: Decimal
    closes: tuple[tuple[date, Decimal], ...]


# --------------------------------------------------------------------------
# Reading
# --------------------------------------------------------------------------
def _mapping(record: Mapping[str, object], key: str, where: str) -> Mapping[str, object]:
    value = record.get(key)
    if not isinstance(value, Mapping):
        raise ReportRefusedError(f"{where} has no {key!r} block")
    return value


def _text(block: Mapping[str, object], key: str, where: str) -> str:
    value = block.get(key)
    if not isinstance(value, str):
        raise ReportRefusedError(f"{where} has no text {key!r}")
    return value


def load_run(directory: Path) -> Run:
    """Read one run directory; refuse it unless it is an evidence-eligible, complete, guarded run.

    :raises ReportRefusedError: any of the refusals in the module docstring.
    """
    path = directory / RUN_RECORD_NAME
    try:
        record = load_eligible_record(path, min_schema=MIN_SCHEMA)
    except EvidenceRefusedError as exc:
        raise ReportRefusedError(str(exc)) from exc
    where = str(path)
    if not isinstance(record.get("protocol"), Mapping):
        raise ReportRefusedError(f"{where} carries no protocol block: no guard decided this run")
    problems = record.get("problems")
    if problems:
        raise ReportRefusedError(f"{where} is not a result: problems {problems!r}")
    trades_path = directory / _TRADES_NAME
    try:
        trades = load_trades_csv(trades_path)
    except (OSError, KeyError, ValueError, InvalidOperation) as exc:
        raise ReportRefusedError(f"{trades_path} cannot be read: {exc}") from exc
    expected = _mapping(record, "results", where).get("trades")
    if expected != len(trades):
        raise ReportRefusedError(
            f"{trades_path} holds {len(trades)} trade(s) and {where} says {expected!r}"
        )
    effective = _mapping(record, "effective", where)
    costs = _mapping(effective, "costs", where)
    arm_text = _text(costs, "stop_slippage_percent", where)
    try:
        arm = Decimal(arm_text)
    except InvalidOperation as exc:
        raise ReportRefusedError(
            f"{where} has a stop slippage {arm_text!r} that is not a number"
        ) from exc
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    return Run(directory, record, trades, arm, digest)


def check_runs(runs: Sequence[Run], protocol: Protocol) -> None:
    """Refuse a set that is not one candidate at distinct, declared arms.

    :raises ReportRefusedError: no run, two candidates, a repeated arm, or an undeclared arm.
    """
    if not runs:
        raise ReportRefusedError("no run directory was given")
    digests = {str(run.record.get("candidate_digest")) for run in runs}
    if len(digests) != 1:
        raise ReportRefusedError(
            f"the runs are of {len(digests)} different candidates: {sorted(digests)}"
        )
    arms = [run.arm for run in runs]
    if len(set(arms)) != len(arms):
        raise ReportRefusedError(
            f"two runs share one stop-slippage arm: {sorted(str(a) for a in arms)}"
        )
    declared = {Decimal(arm) for arm in protocol.arms}
    for run in runs:
        if run.arm not in declared:
            raise ReportRefusedError(
                f"{run.directory} ran at stop slippage {run.arm}%, which the protocol does not declare"
            )


# --------------------------------------------------------------------------
# Splitting
# --------------------------------------------------------------------------
def segments_of(run: Run, boundary: date) -> tuple[Segment, Segment]:
    """The run's in-sample and out-of-sample segments, split at ``boundary`` (a UTC date).

    A trade belongs to the side its ENTRY bar's open falls on. A daily close belongs to the side its UTC
    day falls on; each segment's starting equity is the close of the day before it began (the initial
    balance when there is none).
    """
    equity = EquitySummary.from_record(_mapping(run.record, "equity", str(run.directory)))
    cut = datetime(boundary.year, boundary.month, boundary.day, tzinfo=timezone.utc)
    before = tuple(t for t in run.trades if t.entry_time < cut)
    after = tuple(t for t in run.trades if t.entry_time >= cut)
    early = tuple((day, close) for day, close in equity.daily_closes if day < boundary)
    late = tuple((day, close) for day, close in equity.daily_closes if day >= boundary)
    carried = early[-1][1] if early else equity.initial
    return (
        Segment("in sample", before, equity.initial, early),
        Segment("out of sample", after, carried, late),
    )


def daily_close_drawdown(
    start_equity: Decimal, closes: Sequence[Decimal]
) -> tuple[Decimal, Decimal]:
    """The largest peak-to-trough decline of ``closes``, as ``(fraction of its peak, amount)``.

    The running peak starts at ``start_equity``. A candidate decline is compared by cross-multiplication
    and the quotient is taken once, as ``EquityCurve`` does, so no rounding decides which decline is
    largest. ``(0, 0)`` for a series that never falls below its peak.
    """
    peak = best_peak = best_trough = start_equity
    for close in closes:
        peak = max(peak, close)
        if (peak - close) * best_peak > (best_peak - best_trough) * peak:
            best_peak, best_trough = peak, close
    return (best_peak - best_trough) / best_peak, best_peak - best_trough


def daily_returns_of(start_equity: Decimal, closes: Sequence[Decimal]) -> tuple[Decimal, ...]:
    """Each day's close over the previous close (the first over ``start_equity``) minus one."""
    previous = start_equity
    out: list[Decimal] = []
    for close in closes:
        out.append(close / previous - 1)
        previous = close
    return tuple(out)


def _regime_groups(trades: Sequence[TradeFacts], regimes: RegimeTable) -> dict[str, GroupMetrics]:
    buckets: dict[str, list[TradeFacts]] = {name: [] for name in (*_REGIMES, UNLABELLED)}
    for trade in trades:
        regime = regimes.regime_on(trade.entry_time.date())
        buckets[UNLABELLED if regime is None else regime.value].append(trade)
    return {name: group_metrics(group) for name, group in buckets.items()}


def load_regimes(run: Run, path: Path) -> RegimeTable | None:
    """The committed labels if the record names a digest, checked against it; ``None`` if it names none.

    :raises ReportRefusedError: the file does not match its digest file, or is not the one the run used.
    """
    named = run.record.get("regime_labels")
    if named is None:
        return None
    if not isinstance(named, Mapping):
        raise ReportRefusedError(f"{run.directory} has a regime_labels that is not a block")
    try:
        table = RegimeTable.from_file(path)
    except (OSError, ValueError) as exc:
        raise ReportRefusedError(f"the regime labels {path} cannot be used: {exc}") from exc
    if table.digest != named.get("sha256"):
        raise ReportRefusedError(
            f"{path} has digest {table.digest}, and {run.directory} was labelled by {named.get('sha256')!r}"
        )
    return table


# --------------------------------------------------------------------------
# Rendering
# --------------------------------------------------------------------------
def _fmt(value: Decimal | None, places: int = 4) -> str:
    return "n/a" if value is None else f"{value:.{places}f}"


def _group_lines(indent: str, group: GroupMetrics) -> list[str]:
    returns = group.returns
    return [
        f"{indent}trades {group.trades}  wins {group.wins}  losses {group.losses}  win rate {_fmt(group.win_rate)}",
        f"{indent}net P&L {group.net_pnl}  gross P&L {group.gross_pnl}  fees {group.fees_paid}",
        f"{indent}profit factor net {_fmt(group.profit_factor_net)}  gross {_fmt(group.profit_factor_gross)}",
        f"{indent}per-trade return % mean {_fmt(returns.mean)}  95% interval "
        f"[{_fmt(returns.low)}, {_fmt(returns.high)}]  n {returns.n}",
    ]


def _segment_lines(segment: Segment, regimes: RegimeTable | None) -> list[str]:
    closes = [close for _, close in segment.closes]
    fraction, amount = daily_close_drawdown(segment.start_equity, closes)
    returns = daily_returns_of(segment.start_equity, closes)
    final = closes[-1] if closes else segment.start_equity
    overall = group_metrics(segment.trades)
    lines = [
        f"  {segment.name.upper()}",
        f"    days {len(closes)}  equity from {segment.start_equity} to {final}",
        *_group_lines("    ", overall),
        f"    max drawdown, DAILY CLOSES (not the per-bar figure): {_fmt(fraction)} of peak, {amount} quote",
        f"    sharpe {_fmt(sharpe_ratio(returns))}  sortino {_fmt(sortino_ratio(returns))}  (daily returns, 365-day year)",
    ]
    by_pair: dict[str, list[TradeFacts]] = {}
    for trade in segment.trades:
        by_pair.setdefault(trade.symbol, []).append(trade)
    for symbol in sorted(by_pair):
        lines.append(f"    pair {symbol}")
        lines.extend(_group_lines("      ", group_metrics(by_pair[symbol])))
    if regimes is not None:
        for name, group in _regime_groups(segment.trades, regimes).items():
            lines.append(f"    regime {name}")
            lines.extend(_group_lines("      ", group))
    return lines


def _s7_lines(segment: Segment, regimes: RegimeTable | None) -> list[str]:
    closes = [close for _, close in segment.closes]
    fraction, _amount = daily_close_drawdown(segment.start_equity, closes)
    overall = group_metrics(segment.trades)
    if regimes is None:
        positive = "n/a (no regime labels)"
    else:
        groups = _regime_groups(segment.trades, regimes)
        positive = f"{sum(1 for name in _REGIMES if groups[name].net_pnl > 0)} of {len(_REGIMES)}"
    return [
        "  S7 PREVIEW (out of sample; the four quantities beside the ruled thresholds, no verdict)",
        f"    profit factor (net)         figure {_fmt(overall.profit_factor_net)}    threshold >= {S7_THRESHOLDS['profit_factor_net']}",
        f"    trades                      figure {overall.trades}    threshold >= {S7_THRESHOLDS['trades']}",
        f"    max drawdown (daily-close)  figure {_fmt(fraction)}    threshold <= {S7_THRESHOLDS['max_drawdown']}",
        f"    regimes with net P&L > 0    figure {positive}    threshold >= {S7_THRESHOLDS['regimes_positive']}",
    ]


def render(
    runs: Sequence[Run], protocol: Protocol, regimes_path: Path = _REGIME_LABELS_PATH
) -> str:
    """The whole report as text. Pure of side effects but for reading the regime labels.

    :raises ReportRefusedError: see :func:`check_runs` and :func:`load_regimes`.
    """
    check_runs(runs, protocol)
    ordered = sorted(runs, key=lambda run: run.arm)
    first = ordered[0]
    regimes = load_regimes(first, regimes_path)
    for run in ordered[1:]:
        if (run.record.get("regime_labels") is None) != (regimes is None):
            raise ReportRefusedError("the runs disagree on whether they carry regime labels")
    window = _mapping(first.record, "window", str(first.directory))
    block = _mapping(first.record, "protocol", str(first.directory))
    code = first.record.get("code")
    lines = [
        f"S5 REPORT  boundary {protocol.boundary.isoformat()}  protocol {protocol.sha256}",
        f"candidate {first.record.get('candidate_digest')}  entry {block.get('entry_id')}  kind {block.get('kind')}",
        f"window {window.get('start_date')} to {window.get('end_date')} (end exclusive)  code {code}",
        "",
    ]
    for run in ordered:
        equity = _mapping(run.record, "equity", str(run.directory))
        metrics = _mapping(run.record, "metrics", str(run.directory))
        in_sample, out_of_sample = segments_of(run, protocol.boundary)
        lines.append(f"ARM stop slippage {run.arm}%  run {run.directory.name}")
        lines.append(f"  record sha256 {run.record_sha256}")
        lines.append(
            f"  trade log sha256 {_mapping(run.record, 'results', '')['trade_log_sha256']}"
        )
        lines.append(
            f"  WHOLE RUN, per-bar max drawdown (R-AJ): {metrics.get('max_drawdown')}  "
            f"final equity {equity.get('final')}"
        )
        lines.extend(_segment_lines(in_sample, regimes))
        lines.extend(_segment_lines(out_of_sample, regimes))
        lines.extend(_s7_lines(out_of_sample, regimes))
        lines.append("")
    return "\n".join(lines)


# --------------------------------------------------------------------------
# Entry point
# --------------------------------------------------------------------------
def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument(
        "runs", nargs="+", type=Path, help="run directories of ONE candidate, one per arm"
    )
    parser.add_argument("--protocol", type=Path, default=PROTOCOL_PATH)
    parser.add_argument("--regimes", type=Path, default=_REGIME_LABELS_PATH)
    args = parser.parse_args(argv)
    try:
        protocol = load_protocol(args.protocol)
        loaded = [load_run(directory) for directory in args.runs]
        text = render(loaded, protocol, args.regimes)
    except (ReportRefusedError, ProtocolError) as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        return 2
    sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
