"""Portfolio state -- the account the risk manager reads and execution updates.

Design notes
------------
**State lives here; policy lives in ``risk/``.** :class:`Portfolio` holds what
the account *is* (open positions, free quote balance, the day's realised P&L,
per-symbol cooldowns); ``RiskManager`` holds what the operator *configured* and
decides what to do about it. Splitting them that way means the manager stays a
reconstructible, I/O-free policy object, persistence in a later phase has one
object to serialise instead of reaching into a risk component, and backtest and
paper modes reuse the same ledger rather than growing a second one.

**Mutable, by the same rule that makes ``Position`` mutable.** Value objects in
this system are frozen; objects that accumulate over a trade's -- or a run's --
life are not. A frozen snapshot rebuilt per signal would also have nowhere to
record "cooldown started at T", which is a write.

``validate_assignment`` is on, so the ``Money`` guard applies to *assignment*
and not just construction: ``portfolio.free_quote = 1.5`` raises instead of
quietly seeding the account with a binary float. Plain pydantic models only
validate at construction, which leaves exactly the leak path the guard exists
to close.

**Nothing here reads a clock.** Every time-dependent method takes ``now``
explicitly, which keeps the ledger a pure function of its inputs and leaves one
component -- the manager -- knowing what time it is. That is what makes the
daily-loss and cooldown tests hermetic without patching anything. A naive
``datetime`` is rejected rather than assumed to be UTC: guessing a timezone is
how a day boundary silently moves by hours.

**No mark prices are stored.** :meth:`Portfolio.equity` takes them per call.
The alternative -- holding a ``MarketDataProvider`` -- would be an import cycle
(``core.interfaces`` imports this module) and would put I/O behind an attribute
read; passing them in keeps equity a pure calculation over numbers.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import TYPE_CHECKING

from pydantic import BaseModel, ConfigDict, Field

from trading_bot.core.enums import PositionSide
from trading_bot.core.models import Money, Position

if TYPE_CHECKING:  # pragma: no cover - typing only
    from collections.abc import Mapping

#: Divisor for the whole-percent config fields (``5.0`` means 5%).
_PERCENT = Decimal(100)


def _require_aware(name: str, moment: datetime) -> datetime:
    """Reject a naive ``datetime``.

    A naive value would be interpreted as local time by ``astimezone``, moving
    the UTC day boundary by the host's offset -- a daily-loss halt that resets
    at the wrong hour, on a machine whose timezone nobody thought about.
    """
    if moment.tzinfo is None or moment.tzinfo.utcoffset(moment) is None:
        raise ValueError(f"{name} must be timezone-aware, got naive {moment!r}")
    return moment


class Portfolio(BaseModel):
    """Open positions, free balance, and the limit state the risk rules read.

    Constructed by the composition root and passed to
    :meth:`~trading_bot.core.interfaces.RiskManager.approve` per call. The risk
    manager only ever *reads* it; the mutators below are called by execution
    when an order actually fills.
    """

    model_config = ConfigDict(validate_assignment=True)

    #: Currency every balance, P&L and equity figure here is denominated in.
    quote_asset: str = "USDT"
    #: Unencumbered quote balance -- what an order can actually spend.
    free_quote: Money = Decimal(0)
    #: Open positions by symbol. One position per symbol: this system does not
    #: pyramid, and a second entry would have to merge or overwrite.
    positions: dict[str, Position] = Field(default_factory=dict)
    #: Realised P&L accrued on :attr:`pnl_date`. Negative is a loss.
    realised_pnl: Money = Decimal(0)
    #: UTC date :attr:`realised_pnl` belongs to; ``None`` until the first accrual.
    pnl_date: date | None = None
    #: Per-symbol instants before which no new entry is allowed.
    cooldown_until: dict[str, datetime] = Field(default_factory=dict)

    # -- positions ----------------------------------------------------------
    @property
    def open_positions(self) -> list[Position]:
        """Positions with a non-zero size on a real side (never ``FLAT``)."""
        return [position for position in self.positions.values() if position.is_open]

    @property
    def position_count(self) -> int:
        """How many positions count against ``max_open_positions``."""
        return len(self.open_positions)

    def has_position(self, symbol: str) -> bool:
        """Whether ``symbol`` already has an open position."""
        position = self.positions.get(symbol)
        return position is not None and position.is_open

    def equity(self, marks: Mapping[str, Decimal]) -> Decimal:
        """Total portfolio value in the quote currency.

        Free quote balance **plus** the mark-to-market value of every open
        position -- the definition ``size_position`` documents, and the
        difference between "2% of equity per position" meaning a stable size and
        one that shrinks as capital deploys.

        ``marks`` must price every open position. A missing mark raises rather
        than defaulting to the entry price or to zero: both would silently
        misstate equity, and equity is the denominator of every sizing and
        daily-loss decision. The caller (the manager) checks first and turns the
        condition into a representable refusal, so this raise is a contract
        violation, not a market state.

        Raises:
            ValueError: if a position cannot be marked, or is not ``LONG``.
        """
        total = self.free_quote
        for position in self.open_positions:
            if position.side is not PositionSide.LONG:
                raise ValueError(
                    f"cannot value a {position.side.value} position in {position.symbol}: "
                    "spot holdings are long-only"
                )
            mark = marks.get(position.symbol)
            if mark is None:
                raise ValueError(
                    f"no mark price for open position {position.symbol}; equity is unknown"
                )
            total += position.quantity * mark
        return total

    # -- daily realised P&L -------------------------------------------------
    def _roll_day(self, now: datetime) -> None:
        """Reset the ledger if ``now`` falls on a later UTC day than it covers.

        Rolled lazily, on read as well as on write, rather than by a scheduled
        reset. A bot that trades nothing overnight would otherwise carry
        yesterday's halt into a new day and refuse to trade until something
        happened to poke it -- and nothing would.
        """
        today = _require_aware("now", now).astimezone(timezone.utc).date()
        if self.pnl_date != today:
            self.realised_pnl = Decimal(0)
            self.pnl_date = today

    def realised_today(self, now: datetime) -> Decimal:
        """Realised P&L for the UTC day containing ``now``. Negative is a loss."""
        self._roll_day(now)
        return self.realised_pnl

    def record_realised_pnl(self, amount: Decimal, *, now: datetime) -> None:
        """Accrue ``amount`` of realised P&L into the day containing ``now``.

        Called by execution when a position closes. Negative for a loss.
        """
        self._roll_day(now)
        self.realised_pnl = self.realised_pnl + amount

    def daily_loss_exceeded(
        self, *, limit_percent: Decimal, equity: Decimal, now: datetime
    ) -> bool:
        """Whether today's realised loss has breached ``limit_percent`` of equity.

        ``equity`` is the value *now*, not at the start of the day. That is a
        deliberate approximation with a known direction: after a 5% loss equity
        is 95% of where it started, so a 5% cap sits at 4.75% of the original
        and the halt fires marginally **early**. Erring early is the correct
        posture for a loss limit -- the alternative approximation errs late,
        which is the one that costs money. Exact start-of-day semantics would
        require the ledger to be handed mark prices at the day roll, which can
        fall when no signal is in flight.
        """
        threshold = -(equity * limit_percent / _PERCENT)
        return self.realised_today(now) <= threshold

    # -- cooldown -----------------------------------------------------------
    def start_cooldown(self, symbol: str, *, now: datetime, minutes: int) -> None:
        """Block new entries in ``symbol`` for ``minutes`` after ``now``.

        Called by execution when a position closes -- the "do not immediately
        re-enter what just stopped you out" rule. ``minutes == 0`` is a
        supported configuration and records nothing, so no entry is ever blocked
        by a zero-length window.
        """
        _require_aware("now", now)
        if minutes <= 0:
            return
        self.cooldown_until[symbol] = now + timedelta(minutes=minutes)

    def cooldown_expiry(self, symbol: str) -> datetime | None:
        """When ``symbol``'s cooldown ends, or ``None`` if it is not cooling down."""
        return self.cooldown_until.get(symbol)

    def in_cooldown(self, symbol: str, now: datetime) -> bool:
        """Whether ``symbol`` is still cooling down at ``now``.

        Expiry is lazy -- a comparison, not a sweep. There is no timer to run
        and no task to leak, and the number of stale keys is bounded by the
        number of symbols traded.
        """
        _require_aware("now", now)
        expiry = self.cooldown_until.get(symbol)
        return expiry is not None and now < expiry
