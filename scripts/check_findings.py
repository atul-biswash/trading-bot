#!/usr/bin/env python
"""The findings extractor ``CLAUDE.md`` documents, as a tracked script.

**IT IS A TRANSCRIPTION, NOT A REDESIGN.** ``CLAUDE.md`` carries the extractor
as a PowerShell function inside a fence inside a blockquote -- prose that must
be retyped by hand before it can run, which is ``M5k-001``. The questions here
are that function's questions and the patterns are its patterns.

**TWO DEPARTURES, both deliberate.** PowerShell's ``-match`` and
``Select-String`` are case-INSENSITIVE by default, so the documented function
accepts ``- m5k-001 -- `` as a declaration and cites ``M5K-002``; this is
case-SENSITIVE, because every id on disk is uppercase and a lowercase one is a
typo worth surfacing. And every ``git`` call forces ``encoding="utf-8"`` rather
than the console codepage, which is the defect ``21ad51e`` fixed elsewhere in
this tree and which bit an untracked instrument at ``M5k-010``.

**IT PRINTS WHAT IT MEASURED, NOT ONLY WHAT IT FOUND.** The patterns, the range
resolved to both endpoint SHAs, and the commit count scanned are printed before
any total. An empty declared set on an empty range prints ``commits scanned:
0``; an empty declared set from a wrong pattern prints a non-zero scan beside
it. A check whose failure path prints success is not a check.

**CITED-NOT-DECLARED IS REPORTED AND NEVER FAILED ON.** ``M5i-068``,
``M5i-071`` and ``M5i-073`` are reserved by ruling: cited in the tree and
declared nowhere, deliberately. A tool that failed on them would be demanding
that they be invented. The exit code is driven by duplicates, gaps and
blockless commits only.
"""

from __future__ import annotations

import argparse
import re
import subprocess
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

#: Every git call names this explicitly, so the tool does not depend on the
#: process working directory. ``tests/conftest.py`` chdirs every non-integration
#: test into a ``tmp_path`` so a relative ``./.env`` is never read, and a tool
#: reading the ambient cwd would run git outside the repository and report a
#: resolution failure that has nothing to do with its argument.
_ROOT = Path(__file__).resolve().parents[1]

_BLOCK_HEADER = re.compile(r"^Findings:\s*$|^Findings: none\s*$")

#: Separates one commit from the next in a single ``git log`` read, so the
#: range costs four subprocess calls rather than three per commit.
_RECORD = "@@@CHECK-FINDINGS-RECORD@@@"


@dataclass(frozen=True)
class Commit:
    """One commit's identity and the two message forms the patterns read.

    ``message`` is ``%B`` and is what citations are counted over; ``body`` is
    ``%b`` and is what declarations and the block header are matched against.
    The split is the documented function's and is preserved exactly.
    """

    sha: str
    message: str
    body: str


@dataclass(frozen=True)
class Findings:
    """What one range says about one milestone's namespace."""

    commits: int
    declared: tuple[str, ...]
    distinct: tuple[str, ...]
    duplicates: tuple[str, ...]
    gaps: tuple[int, ...]
    cited_not_declared: tuple[str, ...]
    blockless: tuple[str, ...]

    @property
    def maximum(self) -> int:
        """The highest declared number, or zero when nothing is declared."""
        if not self.distinct:
            return 0
        return max(int(name[-3:]) for name in self.distinct)

    @property
    def failed(self) -> bool:
        """Whether this range is defective.

        ``cited_not_declared`` is deliberately absent: the reserved block is
        not a defect and a tool that failed on it would be wrong.
        """
        return bool(self.duplicates or self.gaps or self.blockless)


def citation_pattern(milestone: str) -> str:
    """The pattern citations are counted with, as the documented function has it."""
    return rf"{re.escape(milestone)}-\d{{3}}"


def declaration_pattern(milestone: str) -> str:
    """The pattern a declaration LINE must match, anchored as the block requires."""
    return rf"^- ({re.escape(milestone)}-\d{{3}}) -- "


