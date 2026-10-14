"""R-BT: the research protocol's declaration, its parser, its windows, its grid and its entries.

The declaration in the REAL ``docs/research/PROTOCOL.md`` is shown to be what its prose and the committed files
say (216 variants, the labels' digest, the committed config's costs and strategy), so the protocol cannot rot
away from them; every defect a declaration or an entry can have is refused and named; the window is classified
against the boundary; and a candidate is a grid point or it is not. The guard that reads all of this is
``test_backtest_guard.py``.
"""

from __future__ import annotations

import copy
import hashlib
import json
from collections.abc import Callable
from datetime import date
from pathlib import Path
from typing import Any

import pytest
import yaml

from tests.unit.protocol_world import (
    BOUNDARY,
    CANDIDATE,
    FULL,
    HISTORY_END,
    PROTOCOL,
    PROTOCOL_TEXT,
    REPO,
    effective,
    entry_text,
)
from trading_bot.backtesting.protocol import (
    ENTRIES_DIR,
    PROTOCOL_PATH,
    Entry,
    ProtocolError,
    WindowClass,
    classify_window,
    grid_point,
    load_entries,
    load_protocol,
    parse_entry,
    parse_protocol,
)

# A small synthetic declaration, for the parse refusals.
BASE: dict[str, Any] = {
    "protocol_schema": 1,
    "history": {"start": "2017-08-17", "end_exclusive": "2026-10-01"},
    "boundary": "2024-01-01",
    "regime_labels_sha256": "6" * 64,
    "arms_stop_slippage_percent": ["0.05", "0.66", "1.20"],
    "gate_arm": "1.20",
    "filter": {"param": "trend_filter_period", "value": 200},
    "min_in_sample_trades": 100,
    "pairs": ["BTCUSDT", "ETHUSDT"],
    "costs": {"fee_percent": "0.1", "slippage_percent": "0.05", "initial_balance": "10000"},
    "exchange_info_environment": "mainnet",
    "families": [
        {
            "id": "f",
            "strategy": "sma_crossover",
            "timeframes": ["1h", "4h"],
            "grid": {"fast_period": [10, 20], "slow_period": [50, 100]},
        }
    ],
    "baselines": [
        {
            "id": "b",
            "strategy": "sma_crossover",
            "params": {"fast_period": 20, "slow_period": 50},
            "pairs": [["BTCUSDT", "1m"], ["ETHUSDT", "5m"]],
            "window": {"start": "2017-08-17", "end_exclusive": "2026-10-01"},
        }
    ],
}


def declaration(data: object) -> str:
    return (
        "# x\n\n<!-- protocol-json:begin -->\n```json\n"
        + json.dumps(data, indent=2)
        + "\n```\n<!-- protocol-json:end -->\n"
    )


def edited(edit: Callable[[dict[str, Any]], None]) -> str:
    data = copy.deepcopy(BASE)
    edit(data)
    return declaration(data)


