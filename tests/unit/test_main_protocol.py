"""R-BT, S6: the research-protocol guard at the ``backtest`` command, and the record it leaves.

``test_backtest_guard.py`` judges ``check_run`` on hand-built effective blocks. These tests judge the
HOOK: that the command asks the guard before it makes any directory, that the block it asks about is the
one the engine records (so a digest the guard accepts is the digest on the run's record), and that what
the guard decided is in the record. The world is the real one (``backtest_world.py``): a real store, real
snapshots and a real config, driven through ``argv`` as an operator drives it.

The REAL declaration is used with its out-of-sample window moved onto the world's two days (a replaced
boundary and history end, one pair), because a test cannot replay 2024 to 2026; every rule, grid and cost
is the real one. ``collect_provenance`` is patched where a test needs a deployment clone's verdict.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
from dataclasses import replace
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

import trading_bot.backtesting.protocol as protocol_module
import trading_bot.main as cli
from tests.unit.backtest_world import build_world
from tests.unit.protocol_world import PROTOCOL, REPO
from tests.unit.selection_world import RULES
from tests.unit.test_main_backtest import argv, only_record, provenance, records
from trading_bot.backtesting import selection as sel
from trading_bot.backtesting.candidate import candidate_digest, effective_settings
from trading_bot.backtesting.engine import RUN_RECORD_SCHEMA, run_backtest, select_pairs
from trading_bot.backtesting.overrides import apply_overrides, build_overrides
from trading_bot.backtesting.protocol import (
    Entry,
    Refusal,
    Variant,
    WindowClass,
    check_run,
    load_entries,
)
from trading_bot.config.settings import get_settings

OOS = ("--start", "2024-03-12", "--end", "2024-03-14")
STRADDLING = ("--start", "2024-03-10", "--end", "2024-03-14")
CANDIDATE = ("--param", "fast_period=10", "--param", "slow_period=50")


@pytest.fixture(autouse=True)
def _no_logging_setup(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep ``main`` from replacing the root handlers ``caplog`` depends on."""
    monkeypatch.setattr(cli, "setup_logging", lambda _config: None)


