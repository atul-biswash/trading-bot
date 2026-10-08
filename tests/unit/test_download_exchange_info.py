"""``scripts/download_exchange_info.py``: one keyless GET per symbol and environment (R-Z).

No test opens a socket. A fake answers the endpoints from a table and records every URL it was
asked, so "one request" and "no request" are assertions about that record.
"""

from __future__ import annotations

import io
import json
import sys
import urllib.error
import urllib.request
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

import download_exchange_info as dl

from trading_bot.backtesting.exchange_info import (
    checksum_file,
    load_snapshot,
    snapshot_file,
)

# fmt: off
_FILTERS: list[dict[str, Any]] = [
    {"filterType": "PRICE_FILTER", "minPrice": "0.01", "maxPrice": "1000000", "tickSize": "0.01"},
    {"filterType": "LOT_SIZE", "minQty": "0.0001", "maxQty": "9000", "stepSize": "0.0001"},
    {"filterType": "NOTIONAL", "minNotional": "5"},
]
# fmt: on


def body(symbol: str, marker: int = 0) -> bytes:
    document = {
        "serverTime": 1_700_000_000_000 + marker,
        "symbols": [
            {
                "symbol": symbol,
                "baseAsset": symbol[:-4],
                "quoteAsset": "USDT",
                "filters": _FILTERS,
            }
        ],
    }
    return json.dumps(document).encode("utf-8")


class FakeVenue:
    """Answers each exchangeInfo URL and records the order of requests."""

    def __init__(self, bodies: dict[str, bytes] | None = None) -> None:
        self.bodies = bodies or {}
        self.asked: list[str] = []

    def __call__(self, url: str) -> bytes:
        self.asked.append(url)
        if url in self.bodies:
            return self.bodies[url]
        symbol = url.rsplit("=", 1)[1]
        return body(symbol, marker=len(self.asked))


def run(argv: list[str], tmp_path: Path, venue: FakeVenue | None = None) -> tuple[int, str]:
    out = io.StringIO()
    code = dl.run([*argv, "--data-dir", str(tmp_path)], fetcher=venue, out=out)
    return code, out.getvalue()


class TestOneGetPerSymbolAndEnvironment:
    def test_the_default_run_fetches_four_snapshots_once_each(self, tmp_path: Path) -> None:
        venue = FakeVenue()
        code, text = run([], tmp_path, venue)
        assert code == 0
        assert venue.asked == [
            "https://api.binance.com/api/v3/exchangeInfo?symbol=BTCUSDT",
            "https://api.binance.com/api/v3/exchangeInfo?symbol=ETHUSDT",
            "https://testnet.binance.vision/api/v3/exchangeInfo?symbol=BTCUSDT",
            "https://testnet.binance.vision/api/v3/exchangeInfo?symbol=ETHUSDT",
        ]
        for environment in ("mainnet", "testnet"):
            for symbol in ("BTCUSDT", "ETHUSDT"):
                snapshot = load_snapshot(tmp_path, environment, symbol)
                assert snapshot.symbol_info.price_tick == Decimal("0.01")
                assert snapshot.symbol_info.step_size == Decimal("0.0001")
                assert f"stored {environment} {symbol}" in text
                assert snapshot.sha256 in text

    def test_the_stored_bytes_are_the_responses_bytes(self, tmp_path: Path) -> None:
        url = "https://api.binance.com/api/v3/exchangeInfo?symbol=BTCUSDT"
        raw = body("BTCUSDT", marker=7)
        venue = FakeVenue({url: raw})
        code, _ = run(["--symbols", "BTCUSDT", "--environments", "mainnet"], tmp_path, venue)
        assert code == 0
        assert snapshot_file(tmp_path, "mainnet", "BTCUSDT").read_bytes() == raw
        assert venue.asked == [url]

    def test_a_snapshot_already_stored_is_reported_and_not_requested(self, tmp_path: Path) -> None:
        first = FakeVenue()
        run(["--symbols", "BTCUSDT", "--environments", "mainnet"], tmp_path, first)
        before = snapshot_file(tmp_path, "mainnet", "BTCUSDT").read_bytes()
        second = FakeVenue()
        code, text = run(["--symbols", "BTCUSDT", "--environments", "mainnet"], tmp_path, second)
        assert code == 0
        assert second.asked == []
        assert "exists mainnet BTCUSDT" in text
        assert snapshot_file(tmp_path, "mainnet", "BTCUSDT").read_bytes() == before

    def test_only_the_missing_snapshot_is_requested_on_a_second_run(self, tmp_path: Path) -> None:
        run(["--symbols", "BTCUSDT", "--environments", "mainnet"], tmp_path, FakeVenue())
        venue = FakeVenue()
        code, _ = run(
            ["--symbols", "BTCUSDT", "ETHUSDT", "--environments", "mainnet"], tmp_path, venue
        )
        assert code == 0
        assert venue.asked == ["https://api.binance.com/api/v3/exchangeInfo?symbol=ETHUSDT"]

    def test_a_dry_run_requests_nothing_and_writes_nothing(self, tmp_path: Path) -> None:
        venue = FakeVenue()
        code, text = run(["--dry-run"], tmp_path, venue)
        assert code == 0
        assert venue.asked == []
        assert text.count("would fetch") == 4
        assert not (tmp_path / "_exchange_info").exists()

    def test_the_default_symbols_are_the_two_the_ruling_names(self) -> None:
        assert dl.DEFAULT_SYMBOLS == ("BTCUSDT", "ETHUSDT")
        assert set(dl.BASES) == {"mainnet", "testnet"}


