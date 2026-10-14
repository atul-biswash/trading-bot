"""S7's decision gate: read a candidate's three out-of-sample records and say PASS or FAIL by the ruled thresholds.

``docs/research/PROTOCOL.md`` section 7 and the owner's rulings R-D, R-B2, R-BW, R-AJ, R-AT and R-CJ, as they
bind this module.

**What it judges.** A candidate's entry (``status`` ``read``, with ``oos.records`` naming the run directory and
the ``run.json`` SHA-256 of each of the three arms) and those three records. **It PASSES only at the gate arm
(1.20%)**, and only if ALL of these hold (R-D, R-CJ):

* the return profit factor is at least ``profit_factor_min`` (1.3) AND the profit factor in USDT is at least
  ``profit_factor_min`` (R-CJ: both, and both are printed). A profit factor with no losing trade is undefined
  and does NOT meet the test: the gate fails closed rather than reading an undefined quotient as infinite;
* at least ``trades_min`` (100) trades;
* the per-bar maximum drawdown (R-AJ, the record's own figure) is at most ``max_drawdown_max`` (0.20);
* a positive net result in at least ``regimes_positive_min`` (2) of the three regimes, counting complete
  quarters only (R-AT).

The 0.05% and 0.66% records are PRINTED, FOR INFORMATION, and decide nothing (R-B2). The gate prints the
figures, the 216 declared variants (R-CG) and how many candidates were read; it applies no multiple-testing
correction, because none is ruled, and says so.

**What it REFUSES, and each refusal is its own error with its own message** (a refusal prints no verdict for
anyone, so a verdict cannot be harvested from the records that did pass):

1. a record that is not evidence-eligible or is older than schema 6 (the evidence door, R-AR);
2. a record with no protocol block, or whose block is not an out-of-sample read of this entry's candidate;
3. a record made under a different protocol digest (a run made before an amendment is not re-read under it);
4. **a window that does not start exactly at 2024-01-01T00:00Z and end exactly at the history's end (R-BW)**;
5. **an initial balance other than the protocol's configured one**, in any of the four places the record
   states it;
6. a candidate digest that is not the entry's, a variant that is not the one the entry's selection chose, or a
   run directory or ``run.json`` digest that is not the one the entry committed;
7. a set of arms that is not exactly the declared three, once each;
8. records of one candidate made by different code, a different config or different exchange-info snapshots;
9. a record with problems, error-log records or handler failures; a trade log that does not hold the counted
   trades; regime labels that are not the protocol's file; or trades that belong to no regime (an out-of-sample
   window holds only complete quarters, so any such trade means the labels or the window are wrong).

Pure but for :func:`read_arm`, which reads one run directory through the evidence door.
"""

from __future__ import annotations

import hashlib
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Final

from trading_bot.backtesting.candidate import canonical_number
from trading_bot.backtesting.evidence import (
    RUN_RECORD_NAME,
    EvidenceRefusedError,
    load_eligible_record,
)
from trading_bot.backtesting.metrics import load_trades_csv
from trading_bot.backtesting.protocol import (
    Entry,
    Variant,
    declaration,
    parse_protocol,
)
from trading_bot.backtesting.selection import VariantKey, return_profit_factor, variant_key
from trading_bot.core.exceptions import TradingBotError

__all__ = [
    "MIN_RECORD_SCHEMA",
    "ArmRun",
    "CandidateResult",
    "Criterion",
    "GateRefusedError",
    "GateReport",
    "GateRules",
    "GateRulesError",
    "evaluate",
    "evaluate_candidate",
    "parse_gate_rules",
    "read_arm",
    "render_report",
]

MIN_RECORD_SCHEMA: Final = 6
REGIMES: Final = ("rising", "falling", "sideways")
_S7_KEYS: Final = frozenset(
    {"profit_factor_min", "trades_min", "max_drawdown_max", "regimes_positive_min"}
)


class GateRulesError(TradingBotError):
    """The ``s7`` block of the protocol's declaration is missing, mistyped or incoherent."""


class GateRefusedError(TradingBotError):
    """A record or an entry is not something S7 may judge; the message names which rule and why."""


