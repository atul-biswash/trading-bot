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
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

import s4_compare as s4

from trading_bot.backtesting.evidence import EvidenceRefusedError
from trading_bot.backtesting.simulated_executor import SimulatedTrade
from trading_bot.data.historical import HistoricalStore, Row, write_month

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
    store: Path | None = None,
    log_lines: list[str] | None = None,
) -> Path:
    directory = tmp_path / "run"
    directory.mkdir()
    record: dict[str, object] = {
        "schema": 4,
        "provenance": {"verdict": "accepted", "refusal_reasons": "none"},
        "results": {"trades": len(rows) if declared is None else declared},
        "pairs": [
            {"symbol": "BTCUSDT", "timeframe": "1m"},
            {"symbol": "ETHUSDT", "timeframe": "5m"},
        ],
        "strategy": {"name": "sma_crossover", "params": {"fast_period": 3, "slow_period": 8}},
        "window": {"data_dir": str(store if store is not None else tmp_path / "no_store")},
    }
    if eligible is not None:
        record["evidence_eligible"] = eligible
    (directory / "run.json").write_text(json.dumps(record), encoding="utf-8", newline="\n")
    if log_lines is not None:
        (directory / "backtest.log").write_text(
            "\n".join(log_lines) + "\n", encoding="utf-8", newline="\n"
        )
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

    def test_a_window_with_no_length_is_refused_too(self, tmp_path: Path) -> None:
        live = capture(tmp_path, [boot()])
        run = run_dir(tmp_path, [])
        assert s4.main(argv(run, live, (WINDOW[0], WINDOW[0]))) == 2


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

    def test_backtest_entries_outside_the_window_are_dropped_at_both_ends(
        self, tmp_path: Path
    ) -> None:
        rows = [
            backtest_row(
                "BTCUSDT", "2026-10-11T23:59:00+00:00", "1"
            ),  # the minute before the start
            backtest_row("BTCUSDT", "2026-10-12T00:00:00+00:00", "1"),  # the start itself: in
            backtest_row("BTCUSDT", "2026-10-12T23:59:00+00:00", "1"),  # the last minute: in
            backtest_row("BTCUSDT", "2026-10-13T00:00:00+00:00", "1"),  # the end itself: out
        ]
        found = s4.within(
            s4.read_backtest_trades(run_dir(tmp_path, rows) / "trades.csv"),
            start=at(WINDOW[0]),
            end=at(WINDOW[1]),
        )
        assert [e.entry_bar_open for e in found] == [
            at("2026-10-12T00:00:00+00:00"),
            at("2026-10-12T23:59:00+00:00"),
        ]

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
            backtest_row("BTCUSDT", OPEN_B, "-3", quote_total="150"),
        ]
        figures = self.figures(tmp_path, live, rows)
        assert figures.live_returns.n == 2
        assert figures.live_returns.mean == D("-0.5")  # (+1% and -2%) / 2
        # +1% and -2%, so the mean is -0.5 and does not cancel to zero: a return left as a fraction
        # (no x 100) or taken over the wrong total would show here.
        assert figures.backtest_returns.mean == D("-0.5")

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


# --------------------------------------------------------------------------------------
# The diagnosis (C4b)
# --------------------------------------------------------------------------------------
TIMEFRAMES = {"BTCUSDT": "1m", "ETHUSDT": "5m"}
MINUTE_MS = 60_000


def log_line(stamp: str, pid: int, text: str = "x") -> str:
    return f"{stamp} | INFO     | pid={pid} | trading_bot.x | {text}"


def pass_line(stamp: str, pid: int) -> str:
    return log_line(stamp, pid, "Reconciled 0 position(s) event=reconciliation_pass positions=0")


def signal_line(
    event: str, symbol: str, close: str, *, action: str = "BUY", extra: str = ""
) -> str:
    return (
        f"2026-10-12T02:00:00Z | INFO     | pid=11 | trading_bot.engine.modes | Intent BUY {symbol} "
        f"event={event} symbol={symbol} timeframe=1m action={action} signal_ts={close} {extra}"
    )


