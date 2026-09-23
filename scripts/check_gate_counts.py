#!/usr/bin/env python
"""Do the hand-maintained gate-count sites agree with a gate run?

**IT NEVER LOOKS AT A BARE DIGIT.** Every site is matched on the STRUCTURE
around the number -- "N files already formatted", "no issues found in N source
files", "N passed, M skipped", and the two gate-scope table rows. A coincidental
digit therefore cannot be mistaken for a count site, and this tool demands no
edit to one: MEASURED, none of ``476`` inside a CRLF byte count, ``+74.11`` in a
money bound, or a Q-C ``:118`` line citation matches any pattern here.
**The exclusion is structural. There is no skip-list, and therefore no new
hand-maintained site of the kind this exists to remove.**

**WHAT IT CANNOT DO, PRINTED EVERY RUN.** Four of the nineteen gate-figure
occurrences are bare digits in prose that no structure separates from a
coincidence. This claims fifteen and lists the rest as REVIEW with their text,
so the hand-maintained half stays VISIBLE. A tool printing a clean run while
four sites went unchecked would be worse than no tool.

**THE RESIDUAL HOLE, STATED RATHER THAN LEFT TO BE FOUND.** A bare prose site
carrying a STALE figure matches neither the structural patterns nor the
expected-token audit, so it is invisible to both tiers and visible only to a
human reading the REVIEW lines.

**THE FIGURES ARE ARGUMENTS, NOT A GATE RUN.** That keeps this pure and
testable without a two-minute gate, at the cost that it verifies the sites
against a STATED triple rather than against the truth. The triple is echoed in
the header, where a wrong number is visible beside the sites it blessed.

**THE DERIVED FIGURE IS DISCRIMINATED BY ITS OWN SKIP COUNT.** ``CLAUDE.md``
holds that only the credentialed run is measured and that the uncredentialed
pair is that run minus the credential-gated integration tests. A pytest site is
classified by the skip count it carries, so a site promoting the derivation to a
measurement mismatches rather than passing quietly.
"""

from __future__ import annotations

import argparse
import re
from dataclasses import dataclass
from pathlib import Path

#: Resolved from this file rather than the process working directory, for the
#: reason ``scripts/check_findings.py`` states: ``tests/conftest.py`` chdirs
#: every non-integration test into a ``tmp_path``, so a relative default would
#: read a document that is not there.
_ROOT = Path(__file__).resolve().parents[1]
_DOCUMENTS: tuple[Path, ...] = (_ROOT / "CLAUDE.md", _ROOT / "README.md")

_FORMAT_OUTPUT = re.compile(r"(\d+) files already formatted")
_FORMAT_ROW = re.compile(r"^\|.*ruff format --check.*\|\s*(\d+)\s*\|$")
_MYPY_OUTPUT = re.compile(r"no issues found in (\d+) source files")
_MYPY_ROW = re.compile(r"^\|\s*`mypy`.*\|\s*(\d+)\s*\|$")
_PYTEST = re.compile(r"(\d+) passed, (\d+) skipped")

_KIND_FORMAT = "ruff format"
_KIND_MYPY = "mypy"
_KIND_MEASURED = "pytest (measured, credentialed)"
_KIND_DERIVED = "pytest (DERIVED, uncredentialed)"
_KIND_UNRECOGNISED = "pytest (UNRECOGNISED skip count)"


@dataclass(frozen=True)
class Expected:
    """The figures a gate run produced, supplied by the caller.

    ``credential_gated`` is the number of ``skipif(not HAS_CREDENTIALS)``
    integration tests. It is an argument with no default because ``CLAUDE.md``
    re-counts it at rotation rather than carrying it.
    """

    ruff_format: int
    mypy: int
    pytest_passed: int
    pytest_skipped: int
    credential_gated: int

    @property
    def derived_passed(self) -> int:
        """The uncredentialed passed figure. DERIVED, never observed here."""
        return self.pytest_passed - self.credential_gated

    @property
    def derived_skipped(self) -> int:
        """The uncredentialed skipped figure. DERIVED, never observed here."""
        return self.pytest_skipped + self.credential_gated


@dataclass(frozen=True)
class Site:
    """One structurally identified count site and its verdict."""

    path: str
    line: int
    kind: str
    observed: str
    wanted: str

    @property
    def ok(self) -> bool:
        return self.observed == self.wanted


@dataclass(frozen=True)
class Unclaimed:
    """A line carrying more gate-figure tokens than any pattern claimed."""

    path: str
    line: int
    text: str
    tokens: int
    claimed: int


