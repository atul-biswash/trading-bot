"""Row classification at ingest (owner's rulings R-L and R-M).

The fixtures that matter are REAL archive rows, quoted verbatim by the P102 census of all
1,100 monthly files (``M5m-070``, ``M5m-071``): one for each shape, read from the files
whose refusal at C4 this classification replaces. A synthetic row is used only where the
census found no instance of the thing under test (a close past the bar's end, a bad
price) or where a month needs filler, and says so.

Expected values are written from the rulings and from literals, never from the function
under test. The sweep over every close offset of one bar is written against the ruling's
wording and not against ``classify_times``.
"""

from __future__ import annotations

import hashlib
import io
import zipfile
from pathlib import Path

import pytest

import trading_bot.data.historical as hist
from trading_bot.data.historical import (
    QUARANTINED_SHAPES,
    ArchiveFormatError,
    ClassifiedMonth,
    IrregularRow,
    Row,
    RowShape,
    check_stored,
    classify_times,
    ingest_zip,
    normalise_archive,
)

# ---- real rows, verbatim from the P102 census ------------------------------------------
# A short bar that traded: BTCUSDT 1h 2017-12-18T12:00, closed at 12:29:13.419.
SHORT_1H = (
    "1513598400000,19116.11000000,19300.00000000,19100.02000000,19161.00000000,242.02821800,"
    "1513600153419,4637857.61884583,2018,129.56599800,2483611.60697771,77673.23955632"
)
# A short bar with no trade: BTCUSDT 1h 2019-06-07T21:00, closed at 21:13:13.524.
ZERO_TRADE_SHORT_1H = (
    "1559941200000,7930.85000000,7930.85000000,7930.85000000,7930.85000000,0.00000000,"
    "1559941993524,0.00000000,0,0.00000000,0.00000000,0"
)
# Closed one millisecond late, at the next bar's open: BTCUSDT 1h 2017-09-06T15:00.
ONE_MS_LATE_1H = (
    "1504710000000,4503.00000000,4619.47000000,4488.33000000,4619.43000000,43.86276800,"
    "1504713600000,199660.76388168,441,29.55703100,134755.08198687,11146.71897399"
)
# Closed on a whole second: BTCUSDT 1h 2021-08-13T01:00, closed at 01:59:59.000.
WHOLE_SECOND_1H = (
    "1628816400000,44493.69000000,44922.00000000,44455.00000000,44847.26000000,1980.12661900,"
    "1628819999000,88562762.79188752,135331,986.53758700,44121929.11192070,0"
)
# A placeholder that closes before it opens: BTCUSDT 1h 2020-12-21T14:00, close 13:47:20.521.
CLOSE_BEFORE_OPEN_1H = (
    "1608559200000,22646.53000000,22646.53000000,22646.53000000,22646.53000000,0.00000000,"
    "1608558440521,0.00000000,0,0.00000000,0.00000000,0"
)
# BTCUSDT 1m 2017-12: line 4681 is a short bar (closes 20.798 s in) and line 4682 opens at
# 06:00:20.799, off the minute grid, and so do the 20,400 rows after it.
SHORT_1M = (
    "1512367200000,11476.87000000,11478.00000000,11476.87000000,11478.00000000,0.28948500,"
    "1512367220798,3322.46567959,4,0.28948500,3322.46567959,37184.18214844"
)
OFF_GRID_1M = (
    "1512367220799,11478.00000000,11478.00000000,11478.00000000,11478.00000000,0.00000000,"
    "1512367280798,0.00000000,0,0.00000000,0.00000000,37184.17978073"
)
# Lines 25081 and 25082 of the same file, the end of the shifted run. 25082 is off the grid
# AND closes early, and the ruling puts the grid first.
OFF_GRID_END_1M = (
    "1513591160799,18719.72000000,18719.77000000,18656.98000000,18668.53000000,7.01241000,"
    "1513591220798,131141.01821479,105,2.10705100,39423.31870064,77284.64063883"
)
OFF_GRID_SHORT_1M = (
    "1513591220799,18668.53000000,18668.53000000,18657.24000000,18668.53000000,0.00342700,"
    "1513591242445,63.94318231,4,0.00032700,6.10460931,77284.63976616"
)

