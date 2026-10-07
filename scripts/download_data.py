#!/usr/bin/env python
"""Download Binance's public monthly kline archive into the historical store.

Usage:
    python scripts/download_data.py --through 2026-09 \
        --symbols BTCUSDT ETHUSDT --intervals 1m 5m 1h 4h 1d

**IT STORES MONTHLY ARCHIVE FILES ONLY**, from each series' first month through
``--through``. The files come from ``data.binance.vision``, which is public and needs no
key, and there is no Testnet path and no REST path here. ``trading_bot.data.historical``
decides what is acceptable: this script lists, fetches and hands each zip to
``ingest_zip``, which verifies the zip against its ``.CHECKSUM`` before parsing a byte.

**EVERY ZIP IS KEPT, AND INGEST ALWAYS READS IT FROM DISK** (owner's ruling R-O). A zip is
written to ``<data-dir>/_zips/<SYMBOL>/<interval>/`` with its ``.CHECKSUM`` file once it has
been verified against that checksum, and it is read back from there to be ingested, so a
change to the importer's rules costs no second download. A zip already on disk whose bytes
equal its ``.CHECKSUM`` is not fetched again; one that does not is fetched and replaced;
one that fails verification is never written. ``_zips`` is not a series directory, so the
store's checks do not see it, and ``data/*`` is ignored by git.

**IDEMPOTENT.** A month whose manifest line and file verify is skipped without a request,
so a re-run after an interruption fetches only what is missing, and a stored file that no
longer matches its manifest is stored again from its kept zip. **A FAILURE IS REPORTED,
NEVER HIDDEN OR FILLED**: a checksum mismatch, an archive that fails validation, a month the
archive does not list and a transport failure each name the month, the rest of the series
continues, and the exit status is non-zero if any month failed. A failed month's zip stays
on disk for diagnosis if it passed its checksum. Gaps are not this script's concern;
``HistoricalStore.coverage`` reports them.

**``--offline`` MAKES A REQUEST IMPOSSIBLE.** The months are those whose zips are on disk,
the fetcher is replaced by one that refuses, and a month whose zip or ``.CHECKSUM`` is
missing or does not match fails instead of being fetched.

**THE NETWORK IS INJECTED.** Every request goes through a ``Fetcher``, ``url -> bytes``,
and the only fetcher that opens a socket is ``fetch_url``, which refuses a URL outside the
two hosts this script talks to and caps a response's size.
"""

from __future__ import annotations

import argparse
import hashlib
import os
import re
import sys
import time
import urllib.error
import urllib.request
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Final, Protocol, TextIO

from trading_bot.data.historical import (
    INTERVAL_MS,
    HistoricalDataError,
    check_stored,
    ingest_zip,
    parse_checksum,
    series_dir,
    verify_zip,
)

Fetcher = Callable[[str], bytes]

LISTING_BASE: Final = "https://s3-ap-northeast-1.amazonaws.com/data.binance.vision"
DATA_BASE: Final = "https://data.binance.vision"
# The listing is asked as ``<LISTING_BASE>?delimiter=...`` and a file as ``<DATA_BASE>/...``.
# Each prefix ends at the character that closes the host, so a lookalike host fails.
_ALLOWED_PREFIXES: Final = (LISTING_BASE + "?", DATA_BASE + "/")
DEFAULT_DATA_DIR: Final = "data/historical"
ZIP_DIR_NAME: Final = "_zips"
DEFAULT_SYMBOLS: Final = ("BTCUSDT", "ETHUSDT")
DEFAULT_INTERVALS: Final = ("1m", "5m", "1h", "4h", "1d")

_MAX_DOWNLOAD_BYTES: Final = 300_000_000
_TIMEOUT_S: Final = 60.0
_KEY: Final = re.compile(r"<Key>([^<]+)</Key>")
_NEXT_MARKER: Final = re.compile(r"<NextMarker>([^<]+)</NextMarker>")
_TRUNCATED: Final = re.compile(r"<IsTruncated>true</IsTruncated>")
_MONTH_ARG: Final = re.compile(r"\d{4}-(0[1-9]|1[0-2])")


