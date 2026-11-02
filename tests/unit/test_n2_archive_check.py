"""``scripts/n2_archive_check.py``: the saved evidence, the three reports and what is printed.

No test touches the network (the script has no fetcher) or the real store. The venue's bars are
JSON pages written into ``tmp_path`` beside a ``responses.sha256``, and every store is a few real
month files written with ``write_month``. Expected figures are literals, or are computed here from
the stored literals, never by the code under test.
"""

from __future__ import annotations

import hashlib
import inspect
import io
import json
import re
import sys
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

import n2_archive_check as chk
import n2_verify_bars as n2

from trading_bot.data.historical import HistoricalStore, Row, month_file, write_month

UTC = timezone.utc
EPOCH = datetime(1970, 1, 1, tzinfo=UTC)
MINUTE = timedelta(minutes=1)
SOURCE = {"source_url": "https://example.invalid/m.zip", "zip_sha256": "0" * 64}
WIDTH = {"1d": 86_400_000, "4h": 14_400_000}
DAY = datetime(2017, 9, 1, tzinfo=UTC)


def at(year: int, month: int, day: int, hour: int = 0) -> datetime:
    return datetime(year, month, day, hour, tzinfo=UTC)


def ms(moment: datetime) -> int:
    return (moment - EPOCH) // timedelta(milliseconds=1)


def minute_rows(
    day: datetime,
    *,
    filler_first: bool = False,
    skip: frozenset[int] = frozenset(),
    last_volume: str | None = None,
) -> list[Row]:
    """1440 minutes: minute i opens 1000 + i, holds volume 2 and is a zero-volume filler if asked."""
    rows: list[Row] = []
    for i in range(1440):
        if i in skip:
            continue
        opened = ms(day) + i * 60_000
        if filler_first and i == 0:
            figures = ["999.00000000"] * 4 + ["0.00000000"]
        else:
            volume = last_volume if (last_volume is not None and i == 1439) else "2.00000000"
            figures = [
                f"{1000 + i}.00000000",
                f"{2000 + i}.00000000",
                f"{500 + i}.00000000",
                f"{1500 + i}.00000000",
                volume,
            ]
        rows.append(Row(opened, *figures, opened + 59_999))
    return rows


def put(root: Path, symbol: str, interval: str, rows: list[Row]) -> None:
    months: dict[str, list[Row]] = {}
    for row in rows:
        moment = EPOCH + timedelta(milliseconds=row.open_time_ms)
        months.setdefault(f"{moment.year:04d}-{moment.month:02d}", []).append(row)
    for month, found in months.items():
        write_month(root, symbol, interval, month, found, **SOURCE)


def figs(first: int, last: int, traded: int) -> list[str]:
    return [
        f"{1000 + first}.00000000",
        f"{2000 + last}.00000000",
        f"{500 + first}.00000000",
        f"{1500 + last}.00000000",
        f"{2 * traded}.00000000",
    ]


def day_figures(timeframe: str, k: int = 0, *, filler_first: bool = False) -> list[str]:
    if timeframe == "1d":
        return figs(1, 1439, 1439) if filler_first else figs(0, 1439, 1440)
    first = 240 * k + (1 if (filler_first and k == 0) else 0)
    return figs(first, 240 * k + 239, 240 - (1 if (filler_first and k == 0) else 0))


def venue_rows(timeframe: str, *, filler_first: bool = False) -> list[list[object]]:
    count = 1 if timeframe == "1d" else 6
    base = ms(DAY)
    return [
        [
            base + k * WIDTH[timeframe],
            *day_figures(timeframe, k, filler_first=filler_first),
            base + (k + 1) * WIDTH[timeframe] - 1,
            "1.0",
            1,
            "1.0",
            "1.0",
            "0",
        ]
        for k in range(count)
    ]


def archive_rows(timeframe: str, *, filler_first: bool = False) -> list[Row]:
    return [
        Row(row[0], *row[1:6], row[6]) for row in venue_rows(timeframe, filler_first=filler_first)
    ]