def live_entry(
    symbol: str = "BTCUSDT", close: str = SIG_A, exit_kind: str = "CLOSE"
) -> s4.LiveEntry:
    signal_close = at(close)
    return s4.LiveEntry(
        symbol=symbol,
        entry_bar_open=signal_close + timedelta(milliseconds=1),
        signal_bar_close=signal_close,
        quantity=D(1),
        entry_quote_total=D(100),
        return_pct=D(1),
        realised=D(1),
        exit_price=D(101),
        exit_kind=exit_kind,
    )


def bt_entry(
    symbol: str = "BTCUSDT", opened: str = OPEN_A, reason: str = "close"
) -> s4.BacktestEntry:
    return s4.BacktestEntry(
        symbol=symbol,
        signal_bar_open=at(opened) - timedelta(minutes=1),
        entry_bar_open=at(opened),
        entry_price=D(100),
        entry_quote_total=D(100),
        realised=D(1),
        return_pct=D(1),
        exit_reason=reason,
        exit_price=D(101),
    )


def sig(
    symbol: str,
    close: str,
    outcome: str = "dispatched",
    stage: str | None = None,
    reference: str | None = None,
) -> s4.Signal:
    return s4.Signal(symbol, at(close), outcome, stage, None if reference is None else D(reference))


def keyed(*signals: s4.Signal) -> dict[tuple[str, datetime], s4.Signal]:
    return {(s.symbol, s.signal_close): s for s in signals}


def series(
    root: Path,
    closes: list[str],
    *,
    first: str = "2026-10-12T01:00:00+00:00",
    omit: frozenset[int] = frozenset(),
    symbol: str = "BTCUSDT",
) -> Path:
    """A 1m series of the given closes from ``first``, one bar per minute, minus the omitted indexes."""
    start = int(at(first).timestamp() * 1000)
    rows = [
        Row(
            start + index * MINUTE_MS,
            close,
            close,
            close,
            close,
            "1.00000000",
            start + (index + 1) * MINUTE_MS - 1,
        )
        for index, close in enumerate(closes)
        if index not in omit
    ]
    write_month(root, symbol, "1m", "2026-10", rows, source_url="x", zip_sha256="0" * 64)
    return root


def checks_over(root: Path | None, fast: int = 3, slow: int = 8) -> s4.SeriesChecks:
    store = None if root is None else HistoricalStore(root)
    return s4.SeriesChecks(store, TIMEFRAMES, fast, slow)


FLAT = ["100.00000000"] * 12
# Signal bar = index 11 of a series that starts 01:00: open 01:11, close 01:11:59.999.
SIGNAL_CLOSE = "2026-10-12T01:11:59.999000+00:00"


class TestTimeframes:
    @pytest.mark.parametrize(("text", "minutes"), [("1m", 1), ("5m", 5), ("1h", 60), ("1d", 1440)])
    def test_the_units_the_bot_trades_parse(self, text: str, minutes: int) -> None:
        assert s4.timeframe_delta(text) == timedelta(minutes=minutes)

    @pytest.mark.parametrize("text", ["", "m", "1x", "1.5m", "1 m", "None"])
    def test_anything_else_is_an_input_error(self, text: str) -> None:
        with pytest.raises(s4.InputError):
            s4.timeframe_delta(text)