# --------------------------------------------------------------------------
# The rules
# --------------------------------------------------------------------------
@dataclass(frozen=True)
class GateRules:
    """S7's thresholds and the facts a record must match, from one parse of ``PROTOCOL.md``."""

    profit_factor_min: Decimal
    trades_min: int
    max_drawdown_max: Decimal
    regimes_positive_min: int
    gate_arm: str
    arms: tuple[str, ...]
    window_start: date
    window_end: date
    initial_balance: Decimal
    regime_labels_sha256: str
    protocol_sha256: str
    variants_declared: int


def _refuse_rules(message: str) -> GateRulesError:
    return GateRulesError(f"the protocol's s7 block {message}")


def parse_gate_rules(text: str) -> GateRules:
    """The ``s7`` block of the declaration, validated, with the protocol facts it is judged against.

    :raises GateRulesError: the block is absent, has a missing or unknown key, a profit-factor minimum
        that is not positive, a trade minimum below 1, a drawdown ceiling outside (0, 1) or a regime
        minimum outside 1 to 3.
    :raises ProtocolError: the declaration itself is refused by :func:`parse_protocol`.
    """
    protocol = parse_protocol(text)
    block = declaration(text).get("s7")
    if not isinstance(block, Mapping):
        raise _refuse_rules("is absent")
    if set(block) != _S7_KEYS:
        raise _refuse_rules(
            f"has keys {sorted(block)}, and the keys are exactly {sorted(_S7_KEYS)}"
        )

    def decimal(key: str) -> Decimal:
        value = block[key]
        if not isinstance(value, str):
            raise _refuse_rules(f"has {key} that is not a number written as text")
        try:
            number = Decimal(value)
        except InvalidOperation:
            raise _refuse_rules(f"has {key} {value!r}, which is not a number") from None
        if not number.is_finite():
            raise _refuse_rules(f"has {key} that is not finite")
        return number

    def integer(key: str) -> int:
        value = block[key]
        if isinstance(value, bool) or not isinstance(value, int):
            raise _refuse_rules(f"has {key} that is not an integer")
        return value

    factor = decimal("profit_factor_min")
    if factor <= 0:
        raise _refuse_rules("has a profit_factor_min that is not positive")
    trades = integer("trades_min")
    if trades < 1:
        raise _refuse_rules("has a trades_min below 1")
    ceiling = decimal("max_drawdown_max")
    if not Decimal(0) < ceiling < Decimal(1):
        raise _refuse_rules(f"has max_drawdown_max {ceiling}, outside (0, 1)")
    regimes = integer("regimes_positive_min")
    if not 1 <= regimes <= len(REGIMES):
        raise _refuse_rules(f"has regimes_positive_min {regimes}, outside 1 to {len(REGIMES)}")
    return GateRules(
        profit_factor_min=factor,
        trades_min=trades,
        max_drawdown_max=ceiling,
        regimes_positive_min=regimes,
        gate_arm=protocol.gate_arm,
        arms=protocol.arms,
        window_start=protocol.boundary,
        window_end=protocol.history_end,
        initial_balance=Decimal(protocol.costs["initial_balance"]),
        regime_labels_sha256=protocol.regime_labels_sha256,
        protocol_sha256=protocol.sha256,
        variants_declared=sum(1 for _ in protocol.variants()),
    )


# --------------------------------------------------------------------------
# One arm's record
# --------------------------------------------------------------------------
@dataclass(frozen=True)
class ArmRun:
    """One out-of-sample record, after every refusal that can be made from it alone."""

    arm: str
    run: str
    record_sha256: str
    candidate_digest: str
    code_commit: str
    config_sha256: str
    exchange_info: str
    variant_key: VariantKey
    return_profit_factor: Decimal | None
    usdt_profit_factor: Decimal | None
    trades: int
    max_drawdown: Decimal
    regime_net: Mapping[str, Decimal]
    by_pair: Mapping[str, tuple[int, Decimal]]

    @property
    def regimes_positive(self) -> int:
        return sum(1 for value in self.regime_net.values() if value > 0)


