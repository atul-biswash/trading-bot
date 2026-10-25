"""The M5n estimators (N6) on synthetic fixtures, each value worked before the module existed.

The expected numbers are the ones committed in ``docs/RUN_LEDGER.md`` section 101 (P148 C2) and, for the
golden bootstrap bounds and the one accepted form of mark, section 104 (P149 C2), derived in exact
``Decimal`` arithmetic and with ``math.erf`` and a bisection, so they share no code with
``sharpe_stats``. No recorded bar is read and no backtest is run: every series below is typed in or drawn
from a seeded generator of this file.
"""

from __future__ import annotations

import math
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from itertools import pairwise
from typing import NamedTuple

import numpy as np
import pandas as pd
import pytest

from trading_bot.backtesting import sharpe_stats
from trading_bot.backtesting.metrics import EquityCurve, daily_returns, sharpe_ratio
from trading_bot.backtesting.sharpe_stats import (
    DAYS_PER_YEAR,
    EULER_MASCHERONI,
    Mark,
    buy_and_hold_marks,
    daily_series,
    deflated_sharpe,
    fee_telemetry,
    sharpe,
    skewness_kurtosis,
    stationary_bootstrap_bounds,
)
from trading_bot.backtesting.sharpe_stats import _expected_maximum_sharpe as expected_maximum_sharpe

D = Decimal
_DAY0 = datetime(2026, 1, 1, tzinfo=timezone.utc)


def _marks(*equities: str, start: datetime = _DAY0) -> list[Mark]:
    return [(start + timedelta(days=i), D(e)) for i, e in enumerate(equities)]


# F2: the exact returns 0.01, -0.01, 0.02, 0, 0.01 as equity marks (1000 * 1.01 * 0.99 * 1.02 * 1 * 1.01).
_F2_MARKS = _marks("1000", "1010.00", "999.9000", "1019.898000", "1019.898000", "1030.09698000")
_F2_RETURNS = (0.01, -0.01, 0.02, 0.0, 0.01)
_F2_DAILY = 0.5262348115842175
_F2_ANNUAL = 10.053701958827061

_SRS6 = [0.02, 0.03, 0.04, 0.05, 0.06, 0.07]


# ---- daily marking ----------------------------------------------------------------------------------
class TestDailySeries:
    def test_the_marks_become_the_exact_daily_returns(self) -> None:
        assert daily_series(_F2_MARKS) == _F2_RETURNS

    def test_the_result_is_float_one_shorter_than_the_marks(self) -> None:
        series = daily_series(_F2_MARKS)
        assert len(series) == len(_F2_MARKS) - 1
        assert all(type(r) is float for r in series)

    def test_a_day_with_no_position_and_no_change_is_a_zero_return(self) -> None:
        series = daily_series(_marks("500", "500", "500", "505"))
        assert series[:2] == (0.0, 0.0)
        assert series[2] == pytest.approx(0.01, rel=1e-12)

    @pytest.mark.parametrize("count", [0, 1])
    def test_fewer_than_two_marks_is_refused(self, count: int) -> None:
        with pytest.raises(ValueError, match="at least two marks"):
            daily_series(_marks(*["1000"] * count))

    def test_a_missing_day_is_refused_not_carried_forward(self) -> None:
        marks = _marks("1000", "1010", "1020")
        marks[2] = (marks[2][0] + timedelta(days=1), marks[2][1])
        with pytest.raises(ValueError, match="exactly one day"):
            daily_series(marks)

    def test_a_repeated_day_is_refused(self) -> None:
        marks = _marks("1000", "1010", "1020")
        marks[2] = marks[1]
        with pytest.raises(ValueError, match="exactly one day"):
            daily_series(marks)

    def test_a_backward_day_is_refused(self) -> None:
        marks = _marks("1000", "1010", "1020")
        marks[1], marks[2] = marks[2], marks[1]
        with pytest.raises(ValueError, match="exactly one day"):
            daily_series(marks)

    def test_a_mark_off_midnight_is_refused(self) -> None:
        marks: list[Mark] = [(_DAY0, D(1000)), (_DAY0 + timedelta(days=1, hours=4), D(1010))]
        with pytest.raises(ValueError, match="00:00:00 UTC"):
            daily_series(marks)

    def test_a_naive_datetime_is_refused(self) -> None:
        marks: list[Mark] = [(datetime(2026, 1, 1), D(1000)), (datetime(2026, 1, 2), D(1010))]
        with pytest.raises(ValueError, match="timezone-aware UTC"):
            daily_series(marks)

    def test_a_non_utc_offset_is_refused(self) -> None:
        zone = timezone(timedelta(hours=2))
        marks: list[Mark] = [
            (datetime(2026, 1, 1, tzinfo=zone), D(1000)),
            (datetime(2026, 1, 2, tzinfo=zone), D(1010)),
        ]
        with pytest.raises(ValueError, match="timezone-aware UTC"):
            daily_series(marks)

    @pytest.mark.parametrize("bad", ["0", "-5"])
    def test_a_non_positive_equity_is_refused(self, bad: str) -> None:
        with pytest.raises(ValueError, match="must be positive"):
            daily_series(_marks("1000", bad))

    def test_a_non_finite_equity_is_refused(self) -> None:
        with pytest.raises(ValueError, match="must be finite"):
            daily_series(_marks("1000", "NaN"))

    def test_a_float_equity_is_the_leak_the_money_rule_stops(self) -> None:
        marks: list[Mark] = [(_DAY0, D(1000)), (_DAY0 + timedelta(days=1), 1010.0)]  # type: ignore[list-item]
        with pytest.raises(TypeError, match="must be a Decimal"):
            daily_series(marks)


