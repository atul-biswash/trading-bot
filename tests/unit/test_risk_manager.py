"""Tests for the risk manager -- limits, the ATR bridge, and the composed path.

Hermetic: no network, no real time, no patching. The clock is injected, the
market-data provider is a scripted fake, and the exchange filters are a plain
dict -- the manager performs no I/O, so nothing has to be mocked to keep it
offline.

Exact ``Decimal`` assertions in money code. A result that is merely *close* is a
bug, and a tolerant assertion cannot detect the float leak the ``Money`` guard
exists to prevent.
"""

from __future__ import annotations

import inspect
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import TYPE_CHECKING

import numpy as np
import pandas as pd
import pytest
from pydantic import ValidationError

from trading_bot.config.models import (
    PositionSizingConfig,
    RiskConfig,
    RiskLimitsConfig,
    StopLossConfig,
    TakeProfitConfig,
    TrailingStopConfig,
)
from trading_bot.core.enums import (
    OrderSide,
    PositionSide,
    PositionSizingMethod,
    ProtectionState,
    RefusalStage,
    RiskRule,
    SignalAction,
    StopType,
)
from trading_bot.core.interfaces import MarketDataProvider
from trading_bot.core.interfaces import RiskManager as RiskManagerPort
from trading_bot.core.models import (
    Candle,
    Position,
    ProtectiveLevels,
    RiskDecision,
    Signal,
    SymbolInfo,
)
from trading_bot.core.portfolio import Portfolio
from trading_bot.risk.manager import (
    EntryIntent,
    ExitIntent,
    PairContext,
    RiskAssessment,
    RiskManager,
)
from trading_bot.risk.rules import ExitReason, should_exit

if TYPE_CHECKING:  # pragma: no cover - typing only
    from collections.abc import Callable, Mapping

    from trading_bot.core.interfaces import CandleHandler

D = Decimal

#: A fixed instant every test measures from. Midday UTC, so a test can advance
#: hours in either direction without accidentally crossing a day boundary.
NOW = datetime(2026, 7, 25, 12, 0, tzinfo=timezone.utc)

SYMBOL = "BTCUSDT"
TIMEFRAME = "1m"


# --------------------------------------------------------------------------
# Fakes and builders
# --------------------------------------------------------------------------
class FakeClock:
    """An injectable clock the test advances explicitly."""

    def __init__(self, now: datetime = NOW) -> None:
        self.now = now

    def __call__(self) -> datetime:
        return self.now

    def advance(self, **delta: float) -> None:
        self.now += timedelta(**delta)


class FakeProvider(MarketDataProvider):
    """Port-conformant provider serving canned frames and candles.

    ``candle_count`` is derived from the frame length so ``is_ready`` -- the
    concrete method the manager's ATR gate calls -- behaves exactly as it does
    in production rather than being stubbed out.
    """

    def __init__(
        self,
        frames: Mapping[str, pd.DataFrame] | None = None,
        candles: Mapping[str, Candle | None] | None = None,
    ) -> None:
        self._frames = dict(frames or {})
        self._candles = dict(candles or {})

    def track(self, symbol: str, timeframe: str) -> None:
        pass

    def on_candle(self, handler: CandleHandler) -> None:
        pass

    async def start(self) -> None:
        pass

    async def stop(self) -> None:
        pass

    def get_dataframe(self, symbol: str, timeframe: str) -> pd.DataFrame:
        return self._frames.get(symbol, ohlcv(0))

    def candle_count(self, symbol: str, timeframe: str) -> int:
        return len(self._frames.get(symbol, ohlcv(0)))

    def last_candle(self, symbol: str, timeframe: str) -> Candle | None:
        return self._candles.get(symbol)


def ohlcv(
    bars: int, *, high: float = 101.0, low: float = 99.0, close: float = 100.0
) -> pd.DataFrame:
    """A float64 OHLCV frame shaped like the provider's, with a constant range.

    A constant ``high``/``low``/``close`` makes the true range constant too, so
    ATR equals that range exactly and the expected stop can be written down.
    """
    index = pd.DatetimeIndex(
        [NOW - timedelta(minutes=bars - i) for i in range(bars)], name="open_time", tz="UTC"
    )
    return pd.DataFrame(
        {
            "open": np.full(bars, close),
            "high": np.full(bars, high),
            "low": np.full(bars, low),
            "close": np.full(bars, close),
            "volume": np.full(bars, 1.0),
        },
        index=index,
    )


def candle(close: str = "100", *, symbol: str = SYMBOL) -> Candle:
    return Candle(
        symbol=symbol,
        timeframe=TIMEFRAME,
        open_time=NOW,
        close_time=NOW,
        open=D("100"),
        high=D("101"),
        low=D("99"),
        close=D(close),
        volume=D("1"),
    )


def symbol_info(
    *,
    symbol: str = SYMBOL,
    price_tick: str = "0.01",
    step_size: str = "0.001",
    min_qty: str = "0.001",
    min_notional: str = "10",
) -> SymbolInfo:
    return SymbolInfo(
        symbol=symbol,
        base_asset=symbol[:3],
        quote_asset="USDT",
        price_tick=D(price_tick),
        step_size=D(step_size),
        min_qty=D(min_qty),
        min_notional=D(min_notional),
    )


def risk_config(
    *,
    method: PositionSizingMethod = PositionSizingMethod.FIXED_FRACTION,
    stop_loss: StopLossConfig | None = None,
    take_profit: TakeProfitConfig | None = None,
    trailing_stop: TrailingStopConfig | None = None,
    max_position_size_percent: str = "100",
    max_open_positions: int = 3,
    max_daily_loss_percent: str = "5.0",
    cooldown_minutes: int = 15,
) -> RiskConfig:
    """A RiskConfig with the caps opened up unless a test narrows them.

    ``max_position_size_percent`` defaults to 100 so that a test exercising a
    sizing method sees that method's own answer rather than the cap's.
    """
    return RiskConfig(
        position_sizing=PositionSizingConfig(method=method),
        stop_loss=stop_loss or StopLossConfig(),
        take_profit=take_profit or TakeProfitConfig(),
        trailing_stop=trailing_stop or TrailingStopConfig(),
        limits=RiskLimitsConfig(
            max_position_size_percent=D(max_position_size_percent),
            max_open_positions=max_open_positions,
            max_daily_loss_percent=D(max_daily_loss_percent),
            cooldown_minutes=cooldown_minutes,
        ),
    )


def multi_pairs(*symbols: str) -> dict[str, PairContext]:
    """A pairs mapping covering several symbols, all on the same timeframe."""
    return {
        symbol: PairContext(timeframe=TIMEFRAME, symbol_info=symbol_info(symbol=symbol))
        for symbol in symbols
    }


def build_manager(
    *,
    config: RiskConfig | None = None,
    provider: MarketDataProvider | None = None,
    pairs: Mapping[str, PairContext] | None = None,
    clock: FakeClock | None = None,
) -> tuple[RiskManager, FakeClock]:
    the_clock = clock or FakeClock()
    manager = RiskManager(
        config=config or risk_config(),
        provider=provider or FakeProvider(frames={SYMBOL: ohlcv(50)}, candles={SYMBOL: candle()}),
        pairs=pairs or {SYMBOL: PairContext(timeframe=TIMEFRAME, symbol_info=symbol_info())},
        clock=the_clock,
    )
    return manager, the_clock


def entry_levels(*, entry: str = "100", symbol: str = SYMBOL) -> ProtectiveLevels:
    """Levels priced at ``entry``, satisfying ProtectiveLevels' own side checks.

    A long's stop sits below entry and its take-profit above, and
    ``stop_distance`` must equal ``|entry - stop|`` exactly -- so the numbers
    here are derived from ``entry`` rather than written twice.
    """
    price = D(entry)
    stop = price * D("0.98")
    return ProtectiveLevels(
        symbol=symbol,
        side=PositionSide.LONG,
        entry_price=price,
        stop_loss=stop,
        take_profit=price * D("1.04"),
        stop_distance=price - stop,
        basis="test levels",
    )


def buy(price: str = "100.00", *, symbol: str = SYMBOL) -> Signal:
    return Signal(symbol=symbol, action=SignalAction.BUY, price=D(price), timestamp=NOW)


def long_position(
    *,
    symbol: str = SYMBOL,
    quantity: str = "1",
    entry: str = "100",
    stop_loss: Decimal | None = None,
    take_profit: Decimal | None = None,
    trailing_stop: Decimal | None = None,
    protection: ProtectionState = ProtectionState.UNKNOWN,
    last_reconciled_at: datetime | None = NOW,
) -> Position:
    """A long position, FRESHLY RECONCILED unless a test says otherwise.

    **The stamp defaults to ``NOW``, and that default is a decision.** Before
    the staleness guard existed every fixture here carried ``None`` and it did
    not matter; now ``None`` is maximally stale, so an unstamped default would
    make every test in this file refuse at `POSITION_STALE` before reaching
    what it was written to exercise. Defaulting to fresh keeps each test
    asserting its own subject.

    The consequence is worth naming rather than absorbing: **every existing
    `evaluate` test thereby begins asserting the FRESH path.** That is correct
    -- they were written before staleness existed and were implicitly fresh --
    but it is a property nobody chose until this commit, across every use of
    this helper.
    """
    return Position(
        symbol=symbol,
        side=PositionSide.LONG,
        quantity=D(quantity),
        entry_price=D(entry),
        entry_bar_time=NOW,
        protection=protection,
        opened_at=NOW,
        stop_loss=stop_loss,
        take_profit=take_profit,
        trailing_stop=trailing_stop,
        last_reconciled_at=last_reconciled_at,
    )


