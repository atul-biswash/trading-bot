"""The Testnet kline recorder: closed bars only, idempotent, resumable, and honest about resets and gaps.

Every test runs against ``Venue``, a fetcher that serves klines out of a list the test controls, so no
socket is opened and no clock is read. A store is judged by the historical store's own deep check
(``HistoricalStore.verify``) and, where a test says nothing may be written, by a hash of every file
under the root before and after.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pytest

from trading_bot.data.historical import (
    INTERVAL_MS,
    Gap,
    HistoricalStore,
    RegistryKind,
    RowShape,
)
from trading_bot.data.kline_recorder import (
    KLINES_LIMIT,
    RECORDER_LOG_NAME,
    TESTNET_BASE,
    BadKlineError,
    RecorderFetchError,
    RecorderStoreError,
    VenueResetError,
    check_overlap,
    klines_url,
    parse_klines,
    parse_server_time,
    record_all,
    record_series,
    source_url,
    time_url,
    verify_store,
)

UTC = timezone.utc
ONE_MIN = INTERVAL_MS["1m"]
FIVE_MIN = INTERVAL_MS["5m"]
BTC = ("BTCUSDT", "1m")
ETH = ("ETHUSDT", "5m")
NOW = datetime(2026, 10, 9, 12, 0, tzinfo=UTC)


def ms(year: int, month: int, day: int, hour: int = 0, minute: int = 0) -> int:
    return int(datetime(year, month, day, hour, minute, tzinfo=UTC).timestamp() * 1000)


T0 = ms(2026, 10, 7, 10, 32)


def kline(
    open_ms: int, interval_ms: int, price: str = "100", *, close_ms: int | None = None
) -> list[object]:
    p = Decimal(price)
    close = open_ms + interval_ms - 1 if close_ms is None else close_ms
    return [
        open_ms,
        f"{p:.8f}",
        f"{p + 1:.8f}",
        f"{p - 1:.8f}",
        f"{p:.8f}",
        "1.00000000",
        close,
        "100.00000000",
        5,
        "0.50000000",
        "50.00000000",
        "0",
    ]


def bars(
    start_ms: int, count: int, interval_ms: int = ONE_MIN, price: int = 100
) -> list[list[object]]:
    return [
        kline(start_ms + i * interval_ms, interval_ms, str(price + i % 7)) for i in range(count)
    ]


class Venue:
    """A fetcher serving ``/time`` and ``/klines`` out of lists the test edits."""

    def __init__(self, server_ms: int) -> None:
        self.server_ms = server_ms
        self.series: dict[tuple[str, str], list[list[object]]] = {}
        self.calls: list[str] = []
        self.bodies: list[bytes] = []
        self.ignore_start = False
        self.fail_when: Callable[[str], bool] | None = None

    def __call__(self, url: str) -> bytes:
        self.calls.append(url)
        if self.fail_when is not None and self.fail_when(url):
            raise RecorderFetchError("the venue did not answer")
        parsed = urlparse(url)
        if parsed.path.endswith("/time"):
            body = json.dumps({"serverTime": self.server_ms})
        else:
            query = parse_qs(parsed.query)
            key = (query["symbol"][0], query["interval"][0])
            start = int(query["startTime"][0])
            limit = int(query["limit"][0])
            rows = [r for r in self.series.get(key, []) if self.ignore_start or r[0] >= start]  # type: ignore[operator]
            body = json.dumps(rows[:limit])
        data = body.encode()
        self.bodies.append(data)
        return data

    def klines_calls(self) -> list[str]:
        return [url for url in self.calls if "/klines" in url]


def venue_with(key: tuple[str, str], rows: list[list[object]]) -> Venue:
    last = rows[-1]
    interval_ms = INTERVAL_MS[key[1]]
    venue = Venue(server_ms=int(last[0]) + interval_ms + 5_000)  # type: ignore[call-overload]
    venue.series[key] = rows
    return venue


def snapshot(root: Path) -> dict[str, str]:
    return {
        path.relative_to(root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def run(root: Path, venue: Venue, key: tuple[str, str] = BTC, **kw: object):  # type: ignore[no-untyped-def]
    return record_series(
        root,
        key[0],
        key[1],
        fetcher=venue,
        server_time_ms=venue.server_ms,
        clock=lambda: NOW,
        **kw,  # type: ignore[arg-type]
    )


def events(root: Path, key: tuple[str, str] = BTC) -> list[dict[str, object]]:
    path = root / key[0] / key[1] / RECORDER_LOG_NAME
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


class TestTheFirstRun:
    def test_it_backfills_from_the_start_of_time_and_the_store_verifies(
        self, tmp_path: Path
    ) -> None:
        venue = venue_with(BTC, bars(T0, 12))
        report = run(tmp_path, venue)
        assert report.rows_added == 12
        assert (report.first_open_ms, report.last_open_ms) == (T0, T0 + 11 * ONE_MIN)
        assert report.stored_after == 12 and report.gaps == ()
        assert HistoricalStore(tmp_path).verify(*BTC) == ()
        assert "startTime=0&" in venue.klines_calls()[0]
        stored = list(
            HistoricalStore(tmp_path).candles(
                "BTCUSDT",
                "1m",
                datetime(2026, 10, 7, tzinfo=UTC),
                datetime(2026, 10, 8, tzinfo=UTC),
            )
        )
        assert len(stored) == 12
        assert stored[0].close == Decimal("100.00000000")

    def test_pages_are_followed_by_start_time(self, tmp_path: Path) -> None:
        venue = venue_with(BTC, bars(T0, 12))
        report = run(tmp_path, venue, page_limit=5)
        assert report.pages == 3 and report.rows_added == 12
        calls = venue.klines_calls()
        assert len(calls) == 3
        assert f"startTime={T0 + 5 * ONE_MIN}&" not in calls[1]
        assert f"startTime={T0 + 4 * ONE_MIN + 1}&" in calls[1]
        assert f"startTime={T0 + 9 * ONE_MIN + 1}&" in calls[2]

    def test_a_five_minute_series_is_kept_on_its_own_grid(self, tmp_path: Path) -> None:
        start = ms(2026, 10, 7, 10, 30)
        venue = venue_with(ETH, bars(start, 20, FIVE_MIN))
        report = run(tmp_path, venue, ETH)
        assert report.rows_added == 20
        assert HistoricalStore(tmp_path).verify(*ETH) == ()

    def test_only_closed_bars_are_stored(self, tmp_path: Path) -> None:
        rows = bars(T0, 5)
        venue = venue_with(BTC, rows)
        venue.server_ms = int(rows[-1][6]) + 1  # type: ignore[call-overload]
        assert run(tmp_path, venue).rows_added == 5
        other = tmp_path / "other"
        venue.server_ms = int(rows[-1][6])  # type: ignore[call-overload]
        report = run(other, venue)
        assert report.rows_added == 4 and report.forming_skipped == 1
        assert report.last_open_ms == T0 + 3 * ONE_MIN


class TestResuming:
    def test_a_second_run_with_nothing_new_changes_no_store_file(self, tmp_path: Path) -> None:
        venue = venue_with(BTC, bars(T0, 12))
        run(tmp_path, venue)
        before = {k: v for k, v in snapshot(tmp_path).items() if not k.endswith(RECORDER_LOG_NAME)}
        report = run(tmp_path, venue)
        after = {k: v for k, v in snapshot(tmp_path).items() if not k.endswith(RECORDER_LOG_NAME)}
        assert report.rows_added == 0 and report.stored_after == 12
        assert after == before
        names = [event["event"] for event in events(tmp_path)]
        assert names == ["recorded", "nothing_new"]

    def test_it_resumes_one_millisecond_after_the_last_stored_open(self, tmp_path: Path) -> None:
        venue = venue_with(BTC, bars(T0, 12))
        run(tmp_path, venue)
        venue.calls.clear()
        run(tmp_path, venue)
        assert f"startTime={T0 + 11 * ONE_MIN + 1}&" in venue.klines_calls()[0]

    def test_new_bars_extend_a_partial_month_in_place(self, tmp_path: Path) -> None:
        venue = venue_with(BTC, bars(T0, 12))
        run(tmp_path, venue)
        venue.series[BTC] = bars(T0, 20)
        venue.server_ms = T0 + 25 * ONE_MIN
        report = run(tmp_path, venue)
        assert report.rows_added == 8 and report.stored_after == 20
        assert report.first_open_ms == T0 + 12 * ONE_MIN
        assert HistoricalStore(tmp_path).verify(*BTC) == ()
        manifest = (tmp_path / "BTCUSDT" / "1m" / "MANIFEST.jsonl").read_text(encoding="utf-8")
        assert len(manifest.splitlines()) == 1
        assert '"rows":20' in manifest

    def test_a_month_boundary_makes_two_files_that_both_verify(self, tmp_path: Path) -> None:
        start = ms(2026, 10, 31, 23, 58)
        venue = venue_with(BTC, bars(start, 6))
        report = run(tmp_path, venue)
        assert report.rows_added == 6
        directory = tmp_path / "BTCUSDT" / "1m"
        assert (directory / "BTCUSDT-1m-2026-10.csv").is_file()
        assert (directory / "BTCUSDT-1m-2026-11.csv").is_file()
        assert HistoricalStore(tmp_path).verify(*BTC) == ()
        assert HistoricalStore(tmp_path).coverage(*BTC).gaps == ()

    def test_the_manifest_names_the_endpoint_and_the_last_page_digest(self, tmp_path: Path) -> None:
        venue = venue_with(BTC, bars(T0, 12))
        run(tmp_path, venue, page_limit=5)
        line = json.loads(
            (tmp_path / "BTCUSDT" / "1m" / "MANIFEST.jsonl")
            .read_text(encoding="utf-8")
            .splitlines()[0]
        )
        assert line["source_url"] == source_url("BTCUSDT", "1m")
        pages = events(tmp_path)[0]["pages"]
        assert isinstance(pages, list)
        assert line["zip_sha256"] == pages[-1]["sha256"]


class TestTheLog:
    def test_each_run_appends_one_line_per_series_naming_every_page(self, tmp_path: Path) -> None:
        venue = venue_with(BTC, bars(T0, 12))
        run(tmp_path, venue, page_limit=5, meta={"code_commit": "abc123"})
        found = events(tmp_path)
        assert len(found) == 1
        event = found[0]
        assert event["event"] == "recorded" and event["at"] == NOW.isoformat()
        assert event["rows_added"] == 12 and event["meta"] == {"code_commit": "abc123"}
        assert event["server_time_ms"] == venue.server_ms
        pages = event["pages"]
        assert isinstance(pages, list) and len(pages) == 3
        klines_bodies = [b for b in venue.bodies if b.startswith(b"[")]
        assert [p["sha256"] for p in pages] == [
            hashlib.sha256(b).hexdigest() for b in klines_bodies
        ]
        assert [p["rows"] for p in pages] == [5, 5, 2]
        assert all(str(p["url"]).startswith(TESTNET_BASE + "/api/v3/klines?") for p in pages)

    def test_the_log_is_not_a_csv_and_the_store_still_verifies(self, tmp_path: Path) -> None:
        run(tmp_path, venue_with(BTC, bars(T0, 3)))
        assert HistoricalStore(tmp_path).verify(*BTC) == ()


class TestAResetIsNotAppendedAcross:
    def stored(self, tmp_path: Path) -> Venue:
        venue = venue_with(BTC, bars(T0, 12))
        run(tmp_path, venue)
        return venue

    def test_a_last_bar_that_differs_refuses_and_writes_nothing(self, tmp_path: Path) -> None:
        venue = self.stored(tmp_path)
        rewritten = bars(T0, 20, price=500)
        venue.series[BTC] = rewritten
        before = snapshot(tmp_path)
        with pytest.raises(VenueResetError, match="rewritten"):
            check_overlap(tmp_path, "BTCUSDT", "1m", fetcher=venue)
        with pytest.raises(VenueResetError):
            record_all(tmp_path, [BTC], fetcher=venue, clock=lambda: NOW)
        assert snapshot(tmp_path) == before

    def test_a_last_bar_the_venue_no_longer_has_refuses(self, tmp_path: Path) -> None:
        venue = self.stored(tmp_path)
        venue.series[BTC] = bars(T0 + 3 * 24 * 60 * ONE_MIN, 10)
        before = snapshot(tmp_path)
        with pytest.raises(VenueResetError, match="discarded"):
            record_all(tmp_path, [BTC], fetcher=venue, clock=lambda: NOW)
        assert snapshot(tmp_path) == before

    def test_every_series_is_checked_before_any_is_written(self, tmp_path: Path) -> None:
        venue = Venue(server_ms=T0 + 200 * ONE_MIN)
        venue.series[BTC] = bars(T0, 12)
        venue.series[ETH] = bars(ms(2026, 10, 7, 10, 30), 20, FIVE_MIN)
        record_all(tmp_path, [BTC, ETH], fetcher=venue, clock=lambda: NOW)
        venue.series[BTC] = bars(T0, 30)  # BTC has new bars to take ...
        venue.series[ETH] = bars(
            ms(2026, 10, 7, 10, 30), 20, FIVE_MIN, price=900
        )  # ... ETH was reset
        before = snapshot(tmp_path)
        with pytest.raises(VenueResetError, match="ETHUSDT"):
            record_all(tmp_path, [BTC, ETH], fetcher=venue, clock=lambda: NOW)
        assert snapshot(tmp_path) == before

    def test_an_unchanged_overlap_passes_and_an_empty_store_has_nothing_to_compare(
        self, tmp_path: Path
    ) -> None:
        venue = self.stored(tmp_path)
        check_overlap(tmp_path, "BTCUSDT", "1m", fetcher=venue)
        before = len(venue.calls)
        check_overlap(tmp_path / "empty", "BTCUSDT", "1m", fetcher=venue)
        assert len(venue.calls) == before

    def test_a_run_reads_the_server_clock_first_and_every_overlap_before_any_page(
        self, tmp_path: Path
    ) -> None:
        venue = Venue(server_ms=T0 + 200 * ONE_MIN)
        venue.series[BTC] = bars(T0, 12)
        venue.series[ETH] = bars(ms(2026, 10, 7, 10, 30), 20, FIVE_MIN)
        record_all(tmp_path, [BTC, ETH], fetcher=venue, clock=lambda: NOW)
        venue.calls.clear()
        venue.series[BTC] = bars(T0, 15)
        record_all(tmp_path, [BTC, ETH], fetcher=venue, clock=lambda: NOW)
        kinds = [
            "time"
            if "/time" in url
            else "limit=1"
            if "limit=1&" in url or url.endswith("limit=1")
            else "page"
            for url in venue.calls
        ]
        assert kinds[0] == "time"
        assert kinds[1:3] == ["limit=1", "limit=1"]
        assert set(kinds[3:]) == {"page"} and len(kinds) == 5


class TestGapsAreReportedAndNeverFilled:
    def test_a_break_between_runs_is_a_gap_in_the_report_and_the_log(self, tmp_path: Path) -> None:
        venue = venue_with(BTC, bars(T0, 12))
        run(tmp_path, venue)
        venue.series[BTC] = bars(T0, 12) + bars(T0 + 15 * ONE_MIN, 5)
        venue.server_ms = T0 + 30 * ONE_MIN
        report = run(tmp_path, venue)
        expected = Gap(T0 + 12 * ONE_MIN, T0 + 15 * ONE_MIN, 3)
        assert report.gaps == (expected,)
        assert report.rows_added == 5 and report.stored_after == 17
        assert events(tmp_path)[-1]["gaps"] == [
            {"start_ms": expected.start_ms, "end_ms": expected.end_ms, "missing": 3}
        ]
        coverage = HistoricalStore(tmp_path).coverage(*BTC)
        assert coverage.missing == 3 and coverage.bars == 17

    def test_a_hole_inside_one_backfill_is_a_gap(self, tmp_path: Path) -> None:
        rows = bars(T0, 4) + bars(T0 + 6 * ONE_MIN, 4)
        report = run(tmp_path, venue_with(BTC, rows))
        assert report.gaps == (Gap(T0 + 4 * ONE_MIN, T0 + 6 * ONE_MIN, 2),)
        assert report.stored_after == 8


class TestIrregularBars:
    def test_an_off_grid_bar_is_quarantined_with_its_line_and_never_repeated(
        self, tmp_path: Path
    ) -> None:
        rows = bars(T0, 5)
        rows.append(kline(T0 + 5 * ONE_MIN + 1_000, ONE_MIN, "100"))
        venue = venue_with(BTC, rows)
        report = run(tmp_path, venue)
        assert report.rows_added == 5 and report.quarantined == 1
        registry = HistoricalStore(tmp_path).registry(*BTC)
        assert len(registry) == 1
        assert registry[0].kind is RegistryKind.QUARANTINED
        assert registry[0].shape is RowShape.OFF_GRID
        assert registry[0].line == 6 and registry[0].month == "2026-10"
        venue.series[BTC] = rows + bars(T0 + 6 * ONE_MIN, 3)
        venue.server_ms = T0 + 60 * ONE_MIN
        second = run(tmp_path, venue)
        assert second.rows_added == 3 and second.quarantined == 0
        assert len(HistoricalStore(tmp_path).registry(*BTC)) == 1
        assert HistoricalStore(tmp_path).verify(*BTC) == ()

    def test_a_short_bar_is_stored_and_registered(self, tmp_path: Path) -> None:
        rows = bars(T0, 3)
        rows.append(kline(T0 + 3 * ONE_MIN, ONE_MIN, "100", close_ms=T0 + 3 * ONE_MIN + 29_999))
        report = run(tmp_path, venue_with(BTC, rows))
        assert report.rows_added == 4 and report.registered == 1
        registry = HistoricalStore(tmp_path).registry(*BTC)
        assert len(registry) == 1 and registry[0].kind is RegistryKind.REGISTERED
        assert registry[0].shape is RowShape.SHORT_BAR

    def test_registry_lines_survive_the_next_extension_of_their_month(self, tmp_path: Path) -> None:
        rows = bars(T0, 3)
        rows.append(kline(T0 + 3 * ONE_MIN, ONE_MIN, "100", close_ms=T0 + 3 * ONE_MIN + 29_999))
        venue = venue_with(BTC, rows)
        run(tmp_path, venue)
        venue.series[BTC] = rows + bars(T0 + 4 * ONE_MIN, 4)
        venue.server_ms = T0 + 60 * ONE_MIN
        run(tmp_path, venue)
        registry = HistoricalStore(tmp_path).registry(*BTC)
        assert len(registry) == 1 and registry[0].line == 4
        assert HistoricalStore(tmp_path).verify(*BTC) == ()

    def test_a_month_holding_only_a_quarantined_bar_stores_nothing_and_is_fetched_again(
        self, tmp_path: Path
    ) -> None:
        """A KNOWN LIMIT, pinned so it is not mistaken for a bug or quietly changed.

        The registry hangs off a month's manifest line, and a month with no stored bar has none, so
        the quarantined bar is counted in the report and the log but written nowhere else. The next
        run therefore asks for it again. The first stored bar of the month ends the limit.
        """
        venue = venue_with(BTC, [kline(T0 + 1_000, ONE_MIN, "100")])
        first = run(tmp_path, venue)
        assert first.rows_added == 0 and first.quarantined == 1
        assert not (tmp_path / "BTCUSDT" / "1m" / "MANIFEST.jsonl").exists()
        second = run(tmp_path, venue)
        assert second.quarantined == 1 and second.pages == 1
        assert "startTime=0&" in venue.klines_calls()[1]


class TestRefusals:
    def test_a_bar_whose_low_is_above_its_open_is_refused_and_nothing_is_written(
        self, tmp_path: Path
    ) -> None:
        rows = bars(T0, 4)
        rows[2][3] = "150.00000000"  # low above the open and the close
        before = snapshot(tmp_path)
        with pytest.raises(BadKlineError, match="enclose"):
            run(tmp_path, venue_with(BTC, rows))
        assert snapshot(tmp_path) == before

    def test_a_page_that_repeats_is_refused(self, tmp_path: Path) -> None:
        venue = venue_with(BTC, bars(T0, 12))
        venue.ignore_start = True
        with pytest.raises(BadKlineError, match="repeated or went backwards"):
            run(tmp_path, venue, page_limit=5)
        assert snapshot(tmp_path) == {}

    def test_a_failed_request_leaves_the_series_as_it_was(self, tmp_path: Path) -> None:
        venue = venue_with(BTC, bars(T0, 12))
        run(tmp_path, venue)
        venue.series[BTC] = bars(T0, 30)
        venue.server_ms = T0 + 60 * ONE_MIN
        before = snapshot(tmp_path)
        venue.fail_when = lambda url: (
            "startTime=" in url and f"startTime={T0 + 11 * ONE_MIN + 1}" in url
        )
        with pytest.raises(RecorderFetchError):
            run(tmp_path, venue)
        assert snapshot(tmp_path) == before

    def test_a_failure_in_the_second_series_leaves_the_first_written_and_clean(
        self, tmp_path: Path
    ) -> None:
        venue = Venue(server_ms=T0 + 200 * ONE_MIN)
        venue.series[BTC] = bars(T0, 12)
        venue.series[ETH] = bars(ms(2026, 10, 7, 10, 30), 20, FIVE_MIN)
        venue.fail_when = lambda url: "symbol=ETHUSDT" in url
        with pytest.raises(RecorderFetchError):
            record_all(tmp_path, [BTC, ETH], fetcher=venue, clock=lambda: NOW)
        assert HistoricalStore(tmp_path).verify(*BTC) == ()
        assert HistoricalStore(tmp_path).coverage(*BTC).bars == 12
        assert not (tmp_path / "ETHUSDT").exists()

    def test_a_store_that_does_not_verify_is_not_extended(self, tmp_path: Path) -> None:
        venue = venue_with(BTC, bars(T0, 12))
        run(tmp_path, venue)
        month = tmp_path / "BTCUSDT" / "1m" / "BTCUSDT-1m-2026-10.csv"
        month.write_bytes(month.read_bytes().replace(b"100.00000000", b"101.00000000", 1))
        venue.series[BTC] = bars(T0, 30)
        venue.server_ms = T0 + 60 * ONE_MIN
        before = snapshot(tmp_path)
        with pytest.raises(RecorderStoreError, match="hash_mismatch"):
            run(tmp_path, venue)
        assert snapshot(tmp_path) == before


class TestTheUrlsAndTheParsers:
    def test_the_urls_are_exact_and_validated(self) -> None:
        assert klines_url("BTCUSDT", "1m", start_ms=5, limit=2) == (
            "https://testnet.binance.vision/api/v3/klines?symbol=BTCUSDT&interval=1m&startTime=5&limit=2"
        )
        assert time_url() == "https://testnet.binance.vision/api/v3/time"
        assert source_url("ETHUSDT", "5m").endswith("klines?symbol=ETHUSDT&interval=5m")
        for symbol, interval, start, limit in (
            ("btcusdt", "1m", 0, 1),
            ("BTCUSDT&x=1", "1m", 0, 1),
            ("BTCUSDT", "2m", 0, 1),
            ("BTCUSDT", "1m", -1, 1),
            ("BTCUSDT", "1m", 0, 0),
            ("BTCUSDT", "1m", 0, KLINES_LIMIT + 1),
        ):
            with pytest.raises(ValueError):
                klines_url(symbol, interval, start_ms=start, limit=limit)

    def test_malformed_klines_are_refused(self) -> None:
        good = kline(T0, ONE_MIN)
        for body in (
            b"not json",
            b'{"a": 1}',
            json.dumps([good[:11]]).encode(),
            json.dumps([[float(T0), *good[1:]]]).encode(),
            json.dumps([[T0, 100, *good[2:]]]).encode(),
            json.dumps([[True, *good[1:]]]).encode(),
        ):
            with pytest.raises(RecorderFetchError):
                parse_klines(body)
        parsed = parse_klines(json.dumps([good]).encode())
        assert len(parsed) == 1 and parsed[0].open_time_ms == T0
        assert parsed[0].line.startswith(f"{T0},100.00000000,")

    def test_the_server_time_must_be_an_integer(self) -> None:
        assert parse_server_time(b'{"serverTime": 1234}') == 1234
        for body in (b"x", b"[]", b'{"serverTime": "1234"}', b'{"serverTime": 12.5}', b"{}"):
            with pytest.raises(RecorderFetchError):
                parse_server_time(body)


class TestVerifyStore:
    def test_a_clean_store_reports_its_bars_and_gaps(self, tmp_path: Path) -> None:
        venue = venue_with(BTC, bars(T0, 4) + bars(T0 + 6 * ONE_MIN, 4))
        run(tmp_path, venue)
        checks = verify_store(tmp_path, [BTC])
        assert len(checks) == 1
        check = checks[0]
        assert check.problems == () and check.bars == 8 and check.months == ("2026-10",)
        assert check.first_open_ms == T0 and check.last_open_ms == T0 + 9 * ONE_MIN
        assert check.gaps == (Gap(T0 + 4 * ONE_MIN, T0 + 6 * ONE_MIN, 2),)

    def test_a_deleted_month_is_a_problem(self, tmp_path: Path) -> None:
        run(tmp_path, venue_with(BTC, bars(T0, 4)))
        (tmp_path / "BTCUSDT" / "1m" / "BTCUSDT-1m-2026-10.csv").unlink()
        check = verify_store(tmp_path, [BTC])[0]
        assert any(problem.kind == "missing_file" for problem in check.problems)
