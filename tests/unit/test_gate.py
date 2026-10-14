"""``backtesting/gate.py``: S7's thresholds at their boundaries, and every refusal, one broken field at a time.

The default candidate of ``gate_world`` PASSES, so each test below breaks (or moves) exactly one thing and
asserts the one consequence: a threshold test moves a figure across its boundary and watches that criterion
and only that criterion change; a refusal test breaks one field of one record and asserts the refusal that
names it. The thresholds are read from the REAL ``PROTOCOL.md``.

The worked defaults. Gate arm: 300 wins of +20 and 100 losses of -10 on a quote of 1,000, so the return
profit factor is 2 x 300 / 100 = 6 (and USDT 6), 400 trades, drawdown 0.10, regimes +100 / -50 / +30.
Boundary rows: a return profit factor of exactly 1.3 is 65 wins and 100 losses (2 x 65 / 100); 64 wins is 1.28.
"""

from __future__ import annotations

import json
from dataclasses import replace
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from tests.unit.gate_world import (
    ENTRY_ID,
    GATE_RULES,
    VARIANT,
    build_candidate,
    make_oos_run,
)
from tests.unit.protocol_world import PROTOCOL, PROTOCOL_TEXT
from tests.unit.selection_world import with_selection
from trading_bot.backtesting import gate
from trading_bot.backtesting.protocol import ProtocolError, parse_entry

D = Decimal


def judge(tmp_path: Path, **kwargs: Any) -> gate.CandidateResult:
    entry, backtests, _ = build_candidate(tmp_path, **kwargs)
    report = gate.evaluate([entry], backtests, GATE_RULES)
    assert len(report.results) == 1
    return report.results[0]


def met(result: gate.CandidateResult) -> dict[str, bool]:
    return {c.name: c.met for c in result.criteria}


RETURN_PF = "profit factor from per-trade returns"
USDT_PF = "profit factor in USDT"
TRADES = "trades"
DRAWDOWN = "maximum drawdown (per bar)"
REGIMES = "regimes with a positive net result"


def refusal(tmp_path: Path, match: str, **kwargs: Any) -> None:
    entry, backtests, _ = build_candidate(tmp_path, **kwargs)
    with pytest.raises(gate.GateRefusedError, match=match):
        gate.evaluate([entry], backtests, GATE_RULES)


# --------------------------------------------------------------------------------------
# The rules
# --------------------------------------------------------------------------------------
class TestTheRulesAreTheRulings:
    def test_the_real_protocol_gives_the_thresholds_the_owner_ruled(self) -> None:
        """R-D: 1.3, 100, 20 percent, two of three regimes; R-B2: the 1.20 arm; R-BW: the window and 10,000."""
        r = GATE_RULES
        assert (r.profit_factor_min, r.trades_min, r.max_drawdown_max, r.regimes_positive_min) == (
            D("1.3"),
            100,
            D("0.20"),
            2,
        )
        assert r.gate_arm == "1.2" and r.arms == ("0.05", "0.66", "1.2")
        assert (r.window_start, r.window_end) == (date(2024, 1, 1), date(2026, 10, 1))
        assert r.initial_balance == D(10000)
        assert r.variants_declared == 216 and r.protocol_sha256 == PROTOCOL.sha256
        assert r.regime_labels_sha256 == PROTOCOL.regime_labels_sha256

    def test_the_s5_reports_printed_thresholds_are_these_ones(self) -> None:
        import sys

        sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
        import s5_report

        assert {
            "profit_factor_net": GATE_RULES.profit_factor_min,
            "trades": GATE_RULES.trades_min,
            "max_drawdown": GATE_RULES.max_drawdown_max,
            "regimes_positive": GATE_RULES.regimes_positive_min,
        } == s5_report.S7_THRESHOLDS

    @pytest.mark.parametrize(
        ("change", "message"),
        [
            (lambda d: d.pop("s7"), "is absent"),
            (lambda d: d["s7"].update(extra=1), "has keys"),
            (lambda d: d["s7"].pop("trades_min"), "has keys"),
            (lambda d: d["s7"].update(profit_factor_min=1.3), "written as text"),
            (lambda d: d["s7"].update(profit_factor_min="x"), "not a number"),
            (lambda d: d["s7"].update(profit_factor_min="NaN"), "not finite"),
            (lambda d: d["s7"].update(profit_factor_min="0"), "not positive"),
            (lambda d: d["s7"].update(trades_min=0), "below 1"),
            (lambda d: d["s7"].update(trades_min=True), "not an integer"),
            (lambda d: d["s7"].update(trades_min="100"), "not an integer"),
            (lambda d: d["s7"].update(max_drawdown_max="0"), r"outside \(0, 1\)"),
            (lambda d: d["s7"].update(max_drawdown_max="1"), r"outside \(0, 1\)"),
            (lambda d: d["s7"].update(regimes_positive_min=0), "outside 1 to 3"),
            (lambda d: d["s7"].update(regimes_positive_min=4), "outside 1 to 3"),
        ],
    )
    def test_an_s7_block_that_is_not_the_protocols_is_refused(
        self, change: Any, message: str
    ) -> None:
        with pytest.raises(gate.GateRulesError, match=message):
            gate.parse_gate_rules(with_selection(change))

    def test_a_declaration_the_protocol_parser_refuses_is_refused_as_that(self) -> None:
        with pytest.raises(ProtocolError):
            gate.parse_gate_rules("nothing here")

    def test_the_thresholds_come_from_the_declaration_not_the_code(self) -> None:
        rules = gate.parse_gate_rules(with_selection(lambda d: d["s7"].update(trades_min=7)))
        assert rules.trades_min == 7


