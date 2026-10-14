"""R-BR: the command-line overrides of a backtest, parsed and applied with the config's own checks.

The ruling, verbatim: *"Backtests take --stop-slippage and strategy, timeframe and parameter overrides
on the command line."* Proved here: each flag's parser refuses what it should; each override changes
exactly what it names; ``--strategy`` drops the old strategy's parameters; ``--timeframe`` raises the
staleness bound the validator would otherwise refuse (``M5m-314``: the COMMITTED config is refused at
every timeframe above 1m without it); and an override the config's checks refuse is refused whole.
"""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
import yaml

from tests.unit.backtest_world import make_settings
from trading_bot.backtesting.overrides import (
    Overrides,
    apply_overrides,
    build_overrides,
    parse_param,
    parse_percent,
)
from trading_bot.config.models import AppConfig
from trading_bot.config.settings import Settings
from trading_bot.core.exceptions import ConfigError

REPO = Path(__file__).resolve().parents[2]


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return make_settings(tmp_path, tmp_path / "hist")


def committed_config() -> AppConfig:
    """The shipped ``config.yaml`` as the loader parses it, without the environment."""
    return AppConfig.model_validate(
        yaml.safe_load((REPO / "config.yaml").read_text(encoding="utf-8"))
    )


class TestPercent:
    @pytest.mark.parametrize(
        ("text", "expected"),
        [("0.66", "0.66"), (" 1.20 ", "1.20"), ("0", "0"), ("1e2", "1E+2"), ("0.05", "0.05")],
    )
    def test_it_is_read_exactly_as_a_decimal(self, text: str, expected: str) -> None:
        value = parse_percent(text)
        assert isinstance(value, Decimal)
        assert value == Decimal(expected)

    @pytest.mark.parametrize("text", ["-0.1", "abc", "", "nan", "inf", "-inf", "1,5"])
    def test_a_negative_or_non_finite_or_non_number_is_refused(self, text: str) -> None:
        with pytest.raises(ConfigError, match="--stop-slippage"):
            parse_percent(text)


class TestParam:
    @pytest.mark.parametrize(
        ("text", "key", "value"),
        [
            ("fast_period=20", "fast_period", 20),
            ("oversold=30.0", "oversold", 30.0),
            ("flag=true", "flag", True),
            ("flag=false", "flag", False),
            ("name=abc", "name", "abc"),
            ('name="abc"', "name", "abc"),
            ("trend_filter_period=200", "trend_filter_period", 200),
            ("x=a=b", "x", "a=b"),
        ],
    )
    def test_the_value_is_json_when_it_is_json_and_text_otherwise(
        self, text: str, key: str, value: object
    ) -> None:
        got_key, got_value = parse_param(text)
        assert got_key == key
        assert got_value == value
        assert type(got_value) is type(value)

    def test_an_integer_and_a_float_stay_what_they_were_typed_as(self) -> None:
        assert type(parse_param("a=20")[1]) is int
        assert type(parse_param("a=20.0")[1]) is float

    @pytest.mark.parametrize(
        "text", ["noequals", "=1", "1k=1", "a b=1", "a-b=1", "k=", "k=null", "k=[1]", 'k={"a":1}']
    )
    def test_a_malformed_param_is_refused(self, text: str) -> None:
        with pytest.raises(ConfigError, match="--param"):
            parse_param(text)


class TestBuild:
    def test_nothing_given_is_empty(self) -> None:
        assert build_overrides().is_empty
        assert Overrides().is_empty
        assert build_overrides(params=[]).is_empty
        assert build_overrides(params=None).is_empty

    @pytest.mark.parametrize(
        "kwargs",
        [
            {"stop_slippage": Decimal("0")},
            {"strategy": "rsi"},
            {"timeframe": "1h"},
            {"params": ["a=1"]},
        ],
    )
    def test_any_one_flag_makes_it_not_empty(self, kwargs: dict[str, Any]) -> None:
        assert not build_overrides(**kwargs).is_empty

    def test_a_zero_stop_slippage_is_an_override_and_not_an_absence(self) -> None:
        assert build_overrides(stop_slippage=Decimal("0")).record() == {
            "stop_slippage_percent": "0"
        }

    def test_a_param_given_twice_is_refused(self) -> None:
        with pytest.raises(ConfigError, match="--param fast_period is given twice"):
            build_overrides(params=["fast_period=1", "fast_period=2"])

    def test_the_record_holds_only_what_was_given_in_canonical_form(self) -> None:
        given = build_overrides(
            stop_slippage=Decimal("0.660"),
            strategy="rsi",
            timeframe="4h",
            params=["period=14", "oversold=30.0", "flag=true"],
        )
        assert given.record() == {
            "stop_slippage_percent": "0.66",
            "strategy": "rsi",
            "timeframe": "4h",
            "params": {"period": "14", "oversold": "30", "flag": True},
        }
        assert Overrides(timeframe="1h").record() == {"timeframe": "1h"}


