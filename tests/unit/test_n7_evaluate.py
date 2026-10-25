"""``scripts/n7_evaluate.py``: the N0 guard, the judgement of pre-registration sections 5 to 8, the report and
the result file, and the whole chain on a fixture world. Fixtures only: nothing here reads a recorded bar,
runs a backtest on recorded data, or touches a venue.

The expected figures are the ones committed in ``docs/RUN_LEDGER.md`` section 104 (P149 C2), derived before the
runner existed by scripts that import neither it nor the estimator module: exact ``Decimal`` statistics,
``math.erf`` and a bisection for Phi, and a plain loop over the numpy generator's draws.

**Three groups.** The guard builds a throwaway git repository and breaks one condition at a time. The judge
worlds W1 to W5 are written as returns, so they exercise sections 5 to 8 without a backtester. World E1 is the
whole chain on a 3-day 1m world: two scripted 1d candidates through the real D1 path, with the hand arithmetic
of ``tests/unit/test_backtest_d1.py`` (entry 100.05, quantity 19.98001, a minute at 90 gapping through the 500-bps
trail and selling at 90 x 0.988).
"""

from __future__ import annotations

import asyncio
import hashlib
import io
import json
import subprocess
import sys
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from tests.unit.d1_world import ScriptedD1, build_minutes, flat, make_settings
from trading_bot.backtesting.sharpe_stats import Mark, daily_series, sharpe
from trading_bot.strategies import registry

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

import n7_evaluate as n7

D = Decimal
UTC = timezone.utc
DAY0 = datetime(2024, 3, 1, tzinfo=UTC)
QUANT = D("0.00000001")

EXPECTED = {
    "W1": {
        "rows": [
            {
                "label": "C1",
                "trades": 9,
                "days": 40,
                "sharpe_annual": -1.2052182459816057,
                "sharpe_daily": -0.06308400618889891,
                "skew": 7.536422509744671e-12,
                "kurt": 1.3041399417229336,
                "boot_p5": -2.299758296965122,
                "dsr": 0.21717004164160092,
                "status": "FAILED (bootstrap, dsr)",
            },
            {
                "label": "C2",
                "trades": 7,
                "days": 40,
                "sharpe_annual": 1.205218245869544,
                "sharpe_daily": 0.06308400618303334,
                "skew": 3.573649109413481e-14,
                "kurt": 1.3041399416826136,
                "boot_p5": 0.16878025384922718,
                "dsr": 0.5023989652630332,
                "status": "FAILED (dsr)",
            },
            {
                "label": "C4",
                "trades": 10,
                "days": 40,
                "sharpe_annual": -1.2052182459816057,
                "sharpe_daily": -0.06308400618889891,
                "skew": 7.536422509744671e-12,
                "kurt": 1.3041399417229336,
                "boot_p5": -2.299758296965122,
                "dsr": 0.21717004164160092,
                "status": "FAILED (bootstrap, dsr)",
            },
        ],
        "outcome": "FAIL",
        "selected": None,
        "tied": [],
    },
    "W2": {
        "rows": [
            {
                "label": "C1",
                "trades": 9,
                "days": 40,
                "sharpe_annual": 13.768603349740467,
                "sharpe_daily": 0.7206816373909911,
                "skew": -0.2909122762019869,
                "kurt": 1.4431662071325528,
                "boot_p5": 12.398619065092335,
                "dsr": 0.9776289353518003,
                "status": "PASS",
            },
            {
                "label": "C2",
                "trades": 7,
                "days": 40,
                "sharpe_annual": 1.205218245869544,
                "sharpe_daily": 0.06308400618303334,
                "skew": 3.573649109413481e-14,
                "kurt": 1.3041399416826136,
                "boot_p5": 0.16878025384922718,
                "dsr": 0.03236930332209115,
                "status": "FAILED (dsr)",
            },
            {
                "label": "C4",
                "trades": 10,
                "days": 40,
                "sharpe_annual": -1.2052182459816057,
                "sharpe_daily": -0.06308400618889891,
                "skew": 7.536422509744671e-12,
                "kurt": 1.3041399417229336,
                "boot_p5": -2.299758296965122,
                "dsr": 0.004208615888820599,
                "status": "FAILED (bootstrap, dsr)",
            },
        ],
        "outcome": "SELECTED",
        "selected": "C1",
        "tied": [],
    },
    "W3": {
        "rows": [
            {
                "label": "C1",
                "trades": 9,
                "days": 40,
                "sharpe_annual": 13.768603349740467,
                "sharpe_daily": 0.7206816373909911,
                "skew": -0.2909122762019869,
                "kurt": 1.4431662071325528,
                "boot_p5": 12.398619065092335,
                "dsr": 0.968362487367783,
                "status": "PASS",
            },
            {
                "label": "C2",
                "trades": 6,
                "days": 40,
                "sharpe_annual": 13.768603349740467,
                "sharpe_daily": 0.7206816373909911,
                "skew": -0.2909122762019869,
                "kurt": 1.4431662071325528,
                "boot_p5": 12.398619065092335,
                "dsr": 0.968362487367783,
                "status": "PASS",
            },
            {
                "label": "C4",
                "trades": 10,
                "days": 40,
                "sharpe_annual": -1.2052182459816057,
                "sharpe_daily": -0.06308400618889891,
                "skew": 7.536422509744671e-12,
                "kurt": 1.3041399417229336,
                "boot_p5": -2.299758296965122,
                "dsr": 0.0025277046364242106,
                "status": "FAILED (bootstrap, dsr)",
            },
        ],
        "outcome": "SELECTED",
        "selected": "C1",
        "tied": [],
    },
    "W3b": {
        "rows": [
            {
                "label": "C1",
                "trades": 9,
                "days": 40,
                "sharpe_annual": 13.768603349740467,
                "sharpe_daily": 0.7206816373909911,
                "skew": -0.2909122762019869,
                "kurt": 1.4431662071325528,
                "boot_p5": 12.398619065092335,
                "dsr": 0.968362487367783,
                "status": "PASS",
            },
            {
                "label": "C2",
                "trades": 9,
                "days": 40,
                "sharpe_annual": 13.768603349740467,
                "sharpe_daily": 0.7206816373909911,
                "skew": -0.2909122762019869,
                "kurt": 1.4431662071325528,
                "boot_p5": 12.398619065092335,
                "dsr": 0.968362487367783,
                "status": "PASS",
            },
            {
                "label": "C4",
                "trades": 10,
                "days": 40,
                "sharpe_annual": -1.2052182459816057,
                "sharpe_daily": -0.06308400618889891,
                "skew": 7.536422509744671e-12,
                "kurt": 1.3041399417229336,
                "boot_p5": -2.299758296965122,
                "dsr": 0.0025277046364242106,
                "status": "FAILED (bootstrap, dsr)",
            },
        ],
        "outcome": "INDETERMINATE",
        "selected": None,
        "tied": ["C1", "C2"],
    },
    "W4": {
        "rows": [
            {
                "label": "C1",
                "trades": 4,
                "days": 40,
                "sharpe_annual": 13.768603349740467,
                "sharpe_daily": 0.7206816373909911,
                "skew": -0.2909122762019869,
                "kurt": 1.4431662071325528,
                "boot_p5": 12.398619065092335,
                "dsr": 0.968362487367783,
                "status": "EXCLUDED (below floor)",
            },
            {
                "label": "C2",
                "trades": 7,
                "days": 40,
                "sharpe_annual": 13.768603349740467,
                "sharpe_daily": 0.7206816373909911,
                "skew": -0.2909122762019869,
                "kurt": 1.4431662071325528,
                "boot_p5": 12.398619065092335,
                "dsr": 0.968362487367783,
                "status": "PASS",
            },
            {
                "label": "C4",
                "trades": 10,
                "days": 40,
                "sharpe_annual": -1.2052182459816057,
                "sharpe_daily": -0.06308400618889891,
                "skew": 7.536422509744671e-12,
                "kurt": 1.3041399417229336,
                "boot_p5": -2.299758296965122,
                "dsr": 0.0025277046364242106,
                "status": "FAILED (bootstrap, dsr)",
            },
        ],
        "outcome": "SELECTED",
        "selected": "C2",
        "tied": [],
    },
    "W5": {
        "rows": [
            {
                "label": "C1",
                "trades": 9,
                "days": 40,
                "sharpe_annual": 11.956330768685685,
                "sharpe_daily": 0.6258229550731527,
                "skew": -0.35641833818703245,
                "kurt": 1.3729652585536885,
                "boot_p5": 10.659342615369008,
                "dsr": 0.9592298570567053,
                "status": "PASS",
            },
            {
                "label": "C2",
                "trades": 7,
                "days": 40,
                "sharpe_annual": 1.205218245869544,
                "sharpe_daily": 0.06308400618303334,
                "skew": 3.573649109413481e-14,
                "kurt": 1.3041399416826136,
                "boot_p5": 0.16878025384922718,
                "dsr": 0.05947298547391883,
                "status": "FAILED (dsr)",
            },
            {
                "label": "C4",
                "trades": 10,
                "days": 40,
                "sharpe_annual": -1.2052182459816057,
                "sharpe_daily": -0.06308400618889891,
                "skew": 7.536422509744671e-12,
                "kurt": 1.3041399417229336,
                "boot_p5": -2.299758296965122,
                "dsr": 0.009462301780677085,
                "status": "FAILED (bootstrap, dsr)",
            },
        ],
        "outcome": "SELECTED",
        "selected": "C1",
        "tied": [],
    },
    "W5s": {
        "rows": [
            {
                "label": "C1",
                "trades": 9,
                "days": 40,
                "sharpe_annual": 11.956330768685685,
                "sharpe_daily": 0.6258229550731527,
                "skew": -0.35641833818703245,
                "kurt": 1.3729652585536885,
                "boot_p5": 10.659342615369008,
                "dsr": 0.9268132182919153,
                "status": "FAILED (dsr)",
            },
            {
                "label": "C2",
                "trades": 7,
                "days": 40,
                "sharpe_annual": 13.768603349740467,
                "sharpe_daily": 0.7206816373909911,
                "skew": -0.2909122762019869,
                "kurt": 1.4431662071325528,
                "boot_p5": 12.398619065092335,
                "dsr": 0.9758277724345463,
                "status": "PASS",
            },
            {
                "label": "C4",
                "trades": 10,
                "days": 40,
                "sharpe_annual": -1.2052182459816057,
                "sharpe_daily": -0.06308400618889891,
                "skew": 7.536422509744671e-12,
                "kurt": 1.3041399417229336,
                "boot_p5": -2.299758296965122,
                "dsr": 0.0037732742122973395,
                "status": "FAILED (bootstrap, dsr)",
            },
        ],
        "outcome": "SELECTED",
        "selected": "C2",
        "tied": [],
    },
}


