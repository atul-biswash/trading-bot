"""The research protocol's test world: the REAL declaration and the builders both protocol test modules share.

Not a test module (nothing here is collected). ``PROTOCOL`` is the committed ``docs/research/PROTOCOL.md``
parsed, so a test against it fails if the file and the code part company; the builders write an
effective-settings block and a research-entry file the way ``candidate.py`` and PROTOCOL.md section 8 do.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any

from trading_bot.backtesting.candidate import candidate_digest, canonical_value
from trading_bot.backtesting.protocol import Entry, parse_entry, parse_protocol

REPO = Path(__file__).resolve().parents[2]
PROTOCOL_TEXT = (REPO / "docs" / "research" / "PROTOCOL.md").read_text(encoding="utf-8")
PROTOCOL = parse_protocol(PROTOCOL_TEXT)
BOUNDARY = date(2024, 1, 1)
HISTORY_END = date(2026, 10, 1)
OOS = (BOUNDARY, HISTORY_END)
FULL = (date(2017, 8, 17), HISTORY_END)


# --------------------------------------------------------------------------------------
# Builders
# --------------------------------------------------------------------------------------
def effective(
    name: str = "sma_crossover",
    params: dict[str, object] | None = None,
    *,
    timeframe: str = "4h",
    pairs: tuple[str, ...] = ("BTCUSDT", "ETHUSDT"),
    arm: str = "1.2",
    fee: str = "0.1",
    slippage: str = "0.05",
    balance: str = "10000",
    environment: str = "mainnet",
    timeframes: tuple[str, ...] | None = None,
) -> dict[str, Any]:
    """An effective-settings block as ``effective_settings`` writes one, by hand."""
    chosen = {"fast_period": 20, "slow_period": 100} if params is None else params
    frames = timeframes if timeframes is not None else tuple(timeframe for _ in pairs)
    return {
        "config_sha256": "a" * 64,
        "strategy": {"name": name, "params": canonical_value(chosen)},
        "pairs": [
            {"symbol": symbol, "timeframe": frame}
            for symbol, frame in zip(pairs, frames, strict=True)
        ],
        "risk": {"max_position_staleness_s": "57600"},
        "exchange_info_environment": environment,
        "costs": {
            "fee_percent": fee,
            "slippage_percent": slippage,
            "stop_slippage_percent": arm,
            "initial_balance": balance,
        },
        "overrides": {},
    }


def baseline_effective(arm: str = "1.2") -> dict[str, Any]:
    return effective(
        params={"fast_period": 20, "slow_period": 50},
        pairs=("BTCUSDT", "ETHUSDT"),
        timeframes=("1m", "5m"),
        arm=arm,
    )


def entry_text(
    eff: dict[str, Any],
    *,
    entry_id: str = "e1",
    kind: str = "candidate",
    ref: str = "sma_crossover",
    status: str = "pending",
    arms: tuple[str, ...] = ("0.05", "0.66", "1.20"),
    oos: object = None,
) -> str:
    body: dict[str, Any] = {
        "entry_schema": 1,
        "id": entry_id,
        "kind": kind,
        "ref": ref,
        "candidate_digest": candidate_digest(eff),
        "arms": list(arms),
        "status": status,
        "oos": oos,
    }
    return json.dumps(body, indent=2) + "\n"


def entry_for(eff: dict[str, Any], **kwargs: Any) -> Entry:
    return parse_entry(entry_text(eff, **kwargs))


CANDIDATE = effective()
OFF_GRID = effective(params={"fast_period": 15, "slow_period": 100})
