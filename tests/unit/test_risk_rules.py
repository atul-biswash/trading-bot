"""Tests for protective exit rules.

Exact ``Decimal`` assertions throughout, no float tolerance -- a protective level
that is merely *close* is a bug, and a tolerant test cannot catch the float leak
the ``Money`` guard exists to prevent. Tick sizes are awkward on purpose, because
the whole point of directional rounding lives at the tick boundary.
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

import pytest

from trading_bot.config.models import (
    PositionSizingConfig,
    RiskLimitsConfig,
    StopLossConfig,
    TakeProfitConfig,
    TrailingStopConfig,
)
from trading_bot.core.enums import (
    PositionSide,
    PositionSizingMethod,
    ProtectionState,
    StopType,
    TakeProfitType,
)
from trading_bot.core.models import Position, SymbolInfo
from trading_bot.risk.position_sizing import calculate_position_size
from trading_bot.risk.rules import (
    ExitDecision,
    ExitReason,
    ProtectiveLevels,
    TrailingStopUpdate,
    compute_protective_levels,
    should_exit,
    stop_loss_level,
    take_profit_level,
    update_trailing_stop,
)

D = Decimal
LONG = PositionSide.LONG
SHORT = PositionSide.SHORT
#: A fixed bar close, so `entry_bar_time` is deterministic across a run.
BAR_TIME = datetime(2026, 7, 25, 12, 0, tzinfo=timezone.utc)


# --------------------------------------------------------------------------
# Stop-loss level: percent and ATR, both sides
# --------------------------------------------------------------------------
class TestStopLossLevel:
    def test_percent_long_rounds_toward_entry(self) -> None:
        """entry 100, 2% -> raw 98.00; on a 0.13 tick it rounds *up* toward entry."""
        level = stop_loss_level(
            side=LONG,
            entry_price=D("100"),
            config=StopLossConfig(type=StopType.PERCENT, percent=D("2.0")),
            tick_size=D("0.13"),
        )
        assert level == D("98.02")
        assert D("100") - level <= D("2.0")  # never wider than configured

    def test_percent_short_rounds_toward_entry(self) -> None:
        """entry 100, 2% -> raw 102.00; on a 0.13 tick it rounds *down* toward entry."""
        level = stop_loss_level(
            side=SHORT,
            entry_price=D("100"),
            config=StopLossConfig(type=StopType.PERCENT, percent=D("2.0")),
            tick_size=D("0.13"),
        )
        assert level == D("101.92")
        assert level - D("100") <= D("2.0")

    def test_percent_clean_tick_is_exact(self) -> None:
        level = stop_loss_level(
            side=LONG,
            entry_price=D("100"),
            config=StopLossConfig(type=StopType.PERCENT, percent=D("2.0")),
            tick_size=D("0.01"),
        )
        assert level == D("98")

    def test_atr_long(self) -> None:
        """distance = multiplier(2) * atr(0.5) = 1.0; stop at 99.00."""
        level = stop_loss_level(
            side=LONG,
            entry_price=D("100"),
            config=StopLossConfig(type=StopType.ATR, atr_multiplier=D("2.0")),
            tick_size=D("0.01"),
            atr_value=0.5,
        )
        assert level == D("99.00")

    def test_atr_short(self) -> None:
        level = stop_loss_level(
            side=SHORT,
            entry_price=D("100"),
            config=StopLossConfig(type=StopType.ATR, atr_multiplier=D("2.0")),
            tick_size=D("0.01"),
            atr_value=0.5,
        )
        assert level == D("101.00")

    def test_disabled_returns_none(self) -> None:
        assert (
            stop_loss_level(
                side=LONG,
                entry_price=D("100"),
                config=StopLossConfig(enabled=False),
                tick_size=D("0.01"),
            )
            is None
        )


# --------------------------------------------------------------------------
# Take-profit level: percent and rr, both sides
# --------------------------------------------------------------------------
class TestTakeProfitLevel:
    def test_percent_long(self) -> None:
        level = take_profit_level(
            side=LONG,
            entry_price=D("100"),
            config=TakeProfitConfig(type=TakeProfitType.PERCENT, percent=D("4.0")),
            tick_size=D("0.01"),
        )
        assert level == D("104")

    def test_percent_short(self) -> None:
        level = take_profit_level(
            side=SHORT,
            entry_price=D("100"),
            config=TakeProfitConfig(type=TakeProfitType.PERCENT, percent=D("4.0")),
            tick_size=D("0.01"),
        )
        assert level == D("96")

    def test_rr_uses_stop_distance(self) -> None:
        """rr 2 on a 25-wide stop -> 50-wide target; long entry 500 -> 550."""
        level = take_profit_level(
            side=LONG,
            entry_price=D("500"),
            config=TakeProfitConfig(type=TakeProfitType.RR, rr_multiple=D("2.0")),
            tick_size=D("0.01"),
            stop_distance=D("25"),
        )
        assert level == D("550")

    def test_rr_without_stop_distance_raises(self) -> None:
        with pytest.raises(ValueError, match="stop_distance is required"):
            take_profit_level(
                side=LONG,
                entry_price=D("500"),
                config=TakeProfitConfig(type=TakeProfitType.RR, rr_multiple=D("2.0")),
                tick_size=D("0.01"),
                stop_distance=None,
            )

    def test_disabled_returns_none(self) -> None:
        assert (
            take_profit_level(
                side=LONG,
                entry_price=D("100"),
                config=TakeProfitConfig(enabled=False),
                tick_size=D("0.01"),
            )
            is None
        )


# --------------------------------------------------------------------------
# Directional rounding: the property every stop kind must satisfy
# --------------------------------------------------------------------------
# (entry, tick, percent) at awkward ticks. Distances are comfortably multi-tick.
# fmt: off
_STOP_ROUNDING_CASES: list[tuple[str, str, str]] = [
    ("100",       "0.13",   "2.0"),   # awkward tick, tight stop
    ("100",       "0.13",   "0.5"),   # tighter still
    ("65050.12",  "0.01",   "2.0"),   # BTC-like
    ("0.4523",    "0.0001", "3.0"),   # cheap asset
    ("7.77",      "0.07",   "1.0"),   # awkward tenth-ish
    ("13",        "0.25",   "2.0"),   # step that is not a power of ten
]
# fmt: on


class TestDirectionalRoundingInvariant:
    """A stop rounds toward its reference, so realized distance <= configured.

    This is the property that bounds risk: if the initial stop rounded *away*
    from entry, the realized loss would exceed the ``risk_per_trade`` budget.
    """

    @pytest.mark.parametrize(("entry", "tick", "percent"), _STOP_ROUNDING_CASES)
    @pytest.mark.parametrize("side", [LONG, SHORT])
    def test_percent_stop_never_wider_than_configured(
        self, side: PositionSide, entry: str, tick: str, percent: str
    ) -> None:
        e, t, p = D(entry), D(tick), D(percent)
        level = stop_loss_level(
            side=side,
            entry_price=e,
            config=StopLossConfig(type=StopType.PERCENT, percent=p),
            tick_size=t,
        )
        assert level is not None
        configured = e * p / D(100)
        realized = abs(e - level)
        assert realized <= configured  # the invariant
        assert level % t == 0  # exact tick multiple
        assert (level < e) if side is LONG else (level > e)  # correct side of entry

    @pytest.mark.parametrize(("entry", "tick", "percent"), _STOP_ROUNDING_CASES)
    @pytest.mark.parametrize("side", [LONG, SHORT])
    def test_trailing_stop_never_gives_back_more_than_configured(
        self, side: PositionSide, entry: str, tick: str, percent: str
    ) -> None:
        """The same invariant for the trailing stop, with the high-water mark as
        its reference: realized give-back <= configured ``trail_percent``."""
        e, t, trail = D(entry), D(tick), D(percent)
        # Drive the mark to +/-10% so the trail is comfortably activated.
        mark = e * D("1.10") if side is LONG else e * D("0.90")
        update = update_trailing_stop(
            side=side,
            entry_price=e,
            price=mark,
            high_water=None,
            existing_stop=None,
            config=TrailingStopConfig(
                enabled=True, activation_percent=D("0.5"), trail_percent=trail
            ),
            tick_size=t,
        )
        assert update.activated
        assert update.stop_price is not None
        configured = update.high_water * trail / D(100)
        realized = abs(update.high_water - update.stop_price)
        assert realized <= configured
        assert update.stop_price % t == 0


# --------------------------------------------------------------------------
# The ATR float -> Decimal boundary
# --------------------------------------------------------------------------
class TestAtrBoundary:
    def test_numpy_float64_converts_via_shortest_repr(self) -> None:
        """The realistic input: atr().iloc[-1] is a numpy.float64.

        multiplier 2 * (1/3) = 0.6666666666666666 (shortest repr), so a long stop
        at entry 100 rounds *up* toward entry to 99.34 -- not the binary-expansion
        value Decimal(np.float64(1/3)) would inject.
        """
        numpy = pytest.importorskip("numpy")
        atr = numpy.float64(1) / numpy.float64(3)
        level = stop_loss_level(
            side=LONG,
            entry_price=D("100"),
            config=StopLossConfig(type=StopType.ATR, atr_multiplier=D("2.0")),
            tick_size=D("0.01"),
            atr_value=atr,
        )
        assert level == D("99.34")

    def test_nan_atr_is_rejected(self) -> None:
        """ATR is NaN during warmup; Decimal(str(nan)) would silently poison a stop."""
        with pytest.raises(ValueError, match="must be finite"):
            stop_loss_level(
                side=LONG,
                entry_price=D("100"),
                config=StopLossConfig(type=StopType.ATR, atr_multiplier=D("2.0")),
                tick_size=D("0.01"),
                atr_value=float("nan"),
            )

    def test_infinite_atr_is_rejected(self) -> None:
        with pytest.raises(ValueError, match="must be finite"):
            stop_loss_level(
                side=LONG,
                entry_price=D("100"),
                config=StopLossConfig(type=StopType.ATR, atr_multiplier=D("2.0")),
                tick_size=D("0.01"),
                atr_value=float("inf"),
            )

    def test_negative_atr_is_rejected(self) -> None:
        """ATR is non-negative by construction, so a negative value is corrupt
        data (a wrong-sided stop otherwise), not a market state."""
        with pytest.raises(ValueError, match="must not be negative"):
            stop_loss_level(
                side=LONG,
                entry_price=D("100"),
                config=StopLossConfig(type=StopType.ATR, atr_multiplier=D("2.0")),
                tick_size=D("0.01"),
                atr_value=-1.0,
            )

    def test_atr_type_without_a_value_raises(self) -> None:
        with pytest.raises(ValueError, match="atr_value is required"):
            stop_loss_level(
                side=LONG,
                entry_price=D("100"),
                config=StopLossConfig(type=StopType.ATR, atr_multiplier=D("2.0")),
                tick_size=D("0.01"),
                atr_value=None,
            )


# --------------------------------------------------------------------------
# Trailing stop: activation, monotonicity, both sides
# --------------------------------------------------------------------------
class TestTrailingStop:
    def test_inactive_below_activation_threshold(self) -> None:
        """A 0.5% move does not reach a 1% activation; the stop is untouched."""
        update = update_trailing_stop(
            side=LONG,
            entry_price=D("100"),
            price=D("100.5"),
            high_water=None,
            existing_stop=None,
            config=TrailingStopConfig(
                enabled=True, activation_percent=D("1.0"), trail_percent=D("1.0")
            ),
            tick_size=D("0.01"),
        )
        assert update.activated is False
        assert update.stop_price is None
        assert update.high_water == D("100.5")

    def test_activates_and_rounds_toward_high_water(self) -> None:
        """110 high-water, 1% trail, 0.13 tick -> 108.94 (give-back 0.96% < 1%)."""
        update = update_trailing_stop(
            side=LONG,
            entry_price=D("100"),
            price=D("110"),
            high_water=None,
            existing_stop=None,
            config=TrailingStopConfig(
                enabled=True, activation_percent=D("1.0"), trail_percent=D("1.0")
            ),
            tick_size=D("0.13"),
        )
        assert update.activated is True
        assert update.stop_price == D("108.94")
        assert D("110") - update.stop_price <= D("110") * D("1.0") / D(100)

    def test_never_moves_against_a_long_across_a_sequence(self) -> None:
        """The stop ratchets up and never down, even as price pulls back."""
        cfg = TrailingStopConfig(enabled=True, activation_percent=D("0.5"), trail_percent=D("2.0"))
        prices = [D("101"), D("105"), D("103"), D("108"), D("102"), D("107")]
        high_water: Decimal | None = None
        stop: Decimal | None = None
        previous: Decimal | None = None
        for price in prices:
            update = update_trailing_stop(
                side=LONG,
                entry_price=D("100"),
                price=price,
                high_water=high_water,
                existing_stop=stop,
                config=cfg,
                tick_size=D("0.01"),
            )
            high_water, stop = update.high_water, update.stop_price
            if previous is not None and stop is not None:
                assert stop >= previous  # monotonic: never against the position
            if stop is not None:
                previous = stop
        assert high_water == D("108")  # the peak seen

    def test_never_moves_against_a_short_across_a_sequence(self) -> None:
        cfg = TrailingStopConfig(enabled=True, activation_percent=D("0.5"), trail_percent=D("2.0"))
        prices = [D("99"), D("95"), D("97"), D("92"), D("98"), D("93")]
        low_water: Decimal | None = None
        stop: Decimal | None = None
        previous: Decimal | None = None
        for price in prices:
            update = update_trailing_stop(
                side=SHORT,
                entry_price=D("100"),
                price=price,
                high_water=low_water,
                existing_stop=stop,
                config=cfg,
                tick_size=D("0.01"),
            )
            low_water, stop = update.high_water, update.stop_price
            if previous is not None and stop is not None:
                assert stop <= previous  # monotonic downward for a short
            if stop is not None:
                previous = stop
        assert low_water == D("92")


# --------------------------------------------------------------------------
# compute_protective_levels: the orchestrator, in order
# --------------------------------------------------------------------------
class TestComputeProtectiveLevels:
    def test_rr_take_profit_uses_the_realized_stop_distance(self) -> None:
        """Stop first, then rr target from the *rounded* distance.

        Awkward tick: the stop rounds to 98.02 (distance 1.98), so an rr-2 target
        is 100 + 2*1.98 = 103.96, not 104 -- the target composes with the stop
        that will actually be placed.
        """
        levels = compute_protective_levels(
            symbol="BTCUSDT",
            side=LONG,
            entry_price=D("100"),
            stop_loss=StopLossConfig(type=StopType.PERCENT, percent=D("2.0")),
            take_profit=TakeProfitConfig(type=TakeProfitType.RR, rr_multiple=D("2.0")),
            tick_size=D("0.13"),
        )
        assert levels.stop_loss == D("98.02")
        assert levels.stop_distance == D("1.98")
        assert levels.take_profit == D("103.87")  # 103.96 rounded down toward entry

    def test_both_disabled_is_representable(self) -> None:
        levels = compute_protective_levels(
            symbol="BTCUSDT",
            side=LONG,
            entry_price=D("100"),
            stop_loss=StopLossConfig(enabled=False),
            take_profit=TakeProfitConfig(enabled=False),
            tick_size=D("0.01"),
        )
        assert levels.stop_loss is None
        assert levels.take_profit is None
        assert levels.stop_distance is None

    def test_flat_side_is_rejected(self) -> None:
        with pytest.raises(ValueError, match="long or short"):
            compute_protective_levels(
                symbol="BTCUSDT",
                side=PositionSide.FLAT,
                entry_price=D("100"),
                stop_loss=StopLossConfig(),
                take_profit=TakeProfitConfig(),
                tick_size=D("0.01"),
            )

    def test_levels_carry_the_side_and_a_basis(self) -> None:
        levels = compute_protective_levels(
            symbol="ETHUSDT",
            side=LONG,
            entry_price=D("100"),
            stop_loss=StopLossConfig(type=StopType.PERCENT, percent=D("2.0")),
            take_profit=TakeProfitConfig(type=TakeProfitType.PERCENT, percent=D("4.0")),
            tick_size=D("0.01"),
        )
        assert levels.symbol == "ETHUSDT"
        assert levels.side is LONG
        assert "stop-loss" in levels.basis


# --------------------------------------------------------------------------
# ProtectiveLevels invariants (the type refuses an incoherent object)
# --------------------------------------------------------------------------
class TestProtectiveLevelsInvariants:
    def test_long_stop_above_entry_is_rejected(self) -> None:
        with pytest.raises(ValueError, match="must be below entry"):
            ProtectiveLevels(
                symbol="X",
                side=LONG,
                entry_price=D("100"),
                stop_loss=D("101"),
                stop_distance=D("1"),
                basis="bad",
            )

    def test_stop_distance_must_match(self) -> None:
        with pytest.raises(ValueError, match="stop_distance"):
            ProtectiveLevels(
                symbol="X",
                side=LONG,
                entry_price=D("100"),
                stop_loss=D("98"),
                stop_distance=D("5"),  # should be 2
                basis="bad",
            )

    def test_frozen(self) -> None:
        levels = ProtectiveLevels(symbol="X", side=LONG, entry_price=D("100"), basis="ok")
        with pytest.raises(ValueError, match="frozen"):
            levels.stop_loss = D("98")  # type: ignore[misc]


# --------------------------------------------------------------------------
# should_exit: precedence, both sides
# --------------------------------------------------------------------------
def _long_position(**levels: Decimal) -> Position:
    return Position(
        symbol="BTCUSDT",
        side=LONG,
        quantity=D("1"),
        entry_price=D("100"),
        entry_bar_time=BAR_TIME,
        protection=ProtectionState.UNKNOWN,
        **levels,
    )


class TestShouldExit:
    def test_no_trigger_returns_none(self) -> None:
        position = _long_position(stop_loss=D("98"), take_profit=D("104"))
        assert should_exit(position=position, price=D("101")) is None

    def test_stop_loss_triggers(self) -> None:
        position = _long_position(stop_loss=D("98"), take_profit=D("104"))
        decision = should_exit(position=position, price=D("97"))
        assert decision is not None
        assert decision.reason is ExitReason.STOP_LOSS
        assert decision.price == D("98")

    def test_stop_loss_boundary_is_inclusive(self) -> None:
        position = _long_position(stop_loss=D("98"))
        decision = should_exit(position=position, price=D("98"))
        assert decision is not None and decision.reason is ExitReason.STOP_LOSS

    def test_take_profit_triggers(self) -> None:
        position = _long_position(stop_loss=D("98"), take_profit=D("104"))
        decision = should_exit(position=position, price=D("105"))
        assert decision is not None
        assert decision.reason is ExitReason.TAKE_PROFIT
        assert decision.price == D("104")

    def test_stop_wins_when_both_trigger_and_reports_worst_fill(self) -> None:
        """A trailing stop that ratcheted above the take-profit: a price between
        them triggers both. The stop wins, and the exit price is the stop level
        (the worse fill), never the target."""
        position = _long_position(take_profit=D("104"), trailing_stop=D("106"))
        decision = should_exit(position=position, price=D("105"))
        assert decision is not None
        assert decision.reason is ExitReason.TRAILING_STOP
        assert decision.price == D("106")  # worst fill, not the 104 target

    def test_first_crossed_stop_binds_when_two_stops_trigger(self) -> None:
        """Both stop-loss and trailing fire; the higher (first hit falling) binds."""
        position = _long_position(stop_loss=D("98"), trailing_stop=D("99"))
        decision = should_exit(position=position, price=D("97"))
        assert decision is not None
        assert decision.reason is ExitReason.TRAILING_STOP
        assert decision.price == D("99")

    def test_short_stop_and_take_profit(self) -> None:
        position = Position(
            symbol="BTCUSDT",
            side=SHORT,
            quantity=D("1"),
            entry_price=D("100"),
            entry_bar_time=BAR_TIME,
            protection=ProtectionState.UNKNOWN,
            stop_loss=D("102"),
            take_profit=D("96"),
        )
        stop = should_exit(position=position, price=D("103"))
        assert stop is not None and stop.reason is ExitReason.STOP_LOSS and stop.price == D("102")
        target = should_exit(position=position, price=D("95"))
        assert target is not None and target.reason is ExitReason.TAKE_PROFIT

    def test_flat_position_never_exits(self) -> None:
        position = Position(
            symbol="BTCUSDT",
            side=PositionSide.FLAT,
            quantity=D("0"),
            entry_price=D("100"),
            entry_bar_time=BAR_TIME,
            protection=ProtectionState.UNKNOWN,
        )
        assert should_exit(position=position, price=D("50")) is None


# --------------------------------------------------------------------------
# Parameter validation
# --------------------------------------------------------------------------
class TestParameterValidation:
    @pytest.mark.parametrize("entry", [D("0"), D("-100")])
    def test_non_positive_entry_raises(self, entry: Decimal) -> None:
        with pytest.raises(ValueError, match="entry_price must be > 0"):
            stop_loss_level(
                side=LONG, entry_price=entry, config=StopLossConfig(), tick_size=D("0.01")
            )

    @pytest.mark.parametrize("price", [D("0"), D("-1")])
    def test_non_positive_price_raises_in_should_exit(self, price: Decimal) -> None:
        with pytest.raises(ValueError, match="price must be > 0"):
            should_exit(position=_long_position(stop_loss=D("98")), price=price)

    def test_flat_side_rejected_in_stop_level(self) -> None:
        with pytest.raises(ValueError, match="long or short"):
            stop_loss_level(
                side=PositionSide.FLAT,
                entry_price=D("100"),
                config=StopLossConfig(),
                tick_size=D("0.01"),
            )


# --------------------------------------------------------------------------
# Sub-tick distance is a representable outcome, not a raise
# --------------------------------------------------------------------------
class TestSubTickDistanceIsRepresentable:
    """A configured distance below one tick is a transient low-volatility state,
    not a config error: the level comes back None with a reason, and no exception
    reaches the engine's consecutive-failure quarantine.
    """

    def test_percent_stop_below_one_tick_returns_none(self) -> None:
        """0.001% of 100 is 0.001, below a 0.01 tick -- no placeable stop."""
        assert (
            stop_loss_level(
                side=LONG,
                entry_price=D("100"),
                config=StopLossConfig(type=StopType.PERCENT, percent=D("0.001")),
                tick_size=D("0.01"),
            )
            is None
        )

    def test_atr_stop_below_one_tick_returns_none(self) -> None:
        """A tiny ATR (a quiet market) puts the stop distance below one tick."""
        assert (
            stop_loss_level(
                side=LONG,
                entry_price=D("100"),
                config=StopLossConfig(type=StopType.ATR, atr_multiplier=D("2.0")),
                tick_size=D("0.01"),
                atr_value=0.001,
            )
            is None
        )

    def test_zero_atr_returns_none_not_raise(self) -> None:
        """A flat/frozen window (ATR 0) is the extreme of the same quiet state."""
        assert (
            stop_loss_level(
                side=LONG,
                entry_price=D("100"),
                config=StopLossConfig(type=StopType.ATR, atr_multiplier=D("2.0")),
                tick_size=D("0.01"),
                atr_value=0.0,
            )
            is None
        )

    def test_protective_levels_carry_a_none_stop_and_a_reason(self) -> None:
        levels = compute_protective_levels(
            symbol="BTCUSDT",
            side=LONG,
            entry_price=D("100"),
            stop_loss=StopLossConfig(type=StopType.PERCENT, percent=D("0.001")),
            take_profit=TakeProfitConfig(enabled=False),
            tick_size=D("0.01"),
        )
        assert levels.stop_loss is None
        assert levels.stop_distance is None
        assert "below one tick" in levels.basis

    def test_rr_target_is_representable_when_the_stop_is_sub_tick(self) -> None:
        """A sub-tick stop leaves no distance, so the rr target is None too --
        computed on the signal path without raising."""
        levels = compute_protective_levels(
            symbol="BTCUSDT",
            side=LONG,
            entry_price=D("100"),
            stop_loss=StopLossConfig(type=StopType.PERCENT, percent=D("0.001")),
            take_profit=TakeProfitConfig(type=TakeProfitType.RR, rr_multiple=D("2.0")),
            tick_size=D("0.01"),
        )
        assert levels.stop_loss is None
        assert levels.take_profit is None
        assert "rr target" in levels.basis


# --------------------------------------------------------------------------
# No float ever reaches a result -- structural, via the Money guard
# --------------------------------------------------------------------------
class TestNoFloatLeaks:
    def test_exit_decision_rejects_a_float(self) -> None:
        for bad in (1.5, float(Decimal("1.5"))):
            with pytest.raises(ValueError, match="must not be built from a float"):
                ExitDecision(symbol="X", reason=ExitReason.STOP_LOSS, price=bad, detail="x")

    def test_trailing_update_rejects_numpy_float64(self) -> None:
        numpy = pytest.importorskip("numpy")
        with pytest.raises(ValueError, match="must not be built from a float"):
            TrailingStopUpdate(high_water=numpy.float64(1.5), activated=True, detail="x")

    def test_protective_levels_reject_a_float_price(self) -> None:
        with pytest.raises(ValueError, match="must not be built from a float"):
            ProtectiveLevels(symbol="X", side=LONG, entry_price=100.0, basis="x")


# --------------------------------------------------------------------------
# The integration-style test: M2 stop composed with M1 sizing
# --------------------------------------------------------------------------
def _symbol_info(step_size: str = "0.001", tick: str = "0.01") -> SymbolInfo:
    return SymbolInfo(
        symbol="BTCUSDT",
        base_asset="BTC",
        quote_asset="USDT",
        price_tick=D(tick),
        step_size=D(step_size),
        min_qty=D("0"),
        min_notional=D("0"),
    )


class TestComposesWithSizing:
    @pytest.mark.parametrize("tick", ["0.01", "0.13", "0.25"])
    def test_realized_risk_at_stop_never_exceeds_the_budget(self, tick: str) -> None:
        """Compute a stop, size ``risk_per_trade`` from it, and prove that closing
        at that stop loses no more than the 1% budget -- the test that catches a
        rounding-direction mistake in the stop.
        """
        equity = D("10000")
        entry = D("500")
        budget = equity * D("0.01")  # risk_per_trade 1% -> 100 quote

        levels = compute_protective_levels(
            symbol="BTCUSDT",
            side=LONG,
            entry_price=entry,
            stop_loss=StopLossConfig(type=StopType.PERCENT, percent=D("5.0")),
            take_profit=TakeProfitConfig(enabled=False),
            tick_size=D(tick),
        )
        assert levels.stop_loss is not None and levels.stop_distance is not None

        decision = calculate_position_size(
            symbol_info=_symbol_info(tick=tick),
            equity=equity,
            price=entry,
            sizing=PositionSizingConfig(
                method=PositionSizingMethod.RISK_PER_TRADE, risk_per_trade=D("0.01")
            ),
            limits=RiskLimitsConfig(max_position_size_percent=D("100")),
            stop_price=levels.stop_loss,
        )
        realized_risk = decision.quantity * levels.stop_distance
        assert realized_risk <= budget
