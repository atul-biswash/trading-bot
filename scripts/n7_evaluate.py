#!/usr/bin/env python
"""The N7 runner: the six M5n candidates over the in-sample span, judged by pre-registration sections 5 to 8.

Usage:
    python scripts/n7_evaluate.py --out RESULT.json
    python scripts/n7_evaluate.py --config PATH --data-dir DIR --out RESULT.json

**What this is, and the guard that comes first.** ``docs/M5N_PREREGISTRATION.md`` (SHA-256
``e6187480b6af7da1349ab280a6bb74f7219d4a7cded4217574e6247d5f54d45e``) fixes the gate; this script applies it.
It computes Sharpe ratios, bootstrap bounds and deflated Sharpe ratios on recorded data, which R-DT clause 3
forbids until N0 records the S4 result. So the **first act of** :func:`main`, before the config or the store is
opened, is :func:`check_n0_guard`, and it refuses unless all three conditions of the charter (section 22) hold:

* (a) the tag ``milestone/M5m`` resolves to a commit;
* (b) the charter, read from the commit at HEAD, carries exactly one line
  ``N0 complete: S4 result recorded at <sha>`` whose commit is an ancestor of HEAD (HEAD counts);
* (c) the charter carries exactly one line ``N7 frozen digest <path> <sha256>`` for the pre-registration,
  the estimator module and this file, and each file's bytes in the working tree hash to it.

**There is no override**: no flag, no environment variable, no config key. The tests reach the guard through
the ``root`` parameter and the module constant ``REPO_ROOT``, and no command line does. Because this file's own
digest is one of the three, **any edit to it, to the estimator module or to the pre-registration after the digests
are recorded is an amendment, and the guard refuses the edited tree.**

**What the evaluation does** (a run with the guard satisfied). For each candidate of R-DY it finds the first
UTC day on which every candidate's indicators are defined for both pairs (:func:`candidate_starts`), then runs
the candidate through the D1 path of the backtester over ``[start, 2024-01-01)``: BTCUSDT and ETHUSDT
together, the book starting flat, an open position at the end marked and not closed. Equity is sampled at each
UTC 00:00 by this module's own candle subscriber, cash plus every open position marked at the decision
timeframe's last close, which for a 4h candidate is the 4h bar that closes at 00:00 and so the 1d archive close
of that day (``M5n-207``). Those marks go to :func:`~trading_bot.backtesting.sharpe_stats.daily_series`, and
:func:`judge` applies sections 5 to 8 to them. The section 3 sensitivities re-run every candidate at the other
costs and are REPORTED, never deciding; the section 10 context is the equal-weight buy and hold.

**What it writes and prints.** One result file (``--out``, refused if it exists), canonical JSON, whose SHA-256
is printed beside the report. The report puts the fee telemetry first, before any Sharpe (charter section 22).
Exit codes: 0 a verdict (a candidate selected, or FAIL at N7); 1 a run was incomplete or the verdict is
INDETERMINATE (a tie that section 7 does not break); 2 refused (the guard, an existing result file, or the
config or store could not be read).
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import logging
import re
import shutil
import subprocess
import sys
import traceback
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from typing import Final, TextIO

import trading_bot.strategies.m5n  # noqa: F401  (registers the six candidates)
from trading_bot.backtesting.engine import BacktestSystem, backtest_system
from trading_bot.backtesting.overrides import apply_overrides, build_overrides
from trading_bot.backtesting.sharpe_stats import (
    Mark,
    buy_and_hold_marks,
    daily_series,
    deflated_sharpe,
    fee_telemetry,
    sharpe,
    skewness_kurtosis,
    stationary_bootstrap_bounds,
)
from trading_bot.backtesting.simulated_executor import SimulatedTrade
from trading_bot.config.settings import Secrets, Settings, get_settings
from trading_bot.core.exceptions import TradingBotError
from trading_bot.core.models import Candle
from trading_bot.data.historical import HistoricalStore
from trading_bot.strategies import registry
from trading_bot.utils.helpers import timeframe_to_ms

DEFAULT_CONFIG: Final = "config.m5n.yaml"
DEFAULT_DATA_DIR: Final = "data/historical"
REPO_ROOT: Path = Path(__file__).resolve().parents[1]
CHARTER_PATH: Final = "docs/M5N_CHARTER_DRAFT.md"
MILESTONE_TAG: Final = "milestone/M5m"
#: The three files whose digests the charter must record, in the order the guard checks them.
FROZEN_PATHS: Final = (
    "docs/M5N_PREREGISTRATION.md",
    "src/trading_bot/backtesting/sharpe_stats.py",
    "scripts/n7_evaluate.py",
)

#: The in-sample span ends here (pre-registration section 2); the archive begins at the first date.
IN_SAMPLE_BEGIN: Final = datetime(2017, 8, 17, tzinfo=timezone.utc)
IN_SAMPLE_END: Final = datetime(2024, 1, 1, tzinfo=timezone.utc)
PAIRS: Final = ("BTCUSDT", "ETHUSDT")

#: The six candidates in R-DY's order, with the decision timeframe each takes.
CANDIDATES: tuple[tuple[str, str, str], ...] = (
    ("C1", "donchian_1d_20", "1d"),
    ("C2", "donchian_1d_55", "1d"),
    ("C3", "sma_cross_1d_50_200", "1d"),
    ("C4", "donchian_4h_20", "4h"),
    ("C5", "keltner_4h_20_2", "4h"),
    ("C6", "tsmom_1d_90", "1d"),
)

#: Pre-registration section 6: the deflated Sharpe ratio must exceed this (c), and the stationary bootstrap
#: (b) uses an expected block length of 20 days, so p = 1/20, 10,000 resamples and this seed.
DSR_MIN: Final = 0.95
BOOTSTRAP_P: Final = 1 / 20
RESAMPLES: Final = 10_000
SEED: Final = 20_261_025
_GATES: Final = ("floor", "bootstrap", "dsr")
_ROUND: Final = 10


@dataclass(frozen=True)
class Floors:
    """A timeframe's trade floors (section 5): closed trades across both pairs."""

    in_sample: int
    out_of_sample: int


