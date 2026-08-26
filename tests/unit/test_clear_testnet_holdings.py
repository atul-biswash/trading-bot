"""The clearing script's guards, pinned so an edit cannot quietly remove them.

**Why these exist rather than a comment.** ``scripts/clear_testnet_holdings.py``
places a real order, and its safety rests on a hardcoded ``testnet=True`` and on
never reading the live credential slot. Neither is visible to any gate this
project runs: ``ruff`` and ``mypy`` cannot tell a literal from a parameter, and
a future author adding ``--mode`` would break nothing they could see. These
tests are what make that break loud.

**No test here touches the network.** The client is a fake satisfying the
script's own ``TestnetAPI`` protocol, and the credential tests construct
``Secrets`` explicitly rather than reading ``.env``.
"""

from __future__ import annotations

import sys
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from trading_bot.config.settings import Secrets
from trading_bot.core.exceptions import ConfigError
from trading_bot.exchange.models import to_symbol_info

# `scripts/` is not a package and is outside `pythonpath`, so it is added here
# rather than restructured -- the script is a script, not library code.
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

import clear_testnet_holdings as clearer

D = Decimal

_LIVE_KEY = "live-key-must-never-be-read"
_LIVE_SECRET = "live-secret-must-never-be-read"
_TESTNET_KEY = "testnet-key"
_TESTNET_SECRET = "testnet-secret"


def _secrets(*, testnet: bool, live: bool) -> Secrets:
    """A ``Secrets`` with either slot populated, built without reading ``.env``."""
    return Secrets(
        binance_api_key=_LIVE_KEY if live else "",
        binance_api_secret=_LIVE_SECRET if live else "",
        binance_testnet_api_key=_TESTNET_KEY if testnet else "",
        binance_testnet_api_secret=_TESTNET_SECRET if testnet else "",
    )


class _FakeClient:
    """Records what it was constructed with; performs no I/O."""

    def __init__(self, **kwargs: Any) -> None:
        self.kwargs = kwargs
        self.testnet = bool(kwargs.get("testnet"))
        self.sold: list[dict[str, Any]] = []
        self.validated: list[dict[str, Any]] = []

    async def create_test_order(self, **params: Any) -> dict[str, Any]:
        self.validated.append(params)
        return {}

    async def order_market_sell(self, **params: Any) -> dict[str, Any]:
        self.sold.append(params)
        return {"status": "FILLED", "executedQty": params["quantity"], "orderId": 1}


def _factory(**overrides: Any) -> Any:
    """An ``AsyncClient.create`` stand-in that records its keyword arguments."""
    created: list[_FakeClient] = []

    async def create(**kwargs: Any) -> _FakeClient:
        client = _FakeClient(**{**kwargs, **overrides})
        created.append(client)
        return client

    create.created = created  # type: ignore[attr-defined]
    return create


# --------------------------------------------------------------------------
# R2: the client is testnet, and it is not a parameter
# --------------------------------------------------------------------------
class TestClientFactory:
    async def test_client_factory_passes_testnet_true(self) -> None:
        """The one construction hardcodes ``testnet=True``.

        This is the guard R2 rests on. It is a literal in the source, so nothing
        else in the toolchain can see it change.
        """
        create = _factory()
        client = await clearer.build_client(create, secrets=_secrets(testnet=True, live=True))

        assert client.testnet is True
        assert create.created[0].kwargs["testnet"] is True

    async def test_client_factory_refuses_a_client_that_is_not_testnet(self) -> None:
        """The post-construction check reads the client, not the argument.

        A library whose ``testnet`` flag did not take effect would otherwise be
        indistinguishable from one where it did.
        """
        create = _factory(testnet=False)
        with pytest.raises(ConfigError, match="does not report testnet=True"):
            await clearer.build_client(create, secrets=_secrets(testnet=True, live=True))


# --------------------------------------------------------------------------
# R2: the live credential slot is never read
# --------------------------------------------------------------------------
class TestCredentials:
    async def test_the_live_key_slot_is_never_read(self) -> None:
        """A blank testnet slot REFUSES; it does not fall back to the live keys.

        This is the behaviour that differs from
        ``Settings.binance_credentials()``, which reads ``binance_api_key`` in
        exactly this state. Selling with a live credential is the failure this
        script is shaped to make impossible.
        """
        with pytest.raises(ConfigError, match="testnet slot only"):
            clearer._testnet_credentials(_secrets(testnet=False, live=True))

    def test_the_testnet_pair_is_what_is_returned(self) -> None:
        """With both slots populated it takes the testnet one."""
        key, secret = clearer._testnet_credentials(_secrets(testnet=True, live=True))
        assert (key, secret) == (_TESTNET_KEY, _TESTNET_SECRET)

    def test_a_half_populated_testnet_slot_refuses(self) -> None:
        """A key with no secret cannot authenticate, so it is not credentials."""
        half = Secrets(binance_testnet_api_key=_TESTNET_KEY, binance_testnet_api_secret="")
        with pytest.raises(ConfigError):
            clearer._testnet_credentials(half)


