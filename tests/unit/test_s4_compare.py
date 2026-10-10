"""``scripts/s4_compare.py``: the door, the match key, the three R-C figures, and a report with no verdict.

Every capture here is a few synthetic lines in the shape the bot logs, and every figure is worked by
hand beside the assertion that pins it, because a comparison whose expected values were taken from its
own output proves nothing. The run directories are written the way ``write_run`` writes them (the
header is ``SimulatedTrade``'s own field list), so a column the tool reads cannot drift from a column
the engine writes without a test noticing.
"""

from __future__ import annotations

import csv
import dataclasses
import json
import re
import sys
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

import s4_compare as s4

from trading_bot.backtesting.evidence import EvidenceRefusedError
from trading_bot.backtesting.simulated_executor import SimulatedTrade

D = Decimal
UTC = timezone.utc
WINDOW = ("2026-10-12T00:00:00Z", "2026-10-13T00:00:00Z")


def boot(verdict: str = "accepted", pid: int = 11, reasons: str = "none") -> str:
    return (
        f"2026-10-12T00:00:01Z | INFO     | pid={pid} | __main__ | Startup provenance {verdict} "
        f"event=boot_provenance verdict={verdict} refusal_reasons={reasons} unknown_reasons=none "
        "install_kind=vcs code_intact=true"
    )


def placed(symbol: str, signal_close: str, qty: str = "1", entry: str = "100") -> str:
    return (
        f"2026-10-12T00:01:03Z | INFO     | pid=11 | trading_bot.execution.executor | Order list "
        f"placed event=order_placed symbol={symbol} quantity={qty} entry={entry} stop_loss=98 "
        f"order_list_id=7 list_client_order_id=tb1-{symbol}-1-0-L entry_bar_time={signal_close}"
    )


def closed(symbol: str, order_id: str, total: str, realised: str, qty: str = "1") -> str:
    return (
        f"2026-10-12T01:00:03Z | INFO     | pid=11 | trading_bot.execution.executor | Closed {symbol} "
        f"event=close_booked symbol={symbol} order_id={order_id} quantity={qty} quote_total={total} "
        f"realised={realised} candle_time=2026-10-12T01:00:59.999000+00:00"
    )


def entry_lines(
    symbol: str, signal_close: str, order_id: str, total: str, realised: str
) -> list[str]:
    """A placement and its booking; the entry quote total is ``total - realised`` = 100 here."""
    return [placed(symbol, signal_close), closed(symbol, order_id, total, realised)]


def capture(tmp_path: Path, lines: list[str], name: str = "live.log") -> Path:
    path = tmp_path / name
    path.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    return path


def backtest_row(
    symbol: str, entry_open: str, realised: str, quote_total: str = "100"
) -> dict[str, str]:
    return {
        "symbol": symbol,
        "signal_bar_open": entry_open,
        "entry_bar_open": entry_open,
        "entry_price": "100",
        "entry_quote_total": quote_total,
        "realised": realised,
        "exit_reason": "close",
        "exit_price": "101",
    }