FLOORS: dict[str, Floors] = {"1d": Floors(30, 12), "4h": Floors(120, 48)}


@dataclass(frozen=True)
class Costs:
    """One cost setting: the fee per side and the stop slippage, both in whole percents."""

    name: str
    fee_percent: Decimal
    stop_slippage_percent: Decimal


#: The costs a verdict uses (section 3), and the sensitivities that are reported and never decide.
BASE_COSTS: Final = Costs("base", Decimal("0.10"), Decimal("1.20"))
SENSITIVITIES: tuple[Costs, ...] = (
    Costs("fee_0.075", Decimal("0.075"), Decimal("1.20")),
    Costs("slip_0.66", Decimal("0.10"), Decimal("0.66")),
    Costs("slip_0.10", Decimal("0.10"), Decimal("0.10")),
)


class RunnerError(TradingBotError):
    """The evaluation cannot give a verdict: a run was incomplete, a book did not add up, or a series has no
    Sharpe. Raised, never repaired."""


# --------------------------------------------------------------------------
# The N0 guard
# --------------------------------------------------------------------------
class GuardError(Exception):
    """A condition of the N0 guard does not hold. ``code`` names which; the tests pin each."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


_N0_LINE = re.compile(r"N0 complete: S4 result recorded at ([0-9a-f]{7,40})")
_DIGEST_LINE = re.compile(r"N7 frozen digest (\S+) ([0-9a-f]{64})")


def _git(root: Path, *args: str) -> subprocess.CompletedProcess[bytes]:
    """Run ``git -C root ...`` and return the process; a missing or failing ``git`` refuses."""
    git = shutil.which("git")
    if git is None:
        raise GuardError("git_unavailable", "no git executable was found on the path")
    try:
        return subprocess.run(
            [git, "-C", str(root), *args],
            capture_output=True,
            timeout=60,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise GuardError("git_unavailable", f"git could not be run: {type(exc).__name__}") from exc


def _is_ancestor(root: Path, commit: str, descendant: str = "HEAD") -> bool:
    """Whether ``commit`` is ``descendant`` or an ancestor of it. Any git failure raises."""
    process = _git(root, "merge-base", "--is-ancestor", commit, descendant)
    if process.returncode == 0:
        return True
    if process.returncode == 1:
        return False
    raise GuardError("git_unavailable", f"git merge-base failed with status {process.returncode}")


def check_n0_guard(root: Path = REPO_ROOT) -> None:
    """Refuse (``GuardError``) unless the charter's three conditions hold. Returns ``None`` when they do.

    The charter is read from the commit at HEAD and not from the working file, so a line that was only typed
    cannot satisfy (b) or (c). A condition that cannot be evaluated refuses.
    """
    shown = _git(root, "show", f"HEAD:{CHARTER_PATH}")
    if shown.returncode != 0:
        raise GuardError(
            "charter_unreadable",
            f"{CHARTER_PATH} cannot be read at HEAD of {root} (git show failed)",
        )
    try:
        # Bytes, decoded strictly, so a carriage return stays on its line and makes it a different line.
        lines = shown.stdout.decode("utf-8").split("\n")
    except UnicodeDecodeError as exc:
        raise GuardError("charter_unreadable", f"{CHARTER_PATH} at HEAD is not UTF-8") from exc

    tag = _git(root, "rev-parse", "--verify", "--quiet", f"refs/tags/{MILESTONE_TAG}^{{commit}}")
    if tag.returncode != 0:
        raise GuardError("tag_missing", f"the tag {MILESTONE_TAG} does not resolve to a commit")

    found = [m.group(1) for line in lines if (m := _N0_LINE.fullmatch(line)) is not None]
    if not found:
        raise GuardError("n0_line_missing", "the charter at HEAD has no 'N0 complete' line")
    if len(found) > 1:
        raise GuardError("n0_line_duplicated", f"the charter has {len(found)} 'N0 complete' lines")
    resolved = _git(root, "rev-parse", "--verify", "--quiet", f"{found[0]}^{{commit}}")
    if resolved.returncode != 0:
        raise GuardError(
            "n0_commit_unknown", f"{found[0]} does not name one commit in this repository"
        )
    if not _is_ancestor(root, resolved.stdout.decode("ascii").strip()):
        raise GuardError("n0_commit_not_ancestor", f"{found[0]} is not an ancestor of HEAD")

    for path in FROZEN_PATHS:
        recorded = [
            m.group(2)
            for line in lines
            if (m := _DIGEST_LINE.fullmatch(line)) is not None and m.group(1) == path
        ]
        if not recorded:
            raise GuardError("digest_line_missing", f"the charter records no digest for {path}")
        if len(recorded) > 1:
            raise GuardError(
                "digest_line_duplicated", f"the charter records {path} {len(recorded)} times"
            )
        try:
            actual = hashlib.sha256((root / path).read_bytes()).hexdigest()
        except OSError as exc:
            raise GuardError(
                "digest_file_unreadable", f"{path} cannot be read: {type(exc).__name__}"
            ) from exc
        if actual != recorded[0]:
            raise GuardError(
                "digest_mismatch",
                f"{path} hashes to {actual}, not the {recorded[0]} the charter records",
            )


# --------------------------------------------------------------------------
# The judgement: pre-registration sections 5 to 8, over marks
# --------------------------------------------------------------------------
@dataclass(frozen=True)
class CandidateRun:
    """What one candidate's run yields, as plain data: the trade books of its CLOSED round trips and its
    daily equity marks. The judgement reads nothing else."""

    label: str
    name: str
    timeframe: str
    trades: int
    open_at_end: int
    gross: Decimal
    fees: Decimal
    entry_notional: Decimal
    marks: tuple[Mark, ...]
    carried_marks: int = 0


@dataclass(frozen=True)
class CandidateJudgement:
    """One candidate against sections 5 and 6, with each gate."""

    label: str
    name: str
    timeframe: str
    trades: int
    floor: int
    floor_met: bool
    days: int
    sharpe_annual: float
    sharpe_daily: float
    skew: float
    kurt: float
    boot_p5: float | None
    boot_error: str | None
    dsr: float
    boot_pass: bool
    dsr_pass: bool
    status: str

    def gates(self) -> dict[str, bool]:
        return {"floor": self.floor_met, "bootstrap": self.boot_pass, "dsr": self.dsr_pass}


@dataclass(frozen=True)
class Judgement:
    """The candidates, and section 7's outcome: ``SELECTED``, ``FAIL`` (no pass, section 8) or
    ``INDETERMINATE`` (a tie that section 7 does not break)."""

    candidates: tuple[CandidateJudgement, ...]
    outcome: str
    selected: str | None
    tied: tuple[str, ...]
    trials: int


def _status(floor_met: bool, boot_pass: bool, dsr_pass: bool) -> str:
    if not floor_met:
        return "EXCLUDED (below floor)"
    if boot_pass and dsr_pass:
        return "PASS"
    failed = [name for name, ok in (("bootstrap", boot_pass), ("dsr", dsr_pass)) if not ok]
    return "FAILED (" + ", ".join(failed) + ")"


def judge(
    runs: Sequence[CandidateRun],
    *,
    floors: Mapping[str, Floors] = FLOORS,
    resamples: int = RESAMPLES,
    seed: int = SEED,
    p: float = BOOTSTRAP_P,
) -> Judgement:
    """Apply sections 5 to 8 to ``runs``. Pure: no store, no clock, no backtester.

    The deflated Sharpe ratio's trial count is ``len(runs)``, which is 6 in the real run (the pre-registration's
    ``N``), and its trial variance is taken from these runs' own daily Sharpe ratios.

    :raises RunnerError: a candidate's daily returns have no variance, so there is no Sharpe (``M5n-203``).
    :raises ValueError: the bootstrap's settings are invalid, or ``runs`` is empty.
    """
    if not runs:
        raise ValueError("there is no candidate to judge")
    if resamples < 1 or not 0.0 < p <= 1.0:
        raise ValueError(f"invalid bootstrap settings: p={p!r}, resamples={resamples}")
    series: list[tuple[float, ...]] = []
    daily: list[float] = []
    for run in runs:
        returns = daily_series(run.marks)
        try:
            daily.append(sharpe(returns, annualise=False))
        except ValueError as exc:
            raise RunnerError(f"candidate {run.label} has no Sharpe ratio: {exc}") from exc
        series.append(returns)
    rows: list[CandidateJudgement] = []
    for run, returns, sr_daily in zip(runs, series, daily, strict=True):
        skew, kurt = skewness_kurtosis(returns)
        boot_p5: float | None
        boot_error: str | None
        try:
            boot_p5 = stationary_bootstrap_bounds(returns, p=p, resamples=resamples, seed=seed).p5
            boot_error = None
        except ValueError as exc:
            # The settings were checked above and the series has a spread, so this is a resample with no
            # variance (M5n-204): the gate fails and the refusal is recorded, not repaired.
            boot_p5, boot_error = None, str(exc)
        dsr = deflated_sharpe(sr_daily, daily, len(returns), skew, kurt, len(runs))
        floor = floors[run.timeframe].in_sample
        floor_met = run.trades >= floor
        boot_pass = boot_p5 is not None and boot_p5 > 0.0
        dsr_pass = dsr > DSR_MIN
        rows.append(
            CandidateJudgement(
                label=run.label,
                name=run.name,
                timeframe=run.timeframe,
                trades=run.trades,
                floor=floor,
                floor_met=floor_met,
                days=len(returns),
                sharpe_annual=sharpe(returns),
                sharpe_daily=sr_daily,
                skew=skew,
                kurt=kurt,
                boot_p5=boot_p5,
                boot_error=boot_error,
                dsr=dsr,
                boot_pass=boot_pass,
                dsr_pass=dsr_pass,
                status=_status(floor_met, boot_pass, dsr_pass),
            )
        )
    passing = [row for row in rows if row.status == "PASS"]
    if not passing:
        return Judgement(tuple(rows), "FAIL", None, (), len(runs))
    best = max((row.sharpe_annual, row.trades) for row in passing)
    tops = tuple(row.label for row in passing if (row.sharpe_annual, row.trades) == best)
    if len(tops) > 1:
        return Judgement(tuple(rows), "INDETERMINATE", None, tops, len(runs))
    return Judgement(tuple(rows), "SELECTED", tops[0], (), len(runs))


@dataclass(frozen=True)
class Flip:
    """A gate that a sensitivity would turn over."""

    label: str
    gate: str
    before: bool
    after: bool


def flips_between(base: Judgement, other: Judgement) -> tuple[Flip, ...]:
    """The gates that differ between two judgements of the same candidates, in candidate then gate order."""
    out: list[Flip] = []
    for before, after in zip(base.candidates, other.candidates, strict=True):
        if before.label != after.label:
            raise ValueError(
                f"the judgements do not list the same candidates: {before.label}, {after.label}"
            )
        gates_before, gates_after = before.gates(), after.gates()
        out.extend(
            Flip(before.label, gate, gates_before[gate], gates_after[gate])
            for gate in _GATES
            if gates_before[gate] != gates_after[gate]
        )
    return tuple(out)


@dataclass(frozen=True)
class Sensitivity:
    """A cost setting's judgement beside the base one. Reported; it never decides anything."""

    costs: Costs
    judgement: Judgement
    flips: tuple[Flip, ...]
    runs: tuple[CandidateRun, ...]

    @property
    def would_select(self) -> str:
        if self.judgement.outcome == "SELECTED":
            return str(self.judgement.selected)
        return "none" if self.judgement.outcome == "FAIL" else "indeterminate"


