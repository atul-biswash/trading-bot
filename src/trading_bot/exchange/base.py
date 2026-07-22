"""Abstract exchange adapter base.

Concrete clients implement :class:`trading_bot.core.interfaces.ExchangeClient`.
Keeping a base here lets shared behaviour (symbol-info caching, retry policy)
live in one place across future exchanges.

STUB — implemented in the connectivity phase.
"""
