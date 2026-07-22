"""Simple moving-average crossover strategy.

STUB — logic is implemented in the strategy phase. Golden cross (fast SMA
crosses above slow SMA) -> BUY; death cross -> CLOSE. Registered now so the
registry and config wiring can be exercised end to end.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from trading_bot.core.models import Signal
from trading_bot.strategies.base import BaseStrategy
from trading_bot.strategies.registry import register_strategy

if TYPE_CHECKING:  # pragma: no cover
    import pandas as pd


@register_strategy("sma_crossover")
class SmaCrossoverStrategy(BaseStrategy):
    def __init__(self, fast_period: int = 20, slow_period: int = 50) -> None:
        super().__init__(fast_period=fast_period, slow_period=slow_period)
        self.fast_period = fast_period
        self.slow_period = slow_period

    @property
    def warmup_period(self) -> int:
        return self.slow_period + 1

    def generate_signal(self, symbol: str, candles: "pd.DataFrame") -> Signal | None:
        raise NotImplementedError("Implemented in the strategy phase.")
