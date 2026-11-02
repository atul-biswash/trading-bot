"""C5 ``keltner_4h_20_2``: the 4h close rises above EMA(20) + 2 x ATR(20) (R-DY).

The ATR is Wilder's. Both indicators are recursive, so a missing decision bar re-seeds them (R-DZ): the
window is the gap-free run that ends at the decision bar, and the band has no value until that run holds
the ATR's warm-up (21 bars) and the previous bar's value that the edge needs (22). The entry is the edge:
the close is strictly above the band now and was at or below it on the bar before.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar, Final

from trading_bot.indicators import keltner_upper
from trading_bot.strategies.helpers import close_series, last_two
from trading_bot.strategies.m5n.base import Evaluation, M5nStrategy
from trading_bot.strategies.registry import register_strategy

if TYPE_CHECKING:  # pragma: no cover - typing only
    import pandas as pd

__all__ = ["Keltner4h202"]

EMA_PERIOD: Final = 20
ATR_PERIOD: Final = 20
MULTIPLIER: Final = 2.0


@register_strategy("keltner_4h_20_2")
class Keltner4h202(M5nStrategy):
    timeframe: ClassVar[str] = "4h"
    recursive: ClassVar[bool] = True

    @property
    def window_bars(self) -> int:
        return ATR_PERIOD + 2

    def evaluate(self, window: pd.DataFrame) -> Evaluation | None:
        close = close_series(window)
        band = keltner_upper(
            self.column(window, "high"),
            self.column(window, "low"),
            close,
            EMA_PERIOD,
            ATR_PERIOD,
            MULTIPLIER,
        )
        upper = last_two(band)
        closes = last_two(close)
        if upper is None or closes is None:
            return None
        if not (closes[1] > upper[1] and not closes[0] > upper[0]):
            return Evaluation(fired=False)
        return Evaluation(
            fired=True,
            reason=(
                f"channel breakout: 4h close {closes[1]:.8g} above EMA({EMA_PERIOD}) + "
                f"{MULTIPLIER:g} x ATR({ATR_PERIOD}) = {upper[1]:.8g}"
            ),
            metadata={
                "ema_period": EMA_PERIOD,
                "atr_period": ATR_PERIOD,
                "multiplier": MULTIPLIER,
                "close": closes[1],
                "upper_band": upper[1],
                "prev_close": closes[0],
                "prev_upper_band": upper[0],
            },
        )
