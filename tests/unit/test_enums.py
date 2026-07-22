"""Tests for domain enum behaviour."""

from __future__ import annotations

from trading_bot.core.enums import OrderSide, OrderStatus, TradingMode


def test_order_side_opposite() -> None:
    assert OrderSide.BUY.opposite is OrderSide.SELL
    assert OrderSide.SELL.opposite is OrderSide.BUY


def test_order_status_open_closed() -> None:
    assert OrderStatus.NEW.is_open
    assert OrderStatus.PARTIALLY_FILLED.is_open
    assert OrderStatus.FILLED.is_closed
    assert not OrderStatus.CANCELED.is_open


def test_trading_mode_flags() -> None:
    assert TradingMode.LIVE.uses_real_money
    assert not TradingMode.TESTNET.uses_real_money
    assert TradingMode.TESTNET.is_live_connection
    assert not TradingMode.PAPER.is_live_connection
    assert not TradingMode.BACKTEST.is_live_connection
