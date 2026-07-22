"""Opt-in integration test against the real Binance **testnet**.

This test is skipped unless testnet credentials are present in the environment
(``BINANCE_TESTNET_API_KEY`` / ``BINANCE_TESTNET_API_SECRET``, or the primary
``BINANCE_API_KEY`` / ``BINANCE_API_SECRET`` as a fallback), so the default test
run stays hermetic and offline. Run it explicitly with::

    pytest -m integration

It only performs read-only calls (ping, balances, ticker) and never places an
order. The mode is pinned to TESTNET here regardless of configuration.
"""

from __future__ import annotations

import os

import pytest

from trading_bot.config.settings import get_settings
from trading_bot.core.enums import TradingMode
from trading_bot.core.models import Balance
from trading_bot.exchange import BinanceClient

_HAS_KEYS = bool(
    os.getenv("BINANCE_TESTNET_API_KEY") or os.getenv("BINANCE_API_KEY")
)

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        not _HAS_KEYS,
        reason="Set BINANCE_TESTNET_API_KEY/SECRET (or BINANCE_API_KEY/SECRET) "
        "to run testnet integration tests.",
    ),
]


async def test_testnet_read_only_roundtrip(config_path: object) -> None:
    """Ping the testnet, read balances, and fetch a live ticker."""
    get_settings.cache_clear()
    settings = get_settings(str(config_path))
    settings.mode = TradingMode.TESTNET  # never connect to live from this test
    assert settings.mode is TradingMode.TESTNET

    async with await BinanceClient.create(settings) as client:
        await client.ping()

        balances = await client.get_balances()
        assert isinstance(balances, list)
        assert all(isinstance(b, Balance) for b in balances)

        ticker = await client.get_ticker("BTCUSDT")
        assert ticker.last > 0
        assert ticker.bid > 0
        assert ticker.ask > 0