# --------------------------------------------------------------------------------------
# The real declaration
# --------------------------------------------------------------------------------------
class TestTheRealDeclaration:
    def test_the_declaration_matches_the_tables(self) -> None:
        """PROTOCOL.md section 5 says 54 + 162 = 216; the declaration must give exactly those."""
        variants = list(PROTOCOL.variants())
        by_family = {f.id: sum(1 for v in variants if v.family == f.id) for f in PROTOCOL.families}
        assert by_family == {"sma_crossover": 54, "rsi": 162}
        assert len(variants) == 216
        assert "| 9 x 3 x 2 = 54 |" in PROTOCOL_TEXT
        assert "| 27 x 3 x 2 = 162 |" in PROTOCOL_TEXT
        assert "fixed by this section**: 216." in PROTOCOL_TEXT

    def test_every_variant_is_distinct(self) -> None:
        keys = {
            (v.family, v.timeframe, v.filtered, tuple(sorted(v.params.items())))
            for v in PROTOCOL.variants()
        }
        assert len(keys) == 216

    def test_the_variants_come_in_the_grids_declared_order(self) -> None:
        variants = list(PROTOCOL.variants())
        first = variants[0]
        assert (first.family, first.timeframe, first.filtered) == ("sma_crossover", "1h", False)
        assert dict(first.params) == {"fast_period": "10", "slow_period": "50"}
        second = variants[1]
        assert dict(second.params) == {"fast_period": "10", "slow_period": "100"}
        filtered = [v for v in variants if v.filtered]
        assert len(filtered) == 108
        assert all(v.params["trend_filter_period"] == "200" for v in filtered)
        assert all("trend_filter_period" not in v.params for v in variants if not v.filtered)

    def test_the_boundary_the_history_and_the_arms_are_the_rulings(self) -> None:
        assert PROTOCOL.boundary == BOUNDARY
        assert PROTOCOL.history_start == date(2017, 8, 17)
        assert PROTOCOL.history_end == HISTORY_END
        assert (HISTORY_END - BOUNDARY).days == 1004
        assert PROTOCOL.arms == ("0.05", "0.66", "1.2")
        assert PROTOCOL.gate_arm == "1.2"
        assert PROTOCOL.pairs == ("BTCUSDT", "ETHUSDT")
        assert PROTOCOL.min_in_sample_trades == 250
        assert (PROTOCOL.filter_param, PROTOCOL.filter_value) == ("trend_filter_period", "200")

    def test_the_labels_digest_is_the_committed_labels_files(self) -> None:
        recorded = (REPO / "docs" / "REGIME_LABELS.json.sha256").read_text(encoding="utf-8").split()
        assert len(recorded) >= 1
        assert PROTOCOL.regime_labels_sha256 == recorded[0].lower()
        actual = hashlib.sha256((REPO / "docs" / "REGIME_LABELS.json").read_bytes()).hexdigest()
        assert PROTOCOL.regime_labels_sha256 == actual

    def test_the_declared_costs_are_the_committed_configs(self) -> None:
        config = yaml.safe_load((REPO / "config.yaml").read_text(encoding="utf-8"))
        block = config["backtesting"]
        assert PROTOCOL.costs == {
            "fee_percent": "0.1",
            "slippage_percent": "0.05",
            "initial_balance": "10000",
        }
        assert str(block["fee_percent"]) == "0.1"
        assert str(block["slippage_percent"]) == "0.05"
        assert float(block["initial_balance"]) == 10000.0
        assert (
            "stop_slippage_percent" not in block
        )  # the arm comes from --stop-slippage or the default
        assert PROTOCOL.exchange_info_environment == "mainnet"

    def test_the_baseline_is_the_committed_config_as_it_stands(self) -> None:
        config = yaml.safe_load((REPO / "config.yaml").read_text(encoding="utf-8"))
        baseline = PROTOCOL.baseline("s5-baseline")
        assert baseline is not None
        assert baseline.strategy == config["strategy"]["name"]
        assert dict(baseline.params) == {k: str(v) for k, v in config["strategy"]["params"].items()}
        assert baseline.pairs == tuple(
            (p["symbol"], p["timeframe"]) for p in config["trading"]["pairs"]
        )
        assert (baseline.window_start, baseline.window_end) == FULL
        assert PROTOCOL.baseline("nope") is None

    def test_each_shipped_strategy_is_a_variant_and_not_an_extra(self) -> None:
        sma = grid_point(PROTOCOL, effective(params={"fast_period": 20, "slow_period": 50}))
        rsi = grid_point(
            PROTOCOL,
            effective("rsi", {"period": 14, "oversold": 30, "overbought": 70}, timeframe="1h"),
        )
        assert sma is not None and sma.family == "sma_crossover"
        assert rsi is not None and rsi.family == "rsi"

    def test_the_digest_is_the_files_own(self) -> None:
        assert PROTOCOL.sha256 == hashlib.sha256(PROTOCOL_TEXT.encode("utf-8")).hexdigest()

    def test_the_loader_reads_the_committed_file(self) -> None:
        loaded = load_protocol(REPO / PROTOCOL_PATH)
        assert loaded == PROTOCOL

    def test_a_missing_file_is_a_protocol_error(self, tmp_path: Path) -> None:
        with pytest.raises(ProtocolError, match="cannot be read"):
            load_protocol(tmp_path / "nope.md")