DEC_FIRST = (
    "1733011200000,96407.99000000,97836.00000000,95693.88000000,97185.18000000,"
    "16938.60452000,1733097599999,1641327626.60622060,3342200,8114.89569000,"
    "786489040.19363780,0"
)
MINUTE = 60_000
HOUR = 3_600_000

DEC_1 = 1512086400000  # 2017-12-01T00:00Z
DEC_10 = 1512864000000
DEC_11 = 1512950400000
DEC_12 = 1513036800000


def bar(
    opened: int,
    closed: int,
    *,
    open_: str = "10.00000000",
    high: str = "12.00000000",
    low: str = "9.00000000",
    close: str = "11.00000000",
    volume: str = "1.00000000",
) -> str:
    """A synthetic archive line: twelve fields, prices that enclose each other."""
    return f"{opened},{open_},{high},{low},{close},{volume},{closed},11.0,1,0.5,5.5,0"


def text_of(*lines: str) -> str:
    return "\n".join(lines) + "\n"


def classified(text: str, *, interval: str, month: str) -> ClassifiedMonth:
    try:
        return normalise_archive(text, interval=interval, month=month)
    except ArchiveFormatError as exc:
        pytest.fail(f"a month of known classes was refused: {exc}")


def shape_of(open_ms: int, close_ms: int, interval_ms: int) -> RowShape | None:
    try:
        return classify_times(open_ms, close_ms, interval_ms)
    except ArchiveFormatError as exc:
        pytest.fail(f"a known shape was refused: {exc}")


class TestTheShapesTheRulingNames:
    def test_the_shape_names_are_the_ones_the_registry_will_persist(self) -> None:
        assert [shape.value for shape in RowShape] == [
            "short_bar",
            "one_ms_late",
            "whole_second",
            "off_grid",
            "close_not_after_open",
        ]

    def test_exactly_two_shapes_are_quarantined(self) -> None:
        assert {RowShape.OFF_GRID, RowShape.CLOSE_NOT_AFTER_OPEN} == QUARANTINED_SHAPES

    def test_a_regular_bar_is_stored_and_registers_nothing(self) -> None:
        month = classified(text_of(DEC_FIRST), interval="1d", month="2024-12")
        assert len(month.rows) == 1
        assert month.registered == ()
        assert month.quarantined == ()


class TestRegisteredShapesAreStoredVerbatim:
    def test_a_short_bar_is_stored_with_its_own_close_and_registered(self) -> None:
        month = classified(text_of(SHORT_1H), interval="1h", month="2017-12")
        assert month.rows == (
            Row(
                1513598400000,
                "19116.11000000",
                "19300.00000000",
                "19100.02000000",
                "19161.00000000",
                "242.02821800",
                1513600153419,
            ),
        )
        assert month.registered == (IrregularRow(1, RowShape.SHORT_BAR, 1513598400000, SHORT_1H),)
        assert month.quarantined == ()

    def test_a_zero_trade_short_bar_is_kept_like_any_other(self) -> None:
        month = classified(text_of(ZERO_TRADE_SHORT_1H), interval="1h", month="2019-06")
        assert [row.volume for row in month.rows] == ["0.00000000"]
        assert month.rows[0].close_time_ms == 1559941993524
        assert [r.shape for r in month.registered] == [RowShape.SHORT_BAR]
        assert month.quarantined == ()

    def test_a_close_one_millisecond_late_is_not_repaired(self) -> None:
        month = classified(text_of(ONE_MS_LATE_1H), interval="1h", month="2017-09")
        assert [row.close_time_ms for row in month.rows] == [1504713600000]
        assert month.registered == (
            IrregularRow(1, RowShape.ONE_MS_LATE, 1504710000000, ONE_MS_LATE_1H),
        )

    def test_a_whole_second_close_is_stored_as_the_archive_wrote_it(self) -> None:
        month = classified(text_of(WHOLE_SECOND_1H), interval="1h", month="2021-08")
        assert [row.close_time_ms for row in month.rows] == [1628819999000]
        assert month.registered == (
            IrregularRow(1, RowShape.WHOLE_SECOND, 1628816400000, WHOLE_SECOND_1H),
        )

    def test_the_registered_raw_line_keeps_all_twelve_fields(self) -> None:
        month = classified(text_of(ONE_MS_LATE_1H), interval="1h", month="2017-09")
        assert len(month.registered) == 1
        assert month.registered[0].raw.split(",")[11] == "11146.71897399"
        assert len(month.registered[0].raw.split(",")) == 12

    def test_a_registered_row_is_in_the_rows_and_the_line_number_is_the_files(self) -> None:
        month = classified(
            text_of(bar(DEC_1, DEC_1 + MINUTE - 1), SHORT_1M), interval="1m", month="2017-12"
        )
        assert [row.open_time_ms for row in month.rows] == [DEC_1, 1512367200000]
        assert [r.line for r in month.registered] == [2]