def _block(record: Mapping[str, object], key: str, where: str) -> Mapping[str, Any]:
    value = record.get(key)
    if not isinstance(value, Mapping):
        raise GateRefusedError(f"{where} has no {key!r} block")
    return value


def _number(value: object, what: str, where: str) -> Decimal:
    try:
        number = Decimal(str(value))
    except InvalidOperation:
        raise GateRefusedError(f"{where} has {what} {value!r}, which is not a number") from None
    if not number.is_finite():
        raise GateRefusedError(f"{where} has {what} that is not finite")
    return number


def read_arm(directory: Path, entry: Entry, arm: str, rules: GateRules) -> ArmRun:
    """Read one run directory of ``entry`` at ``arm``, refusing it by the rules in the module docstring.

    :raises GateRefusedError: the first rule the record breaks; the message names the rule.
    """
    path = directory / RUN_RECORD_NAME
    where = str(path)
    try:
        record = load_eligible_record(path, min_schema=MIN_RECORD_SCHEMA)
    except EvidenceRefusedError as exc:
        raise GateRefusedError(f"refusal 1, not evidence: {exc}") from exc

    protocol = record.get("protocol")
    if not isinstance(protocol, Mapping):
        raise GateRefusedError(
            f"refusal 2: {where} carries no protocol block, so no guard decided it"
        )
    if protocol.get("window_class") != "out_of_sample":
        raise GateRefusedError(
            f"refusal 2: {where} is a {protocol.get('window_class')!r} run, and S7 judges only "
            "out-of-sample reads"
        )
    if protocol.get("kind") != "candidate" or protocol.get("entry_id") != entry.id:
        raise GateRefusedError(
            f"refusal 2: {where} was decided for entry {protocol.get('entry_id')!r} "
            f"({protocol.get('kind')!r}), not for the candidate entry {entry.id!r}"
        )
    if protocol.get("protocol_sha256") != rules.protocol_sha256:
        raise GateRefusedError(
            f"refusal 3: {where} was made under protocol {protocol.get('protocol_sha256')!r}, and the "
            f"protocol now is {rules.protocol_sha256!r}; a run made before an amendment is not re-read "
            "under it"
        )

    window = _block(record, "window", where)
    start_iso = f"{rules.window_start.isoformat()}T00:00:00+00:00"
    end_iso = f"{rules.window_end.isoformat()}T00:00:00+00:00"
    got = (window.get("start_date"), window.get("end_date"), window.get("start"), window.get("end"))
    if got != (rules.window_start.isoformat(), rules.window_end.isoformat(), start_iso, end_iso):
        raise GateRefusedError(
            f"refusal 4 (R-BW): {where} covers {got[0]} to {got[1]} ({got[2]} to {got[3]}), and an "
            f"out-of-sample figure comes only from a run over exactly {rules.window_start.isoformat()} "
            f"to {rules.window_end.isoformat()} starting at 00:00Z"
        )

    effective = _block(record, "effective", where)
    costs = _block(effective, "costs", where)
    fills = _block(record, "fill_parameters", where)
    equity = _block(record, "equity", where)
    metrics = _block(record, "metrics", where)
    stated = {
        "effective.costs.initial_balance": costs.get("initial_balance"),
        "fill_parameters.initial_balance": fills.get("initial_balance"),
        "equity.initial": equity.get("initial"),
        "metrics.initial_balance": metrics.get("initial_balance"),
    }
    for place, value in stated.items():
        if _number(value, place, where) != rules.initial_balance:
            raise GateRefusedError(
                f"refusal 5 (R-BW): {where} states {place} {value!r}, and the configured initial "
                f"balance is {rules.initial_balance}"
            )

    arm_text = canonical_number(
        _number(costs.get("stop_slippage_percent"), "the stop slippage", where)
    )
    if arm_text != arm:
        raise GateRefusedError(
            f"refusal 7: {where} ran at stop slippage {arm_text}, not the arm {arm}"
        )

    if record.get("candidate_digest") != entry.candidate_digest:
        raise GateRefusedError(
            f"refusal 6: {where} has candidate digest {record.get('candidate_digest')!r}, and the entry "
            f"{entry.id!r} binds {entry.candidate_digest!r}"
        )
    variant = protocol.get("variant")
    if not isinstance(variant, Mapping):
        raise GateRefusedError(f"refusal 2: {where} names no declared variant")
    chosen = (entry.selection or {}).get("variant")
    if not isinstance(chosen, Mapping):
        raise GateRefusedError(
            f"refusal 6: entry {entry.id!r} carries no selection block naming the variant it froze, "
            "so the variant that ran cannot be checked against it"
        )
    if dict(variant) != dict(chosen):
        raise GateRefusedError(
            f"refusal 6: {where} ran variant {dict(variant)!r}, and the entry's selection chose "
            f"{dict(chosen)!r}"
        )

    problems = record.get("problems")
    if problems:
        raise GateRefusedError(f"refusal 9: {where} has problems {problems!r}")
    errors = _block(record, "error_log_records", where).get("count")
    if errors != 0:
        raise GateRefusedError(f"refusal 9: {where} logged {errors!r} error record(s)")
    failures = _block(record, "stream", where).get("handler_failures")
    if failures != 0:
        raise GateRefusedError(f"refusal 9: {where} had {failures!r} handler failure(s)")
    labels = _block(record, "regime_labels", where).get("sha256")
    if labels != rules.regime_labels_sha256:
        raise GateRefusedError(
            f"refusal 9: {where} used regime labels {labels!r}, not the protocol's {rules.regime_labels_sha256!r}"
        )

    overall = _block(metrics, "overall", where)
    counted = overall.get("trades")
    results = _block(record, "results", where)
    try:
        trades = load_trades_csv(directory / "trades.csv")
    except (OSError, KeyError, ValueError, InvalidOperation) as exc:
        raise GateRefusedError(
            f"refusal 9: {directory / 'trades.csv'} cannot be read: {exc}"
        ) from exc
    if not (isinstance(counted, int) and counted == results.get("trades") == len(trades)):
        raise GateRefusedError(
            f"refusal 9: {where} counts {counted!r} trades, its results say {results.get('trades')!r} and "
            f"trades.csv holds {len(trades)}"
        )

    by_regime = _block(metrics, "by_regime", where)
    unlabelled = _block(by_regime, "unlabelled", where).get("trades", 0)
    if unlabelled != 0:
        raise GateRefusedError(
            f"refusal 9 (R-AT): {where} has {unlabelled!r} trade(s) in no regime; an out-of-sample window "
            "holds only complete quarters, so the labels or the window are wrong"
        )
    regime_net = {
        regime: _number(_block(by_regime, regime, where).get("net_pnl"), f"{regime} net_pnl", where)
        for regime in REGIMES
    }
    by_pair_block = _block(metrics, "by_pair", where)
    by_pair = {
        symbol: (
            int(_block(by_pair_block, symbol, where).get("trades", 0)),
            _number(
                _block(by_pair_block, symbol, where).get("net_pnl"), f"{symbol} net_pnl", where
            ),
        )
        for symbol in sorted(by_pair_block)
    }
    usdt = overall.get("profit_factor_net")
    code = _block(record, "code", where)
    config = _block(record, "config", where)
    info = record.get("exchange_info")
    return ArmRun(
        arm=arm,
        run=directory.name,
        record_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
        candidate_digest=str(record["candidate_digest"]),
        code_commit=str(code.get("code_commit")),
        config_sha256=str(config.get("sha256")),
        exchange_info=repr(sorted(info.items())) if isinstance(info, Mapping) else repr(info),
        variant_key=_variant_key_of(variant),
        return_profit_factor=return_profit_factor(trades),
        usdt_profit_factor=None if usdt is None else _number(usdt, "profit_factor_net", where),
        trades=counted,
        max_drawdown=_number(metrics.get("max_drawdown"), "max_drawdown", where),
        regime_net=regime_net,
        by_pair=by_pair,
    )


