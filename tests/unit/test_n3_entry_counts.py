"""``scripts/n3_entry_counts.py``: the counts, the window it refuses to widen, and what it prints.

The store is real -- month files written with ``write_month`` -- and small. Every expected figure
is worked by hand from the literals that build the bars, never by the code under test.

**BTCUSDT 1d**, 365 days from 2023-01-01, open = close and high = close + 1, low = close - 1:
the close is 100 for days 0-199, 160 for days 200-299 and 200 from day 300. Then

* C1 and C2 (a close above the prior 20 / 55 highs): day 200 (160 over a high of 101) and day 300
  (200 over a high of 161); the day after each is level with the new high and is not an edge.
* C3 (50 over 200): day 200 only. The averages there are 101.2 and 100.3 against 100 and 100 the
  day before, and the fast one never falls back below the slow one.
* C6 (90-day change from at or below zero to above it): day 200 (160 - 100, after 0) and day 300
  (200 - 160, after 160 - 160 = 0); between them the change is zero from day 290.

**ETHUSDT 1d** is the same bars with day 190 missing. Day 190 is inside the 22-, 57- and 92-row
windows that end on day 200, so the gap rule removes that event for C1, C2 and C6, and the rows
read as consecutive still give it. Day 300 is clear of the gap for all three. C3's window is 201
rows, so the gap also keeps the rule on from day 200; read as consecutive, day 200 is then the
200th row, short of the warm-up, and the cross is not seen on day 201 either (the fast average was
already above the slow one a bar earlier, 101.2 against 100.3), so C3 counts 0 in both readings.

**4h**, Nov-Dec 2023, 366 bars from 2023-11-01T00:00: flat bars (100, 101, 99, 100) except bar 50
(100, 106, 99, 106) and bar 51 (106, 107, 105, 106). C4 fires on bar 50 (106 over a high of 101) and
not on bar 51 (106 is level with the high of bar 50). C5 fires on bar 50 (ATR 2.25, EMA 100.5714,
band 105.0714) and not on bar 51 (ATR 2.2375, EMA 101.0884, band 105.5634, already true). ETHUSDT
4h omits bar 40: a missing bar inside both windows, so the rule suppresses both events.
"""

from __future__ import annotations

import io
import re
import sys
from collections.abc import Sequence
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from trading_bot.core.models import Candle
from trading_bot.data.historical import (
    INTERVAL_MS,
    HistoricalStore,
    Row,
    month_file,
    write_month,
)

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

import n3_entry_counts as n3

UTC = timezone.utc
SOURCE = {"source_url": "https://example.invalid/m.zip", "zip_sha256": "0" * 64}
WIDTH = {"1d": INTERVAL_MS["1d"], "4h": INTERVAL_MS["4h"]}
EPOCH = datetime(1970, 1, 1, tzinfo=UTC)

#: (open, high, low, close)
Ohlc = tuple[int, int, int, int]
FLAT: Ohlc = (100, 101, 99, 100)
SPIKE: Ohlc = (100, 106, 99, 106)
HOLD: Ohlc = (106, 107, 105, 106)


def ms(moment: datetime) -> int:
    return (moment - EPOCH) // timedelta(milliseconds=1)


def money(value: int) -> str:
    return f"{value}.00000000"


def daily_closes() -> list[int]:
    return [100 if day < 200 else 160 if day < 300 else 200 for day in range(365)]


def daily_bars() -> list[Ohlc]:
    return [(c, c + 1, c - 1, c) for c in daily_closes()]


def four_hour_bars() -> list[Ohlc]:
    bars = [FLAT] * 366
    bars[50], bars[51] = SPIKE, HOLD
    return bars


def rows_of(
    start: datetime,
    timeframe: str,
    bars: Sequence[Ohlc],
    *,
    skip: frozenset[int] = frozenset(),
    volumes: Sequence[int] | None = None,
) -> list[Row]:
    width = WIDTH[timeframe]
    rows = []
    for i, (o, h, lo, c) in enumerate(bars):
        if i in skip:
            continue
        opened = ms(start) + i * width
        volume = 1 if volumes is None else volumes[i]
        rows.append(
            Row(opened, money(o), money(h), money(lo), money(c), money(volume), opened + width - 1)
        )
    return rows