# --------------------------------------------------------------------------
# Portfolio: equity, the daily ledger, cooldown
# --------------------------------------------------------------------------
class TestPortfolio:
    def test_equity_is_free_quote_plus_mark_to_market(self) -> None:
        """Equity is total value, not free balance -- the distinction the sizer
        documents, and the difference between a stable position size and one
        that shrinks as capital deploys."""
        portfolio = Portfolio(
            free_quote=D("2500.50"),
            positions={SYMBOL: long_position(quantity="0.5", entry="90")},
        )
        assert portfolio.equity({SYMBOL: D("120.40")}) == D("2560.70")

    def test_equity_ignores_a_closed_position(self) -> None:
        portfolio = Portfolio(
            free_quote=D("1000"),
            positions={
                SYMBOL: Position(
                    symbol=SYMBOL,
                    side=PositionSide.FLAT,
                    quantity=D("0"),
                    entry_price=D("100"),
                    entry_bar_time=NOW,
                    protection=ProtectionState.UNKNOWN,
                )
            },
        )
        assert portfolio.equity({}) == D("1000")
        assert portfolio.position_count == 0

    def test_equity_raises_when_a_position_cannot_be_marked(self) -> None:
        """Defaulting to entry price or zero would misstate the denominator of
        every sizing and daily-loss decision."""
        portfolio = Portfolio(free_quote=D("1000"), positions={SYMBOL: long_position()})
        with pytest.raises(ValueError, match="no mark price"):
            portfolio.equity({})

    def test_realised_pnl_accrues_and_resets_on_the_utc_day_boundary(self) -> None:
        portfolio = Portfolio(free_quote=D("1000"))
        portfolio.record_realised_pnl(D("-120.25"), now=NOW)
        assert portfolio.realised_today(NOW) == D("-120.25")

        # Same UTC day, 11 hours later: still accruing into the same bucket.
        portfolio.record_realised_pnl(D("-10"), now=NOW + timedelta(hours=11))
        assert portfolio.realised_today(NOW + timedelta(hours=11)) == D("-130.25")

        # Past midnight UTC: a fresh day, derived on read rather than rolled.
        assert portfolio.realised_today(NOW + timedelta(hours=13)) == D("0")

    def test_realised_today_derives_the_new_day_without_writing(self) -> None:
        """The read paths are read-only, which is what two docstrings already
        claim -- ``RiskManager.evaluate``'s port docstring ("read, never
        mutated") and this class's own. Before M5b the day roll fired from
        ``realised_today``, so a documented read rewrote the ledger once per UTC
        day, on the first evaluation after midnight -- the path deciding whether
        to open a position.

        Asserted on the fields, not on the return value: the return was already
        correct, and a test that checks only the answer cannot see the write.
        """
        portfolio = Portfolio(free_quote=D("10000"))
        portfolio.record_realised_pnl(D("-450"), now=NOW)

        assert portfolio.realised_today(NOW + timedelta(hours=13)) == D("0")

        assert portfolio.realised_pnl == D("-450")
        assert portfolio.pnl_date == NOW.date()

    def test_the_daily_loss_halt_releases_at_the_next_utc_day_without_a_write(self) -> None:
        """The release used to be produced by the mutation above. It is now
        produced by the derivation, so the halt still lifts at midnight and the
        ledger is not rewritten to lift it.
        """
        portfolio = Portfolio(free_quote=D("10000"))
        portfolio.record_realised_pnl(D("-500"), now=NOW)
        limit = D("5.0")  # threshold -500 against equity 10000

        assert portfolio.daily_loss_exceeded(
            limit_percent=limit, equity=D("10000"), now=NOW, committed=D("0")
        )
        assert not portfolio.daily_loss_exceeded(
            limit_percent=limit, equity=D("10000"), now=NOW + timedelta(hours=13), committed=D("0")
        )

        assert portfolio.realised_pnl == D("-500")
        assert portfolio.pnl_date == NOW.date()

    def test_a_backwards_now_does_not_destroy_or_back_date_the_ledger(self) -> None:
        """The write half. ``now`` can move backwards -- an NTP correction, or an
        out-of-order replay -- and a day comparison that tests *difference*
        rather than *lateness* reads that as a new day: it resets a day of
        booked realised facts and back-dates what survives to a day they did not
        happen on. No exchange statement matches that ledger.

        Accruing into the day already covered is the cheap wrong answer: the
        figure lands on the wrong day, but nothing is lost and the earlier day's
        loss counts against the current cap, so the halt errs early.
        """
        portfolio = Portfolio(free_quote=D("10000"))
        portfolio.record_realised_pnl(D("-450"), now=NOW)

        portfolio.record_realised_pnl(D("-10"), now=NOW - timedelta(hours=13))

        assert portfolio.realised_pnl == D("-460")
        assert portfolio.pnl_date == NOW.date()

    def test_a_backwards_now_does_not_hide_the_days_realised_loss(self) -> None:
        """The read half, and the same defect pointing the other way.

        Deriving on equality answers zero for *any* day that is not the covered
        one, including an earlier one -- so a clock that steps back over
        midnight hides a loss the ledger still holds, and the daily-loss halt
        evaporates while the account is down. Erring late is the direction that
        costs money; this errs early instead, by reporting the recorded figure.
        """
        portfolio = Portfolio(free_quote=D("10000"))
        portfolio.record_realised_pnl(D("-600"), now=NOW)  # 6% of 10000
        earlier = NOW - timedelta(hours=13)
        limit = D("5.0")  # threshold -500 against equity 10000

        assert portfolio.realised_today(earlier) == D("-600")
        assert portfolio.daily_loss_exceeded(
            limit_percent=limit, equity=D("10000"), now=earlier, committed=D("0")
        )

    def test_the_first_accrual_of_a_run_does_not_compare_against_a_missing_day(self) -> None:
        """``pnl_date`` is ``None`` until something is booked, and ``date > None``
        raises ``TypeError`` -- so the null guard in ``_ledger_is_stale`` is what
        makes the comparison legal, not a defensive extra. Without it every run
        would fail on its first realised P&L.
        """
        portfolio = Portfolio(free_quote=D("10000"))
        assert portfolio.pnl_date is None

        portfolio.record_realised_pnl(D("-5"), now=NOW)

        assert portfolio.realised_pnl == D("-5")
        assert portfolio.pnl_date == NOW.date()

    @pytest.mark.parametrize(
        ("amount", "now", "expected", "match"),
        [
            (0.5, NOW + timedelta(hours=13), TypeError, "unsupported operand"),
            (0.5, NOW + timedelta(hours=1), TypeError, "unsupported operand"),
            (0.5, NOW - timedelta(hours=13), TypeError, "unsupported operand"),
            (np.float64(0.5), NOW + timedelta(hours=13), TypeError, "unsupported operand"),
            ("0.5", NOW + timedelta(hours=13), TypeError, "unsupported operand"),
            (D("NaN"), NOW + timedelta(hours=13), ValidationError, "finite number"),
        ],
        ids=[
            "float_rolling",
            "float_same_day",
            "float_backwards_day",
            "numpy_float_rolling",
            "str_rolling",
            "non_finite_rolling",
        ],
    )
    def test_a_failed_accrual_leaves_the_ledger_untouched(
        self, amount: object, now: datetime, expected: type[Exception], match: str
    ) -> None:
        """The roll is a write, and it used to be committed before the accrual
        that can fail -- so a bad amount on the first accrual after midnight
        destroyed the previous day's realised facts and advanced ``pnl_date`` to
        a day nothing had been booked into. That is the same end state commit 1
        closed by the backwards-clock route.

        Both branches of the roll are covered deliberately: only the rolling one
        could half-apply, and a fix that closed it by moving the roll would
        silently change the other. The non-finite row is the discriminating
        case -- ``Money`` rejects it at the *assignment*, independently of the
        float guard on the arithmetic, so a fix that ordered only the
        arithmetic first would still half-apply here.
        """
        portfolio = Portfolio(free_quote=D("10000"))
        portfolio.record_realised_pnl(D("-450"), now=NOW)

        with pytest.raises(expected, match=match):
            # non-Decimal amounts are deliberate: four of the six triggers.
            portfolio.record_realised_pnl(amount, now=now)  # type: ignore[arg-type]

        assert portfolio.realised_pnl == D("-450")
        assert portfolio.pnl_date == NOW.date()

    def test_daily_loss_threshold_is_a_percent_of_equity(self) -> None:
        portfolio = Portfolio(free_quote=D("10000"))
        limit = D("5.0")  # 5% of 10000 == 500

        portfolio.record_realised_pnl(D("-499.99"), now=NOW)
        assert not portfolio.daily_loss_exceeded(
            limit_percent=limit, equity=D("10000"), now=NOW, committed=D("0")
        )

        portfolio.record_realised_pnl(D("-0.01"), now=NOW)
        assert portfolio.daily_loss_exceeded(
            limit_percent=limit, equity=D("10000"), now=NOW, committed=D("0")
        )

    def test_open_position_debits_the_cost_and_records_the_position(self) -> None:
        portfolio = Portfolio(free_quote=D("10000"))
        portfolio.open_position(long_position(quantity="2", entry="150"), cost=D("300"))

        assert portfolio.free_quote == D("9700")
        assert portfolio.has_position(SYMBOL)

    def test_open_position_debits_before_it_inserts(self) -> None:
        """``free_quote`` carries ``ge=0``, so an over-spend raises on the debit.
        Debiting first is what makes that raise leave the ledger untouched --
        inserting first would leave a position whose cost was never accounted
        for, which is a ledger that has already stopped matching the account.
        """
        portfolio = Portfolio(free_quote=D("100"))

        with pytest.raises(ValidationError):
            portfolio.open_position(long_position(), cost=D("500"))

        assert portfolio.free_quote == D("100")  # unchanged
        assert not portfolio.has_position(SYMBOL)  # and nothing was inserted

    def test_close_position_credits_proceeds_and_books_realised_pnl(self) -> None:
        portfolio = Portfolio(free_quote=D("1000"))
        portfolio.open_position(long_position(quantity="2", entry="100"), cost=D("200"))

        pnl = portfolio.close_position(SYMBOL, exit_price=D("110"), now=NOW)

        assert pnl == D("20")  # (110 - 100) * 2
        assert portfolio.free_quote == D("1020")  # 800 + 2 * 110
        assert portfolio.realised_today(NOW) == D("20")
        assert not portfolio.has_position(SYMBOL)

    def test_close_position_nets_the_fee_so_the_ledger_matches_a_statement(self) -> None:
        """The stated reason the ledger holds realised facts only is that it must
        match an exchange statement, and a statement is net of fees.
        """
        portfolio = Portfolio(free_quote=D("1000"))
        portfolio.open_position(long_position(quantity="2", entry="100"), cost=D("200"))

        pnl = portfolio.close_position(SYMBOL, exit_price=D("110"), now=NOW, fee=D("0.5"))

        assert pnl == D("19.5")
        assert portfolio.free_quote == D("1019.5")
        assert portfolio.realised_today(NOW) == D("19.5")

    def test_close_position_on_a_symbol_not_held_is_a_normal_zero(self) -> None:
        portfolio = Portfolio(free_quote=D("1000"))
        assert portfolio.close_position(SYMBOL, exit_price=D("110"), now=NOW) == D("0")
        assert portfolio.free_quote == D("1000")
        assert portfolio.realised_today(NOW) == D("0")

    def test_close_position_rejects_a_naive_datetime(self) -> None:
        """Nothing here reads a clock; every time-dependent method takes ``now``
        and a naive value raises rather than being assumed to be UTC.
        """
        portfolio = Portfolio(free_quote=D("1000"))
        portfolio.open_position(long_position(), cost=D("100"))

        with pytest.raises(ValueError, match="timezone-aware"):
            portfolio.close_position(SYMBOL, exit_price=D("110"), now=datetime(2026, 7, 25, 12, 0))

    @pytest.mark.parametrize(
        ("exit_price", "fee", "now", "expected", "match"),
        [
            (110.0, D("0"), NOW, TypeError, "unsupported operand"),
            (D("110"), 0.5, NOW, TypeError, "unsupported operand"),
            (D("110"), D("2000"), NOW, ValidationError, "greater than or equal to 0"),
            (D("-500"), D("0"), NOW, ValidationError, "greater than or equal to 0"),
            (D("110"), D("0"), NOW.replace(tzinfo=None), ValueError, "timezone-aware"),
        ],
        ids=["float_price", "float_fee", "fee_exceeds_balance", "negative_price", "naive_now"],
    )
    def test_a_failed_close_leaves_the_ledger_untouched(
        self,
        exit_price: Decimal | float,
        fee: Decimal | float,
        now: datetime,
        expected: type[Exception],
        match: str,
    ) -> None:
        """Five ways this method can fail partway through a three-write sequence.
        Reaching any of them is a bug rather than a market state, and a bug that
        removes a position while its proceeds go unaccounted for leaves a ledger
        that has already stopped matching the account -- which is what
        ``open_position``'s ordering discipline exists to prevent, stated there
        and until now obeyed only there.

        The float rows are the money rule working as designed: ``Decimal``
        arithmetic announces a bad crossing by raising. What is fixed is not
        that they raise, but that they raise before anything is written.
        """
        portfolio = Portfolio(free_quote=D("800"), positions={SYMBOL: long_position(quantity="2")})

        with pytest.raises(expected, match=match):
            # float operands are deliberate: two of the five triggers.
            portfolio.close_position(
                SYMBOL,
                exit_price=exit_price,  # type: ignore[arg-type]
                now=now,
                fee=fee,  # type: ignore[arg-type]
            )

        assert SYMBOL in portfolio.positions
        assert portfolio.free_quote == D("800")
        assert portfolio.realised_pnl == D("0")

    def test_free_quote_cannot_go_negative(self) -> None:
        portfolio = Portfolio(free_quote=D("100"))
        with pytest.raises(ValidationError):
            portfolio.free_quote = D("-1")
        with pytest.raises(ValidationError):
            Portfolio(free_quote=D("-1"))

    def test_committed_risk_is_measured_from_the_mark_not_from_the_entry(self) -> None:
        """Mark-to-stop keeps the check at two bases. The entry-to-mark move is
        already reflected on the right-hand side, because equity is marked -- so
        counting it on the left too would overlap by `1 + limit_percent`.
        """
        portfolio = Portfolio(
            free_quote=D("1000"),
            positions={
                SYMBOL: long_position(
                    quantity="2",
                    entry="100",
                    stop_loss=D("90"),
                    protection=ProtectionState.ABSENT_BY_DESIGN,
                )
            },
        )
        # Mark 95: entry-to-stop would be (90-100)*2 = -20; mark-to-stop is
        # (90-95)*2 = -10, and the missing -10 is the entry-to-mark move that
        # equity has already priced in.
        total, uncomputable = portfolio.committed_risk({SYMBOL: D("95")})
        assert total == D("-10")
        assert uncomputable == 0

    def test_committed_risk_prices_off_the_resting_stop_not_the_trail(self) -> None:
        """This assertion was `-3` until now, and is INVERTED rather than
        deleted so the change of mind stays visible.

        It read the trail as "the level actually operative". It is not: nothing
        places or amends an order for a trailing level -- Q-C section 3 fixes
        the legs at three and none is a trailing leg -- so a position whose
        process dies is protected at `stop_loss`, not at the trail. Pricing off
        the trail UNDERSTATED forward risk by 58% here, and the daily-loss check
        would have permitted entries on protection that does not exist.

        Committed risk prices off what RESTS. Overstating while the bot is alive
        is the error this codebase chooses.
        """
        portfolio = Portfolio(
            free_quote=D("1000"),
            positions={
                SYMBOL: long_position(
                    quantity="1",
                    entry="100",
                    stop_loss=D("90"),  # this rests, so this is what binds
                    trailing_stop=D("97"),  # client-side only; no venue counterpart
                    protection=ProtectionState.ABSENT_BY_DESIGN,
                )
            },
        )
        total, _ = portfolio.committed_risk({SYMBOL: D("100")})
        assert total == D("-10")  # (90 - 100) * 1, not (97 - 100) * 1

    def test_a_trailed_position_with_no_resting_stop_is_uncomputable(self) -> None:
        """A trail alone is not protection, so it cannot be priced as though it
        were. The position contributes 0 and is COUNTED, which refuses entries.

        Reachable across runs: `stop_loss.enabled` flipped false then true with a
        position open (Q-C section 5), so the position never carried a requested
        stop while the trail advanced. Counting it would book forward risk for an
        exit that only happens while this process is alive.
        """
        portfolio = Portfolio(
            free_quote=D("1000"),
            positions={
                SYMBOL: long_position(
                    quantity="1",
                    entry="100",
                    stop_loss=None,
                    trailing_stop=D("97"),
                    protection=ProtectionState.ABSENT_BY_DESIGN,
                )
            },
        )
        total, uncomputable = portfolio.committed_risk({SYMBOL: D("100")})
        # The count first: being COUNTED is this test's claim, and contributing
        # zero is the consequence. Asserted the other way round, a mutation that
        # priced the trail would fail on the total and never reach the count.
        assert uncomputable == 1
        assert total == D("0")

    def test_an_absent_by_design_position_with_a_requested_stop_is_priced(self) -> None:
        """CHARACTERISATION OF A KNOWN DEFECT -- Q-C section 7's site 3, finding
        `M5d-011`. This pins what the code does TODAY, not what it should do.

        `ABSENT_BY_DESIGN` asserts that *no protection is expected here*, so a
        non-`None` `stop_loss` contradicts it. The pair is representable because
        `CLAUDE.md` forbids the `Position` `model_validator` that would forbid it
        in M5, and `committed_risk` treats it as TRUSTED: it prices the position
        off a stop whose resting status nothing has established.

        **It is also the ONLY route into the pricing arm**, which is what makes
        this a characterisation rather than an edge case. A *coherent*
        `ABSENT_BY_DESIGN` position has `stop_loss is None`, so `_binding_stop`
        returns `None` and the first clause already counts it uncomputable; and
        `UNKNOWN`, the only other member, is outside `_TRUSTED_PROTECTION`. So
        every position this function prices is in the incoherent state.

        **Closing site 3 INVERTS this test.** The fix needs `ACTIVE` -- a
        `ProtectionState` member that cannot be created before a writer exists --
        so it belongs to the milestone that lands the reconciler. When it does,
        this pairing becomes untrusted and the expected values become
        ``total == 0, uncomputable == 1``. Inverting it then is correct;
        deleting it is not, because the change of behaviour is the thing worth
        recording.

        > **ANNOTATED, and BOTH paragraphs above are now wrong in their
        > particulars while the test itself is untouched and still passes.**
        >
        > *"the ONLY route into the pricing arm"* rested on `UNKNOWN` being
        > *"the only other member"*, which was true of a two-member enum. There
        > are five members now and `ACTIVE` is trusted, so a coherently
        > protected position reaches the pricing arm by the intended route.
        >
        > *"Closing site 3 INVERTS this test"* mis-predicted which change would
        > do it. Site 3 was closed by the `DIVERGED` write plus the whitelist's
        > untrusted default, and that left this incoherent pairing exactly as it
        > was -- `ABSENT_BY_DESIGN` is still trusted, still paired with a
        > non-`None` stop, still priced. **The characterisation stands and the
        > defect it characterises is still open.**
        >
        > The transferable part: a justification resting on a fact established
        > elsewhere -- here, an enum's membership -- goes stale silently when
        > that fact moves, and nothing at the justification's site re-checks it.
        """
        portfolio = Portfolio(
            free_quote=D("1000"),
            positions={
                SYMBOL: long_position(
                    quantity="10",
                    entry="100",
                    stop_loss=D("90"),
                    protection=ProtectionState.ABSENT_BY_DESIGN,
                )
            },
        )
        total, uncomputable = portfolio.committed_risk({SYMBOL: D("100")})
        # The count first, as in the test above: being TRUSTED is the claim, and
        # the priced total is its consequence. Asserted the other way round, a
        # change that stopped trusting the pair would fail on the total and
        # never reach the count that says why.
        assert uncomputable == 0
        assert total == D("-100")  # (90 - 100) * 10, off a stop nothing confirms

    def test_should_exit_still_prefers_the_trail(self) -> None:
        """The asymmetry is deliberate and must stay: `should_exit` asks whether
        to exit NOW and prefers the trail, which is the level a live bot acts on;
        `_binding_stop` asks what happens if the bot STOPS RUNNING.

        Without this test a future edit could "restore consistency" by making
        `should_exit` ignore the trail, and nothing would object -- which would
        break the client-side exit path in the name of the fix above.
        """
        position = long_position(
            quantity="1",
            entry="100",
            stop_loss=D("90"),
            trailing_stop=D("97"),
            protection=ProtectionState.ABSENT_BY_DESIGN,
        )
        # 89 triggers BOTH stops, which is the only state in which a preference
        # is observable. At a price that triggers the trail alone, an edit that
        # dropped the trail would return None and the test would fail on the
        # not-None guard rather than on the preference it exists to pin.
        decision = should_exit(position=position, price=D("89"))
        assert decision is not None
        assert decision.reason is ExitReason.TRAILING_STOP
        assert decision.price == D("97")

    def test_committed_risk_counts_a_position_it_cannot_price(self) -> None:
        """Contributing 0 would tell the caller an unprotected position carries
        no forward risk -- the exact inverse of the truth.
        """
        portfolio = Portfolio(
            free_quote=D("1000"),
            positions={SYMBOL: long_position()},  # no stop of any kind
        )
        total, uncomputable = portfolio.committed_risk({SYMBOL: D("100")})
        assert total == D("0")
        assert uncomputable == 1

    def test_committed_risk_distrusts_a_stop_whose_protection_is_unknown(self) -> None:
        """The D-7 half. A stop level is recorded, but the protection story is
        not established, so the level may not rest at the exchange and pricing
        off it would UNDERSTATE committed risk.

        **Fixture-only today**: nothing in ``src/`` populates ``protection``
        until the reconciler exists, so this does not close D-7 -- it builds the
        signature that will not have to change when it is closed.
        """
        portfolio = Portfolio(
            free_quote=D("1000"),
            positions={
                SYMBOL: long_position(stop_loss=D("90"), protection=ProtectionState.UNKNOWN)
            },
        )
        total, uncomputable = portfolio.committed_risk({SYMBOL: D("100")})
        assert total == D("0")
        assert uncomputable == 1

    def test_an_active_position_is_priced_rather_than_counted_uncomputable(self) -> None:
        """THE ADMISSION, and what it buys. `ACTIVE` is the one state measured
        against the venue rather than assumed -- every requested leg found
        resting, at its trigger, for the quantity, under the list id, nothing
        executed -- so it is the one member allowed to carry the expensive error
        direction that this whitelist otherwise refuses.

        **What it unblocks is TRADING, not a defect.** Left untrusted, a
        correctly protected position counts uncomputable, which refuses every
        entry portfolio-wide: the interlock firing on the healthy path. The
        first position the executor opens would have frozen the portfolio at one
        position, at the highest-risk moment in the project.

        The count is asserted first, as in the tests above: being TRUSTED is the
        claim and the priced total is its consequence, so a change that stopped
        trusting `ACTIVE` fails on the count that says why.
        """
        portfolio = Portfolio(
            free_quote=D("1000"),
            positions={
                SYMBOL: long_position(
                    quantity="10",
                    entry="100",
                    stop_loss=D("90"),
                    protection=ProtectionState.ACTIVE,
                )
            },
        )
        total, uncomputable = portfolio.committed_risk({SYMBOL: D("100")})
        assert uncomputable == 0
        assert total == D("-100")  # (90 - 100) * 10, off a stop the venue confirmed

    def test_membership_says_nothing_about_when_the_protection_was_verified(self) -> None:
        """A CHARACTERISATION OF WHAT THIS COMMIT MAKES LOAD-BEARING, not an
        approval of it.

        The discriminator reads `_TRUSTED_PROTECTION` and does not read
        `last_reconciled_at`. Before `ACTIVE` was admitted that was invisible:
        every reconciler-written state was untrusted, so a stale one and a fresh
        one both counted uncomputable. Now a position classified `ACTIVE` and
        never re-read -- a dropped feed, a budget-skipped pass -- stays trusted
        indefinitely and is priced off a stop that may no longer rest.

        A stamp older than any plausible `max_position_staleness_s` is priced
        here exactly as a fresh one is, and that field HAS NO READER in `src/`.
        The refusal that closes it is a hard precondition of the first dispatch;
        see `docs/NEXT_MILESTONE.md` item 14. This test exists so that closing
        it inverts something rather than passing silently.
        """
        ancient = datetime(2020, 1, 1, tzinfo=timezone.utc)
        position = long_position(
            quantity="10", entry="100", stop_loss=D("90"), protection=ProtectionState.ACTIVE
        )
        position.record_reconciliation(protection=ProtectionState.ACTIVE, at=ancient)
        portfolio = Portfolio(free_quote=D("1000"), positions={SYMBOL: position})

        total, uncomputable = portfolio.committed_risk({SYMBOL: D("100")})

        assert position.last_reconciled_at == ancient
        assert uncomputable == 0  # priced, on protection verified years ago
        assert total == D("-100")

    def test_a_stop_already_above_the_mark_commits_nothing_rather_than_a_credit(self) -> None:
        """The `min(0, ...)` clamp. A long whose stop sits *above* the mark has
        already been breached -- a stale or transient state that `should_exit`
        would act on -- and the arithmetic would otherwise report `+5` of
        committed *profit*, which would offset another position's committed loss
        and quietly raise the daily-loss headroom. Committed risk only ever
        subtracts.
        """
        portfolio = Portfolio(
            free_quote=D("1000"),
            positions={
                SYMBOL: long_position(
                    quantity="1",
                    entry="100",
                    stop_loss=D("105"),  # above the mark below
                    protection=ProtectionState.ABSENT_BY_DESIGN,
                )
            },
        )
        total, _ = portfolio.committed_risk({SYMBOL: D("100")})
        assert total == D("0")  # not +5

    def test_the_daily_limit_counts_committed_risk_beside_realised_loss(self) -> None:
        """An account 4% down realised, holding a position whose stop commits
        another 2%, is not "4% down" for the purposes of a 5% cap.
        """
        portfolio = Portfolio(
            free_quote=D("1000"),
            positions={
                SYMBOL: long_position(
                    quantity="10",
                    entry="100",
                    stop_loss=D("80"),  # commits (80 - 100) * 10 = -200
                    protection=ProtectionState.ABSENT_BY_DESIGN,
                )
            },
        )
        marks = {SYMBOL: D("100")}
        portfolio.record_realised_pnl(D("-400"), now=NOW)  # 20% of a 2000 equity
        limit = D("25.0")  # threshold -500 against equity 2000

        # Realised alone is -400, inside the cap. Realised + committed is -600,
        # which is not -- and the ledger still reads -400.
        assert portfolio.realised_today(NOW) == D("-400")
        committed, _ = portfolio.committed_risk(marks)
        assert committed == D("-200")
        assert portfolio.daily_loss_exceeded(
            limit_percent=limit, equity=D("2000"), now=NOW, committed=committed
        )

    def test_realised_pnl_is_untouched_by_the_committed_term(self) -> None:
        """The committed term lives in the check, never in the ledger -- which is
        what keeps the ledger matching an exchange statement.
        """
        portfolio = Portfolio(
            free_quote=D("1000"),
            positions={
                SYMBOL: long_position(
                    quantity="10",
                    entry="100",
                    stop_loss=D("80"),
                    protection=ProtectionState.ABSENT_BY_DESIGN,
                )
            },
        )
        committed, _ = portfolio.committed_risk({SYMBOL: D("100")})
        portfolio.daily_loss_exceeded(
            limit_percent=D("5.0"), equity=D("2000"), now=NOW, committed=committed
        )
        assert portfolio.realised_pnl == D("0")
        assert portfolio.realised_today(NOW) == D("0")

    def test_cooldown_expires_by_comparison_not_by_sweep(self) -> None:
        portfolio = Portfolio(free_quote=D("1000"))
        portfolio.start_cooldown(SYMBOL, now=NOW, minutes=15)

        assert portfolio.in_cooldown(SYMBOL, NOW + timedelta(minutes=14, seconds=59))
        assert not portfolio.in_cooldown(SYMBOL, NOW + timedelta(minutes=15))
        assert not portfolio.in_cooldown("ETHUSDT", NOW)

    def test_zero_minute_cooldown_records_nothing(self) -> None:
        """`cooldown_minutes: 0` is a supported config and must never block."""
        portfolio = Portfolio(free_quote=D("1000"))
        portfolio.start_cooldown(SYMBOL, now=NOW, minutes=0)
        assert portfolio.cooldown_expiry(SYMBOL) is None
        assert not portfolio.in_cooldown(SYMBOL, NOW)

    def test_naive_datetime_is_rejected(self) -> None:
        """A naive value would be read as local time, moving the UTC day
        boundary by the host's offset."""
        portfolio = Portfolio(free_quote=D("1000"))
        with pytest.raises(ValueError, match="timezone-aware"):
            portfolio.realised_today(datetime(2026, 7, 25, 12, 0))

    def test_naive_datetime_is_rejected_on_the_accrual_path_too(self) -> None:
        """The same rule, pinned independently of the read path.

        Both paths now resolve the UTC day through one helper, so a single edit
        can remove the rejection from both at once -- and the sibling above was
        the suite's only direct hold on it. ``close_position`` reaches this
        guard as well, but only through a position it has already popped and a
        balance it has already credited, so it pins the rule incidentally
        rather than on purpose.
        """
        portfolio = Portfolio(free_quote=D("1000"))
        with pytest.raises(ValueError, match="timezone-aware"):
            portfolio.record_realised_pnl(D("-1"), now=datetime(2026, 7, 25, 12, 0))

    def test_money_fields_reject_a_float_on_assignment(self) -> None:
        """validate_assignment closes the leak plain pydantic models leave open:
        construction is guarded, and so is every later write."""
        portfolio = Portfolio(free_quote=D("1000"))
        with pytest.raises(ValidationError, match="must not be built from a float"):
            portfolio.free_quote = 1000.5  # type: ignore[assignment]


