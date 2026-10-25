#!/usr/bin/env python
"""A mutation survey in a disposable detached worktree OUTSIDE the repository, from a spec file.

This is the survey ``CLAUDE.md`` requires since M5k ("Mutation surveys must execute strictly in
isolated, throwaway worktrees"), as a tested script. It replaces a scratch harness whose
exception-types line was read off pytest's text and under-reported ``decimal.InvalidOperation`` and
``StopIteration`` as assertions (``M5n-088``); here the class of every failing test comes from
:mod:`survey_hook`, which reads it from the live exception.

What one run does, in order:

1. Create a detached worktree of the repository's HEAD at ``--worktree``, which must be outside the
   repository, and copy each ``copy`` file of the spec into it, shown SHA-256-equal.
2. Run an unmutated BASELINE in the worktree and require it green, and print where ``trading_bot`` and
   the ``tests`` package were imported from (the spec's ``proof`` modules), which must be inside the
   worktree. No result counts before both hold.
3. For each mutation, apply it byte-exact (binary read and write, so LF is preserved) with exactly ONE
   match asserted, print the mutated content, run the tests, and restore from an out-of-tree snapshot in
   a ``finally``, shown SHA-equal. A mutation may instead ``create`` a file, which the restore removes.
4. Compare the failing tests with the predicted ones: ``MATCH``; ``MORE`` (recorded); ``FEWER``, which
   HALTS the survey, because an absent kill is indistinguishable from a mutation that never loaded.
   Each failing test prints as a kill (an assertion, an unmet ``pytest.raises`` or ``pytest.fail``, or
   ``SystemExit``) or as a crash with its qualified class.
5. Show every copied file intact, and remove the worktree unless ``--keep``.

A run whose pytest exit status is neither 0 nor 1 produced no verdict (a collection error, an internal
error) and HALTS: a mutation is a claim about behaviour, and an unparseable tree expresses none.

Spec (JSON)::

    {"copy": [paths], "tests": [paths], "proof": ["trading_bot", "tests"],
     "mutations": [{"label", "file", "old", "new", "predict": [node-id suffixes], "abstain": [notes]}]}

``predict`` items are node-id suffixes, or ``prefix:TEXT|N`` for exactly N failures whose id starts
with TEXT. A mutation with ``create`` in place of ``old``/``new`` adds a file.

Usage::

    python scripts/worktree_survey.py --worktree DIR --scratch DIR SPEC.json
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
from collections.abc import Collection, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Final

__all__ = [
    "AnchorError",
    "Comparison",
    "Failure",
    "Mutation",
    "Predicted",
    "Spec",
    "SpecError",
    "apply_replace",
    "compare",
    "load_spec",
    "main",
    "parse_predicted",
    "read_failures",
    "short_id",
]

ROOT: Final = Path(__file__).resolve().parent.parent
_SCRIPTS: Final = Path(__file__).resolve().parent
_PREFIX: Final = "prefix:"
_READABLE_EXITS: Final = frozenset({0, 1})


class SpecError(Exception):
    """The spec file is not a survey this script can run."""


class AnchorError(Exception):
    """A mutation's anchor did not match exactly once."""


@dataclass(frozen=True)
class Mutation:
    label: str
    file: str
    old: str | None
    new: str | None
    create: str | None
    predict: tuple[str, ...]
    abstain: tuple[str, ...]


@dataclass(frozen=True)
class Spec:
    copy: tuple[str, ...]
    tests: tuple[str, ...]
    proof: tuple[str, ...]
    mutations: tuple[Mutation, ...]


@dataclass(frozen=True)
class Failure:
    """One failing test, as :mod:`survey_hook` recorded it."""

    nodeid: str
    when: str
    type_name: str
    kill: bool


@dataclass(frozen=True)
class Predicted:
    exact: tuple[str, ...]
    prefixes: tuple[tuple[str, int], ...]

    @property
    def count(self) -> int:
        return len(self.exact) + sum(n for _, n in self.prefixes)


@dataclass(frozen=True)
class Comparison:
    verdict: str
    missing: frozenset[str]
    extra: frozenset[str]
    predicted: int
    observed: int


def _strings(raw: object, name: str) -> tuple[str, ...]:
    if not isinstance(raw, list) or not all(isinstance(item, str) for item in raw):
        raise SpecError(f"{name} must be a list of strings")
    return tuple(raw)


