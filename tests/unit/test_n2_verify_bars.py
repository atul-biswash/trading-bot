"""``scripts/n2_verify_bars.py``: the one URL, the window, the comparison and what it prints.

No test touches the network or the real store. A ``FakeVenue`` answers the klines URL from a
table of venue bars, honouring ``startTime``, ``endTime`` and ``limit`` as the endpoint does,
and records every URL asked; the store is a few real month files written into ``tmp_path``.
Expected figures are literals, or are computed here from the stored literals, never by the
code under test.
"""

from __future__ import annotations

import hashlib
import io
import json
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

import n2_verify_bars as n2

from trading_bot.data.historical import HistoricalStore, Row, write_month

UTC = timezone.utc
EPOCH = datetime(1970, 1, 1, tzinfo=UTC)
MINUTE = timedelta(minutes=1)
SOURCE = {"source_url": "https://example.invalid/m.zip", "zip_sha256": "0" * 64}
WIDTH = {"1d": 86_400_000, "4h": 14_400_000}
WINDOW_START_MS = 1_502_928_000_000
WINDOW_END_MS = 1_704_067_200_000


def at(year: int, month: int, day: int, hour: int = 0, minute: int = 0) -> datetime:
    return datetime(year, month, day, hour, minute, tzinfo=UTC)


def ms(moment: datetime) -> int:
    return (moment - EPOCH) // timedelta(milliseconds=1)


def minute_row(day: datetime, i: int) -> Row:
    opened = ms(day + i * MINUTE)
    return Row(
        open_time_ms=opened,
        open=f"{1000 + i}.00000000",
        high=f"{2000 + i}.00000000",
        low=f"{500 + i}.00000000",
        close=f"{1500 + i}.00000000",
        volume="2.00000000",
        close_time_ms=opened + 59_999,
    )


def store_days(
    root: Path,
    symbol: str,
    days: list[datetime],
    *,
    skip: dict[datetime, frozenset[int]] | None = None,
) -> HistoricalStore:
    """One month file per month holding the listed whole days; ``skip`` drops minutes of a day."""
    dropped = skip or {}
    months: dict[str, list[Row]] = {}
    for day in days:
        rows = [minute_row(day, i) for i in range(1440) if i not in dropped.get(day, frozenset())]
        months.setdefault(f"{day.year:04d}-{day.month:02d}", []).extend(rows)
    for month, rows in months.items():
        write_month(root, symbol, "1m", month, rows, **SOURCE)
    return HistoricalStore(root)


def expected(timeframe: str, day: datetime, k: int = 0) -> list[str]:
    """The five figures of the k-th bucket of ``day`` from the stored literals, as 8-dp strings."""
    if timeframe == "1d":
        first, last, minutes = 0, 1439, 1440
    else:
        first, last, minutes = 240 * k, 240 * k + 239, 240
    return [
        f"{1000 + first}.00000000",
        f"{2000 + last}.00000000",
        f"{500 + first}.00000000",
        f"{1500 + last}.00000000",
        f"{2 * minutes}.00000000",
    ]


def venue_row(open_ms: int, figures: list[str], timeframe: str) -> list[object]:
    return [
        open_ms,
        *figures,
        open_ms + WIDTH[timeframe] - 1,
        "123.45678900",
        10,
        "1.00000000",
        "2.00000000",
        "0",
    ]


def day_venue(day: datetime, timeframe: str) -> list[list[object]]:
    base = ms(day)
    if timeframe == "1d":
        return [venue_row(base, expected("1d", day), "1d")]
    return [venue_row(base + k * WIDTH["4h"], expected("4h", day, k), "4h") for k in range(6)]


class FakeVenue:
    """Answers the klines endpoint from ``bars[(symbol, interval)]`` and records each URL."""

    def __init__(self, bars: dict[tuple[str, str], list[list[object]]]) -> None:
        self.bars = bars
        self.urls: list[str] = []

    def __call__(self, url: str) -> bytes:
        self.urls.append(url)
        query = dict(urllib.parse.parse_qsl(urllib.parse.urlsplit(url).query))
        rows = self.bars.get((query["symbol"], query["interval"]), [])
        start, end, limit = int(query["startTime"]), int(query["endTime"]), int(query["limit"])
        page = [row for row in rows if start <= int(str(row[0])) <= end][:limit]
        return json.dumps(page).encode("ascii")

    def queries(self) -> list[dict[str, str]]:
        return [dict(urllib.parse.parse_qsl(urllib.parse.urlsplit(u).query)) for u in self.urls]