# --------------------------------------------------------------------------
# The limits, each independently, with the clock advanced explicitly.
#
# Reached through `evaluate`, which is the only entry point since M5b widened
# the port: `approve` was deleted rather than demoted, because it could
# approve an entry whose committed risk was unknown.
# --------------------------------------------------------------------------
class TestLimits:
    def _decision(self, manager: RiskManager, portfolio: Portfolio) -> RiskDecision:
        """The limit verdict `evaluate` reached, or fail saying where it stopped."""
        assessment = manager.evaluate(buy(), portfolio=portfolio)
        assert assessment.decision is not None, (
            f"evaluate stopped before the limits, at {assessment.stage}"
        )
        return assessment.decision

    def test_approves_within_every_limit(self) -> None:
        manager, _ = build_manager()
        decision = self._decision(manager, Portfolio(free_quote=D("10000")))
        assert decision.approved
        assert decision.rule is None

    def test_max_open_positions(self) -> None:
        portfolio = Portfolio(
            free_quote=D("1000"),
            positions={
                # A computable, trusted stop on each: without one `evaluate`
                # refuses at COMMITTED_RISK_UNKNOWN before any limit runs, so
                # the state this test used to reach through `approve` is not
                # reachable through the only entry point that remains.
                "ETHUSDT": long_position(
                    symbol="ETHUSDT",
                    stop_loss=D("90"),
                    protection=ProtectionState.ABSENT_BY_DESIGN,
                ),
                "BNBUSDT": long_position(
                    symbol="BNBUSDT",
                    stop_loss=D("90"),
                    protection=ProtectionState.ABSENT_BY_DESIGN,
                ),
            },
        )
        manager, _ = build_manager(
            config=risk_config(max_open_positions=2),
            provider=FakeProvider(
                candles={"ETHUSDT": candle(symbol="ETHUSDT"), "BNBUSDT": candle(symbol="BNBUSDT")}
            ),
            pairs=multi_pairs(SYMBOL, "ETHUSDT", "BNBUSDT"),
        )

        decision = self._decision(manager, portfolio)
        assert not decision.approved
        assert decision.rule is RiskRule.MAX_OPEN_POSITIONS
        assert "2" in decision.reason

    def test_daily_loss_halt_and_its_release_at_the_next_utc_day(self) -> None:
        manager, clock = build_manager(config=risk_config(max_daily_loss_percent="5.0"))
        portfolio = Portfolio(free_quote=D("10000"))
        portfolio.record_realised_pnl(D("-500"), now=NOW)

        halted = self._decision(manager, portfolio)
        assert not halted.approved
        assert halted.rule is RiskRule.DAILY_LOSS_HALT

        # Still the same UTC day 11 hours on: still halted.
        clock.advance(hours=11)
        assert not self._decision(manager, portfolio).approved

        # Past midnight UTC the ledger rolls and trading resumes.
        clock.advance(hours=2)
        assert self._decision(manager, portfolio).approved

    def test_cooldown(self) -> None:
        manager, clock = build_manager(config=risk_config(cooldown_minutes=15))
        portfolio = Portfolio(free_quote=D("10000"))
        portfolio.start_cooldown(SYMBOL, now=NOW, minutes=15)

        blocked = self._decision(manager, portfolio)
        assert not blocked.approved
        assert blocked.rule is RiskRule.COOLDOWN

        clock.advance(minutes=15)
        assert self._decision(manager, portfolio).approved

    def test_already_in_position(self) -> None:
        manager, _ = build_manager()
        # Stopped, for the reason given in test_max_open_positions.
        portfolio = Portfolio(
            free_quote=D("10000"),
            positions={
                SYMBOL: long_position(
                    stop_loss=D("90"), protection=ProtectionState.ABSENT_BY_DESIGN
                )
            },
        )
        decision = self._decision(manager, portfolio)
        assert not decision.approved
        assert decision.rule is RiskRule.ALREADY_IN_POSITION

    def test_unmarkable_position_blocks_rather_than_raising(self) -> None:
        """Equity is unknown, so no limit can be evaluated -- but the path runs
        on every signal, so it refuses instead of raising."""
        manager, _ = build_manager(
            provider=FakeProvider(candles={SYMBOL: None}),
            pairs={SYMBOL: PairContext(timeframe=TIMEFRAME, symbol_info=symbol_info())},
        )
        portfolio = Portfolio(free_quote=D("10000"), positions={SYMBOL: long_position()})
        decision = self._decision(manager, portfolio)
        assert not decision.approved
        assert decision.rule is RiskRule.NO_MARK_PRICE
        assert "no limit can be checked" in decision.reason

    def test_zero_equity(self) -> None:
        manager, _ = build_manager()
        decision = self._decision(manager, Portfolio(free_quote=D("0")))
        assert not decision.approved
        assert decision.rule is RiskRule.NO_EQUITY

    @pytest.mark.parametrize(
        ("rule", "portfolio_factory"),
        [
            (
                RiskRule.DAILY_LOSS_HALT,
                lambda: _with_loss(Portfolio(free_quote=D("10000")), D("-9999")),
            ),
            (
                RiskRule.ALREADY_IN_POSITION,
                lambda: Portfolio(
                    free_quote=D("10000"),
                    positions={
                        SYMBOL: long_position(
                            stop_loss=D("90"), protection=ProtectionState.ABSENT_BY_DESIGN
                        )
                    },
                ),
            ),
            (
                RiskRule.COOLDOWN,
                lambda: _with_cooldown(Portfolio(free_quote=D("10000"))),
            ),
        ],
    )
    def test_every_rejection_names_the_rule_that_fired(
        self, rule: RiskRule, portfolio_factory: Callable[[], Portfolio]
    ) -> None:
        """A refusal an operator cannot act on is the failure RiskDecision
        exists to prevent: the rule and a human-readable reason, always."""
        manager, _ = build_manager()
        decision = self._decision(manager, portfolio_factory())
        assert not decision.approved
        assert decision.rule is rule
        assert decision.reason


