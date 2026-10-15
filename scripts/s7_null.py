"""S7's null check (R-CS): how likely is a strategy with NO edge to pass S7, for the candidates actually chosen?

``python scripts/s7_null.py --backtests DIR [--entries-dir DIR] [--protocol FILE] [--labels FILE]
[--draws N] [--seed N] [--out FILE]``

R-CS, verbatim: *"Before any out-of-sample read, the chance that a strategy with no edge passes all four S7 tests is
computed for the actual candidate count, by a committed script whose method is stated in its commit. It informs the
reading of S7's result and does not gate it."* ("Four tests" is S7's four thresholds: the profit factor, which the gate
reads two ways and which counts as two tests below, the trade count, the drawdown and the regime test.)

**Reads, writes nothing but ``--out``.** It reads each candidate's pending entry (``docs/research/entries``), that
entry's IN-SAMPLE run directory under ``--backtests`` through the evidence door (the run's ``run.json`` SHA-256 must be
the one the entry froze), the protocol, and the committed regime labels (``docs/REGIME_LABELS.json``, checked against
its digest file). **It reads no bar and no out-of-sample record** (R-CN): the only out-of-sample facts it uses are the
window's dates and the committed quarter labels.

**The method, so that a reader can judge the number.** For each candidate, from its OWN in-sample trades:

1. Each trade's return is ``realised / entry_quote_total`` and its size is ``entry_quote_total``. The null DEMEANS the
   returns (subtracts their mean), so a strategy with exactly zero expected edge net of costs is simulated: the most
   generous no-edge null, since a strategy with no skill pays its costs and loses. The un-demeaned (as-observed) null is
   also reported, as a sensitivity.
2. A simulated out-of-sample sequence has, in each of the window's complete calendar quarters, a POISSON number of
   trades whose mean is the candidate's in-sample trade rate for quarters of that quarter's regime LABEL (trades per
   day, from the in-sample quarters carrying the same label) times the quarter's days. That is "the candidate's in-sample
   trade rate times the window's days", refined by regime; a sensitivity uses one rate for every quarter.
3. Each simulated trade is a (return, size) PAIR drawn with replacement from the candidate's in-sample trades, so the
   shape of its returns and their relation to size are kept. Its profit and loss in USDT is the demeaned return times
   its size.
4. The five S7 criteria are then evaluated exactly as ``backtesting/gate.py`` defines them, on the simulated gate-arm
   sequence: the profit factor from per-trade returns at least 1.3, the profit factor in USDT at least 1.3 (a profit
   factor with no losing trade does NOT pass), at least 100 trades, the drawdown of the simulated equity path at most
   0.20, and a positive net P&L in at least 2 of the 3 regimes, each trade placed in the regime of the quarter it falls
   in. The per-candidate pass probability is the share of draws that meet ALL of them.
5. **Family-wise:** the probability that at least one of the N candidates passes. The candidates' trades overlap in
   time, so they are not independent; the script prints the independence figure ``1 - prod(1 - p)`` and the two bounds
   that hold whatever the dependence, ``max(p)`` and ``min(1, sum(p))``. The truth lies between the bounds, and the
   independence figure is above it where the candidates are positively dependent.

**Approximations, every one of them stated.**

* Trades are exchangeable draws: no autocorrelation, no clustering of wins and losses in time, no dependence of a
  trade's return on its regime (which is what "no edge" means, but a real market has volatility clustering that
  widens the spread of a sum and so RAISES the chance of a pass).
* The equity path is the sequence of trade closes in time order from the configured initial balance (10,000). It
  omits the mark-to-market of open positions that the gate's per-bar drawdown includes, so it UNDERSTATES the
  drawdown, which overstates the pass probability. The drawdown test almost never binds (the share of draws that fail
  it is printed).
* Sizes are the in-sample trades' own sizes, not re-derived from the simulated equity.
* Two pairs trade at once in the real runs; here every trade is one step of one path.
* The thresholds are compared in float64. ``float(Decimal)`` is converted once, at the named boundary
  ``_floats``; this script is a Monte Carlo whose outputs are probabilities, not money, and no money figure is
  written by it.
* The simulation is seeded (``--seed``) and so reproducible for a given NumPy; the Monte Carlo standard error of each
  probability is printed.

Exit status: 0 done; 2 refused. Output is ASCII.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any, Final

import numpy as np
from numpy.typing import NDArray

from trading_bot.backtesting import selection as sel
from trading_bot.backtesting.gate import REGIMES, GateRules, parse_gate_rules
from trading_bot.backtesting.metrics import TradeFacts
from trading_bot.backtesting.protocol import (
    PROTOCOL_PATH,
    Entry,
    ProtocolError,
    Variant,
    load_entries,
    parse_protocol,
)
from trading_bot.backtesting.regimes import RegimeTable, quarter_bounds, quarter_key
from trading_bot.core.exceptions import TradingBotError

__all__ = [
    "Candidate",
    "Model",
    "Outcome",
    "build_model",
    "family_wise",
    "load_candidates",
    "main",
    "simulate",
]

EXIT_REFUSED: Final = 2
SCHEMA: Final = 1
LABELS_PATH: Final = Path("docs") / "REGIME_LABELS.json"
DEFAULT_DRAWS: Final = 100_000
DEFAULT_SEED: Final = 20261015
_CHUNK: Final = 1_000
_INITIAL: Final = 10_000.0
_CRITERIA: Final = ("profit_factor_return", "profit_factor_usdt", "trades", "drawdown", "regimes")

Floats = NDArray[np.float64]
Ints = NDArray[np.int64]


class NullRefusedError(TradingBotError):
    """The inputs cannot support a null check; the message says which and why."""


# --------------------------------------------------------------------------
# Inputs
# --------------------------------------------------------------------------
@dataclass(frozen=True)
class Candidate:
    """One candidate: its entry, and the in-sample trades it was chosen on."""

    entry_id: str
    variant: str
    trades: tuple[TradeFacts, ...]
    in_sample_days: int


def load_candidates(
    entries: Sequence[Entry],
    backtests: Path,
    protocol: Any,
    rules: sel.SelectionRules,
) -> tuple[Candidate, ...]:
    """Every candidate entry's in-sample run, read through the evidence door and checked against the entry.

    :raises NullRefusedError: an entry names no in-sample run, the run is not a point run, or its
        ``run.json`` SHA-256 is not the one the entry froze.
    """
    found: list[Candidate] = []
    for entry in entries:
        if entry.kind != "candidate":
            continue
        chosen = entry.selection or {}
        run = chosen.get("in_sample_run")
        frozen = chosen.get("in_sample_run_json_sha256")
        if not isinstance(run, str) or not isinstance(frozen, str):
            raise NullRefusedError(
                f"entry {entry.id!r} names no in-sample run and no digest for it"
            )
        point = sel.read_run(backtests / run, protocol, rules)
        if not isinstance(point, sel.PointRun):
            raise NullRefusedError(
                f"entry {entry.id!r}: {run} is not a point run ({point.reason.value}: {point.detail})"
            )
        if point.record_sha256 != frozen:
            raise NullRefusedError(
                f"entry {entry.id!r}: {run} has record SHA-256 {point.record_sha256}, and the "
                f"entry froze {frozen}"
            )
        found.append(
            Candidate(
                entry_id=entry.id,
                variant=_describe(point.variant),
                trades=point.trades,
                in_sample_days=(rules.boundary - rules.history_start).days,
            )
        )
    return tuple(found)


def _describe(variant: Variant) -> str:
    """``rsi 1h filter off (overbought=70, oversold=30, period=7)``."""
    params = ", ".join(f"{k}={v}" for k, v in sorted(variant.params.items()))
    return f"{variant.family} {variant.timeframe} filter {'on' if variant.filtered else 'off'} ({params})"


def _floats(values: Sequence[Decimal]) -> Floats:
    """The one Decimal-to-float64 boundary of this script (see the module docstring)."""
    return np.array([float(v) for v in values], dtype=np.float64)


def _quarters(first: date, end: date) -> list[str]:
    """The keys of the calendar quarters that lie wholly inside ``[first, end)``."""
    keys: list[str] = []
    day = first
    while day < end:
        key = quarter_key(day)
        start, stop = quarter_bounds(key)
        if start >= first and stop <= end:
            keys.append(key)
        day = stop
    return keys


@dataclass(frozen=True)
class Model:
    """A candidate's null model: what is drawn, and where it is placed."""

    returns: Floats
    sizes: Floats
    quarter_means: Floats
    quarter_regime: Ints
    quarter_days: Ints
    thresholds: tuple[float, int, float, int]
    mean_return: float
    expected_simple: float
    expected_by_regime: float


