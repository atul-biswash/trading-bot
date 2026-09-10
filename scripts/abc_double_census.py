#!/usr/bin/env python
"""Count the test doubles that stand in for an ABC WITHOUT subclassing it.

**WHY THIS EXISTS, twice measured.** Widening an abstract base moves every
implementation with it, and this project has been blind to that count twice.
Once expensively: mypy reported ``Success`` while 98 tests failed, because the
fakes could no longer be instantiated and mypy does not run them. Once
knowingly: M5h's C5c report could give only a LOWER BOUND of four for
``ExchangeClient``, and said so, because a subclass count cannot see a
duck-typed double -- an object that defines the handful of methods a caller
actually reaches and inherits nothing.

Both blind spots are the same one. **A duck-typed double is invisible to mypy
AND to a subclass count**, so the two instruments this project already runs are
jointly incapable of producing the number. That is what makes a third one worth
writing rather than a convenience.

**AN AST WALK, NEVER A GREP.** A text grep for a symbol has matched its own
docstring here before and an AST walk was the fix. A ``Name`` or ``Attribute``
node cannot be a mention inside a string or a comment.

**IT REPORTS AND DOES NOT ENFORCE.** No gate step, no non-zero exit on a
finding. Whether this becomes a gate is a decision for the project owner; a tool
that fails a build on its first run has made that decision for them.

**IT IS A HEURISTIC, AND IT IS BUILT TO BE WRONG LEGIBLY RATHER THAN
INVISIBLY.** ``CLAUDE.md`` records what mechanising an enumeration buys and what
it does not: *"a tool that is wrong legibly can be corrected, while eyeballing
is wrong invisibly. What it must not buy is confidence. The output of an
enumerator is a CANDIDATE SET to be traced."* So every resolution prints HOW it
was reached, and every declaration site it could not resolve is printed too --
an unresolved site is a hole in the count, and a count with unprinted holes is
the failure this exists to end.

What it can see:

* a class whose bases name the ABC, directly or through another such class;
* an argument passed to a parameter annotated with the ABC, where the argument
  is a call to, or a name bound to, a class defined in the scanned tree;
* a name annotated with the ABC and assigned such a class.

What it CANNOT see, stated so the number is read correctly:

* a double built by a factory, a fixture return value, or ``type(...)``;
* an object passed through an intermediate variable it cannot trace;
* a double reached only via ``monkeypatch.setattr``;
* anything outside the scanned directories.

Usage::

    python scripts/abc_double_census.py
    python scripts/abc_double_census.py --abc MarketDataProvider
"""

from __future__ import annotations

import argparse
import ast
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
INTERFACES = ROOT / "src/trading_bot/core/interfaces.py"
SCAN = ("src", "tests", "scripts")


@dataclass
class ClassInfo:
    """One class definition found in the tree."""

    name: str
    path: Path
    lineno: int
    bases: tuple[str, ...]
    methods: frozenset[str]


@dataclass
class Double:
    """A class standing in for the ABC without subclassing it."""

    info: ClassInfo
    how: str
    sites: list[str] = field(default_factory=list)


def base_names(node: ast.ClassDef) -> tuple[str, ...]:
    return tuple(ast.unparse(b) for b in node.bases)


def method_names(node: ast.ClassDef) -> frozenset[str]:
    return frozenset(
        item.name for item in node.body if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef))
    )


