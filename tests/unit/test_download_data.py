"""``scripts/download_data.py``: listing, planning, idempotence and the failures it reports.

No test touches the network. A ``FakeArchive`` answers the fetcher's URLs from a table of
archive months and records every URL asked, so "a re-run fetches nothing" and "nothing
outside the archive's hosts is requested" are assertions about that record.
"""

from __future__ import annotations

import hashlib
import io
import json
import sys
import urllib.error
import urllib.request
import zipfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

import download_data as dl

from trading_bot.data.historical import (
    HistoricalStore,
    check_stored,
    month_bounds_ms,
    month_file,
)

SYMBOL = "BTCUSDT"
INTERVAL = "1d"
PREFIX = "data/spot/monthly/klines/BTCUSDT/1d/"


def archive_text(month: str, days: int) -> str:
    """A real-shaped 12-column daily archive: the first ``days`` days of ``month``."""
    start, _ = month_bounds_ms(month)
    step = 86_400_000
    lines = []
    for index in range(days):
        opened = start + index * step
        lines.append(
            f"{opened},10.00000000,12.50000000,9.00000000,11.00000000,1.00000000,"
            f"{opened + step - 1},11.00000000,1,0.50000000,5.50000000,0"
        )
    return "\n".join(lines) + "\n"


def zip_bytes(month: str, days: int = 3) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr(f"{SYMBOL}-{INTERVAL}-{month}.csv", archive_text(month, days))
    return buffer.getvalue()


def listing(keys: list[str], *, truncated: bool = False, next_marker: str | None = None) -> bytes:
    body = "".join(f"<Contents><Key>{key}</Key></Contents>" for key in keys)
    flag = "true" if truncated else "false"
    marker = f"<NextMarker>{next_marker}</NextMarker>" if next_marker else ""
    return (
        f'<?xml version="1.0"?><ListBucketResult><IsTruncated>{flag}</IsTruncated>'
        f"{marker}{body}</ListBucketResult>"
    ).encode()


class FakeArchive:
    """Answers the archive's URLs for one series and records each one asked."""

    def __init__(self, months: list[str], *, days: int = 3) -> None:
        self.zips = {month: zip_bytes(month, days) for month in months}
        self.checksums = {
            month: f"{hashlib.sha256(data).hexdigest()}  {SYMBOL}-{INTERVAL}-{month}.zip\n"
            for month, data in self.zips.items()
        }
        self.asked: list[str] = []
        self.listed = list(months)

    def keys(self) -> list[str]:
        out = []
        for month in sorted(self.listed):
            out.append(f"{PREFIX}{SYMBOL}-{INTERVAL}-{month}.zip")
            out.append(f"{PREFIX}{SYMBOL}-{INTERVAL}-{month}.zip.CHECKSUM")
        return out

    def __call__(self, url: str) -> bytes:
        self.asked.append(url)
        if url.startswith(dl.LISTING_BASE):
            return listing(self.keys())
        for month in self.zips:
            if url == dl.month_url(SYMBOL, INTERVAL, month, suffix="zip"):
                return self.zips[month]
            if url == dl.month_url(SYMBOL, INTERVAL, month, suffix="CHECKSUM"):
                return self.checksums[month].encode()
        raise dl.DownloadError(f"{url}: HTTP 404", retryable=False)

    def zip_requests(self) -> list[str]:
        return [url for url in self.asked if url.endswith(".zip")]


def run(archive: dl.Fetcher, root: Path, *extra: str, through: str = "2024-12") -> tuple[int, str]:
    out = io.StringIO()
    argv = [
        "--through", through, "--symbols", SYMBOL, "--intervals", INTERVAL,
        "--data-dir", str(root), *extra,
    ]  # fmt: skip
    code = dl.run(argv, fetcher=archive, out=out)
    return code, out.getvalue()


