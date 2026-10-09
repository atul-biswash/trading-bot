"""The backtest root (M5m S2): the live decision path over stored history, end to end.

The world these tests run in (a store built through the real ``ingest_zip``, snapshots through
the real ``store_snapshot``, a config through the real settings loader) is
``tests/unit/backtest_world.py``. Nothing is faked on the path under test: the provider, the
engine, the risk manager and the signal handler are the live ones, the executor is the
simulated one, and a run is judged by the run record it writes.
"""

from __future__ import annotations

import csv
import hashlib
import json
import logging
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from tests.unit.backtest_world import (
    CODE,
    HOUR_TD,
    WINDOW_BARS,
    at,
    build_world,
    exchange_info,
    make_settings,
    store_series,
)
from trading_bot.backtesting.engine import (
    RUN_RECORD_SCHEMA,
    BacktestError,
    BacktestResult,
    backtest_system,
    record_digest,
    run_backtest,
    write_run,
)
from trading_bot.backtesting.exchange_info import store_snapshot
from trading_bot.backtesting.replay import ReplayClient
from trading_bot.backtesting.simulated_executor import SimulatedExecutor
from trading_bot.config.models import BacktestConfig
from trading_bot.config.settings import Settings
from trading_bot.core.exceptions import ConfigError
from trading_bot.data.market_data import BufferedMarketDataProvider
from trading_bot.engine.live_engine import TradingEngine

D = Decimal


async def run(settings: Settings, **kw: Any) -> BacktestResult:
    return await run_backtest(settings, code_facts=lambda: CODE, **kw)


