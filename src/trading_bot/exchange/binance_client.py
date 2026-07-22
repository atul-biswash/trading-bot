"""Binance Spot REST client (wraps python-binance).

Implements :class:`trading_bot.core.interfaces.ExchangeClient`. Honors the
active mode: constructs a Testnet-backed client when mode == testnet, and maps
Binance responses into the domain models in ``core.models``.

STUB — implemented in the connectivity phase (requires your approval first).
"""
