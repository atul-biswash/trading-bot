"""Record Binance Spot Testnet klines into a historical store of their own (S4, R-AN).

The venue's Testnet keeps only the history since its last reset (``docs/RUN_LEDGER.md``
section 36: the earliest bar was ``2026-10-07T10:32Z`` on two readings an hour apart), and a
reset takes everything before it. S4 compares a backtest with a live Testnet run, so the backtest
needs the bars the live bot saw, and the only way to have them after a reset is to have copied
them first. This module is the copying: keyless, read-only, and idempotent.

**It stores what the historical store already stores, in the same files.** A closed bar is a
:class:`~trading_bot.data.historical.Row` of strings exactly as the venue wrote them, a month is
one CSV under ``<root>/<SYMBOL>/<interval>/`` with a ``MANIFEST.jsonl`` line, and every write goes
through :func:`~trading_bot.data.historical.write_month`, so the manifest is rewritten whole and
atomically and a power cut leaves the old month or the new one. The root is NOT the mainnet
store's; ``HistoricalStore`` reads it unchanged. A REST kline has twelve fields and is classified
by :func:`~trading_bot.data.historical.normalise_archive` like an archive row, so an irregular bar
is registered or quarantined by the same rules and never altered.

**Where a REST fetch differs from an archive month, and what the manifest's two source fields
mean here.** There is no zip and no checksum, so ``source_url`` is the klines endpoint with its
symbol and interval, and ``zip_sha256`` is the SHA-256 of the LAST response body that contributed a
row to that month. The full account of every fetch is ``RECORDER.jsonl`` beside the manifest: one
line per series per run, appended and fsynced, naming each page's URL and SHA-256, the server time,
the rows added and every gap. A month is partial until the month ends, and is rewritten in full each
time it grows.

**Only closed bars are stored.** The server's clock is read first (``/api/v3/time``) and a bar is
kept only if its close time is strictly before it, so the forming bar is never written and a stored
bar is final.

**A reset is detected, not assumed, and nothing is written when one is.** Before any series is
extended, the last stored bar of every series is fetched again and compared in all seven fields. A
bar the venue no longer has, or one that differs, means the venue discarded or rewrote history; every
series then refuses (:class:`VenueResetError`) before a byte of the store, the manifest or the log is
touched. The operator retires the store and starts a new one: appending after a reset would join two
different price histories into one series.

**A gap is reported and never filled.** The first new bar after the last stored one, and every break
inside what is fetched, becomes a :class:`~trading_bot.data.historical.Gap` in the report and in
``RECORDER.jsonl``. The store's own ``coverage`` reports it again.

**The network is injected.** Every request goes through a :data:`Fetcher`, ``url -> bytes``;
this module opens no socket and reads no clock of its own. ``scripts/record_testnet_klines.py``
supplies the one fetcher that talks to the network.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Final

from trading_bot.data.historical import (
    INTERVAL_MS,
    ArchiveFormatError,
    ClassifiedMonth,
    Gap,
    HistoricalStore,
    IrregularRow,
    ManifestEntry,
    Problem,
    RegistryEntry,
    RegistryKind,
    Row,
    check_stored,
    find_gaps,
    normalise_archive,
    series_dir,
    write_month,
)

__all__ = [
    "KLINES_LIMIT",
    "MAX_PAGES",
    "RECORDER_LOG_NAME",
    "TESTNET_BASE",
    "BadKlineError",
    "Fetcher",
    "RecorderError",
    "RecorderFetchError",
    "RecorderStoreError",
    "RestBar",
    "SeriesReport",
    "StoreCheck",
    "VenueResetError",
    "check_overlap",
    "klines_url",
    "parse_klines",
    "parse_server_time",
    "record_all",
    "record_series",
    "source_url",
    "time_url",
    "verify_store",
]

Fetcher = Callable[[str], bytes]

TESTNET_BASE: Final = "https://testnet.binance.vision"
#: The venue's own page size for ``/api/v3/klines``. Weight 2 whatever the limit (M5m-224).
KLINES_LIMIT: Final = 1000
#: A backfill of a month of one-minute bars is 44 pages; this is a ceiling on a runaway loop.
MAX_PAGES: Final = 500
RECORDER_LOG_NAME: Final = "RECORDER.jsonl"

_SYMBOL = re.compile(r"[A-Z0-9]{5,20}")
_REST_FIELDS: Final = 12
_EPOCH: Final = datetime(1970, 1, 1, tzinfo=timezone.utc)
_MS: Final = timedelta(milliseconds=1)


class RecorderError(Exception):
    """The recorder refused or failed; the subclass says which, and the script's exit status."""


