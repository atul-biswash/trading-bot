"""``scripts/s4_daily.py``, the pure parts: the stop rule's arithmetic, the boots, the bookings and the freeze
(M5m P122, R-CZ).

Every input is synthetic: a log written to a temporary directory, and figures worked by hand in the test, because a
check whose expected values came from its own output proves nothing. The expensive failures here are silent ones, as
in ``scripts/trade_census.py``: a ``strategies`` boot counted as T0, a rotated file left out of the capture, a stop
rule off by one at a boundary, and a freeze that overwrites or lands inside a clone each give a plausible report.
The process list, the scheduler, the recorder store and the whole report are in ``test_s4_daily_report.py``.
"""

from __future__ import annotations

import hashlib
import sys
from datetime import datetime, timedelta
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

import s4_daily as sd

from tests.unit.s4_daily_world import (
    NOW,
    REPO,
    T0,
    UTC,
    at,
    booked,
    line,
    provenance,
    starting,
    stopped,
)
from trading_bot.engine.live_engine import _EVENT_STOPPED


# --------------------------------------------------------------------------------------
# The stop rule's arithmetic
# --------------------------------------------------------------------------------------
class TestStopArithmetic:
    def arithmetic(self, now: str, bookings: int, t0: datetime = T0) -> sd.StopArithmetic:
        return sd.stop_arithmetic(t0=t0, now=at(now), bookings=bookings)

    def test_the_earliest_stop_and_the_cap_of_the_real_run(self) -> None:
        a = self.arithmetic("2026-10-16T05:30:00Z", 83)
        assert a.earliest_stop == at("2026-11-01T00:00:00Z")
        assert a.cap == at("2026-11-14T06:05:20Z")

    def test_a_t0_that_is_a_midnight_makes_the_instant_21_days_on_the_earliest_stop(self) -> None:
        midnight = at("2026-10-10T00:00:00Z")
        a = self.arithmetic("2026-10-12T00:00:00Z", 0, t0=midnight)
        assert a.earliest_stop == at("2026-10-31T00:00:00Z")

    def test_a_t0_one_second_after_a_midnight_waits_for_the_next(self) -> None:
        a = self.arithmetic("2026-10-12T00:00:00Z", 0, t0=at("2026-10-10T00:00:01Z"))
        assert a.earliest_stop == at("2026-11-01T00:00:00Z")

    def test_the_earliest_stop_is_inclusive_at_the_boundary(self) -> None:
        before = self.arithmetic("2026-10-31T23:59:59Z", 150)
        on = self.arithmetic("2026-11-01T00:00:00Z", 150)
        assert before.now_at_or_after_earliest is False
        assert on.now_at_or_after_earliest is True

    def test_150_bookings_meet_the_requirement_and_149_do_not(self) -> None:
        short = self.arithmetic("2026-10-16T05:30:00Z", 149)
        met = self.arithmetic("2026-10-16T05:30:00Z", 150)
        assert (short.bookings_meet_required, short.bookings_short) == (False, 1)
        assert (met.bookings_meet_required, met.bookings_short) == (True, 0)
        assert self.arithmetic("2026-10-16T05:30:00Z", 151).bookings_short == 0

    def test_the_next_midnight_is_strictly_after_now(self) -> None:
        assert self.arithmetic("2026-10-16T05:30:00Z", 0).next_midnight == at(
            "2026-10-17T00:00:00Z"
        )
        assert self.arithmetic("2026-10-17T00:00:00Z", 0).next_midnight == at(
            "2026-10-18T00:00:00Z"
        )

    def test_both_conditions_at_the_next_midnight_need_the_time_and_the_count(self) -> None:
        # 2026-10-31T10:00Z: the next midnight is 11-01, which is the earliest stop.
        assert self.arithmetic("2026-10-31T10:00:00Z", 150).stops_at_next_midnight is True
        assert self.arithmetic("2026-10-31T10:00:00Z", 149).stops_at_next_midnight is False
        # one day earlier the next midnight (10-31) is before the earliest stop.
        assert self.arithmetic("2026-10-30T10:00:00Z", 500).stops_at_next_midnight is False

    def test_the_cap_is_inclusive_and_the_floor_is_100(self) -> None:
        assert self.arithmetic("2026-11-14T06:05:19Z", 100).now_at_or_after_cap is False
        assert self.arithmetic("2026-11-14T06:05:20Z", 100).now_at_or_after_cap is True
        assert self.arithmetic("2026-11-14T06:05:20Z", 99).bookings_meet_floor is False
        assert self.arithmetic("2026-11-14T06:05:20Z", 100).bookings_meet_floor is True

    def test_elapsed_days_are_measured_from_t0(self) -> None:
        a = self.arithmetic("2026-10-31T06:05:20Z", 0)
        assert a.elapsed == timedelta(days=21)
        assert sd.duration_text(a.elapsed) == "21d 00h 00m 00s"
        assert sd.duration_text(timedelta(hours=-1, seconds=-5)) == "-0d 01h 00m 05s"

    def test_the_constants_are_the_pre_registered_ones(self) -> None:
        text = (REPO / "docs" / "S4_PREREGISTRATION.md").read_text(encoding="utf-8")
        assert "plus 21 days" in text and sd.MINIMUM_DAYS == 21
        assert "plus 35 days" in text and sd.CAP_DAYS == 35
        assert "**150** bookings" in text and sd.REQUIRED_BOOKINGS == 150
        assert "at least 100 bookings" in text and sd.FLOOR_BOOKINGS == 100
        assert at("2026-10-10T06:05:20Z") == sd.T0


