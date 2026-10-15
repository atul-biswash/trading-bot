"""``scripts/s6_rehearsal.py``: the narrowed protocol, the commands it builds, the records it keeps, the order it runs in.

The rehearsal itself drives real subprocesses for minutes, so these tests never run it. Three things are
tested instead, each against the REAL readers: the narrowed protocol is parsed by the real ``parse_protocol``,
``parse_rules`` and ``parse_gate_rules``; the out-of-sample command line is compared with the sweep's own
builder; and the orchestration runs over ``FakeChain``, a scripted stand-in for the subprocess seam that
writes the files each real command would write (a worktree, a junction, entries, run records) so that the
order of the hops, the stop on a mismatch and the cleanup are judged on the same code the rehearsal runs.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import sys
from datetime import date
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

import s6_rehearsal as rh
import s6_sweep

from tests.unit.protocol_world import PROTOCOL_TEXT, REPO, effective
from trading_bot.backtesting import gate as gate_mod
from trading_bot.backtesting import selection as sel
from trading_bot.backtesting.candidate import candidate_digest, settings_digest
from trading_bot.backtesting.evidence import EvidenceRefusedError
from trading_bot.backtesting.protocol import ProtocolError, declaration, parse_entry, parse_protocol

START, BOUNDARY, END = date(2023, 12, 1), date(2025, 1, 1), date(2025, 4, 1)
ENTRY_OFF, ENTRY_ON = "s6-sma_crossover-4h-off", "s6-sma_crossover-4h-on"
SHA = "a" * 40


def write_record(
    directory: Path,
    *,
    entry_id: str,
    arm: str,
    window_class: str = "out_of_sample",
    flag: bool = True,
    schema: int = 6,
) -> bytes:
    """A run directory holding a ``run.json`` that passes (or, by its keywords, fails) the evidence door."""
    eff = effective(name="sma_crossover", params={"fast_period": 10, "slow_period": 50}, arm=arm)
    record = {
        "schema": schema,
        "evidence_eligible": flag,
        "provenance": {"verdict": "accepted" if flag else "refused"},
        "effective": eff,
        "candidate_digest": candidate_digest(eff),
        "settings_digest": settings_digest(eff),
        "protocol": {"entry_id": entry_id, "arm": arm, "window_class": window_class},
    }
    directory.mkdir(parents=True)
    data = json.dumps(record, sort_keys=True).encode()
    (directory / "run.json").write_bytes(data)
    return data


def narrowed(case: str = "fail", **changes: object) -> str:
    values: dict[str, object] = {"start": START, "boundary": BOUNDARY, "end": END, "case": case}
    values.update(changes)
    return rh.narrow_protocol(PROTOCOL_TEXT, **values)  # type: ignore[arg-type]


# --------------------------------------------------------------------------------------
# The narrowed protocol
# --------------------------------------------------------------------------------------
class TestNarrowing:
    def test_it_declares_two_variants_over_the_narrow_windows(self) -> None:
        protocol = parse_protocol(narrowed())
        variants = list(protocol.variants())
        assert [(v.family, v.timeframe, v.filtered) for v in variants] == [
            ("sma_crossover", "4h", False),
            ("sma_crossover", "4h", True),
        ]
        assert (protocol.history_start, protocol.boundary, protocol.history_end) == (
            START,
            BOUNDARY,
            END,
        )
        assert protocol.min_in_sample_trades == 3

    def test_the_walk_forward_tests_the_year_before_the_boundary(self) -> None:
        rules = sel.parse_rules(narrowed())
        assert rules.test_years == (2024,)
        assert rules.train_start == START

    def test_the_fail_case_keeps_the_real_thresholds(self) -> None:
        real = gate_mod.parse_gate_rules(PROTOCOL_TEXT)
        got = gate_mod.parse_gate_rules(narrowed("fail"))
        assert (got.profit_factor_min, got.trades_min, got.max_drawdown_max) == (
            real.profit_factor_min,
            real.trades_min,
            real.max_drawdown_max,
        )
        assert got.regimes_positive_min == real.regimes_positive_min

    def test_the_pass_case_takes_the_lowest_thresholds_the_rules_admit(self) -> None:
        got = gate_mod.parse_gate_rules(narrowed("pass"))
        assert str(got.profit_factor_min) == "0.0001"
        assert got.trades_min == 1
        assert str(got.max_drawdown_max) == "0.9999"
        assert got.regimes_positive_min == 1

    def test_only_the_declaration_changes_and_the_prose_is_the_real_one(self) -> None:
        text = narrowed()
        begin, end = "<!-- protocol-json:begin -->", "<!-- protocol-json:end -->"
        assert text.startswith("<!-- P118 REHEARSAL COPY")
        real_head, real_rest = PROTOCOL_TEXT.split(begin, 1)
        real_tail = real_rest.split(end, 1)[1]
        head, rest = text.removeprefix(rh._BANNER).split(begin, 1)
        assert (head, rest.split(end, 1)[1]) == (real_head, real_tail)

    def test_every_key_it_does_not_name_is_the_real_one(self) -> None:
        got, real = dict(declaration(narrowed())), dict(declaration(PROTOCOL_TEXT))
        changed = {"history", "boundary", "min_in_sample_trades", "selection", "families", "s7"}
        assert {k: v for k, v in got.items() if k not in changed} == {
            k: v for k, v in real.items() if k not in changed
        }
        assert got["selection"]["arm"] == real["selection"]["arm"]
        assert got["selection"]["ruin_max_drawdown"] == real["selection"]["ruin_max_drawdown"]

    def test_it_is_a_different_protocol_from_the_real_one(self) -> None:
        assert parse_protocol(narrowed()).sha256 != parse_protocol(PROTOCOL_TEXT).sha256

    def test_it_does_not_touch_the_real_protocol_file(self) -> None:
        before = (REPO / "docs" / "research" / "PROTOCOL.md").read_bytes()
        narrowed("pass")
        assert (REPO / "docs" / "research" / "PROTOCOL.md").read_bytes() == before

    @pytest.mark.parametrize(
        ("changes", "phrase"),
        [
            ({"case": "maybe"}, "is not one of"),
            ({"boundary": date(2025, 1, 2)}, "quarter starts"),
            ({"end": date(2025, 5, 1)}, "quarter starts"),
            ({"boundary": date(2025, 4, 1), "end": date(2025, 7, 1)}, "1 January"),
        ],
    )
    def test_it_refuses_a_window_the_rules_cannot_use(
        self, changes: dict[str, object], phrase: str
    ) -> None:
        with pytest.raises(ValueError, match=phrase):
            narrowed(**changes)

    def test_a_boundary_outside_the_history_is_refused_by_the_real_parser(self) -> None:
        with pytest.raises(ProtocolError):
            narrowed(end=date(2025, 1, 1))

    def test_an_in_sample_window_inside_one_calendar_year_is_refused_by_the_selection(self) -> None:
        # The fold tests the year before the boundary and needs a training window before it.
        with pytest.raises(sel.SelectionRulesError):
            narrowed(start=date(2024, 1, 1))


# --------------------------------------------------------------------------------------
# The commands and records the rehearsal builds
# --------------------------------------------------------------------------------------
def candidate(entry_id: str, *, filtered: bool) -> dict[str, object]:
    params: dict[str, object] = {"fast_period": 10, "slow_period": 50}
    if filtered:
        params["trend_filter_period"] = 200
    return {
        "entry_schema": 1,
        "id": entry_id,
        "kind": "candidate",
        "ref": "sma_crossover",
        "candidate_digest": hashlib.sha256(entry_id.encode()).hexdigest(),
        "arms": ["0.05", "0.66", "1.2"],
        "status": "pending",
        "oos": None,
        "selection": {
            "variant": {
                "family": "sma_crossover",
                "timeframe": "4h",
                "filtered": filtered,
                "params": params,
            }
        },
    }


class TestCommandsAndRecords:
    def test_the_out_of_sample_command_is_the_sweeps_with_the_window_and_arm_replaced(self) -> None:
        protocol = parse_protocol(narrowed())
        rules = sel.parse_rules(narrowed())
        for filtered, entry_id in ((False, ENTRY_OFF), (True, ENTRY_ON)):
            entry = candidate(entry_id, filtered=filtered)
            variant = next(v for v in protocol.variants() if v.filtered is filtered)
            sweep = s6_sweep.backtest_argv("py", variant, rules)
            got = rh.oos_argv("py", entry, "1.20", start=BOUNDARY, end=END)
            assert got[:4] == sweep[:4] == ["py", "-m", "trading_bot", "backtest"]
            assert got[4:10] == [
                "--start",
                BOUNDARY.isoformat(),
                "--end",
                END.isoformat(),
                "--stop-slippage",
                "1.20",
            ]
            assert got[10:] == sweep[10:]

    def test_the_command_carries_the_params_the_entry_holds_and_none_it_does_not(self) -> None:
        off = rh.oos_argv(
            "py", candidate(ENTRY_OFF, filtered=False), "0.05", start=BOUNDARY, end=END
        )
        on = rh.oos_argv("py", candidate(ENTRY_ON, filtered=True), "0.05", start=BOUNDARY, end=END)
        assert "trend_filter_period=200" not in " ".join(off)
        assert off.count("--param") == 2
        assert on.count("--param") == 3
        assert "trend_filter_period=200" in on

    def test_marking_an_entry_read_gives_the_shape_the_parser_and_the_gate_read(self) -> None:
        entry = candidate(ENTRY_OFF, filtered=False)
        records = {
            "1.2": ("run-c", "c" * 64),
            "0.05": ("run-a", "a" * 64),
            "0.66": ("run-b", "b" * 64),
        }
        marked = rh.mark_read(entry, records)
        parsed = parse_entry(rh.entry_bytes(marked).decode("ascii"))
        assert (parsed.status, parsed.id) == ("read", ENTRY_OFF)
        assert parsed.oos == {
            "records": {
                "0.05": {"run": "run-a", "run_json_sha256": "a" * 64},
                "0.66": {"run": "run-b", "run_json_sha256": "b" * 64},
                "1.2": {"run": "run-c", "run_json_sha256": "c" * 64},
            }
        }
        assert list(parsed.oos["records"]) == ["0.05", "0.66", "1.2"]  # type: ignore[index]
        assert entry["status"] == "pending"  # the input is not mutated
        assert entry["oos"] is None

    def test_an_entry_is_written_the_way_the_selection_writes_one(self) -> None:
        body = candidate(ENTRY_OFF, filtered=False)
        data = rh.entry_bytes(body)
        assert data == (json.dumps(body, indent=2) + "\n").encode("ascii")
        assert b"\r" not in data

    def test_the_records_found_are_this_entrys_out_of_sample_ones_with_a_canonical_arm(
        self, tmp_path: Path
    ) -> None:
        mine = write_record(tmp_path / "r1", entry_id=ENTRY_ON, arm="1.20")
        write_record(tmp_path / "r2", entry_id=ENTRY_OFF, arm="1.2")
        write_record(tmp_path / "r3", entry_id=ENTRY_ON, arm="0.05", window_class="in_sample")
        (tmp_path / "r4").mkdir()  # a directory with no record: a run cut off, or still running
        found = rh.find_oos_records(tmp_path, ENTRY_ON)
        assert found == {"1.2": ("r1", hashlib.sha256(mine).hexdigest())}
        assert rh.find_oos_records(tmp_path / "absent", ENTRY_ON) == {}

    def test_a_record_that_is_not_evidence_stops_the_search_rather_than_being_skipped(
        self, tmp_path: Path
    ) -> None:
        # The gate would refuse it, and skipping it would mark an entry read behind a record nobody judged.
        write_record(tmp_path / "r1", entry_id=ENTRY_ON, arm="1.2", flag=False)
        with pytest.raises(EvidenceRefusedError, match="evidence_eligible false"):
            rh.find_oos_records(tmp_path, ENTRY_ON)

    def test_a_record_of_an_old_schema_is_refused_too(self, tmp_path: Path) -> None:
        write_record(tmp_path / "r1", entry_id=ENTRY_ON, arm="1.2", schema=5)
        with pytest.raises(EvidenceRefusedError, match="needs schema 6"):
            rh.find_oos_records(tmp_path, ENTRY_ON)

    def test_the_boot_line_is_read_by_its_fields(self) -> None:
        line = (
            "12:00:00 INFO event=boot_provenance verdict=accepted install_kind=vcs code_intact=true"
        )
        assert rh.parse_boot_line("noise\n" + line + "\nmore") == {
            "event": "boot_provenance",
            "verdict": "accepted",
            "install_kind": "vcs",
            "code_intact": "true",
        }
        assert rh.parse_boot_line("nothing here") == {}

    def test_the_install_requirement_escapes_spaces_and_names_the_commit(self) -> None:
        url = rh.worktree_url(Path("F:/trading bot/scratch/x/wt"), SHA)
        assert url == f"binance-trading-bot @ git+file:///F:/trading%20bot/scratch/x/wt@{SHA}"


class TestExpect:
    def outcome(self, code: int = 0, text: str = "") -> rh.Outcome:
        return rh.Outcome(code, text, 0.0)

    def test_it_names_each_way_a_hop_can_differ(self) -> None:
        expect = rh.Expect(
            0, contains=("must",), absent=("never",), counts=(("one", 1),), empty=False
        )
        assert expect.mismatch(self.outcome(0, "must one")) is None
        assert "exit 3, predicted 0" in (expect.mismatch(self.outcome(3, "must one")) or "")
        assert "missing 'must'" in (expect.mismatch(self.outcome(0, "one")) or "")
        assert "unexpected 'never'" in (expect.mismatch(self.outcome(0, "must one never")) or "")
        assert "2 x 'one', predicted 1" in (expect.mismatch(self.outcome(0, "must one one")) or "")

    def test_an_empty_prediction_refuses_any_output(self) -> None:
        expect = rh.Expect(0, empty=True)
        assert expect.mismatch(self.outcome(0, "  \n")) is None
        assert "predicted none" in (expect.mismatch(self.outcome(0, "?? a")) or "")

    def test_it_describes_itself_for_the_record(self) -> None:
        text = rh.Expect(
            1, contains=("a",), absent=("b",), counts=(("c", 2),), empty=True
        ).describe()
        assert text == "exit 1; has 'a'; lacks 'b'; 2 x 'c'; no output"


# --------------------------------------------------------------------------------------
# The orchestration, over a scripted stand-in for the subprocess seam
# --------------------------------------------------------------------------------------
class FakeChain:
    """What each real command would do, as far as the rehearsal can see: its output, its status and its files."""

    def __init__(self, case: str, store: Path) -> None:
        self.case = case
        self.store = store
        self.calls: list[tuple[tuple[str, ...], Path]] = []
        self.overrides: dict[str, rh.Outcome] = {}
        self.link_removable = True
        self.damage_store = False
        self.dirty = False
        self.refusal_leaves_a_run = False
        self.done: set[tuple[str, str]] = set()

    @staticmethod
    def ok(text: str = "") -> rh.Outcome:
        return rh.Outcome(0, text, 0.0)

    def names(self) -> list[str]:
        return [" ".join(argv) for argv, _ in self.calls]

    def __call__(self, argv: object, cwd: Path, env: object) -> rh.Outcome:
        args = tuple(str(a) for a in argv)  # type: ignore[attr-defined]
        self.calls.append((args, cwd))
        text = " ".join(args)
        for marker, outcome in self.overrides.items():
            if marker in text:
                return outcome
        if "worktree add" in text:
            tree = Path(args[-2])
            (tree / "docs" / "research" / "entries").mkdir(parents=True)
            return self.ok()
        if "worktree remove" in text:
            shutil.rmtree(args[-1])
            if self.damage_store:
                next(self.store.iterdir()).unlink()
            return self.ok()
        if "mklink" in text:
            Path(args[-2]).mkdir(parents=True)
            return self.ok("Junction created")
        if args[:3] == ("cmd", "/c", "rmdir"):
            if self.link_removable:
                Path(args[-1]).rmdir()
            return self.ok()
        if args[:2] == ("git", "rev-parse"):
            return self.ok(SHA + "\n")
        if args[:3] == ("git", "status", "--porcelain"):
            if self.dirty:
                return self.ok(
                    f"?? docs/research/selection.json\n?? docs/research/entries/{ENTRY_OFF}.json\n?? docs/research/entries/{ENTRY_ON}.json\n"
                )
            return self.ok()
        if "commit" in args:
            self.dirty = False
            return self.ok("[detached HEAD] x")
        if (
            args[:2] == ("git", "add")
            or args[1:3] == ("-m", "venv")
            or args[1:4] == ("-m", "pip", "install")
        ):
            return self.ok()
        if "trading_bot strategies" in text:
            return self.ok(
                f"event=boot_provenance verdict=accepted install_kind=vcs code_intact=true code_commit={SHA} "
                "checkout_dirty=false commits_agree=true config_tracked=true\n"
            )
        if "s6_sweep.py" in text:
            return self.ok(
                "S6 SWEEP LEDGER\n  variants declared 2; with a sealed evidence-eligible record 2\n"
                "  parallel check: the trade-log digests are equal\n  DUPLICATED k: a, b\n  COMPLETE\n"
            )
        if "s6_select.py" in text:
            return self.select(args, cwd)
        if "trading_bot backtest" in text:
            return self.backtest(args, cwd)
        if "s7_gate.py" in text:
            return self.gate()
        raise AssertionError(f"the fake does not know {text}")

    def select(self, args: tuple[str, ...], cwd: Path) -> rh.Outcome:
        report = (
            "S6 SELECTION (x)\n  variants declared 2; with a run 2; duplicated 1; skipped 0\n"
            "  cells with a candidate 2 of 2\n"
        )
        if "--out" not in args:
            return self.ok(report)
        entries = cwd / "docs" / "research" / "entries"
        (cwd / "docs" / "research" / "selection.json").write_bytes(b"{}\n")
        lines = [f"selection file docs/research/selection.json sha256 {'f' * 64} (3 bytes)"]
        for entry_id, filtered in ((ENTRY_OFF, False), (ENTRY_ON, True)):
            (entries / f"{entry_id}.json").write_bytes(
                rh.entry_bytes(candidate(entry_id, filtered=filtered))
            )
            lines.append(f"entry docs/research/entries/{entry_id}.json")
        self.dirty = True
        return self.ok(report + "\n".join(lines) + "\n")

    def backtest(self, args: tuple[str, ...], cwd: Path) -> rh.Outcome:
        arm = args[args.index("--stop-slippage") + 1]
        entry_id = ENTRY_ON if any("trend_filter_period" in a for a in args) else ENTRY_OFF
        body = json.loads(
            (cwd / "docs" / "research" / "entries" / f"{entry_id}.json").read_text("utf-8")
        )
        if body["status"] == "read":
            return rh.Outcome(
                1, f"[already_read] entry {entry_id!r} has been read out of sample already", 0.0
            )
        if (entry_id, arm) in self.done:
            if self.refusal_leaves_a_run:
                (cwd / "data" / "backtests" / "a-stray-run").mkdir()
            return rh.Outcome(1, "[local_prior_read] a candidate is read once per arm.", 0.0)
        self.done.add((entry_id, arm))
        run = cwd / "data" / "backtests" / f"20250101T00000{len(self.done)}Z-{entry_id}-{arm}"
        write_record(run, entry_id=entry_id, arm=arm)
        return self.ok("done\n")

    def gate(self) -> rh.Outcome:
        if self.case == "pass":
            rows = "".join(f"CANDIDATE {e}\n  S7: PASS\n" for e in (ENTRY_OFF, ENTRY_ON))
            return self.ok(
                "S7 DECISION GATE\n" + rows + "S7 SUMMARY: 2 of 2 candidates read PASS\n"
            )
        rows = "".join(
            f"CANDIDATE {e}\n  NOT MET  trades: 7  (threshold >= 100)\n  S7: FAIL\n"
            for e in (ENTRY_OFF, ENTRY_ON)
        )
        return self.ok("S7 DECISION GATE\n" + rows + "S7 SUMMARY: 0 of 2 candidates read PASS\n")


@pytest.fixture
def world(tmp_path: Path) -> tuple[Path, Path]:
    store = tmp_path / "store"
    store.mkdir()
    for index in range(3):
        (store / f"f{index}").write_bytes(b"x")
    return tmp_path / "root", store


def make(case: str, world: tuple[Path, Path]) -> tuple[rh.Rehearsal, FakeChain]:
    root, store = world
    chain = FakeChain(case, store)
    config = rh.Config(
        repo=REPO, root=root, store=store, python="python", start=START, boundary=BOUNDARY, end=END
    )
    return rh.Rehearsal(case, config, run=chain, echo=lambda _line: None), chain


@pytest.mark.parametrize("case", rh.CASES)
class TestTheCase:
    def test_it_runs_every_hop_in_order_and_matches_every_prediction(
        self, case: str, world: tuple[Path, Path]
    ) -> None:
        rehearsal, chain = make(case, world)
        rehearsal.go(PROTOCOL_TEXT)
        rehearsal.cleanup()
        names = [r.name for r in rehearsal.records]
        assert all(r.matched for r in rehearsal.records)
        assert names[0] == "worktree-add"
        order = [
            "install-by-commit",
            "sweep",
            "select-report",
            "select-write",
            "install-at-entries",
            f"oos-{ENTRY_OFF}-0.05",
            f"oos-{ENTRY_ON}-1.20",
            "second-read-same-arm",
            "install-at-read",
            "read-after-read",
            "s7-gate",
            "junction-remove",
            "worktree-remove",
            "store-untouched",
        ]
        assert [names.index(n) for n in order] == sorted(names.index(n) for n in order)
        assert names.count("sweep") == 1
        assert sum(1 for n in names if n.startswith("oos-") and "records" not in n) == 6
        assert len(chain.done) == 6

    def test_the_junction_is_removed_by_itself_before_the_worktree(
        self, case: str, world: tuple[Path, Path]
    ) -> None:
        rehearsal, chain = make(case, world)
        rehearsal.go(PROTOCOL_TEXT)
        rehearsal.cleanup()
        texts = chain.names()
        first_rmdir = next(i for i, t in enumerate(texts) if t.startswith("cmd /c rmdir"))
        remove = next(i for i, t in enumerate(texts) if "worktree remove" in t)
        assert first_rmdir < remove
        assert texts[first_rmdir].endswith(str(rehearsal.link))
        assert not rehearsal.wt.exists()

    def test_every_hop_is_kept_with_the_digest_of_its_output(
        self, case: str, world: tuple[Path, Path]
    ) -> None:
        rehearsal, _ = make(case, world)
        rehearsal.go(PROTOCOL_TEXT)
        lines = [
            json.loads(x) for x in (rehearsal.base / "hops.jsonl").read_text("ascii").splitlines()
        ]
        assert len(lines) == len(rehearsal.records)
        for line in lines:
            kept = (
                rehearsal.base / "out" / f"{line['number']:02d}-{line['name']}.txt"
            ).read_bytes()
            assert line["output_sha256"] == hashlib.sha256(kept).hexdigest()
            assert line["expected"] and line["matched"] is True
            assert (line["kind"] == "command") == bool(line["argv"])

    def test_the_entries_are_marked_read_and_the_gate_reads_them_back(
        self, case: str, world: tuple[Path, Path]
    ) -> None:
        rehearsal, _ = make(case, world)
        rehearsal.go(PROTOCOL_TEXT)
        for entry_id in (ENTRY_OFF, ENTRY_ON):
            path = rehearsal.wt / "docs" / "research" / "entries" / f"{entry_id}.json"
            entry = parse_entry(path.read_text("utf-8"))
            assert entry.status == "read"
            assert sorted(entry.oos["records"]) == ["0.05", "0.66", "1.2"]  # type: ignore[index]

    def test_a_hop_that_does_not_match_stops_the_case_and_keeps_the_worktree(
        self, case: str, world: tuple[Path, Path]
    ) -> None:
        rehearsal, chain = make(case, world)
        chain.overrides["s6_sweep.py"] = rh.Outcome(0, "variants declared 2\n  NOT COMPLETE\n", 0.0)
        with pytest.raises(rh.HopMismatchError) as caught:
            rehearsal.go(PROTOCOL_TEXT)
        assert caught.value.record.name == "sweep"
        assert rehearsal.records[-1].matched is False
        assert not any("s6_select.py" in t for t in chain.names())
        assert rehearsal.wt.exists()

    def test_a_junction_that_will_not_go_stops_the_cleanup_before_the_worktree_is_touched(
        self, case: str, world: tuple[Path, Path]
    ) -> None:
        rehearsal, chain = make(case, world)
        rehearsal.go(PROTOCOL_TEXT)
        chain.link_removable = False
        with pytest.raises(rh.HopMismatchError) as caught:
            rehearsal.cleanup()
        assert caught.value.record.name == "junction-gone"
        assert not any("worktree remove" in t for t in chain.names())
        assert rehearsal.wt.exists()

    def test_a_store_that_lost_a_file_is_a_mismatch(
        self, case: str, world: tuple[Path, Path]
    ) -> None:
        rehearsal, chain = make(case, world)
        rehearsal.go(PROTOCOL_TEXT)
        chain.damage_store = True
        with pytest.raises(rh.HopMismatchError) as caught:
            rehearsal.cleanup()
        assert caught.value.record.name == "store-untouched"
        assert "3 before, 2 after" in caught.value.record.detail

    def test_the_gate_prediction_is_the_cases_own(
        self, case: str, world: tuple[Path, Path]
    ) -> None:
        rehearsal, chain = make(case, world)
        wrong = (
            "S7 SUMMARY: 0 of 2 candidates read PASS\n"
            if case == "pass"
            else "S7 SUMMARY: 2 of 2 candidates read PASS\n"
        )
        chain.overrides["s7_gate.py"] = rh.Outcome(0, "S7 DECISION GATE\n" + wrong, 0.0)
        with pytest.raises(rh.HopMismatchError) as caught:
            rehearsal.go(PROTOCOL_TEXT)
        assert caught.value.record.name == "s7-gate"

    def test_every_reinstall_forces_the_new_commit_over_the_old_one(
        self, case: str, world: tuple[Path, Path]
    ) -> None:
        # MEASURED at P118: a plain pip install of a new commit into a venv that holds the package keeps
        # the OLD commit and exits 0, and the boot then refuses (commits_agree=false).
        rehearsal, chain = make(case, world)
        rehearsal.go(PROTOCOL_TEXT)
        installs = [
            args
            for args, _ in chain.calls
            if args[1:4] == ("-m", "pip", "install") and "@" in args[-1]
        ]
        assert len(installs) == 3  # after the narrowed protocol, the entries, and the read marking
        for args in installs:
            assert "--force-reinstall" in args and "--no-deps" in args
            assert args[-1] == rh.worktree_url(rehearsal.wt, SHA)

    def test_a_dirty_checkout_after_a_step_is_a_mismatch(
        self, case: str, world: tuple[Path, Path]
    ) -> None:
        rehearsal, chain = make(case, world)
        chain.overrides["status --porcelain"] = rh.Outcome(0, "?? stray.txt\n", 0.0)
        with pytest.raises(rh.HopMismatchError) as caught:
            rehearsal.go(PROTOCOL_TEXT)
        assert caught.value.record.name == "boot-after-narrowing-status"
        assert "predicted none" in caught.value.record.detail

    @pytest.mark.parametrize(
        ("field", "wrong"),
        [
            ("verdict", "refused"),
            ("install_kind", "editable"),
            ("code_intact", "false"),
            ("checkout_dirty", "true"),
            ("commits_agree", "false"),
            ("config_tracked", "false"),
            ("code_commit", "b" * 40),
        ],
    )
    def test_a_boot_that_is_not_accepted_in_any_field_is_a_mismatch(
        self, case: str, field: str, wrong: str, world: tuple[Path, Path]
    ) -> None:
        rehearsal, chain = make(case, world)
        good = {
            "verdict": "accepted",
            "install_kind": "vcs",
            "code_intact": "true",
            "code_commit": SHA,
            "checkout_dirty": "false",
            "commits_agree": "true",
            "config_tracked": "true",
        }
        line = " ".join(f"{k}={wrong if k == field else v}" for k, v in good.items())
        chain.overrides["trading_bot strategies"] = rh.Outcome(
            0, f"event=boot_provenance {line}\n", 0.0
        )
        with pytest.raises(rh.HopMismatchError) as caught:
            rehearsal.go(PROTOCOL_TEXT)
        assert caught.value.record.name == "boot-after-narrowing-provenance"
        assert field in caught.value.record.detail

    def test_a_refused_second_read_that_leaves_a_run_behind_is_a_mismatch(
        self, case: str, world: tuple[Path, Path]
    ) -> None:
        rehearsal, chain = make(case, world)
        chain.refusal_leaves_a_run = True
        with pytest.raises(rh.HopMismatchError) as caught:
            rehearsal.go(PROTOCOL_TEXT)
        assert caught.value.record.name == "second-read-left-no-run"
        assert "a-stray-run" in caught.value.record.detail


class TestTheCommand:
    def test_a_root_inside_the_repository_is_refused(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        store = tmp_path / "s"
        store.mkdir()
        status = rh.main(
            ["--root", str(REPO / "scratch_x"), "--store", str(store)], run=FakeChain("fail", store)
        )
        assert status == rh.EXIT_REFUSED
        assert "outside the repository" in capsys.readouterr().err

    def test_a_missing_store_is_refused(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        status = rh.main(
            ["--root", str(tmp_path / "r"), "--store", str(tmp_path / "none")],
            run=FakeChain("fail", tmp_path),
        )
        assert status == rh.EXIT_REFUSED
        assert "is not a directory" in capsys.readouterr().err

    def test_an_existing_worktree_is_refused_not_overwritten(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        store = tmp_path / "s"
        store.mkdir()
        (tmp_path / "r" / "fail" / "wt").mkdir(parents=True)
        status = rh.main(
            ["--root", str(tmp_path / "r"), "--store", str(store), "--case", "fail"],
            run=FakeChain("fail", store),
        )
        assert status == rh.EXIT_REFUSED
        assert "--clean-only" in capsys.readouterr().err

    def test_both_cases_run_and_each_worktree_is_removed(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        store = tmp_path / "s"
        store.mkdir()
        (store / "f").write_bytes(b"x")
        chain = FakeChain("pass", store)

        def run(argv: object, cwd: Path, env: object) -> rh.Outcome:
            case = "pass" if "pass" in Path(cwd).parts else "fail"
            if case != chain.case and Path(cwd).is_relative_to(tmp_path / "r"):
                chain.case = case
                chain.done.clear()  # a second worktree is a second clone: its own records
            return chain(argv, cwd, env)

        status = rh.main(["--root", str(tmp_path / "r"), "--store", str(store)], run=run)
        out = capsys.readouterr().out
        assert status == 0
        assert "[pass] DONE" in out and "[fail] DONE" in out
        assert not (tmp_path / "r" / "pass" / "wt").exists()
        assert not (tmp_path / "r" / "fail" / "wt").exists()

    def test_a_mismatch_ends_the_command_with_status_one_and_keeps_the_worktree(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        store = tmp_path / "s"
        store.mkdir()
        chain = FakeChain("fail", store)
        chain.overrides["s6_sweep.py"] = rh.Outcome(2, "REFUSED", 0.0)
        status = rh.main(
            ["--root", str(tmp_path / "r"), "--store", str(store), "--case", "fail"], run=chain
        )
        assert status == rh.EXIT_MISMATCH
        assert "STOPPED" in capsys.readouterr().out
        assert (tmp_path / "r" / "fail" / "wt").exists()

    def test_clean_only_removes_a_kept_worktree(self, tmp_path: Path) -> None:
        store = tmp_path / "s"
        store.mkdir()
        chain = FakeChain("fail", store)
        chain.overrides["s6_sweep.py"] = rh.Outcome(2, "REFUSED", 0.0)
        root = tmp_path / "r"
        rh.main(["--root", str(root), "--store", str(store), "--case", "fail"], run=chain)
        del chain.overrides["s6_sweep.py"]
        status = rh.main(
            ["--root", str(root), "--store", str(store), "--case", "fail", "--clean-only"],
            run=chain,
        )
        assert status == 0
        assert not (root / "fail" / "wt").exists()
