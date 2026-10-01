"""Tests for ``scripts/release_position.py`` (C34, P83).

Every test runs in a ``tmp_path`` working directory (``tests/conftest.py``
chdirs each non-integration test), so the tool's relative ``data/state.json``,
``logs/.bot.lock`` and ``logs/release.log`` are this test's own.

Each test names the mutation it exists for and asserts on the STORE'S BYTES
where it can, because a tool that says it removed one symbol is worth only what
the file says afterwards.
"""

from __future__ import annotations

import hashlib
import json
import sys
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

import release_position
from release_position import COMMAND, main

from tests.unit.test_restoration import (
    BAR,
    FILTERS,
    OTHER,
    QTY,
    SL,
    SYMBOL,
    TP,
    W,
    base,
    leg,
    order_list,
    record,
)
from trading_bot.core.enums import OrderStatus
from trading_bot.core.exceptions import ExchangeConnectionError, OrderNotFoundError
from trading_bot.core.interfaces import ExchangeClient
from trading_bot.core.models import Balance, Fee, HeldExit, Order, OrderList, SymbolInfo
from trading_bot.exchange.ids import list_client_order_id
from trading_bot.execution.booking_line import hold_fields
from trading_bot.persistence import store
from trading_bot.utils.instance_lock import DEFAULT_LOCK_PATH, acquire

D = Decimal
STORE = Path("data/state.json")
NOW = datetime(2026, 10, 1, 12, 0, tzinfo=timezone.utc)
KEPT = "SOLUSDT"
CLOSE = store.PendingCloseRecord(
    kind="close", symbol=SYMBOL, entry_bar_time=BAR, generation=0, quantity=QTY
)
OTHER_PLACEMENT = store.PendingRecord(
    symbol=OTHER,
    entry_bar_time=BAR,
    generation=0,
    quantity=QTY,
    entry_limit=D("3000.00"),
    stop_loss=D("2900.00"),
    take_profit=D("3200.00"),
)


def _state() -> store.PersistedState:
    """BTC: a position and a close. ETH: a placement. SOL: a position.

    A store never holds a position and a placement for one symbol, so the three
    symbols between them cover every record kind.
    """
    return store.PersistedState(
        pending=(CLOSE, OTHER_PLACEMENT),
        positions=(record(SYMBOL), record(KEPT)),
        ledger=store.LedgerRecord(
            realised_pnl=D("-12.50000000"), pnl_date=date(2026, 9, 20), trades_count=2
        ),
        lifetime_realised=D("100.50000000"),
    )


def _write(state: store.PersistedState | None = None) -> str:
    """Write the store and return its SHA-256."""
    store.save(state or _state(), STORE)
    return hashlib.sha256(STORE.read_bytes()).hexdigest()


def _sha() -> str:
    return hashlib.sha256(STORE.read_bytes()).hexdigest()


def _confirm(answer: str) -> Any:
    return lambda _prompt: answer


def _never_asked(_prompt: str) -> str:
    raise AssertionError("the operator must not be asked")


class ReadOnlyClient(ExchangeClient):
    """Answers the preview's GETs and FAILS on any write or any read it does not use."""

    def __init__(
        self,
        *,
        lists: list[OrderList],
        orders: list[Order],
        balances: list[Balance],
    ) -> None:
        self._lists = lists
        self._orders = {order.order_id: order for order in orders}
        self._balances = balances
        self.calls: list[str] = []
        self.writes: list[str] = []

    def _write(self, name: str) -> Any:
        self.writes.append(name)
        raise AssertionError(f"a venue WRITE: {name}")

    def _unused(self, name: str) -> Any:
        raise AssertionError(f"a read the preview does not use: {name}")

    async def get_all_order_lists(self, **_kwargs: Any) -> list[OrderList]:
        self.calls.append("get_all_order_lists")
        return list(self._lists)

    async def get_order(
        self,
        symbol: str,
        *,
        order_id: str | None = None,
        client_order_id: str | None = None,
        timeout_s: float | None = None,
        attempts: int | None = None,
    ) -> Order:
        self.calls.append("get_order")
        if order_id is None:
            raise OrderNotFoundError("Order does not exist.")  # the close's sell is absent
        return self._orders[order_id]

    async def get_balances(self) -> list[Balance]:
        self.calls.append("get_balances")
        return list(self._balances)

    async def get_symbol_info(self, symbol: str) -> SymbolInfo:
        self.calls.append("get_symbol_info")
        return FILTERS[symbol]

    async def close(self) -> None:
        self.calls.append("close")

    async def create_order(self, request: Any) -> Any:
        return self._write("create_order")

    async def cancel_order(self, symbol: str, order_id: str) -> Any:
        return self._write("cancel_order")

    async def cancel_order_list(self, *args: Any, **kwargs: Any) -> Any:
        return self._write("cancel_order_list")

    async def create_oto_order_list(self, *args: Any, **kwargs: Any) -> Any:
        return self._write("create_oto_order_list")

    async def create_otoco_order_list(self, *args: Any, **kwargs: Any) -> Any:
        return self._write("create_otoco_order_list")

    async def get_klines(self, *args: Any, **kwargs: Any) -> Any:
        return self._unused("get_klines")

    async def get_ticker(self, *args: Any, **kwargs: Any) -> Any:
        return self._unused("get_ticker")

    async def get_my_trades(self, *args: Any, **kwargs: Any) -> Any:
        return self._unused("get_my_trades")

    async def get_open_orders(self, *args: Any, **kwargs: Any) -> Any:
        return self._unused("get_open_orders")

    async def get_own_open_orders(self, *args: Any, **kwargs: Any) -> Any:
        return self._unused("get_own_open_orders")


