"""The ``backtest`` command (M5m S2): flags laid over the config, a record written, an honest exit.

The world is ``tests/unit/backtest_world.py``: a real store, real snapshots and a real config, so
the command runs the whole composition root and these tests judge it by what it writes and
what it returns. ``main`` is driven as an operator drives it, through ``argv``.
"""

from __future__ import annotations

import argparse
import json
import logging
from collections.abc import Iterator
from datetime import date, datetime, timezone
from pathlib import Path

import pytest

import trading_bot.main as cli
from tests.unit.backtest_world import WINDOW_BARS, at, build_world, make_settings, store_series
from trading_bot.config.models import BacktestConfig
from trading_bot.config.settings import Settings
from trading_bot.core.exceptions import ConfigError
from trading_bot.utils.logger import setup_logging as real_setup_logging


@pytest.fixture(autouse=True)
def _no_logging_setup(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep ``main`` from replacing the root handlers ``caplog`` depends on."""
    monkeypatch.setattr(cli, "setup_logging", lambda _config: None)


def argv(tmp_path: Path, *rest: str) -> list[str]:
    return ["--config", str(tmp_path / "bt_config.yaml"), "backtest", *rest]


def records(tmp_path: Path) -> list[Path]:
    root = tmp_path / "backtests"
    return sorted(root.iterdir()) if root.is_dir() else []


def only_record(tmp_path: Path) -> Path:
    """The one run directory, asserted to be one: a count is an assertion, not an unpack."""
    found = records(tmp_path)
    assert len(found) == 1, found
    return found[0]


class TestTheWindowTheFlagsResolve:
    def configured(self) -> BacktestConfig:
        return BacktestConfig(
            start_date="2024-01-01",
            end_date="2024-02-01",
            initial_balance=5000,
            fee_percent="0.075",
            stop_slippage_percent="0.66",
            data_dir="elsewhere",
        )

    def test_no_flag_leaves_the_configured_window_and_costs(self) -> None:
        resolved = cli._resolve_window(self.configured(), None, None)
        assert resolved == self.configured()

    def test_each_flag_replaces_only_its_own_date(self) -> None:
        only_start = cli._resolve_window(self.configured(), date(2024, 1, 10), None)
        assert (only_start.start_date, only_start.end_date) == (date(2024, 1, 10), date(2024, 2, 1))
        only_end = cli._resolve_window(self.configured(), None, date(2024, 1, 20))
        assert (only_end.start_date, only_end.end_date) == (date(2024, 1, 1), date(2024, 1, 20))

    def test_the_costs_and_the_data_directory_survive_the_flags(self) -> None:
        resolved = cli._resolve_window(self.configured(), date(2024, 1, 10), date(2024, 1, 20))
        assert resolved.fee_percent == self.configured().fee_percent
        assert resolved.stop_slippage_percent == self.configured().stop_slippage_percent
        assert resolved.initial_balance == self.configured().initial_balance
        assert resolved.data_dir == "elsewhere"

    def test_a_reversed_or_empty_window_is_refused_as_config_would_be(self) -> None:
        with pytest.raises(ConfigError, match="end_date"):
            cli._resolve_window(self.configured(), date(2024, 3, 1), None)
        with pytest.raises(ConfigError, match="end_date"):
            cli._resolve_window(self.configured(), date(2024, 1, 5), date(2024, 1, 5))


class TestTheParser:
    def test_a_malformed_date_is_a_usage_error(self) -> None:
        with pytest.raises(SystemExit) as exit_info:
            cli._build_parser().parse_args(["backtest", "--start", "2024-13-45"])
        assert exit_info.value.code == 2

    def test_the_flags_parse(self) -> None:
        args = cli._build_parser().parse_args(
            ["backtest", "--start", "2024-03-01", "--end", "2024-04-01", "--symbols", "A", "B"]
        )
        assert (args.start, args.end, args.symbols) == (
            date(2024, 3, 1),
            date(2024, 4, 1),
            ["A", "B"],
        )
        bare = cli._build_parser().parse_args(["backtest"])
        assert (bare.start, bare.end, bare.symbols) == (None, None, None)

    def test_the_date_type_names_the_bad_text(self) -> None:
        with pytest.raises(argparse.ArgumentTypeError, match="2024-13-45"):
            cli._iso_date("2024-13-45")


class TestTheCommand:
    def test_it_runs_writes_the_record_and_returns_zero(self, tmp_path: Path) -> None:
        build_world(tmp_path)
        code = cli.main(argv(tmp_path, "--start", "2024-03-12", "--end", "2024-03-14"))
        assert code == 0
        directory = only_record(tmp_path)
        record = json.loads((directory / "run.json").read_text(encoding="utf-8"))
        assert record["window"]["start_date"] == "2024-03-12"
        assert record["window"]["end_date"] == "2024-03-14"
        assert record["pairs"][0]["bars_served"] == 48
        assert (directory / "trades.csv").is_file()
        digest = record["results"]["trade_log_sha256"]
        assert directory.name.endswith("-" + digest[:12])
        assert directory.name[8] == "T" and directory.name[:8].isdigit()

    def test_with_no_flag_the_configured_window_is_the_resolved_one(self, tmp_path: Path) -> None:
        build_world(tmp_path)
        assert cli.main(argv(tmp_path)) == 0
        directory = only_record(tmp_path)
        record = json.loads((directory / "run.json").read_text(encoding="utf-8"))
        assert record["window"]["start_date"] == "2024-03-10"
        assert record["pairs"][0]["bars_served"] == WINDOW_BARS
        assert record["pairs"][0]["first_open_time"] == at(216).isoformat()

    def test_the_symbols_flag_replays_only_those_pairs(self, tmp_path: Path) -> None:
        build_world(tmp_path, symbols=("BTCUSDT", "ETHUSDT"))
        assert cli.main(argv(tmp_path, "--symbols", "ethusdt")) == 0
        directory = only_record(tmp_path)
        record = json.loads((directory / "run.json").read_text(encoding="utf-8"))
        assert [pair["symbol"] for pair in record["pairs"]] == ["ETHUSDT"]

    def test_a_run_that_is_not_a_result_still_writes_its_record_and_returns_one(
        self, tmp_path: Path
    ) -> None:
        build_world(tmp_path)
        code = cli.main(argv(tmp_path, "--start", "2025-01-01", "--end", "2025-02-01"))
        assert code == 1
        directory = only_record(tmp_path)
        record = json.loads((directory / "run.json").read_text(encoding="utf-8"))
        assert record["problems"] == ["BTCUSDT 1h served no bars"]

    def test_a_symbol_the_config_does_not_enable_is_a_message_and_exit_one(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        build_world(tmp_path)
        assert cli.main(argv(tmp_path, "--symbols", "DOGEUSDT")) == 1
        assert any("DOGEUSDT" in r.getMessage() for r in caplog.records)
        assert records(tmp_path) == []

    def test_a_reversed_window_is_a_message_and_exit_one(self, tmp_path: Path) -> None:
        build_world(tmp_path)
        assert cli.main(argv(tmp_path, "--start", "2024-04-01", "--end", "2024-03-01")) == 1
        assert records(tmp_path) == []

    def test_it_never_asks_for_a_credential(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def refuse(self: Settings) -> tuple[str, str]:
            raise AssertionError("a backtest asked for exchange credentials")

        monkeypatch.setattr(Settings, "binance_credentials", refuse)
        build_world(tmp_path)
        assert cli.main(argv(tmp_path, "--start", "2024-03-12", "--end", "2024-03-13")) == 0

    def test_two_runs_write_two_directories_and_the_same_trade_log(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Two runs of one history inside one second still name two directories: the stamp
        carries microseconds. The clock is pinned to two instants a microsecond apart, so the
        test does not depend on how fast a run is."""
        instants = iter(
            datetime(2026, 10, 8, 12, 0, 0, microsecond, tzinfo=timezone.utc)
            for microsecond in (1, 2)
        )
        monkeypatch.setattr(cli, "utc_now", lambda: next(instants))
        build_world(tmp_path)
        window = ("--start", "2024-03-12", "--end", "2024-03-16")
        assert cli.main(argv(tmp_path, *window)) == 0
        try:
            second_code = cli.main(argv(tmp_path, *window))
        except FileExistsError as exc:
            pytest.fail(f"the second run named the first run's directory: {exc}")
        assert second_code == 0
        found = records(tmp_path)
        assert len(found) == 2, found
        first, second = found
        assert first.name[:15] == second.name[:15] == "20261008T120000"
        assert first.name != second.name
        assert (first / "trades.csv").read_bytes() == (second / "trades.csv").read_bytes()


@pytest.fixture
def real_logging(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Iterator[Path]:
    """The real ``setup_logging``, run from ``tmp_path`` so ``logs/trading_bot.log`` resolves
    there; the root logger is put back as it was. Yields the bot's log path, which may not exist."""
    root = logging.getLogger()
    saved_handlers, saved_level = list(root.handlers), root.level
    monkeypatch.setattr(cli, "setup_logging", real_setup_logging)
    monkeypatch.chdir(tmp_path)
    yield tmp_path / "logs" / "trading_bot.log"
    for handler in list(root.handlers):
        root.removeHandler(handler)
        if handler not in saved_handlers:
            handler.close()
    for handler in saved_handlers:
        root.addHandler(handler)
    root.setLevel(saved_level)


class TestTheLogStaysInTheRunDirectory:
    """R-AG: a backtest logs only to a file in its own run directory."""

    WINDOW = ("--start", "2024-03-12", "--end", "2024-03-14")

    def test_the_bot_log_is_the_file_a_non_backtest_command_writes(
        self, tmp_path: Path, real_logging: Path
    ) -> None:
        """The control arm: with this config `strategies` DOES write `logs/trading_bot.log`, so
        the untouched file in the next test is not untouched merely because logging is off."""
        build_world(tmp_path, file_logging=True)
        assert cli.main(["--config", str(tmp_path / "bt_config.yaml"), "strategies"]) == 0
        assert real_logging.is_file()
        assert "boot_provenance" in real_logging.read_text(encoding="utf-8")

    def test_a_backtest_leaves_the_bot_log_exactly_as_it_found_it(
        self, tmp_path: Path, real_logging: Path
    ) -> None:
        build_world(tmp_path, file_logging=True)
        real_logging.parent.mkdir()
        sentinel = b"the bot's own line, written before the backtest\n"
        real_logging.write_bytes(sentinel)
        stamp_before = real_logging.stat().st_mtime_ns
        assert cli.main(argv(tmp_path, *self.WINDOW)) == 0
        assert real_logging.read_bytes() == sentinel
        assert real_logging.stat().st_mtime_ns == stamp_before
        assert sorted(p.name for p in real_logging.parent.iterdir()) == ["trading_bot.log"]

    def test_the_run_directory_holds_the_whole_log_from_the_banner_on(
        self, tmp_path: Path, real_logging: Path
    ) -> None:
        build_world(tmp_path, file_logging=True)
        assert cli.main(argv(tmp_path, *self.WINDOW)) == 0
        directory = only_record(tmp_path)
        assert sorted(p.name for p in directory.iterdir()) == [
            "backtest.log",
            "run.json",
            "trades.csv",
        ]
        text = (directory / "backtest.log").read_text(encoding="utf-8")
        # The banner and the provenance line were logged BEFORE the directory existed.
        assert "event=boot_provenance" in text
        assert "event=intent_dispatched" in text
        assert text.index("event=boot_provenance") < text.index("Backtest window:")
        assert text.index("Backtest window:") < text.index("event=intent_dispatched")
        assert "Backtest complete" in text
        assert str(directory / "run.json") in text

    def test_a_refusal_before_the_run_writes_no_file_at_all(
        self, tmp_path: Path, real_logging: Path
    ) -> None:
        build_world(tmp_path, file_logging=True)
        assert cli.main(argv(tmp_path, "--symbols", "DOGEUSDT")) == 1
        assert records(tmp_path) == []
        assert not real_logging.parent.exists()
        assert list(tmp_path.rglob("*.log")) == []

    def test_a_run_that_raises_keeps_its_log_in_a_failed_directory(
        self, tmp_path: Path, real_logging: Path
    ) -> None:
        root = tmp_path / "hist"
        store_series(root, "BTCUSDT")  # a store and no exchangeInfo snapshot
        make_settings(tmp_path, root, file_logging=True)
        assert cli.main(argv(tmp_path, *self.WINDOW)) == 1
        directory = only_record(tmp_path)
        assert directory.name.endswith("-failed")
        assert sorted(p.name for p in directory.iterdir()) == ["backtest.log"]
        text = (directory / "backtest.log").read_text(encoding="utf-8")
        assert "Backtest aborted: ConfigError" in text
        assert "download_exchange_info" in text
        assert "event=boot_provenance" in text
        assert not real_logging.parent.exists()
