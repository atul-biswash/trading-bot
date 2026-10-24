"""``scripts/s4_latch_compare.py``: the E2 wrapper (M5m P130, R-DL, R-DM, R-DO, R-DP).

Every capture here is a few synthetic lines in the shape the bot logs, and every interval and count is worked by hand
beside the assertion that pins it, because a tool whose expected values were taken from its own output proves nothing.
The shapes are the ones the S4 run produced: a latch that clears by itself, one that ends with the process, one ended by
a clean stop, one still open at the capture's end, and a lone position that is ``diverged`` (R-DP). The frozen
``s4_compare`` is imported and run as it stands; where the wrapper must agree with it a test says so.
"""

from __future__ import annotations

import ast
import csv
import dataclasses
import json
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import ClassVar

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

import s4_compare as s4
import s4_latch_compare as e2

from trading_bot.backtesting.simulated_executor import SimulatedTrade
from trading_bot.core.portfolio import _TRUSTED_PROTECTION

UTC = timezone.utc
DAY = "2026-10-12"
WINDOW = ("2026-10-12T00:00:00Z", "2026-10-13T00:00:00Z")
M = datetime(2026, 10, 13, tzinfo=UTC)
VERDICT_WORDS = re.compile(r"\b(PASS|PASSES|PASSED|FAIL|FAILS|FAILED|INCONCLUSIVE)\b")
SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "s4_latch_compare.py"


def t(clock: str, day: str = DAY) -> str:
    return f"{day}T{clock}"


def at(clock: str, day: str = DAY) -> datetime:
    return datetime.fromisoformat(f"{day}T{clock}+00:00")


def line(stamp: str, pid: int, text: str, level: str = "INFO") -> str:
    return f"{stamp}Z | {level:<8} | pid={pid} | trading_bot.x | {text}"


def recon(stamp: str, pid: int, positions: int, states: str) -> str:
    return line(
        stamp,
        pid,
        f"Reconciled {positions} position(s) event=reconciliation_pass positions={positions} "
        f'calls={positions} queries=1 states="{states}"',
    )


def untrusted(stamp: str, pid: int, symbols: str = "BTCUSDT") -> str:
    return line(
        stamp,
        pid,
        f"1 position(s) carry protection this bot does not trust event=reconciliation_untrusted "
        f'count=1 symbols={symbols} detail="x"',
        "WARNING",
    )


def place(stamp: str, pid: int, symbol: str, signal: str) -> str:
    return line(
        stamp,
        pid,
        f"Order list placed event=order_placed symbol={symbol} quantity=1 entry=100 stop_loss=98 "
        f"order_list_id=7 list_client_order_id=tb1-{symbol}-1-0-L entry_bar_time={signal}+00:00",
    )


def book(stamp: str, pid: int, symbol: str, event: str = "close_booked") -> str:
    return line(
        stamp,
        pid,
        f"Closed {symbol} event={event} symbol={symbol} order_id=1 quantity=1 quote_total=101 "
        f"realised=1 candle_time={stamp}.999000+00:00",
    )


def refuse(stamp: str, pid: int, symbol: str = "BTCUSDT") -> str:
    return line(
        stamp,
        pid,
        f"Risk refused {symbol} at committed_risk_unknown event=risk_refused symbol={symbol} "
        f"timeframe=1m action=BUY signal_ts={stamp}.999000+00:00 stage=committed_risk_unknown reason=x",
    )


def halted(stamp: str, pid: int) -> str:
    return line(
        stamp,
        pid,
        "Dispatch refused event=dispatch_refused symbol=BTCUSDT action=CLOSE reason=close_halted",
        "WARNING",
    )


def stopped(stamp: str, pid: int, clean: str = "True") -> str:
    return line(stamp, pid, f"Trading engine stopped event=engine_stopped clean_shutdown={clean}")


def idle(stamp: str, pid: int) -> str:
    return line(stamp, pid, "tick")


def boot(stamp: str, pid: int, verdict: str = "accepted", reasons: str = "none") -> str:
    return line(
        stamp,
        pid,
        f"Startup provenance {verdict} event=boot_provenance verdict={verdict} "
        f"refusal_reasons={reasons} unknown_reasons=none install_kind=vcs code_intact=true",
    )


def sink(lines: list[str]) -> list[e2.LatchEpisode]:
    return list(e2.latch_episodes(lines, closed_at=M))


def span(episode: e2.LatchEpisode) -> tuple[datetime, datetime]:
    return episode.start, episode.end


def latch_passes(
    pid: int,
    clocks: list[str],
    states: str = "unknown=1",
    positions: int = 1,
    symbols: str = "BTCUSDT",
) -> list[str]:
    out: list[str] = []
    for clock in clocks:
        out += [recon(t(clock), pid, positions, states), untrusted(t(clock), pid, symbols)]
    return out


# --------------------------------------------------------------------------------------
# The trusted set is the code's own
# --------------------------------------------------------------------------------------
class TestTheTrustedSet:
    def test_it_is_the_value_names_of_the_whitelist_the_portfolio_refuses_entries_by(self) -> None:
        assert frozenset(state.value for state in _TRUSTED_PROTECTION) == e2.TRUSTED_STATES
        assert {"active", "absent_by_design"} == e2.TRUSTED_STATES

    def test_it_is_imported_and_never_restated_in_the_script(self) -> None:
        tree = ast.parse(SCRIPT.read_text(encoding="utf-8"))
        imported = {
            alias.name
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom) and node.module == "trading_bot.core.portfolio"
            for alias in node.names
        }
        assert "_TRUSTED_PROTECTION" in imported
        literals = {
            node.value
            for node in ast.walk(tree)
            if isinstance(node, ast.Constant) and isinstance(node.value, str)
        }
        assert not literals & {"active", "absent_by_design", "unknown", "diverged", "pending"}