W5_REPORT = """\
N7 in-sample evaluation (pre-registration sections 5 to 8)
window [2024-03-01, 2024-04-10)
fee telemetry (telemetry only, never a criterion)
  C1 trades=9 gross=500 fees=50 net=450 entry_notional=20000 fee_share=0.100000 fee_bps=25.0000
  C2 trades=7 gross=-200 fees=20 net=-220 entry_notional=8000 fee_share=0.100000 fee_bps=25.0000 flag=gross<=0
  C4 trades=10 gross=0 fees=10 net=-10 entry_notional=1000 fee_share=n/a fee_bps=100.0000 flag=gross<=0
candidates (bootstrap p=0.05 resamples=400 seed=20261025; deflated Sharpe trials=3)
  C1 1d trades=9 floor=5 days=40 sharpe_annual=11.956331 boot_p5=10.659343 dsr=0.959230 status=PASS
  C2 1d trades=7 floor=5 days=40 sharpe_annual=1.205218 boot_p5=0.168780 dsr=0.059473 status=FAILED (dsr)
  C4 4h trades=10 floor=8 days=40 sharpe_annual=-1.205218 boot_p5=-2.299758 dsr=0.009462 status=FAILED (bootstrap, dsr)
verdict SELECTED C1
sensitivity fee_0.075 would_select=C2 flips=2
  flip C1 dsr pass->fail
  flip C2 dsr fail->pass
context buy_and_hold sharpe_annual=1.205218 days=40"""


# ---- the judge worlds -----------------------------------------------------------------------------------
PATTERNS = {
    "S1": ["0.012", "-0.004", "0.009", "0.015", "-0.002", "0.011", "0.007", "-0.005"],
    "S2": ["0.010", "-0.004", "0.008", "0.012", "-0.003", "0.009", "0.006", "-0.005"],
    "N1": ["0.010", "-0.011", "0.008", "-0.009", "0.006", "-0.007", "0.004", "-0.005"],
    "N2": ["0.011", "-0.010", "0.009", "-0.008", "0.007", "-0.006", "0.005", "-0.004"],
}  # fmt: skip
TEST_FLOORS = {"1d": n7.Floors(5, 2), "4h": n7.Floors(8, 3)}
RESAMPLES = 400


def marks_of(pattern: str) -> tuple[Mark, ...]:
    """40 returns (the 8-return pattern five times) as marks from 10,000, quantised to 8 places each step."""
    value = D(10000)
    out: list[Mark] = [(DAY0, value)]
    for i, r in enumerate(PATTERNS[pattern] * 5, start=1):
        value = (value * (1 + D(r))).quantize(QUANT)
        out.append((DAY0 + timedelta(days=i), value))
    return tuple(out)


def run_of(
    label: str, timeframe: str, trades: int, pattern: str, **books: Decimal
) -> n7.CandidateRun:
    return n7.CandidateRun(
        label=label,
        name=f"cand_{label.lower()}",
        timeframe=timeframe,
        trades=trades,
        open_at_end=0,
        gross=books.get("gross", D(0)),
        fees=books.get("fees", D(0)),
        entry_notional=books.get("notional", D(1000)),
        marks=marks_of(pattern),
    )


