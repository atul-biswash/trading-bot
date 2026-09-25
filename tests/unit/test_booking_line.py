"""Tests for the booking line's settlement fields -- one field set, three emitters.

The helper is pure, so its own tests need no client and no clock. What the
three emitters actually log is pinned beside each of them, in
``test_reconciliation_driver.py`` and ``test_executor.py``; the census below is
what holds them to this helper rather than to three hand-kept copies.
"""

from __future__ import annotations

import ast
import inspect
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from types import ModuleType

from trading_bot.core.models import ExitSettlement, Fee, HeldExit
from trading_bot.execution import executor as executor_module
from trading_bot.execution import reconciliation_driver as driver_module
from trading_bot.execution.booking_line import (
    disagreement_fields,
    hold_fields,
    quote_total_fields,
    settlement_fields,
)

D = Decimal
FILLED_AT = datetime(2026, 9, 17, 9, 48, 5, 916000, tzinfo=timezone.utc)
#: The order record's timestamp, DELIBERATELY apart from the fill time, so a
#: helper that swapped the two would change both values.
CREATED_AT = FILLED_AT - timedelta(minutes=41)

#: FABRICATED fee `0.37000000` USDT -- every captured SELL fee is zero, so a
#: zero could not tell the fee from a missing one.
SETTLEMENT = ExitSettlement(
    order_id="3189811",
    fee=Fee(amount=D("0.37000000"), asset="USDT"),
    quote_quantity=D("1772.00890360"),
    quantity=D("0.02314000"),
    filled_at=FILLED_AT,
    fill_count=2,
)

#: The field keys the booking lines take from the settlement and nowhere else.
#: A site that still wrote one of these itself would be a second copy of the
#: field set, and a dict display keeps the LAST of two equal keys silently.
_SETTLEMENT_ONLY_KEYS = ("fee", "fee_asset", "fills", "filled_at", "order_created_at")


def test_the_fields_are_the_settlements_own_values_as_whitelist_types() -> None:
    """All SEVEN, by value AND by type. MUTATION: send `filled_at` as a `datetime`,
    drop any field, or read `quote_quantity` where `quantity` is meant.

    The types are asserted separately from the values because `default=str`
    would carry a `datetime` into the JSON sink without error, and the two
    sinks would then render it differently -- the whitelist rule's failure.
    """
    fields = settlement_fields(SETTLEMENT, order_created_at=CREATED_AT)

    assert fields == {
        "order_id": "3189811",
        "quantity": D("0.02314000"),
        "fee": D("0.37000000"),
        "fee_asset": "USDT",
        "fills": 2,
        "filled_at": FILLED_AT.isoformat(),
        "order_created_at": CREATED_AT.isoformat(),
    }
    assert {key: type(value) for key, value in fields.items()} == {
        "order_id": str,
        "quantity": Decimal,
        "fee": Decimal,
        "fee_asset": str,
        "fills": int,
        "filled_at": str,
        "order_created_at": str,
    }
    # The exponent crosses unchanged: `Decimal` equality above is numeric.
    assert str(fields["fee"]) == "0.37000000"
    assert str(fields["quantity"]) == "0.02314000"


def test_an_unknown_order_time_is_omitted_not_null() -> None:
    """ABSENT, never `None`. MUTATION: emit `"order_created_at": None`.

    `not in` is the only assertion that separates the two: `.get()` answers
    `None` for both, which is exactly the distinction the schema rule draws.
    """
    fields = settlement_fields(SETTLEMENT, order_created_at=None)

    assert "order_created_at" not in fields
    assert set(fields) == {"order_id", "quantity", "fee", "fee_asset", "fills", "filled_at"}


def _functions_calling(module: ModuleType, name: str) -> set[str]:
    tree = ast.parse(Path(inspect.getfile(module)).read_text(encoding="utf-8"))
    return {
        fn.name
        for fn in ast.walk(tree)
        if isinstance(fn, ast.AsyncFunctionDef | ast.FunctionDef)
        for node in ast.walk(fn)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == name
    }


def _dict_keys(module: ModuleType) -> set[str]:
    tree = ast.parse(Path(inspect.getfile(module)).read_text(encoding="utf-8"))
    return {
        key.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Dict)
        for key in node.keys
        if isinstance(key, ast.Constant) and isinstance(key.value, str)
    }


def test_all_three_booking_lines_consume_the_helper() -> None:
    """The census: three emitters call it, and none writes its fields itself.

    MUTATION: inline Site B's dict -- `_book_resolved_close` writing
    `"fee": ..., "fee_asset": ...` where it spreads `settlement_fields`.

    Two assertions because each alone is satisfiable by the wrong tree: a
    site can CALL the helper and still write a key of its own beside it,
    which a dict display resolves by keeping the last silently; and a site
    can drop the call AND the keys, which the key census alone would pass.
    `order_id` and `quantity` are not in the key census: other lines in both
    modules carry them legitimately.
    """
    callers = _functions_calling(executor_module, "settlement_fields") | _functions_calling(
        driver_module, "settlement_fields"
    )

    assert callers == {"_log_booked", "_book_close", "_book_resolved_close"}
    for module in (executor_module, driver_module):
        written = _dict_keys(module) & set(_SETTLEMENT_ONLY_KEYS)
        assert written == set(), f"{module.__name__} writes {sorted(written)} itself"


#: The two keys `quote_total_fields` writes. **Extended at 3b-2b (D).**
_QUOTE_TOTAL_KEYS = ("quote_total", "quote_total_source")
_BOOKING_EMITTERS = {"_log_booked", "_book_close", "_book_resolved_close"}