# --------------------------------------------------------------------------------------
# The states field and the break test (R-DO, R-DP)
# --------------------------------------------------------------------------------------
class TestStates:
    def test_the_field_reads_as_name_and_count_pairs(self) -> None:
        text = recon(t("00:00:00"), 1, 2, "active=1,unknown=1")
        assert e2.parse_states(text) == (("active", 1), ("unknown", 1))

    @pytest.mark.parametrize("states", ["", "active", "active=x", "=1", "active=1,"])
    def test_an_absent_empty_or_unreadable_field_is_none_and_never_trusted(
        self, states: str
    ) -> None:
        text = f'event=reconciliation_pass positions=1 states="{states}"'
        assert e2.parse_states(text) is None

    def test_a_line_without_the_field_is_none(self) -> None:
        assert e2.parse_states("event=reconciliation_pass positions=1") is None


def one_pass(
    positions: int, inventory: set[str], states: str | None, clock: str = "00:10:00"
) -> e2.ReconPass:
    text = line(t(clock), 1, "x") if states is None else recon(t(clock), 1, positions, states)
    row = e2.LogRow(1, at(clock), "1", text)
    return e2.ReconPass(row, positions, frozenset(inventory), e2.parse_states(text))


class TestWhenAPassBreaksARun:
    def test_a_full_coverage_all_active_pass_breaks(self) -> None:
        assert e2.can_break(one_pass(2, {"BTCUSDT", "ETHUSDT"}, "active=2"))

    def test_a_lone_position_reported_active_breaks(self) -> None:
        assert e2.can_break(one_pass(1, {"BTCUSDT"}, "active=1"))

    def test_an_absent_by_design_position_is_trusted_and_breaks(self) -> None:
        assert e2.can_break(one_pass(1, {"BTCUSDT"}, "absent_by_design=1"))

    def test_a_pass_covering_fewer_positions_than_the_inventory_breaks_nothing(self) -> None:
        assert not e2.can_break(one_pass(1, {"BTCUSDT", "ETHUSDT"}, "active=1"))

    def test_a_pass_reporting_more_positions_than_the_inventory_holds_breaks_nothing(self) -> None:
        assert not e2.can_break(one_pass(2, {"BTCUSDT"}, "active=2"))

    def test_an_unknown_count_among_trusted_ones_breaks_nothing(self) -> None:
        assert not e2.can_break(one_pass(2, {"BTCUSDT", "ETHUSDT"}, "active=1,unknown=1"))

    @pytest.mark.parametrize("states", ["diverged=1", "pending=1", "unknown=1", "unheard_of=1"])
    def test_any_state_outside_the_trusted_set_named_or_not_breaks_nothing(
        self, states: str
    ) -> None:
        assert not e2.can_break(one_pass(1, {"BTCUSDT"}, states))

    def test_a_trusted_and_an_untrusted_state_together_break_nothing(self) -> None:
        assert not e2.can_break(one_pass(2, {"BTCUSDT", "ETHUSDT"}, "active=1,diverged=1"))

    def test_a_pass_with_no_readable_states_breaks_nothing(self) -> None:
        assert not e2.can_break(one_pass(1, {"BTCUSDT"}, None))

    def test_a_pass_covering_nothing_breaks_nothing(self) -> None:
        assert not e2.can_break(one_pass(0, set(), "active=0"))

    def test_the_trusted_set_can_be_handed_in(self) -> None:
        assert e2.can_break(one_pass(1, {"BTCUSDT"}, "diverged=1"), frozenset({"diverged"}))


# --------------------------------------------------------------------------------------
# The inventory is placements less bookings, per process, from the log alone
# --------------------------------------------------------------------------------------
class TestTheInventory:
    def inventories(self, lines: list[str]) -> list[frozenset[str]]:
        return [p.inventory for p in e2.build_passes(e2.read_rows(lines))]

    def test_a_placement_adds_the_symbol_and_a_booking_removes_it(self) -> None:
        lines = [
            place(t("00:01:00"), 1, "BTCUSDT", t("00:00:59.999000")),
            place(t("00:02:00"), 1, "ETHUSDT", t("00:01:59.999000")),
            recon(t("00:03:00"), 1, 2, "active=2"),
            book(t("00:04:00"), 1, "ETHUSDT"),
            recon(t("00:05:00"), 1, 1, "active=1"),
        ]
        assert self.inventories(lines) == [
            frozenset({"BTCUSDT", "ETHUSDT"}),
            frozenset({"BTCUSDT"}),
        ]

    @pytest.mark.parametrize("event", ["exit_booked", "boot_exit_booked"])
    def test_an_exit_booking_and_a_boot_booking_remove_it_too(self, event: str) -> None:
        lines = [
            place(t("00:01:00"), 1, "BTCUSDT", t("00:00:59.999000")),
            book(t("00:02:00"), 1, "BTCUSDT", event),
            recon(t("00:03:00"), 1, 0, ""),
        ]
        assert self.inventories(lines) == [frozenset()]

    def test_each_process_keeps_its_own_inventory(self) -> None:
        lines = [
            place(t("00:01:00"), 1, "BTCUSDT", t("00:00:59.999000")),
            recon(t("00:02:00"), 1, 1, "active=1"),
            recon(t("00:03:00"), 2, 0, ""),
        ]
        assert self.inventories(lines) == [frozenset({"BTCUSDT"}), frozenset()]

    def test_a_line_without_a_pid_or_a_stamp_is_not_a_row(self) -> None:
        rows = e2.read_rows(
            ["no stamp here", "2026-10-12T00:00:00Z | INFO | no pid", idle(t("00:00:01"), 3)]
        )
        assert [row.pid for row in rows] == ["3"]