def write_responses(directory: Path, series: dict[tuple[str, str], list[list[object]]]) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    lines: list[str] = []
    for (symbol, timeframe), rows in series.items():
        body = json.dumps(rows).encode("ascii")
        name = f"{symbol}-{timeframe}-001.json"
        (directory / name).write_bytes(body)
        lines.append(f"{hashlib.sha256(body).hexdigest()}  {name}")
    (directory / "responses.sha256").write_text("\n".join(lines) + "\n", encoding="ascii")
    return directory


def stage(
    tmp_path: Path,
    *,
    filler_first: bool = False,
    api: dict[str, list[list[object]]] | None = None,
    archive: dict[str, list[Row]] | None = None,
    one_minute: list[Row] | None = None,
) -> tuple[HistoricalStore, Path]:
    root = tmp_path / "store"
    put(root, "BTCUSDT", "1m", one_minute or minute_rows(DAY, filler_first=filler_first))
    for timeframe in ("1d", "4h"):
        found = (archive or {}).get(timeframe, archive_rows(timeframe, filler_first=filler_first))
        put(root, "BTCUSDT", timeframe, found)
    series = {
        ("BTCUSDT", timeframe): (api or {}).get(
            timeframe, venue_rows(timeframe, filler_first=filler_first)
        )
        for timeframe in ("1d", "4h")
    }
    return HistoricalStore(root), write_responses(tmp_path / "responses", series)


def go(store: HistoricalStore, responses: Path) -> chk.Report:
    return chk.run_check(store, responses, ("BTCUSDT",))


def result(
    report: chk.Report, timeframe: str
) -> tuple[chk.ArchiveResult, chk.ConsistencyResult, chk.VolumeResult]:
    (a,) = [r for r in report.archive if r.timeframe == timeframe]
    (b,) = [r for r in report.consistency if r.timeframe == timeframe]
    (c,) = [r for r in report.volume if r.timeframe == timeframe]
    return a, b, c


class TestADayThatAgreesEverywhere:
    def test_the_archive_equals_the_api_and_the_aggregation_is_consistent(
        self, tmp_path: Path
    ) -> None:
        report = go(*stage(tmp_path))
        for timeframe, count in (("1d", 1), ("4h", 6)):
            a, b, c = result(report, timeframe)
            assert (a.archive_bars, a.api_bars, a.compared, a.equal, a.mismatched) == (
                count,
                count,
                count,
                count,
                0,
            )
            assert (a.archive_only, a.api_only, a.differences) == (0, 0, ())
            assert (b.compared, b.complete, b.incomplete, b.no_trade) == (count, count, 0, 0)
            assert (b.consistent, b.failed, b.failures) == (count, 0, ())
            assert (c.complete_paired, c.equal, c.archive_smaller) == (count, count, 0)
            assert c.archive_larger_bands == (0, 0, 0, 0)
            assert (c.median_pct, c.max_pct) == (None, None)

    def test_a_zero_volume_first_minute_is_consistent_under_the_traded_rule(
        self, tmp_path: Path
    ) -> None:
        report = go(*stage(tmp_path, filler_first=True))
        for timeframe in ("1d", "4h"):
            _a, b, c = result(report, timeframe)
            assert (b.failed, b.consistent) == (0, b.compared)
            assert c.equal == c.complete_paired

    def test_the_list_digest_and_file_count_are_reported(self, tmp_path: Path) -> None:
        store, responses = stage(tmp_path)
        report = go(store, responses)
        assert (
            report.list_digest
            == hashlib.sha256((responses / "responses.sha256").read_bytes()).hexdigest()
        )
        assert report.files == 2


