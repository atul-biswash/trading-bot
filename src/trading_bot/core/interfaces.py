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
from decimal import Decimal
from typing import TYPE_CHECKING

from trading_bot.core.assessment import RiskAssessment
from trading_bot.core.models import (
    Balance,
    Candle,
    Order,
    OrderList,
    OrderRequest,
    Signal,
    SizingDecision,
    SymbolInfo,
    Ticker,
)
from trading_bot.core.portfolio import Portfolio

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
    async def get_own_open_orders(
        self,
        symbol: str,
        *,
        timeout_s: float | None = None,
        attempts: int | None = None,
    ) -> list[Order]:
        """Our RESTING orders on ``symbol``, foreign ones filtered out.

        The reconciliation compare set. ``get_open_orders`` returns *every*
        order on the symbol, ours and everyone else's; an implementation must
        return only those it can recognise as its own, and must recognise them
        by a test at least as narrow as parsing a generated identifier -- a raw
        prefix test admits a human's order that merely starts the same way.

        **Returns orders, not parsed identities.** The parsed form belongs to
        the adapter layer that generates the identifiers, and this port lives in
        ``core``, which does not import outward. A caller needing the decomposed
        identity re-parses the ``client_order_id`` carried on each order.

        **``timeout_s`` and ``attempts`` bound one call, and ``None`` means the
        implementation's own policy.** They sit on the port rather than on the
        adapter alone because a caller on a deadline must be able to bound this
        THROUGH the abstraction; a port narrower than its implementation would
        force that caller to reach past it, which defeats the port.

        **Both are supplied today, by the reconciliation driver.**
        ``ReconciliationBudget.from_config`` derives ``timeout_s`` from
        ``risk.reconcile_deadline_s`` and forces ``attempts`` to 1;
        ``ReconciliationDriver`` hands the pair to ``reconcile_open_positions``,
        which passes them straight to this method. So a caller reading this
        signature is reading a channel that is in use rather than reserved.

        Declaring a transport bound on a domain port is a transport concern
        crossing inward, and is coherent here only because this project already
        treats budgets as domain policy: ``dispatch_deadline_s`` and
        ``reconcile_deadline_s`` live in the risk config, not the exchange one.
        """
        ...

    @abstractmethod
    async def get_order(
        self,
        symbol: str,
        *,
        order_id: str | None = None,
        client_order_id: str | None = None,
        timeout_s: float | None = None,
        attempts: int | None = None,
    ) -> Order:
        """One order by the venue's id or by ours. Exactly one identifier.

        **A POINT QUERY IS A DIFFERENT INSTRUMENT FROM ENUMERATION**, and a
        reconciler needs both. MEASURED: immediately after a cancel,
        ``get_own_open_orders`` returned nothing while this endpoint still
        reported the order as ``CANCELED``. Absence from an enumeration says
        only "it does not rest"; never-placed, cancelled and filled are
        indistinguishable from there, and only this separates them.

        ``timeout_s`` and ``attempts`` bound one call, as on
        :meth:`get_own_open_orders`.

        :raises ValueError: neither identifier given, or both.
        :raises OrderNotFoundError: the venue has no such order -- which is an
            ANSWER, not a failure, and callers are expected to act on it.
        """
        ...

    @abstractmethod
    async def get_all_order_lists(
        self,
        *,
        timeout_s: float | None = None,
        attempts: int | None = None,
    ) -> list[OrderList]:
        """Every order list on the account, live and terminal, with its status.

        **ENUMERATION RATHER THAN A POINT QUERY, and the reason is an ambiguity
        rather than a preference.** A point query by our own client order id has
        an undefined answer once that id has been used twice, and generation-0
        ids repeat within a single dispatch by construction, because the id
        derives from ``(symbol, entry_bar_time)``. Enumerating returns every
        candidate and lets the caller reason about the SET.

        **The set can genuinely hold more than one, MEASURED.** A Testnet census
        found 14 lists carrying 12 distinct ``listClientOrderId`` values, with
        one id mapping to THREE lists. A caller that keys a mapping on that id
        silently discards the others.

        ``timeout_s`` and ``attempts`` bound one call, as on
        :meth:`get_own_open_orders`, and ``None`` means the implementation's own
        policy.

        This is a READ. It cannot create, amend or cancel anything.
        """
        ...

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
    def generate_signal(
        self, symbol: str, candles: pd.DataFrame, *, last_candle: Candle
    ) -> Signal | None:
        """Return a :class:`Signal` for the latest candle, or ``None`` to skip.

        ``candles`` is time-ordered OHLCV with a ``DatetimeIndex``, in
        ``float64`` -- the right shape for indicator maths and the wrong shape
        for money.

        ``last_candle`` is that same final bar with ``Decimal`` precision
        intact, and is the **only** admissible source for ``Signal.price`` and
        ``Signal.timestamp``. Rebuilding a price from the frame would round-trip
        a money value through a binary float, undoing the precision the data
        layer deliberately preserves. The ``Money`` field type rejects that
        outright -- ``Signal(price=65050.1)`` raises rather than silently
        coercing -- so handing the strategy the authoritative candle is what
        makes the correct thing also the easy one.

        Taking the whole candle rather than just its close also lets the
        strategy stamp the signal with the bar's ``close_time``. Without it
        ``Signal.timestamp`` falls back to wall-clock now, which is roughly
        right when live and completely wrong in a backtest.
        """


