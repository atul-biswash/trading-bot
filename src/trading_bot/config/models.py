"""Typed representation of ``config.yaml``.

Parsing YAML into these pydantic models means a malformed or nonsensical config
fails fast at startup with a clear error, instead of surfacing as an
``AttributeError`` deep inside the trading loop.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from trading_bot.core.enums import (
    PositionSizingMethod,
    StopType,
    TakeProfitType,
    TradingMode,
)


class _Model(BaseModel):
    # Reject unknown keys so typos in config.yaml are caught immediately.
    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class ExchangeConfig(_Model):
    name: str = "binance"
    recv_window_ms: int = 5000
    requests_timeout_s: int = 10
    rate_limit_safety: float = Field(0.9, gt=0, le=1)


class PairConfig(_Model):
    symbol: str
    timeframe: str
    enabled: bool = True

    @field_validator("symbol")
    @classmethod
    def _upper(cls, v: str) -> str:
        return v.upper()


class TradingConfig(_Model):
    base_currency: str = "USDT"
    default_timeframe: str = "1m"
    pairs: list[PairConfig] = Field(default_factory=list)

    @property
    def enabled_pairs(self) -> list[PairConfig]:
        return [p for p in self.pairs if p.enabled]


class StrategyConfig(_Model):
    name: str
    params: dict[str, object] = Field(default_factory=dict)


class PositionSizingConfig(_Model):
    method: PositionSizingMethod = PositionSizingMethod.FIXED_FRACTION
    fraction: float = Field(0.02, gt=0, le=1)
    fixed_amount: float = Field(100.0, gt=0)
    risk_per_trade: float = Field(0.01, gt=0, le=1)


class StopLossConfig(_Model):
    enabled: bool = True
    type: StopType = StopType.PERCENT
    percent: float = Field(2.0, gt=0)
    atr_period: int = Field(14, gt=0)
    atr_multiplier: float = Field(2.0, gt=0)


class TakeProfitConfig(_Model):
    enabled: bool = True
    type: TakeProfitType = TakeProfitType.PERCENT
    percent: float = Field(4.0, gt=0)
    rr_multiple: float = Field(2.0, gt=0)


class TrailingStopConfig(_Model):
    enabled: bool = False
    activation_percent: float = Field(1.0, gt=0)
    trail_percent: float = Field(1.0, gt=0)


class RiskLimitsConfig(_Model):
    max_open_positions: int = Field(3, ge=1)
    max_daily_loss_percent: float = Field(5.0, gt=0)
    max_position_size_percent: float = Field(20.0, gt=0, le=100)
    cooldown_minutes: int = Field(15, ge=0)


class RiskConfig(_Model):
    position_sizing: PositionSizingConfig = Field(default_factory=PositionSizingConfig)
    stop_loss: StopLossConfig = Field(default_factory=StopLossConfig)
    take_profit: TakeProfitConfig = Field(default_factory=TakeProfitConfig)
    trailing_stop: TrailingStopConfig = Field(default_factory=TrailingStopConfig)
    limits: RiskLimitsConfig = Field(default_factory=RiskLimitsConfig)


class BacktestConfig(_Model):
    start_date: str
    end_date: str
    initial_balance: float = Field(10_000.0, gt=0)
    fee_percent: float = Field(0.1, ge=0)
    slippage_percent: float = Field(0.05, ge=0)
    data_dir: str = "data/historical"


class PaperTradingConfig(_Model):
    initial_balance: float = Field(10_000.0, gt=0)
    fee_percent: float = Field(0.1, ge=0)
    slippage_percent: float = Field(0.05, ge=0)


class TelegramConfig(_Model):
    enabled: bool = False
    notify_on: list[str] = Field(default_factory=list)


class NotificationsConfig(_Model):
    telegram: TelegramConfig = Field(default_factory=TelegramConfig)


class LogFileConfig(_Model):
    enabled: bool = True
    path: str = "logs/trading_bot.log"
    max_bytes: int = Field(10_485_760, gt=0)
    backup_count: int = Field(5, ge=0)
    # YAML key stays "json"; the field is renamed to avoid shadowing
    # pydantic's BaseModel.json method.
    json_format: bool = Field(False, alias="json")


class LoggingConfig(_Model):
    level: str = "INFO"
    console: bool = True
    file: LogFileConfig = Field(default_factory=LogFileConfig)


class DatabaseConfig(_Model):
    url: str = "sqlite:///data/trading_bot.db"
    echo: bool = False


class EngineConfig(_Model):
    loop_interval_s: float = Field(1.0, gt=0)
    # WebSocket auto-reconnection (see exchange/websocket_client.py). 0 means
    # retry indefinitely — the default for 24/7 operation, since a feed that
    # stops silently is the worst failure mode for money software. A positive
    # value caps *consecutive* failed reconnects; the counter resets after any
    # message arrives on a healthy connection.
    reconnect_max_retries: int = Field(0, ge=0)
    reconnect_backoff_s: float = Field(5.0, gt=0)  # base (first) backoff, seconds
    reconnect_backoff_max_s: float = Field(60.0, gt=0)  # backoff ceiling, seconds

    @model_validator(mode="after")
    def _check_backoff_bounds(self) -> EngineConfig:
        if self.reconnect_backoff_max_s < self.reconnect_backoff_s:
            raise ValueError(
                "reconnect_backoff_max_s must be >= reconnect_backoff_s"
            )
        return self


class AppConfig(_Model):
    """Root config object — the fully parsed ``config.yaml``."""

    mode: TradingMode = TradingMode.TESTNET
    exchange: ExchangeConfig = Field(default_factory=ExchangeConfig)
    trading: TradingConfig = Field(default_factory=TradingConfig)
    strategy: StrategyConfig
    risk: RiskConfig = Field(default_factory=RiskConfig)
    backtesting: BacktestConfig
    paper_trading: PaperTradingConfig = Field(default_factory=PaperTradingConfig)
    notifications: NotificationsConfig = Field(default_factory=NotificationsConfig)
    logging: LoggingConfig = Field(default_factory=LoggingConfig)
    database: DatabaseConfig = Field(default_factory=DatabaseConfig)
    engine: EngineConfig = Field(default_factory=EngineConfig)
