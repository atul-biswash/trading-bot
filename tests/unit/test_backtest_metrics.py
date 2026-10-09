"""S3 through the backtest root: the equity loop, the record's equity and metrics blocks, the wiring.

``test_metrics.py`` proves the arithmetic on hand figures. These tests prove that the root samples
the portfolio at the right moments (every bar of every pair, after the executor), that what it
records can be recomputed from the two files a run writes, and that the committed regime labels
reach the metrics. The world is ``backtest_world.py``'s real store.
"""

from __future__ import annotations

import dataclasses
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

import trading_bot.backtesting.engine as engine_module
from tests.unit.backtest_world import CODE, WINDOW_BARS, at, build_world
from trading_bot.backtesting.engine import (
    BacktestResult,
    _EquityProbe,
    run_backtest,
    write_run,
)
from trading_bot.backtesting.metrics import (
    EquityCurve,
    EquitySummary,
    compute_metrics,
    load_trades_csv,
)
from trading_bot.backtesting.regimes import RegimeTable
from trading_bot.config.settings import Settings
from trading_bot.core.enums import PositionSide, ProtectionState
from trading_bot.core.models import Candle, Position
from trading_bot.core.portfolio import Portfolio

D = Decimal
HOUR = timedelta(hours=1)
RISING_Q1 = RegimeTable.from_document(
    {"quarters": [{"quarter": "2024Q1", "regime": "rising"}]}, digest="abc123"
)


async def run(settings: Settings, **kw: Any) -> BacktestResult:
    return await run_backtest(settings, code_facts=lambda: CODE, **kw)


def block(result: BacktestResult, name: str) -> dict[str, Any]:
    found = result.record[name]
    assert isinstance(found, dict)
    return found


class TestTheProbeSamplesThePortfolioAtMarket:
    """``_EquityProbe`` on its own: one position, one mark, an equity worked by hand."""

    @staticmethod
    def candle(close: str) -> Candle:
        opened = datetime(2024, 3, 1, 5, tzinfo=timezone.utc)
        return Candle(
            symbol="BTCUSDT",
            timeframe="1h",
            open_time=opened,
            close_time=opened + HOUR - timedelta(milliseconds=1),
            open=D(close),
            high=D(close),
            low=D(close),
            close=D(close),
            volume=D(1),
        )

    class Provider:
        def __init__(self, last: Candle | None) -> None:
            self.last = last

        def last_candle(self, symbol: str, timeframe: str) -> Candle | None:
            return self.last

    @staticmethod
    def holding() -> Portfolio:
        """1,000 free, then 2 BTC bought for a quote total of 400: 600 free and one position."""
        portfolio = Portfolio(quote_asset="USDT", free_quote=D(1000))
        position = Position(
            symbol="BTCUSDT",
            side=PositionSide.LONG,
            quantity=D(2),
            entry_price=D(200),
            entry_fill_price=D(200),
            entry_quote_total=D(400),
            entry_bar_time=datetime(2024, 3, 1, 4, tzinfo=timezone.utc),
            protection=ProtectionState.UNKNOWN,
            opened_at=datetime(2024, 3, 1, 4, tzinfo=timezone.utc),
            stop_loss=None,
            take_profit=None,
        )
        portfolio.open_position(position, cost=D(400))
        return portfolio

    def probe(self, portfolio: Portfolio, last: Candle | None, curve: EquityCurve) -> _EquityProbe:
        return _EquityProbe(
            provider=self.Provider(last),  # type: ignore[arg-type]
            portfolio=portfolio,
            timeframes={"BTCUSDT": "1h"},
            clock=lambda: datetime(2024, 3, 1, 6, tzinfo=timezone.utc),
            curve=curve,
        )

    async def test_equity_is_the_free_quote_plus_the_position_at_the_last_close(self) -> None:
        start = datetime(2024, 3, 1, tzinfo=timezone.utc)
        curve = EquityCurve(D(1000), start)
        await self.probe(self.holding(), self.candle("250"), curve)(self.candle("250"))
        summary = curve.summary()
        assert summary.final == D(1100)  # 600 free + 2 x 250
        assert summary.open_since == (datetime(2024, 3, 1, 4, tzinfo=timezone.utc),)
        assert summary.samples == 1
        assert summary.last_at == datetime(2024, 3, 1, 6, tzinfo=timezone.utc)

    async def test_the_mark_is_the_last_close_and_not_the_entry_price(self) -> None:
        start = datetime(2024, 3, 1, tzinfo=timezone.utc)
        curve = EquityCurve(D(1000), start)
        await self.probe(self.holding(), self.candle("150"), curve)(self.candle("150"))
        assert curve.summary().final == D(900)  # 600 + 2 x 150: below the 1,000 start
        assert curve.summary().max_drawdown == D("0.1")

    async def test_with_no_position_the_equity_is_the_free_quote_and_nothing_is_open(self) -> None:
        start = datetime(2024, 3, 1, tzinfo=timezone.utc)
        curve = EquityCurve(D(1000), start)
        flat = Portfolio(quote_asset="USDT", free_quote=D(1000))
        await self.probe(flat, None, curve)(self.candle("250"))
        assert curve.summary().final == D(1000) and curve.summary().open_since == ()

    async def test_a_position_with_no_mark_raises_rather_than_guessing_one(self) -> None:
        curve = EquityCurve(D(1000), datetime(2024, 3, 1, tzinfo=timezone.utc))
        with pytest.raises(ValueError, match="no mark price"):
            await self.probe(self.holding(), None, curve)(self.candle("250"))
        assert curve.summary().samples == 0