class TestDownIntervals:
    def test_a_restart_is_the_span_from_the_last_line_to_the_first_reconciliation_pass(
        self,
    ) -> None:
        lines = [
            log_line("2026-10-12T03:00:00Z", 1),
            log_line("2026-10-12T03:00:10Z", 1),
            log_line("2026-10-12T03:05:00Z", 2, "boot"),
            pass_line("2026-10-12T03:06:00Z", 2),
            pass_line("2026-10-12T03:07:00Z", 2),
        ]
        assert s4.down_intervals(lines) == (
            s4.DownInterval(
                at("2026-10-12T03:00:10+00:00"), at("2026-10-12T03:06:00+00:00"), "1", "2"
            ),
        )

    def test_a_process_that_never_reaches_a_pass_is_taken_to_resume_at_its_first_line(self) -> None:
        lines = [log_line("2026-10-12T03:00:10Z", 1), log_line("2026-10-12T03:05:00Z", 2)]
        found = s4.down_intervals(lines)
        assert len(found) == 1
        assert found[0].end == at("2026-10-12T03:05:00+00:00")

    def test_one_process_has_no_downtime(self) -> None:
        assert s4.down_intervals([log_line("2026-10-12T03:00:00Z", 1)] * 3) == ()

    def test_overlapping_processes_make_no_interval_of_no_length(self) -> None:
        lines = [log_line("2026-10-12T03:00:00Z", 1), log_line("2026-10-12T02:59:00Z", 2)]
        assert s4.down_intervals(lines) == ()

    def test_lines_without_a_pid_or_a_zoned_stamp_are_ignored(self) -> None:
        lines = [
            "2026-09-04 09:23:02 | INFO | no pid here",
            "free text",
            log_line("2026-10-12T03:00:00Z", 1),
        ]
        assert s4.down_intervals(lines) == ()


class TestInDowntime:
    INTERVAL = s4.DownInterval(
        at("2026-10-12T03:00:00+00:00"), at("2026-10-12T03:10:00+00:00"), "1", "2"
    )
    BAR = timedelta(minutes=1)

    def test_a_close_inside_the_interval_is_in(self) -> None:
        assert s4.in_downtime(at("2026-10-12T03:05:00+00:00"), [self.INTERVAL], self.BAR)

    def test_two_bars_after_the_end_are_still_in_and_the_third_is_out(self) -> None:
        assert s4.in_downtime(at("2026-10-12T03:11:59.999+00:00"), [self.INTERVAL], self.BAR)
        assert not s4.in_downtime(at("2026-10-12T03:12:00+00:00"), [self.INTERVAL], self.BAR)

    def test_before_the_start_is_out_and_the_start_itself_is_in(self) -> None:
        assert not s4.in_downtime(at("2026-10-12T02:59:59.999+00:00"), [self.INTERVAL], self.BAR)
        assert s4.in_downtime(at("2026-10-12T03:00:00+00:00"), [self.INTERVAL], self.BAR)

    def test_the_bar_length_is_the_pairs_own(self) -> None:
        five = timedelta(minutes=5)
        assert s4.in_downtime(at("2026-10-12T03:19:59+00:00"), [self.INTERVAL], five)
        assert not s4.in_downtime(at("2026-10-12T03:20:00+00:00"), [self.INTERVAL], five)


class TestDowntimeIsExcludedOnBothSides:
    INTERVAL = s4.DownInterval(
        at("2026-10-12T02:00:00+00:00"), at("2026-10-12T02:30:00+00:00"), "1", "2"
    )

    def test_an_entry_signalled_in_the_outage_leaves_both_sides_and_is_listed(self) -> None:
        live = [live_entry(close="2026-10-12T02:09:59.999000+00:00"), live_entry(close=SIG_B)]
        backtest = [bt_entry(opened="2026-10-12T02:10:00+00:00"), bt_entry(opened=OPEN_B)]
        kept_live, kept_bt, excluded = s4.exclude_downtime(
            live, backtest, [self.INTERVAL], TIMEFRAMES
        )
        assert [e.signal_bar_close for e in kept_live] == [at(SIG_B)]
        assert [e.entry_bar_open for e in kept_bt] == [at(OPEN_B)]
        assert [(side, symbol) for side, symbol, _, _ in excluded] == [
            ("live", "BTCUSDT"),
            ("backtest", "BTCUSDT"),
        ]

    def test_a_symbol_the_record_has_no_timeframe_for_is_an_input_error(self) -> None:
        with pytest.raises(s4.InputError):
            s4.exclude_downtime([live_entry("SOLUSDT")], [], [self.INTERVAL], TIMEFRAMES)


