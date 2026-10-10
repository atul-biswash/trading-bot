"""Tests for ``BacktestConfig``: the exact money fields and the half-open UTC window.

M5m S2 multiplies ``fee_percent``, ``slippage_percent``, ``stop_slippage_percent`` and
``initial_balance`` by money, so by the rule in ``config/models.py`` they are ``Decimal`` from
load, not ``float``. The window is ``[start_date, end_date)`` in UTC dates.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from typing import get_args

import pytest
from pydantic import ValidationError

from trading_bot.backtesting.exchange_info import ENVIRONMENTS
from trading_bot.config.models import BacktestConfig
from trading_bot.config.settings import get_settings

_MONEY_FIELDS = ("initial_balance", "fee_percent", "slippage_percent", "stop_slippage_percent")


def _config(**overrides: object) -> BacktestConfig:
    values: dict[str, object] = {"start_date": "2024-01-01", "end_date": "2024-02-01"}
    values.update(overrides)
    return BacktestConfig(**values)


class TestTheMoneyFieldsAreExactDecimals:
    @pytest.mark.parametrize("field", _MONEY_FIELDS)
    def test_each_money_field_is_declared_decimal(self, field: str) -> None:
        """The declared type is the boundary: a ``float`` annotation here would let
        ``Decimal * float`` raise in the fill model, or worse, compare silently."""
        assert BacktestConfig.model_fields[field].annotation is Decimal

    def test_the_defaults_are_exact_decimals(self) -> None:
        config = _config()
        assert config.initial_balance == Decimal("10000")
        assert config.fee_percent == Decimal("0.1")
        assert config.slippage_percent == Decimal("0.05")
        assert config.stop_slippage_percent == Decimal("1.20")
        for field in _MONEY_FIELDS:
            assert type(getattr(config, field)) is Decimal

    def test_the_stop_slippage_default_is_the_owners_1_20_percent(self) -> None:
        """R-B2: the mean of the census of record's eight SL legs, rounded up."""
        assert str(_config().stop_slippage_percent) == "1.20"

    def test_a_yaml_float_arrives_by_its_shortest_repr_not_its_binary_value(self) -> None:
        """``0.1`` is ``0.1000000000000000055...`` as a float. The load boundary must give
        ``Decimal("0.1")``, which is the number the file says."""
        config = _config(fee_percent=0.1, slippage_percent=0.05, stop_slippage_percent=1.2)
        assert config.fee_percent == Decimal("0.1")
        binary_value = Decimal(float("0.1"))  # 0.1000000000000000055511151231257827...
        assert config.fee_percent != binary_value
        assert config.slippage_percent == Decimal("0.05")
        assert config.stop_slippage_percent == Decimal("1.2")

    def test_an_integer_balance_converts_exactly(self) -> None:
        config = _config(initial_balance=5000)
        assert config.initial_balance == Decimal(5000)
        assert type(config.initial_balance) is Decimal

    def test_a_percent_multiplies_money_without_a_conversion(self) -> None:
        """The reason for the type: 0.1% of a 200 USDT notional is exactly 0.2."""
        notional = Decimal("200")
        assert notional * _config().fee_percent / Decimal(100) == Decimal("0.2")

    @pytest.mark.parametrize("field", ("fee_percent", "slippage_percent", "stop_slippage_percent"))
    def test_a_percent_may_be_zero_but_not_negative(self, field: str) -> None:
        assert getattr(_config(**{field: 0}), field) == Decimal(0)
        with pytest.raises(ValidationError):
            _config(**{field: -0.01})

    def test_the_balance_must_be_positive(self) -> None:
        with pytest.raises(ValidationError):
            _config(initial_balance=0)
        with pytest.raises(ValidationError):
            _config(initial_balance=-1)

    @pytest.mark.parametrize("value", ("NaN", "Infinity", "-Infinity"))
    @pytest.mark.parametrize("field", _MONEY_FIELDS)
    def test_a_non_finite_value_is_refused(self, field: str, value: str) -> None:
        with pytest.raises(ValidationError):
            _config(**{field: Decimal(value)})

    def test_an_unknown_key_is_refused(self) -> None:
        """A typo such as ``slippage_pct`` must fail at load, not be ignored."""
        with pytest.raises(ValidationError):
            _config(slippage_pct=0.5)


