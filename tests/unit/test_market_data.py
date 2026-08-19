"""Tests for :class:`BufferedMarketDataProvider` using scripted fakes.

No network and no real time. The REST client is a ``FakeExchangeClient`` with
scripted ``get_klines`` responses, and the stream is a ``FakeMarketDataStream``
that hands the test the handler the provider registered, so live candles are
delivered by calling it directly.

Candles are built by running **recorded Binance payloads** through the real
mappers (``to_candle`` for REST, ``ws_kline_to_candle`` for the socket) rather
than constructed by hand, so the fixtures exercise the same Decimal parsing the
production path uses.
"""

from __future__ import annotations

import logging
from decimal import Decimal
from typing import Any

import numpy as np
import pandas as pd
import pytest

from trading_bot.config.models import DataConfig
from trading_bot.core.exceptions import DataError
from trading_bot.core.interfaces import CandleHandler, ExchangeClient, MarketDataStream
from trading_bot.core.models import (
    Balance,
    Candle,
    Order,
    OrderRequest,
    SymbolInfo,
    Ticker,
)
from trading_bot.data.market_data import BufferedMarketDataProvider
from trading_bot.exchange.models import to_candle, ws_kline_to_candle

# --------------------------------------------------------------------------
# Recorded payloads
# --------------------------------------------------------------------------
_MINUTE_MS = 60_000
_BASE_OPEN_MS = 1_700_000_000_000  # 2023-11-14T22:13:20Z, a 1m bar boundary

# Values with more precision than float64 can hold, so the Decimal->float
# boundary is measurable rather than assumed.
_OPEN = "65000.12345678"
_CLOSE = "65050.87654321"


def _rest_kline(index: int, *, close: str = _CLOSE) -> list[Any]:
    """One Binance REST kline array (index layout: t,o,h,l,c,v,T)."""
    open_ms = _BASE_OPEN_MS + index * _MINUTE_MS
    return [
        open_ms,
        _OPEN,
        "65100.10000000",
        "64900.90000000",
        close,
        "12.50000000",
        open_ms + _MINUTE_MS - 1,
    ]


def _ws_kline_event(
    index: int,
    *,
    close: str = _CLOSE,
    is_closed: bool = True,
    symbol: str = "BTCUSDT",
    interval: str = "1m",
) -> dict[str, Any]:
    """One Binance WebSocket kline event (single-letter codes; ``x`` is finality)."""
    open_ms = _BASE_OPEN_MS + index * _MINUTE_MS
    return {
        "e": "kline",
        "E": open_ms + _MINUTE_MS,
        "s": symbol,
        "k": {
            "t": open_ms,
            "T": open_ms + _MINUTE_MS - 1,
            "s": symbol,
            "i": interval,
            "o": _OPEN,
            "c": close,
            "h": "65100.10000000",
            "l": "64900.90000000",
            "v": "12.50000000",
            "n": 100,
            "x": is_closed,
        },
    }


def rest_candle(
    index: int, *, close: str = _CLOSE, symbol: str = "BTCUSDT", timeframe: str = "1m"
) -> Candle:
    return to_candle(_rest_kline(index, close=close), symbol=symbol, timeframe=timeframe)


def ws_candle(index: int, **kwargs: Any) -> Candle:
    return ws_kline_to_candle(_ws_kline_event(index, **kwargs))