class TestARunIsAResult:
    async def test_a_run_over_a_clean_store_is_complete(self, tmp_path: Path) -> None:
        result = await run(build_world(tmp_path))
        assert result.complete, result.problems
        assert result.problems == ()
        assert len(result.trades) > 10
        assert {t.exit_reason.value for t in result.trades} == {"stop_loss", "take_profit", "close"}
        assert result.record["schema"] == RUN_RECORD_SCHEMA
        assert result.record["problems"] == []

    async def test_every_entry_is_handed_the_bar_after_its_signal_bar(self, tmp_path: Path) -> None:
        """The executor registers ahead of the engine, so a signal decided on a bar settles on
        the next one. Were it registered after, ``fill_entry`` would be handed the signal bar
        itself and raise, and the run would not be complete."""
        result = await run(build_world(tmp_path))
        assert result.complete
        assert all(t.entry_bar_open == t.signal_bar_open + HOUR_TD for t in result.trades)

    async def test_the_cash_identity_holds_exactly(self, tmp_path: Path) -> None:
        """initial + realised - open cost = free quote, to the last digit."""
        result = await run(build_world(tmp_path))
        results = result.record["results"]
        assert isinstance(results, dict)
        assert D(results["cash_identity_residual"]) == 0
        realised = sum((t.realised for t in result.trades), D(0))
        assert D(results["final_free_quote"]) == D(10000) + realised
        assert D(results["realised_total"]) == realised

    async def test_every_booking_is_the_live_identity(self, tmp_path: Path) -> None:
        result = await run(build_world(tmp_path))
        for trade in result.trades:
            assert trade.realised == trade.exit_gross - trade.entry_quote_total - trade.exit_fee

    async def test_every_approved_entry_is_accounted_for(self, tmp_path: Path) -> None:
        """Filled, refused, expired or unaffordable: nothing is lost, and the one entry signalled
        on the last bar expires with the data."""
        result = await run(build_world(tmp_path))
        entries = result.record["entries"]
        executor = result.record["executor"]
        assert isinstance(entries, dict) and isinstance(executor, dict)
        assert sum(entries.values()) == executor["entries_queued"]
        assert entries["filled"] == len(result.trades)
        assert entries["expired"] == 1
        assert result.attempts[-1].settled_bar_open is None

    async def test_the_record_names_what_the_run_stood_on(self, tmp_path: Path) -> None:
        settings = build_world(tmp_path)
        result = await run(settings)
        record = result.record
        root = tmp_path / "hist"
        series = root / "BTCUSDT" / "1h"
        assert record["code"] == CODE
        assert record["config"] == {
            "path": str(settings.config_path),
            "sha256": hashlib.sha256((tmp_path / "bt_config.yaml").read_bytes()).hexdigest(),
        }
        assert record["window"] == {
            "start_date": "2024-03-10",
            "end_date": "2024-03-31",
            "start": "2024-03-10T00:00:00+00:00",
            "end": "2024-03-31T00:00:00+00:00",
            "data_dir": root.as_posix(),
        }
        assert record["fill_parameters"] == {
            "fee_percent": "0.1",
            "slippage_percent": "0.05",
            "stop_slippage_percent": "1.20",
            "initial_balance": "10000",
        }
        assert record["strategy"] == {
            "name": "sma_crossover",
            "params": {"fast_period": 3, "slow_period": 8},
        }
        info_path = root / "_exchange_info" / "mainnet" / "BTCUSDT.json"
        assert record["exchange_info"] == {
            "BTCUSDT": {
                "environment": "mainnet",
                "sha256": hashlib.sha256(info_path.read_bytes()).hexdigest(),
            }
        }
        (pair,) = record["pairs"]  # type: ignore[misc]
        assert (
            pair["manifest_sha256"]
            == hashlib.sha256((series / "MANIFEST.jsonl").read_bytes()).hexdigest()
        )
        assert pair["registry_sha256"] is None
        assert pair["bars_served"] == WINDOW_BARS
        assert pair["first_open_time"] == at(216).isoformat()
        assert pair["last_open_time"] == at(719).isoformat()
        assert record["stream"] == {"bars_delivered": WINDOW_BARS, "handler_failures": 0}
        libraries = record["libraries"]
        assert isinstance(libraries, dict)
        assert set(libraries) >= {"pandas", "numpy", "pydantic"}
        assert all(version != "unknown" for version in libraries.values())

    async def test_two_runs_of_one_history_agree(self, tmp_path: Path) -> None:
        """The determinism test: equal trade-log digests, and equal records outside wall_clock."""
        settings = build_world(tmp_path)
        first = await run(settings)
        second = await run(settings)
        assert first.trade_log_sha256 == second.trade_log_sha256
        assert first.trade_log_sha256 != hashlib.sha256(b"").hexdigest()
        assert record_digest(first.record) == record_digest(second.record)
        assert first.record["wall_clock"] != {}

    async def test_a_changed_fill_parameter_changes_both_digests(self, tmp_path: Path) -> None:
        settings = build_world(tmp_path)
        base = await run(settings)
        harsher = settings.config.backtesting.model_copy(update={"stop_slippage_percent": D("3.0")})
        other = await run(settings, window=harsher)
        assert other.trade_log_sha256 != base.trade_log_sha256
        assert record_digest(other.record) != record_digest(base.record)

    async def test_a_window_can_be_passed_in_place_of_the_configured_one(
        self, tmp_path: Path
    ) -> None:
        settings = build_world(tmp_path)
        window = BacktestConfig(start_date="2024-03-20", end_date="2024-03-25")
        result = await run(
            settings, window=window.model_copy(update={"data_dir": str(tmp_path / "hist")})
        )
        (pair,) = result.record["pairs"]  # type: ignore[misc]
        assert pair["bars_served"] == 5 * 24
        assert pair["first_open_time"] == at(19 * 24).isoformat()