class _NamedMark(NamedTuple):
    at: datetime
    equity: Decimal


def _two(at: object, equity: object = D(1010)) -> list[object]:
    """Two marks: a valid first day, and a second whose instant and equity the test chooses."""
    return [(_DAY0, D(1000)), (at, equity)]


_NEXT = _DAY0 + timedelta(days=1)


class TestTheOneAcceptedFormOfMark:
    """Section 104 (P149 C2): a tuple of an exact datetime on ``timezone.utc`` at exactly 00:00:00.000000
    and an exact ``Decimal`` above zero, on consecutive days; everything else is refused."""

    def test_midnight_exactly_is_accepted(self) -> None:
        assert daily_series(_two(_NEXT)) == pytest.approx((0.01,), rel=1e-12)  # type: ignore[arg-type]

    def test_one_millisecond_before_midnight_is_refused(self) -> None:
        with pytest.raises(ValueError, match="00:00:00 UTC"):
            daily_series(_two(_NEXT - timedelta(milliseconds=1)))  # type: ignore[arg-type]

    def test_one_microsecond_after_midnight_is_refused(self) -> None:
        with pytest.raises(ValueError, match="00:00:00 UTC"):
            daily_series(_two(_NEXT + timedelta(microseconds=1)))  # type: ignore[arg-type]

    @pytest.mark.parametrize(
        "offset",
        [timedelta(seconds=1), timedelta(minutes=1), timedelta(hours=1)],
        ids=["second", "minute", "hour"],
    )
    def test_any_later_instant_in_the_day_is_refused(self, offset: timedelta) -> None:
        with pytest.raises(ValueError, match="00:00:00 UTC"):
            daily_series(_two(_NEXT + offset))  # type: ignore[arg-type]

    @pytest.mark.parametrize(
        "instant",
        [
            date(2026, 1, 2),
            pd.Timestamp("2026-01-02", tz="UTC"),
            "2026-01-02T00:00:00Z",
            1767312000,
        ],
        ids=["date", "timestamp", "str", "int"],
    )
    def test_an_instant_that_is_not_exactly_a_datetime_is_refused(self, instant: object) -> None:
        with pytest.raises(TypeError, match="must be at a datetime"):
            daily_series(_two(instant))  # type: ignore[arg-type]

    @pytest.mark.parametrize(
        "zone",
        [None, timezone(timedelta(hours=2)), timezone(timedelta(0), "Z")],
        ids=["naive", "plus-two", "named-zero-offset"],
    )
    def test_a_zone_that_is_not_timezone_utc_is_refused(self, zone: timezone | None) -> None:
        with pytest.raises(ValueError, match="timezone-aware UTC"):
            daily_series(_two(datetime(2026, 1, 2, tzinfo=zone)))  # type: ignore[arg-type]

    def test_timezone_utc_itself_is_the_accepted_zone(self) -> None:
        assert _DAY0.tzinfo is timezone.utc
        assert len(daily_series(_two(datetime(2026, 1, 2, tzinfo=timezone.utc)))) == 1  # type: ignore[arg-type]

    @pytest.mark.parametrize(
        "mark",
        [[_DAY0, D(1000)], _NamedMark(_DAY0, D(1000)), {"at": _DAY0}],
        ids=["list", "namedtuple", "dict"],
    )
    def test_an_element_that_is_not_a_plain_tuple_is_refused(self, mark: object) -> None:
        with pytest.raises(TypeError, match="must be a tuple"):
            daily_series([mark, (_NEXT, D(1010))])  # type: ignore[list-item]

    @pytest.mark.parametrize("mark", [(_DAY0,), (_DAY0, D(1000), "x")], ids=["one", "three"])
    def test_a_tuple_of_the_wrong_length_is_refused(self, mark: tuple[object, ...]) -> None:
        with pytest.raises(TypeError, match="exactly two items"):
            daily_series([mark, (_NEXT, D(1010))])  # type: ignore[list-item]

    @pytest.mark.parametrize(
        "equity",
        [1010.0, 1010, "1010", True, np.float64(1010.0)],
        ids=["float", "int", "str", "bool", "numpy-float64"],
    )
    def test_an_equity_that_is_not_exactly_a_decimal_is_refused(self, equity: object) -> None:
        with pytest.raises(TypeError, match="must be a Decimal"):
            daily_series(_two(_NEXT, equity))  # type: ignore[arg-type]

    @pytest.mark.parametrize("equity", [D("NaN"), D("Infinity"), D("-Infinity")])
    def test_a_decimal_that_is_not_finite_is_refused(self, equity: Decimal) -> None:
        with pytest.raises(ValueError, match="must be finite"):
            daily_series(_two(_NEXT, equity))  # type: ignore[arg-type]

    def test_a_refusal_names_the_mark_that_broke_the_form(self) -> None:
        marks = [(_DAY0, D(1000)), (_NEXT, D(1010)), (_NEXT + timedelta(days=1), 1020.0)]
        with pytest.raises(TypeError, match="mark 2"):
            daily_series(marks)  # type: ignore[arg-type]


