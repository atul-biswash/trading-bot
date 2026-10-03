#!/usr/bin/env python
"""Normalise the ledger's money exponents to eight decimal places -- M5l's C49, ruled at P92-7.

**WHAT IT IS FOR.** ``Decimal`` addition keeps the finest exponent of its
operands, so four bookings that carried exponent -24 (``M5l-209``) left
``lifetime_realised`` and a day's ``realised`` at -24 in ``data/state.json``,
and every later booking added to them keeps it there (``M5l-210``). C48 stops
the source; nothing in the tree repairs what is already persisted, and this
is that repair. It is a ONE-OFF: run it once per store that carries the
exponent, from a deployment clone's root, and not again.

**IT TOUCHES THE LEDGER'S THREE MONEY SITES AND NOTHING ELSE** -- the open
day's ``realised_pnl``, each completed day's ``realised`` in ``daily_history``,
and ``lifetime_realised``. Positions, pending records, dates and counts are
carried as they were, through the store's own ``load`` and ``save``, so the
schema check and the atomic write apply.

**LOSSLESS-ONLY, PROVED PER VALUE.** A value whose exponent is finer than -8 is
quantised to -8 only if the quantised figure EQUALS it. A value that would
lose a digit -- a ninth decimal place that is not zero -- is never rounded: the
tool refuses, names every such value, and writes nothing. A value already at -8
or coarser is left alone. Refusing rather than rounding is deliberate: this is
a money figure in a durable ledger, and "close enough" is how a ledger stops
matching an exchange statement.

**IT REFUSES WHILE THE BOT RUNS.** It takes the same non-blocking instance lock
the bot takes and holds it for the whole operation, as ``release_position.py``
does, so the bot cannot write the store between this tool's read and its write.

**IT CHANGES EXPONENTS AND NOTHING ELSE, SO IT REFUSES A STORE AT ANOTHER SCHEMA.**
``store.save`` always writes the current schema, so normalising a file written
by an older build would also upgrade it and add the ``positions`` key -- a
second change this tool was not asked to make. MEASURED on a copy of the
2026-09-17 store: schema 1 came back as schema 2 with ``positions: []``. The
operator runs the bot's own build once, which does exactly that, and then this.

**IT NEVER WRITES TO THE VENUE**, and writes only on ``--apply``: without it the
tool prints what it would change and exits 0 with the file untouched.

**IT LOGS BOTH SHA-256s.** One line is appended to ``logs/normalize.log``, and
printed, carrying the store's SHA-256 before and after, so a later reader can
tell which file this tool wrote and that no other changed.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from collections.abc import Callable
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import NamedTuple

from trading_bot.persistence import store
from trading_bot.utils.helpers import utc_now
from trading_bot.utils.instance_lock import DEFAULT_LOCK_PATH, InstanceLockedError, acquire

#: Appended to, never rewritten. Relative to the working directory, like the
#: store and the lock, so it lands beside the clone's own logs.
NORMALIZE_LOG_PATH = Path("logs/normalize.log")

#: Eight decimal places: the exponent every quote-denominated figure the venue
#: reports carries, and the one the ledger's figures have everywhere else.
_EXPONENT = -8
_QUANTUM = Decimal(1).scaleb(_EXPONENT)


class NotLosslessError(ValueError):
    """A value cannot be brought to eight decimal places without changing it."""


class Change(NamedTuple):
    """One value this tool would change, and what it would become. Equal in value."""

    where: str
    before: Decimal
    after: Decimal


class Refusal(NamedTuple):
    """One value this tool cannot quantise losslessly, and where it is."""

    where: str
    value: Decimal


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def quantise_to_8dp(value: Decimal) -> Decimal:
    """``value`` at exponent -8, or ``value`` unchanged if it is already at -8 or coarser.

    **THE LOSSLESS CHECK IS THE POINT.** ``quantize`` rounds, so the result is
    compared with the input by value and a difference raises: a figure that
    would lose a digit is never returned.

    :raises NotLosslessError: the value is not finite, or quantising it would
        change it.
    """
    exponent = value.as_tuple().exponent
    if not isinstance(exponent, int):
        raise NotLosslessError(f"{value} is not a finite number")
    if exponent >= _EXPONENT:
        return value
    try:
        quantised = value.quantize(_QUANTUM)
    except InvalidOperation as exc:
        raise NotLosslessError(f"{value} cannot be represented at eight decimal places") from exc
    if quantised != value:
        raise NotLosslessError(f"{value} would become {quantised}: a digit would be lost")
    return quantised


def normalise_state(
    state: store.PersistedState,
) -> tuple[store.PersistedState, list[Change], list[Refusal]]:
    """The state with its three ledger sites quantised, what changed, and what refused.

    If anything refused, the returned state is ``state`` itself: a caller must
    not write a partly normalised ledger, and gets the original back to make
    that impossible to do by accident.
    """
    changes: list[Change] = []
    refusals: list[Refusal] = []

    def one(where: str, value: Decimal) -> Decimal:
        try:
            quantised = quantise_to_8dp(value)
        except NotLosslessError:
            refusals.append(Refusal(where, value))
            return value
        if quantised.as_tuple().exponent != value.as_tuple().exponent:
            changes.append(Change(where, value, quantised))
        return quantised

    ledger = state.ledger
    if ledger is not None:
        ledger = ledger.model_copy(
            update={"realised_pnl": one("ledger.realised_pnl", ledger.realised_pnl)}
        )
    history: dict[date, store.DayRecord] = {
        day: record.model_copy(
            update={"realised": one(f"daily_history[{day.isoformat()}].realised", record.realised)}
        )
        for day, record in state.daily_history.items()
    }
    lifetime = state.lifetime_realised
    if lifetime is not None:
        lifetime = one("lifetime_realised", lifetime)

    if refusals:
        return state, [], refusals
    updated = state.model_copy(
        update={"ledger": ledger, "daily_history": history, "lifetime_realised": lifetime}
    )
    return updated, changes, []


def _append_log(*, at: datetime, path: Path, changed: int, before: str, after: str) -> str:
    """Append one line to ``logs/normalize.log`` and return it."""
    line = (
        f"{at.isoformat()} normalised store={path} values_changed={changed} "
        f"store_sha256_before={before} store_sha256_after={after}"
    )
    NORMALIZE_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(NORMALIZE_LOG_PATH, "a", encoding="utf-8", newline="") as handle:
        handle.write(line + "\n")
    return line


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Normalise the ledger's money exponents in the bot's store to eight decimal "
        "places, losslessly or not at all. Run from the deployment clone's root, with the bot "
        "stopped. Without --apply it only prints what it would change.",
    )
    parser.add_argument(
        "--store",
        type=Path,
        default=store.DEFAULT_STORE_PATH,
        help=f"the store file (default: {store.DEFAULT_STORE_PATH})",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="write the normalised store; without it nothing is written",
    )
    return parser


def main(argv: list[str] | None = None, *, clock: Callable[[], datetime] = utc_now) -> int:
    """Exit 0 on a normalisation, a preview or nothing to do; 1 on a refusal; 3 on a log failure."""
    args = _build_parser().parse_args(argv)
    path: Path = args.store

    try:
        with acquire(DEFAULT_LOCK_PATH):
            return _normalise(path, args.apply, clock)
    except InstanceLockedError as exc:
        print(f"REFUSED: the bot's instance lock is held, so nothing was changed.\n{exc}")
        return 1


def _normalise(path: Path, apply: bool, clock: Callable[[], datetime]) -> int:
    try:
        state = store.load(path)
    except store.StoreCorruptError as exc:
        print(f"REFUSED: the store is corrupt, so nothing was changed.\n{exc}")
        return 1
    if state is None:
        print(f"REFUSED: there is no store at {path}. Run this from the clone's root.")
        return 1
    file_schema = json.loads(path.read_text(encoding="utf-8")).get("schema")
    if file_schema != store.SCHEMA_VERSION:
        print(
            f"REFUSED: the store is at schema {file_schema} and this build writes schema "
            f"{store.SCHEMA_VERSION}, so saving it would upgrade it as well. Nothing was changed."
        )
        return 1

    updated, changes, refusals = normalise_state(state)
    if refusals:
        for refusal in refusals:
            print(f"  cannot normalise {refusal.where} = {refusal.value}")
        print(
            f"REFUSED: {len(refusals)} value(s) cannot be brought to eight decimal places "
            "without losing a digit. Nothing was changed."
        )
        return 1

    before = _sha256(path)
    if not changes:
        print("NOTHING TO NORMALISE: every ledger figure is at eight decimal places or coarser.")
        print(f"store_sha256={before}")
        return 0

    for change in changes:
        print(f"  {change.where}: {change.before} -> {change.after}")
    if not apply:
        print(
            f"PREVIEW: {len(changes)} value(s) would change; nothing was written. "
            f"Re-run with --apply. store_sha256_before={before}"
        )
        return 0

    store.save(updated, path)
    after = _sha256(path)
    try:
        line = _append_log(at=clock(), path=path, changed=len(changes), before=before, after=after)
    except OSError as exc:
        print(
            f"NORMALISED {len(changes)} value(s), BUT the log could not be written ({exc}). "
            f"Record this by hand: before={before} after={after}"
        )
        return 3
    print(f"NORMALISED {len(changes)} value(s).\n{line}")
    return 0


if __name__ == "__main__":  # pragma: no cover - CLI entry point
    raise SystemExit(main())
