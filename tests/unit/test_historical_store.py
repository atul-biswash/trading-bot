"""The read side of the archive store: serving bars, describing coverage, verifying.

Every store here is built through ``write_month`` into ``tmp_path`` with daily bars, so a
month is a few rows and a gap is a missing month. Expected values are literals or
``datetime`` objects written in the test, never computed by the code under test.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

import pytest

from trading_bot.core.models import Candle
from trading_bot.data.historical import (
    MANIFEST_NAME,
    ArchiveFormatError,
    Coverage,
    Gap,
    HistoricalStore,
    Row,
    StoredFileError,
    month_file,
    write_month,
)

SYMBOL = "BTCUSDT"
INTERVAL = "1d"
DAY_MS = 86_400_000
UTC = timezone.utc
EPOCH = datetime(1970, 1, 1, tzinfo=UTC)


def at(year: int, month: int, day: int, hour: int = 0) -> datetime:
    return datetime(year, month, day, hour, tzinfo=UTC)


def ms(moment: datetime) -> int:
    return (moment - EPOCH) // timedelta(milliseconds=1)


def day_row(year: int, month: int, day: int) -> Row:
    """One daily bar whose prices say which day it is, with the venue's trailing zeros."""
    opened = ms(at(year, month, day))
    return Row(
        open_time_ms=opened,
        open=f"{100 + day}.50000000",
        high=f"{200 + day}.00000000",
        low=f"{50 + day}.25000000",
        close=f"{150 + day}.75000000",
        volume=f"{day}.12300000",
        close_time_ms=opened + DAY_MS - 1,
    )


def store_month(root: Path, month: str, days: list[int]) -> None:
    year, number = (int(part) for part in month.split("-"))
    write_month(
        root,
        SYMBOL,
        INTERVAL,
        month,
        [day_row(year, number, day) for day in days],
        source_url=f"https://example.invalid/{month}.zip",
        zip_sha256="0" * 64,
    )


def served(store: HistoricalStore, start: datetime, end: datetime) -> list[Candle]:
    return list(store.candles(SYMBOL, INTERVAL, start, end))


def opens(candles: list[Candle]) -> list[datetime]:
    return [candle.open_time for candle in candles]


@pytest.fixture
def two_months(tmp_path: Path) -> HistoricalStore:
    """2024-11 days 29 and 30, then 2024-12 days 1 and 2."""
    store_month(tmp_path, "2024-11", [29, 30])
    store_month(tmp_path, "2024-12", [1, 2])
    return HistoricalStore(tmp_path)


class TestCandles:
    def test_the_range_is_start_inclusive_and_end_exclusive_across_a_month_border(
        self, two_months: HistoricalStore
    ) -> None:
        candles = served(two_months, at(2024, 11, 30), at(2024, 12, 2))
        assert opens(candles) == [at(2024, 11, 30), at(2024, 12, 1)]

    def test_the_whole_store_comes_back_in_time_order(self, two_months: HistoricalStore) -> None:
        candles = served(two_months, at(2024, 1, 1), at(2025, 1, 1))
        assert opens(candles) == [
            at(2024, 11, 29),
            at(2024, 11, 30),
            at(2024, 12, 1),
            at(2024, 12, 2),
        ]

    def test_a_bar_that_opened_before_start_is_not_served(
        self, two_months: HistoricalStore
    ) -> None:
        candles = served(two_months, at(2024, 12, 1, 12), at(2025, 1, 1))
        assert opens(candles) == [at(2024, 12, 2)]

    def test_an_end_inside_a_bar_still_excludes_a_bar_opening_after_it(
        self, two_months: HistoricalStore
    ) -> None:
        candles = served(two_months, at(2024, 11, 29), at(2024, 11, 30, 12))
        assert opens(candles) == [at(2024, 11, 29), at(2024, 11, 30)]

    def test_an_empty_or_reversed_range_serves_nothing(self, two_months: HistoricalStore) -> None:
        assert served(two_months, at(2024, 12, 1), at(2024, 12, 1)) == []
        assert served(two_months, at(2024, 12, 2), at(2024, 12, 1)) == []

    def test_a_range_outside_the_store_serves_nothing(self, two_months: HistoricalStore) -> None:
        assert served(two_months, at(2020, 1, 1), at(2021, 1, 1)) == []
        assert served(two_months, at(2030, 1, 1), at(2031, 1, 1)) == []

    def test_a_candle_carries_the_stored_strings_exactly_and_the_times_aware(
        self, two_months: HistoricalStore
    ) -> None:
        candle = served(two_months, at(2024, 12, 1), at(2024, 12, 2))[0]
        assert candle == Candle(
            symbol="BTCUSDT",
            timeframe="1d",
            open_time=at(2024, 12, 1),
            close_time=at(2024, 12, 1) + timedelta(days=1) - timedelta(milliseconds=1),
            open=Decimal("101.50000000"),
            high=Decimal("201.00000000"),
            low=Decimal("51.25000000"),
            close=Decimal("151.75000000"),
            volume=Decimal("1.12300000"),
            is_closed=True,
        )
        assert candle.open_time.utcoffset() == timedelta(0)
        assert candle.close_time.utcoffset() == timedelta(0)

    def test_the_venues_trailing_zeros_survive_into_the_decimal(
        self, two_months: HistoricalStore
    ) -> None:
        candle = served(two_months, at(2024, 12, 1), at(2024, 12, 2))[0]
        assert str(candle.open) == "101.50000000"
        assert str(candle.volume) == "1.12300000"

    def test_a_month_missing_from_the_manifest_serves_nothing_and_is_not_filled(
        self, tmp_path: Path
    ) -> None:
        store_month(tmp_path, "2024-11", [30])
        store_month(tmp_path, "2025-01", [1])
        candles = served(HistoricalStore(tmp_path), at(2024, 1, 1), at(2026, 1, 1))
        assert opens(candles) == [at(2024, 11, 30), at(2025, 1, 1)]

    def test_an_empty_store_serves_nothing(self, tmp_path: Path) -> None:
        assert served(HistoricalStore(tmp_path), at(2024, 1, 1), at(2025, 1, 1)) == []

    def test_the_root_is_the_directory_given(self, tmp_path: Path) -> None:
        assert HistoricalStore(tmp_path).root == tmp_path


