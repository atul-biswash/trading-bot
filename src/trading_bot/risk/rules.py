"""Protective exit rules: stop-loss, take-profit, and trailing stop.

Pure functions that compute protective levels for a position and decide when an
open position should exit. No I/O and no pandas: every rule is a call with
``Decimal`` numbers, exactly like ``position_sizing``.

Rounding -- the load-bearing decision
-------------------------------------
Every protective level is a price and must land on the symbol's tick. The
direction of that rounding is chosen so a rounding artefact can never make a
protective level *looser* than configured:

**A stop rounds toward its reference.** The realized distance from the reference
is then never larger than the configured distance:

* the initial stop-loss rounds toward the **entry price**, so the realized loss
  at stop never exceeds what ``risk_per_trade`` sizing budgeted (a stop rounded
  the other way silently breaches the risk budget);
* the trailing stop rounds toward the **high-water mark**, so the realized
  give-back never exceeds the configured ``trail_percent``.

**A take-profit rounds toward entry**, so the target is never further than
configured and the realized reward is never overstated.

All three are the single rule "round ``level`` toward ``reference``", expressed
once in :func:`_round_toward`. ``round_price`` keeps its unconditional
``ROUND_DOWN`` for order dispatch; these levels need the per-level direction, so
they use :func:`~trading_bot.utils.helpers.round_to_tick` directly. Prices are
strictly positive, so ``ROUND_CEILING``/``ROUND_FLOOR`` are the number-line
directions "up"/"down".

If the configured distance is smaller than one tick, rounding toward the
reference collapses the level onto (or past) it. That is treated as "no placeable
level this bar": the level comes back ``None`` with a reason, never an exception.
An ATR stop distance can fall below a tick simply because volatility went quiet
-- a transient, self-healing state -- and this path runs on *every* signal, so a
raise would reach ``TradingEngine``'s consecutive-failure quarantine and disable
a healthy pair, the very failure ``SizingDecision`` exists to avoid. Genuinely
incoherent *inputs* still raise: a non-positive price or a non-finite ATR value
is a contract violation, not a market state.

The ATR ``float`` -> ``Decimal`` boundary
-----------------------------------------
``indicators.atr`` returns ``float64`` (NaN during warmup), but a stop price is
``Money`` and the ``Money`` guard rejects ``float``/``numpy.float64``. The
conversion is a *different* boundary from the config one and lives in exactly one
place, :func:`_atr_to_decimal`: it rejects non-finite and non-positive input
(``Decimal(str(nan))`` would silently yield ``Decimal('NaN')`` and poison a stop)
and converts via the value's shortest repr, the same principle config load uses.
The residual float error is orders of magnitude below the tick, which the
directional rounding then dominates -- a precision funnel, not a leak. It stays
private here rather than a general ``utils`` helper: a public ``float`` ->
``Decimal`` converter is a Money-guard-defeating tool, and this is the only place
that legitimately needs one.

Order of operations
-------------------
A ``risk_per_trade`` position sizes from the stop distance and an ``rr``
take-profit multiplies it, so the sequence is fixed: **stop -> realized distance
-> size (elsewhere, in sizing) -> take-profit.** :func:`take_profit_level`
requires the stop distance as an argument for the ``rr`` case, so the type makes
the ordering non-optional.

State
-----
Everything here is a pure function; the trailing stop's high-water mark lives on
``Position`` (``highest_price``/``lowest_price``), not on any object here.
:func:`update_trailing_stop` returns the new mark and level for the caller to
store, and enforces monotonicity in code (``max`` for a long, ``min`` for a
short) so the trail can never move against the position.
"""

from __future__ import annotations

import math
from decimal import ROUND_CEILING, ROUND_FLOOR, Decimal
from enum import Enum
from typing import TYPE_CHECKING

from pydantic import BaseModel, ConfigDict, model_validator

from trading_bot.core.enums import PositionSide, StopType, TakeProfitType
from trading_bot.core.models import Money
from trading_bot.utils.helpers import round_to_tick

if TYPE_CHECKING:  # pragma: no cover - typing only
    from trading_bot.config.models import (
        StopLossConfig,
        TakeProfitConfig,
        TrailingStopConfig,
    )
    from trading_bot.core.models import Position

