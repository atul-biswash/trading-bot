"""R-BT, S6: the guard that makes "read once per candidate" mechanical.

Every rule of :func:`check_run` refuses what it should, for the reason it names and in the order its docstring
states, and allows the three arms of a candidate or of the baseline exactly once. The declaration and the
builders are ``tests/unit/protocol_world.py``; the parser and the grid are ``test_backtest_protocol.py``.
"""

from __future__ import annotations

from datetime import date
from typing import Any

import pytest

from tests.unit.protocol_world import (
    BOUNDARY,
    CANDIDATE,
    FULL,
    HISTORY_END,
    OFF_GRID,
    OOS,
    PROTOCOL,
    baseline_effective,
    effective,
    entry_for,
)
from trading_bot.backtesting.candidate import candidate_digest
from trading_bot.backtesting.protocol import (
    Decision,
    Entry,
    ProtocolRefusalError,
    Refusal,
    WindowClass,
    check_run,
)


def run(
    entries: list[Entry],
    eff: dict[str, Any],
    window: tuple[date, date] = OOS,
    *,
    accepted: bool = True,
    reads: set[tuple[str, str]] | None = None,
) -> Decision:
    return check_run(
        PROTOCOL,
        entries,
        effective=eff,
        window_start=window[0],
        window_end=window[1],
        provenance_accepted=accepted,
        local_reads=reads or set(),
    )


def refused(
    entries: list[Entry], eff: dict[str, Any], window: tuple[date, date] = OOS, **kw: Any
) -> Refusal:
    with pytest.raises(ProtocolRefusalError) as raised:
        run(entries, eff, window, **kw)
    return raised.value.reason


# --------------------------------------------------------------------------------------
# The guard
# --------------------------------------------------------------------------------------


class TestAWindowInSampleNeedsNothing:
    def test_no_entry_and_no_provenance_are_needed(self) -> None:
        decision = run([], CANDIDATE, (date(2017, 8, 17), BOUNDARY), accepted=False)
        assert decision.window_class is WindowClass.IN_SAMPLE
        assert decision.entry_id is None and decision.kind is None
        assert decision.variant is not None
        assert decision.arm == "1.2"

    def test_a_variant_off_the_grids_may_be_run_in_sample_and_is_not_a_variant(self) -> None:
        decision = run([], OFF_GRID, (date(2020, 1, 1), date(2021, 1, 1)), accepted=False)
        assert decision.window_class is WindowClass.IN_SAMPLE
        assert decision.variant is None

    def test_the_record_block_says_so(self) -> None:
        block = run([], CANDIDATE, (date(2020, 1, 1), date(2021, 1, 1))).record()
        assert block["window_class"] == "in_sample"
        assert block["protocol_sha256"] == PROTOCOL.sha256
        assert block["entry_id"] is None and block["entry_sha256"] is None and block["kind"] is None


class TestACandidateReadOutOfSample:
    def test_a_committed_pending_entry_allows_the_declared_window_at_each_arm(self) -> None:
        for arm in ("0.05", "0.66", "1.2"):
            eff = effective(arm=arm)
            entries = [entry_for(eff, entry_id="c1")]
            decision = run(entries, eff)
            assert decision.window_class is WindowClass.OUT_OF_SAMPLE
            assert decision.kind == "candidate" and decision.entry_id == "c1"
            assert decision.arm == arm
            assert decision.entry_sha256 == entries[0].sha256
            assert decision.variant is not None and decision.variant.family == "sma_crossover"

    def test_the_record_block_names_the_entry_the_variant_and_the_protocol(self) -> None:
        entries = [entry_for(CANDIDATE, entry_id="c1")]
        block = run(entries, CANDIDATE).record()
        assert block["window_class"] == "out_of_sample"
        assert block["kind"] == "candidate" and block["entry_id"] == "c1"
        assert block["entry_sha256"] == entries[0].sha256
        assert block["protocol_sha256"] == PROTOCOL.sha256
        assert block["variant"] == {
            "family": "sma_crossover",
            "timeframe": "4h",
            "filtered": False,
            "params": {"fast_period": "20", "slow_period": "100"},
        }

    def test_the_entry_is_found_among_others_by_its_digest(self) -> None:
        other = effective(params={"fast_period": 30, "slow_period": 100})
        entries = [entry_for(other, entry_id="o"), entry_for(CANDIDATE, entry_id="c1")]
        assert run(entries, CANDIDATE).entry_id == "c1"


