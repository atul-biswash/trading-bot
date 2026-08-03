"""Tests for position sizing.

Every assertion is an exact ``Decimal`` comparison. There is no tolerance
anywhere in this file, deliberately: a sizing result that is merely *close* is
a bug, and a test that tolerates closeness cannot detect the float leak this
layer exists to prevent.

Symbol filters are hand-built rather than fetched, with awkward-on-purpose step
sizes, because the interesting cases are all rounding boundaries.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from trading_bot.config.models import PositionSizingConfig, RiskLimitsConfig
from trading_bot.core.enums import OrderSide, OrderType, PositionSizingMethod
from trading_bot.core.models import OrderRequest, SizingDecision, SymbolInfo
from trading_bot.risk.position_sizing import (
    calculate_position_size,
    size_by_fixed_amount,
    size_by_fixed_fraction,
    size_by_risk_per_trade,
)


# --------------------------------------------------------------------------
# Fixtures: exchange filters shaped like the real ones
# --------------------------------------------------------------------------
def make_symbol_info(
    *,
    symbol: str = "BTCUSDT",
    step_size: str = "0.00001",
    min_qty: str = "0.00001",
    min_notional: str = "10",
    price_tick: str = "0.01",
) -> SymbolInfo:
    """Filters for one symbol. Strings in, so nothing is built from a float."""
    return SymbolInfo(
        symbol=symbol,
        base_asset="BTC",
        quote_asset="USDT",
        price_tick=Decimal(price_tick),
        step_size=Decimal(step_size),
        min_qty=Decimal(min_qty),
        min_notional=Decimal(min_notional),
    )


def make_sizing(
    *,
    method: PositionSizingMethod = PositionSizingMethod.FIXED_FRACTION,
    fraction: str = "0.02",
    fixed_amount: str = "100",
    risk_per_trade: str = "0.01",
) -> PositionSizingConfig:
    return PositionSizingConfig(
        method=method,
        fraction=Decimal(fraction),
        fixed_amount=Decimal(fixed_amount),
        risk_per_trade=Decimal(risk_per_trade),
    )


def make_limits(*, max_position_size_percent: str = "20") -> RiskLimitsConfig:
    return RiskLimitsConfig(max_position_size_percent=Decimal(max_position_size_percent))


# --------------------------------------------------------------------------
# The float -> Decimal config boundary
# --------------------------------------------------------------------------
class TestConfigDecimalBoundary:
    """The conversion happens once, in pydantic, and happens exactly."""

    def test_yaml_floats_become_exact_decimals(self) -> None:
        """``0.02`` from YAML must become ``Decimal("0.02")``, not the binary expansion.

        This is the entire justification for typing the config fields
        ``Decimal``. Converting naively at the use site instead -- ``Decimal``
        applied straight to the float pydantic was handed -- yields
        ``0.0200000000000000004163...``, which the last assertion pins down.
        """
        from_yaml = 0.02  # what yaml.safe_load actually produces
        config = PositionSizingConfig(fraction=from_yaml, fixed_amount=100.0, risk_per_trade=0.01)

        assert config.fraction == Decimal("0.02")
        assert config.fixed_amount == Decimal("100")
        assert config.risk_per_trade == Decimal("0.01")
        assert config.fraction != Decimal(from_yaml)  # the leak we are avoiding
        assert str(Decimal(from_yaml)).startswith("0.0200000000000000004")

    def test_sizing_fields_are_decimal_not_float(self) -> None:
        """Guards the reversion: ``Decimal * float`` raises ``TypeError`` in Python.

        If someone re-declares these as ``float``, sizing does not silently lose
        precision -- it stops working entirely, at runtime, inside the trading
        loop. This test moves that failure to the suite.
        """
        config = PositionSizingConfig()
        limits = RiskLimitsConfig()

        for value in (config.fraction, config.fixed_amount, config.risk_per_trade):
            assert isinstance(value, Decimal)
            assert not isinstance(value, float)
        assert isinstance(limits.max_position_size_percent, Decimal)

        # The arithmetic sizing actually performs.
        assert Decimal("10000") * config.fraction == Decimal("200.00")

    def test_pydantic_constraints_survive_the_type_change(self) -> None:
        for bad in (0, -0.1, 1.5):
            with pytest.raises(ValueError, match="fraction"):
                PositionSizingConfig(fraction=bad)


# --------------------------------------------------------------------------
# The three methods, in isolation
# --------------------------------------------------------------------------
class TestSizingMethods:
    def test_fixed_fraction(self) -> None:
        """2% of 10 000 is 200 quote; at a price of 50, that is 4 units."""
        quantity = size_by_fixed_fraction(
            equity=Decimal("10000"), price=Decimal("50"), fraction=Decimal("0.02")
        )
        assert quantity == Decimal("4")

    def test_fixed_amount_ignores_equity(self) -> None:
        """The method is defined without reference to account size."""
        quantity = size_by_fixed_amount(price=Decimal("250"), amount=Decimal("100"))
        assert quantity == Decimal("0.4")

    def test_risk_per_trade_holds_the_loss_constant(self) -> None:
        """1% of 10 000 is 100 risked; a 25-wide stop buys 4 units.

        Losing 4 units from 500 down to 475 is exactly 100 quote -- which is
        what the method promises, and the assertion below states it directly
        rather than trusting the formula.
        """
        entry, stop = Decimal("500"), Decimal("475")
        quantity = size_by_risk_per_trade(
            equity=Decimal("10000"),
            entry_price=entry,
            stop_price=stop,
            risk_fraction=Decimal("0.01"),
        )
        assert quantity == Decimal("4")
        assert quantity * (entry - stop) == Decimal("100")

    def test_risk_per_trade_is_independent_of_entry_price(self) -> None:
        """Same stop width, very different price: same quantity.

        This is the property that distinguishes the method from
        ``fixed_fraction``, so it is asserted rather than implied.
        """
        common = {"equity": Decimal("10000"), "risk_fraction": Decimal("0.01")}
        near = size_by_risk_per_trade(
            entry_price=Decimal("500"), stop_price=Decimal("475"), **common
        )
        far = size_by_risk_per_trade(
            entry_price=Decimal("9000"), stop_price=Decimal("8975"), **common
        )
        assert near == far == Decimal("4")

    def test_risk_per_trade_accepts_either_stop_side(self) -> None:
        """Sizing needs a width; which side the stop belongs on is not its call."""
        common = {
            "equity": Decimal("10000"),
            "entry_price": Decimal("500"),
            "risk_fraction": Decimal("0.01"),
        }
        assert size_by_risk_per_trade(
            stop_price=Decimal("475"), **common
        ) == size_by_risk_per_trade(stop_price=Decimal("525"), **common)


# --------------------------------------------------------------------------
# Parameter validation
# --------------------------------------------------------------------------
# fmt: off
_NON_POSITIVE_CASES: list[tuple[str, dict[str, Decimal]]] = [
    ("equity",   {"equity": Decimal("0"),   "price": Decimal("50"), "fraction": Decimal("0.02")}),
    ("equity",   {"equity": Decimal("-1"),  "price": Decimal("50"), "fraction": Decimal("0.02")}),
    ("price",    {"equity": Decimal("100"), "price": Decimal("0"),  "fraction": Decimal("0.02")}),
    ("price",    {"equity": Decimal("100"), "price": Decimal("-5"), "fraction": Decimal("0.02")}),
    ("fraction", {"equity": Decimal("100"), "price": Decimal("50"), "fraction": Decimal("0")}),
    ("fraction", {"equity": Decimal("100"), "price": Decimal("50"), "fraction": Decimal("-0.1")}),
]
# fmt: on


class TestParameterValidation:
    @pytest.mark.parametrize(("name", "kwargs"), _NON_POSITIVE_CASES)
    def test_non_positive_inputs_raise(self, name: str, kwargs: dict[str, Decimal]) -> None:
        with pytest.raises(ValueError, match=f"{name} must be > 0"):
            size_by_fixed_fraction(**kwargs)

    def test_zero_width_stop_raises_rather_than_dividing(self) -> None:
        with pytest.raises(ValueError, match="must differ from entry_price"):
            size_by_risk_per_trade(
                equity=Decimal("10000"),
                entry_price=Decimal("500"),
                stop_price=Decimal("500"),
                risk_fraction=Decimal("0.01"),
            )

    def test_risk_per_trade_without_a_stop_raises(self) -> None:
        """A missing stop is a config error, not a per-signal condition.

        Falling back to another method would silently size by a rule the
        operator did not configure -- the failure mode this rejects.
        """
        with pytest.raises(ValueError, match="stop_price is required"):
            calculate_position_size(
                symbol_info=make_symbol_info(),
                equity=Decimal("10000"),
                price=Decimal("500"),
                sizing=make_sizing(method=PositionSizingMethod.RISK_PER_TRADE),
                limits=make_limits(),
                stop_price=None,
            )

    @pytest.mark.parametrize("equity", [Decimal("0"), Decimal("-100")])
    def test_zero_or_negative_equity_raises(self, equity: Decimal) -> None:
        """An empty account reaching the sizer means an upstream gate failed.

        Returning a plausible "no trade" would hide that; raising surfaces it.
        """
        with pytest.raises(ValueError, match="equity must be > 0"):
            calculate_position_size(
                symbol_info=make_symbol_info(),
                equity=equity,
                price=Decimal("500"),
                sizing=make_sizing(),
                limits=make_limits(),
            )

    @pytest.mark.parametrize("price", [Decimal("0"), Decimal("-500")])
    def test_non_positive_price_raises(self, price: Decimal) -> None:
        with pytest.raises(ValueError, match="price must be > 0"):
            calculate_position_size(
                symbol_info=make_symbol_info(),
                equity=Decimal("10000"),
                price=price,
                sizing=make_sizing(),
                limits=make_limits(),
            )


# --------------------------------------------------------------------------
# Rounding: always down, always to a whole lot
# --------------------------------------------------------------------------
# (step_size, price, expected quantity) at equity 10 000, fraction 2% -> 200 quote.
# fmt: off
_ROUNDING_CASES: list[tuple[str, str, str]] = [
    ("0.00001",  "65050.12", "0.00307"),      # BTC-like: 8 dp price, 5 dp lot
    ("0.001",    "3210.77",  "0.062"),        # ETH-like
    ("1",        "0.4523",   "442"),          # whole-lot asset
    ("0.1",      "7.77",     "25.7"),         # awkward tenth
    ("0.25",     "13",       "15.25"),        # step that is not a power of ten
]
# fmt: on


class TestRounding:
    @pytest.mark.parametrize(("step_size", "price", "expected"), _ROUNDING_CASES)
    def test_rounds_down_to_step_size(self, step_size: str, price: str, expected: str) -> None:
        decision = calculate_position_size(
            symbol_info=make_symbol_info(step_size=step_size, min_qty="0", min_notional="0"),
            equity=Decimal("10000"),
            price=Decimal(price),
            sizing=make_sizing(),
            limits=make_limits(max_position_size_percent="100"),
        )
        assert decision.quantity == Decimal(expected)

    @pytest.mark.parametrize(("step_size", "price", "expected"), _ROUNDING_CASES)
    def test_rounded_quantity_is_an_exact_lot_multiple(
        self, step_size: str, price: str, expected: str
    ) -> None:
        """Not merely close to a multiple -- exactly one, with no remainder."""
        decision = calculate_position_size(
            symbol_info=make_symbol_info(step_size=step_size, min_qty="0", min_notional="0"),
            equity=Decimal("10000"),
            price=Decimal(price),
            sizing=make_sizing(),
            limits=make_limits(max_position_size_percent="100"),
        )
        assert decision.quantity % Decimal(step_size) == 0

    def test_rounding_never_increases_the_order(self) -> None:
        """Rounding up could overspend the balance; the result must not exceed the ask."""
        decision = calculate_position_size(
            symbol_info=make_symbol_info(step_size="0.001", min_notional="0"),
            equity=Decimal("10000"),
            price=Decimal("3210.77"),
            sizing=make_sizing(),
            limits=make_limits(max_position_size_percent="100"),
        )
        assert decision.quantity <= decision.requested_quantity
        assert decision.quantity * Decimal("3210.77") <= Decimal("200")

    def test_exact_multiple_is_left_alone(self) -> None:
        """Rounding must be a no-op when the size already lands on a lot boundary."""
        decision = calculate_position_size(
            symbol_info=make_symbol_info(step_size="0.001", min_notional="0"),
            equity=Decimal("10000"),
            price=Decimal("50"),
            sizing=make_sizing(),
            limits=make_limits(max_position_size_percent="100"),
        )
        assert decision.quantity == Decimal("4")
        assert decision.quantity == decision.requested_quantity


# --------------------------------------------------------------------------
# The max_position_size_percent cap
# --------------------------------------------------------------------------
class TestPositionCap:
    def test_cap_binds_and_is_reported(self) -> None:
        """``fixed_amount`` of 5 000 on 10 000 equity is capped to 20% = 2 000."""
        decision = calculate_position_size(
            symbol_info=make_symbol_info(step_size="0.001"),
            equity=Decimal("10000"),
            price=Decimal("100"),
            sizing=make_sizing(method=PositionSizingMethod.FIXED_AMOUNT, fixed_amount="5000"),
            limits=make_limits(max_position_size_percent="20"),
        )
        assert decision.quantity == Decimal("20")  # 2 000 quote / 100
        assert decision.requested_quantity == Decimal("50")  # what was asked for
        assert "capped" in decision.reason

    def test_cap_is_silent_when_it_does_not_bind(self) -> None:
        decision = calculate_position_size(
            symbol_info=make_symbol_info(step_size="0.001"),
            equity=Decimal("10000"),
            price=Decimal("100"),
            sizing=make_sizing(fraction="0.02"),
            limits=make_limits(max_position_size_percent="20"),
        )
        assert decision.quantity == Decimal("2")
        assert "capped" not in decision.reason

    def test_cap_applies_to_every_method(self) -> None:
        """Including ``risk_per_trade``, where a tight stop can ask for a huge size.

        A 0.1-wide stop on a 100 price asks for 1 000 units -- 100 000 quote on
        10 000 of equity. Without the cap that is a 10x leveraged order.
        """
        decision = calculate_position_size(
            symbol_info=make_symbol_info(step_size="0.001"),
            equity=Decimal("10000"),
            price=Decimal("100"),
            sizing=make_sizing(method=PositionSizingMethod.RISK_PER_TRADE, risk_per_trade="0.01"),
            limits=make_limits(max_position_size_percent="20"),
            stop_price=Decimal("99.9"),
        )
        assert decision.requested_quantity == Decimal("1000")
        assert decision.quantity == Decimal("20")
        assert decision.quantity * Decimal("100") == Decimal("2000")

    def test_cap_is_never_exceeded_after_rounding(self) -> None:
        """Cap first, round down second -- so rounding cannot push back over."""
        equity, price = Decimal("10000"), Decimal("333.33")
        decision = calculate_position_size(
            symbol_info=make_symbol_info(step_size="0.01", min_notional="0"),
            equity=equity,
            price=price,
            sizing=make_sizing(method=PositionSizingMethod.FIXED_AMOUNT, fixed_amount="9000"),
            limits=make_limits(max_position_size_percent="20"),
        )
        assert decision.quantity * price <= equity * Decimal("20") / Decimal("100")


# --------------------------------------------------------------------------
# Exchange filters: a zero result is a valid answer
# --------------------------------------------------------------------------
class TestFilterRejection:
    def test_below_min_notional_returns_zero_not_an_exception(self) -> None:
        """The routine small-account case: 2% of 100 is 2 quote, minimum is 10."""
        decision = calculate_position_size(
            symbol_info=make_symbol_info(min_notional="10", min_qty="0"),
            equity=Decimal("100"),
            price=Decimal("50"),
            sizing=make_sizing(),
            limits=make_limits(),
        )
        assert decision.quantity == Decimal(0)
        assert not decision.is_tradeable
        assert "min_notional" in decision.reason
        assert decision.requested_quantity == Decimal("0.04")  # how close we were

    def test_below_min_qty_returns_zero(self) -> None:
        decision = calculate_position_size(
            symbol_info=make_symbol_info(step_size="0.00001", min_qty="1", min_notional="0"),
            equity=Decimal("10000"),
            price=Decimal("65050.12"),
            sizing=make_sizing(),
            limits=make_limits(),
        )
        assert decision.quantity == Decimal(0)
        assert "min_qty" in decision.reason

    def test_size_smaller_than_one_lot_returns_zero(self) -> None:
        """A coarse lot step on a small account rounds the whole order away."""
        decision = calculate_position_size(
            symbol_info=make_symbol_info(step_size="1", min_qty="0", min_notional="0"),
            equity=Decimal("1000"),
            price=Decimal("65050.12"),
            sizing=make_sizing(),
            limits=make_limits(),
        )
        assert decision.quantity == Decimal(0)
        assert "rounds to zero" in decision.reason

    def test_a_rejection_still_names_the_symbol_and_the_rule(self) -> None:
        """An operator must be able to tell *why* a bot is not trading."""
        decision = calculate_position_size(
            symbol_info=make_symbol_info(symbol="ETHUSDT", min_notional="10", min_qty="0"),
            equity=Decimal("100"),
            price=Decimal("50"),
            sizing=make_sizing(),
            limits=make_limits(),
        )
        assert decision.symbol == "ETHUSDT"
        assert decision.reason.startswith("no trade (fixed_fraction)")

    def test_exactly_at_min_notional_is_accepted(self) -> None:
        """The filter is a floor, not a strict inequality -- boundary must trade."""
        decision = calculate_position_size(
            symbol_info=make_symbol_info(step_size="0.1", min_qty="0", min_notional="10"),
            equity=Decimal("500"),
            price=Decimal("50"),
            sizing=make_sizing(fraction="0.02"),
            limits=make_limits(),
        )
        assert decision.quantity == Decimal("0.2")
        assert decision.quantity * Decimal("50") == Decimal("10")
        assert decision.is_tradeable


# --------------------------------------------------------------------------
# min_notional binds at the lowest price the trade will carry
# --------------------------------------------------------------------------
class TestNotionalBindsAtTheStop:
    """Binance evaluates ``stopPrice * quantity`` for an algo order too.

    A protective stop rests below the entry on a long, so it carries the smaller
    notional. Sizing that measured only the entry produced quantities the
    exchange rejects with ``-1013 Filter failure: NOTIONAL`` -- observed live on
    Binance Spot Testnet before this check existed.
    """

    def test_clears_at_entry_but_fails_at_the_stop_is_refused(self) -> None:
        """The exact case the old code passed and the exchange rejected.

        0.2 at 50 is exactly 10 -- the floor. The same 0.2 at the stop price of
        45 is 9, which is below it. The trade must be refused.
        """
        decision = calculate_position_size(
            symbol_info=make_symbol_info(step_size="0.1", min_qty="0", min_notional="10"),
            equity=Decimal("500"),
            price=Decimal("50"),
            sizing=make_sizing(fraction="0.02"),
            limits=make_limits(),
            stop_price=Decimal("45"),
        )
        assert decision.quantity == Decimal(0)
        assert not decision.is_tradeable
        # Exact, not approximate: 0.2 * 45, never 8.999999...
        assert decision.requested_quantity * Decimal("45") == Decimal("9.0")

    def test_the_reason_names_the_binding_price_not_the_entry(self) -> None:
        """An operator must be able to see *which* price refused the trade."""
        decision = calculate_position_size(
            symbol_info=make_symbol_info(step_size="0.1", min_qty="0", min_notional="10"),
            equity=Decimal("500"),
            price=Decimal("50"),
            sizing=make_sizing(fraction="0.02"),
            limits=make_limits(),
            stop_price=Decimal("45"),
        )
        assert "at 45" in decision.reason
        assert "min_notional" in decision.reason

    def test_a_stop_that_still_clears_the_floor_trades(self) -> None:
        """The check is a floor at the stop, not a blanket penalty."""
        decision = calculate_position_size(
            symbol_info=make_symbol_info(step_size="0.1", min_qty="0", min_notional="10"),
            equity=Decimal("1000"),
            price=Decimal("50"),
            sizing=make_sizing(fraction="0.02"),
            limits=make_limits(),
            stop_price=Decimal("45"),
        )
        assert decision.quantity == Decimal("0.4")
        assert decision.quantity * Decimal("45") == Decimal("18")
        assert decision.is_tradeable

    def test_no_stop_price_falls_back_to_the_entry_price(self) -> None:
        """Stops disabled: there is no lower leg, so the entry is the floor."""
        decision = calculate_position_size(
            symbol_info=make_symbol_info(step_size="0.1", min_qty="0", min_notional="10"),
            equity=Decimal("500"),
            price=Decimal("50"),
            sizing=make_sizing(fraction="0.02"),
            limits=make_limits(),
        )
        assert decision.quantity == Decimal("0.2")
        assert decision.is_tradeable

    def test_a_stop_above_the_entry_does_not_relax_the_floor(self) -> None:
        """``min``, not ``stop_price``: the function stays side-agnostic.

        Unreachable on spot (a long's stop is below entry), but
        ``size_by_risk_per_trade`` takes an absolute distance and does not assume
        a side, so this one must not either. Using ``stop_price`` directly would
        raise the measured notional here and let a sub-minimum trade through.
        """
        decision = calculate_position_size(
            symbol_info=make_symbol_info(step_size="0.1", min_qty="0", min_notional="10"),
            equity=Decimal("495"),
            price=Decimal("49.5"),
            sizing=make_sizing(fraction="0.02"),
            limits=make_limits(),
            stop_price=Decimal("60"),
        )
        # 0.2 at the entry of 49.5 is 9.9 -- below the floor of 10. At the stop
        # of 60 it would be 12, which clears. The entry must win.
        assert decision.quantity == Decimal(0)
        assert "at 49.5" in decision.reason


# --------------------------------------------------------------------------
# SizingDecision invariants
# --------------------------------------------------------------------------
class TestSizingDecisionInvariants:
    def test_quantity_may_not_exceed_requested(self) -> None:
        """Makes "sizing never rounds up" a property of the type.

        Capping and rounding both only reduce, so a decision that claims
        otherwise is a bug and cannot be constructed.
        """
        with pytest.raises(ValueError, match="exceeds requested"):
            SizingDecision(
                symbol="BTCUSDT",
                quantity=Decimal("2"),
                requested_quantity=Decimal("1"),
                reason="impossible",
            )

    def test_a_zero_quantity_must_still_carry_a_reason(self) -> None:
        with pytest.raises(ValueError, match="reason must explain"):
            SizingDecision(
                symbol="BTCUSDT",
                quantity=Decimal(0),
                requested_quantity=Decimal(0),
                reason="",
            )

    def test_negative_quantities_are_rejected(self) -> None:
        with pytest.raises(ValueError, match="must not be negative"):
            SizingDecision(
                symbol="BTCUSDT",
                quantity=Decimal("-1"),
                requested_quantity=Decimal("1"),
                reason="short on spot is not a thing",
            )

    def test_decision_is_frozen(self) -> None:
        decision = SizingDecision(
            symbol="BTCUSDT",
            quantity=Decimal("1"),
            requested_quantity=Decimal("1"),
            reason="ok",
        )
        with pytest.raises(ValueError, match="frozen"):
            decision.quantity = Decimal("2")  # type: ignore[misc]


# --------------------------------------------------------------------------
# No float ever reaches the result -- structurally, not by inspection
# --------------------------------------------------------------------------
class TestNoFloatLeaks:
    def test_the_money_guard_rejects_a_float_decision(self) -> None:
        """The structural claim, stated as a test.

        ``SizingDecision.quantity`` is a ``Money`` field, so a float cannot be
        stored in one even deliberately. Any sizing path that produced a float
        would fail at construction rather than return a lossy number -- which is
        why the tests below can assert the *type* is safe by construction.
        """
        for bad in (0.5, float(Decimal("0.5"))):
            with pytest.raises(ValueError, match="must not be built from a float"):
                SizingDecision(
                    symbol="BTCUSDT",
                    quantity=bad,
                    requested_quantity=Decimal("1"),
                    reason="float smuggled in",
                )

    def test_numpy_float64_is_rejected_too(self) -> None:
        """The realistic leak path: ``DataFrame.iloc`` returns ``numpy.float64``."""
        numpy = pytest.importorskip("numpy")
        with pytest.raises(ValueError, match="must not be built from a float"):
            SizingDecision(
                symbol="BTCUSDT",
                quantity=numpy.float64(0.5),
                requested_quantity=Decimal("1"),
                reason="frame value smuggled in",
            )

    def test_a_sized_quantity_is_accepted_by_a_money_field(self) -> None:
        """End to end: the sizer's output survives the domain's float guard.

        Building a real ``OrderRequest`` from it is the strongest available
        statement that the number is domain-legal, because ``OrderRequest``
        applies exactly the same guard execution will.
        """
        decision = calculate_position_size(
            symbol_info=make_symbol_info(),
            equity=Decimal("10000"),
            price=Decimal("65050.12"),
            sizing=make_sizing(),
            limits=make_limits(),
        )
        request = OrderRequest(
            symbol=decision.symbol,
            side=OrderSide.BUY,
            type=OrderType.MARKET,
            quantity=decision.quantity,
        )
        assert isinstance(request.quantity, Decimal)
        assert not isinstance(request.quantity, float)
        assert request.quantity == decision.quantity

    def test_every_method_returns_a_decimal(self) -> None:
        results = [
            size_by_fixed_fraction(
                equity=Decimal("10000"), price=Decimal("50"), fraction=Decimal("0.02")
            ),
            size_by_fixed_amount(price=Decimal("50"), amount=Decimal("100")),
            size_by_risk_per_trade(
                equity=Decimal("10000"),
                entry_price=Decimal("500"),
                stop_price=Decimal("475"),
                risk_fraction=Decimal("0.01"),
            ),
        ]
        for value in results:
            assert isinstance(value, Decimal)
            assert not isinstance(value, float)
