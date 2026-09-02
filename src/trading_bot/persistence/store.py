"""A crash-survivable store for the facts the venue cannot answer.

**THE COMPOSITION ROOT IS THE ONLY CALLER, and a test enforces that rather
than this sentence.** ``engine/modes.py`` reads the store at boot and writes it
through a callable it injects into ``OrderExecutor``; ``execution/`` imports
nothing from here, so the executor gains no outer-to-outer edge.
``TestOnlyTheCompositionRootMayImportTheStore`` pins both halves.

**This paragraph asserted the OPPOSITE until M5h's maintenance commit.** It
read *"NOTHING IMPORTS THIS FROM OUTSIDE THIS PACKAGE ... The store exists, is
tested, and has no caller"*, and survived on disk through both commits that
falsified it, because each was authorised to change the wiring and not this
file. That is worth recording rather than quietly correcting: a docstring
outliving its fact is this project's recorded recurring defect, and here the
mechanism was an AUTHORISATION BOUNDARY running between a fact and the prose
describing it -- which is a mechanism no gate, grep or review can see, since
both halves were individually correct at the moment they were written.

**NO PORT IS DECLARED, and finding GG is why.** A persistence port would have
exactly one implementation and one caller -- the composition root -- for the
whole of this milestone. GG records what that costs: ``approve`` sat on a port
with no production caller for two milestones, "accumulating the P2 gap that
made deleting it a prerequisite rather than a tidy-up". A concrete module is
promotable to a port the day a second implementation is real; an unearned
declaration is debt from the day it lands. :func:`load` and :func:`save` take
a ``path`` with a default, exactly as ``instance_lock.acquire`` takes
``DEFAULT_LOCK_PATH`` -- this project's worked example of a concrete module
that is testable without an abstraction, and no fake is needed either way.

This module's own tests pass a ``tmp_path``. The COMPOSITION tests in
``test_modes.py`` do not, deliberately: they exercise the DEFAULT path under an
autouse ``chdir``, because the default is what production uses and a test that
passed an explicit path would leave the default itself unexercised. This
paragraph read *"every test passes a ``tmp_path``"* until those tests existed.

**WHAT IT HOLDS: exactly what the venue cannot answer, and nothing
derivable.** The inclusion test is ``PendingPlacement``'s own line -- *"Every
field is something WE REQUESTED, never something the venue reported."* A
persisted fact that goes stale is worse than an absent one, so anything the
venue can be asked at boot is asked at boot:

* **The pending placement set** -- the seven fields ``PendingPlacement``
  carries and no more. When the list did not land, the venue holds no evidence
  the attempt was ever made; that is the whole of what cannot be re-derived.
* **The ledger** -- ``realised_pnl`` and ``pnl_date`` TOGETHER. No trade-history
  method is declared on the port, and attributing P&L needs entry prices of
  positions that no longer exist.
* **A ``schema`` integer**, so the shape can grow additively. ``CLOSE`` will
  need a pending record of a different shape; this is what lets it arrive
  without invalidating a file already on disk.

**What it does NOT hold, each for a stated reason.** No ``Position``: a live
list's economics are venue-derivable, MEASURED -- a captured ``allOrderList``
payload carries populated leg identity triples for a LIVE list -- and a
persisted position the venue has since closed makes ``has_position`` true for
nothing. No ``free_quote``, ``unmanaged_holdings`` or ``blocked_symbols``: all
three are computed at boot from one ``get_balances`` and one
``get_all_order_lists``. No ``cooldown_until``: ``start_cooldown`` has zero
callers, so its schema would be written against assumptions the milestone that
gives it a writer has not made. **No fill price of any kind** -- entry or exit
-- because booking is piece 2's and its source is not ruled.

**THE LEDGER IS ABSENT, NOT ZERO, UNTIL A FIRST ACCRUAL, and the distinction
is load-bearing.** Absent means *nothing has ever been booked*; ``0`` would
mean *accruals netted to zero*. Those are different facts and a reader acting
on the second when the first is true would take "the ledger says zero" as
authority. This is the ``Position.protection`` lock applied to a new field --
*"A default should be the value most likely to be NOTICED when wrong; this is
the value least likely to be"* -- and the ``RiskAssessment.stage`` discipline
of required-but-nullable, so every state says something deliberately.

**MONEY CROSSES AS A STRING, AND THE ADMISSIBLE SET IS A WHITELIST.** Every
``Decimal`` is written as its ``str`` and read back through pydantic's exact
string coercion, which is the boundary the log sink already operates --
``JsonFormatter`` serialises with ``default=str``, so a ``Decimal`` reaches a
log line as ``"50.000"``, exact and never a float. ``CLAUDE.md`` states the
rule that follows and this module obeys it: *"only ``str``, ``int``,
``float``, ``bool``, ``None`` and ``Decimal`` may cross ``extra=``
unconverted. Everything else is converted at the call site -- an enum by
``.value``, a ``datetime`` by ``.isoformat()``."* There is no catch-all here.
Each type is dumped by a named function, because ``default=str`` is precisely
what lets an unrecognised object land as its ``repr`` and produce a
plausible-looking file with no error.

**A ``float`` is REFUSED, not converted.** Every money field is ``Money``, so
the ``_reject_float`` validator runs on load as it does everywhere else in the
domain. A file hand-edited to carry a JSON number rather than a string is a
corrupt file and says so.

**THE WRITE IS ATOMIC AND IS fsync'd AT BOTH SITES.** Temp file in the same
directory, ``flush``, ``os.fsync``, ``os.replace``. ``os.replace`` alone
survives process death; ``fsync`` additionally survives machine crash and
power loss. The frequency argument is what decides it rather than the latency:
at most one write per entry signal and one per position close -- run 5
produced ONE entry in three hours -- so the measured cost of 41.562 ms median
with ``fsync`` on this repository's volume, against 0.326 ms without, is
nearly free at that rate, while the alternative is an order list resting at
the venue with no record of it and no bound on how long that lasts.

**A CORRUPT FILE RAISES; IT DOES NOT READ AS EMPTY.** A store that silently
returns an empty state when it cannot parse is indistinguishable from no store
at all, which is the exact failure it exists to prevent -- and it would
manifest as the bot quietly forgetting a pending placement rather than as an
error anyone sees. A MISSING file is a different answer and returns ``None``:
no store yet is a normal first-boot state, and conflating the two would make a
first boot look like corruption.

**TWO RECORDS FOR ONE SYMBOL IS CORRUPTION, NOT A LATER-WINS OVERWRITE.** The
executor keys ``_pending`` by symbol, so a restored duplicate would COLLAPSE on
the way in and one record would vanish silently -- and the vanished one may be
the placement that actually landed, leaving an order list resting at the venue
with nothing tracking it. That is precisely the unbounded state this store
exists to close, reached through the restore path. So :class:`PersistedState`
refuses it and :func:`load` reports :class:`StoreCorruptError`, which stops the
boot with the file preserved for an operator to read.

**THE TRIGGER IS UNREACHABLE FROM OUR OWN WRITER, and that is recorded here so
a later reader does not delete the guard as dead.** Three of the four write
sites pass ``tuple(self._pending.values())`` -- a symbol-keyed dict, so a
duplicate is structurally impossible. The fourth, in ``OrderExecutor.dispatch``,
passes ``(*self._pending.values(), record)`` and appends a record the dict did
not supply; what prevents a duplicate THERE is the pending guard that refuses a
signal whose symbol is already in ``_pending``, forty-odd lines earlier. So one
route is barred structurally and one behaviourally, and only the second could
be reopened by an edit that looks unrelated. A hand-edited file is the only
route that reaches this today.
"""

