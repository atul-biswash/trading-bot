"""``scripts/s4_explore.py``: the exploratory downtime analysis (M5m P123, R-DC).

Every capture here is a few synthetic lines whose intervals and counts are worked by hand in the test, because an
analysis whose expected values came from its own output proves nothing. The five shapes the ruling's author expects to
differ are each built: a clean stop, a power cut with no position, a power cut with a restored position, a refused boot,
and ``strategies`` boots that must not count. The frozen ``down_intervals`` is imported by the script and run as it
stands; the tests pin where it and the corrected rule agree and where they part.
"""

from __future__ import annotations

import sys
from collections.abc import Sequence
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

import s4_explore as ex
from s4_compare import InputError

from trading_bot.engine.live_engine import _EVENT_STOPPED
from trading_bot.execution.reconciliation_driver import _EVENT_PASS

UTC = timezone.utc
PAIRS = "BTCUSDT/1m, ETHUSDT/5m"
REPO = Path(__file__).resolve().parents[2]
WINDOW = ("2026-10-11T00:00:00Z", "2026-10-12T00:00:00Z")


def at(day_time: str) -> datetime:
    """``HH:MM:SS`` (or with a date) on 2026-10-11 as an aware datetime."""
    text = day_time if "T" in day_time else f"2026-10-11T{day_time}"
    return datetime.fromisoformat(text + "+00:00")


def line(clock: str, pid: int, logger: str, message: str, level: str = "INFO") -> str:
    return f"2026-10-11T{clock}Z | {level:<8} | pid={pid} | {logger} | {message}"


def banner(clock: str, pid: int) -> list[str]:
    """What a ``strategies`` verification boot writes: a provenance line and nothing else."""
    return [
        line(
            clock,
            pid,
            "trading_bot.main",
            "Startup provenance accepted event=boot_provenance verdict=accepted",
        )
    ]


def trading_boot(clock: str, pid: int, engine: str, pairs: str = PAIRS) -> list[str]:
    return [
        line(
            clock,
            pid,
            "trading_bot.main",
            "Startup provenance accepted event=boot_provenance verdict=accepted",
        ),
        line(clock, pid, "trading_bot.main", "Starting in TESTNET mode"),
        line(engine, pid, "trading_bot.engine.live_engine", f"Trading engine started: {pairs}"),
    ]


def reconcile(clock: str, pid: int) -> str:
    return line(
        clock,
        pid,
        "trading_bot.execution.reconciliation_driver",
        f"Reconciled 1 position(s) event={_EVENT_PASS} positions=1",
    )


def stopped(clock: str, pid: int) -> str:
    return line(
        clock,
        pid,
        "trading_bot.engine.live_engine",
        f"Trading engine stopped event={_EVENT_STOPPED} clean_shutdown=True",
    )


def placed(clock: str, pid: int, symbol: str, signal_close: str) -> str:
    return line(
        clock,
        pid,
        "trading_bot.execution.executor",
        f"Order list placed event=order_placed symbol={symbol} quantity=1 entry=100 stop_loss=98 "
        f"order_list_id=7 list_client_order_id=tb1-{symbol}-1-0-L entry_bar_time=2026-10-11T{signal_close}+00:00",
    )


def booked(clock: str, pid: int, symbol: str, order_id: str) -> str:
    return line(
        clock,
        pid,
        "trading_bot.execution.executor",
        f"Closed {symbol} event=close_booked symbol={symbol} order_id={order_id} quantity=1 quote_total=101 "
        "realised=1 candle_time=2026-10-11T23:59:59.999000+00:00",
    )


def seq(*parts: str | Sequence[str]) -> list[str]:
    """Log lines in order: each part is one line or a list of lines."""
    out: list[str] = []
    for part in parts:
        if isinstance(part, str):
            out.append(part)
        else:
            out.extend(part)
    return out


def interval_tuples(intervals: Sequence[ex.DownInterval]) -> list[tuple[str, str, str, str]]:
    """(start, end, before pid, after pid) with the clock times, for comparing a rule's answer in one line."""
    return [
        (i.start.strftime("%H:%M:%S"), i.end.strftime("%H:%M:%S"), i.before_pid, i.after_pid)
        for i in intervals
    ]