def write_series(root: Path, symbol: str, timeframe: str, rows: Sequence[Row]) -> None:
    by_month: dict[str, list[Row]] = {}
    for row in rows:
        month = (EPOCH + timedelta(milliseconds=row.open_time_ms)).strftime("%Y-%m")
        by_month.setdefault(month, []).append(row)
    for month, found in by_month.items():
        write_month(root, symbol, timeframe, month, found, **SOURCE)


def build_store(
    root: Path,
    *,
    btc_volumes: Sequence[int] | None = None,
    eth_daily_skip: frozenset[int] = frozenset({190}),
    eth_four_hour_skip: frozenset[int] = frozenset({40}),
) -> None:
    jan = datetime(2023, 1, 1, tzinfo=UTC)
    nov = datetime(2023, 11, 1, tzinfo=UTC)
    write_series(root, "BTCUSDT", "1d", rows_of(jan, "1d", daily_bars(), volumes=btc_volumes))
    write_series(root, "ETHUSDT", "1d", rows_of(jan, "1d", daily_bars(), skip=eth_daily_skip))
    write_series(root, "BTCUSDT", "4h", rows_of(nov, "4h", four_hour_bars()))
    write_series(
        root, "ETHUSDT", "4h", rows_of(nov, "4h", four_hour_bars(), skip=eth_four_hour_skip)
    )


def report(root: Path, *extra: str) -> tuple[int, str]:
    out = io.StringIO()
    code = n3.main(["--data-dir", str(root), *extra], out)
    return code, out.getvalue()


def table(text: str) -> dict[tuple[str, str], tuple[int, ...]]:
    """The candidate rows: (label, pair) -> (events, no_rdz, suppressed, gated_only)."""
    rows: dict[tuple[str, str], tuple[int, ...]] = {}
    for line in text.splitlines():
        match = re.match(r"^(C[1-6]) \S+\s+(\w+USDT)\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)$", line)
        if match:
            rows[(match.group(1), match.group(2))] = tuple(int(g) for g in match.groups()[2:])
    return rows


def series(text: str) -> dict[tuple[str, str], tuple[int, ...]]:
    """The series rows: (pair, timeframe) -> (bars, slots, missing, gap_runs)."""
    rows: dict[tuple[str, str], tuple[int, ...]] = {}
    for line in text.splitlines():
        match = re.match(r"^(\w+USDT) (1d|4h)\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)$", line)
        if match:
            rows[(match.group(1), match.group(2))] = tuple(int(g) for g in match.groups()[2:])
    return rows


@pytest.fixture(scope="module")
def store(tmp_path_factory: pytest.TempPathFactory) -> Path:
    root = tmp_path_factory.mktemp("n3_store")
    build_store(root)
    return root


@pytest.fixture(scope="module")
def printed(store: Path) -> str:
    code, text = report(store)
    assert code == 0
    return text


class TestTheCounts:
    @pytest.mark.parametrize(
        ("label", "expected"),
        [
            ("C1", (2, 2, 0, 0)),
            ("C2", (2, 2, 0, 0)),
            ("C3", (1, 1, 0, 0)),
            ("C4", (1, 1, 0, 0)),
            ("C5", (1, 1, 0, 0)),
            ("C6", (2, 2, 0, 0)),
        ],
    )
    def test_a_pair_without_a_gap_counts_the_hand_worked_events(
        self, printed: str, label: str, expected: tuple[int, ...]
    ) -> None:
        assert table(printed)[(label, "BTCUSDT")] == expected

    @pytest.mark.parametrize(
        ("label", "expected"),
        [
            ("C1", (1, 2, 1, 0)),
            ("C2", (1, 2, 1, 0)),
            ("C3", (0, 0, 0, 0)),
            ("C4", (0, 1, 1, 0)),
            ("C5", (0, 1, 1, 0)),
            ("C6", (1, 2, 1, 0)),
        ],
    )
    def test_a_missing_bar_suppresses_the_events_whose_window_holds_it(
        self, printed: str, label: str, expected: tuple[int, ...]
    ) -> None:
        assert table(printed)[(label, "ETHUSDT")] == expected

    def test_every_candidate_and_pair_has_a_row(self, printed: str) -> None:
        assert set(table(printed)) == {
            (label, pair) for label in ("C1", "C2", "C3", "C4", "C5", "C6") for pair in n3.PAIRS
        }

    def test_the_events_are_the_ungated_events_less_the_suppressed_plus_the_gated_only(
        self, printed: str
    ) -> None:
        for events, ungated, suppressed, gated_only in table(printed).values():
            assert events == ungated - suppressed + gated_only


