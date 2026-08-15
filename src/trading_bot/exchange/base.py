"""Shared machinery for REST exchange adapters.

:class:`BaseExchangeClient` factors out the two concerns every concrete adapter
needs but that don't belong in any single method:

* **Retry + error translation** (:meth:`_call`) — wraps a raw client coroutine
  so transport/library exceptions become domain exceptions
  (:func:`translate_binance_error`) and transient failures are retried with
  exponential backoff. The retry predicate differs for idempotent reads versus
  order placement (see :meth:`_call`).
* **Symbol-info caching** — :meth:`get_symbol_info` memoises immutable trading
  filters so order sizing never pays a network round-trip per order; a subclass
  supplies the actual fetch via :meth:`_fetch_symbol_info`.

The ``sleep`` callable is injectable so tests can drive retries with zero real
delay.
"""

from __future__ import annotations

import asyncio
from abc import abstractmethod
from collections.abc import Awaitable, Callable
from typing import Any

from tenacity import (
    AsyncRetrying,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from trading_bot.core.exceptions import ExchangeConnectionError, RateLimitError
from trading_bot.core.interfaces import ExchangeClient
from trading_bot.core.models import SymbolInfo
from trading_bot.exchange.models import BINANCE_EXCEPTIONS, translate_binance_error

# Exceptions worth retrying. Connection errors are only retried for *idempotent*
# calls; rate-limit errors are always safe to retry after backoff because a 429
# means the request was rejected before it was accepted.
_IDEMPOTENT_RETRY: tuple[type[Exception], ...] = (ExchangeConnectionError, RateLimitError)
_NON_IDEMPOTENT_RETRY: tuple[type[Exception], ...] = (RateLimitError,)

SleepFn = Callable[[float], Awaitable[Any]]


class BaseExchangeClient(ExchangeClient):
    """Base class providing retry/translation and symbol-info caching."""

    def __init__(
        self,
        *,
        retry_attempts: int = 4,
        retry_backoff: float = 0.5,
        retry_max_wait: float = 8.0,
        sleep: SleepFn | None = None,
    ) -> None:
        if retry_attempts < 1:
            raise ValueError("retry_attempts must be >= 1")
        self._retry_attempts = retry_attempts
        self._retry_backoff = retry_backoff
        self._retry_max_wait = retry_max_wait
        self._sleep: SleepFn = sleep or asyncio.sleep
        self._symbol_info_cache: dict[str, SymbolInfo] = {}

    # -- retry + error translation -----------------------------------------
    def _make_retrying(self, *, idempotent: bool, attempts: int | None = None) -> AsyncRetrying:
        retry_types = _IDEMPOTENT_RETRY if idempotent else _NON_IDEMPOTENT_RETRY
        resolved = self._retry_attempts if attempts is None else attempts
        if resolved < 1:
            raise ValueError("attempts must be >= 1")
        return AsyncRetrying(
            retry=retry_if_exception_type(retry_types),
            wait=wait_exponential(multiplier=self._retry_backoff, max=self._retry_max_wait),
            stop=stop_after_attempt(resolved),
            reraise=True,
            sleep=self._sleep,
        )

    async def _call(
        self,
        func: Callable[..., Awaitable[Any]],
        *args: Any,
        idempotent: bool = True,
        attempts: int | None = None,
        **kwargs: Any,
    ) -> Any:
        """Invoke ``func(*args, **kwargs)`` with translation and retries.

        Library/transport exceptions are converted to domain exceptions first,
        so the retry predicate sees domain types. ``idempotent=False`` (used for
        order placement) narrows retries to rate-limit errors only: a connection
        timeout on a write might mean the order *was* accepted, so it must not be
        blindly resent.

        **``attempts`` is the per-call half of the retry budget, and ``None``
        means "use the client's".** A retry policy is a property of what is being
        asked, not of who is asking, so a caller on a deadline can spend fewer
        attempts than a caller that is merely reading -- without needing a second
        client instance configured differently. Nothing supplies it today; every
        existing call site resolves to the constructor's value and is unchanged.

        It is keyword-only and consumed here, so it never reaches ``func`` and
        cannot be mistaken for an exchange parameter.

        **It bounds ATTEMPTS, not TIME.** Wall time is attempts multiplied by
        whatever bounds one attempt, plus the backoff between them; the
        per-attempt bound is the transport timeout, which is a separate channel.
        Neither this parameter nor any other in this class cancels work already
        in flight -- deliberately, because a budget may refuse to begin work and
        must never abandon a write mid-submission.

        :raises ValueError: ``attempts`` below 1.
        """

        async def _attempt() -> Any:
            try:
                return await func(*args, **kwargs)
            except BINANCE_EXCEPTIONS as exc:
                raise translate_binance_error(exc) from exc

        retrying = self._make_retrying(idempotent=idempotent, attempts=attempts)
        return await retrying(_attempt)

    # -- symbol-info cache --------------------------------------------------
    async def get_symbol_info(self, symbol: str) -> SymbolInfo:
        """Return cached trading filters for ``symbol``, fetching once on miss."""
        cached = self._symbol_info_cache.get(symbol)
        if cached is not None:
            return cached
        info = await self._fetch_symbol_info(symbol)
        self._symbol_info_cache[symbol] = info
        return info

    async def refresh_symbol_info(self, symbol: str) -> SymbolInfo:
        """Force a re-fetch of ``symbol``'s filters and update the cache."""
        info = await self._fetch_symbol_info(symbol)
        self._symbol_info_cache[symbol] = info
        return info

    @abstractmethod
    async def _fetch_symbol_info(self, symbol: str) -> SymbolInfo:
        """Fetch trading filters for ``symbol`` from the exchange (no caching)."""
        ...
