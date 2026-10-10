"""R-BR: the effective settings of a run, and the two digests that name a candidate.

The ruling, verbatim: *"Every effective setting is written into the run record and into the candidate
digest; a record without them is not evidence_eligible."* What is proved here is what makes the digest
mean something: it does not move with how a value was typed, it moves with every setting that defines a
candidate, it leaves the stop-slippage arm out of the candidate and puts it in the settings, and a real
run writes the block and digests that the evidence door then re-computes.
"""

from __future__ import annotations

import copy
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from tests.unit.backtest_world import CODE, build_world, make_settings
from trading_bot.backtesting.candidate import (
    EffectiveSettingsError,
    candidate_arm,
    candidate_digest,
    canonical_number,
    canonical_value,
    check_record_digests,
    effective_settings,
    settings_digest,
)
from trading_bot.backtesting.engine import run_backtest
from trading_bot.config.settings import Settings


def effective_of(
    settings: Settings,
    *,
    pairs: tuple[tuple[str, str], ...] = (("BTCUSDT", "1h"),),
    sha: str | None = "a" * 64,
    overrides: dict[str, object] | None = None,
) -> dict[str, Any]:
    return effective_settings(
        settings.config,
        settings.config.backtesting,
        pairs,
        config_sha256=sha,
        overrides=overrides,
    )


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return make_settings(tmp_path, tmp_path / "hist")


class TestCanonicalValues:
    @pytest.mark.parametrize(
        ("value", "expected"),
        [
            (30, "30"),
            (30.0, "30"),
            (Decimal("30"), "30"),
            (Decimal("30.000"), "30"),
            (Decimal("3E+1"), "30"),
            (0, "0"),
            (0.0, "0"),
            (-0.0, "0"),
            (Decimal("0.00"), "0"),
            (1.2, "1.2"),
            (Decimal("1.20"), "1.2"),
            (Decimal("0.05"), "0.05"),
            (-2.5, "-2.5"),
            (100, "100"),
            (1e21, "1000000000000000000000"),
        ],
    )
    def test_a_number_is_the_same_whichever_way_it_was_typed(
        self, value: object, expected: str
    ) -> None:
        assert canonical_value(value) == expected
        assert canonical_number(value) == expected

    def test_a_boolean_stays_a_boolean_and_is_never_read_as_one(self) -> None:
        assert canonical_value(True) is True
        assert canonical_value(False) is False
        assert canonical_value(True) != canonical_value(1)

    def test_text_and_none_pass_through(self) -> None:
        assert canonical_value("abc") == "abc"
        assert canonical_value("30") == "30"
        assert canonical_value(None) is None

    def test_containers_are_recursed_and_their_keys_become_text(self) -> None:
        assert canonical_value({"a": [1, 2.0, {"b": Decimal("3.0")}], 7: True}) == {
            "a": ["1", "2", {"b": "3"}],
            "7": True,
        }
        assert canonical_value((1, 2)) == ["1", "2"]

    @pytest.mark.parametrize("bad", [float("nan"), float("inf"), float("-inf"), Decimal("NaN")])
    def test_a_number_that_is_not_finite_is_refused(self, bad: object) -> None:
        with pytest.raises(EffectiveSettingsError, match="not a finite number"):
            canonical_value(bad)

    def test_a_value_of_an_unsupported_type_is_refused_and_named(self) -> None:
        with pytest.raises(EffectiveSettingsError, match="object cannot be part"):
            canonical_value(object())
        with pytest.raises(EffectiveSettingsError, match="set cannot be part"):
            canonical_value({1})


