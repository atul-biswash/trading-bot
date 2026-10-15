"""``scripts/s6_sweep.py``: the command lines, the order, R-CH's check, resumption, and the ledger it reports.

Workers are REAL subprocesses of ``sweep_fake_backtest.py``, which writes the directory the real command
writes (a schema-6 record that passes the evidence door), so completion, duplicates, conflicts and the
unsealed ``-running`` directory are judged by the same ``selection.read_run`` the selection uses. The protocol
is narrowed to 2, 4 or 6 variants (the declaration's families edited, every other rule the real one) so a test
launches a handful of processes and not 216; the 216 command lines are checked against the REAL parser and
guard in-process.
"""

from __future__ import annotations

import json
import sys
from dataclasses import replace
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

import s6_sweep as s6

import trading_bot.main as cli
from tests.unit.protocol_world import PROTOCOL, REPO
from tests.unit.selection_world import RULES, bulk, point, with_selection
from trading_bot.backtesting import selection as sel
from trading_bot.backtesting.candidate import effective_settings
from trading_bot.backtesting.engine import select_pairs
from trading_bot.backtesting.overrides import apply_overrides, build_overrides
from trading_bot.backtesting.protocol import (
    Protocol,
    Variant,
    WindowClass,
    check_run,
    grid_point,
    parse_protocol,
)
from trading_bot.config.settings import get_settings

FAKE = Path(__file__).resolve().parent / "sweep_fake_backtest.py"
UTC = timezone.utc


def cut_to(declaration: dict[str, Any], families: list[dict[str, Any]]) -> None:
    """Cut the declaration's families, and clear the R-CM list: it names real points that may no longer exist."""
    declaration["families"] = families
    declaration["selection"]["ineligible_variants"] = []


def narrowed(fast: list[int], timeframes: list[str]) -> tuple[str, Protocol]:
    """The real protocol with its families cut to one sma_crossover grid of ``fast`` x slow 50."""
    family = {
        "id": "sma_crossover",
        "strategy": "sma_crossover",
        "timeframes": timeframes,
        "grid": {"fast_period": fast, "slow_period": [50]},
    }
    text = with_selection(lambda d: cut_to(d, [family]))
    return text, parse_protocol(text)


SMALL_TEXT, SMALL = narrowed([10], ["1h"])  # 2 variants: filter off, on
MEDIUM_TEXT, MEDIUM = narrowed([10, 20], ["1h"])  # 4
PROBE_TEXT, PROBE = narrowed([10], ["1h", "4h", "1d"])  # 6


def two_families() -> tuple[str, Protocol]:
    """sma_crossover and rsi, one grid point each, at 1h and 4h: 2 x 2 x 2 = 8 variants."""
    families = [
        {
            "id": "sma_crossover",
            "strategy": "sma_crossover",
            "timeframes": ["1h", "4h"],
            "grid": {"fast_period": [10], "slow_period": [50]},
        },
        {
            "id": "rsi",
            "strategy": "rsi",
            "timeframes": ["1h", "4h"],
            "grid": {"period": [14], "oversold": [30], "overbought": [70]},
        },
    ]
    text = with_selection(lambda d: cut_to(d, families))
    return text, parse_protocol(text)


BOTH_TEXT, BOTH = two_families()


