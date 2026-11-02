#!/usr/bin/env python
"""Check the archive 4h and 1d series, the traded-minute aggregation and the volume gap (R-DV).

Usage:
    python scripts/n2_archive_check.py --responses <the --out directory of n2_verify_bars.py>

**IT MAKES NO REQUEST AND HAS NO FETCHER.** The venue's bars are the raw responses that
``n2_verify_bars.py`` saved. Each is checked against ``responses.sha256`` before a byte of it is
used, a file that does not match, a file the list does not name and a listed file that is missing
each refuse the run, and the SHA-256 of the list itself is printed so the evidence can be named.

**IT READS ONE FIXED WINDOW, ``[2017-08-17, 2024-01-01)``, AND NOTHING AT OR AFTER THE END.** The
window is the one ``n2_verify_bars.py`` fixes. The store is read through ``HistoricalStore.candles``
and ``aggregate_traded_from_store``, which open no month file beginning at or after the end.

It reports three things, per symbol and timeframe, as counts:

* **A.** The store's archive series (the decision bars of R-DV) against the saved API responses in
  open, high, low, close and base volume: bars each side, compared, equal, mismatched by field, the
  bars only one side has, and up to 50 mismatch rows (the only place a price is printed).
* **B.** The traded-minute aggregation of the 1m series against the archive series, on open, high,
  low and close (R-DV's consistency check): compared, complete and incomplete, those with no traded
  minute (nothing to check), consistent and failed (by field, and whether complete), and the failing
  buckets listed with their time, fields and minute counts and no price.
* **C.** The volume gap: for the complete buckets, the archive series' volume against the sum of the
  1m rows' volume, in bands of the relative difference (0, up to 0.01%, up to 0.1%, up to 1%, over
  1%), the buckets where the archive's is smaller, and the median and maximum relative difference
  among those that differ. No price.

It computes no return, P&L, equity or metric.
"""

from __future__ import annotations

import argparse
import hashlib
import re
import statistics
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Final, TextIO

from n2_verify_bars import (
    DEFAULT_SYMBOLS,
    FIELDS,
    MISMATCH_CAP,
    RUN_CAP,
    TIMEFRAMES,
    WINDOW_END,
    WINDOW_START,
    Run,
    VenueBar,
    VerifyError,
    _runs,
    _stamp,
    epoch_ms,
    parse_page,
)

from trading_bot.data.aggregation import (
    AggregationError,
    TradedBar,
    aggregate_traded_from_store,
)
from trading_bot.data.historical import INTERVAL_MS, HistoricalDataError, HistoricalStore

DIGEST_LIST: Final = "responses.sha256"
EXIT_ERROR: Final = 3
PRICE_FIELDS: Final = ("open", "high", "low", "close")
BAND_EDGES: Final = (Decimal("0.0001"), Decimal("0.001"), Decimal("0.01"))

_RESPONSE: Final = re.compile(r"(?P<symbol>[A-Z]+)-(?P<timeframe>1d|4h)-(?P<page>\d{3})\.json")
_LINE: Final = re.compile(r"(?P<digest>[0-9a-f]{64})  (?P<name>\S+)")


class CheckError(Exception):
    """The saved evidence cannot be trusted: stop and say so."""


def load_api(responses: Path) -> tuple[dict[tuple[str, str], list[VenueBar]], str, int]:
    """The venue's bars per series from the saved responses, the digest of the list and the file count.

    Every listed file must exist and match its SHA-256, no other ``.json`` file may sit beside
    them, and the open times of a series must increase and stay inside the window.
    """
    listing = responses / DIGEST_LIST
    if not listing.is_file():
        raise CheckError(f"{listing} is missing")
    raw = listing.read_bytes()
    listed: dict[str, str] = {}
    for line in raw.decode("ascii").splitlines():
        found = _LINE.fullmatch(line)
        if found is None:
            raise CheckError(f"a line of {DIGEST_LIST} is not '<sha256>  <name>': {line!r}")
        listed[found.group("name")] = found.group("digest")
    present = {path.name for path in responses.glob("*.json")}
    if present != set(listed):
        raise CheckError(
            f"the response files and {DIGEST_LIST} disagree: {sorted(present ^ set(listed))}"
        )
    pages: dict[tuple[str, str], list[tuple[int, bytes]]] = {}
    for name, digest in sorted(listed.items()):
        body = (responses / name).read_bytes()
        if hashlib.sha256(body).hexdigest() != digest:
            raise CheckError(f"{name} does not match its SHA-256 in {DIGEST_LIST}")
        named = _RESPONSE.fullmatch(name)
        if named is None:
            raise CheckError(f"not a response name: {name}")
        key = (named.group("symbol"), named.group("timeframe"))
        pages.setdefault(key, []).append((int(named.group("page")), body))
    end_ms = epoch_ms(WINDOW_END)
    series: dict[tuple[str, str], list[VenueBar]] = {}
    for key, bodies in pages.items():
        bars: list[VenueBar] = []
        for _page, body in sorted(bodies):
            for bar in parse_page(body):
                if bar.open_ms >= end_ms or (bars and bar.open_ms <= bars[-1].open_ms):
                    raise CheckError(f"{key}: a bar is at or after the window end or out of order")
                bars.append(bar)
        series[key] = bars
    return series, hashlib.sha256(raw).hexdigest(), len(listed)


