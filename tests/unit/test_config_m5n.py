"""``config.m5n.yaml`` is research only: it loads, it is a backtest, and it enables nothing live.

M5n's N3 adds one config for the research harness (P142 item 3). It must not be a way to run
anything: no venue, no stop that would be placed, no notification, no log file, no secret. It
names the in-sample window exactly, half-open, so that a harness reading it cannot read a bar at
or after 2024-01-01 (R-DT).
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any

import yaml

from trading_bot.config.models import AppConfig
from trading_bot.core.enums import TradingMode

REPO = Path(__file__).resolve().parents[2]
M5N = REPO / "config.m5n.yaml"


def parsed() -> dict[str, Any]:
    loaded = yaml.safe_load(M5N.read_text(encoding="utf-8"))
    assert isinstance(loaded, dict)
    return loaded


def loaded() -> AppConfig:
    return AppConfig.model_validate(parsed())


class TestItEnablesNothingLive:
    def test_it_loads_under_the_real_config_model(self) -> None:
        assert isinstance(loaded(), AppConfig)

    def test_the_mode_is_backtest(self) -> None:
        assert loaded().mode is TradingMode.BACKTEST

    def test_no_protective_order_is_enabled(self) -> None:
        risk = loaded().risk
        assert risk.stop_loss.enabled is False
        assert risk.take_profit.enabled is False
        assert risk.trailing_stop.enabled is False

    def test_no_notification_and_no_log_file(self) -> None:
        config = loaded()
        assert config.notifications.telegram.enabled is False
        assert config.logging.file.enabled is False

    def test_it_carries_no_secret(self) -> None:
        text = M5N.read_text(encoding="utf-8").lower()
        for word in ("api_key", "api_secret", "secret:", "token:", "chat_id"):
            assert word not in text, word

    def test_the_file_is_lf_only(self) -> None:
        assert b"\r" not in M5N.read_bytes()


class TestThePairsAndTheWindow:
    def test_the_pairs_are_btcusdt_and_ethusdt_daily_and_enabled(self) -> None:
        pairs = [(p.symbol, p.timeframe, p.enabled) for p in loaded().trading.pairs]
        assert pairs == [("BTCUSDT", "1d", True), ("ETHUSDT", "1d", True)]

    def test_the_window_is_the_in_sample_span_ending_at_the_boundary(self) -> None:
        window = loaded().backtesting
        assert window.start_date == date(2017, 8, 17)
        assert window.end_date == date(2024, 1, 1)

    def test_the_fee_is_ten_basis_points_per_side_as_a_decimal(self) -> None:
        fee = loaded().backtesting.fee_percent
        assert isinstance(fee, Decimal)
        assert fee == Decimal("0.10")

    def test_the_slippage_figures_are_the_shipped_ones(self) -> None:
        window = loaded().backtesting
        assert window.slippage_percent == Decimal("0.05")
        assert window.stop_slippage_percent == Decimal("1.20")

    def test_the_data_directory_is_the_mainnet_archive(self) -> None:
        window = loaded().backtesting
        assert window.data_dir == "data/historical"
        assert window.exchange_info_environment == "mainnet"


class TestTheStrategyIsACandidate:
    def test_it_names_one_of_the_six(self) -> None:
        # Imported for its registrations: the live registry does not import the package.
        import trading_bot.strategies.m5n  # noqa: F401
        from trading_bot.strategies.registry import available_strategies

        name = loaded().strategy.name
        assert name in available_strategies()
        assert name in {
            "donchian_1d_20",
            "donchian_1d_55",
            "sma_cross_1d_50_200",
            "donchian_4h_20",
            "keltner_4h_20_2",
            "tsmom_1d_90",
        }
