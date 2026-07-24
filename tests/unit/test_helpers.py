"""Tests for pure helper functions."""

from __future__ import annotations

from decimal import ROUND_CEILING, ROUND_FLOOR, Decimal

import pytest

from trading_bot.utils.helpers import (
    clamp,
    round_price,
    round_step_size,
    round_to_tick,
    timeframe_to_ms,
)


def test_round_step_size_rounds_down() -> None:
    assert round_step_size(Decimal("1.23456"), Decimal("0.001")) == Decimal("1.234")
    assert round_step_size(Decimal("10"), Decimal("0.5")) == Decimal("10.0")
    assert round_step_size(Decimal("0.4"), Decimal("1")) == Decimal("0")


def test_round_step_size_zero_step_is_noop() -> None:
    assert round_step_size(Decimal("1.5"), Decimal("0")) == Decimal("1.5")


def test_round_price_rounds_down_to_tick() -> None:
    assert round_price(Decimal("100.079"), Decimal("0.01")) == Decimal("100.07")


def test_round_to_tick_honours_the_direction() -> None:
    # Same value, opposite modes, on an awkward tick.
    assert round_to_tick(Decimal("100.00"), Decimal("0.13"), rounding=ROUND_CEILING) == Decimal("100.10")
    assert round_to_tick(Decimal("100.00"), Decimal("0.13"), rounding=ROUND_FLOOR) == Decimal("99.97")


def test_round_to_tick_exact_multiple_is_unchanged() -> None:
    assert round_to_tick(Decimal("99.97"), Decimal("0.13"), rounding=ROUND_CEILING) == Decimal("99.97")


def test_round_to_tick_zero_tick_is_noop() -> None:
    assert round_to_tick(Decimal("1.5"), Decimal("0"), rounding=ROUND_FLOOR) == Decimal("1.5")


def test_timeframe_to_ms_known() -> None:
    assert timeframe_to_ms("1m") == 60_000
    assert timeframe_to_ms("1h") == 3_600_000
    assert timeframe_to_ms("1d") == 86_400_000


def test_timeframe_to_ms_unknown_raises() -> None:
    with pytest.raises(ValueError):
        timeframe_to_ms("7m")


def test_clamp() -> None:
    assert clamp(5, 0, 10) == 5
    assert clamp(-1, 0, 10) == 0
    assert clamp(99, 0, 10) == 10
