"""``scripts/s7_null.py``: the chance that a strategy with no edge passes S7 (R-CS).

The simulation is random, so what is tested is everything the randomness stands on: the null model (what is drawn, what is
removed, where it is placed), the five criteria evaluated for a block of sequences against a plain-Python reference that
walks each sequence trade by trade, the loader that ties a candidate to the run its entry froze, the family-wise formula, and
the command. The reference is the point: the vectorised bookkeeping (cumulative sums, quarter boundaries, the drawdown) is
exactly what a single sampled sequence cannot show to be right.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

import s7_null

from tests.unit.protocol_world import PROTOCOL_TEXT, REPO
from trading_bot.backtesting import selection as sel
from trading_bot.backtesting.gate import REGIMES, parse_gate_rules
from trading_bot.backtesting.metrics import TradeFacts
from trading_bot.backtesting.protocol import Entry, Variant
from trading_bot.backtesting.regimes import Regime, RegimeTable, quarter_bounds, quarter_key

GATE = parse_gate_rules(PROTOCOL_TEXT)
RULES = sel.parse_rules(PROTOCOL_TEXT)
UTC = timezone.utc


def table(label: str | None = None, *, by_year: dict[int, str] | None = None) -> RegimeTable:
    """A label for every quarter 2017Q3 to 2026Q3, 2017Q3 unlabelled (it is partial); ``label`` for all the rest."""
    regimes: dict[str, Regime | None] = {}
    for year in range(2017, 2027):
        for quarter in range(1, 5):
            key = f"{year}Q{quarter}"
            if key == "2017Q3":
                regimes[key] = None
            elif year == 2017 and quarter < 3:
                continue
            elif by_year is not None and year in by_year:
                regimes[key] = Regime(by_year[year])
            else:
                regimes[key] = Regime(label or "sideways")
    return RegimeTable(regimes, digest="d" * 64)


def trade(day: str, realised: str, quote: str = "200") -> TradeFacts:
    start = datetime.fromisoformat(day).replace(tzinfo=UTC)
    return TradeFacts(
        symbol="BTCUSDT",
        entry_time=start,
        exit_time=start,
        entry_notional=Decimal(quote),
        entry_fee=Decimal(0),
        entry_quote_total=Decimal(quote),
        exit_gross=Decimal(quote),
        exit_fee=Decimal(0),
        realised=Decimal(realised),
    )


def candidate(trades: list[TradeFacts], entry_id: str = "s6-x") -> s7_null.Candidate:
    days = (RULES.boundary - RULES.history_start).days
    return s7_null.Candidate(entry_id, "x 1h filter off ()", tuple(trades), days)


def mixed(n: int = 40) -> list[TradeFacts]:
    """Winners and losers spread over the in-sample years."""
    out = []
    for i in range(n):
        year = 2018 + i % 5
        out.append(trade(f"{year}-0{1 + i % 9}-1{i % 9}", "6" if i % 3 == 0 else "-3"))
    return out


def spread(n: int, *, win: str, lose: str) -> list[TradeFacts]:
    """``n`` in-sample trades over 2018 to 2022, one in four a winner."""
    return [
        trade(f"{2018 + i % 5}-0{1 + i % 9}-1{i % 9}", win if i % 4 == 0 else lose)
        for i in range(n)
    ]


def model(
    trades: list[TradeFacts] | None = None, tab: RegimeTable | None = None, **kw: Any
) -> s7_null.Model:
    return s7_null.build_model(
        candidate(trades or mixed()), rules=GATE, sel_rules=RULES, table=tab or table(), **kw
    )


# --------------------------------------------------------------------------------------
# The null model
# --------------------------------------------------------------------------------------
class TestTheNullModel:
    def test_the_mean_return_is_removed_and_reported(self) -> None:
        trades = mixed()
        kept = model(trades, demean=False)
        removed = model(trades)
        assert abs(float(removed.returns.mean())) < 1e-12
        assert float(kept.returns.mean()) == pytest.approx(removed.mean_return)
        assert removed.mean_return != 0.0
        np.testing.assert_allclose(removed.returns + removed.mean_return, kept.returns)

    def test_a_draw_is_the_trades_own_return_and_size_pair(self) -> None:
        trades = [trade("2018-01-05", "10", "100"), trade("2018-04-05", "-4", "200")]
        kept = model(trades, demean=False)
        np.testing.assert_allclose(kept.returns, [0.10, -0.02])
        np.testing.assert_allclose(kept.sizes, [100.0, 200.0])

    def test_the_thresholds_are_the_gates_own(self) -> None:
        assert model().thresholds == (1.3, 100, 0.20, 2)
        assert model().thresholds == (
            float(GATE.profit_factor_min),
            GATE.trades_min,
            float(GATE.max_drawdown_max),
            GATE.regimes_positive_min,
        )

    def test_the_expected_count_is_the_in_sample_rate_times_the_window(self) -> None:
        m = model(mixed(40))
        window = (GATE.window_end - GATE.window_start).days
        assert window == 1004
        in_sample_days = (RULES.boundary - RULES.history_start).days
        assert m.expected_simple == pytest.approx(40 / in_sample_days * window)
        assert int(m.quarter_days.sum()) == window and len(m.quarter_days) == 11

    def test_one_rate_for_every_quarter_when_timing_is_uniform(self) -> None:
        m = model(mixed(40), uniform_timing=True)
        assert float(m.quarter_means.sum()) == pytest.approx(m.expected_simple)
        assert np.allclose(m.quarter_means / m.quarter_days, m.quarter_means[0] / m.quarter_days[0])

    def test_regime_rates_follow_the_labels_the_trades_fell_in(self) -> None:
        # Every trade falls in a rising in-sample quarter; the out-of-sample window holds rising quarters (2024) and
        # sideways ones (2025, 2026). Only the rising quarters get trades, at the rising in-sample rate.
        tab = table("sideways", by_year={2018: "rising", 2024: "rising"})
        trades = [trade(f"2018-0{1 + i % 9}-10", "5" if i % 2 else "-5") for i in range(30)]
        m = model(trades, tab)
        rising_days = sum(
            (quarter_bounds(f"2018Q{q}")[1] - quarter_bounds(f"2018Q{q}")[0]).days
            for q in (1, 2, 3, 4)
        )
        oos_rising_days = sum(
            (quarter_bounds(f"2024Q{q}")[1] - quarter_bounds(f"2024Q{q}")[0]).days
            for q in (1, 2, 3, 4)
        )
        assert m.expected_by_regime == pytest.approx(30 / rising_days * oos_rising_days)
        assert m.expected_by_regime != pytest.approx(m.expected_simple)
        assert float(m.quarter_means[m.quarter_regime == REGIMES.index("sideways")].sum()) == 0.0

    def test_a_partial_unlabelled_quarter_is_neither_numerator_nor_denominator(self) -> None:
        early = [trade("2017-09-05", "5"), trade("2017-09-06", "-5"), *mixed(30)]
        with_early = model(early)
        without = model(mixed(30))
        assert with_early.expected_by_regime == pytest.approx(without.expected_by_regime)

    def test_a_candidate_with_no_trade_is_refused(self) -> None:
        with pytest.raises(s7_null.NullRefusedError, match="no in-sample trade"):
            s7_null.build_model(candidate([]), rules=GATE, sel_rules=RULES, table=table())

    def test_an_out_of_sample_quarter_without_a_label_is_refused(self) -> None:
        regimes = {k: v for k, v in table()._regimes.items() if k != "2025Q2"}
        with pytest.raises(s7_null.NullRefusedError, match="2025Q2"):
            model(tab=RegimeTable(regimes))

    def test_the_quarters_are_the_complete_ones_inside_the_window(self) -> None:
        got = s7_null._quarters(GATE.window_start, GATE.window_end)
        assert got[0] == "2024Q1" and got[-1] == "2026Q3" and len(got) == 11
        partial = s7_null._quarters(RULES.history_start, RULES.boundary)
        assert partial[0] == "2017Q4" and partial[-1] == "2023Q4"


# --------------------------------------------------------------------------------------
# The five criteria for a block of sequences, against a reference that walks each one
# --------------------------------------------------------------------------------------
def handmade(returns: list[float], sizes: list[float], regimes: list[int]) -> s7_null.Model:
    return s7_null.Model(
        returns=np.array(returns, dtype=np.float64),
        sizes=np.array(sizes, dtype=np.float64),
        quarter_means=np.zeros(len(regimes), dtype=np.float64),
        quarter_regime=np.array(regimes, dtype=np.int64),
        quarter_days=np.full(len(regimes), 90, dtype=np.int64),
        thresholds=(1.3, 100, 0.20, 2),
        mean_return=0.0,
        expected_simple=0.0,
        expected_by_regime=0.0,
    )


def reference(
    m: s7_null.Model, indices: np.ndarray[Any, Any], counts: np.ndarray[Any, Any]
) -> dict[str, bool]:
    """One sequence, trade by trade, in plain Python: the definition the vectorised code must agree with."""
    floor, trades_min, ceiling, regimes_min = m.thresholds
    sequence: list[tuple[float, float, int]] = []
    cursor = 0
    for quarter, count in enumerate(counts):
        for _ in range(int(count)):
            i = int(indices[cursor])
            sequence.append(
                (
                    float(m.returns[i]),
                    float(m.returns[i] * m.sizes[i]),
                    int(m.quarter_regime[quarter]),
                )
            )
            cursor += 1
    gains_r = sum(r for r, _, _ in sequence if r > 0)
    losses_r = -sum(r for r, _, _ in sequence if r < 0)
    gains_u = sum(p for _, p, _ in sequence if p > 0)
    losses_u = -sum(p for _, p, _ in sequence if p < 0)
    equity = peak = 10_000.0
    worst = 0.0
    for _, pnl, _ in sequence:
        equity += pnl
        peak = max(peak, equity)
        worst = max(worst, (peak - equity) / peak)
    net = [0.0, 0.0, 0.0]
    for _, pnl, regime in sequence:
        net[regime] += pnl
    return {
        "profit_factor_return": losses_r > 0 and gains_r >= floor * losses_r,
        "profit_factor_usdt": losses_u > 0 and gains_u >= floor * losses_u,
        "trades": len(sequence) >= trades_min,
        "drawdown": worst <= ceiling,
        "regimes": sum(1 for value in net if value > 0) >= regimes_min,
    }


class TestTheCriteria:
    def test_the_vectorised_criteria_agree_with_a_trade_by_trade_reference(self) -> None:
        rng = np.random.default_rng(7)
        # Calibrated (scratch/p120/calibrate_test.py) so that every criterion both passes and fails across the 60 draws.
        m = handmade(
            list(rng.normal(0.012, 0.04, 60)),
            list(rng.uniform(3000, 7000, 60)),
            [0, 1, 2, 0, 1, 2, 0, 0],
        )
        counts = rng.integers(6, 24, size=(60, 8)).astype(np.int64)
        longest = int(counts.sum(axis=1).max())
        indices = rng.integers(0, 60, size=(60, longest)).astype(np.int64)
        everything, flags, totals = s7_null.evaluate_chunk(m, indices, counts)
        seen = dict.fromkeys(flags, 0)
        for draw in range(60):
            want = reference(m, indices[draw], counts[draw])
            for name in flags:
                assert bool(flags[name][draw]) == want[name], (draw, name)
                seen[name] += int(want[name])
            assert bool(everything[draw]) == all(want.values())
            assert int(totals[draw]) == int(counts[draw].sum())
        # The block exercises both outcomes of the criteria that can vary, or it checks nothing.
        for name in flags:
            assert 0 < seen[name] < 60, name
        assert 0 < int(everything.sum()) < 60

    def test_a_profit_factor_with_no_losing_trade_does_not_pass(self) -> None:
        m = handmade([0.02, 0.03], [200.0, 200.0], [0])
        counts = np.array([[150]], dtype=np.int64)
        indices = np.zeros((1, 150), dtype=np.int64)
        _, flags, _ = s7_null.evaluate_chunk(m, indices, counts)
        assert not flags["profit_factor_return"][0] and not flags["profit_factor_usdt"][0]

    def test_the_trade_count_is_at_least_the_minimum(self) -> None:
        m = handmade([0.05, -0.01], [200.0, 200.0], [0])
        for n, met in ((99, False), (100, True)):
            counts = np.array([[n]], dtype=np.int64)
            indices = np.zeros((1, n), dtype=np.int64)
            _, flags, _ = s7_null.evaluate_chunk(m, indices, counts)
            assert bool(flags["trades"][0]) is met

    def test_a_drawdown_over_the_ceiling_fails_and_one_at_it_passes(self) -> None:
        # One loser of 2,000 on 10,000 is exactly 0.20: at the ceiling passes; 2,001 fails.
        for loss, met in ((0.20, True), (0.2001, False)):
            m = handmade([-loss], [10_000.0], [0])
            counts = np.array([[1]], dtype=np.int64)
            indices = np.zeros((1, 1), dtype=np.int64)
            _, flags, _ = s7_null.evaluate_chunk(m, indices, counts)
            assert bool(flags["drawdown"][0]) is met, loss

    def test_the_drawdown_is_from_the_peak_not_from_the_start(self) -> None:
        # Up 5,000, then down 3,000: 3,000 / 15,000 = 0.20 from the peak (passes); from the start it is a gain.
        m = handmade([0.5, -0.3], [10_000.0, 10_000.0], [0, 0])
        counts = np.array([[1, 1]], dtype=np.int64)
        indices = np.array([[0, 1]], dtype=np.int64)
        _, flags, _ = s7_null.evaluate_chunk(m, indices, counts)
        assert bool(flags["drawdown"][0])
        worse = handmade([0.5, -0.31], [10_000.0, 10_000.0], [0, 0])
        _, flags, _ = s7_null.evaluate_chunk(worse, indices, counts)
        assert not bool(flags["drawdown"][0])

    @pytest.mark.parametrize(
        ("net", "met"),
        [
            ((5.0, 5.0, -1.0), True),
            ((5.0, -1.0, -1.0), False),
            ((5.0, 0.0, 0.0), False),
            ((1.0, 1.0, 1.0), True),
        ],
    )
    def test_two_of_three_regimes_must_be_net_positive_and_zero_is_not_positive(
        self, net: tuple[float, float, float], met: bool
    ) -> None:
        m = handmade(list(net), [100.0, 100.0, 100.0], [0, 1, 2])
        counts = np.array([[1, 1, 1]], dtype=np.int64)
        indices = np.array([[0, 1, 2]], dtype=np.int64)
        # pnl per regime = net/100 * 100 = net; scale the returns so the quarter sums are the figures above
        _, flags, _ = s7_null.evaluate_chunk(m, indices, counts)
        assert bool(flags["regimes"][0]) is met

    def test_a_quarter_with_no_trade_adds_nothing_to_its_regime(self) -> None:
        m = handmade([0.02, 0.02], [100.0, 100.0], [0, 1, 2])
        counts = np.array([[2, 0, 0]], dtype=np.int64)
        indices = np.zeros((1, 2), dtype=np.int64)
        _, flags, _ = s7_null.evaluate_chunk(m, indices, counts)
        assert not bool(flags["regimes"][0])  # one regime positive, two empty (zero), so 1 of 3


# --------------------------------------------------------------------------------------
# The simulation
# --------------------------------------------------------------------------------------
class TestTheSimulation:
    def test_the_same_seed_gives_the_same_counts_and_another_does_not(self) -> None:
        m = model()
        a, b, c = (s7_null.simulate(m, draws=3000, seed=s) for s in (5, 5, 6))
        assert (a.passed, dict(a.met), a.trades_total) == (b.passed, dict(b.met), b.trades_total)
        assert (a.trades_total, dict(a.met)) != (c.trades_total, dict(c.met))

    def test_an_edge_that_is_kept_passes_almost_always_and_the_null_of_the_same_trades_rarely(
        self,
    ) -> None:
        winners = spread(400, win="12", lose="-2")
        mix = table(by_year={2018: "rising", 2019: "falling", 2024: "rising", 2025: "falling"})
        edge = s7_null.simulate(model(winners, mix, demean=False), draws=4000, seed=1)
        null = s7_null.simulate(model(winners, mix), draws=4000, seed=1)
        assert edge.probability > 0.95
        assert null.probability < 0.5 * edge.probability

    def test_a_losing_strategy_as_observed_never_passes(self) -> None:
        losers = spread(400, win="2", lose="-6")
        assert s7_null.simulate(model(losers, demean=False), draws=3000, seed=2).passed == 0

    def test_a_strategy_whose_trades_are_all_equal_has_no_losing_trade_to_divide_by(self) -> None:
        same = [trade(f"2018-0{1 + i % 9}-10", "5") for i in range(30)]
        assert (
            s7_null.simulate(model(same), draws=1500, seed=3).passed == 0
        )  # demeaned: every return is zero

    def test_too_few_expected_trades_cannot_pass_the_trade_test(self) -> None:
        few = [trade("2018-01-10", "5"), trade("2018-04-10", "-5")]
        outcome = s7_null.simulate(model(few, demean=False), draws=2000, seed=4)
        assert outcome.met["trades"] == 0 and outcome.passed == 0

    def test_a_window_labelled_with_one_regime_cannot_pass_the_regime_test(self) -> None:
        one = table("rising")
        winners = spread(400, win="8", lose="-2")
        outcome = s7_null.simulate(model(winners, one, demean=False), draws=2000, seed=5)
        assert outcome.met["regimes"] == 0 and outcome.passed == 0

    def test_a_draw_count_that_is_not_a_multiple_of_the_chunk_is_run_in_full(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(s7_null, "_CHUNK", 7)
        outcome = s7_null.simulate(model(), draws=20, seed=9)
        assert outcome.draws == 20 and 0 <= outcome.passed <= 20
        assert all(0 <= count <= 20 for count in outcome.met.values())

    def test_the_probability_and_its_standard_error(self) -> None:
        outcome = s7_null.Outcome(draws=100, passed=10, met={}, trades_total=0)
        assert outcome.probability == 0.1
        assert outcome.standard_error == pytest.approx((0.1 * 0.9 / 100) ** 0.5)


class TestFamilyWise:
    def test_independence_and_the_two_bounds(self) -> None:
        got = s7_null.family_wise([0.1, 0.2])
        assert got["independent"] == pytest.approx(1 - 0.9 * 0.8)
        assert got["lower_bound"] == 0.2 and got["upper_bound"] == pytest.approx(0.3)

    def test_the_upper_bound_is_capped_at_one(self) -> None:
        assert s7_null.family_wise([0.7, 0.6])["upper_bound"] == 1.0

    def test_no_candidate_is_no_chance(self) -> None:
        assert s7_null.family_wise([]) == {
            "independent": 0.0,
            "lower_bound": 0.0,
            "upper_bound": 0.0,
        }

    def test_independence_lies_between_the_bounds(self) -> None:
        got = s7_null.family_wise([0.05, 0.08, 0.02])
        assert got["lower_bound"] <= got["independent"] <= got["upper_bound"]


# --------------------------------------------------------------------------------------
# The loader: a candidate is the run its entry froze
# --------------------------------------------------------------------------------------
def entry(
    entry_id: str = "s6-x", *, kind: str = "candidate", selection: dict[str, Any] | None = None
) -> Entry:
    chosen = (
        {"in_sample_run": "run-1", "in_sample_run_json_sha256": "a" * 64}
        if selection is None
        else selection
    )
    return Entry(
        sha256="e" * 64, id=entry_id, kind=kind, ref="x", candidate_digest="c" * 64,
        arms=("0.05", "0.66", "1.2"), status="pending", oos=None, selection=chosen,
    )  # fmt: skip


def point(digest: str = "a" * 64) -> sel.PointRun:
    return sel.PointRun(
        variant=Variant("rsi", "1h", False, {"period": "7"}),
        run="run-1",
        record_sha256=digest,
        candidate_digest="c" * 64,
        trade_log_sha256="t" * 64,
        trades=tuple(mixed(10)),
        max_drawdown=Decimal("0.1"),
        usdt_profit_factor=Decimal("0.5"),
        initial_balance=Decimal(10000),
        daily_closes=(),
    )


class TestLoadingCandidates:
    def load(
        self, entries: list[Entry], monkeypatch: pytest.MonkeyPatch, got: Any
    ) -> tuple[Any, ...]:
        monkeypatch.setattr(sel, "read_run", lambda *_a, **_k: got)
        return s7_null.load_candidates(entries, Path("b"), object(), RULES)

    def test_a_candidate_is_its_entrys_frozen_run(self, monkeypatch: pytest.MonkeyPatch) -> None:
        (found,) = self.load([entry()], monkeypatch, point())
        assert found.entry_id == "s6-x" and len(found.trades) == 10
        assert found.variant == "rsi 1h filter off (period=7)"
        assert found.in_sample_days == (RULES.boundary - RULES.history_start).days

    def test_a_run_whose_record_is_not_the_frozen_one_is_refused(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        with pytest.raises(s7_null.NullRefusedError, match="froze"):
            self.load([entry()], monkeypatch, point("b" * 64))

    def test_a_run_that_is_not_a_point_run_is_refused(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        skipped = sel.SkippedRun("run-1", sel.SkipReason.NOT_SEALED, "never sealed")
        with pytest.raises(s7_null.NullRefusedError, match="not_sealed"):
            self.load([entry()], monkeypatch, skipped)

    def test_an_entry_that_names_no_run_is_refused(self, monkeypatch: pytest.MonkeyPatch) -> None:
        with pytest.raises(s7_null.NullRefusedError, match="no in-sample run"):
            self.load([entry(selection={})], monkeypatch, point())

    def test_an_entry_that_is_not_a_candidates_is_left_alone(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        assert self.load([entry("s5-baseline", kind="baseline")], monkeypatch, point()) == ()


# --------------------------------------------------------------------------------------
# The command
# --------------------------------------------------------------------------------------
class TestTheCommand:
    def world(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> list[str]:
        research = tmp_path / "research"
        (research / "entries").mkdir(parents=True)
        (research / "PROTOCOL.md").write_text(PROTOCOL_TEXT, encoding="utf-8", newline="\n")
        body = {
            "entry_schema": 1, "id": "s6-x", "kind": "candidate", "ref": "x",
            "candidate_digest": "c" * 64, "arms": ["0.05", "0.66", "1.2"], "status": "pending", "oos": None,
            "selection": {"variant": {"family": "x", "timeframe": "1h", "filtered": False, "params": {}},
                          "in_sample_run": "run-1", "in_sample_run_json_sha256": "a" * 64},
        }  # fmt: skip
        (research / "entries" / "s6-x.json").write_text(
            json.dumps(body, indent=2) + "\n", encoding="ascii", newline="\n"
        )
        backtests = tmp_path / "bt"
        backtests.mkdir()
        monkeypatch.setattr(sel, "read_run", lambda *_a, **_k: point())
        monkeypatch.setattr(RegimeTable, "from_file", classmethod(lambda cls, _p: table()))
        return [
            "--backtests",
            str(backtests),
            "--protocol",
            str(research / "PROTOCOL.md"),
            "--draws",
            "300",
        ]

    def test_it_prints_a_report_and_writes_an_ascii_document(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        argv = self.world(tmp_path, monkeypatch)
        out = tmp_path / "null.json"
        assert s7_null.main([*argv, "--out", str(out)]) == 0
        text = capsys.readouterr().out
        assert "NO-EDGE PASS PROBABILITY" in text and "FAMILY-WISE over 1 candidates" in text
        assert all(ord(c) < 128 for c in text)
        data = out.read_bytes()
        assert b"\r" not in data and data.endswith(b"\n")
        document = json.loads(data)
        assert document["s7_null_schema"] == 1 and document["draws"] == 300
        assert document["window"]["days"] == 1004 and len(document["oos_quarters"]) == 11
        assert sum(document["oos_regime_counts"].values()) == 11
        assert [c["entry_id"] for c in document["candidates"]] == ["s6-x"]

    def test_the_same_inputs_and_seed_write_the_same_bytes(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        argv = self.world(tmp_path, monkeypatch)
        for name in ("a.json", "b.json"):
            assert s7_null.main([*argv, "--out", str(tmp_path / name)]) == 0
        assert (tmp_path / "a.json").read_bytes() == (tmp_path / "b.json").read_bytes()

    def test_a_missing_backtests_directory_is_refused(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        argv = self.world(tmp_path, monkeypatch)
        argv[1] = str(tmp_path / "absent")
        assert s7_null.main(argv) == s7_null.EXIT_REFUSED
        assert "is not a directory" in capsys.readouterr().err

    def test_no_candidate_entry_is_refused(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        argv = self.world(tmp_path, monkeypatch)
        (tmp_path / "research" / "entries" / "s6-x.json").unlink()
        assert s7_null.main(argv) == s7_null.EXIT_REFUSED
        assert "holds no candidate entry" in capsys.readouterr().err

    def test_a_draw_count_below_one_is_refused(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        argv = self.world(tmp_path, monkeypatch)
        assert s7_null.main([*argv, "--draws", "0"]) == s7_null.EXIT_REFUSED
        assert "--draws" in capsys.readouterr().err

    def test_labels_that_fail_their_digest_are_refused(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        argv = self.world(tmp_path, monkeypatch)
        monkeypatch.undo()
        labels = tmp_path / "labels.json"
        labels.write_text("{}", encoding="ascii")
        assert s7_null.main([*argv, "--labels", str(labels)]) == s7_null.EXIT_REFUSED
        assert "cannot be used" in capsys.readouterr().err


class TestTheScriptReadsNoBarAndNoOutOfSampleRecord:
    """R-CN: the null check uses the window's dates and the committed quarter labels, and nothing else out of sample."""

    def code(self) -> str:
        import ast

        tree = ast.parse((REPO / "scripts" / "s7_null.py").read_text("utf-8"))
        docstrings: set[int] = set()
        for node in ast.walk(tree):
            body = getattr(node, "body", None)
            if isinstance(body, list) and body:
                first = body[0]
                if (
                    isinstance(first, ast.Expr)
                    and isinstance(first.value, ast.Constant)
                    and isinstance(first.value.value, str)
                ):
                    docstrings.add(id(first.value))
        strings = [
            n.value
            for n in ast.walk(tree)
            if isinstance(n, ast.Constant) and isinstance(n.value, str) and id(n) not in docstrings
        ]
        return "\n".join(strings)

    def test_it_names_no_store_and_no_run_record_file(self) -> None:
        text = self.code()
        for banned in ("historical", "run.json", "mainnet-historical"):
            assert banned not in text, banned

    def test_it_reads_in_sample_runs_only_through_the_selection_reader(self) -> None:
        source = (REPO / "scripts" / "s7_null.py").read_text("utf-8")
        assert (
            "sel.read_run(" in source
            and "read_arm" not in source
            and "load_trades_csv" not in source
        )

    def test_quarter_key_agrees_with_the_labels_it_looks_up(self) -> None:
        from datetime import date

        assert (
            quarter_key(date(2024, 1, 1)) == "2024Q1" and quarter_key(date(2026, 9, 30)) == "2026Q3"
        )