class TestEachRefusal:
    def test_a_run_not_from_an_accepted_clone_is_refused_for_provenance(self) -> None:
        entries = [entry_for(CANDIDATE)]
        assert refused(entries, CANDIDATE, accepted=False) is Refusal.PROVENANCE

    def test_no_entry_at_all(self) -> None:
        assert refused([], CANDIDATE) is Refusal.NO_ENTRY

    def test_an_entry_for_another_candidate_is_no_entry_for_this_one(self) -> None:
        other = effective(params={"fast_period": 30, "slow_period": 100})
        assert refused([entry_for(other)], CANDIDATE) is Refusal.NO_ENTRY

    def test_a_candidate_off_the_grids_cannot_be_read_even_with_an_entry(self) -> None:
        assert refused([entry_for(OFF_GRID)], OFF_GRID) is Refusal.NOT_A_GRID_POINT

    @pytest.mark.parametrize(
        "window",
        [
            (date(2023, 6, 1), HISTORY_END),
            (BOUNDARY, date(2026, 9, 1)),
            (date(2024, 2, 1), HISTORY_END),
            FULL,
            (date(2024, 1, 1), date(2024, 1, 2)),
        ],
        ids=["straddling", "ends-early", "starts-late", "whole-history", "one-day"],
    )
    def test_a_candidate_is_read_over_exactly_the_declared_window(
        self, window: tuple[date, date]
    ) -> None:
        assert refused([entry_for(CANDIDATE)], CANDIDATE, window) is Refusal.WRONG_WINDOW

    @pytest.mark.parametrize(
        "arms",
        [("1.20",), ("0.05", "0.66"), ("0.05", "0.66", "1.20", "2.0"), ("0.05", "0.66", "0.7")],
        ids=["one-arm", "two-arms", "four-arms", "a-foreign-arm"],
    )
    def test_an_entry_must_list_exactly_the_protocols_arms(self, arms: tuple[str, ...]) -> None:
        assert refused([entry_for(CANDIDATE, arms=arms)], CANDIDATE) is Refusal.ARMS_MISMATCH

    def test_an_arm_the_protocol_does_not_declare_is_refused(self) -> None:
        eff = effective(arm="0.5")
        assert refused([entry_for(eff)], eff) is Refusal.ARM_NOT_DECLARED

    def test_an_entry_already_read_is_refused(self) -> None:
        read = entry_for(
            CANDIDATE,
            status="read",
            oos={"records": {"0.05": "a" * 64, "0.66": "b" * 64, "1.2": "c" * 64}},
        )
        assert refused([read], CANDIDATE) is Refusal.ALREADY_READ

    def test_a_record_this_clone_already_holds_refuses_that_arm_only(self) -> None:
        entries = [entry_for(CANDIDATE)]
        digest = candidate_digest(CANDIDATE)
        reads = {(digest, "1.2")}
        assert refused(entries, CANDIDATE, reads=reads) is Refusal.LOCAL_PRIOR_READ
        other_arm = effective(arm="0.66")
        assert run([entry_for(other_arm)], other_arm, reads=reads).arm == "0.66"

    def test_a_read_of_another_candidate_in_this_clone_does_not_block_this_one(self) -> None:
        entries = [entry_for(CANDIDATE)]
        reads = {("f" * 64, "1.2")}
        assert run(entries, CANDIDATE, reads=reads).entry_id == "e1"


class TestTheOrderOfTheRules:
    """Each pair below is a run that breaks two rules; the earlier rule must be the one named."""

    def test_provenance_comes_before_the_entry(self) -> None:
        assert refused([], CANDIDATE, accepted=False) is Refusal.PROVENANCE

    def test_the_entry_comes_before_the_grid(self) -> None:
        assert refused([], OFF_GRID) is Refusal.NO_ENTRY

    def test_the_grid_comes_before_the_window(self) -> None:
        assert refused([entry_for(OFF_GRID)], OFF_GRID, FULL) is Refusal.NOT_A_GRID_POINT

    def test_the_window_comes_before_the_arms(self) -> None:
        bad_arms = entry_for(CANDIDATE, arms=("1.20",))
        assert refused([bad_arms], CANDIDATE, FULL) is Refusal.WRONG_WINDOW

    def test_the_arms_come_before_the_status(self) -> None:
        read = entry_for(CANDIDATE, arms=("1.20",), status="read", oos={"records": {}})
        assert refused([read], CANDIDATE) is Refusal.ARMS_MISMATCH

    def test_the_arm_comes_before_the_status(self) -> None:
        eff = effective(arm="0.5")
        read = entry_for(eff, status="read", oos={"records": {}})
        assert refused([read], eff) is Refusal.ARM_NOT_DECLARED

    def test_the_status_comes_before_the_local_record(self) -> None:
        read = entry_for(CANDIDATE, status="read", oos={"records": {}})
        digest = candidate_digest(CANDIDATE)
        assert refused([read], CANDIDATE, reads={(digest, "1.2")}) is Refusal.ALREADY_READ


