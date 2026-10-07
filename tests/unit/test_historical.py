"""``data/historical.py``: ingest, verify, store and gap-find the venue's bulk archive.

The fixtures that matter are REAL. The 2024-12 rows are the archive's first and last
rows of ``BTCUSDT-1d-2024-12`` (milliseconds); the 2025-01 rows are those of
``BTCUSDT-1d-2025-01`` (microseconds), both read at P100 (``M5m-030``). The five 2017-08
rows are the venue's own bars for 2017-08-31T23:55 to 23:59 UTC, two of them consecutive
zero-volume minutes (``M5m-031``), read from the keyless REST endpoint, whose last bar
equals the archive's last row of that month on every field but the unused twelfth. The
checksum line is the real ``BTCUSDT-1m-2017-08.zip.CHECKSUM``.

Expected values are written from those fixtures and from literals, never from the
function under test, so a wrong unit or a wrong month boundary cannot agree with itself.
"""

from __future__ import annotations

import hashlib
import io
import json
import random
import zipfile
from pathlib import Path

import pytest

import trading_bot.data.historical as hist
from trading_bot.data.historical import (
    ArchiveFormatError,
    ChecksumMismatchError,
    Gap,
    ManifestError,
    Row,
    check_stored,
    find_gaps,
    grid_size,
    ingest_zip,
    month_bounds_ms,
    month_file,
    normalise_archive,
    parse_checksum,
    series_dir,
    verify_zip,
    write_month,
)

DEC_FIRST = (
    "1733011200000,96407.99000000,97836.00000000,95693.88000000,97185.18000000,"
    "16938.60452000,1733097599999,1641327626.60622060,3342200,8114.89569000,"
    "786489040.19363780,0"
)
DEC_LAST = (
    "1735603200000,92792.05000000,96250.00000000,92033.73000000,93576.00000000,"
    "19612.03389000,1735689599999,1845718801.92270400,3347847,9687.96775000,"
    "911716321.60540200,0"
)
JAN_FIRST = (
    "1735689600000000,93576.00000000,95151.15000000,92888.00000000,94591.79000000,"
    "10373.32613000,1735775999999999,975444194.13799830,1516556,5347.73648000,"
    "502914035.64059070,0"
)
JAN_LAST = (
    "1738281600000000,104722.94000000,106012.00000000,101560.00000000,102429.56000000,"
    "21983.18193000,1738367999999999,2282174002.19521760,4331904,10697.39968000,"
    "1111485874.12928450,0"
)
AUG_RUN = [
    "1504223700000,4699.00000000,4699.00000000,4699.00000000,4699.00000000,0.11844200,"
    "1504223759999,556.55895800,6,0.11844200,556.55895800,0",
    "1504223760000,4699.00000000,4699.00000000,4699.00000000,4699.00000000,0.00000000,"
    "1504223819999,0.00000000,0,0.00000000,0.00000000,0",
    "1504223820000,4699.00000000,4699.00000000,4699.00000000,4699.00000000,0.00000000,"
    "1504223879999,0.00000000,0,0.00000000,0.00000000,0",
    "1504223880000,4724.88000000,4724.89000000,4724.88000000,4724.89000000,0.90468100,"
    "1504223939999,4274.51370009,4,0.90468100,4274.51370009,0",
    "1504223940000,4724.89000000,4724.89000000,4724.89000000,4724.89000000,0.00000000,"
    "1504223999999,0.00000000,0,0.00000000,0.00000000,10779.83873125",
]
REAL_CHECKSUM = (
    "4f96569190147d64b7ce55f6760dc3e7962aeb3e209c969b200200e3d7045e70  BTCUSDT-1m-2017-08.zip"
)

DAY = 86_400_000
MINUTE = 60_000


def accepted(text: str, *, interval: str, month: str) -> tuple[Row, ...]:
    try:
        return normalise_archive(text, interval=interval, month=month).rows
    except ArchiveFormatError as exc:
        pytest.fail(f"a good archive was refused: {exc}")


def gaps_of(*args: object, **kwargs: object) -> tuple[Gap, ...]:
    try:
        return find_gaps(*args, **kwargs)
    except ValueError as exc:
        pytest.fail(f"a series on the grid was refused: {exc}")


def grid_of(start_ms: int, end_ms: int, interval_ms: int) -> int:
    try:
        return grid_size(start_ms, end_ms, interval_ms)
    except ValueError as exc:
        pytest.fail(f"a range of whole bars was refused: {exc}")


