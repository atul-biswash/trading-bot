"""Historical kline storage: ingest the venue's bulk archive, verify it, find its gaps.

This module never touches the network. It turns the bytes of one monthly archive
file from ``data.binance.vision`` into a verified CSV under ``backtesting.data_dir``
and a manifest line, and it checks what is already stored. ``scripts/download_data.py``
fetches; this module decides what is acceptable. Its read side, ``HistoricalStore``,
serves stored bars to the backtester and is also network-free.

**Serving a bar and verifying its file are one act.** ``HistoricalStore.candles`` hashes
each month file as it reads it and raises ``StoredFileError`` on a mismatch with the
manifest, so a corrupt or edited file is never served quietly. A month absent from the
manifest yields no bars: that is a gap, and ``coverage`` reports it. Nothing here
fabricates a bar to hide one.

**Money stays a string here.** A price or volume is kept exactly as the venue wrote
it, ``"96407.99000000"`` with its trailing zeros, and is validated by shape rather than
parsed. Nothing in this module uses ``float``. The single ``Decimal`` to ``float``
boundary stays in ``BufferedMarketDataProvider.get_dataframe``.

**The archive changed its time unit, and a wrong reading is silent.** Files through
2024-12 carry millisecond timestamps (13 digits); files from 2025-01 carry microsecond
timestamps (16 digits); MEASURED at P100 (``M5m-030``). A microsecond value read as
milliseconds is a date in the year 56,000, and the reverse is a date in 1970, and in
neither case does anything raise by itself. So the unit is decided per row from the
digit count, any other count is an error, and a microsecond ``open_time`` must be a
multiple of 1000. The stored file is milliseconds throughout.

**A bar's close time is checked, not trusted.** ``close_time_ms`` is the archive's
close time floored to milliseconds, and it must equal ``open_time_ms + interval_ms - 1``
for both units. A file whose close times disagree with its interval is not the file it
claims to be.

**A gap is reported and never filled.** The venue stores an empty minute as a bar with
zero volume and zero trades (``M5m-031``), so a break in the grid means the archive has
no bar there, which is a fact to report and not a quiet market to interpolate.
"""

from __future__ import annotations

import hashlib
import io
import json
import os
import re
import zipfile
from array import array
from collections.abc import Iterator, Sequence
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from itertools import pairwise
from pathlib import Path
from typing import Final

from trading_bot.core.models import Candle

__all__ = [
    "INTERVAL_MS",
    "ArchiveFormatError",
    "ChecksumMismatchError",
    "Coverage",
    "Gap",
    "HistoricalDataError",
    "HistoricalStore",
    "ManifestEntry",
    "ManifestError",
    "Problem",
    "Row",
    "StoredFileError",
    "StoredReport",
    "check_stored",
    "find_gaps",
    "grid_size",
    "ingest_zip",
    "month_bounds_ms",
    "month_file",
    "normalise_archive",
    "parse_checksum",
    "series_dir",
    "verify_zip",
    "write_month",
]

INTERVAL_MS: Final[dict[str, int]] = {
    "1m": 60_000,
    "5m": 300_000,
    "1h": 3_600_000,
    "4h": 14_400_000,
    "1d": 86_400_000,
}

HEADER: Final = "open_time_ms,open,high,low,close,volume,close_time_ms"
MANIFEST_NAME: Final = "MANIFEST.jsonl"

_ARCHIVE_FIELDS: Final = 12
_MS_DIGITS: Final = 13
_US_DIGITS: Final = 16
_MAX_MEMBER_BYTES: Final = 200_000_000
_EPOCH: Final = datetime(1970, 1, 1, tzinfo=timezone.utc)
_ONE_MS: Final = timedelta(milliseconds=1)
_SYMBOL = re.compile(r"[A-Z0-9]{5,20}")
_MONTH = re.compile(r"(\d{4})-(0[1-9]|1[0-2])")
_SHA256 = re.compile(r"[0-9a-f]{64}")
_NUMBER = re.compile(r"\d+(\.\d+)?")
_DIGITS = re.compile(r"\d+")


