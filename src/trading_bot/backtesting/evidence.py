"""Which backtest run records are EVIDENCE (R-AR), and the one door that refuses the rest.

The project owner's ruling R-AR, verbatim: *"A backtest run record carries evidence_eligible, true only
when the provenance verdict is accepted. Every S4 to S7 comparison or decision refuses a record whose
evidence_eligible is false."*

**Why a flag when the verdict is already in the record.** ``provenance.verdict`` has three values --
``accepted``, ``refused`` and ``unrecorded`` -- and a reader who does not know that an editable install
or a dirty checkout reads ``refused`` will mistake an ordinary-looking ``run.json`` for evidence. The
backtest itself RUNS on a refused verdict (only ``run`` is gated, because a backtest touches no venue,
store or lock), so the record is the only place the difference can live. The smoke runs of P106 and P107
were refused records and read exactly like accepted ones until this key existed (M5m-193).

**A record without the key is not evidence.** Schema 3 and earlier have no ``evidence_eligible``, and
absence is refusal: a file written before the ruling cannot have been judged by it.

**A record without its effective settings is not evidence either (R-BR).** The owner's ruling: *"Every
effective setting is written into the run record and into the candidate digest; a record without them is
not evidence_eligible."* From schema 5 the record carries ``effective`` (what the run used, after every
command-line override) and the ``candidate_digest`` and ``settings_digest`` of it, and the door refuses a
schema-5-or-later record that lacks them or whose digests are not those of its ``effective`` block, even
with ``evidence_eligible`` true. **No schema is demanded by default**: S4's frozen comparison reads
schema-4 records written by the S4 clone's code, which has no such block, and it judges each live boot
line through the same door with a synthetic record whose ``schema`` is text (``M5m-313``, measured: a
door that demanded an integer schema failed ten of ``test_s4_compare.py``'s tests). A consumer that must
not accept an older or a non-integer schema passes ``min_schema`` (S5 and S6 do).

**The door.** :func:`load_eligible_record` reads a ``run.json`` and refuses it unless it is eligible;
:func:`require_evidence_eligible` is the same judgement for a record already in hand. A consumer that
compares, decides or reports on a run record calls one of them FIRST. ``tests/unit/test_backtest_evidence.py``
reads every module under ``src/`` and ``scripts/`` and fails if one names ``run.json`` without calling
one, so a new S4 to S7 script cannot be written that skips the check.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Final

from trading_bot.backtesting.candidate import EffectiveSettingsError, check_record_digests
from trading_bot.core.exceptions import TradingBotError

__all__ = [
    "EFFECTIVE_SCHEMA",
    "EVIDENCE_KEY",
    "RUN_RECORD_NAME",
    "EvidenceRefusedError",
    "is_evidence_eligible",
    "load_eligible_record",
    "require_evidence_eligible",
]

#: The record's key, and the file a run directory holds it in.
EVIDENCE_KEY: Final = "evidence_eligible"
RUN_RECORD_NAME: Final = "run.json"

#: The first run-record schema that carries the effective settings and their digests (R-BR).
EFFECTIVE_SCHEMA: Final = 5


class EvidenceRefusedError(TradingBotError):
    """A run record is not evidence: its ``evidence_eligible`` is false, absent or not a boolean."""


def is_evidence_eligible(provenance: Mapping[str, object]) -> bool:
    """True only when the boot line's verdict reads ``accepted``; any other value is not evidence."""
    return provenance.get("verdict") == "accepted"


def require_evidence_eligible(
    record: Mapping[str, object], *, source: str = "the run record", min_schema: int | None = None
) -> None:
    """Refuse a record whose ``evidence_eligible`` is not exactly ``True``, or whose schema is short.

    :param min_schema: the oldest schema this consumer accepts, as an integer; ``None`` (the default)
        demands none. A consumer that needs the effective settings passes 5 or more.
    :raises EvidenceRefusedError: it is false, absent (a schema before the ruling) or not a boolean;
        the schema is below ``min_schema``; or, from schema 5, the effective settings are absent or
        their digests do not match. The message names the cause so it is not a hunt.
    """
    flag = record.get(EVIDENCE_KEY)
    if flag is True:
        _require_schema_and_effective(record, source=source, min_schema=min_schema)
        return
    provenance = record.get("provenance")
    if isinstance(provenance, Mapping):
        verdict = provenance.get("verdict", "absent")
        reasons = provenance.get("refusal_reasons", "not recorded")
    else:
        verdict, reasons = "absent", "not recorded"
    if flag is None:
        state = f"carries no {EVIDENCE_KEY} (schema {record.get('schema')!r}, written before R-AR)"
    elif flag is False:
        state = f"has {EVIDENCE_KEY} false"
    else:
        state = f"has {EVIDENCE_KEY} {flag!r}, which is not a boolean"
    raise EvidenceRefusedError(
        f"{source} {state} and is not evidence for S4 to S7: provenance verdict {verdict!r}, "
        f"refusal reasons {reasons!r}. A run is evidence only from a deployment clone of a pushed "
        "commit whose boot_provenance verdict is accepted."
    )


def _require_schema_and_effective(
    record: Mapping[str, object], *, source: str, min_schema: int | None
) -> None:
    """The schema rule, applied to a record whose flag is true.

    A consumer that names ``min_schema`` gets an integer schema at or above it. One that does not
    gets none demanded, because ``scripts/s4_compare.py`` (frozen) passes a synthetic record for each
    live boot line whose ``schema`` is the text ``"live-boot"``; but ANY record with an integer
    schema of 5 or more must carry its effective settings and matching digests (R-BR).
    """
    raw = record.get("schema")
    schema: int | None = raw if isinstance(raw, int) and not isinstance(raw, bool) else None
    if min_schema is not None:
        if schema is None:
            raise EvidenceRefusedError(
                f"{source} carries no integer schema ({raw!r}) and is not evidence"
            )
        if schema < min_schema:
            raise EvidenceRefusedError(
                f"{source} is schema {schema}, and this consumer needs schema {min_schema} or later"
            )
    if schema is not None and schema >= EFFECTIVE_SCHEMA:
        try:
            check_record_digests(record)
        except EffectiveSettingsError as exc:
            raise EvidenceRefusedError(
                f"{source} is not evidence for S4 to S7: {exc} (R-BR)"
            ) from exc


def load_eligible_record(path: Path, *, min_schema: int | None = None) -> dict[str, object]:
    """Read ``path`` (a ``run.json``) and return it, refusing it first unless it is evidence.

    :raises EvidenceRefusedError: see :func:`require_evidence_eligible`, or the file is not a
        JSON object.
    """
    try:
        record = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise EvidenceRefusedError(f"{path} cannot be read as a run record: {exc}") from exc
    if not isinstance(record, dict):
        raise EvidenceRefusedError(f"{path} is not a JSON object")
    require_evidence_eligible(record, source=str(path), min_schema=min_schema)
    return record
