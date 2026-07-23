"""Tests for :class:`TradingEngine` using a fake provider and scripted strategies.

No network, no real time. The market-data provider is a fake implementing the
:class:`MarketDataProvider` port, which lets the test deliver candles by calling
the engine's registered hook directly, and strategies are scripted to return a
signal, return nothing, or raise.

Candles are built from a recorded Binance WebSocket payload through the real
``ws_kline_to_candle`` mapper, so fixtures carry the same Decimal parsing the
production path uses.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import pandas as pd
import pytest

from trading_bot.config.models import EngineConfig
from trading_bot.core.enums import SignalAction
from trading_bot.core.interfaces import CandleHandler, MarketDataProvider, Strategy
from trading_bot.core.models import Candle, Signal
from trading_bot.engine.live_engine import TradingEngine
from trading_bot.exchange.models import ws_kline_to_candle

_MINUTE_MS = 60_000
_BASE_OPEN_MS = 1_700_000_000_000


def candle(index: int = 0, *, symbol: str = "BTCUSDT", interval: str = "1m") -> Candle:
    """One closed candle, mapped from a recorded WebSocket kline event."""
    open_ms = _BASE_OPEN_MS + index * _MINUTE_MS
    return ws_kline_to_candle(
        {
            "e": "kline",
            "E": open_ms + _MINUTE_MS,
            "s": symbol,
            "k": {
                "t": open_ms,
                "T": open_ms + _MINUTE_MS - 1,
                "s": symbol,
                "i": interval,
                "o": "65000.00000000",
                "c": "65050.00000000",
                "h": "65100.00000000",
                "l": "64900.00000000",
                "v": "12.50000000",
                "n": 100,
                "x": True,
            },
        }
    )


# --------------------------------------------------------------------------
# Fakes
# --------------------------------------------------------------------------
class FakeMarketDataProvider(MarketDataProvider):
    """Port-conformant provider whose candle hook the test drives directly."""

    def __init__(self, counts: dict[tuple[str, str], int] | None = None) -> None:
        self._counts = counts or {}
        self.handlers: list[CandleHandler] = []
        self.frames: dict[tuple[str, str], pd.DataFrame] = {}
        self.start_calls = 0
        self.stop_calls = 0
        self.dataframe_calls: list[tuple[str, str]] = []

    def track(self, symbol: str, timeframe: str) -> None:
        self._counts.setdefault((symbol.upper(), timeframe), 0)

    def on_candle(self, handler: CandleHandler) -> None:
        self.handlers.append(handler)

    async def start(self) -> None:
        self.start_calls += 1

    async def stop(self) -> None:
        self.stop_calls += 1

    def get_dataframe(self, symbol: str, timeframe: str) -> pd.DataFrame:
        key = (symbol.upper(), timeframe)
        self.dataframe_calls.append(key)
        return self.frames.setdefault(key, pd.DataFrame({"close": [1.0, 2.0, 3.0]}))

    def candle_count(self, symbol: str, timeframe: str) -> int:
        return self._counts.get((symbol.upper(), timeframe), 0)

    def last_candle(self, symbol: str, timeframe: str) -> Candle | None:
        return None

    async def emit(self, bar: Candle) -> None:
        """Deliver ``bar`` as if a new candle had just closed."""
        for handler in self.handlers:
            await handler(bar)


class ScriptedStrategy(Strategy):
    """A strategy that returns a fixed result, or raises, on every call."""

    name = "scripted"

    def __init__(
        self,
        *,
        warmup: int = 1,
        result: Signal | None = None,
        raises: Exception | None = None,
    ) -> None:
        self._warmup = warmup
        self._result = result
        self._raises = raises
        self.calls: list[tuple[str, pd.DataFrame]] = []

    @property
    def warmup_period(self) -> int:
        return self._warmup

    def generate_signal(self, symbol: str, candles: pd.DataFrame) -> Signal | None:
        self.calls.append((symbol, candles))
        if self._raises is not None:
            raise self._raises
        return self._result


def buy(symbol: str = "BTCUSDT") -> Signal:
    return Signal(symbol=symbol, action=SignalAction.BUY, reason="test")


def build_engine(
    strategy: Strategy | None = None,
    *,
    counts: dict[tuple[str, str], int] | None = None,
    pair: tuple[str, str] = ("BTCUSDT", "1m"),
    max_strategy_errors: int = 5,
    history_limit: int | None = None,
) -> tuple[TradingEngine, FakeMarketDataProvider, Strategy]:
    resolved = strategy if strategy is not None else ScriptedStrategy()
    provider = FakeMarketDataProvider(counts if counts is not None else {pair: 100})
    engine = TradingEngine(
        provider,
        {pair: resolved},
        max_strategy_errors=max_strategy_errors,
        history_limit=history_limit,
    )
    return engine, provider, resolved


# --------------------------------------------------------------------------
# Construction & lifecycle
# --------------------------------------------------------------------------
def test_rejects_negative_error_budget() -> None:
    with pytest.raises(ValueError, match="max_strategy_errors"):
        TradingEngine(FakeMarketDataProvider(), {}, max_strategy_errors=-1)


async def test_start_wires_the_hook_and_starts_the_provider() -> None:
    engine, provider, _ = build_engine()

    await engine.start()

    assert len(provider.handlers) == 1
    assert provider.start_calls == 1


async def test_start_is_idempotent() -> None:
    engine, provider, _ = build_engine()

    await engine.start()
    await engine.start()

    assert provider.start_calls == 1
    assert len(provider.handlers) == 1


async def test_start_without_strategies_raises() -> None:
    engine = TradingEngine(FakeMarketDataProvider(), {})
    with pytest.raises(ValueError, match="no strategies"):
        await engine.start()


async def test_stop_stops_the_provider() -> None:
    engine, provider, _ = build_engine()
    await engine.start()

    await engine.stop()

    assert provider.stop_calls == 1


async def test_run_returns_once_stop_is_requested() -> None:
    engine, provider, _ = build_engine()

    task = asyncio.create_task(engine.run())
    await asyncio.sleep(0)  # let run() reach the wait
    engine.request_stop()
    await asyncio.wait_for(task, timeout=1)

    assert provider.start_calls == 1
    assert provider.stop_calls == 1


async def test_run_stops_the_provider_even_if_interrupted() -> None:
    """A cancelled wait must still release the feed's connections."""
    engine, provider, _ = build_engine()

    task = asyncio.create_task(engine.run())
    await asyncio.sleep(0)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    assert provider.stop_calls == 1