class TestThePortsShape:
    """M5b widened the port, and the shape is the safety property.

    ``docs/NEXT_MILESTONE.md`` P2: "when the port widens, no method on it may
    approve an entry whose committed risk is unknown." That holds here by
    construction rather than by a check -- ``size_position`` takes no
    ``Portfolio`` and so has nothing to approve an entry against, leaving
    ``evaluate`` as the only port method that sees one, and it refuses under
    ``COMMITTED_RISK_UNKNOWN`` before any limit is consulted.
    """

    def test_the_port_declares_exactly_the_composed_path_and_sizing(self) -> None:
        assert RiskManagerPort.__abstractmethods__ == frozenset({"evaluate", "size_position"})

    def test_only_evaluate_takes_a_portfolio(self) -> None:
        """The by-construction half. ``size_position`` cannot express the
        violation because it is handed an equity figure, not the account."""
        takes_portfolio = {
            name
            for name in RiskManagerPort.__abstractmethods__
            if "portfolio" in inspect.signature(getattr(RiskManagerPort, name)).parameters
        }
        assert takes_portfolio == {"evaluate"}

    def test_approve_is_deleted_not_demoted(self) -> None:
        """P2 offered three shapes; the ruling took deletion. Keeping the method
        private with the check added was rejected because the check would sit in
        a method nothing calls -- so no test exercising ``evaluate`` could reach
        it, and the duplicated guard would be unobservable rather than merely
        redundant.
        """
        assert not hasattr(RiskManagerPort, "approve")
        assert not hasattr(RiskManager, "approve")


