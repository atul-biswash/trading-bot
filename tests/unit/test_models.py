"""Tests for domain models."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

import pytest
from pydantic import ValidationError

from trading_bot.core.enums import PositionSide, ProtectionState, SignalAction
from trading_bot.core.models import (
    Balance,
    OtocoOrderListRequest,
    OtoOrderListRequest,
    Position,
    Signal,
    Ticker,
)

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
    """Members arrive with their writers. An unwritten member is a plausible
    value sitting in the one field whose wrong value is *silent*: it does not
    fail, it switches off the detector that would have noticed.

    **INVERTED at M5e, not deleted, so the change of mind stays visible.** It
    read ``{ABSENT_BY_DESIGN, UNKNOWN}`` from M5a until
    ``execution.reconciliation.classify_protection`` landed, and it FAILED on
    the commit that added the other three -- which is the test working, not
    breaking. What it pins is unchanged: that every member has a writer. Only
    the set of writers grew.

    Kept as a literal here rather than derived from the classifier: that would
    import an outer layer's test helpers into the domain's own tests, and the
    one place `tests/` already couples two modules is recorded as a hazard. The
    derived form of this claim lives beside the classifier, in
    ``test_reconciliation.py``, where it costs no coupling.
    """
    assert set(ProtectionState) == {
        ProtectionState.ABSENT_BY_DESIGN,
        ProtectionState.UNKNOWN,
        ProtectionState.ACTIVE,
        ProtectionState.PENDING,
        ProtectionState.DIVERGED,
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


# --------------------------------------------------------------------------
# Order-list requests -- Q-C section 2's OTOCO and OTO rows
# --------------------------------------------------------------------------
def _otoco(**overrides: object) -> OtocoOrderListRequest:
    kwargs: dict[str, object] = {
        "symbol": "BTCUSDT",
        "quantity": Decimal("0.5"),
        "entry_limit": Decimal("100"),
        "stop_price": Decimal("90"),
        "take_profit": Decimal("120"),
        "entry_bar_time": BAR_TIME,
    }
    kwargs.update(overrides)
    return OtocoOrderListRequest(**kwargs)  # type: ignore[arg-type]


def _oto(**overrides: object) -> OtoOrderListRequest:
    kwargs: dict[str, object] = {
        "symbol": "BTCUSDT",
        "quantity": Decimal("0.5"),
        "entry_limit": Decimal("100"),
        "stop_price": Decimal("90"),
        "entry_bar_time": BAR_TIME,
    }
    kwargs.update(overrides)
    return OtoOrderListRequest(**kwargs)  # type: ignore[arg-type]


def test_an_otoco_request_carries_exactly_the_five_domain_facts_and_two_seeds() -> None:
    """Section 3's OTOCO set is SIXTEEN wire parameters; this is seven fields.

    Pinned as an exact set rather than a subset. A subset assertion would not
    notice a wire name arriving later -- and a domain type growing
    ``pendingAboveStopPrice`` is precisely the leak this commit exists to
    prevent.
    """
    assert set(OtocoOrderListRequest.model_fields) == {
        "symbol",
        "quantity",
        "entry_limit",
        "stop_price",
        "take_profit",
        "entry_bar_time",
        "generation",
    }


def test_an_oto_request_is_the_otoco_set_minus_the_above_leg() -> None:
    """Thirteen wire parameters, six fields. The difference between the two
    types is exactly one domain fact, even though the wire spelling also
    changes prefix (``pending*`` versus ``pendingAbove*``/``pendingBelow*``)."""
    otoco = set(OtocoOrderListRequest.model_fields)
    oto = set(OtoOrderListRequest.model_fields)

    assert otoco - oto == {"take_profit"}
    assert oto - otoco == set()


@pytest.mark.parametrize(
    "forbidden",
    [
        "pendingAbovePrice",
        "pendingAboveTimeInForce",
        "pendingBelowPrice",
        "pendingBelowTimeInForce",
    ],
)
@pytest.mark.parametrize(
    "model", [OtocoOrderListRequest, OtoOrderListRequest], ids=["otoco", "oto"]
)
def test_the_minus_1106_fields_are_unrepresentable(model: type, forbidden: str) -> None:
    """UNREPRESENTABLE, not rejected -- which is stronger, because a check can
    be deleted and a missing field cannot be read.

    Both protective legs are stop-market, so each carries exactly one price and
    there is no second price field to become a limit; and neither type has a
    time-in-force field at all. A mapper enumerating these fields has nothing to
    emit ``-1106`` from.
    """
    assert forbidden not in model.model_fields
    # The general form, not just these four spellings: no field mentions a
    # limit price or a time in force on a pending leg.
    assert not any("time_in_force" in name for name in model.model_fields)


@pytest.mark.parametrize(
    ("overrides", "match"),
    [
        ({"quantity": Decimal("0")}, "quantity must be > 0"),
        ({"entry_limit": Decimal("0")}, "entry_limit must be > 0"),
        ({"stop_price": Decimal("0")}, "stop_price must be > 0"),
        ({"take_profit": Decimal("0")}, "take_profit must be > 0"),
        ({"stop_price": Decimal("100")}, "not below entry_limit"),
        ({"take_profit": Decimal("100")}, "not above entry_limit"),
        ({"entry_bar_time": datetime(2026, 7, 25, 12, 0)}, "timezone-aware"),
        ({"generation": -1}, "greater than or equal to 0"),
    ],
    ids=["qty", "entry", "stop", "tp", "stop_above_entry", "tp_below_entry", "naive", "generation"],
)
def test_an_incoherent_otoco_request_is_refused(overrides: dict[str, object], match: str) -> None:
    """The two ORDERING rules are the ones that matter. Swap stop and target and
    the venue accepts the list happily -- it has no idea which leg we meant --
    and the position closes at a loss the moment it moves in our favour."""
    with pytest.raises(ValidationError, match=match):
        _otoco(**overrides)


@pytest.mark.parametrize(
    ("overrides", "match"),
    [
        ({"quantity": Decimal("0")}, "quantity must be > 0"),
        ({"entry_limit": Decimal("0")}, "entry_limit must be > 0"),
        ({"stop_price": Decimal("0")}, "stop_price must be > 0"),
        ({"stop_price": Decimal("100")}, "not below entry_limit"),
        ({"entry_bar_time": datetime(2026, 7, 25, 12, 0)}, "timezone-aware"),
    ],
    ids=["qty", "entry", "stop", "stop_above_entry", "naive"],
)
def test_an_incoherent_oto_request_is_refused(overrides: dict[str, object], match: str) -> None:
    with pytest.raises(ValidationError, match=match):
        _oto(**overrides)


@pytest.mark.parametrize(
    "field", ["quantity", "entry_limit", "stop_price", "take_profit"], ids=lambda f: str(f)
)
def test_every_price_and_quantity_is_money_not_decimal(field: str) -> None:
    """The one boundary where a ``numpy.float64`` from indicator maths could
    reach a submitted order price. ``Money`` is what stops it; a bare
    ``Decimal`` annotation would take the float and round-trip it silently."""
    with pytest.raises(ValidationError, match="float"):
        _otoco(**{field: 1.5})


def test_generation_defaults_to_zero_and_carries_no_venue_ceiling() -> None:
    """Bounded below only. The 0..99 ceiling is derived from the venue's
    36-character ID limit and lives in ``exchange/ids.py``; ``core/`` must not
    encode a venue constraint, and a request above it fails at ID generation --
    the boundary that owns it."""
    assert _otoco().generation == 0
    # Constructs happily: this type has no opinion about 500.
    assert _otoco(generation=500).generation == 500


@pytest.mark.parametrize("build", [_otoco, _oto], ids=["otoco", "oto"])
def test_an_order_list_request_is_frozen(build: object) -> None:
    request = build()  # type: ignore[operator]
    with pytest.raises(ValidationError):
        request.quantity = Decimal("1")
