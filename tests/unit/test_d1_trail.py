"""The D1 trail as a pure function (N4a, R-EA): every expected figure is worked by hand.

The bars are literals. Minute 0 is 2023-01-01T00:00Z and the entry fill is 20 seconds into it. A
trigger is ``peak x (1 - delta / 10000)`` and an exit is that trigger, or a gapped open, times
``1 - slippage / 100``. The fixtures A to K are the ones section 86 of ``docs/RUN_LEDGER.md``
predicted before the module was written. R-EB (P144) changed one reading: the entry minute's high
counts toward the peak, so fixture B2's expected exit is the trigger of its own high, and the tests
of ``TestTheEntryMinute`` that follow it were written red before the module changed.
"""

from __future__ import annotations

import ast
import io
import tokenize
from collections.abc import Iterator
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

import pytest
from pydantic import ValidationError

from trading_bot.backtesting import d1_trail
from trading_bot.backtesting.d1_trail import (
    TrailOutcome,
    TrailStatus,
    resolve_trail,
    trigger_price,
)
from trading_bot.core.models import Candle

T0 = datetime(2023, 1, 1, tzinfo=timezone.utc)
ENTRY = T0 + timedelta(seconds=20)
Row = tuple[int, str, str, str, str]


def at(minute: int) -> datetime:
    return T0 + timedelta(minutes=minute)


def bar(row: Row) -> Candle:
    minute, open_, high, low, close = row
    return Candle(
        symbol="BTCUSDT",
        timeframe="1m",
        open_time=at(minute),
        close_time=at(minute + 1) - timedelta(milliseconds=1),
        open=open_,
        high=high,
        low=low,
        close=close,
        volume="1",
    )


def walk(
    fill: str,
    delta_bps: int,
    slippage: str,
    *rows: Row,
    entry_time: datetime = ENTRY,
) -> TrailOutcome:
    return resolve_trail(
        entry_time=entry_time,
        entry_price=Decimal(fill),
        delta_bps=delta_bps,
        stop_slippage_percent=Decimal(slippage),
        bars=[bar(row) for row in rows],
    )


FLAT: Row = (0, "100", "100", "100", "100")

A_BARS: tuple[Row, ...] = (
    (0, "100", "101", "100", "101"),
    (1, "101", "103", "101", "103"),
    (2, "103", "105", "103", "105"),
    (3, "105", "108", "105", "108"),
    (4, "108", "108", "100", "101"),
    (5, "101", "200", "100", "150"),
)
D_BARS: tuple[Row, ...] = (
    (0, "100", "104", "100", "104"),
    (1, "104", "106", "104", "106"),
    (2, "99", "100", "98", "98"),
)


class TestTheTriggerPrice:
    def test_the_faqs_own_example(self) -> None:
        assert trigger_price(Decimal("45500"), 700) == Decimal("42315")

    def test_the_two_bounds_of_the_clamp(self) -> None:
        assert trigger_price(Decimal("100"), 10) == Decimal("99.9")
        assert trigger_price(Decimal("100"), 2000) == Decimal("80")

    def test_it_is_exact_to_the_last_digit(self) -> None:
        assert trigger_price(Decimal("1000.5"), 10) == Decimal("999.4995")

    def test_a_delta_that_cannot_make_a_trigger_is_refused(self) -> None:
        for bad in (0, -1, 10000, 20000):
            with pytest.raises(ValueError, match="delta_bps must be between 1 and 9999"):
                trigger_price(Decimal("100"), bad)

    def test_a_delta_that_is_not_an_int_is_refused(self) -> None:
        for bad in (True, 500.0, "500", Decimal(500)):
            with pytest.raises(TypeError, match="delta_bps must be an int"):
                trigger_price(Decimal("100"), bad)  # type: ignore[arg-type]

    def test_a_peak_that_is_a_float_or_not_positive_is_refused(self) -> None:
        with pytest.raises(TypeError, match="peak must be a Decimal"):
            trigger_price(100.0, 500)  # type: ignore[arg-type]
        for bad in (Decimal(0), Decimal(-1)):
            with pytest.raises(ValueError, match="peak must be positive"):
                trigger_price(bad, 500)
        with pytest.raises(ValueError, match="peak must be finite"):
            trigger_price(Decimal("NaN"), 500)


