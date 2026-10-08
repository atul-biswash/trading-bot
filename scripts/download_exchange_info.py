#!/usr/bin/env python
"""Fetch ``exchangeInfo`` once per symbol and environment, and store the raw response.

Usage:
    python scripts/download_exchange_info.py --symbols BTCUSDT ETHUSDT \
        --environments mainnet testnet

**ONE KEYLESS GET PER SYMBOL AND ENVIRONMENT** (the project owner's R-Z), to
``/api/v3/exchangeInfo?symbol=<SYMBOL>`` on ``api.binance.com`` (mainnet) and
``testnet.binance.vision`` (Testnet). No key is read or sent, and there is no retry: a
request that fails is reported and left for the operator, because the ruling authorises one
GET and not a loop. The response is stored byte for byte with its SHA-256 by
``trading_bot.backtesting.exchange_info``, which refuses a response that is not a single
symbol entry the live mapper can read, and **never overwrites a snapshot already stored**:
the response carries ``serverTime``, so a second GET would differ from the first and change
the filters under every earlier backtest. A symbol already stored on an environment is
reported as such and not requested.

A backtest loads filters only from the stored files. The digest printed here is what
``docs/RUN_LEDGER.md`` records.

**THE NETWORK IS INJECTED.** Every request goes through a ``Fetcher``, ``url -> bytes``,
and the only fetcher that opens a socket is ``fetch_url``, which refuses a URL outside the
two hosts above and caps a response's size.
"""

from __future__ import annotations

import argparse
import sys
import urllib.error
import urllib.request
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Final, Protocol, TextIO

from trading_bot.backtesting.exchange_info import (
    ENVIRONMENTS,
    SnapshotError,
    snapshot_file,
    store_snapshot,
)

Fetcher = Callable[[str], bytes]

BASES: Final = {
    "mainnet": "https://api.binance.com",
    "testnet": "https://testnet.binance.vision",
}
_PATH: Final = "/api/v3/exchangeInfo?symbol="
_ALLOWED_PREFIXES: Final = tuple(base + _PATH for base in BASES.values())
DEFAULT_DATA_DIR: Final = "data/historical"
DEFAULT_SYMBOLS: Final = ("BTCUSDT", "ETHUSDT")

_MAX_RESPONSE_BYTES: Final = 5_000_000
_TIMEOUT_S: Final = 30.0


class DownloadError(Exception):
    """A request failed."""


class _Response(Protocol):
    def read(self, size: int = ..., /) -> bytes: ...

    def __enter__(self) -> _Response: ...

    def __exit__(self, *exc: object) -> object: ...


Opener = Callable[[urllib.request.Request, float], _Response]


def _urlopen(request: urllib.request.Request, timeout: float) -> _Response:
    response: _Response = urllib.request.urlopen(request, timeout=timeout)
    return response


def exchange_info_url(environment: str, symbol: str) -> str:
    """The single-symbol ``exchangeInfo`` URL of ``environment``."""
    return BASES[environment] + _PATH + symbol


def fetch_url(url: str, *, opener: Opener = _urlopen) -> bytes:
    """GET ``url`` once, with no key, and return its body. Only this script's two hosts are allowed."""
    if not url.startswith(_ALLOWED_PREFIXES):
        raise DownloadError(f"refusing a URL outside the two exchangeInfo endpoints: {url}")
    request = urllib.request.Request(url, headers={"User-Agent": "trading-bot-exchange-info/1"})
    try:
        with opener(request, _TIMEOUT_S) as response:
            body = response.read(_MAX_RESPONSE_BYTES + 1)
    except urllib.error.HTTPError as exc:
        raise DownloadError(f"{url}: HTTP {exc.code}") from exc
    except (urllib.error.URLError, TimeoutError, ConnectionError) as exc:
        raise DownloadError(f"{url}: {exc}") from exc
    if len(body) > _MAX_RESPONSE_BYTES:
        raise DownloadError(f"{url}: more than {_MAX_RESPONSE_BYTES} bytes")
    return body


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0] if __doc__ else None)
    parser.add_argument("--symbols", nargs="+", default=list(DEFAULT_SYMBOLS))
    parser.add_argument("--environments", nargs="+", default=list(ENVIRONMENTS))
    parser.add_argument("--data-dir", default=DEFAULT_DATA_DIR, help="backtesting.data_dir")
    parser.add_argument(
        "--dry-run", action="store_true", help="list what would be fetched; fetch nothing"
    )
    return parser


def run(
    argv: Sequence[str],
    *,
    fetcher: Fetcher | None = None,
    out: TextIO = sys.stdout,
) -> int:
    """Store what the arguments name. 0 if every snapshot is stored, 1 if any failed, 2 if refused."""
    args = _parser().parse_args(argv)
    unknown = [name for name in args.environments if name not in ENVIRONMENTS]
    if unknown:
        print(f"refused: not environments: {unknown}; expected {list(ENVIRONMENTS)}", file=out)
        return 2
    root = Path(args.data_dir)
    fetch: Fetcher = fetcher if fetcher is not None else fetch_url
    failed = 0
    for environment in args.environments:
        for symbol in args.symbols:
            try:
                target = snapshot_file(root, environment, symbol)
            except SnapshotError as exc:
                print(f"refused: {exc}", file=out)
                return 2
            if target.exists():
                print(f"exists {environment} {symbol}: {target}; not requested", file=out)
                continue
            url = exchange_info_url(environment, symbol)
            if args.dry_run:
                print(f"would fetch {environment} {symbol}: {url}", file=out)
                continue
            try:
                body = fetch(url)
                digest = store_snapshot(root, environment, symbol, body)
            except (DownloadError, SnapshotError, OSError) as exc:
                failed += 1
                print(f"FAILED {environment} {symbol}: {type(exc).__name__}: {exc}", file=out)
                continue
            print(f"stored {environment} {symbol}: {len(body)} bytes sha256 {digest}", file=out)
    return 1 if failed else 0


def main() -> None:
    sys.exit(run(sys.argv[1:]))


if __name__ == "__main__":
    main()
