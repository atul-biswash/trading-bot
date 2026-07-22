"""Risk manager.

Implements :class:`trading_bot.core.interfaces.RiskManager`: vets each signal
against configured limits (max open positions, max daily loss, per-symbol
cooldown, max position size) and delegates sizing to ``position_sizing``.

STUB — implemented in the risk phase.
"""
