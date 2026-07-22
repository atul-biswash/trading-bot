"""Telegram notifier.

Implements :class:`trading_bot.core.interfaces.Notifier` by calling the Telegram
Bot API (sendMessage) via httpx. Token and chat id come from .env; the set of
events to announce comes from ``notifications.telegram.notify_on`` in config.

STUB — implemented in the notifications phase.
"""