from __future__ import annotations

import contextlib
import json
import os
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from trading_bot.core.exceptions import TradingBotError
from trading_bot.core.models import Money

__all__ = [
    "DEFAULT_STORE_PATH",
    "SCHEMA_VERSION",
    "LedgerRecord",
    "PendingRecord",
    "PersistedState",
    "StoreCorruptError",
    "load",
    "save",
]

#: Under ``data/``, which ``.gitignore`` covers with ``data/*`` and
#: ``!data/.gitkeep``. A run artefact, like the log: it is NOT tracked, and it
#: does not solve the problem that nothing notices a run happened.
DEFAULT_STORE_PATH = Path("data/state.json")

#: Bumped only when a shape change cannot be read by the previous version.
#: Adding an optional key is additive and does not move it.
SCHEMA_VERSION = 1

_TEMP_SUFFIX = ".tmp"


class StoreCorruptError(TradingBotError):
    """The store exists and cannot be trusted.

    Distinct from a missing store, which :func:`load` reports as ``None``.
    Raised for unreadable bytes, invalid JSON, an unknown schema version, and
    any payload the models reject -- including a money value written as a JSON
    number, which ``Money`` refuses.
    """


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True)


class PendingRecord(_Frozen):
    """One placement whose outcome was not observed, as it survives a restart.

    The seven fields ``PendingPlacement`` carries, and no more. Every one is
    something WE REQUESTED, never something the venue reported -- that line is
    the inclusion test, and ``executedQty``, a fill price, a leg status or an
    ``orderId`` all fall on the other side and must never be added.
    """

    symbol: str
    entry_bar_time: datetime
    generation: int
    quantity: Money
    entry_limit: Money
    # REQUIRED, matching ``PendingPlacement``. The type still admits ``None``
    # -- a both-disabled config is legal and its levels are genuinely absent --
    # but the KEY must be present, so a truncated store RAISES instead of
    # silently reading as unprotected. ``load`` converts the resulting
    # ``ValidationError`` into ``StoreCorruptError``, which is the type this
    # module documents.
    stop_loss: Money | None
    take_profit: Money | None