# --------------------------------------------------------------------------------------
# Attaching an untrusted line to its pass
# --------------------------------------------------------------------------------------
class TestAttachingUntrustedLines:
    def attach(self, lines: list[str]) -> dict[int, e2.Attachment]:
        rows = e2.read_rows(lines)
        return e2.attach_untrusted(rows, e2.build_passes(rows))

    def test_a_line_goes_to_the_nearest_pass_of_its_own_process(self) -> None:
        lines = [
            recon(t("00:10:00"), 1, 1, "unknown=1"),
            recon(t("00:10:00"), 2, 1, "unknown=1"),
            untrusted(t("00:10:01"), 2),
        ]
        attached = self.attach(lines)
        assert list(attached) == [2]
        assert attached[2].symbols == {"BTCUSDT"}

    def test_a_line_before_its_pass_is_attached_as_well_as_one_after(self) -> None:
        before = self.attach([untrusted(t("00:10:00"), 1), recon(t("00:10:01"), 1, 1, "unknown=1")])
        after = self.attach([recon(t("00:10:00"), 1, 1, "unknown=1"), untrusted(t("00:10:01"), 1)])
        assert list(before) == [2] and list(after) == [1]

    def test_the_first_line_of_a_pass_is_remembered(self) -> None:
        lines = [
            recon(t("00:10:00"), 1, 2, "unknown=2"),
            untrusted(t("00:10:01"), 1, "BTCUSDT"),
            untrusted(t("00:10:02"), 1, "ETHUSDT"),
        ]
        attached = self.attach(lines)[1]
        assert attached.first_line == 2 and attached.symbols == {"BTCUSDT", "ETHUSDT"}

    def test_a_line_with_no_pass_within_fifteen_seconds_is_dropped(self) -> None:
        lines = [recon(t("00:10:00"), 1, 1, "unknown=1"), untrusted(t("00:10:16"), 1)]
        assert self.attach(lines) == {}


# --------------------------------------------------------------------------------------
# The episodes: self-clearing, ended by the process, ended by a clean stop, open
# --------------------------------------------------------------------------------------
class TestASelfClearingLatch:
    def lines(self) -> list[str]:
        return [
            place(t("15:00:00"), 1, "BTCUSDT", t("14:59:59.999000")),
            place(t("15:00:05"), 1, "ETHUSDT", t("15:00:04.999000")),
            recon(t("16:00:01"), 1, 2, "active=1,unknown=1"),
            untrusted(t("16:00:01"), 1),
            recon(t("16:01:00"), 1, 1, "active=1"),
            refuse(t("16:21:00"), 1),
            recon(t("16:51:01"), 1, 1, "diverged=1"),
            untrusted(t("16:51:01"), 1),
            recon(t("16:52:00"), 1, 1, "active=1"),
            recon(t("16:54:00"), 1, 2, "active=2"),
            idle(t("20:00:00"), 1),
            stopped(t("23:59:00"), 1),
        ]

    def test_it_ends_at_the_pass_that_covered_every_position_and_found_them_all_trusted(
        self,
    ) -> None:
        (episode,) = sink(self.lines())
        assert span(episode) == (at("16:00:01"), at("16:54:00"))
        assert episode.end_kind == "breaking pass"

    def test_it_counts_its_untrusted_passes_and_its_refusals(self) -> None:
        (episode,) = sink(self.lines())
        assert (episode.passes, episode.refusals, episode.symbols) == (2, 1, ("BTCUSDT",))

    def test_a_pass_covering_fewer_positions_than_the_inventory_breaks_nothing(self) -> None:
        without_the_full_coverage_pass = self.lines()[:-3]
        (episode,) = sink(without_the_full_coverage_pass)
        assert episode.start == at("16:00:01")
        assert (episode.end, episode.end_kind) == (M, "open, closed at M")
        assert episode.passes == 2

    def test_the_start_is_the_first_untrusted_line_and_not_the_pass_before_it(self) -> None:
        lines = [
            place(t("15:00:00"), 1, "BTCUSDT", t("14:59:59.999000")),
            recon(t("15:30:00"), 1, 1, "active=1"),
            recon(t("16:00:01"), 1, 1, "unknown=1"),
            untrusted(t("16:00:02"), 1),
            refuse(t("16:10:00"), 1),
            idle(t("17:00:00"), 1),
        ]
        (episode,) = sink(lines)
        assert episode.start == at("16:00:02")


