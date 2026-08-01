"""Tests for config loading, validation, and secret resolution."""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest
from pydantic import ValidationError

from trading_bot.config.models import (
    PositionSizingConfig,
    RiskConfig,
    StopLossConfig,
    TakeProfitConfig,
    TrailingStopConfig,
)
from trading_bot.config.settings import get_settings
from trading_bot.core.enums import PositionSizingMethod, TakeProfitType, TradingMode
from trading_bot.core.exceptions import ConfigError


def test_loads_minimal_config(config_path: Path) -> None:
    settings = get_settings(str(config_path))
    assert settings.mode is TradingMode.TESTNET
    assert settings.config.strategy.name == "sma_crossover"
    assert settings.config.backtesting.initial_balance == 5000


def test_missing_config_file_raises() -> None:
    with pytest.raises(ConfigError):
        get_settings("does/not/exist.yaml")


def test_env_mode_override(config_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BOT_MODE", "paper")
    settings = get_settings(str(config_path))
    assert settings.mode is TradingMode.PAPER


def test_testnet_prefers_testnet_keys(config_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BINANCE_API_KEY", "live_key")
    monkeypatch.setenv("BINANCE_API_SECRET", "live_secret")
    monkeypatch.setenv("BINANCE_TESTNET_API_KEY", "tn_key")
    monkeypatch.setenv("BINANCE_TESTNET_API_SECRET", "tn_secret")
    settings = get_settings(str(config_path))
    key, secret = settings.binance_credentials()
    assert key == "tn_key"
    assert secret == "tn_secret"


def test_live_mode_without_keys_raises(config_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BOT_MODE", "live")
    monkeypatch.delenv("BINANCE_API_KEY", raising=False)
    monkeypatch.delenv("BINANCE_API_SECRET", raising=False)
    settings = get_settings(str(config_path))
    with pytest.raises(ConfigError):
        settings.binance_credentials()


def test_invalid_config_rejected(tmp_path: Path) -> None:
    bad = tmp_path / "config.yaml"
    # max_open_positions must be >= 1; unknown keys are also forbidden.
    bad.write_text(
        "mode: testnet\n"
        "strategy:\n  name: x\n"
        "backtesting:\n  start_date: '2024-01-01'\n  end_date: '2024-02-01'\n"
        "risk:\n  limits:\n    max_open_positions: 0\n",
        encoding="utf-8",
    )
    with pytest.raises(ConfigError):
        get_settings(str(bad))


class TestExitConfigDecimalBoundary:
    """The Phase 5 M2 exit-rule config fields convert ``float`` -> ``Decimal``
    exactly, once, here -- the same boundary already proven for position sizing.

    A YAML value such as ``1.005`` must become ``Decimal("1.005")``, not the
    binary expansion ``Decimal(1.005)`` gives, because these fields are later
    multiplied by money and ``Decimal * float`` raises ``TypeError``.
    """

    def test_stop_loss_fields_are_exact_decimals(self) -> None:
        # 1.005 is *not* exactly representable in binary, so it exposes the leak.
        from_yaml = 1.005  # what yaml.safe_load hands pydantic
        cfg = StopLossConfig(percent=2.0, atr_multiplier=from_yaml)
        assert cfg.percent == Decimal("2.0")
        assert cfg.atr_multiplier == Decimal("1.005")
        assert isinstance(cfg.percent, Decimal)
        assert isinstance(cfg.atr_multiplier, Decimal)
        assert cfg.atr_multiplier != Decimal(from_yaml)  # the binary-float leak avoided
        assert isinstance(cfg.atr_period, int)  # a lookback, deliberately not Decimal

    def test_take_profit_fields_are_exact_decimals(self) -> None:
        cfg = TakeProfitConfig(percent=4.0, rr_multiple=1.5)
        assert cfg.percent == Decimal("4.0")
        assert cfg.rr_multiple == Decimal("1.5")
        assert isinstance(cfg.percent, Decimal)
        assert isinstance(cfg.rr_multiple, Decimal)

    def test_trailing_stop_fields_are_exact_decimals(self) -> None:
        cfg = TrailingStopConfig(activation_percent=1.0, trail_percent=0.75)
        assert cfg.activation_percent == Decimal("1.0")
        assert cfg.trail_percent == Decimal("0.75")
        assert isinstance(cfg.activation_percent, Decimal)
        assert isinstance(cfg.trail_percent, Decimal)

    def test_positivity_constraints_survive_the_type_change(self) -> None:
        for bad in (0, -0.1):
            with pytest.raises(ValueError, match="percent"):
                StopLossConfig(percent=bad)
            with pytest.raises(ValueError, match="rr_multiple"):
                TakeProfitConfig(rr_multiple=bad)
            with pytest.raises(ValueError, match="trail_percent"):
                TrailingStopConfig(trail_percent=bad)


class TestRiskConfigCoherence:
    """A stop distance that a disabled stop-loss never produces is rejected at
    load, not hours later on the first signal."""

    def test_defaults_are_coherent(self) -> None:
        RiskConfig()  # stop enabled, take-profit percent, fixed_fraction sizing

    def test_rr_take_profit_without_a_stop_is_rejected(self) -> None:
        with pytest.raises(ValueError, match="take_profit"):
            RiskConfig(
                stop_loss=StopLossConfig(enabled=False),
                take_profit=TakeProfitConfig(type=TakeProfitType.RR),
            )

    def test_risk_per_trade_sizing_without_a_stop_is_rejected(self) -> None:
        with pytest.raises(ValueError, match="risk_per_trade"):
            RiskConfig(
                stop_loss=StopLossConfig(enabled=False),
                position_sizing=PositionSizingConfig(method=PositionSizingMethod.RISK_PER_TRADE),
            )

    def test_rr_take_profit_with_a_stop_is_allowed(self) -> None:
        RiskConfig(
            stop_loss=StopLossConfig(enabled=True),
            take_profit=TakeProfitConfig(type=TakeProfitType.RR),
        )

    def test_percent_take_profit_without_a_stop_is_allowed(self) -> None:
        """A percent target needs no stop distance, so disabling the stop is fine."""
        RiskConfig(
            stop_loss=StopLossConfig(enabled=False),
            take_profit=TakeProfitConfig(type=TakeProfitType.PERCENT),
        )


# --------------------------------------------------------------------------
# Assignment guard: config is loaded once and never mutated
# --------------------------------------------------------------------------
class TestConfigIsImmutableInPractice:
    """``validate_assignment`` turns "config is never mutated after load" from a
    convention into an enforced property.

    That convention is load-bearing: it is the reason a ``Decimal`` config field
    is safe despite the models being mutable. A float written into one would flow
    into ``move_pct < config.activation_percent`` and decide a trailing stop
    *without raising*, because ``Decimal < float`` compares silently.
    """

    def test_a_float_assigned_to_a_decimal_field_is_coerced_by_shortest_repr(self) -> None:
        """Config fields are plain ``Decimal``, **not** ``Money``, so assignment
        coerces rather than rejecting -- and it coerces the safe way.

        ``0.1`` becomes ``Decimal("0.1")``, not the binary expansion
        ``Decimal(0.1)`` would give. Without ``validate_assignment`` the float
        would simply be stored as a ``float``, and then
        ``move_pct < config.activation_percent`` would compare against
        ``0.1000000000000000055…`` silently, because ``Decimal < float`` does not
        raise. The guard is what converts it at the boundary instead.
        """
        config = TrailingStopConfig()
        config.activation_percent = 0.1  # type: ignore[assignment]

        # Bound to a name rather than written inline: `Decimal(<float literal>)`
        # is the anti-pattern this project forbids outright (ruff RUF032), and it
        # appears here only as the value being asserted *against*.
        naive = 0.1
        assert isinstance(config.activation_percent, Decimal)
        assert config.activation_percent == Decimal("0.1")
        assert config.activation_percent != Decimal(naive)  # the binary expansion
        assert format(config.activation_percent, ".30f") == "0.100000000000000000000000000000"

    def test_a_valid_decimal_assignment_is_kept_exact(self) -> None:
        config = TrailingStopConfig()
        config.activation_percent = Decimal("2.50")
        assert config.activation_percent == Decimal("2.50")
        assert str(config.activation_percent) == "2.50"  # exponent preserved

    def test_an_out_of_range_assignment_is_rejected(self) -> None:
        """Field constraints apply on assignment too, not only at construction.
        Without the guard, ``gt=0`` holds at load and never again."""
        config = TrailingStopConfig()
        with pytest.raises(ValidationError):
            config.activation_percent = Decimal("-1")

    def test_a_typo_on_assignment_is_rejected(self) -> None:
        """``extra="forbid"`` catches a misspelled key in ``config.yaml``; this
        catches the same typo made in code against a loaded config."""
        config = TrailingStopConfig()
        with pytest.raises(ValidationError, match="has no attribute"):
            config.activaton_percent = Decimal("1")  # type: ignore[attr-defined]
