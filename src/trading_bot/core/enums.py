"""Enumerations shared across the domain.

Values are chosen to line up with Binance's REST API strings where relevant so
that mapping to/from the exchange stays trivial.
"""

from __future__ import annotations

from enum import Enum


class TradingMode(str, Enum):
    """How the bot connects to the market and whether real orders are placed."""

    TESTNET = "testnet"  # real API, fake money
    LIVE = "live"  # real API, real money
    PAPER = "paper"  # local simulator, live prices, no orders sent
    BACKTEST = "backtest"  # historical replay, no live connection

    @property
    def uses_real_money(self) -> bool:
        return self is TradingMode.LIVE

    @property
    def is_live_connection(self) -> bool:
        """True when a live exchange connection is required (testnet or live)."""
        return self in (TradingMode.TESTNET, TradingMode.LIVE)


class OrderSide(str, Enum):
    BUY = "BUY"
    SELL = "SELL"

    @property
    def opposite(self) -> OrderSide:
        return OrderSide.SELL if self is OrderSide.BUY else OrderSide.BUY


class OrderType(str, Enum):
    MARKET = "MARKET"
    LIMIT = "LIMIT"
    STOP_LOSS = "STOP_LOSS"
    STOP_LOSS_LIMIT = "STOP_LOSS_LIMIT"
    TAKE_PROFIT = "TAKE_PROFIT"
    TAKE_PROFIT_LIMIT = "TAKE_PROFIT_LIMIT"


class OrderStatus(str, Enum):
    NEW = "NEW"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    FILLED = "FILLED"
    CANCELED = "CANCELED"
    PENDING_CANCEL = "PENDING_CANCEL"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"

    @property
    def is_open(self) -> bool:
        return self in (OrderStatus.NEW, OrderStatus.PARTIALLY_FILLED)

    @property
    def is_closed(self) -> bool:
        return not self.is_open


class TimeInForce(str, Enum):
    GTC = "GTC"  # good till canceled
    IOC = "IOC"  # immediate or cancel
    FOK = "FOK"  # fill or kill


class PositionSide(str, Enum):
    LONG = "LONG"
    SHORT = "SHORT"
    FLAT = "FLAT"


class SignalAction(str, Enum):
    """A strategy's instruction for a single symbol on a single candle.

    There is deliberately no ``HOLD``. ``Strategy.generate_signal`` returns
    ``None`` to mean "no opinion", and two spellings of the same state is an
    invitation for one consumer to handle one of them and miss the other. A
    strategy with nothing to say emits nothing at all.
    """

    BUY = "BUY"  # open / add to a long
    SELL = "SELL"  # open / add to a short (spot: typically ignored)
    CLOSE = "CLOSE"  # exit any open position


class RiskRule(str, Enum):
    """Which risk rule refused a signal, reported by ``RiskManager.approve``.

    Richer than a boolean for the same reason :class:`SignalAction` has no
    ``HOLD``: an operator staring at a bot that stopped entering needs to know
    *which* limit is holding it back, and "False" cannot say. It names only the
    rules :meth:`~trading_bot.core.interfaces.RiskManager.approve` itself
    evaluates -- sizing and protective-level refusals carry their own reasons on
    ``SizingDecision`` / ``ProtectiveLevels``.

    The first two are portfolio-wide states in which *no* entry is acceptable;
    the middle two are facts about one symbol; the last is the portfolio-wide
    count, which only applies to a genuinely new position.
    """

    NO_MARK_PRICE = "no_mark_price"  # an open position cannot be valued
    NO_EQUITY = "no_equity"  # equity is not strictly positive
    DAILY_LOSS_HALT = "daily_loss_halt"  # realised loss today breached the cap
    ALREADY_IN_POSITION = "already_in_position"
    COOLDOWN = "cooldown"  # symbol still cooling down after an exit
    MAX_OPEN_POSITIONS = "max_open_positions"


class RefusalStage(str, Enum):
    """Where in ``RiskManager.evaluate`` a signal stopped.

    One value per refusal path, in the order ``evaluate`` reaches them, and
    reported by ``evaluate`` itself on
    :attr:`~trading_bot.risk.manager.RiskAssessment.stage`. Nothing infers it:
    four of the refusals return every component as ``None`` -- unknown pair,
    unusable price, ``SELL``, nothing-to-close -- so an outside observer could
    tell them apart only by re-deriving ``evaluate``'s control flow, which is
    exactly what a new refusal path or a reordered pair of checks would
    invalidate in silence.

    **Coarser than :class:`RiskRule`, and deliberately so.**
    :attr:`LIMIT_REFUSED` covers all five limit rules, because a stage says
    *where* evaluation stopped while ``RiskDecision.rule`` says *which* limit
    fired -- and the decision is populated at that site, so nothing is lost.
    Splitting it would duplicate ``RiskRule`` into a second vocabulary that has
    to be kept in sync by hand. :attr:`NO_MARK_PRICE` looks like the exception
    but is not: it refuses structurally *before* the limits are consulted at
    all, so it is an inability to compute equity rather than a limit's verdict,
    and it is the one place the two vocabularies genuinely coincide.

    There is no ``UNCLASSIFIED``. Every member here is reachable, because
    ``RiskAssessment``'s validator binds a refusal to naming one; an
    unreachable member would invite defensive branching on a state the domain
    forbids, and would sit there as a tempting default for the next refusal
    path somebody adds.
    """

    UNKNOWN_PAIR = "unknown_pair"
    NO_REFERENCE_PRICE = "no_reference_price"
    NOTHING_TO_CLOSE = "nothing_to_close"
    UNSUPPORTED_ACTION = "unsupported_action"
    NO_MARK_PRICE = "no_mark_price"
    LIMIT_REFUSED = "limit_refused"
    ATR_UNAVAILABLE = "atr_unavailable"
    STOP_UNPLACEABLE = "stop_unplaceable"
    SIZE_NOT_TRADEABLE = "size_not_tradeable"
    UNAFFORDABLE = "unaffordable"


class PositionSizingMethod(str, Enum):
    FIXED_FRACTION = "fixed_fraction"
    FIXED_AMOUNT = "fixed_amount"
    RISK_PER_TRADE = "risk_per_trade"


class StopType(str, Enum):
    PERCENT = "percent"
    ATR = "atr"


class TakeProfitType(str, Enum):
    PERCENT = "percent"
    RR = "rr"  # multiple of the stop distance (risk/reward)
