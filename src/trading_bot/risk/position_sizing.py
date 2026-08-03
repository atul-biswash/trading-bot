"""Position sizing -- how much to buy, in units the exchange will actually accept.

Turns ``(equity, entry price, optional stop price, config)`` into a quantity.
Three methods, selected by :class:`~trading_bot.core.enums.PositionSizingMethod`:

``fixed_fraction``
    Deploy a fixed fraction of equity as notional: ``equity * fraction / price``.
``fixed_amount``
    Deploy a fixed number of quote units: ``amount / price``.
``risk_per_trade``
    Deploy whatever quantity makes the loss-at-stop equal a fixed fraction of
    equity: ``equity * risk_per_trade / |entry - stop|``. The entry price does
    not appear in that formula, which is the point of the method -- what is held
    constant is the *loss*, not the notional.

Design notes
------------
**Everything here is ``Decimal``; nothing here converts anything.** The
``float`` -> ``Decimal`` conversion happens once, in ``config/models.py``, where
pydantic validates ``config.yaml``. That is why there is no ``Decimal(str(x))``
in this module and no opportunity for one to be forgotten.

**Rounding is always down**, via :func:`~trading_bot.utils.helpers.round_step_size`
(``ROUND_DOWN``), reusing the function order dispatch already relies on rather
than growing a second one. Rounding a quantity *up* to the lot step can overspend
free balance -- the order is rejected, or worse, filled. Down is the only safe
direction for money. It is applied **last**, after the position cap, so neither
the configured size nor ``max_position_size_percent`` can be exceeded by the
rounding itself. Both operations only ever reduce, which is what lets
:class:`~trading_bot.core.models.SizingDecision` assert
``quantity <= requested_quantity``.

**Exchange filters are applied here, not deferred to execution.** Sizing takes
:class:`~trading_bot.core.models.SymbolInfo` and returns a quantity that already
satisfies ``step_size``, ``min_qty`` and ``min_notional``. The alternative --
return a raw size and let the adapter clamp it -- fails on two counts.
``BinanceClient._enforce`` signals filter violations by *raising*, and "too small
to trade" is a routine outcome on a small account, not an exceptional one; that
path would run on every signal. And a quantity that can never be accepted is a
lie in the domain: logs, notifications and the paper simulator would all report a
number that will not exist. ``_enforce`` stays exactly as it is, an independent
last line of defence immediately before dispatch.

**Precision.** Intermediate division runs in the ambient ``decimal`` context
(28 significant digits by default). This cannot affect the answer: the result is
truncated down to ``step_size`` as the final step, and a lot step is many orders
of magnitude coarser than the 28th significant digit. The returned quantity is
therefore an exact multiple of ``step_size``, which the tests assert directly.

**``min_notional`` is checked at the lowest price the trade will carry, not at
the entry price.** Binance evaluates the notional of *every* order, and for an
algo order that includes ``stopPrice * quantity``. A protective stop rests below
the entry on a long, so its notional is smaller: a quantity that clears the
filter at the entry can be rejected at the stop with ``-1013 Filter failure:
NOTIONAL``, and under a bracketed entry that rejection takes the whole order
list with it. ``stop_price`` -- already a parameter, because ``risk_per_trade``
sizes from it -- is therefore also the notional floor. The two uses are one
number for one reason: where the stop actually is.

The comparison is ``min(price, stop_price)`` rather than ``stop_price``
directly. Nothing here assumes which side of the entry the stop sits on --
``size_by_risk_per_trade`` deliberately takes an absolute distance -- and
``min`` keeps that property intact.

**Market orders.** ``min_notional`` is checked against the signal's reference
price. A market order can fill slightly away from it, so a quantity that clears
the filter here can still be rejected at the exchange. That is the honest limit
of checking before dispatch, and the reason ``_enforce`` re-checks.
"""

from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING

from trading_bot.core.enums import PositionSizingMethod
from trading_bot.core.models import SizingDecision
from trading_bot.utils.helpers import round_step_size

if TYPE_CHECKING:  # pragma: no cover - typing only
    from trading_bot.config.models import PositionSizingConfig, RiskLimitsConfig
    from trading_bot.core.models import SymbolInfo

#: Divisor for the ``*_percent`` config fields, which are whole percents.
_PERCENT = Decimal(100)


def _require_positive(name: str, value: Decimal) -> None:
    """Reject a non-positive input that would make the result meaningless.

    These are contract violations rather than market conditions. Zero equity
    reaching the sizer means an upstream gate failed; a non-positive price means
    corrupt market data. Returning a plausible-looking "no trade" for either
    would bury the bug, so both raise.
    """
    if value <= 0:
        raise ValueError(f"{name} must be > 0, got {value}")


def size_by_fixed_fraction(*, equity: Decimal, price: Decimal, fraction: Decimal) -> Decimal:
    """Quantity worth ``fraction`` of ``equity`` at ``price``.

    Raises ``ValueError`` unless ``equity``, ``price`` and ``fraction`` are all
    strictly positive.
    """
    _require_positive("equity", equity)
    _require_positive("price", price)
    _require_positive("fraction", fraction)
    return equity * fraction / price


def size_by_fixed_amount(*, price: Decimal, amount: Decimal) -> Decimal:
    """Quantity worth exactly ``amount`` quote units at ``price``.

    Equity is not a parameter: this method is deliberately independent of
    account size. The ``max_position_size_percent`` cap applied by
    :func:`calculate_position_size` is what keeps it sane on a small account.
    """
    _require_positive("price", price)
    _require_positive("amount", amount)
    return amount / price


