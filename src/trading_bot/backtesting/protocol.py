"""The S6 research protocol, and the guard that makes "read once per candidate" mechanical (R-BT, S6).

``docs/research/PROTOCOL.md`` fixes, before any S5 run exists, the boundary between the in-sample and the
out-of-sample window (R-BP: ``2024-01-01``), every candidate family and its full parameter grid, the
three stop-slippage arms (R-B2) and the S5 baseline. Its machine-readable half is one JSON declaration
between two markers; :func:`parse_protocol` reads it. A candidate's *entry* is a JSON file under
``docs/research/entries/``, committed BEFORE the candidate's out-of-sample read and committed again,
with its ``oos`` block, after it (PROTOCOL.md section 8). :func:`check_run` is the guard.

**What it refuses, by reason (a :class:`Refusal`).** A window that touches the out-of-sample window
(its ``end_date`` is after the boundary) is refused unless ALL of these hold, checked in this order:

1. ``PROVENANCE``: the run's provenance verdict is ``accepted`` (an out-of-sample read comes only from a
   deployment clone of a pushed commit);
2. ``NO_ENTRY``: an entry carries the run's ``candidate_digest``
   (:mod:`trading_bot.backtesting.candidate`);
3. for a ``candidate`` entry, ``NOT_A_GRID_POINT``: the candidate is a point of a declared family's
   grid (its strategy, its parameters, both pairs on one declared timeframe, the filter parameter
   absent or exactly the declared value, and every cost the declared one); for a ``baseline`` entry,
   ``BASELINE_MISMATCH``: it is the declared baseline's strategy, parameters and pairs;
4. ``WRONG_WINDOW``: the window is exactly the declared out-of-sample window (a candidate) or the declared
   full-history window (the baseline); a window that straddles the boundary is neither;
5. ``ARMS_MISMATCH``: the entry lists exactly the protocol's arms, and ``ARM_NOT_DECLARED``: the run's
   stop-slippage arm is one of them;
6. ``ALREADY_READ``: the entry's ``status`` is ``pending`` and it carries no ``oos`` block;
7. ``LOCAL_PRIOR_READ``: this clone holds no record of this candidate at this arm that touched the
   out-of-sample window (the caller supplies the set; a run that failed leaves no record and may be
   repeated).

A window wholly in sample (``end_date`` at or before the boundary) needs no entry. **That is not a loophole in
the denominator:** a variant outside the declared grids can be run in sample, but it can never be read out of
sample, because step 3 refuses it, so the 216 variants the protocol declares are the multiple-testing
denominator whatever else was tried.

**What it cannot see**, stated so it is not mistaken for complete: a run in a tree that is not a clone of a
pushed commit (refused at step 1 for the out-of-sample window and not evidence anywhere, R-AR); a window of
dates the caller computed wrongly; and an entry whose prose lies. The guard binds an entry to the effective
settings by digest and nothing else.

Pure but for its three readers (the protocol, the entries, and :func:`local_reads` over this clone's run
records): no clock, no network, no git.
"""

from __future__ import annotations

import hashlib
import itertools
import json
import re
from collections.abc import Collection, Iterator, Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
from enum import Enum
from pathlib import Path
from typing import Any, Final

from trading_bot.backtesting.candidate import candidate_arm, candidate_digest, canonical_number
from trading_bot.backtesting.evidence import (
    EFFECTIVE_SCHEMA,
    RUN_RECORD_NAME,
    EvidenceRefusedError,
    require_evidence_eligible,
)
from trading_bot.core.exceptions import TradingBotError

__all__ = [
    "ENTRIES_DIR",
    "PROTOCOL_PATH",
    "Baseline",
    "Decision",
    "Entry",
    "Family",
    "Protocol",
    "ProtocolError",
    "ProtocolRefusalError",
    "Refusal",
    "Variant",
    "WindowClass",
    "check_run",
    "classify_window",
    "declaration",
    "grid_point",
    "load_entries",
    "load_protocol",
    "local_reads",
    "parse_entry",
    "parse_protocol",
]

#: The protocol file and the entries directory, relative to the launch directory (the repository root).
PROTOCOL_PATH: Final = Path("docs") / "research" / "PROTOCOL.md"
ENTRIES_DIR: Final = Path("docs") / "research" / "entries"