class LedgerRecord(_Frozen):
    """Realised P&L and the UTC day it covers. Both, or neither.

    Restoring one without the other is indistinguishable from restoring
    neither: ``_ledger_is_stale`` returns ``True`` on ``covered is None``, so
    a ``realised_pnl`` with no ``pnl_date`` reads as zero for every ``now``.
    Keeping them in one object makes that unrepresentable.
    """

    realised_pnl: Money
    pnl_date: date


class PersistedState(_Frozen):
    """Everything the store holds. ``ledger=None`` means never accrued."""

    schema_version: int = Field(default=SCHEMA_VERSION, ge=1)
    pending: tuple[PendingRecord, ...] = ()
    ledger: LedgerRecord | None = None

    @model_validator(mode="after")
    def _reject_duplicate_symbols(self) -> PersistedState:
        """A symbol may carry at most one unresolved placement.

        **ON THE MODEL RATHER THAN IN :func:`load`, and the reason is which
        constructions get checked.** The composition root builds a
        ``PersistedState`` directly on every write, so a check living only in
        the read path would let a writer-side defect put an invalid state on
        disk and surface it one boot later, at the wrong component. Here, both
        directions are refused at the moment the invalid object is built.

        **It reaches the documented error type for free.** Raising
        ``ValueError`` makes pydantic wrap this in a ``ValidationError``, and
        :func:`load` already converts that to :class:`StoreCorruptError` --
        VERIFIED by driving a duplicate file through ``load``, not inferred
        from reading the ``except`` clause. A direct construction still raises
        ``ValidationError``, which is correct: ``StoreCorruptError`` says *the
        file cannot be trusted*, and there is no file in that case.

        The trigger is unreachable from our own writer; see the module
        docstring for why the guard is kept anyway.
        """
        seen: set[str] = set()
        duplicated: set[str] = set()
        for record in self.pending:
            if record.symbol in seen:
                duplicated.add(record.symbol)
            seen.add(record.symbol)
        if duplicated:
            raise ValueError(
                f"{len(self.pending)} pending record(s) carry a duplicated symbol "
                f"({', '.join(sorted(duplicated))}). A symbol may have at most one "
                "unresolved placement: the executor keys them by symbol, so a duplicate "
                "would collapse on restore and silently discard one record -- possibly "
                "the placement that landed, leaving an order list resting at the venue "
                "with nothing tracking it."
            )
        return self


