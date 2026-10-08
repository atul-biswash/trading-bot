"""The replay harness: stored bars through the unchanged live provider and engine.

Every store here is built through the real ``ingest_zip`` from a hand-written archive, so a
"quarantined span" is a stretch whose off-grid row the importer really set aside, and a
"registered short bar" is a row the importer really stored and registered. Prices are constant
inside a bar and rise by one per hour; the hours are counted from the first of the month.

The strategy is a stub that answers ``BUY`` on every bar with a warm-up of 3, so the engine's
gap guard is the only thing deciding which bars reach the signal handler.
"""

from __future__ import annotations

import hashlib
import io
import logging
import zipfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pandas as pd
import pytest

from trading_bot.backtesting.replay import (
    ReplayClient,
    ReplayError,
    ReplayStream,
    ReplayUnsupportedError,
)
from trading_bot.core.enums import SignalAction
from trading_bot.core.interfaces import Strategy
from trading_bot.core.models import Candle, Signal
from trading_bot.data.historical import (
    GapKind,
    HistoricalStore,
    RegistryKind,
    RowShape,
    ingest_zip,
    month_bounds_ms,
)
from trading_bot.data.market_data import BufferedMarketDataProvider
from trading_bot.engine.live_engine import TradingEngine

SYMBOL = "BTCUSDT"
HOUR = 3_600_000
MONTH = "2024-03"
START_MS, END_MS = month_bounds_ms(MONTH)
EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)
WARMUP = 3


def at(hour: float) -> datetime:
    """The instant ``hour`` hours after the first of the month, UTC."""
    return EPOCH + timedelta(milliseconds=START_MS + int(hour * HOUR))


MONTH_END = EPOCH + timedelta(milliseconds=END_MS)


def line(open_ms: int, close_ms: int, price: int) -> str:
    return (
        f"{open_ms},{price}.00000000,{price + 1}.00000000,{price - 1}.00000000,"
        f"{price}.00000000,1.00000000,{close_ms},100.00000000,1,0.50000000,50.00000000,0"
    )


def hour_line(hour: int) -> str:
    opened = START_MS + hour * HOUR
    return line(opened, opened + HOUR - 1, 100 + hour)


def store_month(
    root: Path, lines: list[str], *, symbol: str = SYMBOL, interval: str = "1h", month: str = MONTH
) -> HistoricalStore:
    data = io.BytesIO()
    with zipfile.ZipFile(data, "w") as archive:
        archive.writestr(f"{symbol}-{interval}-{month}.csv", "\n".join(lines) + "\n")
    raw = data.getvalue()
    ingest_zip(
        raw,
        expected_sha256=hashlib.sha256(raw).hexdigest(),
        root=root,
        symbol=symbol,
        interval=interval,
        month=month,
        source_url=f"https://example.invalid/{symbol}-{interval}-{month}.zip",
    )
    return HistoricalStore(root)


def hours(*wanted: int) -> list[str]:
    return [hour_line(h) for h in wanted]


class AlwaysBuy(Strategy):
    """A strategy with an opinion on every bar, so only the engine's guard silences it."""

    name = "always_buy"

    @property
    def warmup_period(self) -> int:
        return WARMUP

    def generate_signal(
        self, symbol: str, candles: pd.DataFrame, *, last_candle: Candle
    ) -> Signal | None:
        return Signal(
            symbol=symbol,
            action=SignalAction.BUY,
            timestamp=last_candle.close_time,
            price=last_candle.close,
            reason="test",
        )


class Run:
    """One replay through the real provider and engine."""

    def __init__(self) -> None:
        self.signal_hours: list[int] = []
        self.nows: dict[int, datetime] = {}
        self.delivered = 0


async def replay(
    store: HistoricalStore,
    *,
    start: datetime,
    end: datetime,
    seed_limit: int = 5,
    buffer: int = 50,
) -> tuple[Run, BufferedMarketDataProvider, ReplayStream]:
    run = Run()
    client = ReplayClient(store, start)
    stream = ReplayStream(store)
    provider = BufferedMarketDataProvider(
        client, stream, history_limit=seed_limit, buffer_size=buffer
    )
    provider.track(SYMBOL, "1h")
    engine = TradingEngine(provider, {(SYMBOL, "1h"): AlwaysBuy()}, history_limit=seed_limit)

    async def collect(signal: Signal, candle: Candle) -> None:
        hour = int((candle.open_time - at(0)) / timedelta(hours=1))
        run.signal_hours.append(hour)
        run.nows[hour] = stream.now()

    engine.on_signal(collect)
    await engine.start()
    run.delivered = await stream.pump(start, end)
    await engine.stop()
    return run, provider, stream