# --------------------------------------------------------------------------------------
# The thresholds, each at its boundary
# --------------------------------------------------------------------------------------
class TestAPassingCandidate:
    def test_every_criterion_is_met_and_it_passes(self, tmp_path: Path) -> None:
        result = judge(tmp_path)
        assert result.passed and all(met(result).values())
        assert result.gate.arm == "1.2" and result.gate.trades == 400
        assert result.gate.return_profit_factor == D(6) and result.gate.usdt_profit_factor == D(6)
        assert result.gate.max_drawdown == D("0.10") and result.gate.regimes_positive == 2
        assert [a.arm for a in result.arms] == ["0.05", "0.66", "1.2"]


class TestTheReturnProfitFactor:
    def test_exactly_at_the_threshold_is_met(self, tmp_path: Path) -> None:
        result = judge(tmp_path, common={"wins": 65, "losses": 100})
        assert result.gate.return_profit_factor == D("1.3")
        assert met(result)[RETURN_PF] is True

    def test_just_under_it_is_not_met_and_only_that_criterion_moves(self, tmp_path: Path) -> None:
        result = judge(tmp_path, common={"wins": 64, "losses": 100})
        assert result.gate.return_profit_factor == D("1.28")
        assert met(result)[RETURN_PF] is False
        assert [name for name, ok in met(result).items() if not ok] == [RETURN_PF]
        assert not result.passed


class TestTheUsdtProfitFactor:
    def test_exactly_at_the_threshold_is_met(self, tmp_path: Path) -> None:
        assert met(judge(tmp_path, per_arm={"1.2": {"usdt": "1.3"}}))[USDT_PF] is True

    def test_just_under_it_is_not_met_whatever_the_return_figure_says(self, tmp_path: Path) -> None:
        """R-CJ: BOTH must be at least 1.3. The return figure here is 6."""
        result = judge(tmp_path, per_arm={"1.2": {"usdt": "1.299999"}})
        assert met(result)[RETURN_PF] is True and met(result)[USDT_PF] is False
        assert not result.passed

    def test_the_return_figure_failing_alone_also_fails_it(self, tmp_path: Path) -> None:
        """The reverse: USDT is fine (6) and the return figure is 1.28."""
        result = judge(tmp_path, per_arm={"1.2": {"wins": 64, "losses": 100}})
        assert met(result)[USDT_PF] is True and met(result)[RETURN_PF] is False
        assert not result.passed

    def test_no_losing_trade_is_undefined_and_does_not_meet_it(self, tmp_path: Path) -> None:
        result = judge(tmp_path, per_arm={"1.2": {"usdt": None, "wins": 300, "losses": 0}})
        assert result.gate.usdt_profit_factor is None and result.gate.return_profit_factor is None
        figures = {c.name: c.figure for c in result.criteria}
        assert figures[USDT_PF] == "undefined (no losing trade)" == figures[RETURN_PF]
        assert met(result)[USDT_PF] is False and met(result)[RETURN_PF] is False


