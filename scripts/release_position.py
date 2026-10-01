#!/usr/bin/env python
"""Release one symbol's records from the bot's store -- M5l's C34, ruled at P83.

**WHAT IT IS FOR.** P-3k keeps a record per open position on disk, and a boot
that cannot resolve one refuses, or holds it with no ``Position`` (Q5(b)). The
only way out of that state is for an operator to resolve the position at the
venue and then remove its record, and until this tool the only way to remove it
was to edit ``data/state.json`` by hand (``M5l-125``). This is that removal,
done through the store's own ``load`` and ``save`` so the schema check and the
atomic write apply.

**RUN IT FROM A DEPLOYMENT CLONE'S ROOT**, where ``data/state.json`` and
``logs/`` are the ones the bot reads. ``--store`` names another file; the lock
and the release log stay relative to the working directory.

**IT REFUSES WHILE THE BOT RUNS.** It takes the same non-blocking instance lock
the bot takes, holds it for the whole operation, and releases it on exit, so
the bot cannot boot between the operator's confirmation and the write.

**IT NEVER WRITES TO THE VENUE.** ``--preview`` reads: the order lists, the legs
of the records' lists, the close's sell, the balances and the symbol's filters,
and prints what the boot would decide with ``execution.restoration``'s own
``reads_needed`` and ``classify``. A read that fails prints ``preview
unavailable`` and the tool goes on, because a release is exactly what an
operator needs when the venue cannot be read.

**IT REMOVES ONLY THE NAMED SYMBOL'S RECORDS** -- the position record and any
pending placement or close -- and keeps every other record and the ledger,
history and lifetime total as they were. The operator must type the symbol
exactly; anything else aborts with nothing written. One line is appended to
``logs/release.log`` carrying the store's SHA-256 before and after.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import assert_never

from trading_bot.core.exceptions import OrderNotFoundError, TradingBotError
from trading_bot.core.interfaces import ExchangeClient
from trading_bot.core.models import Order
from trading_bot.engine.modes import _restore_pending
from trading_bot.exchange.ids import list_client_order_id
from trading_bot.execution.executor import PendingClose, PendingPlacement
from trading_bot.execution.restoration import (
    BookExit,
    Decision,
    DropExpired,
    DropNotPlaced,
    Gone,
    RefuseBoot,
    Restore,
    RestoreAndClose,
    classify,
    close_sell_id,
    reads_needed,
)
from trading_bot.persistence import store
from trading_bot.utils.helpers import utc_now
from trading_bot.utils.instance_lock import DEFAULT_LOCK_PATH, InstanceLockedError, acquire

#: Appended to, never rewritten. Relative to the working directory, like the
#: store and the lock, so it lands beside the clone's own logs.
RELEASE_LOG_PATH = Path("logs/release.log")

#: The command the bot's own messages quote, minus the symbol. A test pins that
#: those messages and this tool agree on it.
COMMAND = "python scripts/release_position.py --symbol"

#: One bound for every preview read, at one attempt, like a boot read.
_PREVIEW_TIMEOUT_S = 10.0

ClientFactory = Callable[[], Awaitable[ExchangeClient]]


@dataclass(frozen=True)
class Found:
    """One stored record for the symbol, and the list id our seeds derive."""

    kind: str
    record: store.PositionRecord | store.PendingRecord | store.PendingCloseRecord
    list_id: str


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def find_records(state: store.PersistedState, symbol: str) -> list[Found]:
    """Every record for ``symbol``: the position, then pending placements and closes."""
    records: list[store.PositionRecord | store.PendingRecord | store.PendingCloseRecord] = [
        *(r for r in state.positions if r.symbol == symbol),
        *(r for r in state.pending if r.symbol == symbol),
    ]
    return [
        Found(
            kind=record.kind,
            record=record,
            list_id=list_client_order_id(
                record.symbol, record.entry_bar_time, generation=record.generation
            ),
        )
        for record in records
    ]


def remove_records(state: store.PersistedState, symbol: str) -> store.PersistedState:
    """``state`` without ``symbol``'s records. The ledger, history and lifetime stay."""
    return state.model_copy(
        update={
            "pending": tuple(r for r in state.pending if r.symbol != symbol),
            "positions": tuple(r for r in state.positions if r.symbol != symbol),
        }
    )


def _describe(decision: Decision) -> str:
    """One line for what the boot would do with this record."""
    match decision:
        case Restore():
            return "Restore: the list is live, so the boot would restore the position."
        case BookExit():
            leg = "its close sell" if decision.leg is None else f"the {decision.leg.value} leg"
            return f"BookExit: {leg} filled, so the boot would book the exit, ledger only."
        case RestoreAndClose():
            return (
                "RestoreAndClose: protection is gone and the base is held, so the boot would "
                "restore the position and the BOT would then SELL it on its first candle."
            )
        case Gone():
            return "Gone: protection is gone and so is the base; the boot would drop it unbooked."
        case DropExpired():
            return "DropExpired: the entry expired with nothing executed; the boot would drop it."
        case DropNotPlaced():
            return "DropNotPlaced: no list carries its id; the boot would drop it."
        case RefuseBoot():
            return f"RefuseBoot: {decision.reason}"
        case _:
            assert_never(decision)