def archive_series(store: HistoricalStore, symbol: str, timeframe: str) -> list[VenueBar]:
    """The store's archive series for the window, as the same value type the API's bars are."""
    return [
        VenueBar(
            epoch_ms(candle.open_time),
            candle.open,
            candle.high,
            candle.low,
            candle.close,
            candle.volume,
        )
        for candle in store.candles(symbol, timeframe, WINDOW_START, WINDOW_END)
    ]


@dataclass(frozen=True)
class FieldDifference:
    open_ms: int
    field: str
    archive: Decimal
    api: Decimal


@dataclass(frozen=True)
class ArchiveResult:
    symbol: str
    timeframe: str
    archive_bars: int
    api_bars: int
    compared: int
    equal: int
    mismatched: int
    mismatched_by_field: dict[str, int]
    archive_only: int
    api_only: int
    archive_only_runs: tuple[Run, ...]
    api_only_runs: tuple[Run, ...]
    differences: tuple[FieldDifference, ...]


def compare_archive(
    symbol: str, timeframe: str, archive: Sequence[VenueBar], api: Sequence[VenueBar]
) -> ArchiveResult:
    width = INTERVAL_MS[timeframe]
    ours = {bar.open_ms: bar for bar in archive}
    theirs = {bar.open_ms: bar for bar in api}
    by_field = dict.fromkeys(FIELDS, 0)
    rows: list[FieldDifference] = []
    equal = mismatched = 0
    for opened in sorted(ours.keys() & theirs.keys()):
        differing = [
            name for name in FIELDS if getattr(ours[opened], name) != getattr(theirs[opened], name)
        ]
        if not differing:
            equal += 1
            continue
        mismatched += 1
        for name in differing:
            by_field[name] += 1
            rows.append(
                FieldDifference(
                    opened, name, getattr(ours[opened], name), getattr(theirs[opened], name)
                )
            )
    return ArchiveResult(
        symbol=symbol,
        timeframe=timeframe,
        archive_bars=len(archive),
        api_bars=len(api),
        compared=equal + mismatched,
        equal=equal,
        mismatched=mismatched,
        mismatched_by_field=by_field,
        archive_only=len(ours.keys() - theirs.keys()),
        api_only=len(theirs.keys() - ours.keys()),
        archive_only_runs=_runs(list(ours.keys() - theirs.keys()), width),
        api_only_runs=_runs(list(theirs.keys() - ours.keys()), width),
        differences=tuple(rows),
    )


@dataclass(frozen=True)
class Failure:
    open_ms: int
    fields: tuple[str, ...]
    complete: bool
    traded_minutes: int
    minutes_missing: int


@dataclass(frozen=True)
class ConsistencyResult:
    symbol: str
    timeframe: str
    archive_bars: int
    aggregated_bars: int
    compared: int
    complete: int
    incomplete: int
    no_trade: int
    consistent: int
    failed: int
    failed_by_field: dict[str, int]
    failed_complete: int
    failed_incomplete: int
    aggregator_only: int
    archive_only: int
    failures: tuple[Failure, ...]


