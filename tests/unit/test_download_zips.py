"""``scripts/download_data.py`` keeps every zip and ingests from disk (owner's ruling R-O).

No test touches the network: a ``FakeArchive`` answers the archive's URLs from a table and
records every URL it was asked, so "no zip was fetched" is an assertion about that record.
"""

from __future__ import annotations

import hashlib
import io
import json
import sys
import zipfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

import download_data as dl

from trading_bot.data.historical import (
    REGISTRY_NAME,
    ArchiveFormatError,
    HistoricalStore,
    check_stored,
    month_bounds_ms,
)

SYMBOL = "BTCUSDT"
INTERVAL = "1d"
PREFIX = "data/spot/monthly/klines/BTCUSDT/1d/"
DAY = 86_400_000


def line(opened: int, closed: int) -> str:
    return (
        f"{opened},10.00000000,12.50000000,9.00000000,11.00000000,1.00000000,"
        f"{closed},11.00000000,1,0.50000000,5.50000000,0"
    )


def regular_text(month: str, days: int = 3) -> str:
    start, _ = month_bounds_ms(month)
    return "\n".join(line(start + i * DAY, start + (i + 1) * DAY - 1) for i in range(days)) + "\n"


def irregular_text(month: str) -> str:
    """Day 1 regular, day 2 a short bar, day 3 off the grid (quarantined), day 4 regular."""
    start, _ = month_bounds_ms(month)
    rows = [
        line(start, start + DAY - 1),
        line(start + DAY, start + DAY + 3_600_000),
        line(start + 2 * DAY + 21_600_000, start + 3 * DAY + 21_599_999),
        line(start + 3 * DAY, start + 4 * DAY - 1),
    ]
    return "\n".join(rows) + "\n"


def zip_of(month: str, text: str) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr(f"{SYMBOL}-{INTERVAL}-{month}.csv", text)
    return buffer.getvalue()


def listing(months: list[str]) -> bytes:
    keys = "".join(
        f"<Contents><Key>{PREFIX}{SYMBOL}-{INTERVAL}-{m}.zip</Key></Contents>" for m in months
    )
    return f"<ListBucketResult><IsTruncated>false</IsTruncated>{keys}</ListBucketResult>".encode()


class FakeArchive:
    """Answers the archive's URLs for one series and records each one asked."""

    def __init__(self, months: list[str], *, texts: dict[str, str] | None = None) -> None:
        texts = texts or {}
        self.months = list(months)
        self.zips = {m: zip_of(m, texts.get(m, regular_text(m))) for m in months}
        self.sums = {
            m: f"{hashlib.sha256(z).hexdigest()}  {SYMBOL}-{INTERVAL}-{m}.zip\n"
            for m, z in self.zips.items()
        }
        self.asked: list[str] = []

    def __call__(self, url: str) -> bytes:
        self.asked.append(url)
        if url.startswith(dl.LISTING_BASE):
            return listing(self.months)
        for month in self.zips:
            if url == dl.month_url(SYMBOL, INTERVAL, month, suffix="zip"):
                return self.zips[month]
            if url == dl.month_url(SYMBOL, INTERVAL, month, suffix="CHECKSUM"):
                return self.sums[month].encode()
        raise dl.DownloadError(f"{url}: HTTP 404", retryable=False)

    def zip_requests(self) -> list[str]:
        return [u for u in self.asked if u.endswith(".zip")]

    def checksum_requests(self) -> list[str]:
        return [u for u in self.asked if u.endswith(".CHECKSUM")]


def run(fetcher: dl.Fetcher, root: Path, *extra: str, through: str = "2024-12") -> tuple[int, str]:
    out = io.StringIO()
    argv = [
        "--through", through, "--symbols", SYMBOL, "--intervals", INTERVAL,
        "--data-dir", str(root), *extra,
    ]  # fmt: skip
    code = dl.run(argv, fetcher=fetcher, out=out)
    return code, out.getvalue()


