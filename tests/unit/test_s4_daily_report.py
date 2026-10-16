"""``scripts/s4_daily.py``, the reads and the whole report: the bot process, the recorder's task and store, and
``run`` end to end over a clone built in a temporary directory (M5m P122, R-CZ).

The process list and the scheduler's answer are supplied by the test through the script's own seams, so nothing
here starts a process or asks Windows anything; ``TestRealSeams`` replaces the one function that would.
"""

from __future__ import annotations

import argparse
import hashlib
import sys
from datetime import datetime, timedelta
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

import s4_daily as sd

from tests.unit.s4_daily_world import (
    NOW,
    RUN_CMD,
    UTC,
    at,
    booked,
    line,
    provenance,
    starting,
    stopped,
    write_log,
)

# --------------------------------------------------------------------------------------
# The bot process, the recorder, the store
# --------------------------------------------------------------------------------------
CLONE = Path(r"F:\trading bot\deploy\45547f107715")


class TestBotStatus:
    def test_the_last_pid_alive_as_a_run_process(self) -> None:
        processes = [
            sd.ProcessInfo(3444, 3040, "python.exe", RUN_CMD),
            sd.ProcessInfo(5224, 3444, "python3.12.exe", r"C:\x\python.exe -m trading_bot run"),
        ]
        status = sd.bot_status(processes, CLONE, 5224)
        assert status.pid_alive is True
        assert status.launcher_pids == (3444,)

    def test_a_pid_reused_by_another_program_is_not_the_bot(self) -> None:
        processes = [sd.ProcessInfo(5224, 1, "python.exe", "python scripts/check.py")]
        assert sd.bot_status(processes, CLONE, 5224).pid_alive is False

    def test_no_process_with_that_pid_is_not_alive(self) -> None:
        assert (
            sd.bot_status([sd.ProcessInfo(1, 0, "python.exe", RUN_CMD)], CLONE, 5224).pid_alive
            is False
        )

    def test_no_log_pid_is_not_alive(self) -> None:
        assert (
            sd.bot_status([sd.ProcessInfo(1, 0, "python.exe", RUN_CMD)], CLONE, None).pid_alive
            is False
        )

    def test_a_run_of_another_clone_is_not_this_clones_launcher(self) -> None:
        other = r'"F:\trading bot\deploy\other\.venv\Scripts\python.exe" -m trading_bot run'
        assert (
            sd.bot_status([sd.ProcessInfo(9, 0, "python.exe", other)], CLONE, 9).launcher_pids == ()
        )


def write_series(root: Path, symbol: str, interval: str, name: str, rows: list[int]) -> None:
    directory = root / symbol / interval
    directory.mkdir(parents=True, exist_ok=True)
    body = "open_time_ms,open,high,low,close,volume,close_time_ms\n"
    body += "".join(f"{ms},1,1,1,1,1,{ms + 1}\n" for ms in rows)
    (directory / name).write_text(body, encoding="ascii", newline="")


