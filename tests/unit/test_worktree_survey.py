"""The worktree mutation survey (``scripts/worktree_survey.py``) and its pytest plugin.

``scripts/`` is not importable as a package, so both modules are loaded by path with ``scripts/`` on
``sys.path`` first: the plugin imports ``mutation_survey`` by name, which is how it meets it in the
survey's subprocess.

The test that matters most is ``TestTheHookRecordsTheRealClass``. The scratch harness this replaces
read exception types off pytest's text, scanning for names that end in ``Error``, ``Failed`` or
``Exception``, and so printed a ``decimal.InvalidOperation`` and a ``StopIteration`` as assertions
(``M5n-088``). Those two are the first rows of the table below, run through a real pytest subprocess.
"""

from __future__ import annotations

import importlib.util
import json
import shutil
import subprocess
import sys
from pathlib import Path
from types import ModuleType

import pytest

SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"


def _load(name: str) -> ModuleType:
    if str(SCRIPTS) not in sys.path:
        sys.path.insert(0, str(SCRIPTS))
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


survey = _load("worktree_survey")
hook = _load("survey_hook")


class TestQualifiedName:
    def test_a_builtin_is_bare(self) -> None:
        assert hook.qualified_name(ValueError) == "ValueError"
        assert hook.qualified_name(StopIteration) == "StopIteration"

    def test_a_library_class_carries_its_module(self) -> None:
        import decimal

        assert hook.qualified_name(decimal.InvalidOperation) == "decimal.InvalidOperation"

    def test_a_nested_class_carries_its_qualname(self) -> None:
        class Outer:
            class InnerError(Exception):
                pass

        assert hook.qualified_name(Outer.InnerError).endswith("Outer.InnerError")


_HOOK_TESTS = """\
import decimal

import pytest


def test_assertion():
    assert 1 == 2


def test_invalid_operation():
    decimal.Decimal("NaN") < decimal.Decimal(1)


def test_stop_iteration():
    next(iter(()))


def test_fail():
    pytest.fail("x")


def test_exit():
    raise SystemExit(1)


def test_key_error():
    {}["k"]


def test_unmet_raises():
    with pytest.raises(ValueError):
        pass


def test_passes():
    pass
"""


class TestTheHookRecordsTheRealClass:
    def _run(self, tmp_path: Path) -> tuple[dict[str, tuple[str, bool]], list[str]]:
        (tmp_path / "test_rows.py").write_text(_HOOK_TESTS, encoding="utf-8")
        verdicts = tmp_path / "verdicts.jsonl"
        proof = tmp_path / "proof.txt"
        env = {
            "PYTHONPATH": str(SCRIPTS),
            "SURVEY_VERDICTS": str(verdicts),
            "SURVEY_PROOF_OUT": str(proof),
            "SURVEY_PROOF_MODULES": "json,decimal",
            "SYSTEMROOT": "C:\\Windows",
        }
        subprocess.run(
            [sys.executable, "-m", "pytest", "-p", "survey_hook", "-p", "no:cacheprovider"],
            cwd=tmp_path,
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )
        rows = {}
        for line in verdicts.read_text(encoding="utf-8").splitlines():
            row = json.loads(line)
            rows[row["nodeid"].split("::")[-1]] = (row["type"], row["kill"])
        return rows, proof.read_text(encoding="utf-8").splitlines()

    def test_a_crash_named_decimal_invalid_operation_is_a_crash_and_says_so(
        self, tmp_path: Path
    ) -> None:
        rows, _ = self._run(tmp_path)
        assert rows["test_invalid_operation"] == ("decimal.InvalidOperation", False)

    def test_a_stop_iteration_is_a_crash_and_says_so(self, tmp_path: Path) -> None:
        rows, _ = self._run(tmp_path)
        assert rows["test_stop_iteration"] == ("StopIteration", False)

    def test_any_other_exception_type_is_a_crash(self, tmp_path: Path) -> None:
        rows, _ = self._run(tmp_path)
        assert rows["test_key_error"] == ("KeyError", False)

    def test_the_three_assertion_constructs_are_kills(self, tmp_path: Path) -> None:
        rows, _ = self._run(tmp_path)
        assert rows["test_assertion"] == ("AssertionError", True)
        assert rows["test_exit"] == ("SystemExit", True)
        for name in ("test_fail", "test_unmet_raises"):
            type_name, kill = rows[name]
            assert type_name.endswith("Failed")
            assert kill is True

    def test_a_passing_test_leaves_no_row(self, tmp_path: Path) -> None:
        rows, _ = self._run(tmp_path)
        assert "test_passes" not in rows
        assert len(rows) == 7

    def test_the_import_proof_names_where_each_module_came_from(self, tmp_path: Path) -> None:
        _, proof = self._run(tmp_path)
        assert [line.split("=", 1)[0] for line in proof] == ["json", "decimal"]

    def test_nothing_is_written_without_the_environment(self, tmp_path: Path) -> None:
        (tmp_path / "test_rows.py").write_text(_HOOK_TESTS, encoding="utf-8")
        subprocess.run(
            [sys.executable, "-m", "pytest", "-p", "survey_hook", "-p", "no:cacheprovider"],
            cwd=tmp_path,
            env={"PYTHONPATH": str(SCRIPTS), "SYSTEMROOT": "C:\\Windows"},
            capture_output=True,
            text=True,
            check=False,
        )
        assert sorted(p.name for p in tmp_path.iterdir() if p.is_file()) == ["test_rows.py"]


