"""``scripts/s5_report.py``: the door, the split at the boundary, the figures worked by hand, and a report with no verdict.

Every run directory here is written the way the engine writes one (the CSV header is ``SimulatedTrade``'s own
field list, the equity block is ``EquitySummary.to_record``), and every figure is worked by hand beside the
assertion that pins it: a report whose expected values came from its own output proves nothing. One test drives
the REAL ``backtest`` command and reads its record back, so the writer and the reader cannot drift apart.

The scenario, in one place. Initial 10,000 USDT, boundary 2024-01-01. Six trades, each on an entry quote total of
1,000 with a fee of 1 on each leg (so gross = net + 2):

    in sample      2023-06-01 BTC +50 (2023Q2 falling)   2023-07-01 BTC -20 (2023Q3 sideways)   2023-08-01 ETH +30 (2023Q3)
    out of sample  2024-02-01 BTC +100 (2024Q1 rising)   2024-03-01 ETH -40 (2024Q1)            2024-04-01 BTC -10 (2024Q2 falling)

so in sample: net +60, profit factor 80/20 = 4, win rate 2/3; out of sample: net +50, profit factor 100/50 = 2,
BTC +90 (profit factor 10) and ETH -40, regimes rising +60, falling -10, sideways none. Daily closes: in sample
10,050 / 10,030 / 10,060 (drawdown 20 of a 10,050 peak = 0.0020); out of sample, from 10,060, 10,160 / 10,120 /
10,110 (drawdown 50 of a 10,160 peak = 0.0049).
"""

from __future__ import annotations

import csv
import dataclasses
import json
import re
import sys
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

import s5_report as s5

import trading_bot.backtesting.protocol as protocol_module
import trading_bot.main as cli
from tests.unit.backtest_world import build_world
from tests.unit.protocol_world import PROTOCOL, effective
from tests.unit.test_main_backtest import argv as cli_argv
from tests.unit.test_main_backtest import only_record, provenance
from trading_bot.backtesting.candidate import candidate_digest, settings_digest
from trading_bot.backtesting.engine import RUN_RECORD_SCHEMA
from trading_bot.backtesting.metrics import EquitySummary
from trading_bot.backtesting.regimes import document_digest, render_document
from trading_bot.backtesting.simulated_executor import SimulatedTrade

D = Decimal
UTC = timezone.utc
BOUNDARY = date(2024, 1, 1)

IS_TRADES = [
    ("BTCUSDT", "2023-06-01T00:00:00+00:00", "50"),
    ("BTCUSDT", "2023-07-01T00:00:00+00:00", "-20"),
    ("ETHUSDT", "2023-08-01T00:00:00+00:00", "30"),
]
OOS_TRADES = [
    ("BTCUSDT", "2024-02-01T00:00:00+00:00", "100"),
    ("ETHUSDT", "2024-03-01T00:00:00+00:00", "-40"),
    ("BTCUSDT", "2024-04-01T00:00:00+00:00", "-10"),
]
CLOSES = {
    "2023-06-01": "10050",
    "2023-07-01": "10030",
    "2023-12-31": "10060",
    "2024-02-01": "10160",
    "2024-03-01": "10120",
    "2024-04-01": "10110",
}
QUARTERS = {"2023Q2": "falling", "2023Q3": "sideways", "2024Q1": "rising", "2024Q2": "falling"}


def trade_row(symbol: str, entry: str, realised: str) -> dict[str, str]:
    """One ``trades.csv`` row: notional 1,000, a fee of 1 each way, quote total 1,000."""
    gross = D(1000) + D(realised) + 2
    exit_time = (datetime.fromisoformat(entry).replace(hour=12)).isoformat()
    return {
        "symbol": symbol,
        "entry_bar_open": entry,
        "exit_time": exit_time,
        "entry_notional": "1000",
        "entry_fee": "1",
        "entry_quote_total": "1000",
        "exit_gross": str(gross),
        "exit_fee": "1",
        "realised": realised,
    }


def equity_block(closes: dict[str, str]) -> dict[str, object]:
    summary = EquitySummary(
        initial=D(10000),
        final=D(closes[max(closes)]),
        start=datetime(2023, 6, 1, tzinfo=UTC),
        last_at=datetime(2024, 4, 1, tzinfo=UTC),
        samples=len(closes),
        drawdown_peak=D(10160),
        drawdown_trough=D(10110),
        drawdown_peak_at=datetime(2024, 2, 1, tzinfo=UTC),
        drawdown_trough_at=datetime(2024, 4, 1, tzinfo=UTC),
        daily_closes=tuple((date.fromisoformat(k), D(v)) for k, v in sorted(closes.items())),
        open_since=(),
        span_seconds=D(1),
    )
    return summary.to_record()