# --------------------------------------------------------------------------
# Warmup gating
# --------------------------------------------------------------------------
async def test_strategy_is_not_called_before_warmup() -> None:
    strategy = ScriptedStrategy(warmup=50, result=buy())
    engine, provider, _ = build_engine(strategy, counts={("BTCUSDT", "1m"): 49})
    await engine.start()

    await provider.emit(candle())

    assert strategy.calls == []


async def test_strategy_is_called_once_warmup_is_satisfied() -> None:
    strategy = ScriptedStrategy(warmup=50, result=buy())
    engine, provider, _ = build_engine(strategy, counts={("BTCUSDT", "1m"): 50})
    await engine.start()

    await provider.emit(candle())

    assert len(strategy.calls) == 1
    symbol, frame = strategy.calls[0]
    assert symbol == "BTCUSDT"
    assert frame is provider.frames[("BTCUSDT", "1m")]
    assert provider.dataframe_calls == [("BTCUSDT", "1m")]


async def test_warns_when_history_cannot_cover_warmup(
    caplog: pytest.LogCaptureFixture,
) -> None:
    strategy = ScriptedStrategy(warmup=800)
    engine, _, _ = build_engine(strategy, history_limit=500)

    with caplog.at_level(logging.WARNING):
        await engine.start()

    assert "needs 800 candles of warmup" in caplog.text
    assert "300 more bars" in caplog.text


async def test_no_warning_when_history_covers_warmup(
    caplog: pytest.LogCaptureFixture,
) -> None:
    strategy = ScriptedStrategy(warmup=100)
    engine, _, _ = build_engine(strategy, history_limit=500)

    with caplog.at_level(logging.WARNING):
        await engine.start()

    assert "warmup" not in caplog.text


