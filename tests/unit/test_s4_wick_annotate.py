"""``scripts/s4_wick_annotate.py``: the R-DR/R-DS wick annotation (M5m P135).

Every capture, run directory and series here is a few synthetic lines in the shape the bot and the backtest write, and every
interval, bar range and count is worked by hand beside the assertion that pins it, because a tool whose expected values were
taken from its own output proves nothing. The frozen ``s4_compare`` and the committed E2 wrapper are imported and run as they
stand; where the tool must agree with either, a test compares the disagreement list it rebuilds with the one they print.
"""

from __future__ import annotations

import csv
import dataclasses
import json
import re
import sys
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from typing import ClassVar

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

import s4_compare as s4
import s4_latch_compare as e2
import s4_wick_annotate as wick
from trade_census import Trade, build_trades, parse_capture

from trading_bot.backtesting.simulated_executor import SimulatedTrade

UTC = timezone.utc
DAY = "2026-10-12"
WINDOW = ("2026-10-12T00:00:00Z", "2026-10-13T00:00:00Z")
M = datetime(2026, 10, 13, tzinfo=UTC)
VERDICT_WORDS = re.compile(r"\b(PASS|PASSES|PASSED|FAIL|FAILS|FAILED|INCONCLUSIVE)\b")
ONE_MINUTE = timedelta(minutes=1)


def t(clock: str) -> str:
    return f"{DAY}T{clock}"


def at(clock: str) -> datetime:
    return datetime.fromisoformat(f"{DAY}T{clock}+00:00")


def line(stamp: str, pid: int, text: str, level: str = "INFO") -> str:
    return f"{stamp}Z | {level:<8} | pid={pid} | trading_bot.x | {text}"


def boot(stamp: str, pid: int, verdict: str = "accepted", reasons: str = "none") -> str:
    return line(
        stamp,
        pid,
        f"Startup provenance {verdict} event=boot_provenance verdict={verdict} "
        f"refusal_reasons={reasons} unknown_reasons=none install_kind=vcs code_intact=true",
    )


def place(stamp: str, pid: int, symbol: str, signal: str) -> str:
    return line(
        stamp,
        pid,
        f"Order list placed event=order_placed symbol={symbol} quantity=1 entry=100 stop_loss=98 "
        f"order_list_id={re.sub(r'[^0-9]', '', signal)[:12]} list_client_order_id=tb1-{symbol}-{re.sub(r'[^0-9]', '', signal)}-0-L "
        f"entry_bar_time={signal}+00:00",
    )


def close_booked(stamp: str, pid: int, symbol: str, candle: str) -> str:
    return line(
        stamp,
        pid,
        f"Closed {symbol} event=close_booked symbol={symbol} "
        f"order_id={re.sub(r'[^0-9]', '', candle)[:12]} quantity=1 quote_total=101 "
        f"realised=1 candle_time={candle}+00:00",
    )


def leg_booked(stamp: str, pid: int, symbol: str, filled: str) -> str:
    return line(
        stamp,
        pid,
        f"Booked exit for {symbol} event=exit_booked symbol={symbol} quote_total=98 "
        f"realised=-2 order_id=2 quantity=1 leg=SL filled_at={filled}+00:00",
    )


def stopped(stamp: str, pid: int) -> str:
    return line(stamp, pid, "Trading engine stopped event=engine_stopped clean_shutdown=True")


def backtest_row(
    symbol: str,
    entry_open: str,
    *,
    exit_bar_open: str = "",
    timeframe: str = "1m",
    exit_reason: str = "close",
) -> dict[str, str]:
    zoned = f"{entry_open}+00:00"
    return {
        "symbol": symbol,
        "timeframe": timeframe,
        "signal_bar_open": zoned,
        "entry_bar_open": zoned,
        "entry_price": "100",
        "entry_quote_total": "100",
        "realised": "1",
        "exit_reason": exit_reason,
        "exit_bar_open": f"{exit_bar_open}+00:00" if exit_bar_open else "",
        "exit_price": "101",
    }


