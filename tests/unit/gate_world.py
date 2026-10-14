"""Builders for the S7 gate tests (not a test module; nothing here is collected).

``make_oos_run`` writes one out-of-sample run directory the way the engine writes one (a schema-6
``run.json`` that passes the evidence door and a ``trades.csv``), with every field the gate reads set by a
keyword so a test can break exactly one. ``build_candidate`` writes a candidate's three arms and the entry
that committed them, and returns the parsed entry with the body it was parsed from so a test can edit the
body and parse it again.

The default candidate PASSES: at the gate arm 300 wins of +20 and 100 losses of -10 on a quote of 1,000 (a
return profit factor of 2 x 300 / 100 = 6, the same in USDT), 400 trades, a per-bar drawdown of 0.10, and
regime net results rising +100, falling -50, sideways +30 (two of three positive).
"""

from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path
from typing import Any

from tests.unit.protocol_world import PROTOCOL, PROTOCOL_TEXT, effective
from trading_bot.backtesting import gate
from trading_bot.backtesting.candidate import candidate_digest, settings_digest
from trading_bot.backtesting.protocol import Entry, parse_entry

GATE_RULES = gate.parse_gate_rules(PROTOCOL_TEXT)
ENTRY_ID = "s6-sma_crossover-1h-off"
VARIANT: dict[str, Any] = {
    "family": "sma_crossover",
    "timeframe": "1h",
    "filtered": False,
    "params": {"fast_period": "10", "slow_period": "50"},
}
ARMS = ("0.05", "0.66", "1.2")
ENTRY_KEYS = {"0.05": "0.05", "0.66": "0.66", "1.2": "1.20"}
REGIME_NET = {"rising": "100", "falling": "-50", "sideways": "30"}


def candidate_effective(arm: str) -> dict[str, Any]:
    return effective(
        name="sma_crossover",
        params={"fast_period": 10, "slow_period": 50},
        timeframe="1h",
        arm=arm,
    )