class TestParityWithMetrics:
    """M5n-173's note: a reused ``metrics.py`` path must be proven equal to pre-registration section 1.

    The same marks go through ``EquityCurve`` -> ``daily_returns`` -> ``sharpe_ratio`` and through this
    module; the annualised Sharpe agrees to a relative 1e-12.
    """

    def test_the_f2_marks_give_the_same_annualised_sharpe_both_ways(self) -> None:
        curve = EquityCurve(_F2_MARKS[0][1], _F2_MARKS[0][0])
        for at, equity in _F2_MARKS[1:]:
            curve.observe(at, equity, open_since=[])
        theirs = sharpe_ratio(daily_returns(curve.summary()))
        assert theirs is not None
        ours = sharpe(daily_series(_F2_MARKS))
        assert ours == pytest.approx(float(theirs), rel=1e-12)

    def test_the_daily_returns_agree_too(self) -> None:
        curve = EquityCurve(_F2_MARKS[0][1], _F2_MARKS[0][0])
        for at, equity in _F2_MARKS[1:]:
            curve.observe(at, equity, open_since=[])
        theirs = daily_returns(curve.summary())
        ours = daily_series(_F2_MARKS)
        assert len(theirs) == len(ours)
        for a, b in zip(theirs, ours, strict=True):
            assert float(a) == pytest.approx(b, rel=1e-12, abs=1e-15)


# ---- Sharpe and moments -----------------------------------------------------------------------------
class TestSharpe:
    def test_the_known_small_series_by_hand(self) -> None:
        assert sharpe(_F2_RETURNS, annualise=False) == pytest.approx(_F2_DAILY, rel=1e-12)
        assert sharpe(_F2_RETURNS) == pytest.approx(_F2_ANNUAL, rel=1e-12)

    def test_the_annualiser_is_the_square_root_of_365(self) -> None:
        assert DAYS_PER_YEAR == 365
        assert sharpe(_F2_RETURNS) / sharpe(_F2_RETURNS, annualise=False) == pytest.approx(
            math.sqrt(365), rel=1e-12
        )

    def test_the_standard_deviation_is_the_sample_one(self) -> None:
        # n = 2: mean 0.5, sample variance 0.5 (population variance 0.25), so the daily Sharpe is
        # 0.5 / sqrt(0.5); with ddof 0 it would be 0.5 / 0.5 = 1.
        assert sharpe([0.0, 1.0], annualise=False) == pytest.approx(0.5 / math.sqrt(0.5), rel=1e-12)

    @pytest.mark.parametrize("value", [0.01, 0.0, 0.1, -0.003])
    def test_a_constant_series_refuses_rather_than_divides(self, value: float) -> None:
        with pytest.raises(ValueError, match="no variance"):
            sharpe([value] * 10)

    def test_a_constant_series_whose_float_mean_is_inexact_still_refuses(self) -> None:
        with pytest.raises(ValueError, match="no variance"):
            sharpe([0.1] * 7)

    @pytest.mark.parametrize("returns", [[], [0.01]])
    def test_fewer_than_two_returns_refuses(self, returns: list[float]) -> None:
        with pytest.raises(ValueError, match="at least two"):
            sharpe(returns)

    def test_a_non_finite_return_refuses(self) -> None:
        with pytest.raises(ValueError, match="finite"):
            sharpe([0.01, float("nan"), 0.02])

    def test_a_two_dimensional_input_refuses(self) -> None:
        with pytest.raises(ValueError, match="one-dimensional"):
            sharpe(np.zeros((2, 3)))


