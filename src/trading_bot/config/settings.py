"""Application settings: secrets from ``.env`` + behaviour from ``config.yaml``.

Two separate concerns are combined here:

* :class:`Secrets` — API keys and tokens, loaded from environment / ``.env``.
* :class:`AppConfig` — non-secret behaviour, parsed from ``config.yaml``.

:func:`get_settings` merges them into a single cached :class:`Settings` facade
and resolves *which* Binance credentials to use based on the active mode
(testnet vs. live), so the rest of the app never has to think about it.
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

import yaml
from pydantic import ValidationError
from pydantic_settings import BaseSettings, SettingsConfigDict

from trading_bot.config.models import AppConfig
from trading_bot.core.enums import TradingMode
from trading_bot.core.exceptions import ConfigError

DEFAULT_CONFIG_PATH = "config.yaml"


class Secrets(BaseSettings):
    """Secret values read from environment variables / ``.env``.

    Field names map to upper-case env vars (e.g. ``binance_api_key`` reads
    ``BINANCE_API_KEY``). Nothing here is ever written to logs.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    binance_api_key: str = ""
    binance_api_secret: str = ""
    binance_testnet_api_key: str = ""
    binance_testnet_api_secret: str = ""

    telegram_bot_token: str = ""
    telegram_chat_id: str = ""

    # Optional overrides.
    bot_mode: TradingMode | None = None


class Settings:
    """Facade exposing resolved config + secrets to the rest of the app."""

    def __init__(self, config: AppConfig, secrets: Secrets) -> None:
        self.config = config
        self._secrets = secrets
        # An explicit BOT_MODE in the environment wins over config.yaml.
        self.mode: TradingMode = secrets.bot_mode or config.mode

    @property
    def is_live(self) -> bool:
        return self.mode is TradingMode.LIVE

    def binance_credentials(self) -> tuple[str, str]:
        """Return the ``(api_key, api_secret)`` appropriate for the active mode.

        In testnet mode, testnet-specific keys are preferred and fall back to
        the primary keys. Raises :class:`ConfigError` if required keys are
        missing for a mode that needs a live connection.
        """
        if self.mode is TradingMode.TESTNET:
            key = self._secrets.binance_testnet_api_key or self._secrets.binance_api_key
            secret = (
                self._secrets.binance_testnet_api_secret
                or self._secrets.binance_api_secret
            )
        else:
            key = self._secrets.binance_api_key
            secret = self._secrets.binance_api_secret

        if self.mode.is_live_connection and (not key or not secret):
            raise ConfigError(
                f"Missing Binance API credentials for mode '{self.mode.value}'. "
                "Set them in your .env file (see .env.example)."
            )
        return key, secret

    @property
    def telegram(self) -> tuple[str, str]:
        return self._secrets.telegram_bot_token, self._secrets.telegram_chat_id


def _load_yaml_config(path: str | Path) -> AppConfig:
    config_path = Path(path)
    if not config_path.is_file():
        raise ConfigError(f"Config file not found: {config_path}")
    try:
        raw = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as exc:  # pragma: no cover - defensive
        raise ConfigError(f"Could not parse {config_path}: {exc}") from exc
    try:
        return AppConfig.model_validate(raw)
    except ValidationError as exc:
        raise ConfigError(f"Invalid configuration in {config_path}:\n{exc}") from exc


@lru_cache(maxsize=1)
def get_settings(config_path: str | None = None) -> Settings:
    """Load and cache application settings.

    The path is taken from the ``config_path`` argument, then the
    ``BOT_CONFIG_PATH`` env var, then :data:`DEFAULT_CONFIG_PATH`.
    """
    path = config_path or os.getenv("BOT_CONFIG_PATH", DEFAULT_CONFIG_PATH)
    config = _load_yaml_config(path)
    secrets = Secrets()
    return Settings(config=config, secrets=secrets)