# --------------------------------------------------------------------------
# Signal emission
# --------------------------------------------------------------------------
async def test_signal_is_emitted_to_handlers_in_order() -> None:
    engine, provider, _ = build_engine(ScriptedStrategy(result=buy()))
    order: list[str] = []

    async def first(signal: Signal) -> None:
        order.append("first")

    async def second(signal: Signal) -> None:
        order.append("second")

    engine.on_signal(first)
    engine.on_signal(second)
    await engine.start()

    await provider.emit(candle())

    assert order == ["first", "second"]


async def test_no_signal_means_no_handler_call() -> None:
    engine, provider, _ = build_engine(ScriptedStrategy(result=None))
    seen: list[Signal] = []

    async def record(signal: Signal) -> None:
        seen.append(signal)

    engine.on_signal(record)
    await engine.start()

    await provider.emit(candle())

    assert seen == []


async def test_failing_signal_handler_does_not_stop_the_others() -> None:
    engine, provider, _ = build_engine(ScriptedStrategy(result=buy()))
    survivors: list[Signal] = []

    async def boom(signal: Signal) -> None:
        raise RuntimeError("risk manager exploded")

    async def record(signal: Signal) -> None:
        survivors.append(signal)

    engine.on_signal(boom)
    engine.on_signal(record)
    await engine.start()

    await provider.emit(candle())

    assert len(survivors) == 1


# --------------------------------------------------------------------------
# Routing
# --------------------------------------------------------------------------
async def test_each_pair_uses_its_own_strategy() -> None:
    btc = ScriptedStrategy(result=buy("BTCUSDT"))
    eth = ScriptedStrategy(result=buy("ETHUSDT"))
    provider = FakeMarketDataProvider({("BTCUSDT", "1m"): 100, ("ETHUSDT", "5m"): 100})
    engine = TradingEngine(provider, {("BTCUSDT", "1m"): btc, ("ETHUSDT", "5m"): eth})
    await engine.start()

    await provider.emit(candle(symbol="ETHUSDT", interval="5m"))

    assert btc.calls == []
    assert len(eth.calls) == 1
    assert eth.calls[0][0] == "ETHUSDT"


async def test_candle_for_an_unknown_pair_is_ignored() -> None:
    strategy = ScriptedStrategy(result=buy())
    engine, provider, _ = build_engine(strategy)
    await engine.start()

    await provider.emit(candle(symbol="DOGEUSDT"))

    assert strategy.calls == []


async def test_symbol_case_is_normalised() -> None:
    strategy = ScriptedStrategy(result=buy())
    provider = FakeMarketDataProvider({("BTCUSDT", "1m"): 100})
    engine = TradingEngine(provider, {("btcusdt", "1m"): strategy})
    await engine.start()

    await provider.emit(candle())

    assert len(strategy.calls) == 1


# --------------------------------------------------------------------------
# Strategy failure containment
# --------------------------------------------------------------------------
async def test_strategy_exception_does_not_kill_the_engine() -> None:
    strategy = ScriptedStrategy(raises=RuntimeError("indicator blew up"))
    engine, provider, _ = build_engine(strategy)
    seen: list[Signal] = []

    async def record(signal: Signal) -> None:
        seen.append(signal)

    engine.on_signal(record)
    await engine.start()

    await provider.emit(candle(0))
    await provider.emit(candle(1))

    assert len(strategy.calls) == 2  # still being evaluated
    assert seen == []


async def test_pair_is_quarantined_after_consecutive_failures(
    caplog: pytest.LogCaptureFixture,
) -> None:
    strategy = ScriptedStrategy(raises=RuntimeError("always fails"))
    engine, provider, _ = build_engine(strategy, max_strategy_errors=3)
    await engine.start()

    with caplog.at_level(logging.ERROR):
        for index in range(5):
            await provider.emit(candle(index))

    assert len(strategy.calls) == 3  # stopped being called after the 3rd failure
    assert "Quarantining BTCUSDT/1m" in caplog.text


async def test_a_success_resets_the_failure_streak() -> None:
    """Intermittent failures must never accumulate into a quarantine."""

    class FlakyStrategy(ScriptedStrategy):
        def __init__(self) -> None:
            super().__init__()
            self._n = 0

        def generate_signal(self, symbol: str, candles: pd.DataFrame) -> Signal | None:
            self.calls.append((symbol, candles))
            self._n += 1
            if self._n % 3 != 0:  # fails twice, then succeeds, forever
                raise RuntimeError("flaky")
            return None

    strategy = FlakyStrategy()
    engine, provider, _ = build_engine(strategy, max_strategy_errors=3)
    await engine.start()

    for index in range(12):
        await provider.emit(candle(index))

    assert len(strategy.calls) == 12  # never quarantined


