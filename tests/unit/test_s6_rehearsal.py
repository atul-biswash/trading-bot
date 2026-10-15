"""``scripts/s6_rehearsal.py``, first part: the narrowed protocol, the commands it builds, the records it reads.

The narrowed protocol is parsed by the REAL ``parse_protocol``, ``parse_rules`` and ``parse_gate_rules``, and
the out-of-sample command line is compared with the sweep's own builder, so neither can drift from the code
that reads it. The orchestration and its tests are the next commit's.
"""

from __future__ import annotations

import hashlib
import json
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