class RecorderFetchError(RecorderError):
    """A request failed or its answer was not a klines or time response."""


class VenueResetError(RecorderError):
    """The last stored bar is gone from the venue or differs: history was discarded or rewritten."""


class BadKlineError(RecorderError):
    """A bar no class of the importer covers, or a page that is out of order."""


class RecorderStoreError(RecorderError):
    """What is stored does not verify, so nothing is appended to it."""


@dataclass(frozen=True)
class RestBar:
    """One kline from the REST response: the seven stored fields and the twelve-field raw line."""

    open_time_ms: int
    open: str
    high: str
    low: str
    close: str
    volume: str
    close_time_ms: int
    line: str

    def as_row(self) -> Row:
        return Row(
            self.open_time_ms,
            self.open,
            self.high,
            self.low,
            self.close,
            self.volume,
            self.close_time_ms,
        )


@dataclass(frozen=True)
class SeriesReport:
    """What one run did to one series."""

    symbol: str
    interval: str
    pages: int
    rows_added: int
    first_open_ms: int | None
    last_open_ms: int | None
    stored_after: int
    gaps: tuple[Gap, ...]
    registered: int
    quarantined: int
    forming_skipped: int


@dataclass(frozen=True)
class StoreCheck:
    """The result of verifying one series: its bars, its months, its gaps and every problem."""

    symbol: str
    interval: str
    bars: int
    months: tuple[str, ...]
    first_open_ms: int | None
    last_open_ms: int | None
    gaps: tuple[Gap, ...]
    problems: tuple[Problem, ...]


def _require_series(symbol: str, interval: str) -> int:
    if _SYMBOL.fullmatch(symbol) is None:
        raise ValueError(f"not a symbol: {symbol!r}")
    if interval not in INTERVAL_MS:
        raise ValueError(f"not a stored interval: {interval!r}")
    return INTERVAL_MS[interval]


def klines_url(symbol: str, interval: str, *, start_ms: int, limit: int = KLINES_LIMIT) -> str:
    """The Testnet klines request for bars opening at or after ``start_ms``."""
    _require_series(symbol, interval)
    if start_ms < 0 or not 1 <= limit <= KLINES_LIMIT:
        raise ValueError(f"start_ms {start_ms} or limit {limit} is out of range")
    return (
        f"{TESTNET_BASE}/api/v3/klines?symbol={symbol}&interval={interval}"
        f"&startTime={start_ms}&limit={limit}"
    )


def time_url() -> str:
    return f"{TESTNET_BASE}/api/v3/time"


def source_url(symbol: str, interval: str) -> str:
    """The manifest's ``source_url`` for a series: the endpoint, without a page's window."""
    _require_series(symbol, interval)
    return f"{TESTNET_BASE}/api/v3/klines?symbol={symbol}&interval={interval}"


def _is_int(value: object) -> bool:
    return type(value) is int


def parse_server_time(body: bytes) -> int:
    """``serverTime`` in milliseconds from a ``/api/v3/time`` response."""
    try:
        payload = json.loads(body)
    except ValueError as exc:
        raise RecorderFetchError(f"the time response is not JSON: {exc}") from exc
    if not isinstance(payload, dict) or not _is_int(payload.get("serverTime")):
        raise RecorderFetchError("the time response has no integer serverTime")
    return int(payload["serverTime"])