class RiskManager(ABC):
    """Vets signals and sizes positions against configured limits."""

    @abstractmethod
    def size_position(
        self,
        signal: Signal,
        *,
        equity: Decimal,
        price: Decimal,
        stop_price: Decimal | None = None,
    ) -> SizingDecision:
        """Return how much of ``signal.symbol`` to trade, or why nothing will be.

        ``equity`` is **total portfolio value in the quote currency** -- free
        quote balance plus the mark-to-market value of open positions -- not
        free balance alone. The distinction is the difference between "2% of
        equity per position" meaning a stable size and meaning one that shrinks
        as capital deploys. A caller must therefore *separately* confirm that
        free balance covers the resulting order.

        ``price`` is the entry reference, normally ``signal.price``, which is an
        exact ``Decimal`` taken from the closed candle the signal was computed
        on. ``stop_price`` is required only by the ``risk_per_trade`` method,
        which sizes from the distance between entry and stop.

        Returning a :class:`~trading_bot.core.models.SizingDecision` rather than
        a bare quantity is deliberate: "the account is too small for this
        symbol" is a routine outcome that must carry its reason to the operator,
        not an exception and not a silent zero.
        """

    @abstractmethod
    def evaluate(self, signal: Signal, *, portfolio: Portfolio) -> RiskAssessment:
        """Turn ``signal`` into an intent to trade, or into the reason there is none.

        The composed path: preconditions, equity, the limits, the ATR bridge,
        protective levels, sizing and affordability. Every refusal is a returned
        value naming the
        :class:`~trading_bot.core.enums.RefusalStage` it stopped at; nothing on
        this path raises for a market condition.

        **This is the only entry point.** A ``approve``-shaped method that
        checked the limits alone used to sit beside it, and it could approve an
        entry whose committed risk was unknown -- forward risk that cannot be
        priced tells the daily-loss check that an unprotected position carries
        none, which is the inverse of the truth. It is gone rather than guarded,
        so the guarantee is a property of this port's shape: only one method
        here takes a ``Portfolio``, and it refuses.

        ``portfolio`` is **read, never mutated**: recording an entry or an exit
        belongs to whoever actually places the order.

        **Not a pure function of its arguments.** Marks come from an injected
        market-data collaborator, not from ``portfolio``, so equity and
        committed risk are computed against whatever bar has most recently
        closed. The same signal and the same portfolio can evaluate differently
        on two bars, and that is the intended behaviour rather than a caveat.

        The **limits** vet entries only. A ``CLOSE`` is routed to an exit before
        any limit is consulted: an exit must always be permitted, because a
        limit that could trap an open position would be a risk rule that creates
        risk.
        """


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
