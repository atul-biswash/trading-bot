"""Order executor.

Implements :class:`trading_bot.core.interfaces.OrderExecutor`. Translates an
approved, risk-sized signal into an OrderRequest, rounds quantity/price to the
symbol filters, and submits it via the exchange client (or the paper simulator).

STUB — implemented in the execution phase.
"""