class TestAMonotoneRiseThenAFall:
    def test_it_exits_through_the_trigger_of_the_last_peak(self) -> None:
        out = walk("100", 500, "1.00", *A_BARS)
        assert out.status is TrailStatus.EXITED
        assert out.exit_minute == at(4)
        assert out.exit_price == Decimal("101.5740")
        assert out.gap is False
        assert out.peak == Decimal("108")

    def test_the_bars_after_the_exit_change_nothing(self) -> None:
        with_tail = walk("100", 500, "1.00", *A_BARS)
        without_tail = walk("100", 500, "1.00", *A_BARS[:5])
        assert with_tail == without_tail

    def test_the_walk_does_not_advance_the_iterator_past_the_exit(self) -> None:
        bars: Iterator[Candle] = iter([bar(row) for row in A_BARS])
        out = resolve_trail(
            entry_time=ENTRY,
            entry_price=Decimal("100"),
            delta_bps=500,
            stop_slippage_percent=Decimal("1.00"),
            bars=bars,
        )
        assert out.exit_minute == at(4)
        assert next(bars).open_time == at(5)


class TestTheEntryMinute:
    def test_a_fall_in_the_entry_minute_exits_at_the_trigger_from_the_fill(self) -> None:
        out = walk("100", 500, "1.20", (0, "100", "100", "94", "95"))
        assert out.exit_minute == at(0)
        assert out.exit_price == Decimal("93.860")
        assert out.gap is False
        assert out.peak == Decimal("100")

    def test_an_entry_minute_that_opens_below_the_trigger_is_not_a_gap(self) -> None:
        out = walk("100", 500, "1.20", (0, "90", "101", "90", "100"))
        assert out.exit_price == Decimal("94.7986")
        assert out.gap is False
        assert out.peak == Decimal("101")

    def test_the_entry_minutes_high_counts_toward_the_peak(self) -> None:
        out = walk("100", 500, "1.00", (0, "100", "110", "100", "105"))
        assert out.status is TrailStatus.EXITED
        assert out.exit_minute == at(0)
        assert out.exit_price == Decimal("103.4550")
        assert out.gap is False
        assert out.peak == Decimal("110")

    def test_an_entry_minute_low_exactly_at_the_trigger_triggers(self) -> None:
        out = walk("100", 500, "1.00", (0, "100", "100", "95", "96"))
        assert out.status is TrailStatus.EXITED
        assert out.exit_minute == at(0)
        assert out.exit_price == Decimal("94.0500")
        assert out.gap is False
        assert out.peak == Decimal("100")

    def test_an_entry_minute_low_exactly_at_the_trigger_of_its_own_high_triggers(self) -> None:
        out = walk("100", 500, "1.00", (0, "100", "110", "104.5", "105"))
        assert out.status is TrailStatus.EXITED
        assert out.exit_price == Decimal("103.4550")
        assert out.peak == Decimal("110")

    def test_an_entry_minute_low_one_cent_above_the_trigger_leaves_the_position_open(self) -> None:
        flat = walk("100", 500, "1.00", (0, "100", "100", "95.01", "96"))
        assert flat.status is TrailStatus.OPEN
        assert flat.peak == Decimal("100")
        high = walk("100", 500, "1.00", (0, "100", "110", "104.51", "105"))
        assert high.status is TrailStatus.OPEN
        assert high.peak == Decimal("110")

    def test_an_entry_time_on_the_minute_boundary_is_inside_that_minute(self) -> None:
        out = walk("100", 500, "1.00", FLAT, entry_time=at(0))
        assert out.status is TrailStatus.OPEN