def abc_methods(abc_name: str) -> frozenset[str]:
    """The ABC's public method names, read from its own definition."""
    tree = ast.parse(INTERFACES.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == abc_name:
            return frozenset(m for m in method_names(node) if not m.startswith("_"))
    return frozenset()


def scan_files() -> list[Path]:
    out: list[Path] = []
    for folder in SCAN:
        out.extend(sorted((ROOT / folder).rglob("*.py")))
    return [p for p in out if "__pycache__" not in p.parts]


def collect_classes(paths: list[Path]) -> dict[Path, dict[str, ClassInfo]]:
    """Every class in the scanned tree, keyed by MODULE then by name.

    **KEYED BY MODULE, AND A BARE-NAME KEY WAS MEASURED WRONG.** A first version
    keyed on the name alone and kept the first of any collision. This tree has
    THREE classes called ``_StubClient`` -- in ``test_reconciliation_driver``,
    ``test_reconciliation_pass`` and ``test_resolution`` -- and they are not
    interchangeable: the first two define ``get_order`` and
    ``get_own_open_orders`` while the third defines ``get_all_order_lists``. The
    bare-name version reported one of them against call sites belonging to
    another, so both the file it named and the method set it printed were wrong
    for the sites it listed. Module scoping makes that unrepresentable.
    """
    found: dict[Path, dict[str, ClassInfo]] = {}
    for path in paths:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        per_module: dict[str, ClassInfo] = {}
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                per_module[node.name] = ClassInfo(
                    name=node.name,
                    path=path,
                    lineno=node.lineno,
                    bases=base_names(node),
                    methods=method_names(node),
                )
        found[path] = per_module
    return found


def resolve(
    classes: dict[Path, dict[str, ClassInfo]], name: str, *, here: Path
) -> ClassInfo | None:
    """A class by name, preferring the module the reference is IN.

    Falls back to any module defining that name, which is how a base class
    imported from elsewhere is found. Same-module first is what keeps three
    identically-named doubles apart.
    """
    local = classes.get(here, {}).get(name)
    if local is not None:
        return local
    for per_module in classes.values():
        if name in per_module:
            return per_module[name]
    return None


def subclass_closure(
    classes: dict[Path, dict[str, ClassInfo]], abc_name: str
) -> dict[tuple[Path, str], ClassInfo]:
    """Every class reaching the ABC through its bases, transitively.

    Keyed by ``(module, name)`` for the reason :func:`collect_classes` states.
    """
    out: dict[tuple[Path, str], ClassInfo] = {}
    known = {abc_name}
    changed = True
    while changed:
        changed = False
        for path, per_module in classes.items():
            for name, info in per_module.items():
                if (path, name) in out:
                    continue
                if any(any(k in base for k in known) for base in info.bases):
                    out[(path, name)] = info
                    known.add(name)
                    changed = True
    return out


def variable_bindings(tree: ast.AST) -> dict[str, set[str]]:
    """Per-module map of ``name = SomeClass(...)`` bindings.

    **WITHOUT THIS THE COUNT UNDERREPORTS SILENTLY, MEASURED.** The common shape
    in this suite is ``client = _StubClient(...)`` followed by passing ``client``
    -- and a bare ``Name`` argument resolves to no class, so a first version
    skipped those sites without even recording them as unresolved. Two of the
    three ``_StubClient`` doubles in this tree were invisible for that reason,
    in a tool written to make invisible doubles visible.

    A name bound to more than one class is returned with both, and the caller
    reports it as ambiguous rather than picking one. Module-scoped, not
    function-scoped, which is coarse: two functions using ``client`` for
    different classes read as ambiguous even though each is unambiguous where it
    stands. That is the safe direction -- it over-reports uncertainty.
    """
    out: dict[str, set[str]] = {}
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign) or not isinstance(node.value, ast.Call):
            continue
        callee = getattr(node.value.func, "id", None)
        if callee is None:
            continue
        for target in node.targets:
            if isinstance(target, ast.Name):
                out.setdefault(target.id, set()).add(callee)
    return out