class TestALatchEndedByTheProcess:
    def lines(self) -> list[str]:
        return [
            place(t("02:30:02"), 1, "ETHUSDT", t("02:29:59.999000")),
            *latch_passes(1, ["02:59:02", "03:00:02", "03:01:03"], symbols="ETHUSDT"),
            refuse(t("03:33:00"), 1, "BTCUSDT"),
            recon(t("06:54:01"), 1, 1, "unknown=1"),
            untrusted(t("06:54:01"), 1, "ETHUSDT"),
            boot(t("07:00:35"), 2),
            idle(t("07:00:48"), 2),
            boot(t("08:00:00"), 3),
        ]

    def test_with_a_successor_it_ends_at_the_last_line_of_the_process(self) -> None:
        (episode,) = sink(self.lines())
        assert span(episode) == (at("02:59:02"), at("06:54:01"))
        assert episode.end_kind == "last line of the process"
        assert episode.symbols == ("ETHUSDT",)

    def test_a_second_untrusted_symbol_in_the_run_is_named(self) -> None:
        lines = [
            place(t("02:00:00"), 1, "BTCUSDT", t("01:59:59.999000")),
            place(t("02:00:05"), 1, "ETHUSDT", t("02:00:04.999000")),
            recon(t("03:00:00"), 1, 2, "unknown=2"),
            untrusted(t("03:00:00"), 1, "BTCUSDT,ETHUSDT"),
            refuse(t("03:10:00"), 1),
            idle(t("04:00:00"), 1),
        ]
        (episode,) = sink(lines)
        assert episode.symbols == ("BTCUSDT", "ETHUSDT")


class TestALatchEndedByACleanStop:
    def test_it_ends_at_the_clean_stop_though_no_process_follows(self) -> None:
        lines = [
            place(t("13:09:00"), 1, "BTCUSDT", t("13:08:59.999000")),
            *latch_passes(1, ["13:11:00", "13:12:00"]),
            halted(t("13:38:02"), 1),
            stopped(t("20:05:33"), 1),
        ]
        (episode,) = sink(lines)
        assert span(episode) == (at("13:11:00"), at("20:05:33"))
        assert episode.end_kind == "last line of the process"

    def test_a_stop_that_was_not_clean_is_not_a_stop(self) -> None:
        lines = [
            place(t("13:09:00"), 1, "BTCUSDT", t("13:08:59.999000")),
            *latch_passes(1, ["13:11:00"]),
            halted(t("13:38:02"), 1),
            stopped(t("20:05:33"), 1, clean="False"),
        ]
        (episode,) = sink(lines)
        assert (episode.end, episode.end_kind) == (M, "open, closed at M")


class TestALatchOpenAtTheCaptureEnd:
    LINES: ClassVar[list[str]] = [
        place(t("13:09:00"), 1, "BTCUSDT", t("13:08:59.999000")),
        recon(t("13:11:00"), 1, 1, "unknown=1"),
        untrusted(t("13:11:00"), 1),
        refuse(t("13:57:00"), 1),
        idle(t("14:00:00"), 1),
    ]

    def test_the_interval_is_open_and_closed_at_the_window_end(self) -> None:
        (episode,) = sink(self.LINES)
        assert span(episode) == (at("13:11:00"), M)
        assert episode.end_kind == "open, closed at M"

    def test_it_is_closed_at_whatever_m_the_caller_names(self) -> None:
        other = datetime(2026, 11, 1, tzinfo=UTC)
        (episode,) = e2.latch_episodes(self.LINES, closed_at=other)
        assert episode.end == other


class TestWhatIsAnEpisode:
    def test_a_run_with_no_refusal_inside_it_is_not_an_episode(self) -> None:
        lines = [
            place(t("00:00:00"), 1, "BTCUSDT", t("00:00:00")),
            *latch_passes(1, ["00:10:00", "00:11:00"]),
            recon(t("00:12:00"), 1, 1, "active=1"),
            idle(t("01:00:00"), 1),
        ]
        assert sink(lines) == []

    def test_a_refusal_after_the_run_broke_does_not_count(self) -> None:
        lines = [
            place(t("00:00:00"), 1, "BTCUSDT", t("00:00:00")),
            *latch_passes(1, ["00:10:00", "00:11:00"]),
            recon(t("00:12:00"), 1, 1, "active=1"),
            refuse(t("00:13:00"), 1),
        ]
        assert sink(lines) == []

    def test_a_refusal_before_the_run_started_does_not_count(self) -> None:
        lines = [
            place(t("00:00:00"), 1, "BTCUSDT", t("00:00:00")),
            refuse(t("00:05:00"), 1),
            *latch_passes(1, ["00:10:00"]),
            recon(t("00:12:00"), 1, 1, "active=1"),
        ]
        assert sink(lines) == []

    def test_a_refusal_in_another_process_does_not_count(self) -> None:
        lines = [
            place(t("00:00:00"), 1, "BTCUSDT", t("00:00:00")),
            *latch_passes(1, ["00:10:00"]),
            refuse(t("00:11:00"), 2),
            recon(t("00:12:00"), 1, 1, "active=1"),
        ]
        assert sink(lines) == []

    def test_a_close_halted_refusal_qualifies_as_well_as_a_committed_risk_one(self) -> None:
        lines = [
            place(t("00:00:00"), 1, "BTCUSDT", t("00:00:00")),
            *latch_passes(1, ["00:10:00"]),
            halted(t("00:11:00"), 1),
            idle(t("01:00:00"), 1),
        ]
        assert len(sink(lines)) == 1

    def test_an_untrusted_line_with_no_pass_near_it_starts_nothing(self) -> None:
        lines = [
            place(t("00:00:00"), 1, "BTCUSDT", t("00:00:00")),
            untrusted(t("02:00:00"), 1),
            refuse(t("02:01:00"), 1),
            idle(t("03:00:00"), 1),
        ]
        assert sink(lines) == []

    def test_after_a_break_a_new_run_can_start_and_qualify_on_its_own(self) -> None:
        lines = [
            place(t("00:00:00"), 1, "BTCUSDT", t("00:00:00")),
            *latch_passes(1, ["01:00:00"]),
            refuse(t("01:01:00"), 1),
            recon(t("01:02:00"), 1, 1, "active=1"),
            *latch_passes(1, ["02:00:00"]),
            refuse(t("02:01:00"), 1),
            recon(t("02:02:00"), 1, 1, "active=1"),
        ]
        assert [span(e) for e in sink(lines)] == [
            (at("01:00:00"), at("01:02:00")),
            (at("02:00:00"), at("02:02:00")),
        ]