class TestHighAndLowInOneMinute:
    def test_a_new_peak_and_a_low_below_its_trigger_exits(self) -> None:
        out = walk("100", 500, "1.00", FLAT, (1, "100", "110", "99", "105"))
        assert out.exit_minute == at(1)
        assert out.exit_price == Decimal("103.4550")
        assert out.gap is False
        assert out.peak == Decimal("110")

    def test_the_same_low_does_not_exit_while_it_is_above_the_old_trigger_alone(self) -> None:
        out = walk("100", 500, "1.00", FLAT, (1, "100", "100", "99", "99.5"))
        assert out.status is TrailStatus.OPEN
        assert out.peak == Decimal("100")


class TestAGapOpenBelowTheTrigger:
    def test_the_fill_is_the_open_less_the_slippage_and_the_flag_is_set(self) -> None:
        out = walk("100", 500, "1.20", *D_BARS)
        assert out.exit_minute == at(2)
        assert out.exit_price == Decimal("97.812")
        assert out.gap is True
        assert out.peak == Decimal("106")

    def test_the_gap_bars_high_does_not_enter_the_peak(self) -> None:
        out = walk("100", 500, "1.20", *D_BARS[:2], (2, "99", "120", "98", "110"))
        assert out.exit_price == Decimal("97.812")
        assert out.gap is True
        assert out.peak == Decimal("106")


class TestTheTriggerExactly:
    def test_a_low_that_touches_the_trigger_exits_and_is_not_a_gap(self) -> None:
        out = walk("100", 500, "1.00", FLAT, (1, "100", "100", "95", "96"))
        assert out.exit_minute == at(1)
        assert out.exit_price == Decimal("94.0500")
        assert out.gap is False
        assert out.peak == Decimal("100")

    def test_an_open_exactly_at_the_trigger_is_a_gap_at_the_same_price(self) -> None:
        out = walk("100", 500, "1.00", FLAT, (1, "95", "96", "95", "95"))
        assert out.exit_minute == at(1)
        assert out.exit_price == Decimal("94.0500")
        assert out.gap is True
        assert out.peak == Decimal("100")

    def test_a_low_one_cent_above_the_trigger_leaves_the_position_open(self) -> None:
        out = walk("100", 500, "1.00", FLAT, (1, "100", "100", "95.01", "96"))
        assert out.status is TrailStatus.OPEN
        assert out.exit_minute is None
        assert out.exit_price is None
        assert out.gap is False
        assert out.peak == Decimal("100")


class TestTheTwoBoundsOfTheClamp:
    def test_a_delta_of_ten_basis_points(self) -> None:
        out = walk(
            "1000",
            10,
            "1.00",
            (0, "1000", "1000", "999.5", "999.8"),
            (1, "999.8", "1000.5", "999", "999.2"),
        )
        assert out.exit_minute == at(1)
        assert out.exit_price == Decimal("989.504505")
        assert out.gap is False
        assert out.peak == Decimal("1000.5")

    def test_a_delta_of_two_thousand_basis_points(self) -> None:
        out = walk(
            "50",
            2000,
            "1.20",
            (0, "50", "52", "49", "51"),
            (1, "51", "60", "51", "59"),
            (2, "59", "59", "47", "48"),
        )
        assert out.exit_minute == at(2)
        assert out.exit_price == Decimal("47.424")
        assert out.gap is False
        assert out.peak == Decimal("60")


class TestAPathThatEndsOpen:
    def test_the_peak_is_the_highest_high_from_the_entry_minute_on(self) -> None:
        out = walk(
            "100", 500, "1.00", (0, "100", "101", "100", "101"), (1, "101", "102", "100.5", "101")
        )
        assert out.status is TrailStatus.OPEN
        assert out.peak == Decimal("102")

    def test_an_empty_path_is_open_at_the_fill_price(self) -> None:
        out = walk("100", 500, "1.00")
        assert out.status is TrailStatus.OPEN
        assert out.peak == Decimal("100")
        assert out.gap is False

    def test_the_peak_never_moves_down(self) -> None:
        out = walk(
            "100",
            500,
            "1.00",
            FLAT,
            (1, "100", "104", "100", "104"),
            (2, "104", "102", "101", "101"),
        )
        assert out.status is TrailStatus.OPEN
        assert out.peak == Decimal("104")