def build_model(
    candidate: Candidate,
    *,
    rules: GateRules,
    sel_rules: sel.SelectionRules,
    table: RegimeTable,
    demean: bool = True,
    uniform_timing: bool = False,
) -> Model:
    """The null model of ``candidate``; ``demean`` zeroes its mean return, ``uniform_timing`` drops the regime rates.

    :raises NullRefusedError: the candidate has no trade, or an out-of-sample quarter has no label.
    """
    trades = candidate.trades
    if not trades:
        raise NullRefusedError(
            f"candidate {candidate.entry_id!r} has no in-sample trade to draw from"
        )
    sizes = _floats([t.entry_quote_total for t in trades])
    returns = _floats([t.realised for t in trades]) / sizes
    mean = float(returns.mean())
    if demean:
        returns = returns - mean

    regime_index = {name: i for i, name in enumerate(REGIMES)}
    in_sample = _quarters(sel_rules.history_start, sel_rules.boundary)
    days_by_regime = np.zeros(len(REGIMES), dtype=np.float64)
    trades_by_regime = np.zeros(len(REGIMES), dtype=np.float64)
    by_quarter: dict[str, int] = {}
    for trade in trades:
        key = quarter_key(trade.entry_time.date())
        by_quarter[key] = by_quarter.get(key, 0) + 1
    for key in in_sample:
        label = table.regime_on(quarter_bounds(key)[0])
        if label is None:
            continue
        start, stop = quarter_bounds(key)
        days_by_regime[regime_index[label.value]] += (stop - start).days
        trades_by_regime[regime_index[label.value]] += by_quarter.get(key, 0)
    labelled_days = float(days_by_regime.sum())
    if labelled_days == 0:
        raise NullRefusedError("no in-sample quarter carries a regime label")
    overall_rate = float(trades_by_regime.sum()) / labelled_days
    rates = np.where(
        days_by_regime > 0, trades_by_regime / np.maximum(days_by_regime, 1.0), overall_rate
    )

    quarters = _quarters(rules.window_start, rules.window_end)
    if not quarters:
        raise NullRefusedError("the out-of-sample window holds no complete quarter")
    regime: list[int] = []
    days: list[int] = []
    for key in quarters:
        start, stop = quarter_bounds(key)
        label = table.regime_on(start)
        if label is None:
            raise NullRefusedError(f"out-of-sample quarter {key} has no regime label")
        regime.append(regime_index[label.value])
        days.append((stop - start).days)
    quarter_regime = np.array(regime, dtype=np.int64)
    quarter_days = np.array(days, dtype=np.int64)
    simple = len(trades) / candidate.in_sample_days
    by_regime_mean = rates[quarter_regime] * quarter_days
    means = (
        np.full(len(quarters), simple, dtype=np.float64) * quarter_days
        if uniform_timing
        else by_regime_mean
    )
    return Model(
        returns=returns,
        sizes=sizes,
        quarter_means=means.astype(np.float64),
        quarter_regime=quarter_regime,
        quarter_days=quarter_days,
        thresholds=(
            float(rules.profit_factor_min),
            rules.trades_min,
            float(rules.max_drawdown_max),
            rules.regimes_positive_min,
        ),
        mean_return=mean,
        expected_simple=simple * float(quarter_days.sum()),
        expected_by_regime=float(by_regime_mean.sum()),
    )