def scan(commits: Sequence[Commit], *, milestone: str) -> Findings:
    """Answer the documented extractor's questions over already-read commits.

    Pure, and that is what lets the gap, duplicate and blockless cases be
    tested without a repository at all.
    """
    cited = re.compile(citation_pattern(milestone))
    declared_re = re.compile(declaration_pattern(milestone))

    declared: list[str] = []
    seen: set[str] = set()
    blockless: list[str] = []
    for commit in commits:
        lines = commit.body.splitlines()
        for line in lines:
            found = declared_re.match(line)
            if found is not None:
                declared.append(found.group(1))
        seen.update(cited.findall(commit.message))
        if not any(_BLOCK_HEADER.match(line) for line in lines):
            blockless.append(commit.sha)

    distinct = tuple(sorted(set(declared)))
    duplicates = tuple(sorted(name for name, n in Counter(declared).items() if n > 1))
    numbers = sorted(int(name[-3:]) for name in distinct)
    gaps = tuple(n for n in range(1, numbers[-1] + 1) if n not in numbers) if numbers else ()
    undeclared = tuple(sorted(name for name in seen if name not in set(distinct)))
    return Findings(
        commits=len(commits),
        declared=tuple(declared),
        distinct=distinct,
        duplicates=duplicates,
        gaps=gaps,
        cited_not_declared=undeclared,
        blockless=tuple(blockless),
    )


def _git(*args: str) -> str:
    """Run one git command against this checkout, decoded as UTF-8.

    ``-C`` rather than the ambient cwd, and UTF-8 rather than the console
    codepage: the first is why this works under a chdir-ing fixture, the second
    is the defect ``21ad51e`` fixed elsewhere in this tree.
    """
    return subprocess.run(
        ["git", "-C", str(_ROOT), "--no-pager", *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=True,
    ).stdout


def _read(spec: str, fmt: str) -> dict[str, str]:
    """One ``git log`` read of the whole range, keyed by abbreviated sha."""
    raw = _git("log", spec, f"--format={_RECORD}%h%n{fmt}")
    records: dict[str, str] = {}
    for chunk in raw.split(_RECORD):
        if not chunk.strip():
            continue
        sha, _, text = chunk.partition("\n")
        records[sha.strip()] = text
    return records


def read_range(spec: str) -> tuple[str, str, list[Commit]]:
    """Resolve both endpoints and read every commit in the range.

    The endpoints are resolved rather than echoed, so the output names the
    commits actually scanned and an unknown ref is fatal instead of empty.
    """
    left, _, right = spec.partition("..")
    base = _git("rev-parse", f"{left}^{{commit}}").strip()
    head = _git("rev-parse", f"{right or 'HEAD'}^{{commit}}").strip()
    messages = _read(spec, "%B")
    bodies = _read(spec, "%b")
    order = _git("log", spec, "--format=%h").split()
    commits = [
        Commit(sha=sha, message=messages.get(sha, ""), body=bodies.get(sha, "")) for sha in order
    ]
    return base, head, commits


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="check_findings.py",
        description="Audit a milestone's findings namespace over a commit range.",
    )
    parser.add_argument("range", help="a git range, e.g. milestone/M5j..HEAD")
    parser.add_argument("milestone", help="the id prefix, e.g. M5k")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    milestone: str = args.milestone

    try:
        base, head, commits = read_range(args.range)
    except subprocess.CalledProcessError as exc:
        print(f"REFUSED: {args.range} did not resolve: {exc.stderr.strip()}")
        return 2

    report = scan(commits, milestone=milestone)

    print(f"{'=' * 74}\nWHAT WAS MEASURED\n{'=' * 74}")
    print(f"  range argument     : {args.range}")
    print(f"  resolved base      : {base}")
    print(f"  resolved head      : {head}")
    print(f"  commits scanned    : {report.commits}")
    print(f"  citation pattern   : {citation_pattern(milestone)}")
    print(f"  declaration pattern: {declaration_pattern(milestone)}")
    print("  matching is CASE-SENSITIVE; the documented PowerShell is not")

    print(f"\n{'=' * 74}\n{milestone} NAMESPACE\n{'=' * 74}")
    print(f"  declared           : {len(report.declared)}")
    print(f"  distinct           : {len(report.distinct)}")
    print(f"  max                : {report.maximum}")
    print(f"  duplicates         : [{','.join(report.duplicates)}]")
    print(f"  gaps               : [{','.join(str(n) for n in report.gaps)}]")
    print(f"  cited-not-declared : [{','.join(report.cited_not_declared)}]")
    print(f"  blockless commits  : [{','.join(report.blockless)}]")

    if report.cited_not_declared:
        print("\n  NOTE: cited-not-declared is REPORTED, never failed on. The M5i")
        print("  reserved block is deliberate and inventing declarations would be wrong.")

    if not report.failed:
        print(
            f"\nOK: {report.commits} commit(s) scanned, no duplicate, no gap, every block present"
        )
        return 0
    print("\nEXIT 1: the namespace is not contiguous, or a commit carries no findings block.")
    return 1


if __name__ == "__main__":  # pragma: no cover - CLI entry point
    raise SystemExit(main())
