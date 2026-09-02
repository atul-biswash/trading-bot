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
* **The composition.** The store now has exactly one caller -- the composition
  root, pinned by ``TestOnlyTheCompositionRootMayImportTheStore`` -- but
  nothing here exercises it THROUGH that root. The executor's own tests fake
  the writer; these test the store alone. No test in this repository writes a
  real ``data/state.json`` and reads it back through ``live_system``.
* **The read path.** Nothing loads the store at boot yet. As of the wiring
  commit this is a WRITE PATH WITH NO READER, deliberately, and restore is a
  later change.
"""

from __future__ import annotations

import dataclasses
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path

import pytest

# The one test below reaches into `execution/` on purpose; see its docstring.
from trading_bot.execution.executor import PendingPlacement
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


class TestFieldAgreementWithPendingPlacement:
    """The two pending types must carry the same field NAMES. Nothing else
    checks it.

    ``PendingPlacement`` is a frozen dataclass in ``execution/`` and
    ``PendingRecord`` is a pydantic model here: seven fields each, maintained
    by hand in two layers. A field added to one and not the other is a SILENT
    persistence gap -- the executor would hold it, the store would drop it,
    and nothing would raise. The record would simply come back from disk
    missing something.

    **It lives with the store's tests rather than the executor's**, because of
    where the failure is READ. A disagreement means the store cannot hold what
    it exists to hold; a reader seeing this file fail is told the persistence
    layer is incomplete, which is actionable. The same failure under
    ``test_executor.py`` would read as "the executor is broken", which it
    would not be. That is also why this file imports from ``execution/`` --
    the coupling is real and the test is where its consequence lands.

    **WHAT THIS DOES NOT CHECK**, stated because a test whose name overclaims
    is a recorded defect class here (``M5f-088``, ``M5f-073``, ``M5h-045``):

    * **Types.** MEASURED and deliberately declined. The two machineries
      report the same declaration irreconcilably: ``dataclasses.fields()``
      yields the *string* ``'Money'``, because that module carries
      ``from __future__ import annotations``, while pydantic yields the
      resolved ``Optional[Annotated[Decimal, BeforeValidator(...)]]``. A type
      check would have to hand-write the very mapping it exists to verify.
    * **Optionality**, still. Both types now REQUIRE all seven -- the
      asymmetry this bullet used to record is fixed, and
      ``TestRequiredProtectiveLevels`` below is what pins it, because a
      name-set comparison cannot see requiredness in either direction.
    * **Ordering**, because the store dumps by name and order carries nothing.
    * **Semantics.** Two fields agreeing in name and meaning nothing alike
      would pass this.
    * **Arity.** No ``== 7`` assertion: adding a field to BOTH types is a
      legitimate change and must not fail. Agreement is the property, not
      count.

    **Aliases were checked and are absent.** MEASURED: no ``PendingRecord``
    field carries ``alias`` or ``validation_alias``, and ``_dump_pending``
    writes keys by hand rather than through pydantic -- so an alias could not
    change the file even if one were added. An alias assertion would pin
    something that cannot break the store.
    """

    def test_the_two_types_carry_the_same_field_names(self) -> None:
        placement = {field.name for field in dataclasses.fields(PendingPlacement)}
        record = set(s.PendingRecord.model_fields)

        assert placement == record


class TestRequiredProtectiveLevels:
    """``stop_loss`` and ``take_profit`` are REQUIRED, matching
    ``PendingPlacement``.

    The type still admits ``None`` -- a both-disabled config is legal and its
    levels are genuinely absent -- so what is required is the KEY, not a value.
    A truncated store must RAISE rather than read as unprotected, which is the
    dangerous direction: a record silently missing its stop would describe a
    position the bot believes has no protection to reconcile against.

    This is invisible to ``TestFieldAgreementWithPendingPlacement``, which
    compares name sets, and that is why it needs its own class.
    """

    def test_a_stored_record_omitting_stop_loss_raises_store_corrupt(self, tmp_path: Path) -> None:
        path = tmp_path / "state.json"
        path.write_text(
            '{"schema": 1, "ledger": null, "pending": [{"symbol": "ETHUSDT",'
            ' "entry_bar_time": "2026-08-28T15:29:59.999000+00:00", "generation": 0,'
            ' "quantity": "0.72650000", "entry_limit": "2508.41",'
            ' "take_profit": null}]}',
            encoding="utf-8",
        )

        with pytest.raises(s.StoreCorruptError):
            s.load(path)

    def test_a_stored_record_omitting_take_profit_raises_store_corrupt(
        self, tmp_path: Path
    ) -> None:
        path = tmp_path / "state.json"
        path.write_text(
            '{"schema": 1, "ledger": null, "pending": [{"symbol": "ETHUSDT",'
            ' "entry_bar_time": "2026-08-28T15:29:59.999000+00:00", "generation": 0,'
            ' "quantity": "0.72650000", "entry_limit": "2508.41",'
            ' "stop_loss": null}]}',
            encoding="utf-8",
        )

        with pytest.raises(s.StoreCorruptError):
            s.load(path)

    def test_an_explicit_null_still_loads(self, tmp_path: Path) -> None:
        """The other half, and the one that stops this being over-tightened: a
        both-disabled placement has no levels, and its record must round-trip."""
        path = tmp_path / "state.json"
        s.save(s.PersistedState(pending=(_record(stop_loss=None, take_profit=None),)), path)

        restored = s.load(path)

        assert restored is not None
        assert restored.pending[0].stop_loss is None
        assert restored.pending[0].take_profit is None

    def test_constructing_without_the_keys_is_refused(self) -> None:
        with pytest.raises(Exception, match="stop_loss"):
            s.PendingRecord(
                symbol="ETHUSDT",
                entry_bar_time=BAR,
                generation=0,
                quantity=D("1"),
                entry_limit=D("2"),
            )


class TestOnlyTheCompositionRootMayImportTheStore:
    """The store now HAS a caller, and this pins WHICH.

    It replaces a ``TestNoCaller`` that asserted nobody imported the store at
    all. That property is false as of the wiring commit -- and worse, the test
    would have kept PASSING, because it searched for the string
    ``persistence.store`` while the root imports
    ``from trading_bot.persistence import store``. A test that survives the
    falsification of its own premise is not coverage.

    What is pinned instead is the property that still holds and is the one
    worth holding: ``execution/`` must never import ``persistence/``.
    `CLAUDE.md` has outer layers "depend inward only", and the composition
    root is the single layer permitted to know both -- which is exactly why
    the executor takes an injected callable rather than importing the store.
    """

    def test_execution_never_imports_persistence(self) -> None:
        execution = Path(__file__).resolve().parents[2] / "src" / "trading_bot" / "execution"
        offenders = [
            path.name
            for path in execution.rglob("*.py")
            if "trading_bot.persistence" in path.read_text(encoding="utf-8")
        ]
        assert offenders == []

    def test_the_composition_root_is_the_only_importer(self) -> None:
        root = Path(__file__).resolve().parents[2] / "src" / "trading_bot"
        importers = sorted(
            path.relative_to(root).as_posix()
            for path in root.rglob("*.py")
            if path.parent.name != "persistence"
            and "trading_bot.persistence" in path.read_text(encoding="utf-8")
        )
        assert importers == ["engine/modes.py"]
