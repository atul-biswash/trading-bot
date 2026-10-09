"""``scripts/regime_labels.py``: the labels are written once, and re-derivable by ``--check``.

The store is real -- monthly archives built through ``ingest_zip`` -- but small: nine months of
BTCUSDT daily bars, October 2023 to June 2024, three complete quarters whose open and close are
written into this file, so the labels the script must produce are arithmetic done by hand:

    2023Q4  opens 100, closes 120   +20%   rising
    2024Q1  opens 120, closes 100   -16.7% falling
    2024Q2  opens 100, closes 104   +4%    sideways
"""

from __future__ import annotations

import hashlib
import io
import json
import sys
import zipfile
from datetime import date, timedelta
from pathlib import Path

import pytest

from trading_bot.backtesting.regimes import quarter_key
from trading_bot.data.historical import ingest_zip, month_bounds_ms

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

import regime_labels

DAY_MS = 86_400_000
MONTHS = (
    "2023-10",
    "2023-11",
    "2023-12",
    "2024-01",
    "2024-02",
    "2024-03",
    "2024-04",
    "2024-05",
    "2024-06",
)
#: quarter -> (the constant price inside it, the close of its last day)
PLAN = {"2023Q4": (100, 120), "2024Q1": (120, 100), "2024Q2": (100, 104)}
EPOCH = date(1970, 1, 1)
_PINNED = (2024, 1, 1, 0, 0, 0)