class TestSignals:
    def test_dispatched_and_refused_buys_are_read_with_their_stage_and_reference(self) -> None:
        lines = [
            signal_line("intent_dispatched", "BTCUSDT", SIG_A, extra="reference=100.50000000"),
            signal_line("risk_refused", "BTCUSDT", SIG_B, extra="stage=limit_refused reason=x"),
        ]
        found = s4.read_signals(lines)
        assert found[("BTCUSDT", at(SIG_A))] == sig("BTCUSDT", SIG_A, reference="100.5")
        assert found[("BTCUSDT", at(SIG_B))] == sig("BTCUSDT", SIG_B, "refused", "limit_refused")

    def test_a_close_signal_and_an_unreadable_line_are_ignored_and_the_first_record_wins(
        self,
    ) -> None:
        lines = [
            signal_line("intent_dispatched", "BTCUSDT", SIG_A, action="CLOSE"),
            signal_line("intent_dispatched", "BTCUSDT", "not-a-time"),
            signal_line("intent_dispatched", "BTCUSDT", SIG_B, extra="reference=1"),
            signal_line("risk_refused", "BTCUSDT", SIG_B, extra="stage=late"),
        ]
        found = s4.read_signals(lines)
        assert list(found) == [("BTCUSDT", at(SIG_B))]
        assert found[("BTCUSDT", at(SIG_B))].outcome == "dispatched"


class TestSeriesChecks:
    def test_a_missing_bar_among_the_last_slow_bars_is_a_gap(self, tmp_path: Path) -> None:
        root = series(tmp_path / "gap", FLAT, omit=frozenset({7}))
        assert checks_over(root).gap_near("BTCUSDT", at(SIGNAL_CLOSE)) is True

    def test_a_complete_series_has_no_gap(self, tmp_path: Path) -> None:
        root = series(tmp_path / "whole", FLAT)
        assert checks_over(root).gap_near("BTCUSDT", at(SIGNAL_CLOSE)) is False

    def test_equal_exact_averages_at_the_signal_bar_are_a_tie(self, tmp_path: Path) -> None:
        root = series(tmp_path / "tie", FLAT)
        assert checks_over(root).tie_near("BTCUSDT", at(SIGNAL_CLOSE)) is True

    def test_a_tie_at_the_bar_before_the_signal_bar_counts(self, tmp_path: Path) -> None:
        # Ten flat bars then a jump on the last: the averages tie one bar earlier and not at the end.
        closes = ["100.00000000"] * 11 + ["110.00000000"]
        root = series(tmp_path / "before", closes)
        assert checks_over(root).tie_near("BTCUSDT", at(SIGNAL_CLOSE)) is True

    def test_averages_that_differ_at_both_bars_are_no_tie(self, tmp_path: Path) -> None:
        closes = [f"{100 + index}.00000000" for index in range(12)]
        root = series(tmp_path / "rising", closes)
        assert checks_over(root).tie_near("BTCUSDT", at(SIGNAL_CLOSE)) is False

    def test_the_recorded_close_is_the_signal_bars_and_a_missing_bar_has_none(
        self, tmp_path: Path
    ) -> None:
        closes = [*FLAT[:-1], "105.00000000"]
        root = series(tmp_path / "close", closes)
        assert checks_over(root).recorded_close("BTCUSDT", at(SIGNAL_CLOSE)) == D("105")
        assert (
            checks_over(root).recorded_close("BTCUSDT", at("2026-10-12T05:59:59.999000+00:00"))
            is None
        )

    def test_no_store_answers_none_to_every_question(self) -> None:
        checks = checks_over(None)
        assert checks.gap_near("BTCUSDT", at(SIGNAL_CLOSE)) is None
        assert checks.tie_near("BTCUSDT", at(SIGNAL_CLOSE)) is None
        assert checks.recorded_close("BTCUSDT", at(SIGNAL_CLOSE)) is None

    def test_a_symbol_with_no_timeframe_answers_none(self, tmp_path: Path) -> None:
        checks = checks_over(series(tmp_path / "x", FLAT))
        assert checks.tie_near("SOLUSDT", at(SIGNAL_CLOSE)) is None