def go(
    tmp_path: Path,
    store: HistoricalStore,
    venue: FakeVenue,
    symbols: tuple[str, ...] = ("BTCUSDT",),
    limit: int = 1000,
) -> list[n2.SeriesResult]:
    return n2.run(
        store, venue, tmp_path / "out", symbols, pause=0.0, sleep=lambda _s: None, limit=limit
    )


def one(results: list[n2.SeriesResult], timeframe: str, symbol: str = "BTCUSDT") -> n2.SeriesResult:
    (found,) = [r for r in results if r.symbol == symbol and r.timeframe == timeframe]
    return found


DAY = at(2017, 9, 1)


def table(symbol: str, day: datetime) -> dict[tuple[str, str], list[list[object]]]:
    return {(symbol, tf): day_venue(day, tf) for tf in ("1d", "4h")}


class TestAWholeDayThatAgrees:
    def test_every_bucket_is_complete_and_equal(self, tmp_path: Path) -> None:
        store = store_days(tmp_path / "s", "BTCUSDT", [DAY])
        results = go(tmp_path, store, FakeVenue(table("BTCUSDT", DAY)))
        day, sixths = one(results, "1d"), one(results, "4h")
        assert (day.venue_bars, day.aggregated_bars, day.compared, day.equal) == (1, 1, 1, 1)
        assert (sixths.venue_bars, sixths.aggregated_bars, sixths.compared, sixths.equal) == (
            6,
            6,
            6,
            6,
        )
        for result in (day, sixths):
            assert result.mismatched == 0
            assert result.incomplete == 0
            assert result.complete == result.aggregated_bars
            assert (result.aggregator_only, result.venue_only, result.off_grid_venue) == (0, 0, 0)
            assert result.mismatches == ()

    def test_both_pairs_and_both_timeframes_are_run_in_order(self, tmp_path: Path) -> None:
        store = store_days(tmp_path / "s", "BTCUSDT", [DAY])
        store_days(tmp_path / "s", "ETHUSDT", [DAY])
        venue = FakeVenue({**table("BTCUSDT", DAY), **table("ETHUSDT", DAY)})
        results = go(tmp_path, store, venue, ("BTCUSDT", "ETHUSDT"))
        assert [(r.symbol, r.timeframe) for r in results] == [
            ("BTCUSDT", "1d"),
            ("BTCUSDT", "4h"),
            ("ETHUSDT", "1d"),
            ("ETHUSDT", "4h"),
        ]
        assert all(r.equal == r.compared and r.compared > 0 for r in results)