def run_dir(tmp_path: Path, rows: list[dict[str, str]], *, eligible: object = True) -> Path:
    directory = tmp_path / "run"
    directory.mkdir()
    record: dict[str, object] = {
        "schema": 4,
        "provenance": {"verdict": "accepted", "refusal_reasons": "none"},
        "results": {"trades": len(rows)},
        "pairs": [
            {"symbol": "BTCUSDT", "timeframe": "1m"},
            {"symbol": "ETHUSDT", "timeframe": "5m"},
        ],
        "strategy": {"name": "sma_crossover", "params": {"fast_period": 3, "slow_period": 8}},
        "window": {"data_dir": str(tmp_path / "store")},
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


def capture(tmp_path: Path, lines: list[str], name: str = "live.log") -> Path:
    path = tmp_path / name
    path.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    return path


def argv(
    run: Path, live: Path, *, analysis: str = "primary", window: tuple[str, str] = WINDOW
) -> list[str]:
    return [
        "--run", str(run), "--capture", str(live),
        "--window-start", window[0], "--window-end", window[1],
        "--analysis", analysis,
    ]  # fmt: skip


def bar(clock: str, *, open_: str = "100", high: str = "100", low: str = "100") -> wick.Bar:
    return wick.Bar(at(clock), Decimal(open_), Decimal(high), Decimal(low))


@dataclass(frozen=True)
class FakeCandle:
    open_time: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal


class FakeStore:
    """A 1m series for the whole day, flat at 100 except where a test widens a bar."""

    wide: ClassVar[dict[tuple[str, str], tuple[str, str]]] = {}

    def __init__(self, root: Path) -> None:
        self.root = root

    def candles(
        self, symbol: str, interval: str, start: datetime, end: datetime
    ) -> Iterator[FakeCandle]:
        if interval != "1m":
            return
        moment = at("00:00:00")
        index = 0
        while moment < M:
            if start <= moment < end:
                high, low = self.wide.get((symbol, moment.strftime("%H:%M")), ("100", "100"))
                yield FakeCandle(
                    moment, Decimal(100), Decimal(high), Decimal(low), Decimal(100) + index
                )
            moment += ONE_MINUTE
            index += 1


@pytest.fixture
def widen(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    store = tmp_path / "store"
    store.mkdir()
    monkeypatch.setattr(wick, "HistoricalStore", FakeStore)
    monkeypatch.setattr(s4, "HistoricalStore", FakeStore)
    monkeypatch.setattr(e2, "HistoricalStore", FakeStore)
    monkeypatch.setattr(FakeStore, "wide", {})

    def set_wide(symbol: str, clock: str, high: str, low: str = "100") -> None:
        FakeStore.wide[(symbol, clock)] = (high, low)

    return set_wide


def rows_of(out: str) -> list[str]:
    return [text for text in out.splitlines() if " entry bar " in text and "interval [" in text]


def frozen_list(out: str) -> list[tuple[str, str, str, str]]:
    found = re.findall(
        r"\[([^\]]+)\] (live only|backtest only|different exit) (\w+) signal bar (\S+):", out
    )
    return [(cause, kind, symbol, close) for cause, kind, symbol, close in found]


def wick_list(out: str) -> list[tuple[str, str, str, str]]:
    found = re.findall(
        r"(\w+) entry bar (\S+) \[([^\]]+)\] (live only|backtest only|different exit) interval", out
    )
    return [
        (
            cause,
            kind,
            symbol,
            (datetime.fromisoformat(opened) - timedelta(milliseconds=1)).isoformat(),
        )
        for symbol, opened, cause, kind in found
    ]


class TestWhatIsWide:
    def test_the_bound_itself_is_wide_and_the_strict_inequality_is_not_what_is_asked(self) -> None:
        assert (
            wick.annotate([bar("10:00", high="103")], wick.Holding(at("10:00"), at("10:05"))).wide
            == "yes"
        )

    def test_two_point_nine_nine_nine_percent_is_not_wide(self) -> None:
        result = wick.annotate(
            [bar("10:00", high="102.999")], wick.Holding(at("10:00"), at("10:05"))
        )
        assert result.wide == "no"
        assert result.widest == Decimal("0.02999")

    def test_three_point_zero_zero_one_percent_is_wide(self) -> None:
        assert (
            wick.annotate(
                [bar("10:00", high="103.001")], wick.Holding(at("10:00"), at("10:05"))
            ).wide
            == "yes"
        )

    def test_the_range_is_taken_from_the_low_to_the_high_over_the_open(self) -> None:
        result = wick.annotate(
            [bar("10:00", open_="200", high="210", low="190")],
            wick.Holding(at("10:00"), at("10:05")),
        )
        assert result.widest == Decimal("0.1")

    def test_a_bar_whose_open_is_not_positive_has_no_range(self) -> None:
        assert wick.bar_range(bar("10:00", open_="0", high="5", low="0")) is None
        result = wick.annotate(
            [bar("10:00", open_="0", high="5", low="0")], wick.Holding(at("10:00"), at("10:05"))
        )
        assert result == wick.Annotation("unknown", None, 0)

    def test_the_widest_bar_decides_and_the_count_of_bars_is_reported(self) -> None:
        bars = [bar("10:00"), bar("10:01", high="105"), bar("10:02", high="101")]
        result = wick.annotate(bars, wick.Holding(at("10:00"), at("10:05")))
        assert (result.wide, result.widest, result.bars) == ("yes", Decimal("0.05"), 3)


class TestTheHalfOpenInterval:
    HOLDING = wick.Holding(at("10:00"), at("10:10"))

    def test_a_wide_bar_opening_at_the_entry_bars_open_is_inside(self) -> None:
        assert wick.annotate([bar("10:00", high="110"), bar("10:05")], self.HOLDING).wide == "yes"

    def test_a_wide_bar_opening_at_the_exit_bars_close_is_outside(self) -> None:
        result = wick.annotate([bar("10:05"), bar("10:10", high="110")], self.HOLDING)
        assert (result.wide, result.bars) == ("no", 1)

    def test_a_wide_bar_opening_one_minute_before_the_exit_bars_close_is_inside(self) -> None:
        assert wick.annotate([bar("10:09", high="110")], self.HOLDING).wide == "yes"

    def test_a_wide_bar_before_the_entry_is_outside(self) -> None:
        result = wick.annotate([bar("09:59", high="110"), bar("10:03")], self.HOLDING)
        assert (result.wide, result.bars) == ("no", 1)

    def test_no_bar_inside_is_unknown_and_not_no(self) -> None:
        assert wick.annotate([bar("09:00", high="110")], self.HOLDING) == wick.Annotation(
            "unknown", None, 0
        )

    def test_a_reader_that_could_not_serve_the_range_is_unknown(self) -> None:
        assert wick.annotate(None, self.HOLDING) == wick.Annotation("unknown", None, 0)


class TestTheExitBarsClose:
    def trade(self, lines: list[str]) -> Trade:
        found = build_trades(parse_capture(lines), "USDT")
        assert len(found) == 1
        return found[0]

    def test_the_epoch_aligned_floor_of_a_five_minute_bar(self) -> None:
        assert wick.floor_to_bar(at("22:32:10"), timedelta(minutes=5)) == at("22:30:00")
        assert wick.floor_to_bar(at("22:35:00"), timedelta(minutes=5)) == at("22:35:00")

    def test_a_strategy_close_ends_one_millisecond_after_its_signal_bars_close(self) -> None:
        trade = self.trade(
            [
                place(t("22:00:01"), 1, "ETHUSDT", t("21:59:59.999000")),
                close_booked(t("22:40:03"), 1, "ETHUSDT", t("22:39:59.999000")),
            ]
        )
        assert wick.live_exit_close(trade, timedelta(minutes=5), M) == at("22:40:00")

    def test_a_protective_leg_fill_ends_at_the_close_of_the_bar_that_contains_it(self) -> None:
        trade = self.trade(
            [
                place(t("22:00:01"), 1, "ETHUSDT", t("21:59:59.999000")),
                leg_booked(t("22:33:01"), 1, "ETHUSDT", t("22:32:10")),
            ]
        )
        assert wick.live_exit_close(trade, timedelta(minutes=5), M) == at("22:35:00")

    def test_a_fill_exactly_on_a_bar_boundary_belongs_to_the_bar_that_opens_there(self) -> None:
        trade = self.trade(
            [
                place(t("22:00:01"), 1, "ETHUSDT", t("21:59:59.999000")),
                leg_booked(t("22:35:01"), 1, "ETHUSDT", t("22:35:00")),
            ]
        )
        assert wick.live_exit_close(trade, timedelta(minutes=5), M) == at("22:40:00")

    def test_a_booking_with_no_exit_instant_is_read_as_open_at_m(self) -> None:
        raw = line(
            t("22:33:01"),
            1,
            "Booked exit for ETHUSDT event=exit_booked symbol=ETHUSDT quote_total=98 "
            "realised=-2 order_id=2 quantity=1",
        )
        trade = self.trade([place(t("22:00:01"), 1, "ETHUSDT", t("21:59:59.999000")), raw])
        assert trade.exit_time is None
        assert wick.live_exit_close(trade, timedelta(minutes=5), M) == M

    def test_the_backtest_row_ends_at_its_exit_bar_open_plus_the_pairs_timeframe(
        self, tmp_path: Path
    ) -> None:
        rows = [
            backtest_row("BTCUSDT", t("02:20:00"), exit_bar_open=t("02:39:00")),
            backtest_row("ETHUSDT", t("02:20:00"), exit_bar_open=t("02:35:00"), timeframe="5m"),
            backtest_row("BTCUSDT", t("03:00:00")),
        ]
        run = run_dir(tmp_path, rows)
        closes = wick.backtest_exit_closes(run / "trades.csv", M)
        assert closes[("BTCUSDT", at("02:20:00"))] == at("02:40:00")
        assert closes[("ETHUSDT", at("02:20:00"))] == at("02:40:00")
        assert closes[("BTCUSDT", at("03:00:00"))] == M

    def test_a_file_without_the_exit_column_is_an_input_error(self, tmp_path: Path) -> None:
        path = tmp_path / "trades.csv"
        path.write_text(
            "symbol,entry_bar_open\nBTCUSDT,2026-10-12T02:20:00+00:00\n", encoding="utf-8"
        )
        with pytest.raises(s4.InputError):
            wick.backtest_exit_closes(path, M)


class TestTheIntervalOfEachKind:
    def build(self, tmp_path: Path) -> tuple[Path, Path]:
        lines = [
            boot(t("00:00:01"), 11),
            place(t("02:20:03"), 11, "BTCUSDT", t("02:19:59.999000")),
            close_booked(t("02:30:03"), 11, "BTCUSDT", t("02:29:59.999000")),
            place(t("04:10:03"), 11, "BTCUSDT", t("04:09:59.999000")),
            close_booked(t("04:20:03"), 11, "BTCUSDT", t("04:19:59.999000")),
        ]
        rows = [
            backtest_row(
                "BTCUSDT", t("02:20:00"), exit_bar_open=t("02:39:00"), exit_reason="stop_loss"
            ),
            backtest_row("BTCUSDT", t("06:00:00"), exit_bar_open=t("06:09:00")),
        ]
        return run_dir(tmp_path, rows), capture(tmp_path, lines)

    def test_a_wide_bar_in_the_stretch_only_the_backtest_held_makes_the_pair_wide(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str], widen
    ) -> None:
        widen("BTCUSDT", "02:35", "110")
        run, live = self.build(tmp_path)
        assert wick.main(argv(run, live)) == 0
        pair = [r for r in rows_of(capsys.readouterr().out) if "different exit" in r]
        assert len(pair) == 1
        assert "interval [2026-10-12T02:20:00+00:00, 2026-10-12T02:40:00+00:00)" in pair[0]
        assert "wide=yes max_range=10.000000%" in pair[0]

    def test_a_wide_bar_in_the_stretch_only_the_live_bot_held_makes_the_pair_wide(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str], widen
    ) -> None:
        lines = [
            boot(t("00:00:01"), 11),
            place(t("02:20:03"), 11, "BTCUSDT", t("02:19:59.999000")),
            close_booked(t("02:50:03"), 11, "BTCUSDT", t("02:49:59.999000")),
        ]
        rows = [
            backtest_row(
                "BTCUSDT", t("02:20:00"), exit_bar_open=t("02:29:00"), exit_reason="stop_loss"
            )
        ]
        widen("BTCUSDT", "02:45", "110")
        run, live = run_dir(tmp_path, rows), capture(tmp_path, lines)
        assert wick.main(argv(run, live)) == 0
        pair = [r for r in rows_of(capsys.readouterr().out) if "different exit" in r]
        assert len(pair) == 1
        assert "interval [2026-10-12T02:20:00+00:00, 2026-10-12T02:50:00+00:00)" in pair[0]
        assert "wide=yes" in pair[0]

    def test_a_wide_bar_inside_neither_holding_period_leaves_the_pair_unwide(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str], widen
    ) -> None:
        widen("BTCUSDT", "02:10", "110")
        run, live = self.build(tmp_path)
        assert wick.main(argv(run, live)) == 0
        pair = [r for r in rows_of(capsys.readouterr().out) if "different exit" in r]
        assert "wide=no" in pair[0]

    def test_the_same_bar_after_the_union_ends_does_not_make_it_wide(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str], widen
    ) -> None:
        widen("BTCUSDT", "02:40", "110")
        run, live = self.build(tmp_path)
        assert wick.main(argv(run, live)) == 0
        pair = [r for r in rows_of(capsys.readouterr().out) if "different exit" in r]
        assert "wide=no" in pair[0]

    def test_a_live_only_entry_takes_the_live_holding_period(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str], widen
    ) -> None:
        widen("BTCUSDT", "04:12", "104")
        run, live = self.build(tmp_path)
        assert wick.main(argv(run, live)) == 0
        only = [r for r in rows_of(capsys.readouterr().out) if "live only" in r]
        assert len(only) == 1
        assert "interval [2026-10-12T04:10:00+00:00, 2026-10-12T04:20:00+00:00)" in only[0]
        assert "wide=yes max_range=4.000000%" in only[0]

    def test_a_backtest_only_entry_with_no_wide_bar_is_wide_no_and_never_no_live_position(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str], widen
    ) -> None:
        run, live = self.build(tmp_path)
        assert wick.main(argv(run, live)) == 0
        out = capsys.readouterr().out
        only = [r for r in rows_of(out) if "backtest only" in r]
        assert len(only) == 1
        assert "interval [2026-10-12T06:00:00+00:00, 2026-10-12T06:10:00+00:00)" in only[0]
        assert "wide=no max_range=0.000000%" in only[0]
        assert "no live position" not in out

    def test_a_backtest_only_entry_with_a_wide_bar_in_its_period_is_wide_yes(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str], widen
    ) -> None:
        widen("BTCUSDT", "06:09", "130")
        run, live = self.build(tmp_path)
        assert wick.main(argv(run, live)) == 0
        only = [r for r in rows_of(capsys.readouterr().out) if "backtest only" in r]
        assert "wide=yes max_range=30.000000%" in only[0]


