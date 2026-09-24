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

from trading_bot.core.models import ExitSettlement, Fee
from trading_bot.execution import executor as executor_module
from trading_bot.execution import reconciliation_driver as driver_module
from trading_bot.execution.booking_line import settlement_fields

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
