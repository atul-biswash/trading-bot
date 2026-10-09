"""Performance metrics (S3): what a backtest's trades and equity curve say, each with its denominator.

Everything here is pure: no file, no clock, no store. The inputs are the closed trades of a run
(:class:`TradeFacts`), the equity summary the run's per-bar loop accumulated
(:class:`EquityCurve` / :class:`EquitySummary`) and, optionally, the committed regime labels.
Every money figure is ``Decimal``, in the quote asset, and every ratio is a ``Decimal`` quotient
that is REPORTED and never booked; each states what it is a fraction of in
:data:`DENOMINATORS`, which :meth:`Metrics.to_record` writes into the record beside the figures.

**The project owner's rulings this implements, verbatim.**

R-AJ: *"Maximum drawdown is the largest peak-to-trough decline of mark-to-market equity, sampled
at every bar of any pair, as a fraction of the running peak. It is computed in the loop,
exactly. Daily closing equity is recorded for Sharpe and Sortino, annualised over 365 days."*

R-AK: *"The per-trade return and its 95% interval are computed exactly as
scripts/trade_census.py computes them (z = 1.96, sample sd, return on the entry quote total),
and parity is proven by test on a shared set of trades."*

**Drawdown is sampled at every bar and compared without a division.** :class:`EquityCurve` keeps
the pair (peak, trough) that has the largest decline as a fraction of its peak, and decides
whether a new sample beats it by cross-multiplying; the quotient is taken once, for the report.
**That is exact while the products fit the ``Decimal`` context, 28 significant digits** -- equity
below about 1e13 at eight decimals -- and beyond it rounds as a quotient would; within that range a
28-digit quotient resolves every difference the cross-multiplication does, so the choice buys no
resolution and only keeps a division out of the per-bar loop (``M5m-207``). The running peak starts
at the initial balance, so a run that never rises above it still measures its decline from the
start.

**Definitions the rulings leave open, chosen here (``M5m-200``):**

* *Net P&L* is the sum of ``realised`` -- the exit total less the entry quote total (the entry
  fee inside it) less the exit fee -- so it is net of BOTH fees. *Gross P&L* is the sum of
  ``exit_gross - entry_notional``, before either fee; ``gross - entry fees - exit fees = net``,
  and the record carries the residual of that identity.
* *A win* is a trade with net realised above zero; a loss, below zero; a break-even is neither.
  *Profit factor* is the sum of the wins over the absolute sum of the losses, net and gross
  separately, and is ``None`` when there is no loss.
* *Daily closing equity* is the equity after the last bar whose last instant falls in a UTC day,
  carried forward over a day with no bar; a day's return is its close over the previous close
  (the first over the initial balance), as a fraction. *Sharpe* is the mean daily return over its
  sample standard deviation (n - 1), and *Sortino* the mean over the downside deviation
  ``sqrt(sum(min(r, 0)^2) / n)``, both times ``sqrt(365)`` and both with a zero risk-free rate;
  each is ``None`` below two days or with a zero denominator.
* *Exposure* is the fraction of the run's span, from its start to its last bar, during which at
  least one position was open: the union of the closed trades' ``[entry_time, exit_time)``
  intervals and of ``[opened_at, last bar)`` for each position still open at the end, so two
  positions open at once count once and an entry bar counts from its open.
* *Holding period* is ``exit_time - entry_time`` per closed trade: the entry bar's open to the
  exit's booking instant. A position still open at the end is in the equity and the exposure and
  in no trade statistic.
* *A regime* is the one of the quarter containing the trade's entry bar; a trade whose quarter
  is partial or outside the table is ``unlabelled`` (``M5m-198``).
"""

from __future__ import annotations

import csv
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Final

from trading_bot.backtesting.regimes import RegimeTable

__all__ = [
    "DAYS_PER_YEAR",
    "DENOMINATORS",
    "UNLABELLED",
    "Z_95",
    "EquityCurve",
    "EquitySummary",
    "GroupMetrics",
    "Metrics",
    "ReturnStats",
    "TradeFacts",
    "compute_metrics",
    "daily_returns",
    "downside_deviation",
    "exposure_fraction",
    "group_metrics",
    "load_trades_csv",
    "median",
    "return_stats",
    "sharpe_ratio",
    "sortino_ratio",
    "trade_return_pct",
]