class TestQuarantinedShapesAreNotStored:
    def test_a_close_before_the_open_is_set_aside_with_its_raw_line(self) -> None:
        month = classified(text_of(CLOSE_BEFORE_OPEN_1H), interval="1h", month="2020-12")
        assert month.rows == ()
        assert month.registered == ()
        assert month.quarantined == (
            IrregularRow(1, RowShape.CLOSE_NOT_AFTER_OPEN, 1608559200000, CLOSE_BEFORE_OPEN_1H),
        )

    def test_a_close_equal_to_the_open_is_not_after_it_either(self) -> None:
        line = bar(DEC_1, DEC_1)
        month = classified(text_of(line), interval="1m", month="2017-12")
        assert [r.shape for r in month.quarantined] == [RowShape.CLOSE_NOT_AFTER_OPEN]

    def test_a_close_one_millisecond_after_the_open_is_a_short_bar_and_is_stored(self) -> None:
        month = classified(text_of(bar(DEC_1, DEC_1 + 1)), interval="1m", month="2017-12")
        assert [r.shape for r in month.registered] == [RowShape.SHORT_BAR]
        assert month.quarantined == ()

    def test_an_off_grid_open_is_set_aside_and_the_short_bar_before_it_is_kept(self) -> None:
        month = classified(text_of(SHORT_1M, OFF_GRID_1M), interval="1m", month="2017-12")
        assert [row.open_time_ms for row in month.rows] == [1512367200000]
        assert month.registered == (IrregularRow(1, RowShape.SHORT_BAR, 1512367200000, SHORT_1M),)
        assert month.quarantined == (
            IrregularRow(2, RowShape.OFF_GRID, 1512367220799, OFF_GRID_1M),
        )

    def test_the_grid_outranks_an_early_close(self) -> None:
        month = classified(
            text_of(OFF_GRID_END_1M, OFF_GRID_SHORT_1M), interval="1m", month="2017-12"
        )
        assert month.rows == ()
        assert [r.shape for r in month.quarantined] == [RowShape.OFF_GRID, RowShape.OFF_GRID]
        assert month.registered == ()

    def test_the_grid_outranks_a_close_that_is_not_after_the_open(self) -> None:
        off_grid = bar(DEC_1 + 1, DEC_1)
        month = classified(text_of(off_grid), interval="1m", month="2017-12")
        assert [r.shape for r in month.quarantined] == [RowShape.OFF_GRID]

    def test_a_quarantined_row_still_has_to_increase(self) -> None:
        with pytest.raises(ArchiveFormatError, match="line 2: open_time does not increase"):
            normalise_archive(
                text_of(bar(DEC_1 + MINUTE, DEC_1 + 2 * MINUTE - 1), bar(DEC_1 + 1, DEC_1 + 2)),
                interval="1m",
                month="2017-12",
            )

    def test_a_bar_that_opens_before_an_earlier_quarantined_row_is_out_of_order(self) -> None:
        stored = bar(DEC_1 + MINUTE, DEC_1 + 2 * MINUTE - 1)
        off_grid = bar(DEC_1 + 2 * MINUTE + 30_000, DEC_1 + 3 * MINUTE + 29_999)
        on_grid_before_it = bar(DEC_1 + 2 * MINUTE, DEC_1 + 3 * MINUTE - 1)
        with pytest.raises(ArchiveFormatError, match="line 3: open_time does not increase"):
            normalise_archive(
                text_of(stored, off_grid, on_grid_before_it), interval="1m", month="2017-12"
            )

    def test_a_quarantined_row_still_has_to_lie_inside_the_month(self) -> None:
        with pytest.raises(ArchiveFormatError, match="outside 2017-12"):
            normalise_archive(text_of(bar(DEC_1 - 1, DEC_1 + 5)), interval="1m", month="2017-12")

    def test_a_quarantined_row_still_has_its_prices_checked(self) -> None:
        line = bar(DEC_1 + 1, DEC_1 + 2, low="13.00000000")
        with pytest.raises(ArchiveFormatError, match="line 1: the low and high"):
            normalise_archive(text_of(line), interval="1m", month="2017-12")

    def test_a_month_of_quarantined_rows_alone_classifies_with_nothing_to_store(self) -> None:
        month = classified(text_of(CLOSE_BEFORE_OPEN_1H), interval="1h", month="2020-12")
        assert (len(month.rows), len(month.quarantined)) == (0, 1)

    def test_a_month_holding_every_known_shape_is_not_refused(self) -> None:
        text = text_of(
            bar(DEC_1, DEC_1 + MINUTE - 1),
            SHORT_1M,
            OFF_GRID_1M,
            bar(DEC_10, DEC_10 + MINUTE),
            bar(DEC_11, DEC_11 + MINUTE - 1000),
            bar(DEC_12, DEC_12 - 1),
        )
        month = classified(text, interval="1m", month="2017-12")
        assert [row.open_time_ms for row in month.rows] == [DEC_1, 1512367200000, DEC_10, DEC_11]
        assert [(r.line, r.shape) for r in month.registered] == [
            (2, RowShape.SHORT_BAR),
            (4, RowShape.ONE_MS_LATE),
            (5, RowShape.WHOLE_SECOND),
        ]
        assert [(r.line, r.shape) for r in month.quarantined] == [
            (3, RowShape.OFF_GRID),
            (6, RowShape.CLOSE_NOT_AFTER_OPEN),
        ]


