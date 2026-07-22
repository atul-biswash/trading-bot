"""Example strategies.

Importing this package runs each module's ``@register_strategy`` decorator so
the strategies become discoverable through the registry.
"""

from __future__ import annotations

from trading_bot.strategies.examples import rsi_strategy, sma_crossover  # noqa: F401

__all__ = ["sma_crossover", "rsi_strategy"]
