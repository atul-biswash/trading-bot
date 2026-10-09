"""Regime labels (R-AI): calendar quarters labelled by BTCUSDT's quarterly return.

Hand figures throughout: every quarter's open and close are written into the test, so the label
each expects is arithmetic the reader can do. The thresholds are *strict* and *exact*, so the
cases that matter sit ON a threshold and one unit either side of it.
"""

from __future__ import annotations

import hashlib
import json
import random
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

import pytest

from trading_bot.backtesting.regimes import (
    FALLING_BELOW,
    RISING_ABOVE,
    SCHEMA,
    QuarterLabel,
    Regime,
    RegimeTable,
    build_document,
    classify,
    document_digest,
    label_quarters,
    quarter_bounds,
    quarter_key,
    render_document,
)
from trading_bot.core.models import Candle

D = Decimal


def bar(day: date, open_: str, close: str) -> Candle:
    opened = datetime(day.year, day.month, day.day, tzinfo=timezone.utc)
    high = str(max(D(open_), D(close)))
    low = str(min(D(open_), D(close)))
    return Candle(
        symbol="BTCUSDT",
        timeframe="1d",
        open_time=opened,
        close_time=opened + timedelta(days=1) - timedelta(milliseconds=1),
        open=D(open_),
        high=D(high),
        low=D(low),
        close=D(close),
        volume=D(1),
    )


def quarter_of_bars(
    key: str, open_first: str, close_last: str, *, skip: frozenset[date] = frozenset()
) -> list[Candle]:
    """Every day of a quarter; the first opens at ``open_first``, the last closes at ``close_last``,
    and the days between are flat at ``open_first``."""
    start, end = quarter_bounds(key)
    days = [start + timedelta(days=i) for i in range((end - start).days)]
    out = []
    for index, day in enumerate(days):
        if day in skip:
            continue
        last = index == len(days) - 1
        out.append(bar(day, open_first, close_last if last else open_first))
    return out


def only(items: list[QuarterLabel] | tuple[QuarterLabel, ...], quarter: str) -> QuarterLabel:
    found = [item for item in items if item.quarter == quarter]
    assert len(found) == 1, (quarter, [item.quarter for item in items])
    return found[0]


class TestQuarterArithmetic:
    @pytest.mark.parametrize(
        ("day", "key"),
        [
            (date(2024, 1, 1), "2024Q1"),
            (date(2024, 3, 31), "2024Q1"),
            (date(2024, 4, 1), "2024Q2"),
            (date(2024, 6, 30), "2024Q2"),
            (date(2024, 7, 1), "2024Q3"),
            (date(2024, 9, 30), "2024Q3"),
            (date(2024, 10, 1), "2024Q4"),
            (date(2024, 12, 31), "2024Q4"),
            (date(2025, 1, 1), "2025Q1"),
        ],
    )
    def test_a_date_belongs_to_the_quarter_it_falls_in(self, day: date, key: str) -> None:
        assert quarter_key(day) == key

    def test_the_bounds_are_half_open_and_the_fourth_quarter_ends_next_year(self) -> None:
        assert quarter_bounds("2024Q1") == (date(2024, 1, 1), date(2024, 4, 1))
        assert quarter_bounds("2024Q2") == (date(2024, 4, 1), date(2024, 7, 1))
        assert quarter_bounds("2024Q3") == (date(2024, 7, 1), date(2024, 10, 1))
        assert quarter_bounds("2024Q4") == (date(2024, 10, 1), date(2025, 1, 1))

    def test_a_quarter_is_as_many_days_as_the_calendar_gives_it(self) -> None:
        def days(key: str) -> int:
            start, end = quarter_bounds(key)
            return (end - start).days

        assert (days("2024Q1"), days("2023Q1")) == (91, 90)
        assert (days("2023Q2"), days("2023Q3"), days("2023Q4")) == (91, 92, 92)

    @pytest.mark.parametrize("bad", ["2024Q5", "2024Q0", "2024q1", "24Q1", "2024Q", "20241Q1", ""])
    def test_a_malformed_key_is_refused(self, bad: str) -> None:
        with pytest.raises(ValueError, match="not a quarter key"):
            quarter_bounds(bad)