class TestTheLoopThroughARun:
    async def test_the_curve_is_sampled_once_per_bar_of_every_pair(self, tmp_path: Path) -> None:
        result = await run(build_world(tmp_path, symbols=("BTCUSDT", "ETHUSDT")))
        equity = block(result, "equity")
        assert equity["samples"] == 2 * WINDOW_BARS
        assert block(result, "stream")["bars_delivered"] == equity["samples"]

    async def test_it_starts_at_the_windows_start_with_the_initial_balance(
        self, tmp_path: Path
    ) -> None:
        result = await run(build_world(tmp_path))
        equity = block(result, "equity")
        assert equity["initial"] == "10000"
        assert equity["start"] == at(216).isoformat()  # 2024-03-10
        assert equity["last_at"] == at(720).isoformat()  # the last bar's nominal end

    async def test_with_nothing_open_the_final_equity_is_the_initial_plus_realised(
        self, tmp_path: Path
    ) -> None:
        result = await run(build_world(tmp_path))
        results = block(result, "results")
        assert results["open_positions_at_end"] == []
        assert D(block(result, "equity")["final"]) == D(10000) + D(results["realised_total"])
        assert D(block(result, "metrics")["final_equity"]) == D(block(result, "equity")["final"])

    async def test_the_daily_closes_cover_every_day_of_the_window_and_the_last_is_the_final(
        self, tmp_path: Path
    ) -> None:
        result = await run(build_world(tmp_path))
        equity = block(result, "equity")
        closes = equity["daily_closes"]
        assert list(closes) == [f"2024-03-{day:02d}" for day in range(10, 31)]
        assert closes["2024-03-30"] == equity["final"]
        assert block(result, "metrics")["days"] == 21

    async def test_the_marked_drawdown_is_never_smaller_than_the_closed_trades_alone_give(
        self, tmp_path: Path
    ) -> None:
        """A curve marked every bar contains every closed-trade equity as one of its points, so
        its worst decline is at least the worst decline of the closed trades alone. In THIS world
        the two coincide (the worst decline is a realised stop-out, 0.00871351...); that the
        marked curve can be strictly worse is shown by the probe tests above, where a position
        marked 2 x 150 against a 1,000 start gives 0.1 with no trade closed."""
        result = await run(build_world(tmp_path))
        peak = running = D(10000)
        closed_only = D(0)
        for trade in sorted(result.trades, key=lambda t: t.exit_time):
            running += trade.realised
            peak = max(peak, running)
            closed_only = max(closed_only, (peak - running) / peak)
        marked = D(block(result, "metrics")["max_drawdown"])
        assert marked >= closed_only > 0

    async def test_the_metrics_drawdown_is_the_equity_blocks_worst_pair(
        self, tmp_path: Path
    ) -> None:
        result = await run(build_world(tmp_path))
        equity = block(result, "equity")
        peak, trough = D(equity["drawdown_peak"]), D(equity["drawdown_trough"])
        assert D(block(result, "metrics")["max_drawdown"]) == (peak - trough) / peak
        assert D(block(result, "metrics")["max_drawdown_amount"]) == peak - trough
        assert datetime.fromisoformat(equity["drawdown_peak_at"]) < datetime.fromisoformat(
            equity["drawdown_trough_at"]
        )

    async def test_two_runs_record_the_same_equity_and_metrics(self, tmp_path: Path) -> None:
        settings = build_world(tmp_path)
        first, second = await run(settings), await run(settings)
        assert first.record["equity"] == second.record["equity"]
        assert first.record["metrics"] == second.record["metrics"]