# --------------------------------------------------------------------------------------
# R-DP: a lone position that is diverged, pending or unknown breaks nothing
# --------------------------------------------------------------------------------------
class TestAUntrustedStateOnALonePosition:
    def lines(self, states: str, tail: list[str]) -> list[str]:
        return [
            place(t("00:00:00"), 1, "BTCUSDT", t("00:00:00")),
            *latch_passes(1, ["00:10:00"], states=states),
            refuse(t("00:10:30"), 1),
            *latch_passes(1, ["00:11:00", "00:12:00"], states=states),
            *tail,
        ]

    @pytest.mark.parametrize("states", ["diverged=1", "pending=1", "unknown=1"])
    def test_every_pass_is_inside_one_unbroken_run_that_ends_with_the_process(
        self, states: str
    ) -> None:
        (episode,) = sink(self.lines(states, [stopped(t("01:00:00"), 1)]))
        assert span(episode) == (at("00:10:00"), at("01:00:00"))
        assert (episode.passes, episode.end_kind) == (3, "last line of the process")

    def test_the_same_lone_position_reported_active_does_break(self) -> None:
        tail = [recon(t("00:13:00"), 1, 1, "active=1"), stopped(t("01:00:00"), 1)]
        (episode,) = sink(self.lines("diverged=1", tail))
        assert span(episode) == (at("00:10:00"), at("00:13:00"))
        assert episode.end_kind == "breaking pass"

    def test_a_lone_absent_by_design_position_does_break(self) -> None:
        tail = [recon(t("00:13:00"), 1, 1, "absent_by_design=1"), stopped(t("01:00:00"), 1)]
        (episode,) = sink(self.lines("diverged=1", tail))
        assert episode.end == at("00:13:00")


class TestCoverageWithTwoPositions:
    def lines(self, middle: list[str]) -> list[str]:
        return [
            place(t("00:00:00"), 1, "BTCUSDT", t("00:00:00")),
            place(t("00:00:05"), 1, "ETHUSDT", t("00:00:04")),
            recon(t("00:10:00"), 1, 2, "active=1,unknown=1"),
            untrusted(t("00:10:00"), 1),
            refuse(t("00:11:00"), 1),
            *middle,
            idle(t("02:00:00"), 1),
        ]

    def test_a_pass_that_handled_only_the_other_position_breaks_nothing(self) -> None:
        (episode,) = sink(self.lines([recon(t("00:12:00"), 1, 1, "active=1")]))
        assert episode.end == M

    def test_a_pass_that_covered_both_and_found_both_trusted_breaks(self) -> None:
        (episode,) = sink(self.lines([recon(t("00:12:00"), 1, 2, "active=2")]))
        assert span(episode) == (at("00:10:00"), at("00:12:00"))

    def test_a_pass_that_covered_both_and_found_one_unknown_does_not(self) -> None:
        (episode,) = sink(self.lines([recon(t("00:12:00"), 1, 2, "active=1,unknown=1")]))
        assert episode.end == M

    def test_a_booking_shrinks_the_inventory_so_a_single_position_pass_then_covers_it(self) -> None:
        middle = [book(t("00:11:30"), 1, "ETHUSDT"), recon(t("00:12:00"), 1, 1, "active=1")]
        (episode,) = sink(self.lines(middle))
        assert episode.end == at("00:12:00")

    def test_positions_restored_at_boot_and_unseen_by_the_inventory_break_nothing(self) -> None:
        lines = [
            recon(t("00:10:00"), 1, 2, "active=1,unknown=1"),
            untrusted(t("00:10:00"), 1),
            refuse(t("00:11:00"), 1),
            recon(t("00:12:00"), 1, 2, "active=2"),
            idle(t("02:00:00"), 1),
        ]
        (episode,) = sink(lines)
        assert episode.end == M


# --------------------------------------------------------------------------------------
# The three P129 episodes, to the second
# --------------------------------------------------------------------------------------
def p129_log() -> list[str]:
    d11, d12, d13, d21, d23 = ("2026-10-11", "2026-10-12", "2026-10-13", "2026-10-21", "2026-10-23")
    return [
        place(t("15:00:00", d11), 16076, "BTCUSDT", t("14:59:59.999000", d11)),
        place(t("15:00:05", d11), 16076, "ETHUSDT", t("15:00:04.999000", d11)),
        recon(t("16:00:01", d11), 16076, 2, "active=1,unknown=1"),
        untrusted(t("16:00:01", d11), 16076),
        recon(t("16:00:03", d11), 16076, 1, "diverged=1"),
        untrusted(t("16:00:03", d11), 16076),
        recon(t("16:01:00", d11), 16076, 1, "active=1"),
        refuse(t("16:21:00", d11), 16076),
        recon(t("16:51:01", d11), 16076, 1, "diverged=1"),
        untrusted(t("16:51:01", d11), 16076),
        recon(t("16:52:00", d11), 16076, 1, "active=1"),
        recon(t("16:54:00", d11), 16076, 2, "active=2"),
        stopped(t("04:17:43", d12), 16076),
        boot(t("19:17:35", d12), 22304),
        place(t("02:30:02", d13), 22304, "ETHUSDT", t("02:29:59.999000", d13)),
        recon(t("02:59:02", d13), 22304, 1, "unknown=1"),
        untrusted(t("02:59:02", d13), 22304, "ETHUSDT"),
        refuse(t("03:33:00", d13), 22304),
        recon(t("06:54:01", d13), 22304, 1, "unknown=1"),
        untrusted(t("06:54:01", d13), 22304, "ETHUSDT"),
        boot(t("07:00:35", d13), 3444),
        idle(t("07:00:48", d13), 3444),
        boot(t("06:34:32", "2026-10-14"), 25352),
        boot(t("08:47:06", "2026-10-20"), 14600),
        place(t("13:09:00", d21), 14600, "BTCUSDT", t("13:08:59.999000", d21)),
        recon(t("13:11:00", d21), 14600, 1, "unknown=1"),
        untrusted(t("13:11:00", d21), 14600),
        halted(t("13:38:02", d21), 14600),
        refuse(t("13:57:00", d21), 14600),
        recon(t("08:04:02", d23), 14600, 1, "unknown=1"),
        untrusted(t("08:04:02", d23), 14600),
        stopped(t("08:05:33", d23), 14600),
    ]


