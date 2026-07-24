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

__all__ = [
    "ExitDecision",
    "ExitReason",
    "ProtectiveLevels",
    "TrailingStopUpdate",
    "calculate_position_size",
    "compute_protective_levels",
    "should_exit",
    "size_by_fixed_amount",
    "size_by_fixed_fraction",
    "size_by_risk_per_trade",
    "stop_loss_level",
    "take_profit_level",
    "update_trailing_stop",
]
