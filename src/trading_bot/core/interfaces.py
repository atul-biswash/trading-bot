"""Abstract interfaces (ports) that decouple the layers.

Concrete adapters (the Binance client, a Telegram notifier, a SQLite
repository, individual strategies) implement these Protocols/ABCs. Higher-level
code depends only on the abstractions here — the Dependency Inversion in SOLID —
so implementations can be swapped or mocked in tests without touching callers.

Heavy third-party types (pandas) are imported only under ``TYPE_CHECKING`` so
importing this module never pulls in the data stack.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Awaitable, Callable, Sequence
from typing import TYPE_CHECKING

from trading_bot.core.models import (
    Balance,
    Candle,
    Order,
    OrderRequest,
    Signal,
    SymbolInfo,
    Ticker,
)

if TYPE_CHECKING:  # pragma: no cover - typing only
    import pandas as pd


class ExchangeClient(ABC):
    """Read/write access to a spot exchange over REST."""

    @abstractmethod
    async def get_balances(self) -> list[Balance]: ...

    @abstractmethod
    async def get_symbol_info(self, symbol: str) -> SymbolInfo: ...

    @abstractmethod
    async def get_ticker(self, symbol: str) -> Ticker: ...

    @abstractmethod
    async def get_klines(
        self, symbol: str, timeframe: str, *, limit: int = 500
    ) -> list[Candle]: ...

    @abstractmethod
    async def create_order(self, request: OrderRequest) -> Order: ...

    @abstractmethod
    async def cancel_order(self, symbol: str, order_id: str) -> Order: ...

    @abstractmethod
    async def get_open_orders(self, symbol: str | None = None) -> list[Order]: ...

    @abstractmethod
    async def close(self) -> None: ...


# A callback invoked whenever a (closed) candle arrives on the stream.
CandleHandler = Callable[[Candle], Awaitable[None]]

# A callback invoked whenever a strategy produces a signal. This is the seam
# where risk management and execution attach to the engine in later phases.
SignalHandler = Callable[[Signal], Awaitable[None]]


class MarketDataStream(ABC):
    """A live source of streaming candles via WebSocket."""

    @abstractmethod
    def subscribe(self, symbol: str, timeframe: str, handler: CandleHandler) -> None:
        """Register ``handler`` for closed candles of ``symbol``/``timeframe``."""

    @abstractmethod
    async def start(self) -> None: ...

    @abstractmethod
    async def stop(self) -> None: ...


class MarketDataProvider(ABC):
    """Time-ordered OHLCV history plus live updates, ready for strategies.

    Bridges the REST client (history) and the live stream (updates) into the
    ``DataFrame`` :meth:`Strategy.generate_signal` consumes. Money stays
    ``Decimal`` in :meth:`last_candle`; only the DataFrame is ``float`` — that
    conversion is the one deliberate Decimal->float boundary in the system, and
    it exists because indicator maths runs on NumPy.
    """

    @abstractmethod
    def track(self, symbol: str, timeframe: str) -> None:
        """Register ``symbol``/``timeframe`` for seeding and live updates."""

    @abstractmethod
    def on_candle(self, handler: CandleHandler) -> None:
        """Register ``handler``, invoked after each newly accepted closed candle."""

    @abstractmethod
    async def start(self) -> None:
        """Seed history for every tracked pair, then begin consuming live candles."""

    @abstractmethod
    async def stop(self) -> None:
        """Stop live consumption and release owned resources. Idempotent."""

    @abstractmethod
    def get_dataframe(self, symbol: str, timeframe: str) -> pd.DataFrame:
        """Return the rolling OHLCV window for ``symbol``/``timeframe``.

        Time-ordered ascending, indexed by a tz-aware UTC ``DatetimeIndex`` named
        ``open_time``, with ``float64`` ``open``/``high``/``low``/``close``/
        ``volume`` columns. Callers may mutate the result freely.
        """

    @abstractmethod
    def candle_count(self, symbol: str, timeframe: str) -> int:
        """Number of closed candles currently buffered for the pair."""

    @abstractmethod
    def last_candle(self, symbol: str, timeframe: str) -> Candle | None:
        """Most recent closed candle, with ``Decimal`` precision intact.

        Execution and risk read prices from here, never from the ``float``
        DataFrame, so no money value is ever derived from a binary float.
        """

    def is_ready(self, symbol: str, timeframe: str, warmup_period: int) -> bool:
        """Whether enough candles are buffered to satisfy ``warmup_period``.

        Concrete (not abstract) because it is pure derivation from
        :meth:`candle_count`; re-implementing it per adapter would invite two
        subtly different definitions of "ready" in software that trades money.
        """
        return self.candle_count(symbol, timeframe) >= max(warmup_period, 1)


class Strategy(ABC):
    """Turns a window of market data into an optional trading signal."""

    name: str

    @property
    @abstractmethod
    def warmup_period(self) -> int:
        """Minimum number of candles required before signals are valid."""

    @abstractmethod
    def generate_signal(self, symbol: str, candles: "pd.DataFrame") -> Signal | None:
        """Return a :class:`Signal` for the latest candle, or ``None`` to skip.

        ``candles`` is time-ordered OHLCV with a ``DatetimeIndex``.
        """


class RiskManager(ABC):
    """Vets signals and sizes positions against configured limits."""

    @abstractmethod
    def size_position(self, signal: Signal, *, equity, price, stop_price=None): ...

    @abstractmethod
    def approve(self, signal: Signal, *, portfolio) -> bool:
        """Return ``True`` if acting on ``signal`` respects all risk limits."""


class OrderExecutor(ABC):
    """Places orders derived from approved signals."""

    @abstractmethod
    async def execute(self, request: OrderRequest) -> Order: ...


class Notifier(ABC):
    """Delivers human-facing notifications (Telegram, etc.)."""

    @abstractmethod
    async def send(self, message: str) -> None: ...


class Repository(ABC):
    """Persists signals, trades and system events."""

    @abstractmethod
    async def save_signal(self, signal: Signal) -> None: ...

    @abstractmethod
    async def save_order(self, order: Order) -> None: ...

    @abstractmethod
    async def recent_signals(self, symbol: str, *, limit: int = 50) -> Sequence[Signal]: ...