class TestTheP129Table:
    def test_the_intervals_equal_the_p129_r_do_table_to_the_second(self) -> None:
        episodes = e2.latch_episodes(p129_log(), closed_at=datetime(2026, 11, 1, tzinfo=UTC))
        assert [span(e) for e in episodes] == [
            (
                datetime(2026, 10, 11, 16, 0, 1, tzinfo=UTC),
                datetime(2026, 10, 11, 16, 54, 0, tzinfo=UTC),
            ),
            (
                datetime(2026, 10, 13, 2, 59, 2, tzinfo=UTC),
                datetime(2026, 10, 13, 6, 54, 1, tzinfo=UTC),
            ),
            (
                datetime(2026, 10, 21, 13, 11, 0, tzinfo=UTC),
                datetime(2026, 10, 23, 8, 5, 33, tzinfo=UTC),
            ),
        ]

    def test_the_durations_are_p129s(self) -> None:
        episodes = e2.latch_episodes(p129_log(), closed_at=datetime(2026, 11, 1, tzinfo=UTC))
        assert [e.end - e.start for e in episodes] == [
            timedelta(minutes=53, seconds=59),
            timedelta(hours=3, minutes=54, seconds=59),
            timedelta(days=1, hours=18, minutes=54, seconds=33),
        ]

    def test_how_each_one_ends(self) -> None:
        episodes = e2.latch_episodes(p129_log(), closed_at=datetime(2026, 11, 1, tzinfo=UTC))
        assert [e.end_kind for e in episodes] == [
            "breaking pass",
            "last line of the process",
            "last line of the process",
        ]

    def test_the_refusals_each_one_holds(self) -> None:
        episodes = e2.latch_episodes(p129_log(), closed_at=datetime(2026, 11, 1, tzinfo=UTC))
        assert [e.refusals for e in episodes] == [1, 1, 2]


# --------------------------------------------------------------------------------------
# The union with the frozen downtime
# --------------------------------------------------------------------------------------
def iv(start: str, end: str, before: str = "1", after: str = "2") -> s4.DownInterval:
    return s4.DownInterval(at(start), at(end), before, after)


class TestTheUnion:
    def test_an_interval_that_abuts_another_is_merged_into_one(self) -> None:
        merged = e2.merge_intervals(
            [iv("06:00:00", "07:00:00", "9", "9"), iv("07:00:00", "08:00:00", "9", "10")]
        )
        assert [(i.start, i.end) for i in merged] == [(at("06:00:00"), at("08:00:00"))]
        assert (merged[0].before_pid, merged[0].after_pid) == ("9", "10")

    def test_overlapping_intervals_are_merged(self) -> None:
        merged = e2.merge_intervals([iv("06:00:00", "07:30:00"), iv("07:00:00", "08:00:00")])
        assert [(i.start, i.end) for i in merged] == [(at("06:00:00"), at("08:00:00"))]

    def test_an_interval_inside_another_is_absorbed(self) -> None:
        merged = e2.merge_intervals([iv("06:00:00", "09:00:00"), iv("07:00:00", "08:00:00")])
        assert [(i.start, i.end) for i in merged] == [(at("06:00:00"), at("09:00:00"))]

    def test_intervals_with_a_gap_stay_apart_and_come_out_sorted(self) -> None:
        merged = e2.merge_intervals([iv("10:00:00", "11:00:00"), iv("06:00:00", "07:00:00")])
        assert [(i.start, i.end) for i in merged] == [
            (at("06:00:00"), at("07:00:00")),
            (at("10:00:00"), at("11:00:00")),
        ]

    def test_nothing_in_is_nothing_out(self) -> None:
        assert e2.merge_intervals([]) == ()

    def test_a_latch_and_the_downtime_that_follows_it_in_a_real_log_become_one(self) -> None:
        lines = [
            place(t("00:00:00"), 1, "BTCUSDT", t("00:00:00")),
            *latch_passes(1, ["00:10:00", "00:11:00"]),
            refuse(t("00:12:00"), 1),
            idle(t("03:00:00"), 1),
            boot(t("03:05:00"), 2),
            recon(t("03:10:00"), 2, 0, ""),
        ]
        frozen = s4.down_intervals(lines)
        latch = e2.latch_intervals(sink(lines))
        assert [(i.start, i.end) for i in frozen] == [(at("03:00:00"), at("03:10:00"))]
        assert [(i.start, i.end) for i in latch] == [(at("00:10:00"), at("03:00:00"))]
        merged = e2.merge_intervals([*frozen, *latch])
        assert [(i.start, i.end) for i in merged] == [(at("00:10:00"), at("03:10:00"))]