class TestArchiveAgainstTheApi:
    def test_a_wrong_field_is_counted_by_field_and_listed_with_both_values(
        self, tmp_path: Path
    ) -> None:
        bars = venue_rows("4h")
        bars[2][2] = "9999.00000000"
        a, _b, _c = result(go(*stage(tmp_path, api={"4h": bars})), "4h")
        assert (a.compared, a.equal, a.mismatched) == (6, 5, 1)
        assert a.mismatched_by_field == {"open": 0, "high": 1, "low": 0, "close": 0, "volume": 0}
        (row,) = a.differences
        assert row.open_ms == ms(DAY) + 2 * WIDTH["4h"]
        assert (row.field, str(row.archive), str(row.api)) == (
            "high",
            "2719.00000000",
            "9999.00000000",
        )

    def test_two_wrong_fields_are_one_mismatched_bar_and_two_field_counts(
        self, tmp_path: Path
    ) -> None:
        bars = venue_rows("1d")
        bars[0][1] = "1.00000000"
        bars[0][5] = "7.00000000"
        a, _b, _c = result(go(*stage(tmp_path, api={"1d": bars})), "1d")
        assert a.mismatched == 1
        assert (a.mismatched_by_field["open"], a.mismatched_by_field["volume"]) == (1, 1)
        assert len(a.differences) == 2

    def test_figures_are_compared_as_decimals_not_as_strings(self, tmp_path: Path) -> None:
        bars = venue_rows("1d")
        bars[0][1] = "1000.0"
        a, _b, _c = result(go(*stage(tmp_path, api={"1d": bars})), "1d")
        assert a.mismatched == 0

    def test_a_bar_only_the_api_has_is_api_only_and_a_run(self, tmp_path: Path) -> None:
        bars = venue_rows("4h")
        extra = ms(DAY) + 6 * WIDTH["4h"]
        bars.append([extra, *day_figures("4h", 5), extra + WIDTH["4h"] - 1, "1", 1, "1", "1", "0"])
        a, _b, _c = result(go(*stage(tmp_path, api={"4h": bars})), "4h")
        assert (a.api_only, a.archive_only, a.compared) == (1, 0, 6)
        assert a.api_only_runs == (n2.Run(extra, extra, 1),)

    def test_a_bar_only_the_archive_has_is_archive_only(self, tmp_path: Path) -> None:
        bars = venue_rows("4h")[:5]
        a, _b, _c = result(go(*stage(tmp_path, api={"4h": bars})), "4h")
        assert (a.archive_only, a.api_only, a.compared) == (1, 0, 5)
        last = ms(DAY) + 5 * WIDTH["4h"]
        assert a.archive_only_runs == (n2.Run(last, last, 1),)


