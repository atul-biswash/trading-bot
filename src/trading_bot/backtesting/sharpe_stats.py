"""The M5n estimators (N6): daily marking, Sharpe, stationary bootstrap, deflated Sharpe, fee telemetry.

Pure: no file, no store, no clock, no network. Nothing here reads a bar or runs a backtest; every
function takes numbers and returns numbers, which is what lets it be tested on synthetic fixtures whose
values are worked by hand (``docs/RUN_LEDGER.md`` section 101) before any recorded data is touched. The
definitions are the pre-registration's (``docs/M5N_PREREGISTRATION.md``, SHA-256
``e6187480b6af7da1349ab280a6bb74f7219d4a7cded4217574e6247d5f54d45e``) and the owner's four readings of
it (charter section 21), which this module implements and does not amend:

* **Sharpe**: the mean over the sample standard deviation (``ddof`` 1) of the daily net returns, no
  risk-free rate, annualised by ``sqrt(365)``. In the deflated Sharpe ratio the Sharpe ratios, the
  skewness and the kurtosis are daily and unannualised, and the kurtosis is non-excess.
* **Stationary bootstrap** (Politis and Romano): geometric block lengths with ``p = 1/20``, circular
  wrap, the Sharpe recomputed per resample, ``numpy.random.default_rng(20261025)``. The in-sample
  "95 percent percentile lower bound" is the 5th percentile and the out-of-sample "two-sided 95 percent
  percentile lower bound" the 2.5th.
* **Deflated Sharpe ratio** (Bailey and Lopez de Prado, 2014).
* **Float64 estimators, converted from ``Decimal`` equity at one boundary**: :func:`daily_series`, where
  the quotient of two exact ``Decimal`` marks becomes a ``float``. Fee telemetry stays ``Decimal``: it is
  money, and no estimator needs it as a float.

**What it refuses, and why.** Every function raises ``ValueError`` (or ``TypeError`` for a ``float`` where
money is expected) rather than return a number it cannot stand behind: a Sharpe of a series with no
variance, a ratio over a zero gross, a deflation over a trial count that does not match the Sharpe ratios
given. ``metrics.py`` returns ``None`` for the first, which a caller can ignore; here the pre-registration's
*"must refuse, not divide"* is a raise. A missing, repeated or backward day in the marks is refused too,
where ``metrics.py`` carries a missing day forward as a zero return: carrying it forward would manufacture a
flat day the data did not have, and that lowers the standard deviation and raises the Sharpe. A mark has
**one accepted form** (``_check_mark``): a two-item ``tuple`` of an exact ``datetime`` on
``timezone.utc`` at exactly 00:00:00.000000 and an exact ``Decimal`` above zero; anything else, an ``int``
equity and a zero-offset zone that is not ``timezone.utc`` included, is refused.

**The choices the readings leave open**, fixed here and recorded in the ledger (``M5n-180``, ``M5n-185``):
skewness and kurtosis are the moment estimators about the sample mean divided by ``n``; the percentile is
numpy's linear interpolation; the bootstrap's random draws and its batch of 250 resamples are part of the
algorithm, so its result is a function of the returns, ``p``, the resample count and the seed alone.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from statistics import NormalDist
from typing import Final

import numpy as np
from numpy.typing import NDArray

__all__ = [
    "DAYS_PER_YEAR",
    "EULER_MASCHERONI",
    "BootstrapBounds",
    "FeeTelemetry",
    "Mark",
    "buy_and_hold_marks",
    "daily_series",
    "deflated_sharpe",
    "fee_telemetry",
    "sharpe",
    "skewness_kurtosis",
    "stationary_bootstrap_bounds",
]

#: One equity mark: the UTC midnight it is taken at and the equity, cash plus open positions marked.
Mark = tuple[datetime, Decimal]

DAYS_PER_YEAR: Final = 365
EULER_MASCHERONI: Final = 0.5772156649015329
_ANNUALISER: Final = math.sqrt(DAYS_PER_YEAR)
_DAY: Final = timedelta(days=1)
_BASIS_POINTS: Final = Decimal(10000)
#: Resamples drawn per batch. It is part of the algorithm, not a tuning knob: the draws of a batch are
#: made in a fixed order, so changing the batch would change the stream and with it every result.
_BATCH: Final = 250


# --------------------------------------------------------------------------
# Daily marking
# --------------------------------------------------------------------------
def _require_decimal(name: str, value: object) -> Decimal:
    """``value`` as a finite ``Decimal``; a ``float`` is the leak the money rule exists to stop."""
    if isinstance(value, bool) or not isinstance(value, (Decimal, int)):
        raise TypeError(f"{name} must be a Decimal, got {type(value).__name__}")
    number = Decimal(value)
    if not number.is_finite():
        raise ValueError(f"{name} must be finite, got {number}")
    return number


def _check_mark(index: int, mark: object) -> tuple[datetime, Decimal]:
    """The one accepted form of a mark, or a refusal (``M5n-192``).

    A ``tuple`` of exactly two items, ``(at, equity)``, with ``type(at) is datetime`` (a subclass such as
    ``pandas.Timestamp`` is another form), ``at.tzinfo is timezone.utc`` (a zero-offset zone that is some
    other object is another form), ``at`` exactly 00:00:00.000000, and ``type(equity) is Decimal``, finite
    and above zero. Every check is on the exact type, because each wider type is a way for a figure to
    arrive that this module did not mean to take: an ``int`` or ``float`` equity, a naive or shifted
    clock, an instant a moment off midnight.
    """
    if type(mark) is not tuple:
        raise TypeError(
            f"mark {index} must be a tuple (datetime, Decimal), got {type(mark).__name__}"
        )
    if len(mark) != 2:
        raise TypeError(f"mark {index} must have exactly two items, got {len(mark)}")
    at, equity = mark
    if type(at) is not datetime:
        raise TypeError(f"mark {index} must be at a datetime, got {type(at).__name__}")
    if at.tzinfo is not timezone.utc:
        raise ValueError(
            f"mark {index} at {at!r} is not timezone-aware UTC (datetime.timezone.utc)"
        )
    if (at.hour, at.minute, at.second, at.microsecond) != (0, 0, 0, 0):
        raise ValueError(f"mark {index} at {at.isoformat()} is not at 00:00:00 UTC")
    if type(equity) is not Decimal:
        raise TypeError(
            f"the equity of mark {index} must be a Decimal, got {type(equity).__name__}"
        )
    if not equity.is_finite():
        raise ValueError(f"the equity of mark {index} must be finite, got {equity}")
    if equity <= 0:
        raise ValueError(f"the equity of mark {index} must be positive, got {equity}")
    return at, equity


def daily_series(marks: Sequence[Mark]) -> tuple[float, ...]:
    """The daily net returns of equity marks taken at consecutive UTC midnights.

    One return per day after the first mark: ``equity / previous equity - 1``, computed on the exact
    ``Decimal`` marks and converted to ``float`` only then (the one ``Decimal`` to ``float`` boundary of
    this module). A day on which equity did not move is a return of exactly ``0.0``. Each mark must be of
    the one form :func:`_check_mark` describes.

    :raises ValueError: fewer than two marks; a mark that is naive, not on ``timezone.utc`` or not at
        00:00:00.000000; a day that is missing, repeated or out of order; an equity that is not finite or
        not positive.
    :raises TypeError: a mark that is not a two-item ``tuple``; an instant that is not exactly a
        ``datetime``; an equity that is not exactly a ``Decimal`` (a ``float`` or an ``int`` included).
    """
    if len(marks) < 2:
        raise ValueError(f"at least two marks are needed for one daily return, got {len(marks)}")
    returns: list[float] = []
    previous_at: datetime | None = None
    previous_equity = Decimal(0)
    for index, mark in enumerate(marks):
        at, equity = _check_mark(index, mark)
        if previous_at is not None:
            if at - previous_at != _DAY:
                raise ValueError(
                    f"mark {index} at {at.isoformat()} does not follow {previous_at.isoformat()} "
                    "by exactly one day; a missing, repeated or backward day is refused"
                )
            returns.append(float(equity / previous_equity - 1))
        previous_at, previous_equity = at, equity
    return tuple(returns)


def buy_and_hold_marks(
    a: Sequence[Mark], b: Sequence[Mark], *, initial: Decimal
) -> tuple[Mark, ...]:
    """Equity marks of an equal-weight buy-and-hold of two closes series (the pre-registration's context).

    Half of ``initial`` buys each asset at the first price of its series and is held: no fee and no
    rebalance, because it is context and never a criterion. The runner makes that first price the open of
    the first day of the span, so no bar before the span is needed (``M5n-202``). The two series must be
    marked at the same instants.

    :raises ValueError: the series differ in length or in instants, or hold fewer than one mark, or a
        close or ``initial`` is not positive.
    :raises TypeError: a value that is not a ``Decimal``.
    """
    if len(a) != len(b) or not a:
        raise ValueError(
            f"the two series must be non-empty and equally long, got {len(a)} and {len(b)}"
        )
    capital = _require_decimal("initial", initial)
    if capital <= 0:
        raise ValueError(f"initial must be positive, got {capital}")
    first_a = _require_decimal("the first close of the first series", a[0][1])
    first_b = _require_decimal("the first close of the second series", b[0][1])
    if first_a <= 0 or first_b <= 0:
        raise ValueError("a close must be positive")
    half = capital / 2
    out: list[Mark] = []
    for (at_a, close_a), (at_b, close_b) in zip(a, b, strict=True):
        if at_a != at_b:
            raise ValueError(f"the series are marked at {at_a.isoformat()} and {at_b.isoformat()}")
        value_a = _require_decimal("a close", close_a)
        value_b = _require_decimal("a close", close_b)
        if value_a <= 0 or value_b <= 0:
            raise ValueError("a close must be positive")
        out.append((at_a, half * (value_a / first_a) + half * (value_b / first_b)))
    return tuple(out)


# --------------------------------------------------------------------------
# Sharpe and moments
# --------------------------------------------------------------------------
def _as_array(name: str, returns: Sequence[float] | NDArray[np.float64]) -> NDArray[np.float64]:
    values = np.asarray(returns, dtype=np.float64)
    if values.ndim != 1:
        raise ValueError(f"{name} must be one-dimensional, got shape {values.shape}")
    if not bool(np.isfinite(values).all()):
        raise ValueError(f"{name} must be finite")
    return values


def _require_spread(name: str, values: NDArray[np.float64]) -> None:
    """At least two values that are not all equal. Decided by ``min == max`` and not by a computed
    variance, because the mean of identical floats need not be exact and a rounding residue would
    otherwise be divided by."""
    if len(values) < 2:
        raise ValueError(f"{name} needs at least two returns, got {len(values)}")
    if float(values.min()) == float(values.max()):
        raise ValueError(f"{name} has no variance: every return is {float(values[0])!r}")


def sharpe(returns: Sequence[float] | NDArray[np.float64], *, annualise: bool = True) -> float:
    """Mean over the sample standard deviation (``ddof`` 1) of ``returns``; times ``sqrt(365)`` when
    annualised. No risk-free rate.

    :raises ValueError: fewer than two returns, or every return equal (a zero standard deviation).
    """
    values = _as_array("the returns", returns)
    _require_spread("the returns", values)
    n = len(values)
    mean = math.fsum(values.tolist()) / n
    variance = math.fsum((v - mean) ** 2 for v in values.tolist()) / (n - 1)
    ratio = mean / math.sqrt(variance)
    return ratio * _ANNUALISER if annualise else ratio


def skewness_kurtosis(returns: Sequence[float] | NDArray[np.float64]) -> tuple[float, float]:
    """Skewness ``m3 / m2^1.5`` and NON-EXCESS kurtosis ``m4 / m2^2``, from the moments about the sample
    mean divided by ``n`` (reading (1); the estimator is this module's choice, ``M5n-180``).

    :raises ValueError: fewer than two returns, or every return equal.
    """
    values = _as_array("the returns", returns)
    _require_spread("the returns", values)
    n = len(values)
    mean = math.fsum(values.tolist()) / n
    deviations = [v - mean for v in values.tolist()]
    m2 = math.fsum(d**2 for d in deviations) / n
    m3 = math.fsum(d**3 for d in deviations) / n
    m4 = math.fsum(d**4 for d in deviations) / n
    return m3 / m2**1.5, m4 / m2**2


# --------------------------------------------------------------------------
# The stationary bootstrap
# --------------------------------------------------------------------------
@dataclass(frozen=True)
class BootstrapBounds:
    """The percentiles of the bootstrap distribution of the annualised Sharpe ratio.

    ``p5`` is the in-sample lower bound and ``p2_5`` the out-of-sample one (reading (2)); ``mean`` is the
    distribution's mean, reported so that the ordering ``p2_5 <= p5 <= mean`` can be checked, and ``std``
    its population standard deviation (``ddof`` 0), which is what shows a block length at work (``M5n-187``).
    """

    p5: float
    p2_5: float
    mean: float
    std: float
    resamples: int


def stationary_bootstrap_bounds(
    returns: Sequence[float] | NDArray[np.float64], *, p: float, resamples: int, seed: int
) -> BootstrapBounds:
    """Politis-Romano stationary bootstrap of the annualised Sharpe ratio of ``returns``.

    Each resample has the length of ``returns``. Its first index is uniform on ``[0, T)``; at every later
    position a new uniform index is drawn with probability ``p`` and otherwise the previous index plus one
    is taken, wrapping circularly, so block lengths are geometric with mean ``1 / p``. The draws are
    ``rng.integers`` for the candidate starts and ``rng.random`` for the restart decisions, for a batch of
    250 resamples at a time, from ``numpy.random.default_rng(seed)``; the annualised Sharpe is recomputed
    on every resample. ``p = 1`` is the ordinary bootstrap.

    :raises ValueError: ``p`` outside ``(0, 1]``, ``resamples < 1``, fewer than two returns, no variance in
        ``returns``, or a resample with no variance (every draw the same return).
    """
    if isinstance(seed, bool) or not isinstance(seed, int):
        raise TypeError(f"seed must be an int, got {type(seed).__name__}")
    if not 0.0 < p <= 1.0:
        raise ValueError(f"p must be in (0, 1], got {p!r}")
    if resamples < 1:
        raise ValueError(f"resamples must be at least 1, got {resamples}")
    values = _as_array("the returns", returns)
    _require_spread("the returns", values)
    t = len(values)
    positions = np.arange(t)
    rng = np.random.default_rng(seed)
    sharpes = np.empty(resamples, dtype=np.float64)
    done = 0
    while done < resamples:
        batch = min(_BATCH, resamples - done)
        starts = rng.integers(0, t, size=(batch, t))
        restart = rng.random((batch, t)) < p
        # Position 0 always opens a block: ``last`` is 0 there whether or not the draw restarts, because
        # the position index 0 is also what ``np.where`` returns for a non-restart (``M5n-190``).
        last = np.maximum.accumulate(np.where(restart, positions, 0), axis=1)
        base = np.take_along_axis(starts, last, axis=1)
        index = (base + (positions - last)) % t
        sample = values[index]
        # Constant means ``min == max``, not a zero ``std``: numpy's standard deviation of three equal floats
        # is not always zero (``np.std([0.1] * 3, ddof=1)`` is 1.7e-17), and a Sharpe over that is 1e16
        # (``M5n-200``).
        if bool((sample.min(axis=1) == sample.max(axis=1)).any()):
            raise ValueError(
                "a bootstrap resample has no variance, so its Sharpe ratio is undefined"
            )
        deviation = sample.std(axis=1, ddof=1)
        sharpes[done : done + batch] = sample.mean(axis=1) / deviation * _ANNUALISER
        done += batch
    p5, p2_5 = np.percentile(sharpes, [5.0, 2.5])
    return BootstrapBounds(
        p5=float(p5),
        p2_5=float(p2_5),
        mean=float(sharpes.mean()),
        std=float(sharpes.std()),
        resamples=resamples,
    )


# --------------------------------------------------------------------------
# The deflated Sharpe ratio
# --------------------------------------------------------------------------
def _expected_maximum_sharpe(srs: Sequence[float], n: int) -> float:
    """``SR0 = sqrt(V) ((1 - gamma) PhiInv(1 - 1/N) + gamma PhiInv(1 - 1/(N e)))`` for ``n >= 2``, with
    ``V`` the sample variance (``ddof`` 1) of the ``n`` trials' Sharpe ratios."""
    mean = math.fsum(srs) / len(srs)
    variance = math.fsum((s - mean) ** 2 for s in srs) / (len(srs) - 1)
    normal = NormalDist()
    return math.sqrt(variance) * (
        (1.0 - EULER_MASCHERONI) * normal.inv_cdf(1.0 - 1.0 / n)
        + EULER_MASCHERONI * normal.inv_cdf(1.0 - 1.0 / (n * math.e))
    )


def deflated_sharpe(
    sr: float, srs: Sequence[float], t: int, skew: float, kurt: float, n: int
) -> float:
    """The deflated Sharpe ratio: the probability that the candidate's true Sharpe exceeds the expected
    maximum of ``n`` trials, ``Phi((SR - SR0) sqrt(T - 1) / sqrt(1 - g3 SR + (g4 - 1) / 4 SR^2))``.

    ``sr`` is the candidate's DAILY, unannualised Sharpe; ``srs`` the ``n`` trials' daily Sharpe ratios
    (the candidate's own among them); ``t`` the number of daily returns; ``skew`` and ``kurt`` the
    candidate's daily skewness and NON-EXCESS kurtosis. For ``n = 1`` there is no deflation, ``SR0`` is
    zero by definition (the inverse normal of 0 is undefined) and the result is the probabilistic Sharpe
    ratio.

    :raises ValueError: ``n < 1``, ``len(srs) != n``, ``t < 2``, a non-finite input, or a non-positive
        ``1 - g3 SR + (g4 - 1) / 4 SR^2`` under the square root.
    """
    if n < 1:
        raise ValueError(f"n must be at least 1, got {n}")
    if len(srs) != n:
        raise ValueError(f"n is {n} but {len(srs)} Sharpe ratios were given; they are the n trials")
    if t < 2:
        raise ValueError(f"t must be at least 2, got {t}")
    for name, value in (("sr", sr), ("skew", skew), ("kurt", kurt), *[("srs", s) for s in srs]):
        if not math.isfinite(value):
            raise ValueError(f"{name} must be finite, got {value!r}")
    benchmark = 0.0 if n == 1 else _expected_maximum_sharpe(srs, n)
    variance_term = 1.0 - skew * sr + (kurt - 1.0) / 4.0 * sr * sr
    if variance_term <= 0.0:
        raise ValueError(
            f"1 - g3 SR + (g4 - 1) / 4 SR^2 is {variance_term!r}; the Sharpe's variance is undefined"
        )
    z = (sr - benchmark) * math.sqrt(t - 1) / math.sqrt(variance_term)
    return NormalDist().cdf(z)


# --------------------------------------------------------------------------
# Fee telemetry
# --------------------------------------------------------------------------
@dataclass(frozen=True)
class FeeTelemetry:
    """The fee figures of a set of trades, each ratio with its numerator and denominator beside it.

    All ``Decimal``, in the quote asset. ``fee_share`` is ``fees / abs_gross``; ``fee_bps`` is ``fees`` over
    ``entry_notional`` in basis points, the aggregate (a ratio of sums) of the charter's per-trade
    ``fee_bps_per_trade``, which needs rows this function is not given.
    """

    gross: Decimal
    fees: Decimal
    trades: int
    entry_notional: Decimal
    net: Decimal
    abs_gross: Decimal
    fee_share: Decimal
    fees_per_trade: Decimal
    fee_bps: Decimal


def fee_telemetry(
    gross: Decimal, fees: Decimal, trades: int, *, entry_notional: Decimal
) -> FeeTelemetry:
    """Net, fee share, fees per trade and fee basis points of ``trades`` closed round trips.

    :raises ValueError: ``gross`` is 0 (the share is undefined), ``trades < 1``, ``entry_notional`` is not
        positive, or ``fees`` is negative.
    :raises TypeError: a figure that is not a ``Decimal`` (a ``float`` included), or ``trades`` that is not
        an ``int``.
    """
    gross_amount = _require_decimal("gross", gross)
    fee_amount = _require_decimal("fees", fees)
    notional = _require_decimal("entry_notional", entry_notional)
    if isinstance(trades, bool) or not isinstance(trades, int):
        raise TypeError(f"trades must be an int, got {type(trades).__name__}")
    if trades < 1:
        raise ValueError(f"trades must be at least 1, got {trades}")
    if fee_amount < 0:
        raise ValueError(f"fees cannot be negative, got {fee_amount}")
    if notional <= 0:
        raise ValueError(f"entry_notional must be positive, got {notional}")
    if gross_amount == 0:
        raise ValueError("the fee share is undefined over a gross of 0")
    absolute = abs(gross_amount)
    return FeeTelemetry(
        gross=gross_amount,
        fees=fee_amount,
        trades=trades,
        entry_notional=notional,
        net=gross_amount - fee_amount,
        abs_gross=absolute,
        fee_share=fee_amount / absolute,
        fees_per_trade=fee_amount / trades,
        fee_bps=fee_amount / notional * _BASIS_POINTS,
    )
