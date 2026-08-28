"""The X1 probe's guards, pinned so an edit cannot quietly remove them.

**Why these exist rather than a comment.** ``scripts/probe_x1.py`` is the
instrument that answers a measurement two supervised stop-outs failed to
answer, and its value rests on three properties no gate can see: that it calls
exactly one READ per leg and no write endpoint at all; that a missing order is
an answer rather than a crash; and that it refuses to claim attribution it has
not earned. ``ruff`` and ``mypy`` cannot tell a read from a write, and a future
author adding a "while we're here, cancel it" branch would break nothing they
could see.

**No test here touches the network.** The client is a fake exposing only
``get_order``; the write endpoints are present on it solely so a test can
assert they were never called.

**What is NOT covered**, stated rather than left to be discovered:

* The venue interaction itself. Nothing here exercises a real ``get_order``,
  its response shape, or whether a TRIGGERED stop leg populates
  ``cummulativeQuoteQty`` -- which is the whole question the script exists to
  ask. **These tests prove the instrument, not the measurement.**
* ``_probe``'s composition -- ``get_settings``, ``setup_logging``,
  ``BinanceClient.create`` and the ``finally`` teardown -- is exercised only
  through its parts. Faking the whole boot would pin the fake, not the script.
* The script has never been run. At the time these were written it had made
  zero venue calls.
"""

from __future__ import annotations

import sys
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from trading_bot.core.enums import OrderSide, OrderStatus, OrderType
from trading_bot.core.exceptions import ExchangeConnectionError, OrderNotFoundError
from trading_bot.core.models import Order

# `scripts/` is not a package and is outside `pythonpath`, so it is added here
# rather than restructured -- the script is a script, not library code.
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

import probe_x1 as probe

D = Decimal

SYMBOL = "ETHUSDT"

#: Run 5's real leg ids, used as fixtures because a realistic id is what a
#: reader checks against. They are NOT defaults in the script.
ENTRY_ID = "tb1-ETHUSDT-1787930999999-0-W"
EXIT_ID = "tb1-ETHUSDT-1787930999999-0-SL"


def _order(
    *,
    client_order_id: str,
    status: OrderStatus = OrderStatus.FILLED,
    filled: str = "0.72650000",
    average_price: str | None = "2506.42000000",
) -> Order:
    """One filled leg as ``to_order`` would hand it back."""
    return Order(
        order_id="1",
        symbol=SYMBOL,
        side=OrderSide.BUY,
        type=OrderType.LIMIT,
        status=status,
        quantity=D("0.72650000"),
        filled_quantity=D(filled),
        average_price=None if average_price is None else D(average_price),
        client_order_id=client_order_id,
    )


class _FakeClient:
    """Exposes ``get_order`` only; the write methods exist to be asserted unused."""

    def __init__(self, answers: dict[str, Any]) -> None:
        self._answers = answers
        self.get_order_calls: list[tuple[str, str]] = []
        self.write_calls: list[str] = []

    async def get_order(self, symbol: str, *, client_order_id: str) -> Order:
        self.get_order_calls.append((symbol, client_order_id))
        answer = self._answers[client_order_id]
        if isinstance(answer, Exception):
            raise answer
        return answer

    async def create_order(self, *args: Any, **kwargs: Any) -> None:
        self.write_calls.append("create_order")

    async def cancel_order(self, *args: Any, **kwargs: Any) -> None:
        self.write_calls.append("cancel_order")

    async def create_otoco_order_list(self, *args: Any, **kwargs: Any) -> None:
        self.write_calls.append("create_otoco_order_list")