class TestTheTradedMinuteConsistencyCheck:
    def test_a_price_the_archive_has_differently_fails_the_bucket_and_is_listed_without_a_price(
        self, tmp_path: Path
    ) -> None:
        wrong = replace(archive_rows("1d")[0], open="1.00000000")
        _a, b, _c = result(go(*stage(tmp_path, archive={"1d": [wrong]})), "1d")
        assert (b.consistent, b.failed, b.failed_complete, b.failed_incomplete) == (0, 1, 1, 0)
        assert b.failed_by_field == {"open": 1, "high": 0, "low": 0, "close": 0}
        (failure,) = b.failures
        assert failure == chk.Failure(ms(DAY), ("open",), True, 1440, 0)

    def test_a_volume_difference_is_not_a_consistency_failure(self, tmp_path: Path) -> None:
        bigger = replace(archive_rows("1d")[0], volume="9999.00000000")
        _a, b, c = result(go(*stage(tmp_path, archive={"1d": [bigger]})), "1d")
        assert b.failed == 0
        assert c.archive_larger_bands != (0, 0, 0, 0)

    def test_an_incomplete_bucket_with_the_right_prices_is_consistent(self, tmp_path: Path) -> None:
        store, responses = stage(
            tmp_path, one_minute=minute_rows(DAY, skip=frozenset({5})), filler_first=False
        )
        _a, b, _c = result(go(store, responses), "4h")
        assert (b.incomplete, b.complete) == (1, 5)
        assert b.failed == 0

    def test_an_incomplete_bucket_whose_extreme_minute_is_missing_fails_and_says_so(
        self, tmp_path: Path
    ) -> None:
        store, responses = stage(tmp_path, one_minute=minute_rows(DAY, skip=frozenset({0})))
        _a, b, _c = result(go(store, responses), "4h")
        assert (b.failed_incomplete, b.failed_complete) == (1, 0)
        (failure,) = b.failures
        assert (failure.complete, failure.minutes_missing) == (False, 1)
        assert set(failure.fields) == {"open", "low"}

    def test_a_bucket_with_no_traded_minute_is_counted_and_not_checked(
        self, tmp_path: Path
    ) -> None:
        quiet = [
            Row(
                ms(DAY) + i * 60_000,
                *["50.00000000"] * 4,
                "0.00000000",
                ms(DAY) + i * 60_000 + 59_999,
            )
            for i in range(1440)
        ]
        zero = [replace(r, volume="0.00000000") for r in archive_rows("1d")]
        _a, b, _c = result(go(*stage(tmp_path, one_minute=quiet, archive={"1d": zero})), "1d")
        assert (b.no_trade, b.consistent, b.failed) == (1, 0, 0)

    def test_buckets_only_one_side_has_are_counted(self, tmp_path: Path) -> None:
        archive = archive_rows("1d")
        extra = ms(DAY) + WIDTH["1d"]
        more = [*archive, Row(extra, *["1.00000000"] * 5, extra + WIDTH["1d"] - 1)]
        _a, b, _c = result(go(*stage(tmp_path, archive={"1d": more})), "1d")
        assert (b.archive_only, b.aggregator_only, b.compared) == (1, 0, 1)


class TestTheVolumeGap:
    def build(self, tmp_path: Path, archive_volume: str) -> chk.VolumeResult:
        rows = [
            replace(r, volume="1.00000000") if r.volume == "2.00000000" else r
            for r in minute_rows(DAY, last_volume="8560.00000000")
        ]
        archive = [replace(archive_rows("1d")[0], volume=archive_volume)]
        store, responses = stage(tmp_path, archive={"1d": archive}, one_minute=rows)
        return result(go(store, responses), "1d")[2]

    @pytest.mark.parametrize(
        ("archive_volume", "bands"),
        [
            ("9999.00000000", (0, 0, 0, 0)),
            ("10000.00000000", (1, 0, 0, 0)),
            ("10000.10000000", (0, 1, 0, 0)),
            ("10001.00000000", (0, 1, 0, 0)),
            ("10100.00000000", (0, 0, 1, 0)),
            ("10101.00000000", (0, 0, 0, 1)),
            ("20000.00000000", (0, 0, 0, 1)),
        ],
    )
    def test_the_archive_being_larger_lands_in_the_band_its_relative_difference_names(
        self, tmp_path: Path, archive_volume: str, bands: tuple[int, int, int, int]
    ) -> None:
        found = self.build(tmp_path, archive_volume)
        assert found.archive_larger_bands == bands
        assert found.archive_smaller == 0
        assert found.equal == int(archive_volume == "9999.00000000")

    def test_the_archive_being_smaller_is_counted_apart_from_the_bands(
        self, tmp_path: Path
    ) -> None:
        found = self.build(tmp_path, "9000.00000000")
        assert found.archive_smaller == 1
        assert found.archive_larger_bands == (0, 0, 0, 0)

    def test_the_median_and_maximum_are_percentages_of_the_archive_volume(
        self, tmp_path: Path
    ) -> None:
        found = self.build(tmp_path, "10000.00000000")
        assert found.median_pct == Decimal("0.01")
        assert found.max_pct == Decimal("0.01")

    def test_an_incomplete_bucket_is_left_out_of_the_gap(self, tmp_path: Path) -> None:
        store, responses = stage(tmp_path, one_minute=minute_rows(DAY, skip=frozenset({5})))
        found = result(go(store, responses), "1d")[2]
        assert found.complete_paired == 0


