"""Risk management: position sizing, protective exits, and limit enforcement.

``position_sizing`` and ``rules`` are pure, side-effect-free calculation --
every rule is testable by calling it with numbers. ``manager`` composes them
into the decision the engine acts on; it reads market data and a clock, but
performs no I/O.
"""

from trading_bot.risk.manager import (
    Clock,
    PairContext,
    RiskAssessment,
    RiskManager,
    TradeIntent,
)
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
    "Clock",
    "ExitDecision",
    "ExitReason",
    "PairContext",
    "ProtectiveLevels",
    "RiskAssessment",
    "RiskManager",
    "TradeIntent",
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