# --------------------------------------------------------------------------
# Scripted fakes
# --------------------------------------------------------------------------
class FakeExchangeClient(ExchangeClient):
    """Serves scripted kline history and records how it was called."""

    def __init__(
        self,
        history: dict[tuple[str, str], list[Candle]] | None = None,
        journal: list[str] | None = None,
    ) -> None:
        self._history = history or {}
        self._journal = journal if journal is not None else []
        self.kline_calls: list[tuple[str, str, int]] = []
        self.close_calls = 0

    async def get_klines(self, symbol: str, timeframe: str, *, limit: int = 500) -> list[Candle]:
        self.kline_calls.append((symbol, timeframe, limit))
        self._journal.append(f"seed:{symbol}/{timeframe}")
        return list(self._history.get((symbol, timeframe), []))

    async def close(self) -> None:
        self.close_calls += 1
        self._journal.append("close_client")

    # Unused by the provider; present to satisfy the port.
    async def get_balances(self) -> list[Balance]:  # pragma: no cover - not exercised
        raise NotImplementedError

    async def get_symbol_info(self, symbol: str) -> SymbolInfo:  # pragma: no cover
        raise NotImplementedError

    async def get_ticker(self, symbol: str) -> Ticker:  # pragma: no cover
        raise NotImplementedError

    async def create_order(self, request: OrderRequest) -> Order:  # pragma: no cover
        raise NotImplementedError

    async def cancel_order(self, symbol: str, order_id: str) -> Order:  # pragma: no cover
        raise NotImplementedError

    async def get_open_orders(self, symbol: str | None = None) -> list[Order]:  # pragma: no cover
        raise NotImplementedError

    async def get_own_open_orders(  # pragma: no cover
        self,
        symbol: str,
        *,
        timeout_s: float | None = None,
        attempts: int | None = None,
    ) -> list[Order]:
        raise NotImplementedError


class FakeMarketDataStream(MarketDataStream):
    """Captures subscriptions so the test can drive handlers directly."""

    def __init__(self, journal: list[str] | None = None) -> None:
        self._journal = journal if journal is not None else []
        self.handlers: dict[tuple[str, str], CandleHandler] = {}
        self.subscriptions: list[tuple[str, str]] = []
        self.start_calls = 0
        self.stop_calls = 0

    def subscribe(self, symbol: str, timeframe: str, handler: CandleHandler) -> None:
        self.subscriptions.append((symbol, timeframe))
        self.handlers[(symbol, timeframe)] = handler
        self._journal.append(f"subscribe:{symbol}/{timeframe}")

    async def start(self) -> None:
        self.start_calls += 1
        self._journal.append("stream_start")

    async def stop(self) -> None:
        self.stop_calls += 1
        self._journal.append("stream_stop")

    async def emit(self, symbol: str, timeframe: str, candle: Candle) -> None:
        """Deliver ``candle`` as if it arrived on the wire."""
        await self.handlers[(symbol, timeframe)](candle)


def build_provider(
    history: dict[tuple[str, str], list[Candle]] | None = None,
    *,
    pairs: tuple[tuple[str, str], ...] = (("BTCUSDT", "1m"),),
    history_limit: int = 500,
    buffer_size: int = 1000,
    owns_client: bool = False,
    journal: list[str] | None = None,
) -> tuple[BufferedMarketDataProvider, FakeExchangeClient, FakeMarketDataStream]:
    """Assemble a provider over fakes. ``journal`` records the call order."""
    client = FakeExchangeClient(history, journal)
    stream = FakeMarketDataStream(journal)
    provider = BufferedMarketDataProvider(
        client,
        stream,
        history_limit=history_limit,
        buffer_size=buffer_size,
        owns_client=owns_client,
    )
    for symbol, timeframe in pairs:
        provider.track(symbol, timeframe)
    return provider, client, stream


# --------------------------------------------------------------------------
# Construction & configuration
# --------------------------------------------------------------------------
def test_rejects_buffer_smaller_than_history() -> None:
    with pytest.raises(ValueError, match="buffer_size"):
        BufferedMarketDataProvider(
            FakeExchangeClient(), FakeMarketDataStream(), history_limit=500, buffer_size=100
        )


def test_rejects_non_positive_history_limit() -> None:
    with pytest.raises(ValueError, match="history_limit"):
        BufferedMarketDataProvider(
            FakeExchangeClient(), FakeMarketDataStream(), history_limit=0, buffer_size=100
        )


def test_data_config_defaults() -> None:
    config = DataConfig()
    assert config.history_limit == 500
    assert config.buffer_size == 1000


def test_data_config_rejects_history_above_binance_cap() -> None:
    with pytest.raises(ValueError):
        DataConfig(history_limit=1001)


def test_data_config_rejects_buffer_below_history() -> None:
    with pytest.raises(ValueError, match="buffer_size"):
        DataConfig(history_limit=800, buffer_size=500)


