"""The recorder script: its exit statuses, its keyless construction, its fetcher and its scheduler definition.

The library's behaviour is ``test_kline_recorder.py``'s. This file proves what the script adds: the
status each refusal returns (the scheduler's ``LastTaskResult``), that it makes no request under
``--verify-only``, that nothing in it can reach an account, and that the Task Scheduler definition says
what the owner's ruling requires.
"""

from __future__ import annotations

import ast
import hashlib
import io
import json
import sys
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path
from typing import ClassVar
from urllib.parse import parse_qs, urlparse

import pytest

SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import record_testnet_klines as script  # noqa: E402

from trading_bot.data.historical import INTERVAL_MS, HistoricalStore  # noqa: E402
from trading_bot.data.kline_recorder import (  # noqa: E402
    RECORDER_LOG_NAME,
    RecorderFetchError,
)
from trading_bot.utils.instance_lock import acquire  # noqa: E402

UTC = timezone.utc
NOW = datetime(2026, 10, 9, 12, 0, tzinfo=UTC)
T0 = int(datetime(2026, 10, 7, 10, 30, tzinfo=UTC).timestamp() * 1000)
SERIES = [("BTCUSDT", "1m"), ("BTCUSDT", "5m"), ("ETHUSDT", "1m"), ("ETHUSDT", "5m")]


def kline(open_ms: int, interval_ms: int, price: str = "100") -> list[object]:
    return [
        open_ms,
        f"{price}.00000000",
        f"{int(price) + 1}.00000000",
        f"{int(price) - 1}.00000000",
        f"{price}.00000000",
        "1.00000000",
        open_ms + interval_ms - 1,
        "1.0",
        1,
        "1.0",
        "1.0",
        "0",
    ]


class Venue:
    def __init__(self, count: int = 12, price: str = "100") -> None:
        self.server_ms = T0 + 10_000 * 60_000
        self.series = {
            (symbol, interval): [
                kline(T0 + i * INTERVAL_MS[interval], INTERVAL_MS[interval], price)
                for i in range(count)
            ]
            for symbol, interval in SERIES
        }
        self.calls: list[str] = []
        self.break_on: str | None = None
        self.malformed_price = False

    def __call__(self, url: str) -> bytes:
        self.calls.append(url)
        if self.break_on is not None and self.break_on in url:
            raise RecorderFetchError("the venue did not answer")
        parsed = urlparse(url)
        if parsed.path.endswith("/time"):
            return json.dumps({"serverTime": self.server_ms}).encode()
        query = parse_qs(parsed.query)
        key = (query["symbol"][0], query["interval"][0])
        start, limit = int(query["startTime"][0]), int(query["limit"][0])
        rows = [r for r in self.series[key] if r[0] >= start][:limit]  # type: ignore[operator]
        if self.malformed_price and rows:
            rows[0] = list(rows[0])
            rows[0][3] = "500.00000000"  # a low above the open
        return json.dumps(rows).encode()


def go(root: Path, venue: Venue | None, *flags: str) -> tuple[int, str]:
    out = io.StringIO()
    fetcher = venue if venue is not None else _no_network
    code = script.run(["--root", str(root), *flags], out=out, fetcher=fetcher, clock=lambda: NOW)
    return code, out.getvalue()


def _no_network(url: str) -> bytes:
    raise AssertionError(f"a request was made: {url}")


def tree(root: Path) -> dict[str, str]:
    return {
        p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted(root.rglob("*"))
        if p.is_file() and p.name != script.LOCK_NAME
    }


