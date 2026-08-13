"""Custom exception hierarchy.

A single base (:class:`TradingBotError`) lets callers catch everything the bot
raises while still allowing narrow ``except`` clauses for specific failures.
"""

from __future__ import annotations


class TradingBotError(Exception):
    """Base class for every error raised by the bot."""


# --- Configuration ----------------------------------------------------------
class ConfigError(TradingBotError):
    """Invalid, missing, or contradictory configuration."""


# --- Exchange ---------------------------------------------------------------
class ExchangeError(TradingBotError):
    """Base class for exchange-related failures."""


class ExchangeConnectionError(ExchangeError):
    """Network/transport failure talking to the exchange."""


class ExchangeAPIError(ExchangeError):
    """The exchange returned an error response, and it carries the exchange's
    own identifier for it.

    **This is the base of every classified venue error**, which is one principle
    rather than a convenience: if the exchange told us something, the thing it
    told us has a code, and a classification that discards the code leaves an
    operator holding our vocabulary instead of Binance's. Before M5c's hierarchy
    pass, six of seven classified outcomes dropped it -- so the *better* we
    classified, the less machine-readable identity survived, which is backwards.

    **``code`` is ``int | None``, and "carries the code" is weaker than it
    reads.** Two ``src/`` sites raise this with **no** code --
    ``BinanceClient._fetch_symbol_info`` on an unknown symbol, and
    ``to_symbol_info`` on a malformed payload -- because both are *client-side*
    refusals where no venue response exists. **A caller reading ``.code`` must
    therefore handle ``None``**, and the field is deliberately not tightened to
    ``int``: doing so would require splitting those two off into a separate
    type, which would assert a distinction neither of them needs.

    :param message: human-readable description.
    :param code: exchange-specific error code, or ``None`` for a client-side
        refusal that never reached the venue.
    """

    def __init__(self, message: str, *, code: int | None = None) -> None:
        super().__init__(message)
        self.code = code


class RateLimitError(ExchangeAPIError):
    """A rate limit or IP ban was hit; back off before retrying."""


class OrderError(ExchangeAPIError):
    """An order was rejected or could not be created/canceled."""


class InsufficientBalanceError(OrderError):
    """Not enough free balance to place the requested order.

    **Placed under :class:`OrderError` at M5c's hierarchy follow-on, by the
    discriminator that decided every other family rather than on its own
    merits.** That test is whether the venue is refusing a *trade* -- something a
    caller may reasonably handle -- or refusing to *parse*, where nothing can be
    done. Insufficient balance is the most handleable rejection there is: resize,
    skip the signal, or halt entries. It is account state, not our bug.

    **The placement it replaces was inherited, not argued** -- the third instance
    of that shape in this milestone, after ``-1111`` and the reject set. It sat
    directly under :class:`ExchangeError` from the scaffold, and the hierarchy
    pass moved it to :class:`ExchangeAPIError` only as a side effect of giving
    every classified error its code.

    **It also removes a real incoherence in ``-2010``.** That code carries two
    measured meanings separated only by message text, and until this change they
    landed in two different branches: an ``except OrderError`` caught the
    duplicate and not the balance failure, for a reason nobody recorded. They are
    now siblings under one parent -- one code, two meanings, both order
    rejections -- which is what the tree should have said all along.

    ``code`` survives the move: :class:`OrderError` is itself an
    :class:`ExchangeAPIError`, so the hierarchy pass's principle holds through
    its own first follow-on.
    """