# --------------------------------------------------------------------------
# The simulation
# --------------------------------------------------------------------------
@dataclass(frozen=True)
class Outcome:
    """The counts of one simulation: draws, the draws meeting everything, and each criterion alone."""

    draws: int
    passed: int
    met: Mapping[str, int]
    trades_total: int

    @property
    def probability(self) -> float:
        return self.passed / self.draws

    @property
    def standard_error(self) -> float:
        p = self.probability
        return float(np.sqrt(p * (1.0 - p) / self.draws))


def evaluate_chunk(
    model: Model, indices: Ints, counts: Ints
) -> tuple[NDArray[np.bool_], dict[str, NDArray[np.bool_]], Ints]:
    """The five criteria for a block of simulated sequences, given the drawn trade indices and per-quarter counts.

    ``indices`` is (draws, longest sequence), padded; ``counts`` is (draws, quarters). Trade ``k`` of a draw falls in the
    quarter whose cumulative count first exceeds ``k``, so the trades are in time order.
    """
    floor, trades_min, ceiling, regimes_min = model.thresholds
    totals = counts.sum(axis=1)
    live = np.arange(indices.shape[1])[None, :] < totals[:, None]
    ret = np.where(live, model.returns[indices], 0.0)
    pnl = np.where(live, model.returns[indices] * model.sizes[indices], 0.0)

    gains_r, losses_r = np.clip(ret, 0.0, None).sum(axis=1), np.clip(-ret, 0.0, None).sum(axis=1)
    gains_u, losses_u = np.clip(pnl, 0.0, None).sum(axis=1), np.clip(-pnl, 0.0, None).sum(axis=1)
    pf_return = (losses_r > 0) & (gains_r >= floor * losses_r)
    pf_usdt = (losses_u > 0) & (gains_u >= floor * losses_u)

    cumulative = np.concatenate([np.zeros((pnl.shape[0], 1)), np.cumsum(pnl, axis=1)], axis=1)
    equity = _INITIAL + cumulative
    peak = np.maximum.accumulate(equity, axis=1)
    drawdown = ((peak - equity) / peak).max(axis=1)

    upper = np.cumsum(counts, axis=1)
    lower = np.concatenate([np.zeros((counts.shape[0], 1), dtype=np.int64), upper[:, :-1]], axis=1)
    per_quarter = np.take_along_axis(cumulative, upper, axis=1) - np.take_along_axis(
        cumulative, lower, axis=1
    )
    positive = np.zeros(counts.shape[0], dtype=np.int64)
    for index in range(len(REGIMES)):
        net = per_quarter[:, model.quarter_regime == index].sum(axis=1)
        positive += (net > 0).astype(np.int64)

    flags = {
        "profit_factor_return": pf_return,
        "profit_factor_usdt": pf_usdt,
        "trades": totals >= trades_min,
        "drawdown": drawdown <= ceiling,
        "regimes": positive >= regimes_min,
    }
    everything = np.logical_and.reduce(list(flags.values()))
    return everything, flags, totals


