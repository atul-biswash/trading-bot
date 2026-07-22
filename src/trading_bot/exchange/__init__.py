"""Exchange adapters: concrete implementations of the exchange ports.

Importing this package pulls in ``python-binance``/``aiohttp`` (the Binance
adapter's dependencies); the pure domain layer under ``trading_bot.core`` does
not.
"""

from trading_bot.exchange.base import BaseExchangeClient
from trading_bot.exchange.binance_client import BinanceClient
from trading_bot.exchange.websocket_client import BinanceMarketDataStream

__all__ = ["BaseExchangeClient", "BinanceClient", "BinanceMarketDataStream"]
