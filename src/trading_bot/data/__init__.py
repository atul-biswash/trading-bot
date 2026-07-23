"""Data layer: market-data provision, historical loading, persistence gateways.

Importing this package pulls in the pandas/NumPy stack; the pure domain layer
under ``trading_bot.core`` does not.
"""

from trading_bot.data.market_data import BufferedMarketDataProvider

__all__ = ["BufferedMarketDataProvider"]