__all__ = [
    "ExitDecision",
    "ExitReason",
    "ProtectiveLevels",
    "TrailingStopUpdate",
    "compute_protective_levels",
    "should_exit",
    "stop_loss_level",
    "take_profit_level",
    "update_trailing_stop",
]

#: Divisor for the whole-percent config fields (``2.0`` means 2%).
_PERCENT = Decimal(100)
_ONE = Decimal(1)


# ---------------------------------------------------------------------------
# Frozen result objects (mirroring SizingDecision: a wrapper, not a bare number)
# ---------------------------------------------------------------------------
class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True)


class ExitReason(str, Enum):
    """Which protective rule fired. Richer than a boolean: an operator needs to
    know whether a stop, a trailing stop or a target closed the position."""

    STOP_LOSS = "stop_loss"
    TAKE_PROFIT = "take_profit"
    TRAILING_STOP = "trailing_stop"


class ProtectiveLevels(_Frozen):
    """The stop-loss and take-profit computed for a position at entry.

    ``None`` for either level is a legitimate, expected outcome (the rule is
    disabled in config), representable rather than smuggled as a sentinel price.
    The ``Money`` field types mean no level can be built from a ``float``.
    """

    symbol: str
    side: PositionSide
    entry_price: Money
    stop_loss: Money | None = None
    take_profit: Money | None = None
    #: Realized (post-rounding) ``|entry - stop_loss|``; what an ``rr`` take-profit
    #: and ``risk_per_trade`` sizing must both use. ``None`` iff no stop.
    stop_distance: Money | None = None
    basis: str

    @model_validator(mode="after")
    def _check_sides(self) -> ProtectiveLevels:
        """Make "levels sit on the correct side of entry" a property of the type."""
        if self.side is PositionSide.LONG:
            if self.stop_loss is not None and not self.stop_loss < self.entry_price:
                raise ValueError(
                    f"long stop_loss {self.stop_loss} must be below entry {self.entry_price}"
                )
            if self.take_profit is not None and not self.take_profit > self.entry_price:
                raise ValueError(
                    f"long take_profit {self.take_profit} must be above entry {self.entry_price}"
                )
        elif self.side is PositionSide.SHORT:
            if self.stop_loss is not None and not self.stop_loss > self.entry_price:
                raise ValueError(
                    f"short stop_loss {self.stop_loss} must be above entry {self.entry_price}"
                )
            if self.take_profit is not None and not self.take_profit < self.entry_price:
                raise ValueError(
                    f"short take_profit {self.take_profit} must be below entry {self.entry_price}"
                )
        else:
            raise ValueError("ProtectiveLevels requires an open long or short position")

        if (self.stop_loss is None) != (self.stop_distance is None):
            raise ValueError("stop_loss and stop_distance must both be set or both be None")
        if self.stop_loss is not None and self.stop_distance is not None:
            expected = abs(self.entry_price - self.stop_loss)
            if self.stop_distance != expected:
                raise ValueError(
                    f"stop_distance {self.stop_distance} != |entry - stop| {expected}"
                )
        return self


class TrailingStopUpdate(_Frozen):
    """The result of advancing a trailing stop by one bar.

    ``high_water`` is the favourable extreme so far (the peak for a long, the
    trough for a short); the caller stores it on ``Position.highest_price`` /
    ``lowest_price``. ``stop_price`` is ``None`` only while the trail is not yet
    activated and no stop existed before.
    """

    high_water: Money
    stop_price: Money | None = None
    activated: bool
    detail: str


class ExitDecision(_Frozen):
    """Why an open position should exit now, at ``price`` (the level that fired).

    When a stop and the take-profit both trigger on one bar, the stop wins and
    ``price`` is the stop level -- the worst fill of the two.
    """

    symbol: str
    reason: ExitReason
    price: Money
    detail: str


# ---------------------------------------------------------------------------
# Validation and rounding helpers
# ---------------------------------------------------------------------------
def _require_positive(name: str, value: Decimal) -> None:
    """Reject a non-positive input that would make a level meaningless.

    A non-positive entry or price is corrupt market data or an upstream gate
    failure, not a market condition, so it raises rather than returning a
    plausible-looking level -- the same stance ``position_sizing`` takes.
    """
    if value <= 0:
        raise ValueError(f"{name} must be > 0, got {value}")


