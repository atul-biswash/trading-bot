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
# There is deliberately no risk exception. A risk outcome is a *value* in this
# system -- SizingDecision, ProtectiveLevels, RiskDecision, RiskAssessment --
# never a raise, because "too small to trade", "no placeable stop this bar" and
# "the daily-loss cap is hit" are routine answers that must carry their reason to
# an operator. `RiskError` / `RiskLimitExceeded` existed here from the scaffold
# until Phase 5 M3 and never acquired a caller; a class whose docstring read
# "risk-management rejections" named precisely the thing M1-M3 decided must not
# be an exception, so keeping it would have invited the pattern back.
#
# Genuinely incoherent *inputs* to the risk rules (non-positive price, non-finite
# ATR) still raise, as bare `ValueError` -- the same convention `indicators/`
# documents: ValueError for invalid parameters, DataError for malformed data.
# Re-add a risk exception only alongside a caller that catches it.


# --- Notifications ----------------------------------------------------------
class NotificationError(TradingBotError):
    """A notification channel failed to deliver a message."""
