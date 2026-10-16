"""``scripts/store_check.py``: the inventory, the manifest comparison and the exit status (M5m P124, R-DE).

The script is the P113 scratch checker moved under ``scripts/`` with the same behaviour, so these tests pin the
behaviour itself: a real store is built by the recorder script with a fake venue (four series of twelve bars), and each
fault the checker reports is made in a copy of it by hand. Nothing here reads the network or a real store.
"""

from __future__ import annotations

import hashlib
import io
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pytest

SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import record_testnet_klines as recorder  # noqa: E402
import store_check as sc  # noqa: E402

from trading_bot.data.historical import INTERVAL_MS  # noqa: E402

UTC = timezone.utc
NOW = datetime(2026, 10, 9, 12, 0, tzinfo=UTC)
T0 = int(datetime(2026, 10, 7, 10, 30, tzinfo=UTC).timestamp() * 1000)
SERIES = [("BTCUSDT", "1m"), ("BTCUSDT", "5m"), ("ETHUSDT", "1m"), ("ETHUSDT", "5m")]
BARS = 12


def kline(open_ms: int, interval_ms: int) -> list[object]:
    return [
        open_ms,
        "100.00000000",
        "101.00000000",
        "99.00000000",
        "100.00000000",
        "1.00000000",
        open_ms + interval_ms - 1,
        "1.0",
        1,
        "1.0",
        "1.0",
        "0",
    ]


def venue(url: str) -> bytes:
    parsed = urlparse(url)
    if parsed.path.endswith("/time"):
        return json.dumps({"serverTime": T0 + 10_000 * 60_000}).encode()
    query = parse_qs(parsed.query)
    interval = query["interval"][0]
    start = int(query["startTime"][0])
    rows = [kline(T0 + i * INTERVAL_MS[interval], INTERVAL_MS[interval]) for i in range(BARS)]
    return json.dumps([r for r in rows if r[0] >= start]).encode()  # type: ignore[operator]


def make_store(root: Path) -> Path:
    """A real Testnet-shaped store: four series, one month file each, manifests, recorder logs and a lock."""
    code = recorder.run(["--root", str(root)], out=io.StringIO(), fetcher=venue, clock=lambda: NOW)
    assert code == 0
    return root


def check(root: Path, out: Path, capsys: pytest.CaptureFixture[str]) -> tuple[int, list[str]]:
    status = sc.main([str(root), str(out)])
    return status, capsys.readouterr().out.splitlines()


def tree(root: Path) -> dict[str, bytes]:
    return {p.relative_to(root).as_posix(): p.read_bytes() for p in root.rglob("*") if p.is_file()}


# --------------------------------------------------------------------------------------
# The inventory
# --------------------------------------------------------------------------------------
class TestInventory:
    def test_it_lists_every_file_with_a_posix_path_its_size_and_its_digest(
        self, tmp_path: Path
    ) -> None:
        (tmp_path / "a").mkdir()
        (tmp_path / "a" / "b.csv").write_bytes(b"xyz")
        (tmp_path / "c.json").write_bytes(b"")
        assert sc.build_inventory(tmp_path) == {
            "a/b.csv": (3, hashlib.sha256(b"xyz").hexdigest()),
            "c.json": (0, hashlib.sha256(b"").hexdigest()),
        }

    def test_a_zips_directory_is_left_out_at_any_depth(self, tmp_path: Path) -> None:
        (tmp_path / "_zips").mkdir()
        (tmp_path / "_zips" / "big.zip").write_bytes(b"zip")
        (tmp_path / "BTCUSDT" / "_zips").mkdir(parents=True)
        (tmp_path / "BTCUSDT" / "_zips" / "m.zip").write_bytes(b"zip")
        (tmp_path / "keep.txt").write_bytes(b"k")
        assert list(sc.build_inventory(tmp_path)) == ["keep.txt"]

    def test_the_order_is_sorted_by_path(self, tmp_path: Path) -> None:
        for name in ("b.txt", "a.txt", "c.txt"):
            (tmp_path / name).write_bytes(b"1")
        assert list(sc.build_inventory(tmp_path)) == ["a.txt", "b.txt", "c.txt"]

    def test_a_file_larger_than_one_block_is_hashed_whole(self, tmp_path: Path) -> None:
        data = bytes(range(256)) * 5000
        assert len(data) > sc._BLOCK
        (tmp_path / "big").write_bytes(data)
        assert sc.sha256_of(tmp_path / "big") == hashlib.sha256(data).hexdigest()

    def test_the_digest_is_over_the_path_size_digest_lines_joined_by_line_feeds(self) -> None:
        inventory = {"a": (1, "d1"), "b": (2, "d2")}
        expected = hashlib.sha256(b"a 1 d1\nb 2 d2").hexdigest()
        assert sc.inventory_digest(inventory) == expected
        assert sc.inventory_digest({}) == hashlib.sha256(b"").hexdigest()

    def test_the_inventory_file_is_one_json_line_per_file_with_line_feeds_only(
        self, tmp_path: Path
    ) -> None:
        out = tmp_path / "inv.jsonl"
        sc.write_inventory(out, {"a": (1, "d1"), "b/c": (2, "d2")})
        raw = out.read_bytes()
        assert (
            raw
            == b'{"path": "a", "size": 1, "sha256": "d1"}\n{"path": "b/c", "size": 2, "sha256": "d2"}\n'
        )
        assert b"\r" not in raw