class TestTheTradeCount:
    def test_a_hundred_trades_are_enough(self, tmp_path: Path) -> None:
        result = judge(tmp_path, per_arm={"1.2": {"wins": 65, "losses": 35}})
        assert result.gate.trades == 100 and met(result)[TRADES] is True

    def test_ninety_nine_are_not(self, tmp_path: Path) -> None:
        result = judge(tmp_path, per_arm={"1.2": {"wins": 64, "losses": 35}})
        assert result.gate.trades == 99 and met(result)[TRADES] is False
        assert [name for name, ok in met(result).items() if not ok] == [TRADES]


class TestTheDrawdown:
    def test_exactly_twenty_percent_is_met(self, tmp_path: Path) -> None:
        assert met(judge(tmp_path, per_arm={"1.2": {"drawdown": "0.20"}}))[DRAWDOWN] is True

    def test_a_hair_over_is_not(self, tmp_path: Path) -> None:
        result = judge(tmp_path, per_arm={"1.2": {"drawdown": "0.2000001"}})
        assert met(result)[DRAWDOWN] is False and not result.passed


class TestTheRegimes:
    def test_two_positive_regimes_are_enough(self, tmp_path: Path) -> None:
        result = judge(
            tmp_path,
            per_arm={"1.2": {"regime_net": {"rising": "1", "falling": "-1", "sideways": "1"}}},
        )
        assert result.gate.regimes_positive == 2 and met(result)[REGIMES] is True

    def test_one_is_not(self, tmp_path: Path) -> None:
        result = judge(
            tmp_path,
            per_arm={"1.2": {"regime_net": {"rising": "1", "falling": "-1", "sideways": "-1"}}},
        )
        assert result.gate.regimes_positive == 1 and met(result)[REGIMES] is False

    def test_a_regime_with_a_net_of_exactly_zero_is_not_positive(self, tmp_path: Path) -> None:
        result = judge(
            tmp_path,
            per_arm={"1.2": {"regime_net": {"rising": "1", "falling": "0", "sideways": "0"}}},
        )
        assert result.gate.regimes_positive == 1 and met(result)[REGIMES] is False

    def test_all_three_positive_pass(self, tmp_path: Path) -> None:
        result = judge(
            tmp_path,
            per_arm={"1.2": {"regime_net": {"rising": "1", "falling": "1", "sideways": "1"}}},
        )
        assert result.gate.regimes_positive == 3 and met(result)[REGIMES] is True


class TestOnlyTheGateArmDecides:
    def test_failing_information_arms_do_not_fail_a_passing_gate_arm(self, tmp_path: Path) -> None:
        bad = {
            "wins": 10,
            "losses": 100,
            "usdt": "0.1",
            "drawdown": "0.9",
            "regime_net": {"rising": "-1", "falling": "-1", "sideways": "-1"},
        }
        result = judge(tmp_path, per_arm={"0.05": bad, "0.66": bad})
        assert result.passed
        assert [a.trades for a in result.arms] == [110, 110, 400]

    def test_a_failing_gate_arm_fails_though_both_information_arms_pass(
        self, tmp_path: Path
    ) -> None:
        result = judge(tmp_path, per_arm={"1.2": {"usdt": "0.5"}})
        assert not result.passed and all(a.usdt_profit_factor == D(6) for a in result.arms[:2])


