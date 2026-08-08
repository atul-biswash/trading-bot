"""The risk manager -- where limits, sizing and protective levels compose.

:class:`RiskManager` implements the port of the same name and is the handler
wired into :meth:`~trading_bot.engine.live_engine.TradingEngine.on_signal`. It
turns a strategy's signal into an approved, sized, protected **intent** -- and
stops there. Placing that intent is the next milestone; keeping the boundary
here means the whole decision path can be verified without anything being able
to send an order.

Policy, not state, and no I/O
-----------------------------
The manager owns configuration, a market-data reference, per-pair exchange
filters and a clock. The account state it reasons about lives on
:class:`~trading_bot.core.portfolio.Portfolio` and arrives per call. It performs
no network I/O: ``SymbolInfo`` is *injected* rather than fetched, because
``size_position`` is synchronous while ``ExchangeClient.get_symbol_info`` is a
coroutine, and because ``risk/`` promises that every rule is testable by calling
it with numbers. Priming the mapping at startup also means a symbol the exchange
does not know fails at boot rather than on the first signal hours later, and a
unit test can build a manager from a plain dict with no fake client at all.

Order of operations -- fixed, and the reason it is fixed
--------------------------------------------------------
``risk_per_trade`` sizes from the distance to the stop, an ``rr`` take-profit
multiplies that same distance, and an ATR stop needs a market statistic that
does not exist during warmup. Only one order satisfies all three::

    preconditions -> equity -> approve -> ATR -> levels -> size -> affordability

Every step can refuse, and **a refusal is a value, not an exception**. The
engine isolates a raising handler and logs it, so a raise here would not
quarantine the pair -- it would simply print a traceback on every bar forever,
for conditions ("too small to trade", "no placeable stop this bar") that are
routine market states rather than faults. Genuinely incoherent input still
raises, in ``position_sizing`` and ``rules`` where it always did.

Two refusals are worth naming because they are policy, not mechanics:

* **ATR unavailable and the stop is an ATR stop.** The signal is refused. The
  alternatives were falling back to a percent stop, which silently substitutes
  a different risk model for the one the operator configured, and entering
  unprotected, which breaks ``risk_per_trade`` sizing outright.
* **A stop is configured but none is placeable this bar** (the sub-tick case
  M2 makes representable). The entry is skipped for *every* sizing method, not
  only ``risk_per_trade``. The operator asked for a stop; entering without one
  contradicts that instruction, and the condition is transient -- the next bar
  usually clears it. ``stop_loss.enabled`` is what distinguishes "the operator
  turned stops off" from "no level fits on the tick right now".

Exits are defined here and driven elsewhere
-------------------------------------------
:meth:`check_exit` and :meth:`advance_trailing_stop` compose M2's pure rules
with a deliberate choice of price, but nothing here subscribes to candles. An
exit check is per-candle-per-position, while ``on_signal`` fires only when a
strategy has an opinion -- wiring exits into the signal path would skip every
quiet bar, which is precisely the set of bars a stop exists for. The candle
subscription, and acting on the result, belong with execution.

Both feed the closed candle's **close**. On a close-driven engine the bot reacts
at bar close and would fill near it; using the bar's low for a long stop would
claim a fill at a price that has already gone, which is optimistic in backtest
and dishonest live. Real protective orders rest at the exchange and fill
intrabar -- this path is the fallback, and close makes it trigger late, never
early.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from pydantic import BaseModel, ConfigDict, model_validator

from trading_bot.core.enums import (
    OrderSide,
    PositionSide,
    RefusalStage,
    RiskRule,
    SignalAction,
    StopType,
)
from trading_bot.core.exceptions import DataError
from trading_bot.core.interfaces import MarketDataProvider
from trading_bot.core.interfaces import RiskManager as RiskManagerPort
from trading_bot.core.models import (
    Money,
    RiskDecision,
    Signal,
    SizingDecision,
    SymbolInfo,
)
from trading_bot.indicators import atr
from trading_bot.risk.position_sizing import calculate_position_size
from trading_bot.risk.rules import (
    ExitDecision,
    ProtectiveLevels,
    TrailingStopUpdate,
    compute_protective_levels,
    should_exit,
    update_trailing_stop,
)
from trading_bot.utils.helpers import utc_now
from trading_bot.utils.logger import get_logger

if TYPE_CHECKING:  # pragma: no cover - typing only
    from collections.abc import Mapping

    from trading_bot.config.models import RiskConfig
    from trading_bot.core.models import Candle, Position
    from trading_bot.core.portfolio import Portfolio

_log = get_logger(__name__)

__all__ = [
    "Clock",
    "PairContext",
    "RiskAssessment",
    "RiskManager",
    "TradeIntent",
]

#: Source of "now". Injected so the daily-loss and cooldown rules -- the only
#: time-dependent risk in the system -- are testable without real time, mirroring
#: the injected ``sleep`` in ``exchange/base.py``.
Clock = Callable[[], datetime]


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True)


class PairContext(_Frozen):
    """What the manager must know about a tradeable pair, beyond its config.

    One object rather than two parallel mappings so a pair is either fully known
    or not known at all -- there is no state in which the timeframe resolves and
    the filters do not.
    """

    #: The timeframe whose buffer backs this symbol's ATR calculation.
    timeframe: str
    #: Exchange filters: the price tick protective levels round to, and the lot
    #: filters sizing must satisfy.
    symbol_info: SymbolInfo


class TradeIntent(_Frozen):
    """An approved, sized, protected order -- not yet placed.

    Deliberately **not** an ``OrderRequest``. That type has no take-profit
    field, and its ``stop_price`` means "the trigger price of this order", not
    "the protective stop guarding this entry"; expressing an entry plus its two
    protective levels as one ``OrderRequest`` would be a lie execution would
    have to un-learn. Mapping this to the entry order and its protective orders
    is execution's job, where ``_enforce`` re-checks the filters immediately
    before dispatch.
    """

    symbol: str
    side: OrderSide
    quantity: Money
    #: The reference price the intent was computed at -- the signal's price,
    #: which is the closed candle's close with full ``Decimal`` precision.
    price: Money
    #: Protective levels for an entry; ``None`` for an exit, which closes a
    #: position rather than opening one to protect.
    levels: ProtectiveLevels | None = None

    @model_validator(mode="after")
    def _check_invariants(self) -> TradeIntent:
        if self.quantity <= 0:
            raise ValueError(
                f"a trade intent must carry a positive quantity, got {self.quantity}; "
                "'do not trade' is a RiskAssessment with no intent, not a zero-size one"
            )
        if self.price <= 0:
            raise ValueError(f"price must be > 0, got {self.price}")
        if self.levels is not None:
            # The levels carry their own symbol and entry price; disagreement
            # would mean protecting one position with another's stop.
            if self.levels.symbol != self.symbol:
                raise ValueError(f"levels are for {self.levels.symbol}, not {self.symbol}")
            if self.levels.entry_price != self.price:
                raise ValueError(
                    f"levels priced at {self.levels.entry_price} but intent at {self.price}"
                )
        return self


class RiskAssessment(_Frozen):
    """The complete verdict on one signal: the intent, or why there is none.

    Carries the component results that were reached before the verdict was
    settled, so an operator (and a test) can see *where* a signal stopped --
    limits, protective levels or sizing -- without parsing the reason string.
    Components are ``None`` when evaluation refused before computing them.

    :attr:`stage` names that stopping point directly, reported by
    :meth:`RiskManager.evaluate` at the site that refuses rather than inferred
    afterwards from which components are populated. Four of the refusals return
    every component as ``None`` and are separable only by position in
    ``evaluate``'s sequence, so an outside observer could label them only by
    re-deriving that control flow -- which is what ``engine.modes`` did until
    M4b, and what adding a refusal path or reordering two checks silently
    invalidated.

    It is **required but nullable**: there is no default, so every construction
    site has to say something, and an approval says ``None`` deliberately rather
    than by omission.
    """

    symbol: str
    approved: bool
    reason: str
    #: Where evaluation stopped; ``None`` on an approval, which stopped nowhere.
    stage: RefusalStage | None
    intent: TradeIntent | None = None
    decision: RiskDecision | None = None
    levels: ProtectiveLevels | None = None
    sizing: SizingDecision | None = None

    @model_validator(mode="after")
    def _check_invariants(self) -> RiskAssessment:
        if not self.reason:
            raise ValueError("reason must explain the assessment, including an approval")
        if self.approved != (self.intent is not None):
            raise ValueError(
                f"approved={self.approved} contradicts intent={self.intent!r}; an "
                "approval carries the intent it approved and a refusal carries none"
            )
        # Note the polarity: `stage` follows RiskDecision.rule's axis -- present
        # on a refusal, absent on an approval -- and therefore reads inverted
        # against `intent` two lines above, which is present on an approval.
        if self.approved != (self.stage is None):
            raise ValueError(
                f"approved={self.approved} contradicts stage={self.stage!r}; a refusal "
                "must name the stage it stopped at and an approval must name none"
            )
        return self


class RiskManager(RiskManagerPort):
    """Vets, sizes and protects signals against configured limits."""

    def __init__(
        self,
        *,
        config: RiskConfig,
        provider: MarketDataProvider,
        pairs: Mapping[str, PairContext],
        clock: Clock = utc_now,
    ) -> None:
        """Build a manager over injected config, market data, filters and a clock.

        ``pairs`` maps symbol to its timeframe and exchange filters, primed by
        the composition root so this object performs no I/O. ``clock`` returns
        timezone-aware UTC; the default is the process wall clock.
        """
        self._config = config
        self._provider = provider
        self._pairs = dict(pairs)
        self._clock = clock

    # -- port: limits -------------------------------------------------------
    def approve(self, signal: Signal, *, portfolio: Portfolio) -> RiskDecision:
        """Vet ``signal`` against every configured limit. See the port docstring.

        Equity is computed here from the portfolio's positions and the latest
        closed candle for each, because the daily-loss threshold is a percentage
        of it. :meth:`evaluate` computes equity once and reuses it rather than
        paying for it twice.
        """
        marks, unpriced = self._mark_prices(portfolio)
        if unpriced:
            return RiskDecision(
                symbol=signal.symbol,
                approved=False,
                rule=RiskRule.NO_MARK_PRICE,
                reason=(
                    "cannot value open position(s) "
                    f"{', '.join(unpriced)}; equity is unknown, so no limit can be checked"
                ),
            )
        return self._approve(
            signal, portfolio=portfolio, equity=portfolio.equity(marks), marks=marks
        )

    def _approve(
        self,
        signal: Signal,
        *,
        portfolio: Portfolio,
        equity: Decimal,
        marks: Mapping[str, Decimal],
    ) -> RiskDecision:
        """Evaluate the limits against an already-computed ``equity``.

        First failure wins, in a fixed order: the portfolio-wide halt that makes
        every entry unacceptable, then the facts about this one symbol, then the
        portfolio-wide count -- which only bears on a position that would
        genuinely be new, so it is checked after "we already hold this".
        """
        limits = self._config.limits
        now = self._clock()

        def refuse(rule: RiskRule, detail: str) -> RiskDecision:
            return RiskDecision(symbol=signal.symbol, approved=False, rule=rule, reason=detail)

        if equity <= 0:
            return refuse(RiskRule.NO_EQUITY, f"equity is {equity}; nothing to risk")

        if portfolio.daily_loss_exceeded(
            limit_percent=limits.max_daily_loss_percent, equity=equity, now=now, marks=marks
        ):
            return refuse(
                RiskRule.DAILY_LOSS_HALT,
                f"realised P&L {portfolio.realised_today(now)} today breaches "
                f"{limits.max_daily_loss_percent}% of equity {equity}; halted until "
                "the next UTC day",
            )

        if portfolio.has_position(signal.symbol):
            return refuse(
                RiskRule.ALREADY_IN_POSITION,
                f"{signal.symbol} already has an open position; this system does not add to one",
            )

        if portfolio.in_cooldown(signal.symbol, now):
            return refuse(
                RiskRule.COOLDOWN,
                f"{signal.symbol} is in cooldown until {portfolio.cooldown_expiry(signal.symbol)}",
            )

        if portfolio.position_count >= limits.max_open_positions:
            return refuse(
                RiskRule.MAX_OPEN_POSITIONS,
                f"{portfolio.position_count} open positions is at the limit of "
                f"{limits.max_open_positions}",
            )

        return RiskDecision(
            symbol=signal.symbol,
            approved=True,
            reason=(
                f"within all risk limits: {portfolio.position_count}/"
                f"{limits.max_open_positions} positions, equity {equity}, "
                f"realised today {portfolio.realised_today(now)}"
            ),
        )

    # -- port: sizing -------------------------------------------------------
    def size_position(
        self,
        signal: Signal,
        *,
        equity: Decimal,
        price: Decimal,
        stop_price: Decimal | None = None,
    ) -> SizingDecision:
        """Size ``signal`` against ``equity``. See the port docstring.

        The exchange filters come from the injected ``pairs`` mapping. An
        unknown symbol is a wiring or configuration mistake rather than a market
        state, but it is still returned as a refusal: it would otherwise raise
        on every bar of a mis-configured pair.
        """
        context = self._pairs.get(signal.symbol)
        if context is None:
            return SizingDecision(
                symbol=signal.symbol,
                quantity=Decimal(0),
                requested_quantity=Decimal(0),
                reason=(
                    f"no trade: {signal.symbol} has no exchange filters loaded; "
                    "it is not in the manager's configured pairs"
                ),
            )
        return calculate_position_size(
            symbol_info=context.symbol_info,
            equity=equity,
            price=price,
            sizing=self._config.position_sizing,
            limits=self._config.limits,
            stop_price=stop_price,
        )

    # -- the composed path --------------------------------------------------
    def evaluate(self, signal: Signal, *, portfolio: Portfolio) -> RiskAssessment:
        """Turn one signal into an intent to trade, or into the reason there is none.

        The fixed sequence documented in the module docstring. Every refusal is
        a returned value; nothing on this path raises for a market condition.

        Every refusal names the :class:`~trading_bot.core.enums.RefusalStage` it
        stopped at, at the site that refuses. That is the whole reason the stage
        lives on :class:`RiskAssessment`: until M4b it was re-derived from this
        control flow in ``engine.modes``, and four of the refusals -- unknown
        pair, unusable price, ``SELL``, nothing-to-close -- return every
        component as ``None``, so they were separable only by their position in
        this sequence. Adding a path or reordering two checks mislabelled a log
        line with nothing else failing. Now a new refusal cannot be added
        without naming a stage, because the parameter is required.

        .. note::
           The **order** of the checks below is still load-bearing, just no
           longer duplicated: it is what decides which stage an input
           satisfying two guards at once reports.
           ``tests/unit/test_modes.py::TestRefusalStages`` drives the real
           ``evaluate`` down every branch and pins four adjacent pairs by
           supplying an input that trips both. Not every pair is pinned -- some
           are order-independent and some are not separately satisfiable; see
           the M4b entry in ``docs/PHASE_HISTORY.md``.
        """
        symbol = signal.symbol

        def refuse(
            detail: str,
            *,
            stage: RefusalStage,
            decision: RiskDecision | None = None,
            levels: ProtectiveLevels | None = None,
            sizing: SizingDecision | None = None,
        ) -> RiskAssessment:
            return RiskAssessment(
                symbol=symbol,
                approved=False,
                reason=detail,
                stage=stage,
                decision=decision,
                levels=levels,
                sizing=sizing,
            )

        context = self._pairs.get(symbol)
        if context is None:
            return refuse(
                f"{symbol} has no exchange filters loaded; it is not in the manager's "
                "configured pairs",
                stage=RefusalStage.UNKNOWN_PAIR,
            )

        price = signal.price
        if price is None or price <= 0:
            return refuse(
                f"signal carries no usable reference price ({price}); every level and "
                "size is derived from it",
                stage=RefusalStage.NO_REFERENCE_PRICE,
            )

        if signal.action is SignalAction.CLOSE:
            return self._exit_assessment(signal, portfolio=portfolio, price=price)

        if signal.action is not SignalAction.BUY:
            return refuse(
                f"{signal.action.value} opens a short, which is unreachable on spot; "
                "only BUY and CLOSE are actionable",
                stage=RefusalStage.UNSUPPORTED_ACTION,
            )

        marks, unpriced = self._mark_prices(portfolio)
        if unpriced:
            decision = RiskDecision(
                symbol=symbol,
                approved=False,
                rule=RiskRule.NO_MARK_PRICE,
                reason=f"cannot value open position(s) {', '.join(unpriced)}",
            )
            return refuse(decision.reason, stage=RefusalStage.NO_MARK_PRICE, decision=decision)

        # Forward risk that cannot be priced refuses BEFORE the limits, in the
        # shape NO_MARK_PRICE already has: an inability to compute, not a
        # limit's verdict. Scoped by `stop_loss.enabled`, because the two states
        # are different facts -- stops on with a position lacking one is a
        # divergence and refusing is correct, while stops off means the operator
        # has declared they own their exits, so the check honestly degrades to
        # realised-only. There is deliberately no RiskDecision here: no RiskRule
        # names this, which keeps NO_MARK_PRICE the single place the two
        # vocabularies coincide.
        _committed, uncomputable = portfolio.committed_risk(marks)
        if uncomputable and self._config.stop_loss.enabled:
            return refuse(
                f"{uncomputable} open position(s) have no computable stop while "
                "risk.stop_loss.enabled is true; committed risk cannot be summed, so "
                "no daily-loss limit can be checked and all entries are refused",
                stage=RefusalStage.COMMITTED_RISK_UNKNOWN,
            )

        equity = portfolio.equity(marks)
        decision = self._approve(signal, portfolio=portfolio, equity=equity, marks=marks)
        if not decision.approved:
            return refuse(decision.reason, stage=RefusalStage.LIMIT_REFUSED, decision=decision)

        # AFTER the limits, not before, and the position is the argument. An
        # unmanaged holding leaves the ledger INTACT -- nothing is uncomputable,
        # one symbol is simply not ours to trade -- so it does not belong beside
        # NO_MARK_PRICE and COMMITTED_RISK_UNKNOWN, which are inabilities to
        # compute. It is a fact about one symbol, and `_approve`'s own order
        # puts the portfolio-wide halts ahead of those. Checking it here keeps
        # that order intact while still letting it carry its own stage.
        if portfolio.has_unmanaged_holding(symbol):
            return refuse(
                f"{symbol}: the account holds {portfolio.unmanaged_holdings[symbol]} of the "
                "base asset that this bot did not open. It is counted toward equity and the "
                "bot will not trade or sell it; entries here are excluded while it remains",
                stage=RefusalStage.UNMANAGED_HOLDING,
                decision=decision,
            )

        stop_loss = self._config.stop_loss
        atr_value: float | None = None
        if stop_loss.enabled and stop_loss.type is StopType.ATR:
            atr_value = self._atr_value(symbol, context.timeframe)
            if atr_value is None:
                return refuse(
                    f"stop_loss.type='atr' needs an ATR value and none is available for "
                    f"{symbol}/{context.timeframe} (warming up, or the window contains a "
                    f"gap); ATR needs {stop_loss.atr_period + 1} clean bars",
                    stage=RefusalStage.ATR_UNAVAILABLE,
                    decision=decision,
                )

        levels = compute_protective_levels(
            symbol=symbol,
            side=PositionSide.LONG,
            entry_price=price,
            stop_loss=stop_loss,
            take_profit=self._config.take_profit,
            tick_size=context.symbol_info.price_tick,
            atr_value=atr_value,
        )

        # A stop the operator asked for but that cannot be placed this bar. Skip
        # the entry for every sizing method: entering unprotected contradicts the
        # instruction, and this state is transient. It is also what keeps a
        # sub-tick stop from reaching the sizer's contract check, which raises.
        if stop_loss.enabled and levels.stop_loss is None:
            return refuse(
                f"stop-loss is enabled but no level is placeable this bar ({levels.basis}); "
                "not entering unprotected",
                stage=RefusalStage.STOP_UNPLACEABLE,
                decision=decision,
                levels=levels,
            )

        sizing = self.size_position(signal, equity=equity, price=price, stop_price=levels.stop_loss)
        if not sizing.is_tradeable:
            return refuse(
                sizing.reason,
                stage=RefusalStage.SIZE_NOT_TRADEABLE,
                decision=decision,
                levels=levels,
                sizing=sizing,
            )

        # Equity is total portfolio value; free balance is what can actually be
        # spent. The sizer documents that this check is the caller's job. Fees
        # are not modelled here -- execution applies them at dispatch.
        cost = sizing.quantity * price
        if cost > portfolio.free_quote:
            return refuse(
                f"{sizing.quantity} at {price} costs {cost} {portfolio.quote_asset} but "
                f"only {portfolio.free_quote} is free",
                stage=RefusalStage.UNAFFORDABLE,
                decision=decision,
                levels=levels,
                sizing=sizing,
            )

        intent = TradeIntent(
            symbol=symbol,
            side=OrderSide.BUY,
            quantity=sizing.quantity,
            price=price,
            levels=levels,
        )
        _log.info(
            "Risk approved %s: %s at %s (%s)",
            symbol,
            sizing.quantity,
            price,
            levels.basis,
        )
        return RiskAssessment(
            symbol=symbol,
            approved=True,
            reason=f"{decision.reason}; {sizing.reason}",
            stage=None,
            intent=intent,
            decision=decision,
            levels=levels,
            sizing=sizing,
        )

    def _exit_assessment(
        self, signal: Signal, *, portfolio: Portfolio, price: Decimal
    ) -> RiskAssessment:
        """Build the intent that closes an open position.

        No limits, no sizing and no protective levels: an exit is not a new
        risk, and a limit that could trap an open position would be a risk rule
        that creates risk. The quantity is whatever is held.
        """
        position = portfolio.positions.get(signal.symbol)
        if position is None or not position.is_open:
            return RiskAssessment(
                symbol=signal.symbol,
                approved=False,
                reason=f"nothing to close: no open position in {signal.symbol}",
                stage=RefusalStage.NOTHING_TO_CLOSE,
            )
        intent = TradeIntent(
            symbol=signal.symbol,
            side=OrderSide.SELL,
            quantity=position.quantity,
            price=price,
        )
        return RiskAssessment(
            symbol=signal.symbol,
            approved=True,
            reason=f"closing {position.quantity} {signal.symbol} at {price}",
            stage=None,
            intent=intent,
        )

    # -- exits (defined here, driven by execution) --------------------------
    def check_exit(self, position: Position, candle: Candle) -> ExitDecision | None:
        """Whether ``position`` should exit on this closed bar, and by which rule.

        Fed the bar's **close** -- see the module docstring for why not the
        high/low. The close is ``Money`` from the candle, so no float enters.
        """
        return should_exit(position=position, price=candle.close)

    def advance_trailing_stop(
        self, position: Position, candle: Candle
    ) -> TrailingStopUpdate | None:
        """Advance ``position``'s trailing stop by one bar, storing the new state.

        Returns ``None`` when trailing stops are disabled. M2's
        ``update_trailing_stop`` is pure and hands back the new high-water mark
        and level; writing them onto the position is this layer's job, and the
        high-water mark is stored on the side that matches the position's
        direction. Fed the bar's close, for the same reason
        :meth:`check_exit` is.
        """
        config = self._config.trailing_stop
        if not config.enabled:
            return None

        long = position.side is PositionSide.LONG
        update = update_trailing_stop(
            side=position.side,
            entry_price=position.entry_price,
            price=candle.close,
            high_water=position.highest_price if long else position.lowest_price,
            existing_stop=position.trailing_stop,
            config=config,
            tick_size=self._tick_size(position.symbol),
        )
        # Two statements, so the position is briefly observable with a new
        # high-water mark and the previous stop. Harmless today: Position
        # declares no cross-field validator, and nothing reads it between these
        # lines. If such an invariant is ever added, collapse these writes into
        # a single method on Position rather than relaxing the validator to
        # tolerate the intermediate state -- an invariant that accepts the
        # halfway position is not an invariant. `Position.validate_assignment`
        # keeps the Money guard on each of these writes.
        if long:
            position.highest_price = update.high_water
        else:
            position.lowest_price = update.high_water
        position.trailing_stop = update.stop_price
        return update

    # -- internals ----------------------------------------------------------
    def _tick_size(self, symbol: str) -> Decimal:
        """The symbol's price tick, or zero when the pair is unknown.

        ``round_to_tick`` treats a non-positive tick as "do not round", which is
        the right degradation here: an unknown tick must not silently move a
        protective level onto the wrong grid.
        """
        context = self._pairs.get(symbol)
        return context.symbol_info.price_tick if context is not None else Decimal(0)

    def _mark_prices(self, portfolio: Portfolio) -> tuple[dict[str, Decimal], list[str]]:
        """Latest close per symbol equity must value, plus the ones that have none.

        Covers open positions **and** unmanaged base holdings: both are counted
        by ``equity``, so pricing only the first would make ``equity`` raise on
        a mark it was never given. ``marked_symbols`` supplies the union in a
        stable order.

        Prices come from ``last_candle`` -- exact ``Decimal`` -- never from the
        ``float`` frame. Returning the unpriced symbols rather than raising lets
        the caller turn "equity is unknown" into a refusal an operator can read.
        """
        marks: dict[str, Decimal] = {}
        unpriced: list[str] = []
        for symbol in portfolio.marked_symbols():
            price = self._last_close(symbol)
            if price is None:
                unpriced.append(symbol)
            else:
                marks[symbol] = price
        return marks, unpriced

    def _last_close(self, symbol: str) -> Decimal | None:
        """Close of the latest buffered candle for ``symbol``, or ``None``."""
        context = self._pairs.get(symbol)
        if context is None:
            return None
        try:
            candle = self._provider.last_candle(symbol, context.timeframe)
        except DataError:
            # Present in `pairs` but never tracked by the provider: a wiring
            # mismatch. Degrade to "unpriced" -- the caller reports it once per
            # signal, rather than raising on every bar.
            return None
        return None if candle is None else candle.close

    def _atr_value(self, symbol: str, timeframe: str) -> float | None:
        """Scalar ATR for the latest bar, or ``None`` when there is none.

        The bridge M2 anticipated: ``rules.py`` takes a scalar so the risk layer
        stays free of pandas, and this is the one place that turns a frame into
        that scalar. ``rules.py`` rejects a non-finite ATR, so nothing NaN may
        cross -- which takes two gates, not one:

        * ``is_ready`` for ``atr_period + 1`` bars, because true range is
          undefined on the first bar. Checked before building the frame, so
          warmup costs nothing.
        * ``isfinite`` on the scalar itself. Bar count alone is *not* sufficient:
          the indicator re-masks NaN inputs after the seed, so a single gap in
          the window produces a NaN long after warmup has passed.

        ATR is only computed when the configured stop actually needs it, so a
        percent stop never inherits this warmup gate.
        """
        period = self._config.stop_loss.atr_period
        try:
            if not self._provider.is_ready(symbol, timeframe, period + 1):
                return None
            frame = self._provider.get_dataframe(symbol, timeframe)
        except DataError:
            return None

        series = atr(frame["high"], frame["low"], frame["close"], period)
        value = float(series.iloc[-1])
        return value if math.isfinite(value) else None
