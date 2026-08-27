"""The canceller's guards, pinned so an edit cannot quietly remove them.

**Why these exist rather than a comment.**
``scripts/cancel_testnet_order_list.py`` issues a real ``DELETE`` against a
venue, and its safety rests on a hardcoded ``testnet=True``, on never reading
the live credential slot, and on proving ownership by *parsing* an id rather
than by matching its prefix. None of the three is visible to any gate this
project runs: ``ruff`` and ``mypy`` cannot tell a literal from a parameter, and
a future author swapping the parser for ``startswith`` would break nothing they
could see. These tests are what make that break loud.

**No test here touches the network.** The client is a fake satisfying the
script's own ``TestnetCancelAPI`` protocol, and the credential tests construct
``Secrets`` explicitly rather than reading ``.env``.

**What is NOT covered**, stated rather than left to be discovered: the venue
interaction itself. No test may make a network call, so the ``DELETE``'s
acceptance, its response shape and the re-read confirmation are unverified in
exactly the sense ``test_clear_testnet_holdings.py`` records for the seller.
"""

from __future__ import annotations

import sys
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from trading_bot.config.settings import Secrets
from trading_bot.core.exceptions import ConfigError
from trading_bot.exchange.ids import OrderListLeg

# `scripts/` is not a package and is outside `pythonpath`, so it is added here
# rather than restructured -- the script is a script, not library code.
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

import cancel_testnet_order_list as canceller

D = Decimal

_LIVE_KEY = "live-key-must-never-be-read"
_LIVE_SECRET = "live-secret-must-never-be-read"
_TESTNET_KEY = "testnet-key"
_TESTNET_SECRET = "testnet-secret"

#: The list-level id of the captured artefact, and a LEG id from the same list.
#: **Two identifier spaces, shaped so a reader can tell them apart by looking**
#: -- M5g-041's rule, which cost this milestone a defect when one constant
#: served both. The venue space is `int`, ours is `str`.
_OUR_LIST_ID = "tb1-BTCUSDT-1787781959999-0-L"
_OUR_WORKING_ID = "tb1-BTCUSDT-1787781959999-0-W"
_OUR_SL_ID = "tb1-BTCUSDT-1787781959999-0-SL"
_OUR_TP_ID = "tb1-BTCUSDT-1787781959999-0-TP"
_VENUE_LIST_ID = 255471
_VENUE_WORKING_ID = 8444799
_VENUE_SL_ID = 8444800
_VENUE_TP_ID = 8444801


def _secrets(*, testnet: bool, live: bool) -> Secrets:
    """A ``Secrets`` with either slot populated, built without reading ``.env``."""
    return Secrets(
        binance_api_key=_LIVE_KEY if live else "",
        binance_api_secret=_LIVE_SECRET if live else "",
        binance_testnet_api_key=_TESTNET_KEY if testnet else "",
        binance_testnet_api_secret=_TESTNET_SECRET if testnet else "",
    )


# --------------------------------------------------------------------------
# Fixtures: the leg array is VERBATIM from the payload captured at M5g-066;
# only the two status fields are set live, because the captured list had
# already terminated and the script exists for the state that has not.
# --------------------------------------------------------------------------
def _list_payload(
    *, status: str = "EXECUTING", list_client_order_id: str | None = _OUR_LIST_ID
) -> dict[str, Any]:
    return {
        "orderListId": _VENUE_LIST_ID,
        "contingencyType": "OTO",
        "listStatusType": "EXEC_STARTED",
        "listOrderStatus": status,
        "listClientOrderId": list_client_order_id,
        "symbol": "BTCUSDT",
        "orders": [
            {"symbol": "BTCUSDT", "orderId": _VENUE_WORKING_ID, "clientOrderId": _OUR_WORKING_ID},
            {"symbol": "BTCUSDT", "orderId": _VENUE_SL_ID, "clientOrderId": _OUR_SL_ID},
            {"symbol": "BTCUSDT", "orderId": _VENUE_TP_ID, "clientOrderId": _OUR_TP_ID},
        ],
    }


