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
0a. The durable store, read before the instance lock and before every venue
   call. A missing store is a normal first boot; a corrupt one REFUSES, because
   a state file we cannot parse cannot say whether an order list is resting at
   the venue. Numbered ``0a`` rather than renumbering 1 to 12, following the
   ``3a`` already below.
1. REST client (injected, or built from settings).
2. Pair contexts -- the *pure* duplicate-symbol check first, so a config
   mistake costs no network round trip, then one ``get_symbol_info`` per
   distinct symbol.
3. One ``get_balances``, shared by steps 3a and 4 -- two reads could disagree
   if a balance moved between them.
3a. Portfolio, seeded from that snapshot **and from step 0a's ledger** -- the
   one fact the account cannot re-supply, since no trade-history method is
   declared on the port. Restored unconditionally; a stale one reads as zero
   without being discarded.
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

**There are SEVEN boot refusals, and they are not homogeneous** -- which is why
they were documented as four until M5b's rotation and as five until the store
gained a reader. Five raise ``ConfigError`` here: a mode with no composition
root, an empty enabled-pair set, a duplicate symbol on two timeframes, a quote
asset the account does not hold, and every enabled pair blocked
(:func:`_require_something_tradeable`). The sixth is a symbol the exchange does
not know, which **propagates** out of ``get_symbol_info`` inside
:func:`_prime_pairs`. The seventh is a corrupt store, which propagates out of
``store.load`` at step 0a as
:class:`~trading_bot.persistence.store.StoreCorruptError`.

Counting ``raise ConfigError`` sites therefore finds five and misses two, and
the two it misses are of DIFFERENT kinds: one is a refusal this file does not
write, the other is not a ``ConfigError`` at all -- nothing is wrong with the
configuration, and telling an operator to check ``config.yaml`` would send them
to the wrong file. Both are refusals; neither is greppable from here.

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
from trading_bot.core.portfolio import DaySummary, Ledger, Portfolio
from trading_bot.engine.live_engine import TradingEngine
from trading_bot.exchange.ids import parse_list_client_order_id
from trading_bot.execution.dispatch_budget import CallBounds, DispatchBudget
from trading_bot.execution.executor import (
    OrderExecutor,
    Pending,
    PendingClose,
    PendingPlacement,
)
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
    from collections.abc import AsyncIterator, Collection, Mapping, Sequence
    from datetime import date

    from trading_bot.config.settings import Settings
    from trading_bot.core.models import Balance, Candle, Money, Signal

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


def _restore_pending(state: store.PersistedState | None) -> tuple[Pending, ...]:
    """Map stored records back into the executor's own type, field for field.

    **The exact reverse of the forward mapping in :func:`live_system`**, and it
    lives here for the same reason that one does: ``CLAUDE.md`` has outer layers
    depend inward only, and the composition root is the single layer permitted
    to know both ``execution/`` and ``persistence/``. ``execution/`` imports no
    store, and ``persistence/`` imports no executor; the two types meet in this
    file and nowhere else.

    Pure, and takes the loaded state rather than reading it, so the mapping is
    exercisable without a file. ``None`` -- a first boot with no store -- maps
    to an empty tuple, which is the same value the executor defaults to.

    **What a restored record is NOT.** It is not evidence that anything rests
    at the venue; see :meth:`~trading_bot.execution.executor.OrderExecutor.__init__`.
    Nothing here queries, and nothing here decides.
    """
    if state is None:
        return ()
    return tuple(
        PendingClose(
            symbol=record.symbol,
            entry_bar_time=record.entry_bar_time,
            generation=record.generation,
            quantity=record.quantity,
        )
        if record.kind == "close"
        else PendingPlacement(
            symbol=record.symbol,
            entry_bar_time=record.entry_bar_time,
            generation=record.generation,
            quantity=record.quantity,
            entry_limit=record.entry_limit,
            stop_loss=record.stop_loss,
            take_profit=record.take_profit,
        )
        for record in state.pending
    )