@dataclass(frozen=True)
class ContextSharpe:
    """Section 10: the equal-weight buy and hold's annualised Sharpe over the same span."""

    sharpe_annual: float
    days: int


@dataclass(frozen=True)
class Evaluation:
    """Everything the report and the result file are made of."""

    window: tuple[date, date]
    first_defined: Mapping[str, date]
    runs: tuple[CandidateRun, ...]
    judgement: Judgement
    sensitivities: tuple[Sensitivity, ...]
    context: ContextSharpe
    resamples: int = RESAMPLES
    seed: int = SEED
    p: float = BOOTSTRAP_P


# --------------------------------------------------------------------------
# Fee telemetry (charter section 22), the report and the result file
# --------------------------------------------------------------------------
@dataclass(frozen=True)
class TelemetryLine:
    """A candidate's fee figures with each ratio's inputs beside it. ``None`` is ``n/a``."""

    label: str
    trades: int
    gross: Decimal
    fees: Decimal
    net: Decimal
    entry_notional: Decimal
    fee_share: Decimal | None
    fee_bps: Decimal | None
    flag: str


def telemetry_of(run: CandidateRun) -> TelemetryLine:
    """Fees over ``|gross|`` and over entry notional in basis points, or ``n/a`` where the denominator is
    zero or there is no trade, with the flag the owner asked for. Closed round trips only (``M5n-205``)."""
    net = run.gross - run.fees
    if run.trades == 0:
        return TelemetryLine(
            run.label, 0, run.gross, run.fees, net, run.entry_notional, None, None, "no_trades"
        )
    if run.gross != 0:
        book = fee_telemetry(run.gross, run.fees, run.trades, entry_notional=run.entry_notional)
        share: Decimal | None = book.fee_share
        bps: Decimal | None = book.fee_bps
    else:
        # fee_telemetry refuses a zero gross by design; the basis points do not need it.
        share = None
        bps = run.fees / run.entry_notional * Decimal(10000)
    flag = "gross<=0" if run.gross <= 0 else ""
    return TelemetryLine(
        run.label, run.trades, run.gross, run.fees, net, run.entry_notional, share, bps, flag
    )


