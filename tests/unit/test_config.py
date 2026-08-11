"""Tests for config loading, validation, and secret resolution."""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest
from pydantic import ValidationError

from trading_bot.config.models import (
    AppConfig,
    BacktestConfig,
    PairConfig,
    PositionSizingConfig,
    RiskConfig,
    StopLossConfig,
    StrategyConfig,
    TakeProfitConfig,
    TradingConfig,
    TrailingStopConfig,
)
from trading_bot.config.settings import get_settings
from trading_bot.core.enums import PositionSizingMethod, TakeProfitType, TradingMode
from trading_bot.core.exceptions import ConfigError


def test_loads_minimal_config(config_path: Path) -> None:
    settings = get_settings(str(config_path))
    assert settings.mode is TradingMode.TESTNET
    assert settings.config.strategy.name == "sma_crossover"
    assert settings.config.backtesting.initial_balance == 5000


class TestAssetNamesAreNormalised:
    """Both asset-naming fields upper-case at parse, not just one.

    ``PairConfig.symbol`` has done this since Phase 1; ``base_currency`` sat
    three lines below it unnormalised and unread until the composition root
    started matching it against ``Balance.asset``. The root normalises both
    sides itself, so this is defence in depth -- but the pair of them should
    behave the same way, and a test is what says so.
    """

    def test_base_currency_is_upper_cased(self) -> None:
        assert TradingConfig(base_currency="usdt").base_currency == "USDT"

    def test_base_currency_default_is_already_normalised(self) -> None:
        assert TradingConfig().base_currency == "USDT"

    def test_pair_symbol_is_upper_cased(self) -> None:
        assert PairConfig(symbol="btcusdt", timeframe="1m").symbol == "BTCUSDT"

    def test_a_timeframe_is_deliberately_not_case_folded(self) -> None:
        """``1M`` is one *month* on Binance and ``1m`` is one minute, so folding
        the case here would silently merge two different intervals."""
        assert PairConfig(symbol="BTCUSDT", timeframe="1M").timeframe == "1M"


def test_missing_config_file_raises() -> None:
    with pytest.raises(ConfigError):
        get_settings("does/not/exist.yaml")