def _restore_ledger(state: store.PersistedState | None) -> Ledger | None:
    """Map the stored ledger back into the domain's own type, field for field.

    The sibling of :func:`_restore_pending` and here for the identical reason:
    ``core/`` may not import ``persistence/``, so ``store.LedgerRecord`` and
    ``core.portfolio.Ledger`` -- two types carrying the same two fields -- meet
    in this file and nowhere else.

    **RESTORED UNCONDITIONALLY. No date filtering at boot**, and that is the
    ruling rather than an omission. A ledger dated yesterday is not stale data
    to be discarded: :func:`~trading_bot.core.portfolio._ledger_is_stale`
    already derives ``Decimal(0)`` for a prior day on the READ side, so an old
    ledger is harmless and self-correcting the moment it is read. Filtering it
    here would instead lose a SAME-DAY restart's accruals -- the amnesia this
    piece exists to end -- and would do so silently, because the discarded
    figure has no other record.

    Boot performs no write. The restored value is handed to
    :func:`_seed_portfolio` and the store is untouched until the first
    placement.

    ``None`` -- no store, or a store that has never accrued -- maps to ``None``,
    which is the same value ``Portfolio.ledger`` defaults to. **Absent, not
    zero:** a ``Ledger`` carrying ``Decimal(0)`` says accruals netted out on a
    day that was traded, and that is a different fact this mapping must not
    flatten.

    **``trades_count`` CROSSES HERE TOO, and it did not until C3.** The field
    was on the record and this mapping ignored it, so every restart reset the
    day's close count to zero while carrying its total across intact -- the
    total right and the count wrong, on the same object, from the same file.
    Nothing reported it because the domain's own default is ``0``.
    """
    if state is None or state.ledger is None:
        return None
    return Ledger(
        realised_pnl=state.ledger.realised_pnl,
        pnl_date=state.ledger.pnl_date,
        trades_count=state.ledger.trades_count,
    )


def _to_day_record(summary: DaySummary) -> store.DayRecord:
    """One completed day, domain shape into store shape.

    The outbound sibling of :func:`_restore_history` and the day-level twin of
    :func:`_to_record`. It lives here for the reason all of them do: ``core/``
    may not import ``persistence/``, so ``core.portfolio.DaySummary`` and
    ``store.DayRecord`` -- two frozen types carrying the same two fields under
    the same two names -- meet in this file and nowhere else.

    The field names were mirrored deliberately when ``DaySummary`` was written,
    which is what keeps this a rename of nothing.
    """
    return store.DayRecord(realised=summary.realised, trades_count=summary.trades_count)


def _restore_history(state: store.PersistedState | None) -> dict[date, DaySummary]:
    """Completed days from the store, back into the domain's own type.

    **RESTORED IN FULL, WITH NO PRUNE AND NO DATE FILTER**, for the reason
    :func:`_restore_ledger` applies none either. The bound is the DOMAIN's and
    is applied at the roll -- see ``core.portfolio._pruned_history`` -- so
    trimming here would drop days the portfolio would then re-add from nothing,
    or worse, drop them permanently on a file the domain never re-derives.

    An empty mapping is returned for an absent store, which is what
    :attr:`Portfolio.daily_history` defaults to anyway. There is no
    absent-versus-empty distinction to preserve here: a day appears only when
    it ENDS with a booking in it, so "no completed days" and "no file" are the
    same fact about history and are not the same fact about the ledger.
    """
    if state is None:
        return {}
    return {
        day: DaySummary(realised=record.realised, trades_count=record.trades_count)
        for day, record in state.daily_history.items()
    }


def _restore_lifetime(state: store.PersistedState | None) -> Money | None:
    """The lifetime accumulator from the store, preserving ABSENT versus ZERO.

    **NOT A BARE PASSTHROUGH, and the reason is the same one
    :func:`_restore_ledger` states for the ledger itself: absent is not zero.**
    ``None`` means no day has ever rolled -- the bot has not yet completed a UTC
    day with a booking in it. ``Decimal(0)`` means days HAVE rolled and their
    realised totals netted out to nothing. Those are different facts about the
    account, and a mapping that flattened either into the other would report a
    bot that has never closed a day as one that closed several and broke even.

    Written as an explicit function rather than ``state.lifetime_realised`` at
    the call site so the distinction has somewhere to be stated and something
    to fail. A passthrough expression carries the same value and documents
    nothing, and the next hand to touch it has no reason not to write
    ``or Decimal(0)``.
    """
    if state is None:
        return None
    return state.lifetime_realised


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