class TestCandlesRefuseAtTheCall:
    """The arguments are checked when ``candles`` is called, not when it is consumed."""

    def test_a_naive_start_is_refused_without_consuming(self, tmp_path: Path) -> None:
        with pytest.raises(ValueError, match="start"):
            HistoricalStore(tmp_path).candles(
                SYMBOL, INTERVAL, datetime(2024, 1, 1), at(2025, 1, 1)
            )

    def test_a_naive_end_is_refused_without_consuming(self, tmp_path: Path) -> None:
        with pytest.raises(ValueError, match="end"):
            HistoricalStore(tmp_path).candles(
                SYMBOL, INTERVAL, at(2024, 1, 1), datetime(2025, 1, 1)
            )

    def test_a_bad_symbol_is_refused_without_consuming(self, tmp_path: Path) -> None:
        with pytest.raises(ArchiveFormatError):
            HistoricalStore(tmp_path).candles("../etc", INTERVAL, at(2024, 1, 1), at(2025, 1, 1))

    def test_an_interval_that_is_not_stored_is_refused_without_consuming(
        self, tmp_path: Path
    ) -> None:
        with pytest.raises(ArchiveFormatError):
            HistoricalStore(tmp_path).candles(SYMBOL, "3m", at(2024, 1, 1), at(2025, 1, 1))

    def test_an_unreadable_manifest_is_refused_without_consuming(self, tmp_path: Path) -> None:
        store_month(tmp_path, "2024-12", [1])
        manifest = tmp_path / SYMBOL / INTERVAL / MANIFEST_NAME
        manifest.write_text("this is not json\n", encoding="utf-8", newline="")
        with pytest.raises(StoredFileError):
            HistoricalStore(tmp_path).candles(SYMBOL, INTERVAL, at(2024, 1, 1), at(2025, 1, 1))


class TestCandlesReadAsTheyAreConsumed:
    def test_a_month_is_read_only_when_the_iterator_reaches_it(self, tmp_path: Path) -> None:
        store_month(tmp_path, "2024-11", [30])
        store_month(tmp_path, "2024-12", [1])
        store = HistoricalStore(tmp_path)
        iterator = store.candles(SYMBOL, INTERVAL, at(2024, 11, 1), at(2025, 1, 1))
        month_file(tmp_path, SYMBOL, INTERVAL, "2024-12").unlink()
        assert next(iterator).open_time == at(2024, 11, 30)
        with pytest.raises(StoredFileError, match="2024-12"):
            next(iterator)

    def test_a_month_outside_the_range_is_never_read(self, tmp_path: Path) -> None:
        store_month(tmp_path, "2024-11", [30])
        store_month(tmp_path, "2024-12", [1])
        month_file(tmp_path, SYMBOL, INTERVAL, "2024-11").unlink()
        candles = served(HistoricalStore(tmp_path), at(2024, 12, 1), at(2025, 1, 1))
        assert opens(candles) == [at(2024, 12, 1)]

    def test_reading_stops_at_end_and_does_not_open_later_months(self, tmp_path: Path) -> None:
        store_month(tmp_path, "2024-11", [30])
        store_month(tmp_path, "2024-12", [1])
        month_file(tmp_path, SYMBOL, INTERVAL, "2024-12").unlink()
        candles = served(HistoricalStore(tmp_path), at(2024, 11, 1), at(2024, 12, 1))
        assert opens(candles) == [at(2024, 11, 30)]