def size_by_risk_per_trade(
    *,
    equity: Decimal,
    entry_price: Decimal,
    stop_price: Decimal,
    risk_fraction: Decimal,
) -> Decimal:
    """Quantity whose loss at ``stop_price`` equals ``risk_fraction`` of equity.

    Holding ``q`` units and exiting at the stop loses ``q * |entry - stop|``.
    Setting that equal to ``equity * risk_fraction`` gives the quantity below,
    in which ``entry_price`` appears only through the distance.

    The distance is taken as an absolute value: which side the stop belongs on
    is decided by whoever computes it (the protective-exit rules), where the
    trade direction is known. Sizing only needs a width, and a width of zero is
    rejected rather than divided by.
    """
    _require_positive("equity", equity)
    _require_positive("entry_price", entry_price)
    _require_positive("stop_price", stop_price)
    _require_positive("risk_fraction", risk_fraction)

    distance = abs(entry_price - stop_price)
    if distance == 0:
        raise ValueError(
            f"stop_price must differ from entry_price to size by risk (both are {entry_price})"
        )
    return equity * risk_fraction / distance


def _requested_quantity(
    *,
    equity: Decimal,
    price: Decimal,
    sizing: PositionSizingConfig,
    stop_price: Decimal | None,
) -> Decimal:
    """Dispatch to the configured method and return its unconstrained quantity."""
    match sizing.method:
        case PositionSizingMethod.FIXED_FRACTION:
            return size_by_fixed_fraction(equity=equity, price=price, fraction=sizing.fraction)
        case PositionSizingMethod.FIXED_AMOUNT:
            return size_by_fixed_amount(price=price, amount=sizing.fixed_amount)
        case PositionSizingMethod.RISK_PER_TRADE:
            if stop_price is None:
                raise ValueError(
                    "position_sizing.method='risk_per_trade' sizes from the distance "
                    "to the stop, so a stop_price is required; either supply one or "
                    "enable risk.stop_loss in config.yaml"
                )
            return size_by_risk_per_trade(
                equity=equity,
                entry_price=price,
                stop_price=stop_price,
                risk_fraction=sizing.risk_per_trade,
            )
        case _:  # pragma: no cover - defensive; the enum is closed
            raise ValueError(f"Unsupported position sizing method: {sizing.method!r}")


def calculate_position_size(
    *,
    symbol_info: SymbolInfo,
    equity: Decimal,
    price: Decimal,
    sizing: PositionSizingConfig,
    limits: RiskLimitsConfig,
    stop_price: Decimal | None = None,
) -> SizingDecision:
    """Size a position and make it tradeable, or explain why it is not.

    The pipeline, in an order chosen so each step can only reduce the previous
    one: pick the raw quantity from the configured method; cap it at
    ``limits.max_position_size_percent`` of equity; round it **down** to the
    symbol's lot ``step_size``; then verify it clears ``min_qty`` and
    ``min_notional``.

    ``stop_price`` does two jobs, and they are the same fact: it is the distance
    basis for ``risk_per_trade``, and it is the price ``min_notional`` is
    measured at, because a protective leg resting there carries a smaller
    notional than the entry does. A size that clears the filter at the entry and
    fails at the stop is **refused**, never rounded up to clear -- every step in
    this pipeline only reduces, and raising the quantity could breach both the
    position cap and the risk budget.

    Capping before rounding matters. Rounding first and capping second could
    leave a quantity that is a valid lot multiple but sits fractionally above the
    cap, forcing a second rounding pass; this order needs only one.

    ``equity`` is total portfolio value in the quote currency (see
    :meth:`~trading_bot.core.interfaces.RiskManager.size_position`); confirming
    that free balance actually covers the order is the caller's job.

    Returns a :class:`~trading_bot.core.models.SizingDecision`. A zero quantity
    is a normal result, not an error, and always carries a reason.

    Raises:
        ValueError: if ``equity`` or ``price`` is not strictly positive, or if
            the configured method is ``risk_per_trade`` and no usable
            ``stop_price`` was supplied. These are contract violations, not
            market conditions.
    """
    _require_positive("equity", equity)
    _require_positive("price", price)

    requested = _requested_quantity(
        equity=equity, price=price, sizing=sizing, stop_price=stop_price
    )

    # Hard cap on any single position, applied to every method.
    max_notional = equity * limits.max_position_size_percent / _PERCENT
    max_quantity = max_notional / price
    capped = requested > max_quantity
    quantity = min(requested, max_quantity)

    # Down to a whole number of lots. Never up: see the module docstring.
    quantity = round_step_size(quantity, symbol_info.step_size)

    basis = sizing.method.value
    if capped:
        basis = f"{basis}, capped at {limits.max_position_size_percent}% of equity"

    def reject(detail: str) -> SizingDecision:
        return SizingDecision(
            symbol=symbol_info.symbol,
            quantity=Decimal(0),
            requested_quantity=requested,
            reason=f"no trade ({basis}): {detail}",
        )

    if quantity <= 0:
        return reject(f"size {requested} rounds to zero at step_size {symbol_info.step_size}")
    if quantity < symbol_info.min_qty:
        return reject(f"quantity {quantity} below min_qty {symbol_info.min_qty}")

    # The stop rests below the entry on a long, so its notional is the smaller
    # one and it is the one the exchange rejects. See the module docstring.
    binding_price = price if stop_price is None else min(price, stop_price)
    notional = quantity * binding_price
    if notional < symbol_info.min_notional:
        return reject(
            f"notional {notional} at {binding_price} below min_notional {symbol_info.min_notional}"
        )

    return SizingDecision(
        symbol=symbol_info.symbol,
        quantity=quantity,
        requested_quantity=requested,
        reason=f"{basis}: {quantity} at {price} = {notional} quote",
    )