def events(caplog: pytest.LogCaptureFixture, name: str) -> list[logging.LogRecord]:
    return [r for r in caplog.records if vars(r).get("event") == name]


# 10 hours, a hole of four (hours 10 to 13), then 16 hours: hours 0-9 and 14-29 are present.
HOLE = [*hours(*range(10)), *hours(*range(14, 30))]
# The same hole, with one row inside it that opens 20.5 s after hour 11: off the grid, so the
# importer quarantines it. Ascending open times are kept, so it sits between hours 9 and 14.
QUARANTINED = [
    *hours(*range(10)),
    line(START_MS + 11 * HOUR + 20_500, START_MS + 11 * HOUR + 79_500, 111),
    *hours(*range(14, 30)),
]
# Hours 0-9 with hour 5 closing half an hour early: a registered short bar.
SHORT = [
    *hours(*range(5)),
    line(START_MS + 5 * HOUR, START_MS + 5 * HOUR + 1_800_000, 105),
    *hours(*range(6, 10)),
]


class TestTheGapGuardFiresAcrossAnOmittedGap:
    async def test_buys_are_refused_until_the_window_is_clear(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        store = store_month(tmp_path, HOLE)
        with caplog.at_level(logging.INFO):
            run, provider, _ = await replay(store, start=at(0), end=MONTH_END)
        # Bars 0 and 1 are warming up; 2 to 9 are clean; 14 and 15 follow the hole with 1 and 2
        # consecutive bars since it, fewer than the warm-up of 3; 16 onward are clean again.
        assert run.delivered == 26
        assert run.signal_hours == [*range(2, 10), *range(16, 30)]
        refused = events(caplog, "buy_refused_bars_gap")
        assert [vars(r).get("bars_since_gap") for r in refused] == [1, 2]
        assert provider.bars_since_gap(SYMBOL, "1h") == 16  # bars 14 to 29, counting from 1

    async def test_the_provider_records_the_gap_once_with_its_size(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        store = store_month(tmp_path, HOLE)
        with caplog.at_level(logging.WARNING):
            await replay(store, start=at(0), end=MONTH_END)
        recorded = events(caplog, "bars_gap_detected")
        assert len(recorded) == 1
        assert vars(recorded[0]).get("missing_bars") == 4

    async def test_the_store_calls_that_gap_omitted(self, tmp_path: Path) -> None:
        coverage = store_month(tmp_path, HOLE).coverage(SYMBOL, "1h")
        assert [(g.kind, g.missing) for g in coverage.kinded_gaps] == [(GapKind.OMITTED, 4)]


class TestTheGapGuardFiresAcrossAQuarantinedSpan:
    async def test_the_guard_does_not_know_why_a_bar_is_missing(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        store = store_month(tmp_path, QUARANTINED)
        with caplog.at_level(logging.INFO):
            run, provider, _ = await replay(store, start=at(0), end=MONTH_END)
        assert run.delivered == 26
        assert run.signal_hours == [*range(2, 10), *range(16, 30)]
        assert [vars(r).get("bars_since_gap") for r in events(caplog, "buy_refused_bars_gap")] == [
            1,
            2,
        ]
        recorded = events(caplog, "bars_gap_detected")
        assert len(recorded) == 1
        assert vars(recorded[0]).get("missing_bars") == 4
        assert provider.bars_since_gap(SYMBOL, "1h") == 16

    async def test_the_store_calls_that_span_quarantined_where_its_row_opened(
        self, tmp_path: Path
    ) -> None:
        """Hour 11's slot holds the set-aside row, so the four missing hours split into an
        omitted hour, a quarantined hour and two omitted hours. The replay above refuses the
        same bars either way."""
        store = store_month(tmp_path, QUARANTINED)
        coverage = store.coverage(SYMBOL, "1h")
        assert [(g.kind, g.missing) for g in coverage.kinded_gaps] == [
            (GapKind.OMITTED, 1),
            (GapKind.QUARANTINED, 1),
            (GapKind.OMITTED, 2),
        ]
        assert coverage.quarantined_rows == 1

    async def test_the_quarantined_row_is_never_delivered(self, tmp_path: Path) -> None:
        store = store_month(tmp_path, QUARANTINED)
        seen: list[datetime] = []
        stream = ReplayStream(store)

        async def handler(candle: Candle) -> None:
            seen.append(candle.open_time)

        stream.subscribe(SYMBOL, "1h", handler)
        assert await stream.pump(at(0), MONTH_END) == 26
        assert at(11) not in seen
        assert all(opened.minute == 0 and opened.second == 0 for opened in seen)


class TestARegisteredShortBarIsAnOrdinaryBar:
    async def test_it_causes_no_gap_and_gets_its_signal(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        store = store_month(tmp_path, SHORT)
        with caplog.at_level(logging.INFO):
            run, provider, _ = await replay(store, start=at(0), end=MONTH_END)
        assert run.delivered == 10
        assert run.signal_hours == list(range(2, 10))  # including hour 5
        assert events(caplog, "bars_gap_detected") == []
        assert events(caplog, "buy_refused_bars_gap") == []
        assert provider.bars_since_gap(SYMBOL, "1h") is None

    async def test_the_store_registered_it_and_stored_it_with_the_archives_close(
        self, tmp_path: Path
    ) -> None:
        store = store_month(tmp_path, SHORT)
        (entry,) = store.registry(SYMBOL, "1h")
        assert entry.kind is RegistryKind.REGISTERED
        assert entry.shape is RowShape.SHORT_BAR
        assert entry.open_time_ms == START_MS + 5 * HOUR
        bars = {c.open_time: c for c in store.candles(SYMBOL, "1h", at(0), MONTH_END)}
        assert bars[at(5)].close_time == at(5.5)  # the archive's close, half an hour in

    async def test_the_simulated_instant_follows_the_slot_not_the_archives_close(
        self, tmp_path: Path
    ) -> None:
        """Hour 5's archived close is at 05:30, and a clock that followed it would then step
        to 06:00 for hour 5's successor a half hour late. The instant is open time plus
        timeframe: 06:00 for hour 5, and 05:00 and 07:00 around it."""
        store = store_month(tmp_path, SHORT)
        run, _, _ = await replay(store, start=at(0), end=MONTH_END)
        assert run.nows[4] == at(5)
        assert run.nows[5] == at(6)
        assert run.nows[6] == at(7)


class TestAppendPrecedesNotify:
    async def test_a_subscriber_finds_the_candle_already_in_the_buffer(
        self, tmp_path: Path
    ) -> None:
        store = store_month(tmp_path, hours(*range(6)))
        client = ReplayClient(store, at(0))
        stream = ReplayStream(store)
        provider = BufferedMarketDataProvider(client, stream, history_limit=5, buffer_size=50)
        provider.track(SYMBOL, "1h")
        seen: list[tuple[bool, int, datetime]] = []

        async def observer(candle: Candle) -> None:
            last = provider.last_candle(SYMBOL, "1h")
            frame = provider.get_dataframe(SYMBOL, "1h")
            seen.append((last is candle, provider.candle_count(SYMBOL, "1h"), frame.index[-1]))

        provider.on_candle(observer)
        await provider.start()
        await stream.pump(at(0), MONTH_END)
        await provider.stop()
        assert [s[0] for s in seen] == [True] * 6
        assert [s[1] for s in seen] == [1, 2, 3, 4, 5, 6]
        assert [s[2] for s in seen] == [at(h) for h in range(6)]

    async def test_subscribers_run_in_registration_order_on_each_bar(self, tmp_path: Path) -> None:
        store = store_month(tmp_path, hours(0, 1, 2))
        stream = ReplayStream(store)
        provider = BufferedMarketDataProvider(
            ReplayClient(store, at(0)), stream, history_limit=5, buffer_size=50
        )
        provider.track(SYMBOL, "1h")
        order: list[str] = []

        def tagged(tag: str) -> Any:
            async def handler(candle: Candle) -> None:
                order.append(f"{tag}{int((candle.open_time - at(0)) / timedelta(hours=1))}")

            return handler

        provider.on_candle(tagged("a"))
        provider.on_candle(tagged("b"))
        await provider.start()
        await stream.pump(at(0), MONTH_END)
        assert order == ["a0", "b0", "a1", "b1", "a2", "b2"]

    async def test_the_instant_is_set_before_the_handlers_run(self, tmp_path: Path) -> None:
        store = store_month(tmp_path, hours(0, 1))
        stream = ReplayStream(store)
        seen: list[datetime] = []

        async def handler(candle: Candle) -> None:
            seen.append(stream.now())

        stream.subscribe(SYMBOL, "1h", handler)
        await stream.pump(at(0), MONTH_END)
        assert seen == [at(1), at(2)]


class TestTheSeedClient:
    async def test_it_returns_the_last_bars_before_the_window_oldest_first(
        self, tmp_path: Path
    ) -> None:
        store = store_month(tmp_path, hours(*range(30)))
        seed = await ReplayClient(store, at(20)).get_klines(SYMBOL, "1h", limit=5)
        assert [c.open_time for c in seed] == [at(h) for h in (15, 16, 17, 18, 19)]
        assert all(c.is_closed for c in seed)
        assert {(c.symbol, c.timeframe) for c in seed} == {(SYMBOL, "1h")}

    async def test_the_bar_that_opens_at_the_window_start_is_not_in_the_seed(
        self, tmp_path: Path
    ) -> None:
        store = store_month(tmp_path, hours(*range(30)))
        seed = await ReplayClient(store, at(20)).get_klines(SYMBOL, "1h", limit=500)
        assert seed[-1].open_time == at(19)
        assert len(seed) == 20

    async def test_fewer_come_back_when_the_store_holds_fewer(self, tmp_path: Path) -> None:
        store = store_month(tmp_path, hours(*range(30)))
        seed = await ReplayClient(store, at(3)).get_klines(SYMBOL, "1h", limit=10)
        assert [c.open_time for c in seed] == [at(0), at(1), at(2)]

    async def test_nothing_before_the_first_bar_is_an_empty_seed(self, tmp_path: Path) -> None:
        store = store_month(tmp_path, hours(*range(30)))
        assert await ReplayClient(store, at(0)).get_klines(SYMBOL, "1h", limit=5) == []

    async def test_a_hole_inside_the_seed_is_stepped_over_to_find_the_limit(
        self, tmp_path: Path
    ) -> None:
        """Like REST, it returns the last ``limit`` bars there are. Five bars back from hour 16
        is only hours 14 and 15 before the hole, so the search widens past it."""
        store = store_month(tmp_path, HOLE)
        seed = await ReplayClient(store, at(16)).get_klines(SYMBOL, "1h", limit=5)
        assert [c.open_time for c in seed] == [at(h) for h in (7, 8, 9, 14, 15)]

    async def test_that_hole_reaches_the_providers_gap_record(self, tmp_path: Path) -> None:
        """The seed goes through the same append gate as live bars, so its hole is a gap."""
        store = store_month(tmp_path, HOLE)
        stream = ReplayStream(store)
        provider = BufferedMarketDataProvider(
            ReplayClient(store, at(16)), stream, history_limit=5, buffer_size=50
        )
        provider.track(SYMBOL, "1h")
        await provider.start()
        assert provider.candle_count(SYMBOL, "1h") == 5
        assert provider.bars_since_gap(SYMBOL, "1h") == 2  # hours 14 and 15 follow the hole

    async def test_the_seed_ends_where_the_pump_begins(self, tmp_path: Path) -> None:
        store = store_month(tmp_path, hours(*range(30)))
        run, provider, _ = await replay(store, start=at(20), end=MONTH_END, seed_limit=5)
        assert run.delivered == 10
        # 5 seeded (hours 15 to 19) + 10 delivered: every BUY from the first delivered bar on.
        assert run.signal_hours == list(range(20, 30))
        assert provider.candle_count(SYMBOL, "1h") == 15

    async def test_a_naive_window_start_and_a_zero_limit_are_refused(self, tmp_path: Path) -> None:
        store = store_month(tmp_path, hours(0))
        with pytest.raises(ValueError, match="timezone-aware"):
            ReplayClient(store, datetime(2024, 3, 1))
        with pytest.raises(ValueError, match="at least 1"):
            await ReplayClient(store, at(0)).get_klines(SYMBOL, "1h", limit=0)

    async def test_close_is_a_no_op_and_idempotent(self, tmp_path: Path) -> None:
        client = ReplayClient(store_month(tmp_path, hours(0)), at(0))
        await client.close()
        await client.close()


class TestEveryOtherVenueCallIsRefused:
    @pytest.mark.parametrize(
        "name",
        (
            "get_balances",
            "get_symbol_info",
            "get_ticker",
            "create_order",
            "cancel_order",
            "get_open_orders",
            "get_own_open_orders",
            "get_order",
            "get_my_trades",
            "get_all_order_lists",
            "create_otoco_order_list",
            "create_oto_order_list",
            "cancel_order_list",
        ),
    )
    async def test_it_raises_and_names_the_method(self, tmp_path: Path, name: str) -> None:
        client = ReplayClient(store_month(tmp_path, hours(0)), at(0))
        call = getattr(client, name)
        # The two order-list creators take their request positionally; the rest take nothing.
        coroutine = call(None) if name.startswith("create_o") else call()
        with pytest.raises(ReplayUnsupportedError, match=name):
            await coroutine

    async def test_the_refusal_is_a_replay_error(self) -> None:
        assert issubclass(ReplayUnsupportedError, ReplayError)


class TestTheStreamKeepsTheLiveContract:
    async def test_it_refuses_to_start_with_nothing_subscribed(self, tmp_path: Path) -> None:
        stream = ReplayStream(store_month(tmp_path, hours(0)))
        with pytest.raises(ValueError, match="no subscriptions"):
            await stream.start()

    async def test_it_refuses_to_pump_with_nothing_subscribed(self, tmp_path: Path) -> None:
        stream = ReplayStream(store_month(tmp_path, hours(0)))
        with pytest.raises(ReplayError, match="nothing is subscribed"):
            await stream.pump(at(0), MONTH_END)

    async def test_it_has_no_instant_before_the_first_bar(self, tmp_path: Path) -> None:
        stream = ReplayStream(store_month(tmp_path, hours(0)))
        with pytest.raises(ReplayError, match="no bar yet"):
            stream.now()

    async def test_the_instant_stands_on_the_last_bar_after_the_replay(
        self, tmp_path: Path
    ) -> None:
        stream = ReplayStream(store_month(tmp_path, hours(0, 1, 2)))
        stream.subscribe(SYMBOL, "1h", _noop)
        await stream.pump(at(0), MONTH_END)
        assert stream.now() == at(3)

    async def test_a_symbol_is_upper_cased_for_routing(self, tmp_path: Path) -> None:
        stream = ReplayStream(store_month(tmp_path, hours(0, 1)))
        seen: list[Candle] = []

        async def handler(candle: Candle) -> None:
            seen.append(candle)

        stream.subscribe("btcusdt", "1h", handler)
        assert await stream.pump(at(0), MONTH_END) == 2
        assert len(seen) == 2

    async def test_a_timeframe_the_system_cannot_step_is_refused_on_subscribe(
        self, tmp_path: Path
    ) -> None:
        stream = ReplayStream(store_month(tmp_path, hours(0)))
        with pytest.raises(ValueError):
            stream.subscribe(SYMBOL, "7x", _noop)

    async def test_several_handlers_for_one_pair_run_in_subscription_order(
        self, tmp_path: Path
    ) -> None:
        stream = ReplayStream(store_month(tmp_path, hours(0, 1)))
        order: list[str] = []

        def tagged(tag: str) -> Any:
            async def handler(candle: Candle) -> None:
                order.append(tag)

            return handler

        stream.subscribe(SYMBOL, "1h", tagged("first"))
        stream.subscribe(SYMBOL, "1h", tagged("second"))
        await stream.pump(at(0), MONTH_END)
        assert order == ["first", "second", "first", "second"]

    async def test_the_window_is_half_open(self, tmp_path: Path) -> None:
        stream = ReplayStream(store_month(tmp_path, hours(*range(10))))
        opened: list[datetime] = []

        async def handler(candle: Candle) -> None:
            opened.append(candle.open_time)

        stream.subscribe(SYMBOL, "1h", handler)
        assert await stream.pump(at(3), at(6)) == 3
        assert opened == [at(3), at(4), at(5)]

    async def test_a_raising_handler_is_isolated_logged_and_counted(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        stream = ReplayStream(store_month(tmp_path, hours(0, 1, 2)))
        survivors: list[Candle] = []

        async def bad(candle: Candle) -> None:
            raise RuntimeError("boom")

        async def good(candle: Candle) -> None:
            survivors.append(candle)

        stream.subscribe(SYMBOL, "1h", bad)
        stream.subscribe(SYMBOL, "1h", good)
        with caplog.at_level(logging.ERROR):
            assert await stream.pump(at(0), MONTH_END) == 3
        assert len(survivors) == 3
        assert stream.failures == 3
        assert len([r for r in caplog.records if "Candle handler failed" in r.getMessage()]) == 3

    async def test_stop_from_a_handler_ends_the_pump_after_that_bar(self, tmp_path: Path) -> None:
        stream = ReplayStream(store_month(tmp_path, hours(*range(10))))
        count = 0

        async def handler(candle: Candle) -> None:
            nonlocal count
            count += 1
            if count == 3:
                await stream.stop()

        stream.subscribe(SYMBOL, "1h", handler)
        assert await stream.pump(at(0), MONTH_END) == 3
        await stream.stop()  # idempotent
        assert await stream.pump(at(0), MONTH_END) == 0


class TestBarsOfSeveralPairsAreMergedByNominalClose:
    @staticmethod
    def two_pairs(tmp_path: Path) -> HistoricalStore:
        store_month(tmp_path, hours(*range(8)), symbol="BTCUSDT")
        four_hours = [
            line(START_MS, START_MS + 4 * HOUR - 1, 200),
            line(START_MS + 4 * HOUR, START_MS + 8 * HOUR - 1, 201),
        ]
        return store_month(tmp_path, four_hours, symbol="ETHUSDT", interval="4h")

    async def test_ties_go_to_the_pair_subscribed_first(self, tmp_path: Path) -> None:
        store = self.two_pairs(tmp_path)
        stream = ReplayStream(store)
        order: list[tuple[str, int]] = []

        def recorder() -> Any:
            async def handler(candle: Candle) -> None:
                order.append((candle.symbol, int((stream.now() - at(0)) / timedelta(hours=1))))

            return handler

        stream.subscribe("BTCUSDT", "1h", recorder())
        stream.subscribe("ETHUSDT", "4h", recorder())
        assert await stream.pump(at(0), MONTH_END) == 10
        # BTCUSDT's bars close at hours 1 to 8; ETHUSDT's at 4 and 8, after BTCUSDT's on a tie.
        assert order == [
            ("BTCUSDT", 1),
            ("BTCUSDT", 2),
            ("BTCUSDT", 3),
            ("BTCUSDT", 4),
            ("ETHUSDT", 4),
            ("BTCUSDT", 5),
            ("BTCUSDT", 6),
            ("BTCUSDT", 7),
            ("BTCUSDT", 8),
            ("ETHUSDT", 8),
        ]

    async def test_reversing_the_subscription_order_reverses_the_ties_only(
        self, tmp_path: Path
    ) -> None:
        store = self.two_pairs(tmp_path)
        stream = ReplayStream(store)
        order: list[tuple[str, int]] = []

        def recorder() -> Any:
            async def handler(candle: Candle) -> None:
                order.append((candle.symbol, int((stream.now() - at(0)) / timedelta(hours=1))))

            return handler

        stream.subscribe("ETHUSDT", "4h", recorder())
        stream.subscribe("BTCUSDT", "1h", recorder())
        await stream.pump(at(0), MONTH_END)
        assert order == [
            ("BTCUSDT", 1),
            ("BTCUSDT", 2),
            ("BTCUSDT", 3),
            ("ETHUSDT", 4),
            ("BTCUSDT", 4),
            ("BTCUSDT", 5),
            ("BTCUSDT", 6),
            ("BTCUSDT", 7),
            ("ETHUSDT", 8),
            ("BTCUSDT", 8),
        ]


async def _noop(candle: Candle) -> None:
    return None
