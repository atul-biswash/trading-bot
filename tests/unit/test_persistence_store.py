"""The store's guards, pinned so an edit cannot quietly remove them.

**Why these exist rather than a comment.** The store holds the only record
that an order list may be resting at the venue, and the only record of a
realised loss. Three of its properties are invisible to every gate this
project runs: that a ``Decimal`` survives the JSON boundary EXACTLY, that an
absent ledger is distinguishable from a zero one, and that a corrupt file
raises rather than reading as empty. ``ruff`` and ``mypy`` cannot see any of
them, and a future author replacing the hand-written dumpers with
``json.dumps(default=str)`` would break nothing they could see -- while
turning every unrecognised object into its ``repr``.

**What is NOT covered**, stated rather than left to be discovered:

* **Durability itself.** ``os.fsync`` is called and no test proves it survives
  a power cut; proving that needs a machine to lose power. The call is pinned;
  its effect is documented and unverified, exactly as ``instance_lock``
  records for release-on-``SIGKILL``.
* **Concurrency.** Two processes writing this file at once is not tested and
  is not prevented -- ``os.replace`` makes each write atomic, so a reader sees
  one whole state or the other, but a lost update is possible and unbounded.
* **The store has no caller.** Nothing in ``src/`` imports it outside its own
  package, so nothing here exercises it in composition with the executor or
  the composition root.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path

import pytest

from trading_bot.persistence import store as s

D = Decimal

BAR = datetime(2026, 8, 28, 15, 29, 59, 999000, tzinfo=timezone.utc)


def _record(**overrides: object) -> s.PendingRecord:
    """Run 5's real placement, which is the shape this must survive."""
    fields: dict[str, object] = {
        "symbol": "ETHUSDT",
        "entry_bar_time": BAR,
        "generation": 0,
        "quantity": D("0.72650000"),
        "entry_limit": D("2508.41000000"),
        "stop_loss": D("2458.25000000"),
        "take_profit": D("2608.74000000"),
    }
    fields.update(overrides)
    return s.PendingRecord(**fields)  # type: ignore[arg-type]


class TestDecimalRoundTrip:
    """Exactness through the string boundary. No float tolerance anywhere."""

    @pytest.mark.parametrize(
        ("value", "why"),
        [
            (D("0.72650000"), "trailing zeros a float would normalise away"),
            (D("2508.41000000"), "a real entry limit, eight places"),
            (D("-34.99550500"), "a realised loss: negative, eight places"),
            (D("0.1"), "the classic value binary float cannot represent"),
            (D("123456789.123456789"), "more precision than a float carries"),
        ],
    )
    def test_a_money_value_survives_exactly(self, tmp_path: Path, value: Decimal, why: str) -> None:
        path = tmp_path / "state.json"
        s.save(s.PersistedState(pending=(_record(quantity=value),)), path)

        restored = s.load(path)

        assert restored is not None
        assert restored.pending[0].quantity == value, why
        # Exact string identity, not merely numeric equality: `Decimal("0.1")`
        # and `Decimal("0.10")` compare equal and are different records.
        assert str(restored.pending[0].quantity) == str(value)

    def test_the_whole_record_round_trips_field_for_field(self, tmp_path: Path) -> None:
        path = tmp_path / "state.json"
        original = s.PersistedState(pending=(_record(),))

        s.save(original, path)
        restored = s.load(path)

        assert restored == original

    def test_an_aware_timestamp_survives_with_its_offset(self, tmp_path: Path) -> None:
        path = tmp_path / "state.json"
        s.save(s.PersistedState(pending=(_record(),)), path)

        restored = s.load(path)

        assert restored is not None
        assert restored.pending[0].entry_bar_time == BAR
        assert restored.pending[0].entry_bar_time.tzinfo is not None


