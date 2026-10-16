#!/usr/bin/env python
"""Inventory and verify a historical store root. READ-ONLY; writes only its own inventory file (M5m P124, R-DE).

Usage:

    .venv\\Scripts\\python.exe scripts\\store_check.py STORE_ROOT INVENTORY_OUTPUT.jsonl

R-DE, verbatim: *"The store checker used by the S4 stop is a tracked, tested script under scripts/. The runbook names it
and its digest; nothing in an evidence procedure runs from scratch."* This is the P113 scratch script
(``F:\\trading bot\\scratch\\p113\\store_check.py``, SHA-256 ``2a5b5530f525b69485f13141db1d73692760cb418203d1be4c7defa581827592``,
used at RUN_LEDGER section 48) moved under ``scripts/`` with the same behaviour: the same checks, the same output lines
in the same order and the same inventory file, byte for byte. ``tests/unit/test_store_check.py`` pins that, and
RUN_LEDGER section 61 shows the two outputs equal on the mainnet store and on a copy of the recorder's Testnet store.

For every file under the root except ``_zips``: its relative path, size and SHA-256, written to the inventory file one JSON
line each. Then, per series (``BTCUSDT`` and ``ETHUSDT`` at ``1m``, ``5m``, ``1h``, ``4h`` and ``1d``), every CSV month
against its ``MANIFEST.jsonl`` ``csv_sha256`` (missing, extra, mismatched), the deep ``HistoricalStore.verify`` result,
and every ``_exchange_info`` snapshot against its ``.sha256``. Finally one digest of the whole inventory, so two roots are
compared by a single value. A series with no manifest prints ``NO MANIFEST`` and is skipped, which is what a Testnet
store (only ``1m`` and ``5m``) does for the other three intervals.

The exit status is 0 only when nothing is mismatched, missing or extra, no series reports a problem and no snapshot
disagrees with its sidecar; otherwise 1.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from collections.abc import Sequence
from pathlib import Path
from typing import Final

from trading_bot.data.historical import HistoricalStore

SYMBOLS: Final = ("BTCUSDT", "ETHUSDT")
INTERVALS: Final = ("1m", "5m", "1h", "4h", "1d")
_BLOCK: Final = 1 << 20


def sha256_of(path: Path) -> str:
    """The SHA-256 of ``path``, read in 1 MiB blocks."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(_BLOCK), b""):
            digest.update(block)
    return digest.hexdigest()


def build_inventory(root: Path) -> dict[str, tuple[int, str]]:
    """Relative path (POSIX form) to (size, SHA-256) for every file under ``root`` except ``_zips``."""
    files = sorted(
        p for p in root.rglob("*") if p.is_file() and "_zips" not in p.relative_to(root).parts
    )
    return {p.relative_to(root).as_posix(): (p.stat().st_size, sha256_of(p)) for p in files}


def inventory_digest(inventory: dict[str, tuple[int, str]]) -> str:
    """One SHA-256 over every ``path size sha256`` line, in the inventory's (sorted) order."""
    lines = [f"{rel} {size} {digest}" for rel, (size, digest) in inventory.items()]
    return hashlib.sha256("\n".join(lines).encode("utf-8")).hexdigest()


def write_inventory(path: Path, inventory: dict[str, tuple[int, str]]) -> None:
    """The inventory file: one ``{"path", "size", "sha256"}`` JSON line per file, LF-terminated."""
    path.write_text(
        "".join(
            json.dumps({"path": rel, "size": size, "sha256": digest}) + "\n"
            for rel, (size, digest) in inventory.items()
        ),
        encoding="utf-8",
        newline="\n",
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="store_check.py",
        description="Inventory and verify a historical store root. Read only; writes the inventory file.",
    )
    parser.add_argument("root", type=Path, help="the store root")
    parser.add_argument(
        "inventory", type=Path, help="where to write the per-file inventory (JSON lines)"
    )
    args = parser.parse_args(argv)
    root: Path = args.root

    inventory = build_inventory(root)
    write_inventory(args.inventory, inventory)
    csvs = [rel for rel in inventory if rel.endswith(".csv")]
    print(f"root                 : {root}")
    print(f"files (no _zips)     : {len(inventory)}")
    print(f"csv months           : {len(csvs)}")
    print(f"bytes                : {sum(size for size, _ in inventory.values())}")
    print(f"inventory sha256     : {inventory_digest(inventory)}")

    listed: set[str] = set()
    mismatched: list[str] = []
    rows: dict[str, int] = {}
    manifests = 0
    for symbol in SYMBOLS:
        for interval in INTERVALS:
            manifest = root / symbol / interval / "MANIFEST.jsonl"
            if not manifest.is_file():
                print(f"NO MANIFEST          : {symbol} {interval}")
                continue
            manifests += 1
            total = 0
            for text in manifest.read_text(encoding="utf-8").splitlines():
                entry = json.loads(text)
                listed.add(entry["file"])
                total += entry["rows"]
                have = inventory.get(entry["file"])
                if have is None or have[1] != entry["csv_sha256"]:
                    mismatched.append(entry["file"])
            rows[f"{symbol} {interval}"] = total
    missing = sorted(listed - set(csvs))
    extra = sorted(set(csvs) - listed)
    print(f"manifests            : {manifests}")
    print(f"months listed        : {len(listed)}")
    print(f"mismatched vs manifest: {len(mismatched)} {mismatched[:3]}")
    print(f"missing / extra csv  : {len(missing)} / {len(extra)}")
    print(f"rows BTCUSDT 1m      : {rows.get('BTCUSDT 1m')}")
    print(f"rows ETHUSDT 5m      : {rows.get('ETHUSDT 5m')}")

    store = HistoricalStore(root)
    problems = 0
    for symbol in SYMBOLS:
        for interval in INTERVALS:
            if (root / symbol / interval / "MANIFEST.jsonl").is_file():
                found = store.verify(symbol, interval)
                problems += len(found)
                if found:
                    print(f"PROBLEMS {symbol} {interval}: {found[:2]}")
    print(f"verify problems      : {problems}")

    bad_snapshots = 0
    snapshots = 0
    for sidecar in sorted((root / "_exchange_info").rglob("*.sha256")):
        snapshots += 1
        target = sidecar.with_suffix("")
        expected = sidecar.read_text(encoding="ascii").split()[0]
        if sha256_of(target) != expected:
            bad_snapshots += 1
    print(f"snapshots checked    : {snapshots}, mismatched {bad_snapshots}")

    print("-- digests of the descriptive files --")
    for rel in sorted(inventory):
        if rel.endswith((".jsonl", ".json", ".sha256")):
            print(f"{inventory[rel][1]}  {rel}")
    return 0 if not (mismatched or missing or extra or problems or bad_snapshots) else 1


if __name__ == "__main__":  # pragma: no cover - CLI entry point
    raise SystemExit(main())