def make_oos_run(root: Path, name: str, *, arm: str = "1.2", **over: Any) -> Path:
    """One out-of-sample run directory; ``over`` overrides any field the gate reads (see the body)."""
    wins, losses = over.get("wins", 300), over.get("losses", 100)
    rows = [("BTCUSDT" if i % 2 == 0 else "ETHUSDT", "20") for i in range(wins)] + [
        ("BTCUSDT" if i % 2 == 0 else "ETHUSDT", "-10") for i in range(losses)
    ]
    eff = candidate_effective(arm)
    balance = over.get("balances", {})
    regime_net = over.get("regime_net", REGIME_NET)
    record: dict[str, Any] = {
        "schema": over.get("schema", 6),
        "evidence_eligible": over.get("flag", True),
        "provenance": {"verdict": "accepted"},
        "window": over.get(
            "window",
            {
                "start_date": "2024-01-01",
                "end_date": "2026-10-01",
                "start": "2024-01-01T00:00:00+00:00",
                "end": "2026-10-01T00:00:00+00:00",
            },
        ),
        "effective": eff,
        "candidate_digest": over.get("candidate_digest", candidate_digest(eff)),
        "settings_digest": settings_digest(eff),
        "protocol": over.get(
            "protocol",
            {
                "window_class": over.get("window_class", "out_of_sample"),
                "kind": over.get("kind", "candidate"),
                "entry_id": over.get("entry_id", ENTRY_ID),
                "protocol_sha256": over.get("protocol_sha", PROTOCOL.sha256),
                "arm": arm,
                "variant": over.get("variant", VARIANT),
            },
        ),
        "fill_parameters": {"initial_balance": balance.get("fill", "10000.0")},
        "equity": {"initial": balance.get("equity", "10000"), "daily_closes": {}},
        "metrics": {
            "initial_balance": balance.get("metrics", "10000.0"),
            "max_drawdown": over.get("drawdown", "0.10"),
            "overall": {
                "trades": over.get("counted", len(rows)),
                "profit_factor_net": over.get("usdt", "6"),
            },
            "by_regime": {
                **{k: {"trades": 10, "net_pnl": v} for k, v in regime_net.items()},
                "unlabelled": {"trades": over.get("unlabelled", 0), "net_pnl": "0"},
            },
            "by_pair": over.get(
                "by_pair",
                {
                    "BTCUSDT": {"trades": 200, "net_pnl": "60"},
                    "ETHUSDT": {"trades": 200, "net_pnl": "20"},
                },
            ),
        },
        "results": {"trades": over.get("declared", len(rows)), "trade_log_sha256": "e" * 64},
        "problems": over.get("problems", []),
        "error_log_records": {"count": over.get("errors", 0), "first": []},
        "stream": {"handler_failures": over.get("failures", 0)},
        "regime_labels": {"sha256": over.get("labels", PROTOCOL.regime_labels_sha256)},
        "code": {"code_commit": over.get("code_commit", "c" * 40)},
        "config": {"sha256": over.get("config_sha", "d" * 64)},
        "exchange_info": over.get("exchange_info", {"BTCUSDT": {"sha256": "1" * 64}}),
    }
    if "costs_balance" in balance:
        record["effective"]["costs"]["initial_balance"] = balance["costs_balance"]
        record["candidate_digest"] = over.get(
            "candidate_digest", candidate_digest(record["effective"])
        )
        record["settings_digest"] = settings_digest(record["effective"])
    directory = root / name
    directory.mkdir()
    (directory / "run.json").write_text(
        json.dumps(record, sort_keys=True), encoding="utf-8", newline="\n"
    )
    with (directory / "trades.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(
            [
                "symbol", "entry_bar_open", "exit_time", "entry_notional", "entry_fee",
                "entry_quote_total", "exit_gross", "exit_fee", "realised",
            ]
        )  # fmt: skip
        for symbol, realised in rows if "csv_rows" not in over else rows[: over["csv_rows"]]:
            writer.writerow(
                [symbol, "2024-03-01T00:00:00+00:00", "2024-03-01T01:00:00+00:00", "1000", "0", "1000",
                 str(1000 + int(realised)), "0", realised]
            )  # fmt: skip
    return directory


def build_candidate(
    root: Path,
    *,
    per_arm: dict[str, dict[str, Any]] | None = None,
    common: dict[str, Any] | None = None,
    entry: dict[str, Any] | None = None,
) -> tuple[Entry, Path, dict[str, Any]]:
    """A candidate's three arms in ``root/backtests`` and the entry that committed them.

    ``per_arm`` overrides one arm's fields (keyed by the canonical arm: ``"1.2"``), ``common`` all three,
    ``entry`` the entry's body. Returns the parsed entry, the backtests directory and the body.
    """
    backtests = root / "backtests"
    backtests.mkdir(parents=True, exist_ok=True)
    records: dict[str, Any] = {}
    for index, arm in enumerate(ARMS):
        fields = {**(common or {}), **((per_arm or {}).get(arm, {}))}
        name = f"20260101T00000{index}000000Z-{arm.replace('.', 'p')}"
        directory = make_oos_run(backtests, name, arm=arm, **fields)
        digest = hashlib.sha256((directory / "run.json").read_bytes()).hexdigest()
        records[ENTRY_KEYS[arm]] = {"run": name, "run_json_sha256": digest}
    body: dict[str, Any] = {
        "entry_schema": 1,
        "id": ENTRY_ID,
        "kind": "candidate",
        "ref": "sma_crossover",
        "candidate_digest": candidate_digest(candidate_effective("1.2")),
        "arms": [ENTRY_KEYS[a] for a in ARMS],
        "status": "read",
        "oos": {"records": records},
        "selection": {"variant": VARIANT},
    }
    body.update(entry or {})
    return parse_entry(json.dumps(body)), backtests, body
