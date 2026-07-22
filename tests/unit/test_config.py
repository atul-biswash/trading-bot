"""Tests for config loading, validation, and secret resolution."""

from __future__ import annotations

from pathlib import Path

import pytest

from trading_bot.config.settings import get_settings
from trading_bot.core.enums import TradingMode
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


def test_testnet_prefers_testnet_keys(
    config_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("BINANCE_API_KEY", "live_key")
    monkeypatch.setenv("BINANCE_API_SECRET", "live_secret")
    monkeypatch.setenv("BINANCE_TESTNET_API_KEY", "tn_key")
    monkeypatch.setenv("BINANCE_TESTNET_API_SECRET", "tn_secret")
    settings = get_settings(str(config_path))
    key, secret = settings.binance_credentials()
    assert key == "tn_key"
    assert secret == "tn_secret"


def test_live_mode_without_keys_raises(
    config_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
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
