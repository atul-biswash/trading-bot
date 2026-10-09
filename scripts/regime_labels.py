#!/usr/bin/env python
"""Label every calendar quarter by BTCUSDT's quarterly return, once, from the store (R-AI).

Usage:
    python scripts/regime_labels.py                  # write docs/REGIME_LABELS.json + .sha256
    python scripts/regime_labels.py --check          # recompute and compare with the committed file

The project owner's ruling R-AI: *"Regimes are labelled per calendar quarter by BTCUSDT's
quarterly return: above +15% rising, below -15% falling, otherwise sideways. The labels are
computed once from the store, committed in a file with its digest, and fixed before S6."*

**IT WRITES ONCE.** The output and its ``.sha256`` are created with mode ``x``: a file that
already exists is refused, because a label set that moves under S6 is not a label set. The
check mode is how anyone re-derives the committed file from the store and proves it has not
drifted; it writes nothing. The definitions (the quarter, the return, the partial quarters and
the strict, exact thresholds) are in ``trading_bot.backtesting.regimes`` and in the file itself.

Exit codes: 0 written or checked equal; 1 the store cannot be read, or the check differs; 2 the
write was refused because the output already exists.
"""

from __future__ import annotations

import argparse
import hashlib
import sys
from collections.abc import Sequence
from datetime import datetime, timezone
from pathlib import Path
from typing import TextIO

from trading_bot.backtesting.regimes import (
    build_document,
    document_digest,
    label_quarters,
    render_document,
)
from trading_bot.data.historical import MANIFEST_NAME, HistoricalStore, StoredFileError, series_dir

DEFAULT_DATA_DIR = "data/historical"
DEFAULT_OUT = "docs/REGIME_LABELS.json"
SYMBOL = "BTCUSDT"
INTERVAL = "1d"

_EARLIEST = datetime(2000, 1, 1, tzinfo=timezone.utc)
_LATEST = datetime(2100, 1, 1, tzinfo=timezone.utc)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0] if __doc__ else None)
    parser.add_argument("--data-dir", default=DEFAULT_DATA_DIR, help="backtesting.data_dir")
    parser.add_argument("--out", default=DEFAULT_OUT, help="the committed labels file")
    parser.add_argument("--check", action="store_true", help="recompute and compare; write nothing")
    return parser


def compute(root: Path) -> tuple[bytes, str, dict[str, object]]:
    """The rendered document, its digest and the document, from the store under ``root``.

    :raises StoredFileError: a month file is missing or no longer matches its manifest.
    :raises ValueError: the series holds no bar, or two bars open on one day.
    """
    candles = list(HistoricalStore(root).candles(SYMBOL, INTERVAL, _EARLIEST, _LATEST))
    if not candles:
        raise ValueError(f"{SYMBOL} {INTERVAL}: the store under {root} holds no bar")
    manifest = series_dir(root, SYMBOL, INTERVAL) / MANIFEST_NAME
    source = {
        "series": f"{SYMBOL} {INTERVAL}",
        "store_manifest_sha256": hashlib.sha256(manifest.read_bytes()).hexdigest(),
        "bars": len(candles),
        "first_open": min(c.open_time for c in candles).isoformat(),
        "last_open": max(c.open_time for c in candles).isoformat(),
    }
    document = build_document(
        label_quarters(candles), symbol=SYMBOL, interval=INTERVAL, source=source
    )
    rendered = render_document(document)
    return rendered, document_digest(rendered), document


def _digest_line(digest: str, out: Path) -> str:
    return f"{digest}  {out.name}\n"


def run(argv: Sequence[str], *, out: TextIO | None = None) -> int:
    """Write or check the labels; ``out`` is where the one-line report goes (stdout if omitted,
    read at call time so a capturing stdout sees it)."""
    out = out if out is not None else sys.stdout
    args = _parser().parse_args(argv)
    target = Path(args.out)
    sidecar = target.with_name(target.name + ".sha256")
    try:
        rendered, digest, document = compute(Path(args.data_dir))
    except (StoredFileError, ValueError, OSError) as exc:
        print(f"cannot read the store: {type(exc).__name__}: {exc}", file=out)
        return 1
    counts = document["counts"]
    if args.check:
        same = (
            target.is_file()
            and target.read_bytes() == rendered
            and sidecar.is_file()
            and sidecar.read_text(encoding="ascii") == _digest_line(digest, target)
        )
        print(f"{'equal' if same else 'DIFFERS'}: {target} sha256 {digest} {counts}", file=out)
        return 0 if same else 1
    if target.exists() or sidecar.exists():
        print(
            f"refused: {target} or {sidecar} exists; the labels are written once (R-AI). "
            "Use --check to compare.",
            file=out,
        )
        return 2
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("xb") as handle:
        handle.write(rendered)
    with sidecar.open("x", encoding="ascii", newline="\n") as handle:
        handle.write(_digest_line(digest, target))
    print(f"wrote {target} sha256 {digest} {counts}", file=out)
    return 0


def main() -> None:
    sys.exit(run(sys.argv[1:]))


if __name__ == "__main__":
    main()