class TestFloatIsRefused:
    def test_a_float_is_rejected_at_construction(self) -> None:
        """``Money``'s guard, reached through this model like any other."""
        with pytest.raises(Exception, match="float"):
            _record(quantity=0.7265)

    def test_a_json_number_in_the_file_is_corruption_not_a_conversion(self, tmp_path: Path) -> None:
        """The failure mode this prevents is a hand-edited file whose money
        reads as a float and is silently accepted at reduced precision."""
        path = tmp_path / "state.json"
        path.write_text(
            '{"schema": 1, "ledger": null, "pending": [{"symbol": "ETHUSDT",'
            ' "entry_bar_time": "2026-08-28T15:29:59.999000+00:00", "generation": 0,'
            ' "quantity": 0.7265, "entry_limit": "2508.41", "stop_loss": null,'
            ' "take_profit": null}]}',
            encoding="utf-8",
        )

        with pytest.raises(s.StoreCorruptError):
            s.load(path)


class TestLedgerAbsentIsNotZero:
    """Both directions, because one alone cannot show the distinction."""

    def test_an_absent_ledger_restores_as_none(self, tmp_path: Path) -> None:
        path = tmp_path / "state.json"
        s.save(s.PersistedState(), path)

        restored = s.load(path)

        assert restored is not None
        assert restored.ledger is None

    def test_a_zero_ledger_restores_as_zero_and_not_as_absent(self, tmp_path: Path) -> None:
        path = tmp_path / "state.json"
        zero = s.LedgerRecord(realised_pnl=D("0"), pnl_date=date(2026, 8, 28))
        s.save(s.PersistedState(ledger=zero), path)

        restored = s.load(path)

        assert restored is not None
        assert restored.ledger is not None
        assert restored.ledger.realised_pnl == D("0")
        assert restored.ledger.pnl_date == date(2026, 8, 28)

    def test_the_two_states_produce_different_files(self, tmp_path: Path) -> None:
        """The distinction is on disk, not merely in the objects."""
        absent_path = tmp_path / "absent.json"
        zero_path = tmp_path / "zero.json"
        s.save(s.PersistedState(), absent_path)
        s.save(
            s.PersistedState(
                ledger=s.LedgerRecord(realised_pnl=D("0"), pnl_date=date(2026, 8, 28))
            ),
            zero_path,
        )

        assert absent_path.read_text(encoding="utf-8") != zero_path.read_text(encoding="utf-8")

    def test_a_realised_loss_round_trips_exactly(self, tmp_path: Path) -> None:
        path = tmp_path / "state.json"
        ledger = s.LedgerRecord(realised_pnl=D("-34.99550500"), pnl_date=date(2026, 8, 28))
        s.save(s.PersistedState(ledger=ledger), path)

        restored = s.load(path)

        assert restored is not None
        assert restored.ledger == ledger
        assert str(restored.ledger.realised_pnl) == "-34.99550500"


class TestMissingIsNotCorrupt:
    def test_a_missing_file_is_none_and_does_not_raise(self, tmp_path: Path) -> None:
        """A first boot is normal; conflating it with corruption would make
        every first boot look like a failure."""
        assert s.load(tmp_path / "nothing-here.json") is None

    def test_a_missing_parent_directory_is_also_just_missing(self, tmp_path: Path) -> None:
        assert s.load(tmp_path / "no" / "such" / "dir" / "state.json") is None


class TestCorruptRaises:
    @pytest.mark.parametrize(
        ("body", "why"),
        [
            ("not json at all", "unparseable bytes"),
            ("[1, 2, 3]", "valid JSON that is not an object"),
            ('{"schema": 99, "pending": [], "ledger": null}', "a schema this build cannot read"),
            ('{"pending": [], "ledger": null}', "no schema key at all"),
            ('{"schema": 1, "pending": [{"symbol": "ETHUSDT"}], "ledger": null}', "a short record"),
        ],
    )
    def test_it_raises_rather_than_reading_as_empty(
        self, tmp_path: Path, body: str, why: str
    ) -> None:
        """A store that reads as empty when it cannot parse is
        indistinguishable from no store, which is what it exists to prevent."""
        path = tmp_path / "state.json"
        path.write_text(body, encoding="utf-8")

        with pytest.raises(s.StoreCorruptError):
            s.load(path)

    def test_the_error_names_the_path(self, tmp_path: Path) -> None:
        path = tmp_path / "state.json"
        path.write_text("{", encoding="utf-8")

        with pytest.raises(s.StoreCorruptError, match=r"state\.json"):
            s.load(path)


