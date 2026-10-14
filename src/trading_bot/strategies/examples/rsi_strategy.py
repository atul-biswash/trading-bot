"""RSI mean-reversion strategy.

RSI crossing **down** through ``oversold``   -> ``BUY``.
RSI crossing **up** through ``overbought``   -> ``CLOSE``.

Spot semantics
--------------
Overbought maps to ``CLOSE`` (exit the long), never ``SELL`` (open a short),
which a spot account cannot do. See ``SignalAction`` for the distinction.

Crossing, not level
-------------------
The trigger is the *transition* through a threshold, not the state of being past
it. "RSI is below 30" is true for every bar of an oversold stretch and would
emit a fresh ``BUY`` on each one; "RSI just crossed below 30" is true once. This
choice is what sets :attr:`warmup_period` to ``period + 2`` rather than
``period + 1`` -- a crossing needs two RSI values, a level needs one.

Flat markets
------------
A perfectly flat series gives RSI exactly ``50.0`` on every bar (the indicator
layer's deliberate convention), which sits between the thresholds and crosses
neither. A dead market therefore produces silence, which is the correct answer
and the reason that convention was chosen over ``NaN`` or ``100``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from trading_bot.core.enums import SignalAction
from trading_bot.core.models import Signal
from trading_bot.indicators import rsi
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


@register_strategy("rsi")
class RsiStrategy(BaseStrategy):
    """Buy exhaustion below ``oversold``, exit exuberance above ``overbought``.

    ``strength`` is left at its default ``1.0`` even though a natural confidence
    measure exists (how far past the threshold RSI travelled). On the *crossing*
    bar that distance is by construction near zero, so publishing it as
    ``strength`` would invite Phase 5 to size every genuine entry to nothing.
    The number is still computed and exposed as
    ``metadata["threshold_distance"]``, where it is unambiguously diagnostic;
    whether confidence should scale position size stays an explicit Phase 5
    decision rather than an accident inherited from here.
    """

    def __init__(
        self,
        period: int = 14,
        oversold: float = 30.0,
        overbought: float = 70.0,
        trend_filter_period: int | None = None,
    ) -> None:
        """Validate parameters eagerly so a bad ``config.yaml`` fails at startup.

        ``trend_filter_period`` (R-BS, M5m P113) makes an oversold crossing a ``BUY`` only while
        the bar's close is strictly above its SMA of that period (200 in the research protocol);
        ``None``, the default, is the strategy as it always was. The filter gates the entry
        and nothing else: the overbought crossing is a ``CLOSE`` whatever the trend says, so a
        filter can never keep a position open. Buying weakness only inside an uptrend is what
        the filter is for, and the crossing is not taken later if the trend turns up after it.

        Thresholds must lie **strictly** inside ``0..100``, not merely within it.
        RSI saturates at exactly ``0.0`` and ``100.0``, so ``oversold=0`` asks
        for a crossing below zero that can never occur: the strategy would load,
        run forever, and never trade. Rejecting the config is a far better
        failure than a bot that is silently inert.
        """
        if period < 1:
            raise ValueError(f"period must be >= 1, got {period}")
        if not 0.0 < oversold < 100.0:
            raise ValueError(f"oversold must be strictly between 0 and 100, got {oversold}")
        if not 0.0 < overbought < 100.0:
            raise ValueError(f"overbought must be strictly between 0 and 100, got {overbought}")
        if oversold >= overbought:
            raise ValueError(
                f"oversold must be < overbought, got oversold={oversold}, overbought={overbought}"
            )
        self.trend_filter_period = validate_trend_filter_period(trend_filter_period)
        if self.trend_filter_period is None:
            super().__init__(period=period, oversold=oversold, overbought=overbought)
        else:
            super().__init__(
                period=period,
                oversold=oversold,
                overbought=overbought,
                trend_filter_period=self.trend_filter_period,
            )
        self.period = period
        self.oversold = oversold
        self.overbought = overbought

    @property
    def warmup_period(self) -> int:
        """``period + 2`` candles, derived from the indicator NaN contract.

        ``rsi(n)`` leaves exactly ``n`` leading ``NaN`` -- one more than
        ``sma(n)``, because the first bar has no previous close to difference
        against. The first usable value is therefore at index ``period`` and the
        second at ``period + 1``, so detecting a *crossing* needs ``period + 2``
        bars.

        This is deliberately one more than a level test would need. ``period +
        1`` is exactly enough to ask "is RSI below 30 right now?", and reading
        that number as the warmup would silently produce a strategy that fires
        on the wrong condition.

        **With a trend filter the warmup is the larger of that and ``trend_filter_period``**:
        ``sma(n)`` needs ``n`` bars for its first value, and one value is all the filter reads.
        """
        needed = self.period + 2
        if self.trend_filter_period is None:
            return needed
        return max(needed, self.trend_filter_period)

    def generate_signal(
        self, symbol: str, candles: pd.DataFrame, *, last_candle: Candle
    ) -> Signal | None:
        """Emit ``BUY`` or ``CLOSE`` on a threshold crossing, else ``None``.

        ``None`` means "no opinion"; there is no "do nothing" action to emit
        instead, for the same reason as in the crossover strategy.
        """
        close = close_series(candles)
        values = last_two(rsi(close, self.period))
        if values is None:
            return None  # warmup or NaN region: not enough data to have an opinion

        current = values[1]
        if crossed_below(values, (self.oversold, self.oversold)):
            action, label, threshold = SignalAction.BUY, "oversold", self.oversold
            direction = "below"
            # Both denominators are non-zero: thresholds are strictly inside 0..100.
            distance = (self.oversold - current) / self.oversold
        elif crossed_above(values, (self.overbought, self.overbought)):
            action, label, threshold = SignalAction.CLOSE, "overbought", self.overbought
            direction = "above"
            distance = (current - self.overbought) / (100.0 - self.overbought)
        else:
            return None

        metadata: dict[str, str | int | float] = {
            "strategy": self.name,
            "period": self.period,
            "rsi": current,
            "prev_rsi": values[0],
            "threshold": threshold,
            "threshold_kind": label,
            # 0..1: RSI travelled this fraction of the way from the threshold
            # to saturation. Diagnostic only -- see the class docstring.
            "threshold_distance": distance,
        }
        reason = (
            f"{label}: RSI({self.period})={current:.2f} crossed {direction} "
            f"{threshold:.2f} (from {values[0]:.2f})"
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
