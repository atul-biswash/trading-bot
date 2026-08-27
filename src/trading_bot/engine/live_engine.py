"""Trading engine — the orchestration loop.

:class:`TradingEngine` is the component that turns market data into trading
signals. It owns a :class:`~trading_bot.core.interfaces.MarketDataProvider`,
holds one :class:`~trading_bot.core.interfaces.Strategy` per configured pair,
and evaluates that strategy each time a bar closes.

Event-driven, not polled
------------------------
The engine does no polling loop. It subscribes to the provider's ``on_candle``
hook and reacts when a bar actually closes, which is the only moment a candle
strategy's answer can change. That removes a whole class of bug — duplicate
evaluation of the same bar, or acting on a partially-formed one — and costs
nothing in latency.

Scope
-----
This milestone stops at the signal. Risk sizing, order execution, persistence
and notifications attach later through :meth:`TradingEngine.on_signal`, which is
deliberately the *only* thing the engine does with a signal today. Keeping that
boundary means the data -> strategy path can be verified on Testnet long before
anything is able to place an order.

Failure containment
-------------------
Three independent isolation layers, because a 24/7 process must degrade rather
than die:

* A strategy that raises cannot kill the engine — the exception is logged and
  the next bar is still evaluated.
* A pair whose strategy fails ``max_strategy_errors`` times *consecutively* is
  quarantined: loud once, then silent, instead of a traceback every bar forever.
  Any success resets the counter, so intermittent failures never accumulate.
* A signal handler that raises cannot stop the other handlers or the feed.
"""

from __future__ import annotations

import asyncio
from collections.abc import Mapping
from typing import TYPE_CHECKING

from trading_bot.core.interfaces import (
    MarketDataProvider,
    SignalHandler,
    Strategy,
)
from trading_bot.core.models import Candle, Signal
from trading_bot.utils.logger import get_logger

if TYPE_CHECKING:  # pragma: no cover - typing only
    from trading_bot.config.settings import Settings

_log = get_logger(__name__)

_Key = tuple[str, str]

# Default consecutive-failure budget when the engine is built directly rather
# than from config; ``create()`` overrides it from EngineConfig.
_DEFAULT_MAX_STRATEGY_ERRORS = 5


