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

**Every row is classified, and only a shape nobody has seen refuses a month.**
``close_time_ms`` is the archive's close time floored to milliseconds. A regular bar
opens on the interval grid and closes at ``open_time_ms + interval_ms - 1``, and a row
that does not is put in a class by :func:`classify_times` (owner's rulings R-L and R-M,
after the P102 census of all 1,100 months). A row that opens on the grid and closes
after its open is **stored verbatim** whatever its close time is, and a close that
differs from the regular one is registered with its shape: ``short_bar`` (the bar
closed early), ``one_ms_late`` or ``whole_second``. A row that opens off the grid, or
closes at or before its own open, is **quarantined**: not stored, and its raw line,
shape and source are recorded in the series' registry, ``IRREGULAR.jsonl``, beside the
registered rows' (owner's ruling R-L). No stored value is altered. The bars a
quarantined row leaves missing are reported by ``HistoricalStore.coverage`` as gaps of
kind ``quarantined``, and the archive's own omissions as ``omitted`` (ruling R-N); neither
is ever filled. A month is refused only for what no class
covers: a close past the bar's end, a price that is not positive or does not enclose
the bar's open and close, an open time that does not increase or lies outside the month,
a unit or field-count fault, a bad checksum.

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
from bisect import bisect_left
from collections.abc import Iterable, Iterator, Sequence
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from enum import Enum
from itertools import pairwise
from pathlib import Path
from typing import Final

from trading_bot.core.models import Candle