def _token_count(text: str, expected: Expected) -> int:
    """How many WORD-BOUNDED gate figures this line carries.

    The boundaries are what exclude the coincidental set: ``476`` does not
    match ``\\b76\\b`` because ``4`` is a word character.
    """
    wanted = (
        expected.ruff_format,
        expected.mypy,
        expected.pytest_passed,
        expected.derived_passed,
    )
    return sum(len(re.findall(rf"\b{value}\b", text)) for value in wanted)


def classify(path: str, line: int, text: str, expected: Expected) -> list[Site]:
    """Every structurally identified site on one line."""
    sites: list[Site] = []
    for pattern, kind, wanted in (
        (_FORMAT_OUTPUT, _KIND_FORMAT, expected.ruff_format),
        (_FORMAT_ROW, _KIND_FORMAT, expected.ruff_format),
        (_MYPY_OUTPUT, _KIND_MYPY, expected.mypy),
        (_MYPY_ROW, _KIND_MYPY, expected.mypy),
    ):
        for found in pattern.finditer(text):
            sites.append(Site(path, line, kind, found.group(1), str(wanted)))
    for found in _PYTEST.finditer(text):
        passed, skipped = found.group(1), found.group(2)
        if skipped == str(expected.pytest_skipped):
            sites.append(Site(path, line, _KIND_MEASURED, passed, str(expected.pytest_passed)))
        elif skipped == str(expected.derived_skipped):
            sites.append(Site(path, line, _KIND_DERIVED, passed, str(expected.derived_passed)))
        else:
            sites.append(Site(path, line, _KIND_UNRECOGNISED, f"{passed}/{skipped}", "?"))
    return sites


def audit(
    expected: Expected, documents: tuple[Path, ...] = _DOCUMENTS
) -> tuple[list[Site], list[Unclaimed]]:
    """Every structural site, and every gate-figure token no pattern claimed."""
    sites: list[Site] = []
    unclaimed: list[Unclaimed] = []
    for document in documents:
        lines = document.read_text(encoding="utf-8").splitlines()
        for number, text in enumerate(lines, start=1):
            found = classify(str(document), number, text, expected)
            sites.extend(found)
            tokens = _token_count(text, expected)
            if tokens > len(found):
                unclaimed.append(Unclaimed(str(document), number, text.strip(), tokens, len(found)))
    return sites, unclaimed


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="check_gate_counts.py",
        description="Verify the hand-maintained gate-count sites against a gate run.",
    )
    parser.add_argument("--ruff-format", type=int, required=True)
    parser.add_argument("--mypy", type=int, required=True)
    parser.add_argument("--pytest-passed", type=int, required=True)
    parser.add_argument("--pytest-skipped", type=int, required=True)
    parser.add_argument("--credential-gated", type=int, required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    expected = Expected(
        ruff_format=args.ruff_format,
        mypy=args.mypy,
        pytest_passed=args.pytest_passed,
        pytest_skipped=args.pytest_skipped,
        credential_gated=args.credential_gated,
    )
    sites, unclaimed = audit(expected)

    print(f"{'=' * 74}\nWHAT WAS MEASURED\n{'=' * 74}")
    print(f"  documents        : {', '.join(str(d) for d in _DOCUMENTS)}")
    print(f"  ruff format      : {expected.ruff_format}")
    print(f"  mypy             : {expected.mypy}")
    print(
        f"  pytest MEASURED  : {expected.pytest_passed} passed, {expected.pytest_skipped} skipped"
    )
    print(
        f"  pytest DERIVED   : {expected.derived_passed} passed, "
        f"{expected.derived_skipped} skipped "
        f"({expected.pytest_passed} - {expected.credential_gated} credential-gated)"
    )
    print(f"  structural sites : {len(sites)}")

    print(f"\n{'=' * 74}\nSITES\n{'=' * 74}")
    for site in sorted(sites, key=lambda s: (s.path, s.line)):
        mark = "ok " if site.ok else "BAD"
        print(f"  {mark} {site.path}:{site.line:<5} {site.kind:<32} {site.observed}")

    print(f"\n{'=' * 74}\nREVIEW -- gate-figure tokens no pattern claimed\n{'=' * 74}")
    if not unclaimed:
        print("  none")
    for item in unclaimed:
        print(f"  {item.path}:{item.line:<5} {item.tokens - item.claimed} unclaimed")
        print(f"      {item.text[:96]}")
    print("\n  These are bare digits in prose. No structure separates them from a")
    print("  coincidence, so they are LISTED rather than verified. They remain")
    print("  hand-maintained and this tool does not check them.")

    bad = [site for site in sites if not site.ok]
    if not bad:
        print(f"\nOK: {len(sites)} structural site(s) agree; {len(unclaimed)} line(s) for review")
        return 0
    print(f"\nEXIT 1: {len(bad)} structural site(s) disagree with the figures supplied.")
    return 1


if __name__ == "__main__":  # pragma: no cover - CLI entry point
    raise SystemExit(main())
