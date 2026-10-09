"""Regime labels (R-AI): calendar quarters labelled by BTCUSDT's quarterly return.

The project owner's ruling R-AI, verbatim: *"Regimes are labelled per calendar quarter by
BTCUSDT's quarterly return: above +15% rising, below -15% falling, otherwise sideways. The
labels are computed once from the store, committed in a file with its digest, and fixed before
S6."*

**The definitions the ruling leaves open, chosen here and written into the committed file.**

* *Quarter*: a calendar quarter in UTC, half-open ``[start, end)``: Q1 is 1 January to 1 April,
  Q4 is 1 October to 1 January of the next year. A bar belongs to the quarter of the UTC date of
  its open time, so the bar opening ``2024-04-01T00:00Z`` is the first bar of ``2024Q2``.
* *Quarterly return*: ``close_last / open_first - 1`` over the quarter's DAILY bars -- the open
  of the quarter's first day to the close of its last. The daily series is used because it is
  the coarsest the store holds and a quarter is days long.
* *Complete*: a quarter is labelled only if the store holds exactly one daily bar for every day
  of it. **A quarter with a missing day, or one that begins or ends outside the stored history
  (the first, 2017Q3, begins on 2017-08-17), is PARTIAL and carries no label**: a return
  measured over part of a quarter is a different quantity, and a label inferred from it would be
  an invention.
* *Thresholds*: *above +15%* and *below -15%* are strict, so exactly +15% or exactly -15% is
  ``sideways``. **The test is exact**: it compares ``close_last`` with ``open_first * 1.15`` and
  ``open_first * 0.85`` in ``Decimal``, and never divides, so no rounding decides a label. The
  return printed in the file is the quotient rounded to six places, for a reader; nothing is
  decided from it.

This module is pure: it reads no file and no store. ``scripts/regime_labels.py`` reads the store
and writes the committed file, and :class:`RegimeTable` is how the metrics read it back.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from enum import Enum
from pathlib import Path
from typing import Final

from trading_bot.core.models import Candle

__all__ = [
    "FALLING_BELOW",
    "RISING_ABOVE",
    "SCHEMA",
    "QuarterLabel",
    "Regime",
    "RegimeTable",
    "build_document",
    "classify",
    "document_digest",
    "label_quarters",
    "quarter_bounds",
    "quarter_key",
    "render_document",
]

#: The ruled thresholds as fractions of the quarter's opening price.
RISING_ABOVE: Final = Decimal("0.15")
FALLING_BELOW: Final = Decimal("-0.15")

#: The shape of the committed document. Bump it when a key is added, renamed or removed.
SCHEMA: Final = 1

_SIX_PLACES = Decimal("0.000001")


class Regime(str, Enum):
    RISING = "rising"
    FALLING = "falling"
    SIDEWAYS = "sideways"


@dataclass(frozen=True)
class QuarterLabel:
    """One calendar quarter and what the store says of it.

    ``regime`` is ``None`` exactly when the quarter is partial, and ``note`` then says why.
    ``open_first`` and ``close_last`` are ``None`` only for a quarter with no bar at all.
    """

    quarter: str
    start: date
    end: date
    bars: int
    expected_bars: int
    open_first: Decimal | None
    close_last: Decimal | None
    regime: Regime | None
    note: str

    @property
    def complete(self) -> bool:
        return self.regime is not None

    @property
    def quarterly_return(self) -> Decimal | None:
        """``close_last / open_first - 1`` rounded to six places; for display only."""
        if self.open_first is None or self.close_last is None or self.open_first <= 0:
            return None
        return (self.close_last / self.open_first - 1).quantize(_SIX_PLACES)


def quarter_key(day: date) -> str:
    """``2024Q1`` for any date in the first quarter of 2024."""
    return f"{day.year}Q{(day.month - 1) // 3 + 1}"


def quarter_bounds(key: str) -> tuple[date, date]:
    """The half-open ``[start, end)`` dates of a quarter key such as ``2024Q4``."""
    if len(key) != 6 or key[4] != "Q" or not key[:4].isdigit() or key[5] not in "1234":
        raise ValueError(f"not a quarter key: {key!r}")
    year, quarter = int(key[:4]), int(key[5])
    start = date(year, 3 * (quarter - 1) + 1, 1)
    end = date(year + 1, 1, 1) if quarter == 4 else date(year, 3 * quarter + 1, 1)
    return start, end


def classify(open_first: Decimal, close_last: Decimal) -> Regime:
    """The ruled label for a quarter that opened at ``open_first`` and closed at ``close_last``.

    Exact: ``rising`` only if ``close_last`` is strictly above ``open_first * 1.15``, ``falling``
    only if strictly below ``open_first * 0.85``; a close exactly on either bound is ``sideways``.

    :raises ValueError: ``open_first`` is not positive.
    """
    if open_first <= 0:
        raise ValueError(f"a quarter cannot open at {open_first}")
    if close_last > open_first * (1 + RISING_ABOVE):
        return Regime.RISING
    if close_last < open_first * (1 + FALLING_BELOW):
        return Regime.FALLING
    return Regime.SIDEWAYS


def label_quarters(candles: Iterable[Candle]) -> tuple[QuarterLabel, ...]:
    """Label every calendar quarter the daily candles touch, oldest first.

    ``candles`` are one symbol's closed daily bars, in any order. A quarter between the first and
    the last bar that holds no bar at all is still listed, as a partial one.

    :raises ValueError: a day appears twice.
    """
    by_day: dict[date, Candle] = {}
    for candle in candles:
        day = candle.open_time.date()
        if day in by_day:
            raise ValueError(f"two daily bars open on {day.isoformat()}")
        by_day[day] = candle
    if not by_day:
        return ()
    first_day, last_day = min(by_day), max(by_day)
    labels: list[QuarterLabel] = []
    key = quarter_key(first_day)
    while True:
        start, end = quarter_bounds(key)
        if start > last_day:
            break
        labels.append(_label(key, start, end, by_day, first_day, last_day))
        key = quarter_key(end)
    return tuple(labels)


def _label(
    key: str,
    start: date,
    end: date,
    by_day: Mapping[date, Candle],
    first_day: date,
    last_day: date,
) -> QuarterLabel:
    expected = (end - start).days
    days = [start + timedelta(days=i) for i in range(expected)]
    present = [by_day[d] for d in days if d in by_day]
    open_first = present[0].open if present else None
    close_last = present[-1].close if present else None
    if present and len(present) == expected:
        return QuarterLabel(
            quarter=key,
            start=start,
            end=end,
            bars=expected,
            expected_bars=expected,
            open_first=open_first,
            close_last=close_last,
            regime=classify(present[0].open, present[-1].close),
            note="",
        )
    if start < first_day:
        note = f"the stored history begins {first_day.isoformat()}, inside this quarter"
    elif end - timedelta(days=1) > last_day:
        note = f"the stored history ends {last_day.isoformat()}, inside this quarter"
    else:
        missing = [d.isoformat() for d in days if d not in by_day]
        note = f"{len(missing)} daily bar(s) missing, the first on {missing[0]}"
    return QuarterLabel(
        quarter=key,
        start=start,
        end=end,
        bars=len(present),
        expected_bars=expected,
        open_first=open_first,
        close_last=close_last,
        regime=None,
        note=note,
    )


def build_document(
    labels: Iterable[QuarterLabel], *, symbol: str, interval: str, source: Mapping[str, object]
) -> dict[str, object]:
    """The committed document: the definitions, the source, the counts and every quarter."""
    quarters = tuple(labels)
    counts = {regime.value: 0 for regime in Regime}
    counts["partial"] = 0
    for label in quarters:
        counts["partial" if label.regime is None else label.regime.value] += 1
    return {
        "schema": SCHEMA,
        "symbol": symbol,
        "interval": interval,
        "definition": {
            "quarter": "calendar quarter in UTC, half-open [start, end)",
            "bar_belongs_to": "the quarter of the UTC date of its open time",
            "quarterly_return": "close_last / open_first - 1 over the quarter's daily bars",
            "rising_above": str(RISING_ABOVE),
            "falling_below": str(FALLING_BELOW),
            "boundaries": "strict; exactly +15% or exactly -15% is sideways",
            "decided_by": "exact Decimal comparison with open_first * 1.15 and * 0.85, no division",
            "partial": "no label unless every day of the quarter has exactly one stored bar",
        },
        "source": dict(source),
        "counts": {**counts, "quarters": len(quarters)},
        "quarters": [
            {
                "quarter": q.quarter,
                "start": q.start.isoformat(),
                "end": q.end.isoformat(),
                "bars": q.bars,
                "expected_bars": q.expected_bars,
                "open_first": None if q.open_first is None else str(q.open_first),
                "close_last": None if q.close_last is None else str(q.close_last),
                "return": None if q.quarterly_return is None else format(q.quarterly_return, "f"),
                "regime": None if q.regime is None else q.regime.value,
                "note": q.note,
            }
            for q in quarters
        ],
    }


def render_document(document: Mapping[str, object]) -> bytes:
    """The document's bytes: sorted keys, two-space indent, LF, one trailing newline."""
    return (json.dumps(document, sort_keys=True, indent=2) + "\n").encode("utf-8")