# --------------------------------------------------------------------------------------
# Boots
# --------------------------------------------------------------------------------------
class TestBoots:
    def facts(self, lines: list[str]) -> sd.LogFacts:
        return sd.read_log(lines)

    def test_a_strategies_boot_is_neither_t0_nor_a_run_boot(self) -> None:
        facts = self.facts(
            [
                provenance("2026-10-10T05:58:02Z", 27460),
                provenance("2026-10-10T05:58:17Z", 27176),
                provenance("2026-10-10T06:05:20Z", 16076),
                starting("2026-10-10T06:05:20Z", 16076),
            ]
        )
        first = sd.first_run_boot(facts.boots)
        assert first is not None
        assert (first.pid, first.stamp) == (16076, T0)
        kinds = [(boot.pid, boot.kind) for boot in facts.boots]
        assert kinds == [(27460, "other"), (27176, "other"), (16076, "run")]

    def test_a_strategies_boot_after_t0_is_listed_and_is_not_a_run_boot(self) -> None:
        facts = self.facts(
            [
                provenance("2026-10-10T06:05:20Z", 1),
                starting("2026-10-10T06:05:20Z", 1),
                provenance("2026-10-12T09:00:00Z", 2),
            ]
        )
        since = sd.boots_since(facts.boots, T0)
        assert [(b.pid, b.kind) for b in since] == [(1, "run"), (2, "other")]

    def test_boots_before_t0_are_not_since_t0(self) -> None:
        facts = self.facts(
            [
                provenance("2026-10-10T05:58:02Z", 1),
                provenance("2026-10-10T06:05:20Z", 2),
                starting("2026-10-10T06:05:20Z", 2),
            ]
        )
        assert [b.pid for b in sd.boots_since(facts.boots, T0)] == [2]

    def test_a_pid_that_boots_twice_has_each_run_attributed_to_its_own_boot(self) -> None:
        facts = self.facts(
            [
                provenance("2026-10-10T06:05:20Z", 7),
                starting("2026-10-10T06:05:20Z", 7),
                stopped("2026-10-12T04:17:43Z", 7),
                provenance("2026-10-13T00:00:00Z", 7),
            ]
        )
        first, second = facts.boots
        assert (first.kind, first.clean_stop) == ("run", True)
        assert (second.kind, second.clean_stop) == ("other", False)

    def test_the_verdict_and_the_clean_stop_marker_are_read_per_boot(self) -> None:
        facts = self.facts(
            [
                provenance("2026-10-10T06:05:20Z", 1, verdict="refused"),
                starting("2026-10-10T06:05:20Z", 1),
                stopped("2026-10-11T00:00:00Z", 1),
                provenance("2026-10-11T00:01:00Z", 2),
                starting("2026-10-11T00:01:00Z", 2),
            ]
        )
        assert [(b.verdict, b.clean_stop) for b in facts.boots] == [
            ("refused", True),
            ("accepted", False),
        ]

    def test_a_boot_line_without_a_verdict_is_unread_not_accepted(self) -> None:
        facts = self.facts(
            [line("2026-10-10T06:05:20Z", 1, "trading_bot.main", "x event=boot_provenance")]
        )
        assert facts.boots[0].verdict == "unread"

    def test_the_last_stamped_line_and_pid_ignore_unstamped_continuation_lines(self) -> None:
        facts = self.facts(
            [
                line("2026-10-10T06:05:20Z", 1, "trading_bot.main", "a"),
                line("2026-10-10T06:06:00Z", 2, "trading_bot.main", "b"),
                "  ____  banner continuation",
                "",
            ]
        )
        assert (facts.last_stamp, facts.last_pid, facts.last_line_no) == (
            at("2026-10-10T06:06:00Z"),
            2,
            2,
        )

    def test_an_empty_log_has_no_last_line(self) -> None:
        facts = self.facts([])
        assert (facts.last_stamp, facts.last_pid, facts.boots) == (None, None, ())

    def test_the_markers_are_the_ones_the_bot_logs(self) -> None:
        main_source = (REPO / "src" / "trading_bot" / "main.py").read_text(encoding="utf-8")
        assert 'log.info("Starting in %s mode", settings.mode.value.upper())' in main_source
        assert '_EVENT_BOOT_PROVENANCE = "boot_provenance"' in main_source
        assert _EVENT_STOPPED == "engine_stopped"
        assert "event=boot_provenance" in provenance("2026-10-10T06:05:20Z", 1)