class TestADifferenceIsCountedByFieldAndByCompleteness:
    def test_a_wrong_high_in_a_complete_bucket_is_a_complete_mismatch(self, tmp_path: Path) -> None:
        store = store_days(tmp_path / "s", "BTCUSDT", [DAY])
        bars = table("BTCUSDT", DAY)
        bars[("BTCUSDT", "4h")][2][2] = "9999.00000000"
        sixths = one(go(tmp_path, store, FakeVenue(bars)), "4h")
        assert (sixths.compared, sixths.equal, sixths.mismatched) == (6, 5, 1)
        assert sixths.mismatched_by_field == {
            "open": 0,
            "high": 1,
            "low": 0,
            "close": 0,
            "volume": 0,
        }
        assert (sixths.mismatched_complete, sixths.mismatched_incomplete) == (1, 0)
        (row,) = sixths.mismatches
        assert row.open_ms == ms(DAY) + 2 * WIDTH["4h"]
        assert (row.field, str(row.aggregated), str(row.venue)) == (
            "high",
            "2719.00000000",
            "9999.00000000",
        )
        assert row.minutes_missing == 0

    def test_two_wrong_fields_in_one_bucket_are_one_mismatched_bucket_and_two_field_counts(
        self, tmp_path: Path
    ) -> None:
        store = store_days(tmp_path / "s", "BTCUSDT", [DAY])
        bars = table("BTCUSDT", DAY)
        bars[("BTCUSDT", "1d")][0][1] = "1.00000000"
        bars[("BTCUSDT", "1d")][0][5] = "7.00000000"
        day = one(go(tmp_path, store, FakeVenue(bars)), "1d")
        assert day.mismatched == 1
        assert day.mismatched_by_field["open"] == 1
        assert day.mismatched_by_field["volume"] == 1
        assert len(day.mismatches) == 2

    def test_a_missing_minute_that_changes_the_volume_is_an_incomplete_mismatch(
        self, tmp_path: Path
    ) -> None:
        store = store_days(tmp_path / "s", "BTCUSDT", [DAY], skip={DAY: frozenset({5})})
        sixths = one(go(tmp_path, store, FakeVenue(table("BTCUSDT", DAY))), "4h")
        assert sixths.incomplete == 1
        assert (sixths.mismatched_complete, sixths.mismatched_incomplete) == (0, 1)
        assert sixths.mismatched_by_field["volume"] == 1
        (row,) = sixths.mismatches
        assert (str(row.aggregated), str(row.venue), row.minutes_missing) == (
            "478.00000000",
            "480.00000000",
            1,
        )

    def test_an_incomplete_bucket_that_still_equals_the_venue_is_counted_as_such(
        self, tmp_path: Path
    ) -> None:
        store = store_days(tmp_path / "s", "BTCUSDT", [DAY], skip={DAY: frozenset({5})})
        bars = table("BTCUSDT", DAY)
        bars[("BTCUSDT", "4h")][0][5] = "478.00000000"
        sixths = one(go(tmp_path, store, FakeVenue(bars)), "4h")
        assert (sixths.incomplete, sixths.incomplete_equal, sixths.mismatched) == (1, 1, 0)

    def test_figures_are_compared_as_decimals_not_as_strings(self, tmp_path: Path) -> None:
        store = store_days(tmp_path / "s", "BTCUSDT", [DAY])
        bars = table("BTCUSDT", DAY)
        bars[("BTCUSDT", "1d")][0][1] = "1000.0"
        assert one(go(tmp_path, store, FakeVenue(bars)), "1d").mismatched == 0


class TestBucketsOnlyOneSideHas:
    def test_a_venue_bar_with_no_stored_minute_is_venue_only(self, tmp_path: Path) -> None:
        store = store_days(tmp_path / "s", "BTCUSDT", [DAY])
        bars = table("BTCUSDT", DAY)
        other = at(2017, 9, 2)
        bars[("BTCUSDT", "1d")] += day_venue(other, "1d")
        day = one(go(tmp_path, store, FakeVenue(bars)), "1d")
        assert (day.venue_only, day.aggregator_only, day.compared) == (1, 0, 1)
        assert day.venue_only_runs == (n2.Run(ms(other), ms(other), 1),)

    def test_a_stored_bucket_the_venue_lacks_is_aggregator_only(self, tmp_path: Path) -> None:
        store = store_days(tmp_path / "s", "BTCUSDT", [DAY, at(2017, 9, 2)])
        day = one(go(tmp_path, store, FakeVenue(table("BTCUSDT", DAY))), "1d")
        assert (day.aggregator_only, day.venue_only, day.compared) == (1, 0, 1)
        assert day.aggregator_only_runs == (n2.Run(ms(at(2017, 9, 2)), ms(at(2017, 9, 2)), 1),)

    def test_consecutive_unpaired_buckets_are_one_run_and_a_break_starts_another(self) -> None:
        width = WIDTH["1d"]
        base = ms(at(2017, 12, 1))
        opens = [base, base + width, base + 2 * width, base + 5 * width]
        assert n2._runs(opens, width) == (
            n2.Run(base, base + 2 * width, 3),
            n2.Run(base + 5 * width, base + 5 * width, 1),
        )

    def test_a_venue_open_off_the_grid_is_counted(self, tmp_path: Path) -> None:
        store = store_days(tmp_path / "s", "BTCUSDT", [DAY])
        bars = table("BTCUSDT", DAY)
        bars[("BTCUSDT", "1d")].append(
            venue_row(ms(DAY) + 86_400_000 + 1, expected("1d", DAY), "1d")
        )
        assert one(go(tmp_path, store, FakeVenue(bars)), "1d").off_grid_venue == 1