class TestWhatNoClassCoversRefusesTheMonth:
    @pytest.mark.parametrize("past", [2, 3, 1000, HOUR])
    def test_a_close_past_the_bars_end_refuses_the_month_and_names_the_line(
        self, past: int
    ) -> None:
        # Synthetic: the census found no row of this shape in any of the 1,100 files.
        good = bar(DEC_1, DEC_1 + MINUTE - 1)
        late = bar(DEC_1 + MINUTE, DEC_1 + 2 * MINUTE - 1 + past)
        with pytest.raises(ArchiveFormatError, match=r"line 2: .*is not open_time .*no class"):
            normalise_archive(text_of(good, late), interval="1m", month="2017-12")

    @pytest.mark.parametrize(
        ("field", "value"),
        [
            ("open_", "0.00000000"),
            ("high", "0"),
            ("low", "0.00000000"),
            ("close", "0"),
        ],
    )
    def test_a_price_that_is_not_positive_refuses_the_month(self, field: str, value: str) -> None:
        with pytest.raises(ArchiveFormatError, match="line 1: a price is not positive"):
            normalise_archive(
                text_of(bar(DEC_1, DEC_1 + MINUTE - 1, **{field: value})),
                interval="1m",
                month="2017-12",
            )

    @pytest.mark.parametrize(
        "prices",
        [
            {"low": "10.50000000"},
            {"low": "11.50000000"},
            {"high": "10.50000000"},
            {"high": "9.50000000"},
            {"low": "12.50000000", "high": "12.00000000"},
        ],
    )
    def test_a_low_and_high_that_do_not_enclose_the_bar_refuse_the_month(
        self, prices: dict[str, str]
    ) -> None:
        with pytest.raises(ArchiveFormatError, match="line 1: the low and high"):
            normalise_archive(
                text_of(bar(DEC_1, DEC_1 + MINUTE - 1, **prices)),
                interval="1m",
                month="2017-12",
            )

    @pytest.mark.parametrize(
        "prices",
        [
            {"low": "10.00000000"},
            {"low": "11.00000000", "open_": "11.00000000"},
            {"high": "11.00000000", "open_": "11.00000000"},
            {"high": "10.00000000", "close": "10.00000000"},
            {"low": "10.00000000", "high": "10.00000000", "close": "10.00000000"},
        ],
    )
    def test_a_bar_whose_open_or_close_sits_on_the_low_or_high_is_accepted(
        self, prices: dict[str, str]
    ) -> None:
        month = classified(
            text_of(bar(DEC_1, DEC_1 + MINUTE - 1, **prices)), interval="1m", month="2017-12"
        )
        assert len(month.rows) == 1

    def test_an_unknown_shape_after_known_ones_still_refuses_the_whole_month(self) -> None:
        text = text_of(SHORT_1M, OFF_GRID_1M, bar(DEC_10, DEC_10 + MINUTE + 5))
        with pytest.raises(ArchiveFormatError, match="line 3"):
            normalise_archive(text, interval="1m", month="2017-12")