# --------------------------------------------------------------------------
# The allowlist
# --------------------------------------------------------------------------
class TestSymbolValidation:
    def test_an_unknown_symbol_is_refused(self) -> None:
        with pytest.raises(ConfigError, match="refusing SOLUSDT"):
            clearer.validate_symbols(["SOLUSDT"])

    def test_an_unknown_symbol_refuses_the_whole_call(self) -> None:
        """One bad symbol refuses everything rather than silently selling the rest."""
        with pytest.raises(ConfigError, match="DOGEUSDT"):
            clearer.validate_symbols(["BTCUSDT", "DOGEUSDT"])

    def test_symbols_are_upper_cased_and_deduplicated(self) -> None:
        assert clearer.validate_symbols(["btcusdt", "BTCUSDT", "ethusdt"]) == [
            "BTCUSDT",
            "ETHUSDT",
        ]

    def test_an_empty_list_is_refused(self) -> None:
        with pytest.raises(ConfigError, match="--symbol is required"):
            clearer.validate_symbols([])


# --------------------------------------------------------------------------
# The sizing skips -- nothing is placed below a floor
# --------------------------------------------------------------------------
# CAPTURED shape, trimmed to the filters `to_symbol_info` reads. Values are
# MEASURED at M5g-025: MARKET_LOT_SIZE is present and ZEROED on BTCUSDT, so the
# effective step is the raw LOT_SIZE step.
# fmt: off
_BTCUSDT_INFO = {
    "symbol":     "BTCUSDT",
    "baseAsset":  "BTC",
    "quoteAsset": "USDT",
    "filters": [
        {"filterType": "PRICE_FILTER",
         "tickSize": "0.01000000"},
        {"filterType": "LOT_SIZE",
         "stepSize": "0.00001000", "minQty": "0.00001000", "maxQty": "9000.00000000"},
        {"filterType": "MARKET_LOT_SIZE",
         "stepSize": "0.00000000", "minQty": "0.00000000", "maxQty": "141.67845966"},
        {"filterType": "NOTIONAL",
         "minNotional": "5.00000000"},
    ],
}
# fmt: on


def _btc_info() -> Any:
    return to_symbol_info(_BTCUSDT_INFO)


class TestPlanSale:
    def test_a_zero_balance_plans_nothing(self) -> None:
        """Zero free base yields a zero quantity, which the caller skips."""
        quantity, remainder, dust = clearer.plan_sale(_btc_info(), free=D("0"), price=D("78770.01"))
        assert quantity == D("0")
        assert remainder == D("0")
        assert dust is True

    def test_a_sub_step_balance_rounds_to_zero(self) -> None:
        """Below one step there is nothing sellable, so nothing is planned."""
        quantity, remainder, _ = clearer.plan_sale(
            _btc_info(), free=D("0.000009"), price=D("78770.01")
        )
        assert quantity == D("0")
        assert remainder == D("0.000009")

    def test_the_remainder_is_dust_at_the_measured_filters(self) -> None:
        """M5g-030's arithmetic, pinned: the residue cannot block the symbol.

        One whole BTC leaves a residue strictly below one 0.00001 step, worth
        under 0.79 USDT against a 5.00 min_notional.
        """
        info = _btc_info()
        quantity, remainder, dust = clearer.plan_sale(info, free=D("1.000009"), price=D("78770.01"))
        assert quantity == D("1.00000")
        assert remainder == D("0.000009")
        assert remainder * D("78770.01") < info.min_notional
        assert dust is True

    def test_quantity_never_exceeds_the_free_balance(self) -> None:
        """Rounding is DOWN. Up would be unfillable."""
        free = D("0.123456789")
        quantity, _, _ = clearer.plan_sale(_btc_info(), free=free, price=D("78770.01"))
        assert quantity <= free


class TestSellParams:
    def test_a_small_quantity_is_not_rendered_in_scientific_notation(self) -> None:
        """``str(Decimal("0.00001"))`` is ``1E-5``, which the venue rejects."""
        params = clearer._sell_params("BTCUSDT", D("0.00001"))
        assert params["quantity"] == "0.00001"
        assert "E" not in params["quantity"]


class TestFreeBalance:
    def test_an_absent_asset_reads_zero(self) -> None:
        assert clearer.free_balance({"balances": []}, "BTC") == D("0")

    def test_the_balance_is_decimal_not_float(self) -> None:
        account = {"balances": [{"asset": "BTC", "free": "0.10000000", "locked": "0"}]}
        value = clearer.free_balance(account, "BTC")
        assert isinstance(value, Decimal)
        assert value == D("0.1")