class TestNewestBars:
    def test_the_last_row_of_the_newest_month_of_every_series(self, tmp_path: Path) -> None:
        old, new = 1_790_000_000_000, 1_792_109_040_000
        write_series(tmp_path, "BTCUSDT", "1m", "BTCUSDT-1m-2026-09.csv", [old])
        write_series(tmp_path, "BTCUSDT", "1m", "BTCUSDT-1m-2026-10.csv", [new - 60_000, new])
        write_series(tmp_path, "ETHUSDT", "5m", "ETHUSDT-5m-2026-10.csv", [new - 300_000])
        (tmp_path / "_exchange_info" / "testnet").mkdir(parents=True)  # the recorder's own layout
        bars = sd.newest_bars(tmp_path)
        assert [(b.symbol, b.interval) for b in bars] == [("BTCUSDT", "1m"), ("ETHUSDT", "5m")]
        assert bars[0].open_time == datetime.fromtimestamp(new / 1000, tz=UTC)
        assert bars[0].close_time == bars[0].open_time + timedelta(minutes=1)  # type: ignore[operator]
        assert bars[1].close_time == bars[1].open_time + timedelta(minutes=5)  # type: ignore[operator]

    def test_a_series_that_cannot_be_read_is_reported_and_the_others_are_kept(
        self, tmp_path: Path
    ) -> None:
        write_series(tmp_path, "BTCUSDT", "1m", "a.csv", [1_792_109_040_000])
        write_series(tmp_path, "ETHUSDT", "1m", "b.csv", [])
        (tmp_path / "XRPUSDT" / "1m").mkdir(parents=True)
        (tmp_path / "ADAUSDT" / "weekly").mkdir(parents=True)
        (tmp_path / "ADAUSDT" / "weekly" / "c.csv").write_text("h\n1,1\n", encoding="ascii")
        by_symbol = {b.symbol: b for b in sd.newest_bars(tmp_path)}
        assert by_symbol["BTCUSDT"].problem is None
        assert "holds no row" in (by_symbol["ETHUSDT"].problem or "")
        assert by_symbol["XRPUSDT"].problem == "no csv file"
        assert "unreadable interval" in (by_symbol["ADAUSDT"].problem or "")

    def test_a_missing_store_is_a_probe_error(self, tmp_path: Path) -> None:
        with pytest.raises(sd.ProbeError):
            sd.newest_bars(tmp_path / "nope")

    def test_interval_deltas(self) -> None:
        assert sd.interval_delta("1m") == timedelta(minutes=1)
        assert sd.interval_delta("4h") == timedelta(hours=4)
        assert sd.interval_delta("1d") == timedelta(days=1)