class TestAPositionOpenAtM:
    def build(self, tmp_path: Path) -> tuple[Path, Path]:
        lines = [boot(t("00:00:01"), 11)]
        rows = [backtest_row("BTCUSDT", t("23:30:00"))]
        return run_dir(tmp_path, rows), capture(tmp_path, lines)

    def test_its_period_runs_to_the_window_end_and_a_wide_bar_before_m_counts(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str], widen
    ) -> None:
        widen("BTCUSDT", "23:50", "110")
        run, live = self.build(tmp_path)
        assert wick.main(argv(run, live)) == 0
        found = rows_of(capsys.readouterr().out)
        assert len(found) == 1
        only = found[0]
        assert "interval [2026-10-12T23:30:00+00:00, 2026-10-13T00:00:00+00:00)" in only
        assert "wide=yes" in only

    def test_a_wide_bar_at_m_itself_is_outside(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
        widen,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        run, live = self.build(tmp_path)

        def past_m(self: FakeStore, symbol: str, interval: str, start: datetime, end: datetime):
            yield FakeCandle(M, Decimal(100), Decimal(110), Decimal(100), Decimal(100))
            yield FakeCandle(at("23:59:00"), Decimal(100), Decimal(100), Decimal(100), Decimal(100))

        monkeypatch.setattr(FakeStore, "candles", past_m)
        assert wick.main(argv(run, live)) == 0
        found = rows_of(capsys.readouterr().out)
        assert len(found) == 1
        assert "wide=no" in found[0]


class TestNoBarsIsUnknown:
    def test_an_interval_with_no_recorded_bar_is_unknown_and_counted_apart(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
        widen,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        run = run_dir(
            tmp_path, [backtest_row("BTCUSDT", t("06:00:00"), exit_bar_open=t("06:09:00"))]
        )
        live = capture(tmp_path, [boot(t("00:00:01"), 11)])
        monkeypatch.setattr(FakeStore, "candles", lambda *args: iter(()))
        assert wick.main(argv(run, live)) == 0
        out = capsys.readouterr().out
        found = rows_of(out)
        assert len(found) == 1
        assert "wide=unknown max_range=none" in found[0]
        assert "(wide yes 0, wide no 0, unknown 1)" in out

    def test_a_missing_store_is_unknown(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        run = run_dir(
            tmp_path, [backtest_row("BTCUSDT", t("06:00:00"), exit_bar_open=t("06:09:00"))]
        )
        live = capture(tmp_path, [boot(t("00:00:01"), 11)])
        assert wick.main(argv(run, live)) == 0
        out = capsys.readouterr().out
        assert "recorded series         : unreadable" in out
        assert "wide=unknown" in out


class TestTheCountsByCause:
    def build(self, tmp_path: Path) -> tuple[Path, Path]:
        lines = [
            boot(t("00:00:01"), 11),
            place(t("02:20:03"), 11, "BTCUSDT", t("02:19:59.999000")),
            close_booked(t("02:30:03"), 11, "BTCUSDT", t("02:29:59.999000")),
            place(t("04:10:03"), 11, "BTCUSDT", t("04:09:59.999000")),
            close_booked(t("04:20:03"), 11, "BTCUSDT", t("04:19:59.999000")),
        ]
        rows = [
            backtest_row(
                "BTCUSDT", t("02:20:00"), exit_bar_open=t("02:39:00"), exit_reason="stop_loss"
            ),
            backtest_row("BTCUSDT", t("06:00:00"), exit_bar_open=t("06:09:00")),
            backtest_row("BTCUSDT", t("07:00:00"), exit_bar_open=t("07:09:00")),
        ]
        return run_dir(tmp_path, rows), capture(tmp_path, lines)

    @pytest.mark.parametrize("analysis", ["primary", "e1", "e2"])
    def test_the_counts_by_cause_sum_to_the_length_of_the_list(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str], widen, analysis: str
    ) -> None:
        widen("BTCUSDT", "02:35", "110")
        run, live = self.build(tmp_path)
        assert wick.main(argv(run, live, analysis=analysis)) == 0
        out = capsys.readouterr().out
        total = int(re.search(r"ANNOTATED DISAGREEMENTS \((\d+)\)", out).group(1))
        assert total == 4 == len(rows_of(out))
        counted = [
            int(m.group(1))
            for m in re.finditer(
                r"^  [\w -]+ *: (\d+) \(wide yes \d+, wide no \d+, unknown \d+\)$", out, re.M
            )
        ]
        assert sum(counted) == total
        assert re.search(rf"COUNTS BY CAUSE \({total}\)", out)

    def test_the_wide_columns_add_up_to_each_causes_total(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str], widen
    ) -> None:
        widen("BTCUSDT", "02:35", "110")
        run, live = self.build(tmp_path)
        assert wick.main(argv(run, live)) == 0
        for match in re.finditer(
            r"^  [\w -]+ *: (\d+) \(wide yes (\d+), wide no (\d+), unknown (\d+)\)$",
            capsys.readouterr().out,
            re.M,
        ):
            total, yes, no, unknown = (int(group) for group in match.groups())
            assert total == yes + no + unknown

    def test_every_cause_of_the_closed_list_has_a_count_line_even_at_zero(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str], widen
    ) -> None:
        run, live = self.build(tmp_path)
        assert wick.main(argv(run, live)) == 0
        out = capsys.readouterr().out
        for cause in s4.CAUSES:
            assert re.search(rf"^  {re.escape(cause)} *: \d+ \(wide yes", out, re.M)