def _plain(value: Decimal) -> str:
    """A ``Decimal`` as digits with no exponent and no trailing zeros: ``500``, ``0.075``, ``-222.3775113``.
    The fill model's products carry twenty zeros of exponent that mean nothing and would make a report and
    a digest depend on them."""
    return format(value.normalize(), "f")


def _fixed(value: float | None, places: int = 6) -> str:
    return "n/a" if value is None else f"{value:.{places}f}"


def render(evaluation: Evaluation) -> list[str]:
    """The report, fee telemetry first (before any Sharpe), as lines."""
    lines = [
        "N7 in-sample evaluation (pre-registration sections 5 to 8)",
        f"window [{evaluation.window[0].isoformat()}, {evaluation.window[1].isoformat()})",
        "fee telemetry (telemetry only, never a criterion)",
    ]
    for run in evaluation.runs:
        t = telemetry_of(run)
        share = "n/a" if t.fee_share is None else f"{t.fee_share:.6f}"
        bps = "n/a" if t.fee_bps is None else f"{t.fee_bps:.4f}"
        flag = f" flag={t.flag}" if t.flag else ""
        lines.append(
            f"  {t.label} trades={t.trades} gross={_plain(t.gross)} fees={_plain(t.fees)} net={_plain(t.net)}"
            f" entry_notional={_plain(t.entry_notional)} fee_share={share} fee_bps={bps}{flag}"
        )
    judgement = evaluation.judgement
    lines.append(
        f"candidates (bootstrap p={evaluation.p:g} resamples={evaluation.resamples}"
        f" seed={evaluation.seed}; deflated Sharpe trials={judgement.trials})"
    )
    for c in judgement.candidates:
        lines.append(
            f"  {c.label} {c.timeframe} trades={c.trades} floor={c.floor} days={c.days}"
            f" sharpe_annual={c.sharpe_annual:.6f} boot_p5={_fixed(c.boot_p5)} dsr={c.dsr:.6f}"
            f" status={c.status}"
        )
    if judgement.outcome == "SELECTED":
        lines.append(f"verdict SELECTED {judgement.selected}")
    elif judgement.outcome == "FAIL":
        lines.append(
            "verdict FAIL at N7 (no candidate passes; the out-of-sample window stays unread)"
        )
    else:
        lines.append(
            f"verdict INDETERMINATE {' '.join(judgement.tied)} (a tie that section 7 does not break)"
        )
    for s in evaluation.sensitivities:
        lines.append(
            f"sensitivity {s.costs.name} would_select={s.would_select} flips={len(s.flips)}"
        )
        lines.extend(
            f"  flip {f.label} {f.gate} {'pass' if f.before else 'fail'}->{'pass' if f.after else 'fail'}"
            for f in s.flips
        )
    lines.append(
        f"context buy_and_hold sharpe_annual={evaluation.context.sharpe_annual:.6f}"
        f" days={evaluation.context.days}"
    )
    return lines


