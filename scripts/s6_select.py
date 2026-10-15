"""S6 selection: read the in-sample sweep, choose one candidate per cell, print the walk-forward report.

``python scripts/s6_select.py --backtests DIR [--out FILE [--entries-dir DIR]]``

READ ONLY ON THE RUNS. It reads every run directory under ``--backtests`` through the evidence door
(R-AR): only an evidence-eligible, guard-decided, in-sample run over exactly ``[2017-08-17, 2024-01-01)`` at
the 1.20% arm is a point run, and every other directory is listed with its reason, never silently dropped. It
reads no out-of-sample record and makes no run.

**It computes nothing over an incomplete sweep.** All 216 declared variants must have a run (R-CG); a
missing variant, or two runs of one variant whose trade logs disagree, is a refusal that says what is missing.

**What it writes, and only when asked.**

* ``--out FILE`` writes the SELECTION FILE: the chosen point per cell with its evidence, every point's
  figures and reasons, the walk-forward report and the skipped directories, as JSON LINES, one record a line
  (R-CU: a line per variant and a line per cell, so that the file commits within the 1,500-line ceiling, and
  changes no pick). It is created exclusively and
  refuses to overwrite, so a selection already made cannot be silently remade. The owner commits it
  UNEDITED with its SHA-256 (PROTOCOL.md section 6 step 6), which this script prints.
* ``--entries-dir DIR`` (with ``--out``) writes one PENDING entry per candidate, bound to the candidate by
  its digest and carrying the selection file's SHA-256. Every path is checked before anything is written,
  so a refusal leaves nothing partial.

Without ``--out`` it prints the report and writes nothing. Exit status: 0 done; 2 refused (the message says
why). Output is ASCII.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Final

from trading_bot.backtesting import selection as sel
from trading_bot.backtesting.protocol import PROTOCOL_PATH, ProtocolError, parse_protocol
from trading_bot.core.exceptions import TradingBotError

__all__ = ["main"]

EXIT_REFUSED: Final = 2


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="s6_select.py",
        description="Select one S6 candidate per cell from the in-sample sweep (PROTOCOL.md section 6).",
    )
    parser.add_argument(
        "--backtests", required=True, type=Path, help="the clone's backtests directory"
    )
    parser.add_argument("--protocol", type=Path, default=PROTOCOL_PATH, help="the protocol file")
    parser.add_argument("--out", type=Path, default=None, help="write the selection file here")
    parser.add_argument(
        "--entries-dir", type=Path, default=None, help="write one pending entry per candidate here"
    )
    return parser


def _entry_bytes(body: dict[str, object]) -> bytes:
    return (json.dumps(body, indent=2) + "\n").encode("ascii")


def _refuse(message: str) -> int:
    print(f"REFUSED: {message}", file=sys.stderr)
    return EXIT_REFUSED


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.entries_dir is not None and args.out is None:
        return _refuse("--entries-dir needs --out: an entry carries the selection file's SHA-256")
    try:
        text = args.protocol.read_text(encoding="utf-8")
        protocol = parse_protocol(text)
        rules = sel.parse_rules(text)
    except (OSError, ProtocolError, sel.SelectionRulesError) as exc:
        return _refuse(f"the protocol cannot be used: {exc}")
    if not args.backtests.is_dir():
        return _refuse(f"{args.backtests} is not a directory")

    directories = sorted(p for p in args.backtests.iterdir() if p.is_dir())
    ledger = sel.reconcile(protocol, [sel.read_run(d, protocol, rules) for d in directories])
    try:
        selection = sel.select(protocol, rules, ledger)
    except sel.SelectionRefusedError as exc:
        for skipped in ledger.skipped:
            print(
                f"SKIPPED {skipped.run}: {skipped.reason.value}: {skipped.detail}", file=sys.stderr
            )
        for variant in ledger.missing[:5]:
            print(f"MISSING {sel.variant_key(variant)}", file=sys.stderr)
        return _refuse(str(exc))

    print(sel.render_report(selection), end="")
    if args.out is None:
        return 0

    document = sel.selection_document(selection)
    data = sel.selection_bytes(document)
    digest = hashlib.sha256(data).hexdigest()
    planned: list[tuple[Path, bytes]] = [(args.out, data)]
    if args.entries_dir is not None:
        for result in selection.candidates:
            body = sel.candidate_entry(result, selection_sha256=digest, arms=protocol.arms)
            planned.append(
                (args.entries_dir / f"{sel.entry_id(result.cell)}.json", _entry_bytes(body))
            )
    existing = [str(path) for path, _ in planned if path.exists()]
    if existing:
        return _refuse(f"will not overwrite: {', '.join(existing)}")
    try:
        if args.entries_dir is not None:
            args.entries_dir.mkdir(parents=True, exist_ok=True)
        args.out.parent.mkdir(parents=True, exist_ok=True)
        for path, content in planned:
            with path.open("xb") as handle:
                handle.write(content)
    except OSError as exc:
        return _refuse(f"cannot write: {exc}")
    print(f"selection file {args.out} sha256 {digest} ({len(data)} bytes)")
    for path, _ in planned[1:]:
        print(f"entry {path}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except TradingBotError as exc:
        raise SystemExit(f"REFUSED: {exc}") from exc