class TestTheAnalysesAgreeWithTheirSources:
    def build(self, tmp_path: Path) -> tuple[Path, Path]:
        lines = [
            boot(t("00:00:01"), 11),
            place(t("00:01:00"), 11, "ETHUSDT", t("00:00:59.999000")),
            line(
                t("02:10:00"),
                11,
                'Reconciled 1 position(s) event=reconciliation_pass positions=1 calls=1 queries=1 states="unknown=1"',
            ),
            line(
                t("02:10:00"),
                11,
                '1 position(s) carry protection this bot does not trust event=reconciliation_untrusted count=1 symbols=ETHUSDT detail="x"',
                "WARNING",
            ),
            line(
                t("02:11:00"),
                11,
                "Risk refused ETHUSDT at committed_risk_unknown event=risk_refused symbol=ETHUSDT timeframe=1m action=BUY signal_ts=2026-10-12T02:11:00.999000+00:00 stage=committed_risk_unknown reason=x",
                "INFO",
            ),
            place(t("02:20:03"), 11, "BTCUSDT", t("02:19:59.999000")),
            close_booked(t("02:40:03"), 11, "BTCUSDT", t("02:39:59.999000")),
            line(
                t("02:50:00"),
                11,
                'Reconciled 1 position(s) event=reconciliation_pass positions=1 calls=1 queries=1 states="unknown=1"',
            ),
            line(
                t("02:50:00"),
                11,
                '1 position(s) carry protection this bot does not trust event=reconciliation_untrusted count=1 symbols=ETHUSDT detail="x"',
                "WARNING",
            ),
            stopped(t("03:00:00"), 11),
        ]
        rows = [
            backtest_row(
                "BTCUSDT", t("02:20:00"), exit_bar_open=t("02:39:00"), exit_reason="stop_loss"
            ),
            backtest_row("BTCUSDT", t("02:30:00"), exit_bar_open=t("02:39:00")),
            backtest_row("BTCUSDT", t("03:30:00"), exit_bar_open=t("03:39:00")),
        ]
        return run_dir(tmp_path, rows), capture(tmp_path, lines)

    def test_primary_lists_what_the_frozen_tool_lists(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str], widen
    ) -> None:
        run, live = self.build(tmp_path)
        assert s4.main(argv(run, live)[:-2]) == 0
        frozen = frozen_list(capsys.readouterr().out)
        assert wick.main(argv(run, live)) == 0
        assert wick_list(capsys.readouterr().out) == frozen
        assert len(frozen) == 3

    def test_e1_lists_what_the_frozen_tool_lists_for_its_own_window(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str], widen
    ) -> None:
        run, live = self.build(tmp_path)
        window = (WINDOW[0], "2026-10-12T03:00:00Z")
        assert s4.main(argv(run, live, window=window)[:-2]) == 0
        frozen = frozen_list(capsys.readouterr().out)
        assert wick.main(argv(run, live, analysis="e1", window=window)) == 0
        assert wick_list(capsys.readouterr().out) == frozen
        assert len(frozen) == 2

    def test_e2_lists_what_the_committed_wrapper_lists_and_not_what_the_frozen_tool_does(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str], widen
    ) -> None:
        run, live = self.build(tmp_path)
        assert e2.main(argv(run, live)[:-2]) == 0
        wrapper = frozen_list(capsys.readouterr().out)
        assert s4.main(argv(run, live)[:-2]) == 0
        frozen = frozen_list(capsys.readouterr().out)
        assert wick.main(argv(run, live, analysis="e2")) == 0
        assert wick_list(capsys.readouterr().out) == wrapper
        assert wrapper != frozen