class TestTheStatuses:
    def test_a_first_run_stores_all_four_series_and_exits_zero(self, tmp_path: Path) -> None:
        code, text = go(tmp_path, Venue())
        assert code == 0
        lines = [line for line in text.splitlines() if line]
        assert len(lines) == 4
        assert lines[0].startswith("BTCUSDT 1m: +12 bar(s) 2026-10-07T10:30Z..2026-10-07T10:41Z")
        for symbol, interval in SERIES:
            assert HistoricalStore(tmp_path).verify(symbol, interval) == ()
            assert (tmp_path / symbol / interval / RECORDER_LOG_NAME).is_file()

    def test_a_second_run_with_nothing_new_exits_zero_and_adds_no_bar(self, tmp_path: Path) -> None:
        go(tmp_path, Venue())
        code, text = go(tmp_path, Venue())
        assert code == 0
        assert text.count("+0 bar(s)") == 4

    def test_a_reset_exits_two_and_writes_nothing(self, tmp_path: Path) -> None:
        go(tmp_path, Venue())
        before = tree(tmp_path)
        code, text = go(tmp_path, Venue(count=20, price="900"))
        assert code == 2
        assert text.startswith("REFUSED, NOTHING WRITTEN:")
        assert tree(tmp_path) == before

    def test_a_bar_no_class_covers_exits_three_and_writes_nothing(self, tmp_path: Path) -> None:
        venue = Venue()
        venue.malformed_price = True
        code, text = go(tmp_path, venue)
        assert code == 3 and "REFUSED, NOTHING WRITTEN" in text
        assert tree(tmp_path) == {}

    def test_a_store_that_does_not_verify_exits_four(self, tmp_path: Path) -> None:
        go(tmp_path, Venue())
        month = tmp_path / "BTCUSDT" / "1m" / "BTCUSDT-1m-2026-10.csv"
        month.write_bytes(month.read_bytes().replace(b"100.00000000", b"101.00000000", 1))
        before = tree(tmp_path)
        code, text = go(tmp_path, Venue(count=20))
        assert code == 4 and text.startswith("REFUSED:")
        assert tree(tmp_path) == before

    def test_a_failed_request_exits_one(self, tmp_path: Path) -> None:
        venue = Venue()
        venue.break_on = "/klines"
        code, text = go(tmp_path, venue)
        assert code == 1 and text.startswith("FAILED: RecorderFetchError")

    def test_a_second_recorder_is_refused_with_five(self, tmp_path: Path) -> None:
        with acquire(tmp_path / script.LOCK_NAME):
            code, text = go(tmp_path, Venue())
        assert code == 5 and "another recorder holds" in text
        assert not any(p.name != script.LOCK_NAME for p in tmp_path.rglob("*") if p.is_file())

    def test_a_usage_error_exits_sixty_four_and_never_two(self, tmp_path: Path) -> None:
        code, text = go(tmp_path, None, "--symbols", "btcusdt")
        assert code == 64 and "usage error" in text
        code, text = go(tmp_path, None, "--intervals", "2m")
        assert code == 64
        with pytest.raises(SystemExit) as raised:
            script.run(["--no-such-flag"], out=io.StringIO())
        assert raised.value.code == 64


class TestVerifyOnly:
    def test_it_makes_no_request_and_reports_the_store(self, tmp_path: Path) -> None:
        go(tmp_path, Venue())
        code, text = go(tmp_path, None, "--verify-only")
        assert code == 0
        lines = [line for line in text.splitlines() if line]
        assert len(lines) == 4 and "12 bar(s) in 1 month(s)" in lines[0]
        assert "0 problem(s)" in lines[0] and "0 gap(s)" in lines[0]

    def test_it_exits_four_and_names_a_problem(self, tmp_path: Path) -> None:
        go(tmp_path, Venue())
        (tmp_path / "ETHUSDT" / "5m" / "ETHUSDT-5m-2026-10.csv").unlink()
        code, text = go(tmp_path, None, "--verify-only")
        assert code == 4 and "PROBLEM missing_file" in text

    def test_an_empty_root_verifies_with_nothing_in_it(self, tmp_path: Path) -> None:
        code, text = go(tmp_path / "none", None, "--verify-only")
        assert code == 0 and text.count("0 bar(s)") == 4