class HistoricalDataError(Exception):
    """Base of every refusal in this module."""


class ChecksumMismatchError(HistoricalDataError):
    """The archive's bytes do not hash to the checksum the venue published."""


class ArchiveFormatError(HistoricalDataError):
    """A row, a name or a shape that is not what the archive is documented to hold."""


class StoredFileError(HistoricalDataError):
    """A stored file or manifest that no longer is what the manifest says it is."""


class ManifestError(HistoricalDataError):
    """A manifest that cannot be read or extended without losing something."""


@dataclass(frozen=True)
class Row:
    """One stored bar: milliseconds for times, the venue's own strings for money."""

    open_time_ms: int
    open: str
    high: str
    low: str
    close: str
    volume: str
    close_time_ms: int


@dataclass(frozen=True)
class Gap:
    """A run of missing bars on the grid: ``start_ms`` inclusive, ``end_ms`` exclusive."""

    start_ms: int
    end_ms: int
    missing: int


@dataclass(frozen=True)
class ManifestEntry:
    """What was stored for one month, and the source it came from."""

    symbol: str
    interval: str
    month: str
    file: str
    source_url: str
    zip_sha256: str
    rows: int
    first_open_time_ms: int
    last_open_time_ms: int
    csv_sha256: str


@dataclass(frozen=True)
class Problem:
    """One thing wrong with what is stored, tied to a month where it has one."""

    kind: str
    month: str | None
    detail: str


@dataclass(frozen=True)
class StoredReport:
    """The months that verify clean, and every problem found."""

    entries: dict[str, ManifestEntry]
    problems: tuple[Problem, ...]


def _require_symbol(symbol: str) -> None:
    if _SYMBOL.fullmatch(symbol) is None:
        raise ArchiveFormatError(f"not a symbol: {symbol!r}")


def _require_interval(interval: str) -> int:
    if interval not in INTERVAL_MS:
        raise ArchiveFormatError(f"not a stored interval: {interval!r}")
    return INTERVAL_MS[interval]


def _require_month(month: str) -> tuple[int, int]:
    found = _MONTH.fullmatch(month)
    if found is None:
        raise ArchiveFormatError(f"not a month, YYYY-MM: {month!r}")
    return int(found.group(1)), int(found.group(2))


def _to_ms(moment: datetime) -> int:
    return (moment - _EPOCH) // _ONE_MS


def month_bounds_ms(month: str) -> tuple[int, int]:
    """The month's first millisecond (inclusive) and the next month's first (exclusive)."""
    year, number = _require_month(month)
    start = datetime(year, number, 1, tzinfo=timezone.utc)
    following = datetime(year + (number == 12), number % 12 + 1, 1, tzinfo=timezone.utc)
    return _to_ms(start), _to_ms(following)


def series_dir(root: Path, symbol: str, interval: str) -> Path:
    """``<root>/<SYMBOL>/<interval>``, built only from validated parts."""
    _require_symbol(symbol)
    _require_interval(interval)
    return root / symbol / interval


def month_file(root: Path, symbol: str, interval: str, month: str) -> Path:
    """The CSV that holds one month of one series."""
    _require_month(month)
    return series_dir(root, symbol, interval) / f"{symbol}-{interval}-{month}.csv"


def parse_checksum(text: str, file_name: str) -> str:
    """The SHA-256 a ``.CHECKSUM`` file states for ``file_name``.

    The venue writes ``<64 hex>  <name>``. A different name, or a digest that is not 64
    lower-case hex digits, is refused: a checksum for another file proves nothing.
    """
    parts = text.split()
    if len(parts) != 2:
        raise ArchiveFormatError(f"a checksum file holds a digest and a name: {text!r}")
    digest, name = parts
    if _SHA256.fullmatch(digest) is None:
        raise ArchiveFormatError(f"not a SHA-256 digest: {digest!r}")
    if name != file_name:
        raise ArchiveFormatError(f"checksum is for {name!r}, not {file_name!r}")
    return digest