# --------------------------------------------------------------------------------------
# Bookings
# --------------------------------------------------------------------------------------
class TestBookings:
    def test_the_three_booking_events_are_counted_since_t0_by_the_census_parser(self) -> None:
        lines = [
            booked("2026-10-10T06:10:00Z", 1, "1"),
            booked("2026-10-10T07:00:00Z", 1, "2", event="exit_booked"),
            booked("2026-10-10T08:00:00Z", 1, "3", event="boot_exit_booked"),
        ]
        counted = sd.count_bookings(lines, T0)
        assert counted.since_t0 == 3
        assert counted.by_event == (
            ("boot_exit_booked", 1),
            ("close_booked", 1),
            ("exit_booked", 1),
        )
        assert counted.raw_lines_since_t0 == 3
        assert (counted.before_t0, counted.unzoned, counted.anomalies) == (0, 0, 0)

    def test_a_booking_before_t0_is_not_since_t0(self) -> None:
        lines = [booked("2026-10-10T06:05:19Z", 1, "1"), booked("2026-10-10T06:05:20Z", 1, "2")]
        counted = sd.count_bookings(lines, T0)
        assert (counted.since_t0, counted.before_t0, counted.raw_lines_since_t0) == (1, 1, 1)

    def test_a_duplicate_order_is_the_censuss_anomaly_and_is_not_counted(self) -> None:
        lines = [booked("2026-10-11T00:00:00Z", 1, "9"), booked("2026-10-11T00:00:01Z", 1, "9")]
        counted = sd.count_bookings(lines, T0)
        assert (counted.since_t0, counted.anomalies, counted.raw_lines_since_t0) == (1, 1, 2)

    def test_a_placement_or_a_refusal_is_not_a_booking(self) -> None:
        lines = [
            line(
                "2026-10-11T00:00:00Z",
                1,
                "trading_bot.execution.executor",
                "x event=order_placed symbol=BTCUSDT",
            )
        ]
        assert sd.count_bookings(lines, T0).since_t0 == 0

    def test_the_booking_events_are_the_censuss_own(self) -> None:
        assert (sd.EVENT_CLOSE_BOOKED, sd.EVENT_EXIT_BOOKED, sd.EVENT_BOOT_EXIT_BOOKED) == (
            "close_booked",
            "exit_booked",
            "boot_exit_booked",
        )


