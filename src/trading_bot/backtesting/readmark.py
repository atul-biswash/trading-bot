"""Marking a candidate's entry ``read`` (R-CP, the owner's step O7): verify its three records, write their digests.

The sequence of PROTOCOL.md section 8: an entry is committed ``pending``, its three arms are read out of sample, and the
entry is committed again as ``read`` with ``oos.records`` holding, per arm, the run directory and the SHA-256 of its
``run.json``. Until P119 nothing in the tree did the second half; the P118 rehearsal did it inside its own script.

**What is verified, and where.** Every ``run.json`` under the backtests directory is read through the evidence door
(R-AR), and a record that fails it REFUSES the whole marking: this is an out-of-sample clone, in which a run that is
not evidence is an anomaly the operator must explain, not noise to skip. A record is then an out-of-sample candidate
record if the guard's ``protocol`` block says so; in-sample records are ignored, and a record with no ``protocol``
block refuses. Against its entry each out-of-sample record must carry the entry's candidate digest, the current
protocol's digest and exactly the declared out-of-sample window, and an entry needs exactly one record at each
declared arm and nothing else. **The refusals are R-CP's**: an entry already read, a record that fails the door, and a
set other than exactly the declared arms. The gate (``gate.evaluate``) re-checks every record against its entry when
it judges; this module exists so that a typo is found before the commit and not after it.

Pure but for :func:`read_records`, which reads run directories. Nothing here writes: :func:`plan` returns the bytes.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from trading_bot.backtesting.candidate import canonical_number
from trading_bot.backtesting.evidence import (
    RUN_RECORD_NAME,
    EvidenceRefusedError,
    load_eligible_record,
)
from trading_bot.backtesting.gate import MIN_RECORD_SCHEMA
from trading_bot.backtesting.protocol import Protocol, parse_entry
from trading_bot.core.exceptions import TradingBotError

__all__ = [
    "EntryFile",
    "MarkRefusedError",
    "Marking",
    "OosRecord",
    "entry_bytes",
    "plan",
    "read_records",
]


class MarkRefusedError(TradingBotError):
    """An entry cannot be marked ``read``; the message says which rule refused and for which entry or run."""


@dataclass(frozen=True)
class OosRecord:
    """One out-of-sample candidate record, read through the evidence door."""

    entry_id: str
    arm: str
    run: str
    run_json_sha256: str
    candidate_digest: object
    protocol_sha256: object
    window: tuple[object, object]


@dataclass(frozen=True)
class EntryFile:
    """An entry file as it is on disk: its name and its exact text."""

    name: str
    text: str


@dataclass(frozen=True)
class Marking:
    """One entry's new bytes, and the records they hold, in arm order."""

    name: str
    entry_id: str
    data: bytes
    records: tuple[tuple[str, str, str], ...]


def entry_bytes(body: Mapping[str, Any]) -> bytes:
    """An entry as ``s6_select.py`` writes one: indented JSON, ASCII, one trailing newline, LF."""
    return (json.dumps(body, indent=2) + "\n").encode("ascii")


def _arm_of(value: object, where: str) -> str:
    try:
        return canonical_number(Decimal(str(value)))
    except InvalidOperation:
        raise MarkRefusedError(
            f"{where} names stop slippage {value!r}, which is not a number"
        ) from None


def read_records(backtests: Path) -> tuple[OosRecord, ...]:
    """Every out-of-sample candidate record under ``backtests``, each read through the evidence door.

    :raises MarkRefusedError: a ``run.json`` fails the door, changes while it is read, carries no ``protocol``
        block, or is out of sample with no entry id or no arm.
    """
    found: list[OosRecord] = []
    directories = sorted(p for p in backtests.iterdir() if p.is_dir()) if backtests.is_dir() else []
    for directory in directories:
        path = directory / RUN_RECORD_NAME
        if not path.is_file():
            continue  # a run cut off, or still named -running: no record is written until the end
        where = str(path)
        try:
            record = load_eligible_record(path, min_schema=MIN_RECORD_SCHEMA)
        except EvidenceRefusedError as exc:
            raise MarkRefusedError(f"{where} fails the evidence door: {exc}") from exc
        raw = path.read_bytes()
        if json.loads(raw) != record:
            raise MarkRefusedError(f"{where} changed while it was being read")
        block = record.get("protocol")
        if not isinstance(block, Mapping):
            raise MarkRefusedError(f"{where} carries no protocol block, so no guard decided it")
        if block.get("window_class") != "out_of_sample":
            continue
        entry_id = block.get("entry_id")
        if not isinstance(entry_id, str) or not entry_id:
            raise MarkRefusedError(f"{where} is out of sample and names no entry")
        window = record.get("window")
        if not isinstance(window, Mapping):
            raise MarkRefusedError(f"{where} carries no window")
        found.append(
            OosRecord(
                entry_id=entry_id,
                arm=_arm_of(block.get("arm"), where),
                run=directory.name,
                run_json_sha256=hashlib.sha256(raw).hexdigest(),
                candidate_digest=record.get("candidate_digest"),
                protocol_sha256=block.get("protocol_sha256"),
                window=(window.get("start_date"), window.get("end_date")),
            )
        )
    return tuple(found)


