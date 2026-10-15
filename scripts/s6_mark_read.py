"""S6 O7: mark each candidate's entry ``read``, from its three out-of-sample records (R-CP).

``python scripts/s6_mark_read.py --backtests DIR [--protocol FILE] [--entries-dir DIR] [--entry ID ...] [--dry-run]``

Run from the out-of-sample clone after O6, with that clone's own interpreter. It reads every ``run.json`` under
``--backtests`` through the evidence door, finds each candidate entry's three out-of-sample records, verifies them
against the entry (candidate digest, protocol digest, the declared out-of-sample window, exactly one record at each
declared arm and nothing else), and rewrites the entry as ``status`` ``read`` with, per arm, the run directory and
the SHA-256 of its ``run.json``. See :mod:`trading_bot.backtesting.readmark` for what is refused.

**All or none.** Every entry is verified and every new file built before anything is written, so one refusal leaves
every entry as it was. It refuses an entry already read (use ``--entry`` to mark the rest), a ``run.json`` that fails
the door, and a record set other than exactly the declared arms. Nothing is committed or pushed: the next step is the
owner's (``git add docs/research/entries``, commit, push, rebuild, ``s7_gate.py``). ``--dry-run`` verifies and prints
and writes nothing. Exit status: 0 done; 2 refused. Output is ASCII.
"""

from __future__ import annotations

import argparse
import os
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Final

from trading_bot.backtesting import readmark
from trading_bot.backtesting.protocol import (
    PROTOCOL_PATH,
    ProtocolError,
    parse_entry,
    parse_protocol,
)
from trading_bot.core.exceptions import TradingBotError

__all__ = ["main"]

EXIT_REFUSED: Final = 2


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="s6_mark_read.py",
        description="Mark candidate entries read from their out-of-sample records.",
    )
    parser.add_argument(
        "--backtests", required=True, type=Path, help="the clone's backtests directory"
    )
    parser.add_argument("--protocol", type=Path, default=PROTOCOL_PATH, help="the protocol file")
    parser.add_argument("--entries-dir", type=Path, default=None, help="the entries directory")
    parser.add_argument("--entry", action="append", default=None, help="mark only this entry id")
    parser.add_argument("--dry-run", action="store_true", help="verify and print; write nothing")
    return parser


def _refuse(message: str) -> int:
    print(f"REFUSED: {message}", file=sys.stderr)
    return EXIT_REFUSED


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    entries_dir: Path = (
        args.entries_dir if args.entries_dir is not None else args.protocol.parent / "entries"
    )
    try:
        protocol = parse_protocol(args.protocol.read_text(encoding="utf-8"))
        files = [
            readmark.EntryFile(p.name, p.read_text(encoding="utf-8"))
            for p in sorted(entries_dir.glob("*.json"))
        ]
        parsed = [parse_entry(f.text) for f in files]
    except (OSError, ProtocolError) as exc:
        return _refuse(f"the protocol or the entries cannot be used: {exc}")
    if not args.backtests.is_dir():
        return _refuse(f"{args.backtests} is not a directory")
    known = frozenset(e.id for e in parsed)
    wanted = None if args.entry is None else set(args.entry)
    if wanted is not None and sorted(wanted - known):
        return _refuse(f"no such entry: {', '.join(sorted(wanted - known))}")
    targets = [
        f
        for f, e in zip(files, parsed, strict=True)
        if e.kind == "candidate" and (wanted is None or e.id in wanted)
    ]
    if not targets:
        return _refuse("no candidate entry to mark")
    try:
        records = readmark.read_records(args.backtests)
        markings = readmark.plan(targets, records, protocol, known_ids=known)
    except TradingBotError as exc:
        return _refuse(str(exc))
    for marking in markings:
        print(f"entry {marking.entry_id}: {'would be marked' if args.dry_run else 'marked'} read")
        for arm, run, digest in marking.records:
            print(f"  arm {arm:<5} {run} record sha256 {digest}")
    if args.dry_run:
        print("dry run: nothing was written")
        return 0
    try:
        for marking in markings:
            target = entries_dir / marking.name
            temporary = target.with_name(target.name + ".tmp")
            temporary.write_bytes(marking.data)
            os.replace(temporary, target)
    except OSError as exc:
        return _refuse(
            f"cannot write: {exc}; entries already replaced are listed above, check git status"
        )
    for marking in markings:
        written = parse_entry((entries_dir / marking.name).read_text(encoding="utf-8"))
        if written.status != "read":  # pragma: no cover - a self-check of the write just made
            return _refuse(f"{marking.name} did not read back as read")
    print(
        "next: git add docs/research/entries; commit; push; rebuild the clone; scripts/s7_gate.py"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
