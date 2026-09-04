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
* **The composition, from THIS file.** The store has exactly one caller -- the
  composition root, pinned by ``TestOnlyTheCompositionRootMayImportTheStore``
  -- and nothing *here* exercises it through that root. The executor's own
  tests fake the writer; these test the store alone. That gap is now covered
  elsewhere: ``test_modes.py::TestTheStoreIsReadAtBoot`` writes a real store
  and reads it back through ``live_system``. This bullet used to say no such
  test existed anywhere, which the restore commit made false.
* **What a restored record MEANS.** The round trip is pinned; the venue is
  not. Whether a restored placement actually rests at the venue is answered by
  ``resolve_placement`` on the next candle, and no test here or anywhere drives
  that against a real venue -- ``resolve_placement`` has still never run in
  production.
"""

from __future__ import annotations

import dataclasses
import json
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path

import pytest
from pydantic import ValidationError

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


def _duplicate_on_disk(path: Path, *records: s.PendingRecord) -> None:
    """Write a valid store through :func:`save`, then duplicate its first record.

    **The corruption is applied AFTER the real writer, never instead of it.**
    ``save`` takes a ``PersistedState``, which now refuses a duplicate symbol
    at construction, so the invalid file cannot be produced through the write
    path at all -- which is the property under test. Hand-writing the JSON
    would pin this file's idea of the format rather than the format, and would
    keep passing through a dumper change that broke every real store; going
    through ``save`` first means the bytes are exactly what production emits,
    with one entry copied. That is also the only route a duplicate has in
    reality: a hand-edited file.
    """
    s.save(s.PersistedState(pending=records), path)
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["pending"].append(dict(payload["pending"][0]))
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


class TestDuplicateSymbolsAreCorruption:
    """Two records for one symbol is an invalid state, never a later-wins overwrite.

    **Why it is corruption rather than a merge.** ``OrderExecutor`` keys
    ``_pending`` by symbol, so a restored duplicate collapses on the way in and
    one record disappears with nothing reporting it -- and the one that
    disappears may be the placement that actually landed, leaving an order list
    resting at the venue that nothing tracks. That is the unbounded state the
    store exists to close, reached through the restore path.

    **Every test here declares the mutation it would catch**, because a test
    that cannot fail is a defect this project has recorded four times.
    """

    def test_two_records_for_one_symbol_raise_through_load(self, tmp_path: Path) -> None:
        """MUTATION: delete the validator, or make it `return self` unconditionally.

        Also caught: moving `seen.add(...)` above the membership test, which
        makes every record look already-seen -- that fails this AND the two
        negative controls below, which is how the two mutations are told apart.
        """
        path = tmp_path / "state.json"
        _duplicate_on_disk(path, _record(symbol="BTCUSDT"))

        with pytest.raises(s.StoreCorruptError) as excinfo:
            s.load(path)

        # The symbol, so an operator can find the offending record without
        # reading the file, and the path, so they know which file.
        assert "BTCUSDT" in str(excinfo.value)
        assert "state.json" in str(excinfo.value)

    def test_a_direct_construction_is_refused_too(self) -> None:
        """MUTATION: move the check from `PersistedState` into `load`.

        That mutation leaves the load-path test above PASSING -- it is the one
        assertion that distinguishes where the check lives. The composition
        root builds a `PersistedState` on every write, so a check only in the
        read path would let a writer-side defect reach disk and surface one
        boot later, at the wrong component.

        `ValidationError` and not `StoreCorruptError`, deliberately: the latter
        says *the file cannot be trusted*, and here there is no file.
        """
        with pytest.raises(ValidationError):
            s.PersistedState(pending=(_record(symbol="BTCUSDT"), _record(symbol="BTCUSDT")))

    def test_two_records_for_different_symbols_load_fine(self, tmp_path: Path) -> None:
        """MUTATION: reject any `pending` longer than one, or compare by identity.

        Two symbols pending at once is the ORDINARY multi-pair state -- the
        shipped `config.yaml` enables two -- so a guard that refused it would
        stop the bot booting after an ordinary ambiguous write on each pair.
        """
        path = tmp_path / "state.json"
        s.save(
            s.PersistedState(pending=(_record(symbol="BTCUSDT"), _record(symbol="ETHUSDT"))), path
        )

        restored = s.load(path)

        assert restored is not None
        assert [record.symbol for record in restored.pending] == ["BTCUSDT", "ETHUSDT"]

    def test_a_single_record_still_loads(self, tmp_path: Path) -> None:
        """MUTATION: a guard keyed on `pending` being non-empty rather than on repeats.

        The single record is the case run 5 actually produced, so this is the
        one that would have broken the bot in production.
        """
        path = tmp_path / "state.json"
        s.save(s.PersistedState(pending=(_record(symbol="ETHUSDT"),)), path)

        restored = s.load(path)

        assert restored is not None
        assert len(restored.pending) == 1
        assert restored.pending[0].symbol == "ETHUSDT"

    def test_the_message_names_only_the_duplicated_symbol(self, tmp_path: Path) -> None:
        """MUTATION: report every symbol, or report a count with no name.

        Three records, one symbol repeated. An operator meeting this at boot
        has to find the bad record by hand, and a message naming all three
        sends them through two innocent ones first.
        """
        path = tmp_path / "state.json"
        # `_duplicate_on_disk` copies the FIRST entry, so BTCUSDT is the repeat
        # and ETHUSDT is the innocent bystander this asserts is not named.
        _duplicate_on_disk(path, _record(symbol="BTCUSDT"), _record(symbol="ETHUSDT"))

        with pytest.raises(s.StoreCorruptError) as excinfo:
            s.load(path)

        assert "BTCUSDT" in str(excinfo.value)
        assert "ETHUSDT" not in str(excinfo.value)

    def test_an_empty_state_is_not_a_duplicate(self) -> None:
        """MUTATION: a validator that raises whenever `duplicated` is falsy-checked wrong.

        The zero case, which is what every existing test in this file
        constructs implicitly and what a first boot produces.
        """
        assert s.PersistedState().pending == ()


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


# --------------------------------------------------------------------------
# The pending CLOSE -- a second record shape at the SAME schema
# --------------------------------------------------------------------------
def _close_record(**overrides: object) -> s.PendingCloseRecord:
    """A close against the same position ``_record`` describes."""
    fields: dict[str, object] = {
        "kind": "close",
        "symbol": "ETHUSDT",
        "entry_bar_time": BAR,
        "generation": 0,
        "quantity": D("0.72650000"),
    }
    fields.update(overrides)
    return s.PendingCloseRecord(**fields)  # type: ignore[arg-type]


class TestThePendingClose:
    """The second member of the stored union, and the file already on disk."""

    def test_a_close_record_round_trips_exactly(self, tmp_path: Path) -> None:
        """Save then load returns the same object, field for field.

        MUTATION: drop ``quantity`` from ``_dump_pending``'s close branch, or
        write the close through the placement branch.

        Equality on a frozen pydantic model compares every field, so this
        cannot pass while one is silently dropped -- and ``quantity`` is the
        one field a close carries that is not an ID seed.
        """
        path = tmp_path / "state.json"
        state = s.PersistedState(pending=(_close_record(),))

        s.save(state, path)
        loaded = s.load(path)

        assert loaded is not None
        assert loaded.pending == (_close_record(),)

    def test_the_schema_stays_at_one_so_a_close_needs_no_bump(self, tmp_path: Path) -> None:
        """THE RULING, asserted rather than trusted.

        MUTATION: bump ``SCHEMA_VERSION`` to 2.

        ``load`` tests the version by strict EQUALITY, so a bump would make
        THIS build refuse the store already on disk -- which carries the only
        real ledger this project has -- and ``live_system`` refuses to boot on
        a corrupt store. Asserting the integer on a file that contains a close
        is what pins the growth as additive.
        """
        path = tmp_path / "state.json"

        s.save(s.PersistedState(pending=(_close_record(),)), path)

        assert json.loads(path.read_text(encoding="utf-8"))["schema"] == 1
        assert s.SCHEMA_VERSION == 1

    def test_a_file_written_before_the_tag_still_loads_as_a_placement(self, tmp_path: Path) -> None:
        """**THE COMPATIBILITY CLAIM, on a payload shaped like the live file.**

        MUTATION: remove the default from ``PendingRecord.kind``, or make
        ``_load_pending`` require the key.

        Hand-written rather than produced by ``save``, deliberately: a record
        this build wrote would carry ``kind`` and could not express the
        absence. This is the shape of ``data/state.json`` as it exists today,
        ledger included, and it must load unchanged.
        """
        path = tmp_path / "state.json"
        path.write_text(
            json.dumps(
                {
                    "schema": 1,
                    "pending": [
                        {
                            "symbol": "ETHUSDT",
                            "entry_bar_time": BAR.isoformat(),
                            "generation": 0,
                            "quantity": "0.72650000",
                            "entry_limit": "2508.41000000",
                            "stop_loss": "2458.25000000",
                            "take_profit": "2608.74000000",
                        }
                    ],
                    "ledger": {"pnl_date": "2026-09-04", "realised_pnl": "-81.2855010000"},
                }
            ),
            encoding="utf-8",
        )

        loaded = s.load(path)

        assert loaded is not None
        assert loaded.pending == (_record(),)
        assert loaded.pending[0].kind == "placement"
        assert loaded.ledger == s.LedgerRecord(
            realised_pnl=D("-81.2855010000"), pnl_date=date(2026, 9, 4)
        )

    def test_both_kinds_survive_one_file_together(self, tmp_path: Path) -> None:
        """One keyspace, two shapes, neither erasing the other.

        MUTATION: have ``_load_pending`` ignore ``kind`` and always build a
        ``PendingRecord``.

        Under it the close entry raises on the missing ``entry_limit`` -- which
        ``load`` reports as ``StoreCorruptError`` -- so the failure is loud
        rather than a silently dropped record.
        """
        path = tmp_path / "state.json"
        state = s.PersistedState(pending=(_record(), _close_record(symbol="BTCUSDT")))

        s.save(state, path)
        loaded = s.load(path)

        assert loaded is not None
        assert [r.kind for r in loaded.pending] == ["placement", "close"]
        assert loaded.pending == (_record(), _close_record(symbol="BTCUSDT"))

    def test_a_close_record_has_no_entry_economics_and_cannot_acquire_any(
        self, tmp_path: Path
    ) -> None:
        """The line ``PendingPlacement`` draws, held on the store side too.

        MUTATION: add ``entry_limit`` to ``PendingCloseRecord``.

        A MARKET sell has no limit price, so a limit on a close record would be
        a fabricated value in a type whose whole justification is that it holds
        none.

        **ASSERTED AS ABSENCE, NOT AS A RAISE, and the first draft of this test
        got that wrong.** ``_Frozen`` sets only ``frozen=True``; pydantic's
        default is ``extra="ignore"``, so passing ``entry_limit=`` to a close
        record is silently DROPPED rather than refused. That is safe -- nothing
        reads a field the model does not declare -- but it means a raise is the
        wrong instrument. What is pinned instead is stronger and true: the
        field is not on the model, and a hand-edited file carrying one cannot
        put it there.
        """
        assert not (
            {"entry_limit", "stop_loss", "take_profit"} & set(s.PendingCloseRecord.model_fields)
        )

        path = tmp_path / "state.json"
        path.write_text(
            json.dumps(
                {
                    "schema": 1,
                    "pending": [
                        {
                            "kind": "close",
                            "symbol": "ETHUSDT",
                            "entry_bar_time": BAR.isoformat(),
                            "generation": 0,
                            "quantity": "0.72650000",
                            "entry_limit": "2508.41000000",
                        }
                    ],
                    "ledger": None,
                }
            ),
            encoding="utf-8",
        )

        loaded = s.load(path)

        assert loaded is not None
        assert loaded.pending == (_close_record(),)
        assert not hasattr(loaded.pending[0], "entry_limit")

    def test_an_unknown_kind_is_refused_rather_than_defaulted(self, tmp_path: Path) -> None:
        """A value we cannot read is not a placement.

        MUTATION: make ``_load_pending``'s final branch ``return
        PendingRecord(**entry)`` unconditionally.

        Defaulting an unrecognised tag would hand the resolver a record of a
        shape it cannot use, from a file a future build wrote. Refusing keeps
        the failure at the boundary, in the type this module documents.
        """
        path = tmp_path / "state.json"
        path.write_text(
            json.dumps(
                {
                    "schema": 1,
                    "pending": [{"kind": "amend", "symbol": "ETHUSDT"}],
                    "ledger": None,
                }
            ),
            encoding="utf-8",
        )

        with pytest.raises(s.StoreCorruptError, match="amend"):
            s.load(path)

    def test_a_close_still_counts_toward_the_one_record_per_symbol_rule(self) -> None:
        """The duplicate guard reads ``symbol``, which both kinds carry.

        MUTATION: scope ``_reject_duplicate_symbols`` to placements only.

        This is the store-side mirror of the single ``_pending`` keyspace: a
        symbol carries at most ONE unresolved write, of either kind. Without
        it a close and an entry could both be recorded against one symbol,
        which is the state the executor's guard exists to make impossible.
        """
        with pytest.raises(ValidationError):
            s.PersistedState(pending=(_record(), _close_record()))