def _require_directional(side: PositionSide) -> None:
    if side not in (PositionSide.LONG, PositionSide.SHORT):
        raise ValueError(f"a protective level needs an open long or short position, got {side}")


def _round_toward(level: Decimal, reference: Decimal, tick_size: Decimal) -> Decimal:
    """Round ``level`` to the tick, in the direction of ``reference``.

    ``level`` below the reference rounds up toward it; above, down toward it.
    Either way the rounded level moves no further from the reference than the
    raw one, so the realized distance never exceeds the configured distance.
    """
    rounding = ROUND_CEILING if level < reference else ROUND_FLOOR
    return round_to_tick(level, tick_size, rounding=rounding)


def _protective_level(raw: Decimal, reference: Decimal, tick_size: Decimal) -> Decimal | None:
    """Round ``raw`` toward ``reference``, keeping it strictly on ``raw``'s side.

    Returns ``None`` when the configured distance is sub-tick and rounding
    collapses the level onto (or past) the reference: "no placeable level this
    bar", a representable outcome the caller turns into a ``None`` level carrying
    a reason -- never an exception (see the module docstring).
    """
    below = raw < reference
    level = _round_toward(raw, reference, tick_size)
    on_protective_side = level < reference if below else level > reference
    return level if on_protective_side else None


def _level_basis(enabled: bool, level: Decimal | None, kind: str, tick_size: Decimal) -> str:
    """One human-readable clause explaining a level's presence or absence."""
    if not enabled:
        return "disabled"
    if level is not None:
        return f"{kind} {level}"
    return f"distance below one tick ({tick_size}); none placed"


def _atr_to_decimal(value: float) -> Decimal:
    """The one ATR ``float`` -> ``Decimal`` boundary (see the module docstring)."""
    if not math.isfinite(value):
        raise ValueError(
            f"ATR value must be finite, got {value!r} -- ATR is NaN during warmup, so "
            "this is a contract violation (the caller sized/entered before ATR was ready)"
        )
    if value < 0:
        raise ValueError(
            f"ATR value must not be negative, got {value!r} -- ATR is non-negative by "
            "construction, so a negative is corrupt data, not a market state"
        )
    # str(float(x)) is the shortest round-tripping repr for both float and
    # numpy.float64; Decimal(x) would instead inject the full binary expansion. A
    # zero ATR (a flat/frozen window) yields a zero distance, which the caller
    # then treats as "no placeable stop" -- a quiet-market state, not an error.
    return Decimal(str(float(value)))


# ---------------------------------------------------------------------------
# Stop-loss and take-profit levels
# ---------------------------------------------------------------------------
def _stop_distance(config: StopLossConfig, entry_price: Decimal, atr_value: float | None) -> Decimal:
    """Raw (pre-rounding) stop distance from the configured method."""
    if config.type is StopType.PERCENT:
        return entry_price * config.percent / _PERCENT
    if config.type is StopType.ATR:
        if atr_value is None:
            raise ValueError(
                "stop_loss.type='atr' sizes the stop from the ATR value, so an atr_value "
                "is required; either supply one or set stop_loss.type='percent'"
            )
        return config.atr_multiplier * _atr_to_decimal(atr_value)
    raise ValueError(f"Unsupported stop_loss type: {config.type!r}")  # pragma: no cover


def stop_loss_level(
    *,
    side: PositionSide,
    entry_price: Decimal,
    config: StopLossConfig,
    tick_size: Decimal,
    atr_value: float | None = None,
) -> Decimal | None:
    """Tick-aligned stop-loss price, or ``None`` if there is no placeable stop.

    ``None`` means either stop-loss is disabled or the configured distance is
    sub-tick this bar (a transient low-volatility state -- see the module
    docstring). The level is rounded *toward entry*, so ``|entry - level|`` never
    exceeds the configured distance. ``atr_value`` is required only for
    ``type='atr'``.
    """
    if not config.enabled:
        return None
    _require_directional(side)
    _require_positive("entry_price", entry_price)

    distance = _stop_distance(config, entry_price, atr_value)
    raw = entry_price - distance if side is PositionSide.LONG else entry_price + distance
    return _protective_level(raw, entry_price, tick_size)


