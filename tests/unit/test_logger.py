"""Tests for the logging substrate.

This module had **no** test coverage before Phase 5 M4's structured-logging work,
which is how ``extra=`` came to be silently dropped in text mode without anyone
noticing: the JSON sink merged structured fields and the plain sink discarded
them, and the two were never compared.

The load-bearing assertions here are the pair -- *the same seven fields reach
output under both formatter configurations* -- and the empty-``extra=`` case,
which pins the behaviour of every log line the bot emits today.
"""

from __future__ import annotations

import json
import logging
import os
from decimal import Decimal

import pytest

from trading_bot.config.models import LoggingConfig
from trading_bot.utils.logger import (
    _DATE_FORMAT,
    _PLAIN_FORMAT,
    JsonFormatter,
    PlainFormatter,
    setup_logging,
    surplus_fields,
)

#: A risk intent's structured fields: four Decimals, one value containing spaces
#: and a colon, one plain string, one enum-ish token. Shaped like what M4 emits.
SEVEN_FIELDS: dict[str, object] = {
    "symbol": "BTCUSDT",
    "action": "BUY",
    "size": Decimal("50.000"),
    "stop": Decimal("98.00"),
    "take_profit": Decimal("104.00"),
    "refusal_reason": "no trade (fixed_fraction): below min_notional",
    "rule_fired": "cooldown",
}


def make_record(**extra: object) -> logging.LogRecord:
    """A record with a pinned timestamp so rendered output is deterministic."""
    record = logging.LogRecord(
        "trading_bot.probe", logging.INFO, "/p.py", 42, "signal %s accepted", ("BTCUSDT",), None
    )
    record.created = 1_700_000_000.0
    record.msecs = 0.0
    for key, value in extra.items():
        setattr(record, key, value)
    return record


# --------------------------------------------------------------------------
# The pair: both sinks must carry the same fields
# --------------------------------------------------------------------------
class TestBothSinksCarryStructuredFields:
    def test_json_sink_carries_all_seven(self) -> None:
        payload = json.loads(JsonFormatter().format(make_record(**SEVEN_FIELDS)))
        for key, value in SEVEN_FIELDS.items():
            assert payload[key] == str(value), f"{key} missing or altered in JSON output"

    def test_plain_sink_carries_all_seven(self) -> None:
        """The behaviour this change exists to add. Before it, every one of these
        was silently dropped -- the call site looked identical and the output was
        lossy."""
        line = PlainFormatter(_PLAIN_FORMAT, _DATE_FORMAT).format(make_record(**SEVEN_FIELDS))
        for key in SEVEN_FIELDS:
            assert f"{key}=" in line, f"{key} silently dropped from plain output"

    @pytest.mark.parametrize(
        ("field", "rendered"),
        [
            ("size", "50.000"),
            ("stop", "98.00"),
            ("take_profit", "104.00"),
        ],
    )
    def test_decimal_renders_exactly_in_both_sinks(self, field: str, rendered: str) -> None:
        """Exact string equality, not float tolerance: ``Decimal("98.00")`` must
        render ``98.00`` -- never ``98.0``, never a float repr. Trailing zeros are
        significant, they are what the exchange's tick size was expressed in."""
        record = make_record(**SEVEN_FIELDS)

        payload = json.loads(JsonFormatter().format(record))
        assert payload[field] == rendered
        assert isinstance(payload[field], str)  # a JSON *string*, never a number

        line = PlainFormatter(_PLAIN_FORMAT, _DATE_FORMAT).format(make_record(**SEVEN_FIELDS))
        assert f"{field}={rendered}" in line

    def test_value_with_spaces_is_quoted_not_truncated(self) -> None:
        """``refusal_reason`` carries a sentence. Unquoted it would split into
        tokens and the reason would be unparseable."""
        line = PlainFormatter(_PLAIN_FORMAT, _DATE_FORMAT).format(make_record(**SEVEN_FIELDS))
        assert 'refusal_reason="no trade (fixed_fraction): below min_notional"' in line

    def test_insertion_order_is_preserved_not_sorted(self) -> None:
        line = PlainFormatter(_PLAIN_FORMAT, _DATE_FORMAT).format(make_record(**SEVEN_FIELDS))
        positions = [line.index(f"{key}=") for key in SEVEN_FIELDS]
        assert positions == sorted(positions), "field order was not preserved"