def zips_dir(root: Path) -> Path:
    return root / "_zips" / SYMBOL / INTERVAL


def kept(root: Path) -> list[str]:
    directory = zips_dir(root)
    return sorted(p.name for p in directory.iterdir()) if directory.is_dir() else []


class TestEveryZipIsKept:
    def test_a_zip_and_its_checksum_are_kept_under_the_series_beside_the_store(
        self, tmp_path: Path
    ) -> None:
        archive = FakeArchive(["2024-11", "2024-12"])
        code, _ = run(archive, tmp_path)
        assert code == 0
        assert kept(tmp_path) == [
            "BTCUSDT-1d-2024-11.zip",
            "BTCUSDT-1d-2024-11.zip.CHECKSUM",
            "BTCUSDT-1d-2024-12.zip",
            "BTCUSDT-1d-2024-12.zip.CHECKSUM",
        ]

    def test_the_kept_bytes_are_the_archives_own(self, tmp_path: Path) -> None:
        archive = FakeArchive(["2024-12"])
        run(archive, tmp_path)
        assert (zips_dir(tmp_path) / "BTCUSDT-1d-2024-12.zip").read_bytes() == archive.zips[
            "2024-12"
        ]
        assert (zips_dir(tmp_path) / "BTCUSDT-1d-2024-12.zip.CHECKSUM").read_text(
            encoding="utf-8"
        ) == archive.sums["2024-12"]

    def test_the_zip_directory_is_not_a_series_and_the_store_does_not_see_it(
        self, tmp_path: Path
    ) -> None:
        run(FakeArchive(["2024-12"]), tmp_path)
        assert check_stored(tmp_path, SYMBOL, INTERVAL).problems == ()
        assert HistoricalStore(tmp_path).verify(SYMBOL, INTERVAL) == ()

    def test_a_month_after_through_is_not_kept(self, tmp_path: Path) -> None:
        run(FakeArchive(["2024-12", "2025-01"]), tmp_path, through="2024-12")
        assert kept(tmp_path) == ["BTCUSDT-1d-2024-12.zip", "BTCUSDT-1d-2024-12.zip.CHECKSUM"]

    def test_a_dry_run_keeps_nothing_and_makes_no_directory(self, tmp_path: Path) -> None:
        run(FakeArchive(["2024-12"]), tmp_path, "--dry-run")
        assert not (tmp_path / "_zips").exists()

    def test_no_temporary_file_is_left_beside_a_kept_zip(self, tmp_path: Path) -> None:
        run(FakeArchive(["2024-12"]), tmp_path)
        assert not [name for name in kept(tmp_path) if name.endswith(".tmp")]

    def test_the_kept_zips_path_is_validated_like_a_series(self, tmp_path: Path) -> None:
        assert dl.zip_file(tmp_path, SYMBOL, INTERVAL, "2024-12") == (
            tmp_path / "_zips" / SYMBOL / INTERVAL / "BTCUSDT-1d-2024-12.zip"
        )
        with pytest.raises(ArchiveFormatError, match="not a symbol"):
            dl.zip_file(tmp_path, "../x", INTERVAL, "2024-12")