def test_env_mode_override(config_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BOT_MODE", "paper")
    settings = get_settings(str(config_path))
    assert settings.mode is TradingMode.PAPER


def test_testnet_prefers_testnet_keys(config_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BINANCE_API_KEY", "live_key")
    monkeypatch.setenv("BINANCE_API_SECRET", "live_secret")
    monkeypatch.setenv("BINANCE_TESTNET_API_KEY", "tn_key")
    monkeypatch.setenv("BINANCE_TESTNET_API_SECRET", "tn_secret")
    settings = get_settings(str(config_path))
    key, secret = settings.binance_credentials()
    assert key == "tn_key"
    assert secret == "tn_secret"


def test_live_mode_without_keys_raises(config_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BOT_MODE", "live")
    monkeypatch.delenv("BINANCE_API_KEY", raising=False)
    monkeypatch.delenv("BINANCE_API_SECRET", raising=False)
    settings = get_settings(str(config_path))
    with pytest.raises(ConfigError):
        settings.binance_credentials()


def test_invalid_config_rejected(tmp_path: Path) -> None:
    bad = tmp_path / "config.yaml"
    # max_open_positions must be >= 1; unknown keys are also forbidden.
    bad.write_text(
        "mode: testnet\n"
        "strategy:\n  name: x\n"
        "backtesting:\n  start_date: '2024-01-01'\n  end_date: '2024-02-01'\n"
        "risk:\n  limits:\n    max_open_positions: 0\n",
        encoding="utf-8",
    )
    with pytest.raises(ConfigError):
        get_settings(str(bad))


class TestExitConfigDecimalBoundary:
    """The Phase 5 M2 exit-rule config fields convert ``float`` -> ``Decimal``
    exactly, once, here -- the same boundary already proven for position sizing.

    A YAML value such as ``1.005`` must become ``Decimal("1.005")``, not the
    binary expansion ``Decimal(1.005)`` gives, because these fields are later
    multiplied by money and ``Decimal * float`` raises ``TypeError``.
    """

    def test_stop_loss_fields_are_exact_decimals(self) -> None:
        # 1.005 is *not* exactly representable in binary, so it exposes the leak.
        from_yaml = 1.005  # what yaml.safe_load hands pydantic
        cfg = StopLossConfig(percent=2.0, atr_multiplier=from_yaml)
        assert cfg.percent == Decimal("2.0")
        assert cfg.atr_multiplier == Decimal("1.005")
        assert isinstance(cfg.percent, Decimal)
        assert isinstance(cfg.atr_multiplier, Decimal)
        assert cfg.atr_multiplier != Decimal(from_yaml)  # the binary-float leak avoided
        assert isinstance(cfg.atr_period, int)  # a lookback, deliberately not Decimal

    def test_take_profit_fields_are_exact_decimals(self) -> None:
        cfg = TakeProfitConfig(percent=4.0, rr_multiple=1.5)
        assert cfg.percent == Decimal("4.0")
        assert cfg.rr_multiple == Decimal("1.5")
        assert isinstance(cfg.percent, Decimal)
        assert isinstance(cfg.rr_multiple, Decimal)

    def test_trailing_stop_fields_are_exact_decimals(self) -> None:
        cfg = TrailingStopConfig(activation_percent=1.0, trail_percent=0.75)
        assert cfg.activation_percent == Decimal("1.0")
        assert cfg.trail_percent == Decimal("0.75")
        assert isinstance(cfg.activation_percent, Decimal)
        assert isinstance(cfg.trail_percent, Decimal)

    def test_positivity_constraints_survive_the_type_change(self) -> None:
        for bad in (0, -0.1):
            with pytest.raises(ValueError, match="percent"):
                StopLossConfig(percent=bad)
            with pytest.raises(ValueError, match="rr_multiple"):
                TakeProfitConfig(rr_multiple=bad)
            with pytest.raises(ValueError, match="trail_percent"):
                TrailingStopConfig(trail_percent=bad)


class TestRiskConfigCoherence:
    """A stop distance that a disabled stop-loss never produces is rejected at
    load, not hours later on the first signal."""

    def test_defaults_are_coherent(self) -> None:
        RiskConfig()  # stop enabled, take-profit percent, fixed_fraction sizing

    def test_rr_take_profit_without_a_stop_is_rejected(self) -> None:
        with pytest.raises(ValueError, match="take_profit"):
            RiskConfig(
                stop_loss=StopLossConfig(enabled=False),
                take_profit=TakeProfitConfig(type=TakeProfitType.RR),
            )

    def test_risk_per_trade_sizing_without_a_stop_is_rejected(self) -> None:
        with pytest.raises(ValueError, match="risk_per_trade"):
            RiskConfig(
                stop_loss=StopLossConfig(enabled=False),
                position_sizing=PositionSizingConfig(method=PositionSizingMethod.RISK_PER_TRADE),
            )

    def test_rr_take_profit_with_a_stop_is_allowed(self) -> None:
        RiskConfig(
            stop_loss=StopLossConfig(enabled=True),
            take_profit=TakeProfitConfig(type=TakeProfitType.RR),
        )

    def test_a_take_profit_with_no_stop_is_refused_as_a_judgement(self) -> None:
        """This configuration was ALLOWED until now, and the assertion is
        inverted rather than deleted so the change of mind stays visible.

        Nothing downstream became unable to compute it -- a percent target needs
        no stop distance, which is why it was legal. It is refused because the
        payoff shape is adversely lopsided: winners truncated, losers unbounded.
        """
        with pytest.raises(ValueError, match="JUDGEMENT about payoff shape"):
            RiskConfig(
                stop_loss=StopLossConfig(enabled=False),
                take_profit=TakeProfitConfig(type=TakeProfitType.PERCENT),
            )

    def test_the_refusal_does_not_blame_the_exchange_or_a_filter(self) -> None:
        """The message must name the opinion as ours. An operator who reads it as
        an exchange constraint will go looking for a filter that does not exist.
        """
        with pytest.raises(ValueError) as excinfo:
            RiskConfig(
                stop_loss=StopLossConfig(enabled=False),
                take_profit=TakeProfitConfig(type=TakeProfitType.PERCENT),
            )
        message = str(excinfo.value)
        assert "made by this project" in message
        assert "the exchange accepts this configuration" in message
        assert "no filter forbids it" in message

    def test_disabling_both_is_still_supported(self) -> None:
        """`SignalAction.CLOSE` exists so a strategy can own its exits, and that
        style is deliberately preserved -- so the refusal keys on take-profit
        WITH no stop, never on the absence of a stop alone.
        """
        RiskConfig(
            stop_loss=StopLossConfig(enabled=False),
            take_profit=TakeProfitConfig(enabled=False),
        )

    def test_a_trailing_stop_without_a_stop_loss_is_refused(self) -> None:
        """A trailing stop is a CLIENT-SIDE level with no venue counterpart.

        Q-C section 3 fixes the order list at three legs -- the working
        ``LIMIT``, ``STOP_LOSS`` and ``TAKE_PROFIT`` -- and section 5 retains
        the trailing fields "pending the trailing milestone".
        ``advance_trailing_stop`` has no call site in ``src/`` at all. So with
        no stop leg nothing rests at the exchange, and the position is protected
        only while this process is alive and evaluating.

        Refused at load rather than corrected in prose: the locked claim that
        stops-off degrades the committed-risk check to realised-only is true
        again because this configuration can no longer be built.

        Take-profit must also be disabled to reach this check -- with it enabled
        the third refusal fires first. That is deliberate, not incidental.
        """
        with pytest.raises(ValueError, match=r"trailing_stop\.enabled is true"):
            RiskConfig(
                stop_loss=StopLossConfig(enabled=False),
                take_profit=TakeProfitConfig(enabled=False),
                trailing_stop=TrailingStopConfig(enabled=True),
            )

    def test_both_disabled_with_no_trail_is_still_accepted(self) -> None:
        """The fourth check's counterpart to `test_disabling_both_is_still_supported`.

        It keys on the trailing stop WITH no stop-loss, never on the absence of
        a stop alone. Broadening it to the latter would swallow the
        owns-their-exits style that `SignalAction.CLOSE` exists to support, and
        that style is locked as reachable.
        """
        RiskConfig(
            stop_loss=StopLossConfig(enabled=False),
            take_profit=TakeProfitConfig(enabled=False),
            trailing_stop=TrailingStopConfig(enabled=False),
        )

    def test_the_two_price_fields_are_decimal_and_the_three_durations_are_not(self) -> None:
        """The money rule applied field by field, not uniformly. A field becomes
        `Decimal` at the milestone that first multiplies it by money OR compares
        it against money; a duration compared against a clock does neither, and
        typing it `Decimal` would buy nothing and cost a conversion at every
        asyncio call site.
        """
        risk = RiskConfig()
        assert isinstance(risk.max_entry_slippage, Decimal)
        assert isinstance(risk.price_band_margin, Decimal)
        assert isinstance(risk.max_position_staleness_s, float)
        assert isinstance(risk.dispatch_deadline_s, float)
        assert isinstance(risk.reconcile_deadline_s, float)

    def test_max_entry_slippage_is_a_fraction_parsed_exactly(self) -> None:
        """`0.001` is 0.1%, not 0.1 -- the entry formula is
        `close x (1 + slippage)`. Parsed through the shortest-repr boundary, so
        it is exactly 1/1000 rather than a binary approximation of it.
        """
        assert RiskConfig().max_entry_slippage == Decimal("0.001")
        assert RiskConfig().max_entry_slippage * Decimal("1000") == Decimal("1")

    @pytest.mark.parametrize("value", [Decimal("0"), Decimal("-0.001"), Decimal("0.06")])
    def test_max_entry_slippage_is_bounded_at_both_ends(self, value: Decimal) -> None:
        """The upper bound is what stops the config expressing "market order in
        disguise"; near it the price is band-refusable and the whole list dies.
        """
        with pytest.raises(ValidationError):
            RiskConfig(max_entry_slippage=value)

    @pytest.mark.parametrize(
        "field",
        ["max_position_staleness_s", "dispatch_deadline_s", "reconcile_deadline_s"],
    )
    def test_every_duration_must_be_positive(self, field: str) -> None:
        with pytest.raises(ValidationError):
            RiskConfig(**{field: 0.0})

    def test_the_shipped_safety_defaults(self) -> None:
        """Pinned so a change to any of them is a visible diff rather than a
        silent drift. All five are PLACEHOLDER -- NOT MEASURED.
        """
        risk = RiskConfig()
        assert risk.max_entry_slippage == Decimal("0.001")
        assert risk.price_band_margin == Decimal("0.02")
        assert risk.max_position_staleness_s == 180.0
        assert risk.dispatch_deadline_s == 9.0
        assert risk.reconcile_deadline_s == 3.0

    def test_the_rr_case_keeps_its_more_specific_message(self) -> None:
        """`rr` with no stop is a strict subset of take-profit-with-no-stop, so
        it is checked first. Checked second it would be unreachable, and the
        operator would lose the reason their target cannot be computed at all.
        """
        with pytest.raises(ValueError, match="sizes the target from the stop distance"):
            RiskConfig(
                stop_loss=StopLossConfig(enabled=False),
                take_profit=TakeProfitConfig(type=TakeProfitType.RR),
            )


def _app_config(
    *,
    pairs: list[tuple[str, str]] | None = None,
    risk: RiskConfig | None = None,
) -> AppConfig:
    """An AppConfig carrying only what the coherence constraint reads."""
    return AppConfig(
        strategy=StrategyConfig(name="sma_crossover"),
        backtesting=BacktestConfig(start_date="2024-01-01", end_date="2024-02-01"),
        trading=TradingConfig(pairs=[PairConfig(symbol=s, timeframe=t) for s, t in (pairs or [])]),
        risk=risk or RiskConfig(),
    )


class TestDispatchBudgetCoherence:
    """`P_sim x D + N_max x T_recon <= alpha x T_min`, enforced at config load.

    On AppConfig rather than RiskConfig, because two of the five terms come from
    `trading.pairs`, which RiskConfig cannot see.
    """

    def test_the_shipped_shape_passes_with_margin(self) -> None:
        """2 x 9.0 + 3 x 3.0 = 27.0 against a 30.0s budget -- 3.0s spare, and
        1.5s under the 10.5s ceiling the constraint admits for the deadline.
        """
        _app_config(pairs=[("BTCUSDT", "1m"), ("ETHUSDT", "5m")])

    def test_a_third_simultaneous_pair_is_refused(self) -> None:
        """What makes adding a pair a decision rather than a silent degradation:
        3 x 9.0 + 3 x 3.0 = 36.0 against the same 30.0s budget.
        """
        with pytest.raises(ValidationError, match="exceeds 50%"):
            _app_config(pairs=[("BTCUSDT", "1m"), ("ETHUSDT", "1m"), ("SOLUSDT", "1m")])

    def test_the_refusal_names_all_four_inputs_and_a_remedy(self) -> None:
        """An operator must be able to see which number to change without
        re-deriving the constraint.
        """
        with pytest.raises(ValidationError) as excinfo:
            _app_config(pairs=[("BTCUSDT", "1m"), ("ETHUSDT", "1m"), ("SOLUSDT", "1m")])
        message = str(excinfo.value)
        assert "risk.dispatch_deadline_s = 9.0" in message
        assert "risk.reconcile_deadline_s = 3.0" in message
        assert "max_open_positions = 3" in message
        assert "BTCUSDT/1m = 60s" in message
        assert "Lower risk.dispatch_deadline_s" in message

    def test_a_longer_shortest_timeframe_admits_the_same_deadline(self) -> None:
        """T_min is the SHORTEST enabled timeframe, so the same three pairs fit
        once none of them is on a 1-minute bar: budget 150s against 36.0s.
        """
        _app_config(pairs=[("BTCUSDT", "5m"), ("ETHUSDT", "5m"), ("SOLUSDT", "15m")])

    def test_zero_enabled_pairs_is_vacuous_here_and_refused_at_boot(self) -> None:
        """NOT an oversight, and not to be "fixed" into a refusal.

        There is no pipeline to overrun and T_min is undefined rather than zero.
        `engine.modes.live_system` already refuses an empty enabled-pair set at
        BOOT, with a message about the operational consequence. Refusing here
        too would give one configuration two different errors depending on which
        check ran first, and would move a boot refusal into config load where
        `main.py` reports it differently.

        This is also the case that would break every config-loading test in the
        suite: `tests/conftest.py` writes no `trading:` key at all, so `pairs`
        falls to its default empty list on every one of them.
        """
        _app_config(pairs=[])

    def test_disabled_pairs_do_not_count_toward_p_sim(self) -> None:
        """`P_sim` is pairs whose bars can close in the same instant, and a
        disabled pair never closes a bar at all.
        """
        config = AppConfig(
            strategy=StrategyConfig(name="sma_crossover"),
            backtesting=BacktestConfig(start_date="2024-01-01", end_date="2024-02-01"),
            trading=TradingConfig(
                pairs=[
                    PairConfig(symbol="BTCUSDT", timeframe="1m"),
                    PairConfig(symbol="ETHUSDT", timeframe="1m"),
                    PairConfig(symbol="SOLUSDT", timeframe="1m", enabled=False),
                ]
            ),
        )
        assert len(config.trading.enabled_pairs) == 2

    def test_the_shipped_config_yaml_passes_its_own_constraint(self) -> None:
        """The file this repository ships must load. Nothing else in the suite
        reads it -- every other test writes its own -- so without this the
        shipped defaults could drift out of coherence unnoticed.
        """
        settings = get_settings(str(Path(__file__).resolve().parents[2] / "config.yaml"))
        assert settings.config.risk.dispatch_deadline_s == 9.0


# --------------------------------------------------------------------------
# Assignment guard: config is loaded once and never mutated
# --------------------------------------------------------------------------
class TestConfigIsImmutableInPractice:
    """``validate_assignment`` turns "config is never mutated after load" from a
    convention into an enforced property.

    That convention is load-bearing: it is the reason a ``Decimal`` config field
    is safe despite the models being mutable. A float written into one would flow
    into ``move_pct < config.activation_percent`` and decide a trailing stop
    *without raising*, because ``Decimal < float`` compares silently.
    """

    def test_a_float_assigned_to_a_decimal_field_is_coerced_by_shortest_repr(self) -> None:
        """Config fields are plain ``Decimal``, **not** ``Money``, so assignment
        coerces rather than rejecting -- and it coerces the safe way.

        ``0.1`` becomes ``Decimal("0.1")``, not the binary expansion
        ``Decimal(0.1)`` would give. Without ``validate_assignment`` the float
        would simply be stored as a ``float``, and then
        ``move_pct < config.activation_percent`` would compare against
        ``0.1000000000000000055…`` silently, because ``Decimal < float`` does not
        raise. The guard is what converts it at the boundary instead.
        """
        config = TrailingStopConfig()
        config.activation_percent = 0.1  # type: ignore[assignment]

        # Bound to a name rather than written inline: `Decimal(<float literal>)`
        # is the anti-pattern this project forbids outright (ruff RUF032), and it
        # appears here only as the value being asserted *against*.
        naive = 0.1
        assert isinstance(config.activation_percent, Decimal)
        assert config.activation_percent == Decimal("0.1")
        assert config.activation_percent != Decimal(naive)  # the binary expansion
        assert format(config.activation_percent, ".30f") == "0.100000000000000000000000000000"

    def test_a_valid_decimal_assignment_is_kept_exact(self) -> None:
        config = TrailingStopConfig()
        config.activation_percent = Decimal("2.50")
        assert config.activation_percent == Decimal("2.50")
        assert str(config.activation_percent) == "2.50"  # exponent preserved

    def test_an_out_of_range_assignment_is_rejected(self) -> None:
        """Field constraints apply on assignment too, not only at construction.
        Without the guard, ``gt=0`` holds at load and never again."""
        config = TrailingStopConfig()
        with pytest.raises(ValidationError):
            config.activation_percent = Decimal("-1")

    def test_a_typo_on_assignment_is_rejected(self) -> None:
        """``extra="forbid"`` catches a misspelled key in ``config.yaml``; this
        catches the same typo made in code against a loaded config."""
        config = TrailingStopConfig()
        with pytest.raises(ValidationError, match="has no attribute"):
            config.activaton_percent = Decimal("1")  # type: ignore[attr-defined]