Z_95: Final = Decimal("1.96")
DAYS_PER_YEAR: Final = 365
UNLABELLED: Final = "unlabelled"

_HUNDRED: Final = Decimal(100)
_TWO: Final = Decimal(2)
_MICROSECOND: Final = timedelta(microseconds=1)
_SECOND_US: Final = Decimal(1_000_000)

#: What each ratio is a fraction (or an average) of. Written into every record.
DENOMINATORS: Final[dict[str, str]] = {
    "money": "the quote asset, as booked",
    "net_pnl": "sum of realised: exit total - entry quote total - exit fee",
    "gross_pnl": "sum of exit total - entry notional, before both fees",
    "win_rate": "closed trades",
    "average_win": "winning trades (net realised > 0)",
    "average_loss": "losing trades (net realised < 0)",
    "profit_factor_net": "absolute sum of the losing trades' net realised",
    "profit_factor_gross": "absolute sum of the losing trades' gross P&L",
    "trade_return_pct": "the trade's entry quote total, in percent",
    "max_drawdown": "the running peak of mark-to-market equity at the decline's start",
    "daily_return": "the previous day's closing equity (the first: the initial balance)",
    "sharpe_ratio": "sample sd (n - 1) of daily returns, annualised over 365 days",
    "sortino_ratio": "downside deviation over all days, annualised over 365 days",
    "exposure": "seconds from the run's start to its last bar, the span the positions are held within",
    "holding_period": "seconds from the entry bar's open to the exit's booking, per closed trade",
}


@dataclass(frozen=True)
class TradeFacts:
    """The figures of one closed round trip that the metrics read; nothing else is needed."""

    symbol: str
    entry_time: datetime
    exit_time: datetime
    entry_notional: Decimal
    entry_fee: Decimal
    entry_quote_total: Decimal
    exit_gross: Decimal
    exit_fee: Decimal
    realised: Decimal

    @property
    def gross_pnl(self) -> Decimal:
        return self.exit_gross - self.entry_notional

    @property
    def holding(self) -> timedelta:
        return self.exit_time - self.entry_time


def load_trades_csv(path: Path) -> tuple[TradeFacts, ...]:
    """Read ``trades.csv`` as ``write_run`` wrote it: exact decimal strings, ISO times."""
    with path.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    return tuple(
        TradeFacts(
            symbol=row["symbol"],
            entry_time=datetime.fromisoformat(row["entry_bar_open"]),
            exit_time=datetime.fromisoformat(row["exit_time"]),
            entry_notional=Decimal(row["entry_notional"]),
            entry_fee=Decimal(row["entry_fee"]),
            entry_quote_total=Decimal(row["entry_quote_total"]),
            exit_gross=Decimal(row["exit_gross"]),
            exit_fee=Decimal(row["exit_fee"]),
            realised=Decimal(row["realised"]),
        )
        for row in rows
    )


# --------------------------------------------------------------------------
# The per-trade return and its interval: scripts/trade_census.py, exactly (R-AK)
# --------------------------------------------------------------------------
@dataclass(frozen=True)
class ReturnStats:
    """Mean, sample standard deviation and the 95% interval of a set of returns, in percent."""

    n: int
    mean: Decimal | None
    sd: Decimal | None
    se: Decimal | None
    low: Decimal | None
    high: Decimal | None

    def to_record(self) -> dict[str, object]:
        return {
            "n": self.n,
            "mean": _text(self.mean),
            "sd": _text(self.sd),
            "se": _text(self.se),
            "low": _text(self.low),
            "high": _text(self.high),
        }


def trade_return_pct(realised: Decimal, entry_quote_total: Decimal) -> Decimal:
    """``realised / entry_quote_total * 100``, in that order, as ``trade_census`` computes it.

    The order is kept for literal parity. It does not change the value: 100 is a power of ten, so
    scaling by it commutes with a ``Decimal`` quotient's rounding (measured equal over 20,000
    random pairs), and the parity test proves the whole chain against the census instead.

    :raises ValueError: ``entry_quote_total`` is not positive.
    """
    if entry_quote_total <= 0:
        raise ValueError(f"a trade's entry quote total must be positive, got {entry_quote_total}")
    return realised / entry_quote_total * _HUNDRED