def _variant_key_of(variant: Mapping[str, Any]) -> VariantKey:
    """The selection's variant key, from the block a record carries."""
    params = variant.get("params")
    return variant_key(
        Variant(
            str(variant.get("family")),
            str(variant.get("timeframe")),
            bool(variant.get("filtered")),
            {str(k): str(v) for k, v in (params.items() if isinstance(params, Mapping) else ())},
        )
    )


# --------------------------------------------------------------------------
# One candidate
# --------------------------------------------------------------------------
@dataclass(frozen=True)
class Criterion:
    """One S7 test: its figure, its threshold, and whether the figure meets it."""

    name: str
    figure: str
    threshold: str
    met: bool


@dataclass(frozen=True)
class CandidateResult:
    entry_id: str
    candidate_digest: str
    arms: tuple[ArmRun, ...]
    gate: ArmRun
    criteria: tuple[Criterion, ...]

    @property
    def passed(self) -> bool:
        return all(c.met for c in self.criteria)


def _pf(value: Decimal | None) -> str:
    return "undefined (no losing trade)" if value is None else f"{value:.6f}"


def evaluate_candidate(
    entry: Entry, arm_runs: Sequence[ArmRun], rules: GateRules
) -> CandidateResult:
    """Cross-check one candidate's three records and apply S7's tests to the gate arm.

    :raises GateRefusedError: the arms are not exactly the declared three once each, or the records of
        one candidate disagree on the candidate, the code, the config, the snapshots or the variant.
    """
    arms = [run.arm for run in arm_runs]
    if sorted(arms) != sorted(rules.arms):
        raise GateRefusedError(
            f"refusal 7: entry {entry.id!r} has records at arms {sorted(arms)}, and the declared arms "
            f"are {sorted(rules.arms)}, once each"
        )
    for label, values in (
        ("candidate digest", {r.candidate_digest for r in arm_runs}),
        ("code commit", {r.code_commit for r in arm_runs}),
        ("config digest", {r.config_sha256 for r in arm_runs}),
        ("exchange-info snapshots", {r.exchange_info for r in arm_runs}),
        ("variant", {repr(r.variant_key) for r in arm_runs}),
    ):
        if len(values) != 1:
            raise GateRefusedError(
                f"refusal 8: the records of entry {entry.id!r} differ in their {label}: the three arms "
                "must come from one candidate, one code commit and one config"
            )
    gate = next(r for r in arm_runs if r.arm == rules.gate_arm)
    floor = rules.profit_factor_min
    criteria = (
        Criterion(
            "profit factor from per-trade returns",
            _pf(gate.return_profit_factor),
            f">= {floor}",
            gate.return_profit_factor is not None and gate.return_profit_factor >= floor,
        ),
        Criterion(
            "profit factor in USDT",
            _pf(gate.usdt_profit_factor),
            f">= {floor}",
            gate.usdt_profit_factor is not None and gate.usdt_profit_factor >= floor,
        ),
        Criterion(
            "trades", str(gate.trades), f">= {rules.trades_min}", gate.trades >= rules.trades_min
        ),
        Criterion(
            "maximum drawdown (per bar)",
            f"{gate.max_drawdown:.6f}",
            f"<= {rules.max_drawdown_max}",
            gate.max_drawdown <= rules.max_drawdown_max,
        ),
        Criterion(
            "regimes with a positive net result",
            f"{gate.regimes_positive} of {len(REGIMES)}",
            f">= {rules.regimes_positive_min}",
            gate.regimes_positive >= rules.regimes_positive_min,
        ),
    )
    ordered = tuple(sorted(arm_runs, key=lambda r: Decimal(r.arm)))
    return CandidateResult(entry.id, entry.candidate_digest, ordered, gate, criteria)