def _literal_keys_in(module: ModuleType, function: str) -> set[str]:
    """Every string key ``function`` writes itself: a dict display's, or a subscript store's."""
    tree = ast.parse(Path(inspect.getfile(module)).read_text(encoding="utf-8"))
    keys: set[str] = set()
    for fn in ast.walk(tree):
        if not isinstance(fn, ast.AsyncFunctionDef | ast.FunctionDef) or fn.name != function:
            continue
        for node in ast.walk(fn):
            if isinstance(node, ast.Dict):
                keys |= {
                    k.value
                    for k in node.keys
                    if isinstance(k, ast.Constant) and isinstance(k.value, str)
                }
            elif (
                isinstance(node, ast.Subscript)
                and isinstance(node.ctx, ast.Store)
                and isinstance(node.slice, ast.Constant)
                and isinstance(node.slice.value, str)
            ):
                keys.add(node.slice.value)
    return keys


def test_all_three_booking_lines_write_their_total_through_the_provenance_helper() -> None:
    """D's census: the three emitters call ``quote_total_fields``, and none writes its keys.

    MUTATION: write ``"quote_total": total`` literally at any of the three, or
    drop ``quote_total_source`` from one line.

    **SCOPED TO THE THREE BOOKING EMITTERS, deliberately.** Other lines in both
    modules carry ``quote_total`` legitimately and without a source -- the
    deferral, the drop, the resolution and the hold lines report a figure the
    venue gave, not a booked one -- so a module-wide census of that key would
    forbid correct lines. ``quote_total_source``, which only a booking has, IS
    checked module-wide: no site may write it by hand.
    """
    callers = _functions_calling(executor_module, "quote_total_fields") | _functions_calling(
        driver_module, "quote_total_fields"
    )
    assert callers == _BOOKING_EMITTERS

    for module in (executor_module, driver_module):
        for function in _BOOKING_EMITTERS:
            written = _literal_keys_in(module, function) & set(_QUOTE_TOTAL_KEYS)
            assert written == set(), f"{module.__name__}.{function} writes {sorted(written)}"
        assert "quote_total_source" not in _dict_keys(module), (
            f"{module.__name__} writes quote_total_source itself"
        )


def test_the_provenance_fields_carry_the_total_beside_its_source() -> None:
    """D: both keys, by value and type, and nothing else. MUTATION: drop or swap either."""
    total = D("1786.22691640")

    fields = quote_total_fields(total, "fills")

    assert fields == {"quote_total": total, "quote_total_source": "fills"}
    assert fields["quote_total"] is total
    assert str(fields["quote_total"]) == "1786.22691640"


def test_the_disagreement_fields_pair_both_amounts_with_the_asset() -> None:
    """H: BOTH amounts, beside the one asset naming them, and the site. By value and type.

    FABRICATED amounts that DIFFER, so a helper that wrote one amount into
    both keys changes a value. MUTATION: drop the asset, or swap the amounts.
    """
    fields = disagreement_fields(
        order_id="3189811",
        venue_total=D("1772.00890360"),
        fills_total=D("1772.00000000"),
        quote_asset="USDT",
        site="reconciliation",
    )

    assert fields == {
        "order_id": "3189811",
        "venue_quote_total": D("1772.00890360"),
        "fills_quote_total": D("1772.00000000"),
        "quote_asset": "USDT",
        "site": "reconciliation",
    }
    assert {key: type(value) for key, value in fields.items()} == {
        "order_id": str,
        "venue_quote_total": Decimal,
        "fills_quote_total": Decimal,
        "quote_asset": str,
        "site": str,
    }


#: FABRICATED: a BNB fee and a USDT fee on one order -- no captured SELL fill
#: carries a non-USDT fee.
HELD = HeldExit(
    order_id="3189811",
    cause="foreign_fee_asset",
    reason="order 3189811 is charged in ['BNB', 'USDT']",
    fees=(Fee(amount=D("0.00003000"), asset="BNB"), Fee(amount=D("0.10000000"), asset="USDT")),
)


def test_the_hold_line_names_order_asset_amount_and_what_a_restart_does() -> None:
    """R2's one CRITICAL: what was held, each fee BESIDE its asset, and what to do.

    MUTATION: drop the restart sentence, or any instruction below. Each
    phrase is asserted against `resolution` alone, and none of them occurs in
    the other fields, so no phrase is satisfied by a neighbour (`M5i-126`).
    `quote_total` is OMITTED when unknown, never null.
    """
    fields = hold_fields(HELD, quote_asset="USDT", quantity=D("0.02314000"), quote_total=None)

    assert fields["order_id"] == "3189811"
    assert fields["cause"] == "foreign_fee_asset"
    assert fields["quantity"] == D("0.02314000")
    assert fields["fees"] == "0.00003000 BNB; 0.10000000 USDT"
    assert fields["reason"] == HELD.reason
    assert "quote_total" not in fields
    resolution = fields["resolution"]
    assert isinstance(resolution, str)
    for phrase in (
        "NOTHING WAS BOOKED",
        "DO NOT SELL IT BY HAND",
        "PORTFOLIO-WIDE",
        "Enter this trade by hand, then restart",
        "A restart releases the hold, because the position is not persisted",
        "subtracts only USDT",
    ):
        assert phrase in resolution, phrase

    with_total = hold_fields(
        HELD, quote_asset="USDT", quantity=D("0.02314000"), quote_total=D("1772.00890360")
    )
    assert with_total["quote_total"] == D("1772.00890360")