__all__ = [
    "INTERVAL_MS",
    "QUARANTINED_SHAPES",
    "REGISTRY_NAME",
    "ArchiveFormatError",
    "ChecksumMismatchError",
    "ClassifiedMonth",
    "Coverage",
    "Gap",
    "GapKind",
    "HistoricalDataError",
    "HistoricalStore",
    "IngestResult",
    "IrregularRow",
    "KindedGap",
    "ManifestEntry",
    "ManifestError",
    "Problem",
    "RegistryEntry",
    "RegistryKind",
    "Row",
    "RowShape",
    "StoredFileError",
    "StoredReport",
    "check_stored",
    "classify_gaps",
    "classify_times",
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
REGISTRY_NAME: Final = "IRREGULAR.jsonl"

_ARCHIVE_FIELDS: Final = 12
_STORED_FIELDS: Final = 7
_MAX_ROW_PROBLEMS: Final = 5
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
    #: Registry lines this month holds (see ``IRREGULAR.jsonl``). These three keys are
    #: OPTIONAL in a manifest line and written only when not at their default, so a line
    #: written before the registry existed reads as no registry lines, byte for byte.
    registered: int = 0
    quarantined: int = 0
    registry_sha256: str = ""


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
    #: The registry lines of every month in ``entries``, read in the same pass.
    registry: dict[str, tuple[RegistryEntry, ...]] = field(default_factory=dict)


class RowShape(str, Enum):
    """How a row differs from a regular bar. Every member is written by :func:`classify_times`."""

    SHORT_BAR = "short_bar"
    ONE_MS_LATE = "one_ms_late"
    WHOLE_SECOND = "whole_second"
    OFF_GRID = "off_grid"
    CLOSE_NOT_AFTER_OPEN = "close_not_after_open"


#: The shapes whose rows are not stored. Every other shape is stored and registered.
QUARANTINED_SHAPES: Final = frozenset({RowShape.OFF_GRID, RowShape.CLOSE_NOT_AFTER_OPEN})

#: A close this many milliseconds before the regular one is on a whole second.
_WHOLE_SECOND_SHORTFALL: Final = 999


@dataclass(frozen=True)
class IrregularRow:
    """A row that is not a regular bar: where it was, what shape, and the archive's own line.

    ``line`` is 1-based in the archive file. ``raw`` is the line as the archive wrote it,
    with every field, so nothing about a quarantined row is lost by not storing it.
    """

    line: int
    shape: RowShape
    open_time_ms: int
    raw: str


@dataclass(frozen=True)
class ClassifiedMonth:
    """One archive month after classification.

    ``rows`` are the bars to store, verbatim and ascending. ``registered`` are the stored
    rows whose close differs from the regular one, and ``quarantined`` are the rows that
    were not stored. A row is in at most one of ``registered`` and ``quarantined``, and a
    registered row is also in ``rows``.
    """

    rows: tuple[Row, ...]
    registered: tuple[IrregularRow, ...]
    quarantined: tuple[IrregularRow, ...]


@dataclass(frozen=True)
class IngestResult:
    """What ``ingest_zip`` stored and what it set aside."""

    entry: ManifestEntry
    registered: tuple[IrregularRow, ...]
    quarantined: tuple[IrregularRow, ...]


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


def _check_prices(row: Row) -> None:
    """I3: every price is positive and the low and high enclose the open and close."""
    open_, high, low, close = (Decimal(x) for x in (row.open, row.high, row.low, row.close))
    if min(open_, high, low, close) <= 0:
        raise ArchiveFormatError("a price is not positive")
    if not low <= min(open_, close) <= max(open_, close) <= high:
        raise ArchiveFormatError("the low and high do not enclose the open and close")


def classify_times(open_ms: int, close_ms: int, interval_ms: int) -> RowShape | None:
    """The shape of a bar's times: ``None`` for a regular bar, else its :class:`RowShape`.

    The order is the ruling's. A bar that opens off the interval grid is ``OFF_GRID``
    whatever its close is, and one that closes at or before its own open is
    ``CLOSE_NOT_AFTER_OPEN``; both are quarantined. Otherwise the offset of the close from
    the regular ``open + interval - 1`` decides: 0 is regular, +1 is ``ONE_MS_LATE``, -999
    is ``WHOLE_SECOND`` (the close is on a whole second), and any other earlier close is a
    ``SHORT_BAR``. A close later than one millisecond past the regular one is a shape no
    ruling covers, and it raises ``ArchiveFormatError`` so that its month is refused.
    """
    if open_ms % interval_ms:
        return RowShape.OFF_GRID
    if close_ms <= open_ms:
        return RowShape.CLOSE_NOT_AFTER_OPEN
    offset = close_ms - (open_ms + interval_ms - 1)
    if offset == 0:
        return None
    if offset == 1:
        return RowShape.ONE_MS_LATE
    if offset == -_WHOLE_SECOND_SHORTFALL:
        return RowShape.WHOLE_SECOND
    if offset < 0:
        return RowShape.SHORT_BAR
    raise ArchiveFormatError(
        f"close_time {close_ms} is not open_time {open_ms} + {interval_ms} - 1: it is {offset} ms "
        "past the bar's end, a shape this importer has no class for"
    )


def _normalise_row(fields: Sequence[str]) -> Row:
    if len(fields) != _ARCHIVE_FIELDS:
        raise ArchiveFormatError(f"a row has {len(fields)} fields, not {_ARCHIVE_FIELDS}")
    if len(fields[0]) != len(fields[6]):
        raise ArchiveFormatError("open_time and close_time are in different units")
    row = Row(
        open_time_ms=_open_time_ms(fields[0]),
        open=_money(fields[1], "open"),
        high=_money(fields[2], "high"),
        low=_money(fields[3], "low"),
        close=_money(fields[4], "close"),
        volume=_money(fields[5], "volume"),
        close_time_ms=_close_time_ms(fields[6]),
    )
    _check_prices(row)
    return row


def normalise_archive(csv_text: str, *, interval: str, month: str) -> ClassifiedMonth:
    """Parse and classify one monthly archive CSV; refuse what no class covers.

    No header is expected (the archive has none), every row has exactly twelve fields in
    one unit, every price is positive and encloses its bar, ``open_time`` strictly
    increases over EVERY row (a quarantined one included) and lies inside ``month``. A row
    of a known shape never refuses the month: see :func:`classify_times`.
    """
    interval_ms = _require_interval(interval)
    start_ms, end_ms = month_bounds_ms(month)
    rows: list[Row] = []
    registered: list[IrregularRow] = []
    quarantined: list[IrregularRow] = []
    previous: int | None = None
    for number, line in enumerate(csv_text.splitlines(), start=1):
        try:
            row = _normalise_row(line.split(","))
            shape = classify_times(row.open_time_ms, row.close_time_ms, interval_ms)
        except ArchiveFormatError as exc:
            raise ArchiveFormatError(f"line {number}: {exc}") from exc
        if not start_ms <= row.open_time_ms < end_ms:
            raise ArchiveFormatError(
                f"line {number}: open_time {row.open_time_ms} is outside {month}"
            )
        if previous is not None and row.open_time_ms <= previous:
            raise ArchiveFormatError(f"line {number}: open_time does not increase")
        previous = row.open_time_ms
        if shape is None:
            rows.append(row)
        elif shape in QUARANTINED_SHAPES:
            quarantined.append(IrregularRow(number, shape, row.open_time_ms, line))
        else:
            rows.append(row)
            registered.append(IrregularRow(number, shape, row.open_time_ms, line))
    if not rows and not quarantined:
        raise ArchiveFormatError("the archive holds no rows")
    return ClassifiedMonth(tuple(rows), tuple(registered), tuple(quarantined))


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


class GapKind(str, Enum):
    """Why a run of bars is missing from what is stored."""

    #: The archive has no bar there, or the bars are in a month it could not give us.
    OMITTED = "omitted"
    #: The archive had a row for it that was set aside at ingest (owner's ruling R-N).
    QUARANTINED = "quarantined"


@dataclass(frozen=True)
class KindedGap:
    """A run of missing bars of one kind: ``start_ms`` inclusive, ``end_ms`` exclusive."""

    start_ms: int
    end_ms: int
    missing: int
    kind: GapKind


def classify_gaps(
    gaps: Sequence[Gap], quarantined_opens_ms: Iterable[int], interval_ms: int
) -> tuple[KindedGap, ...]:
    """Split each gap into maximal runs of one kind.

    A missing bar's slot, ``[slot, slot + interval)``, is ``QUARANTINED`` if a row that
    was set aside opened inside it, and ``OMITTED`` otherwise. A quarantined row that opened
    in a slot a stored bar already holds is not in any gap and changes nothing. The runs of
    one gap cover it exactly, in order, so the missing bars of the result add up to the
    gaps' own. A gap that is not on the interval grid is refused: it did not come from
    :func:`find_gaps` on stored bars.
    """
    slots = sorted({opened - opened % interval_ms for opened in quarantined_opens_ms})
    result: list[KindedGap] = []

    def add(start: int, end: int, kind: GapKind) -> None:
        result.append(KindedGap(start, end, (end - start) // interval_ms, kind))

    for gap in gaps:
        if gap.start_ms % interval_ms or gap.end_ms % interval_ms:
            raise ValueError(f"{gap.start_ms}..{gap.end_ms} is not on the {interval_ms} ms grid")
        cursor = gap.start_ms
        index = bisect_left(slots, gap.start_ms)
        stop = bisect_left(slots, gap.end_ms)
        while index < stop:
            run_start = slots[index]
            run_end = run_start + interval_ms
            index += 1
            while index < stop and slots[index] == run_end:
                run_end += interval_ms
                index += 1
            if run_start > cursor:
                add(cursor, run_start, GapKind.OMITTED)
            add(run_start, run_end, GapKind.QUARANTINED)
            cursor = run_end
        if cursor < gap.end_ms:
            add(cursor, gap.end_ms, GapKind.OMITTED)
    return tuple(result)


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
    """The manifest line of an entry; an optional key at its default is left out.

    That is the whole compatibility mechanism and it is NOT a schema version: a line
    written before the registry existed has exactly the required keys, and an entry with
    no registry lines serialises to exactly those keys again, so rewriting a manifest
    (``_record`` rewrites all of it) leaves every such line byte for byte as it was.
    """
    record = asdict(entry)
    for key, default in _OPTIONAL_ENTRY_DEFAULTS.items():
        if record[key] == default:
            del record[key]
    return json.dumps(record, sort_keys=True, separators=(",", ":"))


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
_OPTIONAL_ENTRY_TYPES: Final = {"registered": int, "quarantined": int, "registry_sha256": str}
_OPTIONAL_ENTRY_DEFAULTS: Final = {"registered": 0, "quarantined": 0, "registry_sha256": ""}


def _entry_from(raw: object) -> ManifestEntry:
    """Build an entry from a decoded manifest line, or raise ``ValueError``.

    A manifest is a file a person can edit, and ``file`` is joined to the data root, so
    the entry must name exactly the path its own symbol, interval and month imply. Every
    required key must be present and no key outside the required and the optional ones may
    be; an absent optional key reads as its default. The registry digest is present exactly
    when the month holds registry lines.
    """
    allowed = set(_ENTRY_TYPES) | set(_OPTIONAL_ENTRY_TYPES)
    if not isinstance(raw, dict) or not set(_ENTRY_TYPES) <= set(raw) <= allowed:
        raise ValueError("a manifest line is an object with the entry's fields and no others")
    for key, kind in (_ENTRY_TYPES | _OPTIONAL_ENTRY_TYPES).items():
        if key in raw and type(raw[key]) is not kind:
            raise ValueError(f"{key} is not a {kind.__name__}: {raw[key]!r}")
    entry = ManifestEntry(**raw)
    try:
        canonical = month_file(Path(), entry.symbol, entry.interval, entry.month).as_posix()
    except ArchiveFormatError as exc:
        raise ValueError(str(exc)) from exc
    if entry.file != canonical:
        raise ValueError(f"file {entry.file!r} is not {canonical!r}")
    if entry.registered < 0 or entry.quarantined < 0:
        raise ValueError("a registry count is negative")
    if (entry.registered + entry.quarantined > 0) != (entry.registry_sha256 != ""):
        raise ValueError("registry_sha256 is present exactly when the month has registry lines")
    if entry.registry_sha256 and _SHA256.fullmatch(entry.registry_sha256) is None:
        raise ValueError(f"not a SHA-256 digest: {entry.registry_sha256!r}")
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


class RegistryKind(str, Enum):
    """Whether a registry line describes a row that was stored or one that was set aside."""

    REGISTERED = "registered"
    QUARANTINED = "quarantined"


@dataclass(frozen=True)
class RegistryEntry:
    """One line of a series' ``IRREGULAR.jsonl``.

    ``raw`` is the archive's own line with every field, ``line`` its 1-based position in
    the archive file and ``source_url`` the zip it came from. A ``REGISTERED`` line has a
    stored row with the same ``open_time_ms``; a ``QUARANTINED`` one has none.
    """

    month: str
    line: int
    kind: RegistryKind
    shape: RowShape
    open_time_ms: int
    raw: str
    source_url: str


_REGISTRY_TYPES: Final = {
    "month": str,
    "line": int,
    "kind": str,
    "shape": str,
    "open_time_ms": int,
    "raw": str,
    "source_url": str,
}


def _registry_line(entry: RegistryEntry) -> str:
    record = {
        "month": entry.month,
        "line": entry.line,
        "kind": entry.kind.value,
        "shape": entry.shape.value,
        "open_time_ms": entry.open_time_ms,
        "raw": entry.raw,
        "source_url": entry.source_url,
    }
    return json.dumps(record, sort_keys=True, separators=(",", ":"))


def _registry_from(raw: object) -> RegistryEntry:
    """Build a registry entry from a decoded line, or raise ``ValueError``."""
    if not isinstance(raw, dict) or set(raw) != set(_REGISTRY_TYPES):
        raise ValueError("a registry line is an object with exactly the entry's fields")
    for key, kind in _REGISTRY_TYPES.items():
        if type(raw[key]) is not kind:
            raise ValueError(f"{key} is not a {kind.__name__}: {raw[key]!r}")
    if _MONTH.fullmatch(raw["month"]) is None or raw["line"] < 1:
        raise ValueError("a registry line names a month and a 1-based line number")
    entry = RegistryEntry(
        month=raw["month"],
        line=raw["line"],
        kind=RegistryKind(raw["kind"]),
        shape=RowShape(raw["shape"]),
        open_time_ms=raw["open_time_ms"],
        raw=raw["raw"],
        source_url=raw["source_url"],
    )
    if (entry.kind is RegistryKind.QUARANTINED) != (entry.shape in QUARANTINED_SHAPES):
        raise ValueError(f"a {entry.kind.value} line cannot have the shape {entry.shape.value}")
    return entry


def _registry_text(entries: Sequence[RegistryEntry]) -> str:
    return "".join(_registry_line(entry) + "\n" for entry in entries)


def _read_registry(path: Path) -> tuple[dict[str, list[RegistryEntry]], list[Problem]]:
    by_month: dict[str, list[RegistryEntry]] = {}
    problems: list[Problem] = []
    if not path.exists():
        return by_month, problems
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        return by_month, [Problem("bad_registry_line", None, f"not UTF-8: {exc}")]
    for number, line in enumerate(text.splitlines(), start=1):
        try:
            entry = _registry_from(json.loads(line))
        except ValueError as exc:
            problems.append(Problem("bad_registry_line", None, f"line {number}: {exc}"))
            continue
        by_month.setdefault(entry.month, []).append(entry)
    return by_month, problems


def _registry_entries(
    month: str,
    source_url: str,
    registered: Sequence[IrregularRow],
    quarantined: Sequence[IrregularRow],
) -> list[RegistryEntry]:
    entries = [
        RegistryEntry(
            month, r.line, RegistryKind.REGISTERED, r.shape, r.open_time_ms, r.raw, source_url
        )
        for r in registered
    ]
    entries.extend(
        RegistryEntry(
            month, r.line, RegistryKind.QUARANTINED, r.shape, r.open_time_ms, r.raw, source_url
        )
        for r in quarantined
    )
    return sorted(entries, key=lambda entry: entry.line)


def _rewrite_registry(
    path: Path, by_month: dict[str, list[RegistryEntry]], month: str, entries: list[RegistryEntry]
) -> None:
    """Replace one month's lines and write the whole sidecar atomically.

    A sidecar left with no lines at all is removed, so a store with nothing irregular has
    no sidecar and the absence of the file means the same as an empty one.
    """
    if entries:
        by_month[month] = entries
    else:
        by_month.pop(month, None)
    text = "".join(_registry_text(by_month[m]) for m in sorted(by_month))
    if text:
        _atomic_write(path, text.encode("utf-8"))
    else:
        path.unlink(missing_ok=True)


def write_month(
    root: Path,
    symbol: str,
    interval: str,
    month: str,
    rows: Sequence[Row],
    *,
    source_url: str,
    zip_sha256: str,
    registered: Sequence[IrregularRow] = (),
    quarantined: Sequence[IrregularRow] = (),
) -> ManifestEntry:
    """Store one month: the CSV, then its registry lines, then the manifest line.

    The manifest is rewritten whole and atomically, so a power cut leaves either the
    old manifest or the new one and never a torn line, and the manifest line is the
    commit point. A month whose CSV was renamed and whose manifest line was not yet
    written is simply not listed, and the next run stores it again with the same bytes;
    any registry lines it had written are reported as ``orphan_registry`` until then.
    The sidecar is read, and refused if unreadable, BEFORE anything is written.
    """
    if not rows:
        raise ArchiveFormatError("nothing to store")
    path = month_file(root, symbol, interval, month)
    directory = series_dir(root, symbol, interval)
    lines = _registry_entries(month, source_url, registered, quarantined)
    by_month, registry_problems = _read_registry(directory / REGISTRY_NAME)
    if registry_problems:
        raise ManifestError(
            f"{directory / REGISTRY_NAME} has {len(registry_problems)} unreadable lines; not extended"
        )
    data = _render_csv(rows)
    _atomic_write(path, data)
    _rewrite_registry(directory / REGISTRY_NAME, by_month, month, lines)
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
        registered=len(registered),
        quarantined=len(quarantined),
        registry_sha256=(
            hashlib.sha256(_registry_text(lines).encode("utf-8")).hexdigest() if lines else ""
        ),
    )
    _record(directory / MANIFEST_NAME, entry)
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
) -> IngestResult:
    """Verify, unzip, classify and store one monthly archive file.

    The checksum is verified first, so a corrupt download is rejected before a byte of
    it is parsed and nothing is stored. The zip must hold exactly the one member the
    name implies, and that member's size is capped, because a decompression bomb is the
    cheapest way a download can hurt this machine. The rows that are stored are the
    month's verbatim bars; the registered and quarantined rows are written to the series'
    registry with the zip's ``source_url`` and are returned in the result as well.
    A month in which every row is quarantined has nothing to store and is refused.
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
    classified = normalise_archive(text, interval=interval, month=month)
    if not classified.rows:
        raise ArchiveFormatError("every row of the month was quarantined; nothing to store")
    entry = write_month(
        root,
        symbol,
        interval,
        month,
        classified.rows,
        source_url=source_url,
        zip_sha256=expected_sha256,
        registered=classified.registered,
        quarantined=classified.quarantined,
    )
    return IngestResult(entry, classified.registered, classified.quarantined)


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


def _check_registry(entry: ManifestEntry, lines: Sequence[RegistryEntry]) -> list[Problem]:
    """The registry lines of a month against the counts and the digest its manifest line states."""
    registered = sum(line.kind is RegistryKind.REGISTERED for line in lines)
    quarantined = len(lines) - registered
    digest = hashlib.sha256(_registry_text(lines).encode("utf-8")).hexdigest() if lines else ""
    if (registered, quarantined, digest) != (
        entry.registered,
        entry.quarantined,
        entry.registry_sha256,
    ):
        return [
            Problem(
                "registry_mismatch",
                entry.month,
                f"the manifest states {entry.registered} registered and {entry.quarantined} "
                f"quarantined, the registry holds {registered} and {quarantined}"
                + ("" if digest == entry.registry_sha256 else " (digest differs)"),
            )
        ]
    return []


def _stored_row_problems(
    root: Path, entry: ManifestEntry, lines: Sequence[RegistryEntry]
) -> list[Problem]:
    """Re-check every stored row of a month under the rule it was ingested under.

    A stored row must open on the grid and close after it opens, carry positive prices
    that enclose its open and close, ascend, and lie inside the month; and the rows whose
    close is not the regular one must be exactly the month's registered lines, each with
    the shape it was registered under. Reports the first few faults, not every one.
    """
    interval_ms = INTERVAL_MS[entry.interval]
    start_ms, end_ms = month_bounds_ms(entry.month)
    problems: list[Problem] = []
    flagged: dict[int, RowShape] = {}
    previous: int | None = None
    text = (root / entry.file).read_text(encoding="ascii")

    def bad(kind: str, number: int, detail: str) -> None:
        if len(problems) < _MAX_ROW_PROBLEMS:
            problems.append(Problem(kind, entry.month, f"row {number}: {detail}"))

    for number, line in enumerate(text.split("\n")[1:-1], start=1):
        fields = line.split(",")
        try:
            if len(fields) != _STORED_FIELDS or _DIGITS.fullmatch(fields[0]) is None:
                raise ArchiveFormatError("not a stored row")
            if _DIGITS.fullmatch(fields[6]) is None:
                raise ArchiveFormatError("close_time is not an integer")
            row = Row(
                int(fields[0]),
                _money(fields[1], "open"),
                _money(fields[2], "high"),
                _money(fields[3], "low"),
                _money(fields[4], "close"),
                _money(fields[5], "volume"),
                int(fields[6]),
            )
            _check_prices(row)
            shape = classify_times(row.open_time_ms, row.close_time_ms, interval_ms)
        except ArchiveFormatError as exc:
            bad("bad_stored_row", number, str(exc))
            continue
        if not start_ms <= row.open_time_ms < end_ms:
            bad("bad_stored_row", number, "open_time is outside the month")
        if previous is not None and row.open_time_ms <= previous:
            bad("bad_stored_row", number, "open_time does not increase")
        previous = row.open_time_ms
        if shape in QUARANTINED_SHAPES:
            bad("bad_stored_row", number, f"a {shape.value} row is stored")
        elif shape is not None:
            flagged[row.open_time_ms] = shape
    registered = {
        line.open_time_ms: line.shape for line in lines if line.kind is RegistryKind.REGISTERED
    }
    differing = sorted(
        o for o in flagged.keys() | registered.keys() if flagged.get(o) != registered.get(o)
    )
    if differing:
        problems.append(
            Problem(
                "registry_rows_mismatch",
                entry.month,
                f"{len(differing)} open times are stored irregular and not registered under the "
                f"same shape, or registered and not stored irregular (first: {differing[0]})",
            )
        )
    return problems


def check_stored(root: Path, symbol: str, interval: str, *, rows: bool = False) -> StoredReport:
    """Re-verify everything stored for one series against its manifest and its registry.

    A month is in ``entries`` only if its file exists, hashes to the manifest's digest,
    agrees with the manifest on rows and first and last open time, and its registry lines
    match the counts and the digest the manifest states. A CSV file with no manifest line,
    registry lines for a month the manifest does not list, and every unreadable manifest or
    registry line, are problems too. With ``rows=True`` every stored row is also re-checked
    under the ingest rule and against the registry, which reads the whole series.
    """
    directory = series_dir(root, symbol, interval)
    entries, problems = _read_manifest(directory / MANIFEST_NAME)
    registry, registry_problems = _read_registry(directory / REGISTRY_NAME)
    problems.extend(registry_problems)
    for month in sorted(set(registry) - set(entries)):
        problems.append(
            Problem(
                "orphan_registry",
                month,
                f"{len(registry[month])} registry lines for a month the manifest does not list",
            )
        )
    verified: dict[str, ManifestEntry] = {}
    for month, entry in entries.items():
        found = _check_entry(root, entry) + _check_registry(entry, registry.get(month, []))
        if not found and rows:
            found = _stored_row_problems(root, entry, registry.get(month, []))
        problems.extend(found)
        if not found:
            verified[month] = entry
    if directory.is_dir():
        listed = {Path(entry.file).name for entry in entries.values()}
        for path in sorted(directory.glob("*.csv")):
            if path.name not in listed:
                problems.append(Problem("unlisted_file", None, path.name))
    return StoredReport(
        verified,
        tuple(problems),
        {month: tuple(registry.get(month, [])) for month in verified},
    )


@dataclass(frozen=True)
class Coverage:
    """What is stored for one series and what is missing from it.

    ``gaps`` are the runs of missing bars between the first stored bar and the last, plus,
    when ``until`` was given, the run missing after the last. With ``until``,
    ``bars + missing == grid_bars`` exactly, the grid being the bars from the first stored
    one up to ``until``. A month that fails verification is not counted in ``bars`` and
    shows up as a gap and in ``problems``.

    ``kinded_gaps`` split the same gaps by why the bars are missing, and
    ``omitted_bars + quarantined_bars == missing``. ``registered_rows`` and
    ``quarantined_rows`` count the registry lines of the verified months.
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
    kinded_gaps: tuple[KindedGap, ...] = ()
    omitted_bars: int = 0
    quarantined_bars: int = 0
    registered_rows: int = 0
    quarantined_rows: int = 0


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
        """Every problem with what is stored for one series; empty when it is clean.

        This is the deep check: besides each file's hash and the manifest's figures, every
        stored row is re-checked under the ingest rule and against the registry.
        """
        return check_stored(self._root, symbol, interval, rows=True).problems

    def registry(self, symbol: str, interval: str) -> tuple[RegistryEntry, ...]:
        """Every registry line of one series, by month then archive line.

        Raises ``StoredFileError`` if the sidecar has an unreadable line.
        """
        by_month, problems = _read_registry(
            series_dir(self._root, symbol, interval) / REGISTRY_NAME
        )
        if problems:
            raise StoredFileError(
                f"{symbol} {interval}: the registry has {len(problems)} bad lines"
            )
        return tuple(line for month in sorted(by_month) for line in by_month[month])

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
        kinded = classify_gaps(
            gaps,
            (
                line.open_time_ms
                for lines in report.registry.values()
                for line in lines
                if line.kind is RegistryKind.QUARANTINED
            ),
            interval_ms,
        )
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
            kinded_gaps=kinded,
            omitted_bars=sum(g.missing for g in kinded if g.kind is GapKind.OMITTED),
            quarantined_bars=sum(g.missing for g in kinded if g.kind is GapKind.QUARANTINED),
            registered_rows=sum(e.registered for e in report.entries.values()),
            quarantined_rows=sum(e.quarantined for e in report.entries.values()),
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