def document_digest(rendered: bytes) -> str:
    """The SHA-256 of the rendered document, as the committed ``.sha256`` file records it."""
    return hashlib.sha256(rendered).hexdigest()


class RegimeTable:
    """The committed labels, read back: a date's quarter and that quarter's regime."""

    def __init__(self, regimes: Mapping[str, Regime | None], *, digest: str | None = None) -> None:
        self._regimes = dict(regimes)
        #: The SHA-256 of the file the table was read from, or ``None`` if it was built by hand.
        self.digest = digest

    @classmethod
    def from_document(
        cls, document: Mapping[str, object], *, digest: str | None = None
    ) -> RegimeTable:
        quarters = document["quarters"]
        if not isinstance(quarters, list):
            raise ValueError("the regime document has no quarters list")
        regimes: dict[str, Regime | None] = {}
        for row in quarters:
            label = row["regime"]
            regimes[str(row["quarter"])] = None if label is None else Regime(label)
        return cls(regimes, digest=digest)

    @classmethod
    def from_file(cls, path: Path) -> RegimeTable:
        """Read the committed document, refusing it if its digest file does not match.

        :raises ValueError: the ``.sha256`` beside ``path`` is missing or differs from the bytes.
        """
        data = path.read_bytes()
        digest_file = path.with_name(path.name + ".sha256")
        recorded = (
            digest_file.read_text(encoding="ascii").split()[0] if digest_file.is_file() else ""
        )
        if recorded != document_digest(data):
            raise ValueError(f"{path} does not match its digest file {digest_file}")
        return cls.from_document(json.loads(data), digest=recorded)

    def regime_on(self, day: date) -> Regime | None:
        """The regime of ``day``'s quarter; ``None`` if it is partial or not in the table."""
        return self._regimes.get(quarter_key(day))

    def quarter_is_known(self, day: date) -> bool:
        return quarter_key(day) in self._regimes