class TestClassifyTimes:
    @pytest.mark.parametrize(
        ("interval_ms", "opened", "closed", "expected"),
        [
            (MINUTE, DEC_1, DEC_1 + MINUTE - 1, None),
            (HOUR, 1504710000000, 1504713599999, None),
            (86_400_000, 1733011200000, 1733097599999, None),
            (MINUTE, DEC_1, DEC_1 + MINUTE, RowShape.ONE_MS_LATE),
            (HOUR, 1504710000000, 1504713600000, RowShape.ONE_MS_LATE),
            (HOUR, 1628816400000, 1628819999000, RowShape.WHOLE_SECOND),
            (MINUTE, DEC_1, DEC_1 + MINUTE - 1000, RowShape.WHOLE_SECOND),
            (HOUR, 1513598400000, 1513600153419, RowShape.SHORT_BAR),
            (HOUR, DEC_1, DEC_1 + 1, RowShape.SHORT_BAR),
            (HOUR, DEC_1, DEC_1, RowShape.CLOSE_NOT_AFTER_OPEN),
            (HOUR, 1608559200000, 1608558440521, RowShape.CLOSE_NOT_AFTER_OPEN),
            (MINUTE, DEC_1 + 1, DEC_1 + MINUTE, RowShape.OFF_GRID),
            (HOUR, DEC_1 + MINUTE, DEC_1 + MINUTE + 5, RowShape.OFF_GRID),
        ],
    )
    def test_each_documented_case(
        self, interval_ms: int, opened: int, closed: int, expected: RowShape | None
    ) -> None:
        assert shape_of(opened, closed, interval_ms) is expected

    def test_a_close_one_millisecond_either_side_of_a_whole_second_is_a_short_bar(self) -> None:
        for offset in (-1000, -998):
            assert shape_of(DEC_1, DEC_1 + MINUTE - 1 + offset, MINUTE) is RowShape.SHORT_BAR

    def test_every_close_offset_of_one_bar_lands_in_exactly_the_ruled_class(self) -> None:
        """Written against the ruling's wording, over every close from 1 ms before the bar's
        regular close back to the bar's open, and two milliseconds past it.
        """
        for offset in range(-MINUTE, 4):
            closed = DEC_1 + MINUTE - 1 + offset
            if closed <= DEC_1:
                want: RowShape | None = RowShape.CLOSE_NOT_AFTER_OPEN
            elif offset == 0:
                want = None
            elif offset == 1:
                want = RowShape.ONE_MS_LATE
            elif offset == -999:
                want = RowShape.WHOLE_SECOND
            elif offset < 0:
                want = RowShape.SHORT_BAR
            else:
                with pytest.raises(ArchiveFormatError, match="no class"):
                    classify_times(DEC_1, closed, MINUTE)
                continue
            assert shape_of(DEC_1, closed, MINUTE) is want, offset

    def test_the_grid_is_the_epoch_grid_of_the_interval_not_of_the_first_bar(self) -> None:
        assert shape_of(HOUR * 5, HOUR * 5 + HOUR - 1, HOUR) is None
        assert shape_of(HOUR * 5 + MINUTE, HOUR * 6 + MINUTE - 1, HOUR) is RowShape.OFF_GRID

    def test_a_microsecond_close_is_floored_before_it_is_classified(self) -> None:
        opened_us = 1735689600000000
        regular_us = 1735775999999999
        cases = {
            regular_us - 1: None,
            regular_us - 999: None,
            regular_us - 1000: RowShape.SHORT_BAR,
            regular_us + 1: RowShape.ONE_MS_LATE,
            regular_us + 1000: RowShape.ONE_MS_LATE,
        }
        for closed_us, want in cases.items():
            line = f"{opened_us},1.0,2.0,0.5,1.5,3.0,{closed_us},0,0,0,0,0"
            month = classified(text_of(line), interval="1d", month="2025-01")
            got = month.registered[0].shape if month.registered else None
            assert got is want, closed_us
            assert month.rows[0].close_time_ms == closed_us // 1000


