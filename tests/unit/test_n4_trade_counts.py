"""``scripts/n4_trade_counts.py``: the counts it prints, the scan that guards them, and what it refuses.

The script runs the real backtester, so the end-to-end tests build the 1m world of
``tests/unit/d1_world.py`` and point the script at it. The committed window ends at 2024-01-01 and the
test world is March 2024, so those tests move the script's two window constants to the world's span, as
they must; the last group pins that the constants are otherwise exactly the committed ones. The six
candidates are replaced by one scripted strategy with a fixed schedule, so each expected line is a
function of the literals that build the world:

BTCUSDT and ETHUSDT on 4h, 2024-03-01 to 2024-03-04. Both signal on the 00:00 bar and enter on the
04:00 bar; BTCUSDT signals again on the 04:00 bar (refused, it is in position) and on 2024-03-02T00:00,
which enters on the 04:00 bar of day two and is still open at the end. BTCUSDT's first position falls
to a gapped open at minute 700 and ETHUSDT's touches its trail at minute 1000. So BTCUSDT counts 3
signals, 1 trade, 1 open, 2 entries filled and one ``limit_refused``; ETHUSDT 1 signal and 1 trade.
"""

from __future__ import annotations

import builtins
import hashlib
import io
import logging
import re
import sys
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

import pytest

from tests.unit.d1_world import (
    TOUCH,
    FixedD1,
    Minute,
    ScriptedD1,
    build_minutes,
    flat,
    make_settings,
)
from trading_bot.backtesting import engine
from trading_bot.data.historical import HistoricalStore
from trading_bot.strategies import registry

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

import n4_trade_counts as n4

UTC = timezone.utc
STAGES = [
    "unknown_pair",
    "no_reference_price",
    "nothing_to_close",
    "unsupported_action",
    "no_mark_price",
    "position_stale",
    "committed_risk_unknown",
    "limit_refused",
    "live_order_list",
    "unmanaged_holding",
    "atr_unavailable",
    "stop_unplaceable",
    "size_not_tradeable",
    "unaffordable",
]


RULES = [
    "no_mark_price",
    "no_equity",
    "daily_loss_halt",
    "already_in_position",
    "cooldown",
    "max_open_positions",
]
HEADER = "N5 trade counts (R-DT-3d to R-DT-3f outputs only)"


def refusals(symbol: str, **counts: int) -> str:
    return f"  {symbol} refusals " + " ".join(f"{s}={counts.get(s, 0)}" for s in STAGES)


def rules(symbol: str, **counts: int) -> str:
    return f"  {symbol} rules " + " ".join(f"{r}={counts.get(r, 0)}" for r in RULES)


def outcomes(symbol: str, filled: int = 0, fok: int = 0, expired: int = 0, short: int = 0) -> str:
    return (
        f"  {symbol} entry_outcomes filled={filled} fok_refused={fok} expired={expired}"
        f" unaffordable={short}"
    )


EXPECTED_BODY = [
    HEADER,
    "window [2024-03-01, 2024-03-04)",
    "candidate C1 d1_fixed (4h)",
    "  run complete=yes problems=0",
    "  BTCUSDT signals=3 trades=1 open_at_end=1 clamp_upper=0 clamp_lower=0 size_capped=0",
    refusals("BTCUSDT", limit_refused=1),
    rules("BTCUSDT", already_in_position=1),
    outcomes("BTCUSDT", filled=2),
    "  BTCUSDT delta_bps n=3 p10=500 p25=500 p50=500 p75=500 p90=500 min=500 max=500",
    "  ETHUSDT signals=1 trades=1 open_at_end=0 clamp_upper=0 clamp_lower=0 size_capped=0",
    refusals("ETHUSDT"),
    rules("ETHUSDT"),
    outcomes("ETHUSDT", filled=1),
    "  ETHUSDT delta_bps n=1 p10=500 p25=500 p50=500 p75=500 p90=500 min=500 max=500",
]