class TestCandlesRefuseWhatNoLongerMatches:
    def test_a_file_changed_after_it_was_stored_is_refused_not_served(self, tmp_path: Path) -> None:
        store_month(tmp_path, "2024-12", [1, 2])
        path = month_file(tmp_path, SYMBOL, INTERVAL, "2024-12")
        path.write_bytes(path.read_bytes().replace(b"101.50000000", b"999.50000000"))
        with pytest.raises(StoredFileError, match="hash"):
            served(HistoricalStore(tmp_path), at(2024, 12, 1), at(2025, 1, 1))

    def test_a_file_that_is_gone_is_refused_not_skipped(self, tmp_path: Path) -> None:
        store_month(tmp_path, "2024-12", [1, 2])
        month_file(tmp_path, SYMBOL, INTERVAL, "2024-12").unlink()
        with pytest.raises(StoredFileError, match="cannot be read"):
            served(HistoricalStore(tmp_path), at(2024, 12, 1), at(2025, 1, 1))

    def test_a_refused_file_serves_none_of_its_own_bars(self, tmp_path: Path) -> None:
        store_month(tmp_path, "2024-12", [1, 2])
        path = month_file(tmp_path, SYMBOL, INTERVAL, "2024-12")
        path.write_bytes(path.read_bytes() + b"\n")
        iterator = HistoricalStore(tmp_path).candles(
            SYMBOL, INTERVAL, at(2024, 1, 1), at(2025, 1, 1)
        )
        with pytest.raises(StoredFileError):
            next(iterator)


