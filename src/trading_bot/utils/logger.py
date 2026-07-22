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
        for key, value in record.__dict__.items():
            if key not in logging.LogRecord("", 0, "", 0, "", (), None).__dict__:
                payload.setdefault(key, value)
        return json.dumps(payload, default=str)


def _console_handler(use_json: bool) -> logging.Handler:
    if not use_json:
        try:
            from rich.logging import RichHandler

            return RichHandler(rich_tracebacks=True, show_path=False)
        except ImportError:
            pass
    handler = logging.StreamHandler()
    handler.setFormatter(
        JsonFormatter() if use_json else logging.Formatter(_PLAIN_FORMAT, _DATE_FORMAT)
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
            else logging.Formatter(_PLAIN_FORMAT, _DATE_FORMAT)
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