def verify_zip(data: bytes, expected_sha256: str) -> None:
    """Raise unless ``data`` hashes to ``expected_sha256``. Called before anything is parsed."""
    actual = hashlib.sha256(data).hexdigest()
    if actual != expected_sha256:
        raise ChecksumMismatchError(
            f"archive hashes to {actual}, the venue published {expected_sha256}"
        )


def _unit_divisor(raw: str, field: str) -> int:
    if _DIGITS.fullmatch(raw) is None:
        raise ArchiveFormatError(f"{field} is not an integer: {raw!r}")
    if len(raw) == _MS_DIGITS:
        return 1
    if len(raw) == _US_DIGITS:
        return 1000
    raise ArchiveFormatError(f"{field} has {len(raw)} digits, neither 13 (ms) nor 16 (us): {raw!r}")


def _open_time_ms(raw: str) -> int:
    divisor = _unit_divisor(raw, "open_time")
    value = int(raw)
    if value % divisor:
        raise ArchiveFormatError(f"open_time is not a whole millisecond: {raw!r}")
    return value // divisor


def _close_time_ms(raw: str) -> int:
    return int(raw) // _unit_divisor(raw, "close_time")


def _money(raw: str, field: str) -> str:
    if _NUMBER.fullmatch(raw) is None:
        raise ArchiveFormatError(f"{field} is not a plain non-negative number: {raw!r}")
    return raw


def _normalise_row(fields: Sequence[str], interval_ms: int) -> Row:
    if len(fields) != _ARCHIVE_FIELDS:
        raise ArchiveFormatError(f"a row has {len(fields)} fields, not {_ARCHIVE_FIELDS}")
    if len(fields[0]) != len(fields[6]):
        raise ArchiveFormatError("open_time and close_time are in different units")
    open_ms = _open_time_ms(fields[0])
    close_ms = _close_time_ms(fields[6])
    if close_ms != open_ms + interval_ms - 1:
        raise ArchiveFormatError(
            f"close_time {close_ms} is not open_time {open_ms} + {interval_ms} - 1"
        )
    return Row(
        open_time_ms=open_ms,
        open=_money(fields[1], "open"),
        high=_money(fields[2], "high"),
        low=_money(fields[3], "low"),
        close=_money(fields[4], "close"),
        volume=_money(fields[5], "volume"),
        close_time_ms=close_ms,
    )


def normalise_archive(csv_text: str, *, interval: str, month: str) -> tuple[Row, ...]:
    """Parse one monthly archive CSV into rows, refusing anything the archive does not hold.

    No header is expected (the archive has none), every row has exactly twelve fields,
    ``open_time`` strictly increases, and every bar opens inside ``month``.
    """
    interval_ms = _require_interval(interval)
    start_ms, end_ms = month_bounds_ms(month)
    rows: list[Row] = []
    for number, line in enumerate(csv_text.splitlines(), start=1):
        try:
            row = _normalise_row(line.split(","), interval_ms)
        except ArchiveFormatError as exc:
            raise ArchiveFormatError(f"line {number}: {exc}") from exc
        if not start_ms <= row.open_time_ms < end_ms:
            raise ArchiveFormatError(
                f"line {number}: open_time {row.open_time_ms} is outside {month}"
            )
        if rows and row.open_time_ms <= rows[-1].open_time_ms:
            raise ArchiveFormatError(f"line {number}: open_time does not increase")
        rows.append(row)
    if not rows:
        raise ArchiveFormatError("the archive holds no rows")
    return tuple(rows)