def return_stats(values: Sequence[Decimal]) -> ReturnStats:
    """Mean, sample standard deviation (n - 1) and the 95% interval of ``values``.

    The arithmetic of ``scripts/trade_census.py::return_stats``: mean = sum / n; variance =
    sum((v - mean)^2) / (n - 1); sd = sqrt(variance); se = sd / sqrt(n); interval = mean +- 1.96
    se. One value has a mean and nothing else; none has nothing.
    """
    n = len(values)
    if n == 0:
        return ReturnStats(0, None, None, None, None, None)
    mean = sum(values, Decimal(0)) / Decimal(n)
    if n == 1:
        return ReturnStats(1, mean, None, None, None, None)
    variance = sum(((value - mean) ** 2 for value in values), Decimal(0)) / Decimal(n - 1)
    sd = variance.sqrt()
    se = sd / Decimal(n).sqrt()
    return ReturnStats(n, mean, sd, se, mean - Z_95 * se, mean + Z_95 * se)


def median(values: Sequence[Decimal]) -> Decimal | None:
    """The median of ``values``, or ``None`` when there are none; even counts take the midpoint."""
    if not values:
        return None
    ordered = sorted(values)
    middle = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[middle]
    return (ordered[middle - 1] + ordered[middle]) / _TWO


# --------------------------------------------------------------------------
# The equity curve, accumulated in the loop (R-AJ)
# --------------------------------------------------------------------------
@dataclass(frozen=True)
class EquitySummary:
    """What :class:`EquityCurve` knows after the last bar; the record's ``equity`` block."""

    initial: Decimal
    final: Decimal
    start: datetime
    last_at: datetime
    samples: int
    #: The pair with the largest decline as a fraction of its peak (both equal if none declined).
    drawdown_peak: Decimal
    drawdown_trough: Decimal
    drawdown_peak_at: datetime
    drawdown_trough_at: datetime
    daily_closes: tuple[tuple[date, Decimal], ...]
    #: When each position still open after the LAST sample was opened (its entry bar's open).
    open_since: tuple[datetime, ...]
    span_seconds: Decimal

    @property
    def max_drawdown(self) -> Decimal:
        """``(peak - trough) / peak`` of the worst pair: a fraction in ``[0, 1)``."""
        return (self.drawdown_peak - self.drawdown_trough) / self.drawdown_peak

    @property
    def max_drawdown_amount(self) -> Decimal:
        return self.drawdown_peak - self.drawdown_trough

    def to_record(self) -> dict[str, object]:
        return {
            "initial": str(self.initial),
            "final": str(self.final),
            "start": self.start.isoformat(),
            "last_at": self.last_at.isoformat(),
            "samples": self.samples,
            "drawdown_peak": str(self.drawdown_peak),
            "drawdown_trough": str(self.drawdown_trough),
            "drawdown_peak_at": self.drawdown_peak_at.isoformat(),
            "drawdown_trough_at": self.drawdown_trough_at.isoformat(),
            "daily_closes": {day.isoformat(): str(close) for day, close in self.daily_closes},
            "open_since": [moment.isoformat() for moment in self.open_since],
            "span_seconds": str(self.span_seconds),
        }

    @classmethod
    def from_record(cls, record: Mapping[str, object]) -> EquitySummary:
        """The inverse of :meth:`to_record`, for recomputing a finished run's metrics."""
        closes = record["daily_closes"]
        if not isinstance(closes, Mapping):
            raise ValueError("the equity block has no daily_closes mapping")
        return cls(
            initial=Decimal(str(record["initial"])),
            final=Decimal(str(record["final"])),
            start=datetime.fromisoformat(str(record["start"])),
            last_at=datetime.fromisoformat(str(record["last_at"])),
            samples=int(str(record["samples"])),
            drawdown_peak=Decimal(str(record["drawdown_peak"])),
            drawdown_trough=Decimal(str(record["drawdown_trough"])),
            drawdown_peak_at=datetime.fromisoformat(str(record["drawdown_peak_at"])),
            drawdown_trough_at=datetime.fromisoformat(str(record["drawdown_trough_at"])),
            daily_closes=tuple(
                (date.fromisoformat(str(day)), Decimal(str(close)))
                for day, close in sorted(closes.items())
            ),
            open_since=tuple(
                datetime.fromisoformat(str(m)) for m in _as_list(record["open_since"])
            ),
            span_seconds=Decimal(str(record["span_seconds"])),
        )


