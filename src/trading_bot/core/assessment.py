"""The risk decision as a value: the verdict, the intent, and the pair context.

These are what ``risk/`` hands to the layers above it, so they are domain
models rather than risk internals. They live here for the reason ``core/``
exists at all -- an outer layer may depend on them, and they depend on nothing
outward.

That direction is not a preference here, it is load-bearing.
:class:`RiskAssessment` and :class:`EntryIntent` annotate ``levels`` as
:class:`~trading_bot.core.models.ProtectiveLevels`, and these are **pydantic**
models whose fields are resolved when the class is created -- so this module
needs that type at runtime, not merely for type checking. While it lived in
``risk/rules.py`` that import closed a cycle back through ``risk/__init__`` to
``risk/manager.py`` and into this module half-initialised.

:class:`PairContext` is the odd one out and the name was weighed rather than
defaulted: it is a pair's exchange context, not part of a verdict. It travels
with the other two because separating it would cut ``manager.py``'s class block
twice and decide ``__all__`` twice, to save a filename. If this module is ever
renamed, that is the reason.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, model_validator

from trading_bot.core.enums import OrderSide, RefusalStage
from trading_bot.core.models import (
    Money,
    ProtectiveLevels,
    RiskDecision,
    SizingDecision,
    SymbolInfo,
)

__all__ = ["EntryIntent", "ExitIntent", "PairContext", "RiskAssessment"]


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True)


class PairContext(_Frozen):
    """What the manager must know about a tradeable pair, beyond its config.

    One object rather than two parallel mappings so a pair is either fully known
    or not known at all -- there is no state in which the timeframe resolves and
    the filters do not.
    """

    #: The timeframe whose buffer backs this symbol's ATR calculation.
    timeframe: str
    #: Exchange filters: the price tick protective levels round to, and the lot
    #: filters sizing must satisfy.
    symbol_info: SymbolInfo


class EntryIntent(_Frozen):
    """An approved, sized, protected entry -- not yet placed.

    Deliberately **not** an ``OrderRequest``. That type has no take-profit
    field, and its ``stop_price`` means "the trigger price of this order", not
    "the protective stop guarding this entry". Mapping this to the entry order
    and its protective legs is execution's job.

    Split from a single ``TradeIntent`` because an entry carries a limit price
    and a ``CLOSE`` dispatches ``MARKET`` with none. One field cannot carry
    both, and a field meaning different things by ``side`` makes the validator
    conditional on ``side`` -- an invariant somebody eventually inverts.
    """

    symbol: str
    side: OrderSide = OrderSide.BUY
    quantity: Money
    #: The closed candle's close: what the decision was computed against.
    reference_price: Money
    #: The marketable limit actually sent.
    #:
    #: **PLACEHOLDER: equal to ``reference_price`` until the commit that derives
    #: it from ``max_entry_slippage``.** That commit also re-prices the
    #: protective levels, because ``levels.entry_price == entry_limit`` below
    #: forces ``compute_protective_levels`` to be called with the limit rather
    #: than the close. Equality satisfies the direction invariant trivially, and
    #: no test asserts it -- they assert ``entry_limit >= reference_price``.
    entry_limit: Money
    #: Required: the four-way placement branch routes on which levels are
    #: absent, and "neither enabled" is still a ``ProtectiveLevels`` with both
    #: absent and a ``basis`` saying why.
    levels: ProtectiveLevels

    @model_validator(mode="after")
    def _check_invariants(self) -> EntryIntent:
        if self.quantity <= 0:
            raise ValueError(
                f"a trade intent must carry a positive quantity, got {self.quantity}; "
                "'do not trade' is a RiskAssessment with no intent, not a zero-size one"
            )
        if self.entry_limit <= 0:
            raise ValueError(f"entry_limit must be > 0, got {self.entry_limit}")
        if self.reference_price <= 0:
            raise ValueError(f"reference_price must be > 0, got {self.reference_price}")
        # Makes the slippage DIRECTION a property of the type, unfakeable
        # independently of whatever bound `max_entry_slippage` carries in
        # config. It is the one thing here that could silently invert.
        if self.entry_limit < self.reference_price:
            raise ValueError(
                f"entry_limit {self.entry_limit} is below reference_price "
                f"{self.reference_price}; slippage on a buy may only move the limit up"
            )
        if self.side is not OrderSide.BUY:
            raise ValueError(f"an entry opens a long on spot, so it is a BUY; got {self.side}")
        # The levels carry their own symbol and entry price; disagreement would
        # mean protecting one position with another's stop.
        if self.levels.symbol != self.symbol:
            raise ValueError(f"levels are for {self.levels.symbol}, not {self.symbol}")
        if self.levels.entry_price != self.entry_limit:
            raise ValueError(
                f"levels priced at {self.levels.entry_price} but intent at {self.entry_limit}"
            )
        return self


class ExitIntent(_Frozen):
    """An approved exit -- not yet placed, and carrying no limit price.

    A ``CLOSE`` dispatches ``MARKET``: the position should not be held, and a
    limit that missed would leave it held and unprotected. So there is no
    ``entry_limit`` here and no ``levels`` -- an exit closes a position rather
    than opening one to protect.
    """

    symbol: str
    side: OrderSide = OrderSide.SELL
    quantity: Money
    #: The closed candle's close the exit was decided on. Not a limit: the fill
    #: price is unknown until it fills.
    reference_price: Money

    @model_validator(mode="after")
    def _check_invariants(self) -> ExitIntent:
        if self.quantity <= 0:
            raise ValueError(
                f"a trade intent must carry a positive quantity, got {self.quantity}; "
                "'do not trade' is a RiskAssessment with no intent, not a zero-size one"
            )
        if self.reference_price <= 0:
            raise ValueError(f"reference_price must be > 0, got {self.reference_price}")
        if self.side is not OrderSide.SELL:
            raise ValueError(f"an exit closes a long on spot, so it is a SELL; got {self.side}")
        return self


class RiskAssessment(_Frozen):
    """The complete verdict on one signal: the intent, or why there is none.

    Carries the component results that were reached before the verdict was
    settled, so an operator (and a test) can see *where* a signal stopped --
    limits, protective levels or sizing -- without parsing the reason string.
    Components are ``None`` when evaluation refused before computing them.

    :attr:`stage` names that stopping point directly, reported by
    :meth:`RiskManager.evaluate` at the site that refuses rather than inferred
    afterwards from which components are populated. Four of the refusals return
    every component as ``None`` and are separable only by position in
    ``evaluate``'s sequence, so an outside observer could label them only by
    re-deriving that control flow -- which is what ``engine.modes`` did until
    M4b, and what adding a refusal path or reordering two checks silently
    invalidated.

    It is **required but nullable**: there is no default, so every construction
    site has to say something, and an approval says ``None`` deliberately rather
    than by omission.
    """

    symbol: str
    approved: bool
    reason: str
    #: Where evaluation stopped; ``None`` on an approval, which stopped nowhere.
    stage: RefusalStage | None
    intent: EntryIntent | ExitIntent | None = None
    decision: RiskDecision | None = None
    levels: ProtectiveLevels | None = None
    sizing: SizingDecision | None = None

    @model_validator(mode="after")
    def _check_invariants(self) -> RiskAssessment:
        if not self.reason:
            raise ValueError("reason must explain the assessment, including an approval")
        if self.approved != (self.intent is not None):
            raise ValueError(
                f"approved={self.approved} contradicts intent={self.intent!r}; an "
                "approval carries the intent it approved and a refusal carries none"
            )
        # Note the polarity: `stage` follows RiskDecision.rule's axis -- present
        # on a refusal, absent on an approval -- and therefore reads inverted
        # against `intent` two lines above, which is present on an approval.
        if self.approved != (self.stage is None):
            raise ValueError(
                f"approved={self.approved} contradicts stage={self.stage!r}; a refusal "
                "must name the stage it stopped at and an approval must name none"
            )
        return self