class TestApply:
    def test_no_override_returns_the_very_config(self, settings: Settings) -> None:
        assert apply_overrides(settings.config, Overrides()) is settings.config

    def test_the_input_config_is_never_changed(self, settings: Settings) -> None:
        before = settings.config.model_dump()
        apply_overrides(settings.config, build_overrides(stop_slippage=Decimal("0.66")))
        assert settings.config.model_dump() == before

    def test_stop_slippage_replaces_only_the_arm(self, settings: Settings) -> None:
        got = apply_overrides(settings.config, build_overrides(stop_slippage=Decimal("0.66")))
        assert got.backtesting.stop_slippage_percent == Decimal("0.66")
        expected = settings.config.model_dump()
        expected["backtesting"]["stop_slippage_percent"] = Decimal("0.66")
        assert got.model_dump() == expected

    def test_a_param_is_laid_over_the_configured_ones(self, settings: Settings) -> None:
        got = apply_overrides(settings.config, build_overrides(params=["fast_period=4"]))
        assert got.strategy.name == "sma_crossover"
        assert got.strategy.params == {"fast_period": 4, "slow_period": 8}

    def test_a_new_strategy_drops_the_old_strategys_params(self, settings: Settings) -> None:
        got = apply_overrides(settings.config, build_overrides(strategy="rsi", params=["period=9"]))
        assert got.strategy.name == "rsi"
        assert got.strategy.params == {"period": 9}

    def test_a_new_strategy_with_no_params_takes_its_defaults(self, settings: Settings) -> None:
        got = apply_overrides(settings.config, build_overrides(strategy="rsi"))
        assert got.strategy.params == {}

    def test_an_unknown_strategy_is_refused_with_the_registrys_own_words(
        self, settings: Settings
    ) -> None:
        with pytest.raises(ConfigError, match="Unknown strategy 'nope'"):
            apply_overrides(settings.config, build_overrides(strategy="nope"))

    def test_an_unknown_param_is_refused_and_the_accepted_ones_are_listed(
        self, settings: Settings
    ) -> None:
        with pytest.raises(ConfigError, match="Accepted parameters: fast_period, slow_period"):
            apply_overrides(settings.config, build_overrides(params=["fast_perio=4"]))

    def test_a_value_the_strategy_refuses_is_refused(self, settings: Settings) -> None:
        with pytest.raises(ConfigError, match="cannot be built"):
            apply_overrides(settings.config, build_overrides(params=["fast_period=9"]))

    @pytest.mark.parametrize(
        ("flags", "key"),
        [
            (["fast_period=4.0"], "fast_period"),
            (["slow_period=8.5"], "slow_period"),
            (["fast_period=true"], "fast_period"),
        ],
    )
    def test_a_non_integer_for_an_integer_period_is_refused_and_named(
        self, settings: Settings, flags: list[str], key: str
    ) -> None:
        """``M5m-315``: ``fast_period=4.0`` builds and then raises ``TypeError`` on every bar."""
        with pytest.raises(ConfigError, match=f"{key} is an integer parameter"):
            apply_overrides(settings.config, build_overrides(params=flags))

    def test_text_for_an_integer_period_is_refused_by_the_constructor_itself(
        self, settings: Settings
    ) -> None:
        with pytest.raises(ConfigError, match="cannot be built"):
            apply_overrides(settings.config, build_overrides(params=["fast_period=3x"]))

    def test_a_float_for_a_float_threshold_and_an_integer_for_it_are_both_accepted(
        self, settings: Settings
    ) -> None:
        for flags in (["oversold=30"], ["oversold=30.0"], ["oversold=27.5"]):
            got = apply_overrides(settings.config, build_overrides(strategy="rsi", params=flags))
            assert got.strategy.name == "rsi"

    def test_the_old_strategys_params_are_not_silently_kept_for_a_new_name(
        self, settings: Settings
    ) -> None:
        """The configured ``fast_period`` and ``slow_period`` belong to ``sma_crossover``; laid over
        ``rsi`` they would be refused. They are dropped, so only the named ``--param`` remain."""
        got = apply_overrides(settings.config, build_overrides(strategy="rsi", params=["period=5"]))
        assert "fast_period" not in got.strategy.params

    def test_a_timeframe_is_set_on_every_pair(self, tmp_path: Path) -> None:
        both = make_settings(tmp_path, tmp_path / "h", pairs=(("BTCUSDT", "1m"), ("ETHUSDT", "5m")))
        got = apply_overrides(both.config, build_overrides(timeframe="1h"))
        assert [(p.symbol, p.timeframe) for p in got.trading.pairs] == [
            ("BTCUSDT", "1h"),
            ("ETHUSDT", "1h"),
        ]

    def test_an_unknown_timeframe_is_refused(self, settings: Settings) -> None:
        with pytest.raises(ConfigError, match="--timeframe '7x'"):
            apply_overrides(settings.config, build_overrides(timeframe="7x"))

    def test_the_staleness_bound_is_raised_to_what_the_validator_needs(
        self, tmp_path: Path
    ) -> None:
        both = make_settings(tmp_path, tmp_path / "h", pairs=(("BTCUSDT", "1h"), ("ETHUSDT", "1h")))
        got = apply_overrides(both.config, build_overrides(timeframe="4h"))
        assert got.risk.max_position_staleness_s == (3 + 1) * 14_400

    def test_a_bound_the_validator_accepts_is_left_as_committed(self, tmp_path: Path) -> None:
        """Raised only when the validator refuses: 10,800 s already covers two pairs at 1h, so the
        round value (3 + 1) x 3,600 = 14,400 is NOT applied."""
        both = make_settings(tmp_path, tmp_path / "h", pairs=(("BTCUSDT", "1m"), ("ETHUSDT", "5m")))
        got = apply_overrides(both.config, build_overrides(timeframe="1h"))
        assert got.risk.max_position_staleness_s == 10_800

    def test_the_staleness_bound_is_never_lowered(self, tmp_path: Path) -> None:
        both = make_settings(tmp_path, tmp_path / "h", pairs=(("BTCUSDT", "1h"),))
        assert both.config.risk.max_position_staleness_s == 10_800
        got = apply_overrides(both.config, build_overrides(timeframe="1m"))
        assert got.risk.max_position_staleness_s == 10_800