def simulate(model: Model, *, draws: int, seed: int) -> Outcome:
    """``draws`` null sequences for ``model``; reproducible for a given ``seed``."""
    rng = np.random.default_rng(seed)
    met = dict.fromkeys(_CRITERIA, 0)
    passed = 0
    trades_total = 0
    done = 0
    while done < draws:
        size = min(_CHUNK, draws - done)
        counts = rng.poisson(model.quarter_means, size=(size, len(model.quarter_means))).astype(
            np.int64
        )
        longest = max(int(counts.sum(axis=1).max()), 1)
        indices = rng.integers(0, len(model.returns), size=(size, longest)).astype(np.int64)
        everything, flags, totals = evaluate_chunk(model, indices, counts)
        passed += int(everything.sum())
        trades_total += int(totals.sum())
        for name in _CRITERIA:
            met[name] += int(flags[name].sum())
        done += size
    return Outcome(draws=draws, passed=passed, met=met, trades_total=trades_total)


def family_wise(probabilities: Sequence[float]) -> dict[str, float]:
    """The chance that at least one candidate passes: independence, and the bounds that hold whatever the dependence."""
    if not probabilities:
        return {"independent": 0.0, "lower_bound": 0.0, "upper_bound": 0.0}
    none = 1.0
    for p in probabilities:
        none *= 1.0 - p
    return {
        "independent": 1.0 - none,
        "lower_bound": max(probabilities),
        "upper_bound": min(1.0, sum(probabilities)),
    }


# --------------------------------------------------------------------------
# Report
# --------------------------------------------------------------------------
def _p(value: float) -> str:
    return f"{value:.6f}"


