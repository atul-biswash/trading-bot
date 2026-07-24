"""Risk management: position sizing, protective exits, and limit enforcement.

Pure, side-effect-free calculation. Nothing here performs I/O, so every rule is
testable by calling it with numbers.
"""

from trading_bot.risk.position_sizing import (
    calculate_position_size,
    size_by_fixed_amount,
    size_by_fixed_fraction,
    size_by_risk_per_trade,
)

__all__ = [
    "calculate_position_size",
    "size_by_fixed_amount",
    "size_by_fixed_fraction",
    "size_by_risk_per_trade",
]