# --------------------------------------------------------------------------
# The report over every read candidate
# --------------------------------------------------------------------------
@dataclass(frozen=True)
class GateReport:
    rules: GateRules
    results: tuple[CandidateResult, ...]
    pending: tuple[str, ...]

    @property
    def passed(self) -> tuple[CandidateResult, ...]:
        return tuple(r for r in self.results if r.passed)


def evaluate(entries: Sequence[Entry], backtests: Path, rules: GateRules) -> GateReport:
    """Judge every candidate entry that has been read; list the pending ones.

    :raises GateRefusedError: an entry that is ``read`` has no usable ``oos.records``, or any record of
        any candidate is refused. No verdict is returned if any is.
    """
    results: list[CandidateResult] = []
    pending: list[str] = []
    for entry in entries:
        if entry.kind != "candidate":
            continue
        if entry.status != "read":
            pending.append(entry.id)
            continue
        records = (entry.oos or {}).get("records")
        if not isinstance(records, Mapping) or not records:
            raise GateRefusedError(
                f"refusal 6: entry {entry.id!r} is read and holds no oos.records"
            )
        runs: list[ArmRun] = []
        for arm, committed in sorted(records.items()):
            if not isinstance(committed, Mapping):
                raise GateRefusedError(
                    f"refusal 6: entry {entry.id!r} arm {arm!r} is not an object"
                )
            name, expected = committed.get("run"), committed.get("run_json_sha256")
            if not isinstance(name, str) or not isinstance(expected, str):
                raise GateRefusedError(
                    f"refusal 6: entry {entry.id!r} arm {arm!r} lacks run or run_json_sha256"
                )
            arm_run = read_arm(backtests / name, entry, canonical_number(Decimal(arm)), rules)
            if arm_run.record_sha256 != expected:
                raise GateRefusedError(
                    f"refusal 6: {name} has run.json SHA-256 {arm_run.record_sha256}, and entry "
                    f"{entry.id!r} committed {expected}"
                )
            runs.append(arm_run)
        results.append(evaluate_candidate(entry, runs, rules))
    return GateReport(rules, tuple(results), tuple(pending))