WORLDS: dict[str, list[tuple[str, str, int, str]]] = {
    "W1": [("C1", "1d", 9, "N1"), ("C2", "1d", 7, "N2"), ("C4", "4h", 10, "N1")],
    "W2": [("C1", "1d", 9, "S1"), ("C2", "1d", 7, "N2"), ("C4", "4h", 10, "N1")],
    "W3": [("C1", "1d", 9, "S1"), ("C2", "1d", 6, "S1"), ("C4", "4h", 10, "N1")],
    "W3b": [("C1", "1d", 9, "S1"), ("C2", "1d", 9, "S1"), ("C4", "4h", 10, "N1")],
    "W4": [("C1", "1d", 4, "S1"), ("C2", "1d", 7, "S1"), ("C4", "4h", 10, "N1")],
    "W5": [("C1", "1d", 9, "S2"), ("C2", "1d", 7, "N2"), ("C4", "4h", 10, "N1")],
}
W5_SENSITIVITY = [("C1", "1d", 9, "S2"), ("C2", "1d", 7, "S1"), ("C4", "4h", 10, "N1")]


def judge_world(spec: list[tuple[str, str, int, str]]) -> n7.Judgement:
    runs = [run_of(*row) for row in spec]
    return n7.judge(runs, floors=TEST_FLOORS, resamples=RESAMPLES)


class TestTheJudgeWorlds:
    @pytest.mark.parametrize("world", sorted(WORLDS))
    def test_every_candidate_matches_the_independent_derivation(self, world: str) -> None:
        judgement = judge_world(WORLDS[world])
        expected = EXPECTED[world]
        assert judgement.trials == 3
        assert len(judgement.candidates) == len(expected["rows"])
        for got, want in zip(judgement.candidates, expected["rows"], strict=True):
            assert got.label == want["label"]
            assert got.trades == want["trades"]
            assert got.days == want["days"]
            assert got.sharpe_annual == pytest.approx(want["sharpe_annual"], rel=1e-9)
            assert got.sharpe_daily == pytest.approx(want["sharpe_daily"], rel=1e-9)
            assert got.skew == pytest.approx(want["skew"], abs=1e-9)
            assert got.kurt == pytest.approx(want["kurt"], rel=1e-9)
            assert got.boot_p5 == pytest.approx(want["boot_p5"], rel=1e-9)
            assert got.dsr == pytest.approx(want["dsr"], rel=1e-9)
            assert got.status == want["status"]

    @pytest.mark.parametrize("world", sorted(WORLDS))
    def test_the_verdict_matches_the_derivation(self, world: str) -> None:
        judgement = judge_world(WORLDS[world])
        expected = EXPECTED[world]
        assert judgement.outcome == expected["outcome"]
        assert judgement.selected == expected["selected"]
        assert list(judgement.tied) == expected["tied"]

    def test_w1_no_candidate_passes_so_the_run_fails_at_n7(self) -> None:
        judgement = judge_world(WORLDS["W1"])
        assert judgement.outcome == "FAIL"
        assert judgement.selected is None
        assert all(c.status != "PASS" for c in judgement.candidates)

    def test_w1_a_candidate_can_clear_the_bootstrap_and_fail_the_deflated_sharpe(self) -> None:
        c2 = judge_world(WORLDS["W1"]).candidates[1]
        assert c2.boot_pass and not c2.dsr_pass
        assert c2.status == "FAILED (dsr)"

    def test_w3_a_tie_in_sharpe_goes_to_the_candidate_with_more_trades(self) -> None:
        judgement = judge_world(WORLDS["W3"])
        c1, c2, _ = judgement.candidates
        assert c1.sharpe_annual == c2.sharpe_annual
        assert judgement.selected == "C1"

    def test_w3b_a_tie_section_7_does_not_break_is_indeterminate_and_selects_nothing(self) -> None:
        judgement = judge_world(WORLDS["W3b"])
        assert judgement.outcome == "INDETERMINATE"
        assert judgement.selected is None
        assert judgement.tied == ("C1", "C2")

    def test_w4_a_candidate_below_its_floor_is_excluded_though_it_ties_the_winner(self) -> None:
        judgement = judge_world(WORLDS["W4"])
        c1, c2, _ = judgement.candidates
        assert c1.sharpe_annual == c2.sharpe_annual and c1.dsr == c2.dsr
        assert not c1.floor_met and c1.status == "EXCLUDED (below floor)"
        assert judgement.selected == "C2"

    def test_a_floor_is_met_at_exactly_the_floor_and_not_below(self) -> None:
        at = n7.judge([run_of("C1", "1d", 5, "S1")], floors=TEST_FLOORS, resamples=RESAMPLES)
        below = n7.judge([run_of("C1", "1d", 4, "S1")], floors=TEST_FLOORS, resamples=RESAMPLES)
        assert at.candidates[0].floor_met and not below.candidates[0].floor_met

    def test_the_deflated_sharpe_gate_is_strictly_above_0_95(self) -> None:
        assert n7.DSR_MIN == 0.95
        judgement = judge_world(WORLDS["W5"])
        assert [c.dsr_pass for c in judgement.candidates] == [
            c.dsr > 0.95 for c in judgement.candidates
        ]

    def test_a_candidate_with_no_variance_has_no_sharpe_and_the_run_refuses(self) -> None:
        flat_marks = tuple((DAY0 + timedelta(days=i), D(10000)) for i in range(5))
        silent = n7.CandidateRun("C1", "cand_c1", "1d", 0, 0, D(0), D(0), D(0), flat_marks)
        with pytest.raises(n7.RunnerError, match="C1 has no Sharpe"):
            n7.judge([silent, run_of("C2", "1d", 9, "S1")], floors=TEST_FLOORS, resamples=RESAMPLES)

    def test_a_bootstrap_that_refuses_fails_the_gate_and_is_recorded(self) -> None:
        # Returns 0, -x, 0, 0: with p = 1 many resamples are all zero, which the bootstrap refuses.
        values = [D(10000), D(10000), D(9900), D(9900), D(9900)]
        marks = tuple((DAY0 + timedelta(days=i), v) for i, v in enumerate(values))
        sparse = n7.CandidateRun("C1", "cand_c1", "1d", 9, 0, D(0), D(0), D(1), marks)
        judgement = n7.judge([sparse], floors=TEST_FLOORS, resamples=RESAMPLES, p=1.0)
        row = judgement.candidates[0]
        assert row.boot_p5 is None and row.boot_error is not None
        assert "no variance" in row.boot_error
        assert not row.boot_pass
        assert row.status == "FAILED (bootstrap, dsr)"

    def test_the_trial_count_is_the_number_of_runs(self) -> None:
        assert (
            n7.judge([run_of("C1", "1d", 9, "S1")], floors=TEST_FLOORS, resamples=RESAMPLES).trials
            == 1
        )

    def test_nothing_to_judge_is_refused(self) -> None:
        with pytest.raises(ValueError, match="no candidate"):
            n7.judge([])

    @pytest.mark.parametrize(("p", "resamples"), [(0.0, 10), (1.5, 10), (0.05, 0)])
    def test_invalid_bootstrap_settings_are_refused_before_any_work(
        self, p: float, resamples: int
    ) -> None:
        with pytest.raises(ValueError, match="invalid bootstrap settings"):
            n7.judge([run_of("C1", "1d", 9, "S1")], floors=TEST_FLOORS, resamples=resamples, p=p)