def check_consistency(
    symbol: str, timeframe: str, aggregated: Sequence[TradedBar], archive: Sequence[VenueBar]
) -> ConsistencyResult:
    ours = {epoch_ms(bar.open_time): bar for bar in aggregated}
    theirs = {bar.open_ms: bar for bar in archive}
    by_field = dict.fromkeys(PRICE_FIELDS, 0)
    failures: list[Failure] = []
    compared = complete = no_trade = consistent = failed_complete = failed_incomplete = 0
    for opened in sorted(ours.keys() & theirs.keys()):
        bar = ours[opened]
        venue = theirs[opened]
        compared += 1
        complete += int(bar.complete)
        if not bar.has_trade:
            no_trade += 1
            continue
        differing = tuple(
            name for name in PRICE_FIELDS if getattr(bar, name) != getattr(venue, name)
        )
        if not differing:
            consistent += 1
            continue
        if bar.complete:
            failed_complete += 1
        else:
            failed_incomplete += 1
        for name in differing:
            by_field[name] += 1
        failures.append(
            Failure(opened, differing, bar.complete, bar.traded_minutes, bar.minutes_missing)
        )
    return ConsistencyResult(
        symbol=symbol,
        timeframe=timeframe,
        archive_bars=len(archive),
        aggregated_bars=len(aggregated),
        compared=compared,
        complete=complete,
        incomplete=compared - complete,
        no_trade=no_trade,
        consistent=consistent,
        failed=failed_complete + failed_incomplete,
        failed_by_field=by_field,
        failed_complete=failed_complete,
        failed_incomplete=failed_incomplete,
        aggregator_only=len(ours.keys() - theirs.keys()),
        archive_only=len(theirs.keys() - ours.keys()),
        failures=tuple(failures),
    )


@dataclass(frozen=True)
class VolumeResult:
    symbol: str
    timeframe: str
    complete_paired: int
    equal: int
    archive_larger_bands: tuple[int, int, int, int]
    archive_smaller: int
    median_pct: Decimal | None
    max_pct: Decimal | None


def volume_gap(
    symbol: str, timeframe: str, aggregated: Sequence[TradedBar], archive: Sequence[VenueBar]
) -> VolumeResult:
    theirs = {bar.open_ms: bar for bar in archive}
    equal = smaller = paired = 0
    bands = [0, 0, 0, 0]
    relative: list[Decimal] = []
    for bar in aggregated:
        venue = theirs.get(epoch_ms(bar.open_time))
        if venue is None or not bar.complete:
            continue
        paired += 1
        gap = venue.volume - bar.volume
        if gap == 0:
            equal += 1
            continue
        if gap < 0:
            smaller += 1
        size = abs(gap)
        reference = abs(venue.volume)
        relative.append(size / reference if reference else Decimal(1))
        band = next((i for i, edge in enumerate(BAND_EDGES) if size <= reference * edge), 3)
        if gap > 0:
            bands[band] += 1
    return VolumeResult(
        symbol=symbol,
        timeframe=timeframe,
        complete_paired=paired,
        equal=equal,
        archive_larger_bands=(bands[0], bands[1], bands[2], bands[3]),
        archive_smaller=smaller,
        median_pct=statistics.median(relative) * 100 if relative else None,
        max_pct=max(relative) * 100 if relative else None,
    )


@dataclass(frozen=True)
class Report:
    list_digest: str
    files: int
    archive: tuple[ArchiveResult, ...]
    consistency: tuple[ConsistencyResult, ...]
    volume: tuple[VolumeResult, ...]


def run_check(store: HistoricalStore, responses: Path, symbols: Sequence[str]) -> Report:
    api, list_digest, files = load_api(responses)
    a_results: list[ArchiveResult] = []
    b_results: list[ConsistencyResult] = []
    c_results: list[VolumeResult] = []
    for symbol in symbols:
        for timeframe in TIMEFRAMES:
            if (symbol, timeframe) not in api:
                raise CheckError(f"no saved response for {symbol} {timeframe}")
            archive = archive_series(store, symbol, timeframe)
            a_results.append(compare_archive(symbol, timeframe, archive, api[(symbol, timeframe)]))
            traded = list(
                aggregate_traded_from_store(store, symbol, timeframe, WINDOW_START, WINDOW_END)
            )
            b_results.append(check_consistency(symbol, timeframe, traded, archive))
            c_results.append(volume_gap(symbol, timeframe, traded, archive))
    return Report(list_digest, files, tuple(a_results), tuple(b_results), tuple(c_results))


def _runs_line(label: str, runs: Sequence[Run]) -> str:
    shown = "; ".join(
        f"{_stamp(run.start_ms)}..{_stamp(run.last_ms)} x{run.count}" for run in runs[:RUN_CAP]
    )
    more = f" (+{len(runs) - RUN_CAP} more)" if len(runs) > RUN_CAP else ""
    return f"  {label}: {shown}{more}\n"


def _pct(value: Decimal | None) -> str:
    return "n/a" if value is None else f"{value:.6f}%"


