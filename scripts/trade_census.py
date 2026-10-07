#!/usr/bin/env python
"""Census every booked trade in a frozen capture of the bot's log, per trade and in total.

**IT READS A CAPTURE AND NOTHING ELSE.** The path is refused if it lies under a
``logs/`` directory, by the same function ``scripts/run_census.py`` uses, and there
is no default argument. It writes nothing, opens no socket and imports nothing from
``trading_bot``: its whole input is the log's text. Every figure carries the SHA-256
of the file it came from.

**WHAT IT PARSES, AND WHAT RENAMING ONE OF THEM DOES.** Four events, by the value
the bot logs: ``order_placed`` (``execution/executor.py``, ``_EVENT_PLACED``),
``close_booked`` (``execution/executor.py``, ``_EVENT_CLOSE_BOOKED``),
``exit_booked`` (``execution/reconciliation_driver.py``, ``_EVENT_BOOKED``) and
``boot_exit_booked`` (``engine/modes.py``, ``_EVENT_EXIT_BOOKED``).
``tests/unit/test_trade_census.py`` pins each of the four against the constant it
mirrors, so a rename fails a test rather than emptying the census.

**EVERY BOOKING IS MATCHED TO ITS PLACEMENT, AND THE RULE IS NARROW ON PURPOSE.** An
``order_placed`` line is logged when a list is accepted, and a ``FOK`` entry that does
not fill leaves a placement with no booking at all, so the placements of one symbol
are not a queue a booking pops from the front. A booking takes the LATEST placement of
its symbol that lies after that symbol's previous booking and before the booking
itself, preferring one whose quantity equals the booking's. A symbol cannot be
re-entered while held, so no placement of a position that is open can lie between
that position's entry and its booking; and a placement before the previous booking
belongs to a position already closed. A booking with no such placement is unmatched,
listed, and still counted: its entry total comes from its own line.

**THE ENTRY QUOTE TOTAL IS THE BOOKING'S, NOT A QUOTIENT.** It is the line's
``entry_quote_total`` where the line carries one, and otherwise the exit's quote total
less its fee less its realised figure, which is the identity ``Portfolio`` books by. A
fee in an asset other than the quote asset leaves the total unknown and the trade out
of every return figure, listed.

**TWO FACTS ABOUT TIME.** Lines before 2026-09-09 carry local time with no zone, so a
duration is taken from ``entry_bar_time`` and ``candle_time``, both zoned, and never
from the line's own stamp. A booking's DAY is attributed by its booking time, as
``Portfolio`` attributes it, never by its candle time: a zoned stamp is read as UTC, a
naive one is shifted by the offset inferred from the capture's own naive
``close_booked`` lines (the smallest of ``stamp - candle_time``, rounded to a quarter
hour), and the evidence for that offset is printed. A boot-booked line states its own
``booked_day`` and that is used.

**``--until`` REPRODUCES AN EARLIER CENSUS OF A LATER CAPTURE.** A capture that grew
after an earlier census was taken holds that census's bookings as a prefix. Giving the
earlier census's last record time, ``--until 2026-09-24T03:58:40Z``, counts only the
bookings made at or before it, matching and offset inference still run over the whole
file, and the header says how many bookings were kept and how many excluded.

**ALL MONEY IS ``Decimal``.** A return is a percentage of the entry quote total, and
a quotient computed here is reported and never booked. The interval is the mean plus
or minus 1.96 standard errors of the sample standard deviation, which is what the
census this tool replaces reported. A leg is a stop-loss where the line says so, and
otherwise where the exit's average price is below the entry's; its slippage beyond
the trigger is ``(stop - exit price) / stop`` against the matched placement's
``stop_loss``. Its stop distance and its exit move are both measured from that
placement's ``entry`` limit, which is where a stop's own percentage is set: a 2% stop
that fills 4.21% beyond its trigger exits 6.13% below the limit, and that is a price
move, not the realised return, which is taken on the booked entry total.
"""

from __future__ import annotations

import argparse
import re
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from enum import Enum
from pathlib import Path

from run_census import CaptureRefusedError, digest_of, reject_live_log

