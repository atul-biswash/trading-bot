"""Tests for ``scripts/check_arming_conditions.py``.

Each test states what it would fail on. The tool's whole value is that it
refuses to report a clean run while its parser is blind, so the tests that
matter most are the ones pinning the FAILURE path -- a check whose failure path
prints success is not a check.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

from check_arming_conditions import Parsed, Unparsed, blocks, classify, main

_REPO_ROOT = Path(__file__).resolve().parents[2]
_LIVE_DOCUMENT = _REPO_ROOT / "docs" / "NEXT_MILESTONE.md"

_PARSEABLE = """### An item

Some prose about the item.

*Arming condition:* **whoever next edits `to_order` in `exchange/models.py`.**

### Another item

*Arming condition:* **whoever next edits `_book_exits`.**
"""

_NO_SYMBOL = """### An item

*Arming condition:* **whoever amends Q-C section 3's leg set.**
"""

_UNCLOSED_BOLD = """### An item

*Arming condition:* **whoever next edits `to_order` and never closes the span

### Another heading
"""

_MULTI_LINE = """### An item

*Arming condition:* **whoever next reads `ExitFill.venue_time` for anything
other than display** -- the first caller that would compute a duration from it,
and the first that the name misleads.
"""


def _document(tmp_path: Path, text: str) -> Path:
    path = tmp_path / "ITEMS.md"
    path.write_text(text, encoding="utf-8")
    return path


def test_a_document_whose_conditions_all_parse_exits_zero(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Fail-closed means non-zero on failure, not non-zero always.

    EXPRESSIVENESS: both conditions close their bold span and name a symbol, so
    a correct parser has nothing to report and the register is genuinely empty.
    FAILS ON: a tool that exits non-zero unconditionally, which would be
    indistinguishable from the real failure it exists to signal.
    """
    document = _document(tmp_path, _PARSEABLE)

    code = main([str(document)])

    out = capsys.readouterr().out
    assert code == 0
    assert "parsed     : 2" in out
    assert "unparsed   : 0" in out