def grid_size(start_ms: int, end_ms: int, interval_ms: int) -> int:
    """The number of bars on the grid from ``start_ms`` (inclusive) to ``end_ms`` (exclusive)."""
    span = end_ms - start_ms
    if span < 0 or span % interval_ms:
        raise ValueError(f"{start_ms}..{end_ms} is not a whole number of {interval_ms} ms bars")
    return span // interval_ms


def find_gaps(
    open_times_ms: Sequence[int],
    interval_ms: int,
    *,
    start_ms: int | None = None,
    end_ms: int | None = None,
) -> tuple[Gap, ...]:
    """Every run of missing bars, from the differences between consecutive open times.

    With ``start_ms`` and ``end_ms`` the expected grid is that range and a run missing
    at either edge is a gap too, so ``len(open_times_ms) + sum(gap.missing)`` equals
    :func:`grid_size`. A series that does not increase, or whose spacing is not a whole
    number of intervals, or that lies outside the range, raises ``ValueError``: it has
    no gaps to report because it is not on the grid at all.
    """
    gaps: list[Gap] = []
    if not open_times_ms:
        if start_ms is not None and end_ms is not None:
            missing = grid_size(start_ms, end_ms, interval_ms)
            if missing:
                gaps.append(Gap(start_ms, end_ms, missing))
        return tuple(gaps)
    if start_ms is not None:
        lead = open_times_ms[0] - start_ms
        if lead < 0:
            raise ValueError(
                f"a bar at {open_times_ms[0]} lies before the range starts at {start_ms}"
            )
        if lead % interval_ms:
            raise ValueError(f"{start_ms} to {open_times_ms[0]} is not a whole number of bars")
        if lead:
            gaps.append(Gap(start_ms, open_times_ms[0], lead // interval_ms))
    for before, after in pairwise(open_times_ms):
        spacing = after - before
        if spacing <= 0:
            raise ValueError(f"open times do not increase: {before} then {after}")
        if spacing % interval_ms:
            raise ValueError(f"{before} to {after} is not a whole number of {interval_ms} ms bars")
        if spacing > interval_ms:
            gaps.append(Gap(before + interval_ms, after, spacing // interval_ms - 1))
    if end_ms is not None:
        last_end = open_times_ms[-1] + interval_ms
        tail = end_ms - last_end
        if tail < 0:
            raise ValueError(
                f"a bar at {open_times_ms[-1]} lies beyond the range that ends at {end_ms}"
            )
        if tail % interval_ms:
            raise ValueError(f"{last_end} to {end_ms} is not a whole number of bars")
        if tail:
            gaps.append(Gap(last_end, end_ms, tail // interval_ms))
    return tuple(gaps)


def _render_csv(rows: Sequence[Row]) -> bytes:
    lines = [HEADER]
    lines.extend(
        f"{r.open_time_ms},{r.open},{r.high},{r.low},{r.close},{r.volume},{r.close_time_ms}"
        for r in rows
    )
    return ("\n".join(lines) + "\n").encode("ascii")


def _atomic_write(path: Path, data: bytes) -> None:
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


def _entry_line(entry: ManifestEntry) -> str:
    return json.dumps(asdict(entry), sort_keys=True, separators=(",", ":"))


_ENTRY_TYPES: Final = {
    "symbol": str,
    "interval": str,
    "month": str,
    "file": str,
    "source_url": str,
    "zip_sha256": str,
    "rows": int,
    "first_open_time_ms": int,
    "last_open_time_ms": int,
    "csv_sha256": str,
}


def _entry_from(raw: object) -> ManifestEntry:
    """Build an entry from a decoded manifest line, or raise ``ValueError``.

    A manifest is a file a person can edit, and ``file`` is joined to the data root, so
    the entry must name exactly the path its own symbol, interval and month imply.
    """
    if not isinstance(raw, dict) or set(raw) != set(_ENTRY_TYPES):
        raise ValueError("a manifest line is an object with exactly the entry's fields")
    for key, kind in _ENTRY_TYPES.items():
        value = raw[key]
        if type(value) is not kind:
            raise ValueError(f"{key} is not a {kind.__name__}: {value!r}")
    entry = ManifestEntry(**raw)
    try:
        canonical = month_file(Path(), entry.symbol, entry.interval, entry.month).as_posix()
    except ArchiveFormatError as exc:
        raise ValueError(str(exc)) from exc
    if entry.file != canonical:
        raise ValueError(f"file {entry.file!r} is not {canonical!r}")
    return entry


def _read_manifest(path: Path) -> tuple[dict[str, ManifestEntry], list[Problem]]:
    entries: dict[str, ManifestEntry] = {}
    problems: list[Problem] = []
    if not path.exists():
        return entries, problems
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        try:
            entry = _entry_from(json.loads(line))
        except ValueError as exc:
            problems.append(Problem("bad_manifest_line", None, f"line {number}: {exc}"))
            continue
        if entry.month in entries:
            problems.append(Problem("duplicate_month", entry.month, f"line {number}"))
        entries[entry.month] = entry
    return entries, problems


def _record(path: Path, entry: ManifestEntry) -> None:
    entries, problems = _read_manifest(path)
    if problems:
        raise ManifestError(
            f"{path} has {len(problems)} unreadable or repeated lines; not extended"
        )
    entries[entry.month] = entry
    text = "".join(_entry_line(entries[month]) + "\n" for month in sorted(entries))
    _atomic_write(path, text.encode("utf-8"))


def write_month(
    root: Path,
    symbol: str,
    interval: str,
    month: str,
    rows: Sequence[Row],
    *,
    source_url: str,
    zip_sha256: str,
) -> ManifestEntry:
    """Store one month: temp file, atomic rename, then the manifest line.

    The manifest is rewritten whole and atomically, so a power cut leaves either the
    old manifest or the new one and never a torn line. A month whose CSV was renamed
    and whose manifest line was not yet written is simply not listed, and the next run
    stores it again with the same bytes.
    """
    if not rows:
        raise ArchiveFormatError("nothing to store")
    path = month_file(root, symbol, interval, month)
    data = _render_csv(rows)
    _atomic_write(path, data)
    entry = ManifestEntry(
        symbol=symbol,
        interval=interval,
        month=month,
        file=path.relative_to(root).as_posix(),
        source_url=source_url,
        zip_sha256=zip_sha256,
        rows=len(rows),
        first_open_time_ms=rows[0].open_time_ms,
        last_open_time_ms=rows[-1].open_time_ms,
        csv_sha256=hashlib.sha256(data).hexdigest(),
    )
    _record(series_dir(root, symbol, interval) / MANIFEST_NAME, entry)
    return entry


def ingest_zip(
    data: bytes,
    *,
    expected_sha256: str,
    root: Path,
    symbol: str,
    interval: str,
    month: str,
    source_url: str,
) -> ManifestEntry:
    """Verify, unzip, normalise and store one monthly archive file.

    The checksum is verified first, so a corrupt download is rejected before a byte of
    it is parsed and nothing is stored. The zip must hold exactly the one member the
    name implies, and that member's size is capped, because a decompression bomb is the
    cheapest way a download can hurt this machine.
    """
    verify_zip(data, expected_sha256)
    member = f"{symbol}-{interval}-{month}.csv"
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            names = archive.namelist()
            if names != [member]:
                raise ArchiveFormatError(f"expected the one member {member!r}, found {names}")
            with archive.open(member) as handle:
                payload = handle.read(_MAX_MEMBER_BYTES + 1)
        text = payload.decode("utf-8")
    except zipfile.BadZipFile as exc:
        raise ArchiveFormatError(f"not a zip file: {exc}") from exc
    except UnicodeDecodeError as exc:
        raise ArchiveFormatError(f"{member} is not UTF-8: {exc}") from exc
    if len(payload) > _MAX_MEMBER_BYTES:
        raise ArchiveFormatError(f"{member} unpacks past {_MAX_MEMBER_BYTES} bytes")
    rows = normalise_archive(text, interval=interval, month=month)
    return write_month(
        root, symbol, interval, month, rows, source_url=source_url, zip_sha256=expected_sha256
    )


def _check_entry(root: Path, entry: ManifestEntry) -> list[Problem]:
    path = root / entry.file
    if not path.is_file():
        return [Problem("missing_file", entry.month, entry.file)]
    data = path.read_bytes()
    if hashlib.sha256(data).hexdigest() != entry.csv_sha256:
        return [Problem("hash_mismatch", entry.month, entry.file)]
    lines = data.decode("ascii").split("\n")
    body = lines[1:-1]
    if lines[0] != HEADER or lines[-1] != "":
        return [Problem("bad_shape", entry.month, entry.file)]
    first = int(body[0].split(",", 1)[0]) if body else -1
    last = int(body[-1].split(",", 1)[0]) if body else -1
    if (len(body), first, last) != (entry.rows, entry.first_open_time_ms, entry.last_open_time_ms):
        return [
            Problem(
                "bounds_mismatch", entry.month, f"{entry.file}: {len(body)} rows, {first}..{last}"
            )
        ]
    return []


def check_stored(root: Path, symbol: str, interval: str) -> StoredReport:
    """Re-verify everything stored for one series against its manifest.

    A month is in ``entries`` only if its file exists, hashes to the manifest's digest
    and agrees with the manifest on rows and first and last open time. A CSV file with
    no manifest line, and every unreadable manifest line, is a problem too.
    """
    directory = series_dir(root, symbol, interval)
    entries, problems = _read_manifest(directory / MANIFEST_NAME)
    verified: dict[str, ManifestEntry] = {}
    for month, entry in entries.items():
        found = _check_entry(root, entry)
        problems.extend(found)
        if not found:
            verified[month] = entry
    if directory.is_dir():
        listed = {Path(entry.file).name for entry in entries.values()}
        for path in sorted(directory.glob("*.csv")):
            if path.name not in listed:
                problems.append(Problem("unlisted_file", None, path.name))
    return StoredReport(verified, tuple(problems))


@dataclass(frozen=True)
class Coverage:
    """What is stored for one series and what is missing from it.

    ``gaps`` are the runs of missing bars between the first stored bar and the last, plus,
    when ``until`` was given, the run missing after the last. With ``until``,
    ``bars + missing == grid_bars`` exactly, the grid being the bars from the first stored
    one up to ``until``. A month that fails verification is not counted in ``bars`` and
    shows up as a gap and in ``problems``.
    """

    symbol: str
    interval: str
    months: tuple[str, ...]
    bars: int
    first_open_time_ms: int | None
    last_open_time_ms: int | None
    gaps: tuple[Gap, ...]
    missing: int
    grid_bars: int | None
    problems: tuple[Problem, ...]


def _aware_ms(moment: datetime, name: str) -> int:
    if moment.tzinfo is None:
        raise ValueError(f"{name} must be timezone-aware, not naive: {moment!r}")
    return _to_ms(moment)


def _utc(value_ms: int) -> datetime:
    return _EPOCH + timedelta(milliseconds=value_ms)


def _candle(symbol: str, interval: str, line: str) -> Candle:
    fields = line.split(",")
    return Candle(
        symbol=symbol,
        timeframe=interval,
        open_time=_utc(int(fields[0])),
        close_time=_utc(int(fields[6])),
        open=Decimal(fields[1]),
        high=Decimal(fields[2]),
        low=Decimal(fields[3]),
        close=Decimal(fields[4]),
        volume=Decimal(fields[5]),
        is_closed=True,
    )


class HistoricalStore:
    """Serve and describe the bars stored under one data directory. It only reads.

    The directory is ``backtesting.data_dir``. Nothing here writes, fetches or fills.
    """

    def __init__(self, root: Path) -> None:
        self._root = root

    @property
    def root(self) -> Path:
        return self._root

    def verify(self, symbol: str, interval: str) -> tuple[Problem, ...]:
        """Every problem with what is stored for one series; empty when it is clean."""
        return check_stored(self._root, symbol, interval).problems

    def candles(
        self, symbol: str, interval: str, start: datetime, end: datetime
    ) -> Iterator[Candle]:
        """Closed candles with ``start <= open_time < end``, streamed month by month.

        ``start`` and ``end`` must be timezone-aware. Arguments are checked now, when this
        is called, and files are read as the iterator is consumed. Each month file is
        hashed as it is read, and a file that is missing or no longer matches the manifest
        raises ``StoredFileError`` when the iterator reaches it, so a corrupt month cannot
        be served. A month absent from the manifest yields nothing; ``coverage`` reports
        it as a gap. Money comes from the stored strings, exactly.
        """
        _require_interval(interval)
        start_ms = _aware_ms(start, "start")
        end_ms = _aware_ms(end, "end")
        entries = self._listed(symbol, interval)
        return self._stream(symbol, interval, entries, start_ms, end_ms)

    def coverage(self, symbol: str, interval: str, *, until: datetime | None = None) -> Coverage:
        """Describe one series: its months, its bars and its gaps, without filling any.

        ``until`` (exclusive, timezone-aware, on the grid and after the last bar) extends
        the expected grid so a missing last month is a gap and ``bars + missing`` equals
        ``grid_bars``. A series with no verified month has no bars and no gaps.
        """
        interval_ms = _require_interval(interval)
        end_ms = None if until is None else _aware_ms(until, "until")
        report = check_stored(self._root, symbol, interval)
        opens = array("q")
        for month in sorted(report.entries):
            data = (self._root / report.entries[month].file).read_bytes().decode("ascii")
            opens.extend(int(line.split(",", 1)[0]) for line in data.split("\n")[1:-1])
        gaps = find_gaps(opens, interval_ms, end_ms=end_ms)
        grid = grid_size(opens[0], end_ms, interval_ms) if opens and end_ms is not None else None
        return Coverage(
            symbol=symbol,
            interval=interval,
            months=tuple(sorted(report.entries)),
            bars=len(opens),
            first_open_time_ms=opens[0] if opens else None,
            last_open_time_ms=opens[-1] if opens else None,
            gaps=gaps,
            missing=sum(gap.missing for gap in gaps),
            grid_bars=grid,
            problems=report.problems,
        )

    def _listed(self, symbol: str, interval: str) -> dict[str, ManifestEntry]:
        entries, problems = _read_manifest(series_dir(self._root, symbol, interval) / MANIFEST_NAME)
        if problems:
            raise StoredFileError(
                f"{symbol} {interval}: the manifest has {len(problems)} bad lines"
            )
        return entries

    def _stream(
        self,
        symbol: str,
        interval: str,
        entries: dict[str, ManifestEntry],
        start_ms: int,
        end_ms: int,
    ) -> Iterator[Candle]:
        for month in sorted(entries):
            first_ms, after_ms = month_bounds_ms(month)
            if after_ms <= start_ms or first_ms >= end_ms:
                continue
            entry = entries[month]
            try:
                data = (self._root / entry.file).read_bytes()
            except OSError as exc:
                raise StoredFileError(f"{entry.file} cannot be read: {exc}") from exc
            if hashlib.sha256(data).hexdigest() != entry.csv_sha256:
                raise StoredFileError(f"{entry.file} no longer matches its manifest hash")
            for line in data.decode("ascii").split("\n")[1:-1]:
                opened = int(line.split(",", 1)[0])
                if opened < start_ms:
                    continue
                if opened >= end_ms:
                    return
                yield _candle(symbol, interval, line)