def _rounded(value: float | None) -> float | None:
    return None if value is None else round(value, _ROUND)


def _judgement_document(judgement: Judgement) -> dict[str, object]:
    return {
        "outcome": judgement.outcome,
        "selected": judgement.selected,
        "tied": list(judgement.tied),
        "trials": judgement.trials,
        "candidates": [
            {
                "label": c.label,
                "name": c.name,
                "timeframe": c.timeframe,
                "trades": c.trades,
                "floor": c.floor,
                "floor_met": c.floor_met,
                "days": c.days,
                "sharpe_annual": _rounded(c.sharpe_annual),
                "sharpe_daily": _rounded(c.sharpe_daily),
                "skew": _rounded(c.skew),
                "kurtosis": _rounded(c.kurt),
                "boot_p5": _rounded(c.boot_p5),
                "boot_error": c.boot_error,
                "dsr": _rounded(c.dsr),
                "boot_pass": c.boot_pass,
                "dsr_pass": c.dsr_pass,
                "status": c.status,
            }
            for c in judgement.candidates
        ],
    }


def _run_figures(run: CandidateRun) -> dict[str, object]:
    return {
        "label": run.label,
        "trades": run.trades,
        "open_at_end": run.open_at_end,
        "carried_marks": run.carried_marks,
        "gross": _plain(run.gross),
        "fees": _plain(run.fees),
        "entry_notional": _plain(run.entry_notional),
        "final_mark": _plain(run.marks[-1][1]),
    }


