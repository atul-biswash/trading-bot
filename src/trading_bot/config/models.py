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
from trading_bot.utils.helpers import timeframe_to_ms


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
    #: Seconds bounding ONE HTTP round trip, applied by handing
    #: ``requests_params={"timeout": ...}`` to ``AsyncClient.create``. It binds
    #: **per attempt**, never per ``_call``: ``base_client._get_request_kwargs``
    #: merges it into the keyword arguments for a single request.
    #:
    #: **IT OVERRUNS ``risk.dispatch_deadline_s`` BY 1.0 s TODAY, DELIBERATELY,
    #: AND THAT IS PINNED.** The ``MARKET`` sell in the close path is the one
    #: venue WRITE that cannot be handed the dispatch budget -- the *port's*
    #: ``create_order`` takes a request and nothing else -- so it runs under this
    #: value. At ``10`` against ``D = 9.0`` a single attempt overruns by 1.0 s,
    #: which ``DispatchBudget.remaining_s`` absorbs by charging the next
    #: invocation's share. The envelope is enforced by
    #: :meth:`AppConfig._check_transport_fits_the_dispatch_deadline`; see
    #: :data:`_TRANSPORT_OVERRUN_TOLERANCE_S` for the measurement.
    #:
    #: **RAISING THIS DISCARDS A CONNECT BOUND YOU DO NOT KNOW EXISTS.**
    #: MEASURED against ``aiohttp 3.14.2``: a per-request ``timeout`` that is a
    #: bare number is coerced by ``ClientSession._request`` to
    #: ``ClientTimeout(total=<number>)``, which **REPLACES** the session's
    #: ``DEFAULT_TIMEOUT`` wholesale rather than overlaying it. That default is
    #: ``ClientTimeout(total=300, connect=None, sock_read=None, sock_connect=30,
    #: ceil_threshold=5)``, so the library's ``sock_connect=30`` is **thrown
    #: away** and this value is the only bound left -- covering DNS, connect,
    #: send and read together. Safe at ``10`` only because 10 is stricter than
    #: the 30 it displaced. Above 30 the connect phase is silently *looser* than
    #: it would have been with no per-request timeout at all. The envelope
    #: validator refuses such a value first, at today's deadline, which is why
    #: this trap is documented rather than guarded twice.
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

    @field_validator("base_currency")
    @classmethod
    def _upper(cls, v: str) -> str:
        """Normalise the quote asset, mirroring ``PairConfig.symbol`` above.

        Exchange payloads name assets in upper case, so anything that compares
        this value against a ``Balance.asset`` or a ``SymbolInfo.quote_asset``
        is comparing an operator-typed string against an exchange-supplied one.
        The composition root normalises both sides itself and does not depend on
        this -- correctness there must not rest on a validator two layers away --
        but leaving the only *un*normalised asset field in the config next to a
        normalised one is an asymmetry the next reader would have to rediscover.
        """
        return v.upper()

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
    """Risk policy. Five of these fields carry numbers that are **not measured**.

    ``max_entry_slippage`` and ``price_band_margin`` are ``Decimal`` because
    both multiply a price; the three ``_s`` durations are ``float`` because they
    are compared against clocks and never against money. That split is the money
    rule applied field by field rather than uniformly: a config field becomes
    ``Decimal`` at the milestone that first multiplies it by money *or compares
    it against money*, and a duration does neither.

    Statuses and provenance for every one of them live in
    ``docs/M5_NUMBERS.md``. Five of the six numbers there are **PLACEHOLDER --
    NOT MEASURED**, and the field docstrings below say which, so a rationale is
    never mistaken for a sample.
    """

    position_sizing: PositionSizingConfig = Field(default_factory=PositionSizingConfig)
    stop_loss: StopLossConfig = Field(default_factory=StopLossConfig)
    take_profit: TakeProfitConfig = Field(default_factory=TakeProfitConfig)
    trailing_stop: TrailingStopConfig = Field(default_factory=TrailingStopConfig)
    limits: RiskLimitsConfig = Field(default_factory=RiskLimitsConfig)

    #: How far above the reference price a marketable entry limit may sit, as a
    #: **fraction** (``0.001`` is 0.1%), not a whole percent. ``Decimal``: it
    #: multiplies a price.
    #:
    #: **The upper bound is a ceiling on absurdity, not a supported range.** The
    #: measured ``PERCENT_PRICE_BY_SIDE`` band is 0.5x-2x of a 5-minute average,
    #: so a working price far above the recent average is itself band-refusable
    #: -- and a band violation refuses the **whole order list**, entry and both
    #: protective legs together, not gracefully. Anything approaching ``0.05`` is
    #: already in that territory and is asking for a market order in disguise.
    #:
    #: **PLACEHOLDER -- NOT MEASURED**, both the default and the bound. The real
    #: value is a quantile of the close-to-ask distance, and no sample exists.
    max_entry_slippage: Decimal = Field(Decimal("0.001"), gt=0, le=Decimal("0.05"))
    #: Safety margin applied to the ``PERCENT_PRICE_BY_SIDE`` band before a
    #: protective price is checked against it, as a fraction. ``Decimal``: it
    #: scales band multipliers that are themselves ``Decimal`` on ``SymbolInfo``.
    #:
    #: Biased **small** on purpose: the exchange enforces the band itself and a
    #: violation is a clean whole-list rejection, so this pre-check exists to
    #: make a refusal legible and save a round trip, not to be the authority.
    #:
    #: **PLACEHOLDER -- NOT MEASURED**, and blocked behind a prior question --
    #: whether the ``avgPrice`` endpoint reports the series the filter is
    #: actually evaluated against.
    price_band_margin: Decimal = Field(Decimal("0.02"), gt=0, le=Decimal("0.5"))
    #: How stale an open position's exchange read may be before new entries are
    #: refused, in **seconds**. A duration compared against the age of a
    #: reconciliation stamp, so ``float`` rather than ``Decimal``.
    #:
    #: **Its meaning is coupled to the shortest enabled timeframe; its type is
    #: not.** The working value is 3x that timeframe -- a policy choice, "two
    #: consecutive budget skips are normal", not a derivation. Lengthen your
    #: shortest bar and this needs raising **by hand**: nothing checks it, and a
    #: value that fires on a healthy system is the worse failure, because an
    #: operator who sees the line every bar stops reading it.
    #:
    #: **PLACEHOLDER -- NOT MEASURED.**
    max_position_staleness_s: float = Field(180.0, gt=0)
    #: Deadline for the **whole dispatch sequence** -- worst case a three-call
    #: ``CLOSE`` -- in seconds. The only configured number of the two; the
    #: per-call share is **derived** from it (3.0 s here), never set.
    #:
    #: Not ``exchange.requests_timeout_s``: at that general 10 s value a
    #: three-call ``CLOSE`` is 30 s and two pairs closing on the same minute is
    #: 60 s, the entire bar, before reconciliation has run.
    #:
    #: **PLACEHOLDER -- NOT MEASURED.** Too tight is the expensive direction: a
    #: placement that times out may in fact have placed.
    #:
    #: **That direction is about the TRANSPORT TIMEOUT -- the derived per-call
    #: share -- and not about the reservation.** A share that is too tight
    #: abandons a write whose outcome is then unknown, which is the expensive
    #: error and is what the sentence above names. A *reservation* that is too
    #: loose fails the other way: the sequence is permitted to spend past the
    #: deadline, and no later edit un-places what it placed. The two quantities
    #: are one division apart and a reader meets them together, so which is
    #: which is stated rather than inferred. This is a clarification; the
    #: sentence above is correct about what it is about.
    #:
    #: > **ANNOTATED at M5f -- "three-call ``CLOSE``" COUNTS Q-C SECTION 4b's
    #: > THREE *STEPS* AS THREE *CALLS*, AND THAT EQUATION IS FALSE.** Nothing
    #: > above is rewritten and the value is untouched: the field is still the
    #: > whole sequence, the share is still derived from it, and the status
    #: > mark still reads PLACEHOLDER -- NOT MEASURED. Only the divisor is
    #: > wrong.
    #: >
    #: > **Why, from three measured facts, each quoted from where it lives.**
    #: > Q-C section 4b, on the middle step: *"The confirming query decides
    #: > what happens next, and it reads ``executedQty`` on each leg, not
    #: > merely ``status``"*. :class:`~trading_bot.core.models.OrderListEntry`,
    #: > MEASURED against a captured payload: *"Q-C section 7's compare set
    #: > (``status``, ``executedQty``, ``origQty``, legally-sendable prices) is
    #: > therefore not obtainable from a list read-back at all; it needs a
    #: > per-order query per leg."* And
    #: > :meth:`~trading_bot.core.interfaces.ExchangeClient.get_order`,
    #: > MEASURED: *"immediately after a cancel, ``get_own_open_orders``
    #: > returned nothing while this endpoint still reported the order as
    #: > ``CANCELED``... never-placed, cancelled and filled are
    #: > indistinguishable from there, and only this separates them."* So the
    #: > confirm step is per-leg point queries; neither enumeration nor a list
    #: > read-back can serve it.
    #: >
    #: > **Measured worst cases, in calls.** OTOCO **5** -- one cancel
    #: > (MEASURED: one cancel collapses the whole list), three point queries,
    #: > one sell. OTO **4**. Unprotected **1**, there being no protection to
    #: > cancel. The recovery-bearing entry path **3** -- place, did-it-place?,
    #: > re-place.
    #: >
    #: > **NO REPLACEMENT SHARE IS STATED HERE.** Whether the confirm step
    #: > queries all three legs or only the two protective ones is **UNRULED**
    #: > and reserved to the project owner; it decides 5 against 4, and a
    #: > divisor written here before that ruling would be the same kind of
    #: > guess this annotation exists to record.
    dispatch_deadline_s: float = Field(9.0, gt=0)
    #: Deadline for **one** position's reconciliation query, in seconds. Bounds
    #: a single slow read so it cannot consume the reserved floor and starve the
    #: rest of the pass.
    #:
    #: **PLACEHOLDER -- NOT MEASURED.**
    reconcile_deadline_s: float = Field(3.0, gt=0)

    @model_validator(mode="after")
    def _check_protective_coverage(self) -> RiskConfig:
        """Reject configurations whose protective coverage is incoherent.

        Four checks, and the third and fourth are different **in kind** from the
        first two.

        The first two are arithmetic: an ``rr`` take-profit and
        ``risk_per_trade`` sizing both derive their number from the stop
        distance, and with ``stop_loss.enabled`` false there is no such
        distance. Catching that here fails fast at startup rather than raising
        on the first signal hours into a run, and the runtime checks in
        ``risk.rules`` / ``risk.position_sizing`` stay as defence in depth --
        a caller can pass ``stop_price``/``stop_distance`` directly, bypassing
        config entirely.

        The third refuses a **take-profit with no stop at all**, and nothing
        downstream is unable to compute it: the exchange accepts that
        configuration, no filter forbids it, and this bot accepted it until
        now. It is refused as a **judgement about payoff shape** -- winners
        truncated while losers run unbounded, and under exchange-resting
        protection the favourable exit survives a crash while the unfavourable
        one does not. There is deliberately **no runtime counterpart** to it,
        because it is an opinion about configuration rather than a precondition
        for arithmetic.

        The fourth is the **same kind as the third** -- a judgement about
        coherence rather than a precondition for arithmetic -- and it refuses a
        trailing stop with no stop-loss. A trailing stop is a *client-side*
        level: it is computed on each closed bar and written onto the position,
        and nothing places or amends an order for it at the exchange. Q-C
        section 3 fixes the legs at three (the working ``LIMIT``, ``STOP_LOSS``
        and ``TAKE_PROFIT``) and section 5 retains the trailing fields "pending
        the trailing milestone". So with no stop leg nothing rests at the venue,
        and the position is protected only while this process is alive and
        evaluating -- which also contradicts what stops-off means, namely that
        the operator owns their exits via ``SignalAction.CLOSE``.

        Order matters between the first and the third. The ``rr`` case is a
        strict subset of the take-profit-only case, so it is checked first to
        earn its more specific message; checked second it would be unreachable.
        The fourth is independent of all three and is checked last, so an
        operator disabling stops while leaving both a take-profit and a trail
        enabled meets the third refusal first and this one after fixing it.
        """
        if (
            self.take_profit.enabled
            and self.take_profit.type is TakeProfitType.RR
            and not self.stop_loss.enabled
        ):
            raise ValueError(
                "take_profit.type='rr' sizes the target from the stop distance, but "
                "stop_loss.enabled is false -- enable stop_loss. (Switching to "
                "take_profit.type='percent' will not help: a take-profit with no stop "
                "is refused on its own account, see below.)"
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
        if self.take_profit.enabled and not self.stop_loss.enabled:
            raise ValueError(
                "take_profit.enabled is true while stop_loss.enabled is false. This bot "
                "refuses a take-profit-only configuration: it truncates winners while "
                "leaving losers unbounded, and under exchange-resting protection the "
                "favourable exit survives a crash while the unfavourable one does not. "
                "This is a JUDGEMENT about payoff shape made by this project -- the "
                "exchange accepts this configuration, no filter forbids it, and this bot "
                "accepted it until now. A wide stop_loss.percent expresses the same "
                "intent and names the tolerance. Disabling both is still supported."
            )
        if self.trailing_stop.enabled and not self.stop_loss.enabled:
            raise ValueError(
                "trailing_stop.enabled is true while stop_loss.enabled is false. A "
                "trailing stop is a CLIENT-SIDE level: it is computed on each closed "
                "bar and written onto the position, and nothing places or amends an "
                "order for it at the exchange -- Q-C places the working leg, the "
                "STOP_LOSS leg and the TAKE_PROFIT leg only, and retains the trailing "
                "fields 'pending the trailing milestone'. So with no stop leg, nothing "
                "rests at the venue and the position is protected only while this "
                "process is alive and evaluating. It also contradicts the meaning of "
                "stops-off, which is that the operator owns their exits via "
                "SignalAction.CLOSE. Enable stop_loss, or disable trailing_stop."
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


#: Pipeline headroom factor for the coherence constraint on :class:`AppConfig`:
#: at most this fraction of the shortest bar may be spent on dispatch plus
#: reconciliation. Not a config field -- it is a property of the pipeline's
#: headroom policy, not of an operator's account.
#:
#: **BOUNDED, not measured.** A measurement exists and constrains what the value
#: must clear, but does not derive it: worst observed pipeline overhead was 2.9%
#: of a 60 s bar across 90 minutes with no bar missed, so 0.5 leaves roughly a
#: 17x margin and jitter is not the binding term. Raising it does not buy
#: headroom; it relocates the constraint onto venue latency, which that probe
#: never sampled. Full provenance and method: ``docs/M5_NUMBERS.md`` section 3.
_PIPELINE_HEADROOM = 0.5


#: Seconds by which ONE transport attempt may exceed ``risk.dispatch_deadline_s``
#: before the dispatch sequence stops being coherent. Not a config field, for
#: :data:`_PIPELINE_HEADROOM`'s reason one step further: it is not a margin an
#: operator may spend but the measured SHAPE of an overrun that already exists.
#:
#: **It is named rather than written inline, and that is the point.** A bare
#: ``1.0`` beside a deadline reads as slack -- a spare second someone may claim --
#: and this is the opposite: it is the exact size of a known breach, recorded so
#: that the breach cannot grow unnoticed. This project has caught the same shape
#: before, in a number that looked like headroom and was a measurement.
#:
#: **MEASURED.** The ``MARKET`` sell in the close path is the one venue WRITE that
#: does not carry the dispatch budget: ``ExchangeClient.create_order`` takes a
#: request and nothing else -- where the *adapter* method accepts ``timeout_s``
#: and ``attempts`` -- so the sell cannot be handed the bounds its own call site
#: computes, and runs under the client's policy at ``requests_timeout_s``.
#:
#: On the path this governs -- a connection timeout -- ``idempotent=False``
#: narrows the retry set to ``RateLimitError`` alone, so exactly ONE attempt is
#: made and the bound is the transport total: **10.0 s against D = 9.0, an
#: overrun of 1.0 s.** Note what that means for the older figure: the 43.5 s
#: worst case (4 x 10 + 3.5) is arithmetically right and describes the
#: *rate-limit* path, and the mismatch here survives even if ``retry_attempts``
#: were cut to 1.
#:
#: **The overrun is ABSORBED, not ignored**, which is what makes this a tolerance
#: and not a breach left standing: ``DispatchBudget.remaining_s`` returns
#: negatives deliberately, so an overrun is charged against the next invocation's
#: share rather than forgotten. That absorption holds only while the gap stays
#: this size -- and pinning that is the whole job of
#: :meth:`AppConfig._check_transport_fits_the_dispatch_deadline`.
_TRANSPORT_OVERRUN_TOLERANCE_S = 1.0

#: Calls in the longest dispatch sequence -- the discretionary close, which is
#: cancel, then confirm by query, then sell. Used only to report the derived
#: per-call share in the refusal message; the configured number is the whole
#: sequence.
#:
#: > **ANNOTATED at M5f, twice over. This is the only place the three is a
#: > VALUE rather than prose, and both halves of the comment above are
#: > wrong.** Neither is rewritten and the value is not touched.
#: >
#: > **First: "cancel, then confirm by query, then sell" is three STEPS, not
#: > three CALLS**, and the middle step is not one call. Q-C section 4b:
#: > *"The confirming query decides what happens next, and it reads
#: > ``executedQty`` on each leg, not merely ``status``"*.
#: > :class:`~trading_bot.core.models.OrderListEntry`, MEASURED against a
#: > captured payload: *"Q-C section 7's compare set (``status``,
#: > ``executedQty``, ``origQty``, legally-sendable prices) is therefore not
#: > obtainable from a list read-back at all; it needs a per-order query per
#: > leg."* And :meth:`~trading_bot.core.interfaces.ExchangeClient.get_order`,
#: > MEASURED: *"immediately after a cancel, ``get_own_open_orders`` returned
#: > nothing while this endpoint still reported the order as ``CANCELED``...
#: > never-placed, cancelled and filled are indistinguishable from there, and
#: > only this separates them."* So the confirm step is per-leg point queries.
#: > **Measured worst cases, in calls:** OTOCO **5**, OTO **4**, unprotected
#: > **1**, and the recovery-bearing entry path **3**.
#: >
#: > **Second: "Used only to report the derived per-call share in the refusal
#: > message" is false -- nothing uses this name at all.** MEASURED by grep
#: > over ``src/`` and ``tests/``: one hit, this definition. The refusal
#: > message below reports the whole-sequence figures and never divides. So a
#: > reader is told this constant has a consumer, and it has none.
#: >
#: > **Neither is corrected here.** Changing the value needs the ruling below;
#: > removing the name is a code change, and this commit is documentation
#: > only. Whether the confirm step queries all three legs or only the two
#: > protective ones is **UNRULED** and reserved to the project owner -- it
#: > decides 5 against 4 -- so no replacement is written.
_CLOSE_SEQUENCE_CALLS = 3


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

    @model_validator(mode="after")
    def _check_transport_fits_the_dispatch_deadline(self) -> AppConfig:
        """Refuse a transport timeout that overruns the dispatch deadline.

        ``exchange.requests_timeout_s <= risk.dispatch_deadline_s +
        _TRANSPORT_OVERRUN_TOLERANCE_S``.

        **A SECOND VALIDATOR RATHER THAN A CLAUSE IN THE FIRST**, because the two
        constrain different things and prescribe different remedies. Its sibling
        asks whether the whole budget fits the *bar*; this asks whether one
        *transport attempt* fits the budget. Folding them would produce one
        message naming five terms for two unrelated breaches, and an operator
        would have to work out which half fired.

        **It lives on :class:`AppConfig` for the structural reason, not by
        preference:** ``requests_timeout_s`` is ``ExchangeConfig``'s and
        ``dispatch_deadline_s`` is ``RiskConfig``'s, and neither model can see
        the other. ``AppConfig`` is the nearest scope holding both.

        **WHAT IT PINS IS A BREACH, NOT A MARGIN.** On the shipped values it
        holds at EXACT equality -- ``10 <= 9.0 + 1.0`` -- with zero headroom, and
        that is deliberate: the tolerance is sized to the overrun that exists, so
        any widening of the gap is a new fact and is refused. A reader who sees
        the equality and reads it as "just fits" has it backwards.

        Pure, runs at config load, costs no round trip, fails before any client
        exists -- the same posture as its sibling.
        """
        timeout_s = self.exchange.requests_timeout_s
        envelope = self.risk.dispatch_deadline_s + _TRANSPORT_OVERRUN_TOLERANCE_S
        if timeout_s <= envelope:
            return self

        raise ValueError(
            f"exchange.requests_timeout_s = {timeout_s}s exceeds the "
            f"{envelope}s envelope allowed by risk.dispatch_deadline_s = "
            f"{self.risk.dispatch_deadline_s}s plus the "
            f"{_TRANSPORT_OVERRUN_TOLERANCE_S}s measured overrun of one attempt.\n"
            "\n"
            "The MARKET sell in the close path is the one venue WRITE that cannot be\n"
            "handed the dispatch budget -- the port's create_order takes a request and\n"
            "nothing else -- so it runs for up to exchange.requests_timeout_s. That\n"
            "overrun is absorbed by DispatchBudget.remaining_s charging it to the next\n"
            "invocation's share, and only while it stays within the measured amount.\n"
            "Raising exchange.requests_timeout_s widens the gap that absorption covers.\n"
            "\n"
            "Lower exchange.requests_timeout_s, or raise risk.dispatch_deadline_s --\n"
            "noting the latter is separately bounded by the pipeline coherence\n"
            "constraint below. A timeout above 30 additionally discards aiohttp's\n"
            "sock_connect=30 default; see exchange.requests_timeout_s for why."
        )

    @model_validator(mode="after")
    def _check_dispatch_budget_fits_the_bar(self) -> AppConfig:
        """Refuse a budget that cannot fit inside the shortest bar.

        ``P_sim x D + N_max x T_recon + min(N_max, P_sim) x T_recon <= alpha x
        T_min``, per candle-handler invocation -- the right unit, because two
        pairs whose bars coincide produce two back-to-back invocations, each
        with a full budget.

        **THE THIRD TERM IS SETTLEMENT, added by the project owner's ruling at
        M5k.** Booking an exit fetches that order's fills once, bounded by
        ``reconcile_deadline_s`` at one attempt, and neither of the first two
        terms counts that call. At most one settlement runs per position per
        bar -- a position the reconciler books is gone before the executor
        runs, and one in the executor's hands has no fill for the reconciler
        to book -- and positions are keyed by symbol and capped at
        ``max_open_positions``, so ``min(N_max, P_sim)`` bounds how many can
        exit on one bar.

        It lives on :class:`AppConfig` rather than :class:`RiskConfig` because
        two of its five terms come from ``trading.pairs``, which ``RiskConfig``
        cannot see. Pure, runs at config load, costs no round trip, and fails
        before any client exists.

        Reconciliation does **not** carry ``P_sim``: passes are deduplicated by
        the reconciliation stamp, so the second invocation on a coinciding
        minute finds every stamp fresh and does nothing. Dispatch does, because
        two pairs can each emit a signal on the same minute.
        """
        enabled = self.trading.enabled_pairs
        if not enabled:
            # Vacuously satisfied: no pipeline to overrun, and `T_min` is
            # undefined rather than zero. This is NOT an oversight and must not
            # be "fixed" into a refusal -- `engine.modes.live_system` already
            # refuses an empty enabled-pair set AT BOOT, with a message about
            # the operational consequence ("the bot would connect, seed nothing,
            # and sit silent"). Refusing here too would give one configuration
            # two different errors depending on which check ran first, and would
            # move a boot refusal into config load, where `main.py` reports it
            # differently.
            return self

        t_min_s = min(timeframe_to_ms(pair.timeframe) for pair in enabled) / 1000
        p_sim = len(enabled)
        n_max = self.risk.limits.max_open_positions
        exiting = min(n_max, p_sim)
        dispatch = p_sim * self.risk.dispatch_deadline_s
        reconcile = n_max * self.risk.reconcile_deadline_s
        settlement = exiting * self.risk.reconcile_deadline_s
        budget = _PIPELINE_HEADROOM * t_min_s

        if dispatch + reconcile + settlement <= budget:
            return self

        shortest = min(enabled, key=lambda pair: timeframe_to_ms(pair.timeframe))
        raise ValueError(
            f"risk.dispatch_deadline_s = {self.risk.dispatch_deadline_s} x {p_sim} pair(s) "
            f"that can close simultaneously, plus risk.reconcile_deadline_s = "
            f"{self.risk.reconcile_deadline_s} x limits.max_open_positions = {n_max}, "
            f"plus settlement at risk.reconcile_deadline_s = "
            f"{self.risk.reconcile_deadline_s} x {exiting} position(s) that can exit on one "
            f"bar, is {dispatch + reconcile + settlement:.1f}s. That exceeds "
            f"{_PIPELINE_HEADROOM:.0%} of the shortest enabled timeframe "
            f"({shortest.symbol}/{shortest.timeframe} = {t_min_s:.0f}s, budget {budget:.1f}s).\n"
            "\n"
            "The signal handler runs inline on the candle pipeline, so a bar closing\n"
            "while it is still working is missed and never backfilled -- and a gap\n"
            "re-masks ATR to NaN long after warmup, disabling ATR stops on that pair.\n"
            "\n"
            "Lower risk.dispatch_deadline_s, lower risk.reconcile_deadline_s, lower\n"
            "risk.limits.max_open_positions, enable fewer pairs, or configure a longer\n"
            "shortest timeframe in config.yaml."
        )