class TradingEngine:
    """Evaluates strategies on bar close and emits the resulting signals."""

    def __init__(
        self,
        provider: MarketDataProvider,
        strategies: Mapping[_Key, Strategy],
        *,
        max_strategy_errors: int = _DEFAULT_MAX_STRATEGY_ERRORS,
        history_limit: int | None = None,
    ) -> None:
        """Build an engine over an injected provider and per-pair strategies.

        ``strategies`` maps ``(symbol, timeframe)`` to the strategy that trades
        it; symbols are normalised to upper case to match the provider.
        ``history_limit``, when given, is only used to warn at startup that the
        seeded history is too short for a strategy's warmup.
        """
        if max_strategy_errors < 0:
            raise ValueError("max_strategy_errors must be >= 0")

        self._provider = provider
        self._strategies: dict[_Key, Strategy] = {
            (symbol.upper(), timeframe): strategy
            for (symbol, timeframe), strategy in strategies.items()
        }
        self._max_strategy_errors = max_strategy_errors
        self._history_limit = history_limit

        self._signal_handlers: list[SignalHandler] = []
        self._error_counts: dict[_Key, int] = {}
        self._quarantined: set[_Key] = set()
        self._stop_requested = asyncio.Event()
        self._started = False

    # -- construction -------------------------------------------------------
    @classmethod
    async def create(
        cls,
        settings: Settings,
        *,
        provider: MarketDataProvider | None = None,
    ) -> TradingEngine:
        """Build an engine and its market-data provider from :class:`Settings`.

        One strategy *instance per pair* is created rather than one shared
        across symbols. ``generate_signal`` takes the symbol, so a single
        instance would work for a stateless strategy — but a strategy that
        caches anything on ``self`` would silently bleed state between symbols,
        and that bug is invisible until it costs money. Separate instances make
        it impossible; the cost is one small object per pair.
        """
        # Imported lazily, mirroring BufferedMarketDataProvider.create: keeps
        # pandas/NumPy off the import path of anything that only needs the
        # engine's types -- `main.py` annotates against TradingEngine under
        # TYPE_CHECKING and would otherwise pay for the whole data stack to
        # print `--help`.
        from trading_bot.data.market_data import BufferedMarketDataProvider
        from trading_bot.strategies.registry import create_strategy

        resolved_provider = (
            provider if provider is not None else await BufferedMarketDataProvider.create(settings)
        )

        strategy_config = settings.config.strategy
        strategies: dict[_Key, Strategy] = {}
        for pair in settings.config.trading.enabled_pairs:
            strategies[(pair.symbol, pair.timeframe)] = create_strategy(
                strategy_config.name, **strategy_config.params
            )

        return cls(
            resolved_provider,
            strategies,
            max_strategy_errors=settings.config.engine.max_strategy_errors,
            history_limit=settings.config.data.history_limit,
        )

    # -- registration -------------------------------------------------------
    def on_signal(self, handler: SignalHandler) -> None:
        """Register a callback invoked for each signal a strategy produces.

        Handlers run in registration order and are isolated from one another.
        This is where risk management and execution attach in later phases.
        """
        self._signal_handlers.append(handler)

    @property
    def pairs(self) -> list[_Key]:
        """The ``(symbol, timeframe)`` pairs this engine evaluates."""
        return list(self._strategies)

    def strategy_for(self, symbol: str, timeframe: str) -> Strategy | None:
        """The strategy trading a pair, or ``None`` if this engine ignores it."""
        return self._strategies.get((symbol.upper(), timeframe))

    # -- lifecycle ----------------------------------------------------------
    async def start(self) -> None:
        """Wire the candle hook and start the provider. Idempotent."""
        if self._started:
            return
        if not self._strategies:
            raise ValueError("no strategies configured; nothing to run")

        self._warn_on_insufficient_history()
        self._provider.on_candle(self._on_candle)
        await self._provider.start()
        self._started = True
        _log.info(
            "Trading engine started: %s",
            ", ".join(f"{symbol}/{timeframe}" for symbol, timeframe in self._strategies),
        )

    async def stop(self) -> None:
        """Stop the provider and release its resources.

        Idempotent. Safe to call any time.

        **The guard reads ``self._started``, because the object already owns
        that fact.** Until M5g this method had none: it set the flag, signalled,
        stopped the provider and logged, every time it was called. The double
        teardown ``live_system`` performs -- ``run()``'s ``finally`` and the
        root's own -- therefore emitted *"Trading engine stopped"* twice, which
        is how the gap was found (`M5g-079`, run 2, 19:19:32). Nothing failed
        and nothing leaked, because ``provider.stop()`` is safe to repeat; what
        broke was the half of the contract that forbids **duplicating that
        work**.

        A "did I already stop?" flag was not added, and ``CLAUDE.md`` is why:
        it forbids a root papering over double-teardown that way, on the
        grounds that such a flag is *a second source of truth for a fact the
        object already owns*. ``_started`` is that fact, read where it lives.

        **Stopping an engine that never started is a no-op, and that is the
        symmetric reading rather than a gap.** :meth:`start` is what starts the
        provider, so an engine that never started never started one and has
        nothing to release. ``live_system`` stops the provider in its own
        ``finally`` regardless, so no path leaks a feed.

        One consequence worth stating: on that path ``_stop_requested`` is no
        longer set. That sharpens a separation which was blurred --
        :meth:`request_stop` *arms* a shutdown and this *performs* one -- so a
        stop issued before the engine ever ran no longer pre-arms the next
        :meth:`run`.
        """
        if not self._started:
            return
        self._started = False
        self._stop_requested.set()
        await self._provider.stop()
        _log.info("Trading engine stopped")

    def request_stop(self) -> None:
        """Ask :meth:`run` to shut down. Safe to call from a signal handler.

        Synchronous and allocation-free by design: OS signal callbacks cannot
        await, so they flip this event and let the loop unwind normally.
        """
        self._stop_requested.set()

    async def run(self) -> None:
        """Start, run until stopped, then shut down cleanly.

        :meth:`stop` is in a ``finally`` so the provider's WebSocket and REST
        connections are released even if the wait is interrupted — including by
        a ``KeyboardInterrupt`` on Windows, where ``add_signal_handler`` is
        unavailable and Ctrl-C surfaces as an exception instead.
        """
        await self.start()
        try:
            await self._stop_requested.wait()
        finally:
            await self.stop()

    def _warn_on_insufficient_history(self) -> None:
        """Warn when seeded history cannot satisfy a strategy's warmup.

        The engine is the first component that knows both numbers: the provider
        owns ``history_limit`` and the strategy owns ``warmup_period``. Left
        unchecked, the pair would simply never become ready and the bot would
        sit silent for hours with no explanation.
        """
        if self._history_limit is None:
            return
        for (symbol, timeframe), strategy in self._strategies.items():
            warmup = strategy.warmup_period
            if warmup > self._history_limit:
                _log.warning(
                    "%s/%s needs %d candles of warmup but data.history_limit is %d; "
                    "signals will not start until %d more bars have closed live",
                    symbol,
                    timeframe,
                    warmup,
                    self._history_limit,
                    warmup - self._history_limit,
                )

    # -- evaluation ---------------------------------------------------------
    async def _on_candle(self, candle: Candle) -> None:
        """Evaluate the strategy for one freshly-closed bar."""
        key = (candle.symbol, candle.timeframe)
        strategy = self._strategies.get(key)
        if strategy is None:
            # The provider may track pairs this engine has no strategy for.
            _log.debug("No strategy for %s/%s; ignoring candle", key[0], key[1])
            return
        if key in self._quarantined:
            return

        symbol, timeframe = key
        if not self._provider.is_ready(symbol, timeframe, strategy.warmup_period):
            _log.debug(
                "Warming up %s/%s: %d/%d candles",
                symbol,
                timeframe,
                self._provider.candle_count(symbol, timeframe),
                strategy.warmup_period,
            )
            return

        signal = self._evaluate(key, strategy, candle)
        if signal is not None:
            await self._emit(signal, candle)

    def _evaluate(self, key: _Key, strategy: Strategy, candle: Candle) -> Signal | None:
        """Run one strategy against the current window, containing failures.

        ``generate_signal`` is synchronous and runs on the event loop. That is
        intentional: indicator maths over a bounded buffer is sub-millisecond,
        and staying on the loop preserves the single-threaded access guarantee
        the market-data buffer relies on. If a strategy ever becomes genuinely
        slow, the frame handed to it is already a private copy, so moving this
        call to ``asyncio.to_thread`` would be safe.

        ``candle`` is forwarded alongside the frame because it is the same final
        bar carrying full ``Decimal`` precision, and it is what lets a strategy
        put an exact price on its signal. The engine passes the candle it was
        handed rather than re-reading ``provider.last_candle()``: the two are
        identical here -- the provider appends before it notifies -- but only
        the former stays correct if this call ever moves off the current stack,
        at which point ``last_candle()`` could already have advanced a bar. The
        engine deliberately does no other enrichment; a signal leaves the
        strategy complete, so the backtester in a later phase gets the same
        object from the same code without reimplementing anything.
        """
        symbol, timeframe = key
        try:
            frame = self._provider.get_dataframe(symbol, timeframe)
            signal = strategy.generate_signal(symbol, frame, last_candle=candle)
        except Exception as exc:
            self._record_failure(key, exc)
            return None

        self._error_counts.pop(key, None)  # a success clears the streak
        if signal is not None:
            _log.info(
                "Signal %s %s (%s) from %s",
                signal.action.value,
                signal.symbol,
                signal.reason or "no reason given",
                strategy.name,
            )
        return signal

    def _record_failure(self, key: _Key, exc: Exception) -> None:
        """Log a strategy failure and quarantine the pair if it keeps failing.

        The full traceback is logged once. Repeats of the same broken strategy
        are logged as one-liners instead, so the eventual quarantine message is
        not buried under identical stack traces.
        """
        symbol, timeframe = key
        count = self._error_counts.get(key, 0) + 1
        self._error_counts[key] = count
        if count == 1:
            _log.exception("Strategy failed for %s/%s", symbol, timeframe)
        else:
            _log.error(
                "Strategy failed for %s/%s (consecutive failure %d): %r",
                symbol,
                timeframe,
                count,
                exc,
            )
        if self._max_strategy_errors and count >= self._max_strategy_errors:
            self._quarantined.add(key)
            _log.error(
                "Quarantining %s/%s after %d consecutive strategy failures; "
                "no further evaluation until restart",
                symbol,
                timeframe,
                count,
            )

    async def _emit(self, signal: Signal, candle: Candle) -> None:
        """Fan a signal out to registered handlers, isolating failures.

        ``candle`` is the bar the signal was decided on, forwarded rather than
        re-read for the reason :meth:`_evaluate` forwards it to strategies --
        see the note on ``SignalHandler``. A handler needing a restart-stable
        identity seed takes ``candle.close_time``; nothing downstream should
        reach back to ``provider.last_candle()``.
        """
        for handler in self._signal_handlers:
            try:
                await handler(signal, candle)
            except Exception:
                _log.exception("Signal handler failed for %s; continuing", signal.symbol)
