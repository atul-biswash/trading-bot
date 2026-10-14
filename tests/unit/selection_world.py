"""Builders shared by the selection tests (not a test module; nothing here is collected).

``at`` and ``trade`` make a trade of the shape ``metrics.TradeFacts`` has; ``bulk`` makes many at a quote of
100 so that returns and USDT agree; ``point`` makes one variant's run; ``full_ledger`` makes the 216-run
ledger a finished sweep would leave; ``with_selection`` edits the real declaration to drive the refusals of
``parse_rules``. The rules are read from the REAL ``PROTOCOL.md``, so the numbers the owner ruled cannot
drift from the code that applies them.
"""

from __future__ import annotations

import csv
import dataclasses
import hashlib
import json
from dataclasses import replace
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any

from tests.unit.protocol_world import PROTOCOL, PROTOCOL_TEXT, effective
from trading_bot.backtesting import selection as sel
from trading_bot.backtesting.candidate import candidate_digest, settings_digest
from trading_bot.backtesting.engine import RUN_RECORD_SCHEMA
from trading_bot.backtesting.metrics import TradeFacts
from trading_bot.backtesting.protocol import Variant
from trading_bot.backtesting.simulated_executor import SimulatedTrade

D = Decimal
UTC = timezone.utc
RULES = sel.parse_rules(PROTOCOL_TEXT)
BEGIN, END = "<!-- protocol-json:begin -->", "<!-- protocol-json:end -->"


# --------------------------------------------------------------------------------------
# Builders
# --------------------------------------------------------------------------------------
def at(text: str) -> datetime:
    return datetime.fromisoformat(text).replace(tzinfo=UTC)


def trade(entry: str, realised: str, quote: str = "100") -> TradeFacts:
    return TradeFacts(
        symbol="BTCUSDT",
        entry_time=at(entry),
        exit_time=at(entry) + timedelta(hours=1),
        entry_notional=D(quote),
        entry_fee=D(0),
        entry_quote_total=D(quote),
        exit_gross=D(quote) + D(realised),
        exit_fee=D(0),
        realised=D(realised),
    )


def bulk(wins: int, losses: int, win: str = "2", loss: str = "-1") -> tuple[TradeFacts, ...]:
    """``wins`` + ``losses`` trades on a quote of 100, hourly from 2018-01-01, wins first."""
    out: list[TradeFacts] = []
    start = at("2018-01-01T00:00:00")
    for index in range(wins + losses):
        out.append(
            trade((start + timedelta(hours=index)).isoformat(), win if index < wins else loss)
        )
    return tuple(out)


def variant_for(index: int = 0, **changes: Any) -> Variant:
    base = list(PROTOCOL.variants())[index]
    return replace(base, **changes) if changes else base


def point(
    variant: Variant,
    trades: tuple[TradeFacts, ...],
    *,
    run: str | None = None,
    drawdown: str = "0.5",
    usdt: str | None = "1.0",
    log: str = "a",
    closes: tuple[tuple[date, Decimal], ...] = (),
) -> sel.PointRun:
    key = abs(hash(sel.variant_key(variant))) % 10**12
    return sel.PointRun(
        variant=variant,
        run=run or f"20260101T000000000000Z-{key:012d}",
        record_sha256=hashlib.sha256(f"{run}{key}".encode()).hexdigest(),
        candidate_digest=hashlib.sha256(f"digest{key}".encode()).hexdigest(),
        trade_log_sha256=log * 64,
        trades=trades,
        max_drawdown=D(drawdown),
        usdt_profit_factor=None if usdt is None else D(usdt),
        initial_balance=D(10000),
        daily_closes=closes,
    )


def full_ledger(
    special: dict[sel.VariantKey, tuple[TradeFacts, ...]] | None = None,
    default: tuple[TradeFacts, ...] | None = None,
) -> sel.Ledger:
    """One run for each of the 216 declared variants; ``special`` overrides some trades."""
    shared = default if default is not None else bulk(300, 100)
    found = [
        point(v, (special or {}).get(sel.variant_key(v), shared), run=f"r{i:03d}")
        for i, v in enumerate(PROTOCOL.variants())
    ]
    return sel.reconcile(PROTOCOL, found)