def run_dir(
    tmp_path: Path,
    rows: list[dict[str, str]],
    *,
    eligible: object = True,
    declared: int | None = None,
) -> Path:
    directory = tmp_path / "run"
    directory.mkdir()
    record: dict[str, object] = {
        "schema": 4,
        "provenance": {"verdict": "accepted", "refusal_reasons": "none"},
        "results": {"trades": len(rows) if declared is None else declared},
    }
    if eligible is not None:
        record["evidence_eligible"] = eligible
    (directory / "run.json").write_text(json.dumps(record), encoding="utf-8", newline="\n")
    names = [field.name for field in dataclasses.fields(SimulatedTrade)]
    with (directory / "trades.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=names, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({name: row.get(name, "0") for name in names})
    return directory


def argv(run: Path, live: Path, window: tuple[str, str] = WINDOW) -> list[str]:
    return [
        "--run", str(run), "--capture", str(live),
        "--window-start", window[0], "--window-end", window[1],
    ]  # fmt: skip


# Entry bars: the signal bar closes at hh:mm:59.999, the entry bar opens one millisecond later.
SIG_A, OPEN_A = "2026-10-12T02:09:59.999000+00:00", "2026-10-12T02:10:00+00:00"
SIG_B, OPEN_B = "2026-10-12T03:19:59.999000+00:00", "2026-10-12T03:20:00+00:00"
SIG_C, OPEN_C = "2026-10-12T04:29:59.999000+00:00", "2026-10-12T04:30:00+00:00"
OPEN_D = "2026-10-12T05:40:00+00:00"


def at(value: str) -> datetime:
    return datetime.fromisoformat(value).astimezone(UTC)


class TestTheEvidenceDoor:
    def test_a_backtest_record_that_is_not_evidence_is_refused_before_any_figure(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        live = capture(tmp_path, [boot(), *entry_lines("BTCUSDT", SIG_A, "1", "101", "1")])
        run = run_dir(tmp_path, [backtest_row("BTCUSDT", OPEN_A, "1")], eligible=False)
        assert s4.main(argv(run, live)) == 2
        out = capsys.readouterr().out
        assert out.startswith("REFUSED:") and "evidence_eligible false" in out
        assert "R-C FIGURES" not in out

    def test_a_record_written_before_the_ruling_is_refused(self, tmp_path: Path) -> None:
        live = capture(tmp_path, [boot(), *entry_lines("BTCUSDT", SIG_A, "1", "101", "1")])
        run = run_dir(tmp_path, [backtest_row("BTCUSDT", OPEN_A, "1")], eligible=None)
        assert s4.main(argv(run, live)) == 2

    def test_a_capture_with_no_boot_line_is_refused(self, tmp_path: Path) -> None:
        live = capture(tmp_path, entry_lines("BTCUSDT", SIG_A, "1", "101", "1"))
        run = run_dir(tmp_path, [backtest_row("BTCUSDT", OPEN_A, "1")])
        assert s4.main(argv(run, live)) == 2

    def test_one_refused_boot_among_accepted_ones_refuses_the_live_run(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        lines = [
            boot(pid=11),
            boot("refused", pid=12, reasons="install_kind=editable"),
            boot(pid=13),
        ]
        live = capture(tmp_path, lines + entry_lines("BTCUSDT", SIG_A, "1", "101", "1"))
        run = run_dir(tmp_path, [backtest_row("BTCUSDT", OPEN_A, "1")])
        assert s4.main(argv(run, live)) == 2
        assert "pid 12" in capsys.readouterr().out

    def test_an_all_accepted_live_run_and_an_eligible_record_get_through(
        self, tmp_path: Path
    ) -> None:
        live = capture(tmp_path, [boot(), *entry_lines("BTCUSDT", SIG_A, "1", "101", "1")])
        run = run_dir(tmp_path, [backtest_row("BTCUSDT", OPEN_A, "1")])
        assert s4.main(argv(run, live)) == 0

    def test_the_live_door_is_the_evidence_module_s_own(self) -> None:
        with pytest.raises(EvidenceRefusedError):
            s4.require_live_run_eligible([])
        with pytest.raises(EvidenceRefusedError):
            s4.require_live_run_eligible([s4.Boot(1, "9", "unrecorded", "x")])
        s4.require_live_run_eligible([s4.Boot(1, "9", "accepted", "none")])

    def test_a_capture_under_a_logs_directory_is_never_read(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        (tmp_path / "logs").mkdir()
        live = capture(tmp_path / "logs", [boot()])
        run = run_dir(tmp_path, [])
        assert s4.main(argv(run, live)) == 2
        assert "logs/" in capsys.readouterr().out

    def test_a_window_that_ends_before_it_starts_is_refused(self, tmp_path: Path) -> None:
        live = capture(tmp_path, [boot()])
        run = run_dir(tmp_path, [])
        assert s4.main(argv(run, live, (WINDOW[1], WINDOW[0]))) == 2


class TestTheMatchKey:
    def live(self, tmp_path: Path, lines: list[str]) -> tuple[s4.LiveEntry, ...]:
        parsed = s4.parse_capture(lines)
        found, unplaced = s4.live_entries(
            s4.build_trades(parsed, "USDT"), start=at(WINDOW[0]), end=at(WINDOW[1])
        )
        assert unplaced == 0
        return found

    def test_a_live_entry_bar_is_the_signal_bar_close_plus_one_millisecond(
        self, tmp_path: Path
    ) -> None:
        entries = self.live(tmp_path, entry_lines("BTCUSDT", SIG_A, "1", "101", "1"))
        assert len(entries) == 1
        assert entries[0].entry_bar_open == at(OPEN_A)
        assert entries[0].signal_bar_close == at(SIG_A)

    def test_entries_pair_on_symbol_and_entry_bar_and_the_rest_are_listed(
        self, tmp_path: Path
    ) -> None:
        live = self.live(
            tmp_path,
            entry_lines("BTCUSDT", SIG_A, "1", "101", "1")
            + entry_lines("BTCUSDT", SIG_B, "2", "99", "-1")
            + entry_lines("ETHUSDT", SIG_C, "3", "102", "2"),
        )
        rows = [
            backtest_row("BTCUSDT", OPEN_A, "1"),  # matches the first live entry
            backtest_row("ETHUSDT", OPEN_B, "1"),  # the second live entry's bar, but ETHUSDT
            backtest_row("BTCUSDT", OPEN_D, "1"),  # no live entry at all
        ]
        backtest = s4.read_backtest_trades(run_dir(tmp_path, rows) / "trades.csv")
        matching = s4.match_entries(live, backtest)
        assert [(a.symbol, b.symbol) for a, b in matching.matched] == [("BTCUSDT", "BTCUSDT")]
        assert [(e.symbol, e.entry_bar_open) for e in matching.live_only] == [
            ("BTCUSDT", at(OPEN_B)),
            ("ETHUSDT", at(OPEN_C)),
        ]
        assert [(e.symbol, e.entry_bar_open) for e in matching.backtest_only] == [
            ("ETHUSDT", at(OPEN_B)),
            ("BTCUSDT", at(OPEN_D)),
        ]

    def test_two_entries_on_one_key_are_an_input_error_not_a_quiet_choice(
        self, tmp_path: Path
    ) -> None:
        rows = [backtest_row("BTCUSDT", OPEN_A, "1"), backtest_row("BTCUSDT", OPEN_A, "2")]
        backtest = s4.read_backtest_trades(run_dir(tmp_path, rows) / "trades.csv")
        with pytest.raises(s4.InputError):
            s4.match_entries([], backtest)

    def test_the_window_is_half_open_on_the_entry_bar_open(self, tmp_path: Path) -> None:
        lines = entry_lines("BTCUSDT", "2026-10-11T23:59:59.999000+00:00", "1", "101", "1")
        lines += entry_lines("BTCUSDT", SIG_A, "2", "101", "1")
        lines += entry_lines("BTCUSDT", "2026-10-12T23:59:59.999000+00:00", "3", "101", "1")
        parsed = s4.parse_capture(lines)
        found, _ = s4.live_entries(
            s4.build_trades(parsed, "USDT"), start=at(WINDOW[0]), end=at(WINDOW[1])
        )
        # The first entry bar opens 2026-10-12T00:00:00 exactly (inside); the third opens at the
        # window's end, 2026-10-13T00:00:00 (outside).
        assert [e.entry_bar_open for e in found] == [at("2026-10-12T00:00:00+00:00"), at(OPEN_A)]

    def test_a_booking_with_no_placement_is_counted_and_not_keyed(self, tmp_path: Path) -> None:
        parsed = s4.parse_capture([closed("BTCUSDT", "9", "101", "1")])
        found, unplaced = s4.live_entries(
            s4.build_trades(parsed, "USDT"), start=at(WINDOW[0]), end=at(WINDOW[1])
        )
        assert (found, unplaced) == ((), 1)


class TestTheThreeFigures:
    def figures(
        self, tmp_path: Path, live_lines: list[str], rows: list[dict[str, str]]
    ) -> s4.Figures:
        tmp_path.mkdir(exist_ok=True)
        parsed = s4.parse_capture(live_lines)
        live, _ = s4.live_entries(
            s4.build_trades(parsed, "USDT"), start=at(WINDOW[0]), end=at(WINDOW[1])
        )
        backtest = s4.read_backtest_trades(run_dir(tmp_path, rows) / "trades.csv")
        return s4.figures_of(live, backtest, s4.match_entries(live, backtest))

    def test_reproduction_is_matched_over_live_and_counts_differ_by_a_share_of_live(
        self, tmp_path: Path
    ) -> None:
        live = (
            entry_lines("BTCUSDT", SIG_A, "1", "101", "1")
            + entry_lines("BTCUSDT", SIG_B, "2", "99", "-1")
            + entry_lines("ETHUSDT", SIG_C, "3", "102", "2")
            + entry_lines("ETHUSDT", "2026-10-12T05:39:59.999000+00:00", "4", "100", "0")
        )
        rows = [
            backtest_row("BTCUSDT", OPEN_A, "1"),
            backtest_row("BTCUSDT", OPEN_B, "-1"),
            backtest_row("ETHUSDT", OPEN_C, "2"),
            backtest_row("ETHUSDT", OPEN_D, "0"),
            backtest_row("BTCUSDT", "2026-10-12T06:00:00+00:00", "0"),
        ]
        figures = self.figures(tmp_path, live, rows)
        assert (figures.live_count, figures.backtest_count, figures.matched) == (4, 5, 4)
        assert figures.reproduction_pct == D(100)
        assert figures.count_difference == 1
        assert figures.count_difference_pct == D(25)

    def test_three_of_four_is_exactly_seventy_five_percent(self, tmp_path: Path) -> None:
        live = (
            entry_lines("BTCUSDT", SIG_A, "1", "101", "1")
            + entry_lines("BTCUSDT", SIG_B, "2", "101", "1")
            + entry_lines("ETHUSDT", SIG_C, "3", "101", "1")
            + entry_lines("ETHUSDT", "2026-10-12T05:39:59.999000+00:00", "4", "101", "1")
        )
        rows = [
            backtest_row("BTCUSDT", OPEN_A, "1"),
            backtest_row("BTCUSDT", OPEN_B, "1"),
            backtest_row("ETHUSDT", OPEN_C, "1"),
        ]
        figures = self.figures(tmp_path, live, rows)
        assert figures.matched == 3 and figures.reproduction_pct == D(75)
        assert figures.count_difference_pct == D(25)

    def test_a_return_is_realised_over_the_entry_quote_total_as_a_percentage(
        self, tmp_path: Path
    ) -> None:
        # Live: entry total 100 (booked 101 less realised 1), so +1%. Backtest: 2 over 200, +1%.
        live = entry_lines("BTCUSDT", SIG_A, "1", "101", "1") + entry_lines(
            "BTCUSDT", SIG_B, "2", "98", "-2"
        )
        rows = [
            backtest_row("BTCUSDT", OPEN_A, "2", quote_total="200"),
            backtest_row("BTCUSDT", OPEN_B, "-3", quote_total="300"),
        ]
        figures = self.figures(tmp_path, live, rows)
        assert figures.live_returns.n == 2
        assert figures.live_returns.mean == D("-0.5")  # (+1% and -2%) / 2
        assert figures.backtest_returns.mean == D("0")  # (+1% and -1%) / 2

    def test_the_backtest_mean_is_placed_against_the_live_interval(self, tmp_path: Path) -> None:
        # Live returns +1%, +1%, +3%: mean 1.6667, sd 1.1547, se 0.6667, interval 0.3600 to 2.9733.
        live = (
            entry_lines("BTCUSDT", SIG_A, "1", "101", "1")
            + entry_lines("BTCUSDT", SIG_B, "2", "101", "1")
            + entry_lines("BTCUSDT", SIG_C, "3", "103", "3")
        )
        inside = self.figures(tmp_path / "a", live, [backtest_row("BTCUSDT", OPEN_A, "1")])
        below = self.figures(tmp_path / "b", live, [backtest_row("BTCUSDT", OPEN_A, "-5")])
        above = self.figures(tmp_path / "c", live, [backtest_row("BTCUSDT", OPEN_A, "9")])
        assert inside.backtest_mean_position == "inside"
        assert below.backtest_mean_position == "below"
        assert above.backtest_mean_position == "above"

    def test_one_live_trade_has_no_interval_to_place_a_mean_against(self, tmp_path: Path) -> None:
        figures = self.figures(
            tmp_path,
            entry_lines("BTCUSDT", SIG_A, "1", "101", "1"),
            [backtest_row("BTCUSDT", OPEN_A, "1")],
        )
        assert figures.backtest_mean_position == "no interval"

    def test_an_empty_live_side_has_no_percentages_and_does_not_divide_by_zero(
        self, tmp_path: Path
    ) -> None:
        figures = self.figures(tmp_path, [boot()], [backtest_row("BTCUSDT", OPEN_A, "1")])
        assert figures.live_count == 0
        assert figures.reproduction_pct is None and figures.count_difference_pct is None


class TestTheReportPrintsFiguresAndNoVerdict:
    VERDICT_WORDS = re.compile(r"\b(PASS|PASSES|PASSED|FAIL|FAILS|FAILED|INCONCLUSIVE)\b")

    def report(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> str:
        live = capture(
            tmp_path,
            [
                boot(),
                *entry_lines("BTCUSDT", SIG_A, "1", "101", "1"),
                *entry_lines("BTCUSDT", SIG_B, "2", "99", "-1"),
            ],
        )
        run = run_dir(
            tmp_path, [backtest_row("BTCUSDT", OPEN_A, "1"), backtest_row("BTCUSDT", OPEN_D, "1")]
        )
        assert s4.main(argv(run, live)) == 0
        return capsys.readouterr().out

    def test_no_verdict_word_appears(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        out = self.report(tmp_path, capsys)
        assert self.VERDICT_WORDS.search(out) is None

    def test_the_figures_the_entries_and_the_digests_appear(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        out = self.report(tmp_path, capsys)
        assert "reproduced on symbol and bar : 1 of 2 = 50.00%" in out
        assert "LIVE ONLY (1)" in out and "BACKTEST ONLY (1)" in out
        for label in ("capture sha256", "run.json sha256", "trades.csv sha256"):
            assert re.search(rf"{label}\s*: [0-9a-f]{{64}}", out), label
        assert "pid 11 verdict accepted" in out

    def test_a_trades_csv_that_disagrees_with_the_record_is_an_input_error(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        live = capture(tmp_path, [boot()])
        run = run_dir(tmp_path, [backtest_row("BTCUSDT", OPEN_A, "1")], declared=2)
        assert s4.main(argv(run, live)) == 3
        assert "declares 2" in capsys.readouterr().out