# --------------------------------------------------------------------------------------
# Parse refusals
# --------------------------------------------------------------------------------------
class TestParseRefusals:
    def test_the_synthetic_base_parses(self) -> None:
        protocol = parse_protocol(declaration(BASE))
        assert len(list(protocol.variants())) == 2 * 2 * 2 * 2

    @pytest.mark.parametrize(
        ("text", "match"),
        [
            ("no markers at all", "exactly one"),
            (declaration(BASE) + declaration(BASE), "exactly one"),
            (
                "<!-- protocol-json:begin -->\n{}\n<!-- protocol-json:end -->",
                "```json fence",
            ),
            (
                "<!-- protocol-json:begin -->\n```json\n{oops\n```\n<!-- protocol-json:end -->",
                "not valid JSON",
            ),
            (declaration([1, 2]), "top level that is not an object"),
        ],
        ids=["no-markers", "two-blocks", "no-fence", "bad-json", "not-an-object"],
    )
    def test_a_block_that_is_not_one_declaration_is_refused(self, text: str, match: str) -> None:
        with pytest.raises(ProtocolError, match=match):
            parse_protocol(text)

    @pytest.mark.parametrize(
        ("edit", "match"),
        [
            (lambda d: d.update(protocol_schema=2), "protocol_schema 1"),
            (lambda d: d.pop("history"), "history that is not an object"),
            (lambda d: d["history"].update(start="2017-13-01"), "not a YYYY-MM-DD date"),
            (lambda d: d.update(boundary="2017-08-17"), "not strictly inside"),
            (lambda d: d.update(boundary="2026-10-01"), "not strictly inside"),
            (lambda d: d.update(boundary="2030-01-01"), "not strictly inside"),
            (lambda d: d.update(regime_labels_sha256="G" * 64), "64 lowercase hex"),
            (lambda d: d.update(regime_labels_sha256="6" * 63), "64 lowercase hex"),
            (lambda d: d.update(arms_stop_slippage_percent=[]), "no arms_stop_slippage_percent"),
            (lambda d: d.update(arms_stop_slippage_percent=["x"]), "not a number"),
            (lambda d: d.update(arms_stop_slippage_percent=["1.2", "1.20"]), "repeats a arm"),
            (lambda d: d.update(gate_arm="0.5"), "gate_arm that is not one of its arms"),
            (lambda d: d.pop("filter"), "filter that is not an object"),
            (lambda d: d["filter"].update(value="x"), "not a number"),
            (lambda d: d.update(min_in_sample_trades=0), "positive integer"),
            (lambda d: d.update(min_in_sample_trades=True), "positive integer"),
            (lambda d: d.update(min_in_sample_trades=1.5), "positive integer"),
            (lambda d: d.update(pairs=[]), "no pairs"),
            (lambda d: d.update(pairs=["BTCUSDT", "btcusdt"]), "repeats a pair"),
            (lambda d: d["costs"].pop("fee_percent"), "not a number"),
            (lambda d: d["costs"].update(initial_balance="lots"), "not a number"),
            (lambda d: d.pop("exchange_info_environment"), "exchange_info_environment"),
            (lambda d: d.update(families=[]), "no families"),
            (lambda d: d["families"][0].update(timeframes=[]), "no timeframes"),
            (lambda d: d["families"][0].update(grid={}), "empty grid"),
            (lambda d: d["families"][0]["grid"].update(fast_period=[]), "no values for"),
            (lambda d: d["families"][0]["grid"].update(fast_period=[30, 30.0]), "repeats a value"),
            (lambda d: d["families"][0]["grid"].update(fast_period=["x"]), "not a number"),
            (lambda d: d["families"][0]["grid"].update(fast_period=[True]), "not a number"),
            (
                lambda d: d["families"].append(copy.deepcopy(d["families"][0])),
                "repeats a family id",
            ),
            (lambda d: d["baselines"][0].update(pairs=[["BTCUSDT"]]), "pairs for"),
            (
                lambda d: d["baselines"].append(copy.deepcopy(d["baselines"][0])),
                "repeats a baseline id",
            ),
            (lambda d: d["baselines"][0]["window"].update(start="soon"), "not a YYYY-MM-DD date"),
        ],
        ids=[
            "schema",
            "no-history",
            "bad-date",
            "boundary-at-start",
            "boundary-at-end",
            "boundary-after-end",
            "labels-not-hex",
            "labels-short",
            "no-arms",
            "arm-not-a-number",
            "arm-repeated-after-canonicalising",
            "gate-not-an-arm",
            "no-filter",
            "filter-value-text",
            "min-zero",
            "min-bool",
            "min-float",
            "no-pairs",
            "pair-repeated",
            "cost-missing",
            "cost-text",
            "no-environment",
            "no-families",
            "no-timeframes",
            "empty-grid",
            "empty-values",
            "grid-repeat-30-and-30.0",
            "grid-text",
            "grid-bool",
            "family-repeated",
            "baseline-bad-pairs",
            "baseline-repeated",
            "baseline-bad-window",
        ],
    )
    def test_a_declaration_with_a_defect_is_refused_and_the_defect_named(
        self, edit: Callable[[dict[str, Any]], None], match: str
    ) -> None:
        with pytest.raises(ProtocolError, match=match):
            parse_protocol(edited(edit))

    def test_no_baselines_is_allowed(self) -> None:
        text = edited(lambda d: d.pop("baselines"))
        assert parse_protocol(text).baselines == ()