def test_app_config_parses_data_block(tmp_path: Any) -> None:
    from trading_bot.config.settings import get_settings

    path = tmp_path / "config.yaml"
    path.write_text(
        "mode: testnet\n"
        "data:\n  history_limit: 300\n  buffer_size: 750\n"
        "strategy:\n  name: sma_crossover\n"
        "backtesting:\n  start_date: '2024-01-01'\n  end_date: '2024-02-01'\n",
        encoding="utf-8",
    )
    settings = get_settings(str(path))
    assert settings.config.data.history_limit == 300
    assert settings.config.data.buffer_size == 750


def test_app_config_data_block_is_optional(config_path: Any) -> None:
    """A config.yaml predating this milestone still loads, with defaults."""
    from trading_bot.config.settings import get_settings

    settings = get_settings(str(config_path))
    assert settings.config.data.history_limit == 500


# --------------------------------------------------------------------------
# Seeding
# --------------------------------------------------------------------------
async def test_start_seeds_history_with_configured_limit() -> None:
    history = {("BTCUSDT", "1m"): [rest_candle(i) for i in range(5)]}
    provider, client, _ = build_provider(history, history_limit=250, buffer_size=250)

    await provider.start()

    assert client.kline_calls == [("BTCUSDT", "1m", 250)]
    assert provider.candle_count("BTCUSDT", "1m") == 5


async def test_start_seeds_every_tracked_pair() -> None:
    history = {
        ("BTCUSDT", "1m"): [rest_candle(i) for i in range(3)],
        ("ETHUSDT", "5m"): [rest_candle(i, symbol="ETHUSDT", timeframe="5m") for i in range(2)],
    }
    provider, client, stream = build_provider(history, pairs=(("BTCUSDT", "1m"), ("ETHUSDT", "5m")))

    await provider.start()

    assert {call[:2] for call in client.kline_calls} == {("BTCUSDT", "1m"), ("ETHUSDT", "5m")}
    assert provider.candle_count("BTCUSDT", "1m") == 3
    assert provider.candle_count("ETHUSDT", "5m") == 2
    assert set(stream.subscriptions) == {("BTCUSDT", "1m"), ("ETHUSDT", "5m")}


async def test_seeding_drops_a_still_forming_final_candle() -> None:
    """REST history can end on an open bar; a strategy must not see it as final."""
    closed = [rest_candle(i) for i in range(3)]
    forming = rest_candle(3).model_copy(update={"is_closed": False})
    provider, _, _ = build_provider({("BTCUSDT", "1m"): [*closed, forming]})

    await provider.start()

    assert provider.candle_count("BTCUSDT", "1m") == 3
    last = provider.last_candle("BTCUSDT", "1m")
    assert last is not None
    assert last.open_time == closed[-1].open_time