class TestAFailureIsReportedNotRetriedNotHidden:
    def test_a_failed_request_is_reported_and_the_rest_continue(self, tmp_path: Path) -> None:
        class Failing(FakeVenue):
            def __call__(self, url: str) -> bytes:
                self.asked.append(url)
                if url.endswith("BTCUSDT") and "testnet" in url:
                    raise dl.DownloadError("HTTP 502")
                return body(url.rsplit("=", 1)[1], marker=len(self.asked))

        venue = Failing()
        code, text = run([], tmp_path, venue)
        assert code == 1
        assert "FAILED testnet BTCUSDT: DownloadError: HTTP 502" in text
        assert len(venue.asked) == 4  # one attempt each, no retry
        assert not snapshot_file(tmp_path, "testnet", "BTCUSDT").exists()
        assert snapshot_file(tmp_path, "testnet", "ETHUSDT").exists()
        assert snapshot_file(tmp_path, "mainnet", "BTCUSDT").exists()

    def test_a_response_for_the_wrong_symbol_is_stored_nowhere(self, tmp_path: Path) -> None:
        url = "https://api.binance.com/api/v3/exchangeInfo?symbol=BTCUSDT"
        venue = FakeVenue({url: body("ETHUSDT")})
        code, text = run(["--symbols", "BTCUSDT", "--environments", "mainnet"], tmp_path, venue)
        assert code == 1
        assert "FAILED mainnet BTCUSDT: SnapshotError" in text
        assert not snapshot_file(tmp_path, "mainnet", "BTCUSDT").exists()
        assert not checksum_file(tmp_path, "mainnet", "BTCUSDT").exists()

    def test_an_unknown_environment_is_refused_before_any_request(self, tmp_path: Path) -> None:
        venue = FakeVenue()
        code, text = run(["--environments", "live"], tmp_path, venue)
        assert code == 2
        assert "refused" in text
        assert venue.asked == []

    def test_a_name_that_is_not_a_symbol_is_refused_before_any_request(
        self, tmp_path: Path
    ) -> None:
        venue = FakeVenue()
        code, text = run(["--symbols", "../etc"], tmp_path, venue)
        assert code == 2
        assert "not a symbol" in text
        assert venue.asked == []


class TestTheOnlyFetcherThatOpensASocketIsGuarded:
    def test_a_url_outside_the_two_endpoints_is_refused_without_a_request(self) -> None:
        opened: list[object] = []

        def opener(request: urllib.request.Request, timeout: float) -> Any:
            opened.append(request)
            raise AssertionError("no request may be made")

        for url in (
            "https://evil.example/api/v3/exchangeInfo?symbol=BTCUSDT",
            "https://api.binance.com.evil.example/api/v3/exchangeInfo?symbol=BTCUSDT",
            "https://api.binance.com/api/v3/account",
            "http://api.binance.com/api/v3/exchangeInfo?symbol=BTCUSDT",
            "https://testnet.binance.vision/sapi/v1/capital/config/getall",
        ):
            with pytest.raises(dl.DownloadError, match="outside the two"):
                dl.fetch_url(url, opener=opener)
        assert opened == []

    def test_a_request_carries_no_key_and_a_user_agent_only(self) -> None:
        seen: list[urllib.request.Request] = []

        class Response:
            def read(self, size: int = -1, /) -> bytes:
                return b"{}"

            def __enter__(self) -> Response:
                return self

            def __exit__(self, *exc: object) -> None:
                return None

        def opener(request: urllib.request.Request, timeout: float) -> Response:
            seen.append(request)
            return Response()

        assert dl.fetch_url(dl.exchange_info_url("mainnet", "BTCUSDT"), opener=opener) == b"{}"
        assert len(seen) == 1
        headers = {key.lower() for key, _ in seen[0].header_items()}
        assert headers == {"user-agent"}
        assert seen[0].get_method() == "GET"

    def test_an_http_error_and_a_transport_error_become_download_errors(self) -> None:
        def http_error(request: urllib.request.Request, timeout: float) -> Any:
            raise urllib.error.HTTPError(request.full_url, 502, "Bad Gateway", {}, None)

        def transport_error(request: urllib.request.Request, timeout: float) -> Any:
            raise urllib.error.URLError("connection refused")

        url = dl.exchange_info_url("testnet", "BTCUSDT")
        with pytest.raises(dl.DownloadError, match="HTTP 502"):
            dl.fetch_url(url, opener=http_error)
        with pytest.raises(dl.DownloadError, match="connection refused"):
            dl.fetch_url(url, opener=transport_error)

    def test_a_response_over_the_size_cap_is_refused(self) -> None:
        class Big:
            def read(self, size: int = -1, /) -> bytes:
                return b"x" * size

            def __enter__(self) -> Big:
                return self

            def __exit__(self, *exc: object) -> None:
                return None

        with pytest.raises(dl.DownloadError, match="more than"):
            dl.fetch_url(dl.exchange_info_url("mainnet", "BTCUSDT"), opener=lambda r, t: Big())
