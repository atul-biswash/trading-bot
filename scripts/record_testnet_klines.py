#!/usr/bin/env python
"""Record Binance Spot Testnet 1m and 5m klines into a store of their own (S4, R-AN).

Usage:
    python scripts/record_testnet_klines.py                      # extend the store
    python scripts/record_testnet_klines.py --verify-only        # check it; no network
    python scripts/record_testnet_klines.py --root data/historical_testnet \
        --symbols BTCUSDT ETHUSDT --intervals 1m 5m

**KEYLESS AND READ-ONLY, by construction.** Every request is a GET to
``https://testnet.binance.vision/api/v3/`` (``/time`` and ``/klines``); :func:`fetch_url` refuses
any other URL. No key is read or sent, ``.env`` is not opened, no ``Settings`` is built and nothing
from ``trading_bot.config`` or ``trading_bot.exchange`` is imported, so the script touches no account.
That is why it may run from a clone that has no ``.env`` (the owner's R-AW).

**WHAT IT DOES AND REFUSES** is :mod:`trading_bot.data.kline_recorder`'s: closed bars only, resumes
from the last stored bar, writes the store through the historical store's own writer, reports a gap and
never fills it, and, before any series is extended, fetches the last stored bar of every series again and
REFUSES, writing nothing, if the venue no longer has it or it differs (a reset or a rewrite). A reset is
the operator's to resolve: retire the store and start a new one, because appending after a reset would
join two price histories into one series.

**EXIT STATUS** is the contract with the scheduler, which records it as ``LastTaskResult``:

====  ======================================================================================
  0   the store was extended, or already current; or, with ``--verify-only``, it verifies
  1   a request failed or its answer was malformed (transient: the next run tries again)
  2   the venue's history was discarded or rewritten: NOTHING was written
  3   a bar the importer has no class for, or a page that repeated: nothing was written
  4   what is stored does not verify, so it was not extended
  5   another recorder holds ``<root>/RECORDER.lock``
 64   a usage error (a bad symbol, interval or flag)
====  ======================================================================================

**ONE INSTANCE AT A TIME**, by an OS lock on ``<root>/RECORDER.lock`` (the bot's own lock mechanism),
released by the kernel if the process dies. The scheduler definition ``scripts/recorder_task.xml``
also says ``IgnoreNew``.

**THE NETWORK IS INJECTED** into :func:`run` as a ``Fetcher``; only :func:`fetch_url` opens a socket,
retrying a transport fault or a 5xx answer twice (1 s, 2 s) and nothing else. A 429 or 418 is not
retried: the weight of one run is about 16 against a limit of 6000 a minute (M5m-224), so a rate
limit means something is wrong and the next scheduled run is the retry.
"""

from __future__ import annotations

import argparse
import importlib.metadata
import json
import os
import sys
import time
import urllib.error
import urllib.request
from collections.abc import Callable, Sequence
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Final, NoReturn, Protocol, TextIO

from trading_bot.data.kline_recorder import (
    TESTNET_BASE,
    BadKlineError,
    Fetcher,
    RecorderFetchError,
    RecorderStoreError,
    SeriesReport,
    VenueResetError,
    record_all,
    source_url,
    verify_store,
)
from trading_bot.utils.helpers import utc_now
from trading_bot.utils.instance_lock import InstanceLockedError, acquire

EXIT_OK: Final = 0
EXIT_FETCH: Final = 1
EXIT_RESET: Final = 2
EXIT_BAD_KLINE: Final = 3
EXIT_STORE: Final = 4
EXIT_LOCKED: Final = 5
EXIT_USAGE: Final = 64

DEFAULT_ROOT: Final = "data/historical_testnet"
DEFAULT_SYMBOLS: Final = ("BTCUSDT", "ETHUSDT")
DEFAULT_INTERVALS: Final = ("1m", "5m")
LOCK_NAME: Final = "RECORDER.lock"
_ALLOWED_PREFIX: Final = TESTNET_BASE + "/api/v3/"
_TIMEOUT_S: Final = 20.0
_MAX_BYTES: Final = 5_000_000
_EPOCH: Final = datetime(1970, 1, 1, tzinfo=timezone.utc)


class TransientFetchError(RecorderFetchError):
    """A transport fault or a 5xx answer: worth trying again."""


class _Response(Protocol):
    def read(self, size: int = ..., /) -> bytes: ...

    def __enter__(self) -> _Response: ...

    def __exit__(self, *exc: object) -> object: ...


Opener = Callable[[urllib.request.Request, float], _Response]


def _urlopen(request: urllib.request.Request, timeout: float) -> _Response:
    response: _Response = urllib.request.urlopen(request, timeout=timeout)
    return response


def fetch_url(url: str, *, opener: Opener = _urlopen) -> bytes:
    """GET ``url`` and return its body. Only the Testnet ``/api/v3/`` endpoints are allowed."""
    if not url.startswith(_ALLOWED_PREFIX):
        raise RecorderFetchError(f"refusing a URL outside {_ALLOWED_PREFIX}: {url}")
    request = urllib.request.Request(url, headers={"User-Agent": "trading-bot-recorder/1"})
    try:
        with opener(request, _TIMEOUT_S) as response:
            body = response.read(_MAX_BYTES + 1)
    except urllib.error.HTTPError as exc:
        if exc.code >= 500:
            raise TransientFetchError(f"{url}: HTTP {exc.code}") from exc
        raise RecorderFetchError(f"{url}: HTTP {exc.code}") from exc
    except (urllib.error.URLError, TimeoutError, ConnectionError) as exc:
        raise TransientFetchError(f"{url}: {exc}") from exc
    if len(body) > _MAX_BYTES:
        raise RecorderFetchError(f"{url}: more than {_MAX_BYTES} bytes")
    return body


