"""Base class for trading strategies.

A strategy is intentionally *pure*: it receives a window of candles and returns
an optional :class:`~trading_bot.core.models.Signal`. It never touches the
exchange, sizes positions, or manages risk — those are separate concerns
(Single Responsibility). This keeps strategies trivial to unit-test and to run
identically in backtest, paper, and live modes.
"""

from __future__ import annotations

from abc import abstractmethod
from typing import TYPE_CHECKING, Any

from trading_bot.core.interfaces import Strategy
from trading_bot.core.models import Candle, Signal

if TYPE_CHECKING:  # pragma: no cover - typing only
    import pandas as pd


class BaseStrategy(Strategy):
    """Common scaffolding for concrete strategies.

    Subclasses set a class-level ``name`` and implement :meth:`generate_signal`.
    Constructor ``params`` come straight from ``strategy.params`` in config.yaml.
    """

    name: str = "base"

    def __init__(self, **params: Any) -> None:
        self.params = params

    @property
    def warmup_period(self) -> int:
        """Default warmup; override when indicators need a longer lookback."""
        return 1

    @abstractmethod
    def generate_signal(
        self, symbol: str, candles: pd.DataFrame, *, last_candle: Candle
    ) -> Signal | None:
        """See :meth:`trading_bot.core.interfaces.Strategy.generate_signal`.

        ``last_candle`` carries the final bar at full ``Decimal`` precision and
        is the only place a subclass may take ``Signal.price`` from; the
        ``float64`` frame is for indicator maths only.
        """

    def __repr__(self) -> str:  # pragma: no cover - cosmetic
        return f"{type(self).__name__}(name={self.name!r}, params={self.params})"