class TestReadOnly:
    async def test_one_read_per_leg_and_no_write_ever(self) -> None:
        """The property the script's whole safety claim rests on."""
        client = _FakeClient(
            {ENTRY_ID: _order(client_order_id=ENTRY_ID), EXIT_ID: _order(client_order_id=EXIT_ID)}
        )
        failures: list[str] = []
        await probe._query(client, SYMBOL, "entry leg", ENTRY_ID, failures)  # type: ignore[arg-type]
        await probe._query(client, SYMBOL, "exit leg", EXIT_ID, failures)  # type: ignore[arg-type]

        assert client.get_order_calls == [(SYMBOL, ENTRY_ID), (SYMBOL, EXIT_ID)]
        assert client.write_calls == []
        assert failures == []

    def test_the_source_contains_no_write_endpoint(self) -> None:
        """Greps the file itself, because a call added on a branch no test
        reaches would satisfy every other test here."""
        source = (Path(__file__).resolve().parents[2] / "scripts" / "probe_x1.py").read_text(
            encoding="utf-8"
        )
        for forbidden in (
            "create_order(",
            "cancel_order(",
            "create_otoco_order_list(",
            "create_oto_order_list(",
        ):
            assert forbidden not in source, f"probe_x1.py must never call {forbidden}"

    def test_it_does_not_take_the_instance_lock(self) -> None:
        """A documented decision, pinned: a read must not be able to block a boot."""
        source = (Path(__file__).resolve().parents[2] / "scripts" / "probe_x1.py").read_text(
            encoding="utf-8"
        )
        assert "acquire_instance_lock" not in source

    def test_it_logs_through_the_bots_own_setup(self) -> None:
        """G16's remedy, pinned: a venue contact that leaves no trace is the
        defect this script was written to avoid repeating."""
        source = (Path(__file__).resolve().parents[2] / "scripts" / "probe_x1.py").read_text(
            encoding="utf-8"
        )
        assert "setup_logging(settings.config.logging)" in source