def _leg(client_id: str, order_id: int, *, status: str, executed: str, orig: str) -> dict[str, Any]:
    return {
        "symbol": "BTCUSDT",
        "orderId": order_id,
        "clientOrderId": client_id,
        "status": status,
        "executedQty": executed,
        "origQty": orig,
    }


def _legs(
    *, working_status: str = "NEW", working_executed: str = "0.00000000"
) -> dict[int, dict[str, Any]]:
    return {
        _VENUE_WORKING_ID: _leg(
            _OUR_WORKING_ID,
            _VENUE_WORKING_ID,
            status=working_status,
            executed=working_executed,
            orig="0.02310000",
        ),
        _VENUE_SL_ID: _leg(
            _OUR_SL_ID,
            _VENUE_SL_ID,
            status="PENDING_NEW",
            executed="0.00000000",
            orig="0.02310000",
        ),
        _VENUE_TP_ID: _leg(
            _OUR_TP_ID,
            _VENUE_TP_ID,
            status="PENDING_NEW",
            executed="0.00000000",
            orig="0.02310000",
        ),
    }


class _FakeClient:
    """Satisfies ``TestnetCancelAPI``; performs no I/O and records every call."""

    def __init__(
        self,
        *,
        payload: dict[str, Any] | None = None,
        legs: dict[int, dict[str, Any]] | None = None,
        open_lists: list[dict[str, Any]] | None = None,
        **kwargs: Any,
    ) -> None:
        self.kwargs = kwargs
        self.testnet = bool(kwargs.get("testnet", True))
        self.payload = payload if payload is not None else _list_payload()
        self.legs = legs if legs is not None else _legs()
        self.open_lists = open_lists if open_lists is not None else []
        self.cancelled: list[dict[str, Any]] = []
        self.queried: list[int] = []
        self.closed = False

    async def get_order(self, **params: Any) -> dict[str, Any]:
        order_id = int(params["orderId"])
        self.queried.append(order_id)
        return self.legs[order_id]

    async def v3_get_open_order_list(self, **params: Any) -> list[dict[str, Any]]:
        return self.open_lists

    async def v3_get_order_list(self, **params: Any) -> dict[str, Any]:
        return self.payload

    async def v3_delete_order_list(self, **params: Any) -> dict[str, Any]:
        self.cancelled.append(params)
        # A cancel collapses the list, so every later read sees it terminal.
        self.payload = {**self.payload, "listOrderStatus": "ALL_DONE"}
        return self.payload

    async def close_connection(self) -> None:
        self.closed = True


def _factory(**overrides: Any) -> Any:
    async def create(**kwargs: Any) -> Any:
        return _FakeClient(**{**kwargs, **overrides})

    return create


# --------------------------------------------------------------------------
class TestClientFactory:
    async def test_the_factory_is_passed_testnet_true(self) -> None:
        """Catches a parameterised endpoint -- `testnet=mode` instead of a literal."""
        client = await canceller.build_client(
            _factory(), secrets=_secrets(testnet=True, live=False)
        )
        assert client.kwargs["testnet"] is True  # type: ignore[attr-defined]

    async def test_a_client_that_does_not_report_testnet_is_refused(self) -> None:
        """Catches trusting the argument instead of reading the library's state.

        A flag that was *passed* and a flag that *took effect* are different
        facts, and only the second one protects anything.
        """
        with pytest.raises(ConfigError, match="does not report testnet=True"):
            await canceller.build_client(
                _factory(testnet=False), secrets=_secrets(testnet=True, live=False)
            )


class TestCredentials:
    async def test_the_live_key_slot_is_never_read(self) -> None:
        """Catches `binance_credentials()` creeping back in.

        That function falls back to the LIVE slot when the testnet slot is
        blank, so this exact state -- live populated, testnet empty -- is the
        one where the two implementations differ.
        """
        with pytest.raises(ConfigError, match="will not fall back to the live"):
            await canceller.build_client(_factory(), secrets=_secrets(testnet=False, live=True))

    def test_the_testnet_pair_is_what_is_returned(self) -> None:
        assert canceller._testnet_credentials(_secrets(testnet=True, live=True)) == (
            _TESTNET_KEY,
            _TESTNET_SECRET,
        )

    def test_a_half_populated_testnet_slot_refuses(self) -> None:
        """Catches an `or` where an `and` belongs -- one blank key is still unusable."""
        half = Secrets(
            binance_testnet_api_key=_TESTNET_KEY,
            binance_testnet_api_secret="",
        )
        with pytest.raises(ConfigError, match="must both be set"):
            canceller._testnet_credentials(half)


