"""Shared pytest fixtures."""

from __future__ import annotations

from pathlib import Path

import pytest

# A minimal but valid config.yaml body used across tests.
_MINIMAL_CONFIG = """
mode: testnet
strategy:
  name: sma_crossover
  params:
    fast_period: 10
    slow_period: 30
backtesting:
  start_date: "2024-01-01"
  end_date: "2024-02-01"
  initial_balance: 5000
logging:
  console: false
  file:
    enabled: false
"""


@pytest.fixture
def config_path(tmp_path: Path) -> Path:
    """Write a minimal valid config.yaml to a temp dir and return its path."""
    path = tmp_path / "config.yaml"
    path.write_text(_MINIMAL_CONFIG, encoding="utf-8")
    return path


@pytest.fixture(autouse=True)
def _isolated_settings(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Give every test freshly-loaded settings in a clean environment.

    ``Secrets`` reads a relative ``.env`` file plus the process environment, so
    without isolation a developer's real ``.env`` (or shell exports) would leak
    into tests and make results machine-dependent. This fixture clears all
    secret-bearing variables and switches to a scratch directory so no stray
    ``.env`` is discovered. Tests that need specific values set them explicitly
    with ``monkeypatch.setenv``.
    """
    from trading_bot.config.settings import get_settings

    for var in (
        "BINANCE_API_KEY",
        "BINANCE_API_SECRET",
        "BINANCE_TESTNET_API_KEY",
        "BINANCE_TESTNET_API_SECRET",
        "TELEGRAM_BOT_TOKEN",
        "TELEGRAM_CHAT_ID",
        "BOT_MODE",
        "BOT_CONFIG_PATH",
    ):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.chdir(tmp_path)  # so a relative "./.env" is never read

    get_settings.cache_clear()
    yield
    get_settings.cache_clear()