def result_document(evaluation: Evaluation) -> dict[str, object]:
    """The result file's content, JSON-ready. Money is a string, a float is rounded to 10 places."""
    return {
        "schema": 1,
        "window": [evaluation.window[0].isoformat(), evaluation.window[1].isoformat()],
        "first_defined": {k: v.isoformat() for k, v in evaluation.first_defined.items()},
        "parameters": {
            "bootstrap_p": evaluation.p,
            "resamples": evaluation.resamples,
            "seed": evaluation.seed,
            "dsr_min": DSR_MIN,
            "fee_percent": _plain(BASE_COSTS.fee_percent),
            "stop_slippage_percent": _plain(BASE_COSTS.stop_slippage_percent),
        },
        "fee_telemetry": [
            {
                "label": t.label,
                "trades": t.trades,
                "gross": _plain(t.gross),
                "fees": _plain(t.fees),
                "net": _plain(t.net),
                "entry_notional": _plain(t.entry_notional),
                "fee_share": None if t.fee_share is None else _plain(t.fee_share),
                "fee_bps": None if t.fee_bps is None else _plain(t.fee_bps),
                "flag": t.flag,
            }
            for t in map(telemetry_of, evaluation.runs)
        ],
        "runs": [
            {
                **_run_figures(r),
                "marks": [[at.isoformat(), _plain(equity)] for at, equity in r.marks],
            }
            for r in evaluation.runs
        ],
        "judgement": _judgement_document(evaluation.judgement),
        "sensitivities": [
            {
                "name": s.costs.name,
                "fee_percent": _plain(s.costs.fee_percent),
                "stop_slippage_percent": _plain(s.costs.stop_slippage_percent),
                "would_select": s.would_select,
                "flips": [
                    {"label": f.label, "gate": f.gate, "before": f.before, "after": f.after}
                    for f in s.flips
                ],
                "runs": [_run_figures(r) for r in s.runs],
                "judgement": _judgement_document(s.judgement),
            }
            for s in evaluation.sensitivities
        ],
        "context": {
            "buy_and_hold_sharpe_annual": _rounded(evaluation.context.sharpe_annual),
            "days": evaluation.context.days,
        },
    }


def canonical_json(document: Mapping[str, object]) -> bytes:
    """The bytes the result file holds and the digest covers: sorted keys, ASCII, one trailing LF."""
    return (json.dumps(document, sort_keys=True, indent=1, ensure_ascii=True) + "\n").encode(
        "ascii"
    )


# --------------------------------------------------------------------------
# The start day, the marks and the context
# --------------------------------------------------------------------------
def _midnight(day: date) -> datetime:
    return datetime(day.year, day.month, day.day, tzinfo=timezone.utc)


def first_defined_open(opens: Sequence[datetime], timeframe: str, bars: int) -> datetime | None:
    """The open time of the first bar that ends a run of ``bars`` consecutive bars, or ``None``.

    A bar the venue did not publish ends a run (R-DZ), so the count restarts after a gap. ``bars`` is the
    strategy's ``warmup_period``, which for every M5n candidate is the rows its window reads (``M5n-206``).
    """
    width = timedelta(milliseconds=timeframe_to_ms(timeframe))
    run = 0
    previous: datetime | None = None
    for opened in opens:
        run = run + 1 if previous is not None and opened - previous == width else 1
        previous = opened
        if run >= bars:
            return opened
    return None


def candidate_starts(
    store: HistoricalStore,
    specs: Sequence[tuple[str, str, str]] | None = None,
    *,
    begin: datetime | None = None,
    end: datetime | None = None,
) -> dict[str, date]:
    """Per candidate, the first UTC day on which its indicators are defined for both pairs: the UTC day of the
    later pair's first defined bar. The span starts at the latest of these (``M5n-206``).

    :raises RunnerError: a candidate has no defined bar on some pair within ``[begin, end)``.
    """
    chosen = CANDIDATES if specs is None else specs
    first_open = IN_SAMPLE_BEGIN if begin is None else begin
    last_open = IN_SAMPLE_END if end is None else end
    out: dict[str, date] = {}
    for label, name, timeframe in chosen:
        bars = registry.create_strategy(name).warmup_period
        days: list[date] = []
        for symbol in PAIRS:
            opens = [
                bar.open_time for bar in store.candles(symbol, timeframe, first_open, last_open)
            ]
            found = first_defined_open(opens, timeframe, bars)
            if found is None:
                raise RunnerError(f"{label} {name} has no defined bar on {symbol} in the span")
            days.append(found.astimezone(timezone.utc).date())
        out[label] = max(days)
    return out


