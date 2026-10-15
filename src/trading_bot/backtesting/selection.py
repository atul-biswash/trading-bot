"""S6's selection: one candidate per cell from the in-sample runs, and the walk-forward report (PROTOCOL.md section 6).

The owner's rulings, as they bind this module (``docs/research/PROTOCOL.md`` Amendment 2):

* **R-CB** the statistic is the *return profit factor*: the sum of a run's positive trade returns over the
  absolute sum of its negative ones, a return being the net realised result over the entry quote total
  (:func:`~trading_bot.backtesting.metrics.trade_return_pct`, the basis of R-AK). The profit factor in USDT
  is carried beside it and never selects.
* **R-CC** a run whose per-bar maximum drawdown exceeds ``ruin_max_drawdown`` (0.95) is *ruined* and
  ineligible. **R-CD** a point needs at least ``min_in_sample_trades`` (250) trades. A run with no losing
  trade has no statistic and is ineligible too (the quotient is undefined; ranking it first would be an
  assumption, and at 250 trades it is not expected to occur).
* **R-CE** the runs read are those at the gate arm (1.20%) over exactly the in-sample window.
* **R-CF** the walk-forward is a REPORT: four anchored folds, training on ``[2017-08-17, Y)`` and testing on
  calendar year ``Y``. It removes no candidate, adds none and ranks nothing.
* **R-CM** (amendment 3) variants the owner ruled ineligible, read from the declaration's
  ``ineligible_variants``, are never a candidate and never a walk-forward fold's pick. They are still run, reconciled
  and counted: the denominator is unchanged.
* **R-CG** all 216 variants are run. A selection over an incomplete sweep is REFUSED, not computed over what
  is there: a variant tried and not recorded is what makes a later pass meaningless.

**The tie-break.** A tie "to six decimal places" is equality after rounding to six places (half-even, the
``Decimal`` default), and the point that comes first in ``protocol.variants()`` order wins it. Two statistics
that differ by less than a unit in the sixth place but round apart are NOT tied; that is the literal
reading of the protocol and it is pinned by a test.

**The ledger.** :func:`reconcile` turns what a sweep left in a backtests directory into one run per declared
variant, and says what is missing, what was run twice and what is not a declared variant. Two runs of one
variant must agree on the trade-log digest (the engine is deterministic); if they do not, that is a conflict
and the selection refuses.

**What is read from where.** Run records go through the evidence door (R-AR); nothing here opens a record
another way. The rules come from the ``selection`` block of the protocol's declaration, which
:func:`parse_rules` validates strictly, and the walk-forward folds are refused if any fold would touch the
out-of-sample window.

Pure but for :func:`read_run`, which reads one run directory.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import ROUND_HALF_EVEN, Decimal, InvalidOperation
from enum import Enum
from pathlib import Path
from typing import Any, Final

from trading_bot.backtesting.candidate import canonical_number
from trading_bot.backtesting.evidence import (
    RUN_RECORD_NAME,
    EvidenceRefusedError,
    load_eligible_record,
)
from trading_bot.backtesting.metrics import TradeFacts, load_trades_csv, trade_return_pct
from trading_bot.backtesting.protocol import Protocol, Variant, declaration, parse_protocol
from trading_bot.core.exceptions import TradingBotError

__all__ = [
    "MIN_RECORD_SCHEMA",
    "SELECTION_SCHEMA",
    "Assessment",
    "Cell",
    "CellResult",
    "FoldResult",
    "Ineligible",
    "Ledger",
    "PointRun",
    "Selection",
    "SelectionRefusedError",
    "SelectionRules",
    "SelectionRulesError",
    "SkipReason",
    "SkippedRun",
    "assess",
    "candidate_entry",
    "cell_of",
    "choose",
    "daily_close_drawdown",
    "entry_id",
    "parse_rules",
    "read_run",
    "reconcile",
    "render_report",
    "return_profit_factor",
    "select",
    "selection_bytes",
    "selection_document",
    "selection_lines",
    "selection_records",
    "variant_key",
    "walk_forward",
]

#: The run-record schema the selection accepts: the first one that carries the guard's decision.
MIN_RECORD_SCHEMA: Final = 6
#: The schema of the selection file this module writes: 2 is JSON Lines, one record a line (R-CU); 1 was one
#: indented JSON document, whose 5,549 lines could not be committed within the 1,500-line ceiling.
SELECTION_SCHEMA: Final = 2

_UTC: Final = timezone.utc
_STATISTIC: Final = "return_profit_factor"
_SELECTION_KEYS: Final = frozenset(
    {"statistic", "arm", "ruin_max_drawdown", "tie_places", "walk_forward", "ineligible_variants"}
)
_INELIGIBLE_KEYS: Final = frozenset({"family", "timeframe", "filtered", "params", "ruling"})
_WALK_KEYS: Final = frozenset({"train_start", "test_years"})
_TRADES_NAME: Final = "trades.csv"


class SelectionRulesError(TradingBotError):
    """The ``selection`` block of the protocol's declaration is missing, mistyped or incoherent."""