class TestAtomicWrite:
    def test_a_successful_write_leaves_no_temp_file(self, tmp_path: Path) -> None:
        path = tmp_path / "state.json"
        s.save(s.PersistedState(pending=(_record(),)), path)

        assert path.exists()
        assert list(tmp_path.iterdir()) == [path]

    def test_a_failing_replace_leaves_no_temp_file_either(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The raising path. Debris beside the store is how a later reader
        finds two files and has to guess which is real."""
        path = tmp_path / "state.json"

        def _boom(src: object, dst: object) -> None:
            raise OSError("replace refused")

        monkeypatch.setattr(s.os, "replace", _boom)

        with pytest.raises(OSError, match="replace refused"):
            s.save(s.PersistedState(pending=(_record(),)), path)

        assert list(tmp_path.iterdir()) == []

    def test_it_overwrites_an_existing_store_rather_than_appending(self, tmp_path: Path) -> None:
        path = tmp_path / "state.json"
        s.save(s.PersistedState(pending=(_record(), _record(symbol="BTCUSDT"))), path)
        s.save(s.PersistedState(), path)

        restored = s.load(path)

        assert restored is not None
        assert restored.pending == ()

    def test_it_creates_the_parent_directory(self, tmp_path: Path) -> None:
        path = tmp_path / "made" / "up" / "state.json"
        s.save(s.PersistedState(), path)

        assert path.exists()

    def test_the_file_is_written_lf_only(self, tmp_path: Path) -> None:
        """This tree is LF-pinned, and a store round-tripped through CRLF
        would still parse -- so nothing downstream would report it."""
        path = tmp_path / "state.json"
        s.save(s.PersistedState(pending=(_record(),)), path)

        assert b"\r" not in path.read_bytes()

    def test_fsync_is_called_on_the_written_handle(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Durability is not testable here; the CALL is. Without this a future
        edit could drop it and every other test would still pass."""
        seen: list[int] = []
        real_fsync = s.os.fsync

        def _record_fsync(fd: int) -> None:
            seen.append(fd)
            real_fsync(fd)

        monkeypatch.setattr(s.os, "fsync", _record_fsync)
        s.save(s.PersistedState(), tmp_path / "state.json")

        assert len(seen) == 1


class TestDefaults:
    def test_the_default_path_is_under_data_and_is_relative(self) -> None:
        """Matching ``instance_lock.DEFAULT_LOCK_PATH``'s shape: a default
        parameter, resolved against the working directory."""
        assert s.DEFAULT_STORE_PATH.as_posix() == "data/state.json"
        assert not s.DEFAULT_STORE_PATH.is_absolute()

    def test_a_fresh_state_carries_the_current_schema_and_nothing_else(self) -> None:
        state = s.PersistedState()
        assert state.schema_version == s.SCHEMA_VERSION
        assert state.pending == ()
        assert state.ledger is None

    def test_the_state_is_frozen(self) -> None:
        with pytest.raises(Exception, match="frozen"):
            s.PersistedState().pending = (_record(),)  # type: ignore[misc]


class TestNoCaller:
    def test_nothing_outside_the_package_imports_the_store(self) -> None:
        """Pinned because it is a DECISION, not an accident: the store ships
        with no caller so that wiring it -- which writes fields the risk path
        reads -- is a separate, reviewable commit."""
        root = Path(__file__).resolve().parents[2] / "src" / "trading_bot"
        offenders = [
            path.relative_to(root).as_posix()
            for path in root.rglob("*.py")
            if path.parent.name != "persistence"
            and "persistence.store" in path.read_text(encoding="utf-8")
        ]
        assert offenders == []
