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
3 has now unified the three call-site predicates into one; the two enforcers
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
    # ONE SITE. (ii)b retired the three call-site copies; this is what Ruling 2
    # was for. The count went 3 -> 4 at (ii)a, which added the predicate while
    # leaving the copies, and 4 -> 1 here. Both numbers were fixed by the
    # project owner BEFORE either commit was written.
    "src/trading_bot/execution/bookability.py::classify_bookability",
}

#: The three call sites that must CONSUME the predicate. The census above
#: cannot see this: it counts `entry_fill_price is None` comparisons, and after
#: (ii)b the call sites have none WHETHER OR NOT they call
#: `classify_bookability`. So a set of one is reachable by rewiring and equally
#: by deleting the checks and routing them nowhere, and only this pins which
#: happened.
EXPECTED_CONSUMERS = {
    "_bookable_total",
    "_sell_and_book",
    "_book_exits",
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
    """ONE site. The three call-site copies are retired; this is Ruling 2 paid.

    MUTATION: add an unregistered copy anywhere in ``src/``; or delete one.

    **THE SET IS THE ASSERTION, NOT THE COUNT**, and the shape did not change
    when the number went 4 to 1 -- membership is what makes a failure
    actionable, because the message names exactly which site appeared or
    vanished.

    The three retired copies asked the SAME question in THREE different orders,
    and one of them (``_sell_and_book``) tested only this fact because its
    other three were established upstream. That ordering difference was
    ``M5i-039`` across files, and the predicate's single canonical ladder
    ``A > Q > P > C`` is what resolved it.

    **A COUNT OF ONE DOES NOT PROVE THE REWIRING** --
    ``test_all_three_call_sites_consume_the_shared_predicate`` is what does.
    This census matches comparisons, and a call site that deleted its check and
    routed nowhere has none either way.
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
    assert len(found) == 3, "the census reports three sites; other spellings are NOT among them"


def _functions_calling(name: str) -> set[str]:
    """Every function in ``src/`` containing a direct call to ``name``.

    A bare ``Name`` call, not an ``ast.Attribute`` one. The existing
    close-methods census in ``test_executor.py`` collects ``node.func.attr``
    and is therefore blind to ``classify_bookability(...)`` entirely -- it
    could not be reused, so this is written rather than extended.
    """
    calling: set[str] = set()
    for path in sorted(_SRC.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            for inner in ast.walk(node):
                if (
                    isinstance(inner, ast.Call)
                    and isinstance(inner.func, ast.Name)
                    and inner.func.id == name
                ):
                    calling.add(node.name)
    return calling


def test_all_three_call_sites_consume_the_shared_predicate() -> None:
    """The rewiring, pinned. **THE CENSUS ABOVE CANNOT SEE THIS.**

    MUTATION: unwire any site -- return the venue field directly, or
    reimplement the criterion inline.

    A count of one predicate site is reachable two ways: the three copies were
    REWIRED onto it, or they were DELETED and routed nowhere. The census
    counts comparisons, so it scores both identically and reports success for
    the second. This is the assertion that separates them, and it is why the
    set above could safely drop to one.

    Names rather than qualified ids, because a rename is a different failure
    from an unwiring and the census above already pins the file.
    """
    consumers = _functions_calling("classify_bookability")

    assert consumers >= EXPECTED_CONSUMERS, (
        "a call site stopped consuming the shared predicate. Expected all of "
        f"{sorted(EXPECTED_CONSUMERS)} to call it; found {sorted(consumers)}"
    )