class TestTheRequests:
    def test_the_only_url_is_the_klines_endpoint_with_five_parameters_and_no_key(
        self, tmp_path: Path
    ) -> None:
        store = store_days(tmp_path / "s", "BTCUSDT", [DAY])
        venue = FakeVenue(table("BTCUSDT", DAY))
        go(tmp_path, store, venue)
        assert venue.urls
        for url in venue.urls:
            assert url.startswith("https://api.binance.com/api/v3/klines?")
        for query in venue.queries():
            assert set(query) == {"symbol", "interval", "startTime", "endTime", "limit"}

    def test_the_first_request_starts_at_2017_08_17_and_every_one_ends_before_2024(
        self, tmp_path: Path
    ) -> None:
        store = store_days(tmp_path / "s", "BTCUSDT", [DAY])
        venue = FakeVenue(table("BTCUSDT", DAY))
        go(tmp_path, store, venue)
        assert int(venue.queries()[0]["startTime"]) == WINDOW_START_MS
        assert all(int(q["endTime"]) == WINDOW_END_MS - 1 for q in venue.queries())

    def test_a_page_full_to_the_limit_is_followed_by_the_next_from_the_last_open(
        self, tmp_path: Path
    ) -> None:
        store = store_days(tmp_path / "s", "BTCUSDT", [DAY])
        venue = FakeVenue(table("BTCUSDT", DAY))
        sixths = one(go(tmp_path, store, venue, limit=2), "4h")
        starts = [int(q["startTime"]) for q in venue.queries() if q["interval"] == "4h"]
        assert sixths.requests == 4
        assert starts == [
            WINDOW_START_MS,
            ms(DAY) + 2 * WIDTH["4h"],
            ms(DAY) + 4 * WIDTH["4h"],
            ms(DAY) + 6 * WIDTH["4h"],
        ]
        assert sixths.venue_bars == 6

    def test_requests_are_paced_by_the_pause_and_not_before_the_first(self, tmp_path: Path) -> None:
        store = store_days(tmp_path / "s", "BTCUSDT", [DAY])
        slept: list[float] = []
        n2.run(
            store,
            FakeVenue(table("BTCUSDT", DAY)),
            tmp_path / "out",
            ("BTCUSDT",),
            pause=0.3,
            sleep=slept.append,
            limit=2,
        )
        assert slept == [0.3, 0.3, 0.3]

    def test_a_bar_at_or_after_the_window_end_is_an_error_not_a_row(self, tmp_path: Path) -> None:
        store = store_days(tmp_path / "s", "BTCUSDT", [DAY])

        def late(_url: str) -> bytes:
            return json.dumps([venue_row(WINDOW_END_MS, expected("1d", DAY), "1d")]).encode("ascii")

        with pytest.raises(n2.VerifyError, match="at or after the window end"):
            n2.run(store, late, tmp_path / "out", ("BTCUSDT",), pause=0.0)

    def test_open_times_that_do_not_increase_are_an_error(self, tmp_path: Path) -> None:
        store = store_days(tmp_path / "s", "BTCUSDT", [DAY])
        rows = [
            venue_row(ms(DAY) + WIDTH["1d"], expected("1d", DAY), "1d"),
            venue_row(ms(DAY), expected("1d", DAY), "1d"),
        ]

        def backwards(_url: str) -> bytes:
            return json.dumps(rows).encode("ascii")

        with pytest.raises(n2.VerifyError, match="do not increase"):
            n2.run(store, backwards, tmp_path / "out", ("BTCUSDT",), pause=0.0)

    @pytest.mark.parametrize(
        "body", [b"not json", b'{"code": -1}', b"[[1, 2]]", b'[["x", "1", "1", "1", "1", "1"]]']
    )
    def test_a_response_that_is_not_klines_is_an_error(self, body: bytes) -> None:
        with pytest.raises(n2.VerifyError):
            n2.parse_page(body)

    def test_a_figure_that_is_not_a_decimal_is_an_error(self) -> None:
        with pytest.raises(n2.VerifyError, match="not a decimal"):
            n2.parse_page(b'[[1, "a", "1", "1", "1", "1"]]')