def _result(outcome: Outcome) -> dict[str, Any]:
    return {
        "draws": outcome.draws,
        "passes": outcome.passed,
        "probability": _p(outcome.probability),
        "standard_error": _p(outcome.standard_error),
        "mean_trades": f"{outcome.trades_total / outcome.draws:.2f}",
        "criteria_met": {name: outcome.met[name] for name in _CRITERIA},
    }


def render_report(document: Mapping[str, Any]) -> str:
    """The document as text, ASCII."""
    lines = [
        "S7 NULL CHECK (R-CS): the chance that a strategy with no edge passes S7",
        f"  protocol sha256 {document['protocol_sha256']}; regime labels sha256 {document['labels_sha256']}",
        f"  draws {document['draws']} a candidate, seed {document['seed']}, numpy {document['numpy']}",
        f"  window {document['window']['start']} to {document['window']['end']}: "
        f"{document['window']['days']} days, {len(document['oos_quarters'])} complete quarters, regimes "
        + ", ".join(f"{k} {v}" for k, v in document["oos_regime_counts"].items()),
        "  thresholds: " + ", ".join(f"{k} {v}" for k, v in document["thresholds"].items()),
        "  method: see the docstring of scripts/s7_null.py; the null demeans each candidate's own in-sample returns",
        "",
    ]
    for item in document["candidates"]:
        primary = item["primary"]
        lines += [
            f"CANDIDATE {item['entry_id']}  {item['variant']}",
            f"  in-sample trades {item['in_sample_trades']} over {item['in_sample_days']} days; "
            f"mean return per trade {item['mean_return_percent']} percent (removed by the null)",
            f"  expected out-of-sample trades: {item['expected_trades_simple']} by the plain rate, "
            f"{item['expected_trades_by_regime']} by the regime rates",
            f"  NO-EDGE PASS PROBABILITY {primary['probability']}  (standard error {primary['standard_error']}, "
            f"{primary['passes']} of {primary['draws']} draws, mean {primary['mean_trades']} trades)",
            "  each test alone, share of draws meeting it: "
            + ", ".join(
                f"{k} {int(v) / primary['draws']:.4f}" for k, v in primary["criteria_met"].items()
            ),
            f"  sensitivity, in-sample mean return kept (as observed): {item['as_observed']['probability']}",
            f"  sensitivity, one trade rate for every quarter: {item['uniform_timing']['probability']}",
            "",
        ]
    fw = document["family_wise"]
    lines += [
        f"FAMILY-WISE over {len(document['candidates'])} candidates (the null model, primary):",
        f"  at least one passes, if independent: {fw['independent']}",
        f"  whatever the dependence, between {fw['lower_bound']} and {fw['upper_bound']}",
        "  the candidates share a market and their trades overlap, so they are not independent;",
        "  the truth lies between the bounds and the independent figure is above it for positively dependent candidates.",
        "  This informs the reading of S7's result and does not gate it (R-CS).",
    ]
    return "\n".join(lines) + "\n"


