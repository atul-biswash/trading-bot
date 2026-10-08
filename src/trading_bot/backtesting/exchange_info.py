"""Stored ``exchangeInfo`` snapshots: the only source of exchange filters for a backtest.

A backtest sizes and rounds with the same :class:`~trading_bot.core.models.SymbolInfo` the
live bot does, and the live bot gets it from the venue at boot. A backtest must not: a run
has to be reproducible from files, and a venue answer changes. The project owner's R-Z:
*"One keyless exchangeInfo GET per symbol, on mainnet and on Testnet, is authorised. The raw
response is stored with its SHA-256, and backtests load filters only from the stored file."*

**Layout.** ``<data_dir>/_exchange_info/<environment>/<SYMBOL>.json`` holds the response
exactly as the venue sent it, and ``<SYMBOL>.json.sha256`` beside it holds its SHA-256 in
the ``<hex>  <name>`` form the archive's ``.CHECKSUM`` files use. ``<environment>`` is
``mainnet`` or ``testnet``: S5 to S7 read the first and S4, which replays what the bot did
on Testnet, reads the second. The directory is beside the series directories and not
inside one, like ``_zips``, so the store's checks do not see it, and ``data/*`` is ignored
by git, so the record of what was stored is the digest in ``docs/RUN_LEDGER.md``.

**Parsing is the live mapper, unchanged.** :func:`load_snapshot` hands the symbol's entry to
:func:`trading_bot.exchange.models.to_symbol_info`, the function ``get_symbol_info`` uses,
so a filter the live bot reads is read the same way here and a malformed entry is refused
by the same code.

**A snapshot is never overwritten.** The response carries ``serverTime``, so two GETs of
the same symbol never produce the same bytes, and replacing a stored snapshot would change
the filters under every earlier run's feet while its recorded digest still named the old
file. :func:`store_snapshot` refuses a symbol it already holds; replacing one is a
deliberate act, deleting the two files, and a new ledger entry.

**What a snapshot is not.** It is today's filters. Applying them to years of history is an
approximation whose cost is UNMEASURED (``M5m-128``); nothing here knows what a filter was
on a past day.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final

from trading_bot.core.exceptions import ExchangeAPIError
from trading_bot.core.models import SymbolInfo
from trading_bot.exchange.models import to_symbol_info

__all__ = [
    "ENVIRONMENTS",
    "INFO_DIR_NAME",
    "Snapshot",
    "SnapshotError",
    "checksum_file",
    "load_snapshot",
    "snapshot_file",
    "store_snapshot",
]

#: Beside the series directories, never inside one.
INFO_DIR_NAME: Final = "_exchange_info"
#: The two venues R-Z authorises, by the name used in the path.
ENVIRONMENTS: Final = ("mainnet", "testnet")

_SYMBOL: Final = re.compile(r"[A-Z0-9]{5,20}")
_CHECKSUM_LINE: Final = re.compile(r"([0-9a-f]{64})  (\S+)\n?")


class SnapshotError(Exception):
    """A snapshot is missing, altered, malformed, or would overwrite one."""


@dataclass(frozen=True)
class Snapshot:
    """One stored response, verified and parsed.

    ``sha256`` is the digest of the stored bytes, which a run records so that the filters it
    used can be named. ``server_time_ms`` is the venue's ``serverTime`` in the response, or
    ``None`` if it carried none.
    """

    environment: str
    symbol: str
    sha256: str
    server_time_ms: int | None
    symbol_info: SymbolInfo
    path: Path


def _require(environment: str, symbol: str) -> None:
    if environment not in ENVIRONMENTS:
        raise SnapshotError(f"not an environment: {environment!r}; expected one of {ENVIRONMENTS}")
    if _SYMBOL.fullmatch(symbol) is None:
        raise SnapshotError(f"not a symbol: {symbol!r}")


def snapshot_file(root: Path, environment: str, symbol: str) -> Path:
    """Where one snapshot's raw response is stored."""
    _require(environment, symbol)
    return root / INFO_DIR_NAME / environment / f"{symbol}.json"