def annotated_params(tree: ast.AST, abc_name: str) -> dict[str, list[tuple[str, int]]]:
    """Functions with a parameter annotated by the ABC: name -> [(param, index)]."""
    out: dict[str, list[tuple[str, int]]] = {}
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        args = node.args
        ordered = [*args.posonlyargs, *args.args]
        hits: list[tuple[str, int]] = []
        for index, arg in enumerate(ordered):
            if arg.annotation is not None and abc_name in ast.unparse(arg.annotation):
                hits.append((arg.arg, index))
        for arg in args.kwonlyargs:
            if arg.annotation is not None and abc_name in ast.unparse(arg.annotation):
                hits.append((arg.arg, -1))
        if hits:
            out[node.name] = hits
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description="Census of ABC stand-ins.")
    parser.add_argument("--abc", default="ExchangeClient", help="the ABC to census")
    args = parser.parse_args()
    abc_name: str = args.abc

    paths = scan_files()
    methods = abc_methods(abc_name)
    if not methods:
        print(f"REFUSED: no class named {abc_name!r} in {INTERFACES.name}")
        return 2

    print(f"ABC            : {abc_name}")
    print(f"  declared methods ({len(methods)}): {sorted(methods)}")
    print(f"  files scanned  : {len(paths)} under {list(SCAN)}")

    classes = collect_classes(paths)
    subclasses = subclass_closure(classes, abc_name)

    print(f"\n{'=' * 74}\nVISIBLE SET -- classes that SUBCLASS {abc_name}\n{'=' * 74}")
    for (path, name), info in sorted(subclasses.items(), key=lambda kv: str(kv[0])):
        rel = path.relative_to(ROOT).as_posix()
        print(f"  {rel}:{info.lineno}  {name}({', '.join(info.bases)})")
    if not subclasses:
        print("  <none>")

    # Every function in the tree taking the ABC as a declared parameter type.
    #
    # A CLASS IS REGISTERED UNDER ITS OWN NAME, NOT UNDER `__init__`, because a
    # call site reads `ReconciliationDriver(client=...)` and never
    # `__init__(...)`. Without this, constructor injection is invisible -- and
    # it is how one of this tree's three `_StubClient` doubles reaches the ABC,
    # so the omission was measured rather than imagined. The `__init__` entry is
    # dropped: keeping both would double-count every constructor call.
    declarations: dict[str, list[tuple[str, int]]] = {}
    for path in paths:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for fname, hits in annotated_params(tree, abc_name).items():
            if fname == "__init__":
                continue
            declarations.setdefault(fname, []).extend(hits)
        for node in ast.walk(tree):
            if not isinstance(node, ast.ClassDef):
                continue
            for item in node.body:
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)) and item.name in {
                    "__init__",
                    "create",
                }:
                    wrapper = ast.Module(body=[item], type_ignores=[])
                    for _, hits in annotated_params(wrapper, abc_name).items():
                        # `self` occupies index 0, so shift positional indices.
                        shifted = [(p, i - 1 if i > 0 else -1) for p, i in hits]
                        declarations.setdefault(node.name, []).extend(shifted)

    doubles: dict[tuple[Path, str], Double] = {}
    unresolved: list[str] = []

    for path in paths:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        rel = path.relative_to(ROOT).as_posix()
        bindings = variable_bindings(tree)

        # (a) arguments passed to a parameter annotated with the ABC.
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            called = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", None)
            if called not in declarations:
                continue
            candidates: list[ast.expr] = []
            for param, index in declarations[called]:
                for kw in node.keywords:
                    if kw.arg == param:
                        candidates.append(kw.value)
                if 0 <= index < len(node.args):
                    candidates.append(node.args[index])
            for candidate in candidates:
                target = candidate.func if isinstance(candidate, ast.Call) else candidate
                cname = getattr(target, "id", None)
                site = f"{rel}:{node.lineno} -> {called}()"
                if cname is None:
                    unresolved.append(f"{site}  [argument is {type(candidate).__name__}]")
                    continue
                how = "passed where the ABC is declared"
                if resolve(classes, cname, here=path) is None:
                    # Not a class: try the module's `name = SomeClass(...)`
                    # bindings before giving up, and NEVER give up silently.
                    bound = bindings.get(cname, set())
                    if len(bound) != 1:
                        unresolved.append(
                            f"{site}  [argument {cname!r} binds to {sorted(bound) or 'nothing'}]"
                        )
                        continue
                    cname = next(iter(bound))
                    how = "bound to a local, then passed where the ABC is declared"
                found_info = resolve(classes, cname, here=path)
                if found_info is None:
                    unresolved.append(f"{site}  [{cname!r} is not a class in the scanned tree]")
                    continue
                key = (found_info.path, cname)
                if key in subclasses:
                    continue
                double = doubles.setdefault(key, Double(info=found_info, how=how))
                double.sites.append(site)

        # (b) a name annotated with the ABC and assigned a class in the tree.
        for node in ast.walk(tree):
            if not isinstance(node, ast.AnnAssign) or node.value is None:
                continue
            if abc_name not in ast.unparse(node.annotation):
                continue
            value = node.value
            target = value.func if isinstance(value, ast.Call) else value
            cname = getattr(target, "id", None)
            if cname is None:
                continue
            found_info = resolve(classes, cname, here=path)
            if found_info is None or (found_info.path, cname) in subclasses:
                continue
            double = doubles.setdefault(
                (found_info.path, cname),
                Double(info=found_info, how="assigned to a name annotated with the ABC"),
            )
            double.sites.append(f"{rel}:{node.lineno}")

    print(f"\n{'=' * 74}\nINVISIBLE SET -- stand-ins that do NOT subclass {abc_name}\n{'=' * 74}")
    if not doubles:
        print("  <none>")
        print()
        print("  Every stand-in in the scanned tree subclasses the ABC, so mypy and a")
        print("  subclass count agree and the subclass count is EXACT rather than a")
        print("  lower bound. Read that against this tool's stated blind spots above;")
        print("  it is evidence about what was scanned, not a proof of absence.")
    for (_path, name), double in sorted(doubles.items(), key=lambda kv: str(kv[0])):
        info = double.info
        rel = info.path.relative_to(ROOT).as_posix()
        missing = sorted(methods - info.methods)
        print(f"\n  {name}  ({rel}:{info.lineno})")
        print(f"    how       : {double.how}")
        print(f"    defines   : {sorted(methods & info.methods)}")
        print(f"    LACKS     : {missing if missing else '<nothing -- full surface>'}")
        for site in double.sites:
            print(f"    site      : {site}")

    if unresolved:
        print(f"\n{'=' * 74}\nUNRESOLVED SITES -- holes in the count, not absences\n{'=' * 74}")
        for line in unresolved:
            print(f"  {line}")

    total = len(subclasses) + len(doubles)
    print(f"\n{'=' * 74}\nTOTALS\n{'=' * 74}")
    print(f"  subclasses (visible to mypy) : {len(subclasses)}")
    print(f"  duck-typed doubles (invisible): {len(doubles)}")
    print(f"  unresolved sites              : {len(unresolved)}")
    print(f"  TOTAL stand-ins found         : {total}")
    return 0


if __name__ == "__main__":  # pragma: no cover - CLI entry point
    raise SystemExit(main())
