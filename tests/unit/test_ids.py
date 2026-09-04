"""Tests for the Q-C section 6 client order ID scheme.

Pure functions, no network, no clock: every input is supplied. The suite's real
deliverable is the pair of guard tests -- an over-long ID and an illegal
character must be told apart *by the message*, because the venue's own message
cannot tell them apart (M5c-C).
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from trading_bot.core.exceptions import (
    ClientContractViolationError,
    ClientRefusalError,
    ContractViolationError,
    ExchangeAPIError,
)
from trading_bot.exchange.ids import (
    LIST_SUFFIX,
    MAX_CLIENT_ORDER_ID_LENGTH,
    MAX_GENERATION,
    ClientOrderIdParts,
    ListClientOrderIdParts,
    OrderListLeg,
    client_order_id,
    close_client_order_id,
    list_client_order_id,
    parse_client_order_id,
    parse_close_client_order_id,
    parse_list_client_order_id,
)

BAR = datetime(2026, 8, 14, 12, 0, tzinfo=timezone.utc)
BAR_MS = 1_786_708_800_000  # (BAR - epoch) in milliseconds, 13 digits

#: The members that really are legs of a Q-C section 3 order list.
#:
#: **DERIVED BY EXCLUSION, not listed by hand**, so a fifth member added later
#: joins these tests automatically and has to be excluded deliberately -- the
#: direction that fails loudly. Spelling the three out would let a new member
#: land untested with nothing to report it.
#:
#: ``CLOSE`` is excluded because it is not a leg: ``client_order_id`` refuses
#: it and ``parse_client_order_id`` will not read it. Both are pinned below.
LIST_LEGS = tuple(m for m in OrderListLeg if m is not OrderListLeg.CLOSE)


def test_generation_zero_is_derivable_and_deterministic() -> None:
    """Section 6's guarantee: gen 0 comes from ``(symbol, entry_bar_time)``
    alone, by pure computation. Pinned against a literal rather than against a
    re-derivation, so a change to the *form* fails here instead of agreeing with
    itself."""
    assert client_order_id("BTCUSDT", BAR, OrderListLeg.WORKING) == f"tb1-BTCUSDT-{BAR_MS}-0-W"
    # Called twice: "deterministic" is the claim, and one call cannot make it.
    assert client_order_id("BTCUSDT", BAR, OrderListLeg.WORKING) == client_order_id(
        "BTCUSDT", BAR, OrderListLeg.WORKING
    )


@pytest.mark.parametrize("leg", LIST_LEGS, ids=[m.value for m in LIST_LEGS])
def test_every_leg_round_trips(leg: OrderListLeg) -> None:
    """Generate then parse returns exactly what went in, including the leg.

    The generation is non-zero deliberately: at 0 a parser that dropped the
    segment and defaulted would still pass.
    """
    generated = client_order_id("ETHUSDT", BAR, leg, generation=7)

    assert parse_client_order_id(generated) == ClientOrderIdParts(
        symbol="ETHUSDT", entry_bar_time=BAR, generation=7, leg=leg
    )


@pytest.mark.parametrize("leg", LIST_LEGS, ids=[m.value for m in LIST_LEGS])
def test_the_leg_segment_is_the_value_not_the_member(leg: OrderListLeg) -> None:
    """`CLAUDE.md`'s ``str, Enum`` trap, pinned directly.

    MEASURED on this interpreter (3.12.10): ``f"{member}"`` yields
    ``"OrderListLeg.STOP_LOSS"``, not ``"SL"`` -- ``UP042`` is suppressed
    project-wide precisely so ``str(member)`` stays qualified. Interpolating the
    member would put a ``.`` in the ID and blow the length at once.

    Asserting the absence of the class name is what bites: an assertion that the
    ID merely *ends with* the value would also pass for
    ``"...-OrderListLeg.STOP_LOSS"`` if the enum were renamed to end in its own
    value.
    """
    generated = client_order_id("BTCUSDT", BAR, leg)

    assert "OrderListLeg" not in generated
    assert generated.endswith(f"-{leg.value}")


def test_an_over_long_id_reports_a_length_violation() -> None:
    """A 20-character symbol at the maximum generation overruns 36 while every
    character remains legal -- so only the length branch can be responsible."""
    with pytest.raises(ContractViolationError) as excinfo:
        client_order_id("A" * 20, BAR, OrderListLeg.STOP_LOSS, generation=MAX_GENERATION)

    message = str(excinfo.value)
    assert "LENGTH violation" in message
    assert str(MAX_CLIENT_ORDER_ID_LENGTH) in message
    # The exact type AND the ancestry, because `MalformedRequestError` is a
    # subclass and an `isinstance` check alone would keep passing if this
    # started returning one.
    assert type(excinfo.value) is ClientContractViolationError
    assert isinstance(excinfo.value, ExchangeAPIError)
    # The MARKER: this guard runs on our own assembled id, before any
    # request exists, so it is a client-side refusal by construction.
    assert isinstance(excinfo.value, ClientRefusalError)
    # No venue answered, so there is no code to carry -- the same reason
    # `BinanceRequestException` maps to `code=None`.
    assert excinfo.value.code is None


def test_an_illegal_character_reports_a_character_class_violation() -> None:
    """A short symbol carrying a ``.`` stays well inside 36, so only the
    character-class branch can be responsible."""
    with pytest.raises(ContractViolationError) as excinfo:
        client_order_id("BTC.USDT", BAR, OrderListLeg.WORKING)

    message = str(excinfo.value)
    assert "CHARACTER-CLASS violation" in message
    assert type(excinfo.value) is ClientContractViolationError


def test_the_two_violations_name_different_rules() -> None:
    """**The commit's real deliverable.** The venue reports a LENGTH violation as
    "Illegal characters found" (MEASURED, M5c-C), so its message cannot
    distinguish the two and anyone debugging an over-long ID goes looking for a
    bad character. This asserts the discrimination directly: each message names
    its own rule and denies the other. A single combined regex would reproduce
    the venue's misdiagnosis client-side, which is the failure this guard exists
    to prevent.
    """
    with pytest.raises(ContractViolationError) as long_exc:
        client_order_id("A" * 20, BAR, OrderListLeg.STOP_LOSS, generation=MAX_GENERATION)
    with pytest.raises(ContractViolationError) as char_exc:
        client_order_id("BTC.USDT", BAR, OrderListLeg.WORKING)

    long_message, char_message = str(long_exc.value), str(char_exc.value)

    assert "LENGTH violation" in long_message
    assert "CHARACTER-CLASS violation" not in long_message
    assert "CHARACTER-CLASS violation" in char_message
    assert "LENGTH violation" not in char_message


@pytest.mark.parametrize(
    "value",
    [
        "x-HNA2TXFJ7f3a91",  # library-tagged: what `create_order` injects
        "someHumanOrder",  # a person's order on the same symbol
        f"tb1-BTCUSDT-{BAR_MS}-0-XX",  # our prefix, leg outside the set
        f"tb1-BTC-USDT-{BAR_MS}-0-W",  # our prefix, hyphen inside the symbol
        f"tb1-BTCUSDT-{BAR_MS}-0",  # our prefix, leg segment missing
    ],
    ids=["library_tag", "foreign", "bad_leg", "hyphenated_symbol", "truncated"],
)
def test_an_id_that_is_not_ours_parses_to_none(value: str) -> None:
    """``None``, never a raise. Section 6 gives the prefix its purpose:
    ``get_open_orders`` returns *every* order on the symbol, so a reconciler
    filtering that list meets foreign IDs on every pass. Raising would make the
    ordinary case exceptional.
    """
    assert parse_client_order_id(value) is None


def test_a_naive_entry_bar_time_is_refused() -> None:
    """A naive value would be read as local time, moving the millisecond segment
    by the host's offset -- and the ID is supposed to be reproducible on any
    machine that restarts the bot."""
    with pytest.raises(ValueError, match="timezone-aware"):
        client_order_id("BTCUSDT", datetime(2026, 8, 14, 12, 0), OrderListLeg.WORKING)


@pytest.mark.parametrize("generation", [-1, MAX_GENERATION + 1], ids=["negative", "over"])
def test_a_generation_outside_the_bound_is_refused(generation: int) -> None:
    """The bound is derived, not chosen: ``20 + 12 + G + 2 <= 36`` for the
    longest symbol section 10 contemplates and the worst measured leg code."""
    with pytest.raises(ValueError, match="generation must be in"):
        client_order_id("BTCUSDT", BAR, OrderListLeg.WORKING, generation=generation)


@pytest.mark.parametrize("symbol", ["BTCUSDT", "ETHUSDT"])
def test_the_shipped_symbols_fit_at_the_maximum_generation(symbol: str) -> None:
    """Headroom, asserted rather than reasoned. The worst case is a 2-character
    leg at the maximum generation; on the shipped pairs that is 31 characters
    against a limit of 36.
    """
    generated = client_order_id(symbol, BAR, OrderListLeg.STOP_LOSS, generation=MAX_GENERATION)

    assert len(generated) <= MAX_CLIENT_ORDER_ID_LENGTH
    assert len(generated) == 31


# --------------------------------------------------------------------------
# The LIST-level identity -- an extension of section 6, which defines legs only
# --------------------------------------------------------------------------
def test_the_list_id_uses_the_list_suffix_and_the_same_seeds() -> None:
    """Section 3 requires ``listClientOrderId`` on both shapes and section 6
    gives it no form, so one is chosen here on the same terms: same seeds, same
    guard, same bound, differing only in the suffix."""
    assert list_client_order_id("BTCUSDT", BAR) == f"tb1-BTCUSDT-{BAR_MS}-0-{LIST_SUFFIX}"
    assert LIST_SUFFIX not in {member.value for member in OrderListLeg}


def test_the_list_id_is_not_a_leg_and_does_not_parse_as_one() -> None:
    """A list is not a leg, and the LEG parser is about legs.

    Not a gap: a list ID never appears in ``get_open_orders``, which returns
    orders, so the foreign-ID filter that parser exists for never meets one.
    Asserted rather than assumed, because the natural reading of "parse our IDs"
    would include it.

    **ANNOTATED: the assertion is unchanged and the paragraph above is now the
    reason for only half of it.** "There is no list parser" was true when this
    was written and is not: ``parse_list_client_order_id`` serves
    ``get_all_order_lists``, an endpoint that does return list IDs. What this
    test pins is the DISJOINTNESS -- the leg parser still refuses a list ID --
    which matters more now than it did, because there are two parsers to keep
    apart rather than one to keep narrow.
    """
    assert parse_client_order_id(list_client_order_id("BTCUSDT", BAR)) is None


@pytest.mark.parametrize("generation", [-1, MAX_GENERATION + 1], ids=["negative", "over"])
def test_the_list_id_shares_the_generation_bound(generation: int) -> None:
    """Shared through one assembly helper, so leg and list cannot drift apart in
    their bound, their epoch arithmetic or their guard."""
    with pytest.raises(ValueError, match="generation must be in"):
        list_client_order_id("BTCUSDT", BAR, generation=generation)


def test_the_list_id_shares_the_naive_time_refusal() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        list_client_order_id("BTCUSDT", datetime(2026, 8, 14, 12, 0))


def test_the_list_id_round_trips() -> None:
    """Generate then parse recovers every seed the string carries.

    The generation is non-zero for the reason the leg round-trip gives: at 0 a
    parser that dropped the segment and defaulted would still pass.
    """
    generated = list_client_order_id("ETHUSDT", BAR, generation=7)

    assert parse_list_client_order_id(generated) == ListClientOrderIdParts(
        symbol="ETHUSDT", entry_bar_time=BAR, generation=7
    )


def test_a_leg_id_does_not_parse_as_a_list() -> None:
    """The mirror of ``test_the_list_id_is_not_a_leg_and_does_not_parse_as_one``,
    and the pair is what makes the two parsers DISJOINT rather than merely
    narrow.

    Each test alone permits a parser that accepts both forms in one direction.
    Together they forbid it, which is what a later hand widening either suffix
    group would break -- and widening the LEG group is the dangerous one, since
    ``_compare_set`` would reach ``OrderListLeg("L")`` and raise ``ValueError``
    where it promises ``ContractViolationError``.

    **Scoped to ``LIST_LEGS`` rather than every member**, because
    ``client_order_id`` now refuses ``CLOSE`` -- see
    ``test_the_leg_builder_refuses_the_close_code``. The close form's
    disjointness from both other families is asserted separately, in
    ``test_a_close_id_does_not_parse_as_a_leg_and_a_leg_does_not_parse_as_a_close``.
    """
    for leg in LIST_LEGS:
        assert parse_list_client_order_id(client_order_id("BTCUSDT", BAR, leg)) is None


@pytest.mark.parametrize(
    "value",
    [
        "x-HNA2TXFJ7f3a91",  # library-tagged: what `create_order` injects
        "tb1-garbage",  # THE PREFIX-MATCHING REGRESSION -- see the docstring
        f"tb1-BTCUSDT-{BAR_MS}-0-LL",  # our prefix, suffix outside the form
        f"tb1-BTC-USDT-{BAR_MS}-0-L",  # our prefix, hyphen inside the symbol
        f"tb1-BTCUSDT-{BAR_MS}-0",  # our prefix, suffix segment missing
    ],
    ids=["library_tag", "prefix_only", "bad_suffix", "hyphenated_symbol", "truncated"],
)
def test_a_list_id_that_is_not_ours_parses_to_none(value: str) -> None:
    """``None``, never a raise -- the enumeration returns every list on the
    account, so foreign IDs are the ordinary case.

    **``tb1-garbage`` is the one that earns this test.** A raw
    ``startswith("tb1-")`` accepts it, and Q-C records that admitting a human's
    order that merely starts the same way is the failure the parse-don't-prefix
    rule exists to prevent. A boot-time check keyed on a prefix would refuse a
    symbol on the strength of somebody else's string.
    """
    assert parse_list_client_order_id(value) is None


# --------------------------------------------------------------------------
# The CLOSE identity -- a standalone MARKET sell, not a leg of any list
# --------------------------------------------------------------------------
def test_the_close_id_is_deterministic_and_uses_the_same_seeds() -> None:
    """Same seeds, same shape, differing only in the code.

    MUTATION: build from a clock or a counter instead of the seeds.

    Called twice, because "deterministic" is the claim and one call cannot
    make it -- the property that lets a restarted process re-derive the ID it
    would have sent.
    """
    assert close_client_order_id("BTCUSDT", BAR) == f"tb1-BTCUSDT-{BAR_MS}-0-CL"
    assert close_client_order_id("BTCUSDT", BAR) == close_client_order_id("BTCUSDT", BAR)


def test_the_close_code_is_distinct_from_every_other_suffix() -> None:
    """Four identity families, no two sharing a code.

    MUTATION: set ``CLOSE = "TP"``, or ``CLOSE = "L"``.

    Asserted over the ENUM and the list suffix together, so a collision with
    either family fails here rather than at the venue -- where a colliding code
    would silently address somebody else's order.
    """
    codes = [m.value for m in OrderListLeg]

    assert len(codes) == len(set(codes))
    assert OrderListLeg.CLOSE.value not in {m.value for m in LIST_LEGS}
    assert OrderListLeg.CLOSE.value != LIST_SUFFIX


def test_the_close_id_round_trips() -> None:
    """Generate then parse returns exactly what went in.

    MUTATION: drop the ``leg`` field from ``parse_close_client_order_id``'s
    return, or have it read ``match["leg"]`` from a group that does not exist.

    The generation is non-zero deliberately: at 0 a parser that dropped the
    segment and defaulted would still pass.
    """
    generated = close_client_order_id("ETHUSDT", BAR, generation=7)

    assert parse_close_client_order_id(generated) == ClientOrderIdParts(
        symbol="ETHUSDT", entry_bar_time=BAR, generation=7, leg=OrderListLeg.CLOSE
    )


def test_a_close_id_does_not_parse_as_a_leg_and_a_leg_does_not_parse_as_a_close() -> None:
    """THE STRUCTURAL DISJOINTNESS, asserted in both directions.

    MUTATION: widen ``_ID_PATTERN`` to ``(?P<leg>W|SL|TP|CL)``.

    **This is the test that guards a silent double-booking.**
    ``parse_client_order_id`` has two production callers on the reconciliation
    hot path. If it recognised a close sell, ``_compare_set`` would hand it to
    ``classify_protection``, whose ``protective_legs`` is scoped as everything
    that is not ``WORKING`` -- so the sell would be read as PROTECTION, and a
    filled one would build an ``ExitFill`` that the reconciliation driver
    books. A realised loss booked twice, through a regex alternation.

    The ``L`` case failed loudly because ``OrderListLeg("L")`` has no member.
    This one would NOT: ``OrderListLeg("CL")`` is valid, so nothing raises and
    nothing reports it. That asymmetry is why this assertion exists.
    """
    close_id = close_client_order_id("BTCUSDT", BAR)
    leg_id = client_order_id("BTCUSDT", BAR, OrderListLeg.STOP_LOSS)
    list_id = list_client_order_id("BTCUSDT", BAR)

    assert parse_client_order_id(close_id) is None
    assert parse_list_client_order_id(close_id) is None
    assert parse_close_client_order_id(leg_id) is None
    assert parse_close_client_order_id(list_id) is None


def test_the_leg_builder_refuses_the_close_code() -> None:
    """``CLOSE`` is in the enum and is not a leg; the leg builder says so.

    MUTATION: delete the guard in ``client_order_id``.

    Without it the call SUCCEEDS and returns ``tb1-BTCUSDT-...-0-CL`` -- an ID
    whose own family's parser refuses it, discovered only when something tried
    to resolve it. Asserted on the surviving behaviour too: the close builder
    produces exactly the string the leg builder would have.
    """
    with pytest.raises(ValueError, match="not a leg"):
        client_order_id("BTCUSDT", BAR, OrderListLeg.CLOSE)

    assert close_client_order_id("BTCUSDT", BAR).endswith("-CL")


def test_the_close_segment_is_the_value_not_the_member() -> None:
    """`CLAUDE.md`'s ``str, Enum`` trap, on the one member the parametrized
    test above cannot cover.

    MUTATION: build the close ID from ``OrderListLeg.CLOSE`` rather than its
    ``.value``.

    That yields ``OrderListLeg.CLOSE``, which puts a ``.`` in the ID and blows
    both the length and the character class at once -- and the venue reports
    the length violation as a character one, which is the misdiagnosis
    ``_enforce_venue_rule`` exists to prevent.
    """
    generated = close_client_order_id("BTCUSDT", BAR)

    assert "OrderListLeg" not in generated
    assert generated.endswith(f"-{OrderListLeg.CLOSE.value}")


@pytest.mark.parametrize("symbol", ["BTCUSDT", "ETHUSDT"])
def test_the_close_id_fits_the_ceiling_on_the_shipped_symbols(symbol: str) -> None:
    """Headroom on what actually ships, asserted rather than reasoned.

    MUTATION: make ``CLOSE`` three characters, e.g. ``"CLS"``.

    31 characters at the maximum generation -- identical to the ``SL``/``TP``
    figure the leg test asserts, because the code is the same width.
    """
    generated = close_client_order_id(symbol, BAR, generation=MAX_GENERATION)

    assert len(generated) <= MAX_CLIENT_ORDER_ID_LENGTH
    assert len(generated) == 31


def test_the_close_id_fits_the_worst_case_the_ceiling_was_derived_from() -> None:
    """THE BINDING CASE, and the proof that ``CLOSE`` does not move it.

    MUTATION: make ``CLOSE`` three characters.

    ``MAX_GENERATION`` was DERIVED from ``20 + 12 + G + 2 <= 36`` -- a
    twelve-character symbol and a TWO-character leg code. ``CL`` is two
    characters, so it lands on exactly that bound and adds no new worst case.
    Asserted at 36, the measured limit, so a third character fails here rather
    than at the venue with a mislabelled error.

    A thirteen-character symbol still exceeds it and is still caught only by
    the output guard; that is unchanged and is asserted by the leg tests.
    """
    twelve = "ABCDEFGHIJKL"

    generated = close_client_order_id(twelve, BAR, generation=MAX_GENERATION)

    assert len(twelve) == 12
    assert len(generated) == MAX_CLIENT_ORDER_ID_LENGTH


def test_the_close_id_shares_the_generation_bound_and_the_naive_refusal() -> None:
    """One ``_assemble`` means one bound and one guard; this is what says so.

    MUTATION: give ``close_client_order_id`` its own arithmetic instead of
    calling ``_assemble``.

    A second copy would drift in exactly the three things the shared helper
    exists to hold together -- the bound, the epoch arithmetic and the guard.
    """
    with pytest.raises(ValueError, match="generation must be in"):
        close_client_order_id("BTCUSDT", BAR, generation=MAX_GENERATION + 1)

    with pytest.raises(ValueError, match="must be timezone-aware"):
        close_client_order_id("BTCUSDT", BAR.replace(tzinfo=None))


@pytest.mark.parametrize(
    "value",
    [
        "tb1-BTCUSDT-1786708800000-0-SL",
        "tb1-BTCUSDT-1786708800000-0-L",
        "tb1-garbage",
        "x-BTCUSDT-1786708800000-0-CL",
        "tb1-BTC-USDT-1786708800000-0-CL",
    ],
    ids=["a_leg", "a_list", "prefix_only", "foreign_prefix", "hyphenated_symbol"],
)
def test_a_close_id_that_is_not_ours_parses_to_none(value: str) -> None:
    """``None``, never a raise -- the same reason the other two parsers give.

    MUTATION: recognise by ``startswith("tb1-")`` instead of by parsing.

    ``tb1-garbage`` is the row that earns this: a prefix check accepts it, and
    Q-C records that admitting a human's order which merely starts the same way
    is the failure parse-don't-prefix exists to prevent.
    """
    assert parse_close_client_order_id(value) is None
