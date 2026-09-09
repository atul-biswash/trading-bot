"""Centralised logging setup.

Call :func:`setup_logging` once at startup, then use :func:`get_logger` (or the
stdlib ``logging.getLogger``) everywhere else. Supports a console handler
(pretty via ``rich`` when installed, plain otherwise), an optional rotating file
handler, and an optional JSON-lines format for machine ingestion.
"""

from __future__ import annotations

import json
import logging
import time
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover - typing only
    from trading_bot.config.models import LoggingConfig

#: **``%(process)d`` is here so interleaved processes are separable.** One log
#: file carried two concurrent bots on 2026-08-27 with nothing in it saying
#: which record came from which, and the doubling that resulted read as a
#: duplicated subscriber, a duplicated handler and a duplicated candle delivery
#: before it read as two processes.
#:
#: ``record.process`` rather than a record factory: the stdlib already sets it
#: to ``os.getpid()`` on every record, so a factory would be a second source of
#: truth for a value that exists. The JSON sink needs its own line -- ``process``
#: is a native ``LogRecord`` attribute and is therefore filtered out of
#: ``surplus_fields``, so it cannot arrive there via ``extra=``.
_PLAIN_FORMAT = "%(asctime)s | %(levelname)-8s | pid=%(process)d | %(name)s | %(message)s"
#: **ISO-8601 IN UTC, WITH THE ``Z`` AS PART OF THE FORMAT.** It read
#: ``"%Y-%m-%d %H:%M:%S"`` until M5h -- LOCAL time, with nothing saying so.
#:
#: **A LINE AND ITS OWN FIELDS WERE IN DIFFERENT TIMEZONES**, silently. This
#: host runs at ``+0600``, and one real record read:
#:
#:     2026-09-09 05:20:02 ... candle_time=2026-09-08T23:19:59.999000+00:00
#:
#: -- a line stamped the 9th carrying a field explicitly on the 8th. The
#: ``Ledger`` keys on UTC DAYS, so which day a booking belongs to is decided by
#: a clock the log did not report. Five closes that read as one day were four on
#: UTC 09-08 and one on 09-09; a full investigation followed into a defect that
#: did not exist, and the ledger had been correct throughout.
#:
#: The ``Z`` is a literal in the format string rather than ``%z``, which is not
#: portable over the ``struct_time`` that :meth:`logging.Formatter.formatTime`
#: passes to ``time.strftime`` -- and a ``%z`` that rendered empty would restore
#: the ambiguity while looking like it had been fixed.
#:
#: Seconds precision is unchanged. The defect was the missing zone, not the
#: missing milliseconds, and widening precision here would be a second change.
_DATE_FORMAT = "%Y-%m-%dT%H:%M:%SZ"
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


class _UtcFormatter(logging.Formatter):
    """Base that renders every timestamp in UTC. **ONE definition, two sinks.**

    ``logging.Formatter.converter`` defaults to ``time.localtime``, and both
    formatters below reach it through :meth:`formatTime` -- the plain one via
    ``%(asctime)s``, the JSON one by calling it directly. So the timezone was
    decided in ONE place already; it was simply the wrong one, and nothing said
    which.

    **A shared base rather than the attribute on each class**, because the rule
    is *"the two sinks agree on the same record"* and two copies of it are two
    things to keep true. `CLAUDE.md` records the prior instance of exactly this
    class of defect -- the sinks disagreeing silently on how a ``str, Enum``
    rendered -- and the remedy there was the same: make the agreement
    structural rather than maintained.

    ``staticmethod`` because ``converter`` is called as ``self.converter(secs)``
    and a bare function assigned to a class attribute would bind ``self`` as its
    first argument.
    """

    converter = staticmethod(time.gmtime)


class JsonFormatter(_UtcFormatter):
    """Render each record as a single JSON object (one line)."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, object] = {
            "time": self.formatTime(record, _DATE_FORMAT),
            "level": record.levelname,
            "logger": record.name,
            # Explicit, because `surplus_fields` filters every native
            # `LogRecord` attribute and `process` is one -- so this cannot
            # arrive through `extra=`. Same value the plain sinks render from
            # `%(process)d`; the two-sink agreement test pins that.
            "pid": record.process,
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


class PlainFormatter(_UtcFormatter):
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

    **RICH'S OWN TIME COLUMN IS STILL LOCAL, AND IS THE ONE TIMESTAMP THIS
    PROJECT DOES NOT RENDER.** Its format string carries no ``%(asctime)s``, so
    M5h's UTC change cannot reach it -- Rich draws that column from its own
    console clock. Left alone rather than fixed, for two reasons stated rather
    than assumed: ``rich`` is NOT installed in this environment, so the branch
    does not execute and a change to it could not be exercised by any test here;
    and it is CONSOLE-ONLY, where the durable record -- the rotating file, which
    is the only evidence a finished run leaves -- goes through
    :class:`PlainFormatter` or :class:`JsonFormatter` and is now UTC.

    So on a machine with ``rich`` installed the console shows local time and the
    file shows UTC. That is a real inconsistency and it is named here rather
    than discovered later; closing it means taking the column over with
    ``show_time=False``, which is a change to an untestable branch and belongs
    to whoever can run it.
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
    """Return a module logger. Falls back to a basic config if setup was skipped.

    **THE FALLBACK BUILDS OUR FORMATTER, AND IT HAS TO.** Passing ``format=`` and
    ``datefmt=`` to :func:`logging.basicConfig` makes it construct a BARE
    ``logging.Formatter``, whose ``converter`` is ``time.localtime`` -- so
    ``_DATE_FORMAT``'s trailing ``Z`` would be stamped onto a LOCAL time. That
    is worse than the defect this commit fixes: an unmarked local timestamp is
    merely ambiguous, where one marked ``Z`` is a positive assertion that is
    false, and a reader doing UTC arithmetic on it would be wrong by the host's
    offset with nothing to notice.

    Handing ``basicConfig`` a configured handler instead keeps every timestamp
    this project renders inside :class:`_UtcFormatter`.
    """
    if not _configured:
        handler = logging.StreamHandler()
        handler.setFormatter(PlainFormatter(_PLAIN_FORMAT, _DATE_FORMAT))
        logging.basicConfig(level=logging.INFO, handlers=[handler])
    return logging.getLogger(name)