def render(report: Report, out: TextIO) -> None:
    out.write(
        f"N2 ARCHIVE CHECK window=[{_stamp(epoch_ms(WINDOW_START))}, {_stamp(epoch_ms(WINDOW_END))}) "
        f"responses={report.files} {DIGEST_LIST} sha256={report.list_digest}\n"
    )
    out.write("A. ARCHIVE SERIES AGAINST THE SAVED API RESPONSES\n")
    for a in report.archive:
        by_field = " ".join(f"{name}={count}" for name, count in a.mismatched_by_field.items())
        out.write(
            f"{a.symbol} {a.timeframe}: archive={a.archive_bars} api={a.api_bars} "
            f"compared={a.compared} equal={a.equal} mismatched={a.mismatched} [{by_field}] "
            f"archive_only={a.archive_only} api_only={a.api_only}\n"
        )
        if a.archive_only_runs:
            out.write(
                _runs_line(f"{a.symbol} {a.timeframe} archive-only runs", a.archive_only_runs)
            )
        if a.api_only_runs:
            out.write(_runs_line(f"{a.symbol} {a.timeframe} api-only runs", a.api_only_runs))
    listed = [(a, row) for a in report.archive for row in a.differences]
    out.write(f"A MISMATCH LIST ({len(listed)} rows, first {MISMATCH_CAP} shown)\n")
    for a, row in listed[:MISMATCH_CAP]:
        out.write(
            f"  {a.symbol} {a.timeframe} {_stamp(row.open_ms)} {row.field} "
            f"archive={row.archive} api={row.api}\n"
        )
    out.write("B. TRADED-MINUTE AGGREGATION AGAINST THE ARCHIVE SERIES (R-DV)\n")
    for b in report.consistency:
        by_field = " ".join(f"{name}={count}" for name, count in b.failed_by_field.items())
        out.write(
            f"{b.symbol} {b.timeframe}: archive={b.archive_bars} aggregated={b.aggregated_bars} "
            f"compared={b.compared} complete={b.complete} incomplete={b.incomplete} "
            f"no_trade={b.no_trade} consistent={b.consistent} failed={b.failed} [{by_field}] "
            f"failed_complete={b.failed_complete} failed_incomplete={b.failed_incomplete} "
            f"aggregator_only={b.aggregator_only} archive_only={b.archive_only}\n"
        )
    failing = [(b, f) for b in report.consistency for f in b.failures]
    out.write(f"B FAILING BUCKETS ({len(failing)}, first {MISMATCH_CAP} shown)\n")
    for b, f in failing[:MISMATCH_CAP]:
        out.write(
            f"  {b.symbol} {b.timeframe} {_stamp(f.open_ms)} fields={','.join(f.fields)} "
            f"complete={'yes' if f.complete else 'no'} traded_minutes={f.traded_minutes} "
            f"minutes_missing={f.minutes_missing}\n"
        )
    out.write("C. VOLUME GAP, COMPLETE BUCKETS (archive volume against the sum of the 1m rows)\n")
    for c in report.volume:
        z, p1, p2, p3 = c.archive_larger_bands
        out.write(
            f"{c.symbol} {c.timeframe}: complete_paired={c.complete_paired} equal={c.equal} "
            f"larger_up_to_0.01%={z} larger_up_to_0.1%={p1} larger_up_to_1%={p2} "
            f"larger_over_1%={p3} archive_smaller={c.archive_smaller} "
            f"median={_pct(c.median_pct)} max={_pct(c.max_pct)}\n"
        )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Check the archive series, the consistency mode and the volume gap."
    )
    parser.add_argument("--responses", required=True, type=Path, help="n2_verify_bars.py's --out")
    parser.add_argument("--data-dir", type=Path, default=Path("data/historical"))
    parser.add_argument("--symbols", nargs="+", default=list(DEFAULT_SYMBOLS))
    return parser


def main(argv: Sequence[str] | None = None, *, out: TextIO | None = None) -> int:
    args = _build_parser().parse_args(argv)
    stream = sys.stdout if out is None else out
    try:
        report = run_check(HistoricalStore(args.data_dir), args.responses, args.symbols)
    except (CheckError, VerifyError, AggregationError, HistoricalDataError, OSError) as exc:
        stream.write(f"ERROR: {type(exc).__name__}: {exc}\n")
        return EXIT_ERROR
    render(report, stream)
    return 0


if __name__ == "__main__":
    sys.exit(main())