class TestTheRecordedMetricsCanBeRecomputed:
    async def test_they_equal_the_metrics_recomputed_from_trades_csv_and_the_equity_block(
        self, tmp_path: Path
    ) -> None:
        result = await run(build_world(tmp_path), regimes=RISING_Q1)
        write_run(result, tmp_path / "out")
        recomputed = compute_metrics(
            load_trades_csv(tmp_path / "out" / "trades.csv"),
            EquitySummary.from_record(block(result, "equity")),
            quote_asset=str(result.record["quote_asset"]),
            regimes=RISING_Q1,
        )
        assert recomputed.to_record() == result.record["metrics"]
        assert recomputed.overall.trades == len(result.trades) > 10

    async def test_the_overall_trade_count_and_pnl_agree_with_the_results_block(
        self, tmp_path: Path
    ) -> None:
        result = await run(build_world(tmp_path))
        results, overall = block(result, "results"), block(result, "metrics")["overall"]
        assert overall["trades"] == results["trades"]
        assert overall["net_pnl"] == results["realised_total"]
        assert D(overall["entry_fees"]) == D(results["entry_fees_total"])
        assert D(overall["exit_fees"]) == D(results["exit_fees_total"])
        assert D(overall["fee_residual"]) == 0

    async def test_every_trade_of_a_run_is_labelled_by_the_regime_of_its_entry_quarter(
        self, tmp_path: Path
    ) -> None:
        result = await run(build_world(tmp_path), regimes=RISING_Q1)
        metrics = block(result, "metrics")
        regimes = metrics["by_regime"]
        assert regimes["rising"]["trades"] == metrics["overall"]["trades"]
        assert regimes["falling"]["trades"] == regimes["sideways"]["trades"] == 0
        assert regimes["unlabelled"]["trades"] == 0
        assert result.record["regime_labels"] == {"sha256": "abc123"}

    async def test_without_a_table_there_is_no_regime_breakdown_and_no_digest(
        self, tmp_path: Path
    ) -> None:
        result = await run(build_world(tmp_path))
        assert block(result, "metrics")["by_regime"] is None
        assert result.record["regime_labels"] is None

    async def test_the_breakdown_by_pair_matches_the_pairs_run(self, tmp_path: Path) -> None:
        result = await run(build_world(tmp_path, symbols=("BTCUSDT", "ETHUSDT")))
        by_pair = block(result, "metrics")["by_pair"]
        assert set(by_pair) == {"BTCUSDT", "ETHUSDT"}
        assert sum(group["trades"] for group in by_pair.values()) == len(result.trades)
        assert sum(D(group["net_pnl"]) for group in by_pair.values()) == D(
            block(result, "results")["realised_total"]
        )

    async def test_a_fee_identity_that_fails_makes_the_run_not_a_result(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        real = engine_module.compute_metrics

        def broken(*args: Any, **kwargs: Any) -> Any:
            found = real(*args, **kwargs)
            return dataclasses.replace(
                found, overall=dataclasses.replace(found.overall, fee_residual=D(1))
            )

        monkeypatch.setattr(engine_module, "compute_metrics", broken)
        result = await run(build_world(tmp_path))
        assert not result.complete
        assert result.problems == ("fee_identity_residual=1",)

    async def test_the_record_names_its_quote_asset(self, tmp_path: Path) -> None:
        result = await run(build_world(tmp_path))
        assert result.record["quote_asset"] == "USDT"
        assert block(result, "metrics")["quote_asset"] == "USDT"