class TestApplyReplace:
    def test_one_match_is_replaced(self) -> None:
        assert survey.apply_replace(b"a b c", b"b", b"X") == b"a X c"

    def test_no_match_is_refused(self) -> None:
        with pytest.raises(survey.AnchorError, match="0 times"):
            survey.apply_replace(b"a b c", b"z", b"X")

    def test_two_matches_are_refused(self) -> None:
        with pytest.raises(survey.AnchorError, match="2 times"):
            survey.apply_replace(b"b b", b"b", b"X")

    def test_line_endings_are_preserved_byte_for_byte(self) -> None:
        data = b"one\ntwo\r\nthree\n"
        assert survey.apply_replace(data, b"two", b"2") == b"one\n2\r\nthree\n"


class TestCompare:
    def test_the_same_set_matches(self) -> None:
        got = survey.compare(survey.parse_predicted(["A::t1", "A::t2"]), {"A::t1", "A::t2"})
        assert got.verdict == "MATCH"
        assert (got.predicted, got.observed) == (2, 2)

    def test_an_extra_failure_is_more_and_is_named(self) -> None:
        got = survey.compare(survey.parse_predicted(["A::t1"]), {"A::t1", "A::t9"})
        assert got.verdict == "MORE"
        assert got.extra == frozenset({"A::t9"})
        assert got.missing == frozenset()

    def test_a_missing_failure_is_fewer_even_when_something_else_failed(self) -> None:
        got = survey.compare(survey.parse_predicted(["A::t1", "A::t2"]), {"A::t1", "A::t9"})
        assert got.verdict == "FEWER"
        assert got.missing == frozenset({"A::t2"})
        assert got.extra == frozenset({"A::t9"})

    def test_nothing_failing_when_something_was_predicted_is_fewer(self) -> None:
        assert survey.compare(survey.parse_predicted(["A::t1"]), set()).verdict == "FEWER"

    def test_a_suffix_matches_a_parametrised_id(self) -> None:
        got = survey.compare(survey.parse_predicted(["test_x[a-1]"]), {"TestA::test_x[a-1]"})
        assert got.verdict == "MATCH"

    def test_a_prefix_count_is_exact(self) -> None:
        predicted = survey.parse_predicted(["prefix:TestA::test_x|2"])
        two = {"TestA::test_x[1]", "TestA::test_x[2]"}
        assert survey.compare(predicted, two).verdict == "MATCH"
        assert survey.compare(predicted, {"TestA::test_x[1]"}).verdict == "FEWER"
        three = two | {"TestA::test_x[3]"}
        assert survey.compare(predicted, three).verdict == "MORE"

    def test_a_prefix_count_adds_to_the_predicted_total(self) -> None:
        predicted = survey.parse_predicted(["A::t1", "prefix:B::|3"])
        assert predicted.count == 4


class TestShortId:
    def test_the_file_path_is_dropped(self) -> None:
        assert survey.short_id("tests/unit/test_a.py::TestA::test_b") == "TestA::test_b"

    def test_an_id_without_a_separator_is_returned_whole(self) -> None:
        assert survey.short_id("test_a.py") == "test_a.py"


class TestReadFailures:
    def test_a_missing_file_is_no_failures(self, tmp_path: Path) -> None:
        assert survey.read_failures(tmp_path / "none.jsonl") == []

    def test_rows_are_parsed_and_blank_lines_ignored(self, tmp_path: Path) -> None:
        path = tmp_path / "v.jsonl"
        rows = [
            {"nodeid": "a.py::t", "when": "call", "type": "ValueError", "kill": False},
            {"nodeid": "a.py::u", "when": "call", "type": "AssertionError", "kill": True},
        ]
        path.write_text("\n".join(json.dumps(r) for r in rows) + "\n\n", encoding="utf-8")
        got = survey.read_failures(path)
        assert [(f.nodeid, f.type_name, f.kill) for f in got] == [
            ("a.py::t", "ValueError", False),
            ("a.py::u", "AssertionError", True),
        ]


