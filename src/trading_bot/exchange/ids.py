"""Deterministic client order IDs for the Q-C order-list scheme.

``docs/QC_PROTECTIVE_ORDERS.md`` section 6 fixes the form::

    tb1-{symbol}-{entry_bar_time_ms}-{gen}-{leg}

**Why this lives in ``exchange/`` rather than ``core/``.** Its constraints are
measured *venue* behaviour -- a 36-character ceiling and a character class -- and
``core/`` must not know Binance's ID rules any more than it knows ``-1013``. Its
first consumer is the order-list request mapper in this package, and
``execution/`` may import ``exchange/`` while the reverse must not, so placing it
here keeps the dependency direction intact. It is not in ``utils/helpers.py``
either: that module is deliberately venue-agnostic, and a Binance regex would be
the first venue contract in it.

**Scope: generation 0 only.** Section 6 guarantees that generation 0 is
DERIVABLE from ``(symbol, entry_bar_time)`` alone -- pure computation, no
persistence, no I/O -- while any generation above 0 is *recoverable* rather than
derivable: it requires querying prefix-matching orders and taking the highest
seen, so it needs a successful round trip and fails if the venue has aged those
orders out of its query window. :func:`client_order_id` therefore **accepts** a
generation, but **nothing in this module computes a non-zero one**. That arrives
with the client method that can perform the query.

**The prefix is load-bearing and its reason is not the obvious one.** ``tb1-``
exists because ``get_open_orders`` returns *every* order on the symbol, ours and
otherwise, and only a prefix distinguishes them. It is *not* a library tag: the
order-list endpoints are raw passthrough and inject nothing (MEASURED), so
nothing else marks our legs.
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Final, NamedTuple

from trading_bot.core.exceptions import ClientContractViolationError

__all__ = [
    "ID_PREFIX",
    "LIST_SUFFIX",
    "MAX_CLIENT_ORDER_ID_LENGTH",
    "MAX_GENERATION",
    "ClientOrderIdParts",
    "ListClientOrderIdParts",
    "OrderListLeg",
    "client_order_id",
    "close_client_order_id",
    "list_client_order_id",
    "parse_client_order_id",
    "parse_close_client_order_id",
    "parse_list_client_order_id",
]

#: Section 6's prefix. See the module docstring for why it is required.
ID_PREFIX: Final = "tb1-"

#: The suffix for the LIST-level identity, and **deliberately not a member of
#: :class:`OrderListLeg`** -- a list is not a leg. Admitting it to the enum
#: would let it be passed to :func:`client_order_id` and to the leg parser,
#: both of which are about orders; the type would stop meaning "which leg".
#:
#: **This EXTENDS Q-C section 6, which defines leg IDs only.** Section 3
#: requires ``listClientOrderId`` on both shapes and section 6 gives it no form,
#: so a form is chosen here: the same seeds, the same guard and the same
#: generation bound, differing only in this suffix. The section 6 amendment
#: recording it is due at rotation, with M5d-026's.
LIST_SUFFIX: Final = "L"

#: MEASURED at M5c: 36 accepted, 37 rejected with ``-1100``, HTTP 400.
#: ``docs/QC_PROTECTIVE_ORDERS.md`` section 10.
MAX_CLIENT_ORDER_ID_LENGTH: Final = 36

#: The largest generation this scheme can represent, DERIVED rather than chosen.
#:
#: An ID is ``20 + len(symbol) + digits(generation) + len(leg)`` characters --
#: four for ``tb1-``, three separators, thirteen for the millisecond epoch. The
#: worst measured leg code is two characters (``SL``/``TP``) and the longest
#: symbol section 10 contemplates is twelve, so ``20 + 12 + G + 2 <= 36`` gives
#: ``G <= 2`` digits.
#:
#: **The margin is two orders of magnitude and that is deliberate.** Section 7
#: increments the generation once per *detected divergence* and escalates to
#: ``CRITICAL`` with entries halted when a re-place fails, so protocol behaviour
#: is single-digit. This is a REPRESENTABILITY ceiling, not a throughput one.
#:
#: **It does not make the output guard redundant**, because symbol length is an
#: input this bound cannot constrain: a thirteen-character symbol at generation
#: 99 with an ``SL`` leg is 37 characters, and only the guard catches it.
MAX_GENERATION: Final = 99

_EPOCH: Final = datetime(1970, 1, 1, tzinfo=timezone.utc)

#: The venue publishes ``^[a-zA-Z0-9-_]{1,36}$``. That form is **ambiguous**:
#: between ``9`` and ``_`` a bare ``-`` reads as a range in most regex dialects,
#: which would silently admit ``:;<=>?@`` and the upper-case block. We take the
#: conservative literal-hyphen reading, so this class is a SUBSET of whatever
#: the venue meant either way -- an ID we accept is one it accepts.
#:
#: Length is checked separately and FIRST, which is the whole point of this
#: module: the venue reports a *length* violation as "Illegal characters found"
#: (M5c-C), so a single combined pattern would reproduce the misdiagnosis this
#: guard exists to prevent.
_LEGAL_CHARS: Final = re.compile(r"^[A-Za-z0-9_-]+$")

#: The seed segments both IDs share. Symbols carry no ``-``, and both numeric
#: segments are digits, so the split is unambiguous and neither parser needs
#: backtracking heuristics.
#:
#: Factored out so the seeds have ONE definition while the suffixes stay in TWO
#: patterns. That split is deliberate -- see :data:`_LIST_ID_PATTERN`.
_ID_BODY: Final = r"^tb1-(?P<symbol>[A-Za-z0-9]+)-(?P<ms>\d+)-(?P<generation>\d+)-"

_ID_PATTERN: Final = re.compile(_ID_BODY + r"(?P<leg>W|SL|TP)$")

#: **A SECOND PATTERN RATHER THAN ONE ALTERNATION, and the reason is a raise on
#: the reconciliation hot path.** Admitting ``L`` to :data:`_ID_PATTERN`'s group
#: would make :func:`parse_client_order_id` accept a list ID, and its two
#: production callers cannot survive that: ``get_own_open_orders`` would count
#: one as ours, and ``_compare_set`` would reach ``OrderListLeg("L")`` -- which
#: has no such member -- raising ``ValueError`` where it promises
#: ``ContractViolationError``.
#:
#: With two patterns the disjointness is STRUCTURAL: neither can match the
#: other's suffix, and there is no shared alternation for a later hand to widen.
_LIST_ID_PATTERN: Final = re.compile(_ID_BODY + re.escape(LIST_SUFFIX) + r"$")

# A THIRD PATTERN, for the same structural reason the second one exists -- and
# the consequence of widening is WORSE here than it was for `L`. The pattern
# itself is defined BELOW `OrderListLeg`, because it reads that enum's `.value`
# and a module body executes top to bottom; the reasoning lives here, beside
# the two patterns it is about.
#
# Written above the class first, and caught by IMPORTING the module -- mypy
# reported success on the broken form, which is exactly the blind spot
# `CLAUDE.md` records for `core/exceptions.py`.
#
# Admitting `CL` to `_ID_PATTERN`'s alternation would make
# `parse_client_order_id` recognise a close sell as a leg. That parser has two
# production callers on the reconciliation hot path, and both would act on it:
# `get_own_open_orders` would count the sell as ours, and `_compare_set` would
# hand it to `classify_protection`, whose `protective_legs` is scoped as
# *everything that is not* `WORKING`. A close sell would be read as PROTECTION.
#
# The `L` case failed loudly -- `OrderListLeg("L")` has no member, so it
# raised. THIS ONE WOULD NOT FAIL AT ALL. `OrderListLeg("CL")` is a valid
# member now, so the sell would flow through silently; and if it reported
# FILLED, `classify_protection` would build an `ExitFill` and the
# reconciliation driver would BOOK IT -- a second, undesigned booking path
# racing the one Q-C section 4b assigns to the close itself. Silent
# double-booking of a realised loss, arriving through a regex alternation.
#
# Disjointness is STRUCTURAL across all three patterns: `CL` is not `W`, `SL`
# or `TP`, and `-0-CL` does not match `-0-L$` under a fullmatch. There is no
# shared alternation for a later hand to widen.


class OrderListLeg(str, Enum):
    """Which leg of a Q-C order list an ID belongs to.

    ``str, Enum`` rather than ``StrEnum``, per the project-wide ``UP042``
    suppression -- so ``str(member)`` stays ``"OrderListLeg.WORKING"``. **That is
    exactly the trap this module has to avoid**: interpolating a member instead
    of its ``.value`` yields a qualified name containing a ``.``, producing an ID
    that is both over-length and outside the character class, which the venue
    then reports as an illegal *character* while the length is also wrong.
    :func:`client_order_id` builds from ``.value`` only, and the output guard
    catches any future edit that stops doing so.

    The first three codes are section 3's leg set and are what the M5c probe
    sent, so they match the only IDs the venue has been measured to honour
    byte-for-byte.

    **``CLOSE`` IS NOT A LEG OF ANY LIST, AND THE NAME IS BY ANALOGY.** A
    discretionary ``SignalAction.CLOSE`` dispatches a standalone ``MARKET``
    sell under Q-C section 4b -- it is never submitted as part of an order
    list, and it will never appear in an ``OrderList``'s ``orderReports``. A
    reader who takes this enum's name literally will go looking for it there
    and find nothing. It lives here because what the enum actually governs is
    the **leg-code segment of one of our client order IDs**, and a close sell
    needs one of those for exactly the reason the legs do: Q-C section 6 makes
    the ID derivable by pure computation, which is what lets a timed-out write
    be resolved by querying the ID we *would have sent*.

    **It is deliberately absent from :data:`_ID_PATTERN`.** See
    :data:`_CLOSE_ID_PATTERN`: admitting it there would feed a close sell into
    the reconciler's protective compare set.
    """

    WORKING = "W"
    STOP_LOSS = "SL"
    TAKE_PROFIT = "TP"
    #: A discretionary close sell. Two characters, matching the worst measured
    #: leg code, so :data:`MAX_GENERATION` -- which was DERIVED from that
    #: two-character case -- is unchanged by its arrival.
    CLOSE = "CL"


#: The close form's pattern. See the block above :class:`OrderListLeg` for why
#: it is a separate pattern; it lives here because it reads ``CLOSE.value``.
_CLOSE_ID_PATTERN: Final = re.compile(_ID_BODY + re.escape(OrderListLeg.CLOSE.value) + r"$")


class ClientOrderIdParts(NamedTuple):
    """The segments of one of our client order IDs.

    A ``NamedTuple`` rather than a frozen pydantic model: the "value objects are
    frozen pydantic models" rule governs the *domain*, and this is a wire-format
    decomposition in an adapter. It matches ``_ApiRule`` next door in
    ``exchange/models.py``.
    """

    symbol: str
    entry_bar_time: datetime
    generation: int
    leg: OrderListLeg


class ListClientOrderIdParts(NamedTuple):
    """The segments of one of our LIST-level client order IDs.

    **A separate type, and the absence of ``leg`` is the point.** A list is not
    a leg, which is why :data:`LIST_SUFFIX` is deliberately not a member of
    :class:`OrderListLeg`; reusing :class:`ClientOrderIdParts` would need a
    ``leg`` value that does not exist. The two decompositions are different
    shapes because the two identities are.
    """

    symbol: str
    entry_bar_time: datetime
    generation: int


def client_order_id(
    symbol: str,
    entry_bar_time: datetime,
    leg: OrderListLeg,
    *,
    generation: int = 0,
) -> str:
    """Build the section 6 client order ID for one leg.

    Pure: no persistence, no I/O, no clock. Identical across restarts, which is
    what makes the timed-out-write recovery path able to query the IDs it *would
    have sent* without having stored them.

    ``generation`` defaults to 0 and **nothing in this module computes a
    non-zero one** -- see the module docstring. A caller that has recovered a
    higher generation from the venue may pass it.

    **:attr:`OrderListLeg.CLOSE` IS REFUSED HERE.** It is a member of that enum
    for the reason the enum's docstring gives, and it is not a leg of a list.
    Building it through this function would succeed and produce an ID that
    :func:`parse_client_order_id` cannot read -- unparseable by its own
    family's parser, silently, and only at the moment something tried to
    resolve it. Refusing costs one line and converts that into a caller bug
    caught without I/O. :func:`close_client_order_id` is the builder.

    :raises ValueError: ``entry_bar_time`` is naive, ``generation`` is outside
        ``0..MAX_GENERATION``, or ``leg`` is ``CLOSE``. All three are caller
        bugs detectable without building anything.
    :raises ContractViolationError: the assembled ID violates the venue's
        measured rule. The message says **which** rule, which the venue's own
        message does not.
    """
    if leg is OrderListLeg.CLOSE:
        raise ValueError(
            "OrderListLeg.CLOSE is not a leg of an order list and has no place in a leg ID; "
            "use close_client_order_id. Building it here would produce an ID that "
            "parse_client_order_id refuses by design, which would surface only when "
            "something tried to resolve it"
        )
    return _assemble(symbol, entry_bar_time, generation, leg.value)


def list_client_order_id(
    symbol: str,
    entry_bar_time: datetime,
    *,
    generation: int = 0,
) -> str:
    """Build the LIST-level client order ID, which section 6 does not define.

    Section 3 requires ``listClientOrderId`` on both shapes; section 6's scheme
    covers leg IDs only. This closes that gap on the same terms -- same seeds,
    same guard, same generation bound -- with :data:`LIST_SUFFIX` in the leg
    position. It is an EXTENSION of section 6, recorded for amendment at
    rotation rather than smuggled in as an implementation detail.

    Deliberately not recoverable through :func:`parse_client_order_id`, which
    recognises legs. A list ID never appears in ``get_open_orders`` -- that
    endpoint returns orders -- so the filter that parser exists for never meets
    one.

    **ANNOTATED: the paragraph above is still true of the LEG parser, and its
    second sentence no longer justifies having no list parser at all.** It
    reasons from one endpoint, and a caller has since arrived at another:
    ``get_all_order_lists`` returns ``listClientOrderId``, so a boot-time check
    asking *"is one of OUR lists still live on this symbol"* meets list IDs
    routinely. :func:`parse_list_client_order_id` serves that caller. The two
    parsers remain disjoint -- see :data:`_LIST_ID_PATTERN` for why that is
    structural rather than maintained -- so nothing about the leg filter
    changes.

    :raises ValueError: as :func:`client_order_id`.
    :raises ContractViolationError: as :func:`client_order_id`.
    """
    return _assemble(symbol, entry_bar_time, generation, LIST_SUFFIX)


def close_client_order_id(
    symbol: str,
    entry_bar_time: datetime,
    *,
    generation: int = 0,
) -> str:
    """Build the client order ID for a discretionary close sell.

    Q-C section 4b's ``MARKET`` sell is a standalone order, not a leg -- see
    :class:`OrderListLeg` for why its code lives in that enum anyway.

    **``entry_bar_time`` IS THE POSITION'S ENTRY BAR, NOT THE CLOSE'S BAR**, and
    that is the whole of what makes this resolvable. The seed has to be
    something a restarted process can re-derive, and after a restart the bar the
    close was decided on is gone -- it lived only in the dead process's memory.
    The entry bar survives on :attr:`Position.entry_bar_time`, which is
    precisely why section 5 put it there rather than relying on ``opened_at``.
    So a close ID is derivable from the position alone, exactly as a leg ID is.

    The cost is stated rather than hidden: a symbol can carry **one** derivable
    close ID per position per generation. That is sufficient because a position
    is closed once -- and because the pending guard refuses a second dispatch
    while the first is unresolved. A second close on the same position would
    need a generation, which is the same escape hatch the legs use.

    Pure: no persistence, no I/O, no clock. Same seeds, same guard and same
    generation bound as :func:`client_order_id`, through the same
    :func:`_assemble`.

    :raises ValueError: as :func:`client_order_id`.
    :raises ContractViolationError: as :func:`client_order_id`.
    """
    return _assemble(symbol, entry_bar_time, generation, OrderListLeg.CLOSE.value)


def _assemble(symbol: str, entry_bar_time: datetime, generation: int, suffix: str) -> str:
    """Validate the seeds, build the ID, and enforce the venue's rule.

    Shared so the leg and list forms cannot drift apart in their bound, their
    epoch arithmetic or their guard -- the three things a second copy would get
    subtly wrong.
    """
    if entry_bar_time.tzinfo is None or entry_bar_time.tzinfo.utcoffset(entry_bar_time) is None:
        raise ValueError(f"entry_bar_time must be timezone-aware, got naive {entry_bar_time!r}")
    if not 0 <= generation <= MAX_GENERATION:
        raise ValueError(
            f"generation must be in 0..{MAX_GENERATION}, got {generation}. "
            "The ceiling is what the 36-character limit admits for a 12-character "
            "symbol and a 2-character leg code."
        )

    # Integer arithmetic throughout: `timestamp()` returns a float, and a
    # millisecond epoch has no business passing through one.
    ms = (entry_bar_time - _EPOCH) // timedelta(milliseconds=1)
    candidate = f"{ID_PREFIX}{symbol}-{ms}-{generation}-{suffix}"
    _enforce_venue_rule(candidate)
    return candidate


def _enforce_venue_rule(candidate: str) -> None:
    """Reject an ID the venue would reject, saying which rule it broke.

    **Length first, character class second, and never one combined pattern.**
    The venue reports a length violation as "Illegal characters found in
    parameter ..." (MEASURED, M5c-C), so anyone debugging an over-long ID goes
    looking for a bad character. Checking the two separately is the only reason
    this function exists: it is the one place the real cause can be named,
    because by the time the venue answers, the message has already been
    mislabelled.
    """
    if len(candidate) > MAX_CLIENT_ORDER_ID_LENGTH:
        raise ClientContractViolationError(
            f"client order ID is {len(candidate)} characters, over the venue's "
            f"limit of {MAX_CLIENT_ORDER_ID_LENGTH}: {candidate!r}. This is a "
            "LENGTH violation, not a character-class one -- the venue would "
            "report it as 'Illegal characters found', which names the wrong rule."
        )
    if _LEGAL_CHARS.fullmatch(candidate) is None:
        raise ClientContractViolationError(
            f"client order ID contains characters outside the venue's class "
            f"[A-Za-z0-9_-]: {candidate!r}. This is a CHARACTER-CLASS violation; "
            "the length is within the limit."
        )


def parse_client_order_id(value: str) -> ClientOrderIdParts | None:
    """Decompose one of our IDs, or return ``None`` if it is not ours.

    **``None`` rather than a raise, because "not ours" is the expected case.**
    Section 6 gives the prefix its purpose: ``get_open_orders`` returns every
    order on the symbol, so a reconciler filtering that list meets foreign IDs
    routinely. Raising would make the ordinary case exceptional -- the same
    reasoning as "insufficient data is not an error" in ``indicators/``.

    A malformed *ours-looking* ID is also ``None``: this function reports
    recognition, not diagnosis, and a caller that needs the distinction has the
    original string.
    """
    match = _ID_PATTERN.fullmatch(value)
    if match is None:
        return None
    return ClientOrderIdParts(
        symbol=match["symbol"],
        entry_bar_time=_EPOCH + timedelta(milliseconds=int(match["ms"])),
        generation=int(match["generation"]),
        leg=OrderListLeg(match["leg"]),
    )


def parse_list_client_order_id(value: str) -> ListClientOrderIdParts | None:
    """Decompose one of our LIST IDs, or return ``None`` if it is not ours.

    ``None`` rather than a raise, for :func:`parse_client_order_id`'s reason:
    the caller enumerates every list on the account, so foreign IDs are the
    expected case rather than an exceptional one.

    **RECOGNITION IS BY PARSING, NEVER BY PREFIX.** A raw
    ``startswith("tb1-")`` admits ``tb1-garbage``, which this refuses -- the
    hardening ``get_own_open_orders`` already applies to legs, applied to lists
    for the same reason.

    **What it recovers is not all it can VERIFY.** ``symbol`` is checkable
    against a configured pair. ``entry_bar_time`` and ``generation`` are read
    off the string and are **unverifiable after a restart**, because the bar a
    previous process traded on lived only in that process's memory -- there is
    nothing to compare them to. They are returned anyway rather than discarded:
    the regex captures them for free, an operator reading a refusal wants to
    know which bar the orphaned list came from, and throwing away recoverable
    evidence is the shape ``resolution.py`` records as discarding what the
    account demonstrably holds. A caller that MATCHES on them is the misuse;
    the symbol is the only field a boot-time check may key on.
    """
    match = _LIST_ID_PATTERN.fullmatch(value)
    if match is None:
        return None
    return ListClientOrderIdParts(
        symbol=match["symbol"],
        entry_bar_time=_EPOCH + timedelta(milliseconds=int(match["ms"])),
        generation=int(match["generation"]),
    )


def parse_close_client_order_id(value: str) -> ClientOrderIdParts | None:
    """Decompose one of our CLOSE IDs, or return ``None`` if it is not ours.

    ``None`` rather than a raise, for :func:`parse_client_order_id`'s reason.

    Returns :class:`ClientOrderIdParts` rather than a fourth tuple type: the
    segments are identical and its ``leg`` field carries
    :attr:`OrderListLeg.CLOSE`, so a caller holding one always knows which
    family it came from. A third NamedTuple with the same four fields would be
    surface with no distinguishing content.

    **It recovers what :func:`parse_client_order_id` deliberately will not.**
    That parser rejects a close ID -- see :data:`_CLOSE_ID_PATTERN` -- so this
    is the only way back from a close ID to its seeds, and the two are
    structurally incapable of both matching one string.

    ``entry_bar_time`` here is the POSITION'S entry bar; see
    :func:`close_client_order_id`.
    """
    match = _CLOSE_ID_PATTERN.fullmatch(value)
    if match is None:
        return None
    return ClientOrderIdParts(
        symbol=match["symbol"],
        entry_bar_time=_EPOCH + timedelta(milliseconds=int(match["ms"])),
        generation=int(match["generation"]),
        leg=OrderListLeg.CLOSE,
    )
