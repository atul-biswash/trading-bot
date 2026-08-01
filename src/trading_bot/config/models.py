"""Typed representation of ``config.yaml``.

Parsing YAML into these pydantic models means a malformed or nonsensical config
fails fast at startup with a clear error, instead of surfacing as an
``AttributeError`` deep inside the trading loop.

The ``float`` -> ``Decimal`` boundary
------------------------------------
YAML has no decimal type: ``fraction: 0.02`` arrives as a binary ``float``. Any
config value that is later *multiplied by money* is therefore declared
``Decimal`` here, and pydantic performs the conversion at validation time using
the value's shortest repr -- ``0.02`` becomes ``Decimal("0.02")``, not
``Decimal("0.020000000000000000416...")`` as ``Decimal(0.02)`` would give.

Doing it here rather than at each use site means the domain never sees a float
it would have to convert, and there is no ``Decimal(str(x))`` scattered through
the risk layer. Note the deliberate asymmetry with ``core.models.Money``: this
is the one place a float is *allowed* to become a Decimal, precisely because it
is the system's edge; inside the domain the ``Money`` guard rejects floats
outright.

Fields are converted at the milestone that first does money arithmetic with
them, not speculatively -- converting a field before the code that consumes it
exists would mean guessing its semantics. Fields still typed ``float`` below are
ones no money arithmetic touches yet.

**Caveat for any future "dump the effective config" feature:** ``yaml.safe_dump``
cannot represent a ``Decimal`` (it raises ``RepresenterError``). Config is
load-only today, so nothing is affected; a dumper would need an explicit
representer or ``model_dump(mode="json")``.
"""

from __future__ import annotations

from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from trading_bot.core.enums import (
    PositionSizingMethod,
    StopType,
    TakeProfitType,
    TradingMode,
)


class _Model(BaseModel):
    # Reject unknown keys so typos in config.yaml are caught immediately.
    #
    # `validate_assignment` makes "config is loaded once and never mutated" an
    # enforced property rather than a convention. That convention is what
    # justifies leaving these models unguarded elsewhere -- notably the argument
    # for not worrying that a float assigned to a Decimal field would flow into
    # `move_pct < config.activation_percent` and decide a trailing stop without
    # raising, because `Decimal < float` is silent. Nothing in src/ or scripts/
    # assigns to a config model today (`settings.mode = ...` targets the plain
    # `Settings` facade, not these), so the guard costs nothing if the convention
    # holds -- and fails loudly the moment it stops holding.
    model_config = ConfigDict(extra="forbid", populate_by_name=True, validate_assignment=True)


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


class DataConfig(_Model):
    """Market-data history seeding and the in-memory rolling window.

    ``history_limit`` is how many closed candles are fetched per pair over REST
    at startup so strategies are warm immediately instead of waiting hours for a
    slow timeframe to fill. Binance caps a single ``klines`` call at 1000 bars,
    so that is the hard upper bound here (paginated deeper history belongs to
    the backtesting loader, not the live path).

    ``buffer_size`` bounds memory: each pair keeps at most this many candles and
    evicts the oldest, which is what makes 24/7 operation safe. It must be at
    least ``history_limit``, otherwise startup would immediately discard part of
    the history it just paid to fetch.
    """

    history_limit: int = Field(500, ge=1, le=1000)
    buffer_size: int = Field(1000, ge=1)

    @model_validator(mode="after")
    def _check_buffer_covers_history(self) -> DataConfig:
        if self.buffer_size < self.history_limit:
            raise ValueError("buffer_size must be >= history_limit")
        return self


class StrategyConfig(_Model):
    name: str
    params: dict[str, object] = Field(default_factory=dict)


class PositionSizingConfig(_Model):
    """Inputs to ``risk.position_sizing``. All three are money arithmetic.

    ``fraction`` and ``risk_per_trade`` multiply equity; ``fixed_amount`` *is* a
    quote-currency amount. All are ``Decimal`` so sizing never has to convert:
    ``Decimal("10000") * 0.02`` raises ``TypeError`` in Python, which is exactly
    the error this typing removes.
    """

    method: PositionSizingMethod = PositionSizingMethod.FIXED_FRACTION
    fraction: Decimal = Field(Decimal("0.02"), gt=0, le=1)
    fixed_amount: Decimal = Field(Decimal("100"), gt=0)
    risk_per_trade: Decimal = Field(Decimal("0.01"), gt=0, le=1)


class StopLossConfig(_Model):
    """Stop-loss placement.

    ``percent`` and ``atr_multiplier`` are ``Decimal``: Phase 5 M2 multiplies
    both by money (the entry price and the ATR value respectively), so the
    ``float`` -> ``Decimal`` conversion happens here, once, at config load -- see
    the module docstring. ``atr_period`` stays ``int``: it is a lookback passed
    to ``indicators.atr``, never multiplied by money.
    """

    enabled: bool = True
    type: StopType = StopType.PERCENT
    percent: Decimal = Field(Decimal("2.0"), gt=0)
    atr_period: int = Field(14, gt=0)
    atr_multiplier: Decimal = Field(Decimal("2.0"), gt=0)


