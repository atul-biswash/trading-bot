"""Mode wiring -- the composition root for a live exchange connection.

:func:`live_system` assembles the collaborators the LIVE/TESTNET path needs --
REST client, per-pair exchange filters, portfolio, market-data provider, engine,
risk manager and :class:`IntentLogger` -- hands them back as a frozen
:class:`LiveSystem`, and tears them down in the reverse order. It is the only
place in ``src/`` that knows how the pieces fit together, which is what keeps
``live_engine`` mode-agnostic.

**This root dispatches orders.** The signal chain is :class:`IntentLogger`
THEN :class:`~trading_bot.execution.executor.OrderExecutor`: the executor was
chained AFTER the logger rather than replacing it, so every ``risk_refused``
and ``intent_dispatched`` record survives -- including for the signals the
executor then refuses to dispatch. The two answer different questions, what the
risk layer decided and what execution did about it.

The executor is also a CANDLE subscriber, registered after the reconciler and
before the engine's own hook, so each bar runs reconcile, then resolve any
ambiguous placement, then decide.

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
3. One ``get_balances``, shared by steps 3a and 4 -- two reads could disagree
   if a balance moved between them.
3a. Portfolio, seeded from that snapshot.
4. Unmanaged base holdings, from the same snapshot, then one ``get_ticker``
   per candidate asset. Warns; never refuses.
5. Market-data provider (this is the first step that can open a WebSocket).
6. Engine, 7. risk manager, 8. intent logger, 9. the executor,
   10. the one signal handler, 11. the reconciliation driver and 12. the
   executor, both subscribed to candles in that order.

Steps 11 and 12 register on ``provider.on_candle`` **before this function
yields**, and ``TradingEngine.start`` registers its own candle hook only when
``run()`` is called afterwards. Since ``_notify`` fans out in registration
order, the reconciler is always subscriber ZERO and the executor subscriber ONE
-- **reconcile, resolve, then decide** -- so the same bar's ``evaluate`` reads a
ledger this pass has just refreshed, any ambiguous placement from the previous
bar is settled out of THIS bar's fresh budget before a new one can be sent, and
the reserved reconciliation floor is spent before anything else on the bar. That
ordering is a consequence of *where* the registrations happen, so it is pinned
by tests rather than by a comment alone.

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
**The executor mutates it once a placement lands.** Recording a
:class:`~trading_bot.core.models.Position` also debits its cost from
``free_quote``, so this is a ledger rather than a photograph. Realised P&L and
cooldowns still do not move it -- nothing closes a position yet -- so what the
boot snapshot supplies is the STARTING balance, not the running one.

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
from contextlib import ExitStack, asynccontextmanager
from dataclasses import dataclass
from typing import TYPE_CHECKING

from trading_bot.core.assessment import EntryIntent
from trading_bot.core.exceptions import ConfigError, TradingBotError
from trading_bot.core.interfaces import (
    ExchangeClient,
    MarketDataProvider,
    MarketDataStream,
    SignalHandler,
)
from trading_bot.core.portfolio import Portfolio
from trading_bot.engine.live_engine import TradingEngine
from trading_bot.exchange.ids import parse_list_client_order_id
from trading_bot.execution.dispatch_budget import DispatchBudget
from trading_bot.execution.executor import OrderExecutor, PendingPlacement
from trading_bot.execution.reconciliation_driver import (
    ReconciliationBudget,
    ReconciliationDriver,
)
from trading_bot.persistence import store
from trading_bot.risk.manager import PairContext, RiskAssessment, RiskManager
from trading_bot.utils.helpers import utc_now
from trading_bot.utils.instance_lock import acquire as acquire_instance_lock
from trading_bot.utils.logger import get_logger

if TYPE_CHECKING:  # pragma: no cover - typing only
    from collections.abc import AsyncIterator, Mapping, Sequence

    from trading_bot.config.settings import Settings
    from trading_bot.core.models import Balance, Candle, Signal

_log = get_logger(__name__)

__all__ = ["IntentLogger", "LiveSystem", "live_system"]

#: The three ``event`` values. One constant per event so a rename cannot leave
#: the emitter and its test disagreeing silently.
#: The boot-time order-list scan's two events. Its own names rather than reusing
#: a refusal event: this fires once at boot, before any signal exists, and an
#: operator filtering for `risk_refused` is looking at a different moment.
_EVENT_BOOT_BLOCKED = "boot_symbol_blocked"
_EVENT_BOOT_FOREIGN_SYMBOL = "boot_live_list_unconfigured_symbol"
#: The excluded-holdings SUMMARY, emitted once per boot and only when non-empty.
#: It has an event name where the per-asset lines it replaced had none, because
#: the whole point of collapsing them is that this one is machine-findable.
_EVENT_BOOT_EXCLUDED = "boot_assets_excluded"

_EVENT_RISK_REFUSED = "risk_refused"
_EVENT_INTENT_DISPATCHED = "intent_dispatched"
_EVENT_COLLABORATOR_FAILED = "collaborator_failed"

#: Names used in ``collaborator`` on a ``collaborator_failed`` line.
_COLLABORATOR_RISK = "risk_manager"
_COLLABORATOR_INTENT_LOGGER = "intent_logger"
_COLLABORATOR_EXECUTOR = "order_executor"


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
    executor: OrderExecutor


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
    """Records the intent stream. Dispatches nothing, and is no longer last.

    **The executor is chained after this**, so "terminal collaborator" -- which
    this docstring said until the executor landed -- is now false. What remains
    true is the half that matters here: this object performs no venue I/O and
    decides nothing, it records.

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
    executor: OrderExecutor | None = None,
) -> SignalHandler:
    """The one handler registered on the engine: the adapter, and the chain.

    **The executor CHAINS AFTER the intent logger; it does not replace it.**
    The logger owns the whole ``risk_refused`` / ``intent_dispatched`` schema
    and records every assessment, approved or not -- including the ones the
    executor then refuses to dispatch. Replacing it would delete the only
    record of a refused signal, and the two answer different questions: what
    the risk layer decided, and what execution did about it. ``executor`` is
    optional so a caller that wants the decision path without dispatch -- every
    test of this chain that predates the executor -- gets exactly the old
    behaviour.

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
    never be blocked by latency we do not bound ourselves. **This handler now
    awaits venue writes**: it calls ``executor.dispatch``, which may place an
    order list and, on an ambiguous outcome, leaves a record for the next bar to
    resolve. The bound is the executor's own
    :class:`~trading_bot.execution.dispatch_budget.DispatchBudget`, derived from
    ``risk.dispatch_deadline_s`` -- a budget it sets itself, which is what the
    rule above requires.
    """

    async def handle(signal: Signal, candle: Candle) -> None:
        try:
            assessment = risk.evaluate(signal, portfolio=portfolio)
        except Exception as exc:  # the handler must never raise; see the docstring
            _log_collaborator_failure(_COLLABORATOR_RISK, signal, exc, pairs)
            return

        try:
            await intent_logger.record(signal, assessment)
        except Exception as exc:  # the handler must never raise; see the docstring
            _log_collaborator_failure(_COLLABORATOR_INTENT_LOGGER, signal, exc, pairs)

        if executor is None:
            return
        try:
            await executor.dispatch(signal, assessment, candle)
        except Exception as exc:  # the handler must never raise; see the docstring
            _log_collaborator_failure(_COLLABORATOR_EXECUTOR, signal, exc, pairs)

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