class World:
    """The 4h scenario on disk, with the script's window moved to its span."""

    def __init__(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setitem(registry._REGISTRY, "d1_fixed", FixedD1)
        monkeypatch.setattr(n4, "CANDIDATES", (("C1", "d1_fixed", "4h"),))
        monkeypatch.setattr(n4, "IN_SAMPLE_START", datetime(2024, 3, 1, tzinfo=UTC))
        monkeypatch.setattr(n4, "IN_SAMPLE_END", datetime(2024, 3, 4, tzinfo=UTC))
        self.root = tmp_path / "hist"
        paths = {"BTCUSDT": {700: flat("90")}, "ETHUSDT": {1000: TOUCH}}
        for symbol, minutes in paths.items():
            build_minutes(self.root, symbol, count=4320, minutes=minutes, decision="4h")
        settings = make_settings(
            tmp_path,
            self.root,
            pairs=[("BTCUSDT", "4h"), ("ETHUSDT", "4h")],
            strategy="d1_fixed",
            params={},
            start="2024-03-01",
            end="2024-03-04",
        )
        self.config = str(settings.config_path)
        self.tmp = tmp_path

    def run(self, *extra: str) -> tuple[int, str]:
        out = io.StringIO()
        code = n4.main(
            ["--config", self.config, "--data-dir", self.root.as_posix(), *extra], out=out
        )
        return code, out.getvalue()


@pytest.fixture
def world(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> World:
    return World(tmp_path, monkeypatch)


GAP_UP: Minute = ("120", "120", "120", "120", "1")
OUTCOME_SIGNALS = [
    "2024-03-01T00:00",
    "2024-03-01T08:00",
    "2024-03-01T20:00",
    "2024-03-02T08:00",
    "2024-03-02T20:00",
    "2024-03-03T08:00",
]


def outcomes_strategy(delta: int) -> type[ScriptedD1]:
    """A fixed schedule at ``delta``: the script re-resolves the strategy by name with no parameters."""

    class Outcomes(ScriptedD1):
        name = "d1_outcomes"

        def __init__(self) -> None:
            super().__init__(buy={"BTCUSDT": OUTCOME_SIGNALS}, delta=delta)

    return Outcomes


class OutcomesWorld(World):
    """BTCUSDT signals six times on 4h bars, N5 sizing, and every entry meets a different end.

    Bars are numbered from 2024-03-01T00:00, 240 minutes each. The signals on bars 0 and 2 fill on the
    next bar, which OPENS at 120 against a limit of 100.10, so both are FOK-refused (2). The signals on
    bars 5, 8 and 11 meet a next slot the archive lacks (decision slots 6, 9 and 12 are omitted), so all
    three EXPIRE (3). The signal on bar 14 fills on bar 15 and the position is still open at the end (1).
    No entry is unaffordable (0). The four counts are therefore DISTINCT, so a field mapped to the wrong
    outcome cannot print the right line. ETHUSDT has no signal. The trail is ``delta`` basis points.
    """

    def __init__(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, *, delta: int) -> None:
        monkeypatch.setitem(registry._REGISTRY, "d1_outcomes", outcomes_strategy(delta))
        monkeypatch.setattr(n4, "CANDIDATES", (("C1", "d1_outcomes", "4h"),))
        monkeypatch.setattr(n4, "IN_SAMPLE_START", datetime(2024, 3, 1, tzinfo=UTC))
        monkeypatch.setattr(n4, "IN_SAMPLE_END", datetime(2024, 3, 4, tzinfo=UTC))
        self.root = tmp_path / "hist"
        build_minutes(
            self.root,
            "BTCUSDT",
            count=4320,
            minutes={240: GAP_UP, 720: GAP_UP},
            decision="4h",
            omit_decisions=frozenset({6, 9, 12}),
        )
        build_minutes(self.root, "ETHUSDT", count=4320, decision="4h")
        settings = make_settings(
            tmp_path,
            self.root,
            pairs=[("BTCUSDT", "4h"), ("ETHUSDT", "4h")],
            strategy="d1_outcomes",
            params={},
            start="2024-03-01",
            end="2024-03-04",
            n5=True,
        )
        self.config = str(settings.config_path)
        self.tmp = tmp_path


def outcome_body(delta: int, capped: int) -> list[str]:
    return [
        HEADER,
        "window [2024-03-01, 2024-03-04)",
        "candidate C1 d1_outcomes (4h)",
        "  run complete=yes problems=0",
        f"  BTCUSDT signals=6 trades=0 open_at_end=1 clamp_upper=0 clamp_lower=0 size_capped={capped}",
        refusals("BTCUSDT"),
        rules("BTCUSDT"),
        outcomes("BTCUSDT", filled=1, fok=2, expired=3, short=0),
        f"  BTCUSDT delta_bps n=6 p10={delta} p25={delta} p50={delta} p75={delta} p90={delta}"
        f" min={delta} max={delta}",
        "  ETHUSDT signals=0 trades=0 open_at_end=0 clamp_upper=0 clamp_lower=0 size_capped=0",
        refusals("ETHUSDT"),
        rules("ETHUSDT"),
        outcomes("ETHUSDT"),
        "  ETHUSDT delta_bps n=0",
    ]


class TestEveryEntryOutcomeIsPrintedUnderItsOwnName:
    """Closes the hole `M5n-149` named: no earlier world had a non-zero FOK-refused or expired entry,
    so a swap of the two printed the same zeros. Here the four outcomes are 1, 2, 3 and 0."""

    @pytest.mark.parametrize(("delta", "capped"), [(10, 6), (1000, 0)])
    def test_filled_fok_refused_and_expired_are_distinct_and_in_their_fields(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, delta: int, capped: int
    ) -> None:
        code, text = OutcomesWorld(tmp_path, monkeypatch, delta=delta).run()
        assert code == 0, text
        body = outcome_body(delta, capped)
        assert text.splitlines()[: len(body)] == body
        # The three omitted decision slots each log a missing-bar warning, which the script keeps,
        # scans and never shows: three records, and the scan stays CLEAN.
        assert f"scan verdict=CLEAN output_lines={len(body)} log_records=3" in text.splitlines()

    def test_the_cap_count_is_the_entries_queued_and_not_the_signals_or_the_fills(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Six entries are queued, one fills, five do not, and all six were sized at the cap."""
        _, text = OutcomesWorld(tmp_path, monkeypatch, delta=10).run()
        signals_line = next(line for line in text.splitlines() if "BTCUSDT signals=" in line)
        assert signals_line.endswith("size_capped=6")

    def test_the_outcomes_map_to_the_executors_results_by_pair(self) -> None:
        """Four distinct counts for one pair and a different four for the other, through
        `_pair_counts` with a fake executor, so no field can borrow another's source."""
        from collections import Counter
        from types import SimpleNamespace

        from trading_bot.backtesting.d1_executor import SymbolTally
        from trading_bot.backtesting.simulated_executor import EntryResult

        def attempts(symbol: str, filled: int, fok: int, expired: int, short: int) -> list[Any]:
            plan = (
                (EntryResult.FILLED, filled),
                (EntryResult.REFUSED, fok),
                (EntryResult.EXPIRED, expired),
                (EntryResult.UNAFFORDABLE, short),
            )
            return [SimpleNamespace(symbol=symbol, result=r) for r, n in plan for _ in range(n)]

        executor: Any = SimpleNamespace(
            tallies={
                "BTCUSDT": SymbolTally(signals=20, size_capped=6, deltas=[500]),
                "ETHUSDT": SymbolTally(signals=9, size_capped=1, deltas=[700]),
            },
            attempts=attempts("BTCUSDT", 5, 2, 3, 4) + attempts("ETHUSDT", 1, 7, 8, 9),
        )
        trades = Counter({"BTCUSDT": 7, "ETHUSDT": 1})
        btc = n4._pair_counts("BTCUSDT", executor, trades, {"BTCUSDT"})
        eth = n4._pair_counts("ETHUSDT", executor, trades, set())
        assert (btc.entries_filled, btc.fok_refused, btc.expired, btc.unaffordable) == (5, 2, 3, 4)
        assert (eth.entries_filled, eth.fok_refused, eth.expired, eth.unaffordable) == (1, 7, 8, 9)
        assert (btc.size_capped, eth.size_capped) == (6, 1)
        assert (btc.trades, btc.open_at_end, eth.open_at_end) == (7, 1, 0)
        result = n4.CandidateCounts("C1", "donchian_1d_20", "1d", True, 0, (btc, eth))
        lines = n4.render((date(2024, 3, 1), date(2024, 3, 4)), [result])
        assert outcomes("BTCUSDT", filled=5, fok=2, expired=3, short=4) in lines
        assert outcomes("ETHUSDT", filled=1, fok=7, expired=8, short=9) in lines


class TestTheRun:
    def test_the_output_is_exactly_the_schema(self, world: World) -> None:
        code, text = world.run()
        assert code == 0, text
        lines = text.splitlines()
        assert lines[: len(EXPECTED_BODY)] == EXPECTED_BODY
        assert lines[len(EXPECTED_BODY)] == "scan verdict=CLEAN output_lines=14 log_records=0"
        assert len(lines) == len(EXPECTED_BODY) + 2

    def test_the_last_line_is_the_hash_of_every_line_before_it(self, world: World) -> None:
        _, text = world.run()
        *body, last = text.splitlines()
        digest = hashlib.sha256("".join(f"{line}\n" for line in body).encode("ascii"))
        assert last == f"output_sha256={digest.hexdigest()}"

    def test_the_output_has_no_decimal_point_and_no_money_word(self, world: World) -> None:
        _, text = world.run()
        assert text.isascii()
        assert not re.search(r"\d\.\d", text)
        assert not re.search(
            r"price|return|equity|balance|realis|profit|pnl",
            text.replace("no_mark_price", "")
            .replace("no_reference_price", "")
            .replace("no_equity", ""),
            re.I,
        )

    def test_two_runs_print_the_same_bytes(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        texts = []
        for name in ("a", "b"):
            sub = tmp_path / name
            sub.mkdir()
            texts.append(World(sub, monkeypatch).run()[1])
        assert texts[0] == texts[1]

    def test_it_writes_no_run_record_and_no_trade_file(
        self, world: World, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def refuse(*args: Any, **kwargs: Any) -> None:
            raise AssertionError("write_run was called")

        monkeypatch.setattr(engine, "write_run", refuse)
        before = sorted(p.relative_to(world.tmp).as_posix() for p in world.tmp.rglob("*"))
        code, _ = world.run()
        after = sorted(p.relative_to(world.tmp).as_posix() for p in world.tmp.rglob("*"))
        assert code == 0
        assert after == before

    def test_it_opens_no_file_for_writing(
        self, world: World, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        real_open = builtins.open
        written: list[str] = []

        def watching(file: Any, mode: str = "r", *args: Any, **kwargs: Any) -> Any:
            if any(flag in mode for flag in "wax+"):
                written.append(str(file))
            return real_open(file, mode, *args, **kwargs)

        monkeypatch.setattr(builtins, "open", watching)
        code, _ = world.run()
        assert code == 0
        assert written == []

    def test_nothing_the_run_logs_reaches_a_handler_or_a_terminal(
        self, world: World, capfd: pytest.CaptureFixture[str]
    ) -> None:
        spy_stream = io.StringIO()
        spy = logging.StreamHandler(spy_stream)
        spy.setLevel(logging.DEBUG)
        root = logging.getLogger()
        before_level = root.level
        root.addHandler(spy)
        try:
            code, _ = world.run()
            assert code == 0
            assert spy_stream.getvalue() == ""
            assert spy in root.handlers
            assert root.level == before_level
        finally:
            root.removeHandler(spy)
        captured = capfd.readouterr()
        assert captured.err == ""

    def test_a_warning_logged_during_the_run_is_kept_and_counted_and_never_shown(
        self,
        world: World,
        monkeypatch: pytest.MonkeyPatch,
        capfd: pytest.CaptureFixture[str],
    ) -> None:
        real = n4.run_candidate

        async def chatty(*args: Any, **kwargs: Any) -> Any:
            logging.getLogger("probe").warning("BTCUSDT/4h: 1 bar(s) missing between a and b")
            return await real(*args, **kwargs)

        monkeypatch.setattr(n4, "run_candidate", chatty)
        spy_stream = io.StringIO()
        spy = logging.StreamHandler(spy_stream)
        root = logging.getLogger()
        root.addHandler(spy)
        try:
            code, text = world.run()
        finally:
            root.removeHandler(spy)
        assert code == 0, text
        assert "scan verdict=CLEAN output_lines=14 log_records=1" in text.splitlines()
        assert spy_stream.getvalue() == ""
        assert capfd.readouterr().err == ""

    def test_a_narrower_window_is_accepted_and_named(self, world: World) -> None:
        code, text = world.run("--start", "2024-03-02")
        assert code == 0, text
        assert "window [2024-03-02, 2024-03-04)" in text.splitlines()

    def test_a_run_that_is_not_complete_says_so_and_exits_one(
        self, world: World, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from tests.unit.d1_world import BrokenD1

        monkeypatch.setitem(registry._REGISTRY, "d1_fixed", BrokenD1)
        code, text = world.run()
        assert code == 1
        assert "  run complete=no problems=" in text
        assert "scan verdict=CLEAN" in text


class TestTheQuantiles:
    def test_nearest_rank_on_ten_values(self) -> None:
        values = list(range(1, 11))
        assert [n4.quantile(values, p) for p in n4.QUANTILES] == [1, 3, 5, 8, 9]

    def test_a_single_value_is_every_quantile(self) -> None:
        assert [n4.quantile([700], p) for p in n4.QUANTILES] == [700] * 5

    def test_the_line_sorts_its_values_and_prints_the_extremes(self) -> None:
        pair = n4.PairCounts(
            symbol="BTCUSDT",
            signals=4,
            trades=0,
            open_at_end=0,
            entries_filled=0,
            fok_refused=0,
            expired=0,
            unaffordable=0,
            clamp_upper=0,
            clamp_lower=0,
            size_capped=0,
            refusals=(),
            rules=(),
            deltas=(30, 10, 40, 20),
        )
        result = n4.CandidateCounts("C1", "donchian_1d_20", "1d", True, 0, (pair,))
        lines = n4.render((date(2024, 3, 1), date(2024, 3, 4)), [result])
        assert lines[-1] == (
            "  BTCUSDT delta_bps n=4 p10=10 p25=10 p50=20 p75=30 p90=40 min=10 max=40"
        )


class TestTheWindow:
    def test_the_constants_are_the_committed_ones(self) -> None:
        assert datetime(2017, 8, 17, tzinfo=UTC) == n4.IN_SAMPLE_START
        assert datetime(2024, 1, 1, tzinfo=UTC) == n4.IN_SAMPLE_END

    def test_the_candidates_are_the_six_in_r_dys_order(self) -> None:
        assert [name for _, name, _ in n4.CANDIDATES] == [
            "donchian_1d_20",
            "donchian_1d_55",
            "sma_cross_1d_50_200",
            "donchian_4h_20",
            "keltner_4h_20_2",
            "tsmom_1d_90",
        ]
        assert [label for label, _, _ in n4.CANDIDATES] == ["C1", "C2", "C3", "C4", "C5", "C6"]

    @pytest.mark.parametrize(
        "argv",
        [
            ["--start", "2017-08-16"],
            ["--end", "2024-01-02"],
            ["--start", "2020-01-01", "--end", "2020-01-01"],
            ["--start", "2025-01-01", "--end", "2025-02-01"],
        ],
    )
    def test_a_window_outside_the_committed_one_is_refused_before_the_store_is_opened(
        self, argv: list[str], monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        def never(*args: Any, **kwargs: Any) -> None:
            raise AssertionError("the store was opened")

        monkeypatch.setattr(HistoricalStore, "candles", never)
        monkeypatch.setattr(n4, "get_settings", never)
        assert n4.main(argv, out=io.StringIO()) == 2
        assert "refused" in capsys.readouterr().err

    def test_a_naive_window_is_refused(self) -> None:
        with pytest.raises(n4.WindowError):
            n4.check_window(datetime(2020, 1, 1), datetime(2021, 1, 1))

    def test_the_whole_committed_window_is_accepted(self) -> None:
        n4.check_window(n4.IN_SAMPLE_START, n4.IN_SAMPLE_END)


GOOD_LINES = [
    HEADER,
    "window [2017-08-17, 2024-01-01)",
    "candidate C4 donchian_4h_20 (4h)",
    "  run complete=yes problems=0",
    "  BTCUSDT signals=538 trades=255 open_at_end=0 clamp_upper=0 clamp_lower=0 size_capped=93",
    refusals("BTCUSDT", limit_refused=277, no_mark_price=1, position_stale=2),
    rules("BTCUSDT", already_in_position=250, daily_loss_halt=27, no_mark_price=1),
    outcomes("BTCUSDT", filled=255, fok=5, expired=1, short=0),
    "  ETHUSDT delta_bps n=0",
    "  ETHUSDT delta_bps n=546 p10=412 p25=498 p50=620 p75=781 p90=1002 min=10 max=2000",
    "scan verdict=CLEAN output_lines=14 log_records=0",
    "output_sha256=" + "ab12" * 16,
]


class TestTheScan:
    def test_the_lines_the_schema_makes_pass(self) -> None:
        assert n4.scan_lines(GOOD_LINES) == 0

    def test_a_stage_named_for_a_price_is_a_stage_and_not_a_figure(self) -> None:
        assert n4.scan_lines([refusals("BTCUSDT", no_mark_price=3, no_reference_price=1)]) == 0

    @pytest.mark.parametrize("rule", RULES)
    def test_every_rule_name_is_a_label_and_not_a_figure(self, rule: str) -> None:
        """R-DT-3e. ``daily_loss_halt`` holds the word ``loss`` and ``no_equity`` the word ``equity``."""
        assert n4.scan_lines([f"  BTCUSDT rules {rule}=1"]) == 0

    def test_the_rule_names_are_the_risk_managers(self) -> None:
        from trading_bot.core.enums import RiskRule

        assert [rule.value for rule in RiskRule] == RULES
        assert tuple(RULES) == n4._RULES

    @pytest.mark.parametrize(
        "line",
        [
            "  BTCUSDT signals=1.5 trades=1 open_at_end=0 clamp_upper=0 clamp_lower=0 size_capped=0",
            "  BTCUSDT signals=1 trades=1 open_at_end=0 clamp_upper=0 clamp_lower=0 size_capped=1.5",
            "  BTCUSDT signals=1 trades=1 open_at_end=0 clamp_upper=0 clamp_lower=0 size_capped=100000",
            "  BTCUSDT signals=1 trades=1 open_at_end=0 clamp_upper=0 clamp_lower=0",
            "  BTCUSDT signals=1 trades=1 open_at_end=0 clamp_upper=0 clamp_lower=0 size_capped=",
            "  BTCUSDT signals=1 trades=1 open_at_end=0 clamp_upper=0 clamp_lower=0 capped=1",
            "  BTCUSDT rules loss=1",
            "  BTCUSDT rules daily_loss=1",
            "  BTCUSDT rules daily_loss_halt=1.5",
            "  BTCUSDT rules daily_loss_halt=100000",
            "  BTCUSDT rules equity=1",
            "  BTCUSDT entry_outcomes filled=1 fok_refused=0 expired=0 unaffordable=0 fee=1",
            "  BTCUSDT entry_outcomes filled=1 fok_refused=0",
            "  BTCUSDT rules",
            "  BTCUSDT mean_return=1",
            "  BTCUSDT delta_bps n=1 p10=100000 p25=1 p50=1 p75=1 p90=1 min=1 max=1",
            "candidate C1 price_1d (1d)",
            "candidate C1 realised_1d (1d)",
            "candidate C1 donchian_1d_20 (1d) equity",
            "  run complete=yes problems=0 ",
            "",
            "window [2017-08-17, 2024-01-01) café",
            "  BTCUSDT balance 42000",
            "output_sha256=XYZ",
        ],
    )
    def test_a_line_outside_the_grammar_or_with_a_figure_is_counted(self, line: str) -> None:
        assert n4.scan_lines([line]) == 1

    def test_the_count_is_per_line(self) -> None:
        assert n4.scan_lines([GOOD_LINES[0], "  BTCUSDT mean_return=1", "x", GOOD_LINES[1]]) == 2

    @pytest.mark.parametrize(
        "message",
        [
            "BTCUSDT/4h: 1 bar(s) missing between 2017-09-06T16:00:00+00:00 and"
            " 2017-09-06T20:00:00+00:00",
            "Entry for ETHUSDT ignored: an entry is pending or a position is held",
            "stream handler failed for BTCUSDT 4h",
        ],
    )
    def test_an_ordinary_log_message_passes(self, message: str) -> None:
        assert n4.scan_log(message) is False

    @pytest.mark.parametrize(
        "message",
        [
            "Risk approved BTCUSDT: 2.00330000 at 98.10000000",
            "free quote 10000.5",
            "filled at 42000",
            "balance is low",
            "the realised total moved",
            "cost $5",
            "price 100",
        ],
    )
    def test_a_message_that_carries_a_figure_or_a_money_word_is_flagged(self, message: str) -> None:
        assert n4.scan_log(message) is True


class TestAForbiddenFigureNeverReachesTheOutput:
    def test_a_line_the_grammar_refuses_is_not_printed(
        self, world: World, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        real = n4.render

        def leaky(window: tuple[date, date], results: Any) -> list[str]:
            return [*real(window, results), "  BTCUSDT mean_return=42000"]

        monkeypatch.setattr(n4, "render", leaky)
        code, text = world.run()
        assert code == 1
        assert "mean_return" not in text and "42000" not in text
        assert text.strip() == "scan verdict=FAILED output_lines=15 log_records=0 violations=1"

    def test_a_log_record_that_carries_a_figure_fails_the_scan_and_is_not_printed(
        self, world: World, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        real = n4.run_candidate

        async def noisy(*args: Any, **kwargs: Any) -> Any:
            logging.getLogger("probe").warning("filled at 42000.50")
            return await real(*args, **kwargs)

        monkeypatch.setattr(n4, "run_candidate", noisy)
        code, text = world.run()
        assert code == 1
        assert "42000" not in text
        assert text.strip() == "scan verdict=FAILED output_lines=14 log_records=1 violations=1"

    def test_an_exception_is_reported_by_class_and_place_and_never_by_message(
        self, world: World, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        async def broken(*args: Any, **kwargs: Any) -> Any:
            raise ValueError("price was 42000.5")

        monkeypatch.setattr(n4, "run_candidate", broken)
        code, text = world.run()
        err = capsys.readouterr().err
        assert code == 2
        assert text == ""
        assert err.startswith("error: ValueError at test_n4_trade_counts.py:")
        assert "42000" not in err


class TestTheScript:
    def test_it_has_no_fetcher_and_never_writes(self) -> None:
        source = Path(n4.__file__).read_text(encoding="utf-8")
        for word in ("aiohttp", "requests", "AsyncClient", "BinanceClient", "urlopen", "download"):
            assert word not in source, word
        assert not re.search(r"open\([^)]*['\"][wax]", source)
        assert ".write_text(" not in source
        assert ".write_bytes(" not in source
        assert "write_run(" not in source
