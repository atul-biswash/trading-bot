"""C1, C2 and C4: a close above the highest high of the prior ``period`` decision bars (R-DY).

One implementation and three registered names, because the rule is the same and only the lookback and
the timeframe differ:

* ``donchian_1d_20`` (C1): 1d, 20 bars.
* ``donchian_1d_55`` (C2): 1d, 55 bars.
* ``donchian_4h_20`` (C4): 4h, 20 bars.

The condition is *close strictly above* the highest high of the bars before it; a close equal to that
high is not a breakout. The entry is the edge, the bar on which the condition is true and was false on
the bar before, so a run of new highs signals once. That needs the prior ``period`` highs of the current
bar and of the bar before it, a window of ``period + 2`` rows (R-DZ).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar

from trading_bot.indicators import donchian_high
from trading_bot.strategies.helpers import close_series, last_two
from trading_bot.strategies.m5n.base import Evaluation, M5nStrategy
from trading_bot.strategies.registry import register_strategy

if TYPE_CHECKING:  # pragma: no cover - typing only
    import pandas as pd

__all__ = ["Donchian1d20", "Donchian1d55", "Donchian4h20"]


class _Donchian(M5nStrategy):
    period: ClassVar[int]

    @property
    def window_bars(self) -> int:
        return self.period + 2

    def evaluate(self, window: pd.DataFrame) -> Evaluation | None:
        closes = last_two(close_series(window))
        highs = last_two(donchian_high(self.column(window, "high"), self.period))
        if closes is None or highs is None:
            return None
        if not (closes[1] > highs[1] and not closes[0] > highs[0]):
            return Evaluation(fired=False)
        return Evaluation(
            fired=True,
            reason=(
                f"breakout: {self.timeframe} close {closes[1]:.8g} above the highest high "
                f"{highs[1]:.8g} of the prior {self.period} bars"
            ),
            metadata={
                "period": self.period,
                "close": closes[1],
                "donchian_high": highs[1],
                "prev_close": closes[0],
                "prev_donchian_high": highs[0],
            },
        )


@register_strategy("donchian_1d_20")
class Donchian1d20(_Donchian):
    timeframe = "1d"
    period = 20


@register_strategy("donchian_1d_55")
class Donchian1d55(_Donchian):
    timeframe = "1d"
    period = 55


@register_strategy("donchian_4h_20")
class Donchian4h20(_Donchian):
    timeframe = "4h"
    period = 20