class TestKeylessByConstruction:
    def test_the_script_imports_no_settings_exchange_or_secret(self) -> None:
        tree_ = ast.parse((SCRIPTS / "record_testnet_klines.py").read_text(encoding="utf-8"))
        imported = []
        for node in ast.walk(tree_):
            if isinstance(node, ast.ImportFrom) and node.module:
                imported.append(node.module)
            elif isinstance(node, ast.Import):
                imported.extend(alias.name for alias in node.names)
        assert imported, "the script imports nothing at all: the test is blind"
        for name in imported:
            assert not name.startswith("trading_bot.config"), name
            assert not name.startswith("trading_bot.exchange"), name
            assert name != "dotenv", name
        source = (SCRIPTS / "record_testnet_klines.py").read_text(encoding="utf-8")
        code_lines = [ln for ln in source.splitlines() if not ln.lstrip().startswith(("#", '"""'))]
        body = "\n".join(code_lines)
        assert "get_settings" not in body and "Secrets(" not in body and "api_secret" not in body

    def test_the_defaults_are_the_testnet_store_and_both_pairs_at_both_timeframes(self) -> None:
        assert script.DEFAULT_ROOT == "data/historical_testnet"
        assert script.DEFAULT_SYMBOLS == ("BTCUSDT", "ETHUSDT")
        assert script.DEFAULT_INTERVALS == ("1m", "5m")


class TestTheFetcher:
    class Body:
        def __init__(self, data: bytes) -> None:
            self.data = data

        def read(self, size: int = -1, /) -> bytes:
            return self.data if size < 0 else self.data[:size]

        def __enter__(self) -> TestTheFetcher.Body:
            return self

        def __exit__(self, *exc: object) -> None:
            return None

    URL = "https://testnet.binance.vision/api/v3/time"

    def test_only_the_testnet_api_is_fetched(self) -> None:
        def opener(request: urllib.request.Request, timeout: float) -> TestTheFetcher.Body:
            return self.Body(b"{}")

        assert script.fetch_url(self.URL, opener=opener) == b"{}"
        for url in (
            "https://api.binance.com/api/v3/time",
            "https://testnet.binance.vision.evil.example/api/v3/time",
            "https://testnet.binance.vision/sapi/v1/x",
            "http://testnet.binance.vision/api/v3/time",
        ):
            with pytest.raises(RecorderFetchError, match="refusing"):
                script.fetch_url(url, opener=opener)

    def test_a_server_error_or_a_transport_fault_is_transient_and_a_client_error_is_not(
        self,
    ) -> None:
        def raising(error: BaseException):  # type: ignore[no-untyped-def]
            def opener(request: urllib.request.Request, timeout: float) -> TestTheFetcher.Body:
                raise error

            return opener

        def http(code: int) -> urllib.error.HTTPError:
            return urllib.error.HTTPError(self.URL, code, "x", {}, None)  # type: ignore[arg-type]

        with pytest.raises(script.TransientFetchError):
            script.fetch_url(self.URL, opener=raising(http(503)))
        with pytest.raises(script.TransientFetchError):
            script.fetch_url(self.URL, opener=raising(urllib.error.URLError("down")))
        with pytest.raises(script.TransientFetchError):
            script.fetch_url(self.URL, opener=raising(TimeoutError()))
        for code in (400, 418, 429):
            with pytest.raises(RecorderFetchError) as raised:
                script.fetch_url(self.URL, opener=raising(http(code)))
            assert not isinstance(raised.value, script.TransientFetchError)

    def test_a_body_past_the_cap_is_refused(self) -> None:
        def opener(request: urllib.request.Request, timeout: float) -> TestTheFetcher.Body:
            return self.Body(b"x" * (script._MAX_BYTES + 1))

        with pytest.raises(RecorderFetchError, match="more than"):
            script.fetch_url(self.URL, opener=opener)

    def test_retries_wait_one_then_two_seconds_and_stop_at_three_attempts(self) -> None:
        waits: list[float] = []
        attempts: list[int] = []

        def flaky(url: str) -> bytes:
            attempts.append(1)
            if len(attempts) < 3:
                raise script.TransientFetchError("down")
            return b"ok"

        assert script.with_retries(flaky, sleep=waits.append)(self.URL) == b"ok"
        assert waits == [1.0, 2.0] and len(attempts) == 3

        def dead(url: str) -> bytes:
            raise script.TransientFetchError("down")

        with pytest.raises(script.TransientFetchError):
            script.with_retries(dead, sleep=waits.append)(self.URL)

    def test_a_client_error_is_not_retried(self) -> None:
        calls: list[int] = []

        def refused(url: str) -> bytes:
            calls.append(1)
            raise RecorderFetchError("HTTP 429")

        with pytest.raises(RecorderFetchError):
            script.with_retries(refused, sleep=lambda s: None)(self.URL)
        assert len(calls) == 1