@pytest.fixture
def clone(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = tmp_path / "clone"
    (root / "data").mkdir(parents=True)
    monkeypatch.setenv("FAKE_BACKTESTS", str(root / "data" / "backtests"))
    monkeypatch.delenv("FAKE_MODE", raising=False)
    return root


REAL_ARGV = s6.backtest_argv


def fake_argv(variant: Variant, protocol_sha: str = "0" * 64) -> list[str]:
    """The sweep's command line with `-m trading_bot` replaced by the fake script, which records the
    protocol digest it is told (the real command records the digest of the PROTOCOL.md it reads)."""
    real = REAL_ARGV(sys.executable, variant, RULES)
    return [real[0], str(FAKE), *real[3:], "--protocol-sha", protocol_sha]


def run_sweep(
    root: Path, protocol: Protocol, *, workers: int = 1, probe: bool = False
) -> s6.SweepResult:
    return s6.sweep(
        root=root,
        backtests=root / "data" / "backtests",
        manifest_path=root / "data" / "manifest.jsonl",
        logs=root / "data" / "logs",
        protocol=protocol,
        rules=RULES,
        python=sys.executable,
        workers=workers,
        probe=probe,
        argv_for=lambda v: fake_argv(v, protocol.sha256),
        poll_s=0.02,
    )


def events(root: Path) -> list[dict[str, Any]]:
    path = root / "data" / "manifest.jsonl"
    return [json.loads(line) for line in path.read_text(encoding="ascii").splitlines()]


def kinds(root: Path, *, phase: str | None = None) -> list[str]:
    return [f"{e['event']}" for e in events(root) if phase is None or e.get("phase") == phase]


# --------------------------------------------------------------------------------------
# What is run, and in what order
# --------------------------------------------------------------------------------------
class TestTheCommandLine:
    def test_a_variants_argv_is_the_backtest_command_in_sample_at_the_gate_arm(self) -> None:
        variant = next(iter(PROTOCOL.variants()))
        assert s6.backtest_argv("py", variant, RULES) == [
            "py", "-m", "trading_bot", "backtest",
            "--start", "2017-08-17", "--end", "2024-01-01",
            "--stop-slippage", "1.20",
            "--strategy", "sma_crossover", "--timeframe", "1h",
            "--param", "fast_period=10", "--param", "slow_period=50",
        ]  # fmt: skip

    def test_a_filtered_variants_argv_carries_the_filter_as_a_parameter(self) -> None:
        variant = next(v for v in PROTOCOL.variants() if v.filtered)
        argv = s6.backtest_argv("py", variant, RULES)
        assert argv[-2:] == ["--param", "trend_filter_period=200"]

    def test_all_216_command_lines_round_trip_through_the_real_parser_and_the_guard(self) -> None:
        """Parsed by ``main``'s own parser, laid over the committed config, they are the variant they name."""
        parser = cli._build_parser()
        settings = get_settings(str(REPO / "config.yaml"))
        seen = set()
        for variant in PROTOCOL.variants():
            argv = s6.backtest_argv("py", variant, RULES)
            args = parser.parse_args(argv[3:])
            assert args.command == "backtest"
            assert (args.start, args.end) == (date(2017, 8, 17), date(2024, 1, 1))
            assert args.stop_slippage == Decimal("1.20")
            given = build_overrides(
                stop_slippage=args.stop_slippage,
                strategy=args.strategy,
                timeframe=args.timeframe,
                params=args.param,
            )
            laid = settings.with_config(apply_overrides(settings.config, given))
            pairs = [(p.symbol, p.timeframe) for p in select_pairs(laid, None)]
            block = effective_settings(
                laid.config,
                laid.config.backtesting,
                pairs,
                config_sha256=laid.config_sha256,
                overrides=given.record(),
            )
            found = grid_point(PROTOCOL, block)
            assert found is not None and sel.variant_key(found) == sel.variant_key(variant)
            decision = check_run(
                PROTOCOL,
                (),
                effective=block,
                window_start=args.start,
                window_end=args.end,
                provenance_accepted=False,
                local_reads=frozenset(),
            )
            assert decision.window_class is WindowClass.IN_SAMPLE and decision.variant == variant
            seen.add(sel.variant_key(variant))
        assert len(seen) == 216

    def test_the_order_is_heaviest_first_covers_every_variant_and_keeps_the_declared_order_on_ties(
        self,
    ) -> None:
        declared = list(PROTOCOL.variants())
        ordered = s6.order_by_cost(declared)
        assert sorted(map(sel.variant_key, ordered)) == sorted(map(sel.variant_key, declared))
        costs = [s6._cost(v) for v in ordered]
        assert costs == sorted(costs, reverse=True)
        assert (ordered[0].family, ordered[0].timeframe) == ("rsi", "1h") and costs[0] == 36
        assert (ordered[-1].family, ordered[-1].timeframe) == ("sma_crossover", "1d") and costs[
            -1
        ] == 1
        tied = [v for v in ordered if s6._cost(v) == 36]
        assert [sel.variant_key(v) for v in tied] == [
            sel.variant_key(v) for v in declared if s6._cost(v) == 36
        ]


# --------------------------------------------------------------------------------------
# The sweep, serial and parallel (R-CH)
# --------------------------------------------------------------------------------------
class TestASerialSweep:
    def test_it_runs_every_missing_variant_once_and_the_ledger_is_complete(
        self, clone: Path
    ) -> None:
        result = run_sweep(clone, MEDIUM)
        assert result.exit_code == 0 and result.ledger.complete and len(result.ledger.points) == 4
        assert result.ledger.duplicates == () and result.failed == ()
        log = events(clone)
        assert [e["event"] for e in log].count("launch") == 4
        assert [e["event"] for e in log].count("finish") == 4
        assert log[0]["event"] == "sweep_start" and log[0]["to_run"] == 4 and log[0]["workers"] == 1
        assert "parallel_check" not in kinds(clone)
        assert result.check.performed is False and "serial run requested" in result.check.reason
        assert sorted(p.name for p in (clone / "data" / "logs").iterdir())[0].startswith(
            "sweep-001-"
        )

    def test_the_end_line_holds_the_whole_ledger_one_row_per_variant(self, clone: Path) -> None:
        run_sweep(clone, MEDIUM)
        end = events(clone)[-1]
        assert end["event"] == "sweep_end" and end["complete"] is True
        assert (end["declared"], end["with_a_run"], end["missing"], end["conflicts"]) == (
            4,
            4,
            0,
            0,
        )
        rows = end["ledger"]
        assert len(rows) == 4 and all(r["run"] is not None and r["conflict"] is False for r in rows)
        assert [r["variant"]["params"]["fast_period"] for r in rows] == ["10", "20", "10", "20"]
        assert [r["variant"]["filtered"] for r in rows] == [False, False, True, True]

    def test_every_manifest_line_is_one_json_object_with_a_timezone_stamp(
        self, clone: Path
    ) -> None:
        run_sweep(clone, SMALL)
        for line in (clone / "data" / "manifest.jsonl").read_text(encoding="ascii").splitlines():
            event = json.loads(line)
            assert datetime.fromisoformat(event["at"]).tzinfo is not None

    def test_a_complete_ledger_is_not_run_again(self, clone: Path) -> None:
        run_sweep(clone, SMALL)
        before = sorted(p.name for p in (clone / "data" / "backtests").iterdir())
        again = run_sweep(clone, SMALL)
        assert again.exit_code == 0
        assert sorted(p.name for p in (clone / "data" / "backtests").iterdir()) == before
        assert [e for e in events(clone) if e["event"] == "sweep_start"][-1]["to_run"] == 0


class TestTheParallelCheck:
    def test_equal_digests_allow_parallel_and_the_probe_variant_is_a_listed_duplicate(
        self, clone: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("FAKE_MODE", "slow")
        result = run_sweep(clone, MEDIUM, workers=2)
        assert result.check.performed and result.check.parallel_allowed
        assert result.check.serial_digest == result.check.parallel_digest is not None
        assert "equal" in result.check.reason
        assert result.exit_code == 0 and result.ledger.complete and len(result.ledger.points) == 4
        assert len(result.ledger.duplicates) == 1 and result.ledger.conflicts == ()

    def test_the_serial_run_comes_first_then_two_overlapping_launches(
        self, clone: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("FAKE_MODE", "slow")
        run_sweep(clone, MEDIUM, workers=2)
        order = [(e["event"], e.get("phase")) for e in events(clone)]
        serial = order.index(("launch", "check-serial"))
        assert order[serial + 1] == ("finish", "check-serial")
        together = [i for i, item in enumerate(order) if item[1] == "check-parallel"]
        assert [order[i][0] for i in together] == ["launch", "launch", "finish", "finish"]
        assert order.index(("parallel_check", None)) > together[-1]
        sweep_phase = [item[0] for item in order if item[1] == "sweep"]
        assert sweep_phase[:2] == ["launch", "launch"], "the rest runs two at a time"

    def test_different_digests_send_the_rest_serially_and_the_conflict_is_reported(
        self, clone: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("FAKE_MODE", "slow,nondeterministic")
        result = run_sweep(clone, MEDIUM, workers=2)
        assert result.check.performed and not result.check.parallel_allowed
        assert (
            "differ" in result.check.reason
            and result.check.serial_digest != result.check.parallel_digest
        )
        sweep_phase = [e["event"] for e in events(clone) if e.get("phase") == "sweep"]
        assert sweep_phase == ["launch", "finish", "launch", "finish"], (
            "serial after a failed check"
        )
        assert result.exit_code == 1 and len(result.ledger.conflicts) == 1
        assert "CONFLICT" in s6._report(result, MEDIUM)

    def test_a_probe_run_that_leaves_no_record_means_serial(
        self, clone: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("FAKE_MODE", "fail_after=1")
        result = run_sweep(clone, MEDIUM, workers=2)
        assert result.check.performed and not result.check.parallel_allowed
        assert "left no sealed record" in result.check.reason
        assert result.failed and result.exit_code == 1

    def test_one_variant_left_needs_no_check(
        self, clone: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("FAKE_MODE", "crash=trend_filter_period200")
        run_sweep(clone, SMALL)  # the filtered variant crashes: one of the two is done
        monkeypatch.setenv("FAKE_MODE", "")
        result = run_sweep(clone, SMALL, workers=4)
        assert result.check.performed is False and "fewer than two" in result.check.reason
        assert result.exit_code == 0 and "parallel_check" not in kinds(clone)
        assert [e["to_run"] for e in events(clone) if e["event"] == "sweep_start"] == [2, 1]

    def test_a_serial_request_performs_no_check_whatever_is_left(self, clone: Path) -> None:
        run_sweep(clone, MEDIUM, workers=1)
        assert "parallel_check" not in kinds(clone)

    def test_the_check_is_recorded_with_both_digests(self, clone: Path) -> None:
        run_sweep(clone, MEDIUM, workers=2)
        (check,) = [e for e in events(clone) if e["event"] == "parallel_check"]
        assert check["performed"] is True and check["parallel_allowed"] is True
        assert check["serial_trade_log_sha256"] == check["parallel_trade_log_sha256"]
        assert len(check["serial_trade_log_sha256"]) == 64

    def test_parallel_launches_really_overlap_in_time(
        self, clone: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Both probe workers are alive at once: the second launch precedes the first finish."""
        monkeypatch.setenv("FAKE_MODE", "slow")
        run_sweep(clone, MEDIUM, workers=2)
        together = [e for e in events(clone) if e.get("phase") == "check-parallel"]
        assert together[0]["pid"] != together[1]["pid"]
        assert [e["event"] for e in together] == ["launch", "launch", "finish", "finish"]


# --------------------------------------------------------------------------------------
# Resumption after a power cut
# --------------------------------------------------------------------------------------
class TestResumption:
    def test_a_second_invocation_runs_only_what_the_first_left_missing(
        self, clone: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("FAKE_MODE", "fail_after=2")
        first = run_sweep(clone, MEDIUM)
        assert len(first.ledger.points) == 2 and len(first.failed) == 2 and first.exit_code == 1
        sealed = sorted(
            p.name
            for p in (clone / "data" / "backtests").iterdir()
            if not p.name.endswith("-failed")
        )
        monkeypatch.setenv("FAKE_MODE", "")
        second = run_sweep(clone, MEDIUM)
        assert second.exit_code == 0 and second.ledger.complete and len(second.ledger.points) == 4
        starts = [e for e in events(clone) if e["event"] == "sweep_start"]
        assert [s["to_run"] for s in starts] == [4, 2]
        survivors = [p.name for p in (clone / "data" / "backtests").iterdir() if p.name in sealed]
        assert sorted(survivors) == sealed, "the sealed runs were not touched"

    def test_a_record_inside_an_unsealed_running_directory_is_not_a_run(
        self, clone: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("FAKE_MODE", "noseal")
        first = run_sweep(clone, SMALL)
        assert first.exit_code == 1 and len(first.ledger.points) == 0
        assert [s.reason for s in first.ledger.skipped] == [sel.SkipReason.NOT_SEALED] * 2
        monkeypatch.setenv("FAKE_MODE", "")
        second = run_sweep(clone, SMALL)
        assert second.exit_code == 0 and len(second.ledger.points) == 2
        assert len(second.ledger.skipped) == 2, "the litter stays listed and does not block"

    def test_a_failed_worker_is_reported_with_its_exit_status_and_the_rest_still_run(
        self, clone: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("FAKE_MODE", "crash=fast_period20")
        result = run_sweep(clone, MEDIUM)
        assert len(result.failed) == 2 and {f.returncode for f in result.failed} == {1}
        assert len(result.ledger.points) == 2 and result.exit_code == 1
        report = s6._report(result, MEDIUM)
        assert "FAILED" in report and "exit status 1" in report and "NOT COMPLETE" in report

    def test_a_worker_lost_in_the_check_and_recovered_by_the_sweep_is_reported_and_complete(
        self, clone: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """P118's run 3 (M5m-444, M5m-445, R-CQ): the check's second worker died on a stamp collision, the sweep
        ran that variant itself and the ledger read complete, yet the invocation said NOT COMPLETE and exited 1."""
        monkeypatch.setenv("FAKE_MODE", "slow,crash_once=trend_filter_period200")
        result = run_sweep(clone, SMALL, workers=2)
        assert result.check.performed and result.check.parallel_allowed
        assert result.ledger.complete and len(result.ledger.points) == 2
        assert result.failed == () and result.exit_code == 0
        assert [(f.phase, f.returncode) for f in result.recovered] == [("check-parallel", 1)]
        report = s6._report(result, SMALL)
        assert "LOST" in report and "check-parallel" in report and "exit status 1" in report
        assert "RECOVERED" in report and "sealed record" in report
        assert "  COMPLETE" in report and "NOT COMPLETE" not in report and "FAILED" not in report
        end = [e for e in events(clone) if e["event"] == "sweep_end"][-1]
        assert end["complete"] is True and end["failed"] == []
        assert [r["phase"] for r in end["recovered"]] == ["check-parallel"]

    def test_a_worker_lost_and_never_recovered_is_still_failed_and_not_complete(
        self, clone: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("FAKE_MODE", "crash=trend_filter_period200")
        result = run_sweep(clone, SMALL, workers=2)
        assert result.recovered == () and len(result.failed) >= 1 and result.exit_code == 1
        report = s6._report(result, SMALL)
        assert "FAILED" in report and "NOT COMPLETE" in report and "RECOVERED" not in report

    def test_the_probe_runs_the_first_variant_of_each_timeframe_serially_and_stops(
        self, clone: Path
    ) -> None:
        result = run_sweep(clone, PROBE, workers=4, probe=True)
        launched = [e for e in events(clone) if e["event"] == "launch"]
        assert [e["variant"]["timeframe"] for e in launched] == ["1h", "4h", "1d"]
        assert all(e["variant"]["filtered"] is False and e["workers"] == 1 for e in launched)
        assert "parallel_check" not in kinds(clone)
        assert len(result.ledger.points) == 3 and result.exit_code == 1, (
            "a probe is never a complete sweep"
        )
        assert events(clone)[0]["probe"] is True

    def test_the_probe_takes_the_first_variant_of_each_family_and_timeframe_heaviest_first(
        self, clone: Path
    ) -> None:
        """The two strategies cost very different amounts a bar, so a probe must time both."""
        result = run_sweep(clone, BOTH, workers=4, probe=True)
        launched = [e["variant"] for e in events(clone) if e["event"] == "launch"]
        assert [(v["family"], v["timeframe"]) for v in launched] == [
            ("rsi", "1h"),
            ("sma_crossover", "1h"),
            ("rsi", "4h"),
            ("sma_crossover", "4h"),
        ]
        assert all(v["filtered"] is False for v in launched)
        assert len(result.ledger.points) == 4 and result.exit_code == 1


# --------------------------------------------------------------------------------------
# The pool and the report
# --------------------------------------------------------------------------------------
class StubProcess:
    pid = 4242

    def __init__(self) -> None:
        self.terminated = False

    def poll(self) -> int | None:
        return None

    def terminate(self) -> None:
        self.terminated = True


class TestThePool:
    def test_an_interrupt_terminates_what_it_started_records_it_and_propagates(
        self, clone: Path
    ) -> None:
        manifest = s6.Manifest(clone / "data" / "m.jsonl", lambda: datetime(2026, 1, 1, tzinfo=UTC))
        started: list[StubProcess] = []

        def launcher(argv: Any, cwd: Path, log: Path) -> Any:
            stub = StubProcess()
            started.append(stub)
            return stub

        def interrupt(_seconds: float) -> None:
            raise KeyboardInterrupt

        variants = list(SMALL.variants())
        with pytest.raises(KeyboardInterrupt):
            s6.run_pool(
                variants, workers=2, phase="sweep", argv_for=fake_argv, root=clone,
                logs=clone / "data" / "logs", manifest=manifest, launcher=launcher, sleep=interrupt,
            )  # fmt: skip
        assert len(started) == 2 and all(s.terminated for s in started)
        last = json.loads((clone / "data" / "m.jsonl").read_text(encoding="ascii").splitlines()[-1])
        assert last["event"] == "interrupted" and last["terminated"] == [4242, 4242]

    def test_it_never_runs_more_than_the_workers_it_was_given(self, clone: Path) -> None:
        manifest = s6.Manifest(clone / "data" / "m.jsonl", lambda: datetime(2026, 1, 1, tzinfo=UTC))
        live = {"now": 0, "most": 0}

        class Counting(StubProcess):
            def __init__(self) -> None:
                super().__init__()
                live["now"] += 1
                live["most"] = max(live["most"], live["now"])
                self.polls = 0

            def poll(self) -> int | None:
                self.polls += 1
                if self.polls >= 2:
                    live["now"] -= 1
                    return 0
                return None

        done = s6.run_pool(
            list(MEDIUM.variants()), workers=2, phase="sweep", argv_for=fake_argv, root=clone,
            logs=clone / "data" / "logs", manifest=manifest, launcher=lambda argv, cwd, log: Counting(),
            sleep=lambda s: None,
        )  # fmt: skip
        assert len(done) == 4 and live["most"] == 2


class TestTheReport:
    def test_it_names_missing_duplicated_conflicting_off_grid_skipped_and_failed(self) -> None:
        variants = list(SMALL.variants())
        found: list[sel.PointRun | sel.SkippedRun] = [
            point(variants[0], bulk(3, 1), run="a"),
            point(variants[0], bulk(3, 1), run="b"),
            sel.SkippedRun("odd", sel.SkipReason.OFF_GRID, "the guard named no declared variant"),
            sel.SkippedRun("later", sel.SkipReason.NOT_SEALED, "never renamed"),
        ]
        ledger = sel.reconcile(SMALL, found)
        failed = (s6.Finished(variants[1], 99, 3, 1.5),)
        text = s6._report(s6.SweepResult(ledger, s6.Check(False, False, "x"), failed, 1), SMALL)
        assert "variants declared 2; with a sealed evidence-eligible record 1" in text
        assert "MISSING" in text and "DUPLICATED" in text and "a, b" in text
        assert "OFF-GRID odd" in text and "SKIPPED later: not_sealed" in text
        assert "FAILED" in text and "exit status 3" in text and "NOT COMPLETE" in text

    def test_a_recovered_loss_is_printed_as_lost_then_recovered_and_the_report_is_complete(
        self,
    ) -> None:
        variants = list(SMALL.variants())
        found = [point(v, bulk(3, 1), run=f"r{i}") for i, v in enumerate(variants)]
        ledger = sel.reconcile(SMALL, found)
        lost = (s6.Finished(variants[1], 99, 1, 1.4, "check-parallel"),)
        result = s6.SweepResult(ledger, s6.Check(True, True, "equal"), (), 0, lost)
        text = s6._report(result, SMALL)
        assert "LOST" in text and "exit status 1 in check-parallel" in text
        assert "RECOVERED" in text and "sealed record r1" in text
        assert "  COMPLETE" in text and "FAILED" not in text and "NOT COMPLETE" not in text

    def test_a_clean_complete_ledger_says_complete(self) -> None:
        variants = list(SMALL.variants())
        found = [point(v, bulk(3, 1), run=f"r{i}") for i, v in enumerate(variants)]
        ledger = sel.reconcile(SMALL, found)
        text = s6._report(s6.SweepResult(ledger, s6.Check(False, False, ""), (), 0), SMALL)
        assert "  COMPLETE" in text and "NOT COMPLETE" not in text and "MISSING" not in text
        assert "parallel check: not performed" in text


# --------------------------------------------------------------------------------------
# The command
# --------------------------------------------------------------------------------------
class TestTheCommand:
    def protocol_file(self, clone: Path, text: str) -> Path:
        target = clone / "docs" / "research" / "PROTOCOL.md"
        target.parent.mkdir(parents=True)
        target.write_text(text, encoding="utf-8", newline="\n")
        return target

    def test_a_dry_run_prints_the_plan_and_launches_nothing(
        self, clone: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        file = self.protocol_file(clone, MEDIUM_TEXT)
        assert s6.main(["--clone", str(clone), "--protocol", str(file), "--dry-run"]) == 0
        out = capsys.readouterr().out
        assert "plan: 4 of 4 variants to run; 0 already have a record" in out
        assert (
            "-m trading_bot backtest --start 2017-08-17 --end 2024-01-01 --stop-slippage 1.20"
            in out
        )
        assert not (clone / "data" / "manifest.jsonl").exists()
        assert not (clone / "data" / "s6_sweep_manifest.jsonl").exists()

    def test_main_runs_a_sweep_end_to_end_and_prints_the_ledger(
        self, clone: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        file = self.protocol_file(clone, SMALL_TEXT)
        monkeypatch.setattr(
            s6, "backtest_argv", lambda python, v, rules: fake_argv(v, SMALL.sha256)
        )
        code = s6.main(["--clone", str(clone), "--protocol", str(file)], poll_s=0.02)
        out = capsys.readouterr().out
        assert code == 0 and "S6 SWEEP LEDGER" in out and "  COMPLETE" in out
        assert (clone / "data" / "s6_sweep_manifest.jsonl").is_file()
        assert (clone / "data" / "s6_sweep_logs").is_dir()

    def test_workers_below_one_are_refused(
        self, clone: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        assert s6.main(["--clone", str(clone), "--workers", "0"]) == 2
        assert "--workers must be at least 1" in capsys.readouterr().err

    def test_an_unusable_protocol_is_refused(
        self, clone: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        assert s6.main(["--clone", str(clone), "--protocol", str(clone / "nope.md")]) == 2
        assert "the protocol cannot be used" in capsys.readouterr().err

    def test_the_default_protocol_is_the_clones_own(
        self, clone: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        self.protocol_file(clone, SMALL_TEXT)
        assert s6.main(["--clone", str(clone), "--dry-run"]) == 0
        assert "plan: 2 of 2 variants to run" in capsys.readouterr().out


def test_the_real_protocol_has_216_variants_so_the_narrowed_ones_are_cuts_of_it() -> None:
    assert len(list(PROTOCOL.variants())) == 216
    assert [len(list(p.variants())) for p in (SMALL, MEDIUM, PROBE)] == [2, 4, 6]
    assert replace(PROTOCOL).sha256 == PROTOCOL.sha256