def parse_klines(body: bytes) -> list[RestBar]:
    """The bars of a ``/api/v3/klines`` response, in the order the venue gave them.

    Each element must have twelve fields, integer times and string prices, or the response is
    refused whole. Nothing about a price is judged here; ``normalise_archive`` does that.
    """
    try:
        payload = json.loads(body)
    except ValueError as exc:
        raise RecorderFetchError(f"the klines response is not JSON: {exc}") from exc
    if not isinstance(payload, list):
        raise RecorderFetchError("the klines response is not a list")
    bars: list[RestBar] = []
    for number, item in enumerate(payload, start=1):
        if not isinstance(item, list) or len(item) != _REST_FIELDS:
            raise RecorderFetchError(f"kline {number} does not have {_REST_FIELDS} fields")
        if not (_is_int(item[0]) and _is_int(item[6])):
            raise RecorderFetchError(f"kline {number} has a time that is not an integer")
        if not all(isinstance(item[index], str) for index in (1, 2, 3, 4, 5)):
            raise RecorderFetchError(f"kline {number} has a price or volume that is not a string")
        bars.append(
            RestBar(
                open_time_ms=item[0],
                open=item[1],
                high=item[2],
                low=item[3],
                close=item[4],
                volume=item[5],
                close_time_ms=item[6],
                line=",".join(str(field) for field in item),
            )
        )
    return bars


def _month_of(open_time_ms: int) -> str:
    moment = _EPOCH + open_time_ms * _MS
    return f"{moment.year:04d}-{moment.month:02d}"


def _read_rows(root: Path, entry: ManifestEntry) -> list[Row]:
    """The stored rows of one verified month, as the writer rendered them."""
    lines = (root / entry.file).read_bytes().decode("ascii").split("\n")
    rows = []
    for line in lines[1:-1]:
        f = line.split(",")
        rows.append(Row(int(f[0]), f[1], f[2], f[3], f[4], f[5], int(f[6])))
    return rows


@dataclass(frozen=True)
class _State:
    entries: dict[str, ManifestEntry]
    registry: tuple[RegistryEntry, ...]
    last_row: Row | None
    last_seen_ms: int | None


def _load_state(root: Path, symbol: str, interval: str) -> _State:
    """What is stored for one series, after verifying it; a store that fails is not extended."""
    report = check_stored(root, symbol, interval)
    if report.problems:
        shown = "; ".join(
            f"{p.kind} {p.month or ''} {p.detail}".strip() for p in report.problems[:3]
        )
        raise RecorderStoreError(
            f"{symbol} {interval}: the stored series has {len(report.problems)} problems "
            f"and is not extended ({shown})"
        )
    registry = HistoricalStore(root).registry(symbol, interval) if report.entries else ()
    last_row: Row | None = None
    seen: list[int] = [line.open_time_ms for line in registry]
    if report.entries:
        last_month = max(report.entries)
        last_row = _read_rows(root, report.entries[last_month])[-1]
        seen.append(last_row.open_time_ms)
    return _State(dict(report.entries), registry, last_row, max(seen) if seen else None)


def check_overlap(root: Path, symbol: str, interval: str, *, fetcher: Fetcher) -> None:
    """Fetch the last stored bar again and compare it in all seven fields.

    :raises VenueResetError: the venue has no bar opening then, or it differs from the stored one.
    """
    _require_series(symbol, interval)
    state = _load_state(root, symbol, interval)
    if state.last_row is None:
        return
    stored = state.last_row
    bars = parse_klines(
        fetcher(klines_url(symbol, interval, start_ms=stored.open_time_ms, limit=1))
    )
    if not bars or bars[0].open_time_ms != stored.open_time_ms:
        raise VenueResetError(
            f"{symbol} {interval}: the venue no longer has the bar that opens "
            f"{_EPOCH + stored.open_time_ms * _MS:%Y-%m-%dT%H:%M:%SZ}, which this store holds: "
            "history was discarded"
        )
    if bars[0].as_row() != stored:
        raise VenueResetError(
            f"{symbol} {interval}: the bar that opens "
            f"{_EPOCH + stored.open_time_ms * _MS:%Y-%m-%dT%H:%M:%SZ} differs from the stored one: "
            f"stored {stored}, venue {bars[0].as_row()}: history was rewritten"
        )


