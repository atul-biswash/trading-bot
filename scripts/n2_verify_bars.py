#!/usr/bin/env python
"""Compare the 4h and 1d bars aggregated from the 1m store with the venue's own klines.

Usage:
    python scripts/n2_verify_bars.py --out <scratch dir for the raw responses>

**IT READS ONE FIXED WINDOW, ``[2017-08-17, 2024-01-01)``, AND NOTHING AT OR AFTER THE END.**
The end is a constant and not an option. The store is read through ``aggregate_from_store``,
which opens no month file beginning at or after it, and the one venue URL this script may
request is the public mainnet ``https://api.binance.com/api/v3/klines`` with ``symbol``,
``interval``, ``startTime``, ``endTime`` and ``limit``: no key, no header and no signature.
A response holding a bar that opens at or after the end is an error, not a row to ignore.

**IT PRINTS COUNTS.** Per symbol and timeframe: the buckets compared, equal and mismatched
(by field), the complete and incomplete buckets of the aggregation, and the buckets only one
side has. The only values it prints are the rows of the mismatch list, capped at 50; the
time ranges of the unpaired buckets are printed as runs, also capped. It computes no return,
P&L, equity or metric.

**IT RUNS ONCE.** The raw responses and their SHA-256 are written to ``--out`` and the run
refuses a directory that already holds any, so a second run cannot overwrite the first's
evidence. ``--out`` may not be under the store or under a ``logs`` directory.

**THE NETWORK IS INJECTED.** Every request goes through a ``Fetcher``, ``url -> bytes``, and
the only one that opens a socket is ``fetch_url``, which refuses any URL that is not the
klines endpoint above and which treats a non-200 answer, a rate limit included, as an error.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Final, Protocol, TextIO

from trading_bot.data.aggregation import AggregatedBar, AggregationError, aggregate_from_store
from trading_bot.data.historical import INTERVAL_MS, HistoricalDataError, HistoricalStore

Fetcher = Callable[[str], bytes]

KLINES_URL: Final = "https://api.binance.com/api/v3/klines"
WINDOW_START: Final = datetime(2017, 8, 17, tzinfo=timezone.utc)
WINDOW_END: Final = datetime(2024, 1, 1, tzinfo=timezone.utc)
DEFAULT_SYMBOLS: Final = ("BTCUSDT", "ETHUSDT")
TIMEFRAMES: Final = ("1d", "4h")
PAGE_LIMIT: Final = 1000
FIELDS: Final = ("open", "high", "low", "close", "volume")
MISMATCH_CAP: Final = 50
RUN_CAP: Final = 20
EXIT_REFUSED: Final = 2
EXIT_ERROR: Final = 3

_EPOCH: Final = datetime(1970, 1, 1, tzinfo=timezone.utc)
_TIMEOUT_S: Final = 60.0
_MAX_BYTES: Final = 5_000_000


class VerifyError(Exception):
    """A request, a response or an input cannot be trusted: stop and say so."""


class _Response(Protocol):
    def read(self, size: int = ..., /) -> bytes: ...

    def __enter__(self) -> _Response: ...

    def __exit__(self, *exc: object) -> object: ...


Opener = Callable[[urllib.request.Request, float], _Response]


def _urlopen(request: urllib.request.Request, timeout: float) -> _Response:
    response: _Response = urllib.request.urlopen(request, timeout=timeout)
    return response


def epoch_ms(moment: datetime) -> int:
    return (moment - _EPOCH) // timedelta(milliseconds=1)


def fetch_url(url: str, *, opener: Opener = _urlopen) -> bytes:
    """GET ``url`` and return its body. Only the public klines endpoint is allowed."""
    if not url.startswith(KLINES_URL + "?"):
        raise VerifyError(f"refusing a URL outside the klines endpoint: {url}")
    request = urllib.request.Request(url, headers={"User-Agent": "trading-bot-n2-verify/1"})
    try:
        with opener(request, _TIMEOUT_S) as response:
            body = response.read(_MAX_BYTES + 1)
    except urllib.error.HTTPError as exc:
        raise VerifyError(f"{url}: HTTP {exc.code}") from exc
    except (urllib.error.URLError, TimeoutError, ConnectionError) as exc:
        raise VerifyError(f"{url}: {exc}") from exc
    if len(body) > _MAX_BYTES:
        raise VerifyError(f"{url}: more than {_MAX_BYTES} bytes")
    return body


def klines_url(symbol: str, timeframe: str, start_ms: int, end_ms: int, limit: int) -> str:
    query = urllib.parse.urlencode(
        {
            "symbol": symbol,
            "interval": timeframe,
            "startTime": start_ms,
            "endTime": end_ms,
            "limit": limit,
        }
    )
    return f"{KLINES_URL}?{query}"


@dataclass(frozen=True)
class VenueBar:
    open_ms: int
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal


def parse_page(body: bytes) -> list[VenueBar]:
    """The bars of one klines response; anything that is not the documented shape raises."""
    try:
        raw = json.loads(body)
    except ValueError as exc:
        raise VerifyError(f"a response is not JSON: {exc}") from exc
    if not isinstance(raw, list):
        raise VerifyError("a response is not a list of klines")
    found: list[VenueBar] = []
    for row in raw:
        if not isinstance(row, list) or len(row) < 6 or not isinstance(row[0], int):
            raise VerifyError("a kline is not [openTime, open, high, low, close, volume, ...]")
        try:
            figures = [Decimal(str(value)) for value in row[1:6]]
        except InvalidOperation as exc:
            raise VerifyError(f"a kline figure is not a decimal: {row[1:6]!r}") from exc
        found.append(VenueBar(row[0], *figures))
    return found


Saver = Callable[[str, bytes], None]


def fetch_series(
    fetcher: Fetcher,
    symbol: str,
    timeframe: str,
    *,
    save: Saver,
    pause: float,
    sleep: Callable[[float], None] = time.sleep,
    limit: int = PAGE_LIMIT,
) -> tuple[list[VenueBar], int]:
    """Every venue bar of one series with ``WINDOW_START <= open < WINDOW_END``, and the requests."""
    width = INTERVAL_MS[timeframe]
    start_ms = epoch_ms(WINDOW_START)
    end_ms = epoch_ms(WINDOW_END)
    cursor = start_ms
    bars: list[VenueBar] = []
    requests = 0
    while cursor < end_ms:
        if requests:
            sleep(pause)
        body = fetcher(klines_url(symbol, timeframe, cursor, end_ms - 1, limit))
        requests += 1
        save(f"{symbol}-{timeframe}-{requests:03d}.json", body)
        page = parse_page(body)
        if not page:
            break
        previous = bars[-1].open_ms if bars else None
        for bar in page:
            if bar.open_ms >= end_ms:
                raise VerifyError(f"{symbol} {timeframe}: a bar opens at or after the window end")
            if bar.open_ms < cursor or (previous is not None and bar.open_ms <= previous):
                raise VerifyError(f"{symbol} {timeframe}: open times do not increase")
            previous = bar.open_ms
        bars.extend(page)
        cursor = page[-1].open_ms + width
        if len(page) < limit:
            break
    return bars, requests


@dataclass(frozen=True)
class Mismatch:
    open_ms: int
    field: str
    aggregated: Decimal
    venue: Decimal
    minutes_missing: int


@dataclass(frozen=True)
class Run:
    start_ms: int
    last_ms: int
    count: int


@dataclass(frozen=True)
class SeriesResult:
    symbol: str
    timeframe: str
    requests: int
    venue_bars: int
    aggregated_bars: int
    complete: int
    incomplete: int
    compared: int
    equal: int
    mismatched: int
    mismatched_by_field: dict[str, int]
    mismatched_complete: int
    mismatched_incomplete: int
    incomplete_equal: int
    aggregator_only: int
    venue_only: int
    off_grid_venue: int
    mismatches: tuple[Mismatch, ...]
    aggregator_only_runs: tuple[Run, ...]
    venue_only_runs: tuple[Run, ...]


def _runs(opens: Sequence[int], width: int) -> tuple[Run, ...]:
    runs: list[Run] = []
    for opened in sorted(opens):
        if runs and opened == runs[-1].last_ms + width:
            previous = runs[-1]
            runs[-1] = Run(previous.start_ms, opened, previous.count + 1)
        else:
            runs.append(Run(opened, opened, 1))
    return tuple(runs)


def compare(
    symbol: str,
    timeframe: str,
    aggregated: Sequence[AggregatedBar],
    venue: Sequence[VenueBar],
    *,
    requests: int,
) -> SeriesResult:
    """Pair the two sides by open time and count what is equal, different and unpaired."""
    width = INTERVAL_MS[timeframe]
    ours = {epoch_ms(bar.open_time): bar for bar in aggregated}
    theirs = {bar.open_ms: bar for bar in venue}
    compared = equal = mismatched = mismatched_complete = mismatched_incomplete = 0
    incomplete_equal = 0
    by_field = dict.fromkeys(FIELDS, 0)
    rows: list[Mismatch] = []
    for opened in sorted(ours.keys() & theirs.keys()):
        ours_bar = ours[opened]
        venue_bar = theirs[opened]
        compared += 1
        differing = [name for name in FIELDS if getattr(ours_bar, name) != getattr(venue_bar, name)]
        if not differing:
            equal += 1
            if not ours_bar.complete:
                incomplete_equal += 1
            continue
        mismatched += 1
        if ours_bar.complete:
            mismatched_complete += 1
        else:
            mismatched_incomplete += 1
        for name in differing:
            by_field[name] += 1
            rows.append(
                Mismatch(
                    opened,
                    name,
                    getattr(ours_bar, name),
                    getattr(venue_bar, name),
                    ours_bar.minutes_missing,
                )
            )
    complete = sum(1 for bar in aggregated if bar.complete)
    return SeriesResult(
        symbol=symbol,
        timeframe=timeframe,
        requests=requests,
        venue_bars=len(venue),
        aggregated_bars=len(aggregated),
        complete=complete,
        incomplete=len(aggregated) - complete,
        compared=compared,
        equal=equal,
        mismatched=mismatched,
        mismatched_by_field=by_field,
        mismatched_complete=mismatched_complete,
        mismatched_incomplete=mismatched_incomplete,
        incomplete_equal=incomplete_equal,
        aggregator_only=len(ours.keys() - theirs.keys()),
        venue_only=len(theirs.keys() - ours.keys()),
        off_grid_venue=sum(1 for opened in theirs if opened % width),
        mismatches=tuple(rows),
        aggregator_only_runs=_runs(list(ours.keys() - theirs.keys()), width),
        venue_only_runs=_runs(list(theirs.keys() - ours.keys()), width),
    )


def _stamp(open_ms: int) -> str:
    moment = _EPOCH + timedelta(milliseconds=open_ms)
    return moment.strftime("%Y-%m-%dT%H:%M:%SZ")


def render(results: Sequence[SeriesResult], out: TextIO) -> None:
    out.write(
        f"N2 BAR VERIFICATION source={KLINES_URL} "
        f"window=[{_stamp(epoch_ms(WINDOW_START))}, {_stamp(epoch_ms(WINDOW_END))})\n"
    )
    for result in results:
        by_field = " ".join(f"{name}={count}" for name, count in result.mismatched_by_field.items())
        out.write(
            f"{result.symbol} {result.timeframe}: requests={result.requests} "
            f"venue={result.venue_bars} aggregated={result.aggregated_bars} "
            f"complete={result.complete} incomplete={result.incomplete} "
            f"compared={result.compared} equal={result.equal} mismatched={result.mismatched} "
            f"[{by_field}] mismatched_complete={result.mismatched_complete} "
            f"mismatched_incomplete={result.mismatched_incomplete} "
            f"incomplete_equal={result.incomplete_equal} "
            f"aggregator_only={result.aggregator_only} venue_only={result.venue_only} "
            f"off_grid_venue={result.off_grid_venue}\n"
        )
        for label, runs in (
            ("aggregator-only runs", result.aggregator_only_runs),
            ("venue-only runs", result.venue_only_runs),
        ):
            if runs:
                shown = "; ".join(
                    f"{_stamp(run.start_ms)}..{_stamp(run.last_ms)} x{run.count}"
                    for run in runs[:RUN_CAP]
                )
                more = f" (+{len(runs) - RUN_CAP} more)" if len(runs) > RUN_CAP else ""
                out.write(f"  {result.symbol} {result.timeframe} {label}: {shown}{more}\n")
    listed = [(result, row) for result in results for row in result.mismatches]
    out.write(f"MISMATCH LIST ({len(listed)} rows, first {MISMATCH_CAP} shown)\n")
    for result, row in listed[:MISMATCH_CAP]:
        out.write(
            f"  {result.symbol} {result.timeframe} {_stamp(row.open_ms)} {row.field} "
            f"aggregated={row.aggregated} venue={row.venue} minutes_missing={row.minutes_missing}\n"
        )


def refuse_out(out: Path, data_dir: Path) -> str | None:
    """Why ``out`` may not be used, or None."""
    resolved = out.resolve()
    if "logs" in (part.lower() for part in resolved.parts):
        return f"--out may not be under a logs directory: {resolved}"
    root = data_dir.resolve()
    if resolved == root or root in resolved.parents:
        return f"--out may not be inside the store: {resolved}"
    if resolved.exists() and any(resolved.iterdir()):
        return f"--out already holds files; this script runs once: {resolved}"
    return None


def run(
    store: HistoricalStore,
    fetcher: Fetcher,
    out_dir: Path,
    symbols: Sequence[str],
    *,
    pause: float,
    sleep: Callable[[float], None] = time.sleep,
    limit: int = PAGE_LIMIT,
) -> list[SeriesResult]:
    """Fetch, aggregate and compare every series; save each raw response and a digest list."""
    out_dir.mkdir(parents=True, exist_ok=True)
    digests: list[str] = []

    def save(name: str, body: bytes) -> None:
        (out_dir / name).write_bytes(body)
        digests.append(f"{hashlib.sha256(body).hexdigest()}  {name}")

    results: list[SeriesResult] = []
    try:
        for symbol in symbols:
            for timeframe in TIMEFRAMES:
                venue, requests = fetch_series(
                    fetcher,
                    symbol,
                    timeframe,
                    save=save,
                    pause=pause,
                    sleep=sleep,
                    limit=limit,
                )
                aggregated = list(
                    aggregate_from_store(store, symbol, timeframe, WINDOW_START, WINDOW_END)
                )
                results.append(compare(symbol, timeframe, aggregated, venue, requests=requests))
    finally:
        (out_dir / "responses.sha256").write_text("\n".join(digests) + "\n", encoding="ascii")
    return results


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Verify aggregated 4h and 1d bars against the venue."
    )
    parser.add_argument("--out", required=True, type=Path, help="directory for the raw responses")
    parser.add_argument("--data-dir", type=Path, default=Path("data/historical"))
    parser.add_argument("--symbols", nargs="+", default=list(DEFAULT_SYMBOLS))
    parser.add_argument("--pause", type=float, default=0.3, help="seconds between requests")
    return parser


def main(
    argv: Sequence[str] | None = None,
    *,
    fetcher: Fetcher = fetch_url,
    out: TextIO | None = None,
) -> int:
    args = _build_parser().parse_args(argv)
    stream = sys.stdout if out is None else out
    reason = refuse_out(args.out, args.data_dir)
    if reason is not None:
        stream.write(f"REFUSED: {reason}\n")
        return EXIT_REFUSED
    try:
        results = run(
            HistoricalStore(args.data_dir), fetcher, args.out, args.symbols, pause=args.pause
        )
    except (VerifyError, AggregationError, HistoricalDataError, OSError) as exc:
        stream.write(f"ERROR: {type(exc).__name__}: {exc}\n")
        return EXIT_ERROR
    render(results, stream)
    return 0


if __name__ == "__main__":
    sys.exit(main())
