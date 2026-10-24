"""The scaffolding the six M5n candidates share: the gap rule, the edge, the signal.

R-DX, R-DY and R-DZ (``docs/M5N_CHARTER_DRAFT.md`` section 15) fix what a candidate is:

* **Long-only spot, entry only.** A candidate emits ``BUY`` and never ``CLOSE`` or ``SELL``; the exit
  is the D1 trailing stop, not a signal.
* **Decision-bar input only.** It reads the frame it is given and nothing else, and **it reads open,
  high, low and close and never the volume** (R-DX): a ``volume`` column that is present is ignored.
* **Edge-triggered.** A condition that has held for several bars signals on the first.
* **R-DZ.** A window that contains a missing bar gives no value, so no signal, until the window is
  gap-free. ``enforce_gaps=False`` reads the same rows as though they were consecutive. It exists so
  that the effect of R-DZ can be counted (``scripts/n3_entry_counts.py``); nothing live uses it.

``Signal.price`` and ``Signal.timestamp`` come from ``last_candle``, as for every strategy.
"""

from __future__ import annotations

from abc import abstractmethod
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, ClassVar

from trading_bot.core.enums import SignalAction
from trading_bot.core.exceptions import DataError
from trading_bot.core.models import Candle, Signal
from trading_bot.strategies.base import BaseStrategy
from trading_bot.strategies.m5n.gaps import gap_free_run, gap_free_tail

if TYPE_CHECKING:  # pragma: no cover - typing only
    import pandas as pd

__all__ = ["Evaluation", "M5nStrategy"]


@dataclass(frozen=True)
class Evaluation:
    """What a candidate found on the last bar of a window: whether it fired, and why."""

    fired: bool
    reason: str = ""
    metadata: dict[str, str | int | float] = field(default_factory=dict)


class M5nStrategy(BaseStrategy):
    """A long-only candidate on one decision timeframe; subclasses define the condition.

    A subclass sets ``timeframe`` (``"4h"`` or ``"1d"``), says how many rows its window reads
    (``window_bars``) and whether its indicators are recursive (``recursive``), and implements
    :meth:`evaluate`, which sees only a window that R-DZ has already cleared.
    """

    timeframe: ClassVar[str]
    recursive: ClassVar[bool] = False

    def __init__(self, enforce_gaps: bool = True) -> None:
        if not isinstance(enforce_gaps, bool):
            raise ValueError(f"enforce_gaps must be a bool, got {enforce_gaps!r}")
        super().__init__(enforce_gaps=enforce_gaps)
        self.enforce_gaps = enforce_gaps

    @property
    @abstractmethod
    def window_bars(self) -> int:
        """The rows the window reads: the lookback, the current bar and the one before it."""

    @property
    def warmup_period(self) -> int:
        return self.window_bars

    @abstractmethod
    def evaluate(self, window: pd.DataFrame) -> Evaluation | None:
        """The condition on the last row of ``window``, or ``None`` if it has no value there."""

    @staticmethod
    def column(window: pd.DataFrame, name: str) -> pd.Series:
        """One OHLC column of ``window``; a missing one is a ``DataError`` and not a bare ``KeyError``."""
        if name not in window.columns:
            raise DataError(
                f"decision frame has no {name!r} column; got {sorted(str(c) for c in window.columns)}"
            )
        return window[name]

    def _window(self, candles: pd.DataFrame) -> pd.DataFrame | None:
        if self.recursive:
            return gap_free_run(candles, self.timeframe) if self.enforce_gaps else candles
        if self.enforce_gaps:
            return gap_free_tail(candles, self.timeframe, self.window_bars)
        return candles.iloc[-self.window_bars :] if len(candles) >= self.window_bars else None

    def generate_signal(
        self, symbol: str, candles: pd.DataFrame, *, last_candle: Candle
    ) -> Signal | None:
        if last_candle.timeframe != self.timeframe:
            raise DataError(
                f"{self.name} decides on {self.timeframe} bars, got {last_candle.timeframe!r}"
            )
        window = self._window(candles)
        if window is None:
            return None
        found = self.evaluate(window)
        if found is None or not found.fired:
            return None
        return Signal(
            symbol=symbol,
            action=SignalAction.BUY,
            timestamp=last_candle.close_time,
            price=last_candle.close,
            reason=found.reason,
            metadata={"strategy": self.name, "timeframe": self.timeframe, **found.metadata},
        )