def _dump_money(value: Decimal) -> str:
    """A ``Decimal`` crosses as its exact ``str``, never as a JSON number."""
    return str(value)


def _dump_optional_money(value: Decimal | None) -> str | None:
    return None if value is None else _dump_money(value)


def _dump_pending(record: PendingRecord) -> dict[str, Any]:
    """One record, field by named field. There is no catch-all serialiser."""
    return {
        "symbol": record.symbol,
        "entry_bar_time": record.entry_bar_time.isoformat(),
        "generation": record.generation,
        "quantity": _dump_money(record.quantity),
        "entry_limit": _dump_money(record.entry_limit),
        "stop_loss": _dump_optional_money(record.stop_loss),
        "take_profit": _dump_optional_money(record.take_profit),
    }


def _dump_ledger(ledger: LedgerRecord | None) -> dict[str, Any] | None:
    if ledger is None:
        return None
    return {
        "realised_pnl": _dump_money(ledger.realised_pnl),
        "pnl_date": ledger.pnl_date.isoformat(),
    }


def _serialise(state: PersistedState) -> str:
    """The whole file as text. Pure, and it runs BEFORE anything is written.

    The fallible step precedes the irreversible one, as every multi-write
    method in this project does: if a value cannot be dumped, the existing
    file is still the last good one.
    """
    payload = {
        "schema": state.schema_version,
        "pending": [_dump_pending(record) for record in state.pending],
        "ledger": _dump_ledger(state.ledger),
    }
    return json.dumps(payload, indent=2, sort_keys=True) + "\n"


def load(path: Path = DEFAULT_STORE_PATH) -> PersistedState | None:
    """The stored state, or ``None`` when no store exists yet.

    ``None`` is a first boot and is normal. Anything else that goes wrong
    raises :class:`StoreCorruptError` rather than degrading to an empty
    state.

    :raises StoreCorruptError: unreadable, unparseable, an unknown schema
        version, or a payload the models reject.
    """
    try:
        raw_text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return None
    except OSError as exc:
        raise StoreCorruptError(f"{path} exists but could not be read: {exc}") from exc

    try:
        payload = json.loads(raw_text)
    except ValueError as exc:
        raise StoreCorruptError(f"{path} is not valid JSON: {exc}") from exc

    if not isinstance(payload, dict):
        raise StoreCorruptError(f"{path} holds {type(payload).__name__}, not an object")

    version = payload.get("schema")
    if version != SCHEMA_VERSION:
        raise StoreCorruptError(
            f"{path} declares schema {version!r}; this build reads {SCHEMA_VERSION} only"
        )

    try:
        return PersistedState(
            schema_version=SCHEMA_VERSION,
            pending=tuple(PendingRecord(**entry) for entry in payload.get("pending", [])),
            ledger=(None if payload.get("ledger") is None else LedgerRecord(**payload["ledger"])),
        )
    except (ValidationError, TypeError) as exc:
        raise StoreCorruptError(f"{path} does not match the expected shape: {exc}") from exc


def save(state: PersistedState, path: Path = DEFAULT_STORE_PATH) -> None:
    """Write the state atomically and durably. Replaces any existing file.

    Serialise, write to a sibling temp file, ``flush``, ``os.fsync``, then
    ``os.replace``. The temp file is removed on every path that does not
    reach the replace, so a failed write leaves no debris beside the store.

    :raises OSError: the directory cannot be created or written.
    """
    payload = _serialise(state)  # fallible, and first
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + _TEMP_SUFFIX)
    try:
        # `newline=""` writes the string's own LF, never a platform CRLF: this
        # tree is LF-pinned and a store round-tripped through CRLF would still
        # parse, so nothing downstream would report it.
        with open(temp, "w", encoding="utf-8", newline="") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp, path)
    except BaseException:
        # Best-effort, and deliberately swallowing: the write's own error is
        # what the caller needs, and a cleanup failure raised over it would
        # mask the cause -- the masking the nested-teardown rule prevents.
        with contextlib.suppress(OSError):  # pragma: no cover - cleanup of a cleanup
            temp.unlink(missing_ok=True)
        raise