class TestSymbolAllowlist:
    def test_a_symbol_outside_the_allowlist_is_refused(self) -> None:
        """Catches the allowlist being widened to an open argument."""
        with pytest.raises(ConfigError, match="refusing SOLUSDT"):
            canceller.check_symbol_allowed("SOLUSDT")

    def test_both_configured_symbols_are_allowed(self) -> None:
        """Catches an allowlist narrowed to one symbol, which the other tests miss."""
        canceller.check_symbol_allowed("BTCUSDT")
        canceller.check_symbol_allowed("ETHUSDT")


class TestOwnership:
    """**Catches a prefix match replacing the parser.**

    ``startswith("tb1-")`` admits every case below except the foreign one, so
    these are the tests that discriminate parsing from prefix matching.
    """

    def test_our_own_list_id_yields_its_symbol(self) -> None:
        assert canceller.owning_symbol(_OUR_LIST_ID) == "BTCUSDT"

    @pytest.mark.parametrize(
        ("value", "why"),
        [
            ("x-HNA2TXFJ1a2b3c", "the library's own tag -- a foreign id"),
            ("tb1-garbage", "our prefix with a body that does not parse"),
            ("tb1-BTC-USDT-1787781959999-0-L", "a hyphenated symbol"),
            (_OUR_SL_ID, "a LEG id where a LIST id is required"),
        ],
    )
    def test_an_id_that_is_not_one_of_our_list_ids_is_refused(self, value: str, why: str) -> None:
        with pytest.raises(ConfigError, match="refusing"):
            canceller.owning_symbol(value)

    def test_an_absent_list_client_order_id_is_refused(self) -> None:
        """Catches treating a missing id as permission.

        ``OrderList.list_client_order_id`` documents that ``None`` carries no
        meaning on a *placement response*; on a read-back it is the only thing
        proving the list is ours, so absence must refuse rather than pass.
        """
        with pytest.raises(ConfigError, match="nothing to prove it was placed"):
            canceller.owning_symbol(None)

    def test_an_empty_list_client_order_id_is_refused(self) -> None:
        with pytest.raises(ConfigError, match="nothing to prove it was placed"):
            canceller.owning_symbol("")


class TestTerminalStatus:
    @pytest.mark.parametrize("status", ["ALL_DONE", "REJECT"])
    def test_terminal_statuses_are_terminal(self, status: str) -> None:
        assert canceller.is_terminal(status) is True

    @pytest.mark.parametrize("status", ["EXECUTING", "EXEC_STARTED", "SOMETHING_NEW", None])
    def test_everything_else_is_cancellable(self, status: str | None) -> None:
        """Catches the blacklist being inverted into a whitelist.

        An unrecognised status must read as cancellable here, the opposite of
        the boot block's direction: the venue refuses a terminal list harmlessly,
        while refusing a live one strands the operator with no remedy.
        """
        assert canceller.is_terminal(status) is False