def day_lines(month: str, *, plan: dict[str, tuple[int, int]]) -> list[str]:
    start_ms, end_ms = month_bounds_ms(month)
    lines = []
    for opened in range(start_ms, end_ms, DAY_MS):
        day = EPOCH + timedelta(days=opened // DAY_MS)
        constant, last_close = plan[quarter_key(day)]
        next_day = day + timedelta(days=1)
        is_last = quarter_key(next_day) != quarter_key(day)
        close = last_close if is_last else constant
        high, low = max(constant, close), min(constant, close)
        lines.append(
            f"{opened},{constant}.00000000,{high}.00000000,{low}.00000000,{close}.00000000,"
            f"1.00000000,{opened + DAY_MS - 1},100.00000000,1,0.50000000,50.00000000,0"
        )
    return lines


def build_store(root: Path, *, plan: dict[str, tuple[int, int]] | None = None) -> None:
    chosen = plan if plan is not None else PLAN
    for month in MONTHS:
        data = io.BytesIO()
        info = zipfile.ZipInfo(f"BTCUSDT-1d-{month}.csv", date_time=_PINNED)
        info.compress_type = zipfile.ZIP_DEFLATED
        with zipfile.ZipFile(data, "w") as archive:
            archive.writestr(info, "\n".join(day_lines(month, plan=chosen)) + "\n")
        raw = data.getvalue()
        ingest_zip(
            raw,
            expected_sha256=hashlib.sha256(raw).hexdigest(),
            root=root,
            symbol="BTCUSDT",
            interval="1d",
            month=month,
            source_url=f"https://example.invalid/BTCUSDT-1d-{month}.zip",
        )


def run(args: list[str], capsys: pytest.CaptureFixture[str]) -> tuple[int, str]:
    code = regime_labels.run(args)
    return code, capsys.readouterr().out


def invocation(tmp_path: Path, *extra: str) -> list[str]:
    return [
        "--data-dir",
        str(tmp_path / "hist"),
        "--out",
        str(tmp_path / "out" / "labels.json"),
        *extra,
    ]


@pytest.fixture
def store(tmp_path: Path) -> Path:
    build_store(tmp_path / "hist")
    return tmp_path


class TestWriting:
    def test_it_writes_the_labels_and_a_digest_file_beside_them(
        self, store: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        code, text = run(invocation(store), capsys)
        assert code == 0
        target = store / "out" / "labels.json"
        document = json.loads(target.read_bytes())
        rows = {row["quarter"]: row for row in document["quarters"]}
        assert {key: row["regime"] for key, row in rows.items()} == {
            "2023Q4": "rising",
            "2024Q1": "falling",
            "2024Q2": "sideways",
        }
        assert document["counts"] == {
            "rising": 1,
            "falling": 1,
            "sideways": 1,
            "partial": 0,
            "quarters": 3,
        }
        assert (rows["2023Q4"]["open_first"], rows["2023Q4"]["close_last"]) == (
            "100.00000000",
            "120.00000000",
        )
        assert rows["2024Q1"]["return"] == "-0.166667"
        digest = hashlib.sha256(target.read_bytes()).hexdigest()
        assert (store / "out" / "labels.json.sha256").read_text(
            encoding="ascii"
        ) == f"{digest}  labels.json\n"
        assert digest in text

    def test_the_source_block_names_the_series_and_the_manifest_it_was_read_from(
        self, store: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        run(invocation(store), capsys)
        source = json.loads((store / "out" / "labels.json").read_bytes())["source"]
        manifest = store / "hist" / "BTCUSDT" / "1d" / "MANIFEST.jsonl"
        assert source["series"] == "BTCUSDT 1d"
        assert source["store_manifest_sha256"] == hashlib.sha256(manifest.read_bytes()).hexdigest()
        assert (source["first_open"], source["last_open"]) == (
            "2023-10-01T00:00:00+00:00",
            "2024-06-30T00:00:00+00:00",
        )
        assert source["bars"] == 274  # 2023-10-01 to 2024-06-30, one daily bar each

    def test_a_second_write_is_refused_and_changes_nothing(
        self, store: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        run(invocation(store), capsys)
        before = {p.name: p.read_bytes() for p in (store / "out").iterdir()}
        code, text = run(invocation(store), capsys)
        assert code == 2
        assert "refused" in text and "written once" in text
        assert {p.name: p.read_bytes() for p in (store / "out").iterdir()} == before

    def test_a_leftover_digest_file_alone_also_refuses_the_write(
        self, store: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        (store / "out").mkdir()
        (store / "out" / "labels.json.sha256").write_text("stale\n", encoding="ascii")
        code, _ = run(invocation(store), capsys)
        assert code == 2
        assert not (store / "out" / "labels.json").exists()


class TestChecking:
    def test_a_file_equal_to_the_store_checks_equal_and_nothing_is_written(
        self, store: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        run(invocation(store), capsys)
        before = {p.name: (p.read_bytes(), p.stat().st_mtime_ns) for p in (store / "out").iterdir()}
        code, text = run(invocation(store, "--check"), capsys)
        assert code == 0 and text.startswith("equal")
        assert {
            p.name: (p.read_bytes(), p.stat().st_mtime_ns) for p in (store / "out").iterdir()
        } == before

    def test_a_label_file_that_was_edited_is_reported_as_differing(
        self, store: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        run(invocation(store), capsys)
        target = store / "out" / "labels.json"
        target.write_bytes(
            target.read_bytes().replace(b'"regime": "falling"', b'"regime": "rising"')
        )
        code, text = run(invocation(store, "--check"), capsys)
        assert code == 1 and text.startswith("DIFFERS")

    def test_a_missing_digest_file_is_reported_as_differing(
        self, store: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        run(invocation(store), capsys)
        (store / "out" / "labels.json.sha256").unlink()
        code, text = run(invocation(store, "--check"), capsys)
        assert code == 1 and text.startswith("DIFFERS")

    def test_a_store_that_has_changed_since_the_file_was_written_is_reported_as_differing(
        self,
        store: Path,
        tmp_path_factory: pytest.TempPathFactory,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        run(invocation(store), capsys)
        other = tmp_path_factory.mktemp("other")
        build_store(
            other / "hist", plan={"2023Q4": (100, 130), "2024Q1": (130, 100), "2024Q2": (100, 104)}
        )
        code, text = run(
            [
                "--data-dir",
                str(other / "hist"),
                "--out",
                str(store / "out" / "labels.json"),
                "--check",
            ],
            capsys,
        )
        assert code == 1 and text.startswith("DIFFERS")

    def test_a_check_with_no_file_at_all_differs(
        self, store: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        code, text = run(invocation(store, "--check"), capsys)
        assert code == 1 and text.startswith("DIFFERS")


class TestAStoreThatCannotBeRead:
    def test_an_empty_data_directory_is_reported_and_writes_nothing(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        code, text = run(
            [
                "--data-dir",
                str(tmp_path / "nowhere"),
                "--out",
                str(tmp_path / "out" / "labels.json"),
            ],
            capsys,
        )
        assert code == 1
        assert "cannot read the store" in text
        assert not (tmp_path / "out").exists()

    def test_a_month_file_that_no_longer_matches_its_manifest_is_reported(
        self, store: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        month_file = next((store / "hist" / "BTCUSDT" / "1d").glob("*2024-02*.csv"))
        month_file.write_bytes(month_file.read_bytes() + b"x")
        code, text = run(invocation(store), capsys)
        assert code == 1
        assert "cannot read the store" in text and "StoredFileError" in text
        assert not (store / "out" / "labels.json").exists()
