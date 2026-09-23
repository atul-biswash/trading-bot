"""Tests for ``scripts/check_findings.py``.

Each test states what it would fail on, because a test whose negation is not
named is one nobody can tell is abstaining. Both halves of expressiveness are
checked per test: whether the INPUT can express the defect, and whether the
ASSERTION reads the thing the defect moves.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

from check_findings import (
    Commit,
    citation_pattern,
    declaration_pattern,
    main,
    read_range,
    scan,
)

_ACCEPTANCE_RANGE = "milestone/M5h..milestone/M5i"


def _commit(sha: str, *, body: str, subject: str = "feat: a change") -> Commit:
    return Commit(sha=sha, message=f"{subject}\n\n{body}", body=body)


def _block(*ids: str) -> str:
    lines = ["Findings:"]
    lines.extend(f"- {name} -- a one line summary. MEASURED." for name in ids)
    return "\n".join(lines) + "\n"


def test_it_reproduces_the_documented_extractor_on_the_m5i_range() -> None:
    """THE ACCEPTANCE TEST. The figures come from an INDEPENDENT source.

    ``docs/PHASE_HISTORY.md`` records "130 findings declared across
    `M5i-001`-`M5i-136`, every commit carrying a block" and states it "matches
    the documented extractor exactly" -- written before this tool existed.
    Disagreement was possible and would have been noticed, so agreement is
    evidence rather than a tautology.

    PINNED AS LITERALS, NOT RECOMPUTED. Recomputing would compare the tool
    against itself, which is the self-comparison `execution/bookability.py`
    warns of: a change would move both sides at once and the pin would be blind
    by construction.

    THE RESERVED BLOCK IS REPORTED AND DOES NOT FAIL. `M5i-068`, `M5i-071` and
    `M5i-073` are cited in the tree and declared nowhere BY RULING.

    EVERY ASSERTION BELOW TRACES TO A RECORD WRITTEN BEFORE THIS TOOL EXISTED,
    and `failed` is deliberately NOT among them. It folds in gap detection, and
    the independent source speaks only to the declaration count -- "130
    findings declared across `M5i-001`-`M5i-136`" IMPLIES a six-id gap rather
    than denying one. Asserting `failed is False` here would have been this
    test asserting an assumption of its author's. The gap set is pinned
    separately, as the discovery it is.

    FAILS ON: reading `%b` where `%B` is wanted or the reverse; dropping the
    `^- ` anchor; changing the digit width; or adding `cited_not_declared` to
    the exit condition.
    """
    try:
        _base, _head, commits = read_range(_ACCEPTANCE_RANGE)
    except subprocess.CalledProcessError:
        pytest.skip(
            "THE ACCEPTANCE TEST DID NOT RUN: scripts/check_findings.py has no "
            f"independent validation in this run. The range {_ACCEPTANCE_RANGE} did not "
            "resolve, so a milestone tag is missing -- a tag is a ref and `git push` does "
            "not carry it. Run `git fetch --tags` and re-run."
        )

    report = scan(commits, milestone="M5i")

    assert report.commits == 16
    assert len(report.declared) == 130
    assert len(report.distinct) == 130
    assert report.cited_not_declared == ("M5i-068", "M5i-071", "M5i-073")
    assert report.duplicates == ()
    assert report.blockless == ()


def test_the_m5i_namespace_carries_a_six_id_gap_and_only_three_are_reserved() -> None:
    """A DISCOVERY, pinned separately from the acceptance test that made it.

    The tool's first real run over frozen history reported
    `gaps=(68, 69, 70, 71, 72, 73)`. Three of those -- `M5i-068`, `M5i-071`,
    `M5i-073` -- are the reserved block `docs/NEXT_MILESTONE.md` records. THE
    OTHER THREE ARE NEITHER DECLARED NOR CITED ANYWHERE: `M5i-069`, `M5i-070`
    and `M5i-072` appear in no commit body at all, and no document records
    them. `docs/PHASE_HISTORY.md`'s "130 findings declared across
    `M5i-001`-`M5i-136`" is consistent with this and does not mention it.

    KEPT APART FROM THE ACCEPTANCE TEST DELIBERATELY. That test validates the
    tool against records written before it existed; this pins a fact the tool
    itself produced, which is a weaker kind of evidence and should not be
    mixed in with the stronger kind. The range is frozen history, so the
    literal cannot drift.

    FAILS ON: deleting gap detection, which yields `()`; ranging over declared
    numbers rather than `1..max`, same; or an off-by-one at either end.
    """
    try:
        _base, _head, commits = read_range(_ACCEPTANCE_RANGE)
    except subprocess.CalledProcessError:
        pytest.skip(
            f"THE GAP PIN DID NOT RUN: the range {_ACCEPTANCE_RANGE} did not resolve, so a "
            "milestone tag is missing. Run `git fetch --tags` and re-run."
        )

    report = scan(commits, milestone="M5i")

    assert report.gaps == (68, 69, 70, 71, 72, 73)
    assert set(report.cited_not_declared) < {f"M5i-{n:03d}" for n in report.gaps}


def test_a_gap_is_detected() -> None:
    """EXPRESSIVENESS: the input declares 001, 002 and 004, so a gap exists to find.

    FAILS ON: ranging over the declared numbers rather than `1..max`, which
    yields no gap at all; or an off-by-one at the top that reports `4` as
    missing when it is present.
    """
    commits = [_commit("aaa", body=_block("M5k-001", "M5k-002", "M5k-004"))]

    report = scan(commits, milestone="M5k")

    assert report.gaps == (3,)
    assert report.maximum == 4
    assert report.failed is True


def test_a_duplicate_is_detected() -> None:
    """EXPRESSIVENESS: two commits declare the same id, which one commit cannot express.

    TWO ASSERTIONS BECAUSE ONE IS NOT ENOUGH. A mutant that de-duplicates on
    append reports no duplicate AND would pass an assertion reading only
    `duplicates`; the declared-versus-distinct comparison is what kills it.

    FAILS ON: collapsing `declared` to a set; dropping the `Counter`.
    """
    commits = [
        _commit("aaa", body=_block("M5k-001")),
        _commit("bbb", body=_block("M5k-001")),
    ]

    report = scan(commits, milestone="M5k")

    assert report.duplicates == ("M5k-001",)
    assert len(report.declared) != len(report.distinct)
    assert report.failed is True


def test_a_cited_id_that_is_never_declared_is_reported_and_does_not_fail() -> None:
    """THE RESERVED-BLOCK PIN. Reporting and failing are different acts.

    This is what stops a later hand "tightening" the tool until it fails on
    `M5i-068`, `M5i-071` and `M5i-073`, which are reserved by ruling.

    EXPRESSIVENESS: the subject line cites an id the body never declares, so
    the two sets genuinely differ.
    FAILS ON: adding `cited_not_declared` to `failed`; or counting citations
    over `%b`, which would not see the subject and would report nothing.
    """
    commits = [
        _commit(
            "aaa",
            subject="fix: supersede M5k-099",
            body=_block("M5k-001"),
        )
    ]

    report = scan(commits, milestone="M5k")

    assert report.cited_not_declared == ("M5k-099",)
    assert report.failed is False


def test_a_blockless_commit_is_detected() -> None:
    """EXPRESSIVENESS: one body carries no `Findings:` header at all.

    FAILS ON: loosening the anchor to `^Findings:`, which `CLAUDE.md` measures
    matched eighteen lines of WRAPPED PROSE over M5g because a line break put
    the word at column 0.
    """
    commits = [
        _commit("aaa", body=_block("M5k-001")),
        _commit("bbb", body="A body that simply forgot.\n"),
    ]

    report = scan(commits, milestone="M5k")

    assert report.blockless == ("bbb",)
    assert report.failed is True


def test_findings_none_counts_as_a_block() -> None:
    """`Findings: none` is MANDATORY, never an absent section, so it must count.

    FAILS ON: anchoring `^Findings:$` alone, which `CLAUDE.md` measures would
    silently drop all THIRTEEN `Findings: none` blocks in history -- the
    expensive direction, since every one would read as a blockless commit.
    """
    commits = [_commit("aaa", body="Findings: none\n")]

    report = scan(commits, milestone="M5k")

    assert report.blockless == ()
    assert report.failed is False


def test_declaration_matching_is_case_sensitive() -> None:
    """A DELIBERATE DEPARTURE FROM THE DOCUMENTED EXTRACTOR, pinned so it stays one.

    MEASURED in PowerShell: `"- m5k-001 -- x" -match "^- (M5k-\\d{3}) -- "`
    MATCHES and captures `m5k-001`, because `-match` is case-insensitive by
    default. This transcription is case-sensitive, so a lowercase id is a typo
    that surfaces rather than one that is silently accepted.

    FAILS ON: passing `re.IGNORECASE` to either pattern.
    """
    commits = [_commit("aaa", body="Findings:\n- m5k-001 -- lowercase. MEASURED.\n")]

    report = scan(commits, milestone="M5k")

    assert report.declared == ()
    assert report.distinct == ()


def test_the_output_names_its_patterns_and_the_commits_it_scanned(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """THE ANTI-SILENT-SUCCESS PIN. A check whose failure path prints success is not one.

    Without this, an empty declared set from a WRONG PATTERN and an empty
    declared set on an EMPTY RANGE produce the same output and nobody can tell
    them apart. The commit count and the patterns are what separate them.

    EXPRESSIVENESS: `HEAD~1..HEAD` resolves in any clone with two commits, so
    this needs no tag and cannot skip.
    FAILS ON: deleting the measurement header; echoing the range argument
    without resolving it; or omitting the commit count.
    """
    code = main(["HEAD~1..HEAD", "M5k"])
    out = capsys.readouterr().out

    assert code in (0, 1)
    assert citation_pattern("M5k") in out
    assert declaration_pattern("M5k") in out
    assert "commits scanned" in out
    assert "resolved base" in out


def test_an_unresolvable_ref_refuses_loudly_rather_than_reporting_zero(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """An unknown ref is FATAL, not an empty report.

    `CLAUDE.md` records why: the table lookup it replaced "returns a
    well-formed subset that nothing signals distrust of, which is strictly
    worse than the empty result". A procedure that cannot be run wrong is worth
    more than one that is convenient to run right.

    FAILS ON: swallowing `CalledProcessError` into an empty `Findings`, which
    would return 0 with `declared=0` and read exactly like a clean namespace.
    """
    code = main(["milestone/M5x-does-not-exist..HEAD", "M5k"])
    out = capsys.readouterr().out

    assert code == 2
    assert "REFUSED" in out