def _append_event(directory: Path, event: Mapping[str, object]) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    line = json.dumps(event, sort_keys=True, separators=(",", ":")) + "\n"
    with (directory / RECORDER_LOG_NAME).open("a", encoding="utf-8", newline="") as handle:
        handle.write(line)
        handle.flush()
        os.fsync(handle.fileno())


def _gap_record(gap: Gap) -> dict[str, int]:
    return {"start_ms": gap.start_ms, "end_ms": gap.end_ms, "missing": gap.missing}


def record_series(
    root: Path,
    symbol: str,
    interval: str,
    *,
    fetcher: Fetcher,
    server_time_ms: int,
    clock: Callable[[], datetime],
    meta: Mapping[str, str] | None = None,
    page_limit: int = KLINES_LIMIT,
) -> SeriesReport:
    """Extend one series with every closed bar the venue has after the last one stored.

    Every page is fetched BEFORE anything is written, so a failed request leaves the series as
    it was. The months touched are then written one by one, each atomically; if the process dies
    between two months the next run resumes from what reached the disk.

    :raises RecorderFetchError: a request failed or an answer was malformed.
    :raises BadKlineError: a bar no class covers, or a page that repeats or goes backwards.
    :raises RecorderStoreError: what is stored does not verify.
    """
    interval_ms = _require_series(symbol, interval)
    state = _load_state(root, symbol, interval)
    start = 0 if state.last_seen_ms is None else state.last_seen_ms + 1
    pages: list[dict[str, object]] = []
    fetched: list[tuple[RestBar, str]] = []
    forming = 0
    previous = state.last_seen_ms
    for _ in range(MAX_PAGES):
        url = klines_url(symbol, interval, start_ms=start, limit=page_limit)
        body = fetcher(url)
        digest = hashlib.sha256(body).hexdigest()
        bars = parse_klines(body)
        pages.append({"url": url, "sha256": digest, "rows": len(bars)})
        for bar in bars:
            if previous is not None and bar.open_time_ms <= previous:
                raise BadKlineError(
                    f"{symbol} {interval}: a bar opens at {bar.open_time_ms}, not after "
                    f"{previous}: a page repeated or went backwards"
                )
            previous = bar.open_time_ms
            if bar.close_time_ms < server_time_ms:
                fetched.append((bar, digest))
            else:
                forming += 1
        if len(bars) < page_limit:
            break
        start = bars[-1].open_time_ms + 1
    else:
        raise RecorderFetchError(f"{symbol} {interval}: more than {MAX_PAGES} pages; stopped")

    by_month: dict[str, list[tuple[RestBar, str]]] = {}
    for bar, digest in fetched:
        by_month.setdefault(_month_of(bar.open_time_ms), []).append((bar, digest))
    classified: dict[str, ClassifiedMonth] = {}
    for month, items in by_month.items():
        text = "\n".join(bar.line for bar, _ in items)
        try:
            classified[month] = normalise_archive(text, interval=interval, month=month)
        except ArchiveFormatError as exc:
            raise BadKlineError(f"{symbol} {interval} {month}: {exc}") from exc

    stored_opens: list[int] = []
    registered_total = quarantined_total = 0
    for month in sorted(classified):
        new = classified[month]
        entry = state.entries.get(month)
        old_rows = _read_rows(root, entry) if entry is not None else []
        old_registry = [line for line in state.registry if line.month == month]
        old_quarantined = [line for line in old_registry if line.kind is RegistryKind.QUARANTINED]
        base = len(old_rows) + len(old_quarantined)
        registered = [
            IrregularRow(line.line, line.shape, line.open_time_ms, line.raw)
            for line in old_registry
            if line.kind is RegistryKind.REGISTERED
        ] + [IrregularRow(r.line + base, r.shape, r.open_time_ms, r.raw) for r in new.registered]
        quarantined = [
            IrregularRow(line.line, line.shape, line.open_time_ms, line.raw)
            for line in old_quarantined
        ] + [IrregularRow(r.line + base, r.shape, r.open_time_ms, r.raw) for r in new.quarantined]
        registered_total += len(new.registered)
        quarantined_total += len(new.quarantined)
        rows = old_rows + list(new.rows)
        if not rows:
            continue  # only quarantined bars and nothing stored for the month: no manifest line
        last_digest = [digest for _, digest in by_month[month]][-1]
        write_month(
            root,
            symbol,
            interval,
            month,
            rows,
            source_url=source_url(symbol, interval),
            zip_sha256=last_digest,
            registered=registered,
            quarantined=quarantined,
        )
        stored_opens.extend(r.open_time_ms for r in new.rows)

    chain = ([state.last_row.open_time_ms] if state.last_row is not None else []) + stored_opens
    gaps = find_gaps(chain, interval_ms) if len(chain) > 1 else ()
    after = sum(entry.rows for entry in check_stored(root, symbol, interval).entries.values())
    report = SeriesReport(
        symbol=symbol,
        interval=interval,
        pages=len(pages),
        rows_added=len(stored_opens),
        first_open_ms=stored_opens[0] if stored_opens else None,
        last_open_ms=stored_opens[-1] if stored_opens else None,
        stored_after=after,
        gaps=gaps,
        registered=registered_total,
        quarantined=quarantined_total,
        forming_skipped=forming,
    )
    _append_event(
        series_dir(root, symbol, interval),
        {
            "at": clock().isoformat(),
            "event": "recorded" if stored_opens else "nothing_new",
            "symbol": symbol,
            "interval": interval,
            "server_time_ms": server_time_ms,
            "pages": pages,
            "rows_added": report.rows_added,
            "first_open_ms": report.first_open_ms,
            "last_open_ms": report.last_open_ms,
            "stored_after": report.stored_after,
            "gaps": [_gap_record(gap) for gap in gaps],
            "registered": registered_total,
            "quarantined": quarantined_total,
            "forming_skipped": forming,
            "meta": dict(meta or {}),
        },
    )
    return report