# --------------------------------------------------------------------------------------
# Window classification
# --------------------------------------------------------------------------------------
class TestClassifyWindow:
    @pytest.mark.parametrize(
        ("start", "end", "expected"),
        [
            (date(2017, 8, 17), date(2024, 1, 1), WindowClass.IN_SAMPLE),
            (date(2020, 1, 1), date(2021, 1, 1), WindowClass.IN_SAMPLE),
            (date(2023, 12, 31), date(2024, 1, 1), WindowClass.IN_SAMPLE),
            (date(2024, 1, 1), date(2026, 10, 1), WindowClass.OUT_OF_SAMPLE),
            (date(2024, 1, 1), date(2024, 1, 2), WindowClass.OUT_OF_SAMPLE),
            (date(2025, 6, 1), date(2025, 7, 1), WindowClass.OUT_OF_SAMPLE),
            (date(2023, 12, 31), date(2024, 1, 2), WindowClass.STRADDLING),
            (date(2017, 8, 17), date(2026, 10, 1), WindowClass.STRADDLING),
            (date(2023, 12, 31), date(2025, 1, 1), WindowClass.STRADDLING),
        ],
        ids=[
            "history-start-to-boundary",
            "inside-in-sample",
            "last-in-sample-day",
            "the-oos-window",
            "first-oos-day",
            "inside-oos",
            "one-day-either-side",
            "whole-history",
            "from-the-last-in-sample-day",
        ],
    )
    def test_where_the_window_sits(self, start: date, end: date, expected: WindowClass) -> None:
        assert classify_window(PROTOCOL, start, end) is expected


