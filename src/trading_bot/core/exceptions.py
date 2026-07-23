"""Custom exception hierarchy.

A single base (:class:`TradingBotError`) lets callers catch everything the bot
raises while still allowing narrow ``except`` clauses for specific failures.
"""

from __future__ import annotations


class TradingBotError(Exception):
    """Base class for every error raised by the bot."""


# --- Configuration ----------------------------------------------------------
class ConfigError(TradingBotError):
    """Invalid, missing, or contradictory configuration."""


# --- Exchange ---------------------------------------------------------------
class ExchangeError(TradingBotError):
    """Base class for exchange-related failures."""


class ExchangeConnectionError(ExchangeError):
    """Network/transport failure talking to the exchange."""


class ExchangeAPIError(ExchangeError):
    """The exchange returned an error response.

    :param message: human-readable description.
    :param code: exchange-specific error code, if provided.
    """

    def __init__(self, message: str, *, code: int | None = None) -> None:
        super().__init__(message)
        self.code = code


class RateLimitError(ExchangeError):
    """A rate limit or IP ban was hit; back off before retrying."""


class InsufficientBalanceError(ExchangeError):
    """Not enough free balance to place the requested order."""


class OrderError(ExchangeError):
    """An order was rejected or could not be created/canceled."""


# --- Data -------------------------------------------------------------------
class DataError(TradingBotError):
    """Missing, malformed, or insufficient market data."""


# --- Strategy ---------------------------------------------------------------
class StrategyError(TradingBotError):
    """A strategy failed to load or produced an invalid signal."""


class StrategyNotFoundError(StrategyError):
    """No strategy is registered under the requested name."""


class StrategyConfigError(StrategyError):
    """A strategy's configured parameters do not match its constructor.

    Raised for wrong parameter *names* (a typo in ``config.yaml``). Wrong
    *values* under correct names raise ``ValueError`` from the strategy itself,
    where the message can be specific about the constraint that failed.
    """


# --- Risk -------------------------------------------------------------------
class RiskError(TradingBotError):
    """Base class for risk-management rejections."""


class RiskLimitExceeded(RiskError):
    """A configured risk limit blocked an action."""


# --- Notifications ----------------------------------------------------------
class NotificationError(TradingBotError):
    """A notification channel failed to deliver a message."""