class _MidnightProbe:
    """Samples equity after every decision bar that ends at UTC 00:00, and keeps the last sample per midnight.

    Registered on the provider after the executor and the engine's own probe, so the bar's fills and exits are
    in the portfolio when it samples. Marks are the decision timeframe's last closes, exact ``Decimal``.
    """

    def __init__(self, system: BacktestSystem, timeframe: str) -> None:
        self._system = system
        self._timeframe = timeframe
        self.samples: dict[datetime, Decimal] = {}

    async def __call__(self, candle: Candle) -> None:
        end = (
            candle.open_time + timedelta(milliseconds=timeframe_to_ms(candle.timeframe))
        ).astimezone(timezone.utc)
        if (end.hour, end.minute, end.second, end.microsecond) != (0, 0, 0, 0):
            return
        marks: dict[str, Decimal] = {}
        for symbol in self._system.portfolio.marked_symbols():
            last = self._system.provider.last_candle(symbol, self._timeframe)
            if last is not None:
                marks[symbol] = last.close
        self.samples[_midnight(end.date())] = self._system.portfolio.equity(marks)


def assemble_marks(
    samples: Mapping[datetime, Decimal], start: datetime, end: datetime, initial: Decimal
) -> tuple[tuple[Mark, ...], int]:
    """One mark per UTC midnight from ``start`` to ``end`` inclusive: ``initial`` at ``start``, then each
    sampled equity, with the previous mark carried over a midnight nobody sampled. Returns the marks and how
    many were carried, which the result file reports (``M5n-207``)."""
    marks: list[Mark] = [(start, initial)]
    previous, carried = initial, 0
    day = start + timedelta(days=1)
    while day <= end:
        if day in samples:
            previous = samples[day]
        else:
            carried += 1
        marks.append((day, previous))
        day += timedelta(days=1)
    return tuple(marks), carried


def trade_books(trades: Sequence[SimulatedTrade]) -> tuple[Decimal, Decimal, Decimal]:
    """Gross, fees and entry notional of closed round trips, checking each against the ledger's own figure.

    :raises RunnerError: a trade's realised figure is not its gross less its fees.
    """
    gross = fees = notional = Decimal(0)
    for trade in trades:
        trade_gross = trade.exit_gross - trade.entry_notional
        trade_fees = trade.entry_fee + trade.exit_fee
        if trade.realised != trade_gross - trade_fees:
            raise RunnerError(f"the {trade.symbol} trade of {trade.entry_bar_open} does not add up")
        gross += trade_gross
        fees += trade_fees
        notional += trade.entry_notional
    return gross, fees, notional


async def run_candidate(
    base: Settings,
    spec: tuple[str, str, str],
    window_args: Mapping[str, object],
    costs: Costs,
) -> CandidateRun:
    """Run one candidate over both pairs at ``costs`` and return its books and its daily marks.

    :raises RunnerError: the run was incomplete (an ERROR record, a bar the replay could not serve).
    """
    label, name, timeframe = spec
    effective = apply_overrides(base.config, build_overrides(strategy=name, timeframe=timeframe))
    settings = Settings(
        effective, Secrets(), config_path=base.config_path, config_sha256=base.config_sha256
    )
    window = effective.backtesting.model_copy(
        update={
            **window_args,
            "fee_percent": costs.fee_percent,
            "stop_slippage_percent": costs.stop_slippage_percent,
        }
    )
    async with backtest_system(
        settings,
        window=window,
        exchange_info_environment=effective.backtesting.exchange_info_environment,
        code_facts=lambda: {},
    ) as system:
        probe = _MidnightProbe(system, timeframe)
        system.provider.on_candle(probe)
        result = await system.run()
        if not result.complete:
            raise RunnerError(
                f"{label} {name} at {costs.name} was incomplete: {len(result.problems)} problem(s)"
            )
        gross, fees, notional = trade_books(result.trades)
        marks, carried = assemble_marks(
            probe.samples, window.window_start, window.window_end, window.initial_balance
        )
        open_at_end = len(system.portfolio.open_positions)
        return CandidateRun(
            label=label,
            name=name,
            timeframe=timeframe,
            trades=len(result.trades),
            open_at_end=open_at_end,
            gross=gross,
            fees=fees,
            entry_notional=notional,
            marks=marks,
            carried_marks=carried,
        )