class ContractViolationError(ExchangeAPIError):
    """The request is structurally wrong for this endpoint. **Our bug, not a
    market condition.**

    Three measured codes, and the *conditions* are recorded here because the
    exchange's message text for them was never captured -- this prose is the
    only record of what each row means:

    * ``-1106`` -- a forbidden field was sent. Measured on the OTOCO/OTO
      endpoints for ``pendingAbovePrice``, ``pendingAboveTimeInForce``,
      ``pendingBelowPrice`` and ``pendingBelowTimeInForce``
      (``docs/QC_PROTECTIVE_ORDERS.md`` section 3).
    * ``-1159`` -- ``MARKET`` refused as a working type (section 3).
    * ``-1158`` -- ``LIMIT`` refused in the pending-above slot (section 3).

    **This is the PARENT of :class:`MalformedRequestError`, decided at M5c's
    hierarchy pass.** C5 landed the two as a nephew and an uncle and observed
    only that they resembled each other; seeing all six families together showed
    the cost -- their nearest common ancestor was :class:`ExchangeError`, which
    also catches rate limits and order rejections, so **there was no way to catch
    "our bug" as a class at all.** ``except ContractViolationError`` now does.

    ``-1100`` is a contract violation that happens to name a parameter, so the
    payload difference is an argument *for* the relation rather than against it:
    a child adding ``parameter`` to a parent's ``code`` is what subclassing is
    for. Two resembling siblings would have been right only if neither
    generalised the other, and this one does.

    Neither belongs under :class:`OrderError`: there is no market state to
    respond to and nothing a caller can do but stop.

    It derives from :class:`ExchangeAPIError` so that it carries ``code`` -- the
    only identity these errors have, absent their text.

    **No dedicated catcher yet**, and the reclassification changes nothing:
    measured, there is no ``except ExchangeAPIError`` anywhere in ``src/``.
    """


class MalformedRequestError(ContractViolationError):
    """The exchange could not parse the request. **This is our bug, not a market
    condition.**

    Binance returns ``-1100`` for a request whose parameters are ill-formed. The
    measured instance is an over-long client order ID::

        Illegal characters found in parameter 'workingClientOrderId';
        legal range is '^[a-zA-Z0-9-_]{1,36}$'.

    **The message MISLABELS its own cause, and that is measured**: 36 characters
    are accepted and 37 rejected, so a *length* violation is reported as
    "Illegal characters found". Anyone debugging it goes looking for a bad
    character. The embedded regex is the only part of the text that discloses
    the real rule, and it discloses both the length and the character class.

    **It sits outside :class:`OrderError`, and it is the one family in the
    classifier that does.** Every other refinement is the venue refusing a
    *trade*, which a caller may reasonably handle -- retry, skip the signal, log
    and continue. This is the venue refusing to *parse*, and there is nothing a
    caller can do about it except stop. Under ``OrderError`` an
    ``except OrderError`` written for routine rejections would swallow it, which
    is precisely the failure Q-C section 8's "raise loudly" exists to prevent;
    "loud" and "catchable as an ordinary order rejection" are contradictory.

    **It sits under :class:`ContractViolationError` as of M5c's hierarchy
    pass**, not directly under :class:`ExchangeError` as C4 landed it. It is a
    contract violation that happens to name a parameter, so it specialises that
    class rather than resembling it, and it inherits ``code`` in the process --
    which C4's placement discarded. It remains under :class:`ExchangeError`
    transitively, so ``main.py``'s top-level ``except TradingBotError`` still
    reports it as a message rather than a bare traceback.

    ``parameter`` carries the offending parameter name as the exchange spelled
    it, so a caller need not parse the message to know which field was wrong.

    :param message: human-readable description.
    :param parameter: the exchange's parameter name, e.g. ``"workingClientOrderId"``.
    """

    def __init__(self, message: str, *, parameter: str, code: int | None = None) -> None:
        super().__init__(message, code=code)
        self.parameter = parameter


class OrderNotFoundError(OrderError):
    """The exchange has no record of the order this request named.

    Binance returns ``-2011 'Unknown order sent.'``. Measured at M5c on a real
    OTO teardown: cancelling the working leg **auto-cancelled both pending
    legs**, and the follow-up cancels for those two each returned this.

    **Benign is a property of the CALL SITE, not of this class, which is why it
    subclasses ``OrderError`` rather than sitting outside the order hierarchy.**
    On a cancel path it is the expected result of a list that already collapsed
    -- ``docs/QC_PROTECTIVE_ORDERS.md`` section 8 says "benign ... *on cancel
    paths*", and the qualifier is load-bearing. On a **query** path it is the
    opposite: a reconciler that asks for a tracked order by ID and is told no
    such order exists has found a divergence, not a non-event. Same code, same
    message, opposite significance.

    Encoding "benign" in the hierarchy would bake one caller's reading into the
    type and mislead the other, so the class states what the venue reported --
    the order was not found -- and leaves the significance to whoever asked.
    That is the same principle :class:`DuplicateOrderError` is named under.

    Subclassing :class:`OrderError` also keeps this a **refinement**: ``-2011``
    already classified as an ``OrderError``, so no existing catcher changes
    behaviour.

    **No dedicated catcher yet**, deliberately: the cancel path that reads it as
    routine is M5e's. It is raised by a live classifier branch and caught today
    by ``except TradingBotError`` in ``main.py`` -- latent, not dead.
    """


