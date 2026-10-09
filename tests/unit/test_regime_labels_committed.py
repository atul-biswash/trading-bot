"""``docs/REGIME_LABELS.json``: consistent with itself and with its digest file.

That the file matches the STORE is ``scripts/regime_labels.py --check``'s to prove, since the
store is not in git. What a clone CAN prove is everything else: the digest file records the
bytes, the quarters run on without a gap, every label is the ruled one for the figures printed
beside it, and the counts are true. These tests fail if anyone edits the committed labels by hand.
"""

from __future__ import annotations

import hashlib
import json
from datetime import date
from decimal import Decimal
from itertools import pairwise
from pathlib import Path

from trading_bot.backtesting.regimes import (
    FALLING_BELOW,
    RISING_ABOVE,
    RegimeTable,
    classify,
)

D = Decimal
COMMITTED = Path(__file__).resolve().parents[2] / "docs" / "REGIME_LABELS.json"


def document() -> dict[str, object]:
    return json.loads(COMMITTED.read_bytes())


def rows() -> list[dict[str, object]]:
    found = document()["quarters"]
    assert isinstance(found, list) and found
    return found


def test_the_digest_file_records_the_sha256_of_the_labels_file() -> None:
    sidecar = COMMITTED.with_name(COMMITTED.name + ".sha256")
    assert sidecar.read_text(encoding="ascii") == (
        f"{hashlib.sha256(COMMITTED.read_bytes()).hexdigest()}  {COMMITTED.name}\n"
    )


def test_the_file_is_ascii_with_lf_endings_and_loads_as_a_table() -> None:
    raw = COMMITTED.read_bytes()
    assert b"\r" not in raw
    assert all(byte < 128 for byte in raw)
    assert RegimeTable.from_file(COMMITTED).quarter_is_known(date(2024, 3, 31))


def test_the_quarters_run_on_without_a_gap_and_the_counts_are_true() -> None:
    found = rows()
    for before, after in pairwise(found):
        assert before["end"] == after["start"]
    tally: dict[str, int] = {"rising": 0, "falling": 0, "sideways": 0, "partial": 0}
    for row in found:
        tally["partial" if row["regime"] is None else str(row["regime"])] += 1
    assert document()["counts"] == {**tally, "quarters": len(found)}


def test_every_label_is_the_ruled_one_for_the_figures_beside_it() -> None:
    for row in rows():
        if row["regime"] is None:
            assert row["bars"] != row["expected_bars"] and row["note"] != ""
        else:
            assert row["bars"] == row["expected_bars"]
            assert (
                classify(D(str(row["open_first"])), D(str(row["close_last"]))).value
                == row["regime"]
            )


def test_the_thresholds_it_states_are_the_modules() -> None:
    definition = document()["definition"]
    assert isinstance(definition, dict)
    assert D(definition["rising_above"]) == RISING_ABOVE
    assert D(definition["falling_below"]) == FALLING_BELOW


def test_the_known_quarters_are_the_ones_the_store_gave() -> None:
    """A hand check against the figures the first run printed: three quarters, read by eye."""
    by_quarter = {row["quarter"]: row for row in rows()}
    assert by_quarter["2017Q3"]["regime"] is None
    assert by_quarter["2018Q1"]["regime"] == "falling"
    assert by_quarter["2022Q4"]["regime"] == "sideways"
    assert by_quarter["2022Q4"]["return"] == "-0.148292"
    assert by_quarter["2024Q1"]["regime"] == "rising"
    assert len(by_quarter) == 37