def _live_client() -> ReadOnlyClient:
    """The position's list is live and its entry filled: the boot would ``Restore``."""
    legs = [
        leg(W, OrderStatus.FILLED, QTY),
        leg(SL, OrderStatus.NEW),
        leg(TP, OrderStatus.NEW),
    ]
    return ReadOnlyClient(
        lists=[order_list(SYMBOL, status="EXECUTING")], orders=legs, balances=base(QTY)
    )


def _factory(client: ExchangeClient) -> Any:
    async def build() -> ExchangeClient:
        return client

    return build


class TestRefusals:
    def test_a_held_instance_lock_refuses_and_changes_nothing(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """MUTATION: skip the lock check.

        The lock is taken here by the test and so is held when ``main`` tries
        for it. The store is compared by SHA-256, and the operator is never
        asked, so a tool that skipped the check would fail the SHA or the prompt.
        """
        before = _write()

        with acquire(DEFAULT_LOCK_PATH):
            rc = main(["--symbol", SYMBOL], input_fn=_never_asked)

        assert rc == 1
        assert _sha() == before
        assert "instance lock is held" in capsys.readouterr().out
        assert not release_position.RELEASE_LOG_PATH.exists()

    def test_an_unknown_symbol_aborts_with_nothing_written(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        before = _write()

        rc = main(["--symbol", "XRPUSDT"], input_fn=_never_asked)

        assert rc == 1
        assert _sha() == before
        assert "holds no record for XRPUSDT" in capsys.readouterr().out
        assert not release_position.RELEASE_LOG_PATH.exists()

    def test_a_missing_store_refuses(self, capsys: pytest.CaptureFixture[str]) -> None:
        rc = main(["--symbol", SYMBOL], input_fn=_never_asked)

        assert rc == 1
        assert "there is no store" in capsys.readouterr().out
        assert not STORE.exists()

    def test_a_corrupt_store_refuses_and_is_left_as_it_was(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        STORE.parent.mkdir(parents=True, exist_ok=True)
        STORE.write_bytes(b'{"schema": 99, "pending": []}')
        before = _sha()

        rc = main(["--symbol", SYMBOL], input_fn=_never_asked)

        assert rc == 1
        assert _sha() == before
        assert "store is corrupt" in capsys.readouterr().out
        assert not release_position.RELEASE_LOG_PATH.exists()

    def test_a_confirmation_mismatch_aborts_with_nothing_written(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """MUTATION: skip the confirmation check. Case counts: ``btcusdt`` is not ``BTCUSDT``."""
        before = _write()

        rc = main(["--symbol", SYMBOL], input_fn=_confirm("btcusdt"))

        assert rc == 1
        assert _sha() == before
        assert "not typed exactly" in capsys.readouterr().out
        assert not release_position.RELEASE_LOG_PATH.exists()


class TestTheRelease:
    def test_only_the_named_symbols_records_are_removed_and_the_rest_kept_byte_for_byte(
        self,
    ) -> None:
        """MUTATION: remove every record.

        Compared as the file's own JSON, entry by entry: the other symbol's
        position and placement, the ledger, the history and the lifetime total
        must serialise to exactly what they were.
        """
        _write()
        before = json.loads(STORE.read_text(encoding="utf-8"))

        rc = main(["--symbol", SYMBOL], input_fn=_confirm(SYMBOL), clock=lambda: NOW)

        assert rc == 0
        after = json.loads(STORE.read_text(encoding="utf-8"))
        assert [e["symbol"] for e in after["positions"]] == [KEPT]
        assert [e["symbol"] for e in after["pending"]] == [OTHER]

        def kept(payload: dict[str, Any]) -> str:
            others = {
                **payload,
                "positions": [e for e in payload["positions"] if e["symbol"] != SYMBOL],
                "pending": [e for e in payload["pending"] if e["symbol"] != SYMBOL],
            }
            return json.dumps(others, sort_keys=True)

        assert kept(before) == json.dumps(after, sort_keys=True)
        assert after["ledger"] == before["ledger"]
        assert after["lifetime_realised"] == before["lifetime_realised"]

    def test_the_release_goes_through_store_save_once(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """MUTATION: write the file directly instead of through ``store.save``.

        A spy wraps the real ``save`` so the write still happens, and records
        what it was handed. Atomicity is ``save``'s own (temp file, fsync,
        replace); what this pins is that the tool uses it.
        """
        _write()
        calls: list[tuple[store.PersistedState, Path]] = []
        real_save = store.save

        def spy(state: store.PersistedState, path: Path = store.DEFAULT_STORE_PATH) -> None:
            calls.append((state, path))
            real_save(state, path)

        monkeypatch.setattr(store, "save", spy)

        rc = main(["--symbol", SYMBOL], input_fn=_confirm(SYMBOL), clock=lambda: NOW)

        assert rc == 0
        assert len(calls) == 1
        saved, path = calls[0]
        assert path == STORE
        assert all(r.symbol != SYMBOL for r in (*saved.positions, *saved.pending))
        assert len(saved.positions) + len(saved.pending) == 2

    def test_the_release_log_line_carries_both_digests_and_the_removed_records(self) -> None:
        before = _write()

        rc = main(["--symbol", SYMBOL], input_fn=_confirm(SYMBOL), clock=lambda: NOW)

        assert rc == 0
        after = _sha()
        assert after != before
        lines = release_position.RELEASE_LOG_PATH.read_text(encoding="utf-8").splitlines()
        assert len(lines) == 1
        list_id = list_client_order_id(SYMBOL, BAR, generation=0)
        assert lines[0].startswith("2026-10-01T12:00:00+00:00 released symbol=BTCUSDT ")
        assert f"removed=[position:{list_id},close:{list_id}]" in lines[0]
        assert f"store_sha256_before={before}" in lines[0]
        assert f"store_sha256_after={after}" in lines[0]

    def test_the_lock_is_released_on_exit(self) -> None:
        """The tool holds the lock for its own run and not a moment longer."""
        _write()

        assert main(["--symbol", SYMBOL], input_fn=_confirm(SYMBOL), clock=lambda: NOW) == 0

        with acquire(DEFAULT_LOCK_PATH):
            pass

    def test_a_store_option_names_another_file(self) -> None:
        other = Path("elsewhere.json")
        store.save(_state(), other)
        before = _write()

        rc = main(
            ["--symbol", SYMBOL, "--store", str(other)],
            input_fn=_confirm(SYMBOL),
            clock=lambda: NOW,
        )

        assert rc == 0
        assert _sha() == before  # the default store was never touched
        assert [r.symbol for r in store.load(other).positions] == [KEPT]  # type: ignore[union-attr]


class TestThePreview:
    def test_preview_reads_only_and_says_what_the_boot_would_decide(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """A fake that raises on any write, and on any read the preview does not use.

        The operator then types the wrong symbol, so the run aborts and the
        assertion on the store holds without a release having happened.
        """
        before = _write()
        client = _live_client()

        rc = main(
            ["--symbol", SYMBOL, "--preview"],
            input_fn=_confirm("no"),
            client_factory=_factory(client),
        )

        assert rc == 1
        assert _sha() == before
        assert client.writes == []
        assert set(client.calls) <= {
            "get_all_order_lists",
            "get_order",
            "get_balances",
            "get_symbol_info",
            "close",
        }
        assert "get_all_order_lists" in client.calls
        out = capsys.readouterr().out
        assert "Restore: the list is live" in out
        assert "close sell id" in out  # the close beside the record was read too

    def test_an_unreadable_venue_prints_unavailable_and_the_release_still_goes_on(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        _write()

        async def broken() -> ExchangeClient:
            raise ExchangeConnectionError("no route to host")

        rc = main(
            ["--symbol", SYMBOL, "--preview"],
            input_fn=_confirm(SYMBOL),
            client_factory=broken,
            clock=lambda: NOW,
        )

        assert rc == 0
        out = capsys.readouterr().out
        assert "preview unavailable: ExchangeConnectionError: no route to host" in out
        assert [r.symbol for r in store.load(STORE).positions] == [KEPT]  # type: ignore[union-attr]


class TestTheMessagesNameTheTool:
    HELD = HeldExit(
        order_id="3189811",
        cause="foreign_fee_asset",
        reason="order 3189811 is charged in ['BNB']",
        fees=(Fee(amount=D("0.00003000"), asset="BNB"),),
    )

    def test_the_hold_message_names_the_release_command(self) -> None:
        """MUTATION: restore "Enter this trade by hand, then restart".

        ``M5l-143``: the old sentence told an operator to restart, and a restart
        keeps the hold. The command is the tool's own ``COMMAND``, so the
        message and the tool cannot drift apart.
        """
        fields = hold_fields(self.HELD, quote_asset="USDT", quantity=D("0.0231"), quote_total=None)

        resolution = fields["resolution"]
        assert isinstance(resolution, str)
        assert f"Resolve it at the venue, then release the record: {COMMAND} <SYMBOL>" in resolution
        assert "Enter this trade by hand" not in resolution
        assert (Path(release_position.__file__)).name == "release_position.py"

    def test_the_boot_messages_quote_the_tools_own_command(self) -> None:
        """The boot quotes the command in three places from one constant; the script owns it."""
        from trading_bot.engine import modes

        assert f"{COMMAND} <SYMBOL>" == modes._RELEASE_COMMAND
        assert modes._RELEASE_COMMAND in modes._RELEASE_HINT
        assert modes._RELEASE_COMMAND in modes._BOOT_HOLD_RESOLUTION
