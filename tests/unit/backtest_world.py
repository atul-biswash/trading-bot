"""A small, real world for the backtest's end-to-end tests: a store, snapshots and a config.

Not a test module (nothing here is collected), and imported by the tests that need a world, so
no test module imports another. Every store is built through the real ``ingest_zip`` from a
hand-written archive, every ``exchangeInfo`` snapshot through the real ``store_snapshot``, and
every config through the real settings loader.

The price path is a seeded, mean-reverting random walk of integer prices around 100, one price
per hour for the 744 hours of March 2024, so SMA(3) and SMA(8) cross often and trades start,
stop out, reach their target and close on a signal. Seed 4 ends on a ``BUY`` signal with no bar
after it, which is the one entry that expires at the end of the data.
"""

from __future__ import annotations

import hashlib
import io
import json
import random
import zipfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from trading_bot.backtesting.exchange_info import store_snapshot
from trading_bot.config.settings import Settings, get_settings
from trading_bot.data.historical import ingest_zip, month_bounds_ms

HOUR = 3_600_000
HOUR_TD = timedelta(hours=1)
MONTH = "2024-03"
START_MS, _ = month_bounds_ms(MONTH)
EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)
CODE = {"install_kind": "test", "code_commit": "0" * 40, "checkout_dirty": False}
WINDOW_BARS = 21 * 24  # 2024-03-10 to 2024-03-31, half-open

# fmt: off
FILTERS: list[dict[str, Any]] = [
    {"filterType": "PRICE_FILTER",
     "minPrice": "0.01000000", "maxPrice": "1000000.00000000", "tickSize": "0.01000000"},
    {"filterType": "LOT_SIZE",
     "minQty": "0.00001000", "maxQty": "9000.00000000", "stepSize": "0.00001000"},
    {"filterType": "NOTIONAL",
     "minNotional": "5.00000000", "applyMinToMarket": True,
     "maxNotional": "9000000.00000000", "applyMaxToMarket": False, "avgPriceMins": 5},
]
# fmt: on


def at(hour: int) -> datetime:
    """The instant ``hour`` hours after the first of the month, UTC."""
    return EPOCH + timedelta(milliseconds=START_MS + hour * HOUR)


def exchange_info(symbol: str, *, quote: str = "USDT") -> bytes:
    entry = {
        "symbol": symbol,
        "status": "TRADING",
        "baseAsset": symbol[: -len(quote)],
        "quoteAsset": quote,
        "filters": FILTERS,
    }
    document = {"timezone": "UTC", "serverTime": 1_700_000_000_000, "symbols": [entry]}
    return json.dumps(document).encode("utf-8")


def walk(seed: int, hours: int = 744) -> list[int]:
    """A mean-reverting random walk of integer prices around 100, fixed by ``seed``."""
    rng = random.Random(seed)
    price = 100.0
    path = []
    for _ in range(hours):
        price += rng.gauss(0, 1.7) + (100 - price) * 0.04
        path.append(round(price))
    return path


PATH = walk(4)


def bar_line(hour: int, shift: int = 0) -> str:
    opened = START_MS + hour * HOUR
    price = PATH[hour] + shift
    return (
        f"{opened},{price}.00000000,{price + 1}.00000000,{price - 1}.00000000,"
        f"{price}.00000000,1.00000000,{opened + HOUR - 1},100.00000000,1,0.50000000,50.00000000,0"
    )


def store_series(
    root: Path,
    symbol: str,
    *,
    interval: str = "1h",
    omit: frozenset[int] = frozenset(),
    shift: int = 0,
) -> None:
    lines = [bar_line(h, shift) for h in range(744) if h not in omit]
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


def make_settings(
    tmp_path: Path,
    root: Path,
    *,
    pairs: tuple[tuple[str, str], ...] = (("BTCUSDT", "1h"),),
    base_currency: str = "USDT",
    start: str = "2024-03-10",
    end: str = "2024-03-31",
    file_logging: bool = False,
) -> Settings:
    """A config over ``root``. ``file_logging`` turns on the bot's own file sink, at the
    default relative path ``logs/trading_bot.log``, so a test can prove a command leaves it."""
    log_block = (
        "logging:\n  console: false\n  file:\n    enabled: true\n    path: logs/trading_bot.log\n"
        if file_logging
        else "logging:\n  console: false\n  file:\n    enabled: false\n"
    )
    pair_block = "".join(
        f"    - symbol: {symbol}\n      timeframe: {timeframe}\n      enabled: true\n"
        for symbol, timeframe in pairs
    )
    path = tmp_path / "bt_config.yaml"
    path.write_text(
        "mode: testnet\n"
        f"trading:\n  base_currency: {base_currency}\n  pairs:\n{pair_block}"
        "strategy:\n  name: sma_crossover\n  params:\n    fast_period: 3\n    slow_period: 8\n"
        "risk:\n"
        "  position_sizing:\n    method: fixed_fraction\n    fraction: 0.02\n"
        "  stop_loss:\n    enabled: true\n    type: percent\n    percent: 2.0\n"
        "  take_profit:\n    enabled: true\n    type: percent\n    percent: 4.0\n"
        "  max_position_staleness_s: 10800\n"
        "  reconcile_deadline_s: 2.3\n"
        "backtesting:\n"
        f"  start_date: '{start}'\n  end_date: '{end}'\n  data_dir: {root.as_posix()}\n"
        + log_block,
        encoding="utf-8",
    )
    get_settings.cache_clear()
    return get_settings(str(path))


def build_world(
    tmp_path: Path,
    *,
    omit: frozenset[int] = frozenset(),
    symbols: tuple[str, ...] = ("BTCUSDT",),
    file_logging: bool = False,
) -> Settings:
    """A store of every symbol's March, a mainnet snapshot for each, and a config naming them."""
    root = tmp_path / "hist"
    for index, symbol in enumerate(symbols):
        store_series(root, symbol, omit=omit, shift=index)
        store_snapshot(root, "mainnet", symbol, exchange_info(symbol))
    return make_settings(
        tmp_path,
        root,
        pairs=tuple((symbol, "1h") for symbol in symbols),
        file_logging=file_logging,
    )