class TakeProfitConfig(_Model):
    """Take-profit placement.

    ``percent`` multiplies the entry price and ``rr_multiple`` multiplies the
    stop distance -- both money arithmetic in Phase 5 M2 -- so both are
    ``Decimal`` from config load. See the module docstring.
    """

    enabled: bool = True
    type: TakeProfitType = TakeProfitType.PERCENT
    percent: Decimal = Field(Decimal("4.0"), gt=0)
    rr_multiple: Decimal = Field(Decimal("2.0"), gt=0)


class TrailingStopConfig(_Model):
    """Trailing-stop placement.

    ``activation_percent`` and ``trail_percent`` are multiplied by the position's
    high-water mark (money) in Phase 5 M2, so both become ``Decimal`` at config
    load. See the module docstring.
    """

    enabled: bool = False
    activation_percent: Decimal = Field(Decimal("1.0"), gt=0)
    trail_percent: Decimal = Field(Decimal("1.0"), gt=0)


class RiskLimitsConfig(_Model):
    """Hard limits applied on top of whatever the sizing method asks for.

    ``max_position_size_percent`` is ``Decimal`` because position sizing caps
    against equity with it. ``max_daily_loss_percent`` joins it as ``Decimal``
    in Phase 5 M3: the daily-loss tracker multiplies it by equity to derive the
    halt threshold, which is money arithmetic, and ``Decimal * float`` raises
    ``TypeError`` -- the error this typing removes.

    ``max_open_positions`` and ``cooldown_minutes`` stay ``int``. One is a count
    and the other a duration; neither is ever multiplied by money.
    """

    max_open_positions: int = Field(3, ge=1)
    max_daily_loss_percent: Decimal = Field(Decimal("5.0"), gt=0)
    max_position_size_percent: Decimal = Field(Decimal("20"), gt=0, le=100)
    cooldown_minutes: int = Field(15, ge=0)


class RiskConfig(_Model):
    position_sizing: PositionSizingConfig = Field(default_factory=PositionSizingConfig)
    stop_loss: StopLossConfig = Field(default_factory=StopLossConfig)
    take_profit: TakeProfitConfig = Field(default_factory=TakeProfitConfig)
    trailing_stop: TrailingStopConfig = Field(default_factory=TrailingStopConfig)
    limits: RiskLimitsConfig = Field(default_factory=RiskLimitsConfig)

    @model_validator(mode="after")
    def _check_stop_distance_is_available(self) -> RiskConfig:
        """Reject config that multiplies a stop distance a disabled stop never gives.

        Both an ``rr`` take-profit and ``risk_per_trade`` sizing derive their size
        from the stop distance; with ``stop_loss.enabled`` false there is no such
        distance. Catching it here fails fast at startup with a clear message,
        rather than raising on the first signal hours into a run. The runtime
        checks in ``risk.rules`` / ``risk.position_sizing`` stay as defence in
        depth -- a caller can pass ``stop_price``/``stop_distance`` directly,
        bypassing config entirely.
        """
        if (
            self.take_profit.enabled
            and self.take_profit.type is TakeProfitType.RR
            and not self.stop_loss.enabled
        ):
            raise ValueError(
                "take_profit.type='rr' sizes the target from the stop distance, but "
                "stop_loss.enabled is false -- enable stop_loss or use "
                "take_profit.type='percent'"
            )
        if (
            self.position_sizing.method is PositionSizingMethod.RISK_PER_TRADE
            and not self.stop_loss.enabled
        ):
            raise ValueError(
                "position_sizing.method='risk_per_trade' sizes from the stop distance, "
                "but stop_loss.enabled is false -- enable stop_loss or choose another "
                "sizing method"
            )
        return self


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
    # Consecutive strategy failures tolerated for one pair before the engine
    # quarantines it (stops evaluating it until restart). A strategy raising on
    # every bar produces no signals but would otherwise log a traceback forever;
    # quarantining makes the failure loud once instead of endless. 0 disables
    # quarantine — errors are still logged, and the pair keeps being retried.
    max_strategy_errors: int = Field(5, ge=0)

    @model_validator(mode="after")
    def _check_backoff_bounds(self) -> EngineConfig:
        if self.reconnect_backoff_max_s < self.reconnect_backoff_s:
            raise ValueError("reconnect_backoff_max_s must be >= reconnect_backoff_s")
        return self


class AppConfig(_Model):
    """Root config object — the fully parsed ``config.yaml``."""

    mode: TradingMode = TradingMode.TESTNET
    exchange: ExchangeConfig = Field(default_factory=ExchangeConfig)
    trading: TradingConfig = Field(default_factory=TradingConfig)
    data: DataConfig = Field(default_factory=DataConfig)
    strategy: StrategyConfig
    risk: RiskConfig = Field(default_factory=RiskConfig)
    backtesting: BacktestConfig
    paper_trading: PaperTradingConfig = Field(default_factory=PaperTradingConfig)
    notifications: NotificationsConfig = Field(default_factory=NotificationsConfig)
    logging: LoggingConfig = Field(default_factory=LoggingConfig)
    database: DatabaseConfig = Field(default_factory=DatabaseConfig)
    engine: EngineConfig = Field(default_factory=EngineConfig)