# --------------------------------------------------------------------------------------
# The first closed candle
# --------------------------------------------------------------------------------------
class TestFirstClosedCandle:
    def test_it_is_the_next_boundary_of_the_shortest_timeframe(self) -> None:
        pairs = [("BTCUSDT", "1m"), ("ETHUSDT", "5m")]
        assert ex.first_closed_candle(at("10:00:20"), pairs) == at("10:01:00")
        assert ex.first_closed_candle(at("10:00:59"), pairs) == at("10:01:00")

    def test_a_stamp_on_a_boundary_waits_for_the_next_one(self) -> None:
        assert ex.first_closed_candle(at("10:01:00"), [("BTCUSDT", "1m")]) == at("10:02:00")

    def test_with_only_five_minute_pairs_the_grid_is_five_minutes(self) -> None:
        assert ex.first_closed_candle(at("10:00:20"), [("ETHUSDT", "5m")]) == at("10:05:00")
        assert ex.first_closed_candle(at("10:04:59"), [("ETHUSDT", "5m")]) == at("10:05:00")
        assert ex.first_closed_candle(at("10:05:00"), [("ETHUSDT", "5m")]) == at("10:10:00")

    def test_an_hourly_grid_is_aligned_to_the_utc_hour(self) -> None:
        assert ex.first_closed_candle(at("10:20:00"), [("BTCUSDT", "1h")]) == at("11:00:00")


# --------------------------------------------------------------------------------------
# The processes
# --------------------------------------------------------------------------------------
class TestProcesses:
    def test_a_trading_process_is_one_with_an_engine_started_line(self) -> None:
        lines = seq(
            banner("09:00:00", 1),
            trading_boot("10:00:00", 2, "10:00:20"),
            [reconcile("10:02:00", 2), stopped("12:00:00", 2)],
        )
        one, two = ex.read_processes(lines)
        assert (one.pid, one.engine_started, one.first_candle, one.clean_stop) == (
            "1",
            None,
            None,
            False,
        )
        assert (two.pid, two.engine_started, two.first_candle, two.clean_stop) == (
            "2",
            at("10:00:20"),
            at("10:01:00"),
            True,
        )
        assert (two.first, two.last, two.first_pass, two.pairs) == (
            at("10:00:00"),
            at("12:00:00"),
            at("10:02:00"),
            (("BTCUSDT", "1m"), ("ETHUSDT", "5m")),
        )

    def test_processes_are_ordered_by_the_first_line_they_wrote(self) -> None:
        lines = trading_boot("10:00:00", 9, "10:00:20") + banner("10:30:00", 3)
        assert [p.pid for p in ex.read_processes(lines)] == ["9", "3"]

    def test_unstamped_lines_and_other_noise_are_ignored(self) -> None:
        lines = ["  ____  banner art", "", *trading_boot("10:00:00", 2, "10:00:20")]
        assert [p.pid for p in ex.read_processes(lines)] == ["2"]

    def test_the_timeframes_come_from_the_engine_started_lines(self) -> None:
        lines = trading_boot("10:00:00", 2, "10:00:20") + trading_boot("11:00:00", 3, "11:00:20")
        assert ex.timeframes_of(ex.read_processes(lines)) == {"BTCUSDT": "1m", "ETHUSDT": "5m"}

    def test_two_processes_that_disagree_on_a_timeframe_are_an_input_error(self) -> None:
        lines = trading_boot("10:00:00", 2, "10:00:20") + trading_boot(
            "11:00:00", 3, "11:00:20", pairs="BTCUSDT/5m"
        )
        with pytest.raises(InputError, match="BTCUSDT"):
            ex.timeframes_of(ex.read_processes(lines))

    def test_the_markers_are_the_ones_the_bot_logs(self) -> None:
        source = (REPO / "src" / "trading_bot" / "engine" / "live_engine.py").read_text(
            encoding="utf-8"
        )
        assert '"Trading engine started: %s"' in source
        assert (_EVENT_STOPPED, _EVENT_PASS) == ("engine_stopped", "reconciliation_pass")
        assert (
            ex._ENGINE_STARTED.search("Trading engine started: BTCUSDT/1m, ETHUSDT/5m") is not None
        )


