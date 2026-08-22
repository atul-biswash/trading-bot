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
    "OrderListLeg",
    "client_order_id",
    "list_client_order_id",
    "parse_client_order_id",
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

#: Symbols carry no ``-``, and both numeric segments are digits, so the split is
#: unambiguous and the parser needs no backtracking heuristics.
_ID_PATTERN: Final = re.compile(
    r"^tb1-(?P<symbol>[A-Za-z0-9]+)-(?P<ms>\d+)-(?P<generation>\d+)-(?P<leg>W|SL|TP)$"
)


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

    The three codes are section 3's leg set and are what the M5c probe sent, so
    they match the only IDs the venue has been measured to honour byte-for-byte.
    """

    WORKING = "W"
    STOP_LOSS = "SL"
    TAKE_PROFIT = "TP"


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

    :raises ValueError: ``entry_bar_time`` is naive, or ``generation`` is
        outside ``0..MAX_GENERATION``. Both are caller bugs detectable without
        building anything.
    :raises ContractViolationError: the assembled ID violates the venue's
        measured rule. The message says **which** rule, which the venue's own
        message does not.
    """
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

    :raises ValueError: as :func:`client_order_id`.
    :raises ContractViolationError: as :func:`client_order_id`.
    """
    return _assemble(symbol, entry_bar_time, generation, LIST_SUFFIX)


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
