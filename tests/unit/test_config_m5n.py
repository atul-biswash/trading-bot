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
from trading_bot.core.enums import PositionSizingMethod, StopType, TradingMode

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

    def test_no_target_and_no_trailing_percent_is_enabled_and_the_stop_is_for_sizing_only(
        self,
    ) -> None:
        """Overturned at P145 under the N5 decisions (charter section 18), and kept to its subject.

        It asserted ``stop_loss.enabled is False``. N5 sizes 1 percent risk at the initial stop, which
        the unchanged risk manager refuses to do while the stop is disabled, so the stop is enabled
        here as a sizing input. What the test existed to say still holds and is still asserted: the
        file is a backtest (the mode test above), nothing is placed, and the only exit is the D1
        trail, so no take-profit and no trailing percent.
        """
        risk = loaded().risk
        assert risk.stop_loss.enabled is True
        assert risk.take_profit.enabled is False
        assert risk.trailing_stop.enabled is False

    def test_the_sizing_is_one_percent_risked_at_the_stop(self) -> None:
        risk = loaded().risk
        assert risk.position_sizing.method is PositionSizingMethod.RISK_PER_TRADE
        assert risk.position_sizing.risk_per_trade == Decimal("0.01")
        assert risk.stop_loss.type is StopType.PERCENT

    def test_every_other_risk_setting_is_a_default(self) -> None:
        """N5 decision: every other RiskManager setting stays at its default. The file sets only the
        staleness bound a 1d shortest timeframe needs, which is not a RiskManager limit."""
        raw = parsed()["risk"]
        assert set(raw) == {
            "position_sizing",
            "stop_loss",
            "take_profit",
            "trailing_stop",
            "max_position_staleness_s",
        }
        limits = loaded().risk.limits
        assert (
            limits.max_open_positions,
            limits.max_daily_loss_percent,
            limits.max_position_size_percent,
            limits.cooldown_minutes,
        ) == (3, Decimal("5.0"), Decimal("20"), 15)
        assert loaded().risk.max_entry_slippage == Decimal("0.001")

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
