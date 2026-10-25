"""A small 1m world for the D1 executor and replay tests.

Not a test module (nothing here is collected). Every store is built through the real ``ingest_zip``
from a hand-written archive, one month, one row per bar. A minute is ``(open, high, low, close,
volume)`` as whole-number strings; any minute not named is a flat bar at the base price with volume 1,
and a minute in ``omit`` is not in the archive at all. Minute 0 is ``2024-03-01T00:00Z``. A decision
series (``4h`` or ``1d``) is aggregated from the minutes that exist, so a decision bar and the minutes
under it always agree, and a decision slot can be dropped on its own with ``omit_decisions``.
"""

from __future__ import annotations

import hashlib
import io
import json
import zipfile
from collections.abc import Mapping, Sequence
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from tests.unit.backtest_world import exchange_info
from trading_bot.backtesting.exchange_info import store_snapshot
from trading_bot.config.settings import Settings, get_settings
from trading_bot.core.enums import SignalAction
from trading_bot.core.models import Candle, Signal
from trading_bot.data.historical import HistoricalStore, ingest_zip, month_bounds_ms
from trading_bot.strategies.base import BaseStrategy

MONTH = "2024-03"
START_MS, _ = month_bounds_ms(MONTH)
MINUTE_MS = 60_000
STEP_MINUTES = {"1m": 1, "4h": 240, "1d": 1440}
T0 = datetime(2024, 3, 1, tzinfo=timezone.utc)

Minute = tuple[str, str, str, str, str]
TOUCH: Minute = ("100", "100", "94", "95", "1")


def at(minute: int) -> datetime:
    """The instant of ``minute`` minutes after the first of the month, UTC."""
    return T0 + timedelta(minutes=minute)


def flat(price: str, volume: str = "1") -> Minute:
    return (price, price, price, price, volume)


def _line(opened_ms: int, span_ms: int, row: Minute) -> str:
    open_, high, low, close, volume = row
    return (
        f"{opened_ms},{open_}.00000000,{high}.00000000,{low}.00000000,{close}.00000000,"
        f"{volume}.00000000,{opened_ms + span_ms - 1},100.00000000,1,0.50000000,50.00000000,0"
    )


def _ingest(root: Path, symbol: str, interval: str, rows: Mapping[int, Minute]) -> None:
    span_ms = STEP_MINUTES[interval] * MINUTE_MS
    lines = [_line(START_MS + index * span_ms, span_ms, rows[index]) for index in sorted(rows)]
    data = io.BytesIO()
    with zipfile.ZipFile(data, "w") as archive:
        archive.writestr(f"{symbol}-{interval}-{MONTH}.csv", "\n".join(lines) + "\n")
    raw = data.getvalue()
    ingest_zip(
        raw,
        expected_sha256=hashlib.sha256(raw).hexdigest(),
        root=root,
        symbol=symbol,
        interval=interval,
        month=MONTH,
        source_url=f"https://example.invalid/{symbol}-{interval}-{MONTH}.zip",
    )