class TestTheSensitivityThatFlipsAGateAndDecidesNothing:
    """W5: under ``fee_0.075`` C2 would pass and C1 would fail the deflated Sharpe gate. The verdict stays."""

    def _evaluation(self) -> n7.Evaluation:
        books = {
            "C1": {"gross": D("500"), "fees": D("50"), "notional": D("20000")},
            "C2": {"gross": D("-200"), "fees": D("20"), "notional": D("8000")},
            "C4": {"gross": D("0"), "fees": D("10"), "notional": D("1000")},
        }
        runs = tuple(run_of(*row, **books[row[0]]) for row in WORLDS["W5"])
        base = n7.judge(runs, floors=TEST_FLOORS, resamples=RESAMPLES)
        other_runs = tuple(run_of(*row) for row in W5_SENSITIVITY)
        other = n7.judge(other_runs, floors=TEST_FLOORS, resamples=RESAMPLES)
        sensitivity = n7.Sensitivity(
            n7.Costs("fee_0.075", D("0.075"), D("1.20")),
            other,
            n7.flips_between(base, other),
            other_runs,
        )
        returns = daily_series(marks_of("N2"))
        return n7.Evaluation(
            window=(date(2024, 3, 1), date(2024, 4, 10)),
            first_defined={},
            runs=runs,
            judgement=base,
            sensitivities=(sensitivity,),
            context=n7.ContextSharpe(sharpe(returns), len(returns)),
            resamples=RESAMPLES,
        )

    def test_the_flips_are_listed_in_candidate_then_gate_order(self) -> None:
        sensitivity = self._evaluation().sensitivities[0]
        assert sensitivity.flips == (
            n7.Flip("C1", "dsr", True, False),
            n7.Flip("C2", "dsr", False, True),
        )

    def test_the_sensitivity_would_select_another_candidate_and_the_verdict_does_not_change(
        self,
    ) -> None:
        evaluation = self._evaluation()
        assert evaluation.sensitivities[0].would_select == "C2"
        assert evaluation.judgement.outcome == "SELECTED"
        assert evaluation.judgement.selected == "C1"

    def test_the_whole_report_is_the_predicted_text_with_the_fee_telemetry_first(self) -> None:
        lines = n7.render(self._evaluation())
        assert "\n".join(lines) == W5_REPORT
        assert lines[2] == "fee telemetry (telemetry only, never a criterion)"
        first_figure = next(i for i, line in enumerate(lines) if "sharpe" in line.lower())
        assert first_figure > 2 and all(
            "sharpe" not in line.lower() for line in lines[:first_figure]
        )

    def test_would_select_names_none_and_indeterminate_too(self) -> None:
        none = n7.Sensitivity(n7.Costs("x", D(0), D(0)), judge_world(WORLDS["W1"]), (), ())
        tie = n7.Sensitivity(n7.Costs("x", D(0), D(0)), judge_world(WORLDS["W3b"]), (), ())
        assert (none.would_select, tie.would_select) == ("none", "indeterminate")

    def test_a_sensitivity_listing_other_candidates_cannot_be_compared(self) -> None:
        a = judge_world(WORLDS["W5"])
        b = n7.judge([run_of("C2", "1d", 9, "S1")], floors=TEST_FLOORS, resamples=RESAMPLES)
        a_one = n7.Judgement(a.candidates[:1], a.outcome, a.selected, a.tied, 1)
        with pytest.raises(ValueError, match="same candidates"):
            n7.flips_between(a_one, b)


class TestFeeTelemetry:
    def _line(self, trades: int, gross: str, fees: str, notional: str) -> n7.TelemetryLine:
        run = n7.CandidateRun(
            "C1", "c", "1d", trades, 0, D(gross), D(fees), D(notional), marks_of("S1")
        )
        return n7.telemetry_of(run)

    def test_a_positive_gross_gives_both_ratios_and_no_flag(self) -> None:
        t = self._line(10, "500", "50", "20000")
        assert (t.net, t.fee_share, t.fee_bps, t.flag) == (D(450), D("0.1"), D(25), "")

    def test_a_negative_gross_is_over_its_absolute_value_and_flagged(self) -> None:
        t = self._line(4, "-200", "20", "8000")
        assert (t.net, t.fee_share, t.fee_bps, t.flag) == (D(-220), D("0.1"), D(25), "gross<=0")

    def test_a_zero_gross_has_no_share_but_has_basis_points_and_is_flagged(self) -> None:
        t = self._line(10, "0", "10", "1000")
        assert (t.fee_share, t.fee_bps, t.flag) == (None, D(100), "gross<=0")

    def test_no_trade_has_no_ratio_and_says_so(self) -> None:
        t = self._line(0, "0", "0", "0")
        assert (t.fee_share, t.fee_bps, t.flag) == (None, None, "no_trades")

    def test_the_report_prints_n_a_where_a_ratio_is_undefined(self) -> None:
        evaluation = TestTheSensitivityThatFlipsAGateAndDecidesNothing()._evaluation()
        line = next(x for x in n7.render(evaluation) if x.startswith("  C4 trades"))
        assert "fee_share=n/a" in line and "flag=gross<=0" in line


class TestTheResultFile:
    def _evaluation(self) -> n7.Evaluation:
        return TestTheSensitivityThatFlipsAGateAndDecidesNothing()._evaluation()

    def test_the_document_is_canonical_ascii_json_ending_in_one_line_feed(self) -> None:
        payload = n7.canonical_json(n7.result_document(self._evaluation()))
        assert payload.isascii() and payload.endswith(b"}\n") and not payload.endswith(b"\n\n")
        assert b"\r" not in payload
        document = json.loads(payload)
        assert document["schema"] == 1
        assert document["window"] == ["2024-03-01", "2024-04-10"]

    def test_money_is_a_string_and_a_float_is_rounded_to_ten_places(self) -> None:
        document = n7.result_document(self._evaluation())
        telemetry = document["fee_telemetry"]
        assert telemetry[0]["gross"] == "500" and telemetry[0]["fee_share"] == "0.1"  # type: ignore[index]
        c1 = document["judgement"]["candidates"][0]  # type: ignore[index]
        assert c1["sharpe_annual"] == round(c1["sharpe_annual"], 10)
        assert all(isinstance(m[1], str) for m in document["runs"][0]["marks"])  # type: ignore[index]

    def test_the_same_evaluation_gives_the_same_bytes_and_so_the_same_digest(self) -> None:
        a = n7.canonical_json(n7.result_document(self._evaluation()))
        b = n7.canonical_json(n7.result_document(self._evaluation()))
        assert a == b and hashlib.sha256(a).hexdigest() == hashlib.sha256(b).hexdigest()

    def test_the_document_records_the_sensitivities_and_what_they_would_select(self) -> None:
        sens = n7.result_document(self._evaluation())["sensitivities"]
        assert sens[0]["name"] == "fee_0.075" and sens[0]["would_select"] == "C2"  # type: ignore[index]
        assert [f["gate"] for f in sens[0]["flips"]] == ["dsr", "dsr"]  # type: ignore[index]


