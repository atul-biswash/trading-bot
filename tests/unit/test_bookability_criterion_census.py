"""Every site testing a cost basis for absence is REGISTERED here, and counted.

**RULING 2'S CONDITION, MADE ENFORCEABLE.** M5i commit 3b was authorised to add
a THIRD copy of ``entry_fill_price is None`` to ``execution/executor.py`` only
because option 3 is mandated to deliver a single shared bookability predicate
consumed by all of them. A copy option 3's author cannot find is a copy that
survives the unification, so the debt is counted here rather than described in a
docstring nobody greps.

**WHY A TEST AND NOT A COMMENT.** A marker comment cannot fail. This can: an
unregistered predicate site turns the count red and hands the author the
complete list in the failure message, so nobody has to know the sites exist. It
is the shape ``CLAUDE.md`` already names -- *"a ruling NOT to act is testable
exactly when the thing has an observable shape"* -- applied to a ruling to act
LATER.

**PREDICATES AND ENFORCERS ARE COUNTED SEPARATELY, because they are different
obligations.** A predicate REFUSES before the call and yields the right label; an
enforcer RAISES once an unpriceable position has already reached a pricing call.
``M5i-001`` is what happens when a predicate is missing and only the enforcer
catches it: the label was emitted before the raise and was already wrong. Option
3 unifies the three call-site predicates into the fourth; the two enforcers
stay, because a last line of defence that is deleted once callers are polite is
not a defence.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

#: Every site where a ``Position``'s cost basis is tested for absence, split by
#: what the site DOES about it. Stated as data so a failure prints the list.
EXPECTED_PREDICATES = {
    # THE SHARED PREDICATE, registered at (ii)a. The three below are the
    # call-site copies it exists to retire; (ii)b removes them and this set
    # becomes this line alone.
    "src/trading_bot/execution/bookability.py::classify_bookability",
    "src/trading_bot/execution/executor.py::_bookable_total",
    "src/trading_bot/execution/executor.py::_sell_and_book",
    "src/trading_bot/execution/reconciliation_driver.py::_book_exits",
}
EXPECTED_ENFORCERS = {
    "src/trading_bot/core/models.py::unrealized_pnl",
    "src/trading_bot/core/portfolio.py::_realised_from_total",
}

_SRC = Path(__file__).resolve().parents[2] / "src" / "trading_bot"


def _enclosing_function(tree: ast.Module, target: ast.AST) -> str:
    """The innermost ``def`` containing ``target``, or ``<module>``."""
    best = "<module>"
    best_depth = -1
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if any(child is target for child in ast.walk(node)):
            depth = node.col_offset
            if depth > best_depth:
                best, best_depth = node.name, depth
    return best


def _census() -> tuple[set[str], set[str]]:
    """Every ``<x>.entry_fill_price is None`` comparison in ``src/``, classified.

    **AST RATHER THAN GREP, AND THE REASON IS POLARITY.** ``CLAUDE.md`` records
    that a string enumerator cannot read an ``is`` from an ``is not``, so a
    substring census would score an inverted check identically to a correct one.
    This matches the comparison node itself.
    """
    predicates: set[str] = set()
    enforcers: set[str] = set()
    for path in sorted(_SRC.rglob("*.py")):
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source)
        lines = source.splitlines()
        for node in ast.walk(tree):
            if not isinstance(node, ast.Compare):
                continue
            left = node.left
            if not (isinstance(left, ast.Attribute) and left.attr == "entry_fill_price"):
                continue
            if len(node.ops) != 1 or not isinstance(node.ops[0], ast.Is):
                continue
            comparator = node.comparators[0]
            if not (isinstance(comparator, ast.Constant) and comparator.value is None):
                continue
            rel = path.relative_to(_SRC.parents[1]).as_posix()
            site = f"{rel}::{_enclosing_function(tree, node)}"
            # A site that RAISES is an enforcer; one that returns or continues
            # is a predicate. Read from the three lines the check guards, which
            # is enough for every site in this tree and is asserted below by the
            # membership check rather than trusted on its own.
            guarded = "\n".join(lines[node.lineno : node.lineno + 3])
            (enforcers if "raise" in guarded else predicates).add(site)
    return predicates, enforcers


def test_every_cost_basis_predicate_site_is_registered() -> None:
    """FOUR sites at (ii)a: the shared predicate, plus the three it retires.

    MUTATION: add an unregistered copy anywhere in ``src/``; or delete one.

    **THE SET IS THE ASSERTION, NOT THE COUNT.** Membership is what makes a
    failure actionable -- the message names exactly which site appeared or
    vanished -- and it is also what lets this survive (ii)b, where the same
    assertion drops to ONE entry without changing shape.

    The three call-site copies ask the SAME question in THREE different orders,
    and one of them (``_sell_and_book``) tests only this fact because its other
    three are established upstream. That ordering difference is ``M5i-039``
    across files, and it is what the registered predicate's single canonical
    ladder resolves.
    """
    predicates, _ = _census()

    assert predicates == EXPECTED_PREDICATES, (
        "the bookability criterion's registered site set moved. Option 3 must unify "
        f"EXACTLY these: {sorted(EXPECTED_PREDICATES)}. Found: {sorted(predicates)}"
    )


def test_the_two_enforcing_raises_are_still_there() -> None:
    """The last line of defence, counted apart from the predicates.

    MUTATION: delete either raise on the grounds that callers now check.

    They are not redundant with the predicates and must not be removed when
    option 3 lands. ``M5i-001`` is the measured case of a predicate missing and
    the enforcer being the only thing that fired -- too late to fix the label,
    and the only reason the ledger was not corrupted.
    """
    _, enforcers = _census()

    assert enforcers == EXPECTED_ENFORCERS, (
        f"expected {sorted(EXPECTED_ENFORCERS)}, found {sorted(enforcers)}"
    )


@pytest.mark.parametrize("spelling", ["if not position.entry_fill_price:", "is not None"])
def test_this_census_is_blind_to_other_spellings(spelling: str) -> None:
    """**THE BLIND SPOT, DECLARED IN THE TEST RATHER THAN DISCOVERED LATER.**

    This census anchors on the ``<x>.entry_fill_price is None`` comparison, so a
    further site written ``if not position.entry_fill_price:`` slips past it
    entirely -- and so does an inverted ``is not None``. Neither is hypothetical
    housekeeping: the truthiness spelling is SEPARATELY A BUG, because a cost
    basis of ``Decimal(0)`` is falsey and would be read as absent.

    ``CLAUDE.md``: *"a tool that is wrong legibly can be corrected, while
    eyeballing is wrong invisibly"* -- and the half that makes it legible is
    saying so where the tool lives. This test asserts nothing about ``src/``; it
    exists so the limitation is greppable from the census it limits.
    """
    predicates, enforcers = _census()
    found = predicates | enforcers

    assert spelling not in found, "unreachable: the census yields site ids, not source text"
    assert len(found) == 6, "the census reports six sites; other spellings are NOT among them"
