"""The D1 executor wired into ``backtest_system`` (N4b): a strategy that declares the D1 exit takes the
new path, every other strategy takes the old one, and the whole chain runs over a real replay.

The worlds are built here from hand-written minutes (``tests/unit/d1_world.py``) and the decision bars
are aggregated from them, so a decision bar and the minutes under it agree. A scripted strategy emits
``BUY`` on named decision bars with a named trail, which keeps every expected figure a function of the
literals; one test at the end runs the real ``donchian_1d_20`` instead. The fill defaults apply: entry
slippage 0.05 percent, stop slippage 1.20 percent, fee 0.10 percent. A decision bar opening at 100 fills
at 100.05, so a 500-basis-point trail starts at 100.05 x 0.95 = 95.0475; a trigger there sells at
95.0475 x 0.988 = 93.90693, and a gapped open at 90 sells at 90 x 0.988 = 88.92.

The old path is pinned by the trade-log digests the simulated executor produced on the same worlds
before this change (measured at ``fec51e4``, the commit before the engine learned to choose).
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

import trading_bot.strategies.m5n  # noqa: F401  (registers the six candidates)
from tests.unit.backtest_world import CODE, build_world
from tests.unit.d1_world import TOUCH, Minute, ScriptedD1, at, build_minutes, flat, make_settings
from trading_bot.backtesting import engine
from trading_bot.backtesting.d1_executor import D1Executor
from trading_bot.backtesting.d1_risk import D1RiskManager
from trading_bot.backtesting.engine import BacktestResult, BacktestSystem, backtest_system
from trading_bot.backtesting.simulated_executor import SimulatedExecutor
from trading_bot.core.enums import RefusalStage, RiskRule
from trading_bot.core.models import Candle
from trading_bot.data.historical import HistoricalStore
from trading_bot.risk.manager import RiskManager
from trading_bot.strategies import registry

D = Decimal
OLD_DIGEST_ONE = "77421e427e840ca1f1482fed3a6f46792051d99a67dcdac2ae5affdaefbb9d10"
OLD_DIGEST_TWO = "3626ae33cc4a955cfa68db307de1ccb822145d383f076bec978705d3c7be4a6d"


async def run_world(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    timeframe: str,
    count: int,
    start: str,
    end: str,
    buy: dict[str, list[str]],
    paths: dict[str, dict[int, Minute]],
    omit: frozenset[int] = frozenset(),
    omit_decisions: frozenset[int] = frozenset(),
    delta: int = 500,
    n5: bool = False,
    max_open_positions: int | None = None,
) -> tuple[BacktestSystem, BacktestResult]:
    monkeypatch.setitem(registry._REGISTRY, "d1_scripted", ScriptedD1)
    root = tmp_path / "hist"
    for symbol in buy:
        build_minutes(
            root,
            symbol,
            count=count,
            minutes=paths.get(symbol),
            omit=omit,
            decision=timeframe,
            omit_decisions=omit_decisions,
        )
    settings = make_settings(
        tmp_path,
        root,
        pairs=[(symbol, timeframe) for symbol in buy],
        strategy="d1_scripted",
        params={"buy": buy, "delta": delta},
        start=start,
        end=end,
        n5=n5,
        max_open_positions=max_open_positions,
    )
    async with backtest_system(settings, code_facts=lambda: CODE) as system:
        result = await system.run()
        return system, result


def d1(system: BacktestSystem) -> D1Executor:
    assert isinstance(system.executor, D1Executor), type(system.executor)
    return system.executor


class TestTheChoice:
    async def test_a_strategy_that_declares_the_exit_takes_the_d1_executor(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        system, result = await run_world(
            tmp_path,
            monkeypatch,
            timeframe="4h",
            count=4320,
            start="2024-03-01",
            end="2024-03-04",
            buy={"BTCUSDT": ["2024-03-01T00:00"]},
            paths={},
        )
        assert type(system.executor) is D1Executor
        assert type(system.risk) is D1RiskManager
        assert result.complete, result.problems

    async def test_a_strategy_that_does_not_takes_the_simulated_executor_and_its_digest_holds(
        self, tmp_path: Path
    ) -> None:
        settings = build_world(tmp_path, symbols=("BTCUSDT",))
        async with backtest_system(settings, code_facts=lambda: CODE) as system:
            assert type(system.executor) is SimulatedExecutor
            assert type(system.risk) is RiskManager
            result = await system.run()
        assert len(result.trades) == 24
        assert result.trade_log_sha256 == OLD_DIGEST_ONE

    async def test_the_old_path_holds_on_two_pairs_too(self, tmp_path: Path) -> None:
        settings = build_world(tmp_path, symbols=("BTCUSDT", "ETHUSDT"))
        async with backtest_system(settings, code_facts=lambda: CODE) as system:
            assert type(system.executor) is SimulatedExecutor
            assert type(system.risk) is RiskManager
            result = await system.run()
        assert len(result.trades) == 48
        assert result.trade_log_sha256 == OLD_DIGEST_TWO

    async def test_no_series_is_asked_for_past_the_window_end(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        asked: list[tuple[str, datetime]] = []
        original = HistoricalStore.candles

        def spy(
            self: HistoricalStore, symbol: str, interval: str, start: datetime, end: datetime
        ) -> Iterator[Candle]:
            asked.append((interval, end))
            return original(self, symbol, interval, start, end)

        monkeypatch.setattr(HistoricalStore, "candles", spy)
        await run_world(
            tmp_path,
            monkeypatch,
            timeframe="4h",
            count=5000,
            start="2024-03-01",
            end="2024-03-04",
            buy={"BTCUSDT": ["2024-03-01T00:00"]},
            paths={"BTCUSDT": {4400: flat("90")}},
        )
        assert {interval for interval, _ in asked} == {"1m", "4h"}
        assert all(end <= at(4320) for _, end in asked)

    def test_a_mix_of_declaring_and_other_strategies_is_refused(self) -> None:
        class Fake:
            def __init__(self, flags: dict[str, bool]) -> None:
                self.flags = flags

            def strategy_for(self, symbol: str, timeframe: str) -> object:
                flag = self.flags[symbol]

                class S:
                    declares_d1_exit = flag

                return S()

        pairs = [_pair("BTCUSDT"), _pair("ETHUSDT")]
        from trading_bot.core.exceptions import ConfigError

        with pytest.raises(ConfigError, match="declare the D1 exit"):
            engine.uses_d1_executor(Fake({"BTCUSDT": True, "ETHUSDT": False}), pairs)
        assert engine.uses_d1_executor(Fake({"BTCUSDT": True, "ETHUSDT": True}), pairs) is True
        assert engine.uses_d1_executor(Fake({"BTCUSDT": False, "ETHUSDT": False}), pairs) is False


class TestN5SizingThroughTheWholeChain:
    """The signal's trail reaches the unchanged risk manager and the quantity that comes out is the
    1-percent one (N5). The fills are the hand-worked ones of the module docstring: a bar opening at
    100 fills at 100.05 under the entry limit 100.10, and equity is the 10,000 initial balance."""

    async def _position(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, *, delta: int, n5: bool
    ) -> Any:
        system, result = await run_world(
            tmp_path,
            monkeypatch,
            timeframe="4h",
            count=4320,
            start="2024-03-01",
            end="2024-03-04",
            buy={"BTCUSDT": ["2024-03-01T00:00"]},
            paths={},
            delta=delta,
            n5=n5,
        )
        assert result.complete, result.problems
        return system.portfolio.positions["BTCUSDT"]

    async def test_a_trail_of_1000_risks_one_percent(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        position = await self._position(tmp_path, monkeypatch, delta=1000, n5=True)
        assert position.quantity == D("9.990")
        assert position.stop_loss == D("90.045")
        assert position.entry_fill_price is not None
        # The loss from the fill to the executor's stop, which committed risk prices from.
        loss = position.quantity * (position.entry_fill_price - position.stop_loss)
        assert D("99") < loss <= D("100")

    async def test_the_upper_clamp_sizes_from_a_twenty_percent_stop(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        position = await self._position(tmp_path, monkeypatch, delta=2000, n5=True)
        assert position.quantity == D("4.995")
        assert position.stop_loss == D("80.04")

    async def test_the_lower_clamp_is_cut_by_the_position_cap(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        position = await self._position(tmp_path, monkeypatch, delta=10, n5=True)
        # 20 percent of 10,000 over the limit 100.10 is 19.98001998, rounded down to the world's
        # 0.00001 step; the other three quantities here are exact at that step too.
        assert position.quantity == D("19.98001")

    async def test_the_same_world_without_n5_is_sized_by_the_fixed_fraction(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        position = await self._position(tmp_path, monkeypatch, delta=1000, n5=False)
        assert position.quantity == D("1.998")


class TestRefusalsByRuleThroughTheWholeChain:
    """R-DT-3e: the executor's tally names the rule the real manager fired, on the real chain."""

    async def test_a_second_signal_while_held_is_already_in_position(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        system, result = await run_world(
            tmp_path,
            monkeypatch,
            timeframe="4h",
            count=4320,
            start="2024-03-01",
            end="2024-03-04",
            buy={"BTCUSDT": ["2024-03-01T00:00", "2024-03-01T04:00"]},
            paths={},
            delta=500,
            n5=True,
        )
        assert result.complete, result.problems
        tally = d1(system).tallies["BTCUSDT"]
        assert tally.refusals == {RefusalStage.LIMIT_REFUSED: 1}
        assert tally.rules == {RiskRule.ALREADY_IN_POSITION: 1}

    async def test_a_winner_on_an_untrailed_stop_halts_every_entry_including_its_own_pair(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """M5n-091 on the real chain. BTCUSDT is bought at 100 and jumps to 300 inside a 2000 bps trail
        (trigger 240), so it is never stopped; its executor stop stays at 80.04 and commits about
        1,099 against a threshold of 5 percent of about 11,000. Nothing is realised. The next day's
        signals on BOTH pairs are halted, and the one on BTCUSDT, which is held, is counted as the
        halt and not as a position already held (M5n-126)."""
        system, result = await run_world(
            tmp_path,
            monkeypatch,
            timeframe="4h",
            count=4320,
            start="2024-03-01",
            end="2024-03-04",
            buy={
                "BTCUSDT": ["2024-03-01T00:00", "2024-03-02T00:00"],
                "ETHUSDT": ["2024-03-02T00:00"],
            },
            paths={"BTCUSDT": {minute: flat("300") for minute in range(400, 4320)}},
            delta=2000,
            n5=True,
        )
        assert result.complete, result.problems
        assert result.trades == ()
        tallies = d1(system).tallies
        assert tallies["BTCUSDT"].refusals == {RefusalStage.LIMIT_REFUSED: 1}
        assert tallies["BTCUSDT"].rules == {RiskRule.DAILY_LOSS_HALT: 1}
        assert tallies["ETHUSDT"].refusals == {RefusalStage.LIMIT_REFUSED: 1}
        assert tallies["ETHUSDT"].rules == {RiskRule.DAILY_LOSS_HALT: 1}
        assert d1(system).unsettled["open_positions"] == ("BTCUSDT",)
        assert system.portfolio.realised_today(at(4319)) == 0


def _pair(symbol: str) -> Any:
    from trading_bot.config.models import PairConfig

    return PairConfig(symbol=symbol, timeframe="4h", enabled=True)


def scenario(timeframe: str) -> dict[str, Any]:
    """Two pairs that overlap, a refusal while in position, a gapped exit, a touch and an OPEN."""
    if timeframe == "4h":
        unit = 60 * 4
        names = ("2024-03-01T00:00", "2024-03-01T04:00", "2024-03-02T00:00")
        return {
            "count": 4320,
            "end": "2024-03-04",
            "btc_buys": list(names),
            "eth_buys": [names[0]],
            "paths": {"BTCUSDT": {700: flat("90")}, "ETHUSDT": {1000: TOUCH}},
            "entry_minute": unit,
            "btc_exit": 700,
            "eth_exit": 1000,
            "second_entry": 1680,
        }
    names = ("2024-03-01T00:00", "2024-03-02T00:00", "2024-03-04T00:00")
    return {
        "count": 10080,
        "end": "2024-03-08",
        "btc_buys": list(names),
        "eth_buys": [names[0]],
        "paths": {"BTCUSDT": {3000: flat("90")}, "ETHUSDT": {4000: TOUCH}},
        "entry_minute": 1440,
        "btc_exit": 3000,
        "eth_exit": 4000,
        "second_entry": 5760,
    }


@pytest.mark.parametrize("timeframe", ["4h", "1d"])
class TestBothPairsOnBothTimeframes:
    async def _run(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, timeframe: str
    ) -> tuple[BacktestSystem, BacktestResult, dict[str, Any]]:
        spec = scenario(timeframe)
        system, result = await run_world(
            tmp_path,
            monkeypatch,
            timeframe=timeframe,
            count=spec["count"],
            start="2024-03-01",
            end=spec["end"],
            buy={"BTCUSDT": spec["btc_buys"], "ETHUSDT": spec["eth_buys"]},
            paths=spec["paths"],
        )
        return system, result, spec

    async def test_the_run_is_complete_and_the_cash_identity_holds(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, timeframe: str
    ) -> None:
        _, result, _ = await self._run(tmp_path, monkeypatch, timeframe)
        assert result.complete, result.problems
        results = result.record["results"]
        assert isinstance(results, dict)
        assert D(str(results["cash_identity_residual"])) == 0

    async def test_each_pair_books_its_own_exit_at_the_hand_worked_price(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, timeframe: str
    ) -> None:
        _, result, spec = await self._run(tmp_path, monkeypatch, timeframe)
        by_symbol = {t.symbol: t for t in result.trades}
        assert set(by_symbol) == {"BTCUSDT", "ETHUSDT"}
        btc, eth = by_symbol["BTCUSDT"], by_symbol["ETHUSDT"]
        assert btc.entry_price == D("100.05")
        assert btc.stop_loss == D("95.0475")
        assert btc.exit_price == D("88.92")
        assert btc.exit_open_through_trigger is True
        assert btc.exit_time == at(spec["btc_exit"] + 1)
        assert eth.exit_price == D("93.90693")
        assert eth.exit_open_through_trigger is False
        assert eth.exit_time == at(spec["eth_exit"] + 1)

    async def test_the_positions_overlap_and_the_earlier_exit_is_booked_first(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, timeframe: str
    ) -> None:
        _, result, spec = await self._run(tmp_path, monkeypatch, timeframe)
        by_symbol = {t.symbol: t for t in result.trades}
        assert by_symbol["ETHUSDT"].entry_bar_open == at(spec["entry_minute"])
        assert by_symbol["BTCUSDT"].entry_bar_open == at(spec["entry_minute"])
        assert by_symbol["ETHUSDT"].entry_bar_open < by_symbol["BTCUSDT"].exit_time
        assert [t.symbol for t in result.trades] == ["BTCUSDT", "ETHUSDT"]

    async def test_a_signal_while_in_position_is_a_limit_refusal(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, timeframe: str
    ) -> None:
        system, _, _ = await self._run(tmp_path, monkeypatch, timeframe)
        tallies = d1(system).tallies
        assert tallies["BTCUSDT"].signals == 3
        assert tallies["BTCUSDT"].refusals == {RefusalStage.LIMIT_REFUSED: 1}
        assert tallies["ETHUSDT"].signals == 1
        assert tallies["ETHUSDT"].refusals == {}

    async def test_the_second_entry_is_still_open_at_the_end(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, timeframe: str
    ) -> None:
        system, result, spec = await self._run(tmp_path, monkeypatch, timeframe)
        assert d1(system).unsettled["open_positions"] == ("BTCUSDT",)
        results = result.record["results"]
        assert isinstance(results, dict)
        assert results["open_positions_at_end"] == ["BTCUSDT"]
        assert d1(system).counts.entries_filled == 3
        position = system.portfolio.positions["BTCUSDT"]
        assert position.opened_at == at(spec["second_entry"])


class TestAGapWhilePositionsAreOpen:
    async def test_a_missing_decision_bar_and_minutes_with_a_fall_exit_at_the_next_open(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        system, result = await run_world(
            tmp_path,
            monkeypatch,
            timeframe="4h",
            count=1440,
            start="2024-03-01",
            end="2024-03-02",
            buy={"BTCUSDT": ["2024-03-01T00:00"]},
            paths={"BTCUSDT": {520: flat("90")}},
            omit=frozenset(range(500, 520)),
            omit_decisions=frozenset({2}),
        )
        assert result.complete, result.problems
        (trade,) = result.trades
        assert trade.exit_price == D("88.92")
        assert trade.exit_open_through_trigger is True
        assert trade.spans_gap is True
        assert d1(system).counts.gaps_seen == 1

    async def test_the_same_gap_without_a_fall_leaves_the_position_open(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        system, result = await run_world(
            tmp_path,
            monkeypatch,
            timeframe="4h",
            count=1440,
            start="2024-03-01",
            end="2024-03-02",
            buy={"BTCUSDT": ["2024-03-01T00:00"]},
            paths={},
            omit=frozenset(range(500, 520)),
            omit_decisions=frozenset({2}),
        )
        assert result.complete, result.problems
        assert result.trades == ()
        assert d1(system).unsettled["open_positions"] == ("BTCUSDT",)


class TestTheRealCandidate:
    async def test_a_quiet_breakout_clamps_to_the_lower_bound_and_stays_open(
        self, tmp_path: Path
    ) -> None:
        minutes = {n: flat("10001") for n in range(25 * 1440, 30 * 1440)}
        settings = _donchian_world(tmp_path, minutes, base="10000")
        async with backtest_system(settings, code_facts=lambda: CODE) as system:
            result = await system.run()
        assert result.complete, result.problems
        tally = d1(system).tallies["BTCUSDT"]
        assert tally.signals == 1
        assert tally.deltas == [10]
        assert (tally.clamp_upper, tally.clamp_lower) == (0, 1)
        assert d1(system).unsettled["open_positions"] == ("BTCUSDT",)

    async def test_a_wild_breakout_clamps_to_the_upper_bound(self, tmp_path: Path) -> None:
        spikes = {day * 1440 + 10: ("100", "400", "10", "100", "1") for day in range(25)}
        calm = {n: flat("500") for n in range(25 * 1440, 30 * 1440)}
        settings = _donchian_world(tmp_path, {**spikes, **calm})
        async with backtest_system(settings, code_facts=lambda: CODE) as system:
            result = await system.run()
        assert result.complete, result.problems
        tally = d1(system).tallies["BTCUSDT"]
        assert tally.deltas == [2000]
        assert (tally.clamp_upper, tally.clamp_lower) == (1, 0)


def _donchian_world(tmp_path: Path, minutes: dict[int, Minute], base: str = "100") -> Any:
    root = tmp_path / "hist"
    build_minutes(root, "BTCUSDT", count=30 * 1440, minutes=minutes, base=base, decision="1d")
    return make_settings(
        tmp_path,
        root,
        pairs=[("BTCUSDT", "1d")],
        strategy="donchian_1d_20",
        params={},
        start="2024-03-01",
        end="2024-03-31",
    )
