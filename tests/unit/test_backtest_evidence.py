"""R-AR: ``evidence_eligible``, the one door that refuses a run record that is not evidence.

The owner's ruling, verbatim: *"A backtest run record carries evidence_eligible, true only when the
provenance verdict is accepted. Every S4 to S7 comparison or decision refuses a record whose
evidence_eligible is false."* Three things are proved here: the judgement itself (exactly ``accepted``,
exactly ``True``), that a real run writes it into ``run.json`` and into the digest, and -- the part a
future author can break without a failing test elsewhere -- that no module under ``src/`` or ``scripts/``
reads a run record without calling the door.
"""

from __future__ import annotations

import ast
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pytest

from tests.unit.backtest_world import CODE, build_world
from trading_bot.backtesting.engine import (
    RUN_RECORD_SCHEMA,
    record_digest,
    run_backtest,
    write_run,
)
from trading_bot.backtesting.evidence import (
    EVIDENCE_KEY,
    RUN_RECORD_NAME,
    EvidenceRefusedError,
    is_evidence_eligible,
    load_eligible_record,
    require_evidence_eligible,
)

REPO = Path(__file__).resolve().parents[2]
GUARDS = frozenset({"require_evidence_eligible", "load_eligible_record"})
#: The modules that WRITE a run record and the one that defines the door. A module that names the
#: record and is not here must call the door. Adding a name here is a visible edit. ``main.py`` was
#: listed until R-BF (``M5m-257``): it only printed a path, and a listed module is exempt whatever
#: it does, so a ``main`` that began to read the record would have gone unchecked.
WRITERS = frozenset(
    {
        "src/trading_bot/backtesting/engine.py",
        "src/trading_bot/backtesting/evidence.py",
    }
)


def record(verdict: object = "accepted", flag: object = True, **extra: object) -> dict[str, Any]:
    return {
        "schema": RUN_RECORD_SCHEMA,
        "provenance": {"verdict": verdict, "refusal_reasons": "install_kind=editable"},
        EVIDENCE_KEY: flag,
        **extra,
    }


class TestTheJudgement:
    @pytest.mark.parametrize(
        ("verdict", "expected"),
        [
            ("accepted", True),
            ("refused", False),
            ("unrecorded", False),
            ("ACCEPTED", False),
            ("accepted ", False),
            ("", False),
            (None, False),
            (1, False),
        ],
    )
    def test_only_the_word_accepted_is_eligible(self, verdict: object, expected: bool) -> None:
        assert is_evidence_eligible({"verdict": verdict}) is expected

    def test_a_provenance_with_no_verdict_is_not_eligible(self) -> None:
        assert is_evidence_eligible({}) is False

    def test_a_true_flag_passes_and_returns_nothing(self) -> None:
        assert require_evidence_eligible(record()) is None

    @pytest.mark.parametrize("flag", [False, 0, 1, "true", "True", None, [], [True], {}])
    def test_anything_but_the_boolean_true_is_refused(self, flag: object) -> None:
        with pytest.raises(EvidenceRefusedError):
            require_evidence_eligible(record(flag=flag))

    def test_a_record_with_no_key_is_refused_as_written_before_the_ruling(self) -> None:
        old = {"schema": 3, "provenance": {"verdict": "accepted"}}
        with pytest.raises(EvidenceRefusedError) as raised:
            require_evidence_eligible(old)
        text = str(raised.value)
        assert "carries no evidence_eligible" in text and "schema 3" in text
        assert "written before R-AR" in text

    def test_the_refusal_names_the_verdict_the_reasons_and_the_source(self) -> None:
        with pytest.raises(EvidenceRefusedError) as raised:
            require_evidence_eligible(
                record("refused", False), source="data/backtests/20261009T0-abc/run.json"
            )
        text = str(raised.value)
        assert text.startswith("data/backtests/20261009T0-abc/run.json has evidence_eligible false")
        assert "'refused'" in text and "install_kind=editable" in text
        assert "deployment clone of a pushed commit" in text

    def test_a_non_boolean_flag_is_named_as_such(self) -> None:
        with pytest.raises(EvidenceRefusedError, match="which is not a boolean"):
            require_evidence_eligible(record(flag="true"))

    def test_a_missing_or_foreign_provenance_block_is_reported_as_absent(self) -> None:
        for provenance in (None, "x", 3):
            with pytest.raises(EvidenceRefusedError, match="provenance verdict 'absent'"):
                require_evidence_eligible({EVIDENCE_KEY: False, "provenance": provenance})