class DownloadError(Exception):
    """A request failed. ``retryable`` is true for a transport fault or a server error."""

    def __init__(self, message: str, *, retryable: bool) -> None:
        super().__init__(message)
        self.retryable = retryable


class _Response(Protocol):
    def read(self, size: int = ..., /) -> bytes: ...

    def __enter__(self) -> _Response: ...

    def __exit__(self, *exc: object) -> object: ...


Opener = Callable[[urllib.request.Request, float], _Response]


def _urlopen(request: urllib.request.Request, timeout: float) -> _Response:
    response: _Response = urllib.request.urlopen(request, timeout=timeout)
    return response


def fetch_url(url: str, *, opener: Opener = _urlopen) -> bytes:
    """GET ``url`` and return its body. Only this script's two hosts are allowed."""
    if not url.startswith(_ALLOWED_PREFIXES):
        raise DownloadError(f"refusing a URL outside the archive's hosts: {url}", retryable=False)
    request = urllib.request.Request(url, headers={"User-Agent": "trading-bot-historical/1"})
    try:
        with opener(request, _TIMEOUT_S) as response:
            body = response.read(_MAX_DOWNLOAD_BYTES + 1)
    except urllib.error.HTTPError as exc:
        raise DownloadError(f"{url}: HTTP {exc.code}", retryable=exc.code >= 500) from exc
    except (urllib.error.URLError, TimeoutError, ConnectionError) as exc:
        raise DownloadError(f"{url}: {exc}", retryable=True) from exc
    if len(body) > _MAX_DOWNLOAD_BYTES:
        raise DownloadError(f"{url}: more than {_MAX_DOWNLOAD_BYTES} bytes", retryable=False)
    return body


def with_retries(
    fetcher: Fetcher, *, attempts: int = 3, sleep: Callable[[float], None] = time.sleep
) -> Fetcher:
    """Retry a fetcher on a retryable ``DownloadError``, waiting 1 s, 2 s, ... between tries."""

    def fetch(url: str) -> bytes:
        for attempt in range(1, attempts + 1):
            try:
                return fetcher(url)
            except DownloadError as exc:
                if not exc.retryable or attempt == attempts:
                    raise
                sleep(float(attempt))
        raise AssertionError("unreachable: attempts must be at least 1")

    return fetch


def month_url(symbol: str, interval: str, month: str, *, suffix: str) -> str:
    """The archive URL of one month's zip (``suffix`` ``zip``) or checksum (``CHECKSUM``)."""
    name = f"{symbol}-{interval}-{month}.zip"
    return f"{DATA_BASE}/data/spot/monthly/klines/{symbol}/{interval}/{name}" + (
        "" if suffix == "zip" else f".{suffix}"
    )


def list_months(fetcher: Fetcher, symbol: str, interval: str) -> tuple[str, ...]:
    """Every month the archive holds a zip for, oldest first, following the listing's pages."""
    prefix = f"data/spot/monthly/klines/{symbol}/{interval}/"
    wanted = re.compile(
        re.escape(prefix) + re.escape(f"{symbol}-{interval}-") + r"(\d{4}-\d{2})\.zip"
    )
    months: set[str] = set()
    marker = ""
    while True:
        url = f"{LISTING_BASE}?delimiter=/&prefix={prefix}" + (
            f"&marker={marker}" if marker else ""
        )
        page = fetcher(url).decode("utf-8")
        keys = _KEY.findall(page)
        for key in keys:
            found = wanted.fullmatch(key)
            if found is not None:
                months.add(found.group(1))
        if _TRUNCATED.search(page) is None:
            return tuple(sorted(months))
        following = _NEXT_MARKER.search(page)
        marker = following.group(1) if following is not None else (keys[-1] if keys else "")
        if not marker:
            raise DownloadError(
                f"a truncated listing of {prefix} names no next page", retryable=False
            )