def _seed_portfolio(
    balances: Sequence[Balance],
    *,
    quote_asset: str,
    ledger: Ledger | None = None,
    daily_history: dict[date, DaySummary] | None = None,
    lifetime_realised: Money | None = None,
) -> Portfolio:
    """Build the boot-snapshot portfolio from the account's quote balance.

    **``ledger`` is the ONE field that does NOT come from the venue**, and that
    asymmetry is the whole of why it is a parameter. Free balance, positions
    and unmanaged holdings are all re-derivable from the account at boot;
    realised P&L is not, because no trade-history method is declared on the
    port and attributing P&L needs entry prices of positions that no longer
    exist. It is therefore the only thing a restart genuinely forgets, and the
    only reason the store holds it.

    Defaulting to ``None`` keeps every caller that predates the restore
    unchanged, and ``None`` is what ``Portfolio.ledger`` defaults to anyway --
    absent, meaning nothing has ever been booked.

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
            # ONE CONSTRUCTION, not construct-then-assign. `Portfolio` carries
            # `validate_assignment=True`, so seeding the ledger afterwards
            # would be a second validated write and would leave the object
            # briefly existing without the record it is supposed to boot with.
            # C3 added two more restored fields and they go into this SAME
            # call for that reason -- three restored values assigned after
            # construction would be three such windows instead of one.
            #
            # `daily_history` is normalised to `{}` here rather than passed
            # through: the field carries a dict FACTORY default, so `None` is
            # not a value it accepts. `lifetime_realised` passes through
            # untouched because `None` IS one of its values -- never accrued,
            # as distinct from accrued to zero.
            return Portfolio(
                quote_asset=normalised,
                free_quote=balance.free,
                ledger=ledger,
                daily_history=daily_history if daily_history is not None else {},
                lifetime_realised=lifetime_realised,
            )
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


def _require_something_tradeable(
    pairs: Mapping[str, PairContext],
    portfolio: Portfolio,
    *,
    pending: Collection[str],
) -> None:
    """V2: refuse the boot when nothing is left to trade.

    **This is NOT B1.** B1 refuses whenever any live list exists, which would
    stop a two-pair bot over one blocked symbol. This adds no judgement about
    what to block -- it observes what the boot already excluded and says so.
    With two pairs enabled and one excluded it does not fire.

    **Why exit rather than idle.** A bot with every symbol excluded connects,
    seeds history, evaluates strategies and refuses every signal -- indefinitely
    and quietly, among five hundred boot warnings. That is
    ``docs/M5_NUMBERS.md``'s own failure shape: *"the bot looks healthy while
    never trading."* An exit is the one outcome an operator cannot miss.

    It is the family of the five existing boot refusals -- a ``ConfigError``
    raised before the first socket -- and joins them for the same reason: the
    honest failure is immediate and names its cause. It shares that mechanism
    with the corrupt-state refusal rather than adding a second: both raise a
    :class:`~trading_bot.core.exceptions.TradingBotError` subclass, both are
    caught by the one handler in ``main``, and both leave by the same exit.

    **TWO EXCLUSION CAUSES NOW, AND THE SECOND IS A PENDING CLOSE.** ``pending``
    carries the symbols whose restored records the caller judged disqualifying.
    Such a record means this process is holding a lock on that symbol: the
    executor's dispatch guard refuses every entry while one is held, and a
    close's record is not cleared by a restart, because ``Position`` is
    in-process only -- so ``RiskManager`` refuses the CLOSE at
    ``NOTHING_TO_CLOSE`` before anything can reach the path that would release
    it. Left to itself that symbol refuses entries for the life of the process
    while looking perfectly healthy, which is the failure shape above reached by
    a second route this check could not previously see.

    **ANNOTATED BY THE FEE COMMIT: "LEFT TO ITSELF THAT SYMBOL REFUSES ENTRIES
    FOR THE LIFE OF THE PROCESS" DOES NOT DESCRIBE THE EXECUTOR.**
    ``OrderExecutor.__call__`` resolves every restored record on the first
    candle, closes included, and ``_resolve_close`` releases a restored close
    there: with no ``Position`` after a restart, the fill classifies
    ``POSITION_ABSENT`` and the record is dropped unbooked. The lock heals one
    candle after boot. What stands is this check's own reason, one step
    earlier: on a config whose every pair is excluded the boot refuses BEFORE
    that first candle, so the healing path is never reached there.

    **A RESTORED *PLACEMENT* IS NOT IN ``pending``, AND EXCLUDING ONE WOULD
    DEADLOCK THE BOT.** The two locks look alike and behave oppositely. A
    placement lock is SELF-HEALING: ``OrderExecutor.__call__`` resolves it
    against the venue on the first candle and releases it. A close lock is not,
    for the reason above. So refusing to boot over a placement would prevent the
    very tick that clears it -- the bot would refuse, restart, refuse again, and
    the state that caused it could never be reached to resolve. An unrecoverable
    restart loop, produced by the check meant to stop an unproductive one.

    That asymmetry is the whole of the ruling and it is stated HERE rather than
    only at the call site, because the filter is one predicate and a later hand
    widening ``pending`` back to every record would restore the deadlock while
    making the code look more thorough.

    **WHICH KIND IS THE CALLER'S JUDGEMENT, NOT THIS FUNCTION'S.** The filter is
    applied where the symbols are derived; the contract here stays "these
    symbols are not tradeable, and here is why". This function never inspects a
    record, and it never learns that a union of two kinds exists.

    **WHAT A RESOLUTION DOES ABOUT IT IS NOT DECIDED HERE AND IS NOT DESCRIBED
    HERE.** This function observes a restored lock and refuses an unrunnable
    boot; it makes no claim about what any later code does with the record.

    **``pending`` IS REQUIRED AND KEYWORD-ONLY, WITH NO DEFAULT.** An empty
    default would be the value most likely to be wrong and least likely to be
    noticed -- a caller that forgot it would silently restore the old blindness
    and every test would still pass. The same reasoning ``Position.protection``
    carries, one notch weaker because no validator enforces it here.

    **``excluded`` MAPS EVERY NON-TRADEABLE SYMBOL TO ITS OWN REASON, and that
    is what keeps the message renderable.** The reason is taken from the
    collection that caused the exclusion, so a symbol cannot be excluded without
    one. Building the detail line by looking each symbol up in
    ``blocked_symbols`` -- which was correct while that was the ONLY cause --
    raises ``KeyError`` the moment a symbol is excluded for being pending.
    MEASURED before this change: the old expression over a blocked-plus-pending
    set raises ``KeyError: 'ETHUSDT'``, so the refusal could not print itself.

    **THREE CAUSES, AND EACH IS A DIFFERENT WAY THE SYMBOL IS SPOKEN FOR.**

    * ``blocked_symbols`` -- an order list of OURS is still working at the
      venue. Money is committed to a resting order this process does not track.
    * ``pending`` -- a close this bot started is unresolved, so what happened at
      the venue is unknown and the executor holds a lock on the symbol.
    * ``unmanaged_holdings`` -- the account holds base the bot did not open.
      Untracked inventory, counted toward equity and never sold by this bot,
      which ``RiskManager`` refuses entries against at
      ``RefusalStage.UNMANAGED_HOLDING``.

    The third arrived last and was the longest blind: the risk layer refused
    those entries all along, while this gate could not see them, so a
    single-pair bot holding untracked base booted clean and refused every
    signal for ever. Same failure shape as the pending case, by a third route.

    **``unmanaged_holdings`` IS READ HERE AND NEVER WRITTEN.** It stays a BOOT
    snapshot, taken once before any ``Position`` exists, and that timing is its
    own correctness argument -- see the field. Reading it costs nothing;
    writing it at runtime was considered and rejected, because ``equity`` sums
    it and ``NO_MARK_PRICE`` refuses portfolio-wide on anything it cannot price.

    **A RESTORED PLACEMENT IS STILL NOT A CAUSE**, and that ruling survives
    this rewrite deliberately. A placement lock is SELF-HEALING --
    ``OrderExecutor.__call__`` resolves it against the venue on the first
    candle and releases it -- so refusing to boot over one would prevent the
    very tick that clears it: refuse, restart, refuse again, with the causing
    state permanently out of reach. Only a CLOSE reaches ``pending`` above.

    **A SYMBOL WITH MORE THAN ONE CAUSE REPORTS THE FIRST OF
    blocked > pending > unmanaged**, and the order is by how immediately the
    venue is committed rather than by severity. A working order list is money in
    a live order right now; an unresolved close is a lock over an unknown venue
    state; untracked inventory is an asset sitting still. Each names a different
    action -- cancel it, resolve it, sell or move it -- and the operator should
    be sent to the most immediate one. Reporting all three would make the common
    single-cause line harder to read for a case that needs one action anyway.
    """
    excluded: dict[str, str] = {}
    for symbol in pairs:
        if symbol in portfolio.blocked_symbols:
            excluded[symbol] = portfolio.blocked_symbols[symbol]
        elif symbol in pending:
            excluded[symbol] = (
                "a close this bot started is UNRESOLVED -- a pending close record for this "
                "symbol was restored from the store, so what happened to the position at the "
                "venue is unknown. Entries here are refused while that record is held"
            )
        elif symbol in portfolio.unmanaged_holdings:
            excluded[symbol] = (
                f"the account holds {portfolio.unmanaged_holdings[symbol]} of the base asset "
                "that this bot did not open. It is counted toward equity and the bot will "
                "not trade or sell it; entries here are excluded while it remains"
            )

    tradeable = [symbol for symbol in pairs if symbol not in excluded]
    if tradeable:
        return
    detail = "\n".join(f"  {symbol}: {excluded[symbol]}" for symbol in sorted(pairs))
    raise ConfigError(
        "every enabled pair is excluded, so there is nothing this bot can trade. Stopping "
        "rather than running with no reachable action:\n"
        f"{detail}\n"
        "Cancel any order list listed above at the venue, resolve any unresolved close, sell "
        "or move any untracked base holding, or enable a pair that is not listed, then "
        "restart."
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

    # STEP 0a: THE DURABLE STATE, READ BEFORE ANYTHING ELSE EXISTS.
    #
    # `StoreCorruptError` is NOT caught, and that is the ruling rather than an
    # omission. A store we cannot parse cannot say whether an order list is
    # RESTING at the venue or was never placed -- and those want opposite
    # actions. Booting anyway would run with `has_position` false for a symbol
    # that may hold live protection, and the first `_persist_pending` write
    # would OVERWRITE the evidence with an empty set. Refusing is the only
    # answer that preserves the file for an operator to look at.
    #
    # AHEAD OF EVERY VENUE CALL, which is three: `BinanceClient.create`
    # authenticates, `_prime_pairs` reads symbol info, `get_balances` reads the
    # account. So a corrupt store refuses before a socket, a signature or a
    # credential is used -- the shape the other boot refusals already have.
    #
    # AHEAD OF THE INSTANCE LOCK TOO. Lines below up to the `try` are outside
    # every teardown scope, so a raise between `enter_context` and that `try`
    # would leave the ExitStack to garbage collection. Reading first adds no
    # raise site to that gap. Nothing is lost by reading unlocked: `store.save`
    # replaces atomically, so a concurrent writer cannot be read half-written,
    # and a process that loses the lock exits without ever writing.
    #
    # A MISSING STORE IS NOT CORRUPTION -- `load` returns None, which is the
    # ordinary first boot and proceeds normally.
    restored = store.load()
    # ONE EVALUATION, TWO CONSUMERS. The boot gate below needs the restored
    # symbols and the executor needs the records themselves, and calling
    # `_restore_pending` twice would let the gate and the executor disagree
    # about what came back -- a second source of truth for one file read. It is
    # pure and takes the already-loaded state, so hoisting it here crosses
    # nothing: no client exists yet, no lock is held, and a raise would happen
    # earlier than it does today rather than later.
    restored_pending = _restore_pending(restored)

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
        # THE LEDGER IS THE ONE FACT THE VENUE CANNOT RE-SUPPLY, so it comes
        # from the store read at step 0a rather than from `balances`. Until
        # this line it was written and never read back -- the same
        # write-path-with-no-reader shape closed for `pending`, still open for
        # the ledger, and the reason `data/state.json` has read `"ledger":
        # null` after every run to date.
        portfolio = _seed_portfolio(
            balances,
            quote_asset=settings.config.trading.base_currency,
            ledger=_restore_ledger(restored),
            daily_history=_restore_history(restored),
            lifetime_realised=_restore_lifetime(restored),
        )
        # Still before any socket, with the other four boot refusals.
        await _snapshot_unmanaged_holdings(
            resolved_client, balances=balances, pairs=pairs, portfolio=portfolio
        )
        # Beside the holdings snapshot, and after it: the two blocking
        # mechanisms are established together, so an operator meets both
        # verdicts before anything opens a socket. Still ahead of step 5.
        await _snapshot_live_order_lists(resolved_client, pairs=pairs, portfolio=portfolio)
        # CLOSES ONLY, and a placement here would DEADLOCK THE BOT. A restored
        # placement is resolved against the venue by the executor on the first
        # candle and released; refusing to boot over one would prevent that very
        # tick, so the bot would refuse, restart and refuse again with the
        # causing state permanently out of reach. A restored close has no such
        # path -- see `_require_something_tradeable` for why -- and is the whole
        # reason that check learned about `_pending` at all.
        #
        # Filtered HERE rather than inside the check: which kind disqualifies a
        # symbol is this root's judgement, and the check's contract stays "these
        # symbols are not tradeable".
        _require_something_tradeable(
            pairs,
            portfolio,
            pending={record.symbol for record in restored_pending if record.kind == "close"},
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
                # SEEDED FROM THE STORE READ AT STEP 0a. Starting from a fresh
                # `PersistedState()` when a store existed would silently ERASE
                # the ledger on the first placement -- the whole-file clobber
                # this root owns the state to prevent, arriving from inside the
                # owner.
                #
                # WHAT THIS OBJECT CARRIES, EXACTLY -- and the list is shorter
                # than it looks. This comment used to say the closures "carry
                # `ledger` across verbatim, so whatever was restored is
                # preserved through every subsequent write". That was true of
                # `ledger` and FALSE of everything C1 and C2 added, because
                # both closures REBUILD a frozen `PersistedState` from named
                # keywords: any field they do not name reverts to its default,
                # whatever this object holds. A restored `daily_history` was
                # therefore erased by the first save of the run -- the same
                # clobber, arriving through the seeding that exists to stop it.
                #
                # After C3 the closures name every field they must preserve,
                # and they take FOUR of the five from `portfolio` LIVE rather
                # than from here. So `persisted` is now the carrier of exactly
                # ONE slice -- `pending` -- read by `_persist_ledger` alone.
                # That one read is the residual its own docstring names; it is
                # UNRULED and deliberately untouched by C3.
                persisted = restored if restored is not None else store.PersistedState()

                def _to_record(
                    record: Pending,
                ) -> store.PendingRecord | store.PendingCloseRecord:
                    """One domain record into its store shape, dispatched on ``kind``.

                    **THE MAPPING STAYS HERE, and the union is why it had to
                    grow.** `CLAUDE.md` has outer layers depend inward only, so
                    ``execution/`` never imports ``persistence/`` and the root
                    is the one layer permitted to know both. When ``_pending``
                    became ``PendingPlacement | PendingClose`` the writer alias
                    widened with it, and contravariance made a closure written
                    for placements alone stop satisfying it -- so mypy named
                    THIS site rather than letting a close reach a mapper that
                    would have dropped it. That is the union doing the work it
                    was chosen for.

                    Lifted out of the closure because it now branches; a
                    conditional expression inside a generator inside a
                    constructor is where this would have become unreadable.
                    """
                    if record.kind == "close":
                        return store.PendingCloseRecord(
                            kind="close",
                            symbol=record.symbol,
                            entry_bar_time=record.entry_bar_time,
                            generation=record.generation,
                            quantity=record.quantity,
                        )
                    return store.PendingRecord(
                        symbol=record.symbol,
                        entry_bar_time=record.entry_bar_time,
                        generation=record.generation,
                        quantity=record.quantity,
                        entry_limit=record.entry_limit,
                        stop_loss=record.stop_loss,
                        take_profit=record.take_profit,
                    )

                def _persist_pending(records: tuple[Pending, ...]) -> None:
                    """Write the executor's pending set, carrying the LIVE ledger.

                    **``portfolio.ledger`` IS READ HERE, AT SERIALISATION TIME.
                    IT USED TO PASS ``persisted.ledger`` AND THAT LOST REAL
                    MONEY.** ``persisted`` is seeded from the boot read and
                    rebound only by these two closures, so its ledger slice is a
                    SNAPSHOT -- and the executor's booking path accrues through
                    ``Portfolio.close_position``, which goes through no writer
                    at all. Every pending write therefore stamped the boot value
                    over whatever had been booked since.

                    MEASURED, and it is the reason this closure changed: on
                    2026-09-06 the bot closed four positions between 06:15 and
                    10:16 -- ``-6.9908540000``, ``+1.4531076000``,
                    ``+0.9816510000``, ``+1.1078115000``, the project's first
                    profits -- and each close's pending DELETION rewrote
                    ``data/state.json`` with the boot snapshot. The file's mtime
                    was ``10:16:03``, the instant of the last booking, and its
                    contents read ``-135.8406927000``: the value from two days
                    earlier. The live accrual, ``-3.4482839000`` on a rolled
                    ``pnl_date``, never reached disk.

                    **Reading the portfolio is what makes the slice unownable by
                    a stale local.** The ledger has exactly one writer --
                    ``record_realised_pnl``, reached only from
                    ``close_position`` -- so ``portfolio.ledger`` is current
                    truth at every instant, and a closure that reads it cannot
                    be behind. A cached copy can only ever be equal or wrong.

                    **THIS IS ALSO WHAT MAKES A CLOSE ONE ATOMIC SAVE.** The
                    close's completion drops the symbol from ``_pending`` and
                    calls this once; the deletion and the accrual are now in the
                    SAME ``PersistedState`` and reach disk in the same
                    ``os.replace``. No second callback is needed and none is
                    added -- a separate completion writer would be a second
                    owner of one slice, which is the clobber this root holds the
                    whole state to prevent.
                    """
                    nonlocal persisted
                    # EVERY FIELD BELOW IS READ LIVE FROM `portfolio`, NEVER
                    # FROM `persisted`. `persisted` is a local refreshed only
                    # by whichever closure last ran, and the history and the
                    # lifetime total change through `record_realised_pnl`,
                    # which goes through NO writer -- exactly the shape that
                    # cost four bookings on 2026-09-06 when the ledger was
                    # cached here.
                    persisted = store.PersistedState(
                        pending=tuple(_to_record(record) for record in records),
                        ledger=(
                            None
                            if portfolio.ledger is None
                            else store.LedgerRecord(
                                realised_pnl=portfolio.ledger.realised_pnl,
                                pnl_date=portfolio.ledger.pnl_date,
                                trades_count=portfolio.ledger.trades_count,
                            )
                        ),
                        daily_history={
                            day: _to_day_record(summary)
                            for day, summary in portfolio.daily_history.items()
                        },
                        lifetime_realised=portfolio.lifetime_realised,
                    )
                    store.save(persisted)

                def _persist_ledger(ledger: Ledger) -> None:
                    """Write the accrued ledger, preserving the pending set.

                    **NO LONGER AN EXACT MIRROR, and the asymmetry is the
                    point.** ``store.save`` is WHOLE-FILE, so each writer must
                    carry the other's slice across. That one now reads
                    ``portfolio.ledger`` LIVE; this one still passes
                    ``pending=persisted.pending``, and the two are not the same
                    risk.

                    **Why this side may cache where that side could not.** The
                    ledger changes through ``close_position``, which goes
                    through NO writer -- so a cached ledger goes stale
                    invisibly, which is exactly what cost four bookings on
                    2026-09-06. The pending set changes only through the
                    executor, which persists on EVERY mutation, so
                    ``persisted.pending`` is refreshed by the same act that
                    changes it.

                    **THE RESIDUAL, NAMED RATHER THAN FIXED.**
                    ``_persist_quietly`` SWALLOWS a failed delete-write by
                    design -- a stale record on disk is self-correcting where a
                    refused write is not. On that path ``_pending`` has changed
                    and ``persisted.pending`` has not, so a later ledger write
                    would restore the stale set. Narrow, reachable only through
                    a swallowed write failure, and NOT closed here: the ruling
                    that produced this commit names ``_persist_pending`` only,
                    and widening it unasked would be a second change hiding
                    inside a fix.

                    **The mapping lives HERE for the same reason the callable
                    does.** ``CLAUDE.md`` has outer layers "depend inward
                    only", and the composition root is the one layer permitted
                    to know both ``core/`` and ``persistence/``. The argument
                    is a ``core.portfolio.Ledger`` -- an INWARD type the driver
                    may name -- and ``store.LedgerRecord`` never leaves this
                    file, exactly as ``store.PendingRecord`` never leaves it.

                    **THE RECONCILER CALLS THIS**, for a venue-triggered fill it
                    books itself. The executor's own close path does NOT -- it
                    holds no ledger writer, and after this commit it does not
                    need one: its pending write carries the live ledger, so a
                    close's deletion and its accrual reach disk together.
                    """
                    nonlocal persisted
                    # `trades_count` comes from the ARGUMENT, beside the two
                    # fields already taken from it: the caller passes the
                    # ledger it wants written, and reading two of its three
                    # fields from the argument and the third from `portfolio`
                    # could write a record that never existed on either.
                    #
                    # The history and the lifetime total have no argument, so
                    # they are read LIVE from `portfolio` -- never from
                    # `persisted`, which is a stale local. That is the same
                    # rule the pending closure states above.
                    persisted = store.PersistedState(
                        pending=persisted.pending,
                        ledger=store.LedgerRecord(
                            realised_pnl=ledger.realised_pnl,
                            pnl_date=ledger.pnl_date,
                            trades_count=ledger.trades_count,
                        ),
                        daily_history={
                            day: _to_day_record(summary)
                            for day, summary in portfolio.daily_history.items()
                        },
                        lifetime_realised=portfolio.lifetime_realised,
                    )
                    store.save(persisted)

                executor = OrderExecutor(
                    client=resolved_client,
                    portfolio=portfolio,
                    budget=DispatchBudget.from_config(settings.config),
                    settlement_bounds=CallBounds(
                        timeout_s=settings.config.risk.reconcile_deadline_s, attempts=1
                    ),
                    persist_pending=_persist_pending,
                    # RESTORED, NOT RESOLVED. These are questions the previous
                    # process could not answer, handed straight to the existing
                    # first-candle path: `__call__` runs `resolve_placement` on
                    # each one out of the next bar's fresh budget. NO BOOT-TIME
                    # RESOLUTION is added here -- doing it at boot would spend
                    # an unbudgeted round trip per record ahead of the socket,
                    # and would duplicate a path that is already written,
                    # already ordered before the engine's own hook, and already
                    # fail-closed on an UNRESOLVED verdict.
                    restored_pending=restored_pending,
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
                    persist_ledger=_persist_ledger,
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