class TestWorkingExposure:
    def test_an_unfilled_working_leg_leaves_nothing(self) -> None:
        legs = [canceller.to_leg_state(raw) for raw in _legs().values()]
        assert canceller.working_exposure(legs) == canceller.Exposure(D("0"), True)

    def test_a_partially_filled_working_leg_still_counts(self) -> None:
        """Catches `status == "FILLED"` used where `executedQty > 0` belongs.

        A partial fill leaves base behind exactly as a full one does, and a
        status test would report that case clean.
        """
        legs = [
            canceller.to_leg_state(raw)
            for raw in _legs(
                working_status="PARTIALLY_FILLED", working_executed="0.00500000"
            ).values()
        ]
        assert canceller.working_exposure(legs) == canceller.Exposure(D("0.00500000"), True)

    def test_no_identifiable_working_leg_is_not_reported_as_empty(self) -> None:
        """Catches conflating "nothing filled" with "we could not tell".

        Only the first is a safe verdict, and they must not share a code path.
        """
        foreign = _leg("x-HNA2TXFJ1a2b3c", 99, status="NEW", executed="0", orig="1")
        exposure = canceller.working_exposure([canceller.to_leg_state(foreign)])
        assert exposure.identified is False

    def test_a_leg_state_carries_decimals_not_floats(self) -> None:
        """Catches a float leaking in through the quantity fields."""
        state = canceller.to_leg_state(_legs()[_VENUE_WORKING_ID])
        assert isinstance(state.executed_qty, Decimal)
        assert isinstance(state.orig_qty, Decimal)
        assert state.leg is OrderListLeg.WORKING