# --------------------------------------------------------------------------------------
# Grid membership
# --------------------------------------------------------------------------------------
class TestGridPoint:
    def test_a_declared_point_is_found_with_its_family_timeframe_and_filter(self) -> None:
        point = grid_point(PROTOCOL, effective(params={"fast_period": 30, "slow_period": 200}))
        assert point is not None
        assert (point.family, point.timeframe, point.filtered) == ("sma_crossover", "4h", False)
        assert dict(point.params) == {"fast_period": "30", "slow_period": "200"}

    def test_the_filter_at_exactly_the_declared_value_is_a_filtered_variant(self) -> None:
        point = grid_point(
            PROTOCOL,
            effective(params={"fast_period": 10, "slow_period": 50, "trend_filter_period": 200}),
        )
        assert point is not None and point.filtered is True

    def test_a_threshold_typed_as_a_float_is_the_same_point(self) -> None:
        a = grid_point(
            PROTOCOL,
            effective("rsi", {"period": 7, "oversold": 20, "overbought": 80}, timeframe="1d"),
        )
        b = grid_point(
            PROTOCOL,
            effective("rsi", {"period": 7, "oversold": 20.0, "overbought": 80.0}, timeframe="1d"),
        )
        assert a is not None and b is not None
        assert dict(a.params) == dict(b.params)

    @pytest.mark.parametrize(
        "eff",
        [
            effective(params={"fast_period": 15, "slow_period": 100}),
            effective(params={"fast_period": 20, "slow_period": 100, "extra": 1}),
            effective(params={"fast_period": 20}),
            effective(params={"fast_period": 20, "slow_period": 100, "trend_filter_period": 100}),
            effective(params={"fast_period": 20, "slow_period": 100, "trend_filter_period": 201}),
            effective(timeframe="15m"),
            effective(timeframe="1m"),
            effective(pairs=("BTCUSDT",)),
            effective(pairs=("ETHUSDT", "BTCUSDT")),
            effective(pairs=("BTCUSDT", "ETHUSDT", "SOLUSDT")),
            effective(timeframes=("1h", "4h")),
            effective("macd", {"fast_period": 20, "slow_period": 100}),
            effective(fee="0.075"),
            effective(slippage="0.1"),
            effective(balance="5000"),
            effective(environment="testnet"),
        ],
        ids=[
            "off-grid-value",
            "extra-param",
            "missing-param",
            "filter-wrong-value-100",
            "filter-wrong-value-201",
            "undeclared-timeframe",
            "candidate-at-1m",
            "one-pair",
            "pairs-reversed",
            "three-pairs",
            "pairs-on-two-timeframes",
            "undeclared-strategy",
            "fee",
            "entry-slippage",
            "balance",
            "environment",
        ],
    )
    def test_anything_off_the_declared_grids_is_not_a_point(self, eff: dict[str, Any]) -> None:
        assert grid_point(PROTOCOL, eff) is None

    def test_a_block_with_no_strategy_or_pairs_is_not_a_point(self) -> None:
        assert grid_point(PROTOCOL, {}) is None
        assert grid_point(PROTOCOL, {**effective(), "pairs": []}) is None
        assert grid_point(PROTOCOL, {**effective(), "strategy": "x"}) is None
        assert grid_point(PROTOCOL, {**effective(), "costs": "x"}) is None

    def test_the_arm_is_not_part_of_being_a_point(self) -> None:
        assert grid_point(PROTOCOL, effective(arm="0.05")) is not None
        assert grid_point(PROTOCOL, effective(arm="0.66")) is not None


# --------------------------------------------------------------------------------------
# Entries
# --------------------------------------------------------------------------------------
class TestEntries:
    def test_a_valid_entry_is_read_with_canonical_arms_and_its_files_digest(self) -> None:
        text = entry_text(CANDIDATE)
        entry = parse_entry(text)
        assert entry.arms == ("0.05", "0.66", "1.2")
        assert entry.sha256 == hashlib.sha256(text.encode("utf-8")).hexdigest()
        assert (entry.kind, entry.status, entry.oos) == ("candidate", "pending", None)

    def test_a_read_entry_carries_its_oos_block(self) -> None:
        entry = parse_entry(
            entry_text(CANDIDATE, status="read", oos={"records": {"1.2": "d" * 64}})
        )
        assert entry.status == "read" and entry.oos == {"records": {"1.2": "d" * 64}}

    @pytest.mark.parametrize(
        ("edit", "match"),
        [
            (lambda d: d.update(entry_schema=2), "entry_schema 1"),
            (lambda d: d.pop("id"), "no text 'id'"),
            (lambda d: d.update(id=""), "no text 'id'"),
            (lambda d: d.update(kind="strategy"), "has kind 'strategy'"),
            (lambda d: d.update(status="done"), "has status 'done'"),
            (lambda d: d.update(candidate_digest="abc"), "not 64 hex digits"),
            (lambda d: d.update(candidate_digest="G" * 64), "not 64 hex digits"),
            (lambda d: d.update(arms=[]), "has no arms"),
            (lambda d: d.update(arms=["x"]), "not a number"),
            (lambda d: d.update(arms=[1.2]), "has no arms"),
            (lambda d: d.update(oos=[1]), "oos that is not an object"),
            (lambda d: d.update(status="pending", oos={"records": {}}), "pending' and has an oos"),
            (lambda d: d.update(status="read", oos=None), "read' and lacks an oos"),
        ],
        ids=[
            "schema",
            "no-id",
            "empty-id",
            "kind",
            "status",
            "short-digest",
            "non-hex-digest",
            "no-arms",
            "arm-text",
            "arm-number",
            "oos-list",
            "pending-with-oos",
            "read-without-oos",
        ],
    )
    def test_a_malformed_entry_is_refused(
        self, edit: Callable[[dict[str, Any]], None], match: str
    ) -> None:
        data = json.loads(entry_text(CANDIDATE))
        edit(data)
        with pytest.raises(ProtocolError, match=match):
            parse_entry(json.dumps(data))

    def test_text_that_is_not_json_or_not_an_object_is_refused(self) -> None:
        with pytest.raises(ProtocolError, match="not valid JSON"):
            parse_entry("{oops")
        with pytest.raises(ProtocolError, match="not a JSON object"):
            parse_entry("[1]")