class TestMissingOrder:
    async def test_a_missing_order_is_an_answer_not_a_failure(self) -> None:
        """``OrderNotFoundError`` is the venue answering. It must not raise, and
        it must not be counted as a failed step -- otherwise "the id is wrong"
        and "the network is down" become indistinguishable."""
        client = _FakeClient({EXIT_ID: OrderNotFoundError("no such order")})
        failures: list[str] = []

        result = await probe._query(client, SYMBOL, "exit leg", EXIT_ID, failures)  # type: ignore[arg-type]

        assert result.found is False
        assert result.order is None
        assert failures == []

    async def test_a_transport_error_is_a_failure_unlike_a_missing_order(self) -> None:
        """The other half of the same distinction."""
        client = _FakeClient({EXIT_ID: ExchangeConnectionError("boom")})
        failures: list[str] = []

        result = await probe._query(client, SYMBOL, "exit leg", EXIT_ID, failures)  # type: ignore[arg-type]

        assert result.found is False
        assert failures == ["exit leg"]

    def test_reporting_a_missing_leg_does_not_crash(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        probe._report_leg(probe.LegResult("exit leg", EXIT_ID, None))
        assert "NOT FOUND at the venue" in capsys.readouterr().out


class TestNotional:
    def test_it_is_exact_in_decimal(self) -> None:
        """No float tolerance: a result that is merely close is a bug."""
        order = _order(client_order_id=EXIT_ID, filled="0.72650000", average_price="2458.25000000")
        assert probe.notional(order) == D("0.72650000") * D("2458.25000000")

    def test_an_absent_average_price_yields_none_rather_than_zero(self) -> None:
        """The distinction X1 exists to make. Zero would read as "no money
        moved"; ``None`` reads as "we do not know", which is the truth."""
        assert probe.notional(_order(client_order_id=EXIT_ID, average_price=None)) is None

    def test_an_absent_order_yields_none(self) -> None:
        assert probe.notional(None) is None


class TestArithmetic:
    def test_a_null_average_price_is_reported_as_a_result(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """X1's NO answer must arrive as a verdict, not a traceback."""
        entry = probe.LegResult("entry", ENTRY_ID, _order(client_order_id=ENTRY_ID))
        exit_ = probe.LegResult(
            "exit", EXIT_ID, _order(client_order_id=EXIT_ID, average_price=None)
        )

        probe._report_arithmetic(entry, exit_, D("34.99550500"))

        assert "UNDERDETERMINED" in capsys.readouterr().out

    def test_two_priced_legs_that_match_the_delta_attribute_it(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        entry = probe.LegResult(
            "entry", ENTRY_ID, _order(client_order_id=ENTRY_ID, average_price="2000")
        )
        exit_ = probe.LegResult(
            "exit", EXIT_ID, _order(client_order_id=EXIT_ID, average_price="1900")
        )
        # spent 0.7265 x 2000 = 1453; received 0.7265 x 1900 = 1380.35; net -72.65
        probe._report_arithmetic(entry, exit_, D("72.65"))

        assert "ATTRIBUTED EXACTLY" in capsys.readouterr().out

    def test_a_residual_is_reported_rather_than_rounded_away(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        entry = probe.LegResult(
            "entry", ENTRY_ID, _order(client_order_id=ENTRY_ID, average_price="2000")
        )
        exit_ = probe.LegResult(
            "exit", EXIT_ID, _order(client_order_id=EXIT_ID, average_price="1900")
        )
        probe._report_arithmetic(entry, exit_, D("70.00"))

        assert "NOT fully attributed" in capsys.readouterr().out

    def test_without_a_delta_no_attribution_is_claimed(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """A probe that asserted attribution against a number nobody supplied
        would be inventing the comparison."""
        entry = probe.LegResult("entry", ENTRY_ID, _order(client_order_id=ENTRY_ID))
        exit_ = probe.LegResult("exit", EXIT_ID, _order(client_order_id=EXIT_ID))

        probe._report_arithmetic(entry, exit_, None)

        out = capsys.readouterr().out
        assert "no comparison" in out
        assert "ATTRIBUTED" not in out


class TestEveryFieldIsEnumerated:
    def test_it_prints_every_field_the_model_carries(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Enumerated from the model, so a field nobody expected still appears --
        which is the point, since nothing has looked at this payload before."""
        probe._report_leg(probe.LegResult("entry", ENTRY_ID, _order(client_order_id=ENTRY_ID)))
        out = capsys.readouterr().out
        for field in Order.model_fields:
            assert field in out


class TestParser:
    def test_symbol_entry_and_exit_are_all_required(self) -> None:
        """No id has a default: a probe with a hardcoded target answers last
        week's question."""
        for argv in (
            ["--entry-leg", ENTRY_ID, "--exit-leg", EXIT_ID],
            ["--symbol", SYMBOL, "--exit-leg", EXIT_ID],
            ["--symbol", SYMBOL, "--entry-leg", ENTRY_ID],
        ):
            with pytest.raises(SystemExit):
                probe._build_parser().parse_args(argv)

    def test_the_account_delta_is_optional_and_defaults_to_absent(self) -> None:
        args = probe._build_parser().parse_args(
            ["--symbol", SYMBOL, "--entry-leg", ENTRY_ID, "--exit-leg", EXIT_ID]
        )
        assert args.account_delta is None

    def test_there_is_no_mode_flag(self) -> None:
        """Testnet-only by construction: no flag can select a live connection."""
        with pytest.raises(SystemExit):
            probe._build_parser().parse_args(
                [
                    "--symbol",
                    SYMBOL,
                    "--entry-leg",
                    ENTRY_ID,
                    "--exit-leg",
                    EXIT_ID,
                    "--mode",
                    "live",
                ]
            )


class TestMain:
    def test_a_non_numeric_account_delta_exits_two_without_connecting(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Config-shaped error, config exit code, and no client is built."""
        code = probe.main(
            [
                "--symbol",
                SYMBOL,
                "--entry-leg",
                ENTRY_ID,
                "--exit-leg",
                EXIT_ID,
                "--account-delta",
                "not-a-number",
            ]
        )
        assert code == 2
        assert "not a number" in capsys.readouterr().err
