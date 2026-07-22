"""RSI mean-reversion strategy.

STUB — logic is implemented in the strategy phase. RSI below oversold -> BUY;
RSI above overbought -> CLOSE.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from trading_bot.core.models import Signal
from trading_bot.strategies.base import BaseStrategy
from trading_bot.strategies.registry import register_strategy

if TYPE_CHECKING:  # pragma: no cover
    import pandas as pd


@register_strategy("rsi")
class RsiStrategy(BaseStrategy):
    def __init__(
        self, period: int = 14, oversold: float = 30.0, overbought: float = 70.0
    ) -> None:
        super().__init__(period=period, oversold=oversold, overbought=overbought)
        self.period = period
        self.oversold = oversold
        self.overbought = overbought

    @property
    def warmup_period(self) -> int:
        return self.period + 1

    def generate_signal(self, symbol: str, candles: "pd.DataFrame") -> Signal | None:
        raise NotImplementedError("Implemented in the strategy phase.")