class TestTheEffectiveBlock:
    def test_it_holds_what_the_run_used(self, settings: Settings) -> None:
        block = effective_of(settings, overrides={"stop_slippage_percent": "0.66"})
        assert block["config_sha256"] == "a" * 64
        assert block["strategy"] == {
            "name": "sma_crossover",
            "params": {"fast_period": "3", "slow_period": "8"},
        }
        assert block["pairs"] == [{"symbol": "BTCUSDT", "timeframe": "1h"}]
        assert block["risk"] == {"max_position_staleness_s": "10800"}
        assert block["exchange_info_environment"] == "mainnet"
        assert block["costs"] == {
            "fee_percent": "0.1",
            "slippage_percent": "0.05",
            "stop_slippage_percent": "1.2",
            "initial_balance": "10000",
        }
        assert block["overrides"] == {"stop_slippage_percent": "0.66"}

    def test_a_config_of_unknown_digest_is_recorded_as_none_not_as_a_guess(
        self, settings: Settings
    ) -> None:
        assert effective_of(settings, sha=None)["config_sha256"] is None

    def test_the_pairs_are_the_ones_given_in_the_order_given(self, settings: Settings) -> None:
        block = effective_of(settings, pairs=(("ETHUSDT", "5m"), ("BTCUSDT", "1m")))
        assert [pair["symbol"] for pair in block["pairs"]] == ["ETHUSDT", "BTCUSDT"]

    def test_the_arm_is_the_canonical_stop_slippage(self, settings: Settings) -> None:
        assert candidate_arm(effective_of(settings)) == "1.2"


class TestTheCandidateDigest:
    def test_it_is_a_sha256_and_is_stable(self, settings: Settings) -> None:
        digest = candidate_digest(effective_of(settings))
        assert len(digest) == 64 and set(digest) <= set("0123456789abcdef")
        assert digest == candidate_digest(effective_of(settings))

    def test_the_stop_slippage_arm_is_not_part_of_the_candidate(self, settings: Settings) -> None:
        a = effective_of(settings)
        b = copy.deepcopy(a)
        b["costs"]["stop_slippage_percent"] = "0.66"
        assert candidate_digest(a) == candidate_digest(b)
        assert settings_digest(a) != settings_digest(b)
        assert candidate_arm(a) == "1.2" and candidate_arm(b) == "0.66"

    @pytest.mark.parametrize(
        "change",
        [
            lambda e: e.__setitem__("config_sha256", "b" * 64),
            lambda e: e["strategy"].__setitem__("name", "rsi"),
            lambda e: e["strategy"]["params"].__setitem__("fast_period", "4"),
            lambda e: e["strategy"]["params"].__setitem__("trend_filter_period", "200"),
            lambda e: e["pairs"][0].__setitem__("timeframe", "4h"),
            lambda e: e["pairs"][0].__setitem__("symbol", "ETHUSDT"),
            lambda e: e["pairs"].append({"symbol": "ETHUSDT", "timeframe": "1h"}),
            lambda e: e["risk"].__setitem__("max_position_staleness_s", "20000"),
            lambda e: e.__setitem__("exchange_info_environment", "testnet"),
            lambda e: e["costs"].__setitem__("fee_percent", "0.075"),
            lambda e: e["costs"].__setitem__("slippage_percent", "0.1"),
            lambda e: e["costs"].__setitem__("initial_balance", "5000"),
        ],
        ids=[
            "config",
            "strategy",
            "param",
            "filter",
            "timeframe",
            "symbol",
            "extra-pair",
            "staleness",
            "environment",
            "fee",
            "slippage",
            "balance",
        ],
    )
    def test_every_other_effective_setting_moves_both_digests(
        self, settings: Settings, change: Any
    ) -> None:
        base = effective_of(settings)
        moved = copy.deepcopy(base)
        change(moved)
        assert candidate_digest(moved) != candidate_digest(base)
        assert settings_digest(moved) != settings_digest(base)

    def test_how_the_settings_were_reached_is_in_neither_digest(self, settings: Settings) -> None:
        a = effective_of(settings, overrides={})
        b = effective_of(settings, overrides={"params": {"fast_period": "3"}})
        assert a["overrides"] != b["overrides"]
        assert candidate_digest(a) == candidate_digest(b)
        assert settings_digest(a) == settings_digest(b)

    def test_a_grid_value_typed_as_30_or_30_point_0_is_one_candidate(
        self, settings: Settings
    ) -> None:
        a = effective_of(settings)
        b = copy.deepcopy(a)
        a["strategy"]["params"] = {"oversold": canonical_value(30)}
        b["strategy"]["params"] = {"oversold": canonical_value(30.0)}
        assert candidate_digest(a) == candidate_digest(b)

    def test_the_order_the_params_were_given_in_does_not_matter(self, settings: Settings) -> None:
        a = effective_of(settings)
        b = copy.deepcopy(a)
        a["strategy"]["params"] = {"a": "1", "b": "2"}
        b["strategy"]["params"] = {"b": "2", "a": "1"}
        assert candidate_digest(a) == candidate_digest(b)

    def test_a_block_missing_a_part_is_refused_and_the_part_is_named(
        self, settings: Settings
    ) -> None:
        block = effective_of(settings)
        for key in (
            "config_sha256",
            "strategy",
            "pairs",
            "risk",
            "exchange_info_environment",
            "costs",
        ):
            broken = {k: v for k, v in block.items() if k != key}
            with pytest.raises(EffectiveSettingsError, match=key):
                candidate_digest(broken)
            with pytest.raises(EffectiveSettingsError, match=key):
                settings_digest(broken)

    def test_an_incomplete_costs_block_is_refused(self, settings: Settings) -> None:
        block = effective_of(settings)
        del block["costs"]["fee_percent"]
        with pytest.raises(EffectiveSettingsError, match="no complete costs block"):
            candidate_digest(block)
        with pytest.raises(EffectiveSettingsError, match="no complete costs block"):
            candidate_arm(block)