# --------------------------------------------------------------------------------------
# The two rules, on the five shapes
# --------------------------------------------------------------------------------------
class TestTheTwoRules:
    def both(
        self, lines: list[str]
    ) -> tuple[list[tuple[str, str, str, str]], list[tuple[str, str, str, str]]]:
        frozen = interval_tuples(ex.down_intervals(lines))
        corrected = interval_tuples(ex.corrected_intervals(ex.read_processes(lines)))
        return frozen, corrected

    def test_a_clean_stop_ends_at_the_first_pass_under_the_frozen_rule_and_at_the_first_candle_under_the_corrected(
        self,
    ) -> None:
        lines = seq(
            trading_boot("10:00:00", 100, "10:00:20"),
            [stopped("12:00:00", 100)],
            trading_boot("12:30:00", 200, "12:30:20"),
            [placed("12:40:01", 200, "BTCUSDT", "12:39:59.999000"), reconcile("12:41:00", 200)],
        )
        frozen, corrected = self.both(lines)
        assert frozen == [("12:00:00", "12:41:00", "100", "200")]
        assert corrected == [("12:00:00", "12:31:00", "100", "200")]

    def test_a_power_cut_with_no_position_is_down_until_the_next_first_position_under_the_frozen_rule(
        self,
    ) -> None:
        lines = seq(
            trading_boot("13:00:00", 300, "13:00:20"),
            [reconcile("14:00:10", 300)],
            trading_boot("14:10:00", 400, "14:10:20"),
            [placed("15:29:01", 400, "BTCUSDT", "15:28:59.999000"), reconcile("15:30:05", 400)],
        )
        frozen, corrected = self.both(lines)
        assert frozen == [("14:00:10", "15:30:05", "300", "400")]
        assert corrected == [("14:00:10", "14:11:00", "300", "400")]

    def test_a_power_cut_with_a_restored_position_ends_in_the_same_minute_under_both_rules(
        self,
    ) -> None:
        lines = seq(
            trading_boot("15:00:00", 500, "15:00:20"),
            [reconcile("16:00:00", 500)],
            trading_boot("16:20:00", 600, "16:20:15"),
            [
                line(
                    "16:20:16",
                    600,
                    "trading_bot.engine.modes",
                    "restored position event=boot_position_restored",
                ),
                reconcile("16:21:00", 600),
            ],
        )
        frozen, corrected = self.both(lines)
        assert frozen == corrected == [("16:00:00", "16:21:00", "500", "600")]

    def test_a_refused_boot_is_not_a_trading_process_and_lies_inside_one_corrected_interval(
        self,
    ) -> None:
        refused = [
            line(
                "18:10:00",
                800,
                "trading_bot.main",
                "Startup provenance accepted event=boot_provenance verdict=accepted",
            ),
            line("18:10:00", 800, "trading_bot.main", "Starting in TESTNET mode"),
            line(
                "18:10:12",
                800,
                "trading_bot.main",
                "1 restored record(s) cannot be resolved at boot, so this bot refuses",
                level="ERROR",
            ),
        ]
        lines = seq(
            trading_boot("17:00:00", 700, "17:00:20"),
            [reconcile("18:00:00", 700)],
            refused,
            trading_boot("18:30:00", 900, "18:30:20"),
            [reconcile("18:31:00", 900)],
        )
        frozen, corrected = self.both(lines)
        assert frozen == [
            ("18:00:00", "18:10:00", "700", "800"),
            ("18:10:12", "18:31:00", "800", "900"),
        ]
        assert corrected == [("18:00:00", "18:31:00", "700", "900")]
        processes = {p.pid: p for p in ex.read_processes(lines)}
        assert processes["800"].first_candle is None and processes["900"].first_candle is not None

    def test_strategies_boots_never_count_in_the_corrected_rule_even_when_one_runs_beside_the_bot(
        self,
    ) -> None:
        lines = seq(
            banner("09:00:00", 10),
            banner("09:00:16", 11),
            trading_boot("10:00:00", 20, "10:00:20"),
            [reconcile("10:01:00", 20)],
            banner("11:00:00", 12),
            [reconcile("11:59:00", 20), stopped("12:00:00", 20)],
            trading_boot("12:30:00", 21, "12:30:20"),
            [reconcile("12:45:00", 21)],
        )
        frozen, corrected = self.both(lines)
        # The frozen rule ordered pid 12, a one-line check that started while the bot was trading, between the two
        # trading processes and so is "down" from 11:00:00 (its only line) to the bot's next first pass.
        assert ("11:00:00", "12:45:00", "12", "21") in frozen
        assert ("09:00:00", "09:00:16", "10", "11") in frozen
        assert corrected == [("12:00:00", "12:31:00", "20", "21")]

    def test_nothing_before_the_first_trading_process_or_after_the_last_is_an_interval(
        self,
    ) -> None:
        lines = seq(
            banner("08:00:00", 1),
            trading_boot("10:00:00", 2, "10:00:20"),
            [stopped("12:00:00", 2)],
            banner("12:05:00", 3),
        )
        assert ex.corrected_intervals(ex.read_processes(lines)) == ()

    def test_a_process_that_overlaps_the_one_before_it_makes_no_interval(self) -> None:
        lines = seq(
            trading_boot("10:00:00", 1, "10:00:20"),
            trading_boot("10:30:00", 2, "10:30:20"),
            [reconcile("11:00:00", 1)],
        )
        assert ex.corrected_intervals(ex.read_processes(lines)) == ()