class TestCarriedIn:
    def trades(self, lines: list[str]) -> list[s4.Trade]:
        return list(s4.build_trades(s4.parse_capture(lines), "USDT"))

    def test_a_position_opened_before_the_window_and_closed_inside_it_is_carried(self) -> None:
        lines = [
            placed("BTCUSDT", "2026-10-11T23:50:59.999000+00:00"),
            closed("BTCUSDT", "1", "101", "1"),
        ]
        carried = s4.carried_in(self.trades(lines), at(WINDOW[0]))
        assert [symbol for symbol, _ in carried] == ["BTCUSDT"]

    def test_one_closed_before_the_window_or_opened_inside_it_is_not(self) -> None:
        early = [
            placed("BTCUSDT", "2026-10-10T23:50:59.999000+00:00"),
            closed("BTCUSDT", "1", "101", "1").replace("2026-10-12T01:00", "2026-10-11T01:00"),
        ]
        inside = entry_lines("ETHUSDT", SIG_C, "2", "101", "1")
        assert s4.carried_in(self.trades(early + inside), at(WINDOW[0])) == ()


class TestEachCauseHasItsOwnEvidence:
    """One constructed pair per cause. ``diagnose`` is given the signals both sides logged and the
    recorded series, and must return exactly one cause from the closed list."""

    def run(
        self,
        matching: s4.Matching,
        *,
        live: dict[tuple[str, datetime], s4.Signal] | None = None,
        backtest: dict[tuple[str, datetime], s4.Signal] | None = None,
        checks: s4.SeriesChecks | None = None,
        carried: tuple[tuple[str, datetime | None], ...] = (),
    ) -> tuple[s4.Disagreement, ...]:
        return s4.diagnose(
            matching,
            live_signals=live or {},
            backtest_signals=backtest or {},
            checks=checks or checks_over(None),
            carried=carried,
            timeframes=TIMEFRAMES,
        )

    def only(self, found: tuple[s4.Disagreement, ...]) -> s4.Disagreement:
        assert len(found) == 1, found
        return found[0]

    def test_every_cause_is_on_the_closed_list(self) -> None:
        assert set(s4.CAUSES) == {
            "recorded-gap",
            "bar differs",
            "exact-decimal tie",
            "window-edge",
            "risk refusal differs",
            "fok-unfilled",
            "fill-model",
            "unexplained",
        }

    def test_a_live_entry_the_backtest_never_signalled_on_a_tie_is_a_tie(
        self, tmp_path: Path
    ) -> None:
        checks = checks_over(series(tmp_path / "t", FLAT))
        matching = s4.Matching((), (live_entry(close=SIGNAL_CLOSE),), ())
        found = self.only(self.run(matching, checks=checks))
        assert (found.kind, found.cause) == ("live only", "exact-decimal tie")

    def test_a_missing_bar_outranks_a_tie(self, tmp_path: Path) -> None:
        checks = checks_over(series(tmp_path / "g", FLAT, omit=frozenset({7})))
        matching = s4.Matching((), (live_entry(close=SIGNAL_CLOSE),), ())
        assert self.only(self.run(matching, checks=checks)).cause == "recorded-gap"

    def test_a_recorded_close_that_differs_from_the_live_reference_outranks_a_tie(
        self, tmp_path: Path
    ) -> None:
        checks = checks_over(series(tmp_path / "b", FLAT))
        matching = s4.Matching((), (live_entry(close=SIGNAL_CLOSE),), ())
        live = keyed(sig("BTCUSDT", SIGNAL_CLOSE, reference="99.5"))
        found = self.only(self.run(matching, live=live, checks=checks))
        assert found.cause == "bar differs" and "99.5" in found.evidence

    def test_a_signal_nothing_explains_is_unexplained_and_says_why(self, tmp_path: Path) -> None:
        closes = [f"{100 + index}.00000000" for index in range(12)]
        checks = checks_over(series(tmp_path / "u", closes))
        found = self.only(
            self.run(s4.Matching((), (live_entry(close=SIGNAL_CLOSE),), ()), checks=checks)
        )
        assert found.cause == "unexplained" and "no recorded input" in found.evidence
        unread = self.only(self.run(s4.Matching((), (live_entry(close=SIGNAL_CLOSE),), ())))
        assert unread.cause == "unexplained" and "could not be read" in unread.evidence

    def test_a_live_entry_the_backtest_refused_is_a_risk_refusal_with_the_stage(self) -> None:
        backtest = keyed(sig("BTCUSDT", SIG_A, "refused", "limit_refused"))
        found = self.only(self.run(s4.Matching((), (live_entry(),), ()), backtest=backtest))
        assert found.cause == "risk refusal differs" and "limit_refused" in found.evidence

    def test_a_live_entry_the_backtest_dispatched_and_did_not_fill_is_the_fill_model(self) -> None:
        backtest = keyed(sig("BTCUSDT", SIG_A))
        found = self.only(self.run(s4.Matching((), (live_entry(),), ()), backtest=backtest))
        assert found.cause == "fill-model"

    def test_a_backtest_entry_the_live_bot_dispatched_and_never_booked_is_fok_unfilled(
        self,
    ) -> None:
        live = keyed(sig("BTCUSDT", SIG_A))
        found = self.only(self.run(s4.Matching((), (), (bt_entry(),)), live=live))
        assert (found.kind, found.cause) == ("backtest only", "fok-unfilled")

    def test_a_backtest_entry_the_live_bot_refused_is_a_risk_refusal(self) -> None:
        live = keyed(sig("BTCUSDT", SIG_A, "refused", "daily_loss"))
        found = self.only(self.run(s4.Matching((), (), (bt_entry(),)), live=live))
        assert found.cause == "risk refusal differs" and "daily_loss" in found.evidence

    def test_an_already_in_position_refusal_beside_a_carried_position_is_the_windows_edge(
        self,
    ) -> None:
        live = keyed(sig("BTCUSDT", SIG_A, "refused", "already_in_position"))
        carried = (("BTCUSDT", at("2026-10-12T05:00:00+00:00")),)
        found = self.only(self.run(s4.Matching((), (), (bt_entry(),)), live=live, carried=carried))
        assert found.cause == "window-edge"
        elsewhere = (("ETHUSDT", at("2026-10-12T05:00:00+00:00")),)
        again = self.only(
            self.run(s4.Matching((), (), (bt_entry(),)), live=live, carried=elsewhere)
        )
        assert again.cause == "risk refusal differs"

    def test_a_carried_position_closed_before_the_signal_is_not_the_windows_edge(self) -> None:
        live = keyed(sig("BTCUSDT", SIG_A, "refused", "already_in_position"))
        carried = (("BTCUSDT", at("2026-10-12T01:00:00+00:00")),)
        found = self.only(self.run(s4.Matching((), (), (bt_entry(),)), live=live, carried=carried))
        assert found.cause == "risk refusal differs"

    def test_a_matched_pair_that_exited_differently_is_the_fill_model_with_both_prices(
        self,
    ) -> None:
        pair = (live_entry(exit_kind="SL"), bt_entry(reason="take_profit"))
        found = self.only(self.run(s4.Matching((pair,), (), ())))
        assert found.kind == "different exit" and found.cause == "fill-model"
        assert "SL at 101" in found.evidence and "take_profit at 101" in found.evidence

    def test_a_matched_pair_that_exited_alike_is_no_disagreement(self) -> None:
        stop = (live_entry(exit_kind="SL"), bt_entry(reason="stop_loss"))
        close = (live_entry(exit_kind="CLOSE"), bt_entry(reason="close"))
        assert self.run(s4.Matching((stop, close), (), ())) == ()


