"""S7: judge every candidate that has been read out of sample, by the ruled thresholds.

``python scripts/s7_gate.py --backtests DIR [--protocol FILE] [--entries-dir DIR] [--entry ID ...]``

READ ONLY. It reads the committed entries of the candidates whose status is ``read``, then each entry's
three out-of-sample records through the evidence door, checking each against the entry (the run directory
and the ``run.json`` SHA-256 the entry committed), and prints, per candidate, the figures of all three arms,
the gate arm's five tests against their thresholds, and PASS or FAIL. See :mod:`trading_bot.backtesting.gate`
for what passes and what is refused.

**A refusal prints no verdict for anyone.** If any record or entry is refused, the command prints every
refusal to stderr and exits 2 with nothing on stdout, so a verdict cannot be harvested from the candidates
that happened to be well formed. The exit status of a verdict is 0 whether it is PASS or FAIL: a failing
candidate is an outcome and not an error. ``--entry ID`` (repeatable) restricts the judgement to those
candidates. Output is ASCII.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Final

from trading_bot.backtesting import gate
from trading_bot.backtesting.protocol import PROTOCOL_PATH, ProtocolError, load_entries

__all__ = ["main"]

EXIT_REFUSED: Final = 2


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="s7_gate.py", description="Judge the out-of-sample candidates by S7's thresholds."
    )
    parser.add_argument(
        "--backtests", required=True, type=Path, help="the clone's backtests directory"
    )
    parser.add_argument("--protocol", type=Path, default=PROTOCOL_PATH, help="the protocol file")
    parser.add_argument("--entries-dir", type=Path, default=None, help="the entries directory")
    parser.add_argument("--entry", action="append", default=None, help="judge only this entry id")
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
        rules = gate.parse_gate_rules(args.protocol.read_text(encoding="utf-8"))
        entries = load_entries(entries_dir)
    except (OSError, ProtocolError, gate.GateRulesError) as exc:
        return _refuse(f"the protocol or the entries cannot be used: {exc}")
    if not args.backtests.is_dir():
        return _refuse(f"{args.backtests} is not a directory")
    if args.entry is not None:
        unknown = sorted(set(args.entry) - {e.id for e in entries})
        if unknown:
            return _refuse(f"no such entry: {', '.join(unknown)}")
        entries = tuple(e for e in entries if e.id in set(args.entry))
    refusals: list[str] = []
    results: list[gate.CandidateResult] = []
    pending: list[str] = []
    for entry in entries:
        try:
            report = gate.evaluate([entry], args.backtests, rules)
        except gate.GateRefusedError as exc:
            refusals.append(f"{entry.id}: {exc}")
            continue
        results.extend(report.results)
        pending.extend(report.pending)
    if refusals:
        for line in refusals:
            print(f"REFUSED: {line}", file=sys.stderr)
        return EXIT_REFUSED
    print(gate.render_report(gate.GateReport(rules, tuple(results), tuple(pending))), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
