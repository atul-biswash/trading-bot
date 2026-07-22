"""Binance Spot adapter implementing the :class:`ExchangeClient` port.

:class:`BinanceClient` wraps ``python-binance``'s :class:`AsyncClient`, mapping
every request/response through the pure functions in
:mod:`trading_bot.exchange.models` and routing every call through
:meth:`BaseExchangeClient._call` for retry + domain-error translation.

Construction is via the async :meth:`create` factory (dependency-injects a
configured ``AsyncClient``); the underlying client can also be injected directly
for tests. ``enforce_filters=True`` makes the adapter round order price/quantity
to the symbol's tick/step and reject sub-minimum orders *before* dispatch, so
invalid requests never reach the exchange (avoiding ``-1013`` filter failures).

Sizing decisions (how much to trade) belong to the risk/execution layers; this
adapter only enforces exchange *filter compliance* on whatever it is handed.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Protocol

from trading_bot.core.enums import TradingMode
from trading_bot.core.exceptions import ExchangeAPIError, OrderError
from trading_bot.core.models import (
    Balance,
    Candle,
    Order,
    OrderRequest,
    SymbolInfo,
    Ticker,
)
from trading_bot.exchange.base import BaseExchangeClient, SleepFn
from trading_bot.exchange.models import (
    order_request_to_params,
    to_balances,
    to_candles,
    to_order,
    to_symbol_info,
    to_ticker,
)
from trading_bot.utils.helpers import round_price, round_step_size, utc_now
from trading_bot.utils.logger import get_logger

if TYPE_CHECKING:  # pragma: no cover - typing only
    from trading_bot.config.settings import Settings


class _AsyncBinanceAPI(Protocol):
    """The subset of ``AsyncClient`` this adapter depends on.

    Declaring the surface as a Protocol keeps the adapter honest about what it
    uses and lets tests supply a lightweight fake without subclassing the real
    client.
    """

    async def ping(self) -> Any: ...
    async def get_account(self, **params: Any) -> dict[str, Any]: ...
    async def get_symbol_info(self, symbol: str) -> dict[str, Any] | None: ...
    async def get_ticker(self, **params: Any) -> dict[str, Any]: ...
    async def get_klines(self, **params: Any) -> list[list[Any]]: ...
    async def create_order(self, **params: Any) -> dict[str, Any]: ...
    async def create_test_order(self, **params: Any) -> dict[str, Any]: ...
    async def cancel_order(self, **params: Any) -> dict[str, Any]: ...
    async def get_open_orders(self, **params: Any) -> list[dict[str, Any]]: ...
    async def close_connection(self) -> None: ...


class BinanceClient(BaseExchangeClient):
    """Async Binance Spot REST adapter."""

    def __init__(
        self,
        client: _AsyncBinanceAPI,
        *,
        recv_window_ms: int = 5000,
        enforce_filters: bool = True,
        retry_attempts: int = 4,
        retry_backoff: float = 0.5,
        retry_max_wait: float = 8.0,
        sleep: SleepFn | None = None,
    ) -> None:
        super().__init__(
            retry_attempts=retry_attempts,
            retry_backoff=retry_backoff,
            retry_max_wait=retry_max_wait,
            sleep=sleep,
        )
        self._client = client
        self._recv_window = recv_window_ms
        self._enforce_filters = enforce_filters
        self._log = get_logger(__name__)

    # -- construction -------------------------------------------------------
    @classmethod
    async def create(
        cls,
        settings: Settings,
        *,
        enforce_filters: bool = True,
        sleep: SleepFn | None = None,
    ) -> BinanceClient:
        """Build a client from :class:`Settings` (testnet unless mode is LIVE).

        The ``testnet`` flag is driven purely by ``settings.mode``; credentials
        come from :meth:`Settings.binance_credentials`, which raises
        :class:`ConfigError` if the required keys are absent.
        """
        from binance import AsyncClient

        api_key, api_secret = settings.binance_credentials()
        exchange = settings.config.exchange
        testnet = settings.mode is TradingMode.TESTNET
        client = await AsyncClient.create(
            api_key=api_key,
            api_secret=api_secret,
            testnet=testnet,
            requests_params={"timeout": exchange.requests_timeout_s},
        )
        return cls(
            client,
            recv_window_ms=exchange.recv_window_ms,
            enforce_filters=enforce_filters,
            sleep=sleep,
        )

    # -- account / market data ---------------------------------------------
    async def get_balances(self) -> list[Balance]:
        raw = await self._call(self._client.get_account, recvWindow=self._recv_window)
        return to_balances(raw)

    async def get_ticker(self, symbol: str) -> Ticker:
        raw = await self._call(self._client.get_ticker, symbol=symbol)
        return to_ticker(raw)

    async def get_klines(
        self, symbol: str, timeframe: str, *, limit: int = 500
    ) -> list[Candle]:
        raw = await self._call(
            self._client.get_klines, symbol=symbol, interval=timeframe, limit=limit
        )
        candles = to_candles(raw, symbol=symbol, timeframe=timeframe)
        # The most recent candle may still be forming; the mapper marks every
        # candle closed, so flip the final one based on the wall clock.
        if candles and candles[-1].close_time > utc_now():
            candles[-1] = candles[-1].model_copy(update={"is_closed": False})
        return candles

    async def _fetch_symbol_info(self, symbol: str) -> SymbolInfo:
        raw = await self._call(self._client.get_symbol_info, symbol)
        if raw is None:
            raise ExchangeAPIError(f"Unknown symbol: {symbol!r}")
        return to_symbol_info(raw)

    # -- orders -------------------------------------------------------------
    async def create_order(self, request: OrderRequest) -> Order:
        prepared = await self._enforce(request) if self._enforce_filters else request
        params = order_request_to_params(prepared)
        params["recvWindow"] = self._recv_window
        # Order placement is NOT idempotent: retry only on rate-limit (rejected
        # pre-acceptance), never on a connection timeout that may have landed.
        raw = await self._call(
            self._client.create_order, idempotent=False, **params
        )
        return to_order(raw)

    async def validate_order(self, request: OrderRequest) -> None:
        """Validate an order via Binance's test endpoint without placing it.

        Applies the same filter enforcement as :meth:`create_order`; returns
        ``None`` on success and raises :class:`OrderError` / other domain errors
        on rejection. Useful as a pre-flight check in the execution layer.
        """
        prepared = await self._enforce(request) if self._enforce_filters else request
        params = order_request_to_params(prepared)
        params["recvWindow"] = self._recv_window
        await self._call(self._client.create_test_order, idempotent=False, **params)

    async def cancel_order(self, symbol: str, order_id: str) -> Order:
        raw = await self._call(
            self._client.cancel_order,
            symbol=symbol,
            orderId=int(order_id),
            recvWindow=self._recv_window,
        )
        return to_order(raw)

    async def get_open_orders(self, symbol: str | None = None) -> list[Order]:
        params: dict[str, Any] = {"recvWindow": self._recv_window}
        if symbol is not None:
            params["symbol"] = symbol
        raw = await self._call(self._client.get_open_orders, **params)
        return [to_order(o) for o in raw]

    # -- lifecycle ----------------------------------------------------------
    async def ping(self) -> None:
        """Round-trip the exchange to verify connectivity/credentials wiring."""
        await self._call(self._client.ping)

    async def close(self) -> None:
        await self._client.close_connection()

    async def __aenter__(self) -> BinanceClient:
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        await self.close()

    # -- filter compliance --------------------------------------------------
    async def _enforce(self, request: OrderRequest) -> OrderRequest:
        """Round price/quantity to the symbol's filters and reject invalid orders.

        Rounds quantity down to ``step_size`` and price down to ``price_tick``,
        then validates ``min_qty`` (always) and ``min_notional`` (when the price
        is known, i.e. non-market orders). Raises :class:`OrderError` before any
        network call if the order cannot satisfy the exchange filters.
        """
        info = await self.get_symbol_info(request.symbol)
        quantity = round_step_size(request.quantity, info.step_size)
        price = (
            round_price(request.price, info.price_tick)
            if request.price is not None
            else None
        )

        if quantity != request.quantity or price != request.price:
            self._log.info(
                "Adjusted %s order to exchange filters: qty %s -> %s, price %s -> %s",
                request.symbol,
                request.quantity,
                quantity,
                request.price,
                price,
            )

        if quantity <= 0:
            raise OrderError(
                f"Quantity for {request.symbol} rounds to zero at step {info.step_size}"
            )
        if quantity < info.min_qty:
            raise OrderError(
                f"Quantity {quantity} below min_qty {info.min_qty} for {request.symbol}"
            )
        if price is not None and info.min_notional > 0:
            notional = quantity * price
            if notional < info.min_notional:
                raise OrderError(
                    f"Notional {notional} below min_notional {info.min_notional} "
                    f"for {request.symbol}"
                )

        return request.model_copy(update={"quantity": quantity, "price": price})