# --------------------------------------------------------------------------------------
# Time, and the entries each rule excludes
# --------------------------------------------------------------------------------------
class TestTimeAndEntries:
    def intervals(self) -> list[ex.DownInterval]:
        return [
            ex.DownInterval(at("12:00:00"), at("12:41:00"), "100", "200"),
            ex.DownInterval(at("16:00:00"), at("16:21:00"), "500", "600"),
        ]

    def test_total_time_sums_every_interval(self) -> None:
        assert ex.total_time(self.intervals()) == timedelta(minutes=41 + 21)
        assert ex.total_time([]) == timedelta(0)

    def test_clipped_time_counts_only_the_part_inside_the_window(self) -> None:
        window = (at("12:30:00"), at("16:10:00"))
        assert ex.clipped_time(self.intervals(), *window) == timedelta(minutes=11 + 10)
        assert ex.clipped_time(self.intervals(), at("13:00:00"), at("15:00:00")) == timedelta(0)

    def test_duration_text_is_hours_minutes_seconds(self) -> None:
        assert ex.duration_text(timedelta(hours=1, minutes=29, seconds=55)) == "1:29:55"
        assert ex.duration_text(timedelta(seconds=7)) == "0:00:07"

    def test_an_entry_is_excluded_inside_an_interval_and_in_the_two_bars_after_it(self) -> None:
        lines = seq(
            trading_boot("10:00:00", 1, "10:00:20"),
            [
                placed("11:30:01", 1, "BTCUSDT", "11:29:59.999000"),
                booked("11:45:00", 1, "BTCUSDT", "1"),
            ],
            [
                placed("12:42:01", 1, "BTCUSDT", "12:41:59.999000"),
                booked("12:50:00", 1, "BTCUSDT", "2"),
            ],
            [
                placed("12:49:01", 1, "ETHUSDT", "12:48:59.999000"),
                booked("12:55:00", 1, "ETHUSDT", "3"),
            ],
        )
        from trade_census import build_trades, parse_capture

        trades = build_trades(parse_capture(lines), "USDT")
        entries, unplaced = ex.live_entries(
            trades, start=at("2026-10-11T00:00:00"), end=at("2026-10-12T00:00:00")
        )
        assert (len(entries), unplaced) == (3, 0)
        timeframes = {"BTCUSDT": "1m", "ETHUSDT": "5m"}
        out = ex.excluded_entries(entries, self.intervals(), timeframes)
        # The 11:29:59.999 signal is before the interval. The 12:41:59.999 BTC signal closes 59 s after the interval
        # ends, inside its two 1m bars (until 12:43:00). The ETH 5m signal at 12:48:59.999 is past that but inside
        # its two 5m bars (until 12:51:00), so a bar length taken from the wrong pair is caught.
        assert [(e.symbol, e.signal_bar_close.strftime("%H:%M:%S")) for e, _ in out] == [
            ("BTCUSDT", "12:41:59"),
            ("ETHUSDT", "12:48:59"),
        ]

    def test_an_entry_on_a_symbol_the_capture_names_no_timeframe_for_is_an_input_error(
        self,
    ) -> None:
        from trade_census import build_trades, parse_capture

        lines = [
            placed("11:30:01", 1, "BTCUSDT", "11:29:59.999000"),
            booked("11:45:00", 1, "BTCUSDT", "1"),
        ]
        trades = build_trades(parse_capture(lines), "USDT")
        entries, _ = ex.live_entries(
            trades, start=at("2026-10-11T00:00:00"), end=at("2026-10-12T00:00:00")
        )
        with pytest.raises(InputError, match="BTCUSDT"):
            ex.excluded_entries(entries, self.intervals(), {})