class TestClassify:
    def test_the_thresholds_are_the_ruled_ones(self) -> None:
        assert (D("0.15"), D("-0.15")) == (RISING_ABOVE, FALLING_BELOW)

    def test_exactly_plus_fifteen_percent_is_sideways_and_one_unit_above_is_rising(self) -> None:
        assert classify(D("100"), D("115")) is Regime.SIDEWAYS
        assert classify(D("100"), D("115.00000001")) is Regime.RISING
        assert classify(D("100"), D("114.99999999")) is Regime.SIDEWAYS

    def test_exactly_minus_fifteen_percent_is_sideways_and_one_unit_below_is_falling(self) -> None:
        assert classify(D("100"), D("85")) is Regime.SIDEWAYS
        assert classify(D("100"), D("84.99999999")) is Regime.FALLING
        assert classify(D("100"), D("85.00000001")) is Regime.SIDEWAYS

    def test_the_bound_is_exact_for_a_price_that_is_not_round(self) -> None:
        # 42,280.10 * 1.15 = 48,622.115 exactly; a quotient rounded to six places would blur it.
        assert classify(D("42280.10"), D("48622.115")) is Regime.SIDEWAYS
        assert classify(D("42280.10"), D("48622.11500001")) is Regime.RISING
        assert classify(D("42280.10"), D("35938.085")) is Regime.SIDEWAYS
        assert classify(D("42280.10"), D("35938.08499999")) is Regime.FALLING

    def test_flat_and_ordinary_moves_are_sideways_and_big_ones_are_not(self) -> None:
        assert classify(D("100"), D("100")) is Regime.SIDEWAYS
        assert classify(D("100"), D("107")) is Regime.SIDEWAYS
        assert classify(D("100"), D("300")) is Regime.RISING
        assert classify(D("100"), D("10")) is Regime.FALLING

    @pytest.mark.parametrize("opening", [D("0"), D("-1")])
    def test_a_quarter_cannot_open_at_a_non_positive_price(self, opening: Decimal) -> None:
        with pytest.raises(ValueError, match="cannot open at"):
            classify(opening, D("1"))


