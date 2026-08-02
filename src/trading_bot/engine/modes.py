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
1. REST client (injected, or built from settings).
2. Pair contexts -- the *pure* duplicate-symbol check first, so a config
   mistake costs no network round trip, then one ``get_symbol_info`` per
   distinct symbol.
3. Portfolio, seeded from ``get_balances``.
4. Market-data provider (this is the first step that can open a WebSocket).
5. Engine, 6. risk manager, 7. intent logger, 8. the one signal handler.

Steps 2 and 3 are the fail-fast: everything that can refuse the boot does so
before step 4, so a refusal has exactly one REST client to unwind and never a
half-open feed.

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
It is read once, at step 3, and **nothing mutates it in M4a** -- no fills, no
realised P&L, no cooldowns, because nothing places an order yet. Every
evaluation for the life of the process sees the balances the process started
with. Execution is what makes it a ledger; until then it is a photograph.

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
from enum import Enum
from typing import TYPE_CHECKING

from trading_bot.core.enums import RiskRule, SignalAction
from trading_bot.core.exceptions import ConfigError
from trading_bot.core.interfaces import (
    ExchangeClient,
    MarketDataProvider,
    MarketDataStream,
    SignalHandler,
)
from trading_bot.core.portfolio import Portfolio
from trading_bot.engine.live_engine import TradingEngine
from trading_bot.risk.manager import PairContext, RiskAssessment, RiskManager
from trading_bot.utils.helpers import utc_now
from trading_bot.utils.logger import get_logger

if TYPE_CHECKING:  # pragma: no cover - typing only
    from collections.abc import AsyncIterator, Mapping

    from trading_bot.config.settings import Settings
    from trading_bot.core.models import Signal

_log = get_logger(__name__)

__all__ = ["IntentLogger", "LiveSystem", "RefusalStage", "live_system"]

#: The three ``event`` values. One constant per event so a rename cannot leave
#: the emitter and its test disagreeing silently.
_EVENT_RISK_REFUSED = "risk_refused"
_EVENT_INTENT_DISPATCHED = "intent_dispatched"
_EVENT_COLLABORATOR_FAILED = "collaborator_failed"

#: Names used in ``collaborator`` on a ``collaborator_failed`` line.
_COLLABORATOR_RISK = "risk_manager"
_COLLABORATOR_INTENT_LOGGER = "intent_logger"


class RefusalStage(str, Enum):
    """Where in ``RiskManager.evaluate`` a signal stopped.

    One value per refusal path, in the order ``evaluate`` reaches them. The
    label is derived by :func:`_refusal_stage` rather than reported by the
    manager, because the manager has no stage vocabulary yet -- choosing one
    before an operator has read any of these lines would be designing the enum
    backwards. M4b moves it inward as ``RiskAssessment.stage`` and this ladder
    collapses to reading that field.

    :attr:`UNCLASSIFIED` is a **defect signal, not a category.** It can only be
    reached if :func:`_refusal_stage` has desynchronised from ``evaluate`` -- a
    new refusal path, or two checks reordered. It is therefore logged at
    ``ERROR`` while ordinary refusals log at ``INFO``: an operator seeing it has
    found a bug in this module, not a market condition.
    """

    UNKNOWN_PAIR = "unknown_pair"
    NO_REFERENCE_PRICE = "no_reference_price"
    NOTHING_TO_CLOSE = "nothing_to_close"
    UNSUPPORTED_ACTION = "unsupported_action"
    NO_MARK_PRICE = "no_mark_price"
    LIMIT_REFUSED = "limit_refused"
    ATR_UNAVAILABLE = "atr_unavailable"
    STOP_UNPLACEABLE = "stop_unplaceable"
    SIZE_NOT_TRADEABLE = "size_not_tradeable"
    UNAFFORDABLE = "unaffordable"
    UNCLASSIFIED = "unclassified"


@dataclass(frozen=True, slots=True, eq=False)
class LiveSystem:
    """The assembled live collaborators, built and torn down by :func:`live_system`.

    A frozen dataclass rather than a pydantic model: every field is a live
    collaborator rather than a domain value, so validation would have nothing to
    validate and would need ``arbitrary_types_allowed`` to say so. ``eq=False``
    because identity is the only meaningful equality for stateful objects, and
    ``slots=True`` so a mistyped attribute raises instead of silently sticking.

    ``client`` and ``provider`` are typed as their ports so a scripted fake
    satisfies them. ``risk`` is the **concrete** :class:`RiskManager`: the port
    of that name declares only ``size_position`` and ``approve``, while
    ``evaluate`` -- the composed path this milestone exists to observe -- is
    class-only. Widening the port is M5's business, not this milestone's.
    """

    settings: Settings
    client: ExchangeClient
    provider: MarketDataProvider
    engine: TradingEngine
    risk: RiskManager
    portfolio: Portfolio
    pairs: Mapping[str, PairContext]
    intent_logger: IntentLogger