def _aggregate(minutes: Mapping[int, Minute], size: int) -> dict[int, Minute]:
    grouped: dict[int, list[Minute]] = {}
    for index in sorted(minutes):
        grouped.setdefault(index // size, []).append(minutes[index])
    out: dict[int, Minute] = {}
    for slot, rows in grouped.items():
        out[slot] = (
            rows[0][0],
            str(max(int(r[1]) for r in rows)),
            str(min(int(r[2]) for r in rows)),
            rows[-1][3],
            str(sum(int(r[4]) for r in rows)),
        )
    return out


def build_minutes(
    root: Path,
    symbol: str,
    *,
    count: int,
    minutes: Mapping[int, Minute] | None = None,
    base: str = "100",
    omit: frozenset[int] = frozenset(),
    decision: str | None = None,
    omit_decisions: frozenset[int] = frozenset(),
) -> HistoricalStore:
    """Store ``count`` minutes of ``symbol``'s 1m series under ``root``, and a decision series
    aggregated from them when ``decision`` is ``"4h"`` or ``"1d"``; return the store."""
    named = dict(minutes or {})
    rows = {index: named.get(index, flat(base)) for index in range(count) if index not in omit}
    _ingest(root, symbol, "1m", rows)
    if decision is not None:
        bars = _aggregate(rows, STEP_MINUTES[decision])
        _ingest(root, symbol, decision, {s: r for s, r in bars.items() if s not in omit_decisions})
    return HistoricalStore(root)


def make_settings(
    tmp_path: Path,
    root: Path,
    *,
    pairs: Sequence[tuple[str, str]],
    strategy: str,
    params: Mapping[str, Any],
    start: str,
    end: str,
) -> Settings:
    """A backtest config over ``root`` with a snapshot of ``exchangeInfo`` per symbol: fixed-fraction
    sizing at 2 percent, every protective order off, the fee and slippage defaults."""
    for symbol in sorted({symbol for symbol, _ in pairs}):
        store_snapshot(root, "mainnet", symbol, exchange_info(symbol))
    pair_block = "".join(
        f"    - symbol: {symbol}\n      timeframe: {timeframe}\n      enabled: true\n"
        for symbol, timeframe in pairs
    )
    path = tmp_path / "d1_config.yaml"
    path.write_text(
        "mode: backtest\n"
        f"trading:\n  base_currency: USDT\n  pairs:\n{pair_block}"
        f"strategy:\n  name: {strategy}\n  params: {json.dumps(dict(params))}\n"
        "risk:\n"
        "  position_sizing:\n    method: fixed_fraction\n    fraction: 0.02\n"
        "  stop_loss:\n    enabled: false\n"
        "  take_profit:\n    enabled: false\n"
        "  trailing_stop:\n    enabled: false\n"
        "  max_position_staleness_s: 259200.0\n"
        "backtesting:\n"
        f"  start_date: '{start}'\n  end_date: '{end}'\n  data_dir: {root.as_posix()}\n"
        "logging:\n  console: false\n  file:\n    enabled: false\n",
        encoding="utf-8",
    )
    get_settings.cache_clear()
    return get_settings(str(path))


class ScriptedD1(BaseStrategy):
    """Emits ``BUY`` on the named decision bars, each carrying the D1 trail; declares the D1 exit."""

    name = "d1_scripted"
    declares_d1_exit = True

    def __init__(
        self, buy: dict[str, list[str]] | None = None, delta: int = 500, clamp: str = "none"
    ) -> None:
        super().__init__(buy=buy, delta=delta, clamp=clamp)
        self._buy = {symbol: set(times) for symbol, times in (buy or {}).items()}
        self._delta = delta
        self._clamp = clamp

    def generate_signal(self, symbol: str, candles: Any, *, last_candle: Candle) -> Signal | None:
        if last_candle.open_time.strftime("%Y-%m-%dT%H:%M") not in self._buy.get(symbol, set()):
            return None
        return Signal(
            symbol=symbol,
            action=SignalAction.BUY,
            timestamp=last_candle.close_time,
            price=last_candle.close,
            metadata={"trail_delta_bps": self._delta, "trail_clamp": self._clamp},
        )


class FixedD1(ScriptedD1):
    """The scripted strategy with a fixed schedule, for a caller that cannot hand it parameters."""

    name = "d1_fixed"

    def __init__(self) -> None:
        super().__init__(
            buy={
                "BTCUSDT": ["2024-03-01T00:00", "2024-03-01T04:00", "2024-03-02T00:00"],
                "ETHUSDT": ["2024-03-01T00:00"],
            }
        )


class BrokenD1(FixedD1):
    """A D1 strategy whose signals forget the trail, which the executor refuses."""

    def generate_signal(self, symbol: str, candles: Any, *, last_candle: Candle) -> Signal | None:
        found = super().generate_signal(symbol, candles, last_candle=last_candle)
        if found is None:
            return None
        return Signal(
            symbol=symbol,
            action=SignalAction.BUY,
            timestamp=last_candle.close_time,
            price=last_candle.close,
        )