class TestTheBaseline:
    def test_the_whole_history_is_allowed_to_the_declared_baseline_at_each_arm(self) -> None:
        for arm in ("0.05", "0.66", "1.2"):
            eff = baseline_effective(arm)
            entries = [entry_for(eff, entry_id="s5-baseline", kind="baseline", ref="s5-baseline")]
            decision = run(entries, eff, FULL)
            assert decision.kind == "baseline" and decision.entry_id == "s5-baseline"
            assert decision.window_class is WindowClass.STRADDLING
            assert decision.variant is None

    def test_a_baseline_entry_does_not_allow_the_candidate_window(self) -> None:
        eff = baseline_effective()
        entries = [entry_for(eff, kind="baseline", ref="s5-baseline")]
        assert refused(entries, eff, OOS) is Refusal.WRONG_WINDOW

    def test_a_baseline_entry_naming_an_undeclared_baseline_is_a_mismatch(self) -> None:
        eff = baseline_effective()
        assert refused([entry_for(eff, kind="baseline", ref="elsewhere")], eff, FULL) is (
            Refusal.BASELINE_MISMATCH
        )

    def test_a_run_that_is_not_the_declared_baseline_is_a_mismatch(self) -> None:
        eff = effective(params={"fast_period": 10, "slow_period": 50}, timeframes=("1m", "5m"))
        entries = [entry_for(eff, kind="baseline", ref="s5-baseline")]
        assert refused(entries, eff, FULL) is Refusal.BASELINE_MISMATCH

    def test_a_baseline_with_other_costs_is_a_mismatch(self) -> None:
        eff = effective(
            params={"fast_period": 20, "slow_period": 50}, timeframes=("1m", "5m"), fee="0"
        )
        entries = [entry_for(eff, kind="baseline", ref="s5-baseline")]
        assert refused(entries, eff, FULL) is Refusal.BASELINE_MISMATCH

    def test_a_baseline_is_read_once_per_arm_too(self) -> None:
        eff = baseline_effective()
        entries = [entry_for(eff, kind="baseline", ref="s5-baseline")]
        digest = candidate_digest(eff)
        assert refused(entries, eff, FULL, reads={(digest, "1.2")}) is Refusal.LOCAL_PRIOR_READ

    def test_a_baseline_entry_already_read_is_refused(self) -> None:
        eff = baseline_effective()
        read = entry_for(
            eff, kind="baseline", ref="s5-baseline", status="read", oos={"records": {}}
        )
        assert refused([read], eff, FULL) is Refusal.ALREADY_READ

    def test_the_baseline_runs_in_sample_without_an_entry(self) -> None:
        decision = run([], baseline_effective(), (date(2017, 8, 17), BOUNDARY), accepted=False)
        assert decision.window_class is WindowClass.IN_SAMPLE


class TestTheRefusalCarriesItsReason:
    def test_the_message_names_the_reason_and_the_window(self) -> None:
        with pytest.raises(ProtocolRefusalError) as raised:
            run([], CANDIDATE)
        assert raised.value.reason is Refusal.NO_ENTRY
        assert str(raised.value).startswith("[no_entry] ")
        assert "2024-01-01 to 2026-10-01" in str(raised.value)
        assert candidate_digest(CANDIDATE) in str(raised.value)

    def test_the_vocabulary_is_the_nine_refusals_tested_above(self) -> None:
        """A member nothing tests is dead vocabulary: each of these nine has a test in this module that
        makes the guard raise it, and a tenth would have to earn one."""
        assert {r.value for r in Refusal} == {
            "provenance",
            "no_entry",
            "not_a_grid_point",
            "baseline_mismatch",
            "wrong_window",
            "arms_mismatch",
            "arm_not_declared",
            "already_read",
            "local_prior_read",
        }