# --------------------------------------------------------------------------------------
# Every refusal
# --------------------------------------------------------------------------------------
class TestRefusal1NotEvidence:
    def test_a_record_that_is_not_evidence_eligible(self, tmp_path: Path) -> None:
        refusal(tmp_path, "refusal 1, not evidence", per_arm={"1.2": {"flag": False}})

    def test_a_record_older_than_schema_6(self, tmp_path: Path) -> None:
        refusal(tmp_path, "refusal 1, not evidence", per_arm={"0.05": {"schema": 5}})

    def test_a_run_directory_that_is_not_there(self, tmp_path: Path) -> None:
        _, backtests, body = build_candidate(tmp_path)
        body["oos"]["records"]["0.66"]["run"] = "does-not-exist"
        with pytest.raises(gate.GateRefusedError, match="refusal 1, not evidence"):
            gate.evaluate([parse_entry(json.dumps(body))], backtests, GATE_RULES)


class TestRefusal2NotTheCandidatesOutOfSampleRead:
    def test_no_protocol_block(self, tmp_path: Path) -> None:
        refusal(
            tmp_path, "refusal 2: .* carries no protocol block", per_arm={"1.2": {"protocol": None}}
        )

    @pytest.mark.parametrize("window_class", ["in_sample", "straddling"])
    def test_a_run_that_is_not_out_of_sample(self, tmp_path: Path, window_class: str) -> None:
        refusal(
            tmp_path,
            f"refusal 2: .* is a '{window_class}' run",
            per_arm={"1.2": {"window_class": window_class}},
        )

    def test_a_run_decided_for_another_entry(self, tmp_path: Path) -> None:
        refusal(
            tmp_path,
            "refusal 2: .* decided for entry 'someone-else'",
            per_arm={"0.66": {"entry_id": "someone-else"}},
        )

    def test_a_baseline_read(self, tmp_path: Path) -> None:
        refusal(tmp_path, "refusal 2: .*'baseline'", per_arm={"0.05": {"kind": "baseline"}})

    def test_a_record_that_names_no_variant(self, tmp_path: Path) -> None:
        protocol = {
            "window_class": "out_of_sample",
            "kind": "candidate",
            "entry_id": ENTRY_ID,
            "protocol_sha256": PROTOCOL.sha256,
            "arm": "1.2",
        }
        refusal(
            tmp_path,
            "refusal 2: .* names no declared variant",
            per_arm={"1.2": {"protocol": protocol}},
        )


class TestRefusal3AnotherProtocol:
    def test_a_run_made_under_a_different_protocol_digest(self, tmp_path: Path) -> None:
        refusal(
            tmp_path,
            "refusal 3: .* a run made before an amendment",
            per_arm={"1.2": {"protocol_sha": "0" * 64}},
        )


class TestRefusal4TheWindow:
    @pytest.mark.parametrize(
        "window",
        [
            {
                "start_date": "2024-01-02",
                "end_date": "2026-10-01",
                "start": "2024-01-02T00:00:00+00:00",
                "end": "2026-10-01T00:00:00+00:00",
            },
            {
                "start_date": "2024-01-01",
                "end_date": "2026-09-30",
                "start": "2024-01-01T00:00:00+00:00",
                "end": "2026-09-30T00:00:00+00:00",
            },
            {
                "start_date": "2024-01-01",
                "end_date": "2026-10-01",
                "start": "2024-01-01T01:00:00+00:00",
                "end": "2026-10-01T00:00:00+00:00",
            },
            {
                "start_date": "2024-01-01",
                "end_date": "2026-10-01",
                "start": "2024-01-01T00:00:00+00:00",
                "end": "2026-10-01T00:00:01+00:00",
            },
            {
                "start_date": "2017-08-17",
                "end_date": "2026-10-01",
                "start": "2017-08-17T00:00:00+00:00",
                "end": "2026-10-01T00:00:00+00:00",
            },
        ],
        ids=[
            "starts-a-day-late",
            "ends-a-day-early",
            "start-instant-off",
            "end-instant-off",
            "straddling-from-2017",
        ],
    )
    def test_a_window_that_is_not_exactly_the_declared_one(
        self, tmp_path: Path, window: dict[str, str]
    ) -> None:
        refusal(tmp_path, r"refusal 4 \(R-BW\)", per_arm={"0.66": {"window": window}})

    def test_a_missing_window_block(self, tmp_path: Path) -> None:
        refusal(tmp_path, r"refusal 4 \(R-BW\)", per_arm={"1.2": {"window": {}}})