_BEGIN: Final = "<!-- protocol-json:begin -->"
_END: Final = "<!-- protocol-json:end -->"
_HEX64: Final = re.compile(r"^[0-9a-f]{64}$")
_PROTOCOL_SCHEMA: Final = 1
_ENTRY_SCHEMA: Final = 1
_FILTER_STATES: Final = (False, True)


class ProtocolError(TradingBotError):
    """The protocol declaration or an entry file is malformed; nothing out of sample may run on it."""


class Refusal(str, Enum):
    """Why the guard refused a run. The values are what the refusal message and the tests name."""

    PROVENANCE = "provenance"
    NO_ENTRY = "no_entry"
    NOT_A_GRID_POINT = "not_a_grid_point"
    BASELINE_MISMATCH = "baseline_mismatch"
    WRONG_WINDOW = "wrong_window"
    ARMS_MISMATCH = "arms_mismatch"
    ARM_NOT_DECLARED = "arm_not_declared"
    ALREADY_READ = "already_read"
    LOCAL_PRIOR_READ = "local_prior_read"


class ProtocolRefusalError(TradingBotError):
    """The guard refused a run. ``reason`` says which rule; the message says what to do."""

    def __init__(self, reason: Refusal, message: str) -> None:
        super().__init__(f"[{reason.value}] {message}")
        self.reason = reason


class WindowClass(str, Enum):
    """Where a window sits against the boundary."""

    IN_SAMPLE = "in_sample"
    OUT_OF_SAMPLE = "out_of_sample"
    STRADDLING = "straddling"


@dataclass(frozen=True)
class Family:
    """One candidate family: a strategy, its timeframes and the full grid of its parameters."""

    id: str
    strategy: str
    timeframes: tuple[str, ...]
    #: parameter name -> its allowed values, canonical (``30`` and ``30.0`` are ``"30"``), in declared order.
    grid: Mapping[str, tuple[str, ...]]


@dataclass(frozen=True)
class Baseline:
    """A declared non-candidate configuration that may read the whole history (S5, R-BT)."""

    id: str
    strategy: str
    params: Mapping[str, str]
    pairs: tuple[tuple[str, str], ...]
    window_start: date
    window_end: date


@dataclass(frozen=True)
class Variant:
    """One declared variant: a family, a timeframe, whether the filter is on, and a grid point."""

    family: str
    timeframe: str
    filtered: bool
    params: Mapping[str, str]


@dataclass(frozen=True)
class Protocol:
    """The declaration of PROTOCOL.md, validated."""

    sha256: str
    history_start: date
    history_end: date
    boundary: date
    regime_labels_sha256: str
    arms: tuple[str, ...]
    gate_arm: str
    filter_param: str
    filter_value: str
    min_in_sample_trades: int
    pairs: tuple[str, ...]
    costs: Mapping[str, str]
    exchange_info_environment: str
    families: tuple[Family, ...]
    baselines: tuple[Baseline, ...]

    def variants(self) -> Iterator[Variant]:
        """Every declared variant, family by family, in the grids' declared order."""
        for family in self.families:
            names = list(family.grid)
            for timeframe in family.timeframes:
                for filtered in _FILTER_STATES:
                    for combo in itertools.product(*(family.grid[name] for name in names)):
                        params = dict(zip(names, combo, strict=True))
                        if filtered:
                            params[self.filter_param] = self.filter_value
                        yield Variant(family.id, timeframe, filtered, params)

    def baseline(self, baseline_id: str) -> Baseline | None:
        return next((b for b in self.baselines if b.id == baseline_id), None)


@dataclass(frozen=True)
class Entry:
    """A research-log entry file: the machine-checked half of ``docs/research/LOG.md``."""

    sha256: str
    id: str
    kind: str
    ref: str
    candidate_digest: str
    arms: tuple[str, ...]
    status: str
    oos: Mapping[str, Any] | None


@dataclass(frozen=True)
class Decision:
    """What the guard allowed, in the form the run record keeps (its ``protocol`` block)."""

    protocol_sha256: str
    window_class: WindowClass
    arm: str
    kind: str | None
    entry_id: str | None
    entry_sha256: str | None
    variant: Variant | None

    def record(self) -> dict[str, object]:
        out: dict[str, object] = {
            "protocol_sha256": self.protocol_sha256,
            "window_class": self.window_class.value,
            "arm": self.arm,
            "kind": self.kind,
            "entry_id": self.entry_id,
            "entry_sha256": self.entry_sha256,
        }
        if self.variant is not None:
            out["variant"] = {
                "family": self.variant.family,
                "timeframe": self.variant.timeframe,
                "filtered": self.variant.filtered,
                "params": dict(self.variant.params),
            }
        return out