# ---- the constants the pre-registration fixes -------------------------------------------------------------
class TestTheConstantsAreThePreRegistrations:
    def test_the_floors_are_section_5(self) -> None:
        assert {"1d": n7.Floors(30, 12), "4h": n7.Floors(120, 48)} == n7.FLOORS

    def test_the_bootstrap_is_section_6_b(self) -> None:
        assert (n7.BOOTSTRAP_P, n7.RESAMPLES, n7.SEED) == (1 / 20, 10_000, 20261025)
        assert n7.BOOTSTRAP_P == 0.05

    def test_the_span_ends_on_2024_01_01_and_the_archive_begins_on_2017_08_17(self) -> None:
        assert datetime(2024, 1, 1, tzinfo=UTC) == n7.IN_SAMPLE_END
        assert datetime(2017, 8, 17, tzinfo=UTC) == n7.IN_SAMPLE_BEGIN

    def test_the_costs_are_section_3(self) -> None:
        assert (n7.BASE_COSTS.fee_percent, n7.BASE_COSTS.stop_slippage_percent) == (
            D("0.10"),
            D("1.20"),
        )
        assert [(c.name, c.fee_percent, c.stop_slippage_percent) for c in n7.SENSITIVITIES] == [
            ("fee_0.075", D("0.075"), D("1.20")),
            ("slip_0.66", D("0.10"), D("0.66")),
            ("slip_0.10", D("0.10"), D("0.10")),
        ]

    def test_the_candidates_are_the_six_of_r_dy_and_all_are_registered(self) -> None:
        assert n7.CANDIDATES == (
            ("C1", "donchian_1d_20", "1d"),
            ("C2", "donchian_1d_55", "1d"),
            ("C3", "sma_cross_1d_50_200", "1d"),
            ("C4", "donchian_4h_20", "4h"),
            ("C5", "keltner_4h_20_2", "4h"),
            ("C6", "tsmom_1d_90", "1d"),
        )
        for _, name, timeframe in n7.CANDIDATES:
            strategy = registry.create_strategy(name)
            assert strategy.timeframe == timeframe  # type: ignore[attr-defined]

    def test_every_candidate_window_holds_the_atr_the_trail_needs(self) -> None:
        for _, name, _ in n7.CANDIDATES:
            assert registry.create_strategy(name).warmup_period >= 21

    def test_the_frozen_paths_and_the_tag(self) -> None:
        assert n7.FROZEN_PATHS == (
            "docs/M5N_PREREGISTRATION.md",
            "src/trading_bot/backtesting/sharpe_stats.py",
            "scripts/n7_evaluate.py",
        )
        assert n7.MILESTONE_TAG == "milestone/M5m"
        assert n7.CHARTER_PATH == "docs/M5N_CHARTER_DRAFT.md"

    def test_the_guard_reads_the_repository_this_script_lives_in(self) -> None:
        assert Path(n7.__file__).resolve() == n7.REPO_ROOT / "scripts" / "n7_evaluate.py"


# ---- the start day, the marks and the books ---------------------------------------------------------------
def opens(*hours: int) -> list[datetime]:
    return [datetime(2024, 3, 1, tzinfo=UTC) + timedelta(hours=h) for h in hours]


class TestTheStartDay:
    def test_a_run_of_enough_consecutive_bars_ends_at_the_first_defined_bar(self) -> None:
        series = [DAY0 + timedelta(days=i) for i in range(10)]
        assert n7.first_defined_open(series, "1d", 4) == DAY0 + timedelta(days=3)

    def test_one_bar_is_defined_at_the_first_bar(self) -> None:
        assert n7.first_defined_open([DAY0], "1d", 1) == DAY0

    def test_a_gap_restarts_the_count(self) -> None:
        series = [DAY0 + timedelta(days=i) for i in (0, 1, 2, 4, 5, 6, 7)]
        assert n7.first_defined_open(series, "1d", 4) == DAY0 + timedelta(days=7)

    def test_a_repeated_open_time_restarts_the_count(self) -> None:
        series = [
            DAY0,
            DAY0 + timedelta(days=1),
            DAY0 + timedelta(days=1),
            DAY0 + timedelta(days=2),
        ]
        assert n7.first_defined_open(series, "1d", 3) is None

    def test_a_series_too_short_is_never_defined(self) -> None:
        assert n7.first_defined_open([DAY0, DAY0 + timedelta(days=1)], "1d", 3) is None

    def test_a_4h_series_counts_four_hour_bars(self) -> None:
        series = [DAY0 + timedelta(hours=4 * i) for i in range(6)]
        assert n7.first_defined_open(series, "4h", 5) == DAY0 + timedelta(hours=16)

    def test_an_empty_series_is_never_defined(self) -> None:
        assert n7.first_defined_open([], "1d", 1) is None


class TestAssembleMarks:
    def test_the_start_is_the_initial_balance_and_each_midnight_is_its_sample(self) -> None:
        end = DAY0 + timedelta(days=3)
        samples = {DAY0 + timedelta(days=i): D(10000 + i) for i in (1, 2, 3)}
        marks, carried = n7.assemble_marks(samples, DAY0, end, D(10000))
        assert [m[1] for m in marks] == [D(10000), D(10001), D(10002), D(10003)]
        assert [m[0] for m in marks] == [DAY0 + timedelta(days=i) for i in range(4)]
        assert carried == 0

    def test_a_midnight_nobody_sampled_carries_the_previous_mark_and_is_counted(self) -> None:
        end = DAY0 + timedelta(days=3)
        samples = {DAY0 + timedelta(days=1): D(10100), DAY0 + timedelta(days=3): D(10300)}
        marks, carried = n7.assemble_marks(samples, DAY0, end, D(10000))
        assert [m[1] for m in marks] == [D(10000), D(10100), D(10100), D(10300)]
        assert carried == 1

    def test_the_marks_are_of_the_one_form_the_estimator_accepts(self) -> None:
        marks, _ = n7.assemble_marks({}, DAY0, DAY0 + timedelta(days=2), D(10000))
        assert daily_series(marks) == (0.0, 0.0)


# ---- the guard ------------------------------------------------------------------------------------------
FILES = {
    "docs/M5N_PREREGISTRATION.md": b"pre-registration, as frozen\n",
    "src/trading_bot/backtesting/sharpe_stats.py": b"# the estimator module, as frozen\n",
    "scripts/n7_evaluate.py": b"# the runner, as frozen\n",
}


class Repo:
    """A throwaway git repository the guard is pointed at."""

    def __init__(self, path: Path) -> None:
        self.path = path

    def git(self, *args: str) -> str:
        done = subprocess.run(
            [
                "git",
                "-C",
                str(self.path),
                "-c",
                "user.name=test",
                "-c",
                "user.email=test@example.invalid",
                "-c",
                "commit.gpgsign=false",
                "-c",
                "core.autocrlf=false",
                # Git for Windows switches fsmonitor on in its system config, and every `add` or
                # `commit` in a throwaway repository then starts a daemon that outlives the repository
                # and the test. 821 of them held about 30 GB of committed memory (M5n-223).
                "-c",
                "core.fsmonitor=false",
                *args,
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=True,
        )
        return done.stdout.strip()

    def write(self, relative: str, data: bytes) -> None:
        target = self.path / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)

    def commit(self, message: str) -> str:
        self.git("add", "-A")
        self.git("commit", "-q", "-m", message)
        return self.git("rev-parse", "HEAD")