class DuplicateOrderError(OrderError):
    """The exchange reported that this order or order list was already sent.

    Binance returns ``-2010 'Duplicate order sent.'`` when a submission reuses a
    client order ID that is still attached to a **live** order -- measured for a
    single order and for an order list alike, and measured *not* to fire once
    the original has reached a terminal state, because a terminal order's ID is
    released (see ``docs/QC_PROTECTIVE_ORDERS.md`` sections 6 and 8).

    **Named for what the venue reported, not for how a caller reads it.** The
    timed-out-write recovery path treats this as its *success* signal -- a
    re-place that collides proves the original landed and is still working -- but
    that is an interpretation made by the caller. What this class asserts is only
    that the exchange refused a duplicate.

    A subclass of :class:`OrderError` rather than a sibling, for the reason
    :class:`FilterRejectedError` is: the venue did reject an order, so every
    existing ``except OrderError`` keeps catching it and this commit refines a
    classification rather than moving one.

    **It has no dedicated catcher yet**, and that is deliberate rather than
    overlooked: it is raised by a live classifier branch on every matching venue
    response and is caught today by ``except TradingBotError`` in ``main.py``, so
    it is *latent*, not dead. The recovery path that reads it as success arrives
    with M5e.
    """


class FilterRejectedError(OrderError):
    """An order violates a named exchange filter.

    A subclass of :class:`OrderError` rather than a sibling, so every existing
    ``except OrderError`` keeps catching it: a filter rejection *is* an order
    rejection, with the filter named.

    ``filter_name`` carries the exchange's own spelling -- ``PRICE_FILTER``,
    ``LOT_SIZE``, ``NOTIONAL`` -- so a refusal raised locally before dispatch
    and one parsed out of a venue rejection are legible as the same condition.
    A caller must be able to read "which filter" without parsing the message.

    :param message: human-readable description.
    :param filter_name: the exchange's filter name, e.g. ``"PRICE_FILTER"``.
    """

    def __init__(self, message: str, *, filter_name: str, code: int | None = None) -> None:
        super().__init__(message, code=code)
        self.filter_name = filter_name


# --- Data -------------------------------------------------------------------
class DataError(TradingBotError):
    """Missing, malformed, or insufficient market data."""


# --- Strategy ---------------------------------------------------------------
class StrategyError(TradingBotError):
    """A strategy failed to load or produced an invalid signal."""


class StrategyNotFoundError(StrategyError):
    """No strategy is registered under the requested name."""


class StrategyConfigError(StrategyError):
    """A strategy's configured parameters do not match its constructor.

    Raised for wrong parameter *names* (a typo in ``config.yaml``). Wrong
    *values* under correct names raise ``ValueError`` from the strategy itself,
    where the message can be specific about the constraint that failed.
    """


# --- Risk -------------------------------------------------------------------
# There is deliberately no risk exception. A risk outcome is a *value* in this
# system -- SizingDecision, ProtectiveLevels, RiskDecision, RiskAssessment --
# never a raise, because "too small to trade", "no placeable stop this bar" and
# "the daily-loss cap is hit" are routine answers that must carry their reason to
# an operator. `RiskError` / `RiskLimitExceeded` existed here from the scaffold
# until Phase 5 M3 and never acquired a caller; a class whose docstring read
# "risk-management rejections" named precisely the thing M1-M3 decided must not
# be an exception, so keeping it would have invited the pattern back.
#
# Genuinely incoherent *inputs* to the risk rules (non-positive price, non-finite
# ATR) still raise, as bare `ValueError` -- the same convention `indicators/`
# documents: ValueError for invalid parameters, DataError for malformed data.
# Re-add a risk exception only alongside a caller that catches it.


# --- Notifications ----------------------------------------------------------
class NotificationError(TradingBotError):
    """A notification channel failed to deliver a message."""