# --------------------------------------------------------------------------
# Parsing
# --------------------------------------------------------------------------
def _fail(message: str) -> ProtocolError:
    return ProtocolError(f"the research protocol declaration {message}")


def _mapping(value: object, where: str) -> Mapping[str, Any]:
    if not isinstance(value, dict):
        raise _fail(f"has {where} that is not an object")
    return value


def _text(data: Mapping[str, Any], key: str, where: str) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value:
        raise _fail(f"has no text {key!r} in {where}")
    return value


def _date(data: Mapping[str, Any], key: str, where: str) -> date:
    try:
        return date.fromisoformat(_text(data, key, where))
    except ValueError:
        raise _fail(f"has {key!r} in {where} that is not a YYYY-MM-DD date") from None


def _number_text(value: object, where: str) -> str:
    """A declared number (given as a JSON number or numeric text) as its canonical text."""
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        raise _fail(f"has {where} that is not a number")
    try:
        Decimal(str(value))
    except InvalidOperation:
        raise _fail(f"has {where} that is not a number") from None
    return canonical_number(value if not isinstance(value, str) else Decimal(value))


def _grid(raw: object, family: str) -> dict[str, tuple[str, ...]]:
    grid = _mapping(raw, f"the grid of {family!r}")
    if not grid:
        raise _fail(f"has an empty grid for {family!r}")
    out: dict[str, tuple[str, ...]] = {}
    for name, values in grid.items():
        if not isinstance(values, list) or not values:
            raise _fail(f"has no values for {name!r} in {family!r}")
        canonical = tuple(_number_text(v, f"a value of {name!r} in {family!r}") for v in values)
        if len(set(canonical)) != len(canonical):
            raise _fail(f"repeats a value of {name!r} in {family!r}")
        out[name] = canonical
    return out


def _unique(items: Sequence[str], what: str) -> tuple[str, ...]:
    if len(set(items)) != len(items):
        raise _fail(f"repeats a {what}")
    return tuple(items)


def declaration(text: str) -> Mapping[str, Any]:
    """The JSON declaration between the markers of ``PROTOCOL.md``, as a mapping of its top level.

    Public so that the S6 tooling reads the blocks this module ignores (``selection``, ``s7``) from the
    same markers rather than from a second parser.

    :raises ProtocolError: the markers or the JSON are absent or malformed, or the schema is not ours.
    """
    if text.count(_BEGIN) != 1 or text.count(_END) != 1:
        raise _fail(f"does not have exactly one {_BEGIN} ... {_END} block")
    body = text.split(_BEGIN, 1)[1].split(_END, 1)[0].strip()
    fence_open, fence_close = "```json", "```"
    if not (body.startswith(fence_open) and body.endswith(fence_close)):
        raise _fail("is not inside a ```json fence")
    try:
        data = json.loads(body[len(fence_open) : -len(fence_close)])
    except ValueError as exc:
        raise _fail(f"is not valid JSON: {exc}") from exc
    top = _mapping(data, "its top level")
    if top.get("protocol_schema") != _PROTOCOL_SCHEMA:
        raise _fail(f"is not protocol_schema {_PROTOCOL_SCHEMA}")
    return top