def text_of(*lines: str) -> str:
    return "\n".join(lines) + "\n"


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def zip_of(members: dict[str, bytes]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, payload in members.items():
            archive.writestr(name, payload)
    return buffer.getvalue()


def month_text(month: str, interval: str, *, microseconds: bool, count: int | None = None) -> str:
    start, end = month_bounds_ms(month)
    step = hist.INTERVAL_MS[interval]
    total = (end - start) // step if count is None else count
    scale = 1000 if microseconds else 1
    lines = []
    for index in range(total):
        opened = start + index * step
        closed = opened + step - 1
        close_field = closed * scale + (scale - 1)
        lines.append(
            f"{opened * scale},10.00000000,12.50000000,9.00000000,11.00000000,"
            f"1.00000000,{close_field},11.00000000,1,0.50000000,5.50000000,0"
        )
    return text_of(*lines)


def one_row(opened: int = 1735689600000, *, interval_ms: int = DAY) -> Row:
    return Row(
        opened,
        "10.00000000",
        "12.50000000",
        "9.00000000",
        "11.00000000",
        "1.00000000",
        opened + interval_ms - 1,
    )


class TestParseChecksum:
    def test_the_real_checksum_line_yields_its_digest(self) -> None:
        digest = parse_checksum(REAL_CHECKSUM, "BTCUSDT-1m-2017-08.zip")
        assert digest == "4f96569190147d64b7ce55f6760dc3e7962aeb3e209c969b200200e3d7045e70"

    def test_a_trailing_newline_is_tolerated(self) -> None:
        assert parse_checksum(REAL_CHECKSUM + "\n", "BTCUSDT-1m-2017-08.zip")

    def test_a_checksum_for_another_file_proves_nothing_and_is_refused(self) -> None:
        with pytest.raises(ArchiveFormatError, match="checksum is for"):
            parse_checksum(REAL_CHECKSUM, "BTCUSDT-1m-2017-09.zip")

    @pytest.mark.parametrize(
        "text",
        [
            "",
            "4f96",
            f"{'a' * 63}  BTCUSDT-1m-2017-08.zip",
            f"{'A' * 64}  BTCUSDT-1m-2017-08.zip",
            f"{'g' * 64}  BTCUSDT-1m-2017-08.zip",
            f"{'a' * 64}  BTCUSDT-1m-2017-08.zip extra",
        ],
    )
    def test_anything_but_a_digest_and_a_name_is_refused(self, text: str) -> None:
        with pytest.raises(ArchiveFormatError):
            parse_checksum(text, "BTCUSDT-1m-2017-08.zip")


class TestVerifyZip:
    def test_matching_bytes_pass(self) -> None:
        verify_zip(b"abc", sha(b"abc"))

    def test_a_single_changed_byte_is_refused_and_both_digests_are_named(self) -> None:
        with pytest.raises(ChecksumMismatchError) as raised:
            verify_zip(b"abd", sha(b"abc"))
        assert sha(b"abd") in str(raised.value)
        assert sha(b"abc") in str(raised.value)


class TestMonthBounds:
    @pytest.mark.parametrize(
        ("month", "start", "end"),
        [
            ("2017-08", 1501545600000, 1504224000000),
            ("2024-12", 1733011200000, 1735689600000),
            ("2025-01", 1735689600000, 1738368000000),
            ("2024-02", 1706745600000, 1709251200000),
        ],
    )
    def test_the_bounds_are_the_months_first_millisecond_and_the_next_months(
        self, month: str, start: int, end: int
    ) -> None:
        assert month_bounds_ms(month) == (start, end)

    def test_the_last_close_time_of_august_2017_is_the_last_millisecond_before_the_end(
        self,
    ) -> None:
        assert month_bounds_ms("2017-08")[1] - 1 == 1504223999999

    @pytest.mark.parametrize("month", ["2024-13", "2024-00", "2024-1", "24-01", "2024/01", ""])
    def test_a_malformed_month_is_refused(self, month: str) -> None:
        with pytest.raises(ArchiveFormatError, match="not a month"):
            month_bounds_ms(month)


class TestNormaliseRealRows:
    def test_millisecond_rows_from_2024_12_keep_their_strings_verbatim(self) -> None:
        rows = accepted(text_of(DEC_FIRST, DEC_LAST), interval="1d", month="2024-12")
        assert rows[0] == Row(
            1733011200000,
            "96407.99000000",
            "97836.00000000",
            "95693.88000000",
            "97185.18000000",
            "16938.60452000",
            1733097599999,
        )
        assert rows[1].open_time_ms == 1735603200000
        assert rows[1].close_time_ms == 1735689599999
        assert rows[1].low == "92033.73000000"

    def test_microsecond_rows_from_2025_01_become_exact_milliseconds(self) -> None:
        rows = accepted(text_of(JAN_FIRST, JAN_LAST), interval="1d", month="2025-01")
        assert rows[0].open_time_ms == 1735689600000
        assert rows[0].close_time_ms == 1735775999999
        assert rows[1].open_time_ms == 1738281600000
        assert rows[1].close_time_ms == 1738367999999
        assert rows[1].volume == "21983.18193000"

    def test_the_same_instant_in_either_unit_normalises_to_the_same_row(self) -> None:
        milliseconds = "1735603200000,1.0,2.0,0.5,1.5,3.0,1735689599999,0,0,0,0,0"
        microseconds = "1735603200000000,1.0,2.0,0.5,1.5,3.0,1735689599999999,0,0,0,0,0"
        a = accepted(text_of(milliseconds), interval="1d", month="2024-12")
        b = accepted(text_of(microseconds), interval="1d", month="2024-12")
        assert a == b

    def test_a_run_of_zero_volume_minutes_is_four_ordinary_bars_not_a_gap(self) -> None:
        rows = accepted(text_of(*AUG_RUN), interval="1m", month="2017-08")
        assert [row.volume for row in rows] == [
            "0.11844200",
            "0.00000000",
            "0.00000000",
            "0.90468100",
            "0.00000000",
        ]
        assert rows[1].open == rows[1].high == rows[1].low == rows[1].close == "4699.00000000"
        assert gaps_of([row.open_time_ms for row in rows], MINUTE) == ()

    def test_the_archives_own_last_row_of_2017_08_is_accepted_whatever_its_twelfth_field_holds(
        self,
    ) -> None:
        line = AUG_RUN[-1].rsplit(",", 1)[0] + ",10779.83873125"
        (row,) = accepted(text_of(line), interval="1m", month="2017-08")
        assert row.close_time_ms == 1504223999999

    def test_only_seven_columns_are_kept(self) -> None:
        (row,) = accepted(text_of(DEC_FIRST), interval="1d", month="2024-12")
        assert tuple(vars(row)) == (
            "open_time_ms",
            "open",
            "high",
            "low",
            "close",
            "volume",
            "close_time_ms",
        )

    def test_prices_are_strings_and_not_floats(self) -> None:
        (row,) = accepted(text_of(DEC_FIRST), interval="1d", month="2024-12")
        for value in (row.open, row.high, row.low, row.close, row.volume):
            assert type(value) is str
        assert type(row.open_time_ms) is int


class TestTimeUnit:
    def row(self, opened: str, closed: str) -> str:
        return f"{opened},1.0,2.0,0.5,1.5,3.0,{closed},0,0,0,0,0"

    @pytest.mark.parametrize("digits", [12, 14, 15, 17, 18])
    def test_an_open_time_that_is_neither_13_nor_16_digits_is_refused(self, digits: int) -> None:
        opened = "1" + "0" * (digits - 1)
        closed = "1" + "0" * (digits - 1)
        with pytest.raises(ArchiveFormatError, match="neither 13"):
            normalise_archive(text_of(self.row(opened, closed)), interval="1d", month="2024-12")

    @pytest.mark.parametrize("opened", ["abcdefghijklm", "1733011200.00", "-733011200000", ""])
    def test_an_open_time_that_is_not_an_integer_is_refused(self, opened: str) -> None:
        with pytest.raises(ArchiveFormatError):
            normalise_archive(
                text_of(self.row(opened, "1733097599999")), interval="1d", month="2024-12"
            )

    def test_a_microsecond_open_time_must_be_a_whole_millisecond(self) -> None:
        line = self.row("1733011200000001", "1733097599999999")
        with pytest.raises(ArchiveFormatError, match="whole millisecond"):
            normalise_archive(text_of(line), interval="1d", month="2024-12")

    def test_a_close_time_in_the_other_unit_is_refused(self) -> None:
        line = self.row("1733011200000", "1733097599999999")
        with pytest.raises(ArchiveFormatError, match="different units"):
            normalise_archive(text_of(line), interval="1d", month="2024-12")

    @pytest.mark.parametrize("offset", [2, 1000, 86_400_000])
    def test_a_millisecond_close_time_past_the_bars_end_is_refused(self, offset: int) -> None:
        line = self.row("1733011200000", str(1733097599999 + offset))
        with pytest.raises(ArchiveFormatError, match="is not open_time"):
            normalise_archive(text_of(line), interval="1d", month="2024-12")

    @pytest.mark.parametrize("offset", [2000, 3000])
    def test_a_microsecond_close_time_past_the_bars_end_is_refused(self, offset: int) -> None:
        line = self.row("1735689600000000", str(1735775999999999 + offset))
        with pytest.raises(ArchiveFormatError, match="is not open_time"):
            normalise_archive(text_of(line), interval="1d", month="2025-01")

    def test_a_microsecond_close_time_is_floored_not_rounded(self) -> None:
        for closed in ("1735775999999000", "1735775999999500", "1735775999999999"):
            line = self.row("1735689600000000", closed)
            (row,) = accepted(text_of(line), interval="1d", month="2025-01")
            assert row.close_time_ms == 1735775999999

    def test_a_row_is_checked_against_the_interval_it_is_stored_under(self) -> None:
        with pytest.raises(ArchiveFormatError, match="is not open_time"):
            normalise_archive(text_of(DEC_FIRST), interval="1h", month="2024-12")

    def test_the_boundary_between_the_two_units_is_the_boundary_between_the_two_files(self) -> None:
        december = accepted(text_of(DEC_LAST), interval="1d", month="2024-12")
        january = accepted(text_of(JAN_FIRST), interval="1d", month="2025-01")
        assert january[0].open_time_ms - december[0].open_time_ms == DAY


class TestArchiveShape:
    def test_eleven_and_thirteen_fields_are_refused(self) -> None:
        for line in (DEC_FIRST.rsplit(",", 1)[0], DEC_FIRST + ",0"):
            with pytest.raises(ArchiveFormatError, match="fields"):
                normalise_archive(text_of(line), interval="1d", month="2024-12")

    def test_a_header_row_is_refused_at_line_one(self) -> None:
        header = "open_time,open,high,low,close,volume,close_time,q,n,b,t,i"
        with pytest.raises(ArchiveFormatError, match="line 1"):
            normalise_archive(text_of(header, DEC_FIRST), interval="1d", month="2024-12")

    def test_the_line_number_of_a_bad_row_is_named(self) -> None:
        with pytest.raises(ArchiveFormatError, match="line 2"):
            normalise_archive(text_of(DEC_FIRST, "garbage"), interval="1d", month="2024-12")

    @pytest.mark.parametrize(
        "value", ["abc", "-1.0", "1e5", "NaN", "Infinity", "", "1.", ".5", "1,5"]
    )
    def test_a_price_or_volume_that_is_not_a_plain_non_negative_number_is_refused(
        self, value: str
    ) -> None:
        line = DEC_FIRST.replace("96407.99000000", value, 1)
        with pytest.raises(ArchiveFormatError):
            normalise_archive(text_of(line), interval="1d", month="2024-12")

    @pytest.mark.parametrize("value", ["5", "0", "0.00000000", "1234567.12345678"])
    def test_plain_numbers_pass_unchanged(self, value: str) -> None:
        line = DEC_FIRST.replace("16938.60452000", value, 1)
        (row,) = accepted(text_of(line), interval="1d", month="2024-12")
        assert row.volume == value

    def test_a_repeated_open_time_is_refused(self) -> None:
        with pytest.raises(ArchiveFormatError, match="does not increase"):
            normalise_archive(text_of(DEC_FIRST, DEC_FIRST), interval="1d", month="2024-12")

    def test_a_decreasing_open_time_is_refused(self) -> None:
        with pytest.raises(ArchiveFormatError, match="does not increase"):
            normalise_archive(text_of(DEC_LAST, DEC_FIRST), interval="1d", month="2024-12")

    def test_a_bar_from_the_next_month_is_refused(self) -> None:
        january_first = "1735689600000,1.0,2.0,0.5,1.5,3.0,1735775999999,0,0,0,0,0"
        with pytest.raises(ArchiveFormatError, match="outside 2024-12"):
            normalise_archive(text_of(DEC_FIRST, january_first), interval="1d", month="2024-12")

    def test_a_bar_from_the_previous_month_is_refused(self) -> None:
        with pytest.raises(ArchiveFormatError, match="outside 2025-01"):
            normalise_archive(text_of(DEC_LAST), interval="1d", month="2025-01")

    def test_an_empty_archive_is_refused(self) -> None:
        with pytest.raises(ArchiveFormatError, match="no rows"):
            normalise_archive("", interval="1d", month="2024-12")

    def test_carriage_returns_at_line_ends_are_tolerated(self) -> None:
        rows = accepted(DEC_FIRST + "\r\n" + DEC_LAST + "\r\n", interval="1d", month="2024-12")
        assert len(rows) == 2

    def test_an_unknown_interval_is_refused(self) -> None:
        with pytest.raises(ArchiveFormatError, match="interval"):
            normalise_archive(text_of(DEC_FIRST), interval="2m", month="2024-12")


class TestGrid:
    def test_a_day_of_minutes_is_1440_bars(self) -> None:
        assert grid_of(0, DAY, MINUTE) == 1440

    def test_the_full_btcusdt_minute_series_to_2026_10_01_is_the_predicted_4797840(self) -> None:
        first = 1502942400000
        end = 1790812800000
        assert grid_of(first, end, MINUTE) == 4_797_840

    @pytest.mark.parametrize(("start", "end"), [(0, 90_000), (60_000, 0)])
    def test_a_range_that_is_not_whole_bars_or_runs_backwards_is_refused(
        self, start: int, end: int
    ) -> None:
        with pytest.raises(ValueError, match="whole number"):
            grid_size(start, end, MINUTE)

    def test_a_range_offset_from_zero_is_still_counted_in_whole_bars(self) -> None:
        assert grid_of(1, 60_001, MINUTE) == 1


class TestFindGaps:
    def test_a_contiguous_series_has_none(self) -> None:
        assert gaps_of([0, MINUTE, 2 * MINUTE, 3 * MINUTE], MINUTE) == ()

    def test_one_missing_bar_is_one_gap_of_one(self) -> None:
        assert gaps_of([0, MINUTE, 3 * MINUTE], MINUTE) == (Gap(2 * MINUTE, 3 * MINUTE, 1),)

    def test_a_run_of_missing_bars_is_one_gap_with_its_count(self) -> None:
        assert gaps_of([0, 5 * MINUTE], MINUTE) == (Gap(MINUTE, 5 * MINUTE, 4),)

    def test_several_gaps_come_back_in_order(self) -> None:
        series = [0, 3 * MINUTE, 4 * MINUTE, 9 * MINUTE]
        assert gaps_of(series, MINUTE) == (
            Gap(MINUTE, 3 * MINUTE, 2),
            Gap(5 * MINUTE, 9 * MINUTE, 4),
        )

    def test_a_leading_edge_run_is_a_gap_when_the_range_starts_earlier(self) -> None:
        assert gaps_of([2 * MINUTE, 3 * MINUTE], MINUTE, start_ms=0) == (Gap(0, 2 * MINUTE, 2),)

    def test_a_trailing_edge_run_is_a_gap_when_the_range_ends_later(self) -> None:
        got = gaps_of([0, MINUTE, 4 * MINUTE], MINUTE, end_ms=10 * MINUTE)
        assert got == (Gap(2 * MINUTE, 4 * MINUTE, 2), Gap(5 * MINUTE, 10 * MINUTE, 5))

    def test_a_range_that_the_series_exactly_fills_has_no_edge_gap(self) -> None:
        assert gaps_of([0, MINUTE], MINUTE, start_ms=0, end_ms=2 * MINUTE) == ()

    def test_an_empty_series_over_a_range_is_one_gap_of_the_whole_grid(self) -> None:
        assert gaps_of([], MINUTE, start_ms=0, end_ms=5 * MINUTE) == (Gap(0, 5 * MINUTE, 5),)

    def test_an_empty_series_with_no_range_has_nothing_to_report(self) -> None:
        assert gaps_of([], MINUTE) == ()
        assert gaps_of([], MINUTE, start_ms=0) == ()
        assert gaps_of([], MINUTE, start_ms=MINUTE, end_ms=MINUTE) == ()

    def test_rows_plus_missing_bars_equal_the_grid_exactly(self) -> None:
        generator = random.Random(20261007)
        for _ in range(300):
            total = generator.randint(1, 60)
            kept = sorted(generator.sample(range(total), generator.randint(1, total)))
            times = [index * MINUTE for index in kept]
            gaps = gaps_of(times, MINUTE, start_ms=0, end_ms=total * MINUTE)
            assert len(times) + sum(gap.missing for gap in gaps) == grid_of(
                0, total * MINUTE, MINUTE
            )

    def test_a_gap_spans_exactly_its_missing_bars(self) -> None:
        for gap in gaps_of([0, 7 * MINUTE, 8 * MINUTE, 20 * MINUTE], MINUTE):
            assert gap.end_ms - gap.start_ms == gap.missing * MINUTE

    def test_a_repeated_open_time_is_not_a_gap_it_is_a_refusal(self) -> None:
        with pytest.raises(ValueError, match="do not increase"):
            find_gaps([0, MINUTE, MINUTE], MINUTE)

    def test_a_decreasing_series_is_a_refusal(self) -> None:
        with pytest.raises(ValueError, match="do not increase"):
            find_gaps([MINUTE, 0], MINUTE)

    def test_an_off_grid_spacing_is_a_refusal_not_a_rounded_gap(self) -> None:
        with pytest.raises(ValueError, match="whole number"):
            find_gaps([0, 90_000], MINUTE)

    def test_a_bar_before_the_range_starts_is_a_refusal(self) -> None:
        with pytest.raises(ValueError, match="before the range starts"):
            find_gaps([MINUTE], MINUTE, start_ms=2 * MINUTE)

    def test_a_bar_one_interval_before_the_start_is_still_before_it(self) -> None:
        with pytest.raises(ValueError, match="before the range starts"):
            find_gaps([0], MINUTE, start_ms=MINUTE)

    def test_a_bar_beyond_the_end_is_a_refusal(self) -> None:
        with pytest.raises(ValueError, match="beyond the range"):
            find_gaps([0, MINUTE], MINUTE, end_ms=MINUTE)

    def test_a_misaligned_start_or_end_is_a_refusal(self) -> None:
        with pytest.raises(ValueError, match="whole number"):
            find_gaps([MINUTE], MINUTE, start_ms=1)
        with pytest.raises(ValueError, match="whole number"):
            find_gaps([0], MINUTE, end_ms=MINUTE + 1)


class TestLayoutAndValidation:
    def test_the_layout_is_symbol_then_interval_then_a_file_named_for_the_month(
        self, tmp_path: Path
    ) -> None:
        assert series_dir(tmp_path, "BTCUSDT", "1m") == tmp_path / "BTCUSDT" / "1m"
        assert month_file(tmp_path, "BTCUSDT", "1m", "2017-08") == (
            tmp_path / "BTCUSDT" / "1m" / "BTCUSDT-1m-2017-08.csv"
        )

    @pytest.mark.parametrize("symbol", ["../x", "btcusdt", "BTC", "BTC/USDT", "", "A" * 21])
    def test_a_symbol_that_could_leave_the_directory_is_refused_and_nothing_is_created(
        self, tmp_path: Path, symbol: str
    ) -> None:
        with pytest.raises(ArchiveFormatError, match="symbol"):
            write_month(
                tmp_path, symbol, "1d", "2025-01", [one_row()], source_url="u", zip_sha256="0" * 64
            )
        assert list(tmp_path.iterdir()) == []

    @pytest.mark.parametrize(
        ("interval", "month"), [("2m", "2025-01"), ("1d", "2025-13"), ("1d", "../2025")]
    )
    def test_an_unknown_interval_or_month_is_refused_and_nothing_is_created(
        self, tmp_path: Path, interval: str, month: str
    ) -> None:
        with pytest.raises(ArchiveFormatError):
            write_month(
                tmp_path,
                "BTCUSDT",
                interval,
                month,
                [one_row()],
                source_url="u",
                zip_sha256="0" * 64,
            )
        assert list(tmp_path.iterdir()) == []


class TestWriteMonth:
    def write(
        self, root: Path, month: str = "2025-01", rows: list[Row] | None = None
    ) -> hist.ManifestEntry:
        return write_month(
            root,
            "BTCUSDT",
            "1d",
            month,
            rows or [one_row()],
            source_url="https://example.invalid/x.zip",
            zip_sha256="a" * 64,
        )

    def test_the_file_holds_a_header_then_one_line_per_row_with_lf_endings(
        self, tmp_path: Path
    ) -> None:
        rows = [one_row(1735689600000), one_row(1735776000000)]
        self.write(tmp_path, rows=rows)
        data = (tmp_path / "BTCUSDT" / "1d" / "BTCUSDT-1d-2025-01.csv").read_bytes()
        assert b"\r" not in data
        assert data.decode("ascii") == (
            "open_time_ms,open,high,low,close,volume,close_time_ms\n"
            "1735689600000,10.00000000,12.50000000,9.00000000,11.00000000,1.00000000,1735775999999\n"
            "1735776000000,10.00000000,12.50000000,9.00000000,11.00000000,1.00000000,1735862399999\n"
        )

    def test_the_venues_strings_survive_with_their_trailing_zeros(self, tmp_path: Path) -> None:
        rows = accepted(text_of(DEC_FIRST), interval="1d", month="2024-12")
        write_month(tmp_path, "BTCUSDT", "1d", "2024-12", rows, source_url="u", zip_sha256="b" * 64)
        text = (tmp_path / "BTCUSDT" / "1d" / "BTCUSDT-1d-2024-12.csv").read_text(encoding="ascii")
        assert "96407.99000000,97836.00000000,95693.88000000,97185.18000000,16938.60452000" in text

    def test_the_manifest_entry_describes_the_file(self, tmp_path: Path) -> None:
        entry = self.write(tmp_path, rows=[one_row(1735689600000), one_row(1735776000000)])
        data = (tmp_path / entry.file).read_bytes()
        assert entry.file == "BTCUSDT/1d/BTCUSDT-1d-2025-01.csv"
        assert entry.rows == 2
        assert entry.first_open_time_ms == 1735689600000
        assert entry.last_open_time_ms == 1735776000000
        assert entry.csv_sha256 == sha(data)
        assert entry.zip_sha256 == "a" * 64
        assert entry.source_url == "https://example.invalid/x.zip"

    def test_the_manifest_has_one_sorted_compact_line_per_month(self, tmp_path: Path) -> None:
        self.write(tmp_path, "2025-02", [one_row(1738368000000)])
        self.write(tmp_path, "2025-01")
        lines = (
            (tmp_path / "BTCUSDT" / "1d" / "MANIFEST.jsonl")
            .read_text(encoding="utf-8")
            .splitlines()
        )
        assert [json.loads(line)["month"] for line in lines] == ["2025-01", "2025-02"]
        assert all(" " not in line for line in lines)
        assert list(json.loads(lines[0])) == sorted(json.loads(lines[0]))

    def test_storing_a_month_again_replaces_its_line_and_adds_none(self, tmp_path: Path) -> None:
        self.write(tmp_path)
        self.write(tmp_path)
        lines = (
            (tmp_path / "BTCUSDT" / "1d" / "MANIFEST.jsonl")
            .read_text(encoding="utf-8")
            .splitlines()
        )
        assert len(lines) == 1

    def test_no_temporary_file_is_left_behind(self, tmp_path: Path) -> None:
        self.write(tmp_path)
        names = sorted(path.name for path in (tmp_path / "BTCUSDT" / "1d").iterdir())
        assert names == ["BTCUSDT-1d-2025-01.csv", "MANIFEST.jsonl"]

    def test_nothing_is_written_for_no_rows(self, tmp_path: Path) -> None:
        with pytest.raises(ArchiveFormatError, match="nothing to store"):
            write_month(
                tmp_path, "BTCUSDT", "1d", "2025-01", [], source_url="u", zip_sha256="a" * 64
            )
        assert list(tmp_path.iterdir()) == []

    def test_a_failed_rename_leaves_no_file_no_temporary_and_no_manifest(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def refuse(source: object, destination: object) -> None:
            raise OSError("power cut")

        monkeypatch.setattr(hist.os, "replace", refuse)
        with pytest.raises(OSError, match="power cut"):
            self.write(tmp_path)
        assert [path.name for path in (tmp_path / "BTCUSDT" / "1d").iterdir()] == []

    def test_a_power_cut_between_the_rename_and_the_manifest_lists_nothing_and_the_rerun_repairs_it(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def refuse(path: Path, entry: object) -> None:
            raise OSError("power cut")

        with monkeypatch.context() as patch:
            patch.setattr(hist, "_record", refuse)
            with pytest.raises(OSError, match="power cut"):
                self.write(tmp_path)
        report = check_stored(tmp_path, "BTCUSDT", "1d")
        assert report.entries == {}
        assert [problem.kind for problem in report.problems] == ["unlisted_file"]
        self.write(tmp_path)
        clean = check_stored(tmp_path, "BTCUSDT", "1d")
        assert list(clean.entries) == ["2025-01"]
        assert clean.problems == ()

    def test_an_unreadable_manifest_is_not_extended_and_is_left_exactly_as_it_was(
        self, tmp_path: Path
    ) -> None:
        directory = tmp_path / "BTCUSDT" / "1d"
        directory.mkdir(parents=True)
        manifest = directory / "MANIFEST.jsonl"
        manifest.write_bytes(b'{"month": "2024-12"\n')
        before = manifest.read_bytes()
        with pytest.raises(ManifestError):
            self.write(tmp_path)
        assert manifest.read_bytes() == before


class TestCheckStored:
    def stored(self, root: Path) -> hist.ManifestEntry:
        return write_month(
            root,
            "BTCUSDT",
            "1d",
            "2025-01",
            [one_row(1735689600000), one_row(1735776000000)],
            source_url="u",
            zip_sha256="c" * 64,
        )

    def manifest_path(self, root: Path) -> Path:
        return root / "BTCUSDT" / "1d" / "MANIFEST.jsonl"

    def edit_manifest(self, root: Path, **changes: object) -> None:
        path = self.manifest_path(root)
        record = json.loads(path.read_text(encoding="utf-8"))
        record.update(changes)
        path.write_text(json.dumps(record) + "\n", encoding="utf-8")

    def test_a_clean_series_verifies_with_no_problem(self, tmp_path: Path) -> None:
        entry = self.stored(tmp_path)
        report = check_stored(tmp_path, "BTCUSDT", "1d")
        assert report.entries == {"2025-01": entry}
        assert report.problems == ()

    def test_a_series_never_stored_is_empty_and_clean(self, tmp_path: Path) -> None:
        report = check_stored(tmp_path, "BTCUSDT", "1d")
        assert report.entries == {}
        assert report.problems == ()

    def test_a_deleted_file_is_a_problem_and_the_month_is_not_verified(
        self, tmp_path: Path
    ) -> None:
        entry = self.stored(tmp_path)
        (tmp_path / entry.file).unlink()
        report = check_stored(tmp_path, "BTCUSDT", "1d")
        assert report.entries == {}
        assert [(p.kind, p.month) for p in report.problems] == [("missing_file", "2025-01")]

    def test_one_changed_byte_is_a_hash_mismatch(self, tmp_path: Path) -> None:
        entry = self.stored(tmp_path)
        path = tmp_path / entry.file
        data = bytearray(path.read_bytes())
        data[-5] = ord("9") if data[-5] != ord("9") else ord("8")
        path.write_bytes(bytes(data))
        report = check_stored(tmp_path, "BTCUSDT", "1d")
        assert report.entries == {}
        assert [p.kind for p in report.problems] == ["hash_mismatch"]

    def test_a_manifest_that_misstates_the_row_count_is_a_bounds_mismatch(
        self, tmp_path: Path
    ) -> None:
        self.stored(tmp_path)
        self.edit_manifest(tmp_path, rows=3)
        report = check_stored(tmp_path, "BTCUSDT", "1d")
        assert [p.kind for p in report.problems] == ["bounds_mismatch"]
        assert report.entries == {}

    def test_a_manifest_that_misstates_the_last_open_time_is_a_bounds_mismatch(
        self, tmp_path: Path
    ) -> None:
        self.stored(tmp_path)
        self.edit_manifest(tmp_path, last_open_time_ms=1)
        assert [p.kind for p in check_stored(tmp_path, "BTCUSDT", "1d").problems] == [
            "bounds_mismatch"
        ]

    def test_a_file_whose_header_was_removed_is_a_bad_shape_even_with_a_matching_hash(
        self, tmp_path: Path
    ) -> None:
        entry = self.stored(tmp_path)
        path = tmp_path / entry.file
        body = path.read_bytes().split(b"\n", 1)[1]
        path.write_bytes(body)
        self.edit_manifest(tmp_path, csv_sha256=sha(body))
        assert [p.kind for p in check_stored(tmp_path, "BTCUSDT", "1d").problems] == ["bad_shape"]

    def test_a_csv_with_no_manifest_line_is_reported_as_unlisted(self, tmp_path: Path) -> None:
        entry = self.stored(tmp_path)
        self.manifest_path(tmp_path).unlink()
        report = check_stored(tmp_path, "BTCUSDT", "1d")
        assert report.entries == {}
        assert [(p.kind, p.detail) for p in report.problems] == [
            ("unlisted_file", Path(entry.file).name)
        ]

    @pytest.mark.parametrize(
        "changes",
        [
            {"file": "../../etc/passwd"},
            {"file": "BTCUSDT/1d/other.csv"},
            {"symbol": "ETHUSDT"},
            {"month": "2025-13"},
            {"interval": "9z"},
            {"rows": "2"},
            {"rows": True},
            {"zip_sha256": 5},
        ],
    )
    def test_a_manifest_line_that_names_another_path_or_has_the_wrong_types_is_refused(
        self, tmp_path: Path, changes: dict[str, object]
    ) -> None:
        self.stored(tmp_path)
        self.edit_manifest(tmp_path, **changes)
        report = check_stored(tmp_path, "BTCUSDT", "1d")
        assert report.entries == {}
        assert "bad_manifest_line" in {p.kind for p in report.problems}

    def test_an_extra_or_missing_field_in_a_manifest_line_is_refused(self, tmp_path: Path) -> None:
        self.stored(tmp_path)
        path = self.manifest_path(tmp_path)
        record = json.loads(path.read_text(encoding="utf-8"))
        del record["rows"]
        path.write_text(json.dumps(record) + "\n", encoding="utf-8")
        assert "bad_manifest_line" in {
            p.kind for p in check_stored(tmp_path, "BTCUSDT", "1d").problems
        }

    def test_a_repeated_month_line_is_reported(self, tmp_path: Path) -> None:
        self.stored(tmp_path)
        path = self.manifest_path(tmp_path)
        line = path.read_text(encoding="utf-8")
        path.write_text(line + line, encoding="utf-8")
        assert "duplicate_month" in {
            p.kind for p in check_stored(tmp_path, "BTCUSDT", "1d").problems
        }

    def test_a_stray_temporary_file_is_not_reported_as_unlisted(self, tmp_path: Path) -> None:
        entry = self.stored(tmp_path)
        (tmp_path / entry.file).with_name(".stray.csv.tmp").write_bytes(b"x")
        assert check_stored(tmp_path, "BTCUSDT", "1d").problems == ()


class TestIngestZip:
    def archive(self, month: str = "2025-01", *, microseconds: bool = True) -> tuple[bytes, str]:
        csv = month_text(month, "1d", microseconds=microseconds).encode("utf-8")
        data = zip_of({f"BTCUSDT-1d-{month}.csv": csv})
        return data, sha(data)

    def ingest(
        self, root: Path, data: bytes, expected: str, month: str = "2025-01"
    ) -> hist.ManifestEntry:
        return ingest_zip(
            data,
            expected_sha256=expected,
            root=root,
            symbol="BTCUSDT",
            interval="1d",
            month=month,
            source_url="https://data.binance.vision/x.zip",
        ).entry

    def accepted_ingest(
        self, root: Path, data: bytes, expected: str, month: str = "2025-01"
    ) -> hist.ManifestEntry:
        try:
            return self.ingest(root, data, expected, month)
        except hist.HistoricalDataError as exc:
            pytest.fail(f"a good archive was refused: {exc}")

    def test_a_good_microsecond_month_is_stored_in_milliseconds(self, tmp_path: Path) -> None:
        data, digest = self.archive()
        entry = self.accepted_ingest(tmp_path, data, digest)
        assert entry.rows == 31
        assert entry.first_open_time_ms == 1735689600000
        assert entry.last_open_time_ms == 1738281600000
        assert entry.zip_sha256 == digest
        assert entry.source_url == "https://data.binance.vision/x.zip"
        first = (tmp_path / entry.file).read_text(encoding="ascii").splitlines()[1]
        assert first.startswith("1735689600000,10.00000000,")
        assert first.endswith(",1735775999999")

    def test_a_good_millisecond_month_is_stored_the_same_way(self, tmp_path: Path) -> None:
        data, digest = self.archive("2024-12", microseconds=False)
        entry = self.accepted_ingest(tmp_path, data, digest, "2024-12")
        assert (entry.rows, entry.first_open_time_ms) == (31, 1733011200000)

    def test_a_wrong_checksum_stores_nothing_at_all(self, tmp_path: Path) -> None:
        data, _ = self.archive()
        with pytest.raises(ChecksumMismatchError):
            self.ingest(tmp_path, data, "0" * 64)
        assert list(tmp_path.iterdir()) == []

    def test_the_checksum_is_verified_before_anything_is_parsed(self, tmp_path: Path) -> None:
        not_a_zip = b"this is not a zip file"
        with pytest.raises(ChecksumMismatchError):
            self.ingest(tmp_path, not_a_zip, "0" * 64)
        with pytest.raises(ArchiveFormatError, match="not a zip"):
            self.ingest(tmp_path, not_a_zip, sha(not_a_zip))
        assert list(tmp_path.iterdir()) == []

    @pytest.mark.parametrize(
        "members",
        [
            {},
            {"BTCUSDT-1d-2025-02.csv": b"x"},
            {"BTCUSDT-1d-2025-01.csv": b"x", "extra.csv": b"y"},
            {"../BTCUSDT-1d-2025-01.csv": b"x"},
        ],
    )
    def test_a_zip_without_exactly_the_named_member_is_refused(
        self, tmp_path: Path, members: dict[str, bytes]
    ) -> None:
        data = zip_of(members)
        with pytest.raises(ArchiveFormatError, match="expected the one member"):
            self.ingest(tmp_path, data, sha(data))
        assert list(tmp_path.iterdir()) == []

    def test_a_member_that_is_not_utf8_is_refused(self, tmp_path: Path) -> None:
        data = zip_of({"BTCUSDT-1d-2025-01.csv": b"\xff\xfe\x00"})
        with pytest.raises(ArchiveFormatError, match="not UTF-8"):
            self.ingest(tmp_path, data, sha(data))

    def test_a_member_that_unpacks_past_the_cap_is_refused(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        data, digest = self.archive()
        monkeypatch.setattr(hist, "_MAX_MEMBER_BYTES", 100)
        with pytest.raises(ArchiveFormatError, match="unpacks past"):
            self.ingest(tmp_path, data, digest)
        assert list(tmp_path.iterdir()) == []

    def test_a_bad_row_inside_a_verified_zip_stores_nothing(self, tmp_path: Path) -> None:
        text = month_text("2025-01", "1d", microseconds=True).replace("11.00000000", "oops", 1)
        data = zip_of({"BTCUSDT-1d-2025-01.csv": text.encode("utf-8")})
        with pytest.raises(ArchiveFormatError, match="line 1"):
            self.ingest(tmp_path, data, sha(data))
        assert list(tmp_path.iterdir()) == []

    def test_a_month_file_named_for_another_month_is_refused_by_its_own_timestamps(
        self, tmp_path: Path
    ) -> None:
        text = month_text("2025-02", "1d", microseconds=True)
        data = zip_of({"BTCUSDT-1d-2025-01.csv": text.encode("utf-8")})
        with pytest.raises(ArchiveFormatError, match="outside 2025-01"):
            self.ingest(tmp_path, data, sha(data))

    def test_the_stored_month_verifies_clean_afterwards(self, tmp_path: Path) -> None:
        data, digest = self.archive()
        self.accepted_ingest(tmp_path, data, digest)
        report = check_stored(tmp_path, "BTCUSDT", "1d")
        assert list(report.entries) == ["2025-01"]
        assert report.problems == ()
