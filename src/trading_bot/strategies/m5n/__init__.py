"""The six M5n candidates (R-DY): importing this package registers them.

``donchian_1d_20``, ``donchian_1d_55``, ``sma_cross_1d_50_200``, ``donchian_4h_20``, ``keltner_4h_20_2``
and ``tsmom_1d_90``. They are research strategies on the archive decision series and are **not** imported
by ``create_strategy`` or ``available_strategies``, so the live engine's registry does not list them; a
caller that wants one imports this package first.
"""

from __future__ import annotations

from trading_bot.strategies.m5n import donchian, keltner, sma_cross, tsmom

__all__ = ["donchian", "keltner", "sma_cross", "tsmom"]