class TestTheSeriesFacts:
    def test_a_series_without_a_gap_has_no_missing_slots(self, printed: str) -> None:
        found = series(printed)
        assert found[("BTCUSDT", "1d")] == (365, 365, 0, 0)
        assert found[("BTCUSDT", "4h")] == (366, 366, 0, 0)

    def test_a_missing_bar_is_one_missing_slot_and_one_gap_run(self, printed: str) -> None:
        found = series(printed)
        assert found[("ETHUSDT", "1d")] == (364, 365, 1, 1)
        assert found[("ETHUSDT", "4h")] == (365, 366, 1, 1)

    def test_an_empty_series_has_nothing(self) -> None:
        facts = n3.series_facts([], "BTCUSDT", "1d", n3.IN_SAMPLE_END)
        assert (facts.bars, facts.slots, facts.missing, facts.gap_runs) == (0, 0, 0, 0)

    def test_a_missing_last_bar_counts_as_a_missing_slot(self, tmp_path: Path) -> None:
        root = tmp_path / "s"
        jan = datetime(2023, 1, 1, tzinfo=UTC)
        write_series(root, "BTCUSDT", "1d", rows_of(jan, "1d", daily_bars()[:30]))
        found = list(
            HistoricalStore(root).candles("BTCUSDT", "1d", jan, datetime(2023, 1, 31, tzinfo=UTC))
        )
        facts = n3.series_facts(found, "BTCUSDT", "1d", datetime(2023, 2, 2, tzinfo=UTC))
        assert (facts.bars, facts.slots, facts.missing, facts.gap_runs) == (30, 32, 2, 0)


class TestWhatIsPrinted:
    def test_counts_only_no_price_no_time_and_no_return(self, printed: str) -> None:
        assert re.search(r"\d+\.\d+", printed) is None, "a decimal number was printed"
        assert re.search(r"\d\d:\d\d", printed) is None, "a time of day was printed"
        assert "%" not in printed

    def test_it_says_the_counts_are_upper_bounds_on_trades(self, printed: str) -> None:
        assert "UPPER BOUND" in printed

    def test_it_is_reproducible(self, store: Path, printed: str) -> None:
        assert report(store) == (0, printed)

    def test_a_volume_that_differs_changes_nothing(self, tmp_path: Path, printed: str) -> None:
        root = tmp_path / "v"
        build_store(root, btc_volumes=[(i * 7919) % 100_003 for i in range(365)])
        assert report(root) == (0, printed)


class TestTheWindow:
    @pytest.mark.parametrize(
        "args",
        [
            ["--start", "2017-08-16"],
            ["--end", "2024-01-02"],
            ["--start", "2024-01-01", "--end", "2024-01-02"],
            ["--start", "2023-06-01", "--end", "2023-06-01"],
            ["--start", "2023-06-02", "--end", "2023-06-01"],
        ],
    )
    def test_a_window_outside_the_committed_one_is_refused_before_the_store_is_opened(
        self, tmp_path: Path, args: list[str], capsys: pytest.CaptureFixture[str]
    ) -> None:
        missing = tmp_path / "does-not-exist"
        code, text = report(missing, *args)
        assert (code, text) == (2, "")
        assert "refused" in capsys.readouterr().err
        assert not missing.exists()

    def test_the_window_may_narrow(self, store: Path, printed: str) -> None:
        code, text = report(store, "--end", "2023-12-31")
        assert code == 0
        assert series(text)[("BTCUSDT", "1d")] == (364, 364, 0, 0)
        assert table(text)[("C1", "BTCUSDT")] == table(printed)[("C1", "BTCUSDT")]

    def test_check_window_needs_timezone_aware_bounds(self) -> None:
        with pytest.raises(ValueError, match="timezone-aware"):
            n3.check_window(datetime(2020, 1, 1), n3.IN_SAMPLE_END)

    def test_load_series_refuses_a_window_past_the_boundary(self, store: Path) -> None:
        with pytest.raises(ValueError, match="R-DT"):
            n3.load_series(
                HistoricalStore(store),
                "BTCUSDT",
                "1d",
                n3.IN_SAMPLE_START,
                datetime(2024, 1, 2, tzinfo=UTC),
            )

    def test_a_month_at_or_after_the_boundary_is_never_opened(self, tmp_path: Path) -> None:
        root = tmp_path / "b"
        build_store(root)
        late = datetime(2024, 1, 1, tzinfo=UTC)
        write_series(root, "BTCUSDT", "1d", rows_of(late, "1d", [(500, 501, 499, 500)] * 31))
        month_file(root, "BTCUSDT", "1d", "2024-01").write_bytes(b"not a month file\n")
        code, text = report(root)
        assert code == 0
        assert series(text)[("BTCUSDT", "1d")] == (365, 365, 0, 0)