class TestTheIntentSplit:
    """M5b split ``TradeIntent`` so an entry carries a limit and an exit does not.

    Three of these pin arguments that had no test before this commit: the exit
    line's absent fields, the union's non-coercion, and the ``side`` invariants.
    """

    def test_an_entry_limit_below_the_reference_is_refused(self) -> None:
        """The slippage DIRECTION as a property of the type. Slippage on a buy
        may only move the limit up, and this is the one invariant that could
        silently invert -- it is unfakeable independently of whatever bound
        ``max_entry_slippage`` carries in config."""
        with pytest.raises(ValidationError, match="below reference_price"):
            EntryIntent(
                symbol=SYMBOL,
                side=OrderSide.BUY,
                quantity=D("1"),
                reference_price=D("100"),
                entry_limit=D("99.99"),
                levels=entry_levels(entry="99.99"),
            )

    def test_an_entry_intent_requires_its_levels(self) -> None:
        """Required, not optional: the four-way placement branch routes on which
        levels are absent, and "neither enabled" is still a ProtectiveLevels
        with both absent and a basis saying why.

        Asserts the ``missing`` error type, not merely that *something* refused.
        Giving the field a default makes ``_check_invariants`` read
        ``self.levels.symbol`` off ``None``: an ``AttributeError`` raised on the
        way to the check rather than the required-field check firing. Adding a
        ``levels is None`` guard to that validator would convert the crash into
        a clean ``ValidationError`` and a test matching on the message alone
        would stop biting while the field was still optional.
        """
        with pytest.raises(ValidationError) as excinfo:
            EntryIntent(
                symbol=SYMBOL,
                side=OrderSide.BUY,
                quantity=D("1"),
                reference_price=D("100"),
                entry_limit=D("100"),
            )
        assert [(e["type"], e["loc"]) for e in excinfo.value.errors()] == [("missing", ("levels",))]

    @pytest.mark.parametrize("kind", ["entry", "exit"], ids=["entry", "exit"])
    def test_each_intent_pins_its_own_side(self, kind: str) -> None:
        """An entry is a BUY and an exit is a SELL on spot. Locked for both, and
        unpinned until this commit -- an unenforced invariant in a validator
        reads as covered, which is worse than none."""
        with pytest.raises(ValidationError, match="got OrderSide"):
            if kind == "entry":
                EntryIntent(
                    symbol=SYMBOL,
                    side=OrderSide.SELL,
                    quantity=D("1"),
                    reference_price=D("100"),
                    entry_limit=D("100"),
                    levels=entry_levels(),
                )
            else:
                ExitIntent(
                    symbol=SYMBOL,
                    side=OrderSide.BUY,
                    quantity=D("1"),
                    reference_price=D("100"),
                )

    def test_the_assessment_preserves_which_intent_it_was_given(self) -> None:
        """``RiskAssessment.intent`` is a union, and a consumer narrowing it with
        ``isinstance`` depends on the member surviving construction. It does.

        **This is a consequence, not an independent property, and the compound
        that falsifies it is FOUR edits rather than the two first claimed.**
        Measured across a sixteen-cell matrix; exactly one cell coerces, and it
        needs all of: ``from_attributes=True`` on ``_Frozen``, the removal of
        ``ExitIntent``'s ``BUY`` rejection, the union reordered to
        ``ExitIntent | EntryIntent``, **and** ``union_mode="left_to_right"``.
        Drop any one and the member survives.

        The reason is that smart union matches an exact instance first, so
        while an ``EntryIntent`` remains a valid ``EntryIntent`` no config
        change can make it validate as anything else -- structural validation
        and the side check are necessary but nowhere near sufficient. Only
        abandoning smart union *and* putting ``ExitIntent`` first gets an
        ``EntryIntent`` validated against it, at which point every one of
        ``ExitIntent``'s four fields is present on it, and ``entry_limit`` and
        ``levels`` are dropped with no error.

        So the honest statement of what this pins is narrow: it holds as long as
        the value handed over is a valid member of the union, which pydantic
        guarantees structurally. Kept because a consumer narrowing with
        ``isinstance`` depends on it and the cost is three lines -- not because
        a reachable single edit breaks it.
        """
        exit_intent = ExitIntent(
            symbol=SYMBOL, side=OrderSide.SELL, quantity=D("1"), reference_price=D("100")
        )
        entry_intent = EntryIntent(
            symbol=SYMBOL,
            side=OrderSide.BUY,
            quantity=D("1"),
            reference_price=D("100"),
            entry_limit=D("100"),
            levels=entry_levels(),
        )
        for given in (exit_intent, entry_intent):
            assessment = RiskAssessment(
                symbol=SYMBOL, approved=True, reason="ok", stage=None, intent=given
            )
            assert type(assessment.intent) is type(given)


def _with_loss(portfolio: Portfolio, amount: Decimal) -> Portfolio:
    portfolio.record_realised_pnl(amount, now=NOW)
    return portfolio


def _with_cooldown(portfolio: Portfolio) -> Portfolio:
    portfolio.start_cooldown(SYMBOL, now=NOW, minutes=30)
    return portfolio


