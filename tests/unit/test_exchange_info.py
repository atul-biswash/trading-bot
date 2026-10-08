"""Stored ``exchangeInfo`` snapshots (the owner's R-Z): stored raw, verified, parsed by the live mapper.

No test touches the network. The payload below has the SHAPE of a single-symbol response, with a
Testnet BTCUSDT entry's filters as ``tests/unit/test_exchange_mappers.py`` records them; the
expected figures are read off it by hand.
"""

from __future__ import annotations

import hashlib
import json
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from trading_bot.backtesting import exchange_info as ei
from trading_bot.backtesting.exchange_info import (
    INFO_DIR_NAME,
    SnapshotError,
    checksum_file,
    load_snapshot,
    snapshot_file,
    store_snapshot,
)
from trading_bot.core.models import SymbolInfo

SERVER_TIME = 1_700_000_000_123

# fmt: off
FILTERS: list[dict[str, Any]] = [
    {"filterType": "PRICE_FILTER",
     "minPrice": "0.01000000", "maxPrice": "1000000.00000000", "tickSize": "0.01000000"},
    {"filterType": "LOT_SIZE",
     "minQty": "0.00001000", "maxQty": "9000.00000000", "stepSize": "0.00001000"},
    {"filterType": "MARKET_LOT_SIZE",
     "minQty": "0.00000000", "maxQty": "141.67845966", "stepSize": "0.00000000"},
    {"filterType": "PERCENT_PRICE_BY_SIDE",
     "bidMultiplierUp": "2", "bidMultiplierDown": "0.5",
     "askMultiplierUp": "2", "askMultiplierDown": "0.5", "avgPriceMins": 5},
    {"filterType": "NOTIONAL",
     "minNotional": "5.00000000", "applyMinToMarket": True,
     "maxNotional": "9000000.00000000", "applyMaxToMarket": False, "avgPriceMins": 5},
    {"filterType": "MAX_NUM_ORDER_LISTS", "maxNumOrderLists": 20},
    {"filterType": "MAX_NUM_ALGO_ORDERS", "maxNumAlgoOrders": 5},
]
# fmt: on


