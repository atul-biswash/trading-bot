"""Builders shared by the ``scripts/s4_daily.py`` test modules: log lines as the bot writes them, and the
instants the S4 run is measured against. A module of its own, so that neither test module imports another."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from trading_bot.engine.live_engine import _EVENT_STOPPED

UTC = timezone.utc
T0 = datetime(2026, 10, 10, 6, 5, 20, tzinfo=UTC)
REPO = Path(__file__).resolve().parents[2]
RUN_CMD = r'"F:\trading bot\deploy\45547f107715\.venv\Scripts\python.exe" -m trading_bot run'


def at(text: str) -> datetime:
    return datetime.fromisoformat(text.replace("Z", "+00:00"))


def line(stamp: str, pid: int, logger: str, message: str, level: str = "INFO") -> str:
    return f"{stamp} | {level:<8} | pid={pid} | {logger} | {message}"


def provenance(stamp: str, pid: int, verdict: str = "accepted") -> str:
    return line(
        stamp,
        pid,
        "trading_bot.main",
        f"Startup provenance accepted event=boot_provenance verdict={verdict} refusal_reasons=none",
    )


def starting(stamp: str, pid: int) -> str:
    return line(stamp, pid, "trading_bot.main", "Starting in TESTNET mode")


def booked(stamp: str, pid: int, order_id: str, event: str = "close_booked") -> str:
    return line(
        stamp,
        pid,
        "trading_bot.execution.executor",
        f"Closed BTCUSDT event={event} symbol=BTCUSDT order_id={order_id} quantity=1 "
        "quote_total=101 realised=1 candle_time=2026-10-11T01:00:59.999000+00:00",
    )


def stopped(stamp: str, pid: int) -> str:
    return line(
        stamp,
        pid,
        "trading_bot.engine.live_engine",
        f"Trading engine stopped event={_EVENT_STOPPED} clean_shutdown=True",
    )


def write_log(path: Path, lines: list[str]) -> None:
    path.write_bytes(("\r\n".join(lines) + "\r\n").encode("utf-8"))


NOW = at("2026-10-16T05:30:00Z")