class TestFetchUrl:
    class Recorder:
        def __init__(self, error: Exception | None = None) -> None:
            self.requests: list[urllib.request.Request] = []
            self.error = error

        def __call__(self, request: urllib.request.Request, timeout: float) -> io.BytesIO:
            self.requests.append(request)
            if self.error is not None:
                raise self.error
            return _Body(b"[]")

    def test_a_url_outside_the_klines_endpoint_is_refused_before_any_request(self) -> None:
        recorder = self.Recorder()
        for url in (
            "https://api.binance.com/api/v3/exchangeInfo",
            "https://api.binance.com/api/v3/klines",
            "https://testnet.binance.vision/api/v3/klines?symbol=BTCUSDT",
            "https://api.binance.com.evil.example/api/v3/klines?x=1",
        ):
            with pytest.raises(n2.VerifyError, match="outside the klines endpoint"):
                n2.fetch_url(url, opener=recorder)
        assert recorder.requests == []

    def test_the_request_carries_no_key_and_no_header_but_a_user_agent(self) -> None:
        recorder = self.Recorder()
        n2.fetch_url(n2.klines_url("BTCUSDT", "1d", 0, 1, 1000), opener=recorder)
        (request,) = recorder.requests
        assert dict(request.header_items()) == {"User-agent": "trading-bot-n2-verify/1"}

    def test_a_rate_limit_is_an_error_and_not_retried(self) -> None:
        recorder = self.Recorder(urllib.error.HTTPError("u", 429, "Too Many", {}, None))
        with pytest.raises(n2.VerifyError, match="HTTP 429"):
            n2.fetch_url(n2.klines_url("BTCUSDT", "1d", 0, 1, 1000), opener=recorder)
        assert len(recorder.requests) == 1

    def test_a_transport_failure_is_an_error(self) -> None:
        recorder = self.Recorder(urllib.error.URLError("down"))
        with pytest.raises(n2.VerifyError, match="down"):
            n2.fetch_url(n2.klines_url("BTCUSDT", "1d", 0, 1, 1000), opener=recorder)


class _Body(io.BytesIO):
    def __enter__(self) -> _Body:
        return self


class TestEvidenceIsKept:
    def test_every_raw_response_is_saved_with_its_sha256(self, tmp_path: Path) -> None:
        store = store_days(tmp_path / "s", "BTCUSDT", [DAY])
        venue = FakeVenue(table("BTCUSDT", DAY))
        go(tmp_path, store, venue, limit=2)
        out = tmp_path / "out"
        listed = (out / "responses.sha256").read_text(encoding="ascii").splitlines()
        saved = sorted(p.name for p in out.glob("*.json"))
        assert len(listed) == len(saved) == len(venue.urls)
        for line in listed:
            digest, _, name = line.partition("  ")
            assert hashlib.sha256((out / name).read_bytes()).hexdigest() == digest

    def test_the_digest_list_is_written_even_when_a_later_request_fails(
        self, tmp_path: Path
    ) -> None:
        store = store_days(tmp_path / "s", "BTCUSDT", [DAY])
        calls = {"n": 0}
        venue = FakeVenue(table("BTCUSDT", DAY))

        def failing(url: str) -> bytes:
            calls["n"] += 1
            if calls["n"] == 2:
                raise n2.VerifyError("boom")
            return venue(url)

        with pytest.raises(n2.VerifyError):
            n2.run(store, failing, tmp_path / "out", ("BTCUSDT",), pause=0.0)
        listed = (tmp_path / "out" / "responses.sha256").read_text(encoding="ascii").splitlines()
        assert len(listed) == 1


class TestRefusals:
    def test_an_out_directory_under_logs_is_refused(self, tmp_path: Path) -> None:
        assert n2.refuse_out(tmp_path / "logs" / "x", tmp_path / "store") is not None

    def test_an_out_directory_inside_the_store_is_refused(self, tmp_path: Path) -> None:
        assert n2.refuse_out(tmp_path / "store" / "sub", tmp_path / "store") is not None
        assert n2.refuse_out(tmp_path / "store", tmp_path / "store") is not None

    def test_an_out_directory_that_already_holds_files_is_refused(self, tmp_path: Path) -> None:
        out = tmp_path / "out"
        out.mkdir()
        (out / "keep.json").write_bytes(b"[]")
        assert n2.refuse_out(out, tmp_path / "store") is not None

    def test_a_new_or_empty_out_directory_is_accepted(self, tmp_path: Path) -> None:
        assert n2.refuse_out(tmp_path / "new", tmp_path / "store") is None
        (tmp_path / "empty").mkdir()
        assert n2.refuse_out(tmp_path / "empty", tmp_path / "store") is None

    def test_a_second_run_into_the_same_directory_is_refused_and_overwrites_nothing(
        self, tmp_path: Path
    ) -> None:
        store = store_days(tmp_path / "s", "BTCUSDT", [DAY])
        argv = ["--out", str(tmp_path / "out"), "--data-dir", str(tmp_path / "s")]
        argv += ["--symbols", "BTCUSDT"]
        venue = FakeVenue(table("BTCUSDT", DAY))
        first_out = io.StringIO()
        assert n2.main(argv, fetcher=venue, out=first_out) == 0
        before = {p.name: p.read_bytes() for p in (tmp_path / "out").iterdir()}
        second_out = io.StringIO()
        assert n2.main(argv, fetcher=venue, out=second_out) == n2.EXIT_REFUSED
        assert "REFUSED" in second_out.getvalue()
        assert {p.name: p.read_bytes() for p in (tmp_path / "out").iterdir()} == before
        assert store.root == tmp_path / "s"


