"""Centralised logging setup.

Call :func:`setup_logging` once at startup, then use :func:`get_logger` (or the
stdlib ``logging.getLogger``) everywhere else. Supports a console handler
(pretty via ``rich`` when installed, plain otherwise), an optional rotating file
handler, and an optional JSON-lines format for machine ingestion.
"""

from __future__ import annotations

import json
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover - typing only
    from trading_bot.config.models import LoggingConfig

_PLAIN_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"
_configured = False

#: Attribute names a ``LogRecord`` carries natively, computed once at import from
#: one synthesised record. Anything on a record that is *not* in this set arrived
#: through ``logger.info(..., extra={...})`` and is a structured field.
#:
#: ``message`` and ``asctime`` are added explicitly because they do not exist on a
#: fresh record -- ``logging.Formatter.format`` *assigns* them to the record as a
#: side effect while rendering. A formatter that calls ``super().format()`` and
#: then inspects the record therefore sees two attributes that were not there
#: when it started, and would report the message back as one of its own extras.
#: This exact set is what ``Logger.makeRecord`` refuses to let ``extra=``
#: overwrite, so mirroring it keeps both ends of the contract agreeing.
#:
#: Snapshotting is a deliberate narrowing: the set is fixed at import rather than
#: recomputed per call. Nothing in the stdlib varies these per record, so the two
#: definitions agree today -- but they are different definitions, and this one
#: would not notice an interpreter adding an attribute mid-process.
_RESERVED_RECORD_KEYS: frozenset[str] = frozenset(
    logging.LogRecord("", 0, "", 0, "", (), None).__dict__
) | {"message", "asctime"}

#: Characters that force a logfmt value to be quoted rather than written bare.
_LOGFMT_NEEDS_QUOTING = (" ", "\t", "\n", "\r", "=", '"', "'")


def surplus_fields(record: logging.LogRecord) -> dict[str, object]:
    """Structured fields attached to ``record`` via ``extra=``, in insertion order.

    ``Logger.makeRecord`` refuses to overwrite a native attribute -- it raises
    ``KeyError("Attempt to overwrite 'name' in LogRecord")`` at the *call site* --
    so anything left over here is unambiguously caller-supplied.
    """
    return {
        key: value for key, value in record.__dict__.items() if key not in _RESERVED_RECORD_KEYS
    }


class JsonFormatter(logging.Formatter):
    """Render each record as a single JSON object (one line)."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, object] = {
            "time": self.formatTime(record, _DATE_FORMAT),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        # Include any structured extras attached via `logger.info(..., extra=...)`.
        for key, value in surplus_fields(record).items():
            payload.setdefault(key, value)
        # `default=str` is what lets a Decimal through as an exact string rather
        # than raising TypeError. It is a catch-all, so an unrecognised object
        # lands as its repr instead of failing -- see CLAUDE.md.
        return json.dumps(payload, default=str)


class PlainFormatter(logging.Formatter):
    """Text formatter that appends ``extra=`` fields as logfmt key/value pairs.

    Without this, structured fields are **silently dropped** in text mode: the
    format string names four attributes and nothing renders the rest, so the same
    call that produces a complete JSON line produces a lossy text one. That
    asymmetry is invisible at the call site, which is what makes it dangerous.

    Values are rendered with ``str()``, matching the JSON sink's ``default=str``,
    so a ``Decimal`` appears as ``50.000`` in both -- exact, never a float.
    Insertion order is preserved and never sorted: the caller's ordering is
    information, and re-sorting would scramble a deliberately-ordered intent line.
    """

    def format(self, record: logging.LogRecord) -> str:
        base = super().format(record)
        surplus = surplus_fields(record)
        if not surplus:
            # No separator, no trailing space: a record with no extras must render
            # byte-identically to how it did before this formatter existed.
            return base
        return f"{base} {' '.join(_logfmt(k, v) for k, v in surplus.items())}"


def _logfmt(key: str, value: object) -> str:
    """One ``key=value`` pair, quoted only when the value would be ambiguous."""
    text = str(value)
    if text == "" or any(char in text for char in _LOGFMT_NEEDS_QUOTING):
        return f"{key}={json.dumps(text)}"
    return f"{key}={text}"


def _console_handler(use_json: bool) -> logging.Handler:
    """Build the console handler. Three sinks exist here, not two.

    ``RichHandler`` renders the timestamp, level and logger name itself, so it
    gets ``PlainFormatter("%(message)s")`` -- enough to append structured fields
    without duplicating the columns Rich already owns. It previously carried *no*
    formatter at all, falling back to the stdlib default.
    """
    if not use_json:
        try:
            from rich.logging import RichHandler
        except ImportError:
            pass
        else:
            rich_handler = RichHandler(rich_tracebacks=True, show_path=False)
            rich_handler.setFormatter(PlainFormatter("%(message)s"))
            return rich_handler
    handler = logging.StreamHandler()
    handler.setFormatter(
        JsonFormatter() if use_json else PlainFormatter(_PLAIN_FORMAT, _DATE_FORMAT)
    )
    return handler


def setup_logging(config: LoggingConfig) -> None:
    """Configure the root logger from a :class:`LoggingConfig`. Idempotent."""
    global _configured
    root = logging.getLogger()
    root.setLevel(config.level.upper())

    # Clear existing handlers so re-configuration (e.g. in tests) is clean.
    for handler in list(root.handlers):
        root.removeHandler(handler)

    if config.console:
        root.addHandler(_console_handler(config.file.json_format))

    if config.file.enabled:
        path = Path(config.file.path)
        path.parent.mkdir(parents=True, exist_ok=True)
        file_handler = RotatingFileHandler(
            path,
            maxBytes=config.file.max_bytes,
            backupCount=config.file.backup_count,
            encoding="utf-8",
        )
        file_handler.setFormatter(
            JsonFormatter()
            if config.file.json_format
            else PlainFormatter(_PLAIN_FORMAT, _DATE_FORMAT)
        )
        root.addHandler(file_handler)

    # Quiet down noisy third-party libraries.
    logging.getLogger("websockets").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    _configured = True


def get_logger(name: str) -> logging.Logger:
    """Return a module logger. Falls back to a basic config if setup was skipped."""
    if not _configured:
        logging.basicConfig(level=logging.INFO, format=_PLAIN_FORMAT, datefmt=_DATE_FORMAT)
    return logging.getLogger(name)