class TestTheOutputStream:
    def test_stdout_is_resolved_when_the_script_runs_not_when_it_is_imported(
        self, capsys: pytest.CaptureFixture[str], tmp_path: Path
    ) -> None:
        code = script.run(["--root", str(tmp_path), "--verify-only"])
        assert code == 0
        assert "BTCUSDT 1m: 0 bar(s)" in capsys.readouterr().out


class TestTheSchedulerDefinition:
    NS: ClassVar[dict[str, str]] = {"t": "http://schemas.microsoft.com/windows/2004/02/mit/task"}

    def task(self) -> ET.Element:
        return ET.parse(SCRIPTS / "recorder_task.xml").getroot()

    def text(self, path: str) -> str:
        found = self.task().find(path, self.NS)
        assert found is not None and found.text is not None, path
        return found.text

    def test_it_runs_at_start_up_and_every_six_hours(self) -> None:
        assert self.task().find("t:Triggers/t:BootTrigger", self.NS) is not None
        assert self.text("t:Triggers/t:TimeTrigger/t:Repetition/t:Interval") == "PT6H"
        assert self.text("t:Triggers/t:TimeTrigger/t:Repetition/t:StopAtDurationEnd") == "false"

    def test_a_missed_run_is_made_up_and_two_never_overlap(self) -> None:
        assert self.text("t:Settings/t:StartWhenAvailable") == "true"
        assert self.text("t:Settings/t:MultipleInstancesPolicy") == "IgnoreNew"
        assert self.text("t:Settings/t:ExecutionTimeLimit") == "PT30M"
        assert self.text("t:Settings/t:RunOnlyIfNetworkAvailable") == "true"
        assert self.text("t:Settings/t:DisallowStartIfOnBatteries") == "false"
        assert self.text("t:Settings/t:RestartOnFailure/t:Count") == "3"

    def test_it_runs_whether_or_not_the_user_is_logged_on_without_a_stored_password(self) -> None:
        assert self.text("t:Principals/t:Principal/t:LogonType") == "S4U"
        assert self.text("t:Principals/t:Principal/t:RunLevel") == "LeastPrivilege"

    def test_it_runs_the_clones_own_interpreter_on_this_script_with_the_placeholders_intact(
        self,
    ) -> None:
        assert self.text("t:Actions/t:Exec/t:Command") == "@CLONE@\\.venv\\Scripts\\python.exe"
        assert self.text("t:Actions/t:Exec/t:Arguments") == (
            "scripts\\record_testnet_klines.py --root @ROOT@"
        )
        assert self.text("t:Actions/t:Exec/t:WorkingDirectory") == "@CLONE@"
        assert self.text("t:Principals/t:Principal/t:UserId") == "@USER@"

    def test_no_secret_and_no_env_file_is_named_in_it(self) -> None:
        raw = (SCRIPTS / "recorder_task.xml").read_text(encoding="utf-8")
        body = raw[raw.index("<Task") :]
        for word in (".env", "API_KEY", "SECRET", "password", "Password"):
            assert word not in body
        assert raw.isascii()
