"""Mode wiring -- the composition root for a live exchange connection.

:func:`live_system` assembles the collaborators the LIVE/TESTNET path needs --
REST client, per-pair exchange filters, portfolio, market-data provider, engine,
risk manager and :class:`IntentLogger` -- hands them back as a frozen
:class:`LiveSystem`, and tears them down in the reverse order. It is the only
place in ``src/`` that knows how the pieces fit together, which is what keeps
``live_engine`` mode-agnostic.

Nothing here dispatches an order. :class:`IntentLogger` is the terminal
collaborator and it *logs*; it is deliberately not called ``Executor`` and does
not live in ``execution/``, because claiming that stub would make the stub
inventory lie about what exists.

Not re-exported from ``trading_bot.engine``
-------------------------------------------
``engine/__init__.py`` names ``live_engine`` only. Importing this module pulls
in pandas, NumPy and (on the un-injected path) ``python-binance``/``aiohttp``,
so re-exporting it would put the whole data stack on the import path of anything
that merely wants the engine's types. ``main.py`` imports it deferred, exactly
as it already defers ``live_engine``.

LIVE and TESTNET only -- and why that is a refusal, not a prohibition
---------------------------------------------------------------------
:func:`live_system` refuses a mode for which ``is_live_connection`` is false.
That is a statement about what has been *built*, not about what is allowed:
``paper`` needs ``paper/simulator.py`` and ``backtest`` needs
``backtesting/engine.py``, and both are still docstring-only stubs. There is no
composition root for them yet, so the honest failure is an immediate
:class:`~trading_bot.core.exceptions.ConfigError` naming the missing piece,
rather than a signed REST call failing several steps later with an exchange
error code that says nothing about the real cause.

Boot order: all I/O before any socket exists
--------------------------------------------
0. Mode check -- pure, and before the client exists at all.
1. REST client (injected, or built from settings).
2. Pair contexts -- the *pure* duplicate-symbol check first, so a config
   mistake costs no network round trip, then one ``get_symbol_info`` per
   distinct symbol.
3. Portfolio, seeded from ``get_balances``.
4. Unmanaged base holdings -- a second ``get_balances``, then one
   ``get_ticker`` per candidate asset. Warns; never refuses.
5. Market-data provider (this is the first step that can open a WebSocket).
6. Engine, 7. risk manager, 8. intent logger, 9. the one signal handler,
   10. the reconciliation driver, subscribed to candles.

Step 10 registers on ``provider.on_candle`` **before this function yields**, and
``TradingEngine.start`` registers its own candle hook only when ``run()`` is
called afterwards. Since ``_notify`` fans out in registration order, the
reconciler is always subscriber zero -- **reconcile, then decide** -- so the
same bar's ``evaluate`` reads a ledger this pass has just refreshed, and the
reserved reconciliation floor is spent before anything else on the bar. That
ordering is a consequence of *where* the two registrations happen, so it is
pinned by tests rather than by a comment alone.

Steps 0 to 3 are the fail-fast: every boot refusal is raised there, before the
first socket at step 5, so a refusal has exactly one REST client to unwind and
never a half-open feed. Step 4 is the exception that proves the shape -- it is
I/O on the same side of the socket, and it only warns.

**There are FIVE boot refusals, and they are not homogeneous** -- which is why
they were documented as four until M5b's rotation. Four raise ``ConfigError``
here: a mode with no composition root, an empty enabled-pair set, a duplicate
symbol on two timeframes, and a quote asset the account does not hold. The fifth
is a symbol the exchange does not know, which **propagates** out of
``get_symbol_info`` inside :func:`_prime_pairs` rather than being raised by this
module. Counting the ``raise ConfigError`` sites therefore finds four and misses
the one that is a refusal this file does not write.

Ownership: this root closes the client unconditionally
------------------------------------------------------
``BufferedMarketDataProvider`` closes a client only when it built one itself
(``owns_client = client is None``), because an injected client belongs to its
caller. This root is that caller, and it has no caller of its own -- so it
closes what it hands over, injected or not. That inverts the convention
deliberately: without it an injected client is closed by nobody, on the success
path *and* on the path where the stream fails to build. ``close()`` is
idempotent, and it has to be already -- ``AsyncClient.create`` calls
``close_connection()`` in its own ``except`` before re-raising.

Teardown is nested, not one ``finally``
---------------------------------------
Three scopes, each opened immediately after the object it releases is bound:
client -> provider -> engine. A single ``finally`` naming ``engine`` would raise
``UnboundLocalError`` when the boot fails at step 2, 3 or 4, masking the real
error with a bookkeeping one. Nesting also makes the ordering structural rather
than remembered: the engine stops (which stops the provider, which stops the
stream) strictly before the client closes.

The portfolio is a boot snapshot
--------------------------------
It is built at step 3 and written once more at step 4, where
:func:`_snapshot_unmanaged_holdings` records the base the account already held.
After that **nothing mutates it** -- no fills, no realised P&L, no cooldowns,
because nothing places an order yet. Every evaluation for the life of the
process sees the balances the process started with. Execution is what makes it
a ledger; until then it is a photograph.

The log schema
--------------
Three events -- ``risk_refused``, ``intent_dispatched``, ``collaborator_failed``
-- with a fixed field set each. Absent fields are **absent, not null**. Money
crosses as ``Decimal`` (both sinks render it exactly). Enums cross as
``.value``: a ``str, Enum`` member reaches the JSON sink as its string value but
the text sink as ``str(member)`` -- ``"BUY"`` versus ``"SignalAction.BUY"`` --
so passing the member itself makes the two sinks disagree about the same field.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import TYPE_CHECKING

from trading_bot.core.assessment import EntryIntent
from trading_bot.core.exceptions import ConfigError
from trading_bot.core.interfaces import (
    ExchangeClient,
    MarketDataProvider,
    MarketDataStream,
    SignalHandler,
)
from trading_bot.core.portfolio import Portfolio
from trading_bot.engine.live_engine import TradingEngine
from trading_bot.execution.reconciliation_driver import (
    ReconciliationBudget,
    ReconciliationDriver,
)
from trading_bot.risk.manager import PairContext, RiskAssessment, RiskManager
from trading_bot.utils.helpers import utc_now
from trading_bot.utils.logger import get_logger

if TYPE_CHECKING:  # pragma: no cover - typing only
    from collections.abc import AsyncIterator, Mapping

    from trading_bot.config.settings import Settings
    from trading_bot.core.models import Signal

_log = get_logger(__name__)

__all__ = ["IntentLogger", "LiveSystem", "live_system"]

#: The three ``event`` values. One constant per event so a rename cannot leave
#: the emitter and its test disagreeing silently.
_EVENT_RISK_REFUSED = "risk_refused"
_EVENT_INTENT_DISPATCHED = "intent_dispatched"
_EVENT_COLLABORATOR_FAILED = "collaborator_failed"

#: Names used in ``collaborator`` on a ``collaborator_failed`` line.
_COLLABORATOR_RISK = "risk_manager"
_COLLABORATOR_INTENT_LOGGER = "intent_logger"


@dataclass(frozen=True, slots=True, eq=False)
class LiveSystem:
    """The assembled live collaborators, built and torn down by :func:`live_system`.

    A frozen dataclass rather than a pydantic model: every field is a live
    collaborator rather than a domain value, so validation would have nothing to
    validate and would need ``arbitrary_types_allowed`` to say so. ``eq=False``
    because identity is the only meaningful equality for stateful objects, and
    ``slots=True`` so a mistyped attribute raises instead of silently sticking.

    ``client`` and ``provider`` are typed as their ports so a scripted fake
    satisfies them. ``risk`` is the **concrete** :class:`RiskManager` even
    though ``evaluate`` is now on the port: the root builds the concrete object
    and hands it over, and widening this field's type would buy nothing the
    port does not already guarantee.
    """

    settings: Settings
    client: ExchangeClient
    provider: MarketDataProvider
    engine: TradingEngine
    risk: RiskManager
    portfolio: Portfolio
    pairs: Mapping[str, PairContext]
    intent_logger: IntentLogger
    reconciler: ReconciliationDriver


# --------------------------------------------------------------------------
# Observability
# --------------------------------------------------------------------------
#: Written into ``stage`` when a refusal reaches the logger without one. The
#: value is a fixed literal rather than a :class:`RefusalStage` member because
#: it is not a category of refusal -- it is this pipeline reporting on itself.
_STAGE_UNSET = "unset"


def _common_fields(signal: Signal, pairs: Mapping[str, PairContext]) -> dict[str, object]:
    """The fields every event carries, in schema order.

    ``timeframe`` is the one field that can be absent: ``Signal`` has no
    timeframe, so it is resolved through ``pairs`` -- and a signal refused for
    :attr:`~trading_bot.core.enums.RefusalStage.UNKNOWN_PAIR` is by definition
    not in ``pairs``. That resolution is single-valued only because a duplicate
    symbol refuses the boot (see :func:`_pair_timeframes`).

    ``action`` crosses as ``.value`` and ``signal_ts`` as an explicit
    ``isoformat()`` rather than leaning on the JSON sink's ``default=str``
    catch-all.
    """
    fields: dict[str, object] = {"symbol": signal.symbol}
    context = pairs.get(signal.symbol)
    if context is not None:
        fields["timeframe"] = context.timeframe
    fields["action"] = signal.action.value
    fields["signal_ts"] = signal.timestamp.isoformat()
    return fields


class IntentLogger:
    """Terminal collaborator: records the intent stream. Dispatches nothing.

    Owns the whole ``risk_refused`` / ``intent_dispatched`` schema, so a field
    name has exactly one definition and one test. The signal handler owns only
    ``collaborator_failed``, which cannot live here -- it has to survive this
    object being the thing that broke.
    """

    def __init__(self, *, pairs: Mapping[str, PairContext]) -> None:
        self._pairs = pairs

    async def record(self, signal: Signal, assessment: RiskAssessment) -> None:
        """Emit one line for ``assessment``: the intent, or the stage it died at."""
        intent = assessment.intent
        if intent is not None:
            # `approved` and `intent is not None` are equivalent by
            # RiskAssessment's validator; branching on the intent is what narrows
            # the Optional for the type checker without an assert.
            extra: dict[str, object] = {"event": _EVENT_INTENT_DISPATCHED}
            extra.update(_common_fields(signal, self._pairs))
            extra["side"] = intent.side.value
            extra["quantity"] = intent.quantity
            if isinstance(intent, EntryIntent):
                extra["order_type"] = "LIMIT"
                # `entry` is the price actually sent and `reference` the candle
                # close, so applied slippage is visible in one record rather
                # than inferred from two.
                extra["entry"] = intent.entry_limit
                extra["reference"] = intent.reference_price
                if intent.levels.stop_loss is not None:
                    extra["stop"] = intent.levels.stop_loss
                if intent.levels.take_profit is not None:
                    extra["take_profit"] = intent.levels.take_profit
            else:
                # No `entry`, no `reference`: "at what price" is genuinely
                # unknown until it fills, and a field that would have to lie is
                # omitted rather than nulled.
                extra["order_type"] = "MARKET"
            _log.info(
                "Intent %s %s %s",
                intent.side.value,
                intent.quantity,
                intent.symbol,
                extra=extra,
            )
            return

        # RiskAssessment's validator binds `stage` to `approved`, so a refusal
        # always carries one -- but that link is a runtime invariant and mypy
        # cannot derive it from `intent is None` above. Hence a real branch
        # rather than an assert.
        #
        # Deliberately logged, not raised, and NOT an `assert`. This method runs
        # inside the signal handler, which must never raise: an exception here
        # becomes an unstructured traceback once per bar forever, because the
        # engine's consecutive-failure counter is fed from _evaluate and never
        # from _emit. `assert` is doubly wrong -- it also vanishes under -O. The
        # state is unreachable through the domain; if it ever happens the
        # pipeline is broken, and the honest response is a loud line, not a
        # crash in the one component whose job is to report.
        stage = assessment.stage
        label = stage.value if stage is not None else _STAGE_UNSET
        level = logging.INFO if stage is not None else logging.ERROR

        extra = {"event": _EVENT_RISK_REFUSED}
        extra.update(_common_fields(signal, self._pairs))
        extra["stage"] = label
        decision = assessment.decision
        rule = decision.rule if decision is not None else None
        if rule is not None:
            extra["rule_fired"] = rule.value
        extra["reason"] = assessment.reason
        _log.log(level, "Risk refused %s at %s", signal.symbol, label, extra=extra)


def _log_collaborator_failure(
    collaborator: str, signal: Signal, exc: Exception, pairs: Mapping[str, PairContext]
) -> None:
    """Report a collaborator that raised, naming which one it was."""
    extra: dict[str, object] = {"event": _EVENT_COLLABORATOR_FAILED}
    extra.update(_common_fields(signal, pairs))
    extra["collaborator"] = collaborator
    extra["error_type"] = type(exc).__name__
    extra["error"] = str(exc)
    _log.exception(
        "Collaborator %s failed for %s; continuing", collaborator, signal.symbol, extra=extra
    )


def _build_signal_handler(
    *,
    risk: RiskManager,
    intent_logger: IntentLogger,
    portfolio: Portfolio,
    pairs: Mapping[str, PairContext],
) -> SignalHandler:
    """The one handler registered on the engine: the adapter, and the chain.

    ``SignalHandler`` is a coroutine taking only a signal, while
    ``RiskManager.evaluate`` is synchronous and needs a portfolio. This closure
    is that adapter, and the only place the boot-snapshot portfolio is supplied.

    **It must never raise.** ``TradingEngine._emit`` catches with a bare
    ``except Exception`` and ``_log.exception`` and no structured fields, so
    anything escaping here becomes an unstructured traceback -- once per bar,
    forever, because the engine's consecutive-failure counter is fed from
    ``_evaluate`` and never from ``_emit``, so no pair would ever be
    quarantined. Each collaborator therefore gets its own ``try``, and its own
    name in the log line.

    **Bounded I/O, not none.** Handlers are awaited sequentially from
    ``_on_candle``, itself awaited from the provider's ``_notify`` on the
    stream's dispatch task, so handler latency is charged directly to the
    candle pipeline. The rule is a budget, not an abstinence: the pipeline must
    never be blocked by latency we do not bound ourselves. This handler happens
    to perform no I/O because it has nothing to do yet -- the milestone that
    places orders adds it under a deadline it sets itself.
    """

    async def handle(signal: Signal) -> None:
        try:
            assessment = risk.evaluate(signal, portfolio=portfolio)
        except Exception as exc:  # the handler must never raise; see the docstring
            _log_collaborator_failure(_COLLABORATOR_RISK, signal, exc, pairs)
            return

        try:
            await intent_logger.record(signal, assessment)
        except Exception as exc:  # the handler must never raise; see the docstring
            _log_collaborator_failure(_COLLABORATOR_INTENT_LOGGER, signal, exc, pairs)

    return handle


# --------------------------------------------------------------------------
# Boot steps
# --------------------------------------------------------------------------
def _require_live_connection_mode(settings: Settings) -> None:
    """Refuse a mode that has no composition root yet.

    Not a prohibition -- a statement about what exists. ``paper`` needs
    ``paper/simulator.py`` and ``backtest`` needs ``backtesting/engine.py``, and
    both are docstring-only stubs today.
    """
    if settings.mode.is_live_connection:
        return
    raise ConfigError(
        f"No composition root exists for mode '{settings.mode.value}' yet. live_system "
        "assembles the LIVE/TESTNET collaborators (REST client, market-data feed, risk "
        f"manager); '{settings.mode.value}' needs a simulator that is still a stub "
        "(paper/simulator.py, backtesting/engine.py). Run with mode 'testnet' to "
        "exercise this path."
    )


def _pair_timeframes(settings: Settings) -> dict[str, str]:
    """Map each enabled symbol to its timeframe, refusing a duplicate symbol.

    ``RiskManager`` keys its pair contexts by **symbol alone**, with the
    timeframe inside the value, while the engine keys by ``(symbol, timeframe)``.
    Config permits the same symbol on two timeframes, so a plain dict
    comprehension would drop one -- last write wins, no error -- and the manager
    would then compute ATR for both engine pairs off whichever timeframe
    survived. Wrong stops, silently, on a green gate.

    An empty result is refused here too. ``TradingEngine.start`` already rejects
    it -- correctly, since a directly-constructed engine with no strategies is a
    programming error -- but it does so with a bare ``ValueError``, several steps
    later, after a REST client and a WebSocket are already open. ``ValueError``
    is not a :class:`~trading_bot.core.exceptions.TradingBotError`, so it escapes
    ``main``'s handler as a traceback rather than a message. Refusing at the root
    is the same answer delivered earlier, in the vocabulary the operator can act
    on: it names ``config.yaml``. That guard stays where it is; this one is not a
    replacement for it.

    Pure, and run before any network call, so a config mistake costs no round
    trip.
    """
    configured = settings.config.trading.pairs
    enabled = settings.config.trading.enabled_pairs
    if not enabled:
        # Worth distinguishing: "you wrote no pairs" and "you disabled the ones
        # you wrote" look identical from the engine but need opposite fixes, and
        # the second is the one an operator hits after toggling a pair off to
        # debug something and forgetting to toggle it back.
        detail = (
            f"all {len(configured)} configured pair(s) have enabled: false"
            if configured
            else "trading.pairs is empty"
        )
        raise ConfigError(
            f"No enabled trading pairs: {detail}. The bot would connect to the "
            "exchange, seed nothing, and sit silent. Add a pair under "
            "trading.pairs in config.yaml, or set enabled: true on one that is "
            "already there."
        )

    timeframes: dict[str, str] = {}
    for pair in enabled:
        existing = timeframes.get(pair.symbol)
        if existing is not None:
            raise ConfigError(
                f"{pair.symbol} is enabled on two timeframes ({existing} and "
                f"{pair.timeframe}). The risk manager keys its pair context by symbol "
                "alone, so one would silently displace the other and both engine pairs "
                "would size and stop off a single timeframe's ATR. Enable one timeframe "
                f"per symbol in config.yaml, or remove one of the {pair.symbol} entries."
            )
        timeframes[pair.symbol] = pair.timeframe
    return timeframes


async def _prime_pairs(
    client: ExchangeClient, timeframes: Mapping[str, str]
) -> dict[str, PairContext]:
    """Fetch exchange filters for every distinct symbol, once each.

    One round trip per **symbol**, not per pair: ``get_symbol_info`` is memoised
    per client instance on a symbol key. A symbol the exchange does not know
    raises here, at boot, rather than on the first signal hours later.
    """
    pairs: dict[str, PairContext] = {}
    for symbol, timeframe in timeframes.items():
        symbol_info = await client.get_symbol_info(symbol)
        pairs[symbol] = PairContext(timeframe=timeframe, symbol_info=symbol_info)
    return pairs


async def _seed_portfolio(client: ExchangeClient, *, quote_asset: str) -> Portfolio:
    """Build the boot-snapshot portfolio from the account's quote balance.

    From the exchange, never from config: both ``initial_balance`` fields are
    ``float`` *and* belong to backtest/paper, so that route is dead twice over.
    ``Balance.free`` is already ``Money``, parsed from the wire string with
    ``Decimal(str(...))``, so this opens no new float boundary.

    Both sides are upper-cased before matching. ``trading.base_currency`` carries
    no validator while ``PairConfig.symbol`` twelve lines above it does, and
    nothing read ``base_currency`` at all until this function; normalising here
    means this code is correct standing alone. The **normalised** form is what
    lands on the portfolio, because it is interpolated into refusal messages and
    future code will compare against it.

    ``get_balances`` returns every asset including zero balances, so an absent
    entry means genuinely absent -- a configured quote asset the account does not
    hold -- and refuses the boot. A zero balance is a valid, non-refusing state.
    """
    normalised = quote_asset.upper()
    balances = await client.get_balances()
    for balance in balances:
        if balance.asset.upper() == normalised:
            return Portfolio(quote_asset=normalised, free_quote=balance.free)
    raise ConfigError(
        f"trading.base_currency is {quote_asset!r} but the account reports no "
        f"{normalised} balance entry. get_balances() returns every asset, including "
        "zero balances, so an absent entry means the exchange does not recognise "
        "this asset for this account -- check base_currency in config.yaml against "
        "the environment the credentials belong to."
    )


async def _snapshot_unmanaged_holdings(
    client: ExchangeClient, *, pairs: Mapping[str, PairContext], portfolio: Portfolio
) -> None:
    """Record material base holdings the account had before this bot started.

    **Counted toward equity, never adopted as positions.** Adopting would give
    a holding no entry price, no stop and no requested protection -- the
    terminal stopless state, manufactured at every boot -- and would eventually
    have the bot sell an asset a human bought. Ignoring them is worse:
    ``has_position`` would be ``False`` whatever the account holds, so a ``BUY``
    would pass ``ALREADY_IN_POSITION`` and pyramid onto the holding, sized
    against an equity that excludes the thing it is adding to.

    **Priced over REST, deliberately.** The provider exists to serve the live
    path and its buffers are empty until ``start()``, which runs after the
    composition root has yielded -- so ``last_candle`` has nothing at boot. One
    read-only ticker per candidate asset costs a round trip and keeps this
    entire step ahead of any socket, which is where the other four boot
    refusals live.

    **Taken before any ``Position`` exists, and that timing is the argument.**
    Measuring unmanaged base later would count base held by positions the bot
    opened: ``equity`` would double-count it and the refusal would mislabel,
    reporting an unmanaged holding where the truth is ``ALREADY_IN_POSITION``.

    ``total`` and ``free`` answer different questions and both are used.
    Equity asks what the account **owns**, so the recorded quantity is ``total``
    -- locked base is owned, and excluding it understates the denominator every
    sizing decision divides by. Materiality asks whether this is **dust**, and
    dust is defined by sellability: a holding worth less than ``min_notional``
    cannot be sold at all. Locked base is not sellable, so only ``free`` counts
    toward clearing that threshold. The asymmetry is safe both ways -- a holding
    whose free portion is dust does not block the symbol, which is right,
    because the locked portion is committed to somebody else's resting order.
    """
    quote = portfolio.quote_asset
    # Base asset -> the symbol that prices it, restricted to pairs quoted in the
    # portfolio's currency: a BTCEUR pair cannot value a BTC holding for a
    # USDT-denominated account. Two enabled pairs sharing a base asset *and* the
    # quote asset would let the last one win here; the exchange does not offer
    # such a duplicate, and `_pair_timeframes` already refuses duplicate symbols.
    by_base = {
        context.symbol_info.base_asset: symbol
        for symbol, context in pairs.items()
        if context.symbol_info.quote_asset == quote
    }

    for balance in await client.get_balances():
        asset = balance.asset.upper()
        # The quote asset is already `free_quote`; counting it here would
        # double it into equity outright.
        if asset == quote or balance.total <= 0:
            continue

        symbol = by_base.get(asset)
        if symbol is None:
            _log.warning(
                "%s: holding of %s is EXCLUDED FROM EQUITY -- no enabled %s pair, so it "
                "cannot be priced. Equity is understated by its value.",
                asset,
                balance.total,
                quote,
            )
            continue

        price = (await client.get_ticker(symbol)).last
        if balance.free * price < pairs[symbol].symbol_info.min_notional:
            continue  # dust: too small to sell, so it must not block the pair

        portfolio.unmanaged_holdings[symbol] = balance.total
        # WARNING, once, at boot -- never CRITICAL. This is an ordinary state of
        # a shared account and will be true on many boots; escalating it would
        # train an operator to skim the level that carries the one condition
        # nothing can resolve.
        _log.warning(
            "%s: the account held %s %s at boot that this bot did not open. It is counted "
            "toward equity and THE BOT WILL NOT TRADE OR SELL IT. Entries on %s are "
            "excluded while it remains.",
            symbol,
            balance.total,
            asset,
            symbol,
        )


# --------------------------------------------------------------------------
# The root
# --------------------------------------------------------------------------
@asynccontextmanager
async def live_system(
    settings: Settings,
    *,
    client: ExchangeClient | None = None,
    stream: MarketDataStream | None = None,
) -> AsyncIterator[LiveSystem]:
    """Assemble the live collaborators, yield them, and tear them down.

    ``client`` and ``stream`` inject pre-built **leaf adapters**, which is what
    makes this path testable without a network. They are deliberately the only
    two seams: injecting a whole *provider* would skip the step that wires the
    provider to the client, and that step is precisely what the ownership
    behaviour depends on. Replacing a leaf keeps the boot path under test
    identical to the one production takes.

    Whatever is injected is still closed here -- see the module docstring on
    ownership.
    """
    _require_live_connection_mode(settings)

    # Imported lazily, mirroring BufferedMarketDataProvider.create: keeps
    # python-binance and aiohttp off the import path when a fake client is
    # injected, and off it entirely for anything that only imports this module's
    # types.
    from trading_bot.data.market_data import BufferedMarketDataProvider
    from trading_bot.exchange.binance_client import BinanceClient

    resolved_client = client if client is not None else await BinanceClient.create(settings)
    try:
        timeframes = _pair_timeframes(settings)
        pairs = await _prime_pairs(resolved_client, timeframes)
        portfolio = await _seed_portfolio(
            resolved_client, quote_asset=settings.config.trading.base_currency
        )
        # Still before any socket, with the other four boot refusals.
        await _snapshot_unmanaged_holdings(resolved_client, pairs=pairs, portfolio=portfolio)

        provider = await BufferedMarketDataProvider.create(
            settings, client=resolved_client, stream=stream
        )
        try:
            engine = await TradingEngine.create(settings, provider=provider)
            try:
                risk = RiskManager(
                    config=settings.config.risk,
                    provider=provider,
                    pairs=pairs,
                    clock=utc_now,
                )
                intent_logger = IntentLogger(pairs=pairs)
                engine.on_signal(
                    _build_signal_handler(
                        risk=risk,
                        intent_logger=intent_logger,
                        portfolio=portfolio,
                        pairs=pairs,
                    )
                )
                # RECONCILE, THEN DECIDE -- and the ordering is structural
                # rather than remembered. `_notify` runs candle subscribers in
                # registration order, and the engine registers its own hook
                # inside `start()`, which runs only after this context manager
                # has yielded. So the reconciler is always subscriber zero:
                # the same bar's `evaluate` reads a ledger this pass has just
                # refreshed, and the reserved reconciliation floor is spent
                # before any dispatch could compete for it.
                reconciler = ReconciliationDriver(
                    portfolio=portfolio,
                    client=resolved_client,
                    budget=ReconciliationBudget.from_config(settings.config, timeframes=timeframes),
                )
                provider.on_candle(reconciler)
                _log.info(
                    "Composition root ready: %d pair(s), %s %s free",
                    len(pairs),
                    portfolio.free_quote,
                    portfolio.quote_asset,
                )
                yield LiveSystem(
                    settings=settings,
                    client=resolved_client,
                    provider=provider,
                    engine=engine,
                    risk=risk,
                    portfolio=portfolio,
                    pairs=pairs,
                    intent_logger=intent_logger,
                    reconciler=reconciler,
                )
            finally:
                await engine.stop()
        finally:
            # Covers the narrow window in which the provider exists but the
            # engine does not: TradingEngine.create can still raise on a bad
            # strategy name, and the provider's stream owns a second AsyncClient
            # that nothing else would close. Safe to reach twice -- every stop()
            # on this path is documented idempotent.
            await provider.stop()
    finally:
        await resolved_client.close()