class TestListMonths:
    def test_zips_are_listed_oldest_first_and_checksums_are_not_months(self) -> None:
        archive = FakeArchive(["2024-12", "2024-10", "2024-11"])
        assert dl.list_months(archive, SYMBOL, INTERVAL) == ("2024-10", "2024-11", "2024-12")

    def test_keys_of_another_series_or_shape_are_ignored(self) -> None:
        keys = [
            f"{PREFIX}BTCUSDT-1d-2024-10.zip",
            f"{PREFIX}BTCUSDT-1d-2024-10.zip.CHECKSUM",
            f"{PREFIX}BTCUSDT-1d-2024-1.zip",
            f"{PREFIX}BTCUSDT-1d-2024-11.zip.bak",
            f"{PREFIX}ETHUSDT-1d-2024-11.zip",
            "data/spot/monthly/klines/BTCUSDT/1h/BTCUSDT-1h-2024-12.zip",
        ]
        assert dl.list_months(lambda _url: listing(keys), SYMBOL, INTERVAL) == ("2024-10",)

    def test_the_listing_is_asked_for_this_series_prefix_only(self) -> None:
        archive = FakeArchive(["2024-12"])
        dl.list_months(archive, SYMBOL, INTERVAL)
        assert archive.asked == [f"{dl.LISTING_BASE}?delimiter=/&prefix={PREFIX}"]

    def test_a_truncated_listing_is_followed_by_its_next_marker(self) -> None:
        first = f"{PREFIX}BTCUSDT-1d-2024-10.zip"
        second = f"{PREFIX}BTCUSDT-1d-2024-11.zip"
        asked: list[str] = []
        pages = [listing([first], truncated=True, next_marker=first), listing([second])]

        def fetcher(url: str) -> bytes:
            asked.append(url)
            return pages[len(asked) - 1]

        assert dl.list_months(fetcher, SYMBOL, INTERVAL) == ("2024-10", "2024-11")
        assert asked[1] == f"{dl.LISTING_BASE}?delimiter=/&prefix={PREFIX}&marker={first}"

    def test_without_a_next_marker_the_last_key_is_the_marker(self) -> None:
        first = f"{PREFIX}BTCUSDT-1d-2024-10.zip"
        asked: list[str] = []
        pages = [listing([first], truncated=True), listing([])]

        def fetcher(url: str) -> bytes:
            asked.append(url)
            return pages[len(asked) - 1]

        assert dl.list_months(fetcher, SYMBOL, INTERVAL) == ("2024-10",)
        assert asked[1].endswith(f"&marker={first}")

    def test_a_truncated_page_with_nothing_to_continue_from_is_refused(self) -> None:
        with pytest.raises(dl.DownloadError, match="next page"):
            dl.list_months(lambda _url: listing([], truncated=True), SYMBOL, INTERVAL)


class TestMonthUrl:
    def test_the_zip_and_its_checksum_urls(self) -> None:
        base = f"{dl.DATA_BASE}/data/spot/monthly/klines/BTCUSDT/1d/BTCUSDT-1d-2024-12.zip"
        assert dl.month_url(SYMBOL, INTERVAL, "2024-12", suffix="zip") == base
        assert dl.month_url(SYMBOL, INTERVAL, "2024-12", suffix="CHECKSUM") == base + ".CHECKSUM"


