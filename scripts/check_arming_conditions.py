#!/usr/bin/env python
"""Extract the arming conditions in ``docs/NEXT_MILESTONE.md``, and say what it could not.

**DUAL REGISTER, FAIL-CLOSED. IT EXITS NON-ZERO ON TODAY'S TREE, AND THAT IS
THE TOOL WORKING RATHER THAN FAILING.** The conditions were written as prose
before anything read them mechanically, so their grammar is irregular: measured
on this tree, 22 conditions exist, 16 of them run past the line they begin on,
at least four distinct opening grammars are in use, and two are complete
sentences carrying no backticked symbol at all. An extractor keyed on a symbol
inside a bold span therefore cannot reach every one of them.

**A CHECK WHOSE FAILURE PATH PRINTS SUCCESS IS NOT A CHECK.** The tempting
shape here is to print the conditions that parsed and stop, which reports a
clean run precisely when the parser is at its most broken -- an extractor that
matched nothing at all would print an empty list and exit zero. So this keeps
two registers: PARSED, with the symbols each condition cross-references, and
UNPARSED, with every candidate block that failed extraction and the reason. The
unparsed count is printed on every run INCLUDING when it is zero, and a non-empty
unparsed register exits non-zero.

**WHAT "PARSED" MEANS, stated so the register is readable.** A block parses when
its bold span closes inside the block and that span carries at least one
backticked token. Those tokens are the symbol cross-references. A block whose
bold span never closes, or which names no symbol, is unparsed -- not because it
is a bad condition, but because this parser cannot tell what site it names.

Regularising the prose and widening the parser are both open; this tool exists
to make the gap countable rather than to hide it.
"""

from __future__ import annotations

import argparse
import re
from dataclasses import dataclass
from pathlib import Path

_MARKER = "*Arming condition:*"
_BOLD_SPAN = re.compile(r"\*\*(.+?)\*\*", re.DOTALL)
_BACKTICKED = re.compile(r"`([^`]+)`")
_DEFAULT_DOCUMENT = Path("docs/NEXT_MILESTONE.md")

_REASON_NO_BOLD = "the bold span does not close inside the block"
_REASON_NO_SYMBOL = "the bold span names no backticked symbol"


@dataclass(frozen=True)
class Parsed:
    """A condition the parser could read, with the symbols it names."""

    line: int
    text: str
    symbols: tuple[str, ...]


@dataclass(frozen=True)
class Unparsed:
    """A candidate block the parser could not read, and why."""

    line: int
    text: str
    reason: str


def blocks(lines: list[str]) -> list[tuple[int, str]]:
    """Return each arming-condition block as a one-indexed line number and text.

    A block runs from the marker to the next blank line, which is what makes a
    multi-line condition one candidate rather than several.
    """
    found: list[tuple[int, str]] = []
    index = 0
    while index < len(lines):
        if _MARKER in lines[index]:
            start = index
            collected: list[str] = []
            while index < len(lines) and lines[index].strip():
                collected.append(lines[index].strip())
                index += 1
            found.append((start + 1, " ".join(collected)))
        index += 1
    return found


def classify(line: int, text: str) -> Parsed | Unparsed:
    """Sort one block into the parsed or the unparsed register."""
    span = _BOLD_SPAN.search(text, text.index(_MARKER))
    if span is None:
        return Unparsed(line=line, text=text, reason=_REASON_NO_BOLD)
    symbols = tuple(match.group(1) for match in _BACKTICKED.finditer(span.group(1)))
    if not symbols:
        return Unparsed(line=line, text=text, reason=_REASON_NO_SYMBOL)
    return Parsed(line=line, text=span.group(1), symbols=symbols)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="check_arming_conditions.py",
        description="Register the arming conditions that parse and every one that does not.",
    )
    parser.add_argument(
        "document",
        type=Path,
        nargs="?",
        default=_DEFAULT_DOCUMENT,
        help=f"markdown document to read (default: {_DEFAULT_DOCUMENT})",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    document: Path = args.document

    if not document.is_file():
        print(f"REFUSED: {document} is not a file")
        return 2

    lines = document.read_text(encoding="utf-8").splitlines()
    candidates = blocks(lines)
    parsed: list[Parsed] = []
    unparsed: list[Unparsed] = []
    for line, text in candidates:
        result = classify(line, text)
        if isinstance(result, Parsed):
            parsed.append(result)
        else:
            unparsed.append(result)

    print(f"{'=' * 74}\nPARSED -- conditions this extractor could read\n{'=' * 74}")
    for read in parsed:
        print(f"  line {read.line:<5} symbols: {', '.join(read.symbols)}")
        print(f"    {read.text[:100]}")

    print(f"\n{'=' * 74}\nUNPARSED -- candidates that failed extraction\n{'=' * 74}")
    if not unparsed:
        print("  none")
    for failure in unparsed:
        print(f"  line {failure.line:<5} {failure.reason}")
        print(f"    {failure.text[:100]}")

    print(f"\n{'=' * 74}\nTOTALS\n{'=' * 74}")
    print(f"  candidates : {len(candidates)}")
    print(f"  parsed     : {len(parsed)}")
    print(f"  unparsed   : {len(unparsed)}")

    if unparsed:
        print(
            f"\nEXIT 1: {len(unparsed)} candidate(s) failed extraction. A condition this "
            "parser cannot read is a condition nothing audits, so the run fails rather "
            "than reporting the subset it managed."
        )
        return 1
    return 0


if __name__ == "__main__":  # pragma: no cover - CLI entry point
    raise SystemExit(main())