@pytest.fixture
def entries(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    """The real declaration, its window moved onto the world's days, and an empty entries directory."""
    narrow = replace(
        PROTOCOL,
        boundary=date(2024, 3, 12),
        history_end=date(2024, 3, 14),
        pairs=("BTCUSDT",),
    )
    directory = tmp_path / "entries"
    directory.mkdir()
    real_load_entries = load_entries
    monkeypatch.setattr(protocol_module, "load_protocol", lambda *_a, **_k: narrow)
    monkeypatch.setattr(
        protocol_module, "load_entries", lambda *_a, **_k: real_load_entries(directory)
    )
    return directory


@pytest.fixture
def deployment(monkeypatch: pytest.MonkeyPatch) -> None:
    """A deployment clone's boot verdict: ``accepted``."""
    facts = provenance(accepted=True)
    monkeypatch.setattr(cli, "collect_provenance", lambda *_a, **_k: facts)


def write_entry(directory: Path, digest: str, *, name: str = "e1", **fields: Any) -> str:
    """Commit an entry for ``digest``; returns the text written."""
    body: dict[str, Any] = {
        "entry_schema": 1,
        "id": name,
        "kind": "candidate",
        "ref": "sma_crossover",
        "candidate_digest": digest,
        "arms": ["0.05", "0.66", "1.20"],
        "status": "pending",
        "oos": None,
    }
    body.update(fields)
    text = json.dumps(body, indent=2) + "\n"
    (directory / f"{name}.json").write_text(text, encoding="utf-8")
    return text


def refusal_text(caplog: pytest.LogCaptureFixture) -> str:
    """Everything the command logged at ERROR, joined."""
    return " ".join(
        r.getMessage()
        for r in caplog.records
        if r.name == "trading_bot.main" and r.levelno >= logging.ERROR
    )


def named_digest(caplog: pytest.LogCaptureFixture) -> str:
    """The candidate digest a NO_ENTRY refusal names, asserted to be exactly one."""
    found = re.findall(r"candidate digest ([0-9a-f]{64})", refusal_text(caplog))
    assert len(found) == 1, refusal_text(caplog)
    return found[0]


def read_record(directory: Path) -> dict[str, Any]:
    loaded = json.loads((directory / "run.json").read_text(encoding="utf-8"))
    assert isinstance(loaded, dict)
    return loaded


class TestAnInSampleWindowNeedsNothing:
    def test_the_decision_is_recorded_and_no_entry_is_asked_for(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        late = replace(PROTOCOL, boundary=date(2030, 1, 1))
        monkeypatch.setattr(protocol_module, "load_protocol", lambda *_a, **_k: late)
        build_world(tmp_path)
        assert cli.main(argv(tmp_path, *OOS)) == 0
        record = read_record(only_record(tmp_path))
        assert record["schema"] == RUN_RECORD_SCHEMA == 6
        block = record["protocol"]
        assert isinstance(block, dict), block
        assert block["window_class"] == "in_sample"
        assert block["arm"] == "1.2"
        assert block["protocol_sha256"] == PROTOCOL.sha256
        assert block["entry_id"] is None and block["kind"] is None

    def test_a_missing_protocol_refuses_even_an_in_sample_run_and_leaves_nothing(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        build_world(tmp_path)
        monkeypatch.chdir(tmp_path)
        caplog.set_level(logging.INFO)
        assert cli.main(argv(tmp_path, *OOS)) == 1
        assert "cannot be read" in refusal_text(caplog)
        assert records(tmp_path) == []


class TestAnInSampleGridPointNamesItsVariant:
    """The path S6's selection and sweep rest on: the REAL command, over a grid point, in sample.

    The selection and the sweep are tested against an imitation of the record (``selection_world``); these
    drive ``cli.main`` and read back what the ENGINE wrote, so the writer and the reader cannot drift apart.
    The world's two days stand for the in-sample window (the boundary is moved to 2030).
    """

    GRID_FLAGS = (*OOS, "--stop-slippage", "1.20", *CANDIDATE)

    def run_in_sample(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, *flags: str
    ) -> dict[str, Any]:
        late = replace(PROTOCOL, boundary=date(2030, 1, 1))
        monkeypatch.setattr(protocol_module, "load_protocol", lambda *_a, **_k: late)
        build_world(tmp_path, symbols=("BTCUSDT", "ETHUSDT"))
        assert cli.main(argv(tmp_path, *flags)) == 0
        return read_record(only_record(tmp_path))

    def test_the_record_names_the_variant_the_command_line_selected(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        record = self.run_in_sample(tmp_path, monkeypatch, *self.GRID_FLAGS)
        block = record["protocol"]
        assert block["window_class"] == "in_sample" and block["arm"] == "1.2"
        assert block["entry_id"] is None and block["kind"] is None
        assert block["variant"] == {
            "family": "sma_crossover",
            "timeframe": "1h",
            "filtered": False,
            "params": {"fast_period": "10", "slow_period": "50"},
        }

    def test_the_record_the_engine_wrote_reads_back_as_a_point_run(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, deployment: None
    ) -> None:
        record = self.run_in_sample(tmp_path, monkeypatch, *self.GRID_FLAGS)
        directory = only_record(tmp_path)
        rules = replace(RULES, history_start=date(2024, 3, 12), boundary=date(2024, 3, 14))
        got = sel.read_run(directory, PROTOCOL, rules)
        assert isinstance(got, sel.PointRun), got
        assert got.variant == Variant(
            "sma_crossover", "1h", False, {"fast_period": "10", "slow_period": "50"}
        )
        assert got.run == directory.name
        assert (
            got.record_sha256 == hashlib.sha256((directory / "run.json").read_bytes()).hexdigest()
        )
        assert got.candidate_digest == record["candidate_digest"]
        assert got.trade_log_sha256 == record["results"]["trade_log_sha256"]
        assert len(got.trades) == record["results"]["trades"]
        assert got.initial_balance == Decimal(record["equity"]["initial"])
        assert got.max_drawdown == Decimal(record["metrics"]["max_drawdown"])
        assert [str(day) for day, _ in got.daily_closes] == sorted(record["equity"]["daily_closes"])

    def test_an_off_grid_run_names_no_variant_and_reads_back_as_off_grid(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, deployment: None
    ) -> None:
        flags = (
            *OOS,
            "--stop-slippage",
            "1.20",
            "--param",
            "fast_period=15",
            "--param",
            "slow_period=50",
        )
        record = self.run_in_sample(tmp_path, monkeypatch, *flags)
        assert "variant" not in record["protocol"]
        rules = replace(RULES, history_start=date(2024, 3, 12), boundary=date(2024, 3, 14))
        got = sel.read_run(only_record(tmp_path), PROTOCOL, rules)
        assert isinstance(got, sel.SkippedRun) and got.reason is sel.SkipReason.OFF_GRID


class TestAnOutOfSampleWindowIsGuarded:
    def test_a_run_that_is_not_from_a_deployment_clone_is_refused_and_leaves_nothing(
        self, tmp_path: Path, entries: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        build_world(tmp_path)
        caplog.set_level(logging.INFO)
        assert cli.main(argv(tmp_path, *OOS, *CANDIDATE)) == 1
        assert "accepted" in refusal_text(caplog)
        assert records(tmp_path) == []

    def test_without_an_entry_it_is_refused_and_the_refusal_names_the_digest(
        self,
        tmp_path: Path,
        entries: Path,
        deployment: None,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        build_world(tmp_path)
        caplog.set_level(logging.INFO)
        assert cli.main(argv(tmp_path, *OOS, *CANDIDATE)) == 1
        assert len(named_digest(caplog)) == 64
        assert records(tmp_path) == []

    def test_with_its_entry_the_candidate_runs_and_the_record_holds_what_was_decided(
        self,
        tmp_path: Path,
        entries: Path,
        deployment: None,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        build_world(tmp_path)
        caplog.set_level(logging.INFO)
        assert cli.main(argv(tmp_path, *OOS, *CANDIDATE)) == 1
        digest = named_digest(caplog)
        text = write_entry(entries, digest)
        assert cli.main(argv(tmp_path, *OOS, *CANDIDATE)) == 0
        record = read_record(only_record(tmp_path))
        assert record["evidence_eligible"] is True
        assert record["candidate_digest"] == digest
        block = record["protocol"]
        assert isinstance(block, dict), block
        assert block["window_class"] == "out_of_sample"
        assert block["kind"] == "candidate"
        assert block["entry_id"] == "e1"
        assert block["entry_sha256"] == hashlib.sha256(text.encode("utf-8")).hexdigest()
        assert block["arm"] == "1.2"
        assert block["variant"] == {
            "family": "sma_crossover",
            "timeframe": "1h",
            "filtered": False,
            "params": {"fast_period": "10", "slow_period": "50"},
        }

    def test_each_declared_arm_is_read_once_and_an_arm_cannot_be_read_twice(
        self,
        tmp_path: Path,
        entries: Path,
        deployment: None,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        build_world(tmp_path)
        caplog.set_level(logging.INFO)
        assert cli.main(argv(tmp_path, *OOS, *CANDIDATE)) == 1
        write_entry(entries, named_digest(caplog))
        assert cli.main(argv(tmp_path, *OOS, *CANDIDATE)) == 0
        assert cli.main(argv(tmp_path, *OOS, *CANDIDATE, "--stop-slippage", "0.66")) == 0
        assert cli.main(argv(tmp_path, *OOS, *CANDIDATE, "--stop-slippage", "0.05")) == 0
        assert len(records(tmp_path)) == 3
        caplog.clear()
        assert cli.main(argv(tmp_path, *OOS, *CANDIDATE, "--stop-slippage", "0.66")) == 1
        assert "once per arm" in refusal_text(caplog)
        assert len(records(tmp_path)) == 3

    def test_an_arm_the_protocol_does_not_declare_is_refused(
        self,
        tmp_path: Path,
        entries: Path,
        deployment: None,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        build_world(tmp_path)
        caplog.set_level(logging.INFO)
        assert cli.main(argv(tmp_path, *OOS, *CANDIDATE)) == 1
        write_entry(entries, named_digest(caplog))
        caplog.clear()
        assert cli.main(argv(tmp_path, *OOS, *CANDIDATE, "--stop-slippage", "0.5")) == 1
        assert "not one of the declared arms" in refusal_text(caplog)
        assert records(tmp_path) == []

    def test_a_candidate_that_is_not_a_grid_point_cannot_be_read_even_with_an_entry(
        self,
        tmp_path: Path,
        entries: Path,
        deployment: None,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        build_world(tmp_path)
        caplog.set_level(logging.INFO)
        assert cli.main(argv(tmp_path, *OOS)) == 1  # the world's own 3/8 crossover
        write_entry(entries, named_digest(caplog))
        caplog.clear()
        assert cli.main(argv(tmp_path, *OOS)) == 1
        assert "not a point of any declared family" in refusal_text(caplog)
        assert records(tmp_path) == []

    def test_a_window_that_is_not_exactly_the_declared_one_is_refused(
        self,
        tmp_path: Path,
        entries: Path,
        deployment: None,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        build_world(tmp_path)
        caplog.set_level(logging.INFO)
        assert cli.main(argv(tmp_path, *OOS, *CANDIDATE)) == 1
        write_entry(entries, named_digest(caplog))
        caplog.clear()
        assert cli.main(argv(tmp_path, *STRADDLING, *CANDIDATE)) == 1
        assert "only over exactly 2024-03-12 to 2024-03-14" in refusal_text(caplog)
        assert records(tmp_path) == []

    def test_an_entry_already_read_cannot_be_read_again(
        self,
        tmp_path: Path,
        entries: Path,
        deployment: None,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        build_world(tmp_path)
        caplog.set_level(logging.INFO)
        assert cli.main(argv(tmp_path, *OOS, *CANDIDATE)) == 1
        write_entry(entries, named_digest(caplog), status="read", oos={"records": []})
        caplog.clear()
        assert cli.main(argv(tmp_path, *OOS, *CANDIDATE)) == 1
        assert "has been read out of sample already" in refusal_text(caplog)
        assert records(tmp_path) == []

    def test_a_malformed_entry_refuses_the_run_rather_than_being_skipped(
        self,
        tmp_path: Path,
        entries: Path,
        deployment: None,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        build_world(tmp_path)
        (entries / "broken.json").write_text("{not json", encoding="utf-8")
        caplog.set_level(logging.INFO)
        assert cli.main(argv(tmp_path, *OOS, *CANDIDATE)) == 1
        assert "not valid JSON" in refusal_text(caplog)
        assert records(tmp_path) == []

    def test_a_prior_record_that_is_not_evidence_refuses_the_scan_and_the_run(
        self,
        tmp_path: Path,
        entries: Path,
        deployment: None,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        build_world(tmp_path)
        caplog.set_level(logging.INFO)
        assert cli.main(argv(tmp_path, *OOS, *CANDIDATE)) == 1
        write_entry(entries, named_digest(caplog))
        stray = tmp_path / "backtests" / "20261008T120000000000Z-0123456789ab"
        stray.mkdir(parents=True)
        (stray / "run.json").write_text(
            json.dumps({"window": {"start_date": "2024-03-12", "end_date": "2024-03-14"}}),
            encoding="utf-8",
        )
        caplog.clear()
        assert cli.main(argv(tmp_path, *OOS, *CANDIDATE)) == 1
        assert "cannot tell what it read" in refusal_text(caplog)
        assert len(records(tmp_path)) == 1


class TestTheHookJudgesTheBlockTheEngineRecords:
    def test_the_digest_the_guard_asks_about_is_the_digest_on_the_record(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The hook builds its effective block itself; a record's digest differing from it would
        make every entry unreadable or, worse, an entry bind to the wrong run."""
        late = replace(PROTOCOL, boundary=date(2030, 1, 1))
        monkeypatch.setattr(protocol_module, "load_protocol", lambda *_a, **_k: late)
        settings = build_world(tmp_path, symbols=("BTCUSDT", "ETHUSDT"))
        assert cli.main(argv(tmp_path, *OOS, "--stop-slippage", "0.66", *CANDIDATE)) == 0
        record = read_record(only_record(tmp_path))
        given = build_overrides(
            stop_slippage="0.66",
            strategy=None,
            timeframe=None,
            params=["fast_period=10", "slow_period=50"],
        )
        laid = settings.with_config(apply_overrides(settings.config, given))
        expected = effective_settings(
            laid.config,
            laid.config.backtesting,
            [(p.symbol, p.timeframe) for p in select_pairs(laid, None)],
            config_sha256=laid.config_sha256,
            overrides=given.record(),
        )
        assert record["candidate_digest"] == candidate_digest(expected)


class TestTheEngineRecordsWhatItIsGiven:
    async def test_a_run_given_no_decision_records_none(self, tmp_path: Path) -> None:
        settings = build_world(tmp_path)
        result = await run_backtest(settings, code_facts=lambda: {})
        assert result.record["protocol"] is None

    async def test_a_decision_is_recorded_whole_and_not_aliased(self, tmp_path: Path) -> None:
        settings = build_world(tmp_path)
        given: dict[str, object] = {"window_class": "in_sample", "arm": "1.2"}
        result = await run_backtest(settings, code_facts=lambda: {}, protocol=given)
        assert result.record["protocol"] == given
        assert result.record["protocol"] is not given


class TestTheCommittedBaselineEntry:
    """S5's entry, committed before any S5 run exists, names the config as it is committed."""

    def baseline(self, arm: str) -> dict[str, Any]:
        settings = get_settings(str(REPO / "config.yaml"))
        pairs = [(p.symbol, p.timeframe) for p in select_pairs(settings, None)]
        block = effective_settings(
            settings.config,
            settings.config.backtesting,
            pairs,
            config_sha256=settings.config_sha256,
            overrides={},
        )
        block["costs"] = {**block["costs"], "stop_slippage_percent": arm}
        return block

    def baseline_entry(self) -> Entry:
        """S5's entry, selected by its id (R-CI): the directory also holds the candidates' entries."""
        matching = [
            entry
            for entry in load_entries(REPO / "docs" / "research" / "entries")
            if entry.id == "s5-baseline"
        ]
        assert len(matching) == 1
        return matching[0]

    def test_the_entry_names_the_committed_configs_baseline_and_is_allowed_at_each_arm(
        self,
    ) -> None:
        """The entry's BINDING to the committed config's baseline, judged on the entry as it stood
        before the read: R-BY marked the committed entry ``read``, which the guard now refuses, so the
        entry is reset to ``pending`` in memory (ratified by R-CA). Every assertion below is the original
        one; R-CI changed only where ``committed`` comes from (selected by id, not the whole directory)."""
        committed = [replace(self.baseline_entry(), status="pending", oos=None)]
        assert [e.id for e in committed] == ["s5-baseline"]
        window = (PROTOCOL.history_start, PROTOCOL.history_end)
        for arm in ("0.05", "0.66", "1.2"):
            decision = check_run(
                PROTOCOL,
                committed,
                effective=self.baseline(arm),
                window_start=window[0],
                window_end=window[1],
                provenance_accepted=True,
                local_reads=frozenset(),
            )
            assert decision.window_class is WindowClass.STRADDLING
            assert decision.kind == "baseline"
            assert decision.entry_id == "s5-baseline"
            assert decision.arm == arm

    def test_the_entry_is_the_declared_baseline_and_is_read_with_its_three_records(self) -> None:
        """R-BY overturned this test's old ``entry.status == "pending" and entry.oos is None``."""
        entry = self.baseline_entry()
        assert entry.kind == "baseline" and entry.ref == "s5-baseline"
        assert entry.status == "read" and entry.oos is not None
        records = entry.oos["records"]
        assert sorted(records) == ["0.05", "0.66", "1.20"]
        for arm, record in records.items():
            assert re.fullmatch(r"\d{8}T\d{12}Z-[0-9a-f]{12}", record["run"]), arm
            assert re.fullmatch(r"[0-9a-f]{64}", record["run_json_sha256"]), arm
        assert entry.candidate_digest == candidate_digest(self.baseline("1.2"))

    def test_a_fresh_clones_guard_refuses_a_second_read_of_the_baseline_at_every_arm(
        self,
    ) -> None:
        """No state outside git: a clone of this commit holds no record (``local_reads`` is empty), and
        the committed entry alone refuses the baseline at each arm."""
        committed = load_entries(REPO / "docs" / "research" / "entries")
        for arm in ("0.05", "0.66", "1.2"):
            with pytest.raises(protocol_module.ProtocolRefusalError) as caught:
                check_run(
                    PROTOCOL,
                    committed,
                    effective=self.baseline(arm),
                    window_start=PROTOCOL.history_start,
                    window_end=PROTOCOL.history_end,
                    provenance_accepted=True,
                    local_reads=frozenset(),
                )
            assert caught.value.reason is Refusal.ALREADY_READ, arm
            assert "has been read out of sample already" in str(caught.value), arm

    def test_an_edit_to_the_config_makes_the_entry_refuse(self) -> None:
        """A different config digest is a different candidate: the entry must be re-made, not reused."""
        edited = self.baseline("1.2")
        edited["config_sha256"] = "0" * 64
        committed = load_entries(REPO / "docs" / "research" / "entries")
        with pytest.raises(protocol_module.ProtocolRefusalError) as caught:
            check_run(
                PROTOCOL,
                committed,
                effective=edited,
                window_start=PROTOCOL.history_start,
                window_end=PROTOCOL.history_end,
                provenance_accepted=True,
                local_reads=frozenset(),
            )
        assert caught.value.reason is Refusal.NO_ENTRY