# --------------------------------------------------------------------------------------
# The whole report, end to end
# --------------------------------------------------------------------------------------
def capture(tmp_path: Path, lines: list[str], name: str = "live.log") -> Path:
    path = tmp_path / name
    path.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    return path


def backtest_row(symbol: str, entry_open: str, realised: str = "1") -> dict[str, str]:
    zoned = f"{entry_open}+00:00"
    return {
        "symbol": symbol,
        "signal_bar_open": zoned,
        "entry_bar_open": zoned,
        "entry_price": "100",
        "entry_quote_total": "100",
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
        "window": {"data_dir": str(tmp_path / "no_store")},
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


def signal_line(event: str, symbol: str, close: str, extra: str = "") -> str:
    return (
        f"2026-10-12T00:00:00Z | INFO     | pid=11 | trading_bot.engine.modes | Intent BUY {symbol} "
        f"event={event} symbol={symbol} timeframe=1m action=BUY signal_ts={close} {extra}"
    )


class TestExclusionOnBothSides:
    SIG_IN = t("02:19:59.999000") + "+00:00"
    SIG_BT = t("02:29:59.999000") + "+00:00"

    def build(self, tmp_path: Path) -> tuple[Path, Path]:
        lines = [
            boot(t("00:00:01"), 11),
            place(t("00:01:00"), 11, "ETHUSDT", t("00:00:59.999000")),
            recon(t("02:10:00"), 11, 1, "unknown=1"),
            untrusted(t("02:10:00"), 11, "ETHUSDT"),
            refuse(t("02:11:00"), 11),
            place(t("02:20:03"), 11, "BTCUSDT", t("02:19:59.999000")),
            book(t("02:40:03"), 11, "BTCUSDT"),
            recon(t("02:50:00"), 11, 1, "unknown=1"),
            untrusted(t("02:50:00"), 11, "ETHUSDT"),
            stopped(t("03:00:00"), 11),
        ]
        rows = [
            backtest_row("BTCUSDT", t("02:20:00")),
            backtest_row("BTCUSDT", t("02:30:00")),
            backtest_row("BTCUSDT", t("03:30:00")),
        ]
        return run_dir(tmp_path, rows), capture(tmp_path, lines)

    def test_the_wrapper_drops_the_entries_the_latch_covers_from_both_sides_and_lists_them(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        run, live = self.build(tmp_path)
        assert e2.main(argv(run, live)) == 0
        out = capsys.readouterr().out
        assert "excluded on both sides (3)" in out
        assert "live BTCUSDT signal bar close 2026-10-12T02:19:59.999000+00:00" in out
        assert "backtest BTCUSDT signal bar close 2026-10-12T02:29:59.999000+00:00" in out
        assert "backtest BTCUSDT signal bar close 2026-10-12T02:19:59.999000+00:00" in out
        assert "LATCH EPISODES (1)" in out

    def test_the_frozen_tool_on_the_same_inputs_excludes_nothing(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        run, live = self.build(tmp_path)
        assert s4.main(argv(run, live)) == 0
        assert "excluded on both sides (0)" in capsys.readouterr().out

    def test_the_figures_follow_the_exclusion(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        run, live = self.build(tmp_path)
        assert e2.main(argv(run, live)) == 0
        out = capsys.readouterr().out
        assert "live entries booked          : 0" in out
        assert "backtest entries             : 1" in out


class TestTheThirteenOhNineEntry:
    SIGNAL = "2026-10-12T03:08:59.999000+00:00"

    def build(self, tmp_path: Path) -> tuple[Path, Path]:
        lines = [
            boot(t("00:00:01"), 11),
            signal_line("intent_dispatched", "BTCUSDT", self.SIGNAL),
            place(t("03:09:02"), 11, "BTCUSDT", t("03:08:59.999000")),
            recon(t("03:10:00"), 11, 1, "active=1"),
            recon(t("03:11:00"), 11, 1, "unknown=1"),
            untrusted(t("03:11:00"), 11),
            refuse(t("03:20:00"), 11),
            stopped(t("04:00:00"), 11),
        ]
        run = run_dir(tmp_path, [backtest_row("BTCUSDT", t("03:09:00"))])
        return run, capture(tmp_path, lines)

    def test_the_frozen_diagnosis_labels_a_filled_entry_that_was_never_booked_fok_unfilled(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        run, live = self.build(tmp_path)
        assert s4.main(argv(run, live)) == 0
        out = capsys.readouterr().out
        assert "[fok-unfilled] backtest only BTCUSDT" in out
        assert "the live bot placed and nothing was booked" in out

    def test_the_latch_starts_after_the_entrys_signal_bar_so_e2_does_not_exclude_it(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        run, live = self.build(tmp_path)
        assert e2.main(argv(run, live)) == 0
        out = capsys.readouterr().out
        assert "excluded on both sides (0)" in out
        assert "[fok-unfilled] backtest only BTCUSDT" in out
        assert "LATCH EPISODES (1)" in out

    def test_the_wrapper_adds_no_label_of_its_own(self) -> None:
        assert e2.diagnose is s4.diagnose
        assert e2.exclude_downtime is s4.exclude_downtime


class TestTheReport:
    def build(self, tmp_path: Path) -> tuple[Path, Path]:
        lines = [
            boot(t("00:00:01"), 11),
            place(t("00:01:00"), 11, "BTCUSDT", t("00:00:59.999000")),
            book(t("01:00:03"), 11, "BTCUSDT"),
            idle(t("02:00:00"), 11),
        ]
        return run_dir(tmp_path, [backtest_row("BTCUSDT", t("00:01:00"))]), capture(tmp_path, lines)

    def test_it_is_headed_as_exploratory_and_names_the_rulings_and_the_trusted_set(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        run, live = self.build(tmp_path)
        assert e2.main(argv(run, live)) == 0
        out = capsys.readouterr().out
        assert out.splitlines()[1].startswith("EXPLORATORY E2 (R-DL)")
        assert "rulings applied: R-DM, R-DO, R-DP" in out
        assert "absent_by_design, active" in out
        assert "cannot" not in out.splitlines()[1]

    def test_it_prints_the_three_figures_and_every_cause_count(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        run, live = self.build(tmp_path)
        assert e2.main(argv(run, live)) == 0
        out = capsys.readouterr().out
        assert "reproduced on symbol and bar : 1 of 1 = 100.00%" in out
        assert "trade counts                 : 1 against 1, difference 0 = 0.00% of live" in out
        assert "live per-trade mean" in out and "backtest per-trade mean" in out
        for cause in s4.CAUSES:
            assert re.search(rf"^\s+{re.escape(cause)}\s*: \d+$", out, re.MULTILINE), cause

    def test_no_verdict_word_appears(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        run, live = self.build(tmp_path)
        assert e2.main(argv(run, live)) == 0
        assert VERDICT_WORDS.search(capsys.readouterr().out) is None

    def test_with_no_latch_it_ends_with_exactly_the_frozen_report(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        run, live = self.build(tmp_path)
        assert s4.main(argv(run, live)) == 0
        frozen = capsys.readouterr().out
        assert e2.main(argv(run, live)) == 0
        assert capsys.readouterr().out.endswith(frozen)

    def test_with_only_downtime_and_no_latch_the_exclusion_is_the_frozen_one(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        lines = [
            boot(t("00:00:01"), 11),
            idle(t("03:30:00"), 11),
            boot(t("03:31:00"), 12),
            recon(t("04:00:00"), 12, 0, ""),
        ]
        run = run_dir(tmp_path, [backtest_row("BTCUSDT", t("03:40:00"))])
        live = capture(tmp_path, lines)
        assert s4.main(argv(run, live)) == 0
        frozen = capsys.readouterr().out
        assert e2.main(argv(run, live)) == 0
        assert capsys.readouterr().out.endswith(frozen)
        assert "excluded on both sides (1)" in frozen


class TestTheInputsAreTheFrozenToolsOwn:
    def test_a_backtest_record_that_is_not_evidence_is_refused_before_any_figure(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        live = capture(tmp_path, [boot(t("00:00:01"), 11), idle(t("01:00:00"), 11)])
        run = run_dir(tmp_path, [], eligible=False)
        assert e2.main(argv(run, live)) == 2
        assert "REFUSED" in capsys.readouterr().out

    def test_a_refused_boot_refuses_the_live_run(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        live = capture(
            tmp_path,
            [
                boot(t("00:00:01"), 11),
                boot(t("00:30:00"), 12, verdict="refused", reasons="checkout_dirty=true"),
            ],
        )
        run = run_dir(tmp_path, [])
        assert e2.main(argv(run, live)) == 2
        assert "REFUSED" in capsys.readouterr().out

    def test_a_capture_with_no_boot_line_is_refused(self, tmp_path: Path) -> None:
        live = capture(tmp_path, [idle(t("00:00:01"), 11)])
        assert e2.main(argv(run_dir(tmp_path, []), live)) == 2

    def test_a_capture_under_a_logs_directory_is_never_read(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        (tmp_path / "logs").mkdir()
        live = capture(tmp_path / "logs", [boot(t("00:00:01"), 11)])
        assert e2.main(argv(run_dir(tmp_path, []), live)) == 2
        assert "logs/" in capsys.readouterr().out

    def test_a_window_that_ends_before_it_starts_is_refused(self, tmp_path: Path) -> None:
        live = capture(tmp_path, [boot(t("00:00:01"), 11)])
        assert e2.main(argv(run_dir(tmp_path, []), live, (WINDOW[1], WINDOW[0]))) == 2

    def test_a_trades_csv_that_disagrees_with_the_record_is_an_input_error(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        live = capture(tmp_path, [boot(t("00:00:01"), 11)])
        run = run_dir(tmp_path, [backtest_row("BTCUSDT", t("00:01:00"))], declared=2)
        assert e2.main(argv(run, live)) == 3
        assert "declares 2" in capsys.readouterr().out

    def test_a_record_with_no_pairs_is_an_input_error_and_not_a_default(
        self, tmp_path: Path
    ) -> None:
        live = capture(tmp_path, [boot(t("00:00:01"), 11)])
        run = run_dir(tmp_path, [])
        record = json.loads((run / "run.json").read_text(encoding="utf-8"))
        del record["pairs"]
        (run / "run.json").write_text(json.dumps(record), encoding="utf-8", newline="\n")
        assert e2.main(argv(run, live)) == 3

    def test_the_arguments_are_the_frozen_parsers_with_only_the_name_changed(self) -> None:
        with pytest.raises(SystemExit) as caught:
            e2.main(["--help"])
        assert caught.value.code == 0
