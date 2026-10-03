"""Tests for ``scripts/normalize_ledger_exponents.py`` (C49, the owner's P92-7).

Every test runs in a ``tmp_path`` working directory (``tests/conftest.py``
chdirs each non-integration test), so the tool's relative ``data/state.json``,
``logs/.bot.lock`` and ``logs/normalize.log`` are this test's own.

The fixture's figures are the MEASURED ones: the exponent -24 values
``M5l-210`` read out of the copy of ``state.json`` whose SHA-256 is
``5164ccc0499c4c9f01164fdac9d9bd8ce9a978d32cd14df36912a66a9cff0f07``.
Each test names the mutation it exists for and asserts on the STORE'S BYTES,
because a tool that says it normalised a ledger is worth only what the file
says afterwards.
"""

from __future__ import annotations

import hashlib
import json
import sys
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

import normalize_ledger_exponents
from normalize_ledger_exponents import NORMALIZE_LOG_PATH, NotLosslessError, main, quantise_to_8dp

from trading_bot.persistence import store
from trading_bot.utils.instance_lock import DEFAULT_LOCK_PATH, acquire

D = Decimal
STORE = Path("data/state.json")
NOW = datetime(2026, 10, 3, 12, 0, tzinfo=timezone.utc)

#: The measured exponent -24 figures, and what they become. Equal in VALUE.
LIFETIME = "-209.601849800000000000000000"
DAY_24 = "2.885073700000000000000000"
DAY_10 = "-0.5411033000"
OPEN_DAY = "75.164021600000000000000000"


def _position(symbol: str = "BTCUSDT") -> store.PositionRecord:
    return store.PositionRecord(
        kind="position",
        symbol=symbol,
        entry_bar_time=datetime(2026, 9, 20, 10, 0, tzinfo=timezone.utc),
        generation=0,
        quantity=D("0.02310000"),
        entry_limit=D("60123.45000000"),
        stop_loss=D("58000.00000000"),
        take_profit=D("63000.00000000"),
    )


def _state(*, open_day: str = OPEN_DAY, lifetime: str | None = LIFETIME) -> store.PersistedState:
    return store.PersistedState(
        positions=(_position(),),
        ledger=store.LedgerRecord(
            realised_pnl=D(open_day), pnl_date=date(2026, 9, 21), trades_count=3
        ),
        daily_history={
            date(2026, 9, 10): store.DayRecord(realised=D(DAY_24), trades_count=2),
            date(2026, 9, 14): store.DayRecord(realised=D(DAY_10), trades_count=4),
        },
        lifetime_realised=None if lifetime is None else D(lifetime),
    )


def _write(state: store.PersistedState | None = None) -> str:
    """Write the store and return its SHA-256."""
    store.save(state or _state(), STORE)
    return _sha()


def _sha() -> str:
    return hashlib.sha256(STORE.read_bytes()).hexdigest()


def _payload() -> dict[str, Any]:
    loaded: dict[str, Any] = json.loads(STORE.read_text(encoding="utf-8"))
    return loaded


# --------------------------------------------------------------------------
# The quantiser: lossless or not at all
# --------------------------------------------------------------------------
@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("5.201974900000000000000000", "5.20197490"),
        ("-209.601849800000000000000000", "-209.60184980"),
        ("-0.5411033000", "-0.54110330"),
        ("0E-24", "0E-8"),
        ("5.20197490", "5.20197490"),
        ("5.2019749", "5.2019749"),
        ("12", "12"),
    ],
)
def test_the_quantiser_brings_a_lossless_value_to_exponent_minus_8(raw: str, expected: str) -> None:
    """Finer than -8 is quantised; -8 or coarser is returned untouched.

    Compared by `str` so the EXPONENT is asserted, not only the value.
    MUTATION: quantise a coarser value too (`5.2019749` would become
    `5.20197490`), or return the input unchanged.
    """
    result = quantise_to_8dp(D(raw))

    assert str(result) == expected
    assert result == D(raw)


@pytest.mark.parametrize("raw", ["1.123456789", "-0.000000001", "209.601849812345678901234567"])
def test_the_quantiser_refuses_a_value_that_would_lose_a_digit(raw: str) -> None:
    """A nonzero ninth decimal place is never rounded. MUTATION: drop the equality check."""
    with pytest.raises(NotLosslessError):
        quantise_to_8dp(D(raw))