def parse_protocol(text: str) -> Protocol:
    """The declaration between the markers of ``PROTOCOL.md``, validated.

    :raises ProtocolError: the markers or the JSON are absent or malformed, a required key is
        missing or mistyped, the boundary is not strictly inside the history, the arms do not
        contain the gate arm, a grid repeats a value, or a family or baseline id repeats.
    """
    top = declaration(text)

    history = _mapping(top.get("history"), "history")
    start, end = _date(history, "start", "history"), _date(history, "end_exclusive", "history")
    boundary = _date(top, "boundary", "the top level")
    if not start < boundary < end:
        raise _fail("has a boundary that is not strictly inside the history")

    labels = _text(top, "regime_labels_sha256", "the top level")
    if not _HEX64.match(labels):
        raise _fail("has regime_labels_sha256 that is not 64 lowercase hex digits")

    raw_arms = top.get("arms_stop_slippage_percent")
    if not isinstance(raw_arms, list) or not raw_arms:
        raise _fail("has no arms_stop_slippage_percent")
    arms = _unique([_number_text(a, "an arm") for a in raw_arms], "arm")
    gate_arm = _number_text(top.get("gate_arm"), "gate_arm")
    if gate_arm not in arms:
        raise _fail("has a gate_arm that is not one of its arms")

    filter_block = _mapping(top.get("filter"), "filter")
    filter_param = _text(filter_block, "param", "filter")
    filter_value = _number_text(filter_block.get("value"), "the filter value")

    minimum = top.get("min_in_sample_trades")
    if isinstance(minimum, bool) or not isinstance(minimum, int) or minimum < 1:
        raise _fail("has a min_in_sample_trades that is not a positive integer")

    raw_pairs = top.get("pairs")
    if (
        not isinstance(raw_pairs, list)
        or not raw_pairs
        or not all(isinstance(p, str) for p in raw_pairs)
    ):
        raise _fail("has no pairs")
    pairs = _unique([p.upper() for p in raw_pairs], "pair")

    costs_block = _mapping(top.get("costs"), "costs")
    costs = {
        key: _number_text(costs_block.get(key), f"the cost {key!r}")
        for key in ("fee_percent", "slippage_percent", "initial_balance")
    }
    environment = _text(top, "exchange_info_environment", "the top level")

    families: list[Family] = []
    raw_families = top.get("families")
    if not isinstance(raw_families, list) or not raw_families:
        raise _fail("has no families")
    for raw in raw_families:
        block = _mapping(raw, "a family")
        family_id = _text(block, "id", "a family")
        timeframes = block.get("timeframes")
        if (
            not isinstance(timeframes, list)
            or not timeframes
            or not all(isinstance(t, str) for t in timeframes)
        ):
            raise _fail(f"has no timeframes for {family_id!r}")
        families.append(
            Family(
                id=family_id,
                strategy=_text(block, "strategy", f"family {family_id!r}"),
                timeframes=_unique(timeframes, f"timeframe of {family_id!r}"),
                grid=_grid(block.get("grid"), family_id),
            )
        )
    _unique([f.id for f in families], "family id")

    baselines: list[Baseline] = []
    for raw in top.get("baselines", []):
        block = _mapping(raw, "a baseline")
        baseline_id = _text(block, "id", "a baseline")
        window = _mapping(block.get("window"), f"the window of {baseline_id!r}")
        raw_params = _mapping(block.get("params"), f"the params of {baseline_id!r}")
        raw_baseline_pairs = block.get("pairs")
        if (
            not isinstance(raw_baseline_pairs, list)
            or not raw_baseline_pairs
            or not all(isinstance(p, list) and len(p) == 2 for p in raw_baseline_pairs)
        ):
            raise _fail(f"has no [symbol, timeframe] pairs for {baseline_id!r}")
        baselines.append(
            Baseline(
                id=baseline_id,
                strategy=_text(block, "strategy", f"baseline {baseline_id!r}"),
                params={
                    k: _number_text(v, f"a param of {baseline_id!r}") for k, v in raw_params.items()
                },
                pairs=tuple((str(p[0]).upper(), str(p[1])) for p in raw_baseline_pairs),
                window_start=_date(window, "start", f"the window of {baseline_id!r}"),
                window_end=_date(window, "end_exclusive", f"the window of {baseline_id!r}"),
            )
        )
    _unique([b.id for b in baselines], "baseline id")

    return Protocol(
        sha256=hashlib.sha256(text.encode("utf-8")).hexdigest(),
        history_start=start,
        history_end=end,
        boundary=boundary,
        regime_labels_sha256=labels,
        arms=arms,
        gate_arm=gate_arm,
        filter_param=filter_param,
        filter_value=filter_value,
        min_in_sample_trades=minimum,
        pairs=pairs,
        costs=costs,
        exchange_info_environment=environment,
        families=tuple(families),
        baselines=tuple(baselines),
    )