class TestDownload:
    def test_every_listed_month_through_the_last_is_stored_and_verifies(
        self, tmp_path: Path
    ) -> None:
        archive = FakeArchive(["2024-10", "2024-11", "2024-12"])
        code, text = run(archive, tmp_path)
        assert code == 0
        assert "BTCUSDT 1d: listed 3, stored 3, skipped 0, failed 0" in text
        report = check_stored(tmp_path, SYMBOL, INTERVAL)
        assert sorted(report.entries) == ["2024-10", "2024-11", "2024-12"]
        assert report.problems == ()

    def test_the_manifest_records_the_zip_url_and_the_checksum_it_was_verified_against(
        self, tmp_path: Path
    ) -> None:
        archive = FakeArchive(["2024-12"])
        run(archive, tmp_path)
        entry = check_stored(tmp_path, SYMBOL, INTERVAL).entries["2024-12"]
        assert entry.source_url == dl.month_url(SYMBOL, INTERVAL, "2024-12", suffix="zip")
        assert entry.zip_sha256 == hashlib.sha256(archive.zips["2024-12"]).hexdigest()
        assert entry.rows == 3

    def test_months_after_through_are_not_stored(self, tmp_path: Path) -> None:
        archive = FakeArchive(["2024-11", "2024-12", "2025-01"])
        code, text = run(archive, tmp_path, through="2024-12")
        assert code == 0
        assert "listed 2, stored 2" in text
        assert sorted(check_stored(tmp_path, SYMBOL, INTERVAL).entries) == ["2024-11", "2024-12"]
        assert not any("2025-01" in url for url in archive.asked)

    def test_a_month_the_archive_does_not_list_is_a_gap_and_nothing_is_requested_for_it(
        self, tmp_path: Path
    ) -> None:
        archive = FakeArchive(["2024-10", "2024-12"])
        code, _ = run(archive, tmp_path)
        assert code == 0
        assert not any("2024-11" in url for url in archive.asked)
        coverage = HistoricalStore(tmp_path).coverage(SYMBOL, INTERVAL)
        assert coverage.months == ("2024-10", "2024-12")
        assert coverage.missing > 0

    def test_only_the_archives_two_hosts_are_asked(self, tmp_path: Path) -> None:
        archive = FakeArchive(["2024-11", "2024-12"])
        run(archive, tmp_path)
        assert archive.asked
        assert all(
            url.startswith((dl.LISTING_BASE + "?", dl.DATA_BASE + "/")) for url in archive.asked
        )


class TestIdempotence:
    def test_a_second_run_requests_no_zip_and_no_checksum(self, tmp_path: Path) -> None:
        archive = FakeArchive(["2024-11", "2024-12"])
        run(archive, tmp_path)
        again = FakeArchive(["2024-11", "2024-12"])
        code, text = run(again, tmp_path)
        assert code == 0
        assert "listed 2, stored 0, skipped 2, failed 0" in text
        assert len(again.asked) == 1
        assert again.asked[0].startswith(dl.LISTING_BASE)

    def test_a_run_after_an_interruption_fetches_only_the_missing_month(
        self, tmp_path: Path
    ) -> None:
        run(FakeArchive(["2024-11"]), tmp_path, through="2024-11")
        archive = FakeArchive(["2024-11", "2024-12"])
        code, text = run(archive, tmp_path)
        assert code == 0
        assert "stored 1, skipped 1" in text
        assert archive.zip_requests() == [dl.month_url(SYMBOL, INTERVAL, "2024-12", suffix="zip")]

    def test_a_stored_file_that_no_longer_matches_its_manifest_is_fetched_again(
        self, tmp_path: Path
    ) -> None:
        run(FakeArchive(["2024-12"]), tmp_path)
        path = month_file(tmp_path, SYMBOL, INTERVAL, "2024-12")
        path.write_bytes(path.read_bytes().replace(b"10.00000000", b"99.00000000"))
        archive = FakeArchive(["2024-12"])
        code, text = run(archive, tmp_path)
        assert code == 0
        assert "stored 1, skipped 0" in text
        assert check_stored(tmp_path, SYMBOL, INTERVAL).problems == ()

    def test_the_manifest_after_a_second_run_is_byte_identical(self, tmp_path: Path) -> None:
        run(FakeArchive(["2024-11", "2024-12"]), tmp_path)
        manifest = tmp_path / SYMBOL / INTERVAL / "MANIFEST.jsonl"
        before = manifest.read_bytes()
        run(FakeArchive(["2024-11", "2024-12"]), tmp_path)
        assert manifest.read_bytes() == before