async def test_seeding_does_not_warn_about_a_forming_final_candle(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """The routine case must stay quiet, or startup cries wolf on every run."""
    closed = [rest_candle(i) for i in range(3)]
    forming = rest_candle(3).model_copy(update={"is_closed": False})
    provider, _, _ = build_provider({("BTCUSDT", "1m"): [*closed, forming]})

    with caplog.at_level(logging.WARNING):
        await provider.start()

    assert caplog.records == []


async def test_seeding_warns_about_genuinely_out_of_order_history(
    caplog: pytest.LogCaptureFixture,
) -> None:
    scrambled = [rest_candle(0), rest_candle(5), rest_candle(2)]
    provider, _, _ = build_provider({("BTCUSDT", "1m"): scrambled})

    with caplog.at_level(logging.WARNING):
        await provider.start()

    assert "dropped 1 out-of-order candle" in caplog.text


async def test_seeding_drops_out_of_order_history() -> None:
    scrambled = [rest_candle(0), rest_candle(5), rest_candle(2)]
    provider, _, _ = build_provider({("BTCUSDT", "1m"): scrambled})

    await provider.start()

    assert provider.candle_count("BTCUSDT", "1m") == 2
    frame = provider.get_dataframe("BTCUSDT", "1m")
    assert frame.index.is_monotonic_increasing


async def test_start_seeds_then_subscribes_then_goes_live() -> None:
    """No live candle can race ahead of the history it belongs after.

    Every pair must be seeded before *any* subscription exists, and the stream
    must only go live once all handlers are wired.
    """
    journal: list[str] = []
    provider, _, _ = build_provider(
        {
            ("BTCUSDT", "1m"): [rest_candle(i) for i in range(3)],
            ("ETHUSDT", "5m"): [rest_candle(0, symbol="ETHUSDT", timeframe="5m")],
        },
        pairs=(("BTCUSDT", "1m"), ("ETHUSDT", "5m")),
        journal=journal,
    )

    await provider.start()

    assert journal == [
        "seed:BTCUSDT/1m",
        "seed:ETHUSDT/5m",
        "subscribe:BTCUSDT/1m",
        "subscribe:ETHUSDT/5m",
        "stream_start",
    ]


async def test_start_is_idempotent() -> None:
    provider, client, stream = build_provider({("BTCUSDT", "1m"): [rest_candle(0)]})

    await provider.start()
    await provider.start()

    assert len(client.kline_calls) == 1
    assert stream.start_calls == 1


async def test_start_without_tracked_pairs_raises() -> None:
    provider = BufferedMarketDataProvider(FakeExchangeClient(), FakeMarketDataStream())
    with pytest.raises(ValueError, match="no tracked pairs"):
        await provider.start()


async def test_track_after_start_raises() -> None:
    provider, _, _ = build_provider({("BTCUSDT", "1m"): [rest_candle(0)]})
    await provider.start()
    with pytest.raises(RuntimeError, match="before start"):
        provider.track("ETHUSDT", "1m")


# --------------------------------------------------------------------------
# Live appends, ordering and eviction
# --------------------------------------------------------------------------
async def test_live_closed_candle_is_appended() -> None:
    provider, _, stream = build_provider({("BTCUSDT", "1m"): [rest_candle(0)]})
    await provider.start()

    await stream.emit("BTCUSDT", "1m", ws_candle(1))

    assert provider.candle_count("BTCUSDT", "1m") == 2
    last = provider.last_candle("BTCUSDT", "1m")
    assert last is not None
    assert last.open_time == ws_candle(1).open_time


async def test_forming_candle_is_ignored() -> None:
    provider, _, stream = build_provider({("BTCUSDT", "1m"): [rest_candle(0)]})
    await provider.start()

    await stream.emit("BTCUSDT", "1m", ws_candle(1, is_closed=False))

    assert provider.candle_count("BTCUSDT", "1m") == 1


async def test_duplicate_open_time_replaces_in_place() -> None:
    """A re-delivered bar corrects the existing one instead of duplicating it."""
    provider, _, stream = build_provider({("BTCUSDT", "1m"): [rest_candle(0), rest_candle(1)]})
    await provider.start()

    await stream.emit("BTCUSDT", "1m", ws_candle(1, close="66000.00000000"))

    assert provider.candle_count("BTCUSDT", "1m") == 2
    last = provider.last_candle("BTCUSDT", "1m")
    assert last is not None
    assert last.close == Decimal("66000.00000000")


async def test_stale_candle_is_dropped() -> None:
    """Binance replays recent bars after a reconnect; older bars must not rewind."""
    provider, _, stream = build_provider(
        {("BTCUSDT", "1m"): [rest_candle(0), rest_candle(1), rest_candle(2)]}
    )
    await provider.start()

    await stream.emit("BTCUSDT", "1m", ws_candle(1, close="99999.00000000"))

    assert provider.candle_count("BTCUSDT", "1m") == 3
    last = provider.last_candle("BTCUSDT", "1m")
    assert last is not None
    assert last.open_time == rest_candle(2).open_time
    assert last.close == Decimal(_CLOSE)


async def test_buffer_evicts_oldest_at_capacity() -> None:
    provider, _, stream = build_provider(
        {("BTCUSDT", "1m"): [rest_candle(i) for i in range(3)]},
        history_limit=3,
        buffer_size=3,
    )
    await provider.start()

    await stream.emit("BTCUSDT", "1m", ws_candle(3))

    assert provider.candle_count("BTCUSDT", "1m") == 3
    frame = provider.get_dataframe("BTCUSDT", "1m")
    assert frame.index[0] == rest_candle(1).open_time
    assert frame.index[-1] == ws_candle(3).open_time


async def test_symbol_case_is_normalised() -> None:
    provider, _, _ = build_provider({("BTCUSDT", "1m"): [rest_candle(0)]}, pairs=())
    provider.track("btcusdt", "1m")
    await provider.start()

    assert provider.candle_count("btcusdt", "1m") == 1
    assert provider.candle_count("BTCUSDT", "1m") == 1


# --------------------------------------------------------------------------
# DataFrame contract
# --------------------------------------------------------------------------
async def test_dataframe_shape_dtypes_and_index() -> None:
    provider, _, _ = build_provider({("BTCUSDT", "1m"): [rest_candle(i) for i in range(4)]})
    await provider.start()

    frame = provider.get_dataframe("BTCUSDT", "1m")

    assert list(frame.columns) == ["open", "high", "low", "close", "volume"]
    assert len(frame) == 4
    assert all(dtype == np.float64 for dtype in frame.dtypes)
    assert isinstance(frame.index, pd.DatetimeIndex)
    assert frame.index.name == "open_time"
    assert str(frame.index.tz) == "UTC"
    assert frame.index.is_monotonic_increasing


async def test_empty_dataframe_still_honours_the_contract() -> None:
    """A tracked pair with no candles yet is valid, and must be typed the same."""
    provider, _, _ = build_provider({("BTCUSDT", "1m"): []})
    await provider.start()

    frame = provider.get_dataframe("BTCUSDT", "1m")

    assert len(frame) == 0
    assert list(frame.columns) == ["open", "high", "low", "close", "volume"]
    assert all(dtype == np.float64 for dtype in frame.dtypes)
    assert isinstance(frame.index, pd.DatetimeIndex)
    assert str(frame.index.tz) == "UTC"


async def test_decimal_to_float_conversion_is_exact_at_the_boundary() -> None:
    provider, _, _ = build_provider({("BTCUSDT", "1m"): [rest_candle(0)]})
    await provider.start()

    frame = provider.get_dataframe("BTCUSDT", "1m")

    assert frame["open"].iloc[0] == float(Decimal(_OPEN))
    assert frame["close"].iloc[0] == float(Decimal(_CLOSE))
    # ...and the buffer kept the precision the float lost.
    last = provider.last_candle("BTCUSDT", "1m")
    assert last is not None
    assert last.open == Decimal(_OPEN)


async def test_dataframe_is_a_copy_per_call() -> None:
    """A strategy adding an indicator column must not corrupt other consumers."""
    provider, _, _ = build_provider({("BTCUSDT", "1m"): [rest_candle(i) for i in range(3)]})
    await provider.start()

    first = provider.get_dataframe("BTCUSDT", "1m")
    first["sma"] = 1.0
    first.iloc[0, 0] = -1.0

    second = provider.get_dataframe("BTCUSDT", "1m")
    assert "sma" not in second.columns
    assert second["open"].iloc[0] == float(Decimal(_OPEN))


async def test_dataframe_refreshes_after_a_new_candle() -> None:
    """The memoised frame must be invalidated by an append, not served stale."""
    provider, _, stream = build_provider({("BTCUSDT", "1m"): [rest_candle(0)]})
    await provider.start()

    assert len(provider.get_dataframe("BTCUSDT", "1m")) == 1
    await stream.emit("BTCUSDT", "1m", ws_candle(1))
    assert len(provider.get_dataframe("BTCUSDT", "1m")) == 2


async def test_dataframe_refreshes_after_an_in_place_correction() -> None:
    provider, _, stream = build_provider({("BTCUSDT", "1m"): [rest_candle(0)]})
    await provider.start()

    provider.get_dataframe("BTCUSDT", "1m")  # populate the memo
    await stream.emit("BTCUSDT", "1m", ws_candle(0, close="66000.00000000"))

    frame = provider.get_dataframe("BTCUSDT", "1m")
    assert frame["close"].iloc[-1] == 66000.0


def test_untracked_pair_raises_data_error() -> None:
    provider, _, _ = build_provider({("BTCUSDT", "1m"): []})
    with pytest.raises(DataError, match="not tracked"):
        provider.get_dataframe("DOGEUSDT", "1m")


# --------------------------------------------------------------------------
# Readiness
# --------------------------------------------------------------------------
async def test_is_ready_tracks_warmup_period() -> None:
    provider, _, stream = build_provider({("BTCUSDT", "1m"): [rest_candle(i) for i in range(3)]})
    await provider.start()

    assert provider.is_ready("BTCUSDT", "1m", 3) is True
    assert provider.is_ready("BTCUSDT", "1m", 4) is False

    await stream.emit("BTCUSDT", "1m", ws_candle(3))
    assert provider.is_ready("BTCUSDT", "1m", 4) is True


async def test_is_ready_is_false_for_an_empty_buffer() -> None:
    """A zero warmup must still require at least one candle."""
    provider, _, _ = build_provider({("BTCUSDT", "1m"): []})
    await provider.start()

    assert provider.candle_count("BTCUSDT", "1m") == 0
    assert provider.is_ready("BTCUSDT", "1m", 0) is False


async def test_last_candle_is_none_when_empty() -> None:
    provider, _, _ = build_provider({("BTCUSDT", "1m"): []})
    await provider.start()
    assert provider.last_candle("BTCUSDT", "1m") is None


# --------------------------------------------------------------------------
# Candle hook
# --------------------------------------------------------------------------
async def test_on_candle_fires_for_accepted_candles_only() -> None:
    provider, _, stream = build_provider({("BTCUSDT", "1m"): [rest_candle(0)]})
    seen: list[Candle] = []

    async def record(candle: Candle) -> None:
        seen.append(candle)

    provider.on_candle(record)
    await provider.start()

    await stream.emit("BTCUSDT", "1m", ws_candle(1))
    await stream.emit("BTCUSDT", "1m", ws_candle(1, is_closed=False))  # forming
    await stream.emit("BTCUSDT", "1m", ws_candle(0))  # stale

    assert len(seen) == 1
    assert seen[0].open_time == ws_candle(1).open_time


async def test_seeding_does_not_fire_the_candle_hook() -> None:
    """Seeding is history, not news; the engine should not trade 500 old bars."""
    provider, _, _ = build_provider({("BTCUSDT", "1m"): [rest_candle(i) for i in range(5)]})
    seen: list[Candle] = []

    async def record(candle: Candle) -> None:
        seen.append(candle)

    provider.on_candle(record)
    await provider.start()

    assert seen == []


async def test_failing_hook_does_not_break_the_feed() -> None:
    provider, _, stream = build_provider({("BTCUSDT", "1m"): [rest_candle(0)]})
    survivors: list[Candle] = []

    async def boom(candle: Candle) -> None:
        raise RuntimeError("strategy blew up")

    async def record(candle: Candle) -> None:
        survivors.append(candle)

    provider.on_candle(boom)
    provider.on_candle(record)
    await provider.start()

    await stream.emit("BTCUSDT", "1m", ws_candle(1))

    assert len(survivors) == 1
    assert provider.candle_count("BTCUSDT", "1m") == 2


# --------------------------------------------------------------------------
# Shutdown
# --------------------------------------------------------------------------
async def test_stop_stops_the_stream_and_leaves_an_injected_client_open() -> None:
    provider, client, stream = build_provider({("BTCUSDT", "1m"): [rest_candle(0)]})
    await provider.start()

    await provider.stop()

    assert stream.stop_calls == 1
    assert client.close_calls == 0  # not ours to close


async def test_stop_stops_the_stream_before_closing_the_client() -> None:
    """Closing the REST pool while the feed is still up would be backwards."""
    journal: list[str] = []
    provider, _, _ = build_provider(
        {("BTCUSDT", "1m"): [rest_candle(0)]}, owns_client=True, journal=journal
    )
    await provider.start()

    await provider.stop()

    assert journal[-2:] == ["stream_stop", "close_client"]


async def test_stop_closes_a_client_the_provider_owns() -> None:
    provider, client, _ = build_provider({("BTCUSDT", "1m"): [rest_candle(0)]}, owns_client=True)
    await provider.start()

    await provider.stop()

    assert client.close_calls == 1


async def test_stop_is_safe_before_start() -> None:
    provider, _, stream = build_provider({("BTCUSDT", "1m"): []})
    await provider.stop()
    assert stream.stop_calls == 1