async def _preview(client: ExchangeClient, symbol: str, state: store.PersistedState) -> list[str]:
    """What the boot would decide for ``symbol``. GET calls only; may raise ``TradingBotError``."""
    only = state.model_copy(
        update={
            "pending": tuple(r for r in state.pending if r.symbol == symbol),
            "positions": tuple(r for r in state.positions if r.symbol == symbol),
        }
    )
    restored = _restore_pending(only)
    placements = [r for r in restored if isinstance(r, PendingPlacement)]
    closes = [r for r in restored if isinstance(r, PendingClose)]
    records = list(only.positions)

    lines: list[str] = []
    if not records and not placements:
        return [
            "no position record or pending placement: a pending close alone is not decided "
            "at boot; the first candle releases it."
        ]

    order_lists = await client.get_all_order_lists()
    plan = reads_needed(records, placements, order_lists, closes)
    orders = [
        await client.get_order(symbol, order_id=order_id, timeout_s=_PREVIEW_TIMEOUT_S, attempts=1)
        for order_id in plan.order_ids
    ]
    sells: dict[str, Order | None] = {}
    for sell_symbol, sell_id in plan.sell_reads:
        try:
            sells[sell_id] = await client.get_order(
                sell_symbol, client_order_id=sell_id, timeout_s=_PREVIEW_TIMEOUT_S, attempts=1
            )
        except OrderNotFoundError:
            sells[sell_id] = None
    balances = await client.get_balances()
    filters = {symbol: await client.get_symbol_info(symbol)}

    decisions = classify(
        records, placements, order_lists, orders, balances, filters, closes=closes, sells=sells
    )
    for close in closes:
        lines.append(f"close sell id {close_sell_id(close)}: read by the boot beside the record.")
    lines.extend(_describe(decision) for decision in decisions)
    return lines


async def _default_client() -> ExchangeClient:
    """The bot's own client, built from the same settings a boot reads."""
    from trading_bot.config.settings import get_settings
    from trading_bot.exchange import BinanceClient

    settings = get_settings(None)
    settings.binance_credentials()  # refuses LIVE and a missing key before any socket
    return await BinanceClient.create(settings)


async def _run_preview(
    client_factory: ClientFactory, symbol: str, state: store.PersistedState
) -> list[str]:
    client: ExchangeClient | None = None
    try:
        client = await client_factory()
        return await _preview(client, symbol, state)
    except TradingBotError as exc:
        return [f"preview unavailable: {type(exc).__name__}: {exc}"]
    finally:
        if client is not None:
            await client.close()


def _append_release_log(
    *, at: datetime, symbol: str, removed: Sequence[Found], before: str, after: str
) -> str:
    """Append one line to ``logs/release.log`` and return it."""
    items = ",".join(f"{item.kind}:{item.list_id}" for item in removed)
    line = (
        f"{at.isoformat()} released symbol={symbol} removed=[{items}] "
        f"store_sha256_before={before} store_sha256_after={after}"
    )
    RELEASE_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(RELEASE_LOG_PATH, "a", encoding="utf-8", newline="") as handle:
        handle.write(line + "\n")
    return line


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Release one symbol's records from the bot's store. Run from the "
        "deployment clone's root, with the bot stopped.",
    )
    parser.add_argument("--symbol", required=True, help="the symbol whose records to release")
    parser.add_argument(
        "--store",
        type=Path,
        default=store.DEFAULT_STORE_PATH,
        help=f"the store file (default: {store.DEFAULT_STORE_PATH})",
    )
    parser.add_argument(
        "--preview",
        action="store_true",
        help="read the venue (GET only) and print what the boot would decide",
    )
    return parser


def main(
    argv: list[str] | None = None,
    *,
    input_fn: Callable[[str], str] = input,
    client_factory: ClientFactory = _default_client,
    clock: Callable[[], datetime] = utc_now,
) -> int:
    """Exit 0 on a release; 1 on any refusal or abort, with nothing written."""
    args = _build_parser().parse_args(argv)
    symbol: str = args.symbol
    path: Path = args.store

    try:
        with acquire(DEFAULT_LOCK_PATH):
            return _release(symbol, path, args.preview, input_fn, client_factory, clock)
    except InstanceLockedError as exc:
        print(f"REFUSED: the bot's instance lock is held, so nothing was changed.\n{exc}")
        return 1


def _release(
    symbol: str,
    path: Path,
    preview: bool,
    input_fn: Callable[[str], str],
    client_factory: ClientFactory,
    clock: Callable[[], datetime],
) -> int:
    try:
        state = store.load(path)
    except store.StoreCorruptError as exc:
        print(f"REFUSED: the store is corrupt, so nothing was changed.\n{exc}")
        return 1
    if state is None:
        print(f"REFUSED: there is no store at {path}. Run this from the clone's root.")
        return 1

    found = find_records(state, symbol)
    if not found:
        print(f"REFUSED: the store at {path} holds no record for {symbol}. Nothing was changed.")
        return 1

    for item in found:
        print(f"--- {item.kind} record, our list id {item.list_id} ---")
        print(item.record.model_dump_json(indent=2))

    if preview:
        print("--- preview: GET-only reads; nothing is written ---")
        for line in asyncio.run(_run_preview(client_factory, symbol, state)):
            print(line)

    try:
        answer = input_fn(f"Type the symbol {symbol} to release these {len(found)} record(s): ")
    except EOFError:
        answer = ""
    if answer != symbol:
        print("ABORTED: the symbol was not typed exactly. Nothing was changed.")
        return 1

    before = _sha256(path)
    store.save(remove_records(state, symbol), path)
    after = _sha256(path)
    try:
        line = _append_release_log(
            at=clock(), symbol=symbol, removed=found, before=before, after=after
        )
    except OSError as exc:
        print(
            f"RELEASED {len(found)} record(s) for {symbol}, BUT the release log could not be "
            f"written ({exc}). Record this by hand: before={before} after={after}"
        )
        return 3
    print(f"RELEASED {len(found)} record(s) for {symbol}.\n{line}")
    return 0


if __name__ == "__main__":  # pragma: no cover - CLI entry point
    raise SystemExit(main())