def digests() -> dict[str, str]:
    return {path: hashlib.sha256(data).hexdigest() for path, data in FILES.items()}


def good_charter(
    c1: str,
    side: str | None,
    *,
    n0: list[str] | None = None,
    drop: tuple[str, ...] = (),
    extra: tuple[str, ...] = (),
) -> list[str]:
    lines = ["# charter", ""]
    lines += n0 if n0 is not None else [f"N0 complete: S4 result recorded at {c1}"]
    for path, digest in digests().items():
        if path not in drop:
            lines.append(f"N7 frozen digest {path} {digest}")
    return [*lines, *extra, ""]


def make_repo(
    tmp_path: Path,
    *,
    tag: str | None = "milestone/M5m",
    annotated: bool = False,
    charter: Any = good_charter,
    with_side_commit: bool = False,
    write_charter: bool = True,
) -> tuple[Repo, str, str | None]:
    """A repository with the three frozen files, a charter that satisfies the guard, and the tag.

    ``charter`` is called with the first commit's hash and a side commit's hash (or ``None``) and returns the
    charter's lines. Returns the repository, the first commit and the side commit."""
    repo = Repo(tmp_path / "repo")
    repo.path.mkdir(parents=True)
    repo.git("init", "-q")
    repo.git("symbolic-ref", "HEAD", "refs/heads/main")
    for path, data in FILES.items():
        repo.write(path, data)
    c1 = repo.commit("frozen files")
    side: str | None = None
    if with_side_commit:
        repo.git("checkout", "-q", "-b", "side")
        repo.write("side.txt", b"not on main\n")
        side = repo.commit("a commit that main never merges")
        repo.git("checkout", "-q", "main")
    if write_charter:
        repo.write(n7.CHARTER_PATH, "\n".join(charter(c1, side)).encode("utf-8"))
        repo.commit("charter")
    if tag is not None:
        if annotated:
            repo.git("tag", "-a", tag, c1, "-m", "M5m close")
        else:
            repo.git("tag", tag, c1)
    return repo, c1, side


def refusal(root: Path) -> str:
    with pytest.raises(n7.GuardError) as caught:
        n7.check_n0_guard(root)
    return caught.value.code


class TestTheGuardAccepts:
    def test_a_repository_that_satisfies_all_three_conditions(self, tmp_path: Path) -> None:
        repo, _, _ = make_repo(tmp_path)
        n7.check_n0_guard(repo.path)

    def test_an_annotated_tag(self, tmp_path: Path) -> None:
        repo, _, _ = make_repo(tmp_path, annotated=True)
        n7.check_n0_guard(repo.path)

    def test_a_seven_character_hash(self, tmp_path: Path) -> None:
        repo, _, _ = make_repo(
            tmp_path,
            charter=lambda c1, side: good_charter(
                c1, side, n0=[f"N0 complete: S4 result recorded at {c1[:7]}"]
            ),
        )
        n7.check_n0_guard(repo.path)

    def test_a_commit_is_its_own_ancestor(self, tmp_path: Path) -> None:
        repo, c1, _ = make_repo(tmp_path)
        assert n7._is_ancestor(repo.path, c1, c1)
        assert n7._is_ancestor(repo.path, c1, "HEAD")

    def test_a_charter_with_crlf_line_endings_is_not_read_as_a_match(self, tmp_path: Path) -> None:
        # The charter is LF-pinned; a CR left on a line makes it a different line, and the guard refuses.
        repo, c1, _ = make_repo(tmp_path, write_charter=False, tag=None)
        text = "\r\n".join(good_charter(c1, None)).encode("utf-8")
        repo.write(n7.CHARTER_PATH, text)
        repo.commit("charter")
        repo.git("tag", "milestone/M5m", c1)
        assert refusal(repo.path) == "n0_line_missing"


class TestTheGuardRefusesConditionA:
    def test_no_tag(self, tmp_path: Path) -> None:
        repo, _, _ = make_repo(tmp_path, tag=None)
        assert refusal(repo.path) == "tag_missing"

    def test_a_tag_of_another_name(self, tmp_path: Path) -> None:
        repo, _, _ = make_repo(tmp_path, tag="milestone/M5l")
        assert refusal(repo.path) == "tag_missing"


class TestTheGuardRefusesConditionB:
    def test_no_line(self, tmp_path: Path) -> None:
        repo, _, _ = make_repo(tmp_path, charter=lambda c1, side: good_charter(c1, side, n0=[]))
        assert refusal(repo.path) == "n0_line_missing"

    @pytest.mark.parametrize(
        "line",
        [
            "N0 complete: S4 result recorded at {sha} and more",
            "N0 complete: S4 result recorded at {upper}",
            "N0 complete: S4 result recorded at <sha>",
            "N0 complete: S4 result recorded at {short}",
            ' "N0 complete: S4 result recorded at {sha}"',
            "n0 complete: s4 result recorded at {sha}",
        ],
        ids=[
            "trailing-text",
            "upper-case",
            "placeholder",
            "six-characters",
            "quoted",
            "lower-case-words",
        ],
    )
    def test_a_line_that_is_not_exactly_the_form(self, tmp_path: Path, line: str) -> None:
        def charter(c1: str, side: str | None) -> list[str]:
            text = line.format(sha=c1, upper=c1.upper(), short=c1[:6])
            return good_charter(c1, side, n0=[text])

        repo, _, _ = make_repo(tmp_path, charter=charter)
        assert refusal(repo.path) == "n0_line_missing"

    def test_two_lines(self, tmp_path: Path) -> None:
        def charter(c1: str, side: str | None) -> list[str]:
            line = f"N0 complete: S4 result recorded at {c1}"
            return good_charter(c1, side, n0=[line, line])

        repo, _, _ = make_repo(tmp_path, charter=charter)
        assert refusal(repo.path) == "n0_line_duplicated"

    def test_a_line_that_is_only_in_the_working_copy(self, tmp_path: Path) -> None:
        repo, c1, _ = make_repo(tmp_path, charter=lambda c1, side: good_charter(c1, side, n0=[]))
        path = repo.path / n7.CHARTER_PATH
        path.write_bytes(path.read_bytes() + f"N0 complete: S4 result recorded at {c1}\n".encode())
        assert refusal(repo.path) == "n0_line_missing"

    def test_a_commit_the_repository_does_not_have(self, tmp_path: Path) -> None:
        repo, _, _ = make_repo(
            tmp_path,
            charter=lambda c1, side: good_charter(
                c1, side, n0=["N0 complete: S4 result recorded at deadbeef0000"]
            ),
        )
        assert refusal(repo.path) == "n0_commit_unknown"

    def test_a_commit_that_is_not_an_ancestor_of_head(self, tmp_path: Path) -> None:
        def charter(c1: str, side: str | None) -> list[str]:
            return good_charter(c1, side, n0=[f"N0 complete: S4 result recorded at {side}"])

        repo, _, side = make_repo(tmp_path, charter=charter, with_side_commit=True)
        assert side is not None
        assert refusal(repo.path) == "n0_commit_not_ancestor"


