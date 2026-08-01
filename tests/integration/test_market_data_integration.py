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

        # The first live bar may be a *new* bar or a *re-delivery of the seed's
        # last bar*, and which one happens is a race with the minute boundary:
        # REST history can end on the very bar the WebSocket is about to close.
        # `_append` handles both -- it appends a new `open_time` and **replaces**
        # an equal one ("same bar re-delivered, possibly corrected"), which is
        # what makes a corrected bar safe after a reconnect. So the frame grows
        # by one on the append path and by zero on the replace path, and this
        # test asserts the invariant common to both rather than a fixed
        # increment. An earlier version asserted `len(seeded) + 1` and failed
        # intermittently for years' worth of runs against correct behaviour.
        extended = provider.get_dataframe("BTCUSDT", "1m")
        growth = len(extended) - len(seeded)
        assert growth in (0, 1), f"buffer grew by {growth}; only append or replace is legal"
        assert extended.index[-1] == live.open_time
        assert extended.index.is_monotonic_increasing
        assert extended.index.is_unique

        if growth == 0:
            # Replacement path. "Grew by 0" is also what a provider that silently
            # *dropped* the bar would produce, so prove the replacement actually
            # replaced: the final row must differ from the one seeding left, and
            # must equal the candle just delivered.
            assert extended.index[-1] == seeded.index[-1], "replaced a different bar"
            assert not extended.iloc[-1].equals(seeded.iloc[-1]), (
                "buffer length unchanged and the last row is identical -- the "
                "re-delivered bar was dropped rather than replacing the seeded one"
            )
            assert extended["close"].iloc[-1] == pytest.approx(float(live.close))
        else:
            # Append path: a genuinely new bar, beyond everything seeded.
            assert extended.index[-1] > seeded.index[-1]
            assert extended.iloc[:-1].equals(seeded), "appending disturbed the seeded rows"
    finally:
        await provider.stop()