def parse_entry(text: str) -> Entry:
    """One entry file, validated.

    :raises ProtocolError: it is not JSON, lacks a field, has a kind other than ``candidate`` or
        ``baseline``, a status other than ``pending`` or ``read``, a digest that is not 64 hex digits,
        a ``pending`` entry with an ``oos`` block, or a ``read`` entry without one.
    """
    try:
        data = json.loads(text)
    except ValueError as exc:
        raise ProtocolError(f"a research entry is not valid JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise ProtocolError("a research entry is not a JSON object")
    if data.get("entry_schema") != _ENTRY_SCHEMA:
        raise ProtocolError(f"a research entry is not entry_schema {_ENTRY_SCHEMA}")
    fields: dict[str, str] = {}
    for key in ("id", "kind", "ref", "candidate_digest", "status"):
        value = data.get(key)
        if not isinstance(value, str) or not value:
            raise ProtocolError(f"a research entry has no text {key!r}")
        fields[key] = value
    if fields["kind"] not in ("candidate", "baseline"):
        raise ProtocolError(f"research entry {fields['id']!r} has kind {fields['kind']!r}")
    if fields["status"] not in ("pending", "read"):
        raise ProtocolError(f"research entry {fields['id']!r} has status {fields['status']!r}")
    if not _HEX64.match(fields["candidate_digest"]):
        raise ProtocolError(
            f"research entry {fields['id']!r} has a candidate_digest that is not 64 hex digits"
        )
    raw_arms = data.get("arms")
    if (
        not isinstance(raw_arms, list)
        or not raw_arms
        or not all(isinstance(a, str) for a in raw_arms)
    ):
        raise ProtocolError(f"research entry {fields['id']!r} has no arms")
    try:
        arms = tuple(canonical_number(Decimal(a)) for a in raw_arms)
    except InvalidOperation:
        raise ProtocolError(
            f"research entry {fields['id']!r} has an arm that is not a number"
        ) from None
    oos = data.get("oos")
    if oos is not None and not isinstance(oos, dict):
        raise ProtocolError(f"research entry {fields['id']!r} has an oos that is not an object")
    if (fields["status"] == "read") != (oos is not None):
        raise ProtocolError(
            f"research entry {fields['id']!r} is {fields['status']!r} and "
            f"{'has' if oos is not None else 'lacks'} an oos block"
        )
    return Entry(
        sha256=hashlib.sha256(text.encode("utf-8")).hexdigest(),
        id=fields["id"],
        kind=fields["kind"],
        ref=fields["ref"],
        candidate_digest=fields["candidate_digest"],
        arms=arms,
        status=fields["status"],
        oos=oos,
    )


def load_protocol(path: Path = PROTOCOL_PATH) -> Protocol:
    """Read and parse the protocol file.

    :raises ProtocolError: it cannot be read, or :func:`parse_protocol` refuses it.
    """
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ProtocolError(f"the research protocol {path} cannot be read: {exc}") from exc
    return parse_protocol(text)


def load_entries(directory: Path = ENTRIES_DIR) -> tuple[Entry, ...]:
    """Every ``*.json`` entry under ``directory``, sorted by name. An absent directory holds none.

    A malformed entry refuses the whole load: an entry that cannot be read must not be skipped, because
    the entry it hides might be the one that says a candidate has been read.

    :raises ProtocolError: an entry is malformed, an id repeats, or two entries name one candidate digest.
    """
    if not directory.is_dir():
        return ()
    entries: list[Entry] = []
    for path in sorted(directory.glob("*.json")):
        try:
            text = path.read_text(encoding="utf-8")
        except OSError as exc:
            raise ProtocolError(f"the research entry {path} cannot be read: {exc}") from exc
        entries.append(parse_entry(text))
    _unique_entries(entries)
    return tuple(entries)


def local_reads(protocol: Protocol, directory: Path) -> frozenset[tuple[str, str]]:
    """The ``(candidate_digest, arm)`` of every record under ``directory`` that touched the out-of-sample window.

    Reads ``<directory>/*/run.json``, the run directories of this clone; a ``-running`` or ``-failed``
    directory holds none, because the record is written last, so a run that failed leaves no read behind.
    A record whose window is wholly in sample is skipped unjudged. **A record that did touch the
    out-of-sample window must be evidence** (:func:`~trading_bot.backtesting.evidence.require_evidence_eligible`,
    schema 5 or later), and one that is not is an anomaly this guard cannot account for, so it refuses
    rather than skipping it: skipping would let a candidate be read twice behind it.

    :raises ProtocolError: a record cannot be read, names no window, or touched the out-of-sample window
        and is not evidence.
    """
    reads: set[tuple[str, str]] = set()
    if not directory.is_dir():
        return frozenset()
    for path in sorted(directory.glob(f"*/{RUN_RECORD_NAME}")):
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise ProtocolError(f"the run record {path} cannot be read: {exc}") from exc
        window = record.get("window") if isinstance(record, dict) else None
        if not isinstance(window, dict):
            raise ProtocolError(f"the run record {path} names no window")
        try:
            start = date.fromisoformat(str(window["start_date"]))
            end = date.fromisoformat(str(window["end_date"]))
        except (KeyError, ValueError) as exc:
            raise ProtocolError(f"the run record {path} names no readable window") from exc
        if classify_window(protocol, start, end) is WindowClass.IN_SAMPLE:
            continue
        try:
            require_evidence_eligible(record, source=str(path), min_schema=EFFECTIVE_SCHEMA)
        except EvidenceRefusedError as exc:
            raise ProtocolError(
                f"the run record {path} touched the out-of-sample window and is not evidence, "
                f"so the guard cannot tell what it read: {exc}"
            ) from exc
        effective = record["effective"]
        reads.add((candidate_digest(effective), candidate_arm(effective)))
    return frozenset(reads)


def _unique_entries(entries: Sequence[Entry]) -> None:
    ids = [e.id for e in entries]
    if len(set(ids)) != len(ids):
        raise ProtocolError("two research entries have one id")
    digests = [e.candidate_digest for e in entries]
    if len(set(digests)) != len(digests):
        raise ProtocolError("two research entries name one candidate digest")


# --------------------------------------------------------------------------
# The rules
# --------------------------------------------------------------------------
def classify_window(protocol: Protocol, start_date: date, end_date: date) -> WindowClass:
    """Where the half-open window ``[start_date, end_date)`` sits against the boundary.

    In sample means ``end_date`` is at or before the boundary; out of sample means ``start_date`` is at or
    after it; anything else straddles it.
    """
    if end_date <= protocol.boundary:
        return WindowClass.IN_SAMPLE
    if start_date >= protocol.boundary:
        return WindowClass.OUT_OF_SAMPLE
    return WindowClass.STRADDLING


def _pairs_of(effective: Mapping[str, object]) -> list[tuple[str, str]]:
    raw = effective.get("pairs")
    pairs: list[tuple[str, str]] = []
    if isinstance(raw, list):
        for item in raw:
            if isinstance(item, Mapping):
                pairs.append((str(item.get("symbol")), str(item.get("timeframe"))))
    return pairs


def _strategy_of(effective: Mapping[str, object]) -> tuple[str | None, dict[str, str]]:
    block = effective.get("strategy")
    if not isinstance(block, Mapping):
        return None, {}
    params = block.get("params")
    name = block.get("name")
    clean = {str(k): str(v) for k, v in params.items()} if isinstance(params, Mapping) else {}
    return (name if isinstance(name, str) else None), clean


def _costs_match(protocol: Protocol, effective: Mapping[str, object]) -> bool:
    costs = effective.get("costs")
    if not isinstance(costs, Mapping):
        return False
    return (
        all(str(costs.get(key)) == value for key, value in protocol.costs.items())
        and effective.get("exchange_info_environment") == protocol.exchange_info_environment
    )


def grid_point(protocol: Protocol, effective: Mapping[str, object]) -> Variant | None:
    """The declared variant the effective settings are, or ``None`` if they are not one.

    A variant is a family's strategy, both protocol pairs on ONE of the family's timeframes, every grid
    parameter at one of its declared values and no other parameter except the filter, which is absent or
    exactly the declared value, and every cost and the ``exchangeInfo`` environment as declared.
    """
    name, params = _strategy_of(effective)
    pairs = _pairs_of(effective)
    if name is None or not pairs or not _costs_match(protocol, effective):
        return None
    timeframes = {timeframe for _symbol, timeframe in pairs}
    if len(timeframes) != 1 or [symbol for symbol, _t in pairs] != list(protocol.pairs):
        return None
    timeframe = next(iter(timeframes))
    for family in protocol.families:
        if family.strategy != name or timeframe not in family.timeframes:
            continue
        filtered = protocol.filter_param in params
        rest = {k: v for k, v in params.items() if k != protocol.filter_param}
        if filtered and params[protocol.filter_param] != protocol.filter_value:
            continue
        if set(rest) != set(family.grid):
            continue
        if all(rest[key] in family.grid[key] for key in family.grid):
            return Variant(family.id, timeframe, filtered, params)
    return None


def _is_baseline(protocol: Protocol, baseline: Baseline, effective: Mapping[str, object]) -> bool:
    name, params = _strategy_of(effective)
    return (
        name == baseline.strategy
        and params == dict(baseline.params)
        and [(s, t) for s, t in _pairs_of(effective)] == list(baseline.pairs)
        and _costs_match(protocol, effective)
    )


def check_run(
    protocol: Protocol,
    entries: Sequence[Entry],
    *,
    effective: Mapping[str, object],
    window_start: date,
    window_end: date,
    provenance_accepted: bool,
    local_reads: Collection[tuple[str, str]],
) -> Decision:
    """Allow a run, or refuse it by one of the rules in the module docstring.

    :param effective: the run's effective-settings block (:func:`~trading_bot.backtesting.candidate.effective_settings`).
    :param window_start: the first day replayed.
    :param window_end: the day the replay stops before.
    :param provenance_accepted: whether the run's boot verdict is ``accepted``.
    :param local_reads: ``(candidate_digest, arm)`` pairs this clone already holds a completed record
        of for a window that touched the out-of-sample window.
    :raises ProtocolRefusalError: a rule refuses it; ``.reason`` says which.
    """
    arm = candidate_arm(effective)
    window_class = classify_window(protocol, window_start, window_end)
    if window_class is WindowClass.IN_SAMPLE:
        return Decision(
            protocol.sha256, window_class, arm, None, None, None, grid_point(protocol, effective)
        )

    where = f"{window_start.isoformat()} to {window_end.isoformat()}"
    if not provenance_accepted:
        raise ProtocolRefusalError(
            Refusal.PROVENANCE,
            f"the window {where} touches the out-of-sample window (from {protocol.boundary.isoformat()}), "
            "and a run reads it only from a deployment clone of a pushed commit whose boot_provenance "
            "verdict is accepted.",
        )
    digest = candidate_digest(effective)
    entry = next((e for e in entries if e.candidate_digest == digest), None)
    if entry is None:
        raise ProtocolRefusalError(
            Refusal.NO_ENTRY,
            f"the window {where} touches the out-of-sample window, and no committed entry under "
            f"{ENTRIES_DIR.as_posix()} carries candidate digest {digest}. Commit the candidate's entry "
            "first, push it, and run from a clone of that commit.",
        )

    variant: Variant | None = None
    expected_start, expected_end = protocol.boundary, protocol.history_end
    if entry.kind == "candidate":
        variant = grid_point(protocol, effective)
        if variant is None:
            raise ProtocolRefusalError(
                Refusal.NOT_A_GRID_POINT,
                f"entry {entry.id!r} names a candidate that is not a point of any declared family's grid, "
                "so it cannot be read out of sample; amend the protocol first (PROTOCOL.md section 10).",
            )
    else:
        baseline = protocol.baseline(entry.ref)
        if baseline is None or not _is_baseline(protocol, baseline, effective):
            raise ProtocolRefusalError(
                Refusal.BASELINE_MISMATCH,
                f"entry {entry.id!r} is a baseline entry, and the run is not the declared baseline {entry.ref!r}.",
            )
        expected_start, expected_end = baseline.window_start, baseline.window_end

    if (window_start, window_end) != (expected_start, expected_end):
        raise ProtocolRefusalError(
            Refusal.WRONG_WINDOW,
            f"entry {entry.id!r} may be read only over exactly "
            f"{expected_start.isoformat()} to {expected_end.isoformat()}, not {where}.",
        )
    if tuple(sorted(entry.arms)) != tuple(sorted(protocol.arms)):
        raise ProtocolRefusalError(
            Refusal.ARMS_MISMATCH,
            f"entry {entry.id!r} lists arms {list(entry.arms)}, and the protocol's are {list(protocol.arms)}.",
        )
    if arm not in protocol.arms:
        raise ProtocolRefusalError(
            Refusal.ARM_NOT_DECLARED,
            f"stop slippage {arm}% is not one of the declared arms {list(protocol.arms)}.",
        )
    if entry.status != "pending" or entry.oos is not None:
        raise ProtocolRefusalError(
            Refusal.ALREADY_READ,
            f"entry {entry.id!r} has been read out of sample already (status {entry.status!r}); a candidate "
            "is read once.",
        )
    if (digest, arm) in local_reads:
        raise ProtocolRefusalError(
            Refusal.LOCAL_PRIOR_READ,
            f"this clone already holds a completed record of entry {entry.id!r} at stop slippage {arm}% "
            "over the out-of-sample window; a candidate is read once per arm.",
        )
    return Decision(protocol.sha256, window_class, arm, entry.kind, entry.id, entry.sha256, variant)