class TestTheGuardRefusesConditionC:
    @pytest.mark.parametrize("path", list(FILES))
    def test_a_missing_digest_line_for_each_file(self, tmp_path: Path, path: str) -> None:
        repo, _, _ = make_repo(
            tmp_path, charter=lambda c1, side: good_charter(c1, side, drop=(path,))
        )
        assert refusal(repo.path) == "digest_line_missing"

    @pytest.mark.parametrize("path", list(FILES))
    def test_a_repeated_digest_line_for_each_file(self, tmp_path: Path, path: str) -> None:
        def charter(c1: str, side: str | None) -> list[str]:
            return good_charter(c1, side, extra=(f"N7 frozen digest {path} {digests()[path]}",))

        repo, _, _ = make_repo(tmp_path, charter=charter)
        assert refusal(repo.path) == "digest_line_duplicated"

    @pytest.mark.parametrize("path", list(FILES))
    def test_an_edited_file_for_each_of_the_three(self, tmp_path: Path, path: str) -> None:
        repo, _, _ = make_repo(tmp_path)
        target = repo.path / path
        target.write_bytes(target.read_bytes() + b"# an amendment\n")
        assert refusal(repo.path) == "digest_mismatch"

    @pytest.mark.parametrize("path", list(FILES))
    def test_a_file_that_is_gone_for_each_of_the_three(self, tmp_path: Path, path: str) -> None:
        repo, _, _ = make_repo(tmp_path)
        (repo.path / path).unlink()
        assert refusal(repo.path) == "digest_file_unreadable"

    def test_a_digest_of_the_wrong_length_is_not_a_digest_line(self, tmp_path: Path) -> None:
        def charter(c1: str, side: str | None) -> list[str]:
            lines = good_charter(c1, side, drop=("scripts/n7_evaluate.py",))
            return [*lines, "N7 frozen digest scripts/n7_evaluate.py abc123"]

        repo, _, _ = make_repo(tmp_path, charter=charter)
        assert refusal(repo.path) == "digest_line_missing"