class TestTheSavedEvidenceIsChecked:
    def test_a_response_that_no_longer_matches_its_digest_refuses_the_run(
        self, tmp_path: Path
    ) -> None:
        store, responses = stage(tmp_path)
        (responses / "BTCUSDT-1d-001.json").write_bytes(b"[]")
        with pytest.raises(chk.CheckError, match="does not match its SHA-256"):
            go(store, responses)

    def test_a_json_file_the_list_does_not_name_refuses_the_run(self, tmp_path: Path) -> None:
        store, responses = stage(tmp_path)
        (responses / "BTCUSDT-4h-002.json").write_bytes(b"[]")
        with pytest.raises(chk.CheckError, match="disagree"):
            go(store, responses)

    def test_a_listed_file_that_is_missing_refuses_the_run(self, tmp_path: Path) -> None:
        store, responses = stage(tmp_path)
        (responses / "BTCUSDT-4h-001.json").unlink()
        with pytest.raises(chk.CheckError, match="disagree"):
            go(store, responses)

    def test_a_missing_digest_list_refuses_the_run(self, tmp_path: Path) -> None:
        store, responses = stage(tmp_path)
        (responses / "responses.sha256").unlink()
        with pytest.raises(chk.CheckError, match="is missing"):
            go(store, responses)

    def test_a_malformed_digest_line_refuses_the_run(self, tmp_path: Path) -> None:
        store, responses = stage(tmp_path)
        (responses / "responses.sha256").write_text("not a digest line\n", encoding="ascii")
        with pytest.raises(chk.CheckError, match="is not"):
            go(store, responses)

    def test_a_bar_at_or_after_the_window_end_refuses_the_run(self, tmp_path: Path) -> None:
        late = [
            [1_704_067_200_000, "1", "1", "1", "1", "1", 1_704_153_599_999, "1", 1, "1", "1", "0"]
        ]
        store, responses = stage(tmp_path, api={"1d": late})
        with pytest.raises(chk.CheckError, match="window end or out of order"):
            go(store, responses)

    def test_open_times_out_of_order_refuse_the_run(self, tmp_path: Path) -> None:
        rows = venue_rows("4h")
        rows[0], rows[1] = rows[1], rows[0]
        store, responses = stage(tmp_path, api={"4h": rows})
        with pytest.raises(chk.CheckError, match="window end or out of order"):
            go(store, responses)

    def test_a_series_with_no_saved_response_refuses_the_run(self, tmp_path: Path) -> None:
        store, responses = stage(tmp_path)
        with pytest.raises(chk.CheckError, match="no saved response for ETHUSDT"):
            chk.run_check(store, responses, ("ETHUSDT",))


class TestNothingAtOrAfterTheWindowEndIsRead:
    def test_files_of_2024_01_that_no_longer_match_their_hash_are_never_opened(
        self, tmp_path: Path
    ) -> None:
        store, responses = stage(tmp_path)
        late = at(2024, 1, 1)
        for interval in ("1m", "1d", "4h"):
            put(
                store.root,
                "BTCUSDT",
                interval,
                [Row(ms(late), *["1.00000000"] * 5, ms(late) + 59_999)],
            )
            month_file(store.root, "BTCUSDT", interval, "2024-01").write_bytes(
                b"not the bytes it hashed"
            )
        report = go(store, responses)
        assert result(report, "1d")[0].equal == 1