class TestTheFaqsOwnExample:
    def test_a_700_bips_trail_from_45500_exits_at_42315(self) -> None:
        out = walk(
            "45500",
            700,
            "0",
            (0, "45500", "45500", "45500", "45500"),
            (1, "45500", "45500", "42315", "42400"),
        )
        assert out.exit_minute == at(1)
        assert out.exit_price == Decimal("42315")
        assert out.gap is False
        assert out.peak == Decimal("45500")


class TestRefusals:
    def test_a_float_among_the_money_figures_is_a_type_error(self) -> None:
        bars = [bar(FLAT)]
        with pytest.raises(TypeError, match="entry_price must be a Decimal"):
            resolve_trail(
                entry_time=ENTRY,
                entry_price=100.0,  # type: ignore[arg-type]
                delta_bps=500,
                stop_slippage_percent=Decimal("1"),
                bars=bars,
            )
        with pytest.raises(TypeError, match="stop_slippage_percent must be a Decimal"):
            resolve_trail(
                entry_time=ENTRY,
                entry_price=Decimal("100"),
                delta_bps=500,
                stop_slippage_percent=1.2,  # type: ignore[arg-type]
                bars=bars,
            )

    @pytest.mark.parametrize("bad", ["0", "-1", "NaN", "Infinity"])
    def test_an_entry_price_that_is_not_positive_and_finite_is_refused(self, bad: str) -> None:
        with pytest.raises(ValueError, match="entry_price must be"):
            walk(bad, 500, "1", FLAT)

    @pytest.mark.parametrize("bad", ["-0.01", "100", "150", "NaN"])
    def test_a_slippage_outside_zero_to_below_one_hundred_is_refused(self, bad: str) -> None:
        with pytest.raises(ValueError, match="stop_slippage_percent must be"):
            walk("100", 500, bad, FLAT)

    @pytest.mark.parametrize("bad", [0, -5, 10000])
    def test_a_delta_out_of_range_is_refused(self, bad: int) -> None:
        with pytest.raises(ValueError, match="delta_bps must be between"):
            walk("100", bad, "1", FLAT)

    def test_a_delta_that_is_a_bool_is_refused(self) -> None:
        with pytest.raises(TypeError, match="delta_bps must be an int"):
            walk("100", True, "1", FLAT)

    def test_a_naive_entry_time_is_refused(self) -> None:
        with pytest.raises(ValueError, match="entry_time must be timezone-aware"):
            walk("100", 500, "1", FLAT, entry_time=datetime(2023, 1, 1, 0, 0, 20))

    def test_an_entry_time_outside_the_first_bars_minute_is_refused(self) -> None:
        for moment in (at(0) - timedelta(seconds=1), at(1)):
            with pytest.raises(ValueError, match="not inside the first bar's minute"):
                walk("100", 500, "1", FLAT, entry_time=moment)

    def test_a_bar_that_is_not_a_one_minute_bar_is_refused(self) -> None:
        daily = Candle(
            symbol="BTCUSDT",
            timeframe="1d",
            open_time=T0,
            close_time=T0 + timedelta(days=1) - timedelta(milliseconds=1),
            open="100",
            high="100",
            low="100",
            close="100",
            volume="1",
        )
        with pytest.raises(ValueError, match="walks 1m bars"):
            resolve_trail(
                entry_time=ENTRY,
                entry_price=Decimal("100"),
                delta_bps=500,
                stop_slippage_percent=Decimal("1"),
                bars=[daily],
            )

    def test_a_repeated_minute_is_refused(self) -> None:
        with pytest.raises(ValueError, match="must strictly increase"):
            walk("100", 500, "1", FLAT, FLAT)

    def test_a_minute_out_of_order_is_refused(self) -> None:
        with pytest.raises(ValueError, match="must strictly increase"):
            walk(
                "100",
                500,
                "1",
                FLAT,
                (2, "100", "100", "100", "100"),
                (1, "100", "100", "100", "100"),
            )

    def test_a_bar_with_a_naive_open_time_is_refused(self) -> None:
        naive = Candle.model_construct(
            symbol="BTCUSDT",
            timeframe="1m",
            open_time=datetime(2023, 1, 1),
            close_time=datetime(2023, 1, 1, 0, 0, 59),
            open=Decimal(100),
            high=Decimal(100),
            low=Decimal(100),
            close=Decimal(100),
            volume=Decimal(1),
            is_closed=True,
        )
        with pytest.raises(ValueError, match="open time must be timezone-aware"):
            resolve_trail(
                entry_time=ENTRY,
                entry_price=Decimal("100"),
                delta_bps=500,
                stop_slippage_percent=Decimal("1"),
                bars=[naive],
            )

    def test_a_missing_minute_is_not_detected_here(self) -> None:
        out = walk("100", 500, "1.00", FLAT, (5, "100", "100", "99", "99.5"))
        assert out.status is TrailStatus.OPEN