class TestLabelQuarters:
    def test_a_complete_quarter_is_labelled_from_its_first_open_and_last_close(self) -> None:
        labels = label_quarters(quarter_of_bars("2024Q1", "100", "130"))
        assert len(labels) == 1, labels
        label = labels[0]
        assert label.quarter == "2024Q1"
        assert (label.start, label.end) == (date(2024, 1, 1), date(2024, 4, 1))
        assert (label.bars, label.expected_bars) == (91, 91)
        assert (label.open_first, label.close_last) == (D("100"), D("130"))
        assert label.regime is Regime.RISING
        assert label.complete is True
        assert label.quarterly_return == D("0.300000")
        assert label.note == ""

    def test_each_regime_is_reachable(self) -> None:
        bars = (
            quarter_of_bars("2024Q1", "100", "130")
            + quarter_of_bars("2024Q2", "130", "100")
            + quarter_of_bars("2024Q3", "100", "104")
        )
        labels = label_quarters(bars)
        assert [(label.quarter, label.regime) for label in labels] == [
            ("2024Q1", Regime.RISING),
            ("2024Q2", Regime.FALLING),
            ("2024Q3", Regime.SIDEWAYS),
        ]

    def test_the_first_day_of_a_quarter_belongs_to_it_and_not_to_the_one_before(self) -> None:
        """2024-04-01 opens at 110 and closes at 300. In 2024Q2 that day is the first bar, so
        Q2 returns 110 -> 120 (sideways); had it fallen in Q1 the quarter would close at 300."""
        q1 = quarter_of_bars("2024Q1", "100", "110")
        q2 = quarter_of_bars("2024Q2", "110", "120")
        q2[0] = bar(date(2024, 4, 1), "110", "300")
        labels = label_quarters(q1 + q2)
        first, second = labels
        assert (first.close_last, first.regime) == (D("110"), Regime.SIDEWAYS)
        assert (second.open_first, second.close_last) == (D("110"), D("120"))
        assert second.regime is Regime.SIDEWAYS

    def test_the_last_day_of_a_quarter_belongs_to_it_and_not_to_the_one_after(self) -> None:
        q1 = quarter_of_bars("2024Q1", "100", "100")
        q1[-1] = bar(date(2024, 3, 31), "100", "140")
        q2 = quarter_of_bars("2024Q2", "140", "140")
        first, second = label_quarters(q1 + q2)
        assert (first.bars, first.close_last, first.regime) == (91, D("140"), Regime.RISING)
        assert second.open_first == D("140")

    def test_a_missing_day_makes_the_quarter_partial_with_the_day_named(self) -> None:
        bars = quarter_of_bars("2024Q1", "100", "130", skip=frozenset({date(2024, 2, 10)}))
        labels = label_quarters(bars)
        assert len(labels) == 1, labels
        label = labels[0]
        assert label.regime is None and label.complete is False
        assert (label.bars, label.expected_bars) == (90, 91)
        assert label.note == "1 daily bar(s) missing, the first on 2024-02-10"

    def test_a_quarter_the_history_begins_inside_is_partial(self) -> None:
        bars = [
            b
            for b in quarter_of_bars("2017Q3", "100", "200")
            if b.open_time.date() >= date(2017, 8, 17)
        ]
        bars += quarter_of_bars("2017Q4", "200", "210")
        first, second = label_quarters(bars)
        assert first.quarter == "2017Q3" and first.regime is None
        assert first.note == "the stored history begins 2017-08-17, inside this quarter"
        assert second.regime is Regime.SIDEWAYS

    def test_a_quarter_the_history_ends_inside_is_partial(self) -> None:
        bars = quarter_of_bars("2024Q1", "100", "100")
        bars += [
            b
            for b in quarter_of_bars("2024Q2", "100", "100")
            if b.open_time.date() <= date(2024, 5, 20)
        ]
        first, second = label_quarters(bars)
        assert first.regime is Regime.SIDEWAYS
        assert second.regime is None
        assert second.note == "the stored history ends 2024-05-20, inside this quarter"

    def test_a_quarter_with_no_bar_at_all_is_listed_as_partial(self) -> None:
        bars = quarter_of_bars("2024Q1", "100", "100") + quarter_of_bars("2024Q3", "100", "100")
        labels = label_quarters(bars)
        assert [label.quarter for label in labels] == ["2024Q1", "2024Q2", "2024Q3"]
        empty = only(labels, "2024Q2")
        assert (empty.bars, empty.open_first, empty.close_last, empty.regime) == (
            0,
            None,
            None,
            None,
        )
        assert empty.quarterly_return is None
        assert empty.note.startswith("91 daily bar(s) missing")

    def test_the_order_of_the_input_does_not_matter(self) -> None:
        bars = quarter_of_bars("2024Q1", "100", "130") + quarter_of_bars("2024Q2", "130", "100")
        shuffled = list(bars)
        random.Random(7).shuffle(shuffled)
        assert label_quarters(shuffled) == label_quarters(bars)

    def test_two_bars_on_one_day_are_refused(self) -> None:
        bars = quarter_of_bars("2024Q1", "100", "100")
        bars.append(bar(date(2024, 1, 5), "1", "1"))
        with pytest.raises(ValueError, match="two daily bars open on 2024-01-05"):
            label_quarters(bars)

    def test_no_bars_give_no_labels(self) -> None:
        assert label_quarters([]) == ()


