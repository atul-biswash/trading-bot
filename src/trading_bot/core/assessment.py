"""The risk decision as a value: the verdict, the intent, and the pair context.

These are what ``risk/`` hands to the layers above it, so they are domain
models rather than risk internals. They live here for the reason ``core/``
exists at all -- an outer layer may depend on them, and they depend on nothing
outward.

That direction is not a preference here, it is load-bearing.
:class:`RiskAssessment` and :class:`TradeIntent` annotate ``levels`` as
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

__all__ = ["PairContext", "RiskAssessment", "TradeIntent"]


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


class TradeIntent(_Frozen):
    """An approved, sized, protected order -- not yet placed.

    Deliberately **not** an ``OrderRequest``. That type has no take-profit
    field, and its ``stop_price`` means "the trigger price of this order", not
    "the protective stop guarding this entry"; expressing an entry plus its two
    protective levels as one ``OrderRequest`` would be a lie execution would
    have to un-learn. Mapping this to the entry order and its protective orders
    is execution's job, where ``_enforce`` re-checks the filters immediately
    before dispatch.
    """

    symbol: str
    side: OrderSide
    quantity: Money
    #: The reference price the intent was computed at -- the signal's price,
    #: which is the closed candle's close with full ``Decimal`` precision.
    price: Money
    #: Protective levels for an entry; ``None`` for an exit, which closes a
    #: position rather than opening one to protect.
    levels: ProtectiveLevels | None = None

    @model_validator(mode="after")
    def _check_invariants(self) -> TradeIntent:
        if self.quantity <= 0:
            raise ValueError(
                f"a trade intent must carry a positive quantity, got {self.quantity}; "
                "'do not trade' is a RiskAssessment with no intent, not a zero-size one"
            )
        if self.price <= 0:
            raise ValueError(f"price must be > 0, got {self.price}")
        if self.levels is not None:
            # The levels carry their own symbol and entry price; disagreement
            # would mean protecting one position with another's stop.
            if self.levels.symbol != self.symbol:
                raise ValueError(f"levels are for {self.levels.symbol}, not {self.symbol}")
            if self.levels.entry_price != self.price:
                raise ValueError(
                    f"levels priced at {self.levels.entry_price} but intent at {self.price}"
                )
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
    intent: TradeIntent | None = None
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
