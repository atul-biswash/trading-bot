"""A stand-in for ``python -m trading_bot backtest`` that the sweep tests launch as a real subprocess.

Not a test module (nothing here is collected). It takes the flags the sweep builds, and writes into
``$FAKE_BACKTESTS`` the directory the real command writes: a schema-6 ``run.json`` that passes the evidence
door (the digests are made with the repository's own ``candidate`` functions) and a ``trades.csv`` of two
trades, named ``<stamp>-<trade log digest, 12 characters>``. It imports only the light ``candidate`` module,
so a launch costs a fraction of a second.

``$FAKE_MODE`` is a comma-separated list of: ``slow`` (sleep 0.4 s so two launches overlap), ``nondeterministic``
(the trade-log digest depends on the process id and the clock, so two runs of one variant disagree),
``fail_after=K`` (once K sealed runs exist, leave ``<stamp>-failed`` with no record and exit 1),
``noseal`` (leave the record in ``<stamp>-running`` and exit 0: a power cut between the record and the rename)
and ``crash=TEXT`` (exit 1 with no directory when TEXT is in the variant's label).
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import sys
import time
from decimal import Decimal
from pathlib import Path

sys.path[:0] = [str(Path(__file__).resolve().parents[2] / "src")]

from trading_bot.backtesting.candidate import (  # noqa: E402
    candidate_digest,
    canonical_number,
    canonical_value,
    settings_digest,
)

COLUMNS = (
    "symbol",
    "entry_bar_open",
    "exit_time",
    "entry_notional",
    "entry_fee",
    "entry_quote_total",
    "exit_gross",
    "exit_fee",
    "realised",
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("command")
    parser.add_argument("--start", required=True)
    parser.add_argument("--end", required=True)
    parser.add_argument("--stop-slippage", required=True)
    parser.add_argument("--strategy", required=True)
    parser.add_argument("--timeframe", required=True)
    parser.add_argument("--param", action="append", default=[])
    args = parser.parse_args()
    backtests = Path(os.environ["FAKE_BACKTESTS"])
    modes = [m for m in os.environ.get("FAKE_MODE", "").split(",") if m]
    backtests.mkdir(parents=True, exist_ok=True)

    params = {}
    for text in args.param:
        key, value = text.split("=", 1)
        params[key] = json.loads(value)
    label = f"{args.strategy}-{args.timeframe}-" + "-".join(
        f"{k}{v}" for k, v in sorted(params.items())
    )
    stamp = f"{time.time_ns()}"
    for mode in modes:
        if mode.startswith("crash=") and mode[len("crash=") :] in label:
            return 1
        if mode.startswith("fail_after="):
            sealed = [
                p
                for p in backtests.iterdir()
                if p.is_dir() and not p.name.endswith(("-running", "-failed"))
            ]
            if len(sealed) >= int(mode.split("=", 1)[1]):
                failed = backtests / f"{stamp}-failed"
                failed.mkdir()
                (failed / "backtest.log").write_text(
                    "Backtest aborted: simulated power cut\n", encoding="ascii"
                )
                return 1
    if "slow" in modes:
        time.sleep(0.4)

    arm = canonical_number(Decimal(args.stop_slippage))
    effective = {
        "config_sha256": "a" * 64,
        "strategy": {"name": args.strategy, "params": canonical_value(params)},
        "pairs": [
            {"symbol": "BTCUSDT", "timeframe": args.timeframe},
            {"symbol": "ETHUSDT", "timeframe": args.timeframe},
        ],
        "risk": {"max_position_staleness_s": "57600"},
        "exchange_info_environment": "mainnet",
        "costs": {
            "fee_percent": "0.1",
            "slippage_percent": "0.05",
            "stop_slippage_percent": arm,
            "initial_balance": "10000",
        },
        "overrides": {},
    }
    salt = f"|{os.getpid()}|{time.time_ns()}" if "nondeterministic" in modes else ""
    log_digest = hashlib.sha256((label + salt).encode("ascii")).hexdigest()
    record = {
        "schema": 6,
        "evidence_eligible": True,
        "provenance": {"verdict": "accepted"},
        "window": {"start_date": args.start, "end_date": args.end},
        "effective": effective,
        "candidate_digest": candidate_digest(effective),
        "settings_digest": settings_digest(effective),
        "protocol": {
            "window_class": "in_sample",
            "arm": arm,
            "variant": {
                "family": args.strategy,
                "timeframe": args.timeframe,
                "filtered": "trend_filter_period" in params,
                "params": canonical_value(params),
            },
        },
        "results": {"trades": 2, "trade_log_sha256": log_digest},
        "equity": {"initial": "10000", "daily_closes": {"2017-08-17": "10000"}},
        "metrics": {"max_drawdown": "0.1", "overall": {"profit_factor_net": "1.0"}},
        "problems": [],
    }
    name = f"{stamp}-running" if "noseal" in modes else f"{stamp}-{log_digest[:12]}"
    directory = backtests / name
    directory.mkdir()
    (directory / "run.json").write_text(
        json.dumps(record, sort_keys=True), encoding="utf-8", newline="\n"
    )
    with (directory / "trades.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(COLUMNS)
        for symbol, realised in (("BTCUSDT", "10"), ("ETHUSDT", "-5")):
            writer.writerow(
                [
                    symbol,
                    "2018-03-01T00:00:00+00:00",
                    "2018-03-01T01:00:00+00:00",
                    "1000",
                    "0",
                    "1000",
                    str(1000 + int(realised)),
                    "0",
                    realised,
                ]
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