class TestIngestReadsTheKeptZip:
    def test_a_month_deleted_from_the_store_is_stored_again_from_disk_with_no_request(
        self, tmp_path: Path
    ) -> None:
        run(FakeArchive(["2024-12"]), tmp_path)
        (tmp_path / SYMBOL / INTERVAL / "MANIFEST.jsonl").unlink()
        (tmp_path / SYMBOL / INTERVAL / "BTCUSDT-1d-2024-12.csv").unlink()
        again = FakeArchive(["2024-12"])
        code, text = run(again, tmp_path)
        assert code == 0
        assert "stored 1" in text and "fetched 0, reused 1" in text
        assert again.zip_requests() == []
        assert again.checksum_requests() == []
        assert check_stored(tmp_path, SYMBOL, INTERVAL).problems == ()

    def test_what_is_ingested_is_what_was_read_back_from_disk(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        real = dl.write_atomic

        def corrupting(path: Path, data: bytes) -> None:
            real(path, data + b"x" if path.suffix == ".zip" else data)

        monkeypatch.setattr(dl, "write_atomic", corrupting)
        code, text = run(FakeArchive(["2024-12"]), tmp_path)
        assert code == 1
        assert "FAILED BTCUSDT 1d 2024-12: ChecksumMismatchError" in text
        assert check_stored(tmp_path, SYMBOL, INTERVAL).entries == {}

    def test_a_failed_write_is_a_failed_month_and_leaves_no_zip(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def broken(*_args: object) -> None:
            raise OSError("disk full")

        monkeypatch.setattr(dl.os, "replace", broken)
        code, text = run(FakeArchive(["2024-12"]), tmp_path)
        assert code == 1
        assert "FAILED BTCUSDT 1d 2024-12: OSError" in text
        assert kept(tmp_path) == []


class TestAZipAlreadyOnDisk:
    def test_one_equal_to_its_checksum_is_not_fetched_and_neither_is_its_checksum(
        self, tmp_path: Path
    ) -> None:
        run(FakeArchive(["2024-12"]), tmp_path)
        for name in ("MANIFEST.jsonl", "BTCUSDT-1d-2024-12.csv"):
            (tmp_path / SYMBOL / INTERVAL / name).unlink()
        again = FakeArchive(["2024-12"])
        run(again, tmp_path)
        assert again.asked and all(u.startswith(dl.LISTING_BASE) for u in again.asked)

    def test_one_with_no_checksum_file_gets_only_its_checksum_fetched(self, tmp_path: Path) -> None:
        run(FakeArchive(["2024-12"]), tmp_path)
        for name in ("MANIFEST.jsonl", "BTCUSDT-1d-2024-12.csv"):
            (tmp_path / SYMBOL / INTERVAL / name).unlink()
        (zips_dir(tmp_path) / "BTCUSDT-1d-2024-12.zip.CHECKSUM").unlink()
        again = FakeArchive(["2024-12"])
        code, _ = run(again, tmp_path)
        assert code == 0
        assert again.zip_requests() == []
        assert len(again.checksum_requests()) == 1
        assert (zips_dir(tmp_path) / "BTCUSDT-1d-2024-12.zip.CHECKSUM").read_text(
            encoding="utf-8"
        ) == again.sums["2024-12"]

    def test_one_that_does_not_match_its_checksum_is_fetched_and_replaced(
        self, tmp_path: Path
    ) -> None:
        run(FakeArchive(["2024-12"]), tmp_path)
        for name in ("MANIFEST.jsonl", "BTCUSDT-1d-2024-12.csv"):
            (tmp_path / SYMBOL / INTERVAL / name).unlink()
        path = zips_dir(tmp_path) / "BTCUSDT-1d-2024-12.zip"
        path.write_bytes(path.read_bytes() + b"corrupt")
        again = FakeArchive(["2024-12"])
        code, text = run(again, tmp_path)
        assert code == 0
        assert "fetched 1, reused 0" in text
        assert path.read_bytes() == again.zips["2024-12"]
        assert len(again.zip_requests()) == 1

    def test_a_download_that_fails_its_checksum_writes_nothing_for_the_month(
        self, tmp_path: Path
    ) -> None:
        archive = FakeArchive(["2024-11", "2024-12"])
        archive.sums["2024-11"] = f"{'0' * 64}  {SYMBOL}-{INTERVAL}-2024-11.zip\n"
        code, text = run(archive, tmp_path)
        assert code == 1
        assert "FAILED BTCUSDT 1d 2024-11: ChecksumMismatchError" in text
        assert kept(tmp_path) == ["BTCUSDT-1d-2024-12.zip", "BTCUSDT-1d-2024-12.zip.CHECKSUM"]

    def test_a_zip_that_passes_its_checksum_but_fails_validation_stays_for_diagnosis(
        self, tmp_path: Path
    ) -> None:
        bad = regular_text("2024-12").replace("10.00000000", "1x.00000000", 1)
        archive = FakeArchive(["2024-12"], texts={"2024-12": bad})
        code, text = run(archive, tmp_path)
        assert code == 1
        assert "FAILED BTCUSDT 1d 2024-12: ArchiveFormatError" in text
        assert "BTCUSDT-1d-2024-12.zip" in kept(tmp_path)
        assert check_stored(tmp_path, SYMBOL, INTERVAL).entries == {}


class TestOffline:
    def seeded(self, root: Path, months: list[str]) -> FakeArchive:
        archive = FakeArchive(months)
        run(archive, root)
        for month in months:
            (root / SYMBOL / INTERVAL / f"BTCUSDT-1d-{month}.csv").unlink()
        (root / SYMBOL / INTERVAL / "MANIFEST.jsonl").unlink()
        return archive

    def test_the_zips_on_disk_are_ingested_and_the_fetcher_is_never_called(
        self, tmp_path: Path
    ) -> None:
        self.seeded(tmp_path, ["2024-11", "2024-12"])
        calls: list[str] = []

        def recorder(url: str) -> bytes:
            calls.append(url)
            return b""

        result = dl.download_series(
            recorder, tmp_path, SYMBOL, INTERVAL, "2024-12", offline=True, out=io.StringIO()
        )
        assert calls == []
        assert (result.downloaded, result.failed, result.reused) == (
            ["2024-11", "2024-12"],
            {},
            ["2024-11", "2024-12"],
        )
        assert sorted(check_stored(tmp_path, SYMBOL, INTERVAL).entries) == ["2024-11", "2024-12"]

    def test_the_command_line_flag_replaces_even_an_injected_fetcher(self, tmp_path: Path) -> None:
        self.seeded(tmp_path, ["2024-12"])
        calls: list[str] = []

        def recorder(url: str) -> bytes:
            calls.append(url)
            return b""

        code, text = run(recorder, tmp_path, "--offline")
        assert code == 0
        assert calls == []
        assert "fetched 0, reused 1" in text

    def test_a_zip_with_no_checksum_file_fails_instead_of_being_fetched(
        self, tmp_path: Path
    ) -> None:
        self.seeded(tmp_path, ["2024-12"])
        (zips_dir(tmp_path) / "BTCUSDT-1d-2024-12.zip.CHECKSUM").unlink()
        code, text = run(FakeArchive(["2024-12"]), tmp_path, "--offline")
        assert code == 1
        assert (
            "FAILED BTCUSDT 1d 2024-12: DownloadError: no request is allowed with --offline" in text
        )

    def test_a_zip_that_does_not_match_its_checksum_fails_instead_of_being_fetched(
        self, tmp_path: Path
    ) -> None:
        self.seeded(tmp_path, ["2024-12"])
        path = zips_dir(tmp_path) / "BTCUSDT-1d-2024-12.zip"
        path.write_bytes(path.read_bytes() + b"corrupt")
        code, text = run(FakeArchive(["2024-12"]), tmp_path, "--offline")
        assert code == 1
        assert "does not match its CHECKSUM, and --offline fetches nothing" in text
        assert check_stored(tmp_path, SYMBOL, INTERVAL).entries == {}

    def test_with_no_zip_on_disk_the_series_is_a_failure_not_a_green_run(
        self, tmp_path: Path
    ) -> None:
        code, text = run(FakeArchive(["2024-12"]), tmp_path, "--offline")
        assert code == 1
        assert "no zip of BTCUSDT 1d through 2024-12 is on disk" in text

    def test_a_month_already_stored_is_skipped_without_reading_its_zip(
        self, tmp_path: Path
    ) -> None:
        run(FakeArchive(["2024-12"]), tmp_path)
        (zips_dir(tmp_path) / "BTCUSDT-1d-2024-12.zip").write_bytes(b"not even a zip")
        code, text = run(FakeArchive(["2024-12"]), tmp_path, "--offline")
        assert code == 0
        assert "stored 0, skipped 1, failed 0" in text

    def test_through_limits_the_months_taken_from_disk(self, tmp_path: Path) -> None:
        self.seeded(tmp_path, ["2024-11", "2024-12"])
        code, text = run(FakeArchive([]), tmp_path, "--offline", through="2024-11")
        assert code == 0
        assert "listed 1, stored 1" in text

    def test_a_dry_run_offline_plans_from_disk_and_stores_nothing(self, tmp_path: Path) -> None:
        self.seeded(tmp_path, ["2024-12"])
        code, text = run(FakeArchive([]), tmp_path, "--offline", "--dry-run")
        assert code == 0
        assert "listed 1, would store 1" in text
        assert check_stored(tmp_path, SYMBOL, INTERVAL).entries == {}

    def test_only_this_series_month_zips_are_taken_from_disk(self, tmp_path: Path) -> None:
        directory = zips_dir(tmp_path)
        directory.mkdir(parents=True)
        for name in (
            "BTCUSDT-1d-2024-12.zip",
            "BTCUSDT-1d-2024-13.zip",
            "BTCUSDT-1d-2024-1.zip",
            "ETHUSDT-1d-2024-11.zip",
            "BTCUSDT-1d-2024-10.zip.CHECKSUM",
            ".BTCUSDT-1d-2024-09.zip.tmp",
            "notes.txt",
        ):
            (directory / name).write_bytes(b"x")
        assert dl.months_on_disk(tmp_path, SYMBOL, INTERVAL) == ("2024-12",)

    def test_no_directory_means_no_months(self, tmp_path: Path) -> None:
        assert dl.months_on_disk(tmp_path, SYMBOL, INTERVAL) == ()


class TestTheSummaryCountsWhatWasSetAside:
    def test_registered_and_quarantined_rows_are_counted_and_the_registry_names_the_zip(
        self, tmp_path: Path
    ) -> None:
        archive = FakeArchive(["2024-12"], texts={"2024-12": irregular_text("2024-12")})
        code, text = run(archive, tmp_path)
        assert code == 0
        assert "registered 1, quarantined 1, fetched 1, reused 0" in text
        lines = [
            json.loads(x)
            for x in (tmp_path / SYMBOL / INTERVAL / REGISTRY_NAME)
            .read_text(encoding="utf-8")
            .splitlines()
        ]
        assert [(x["kind"], x["shape"], x["line"]) for x in lines] == [
            ("registered", "short_bar", 2),
            ("quarantined", "off_grid", 3),
        ]
        assert {x["source_url"] for x in lines} == {
            dl.month_url(SYMBOL, INTERVAL, "2024-12", suffix="zip")
        }
        assert HistoricalStore(tmp_path).verify(SYMBOL, INTERVAL) == ()

    def test_fetched_and_reused_months_are_counted_apart(self, tmp_path: Path) -> None:
        run(FakeArchive(["2024-11"]), tmp_path, through="2024-11")
        for name in ("MANIFEST.jsonl", "BTCUSDT-1d-2024-11.csv"):
            (tmp_path / SYMBOL / INTERVAL / name).unlink()
        code, text = run(FakeArchive(["2024-11", "2024-12"]), tmp_path)
        assert code == 0
        assert "stored 2" in text
        assert "fetched 1, reused 1" in text

    def test_a_rerun_after_everything_is_stored_counts_nothing_fetched(
        self, tmp_path: Path
    ) -> None:
        run(FakeArchive(["2024-12"]), tmp_path)
        _, text = run(FakeArchive(["2024-12"]), tmp_path)
        assert (
            "stored 0, skipped 1, failed 0, registered 0, quarantined 0, fetched 0, reused 0"
            in text
        )