# --------------------------------------------------------------------------------------
# The freeze
# --------------------------------------------------------------------------------------
class TestFreeze:
    def make_logs(self, root: Path) -> Path:
        logs = root / "clone" / "logs"
        logs.mkdir(parents=True)
        (logs / "trading_bot.log").write_bytes(b"active line\r\n")
        (logs / "trading_bot.log.1").write_bytes(b"newer rotated\r\n")
        (logs / "trading_bot.log.2").write_bytes(b"older rotated\r\n")
        (logs / "trading_bot.log.10").write_bytes(b"oldest rotated\r\n")
        (logs / ".bot.lock").write_bytes(b"123")
        (logs / "release.log").write_bytes(b"not ours")
        return logs

    def test_the_family_is_every_trading_bot_log_file_and_nothing_else(
        self, tmp_path: Path
    ) -> None:
        logs = self.make_logs(tmp_path)
        (logs / "trading_bot.log.bak").write_bytes(b"x")
        family = sd.log_family(logs)
        assert [p.name for p in family.ordered] == [
            "trading_bot.log.10",
            "trading_bot.log.2",
            "trading_bot.log.1",
            "trading_bot.log",
        ]
        assert [p.name for p in family.outside] == ["trading_bot.log.bak"]

    def test_a_rotated_log_is_frozen_with_every_file_and_a_digest_for_each(
        self, tmp_path: Path
    ) -> None:
        logs = self.make_logs(tmp_path)
        freeze = sd.freeze_family(logs, tmp_path / "scratch" / "s4" / "2026-10-16", NOW, ())
        assert [f.source.name for f in freeze.files] == [
            "trading_bot.log.10",
            "trading_bot.log.2",
            "trading_bot.log.1",
            "trading_bot.log",
        ]
        for item in freeze.files:
            data = item.copy.read_bytes()
            assert data == item.source.read_bytes()
            assert (item.size, item.sha256) == (len(data), hashlib.sha256(data).hexdigest())
        expected = b"oldest rotated\r\nolder rotated\r\nnewer rotated\r\nactive line\r\n"
        assert freeze.capture.read_bytes() == expected
        assert freeze.capture_sha256 == hashlib.sha256(expected).hexdigest()
        assert freeze.capture_size == len(expected)

    def test_a_file_with_another_suffix_is_frozen_and_kept_out_of_the_capture(
        self, tmp_path: Path
    ) -> None:
        logs = self.make_logs(tmp_path)
        (logs / "trading_bot.log.bak").write_bytes(b"stray")
        freeze = sd.freeze_family(logs, tmp_path / "scratch" / "d", NOW, ())
        assert [f.source.name for f in freeze.outside] == ["trading_bot.log.bak"]
        assert freeze.outside[0].copy.read_bytes() == b"stray"
        assert b"stray" not in freeze.capture.read_bytes()

    def test_the_sums_file_names_every_copy_and_the_capture(self, tmp_path: Path) -> None:
        logs = self.make_logs(tmp_path)
        freeze = sd.freeze_family(logs, tmp_path / "d", NOW, ())
        sums = (tmp_path / "d" / f"{freeze.stamp}-SHA256SUMS.txt").read_text(encoding="ascii")
        for item in freeze.files:
            assert f"{item.sha256}  {item.copy.name}" in sums
        assert f"{freeze.capture_sha256}  {freeze.capture.name}" in sums

    def test_the_source_is_unchanged_and_nothing_is_written_beside_it(self, tmp_path: Path) -> None:
        logs = self.make_logs(tmp_path)
        before = {p.name: (p.read_bytes(), p.stat().st_mtime_ns) for p in logs.iterdir()}
        clone = logs.parent
        tree_before = sorted(str(p) for p in clone.rglob("*"))
        sd.freeze_family(logs, tmp_path / "scratch" / "d", NOW, (clone,))
        assert {p.name: (p.read_bytes(), p.stat().st_mtime_ns) for p in logs.iterdir()} == before
        assert sorted(str(p) for p in clone.rglob("*")) == tree_before

    def test_a_log_a_writer_still_holds_open_is_copied(self, tmp_path: Path) -> None:
        logs = self.make_logs(tmp_path)
        with (logs / "trading_bot.log").open("ab") as writer:
            writer.write(b"appended while open\r\n")
            writer.flush()
            freeze = sd.freeze_family(logs, tmp_path / "d", NOW, ())
        assert freeze.files[-1].copy.read_bytes().endswith(b"appended while open\r\n")

    def test_a_freeze_never_overwrites(self, tmp_path: Path) -> None:
        logs = self.make_logs(tmp_path)
        destination = tmp_path / "d"
        sd.freeze_family(logs, destination, NOW, ())
        before = {p.name: p.read_bytes() for p in destination.iterdir()}
        with pytest.raises(sd.FreezeRefusedError, match="never overwrites"):
            sd.freeze_family(logs, destination, NOW, ())
        assert {p.name: p.read_bytes() for p in destination.iterdir()} == before

    def test_a_second_freeze_a_second_later_keeps_the_first(self, tmp_path: Path) -> None:
        logs = self.make_logs(tmp_path)
        first = sd.freeze_family(logs, tmp_path / "d", NOW, ())
        second = sd.freeze_family(logs, tmp_path / "d", NOW + timedelta(seconds=1), ())
        assert first.stamp != second.stamp
        assert first.capture.is_file() and second.capture.is_file()

    @pytest.mark.parametrize(
        ("where", "message"),
        [
            ("bare_logs", r"logs/ directory"),
            ("protected", r"which is a clone"),
            ("git", r"holds a \.git entry"),
        ],
    )
    def test_a_destination_inside_a_clone_is_refused_by_each_guard_alone(
        self, tmp_path: Path, where: str, message: str
    ) -> None:
        # Each case is caught by exactly one of the three guards, so removing any one fails one case.
        logs = self.make_logs(tmp_path)
        (tmp_path / "recorder").mkdir()
        (tmp_path / "repo" / ".git").mkdir(parents=True)
        targets = {
            "bare_logs": tmp_path / "elsewhere" / "logs" / "frozen",
            "protected": tmp_path / "recorder" / "x",
            "git": tmp_path / "repo" / "scratch",
        }
        before = sorted(str(p) for p in tmp_path.rglob("*"))
        with pytest.raises(sd.FreezeRefusedError, match=message):
            sd.freeze_family(logs, targets[where], NOW, (tmp_path / "recorder",))
        assert sorted(str(p) for p in tmp_path.rglob("*")) == before

    def test_a_set_of_files_that_changed_while_it_was_copied_is_flagged(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        logs = self.make_logs(tmp_path)
        real = sd.log_family
        answers = iter([real(logs), sd.LogFamily((logs / "trading_bot.log",), ())])
        monkeypatch.setattr(sd, "log_family", lambda directory: next(answers))
        assert sd.freeze_family(logs, tmp_path / "d", NOW, ()).family_changed is True
        monkeypatch.setattr(sd, "log_family", real)
        assert sd.freeze_family(logs, tmp_path / "e", NOW, ()).family_changed is False

    def test_a_directory_with_no_log_files_is_refused(self, tmp_path: Path) -> None:
        empty = tmp_path / "logs"
        empty.mkdir()
        with pytest.raises(sd.FreezeRefusedError, match=r"holds no trading_bot\.log"):
            sd.freeze_family(empty, tmp_path / "d", NOW, ())

    def test_a_missing_log_directory_is_refused(self, tmp_path: Path) -> None:
        with pytest.raises(sd.FreezeRefusedError, match="not a directory"):
            sd.freeze_family(tmp_path / "nope", tmp_path / "d", NOW, ())


class TestHelpers:
    def test_utc_text(self) -> None:
        assert sd.utc_text(None) == "none"
        assert (
            sd.utc_text(datetime(2026, 10, 16, 5, 30, 0, 999, tzinfo=UTC)) == "2026-10-16T05:30:00Z"
        )

    def test_the_midnight_helpers(self) -> None:
        assert sd.first_midnight_at_or_after(at("2026-10-31T00:00:00Z")) == at(
            "2026-10-31T00:00:00Z"
        )
        assert sd.first_midnight_at_or_after(at("2026-10-31T00:00:01Z")) == at(
            "2026-11-01T00:00:00Z"
        )
        assert sd.next_utc_midnight(at("2026-10-31T00:00:00Z")) == at("2026-11-01T00:00:00Z")
