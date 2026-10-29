"""Structured logging configuration for wyrdforge (Phase E5).

Before E5 the package shipped no logging configuration at all:
modules that log do so through ``logging.getLogger(__name__)`` (the
right habit), but an operator had no supported way to set levels or
formats for the ``wyrdforge`` logger tree — output shape depended on
whatever the host application happened to configure, and with no
configuration at all Python's last-resort handler dropped everything
below WARNING.

This module is the supported surface.  It is deliberately small —
one :func:`configure_logging` call over stdlib ``logging.config`` —
and strictly opt-in: importing wyrdforge never configures logging,
and existing callers who never call :func:`configure_logging` see no
behaviour change.

Usage::

    from wyrdforge.logging_config import configure_logging

    configure_logging()                       # INFO, text format
    configure_logging(level="DEBUG")          # explicit level wins
    configure_logging(fmt="json")             # one JSON object per line

Environment overrides (used when the matching argument is omitted):

* ``WYRD_LOG_LEVEL`` — a stdlib level name (``DEBUG``, ``INFO``,
  ``WARNING``, ``ERROR``, ``CRITICAL``; case-insensitive, numeric
  levels also accepted).  Default: ``INFO``.
* ``WYRD_LOG_FORMAT`` — ``text`` (default) or ``json``.

An unknown level or format — passed explicitly or via the
environment — raises :class:`ValueError` naming the bad value;
silently falling back would hide exactly the operator typo this
surface exists to make visible.

The configuration applies to the ``wyrdforge`` logger (children such
as ``wyrdforge.runtime.events`` inherit it), writes to stderr, and
never disables existing loggers, so a host application's own logging
setup keeps working beside it.
"""

from __future__ import annotations

import json
import logging
import logging.config
import os
from datetime import datetime, timezone
from typing import IO

#: Environment variable carrying the log level override.
LOG_LEVEL_ENV_VAR = "WYRD_LOG_LEVEL"

#: Environment variable carrying the log format override.
LOG_FORMAT_ENV_VAR = "WYRD_LOG_FORMAT"

#: Level used when neither the argument nor the environment names one.
DEFAULT_LEVEL = "INFO"

#: Format used when neither the argument nor the environment names one.
DEFAULT_FORMAT = "text"

_FORMATS = ("text", "json")

_TEXT_FORMAT = "%(asctime)s %(levelname)-8s %(name)s: %(message)s"


class JsonFormatter(logging.Formatter):
    """Format each record as one JSON object per line.

    Fields: ``ts`` (UTC ISO-8601), ``level``, ``logger``,
    ``message``, and ``exc_info`` when the record carries exception
    information.  Stable field names are the point: log pipelines
    can parse every wyrdforge line the same way.
    """

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)


def _resolve_level(level: str | int | None) -> int:
    """Resolve an explicit level or the WYRD_LOG_LEVEL override to an int."""
    raw: str | int | None = level
    if raw is None:
        raw = os.environ.get(LOG_LEVEL_ENV_VAR) or DEFAULT_LEVEL
    if isinstance(raw, int):
        return raw
    name = str(raw).strip().upper()
    if name.isdigit():
        return int(name)
    resolved = logging.getLevelName(name)
    if not isinstance(resolved, int):
        raise ValueError(
            f"unknown log level {raw!r} (expected a stdlib level name "
            f"such as DEBUG/INFO/WARNING/ERROR/CRITICAL)"
        )
    return resolved


def _resolve_format(fmt: str | None) -> str:
    raw = fmt if fmt is not None else (os.environ.get(LOG_FORMAT_ENV_VAR) or DEFAULT_FORMAT)
    resolved = str(raw).strip().lower()
    if resolved not in _FORMATS:
        raise ValueError(
            f"unknown log format {raw!r} (expected one of: {', '.join(_FORMATS)})"
        )
    return resolved


def default_config(
    level: str | int | None = None,
    fmt: str | None = None,
    *,
    stream: IO[str] | None = None,
) -> dict:
    """Build the dictConfig dictionary :func:`configure_logging` applies.

    Pure: builds and validates the configuration without touching
    global logging state, so callers (and tests) can inspect exactly
    what would be applied.  ``stream`` redirects the console handler
    (default: stderr at apply time).
    """
    resolved_level = _resolve_level(level)
    resolved_format = _resolve_format(fmt)
    handler: dict = {
        "class": "logging.StreamHandler",
        "formatter": resolved_format,
    }
    if stream is not None:
        handler["stream"] = stream
    else:
        handler["stream"] = "ext://sys.stderr"
    return {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "text": {"format": _TEXT_FORMAT},
            "json": {"()": JsonFormatter},
        },
        "handlers": {"console": handler},
        "loggers": {
            "wyrdforge": {
                "level": resolved_level,
                "handlers": ["console"],
                "propagate": False,
            }
        },
    }


def configure_logging(
    level: str | int | None = None,
    fmt: str | None = None,
    *,
    stream: IO[str] | None = None,
) -> dict:
    """Configure the ``wyrdforge`` logger tree and return the applied config.

    Opt-in and additive: only the ``wyrdforge`` logger gains a
    handler and a level; the root logger and any host-application
    loggers are untouched, and existing loggers are never disabled.
    Calling it again replaces the previous wyrdforge configuration.
    """
    config = default_config(level, fmt, stream=stream)
    logging.config.dictConfig(config)
    return config


__all__ = [
    "DEFAULT_FORMAT",
    "DEFAULT_LEVEL",
    "LOG_FORMAT_ENV_VAR",
    "LOG_LEVEL_ENV_VAR",
    "JsonFormatter",
    "configure_logging",
    "default_config",
]