def entry(symbol: str = "BTCUSDT", filters: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    return {
        "symbol": symbol,
        "status": "TRADING",
        "baseAsset": symbol[:-4],
        "quoteAsset": "USDT",
        "filters": FILTERS if filters is None else filters,
    }


def response(
    symbol: str = "BTCUSDT",
    *,
    server_time: int | None = SERVER_TIME,
    symbols: list[Any] | None = None,
) -> bytes:
    document: dict[str, Any] = {"timezone": "UTC", "rateLimits": [], "exchangeFilters": []}
    if server_time is not None:
        document["serverTime"] = server_time
    document["symbols"] = [entry(symbol)] if symbols is None else symbols
    return json.dumps(document, indent=2).encode("utf-8")


class TestStoringAndLoading:
    def test_a_stored_response_loads_into_the_live_symbol_info(self, tmp_path: Path) -> None:
        raw = response()
        digest = store_snapshot(tmp_path, "mainnet", "BTCUSDT", raw)
        snapshot = load_snapshot(tmp_path, "mainnet", "BTCUSDT")
        info = snapshot.symbol_info
        assert isinstance(info, SymbolInfo)
        assert info.symbol == "BTCUSDT"
        assert (info.base_asset, info.quote_asset) == ("BTC", "USDT")
        assert info.price_tick == Decimal("0.01")
        assert info.step_size == Decimal("0.00001")
        assert info.min_qty == Decimal("0.00001")
        assert info.min_notional == Decimal("5")
        assert info.market_lot is not None
        assert info.market_lot.max_qty == Decimal("141.67845966")
        assert info.percent_price is not None
        assert info.percent_price.bid_multiplier_up == Decimal("2")
        assert info.percent_price.ask_multiplier_down == Decimal("0.5")
        assert info.percent_price.avg_price_mins == 5
        assert info.max_num_algo_orders == 5
        assert info.max_num_order_lists == 20
        assert snapshot.sha256 == digest
        assert snapshot.server_time_ms == SERVER_TIME
        assert (snapshot.environment, snapshot.symbol) == ("mainnet", "BTCUSDT")

    def test_the_response_is_stored_byte_for_byte_with_its_digest_beside_it(
        self, tmp_path: Path
    ) -> None:
        raw = response()
        digest = store_snapshot(tmp_path, "testnet", "BTCUSDT", raw)
        path = tmp_path / INFO_DIR_NAME / "testnet" / "BTCUSDT.json"
        assert snapshot_file(tmp_path, "testnet", "BTCUSDT") == path
        assert path.read_bytes() == raw
        assert digest == hashlib.sha256(raw).hexdigest()
        assert checksum_file(tmp_path, "testnet", "BTCUSDT") == path.with_name(
            "BTCUSDT.json.sha256"
        )
        assert checksum_file(tmp_path, "testnet", "BTCUSDT").read_text(encoding="ascii") == (
            f"{digest}  BTCUSDT.json\n"
        )

    def test_a_response_without_a_server_time_loads_with_none(self, tmp_path: Path) -> None:
        store_snapshot(tmp_path, "mainnet", "BTCUSDT", response(server_time=None))
        assert load_snapshot(tmp_path, "mainnet", "BTCUSDT").server_time_ms is None

    def test_the_two_environments_hold_independent_snapshots(self, tmp_path: Path) -> None:
        main = response(server_time=1)
        test = response(server_time=2)
        store_snapshot(tmp_path, "mainnet", "BTCUSDT", main)
        store_snapshot(tmp_path, "testnet", "BTCUSDT", test)
        assert load_snapshot(tmp_path, "mainnet", "BTCUSDT").server_time_ms == 1
        assert load_snapshot(tmp_path, "testnet", "BTCUSDT").server_time_ms == 2
        assert load_snapshot(tmp_path, "mainnet", "BTCUSDT").sha256 != (
            load_snapshot(tmp_path, "testnet", "BTCUSDT").sha256
        )

    def test_the_older_min_notional_spelling_is_read_by_the_live_mapper(
        self, tmp_path: Path
    ) -> None:
        """Parsing is ``to_symbol_info``, so what it accepts for the live bot it accepts here."""
        filters = [f for f in FILTERS if f["filterType"] != "NOTIONAL"]
        filters.append({"filterType": "MIN_NOTIONAL", "minNotional": "10.00000000"})
        raw = response(symbols=[entry(filters=filters)])
        store_snapshot(tmp_path, "mainnet", "BTCUSDT", raw)
        assert load_snapshot(tmp_path, "mainnet", "BTCUSDT").symbol_info.min_notional == Decimal(10)

    def test_the_loader_hands_the_symbols_entry_to_the_live_mapper(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        store_snapshot(tmp_path, "mainnet", "BTCUSDT", response())
        seen: list[dict[str, Any]] = []
        sentinel = SymbolInfo(
            symbol="BTCUSDT",
            base_asset="X",
            quote_asset="Y",
            price_tick=Decimal(1),
            step_size=Decimal(1),
            min_qty=Decimal(1),
            min_notional=Decimal(1),
        )

        def spy(raw: dict[str, Any]) -> SymbolInfo:
            seen.append(raw)
            return sentinel

        monkeypatch.setattr(ei, "to_symbol_info", spy)
        assert load_snapshot(tmp_path, "mainnet", "BTCUSDT").symbol_info is sentinel
        assert len(seen) == 1
        assert seen[0]["symbol"] == "BTCUSDT"
        assert seen[0]["filters"] == FILTERS


class TestAStoredSnapshotIsNeverOverwritten:
    def test_a_second_store_of_the_same_symbol_is_refused_and_changes_nothing(
        self, tmp_path: Path
    ) -> None:
        first = response(server_time=1)
        store_snapshot(tmp_path, "mainnet", "BTCUSDT", first)
        with pytest.raises(SnapshotError, match="never overwritten"):
            store_snapshot(tmp_path, "mainnet", "BTCUSDT", response(server_time=2))
        assert snapshot_file(tmp_path, "mainnet", "BTCUSDT").read_bytes() == first
        assert load_snapshot(tmp_path, "mainnet", "BTCUSDT").server_time_ms == 1

    def test_a_leftover_digest_alone_also_blocks_a_store(self, tmp_path: Path) -> None:
        sum_path = checksum_file(tmp_path, "mainnet", "BTCUSDT")
        sum_path.parent.mkdir(parents=True)
        sum_path.write_text("x", encoding="ascii")
        with pytest.raises(SnapshotError, match="never overwritten"):
            store_snapshot(tmp_path, "mainnet", "BTCUSDT", response())
        assert not snapshot_file(tmp_path, "mainnet", "BTCUSDT").exists()


class TestALoadVerifiesBeforeItParses:
    def test_an_altered_response_is_refused(self, tmp_path: Path) -> None:
        store_snapshot(tmp_path, "mainnet", "BTCUSDT", response())
        path = snapshot_file(tmp_path, "mainnet", "BTCUSDT")
        path.write_bytes(path.read_bytes().replace(b"0.01000000", b"0.02000000"))
        with pytest.raises(SnapshotError, match="no longer matches"):
            load_snapshot(tmp_path, "mainnet", "BTCUSDT")

    def test_a_missing_digest_is_refused_and_names_the_script(self, tmp_path: Path) -> None:
        store_snapshot(tmp_path, "mainnet", "BTCUSDT", response())
        checksum_file(tmp_path, "mainnet", "BTCUSDT").unlink()
        with pytest.raises(SnapshotError, match="download_exchange_info"):
            load_snapshot(tmp_path, "mainnet", "BTCUSDT")

    def test_a_missing_response_is_refused(self, tmp_path: Path) -> None:
        with pytest.raises(SnapshotError, match="no usable snapshot"):
            load_snapshot(tmp_path, "mainnet", "BTCUSDT")

    @pytest.mark.parametrize(
        "text",
        (
            "",
            "not a digest  BTCUSDT.json\n",
            f"{'a' * 64} BTCUSDT.json\n",
            f"{'A' * 64}  BTCUSDT.json\n",
        ),
    )
    def test_a_malformed_digest_file_is_refused(self, tmp_path: Path, text: str) -> None:
        store_snapshot(tmp_path, "mainnet", "BTCUSDT", response())
        checksum_file(tmp_path, "mainnet", "BTCUSDT").write_text(text, encoding="ascii")
        with pytest.raises(SnapshotError, match="is not"):
            load_snapshot(tmp_path, "mainnet", "BTCUSDT")

    def test_a_digest_file_naming_another_response_is_refused(self, tmp_path: Path) -> None:
        raw = response()
        store_snapshot(tmp_path, "mainnet", "BTCUSDT", raw)
        digest = hashlib.sha256(raw).hexdigest()
        checksum_file(tmp_path, "mainnet", "BTCUSDT").write_text(
            f"{digest}  ETHUSDT.json\n", encoding="ascii"
        )
        with pytest.raises(SnapshotError, match="is not"):
            load_snapshot(tmp_path, "mainnet", "BTCUSDT")


class TestAResponseThatIsNotASingleReadableSymbolIsRefusedBeforeAnythingIsWritten:
    @pytest.mark.parametrize(
        "raw",
        (
            b"not json",
            b"\xff\xfe",
            b"[]",
            b'{"symbols": "BTCUSDT"}',
            b'{"symbols": []}',
            json.dumps({"symbols": [entry(), entry("ETHUSDT")]}).encode(),
            json.dumps({"symbols": ["BTCUSDT"]}).encode(),
        ),
    )
    def test_a_malformed_or_multi_symbol_response(self, tmp_path: Path, raw: bytes) -> None:
        with pytest.raises(SnapshotError):
            store_snapshot(tmp_path, "mainnet", "BTCUSDT", raw)
        assert not snapshot_file(tmp_path, "mainnet", "BTCUSDT").exists()
        assert not checksum_file(tmp_path, "mainnet", "BTCUSDT").exists()

    def test_a_response_for_another_symbol(self, tmp_path: Path) -> None:
        with pytest.raises(SnapshotError, match="is for 'ETHUSDT'"):
            store_snapshot(tmp_path, "mainnet", "BTCUSDT", response("ETHUSDT"))
        assert not snapshot_file(tmp_path, "mainnet", "BTCUSDT").exists()

    def test_an_entry_the_live_mapper_refuses(self, tmp_path: Path) -> None:
        """Without ``LOT_SIZE`` the mapper raises; the snapshot must not be stored."""
        filters = [f for f in FILTERS if f["filterType"] != "LOT_SIZE"]
        with pytest.raises(SnapshotError, match="live mapper refuses"):
            store_snapshot(
                tmp_path, "mainnet", "BTCUSDT", response(symbols=[entry(filters=filters)])
            )
        assert not snapshot_file(tmp_path, "mainnet", "BTCUSDT").exists()


class TestNamesAreValidatedBeforeTheyBecomePaths:
    @pytest.mark.parametrize("environment", ("", "main", "MAINNET", "../mainnet", "live"))
    def test_an_unknown_environment(self, tmp_path: Path, environment: str) -> None:
        with pytest.raises(SnapshotError, match="not an environment"):
            snapshot_file(tmp_path, environment, "BTCUSDT")
        with pytest.raises(SnapshotError, match="not an environment"):
            store_snapshot(tmp_path, environment, "BTCUSDT", response())

    @pytest.mark.parametrize(
        "symbol", ("", "btcusdt", "BTC", "../BTCUSDT", "BTC/USDT", "BTCUSDT.json")
    )
    def test_a_name_that_is_not_a_symbol(self, tmp_path: Path, symbol: str) -> None:
        with pytest.raises(SnapshotError, match="not a symbol"):
            snapshot_file(tmp_path, "mainnet", symbol)
        with pytest.raises(SnapshotError, match="not a symbol"):
            load_snapshot(tmp_path, "mainnet", symbol)

    def test_the_directory_cannot_be_mistaken_for_a_series(self) -> None:
        """A series directory is named by a symbol; ``_exchange_info`` starts with an underscore."""
        assert INFO_DIR_NAME.startswith("_")
        assert INFO_DIR_NAME not in {"BTCUSDT", "ETHUSDT"}