class TestTheReport:
    def build(self, tmp_path: Path) -> tuple[Path, Path]:
        run = run_dir(
            tmp_path, [backtest_row("BTCUSDT", t("06:00:00"), exit_bar_open=t("06:09:00"))]
        )
        return run, capture(tmp_path, [boot(t("00:00:01"), 11)])

    def test_it_begins_with_its_header_and_names_the_analysis_and_the_window(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str], widen
    ) -> None:
        run, live = self.build(tmp_path)
        assert wick.main(argv(run, live, analysis="e1")) == 0
        out = capsys.readouterr().out.splitlines()
        assert out[1] == "DIAGNOSTIC R-DR/R-DS" == wick.HEADER
        assert "  analysis                : e1" in out
        assert (
            "  window (entry bar open) : [2026-10-12T00:00:00+00:00, 2026-10-13T00:00:00+00:00)"
            in out
        )

    def test_it_names_no_verdict_and_prints_no_figure(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str], widen
    ) -> None:
        run, live = self.build(tmp_path)
        assert wick.main(argv(run, live)) == 0
        out = capsys.readouterr().out
        assert VERDICT_WORDS.search(out) is None
        assert "live entries booked" not in out
        assert "reproduced on symbol and bar" not in out

    def test_it_cites_the_two_rulings_and_the_threshold(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str], widen
    ) -> None:
        run, live = self.build(tmp_path)
        assert wick.main(argv(run, live)) == 0
        out = capsys.readouterr().out
        assert "R-DR (docs/S4_CORRECTION_P134.md), R-DS (docs/S4_CORRECTION_P135.md)" in out
        assert ">= 3.00%" in out

    def test_it_carries_the_digests_of_its_inputs(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str], widen
    ) -> None:
        run, live = self.build(tmp_path)
        assert wick.main(argv(run, live)) == 0
        out = capsys.readouterr().out
        for name in ("capture sha256", "run.json sha256", "trades.csv sha256"):
            assert re.search(rf"{name} *: [0-9a-f]{{64}}", out)

    def test_it_reads_and_never_writes(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str], widen
    ) -> None:
        run, live = self.build(tmp_path)

        def listing() -> list[tuple[str, int]]:
            return sorted((str(p), p.stat().st_size) for p in tmp_path.rglob("*") if p.is_file())

        before = listing()
        assert wick.main(argv(run, live)) == 0
        assert listing() == before


