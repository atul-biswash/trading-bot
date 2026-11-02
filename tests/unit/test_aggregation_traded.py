"""The traded-minute aggregation: prices over minutes that traded, volume over every minute.

A traded minute is one with nonzero volume, because the store keeps no trade count. Every stream
is built here from literal prices and every expected value is a literal, or is computed in the test
from the same literals, never by the code under test.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

import pytest
from pydantic import ValidationError

from trading_bot.core.models import Candle
from trading_bot.data.aggregation import (
    AggregatedBar,
    AggregationError,
    TradedBar,
    aggregate_bars,
    aggregate_traded_bars,
    aggregate_traded_from_store,
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
SOURCE = {"source_url": "https://example.invalid/m.zip", "zip_sha256": "0" * 64}


def at(year: int, month: int, day: int, hour: int = 0, minute: int = 0) -> datetime:
    return datetime(year, month, day, hour, minute, tzinfo=UTC)


def ms(moment: datetime) -> int:
    return (moment - EPOCH) // timedelta(milliseconds=1)


def minute(
    opened: datetime,
    *,
    o: str,
    h: str,
    low: str,
    c: str,
    v: str,
    symbol: str = "BTCUSDT",
    timeframe: str = "1m",
) -> Candle:
    return Candle(
        symbol=symbol,
        timeframe=timeframe,
        open_time=opened,
        close_time=opened + timedelta(milliseconds=59_999),
        open=o,
        high=h,
        low=low,
        close=c,
        volume=v,
    )


def filler(opened: datetime, price: str, *, symbol: str = "BTCUSDT") -> Candle:
    """What the archive writes for a minute nothing traded in: the previous close, no volume."""
    return minute(opened, o=price, h=price, low=price, c=price, v="0", symbol=symbol)


def traded(opened: datetime, *, symbol: str = "BTCUSDT", i: int = 0) -> Candle:
    return minute(
        opened,
        o=str(1000 + i),
        h=str(2000 + i),
        low=str(500 + i),
        c=str(1500 + i),
        v="2",
        symbol=symbol,
    )


def run(start: datetime, count: int, *, symbol: str = "BTCUSDT") -> list[Candle]:
    return [traded(start + i * MINUTE, symbol=symbol, i=i) for i in range(count)]


def one_bar(candles: list[Candle], timeframe: str = "4h") -> TradedBar:
    (only,) = aggregate_traded_bars(candles, timeframe)
    return only


def plain_bar(candles: list[Candle], timeframe: str = "4h") -> AggregatedBar:
    (only,) = aggregate_bars(candles, timeframe)
    return only


class TestABucketInWhichEveryMinuteTraded:
    def test_it_equals_the_plain_aggregation_in_the_four_prices(self) -> None:
        stream = run(at(2023, 6, 15, 4), 240)
        plain = plain_bar(stream)
        found = one_bar(stream)
        assert (found.open, found.high, found.low, found.close) == (
            plain.open,
            plain.high,
            plain.low,
            plain.close,
        )
        assert (found.open, found.high, found.low, found.close) == (
            Decimal("1000"),
            Decimal("2239"),
            Decimal("500"),
            Decimal("1739"),
        )

    def test_the_counts_and_the_volume(self) -> None:
        found = one_bar(run(at(2023, 6, 15, 4), 240))
        assert found.traded_minutes == 240
        assert found.minutes_present == 240
        assert found.minutes_missing == 0
        assert found.volume == Decimal("480")
        assert found.complete is True
        assert found.has_trade is True

    def test_every_figure_is_a_decimal(self) -> None:
        found = one_bar(run(at(2023, 6, 15, 4), 3))
        figures = (found.open, found.high, found.low, found.close, found.volume)
        assert all(type(figure) is Decimal for figure in figures)


class TestAZeroTradeFirstMinute:
    def test_the_open_is_the_first_traded_minutes_not_the_fillers(self) -> None:
        stream = [
            filler(at(2023, 6, 15, 4, 0), "50"),
            minute(at(2023, 6, 15, 4, 1), o="60", h="70", low="55", c="65", v="3"),
        ]
        found = one_bar(stream)
        assert found.open == Decimal("60")
        assert found.traded_minutes == 1
        assert found.minutes_present == 2
        assert found.volume == Decimal("3")

    def test_the_plain_aggregation_takes_the_fillers_open_and_that_is_the_difference(self) -> None:
        stream = [
            filler(at(2023, 6, 15, 4, 0), "50"),
            minute(at(2023, 6, 15, 4, 1), o="60", h="70", low="55", c="65", v="3"),
        ]
        assert plain_bar(stream).open == Decimal("50")
        assert one_bar(stream).open == Decimal("60")

    def test_a_filler_whose_price_is_the_first_trade_changes_nothing(self) -> None:
        stream = [
            filler(at(2023, 6, 15, 4, 0), "60"),
            minute(at(2023, 6, 15, 4, 1), o="60", h="70", low="55", c="65", v="3"),
        ]
        assert one_bar(stream).open == plain_bar(stream).open == Decimal("60")


class TestAZeroTradeLastMinute:
    def test_the_close_is_the_last_traded_minutes(self) -> None:
        stream = [
            minute(at(2023, 6, 15, 4, 0), o="60", h="70", low="55", c="65", v="3"),
            filler(at(2023, 6, 15, 4, 1), "65"),
            filler(at(2023, 6, 15, 4, 2), "65"),
        ]
        found = one_bar(stream)
        assert found.close == Decimal("65")
        assert found.traded_minutes == 1

    def test_a_filler_close_that_differs_is_not_taken(self) -> None:
        stream = [
            minute(at(2023, 6, 15, 4, 0), o="60", h="70", low="55", c="65", v="3"),
            filler(at(2023, 6, 15, 4, 1), "999"),
        ]
        assert one_bar(stream).close == Decimal("65")
        assert plain_bar(stream).close == Decimal("999")


class TestAZeroTradeExtreme:
    def test_a_fillers_high_and_low_do_not_widen_the_bucket(self) -> None:
        stream = [
            minute(at(2023, 6, 15, 4, 0), o="60", h="70", low="55", c="65", v="3"),
            minute(at(2023, 6, 15, 4, 1), o="999", h="999", low="1", c="999", v="0"),
            minute(at(2023, 6, 15, 4, 2), o="65", h="68", low="58", c="66", v="1"),
        ]
        found = one_bar(stream)
        assert (found.high, found.low) == (Decimal("70"), Decimal("55"))
        plain = plain_bar(stream)
        assert (plain.high, plain.low) == (Decimal("999"), Decimal("1"))

    def test_a_traded_extreme_is_kept(self) -> None:
        stream = [
            filler(at(2023, 6, 15, 4, 0), "50"),
            minute(at(2023, 6, 15, 4, 1), o="60", h="70", low="55", c="65", v="3"),
            minute(at(2023, 6, 15, 4, 2), o="65", h="90", low="20", c="66", v="1"),
        ]
        found = one_bar(stream)
        assert (found.high, found.low) == (Decimal("90"), Decimal("20"))


class TestABucketWithNoTradedMinute:
    def test_it_has_no_prices_a_volume_of_zero_and_is_still_complete(self) -> None:
        stream = [filler(at(2023, 6, 15, 4) + i * MINUTE, "50") for i in range(240)]
        found = one_bar(stream)
        assert (found.open, found.high, found.low, found.close) == (None, None, None, None)
        assert found.volume == Decimal("0")
        assert found.traded_minutes == 0
        assert found.has_trade is False
        assert found.complete is True

    def test_it_is_emitted_and_not_skipped_or_priced_from_a_neighbour(self) -> None:
        stream = run(at(2023, 6, 15, 0), 240) + [
            filler(at(2023, 6, 15, 4) + i * MINUTE, "50") for i in range(240)
        ]
        first, second = aggregate_traded_bars(stream, "4h")
        assert first.has_trade is True
        assert second.has_trade is False
        assert second.open is None

    def test_a_bar_with_no_traded_minute_cannot_carry_a_price(self) -> None:
        with pytest.raises(ValidationError):
            TradedBar(**self.fields(traded_minutes=0, open="1"))

    def test_a_bar_with_a_traded_minute_must_carry_all_four_prices(self) -> None:
        with pytest.raises(ValidationError):
            TradedBar(**self.fields(traded_minutes=1, low=None))

    def test_a_float_price_is_refused(self) -> None:
        with pytest.raises(ValidationError):
            TradedBar(**self.fields(traded_minutes=1, open=1.5))

    @staticmethod
    def fields(**override: object) -> dict[str, object]:
        base: dict[str, object] = {
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
            "traded_minutes": 1,
        }
        base.update(override)
        return base


class TestGapsAreStillReportedAndNeverFilled:
    def test_a_missing_minute_is_counted_beside_a_filler(self) -> None:
        stream = [
            filler(at(2023, 6, 15, 4, 0), "50"),
            minute(at(2023, 6, 15, 4, 2), o="60", h="70", low="55", c="65", v="3"),
        ]
        found = one_bar(stream)
        assert found.minutes_present == 2
        assert found.minutes_missing == 238
        assert found.complete is False
        assert found.traded_minutes == 1

    def test_a_bucket_with_no_stored_minute_is_not_emitted(self) -> None:
        stream = run(at(2023, 6, 15, 4), 240) + run(at(2023, 6, 15, 12), 240)
        found = list(aggregate_traded_bars(stream, "4h"))
        assert [bar.open_time for bar in found] == [at(2023, 6, 15, 4), at(2023, 6, 15, 12)]


class TestBothPairsAndBothTimeframes:
    @pytest.mark.parametrize("symbol", ["BTCUSDT", "ETHUSDT"])
    @pytest.mark.parametrize("timeframe", ["4h", "1d"])
    def test_the_symbol_timeframe_and_grid_are_the_plain_aggregations(
        self, symbol: str, timeframe: str
    ) -> None:
        stream = run(at(2023, 6, 15, 3, 58), 4, symbol=symbol)
        plain = list(aggregate_bars(stream, timeframe))
        found = list(aggregate_traded_bars(stream, timeframe))
        assert [bar.open_time for bar in found] == [bar.open_time for bar in plain]
        assert [bar.close_time for bar in found] == [bar.close_time for bar in plain]
        assert {bar.symbol for bar in found} == {symbol}
        assert {bar.timeframe for bar in found} == {timeframe}

    @pytest.mark.parametrize("symbol", ["BTCUSDT", "ETHUSDT"])
    def test_a_day_equals_the_fold_of_its_six_4h_buckets_with_a_filler_first(
        self, symbol: str
    ) -> None:
        stream = [
            filler(at(2023, 6, 15, 0, 0), "50", symbol=symbol),
            *run(at(2023, 6, 15, 0, 1), 1439, symbol=symbol),
        ]
        (day,) = aggregate_traded_bars(stream, "1d")
        sixths = list(aggregate_traded_bars(stream, "4h"))
        assert len(sixths) == 6
        assert day.open == sixths[0].open == Decimal("1000")
        assert day.close == sixths[-1].close
        assert day.high == max(bar.high for bar in sixths if bar.high is not None)
        assert day.low == min(bar.low for bar in sixths if bar.low is not None)
        assert day.volume == sum((bar.volume for bar in sixths), Decimal(0))
        assert day.traded_minutes == 1439
        assert day.minutes_present == 1440


class TestTheStreamChecksAreTheSame:
    def test_a_candle_that_is_not_a_1m_bar_is_refused(self) -> None:
        stream = [minute(at(2023, 6, 15, 4), o="1", h="1", low="1", c="1", v="1", timeframe="5m")]
        with pytest.raises(AggregationError, match="expected 1m"):
            list(aggregate_traded_bars(stream, "4h"))

    def test_open_times_must_increase(self) -> None:
        stream = [traded(at(2023, 6, 15, 4, 1)), traded(at(2023, 6, 15, 4, 0))]
        with pytest.raises(AggregationError, match="do not increase"):
            list(aggregate_traded_bars(stream, "4h"))

    def test_two_symbols_are_refused(self) -> None:
        stream = [traded(at(2023, 6, 15, 4, 0)), traded(at(2023, 6, 15, 4, 1), symbol="ETHUSDT")]
        with pytest.raises(AggregationError, match="mixed symbols"):
            list(aggregate_traded_bars(stream, "4h"))

    def test_an_open_time_off_the_minute_is_refused(self) -> None:
        off = at(2023, 6, 15, 4) + timedelta(seconds=30)
        with pytest.raises(AggregationError, match="off the minute grid"):
            list(aggregate_traded_bars([traded(off)], "4h"))

    @pytest.mark.parametrize("timeframe", ["1m", "1h", "1w", ""])
    def test_a_timeframe_other_than_4h_and_1d_is_refused(self, timeframe: str) -> None:
        with pytest.raises(AggregationError, match="not an aggregated timeframe"):
            list(aggregate_traded_bars([], timeframe))

    def test_empty_input_gives_no_bars(self) -> None:
        assert list(aggregate_traded_bars([], "4h")) == []


def stored(opened: datetime, *, o: str, volume: str) -> Row:
    return Row(
        open_time_ms=ms(opened),
        open=o,
        high=o,
        low=o,
        close=o,
        volume=volume,
        close_time_ms=ms(opened) + 59_999,
    )


def put(root: Path, symbol: str, month: str, rows: list[Row]) -> None:
    write_month(root, symbol, "1m", month, rows, **SOURCE)


class TestAgainstARealStore:
    def test_a_filler_first_minute_is_skipped_for_the_open_and_counted_for_the_volume(
        self, tmp_path: Path
    ) -> None:
        put(
            tmp_path,
            "BTCUSDT",
            "2021-03",
            [
                stored(at(2021, 3, 1, 0, 0), o="5.00000000", volume="0.00000000"),
                stored(at(2021, 3, 1, 0, 1), o="6.00000000", volume="1.50000000"),
            ],
        )
        store = HistoricalStore(tmp_path)
        (day,) = aggregate_traded_from_store(store, "BTCUSDT", "1d", at(2021, 3, 1), at(2021, 3, 2))
        assert (day.open, day.volume, day.traded_minutes, day.minutes_present) == (
            Decimal("6"),
            Decimal("1.5"),
            1,
            2,
        )

    def test_the_symbol_is_the_one_asked_for(self, tmp_path: Path) -> None:
        put(tmp_path, "BTCUSDT", "2021-03", [stored(at(2021, 3, 1), o="1.00000000", volume="1")])
        put(tmp_path, "ETHUSDT", "2021-03", [stored(at(2021, 3, 1), o="2.00000000", volume="1")])
        (eth,) = aggregate_traded_from_store(
            HistoricalStore(tmp_path), "ETHUSDT", "1d", at(2021, 3, 1), at(2021, 3, 2)
        )
        assert (eth.symbol, eth.open) == ("ETHUSDT", Decimal("2"))

    def test_no_month_file_at_or_after_end_is_opened(self, tmp_path: Path) -> None:
        put(
            tmp_path,
            "BTCUSDT",
            "2023-12",
            [stored(at(2023, 12, 31, 23, 59), o="5.00000000", volume="1")],
        )
        put(tmp_path, "BTCUSDT", "2024-01", [stored(at(2024, 1, 1), o="6.00000000", volume="1")])
        month_file(tmp_path, "BTCUSDT", "1m", "2024-01").write_bytes(b"not the bytes it hashed")
        store = HistoricalStore(tmp_path)
        (last,) = aggregate_traded_from_store(
            store, "BTCUSDT", "1d", at(2023, 12, 31), at(2024, 1, 1)
        )
        assert last.open_time == at(2023, 12, 31)
        with pytest.raises(StoredFileError):
            list(
                aggregate_traded_from_store(
                    store, "BTCUSDT", "1d", at(2023, 12, 31), at(2024, 1, 2)
                )
            )

    @pytest.mark.parametrize(
        ("start", "end"),
        [(at(2021, 3, 1, 1), at(2021, 3, 2)), (at(2021, 3, 1), at(2021, 3, 2, 1))],
    )
    def test_a_range_off_the_grid_is_refused_at_the_call(
        self, tmp_path: Path, start: datetime, end: datetime
    ) -> None:
        with pytest.raises(AggregationError, match="not on the 1d grid"):
            aggregate_traded_from_store(
                HistoricalStore(tmp_path / "absent"), "BTCUSDT", "1d", start, end
            )

    def test_a_naive_instant_and_an_unaggregated_timeframe_are_refused_at_the_call(
        self, tmp_path: Path
    ) -> None:
        store = HistoricalStore(tmp_path / "absent")
        with pytest.raises(AggregationError, match="timezone-aware"):
            aggregate_traded_from_store(
                store, "BTCUSDT", "1d", datetime(2021, 3, 1), at(2021, 3, 2)
            )
        with pytest.raises(AggregationError, match="not an aggregated timeframe"):
            aggregate_traded_from_store(store, "BTCUSDT", "1h", at(2021, 3, 1), at(2021, 3, 2))
