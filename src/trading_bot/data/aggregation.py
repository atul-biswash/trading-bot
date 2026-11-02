"""Aggregate stored 1m bars into 4h and 1d bars, each tagged complete or incomplete.

The input is a stream of 1m ``Candle`` objects, normally from ``HistoricalStore.candles``,
which only reads. The output is one ``AggregatedBar`` per bucket that holds at least one
stored minute, in the same ``Decimal`` the store serves. Nothing is rounded, divided or
converted to ``float``: an open is the first stored minute's open, a close the last stored
minute's close, a high and a low the extremes and a volume an exact sum.

**Buckets sit on the UTC grid.** A 1d bucket opens at ``00:00``; a 4h bucket opens at
``00``, ``04``, ``08``, ``12``, ``16`` or ``20``. Both are multiples of their width from the
epoch, which is how the venue aligns them, and ``close_time`` is the last millisecond of the
bucket, as the venue's is.

**A gap is reported and never filled.** A bucket with some of its minutes stored is emitted
with ``minutes_missing`` counting the rest and is not complete; a bucket with none is not
emitted at all. No minute is invented, copied forward or interpolated, so a downstream
reader that wants only whole buckets filters on ``complete`` and one that wants every
bucket the store can say anything about takes them all.

**A second aggregation takes the prices over traded minutes only** (``aggregate_traded_bars``,
``TradedBar``), because the archive writes a zero-volume filler bar for a minute nothing traded
in and its prices are the previous close. The plain aggregation above takes the filler's open
as a bucket's open when the first minute is a filler, and that is why it differs from the
venue's bar in about one to four percent of complete buckets (``docs/RUN_LEDGER.md`` section
75). The store keeps no trade count, so a traded minute is one with nonzero volume.

**The range is checked before any file is opened.** ``aggregate_from_store`` requires a
start and an end that sit on the timeframe's grid, because a range cut inside a bucket
would make its last bucket look incomplete for a reason that is not the store's, and it
hands the store an end at which month files starting at or after it are never opened.
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Final

from pydantic import BaseModel, ConfigDict, model_validator

from trading_bot.core.models import Candle, Money
from trading_bot.data.historical import INTERVAL_MS, HistoricalStore

__all__ = [
    "AGGREGATED_TIMEFRAMES",
    "AggregatedBar",
    "AggregationError",
    "TradedBar",
    "aggregate_bars",
    "aggregate_from_store",
    "aggregate_traded_bars",
    "aggregate_traded_from_store",
]

AGGREGATED_TIMEFRAMES: Final = ("4h", "1d")

_MINUTE_MS: Final = INTERVAL_MS["1m"]
_EPOCH: Final = datetime(1970, 1, 1, tzinfo=timezone.utc)
_MS: Final = timedelta(milliseconds=1)


class AggregationError(Exception):
    """The input cannot be aggregated without guessing: say so rather than guess."""


class AggregatedBar(BaseModel):
    """One 4h or 1d bar built from stored 1m bars, and how many of its minutes were stored."""

    model_config = ConfigDict(frozen=True)

    symbol: str
    timeframe: str
    open_time: datetime
    close_time: datetime
    open: Money
    high: Money
    low: Money
    close: Money
    volume: Money
    minutes_present: int
    minutes_missing: int

    @property
    def complete(self) -> bool:
        return self.minutes_missing == 0


class _Bucket:
    __slots__ = ("close", "high", "low", "open", "open_ms", "present", "volume")

    def __init__(self, open_ms: int, first: Candle) -> None:
        self.open_ms = open_ms
        self.open = first.open
        self.high = first.high
        self.low = first.low
        self.close = first.close
        self.volume = first.volume
        self.present = 1

    def add(self, candle: Candle) -> None:
        if candle.high > self.high:
            self.high = candle.high
        if candle.low < self.low:
            self.low = candle.low
        self.close = candle.close
        self.volume += candle.volume
        self.present += 1

    def build(self, symbol: str, timeframe: str, width_ms: int) -> AggregatedBar:
        return AggregatedBar(
            symbol=symbol,
            timeframe=timeframe,
            open_time=_EPOCH + timedelta(milliseconds=self.open_ms),
            close_time=_EPOCH + timedelta(milliseconds=self.open_ms + width_ms - 1),
            open=self.open,
            high=self.high,
            low=self.low,
            close=self.close,
            volume=self.volume,
            minutes_present=self.present,
            minutes_missing=width_ms // _MINUTE_MS - self.present,
        )


def _width_ms(timeframe: str) -> int:
    if timeframe not in AGGREGATED_TIMEFRAMES:
        raise AggregationError(
            f"not an aggregated timeframe: {timeframe!r}; expected one of {AGGREGATED_TIMEFRAMES}"
        )
    return INTERVAL_MS[timeframe]


def _epoch_ms(moment: datetime, name: str) -> int:
    if moment.tzinfo is None:
        raise AggregationError(f"{name} must be timezone-aware, not naive: {moment!r}")
    return (moment - _EPOCH) // _MS


def _require_grid(timeframe: str, start: datetime, end: datetime) -> None:
    width_ms = _width_ms(timeframe)
    for name, moment in (("start", start), ("end", end)):
        if _epoch_ms(moment, name) % width_ms:
            raise AggregationError(f"{name} is not on the {timeframe} grid: {moment!r}")


def _checked_stream(candles: Iterable[Candle], width_ms: int) -> Iterator[tuple[str, int, Candle]]:
    """Each candle of a 1m stream with its symbol and the open of its bucket, after the checks.

    Raises ``AggregationError`` for a candle that is not a 1m bar, a second symbol, and an
    open time that is off the minute or does not increase. A generator: the checks run as
    the stream is consumed.
    """
    symbol: str | None = None
    previous_ms: int | None = None
    for candle in candles:
        if candle.timeframe != "1m":
            raise AggregationError(f"expected 1m candles, got {candle.timeframe!r}")
        if symbol is None:
            symbol = candle.symbol
        elif candle.symbol != symbol:
            raise AggregationError(f"mixed symbols: {symbol!r} and {candle.symbol!r}")
        opened_ms = _epoch_ms(candle.open_time, "open_time")
        if opened_ms % _MINUTE_MS:
            raise AggregationError(f"open time is off the minute grid: {candle.open_time!r}")
        if previous_ms is not None and opened_ms <= previous_ms:
            raise AggregationError(f"open times do not increase at {candle.open_time!r}")
        previous_ms = opened_ms
        yield symbol, opened_ms - opened_ms % width_ms, candle


def aggregate_bars(candles: Iterable[Candle], timeframe: str) -> Iterator[AggregatedBar]:
    """Aggregate a time-ordered stream of 1m candles of one symbol into ``timeframe`` bars.

    Raises ``AggregationError`` for the stream faults ``_checked_stream`` names and for a
    timeframe other than ``AGGREGATED_TIMEFRAMES``. A generator: the checks run as the stream
    is consumed.
    """
    width_ms = _width_ms(timeframe)
    current: _Bucket | None = None
    last_symbol = ""
    for symbol, bucket_ms, candle in _checked_stream(candles, width_ms):
        last_symbol = symbol
        if current is None:
            current = _Bucket(bucket_ms, candle)
        elif current.open_ms == bucket_ms:
            current.add(candle)
        else:
            yield current.build(symbol, timeframe, width_ms)
            current = _Bucket(bucket_ms, candle)
    if current is not None:
        yield current.build(last_symbol, timeframe, width_ms)


def aggregate_from_store(
    store: HistoricalStore, symbol: str, timeframe: str, start: datetime, end: datetime
) -> Iterator[AggregatedBar]:
    """Aggregate the store's 1m bars with ``start <= open_time < end`` into ``timeframe`` bars.

    ``start`` and ``end`` must be timezone-aware and on the timeframe's UTC grid; they are
    checked now, when this is called, and files are read as the iterator is consumed. The
    store opens no month file that begins at or after ``end``.
    """
    _require_grid(timeframe, start, end)
    return aggregate_bars(store.candles(symbol, "1m", start, end), timeframe)


class TradedBar(BaseModel):
    """One 4h or 1d bar whose prices are those of its traded minutes only.

    A traded minute is a minute with nonzero volume, because the store keeps no trade count.
    ``open`` is the first traded minute's open, ``close`` the last traded minute's close,
    ``high`` and ``low`` the extremes over the traded minutes; a minute with no volume is the
    filler the archive writes for a minute nothing traded in, its prices are the previous
    close, and it takes no part in them. ``volume`` is the sum over every stored minute, as in
    ``AggregatedBar``. A bucket with no traded minute has no prices, which are ``None``
    together, and is not given any.
    """

    model_config = ConfigDict(frozen=True)

    symbol: str
    timeframe: str
    open_time: datetime
    close_time: datetime
    open: Money | None
    high: Money | None
    low: Money | None
    close: Money | None
    volume: Money
    minutes_present: int
    minutes_missing: int
    traded_minutes: int

    @model_validator(mode="after")
    def _prices_follow_the_traded_minutes(self) -> TradedBar:
        priced = (self.open, self.high, self.low, self.close)
        if self.traded_minutes == 0 and any(price is not None for price in priced):
            raise ValueError("a bucket with no traded minute has no prices")
        if self.traded_minutes > 0 and any(price is None for price in priced):
            raise ValueError("a bucket with a traded minute has all four prices")
        return self

    @property
    def complete(self) -> bool:
        return self.minutes_missing == 0

    @property
    def has_trade(self) -> bool:
        return self.traded_minutes > 0


class _TradedBucket:
    __slots__ = ("close", "high", "low", "open", "open_ms", "present", "traded", "volume")

    def __init__(self, open_ms: int, first: Candle) -> None:
        self.open_ms = open_ms
        self.open: Decimal | None = None
        self.high: Decimal | None = None
        self.low: Decimal | None = None
        self.close: Decimal | None = None
        self.volume = Decimal(0)
        self.present = 0
        self.traded = 0
        self.add(first)

    def add(self, candle: Candle) -> None:
        self.volume += candle.volume
        self.present += 1
        if candle.volume == 0:
            return
        if self.open is None or self.high is None or self.low is None:
            self.open = candle.open
            self.high = candle.high
            self.low = candle.low
        else:
            if candle.high > self.high:
                self.high = candle.high
            if candle.low < self.low:
                self.low = candle.low
        self.close = candle.close
        self.traded += 1

    def build(self, symbol: str, timeframe: str, width_ms: int) -> TradedBar:
        return TradedBar(
            symbol=symbol,
            timeframe=timeframe,
            open_time=_EPOCH + timedelta(milliseconds=self.open_ms),
            close_time=_EPOCH + timedelta(milliseconds=self.open_ms + width_ms - 1),
            open=self.open,
            high=self.high,
            low=self.low,
            close=self.close,
            volume=self.volume,
            minutes_present=self.present,
            minutes_missing=width_ms // _MINUTE_MS - self.present,
            traded_minutes=self.traded,
        )


def aggregate_traded_bars(candles: Iterable[Candle], timeframe: str) -> Iterator[TradedBar]:
    """Aggregate a time-ordered stream of 1m candles into ``timeframe`` bars over traded minutes.

    The same stream checks, the same grid and the same completeness as ``aggregate_bars``;
    only the four prices differ (see ``TradedBar``). A generator.
    """
    width_ms = _width_ms(timeframe)
    current: _TradedBucket | None = None
    last_symbol = ""
    for symbol, bucket_ms, candle in _checked_stream(candles, width_ms):
        last_symbol = symbol
        if current is None:
            current = _TradedBucket(bucket_ms, candle)
        elif current.open_ms == bucket_ms:
            current.add(candle)
        else:
            yield current.build(symbol, timeframe, width_ms)
            current = _TradedBucket(bucket_ms, candle)
    if current is not None:
        yield current.build(last_symbol, timeframe, width_ms)


def aggregate_traded_from_store(
    store: HistoricalStore, symbol: str, timeframe: str, start: datetime, end: datetime
) -> Iterator[TradedBar]:
    """``aggregate_from_store`` with the traded-minute prices of ``aggregate_traded_bars``."""
    _require_grid(timeframe, start, end)
    return aggregate_traded_bars(store.candles(symbol, "1m", start, end), timeframe)