class TestFailuresAreReportedNotHidden:
    def test_a_checksum_mismatch_stores_nothing_for_that_month_and_exits_non_zero(
        self, tmp_path: Path
    ) -> None:
        archive = FakeArchive(["2024-11", "2024-12"])
        archive.checksums["2024-11"] = f"{'0' * 64}  {SYMBOL}-{INTERVAL}-2024-11.zip\n"
        code, text = run(archive, tmp_path)
        assert code == 1
        assert "FAILED BTCUSDT 1d 2024-11: ChecksumMismatchError" in text
        assert "listed 2, stored 1, skipped 0, failed 1" in text
        report = check_stored(tmp_path, SYMBOL, INTERVAL)
        assert sorted(report.entries) == ["2024-12"]
        assert not month_file(tmp_path, SYMBOL, INTERVAL, "2024-11").exists()

    def test_a_checksum_for_another_file_is_a_failure(self, tmp_path: Path) -> None:
        archive = FakeArchive(["2024-12"])
        archive.checksums["2024-12"] = archive.checksums["2024-12"].replace("2024-12", "2024-11")
        code, text = run(archive, tmp_path)
        assert code == 1
        assert "FAILED BTCUSDT 1d 2024-12: ArchiveFormatError" in text

    def test_an_archive_that_fails_validation_is_a_failure_and_the_run_continues(
        self, tmp_path: Path
    ) -> None:
        archive = FakeArchive(["2024-11", "2024-12"])
        bad = zip_bytes("2024-11").replace(b"10.00000000", b"1x.00000000")
        archive.zips["2024-11"] = bad
        archive.checksums["2024-11"] = (
            f"{hashlib.sha256(bad).hexdigest()}  {SYMBOL}-{INTERVAL}-2024-11.zip\n"
        )
        code, text = run(archive, tmp_path)
        assert code == 1
        assert "FAILED BTCUSDT 1d 2024-11" in text
        assert sorted(check_stored(tmp_path, SYMBOL, INTERVAL).entries) == ["2024-12"]

    def test_a_missing_download_is_a_failure_for_that_month(self, tmp_path: Path) -> None:
        archive = FakeArchive(["2024-11", "2024-12"])
        del archive.zips["2024-11"]
        code, text = run(archive, tmp_path)
        assert code == 1
        assert "FAILED" in text and "2024-11" in text
        assert sorted(check_stored(tmp_path, SYMBOL, INTERVAL).entries) == ["2024-12"]

    def test_a_series_the_archive_does_not_list_is_a_failure_not_a_green_run(
        self, tmp_path: Path
    ) -> None:
        code, text = run(lambda _url: listing([]), tmp_path)
        assert code == 1
        assert "lists no month of BTCUSDT 1d through 2024-12" in text

    def test_a_listing_that_fails_is_reported_as_the_series_failure(self, tmp_path: Path) -> None:
        def broken(url: str) -> bytes:
            raise dl.DownloadError(f"{url}: HTTP 503", retryable=False)

        code, text = run(broken, tmp_path)
        assert code == 1
        assert "listing failed" in text

    def test_a_failed_month_is_fetched_again_by_the_next_run(self, tmp_path: Path) -> None:
        archive = FakeArchive(["2024-12"])
        good = archive.checksums["2024-12"]
        archive.checksums["2024-12"] = f"{'0' * 64}  {SYMBOL}-{INTERVAL}-2024-12.zip\n"
        assert run(archive, tmp_path)[0] == 1
        archive.checksums["2024-12"] = good
        assert run(archive, tmp_path)[0] == 0
        assert sorted(check_stored(tmp_path, SYMBOL, INTERVAL).entries) == ["2024-12"]


class TestDryRun:
    def test_it_lists_and_plans_and_stores_and_fetches_nothing_else(self, tmp_path: Path) -> None:
        archive = FakeArchive(["2024-11", "2024-12"])
        code, text = run(archive, tmp_path, "--dry-run")
        assert code == 0
        assert "listed 2, would store 2, skipped 0, failed 0" in text
        assert len(archive.asked) == 1
        assert not (tmp_path / SYMBOL).exists()

    def test_it_counts_a_stored_month_as_skipped(self, tmp_path: Path) -> None:
        run(FakeArchive(["2024-11"]), tmp_path, through="2024-11")
        archive = FakeArchive(["2024-11", "2024-12"])
        _, text = run(archive, tmp_path, "--dry-run")
        assert "listed 2, would store 1, skipped 1" in text