def record_all(
    root: Path,
    series: Sequence[tuple[str, str]],
    *,
    fetcher: Fetcher,
    clock: Callable[[], datetime],
    meta: Mapping[str, str] | None = None,
    page_limit: int = KLINES_LIMIT,
) -> tuple[SeriesReport, ...]:
    """One run: read the server's clock, check every overlap, then extend every series.

    The overlap check of EVERY series runs before the first write, so a reset found in any of
    them refuses the whole run with the store untouched.
    """
    server_ms = parse_server_time(fetcher(time_url()))
    for symbol, interval in series:
        check_overlap(root, symbol, interval, fetcher=fetcher)
    return tuple(
        record_series(
            root,
            symbol,
            interval,
            fetcher=fetcher,
            server_time_ms=server_ms,
            clock=clock,
            meta=meta,
            page_limit=page_limit,
        )
        for symbol, interval in series
    )


def verify_store(root: Path, series: Sequence[tuple[str, str]]) -> tuple[StoreCheck, ...]:
    """The deep check of each series (every stored row re-validated) and its coverage. No network."""
    checks = []
    store = HistoricalStore(root)
    for symbol, interval in series:
        _require_series(symbol, interval)
        problems = store.verify(symbol, interval)
        coverage = store.coverage(symbol, interval)
        checks.append(
            StoreCheck(
                symbol=symbol,
                interval=interval,
                bars=coverage.bars,
                months=coverage.months,
                first_open_ms=coverage.first_open_time_ms,
                last_open_ms=coverage.last_open_time_ms,
                gaps=coverage.gaps,
                problems=problems,
            )
        )
    return tuple(checks)