# --------------------------------------------------------------------------
# The empty case: today's behaviour for every log line the bot emits
# --------------------------------------------------------------------------
class TestNoExtraIsUnchanged:
    """Every ``get_logger`` call site in ``src/`` passes no ``extra=``, so this
    path *is* the bot's entire current logging behaviour. A stray separator or a
    trailing space here regresses every line it writes."""

    def test_plain_output_has_no_trailing_separator(self) -> None:
        """**The `pid=` column arrived at M5g-19 and this baseline moved with it.**

        Two concurrent bots wrote to one file on 2026-08-27 with nothing saying
        which record came from which, and the resulting doubling read as three
        different defects before it read as two processes. The column is not
        decoration.

        `os.getpid()` rather than a literal: the value is whatever process runs
        the suite, and pinning a literal would fail on every machine but one.
        """
        line = PlainFormatter(_PLAIN_FORMAT, _DATE_FORMAT).format(make_record())
        assert line == (
            f"2023-11-15 04:13:20 | INFO     | pid={os.getpid()} | "
            "trading_bot.probe | signal BTCUSDT accepted"
        )
        assert not line.endswith(" ")

    def test_rich_message_column_is_bare(self) -> None:
        """RichHandler renders its own columns, so its formatter emits the message
        alone -- with nothing appended when there are no extras."""
        assert PlainFormatter("%(message)s").format(make_record()) == "signal BTCUSDT accepted"

    def test_json_output_has_only_the_base_keys(self) -> None:
        """`pid` joined the base set at M5g-19, and it needed its OWN line in
        `JsonFormatter.format` to do so.

        It cannot arrive through `extra=`: `process` is a native `LogRecord`
        attribute, so `surplus_fields` filters it out. That is why the two sinks
        carry two independent edits, and why a two-sink agreement test exists in
        `test_modes.py` to catch them disagreeing.
        """
        payload = json.loads(JsonFormatter().format(make_record()))
        assert set(payload) == {"time", "level", "logger", "pid", "message"}
        assert payload["pid"] == os.getpid()

    def test_formatter_side_effects_are_not_reported_as_fields(self) -> None:
        """``logging.Formatter.format`` assigns ``message`` and ``asctime`` onto
        the record while rendering. A reserved set built from a *fresh* record
        does not contain them, so they came back as caller extras -- the plain
        line ended with ``message="..." asctime="..."``. This is a regression
        test for that exact defect.
        """
        record = make_record()
        logging.Formatter(_PLAIN_FORMAT, _DATE_FORMAT).format(record)  # mutates record
        assert surplus_fields(record) == {}


# --------------------------------------------------------------------------
# Wiring: which formatter each of the three plain sinks receives
# --------------------------------------------------------------------------
class TestHandlerWiring:
    def test_rich_console_gets_a_plain_formatter(self) -> None:
        setup_logging(LoggingConfig(console=True, file={"enabled": False, "json": False}))
        handler = logging.getLogger().handlers[0]
        assert type(handler).__name__ == "RichHandler"
        assert isinstance(handler.formatter, PlainFormatter)

    def test_stream_fallback_gets_a_plain_formatter(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """With ``rich`` unavailable the console falls back to a StreamHandler.
        That third sink is easy to miss -- it only appears when an import fails."""
        import builtins

        real_import = builtins.__import__

        def no_rich(name: str, *args: object, **kwargs: object) -> object:
            if name.startswith("rich"):
                raise ImportError("rich disabled for this test")
            return real_import(name, *args, **kwargs)  # type: ignore[arg-type]

        monkeypatch.setattr(builtins, "__import__", no_rich)
        setup_logging(LoggingConfig(console=True, file={"enabled": False, "json": False}))
        handler = logging.getLogger().handlers[0]
        assert type(handler) is logging.StreamHandler
        assert isinstance(handler.formatter, PlainFormatter)

    def test_file_sink_gets_plain_or_json_per_config(self, tmp_path: object) -> None:
        path = f"{tmp_path}/bot.log"
        setup_logging(
            LoggingConfig(console=False, file={"enabled": True, "json": False, "path": path})
        )
        assert isinstance(logging.getLogger().handlers[0].formatter, PlainFormatter)

        setup_logging(
            LoggingConfig(console=False, file={"enabled": True, "json": True, "path": path})
        )
        assert isinstance(logging.getLogger().handlers[0].formatter, JsonFormatter)


# --------------------------------------------------------------------------
# The KeyError guard -- enforced by the stdlib, not by convention
# --------------------------------------------------------------------------
class TestReservedNames:
    @pytest.mark.parametrize("name", ["name", "message", "asctime", "module", "args", "msg"])
    def test_reserved_field_names_raise_at_the_call_site(self, name: str) -> None:
        log = logging.getLogger(f"probe.reserved.{name}")
        log.handlers = [logging.NullHandler()]
        log.propagate = False
        with pytest.raises(KeyError, match="Attempt to overwrite"):
            log.info("x", extra={name: "x"})

    def test_none_of_the_intent_fields_are_reserved(self) -> None:
        log = logging.getLogger("probe.intent")
        log.handlers = [logging.NullHandler()]
        log.propagate = False
        log.info("x", extra=SEVEN_FIELDS)  # must not raise