# --------------------------------------------------------------------------
# The tool
# --------------------------------------------------------------------------
class TestNormalising:
    def test_lossless_values_are_normalised_and_nothing_else_moves(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """All FOUR figures at -8, equal in value, the position record byte-identical.

        The exponent-24 open day, the exponent-24 history row, the exponent-24
        lifetime and an exponent-10 history row. MUTATION: skip any one site
        (the ledger, the history, the lifetime), or touch the position's
        money.
        """
        _write()
        before = _payload()

        rc = main(["--apply"], clock=lambda: NOW)

        assert rc == 0
        after = _payload()
        assert after["ledger"]["realised_pnl"] == "75.16402160"
        assert after["lifetime_realised"] == "-209.60184980"
        assert after["daily_history"]["2026-09-10"]["realised"] == "2.88507370"
        assert after["daily_history"]["2026-09-14"]["realised"] == "-0.54110330"
        # Equal in value to what was there: the repair is the exponent only.
        assert D(after["ledger"]["realised_pnl"]) == D(before["ledger"]["realised_pnl"])
        assert D(after["lifetime_realised"]) == D(before["lifetime_realised"])
        # Everything else is the same bytes: positions, pending, dates, counts.
        assert after["positions"] == before["positions"]
        assert after["pending"] == before["pending"]
        assert after["ledger"]["pnl_date"] == before["ledger"]["pnl_date"]
        assert after["ledger"]["trades_count"] == before["ledger"]["trades_count"]
        assert after["daily_history"]["2026-09-10"]["trades_count"] == 2
        assert "NORMALISED 4 value(s)" in capsys.readouterr().out

    def test_a_non_lossless_value_refuses_and_writes_nothing(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """One bad value refuses the whole file: no partial normalisation, no log.

        The open day carries a ninth decimal place, beside figures that WOULD
        quantise. MUTATION: quantise without the lossless check -- the file is
        then rewritten with `1.12345679`, and the SHA, the exit code and the
        absent log all fail.
        """
        before = _write(_state(open_day="1.123456789"))

        rc = main(["--apply"], clock=lambda: NOW)

        out = capsys.readouterr().out
        assert rc == 1
        assert _sha() == before
        assert "ledger.realised_pnl = 1.123456789" in out
        assert "REFUSED" in out
        assert not NORMALIZE_LOG_PATH.exists()

    def test_every_refusal_is_listed_not_only_the_first(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """The operator sees every figure that blocks the run. MUTATION: stop at the first."""
        state = _state(open_day="1.123456789", lifetime="-209.601849812")
        _write(state)

        rc = main(["--apply"], clock=lambda: NOW)

        out = capsys.readouterr().out
        assert rc == 1
        assert "ledger.realised_pnl" in out
        assert "lifetime_realised" in out
        assert "2 value(s)" in out

    def test_it_refuses_while_the_bots_lock_is_held(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """MUTATION: skip the lock check.

        The lock is taken here by the test and so is held when `main` tries for
        it. The store is compared by SHA-256: a tool that skipped the check
        would rewrite it.
        """
        before = _write()

        with acquire(DEFAULT_LOCK_PATH):
            rc = main(["--apply"], clock=lambda: NOW)

        assert rc == 1
        assert _sha() == before
        assert "instance lock is held" in capsys.readouterr().out
        assert not NORMALIZE_LOG_PATH.exists()

    def test_the_lock_is_released_on_exit(self) -> None:
        """The tool holds the lock for its own run and not a moment longer."""
        _write()

        assert main(["--apply"], clock=lambda: NOW) == 0

        with acquire(DEFAULT_LOCK_PATH):
            pass

    def test_both_shas_are_logged_and_printed(self, capsys: pytest.CaptureFixture[str]) -> None:
        """One log line, carrying the store's SHA-256 before and after.

        MUTATION: log only the before, hash the file before the write twice,
        or log nothing.
        """
        before = _write()

        rc = main(["--apply"], clock=lambda: NOW)

        after = _sha()
        assert rc == 0
        assert after != before
        lines = NORMALIZE_LOG_PATH.read_text(encoding="utf-8").splitlines()
        assert len(lines) == 1
        assert f"store_sha256_before={before}" in lines[0]
        assert f"store_sha256_after={after}" in lines[0]
        assert "values_changed=4" in lines[0]
        assert NOW.isoformat() in lines[0]
        out = capsys.readouterr().out
        assert before in out
        assert after in out

    def test_without_apply_it_previews_and_writes_nothing(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """MUTATION: write regardless of the flag."""
        before = _write()

        rc = main([], clock=lambda: NOW)

        out = capsys.readouterr().out
        assert rc == 0
        assert _sha() == before
        assert "PREVIEW: 4 value(s) would change" in out
        assert f"{LIFETIME} -> -209.60184980" in out
        assert not NORMALIZE_LOG_PATH.exists()

    def test_a_ledger_already_at_eight_places_is_left_alone(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Idempotent: a second run finds nothing, writes nothing and logs nothing."""
        _write()
        assert main(["--apply"], clock=lambda: NOW) == 0
        normalised = _sha()
        capsys.readouterr()

        rc = main(["--apply"], clock=lambda: NOW)

        assert rc == 0
        assert _sha() == normalised
        assert "NOTHING TO NORMALISE" in capsys.readouterr().out
        # Asserted to EXIST before it is read: a missing log would otherwise raise
        # FileNotFoundError, a crash, where the mutation should fail an assertion.
        assert NORMALIZE_LOG_PATH.exists()
        assert len(NORMALIZE_LOG_PATH.read_text(encoding="utf-8").splitlines()) == 1

    def test_a_store_with_no_ledger_is_nothing_to_do(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """`ledger=None` and no lifetime: no site, no change, and no crash."""
        before = _write(store.PersistedState(positions=(_position(),)))

        rc = main(["--apply"], clock=lambda: NOW)

        assert rc == 0
        assert _sha() == before
        assert "NOTHING TO NORMALISE" in capsys.readouterr().out

    def test_a_store_at_another_schema_is_refused_untouched(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Exponents only: saving an older store would upgrade it too (schema and `positions`).

        MUTATION: drop the schema check -- the file is then rewritten at the
        current schema, and the SHA and the exit code both fail.
        """
        _write()
        payload = _payload()
        payload["schema"] = 1
        del payload["positions"]
        STORE.write_text(json.dumps(payload), encoding="utf-8")
        before = _sha()

        rc = main(["--apply"], clock=lambda: NOW)

        out = capsys.readouterr().out
        assert rc == 1
        assert _sha() == before
        assert "schema 1" in out
        assert "upgrade" in out
        assert not NORMALIZE_LOG_PATH.exists()

    def test_a_missing_store_is_refused(self, capsys: pytest.CaptureFixture[str]) -> None:
        rc = main(["--apply"], clock=lambda: NOW)

        assert rc == 1
        assert "there is no store" in capsys.readouterr().out
        assert not NORMALIZE_LOG_PATH.exists()

    def test_a_corrupt_store_is_refused_untouched(self, capsys: pytest.CaptureFixture[str]) -> None:
        STORE.parent.mkdir(parents=True, exist_ok=True)
        STORE.write_text("{not json", encoding="utf-8")
        before = _sha()

        rc = main(["--apply"], clock=lambda: NOW)

        assert rc == 1
        assert _sha() == before
        assert "corrupt" in capsys.readouterr().out

    def test_a_store_option_names_another_file(self) -> None:
        other = Path("elsewhere.json")
        store.save(_state(), other)
        untouched = _write()

        rc = main(["--apply", "--store", str(other)], clock=lambda: NOW)

        assert rc == 0
        assert _sha() == untouched
        assert json.loads(other.read_text(encoding="utf-8"))["lifetime_realised"] == "-209.60184980"

    def test_a_log_that_cannot_be_written_still_prints_both_shas(
        self, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Exit 3, with the SHAs on the screen so the operator can record them by hand."""
        before = _write()

        def _boom(**_kwargs: object) -> str:
            raise OSError("disk full")

        monkeypatch.setattr(normalize_ledger_exponents, "_append_log", _boom)

        rc = main(["--apply"], clock=lambda: NOW)

        out = capsys.readouterr().out
        assert rc == 3
        assert f"before={before}" in out
        assert f"after={_sha()}" in out