def labels(tmp_path: Path) -> tuple[Path, str]:
    """A tiny committed-labels file and its digest file, as ``RegimeTable.from_file`` wants them."""
    document = {
        "quarters": [{"quarter": q, "regime": r} for q, r in QUARTERS.items()],
    }
    data = render_document(document)
    path = tmp_path / "REGIME_LABELS.json"
    path.write_bytes(data)
    digest = document_digest(data)
    path.with_name(path.name + ".sha256").write_text(
        digest + "  REGIME_LABELS.json\n", encoding="ascii"
    )
    return path, digest


def make_run(
    tmp_path: Path,
    arm: str,
    *,
    name: str | None = None,
    labels_digest: str | None = None,
    trades: list[tuple[str, str, str]] | None = None,
    schema: int = RUN_RECORD_SCHEMA,
    flag: object = True,
    protocol: object = "decision",
    problems: list[str] | None = None,
    declared: int | None = None,
    params: dict[str, object] | None = None,
    closes: dict[str, str] | None = None,
) -> Path:
    rows = [trade_row(*t) for t in (IS_TRADES + OOS_TRADES if trades is None else trades)]
    eff = effective(arm=arm, params=params)
    directory = tmp_path / (name or f"run-{arm}")
    directory.mkdir()
    record: dict[str, Any] = {
        "schema": schema,
        "evidence_eligible": flag,
        "provenance": {"verdict": "accepted"},
        "code": {"code_commit": "a" * 40},
        "window": {"start_date": "2023-06-01", "end_date": "2024-05-01"},
        "effective": eff,
        "candidate_digest": candidate_digest(eff),
        "settings_digest": settings_digest(eff),
        "protocol": {
            "window_class": "straddling",
            "entry_id": "s5-baseline",
            "kind": "baseline",
            "arm": arm,
        }
        if protocol == "decision"
        else protocol,
        "results": {
            "trades": len(rows) if declared is None else declared,
            "trade_log_sha256": "f" * 64,
        },
        "equity": equity_block(closes or CLOSES),
        "metrics": {"max_drawdown": "0.0123"},
        "regime_labels": None if labels_digest is None else {"sha256": labels_digest},
        "problems": [] if problems is None else problems,
    }
    (directory / "run.json").write_text(
        json.dumps(record, sort_keys=True), encoding="utf-8", newline="\n"
    )
    names = [field.name for field in dataclasses.fields(SimulatedTrade)]
    with (directory / "trades.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=names, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "0") for field in names})
    return directory


def report(tmp_path: Path, *arms: str, regimes: bool = True, **kwargs: Any) -> str:
    path, digest = labels(tmp_path)
    runs = [
        make_run(tmp_path, arm, labels_digest=digest if regimes else None, **kwargs) for arm in arms
    ]
    loaded = [s5.load_run(directory) for directory in runs]
    return s5.render(loaded, PROTOCOL, path)


def section(text: str, heading: str, until: str) -> str:
    start = text.index(heading)
    return text[start : text.index(until, start)]


class TestTheDoor:
    def test_the_minimum_schema_is_the_first_one_with_the_guards_decision(self) -> None:
        assert s5.MIN_SCHEMA == 6
        assert RUN_RECORD_SCHEMA >= s5.MIN_SCHEMA

    @pytest.mark.parametrize(
        ("kwargs", "message"),
        [
            ({"flag": False}, "evidence_eligible"),
            ({"flag": None}, "evidence_eligible"),
            ({"schema": 5}, "needs schema 6"),
            ({"protocol": None}, "no protocol block"),
            ({"problems": ["cash_identity_residual=1"]}, "not a result"),
            ({"declared": 7}, "holds 6 trade"),
        ],
        ids=["flag-false", "flag-absent", "schema-5", "no-protocol", "problems", "trade-count"],
    )
    def test_a_run_that_is_not_evidence_or_not_a_result_is_refused(
        self, tmp_path: Path, kwargs: dict[str, Any], message: str
    ) -> None:
        directory = make_run(tmp_path, "1.2", **kwargs)
        with pytest.raises(s5.ReportRefusedError, match=message):
            s5.load_run(directory)

    def test_a_missing_trades_file_is_refused_not_crashed_on(self, tmp_path: Path) -> None:
        directory = make_run(tmp_path, "1.2")
        (directory / "trades.csv").unlink()
        with pytest.raises(s5.ReportRefusedError, match="cannot be read"):
            s5.load_run(directory)

    def test_a_directory_with_no_record_is_refused(self, tmp_path: Path) -> None:
        with pytest.raises(s5.ReportRefusedError, match="cannot be read as a run record"):
            s5.load_run(tmp_path)

    def test_runs_of_two_candidates_are_refused(self, tmp_path: Path) -> None:
        path, digest = labels(tmp_path)
        first = s5.load_run(make_run(tmp_path, "1.2", labels_digest=digest))
        other = s5.load_run(
            make_run(
                tmp_path,
                "0.66",
                labels_digest=digest,
                params={"fast_period": 10, "slow_period": 50},
            )
        )
        with pytest.raises(s5.ReportRefusedError, match="2 different candidates"):
            s5.render([first, other], PROTOCOL, path)

    def test_two_runs_of_one_arm_are_refused(self, tmp_path: Path) -> None:
        path, digest = labels(tmp_path)
        first = s5.load_run(make_run(tmp_path, "1.2", labels_digest=digest, name="a"))
        again = s5.load_run(make_run(tmp_path, "1.2", labels_digest=digest, name="b"))
        with pytest.raises(s5.ReportRefusedError, match="share one stop-slippage arm"):
            s5.render([first, again], PROTOCOL, path)

    def test_an_arm_the_protocol_does_not_declare_is_refused(self, tmp_path: Path) -> None:
        path, digest = labels(tmp_path)
        run = s5.load_run(make_run(tmp_path, "0.5", labels_digest=digest))
        with pytest.raises(s5.ReportRefusedError, match="does not declare"):
            s5.render([run], PROTOCOL, path)

    def test_no_run_is_refused(self) -> None:
        with pytest.raises(s5.ReportRefusedError, match="no run directory"):
            s5.check_runs([], PROTOCOL)

    def test_labels_that_are_not_the_ones_the_run_used_are_refused(self, tmp_path: Path) -> None:
        path, _digest = labels(tmp_path)
        run = s5.load_run(make_run(tmp_path, "1.2", labels_digest="0" * 64))
        with pytest.raises(s5.ReportRefusedError, match="was labelled by"):
            s5.render([run], PROTOCOL, path)

    def test_labels_that_do_not_match_their_digest_file_are_refused(self, tmp_path: Path) -> None:
        path, digest = labels(tmp_path)
        path.write_bytes(path.read_bytes() + b" ")
        run = s5.load_run(make_run(tmp_path, "1.2", labels_digest=digest))
        with pytest.raises(s5.ReportRefusedError, match="cannot be used"):
            s5.render([run], PROTOCOL, path)


class TestTheSplit:
    def test_trades_are_split_by_the_open_of_their_entry_bar_at_the_boundary(
        self, tmp_path: Path
    ) -> None:
        trades = [
            ("BTCUSDT", "2023-12-31T23:59:00+00:00", "1"),
            ("BTCUSDT", "2024-01-01T00:00:00+00:00", "2"),
        ]
        run = s5.load_run(make_run(tmp_path, "1.2", trades=trades))
        before, after = s5.segments_of(run, BOUNDARY)
        assert [t.realised for t in before.trades] == [D(1)]
        assert [t.realised for t in after.trades] == [D(2)]

    def test_each_segment_starts_from_the_equity_at_the_end_of_the_day_before_it(
        self, tmp_path: Path
    ) -> None:
        run = s5.load_run(make_run(tmp_path, "1.2"))
        before, after = s5.segments_of(run, BOUNDARY)
        assert before.start_equity == D(10000)
        assert after.start_equity == D(10060)
        assert [day.isoformat() for day, _ in before.closes] == [
            "2023-06-01",
            "2023-07-01",
            "2023-12-31",
        ]
        assert [day.isoformat() for day, _ in after.closes] == [
            "2024-02-01",
            "2024-03-01",
            "2024-04-01",
        ]

    def test_a_run_wholly_after_the_boundary_has_an_empty_in_sample_side(
        self, tmp_path: Path
    ) -> None:
        closes = {k: v for k, v in CLOSES.items() if k >= "2024"}
        run = s5.load_run(make_run(tmp_path, "1.2", trades=OOS_TRADES, closes=closes))
        before, after = s5.segments_of(run, BOUNDARY)
        assert before.trades == () and before.closes == ()
        assert after.start_equity == D(10000)

    def test_the_drawdown_of_daily_closes_is_the_largest_fraction_not_the_largest_amount(
        self,
    ) -> None:
        # a 10% decline of 100 and a 5% decline of 500: the fraction decides, as R-AJ's does
        closes = [D(900), D(10000), D(9500)]
        fraction, amount = s5.daily_close_drawdown(D(1000), closes)
        assert (fraction, amount) == (D("0.1"), D(100))

    def test_the_running_peak_starts_at_the_starting_equity(self) -> None:
        assert s5.daily_close_drawdown(D(1000), [D(900)]) == (D("0.1"), D(100))

    def test_a_series_that_never_falls_has_no_drawdown(self) -> None:
        assert s5.daily_close_drawdown(D(1000), [D(1001), D(1002)]) == (D(0), D(0))
        assert s5.daily_close_drawdown(D(1000), []) == (D(0), D(0))

    def test_daily_returns_are_each_close_over_the_previous_one(self) -> None:
        assert s5.daily_returns_of(D(100), [D(110), D(99)]) == (D("0.1"), D("-0.1"))


class TestTheFigures:
    def test_the_in_sample_figures_are_the_hand_worked_ones(self, tmp_path: Path) -> None:
        text = report(tmp_path, "1.2")
        block = section(text, "  IN SAMPLE", "  OUT OF SAMPLE")
        assert "trades 3  wins 2  losses 1  win rate 0.6667" in block
        assert "net P&L 60  gross P&L 66  fees 6" in block
        assert "profit factor net 4.0000" in block
        assert "0.0020 of peak, 20 quote" in block
        assert "equity from 10000 to 10060" in block

    def test_the_out_of_sample_figures_are_the_hand_worked_ones(self, tmp_path: Path) -> None:
        text = report(tmp_path, "1.2")
        block = section(text, "  OUT OF SAMPLE", "  S7 PREVIEW")
        assert "trades 3  wins 1  losses 2  win rate 0.3333" in block
        assert "net P&L 50  gross P&L 56  fees 6" in block
        assert "profit factor net 2.0000" in block
        assert "0.0049 of peak, 50 quote" in block
        assert "equity from 10060 to 10110" in block

    def test_the_pairs_are_broken_out_in_each_segment(self, tmp_path: Path) -> None:
        text = report(tmp_path, "1.2")
        block = section(text, "  OUT OF SAMPLE", "  S7 PREVIEW")
        btc = section(block, "    pair BTCUSDT", "    pair ETHUSDT")
        assert "trades 2  wins 1  losses 1" in btc
        assert "net P&L 90" in btc and "profit factor net 10.0000" in btc
        eth = section(block, "    pair ETHUSDT", "    regime")
        assert "trades 1  wins 0  losses 1" in eth and "net P&L -40" in eth

    def test_the_regimes_are_broken_out_from_the_committed_labels(self, tmp_path: Path) -> None:
        text = report(tmp_path, "1.2")
        block = section(text, "  OUT OF SAMPLE", "  S7 PREVIEW")
        rising = section(block, "    regime rising", "    regime falling")
        assert "trades 2" in rising and "net P&L 60" in rising
        falling = section(block, "    regime falling", "    regime sideways")
        assert "trades 1" in falling and "net P&L -10" in falling
        sideways = section(block, "    regime sideways", "    regime unlabelled")
        assert "trades 0" in sideways

    def test_the_whole_run_per_bar_drawdown_is_printed_apart_and_labelled(
        self, tmp_path: Path
    ) -> None:
        text = report(tmp_path, "1.2")
        assert "WHOLE RUN, per-bar max drawdown (R-AJ): 0.0123" in text
        assert text.count("DAILY CLOSES (not the per-bar figure)") == 2

    def test_the_s7_preview_lists_the_four_quantities_beside_their_thresholds(
        self, tmp_path: Path
    ) -> None:
        text = report(tmp_path, "1.2")
        block = text[text.index("  S7 PREVIEW") :]
        assert "profit factor (net)         figure 2.0000    threshold >= 1.3" in block
        assert "trades                      figure 3    threshold >= 100" in block
        assert "max drawdown (daily-close)  figure 0.0049    threshold <= 0.20" in block
        assert "regimes with net P&L > 0    figure 1 of 3    threshold >= 2" in block

    def test_without_regime_labels_there_is_no_regime_section_and_the_preview_says_so(
        self, tmp_path: Path
    ) -> None:
        text = report(tmp_path, "1.2", regimes=False)
        assert not re.search(r"^    regime ", text, flags=re.MULTILINE)
        assert "n/a (no regime labels)" in text

    def test_the_arms_print_in_ascending_order_whatever_the_order_given(
        self, tmp_path: Path
    ) -> None:
        (tmp_path / "f").mkdir()
        (tmp_path / "b").mkdir()
        forward = report(tmp_path / "f", "0.05", "0.66", "1.2")
        backward = report(tmp_path / "b", "1.2", "0.66", "0.05")
        arms = re.findall(r"ARM stop slippage ([0-9.]+)%", forward)
        assert arms == ["0.05", "0.66", "1.2"]
        assert re.findall(r"ARM stop slippage ([0-9.]+)%", backward) == arms

    def test_the_report_names_the_boundary_the_candidate_and_each_digest(
        self, tmp_path: Path
    ) -> None:
        text = report(tmp_path, "1.2")
        assert "boundary 2024-01-01" in text
        assert PROTOCOL.sha256 in text
        assert candidate_digest(effective(arm="1.2")) in text
        assert "entry s5-baseline  kind baseline" in text
        assert "trade log sha256 " + "f" * 64 in text
        assert re.search(r"record sha256 [0-9a-f]{64}", text)

    def test_the_report_has_no_verdict(self, tmp_path: Path) -> None:
        text = report(tmp_path, "0.05", "0.66", "1.2")
        for word in ("PASS", "FAIL", "INCONCLUSIVE", "pass", "fail"):
            assert word not in text, word


class TestTheCommandLine:
    def test_a_good_set_prints_the_report_and_exits_zero(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        path, digest = labels(tmp_path)
        run = make_run(tmp_path, "1.2", labels_digest=digest)
        protocol_path = Path(__file__).resolve().parents[2] / "docs" / "research" / "PROTOCOL.md"
        code = s5.main([str(run), "--protocol", str(protocol_path), "--regimes", str(path)])
        captured = capsys.readouterr()
        assert code == 0
        assert "ARM stop slippage 1.2%" in captured.out
        assert captured.err == ""

    def test_a_refusal_prints_nothing_on_stdout_and_exits_two(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        run = make_run(tmp_path, "1.2", flag=False)
        protocol_path = Path(__file__).resolve().parents[2] / "docs" / "research" / "PROTOCOL.md"
        assert s5.main([str(run), "--protocol", str(protocol_path)]) == 2
        captured = capsys.readouterr()
        assert captured.out == ""
        assert captured.err.startswith("REFUSED: ")

    def test_an_unreadable_protocol_is_a_refusal_not_a_traceback(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        run = make_run(tmp_path, "1.2")
        assert s5.main([str(run), "--protocol", str(tmp_path / "none.md")]) == 2
        assert capsys.readouterr().err.startswith("REFUSED: ")


class TestAgainstARealRun:
    """The writer's record is the reader's input: a run the real command wrote is read back whole."""

    def test_a_record_the_backtest_command_wrote_is_reported(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        late = dataclasses.replace(PROTOCOL, boundary=date(2030, 1, 1))
        monkeypatch.setattr(protocol_module, "load_protocol", lambda *_a, **_k: late)
        monkeypatch.setattr(cli, "setup_logging", lambda _config: None)
        facts = provenance(accepted=True)
        monkeypatch.setattr(cli, "collect_provenance", lambda *_a, **_k: facts)
        build_world(tmp_path)
        assert cli.main(cli_argv(tmp_path, "--start", "2024-03-12", "--end", "2024-03-14")) == 0
        directory = only_record(tmp_path)
        run = s5.load_run(directory)
        assert run.arm == D("1.2")
        text = s5.render([run], PROTOCOL, tmp_path / "no_labels.json")
        assert "ARM stop slippage 1.2%" in text
        assert "OUT OF SAMPLE" in text and "IN SAMPLE" in text
        capsys.readouterr()
