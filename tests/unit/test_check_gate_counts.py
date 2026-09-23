"""Tests for ``scripts/check_gate_counts.py``.

Each test states what it would fail on. The second is the one that earns its
place: it asserts that a set of COINCIDENTAL digits is not demanded, which is
the half of the count discipline no tool can infer and every tool can get
wrong in the expensive direction.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

from check_gate_counts import Expected, audit

_EXPECTED = Expected(
    ruff_format=126,
    mypy=78,
    pytest_passed=1676,
    pytest_skipped=1,
    credential_gated=3,
)


def _documents(tmp_path: Path, claude: str, readme: str) -> tuple[Path, ...]:
    first = tmp_path / "CLAUDE.md"
    second = tmp_path / "README.md"
    first.write_text(claude, encoding="utf-8")
    second.write_text(readme, encoding="utf-8")
    return (first, second)


def test_a_matching_document_set_agrees_and_a_mismatched_one_does_not(tmp_path: Path) -> None:
    """All four structural shapes, once agreeing and once not.

    EXPRESSIVENESS: the fixture carries the fenced gate output, both
    gate-scope table rows, the credentialed pytest pair and the DERIVED pair,
    so every pattern and both pytest kinds have something to match. A fixture
    with one shape could not tell a tool that reads one from a tool that reads
    four.

    THE DERIVED FIGURE IS DISCRIMINATED BY ITS SKIP COUNT, and the last
    assertion is what pins it: a site reading `1673 passed, 1 skipped` has
    promoted a derivation to a measurement, and it must report BAD rather than
    pass because the number happens to appear somewhere valid.

    FAILS ON: setting `ok` unconditionally true, which survives the first half
    and dies on the second; reporting everything bad, which dies on the first;
    dropping the pytest skip-count discrimination, which mislabels the derived
    pair and stops the promotion being caught.
    """
    claude = (
        "ruff format --check src tests scripts  126 files already formatted\n"
        "mypy                                   Success: no issues found in 78 source files\n"
        "pytest                                 1673 passed, 4 skipped\n"
        "                                       (1676 passed, 1 skipped with credentials)\n"
        "| `ruff check` / `ruff format --check` | `src tests scripts` | 126 |\n"
        '| `mypy` | `files = ["src/trading_bot", "scripts"]` | 78 |\n'
    )
    readme = "pytest 1676 passed, 1 skipped\n"

    sites, unclaimed = audit(_EXPECTED, _documents(tmp_path, claude, readme))

    assert sites != []
    assert all(site.ok for site in sites)
    assert unclaimed == []

    stale = claude.replace("126 files already formatted", "125 files already formatted")
    sites, _unclaimed = audit(_EXPECTED, _documents(tmp_path, stale, readme))

    bad = [site for site in sites if not site.ok]
    assert len(bad) == 1
    assert bad[0].observed == "125"
    assert bad[0].line == 1

    promoted = "pytest 1673 passed, 1 skipped\n"
    sites, _unclaimed = audit(_EXPECTED, _documents(tmp_path, promoted, readme))

    bad = [site for site in sites if not site.ok]
    assert len(bad) == 1
    assert bad[0].kind == "pytest (measured, credentialed)"


def test_the_coincidental_digit_set_is_not_demanded(tmp_path: Path) -> None:
    """The five hits P0 enumerated, verbatim, and none may be claimed or flagged.

    A helper that demanded an edit to a money bound or a line citation would be
    worse than no helper, because a tired hand would make the edit. The
    exclusion here is STRUCTURAL -- word boundaries and surrounding vocabulary
    -- so there is no skip-list to maintain and none to go stale.

    EXPRESSIVENESS: `476` contains the mypy figure's digits as a SUBSTRING, so
    a tool that dropped `\\b` would claim it. `+74.11` and the three `118`
    hits carry no gate token at all and are present to prove the patterns do
    not reach for any nearby digit.

    FAILS ON: dropping the word boundaries from the token audit, which flags
    `476`; matching a bare `\\d+` near gate vocabulary; or widening the table
    row pattern to any row ending in a number.
    """
    claude = (
        "heredoc wrote CRLF into two LF-pinned fixture files -- 1148 and 476 CR bytes\n"
        "bounded at -34.34 and +74.11. Both legs were CANCELED with\n"
        "the digit grep found 18 lines, and the inverse spared a coincidental `118`\n"
        "A fourth `118` also exists and is NOT a gate figure: a line-number citation\n"
        "used: `M5_NUMBERS.md:433` for a row at `:434`, Q-C `:101`/`:118` for labels at\n"
    )

    sites, unclaimed = audit(_EXPECTED, _documents(tmp_path, claude, ""))

    assert sites == []
    assert unclaimed == []
