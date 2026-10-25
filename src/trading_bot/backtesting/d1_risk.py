"""The D1 risk manager: the unchanged ``RiskManager``, sized from each signal's own clamped trail (N5).

N4b ran the six M5n candidates with fixed-fraction sizing and no stop, which made the risk manager's
stop-dependent rules inert. N5 sizes the position so that the loss at the initial stop is 1 percent of
equity (charter section 18), and the initial stop of a D1 position is the first trigger of its trail:
``delta`` basis points below the entry, where ``delta`` is the signal's own ``trail_delta_bps``.

``RiskManager.evaluate`` takes no stop: it derives one from its config, and ``stop_loss.type='percent'``
is exactly a stop supplied as a distance. So this class changes no rule and no formula. It keeps one
UNCHANGED ``RiskManager`` per delta, each built over a copy of the configuration whose
``stop_loss.percent`` is ``delta / 100`` (an exact ``Decimal`` for an integer delta), and ``evaluate``
delegates to the one for the signal's delta. Everything else a manager reads -- the limits, the
provider, the filters, the clock -- is shared, and none of it is state a manager mutates, so each manager
is the one the base class would be if the file carried that percent.

**What it does not do.** It overrides nothing but ``evaluate``. A signal that is not a ``BUY``, that
carries no integer ``trail_delta_bps``, or that arrives while ``stop_loss`` is disabled is evaluated by
the base class with the base configuration, exactly as before; the executor then refuses a ``BUY``
without a delta as it did in N4b. A delta that is not positive is a contract violation of the strategy
and raises ``ValueError``, which the signal handler isolates and which makes the run incomplete.

**Where the stop is priced.** The manager sizes at the signal bar, before any fill exists, so its stop is
``entry_limit x (1 - delta / 10000)`` on the tick, with ``entry_limit`` the close widened by the entry
tolerance. The executor's ``Position.stop_loss`` is ``fill x (1 - delta / 10000)``; the two differ by the
entry slippage and a tick, and the committed-risk check reads the executor's.
"""

from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING

from trading_bot.backtesting.d1_executor import DELTA_KEY
from trading_bot.core.enums import SignalAction, StopType
from trading_bot.risk.manager import Clock, RiskAssessment, RiskManager
from trading_bot.utils.helpers import utc_now

if TYPE_CHECKING:  # pragma: no cover - typing only
    from collections.abc import Mapping

    from trading_bot.config.models import RiskConfig
    from trading_bot.core.interfaces import MarketDataProvider
    from trading_bot.core.models import Signal
    from trading_bot.core.portfolio import Portfolio
    from trading_bot.risk.manager import PairContext

__all__ = ["D1RiskManager"]

_HUNDRED = Decimal(100)


class D1RiskManager(RiskManager):
    """A ``RiskManager`` whose percent stop is each signal's own clamped trail."""

    def __init__(
        self,
        *,
        config: RiskConfig,
        provider: MarketDataProvider,
        pairs: Mapping[str, PairContext],
        clock: Clock = utc_now,
    ) -> None:
        super().__init__(config=config, provider=provider, pairs=pairs, clock=clock)
        self._by_delta: dict[int, RiskManager] = {}

    def evaluate(self, signal: Signal, *, portfolio: Portfolio) -> RiskAssessment:
        """The base ``evaluate`` over the stop of this signal's delta; see the module docstring."""
        delta = signal.metadata.get(DELTA_KEY)
        if (
            signal.action is not SignalAction.BUY
            or type(delta) is not int
            or not self._config.stop_loss.enabled
        ):
            return super().evaluate(signal, portfolio=portfolio)
        return self._manager_for(delta).evaluate(signal, portfolio=portfolio)

    def _manager_for(self, delta: int) -> RiskManager:
        manager = self._by_delta.get(delta)
        if manager is None:
            if delta <= 0:
                raise ValueError(
                    f"a trail of {delta} basis points is not a distance below the entry"
                )
            stop = self._config.stop_loss.model_copy(
                update={"type": StopType.PERCENT, "percent": Decimal(delta) / _HUNDRED}
            )
            manager = RiskManager(
                config=self._config.model_copy(update={"stop_loss": stop}),
                provider=self._provider,
                pairs=self._pairs,
                clock=self._clock,
            )
            self._by_delta[delta] = manager
        return manager
