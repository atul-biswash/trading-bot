"""Opt-in integration test: the real Binance **testnet** kline WebSocket.

Skipped unless testnet credentials are present in the environment
(``BINANCE_TESTNET_API_KEY`` / ``BINANCE_TESTNET_API_SECRET``, or the primary
``BINANCE_API_KEY`` / ``BINANCE_API_SECRET`` as a fallback), so the default test
run stays hermetic and offline. Run it explicitly with::

    pytest -m integration

It connects to the testnet, subscribes to a 1-minute kline stream, and waits for
one **closed** candle. The mode is pinned to TESTNET here regardless of
configuration. A generous timeout is used because a 1m bar closes at most once
per minute.
"""

from __future__ import annotations

import asyncio
import os

import pytest

from trading_bot.config.settings import get_settings
from trading_bot.core.enums import TradingMode
from trading_bot.core.models import Candle
from trading_bot.exchange.websocket_client import BinanceMarketDataStream

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


async def test_testnet_ws_delivers_a_closed_candle(config_path: object) -> None:
    """Subscribe to a live testnet kline stream and receive one closed candle."""
    get_settings.cache_clear()
    settings = get_settings(str(config_path))
    settings.mode = TradingMode.TESTNET  # never connect to live from this test
    assert settings.mode is TradingMode.TESTNET

    received: asyncio.Queue[Candle] = asyncio.Queue()

    async def handler(candle: Candle) -> None:
        await received.put(candle)

    stream = await BinanceMarketDataStream.create(settings)
    stream.subscribe("BTCUSDT", "1m", handler)
    await stream.start()
    try:
        candle = await asyncio.wait_for(received.get(), timeout=120)
        assert isinstance(candle, Candle)
        assert candle.is_closed is True
        assert candle.symbol == "BTCUSDT"
        assert candle.timeframe == "1m"
        assert candle.close > 0
    finally:
        await stream.stop()