def _optional_text(raw: dict[str, object], key: str, label: str) -> str | None:
    value = raw.get(key)
    if value is not None and not isinstance(value, str):
        raise SpecError(f"mutation {label}: {key} must be a string")
    return value


def load_spec(path: Path) -> Spec:
    """Read and validate a spec file.

    :raises SpecError: the file is not valid JSON of the documented shape, a label repeats, or a
        mutation is neither a replacement nor a creation.
    """
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise SpecError(f"{path}: {exc}") from exc
    if not isinstance(raw, dict):
        raise SpecError("the spec must be a JSON object")
    mutations_raw = raw.get("mutations")
    if not isinstance(mutations_raw, list) or not mutations_raw:
        raise SpecError("the spec needs a non-empty list of mutations")
    mutations: list[Mutation] = []
    seen: set[str] = set()
    for item in mutations_raw:
        if not isinstance(item, dict) or not isinstance(item.get("label"), str):
            raise SpecError("each mutation needs a string label")
        label = item["label"]
        if label in seen:
            raise SpecError(f"the label {label} repeats")
        seen.add(label)
        file = item.get("file")
        if not isinstance(file, str):
            raise SpecError(f"mutation {label}: file must be a string")
        old = _optional_text(item, "old", label)
        new = _optional_text(item, "new", label)
        create = _optional_text(item, "create", label)
        replaces = old is not None and new is not None
        if replaces == (create is not None) or (not replaces and create is None):
            raise SpecError(f"mutation {label}: give either old and new, or create")
        mutations.append(
            Mutation(
                label=label,
                file=file,
                old=old,
                new=new,
                create=create,
                predict=_strings(item.get("predict", []), f"{label}.predict"),
                abstain=_strings(item.get("abstain", []), f"{label}.abstain"),
            )
        )
    tests = _strings(raw.get("tests"), "tests")
    if not tests:
        raise SpecError("the spec needs at least one test path")
    return Spec(
        copy=_strings(raw.get("copy", []), "copy"),
        tests=tests,
        proof=_strings(raw.get("proof", ["trading_bot", "tests"]), "proof"),
        mutations=tuple(mutations),
    )


def apply_replace(data: bytes, old: bytes, new: bytes) -> bytes:
    """``data`` with its one occurrence of ``old`` replaced by ``new``.

    :raises AnchorError: ``old`` occurs zero times or more than once, so the experiment would not be
        the one described.
    """
    count = data.count(old)
    if count != 1:
        raise AnchorError(f"the anchor matches {count} times, not once")
    return data.replace(old, new)


def parse_predicted(items: Sequence[str]) -> Predicted:
    """Split a ``predict`` list into node-id suffixes and ``prefix:TEXT|N`` counts."""
    exact = tuple(item for item in items if not item.startswith(_PREFIX))
    prefixes: list[tuple[str, int]] = []
    for item in items:
        if item.startswith(_PREFIX):
            text, _, count = item[len(_PREFIX) :].rpartition("|")
            prefixes.append((text, int(count)))
    return Predicted(exact=exact, prefixes=tuple(prefixes))


def short_id(nodeid: str) -> str:
    """A node id without its file path: ``Class::test[param]``."""
    return nodeid.split("::", 1)[1] if "::" in nodeid else nodeid


def compare(predicted: Predicted, failed: Collection[str]) -> Comparison:
    """Compare the short ids that failed with the predicted set.

    ``FEWER`` when any predicted failure is absent, whatever else failed; ``MORE`` when every predicted
    failure is there and something else failed too; ``MATCH`` otherwise.
    """
    observed = set(failed)
    explained = {g for g in observed if any(g.endswith(p) for p in predicted.exact)}
    missing = {p for p in predicted.exact if not any(g.endswith(p) for g in observed)}
    extra: set[str] = set()
    for text, count in predicted.prefixes:
        hits = {g for g in observed if g.startswith(text)}
        explained |= hits
        if len(hits) < count:
            missing.add(f"{text} (expected {count}, got {len(hits)})")
        elif len(hits) > count:
            extra |= hits
    extra |= observed - explained
    verdict = "MATCH" if not missing and not extra else ("FEWER" if missing else "MORE")
    return Comparison(
        verdict=verdict,
        missing=frozenset(missing),
        extra=frozenset(extra),
        predicted=predicted.count,
        observed=len(observed),
    )