class TestTheInputsAreTheFrozenToolsOwn:
    def test_a_run_record_that_is_not_evidence_is_refused(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        run = run_dir(tmp_path, [], eligible=False)
        live = capture(tmp_path, [boot(t("00:00:01"), 11)])
        assert wick.main(argv(run, live)) == 2
        assert capsys.readouterr().out.startswith("REFUSED:")

    def test_a_refused_live_boot_refuses_the_run(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        run = run_dir(tmp_path, [])
        live = capture(tmp_path, [boot(t("00:00:01"), 11, verdict="refused", reasons="dirty")])
        assert wick.main(argv(run, live)) == 2
        assert capsys.readouterr().out.startswith("REFUSED:")

    def test_a_capture_with_no_boot_line_is_refused(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        run = run_dir(tmp_path, [])
        live = capture(tmp_path, [place(t("00:01:00"), 11, "BTCUSDT", t("00:00:59.999000"))])
        assert wick.main(argv(run, live)) == 2

    def test_a_path_under_logs_is_refused_before_it_is_read(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        run = run_dir(tmp_path, [])
        logs = tmp_path / "logs"
        logs.mkdir()
        live = capture(logs, [boot(t("00:00:01"), 11)])
        assert wick.main(argv(run, live)) == 2
        assert capsys.readouterr().out.startswith("REFUSED:")

    def test_an_inverted_window_is_refused(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        run = run_dir(tmp_path, [])
        live = capture(tmp_path, [boot(t("00:00:01"), 11)])
        assert wick.main(argv(run, live, window=(WINDOW[1], WINDOW[0]))) == 2

    def test_an_analysis_that_is_not_one_of_the_three_is_an_argument_error(
        self, tmp_path: Path
    ) -> None:
        run = run_dir(tmp_path, [])
        live = capture(tmp_path, [boot(t("00:00:01"), 11)])
        with pytest.raises(SystemExit) as raised:
            wick.main(argv(run, live, analysis="e3"))
        assert raised.value.code == 2

    def test_the_analysis_is_required(self, tmp_path: Path) -> None:
        run = run_dir(tmp_path, [])
        live = capture(tmp_path, [boot(t("00:00:01"), 11)])
        with pytest.raises(SystemExit) as raised:
            wick.main(argv(run, live)[:-2])
        assert raised.value.code == 2

    def test_the_three_analyses_are_exactly_primary_e1_and_e2(self) -> None:
        assert wick.ANALYSES == ("primary", "e1", "e2")

    def test_the_arguments_are_the_frozen_parsers_plus_analysis(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        with pytest.raises(SystemExit):
            s4.main(["--help"])
        frozen = capsys.readouterr().out
        with pytest.raises(SystemExit):
            wick.main(["--help"])
        mine = capsys.readouterr().out
        for option in (
            "--run",
            "--capture",
            "--window-start",
            "--window-end",
            "--quote-asset",
            "--store",
            "--backtest-log",
        ):
            assert option in frozen and option in mine
        assert "--analysis" in mine and "--analysis" not in frozen