class TestMoments:
    def test_skewness_and_non_excess_kurtosis_by_hand(self) -> None:
        # 1, 2, 3, 4, 10: mean 4, m2 = 10, m3 = 36, m4 = 278.8.
        skew, kurt = skewness_kurtosis([1.0, 2.0, 3.0, 4.0, 10.0])
        assert skew == pytest.approx(1.1384199576606166, rel=1e-12)
        assert kurt == pytest.approx(2.788, rel=1e-12)

    def test_a_symmetric_series_has_no_skew(self) -> None:
        skew, _ = skewness_kurtosis([-2.0, -1.0, 0.0, 1.0, 2.0])
        assert skew == pytest.approx(0.0, abs=1e-12)

    def test_a_two_point_series_has_kurtosis_one(self) -> None:
        # The minimum of non-excess kurtosis: a coin flip.
        _, kurt = skewness_kurtosis([-1.0, 1.0, -1.0, 1.0])
        assert kurt == pytest.approx(1.0, rel=1e-12)

    def test_a_constant_series_refuses(self) -> None:
        with pytest.raises(ValueError, match="no variance"):
            skewness_kurtosis([0.01] * 10)


# ---- the stationary bootstrap -----------------------------------------------------------------------
def _reference_iid_sharpes(returns: np.ndarray, resamples: int, seed: int) -> np.ndarray:
    """An independent iid bootstrap: one resample per loop turn, its own generator, no shared code."""
    rng = np.random.default_rng(seed)
    t = len(returns)
    out = np.empty(resamples)
    for r in range(resamples):
        draw = returns[rng.integers(0, t, size=t)]
        out[r] = draw.mean() / draw.std(ddof=1) * math.sqrt(365)
    return out


def _runs_series() -> np.ndarray:
    """Thirty days up then thirty down, four times, with a little noise: strongly autocorrelated."""
    base = np.concatenate([np.full(30, 0.006), np.full(30, -0.005)] * 4)
    return base + np.random.default_rng(3).normal(0.0, 0.002, len(base))


def _standardised(mean: float, seed: int) -> np.ndarray:
    """Sixty seeded draws rescaled to a sample mean of exactly ``mean`` and a sample sd of 0.01, so the
    sign of the series' Sharpe is a property of the fixture and not of the draw."""
    z = np.random.default_rng(seed).normal(0.0, 1.0, 60)
    return mean + 0.01 * (z - z.mean()) / z.std(ddof=1)


_POSITIVE = _standardised(0.001, 7)
_NEGATIVE = _standardised(-0.001, 8)


