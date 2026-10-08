"""The backtest's fill model: pure functions from a bar and a level to a price.

This is the one component of the backtest whose error is silent. A wrong fill price books a
plausible trade at a wrong figure, and nothing downstream can tell; so it is pure, it has no
clock and no state, every figure is a ``Decimal``, and every rule below is a function the
mutation survey of M5m's Q2 can break one line at a time.

**Long only, because spot is.** ``SignalAction.SELL`` means "open a short" and is unreachable.

**The rules, each with its source.**

* **Entry** (P99). An order is placed at the instant a signal bar closes. It fills at the NEXT
  bar's open plus ``slippage_percent``, and only if that price is at or below the entry limit;
  otherwise it is refused, as the live ``FOK`` limit is. It never fills later in the bar, and
  never at the bar's close. If the next slot is missing the order EXPIRES (R-W(d)): a ``FOK``
  that cannot fill at once does not wait for a bar that may never come.
* **Protection** (P99, R-B2, R-P1, R-W). Both protective legs are market orders once triggered.
  The stop triggers when the bar's low is at or below it; the take-profit when the bar's high is
  at or above it. **When one bar touches both, the stop wins** -- the same rule
  ``risk.rules.should_exit`` encodes, and a test holds the two to agreement. A stop fills at its
  trigger less ``stop_slippage_percent``; **if the bar's open is already at or through the
  stop, it fills at the OPEN less the same slippage** (R-P1, extended to every bar by R-W(b)),
  because the open is the first price at which the stop could trade. A take-profit fills at
  **its trigger** less ``stop_slippage_percent`` (R-W(a)), **and never at a better open**
  (R-P1): a bar that gaps over the target is not credited the gap.
* **``CLOSE``** (P99). A ``MARKET`` sell at the open of the bar it is handed, less
  ``slippage_percent``. Which bar that is -- the next one, or the first after a gap, which is
  where R-W(d) queues it -- is the caller's sequencing and not this module's.
* **Fees** (R-W(c)). ``fee_percent`` of each leg's notional, charged in the quote asset. The
  ENTRY fee is folded into the entry quote total, which is what the ledger books the entry
  against, and is also returned separately so a trade log can show it and S3 can sum it; the
  EXIT fee is returned for ``Portfolio.close_position`` to subtract. The live ledger is gross
  of entry fees (the owner's R-a); this one is net of both, and the base-asset reality of a
  BUY commission is N6's and is deferred.

**Two accepted biases, both against the strategy, and stated so a result is not read as free
of them.** At a gapped-through stop the open is already worse than the stop, and the stop
slippage is then charged on top of the open: the gap and the slippage both count (R-W, last
sentence). And a take-profit is credited its trigger, never a better open, while a stop is
charged a worse one.

**Prices are not rounded to the tick.** Slippage is a modelled move and not an order price,
and an exact ``Decimal`` product keeps the arithmetic reproducible to the last digit. Rounding
to the tick is a refinement nobody has ruled.

**No wall clock.** Nothing here reads a time except to compare two instants it is handed.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import TYPE_CHECKING

from trading_bot.core.models import Candle
from trading_bot.risk.rules import ExitReason

if TYPE_CHECKING:  # pragma: no cover - typing only
    from trading_bot.config.models import BacktestConfig

__all__ = [
    "EntryBooking",
    "EntryFill",
    "EntryOutcome",
    "ExitBooking",
    "FillParameters",
    "ProtectiveFill",
    "book_entry",
    "book_exit",
    "fill_close",
    "fill_entry",
    "fill_protective",
]

_ONE = Decimal(1)
_HUNDRED = Decimal(100)


@dataclass(frozen=True)
class FillParameters:
    """The three percents the fill model charges, each with the owner's default.

    All are whole percents (``0.1`` is 0.1%), ``Decimal`` and checked: a ``float`` is refused,
    because ``Decimal * float`` raises at the use and a silent coercion would not. They are
    non-negative and below 100, so a sell cannot be priced at or below zero.

    * ``fee_percent``: per leg, on its notional. Default 0.1, Binance Spot's standard rate.
    * ``slippage_percent``: the adverse move on the entry and on a ``CLOSE``. Default 0.05.
    * ``stop_slippage_percent``: the adverse move on a protective leg, the take-profit
      included. Default 1.20, the owner's R-B2.
    """

    fee_percent: Decimal = Decimal("0.1")
    slippage_percent: Decimal = Decimal("0.05")
    stop_slippage_percent: Decimal = Decimal("1.20")

    def __post_init__(self) -> None:
        for name in ("fee_percent", "slippage_percent", "stop_slippage_percent"):
            value = getattr(self, name)
            if type(value) is not Decimal:
                raise TypeError(f"{name} must be a Decimal, not {type(value).__name__}")
            if not value.is_finite() or not Decimal(0) <= value < _HUNDRED:
                raise ValueError(f"{name} must be at least 0 and below 100, got {value}")

    @classmethod
    def from_config(cls, config: BacktestConfig) -> FillParameters:
        """The parameters a ``BacktestConfig`` carries, which are already ``Decimal``."""
        return cls(
            fee_percent=config.fee_percent,
            slippage_percent=config.slippage_percent,
            stop_slippage_percent=config.stop_slippage_percent,
        )


def _worse_for_a_buyer(price: Decimal, percent: Decimal) -> Decimal:
    return price * (_ONE + percent / _HUNDRED)


def _worse_for_a_seller(price: Decimal, percent: Decimal) -> Decimal:
    return price * (_ONE - percent / _HUNDRED)


def _require_positive(name: str, value: Decimal) -> None:
    if value <= 0:
        raise ValueError(f"{name} must be positive, got {value}")


# --------------------------------------------------------------------------
# Entry
# --------------------------------------------------------------------------
class EntryOutcome(str, Enum):
    """What became of an entry order."""

    #: Filled at the next bar's open plus slippage, at or below the limit.
    FILLED = "filled"
    #: The next slot was missing, so the ``FOK`` order found no bar to fill on.
    EXPIRED = "expired"
    #: The next bar's open plus slippage was above the limit, as the live ``FOK`` is refused.
    REFUSED = "refused"


@dataclass(frozen=True)
class EntryFill:
    """The outcome of an entry order. ``price`` is set only when it ``FILLED``."""

    outcome: EntryOutcome
    price: Decimal | None
    detail: str


def fill_entry(
    *,
    entry_limit: Decimal,
    placed_at: datetime,
    next_bar: Candle | None,
    params: FillParameters,
) -> EntryFill:
    """Fill an entry placed at ``placed_at`` against ``next_bar``, or say why it did not.

    ``placed_at`` is the instant the order went in, which is the nominal close of the signal
    bar. ``next_bar`` is the next bar the store holds, or ``None`` if there is none. The order
    can only fill on the bar that OPENS at ``placed_at``; a bar that opens later means the
    slot in between is missing, and the order expires.

    :raises ValueError: ``entry_limit`` is not positive, or ``next_bar`` opened BEFORE the
        order was placed, which no caller can mean.
    """
    _require_positive("entry_limit", entry_limit)
    if next_bar is None:
        return EntryFill(EntryOutcome.EXPIRED, None, "there is no next bar")
    if next_bar.open_time < placed_at:
        raise ValueError(
            f"the next bar opened at {next_bar.open_time}, before the order was placed at "
            f"{placed_at}"
        )
    if next_bar.open_time > placed_at:
        return EntryFill(
            EntryOutcome.EXPIRED,
            None,
            f"the slot at {placed_at} is missing; the next bar opens at {next_bar.open_time}",
        )
    price = _worse_for_a_buyer(next_bar.open, params.slippage_percent)
    if price <= entry_limit:
        return EntryFill(EntryOutcome.FILLED, price, f"{price} is within the limit {entry_limit}")
    return EntryFill(
        EntryOutcome.REFUSED, None, f"{price} is above the limit {entry_limit}; the FOK is refused"
    )


@dataclass(frozen=True)
class EntryBooking:
    """What an entry fill costs, with the fee kept visible.

    ``quote_total`` is ``notional + fee``: the figure the ledger debits and books the entry
    against. ``fee`` is also here on its own, for the trade log.
    """

    quantity: Decimal
    price: Decimal
    notional: Decimal
    fee: Decimal
    quote_total: Decimal


def book_entry(*, quantity: Decimal, price: Decimal, params: FillParameters) -> EntryBooking:
    """The notional, fee and quote total of buying ``quantity`` at ``price``."""
    _require_positive("quantity", quantity)
    _require_positive("price", price)
    notional = quantity * price
    fee = notional * params.fee_percent / _HUNDRED
    return EntryBooking(quantity, price, notional, fee, notional + fee)


# --------------------------------------------------------------------------
# Protection
# --------------------------------------------------------------------------
@dataclass(frozen=True)
class ProtectiveFill:
    """A protective leg that triggered on a bar, and the price it filled at.

    ``open_through_trigger`` is true when the bar OPENED at or beyond the trigger: for a stop,
    at or below it (the stop gapped), for a take-profit, at or above it. A trade log reports
    it, and the stop's price differs because of it.
    """

    reason: ExitReason
    price: Decimal
    trigger: Decimal
    open_through_trigger: bool


def fill_protective(
    *,
    stop_loss: Decimal | None,
    take_profit: Decimal | None,
    bar: Candle,
    params: FillParameters,
) -> ProtectiveFill | None:
    """Whether a long position's protective legs trigger on ``bar``, and at what price.

    ``None`` means neither did. Either level may be absent (a leg that is not enabled).
    **A bar that touches both is a stop**: the stop is tested first and returns. The stop
    triggers when ``bar.low <= stop_loss`` and fills at the trigger less
    ``stop_slippage_percent``, or at ``bar.open`` less the same when the open is already at or
    through the stop. The take-profit triggers when ``bar.high >= take_profit`` and fills at its
    trigger less ``stop_slippage_percent``, whatever the open.

    :raises ValueError: a level is not positive, or the stop is not below the take-profit.
    """
    if stop_loss is not None:
        _require_positive("stop_loss", stop_loss)
    if take_profit is not None:
        _require_positive("take_profit", take_profit)
    if stop_loss is not None and take_profit is not None and stop_loss >= take_profit:
        raise ValueError(f"stop_loss {stop_loss} must be below take_profit {take_profit}")

    if stop_loss is not None and bar.low <= stop_loss:
        through = bar.open <= stop_loss
        base = bar.open if through else stop_loss
        price = _worse_for_a_seller(base, params.stop_slippage_percent)
        return ProtectiveFill(ExitReason.STOP_LOSS, price, stop_loss, through)
    if take_profit is not None and bar.high >= take_profit:
        price = _worse_for_a_seller(take_profit, params.stop_slippage_percent)
        return ProtectiveFill(ExitReason.TAKE_PROFIT, price, take_profit, bar.open >= take_profit)
    return None


# --------------------------------------------------------------------------
# CLOSE and the exit booking
# --------------------------------------------------------------------------
def fill_close(*, bar: Candle, params: FillParameters) -> Decimal:
    """The price of a ``MARKET`` sell on ``bar``: its open less ``slippage_percent``."""
    return _worse_for_a_seller(bar.open, params.slippage_percent)


@dataclass(frozen=True)
class ExitBooking:
    """What an exit fill returns: ``gross`` is the exit quote total, ``fee`` is subtracted."""

    quantity: Decimal
    price: Decimal
    gross: Decimal
    fee: Decimal
    net: Decimal


def book_exit(*, quantity: Decimal, price: Decimal, params: FillParameters) -> ExitBooking:
    """The gross, fee and net of selling ``quantity`` at ``price``; the fee is on the gross."""
    _require_positive("quantity", quantity)
    _require_positive("price", price)
    gross = quantity * price
    fee = gross * params.fee_percent / _HUNDRED
    return ExitBooking(quantity, price, gross, fee, gross - fee)
