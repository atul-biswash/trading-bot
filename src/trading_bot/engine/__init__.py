"""Engine: orchestration of the data -> strategy -> signal path.

Importing this package pulls in the data stack (pandas/NumPy) via the engine's
collaborators; the pure domain layer under ``trading_bot.core`` does not.
"""

from trading_bot.engine.live_engine import TradingEngine

__all__ = ["TradingEngine"]