class TestRefusal5TheInitialBalance:
    @pytest.mark.parametrize(
        ("place", "balances"),
        [
            ("fill_parameters.initial_balance", {"fill": "5000.0"}),
            ("equity.initial", {"equity": "5000"}),
            ("metrics.initial_balance", {"metrics": "5000.0"}),
            ("effective.costs.initial_balance", {"costs_balance": "5000"}),
        ],
    )
    def test_each_of_the_four_places_a_record_states_it(
        self, tmp_path: Path, place: str, balances: dict[str, str]
    ) -> None:
        refusal(
            tmp_path,
            rf"refusal 5 \(R-BW\): .* states {place.replace('.', '[.]')}",
            per_arm={"1.2": {"balances": balances}},
        )

    def test_an_equal_balance_written_differently_is_the_same_balance(self, tmp_path: Path) -> None:
        result = judge(
            tmp_path, per_arm={"1.2": {"balances": {"fill": "10000.00", "metrics": "1E+4"}}}
        )
        assert result.passed


class TestRefusal6TheEntry:
    def test_a_candidate_digest_that_is_not_the_entrys(self, tmp_path: Path) -> None:
        """The entry binds a digest the (valid) records do not carry: a record's OWN digest is checked by
        the evidence door first, so the mismatch has to be on the entry's side."""
        refusal(
            tmp_path,
            "refusal 6: .* has candidate digest",
            entry={"candidate_digest": "f" * 64},
        )

    def test_a_variant_other_than_the_one_the_selection_chose(self, tmp_path: Path) -> None:
        other = {**VARIANT, "params": {"fast_period": "20", "slow_period": "50"}}
        refusal(tmp_path, "refusal 6: .* ran variant", per_arm={"1.2": {"variant": other}})

    def test_an_entry_with_no_selection_block(self, tmp_path: Path) -> None:
        refusal(
            tmp_path, "refusal 6: entry .* carries no selection block", entry={"selection": None}
        )

    def test_an_entry_whose_selection_names_no_variant(self, tmp_path: Path) -> None:
        refusal(
            tmp_path,
            "refusal 6: entry .* carries no selection block",
            entry={"selection": {"trades": 5}},
        )

    def test_a_run_json_that_is_not_the_one_the_entry_committed(self, tmp_path: Path) -> None:
        _, backtests, body = build_candidate(tmp_path)
        body["oos"]["records"]["1.20"]["run_json_sha256"] = "9" * 64
        with pytest.raises(gate.GateRefusedError, match=r"refusal 6: .* has run[.]json SHA-256"):
            gate.evaluate([parse_entry(json.dumps(body))], backtests, GATE_RULES)

    def test_an_entry_that_is_read_and_holds_no_records(self, tmp_path: Path) -> None:
        _, backtests, body = build_candidate(tmp_path)
        body["oos"] = {}
        with pytest.raises(
            gate.GateRefusedError, match=r"refusal 6: entry .* holds no oos.records"
        ):
            gate.evaluate([parse_entry(json.dumps(body))], backtests, GATE_RULES)

    def test_an_arm_that_is_not_an_object(self, tmp_path: Path) -> None:
        _entry, backtests, body = build_candidate(tmp_path)
        body["oos"]["records"]["0.05"] = "text"
        with pytest.raises(
            gate.GateRefusedError, match=r"refusal 6: entry .* arm '0.05' is not an object"
        ):
            gate.evaluate([parse_entry(json.dumps(body))], backtests, GATE_RULES)

    def test_an_arm_without_its_run_or_digest(self, tmp_path: Path) -> None:
        _entry, backtests, body = build_candidate(tmp_path)
        del body["oos"]["records"]["0.66"]["run_json_sha256"]
        with pytest.raises(
            gate.GateRefusedError, match=r"refusal 6: entry .* lacks run or run_json_sha256"
        ):
            gate.evaluate([parse_entry(json.dumps(body))], backtests, GATE_RULES)