def _check_record(item: OosRecord, digest: str, protocol: Protocol) -> None:
    expected = (protocol.boundary.isoformat(), protocol.history_end.isoformat())
    if item.window != expected:
        raise MarkRefusedError(
            f"{item.run} covers {item.window[0]} to {item.window[1]}, and an out-of-sample read is exactly "
            f"{expected[0]} to {expected[1]}"
        )
    if item.candidate_digest != digest:
        raise MarkRefusedError(
            f"{item.run} has candidate digest {item.candidate_digest!r}, and entry {item.entry_id!r} binds {digest!r}"
        )
    if item.protocol_sha256 != protocol.sha256:
        raise MarkRefusedError(
            f"{item.run} was made under protocol {item.protocol_sha256!r}, and the protocol now is "
            f"{protocol.sha256!r}"
        )


def plan(
    entries: Sequence[EntryFile],
    records: Sequence[OosRecord],
    protocol: Protocol,
    *,
    known_ids: frozenset[str],
) -> tuple[Marking, ...]:
    """The marking of each of ``entries``, or a refusal for the first rule one of them breaks.

    ``known_ids`` is every entry id on disk, targets or not: a record naming an id outside it is refused, where
    a record naming a known entry that is not being marked is left alone. Nothing is returned for a subset:
    the caller writes all of it or none.

    :raises MarkRefusedError: an entry is not a pending candidate, a record belongs to no entry, a record is not
        the entry's (digest, protocol, window), an arm is read twice, or the arms are not exactly the declared ones.
    """
    unknown = sorted({r.entry_id for r in records} - known_ids)
    if unknown:
        raise MarkRefusedError(
            f"out-of-sample records name entries that are not committed: {', '.join(unknown)}"
        )
    declared = sorted(protocol.arms)
    markings: list[Marking] = []
    for file in entries:
        entry = parse_entry(file.text)
        if entry.kind != "candidate":
            raise MarkRefusedError(
                f"entry {entry.id!r} is a {entry.kind!r} entry, not a candidate's"
            )
        if entry.status != "pending" or entry.oos is not None:
            raise MarkRefusedError(
                f"entry {entry.id!r} is already read (status {entry.status!r}); a candidate is read once"
            )
        if sorted(entry.arms) != declared:
            raise MarkRefusedError(
                f"entry {entry.id!r} lists arms {list(entry.arms)}, and the protocol's are {declared}"
            )
        mine = [r for r in records if r.entry_id == entry.id]
        by_arm: dict[str, OosRecord] = {}
        for item in mine:
            _check_record(item, entry.candidate_digest, protocol)
            if item.arm in by_arm:
                raise MarkRefusedError(
                    f"entry {entry.id!r} has two records at arm {item.arm}: {by_arm[item.arm].run} and "
                    f"{item.run}; a candidate is read once per arm"
                )
            by_arm[item.arm] = item
        if sorted(by_arm) != declared:
            missing = sorted(set(declared) - set(by_arm))
            extra = sorted(set(by_arm) - set(declared))
            raise MarkRefusedError(
                f"entry {entry.id!r} needs exactly one out-of-sample record at each of {declared}; "
                f"it has {sorted(by_arm)} (missing {missing}, not declared {extra})"
            )
        raw = json.loads(file.text)
        spelled = {canonical_number(Decimal(a)): a for a in raw["arms"]}
        ordered = sorted(declared, key=Decimal)
        marked = dict(raw)
        marked["status"] = "read"
        marked["oos"] = {
            "records": {
                spelled[arm]: {
                    "run": by_arm[arm].run,
                    "run_json_sha256": by_arm[arm].run_json_sha256,
                }
                for arm in ordered
            }
        }
        markings.append(
            Marking(
                name=file.name,
                entry_id=entry.id,
                data=entry_bytes(marked),
                records=tuple(
                    (arm, by_arm[arm].run, by_arm[arm].run_json_sha256) for arm in ordered
                ),
            )
        )
    return tuple(markings)
