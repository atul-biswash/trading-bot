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

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, Protocol

from trading_bot.core.enums import TradingMode
from trading_bot.core.exceptions import ExchangeAPIError, FilterRejectedError, OrderError
from trading_bot.core.models import (
    Balance,
    Candle,
    Order,
    OrderList,
    OrderRequest,
    OtocoOrderListRequest,
    OtoOrderListRequest,
    SymbolInfo,
    Ticker,
)
from trading_bot.exchange.base import BaseExchangeClient, SleepFn
from trading_bot.exchange.ids import ClientOrderIdParts, parse_client_order_id
from trading_bot.exchange.models import (
    enforce_oto_filters,
    enforce_otoco_filters,
    order_request_to_params,
    oto_request_to_params,
    otoco_request_to_params,
    to_balances,
    to_candles,
    to_order,
    to_order_list,
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
    async def v3_post_order_list_otoco(self, **params: Any) -> dict[str, Any]: ...
    async def v3_post_order_list_oto(self, **params: Any) -> dict[str, Any]: ...
    async def v3_get_order_list(self, **params: Any) -> dict[str, Any]: ...
    async def v3_get_order(self, **params: Any) -> dict[str, Any]: ...
    async def v3_get_all_order_list(self, **params: Any) -> list[dict[str, Any]]: ...
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

    # -- per-call transport bound -------------------------------------------
    @staticmethod
    def _with_call_timeout(params: Mapping[str, Any], timeout_s: float | None) -> dict[str, Any]:
        """Return ``params`` carrying a per-call HTTP timeout, or a copy of it.

        **The channel is a library internal and this is its only user.**
        ``python-binance`` merges ``data["requests_params"]`` into the keyword
        arguments it hands aiohttp, then deletes the key before signing, so a
        timeout supplied this way bounds exactly one HTTP round trip and never
        reaches the wire as a parameter. ``exchange.requests_timeout_s`` is
        merged first and is therefore overridden by whatever this supplies.

        **It emits exactly ``{"timeout": ...}``, and that restraint is the whole
        of its safety.** The merge is ``kwargs.update()`` over *every* key, so
        this is an arbitrary keyword-argument injection into ``aiohttp``, not a
        timeout parameter. A second key would be forwarded verbatim and fail at
        the transport with a ``TypeError`` rather than as a domain error.

        **Always a fresh dict, never the caller's.** ``_get_request_kwargs``
        does ``del kwargs["data"]["requests_params"]`` on what it is given, so a
        shared or reused mapping would be mutated under its owner.

        ``None`` means "no per-call bound" and yields a plain copy, so a caller
        that has no deadline pays nothing and looks the same at the call site.
        """
        if timeout_s is None:
            return dict(params)
        return {**params, "requests_params": {"timeout": timeout_s}}

    # -- account / market data ---------------------------------------------
    async def get_balances(self) -> list[Balance]:
        raw = await self._call(self._client.get_account, recvWindow=self._recv_window)
        return to_balances(raw)

    async def get_ticker(self, symbol: str) -> Ticker:
        raw = await self._call(self._client.get_ticker, symbol=symbol)
        return to_ticker(raw)

    async def get_klines(self, symbol: str, timeframe: str, *, limit: int = 500) -> list[Candle]:
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
        """Fetch one symbol's filters, uncached. See :meth:`get_symbol_info`.

        **OUT OF SCOPE for the per-call transport bound, and it is the one
        exclusion that sits on a timed path.** ``AsyncClient.get_symbol_info``
        takes an explicit ``symbol`` rather than ``**params``, and it delegates
        to ``get_exchange_info`` -- the whole-exchange payload -- so there is no
        params dict for :meth:`_with_call_timeout` to ride and no narrower
        endpoint to call instead.

        It reaches the dispatch path through ``_enforce`` and both
        ``_prepare_*`` methods, where a cache miss would spend an unbounded call
        inside a bounded sequence. Safe today only because the composition root
        primes every configured symbol at boot and nothing refreshes the cache:
        two facts in two other files, with nothing linking them, which is why
        the exclusion is written down here rather than inferred.
        """
        raw = await self._call(self._client.get_symbol_info, symbol)
        if raw is None:
            raise ExchangeAPIError(f"Unknown symbol: {symbol!r}")
        return to_symbol_info(raw)

    # -- orders -------------------------------------------------------------
    async def create_order(
        self,
        request: OrderRequest,
        *,
        timeout_s: float | None = None,
        attempts: int | None = None,
    ) -> Order:
        """Place a single order.

        ``timeout_s`` bounds one HTTP round trip and ``attempts`` bounds how many
        are made; ``None`` for either means the client's own policy, which is
        what every caller uses today.

        **The filter-enforcement lookup is NOT covered by ``timeout_s``.**
        ``_enforce`` calls :meth:`get_symbol_info`, which cannot carry the
        per-call channel, so on a cache miss this method makes an unbounded call
        before the bounded one. It is warm in practice because the composition
        root primes every configured symbol at boot and nothing refreshes -- a
        fact that lives in another file, which is why it is written here.
        """
        prepared = await self._enforce(request) if self._enforce_filters else request
        params = order_request_to_params(prepared)
        params["recvWindow"] = self._recv_window
        # Order placement is NOT idempotent: retry only on rate-limit (rejected
        # pre-acceptance), never on a connection timeout that may have landed.
        raw = await self._call(
            self._client.create_order,
            idempotent=False,
            attempts=attempts,
            **self._with_call_timeout(params, timeout_s),
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

    async def cancel_order(
        self,
        symbol: str,
        order_id: str,
        *,
        timeout_s: float | None = None,
        attempts: int | None = None,
    ) -> Order:
        """Cancel one order by venue id.

        ``idempotent`` is left at its default of ``True`` **deliberately**: a
        cancel is idempotent at the venue, so retrying REDUCES the frequency of
        unknown state rather than creating it, and ``-2011`` on a retry is
        strictly more informative than a timeout because it rules out "never
        received". Do not narrow it without re-arguing that.

        The response names the order differently from every other shape -- ours
        arrives in ``origClientOrderId`` -- which :func:`to_order` handles.
        """
        params = {
            "symbol": symbol,
            "orderId": int(order_id),
            "recvWindow": self._recv_window,
        }
        raw = await self._call(
            self._client.cancel_order,
            attempts=attempts,
            **self._with_call_timeout(params, timeout_s),
        )
        return to_order(raw)

    async def get_open_orders(self, symbol: str | None = None) -> list[Order]:
        params: dict[str, Any] = {"recvWindow": self._recv_window}
        if symbol is not None:
            params["symbol"] = symbol
        raw = await self._call(self._client.get_open_orders, **params)
        return [to_order(o) for o in raw]

    # -- order lists --------------------------------------------------------
    async def create_otoco_order_list(
        self,
        request: OtocoOrderListRequest,
        *,
        timeout_s: float | None = None,
        attempts: int | None = None,
    ) -> OrderList:
        """Place a three-leg OTOCO list: working ``LIMIT``, below stop, above target.

        **Its own method rather than a branch shared with OTO**, mirroring the
        two mappers. Q-C section 2 calls the arity branch irreducible and it
        dispatches to a different endpoint, so the caller selects by selecting
        the request type it built -- and there is no ``else`` here that cannot
        occur.

        ``idempotent=False``, and this is the write the rule was written for: a
        connection timeout **may have landed**, so it must not be resent. The
        recovery is to QUERY the IDs we would have sent, which Q-C section 6
        makes derivable by pure computation. Only ``RateLimitError`` is retried,
        because a 429 is rejected before acceptance.

        **The dispatch budget is now EXPRESSIBLE here and is still not SET.**
        ``timeout_s`` bounds one HTTP round trip and ``attempts`` bounds how many
        are made; both default to ``None``, meaning the client's own policy, so
        this method behaves exactly as it did until a caller supplies them.
        Nothing does yet. The values derive from ``risk.dispatch_deadline_s``,
        which is a PLACEHOLDER, and belong with the executor that spends it --
        M5d-008 recorded the gap as 4 x ``requests_timeout_s`` + 3.5s of backoff
        against a deadline of 9.0, and closing it is a decision about numbers
        rather than about mechanism.

        **The filter lookup in :meth:`_prepare_otoco` is NOT covered by
        ``timeout_s``** -- see :meth:`create_order` for why that is safe today
        and where the fact it rests on lives.

        Returns an :class:`OrderList`. The placement response carries both
        ``orders`` and ``orderReports``; :func:`to_order_list` reads the former,
        whose shape is MEASURED identical to the read-back's. ``orderReports``
        -- which carries section 7's whole compare set, free, at the one moment
        it is offered -- is deliberately **not consumed**; a caller that needs
        leg detail re-reads. That is a recorded loss, not an oversight.
        """
        params = await self._prepare_otoco(request)
        raw = await self._call(
            self._client.v3_post_order_list_otoco,
            idempotent=False,
            attempts=attempts,
            **self._with_call_timeout(params, timeout_s),
        )
        return to_order_list(raw)

    async def create_oto_order_list(
        self,
        request: OtoOrderListRequest,
        *,
        timeout_s: float | None = None,
        attempts: int | None = None,
    ) -> OrderList:
        """Place a two-leg OTO list: working ``LIMIT`` and a stop, no target.

        See :meth:`create_otoco_order_list` for the retry classification, the
        per-call bounds and the response mapping; all apply unchanged. The only
        difference is the endpoint and the parameter set -- thirteen rather than
        sixteen, under section 3's plain ``pending*`` prefix.
        """
        params = await self._prepare_oto(request)
        raw = await self._call(
            self._client.v3_post_order_list_oto,
            idempotent=False,
            attempts=attempts,
            **self._with_call_timeout(params, timeout_s),
        )
        return to_order_list(raw)

    async def _prepare_otoco(self, request: OtocoOrderListRequest) -> dict[str, Any]:
        """Filter-check and map, so nothing reaches the wire unchecked."""
        info = await self.get_symbol_info(request.symbol)
        prepared = enforce_otoco_filters(request, info) if self._enforce_filters else request
        params = otoco_request_to_params(prepared)
        params["recvWindow"] = self._recv_window
        return params

    async def _prepare_oto(self, request: OtoOrderListRequest) -> dict[str, Any]:
        info = await self.get_symbol_info(request.symbol)
        prepared = enforce_oto_filters(request, info) if self._enforce_filters else request
        params = oto_request_to_params(prepared)
        params["recvWindow"] = self._recv_window
        return params

    async def get_order_list(
        self,
        *,
        order_list_id: str | None = None,
        list_client_order_id: str | None = None,
        timeout_s: float | None = None,
        attempts: int | None = None,
    ) -> OrderList:
        """Read one order list back, by the venue's ID or by ours.

        **This is the only view of a TERMINATED list, and that is the whole
        reason it exists.** Enumeration answers "what rests"; it cannot tell
        "never placed" from "placed and already terminal", because both return
        nothing. That distinction is what the timed-out-write recovery turns on,
        and terminal lists were MEASURED to remain queryable for at least 1d16h
        (M5d-054). Everything else this returns -- list status, leg identities --
        is derivable from :meth:`get_own_open_orders`, so it is not built for
        those.

        **It does NOT carry Q-C section 7's compare set.** The read-back's legs
        are identity triples: no ``status``, no ``executedQty``, no prices
        (MEASURED, M5d-052). Use :meth:`get_own_open_orders` for those.

        Idempotent -- a read, so ``_call``'s default policy applies and a
        connection error is retried. That is the opposite classification from
        the placement methods above, and deliberately so: re-reading cannot
        create anything.

        :raises ValueError: neither identifier given, or both. The venue accepts
            either and we do not guess which the caller meant.
        """
        if (order_list_id is None) == (list_client_order_id is None):
            raise ValueError(
                "pass exactly one of order_list_id or list_client_order_id, "
                f"got order_list_id={order_list_id!r}, "
                f"list_client_order_id={list_client_order_id!r}"
            )
        params: dict[str, Any] = {"recvWindow": self._recv_window}
        if order_list_id is not None:
            params["orderListId"] = int(order_list_id)
        else:
            params["origClientOrderId"] = list_client_order_id
        raw = await self._call(
            self._client.v3_get_order_list,
            attempts=attempts,
            **self._with_call_timeout(params, timeout_s),
        )
        return to_order_list(raw)

    async def get_order(
        self,
        symbol: str,
        *,
        order_id: str | None = None,
        client_order_id: str | None = None,
        timeout_s: float | None = None,
        attempts: int | None = None,
    ) -> Order:
        """Read one order back, by the venue's id or by ours.

        **A POINT QUERY IS A DIFFERENT INSTRUMENT FROM ENUMERATION, and the
        reconciler needs both.** MEASURED: after a cancel, `get_open_orders`
        returns ``[]`` while this endpoint still reports the order with
        ``status`` ``CANCELED``. So an ABSENT leg is not a resolved leg --
        enumeration says only "it does not rest", and never-placed, cancelled
        and (unmeasured) filled all look identical from there. A classifier that
        resolved absence directly would be reading one instrument for an answer
        only the other can give.

        **Ours comes back in ``clientOrderId`` here**, not in
        ``origClientOrderId``: the substitution is a property of the CANCEL
        response, not of the order. :func:`to_order` prefers the latter where
        present and falls through to the former, which is correct for both.

        Idempotent -- a read, so ``_call``'s default policy applies. See
        :meth:`create_order` for ``timeout_s`` and ``attempts``.

        :raises ValueError: neither identifier given, or both. The venue accepts
            either and we do not guess which the caller meant.
        """
        if (order_id is None) == (client_order_id is None):
            raise ValueError(
                "pass exactly one of order_id or client_order_id, "
                f"got order_id={order_id!r}, client_order_id={client_order_id!r}"
            )
        params: dict[str, Any] = {"symbol": symbol, "recvWindow": self._recv_window}
        if order_id is not None:
            params["orderId"] = int(order_id)
        else:
            params["origClientOrderId"] = client_order_id
        raw = await self._call(
            self._client.v3_get_order,
            attempts=attempts,
            **self._with_call_timeout(params, timeout_s),
        )
        return to_order(raw)

    async def get_all_order_lists(
        self,
        *,
        timeout_s: float | None = None,
        attempts: int | None = None,
    ) -> list[OrderList]:
        """Every order list on the account, live and terminal, with its status.

        **This is R13's "did it place?" query, and the reason it is not a point
        query is an ambiguity rather than a preference.** A point query by our
        own id has an undefined answer once that id has been used twice -- the
        live order, the most recent, or a stale terminal one, indistinguishable
        in the payload -- and generation-0 ids repeat within a single dispatch
        by construction, because the id derives from ``(symbol,
        entry_bar_time)``. Enumerating and letting the caller pick avoids
        trusting the venue's choice.

        MEASURED: it returns terminal lists intact days after they closed, and a
        live list alongside them carrying ``EXEC_STARTED``/``EXECUTING``.

        **No ``limit`` or ``fromId`` parameter**, deliberately: the venue's
        default already returns what the disambiguation needs, and a paging
        argument with no caller is surface this milestone has not earned.

        Idempotent. Each element maps through :func:`to_order_list`, whose shape
        is measured identical to the single-list read-back's.
        """
        params: dict[str, Any] = {"recvWindow": self._recv_window}
        raw = await self._call(
            self._client.v3_get_all_order_list,
            attempts=attempts,
            **self._with_call_timeout(params, timeout_s),
        )
        return [to_order_list(entry) for entry in raw]

    async def get_own_open_orders(
        self,
        symbol: str,
        *,
        timeout_s: float | None = None,
        attempts: int | None = None,
    ) -> list[tuple[ClientOrderIdParts, Order]]:
        """Our RESTING orders on ``symbol``, each paired with its parsed identity.

        **Scoped to what RESTS, which is what the endpoint means.** A filled leg
        is not open and its absence here is the correct answer, not a gap.
        Whether a filled leg remains visible to this endpoint at all is
        UNMEASURED (M5d-072) -- and nothing here depends on it, precisely
        because the claim is "what rests" rather than "everything of ours". A
        caller needing fill history wants ``get_order`` by ID, not this.

        **`get_open_orders`, not `v3_get_order_list`, and the choice is
        measured.** This endpoint returns FULL order objects for all three legs
        including pendings in ``PENDING_NEW`` -- ``status``, ``executedQty``,
        ``origQty``, ``stopPrice`` -- which is Q-C section 7's compare set
        (MEASURED, M5d-064/M5d-066). The list read-back returns identity triples
        and cannot supply it.

        **Filtered by PARSING, not by the raw prefix**, and the tie-break is not
        caution. Section 6 requires generation recovery to query prefix-matching
        orders and take "the highest seen" -- and a raw ``startswith("tb1-")``
        yields no generation to take. Parsing supplies it, and rejects
        ``tb1-garbage``, which a prefix test would accept as ours. The failure
        section 6 exists to prevent is treating a human's order as ours; the
        parse is a strictly narrower filter than the prefix it replaces.

        Foreign orders are dropped silently: this endpoint returns *every* order
        on the symbol, ours and otherwise, so meeting other people's orders is
        the ordinary case rather than an anomaly.
        """
        params = {"symbol": symbol, "recvWindow": self._recv_window}
        raw = await self._call(
            self._client.get_open_orders,
            attempts=attempts,
            **self._with_call_timeout(params, timeout_s),
        )
        found: list[tuple[ClientOrderIdParts, Order]] = []
        for payload in raw:
            order = to_order(payload)
            parts = parse_client_order_id(order.client_order_id or "")
            if parts is not None:
                found.append((parts, order))
        return found

    # -- lifecycle ----------------------------------------------------------
    async def ping(self) -> None:
        """Round-trip the exchange to verify connectivity/credentials wiring.

        **OUT OF SCOPE for the per-call transport bound**, and it is a property
        of the library rather than a choice: ``AsyncClient.ping`` takes no
        parameters, so there is no params dict for
        :meth:`_with_call_timeout` to ride. Recorded rather than left silently
        unbounded. ``attempts`` could be supplied; no caller wants it.
        """
        await self._call(self._client.ping)

    async def close(self) -> None:
        # OUT OF SCOPE for the per-call transport bound: `close_connection`
        # takes no parameters, so there is no params dict to carry it. Teardown
        # is also the one path where a tighter bound would be actively wrong --
        # abandoning it leaks an aiohttp session, and the masking window this
        # method exists to close is measured in the error it would hide, not in
        # seconds.
        #
        # The one method that used to reach the client without `_call`, so a
        # transport failure here escaped as a raw `aiohttp.ClientError`.
        # `live_system` closes in an unconditional `finally`, where such a raise
        # propagates over the boot error that caused the teardown -- the exact
        # masking the nested-teardown design exists to prevent.
        #
        # `idempotent=False` reads backwards and is not: the flag means "is a
        # connection failure safe to retry", not "is this operation idempotent".
        # `_IDEMPOTENT_RETRY` contains `ExchangeConnectionError`, so `True` would
        # retry the very failure this classification exists to surface, spending
        # backoff inside the teardown and lengthening the masking window.
        await self._call(self._client.close_connection, idempotent=False)

    async def __aenter__(self) -> BinanceClient:
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        await self.close()

    # -- filter compliance --------------------------------------------------
    async def _enforce(self, request: OrderRequest) -> OrderRequest:
        """Round price/quantity to the symbol's filters and reject invalid orders.

        Rounds quantity down to the **effective** lot step and price down to
        ``price_tick``, then validates the **effective** minimum quantity
        (always) and ``min_notional`` (whenever *some* price is known -- the
        limit price, or a stop-type order's trigger). Raises
        :class:`OrderError` before any network call if the order cannot satisfy
        the exchange filters.

        **A plain ``MARKET`` order is still not notional-checked**, and that is
        a stated limit rather than an oversight: no client-side price exists to
        multiply, and the exchange evaluates it against a 5-minute average this
        method never fetches. Binance does apply the minimum to market orders --
        ``NOTIONAL.applyMinToMarket`` is ``true`` on both configured symbols
        (MEASURED, Testnet) -- so such an order can still be rejected at the
        venue. Whether the same flag binds a *triggered* stop-type order is
        UNRESOLVED; checking the trigger is the conservative reading.

        **Effective, not raw.** ``effective_step_size`` / ``effective_min_qty``
        take the stricter of ``LOT_SIZE`` and ``MARKET_LOT_SIZE``, which is what
        ``risk.position_sizing`` already sizes against. Reading the raw
        ``LOT_SIZE`` fields here made this last line of defence *weaker* than
        the sizing it exists to re-check -- so a quantity the sizer would have
        refused could pass the very guard meant to catch it. The two now agree
        by construction rather than by coincidence.

        **``price`` is rounded and ``stop_price`` is rejected, and the asymmetry
        is deliberate.** ``price`` is legitimately *derived* here: an entry limit
        comes from a candle close and a slippage multiplier, so putting it on
        the tick is part of constructing it. ``stop_price`` is not derived -- it
        *arrives* from ``risk.rules`` already tick-rounded by contract, toward
        its reference, with the direction chosen per level so the realised
        distance can only shrink. An off-tick ``stop_price`` therefore means an
        upstream broke that contract, and rounding it here would paper over the
        break: ``ROUND_DOWN`` on a long's stop moves it *away* from entry, so a
        silently widened stop would breach the ``risk_per_trade`` budget through
        the very component meant to catch such a breach. Rejecting names the
        break instead.

        **What this check is, precisely: detection, not defence.** It does not
        protect the trigger -- ``risk.rules`` rounding correctly is still the
        only thing that does. What it buys is that the dependency on that
        upstream is **explicit and loud** rather than silent and coincidental.
        The trigger is protected once and checked once, not twice.
        """
        info = await self.get_symbol_info(request.symbol)

        if request.stop_price is not None and (
            round_price(request.stop_price, info.price_tick) != request.stop_price
        ):
            raise FilterRejectedError(
                f"stop_price {request.stop_price} for {request.symbol} is not a multiple "
                f"of tickSize {info.price_tick}; protective levels arrive tick-rounded, "
                "so this is an upstream contract violation rather than a market state",
                filter_name="PRICE_FILTER",
            )

        quantity = round_step_size(request.quantity, info.effective_step_size)
        price = round_price(request.price, info.price_tick) if request.price is not None else None

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
                f"Quantity for {request.symbol} rounds to zero at step {info.effective_step_size}"
            )
        if quantity < info.effective_min_qty:
            raise OrderError(
                f"Quantity {quantity} below min_qty {info.effective_min_qty} for {request.symbol}"
            )
        # A stop-market order carries no price, but the exchange still evaluates
        # a notional for it: ``stopPrice * quantity``. Skipping the check
        # whenever ``price`` was absent meant every stop-type order went out
        # unchecked -- and a stop resting below the entry carries the *smaller*
        # notional, so it is the leg the exchange rejects first. Observed live:
        # a Testnet probe took ``-1013 Filter failure: NOTIONAL`` on exactly
        # that. The reference is the price when there is one, the trigger
        # otherwise.
        notional_price = price if price is not None else request.stop_price
        if notional_price is not None and info.min_notional > 0:
            notional = quantity * notional_price
            if notional < info.min_notional:
                raise OrderError(
                    f"Notional {notional} below min_notional {info.min_notional} "
                    f"for {request.symbol}"
                )

        return request.model_copy(update={"quantity": quantity, "price": price})