class TestRealSeams:
    def test_the_task_answer_is_read_as_utc_and_a_never_run_task_has_no_last_run(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        answer = {
            "last": "2026-10-16T00:05:01.1234567Z",
            "result": 0,
            "next": "2026-10-16T06:05:00.0000000Z",
            "missed": 0,
        }
        monkeypatch.setattr(sd, "_query", lambda script: answer)
        task = sd.real_task("tb-recorder")
        assert task == sd.TaskInfo(
            at("2026-10-16T00:05:01.123456Z"), 0, at("2026-10-16T06:05:00Z"), 0
        )
        answer["last"] = "1999-11-30T00:00:00.0000000Z"
        answer["result"] = 267011
        assert sd.real_task("tb-recorder").last_run is None

    def test_a_task_answer_that_is_not_an_object_is_a_probe_error(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(sd, "_query", lambda script: [1])
        with pytest.raises(sd.ProbeError):
            sd.real_task("tb-recorder")

    def test_one_process_and_no_process_and_two_are_all_lists(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        row = {"pid": 5, "ppid": 1, "name": "python.exe", "cmd": None}
        for answer, count in (([], 0), (row, 1), ([row, row], 2)):
            monkeypatch.setattr(sd, "_query", lambda script, a=answer: a)
            assert len(sd.real_processes()) == count
        monkeypatch.setattr(sd, "_query", lambda script: row)
        assert sd.real_processes()[0].command_line == ""

    def test_the_queries_ask_only_for_reads(self) -> None:
        import inspect

        source = inspect.getsource(sd.real_processes) + inspect.getsource(sd.real_task)
        for verb in ("Get-CimInstance", "Get-ScheduledTaskInfo"):
            assert verb in source
        for write in (
            "Set-",
            "Start-",
            "Stop-",
            "Remove-",
            "New-",
            "Register-",
            "Unregister-",
            "Invoke-",
        ):
            assert write not in source


# --------------------------------------------------------------------------------------
# The whole report
# --------------------------------------------------------------------------------------
class World:
    """A clone with a rotated log, a recorder store and the seams, all in a temporary directory."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.clone = root / "clone"
        self.logs = self.clone / "logs"
        self.logs.mkdir(parents=True)
        (self.clone / "src").mkdir()
        self.store = root / "recorder" / "data"
        self.scratch = root / "scratch" / "s4"
        self.processes: list[sd.ProcessInfo] = [
            sd.ProcessInfo(5224, 3444, "python3.12.exe", "python -m trading_bot run")
        ]
        self.task: sd.TaskInfo | sd.ProbeError = sd.TaskInfo(
            at("2026-10-16T00:05:01Z"), 0, at("2026-10-16T06:05:00Z"), 0
        )
        write_series(self.store, "BTCUSDT", "1m", "BTCUSDT-1m-2026-10.csv", [1_792_109_040_000])

    def write_logs(self) -> None:
        write_log(
            self.logs / "trading_bot.log.1",
            [
                provenance("2026-10-10T05:58:02Z", 27460),
                provenance("2026-10-10T06:05:20Z", 16076),
                starting("2026-10-10T06:05:20Z", 16076),
                booked("2026-10-10T07:00:00Z", 16076, "1"),
                stopped("2026-10-12T04:17:43Z", 16076),
            ],
        )
        write_log(
            self.logs / "trading_bot.log",
            [
                provenance("2026-10-15T11:16:55Z", 5224),
                starting("2026-10-15T11:16:55Z", 5224),
                booked("2026-10-15T12:00:00Z", 5224, "2", event="exit_booked"),
                line(
                    "2026-10-16T05:27:01Z",
                    5224,
                    "trading_bot.execution.reconciliation_driver",
                    "x event=reconciliation_pass",
                ),
            ],
        )

    def env(self, now: datetime = NOW) -> sd.Environment:
        def read_task(name: str) -> sd.TaskInfo:
            if isinstance(self.task, sd.ProbeError):
                raise self.task
            return self.task

        return sd.Environment(now, lambda: self.processes, read_task)

    def args(self) -> argparse.Namespace:
        return argparse.Namespace(
            clone=self.clone, recorder_root=self.store, task="tb-recorder", scratch=self.scratch
        )


@pytest.fixture
def world(tmp_path: Path) -> World:
    w = World(tmp_path)
    w.write_logs()
    return w


def text_of(report: list[str]) -> str:
    return "\n".join(report)


class TestRun:
    def test_the_report_states_each_figure_the_ruling_names(self, world: World) -> None:
        status, report = sd.run(world.args(), world.env())
        text = text_of(report)
        assert status == 0
        assert "last pid in the log : 5224" in text
        assert "alive as a '-m trading_bot run' process : yes" in text
        assert (
            "log's last line : 2026-10-16T05:27:01Z (capture line 9), 0d 00h 02m 59s before now"
            in text
        )
        assert (
            "task tb-recorder: last run 2026-10-16T00:05:01Z, last result 0 (extended, or already current)"
            in text
        )
        assert (
            "BTCUSDT 1m: newest bar opens 2026-10-16T00:04:00Z, closed 0d 05h 25m 00s before now"
            in text
        )
        assert (
            "T0 from the log (first run boot) : 2026-10-10T06:05:20Z  pid 16076  = the ruled T0"
            in text
        )
        assert "boots at or after T0 : 2 (2 run)" in text
        assert (
            "2026-10-10T06:05:20Z  pid 16076" in text
            and "pid 27460" not in text.split("boots since T0")[1]
        )
        assert "bookings since T0 : 2" in text
        assert "bookings since T0 : 2 against 150  (short by 148)" in text
        assert "earliest stop : 2026-11-01T00:00:00Z" in text
        assert "cap : 2026-11-14T06:05:20Z" in text

    def test_it_freezes_every_file_under_the_utc_date_and_writes_the_report_beside_them(
        self, world: World
    ) -> None:
        _, report = sd.run(world.args(), world.env())
        day = world.scratch / "2026-10-16"
        names = sorted(p.name for p in day.iterdir())
        assert names == [
            "053000Z-SHA256SUMS.txt",
            "053000Z-capture.log",
            "053000Z-report.txt",
            "053000Z-trading_bot.log",
            "053000Z-trading_bot.log.1",
        ]
        assert (day / "053000Z-report.txt").read_text(encoding="utf-8") == text_of(report) + "\n"
        capture = (day / "053000Z-capture.log").read_bytes()
        assert (
            capture
            == (world.logs / "trading_bot.log.1").read_bytes()
            + (world.logs / "trading_bot.log").read_bytes()
        )
        assert hashlib.sha256(capture).hexdigest() in text_of(report)

    def test_a_file_outside_the_capture_and_a_changed_set_are_both_in_the_report(
        self, world: World, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        (world.logs / "trading_bot.log.bak").write_bytes(b"stray")
        real = sd.log_family
        answers = iter([real(world.logs), sd.LogFamily((), ())])
        monkeypatch.setattr(sd, "log_family", lambda directory: next(answers))
        _, report = sd.run(world.args(), world.env())
        text = text_of(report)
        assert "trading_bot.log.bak" in text and "outside the capture" in text
        assert "WARNING: the set of log files changed while it was being copied" in text

    def test_the_clone_is_untouched(self, world: World) -> None:
        before = {str(p): (p.read_bytes() if p.is_file() else None) for p in world.clone.rglob("*")}
        sd.run(world.args(), world.env())
        assert {
            str(p): (p.read_bytes() if p.is_file() else None) for p in world.clone.rglob("*")
        } == before

    def test_a_failed_task_query_and_a_failed_process_query_are_reported_and_the_rest_goes_on(
        self, world: World
    ) -> None:
        world.task = sd.ProbeError("denied")

        def broken() -> list[sd.ProcessInfo]:
            raise sd.ProbeError("no powershell")

        env = sd.Environment(NOW, broken, world.env().read_task)
        status, report = sd.run(world.args(), env)
        text = text_of(report)
        assert status == 0
        assert "process list unavailable: no powershell" in text
        assert "task tb-recorder unavailable: denied" in text
        assert "bookings since T0 : 2" in text

    def test_a_missing_recorder_store_is_reported(self, world: World) -> None:
        args = world.args()
        args.recorder_root = world.root / "nope"
        _, report = sd.run(args, world.env())
        assert "recorder store unavailable" in text_of(report)

    def test_a_dead_bot_and_a_stale_log_are_stated_as_facts(self, world: World) -> None:
        world.processes = []
        _, report = sd.run(world.args(), world.env(NOW + timedelta(hours=3)))
        text = text_of(report)
        assert "alive as a '-m trading_bot run' process : no" in text
        # The whole line, so the sign is pinned: "-0d 03h 02m 59s before now" also ends in the short form.
        assert "(capture line 9), 0d 03h 02m 59s before now" in text

    def test_a_t0_that_differs_from_the_logs_first_run_boot_is_said_to_differ(
        self, world: World
    ) -> None:
        _, report = sd.run(world.args(), world.env(), t0=at("2026-10-10T05:58:02Z"))
        assert "DIFFERS from the ruled T0" in text_of(report)

    def test_the_report_gives_no_verdict(self, world: World) -> None:
        _, report = sd.run(world.args(), world.env())
        text = text_of(report).lower()
        for word in ("pass", "fail", "verdict:", "should", "recommend", "stop now", "has ended"):
            assert word not in text.replace("verdict=", "")

    def test_a_destination_inside_the_clone_is_refused_before_anything_is_written(
        self, world: World
    ) -> None:
        args = world.args()
        args.scratch = world.clone / "scratch"
        before = sorted(str(p) for p in world.root.rglob("*"))
        status, report = sd.run(args, world.env())
        assert status == 2 and report[0].startswith("REFUSED:")
        assert sorted(str(p) for p in world.root.rglob("*")) == before

    def test_a_rerun_in_the_same_second_is_refused_and_leaves_the_first_freeze(
        self, world: World
    ) -> None:
        sd.run(world.args(), world.env())
        day = world.scratch / "2026-10-16"
        before = {p.name: p.read_bytes() for p in day.iterdir()}
        status, report = sd.run(world.args(), world.env())
        assert status == 2 and "never overwrites" in report[0]
        assert {p.name: p.read_bytes() for p in day.iterdir()} == before

    def test_the_default_destination_and_inputs_are_the_documented_ones(self) -> None:
        assert Path(r"F:\trading bot\scratch\s4") == sd.SCRATCH_ROOT
        assert Path(r"F:\trading bot\deploy\45547f107715") == sd.CLONE
        assert (
            Path(r"F:\trading bot\recorder\45547f107715\data\historical_testnet")
            == sd.RECORDER_ROOT
        )
        assert sd.TASK_NAME == "tb-recorder"
        parsed = sd._build_parser().parse_args([])
        assert (parsed.clone, parsed.scratch, parsed.task) == (
            sd.CLONE,
            sd.SCRATCH_ROOT,
            "tb-recorder",
        )