async def test_zero_error_budget_disables_quarantine() -> None:
    strategy = ScriptedStrategy(raises=RuntimeError("always fails"))
    engine, provider, _ = build_engine(strategy, max_strategy_errors=0)
    await engine.start()

    for index in range(10):
        await provider.emit(candle(index))

    assert len(strategy.calls) == 10


# --------------------------------------------------------------------------
# Configuration
# --------------------------------------------------------------------------
def test_engine_config_default_error_budget() -> None:
    assert EngineConfig().max_strategy_errors == 5


def test_engine_config_rejects_negative_error_budget() -> None:
    with pytest.raises(ValueError):
        EngineConfig(max_strategy_errors=-1)


def test_app_config_parses_engine_error_budget(tmp_path: Any) -> None:
    from trading_bot.config.settings import get_settings

    path = tmp_path / "config.yaml"
    path.write_text(
        "mode: testnet\n"
        "engine:\n  max_strategy_errors: 2\n"
        "strategy:\n  name: sma_crossover\n"
        "backtesting:\n  start_date: '2024-01-01'\n  end_date: '2024-02-01'\n",
        encoding="utf-8",
    )
    settings = get_settings(str(path))
    assert settings.config.engine.max_strategy_errors == 2


def _config_with_pairs(tmp_path: Any) -> str:
    path = tmp_path / "config.yaml"
    path.write_text(
        "mode: testnet\n"
        "trading:\n"
        "  pairs:\n"
        "    - symbol: btcusdt\n      timeframe: 1m\n"
        "    - symbol: ETHUSDT\n      timeframe: 5m\n"
        "    - symbol: DOGEUSDT\n      timeframe: 1m\n      enabled: false\n"
        "strategy:\n  name: sma_crossover\n  params:\n    fast_period: 5\n    slow_period: 20\n"
        "backtesting:\n  start_date: '2024-01-01'\n  end_date: '2024-02-01'\n",
        encoding="utf-8",
    )
    return str(path)


async def test_create_builds_one_strategy_instance_per_enabled_pair(tmp_path: Any) -> None:
    from trading_bot.config.settings import get_settings

    settings = get_settings(_config_with_pairs(tmp_path))
    provider = FakeMarketDataProvider({("BTCUSDT", "1m"): 100, ("ETHUSDT", "5m"): 100})

    engine = await TradingEngine.create(settings, provider=provider)

    strategies = engine.pairs
    assert set(strategies) == {("BTCUSDT", "1m"), ("ETHUSDT", "5m")}  # disabled pair skipped
    btc = engine.strategy_for("BTCUSDT", "1m")
    eth = engine.strategy_for("ETHUSDT", "5m")
    assert btc is not None and eth is not None
    assert btc is not eth  # separate instances: no cross-symbol state bleed
    assert btc.name == "sma_crossover"
    assert btc.warmup_period == 21  # slow_period + 1, from config params
    assert engine.strategy_for("DOGEUSDT", "1m") is None


async def test_unimplemented_stub_strategy_is_quarantined_not_fatal(
    tmp_path: Any, caplog: pytest.LogCaptureFixture
) -> None:
    """The shipped strategy stubs raise NotImplementedError on every bar.

    The engine must survive that, log it once loudly, and fall silent — not
    emit a traceback per candle forever.
    """
    from trading_bot.config.settings import get_settings

    settings = get_settings(_config_with_pairs(tmp_path))
    settings.config.engine.max_strategy_errors = 2
    provider = FakeMarketDataProvider({("BTCUSDT", "1m"): 500, ("ETHUSDT", "5m"): 500})

    engine = await TradingEngine.create(settings, provider=provider)
    await engine.start()

    with caplog.at_level(logging.ERROR):
        for index in range(6):
            await provider.emit(candle(index))

    assert "Quarantining BTCUSDT/1m" in caplog.text
    # Two failures were evaluated, then the pair went quiet.
    assert provider.dataframe_calls == [("BTCUSDT", "1m"), ("BTCUSDT", "1m")]
