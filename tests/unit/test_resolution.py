"""Tests for the ambiguous-write resolver.

No network and no clock: the client is a stub that records what it was asked
and refuses to answer what it was not told.

**THE FIXTURES CARRY DUPLICATE ids ON PURPOSE, and a suite that did not could
not test this module at all.** The whole design constraint is that one
``listClientOrderId`` may map to several lists -- MEASURED on Testnet, where 14
lists carried 12 distinct ids and one id mapped to THREE. A fixture whose ids
are all unique cannot express the mutation that keys a mapping on that id, so
every multi-match case here builds the collision deliberately.

**In the several-with-one-live fixture the LIVE list is deliberately NOT LAST.**
A dict keyed on the id keeps the last writer, so a fixture with the live one
last would let that mutation survive by luck. The ordering is the test.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import pytest

from trading_bot.core.models import OrderList, OrderListEntry
from trading_bot.exchange.ids import list_client_order_id
from trading_bot.execution.resolution import (
    PlacementOutcome,
    PlacementVerdict,
    resolve_placement,
)

SYMBOL = "BTCUSDT"
BAR = datetime(2026, 8, 21, 12, 0, 0, tzinfo=timezone.utc)
GEN = 0
WANTED = list_client_order_id(SYMBOL, BAR, generation=GEN)
OTHER = list_client_order_id("ETHUSDT", BAR, generation=GEN)


def _list(
    order_list_id: str,
    *,
    lcid: str | None = WANTED,
    status: str = "ALL_DONE",
    legs: int = 3,
) -> OrderList:
    """One order list as `get_all_order_lists` reports it."""
    return OrderList(
        order_list_id=order_list_id,
        symbol=SYMBOL,
        list_client_order_id=lcid,
        list_status_type=status,
        list_order_status=status,
        orders=tuple(
            OrderListEntry(symbol=SYMBOL, order_id=f"{order_list_id}{i}", client_order_id=f"c{i}")
            for i in range(legs)
        ),
    )


class _StubClient:
    """Records what it was asked, and REFUSES to answer what it was not told.

    Mirrors ``test_reconciliation_pass``'s stub and for the same reason: an
    implicit empty enumeration is a real classification here -- ``NOT_PLACED``,
    with a real consequence -- so a test getting it by default would pass for a
    reason nobody chose. A listing must be configured, even when the intended
    listing is empty.

    ``timeout_s`` and ``attempts`` are NAMED rather than swallowed into
    ``**kwargs``: a fixture that accepts an argument and discards it cannot
    express a mutation that stops forwarding it.
    """

    def __init__(self, listing: list[OrderList] | Exception | None = None) -> None:
        self._listing = listing
        self.calls = 0
        self.bounds: list[tuple[float | None, int | None]] = []

    async def get_all_order_lists(
        self, *, timeout_s: float | None = None, attempts: int | None = None
    ) -> list[OrderList]:
        self.calls += 1
        self.bounds.append((timeout_s, attempts))
        if self._listing is None:
            raise AssertionError(
                "no listing configured. Configure one explicitly -- an implicit empty "
                "enumeration is a verdict (NOT_PLACED), not an absence of one."
            )
        if isinstance(self._listing, Exception):
            raise self._listing
        return self._listing


async def _resolve(client: Any, **kwargs: Any) -> PlacementVerdict:
    return await resolve_placement(
        client, symbol=SYMBOL, entry_bar_time=BAR, generation=GEN, **kwargs
    )


class TestTheUnambiguousRows:
    """One match, or none. These are the rows the set size does not complicate."""

    async def test_no_match_is_not_placed(self) -> None:
        """An empty enumeration and an enumeration full of other people's lists
        are the same answer: nothing of ours rests."""
        client = _StubClient([_list("999", lcid=OTHER), _list("998", lcid=None)])

        verdict = await _resolve(client)

        assert verdict.outcome is PlacementOutcome.NOT_PLACED
        assert verdict.matched == ()
        assert WANTED in verdict.reason

    async def test_one_live_match_is_placed_live(self) -> None:
        """Under the FOK inference a live list means the entry FILLED -- which is
        why C4 reads this to decide whether to construct a Position."""
        client = _StubClient([_list("100", status="EXECUTING")])

        verdict = await _resolve(client)

        assert verdict.outcome is PlacementOutcome.PLACED_LIVE
        assert [ol.order_list_id for ol in verdict.matched] == ["100"]

    async def test_one_terminal_match_is_placed_terminal(self) -> None:
        """MEASURED 2026-08-21: a FOK-expired list reads ALL_DONE/ALL_DONE and is
        findable by our derived id. Nothing rests and no position was opened."""
        client = _StubClient([_list("100", status="ALL_DONE")])

        verdict = await _resolve(client)

        assert verdict.outcome is PlacementOutcome.PLACED_TERMINAL
        assert [ol.order_list_id for ol in verdict.matched] == ["100"]


class TestMultiplicity:
    """The rows a dict keyed on the id would destroy. MEASURED: one id mapped to
    three lists on the probe account."""

    async def test_several_with_one_live_is_placed_live(self) -> None:
        """At most one live list may hold an id, so the live one is unambiguous
        however many terminals sit beside it.

        **The live list is FIRST, deliberately.** A dict keyed on the id keeps
        the LAST writer, so putting the live one last would let that mutation
        pass by luck rather than by correctness.
        """
        client = _StubClient(
            [
                _list("100", status="EXECUTING"),
                _list("101", status="ALL_DONE"),
                _list("102", status="ALL_DONE"),
            ]
        )

        verdict = await _resolve(client)

        assert verdict.outcome is PlacementOutcome.PLACED_LIVE
        assert [ol.order_list_id for ol in verdict.matched] == ["100", "101", "102"]

    async def test_several_all_terminal_is_unresolved(self) -> None:
        """The row that could have gone either way, and the reason it did not.

        A terminal id is released and reusable, so any of these may be this
        attempt's or an earlier one's, and the payload carries no timestamp to
        separate them. Reporting PLACED_TERMINAL would assert something not
        known. Under the fail-closed ruling both verdicts lead the caller to the
        same action, so honesty is free here -- and guessing is the one thing
        unavailable.
        """
        client = _StubClient(
            [_list("100"), _list("101"), _list("102")]  # the measured 3-way collision
        )

        verdict = await _resolve(client)

        assert verdict.outcome is PlacementOutcome.UNRESOLVED
        assert [ol.order_list_id for ol in verdict.matched] == ["100", "101", "102"]
        assert "released and reusable" in verdict.reason

    async def test_several_live_is_unresolved_because_the_premise_is_violated(self) -> None:
        """Two live lists on one id cannot happen under the measured uniqueness
        rule. If it does, every other rule here rests on a measurement that no
        longer holds -- so this refuses rather than picking one."""
        client = _StubClient([_list("100", status="EXECUTING"), _list("101", status="EXECUTING")])

        verdict = await _resolve(client)

        assert verdict.outcome is PlacementOutcome.UNRESOLVED
        assert "unique against live orders" in verdict.reason

    async def test_the_verdict_carries_every_match_not_just_one(self) -> None:
        """Multiplicity is the evidence for UNRESOLVED, so it is carried rather
        than reduced -- a caller that has to escalate needs to name what it saw."""
        client = _StubClient([_list("100"), _list("101"), _list("102"), _list("103")])

        verdict = await _resolve(client)

        assert len(verdict.matched) == 4
        assert [ol.order_list_id for ol in verdict.matched] == ["100", "101", "102", "103"]


class TestTheQueryItself:
    """What the resolver does with the call rather than with the answer."""

    async def test_a_failed_query_is_unresolved_and_says_so(self) -> None:
        """ "No list matched" and "the query did not answer" are different facts.
        The reconciler settled this shape: absence is not an answer."""
        client = _StubClient(RuntimeError("connection reset"))

        verdict = await _resolve(client)

        assert verdict.outcome is PlacementOutcome.UNRESOLVED
        assert verdict.matched == ()
        assert "RuntimeError" in verdict.reason
        assert "connection reset" in verdict.reason

    async def test_the_bounds_are_passed_through(self) -> None:
        """Funding is unruled, but the channel must exist -- a resolver that
        cannot be bounded is the one call in a dispatch sequence nothing bounds."""
        client = _StubClient([])

        await _resolve(client, timeout_s=2.5, attempts=1)

        assert client.bounds == [(2.5, 1)]

    async def test_the_query_is_made_exactly_once(self) -> None:
        """One enumeration answers the whole question; a second would cost a
        round trip in a sequence already under strain."""
        client = _StubClient([])

        await _resolve(client)

        assert client.calls == 1


class TestTheIdIsDerived:
    """The id is computed from the seeds, which is what lets this run after a
    timeout destroyed every local record of the attempt."""

    async def test_the_id_matched_is_the_derived_one(self) -> None:
        client = _StubClient([_list("100", lcid=WANTED)])

        verdict = await _resolve(client)

        assert verdict.outcome is PlacementOutcome.PLACED_TERMINAL
        assert WANTED in verdict.reason

    async def test_a_different_generation_derives_a_different_id_and_misses(self) -> None:
        """Generation is part of the seed. A list placed at generation 0 is not
        the list a generation-1 query is asking about."""
        client = _StubClient([_list("100", lcid=WANTED)])

        verdict = await resolve_placement(client, symbol=SYMBOL, entry_bar_time=BAR, generation=1)

        assert verdict.outcome is PlacementOutcome.NOT_PLACED

    async def test_a_naive_bar_time_raises_rather_than_returning_a_verdict(self) -> None:
        """A caller bug is not a venue answer. A verdict means the venue was
        asked; a naive seed means it never was, and converting that into
        UNRESOLVED would let a programming error read as venue ambiguity.
        """
        client = _StubClient([])

        with pytest.raises(ValueError, match="timezone-aware"):
            await resolve_placement(
                client,
                symbol=SYMBOL,
                entry_bar_time=datetime(2026, 8, 21, 12, 0, 0),
                generation=GEN,
            )

        assert client.calls == 0