class TestTheRecordCheck:
    def record(self, settings: Settings) -> dict[str, Any]:
        block = effective_of(settings)
        return {
            "effective": block,
            "candidate_digest": candidate_digest(block),
            "settings_digest": settings_digest(block),
        }

    def test_a_consistent_record_passes(self, settings: Settings) -> None:
        assert check_record_digests(self.record(settings)) is None

    def test_a_record_without_a_block_is_refused(self, settings: Settings) -> None:
        body = self.record(settings)
        del body["effective"]
        with pytest.raises(EffectiveSettingsError, match="no effective settings"):
            check_record_digests(body)

    @pytest.mark.parametrize("name", ["candidate_digest", "settings_digest"])
    def test_a_missing_or_foreign_digest_is_refused(self, settings: Settings, name: str) -> None:
        body = self.record(settings)
        del body[name]
        with pytest.raises(EffectiveSettingsError, match=f"no {name}"):
            check_record_digests(body)
        body[name] = "0" * 64
        with pytest.raises(EffectiveSettingsError, match=f"{name} is not the digest"):
            check_record_digests(body)
        body[name] = 5
        with pytest.raises(EffectiveSettingsError, match=f"no {name}"):
            check_record_digests(body)


class TestARealRunWritesTheBlock:
    async def run(self, tmp_path: Path, **kwargs: Any) -> Any:
        tmp_path.mkdir(parents=True, exist_ok=True)
        settings = build_world(tmp_path)
        return await run_backtest(
            settings, code_facts=lambda: {**CODE, "verdict": "accepted"}, **kwargs
        )

    async def test_the_record_carries_the_block_and_digests_that_check_out(
        self, tmp_path: Path
    ) -> None:
        result = await self.run(tmp_path)
        record = result.record
        assert record["effective"]["strategy"]["name"] == "sma_crossover"
        assert record["effective"]["pairs"] == [{"symbol": "BTCUSDT", "timeframe": "1h"}]
        assert record["effective"]["overrides"] == {}
        assert record["candidate_digest"] == candidate_digest(record["effective"])
        assert record["settings_digest"] == settings_digest(record["effective"])
        assert check_record_digests(record) is None

    async def test_the_overrides_the_command_gave_are_kept_for_the_reader(
        self, tmp_path: Path
    ) -> None:
        result = await self.run(tmp_path, overrides={"stop_slippage_percent": "0.66"})
        assert result.record["effective"]["overrides"] == {"stop_slippage_percent": "0.66"}

    async def test_the_block_agrees_with_the_older_blocks_of_the_same_record(
        self, tmp_path: Path
    ) -> None:
        """The older ``strategy`` and ``fill_parameters`` blocks and the new ``effective`` one are
        written from the same objects, and must say the same thing in their own forms."""
        record = (await self.run(tmp_path)).record
        assert record["effective"]["strategy"]["name"] == record["strategy"]["name"]
        for key in ("fee_percent", "slippage_percent", "stop_slippage_percent", "initial_balance"):
            assert Decimal(record["effective"]["costs"][key]) == Decimal(
                record["fill_parameters"][key]
            )
