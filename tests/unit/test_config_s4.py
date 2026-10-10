"""``config.s4.yaml`` differs from ``config.yaml`` only under ``backtesting:`` (S4, P108 B3, P110 C3).

S4 compares the backtester with the venue (Testnet): one live run of the committed bot under the
committed ``config.yaml``, and one backtest of the same window over klines recorded from the same
venue. The backtest must size, stop and limit exactly as the live run did, so the second config
may differ from the first in the backtester's own section and nowhere else. Anything outside
``backtesting:`` that drifted would make the comparison a comparison of two different bots.

**BYTES, NOT ONLY MEANING.** The first test compares the two files line by line outside the
``backtesting:`` block, so a reworded comment, a reordered key or a changed risk number all fail
it, where a comparison of parsed YAML would pass a comment and a reorder. The second compares the
parsed trees, which is what the bot reads. The third pins WHICH keys under ``backtesting:`` differ
and to what, so the S4 parameters in the pre-registration are the ones the file holds.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any

import yaml

from trading_bot.config.settings import get_settings

REPO = Path(__file__).resolve().parents[2]
BASE = REPO / "config.yaml"
S4 = REPO / "config.s4.yaml"

#: Every key under ``backtesting:`` whose value in the S4 file differs from the base file, or that
#: the base file does not carry.
CHANGED_KEYS = frozenset(
    {
        "start_date",
        "end_date",
        "initial_balance",
        "fee_percent",
        "stop_slippage_percent",
        "data_dir",
        "exchange_info_environment",
    }
)


def outside_backtesting(path: Path) -> list[str]:
    """The file's lines with the top-level ``backtesting:`` block removed.

    The block starts at the line ``backtesting:`` and ends at the next line that begins in
    column 0 with a non-space, non-comment character (the next top-level key).
    """
    kept: list[str] = []
    inside = False
    for line in path.read_text(encoding="utf-8").split("\n"):
        if line.startswith("backtesting:"):
            inside = True
            continue
        if inside and line and not line.startswith((" ", "#")):
            inside = False
        if not inside:
            kept.append(line)
    return kept


def parsed(path: Path) -> dict[str, Any]:
    loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert isinstance(loaded, dict)
    return loaded


class TestTheTwoConfigsAgreeOutsideTheBacktester:
    def test_every_line_outside_the_backtesting_block_is_identical(self) -> None:
        base, s4 = outside_backtesting(BASE), outside_backtesting(S4)
        assert len(base) > 100, "the scan found too little of config.yaml to mean anything"
        assert s4 == base

    def test_the_parsed_trees_agree_on_every_other_section(self) -> None:
        base, s4 = parsed(BASE), parsed(S4)
        assert set(s4) == set(base)
        for section in base:
            if section != "backtesting":
                assert s4[section] == base[section], section

    def test_the_backtesting_keys_that_differ_are_exactly_the_s4_parameters(self) -> None:
        base, s4 = parsed(BASE)["backtesting"], parsed(S4)["backtesting"]
        differing = {key for key in s4 if s4[key] != base.get(key)}
        assert differing == set(CHANGED_KEYS)
        assert set(base) - set(s4) == set(), "S4 drops no key the base file sets"
        # The two the pre-registration states as gate values, and the one it leaves as the shipped.
        assert s4["fee_percent"] == 0
        assert s4["exchange_info_environment"] == "testnet"
        assert s4["data_dir"] == "data/historical_testnet"
        assert s4["slippage_percent"] == base["slippage_percent"]


class TestItLoadsAsTheBacktesterReadsIt:
    def test_it_loads_through_the_real_loader_with_the_s4_values(self) -> None:
        get_settings.cache_clear()
        window = get_settings(str(S4)).config.backtesting
        assert window.fee_percent == Decimal(0)
        assert window.slippage_percent == Decimal("0.05")
        assert window.stop_slippage_percent == Decimal("1.20")
        assert window.exchange_info_environment == "testnet"
        assert window.data_dir == "data/historical_testnet"
        assert window.initial_balance > 0
        assert window.end_date > window.start_date
        assert isinstance(window.start_date, date)

    def test_the_base_config_still_selects_mainnet_filters(self) -> None:
        get_settings.cache_clear()
        assert get_settings(str(BASE)).config.backtesting.exchange_info_environment == "mainnet"