def build_document(
    candidates: Sequence[Candidate],
    *,
    protocol_sha256: str,
    labels_sha256: str,
    rules: GateRules,
    sel_rules: sel.SelectionRules,
    table: RegimeTable,
    draws: int,
    seed: int,
) -> dict[str, Any]:
    """Run the three nulls for every candidate and assemble the document."""
    quarters = _quarters(rules.window_start, rules.window_end)
    labels = [table.regime_on(quarter_bounds(key)[0]) for key in quarters]
    regime_counts = {
        name: sum(1 for label in labels if label is not None and label.value == name)
        for name in REGIMES
    }
    items: list[dict[str, Any]] = []
    primaries: list[float] = []
    for index, candidate in enumerate(candidates):
        model = build_model(candidate, rules=rules, sel_rules=sel_rules, table=table)
        observed = build_model(
            candidate, rules=rules, sel_rules=sel_rules, table=table, demean=False
        )
        uniform = build_model(
            candidate, rules=rules, sel_rules=sel_rules, table=table, uniform_timing=True
        )
        # One stream per candidate and per variant, derived from the seed, so adding a candidate moves no other.
        primary = simulate(model, draws=draws, seed=seed + 1000 * index)
        primaries.append(primary.probability)
        items.append(
            {
                "entry_id": candidate.entry_id,
                "variant": candidate.variant,
                "in_sample_trades": len(candidate.trades),
                "in_sample_days": candidate.in_sample_days,
                "mean_return_percent": f"{model.mean_return * 100:.4f}",
                "expected_trades_simple": f"{model.expected_simple:.2f}",
                "expected_trades_by_regime": f"{model.expected_by_regime:.2f}",
                "primary": _result(primary),
                "as_observed": _result(
                    simulate(observed, draws=draws, seed=seed + 1000 * index + 1)
                ),
                "uniform_timing": _result(
                    simulate(uniform, draws=draws, seed=seed + 1000 * index + 2)
                ),
            }
        )
    return {
        "s7_null_schema": SCHEMA,
        "protocol_sha256": protocol_sha256,
        "labels_sha256": labels_sha256,
        "draws": draws,
        "seed": seed,
        "numpy": np.__version__,
        "window": {
            "start": rules.window_start.isoformat(),
            "end": rules.window_end.isoformat(),
            "days": (rules.window_end - rules.window_start).days,
        },
        "oos_quarters": [
            {"quarter": key, "regime": None if label is None else label.value}
            for key, label in zip(quarters, labels, strict=True)
        ],
        "oos_regime_counts": regime_counts,
        "thresholds": {
            "profit_factor_min": str(rules.profit_factor_min),
            "trades_min": rules.trades_min,
            "max_drawdown_max": str(rules.max_drawdown_max),
            "regimes_positive_min": rules.regimes_positive_min,
        },
        "candidates": items,
        "family_wise": {k: _p(v) for k, v in family_wise(primaries).items()},
    }


# --------------------------------------------------------------------------
# Command line
# --------------------------------------------------------------------------
def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="s7_null.py",
        description="The chance that a strategy with no edge passes S7, for the chosen candidates (R-CS).",
    )
    parser.add_argument(
        "--backtests", required=True, type=Path, help="the sweep clone's backtests directory"
    )
    parser.add_argument("--entries-dir", type=Path, default=None, help="the candidates' entries")
    parser.add_argument("--protocol", type=Path, default=PROTOCOL_PATH, help="the protocol file")
    parser.add_argument(
        "--labels", type=Path, default=LABELS_PATH, help="the committed regime labels"
    )
    parser.add_argument(
        "--draws", type=int, default=DEFAULT_DRAWS, help="simulated sequences a candidate"
    )
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED, help="the random seed")
    parser.add_argument("--out", type=Path, default=None, help="write the document (JSON) here")
    return parser


def _refuse(message: str) -> int:
    print(f"REFUSED: {message}", file=sys.stderr)
    return EXIT_REFUSED


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.draws < 1:
        return _refuse("--draws must be at least 1")
    try:
        text = args.protocol.read_text(encoding="utf-8")
        protocol = parse_protocol(text)
        sel_rules = sel.parse_rules(text)
        rules = parse_gate_rules(text)
        entries_dir = (
            args.entries_dir if args.entries_dir is not None else args.protocol.parent / "entries"
        )
        entries = [e for e in load_entries(entries_dir) if e.kind == "candidate"]
        table = RegimeTable.from_file(args.labels)
    except (OSError, ProtocolError, sel.SelectionRulesError, TradingBotError, ValueError) as exc:
        return _refuse(f"the inputs cannot be used: {exc}")
    if not entries:
        return _refuse(f"{entries_dir} holds no candidate entry")
    if not args.backtests.is_dir():
        return _refuse(f"{args.backtests} is not a directory")
    try:
        candidates = load_candidates(entries, args.backtests, protocol, sel_rules)
        document = build_document(
            candidates,
            protocol_sha256=protocol.sha256,
            labels_sha256=str(table.digest),
            rules=rules,
            sel_rules=sel_rules,
            table=table,
            draws=args.draws,
            seed=args.seed,
        )
    except NullRefusedError as exc:
        return _refuse(str(exc))
    print(render_report(document), end="")
    if args.out is not None:
        data = (json.dumps(document, indent=2, sort_keys=True, ensure_ascii=True) + "\n").encode(
            "ascii"
        )
        args.out.write_bytes(data)
        print(f"document {args.out} ({len(data)} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