def take_profit_level(
    *,
    side: PositionSide,
    entry_price: Decimal,
    config: TakeProfitConfig,
    tick_size: Decimal,
    stop_distance: Decimal | None = None,
) -> Decimal | None:
    """Tick-aligned take-profit price, or ``None`` if there is no placeable target.

    ``None`` means take-profit is disabled or the configured distance is sub-tick.
    ``rr`` targets are ``rr_multiple`` times ``stop_distance``, which must
    therefore be supplied (compute the stop first); passing ``stop_distance=None``
    for an ``rr`` target is a caller error and raises. The level rounds *toward
    entry*, so the realized reward is never overstated.
    """
    if not config.enabled:
        return None
    _require_directional(side)
    _require_positive("entry_price", entry_price)

    if config.type is TakeProfitType.PERCENT:
        distance = entry_price * config.percent / _PERCENT
    elif config.type is TakeProfitType.RR:
        if stop_distance is None:
            raise ValueError(
                "take_profit.type='rr' multiplies the stop distance, so stop_distance is "
                "required; compute the stop first or enable stop_loss"
            )
        _require_positive("stop_distance", stop_distance)
        distance = config.rr_multiple * stop_distance
    else:  # pragma: no cover - the enum is closed
        raise ValueError(f"Unsupported take_profit type: {config.type!r}")

    raw = entry_price + distance if side is PositionSide.LONG else entry_price - distance
    return _protective_level(raw, entry_price, tick_size)


def compute_protective_levels(
    *,
    symbol: str,
    side: PositionSide,
    entry_price: Decimal,
    stop_loss: StopLossConfig,
    take_profit: TakeProfitConfig,
    tick_size: Decimal,
    atr_value: float | None = None,
) -> ProtectiveLevels:
    """Compute stop-loss and take-profit for a new position, in the fixed order.

    Stop first (its realized distance feeds an ``rr`` take-profit), then the
    take-profit. Returns a :class:`ProtectiveLevels`; either level may be ``None``
    when its rule is disabled or its configured distance is sub-tick this bar. The
    ``basis`` string records why each level is present or absent.
    """
    _require_directional(side)
    _require_positive("entry_price", entry_price)

    stop = stop_loss_level(
        side=side, entry_price=entry_price, config=stop_loss, tick_size=tick_size, atr_value=atr_value
    )
    distance = None if stop is None else abs(entry_price - stop)

    # An rr target multiplies the stop distance; when the stop is unavailable this
    # bar (disabled, or sub-tick), the target is equally unavailable. Represent it
    # as no target rather than letting take_profit_level raise on a live signal.
    rr_without_distance = (
        take_profit.enabled and take_profit.type is TakeProfitType.RR and distance is None
    )
    target = (
        None
        if rr_without_distance
        else take_profit_level(
            side=side,
            entry_price=entry_price,
            config=take_profit,
            tick_size=tick_size,
            stop_distance=distance,
        )
    )

    stop_desc = _level_basis(stop_loss.enabled, stop, stop_loss.type.value, tick_size)
    tp_desc = (
        "no stop distance for rr target"
        if rr_without_distance
        else _level_basis(take_profit.enabled, target, take_profit.type.value, tick_size)
    )
    basis = f"{side.value} @ {entry_price}: stop-loss {stop_desc}, take-profit {tp_desc}"
    return ProtectiveLevels(
        symbol=symbol,
        side=side,
        entry_price=entry_price,
        stop_loss=stop,
        take_profit=target,
        stop_distance=distance,
        basis=basis,
    )


