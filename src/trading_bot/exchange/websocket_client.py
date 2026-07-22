"""Binance market-data WebSocket stream.

Implements :class:`trading_bot.core.interfaces.MarketDataStream`: subscribes to
kline streams, emits closed :class:`~trading_bot.core.models.Candle` objects to
registered handlers, and auto-reconnects with backoff.

STUB — implemented in the streaming phase.
"""