class TestRefusal7TheArms:
    def test_a_record_at_an_arm_other_than_the_one_the_entry_filed_it_under(
        self, tmp_path: Path
    ) -> None:
        _entry, backtests, body = build_candidate(tmp_path)
        records = body["oos"]["records"]
        records["0.05"], records["0.66"] = records["0.66"], records["0.05"]
        with pytest.raises(
            gate.GateRefusedError,
            match=r"refusal 7: .* ran at stop slippage 0.66, not the arm 0.05",
        ):
            gate.evaluate([parse_entry(json.dumps(body))], backtests, GATE_RULES)

    def test_an_entry_that_committed_only_two_arms(self, tmp_path: Path) -> None:
        _entry, backtests, body = build_candidate(tmp_path)
        del body["oos"]["records"]["0.05"]
        with pytest.raises(gate.GateRefusedError, match=r"refusal 7: entry .* has records at arms"):
            gate.evaluate([parse_entry(json.dumps(body))], backtests, GATE_RULES)

    def test_an_entry_that_committed_an_undeclared_fourth_arm(self, tmp_path: Path) -> None:
        _entry, backtests, body = build_candidate(tmp_path)
        body["oos"]["records"]["0.5"] = body["oos"]["records"]["0.66"]
        with pytest.raises(gate.GateRefusedError, match="refusal 7"):
            gate.evaluate([parse_entry(json.dumps(body))], backtests, GATE_RULES)


class TestRefusal8TheThreeRecordsAreOneCandidate:
    @pytest.mark.parametrize(
        ("label", "field"),
        [
            ("code commit", {"code_commit": "9" * 40}),
            ("config digest", {"config_sha": "9" * 64}),
            ("exchange-info snapshots", {"exchange_info": {"BTCUSDT": {"sha256": "9" * 64}}}),
        ],
    )
    def test_records_made_by_different_code_config_or_snapshots(
        self, tmp_path: Path, label: str, field: dict[str, Any]
    ) -> None:
        refusal(tmp_path, f"refusal 8: .* differ in their {label}", per_arm={"0.66": field})


class TestRefusal9TheRecordIsSound:
    def test_a_record_with_problems(self, tmp_path: Path) -> None:
        refusal(
            tmp_path,
            "refusal 9: .* has problems",
            per_arm={"1.2": {"problems": ["a cash identity"]}},
        )

    def test_a_record_that_logged_errors(self, tmp_path: Path) -> None:
        refusal(tmp_path, "refusal 9: .* logged 2 error record", per_arm={"1.2": {"errors": 2}})

    def test_a_record_with_handler_failures(self, tmp_path: Path) -> None:
        refusal(tmp_path, "refusal 9: .* had 1 handler failure", per_arm={"0.05": {"failures": 1}})

    def test_regime_labels_that_are_not_the_protocols_file(self, tmp_path: Path) -> None:
        refusal(tmp_path, "refusal 9: .* used regime labels", per_arm={"1.2": {"labels": "8" * 64}})

    def test_a_trade_log_that_does_not_hold_the_counted_trades(self, tmp_path: Path) -> None:
        refusal(tmp_path, "refusal 9: .* counts 400 trades", per_arm={"1.2": {"csv_rows": 399}})

    def test_a_count_that_the_results_block_does_not_share(self, tmp_path: Path) -> None:
        refusal(tmp_path, "refusal 9: .* counts 400 trades", per_arm={"1.2": {"declared": 401}})

    def test_trades_in_no_regime(self, tmp_path: Path) -> None:
        refusal(
            tmp_path,
            r"refusal 9 \(R-AT\): .* 3 trade\(s\) in no regime",
            per_arm={"1.2": {"unlabelled": 3}},
        )

    def test_a_record_with_no_error_block(self, tmp_path: Path) -> None:
        _entry, backtests, body = build_candidate(tmp_path)
        run = backtests / body["oos"]["records"]["1.20"]["run"] / "run.json"
        record = json.loads(run.read_text(encoding="utf-8"))
        del record["error_log_records"]
        run.write_text(json.dumps(record, sort_keys=True), encoding="utf-8", newline="\n")
        import hashlib

        body["oos"]["records"]["1.20"]["run_json_sha256"] = hashlib.sha256(
            run.read_bytes()
        ).hexdigest()
        with pytest.raises(gate.GateRefusedError, match="has no 'error_log_records' block"):
            gate.evaluate([parse_entry(json.dumps(body))], backtests, GATE_RULES)