def buy_and_hold_context(
    store: HistoricalStore, start: date, end: date, initial: Decimal
) -> ContextSharpe:
    """Section 10: equal weight in both pairs, bought at the open of the first day and marked at each
    midnight's 1d archive close (``M5n-202``).

    :raises RunnerError: the 1d archive has a missing day inside the span.
    """
    days = (end - start).days
    series: list[list[Mark]] = []
    for symbol in PAIRS:
        bars = list(store.candles(symbol, "1d", _midnight(start), _midnight(end)))
        if len(bars) != days or any(
            bar.open_time.astimezone(timezone.utc) != _midnight(start) + timedelta(days=i)
            for i, bar in enumerate(bars)
        ):
            raise RunnerError(f"the {symbol} 1d archive does not hold {days} consecutive days")
        marks: list[Mark] = [(_midnight(start), bars[0].open)]
        marks.extend(
            (_midnight(start) + timedelta(days=i + 1), bar.close) for i, bar in enumerate(bars)
        )
        series.append(marks)
    returns = daily_series(buy_and_hold_marks(series[0], series[1], initial=initial))
    return ContextSharpe(sharpe(returns), len(returns))


async def evaluate(base: Settings, data_dir: str) -> Evaluation:
    """Run every candidate at the base costs and at each sensitivity, and judge them.

    :raises RunnerError: a run was incomplete, a start day does not exist, or a candidate has no Sharpe.
    """
    store = HistoricalStore(Path(data_dir))
    first = candidate_starts(store)
    start = max(first.values())
    if _midnight(start) >= IN_SAMPLE_END:
        raise RunnerError(f"the span would start on {start}, at or after its end")
    window_args: dict[str, object] = {
        "data_dir": data_dir,
        "start_date": start,
        "end_date": IN_SAMPLE_END.date(),
    }

    def judged(candidate_runs: Sequence[CandidateRun]) -> Judgement:
        # The module's constants are read here, at call time, so a test that moves them is obeyed.
        return judge(candidate_runs, floors=FLOORS, resamples=RESAMPLES, seed=SEED, p=BOOTSTRAP_P)

    runs = tuple([await run_candidate(base, spec, window_args, BASE_COSTS) for spec in CANDIDATES])
    judgement = judged(runs)
    sensitivities: list[Sensitivity] = []
    for costs in SENSITIVITIES:
        other_runs = [await run_candidate(base, spec, window_args, costs) for spec in CANDIDATES]
        other = judged(other_runs)
        sensitivities.append(
            Sensitivity(costs, other, flips_between(judgement, other), tuple(other_runs))
        )
    initial = base.config.backtesting.initial_balance
    context = buy_and_hold_context(store, start, IN_SAMPLE_END.date(), initial)
    return Evaluation(
        window=(start, IN_SAMPLE_END.date()),
        first_defined=first,
        runs=runs,
        judgement=judgement,
        sensitivities=tuple(sensitivities),
        context=context,
        resamples=RESAMPLES,
        seed=SEED,
        p=BOOTSTRAP_P,
    )


def main(argv: Sequence[str] | None = None, out: TextIO | None = None) -> int:
    stream = out if out is not None else sys.stdout
    parser = argparse.ArgumentParser(
        description="The N7 runner: judge the six M5n candidates in sample."
    )
    parser.add_argument("--config", default=DEFAULT_CONFIG)
    parser.add_argument("--data-dir", default=DEFAULT_DATA_DIR)
    parser.add_argument(
        "--out", required=True, help="the result file; refused if it already exists"
    )
    args = parser.parse_args(argv)
    try:
        check_n0_guard(REPO_ROOT)
    except GuardError as exc:
        print(f"refused: {exc.code}: {exc}", file=sys.stderr)
        return 2
    target = Path(args.out)
    if target.exists():
        print(
            f"refused: result_exists: {target} already exists; there is one result file",
            file=sys.stderr,
        )
        return 2
    # The backtester logs every order at INFO, thousands of lines a run; the report is the output. WARNING
    # and above still reach the handlers, and an ERROR record makes a run incomplete in any case.
    logging.disable(logging.INFO)
    try:
        base = get_settings(args.config)
        evaluation = asyncio.run(evaluate(base, args.data_dir))
    except RunnerError as exc:
        print(f"no verdict: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:
        frame = traceback.extract_tb(exc.__traceback__)[-1]
        print(
            f"error: {type(exc).__name__} at {Path(frame.filename).name}:{frame.lineno}",
            file=sys.stderr,
        )
        return 2
    finally:
        logging.disable(logging.NOTSET)
    payload = canonical_json(result_document(evaluation))
    with open(target, "xb") as handle:
        handle.write(payload)
    digest = hashlib.sha256(payload).hexdigest()
    for line in render(evaluation):
        print(line, file=stream)
    print(f"result_file={target}", file=stream)
    print(f"result_sha256={digest}", file=stream)
    return 1 if evaluation.judgement.outcome == "INDETERMINATE" else 0


if __name__ == "__main__":
    sys.exit(main())