# ---------------------------------------------------------------------------
# Trailing stop -- the only stateful rule, kept pure by returning the new state
# ---------------------------------------------------------------------------
def update_trailing_stop(
    *,
    side: PositionSide,
    entry_price: Decimal,
    price: Decimal,
    high_water: Decimal | None,
    existing_stop: Decimal | None,
    config: TrailingStopConfig,
    tick_size: Decimal,
) -> TrailingStopUpdate:
    """Advance a trailing stop by one bar; returns the new mark and level.

    ``high_water`` is the previous favourable extreme (``Position.highest_price``
    for a long, ``lowest_price`` for a short) or ``None`` on the first bar.
    ``existing_stop`` is the previous ``Position.trailing_stop``.

    The trail activates only once the favourable move reaches
    ``activation_percent`` (measured from the extreme, so activation is sticky).
    Once active, the level rounds *toward the high-water mark* (give-back never
    exceeds ``trail_percent``) and is combined with the previous level by ``max``
    (long) / ``min`` (short) -- the monotonicity that guarantees the stop never
    moves against the position.
    """
    _require_directional(side)
    _require_positive("entry_price", entry_price)
    _require_positive("price", price)

    long = side is PositionSide.LONG
    if high_water is None:
        mark = price
    else:
        mark = max(high_water, price) if long else min(high_water, price)

    favourable_move = mark - entry_price if long else entry_price - mark
    move_pct = favourable_move / entry_price * _PERCENT
    if move_pct < config.activation_percent:
        return TrailingStopUpdate(
            high_water=mark,
            stop_price=existing_stop,
            activated=False,
            detail=f"trail inactive: move {move_pct}% < activation {config.activation_percent}%",
        )

    factor = _ONE - config.trail_percent / _PERCENT if long else _ONE + config.trail_percent / _PERCENT
    candidate = _protective_level(mark * factor, mark, tick_size)
    if candidate is None:
        # Trail distance is sub-tick this bar (very low volatility or a very tight
        # trail). Keep the previous stop rather than tightening on a rounding
        # artefact; the trail resumes once the distance clears one tick. Still
        # activated -- activation is sticky.
        return TrailingStopUpdate(
            high_water=mark,
            stop_price=existing_stop,
            activated=True,
            detail=f"trail distance below one tick ({tick_size}); stop unchanged",
        )
    if existing_stop is None:
        new_stop = candidate
    else:
        new_stop = max(existing_stop, candidate) if long else min(existing_stop, candidate)

    return TrailingStopUpdate(
        high_water=mark,
        stop_price=new_stop,
        activated=True,
        detail=f"trail @ {new_stop} ({config.trail_percent}% behind {mark})",
    )


# ---------------------------------------------------------------------------
# Exit detection -- the pure predicate; acting on it is M3's job
# ---------------------------------------------------------------------------
def should_exit(*, position: Position, price: Decimal) -> ExitDecision | None:
    """Decide whether ``position`` should exit at ``price``, and by which rule.

    Evaluates the levels already stored on ``position`` against a **single**
    price -- M3 chooses deliberately whether to feed the bar's close or its
    high/low. A stop (fixed or trailing) takes precedence over the take-profit
    when a single price triggers both, and the returned ``price`` is the stop
    level: the worst fill of the two. Among multiple triggered stops the one hit
    first (the higher for a long, lower for a short) binds. ``None`` means hold.
    """
    _require_positive("price", price)
    long = position.side is PositionSide.LONG
    short = position.side is PositionSide.SHORT
    if not (long or short):
        return None

    triggered: list[tuple[ExitReason, Decimal]] = []
    if position.stop_loss is not None and (
        price <= position.stop_loss if long else price >= position.stop_loss
    ):
        triggered.append((ExitReason.STOP_LOSS, position.stop_loss))
    if position.trailing_stop is not None and (
        price <= position.trailing_stop if long else price >= position.trailing_stop
    ):
        triggered.append((ExitReason.TRAILING_STOP, position.trailing_stop))

    if triggered:
        # The first stop price reaches as it moves adversely binds: highest for a
        # long, lowest for a short.
        reason, level = max(triggered, key=lambda t: t[1]) if long else min(triggered, key=lambda t: t[1])
        arrow = "<=" if long else ">="
        return ExitDecision(
            symbol=position.symbol,
            reason=reason,
            price=level,
            detail=f"price {price} {arrow} {reason.value} {level}",
        )

    if position.take_profit is not None and (
        price >= position.take_profit if long else price <= position.take_profit
    ):
        arrow = ">=" if long else "<="
        return ExitDecision(
            symbol=position.symbol,
            reason=ExitReason.TAKE_PROFIT,
            price=position.take_profit,
            detail=f"price {price} {arrow} take_profit {position.take_profit}",
        )
    return None