def _spec(tmp_path: Path, body: dict[str, object]) -> Path:
    path = tmp_path / "spec.json"
    path.write_text(json.dumps(body), encoding="utf-8")
    return path


_GOOD = {
    "tests": ["tests/test_a.py"],
    "mutations": [{"label": "m1", "file": "src/a.py", "old": "x", "new": "y", "predict": ["t"]}],
}


class TestLoadSpec:
    def test_a_valid_spec_loads_with_its_defaults(self, tmp_path: Path) -> None:
        spec = survey.load_spec(_spec(tmp_path, _GOOD))
        assert spec.copy == ()
        assert spec.proof == ("trading_bot", "tests")
        assert [m.label for m in spec.mutations] == ["m1"]

    def test_a_creation_is_a_mutation(self, tmp_path: Path) -> None:
        body = dict(_GOOD, mutations=[{"label": "c", "file": "n.py", "create": "pass\n"}])
        spec = survey.load_spec(_spec(tmp_path, body))
        assert spec.mutations[0].create == "pass\n"

    @pytest.mark.parametrize(
        ("body", "message"),
        [
            ({"tests": ["t"]}, "non-empty list of mutations"),
            (dict(_GOOD, tests=[]), "at least one test path"),
            (
                dict(
                    _GOOD,
                    mutations=[
                        {"label": "a", "file": "f", "old": "1", "new": "2"},
                        {"label": "a", "file": "f", "old": "1", "new": "2"},
                    ],
                ),
                "repeats",
            ),
            (
                dict(
                    _GOOD,
                    mutations=[{"label": "a", "file": "f", "old": "1", "new": "2", "create": "c"}],
                ),
                "either old and new, or create",
            ),
            (
                dict(_GOOD, mutations=[{"label": "a", "file": "f", "old": "1"}]),
                "either old and new",
            ),
            (
                dict(_GOOD, mutations=[{"label": "a", "file": 3, "old": "1", "new": "2"}]),
                "file must",
            ),
            (dict(_GOOD, mutations=[{"file": "f", "old": "1", "new": "2"}]), "string label"),
        ],
    )
    def test_a_malformed_spec_is_refused(
        self, tmp_path: Path, body: dict[str, object], message: str
    ) -> None:
        with pytest.raises(survey.SpecError, match=message):
            survey.load_spec(_spec(tmp_path, body))

    def test_a_file_that_is_not_json_is_refused(self, tmp_path: Path) -> None:
        path = tmp_path / "spec.json"
        path.write_text("{not json", encoding="utf-8")
        with pytest.raises(survey.SpecError):
            survey.load_spec(path)

    def test_a_missing_file_is_refused(self, tmp_path: Path) -> None:
        with pytest.raises(survey.SpecError):
            survey.load_spec(tmp_path / "absent.json")


_PKG = """\
def total(a, b):
    return a + b
"""

_PKG_TESTS = """\
from pkg.calc import total


def test_adds():
    assert total(2, 3) == 5
"""


def _git(*args: str, cwd: Path) -> None:
    subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@t", *args],
        cwd=cwd,
        check=True,
        capture_output=True,
    )


@pytest.fixture
def small_repo(tmp_path: Path) -> Path:
    if shutil.which("git") is None:
        pytest.skip("git is not on PATH")
    repo = tmp_path / "repo"
    (repo / "pkg").mkdir(parents=True)
    (repo / "tests").mkdir()
    (repo / "pkg" / "__init__.py").write_bytes(b"")
    (repo / "pkg" / "calc.py").write_bytes(_PKG.encode("utf-8"))
    (repo / "tests" / "__init__.py").write_bytes(b"")
    (repo / "tests" / "test_calc.py").write_bytes(_PKG_TESTS.encode("utf-8"))
    _git("init", "-q", cwd=repo)
    _git("add", "-A", cwd=repo)
    _git("commit", "-q", "-m", "base", cwd=repo)
    return repo


def _run(
    tmp_path: Path,
    repo: Path,
    mutations: list[dict[str, object]],
    capsys: pytest.CaptureFixture[str],
) -> tuple[int, str]:
    spec = _spec(
        tmp_path,
        {"tests": ["tests/test_calc.py"], "proof": ["pkg", "tests"], "mutations": mutations},
    )
    code = survey.main(
        [
            str(spec),
            "--worktree",
            str(tmp_path / "wt"),
            "--scratch",
            str(tmp_path / "scratch"),
            "--repo",
            str(repo),
        ]
    )
    return code, capsys.readouterr().out


