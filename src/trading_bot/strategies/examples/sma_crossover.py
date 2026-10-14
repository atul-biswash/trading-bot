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
    trend_allows_entry,
    validate_trend_filter_period,
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

    def __init__(
        self,
        fast_period: int = 20,
        slow_period: int = 50,
        trend_filter_period: int | None = None,
    ) -> None:
        """Validate periods eagerly so a bad ``config.yaml`` fails at startup.

        ``trend_filter_period`` (R-BS, M5m P113) makes a golden cross a ``BUY`` only while the
        bar's close is strictly above its SMA of that period (200 in the research protocol);
        ``None``, the default, is the strategy as it always was. The filter gates the entry
        and nothing else: the death cross is a ``CLOSE`` whatever the trend says, because an
        exit that a filter could suppress would trap the position it is meant to release.
        Being stateless, a cross that happens below the trend is simply not taken, and is not
        taken later when the trend turns up.

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
        self.trend_filter_period = validate_trend_filter_period(trend_filter_period)
        if self.trend_filter_period is None:
            super().__init__(fast_period=fast_period, slow_period=slow_period)
        else:
            super().__init__(
                fast_period=fast_period,
                slow_period=slow_period,
                trend_filter_period=self.trend_filter_period,
            )
        self.fast_period = fast_period
        self.slow_period = slow_period

    @property
    def warmup_period(self) -> int:
        """``slow_period + 1`` candles, derived from the indicator NaN contract.

        ``sma(n)`` leaves exactly ``n - 1`` leading ``NaN``, so the first usable
        slow value sits at index ``slow_period - 1`` and the second at index
        ``slow_period``. Detecting a *transition* needs both, hence
        ``slow_period + 1`` bars. The fast SMA is ready strictly earlier and so
        never binds. **With a trend filter the warmup is the larger of that and
        ``trend_filter_period``**: ``sma(n)`` needs ``n`` bars for its first value, and
        one value is all the filter reads.
        """
        needed = self.slow_period + 1
        if self.trend_filter_period is None:
            return needed
        return max(needed, self.trend_filter_period)

    def generate_signal(
        self, symbol: str, candles: pd.DataFrame, *, last_candle: Candle
    ) -> Signal | None:
        """Emit ``BUY`` on a golden cross, ``CLOSE`` on a death cross, else ``None``.

        ``None`` means "no opinion" and is by far the common case -- a cross is
        rare. There is no "do nothing" signal to emit instead: one would wake
        every registered handler on every bar of every pair, which later phases
        would persist a row for and notify on.

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

        metadata: dict[str, str | int | float] = {
            "strategy": self.name,
            "fast_period": self.fast_period,
            "slow_period": self.slow_period,
            "fast_sma": fast[1],
            "slow_sma": slow[1],
            "prev_fast_sma": fast[0],
            "prev_slow_sma": slow[0],
        }
        reason = (
            f"{label}: SMA({self.fast_period})={fast[1]:.8g} crossed {direction} "
            f"SMA({self.slow_period})={slow[1]:.8g}"
        )
        if self.trend_filter_period is not None and action is SignalAction.BUY:
            allowed, trend = trend_allows_entry(close, self.trend_filter_period)
            if not allowed or trend is None:
                return None  # below its trend, or the trend is not measurable yet: no entry
            metadata["trend_filter_period"] = self.trend_filter_period
            metadata["trend_sma"] = trend
            reason += f"; close above SMA({self.trend_filter_period})={trend:.8g}"

        return Signal(
            symbol=symbol,
            action=action,
            timestamp=last_candle.close_time,
            price=last_candle.close,
            reason=reason,
            metadata=metadata,
        )