# --------------------------------------------------------------------------
# The ATR bridge -- warmup must never hand a NaN to rules.py
# --------------------------------------------------------------------------
class TestAtrBridge:
    def atr_config(self, *, period: int = 14, multiplier: str = "2.0") -> RiskConfig:
        return risk_config(
            stop_loss=StopLossConfig(
                type=StopType.ATR, atr_period=period, atr_multiplier=D(multiplier)
            ),
            take_profit=TakeProfitConfig(enabled=False),
        )

    def test_atr_stop_uses_the_computed_atr(self) -> None:
        """A constant 2.00 true range gives ATR 2.0, so a 2x stop sits 4 below
        entry. The ATR value crosses as a float and lands as an exact Decimal.

        Entry is the derived limit 100.10, so the stop is 96.10 -- the ATR
        distance is unchanged at 4.00 and it is the reference that moved."""
        manager, _ = build_manager(
            config=self.atr_config(),
            provider=FakeProvider(frames={SYMBOL: ohlcv(50)}, candles={SYMBOL: candle()}),
        )
        assessment = manager.evaluate(buy("100.00"), portfolio=Portfolio(free_quote=D("10000")))

        assert assessment.approved
        assert assessment.levels is not None
        assert assessment.levels.stop_loss == D("96.10")
        assert assessment.levels.stop_distance == D("4.00")

    def test_warmup_refuses_without_raising(self) -> None:
        """ATR needs period + 1 bars; rules.py raises on a non-finite ATR, so
        the bridge must gate rather than pass a NaN across."""
        manager, _ = build_manager(
            config=self.atr_config(period=14),
            provider=FakeProvider(frames={SYMBOL: ohlcv(14)}, candles={SYMBOL: candle()}),
        )
        assessment = manager.evaluate(buy(), portfolio=Portfolio(free_quote=D("10000")))

        assert not assessment.approved
        assert "atr" in assessment.reason.lower()
        # It got past the limits: this is a data-readiness refusal, not a limit.
        assert assessment.decision is not None
        assert assessment.decision.approved
        assert assessment.levels is None

    def test_one_more_bar_clears_warmup(self) -> None:
        manager, _ = build_manager(
            config=self.atr_config(period=14),
            provider=FakeProvider(frames={SYMBOL: ohlcv(15)}, candles={SYMBOL: candle()}),
        )
        assert manager.evaluate(buy(), portfolio=Portfolio(free_quote=D("10000"))).approved

    def test_a_gap_after_warmup_is_caught_by_the_finiteness_check(self) -> None:
        """Bar count alone is not sufficient: the indicator re-masks NaN inputs
        after the seed, so one bad tick yields a NaN long past warmup.

        The NaN goes on the final bar's ``high``, which enters that bar's own
        true range. A NaN *close* would not do it -- true range compares against
        the *previous* close, so a bad close only poisons the following bar.
        """
        frame = ohlcv(50)
        frame.iloc[-1, frame.columns.get_loc("high")] = np.nan
        manager, _ = build_manager(
            config=self.atr_config(),
            provider=FakeProvider(frames={SYMBOL: frame}, candles={SYMBOL: candle()}),
        )
        assessment = manager.evaluate(buy(), portfolio=Portfolio(free_quote=D("10000")))

        assert not assessment.approved
        assert "atr" in assessment.reason.lower()

    def test_a_percent_stop_never_inherits_the_atr_warmup_gate(self) -> None:
        """No ATR is needed, so an empty buffer must not block the entry."""
        manager, _ = build_manager(
            provider=FakeProvider(frames={SYMBOL: ohlcv(0)}, candles={SYMBOL: candle()})
        )
        assert manager.evaluate(buy(), portfolio=Portfolio(free_quote=D("10000"))).approved


# --------------------------------------------------------------------------
# A None stop: disabled (intended) vs sub-tick (transient)
# --------------------------------------------------------------------------
class TestNoPlaceableStop:
    @pytest.mark.parametrize(
        "method",
        [
            PositionSizingMethod.FIXED_FRACTION,
            PositionSizingMethod.FIXED_AMOUNT,
            PositionSizingMethod.RISK_PER_TRADE,
        ],
    )
    def test_sub_tick_stop_skips_the_entry_for_every_sizing_method(
        self, method: PositionSizingMethod
    ) -> None:
        """A 0.1% stop on a 1.00 tick collapses onto entry. The operator asked
        for a stop, so no method enters without one -- and this is also what
        keeps a None stop away from the sizer's contract check, which raises."""
        manager, _ = build_manager(
            config=risk_config(
                method=method,
                stop_loss=StopLossConfig(percent=D("0.1")),
                take_profit=TakeProfitConfig(enabled=False),
            ),
            pairs={
                SYMBOL: PairContext(timeframe=TIMEFRAME, symbol_info=symbol_info(price_tick="1.00"))
            },
        )
        assessment = manager.evaluate(buy("100"), portfolio=Portfolio(free_quote=D("10000")))

        assert not assessment.approved
        assert "not entering unprotected" in assessment.reason
        assert assessment.levels is not None
        assert assessment.levels.stop_loss is None
        assert assessment.sizing is None  # refused before sizing

    @pytest.mark.parametrize(
        "method",
        [PositionSizingMethod.FIXED_FRACTION, PositionSizingMethod.FIXED_AMOUNT],
    )
    def test_a_disabled_stop_is_an_instruction_and_is_honoured(
        self, method: PositionSizingMethod
    ) -> None:
        """Stops off is the operator's explicit choice, not a transient state,
        so the entry proceeds unprotected.

        Both protective levels are disabled here because a take-profit with no
        stop is now refused at config load as a payoff-shape judgement. The
        neither-enabled shape is the one that stays reachable -- deliberately,
        so a strategy that owns its exits via `SignalAction.CLOSE` keeps
        working -- and it is the shape this test was always really about.
        """
        manager, _ = build_manager(
            config=risk_config(
                method=method,
                stop_loss=StopLossConfig(enabled=False),
                take_profit=TakeProfitConfig(enabled=False),
            )
        )
        assessment = manager.evaluate(buy(), portfolio=Portfolio(free_quote=D("10000")))

        assert assessment.approved
        assert assessment.levels is not None
        assert assessment.levels.stop_loss is None
        assert assessment.levels.take_profit is None

    def test_risk_per_trade_with_stops_disabled_is_rejected_at_config_load(self) -> None:
        """The combination never reaches the manager: it fails fast at startup,
        which is why the sizer's raise stays a contract check rather than a
        condition the live path has to handle."""
        with pytest.raises(ValidationError, match="risk_per_trade"):
            risk_config(
                method=PositionSizingMethod.RISK_PER_TRADE,
                stop_loss=StopLossConfig(enabled=False),
                take_profit=TakeProfitConfig(enabled=False),
            )


# --------------------------------------------------------------------------
# evaluate: preconditions, sizing refusals, affordability, exits
# --------------------------------------------------------------------------
class TestStaleness:
    """The ledger's currency, checked before anything is computed from it."""

    @staticmethod
    def _manager_and_signal() -> tuple[RiskManager, Signal]:
        pairs = multi_pairs(SYMBOL, "ETHUSDT")
        manager, _ = build_manager(
            provider=FakeProvider(candles={SYMBOL: candle(), "ETHUSDT": candle(symbol="ETHUSDT")}),
            pairs=pairs,
        )
        return manager, buy()

    def test_an_unstamped_position_is_maximally_stale(self) -> None:
        """`None` means never COMPLETELY reconciled, and it refuses.

        A separate branch rather than a sentinel folded into the comparison --
        `None` has no subtraction -- which is also what keeps a mutation of this
        half attributable to it rather than to the arithmetic.

        The position is `ABSENT_BY_DESIGN` with a stop so it is trusted and
        priced, and therefore cannot reach `COMMITTED_RISK_UNKNOWN`: this test
        must fail for staleness or not at all.
        """
        manager, signal = self._manager_and_signal()
        portfolio = Portfolio(
            free_quote=D("10000"),
            positions={
                "ETHUSDT": long_position(
                    symbol="ETHUSDT",
                    stop_loss=D("90"),
                    protection=ProtectionState.ABSENT_BY_DESIGN,
                    last_reconciled_at=None,
                )
            },
        )

        assessment = manager.evaluate(signal, portfolio=portfolio)

        assert not assessment.approved
        assert assessment.stage is RefusalStage.POSITION_STALE

    def test_a_freshly_reconciled_position_is_not_refused(self) -> None:
        """The other direction. Without this, a guard that refused everything
        would satisfy every test above.

        DECLARED ABSTENTION: this fixture cannot express a mutation of the
        `None` branch, because its stamp is set. That is structural rather than
        an oversight -- the two halves are separate code and are separately
        pinned.
        """
        manager, signal = self._manager_and_signal()
        portfolio = Portfolio(
            free_quote=D("10000"),
            positions={
                "ETHUSDT": long_position(
                    symbol="ETHUSDT",
                    stop_loss=D("90"),
                    protection=ProtectionState.ABSENT_BY_DESIGN,
                    last_reconciled_at=NOW - timedelta(seconds=1),
                )
            },
        )

        assessment = manager.evaluate(signal, portfolio=portfolio)

        assert assessment.stage is not RefusalStage.POSITION_STALE

    def test_staleness_refuses_ahead_of_committed_risk_unknown(self) -> None:
        """THE ADJACENCY, on an input the pass really produces.

        A position stamped at some point, later found to have an absent leg --
        `record_partial_reconciliation` writes `UNKNOWN` and LEAVES THE EXISTING
        STAMP, which `test_models.py` pins -- and then aged past the bound. It
        trips both guards: stale by the stamp, uncomputable by `UNKNOWN` being
        outside the trusted set.

        Staleness wins, and the ordering is the ruling: this names the CAUSE
        where committed-risk-unknown names the CONSEQUENCE, and an operator
        reading "the ledger is not current" can act where one reading
        "committed risk is unknown" must work backwards to the same place.
        """
        manager, signal = self._manager_and_signal()
        position = long_position(
            symbol="ETHUSDT",
            stop_loss=D("90"),
            protection=ProtectionState.ACTIVE,
            last_reconciled_at=NOW - timedelta(hours=1),
        )
        position.record_partial_reconciliation(protection=ProtectionState.UNKNOWN)
        portfolio = Portfolio(free_quote=D("10000"), positions={"ETHUSDT": position})

        # Both conditions hold, which is what makes this an ordering test.
        assert position.last_reconciled_at == NOW - timedelta(hours=1)
        assert portfolio.committed_risk({"ETHUSDT": D("100")})[1] == 1

        assessment = manager.evaluate(signal, portfolio=portfolio)

        assert assessment.stage is RefusalStage.POSITION_STALE

    def test_the_guard_is_not_gated_on_stop_loss_enabled(self) -> None:
        """THE ONE BEHAVIOUR CHANGE IN THIS COMMIT, pinned rather than left to
        the docstring.

        `COMMITTED_RISK_UNKNOWN` is gated on `stop_loss.enabled` because that
        opt-out is about COMMITTED RISK -- the operator has declared they own
        their exits. Staleness is about whether `positions`, `position_count`
        and `has_position` describe reality, and a `CLOSE`-owning operator
        still needs `has_position` correct or a `BUY` pyramids onto a position
        that closed at the venue.

        The change is narrow: a stop-disabled position classifies
        `ABSENT_BY_DESIGN` and is stamped on the first pass, so this fires only
        once the pass STOPS RUNNING -- and an operator who opted out of
        protective orders is the least equipped to notice that unaided.
        """
        # Both disabled, because the config layer permits nothing else: stops
        # off implies everything off, since a take-profit or a trailing stop
        # without a stop is refused at load. So this is the ONLY stop-disabled
        # configuration that exists, and it is the whole surface of the change.
        pairs = multi_pairs(SYMBOL, "ETHUSDT")
        manager, _ = build_manager(
            config=risk_config(
                stop_loss=StopLossConfig(enabled=False),
                take_profit=TakeProfitConfig(enabled=False),
            ),
            provider=FakeProvider(candles={SYMBOL: candle(), "ETHUSDT": candle(symbol="ETHUSDT")}),
            pairs=pairs,
        )
        portfolio = Portfolio(
            free_quote=D("10000"),
            positions={
                "ETHUSDT": long_position(
                    symbol="ETHUSDT",
                    protection=ProtectionState.ABSENT_BY_DESIGN,
                    last_reconciled_at=None,
                )
            },
        )

        assessment = manager.evaluate(buy(), portfolio=portfolio)

        assert assessment.stage is RefusalStage.POSITION_STALE