def render_report(report: GateReport) -> str:
    """The figures, the variant count and the verdict by the ruled thresholds; no correction is applied."""
    rules = report.rules
    lines = [
        "S7 DECISION GATE (PROTOCOL.md section 7; a pass is the gate arm only)",
        f"  protocol sha256 {rules.protocol_sha256}",
        f"  variants declared {rules.variants_declared} (the denominator of any multiple-testing judgement);"
        f" candidates read {len(report.results)}; still pending {len(report.pending)}",
        f"  thresholds: both profit factors >= {rules.profit_factor_min}; trades >= {rules.trades_min};"
        f" per-bar drawdown <= {rules.max_drawdown_max}; >= {rules.regimes_positive_min} of {len(REGIMES)}"
        " regimes net positive (complete quarters)",
        "  no multiple-testing correction is applied: none is ruled, and the count above is for the reader",
    ]
    for result in report.results:
        lines.append("")
        lines.append(f"CANDIDATE {result.entry_id}  digest {result.candidate_digest}")
        lines.append(
            "  arm      trades  return PF    USDT PF      max dd     regimes+  (information except the gate arm)"
        )
        for run in result.arms:
            mark = "  <- GATE ARM" if run.arm == rules.gate_arm else ""
            lines.append(
                f"  {run.arm:<7}  {run.trades:>6}  {_pf(run.return_profit_factor):<11}  "
                f"{_pf(run.usdt_profit_factor):<11}  {run.max_drawdown:.6f}   {run.regimes_positive} of {len(REGIMES)}{mark}"
            )
        for criterion in result.criteria:
            lines.append(
                f"  {'MET    ' if criterion.met else 'NOT MET'}  {criterion.name}: {criterion.figure}"
                f"  (threshold {criterion.threshold})"
            )
        regimes = ", ".join(f"{k} {v}" for k, v in result.gate.regime_net.items())
        lines.append(f"  regime net P&L at the gate arm: {regimes}")
        pairs = ", ".join(f"{k} {n} trades net {v}" for k, (n, v) in result.gate.by_pair.items())
        lines.append(f"  per pair at the gate arm: {pairs}")
        lines.append(f"  S7: {'PASS' if result.passed else 'FAIL'}")
    for entry_id in report.pending:
        lines.append(f"PENDING {entry_id}: not read out of sample, so not judged")
    lines.append("")
    lines.append(f"S7 SUMMARY: {len(report.passed)} of {len(report.results)} candidates read PASS")
    return "\n".join(lines) + "\n"