class TestTheDoorThatReadsAFile:
    def write(self, tmp_path: Path, content: str) -> Path:
        path = tmp_path / RUN_RECORD_NAME
        path.write_text(content, encoding="utf-8")
        return path

    def test_an_eligible_record_is_returned_whole(self, tmp_path: Path) -> None:
        body = record(note="kept")
        path = self.write(tmp_path, json.dumps(body))
        assert load_eligible_record(path) == body

    def test_an_ineligible_record_is_refused_with_its_path_in_the_message(
        self, tmp_path: Path
    ) -> None:
        path = self.write(tmp_path, json.dumps(record("refused", False)))
        with pytest.raises(EvidenceRefusedError) as raised:
            load_eligible_record(path)
        assert str(path) in str(raised.value)

    def test_a_file_that_is_not_a_record_is_refused_not_crashed_on(self, tmp_path: Path) -> None:
        with pytest.raises(EvidenceRefusedError, match="cannot be read"):
            load_eligible_record(self.write(tmp_path, "not json"))
        with pytest.raises(EvidenceRefusedError, match="not a JSON object"):
            load_eligible_record(self.write(tmp_path, "[1, 2]"))
        with pytest.raises(EvidenceRefusedError, match="cannot be read"):
            load_eligible_record(tmp_path / "missing" / RUN_RECORD_NAME)


class TestARealRunWritesIt:
    async def result(self, tmp_path: Path, facts: Mapping[str, Any]) -> Any:
        tmp_path.mkdir(parents=True, exist_ok=True)
        settings = build_world(tmp_path)
        return await run_backtest(settings, code_facts=lambda: facts)

    async def test_an_accepted_verdict_makes_the_record_eligible(self, tmp_path: Path) -> None:
        result = await self.result(tmp_path, {**CODE, "verdict": "accepted"})
        assert result.record["schema"] == RUN_RECORD_SCHEMA == 4
        assert result.record[EVIDENCE_KEY] is True
        require_evidence_eligible(result.record)

    @pytest.mark.parametrize("verdict", ["refused", "something-else"])
    async def test_a_refused_or_unknown_verdict_does_not(
        self, tmp_path: Path, verdict: str
    ) -> None:
        result = await self.result(tmp_path, {**CODE, "verdict": verdict})
        assert result.record[EVIDENCE_KEY] is False
        with pytest.raises(EvidenceRefusedError):
            require_evidence_eligible(result.record)

    async def test_facts_that_carry_no_verdict_are_unrecorded_and_not_eligible(
        self, tmp_path: Path
    ) -> None:
        result = await self.result(tmp_path, CODE)
        assert result.record["provenance"]["verdict"] == "unrecorded"
        assert result.record[EVIDENCE_KEY] is False

    async def test_the_flag_is_part_of_the_record_digest(self, tmp_path: Path) -> None:
        result = await self.result(tmp_path, {**CODE, "verdict": "accepted"})
        flipped = {**result.record, EVIDENCE_KEY: False}
        assert record_digest(flipped) != record_digest(result.record)

    async def test_the_file_a_run_writes_is_read_back_through_the_door(
        self, tmp_path: Path
    ) -> None:
        good = await self.result(tmp_path / "a", {**CODE, "verdict": "accepted"})
        write_run(good, tmp_path / "a" / "out")
        assert load_eligible_record(tmp_path / "a" / "out" / RUN_RECORD_NAME)[EVIDENCE_KEY] is True
        bad = await self.result(tmp_path / "b", {**CODE, "verdict": "refused"})
        write_run(bad, tmp_path / "b" / "out")
        with pytest.raises(EvidenceRefusedError):
            load_eligible_record(tmp_path / "b" / "out" / RUN_RECORD_NAME)


def naming_nodes(tree: ast.AST) -> list[ast.AST]:
    """The nodes that name a run record: a string with ``run.json`` in it (docstrings excepted) or
    the constant ``RUN_RECORD_NAME`` used as a name or an attribute."""
    docstrings: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            first = node.body[0] if node.body else None
            if (
                isinstance(first, ast.Expr)
                and isinstance(first.value, ast.Constant)
                and isinstance(first.value.value, str)
            ):
                docstrings.add(id(first.value))
    found: list[ast.AST] = []
    for node in ast.walk(tree):
        if (
            (
                isinstance(node, ast.Constant)
                and isinstance(node.value, str)
                and "run.json" in node.value
                and id(node) not in docstrings
            )
            or (isinstance(node, ast.Name) and node.id == "RUN_RECORD_NAME")
            or (isinstance(node, ast.Attribute) and node.attr == "RUN_RECORD_NAME")
        ):
            found.append(node)
    return found