def read_failures(path: Path) -> list[Failure]:
    """The failures :mod:`survey_hook` recorded, one JSON line each; a missing file is none."""
    if not path.exists():
        return []
    failures: list[Failure] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        failures.append(Failure(row["nodeid"], row["when"], row["type"], bool(row["kill"])))
    return failures


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _git(*args: str, cwd: Path) -> str:
    done = subprocess.run(
        ["git", *args], cwd=cwd, capture_output=True, text=True, check=True, encoding="utf-8"
    )
    return done.stdout.strip()


class _Run:
    """One survey: the paths, the pytest subprocess, and the verdict files."""

    def __init__(
        self, *, repo: Path, worktree: Path, scratch: Path, python: str, spec: Spec, tag: str
    ) -> None:
        self.repo, self.worktree, self.scratch = repo, worktree, scratch
        self.python, self.spec, self.tag = python, spec, tag
        self.proof_out = scratch / f"survey_{tag}_proof.txt"
        self.snapshots = scratch / "survey_snapshots"

    def pytest(self, label: str) -> tuple[int, list[Failure], str]:
        verdicts = self.scratch / f"survey_{self.tag}_{label}_verdicts.jsonl"
        verdicts.write_text("", encoding="utf-8")
        env = dict(os.environ)
        env["PYTHONPATH"] = str(_SCRIPTS)
        env["SURVEY_VERDICTS"] = str(verdicts)
        env["SURVEY_PROOF_OUT"] = str(self.proof_out)
        env["SURVEY_PROOF_MODULES"] = ",".join(self.spec.proof)
        done = subprocess.run(
            [
                self.python,
                "-m",
                "pytest",
                "-p",
                "survey_hook",
                "-p",
                "no:cacheprovider",
                "-rf",
                *self.spec.tests,
            ],
            cwd=self.worktree,
            env=env,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        (self.scratch / f"survey_{self.tag}_{label}.txt").write_text(
            done.stdout + done.stderr, encoding="utf-8"
        )
        failures = [f for f in read_failures(verdicts) if f.when == "call"]
        tail = [ln for ln in done.stdout.splitlines() if " passed" in ln or " failed" in ln]
        return done.returncode, failures, tail[-1] if tail else "??"


def _report(
    label: str, comparison: Comparison, failures: Sequence[Failure], abstain: Sequence[str]
) -> None:
    print(
        f"[{label}] predicted {comparison.predicted}, observed {comparison.observed}: "
        f"{comparison.verdict}"
    )
    for failure in sorted(failures, key=lambda f: f.nodeid):
        kind = "kill" if failure.kill else f"crash {failure.type_name}"
        print(f"     killed: {short_id(failure.nodeid)}  [{kind}]")
    for name in sorted(comparison.missing):
        print("     PREDICTED BUT NOT KILLED:", name)
    for name in sorted(comparison.extra):
        print("     KILLED BEYOND PREDICTION:", name)
    for note in abstain:
        print("     declared abstention:", note)


def _proof_inside(lines: Sequence[str], worktree: Path) -> bool:
    """``True`` when every ``name=path`` proof line names a file under ``worktree``."""
    root = worktree.resolve()
    for line in lines:
        _, _, location = line.partition("=")
        try:
            Path(location).resolve().relative_to(root)
        except ValueError:
            return False
    return True


def _outside(repo: Path, worktree: Path) -> bool:
    return repo.resolve() not in (worktree.resolve(), *worktree.resolve().parents)


def run_survey(
    spec: Spec, *, repo: Path, worktree: Path, scratch: Path, python: str, tag: str, keep: bool
) -> int:
    """Run a survey and return 0 completed, 1 halted, 2 not started."""
    if not _outside(repo, worktree) or worktree.resolve() == repo.resolve():
        print(f"the worktree {worktree} must be outside the repository {repo}", file=sys.stderr)
        return 2
    if worktree.exists():
        print(f"the worktree path {worktree} already exists", file=sys.stderr)
        return 2
    scratch.mkdir(parents=True, exist_ok=True)
    run = _Run(repo=repo, worktree=worktree, scratch=scratch, python=python, spec=spec, tag=tag)
    run.snapshots.mkdir(parents=True, exist_ok=True)
    run.proof_out.write_text("", encoding="utf-8")
    head = _git("rev-parse", "HEAD", cwd=repo)
    _git("worktree", "add", "--detach", str(worktree), head, cwd=repo)
    try:
        return _survey(run, repo=repo, head=head)
    finally:
        if not keep:
            _git("worktree", "remove", "--force", str(worktree), cwd=repo)
            _git("worktree", "prune", cwd=repo)
            print("worktrees:", _git("worktree", "list", cwd=repo).replace("\n", " | "))


def _survey(run: _Run, *, repo: Path, head: str) -> int:
    spec, worktree = run.spec, run.worktree
    print("worktree at", _git("rev-parse", "HEAD", cwd=worktree), "of", head)
    for rel in spec.copy:
        (worktree / rel).parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(repo / rel, worktree / rel)
        if _sha(repo / rel) != _sha(worktree / rel):
            print(f"{rel}: the copy is not SHA-equal to the original", file=sys.stderr)
            return 2
        print(f"copied {rel} sha {_sha(worktree / rel)}")
    code, failures, summary = run.pytest("baseline")
    print(f"[baseline] exit {code}: {summary}; failing: {sorted(f.nodeid for f in failures)}")
    proof = run.proof_out.read_text(encoding="utf-8").splitlines()
    for line in proof:
        print("import proof:", line)
    if not proof or not _proof_inside(proof, worktree):
        print("the import location is NOT the worktree: no result counts", file=sys.stderr)
        return 2
    if code != 0:
        print("the unmutated baseline is not green: no result counts", file=sys.stderr)
        return 2
    halted = False
    for mutation in spec.mutations:
        code, failures = _mutate(run, mutation)
        if code not in _READABLE_EXITS:
            print(f"[{mutation.label}] HALT: pytest exited {code}, so there is no verdict")
            halted = True
            break
        comparison = compare(
            parse_predicted(mutation.predict), {short_id(f.nodeid) for f in failures}
        )
        _report(mutation.label, comparison, failures, mutation.abstain)
        if comparison.missing:
            print(f"[{mutation.label}] HALT: a predicted kill is absent")
            halted = True
            break
    for rel in spec.copy:
        if _sha(worktree / rel) != _sha(repo / rel):
            print(f"{rel}: NOT intact", file=sys.stderr)
            return 2
    print("all copied files are intact" + (" -- SURVEY HALTED" if halted else ""))
    return 1 if halted else 0


def _mutate(run: _Run, mutation: Mutation) -> tuple[int, list[Failure]]:
    target = run.worktree / mutation.file
    if mutation.create is not None:
        if target.exists():
            raise AnchorError(f"{mutation.label}: {mutation.file} already exists")
        try:
            target.write_bytes(mutation.create.encode("utf-8"))
            print(f"[{mutation.label}] CREATED {mutation.file}: {mutation.create!r:.200}")
            code, failures, _ = run.pytest(mutation.label)
        finally:
            target.unlink()
            print(f"[{mutation.label}] removed; file gone = {not target.exists()}")
        return code, failures
    assert mutation.old is not None and mutation.new is not None
    data = target.read_bytes()
    mutated = apply_replace(data, mutation.old.encode("utf-8"), mutation.new.encode("utf-8"))
    snapshot = run.snapshots / f"{run.tag}_{mutation.label}_{target.name}"
    shutil.copy2(target, snapshot)
    before = _sha(target)
    try:
        target.write_bytes(mutated)
        print(
            f"[{mutation.label}] MUTATED {mutation.file}: {mutation.old!r:.150} -> {mutation.new!r:.150}"
        )
        code, failures, _ = run.pytest(mutation.label)
    finally:
        shutil.copy2(snapshot, target)
        equal = _sha(target) == before
        print(f"[{mutation.label}] restored; sha equal to before = {equal}")
        if not equal:
            raise AnchorError(f"restore mismatch, snapshot kept at {snapshot}")
    return code, failures


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run a mutation survey in a throwaway worktree.")
    parser.add_argument("spec", type=Path)
    parser.add_argument("--worktree", type=Path, required=True)
    parser.add_argument("--scratch", type=Path, required=True)
    parser.add_argument("--repo", type=Path, default=ROOT)
    parser.add_argument("--python", default=sys.executable)
    parser.add_argument("--keep", action="store_true")
    args = parser.parse_args(argv)
    try:
        spec = load_spec(args.spec)
    except SpecError as exc:
        print(f"bad spec: {exc}", file=sys.stderr)
        return 2
    return run_survey(
        spec,
        repo=args.repo,
        worktree=args.worktree,
        scratch=args.scratch,
        python=args.python,
        tag=args.spec.stem,
        keep=args.keep,
    )


if __name__ == "__main__":
    sys.exit(main())