class TestStationaryBootstrap:
    def test_the_same_inputs_and_seed_give_identical_bounds(self) -> None:
        a = stationary_bootstrap_bounds(_POSITIVE, p=0.05, resamples=1000, seed=20261025)
        b = stationary_bootstrap_bounds(_POSITIVE, p=0.05, resamples=1000, seed=20261025)
        assert a == b

    def test_a_different_seed_gives_different_bounds(self) -> None:
        a = stationary_bootstrap_bounds(_POSITIVE, p=0.05, resamples=1000, seed=1)
        b = stationary_bootstrap_bounds(_POSITIVE, p=0.05, resamples=1000, seed=2)
        assert a.p5 != b.p5
        assert a.mean != b.mean

    def test_the_result_does_not_depend_on_the_input_container(self) -> None:
        as_list = stationary_bootstrap_bounds(list(_POSITIVE), p=0.05, resamples=300, seed=5)
        as_array = stationary_bootstrap_bounds(_POSITIVE, p=0.05, resamples=300, seed=5)
        assert as_list == as_array

    @pytest.mark.parametrize(
        "series", [_POSITIVE, _NEGATIVE, _runs_series()], ids=["positive", "negative", "runs"]
    )
    def test_the_bounds_order_2_5th_below_5th_below_the_mean(self, series: np.ndarray) -> None:
        bounds = stationary_bootstrap_bounds(series, p=0.05, resamples=2000, seed=11)
        assert bounds.p2_5 < bounds.p5 < bounds.mean
        assert bounds.resamples == 2000

    def test_the_bootstrap_mean_has_the_sign_of_the_sample_sharpe(self) -> None:
        assert sharpe(_POSITIVE) == pytest.approx(0.1 * math.sqrt(365), rel=1e-9)
        assert sharpe(_NEGATIVE) == pytest.approx(-0.1 * math.sqrt(365), rel=1e-9)
        positive = stationary_bootstrap_bounds(_POSITIVE, p=0.05, resamples=2000, seed=11)
        negative = stationary_bootstrap_bounds(_NEGATIVE, p=0.05, resamples=2000, seed=11)
        assert positive.mean > 0.0 > negative.mean

    def test_a_vanishing_restart_probability_rotates_the_whole_series(self) -> None:
        # With p effectively 0 every resample is one circular rotation of the series, which has the
        # series' own mean and standard deviation: every resample's Sharpe is the sample Sharpe. This
        # fails if the wrap-around or the block continuation is wrong.
        bounds = stationary_bootstrap_bounds(_F2_RETURNS, p=1e-12, resamples=500, seed=3)
        for value in (bounds.p5, bounds.p2_5, bounds.mean):
            assert value == pytest.approx(_F2_ANNUAL, rel=1e-9)
        assert bounds.std == pytest.approx(0.0, abs=1e-9)

    def test_a_block_length_of_one_matches_an_independent_iid_bootstrap(self) -> None:
        ours = stationary_bootstrap_bounds(_POSITIVE, p=1.0, resamples=20000, seed=11)
        reference = _reference_iid_sharpes(_POSITIVE, 20000, 12)
        assert abs(ours.mean - float(reference.mean())) < 0.15
        assert 0.97 < ours.std / float(reference.std()) < 1.03
        assert abs(ours.p5 - float(np.percentile(reference, 5))) < 0.25
        assert abs(ours.p2_5 - float(np.percentile(reference, 2.5))) < 0.3

    def test_blocks_widen_the_distribution_of_an_autocorrelated_series(self) -> None:
        series = _runs_series()
        blocked = stationary_bootstrap_bounds(series, p=1 / 20, resamples=3000, seed=21)
        iid = stationary_bootstrap_bounds(series, p=1.0, resamples=3000, seed=21)
        assert blocked.std / iid.std > 1.5

    @pytest.mark.parametrize("p", [0.0, -0.1, 1.5, float("nan")])
    def test_a_restart_probability_outside_the_unit_interval_refuses(self, p: float) -> None:
        with pytest.raises(ValueError, match=r"p must be in \(0, 1\]"):
            stationary_bootstrap_bounds(_POSITIVE, p=p, resamples=10, seed=1)

    def test_zero_resamples_refuses(self) -> None:
        with pytest.raises(ValueError, match="at least 1"):
            stationary_bootstrap_bounds(_POSITIVE, p=0.05, resamples=0, seed=1)

    def test_a_one_return_series_refuses(self) -> None:
        with pytest.raises(ValueError, match="at least two"):
            stationary_bootstrap_bounds([0.01], p=0.05, resamples=10, seed=1)

    def test_a_constant_series_refuses(self) -> None:
        with pytest.raises(ValueError, match="no variance"):
            stationary_bootstrap_bounds([0.01] * 20, p=0.05, resamples=10, seed=1)

    def test_a_resample_with_no_variance_refuses(self) -> None:
        # Nine zeros and one 0.01: a 10-draw iid resample is all zeros with probability 0.9^10, so
        # within 250 resamples one has no variance.
        sparse = [0.0] * 9 + [0.01]
        with pytest.raises(ValueError, match="resample has no variance"):
            stationary_bootstrap_bounds(sparse, p=1.0, resamples=250, seed=1)

    def test_a_float_seed_refuses(self) -> None:
        with pytest.raises(TypeError, match="seed must be an int"):
            stationary_bootstrap_bounds(_POSITIVE, p=0.05, resamples=10, seed=1.5)  # type: ignore[arg-type]


_GOLDEN_RETURNS = [
    0.012, -0.007, 0.004, 0.009, -0.011, 0.015, 0.002, -0.004,
    0.008, 0.006, -0.009, 0.013, 0.001, -0.002, 0.010, -0.006,
    0.005, 0.011, -0.008, 0.003, 0.007, -0.001, 0.009, -0.005,
]  # fmt: skip

