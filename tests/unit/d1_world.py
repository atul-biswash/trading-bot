"""A small 1m world for the D1 executor and replay tests.

Not a test module (nothing here is collected). Every store is built through the real ``ingest_zip``
from a hand-written archive, one month, one row per minute. A minute is ``(open, high, low, close,
volume)`` as strings; any minute not named is a flat bar at the base price with volume 1, and a minute
in ``omit`` is not in the archive at all. Minute 0 is ``2024-03-01T00:00Z``.
"""

from __future__ import annotations

import hashlib
import io
import zipfile
from collections.abc import Mapping
from datetime import datetime, timedelta, timezone
from pathlib import Path

from trading_bot.data.historical import HistoricalStore, ingest_zip, month_bounds_ms

MONTH = "2024-03"
START_MS, _ = month_bounds_ms(MONTH)
MINUTE_MS = 60_000
T0 = datetime(2024, 3, 1, tzinfo=timezone.utc)

Minute = tuple[str, str, str, str, str]


def at(minute: int) -> datetime:
    """The instant of ``minute`` minutes after the first of the month, UTC."""
    return T0 + timedelta(minutes=minute)


def flat(price: str, volume: str = "1") -> Minute:
    return (price, price, price, price, volume)


def minute_line(index: int, row: Minute) -> str:
    opened = START_MS + index * MINUTE_MS
    open_, high, low, close, volume = row
    return (
        f"{opened},{open_}.00000000,{high}.00000000,{low}.00000000,{close}.00000000,"
        f"{volume}.00000000,{opened + MINUTE_MS - 1},100.00000000,1,0.50000000,50.00000000,0"
    )


def build_minutes(
    root: Path,
    symbol: str,
    *,
    count: int,
    minutes: Mapping[int, Minute] | None = None,
    base: str = "100",
    omit: frozenset[int] = frozenset(),
) -> HistoricalStore:
    """Store ``count`` minutes of ``symbol``'s 1m series under ``root`` and return the store.

    A price may carry decimals as a string (``"94.5"``): the archive writer appends ``.00000000``,
    so give whole numbers here and build fractional prices from whole ones in the test.
    """
    named = dict(minutes or {})
    lines = [
        minute_line(index, named.get(index, flat(base)))
        for index in range(count)
        if index not in omit
    ]
    data = io.BytesIO()
    with zipfile.ZipFile(data, "w") as archive:
        archive.writestr(f"{symbol}-1m-{MONTH}.csv", "\n".join(lines) + "\n")
    raw = data.getvalue()
    ingest_zip(
        raw,
        expected_sha256=hashlib.sha256(raw).hexdigest(),
        root=root,
        symbol=symbol,
        interval="1m",
        month=MONTH,
        source_url=f"https://example.invalid/{symbol}-1m-{MONTH}.zip",
    )
    return HistoricalStore(root)