class TestWhatIsPrintedAndWhatIsNotAsked:
    def test_the_script_has_no_fetcher_and_no_network_parameter(self) -> None:
        assert set(inspect.signature(chk.main).parameters) == {"argv", "out"}
        assert set(inspect.signature(chk.run_check).parameters) == {"store", "responses", "symbols"}

    def test_a_clean_run_prints_the_three_reports_and_no_price(self, tmp_path: Path) -> None:
        store, responses = stage(tmp_path)
        out = io.StringIO()
        argv = [
            "--responses",
            str(responses),
            "--data-dir",
            str(store.root),
            "--symbols",
            "BTCUSDT",
        ]
        assert chk.main(argv, out=out) == 0
        text = out.getvalue()
        for heading in (
            "N2 ARCHIVE CHECK window=[2017-08-17T00:00:00Z, 2024-01-01T00:00:00Z)",
            "A. ARCHIVE SERIES AGAINST THE SAVED API RESPONSES",
            "B. TRADED-MINUTE AGGREGATION AGAINST THE ARCHIVE SERIES (R-DV)",
            "C. VOLUME GAP, COMPLETE BUCKETS",
            "A MISMATCH LIST (0 rows, first 50 shown)",
            "B FAILING BUCKETS (0, first 50 shown)",
        ):
            assert heading in text
        assert "BTCUSDT 1d: archive=1 api=1 compared=1 equal=1 mismatched=0" in text
        for literal in ("1000.00000000", "3439.00000000", "2880.00000000"):
            assert literal not in text

    def test_the_failing_bucket_list_has_times_and_fields_and_no_price(
        self, tmp_path: Path
    ) -> None:
        store, responses = stage(tmp_path, one_minute=minute_rows(DAY, skip=frozenset({0})))
        out = io.StringIO()
        argv = [
            "--responses",
            str(responses),
            "--data-dir",
            str(store.root),
            "--symbols",
            "BTCUSDT",
        ]
        assert chk.main(argv, out=out) == 0
        lines = [line for line in out.getvalue().splitlines() if "traded_minutes=" in line]
        assert lines
        assert all("fields=" in line and "complete=no" in line for line in lines)
        assert not any(re.search(r"\d+\.\d+", line) for line in lines)

    def test_the_mismatch_list_is_capped_at_fifty_rows(self, tmp_path: Path) -> None:
        days = [DAY + timedelta(days=d) for d in range(60)]
        root = tmp_path / "store"
        one_day = [r for d in days for r in minute_rows(d)]
        put(root, "BTCUSDT", "1m", one_day)
        archive_1d = [Row(ms(d), *day_figures("1d"), ms(d) + WIDTH["1d"] - 1) for d in days]
        archive_4h = [Row(ms(d), *day_figures("4h"), ms(d) + WIDTH["4h"] - 1) for d in days]
        put(root, "BTCUSDT", "1d", archive_1d)
        put(root, "BTCUSDT", "4h", archive_4h)
        wrong = [
            [
                ms(d),
                "1.00000000",
                "1.00000000",
                "1.00000000",
                "1.00000000",
                "1.00000000",
                ms(d) + WIDTH["1d"] - 1,
                "1",
                1,
                "1",
                "1",
                "0",
            ]
            for d in days
        ]
        responses = write_responses(
            tmp_path / "responses", {("BTCUSDT", "1d"): wrong, ("BTCUSDT", "4h"): []}
        )
        out = io.StringIO()
        argv = ["--responses", str(responses), "--data-dir", str(root), "--symbols", "BTCUSDT"]
        assert chk.main(argv, out=out) == 0
        listed = [
            line
            for line in out.getvalue().splitlines()
            if " archive=" in line and " api=" in line and "BTCUSDT 1d 2017" in line
        ]
        assert len(listed) == 50
        assert "(300 rows, first 50 shown)" in out.getvalue()

    def test_a_refused_run_is_an_error_exit_and_prints_no_report(self, tmp_path: Path) -> None:
        store, responses = stage(tmp_path)
        (responses / "BTCUSDT-1d-001.json").write_bytes(b"[]")
        out = io.StringIO()
        argv = [
            "--responses",
            str(responses),
            "--data-dir",
            str(store.root),
            "--symbols",
            "BTCUSDT",
        ]
        assert chk.main(argv, out=out) == chk.EXIT_ERROR
        assert out.getvalue().startswith("ERROR: CheckError:")
        assert "N2 ARCHIVE CHECK" not in out.getvalue()