# --------------------------------------------------------------------------------------
# The whole report, through main
# --------------------------------------------------------------------------------------
def write_capture(tmp_path: Path, lines: list[str], name: str = "capture.log") -> Path:
    path = tmp_path / name
    path.write_bytes(("\n".join(lines) + "\n").encode("utf-8"))
    return path


def scenario_lines() -> list[str]:
    """A clean stop at 12:00:00, a restart at 12:30:00, and four entries around the downtime."""
    return seq(
        trading_boot("10:00:00", 100, "10:00:20"),
        [
            placed("11:30:01", 100, "BTCUSDT", "11:29:59.999000"),
            reconcile("11:31:00", 100),
            booked("11:45:00", 100, "BTCUSDT", "1"),
        ],
        [stopped("12:00:00", 100)],
        trading_boot("12:30:00", 200, "12:30:20"),
        [
            placed("12:40:01", 200, "BTCUSDT", "12:39:59.999000"),
            reconcile("12:41:00", 200),
            booked("12:50:00", 200, "BTCUSDT", "2"),
        ],
        [
            placed("12:59:01", 200, "BTCUSDT", "12:58:59.999000"),
            reconcile("13:00:00", 200),
            booked("13:10:00", 200, "BTCUSDT", "3"),
        ],
    )


class TestMain:
    def run(
        self, tmp_path: Path, lines: list[str], capsys: pytest.CaptureFixture[str], *extra: str
    ) -> tuple[int, str]:
        capture = write_capture(tmp_path, lines)
        status = ex.main(
            [str(capture), "--window-start", WINDOW[0], "--window-end", WINDOW[1], *extra]
        )
        return status, capsys.readouterr().out

    def test_the_report_states_each_rule_its_intervals_and_the_entries_it_excludes(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        status, out = self.run(tmp_path, scenario_lines(), capsys)
        assert status == 0
        # 12:00:00 -> 12:41:00 frozen (41 min), 12:00:00 -> 12:31:00 corrected (31 min).
        assert (
            "frozen rule (down_intervals, imported): 1 interval(s), total 0:41:00, inside the window 0:41:00"
            in out
        )
        assert (
            "corrected rule (R-DC): 1 interval(s), total 0:31:00, inside the window 0:31:00" in out
        )
        assert "2026-10-11T12:00:00Z -> 2026-10-11T12:41:00Z  0:41:00  pid 100 -> pid 200" in out
        assert "2026-10-11T12:00:00Z -> 2026-10-11T12:31:00Z  0:31:00  pid 100 -> pid 200" in out
        # The three entries (signal closes 11:29:59, 12:39:59 and 12:58:59): the middle one only under the frozen rule.
        assert (
            "ENTRIES whose entry bar opens in the window: 3 (bookings with no matched placement: 0)"
            in out
        )
        assert "excluded under the frozen rule    : 1, kept 2" in out
        assert "excluded under the corrected rule : 0, kept 3" in out
        assert "excluded under both               : 0" in out
        assert "only under the frozen rule        : 1" in out
        assert "only under the corrected rule     : 0" in out
        assert "BTCUSDT  signal bar closes 2026-10-11T12:39:59Z  excluded under: frozen" in out

    def test_the_count_arithmetic_is_against_the_floor_of_100_and_states_no_verdict(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        _, out = self.run(tmp_path, scenario_lines(), capsys)
        assert "bookings made in the window (booking time)  : 3" in out
        assert "entries in the window                       : 3" in out
        assert "bookings in the window - excluded       : 2  (below 100)" in out
        assert "entries in the window - excluded        : 2  (below 100)" in out
        assert "bookings in the window - excluded       : 3  (below 100)" in out
        lowered = out.lower()
        for word in ("pass", "fail", "should", "recommend"):
            assert word not in lowered.replace("first pass", "").replace("reconciliation_pass", "")

    def test_every_process_is_listed_with_its_engine_and_first_closed_candle(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        _, out = self.run(tmp_path, scenario_lines() + banner("13:30:00", 7), capsys)
        assert "PROCESSES (3), ordered by first line" in out
        assert (
            "pid 100    first 2026-10-11T10:00:00Z  last 2026-10-11T12:00:00Z  engine started 2026-10-11T10:00:20Z"
            in out
        )
        assert "first closed candle 2026-10-11T12:31:00Z  clean stop no" in out
        assert "engine started none (not a trading process)" in out

    def test_the_header_says_it_is_exploratory_and_names_the_captures_digest(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        import hashlib

        capture = write_capture(tmp_path, scenario_lines())
        digest = hashlib.sha256(capture.read_bytes()).hexdigest()
        assert ex.main([str(capture), "--window-start", WINDOW[0], "--window-end", WINDOW[1]]) == 0
        out = capsys.readouterr().out
        assert (
            "EXPLORATORY (the ratified CHOSEN line 5): never replaces scripts/s4_compare.py's result"
            in out
        )
        assert f"sha256  : {digest}" in out
        assert "window  : [2026-10-11T00:00:00Z, 2026-10-12T00:00:00Z)" in out

    def test_a_capture_under_logs_is_refused_before_a_byte_is_read(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        live = tmp_path / "logs"
        live.mkdir()
        path = write_capture(live, scenario_lines(), name="trading_bot.log")
        assert ex.main([str(path), "--window-start", WINDOW[0], "--window-end", WINDOW[1]]) == 2
        assert "REFUSED" in capsys.readouterr().out

    def test_a_missing_file_and_a_backwards_window_are_refused(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        assert (
            ex.main(
                [str(tmp_path / "nope.log"), "--window-start", WINDOW[0], "--window-end", WINDOW[1]]
            )
            == 2
        )
        assert "is not a file" in capsys.readouterr().out
        capture = write_capture(tmp_path, scenario_lines())
        assert ex.main([str(capture), "--window-start", WINDOW[1], "--window-end", WINDOW[0]]) == 2
        assert "must be after" in capsys.readouterr().out

    def test_a_window_instant_without_a_zone_is_an_argument_error(self, tmp_path: Path) -> None:
        capture = write_capture(tmp_path, scenario_lines())
        with pytest.raises(SystemExit) as caught:
            ex.main(
                [str(capture), "--window-start", "2026-10-11T00:00:00", "--window-end", WINDOW[1]]
            )
        assert caught.value.code == 2

    def test_conflicting_timeframes_are_an_input_error_with_status_three(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        lines = trading_boot("10:00:00", 1, "10:00:20") + trading_boot(
            "11:00:00", 2, "11:00:20", pairs="BTCUSDT/5m"
        )
        status, out = self.run(tmp_path, lines, capsys)
        assert status == 3 and "INPUT ERROR" in out

    def test_it_writes_nothing_beside_the_capture(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        capture = write_capture(tmp_path, scenario_lines())
        before = (sorted(p.name for p in tmp_path.iterdir()), capture.read_bytes())
        ex.main([str(capture), "--window-start", WINDOW[0], "--window-end", WINDOW[1]])
        capsys.readouterr()
        assert (sorted(p.name for p in tmp_path.iterdir()), capture.read_bytes()) == before