class TestWhichStoredFiltersTheRunSizesWith:
    """``exchange_info_environment`` (P110 C3): mainnet files for a backtest on mainnet klines,
    the Testnet ones for S4, which replays what the bot did on Testnet."""

    def test_the_default_is_mainnet(self) -> None:
        assert _config().exchange_info_environment == "mainnet"

    def test_testnet_is_accepted(self) -> None:
        assert _config(exchange_info_environment="testnet").exchange_info_environment == "testnet"

    @pytest.mark.parametrize("bad", ["", "Testnet", "paper", "main", "mainnet "])
    def test_anything_else_is_refused_at_load(self, bad: str) -> None:
        with pytest.raises(ValidationError):
            _config(exchange_info_environment=bad)

    def test_it_names_exactly_the_environments_the_store_keeps(self) -> None:
        """The config cannot import ``backtesting`` (the layers run the other way), so the two
        lists are pinned equal here and a third environment added to one fails this."""
        assert get_args(BacktestConfig.model_fields["exchange_info_environment"].annotation) == (
            ENVIRONMENTS
        )


class TestTheWindowIsHalfOpenInUtcDates:
    def test_a_date_string_parses_to_a_date(self) -> None:
        config = _config(start_date="2024-01-01", end_date="2024-06-30")
        assert config.start_date == date(2024, 1, 1)
        assert config.end_date == date(2024, 6, 30)

    def test_the_window_instants_are_utc_midnights_and_aware(self) -> None:
        config = _config(start_date="2024-01-01", end_date="2024-01-02")
        assert config.window_start == datetime(2024, 1, 1, tzinfo=timezone.utc)
        assert config.window_end == datetime(2024, 1, 2, tzinfo=timezone.utc)
        assert config.window_start.tzinfo is timezone.utc
        assert config.window_end.utcoffset() == timedelta(0)

    def test_the_end_date_itself_is_not_in_the_window(self) -> None:
        """One day from 2024-01-01 to 2024-01-02 is exactly 24 hours: the 2nd is excluded."""
        config = _config(start_date="2024-01-01", end_date="2024-01-02")
        assert config.window_end - config.window_start == timedelta(hours=24)

    def test_a_leap_day_is_counted(self) -> None:
        config = _config(start_date="2024-02-28", end_date="2024-03-01")
        assert config.window_end - config.window_start == timedelta(days=2)

    def test_an_empty_window_is_refused(self) -> None:
        with pytest.raises(ValidationError, match="half-open"):
            _config(start_date="2024-01-01", end_date="2024-01-01")

    def test_a_reversed_window_is_refused(self) -> None:
        with pytest.raises(ValidationError, match="must be after start_date"):
            _config(start_date="2024-02-01", end_date="2024-01-01")

    @pytest.mark.parametrize("bad", ("2024-13-01", "2024-02-30", "yesterday", ""))
    def test_a_date_that_does_not_exist_is_refused(self, bad: str) -> None:
        with pytest.raises(ValidationError):
            _config(start_date=bad)

    def test_a_reassigned_window_is_checked_again(self) -> None:
        """``_Model`` validates assignment, so the window cannot be made empty after load."""
        config = _config(start_date="2024-01-01", end_date="2024-02-01")
        with pytest.raises(ValidationError):
            config.end_date = date(2023, 12, 31)


class TestTheShippedFileStillLoads:
    def test_the_committed_config_yaml_loads_with_exact_fields_and_a_181_day_window(self) -> None:
        """The repository's own ``config.yaml`` has a window of 2024-01-01 to 2024-06-30.

        M5m-036: that window disagrees with the ruled "all available history", and S2 sets
        the real window per run. This pins only that the file loads under the new types.
        """
        settings = get_settings(str(Path(__file__).resolve().parents[2] / "config.yaml"))
        backtesting = settings.config.backtesting
        assert type(backtesting.fee_percent) is Decimal
        assert backtesting.fee_percent == Decimal("0.1")
        assert backtesting.slippage_percent == Decimal("0.05")
        assert backtesting.initial_balance == Decimal("10000")
        assert backtesting.stop_slippage_percent == Decimal("1.20")
        assert backtesting.window_end - backtesting.window_start == timedelta(days=181)