class TestCoverage:
    def test_a_missing_month_is_one_gap_and_never_filled(self, tmp_path: Path) -> None:
        store_month(tmp_path, "2024-11", [29, 30])
        store_month(tmp_path, "2025-01", [1, 2])
        coverage = HistoricalStore(tmp_path).coverage(SYMBOL, INTERVAL)
        assert coverage.months == ("2024-11", "2025-01")
        assert coverage.bars == 4
        assert coverage.first_open_time_ms == ms(at(2024, 11, 29))
        assert coverage.last_open_time_ms == ms(at(2025, 1, 2))
        assert coverage.gaps == (Gap(ms(at(2024, 12, 1)), ms(at(2025, 1, 1)), 31),)
        assert coverage.missing == 31
        assert coverage.grid_bars is None
        assert coverage.problems == ()

    def test_a_gap_inside_a_month_is_found_too(self, tmp_path: Path) -> None:
        store_month(tmp_path, "2024-12", [1, 2, 5])
        coverage = HistoricalStore(tmp_path).coverage(SYMBOL, INTERVAL)
        assert coverage.gaps == (Gap(ms(at(2024, 12, 3)), ms(at(2024, 12, 5)), 2),)
        assert coverage.missing == 2

    def test_a_contiguous_series_has_no_gaps(self, two_months: HistoricalStore) -> None:
        coverage = two_months.coverage(SYMBOL, INTERVAL)
        assert coverage.bars == 4
        assert coverage.gaps == ()
        assert coverage.missing == 0

    def test_until_makes_a_missing_last_month_a_gap_and_the_grid_adds_up(
        self, tmp_path: Path
    ) -> None:
        store_month(tmp_path, "2024-11", [29, 30])
        store_month(tmp_path, "2025-01", [1, 2])
        coverage = HistoricalStore(tmp_path).coverage(SYMBOL, INTERVAL, until=at(2025, 1, 4))
        assert coverage.gaps == (
            Gap(ms(at(2024, 12, 1)), ms(at(2025, 1, 1)), 31),
            Gap(ms(at(2025, 1, 3)), ms(at(2025, 1, 4)), 1),
        )
        assert coverage.missing == 32
        assert coverage.grid_bars == 36
        assert coverage.bars + coverage.missing == coverage.grid_bars

    def test_until_right_after_the_last_bar_adds_no_trailing_gap(
        self, two_months: HistoricalStore
    ) -> None:
        coverage = two_months.coverage(SYMBOL, INTERVAL, until=at(2024, 12, 3))
        assert coverage.gaps == ()
        assert coverage.grid_bars == 4
        assert coverage.bars + coverage.missing == coverage.grid_bars

    def test_until_before_the_last_bar_is_refused(self, two_months: HistoricalStore) -> None:
        with pytest.raises(ValueError, match="beyond"):
            two_months.coverage(SYMBOL, INTERVAL, until=at(2024, 12, 2))

    def test_a_naive_until_is_refused(self, two_months: HistoricalStore) -> None:
        with pytest.raises(ValueError, match="until"):
            two_months.coverage(SYMBOL, INTERVAL, until=datetime(2025, 1, 1))

    def test_an_empty_store_has_no_bars_no_gaps_and_no_grid(self, tmp_path: Path) -> None:
        store = HistoricalStore(tmp_path)
        expected = Coverage(
            symbol=SYMBOL,
            interval=INTERVAL,
            months=(),
            bars=0,
            first_open_time_ms=None,
            last_open_time_ms=None,
            gaps=(),
            missing=0,
            grid_bars=None,
            problems=(),
        )
        assert store.coverage(SYMBOL, INTERVAL) == expected
        assert store.coverage(SYMBOL, INTERVAL, until=at(2025, 1, 1)) == expected

    def test_a_month_that_fails_verification_is_not_counted_and_is_reported(
        self, tmp_path: Path
    ) -> None:
        store_month(tmp_path, "2024-11", [30])
        store_month(tmp_path, "2024-12", [1, 2])
        path = month_file(tmp_path, SYMBOL, INTERVAL, "2024-12")
        path.write_bytes(path.read_bytes().replace(b"101.50000000", b"999.50000000"))
        coverage = HistoricalStore(tmp_path).coverage(SYMBOL, INTERVAL, until=at(2025, 1, 1))
        assert coverage.months == ("2024-11",)
        assert coverage.bars == 1
        assert [(p.kind, p.month) for p in coverage.problems] == [("hash_mismatch", "2024-12")]
        assert coverage.gaps == (Gap(ms(at(2024, 12, 1)), ms(at(2025, 1, 1)), 31),)
        assert coverage.bars + coverage.missing == coverage.grid_bars

    def test_a_bad_symbol_or_interval_is_refused(self, tmp_path: Path) -> None:
        store = HistoricalStore(tmp_path)
        with pytest.raises(ArchiveFormatError):
            store.coverage("btc usdt", INTERVAL)
        with pytest.raises(ArchiveFormatError):
            store.coverage(SYMBOL, "2h")


class TestVerify:
    def test_a_clean_series_has_no_problems(self, two_months: HistoricalStore) -> None:
        assert two_months.verify(SYMBOL, INTERVAL) == ()

    def test_a_changed_file_and_a_stray_file_are_both_reported(self, tmp_path: Path) -> None:
        store_month(tmp_path, "2024-12", [1])
        path = month_file(tmp_path, SYMBOL, INTERVAL, "2024-12")
        path.write_bytes(path.read_bytes().replace(b"101.50000000", b"999.50000000"))
        (path.parent / "BTCUSDT-1d-2020-01.csv").write_bytes(b"x")
        kinds = sorted(
            problem.kind for problem in HistoricalStore(tmp_path).verify(SYMBOL, INTERVAL)
        )
        assert kinds == ["hash_mismatch", "unlisted_file"]

    def test_a_series_never_stored_has_no_problems(self, tmp_path: Path) -> None:
        assert HistoricalStore(tmp_path).verify("ETHUSDT", "1h") == ()

    def test_an_unreadable_manifest_line_is_reported_not_raised(self, tmp_path: Path) -> None:
        store_month(tmp_path, "2024-12", [1])
        manifest = tmp_path / SYMBOL / INTERVAL / MANIFEST_NAME
        lines = manifest.read_text(encoding="utf-8").splitlines()
        lines.append(json.dumps({"month": "nonsense"}))
        manifest.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="")
        kinds = [problem.kind for problem in HistoricalStore(tmp_path).verify(SYMBOL, INTERVAL)]
        assert kinds == ["bad_manifest_line"]