class EquityCurve:
    """The loop's accumulator: one :meth:`observe` per bar of any pair, then :meth:`summary`.

    ``initial`` is the equity before the first bar, observed at ``start``. Samples must not go
    back in time, and several may share an instant (two pairs closing on one minute): the last
    of them is the one a day closes on.
    """

    def __init__(self, initial: Decimal, start: datetime) -> None:
        if initial <= 0:
            raise ValueError(f"the initial equity must be positive, got {initial}")
        self._initial = initial
        self._start = start
        self._last_at = start
        self._last_equity = initial
        self._open_since: tuple[datetime, ...] = ()
        self._peak = initial
        self._peak_at = start
        # The worst decline so far, as the pair that makes it.
        self._worst_peak = initial
        self._worst_trough = initial
        self._worst_peak_at = start
        self._worst_trough_at = start
        self._daily: dict[date, Decimal] = {}
        self._samples = 0

    def observe(self, at: datetime, equity: Decimal, *, open_since: Sequence[datetime]) -> None:
        """Record the equity after one bar, and when each position still open was opened.

        :raises ValueError: ``at`` is before the previous sample, or ``equity`` is negative.
        """
        if at < self._last_at:
            raise ValueError(
                f"a sample at {at.isoformat()} follows one at {self._last_at.isoformat()}"
            )
        if equity < 0:
            raise ValueError(f"equity cannot be negative, got {equity}")
        if equity > self._peak:
            self._peak = equity
            self._peak_at = at
        # (peak - equity) / peak beats (worst_peak - worst_trough) / worst_peak, cross-multiplied:
        if (self._peak - equity) * self._worst_peak > (
            self._worst_peak - self._worst_trough
        ) * self._peak:
            self._worst_peak = self._peak
            self._worst_trough = equity
            self._worst_peak_at = self._peak_at
            self._worst_trough_at = at
        self._daily[(at - _MICROSECOND).date()] = equity
        self._open_since = tuple(sorted(open_since))
        self._last_at = at
        self._last_equity = equity
        self._samples += 1

    def summary(self) -> EquitySummary:
        return EquitySummary(
            initial=self._initial,
            final=self._last_equity,
            start=self._start,
            last_at=self._last_at,
            samples=self._samples,
            drawdown_peak=self._worst_peak,
            drawdown_trough=self._worst_trough,
            drawdown_peak_at=self._worst_peak_at,
            drawdown_trough_at=self._worst_trough_at,
            daily_closes=tuple(sorted(self._daily.items())),
            open_since=self._open_since,
            span_seconds=_seconds(self._last_at - self._start),
        )