class TestLoadEntries:
    def write(self, directory: Path, name: str, text: str) -> None:
        directory.mkdir(parents=True, exist_ok=True)
        (directory / name).write_text(text, encoding="utf-8")

    def test_an_absent_directory_holds_no_entries(self, tmp_path: Path) -> None:
        assert load_entries(tmp_path / "entries") == ()

    def test_entries_are_read_in_name_order_and_other_files_are_ignored(
        self, tmp_path: Path
    ) -> None:
        directory = tmp_path / "entries"
        other = effective(params={"fast_period": 30, "slow_period": 100})
        self.write(directory, "b.json", entry_text(other, entry_id="b"))
        self.write(directory, "a.json", entry_text(CANDIDATE, entry_id="a"))
        self.write(directory, "notes.md", "not an entry")
        loaded = load_entries(directory)
        assert [e.id for e in loaded] == ["a", "b"]

    def test_a_malformed_entry_refuses_the_whole_load(self, tmp_path: Path) -> None:
        directory = tmp_path / "entries"
        self.write(directory, "a.json", entry_text(CANDIDATE))
        self.write(directory, "b.json", "{oops")
        with pytest.raises(ProtocolError, match="not valid JSON"):
            load_entries(directory)

    def test_two_entries_with_one_id_are_refused(self, tmp_path: Path) -> None:
        directory = tmp_path / "entries"
        other = effective(params={"fast_period": 30, "slow_period": 100})
        self.write(directory, "a.json", entry_text(CANDIDATE, entry_id="same"))
        self.write(directory, "b.json", entry_text(other, entry_id="same"))
        with pytest.raises(ProtocolError, match="one id"):
            load_entries(directory)

    def test_two_entries_for_one_candidate_are_refused(self, tmp_path: Path) -> None:
        directory = tmp_path / "entries"
        self.write(directory, "a.json", entry_text(CANDIDATE, entry_id="a"))
        self.write(directory, "b.json", entry_text(CANDIDATE, entry_id="b"))
        with pytest.raises(ProtocolError, match="one candidate digest"):
            load_entries(directory)

    def test_the_committed_entries_directory_loads(self) -> None:
        """Whatever is committed under docs/research/entries must parse; it is empty until C4."""
        loaded = load_entries(REPO / ENTRIES_DIR)
        assert isinstance(loaded, tuple)
        assert all(isinstance(e, Entry) for e in loaded)


class TestAnEntrysSelectionBlock:
    """The block S6's freeze writes into a candidate's entry (PROTOCOL.md section 6 step 6): kept, never read
    by the guard, and refused if it is present and not an object."""

    def body(self, **changes: Any) -> str:
        data = json.loads(entry_text(CANDIDATE))
        data.update(changes)
        return json.dumps(data)

    def test_it_is_kept_as_written(self) -> None:
        block = {"variant": {"family": "sma_crossover"}, "trades": 350}
        assert parse_entry(self.body(selection=block)).selection == block

    def test_an_entry_without_one_has_none(self) -> None:
        assert parse_entry(self.body()).selection is None

    @pytest.mark.parametrize("bad", ["text", 5, ["a"], True])
    def test_one_that_is_present_and_not_an_object_is_refused(self, bad: object) -> None:
        with pytest.raises(ProtocolError, match="selection that is not an object"):
            parse_entry(self.body(selection=bad))

    def test_the_guard_ignores_it(self) -> None:
        plain = parse_entry(self.body())
        with_block = parse_entry(self.body(selection={"variant": {"family": "x"}}))
        assert (plain.id, plain.candidate_digest, plain.status, plain.oos) == (
            with_block.id,
            with_block.candidate_digest,
            with_block.status,
            with_block.oos,
        )
