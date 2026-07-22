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


class MarketDataStream(ABC):
    """A live source of streaming candles via WebSocket."""

    @abstractmethod
    def subscribe(self, symbol: str, timeframe: str, handler: CandleHandler) -> None:
        """Register ``handler`` for closed candles of ``symbol``/``timeframe``."""

    @abstractmethod
    async def start(self) -> None: ...

    @abstractmethod
    async def stop(self) -> None: ...


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