def checksum_file(root: Path, environment: str, symbol: str) -> Path:
    """Where one snapshot's SHA-256 is stored, beside the response."""
    path = snapshot_file(root, environment, symbol)
    return path.with_name(path.name + ".sha256")


def _write_atomic(path: Path, data: bytes) -> None:
    """Write through a temporary file and a rename, so a kill leaves the old file or the new."""
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


def _entry(raw: bytes, symbol: str) -> tuple[dict[str, Any], int | None]:
    """The one symbol entry of a single-symbol ``exchangeInfo`` response, and its server time."""
    try:
        document = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise SnapshotError(f"{symbol}: the response is not JSON ({exc})") from exc
    entries = document.get("symbols") if isinstance(document, dict) else None
    if not isinstance(entries, list) or len(entries) != 1 or not isinstance(entries[0], dict):
        raise SnapshotError(
            f"{symbol}: the response must hold exactly one entry under 'symbols', "
            "as a request for a single symbol answers"
        )
    entry: dict[str, Any] = entries[0]
    if entry.get("symbol") != symbol:
        raise SnapshotError(f"{symbol}: the response is for {entry.get('symbol')!r}")
    server_time = document.get("serverTime")
    return entry, server_time if isinstance(server_time, int) else None


def store_snapshot(root: Path, environment: str, symbol: str, raw: bytes) -> str:
    """Store ``raw`` as the snapshot of ``symbol`` on ``environment``; return its SHA-256.

    The response is checked before anything is written: it must be JSON holding exactly one
    symbol entry for ``symbol``, and the live mapper must be able to read it. Then the
    response is written, and its digest after it, so a kill between the two leaves a response
    with no digest, which :func:`load_snapshot` refuses and which a re-run does not silently
    adopt: :class:`SnapshotError` is raised for a snapshot that already exists in either
    file, and the leftover must be removed by hand.
    """
    path = snapshot_file(root, environment, symbol)
    sum_path = checksum_file(root, environment, symbol)
    if path.exists() or sum_path.exists():
        raise SnapshotError(
            f"{path} is already stored; a snapshot is never overwritten. To replace it, delete "
            "the response and its .sha256 and record the new digest in docs/RUN_LEDGER.md"
        )
    entry, _ = _entry(raw, symbol)
    try:
        to_symbol_info(entry)
    except ExchangeAPIError as exc:
        raise SnapshotError(f"{symbol}: the live mapper refuses the entry ({exc})") from exc
    digest = hashlib.sha256(raw).hexdigest()
    _write_atomic(path, raw)
    _write_atomic(sum_path, f"{digest}  {path.name}\n".encode("ascii"))
    return digest


def load_snapshot(root: Path, environment: str, symbol: str) -> Snapshot:
    """Read, verify and parse one stored snapshot.

    The digest file must exist and name this response, and the response's bytes must hash
    to it, before a byte is parsed. Parsing is :func:`to_symbol_info`, the live mapper.

    :raises SnapshotError: the response or its digest is missing, the digest is malformed or
        does not match, or the response is not a single-symbol ``exchangeInfo`` the mapper
        accepts.
    """
    path = snapshot_file(root, environment, symbol)
    sum_path = checksum_file(root, environment, symbol)
    try:
        raw = path.read_bytes()
        sum_text = sum_path.read_text(encoding="ascii")
    except (OSError, UnicodeDecodeError) as exc:
        raise SnapshotError(
            f"no usable snapshot of {symbol} on {environment} at {path}: {exc}. Fetch it with "
            "scripts/download_exchange_info.py"
        ) from exc
    found = _CHECKSUM_LINE.fullmatch(sum_text)
    if found is None or found.group(2) != path.name:
        raise SnapshotError(f"{sum_path} is not '<sha256>  {path.name}'")
    digest = hashlib.sha256(raw).hexdigest()
    if digest != found.group(1):
        raise SnapshotError(f"{path} no longer matches its recorded SHA-256")
    entry, server_time = _entry(raw, symbol)
    try:
        info = to_symbol_info(entry)
    except ExchangeAPIError as exc:
        raise SnapshotError(f"{symbol}: the live mapper refuses the entry ({exc})") from exc
    return Snapshot(environment, symbol, digest, server_time, info, path)
