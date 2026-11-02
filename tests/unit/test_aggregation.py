"""Aggregating 1m bars into 4h and 1d bars: the grid, the values, the gaps and the store.

Every stream is built in the test from literal prices, and every expected value is a literal
or is computed here from the same literals, never by the code under test. The store tests
write real month files into ``tmp_path`` with ``write_month``, so a month-file boundary is a
real one.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

import pytest
from pydantic import ValidationError

from trading_bot.core.models import Candle
from trading_bot.data.aggregation import (
    AGGREGATED_TIMEFRAMES,
    AggregatedBar,
    AggregationError,
    aggregate_bars,
    aggregate_from_store,
)
from trading_bot.data.historical import (
    HistoricalStore,
    Row,
    StoredFileError,
    month_file,
    write_month,
)

UTC = timezone.utc
EPOCH = datetime(1970, 1, 1, tzinfo=UTC)
MINUTE = timedelta(minutes=1)
LAST_MS = timedelta(milliseconds=59_999)
SOURCE = {"source_url": "https://example.invalid/m.zip", "zip_sha256": "0" * 64}


def at(year: int, month: int, day: int, hour: int = 0, minute: int = 0) -> datetime:
    return datetime(year, month, day, hour, minute, tzinfo=UTC)


def ms(moment: datetime) -> int:
    return (moment - EPOCH) // timedelta(milliseconds=1)


def candle(
    opened: datetime,
    *,
    o: str = "100",
    h: str = "110",
    low: str = "90",
    c: str = "105",
    v: str = "1",
    symbol: str = "BTCUSDT",
    timeframe: str = "1m",
) -> Candle:
    return Candle(
        symbol=symbol,
        timeframe=timeframe,
        open_time=opened,
        close_time=opened + LAST_MS,
        open=o,
        high=h,
        low=low,
        close=c,
        volume=v,
    )


def run(
    start: datetime,
    count: int,
    *,
    symbol: str = "BTCUSDT",
    skip: frozenset[int] = frozenset(),
) -> list[Candle]:
    """``count`` consecutive minutes from ``start``; minute i opens 1000 + i and holds volume 2."""
    return [
        candle(
            start + i * MINUTE,
            o=str(1000 + i),
            h=str(2000 + i),
            low=str(500 + i),
            c=str(1500 + i),
            v="2",
            symbol=symbol,
        )
        for i in range(count)
        if i not in skip
    ]


def bars(candles: list[Candle], timeframe: str) -> list[AggregatedBar]:
    return list(aggregate_bars(candles, timeframe))


def opens(found: list[AggregatedBar]) -> list[datetime]:
    return [bar.open_time for bar in found]


class TestTheGrid:
    @pytest.mark.parametrize(
        ("hour", "minute", "bucket_hour"),
        [
            (0, 0, 0),
            (3, 59, 0),
            (4, 0, 4),
            (7, 59, 4),
            (8, 0, 8),
            (11, 59, 8),
            (12, 0, 12),
            (15, 59, 12),
            (16, 0, 16),
            (19, 59, 16),
            (20, 0, 20),
            (23, 59, 20),
        ],
    )
    def test_a_4h_bucket_opens_on_00_04_08_12_16_or_20_utc(
        self, hour: int, minute: int, bucket_hour: int
    ) -> None:
        found = bars([candle(at(2023, 6, 15, hour, minute))], "4h")
        assert opens(found) == [at(2023, 6, 15, bucket_hour)]

    def test_the_minute_before_midnight_and_the_midnight_minute_are_two_1d_buckets(self) -> None:
        found = bars([candle(at(2023, 6, 15, 23, 59)), candle(at(2023, 6, 16, 0, 0))], "1d")
        assert opens(found) == [at(2023, 6, 15), at(2023, 6, 16)]

    def test_a_1d_bucket_opens_at_00_utc_whatever_the_minute_inside_it(self) -> None:
        found = bars([candle(at(2020, 2, 29, 13, 37))], "1d")
        assert opens(found) == [at(2020, 2, 29)]

    @pytest.mark.parametrize(
        ("timeframe", "closes"),
        [
            ("4h", at(2023, 6, 15, 3, 59) + timedelta(seconds=59, milliseconds=999)),
            ("1d", at(2023, 6, 15, 23, 59) + timedelta(seconds=59, milliseconds=999)),
        ],
    )
    def test_close_time_is_the_last_millisecond_of_the_bucket(
        self, timeframe: str, closes: datetime
    ) -> None:
        (only,) = bars([candle(at(2023, 6, 15, 1))], timeframe)
        assert only.close_time == closes

    def test_only_4h_and_1d_are_aggregated(self) -> None:
        assert AGGREGATED_TIMEFRAMES == ("4h", "1d")


class TestTheValues:
    def test_a_full_4h_bucket_has_the_first_open_the_last_close_the_extremes_and_the_sum(
        self,
    ) -> None:
        (only,) = bars(run(at(2023, 6, 15, 4), 240), "4h")
        assert only.open == Decimal("1000")
        assert only.close == Decimal("1500") + 239
        assert only.high == Decimal("2000") + 239
        assert only.low == Decimal("500")
        assert only.volume == Decimal("480")
        assert only.minutes_present == 240
        assert only.minutes_missing == 0
        assert only.complete is True

    def test_open_and_close_are_the_first_and_last_minute_not_the_extremes(self) -> None:
        stream = [
            candle(at(2023, 6, 15, 4, 0), o="50", h="60", low="10", c="55"),
            candle(at(2023, 6, 15, 4, 1), o="55", h="999", low="1", c="70"),
            candle(at(2023, 6, 15, 4, 2), o="70", h="80", low="65", c="75"),
        ]
        (only,) = bars(stream, "4h")
        assert (only.open, only.high, only.low, only.close) == (
            Decimal("50"),
            Decimal("999"),
            Decimal("1"),
            Decimal("75"),
        )

    def test_a_volume_is_an_exact_decimal_sum(self) -> None:
        stream = [
            candle(at(2023, 6, 15, 4, 0), v="0.10000000"),
            candle(at(2023, 6, 15, 4, 1), v="0.20000000"),
        ]
        (only,) = bars(stream, "4h")
        assert only.volume == Decimal("0.3")
        assert type(only.volume) is Decimal

    def test_every_figure_is_a_decimal(self) -> None:
        (only,) = bars([candle(at(2023, 6, 15, 4))], "4h")
        figures = (only.open, only.high, only.low, only.close, only.volume)
        assert all(type(figure) is Decimal for figure in figures)

    def test_a_day_equals_the_fold_of_its_six_4h_buckets(self) -> None:
        stream = run(at(2023, 6, 15), 1440)
        (day,) = bars(stream, "1d")
        sixths = bars(stream, "4h")
        assert len(sixths) == 6
        assert day.open == sixths[0].open
        assert day.close == sixths[-1].close
        assert day.high == max(bar.high for bar in sixths)
        assert day.low == min(bar.low for bar in sixths)
        assert day.volume == sum((bar.volume for bar in sixths), Decimal(0))
        assert day.minutes_present == 1440
        assert day.complete is True

    def test_empty_input_gives_no_bars(self) -> None:
        assert bars([], "4h") == []
        assert bars([], "1d") == []


class TestGapsAreReportedAndNeverFilled:
    def test_one_missing_interior_minute_is_counted_and_the_bucket_is_incomplete(self) -> None:
        (only,) = bars(run(at(2023, 6, 15, 4), 240, skip=frozenset({100})), "4h")
        assert only.minutes_present == 239
        assert only.minutes_missing == 1
        assert only.complete is False
        assert only.volume == Decimal("478")
        assert only.open == Decimal("1000")
        assert only.close == Decimal("1500") + 239

    def test_a_missing_first_minute_makes_the_second_minute_the_open(self) -> None:
        (only,) = bars(run(at(2023, 6, 15, 4), 240, skip=frozenset({0})), "4h")
        assert only.open == Decimal("1001")
        assert only.minutes_missing == 1

    def test_a_missing_last_minute_makes_the_one_before_the_close(self) -> None:
        (only,) = bars(run(at(2023, 6, 15, 4), 240, skip=frozenset({239})), "4h")
        assert only.close == Decimal("1500") + 238
        assert only.high == Decimal("2000") + 238
        assert only.minutes_missing == 1

    def test_the_missing_minute_that_held_the_extreme_is_not_replaced(self) -> None:
        (only,) = bars(run(at(2023, 6, 15, 4), 240, skip=frozenset({0})), "4h")
        assert only.low == Decimal("501")

    def test_a_stream_that_starts_mid_day_has_a_first_day_missing_the_earlier_minutes(self) -> None:
        (only,) = bars(run(at(2017, 8, 17, 4), 1200), "1d")
        assert only.open_time == at(2017, 8, 17)
        assert only.minutes_present == 1200
        assert only.minutes_missing == 240
        assert only.complete is False

    def test_a_bucket_with_no_stored_minute_is_not_emitted_and_nothing_stands_in_for_it(
        self,
    ) -> None:
        stream = run(at(2023, 6, 15, 4), 240) + run(at(2023, 6, 15, 12), 240)
        found = bars(stream, "4h")
        assert opens(found) == [at(2023, 6, 15, 4), at(2023, 6, 15, 12)]
        assert all(bar.complete for bar in found)

    def test_the_bar_after_a_gap_starts_from_its_own_first_minute(self) -> None:
        stream = run(at(2023, 6, 15, 0), 240) + run(at(2023, 6, 15, 8), 240)
        first, second = bars(stream, "4h")
        assert first.close == Decimal("1500") + 239
        assert second.open == Decimal("1000")

    def test_a_whole_missing_day_inside_a_run_of_days_gives_no_bar_for_it(self) -> None:
        stream = run(at(2023, 6, 15), 1440) + run(at(2023, 6, 17), 1440)
        assert opens(bars(stream, "1d")) == [at(2023, 6, 15), at(2023, 6, 17)]


class TestBothPairs:
    @pytest.mark.parametrize("symbol", ["BTCUSDT", "ETHUSDT"])
    @pytest.mark.parametrize("timeframe", ["4h", "1d"])
    def test_the_symbol_and_timeframe_are_carried_onto_the_bar(
        self, symbol: str, timeframe: str
    ) -> None:
        (only,) = bars([candle(at(2023, 6, 15, 4), symbol=symbol)], timeframe)
        assert only.symbol == symbol
        assert only.timeframe == timeframe

    def test_two_symbols_in_one_stream_are_refused(self) -> None:
        stream = [candle(at(2023, 6, 15, 4)), candle(at(2023, 6, 15, 4, 1), symbol="ETHUSDT")]
        with pytest.raises(AggregationError, match="mixed symbols"):
            bars(stream, "4h")


class TestInputThatCannotBeAggregatedWithoutGuessing:
    def test_a_candle_that_is_not_a_1m_bar_is_refused(self) -> None:
        with pytest.raises(AggregationError, match="expected 1m"):
            bars([candle(at(2023, 6, 15, 4), timeframe="5m")], "4h")

    def test_open_times_must_increase(self) -> None:
        stream = [candle(at(2023, 6, 15, 4, 1)), candle(at(2023, 6, 15, 4, 0))]
        with pytest.raises(AggregationError, match="do not increase"):
            bars(stream, "4h")

    def test_a_repeated_minute_is_refused_not_added_twice(self) -> None:
        stream = [candle(at(2023, 6, 15, 4, 1)), candle(at(2023, 6, 15, 4, 1))]
        with pytest.raises(AggregationError, match="do not increase"):
            bars(stream, "4h")

    def test_an_open_time_off_the_minute_is_refused(self) -> None:
        off = at(2023, 6, 15, 4, 0) + timedelta(seconds=30)
        with pytest.raises(AggregationError, match="off the minute grid"):
            bars([candle(off)], "4h")

    @pytest.mark.parametrize("timeframe", ["1m", "5m", "1h", "1w", ""])
    def test_a_timeframe_other_than_4h_and_1d_is_refused(self, timeframe: str) -> None:
        with pytest.raises(AggregationError, match="not an aggregated timeframe"):
            bars([], timeframe)


class TestTheBarType:
    def make(self, **override: object) -> AggregatedBar:
        fields: dict[str, object] = {
            "symbol": "BTCUSDT",
            "timeframe": "4h",
            "open_time": at(2023, 6, 15, 4),
            "close_time": at(2023, 6, 15, 7, 59),
            "open": "1",
            "high": "2",
            "low": "1",
            "close": "2",
            "volume": "3",
            "minutes_present": 240,
            "minutes_missing": 0,
        }
        fields.update(override)
        return AggregatedBar(**fields)

    def test_a_float_figure_is_refused(self) -> None:
        with pytest.raises(ValidationError):
            self.make(open=1.5)

    def test_the_bar_is_frozen(self) -> None:
        with pytest.raises(ValidationError):
            self.make().minutes_missing = 5

    def test_complete_follows_the_missing_count(self) -> None:
        assert self.make().complete is True
        assert self.make(minutes_present=239, minutes_missing=1).complete is False


def stored_row(opened: datetime, *, o: str) -> Row:
    return Row(
        open_time_ms=ms(opened),
        open=o,
        high=o,
        low=o,
        close=o,
        volume="1.00000000",
        close_time_ms=ms(opened) + 59_999,
    )


def store_rows(root: Path, symbol: str, month: str, rows: list[Row]) -> None:
    write_month(root, symbol, "1m", month, rows, **SOURCE)


def day_rows(day: datetime, *, price: str) -> list[Row]:
    return [stored_row(day + i * MINUTE, o=price) for i in range(1440)]


class TestAgainstARealStore:
    def test_a_month_file_boundary_ends_one_bucket_and_starts_the_next(
        self, tmp_path: Path
    ) -> None:
        store_rows(
            tmp_path,
            "BTCUSDT",
            "2021-02",
            [
                stored_row(at(2021, 2, 28, 23, 58), o="10.00000000"),
                stored_row(at(2021, 2, 28, 23, 59), o="11.00000000"),
            ],
        )
        store_rows(
            tmp_path,
            "BTCUSDT",
            "2021-03",
            [
                stored_row(at(2021, 3, 1, 0, 0), o="12.00000000"),
                stored_row(at(2021, 3, 1, 0, 1), o="13.00000000"),
            ],
        )
        store = HistoricalStore(tmp_path)
        first, second = aggregate_from_store(
            store, "BTCUSDT", "1d", at(2021, 2, 28), at(2021, 3, 2)
        )
        assert (first.open_time, first.open, first.close) == (
            at(2021, 2, 28),
            Decimal("10"),
            Decimal("11"),
        )
        assert (second.open_time, second.open, second.close) == (
            at(2021, 3, 1),
            Decimal("12"),
            Decimal("13"),
        )
        assert (first.minutes_missing, second.minutes_missing) == (1438, 1438)

    def test_a_whole_day_in_a_month_file_is_one_complete_1d_bar_and_six_4h_bars(
        self, tmp_path: Path
    ) -> None:
        store_rows(tmp_path, "BTCUSDT", "2021-03", day_rows(at(2021, 3, 1), price="7.00000000"))
        store = HistoricalStore(tmp_path)
        (day,) = aggregate_from_store(store, "BTCUSDT", "1d", at(2021, 3, 1), at(2021, 3, 2))
        sixths = list(aggregate_from_store(store, "BTCUSDT", "4h", at(2021, 3, 1), at(2021, 3, 2)))
        assert day.complete is True
        assert day.volume == Decimal("1440")
        assert len(sixths) == 6
        assert all(bar.complete and bar.volume == Decimal("240") for bar in sixths)

    def test_the_symbol_is_the_one_asked_for(self, tmp_path: Path) -> None:
        store_rows(tmp_path, "BTCUSDT", "2021-03", [stored_row(at(2021, 3, 1), o="1.00000000")])
        store_rows(tmp_path, "ETHUSDT", "2021-03", [stored_row(at(2021, 3, 1), o="2.00000000")])
        store = HistoricalStore(tmp_path)
        (eth,) = aggregate_from_store(store, "ETHUSDT", "1d", at(2021, 3, 1), at(2021, 3, 2))
        assert eth.symbol == "ETHUSDT"
        assert eth.open == Decimal("2")

    def test_no_month_file_at_or_after_end_is_opened(self, tmp_path: Path) -> None:
        store_rows(
            tmp_path,
            "BTCUSDT",
            "2023-12",
            [stored_row(at(2023, 12, 31, 23, 59), o="5.00000000")],
        )
        store_rows(tmp_path, "BTCUSDT", "2024-01", [stored_row(at(2024, 1, 1), o="6.00000000")])
        month_file(tmp_path, "BTCUSDT", "1m", "2024-01").write_bytes(b"not the bytes it hashed")
        store = HistoricalStore(tmp_path)
        (last,) = aggregate_from_store(store, "BTCUSDT", "1d", at(2023, 12, 31), at(2024, 1, 1))
        assert last.open_time == at(2023, 12, 31)
        with pytest.raises(StoredFileError):
            list(aggregate_from_store(store, "BTCUSDT", "1d", at(2023, 12, 31), at(2024, 1, 2)))

    @pytest.mark.parametrize(
        ("start", "end"),
        [
            (at(2021, 3, 1, 1), at(2021, 3, 2)),
            (at(2021, 3, 1), at(2021, 3, 2, 1)),
            (at(2021, 3, 1), at(2021, 3, 1, 12)),
        ],
    )
    def test_a_range_off_the_1d_grid_is_refused_at_the_call(
        self, tmp_path: Path, start: datetime, end: datetime
    ) -> None:
        with pytest.raises(AggregationError, match="not on the 1d grid"):
            aggregate_from_store(HistoricalStore(tmp_path / "absent"), "BTCUSDT", "1d", start, end)

    def test_a_range_on_the_4h_grid_but_not_the_1d_grid_is_accepted_for_4h(
        self, tmp_path: Path
    ) -> None:
        store_rows(tmp_path, "BTCUSDT", "2021-03", [stored_row(at(2021, 3, 1, 5), o="1.00000000")])
        found: Iterator[AggregatedBar] = aggregate_from_store(
            HistoricalStore(tmp_path), "BTCUSDT", "4h", at(2021, 3, 1, 4), at(2021, 3, 1, 8)
        )
        assert opens(list(found)) == [at(2021, 3, 1, 4)]

    def test_a_naive_start_or_end_is_refused_at_the_call(self, tmp_path: Path) -> None:
        naive = datetime(2021, 3, 1)
        store = HistoricalStore(tmp_path / "absent")
        with pytest.raises(AggregationError, match="timezone-aware"):
            aggregate_from_store(store, "BTCUSDT", "1d", naive, at(2021, 3, 2))
        with pytest.raises(AggregationError, match="timezone-aware"):
            aggregate_from_store(store, "BTCUSDT", "1d", at(2021, 3, 1), naive)

    def test_an_unaggregated_timeframe_is_refused_at_the_call(self, tmp_path: Path) -> None:
        with pytest.raises(AggregationError, match="not an aggregated timeframe"):
            aggregate_from_store(
                HistoricalStore(tmp_path), "BTCUSDT", "1h", at(2021, 3, 1), at(2021, 3, 2)
            )
