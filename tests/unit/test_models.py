"""Tests for domain models."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

import pytest
from pydantic import ValidationError

from trading_bot.core.enums import PositionSide, ProtectionState, SignalAction
from trading_bot.core.models import Balance, Position, Signal, Ticker

#: A fixed bar close, so `entry_bar_time` is deterministic across a run.
BAR_TIME = datetime(2026, 7, 25, 12, 0, tzinfo=timezone.utc)


def test_balance_total() -> None:
    bal = Balance(asset="USDT", free=Decimal("100"), locked=Decimal("25"))
    assert bal.total == Decimal("125")


def test_ticker_mid() -> None:
    t = Ticker(
        symbol="BTCUSDT",
        bid=Decimal("100"),
        ask=Decimal("102"),
        last=Decimal("101"),
        timestamp=datetime.now(timezone.utc),
    )
    assert t.mid == Decimal("101")


def test_ticker_is_frozen() -> None:
    t = Ticker(
        symbol="BTCUSDT",
        bid=Decimal("100"),
        ask=Decimal("102"),
        last=Decimal("101"),
        timestamp=datetime.now(timezone.utc),
    )
    with pytest.raises(ValidationError):
        t.bid = Decimal("200")  # type: ignore[misc]


def test_position_unrealized_pnl_long() -> None:
    pos = Position(
        symbol="BTCUSDT",
        side=PositionSide.LONG,
        quantity=Decimal("2"),
        entry_price=Decimal("100"),
        entry_bar_time=BAR_TIME,
        protection=ProtectionState.UNKNOWN,
    )
    assert pos.unrealized_pnl(Decimal("110")) == Decimal("20")
    assert pos.unrealized_pnl(Decimal("90")) == Decimal("-20")


def test_position_unrealized_pnl_short() -> None:
    pos = Position(
        symbol="BTCUSDT",
        side=PositionSide.SHORT,
        quantity=Decimal("2"),
        entry_price=Decimal("100"),
        entry_bar_time=BAR_TIME,
        protection=ProtectionState.UNKNOWN,
    )
    assert pos.unrealized_pnl(Decimal("90")) == Decimal("20")


# --------------------------------------------------------------------------
# Money fields refuse to be built from binary floats
# --------------------------------------------------------------------------
def test_money_rejects_a_float() -> None:
    """The precision the data layer preserves must not be undone downstream.

    Without the guard pydantic coerces this silently and the signal carries a
    price that merely looks correct.
    """
    with pytest.raises(ValidationError, match="must not be built from a float"):
        Signal(symbol="BTCUSDT", action=SignalAction.BUY, price=65050.1)


def test_money_rejects_a_numpy_float() -> None:
    """``np.float64`` is a ``float`` subclass -- and is what ``iloc`` returns."""
    numpy = pytest.importorskip("numpy")

    with pytest.raises(ValidationError, match="must not be built from a float"):
        Balance(asset="USDT", free=numpy.float64(1.5), locked=Decimal(0))


def test_money_accepts_decimals_strings_and_ints() -> None:
    """All three convert exactly, so none of them can lose precision."""
    assert Balance(asset="USDT", free=Decimal("1.50"), locked=0).free == Decimal("1.50")
    assert Balance(asset="USDT", free="1.50", locked=0).free == Decimal("1.50")
    assert str(Balance(asset="USDT", free="1.50", locked=0).free) == "1.50"  # exponent kept


def test_money_guard_covers_optional_fields_too() -> None:
    with pytest.raises(ValidationError, match="must not be built from a float"):
        Position(
            symbol="BTCUSDT",
            side=PositionSide.LONG,
            quantity=Decimal("1"),
            entry_price=Decimal("100"),
            entry_bar_time=BAR_TIME,
            protection=ProtectionState.UNKNOWN,
            stop_loss=98.5,
        )


# --------------------------------------------------------------------------
# The guard survives mutation, not just construction
# --------------------------------------------------------------------------
def _open_position() -> Position:
    return Position(
        symbol="BTCUSDT",
        side=PositionSide.LONG,
        quantity=Decimal("1"),
        entry_price=Decimal("100"),
        entry_bar_time=BAR_TIME,
        protection=ProtectionState.UNKNOWN,
    )


def test_protection_has_no_default_and_a_site_that_forgets_it_cannot_construct() -> None:
    """The tempting default is ``ABSENT_BY_DESIGN``, and it is the wrong one: it
    asserts "no protection is expected here", which switches the divergence
    detector off for that position. A construction site that forgot the field
    would produce a position the reconciler had been told to ignore, and the
    instruction would have come from nobody. So there is no default, and
    forgetting it fails loudly at construction instead.
    """
    with pytest.raises(ValidationError, match="protection"):
        Position(
            symbol="BTCUSDT",
            side=PositionSide.LONG,
            quantity=Decimal("1"),
            entry_price=Decimal("100"),
            entry_bar_time=BAR_TIME,
        )


def test_entry_bar_time_and_opened_at_are_independent() -> None:
    """They answer different questions and neither replaces the other.
    ``opened_at`` is wall-clock and does not survive a restart; ``entry_bar_time``
    is the bar close the entry was decided on, and is what seeds a derivable
    client order ID -- which is precisely why it cannot be wall-clock.
    """
    later = datetime(2026, 7, 25, 13, 30, tzinfo=timezone.utc)
    pos = Position(
        symbol="BTCUSDT",
        side=PositionSide.LONG,
        quantity=Decimal("1"),
        entry_price=Decimal("100"),
        entry_bar_time=BAR_TIME,
        protection=ProtectionState.ABSENT_BY_DESIGN,
        opened_at=later,
    )
    assert pos.entry_bar_time == BAR_TIME
    assert pos.opened_at == later
    # The order-list identity and the reconciliation stamp start unknown.
    assert pos.order_list_id is None
    assert pos.last_reconciled_at is None


def test_protection_state_ships_only_the_members_that_have_writers() -> None:
    """Members arrive with their writers. ``PENDING`` / ``ACTIVE`` / ``DIVERGED``
    are named in the order-list contract and land in the milestones that first
    write them -- not before. An unwritten member is a plausible value sitting in
    the one field whose wrong value is *silent*: it does not fail, it switches
    off the detector that would have noticed.
    """
    assert set(ProtectionState) == {
        ProtectionState.ABSENT_BY_DESIGN,
        ProtectionState.UNKNOWN,
    }


def test_money_guard_survives_assignment_on_position() -> None:
    """``Position`` is the one mutable money model, so construction-time
    validation alone would leave the guard open exactly where it is written to.

    Pydantic validates at construction only unless ``validate_assignment`` is
    set; without it this assignment succeeds and stores a binary ``float`` in a
    ``Money`` field.
    """
    position = _open_position()

    with pytest.raises(ValidationError, match="must not be built from a float"):
        position.stop_loss = 98.5  # type: ignore[assignment]

    assert position.stop_loss is None  # the rejected write left no trace


#: Every ``Money`` field on ``Position``. Enumerated rather than sampled: the
#: guard is only as good as its least-covered field, and a future field added
#: without a test would be exactly the gap that goes unnoticed.
_POSITION_MONEY_FIELDS = [
    "quantity",
    "entry_price",
    "stop_loss",
    "take_profit",
    "trailing_stop",
    "highest_price",
    "lowest_price",
]


def test_money_field_list_is_complete() -> None:
    """Fails if a ``Money`` field is added to ``Position`` without being covered.

    Derived from the model rather than hand-maintained, so the parametrised
    tests below cannot silently fall behind the type they guard.
    """
    declared = {
        name for name, field in Position.model_fields.items() if "Decimal" in str(field.annotation)
    }
    assert set(_POSITION_MONEY_FIELDS) == declared


@pytest.mark.parametrize("field", _POSITION_MONEY_FIELDS)
def test_money_guard_covers_every_money_field_against_float(field: str) -> None:
    """The trailing-stop bookkeeping fields are the realistic leak path -- they
    are advanced from NumPy-derived market data on every bar -- but the guard is
    asserted on all seven, including the two set at entry."""
    position = _open_position()

    with pytest.raises(ValidationError, match="must not be built from a float"):
        setattr(position, field, 108.9)


@pytest.mark.parametrize("field", _POSITION_MONEY_FIELDS)
def test_money_guard_covers_every_money_field_against_numpy_float(field: str) -> None:
    """``np.float64`` is what ``DataFrame.iloc`` returns -- the leak path in
    practice, and a ``float`` subclass, so the same guard catches it. Asserted
    per field rather than on one sample, because ``numpy`` is how the value
    actually arrives."""
    numpy = pytest.importorskip("numpy")
    position = _open_position()

    with pytest.raises(ValidationError, match="must not be built from a float"):
        setattr(position, field, numpy.float64(108.9))


def test_valid_decimal_assignment_still_works_exactly() -> None:
    """The guard must not cost precision on the writes that are legitimate."""
    position = _open_position()

    position.trailing_stop = Decimal("108.90")
    position.highest_price = Decimal("110")

    assert position.trailing_stop == Decimal("108.90")
    assert str(position.trailing_stop) == "108.90"  # exponent preserved
    assert position.highest_price == Decimal("110")


def test_clearing_a_level_to_none_is_still_allowed() -> None:
    """``update_trailing_stop`` legitimately returns ``None`` while the trail is
    inactive, and ``advance_trailing_stop`` assigns it straight through."""
    position = _open_position()
    position.trailing_stop = Decimal("108.90")

    position.trailing_stop = None

    assert position.trailing_stop is None


# --------------------------------------------------------------------------
# Signal.metadata carries plain scalars only
# --------------------------------------------------------------------------
def _signal(**metadata: object) -> Signal:
    return Signal(symbol="BTCUSDT", action=SignalAction.BUY, metadata=metadata)


@pytest.mark.parametrize(
    ("label", "value"),
    [
        ("str", "sma_crossover"),
        ("int", 20),
        ("float", 1.5),
        ("bool", True),
        ("none", None),
    ],
)
def test_metadata_accepts_plain_scalars(label: str, value: object) -> None:
    """``bool`` is admitted deliberately: ``type(True) is int`` is False, so it
    had to be listed explicitly rather than arriving via ``int``."""
    assert _signal(**{label: value}).metadata[label] == value


def test_metadata_rejects_numpy_float() -> None:
    """The realistic leak: ``Series.iloc`` yields ``np.float64``, and it is a
    ``float`` subclass, so an ``isinstance`` check would let it through. Exact
    type matching is what stops it -- without ``core/`` importing numpy."""
    numpy = pytest.importorskip("numpy")

    with pytest.raises(ValidationError, match="must be a plain int/float/str/bool"):
        _signal(rsi=numpy.float64(71.5))


def test_metadata_rejects_numpy_int() -> None:
    numpy = pytest.importorskip("numpy")

    with pytest.raises(ValidationError, match="must be a plain int/float/str/bool"):
        _signal(period=numpy.int64(14))


def test_numpy_float_would_otherwise_pass_an_isinstance_check() -> None:
    """Pins the reason the guard cannot reuse ``_reject_float``'s mechanism.

    ``_reject_float`` rejects the whole float family, so ``isinstance`` is right
    there. Here ``float`` is allowed and ``np.float64`` is not, and no
    ``isinstance`` test separates them -- if this assertion ever flips, the
    metadata guard could be simplified.
    """
    numpy = pytest.importorskip("numpy")

    assert isinstance(numpy.float64(1.5), float)  # the trap
    assert type(numpy.float64(1.5)) is not float  # the way out


@pytest.mark.parametrize(
    ("label", "value"),
    [
        ("nested_dict", {"a": 1}),
        ("nested_list", [1, 2]),
        ("decimal", Decimal("1.5")),
        ("tuple", (1, 2)),
    ],
)
def test_metadata_rejects_containers_and_decimals(label: str, value: object) -> None:
    """These serialise through ``json.dumps(default=str)`` to a repr rather than
    failing, which is the same silent-corruption path as a NumPy scalar. A
    ``Decimal`` is rejected too: money belongs in typed fields, not diagnostics."""
    with pytest.raises(ValidationError, match="must be a plain int/float/str/bool"):
        _signal(**{label: value})


def test_metadata_keys_are_enforced_by_pydantic_not_this_guard() -> None:
    """Keys need no check of ours -- ``dict[str, object]`` already rejects a
    non-str key at construction, so the validator covers values only."""
    with pytest.raises(ValidationError):
        Signal(symbol="BTCUSDT", action=SignalAction.BUY, metadata={1: "a"})


def test_metadata_error_names_the_offending_key() -> None:
    """An operator needs to know *which* field leaked, not just that one did."""
    numpy = pytest.importorskip("numpy")

    with pytest.raises(ValidationError, match=r"metadata\['rsi'\]"):
        _signal(strategy="rsi_strategy", rsi=numpy.float64(71.5))


def test_empty_metadata_is_still_the_default() -> None:
    assert Signal(symbol="BTCUSDT", action=SignalAction.BUY).metadata == {}