class TestRefusals:
    def test_a_bad_symbol_is_refused_before_any_request(self, tmp_path: Path) -> None:
        archive = FakeArchive(["2024-12"])
        out = io.StringIO()
        code = dl.run(
            ["--through", "2024-12", "--symbols", SYMBOL, "../x", "--intervals", INTERVAL,
             "--data-dir", str(tmp_path)],
            fetcher=archive,
            out=out,
        )  # fmt: skip
        assert code == 2
        assert archive.asked == []
        assert "refused" in out.getvalue()

    def test_an_interval_that_is_not_stored_is_refused_before_any_request(
        self, tmp_path: Path
    ) -> None:
        archive = FakeArchive(["2024-12"])
        out = io.StringIO()
        code = dl.run(
            ["--through", "2024-12", "--symbols", SYMBOL, "--intervals", "3m",
             "--data-dir", str(tmp_path)],
            fetcher=archive,
            out=out,
        )  # fmt: skip
        assert code == 2
        assert archive.asked == []

    @pytest.mark.parametrize("through", ["2024", "2024-13", "2024-00", "2024-1", "last month"])
    def test_a_through_that_is_not_a_month_is_refused(self, tmp_path: Path, through: str) -> None:
        archive = FakeArchive(["2024-12"])
        code, text = run(archive, tmp_path, through=through)
        assert code == 2
        assert archive.asked == []
        assert "YYYY-MM" in text

    def test_through_is_required(self) -> None:
        with pytest.raises(SystemExit) as raised:
            dl.run([], fetcher=FakeArchive([]), out=io.StringIO())
        assert raised.value.code == 2


class TestWithRetries:
    def test_a_retryable_failure_is_retried_with_a_growing_wait_and_then_succeeds(self) -> None:
        calls: list[str] = []
        waits: list[float] = []

        def flaky(url: str) -> bytes:
            calls.append(url)
            if len(calls) < 3:
                raise dl.DownloadError("reset", retryable=True)
            return b"ok"

        assert dl.with_retries(flaky, attempts=3, sleep=waits.append)("u") == b"ok"
        assert len(calls) == 3
        assert waits == [1.0, 2.0]

    def test_a_retryable_failure_that_never_clears_is_raised_after_the_last_attempt(self) -> None:
        calls: list[str] = []
        waits: list[float] = []

        def down(url: str) -> bytes:
            calls.append(url)
            raise dl.DownloadError("reset", retryable=True)

        with pytest.raises(dl.DownloadError, match="reset"):
            dl.with_retries(down, attempts=3, sleep=waits.append)("u")
        assert len(calls) == 3
        assert waits == [1.0, 2.0]

    def test_a_non_retryable_failure_is_raised_at_once(self) -> None:
        calls: list[str] = []
        waits: list[float] = []

        def missing(url: str) -> bytes:
            calls.append(url)
            raise dl.DownloadError("HTTP 404", retryable=False)

        with pytest.raises(dl.DownloadError, match="404"):
            dl.with_retries(missing, attempts=3, sleep=waits.append)("u")
        assert len(calls) == 1
        assert waits == []


class _Body:
    def __init__(self, data: bytes) -> None:
        self._data = data

    def read(self, size: int = -1, /) -> bytes:
        return self._data if size < 0 else self._data[:size]

    def __enter__(self) -> _Body:
        return self

    def __exit__(self, *exc: object) -> None:
        return None