# --------------------------------------------------------------------------------------
# Over the entries, and the report
# --------------------------------------------------------------------------------------
class TestEvaluateOverEntries:
    def test_a_pending_candidate_is_listed_not_judged_and_a_baseline_is_ignored(
        self, tmp_path: Path
    ) -> None:
        _entry, backtests, body = build_candidate(tmp_path)
        pending = {
            **body,
            "id": "s6-rsi-4h-on",
            "candidate_digest": "a" * 64,
            "status": "pending",
            "oos": None,
        }
        baseline = {**body, "id": "s5-baseline", "kind": "baseline", "candidate_digest": "b" * 64}
        entries = [parse_entry(json.dumps(x)) for x in (body, pending, baseline)]
        report = gate.evaluate(entries, backtests, GATE_RULES)
        assert [r.entry_id for r in report.results] == [ENTRY_ID]
        assert report.pending == ("s6-rsi-4h-on",)

    def test_one_refused_candidate_returns_no_verdict_for_the_others(self, tmp_path: Path) -> None:
        good, backtests, _body = build_candidate(tmp_path / "a")
        _bad, _bad_backtests, bad_body = build_candidate(
            tmp_path / "b", per_arm={"1.2": {"flag": False}}
        )
        bad_body = {**bad_body, "id": "s6-rsi-4h-on", "candidate_digest": "a" * 64}
        with pytest.raises(gate.GateRefusedError):
            gate.evaluate([good, parse_entry(json.dumps(bad_body))], backtests, GATE_RULES)


class TestTheReport:
    def test_it_prints_both_profit_factors_the_count_the_verdict_and_says_no_correction_is_applied(
        self, tmp_path: Path
    ) -> None:
        entry, backtests, _ = build_candidate(tmp_path)
        text = gate.render_report(gate.evaluate([entry], backtests, GATE_RULES))
        assert "variants declared 216" in text and "candidates read 1; still pending 0" in text
        assert "no multiple-testing correction is applied" in text
        assert "MET      profit factor from per-trade returns: 6.000000  (threshold >= 1.3)" in text
        assert "MET      profit factor in USDT: 6.000000  (threshold >= 1.3)" in text
        assert "<- GATE ARM" in text and "S7: PASS" in text
        assert "S7 SUMMARY: 1 of 1 candidates read PASS" in text
        assert all(ord(c) < 128 for c in text)

    def test_a_failing_candidate_says_fail_and_names_the_criterion(self, tmp_path: Path) -> None:
        entry, backtests, _ = build_candidate(tmp_path, per_arm={"1.2": {"drawdown": "0.5"}})
        text = gate.render_report(gate.evaluate([entry], backtests, GATE_RULES))
        assert "NOT MET  maximum drawdown (per bar): 0.500000  (threshold <= 0.20)" in text
        assert "S7: FAIL" in text and "S7 SUMMARY: 0 of 1 candidates read PASS" in text

    def test_the_regimes_and_pairs_are_printed_beside_the_verdict(self, tmp_path: Path) -> None:
        entry, backtests, _ = build_candidate(tmp_path)
        text = gate.render_report(gate.evaluate([entry], backtests, GATE_RULES))
        assert "regime net P&L at the gate arm: rising 100, falling -50, sideways 30" in text
        assert (
            "per pair at the gate arm: BTCUSDT 200 trades net 60, ETHUSDT 200 trades net 20" in text
        )


def test_the_protocol_text_the_tests_judge_against_is_the_real_one() -> None:
    assert replace(GATE_RULES).protocol_sha256 == PROTOCOL.sha256
    assert PROTOCOL_TEXT.count("protocol-json:begin") == 1
    assert make_oos_run is not None