class TestTheGuardFailsClosed:
    def test_a_directory_that_is_not_a_repository(self, tmp_path: Path) -> None:
        assert refusal(tmp_path) == "charter_unreadable"

    def test_a_repository_without_the_charter_at_head(self, tmp_path: Path) -> None:
        repo, _, _ = make_repo(tmp_path, write_charter=False)
        assert refusal(repo.path) == "charter_unreadable"

    def test_no_git_on_the_path(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        repo, _, _ = make_repo(tmp_path)
        monkeypatch.setattr(n7.shutil, "which", lambda name: None)
        assert refusal(repo.path) == "git_unavailable"

    def test_conditions_are_checked_in_the_owners_order_after_the_charter_is_read(
        self, tmp_path: Path
    ) -> None:
        # No tag AND no N0 line: (a) is reported, not (b).
        repo, _, _ = make_repo(
            tmp_path, tag=None, charter=lambda c1, side: good_charter(c1, side, n0=[])
        )
        assert refusal(repo.path) == "tag_missing"


class TestMainRunsTheGuardFirstAndHasNoOverride:
    def test_main_refuses_before_it_reads_a_config_or_a_store(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        def explode(*args: object, **kwargs: object) -> None:
            raise AssertionError("the guard must refuse before anything is opened")

        monkeypatch.setattr(n7, "REPO_ROOT", tmp_path)
        monkeypatch.setattr(n7, "get_settings", explode)
        monkeypatch.setattr(n7, "evaluate", explode)
        code = n7.main(["--out", str(tmp_path / "result.json")])
        assert code == 2
        assert "refused: charter_unreadable" in capsys.readouterr().err
        assert not (tmp_path / "result.json").exists()

    def test_there_is_no_flag_and_no_environment_variable_that_skips_it(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        monkeypatch.setattr(n7, "REPO_ROOT", tmp_path)
        for name in ("N7_SKIP_GUARD", "N7_FORCE", "SKIP_GUARD", "FORCE"):
            monkeypatch.setenv(name, "1")
        with pytest.raises(SystemExit):
            n7.main(["--out", str(tmp_path / "r.json"), "--skip-guard"])
        assert n7.main(["--out", str(tmp_path / "r.json")]) == 2
        assert "refused:" in capsys.readouterr().err

    def test_the_only_options_are_config_data_dir_and_out(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        with pytest.raises(SystemExit):
            n7.main(["--help"])
        text = capsys.readouterr().out
        flags = {word.strip(",") for word in text.split() if word.startswith("-")}
        assert flags == {"-h", "--help", "--config", "--data-dir", "--out"}


# ---- world E1: the whole chain ---------------------------------------------------------------------------
class N7A(ScriptedD1):
    """Buys BTCUSDT on the bar of 2024-03-01; a minute at 90 will gap through its trail."""

    name = "n7_a"

    def __init__(self) -> None:
        super().__init__(buy={"BTCUSDT": ["2024-03-01T00:00"]})


class N7B(ScriptedD1):
    """Buys ETHUSDT on the bar of 2024-03-01 and holds it while the price steps up."""

    name = "n7_b"

    def __init__(self) -> None:
        super().__init__(buy={"ETHUSDT": ["2024-03-01T00:00"]})


class E1:
    def __init__(self, tmp: Path, mp: pytest.MonkeyPatch) -> None:
        mp.setitem(registry._REGISTRY, "n7_a", N7A)
        mp.setitem(registry._REGISTRY, "n7_b", N7B)
        mp.setattr(n7, "CANDIDATES", (("C1", "n7_a", "1d"), ("C2", "n7_b", "1d")))
        mp.setattr(n7, "IN_SAMPLE_BEGIN", datetime(2024, 3, 1, tzinfo=UTC))
        mp.setattr(n7, "IN_SAMPLE_END", datetime(2024, 3, 4, tzinfo=UTC))
        mp.setattr(n7, "RESAMPLES", 400)
        mp.setitem(n7.FLOORS, "1d", n7.Floors(1, 1))
        self.root = tmp / "hist"
        paths: dict[str, dict[int, Any]] = {
            "BTCUSDT": {2000: flat("90")},
            "ETHUSDT": {
                **{minute: flat("102") for minute in range(1500, 2880)},
                **{minute: flat("104") for minute in range(2880, 4320)},
            },
        }
        for symbol, minutes in paths.items():
            build_minutes(self.root, symbol, count=4320, minutes=minutes, decision="1d")
        self.settings = make_settings(
            tmp,
            self.root,
            pairs=[("BTCUSDT", "1d"), ("ETHUSDT", "1d")],
            strategy="n7_a",
            params={},
            start="2024-03-01",
            end="2024-03-04",
            n5=True,
        )

    def evaluate(self) -> n7.Evaluation:
        return asyncio.run(n7.evaluate(self.settings, str(self.root)))


@pytest.fixture(scope="module")
def e1(tmp_path_factory: pytest.TempPathFactory) -> tuple[E1, n7.Evaluation]:
    with pytest.MonkeyPatch.context() as mp:
        world = E1(tmp_path_factory.mktemp("e1"), mp)
        return world, world.evaluate()


E1_STAMPS = [DAY0 + timedelta(days=i) for i in range(4)]
E1_COSTS = {
    # name: (C1 gross, C1 fees, C1 final mark, C2 mark on 03-03, C2 mark on 03-04)
    "base": ("-222.37751130", "3.77562248970", "9773.84686621030", "10036.9620194995", "10076.9220394995"),
    "fee_0.075": (
        "-222.37751130", "2.8317168672750", "9774.7907718327250",
        "10037.461769499625", "10077.421789499625",
    ),
    "slip_0.66": (
        "-212.667226440", "3.785332774560", "9783.547440785440",
        "10036.9620194995", "10076.9220394995",
    ),
    "slip_0.10": (
        "-202.59730140", "3.79540269960", "9793.60729590040",
        "10036.9620194995", "10076.9220394995",
    ),
}  # fmt: skip


class TestWorldE1:
    def test_the_span_starts_on_the_first_day_every_indicator_is_defined(
        self, e1: tuple[E1, n7.Evaluation]
    ) -> None:
        _, evaluation = e1
        assert evaluation.window == (date(2024, 3, 1), date(2024, 3, 4))
        assert dict(evaluation.first_defined) == {"C1": date(2024, 3, 1), "C2": date(2024, 3, 1)}

    def test_c1_closes_one_trade_at_the_gapped_open_and_its_books_are_the_hand_arithmetic(
        self, e1: tuple[E1, n7.Evaluation]
    ) -> None:
        _, evaluation = e1
        c1 = evaluation.runs[0]
        assert (c1.label, c1.trades, c1.open_at_end) == ("C1", 1, 0)
        assert c1.gross == D("-222.37751130")
        assert c1.fees == D("3.77562248970")
        assert c1.entry_notional == D("1999.0000005")
        assert c1.gross - c1.fees == D("-226.15313378970")

    def test_c1_marks_are_flat_until_the_position_is_booked_at_the_next_midnight(
        self, e1: tuple[E1, n7.Evaluation]
    ) -> None:
        _, evaluation = e1
        c1 = evaluation.runs[0]
        assert [m[0] for m in c1.marks] == E1_STAMPS
        assert [m[1] for m in c1.marks] == [
            D(10000), D(10000), D("9773.84686621030"), D("9773.84686621030")
        ]  # fmt: skip
        assert c1.carried_marks == 0

    def test_c2_holds_an_open_position_that_is_marked_and_not_counted_as_a_trade(
        self, e1: tuple[E1, n7.Evaluation]
    ) -> None:
        _, evaluation = e1
        c2 = evaluation.runs[1]
        assert (c2.label, c2.trades, c2.open_at_end) == ("C2", 0, 1)
        assert (c2.gross, c2.fees, c2.entry_notional) == (D(0), D(0), D(0))
        assert [m[1] for m in c2.marks] == [
            D(10000), D(10000), D("10036.9620194995"), D("10076.9220394995")
        ]  # fmt: skip

    def test_the_judgement_is_the_derivations(self, e1: tuple[E1, n7.Evaluation]) -> None:
        _, evaluation = e1
        c1, c2 = evaluation.judgement.candidates
        assert evaluation.judgement.trials == 2
        assert (c1.days, c2.days) == (3, 3)
        assert c1.sharpe_annual == pytest.approx(-11.030261405182864, rel=1e-9)
        assert c1.boot_p5 is None and c1.boot_error is not None
        assert "no variance" in c1.boot_error
        assert c1.dsr == pytest.approx(0.015561786562121649, rel=1e-9)
        assert c1.status == "FAILED (bootstrap, dsr)"
        assert c2.sharpe_annual == pytest.approx(22.01503752889929, rel=1e-9)
        assert c2.boot_p5 == pytest.approx(22.015037528899285, rel=1e-9)
        assert c2.dsr == pytest.approx(0.6988559685368246, rel=1e-9)
        assert c2.status == "EXCLUDED (below floor)"
        assert (evaluation.judgement.outcome, evaluation.judgement.selected) == ("FAIL", None)

    def test_the_sensitivities_run_at_their_own_costs_and_flip_nothing(
        self, e1: tuple[E1, n7.Evaluation]
    ) -> None:
        _, evaluation = e1
        assert [s.costs.name for s in evaluation.sensitivities] == [
            "fee_0.075",
            "slip_0.66",
            "slip_0.10",
        ]
        for sensitivity in evaluation.sensitivities:
            gross, fees, final, day3, day4 = E1_COSTS[sensitivity.costs.name]
            c1, c2 = sensitivity.runs
            assert (c1.gross, c1.fees) == (D(gross), D(fees))
            assert c1.marks[-1][1] == D(final)
            assert [m[1] for m in c2.marks][2:] == [D(day3), D(day4)]
            assert sensitivity.flips == ()
            assert sensitivity.would_select == "none"

    def test_the_context_is_the_equal_weight_buy_and_hold(
        self, e1: tuple[E1, n7.Evaluation]
    ) -> None:
        _, evaluation = e1
        assert evaluation.context.days == 3
        assert evaluation.context.sharpe_annual == pytest.approx(22.05970379743417, rel=1e-9)

    def test_the_report_puts_the_fee_telemetry_first(self, e1: tuple[E1, n7.Evaluation]) -> None:
        _, evaluation = e1
        lines = n7.render(evaluation)
        assert lines[2] == "fee telemetry (telemetry only, never a criterion)"
        assert lines[3] == (
            "  C1 trades=1 gross=-222.3775113 fees=3.7756224897 net=-226.1531337897"
            " entry_notional=1999.0000005 fee_share=0.016978 fee_bps=18.8876 flag=gross<=0"
        )
        assert lines[4] == (
            "  C2 trades=0 gross=0 fees=0 net=0 entry_notional=0 fee_share=n/a fee_bps=n/a flag=no_trades"
        )
        assert "verdict FAIL at N7" in "\n".join(lines)


class TestMainOnTheFixtureWorldWithTheGuardSatisfied:
    def test_it_writes_one_result_file_prints_its_digest_and_refuses_a_second_run(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        repo, _, _ = make_repo(tmp_path / "guard")
        monkeypatch.setattr(n7, "REPO_ROOT", repo.path)
        world = E1(tmp_path, monkeypatch)
        result = tmp_path / "n7_result.json"
        out = io.StringIO()
        args = [
            "--config",
            str(world.settings.config_path),
            "--data-dir",
            str(world.root),
            "--out",
            str(result),
        ]
        assert n7.main(args, out=out) == 0
        printed = out.getvalue().splitlines()
        assert printed[2] == "fee telemetry (telemetry only, never a criterion)"
        digest = hashlib.sha256(result.read_bytes()).hexdigest()
        assert printed[-1] == f"result_sha256={digest}"
        assert printed[-2] == f"result_file={result}"
        document = json.loads(result.read_bytes())
        assert document["judgement"]["outcome"] == "FAIL"
        before = result.read_bytes()
        assert n7.main(args, out=io.StringIO()) == 2
        assert result.read_bytes() == before