class TestTheCommittedConfigAtEveryTimeframe:
    """``M5m-314``: ``config.yaml``'s 180 s staleness bound is accepted only while the shortest
    timeframe is 1m. Without the raise a ``--timeframe`` override is refused by the validator."""

    @pytest.mark.parametrize("timeframe", ["5m", "1h", "4h", "1d"])
    def test_the_bare_config_is_refused_at_a_longer_timeframe(self, timeframe: str) -> None:
        data = committed_config().model_dump()
        for pair in data["trading"]["pairs"]:
            pair["timeframe"] = timeframe
        with pytest.raises(ValueError, match="max_position_staleness_s"):
            AppConfig.model_validate(data)

    @pytest.mark.parametrize(
        ("timeframe", "bound"),
        [("5m", 1_200), ("1h", 14_400), ("4h", 57_600), ("1d", 345_600)],
    )
    def test_the_override_makes_it_valid_with_the_round_value(
        self, timeframe: str, bound: int
    ) -> None:
        got = apply_overrides(committed_config(), build_overrides(timeframe=timeframe))
        assert got.risk.max_position_staleness_s == bound
        assert {p.timeframe for p in got.trading.pairs} == {timeframe}

    def test_one_minute_needs_no_raise(self) -> None:
        got = apply_overrides(committed_config(), build_overrides(timeframe="1m"))
        assert got.risk.max_position_staleness_s == 180

    def test_the_candidate_shape_of_the_protocol_builds_on_the_committed_config(self) -> None:
        """An rsi candidate at 4h with the filter parameter is exactly what S6 will ask for."""
        got = apply_overrides(
            committed_config(),
            build_overrides(
                strategy="rsi",
                timeframe="4h",
                stop_slippage=Decimal("0.66"),
                params=["period=14", "oversold=30", "overbought=70"],
            ),
        )
        assert got.strategy.name == "rsi"
        assert got.strategy.params == {"period": 14, "oversold": 30, "overbought": 70}
        assert got.backtesting.stop_slippage_percent == Decimal("0.66")


class TestSettingsWithConfig:
    def test_the_secrets_path_digest_and_mode_carry_over(self, settings: Settings) -> None:
        other = apply_overrides(settings.config, build_overrides(stop_slippage=Decimal("0.66")))
        moved = settings.with_config(other)
        assert moved is not settings
        assert moved.config is other
        assert moved.config_path == settings.config_path
        assert moved.config_sha256 == settings.config_sha256
        assert moved.mode is settings.mode
        assert moved._secrets is settings._secrets