class TestTheDocument:
    def labels(self) -> tuple[QuarterLabel, ...]:
        partial = [
            b
            for b in quarter_of_bars("2023Q4", "100", "100")
            if b.open_time.date() >= date(2023, 11, 1)
        ]
        return label_quarters(
            partial
            + quarter_of_bars("2024Q1", "100", "130")
            + quarter_of_bars("2024Q2", "130", "100")
            + quarter_of_bars("2024Q3", "100", "104")
        )

    def document(self) -> dict[str, object]:
        return build_document(
            self.labels(), symbol="BTCUSDT", interval="1d", source={"series": "BTCUSDT 1d"}
        )

    def test_the_counts_add_up_and_name_every_regime_and_the_partial_ones(self) -> None:
        counts = self.document()["counts"]
        assert counts == {
            "rising": 1,
            "falling": 1,
            "sideways": 1,
            "partial": 1,
            "quarters": 4,
        }

    def test_every_quarter_row_carries_its_figures_as_exact_strings(self) -> None:
        rows = self.document()["quarters"]
        assert isinstance(rows, list)
        first = rows[1]
        assert first == {
            "quarter": "2024Q1",
            "start": "2024-01-01",
            "end": "2024-04-01",
            "bars": 91,
            "expected_bars": 91,
            "open_first": "100",
            "close_last": "130",
            "return": "0.300000",
            "regime": "rising",
            "note": "",
        }
        assert rows[0]["regime"] is None and rows[0]["return"] is not None

    def test_the_definitions_are_written_into_the_document(self) -> None:
        definition = self.document()["definition"]
        assert isinstance(definition, dict)
        assert definition["rising_above"] == "0.15" and definition["falling_below"] == "-0.15"
        assert "strict" in str(definition["boundaries"])
        assert self.document()["schema"] == SCHEMA

    def test_the_rendering_is_sorted_lf_and_ends_in_one_newline(self) -> None:
        rendered = render_document(self.document())
        assert rendered.endswith(b"}\n") and not rendered.endswith(b"\n\n")
        assert b"\r" not in rendered
        assert json.loads(rendered) == json.loads(json.dumps(self.document()))
        keys = [line.strip() for line in rendered.decode().splitlines() if line.startswith('  "')]
        assert keys == sorted(keys)

    def test_the_digest_is_the_sha256_of_the_rendered_bytes_and_moves_with_a_label(self) -> None:
        rendered = render_document(self.document())
        assert document_digest(rendered) == hashlib.sha256(rendered).hexdigest()
        other = build_document(
            label_quarters(quarter_of_bars("2024Q1", "100", "116")),
            symbol="BTCUSDT",
            interval="1d",
            source={"series": "BTCUSDT 1d"},
        )
        changed = build_document(
            label_quarters(quarter_of_bars("2024Q1", "100", "115")),
            symbol="BTCUSDT",
            interval="1d",
            source={"series": "BTCUSDT 1d"},
        )
        assert document_digest(render_document(other)) != document_digest(render_document(changed))


class TestTheTable:
    def table(self) -> RegimeTable:
        labels = label_quarters(
            quarter_of_bars("2024Q1", "100", "130")
            + quarter_of_bars("2024Q2", "130", "100")
            + [
                b
                for b in quarter_of_bars("2024Q3", "100", "100")
                if b.open_time.date() <= date(2024, 8, 1)
            ]
        )
        document = build_document(labels, symbol="BTCUSDT", interval="1d", source={})
        return RegimeTable.from_document(document)

    def test_a_table_built_by_hand_has_no_digest_and_one_given_keeps_it(self) -> None:
        document = {"quarters": [{"quarter": "2024Q1", "regime": "rising"}]}
        assert RegimeTable.from_document(document).digest is None
        assert RegimeTable.from_document(document, digest="abc").digest == "abc"
        assert RegimeTable({}).digest is None

    def test_a_date_reads_its_quarters_regime(self) -> None:
        table = self.table()
        assert table.regime_on(date(2024, 1, 1)) is Regime.RISING
        assert table.regime_on(date(2024, 3, 31)) is Regime.RISING
        assert table.regime_on(date(2024, 4, 1)) is Regime.FALLING
        assert table.regime_on(date(2024, 6, 30)) is Regime.FALLING

    def test_a_partial_quarter_and_a_quarter_outside_the_table_read_none_differently(self) -> None:
        table = self.table()
        assert table.regime_on(date(2024, 7, 15)) is None
        assert table.quarter_is_known(date(2024, 7, 15)) is True
        assert table.regime_on(date(2030, 1, 1)) is None
        assert table.quarter_is_known(date(2030, 1, 1)) is False

    def test_a_file_whose_digest_matches_is_read_and_one_that_does_not_is_refused(
        self, tmp_path: Path
    ) -> None:
        document = build_document(
            label_quarters(quarter_of_bars("2024Q1", "100", "130")),
            symbol="BTCUSDT",
            interval="1d",
            source={},
        )
        rendered = render_document(document)
        target = tmp_path / "labels.json"
        target.write_bytes(rendered)
        sidecar = tmp_path / "labels.json.sha256"
        with pytest.raises(ValueError, match="does not match its digest file"):
            RegimeTable.from_file(target)  # no digest file at all
        sidecar.write_text(f"{document_digest(rendered)}  labels.json\n", encoding="ascii")
        assert RegimeTable.from_file(target).regime_on(date(2024, 2, 1)) is Regime.RISING
        assert RegimeTable.from_file(target).digest == document_digest(rendered)
        target.write_bytes(rendered.replace(b"rising", b"falling"))
        with pytest.raises(ValueError, match="does not match its digest file"):
            RegimeTable.from_file(target)