class TestUnfilledPlacements:
    def test_a_placement_with_no_booking_inside_the_window_is_listed(self) -> None:
        lines = [
            *entry_lines("BTCUSDT", SIG_A, "1", "101", "1"),
            placed("BTCUSDT", SIG_B),
            placed("ETHUSDT", "2026-10-11T22:59:59.999000+00:00"),
        ]
        parsed = s4.parse_capture(lines)
        trades = s4.build_trades(parsed, "USDT")
        found = s4.unfilled_placements(
            parsed.placements, trades, start=at(WINDOW[0]), end=at(WINDOW[1])
        )
        assert [(p.symbol, p.entry_bar_time) for p in found] == [("BTCUSDT", at(SIG_B))]

    def test_the_backtests_view_of_each_such_placement(self) -> None:
        parsed = s4.parse_capture([placed("BTCUSDT", SIG_A)])
        assert len(parsed.placements) == 1
        placement = parsed.placements[0]
        view = s4.backtest_view_of
        assert view(placement, [bt_entry(opened=OPEN_A)], {}) == "backtest FILLED"
        assert view(placement, [], {}) == "backtest emitted no signal"
        refused = keyed(sig("BTCUSDT", SIG_A, "refused", "cooldown"))
        assert view(placement, [], refused) == "backtest refused at cooldown"
        assert (
            view(placement, [], keyed(sig("BTCUSDT", SIG_A)))
            == "backtest dispatched and did not fill"
        )


