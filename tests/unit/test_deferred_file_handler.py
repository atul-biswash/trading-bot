"""``DeferredFileHandler``: records held until a file is chosen, then written in order.

A backtest names its log only after its run directory exists, but logs its banner and its
provenance line first. These tests judge the handler by the bytes it leaves on disk and by
what it refuses, never by its internals.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Iterator
from pathlib import Path

import pytest

from trading_bot.utils.logger import DeferredFileHandler, PlainFormatter

_LOGGER_NAME = "tests.deferred_file_handler"


def record(message: str, **extra: object) -> logging.LogRecord:
    made = logging.getLogger(_LOGGER_NAME).makeRecord(
        _LOGGER_NAME, logging.INFO, __file__, 1, message, (), None, extra=extra or None
    )
    return made


@pytest.fixture
def handler() -> Iterator[DeferredFileHandler]:
    made = DeferredFileHandler(json_format=False)
    yield made
    made.close()


def lines(path: Path) -> list[str]:
    return path.read_text(encoding="utf-8").splitlines()


class TestHoldingAndFlushing:
    def test_nothing_reaches_the_disk_before_a_file_is_chosen(
        self, handler: DeferredFileHandler, tmp_path: Path
    ) -> None:
        handler.handle(record("banner"))
        handler.handle(record("provenance"))
        assert list(tmp_path.iterdir()) == []
        assert handler.is_open is False

    def test_open_writes_the_held_records_in_order_and_then_the_later_ones(
        self, handler: DeferredFileHandler, tmp_path: Path
    ) -> None:
        for text in ("first", "second", "third"):
            handler.handle(record(text))
        target = tmp_path / "run.log"
        handler.open(target)
        handler.handle(record("fourth"))
        handler.close_file()
        written = lines(target)
        assert len(written) == 4
        assert [line.rsplit(" | ", 1)[1] for line in written] == [
            "first",
            "second",
            "third",
            "fourth",
        ]

    def test_a_line_is_the_plain_sink_format_with_its_structured_fields(
        self, handler: DeferredFileHandler, tmp_path: Path
    ) -> None:
        made = record("Startup provenance accepted", event="boot_provenance", verdict="accepted")
        handler.handle(made)
        target = tmp_path / "run.log"
        handler.open(target)
        handler.close_file()
        expected = PlainFormatter(
            "%(asctime)s | %(levelname)-8s | pid=%(process)d | %(name)s | %(message)s",
            "%Y-%m-%dT%H:%M:%SZ",
        ).format(made)
        assert lines(target) == [expected]
        assert "event=boot_provenance verdict=accepted" in expected

    def test_the_json_format_writes_one_json_object_per_line(self, tmp_path: Path) -> None:
        made = DeferredFileHandler(json_format=True)
        try:
            made.handle(record("held", event="a_held_event"))
            target = tmp_path / "run.jsonl"
            made.open(target)
            made.handle(record("live"))
            made.close_file()
        finally:
            made.close()
        parsed = [json.loads(line) for line in lines(target)]
        assert [row["message"] for row in parsed] == ["held", "live"]
        assert parsed[0]["event"] == "a_held_event"


class TestRefusals:
    def test_an_existing_path_is_never_overwritten(
        self, handler: DeferredFileHandler, tmp_path: Path
    ) -> None:
        target = tmp_path / "run.log"
        target.write_bytes(b"an earlier run\n")
        handler.handle(record("held"))
        with pytest.raises(FileExistsError):
            handler.open(target)
        assert target.read_bytes() == b"an earlier run\n"
        assert handler.is_open is False

    def test_a_second_open_is_refused(self, handler: DeferredFileHandler, tmp_path: Path) -> None:
        handler.open(tmp_path / "a.log")
        with pytest.raises(ValueError, match="already been opened"):
            handler.open(tmp_path / "b.log")
        assert not (tmp_path / "b.log").exists()

    def test_a_sealed_handler_cannot_be_reopened(
        self, handler: DeferredFileHandler, tmp_path: Path
    ) -> None:
        handler.open(tmp_path / "a.log")
        handler.close_file()
        with pytest.raises(ValueError, match="already been opened"):
            handler.open(tmp_path / "b.log")
        assert not (tmp_path / "b.log").exists()


class TestSealing:
    def test_records_after_close_file_are_written_nowhere(
        self, handler: DeferredFileHandler, tmp_path: Path
    ) -> None:
        target = tmp_path / "run.log"
        handler.open(target)
        handler.handle(record("kept"))
        handler.close_file()
        size = target.stat().st_size
        handler.handle(record("after the seal"))
        assert target.stat().st_size == size
        assert handler.is_open is False
        assert "after the seal" not in target.read_text(encoding="utf-8")

    def test_close_file_is_idempotent_and_safe_before_open(
        self, handler: DeferredFileHandler, tmp_path: Path
    ) -> None:
        handler.close_file()
        handler.close_file()
        handler.handle(record("still held"))
        target = tmp_path / "run.log"
        handler.open(target)
        handler.close_file()
        assert [line.rsplit(" | ", 1)[1] for line in lines(target)] == ["still held"]


class TestCapacity:
    def test_records_beyond_the_capacity_are_counted_and_not_written(self, tmp_path: Path) -> None:
        small = DeferredFileHandler(json_format=False, capacity=2)
        try:
            for text in ("one", "two", "three", "four"):
                small.handle(record(text))
            assert small.dropped == 2
            target = tmp_path / "run.log"
            small.open(target)
            small.close_file()
        finally:
            small.close()
        assert [line.rsplit(" | ", 1)[1] for line in lines(target)] == ["one", "two"]

    def test_a_handler_that_is_never_opened_leaves_no_file(self, tmp_path: Path) -> None:
        unused = DeferredFileHandler(json_format=False)
        unused.handle(record("refused before it began"))
        unused.close()
        assert list(tmp_path.iterdir()) == []