class TestEvaluate:
    def test_unknown_pair_is_refused(self) -> None:
        manager, _ = build_manager()
        assessment = manager.evaluate(
            buy(symbol="DOGEUSDT"), portfolio=Portfolio(free_quote=D("10000"))
        )
        assert not assessment.approved
        assert "DOGEUSDT" in assessment.reason

    @pytest.mark.parametrize(
        ("stop_loss_level", "realised", "expected_committed"),
        [(D("80"), D("-400"), D("-200")), (None, D("-600"), D("0"))],
        ids=["committed_pushes_it_over", "committed_is_zero"],
    )
    def test_the_daily_loss_message_is_checkable_against_its_own_predicate(
        self, stop_loss_level: Decimal | None, realised: Decimal, expected_committed: Decimal
    ) -> None:
        """An operator doing the arithmetic from the message alone must reach the
        verdict the predicate reached. The shipped message named realised P&L
        only, while the predicate has added committed risk since `0029f61`, so
        it asserted that -400 breached 25% of 2000 -- which is false, and is the
        failure `RiskDecision` exists to prevent.

        The committed term is named even when it is zero. The predicate always
        includes it, so a message that named it conditionally would teach that
        it is conditional; and "committed risk 0" distinguishes "realised alone
        breached" from "the committed term pushed it over", which is the whole
        point. The log schema's absent-not-null rule governs structured
        ``extra=`` fields a consumer parses by key, not prose a human reads,
        where an omitted term is invisible rather than absent.
        """
        position = long_position(
            quantity="10",
            entry="100",
            stop_loss=stop_loss_level,
            protection=ProtectionState.ABSENT_BY_DESIGN,
        )
        portfolio = Portfolio(
            free_quote=D("1000"),
            positions={"ETHUSDT": position.model_copy(update={"symbol": "ETHUSDT"})},
        )
        portfolio.record_realised_pnl(realised, now=NOW)
        manager, _ = build_manager(
            # Stops off so the `committed_is_zero` case reaches the limits: with
            # them on, a position lacking a stop refuses at COMMITTED_RISK_UNKNOWN
            # before any limit is consulted. Take-profit follows, because a
            # take-profit with no stop is refused at config load.
            config=risk_config(
                max_daily_loss_percent="25.0",
                stop_loss=StopLossConfig(enabled=False),
                take_profit=TakeProfitConfig(enabled=False),
            ),
            provider=FakeProvider(candles={SYMBOL: candle(), "ETHUSDT": candle(symbol="ETHUSDT")}),
            pairs=multi_pairs(SYMBOL, "ETHUSDT"),
        )

        assessment = manager.evaluate(buy(), portfolio=portfolio)

        assert assessment.decision is not None
        assert assessment.decision.rule is RiskRule.DAILY_LOSS_HALT
        reason = assessment.decision.reason
        # equity is 1000 free + 10 * 100 mark = 2000; the cap is 25% of that.
        equity, threshold = D("2000"), D("-500")
        assert f"realised {realised}" in reason
        assert f"committed risk {expected_committed}" in reason
        assert f"is {realised + expected_committed}" in reason
        assert f"25.0% of equity {equity}" in reason
        # The message's own arithmetic reaches the predicate's verdict...
        assert realised + expected_committed <= threshold
        # ...and on the first case realised alone would not have, so the test
        # cannot degenerate into one the old message would have got right.
        assert (realised <= threshold) is (expected_committed == 0)

    def test_committed_risk_is_computed_once_per_evaluation(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """`evaluate` needs the uncomputable *count* before the limits and the
        *sum* inside them, and it used to obtain each from its own pass over
        every open position -- each discarding the half the other needed. The
        module docstring claims the opposite economy for the adjacent quantity:
        "evaluate computes equity once and reuses it rather than paying for it
        twice."

        Asserted on the call count rather than on the message, deliberately: the
        cheaper fix -- leave the double computation and build the message from a
        third pass -- produces a byte-identical message, so only this can tell
        the two apart.
        """
        calls: list[object] = []
        original = Portfolio.committed_risk

        def counting(self: Portfolio, marks: object) -> object:
            calls.append(marks)
            return original(self, marks)  # type: ignore[arg-type]

        monkeypatch.setattr(Portfolio, "committed_risk", counting)

        portfolio = Portfolio(
            free_quote=D("10000"),
            positions={
                "ETHUSDT": long_position(
                    symbol="ETHUSDT",
                    stop_loss=D("90"),
                    protection=ProtectionState.ABSENT_BY_DESIGN,
                )
            },
        )
        manager, _ = build_manager(
            provider=FakeProvider(candles={SYMBOL: candle(), "ETHUSDT": candle(symbol="ETHUSDT")}),
            pairs=multi_pairs(SYMBOL, "ETHUSDT"),
        )

        assessment = manager.evaluate(buy(), portfolio=portfolio)

        assert assessment.approved
        assert len(calls) == 1

    def test_a_signal_without_a_price_is_refused(self) -> None:
        """Every level and size derives from it, and Signal.price is optional."""
        manager, _ = build_manager()
        signal = Signal(symbol=SYMBOL, action=SignalAction.BUY, timestamp=NOW)
        assessment = manager.evaluate(signal, portfolio=Portfolio(free_quote=D("10000")))
        assert not assessment.approved
        assert "reference price" in assessment.reason

    def test_sell_is_unreachable_on_spot(self) -> None:
        manager, _ = build_manager()
        signal = Signal(symbol=SYMBOL, action=SignalAction.SELL, price=D("100"), timestamp=NOW)
        assessment = manager.evaluate(signal, portfolio=Portfolio(free_quote=D("10000")))
        assert not assessment.approved
        assert "short" in assessment.reason

    def test_too_small_to_trade_carries_the_sizing_reason(self) -> None:
        """A tiny account is a routine outcome, not an error -- and the refusal
        is the sizer's own explanation, not a paraphrase."""
        manager, _ = build_manager(
            pairs={
                SYMBOL: PairContext(
                    timeframe=TIMEFRAME, symbol_info=symbol_info(min_notional="5000")
                )
            }
        )
        assessment = manager.evaluate(buy(), portfolio=Portfolio(free_quote=D("500")))

        assert not assessment.approved
        assert assessment.sizing is not None
        assert not assessment.sizing.is_tradeable
        assert assessment.reason == assessment.sizing.reason
        assert "min_notional" in assessment.reason

    def test_an_unaffordable_order_is_refused(self) -> None:
        """Equity is total value; free balance is what can be spent. The sizer
        documents that confirming the difference is the caller's job.

        Equity here is 10050 -- almost all of it already deployed in ETHUSDT --
        so the fixed 100-quote order sizes cleanly and is still unaffordable.
        """
        manager, _ = build_manager(
            config=risk_config(method=PositionSizingMethod.FIXED_AMOUNT),
            provider=FakeProvider(candles={"ETHUSDT": candle(symbol="ETHUSDT")}),
            pairs=multi_pairs(SYMBOL, "ETHUSDT"),
        )
        portfolio = Portfolio(
            free_quote=D("50"),
            positions={
                "ETHUSDT": long_position(
                    symbol="ETHUSDT",
                    quantity="100",
                    entry="100",
                    stop_loss=D("99"),
                    protection=ProtectionState.ABSENT_BY_DESIGN,
                )
            },
        )
        assessment = manager.evaluate(buy(), portfolio=portfolio)

        assert not assessment.approved
        assert "is free" in assessment.reason
        assert assessment.sizing is not None
        assert assessment.sizing.is_tradeable  # sizing succeeded; the balance did not

    def test_close_produces_an_exit_intent_bypassing_the_limits(self) -> None:
        """An exit is not a new risk. A limit that could trap an open position
        would be a risk rule that creates risk."""
        manager, _ = build_manager(config=risk_config(max_open_positions=1))
        portfolio = Portfolio(free_quote=D("0"), positions={SYMBOL: long_position(quantity="0.75")})
        portfolio.start_cooldown(SYMBOL, now=NOW, minutes=60)
        portfolio.record_realised_pnl(D("-99999"), now=NOW)

        signal = Signal(symbol=SYMBOL, action=SignalAction.CLOSE, price=D("123.45"), timestamp=NOW)
        assessment = manager.evaluate(signal, portfolio=portfolio)

        assert assessment.approved
        assert assessment.intent is not None
        assert assessment.intent.side is OrderSide.SELL
        assert assessment.intent.quantity == D("0.75")
        assert not hasattr(assessment.intent, "levels")

    def test_close_with_nothing_open_is_refused(self) -> None:
        manager, _ = build_manager()
        signal = Signal(symbol=SYMBOL, action=SignalAction.CLOSE, price=D("100"), timestamp=NOW)
        assessment = manager.evaluate(signal, portfolio=Portfolio(free_quote=D("1000")))
        assert not assessment.approved
        assert "nothing to close" in assessment.reason

    def test_an_approval_reports_no_stage(self) -> None:
        """The approval half of the stage invariant, through the real path.

        The log-schema test asserting `"stage" not in fields` sits downstream of
        IntentLogger's early return, which never reads `stage` -- it passes
        whatever the domain does. This one goes through evaluate.

        Pins evaluate's *behaviour*. The validator's raise is a separate claim
        with its own test in TestMoneyGuard; neither implies the other.
        """
        manager, _ = build_manager()
        assessment = manager.evaluate(buy("100.00"), portfolio=Portfolio(free_quote=D("10000")))

        assert assessment.approved
        assert assessment.stage is None


# --------------------------------------------------------------------------
# Exits: the pure predicate, driven with a deliberate price
# --------------------------------------------------------------------------
class TestExits:
    def test_check_exit_uses_the_bar_close_not_its_low(self) -> None:
        """The bot reacts at bar close and fills near it. Triggering on the low
        would claim a fill at a price that has already gone."""
        manager, _ = build_manager()
        position = long_position(stop_loss=D("98"))

        # Low pierces the stop but the bar closed above it: no exit yet.
        pierced = Candle(
            symbol=SYMBOL,
            timeframe=TIMEFRAME,
            open_time=NOW,
            close_time=NOW,
            open=D("100"),
            high=D("100"),
            low=D("97"),
            close=D("99"),
            volume=D("1"),
        )
        assert manager.check_exit(position, pierced) is None

        assert manager.check_exit(position, candle("97.5")) is not None

    def test_a_stop_beats_the_take_profit_on_one_bar(self) -> None:
        manager, _ = build_manager()
        position = long_position(stop_loss=D("98"), take_profit=D("104"))
        decision = manager.check_exit(position, candle("97"))
        assert decision is not None
        assert decision.reason is ExitReason.STOP_LOSS
        assert decision.price == D("98")

    def test_advance_trailing_stop_stores_the_new_state(self) -> None:
        manager, _ = build_manager(
            config=risk_config(
                trailing_stop=TrailingStopConfig(
                    enabled=True, activation_percent=D("1.0"), trail_percent=D("1.0")
                )
            )
        )
        position = long_position(entry="100")

        update = manager.advance_trailing_stop(position, candle("110"))
        assert update is not None
        assert update.activated
        assert position.highest_price == D("110")
        assert position.trailing_stop == D("108.90")

        # A lower close cannot drag the stop back down.
        manager.advance_trailing_stop(position, candle("105"))
        assert position.highest_price == D("110")
        assert position.trailing_stop == D("108.90")

    def test_trailing_disabled_returns_none_and_touches_nothing(self) -> None:
        manager, _ = build_manager()
        position = long_position()
        assert manager.advance_trailing_stop(position, candle("110")) is None
        assert position.trailing_stop is None
        assert position.highest_price is None


# --------------------------------------------------------------------------
# M1 + M2 + M3 composed, end to end
# --------------------------------------------------------------------------
class TestComposedPath:
    def test_realised_risk_at_the_stop_equals_the_configured_budget(self) -> None:
        """The end-to-end invariant the whole milestone exists to produce:
        quantity * realised stop distance <= equity * risk_per_trade.

        Realised, not configured: the stop that matters is the one after
        directional rounding, which is why ProtectiveLevels carries the distance
        rather than letting sizing recompute it.
        """
        config = risk_config(method=PositionSizingMethod.RISK_PER_TRADE)
        manager, _ = build_manager(config=config)
        portfolio = Portfolio(free_quote=D("10000"))

        assessment = manager.evaluate(buy("100.00"), portfolio=portfolio)

        assert assessment.approved
        assert assessment.intent is not None
        assert assessment.levels is not None
        assert assessment.levels.stop_distance is not None

        budget = D("10000") * config.position_sizing.risk_per_trade
        realised = assessment.intent.quantity * assessment.levels.stop_distance
        assert realised == budget == D("100")
        assert assessment.intent.quantity == D("50")
        # 2% below the derived limit 100.10, not below the close.
        assert assessment.levels.stop_loss == D("98.10")

    def test_an_awkward_tick_keeps_realised_risk_inside_the_budget(self) -> None:
        """On a tick that does not divide the stop distance the stop rounds
        *toward entry*, so the realised risk can only come in under budget --
        never over it."""
        config = risk_config(method=PositionSizingMethod.RISK_PER_TRADE)
        manager, _ = build_manager(
            config=config,
            pairs={
                SYMBOL: PairContext(timeframe=TIMEFRAME, symbol_info=symbol_info(price_tick="0.13"))
            },
        )
        assessment = manager.evaluate(buy("100"), portfolio=Portfolio(free_quote=D("10000")))

        assert assessment.approved
        assert assessment.intent is not None
        assert assessment.levels is not None
        assert assessment.levels.stop_loss == D("98.15")  # rounded up, toward entry
        assert assessment.levels.stop_distance is not None

        budget = D("10000") * config.position_sizing.risk_per_trade
        realised = assessment.intent.quantity * assessment.levels.stop_distance
        assert realised <= budget

    def test_the_levels_and_the_sizing_are_priced_at_the_limit_not_the_close(self) -> None:
        """Q-C section 4: the limit is the reference for both protective levels
        and sizing. Sizing off the close while the levels price off the limit
        would make the realised entry-to-stop distance differ from the one the
        quantity was derived from -- realised risk quietly exceeding configured.

        The two assertions before the equality are the point. Reverting the
        levels to the close raises ``ValidationError`` inside ``EntryIntent``,
        so a test that only checked ``levels.entry_price == entry_limit`` would
        be caught by the type's own validator rather than by its own claim.
        Pinning that the limit has actually MOVED off the close is what makes
        the equality mean something.
        """
        manager, _ = build_manager(config=risk_config(method=PositionSizingMethod.RISK_PER_TRADE))
        assessment = manager.evaluate(buy("100.00"), portfolio=Portfolio(free_quote=D("10000")))

        assert assessment.approved
        assert assessment.intent is not None
        assert assessment.levels is not None
        assert isinstance(assessment.intent, EntryIntent)
        # Pre-assertion: the limit is genuinely a different number.
        assert assessment.intent.entry_limit == D("100.10")
        assert assessment.intent.entry_limit != assessment.intent.reference_price
        # ...and both consumers are priced at it, not at the close.
        assert assessment.levels.entry_price == assessment.intent.entry_limit
        assert assessment.sizing is not None
        assert f"at {assessment.intent.entry_limit}" in assessment.sizing.reason

    def test_affordability_is_checked_against_the_limit_not_the_close(self) -> None:
        """The order is dispatched at the limit, so the limit is what it costs.

        Free quote sits strictly BETWEEN the two costs: 0.999 units costs 99.9
        at the close and 99.9999 at the limit, and 99.95 is free. Checking
        against the close would approve an entry the account cannot pay for.

        Equity is raised by an ETHUSDT position rather than by free quote,
        because equity and free quote are the same number in a cash-only
        portfolio -- lowering free quote would shrink the size along with it and
        the knife edge would never be reached. Its stop is trusted so the case
        refuses on affordability rather than on committed risk one guard
        earlier, and ``fixed_amount`` sizing keeps the quantity independent of
        the equity that position adds.
        """
        manager, _ = build_manager(
            config=risk_config(method=PositionSizingMethod.FIXED_AMOUNT),
            provider=FakeProvider(
                frames={SYMBOL: ohlcv(50)},
                candles={SYMBOL: candle(), "ETHUSDT": candle(symbol="ETHUSDT")},
            ),
            pairs=multi_pairs(SYMBOL, "ETHUSDT"),
        )
        portfolio = Portfolio(
            free_quote=D("99.95"),
            positions={
                "ETHUSDT": long_position(
                    symbol="ETHUSDT",
                    quantity="100",
                    entry="100",
                    stop_loss=D("99"),
                    protection=ProtectionState.ABSENT_BY_DESIGN,
                )
            },
        )

        assessment = manager.evaluate(buy("100.00"), portfolio=portfolio)

        assert not assessment.approved
        assert assessment.stage is RefusalStage.UNAFFORDABLE
        # The message names the limit, not the close: 0.999 * 100.10.
        assert "0.999 at 100.10 costs 99.99990" in assessment.reason

    def test_the_position_cap_binds_before_the_sizing_method(self) -> None:
        config = risk_config(
            method=PositionSizingMethod.RISK_PER_TRADE, max_position_size_percent="20"
        )
        manager, _ = build_manager(config=config)
        assessment = manager.evaluate(buy("100.00"), portfolio=Portfolio(free_quote=D("10000")))

        assert assessment.approved
        assert assessment.intent is not None
        # 20% of 10000 equity is a 2000 notional, and the notional is measured
        # at the price the order is sent at: 2000 / 100.10 == 19.980 units,
        # below the method's own 50. Measured at the close it would be 20, whose
        # notional at the limit is 2002 -- over the cap the test is about.
        assert assessment.intent.quantity == D("19.980")
        assert assessment.sizing is not None
        assert "capped" in assessment.sizing.reason


# --------------------------------------------------------------------------
# Structural: no result can be built from a float
# --------------------------------------------------------------------------
class TestMoneyGuard:
    def test_trade_intent_rejects_a_float_quantity(self) -> None:
        with pytest.raises(ValidationError, match="must not be built from a float"):
            EntryIntent(
                symbol=SYMBOL,
                side=OrderSide.BUY,
                quantity=1.5,  # type: ignore[arg-type]
                reference_price=D("100"),
                entry_limit=D("100"),
                levels=entry_levels(),
            )

    def test_trade_intent_rejects_a_numpy_float(self) -> None:
        """numpy.float64 is what DataFrame.iloc hands back -- the realistic leak
        path, and a float subclass, so the same guard catches it."""
        with pytest.raises(ValidationError, match="must not be built from a float"):
            EntryIntent(
                symbol=SYMBOL,
                side=OrderSide.BUY,
                quantity=np.float64(1.5),  # type: ignore[arg-type]
                reference_price=D("100"),
                entry_limit=D("100"),
                levels=entry_levels(),
            )

    @pytest.mark.parametrize("kind", ["entry", "exit"], ids=["entry", "exit"])
    def test_an_intent_must_carry_a_positive_quantity(self, kind: str) -> None:
        """'Do not trade' is an assessment with no intent, never a zero-size one.

        Locked for BOTH types, so pinned on both: the rule is not a property of
        the entry shape."""
        with pytest.raises(ValidationError, match="positive quantity"):
            if kind == "entry":
                EntryIntent(
                    symbol=SYMBOL,
                    side=OrderSide.BUY,
                    quantity=D("0"),
                    reference_price=D("100"),
                    entry_limit=D("100"),
                    levels=entry_levels(),
                )
            else:
                ExitIntent(
                    symbol=SYMBOL,
                    side=OrderSide.SELL,
                    quantity=D("0"),
                    reference_price=D("100"),
                )

    def test_levels_must_match_the_intent_they_protect(self) -> None:
        manager, _ = build_manager()
        assessment = manager.evaluate(buy("100.00"), portfolio=Portfolio(free_quote=D("10000")))
        assert assessment.intent is not None
        assert assessment.intent.levels is not None

        with pytest.raises(ValidationError, match="priced at"):
            EntryIntent(
                symbol=SYMBOL,
                side=OrderSide.BUY,
                quantity=D("1"),
                reference_price=D("999"),
                entry_limit=D("999"),
                levels=assessment.intent.levels,
            )

    def test_a_risk_decision_refusal_must_name_a_rule(self) -> None:
        with pytest.raises(ValidationError, match="must name the rule"):
            RiskDecision(symbol=SYMBOL, approved=False, reason="because")

    def test_a_risk_decision_approval_must_not_name_a_rule(self) -> None:
        with pytest.raises(ValidationError, match="must name the rule"):
            RiskDecision(symbol=SYMBOL, approved=True, reason="fine", rule=RiskRule.COOLDOWN)

    def test_a_risk_assessment_stage_must_agree_with_its_verdict(self) -> None:
        """Both directions of the invariant mirroring `rule` two tests above --
        and the two places RiskAssessment cannot mirror RiskDecision's shape.

        `stage` is **required**, so the refusal direction passes ``None``
        explicitly: omitting it raises pydantic's own ``missing`` and never
        reaches this validator, where `rule`'s default of ``None`` lets the
        sibling above omit it.

        The approval direction needs a real intent, because `_check_invariants`
        binds `intent` to `approved` *first* -- without one it refuses for the
        wrong reason and this test would pass on the wrong error.
        """
        with pytest.raises(ValidationError, match="must name the stage"):
            RiskAssessment(symbol=SYMBOL, approved=False, reason="because", stage=None)

        with pytest.raises(ValidationError, match="must name the stage"):
            RiskAssessment(
                symbol=SYMBOL,
                approved=True,
                reason="fine",
                stage=RefusalStage.LIMIT_REFUSED,
                intent=ExitIntent(
                    symbol=SYMBOL, side=OrderSide.SELL, quantity=D("1"), reference_price=D("100")
                ),
            )