class TestIngestKeepsOnlyWhatTheRulingStores:
    @staticmethod
    def zip_of(name: str, text: str) -> tuple[bytes, str]:
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
            archive.writestr(name, text.encode("utf-8"))
        data = buffer.getvalue()
        return data, hashlib.sha256(data).hexdigest()

    def ingest(self, root: Path, text: str, *, interval: str = "1m", month: str = "2017-12"):
        data, digest = self.zip_of(f"BTCUSDT-{interval}-{month}.csv", text)
        return ingest_zip(
            data,
            expected_sha256=digest,
            root=root,
            symbol="BTCUSDT",
            interval=interval,
            month=month,
            source_url="https://data.binance.vision/x.zip",
        )

    def accepted_ingest(self, root: Path, text: str) -> hist.IngestResult:
        try:
            return self.ingest(root, text)
        except hist.HistoricalDataError as exc:
            pytest.fail(f"a month of known classes was refused: {exc}")

    def test_the_stored_file_holds_the_verbatim_rows_and_not_the_quarantined_one(
        self, tmp_path: Path
    ) -> None:
        text = text_of(bar(DEC_1, DEC_1 + MINUTE - 1), SHORT_1M, OFF_GRID_1M)
        result = self.accepted_ingest(tmp_path, text)
        assert result.entry.rows == 2
        assert [r.shape for r in result.registered] == [RowShape.SHORT_BAR]
        assert [r.shape for r in result.quarantined] == [RowShape.OFF_GRID]
        assert result.quarantined[0].raw == OFF_GRID_1M
        lines = (tmp_path / result.entry.file).read_text(encoding="ascii").splitlines()
        assert lines[1:] == [
            "1512086400000,10.00000000,12.00000000,9.00000000,11.00000000,1.00000000,1512086459999",
            "1512367200000,11476.87000000,11478.00000000,11476.87000000,11478.00000000,"
            "0.28948500,1512367220798",
        ]
        assert result.entry.first_open_time_ms == DEC_1
        assert result.entry.last_open_time_ms == 1512367200000

    def test_the_result_names_the_entry_it_stored(self, tmp_path: Path) -> None:
        result = self.accepted_ingest(tmp_path, text_of(SHORT_1M))
        report = check_stored(tmp_path, "BTCUSDT", "1m")
        assert report.entries == {"2017-12": result.entry}
        assert report.problems == ()

    def test_a_month_in_which_every_row_is_quarantined_is_refused_and_stores_nothing(
        self, tmp_path: Path
    ) -> None:
        with pytest.raises(ArchiveFormatError, match="every row of the month was quarantined"):
            self.ingest(tmp_path, text_of(OFF_GRID_END_1M, OFF_GRID_SHORT_1M))
        assert list(tmp_path.iterdir()) == []

    def test_an_unknown_shape_inside_a_verified_zip_stores_nothing(self, tmp_path: Path) -> None:
        text = text_of(SHORT_1M, bar(DEC_10, DEC_10 + MINUTE + 5))
        with pytest.raises(ArchiveFormatError, match=r"line 2: .*no class"):
            self.ingest(tmp_path, text)
        assert list(tmp_path.iterdir()) == []

    def test_the_ingest_module_exposes_the_classification_names(self) -> None:
        for name in (
            "RowShape",
            "classify_times",
            "IrregularRow",
            "ClassifiedMonth",
            "IngestResult",
        ):
            assert name in hist.__all__