class SelectionRefusedError(TradingBotError):
    """The sweep is not a complete, consistent set of runs, so no selection is computed."""


# --------------------------------------------------------------------------
# The rules
# --------------------------------------------------------------------------
@dataclass(frozen=True)
class SelectionRules:
    """What PROTOCOL.md section 6 ruled, as numbers."""

    statistic: str
    arm: str
    ruin_max_drawdown: Decimal
    min_trades: int
    tie_places: int
    train_start: date
    test_years: tuple[int, ...]
    history_start: date
    boundary: date
    #: Variants the OWNER RULED ineligible for selection (R-CM), by :func:`variant_key`. They are still run
    #: and still counted in the variant denominator; they are never a candidate and never a fold's pick.
    ineligible_variants: frozenset[VariantKey] = frozenset()


def _refuse(message: str) -> SelectionRulesError:
    return SelectionRulesError(f"the protocol's selection block {message}")


def _int(value: object, what: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise _refuse(f"has {what} that is not an integer")
    return value


def _decimal(value: object, what: str) -> Decimal:
    if not isinstance(value, str):
        raise _refuse(f"has {what} that is not a number written as text")
    try:
        number = Decimal(value)
    except InvalidOperation:
        raise _refuse(f"has {what} {value!r}, which is not a number") from None
    if not number.is_finite():
        raise _refuse(f"has {what} that is not finite")
    return number


def _date(value: object, what: str) -> date:
    if not isinstance(value, str):
        raise _refuse(f"has {what} that is not an ISO date")
    try:
        return date.fromisoformat(value)
    except ValueError:
        raise _refuse(f"has {what} {value!r}, which is not an ISO date") from None


def parse_rules(text: str) -> SelectionRules:
    """The rules of ``PROTOCOL.md``'s declaration, validated against the rest of it.

    :raises SelectionRulesError: the block is absent, has a missing or unknown key, names a statistic
        other than ``return_profit_factor``, an arm that is not the gate arm, a ruin level outside
        (0, 1), tie places outside 1 to 12, a training start that is not the history's start, or test
        years that are not strictly increasing, that leave no training window, or whose calendar year
        ends after the boundary (a fold may not touch the out-of-sample window).
    :raises ProtocolError: the declaration itself is refused by :func:`parse_protocol`.
    """
    protocol = parse_protocol(text)
    top = declaration(text)
    block = top.get("selection")
    if not isinstance(block, Mapping):
        raise _refuse("is absent")
    keys = set(block)
    if keys != _SELECTION_KEYS:
        raise _refuse(
            f"has keys {sorted(keys)}, and the keys are exactly {sorted(_SELECTION_KEYS)}"
        )
    if block["statistic"] != _STATISTIC:
        raise _refuse(
            f"names the statistic {block['statistic']!r}, and only {_STATISTIC!r} is built"
        )
    arm = canonical_number(_decimal(block["arm"], "an arm"))
    if arm != protocol.gate_arm:
        raise _refuse(f"selects on arm {arm}, and the gate arm is {protocol.gate_arm}")
    ruin = _decimal(block["ruin_max_drawdown"], "ruin_max_drawdown")
    if not Decimal(0) < ruin < Decimal(1):
        raise _refuse(f"has ruin_max_drawdown {ruin}, outside (0, 1)")
    places = _int(block["tie_places"], "tie_places")
    if not 1 <= places <= 12:
        raise _refuse(f"has tie_places {places}, outside 1 to 12")
    walk = block["walk_forward"]
    if not isinstance(walk, Mapping) or set(walk) != _WALK_KEYS:
        raise _refuse(f"has a walk_forward that is not exactly {sorted(_WALK_KEYS)}")
    train_start = _date(walk["train_start"], "train_start")
    if train_start != protocol.history_start:
        raise _refuse(f"trains from {train_start}, and the history starts {protocol.history_start}")
    raw_years = walk["test_years"]
    if not isinstance(raw_years, list) or not raw_years:
        raise _refuse("has no test_years")
    years = tuple(_int(y, "a test year") for y in raw_years)
    if list(years) != sorted(set(years)):
        raise _refuse("has test_years that are not strictly increasing")
    for year in years:
        if date(year, 1, 1) <= train_start:
            raise _refuse(f"has test year {year}, which leaves no training window")
        if date(year + 1, 1, 1) > protocol.boundary:
            raise _refuse(
                f"has test year {year}, which ends after the boundary {protocol.boundary}"
            )
    return SelectionRules(
        statistic=_STATISTIC,
        arm=arm,
        ruin_max_drawdown=ruin,
        min_trades=protocol.min_in_sample_trades,
        tie_places=places,
        train_start=train_start,
        test_years=years,
        history_start=protocol.history_start,
        boundary=protocol.boundary,
        ineligible_variants=_ineligible_variants(block["ineligible_variants"], protocol),
    )


def _ineligible_variants(raw: object, protocol: Protocol) -> frozenset[VariantKey]:
    """The variants the owner ruled ineligible (R-CM), each checked to be a declared point of the grids."""
    if not isinstance(raw, list):
        raise _refuse("has ineligible_variants that is not a list")
    declared = {variant_key(v) for v in protocol.variants()}
    found: set[VariantKey] = set()
    for item in raw:
        if not isinstance(item, Mapping) or set(item) != _INELIGIBLE_KEYS:
            raise _refuse(
                f"has an ineligible variant that is not exactly {sorted(_INELIGIBLE_KEYS)}"
            )
        params, ruling = item["params"], item["ruling"]
        if (
            not isinstance(item["family"], str)
            or not isinstance(item["timeframe"], str)
            or not isinstance(item["filtered"], bool)
            or not isinstance(params, Mapping)
            or not all(isinstance(k, str) and isinstance(v, str) for k, v in params.items())
            or not isinstance(ruling, str)
            or not ruling
        ):
            raise _refuse("has an ineligible variant with a mistyped field")
        key = variant_key(
            Variant(item["family"], item["timeframe"], item["filtered"], dict(params))
        )
        if key not in declared:
            raise _refuse(f"rules ineligible a variant that is not a declared point: {key}")
        if key in found:
            raise _refuse(f"rules the variant {key} ineligible twice")
        found.add(key)
    return frozenset(found)


# --------------------------------------------------------------------------
# Variants and cells
# --------------------------------------------------------------------------
VariantKey = tuple[str, str, bool, tuple[tuple[str, str], ...]]


def variant_key(variant: Variant) -> VariantKey:
    """A hashable identity for a variant (its ``params`` mapping is not hashable)."""
    return (
        variant.family,
        variant.timeframe,
        variant.filtered,
        tuple(sorted(variant.params.items())),
    )


@dataclass(frozen=True)
class Cell:
    """A family, a timeframe and a filter setting: twelve of them hold the 216 variants."""

    family: str
    timeframe: str
    filtered: bool

    @property
    def label(self) -> str:
        return f"{self.family} {self.timeframe} filter {'on' if self.filtered else 'off'}"


def cell_of(variant: Variant) -> Cell:
    return Cell(variant.family, variant.timeframe, variant.filtered)


def entry_id(cell: Cell) -> str:
    """The id of a candidate's entry file: ``s6-<family>-<timeframe>-<on|off>``."""
    return f"s6-{cell.family}-{cell.timeframe}-{'on' if cell.filtered else 'off'}"


def _variant_json(variant: Variant) -> dict[str, Any]:
    return {
        "family": variant.family,
        "timeframe": variant.timeframe,
        "filtered": variant.filtered,
        "params": dict(sorted(variant.params.items())),
    }


# --------------------------------------------------------------------------
# One run, as the selection sees it
# --------------------------------------------------------------------------
@dataclass(frozen=True)
class PointRun:
    """One variant's in-sample run at the gate arm, read through the evidence door."""

    variant: Variant
    run: str
    record_sha256: str
    candidate_digest: str
    trade_log_sha256: str
    trades: tuple[TradeFacts, ...]
    #: The per-bar maximum drawdown the record states (R-AJ), as a fraction of the running peak.
    max_drawdown: Decimal
    usdt_profit_factor: Decimal | None
    initial_balance: Decimal
    daily_closes: tuple[tuple[date, Decimal], ...]


class SkipReason(str, Enum):
    """Why a run directory is not a point run. Every skipped directory is REPORTED, never dropped."""

    NOT_EVIDENCE = "not_evidence"
    NO_PROTOCOL_BLOCK = "no_protocol_block"
    NOT_IN_SAMPLE = "not_in_sample"
    OTHER_WINDOW = "other_window"
    OTHER_ARM = "other_arm"
    OFF_GRID = "off_grid"
    UNREADABLE = "unreadable"
    NOT_SEALED = "not_sealed"
    OTHER_PROTOCOL = "other_protocol"


@dataclass(frozen=True)
class SkippedRun:
    run: str
    reason: SkipReason
    detail: str


def _mapping(record: Mapping[str, object], key: str) -> Mapping[str, Any] | None:
    value = record.get(key)
    return value if isinstance(value, Mapping) else None


def _variant_of(block: Mapping[str, Any]) -> Variant | None:
    raw = block.get("variant")
    if not isinstance(raw, Mapping):
        return None
    params = raw.get("params")
    family, timeframe, filtered = raw.get("family"), raw.get("timeframe"), raw.get("filtered")
    if (
        not isinstance(family, str)
        or not isinstance(timeframe, str)
        or not isinstance(filtered, bool)
        or not isinstance(params, Mapping)
        or not all(isinstance(k, str) and isinstance(v, str) for k, v in params.items())
    ):
        return None
    return Variant(family, timeframe, filtered, dict(params))


def read_run(directory: Path, protocol: Protocol, rules: SelectionRules) -> PointRun | SkippedRun:
    """Read one run directory through the evidence door, or say why it is not a point run.

    A directory is a point run only if its record is evidence-eligible at schema
    :data:`MIN_RECORD_SCHEMA` or later, carries the guard's decision with a declared variant, was made in
    sample over exactly ``[history start, boundary)`` at the selection arm, has no problems, and holds
    exactly the trades it counts.

    **A directory still named ``<stamp>-running`` is never a point run, even with a record inside it.**
    The ``backtest`` command writes the record into ``<stamp>-running`` and only then renames the
    directory to ``<stamp>-<trade log digest>``; a process that stopped between the two (a power cut)
    leaves a complete-looking record in a directory that was never sealed. It is listed as
    ``NOT_SEALED`` and the variant is run again.

    **A run made under another protocol digest is never a point run** (``OTHER_PROTOCOL``): PROTOCOL.md
    section 10 says a run made before an amendment is not re-read under it, and the S7 gate refuses it
    the same way. The consequence is operational: ``PROTOCOL.md`` must not change, by one byte, between
    the sweep and the selection.
    """
    name = directory.name
    if name.endswith("-running"):
        return SkippedRun(
            name,
            SkipReason.NOT_SEALED,
            "the run directory was never renamed to its final name; the process stopped before sealing it",
        )
    path = directory / RUN_RECORD_NAME
    try:
        record = load_eligible_record(path, min_schema=MIN_RECORD_SCHEMA)
    except EvidenceRefusedError as exc:
        return SkippedRun(name, SkipReason.NOT_EVIDENCE, str(exc))
    block = _mapping(record, "protocol")
    if block is None:
        return SkippedRun(
            name, SkipReason.NO_PROTOCOL_BLOCK, "the record carries no protocol block"
        )
    if block.get("window_class") != "in_sample":
        return SkippedRun(
            name, SkipReason.NOT_IN_SAMPLE, f"window_class {block.get('window_class')!r}"
        )
    if block.get("protocol_sha256") != protocol.sha256:
        return SkippedRun(
            name,
            SkipReason.OTHER_PROTOCOL,
            f"made under protocol {block.get('protocol_sha256')!r}, and the protocol now is "
            f"{protocol.sha256!r}; a run made before an amendment is not re-read under it",
        )
    window = _mapping(record, "window") or {}
    wanted = (rules.history_start.isoformat(), rules.boundary.isoformat())
    got = (window.get("start_date"), window.get("end_date"))
    if got != wanted:
        return SkippedRun(
            name,
            SkipReason.OTHER_WINDOW,
            f"window {got[0]} to {got[1]}, not {wanted[0]} to {wanted[1]}",
        )
    effective = _mapping(record, "effective") or {}
    costs = _mapping(effective, "costs") or {}
    try:
        arm = canonical_number(Decimal(str(costs.get("stop_slippage_percent"))))
    except InvalidOperation:
        return SkippedRun(name, SkipReason.UNREADABLE, "the stop-slippage arm is not a number")
    if arm != rules.arm:
        return SkippedRun(name, SkipReason.OTHER_ARM, f"stop slippage {arm}, not {rules.arm}")
    variant = _variant_of(block)
    if variant is None:
        return SkippedRun(name, SkipReason.OFF_GRID, "the guard named no declared variant")
    if record.get("problems"):
        return SkippedRun(name, SkipReason.UNREADABLE, f"problems {record.get('problems')!r}")
    try:
        trades = load_trades_csv(directory / _TRADES_NAME)
        results = _mapping(record, "results") or {}
        metrics = _mapping(record, "metrics") or {}
        equity = _mapping(record, "equity") or {}
        counted = results.get("trades")
        if counted != len(trades):
            return SkippedRun(
                name,
                SkipReason.UNREADABLE,
                f"trades.csv holds {len(trades)} and the record says {counted!r}",
            )
        usdt = (_mapping(metrics, "overall") or {}).get("profit_factor_net")
        closes_raw = equity.get("daily_closes")
        if not isinstance(closes_raw, Mapping):
            return SkippedRun(name, SkipReason.UNREADABLE, "the equity block has no daily_closes")
        point = PointRun(
            variant=variant,
            run=name,
            record_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
            candidate_digest=str(record["candidate_digest"]),
            trade_log_sha256=str(results["trade_log_sha256"]),
            trades=trades,
            max_drawdown=Decimal(str(metrics["max_drawdown"])),
            usdt_profit_factor=None if usdt is None else Decimal(str(usdt)),
            initial_balance=Decimal(str(equity["initial"])),
            daily_closes=tuple(
                sorted(
                    (date.fromisoformat(day), Decimal(str(value)))
                    for day, value in closes_raw.items()
                )
            ),
        )
    except (OSError, KeyError, ValueError, InvalidOperation) as exc:
        return SkippedRun(name, SkipReason.UNREADABLE, f"{type(exc).__name__}: {exc}")
    if any(t.entry_time.tzinfo is None for t in trades):
        return SkippedRun(name, SkipReason.UNREADABLE, "a trade's entry time carries no time zone")
    return point


# --------------------------------------------------------------------------
# The ledger: what the sweep left behind
# --------------------------------------------------------------------------
@dataclass(frozen=True)
class Ledger:
    """One run per declared variant, and everything that is not."""

    points: Mapping[VariantKey, PointRun]
    missing: tuple[Variant, ...]
    duplicates: tuple[tuple[Variant, tuple[str, ...]], ...]
    conflicts: tuple[tuple[Variant, tuple[str, ...]], ...]
    skipped: tuple[SkippedRun, ...]
    declared: int

    @property
    def complete(self) -> bool:
        return not self.missing and not self.conflicts


def reconcile(protocol: Protocol, found: Sequence[PointRun | SkippedRun]) -> Ledger:
    """Match ``found`` to the declared variants.

    Where one variant has several runs that AGREE on the trade-log digest, the first by directory name
    stands and the rest are listed as duplicates; where they DISAGREE, the variant is a conflict and the
    ledger is incomplete. A point run whose variant is not a declared one is listed as off-grid.
    """
    declared = {variant_key(v): v for v in protocol.variants()}
    by_variant: dict[VariantKey, list[PointRun]] = {}
    skipped: list[SkippedRun] = []
    for item in found:
        if isinstance(item, SkippedRun):
            skipped.append(item)
            continue
        key = variant_key(item.variant)
        if key not in declared:
            skipped.append(
                SkippedRun(item.run, SkipReason.OFF_GRID, "the variant is not a declared one")
            )
            continue
        by_variant.setdefault(key, []).append(item)
    points: dict[VariantKey, PointRun] = {}
    duplicates: list[tuple[Variant, tuple[str, ...]]] = []
    conflicts: list[tuple[Variant, tuple[str, ...]]] = []
    for key, runs in by_variant.items():
        runs.sort(key=lambda p: p.run)
        points[key] = runs[0]
        if len(runs) > 1:
            names = tuple(p.run for p in runs)
            if len({p.trade_log_sha256 for p in runs}) == 1:
                duplicates.append((declared[key], names))
            else:
                conflicts.append((declared[key], names))
    missing = tuple(v for key, v in declared.items() if key not in points)
    skipped.sort(key=lambda s: s.run)
    return Ledger(
        points, missing, tuple(duplicates), tuple(conflicts), tuple(skipped), len(declared)
    )


# --------------------------------------------------------------------------
# The statistic and the eligibility rules
# --------------------------------------------------------------------------
def return_profit_factor(trades: Sequence[TradeFacts]) -> Decimal | None:
    """Positive returns over the absolute sum of negative returns; ``None`` if there is no losing trade.

    A trade's return is ``realised / entry_quote_total`` in percent. A zero return is neither a gain nor
    a loss. Scale cancels, so percent and fraction give the same quotient.
    """
    returns = [trade_return_pct(t.realised, t.entry_quote_total) for t in trades]
    gains = sum((r for r in returns if r > 0), Decimal(0))
    losses = -sum((r for r in returns if r < 0), Decimal(0))
    return gains / losses if losses != 0 else None


class Ineligible(str, Enum):
    RUINED = "ruined"
    TOO_FEW_TRADES = "too_few_trades"
    NO_LOSING_TRADE = "no_losing_trade"
    #: Ruled ineligible by the owner before any in-sample result existed (R-CM), whatever its figures.
    RULED_INELIGIBLE = "ruled_ineligible"


@dataclass(frozen=True)
class Assessment:
    """One point's figures and every reason it is not eligible (empty when it is)."""

    variant: Variant
    run: str
    record_sha256: str
    candidate_digest: str
    trades: int
    max_drawdown: Decimal
    statistic: Decimal | None
    usdt_profit_factor: Decimal | None
    reasons: tuple[Ineligible, ...]

    @property
    def eligible(self) -> bool:
        return not self.reasons


def assess(point: PointRun, rules: SelectionRules) -> Assessment:
    """Apply R-CC, R-CD and the definedness of R-CB to one run, recording EVERY reason it fails."""
    statistic = return_profit_factor(point.trades)
    reasons: list[Ineligible] = []
    if point.max_drawdown > rules.ruin_max_drawdown:
        reasons.append(Ineligible.RUINED)
    if len(point.trades) < rules.min_trades:
        reasons.append(Ineligible.TOO_FEW_TRADES)
    if statistic is None:
        reasons.append(Ineligible.NO_LOSING_TRADE)
    if variant_key(point.variant) in rules.ineligible_variants:
        reasons.append(Ineligible.RULED_INELIGIBLE)
    return Assessment(
        variant=point.variant,
        run=point.run,
        record_sha256=point.record_sha256,
        candidate_digest=point.candidate_digest,
        trades=len(point.trades),
        max_drawdown=point.max_drawdown,
        statistic=statistic,
        usdt_profit_factor=point.usdt_profit_factor,
        reasons=tuple(reasons),
    )


def _rounded(value: Decimal, places: int) -> Decimal:
    return value.quantize(Decimal(1).scaleb(-places), rounding=ROUND_HALF_EVEN)


def choose(assessments: Sequence[Assessment], places: int) -> Assessment | None:
    """The eligible point with the highest statistic; ``assessments`` is in the declared order.

    Statistics are compared after rounding to ``places`` decimal places, and a strict ``>`` keeps the
    earlier point on a tie, so the first in the declared order wins it.
    """
    best: Assessment | None = None
    best_value: Decimal | None = None
    for item in assessments:
        if not item.eligible or item.statistic is None:
            continue
        value = _rounded(item.statistic, places)
        if best_value is None or value > best_value:
            best, best_value = item, value
    return best


# --------------------------------------------------------------------------
# The walk-forward report (R-CF)
# --------------------------------------------------------------------------
def daily_close_drawdown(
    initial: Decimal, closes: Sequence[tuple[date, Decimal]], before: date
) -> Decimal:
    """The largest peak-to-trough fall of the daily-close equity before ``before``, as a fraction of its peak.

    The peak starts at ``initial``. This is NOT the per-bar figure of R-AJ: it samples once a day, so it
    can only under-detect that figure, and the walk-forward report says so.
    """
    peak = initial
    worst = Decimal(0)
    for day, close in closes:
        if day >= before:
            break
        peak = max(peak, close)
        worst = max(worst, (peak - close) / peak)
    return worst


@dataclass(frozen=True)
class FoldResult:
    """One fold of one cell."""

    year: int
    eligible_points: int
    picked: Variant | None
    picked_run: str | None
    training_statistic: Decimal | None
    forward_trades: int
    forward_statistic: Decimal | None
    is_candidate: bool


def _at(year: int) -> datetime:
    return datetime(year, 1, 1, tzinfo=_UTC)


def walk_forward(
    points: Sequence[PointRun], rules: SelectionRules, candidate: Variant | None
) -> tuple[FoldResult, ...]:
    """The report for one cell: ``points`` are its runs in the declared order.

    Per fold the rule of R-CB to R-CD picks from the TRAINING trades alone (entry bar opening in
    ``[train_start, Y-01-01)``), with the unscaled trade minimum and the daily-close drawdown standing
    for the per-bar ruin test; the pick's forward figure is its return profit factor over the trades
    whose entry opens in calendar year ``Y``. One continuous run is split by entry time, so account
    state carries across the split (an approximation the report states).
    """
    start = datetime(
        rules.train_start.year, rules.train_start.month, rules.train_start.day, tzinfo=_UTC
    )
    folds: list[FoldResult] = []
    for year in rules.test_years:
        cutoff, end = _at(year), _at(year + 1)
        graded: list[tuple[PointRun, Decimal]] = []
        for point in points:
            if variant_key(point.variant) in rules.ineligible_variants:
                continue
            training = [t for t in point.trades if start <= t.entry_time < cutoff]
            statistic = return_profit_factor(training)
            ruined = (
                daily_close_drawdown(point.initial_balance, point.daily_closes, cutoff.date())
                > rules.ruin_max_drawdown
            )
            if ruined or len(training) < rules.min_trades or statistic is None:
                continue
            graded.append((point, statistic))
        best: tuple[PointRun, Decimal] | None = None
        for point, statistic in graded:
            if best is None or _rounded(statistic, rules.tie_places) > _rounded(
                best[1], rules.tie_places
            ):
                best = (point, statistic)
        if best is None:
            folds.append(FoldResult(year, 0, None, None, None, 0, None, False))
            continue
        picked, training_statistic = best
        forward = [t for t in picked.trades if cutoff <= t.entry_time < end]
        folds.append(
            FoldResult(
                year=year,
                eligible_points=len(graded),
                picked=picked.variant,
                picked_run=picked.run,
                training_statistic=training_statistic,
                forward_trades=len(forward),
                forward_statistic=return_profit_factor(forward),
                is_candidate=candidate is not None
                and variant_key(picked.variant) == variant_key(candidate),
            )
        )
    return tuple(folds)


# --------------------------------------------------------------------------
# The selection
# --------------------------------------------------------------------------
@dataclass(frozen=True)
class CellResult:
    cell: Cell
    assessments: tuple[Assessment, ...]
    candidate: Assessment | None
    folds: tuple[FoldResult, ...]

    @property
    def eligible_count(self) -> int:
        return sum(1 for a in self.assessments if a.eligible)

    @property
    def folds_above_one(self) -> int:
        return sum(
            1 for f in self.folds if f.forward_statistic is not None and f.forward_statistic > 1
        )


@dataclass(frozen=True)
class Selection:
    protocol_sha256: str
    rules: SelectionRules
    cells: tuple[CellResult, ...]
    ledger: Ledger

    @property
    def candidates(self) -> tuple[CellResult, ...]:
        return tuple(c for c in self.cells if c.candidate is not None)


def select(protocol: Protocol, rules: SelectionRules, ledger: Ledger) -> Selection:
    """One candidate per cell that has an eligible point; the walk-forward report beside each.

    :raises SelectionRefusedError: a declared variant has no run, or two runs of one variant disagree.
    """
    if ledger.missing:
        raise SelectionRefusedError(
            f"{len(ledger.missing)} of {ledger.declared} declared variants have no run; the first is "
            f"{_describe(ledger.missing[0])}. A selection over an incomplete sweep is not computed."
        )
    if ledger.conflicts:
        variant, names = ledger.conflicts[0]
        raise SelectionRefusedError(
            f"{len(ledger.conflicts)} variants have runs that disagree on the trade log; the first is "
            f"{_describe(variant)} ({', '.join(names)})."
        )
    grouped: dict[Cell, list[PointRun]] = {}
    for variant in protocol.variants():
        grouped.setdefault(cell_of(variant), []).append(ledger.points[variant_key(variant)])
    cells: list[CellResult] = []
    for cell, points in grouped.items():
        assessments = tuple(assess(p, rules) for p in points)
        candidate = choose(assessments, rules.tie_places)
        folds = walk_forward(points, rules, None if candidate is None else candidate.variant)
        cells.append(CellResult(cell, assessments, candidate, folds))
    return Selection(protocol.sha256, rules, tuple(cells), ledger)


def _describe(variant: Variant) -> str:
    params = ", ".join(f"{k}={v}" for k, v in sorted(variant.params.items()))
    return f"{cell_of(variant).label} ({params})"


# --------------------------------------------------------------------------
# Output
# --------------------------------------------------------------------------
def _text(value: Decimal | None) -> str | None:
    return None if value is None else str(value)


def selection_document(selection: Selection) -> dict[str, Any]:
    """The selection file's content: deterministic, exact, and complete enough to audit every cell."""
    rules = selection.rules
    ledger = selection.ledger
    cells: list[dict[str, Any]] = []
    for result in selection.cells:
        candidate = result.candidate
        cells.append(
            {
                "cell": {
                    "family": result.cell.family,
                    "timeframe": result.cell.timeframe,
                    "filtered": result.cell.filtered,
                },
                "entry_id": entry_id(result.cell),
                "eligible_points": result.eligible_count,
                "points": len(result.assessments),
                "candidate": None
                if candidate is None
                else {
                    "variant": _variant_json(candidate.variant),
                    "run": candidate.run,
                    "run_json_sha256": candidate.record_sha256,
                    "candidate_digest": candidate.candidate_digest,
                    "return_profit_factor": _text(candidate.statistic),
                    "usdt_profit_factor": _text(candidate.usdt_profit_factor),
                    "trades": candidate.trades,
                    "max_drawdown": str(candidate.max_drawdown),
                },
                "assessments": [
                    {
                        "variant": _variant_json(a.variant),
                        "run": a.run,
                        "run_json_sha256": a.record_sha256,
                        "trades": a.trades,
                        "max_drawdown": str(a.max_drawdown),
                        "return_profit_factor": _text(a.statistic),
                        "usdt_profit_factor": _text(a.usdt_profit_factor),
                        "ineligible": [r.value for r in a.reasons],
                    }
                    for a in result.assessments
                ],
                "walk_forward": [
                    {
                        "year": f.year,
                        "eligible_points": f.eligible_points,
                        "picked": None if f.picked is None else _variant_json(f.picked),
                        "picked_run": f.picked_run,
                        "training_return_profit_factor": _text(f.training_statistic),
                        "forward_trades": f.forward_trades,
                        "forward_return_profit_factor": _text(f.forward_statistic),
                        "is_candidate": f.is_candidate,
                    }
                    for f in result.folds
                ],
                "folds_above_one": result.folds_above_one,
            }
        )
    return {
        "selection_schema": SELECTION_SCHEMA,
        "protocol_sha256": selection.protocol_sha256,
        "rules": {
            "statistic": rules.statistic,
            "arm": rules.arm,
            "ruin_max_drawdown": str(rules.ruin_max_drawdown),
            "min_trades": rules.min_trades,
            "tie_places": rules.tie_places,
            "train_start": rules.train_start.isoformat(),
            "test_years": list(rules.test_years),
            "window": [rules.history_start.isoformat(), rules.boundary.isoformat()],
            "ineligible_variants": [
                {
                    "family": family,
                    "timeframe": timeframe,
                    "filtered": filtered,
                    "params": dict(params),
                }
                for family, timeframe, filtered, params in sorted(rules.ineligible_variants)
            ],
        },
        "variants_declared": ledger.declared,
        "variants_with_a_run": len(ledger.points),
        "cells_with_a_candidate": len(selection.candidates),
        "cells": cells,
        "duplicates": [
            {"variant": _variant_json(v), "runs": list(names)} for v, names in ledger.duplicates
        ],
        "skipped": [
            {"run": s.run, "reason": s.reason.value, "detail": s.detail} for s in ledger.skipped
        ],
    }


_NOT_RECORDS: Final = frozenset({"cells", "duplicates", "skipped"})


def selection_lines(document: Mapping[str, Any]) -> list[dict[str, Any]]:
    """The document as the records of the file, in file order (R-CU).

    A ``header`` record (everything in the document but the three lists); then, for each cell, one ``variant``
    record per point (its run, the record's SHA-256 and its statistics, tagged with the cell's ``entry_id``) and
    one ``cell`` record (the pick, the counts and the walk-forward); then one ``duplicate`` record per variant
    run twice and one ``skipped`` record per directory not read. Nothing is dropped and nothing is added but the
    ``record`` kind and the ``entry_id`` on a ``variant``: the picks and every digest are the document's.
    """
    records: list[dict[str, Any]] = [
        {"record": "header", **{k: v for k, v in document.items() if k not in _NOT_RECORDS}}
    ]
    for cell in document["cells"]:
        for point in cell["assessments"]:
            records.append({"record": "variant", "entry_id": cell["entry_id"], **point})
        pick = {k: v for k, v in cell.items() if k != "assessments"}
        records.append({"record": "cell", **pick})
    records.extend({"record": "duplicate", **item} for item in document["duplicates"])
    records.extend({"record": "skipped", **item} for item in document["skipped"])
    return records


def selection_bytes(document: Mapping[str, Any]) -> bytes:
    """The file's exact bytes: JSON Lines, one record a line, sorted keys, ASCII, LF after every line (R-CU)."""
    return "".join(
        json.dumps(record, sort_keys=True, ensure_ascii=True) + "\n"
        for record in selection_lines(document)
    ).encode("ascii")


def selection_records(data: bytes) -> list[dict[str, Any]]:
    """The records of a selection file, read back.

    :raises ValueError: the bytes are not ASCII, do not end with a line feed, or hold a line that is not a JSON
        object carrying a ``record`` kind.
    """
    text = data.decode("ascii")
    if not text.endswith("\n"):
        raise ValueError("a selection file ends with a line feed")
    records: list[dict[str, Any]] = []
    for number, line in enumerate(text[:-1].split("\n"), start=1):
        record = json.loads(line)
        if not isinstance(record, dict) or not isinstance(record.get("record"), str):
            raise ValueError(f"line {number} is not a record")
        records.append(record)
    return records


def candidate_entry(
    result: CellResult, *, selection_sha256: str, arms: Sequence[str]
) -> dict[str, Any]:
    """The pending entry for a cell's candidate (PROTOCOL.md section 6 step 6).

    :raises SelectionRefusedError: the cell has no candidate.
    """
    candidate = result.candidate
    if candidate is None:
        raise SelectionRefusedError(f"{result.cell.label} has no candidate, so it has no entry")
    return {
        "entry_schema": 1,
        "id": entry_id(result.cell),
        "kind": "candidate",
        "ref": result.cell.family,
        "candidate_digest": candidate.candidate_digest,
        "arms": list(arms),
        "status": "pending",
        "oos": None,
        "selection": {
            "variant": _variant_json(candidate.variant),
            "in_sample_run": candidate.run,
            "in_sample_run_json_sha256": candidate.record_sha256,
            "return_profit_factor": _text(candidate.statistic),
            "usdt_profit_factor": _text(candidate.usdt_profit_factor),
            "trades": candidate.trades,
            "selection_file_sha256": selection_sha256,
        },
    }


def render_report(selection: Selection) -> str:
    """A text report: the ledger, each cell's table and candidate, and the walk-forward report."""
    rules = selection.rules
    ledger = selection.ledger
    lines = [
        "S6 SELECTION (PROTOCOL.md section 6; no out-of-sample record is read)",
        f"  protocol sha256 {selection.protocol_sha256}",
        f"  statistic {rules.statistic}; arm {rules.arm}; ruined above per-bar drawdown {rules.ruin_max_drawdown};"
        f" at least {rules.min_trades} trades; ties to {rules.tie_places} places",
        f"  variants declared {ledger.declared}; with a run {len(ledger.points)}; duplicated "
        f"{len(ledger.duplicates)}; skipped directories {len(ledger.skipped)}",
        f"  cells with a candidate {len(selection.candidates)} of {len(selection.cells)}",
        f"  ruled ineligible by the owner (R-CM), still run and counted: {len(rules.ineligible_variants)}",
    ]
    for skipped in ledger.skipped:
        lines.append(f"  SKIPPED {skipped.run}: {skipped.reason.value}: {skipped.detail}")
    for result in selection.cells:
        lines.append("")
        lines.append(
            f"CELL {result.cell.label}: {result.eligible_count} of {len(result.assessments)} points eligible"
        )
        candidate = result.candidate
        if candidate is None:
            lines.append("  no candidate")
        else:
            lines.append(
                f"  CANDIDATE {_describe(candidate.variant)}: return PF {_fmt(candidate.statistic)}, "
                f"USDT PF {_fmt(candidate.usdt_profit_factor)}, {candidate.trades} trades, "
                f"max drawdown {_fmt(candidate.max_drawdown)}, run {candidate.run}"
            )
        lines.append(
            "  walk-forward (a report, not a gate; one run split by entry time, daily-close ruin test):"
        )
        for fold in result.folds:
            if fold.picked is None:
                lines.append(f"    {fold.year}: no eligible point in training")
                continue
            lines.append(
                f"    {fold.year}: {fold.eligible_points} eligible; picked {_describe(fold.picked)}"
                f" (training PF {_fmt(fold.training_statistic)}); forward {fold.forward_trades} trades,"
                f" PF {_fmt(fold.forward_statistic)}{'; IS THE CANDIDATE' if fold.is_candidate else ''}"
            )
        lines.append(
            f"  folds with a forward return PF above 1: {result.folds_above_one} of {len(result.folds)}"
        )
    return "\n".join(lines) + "\n"


def _fmt(value: Decimal | None) -> str:
    return "n/a" if value is None else f"{value:.6f}"