def zip_file(root: Path, symbol: str, interval: str, month: str) -> Path:
    """Where a month's zip is kept: ``<root>/_zips/<SYMBOL>/<interval>/<name>.zip``."""
    series_dir(root, symbol, interval)
    return root / ZIP_DIR_NAME / symbol / interval / f"{symbol}-{interval}-{month}.zip"


def write_atomic(path: Path, data: bytes) -> None:
    """Write ``data`` to ``path`` through a temporary file and a rename, so a kill leaves
    either the old file or the new one and never half of it."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    try:
        with temporary.open("wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def months_on_disk(root: Path, symbol: str, interval: str) -> tuple[str, ...]:
    """The months whose zips are kept on disk for a series, oldest first."""
    series_dir(root, symbol, interval)
    directory = root / ZIP_DIR_NAME / symbol / interval
    if not directory.is_dir():
        return ()
    wanted = re.compile(re.escape(f"{symbol}-{interval}-") + r"(\d{4}-(?:0[1-9]|1[0-2]))\.zip")
    found = (wanted.fullmatch(path.name) for path in directory.glob("*.zip"))
    return tuple(sorted(match.group(1) for match in found if match is not None))


def _refuse_request(url: str) -> bytes:
    raise DownloadError(f"no request is allowed with --offline: {url}", retryable=False)


@dataclass
class SeriesResult:
    symbol: str
    interval: str
    listed: int = 0
    downloaded: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    failed: dict[str, str] = field(default_factory=dict)
    fetched: list[str] = field(default_factory=list)
    reused: list[str] = field(default_factory=list)
    registered: int = 0
    quarantined: int = 0
    note: str = ""

    @property
    def ok(self) -> bool:
        return not self.failed and not self.note


def obtain(
    fetcher: Fetcher, root: Path, symbol: str, interval: str, month: str, *, offline: bool = False
) -> tuple[bytes, str, bool]:
    """The month's zip bytes read from disk, its digest, and whether the zip was fetched.

    The digest is the on-disk ``.CHECKSUM``'s, or is fetched when there is none. A zip on
    disk that hashes to it is used as it is. Otherwise the zip is fetched, verified against
    the digest BEFORE anything is written, then written (and its checksum file after it, so
    a kill between the two leaves a zip the next run can still use), and read back. With
    ``offline`` a missing or mismatching file is an error and ``fetcher`` is never called.
    """
    name = f"{symbol}-{interval}-{month}.zip"
    path = zip_file(root, symbol, interval, month)
    sum_path = path.with_name(name + ".CHECKSUM")
    sum_text: str | None = None
    if sum_path.is_file():
        digest = parse_checksum(sum_path.read_text(encoding="utf-8"), name)
    else:
        sum_url = month_url(symbol, interval, month, suffix="CHECKSUM")
        sum_text = fetcher(sum_url).decode("utf-8")
        digest = parse_checksum(sum_text, name)
    if path.is_file() and hashlib.sha256(path.read_bytes()).hexdigest() == digest:
        if sum_text is not None:
            write_atomic(sum_path, sum_text.encode("utf-8"))
        return path.read_bytes(), digest, False
    if offline:
        raise DownloadError(
            f"{path} is missing or does not match its CHECKSUM, and --offline fetches nothing",
            retryable=False,
        )
    verify_zip(data := fetcher(month_url(symbol, interval, month, suffix="zip")), digest)
    write_atomic(path, data)
    if sum_text is not None:
        write_atomic(sum_path, sum_text.encode("utf-8"))
    return path.read_bytes(), digest, True


def download_series(
    fetcher: Fetcher,
    root: Path,
    symbol: str,
    interval: str,
    through: str,
    *,
    dry_run: bool = False,
    offline: bool = False,
    out: TextIO = sys.stdout,
) -> SeriesResult:
    """Store every listed month up to ``through`` that is not already stored and verified.

    With ``offline`` the months are those whose zips are on disk and ``fetcher`` is never
    called.
    """
    series_dir(root, symbol, interval)
    result = SeriesResult(symbol, interval)
    try:
        everything = (
            months_on_disk(root, symbol, interval)
            if offline
            else list_months(fetcher, symbol, interval)
        )
    except DownloadError as exc:
        result.note = f"listing failed: {exc}"
        return result
    listed = [month for month in everything if month <= through]
    result.listed = len(listed)
    if not listed:
        result.note = (
            f"no zip of {symbol} {interval} through {through} is on disk"
            if offline
            else f"the archive lists no month of {symbol} {interval} through {through}"
        )
        return result
    stored = check_stored(root, symbol, interval).entries
    for month in listed:
        if month in stored:
            result.skipped.append(month)
            continue
        if dry_run:
            result.downloaded.append(month)
            continue
        try:
            data, digest, fetched = obtain(fetcher, root, symbol, interval, month, offline=offline)
            ingested = ingest_zip(
                data,
                expected_sha256=digest,
                root=root,
                symbol=symbol,
                interval=interval,
                month=month,
                source_url=month_url(symbol, interval, month, suffix="zip"),
            )
        except (DownloadError, HistoricalDataError, UnicodeDecodeError, OSError) as exc:
            result.failed[month] = f"{type(exc).__name__}: {exc}"
            print(f"FAILED {symbol} {interval} {month}: {result.failed[month]}", file=out)
            continue
        result.downloaded.append(month)
        (result.fetched if fetched else result.reused).append(month)
        result.registered += len(ingested.registered)
        result.quarantined += len(ingested.quarantined)
        print(f"stored {symbol} {interval} {month}", file=out)
    return result


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0] if __doc__ else None)
    parser.add_argument("--through", required=True, help="last month to store, YYYY-MM")
    parser.add_argument("--symbols", nargs="+", default=list(DEFAULT_SYMBOLS))
    parser.add_argument("--intervals", nargs="+", default=list(DEFAULT_INTERVALS))
    parser.add_argument("--data-dir", default=DEFAULT_DATA_DIR, help="backtesting.data_dir")
    parser.add_argument("--dry-run", action="store_true", help="list and plan; fetch no zip")
    parser.add_argument(
        "--offline",
        action="store_true",
        help="plan from the zips on disk and make no request at all",
    )
    return parser


def run(
    argv: Sequence[str],
    *,
    fetcher: Fetcher | None = None,
    out: TextIO = sys.stdout,
) -> int:
    """Download what the arguments name. 0 if every month is stored, 1 if any failed, 2 if refused."""
    args = _parser().parse_args(argv)
    if _MONTH_ARG.fullmatch(args.through) is None:
        print(f"refused: --through must be YYYY-MM, not {args.through!r}", file=out)
        return 2
    unknown = [interval for interval in args.intervals if interval not in INTERVAL_MS]
    if unknown:
        print(f"refused: not stored intervals: {unknown}; stored: {sorted(INTERVAL_MS)}", file=out)
        return 2
    root = Path(args.data_dir)
    try:
        for symbol in args.symbols:
            for interval in args.intervals:
                series_dir(root, symbol, interval)
    except HistoricalDataError as exc:
        print(f"refused: {exc}", file=out)
        return 2
    if args.offline:
        fetch: Fetcher = _refuse_request
    else:
        fetch = fetcher if fetcher is not None else with_retries(fetch_url)
    results: list[SeriesResult] = []
    for symbol in args.symbols:
        for interval in args.intervals:
            results.append(
                download_series(
                    fetch,
                    root,
                    symbol,
                    interval,
                    args.through,
                    dry_run=args.dry_run,
                    offline=args.offline,
                    out=out,
                )
            )
    verb = "would store" if args.dry_run else "stored"
    for result in results:
        print(
            f"{result.symbol} {result.interval}: listed {result.listed}, {verb} "
            f"{len(result.downloaded)}, skipped {len(result.skipped)}, failed {len(result.failed)}"
            f", registered {result.registered}, quarantined {result.quarantined}"
            f", fetched {len(result.fetched)}, reused {len(result.reused)}"
            + (f", {result.note}" if result.note else ""),
            file=out,
        )
    return 0 if all(result.ok for result in results) else 1


def main() -> None:
    sys.exit(run(sys.argv[1:]))


if __name__ == "__main__":
    main()
