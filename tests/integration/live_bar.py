"""The one assertion the live market-data integration test makes about the first live candle (R-DI, M5m P126).

R-DI, verbatim: *"test_testnet_provider_seeds_history_and_extends_it_live asserts what holds on both paths: after the first
live candle, the buffer's last bar equals the stream's closed bar, whether it was appended or replaced in place. An identical
replacement is correct behaviour (M5m-571). The test keeps its subject."*

It lives in a module of its own, not in the integration test, because that test needs credentials, the network and a minute
boundary, and so cannot be mutated deterministically. Here it is a function of a frame and a candle, and
``tests/unit/test_integration_live_bar.py`` shows what it accepts and what it refuses.

WHY "EQUALS", NOT "DIFFERS FROM THE SEED". The first live bar is either a new bar (appended) or a re-delivery of the seed's last
bar (replaced in place), and which one happens is a race with the minute boundary. On the replace path the REST seed may have been
fetched AFTER that bar closed, so it already holds the final values and the stream delivers the same ones: an identical
replacement. The earlier assertion, that the row must differ from the seeded one, failed on exactly that (the gate of P125,
M5m-571). What every correct outcome shares is that the buffer's last bar IS the stream's closed bar. A provider that dropped
the bar would leave the seed's last row, which differs from the candle unless it was already identical, and then dropping it is
indistinguishable from replacing it and does no harm.
"""

from __future__ import annotations

import pandas as pd
import pytest

from trading_bot.core.models import Candle

_COLUMNS = ("open", "high", "low", "close", "volume")
_RELATIVE = 1e-12  # float64 noise only; one tick (0.01) on a BTC price is a relative 1.2e-7


def assert_last_bar_is_the_live_candle(frame: pd.DataFrame, candle: Candle) -> None:
    """The frame's last row is the candle: its open time and each of the five OHLCV values.

    The frame is float64 (the data layer's one Decimal to float boundary) and the candle is exact, so the values are compared
    through ``float`` with ``pytest.approx`` at a relative 1e-12 (float noise, not a tick), where the integration test used to compare only the close, loosely.
    """
    assert frame.index[-1] == candle.open_time, (
        f"the buffer's last bar opens {frame.index[-1]} but the stream's closed bar opens {candle.open_time}"
    )
    last = frame.iloc[-1]
    for column in _COLUMNS:
        expected = float(getattr(candle, column))
        assert float(last[column]) == pytest.approx(expected, rel=_RELATIVE, abs=0), (
            f"the buffer's last {column} is {last[column]} but the stream's closed bar has {expected}"
        )
