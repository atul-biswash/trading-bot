"""C6 ``tsmom_1d_90``: the 1d close moves from at or below to above the close 90 bars earlier (R-DY).

Time-series momentum, long-only. The 90-bar momentum of the close is read at the current bar and the one
before: it was at or below zero and is now strictly above, which ``crossed_above`` against a flat zero
expresses. The window is ``90 + 2`` rows, all consecutive bars (R-DZ). A falling momentum is not a signal:
the exit is the D1 trailing stop.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar, Final

from trading_bot.indicators import momentum
from trading_bot.strategies.helpers import close_series, crossed_above, last_two
from trading_bot.strategies.m5n.base import Evaluation, M5nStrategy
from trading_bot.strategies.registry import register_strategy

if TYPE_CHECKING:  # pragma: no cover - typing only
    import pandas as pd

__all__ = ["Tsmom1d90"]

LOOKBACK: Final = 90


@register_strategy("tsmom_1d_90")
class Tsmom1d90(M5nStrategy):
    timeframe: ClassVar[str] = "1d"

    @property
    def window_bars(self) -> int:
        return LOOKBACK + 2

    def evaluate(self, window: pd.DataFrame) -> Evaluation | None:
        close = close_series(window)
        change = last_two(momentum(close, LOOKBACK))
        if change is None:
            return None
        if not crossed_above(change, (0.0, 0.0)):
            return Evaluation(fired=False)
        return Evaluation(
            fired=True,
            reason=f"momentum turned positive: close is {change[1]:.8g} above the close {LOOKBACK} bars earlier",
            metadata={"lookback": LOOKBACK, "momentum": change[1], "prev_momentum": change[0]},
        )
