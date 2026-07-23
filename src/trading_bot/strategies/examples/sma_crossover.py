"""Simple moving-average crossover strategy.

Golden cross (fast SMA crosses above slow SMA) -> ``BUY``.
Death cross (fast SMA crosses back below slow) -> ``CLOSE``.

Spot semantics
--------------
There is no short side on spot, so the exit is ``CLOSE`` and never ``SELL``.
``SignalAction.SELL`` means "open or add to a short" in this domain; emitting it
here would hand Phase 6 execution an instruction a spot account cannot honour.

Edge-triggered, not level-triggered
-----------------------------------
A cross is a *transition*, so the signal fires on the bar where the transition
happens and stays silent while the resulting condition persists. Level
triggering -- emitting ``BUY`` on every bar where fast > slow -- would place a
duplicate order every single bar once execution lands, and would make the
strategy's behaviour depend on how often it happens to be evaluated.

Stateless by design
-------------------
The transition is recomputed from the last two bars of the buffer on every
evaluation rather than remembered on ``self``. One instance per pair makes
in-memory state *safe*, but it would not make it *right*:

* after a process restart the buffer is re-seeded from REST history, so a
  recomputed answer is unchanged while remembered state is gone;
* the provider **replaces** ``buffer[-1]`` when a reconnect re-delivers a
  corrected bar, so state accumulated from the first delivery would be stale
  while recomputation simply sees the correction;
* backtest and live run the identical code path.

The cost is a rolling mean over a bounded buffer once per closed bar, which is
microseconds. Incremental updates would buy nothing and would introduce a
second, drift-prone code path for the same number.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from trading_bot.core.enums import SignalAction
from trading_bot.core.models import Signal
from trading_bot.indicators import sma
from trading_bot.strategies.base import BaseStrategy
from trading_bot.strategies.helpers import (
    close_series,
    crossed_above,
    crossed_below,
    last_two,
)
from trading_bot.strategies.registry import register_strategy

if TYPE_CHECKING:  # pragma: no cover - typing only
    import pandas as pd

    from trading_bot.core.models import Candle


@register_strategy("sma_crossover")
class SmaCrossoverStrategy(BaseStrategy):
    """Trend-following crossover of a fast and a slow simple moving average.

    ``strength`` is left at its default ``1.0``. There is no defensible
    confidence measure at a crossover -- the two averages are equal by
    definition at the moment they cross, so any number here would be invented.
    Shipping a fabricated confidence that Phase 5 might multiply a position size
    by is worse than shipping an honest constant.
    """

    def __init__(self, fast_period: int = 20, slow_period: int = 50) -> None:
        """Validate periods eagerly so a bad ``config.yaml`` fails at startup.

        Construction happens once per pair while the engine is being built, long
        before any money is at stake. Deferring these checks to the first
        evaluation would instead surface them as strategy exceptions, which the
        engine counts toward quarantine -- turning a one-line config typo into a
        pair that silently stops trading five bars later.
        """
        if fast_period < 1:
            raise ValueError(f"fast_period must be >= 1, got {fast_period}")
        if slow_period < 1:
            raise ValueError(f"slow_period must be >= 1, got {slow_period}")
        if fast_period >= slow_period:
            raise ValueError(
                "fast_period must be < slow_period, got "
                f"fast_period={fast_period}, slow_period={slow_period}"
            )
        super().__init__(fast_period=fast_period, slow_period=slow_period)
        self.fast_period = fast_period
        self.slow_period = slow_period

    @property
    def warmup_period(self) -> int:
        """``slow_period + 1`` candles, derived from the indicator NaN contract.

        ``sma(n)`` leaves exactly ``n - 1`` leading ``NaN``, so the first usable
        slow value sits at index ``slow_period - 1`` and the second at index
        ``slow_period``. Detecting a *transition* needs both, hence
        ``slow_period + 1`` bars. The fast SMA is ready strictly earlier and so
        never binds.
        """
        return self.slow_period + 1

    def generate_signal(
        self, symbol: str, candles: pd.DataFrame, *, last_candle: Candle
    ) -> Signal | None:
        """Emit ``BUY`` on a golden cross, ``CLOSE`` on a death cross, else ``None``.

        ``None`` means "no opinion" and is by far the common case -- a cross is
        rare. An explicit ``HOLD`` signal is deliberately never emitted: it would
        wake every registered signal handler on every bar of every pair, which
        later phases would persist one row per bar and notify on.

        ``last_candle`` is the same final bar as the frame's last row, but with
        ``Decimal`` precision intact, and is the only admissible source for the
        signal's price and timestamp.
        """
        close = close_series(candles)
        fast = last_two(sma(close, self.fast_period))
        slow = last_two(sma(close, self.slow_period))
        if fast is None or slow is None:
            return None  # warmup or NaN region: not enough data to have an opinion

        if crossed_above(fast, slow):
            action, label, direction = SignalAction.BUY, "golden cross", "above"
        elif crossed_below(fast, slow):
            action, label, direction = SignalAction.CLOSE, "death cross", "below"
        else:
            return None

        return Signal(
            symbol=symbol,
            action=action,
            timestamp=last_candle.close_time,
            price=last_candle.close,
            reason=(
                f"{label}: SMA({self.fast_period})={fast[1]:.8g} crossed {direction} "
                f"SMA({self.slow_period})={slow[1]:.8g}"
            ),
            metadata={
                "strategy": self.name,
                "fast_period": self.fast_period,
                "slow_period": self.slow_period,
                "fast_sma": fast[1],
                "slow_sma": slow[1],
                "prev_fast_sma": fast[0],
                "prev_slow_sma": slow[0],
            },
        )