class TestEnumerate:
    async def test_nothing_open_is_exit_zero_and_not_an_error(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Catches an empty account being reported as a failure.

        Nothing open is the state the whole cancel-then-sell sequence exists to
        reach; making it an error would render a correct account broken.
        """
        client = _FakeClient(open_lists=[])
        assert await canceller._enumerate(client) == 0
        assert "Nothing to cancel" in capsys.readouterr().out

    async def test_an_open_list_is_reported_with_its_venue_id(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        client = _FakeClient(open_lists=[_list_payload()])
        assert await canceller._enumerate(client) == 0
        assert str(_VENUE_LIST_ID) in capsys.readouterr().out

    async def test_enumerating_writes_nothing(self) -> None:
        client = _FakeClient(open_lists=[_list_payload()])
        await canceller._enumerate(client)
        assert client.cancelled == []


class TestCancelOne:
    async def test_a_dry_run_calls_no_write_method_at_all(self) -> None:
        """**Catches a dry run that writes.** The single most important test here.

        The default path must reach the venue only through signed GETs; if the
        `--execute` gate is ever removed or inverted, this is what reports it.
        """
        client = _FakeClient()
        assert await canceller._cancel_one(client, _VENUE_LIST_ID, execute=False) == 0
        assert client.cancelled == []

    async def test_a_dry_run_still_performs_the_per_leg_reads(self) -> None:
        """Catches the 1+N read being dropped back to a single list read-back.

        MEASURED: the list read-back carries no `status` and no `executedQty`,
        so without the per-leg queries the fill consequence cannot be known.
        """
        client = _FakeClient()
        await canceller._cancel_one(client, _VENUE_LIST_ID, execute=False)
        assert client.queried == [_VENUE_WORKING_ID, _VENUE_SL_ID, _VENUE_TP_ID]

    async def test_a_terminal_list_is_nothing_to_cancel(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Catches a terminal list being cancelled anyway, wasting a write."""
        client = _FakeClient(payload=_list_payload(status="ALL_DONE"))
        assert await canceller._cancel_one(client, _VENUE_LIST_ID, execute=True) == 0
        assert "NOTHING TO CANCEL" in capsys.readouterr().out
        assert client.cancelled == []

    async def test_a_terminal_list_is_not_even_read_per_leg(self) -> None:
        """Catches the terminal check being placed after the N reads.

        Ordering, not tidiness: a terminal list costs one read, not four.
        """
        client = _FakeClient(payload=_list_payload(status="ALL_DONE"))
        await canceller._cancel_one(client, _VENUE_LIST_ID, execute=True)
        assert client.queried == []

    async def test_a_filled_working_leg_warns_that_base_is_left_unprotected(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Catches the naked-base consequence going unstated.

        This is the state the forced `cancel -> sell -> boot` sequence exists
        for, and an operator who does not see it will cancel and then boot into
        an `UNMANAGED_HOLDING` block they were not warned about.
        """
        client = _FakeClient(legs=_legs(working_status="FILLED", working_executed="0.02310000"))
        await canceller._cancel_one(client, _VENUE_LIST_ID, execute=False)
        out = capsys.readouterr().out
        assert "UNPROTECTED and FREE" in out
        assert "0.02310000" in out
        assert "UNMANAGED_HOLDING" in out

    async def test_an_unfilled_working_leg_says_nothing_is_left_behind(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        client = _FakeClient()
        await canceller._cancel_one(client, _VENUE_LIST_ID, execute=False)
        assert "leaves no BTC behind" in capsys.readouterr().out

    async def test_a_foreign_list_is_refused_before_any_leg_is_read(self) -> None:
        """Catches ownership being checked after the reads, or not at all."""
        client = _FakeClient(payload=_list_payload(list_client_order_id="x-HNA2TXFJ1a2b3c"))
        with pytest.raises(ConfigError, match="not one of ours"):
            await canceller._cancel_one(client, _VENUE_LIST_ID, execute=True)
        assert client.queried == []
        assert client.cancelled == []

    async def test_execute_sends_the_venue_id_and_the_proved_symbol(self) -> None:
        """Catches the two identifier spaces being crossed -- M5g-040's defect.

        The selector on the wire is the VENUE numeric id; the symbol beside it
        is the one proved by parsing OUR client id. Neither may be the other.
        """
        client = _FakeClient()
        assert await canceller._cancel_one(client, _VENUE_LIST_ID, execute=True) == 0
        assert client.cancelled == [
            {"symbol": "BTCUSDT", "orderListId": _VENUE_LIST_ID, "recvWindow": 5000}
        ]

    async def test_a_list_that_does_not_go_terminal_after_the_cancel_reports_failure(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Catches the post-cancel confirmation being dropped.

        A `DELETE` that returns without the list going terminal is the state an
        operator must not read as success.
        """

        class _StubbornClient(_FakeClient):
            async def v3_delete_order_list(self, **params: Any) -> dict[str, Any]:
                self.cancelled.append(params)
                return self.payload  # never goes terminal

        client = _StubbornClient()
        assert await canceller._cancel_one(client, _VENUE_LIST_ID, execute=True) == 1
        assert "still reads" in capsys.readouterr().err


class TestInstanceLock:
    def test_main_takes_the_instance_lock(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Catches Departure 3 being removed.

        Cancelling protection under a running bot pulls resting legs out from
        under a `Position` the reconciler may have classified ACTIVE. Nothing
        else in this suite would notice the lock going away.
        """
        taken: list[bool] = []

        class _Lock:
            def __enter__(self) -> None:
                taken.append(True)

            def __exit__(self, *args: object) -> None:
                return None

        monkeypatch.setattr(canceller, "acquire_instance_lock", lambda: _Lock())
        monkeypatch.setattr(canceller.asyncio, "run", lambda coro: coro.close() or 0)
        assert canceller.main([]) == 0
        assert taken == [True]

    def test_a_held_lock_exits_two_and_writes_nothing(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Catches `InstanceLockedError` escaping as a traceback instead of exit 2.

        It is a `ConfigError`, so the handler already present maps it; this
        pins that no second exit convention is introduced.
        """
        from trading_bot.utils.instance_lock import InstanceLockedError

        def _refuse() -> None:
            raise InstanceLockedError("another instance is running; held by PID: 4242")

        ran: list[bool] = []
        monkeypatch.setattr(canceller, "acquire_instance_lock", _refuse)
        monkeypatch.setattr(canceller.asyncio, "run", lambda coro: ran.append(True) or 0)
        assert canceller.main([]) == 2
        assert "4242" in capsys.readouterr().err
        assert ran == []


class TestParser:
    def test_the_default_target_is_absent_not_zero(self) -> None:
        """Catches `default=0`, which argparse would make indistinguishable from a real id.

        `None` is what routes to the enumeration; `0` would route to a lookup of
        list zero.
        """
        assert canceller._build_parser().parse_args([]).order_list_id is None

    def test_execute_is_off_by_default(self) -> None:
        assert canceller._build_parser().parse_args([]).execute is False

    def test_the_venue_id_is_parsed_as_an_integer(self) -> None:
        args = canceller._build_parser().parse_args(["--order-list-id", "255471"])
        assert args.order_list_id == _VENUE_LIST_ID
