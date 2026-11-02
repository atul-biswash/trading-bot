"""C3 ``sma_cross_1d_50_200``: the 1d SMA(50) crosses above the 1d SMA(200) (R-DY).

The cross is the project's own: ``crossed_above`` fires when the fast average was at or below the slow one
on the bar before and is strictly above it now, exactly once per transition. Both averages are read at the
current bar and the one before, so the window is ``200 + 1`` rows and no signal is taken until all of them
are consecutive bars (R-DZ). The death cross is not a signal: the exit is the D1 trailing stop.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar, Final

from trading_bot.indicators import sma
from trading_bot.strategies.helpers import close_series, crossed_above, last_two
from trading_bot.strategies.m5n.base import Evaluation, M5nStrategy
from trading_bot.strategies.registry import register_strategy

if TYPE_CHECKING:  # pragma: no cover - typing only
    import pandas as pd

__all__ = ["SmaCross1d50200"]

FAST: Final = 50
SLOW: Final = 200


@register_strategy("sma_cross_1d_50_200")
class SmaCross1d50200(M5nStrategy):
    timeframe: ClassVar[str] = "1d"

    @property
    def window_bars(self) -> int:
        return SLOW + 1

    def evaluate(self, window: pd.DataFrame) -> Evaluation | None:
        close = close_series(window)
        fast = last_two(sma(close, FAST))
        slow = last_two(sma(close, SLOW))
        if fast is None or slow is None:
            return None
        if not crossed_above(fast, slow):
            return Evaluation(fired=False)
        return Evaluation(
            fired=True,
            reason=f"golden cross: SMA({FAST})={fast[1]:.8g} crossed above SMA({SLOW})={slow[1]:.8g}",
            metadata={
                "fast_period": FAST,
                "slow_period": SLOW,
                "fast_sma": fast[1],
                "slow_sma": slow[1],
                "prev_fast_sma": fast[0],
                "prev_slow_sma": slow[0],
            },
        )
