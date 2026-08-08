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


def test_pending_cancel_is_open_because_a_cancel_in_flight_still_rests() -> None:
    """A cancel that has not completed leaves the order on the book, where it
    can still fill. Under the old whitelist this read ``is_closed``, and no
    test covered it -- which is why the inversion needed this one.
    """
    assert OrderStatus.PENDING_CANCEL.is_open
    assert not OrderStatus.PENDING_CANCEL.is_closed


def test_pending_new_is_open_so_a_pending_protective_leg_stays_watched() -> None:
    """Every protective leg of an order list sits at ``PENDING_NEW`` from
    placement until the working order fills. Reading that as terminal would
    stop a reconciler watching the one state protection spends its life in.
    """
    assert OrderStatus.PENDING_NEW.is_open


def test_the_terminal_set_is_exactly_these_four() -> None:
    """Anti-rot: the split is a partition, and both halves are pinned.

    Pinning only the closed half would not bite on an *added* member, because
    a blacklist lands new members open by construction. Pinning both means a
    new status fails here until somebody classifies it deliberately -- and
    moving one into the terminal set, the direction that costs a reconciler
    its watch, cannot happen quietly either.
    """
    closed = {status for status in OrderStatus if status.is_closed}
    still_open = {status for status in OrderStatus if status.is_open}

    assert closed == {
        OrderStatus.FILLED,
        OrderStatus.CANCELED,
        OrderStatus.REJECTED,
        OrderStatus.EXPIRED,
    }
    assert still_open == {
        OrderStatus.NEW,
        OrderStatus.PARTIALLY_FILLED,
        OrderStatus.PENDING_CANCEL,
        OrderStatus.PENDING_NEW,
        OrderStatus.EXPIRED_IN_MATCH,
    }
    assert closed | still_open == set(OrderStatus)  # every member classified
    assert not closed & still_open  # and none of them twice


def test_trading_mode_flags() -> None:
    assert TradingMode.LIVE.uses_real_money
    assert not TradingMode.TESTNET.uses_real_money
    assert TradingMode.TESTNET.is_live_connection
    assert not TradingMode.PAPER.is_live_connection
    assert not TradingMode.BACKTEST.is_live_connection