EVENT_PLACED = "order_placed"
EVENT_CLOSE_BOOKED = "close_booked"
EVENT_EXIT_BOOKED = "exit_booked"
EVENT_BOOT_EXIT_BOOKED = "boot_exit_booked"

_BOOKING_EVENTS = (EVENT_CLOSE_BOOKED, EVENT_EXIT_BOOKED, EVENT_BOOT_EXIT_BOOKED)
_EVENTS = (EVENT_PLACED, *_BOOKING_EVENTS)

_EVENT_PATTERN = re.compile(r"event=([a-z0-9_]+)")
_FIELD_PATTERN = re.compile(r"(?<![\w.])([a-z][a-z0-9_]*)=(\S+)")
_STAMP_PATTERN = re.compile(r"^(\d{4})-(\d{2})-(\d{2})[ T](\d{2}):(\d{2}):(\d{2})(Z?)")

_Z_95 = Decimal("1.96")
_HUNDRED = Decimal(100)
_TWO = Decimal(2)
_QUARTER_HOUR_S = 900
_OFFSET_WINDOW = (timedelta(seconds=-60), timedelta(hours=1))
_REFUSED_EXIT = 2
_ANOMALY_EXIT = 1


class Route(str, Enum):
    """Which path booked the exit: the strategy's own ``CLOSE``, or a protective leg."""

    CLOSE = "CLOSE"
    LEG = "LEG"


class Leg(str, Enum):
    """A protective leg, where the exit is one."""

    STOP_LOSS = "SL"
    TAKE_PROFIT = "TP"


@dataclass(frozen=True)
class Placement:
    """One ``order_placed`` line."""

    line_no: int
    symbol: str
    quantity: Decimal
    entry: Decimal
    stop_loss: Decimal
    entry_bar_time: datetime
    list_client_order_id: str | None


@dataclass(frozen=True)
class Booking:
    """One booking line, as logged."""

    line_no: int
    event: str
    symbol: str
    order_id: str
    quantity: Decimal
    quote_total: Decimal
    realised: Decimal
    stamp: datetime
    fee: Decimal | None
    fee_asset: str | None
    entry_quote_total: Decimal | None
    candle_time: datetime | None
    filled_at: datetime | None
    leg_label: str | None
    close_client_order_id: str | None
    booked_day: date | None


@dataclass(frozen=True)
class Anomaly:
    """A line the tool read and could not turn into a placement or a booking."""

    line_no: int
    event: str
    reason: str


@dataclass(frozen=True)
class Parsed:
    """The placements, bookings and anomalies of one capture, in file order."""

    placements: tuple[Placement, ...]
    bookings: tuple[Booking, ...]
    anomalies: tuple[Anomaly, ...]


@dataclass(frozen=True)
class OffsetEstimate:
    """The inferred offset of the capture's naive stamps, and the evidence for it."""

    offset: timedelta
    lines_used: int
    lines_agreeing: int


@dataclass(frozen=True)
class Trade:
    """One booking, its matched placement and every figure derived from them."""

    booking: Booking
    placement: Placement | None
    quantity_matches: bool | None
    route: Route
    leg: Leg | None
    entry_quote_total: Decimal | None
    entry_total_source: str
    return_pct: Decimal | None
    entry_time: datetime | None
    exit_time: datetime | None
    booked_at: datetime | None
    booked_day: date | None
    exit_price: Decimal
    slippage_pct: Decimal | None
    stop_distance_pct: Decimal | None
    exit_move_pct: Decimal | None


@dataclass(frozen=True)
class ReturnStats:
    """Mean, sample standard deviation and the 95% interval of a set of returns."""

    n: int
    mean: Decimal | None
    sd: Decimal | None
    se: Decimal | None
    low: Decimal | None
    high: Decimal | None


@dataclass(frozen=True)
class Totals:
    """Counts and money over a set of trades."""

    count: int
    realised: Decimal
    wins: int
    gross_win: Decimal
    gross_loss: Decimal
    win_rate_pct: Decimal | None
    profit_factor: Decimal | None


class _LineError(Exception):
    """A line that cannot be read, with the reason that is reported."""


def _fields(line: str) -> dict[str, str]:
    found: dict[str, str] = {}
    for key, value in _FIELD_PATTERN.findall(line):
        found.setdefault(key, value)
    return found