class TestTheDiagnosisEndToEnd:
    def build(self, tmp_path: Path) -> tuple[Path, Path]:
        """A live run with a restart, an entry the backtest took during it, one entry both took, and an
        unfilled placement; the backtest also took an entry the live bot has no signal for."""
        after_restart = [*entry_lines("BTCUSDT", SIG_A, "1", "101", "1"), placed("BTCUSDT", SIG_B)]
        lines = [
            boot(pid=11),
            log_line("2026-10-12T03:30:00Z", 11),
            boot(pid=12),
            pass_line("2026-10-12T04:00:00Z", 12),
            *[line.replace("pid=11", "pid=12") for line in after_restart],
        ]
        live = capture(tmp_path, lines)
        log = [
            signal_line("intent_dispatched", "BTCUSDT", SIG_A, extra="reference=100"),
            signal_line("intent_dispatched", "BTCUSDT", "2026-10-12T03:39:59.999000+00:00"),
        ]
        rows = [
            backtest_row("BTCUSDT", OPEN_A, "1"),
            backtest_row("BTCUSDT", "2026-10-12T03:40:00+00:00", "1"),
            backtest_row("BTCUSDT", OPEN_D, "1"),
        ]
        run = run_dir(tmp_path, rows, log_lines=log)
        return run, live

    def test_the_report_lists_downtime_unfilled_placements_and_causes(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        run, live = self.build(tmp_path)
        assert s4.main(argv(run, live)) == 0
        out = capsys.readouterr().out
        assert "BOT DOWNTIME (R-AP)" in out and "pid 11 -> pid 12" in out
        assert "excluded on both sides (1)" in out
        assert "LIVE PLACEMENTS WITH NO BOOKING IN THE CAPTURE (1)" in out
        assert "backtest emitted no signal" in out
        assert "DISAGREEMENTS (1)" in out and "[unexplained] backtest only" in out
        assert TestTheReportPrintsFiguresAndNoVerdict.VERDICT_WORDS.search(out) is None

    def test_an_unreadable_store_is_named_and_the_report_still_prints(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        run, live = self.build(tmp_path)
        assert s4.main(argv(run, live)) == 0
        assert "recorded series" in capsys.readouterr().out

    def test_a_record_with_no_pairs_is_an_input_error_and_not_a_default(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        run, live = self.build(tmp_path)
        record = json.loads((run / "run.json").read_text(encoding="utf-8"))
        del record["pairs"]
        (run / "run.json").write_text(json.dumps(record), encoding="utf-8", newline="\n")
        assert s4.main(argv(run, live)) == 3
        assert "names no pairs" in capsys.readouterr().out
