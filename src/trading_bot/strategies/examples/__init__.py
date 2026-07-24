"""Example strategies.

Importing this package runs each module's ``@register_strategy`` decorator so
the strategies become discoverable through the registry.
"""

from __future__ import annotations

from trading_bot.strategies.examples import rsi_strategy, sma_crossover

__all__ = ["rsi_strategy", "sma_crossover"]