class TestWhatIsPrinted:
    def run_main(self, tmp_path: Path, bars: dict[tuple[str, str], list[list[object]]]) -> str:
        store_days(tmp_path / "s", "BTCUSDT", [DAY])
        out = io.StringIO()
        argv = ["--out", str(tmp_path / "out"), "--data-dir", str(tmp_path / "s")]
        argv += ["--symbols", "BTCUSDT"]
        assert n2.main(argv, fetcher=FakeVenue(bars), out=out) == 0
        return out.getvalue()

    def test_a_clean_run_prints_counts_and_no_price_or_volume(self, tmp_path: Path) -> None:
        text = self.run_main(tmp_path, table("BTCUSDT", DAY))
        assert "N2 BAR VERIFICATION" in text
        assert "BTCUSDT 1d: requests=1 venue=1 aggregated=1" in text
        assert "MISMATCH LIST (0 rows, first 50 shown)" in text
        assert "aggregated=" not in text.split("MISMATCH LIST")[1]
        for literal in ("1000.00000000", "2479.00000000", "2880.00000000", "480.00000000"):
            assert literal not in text

    def test_the_mismatch_list_is_capped_at_fifty_rows(self, tmp_path: Path) -> None:
        days = [at(2017, 9, 1) + timedelta(days=d) for d in range(10)]
        store_days(tmp_path / "s", "BTCUSDT", days)
        wrong = [
            venue_row(ms(d) + k * WIDTH["4h"], ["1.00000000"] * 5, "4h")
            for d in days
            for k in range(6)
        ]
        bars = {("BTCUSDT", "4h"): wrong, ("BTCUSDT", "1d"): []}
        out = io.StringIO()
        argv = ["--out", str(tmp_path / "out"), "--data-dir", str(tmp_path / "s")]
        argv += ["--symbols", "BTCUSDT"]
        assert n2.main(argv, fetcher=FakeVenue(bars), out=out) == 0
        text = out.getvalue()
        listed = [line for line in text.splitlines() if "minutes_missing=" in line]
        assert "MISMATCH LIST (" in text
        assert len(listed) == n2.MISMATCH_CAP == 50
        assert "first 50 shown" in text

    def test_runs_of_unpaired_buckets_are_printed_with_their_times_and_count(
        self, tmp_path: Path
    ) -> None:
        bars = table("BTCUSDT", DAY)
        bars[("BTCUSDT", "1d")] += day_venue(at(2017, 12, 1), "1d") + day_venue(
            at(2017, 12, 2), "1d"
        )
        text = self.run_main(tmp_path, bars)
        assert "venue-only runs: 2017-12-01T00:00:00Z..2017-12-02T00:00:00Z x2" in text

    def test_a_fetch_error_is_an_error_exit_and_prints_no_result(self, tmp_path: Path) -> None:
        store_days(tmp_path / "s", "BTCUSDT", [DAY])

        def broken(_url: str) -> bytes:
            raise n2.VerifyError("HTTP 451")

        out = io.StringIO()
        argv = ["--out", str(tmp_path / "out"), "--data-dir", str(tmp_path / "s")]
        argv += ["--symbols", "BTCUSDT"]
        assert n2.main(argv, fetcher=broken, out=out) == n2.EXIT_ERROR
        assert out.getvalue().startswith("ERROR: VerifyError: HTTP 451")
        assert "N2 BAR VERIFICATION" not in out.getvalue()