def _stamp(line: str) -> datetime:
    match = _STAMP_PATTERN.match(line)
    if match is None:
        raise _LineError("the line carries no leading timestamp")
    year, month, day, hour, minute, second = (int(part) for part in match.groups()[:6])
    zone = timezone.utc if match.group(7) == "Z" else None
    return datetime(year, month, day, hour, minute, second, tzinfo=zone)


def _decimal(fields: dict[str, str], key: str) -> Decimal:
    raw = fields.get(key)
    if raw is None:
        raise _LineError(f"missing field {key}")
    return _parse_decimal(key, raw)


def _parse_decimal(key: str, raw: str) -> Decimal:
    try:
        value = Decimal(raw)
    except InvalidOperation as exc:
        raise _LineError(f"field {key} is not a decimal: {raw!r}") from exc
    if not value.is_finite():
        raise _LineError(f"field {key} is not finite: {raw!r}")
    return value


def _positive(fields: dict[str, str], key: str) -> Decimal:
    value = _decimal(fields, key)
    if value <= 0:
        raise _LineError(f"field {key} is not positive: {fields[key]!r}")
    return value


def _optional_decimal(fields: dict[str, str], key: str) -> Decimal | None:
    return _parse_decimal(key, fields[key]) if key in fields else None


def _optional_time(fields: dict[str, str], key: str) -> datetime | None:
    raw = fields.get(key)
    if raw is None:
        return None
    try:
        value = datetime.fromisoformat(raw)
    except ValueError as exc:
        raise _LineError(f"field {key} is not a timestamp: {raw!r}") from exc
    if value.tzinfo is None:
        raise _LineError(f"field {key} carries no zone: {raw!r}")
    return value.astimezone(timezone.utc)


def _required(fields: dict[str, str], key: str) -> str:
    raw = fields.get(key)
    if raw is None:
        raise _LineError(f"missing field {key}")
    return raw


def _placement(line_no: int, fields: dict[str, str]) -> Placement:
    entry_bar_time = _optional_time(fields, "entry_bar_time")
    if entry_bar_time is None:
        raise _LineError("missing field entry_bar_time")
    return Placement(
        line_no=line_no,
        symbol=_required(fields, "symbol"),
        quantity=_positive(fields, "quantity"),
        entry=_positive(fields, "entry"),
        stop_loss=_positive(fields, "stop_loss"),
        entry_bar_time=entry_bar_time,
        list_client_order_id=fields.get("list_client_order_id"),
    )


def _booked_day(fields: dict[str, str]) -> date | None:
    raw = fields.get("booked_day")
    if raw is None:
        return None
    try:
        return date.fromisoformat(raw)
    except ValueError as exc:
        raise _LineError(f"field booked_day is not a date: {raw!r}") from exc


def _booking(line_no: int, event: str, line: str, fields: dict[str, str]) -> Booking:
    return Booking(
        line_no=line_no,
        event=event,
        symbol=_required(fields, "symbol"),
        order_id=_required(fields, "order_id"),
        quantity=_positive(fields, "quantity"),
        quote_total=_positive(fields, "quote_total"),
        realised=_decimal(fields, "realised"),
        stamp=_stamp(line),
        fee=_optional_decimal(fields, "fee"),
        fee_asset=fields.get("fee_asset"),
        entry_quote_total=_optional_decimal(fields, "entry_quote_total"),
        candle_time=_optional_time(fields, "candle_time"),
        filled_at=_optional_time(fields, "filled_at"),
        leg_label=fields.get("leg"),
        close_client_order_id=fields.get("close_client_order_id"),
        booked_day=_booked_day(fields),
    )


