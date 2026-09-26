"""Application settings: secrets from ``.env`` + behaviour from ``config.yaml``.

Two separate concerns are combined here:

* :class:`Secrets` — API keys and tokens, loaded from environment / ``.env``.
* :class:`AppConfig` — non-secret behaviour, parsed from ``config.yaml``.

:func:`get_settings` merges them into a single cached :class:`Settings` facade.
Its credential read serves the Binance TESTNET slots and refuses every other
mode: live trading is blocked by architectural invariant (CLAUDE.md), enforced
by :func:`refuse_live_trading`.
"""

from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import yaml
from pydantic import ValidationError
from pydantic_settings import BaseSettings, SettingsConfigDict

from trading_bot.config.models import AppConfig
from trading_bot.core.enums import TradingMode
from trading_bot.core.exceptions import ConfigError, LiveTradingBlockedError

DEFAULT_CONFIG_PATH = "config.yaml"

#: The ruled refusal, verbatim. Three lines joined by ``\n`` and no trailing
#: newline, because ``SystemExit`` prints its argument and adds its own.
LIVE_TRADING_BLOCKED_MESSAGE = (
    "FATAL: Live trading is blocked by architectural invariant (CLAUDE.md).\n"
    "Base-denominated entry fee netting is unmodeled in position sizing and order list "
    "generation.\n"
    "Startup refused."
)


class Secrets(BaseSettings):
    """Secret values read from environment variables / ``.env``.

    Field names map to upper-case env vars (e.g. ``binance_testnet_api_key``
    reads ``BINANCE_TESTNET_API_KEY``). Nothing here is ever written to logs.

    **The two live slots are declared and read nowhere.** They stay so an
    ``.env`` carrying them still loads; :meth:`Settings.binance_credentials`
    serves the testnet slots only.
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


def refuse_live_trading(mode: TradingMode) -> None:
    """Raise :class:`LiveTradingBlockedError` if ``mode`` trades real money.

    **The one predicate every entry point and the credential read share.**
    ``uses_real_money`` is true for ``TradingMode.LIVE`` alone -- unlike
    ``is_live_connection``, which is also true for TESTNET -- so this refuses
    real money and admits testnet, paper and backtest.

    **It takes the mode and nothing else, deliberately.** No ``allow=``
    parameter, no environment variable, no config flag: CLAUDE.md's block is
    lifted by a reviewed code change, never by a switch.
    ``tests/unit/test_live_guard.py`` pins the signature.
    """
    if mode.uses_real_money:
        raise LiveTradingBlockedError(LIVE_TRADING_BLOCKED_MESSAGE)


class Settings:
    """Facade exposing resolved config + secrets to the rest of the app.

    ``config_path`` and ``config_sha256`` say WHICH file was loaded and WHICH
    bytes of it: the resolved path, and the SHA-256 of the single read that was
    decoded and parsed. Both are ``None`` when a caller built the facade from an
    already-parsed :class:`AppConfig`, and a reader must treat ``None`` as
    unknown -- the startup provenance check refuses on it.
    """

    def __init__(
        self,
        config: AppConfig,
        secrets: Secrets,
        *,
        config_path: Path | None = None,
        config_sha256: str | None = None,
    ) -> None:
        self.config = config
        self._secrets = secrets
        self.config_path = config_path
        self.config_sha256 = config_sha256
        # An explicit BOT_MODE in the environment wins over config.yaml.
        self.mode: TradingMode = secrets.bot_mode or config.mode

    @property
    def is_live(self) -> bool:
        return self.mode is TradingMode.LIVE

    def binance_credentials(self) -> tuple[str, str]:
        """Return the TESTNET ``(api_key, api_secret)``, or refuse.

        **THREE REFUSALS, IN THIS ORDER, AND ALL OF THEM PRECEDE ANY READ OF A
        KEY SLOT.** Ruled by the project owner at M5k.

        1. ``LIVE`` raises :class:`LiveTradingBlockedError` through
           :func:`refuse_live_trading`, so the live key never leaves
           :class:`Secrets`. Every client built from ``Settings`` takes its
           keys here, which makes this the backstop behind the entry-point
           checks.
        2. ``PAPER`` and ``BACKTEST`` raise :class:`ConfigError`: they use no
           exchange credentials. Until this they were handed the live slots,
           and both client constructors build ``testnet=False`` for any mode
           but TESTNET -- so either reaching a constructor would have bound the
           live venue.
        3. ``TESTNET`` reads the testnet slots ONLY. There is no fallback to
           the live slots: an empty testnet slot is a refusal, never a live
           key sent to the testnet host.

        :raises LiveTradingBlockedError: the mode trades real money.
        :raises ConfigError: PAPER or BACKTEST, or a testnet slot is empty.
        """
        refuse_live_trading(self.mode)
        if self.mode in (TradingMode.PAPER, TradingMode.BACKTEST):
            raise ConfigError("PAPER and BACKTEST modes do not use exchange credentials")
        key = self._secrets.binance_testnet_api_key
        secret = self._secrets.binance_testnet_api_secret
        if not key or not secret:
            raise ConfigError("Missing Binance Testnet credentials")
        return key, secret

    @property
    def telegram(self) -> tuple[str, str]:
        return self._secrets.telegram_bot_token, self._secrets.telegram_chat_id


@dataclass(frozen=True)
class _LoadedConfig:
    """A parsed config together with the identity of the bytes it came from."""

    config: AppConfig
    path: Path
    sha256: str


def _read_config(path: str | Path) -> _LoadedConfig:
    """Read the file ONCE, then hash, decode and parse those same bytes.

    **One read, not two.** Hashing a second read would describe whatever the
    file held a moment later, which is not necessarily what was parsed -- a
    digest that can disagree with the configuration it claims to identify.

    Decoding bytes rather than calling ``read_text`` drops universal-newline
    translation, which YAML does not need: it treats CRLF and LF as the same
    line break, and ``tests/unit/test_settings.py`` pins that.
    """
    config_path = Path(path)
    if not config_path.is_file():
        raise ConfigError(f"Config file not found: {config_path}")
    data = config_path.read_bytes()
    try:
        raw = yaml.safe_load(data.decode("utf-8")) or {}
    except yaml.YAMLError as exc:  # pragma: no cover - defensive
        raise ConfigError(f"Could not parse {config_path}: {exc}") from exc
    try:
        config = AppConfig.model_validate(raw)
    except ValidationError as exc:
        raise ConfigError(f"Invalid configuration in {config_path}:\n{exc}") from exc
    return _LoadedConfig(
        config=config,
        path=config_path.resolve(),
        sha256=hashlib.sha256(data).hexdigest(),
    )


def _load_yaml_config(path: str | Path) -> AppConfig:
    return _read_config(path).config


@lru_cache(maxsize=1)
def get_settings(config_path: str | None = None) -> Settings:
    """Load and cache application settings.

    The path is taken from the ``config_path`` argument, then the
    ``BOT_CONFIG_PATH`` env var, then :data:`DEFAULT_CONFIG_PATH`. The facade
    carries the resolved path and the digest of the bytes parsed.
    """
    path: str | Path = config_path or os.getenv("BOT_CONFIG_PATH") or DEFAULT_CONFIG_PATH
    loaded = _read_config(path)
    secrets = Secrets()
    return Settings(
        config=loaded.config,
        secrets=secrets,
        config_path=loaded.path,
        config_sha256=loaded.sha256,
    )