# --------------------------------------------------------------------------------------
# The report on a real store
# --------------------------------------------------------------------------------------
class TestTheReport:
    def test_a_clean_testnet_shaped_store_reads_exit_zero_and_every_line(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        root = make_store(tmp_path / "store")
        inv = tmp_path / "inv.jsonl"
        status, lines = check(root, inv, capsys)
        files = [p for p in root.rglob("*") if p.is_file()]
        assert status == 0
        assert lines[0] == f"root                 : {root}"
        assert lines[1] == f"files (no _zips)     : {len(files)}"
        assert lines[2] == "csv months           : 4"
        assert lines[3] == f"bytes                : {sum(p.stat().st_size for p in files)}"
        assert lines[4] == f"inventory sha256     : {sc.inventory_digest(sc.build_inventory(root))}"
        assert [ln for ln in lines if ln.startswith("NO MANIFEST")] == [
            f"NO MANIFEST          : {symbol} {interval}"
            for symbol in ("BTCUSDT", "ETHUSDT")
            for interval in ("1h", "4h", "1d")
        ]
        assert "manifests            : 4" in lines
        assert "months listed        : 4" in lines
        assert "mismatched vs manifest: 0 []" in lines
        assert "missing / extra csv  : 0 / 0" in lines
        assert f"rows BTCUSDT 1m      : {BARS}" in lines
        assert f"rows ETHUSDT 5m      : {BARS}" in lines
        assert "verify problems      : 0" in lines
        assert "snapshots checked    : 0, mismatched 0" in lines
        assert lines.index("-- digests of the descriptive files --") == len(lines) - 1 - 8

    def test_the_descriptive_digests_are_the_jsonl_json_and_sha256_files_in_path_order(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        root = make_store(tmp_path / "store")
        snap = root / "_exchange_info" / "testnet"
        snap.mkdir(parents=True)
        (snap / "BTCUSDT.json").write_bytes(b"{}")
        digest = hashlib.sha256(b"{}").hexdigest()
        (snap / "BTCUSDT.json.sha256").write_text(f"{digest}  BTCUSDT.json\n", encoding="ascii")
        _, lines = check(root, tmp_path / "inv.jsonl", capsys)
        tail = lines[lines.index("-- digests of the descriptive files --") + 1 :]
        names = [ln.split("  ", 1)[1] for ln in tail]
        assert "_exchange_info/testnet/BTCUSDT.json" in names
        assert "_exchange_info/testnet/BTCUSDT.json.sha256" in names
        assert names == sorted(names)
        assert names and all(n.endswith((".jsonl", ".json", ".sha256")) for n in names)
        assert not any(n.endswith(".csv") for n in names)
        assert tail[0] == f"{sc.sha256_of(root / names[0])}  {names[0]}"

    def test_the_inventory_file_matches_the_inventory(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        root = make_store(tmp_path / "store")
        inv = tmp_path / "inv.jsonl"
        check(root, inv, capsys)
        rows = [json.loads(x) for x in inv.read_text(encoding="utf-8").splitlines()]
        assert {r["path"]: (r["size"], r["sha256"]) for r in rows} == sc.build_inventory(root)

    def test_the_store_is_not_written(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        root = make_store(tmp_path / "store")
        before = tree(root)
        check(root, tmp_path / "inv.jsonl", capsys)
        assert tree(root) == before

    def test_a_zips_directory_does_not_count(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        root = make_store(tmp_path / "store")
        _, plain = check(root, tmp_path / "a.jsonl", capsys)
        (root / "_zips").mkdir()
        (root / "_zips" / "x.zip").write_bytes(b"zip")
        status, with_zips = check(root, tmp_path / "b.jsonl", capsys)
        assert status == 0 and with_zips[:5] == plain[:5]


class TestEachFaultIsReportedAndFailsTheExit:
    def first_csv(self, root: Path) -> Path:
        return next(p for p in sorted(root.rglob("*.csv")))

    def test_a_changed_csv_is_a_mismatch(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        root = make_store(tmp_path / "store")
        csv = self.first_csv(root)
        csv.write_bytes(csv.read_bytes() + b"\n")
        status, lines = check(root, tmp_path / "inv.jsonl", capsys)
        rel = csv.relative_to(root).as_posix()
        assert status == 1
        assert f"mismatched vs manifest: 1 ['{rel}']" in lines

    def test_a_csv_the_manifest_lists_and_the_store_lacks_is_missing_and_mismatched(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        root = make_store(tmp_path / "store")
        self.first_csv(root).unlink()
        status, lines = check(root, tmp_path / "inv.jsonl", capsys)
        assert status == 1
        assert "missing / extra csv  : 1 / 0" in lines
        assert any(ln.startswith("mismatched vs manifest: 1 ") for ln in lines)

    def test_a_csv_no_manifest_lists_is_extra(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # The store's own verify also flags an unlisted month, which would fail the exit by itself and hide
        # whether "extra" does; a verify that finds nothing leaves "extra" as the only thing that can.
        class Clean:
            def __init__(self, root: Path) -> None:
                pass

            def verify(self, symbol: str, interval: str) -> tuple[str, ...]:
                return ()

        root = make_store(tmp_path / "store")
        monkeypatch.setattr(sc, "HistoricalStore", Clean)
        (root / "BTCUSDT" / "1m" / "BTCUSDT-1m-2026-11.csv").write_bytes(b"stray")
        status, lines = check(root, tmp_path / "inv.jsonl", capsys)
        assert status == 1
        assert "missing / extra csv  : 0 / 1" in lines
        assert "csv months           : 5" in lines

    def test_the_stores_own_verify_problems_are_printed_and_counted(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        class Failing:
            def __init__(self, root: Path) -> None:
                pass

            def verify(self, symbol: str, interval: str) -> tuple[str, ...]:
                return (
                    ("first", "second", "third") if (symbol, interval) == ("BTCUSDT", "1m") else ()
                )

        root = make_store(tmp_path / "store")
        monkeypatch.setattr(sc, "HistoricalStore", Failing)
        status, lines = check(root, tmp_path / "inv.jsonl", capsys)
        assert status == 1
        assert (
            "PROBLEMS BTCUSDT 1m: ('first', 'second')" in lines
            or "PROBLEMS BTCUSDT 1m: ['first', 'second']" in lines
        )
        assert "verify problems      : 3" in lines

    def test_a_snapshot_that_disagrees_with_its_sidecar_fails_and_one_that_agrees_does_not(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        root = make_store(tmp_path / "store")
        snap = root / "_exchange_info" / "testnet"
        snap.mkdir(parents=True)
        (snap / "BTCUSDT.json").write_bytes(b'{"a": 1}')
        (snap / "BTCUSDT.json.sha256").write_text(
            hashlib.sha256(b'{"a": 1}').hexdigest() + "  BTCUSDT.json\n", encoding="ascii"
        )
        ok_status, ok_lines = check(root, tmp_path / "a.jsonl", capsys)
        assert ok_status == 0 and "snapshots checked    : 1, mismatched 0" in ok_lines
        (snap / "BTCUSDT.json").write_bytes(b'{"a": 2}')
        bad_status, bad_lines = check(root, tmp_path / "b.jsonl", capsys)
        assert bad_status == 1 and "snapshots checked    : 1, mismatched 1" in bad_lines

    def test_a_series_with_no_manifest_is_skipped_not_failed(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        root = make_store(tmp_path / "store")
        status, lines = check(root, tmp_path / "inv.jsonl", capsys)
        assert status == 0 and "NO MANIFEST          : BTCUSDT 1h" in lines

    def test_an_empty_directory_has_no_manifest_in_any_series_and_exits_zero(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        empty = tmp_path / "empty"
        empty.mkdir()
        status, lines = check(empty, tmp_path / "inv.jsonl", capsys)
        assert status == 0
        assert lines[1] == "files (no _zips)     : 0"
        assert sum(ln.startswith("NO MANIFEST") for ln in lines) == 10
        assert "rows BTCUSDT 1m      : None" in lines


class TestTheCommandLine:
    def test_it_needs_a_root_and_an_inventory_path(self) -> None:
        with pytest.raises(SystemExit) as caught:
            sc.main(["only-one"])
        assert caught.value.code == 2

    def test_the_markers_it_reads_are_the_recorders(self) -> None:
        assert sc.SYMBOLS == ("BTCUSDT", "ETHUSDT")
        assert sc.INTERVALS == ("1m", "5m", "1h", "4h", "1d")