def calls_a_guard(tree: ast.AST) -> bool:
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func
            name = func.id if isinstance(func, ast.Name) else getattr(func, "attr", None)
            if name in GUARDS:
                return True
    return False


def unguarded_readers(sources: Mapping[str, str]) -> list[str]:
    """Modules that name a run record, are not a listed writer, and never call the door."""
    bad = []
    for name, text in sorted(sources.items()):
        if name in WRITERS:
            continue
        tree = ast.parse(text)
        if naming_nodes(tree) and not calls_a_guard(tree):
            bad.append(name)
    return bad


class TestEveryConsumerGoesThroughTheDoor:
    def sources(self) -> dict[str, str]:
        files = sorted((REPO / "src" / "trading_bot").rglob("*.py")) + sorted(
            (REPO / "scripts").glob("*.py")
        )
        return {p.relative_to(REPO).as_posix(): p.read_text(encoding="utf-8") for p in files}

    def test_no_module_reads_a_run_record_without_calling_the_door(self) -> None:
        sources = self.sources()
        assert len(sources) > 80, "the scan found too few files to mean anything"
        assert unguarded_readers(sources) == []

    def test_each_listed_writer_exists_and_does_name_the_record(self) -> None:
        sources = self.sources()
        for name in WRITERS:
            assert name in sources, name
            assert naming_nodes(ast.parse(sources[name])), f"{name} no longer names the record"

    def test_the_scan_catches_a_reader_that_never_calls_the_door(self) -> None:
        reader = 'import json\ndata = json.load(open(d / "run.json"))\n'
        assert unguarded_readers({"scripts/s4_compare.py": reader}) == ["scripts/s4_compare.py"]

    def test_the_scan_catches_a_reader_that_uses_the_constant(self) -> None:
        reader = (
            "from trading_bot.backtesting.evidence import RUN_RECORD_NAME\nprint(RUN_RECORD_NAME)\n"
        )
        assert unguarded_readers({"scripts/x.py": reader}) == ["scripts/x.py"]
        attribute = "import e\nprint(e.RUN_RECORD_NAME)\n"
        assert unguarded_readers({"scripts/y.py": attribute}) == ["scripts/y.py"]

    def test_the_scan_passes_a_reader_that_calls_either_door_by_name_or_attribute(self) -> None:
        by_name = 'from e import load_eligible_record\nload_eligible_record(d / "run.json")\n'
        by_attribute = 'import e\ne.require_evidence_eligible(record)\nopen("x/run.json")\n'
        assert unguarded_readers({"scripts/a.py": by_name, "scripts/b.py": by_attribute}) == []

    def test_importing_the_door_without_calling_it_is_not_enough(self) -> None:
        lazy = 'from e import load_eligible_record\nopen("run.json")\n'
        assert unguarded_readers({"scripts/c.py": lazy}) == ["scripts/c.py"]

    def test_a_function_that_only_resembles_a_door_is_not_one(self) -> None:
        near = 'def require_evidence_eligible_x(r): ...\nrequire_evidence_eligible_x(1)\nopen("run.json")\n'
        assert unguarded_readers({"scripts/d.py": near}) == ["scripts/d.py"]

    def test_a_mention_in_a_docstring_alone_is_not_a_reader(self) -> None:
        text = '"""Reads run.json."""\n\ndef f() -> None:\n    """Also run.json."""\n'
        assert unguarded_readers({"scripts/e.py": text}) == []

    def test_a_listed_writer_is_exempt_and_an_unlisted_namesake_is_not(self) -> None:
        text = 'open("run.json", "x")\n'
        assert unguarded_readers({"src/trading_bot/backtesting/engine.py": text}) == []
        assert unguarded_readers({"src/trading_bot/other/engine.py": text}) == [
            "src/trading_bot/other/engine.py"
        ]

    def test_main_is_not_a_listed_writer(self) -> None:
        """R-BF, `M5m-257`: ``main.py`` came off the list. It prints no path to the record, and a
        ``main`` that ever reads one must call the door like any other consumer."""
        assert "src/trading_bot/main.py" not in WRITERS
        assert sorted(WRITERS) == [
            "src/trading_bot/backtesting/engine.py",
            "src/trading_bot/backtesting/evidence.py",
        ]

    def test_a_main_that_names_the_record_without_the_door_is_caught(self) -> None:
        reader = 'import json\nrecord = json.load(open(directory / "run.json"))\n'
        assert unguarded_readers({"src/trading_bot/main.py": reader}) == ["src/trading_bot/main.py"]
        with_door = reader + "from e import load_eligible_record\nload_eligible_record(p)\n"
        assert unguarded_readers({"src/trading_bot/main.py": with_door}) == []