def _seed_portfolio(balances: Sequence[Balance], *, quote_asset: str) -> Portfolio:
    """Build the boot-snapshot portfolio from the account's quote balance.

    **Takes a snapshot rather than reading one, and shares it with
    :func:`_snapshot_unmanaged_holdings`.** The boot reads ``get_balances`` once
    and hands the same sequence to both. Two reads is not merely a wasted round
    trip: a balance moving between them would leave the seeded portfolio and the
    unmanaged-holdings snapshot describing **different accounts**, and every
    equity figure derived afterwards would be a blend of two instants. One read
    makes that unrepresentable rather than unlikely.

    That also makes this function pure -- no client, no I/O, no await -- so the
    quote-matching rules below can be exercised against a list of balances.

    From the exchange, never from config: both ``initial_balance`` fields are
    ``float`` *and* belong to backtest/paper, so that route is dead twice over.
    ``Balance.free`` is already ``Money``, parsed from the wire string with
    ``Decimal(str(...))``, so this opens no new float boundary.

    Both sides are upper-cased before matching, here rather than upstream.
    ``base_currency`` does carry a validator -- ``TradingConfig._upper`` in
    ``config/models.py``, a ``field_validator`` that upper-cases it at parse --
    so the value arriving here is normalised already. That is defence in depth
    and not the reason this is correct.

    **This paragraph used to assert that no such validator existed. That was
    FALSE, and it carried no weight**, which is worth separating: the conclusion
    was never "no validator exists" but "this code is correct STANDING ALONE",
    and not depending on a validator two layers away is exactly what that means.
    ``TradingConfig._upper``'s own docstring says the same thing from the other
    side -- *"The composition root normalises both sides itself and does not
    depend on this -- correctness there must not rest on a validator two layers
    away."* So the two files agreed on the substance while disagreeing on the
    fact.

    This function remains ``base_currency``'s only consumer: ``live_system``
    reads it once to pass it here, and nothing else in ``src/`` touches it. The
    **normalised** form is what lands on the portfolio, because it is
    interpolated into refusal messages and future code will compare against it.

    ``get_balances`` returns every asset including zero balances, so an absent
    entry means genuinely absent -- a configured quote asset the account does not
    hold -- and refuses the boot. A zero balance is a valid, non-refusing state.
    """
    normalised = quote_asset.upper()
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
    client: ExchangeClient,
    *,
    balances: Sequence[Balance],
    pairs: Mapping[str, PairContext],
    portfolio: Portfolio,
) -> None:
    """Record material base holdings the account had before this bot started.

    **``balances`` is the boot's single account read, shared with
    :func:`_seed_portfolio`.** This function used to take its own, and the two
    reads could disagree if a balance moved between them -- leaving the seeded
    portfolio and this snapshot describing different accounts. The ``client`` is
    still needed, for the per-asset ticker below.

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

    # Collected, then reported ONCE below. Per-asset WARNING lines put 501 of
    # them into run 2's 609-line log -- 82.3% of the run, and 501 of its 503
    # WARNING lines -- so a B2 block line would have sat among them at an
    # adjacent level, and the silence-as-pass check B2 relies on was unreadable
    # (`M5g-080`, `M5g-076`).
    excluded: list[str] = []

    for balance in balances:
        asset = balance.asset.upper()
        # The quote asset is already `free_quote`; counting it here would
        # double it into equity outright.
        if asset == quote or balance.total <= 0:
            continue

        symbol = by_base.get(asset)
        if symbol is None:
            excluded.append(asset)
            # DEBUG, not WARNING, and the QUANTITY is why this detail is worth
            # keeping but not worth announcing. This branch runs precisely
            # because no enabled pair quoted in `quote` prices the asset, so
            # the amount cannot be valued here at all: 501 such quantities
            # cannot be summed and do not bound the equity error. The ASSET
            # NAME is the half an operator can act on -- it says what to enable
            # -- so the full list stays available under `logging.level: DEBUG`
            # rather than being sampled into the summary, where an arbitrary
            # five of five hundred would read as the whole set.
            _log.debug(
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

    # ONE line, and only when there is something to say. A line reporting zero
    # exclusions would fire on every healthy boot forever, which is the banner
    # this collapse exists to remove rather than relocate -- and it is the same
    # silence-as-pass convention the B2 scan beside it already uses.
    #
    # WARNING and NOT downgraded, deliberately. On a faucet-funded Testnet
    # account this fires every boot and looks structural; on a live account it
    # fires only when the operator holds something the bot cannot price, which
    # is genuinely exceptional. Lowering the level to suit the development
    # environment would hide a real degradation in the one that matters --
    # equity is the denominator of every sizing decision AND of the daily-loss
    # threshold. The volume was the defect; the level was not.
    #
    # **NO ASSET NAME CROSSES THIS LINE**, which is what makes it unbreakable by
    # a name like `这是测试币` -- measured on this account in run 2. Only a count
    # and the quote asset appear, both plain types the `extra=` whitelist admits.
    if excluded:
        _log.warning(
            "%d asset(s) are EXCLUDED FROM EQUITY -- no enabled %s pair prices them, so "
            "equity is UNDERSTATED by their combined value, which cannot be computed here. "
            "Set logging.level to DEBUG for the per-asset list.",
            len(excluded),
            quote,
            extra={
                "event": _EVENT_BOOT_EXCLUDED,
                "excluded_count": len(excluded),
                "quote_asset": quote,
            },
        )


# --------------------------------------------------------------------------
# The root
# --------------------------------------------------------------------------
#: List statuses from which nothing further can happen. **A BLACKLIST, and it
#: is deliberately NOT ``resolution._is_live``.**
#:
#: That helper is a WHITELIST of live states (``EXECUTING``, ``EXEC_STARTED``),
#: so a status nobody has classified reads as *terminal* -- the permissive
#: direction, which is right for its caller: ``resolve_placement`` asks *"did my
#: write land and is it working"*, and answering "not live" costs a re-query.
#:
#: This asks the opposite question -- *"is it safe to trade this symbol"* -- and
#: under fail-closed an unrecognised status must BLOCK. So the default has to
#: invert, and the only way to invert it is to test TERMINAL rather than negate
#: LIVE. ``_is_live`` is not reused and not changed: it has other callers whose
#: direction is correct for them.
#:
#: Two definitions answering opposite questions with opposite defaults, on
#: purpose. Neither is a copy of the other.
_TERMINAL_LIST_STATUSES = frozenset({"ALL_DONE", "REJECT"})


async def _snapshot_live_order_lists(
    client: ExchangeClient,
    *,
    pairs: Mapping[str, PairContext],
    portfolio: Portfolio,
) -> None:
    """Block any enabled symbol carrying an order list of OURS that still works.

    **The failure this exists to prevent, measured.** ``Position`` is
    in-process only, so a restart forgets it entirely and
    ``reconcile_open_positions`` -- which iterates ``portfolio.open_positions``
    -- is structurally silent about it. Meanwhile the base is *locked* by the
    resting protective legs, so ``balance.free`` is zero, so
    :func:`_snapshot_unmanaged_holdings` reads it as dust and blocks nothing.
    The bot would then enter again, on top of a live list it does not know
    about. Measured on this account: BTC ``free=0``, ``locked=0.02310000``,
    order list ``255471`` ``EXECUTING``, two legs resting.

    **The ``-2010`` collision does not save a restart.** Two processes on ONE
    bar derive the same client order id and the venue refuses the second. A
    restart signals on a DIFFERENT bar, so ``entry_bar_time`` differs, so the
    ids differ, so both are accepted. The accidental protection that contained
    the concurrent case is absent from the sequential one.

    **ONE call, account-wide**, regardless of how many pairs are enabled --
    ``get_all_order_lists`` enumerates the account and the filtering is local.

    **Recognition is by PARSING, never by prefix.** A raw
    ``startswith("tb1-")`` admits ``tb1-garbage``; a human's order that merely
    starts the same way would refuse a symbol. Only ``symbol`` is matched:
    ``entry_bar_time`` and ``generation`` are recovered by the parser but are
    unverifiable after a restart, because the bar a previous process traded on
    lived only in that process's memory.

    **FAIL CLOSED, and account-wide.** If the enumeration raises, every enabled
    symbol is blocked -- not one. The call is a single account-wide read, so its
    failure carries no symbol-specific information; blocking one would assert
    knowledge about the others that we do not have. A boot that cannot see the
    venue cannot know whether it is about to pyramid.

    Blocks rather than raising, so it is **not** a sixth ``ConfigError`` boot
    refusal: the ruling is to refuse a symbol, not the boot. Whether anything
    remains tradeable is a separate question, answered by the caller.
    """
    try:
        lists = await client.get_all_order_lists()
    except TradingBotError as exc:
        for symbol in pairs:
            portfolio.blocked_symbols[symbol] = (
                "could not enumerate order lists at boot, so whether one of ours is still "
                f"working here is UNKNOWN ({type(exc).__name__}: {exc}). Refusing rather than "
                "assuming: a boot that cannot see the venue cannot know whether it is about "
                "to open a second position on top of a live one"
            )
        _log.error(
            "Order-list enumeration FAILED at boot; every enabled symbol is blocked. "
            "Nothing will be entered until the venue can be read and the bot restarted.",
            extra={
                "event": _EVENT_BOOT_BLOCKED,
                "symbols": ",".join(sorted(pairs)),
                "error_type": type(exc).__name__,
                "error": str(exc),
            },
        )
        return

    for order_list in lists:
        if order_list.list_order_status in _TERMINAL_LIST_STATUSES:
            continue
        parts = parse_list_client_order_id(order_list.list_client_order_id or "")
        if parts is None:
            continue  # not ours: a human's list, or another tool's

        symbol = parts.symbol
        if symbol not in pairs:
            # R-NE: nothing to block. `evaluate` already refuses an unconfigured
            # symbol at `UNKNOWN_PAIR`, so a block here would be a second
            # mechanism for a refusal that already happens. The operator still
            # needs telling -- money is resting there, and re-enabling the pair
            # would make it matter.
            _log.warning(
                "%s carries a live order list of ours (%s) but is not an enabled pair. "
                "Nothing is blocked; enabling this pair while that list works would.",
                symbol,
                order_list.order_list_id,
                extra={
                    "event": _EVENT_BOOT_FOREIGN_SYMBOL,
                    "symbol": symbol,
                    "order_list_id": order_list.order_list_id,
                    "list_client_order_id": order_list.list_client_order_id,
                },
            )
            continue

        portfolio.blocked_symbols[symbol] = (
            f"an order list this bot placed is still working at the venue (venue list "
            f"{order_list.order_list_id}, our id {order_list.list_client_order_id}, status "
            f"{order_list.list_order_status}). Money is resting there that this bot is NOT "
            "watching: the position it belongs to was lost when the previous process ended. "
            "Entries here are refused until that list is cancelled at the venue AND the bot "
            "is restarted"
        )
        _log.error(
            "%s is BLOCKED: a live order list of ours is working at the venue",
            symbol,
            extra={
                "event": _EVENT_BOOT_BLOCKED,
                "symbol": symbol,
                "order_list_id": order_list.order_list_id,
                "list_client_order_id": order_list.list_client_order_id,
                "list_order_status": order_list.list_order_status,
            },
        )


def _require_something_tradeable(pairs: Mapping[str, PairContext], portfolio: Portfolio) -> None:
    """V2: refuse the boot when nothing is left to trade.

    **This is NOT B1.** B1 refuses whenever any live list exists, which would
    stop a two-pair bot over one blocked symbol. This adds no judgement about
    what to block -- it observes that :func:`_snapshot_live_order_lists` blocked
    everything and says so. With two pairs enabled and one blocked it does not
    fire.

    **Why exit rather than idle.** A bot with every symbol blocked connects,
    seeds history, evaluates strategies and refuses every signal -- indefinitely
    and quietly, among five hundred boot warnings. That is
    ``docs/M5_NUMBERS.md``'s own failure shape: *"the bot looks healthy while
    never trading."* An exit is the one outcome an operator cannot miss.

    It is the family of the five existing boot refusals -- a ``ConfigError``
    raised before the first socket -- and joins them for the same reason: the
    honest failure is immediate and names its cause.
    """
    tradeable = [symbol for symbol in pairs if symbol not in portfolio.blocked_symbols]
    if tradeable:
        return
    detail = "\n".join(
        f"  {symbol}: {portfolio.blocked_symbols[symbol]}" for symbol in sorted(pairs)
    )
    raise ConfigError(
        "every enabled pair is blocked, so there is nothing this bot can trade. Stopping "
        "rather than running with no reachable action:\n"
        f"{detail}\n"
        "Cancel the listed order lists at the venue, or enable a pair that is not blocked, "
        "then restart."
    )


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

    # THE OUTERMOST SCOPE, and BEFORE the client. A refused instance must never
    # authenticate, so the lock precedes every venue call -- the only thing
    # ahead of it is the pure mode check. It is released in the innermost
    # `finally` of the outermost one, AFTER the client closes, so it outlives
    # every other resource: no window exists in which this process has torn
    # down but still holds the account.
    #
    # A `contextlib.ExitStack` rather than a `with` block, and the reason is
    # reviewability rather than taste: a `with` here would re-indent this
    # function's entire body, mixing a mechanical change into a semantic commit.
    #
    # ONLY WHEN THE CLIENT IS OURS TO BUILD. An injected client authenticates
    # nothing, and acquiring unconditionally would make every test of this boot
    # path contend for one lock file -- serialising a suite over a resource
    # that exists to serialise PROCESSES.
    instance_lock = ExitStack()
    if client is None:
        instance_lock.enter_context(acquire_instance_lock())

    resolved_client = client if client is not None else await BinanceClient.create(settings)
    try:
        timeframes = _pair_timeframes(settings)
        pairs = await _prime_pairs(resolved_client, timeframes)
        # ONE account read, shared by both consumers below. The saved round trip
        # is the smaller half: two reads could disagree if a balance moved
        # between them, and the seeded portfolio and the unmanaged-holdings
        # snapshot would then describe different accounts. The single read is
        # taken at the EARLIER of the two original moments, so `_seed_portfolio`
        # observes exactly what it did before and the holdings snapshot now
        # observes an account state one round trip older.
        balances = await resolved_client.get_balances()
        portfolio = _seed_portfolio(balances, quote_asset=settings.config.trading.base_currency)
        # Still before any socket, with the other four boot refusals.
        await _snapshot_unmanaged_holdings(
            resolved_client, balances=balances, pairs=pairs, portfolio=portfolio
        )
        # Beside the holdings snapshot, and after it: the two blocking
        # mechanisms are established together, so an operator meets both
        # verdicts before anything opens a socket. Still ahead of step 5.
        await _snapshot_live_order_lists(resolved_client, pairs=pairs, portfolio=portfolio)
        _require_something_tradeable(pairs, portfolio)

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

                # THE ROOT OWNS THE WHOLE `PersistedState`, and that ownership
                # is the ruling rather than a convenience. `store.save` is
                # WHOLE-FILE, so two writers would clobber each other: the
                # executor owns `pending`, a later accrual will own the ledger,
                # and only an object holding BOTH can write either without
                # erasing the other.
                #
                # THE MAPPING LIVES HERE for the same reason the callable does.
                # `CLAUDE.md` has outer layers "depend inward only", and the
                # composition root is the one layer permitted to know both
                # `execution/` and `persistence/` -- so `execution/` never
                # imports the store and gains no outer-to-outer edge.
                #
                # NOTHING READS THIS AT BOOT. Restore is a later commit; the
                # state starts empty and this is a write path with no reader.
                persisted = store.PersistedState()

                def _persist_pending(records: tuple[PendingPlacement, ...]) -> None:
                    """Write the executor's pending set, preserving the ledger."""
                    nonlocal persisted
                    persisted = store.PersistedState(
                        pending=tuple(
                            store.PendingRecord(
                                symbol=record.symbol,
                                entry_bar_time=record.entry_bar_time,
                                generation=record.generation,
                                quantity=record.quantity,
                                entry_limit=record.entry_limit,
                                stop_loss=record.stop_loss,
                                take_profit=record.take_profit,
                            )
                            for record in records
                        ),
                        ledger=persisted.ledger,
                    )
                    store.save(persisted)

                executor = OrderExecutor(
                    client=resolved_client,
                    portfolio=portfolio,
                    budget=DispatchBudget.from_config(settings.config),
                    persist_pending=_persist_pending,
                )
                engine.on_signal(
                    _build_signal_handler(
                        risk=risk,
                        intent_logger=intent_logger,
                        portfolio=portfolio,
                        pairs=pairs,
                        executor=executor,
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
                # Subscriber ONE: Option 4 resolution, after the reconciler and
                # still before the engine's own hook. So every bar runs
                # reconcile -> resolve -> decide, and an ambiguous write from
                # the previous bar is settled out of THIS bar's fresh budget
                # before anything new can be dispatched.
                provider.on_candle(executor)
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
                    executor=executor,
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
        # Nested so the lock is released even if closing the client raises,
        # and released AFTER it -- which is what makes it the outermost
        # teardown despite not being the outermost `with`.
        try:
            await resolved_client.close()
        finally:
            instance_lock.close()