class TestASurveyEndToEnd:
    def test_a_kill_and_a_crash_are_told_apart_and_the_tree_is_left_as_it_was(
        self, tmp_path: Path, small_repo: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        before = (small_repo / "pkg" / "calc.py").read_bytes()
        code, out = _run(
            tmp_path,
            small_repo,
            [
                {
                    "label": "k",
                    "file": "pkg/calc.py",
                    "old": "a + b",
                    "new": "a - b",
                    "predict": ["test_adds"],
                },
                {
                    "label": "c",
                    "file": "pkg/calc.py",
                    "old": "a + b",
                    "new": "next(iter(()))",
                    "predict": ["test_adds"],
                },
            ],
            capsys,
        )
        assert code == 0, out
        assert "[k] predicted 1, observed 1: MATCH" in out
        assert "[c] predicted 1, observed 1: MATCH" in out
        assert "test_adds  [kill]" in out
        assert "test_adds  [crash StopIteration]" in out
        assert out.count("sha equal to before = True") == 2
        assert "all copied files are intact" in out
        assert (small_repo / "pkg" / "calc.py").read_bytes() == before
        assert not (tmp_path / "wt").exists()

    def test_the_import_proof_is_printed_and_is_inside_the_worktree(
        self, tmp_path: Path, small_repo: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        spec = _spec(
            tmp_path,
            {
                "tests": ["tests/test_calc.py"],
                "proof": ["pkg", "tests"],
                "mutations": [
                    {
                        "label": "k",
                        "file": "pkg/calc.py",
                        "old": "a + b",
                        "new": "a * b",
                        "predict": ["test_adds"],
                    }
                ],
            },
        )
        survey.main(
            [
                str(spec),
                "--worktree",
                str(tmp_path / "wt"),
                "--scratch",
                str(tmp_path / "s"),
                "--repo",
                str(small_repo),
            ]
        )
        out = capsys.readouterr().out
        lines = [ln for ln in out.splitlines() if ln.startswith("import proof:")]
        assert len(lines) == 2
        for line in lines:
            assert str(tmp_path / "wt").lower() in line.lower()
            assert str(small_repo).lower() not in line.lower()

    def test_a_predicted_kill_that_is_absent_halts_the_survey(
        self, tmp_path: Path, small_repo: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        code, out = _run(
            tmp_path,
            small_repo,
            [
                {
                    "label": "quiet",
                    "file": "pkg/calc.py",
                    "old": "a + b",
                    "new": "b + a",
                    "predict": ["test_adds"],
                },
                {
                    "label": "never",
                    "file": "pkg/calc.py",
                    "old": "a + b",
                    "new": "a - b",
                    "predict": ["test_adds"],
                },
            ],
            capsys,
        )
        assert code == 1
        assert "[quiet] predicted 1, observed 0: FEWER" in out
        assert "PREDICTED BUT NOT KILLED: test_adds" in out
        assert "[quiet] HALT" in out
        assert "[never]" not in out
        assert "SURVEY HALTED" in out

    def test_a_mutation_that_breaks_collection_halts_and_is_not_a_kill(
        self, tmp_path: Path, small_repo: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        code, out = _run(
            tmp_path,
            small_repo,
            [
                {
                    "label": "syntax",
                    "file": "tests/test_calc.py",
                    "old": "import total",
                    "new": "import (total",
                    "predict": ["test_adds"],
                }
            ],
            capsys,
        )
        assert code == 1
        assert "[syntax] HALT: pytest exited" in out

    def test_a_created_file_is_removed_again(
        self, tmp_path: Path, small_repo: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        code, out = _run(
            tmp_path,
            small_repo,
            [
                {
                    "label": "new",
                    "file": "tests/test_extra.py",
                    "create": "def test_extra():\n    assert False\n",
                    "predict": [],
                }
            ],
            capsys,
        )
        assert code == 0, out
        assert "[new] removed; file gone = True" in out

    def test_a_worktree_inside_the_repository_is_refused(
        self, tmp_path: Path, small_repo: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        spec = _spec(tmp_path, _GOOD)
        code = survey.main(
            [
                str(spec),
                "--worktree",
                str(small_repo / "wt"),
                "--scratch",
                str(tmp_path / "s"),
                "--repo",
                str(small_repo),
            ]
        )
        assert code == 2
        assert "must be outside the repository" in capsys.readouterr().err

    def test_a_bad_spec_is_refused_before_anything_is_made(
        self, tmp_path: Path, small_repo: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        spec = _spec(tmp_path, {"tests": []})
        code = survey.main(
            [
                str(spec),
                "--worktree",
                str(tmp_path / "wt"),
                "--scratch",
                str(tmp_path / "s"),
                "--repo",
                str(small_repo),
            ]
        )
        assert code == 2
        assert not (tmp_path / "wt").exists()