class TestTheRootAndItsTeardown:
    async def test_the_client_is_closed_when_the_run_completes(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        closed: list[int] = []
        real = ReplayClient.close

        async def spy(self: ReplayClient) -> None:
            closed.append(1)
            await real(self)

        monkeypatch.setattr(ReplayClient, "close", spy)
        await run(build_world(tmp_path))
        assert closed == [1]

    async def test_the_client_is_closed_when_a_later_boot_step_fails(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        closed: list[int] = []
        real = ReplayClient.close

        async def spy(self: ReplayClient) -> None:
            closed.append(1)
            await real(self)

        async def boom(*args: Any, **kwargs: Any) -> TradingEngine:
            raise RuntimeError("engine build failed")

        monkeypatch.setattr(ReplayClient, "close", spy)
        monkeypatch.setattr(TradingEngine, "create", boom)
        settings = build_world(tmp_path)
        with pytest.raises(RuntimeError, match="engine build failed"):
            async with backtest_system(settings, code_facts=lambda: CODE):
                pytest.fail("the root yielded despite a failed boot")
        assert closed == [1]

    async def test_the_client_is_closed_when_the_body_raises(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        closed: list[int] = []
        real = ReplayClient.close

        async def spy(self: ReplayClient) -> None:
            closed.append(1)
            await real(self)

        monkeypatch.setattr(ReplayClient, "close", spy)
        settings = build_world(tmp_path)
        with pytest.raises(ZeroDivisionError):
            async with backtest_system(settings, code_facts=lambda: CODE):
                raise ZeroDivisionError
        assert closed == [1]

    async def test_the_engine_is_stopped_when_the_run_completes(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        stopped: list[int] = []
        real = TradingEngine.stop

        async def spy(self: TradingEngine) -> None:
            stopped.append(1)
            await real(self)

        monkeypatch.setattr(TradingEngine, "stop", spy)
        await run(build_world(tmp_path))
        assert stopped == [1]

    async def test_the_provider_is_stopped_when_the_body_raises_before_the_engine_started(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """``TradingEngine.stop`` releases only what ``start`` acquired, so an engine that never
        started leaves the provider to the root's own scope."""
        stopped: list[int] = []
        real = BufferedMarketDataProvider.stop

        async def spy(self: BufferedMarketDataProvider) -> None:
            stopped.append(1)
            await real(self)

        monkeypatch.setattr(BufferedMarketDataProvider, "stop", spy)
        settings = build_world(tmp_path)
        with pytest.raises(ZeroDivisionError):
            async with backtest_system(settings, code_facts=lambda: CODE):
                raise ZeroDivisionError
        assert stopped == [1]

    async def test_a_system_runs_once(self, tmp_path: Path) -> None:
        settings = build_world(tmp_path)
        async with backtest_system(settings, code_facts=lambda: CODE) as system:
            await system.run()
            with pytest.raises(BacktestError, match="already run"):
                await system.run()

    async def test_the_executor_is_registered_ahead_of_the_engine(self, tmp_path: Path) -> None:
        """The first subscriber the provider calls is the executor, and the engine's hook, added
        by ``engine.start``, comes after it."""
        settings = build_world(tmp_path)
        async with backtest_system(settings, code_facts=lambda: CODE) as system:
            before = list(system.provider._handlers)
            assert before[0] == system.executor
            await system.engine.start()
            after = list(system.provider._handlers)
            assert after[:-1] == before
            assert after[-1] != system.executor

    async def test_a_symbol_the_config_does_not_enable_is_refused(self, tmp_path: Path) -> None:
        settings = build_world(tmp_path)
        with pytest.raises(ConfigError, match="DOGEUSDT"):
            await run(settings, symbols=["DOGEUSDT"])

    async def test_a_missing_snapshot_is_refused_with_the_remedy(self, tmp_path: Path) -> None:
        root = tmp_path / "hist"
        store_series(root, "BTCUSDT")
        settings = make_settings(tmp_path, root)
        with pytest.raises(ConfigError, match="download_exchange_info"):
            await run(settings)

    async def test_the_other_environments_snapshot_is_not_used(self, tmp_path: Path) -> None:
        settings = build_world(tmp_path)
        with pytest.raises(ConfigError, match="testnet"):
            await run(settings, exchange_info_environment="testnet")

    async def test_a_symbol_on_two_timeframes_is_refused(self, tmp_path: Path) -> None:
        root = tmp_path / "hist"
        store_series(root, "BTCUSDT")
        store_snapshot(root, "mainnet", "BTCUSDT", exchange_info("BTCUSDT"))
        settings = make_settings(tmp_path, root, pairs=(("BTCUSDT", "1h"), ("BTCUSDT", "5m")))
        with pytest.raises(ConfigError, match="two timeframes"):
            await run(settings)

    async def test_a_pair_quoted_in_another_asset_is_refused(self, tmp_path: Path) -> None:
        root = tmp_path / "hist"
        store_series(root, "BTCEUR")
        store_snapshot(root, "mainnet", "BTCEUR", exchange_info("BTCEUR", quote="EUR"))
        settings = make_settings(tmp_path, root, pairs=(("BTCEUR", "1h"),))
        with pytest.raises(ConfigError, match="EUR"):
            await run(settings)

    async def test_a_symbol_filter_replays_only_that_pair(self, tmp_path: Path) -> None:
        settings = build_world(tmp_path, symbols=("BTCUSDT", "ETHUSDT"))
        both = await run(settings)
        try:
            only_eth = await run(settings, symbols=["ethusdt"])
        except ConfigError as exc:
            pytest.fail(f"a lower-case symbol was refused: {exc}")
        assert {t.symbol for t in both.trades} == {"BTCUSDT", "ETHUSDT"}
        assert {t.symbol for t in only_eth.trades} == {"ETHUSDT"}
        assert [p["symbol"] for p in only_eth.record["pairs"]] == ["ETHUSDT"]  # type: ignore[attr-defined]
        assert list(only_eth.record["exchange_info"]) == ["ETHUSDT"]  # type: ignore[call-overload]


class TestARunThatRaisedIsNotAResult:
    async def test_a_failing_executor_is_counted_and_the_run_is_incomplete(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The provider isolates a failing subscriber and logs it, so the run carries on and
        would finish with fills silently skipped. The system counts the ERROR."""
        calls = {"n": 0}
        real = SimulatedExecutor.__call__

        async def flaky(self: SimulatedExecutor, candle: Any) -> None:
            calls["n"] += 1
            if calls["n"] == 40:
                raise RuntimeError("the executor broke")
            await real(self, candle)

        monkeypatch.setattr(SimulatedExecutor, "__call__", flaky)
        result = await run(build_world(tmp_path))
        assert not result.complete
        assert any(problem.startswith("error_log_records=") for problem in result.problems)
        errors = result.record["error_log_records"]
        assert isinstance(errors, dict) and errors["count"] == 1
        assert "handler failed" in errors["first"][0]

    async def test_a_pair_that_served_no_bars_is_not_a_result(self, tmp_path: Path) -> None:
        settings = build_world(tmp_path)
        window = settings.config.backtesting.model_copy(
            update={
                "start_date": date(2025, 1, 1),
                "end_date": date(2025, 2, 1),
            }
        )
        result = await run(settings, window=window)
        assert not result.complete
        assert result.problems == ("BTCUSDT 1h served no bars",)

    async def test_an_error_logged_after_the_run_is_not_counted(self, tmp_path: Path) -> None:
        """The tally is detached when the run ends: an ERROR logged afterwards, by anything in the
        process, reaches neither this run's count nor its record."""
        settings = build_world(tmp_path)
        async with backtest_system(settings, code_facts=lambda: CODE) as system:
            result = await system.run()
            logging.getLogger("trading_bot.test").error("after the run")
            assert system._errors.count == 0
        assert result.complete

    async def test_a_stream_handler_failure_is_counted_and_the_run_is_incomplete(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A failure that escapes the provider reaches the stream's own isolation, which counts
        it; the run reports that count as its own problem and not only as a logged ERROR."""
        real = BufferedMarketDataProvider._append

        def flaky(self: BufferedMarketDataProvider, key: Any, candle: Any) -> bool:
            # The seed also appends, so the failing bar is named and not counted.
            if candle.open_time == at(300):
                raise RuntimeError("the buffer broke")
            return real(self, key, candle)

        monkeypatch.setattr(BufferedMarketDataProvider, "_append", flaky)
        result = await run(build_world(tmp_path))
        assert not result.complete
        assert "stream_handler_failures=1" in result.problems
        assert result.record["stream"] == {"bars_delivered": WINDOW_BARS, "handler_failures": 1}

    async def test_a_cash_identity_that_does_not_hold_is_not_a_result(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """One unit of quote appears in the ledger from nowhere, as a booking bug would leave it."""
        settings = build_world(tmp_path)
        async with backtest_system(settings, code_facts=lambda: CODE) as system:
            real = SimulatedExecutor.finish

            def leaky(self: SimulatedExecutor) -> None:
                real(self)
                system.portfolio.free_quote = system.portfolio.free_quote + D(1)

            monkeypatch.setattr(SimulatedExecutor, "finish", leaky)
            result = await system.run()
        assert not result.complete
        (problem,) = result.problems
        assert problem.startswith("cash_identity_residual=")
        assert D(problem.split("=")[1]) == -1
        results = result.record["results"]
        assert isinstance(results, dict) and D(results["cash_identity_residual"]) == -1


class TestWriteRun:
    async def test_the_record_and_the_trades_are_written_to_a_new_directory(
        self, tmp_path: Path
    ) -> None:
        result = await run(build_world(tmp_path))
        run_path, trades_path = write_run(result, tmp_path / "out" / "run-1")
        assert json.loads(run_path.read_text(encoding="utf-8")) == json.loads(
            json.dumps(result.record)
        )
        with trades_path.open(encoding="utf-8", newline="") as handle:
            rows = list(csv.DictReader(handle))
        assert len(rows) == len(result.trades)
        assert rows[0]["exit_reason"] == result.trades[0].exit_reason.value
        assert D(rows[0]["realised"]) == result.trades[0].realised
        assert b"\r" not in trades_path.read_bytes()
        assert b"\r" not in run_path.read_bytes()

    async def test_an_existing_directory_is_never_overwritten(self, tmp_path: Path) -> None:
        result = await run(build_world(tmp_path))
        write_run(result, tmp_path / "out")
        with pytest.raises(FileExistsError):
            write_run(result, tmp_path / "out")

    async def test_a_directory_the_caller_made_can_be_filled_and_keeps_what_it_held(
        self, tmp_path: Path
    ) -> None:
        """The command makes the directory first, for its log; `existing=True` fills it."""
        result = await run(build_world(tmp_path))
        directory = tmp_path / "out"
        directory.mkdir()
        (directory / "backtest.log").write_bytes(b"a log line\n")
        run_path, trades_path = write_run(result, directory, existing=True)
        assert sorted(p.name for p in directory.iterdir()) == [
            "backtest.log",
            "run.json",
            "trades.csv",
        ]
        assert (directory / "backtest.log").read_bytes() == b"a log line\n"
        assert (run_path.parent, trades_path.parent) == (directory, directory)

    async def test_existing_requires_the_directory_to_exist(self, tmp_path: Path) -> None:
        result = await run(build_world(tmp_path))
        with pytest.raises(FileNotFoundError):
            write_run(result, tmp_path / "never-made", existing=True)
        assert not (tmp_path / "never-made").exists()

    async def test_existing_never_overwrites_a_record_already_there(self, tmp_path: Path) -> None:
        result = await run(build_world(tmp_path))
        directory = tmp_path / "out"
        directory.mkdir()
        (directory / "run.json").write_bytes(b"an earlier record\n")
        with pytest.raises(FileExistsError):
            write_run(result, directory, existing=True)
        assert (directory / "run.json").read_bytes() == b"an earlier record\n"
        assert not (directory / "trades.csv").exists()

    async def test_a_run_with_no_trade_still_writes_the_columns(self, tmp_path: Path) -> None:
        settings = build_world(tmp_path)
        window = settings.config.backtesting.model_copy(
            update={
                "start_date": date(2024, 3, 1),
                "end_date": date(2024, 3, 2),
            }
        )
        result = await run(settings, window=window)
        _, trades_path = write_run(result, tmp_path / "out")
        header = trades_path.read_text(encoding="utf-8").splitlines()[0]
        assert header.startswith("symbol,timeframe,signal_bar_open,")
        assert header.endswith(",spans_gap,spans_short_bar")


class TestGapsInTheData:
    async def test_a_hole_in_the_data_is_seen_and_guarded(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Hours 274 to 278 are missing. Without the hole a BUY is signalled on the bar of hour
        281 and filled; with it, the bars after the hole are fewer than the strategy's warm-up
        window, so the live engine's gap guard refuses that BUY (R-P1) and says so once."""
        clean = await run(build_world(tmp_path / "clean"))
        assert at(281) in {t.signal_bar_open for t in clean.trades}

        caplog.set_level(logging.WARNING)
        holed = await run(build_world(tmp_path / "holed", omit=frozenset(range(274, 279))))
        assert holed.complete, holed.problems
        refused = [r for r in caplog.records if getattr(r, "event", None) == "buy_refused_bars_gap"]
        assert len(refused) == 1
        assert at(281) not in {t.signal_bar_open for t in holed.trades}
        executor = holed.record["executor"]
        assert isinstance(executor, dict) and executor["gaps_seen"] == 1
        assert holed.record["stream"] == {
            "bars_delivered": WINDOW_BARS - 5,
            "handler_failures": 0,
        }

    async def test_a_trade_across_the_hole_is_flagged_in_the_record(self, tmp_path: Path) -> None:
        result = await run(build_world(tmp_path, omit=frozenset(range(274, 279))))
        results = result.record["results"]
        assert isinstance(results, dict)
        assert results["trades_spanning_a_gap"] == sum(1 for t in result.trades if t.spans_gap)
        assert results["trades_spanning_a_short_bar"] == 0