class TestWhenTheStoreCannotBeRead:
    def test_an_absent_store_is_exit_one(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        code, text = report(tmp_path / "nothing")
        assert (code, text) == (1, "")
        assert "unreadable" in capsys.readouterr().err

    def test_a_month_that_no_longer_matches_its_manifest_is_exit_one(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        root = tmp_path / "c"
        build_store(root)
        path = month_file(root, "BTCUSDT", "1d", "2023-03")
        path.write_bytes(path.read_bytes() + b"1,2,3\n")
        code, text = report(root)
        assert (code, text) == (1, "")
        assert "unreadable" in capsys.readouterr().err


def prefix_events(candles: Sequence[Candle], name: str, *, enforce_gaps: bool) -> int:
    """Entry events when the strategy is handed the WHOLE prefix at every bar, nothing trimmed."""
    strategy = n3._strategy(name, enforce_gaps=enforce_gaps)
    frame = n3._build_frame(candles)
    found = 0
    for i in range(len(candles)):
        signal = strategy.generate_signal(
            candles[i].symbol, frame.iloc[: i + 1], last_candle=candles[i]
        )
        found += signal is not None
    return found


class TestTrimmingTheViewChangesNothing:
    """A non-recursive candidate is handed its trailing rows only; the count must not depend on it."""

    @pytest.mark.parametrize(("label", "name", "timeframe"), n3.CANDIDATES)
    @pytest.mark.parametrize("symbol", n3.PAIRS)
    def test_the_counts_equal_those_of_the_whole_prefix(
        self, store: Path, label: str, name: str, timeframe: str, symbol: str
    ) -> None:
        candles = n3.load_series(
            HistoricalStore(store), symbol, timeframe, n3.IN_SAMPLE_START, n3.IN_SAMPLE_END
        )
        counted = n3.count_entries(candles, label, name, symbol, timeframe)
        assert counted.gated == prefix_events(candles, name, enforce_gaps=True)
        assert counted.ungated == prefix_events(candles, name, enforce_gaps=False)


class TestTheScriptIsReadOnlyAndOffline:
    def test_it_reads_through_the_store_and_has_no_fetcher(self) -> None:
        source = Path(n3.__file__).read_text(encoding="utf-8")
        for word in ("aiohttp", "requests", "AsyncClient", "BinanceClient", "urlopen", "download"):
            assert word not in source, word

    def test_it_opens_nothing_for_writing(self) -> None:
        source = Path(n3.__file__).read_text(encoding="utf-8")
        assert not re.search(r"open\([^)]*['\"][wax]", source)
        assert ".write_text(" not in source
        assert ".write_bytes(" not in source

    def test_the_candidates_are_the_six_in_r_dys_order(self) -> None:
        assert [name for _, name, _ in n3.CANDIDATES] == [
            "donchian_1d_20",
            "donchian_1d_55",
            "sma_cross_1d_50_200",
            "donchian_4h_20",
            "keltner_4h_20_2",
            "tsmom_1d_90",
        ]
        assert [label for label, _, _ in n3.CANDIDATES] == ["C1", "C2", "C3", "C4", "C5", "C6"]

    def test_the_window_constants_are_the_committed_ones(self) -> None:
        assert datetime(2017, 8, 17, tzinfo=UTC) == n3.IN_SAMPLE_START
        assert datetime(2024, 1, 1, tzinfo=UTC) == n3.IN_SAMPLE_END