def parse_capture(lines: Sequence[str]) -> Parsed:
    """Read the four events out of ``lines``; a line that cannot be read is an anomaly.

    A booking whose ``(symbol, order_id)`` an earlier booking already carried is an
    anomaly and is not counted, because one sell is one booking.
    """
    placements: list[Placement] = []
    bookings: list[Booking] = []
    anomalies: list[Anomaly] = []
    seen: set[tuple[str, str]] = set()
    for line_no, line in enumerate(lines, start=1):
        found = _EVENT_PATTERN.search(line)
        if found is None or found.group(1) not in _EVENTS:
            continue
        event = found.group(1)
        fields = _fields(line)
        try:
            if event == EVENT_PLACED:
                placements.append(_placement(line_no, fields))
                continue
            booking = _booking(line_no, event, line, fields)
        except _LineError as exc:
            anomalies.append(Anomaly(line_no, event, str(exc)))
            continue
        key = (booking.symbol, booking.order_id)
        if key in seen:
            anomalies.append(
                Anomaly(line_no, event, f"duplicate booking of {key[0]} order {key[1]}")
            )
            continue
        seen.add(key)
        bookings.append(booking)
    return Parsed(tuple(placements), tuple(bookings), tuple(anomalies))


def infer_local_offset(bookings: Sequence[Booking]) -> OffsetEstimate | None:
    """Infer the offset of the naive stamps from naive bookings that carry a ``candle_time``.

    The smallest ``stamp - candle_time`` is the booking that followed its candle most
    promptly, so it is the nearest to the offset itself; it is rounded to a quarter
    hour. ``lines_agreeing`` counts the lines whose stamp lies within a minute before
    and an hour after the candle once that offset is applied.
    """
    deltas = [
        booking.stamp - booking.candle_time.replace(tzinfo=None)
        for booking in bookings
        if booking.stamp.tzinfo is None and booking.candle_time is not None
    ]
    if not deltas:
        return None
    smallest = min(deltas)
    quarters = (int(smallest.total_seconds()) + _QUARTER_HOUR_S // 2) // _QUARTER_HOUR_S
    offset = timedelta(seconds=quarters * _QUARTER_HOUR_S)
    low, high = _OFFSET_WINDOW
    agreeing = sum(1 for delta in deltas if low <= delta - offset <= high)
    return OffsetEstimate(offset, len(deltas), agreeing)


def match_placements(
    placements: Sequence[Placement], bookings: Sequence[Booking]
) -> dict[int, Placement | None]:
    """Map each booking's line number to its placement, or ``None``.

    The candidates are the symbol's placements lying strictly between that symbol's
    previous booking and this one, in file order. Of those the latest whose quantity
    equals the booking's is taken; failing that, the latest. Nothing else is paired.
    """
    by_symbol: dict[str, list[Booking]] = defaultdict(list)
    for booking in bookings:
        by_symbol[booking.symbol].append(booking)
    matched: dict[int, Placement | None] = {}
    for symbol, own in by_symbol.items():
        own_placements = [placement for placement in placements if placement.symbol == symbol]
        previous_line = 0
        for booking in sorted(own, key=lambda item: item.line_no):
            candidates = [
                placement
                for placement in own_placements
                if previous_line < placement.line_no < booking.line_no
            ]
            equal = [
                placement for placement in candidates if placement.quantity == booking.quantity
            ]
            chosen = equal[-1] if equal else (candidates[-1] if candidates else None)
            matched[booking.line_no] = chosen
            previous_line = booking.line_no
    return matched


def _entry_total(booking: Booking, quote_asset: str) -> tuple[Decimal | None, str]:
    if booking.entry_quote_total is not None:
        return booking.entry_quote_total, "line"
    fee = Decimal(0)
    if booking.fee is not None:
        if booking.fee_asset != quote_asset:
            return None, "unknown: fee not in the quote asset"
        fee = booking.fee
    return booking.quote_total - fee - booking.realised, "derived"


def _route(booking: Booking) -> Route:
    if booking.event == EVENT_CLOSE_BOOKED:
        return Route.CLOSE
    if booking.event == EVENT_BOOT_EXIT_BOOKED and booking.close_client_order_id is not None:
        return Route.CLOSE
    return Route.LEG


def _leg(booking: Booking, route: Route, entry_price: Decimal | None) -> Leg | None:
    if route is Route.CLOSE:
        return None
    for leg in Leg:
        if booking.leg_label == leg.value:
            return leg
    if entry_price is None:
        return None
    exit_price = booking.quote_total / booking.quantity
    if exit_price < entry_price:
        return Leg.STOP_LOSS
    if exit_price > entry_price:
        return Leg.TAKE_PROFIT
    return None


def _booked_at(booking: Booking, offset: OffsetEstimate | None) -> datetime | None:
    if booking.stamp.tzinfo is not None:
        return booking.stamp.astimezone(timezone.utc)
    if offset is None:
        return None
    return (booking.stamp - offset.offset).replace(tzinfo=timezone.utc)


def _day(booking: Booking, booked_at: datetime | None) -> date | None:
    if booking.booked_day is not None:
        return booking.booked_day
    if booked_at is not None:
        return booked_at.date()
    return None


def build_trades(parsed: Parsed, quote_asset: str) -> tuple[Trade, ...]:
    """Pair every booking with its placement and derive its figures."""
    offset = infer_local_offset(parsed.bookings)
    matched = match_placements(parsed.placements, parsed.bookings)
    trades: list[Trade] = []
    for booking in parsed.bookings:
        placement = matched[booking.line_no]
        route = _route(booking)
        entry_total, source = _entry_total(booking, quote_asset)
        entry_price = entry_total / booking.quantity if entry_total is not None else None
        leg = _leg(booking, route, entry_price)
        exit_price = booking.quote_total / booking.quantity
        return_pct = (
            booking.realised / entry_total * _HUNDRED
            if entry_total is not None and entry_total != 0
            else None
        )
        slippage_pct = None
        stop_distance_pct = None
        exit_move_pct = None
        if leg is Leg.STOP_LOSS and placement is not None:
            slippage_pct = (placement.stop_loss - exit_price) / placement.stop_loss * _HUNDRED
            stop_distance_pct = (placement.entry - placement.stop_loss) / placement.entry * _HUNDRED
            exit_move_pct = (exit_price - placement.entry) / placement.entry * _HUNDRED
        exit_time = booking.candle_time if route is Route.CLOSE else booking.filled_at
        booked_at = _booked_at(booking, offset)
        trades.append(
            Trade(
                booking=booking,
                placement=placement,
                quantity_matches=(
                    None if placement is None else placement.quantity == booking.quantity
                ),
                route=route,
                leg=leg,
                entry_quote_total=entry_total,
                entry_total_source=source,
                return_pct=return_pct,
                entry_time=None if placement is None else placement.entry_bar_time,
                exit_time=exit_time,
                booked_at=booked_at,
                booked_day=_day(booking, booked_at),
                exit_price=exit_price,
                slippage_pct=slippage_pct,
                stop_distance_pct=stop_distance_pct,
                exit_move_pct=exit_move_pct,
            )
        )
    return tuple(trades)


def totals(realised: Sequence[Decimal]) -> Totals:
    """Count, sum, win rate and profit factor of a set of realised figures."""
    wins = [value for value in realised if value > 0]
    losses = [value for value in realised if value < 0]
    gross_win = sum(wins, Decimal(0))
    gross_loss = -sum(losses, Decimal(0))
    count = len(realised)
    return Totals(
        count=count,
        realised=sum(realised, Decimal(0)),
        wins=len(wins),
        gross_win=gross_win,
        gross_loss=gross_loss,
        win_rate_pct=Decimal(len(wins)) / Decimal(count) * _HUNDRED if count else None,
        profit_factor=gross_win / gross_loss if gross_loss != 0 else None,
    )


def return_stats(values: Sequence[Decimal]) -> ReturnStats:
    """Mean, sample standard deviation (n - 1) and the 95% interval of ``values``."""
    n = len(values)
    if n == 0:
        return ReturnStats(0, None, None, None, None, None)
    mean = sum(values, Decimal(0)) / Decimal(n)
    if n == 1:
        return ReturnStats(1, mean, None, None, None, None)
    variance = sum(((value - mean) ** 2 for value in values), Decimal(0)) / Decimal(n - 1)
    sd = variance.sqrt()
    se = sd / Decimal(n).sqrt()
    return ReturnStats(n, mean, sd, se, mean - _Z_95 * se, mean + _Z_95 * se)


def median(values: Sequence[Decimal]) -> Decimal | None:
    """The median of ``values``, or ``None`` when there are none."""
    if not values:
        return None
    ordered = sorted(values)
    middle = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[middle]
    return (ordered[middle - 1] + ordered[middle]) / _TWO


def net_mean(mean: Decimal, fee_percent: Decimal) -> Decimal:
    """The mean return net of a round trip: two sides at ``fee_percent`` each."""
    return mean - _TWO * fee_percent


def _fmt(value: Decimal | None, places: int, suffix: str = "") -> str:
    if value is None:
        return "n/a"
    return f"{value:.{places}f}{suffix}"


def _minutes(delta: timedelta | None) -> str:
    if delta is None:
        return "n/a"
    return f"{int(delta.total_seconds()) // 60}m"


def _hold(trade: Trade) -> timedelta | None:
    if trade.entry_time is None or trade.exit_time is None:
        return None
    return trade.exit_time - trade.entry_time


def _label(trade: Trade) -> str:
    if trade.leg is None:
        return trade.route.value if trade.route is Route.CLOSE else "LEG/?"
    return f"LEG/{trade.leg.value}"


def _stats_lines(name: str, trades: Sequence[Trade], fee_percent: Decimal) -> list[str]:
    returns = [trade.return_pct for trade in trades if trade.return_pct is not None]
    realised = totals([trade.booking.realised for trade in trades])
    stats = return_stats(returns)
    lines = [
        f"  {name}",
        f"    bookings            : {realised.count}",
        f"    realised gross      : {_fmt(realised.realised, 4)} USDT",
        f"    win rate            : {_fmt(realised.win_rate_pct, 1, '%')} "
        f"({realised.wins} of {realised.count})",
        f"    profit factor       : {_fmt(realised.profit_factor, 2)}"
        + ("" if realised.profit_factor is not None else " (no losing booking)"),
        f"    per-trade return n  : {stats.n}",
        f"    mean                : {_fmt(stats.mean, 4, '%')}",
        f"    std dev (n - 1)     : {_fmt(stats.sd, 4, '%')}",
        f"    95% interval        : [{_fmt(stats.low, 4, '%')}, {_fmt(stats.high, 4, '%')}]",
    ]
    if stats.mean is not None:
        net = net_mean(stats.mean, fee_percent)
        t_value = net / stats.se if stats.se is not None and stats.se != 0 else None
        lines.append(f"    net mean at {fee_percent}% a side : {_fmt(net, 4, '%')}")
        lines.append(f"    t of the net mean   : {_fmt(t_value, 2)}")
    else:
        lines.append(f"    net mean at {fee_percent}% a side : n/a")
    return lines


def _slippage_lines(trades: Sequence[Trade]) -> list[str]:
    legs = [trade for trade in trades if trade.leg is Leg.STOP_LOSS]
    measured = [trade for trade in legs if trade.slippage_pct is not None]
    beyond = [
        trade.slippage_pct
        for trade in measured
        if trade.slippage_pct is not None and trade.slippage_pct > 0
    ]
    lines = [
        f"  stop-loss legs      : {len(legs)} ({len(measured)} with a matched placement)",
        f"  filled beyond trigger: {len(beyond)}",
    ]
    if beyond:
        lines.append(
            f"  beyond-trigger slippage: min {_fmt(min(beyond), 4, '%')}, "
            f"median {_fmt(median(beyond), 4, '%')}, max {_fmt(max(beyond), 4, '%')}"
        )
    worst = min(
        (trade for trade in measured if trade.exit_move_pct is not None),
        key=lambda trade: trade.exit_move_pct if trade.exit_move_pct is not None else Decimal(0),
        default=None,
    )
    if worst is not None:
        lines.append(
            f"  worst stop-loss exit: line {worst.booking.line_no}, exit "
            f"{_fmt(worst.exit_move_pct, 4, '%')} from the placement's entry limit against a "
            f"stop {_fmt(worst.stop_distance_pct, 4, '%')} below it; realised return "
            f"{_fmt(worst.return_pct, 4, '%')} of the booked entry total"
        )
    lines.append("  per leg (slippage is beyond the trigger, positive = worse than the stop):")
    for trade in legs:
        lines.append(
            f"    line {trade.booking.line_no:<6} {trade.booking.symbol:<8} stop "
            + (f"{trade.placement.stop_loss}" if trade.placement is not None else "n/a")
            + f" exit {_fmt(trade.exit_price, 8)} slippage {_fmt(trade.slippage_pct, 4, '%')} "
            f"stop distance {_fmt(trade.stop_distance_pct, 4, '%')} "
            f"exit move {_fmt(trade.exit_move_pct, 4, '%')}"
        )
    return lines


def restrict_until(trades: Sequence[Trade], until: datetime) -> tuple[tuple[Trade, ...], int]:
    """Keep the bookings made at or before ``until``; return them and how many were dropped.

    A booking whose time is unknown, a naive stamp with no inferred offset, is dropped
    and counted: a window cannot place a booking it cannot date.
    """
    kept = tuple(
        trade for trade in trades if trade.booked_at is not None and trade.booked_at <= until
    )
    return kept, len(trades) - len(kept)


def render(
    parsed: Parsed,
    trades: Sequence[Trade],
    *,
    path: Path,
    size: int,
    line_count: int,
    sha: str,
    fee_percent: Decimal,
    booked_placements: int,
    until: datetime | None = None,
    excluded: int = 0,
) -> list[str]:
    """The report, one string per line.

    ``booked_placements`` is the number of distinct placements any booking of the WHOLE
    capture matched, so a run restricted by ``until`` does not report the placements
    after the window as never booked.
    """
    rule = "=" * 74
    offset = infer_local_offset(parsed.bookings)
    out = [rule, "CAPTURE", rule]
    out += [f"  path   : {path}", f"  bytes  : {size}", f"  lines  : {line_count}"]
    out += [f"  sha256 : {sha}"]
    if offset is None:
        out.append("  naive-stamp offset : none inferred (no naive close_booked with candle_time)")
    else:
        out.append(
            f"  naive-stamp offset : {offset.offset} from {offset.lines_used} naive lines, "
            f"{offset.lines_agreeing} agreeing"
        )
    out += [
        f"  placements : {len(parsed.placements)}",
        f"  bookings   : {len(parsed.bookings)}",
        f"  anomalies  : {len(parsed.anomalies)}",
    ]
    if until is not None:
        out.append(
            f"  restricted to bookings at or before {until.strftime('%Y-%m-%dT%H:%M:%SZ')} : "
            f"kept {len(trades)}, excluded {excluded}"
        )
    matched = [trade for trade in trades if trade.placement is not None]
    out.append(f"  bookings matched to a placement : {len(matched)} of {len(trades)}")
    out.append(f"  placements never booked          : {len(parsed.placements) - booked_placements}")
    out.append(
        "  quantity differs from its placement : "
        f"{sum(1 for trade in trades if trade.quantity_matches is False)}"
    )

    out += [f"\n{rule}\nPER BOOKING  [sha256 {sha}]\n{rule}"]
    for number, trade in enumerate(trades, start=1):
        booked = (
            "n/a" if trade.booked_at is None else trade.booked_at.strftime("%Y-%m-%dT%H:%M:%SZ")
        )
        out.append(
            f"  {number:>4} line {trade.booking.line_no:<6} {booked} {trade.booking.symbol:<8} "
            f"{_label(trade):<7} held {_minutes(_hold(trade)):>6} "
            f"qty {trade.booking.quantity} realised {_fmt(trade.booking.realised, 4):>12} "
            f"return {_fmt(trade.return_pct, 4, '%'):>10} "
            f"{'unmatched' if trade.placement is None else 'placement line ' + str(trade.placement.line_no)}"
        )

    out += [f"\n{rule}\nTOTALS  [sha256 {sha}]\n{rule}"]
    closes = [trade for trade in trades if trade.route is Route.CLOSE]
    legs = [trade for trade in trades if trade.route is Route.LEG]
    out.append(
        f"  closes by CLOSE: {len(closes)}   by a protective leg: {len(legs)} "
        f"(SL {sum(1 for t in legs if t.leg is Leg.STOP_LOSS)}, "
        f"TP {sum(1 for t in legs if t.leg is Leg.TAKE_PROFIT)}, "
        f"unclassified {sum(1 for t in legs if t.leg is None)})"
    )
    out += _stats_lines("ALL BOOKINGS", trades, fee_percent)
    out += _stats_lines("STRATEGY CLOSES ONLY", closes, fee_percent)
    out += _stats_lines("PROTECTIVE LEGS ONLY", legs, fee_percent)

    out += [f"\n{rule}\nSTOP-LOSS SLIPPAGE  [sha256 {sha}]\n{rule}"]
    out += _slippage_lines(trades)

    out += [f"\n{rule}\nPER BOOKING DAY (UTC, by booking time)  [sha256 {sha}]\n{rule}"]
    per_day: dict[date | None, list[Decimal]] = defaultdict(list)
    for trade in trades:
        per_day[trade.booked_day].append(trade.booking.realised)
    for day in sorted(per_day, key=lambda item: (item is None, item or date.min)):
        figures = totals(per_day[day])
        out.append(
            f"  {'unattributed' if day is None else day.isoformat():<12} "
            f"bookings {figures.count:>3}  realised {_fmt(figures.realised, 4):>12}"
        )

    returnless = [trade for trade in trades if trade.return_pct is None]
    if returnless or parsed.anomalies:
        out += [f"\n{rule}\nEXCLUDED AND ANOMALOUS  [sha256 {sha}]\n{rule}"]
        for trade in returnless:
            out.append(
                f"  line {trade.booking.line_no}: no return, entry total {trade.entry_total_source}"
            )
        for anomaly in parsed.anomalies:
            out.append(f"  line {anomaly.line_no} {anomaly.event}: {anomaly.reason}")
    return out


def _non_negative_decimal(raw: str) -> Decimal:
    try:
        value = Decimal(raw)
    except InvalidOperation as exc:
        raise argparse.ArgumentTypeError(f"not a decimal: {raw!r}") from exc
    if not value.is_finite() or value < 0:
        raise argparse.ArgumentTypeError(f"must be a finite, non-negative decimal: {raw!r}")
    return value


def _utc_instant(raw: str) -> datetime:
    try:
        value = datetime.fromisoformat(raw)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"not an ISO timestamp: {raw!r}") from exc
    if value.tzinfo is None:
        raise argparse.ArgumentTypeError(f"carries no zone, write it as ...Z: {raw!r}")
    return value.astimezone(timezone.utc)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="trade_census.py",
        description="Census every booked trade in a frozen capture. Never reads the live log.",
    )
    parser.add_argument(
        "capture",
        type=Path,
        help="path to a frozen capture; a path under logs/ is refused",
    )
    parser.add_argument(
        "--fee-percent",
        type=_non_negative_decimal,
        default=Decimal("0.1"),
        help="commission in percent per side for the net mean; a round trip pays it twice",
    )
    parser.add_argument(
        "--quote-asset",
        default="USDT",
        help="the quote asset a booking's fee must be denominated in to enter a return",
    )
    parser.add_argument(
        "--until",
        type=_utc_instant,
        default=None,
        help="count only bookings made at or before this zoned instant, for example "
        "2026-09-24T03:58:40Z; placements are still matched over the whole capture",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    capture: Path = args.capture

    try:
        reject_live_log(capture)
    except CaptureRefusedError as exc:
        print(f"REFUSED: {exc}")
        return _REFUSED_EXIT

    if not capture.is_file():
        print(f"REFUSED: {capture} is not a file")
        return _REFUSED_EXIT

    size = capture.stat().st_size
    lines = capture.read_text(encoding="utf-8", errors="replace").splitlines()
    sha = digest_of(capture)
    parsed = parse_capture(lines)
    all_trades = build_trades(parsed, args.quote_asset)
    booked_placements = len(
        {trade.placement.line_no for trade in all_trades if trade.placement is not None}
    )
    trades, excluded = (
        (all_trades, 0) if args.until is None else restrict_until(all_trades, args.until)
    )
    for line in render(
        parsed,
        trades,
        path=capture,
        size=size,
        line_count=len(lines),
        sha=sha,
        fee_percent=args.fee_percent,
        booked_placements=booked_placements,
        until=args.until,
        excluded=excluded,
    ):
        print(line)
    return _ANOMALY_EXIT if parsed.anomalies else 0


if __name__ == "__main__":
    raise SystemExit(main())