def _seconds(delta: timedelta) -> Decimal:
    """Exact seconds of a ``timedelta``: whole microseconds over a million."""
    return Decimal(delta // _MICROSECOND) / _SECOND_US


def _as_list(value: object) -> list[object]:
    if not isinstance(value, list):
        raise ValueError(f"expected a list, got {type(value).__name__}")
    return value


def exposure_fraction(trades: Sequence[TradeFacts], equity: EquitySummary) -> Decimal | None:
    """The share of the run's span with at least one position open, or ``None`` for no span.

    The union of every closed trade's ``[entry_time, exit_time)`` and of ``[opened_at, last
    bar)`` for each position still open at the end, clipped to the run's own span, so overlapping
    positions count once.
    """
    if equity.span_seconds == 0:
        return None
    intervals = [(t.entry_time, t.exit_time) for t in trades]
    intervals += [(opened, equity.last_at) for opened in equity.open_since]
    clipped = sorted(
        (max(begin, equity.start), min(end, equity.last_at))
        for begin, end in intervals
        if max(begin, equity.start) < min(end, equity.last_at)
    )
    covered = timedelta(0)
    current: tuple[datetime, datetime] | None = None
    for begin, end in clipped:
        if current is None:
            current = (begin, end)
        elif begin <= current[1]:
            current = (current[0], max(current[1], end))
        else:
            covered += current[1] - current[0]
            current = (begin, end)
    if current is not None:
        covered += current[1] - current[0]
    return _seconds(covered) / equity.span_seconds


# --------------------------------------------------------------------------
# Daily returns, Sharpe and Sortino (R-AJ)
# --------------------------------------------------------------------------
def daily_returns(summary: EquitySummary) -> tuple[Decimal, ...]:
    """One return per calendar day from the run's first day to its last, closes carried forward.

    A day's return is its closing equity over the previous day's, minus one; the first day's
    previous close is the initial balance. A day with no bar keeps the previous close, so its
    return is zero.
    """
    closes = dict(summary.daily_closes)
    if not closes:
        return ()
    first, last = min(closes), max(closes)
    previous = summary.initial
    out: list[Decimal] = []
    day = first
    while day <= last:
        close = closes.get(day, previous)
        out.append(close / previous - 1)
        previous = close
        day += timedelta(days=1)
    return tuple(out)


def _annualiser() -> Decimal:
    return Decimal(DAYS_PER_YEAR).sqrt()


def sharpe_ratio(returns: Sequence[Decimal]) -> Decimal | None:
    """Mean over sample sd (n - 1), times sqrt(365); ``None`` below two days or at zero sd."""
    n = len(returns)
    if n < 2:
        return None
    mean = sum(returns, Decimal(0)) / Decimal(n)
    variance = sum(((r - mean) ** 2 for r in returns), Decimal(0)) / Decimal(n - 1)
    sd = variance.sqrt()
    if sd == 0:
        return None
    return mean / sd * _annualiser()


def downside_deviation(returns: Sequence[Decimal]) -> Decimal:
    """``sqrt(sum(min(r, 0)^2) / n)`` over ALL days, with a target of zero."""
    n = len(returns)
    if n == 0:
        return Decimal(0)
    total = sum((min(r, Decimal(0)) ** 2 for r in returns), Decimal(0))
    return (total / Decimal(n)).sqrt()


def sortino_ratio(returns: Sequence[Decimal]) -> Decimal | None:
    """Mean over the downside deviation, times sqrt(365); ``None`` below two days or with no loss."""
    n = len(returns)
    if n < 2:
        return None
    deviation = downside_deviation(returns)
    if deviation == 0:
        return None
    mean = sum(returns, Decimal(0)) / Decimal(n)
    return mean / deviation * _annualiser()


# --------------------------------------------------------------------------
# The metrics of a set of trades, and their breakdowns
# --------------------------------------------------------------------------
@dataclass(frozen=True)
class GroupMetrics:
    """The trade statistics of one set of closed trades (all of them, one pair, one regime)."""

    trades: int
    wins: int
    losses: int
    net_pnl: Decimal
    gross_pnl: Decimal
    entry_fees: Decimal
    exit_fees: Decimal
    #: ``gross - entry fees - exit fees - net``: zero when the identity holds.
    fee_residual: Decimal
    win_rate: Decimal | None
    average_win: Decimal | None
    average_loss: Decimal | None
    profit_factor_net: Decimal | None
    profit_factor_gross: Decimal | None
    mean_holding_s: Decimal | None
    median_holding_s: Decimal | None
    returns: ReturnStats

    @property
    def fees_paid(self) -> Decimal:
        return self.entry_fees + self.exit_fees

    def to_record(self) -> dict[str, object]:
        return {
            "trades": self.trades,
            "wins": self.wins,
            "losses": self.losses,
            "net_pnl": str(self.net_pnl),
            "gross_pnl": str(self.gross_pnl),
            "entry_fees": str(self.entry_fees),
            "exit_fees": str(self.exit_fees),
            "fees_paid": str(self.fees_paid),
            "fee_residual": str(self.fee_residual),
            "win_rate": _text(self.win_rate),
            "average_win": _text(self.average_win),
            "average_loss": _text(self.average_loss),
            "profit_factor_net": _text(self.profit_factor_net),
            "profit_factor_gross": _text(self.profit_factor_gross),
            "mean_holding_s": _text(self.mean_holding_s),
            "median_holding_s": _text(self.median_holding_s),
            "returns_pct": self.returns.to_record(),
        }


def _profit_factor(values: Sequence[Decimal]) -> Decimal | None:
    gains = sum((v for v in values if v > 0), Decimal(0))
    losses = -sum((v for v in values if v < 0), Decimal(0))
    return gains / losses if losses != 0 else None


def group_metrics(trades: Sequence[TradeFacts]) -> GroupMetrics:
    """Every trade statistic of ``trades``; an empty set has zero counts and ``None`` ratios."""
    nets = [t.realised for t in trades]
    grosses = [t.gross_pnl for t in trades]
    wins = [v for v in nets if v > 0]
    losses = [v for v in nets if v < 0]
    count = len(trades)
    net = sum(nets, Decimal(0))
    gross = sum(grosses, Decimal(0))
    entry_fees = sum((t.entry_fee for t in trades), Decimal(0))
    exit_fees = sum((t.exit_fee for t in trades), Decimal(0))
    holding = [Decimal(t.holding // _MICROSECOND) / _SECOND_US for t in trades]
    return GroupMetrics(
        trades=count,
        wins=len(wins),
        losses=len(losses),
        net_pnl=net,
        gross_pnl=gross,
        entry_fees=entry_fees,
        exit_fees=exit_fees,
        fee_residual=gross - entry_fees - exit_fees - net,
        win_rate=Decimal(len(wins)) / Decimal(count) if count else None,
        average_win=sum(wins, Decimal(0)) / Decimal(len(wins)) if wins else None,
        average_loss=sum(losses, Decimal(0)) / Decimal(len(losses)) if losses else None,
        profit_factor_net=_profit_factor(nets),
        profit_factor_gross=_profit_factor(grosses),
        mean_holding_s=sum(holding, Decimal(0)) / Decimal(count) if count else None,
        median_holding_s=median(holding),
        returns=return_stats([trade_return_pct(t.realised, t.entry_quote_total) for t in trades]),
    )


@dataclass(frozen=True)
class Metrics:
    """Every S3 figure of one run: the whole, the equity measures and the breakdowns."""

    quote_asset: str
    initial_balance: Decimal
    final_equity: Decimal
    overall: GroupMetrics
    max_drawdown: Decimal
    max_drawdown_amount: Decimal
    sharpe: Decimal | None
    sortino: Decimal | None
    exposure: Decimal | None
    days: int
    by_pair: Mapping[str, GroupMetrics]
    #: ``None`` when no regime table was given; otherwise a bucket per regime and ``unlabelled``.
    by_regime: Mapping[str, GroupMetrics] | None

    def to_record(self) -> dict[str, object]:
        return {
            "quote_asset": self.quote_asset,
            "initial_balance": str(self.initial_balance),
            "final_equity": str(self.final_equity),
            "overall": self.overall.to_record(),
            "max_drawdown": str(self.max_drawdown),
            "max_drawdown_amount": str(self.max_drawdown_amount),
            "sharpe_ratio": _text(self.sharpe),
            "sortino_ratio": _text(self.sortino),
            "exposure": _text(self.exposure),
            "days": self.days,
            "by_pair": {symbol: group.to_record() for symbol, group in self.by_pair.items()},
            "by_regime": (
                None
                if self.by_regime is None
                else {name: group.to_record() for name, group in self.by_regime.items()}
            ),
            "denominators": dict(DENOMINATORS),
        }


def compute_metrics(
    trades: Iterable[TradeFacts],
    equity: EquitySummary,
    *,
    quote_asset: str,
    regimes: RegimeTable | None = None,
) -> Metrics:
    """The S3 metrics of a run's closed trades and its equity summary.

    ``trades`` are taken in the order given. Pairs are listed in order of first trade; regimes in
    the order rising, falling, sideways, then ``unlabelled``, each present even when empty.
    """
    ordered = tuple(trades)
    returns = daily_returns(equity)
    by_pair: dict[str, list[TradeFacts]] = {}
    for trade in ordered:
        by_pair.setdefault(trade.symbol, []).append(trade)
    by_regime: dict[str, GroupMetrics] | None = None
    if regimes is not None:
        buckets: dict[str, list[TradeFacts]] = {
            "rising": [],
            "falling": [],
            "sideways": [],
            UNLABELLED: [],
        }
        for trade in ordered:
            regime = regimes.regime_on(trade.entry_time.date())
            buckets[UNLABELLED if regime is None else regime.value].append(trade)
        by_regime = {name: group_metrics(group) for name, group in buckets.items()}
    return Metrics(
        quote_asset=quote_asset,
        initial_balance=equity.initial,
        final_equity=equity.final,
        overall=group_metrics(ordered),
        max_drawdown=equity.max_drawdown,
        max_drawdown_amount=equity.max_drawdown_amount,
        sharpe=sharpe_ratio(returns),
        sortino=sortino_ratio(returns),
        exposure=exposure_fraction(ordered, equity),
        days=len(returns),
        by_pair={symbol: group_metrics(group) for symbol, group in by_pair.items()},
        by_regime=by_regime,
    )


def _text(value: Decimal | None) -> str | None:
    return None if value is None else str(value)