class TestTheOutcomeShape:
    def test_an_exited_outcome_needs_its_minute_and_price(self) -> None:
        with pytest.raises(ValidationError):
            TrailOutcome(
                status=TrailStatus.EXITED,
                exit_minute=None,
                exit_price=None,
                gap=False,
                peak=Decimal(1),
            )

    def test_an_open_outcome_carries_neither_and_no_gap(self) -> None:
        with pytest.raises(ValidationError):
            TrailOutcome(
                status=TrailStatus.OPEN,
                exit_minute=at(1),
                exit_price=Decimal(1),
                gap=False,
                peak=Decimal(1),
            )
        with pytest.raises(ValidationError):
            TrailOutcome(
                status=TrailStatus.OPEN,
                exit_minute=None,
                exit_price=None,
                gap=True,
                peak=Decimal(1),
            )

    def test_a_float_price_is_refused_by_the_money_guard(self) -> None:
        with pytest.raises(ValidationError):
            TrailOutcome(
                status=TrailStatus.OPEN,
                exit_minute=None,
                exit_price=None,
                gap=False,
                peak=1.5,  # type: ignore[arg-type]
            )

    def test_the_outcome_is_frozen(self) -> None:
        out = walk("100", 500, "1")
        with pytest.raises(ValidationError):
            out.peak = Decimal(2)  # type: ignore[misc]

    def test_every_figure_is_a_decimal(self) -> None:
        out = walk("100", 500, "1.00", *A_BARS)
        assert type(out.exit_price) is Decimal
        assert type(out.peak) is Decimal


class TestThePurity:
    def test_the_module_imports_no_clock_no_store_and_no_io(self) -> None:
        tree = ast.parse(Path(d1_trail.__file__).read_text(encoding="utf-8"))
        imported: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported |= {alias.name for alias in node.names}
            elif isinstance(node, ast.ImportFrom) and node.module is not None:
                imported.add(node.module)
        assert imported == {
            "__future__",
            "collections.abc",
            "datetime",
            "decimal",
            "enum",
            "pydantic",
            "trading_bot.core.models",
        }

    def test_it_reads_no_wall_clock(self) -> None:
        source = Path(d1_trail.__file__).read_text(encoding="utf-8")
        for word in (".now(", ".utcnow(", "time.time", "sleep", "open(", "read_text", "write_text"):
            assert word not in source, word

    def test_it_has_no_comment(self) -> None:
        source = Path(d1_trail.__file__).read_text(encoding="utf-8")
        kinds = [token.type for token in tokenize.generate_tokens(io.StringIO(source).readline)]
        assert tokenize.COMMENT not in kinds

    def test_the_same_arguments_give_the_same_answer(self) -> None:
        assert walk("100", 500, "1.20", *D_BARS) == walk("100", 500, "1.20", *D_BARS)