def test_the_unparsed_count_is_printed_when_it_is_zero(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The register prints on a clean run, which is the point of the dual form.

    EXPRESSIVENESS: the input has an EMPTY unparsed register, which is exactly
    the case a tool printing only non-empty registers would render silent.
    FAILS ON: guarding the UNPARSED block behind ``if unparsed:`` so a clean run
    prints nothing -- the reader then cannot tell a parser that found nothing to
    report from one that could not report.
    """
    document = _document(tmp_path, _PARSEABLE)

    main([str(document)])

    out = capsys.readouterr().out
    assert "UNPARSED" in out
    assert "none" in out
    assert "unparsed   : 0" in out


def test_a_condition_naming_no_symbol_is_unparsed_and_exits_nonzero(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A condition the parser cannot cross-reference is registered, not dropped.

    EXPRESSIVENESS: the condition is well-formed prose with a closed bold span
    and no backticked token -- a real shape measured twice in the live document.
    FAILS ON: skipping symbol-less conditions silently, which would report a
    clean run while auditing fewer conditions than the file contains.
    """
    document = _document(tmp_path, _NO_SYMBOL)

    code = main([str(document)])

    out = capsys.readouterr().out
    assert code == 1
    assert "unparsed   : 1" in out
    assert "names no backticked symbol" in out


def test_an_unclosed_bold_span_is_unparsed_with_its_own_reason(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The two failure reasons are distinguished rather than collapsed.

    EXPRESSIVENESS: the span opens and never closes, which is a different defect
    from naming no symbol and would be hidden by one shared reason string.
    FAILS ON: reporting a single generic "could not parse", which tells a reader
    that something failed and not what to fix.
    """
    document = _document(tmp_path, _UNCLOSED_BOLD)

    code = main([str(document)])

    out = capsys.readouterr().out
    assert code == 1
    assert "does not close" in out


def test_a_multi_line_condition_is_one_candidate_and_parses(tmp_path: Path) -> None:
    """Sixteen of the live document's conditions run past their opening line.

    EXPRESSIVENESS: the condition's symbol sits on the FIRST line and its bold
    span closes on the SECOND, so a line-at-a-time parser would either miss the
    close or split one condition into several.
    FAILS ON: parsing per line rather than per block, which is the shape that
    would put every multi-line condition in the unparsed register and make the
    tool useless against the real file.
    """
    document = _document(tmp_path, _MULTI_LINE)

    candidates = blocks(document.read_text(encoding="utf-8").splitlines())

    assert len(candidates) == 1
    line, text = candidates[0]
    result = classify(line, text)
    assert isinstance(result, Parsed)
    assert "ExitFill.venue_time" in result.symbols


def test_a_document_with_no_conditions_exits_zero(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """No candidates is a clean run, and the totals say so explicitly.

    EXPRESSIVENESS: the input genuinely contains no marker.
    FAILS ON: treating an empty candidate list as a parse failure, or printing
    nothing at all -- the reader needs "candidates : 0" to distinguish an empty
    document from a marker whose spelling drifted.
    """
    document = _document(tmp_path, "### An item\n\nNo condition here.\n")

    code = main([str(document)])

    out = capsys.readouterr().out
    assert code == 0
    assert "candidates : 0" in out
    assert "unparsed   : 0" in out


def test_a_missing_document_is_refused(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """A path that is not a file refuses rather than raising.

    EXPRESSIVENESS: the path is not created.
    FAILS ON: letting ``read_text`` raise ``FileNotFoundError`` through the CLI.
    """
    code = main([str(tmp_path / "absent.md")])

    assert code == 2
    assert "REFUSED" in capsys.readouterr().out


def test_the_live_document_exit_code_matches_its_unparsed_register(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The fail-closed contract holds against the real file, whatever it contains.

    EXPRESSIVENESS: the input is the tracked document, whose conditions are
    irregular today and are expected to be regularised later. Asserting a
    SNAPSHOT of the unparsed count would pin prose rather than behaviour and
    would fail on any legitimate edit, so this asserts the COHERENCE instead:
    non-zero exit if and only if the register is non-empty.
    FAILS ON: widening the parser without re-checking the register, or exiting
    zero while candidates remain unparsed -- which is the tool reporting success
    on the path it exists to fail.
    """
    code = main([str(_LIVE_DOCUMENT)])

    out = capsys.readouterr().out
    unparsed_lines = [line for line in out.splitlines() if line.strip().startswith("unparsed   :")]
    assert unparsed_lines
    unparsed = int(unparsed_lines[0].split(":")[1].strip())

    assert (code == 1) == (unparsed > 0)
    assert code in (0, 1)


def test_the_registers_partition_the_candidates(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Every candidate lands in exactly one register.

    EXPRESSIVENESS: the document mixes a parseable condition with a symbol-less
    one, so a tool that dropped either would break the sum.
    FAILS ON: a candidate falling through both registers, which would let the
    totals look consistent while a condition went unaudited.
    """
    document = _document(tmp_path, _PARSEABLE + "\n" + _NO_SYMBOL)

    main([str(document)])

    out = capsys.readouterr().out
    assert "candidates : 3" in out
    assert "parsed     : 2" in out
    assert "unparsed   : 1" in out


def test_classify_returns_the_unparsed_type_for_a_symbol_less_condition() -> None:
    """The register types are distinguishable without reading printed text.

    EXPRESSIVENESS: the block is symbol-less prose.
    FAILS ON: returning a single type with a boolean flag, which would make the
    partition above assertable only through stdout.
    """
    result = classify(1, "*Arming condition:* **whoever amends the leg set.**")

    assert isinstance(result, Unparsed)
    assert result.reason.endswith("no backticked symbol")