def with_retries(
    fetcher: Fetcher, *, attempts: int = 3, sleep: Callable[[float], None] = time.sleep
) -> Fetcher:
    """Retry a fetcher on a ``TransientFetchError``, waiting 1 s, 2 s, ... between tries."""

    def fetch(url: str) -> bytes:
        for attempt in range(1, attempts + 1):
            try:
                return fetcher(url)
            except TransientFetchError:
                if attempt == attempts:
                    raise
                sleep(float(attempt))
        raise AssertionError("unreachable: attempts must be at least 1")

    return fetch


class _Parser(argparse.ArgumentParser):
    """argparse exits 2 on a usage error, which here means a venue reset; use 64 instead."""

    def error(self, message: str) -> NoReturn:
        self.print_usage(sys.stderr)
        self.exit(EXIT_USAGE, f"{self.prog}: error: {message}\n")


def _build_parser() -> argparse.ArgumentParser:
    parser = _Parser(description="Record Binance Spot Testnet klines (keyless, read-only).")
    parser.add_argument("--root", default=DEFAULT_ROOT, help="the Testnet store's root")
    parser.add_argument("--symbols", nargs="+", default=list(DEFAULT_SYMBOLS), metavar="SYMBOL")
    parser.add_argument(
        "--intervals", nargs="+", default=list(DEFAULT_INTERVALS), metavar="INTERVAL"
    )
    parser.add_argument(
        "--verify-only",
        action="store_true",
        help="check what is stored (every row re-validated) and make no request",
    )
    return parser


def _installed_commit() -> str:
    """The commit pip recorded when it built this install (PEP 610), or ``unknown``."""
    try:
        text = importlib.metadata.distribution("binance-trading-bot").read_text("direct_url.json")
        if text:
            commit = json.loads(text).get("vcs_info", {}).get("commit_id")
            if isinstance(commit, str):
                return commit
    except (importlib.metadata.PackageNotFoundError, ValueError):
        pass
    return "unknown"


def _stamp(open_ms: int | None) -> str:
    if open_ms is None:
        return "-"
    return (_EPOCH + timedelta(milliseconds=open_ms)).strftime("%Y-%m-%dT%H:%MZ")


def _line(report: SeriesReport) -> str:
    gaps = f", {len(report.gaps)} gap(s) ({sum(g.missing for g in report.gaps)} bars)"
    return (
        f"{report.symbol} {report.interval}: +{report.rows_added} bar(s) "
        f"{_stamp(report.first_open_ms)}..{_stamp(report.last_open_ms)}, "
        f"stored {report.stored_after}, {report.pages} page(s), "
        f"{report.forming_skipped} forming skipped"
        f"{gaps if report.gaps else ''}"
        f"{f', {report.quarantined} quarantined' if report.quarantined else ''}"
        f"{f', {report.registered} registered' if report.registered else ''}"
    )


def run(
    argv: Sequence[str],
    *,
    out: TextIO | None = None,
    fetcher: Fetcher | None = None,
    clock: Callable[[], datetime] = utc_now,
) -> int:
    """Run the recorder and return its exit status. ``out`` is resolved at call time."""
    stream = sys.stdout if out is None else out
    args = _build_parser().parse_args(list(argv))
    series = [(symbol, interval) for symbol in args.symbols for interval in args.intervals]
    for symbol, interval in series:
        try:
            source_url(symbol, interval)
        except ValueError as exc:
            print(f"usage error: {exc}", file=stream)
            return EXIT_USAGE
    root = Path(args.root)

    if args.verify_only:
        try:
            checks = verify_store(root, series)
        except ValueError as exc:
            print(f"usage error: {exc}", file=stream)
            return EXIT_USAGE
        bad = 0
        for check in checks:
            gaps = sum(g.missing for g in check.gaps)
            print(
                f"{check.symbol} {check.interval}: {check.bars} bar(s) in {len(check.months)} "
                f"month(s) {_stamp(check.first_open_ms)}..{_stamp(check.last_open_ms)}, "
                f"{len(check.gaps)} gap(s) ({gaps} bars), {len(check.problems)} problem(s)",
                file=stream,
            )
            for problem in check.problems:
                print(
                    f"  PROBLEM {problem.kind} {problem.month or ''} {problem.detail}", file=stream
                )
            bad += len(check.problems)
        return EXIT_STORE if bad else EXIT_OK

    meta = {
        "recorder": "record_testnet_klines/1",
        "commit": _installed_commit(),
        "pid": str(os.getpid()),
    }
    fetch = fetcher if fetcher is not None else with_retries(fetch_url)
    try:
        with acquire(root / LOCK_NAME):
            reports = record_all(root, series, fetcher=fetch, clock=clock, meta=meta)
    except InstanceLockedError:
        print(f"another recorder holds {root / LOCK_NAME}; nothing was done", file=stream)
        return EXIT_LOCKED
    except VenueResetError as exc:
        print(f"REFUSED, NOTHING WRITTEN: {exc}", file=stream)
        return EXIT_RESET
    except BadKlineError as exc:
        print(f"REFUSED, NOTHING WRITTEN: {exc}", file=stream)
        return EXIT_BAD_KLINE
    except RecorderStoreError as exc:
        print(f"REFUSED: {exc}", file=stream)
        return EXIT_STORE
    except (RecorderFetchError, OSError, ValueError) as exc:
        print(f"FAILED: {type(exc).__name__}: {exc}", file=stream)
        return EXIT_FETCH
    for report in reports:
        print(_line(report), file=stream)
    return EXIT_OK


def main() -> None:
    sys.exit(run(sys.argv[1:]))


if __name__ == "__main__":
    main()