# Section 104 (P149 C2), derived by a plain loop over the generator's draws, exact Decimal Sharpe ratios
# and a hand-written percentile; the module's vectorised index construction is not in it.
_G1 = {
    "p5": 4.927886866519763,
    "p2_5": 4.439440781578283,
    "mean": 6.458913293099271,
    "std": 0.9760475595174631,
}
_G2 = {
    "p5": 4.838931764884872,
    "p2_5": 4.471253881083067,
    "mean": 6.439681460048089,
    "std": 0.9555063041823855,
}
# The stream a batch of 100 resamples would draw at 600 resamples.
_G3 = {
    "p5": 4.81097837508935,
    "p2_5": 4.399061271556962,
    "mean": 6.4141602214840665,
    "std": 0.9164827387133547,
}


class TestTheBootstrapStreamIsPinned:
    """``M5n-191``: the P148 survey's ``m20`` (a batch of 100) failed nothing, because every statistical test
    was indifferent to the draw stream. These values are the stream: a change to the batch, the draw order
    or the index construction moves them."""

    @staticmethod
    def _check(bounds: sharpe_stats.BootstrapBounds, expected: dict[str, float]) -> None:
        assert bounds.p5 == pytest.approx(expected["p5"], rel=1e-9)
        assert bounds.p2_5 == pytest.approx(expected["p2_5"], rel=1e-9)
        assert bounds.mean == pytest.approx(expected["mean"], rel=1e-9)
        assert bounds.std == pytest.approx(expected["std"], rel=1e-9)

    def test_g1_six_hundred_resamples_across_three_batches(self) -> None:
        bounds = stationary_bootstrap_bounds(_GOLDEN_RETURNS, p=0.05, resamples=600, seed=20261025)
        self._check(bounds, _G1)
        assert bounds.resamples == 600

    def test_g2_the_pre_registered_ten_thousand_resamples(self) -> None:
        bounds = stationary_bootstrap_bounds(
            _GOLDEN_RETURNS, p=0.05, resamples=10000, seed=20261025
        )
        self._check(bounds, _G2)

    def test_the_batch_size_is_part_of_the_value(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(sharpe_stats, "_BATCH", 100)
        bounds = stationary_bootstrap_bounds(_GOLDEN_RETURNS, p=0.05, resamples=600, seed=20261025)
        self._check(bounds, _G3)
        assert abs(bounds.p5 - _G1["p5"]) > 0.1

    def test_the_sample_sharpe_the_fixture_has(self) -> None:
        assert sharpe(_GOLDEN_RETURNS) == pytest.approx(6.413997967427307, rel=1e-12)

    def test_a_constant_resample_of_non_zero_returns_refuses(self) -> None:
        """``M5n-200``: ``np.std`` of three equal 0.1 is 1.7e-17, not zero, so a ``std == 0`` guard let
        a constant resample through with a Sharpe near 1e16. The series is three returns, so with
        ``p = 1`` a third of the resamples are 0.1 three times over."""
        with pytest.raises(ValueError, match="resample has no variance"):
            stationary_bootstrap_bounds([0.1, 0.1, 0.2], p=1.0, resamples=250, seed=1)

    def test_numpy_does_give_a_non_zero_std_for_three_equal_floats(self) -> None:
        """The fact the guard above rests on, so that a numpy that changed it would say so here."""
        assert float(np.array([[0.1, 0.1, 0.1]]).std(axis=1, ddof=1)[0]) > 0.0


# ---- the deflated Sharpe ratio ----------------------------------------------------------------------
class TestDeflatedSharpe:
    def test_one_trial_has_no_deflation_so_it_is_the_probabilistic_sharpe_ratio(self) -> None:
        # z = 0.1 * sqrt(100) / sqrt(1 + 0.5 * 0.01) = 0.9975093361076329
        value = deflated_sharpe(0.1, [0.1], 101, 0.0, 3.0, 1)
        assert value == pytest.approx(0.8407413278013518, abs=1e-12)

    def test_one_trial_ignores_what_the_single_sharpe_list_says_beyond_its_length(self) -> None:
        assert deflated_sharpe(0.1, [0.9], 101, 0.0, 3.0, 1) == pytest.approx(
            deflated_sharpe(0.1, [0.1], 101, 0.0, 3.0, 1), abs=1e-15
        )

    def test_the_expected_maximum_for_six_trials_by_hand(self) -> None:
        # V = 0.00035; PhiInv(1 - 1/6) = 0.9674215661017014; PhiInv(1 - 1/(6e)) = 1.5438425504501443.
        assert expected_maximum_sharpe(_SRS6, 6) == pytest.approx(0.024323406913442605, rel=1e-9)

    def test_the_expected_maximum_for_two_trials_by_hand(self) -> None:
        # The first inverse-normal term is PhiInv(0.5) = 0, so only the Euler-Mascheroni term remains.
        assert expected_maximum_sharpe([0.01, 0.03], 2) == pytest.approx(
            0.007350450569975128, rel=1e-9
        )

    def test_the_euler_mascheroni_constant(self) -> None:
        assert pytest.approx(0.5772156649015329, abs=1e-15) == EULER_MASCHERONI

    def test_six_trials_with_skew_and_fat_tails_by_hand(self) -> None:
        high = deflated_sharpe(0.07, _SRS6, 2300, -0.5, 6.0, 6)
        low = deflated_sharpe(0.05, _SRS6, 2300, -0.5, 6.0, 6)
        assert high == pytest.approx(0.9840796754055363, abs=1e-9)
        assert low == pytest.approx(0.8876609553599609, abs=1e-9)

    def test_two_trials_by_hand(self) -> None:
        value = deflated_sharpe(0.03, [0.01, 0.03], 500, 0.0, 3.0, 2)
        assert value == pytest.approx(0.6935150938004597, abs=1e-9)

    def test_it_is_strictly_increasing_in_the_sharpe_for_a_symmetric_case(self) -> None:
        grid = [k / 100 for k in range(21)]
        values = [deflated_sharpe(s, _SRS6, 1000, 0.0, 3.0, 6) for s in grid]
        assert all(b > a for a, b in pairwise(values))
        assert values[0] == pytest.approx(0.22100929595628976, abs=1e-9)
        assert values[-1] == pytest.approx(0.9999999807825788, abs=1e-9)

    def test_more_trials_deflate_the_same_sharpe(self) -> None:
        few = deflated_sharpe(0.06, [0.04, 0.06], 1000, 0.0, 3.0, 2)
        many = deflated_sharpe(0.06, [0.01, 0.02, 0.03, 0.04, 0.05, 0.06], 1000, 0.0, 3.0, 6)
        assert many < few

    @pytest.mark.parametrize("n", [0, -1])
    def test_a_trial_count_below_one_refuses(self, n: int) -> None:
        with pytest.raises(ValueError, match="n must be at least 1"):
            deflated_sharpe(0.1, [], 100, 0.0, 3.0, n)

    def test_a_sharpe_list_not_matching_n_refuses(self) -> None:
        with pytest.raises(ValueError, match="they are the n trials"):
            deflated_sharpe(0.07, _SRS6[:5], 2300, 0.0, 3.0, 6)

    def test_fewer_than_two_observations_refuses(self) -> None:
        with pytest.raises(ValueError, match="t must be at least 2"):
            deflated_sharpe(0.1, [0.1], 1, 0.0, 3.0, 1)

    def test_a_non_positive_variance_term_refuses(self) -> None:
        # 1 - 10 * 0.2 + (3 - 1) / 4 * 0.04 = -0.98
        with pytest.raises(ValueError, match="variance is undefined"):
            deflated_sharpe(0.2, [0.2], 100, 10.0, 3.0, 1)

    @pytest.mark.parametrize("field", ["sr", "skew", "kurt", "srs"])
    def test_a_non_finite_input_refuses(self, field: str) -> None:
        nan = float("nan")
        kwargs = {"sr": 0.1, "skew": 0.0, "kurt": 3.0, "srs": [0.1]}
        kwargs[field] = [nan] if field == "srs" else nan  # type: ignore[assignment]
        with pytest.raises(ValueError, match="finite"):
            deflated_sharpe(kwargs["sr"], kwargs["srs"], 100, kwargs["skew"], kwargs["kurt"], 1)  # type: ignore[arg-type]


# ---- fee telemetry ----------------------------------------------------------------------------------
class TestFeeTelemetry:
    def test_net_share_per_trade_and_basis_points_by_hand(self) -> None:
        result = fee_telemetry(D(500), D(50), 10, entry_notional=D(20000))
        assert result.net == D(450)
        assert result.fee_share == D("0.1")
        assert result.fees_per_trade == D(5)
        assert result.fee_bps == D(25)

    def test_the_numerators_and_denominators_are_reported_beside_each_ratio(self) -> None:
        result = fee_telemetry(D(500), D(50), 10, entry_notional=D(20000))
        assert (result.gross, result.fees, result.trades) == (D(500), D(50), 10)
        assert (result.abs_gross, result.entry_notional) == (D(500), D(20000))

    def test_the_share_is_over_the_absolute_gross(self) -> None:
        result = fee_telemetry(D(-200), D(20), 4, entry_notional=D(8000))
        assert result.net == D(-220)
        assert result.abs_gross == D(200)
        assert result.fee_share == D("0.1")

    def test_a_zero_gross_refuses(self) -> None:
        with pytest.raises(ValueError, match="gross of 0"):
            fee_telemetry(D(0), D(50), 10, entry_notional=D(20000))

    def test_zero_fees_are_a_zero_share(self) -> None:
        assert fee_telemetry(D(100), D(0), 1, entry_notional=D(1000)).fee_share == D(0)

    @pytest.mark.parametrize("trades", [0, -3])
    def test_fewer_than_one_trade_refuses(self, trades: int) -> None:
        with pytest.raises(ValueError, match="trades must be at least 1"):
            fee_telemetry(D(500), D(50), trades, entry_notional=D(20000))

    @pytest.mark.parametrize("notional", [D(0), D(-1)])
    def test_a_non_positive_notional_refuses(self, notional: Decimal) -> None:
        with pytest.raises(ValueError, match="entry_notional must be positive"):
            fee_telemetry(D(500), D(50), 10, entry_notional=notional)

    def test_negative_fees_refuse(self) -> None:
        with pytest.raises(ValueError, match="fees cannot be negative"):
            fee_telemetry(D(500), D(-1), 10, entry_notional=D(20000))

    @pytest.mark.parametrize("which", ["gross", "fees", "notional"])
    def test_a_float_figure_is_refused(self, which: str) -> None:
        args: dict[str, object] = {"gross": D(500), "fees": D(50), "notional": D(20000)}
        args[which] = 500.0
        with pytest.raises(TypeError, match="must be a Decimal"):
            fee_telemetry(
                args["gross"],  # type: ignore[arg-type]
                args["fees"],  # type: ignore[arg-type]
                10,
                entry_notional=args["notional"],  # type: ignore[arg-type]
            )

    def test_a_non_int_trade_count_is_refused(self) -> None:
        with pytest.raises(TypeError, match="trades must be an int"):
            fee_telemetry(D(500), D(50), 10.0, entry_notional=D(20000))  # type: ignore[arg-type]

    def test_a_boolean_trade_count_is_refused(self) -> None:
        with pytest.raises(TypeError, match="trades must be an int"):
            fee_telemetry(D(500), D(50), True, entry_notional=D(20000))


# ---- buy and hold -----------------------------------------------------------------------------------
class TestBuyAndHold:
    def _series(self, closes: tuple[int, ...]) -> list[Mark]:
        return [(_DAY0 + timedelta(days=i), D(c)) for i, c in enumerate(closes)]

    def test_equal_weight_marks_by_hand(self) -> None:
        marks = buy_and_hold_marks(
            self._series((100, 110, 99)), self._series((50, 50, 60)), initial=D(1000)
        )
        assert [equity for _, equity in marks] == [D(1000), D(1050), D(1095)]
        assert [at for at, _ in marks] == [_DAY0 + timedelta(days=i) for i in range(3)]

    def test_its_daily_returns_by_hand(self) -> None:
        marks = buy_and_hold_marks(
            self._series((100, 110, 99)), self._series((50, 50, 60)), initial=D(1000)
        )
        returns = daily_series(marks)
        assert returns[0] == pytest.approx(0.05, rel=1e-12)
        assert returns[1] == pytest.approx(3 / 70, rel=1e-12)

    def test_series_of_different_length_refuse(self) -> None:
        with pytest.raises(ValueError, match="equally long"):
            buy_and_hold_marks(self._series((100, 110)), self._series((50,)), initial=D(1000))

    def test_series_marked_at_different_instants_refuse(self) -> None:
        b = [(at + timedelta(days=1), c) for at, c in self._series((50, 50))]
        with pytest.raises(ValueError, match="are marked at"):
            buy_and_hold_marks(self._series((100, 110)), b, initial=D(1000))

    def test_a_non_positive_close_refuses(self) -> None:
        with pytest.raises(ValueError, match="close must be positive"):
            buy_and_hold_marks(self._series((100, 0)), self._series((50, 50)), initial=D(1000))

    def test_a_non_positive_initial_refuses(self) -> None:
        with pytest.raises(ValueError, match="initial must be positive"):
            buy_and_hold_marks(self._series((100,)), self._series((50,)), initial=D(0))

    def test_a_float_close_is_refused(self) -> None:
        a: list[Mark] = [(_DAY0, D(100)), (_DAY0 + timedelta(days=1), 110.0)]  # type: ignore[list-item]
        with pytest.raises(TypeError, match="must be a Decimal"):
            buy_and_hold_marks(a, self._series((50, 50)), initial=D(1000))