class TestFetchUrl:
    GOOD = f"{dl.DATA_BASE}/data/spot/monthly/klines/BTCUSDT/1d/BTCUSDT-1d-2024-12.zip"

    def test_a_body_is_returned_and_the_request_is_sent_with_a_user_agent(self) -> None:
        seen: list[urllib.request.Request] = []

        def opener(request: urllib.request.Request, timeout: float) -> _Body:
            seen.append(request)
            assert timeout == dl._TIMEOUT_S
            return _Body(b"payload")

        assert dl.fetch_url(self.GOOD, opener=opener) == b"payload"
        assert seen[0].full_url == self.GOOD
        assert seen[0].get_header("User-agent") == "trading-bot-historical/1"

    @pytest.mark.parametrize(
        "url",
        [
            "http://data.binance.vision/data/x.zip",
            "https://example.invalid/data.zip",
            "https://data.binance.vision.evil.invalid/x.zip",
            "file:///etc/passwd",
            "https://data.binance.vision",
        ],
    )
    def test_a_url_outside_the_archives_hosts_is_refused_before_any_request(self, url: str) -> None:
        def opener(request: urllib.request.Request, timeout: float) -> _Body:
            pytest.fail("a socket was opened for a refused URL")

        with pytest.raises(dl.DownloadError, match="outside") as raised:
            dl.fetch_url(url, opener=opener)
        assert raised.value.retryable is False

    def test_an_http_error_below_500_is_not_retryable_and_names_the_status(self) -> None:
        def opener(request: urllib.request.Request, timeout: float) -> _Body:
            raise urllib.error.HTTPError(request.full_url, 404, "Not Found", None, None)  # type: ignore[arg-type]

        with pytest.raises(dl.DownloadError, match="HTTP 404") as raised:
            dl.fetch_url(self.GOOD, opener=opener)
        assert raised.value.retryable is False

    def test_a_server_error_is_retryable(self) -> None:
        def opener(request: urllib.request.Request, timeout: float) -> _Body:
            raise urllib.error.HTTPError(request.full_url, 503, "Unavailable", None, None)  # type: ignore[arg-type]

        with pytest.raises(dl.DownloadError) as raised:
            dl.fetch_url(self.GOOD, opener=opener)
        assert raised.value.retryable is True

    @pytest.mark.parametrize(
        "error",
        [urllib.error.URLError("dns"), TimeoutError("slow"), ConnectionResetError("reset")],
    )
    def test_a_transport_fault_is_retryable(self, error: Exception) -> None:
        def opener(request: urllib.request.Request, timeout: float) -> _Body:
            raise error

        with pytest.raises(dl.DownloadError) as raised:
            dl.fetch_url(self.GOOD, opener=opener)
        assert raised.value.retryable is True

    def test_a_body_past_the_cap_is_refused_and_not_retryable(self) -> None:
        def opener(request: urllib.request.Request, timeout: float) -> _Body:
            return _Body(b"x" * (dl._MAX_DOWNLOAD_BYTES + 1))

        with pytest.raises(dl.DownloadError, match="more than") as raised:
            dl.fetch_url(self.GOOD, opener=opener)
        assert raised.value.retryable is False

    def test_the_cap_refuses_one_byte_over_and_accepts_exactly_the_cap(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(dl, "_MAX_DOWNLOAD_BYTES", 10)

        def opener(request: urllib.request.Request, timeout: float) -> _Body:
            return _Body(b"x" * 11)

        with pytest.raises(dl.DownloadError):
            dl.fetch_url(self.GOOD, opener=opener)

        def exact(request: urllib.request.Request, timeout: float) -> _Body:
            return _Body(b"x" * 10)

        assert dl.fetch_url(self.GOOD, opener=exact) == b"x" * 10


class TestManifestShape:
    def test_each_downloaded_month_is_one_sorted_manifest_line(self, tmp_path: Path) -> None:
        run(FakeArchive(["2024-12", "2024-10", "2024-11"]), tmp_path)
        lines = (tmp_path / SYMBOL / INTERVAL / "MANIFEST.jsonl").read_text().splitlines()
        assert [json.loads(line)["month"] for line in lines] == ["2024-10", "2024-11", "2024-12"]