# --------------------------------------------------------------------------
# Observability
# --------------------------------------------------------------------------
def _refusal_stage(
    signal: Signal, assessment: RiskAssessment, *, pairs: Mapping[str, PairContext]
) -> RefusalStage:
    """Which of ``evaluate``'s refusal paths produced ``assessment``.

    Pure and **total**: it never raises and always returns a value, because it
    runs inside a signal handler that must not raise.

    The order below mirrors ``RiskManager.evaluate``'s own control flow and is
    not free to change. ``evaluate`` checks the pair context before the price and
    both before dispatching a ``CLOSE``, so a ``CLOSE`` for an unknown symbol is
    :attr:`RefusalStage.UNKNOWN_PAIR` rather than
    :attr:`RefusalStage.NOTHING_TO_CLOSE`; reordering these two lines would
    mislabel it with no test failing anywhere else.

    Four refusals carry no components at all -- unknown pair, unusable price,
    ``SELL``, and nothing-to-close all produce ``decision``/``levels``/``sizing``
    of ``None`` -- so they are separated by the ``Signal`` itself plus the
    ``pairs`` mapping this root built, never by parsing ``reason``.

    The last three are separated by which component evaluation reached:
    ``levels is None`` means it stopped at the ATR bridge, ``sizing is None``
    means it stopped at the stop gate, and past both, ``sizing.is_tradeable``
    is a guard-derived invariant -- the affordability check at the end of
    ``evaluate`` is reachable only after the sizer's own guard has passed.
    """
    if signal.symbol not in pairs:
        return RefusalStage.UNKNOWN_PAIR

    price = signal.price
    if price is None or price <= 0:
        return RefusalStage.NO_REFERENCE_PRICE

    if signal.action is SignalAction.CLOSE:
        return RefusalStage.NOTHING_TO_CLOSE
    if signal.action is not SignalAction.BUY:
        return RefusalStage.UNSUPPORTED_ACTION

    decision = assessment.decision
    if decision is None:
        # Unreachable: every refusal past this point carries a decision. Kept so
        # the function stays total, and loud (see RefusalStage.UNCLASSIFIED).
        return RefusalStage.UNCLASSIFIED
    if decision.rule is RiskRule.NO_MARK_PRICE:
        return RefusalStage.NO_MARK_PRICE
    if not decision.approved:
        return RefusalStage.LIMIT_REFUSED

    if assessment.levels is None:
        return RefusalStage.ATR_UNAVAILABLE
    sizing = assessment.sizing
    if sizing is None:
        return RefusalStage.STOP_UNPLACEABLE
    if not sizing.is_tradeable:
        return RefusalStage.SIZE_NOT_TRADEABLE
    return RefusalStage.UNAFFORDABLE


def _common_fields(signal: Signal, pairs: Mapping[str, PairContext]) -> dict[str, object]:
    """The fields every event carries, in schema order.

    ``timeframe`` is the one field that can be absent: ``Signal`` has no
    timeframe, so it is resolved through ``pairs`` -- and a signal refused for
    :attr:`RefusalStage.UNKNOWN_PAIR` is by definition not in ``pairs``. That
    resolution is single-valued only because a duplicate symbol refuses the boot
    (see :func:`_pair_timeframes`).

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
            extra["entry"] = intent.price
            levels = intent.levels
            if levels is not None:
                if levels.stop_loss is not None:
                    extra["stop"] = levels.stop_loss
                if levels.take_profit is not None:
                    extra["take_profit"] = levels.take_profit
            _log.info(
                "Intent %s %s %s @ %s",
                intent.side.value,
                intent.quantity,
                intent.symbol,
                intent.price,
                extra=extra,
            )
            return

        stage = _refusal_stage(signal, assessment, pairs=self._pairs)
        extra = {"event": _EVENT_RISK_REFUSED}
        extra.update(_common_fields(signal, self._pairs))
        extra["stage"] = stage.value
        decision = assessment.decision
        rule = decision.rule if decision is not None else None
        if rule is not None:
            extra["rule_fired"] = rule.value
        extra["reason"] = assessment.reason
        # UNCLASSIFIED means this module has drifted from evaluate(), not that
        # the market said no. It is the one refusal worth waking someone for.
        level = logging.ERROR if stage is RefusalStage.UNCLASSIFIED else logging.INFO
        _log.log(level, "Risk refused %s at %s", signal.symbol, stage.value, extra=extra)


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

    **No I/O.** Handlers are awaited sequentially from ``_on_candle``, so
    anything slow here delays the candle pipeline itself.
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
