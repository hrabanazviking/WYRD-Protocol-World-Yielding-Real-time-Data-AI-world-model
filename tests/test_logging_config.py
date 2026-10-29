"""Phase E5 pinning tests for wyrdforge.logging_config.

The E5 logging surface is opt-in and additive: configuring works,
the environment overrides resolve, bad values raise, output is
parseable in both formats, and key modules emit through named
``__name__`` loggers under the wyrdforge tree.  Global logging
state touched here is restored after every test so the rest of the
suite sees the un-configured defaults it expects.
"""

from __future__ import annotations

import io
import json
import logging

import pytest

from wyrdforge.logging_config import (
    JsonFormatter,
    configure_logging,
    default_config,
)


@pytest.fixture(autouse=True)
def _restore_wyrdforge_logger():
    logger = logging.getLogger("wyrdforge")
    old_handlers = list(logger.handlers)
    old_level = logger.level
    old_propagate = logger.propagate
    yield
    logger.handlers = old_handlers
    logger.level = old_level
    logger.propagate = old_propagate


def test_default_config_shape_and_defaults():
    config = default_config()
    assert config["version"] == 1
    assert config["disable_existing_loggers"] is False
    wyrd = config["loggers"]["wyrdforge"]
    assert wyrd["level"] == logging.INFO
    assert wyrd["handlers"] == ["console"]
    assert wyrd["propagate"] is False
    # No root-logger configuration: a host app's setup is untouched.
    assert "root" not in config


def test_env_overrides(monkeypatch):
    monkeypatch.setenv("WYRD_LOG_LEVEL", "debug")
    monkeypatch.setenv("WYRD_LOG_FORMAT", "json")
    config = default_config()
    assert config["loggers"]["wyrdforge"]["level"] == logging.DEBUG
    assert config["handlers"]["console"]["formatter"] == "json"


def test_explicit_arguments_beat_env(monkeypatch):
    monkeypatch.setenv("WYRD_LOG_LEVEL", "DEBUG")
    monkeypatch.setenv("WYRD_LOG_FORMAT", "json")
    config = default_config(level="ERROR", fmt="text")
    assert config["loggers"]["wyrdforge"]["level"] == logging.ERROR
    assert config["handlers"]["console"]["formatter"] == "text"


def test_unknown_level_and_format_raise():
    with pytest.raises(ValueError, match="unknown log level"):
        default_config(level="CHATTY")
    with pytest.raises(ValueError, match="unknown log format"):
        default_config(fmt="yaml")


def test_configure_text_output_through_named_logger():
    stream = io.StringIO()
    configure_logging(level="DEBUG", fmt="text", stream=stream)
    logging.getLogger("wyrdforge.runtime.events").info("bus started")
    out = stream.getvalue()
    assert "wyrdforge.runtime.events" in out
    assert "bus started" in out
    assert "INFO" in out


def test_configure_json_output_is_parseable():
    stream = io.StringIO()
    configure_logging(level="DEBUG", fmt="json", stream=stream)
    logging.getLogger("wyrdforge.persistence.world_store").warning("load note")
    lines = [line for line in stream.getvalue().splitlines() if line.strip()]
    assert len(lines) == 1
    payload = json.loads(lines[0])
    assert payload["logger"] == "wyrdforge.persistence.world_store"
    assert payload["level"] == "WARNING"
    assert payload["message"] == "load note"
    assert payload["ts"]  # UTC ISO-8601 timestamp present


def test_configure_respects_level():
    stream = io.StringIO()
    configure_logging(level="ERROR", stream=stream)
    log = logging.getLogger("wyrdforge.oracle.passive_oracle")
    log.info("below the configured level")
    log.error("at the configured level")
    out = stream.getvalue()
    assert "below the configured level" not in out
    assert "at the configured level" in out


def test_json_formatter_includes_exception():
    stream = io.StringIO()
    configure_logging(fmt="json", stream=stream)
    log = logging.getLogger("wyrdforge.test_exc")
    try:
        raise RuntimeError("boom")
    except RuntimeError:
        log.exception("failed")
    payload = json.loads(stream.getvalue().strip())
    assert "RuntimeError: boom" in payload["exc_info"]
    assert isinstance(JsonFormatter(), logging.Formatter)


def test_key_modules_emit_through_named_loggers():
    """Modules that log use getLogger(__name__) under the wyrdforge tree."""
    import wyrdforge.bridges.http_api as http_api
    import wyrdforge.persistence.bond_store as bond_store
    import wyrdforge.runtime.events as events
    import wyrdforge.runtime.turn_loop as turn_loop

    for module in (http_api, bond_store, events, turn_loop):
        named = getattr(module, "logger", None) or getattr(module, "log")
        assert named.name == module.__name__
        assert named.name.startswith("wyrdforge.")
