"""Opt-in integration test: the market-data provider against Binance **testnet**.

Skipped unless testnet credentials are present in the environment
(``BINANCE_TESTNET_API_KEY`` / ``BINANCE_TESTNET_API_SECRET``, or the primary
``BINANCE_API_KEY`` / ``BINANCE_API_SECRET`` as a fallback), so the default test
run stays hermetic and offline. Run it explicitly with::

    pytest -m integration

It seeds real history over REST, then waits for one live candle to arrive on the
WebSocket and extend the frame. The mode is pinned to TESTNET regardless of
configuration. A generous timeout is used because a 1-minute bar closes at most
once per minute.
"""

from __future__ import annotations

import asyncio

import pandas as pd
import pytest

from tests.integration.credentials import HAS_CREDENTIALS, SKIP_REASON
from trading_bot.config.settings import get_settings
from trading_bot.core.enums import TradingMode
from trading_bot.core.models import Candle
from trading_bot.data.market_data import BufferedMarketDataProvider

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        not HAS_CREDENTIALS,
        reason=SKIP_REASON,
    ),
]

_HISTORY_LIMIT = 120


async def test_testnet_provider_seeds_history_and_extends_it_live(
    config_path: object,
) -> None:
    """Seed real testnet history, then grow it with one live closed candle."""
    get_settings.cache_clear()
    settings = get_settings(str(config_path))
    settings.mode = TradingMode.TESTNET  # never connect to live from this test
    assert settings.mode is TradingMode.TESTNET
    settings.config.data.history_limit = _HISTORY_LIMIT
    settings.config.data.buffer_size = max(settings.config.data.buffer_size, _HISTORY_LIMIT)

    arrived: asyncio.Queue[Candle] = asyncio.Queue()

    async def on_candle(candle: Candle) -> None:
        await arrived.put(candle)

    provider = await BufferedMarketDataProvider.create(settings)
    provider.track("BTCUSDT", "1m")
    provider.on_candle(on_candle)
    await provider.start()
    try:
        # --- seeded history -------------------------------------------------
        seeded = provider.get_dataframe("BTCUSDT", "1m")
        assert not seeded.empty
        assert len(seeded) <= _HISTORY_LIMIT
        assert list(seeded.columns) == ["open", "high", "low", "close", "volume"]
        assert isinstance(seeded.index, pd.DatetimeIndex)
        assert str(seeded.index.tz) == "UTC"
        assert seeded.index.is_monotonic_increasing
        assert seeded.index.is_unique
        assert (seeded["high"] >= seeded["low"]).all()
        assert provider.is_ready("BTCUSDT", "1m", 50)

        # Money keeps full precision behind the float frame.
        last = provider.last_candle("BTCUSDT", "1m")
        assert last is not None
        assert last.is_closed is True
        assert last.close > 0

        # --- one live candle ------------------------------------------------
        live = await asyncio.wait_for(arrived.get(), timeout=150)
        assert live.symbol == "BTCUSDT"
        assert live.timeframe == "1m"
        assert live.is_closed is True

        extended = provider.get_dataframe("BTCUSDT", "1m")
        assert len(extended) == len(seeded) + 1
        assert extended.index[-1] == live.open_time
        assert extended.index.is_monotonic_increasing
    finally:
        await provider.stop()