GRID = Variant("sma_crossover", "1h", False, {"fast_period": "10", "slow_period": "50"})
CLOSES = {"2017-08-17": "10000", "2020-01-01": "12000", "2023-12-31": "9000"}


def make_run(
    root: Path,
    name: str = "20260101T000000000000Z-aaaaaaaaaaaa",
    *,
    variant: Variant = GRID,
    **over: Any,
) -> Path:
    """A run directory written the way the engine writes one: ``run.json`` and ``trades.csv``.

    ``over`` overrides: ``arm``, ``timeframe``, ``rows`` (``(symbol, entry, realised)`` triples), ``protocol``
    (the whole block, or ``None``), ``schema``, ``flag`` (``evidence_eligible``), ``window``, ``problems``,
    ``declared`` (the trade count the record claims), ``drawdown`` and ``log`` (the trade-log digest).
    """
    eff = effective(
        name=variant.family,
        params=dict(variant.params),
        timeframe=over.get("timeframe", variant.timeframe),
        arm=over.get("arm", "1.2"),
    )
    rows = over.get(
        "rows",
        [
            ("BTCUSDT", "2018-03-01T00:00:00+00:00", "10"),
            ("ETHUSDT", "2018-04-01T00:00:00+00:00", "-4"),
        ],
    )
    protocol_block: Any = over.get(
        "protocol",
        {
            "window_class": "in_sample",
            "protocol_sha256": over.get("protocol_sha", PROTOCOL.sha256),
            "arm": over.get("arm", "1.2"),
            "variant": {
                "family": variant.family,
                "timeframe": variant.timeframe,
                "filtered": variant.filtered,
                "params": dict(variant.params),
            },
        },
    )
    record: dict[str, Any] = {
        "schema": over.get("schema", RUN_RECORD_SCHEMA),
        "evidence_eligible": over.get("flag", True),
        "provenance": {"verdict": "accepted"},
        "window": over.get("window", {"start_date": "2017-08-17", "end_date": "2024-01-01"}),
        "effective": eff,
        "candidate_digest": candidate_digest(eff),
        "settings_digest": settings_digest(eff),
        "protocol": protocol_block,
        "results": {
            "trades": over.get("declared", len(rows)),
            "trade_log_sha256": over.get("log", "e" * 64),
        },
        "equity": {"initial": "10000", "daily_closes": CLOSES},
        "metrics": {
            "max_drawdown": over.get("drawdown", "0.31"),
            "overall": {"profit_factor_net": "0.8"},
        },
        "problems": over.get("problems", []),
    }
    directory = root / name
    directory.mkdir()
    (directory / "run.json").write_text(
        json.dumps(record, sort_keys=True), encoding="utf-8", newline="\n"
    )
    names = [field.name for field in dataclasses.fields(SimulatedTrade)]
    with (directory / "trades.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=names, lineterminator="\n")
        writer.writeheader()
        for symbol, entry, realised in rows:
            gross = D(1000) + D(realised)
            writer.writerow(
                dict.fromkeys(names, "0")
                | {
                    "symbol": symbol,
                    "entry_bar_open": entry,
                    "exit_time": entry,
                    "entry_notional": "1000",
                    "entry_quote_total": "1000",
                    "exit_gross": str(gross),
                    "realised": realised,
                }
            )
    return directory


def with_selection(change: Any) -> str:
    """``PROTOCOL.md`` with its declaration edited by ``change(data)``."""
    head, rest = PROTOCOL_TEXT.split(BEGIN, 1)
    body, tail = rest.split(END, 1)
    data = json.loads(body.strip()[len("```json") : -len("```")])
    change(data)
    return head + BEGIN + "\n```json\n" + json.dumps(data, indent=2) + "\n```\n" + END + tail
