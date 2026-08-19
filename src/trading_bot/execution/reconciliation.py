"""Classify a position's protection from what rests at the venue, and record it.

**Two layers, and the split is deliberate.**
:func:`classify_protection` is PURE -- no I/O, no config, no clock, no
``Position``: it takes requested levels and a compare set and returns a frozen
verdict carrying its reason. :func:`reconcile_open_positions` is the pass
around it: it reads, classifies, and writes. Driving the pass from the candle
subscription, and performing the point queries a verdict asks for, belong to
whoever owns the reconciler and are not here.

The pure half is what makes the impure half testable without a venue, and
keeping the classification decidable from data alone is why it is worth the
extra function.

**Keyed off what was REQUESTED, never off what is absent.** Divergence is
"protection was requested and does not rest", not "no legs are resting" -- so a
position with nothing requested is not diverged, and a requested leg that has
vanished is not diverged either. It is *unresolved*, which is a different
answer and a weaker one.

**Why this module rather than ``core/``.** The compare set carries
:class:`~trading_bot.exchange.ids.ClientOrderIdParts`, and ``core/`` may not
import an outer layer. It is also not risk policy: nothing here decides what to
do about a verdict, only what the verdict is.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Literal, assert_never

from pydantic import BaseModel, ConfigDict

from trading_bot.core.enums import OrderStatus, ProtectionState
from trading_bot.core.exceptions import ContractViolationError, OrderNotFoundError
from trading_bot.core.interfaces import ExchangeClient
from trading_bot.core.models import Order, Position
from trading_bot.core.portfolio import Portfolio
from trading_bot.exchange.ids import (
    ClientOrderIdParts,
    OrderListLeg,
    client_order_id,
    parse_client_order_id,
)

__all__ = [
    "ProtectionAssessment",
    "UnresolvedLeg",
    "classify_protection",
    "reconcile_open_positions",
    "resolve_unresolved_legs",
]

#: The generation every position is reconciled at, because there is nowhere to
#: read one from: ``Position`` carries no generation field and nothing in
#: ``src/`` has ever produced a generation above zero.
#:
#: Named rather than inlined so the assumption is greppable. It is WRONG the
#: moment a re-placement happens -- section 7's "re-place once at the next
#: generation" -- and the consequence is recorded as ``M5e-031``: a leg resting
#: under an earlier generation is filtered out, reads as absent, and yields an
#: unresolved entry naming an identifier that was never sent. The first
#: re-placement arms it.
_NO_GENERATION_SOURCE = 0


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True)


class UnresolvedLeg(_Frozen):
    """A requested leg that is absent from the compare set, and how to resolve it.

    **Absence is not an answer.** A leg missing from ``get_open_orders`` may
    never have been placed, may have been cancelled, or may have filled, and
    MEASURED at M5e: after a cancel the enumeration returned ``[]`` while a
    point query by ``origClientOrderId`` still reported ``CANCELED``. The two
    endpoints are different instruments and only the second separates those
    cases.

    So this names the query rather than guessing its result. The identifier is
    derived by pure computation from the same seeds that generated it, which is
    what makes a classifier able to say "ask about *this*" without any I/O.
    """

    leg: OrderListLeg
    client_order_id: str


class ProtectionAssessment(_Frozen):
    """What is known about one position's protection, and why.

    A verdict is a **value carrying its reason**, never an exception and never a
    bare enum: "the stop rests one tick low" and "the stop is not there at all"
    are different facts that would otherwise arrive as the same word.

    ``unresolved`` is non-empty only for :attr:`ProtectionState.UNKNOWN` reached
    through absence, and it is the caller's work list.
    """

    state: ProtectionState
    reason: str
    unresolved: tuple[UnresolvedLeg, ...] = ()


def _requested(
    stop_loss: Decimal | None, take_profit: Decimal | None
) -> dict[OrderListLeg, Decimal]:
    """The protective legs that were asked for, by leg code.

    The working leg is deliberately absent: it is the entry, not protection, and
    it is *expected* to leave the book when it fills.
    """
    asked: dict[OrderListLeg, Decimal] = {}
    if stop_loss is not None:
        asked[OrderListLeg.STOP_LOSS] = stop_loss
    if take_profit is not None:
        asked[OrderListLeg.TAKE_PROFIT] = take_profit
    return asked


def classify_protection(
    *,
    symbol: str,
    entry_bar_time: datetime,
    generation: int,
    quantity: Decimal,
    order_list_id: str | None,
    stop_loss: Decimal | None,
    take_profit: Decimal | None,
    resting: Sequence[tuple[ClientOrderIdParts, Order]],
) -> ProtectionAssessment:
    """Compare requested protection against what rests, and say what is known.

    ``resting`` is the symbol's own ``tb1-`` compare set. Legs belonging to
    another bar or another generation are ignored here rather than filtered by
    the caller, so a caller reading one symbol cannot accidentally attribute a
    neighbouring position's legs to this one.

    **The compared set, and its two deliberate exclusions.** Existence, status,
    ``executedQty``, ``origQty``, ``orderListId`` and the trigger price are
    compared; the client order id is compared implicitly, since it is what
    selects a leg at all. ``price`` and ``timeInForce`` on a stop-market leg are
    **server defaults and are excluded entirely** -- comparing them manufactures
    divergence on every pass.

    **The trigger is compared NUMERICALLY.** The venue pads what it returns --
    ``"40917.83"`` comes back ``"40917.83000000"`` -- so a string comparison
    would report divergence every cycle on protection that is perfectly correct.
    ``Order.stop_price`` is already ``Decimal`` and ``Decimal`` equality is
    numeric, which is the whole mechanism; it is stated because it is invisible.

    :returns: a frozen verdict. Never raises for an ordinary venue state -- an
        unreadable one is a value, because a reconciler that raised on a state
        it did not expect would take the pass down with it.
    """
    asked = _requested(stop_loss, take_profit)
    mine = {
        parts.leg: order
        for parts, order in resting
        if parts.symbol == symbol
        and parts.entry_bar_time == entry_bar_time
        and parts.generation == generation
    }

    if not asked:
        # `ABSENT_BY_DESIGN` asserts that no protection is EXPECTED, which is
        # the off-switch for the divergence detector on this position. Assert it
        # only when nothing of ours rests either; legs resting under a position
        # that asked for none is a story nobody has established, and switching
        # the detector off over it is exactly the silent wrong value.
        protective = {leg: order for leg, order in mine.items() if leg is not OrderListLeg.WORKING}
        if protective:
            return ProtectionAssessment(
                state=ProtectionState.UNKNOWN,
                reason=(
                    f"no protection was requested for {symbol}, yet "
                    f"{len(protective)} protective leg(s) rest under our own ids"
                ),
            )
        return ProtectionAssessment(
            state=ProtectionState.ABSENT_BY_DESIGN,
            reason=f"no protective levels were requested for {symbol}",
        )

    # A fill is refused rather than interpreted, and BEFORE any price
    # comparison, so a filled leg carrying a stale trigger is not mislabelled a
    # price divergence. Nothing in this tree has ever observed a filled
    # protective leg -- the fill path is UNMEASURED -- so the honest answer is
    # that the story is not established. `UNKNOWN` is untrusted, which refuses
    # entries: reversible, and it makes the missing measurement visible in
    # behaviour instead of hiding it inside an assumption.
    #
    # SCOPED TO PROTECTIVE LEGS, AND THE WORKING LEG IS THE REASON. `-W` is the
    # entry: by the time a `Position` exists it has filled BY DEFINITION. Judged
    # by the rule above it would make every correctly protected position read
    # `UNKNOWN`, which is untrusted, which counts uncomputable, which refuses
    # every entry portfolio-wide -- the interlock firing on the healthy path.
    #
    # The scoping is correct under BOTH answers to the open question of whether
    # a filled leg stays visible to `get_open_orders`, which is why it needs no
    # measurement: if filled legs remain visible it prevents that refusal, and
    # if they vanish the working leg is never in the compare set and the skip is
    # inert. It changes behaviour only in the case that would be broken.
    #
    # Scoped by LEG rather than by what was asked for, so an unrequested `-SL`
    # or `-TP` reporting a fill still refuses. That is the conservative side.
    # Annotated rather than inferred: without it the `is not WORKING` test
    # narrows the key type to the two remaining members, and a `for` target is
    # FUNCTION-scoped, so the narrowed binding collides with the plain
    # `OrderListLeg` the later loops assign to the same name.
    protective_legs: dict[OrderListLeg, Order] = {
        leg: order for leg, order in mine.items() if leg is not OrderListLeg.WORKING
    }
    for leg, order in sorted(protective_legs.items(), key=lambda item: item[0].value):
        if order.status is OrderStatus.FILLED or order.filled_quantity > 0:
            return ProtectionAssessment(
                state=ProtectionState.UNKNOWN,
                reason=(
                    f"{symbol} leg {leg.value} reports status {order.status.value} with "
                    f"{order.filled_quantity} executed; the fill path is unmeasured, so this "
                    "state is refused rather than interpreted"
                ),
            )

    missing = tuple(
        UnresolvedLeg(
            leg=leg,
            client_order_id=client_order_id(symbol, entry_bar_time, leg, generation=generation),
        )
        for leg in sorted(asked, key=lambda leg: leg.value)
        if leg not in mine
    )
    if missing:
        return ProtectionAssessment(
            state=ProtectionState.UNKNOWN,
            reason=(
                f"{symbol} requested leg(s) "
                f"{', '.join(item.leg.value for item in missing)} are absent from what rests; "
                "absence is never-placed, cancelled or filled and only a point query separates "
                "them"
            ),
            unresolved=missing,
        )

    for leg in sorted(asked, key=lambda leg: leg.value):
        order = mine[leg]
        wanted = asked[leg]
        if order.stop_price != wanted:
            return ProtectionAssessment(
                state=ProtectionState.DIVERGED,
                reason=(
                    f"{symbol} leg {leg.value} rests at trigger {order.stop_price} where "
                    f"{wanted} was requested"
                ),
            )
        if order.quantity != quantity:
            return ProtectionAssessment(
                state=ProtectionState.DIVERGED,
                reason=(
                    f"{symbol} leg {leg.value} rests for {order.quantity} where {quantity} "
                    "was requested"
                ),
            )
        if order_list_id is not None and order.order_list_id != order_list_id:
            return ProtectionAssessment(
                state=ProtectionState.DIVERGED,
                reason=(
                    f"{symbol} leg {leg.value} belongs to list {order.order_list_id} where "
                    f"{order_list_id} was requested"
                ),
            )

    pending = tuple(
        leg.value
        for leg in sorted(asked, key=lambda leg: leg.value)
        if mine[leg].status is OrderStatus.PENDING_NEW
    )
    if pending:
        return ProtectionAssessment(
            state=ProtectionState.PENDING,
            reason=(
                f"{symbol} leg(s) {', '.join(pending)} are accepted and not yet activated; "
                "a pending leg becomes live only when the working order fills"
            ),
        )

    return ProtectionAssessment(
        state=ProtectionState.ACTIVE,
        reason=f"{symbol}: every requested protective leg rests at its requested trigger",
    )


def _is_due(position: Position, *, now: datetime, dedup_interval: timedelta) -> bool:
    """Whether this position's stamp is old enough to re-read.

    **Passes are deduplicated by ``last_reconciled_at``**: a position is
    re-read only once its stamp is older than the interval the driver supplies,
    so two pairs whose bars close on the same minute pay for one pass and not
    two.

    **``None`` re-reads, and that is a DEDUP decision only.** An unstamped
    position has never been read; re-reading it costs one call and cannot be
    wrong. What ``None`` should mean for the STALENESS REFUSAL -- maximally
    stale, exempt until first stamped, or stamped at construction -- is a
    separate ruling, reserved, and untouched here. Nothing in this function is
    precedent for it.

    The interval is a parameter rather than a constant because it derives from
    the shortest enabled timeframe, which is config the driver holds.
    """
    if position.last_reconciled_at is None:
        return True
    return now - position.last_reconciled_at > dedup_interval


def _compare_set(orders: Sequence[Order], *, symbol: str) -> list[tuple[ClientOrderIdParts, Order]]:
    """Re-parse each order's identifier and pair it back up.

    The port returns orders alone, because the parsed form lives in a module
    ``core`` may not import. Parsing here is the cost of that, and it is pure
    string work over a list already bounded by the venue's open-order count.

    **An unparseable identifier is a CONTRACT VIOLATION, not a market state.**
    The implementation filters by parsing, so every order reaching here parses
    by construction; one that does not means our adapter is broken or an
    implementation does not honour the port. That is our bug, and this project
    keeps our bugs in a family a caller can catch as a class rather than
    disguising them as refusals.

    **Raising mid-pass is survivable, which is what makes it the right answer
    rather than merely the correctly classified one.** An abort leaves the
    positions already visited written and the rest untouched, so those keep old
    stamps, go stale, and refuse entries -- which is IDENTICAL to a pass cut
    short by its budget, a designed normal state rather than a novel one. And
    because positions are visited oldest stamp first, the loss falls on the
    FRESHEST, which is the one that could best afford to wait.
    """
    found: list[tuple[ClientOrderIdParts, Order]] = []
    for order in orders:
        parts = parse_client_order_id(order.client_order_id or "")
        if parts is None:
            raise ContractViolationError(
                f"{symbol}: get_own_open_orders returned an order whose client order id "
                f"does not parse: {order.client_order_id!r}. The implementation filters by "
                "parsing, so this is our bug rather than a venue state."
            )
        found.append((parts, order))
    return found


async def reconcile_open_positions(
    *,
    portfolio: Portfolio,
    client: ExchangeClient,
    now: datetime,
    dedup_interval: timedelta,
    max_calls: int,
    timeout_s: float | None,
    attempts: int | None,
) -> tuple[tuple[Position, ProtectionAssessment], ...]:
    """Read what rests, classify every due position, and record the verdict.

    **One call per symbol.** Section 7 prices the compare set at "one call per
    symbol, amortised across every position on that symbol", and this pass is
    literally that -- the point query that resolves an absent leg is a separate,
    visible budget line rather than a phase hidden inside this one.

    **Positions are visited OLDEST STAMP FIRST**, so a pass cut short by the
    budget always advances the stalest one instead of starving a fixed tail.
    Unstamped positions sort first, having waited longest by definition.

    **Returns the assessments, not just the states.** The reason and the
    unresolved legs cannot be recovered from a written ``Position``: resolving
    an absent leg would have to re-derive the whole classification, escalation
    needs a cause for its detail, and an operator facing a portfolio-wide
    refusal is owed one. Nothing is logged here -- the driver decides what is
    worth saying.

    ``now`` is WALL CLOCK. Candle time cannot be used: staleness must count
    every bar that never arrived because the feed dropped, and a bar that never
    arrived contributes no timestamp, so a candle clock freezes exactly during
    the outage that makes the ledger least trustworthy.

    **``max_calls`` bounds the WHOLE reconciliation phase, not this pass.**
    The coherence validator reserves ``max_open_positions x
    reconcile_deadline_s`` for reconciliation, and every call is bounded by
    ``reconcile_deadline_s``, so the reservation admits exactly
    ``max_open_positions`` calls. That reservation is met with equality and
    never exceeded: what this pass does not spend is what
    :func:`resolve_unresolved_legs` may.

    **The pass makes EXACTLY ONE call per returned assessment**, which is why
    the caller can derive the remainder as ``max_calls - len(results)`` with no
    counter to keep in step. The loop is written against ``len(results)``
    rather than a parallel tally so the invariant is structural rather than
    remembered.

    **``timeout_s`` and ``attempts`` are REQUIRED and nullable**, not defaulted.
    ``None`` means the implementation's own policy and is a legitimate answer;
    what is not legitimate is a caller that never considered the question,
    because omitting them silently inherits the client-wide policy -- four
    attempts at ``exchange.requests_timeout_s``, tens of seconds -- inside a
    slot reserved at ``reconcile_deadline_s``. That failure is silent and
    blows the only guarantee the coherence validator computes, so every call
    site says something, as ``RiskAssessment.stage`` does. No number is chosen
    here; budgets are the driver's.

    **It reserves what the FIRST unresolved position NEEDS -- its ``L``
    outstanding legs -- once a leg has been seen unresolved.** Positions are
    keyed by symbol on ``Portfolio``, so at the position limit the pass would
    otherwise consume the entire budget and leave the resolver zero -- every
    cycle, and precisely when there is most protection to verify. Dedup does
    not help: a deduped position produces no assessment, so the call it frees
    and the resolution that call would fund never coexist.

    The reservation is CONDITIONAL, and that is what makes it free. At steady
    state nothing is unresolved, so the pass spends every call; holding calls
    back unconditionally would tax reconciliation permanently for a resolver
    with no work to do. It also cannot starve the pass to nothing: ``reserved``
    is assigned only *after* a call returns, so before the first call it is
    zero and ``0 + 0 >= max_calls`` is false for any positive budget.

    **Reserving exactly ONE call was this rule's first form, and it left a
    LIVELOCK.** Recorded rather than replaced silently, because the earlier
    reasoning was sound and only its quantity was wrong. Resolution is
    all-or-nothing -- the ``missing`` tuple is re-derived in fixed leg order
    every cycle and the budget is spent from the front, so one reserved call
    re-queries the same first leg forever and a two-leg position never
    completes. Never completing means never stamped, means sorting first
    forever, means the healthy positions behind it are never read at all.

    **Completing an ``L``-leg position costs ``1 + L`` calls**: one enumeration
    to discover it, ``L`` point queries to resolve it. So this rule closes the
    livelock exactly when ``max_calls >= L + 1``, and below that no scheme
    respecting ``total <= max_calls`` can -- that is arithmetic rather than a
    weakness in the rule. See ``docs/NEXT_MILESTONE.md`` item 13 for the config
    relation this implies, which nothing validates.

    **``L`` is DISCOVERED BY VISITING, not predicted**, and the reservation
    takes effect from the next iteration. It protects work already identified
    rather than work forecast, which is what lets it exist without lookahead.
    One asymmetric case follows and self-corrects: a first unresolved position
    discovered *last* sets ``reserved`` after every call is spent, so the
    resolver may get nothing that cycle -- but that position is left unstamped,
    sorts first next cycle, and is then discovered on call one.

    **A position whose assessment carries unresolved legs is NOT stamped.** It
    keeps ``protection`` -- the verdict is real and untrusted either way -- and
    is left maximally stale, so it sorts first next cycle and the reservation
    fires early enough to fund it. The stamp is the state; nothing here
    remembers anything between passes. See
    :meth:`~trading_bot.core.models.Position.record_partial_reconciliation`.

    :raises ContractViolationError: an order came back with an identifier that
        does not parse. See :func:`_compare_set` for why aborting is safe.
    """
    due = sorted(
        (
            position
            for position in portfolio.open_positions
            if _is_due(position, now=now, dedup_interval=dedup_interval)
        ),
        key=lambda position: (
            position.last_reconciled_at is not None,
            position.last_reconciled_at or now,
        ),
    )

    results: list[tuple[Position, ProtectionAssessment]] = []
    reserved = 0
    for position in due:
        # ONE condition, not two branches. With `reserved` at zero this IS the
        # plain cap; with `reserved` at L it IS the reservation. The earlier
        # form was a disjunction because the reserved quantity was fixed at
        # one; making it a quantity collapses both halves into the same
        # arithmetic -- how many calls this pass may still spend.
        #
        # The guarantee falls out of it: the loop continues only while
        # `len(results) + reserved < max_calls`, so it ends with
        # `len(results) <= max_calls - reserved`, so the remainder the caller
        # derives is at least `reserved`. Total stays at or under `max_calls`.
        if len(results) + reserved >= max_calls:
            break
        orders = await client.get_own_open_orders(
            position.symbol, timeout_s=timeout_s, attempts=attempts
        )
        assessment = classify_protection(
            symbol=position.symbol,
            entry_bar_time=position.entry_bar_time,
            generation=_NO_GENERATION_SOURCE,
            quantity=position.quantity,
            order_list_id=position.order_list_id,
            stop_loss=position.stop_loss,
            take_profit=position.take_profit,
            resting=_compare_set(orders, symbol=position.symbol),
        )
        if assessment.unresolved:
            position.record_partial_reconciliation(protection=assessment.state)
            # FIRST-WINS, not accumulate and not last-wins. Reserving for every
            # unresolved position would shrink the pass until it read almost
            # nothing, and completing them one at a time is what makes progress
            # monotone: each cycle finishes one position, stamps it, and frees
            # its share for the next.
            if reserved == 0:
                reserved = len(assessment.unresolved)
        else:
            position.record_reconciliation(protection=assessment.state, at=now)
        results.append((position, assessment))
    return tuple(results)


#: The states a point-query answer can produce -- NARROWER than
#: :class:`ProtectionState` on purpose.
#:
#: The narrowing is what makes the exhaustiveness guard in the precedence walk
#: possible at all: over the full enum mypy can prove nothing about which
#: members a fold must handle. Adding a member here without extending that walk
#: fails the type check, which is the whole point.
_ResolvedState = Literal[ProtectionState.UNKNOWN, ProtectionState.DIVERGED]


def _refine(leg: OrderListLeg, order: Order, *, symbol: str) -> tuple[_ResolvedState, str]:
    """What one point-query answer means for the leg it was asked about.

    **One discriminator rather than a list of statuses**, so a status nobody has
    classified still lands somewhere defensible: ``OrderStatus.is_open`` is a
    blacklist of terminal states, and its unclassified members default to OPEN
    -- which here means UNKNOWN, which refuses. The reversible direction.
    """
    if order.status is OrderStatus.FILLED or order.filled_quantity > 0:
        return (
            ProtectionState.UNKNOWN,
            f"{symbol} leg {leg.value} reports {order.status.value} with "
            f"{order.filled_quantity} executed; the fill path is unmeasured, so this state is "
            "refused rather than interpreted",
        )
    if order.status.is_open:
        return (
            ProtectionState.UNKNOWN,
            f"{symbol} leg {leg.value} is INSTRUMENT DISAGREEMENT: absent from the enumeration "
            f"and {order.status.value} on a point query. Two views of one leg disagree, and "
            "nothing measured says which to believe, so neither is acted on",
        )
    return (
        ProtectionState.DIVERGED,
        f"{symbol} leg {leg.value} was requested and does not rest: the point query reports "
        f"{order.status.value}",
    )


async def resolve_unresolved_legs(
    *,
    assessments: Sequence[tuple[Position, ProtectionAssessment]],
    client: ExchangeClient,
    max_queries: int,
    now: datetime,
    timeout_s: float | None,
    attempts: int | None,
) -> tuple[tuple[Position, ProtectionAssessment], ...]:
    """Resolve absent legs by point query, within a cap.

    **Beside the pass, not inside it.** Section 7 budgets the compare set at one
    call per symbol and the pass stays literally that; these queries are a
    separate, visible budget line the driver decides to spend. Folding them in
    would make one call per symbol quietly mean one plus however many legs
    happened to be missing.

    **``max_queries`` is a parameter and no number is chosen here.** It is a
    budget, and budgets in this project are the driver's to set. The same is
    true of ``timeout_s`` and ``attempts``, which are required and nullable for
    the reason given on :func:`reconcile_open_positions`. ``now`` is the same
    instant the pass used: one clock reading per cycle, so a two-phase
    reconciliation records the cycle it belongs to rather than the moment its
    second half happened to finish.

    **This function does NOT write to the positions**, deliberately. Every state
    it can return is untrusted exactly as the ``UNKNOWN`` the pass already wrote
    is untrusted, so the ledger's answer to "may this stop be priced" does not
    change -- only the REPORT sharpens. Writing would also re-stamp
    ``last_reconciled_at`` and reset a dedup clock the pass has just set.

    .. note::

       **SUPERSEDED in its second half, and annotated rather than rewritten,
       because its first half is still the reason this is safe.**

       What SURVIVES: every state returned here is untrusted, so writing one
       changes no risk answer. That is what makes the write below harmless
       rather than merely convenient.

       What FAILED: *"would also re-stamp ``last_reconciled_at`` and reset a
       dedup clock the pass has just set"*. The pass no longer sets a stamp on
       a position carrying unresolved legs -- it writes protection alone -- so
       for exactly the positions reaching the write below there is no clock to
       reset. **This is a justification that went stale when a fact
       established elsewhere moved**, which is why it is annotated at its own
       site instead of being quietly deleted.

       **So this function writes in ONE case: a position whose every
       outstanding leg it actually queried.** That is the second half of a
       two-phase reconciliation, and the stamp records the phase that
       completed it. A position with legs left over is still not stamped, and
       the legs are carried back in ``unresolved`` so the caller can tell "all
       queried" from "the budget ran out" -- a distinction that previously
       existed only in the reason prose, where nothing could act on it.

    **Only ``OrderNotFoundError`` is caught, and the principle generalises past
    this function.** It is an ANSWER: the venue saying the order does not exist.
    Everything else -- a transport failure, a rate limit, a contract violation --
    is a FAILURE TO GET AN ANSWER, and turning one of those into a verdict would
    be exactly what the classifier already refuses to do with absence. A verdict
    must rest on something the venue said. This is the precedent the executor's
    recovery behaviours inherit: catch answers, propagate failures.

    Per leg, so one leg's outcome cannot discard another's. The function may
    raise; the driver above it is what must not.

    **Where legs disagree, the WEAKER answer wins.** A position with one leg
    provably gone and another unresolved is not a position we understand, so it
    reports ``UNKNOWN`` rather than ``DIVERGED`` -- and ``DIVERGED`` is what
    section 7 answers with re-placement, which should not run on partial
    knowledge.
    """
    budget = max_queries
    refined: list[tuple[Position, ProtectionAssessment]] = []

    for position, assessment in assessments:
        if not assessment.unresolved:
            refined.append((position, assessment))
            continue

        states: list[_ResolvedState] = []
        reasons: list[str] = []
        carried: list[UnresolvedLeg] = []
        for item in assessment.unresolved:
            if budget <= 0:
                states.append(ProtectionState.UNKNOWN)
                reasons.append(
                    f"{position.symbol} leg {item.leg.value} was NOT YET QUERIED -- the point-query "
                    "budget was exhausted before reaching it, so nothing is known about it beyond "
                    "its absence from the enumeration"
                )
                # Carried back rather than left to the prose. "Every leg was
                # queried" and "the budget ran out" are different facts with
                # different consequences -- only the first may stamp -- and a
                # caller cannot act on a distinction that exists only in a
                # sentence.
                carried.append(item)
                continue
            budget -= 1
            try:
                order = await client.get_order(
                    position.symbol,
                    client_order_id=item.client_order_id,
                    timeout_s=timeout_s,
                    attempts=attempts,
                )
            except OrderNotFoundError as exc:
                states.append(ProtectionState.DIVERGED)
                reasons.append(
                    f"{position.symbol} leg {item.leg.value} was requested and the venue has no "
                    f"such order ({exc}). Note this cannot distinguish never-placed from "
                    "placed-and-since-purged; order retention is unmeasured"
                )
                continue
            state, reason = _refine(item.leg, order, symbol=position.symbol)
            states.append(state)
            reasons.append(reason)

        # THE WEAKER ANSWER WINS, and the walk is explicit so a third state
        # cannot slip through it. The previous form -- UNKNOWN if UNKNOWN is
        # present else DIVERGED -- hardcoded the two states `_refine` produces
        # and would have silently converted any third to DIVERGED. Safe in
        # direction, since DIVERGED is untrusted, and silent, which is the part
        # that matters: nothing would have reported the collapse.
        #
        # `assert_never` is a TYPE assertion, not defensive branching. Its
        # branch is provably unreachable under mypy, so widening
        # `_ResolvedState` fails the GATE rather than producing a wrong verdict
        # at runtime. That is the opposite of the harm the no-`UNCLASSIFIED`
        # rule names -- it forbids an unreachable enum member because one
        # "would invite defensive branching on a state the domain forbids", and
        # this makes such branching impossible to add without mypy objecting.
        verdict: _ResolvedState = ProtectionState.DIVERGED
        for candidate in states:
            if candidate is ProtectionState.UNKNOWN:
                verdict = ProtectionState.UNKNOWN
            elif candidate is ProtectionState.DIVERGED:
                continue
            else:
                assert_never(candidate)
        outcome = ProtectionAssessment(
            state=verdict, reason="; ".join(reasons), unresolved=tuple(carried)
        )
        # The completing half of a two-phase reconciliation, and it stamps
        # only when there is nothing left outstanding. A position with legs
        # carried forward stays unstamped, stays maximally stale, and is
        # visited first next cycle -- which is what funds the query it did not
        # get this time.
        if not carried:
            position.record_reconciliation(protection=verdict, at=now)
        refined.append((position, outcome))

    return tuple(refined)
