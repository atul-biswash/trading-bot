"""P-3j (M5l P94): a hold made by a REAL driver pass, aged into a stale refusal, end to end.

``M5k-090``'s limit: the staleness rows called ``hold_settlement()`` on a
hand-built position, and nothing drove the driver's hold, the stopped stamp and
the elapsed time together. This does, with the real ``ReconciliationDriver`` and
the real ``RiskManager``, and nothing between them but a position and a clock.

**A LEAF MODULE THAT IMPORTS FROM TWO TEST MODULES, and it says so.** It uses
the driver tests' stub client and booking fixtures and the risk tests' manager
builders, because writing either again would be a second copy of a fixture
that drifts. An import-time break in either module fails this one and nothing
else, so a traceback naming this file may have nothing to do with it -- the
hazard CLAUDE.md records for ``test_modes.py``, with the same remedy.
"""

from __future__ import annotations

from datetime import timedelta

import pytest

from tests.unit.test_reconciliation_driver import (
    _TERMINAL,
    _UNREADABLE,
    _booking_position,
    _candle,
    _driver,
    _filled_leg,
    _Pass,
    _portfolio,
    _StubClient,
)
from tests.unit.test_reconciliation_driver import (
    NOW as DRIVER_NOW,
)
from tests.unit.test_risk_manager import (
    SYMBOL,
    FakeClock,
    FakeProvider,
    build_manager,
    buy,
    candle,
    multi_pairs,
)
from trading_bot.core.enums import ProtectionState, RefusalStage

#: The settled order id the driver fixtures' filled leg carries.
BTC_ID = "777"


@pytest.mark.parametrize(
    ("answer", "passes", "reason"),
    [
        (_TERMINAL["foreign_fee"], 1, "foreign_fee_asset (R2): one fetch, then held"),
        (_UNREADABLE["transport"], 5, "settlement_timeout (P-3b): five failed passes, then held"),
    ],
    ids=["foreign_fee", "settlement_timeout"],
)
async def test_a_driver_hold_ages_into_a_stale_refusal_that_names_the_held_symbol(
    answer: object, passes: int, reason: str
) -> None:
    """The whole chain, for both ways a driver holds a position.

    1. A real pass holds BTCUSDT, so its stamp is the LAST pass's and then stops.
    2. Inside the staleness bound an entry on ETHUSDT is refused as
       `COMMITTED_RISK_UNKNOWN`, which does not name the hold (P-3d's gap).
    3. A later driver pass does not visit the held position (ruling A): no read,
       no stamp.
    4. Past the bound the refusal is `POSITION_STALE`, and it names `BTCUSDT`
       as held.

    MUTATIONS: remove the held clause (step 4 fails); let the driver visit a
    held position (step 3 fails, and the stamp moves so step 4 is not stale);
    drop `hold_settlement` from the timeout path (step 1 fails for that row).
    """
    assert SYMBOL == "BTCUSDT"  # the driver fixtures' symbol; the signal is for the OTHER pair
    position = _booking_position()
    portfolio = _portfolio(position)
    client = _StubClient({"BTCUSDT": [_filled_leg("BTCUSDT")]}, trades={"777": answer})  # type: ignore[dict-item]
    tick = _Pass()
    driver = _driver(portfolio, client, clock=tick)

    for _ in range(passes):
        await driver(_candle())
        tick.advance()

    # 1. Held by a real pass; the stamp is the last pass's, set before the hold.
    assert position.settlement_hold is True, reason
    stamp = position.last_reconciled_at
    assert stamp == DRIVER_NOW + timedelta(minutes=2 * (passes - 1))
    assert position.protection is ProtectionState.UNKNOWN
    assert BTC_ID in client.settled and client.settled == [BTC_ID] * passes

    clock = FakeClock(stamp + timedelta(seconds=10))
    manager, _ = build_manager(
        provider=FakeProvider(candles={SYMBOL: candle(), "ETHUSDT": candle(symbol="ETHUSDT")}),
        pairs=multi_pairs(SYMBOL, "ETHUSDT"),
        clock=clock,
    )

    # 2. Inside the bound: refused, and nothing names the hold.
    inside = manager.evaluate(buy(symbol="ETHUSDT"), portfolio=portfolio)
    assert not inside.approved
    assert inside.stage is RefusalStage.COMMITTED_RISK_UNKNOWN
    assert "held" not in inside.reason

    # 3. A later pass over the same portfolio does not touch the held position.
    asked, queried, settled = list(client.asked), list(client.queried), list(client.settled)
    await driver(_candle())
    assert (client.asked, client.queried, client.settled) == (asked, queried, settled)
    assert position.last_reconciled_at == stamp

    # 4. Past the bound: stale by ageing, and the reason names the held symbol.
    clock.now = stamp + timedelta(seconds=181)
    stale = manager.evaluate(buy(symbol="ETHUSDT"), portfolio=portfolio)
    assert not stale.approved
    assert stale.stage is RefusalStage.POSITION_STALE
    assert "(held: BTCUSDT)" in stale.reason
    assert "1 open position(s) have not been fully reconciled" in stale.reason
