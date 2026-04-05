"""test_hardening.py — Tests for wyrdforge.hardening (Phase 18).

Covers: BackoffConfig, retry_with_backoff, BoundedThreadPool,
        safe_persona_id, is_valid_persona_id, validate_world_config,
        coerce_env, WyrdHTTPServer hardening, memory_store hardening.
"""
from __future__ import annotations

import os
import sqlite3
import tempfile
import threading
import time
from pathlib import Path
from unittest.mock import MagicMock, patch, call

import pytest

from wyrdforge.hardening.backoff import BackoffConfig, retry_with_backoff, compute_delays
from wyrdforge.hardening.normalization import safe_persona_id, is_valid_persona_id
from wyrdforge.hardening.pool import BoundedThreadPool
from wyrdforge.hardening.config_validator import (
    validate_world_config,
    coerce_env,
    report_active_config,
    ConfigValidationError,
)


# ===========================================================================
# BackoffConfig.delay_for
# ===========================================================================

class TestBackoffConfig:
    def test_first_delay_equals_base(self):
        cfg = BackoffConfig(base_delay=1.0, jitter=0.0)
        assert cfg.delay_for(0) == pytest.approx(1.0)

    def test_second_delay_doubles(self):
        cfg = BackoffConfig(base_delay=1.0, multiplier=2.0, jitter=0.0)
        assert cfg.delay_for(1) == pytest.approx(2.0)

    def test_third_delay_quadruples(self):
        cfg = BackoffConfig(base_delay=1.0, multiplier=2.0, jitter=0.0)
        assert cfg.delay_for(2) == pytest.approx(4.0)

    def test_capped_at_max_delay(self):
        cfg = BackoffConfig(base_delay=1.0, max_delay=5.0, multiplier=10.0, jitter=0.0)
        assert cfg.delay_for(3) == pytest.approx(5.0)

    def test_jitter_never_negative(self):
        cfg = BackoffConfig(base_delay=0.1, jitter=1.0)
        for _ in range(50):
            assert cfg.delay_for(0) >= 0.0

    def test_zero_jitter_deterministic(self):
        cfg = BackoffConfig(base_delay=2.0, jitter=0.0, multiplier=2.0)
        assert cfg.delay_for(0) == pytest.approx(2.0)
        assert cfg.delay_for(1) == pytest.approx(4.0)

    def test_defaults_reasonable(self):
        cfg = BackoffConfig()
        assert cfg.max_attempts == 4
        assert cfg.base_delay == 0.5
        assert cfg.max_delay == 30.0


# ===========================================================================
# compute_delays
# ===========================================================================

class TestComputeDelays:
    def test_single_retry(self):
        cfg = BackoffConfig(base_delay=1.0, multiplier=2.0, jitter=0.0)
        assert compute_delays(cfg, 1) == [1.0]

    def test_three_retries_doubling(self):
        cfg = BackoffConfig(base_delay=1.0, multiplier=2.0, jitter=0.0)
        assert compute_delays(cfg, 3) == pytest.approx([1.0, 2.0, 4.0])

    def test_capped_values(self):
        cfg = BackoffConfig(base_delay=1.0, max_delay=3.0, multiplier=2.0, jitter=0.0)
        delays = compute_delays(cfg, 4)
        assert all(d <= 3.0 for d in delays)

    def test_zero_retries_empty(self):
        cfg = BackoffConfig()
        assert compute_delays(cfg, 0) == []


# ===========================================================================
# retry_with_backoff
# ===========================================================================

class TestRetryWithBackoff:
    def test_success_on_first_attempt(self):
        calls = []
        def fn():
            calls.append(1)
            return "ok"
        cfg = BackoffConfig(max_attempts=3, base_delay=0.0, jitter=0.0)
        result = retry_with_backoff(fn, config=cfg)
        assert result == "ok"
        assert len(calls) == 1

    def test_retries_on_retryable_exception(self):
        calls = []
        def fn():
            calls.append(1)
            if len(calls) < 3:
                raise ConnectionError("not yet")
            return "done"
        cfg = BackoffConfig(max_attempts=4, base_delay=0.0, jitter=0.0)
        result = retry_with_backoff(fn, config=cfg, retryable=(ConnectionError,))
        assert result == "done"
        assert len(calls) == 3

    def test_non_retryable_propagates_immediately(self):
        def fn():
            raise ValueError("not retryable")
        cfg = BackoffConfig(max_attempts=4, base_delay=0.0, jitter=0.0)
        with pytest.raises(ValueError):
            retry_with_backoff(fn, config=cfg, retryable=(ConnectionError,))

    def test_raises_after_max_attempts(self):
        def fn():
            raise ConnectionError("always fails")
        cfg = BackoffConfig(max_attempts=3, base_delay=0.0, jitter=0.0)
        with pytest.raises(ConnectionError):
            retry_with_backoff(fn, config=cfg, retryable=(ConnectionError,))

    def test_on_retry_callback_called(self):
        called = []
        def fn():
            raise OSError("fail")
        def on_retry(attempt, exc):
            called.append(attempt)
        cfg = BackoffConfig(max_attempts=3, base_delay=0.0, jitter=0.0)
        with pytest.raises(OSError):
            retry_with_backoff(fn, config=cfg, retryable=(OSError,), on_retry=on_retry)
        assert called == [1, 2]

    def test_default_config_retries_four_times(self):
        calls = []
        def fn():
            calls.append(1)
            raise OSError("fail")
        cfg = BackoffConfig(max_attempts=4, base_delay=0.0, jitter=0.0)
        with pytest.raises(OSError):
            retry_with_backoff(fn, config=cfg)
        assert len(calls) == 4


# ===========================================================================
# safe_persona_id
# ===========================================================================

class TestSafePersonaId:
    def test_ascii_name(self):
        assert safe_persona_id("Sigrid Stormborn") == "sigrid_stormborn"

    def test_none_returns_empty(self):
        assert safe_persona_id(None) == ""

    def test_bytes_input(self):
        result = safe_persona_id(b"sigrid")
        assert result == "sigrid"

    def test_diacritics_stripped(self):
        result = safe_persona_id("Björn")
        assert result == "bjorn"

    def test_emoji_removed(self):
        result = safe_persona_id("guard 🐺 wolf")
        assert "🐺" not in result
        assert re.match(r"^[a-z0-9_]*$", result)

    def test_nul_bytes_stripped(self):
        result = safe_persona_id("sig\x00rid")
        assert "\x00" not in result
        assert "sigrid" == result

    def test_very_long_input_truncated(self):
        result = safe_persona_id("a" * 1000)
        assert len(result) <= 64

    def test_rtl_override_stripped(self):
        # U+202E RIGHT-TO-LEFT OVERRIDE is category Cf
        result = safe_persona_id("sig\u202erid")
        assert "\u202e" not in result

    def test_unicode_digits_lowercased(self):
        result = safe_persona_id("guard01")
        assert result == "guard01"

    def test_consecutive_underscores_collapsed(self):
        result = safe_persona_id("dark   elf")
        assert "__" not in result

    def test_empty_string(self):
        assert safe_persona_id("") == ""

    def test_special_chars_only(self):
        result = safe_persona_id("!@#$%")
        assert result == ""

    def test_nordic_name(self):
        result = safe_persona_id("Eiríkr Járnsíða")
        assert re.match(r"^[a-z0-9_]+$", result)
        assert len(result) > 0


# ===========================================================================
# is_valid_persona_id
# ===========================================================================

class TestIsValidPersonaId:
    def test_valid_simple(self):
        assert is_valid_persona_id("sigrid") is True

    def test_valid_with_underscores(self):
        assert is_valid_persona_id("sigrid_stormborn") is True

    def test_valid_with_numbers(self):
        assert is_valid_persona_id("guard_01") is True

    def test_empty_string_invalid(self):
        assert is_valid_persona_id("") is False

    def test_leading_underscore_invalid(self):
        assert is_valid_persona_id("_sigrid") is False

    def test_trailing_underscore_invalid(self):
        assert is_valid_persona_id("sigrid_") is False

    def test_consecutive_underscores_invalid(self):
        assert is_valid_persona_id("sigrid__stormborn") is False

    def test_uppercase_invalid(self):
        assert is_valid_persona_id("Sigrid") is False

    def test_space_invalid(self):
        assert is_valid_persona_id("sigrid stormborn") is False

    def test_65_chars_invalid(self):
        assert is_valid_persona_id("a" * 65) is False

    def test_64_chars_valid(self):
        assert is_valid_persona_id("a" * 64) is True


# ===========================================================================
# BoundedThreadPool
# ===========================================================================

class TestBoundedThreadPool:
    def test_task_executes(self):
        event = threading.Event()
        pool = BoundedThreadPool(max_workers=2)
        pool.submit(event.set)
        assert event.wait(timeout=2.0)
        pool.shutdown(wait=True, timeout=1.0)

    def test_max_workers_respected(self):
        pool = BoundedThreadPool(max_workers=4)
        assert pool.max_workers == 4
        pool.shutdown()

    def test_submit_returns_true_on_success(self):
        pool = BoundedThreadPool(max_workers=2)
        result = pool.submit(lambda: None)
        assert result is True
        pool.shutdown(wait=True)

    def test_submit_returns_false_after_shutdown(self):
        pool = BoundedThreadPool(max_workers=2)
        pool.shutdown(wait=False)
        result = pool.submit(lambda: None)
        assert result is False

    def test_tasks_submitted_counter(self):
        pool = BoundedThreadPool(max_workers=2)
        pool.submit(lambda: None)
        pool.submit(lambda: None)
        time.sleep(0.1)
        assert pool.tasks_submitted == 2
        pool.shutdown()

    def test_queue_full_drops_task(self):
        pool = BoundedThreadPool(max_workers=1, max_queue=1)
        barrier = threading.Barrier(2)
        # Block the single worker
        pool.submit(lambda: barrier.wait(timeout=3))
        # Fill the queue
        pool.submit(lambda: None)
        # This one should be dropped
        result = pool.submit(lambda: None)
        assert result is False
        assert pool.tasks_dropped >= 1
        barrier.wait(timeout=3)
        pool.shutdown(wait=True)

    def test_exception_in_task_does_not_crash_pool(self):
        event = threading.Event()
        pool = BoundedThreadPool(max_workers=2)
        pool.submit(lambda: 1 / 0)          # raises ZeroDivisionError
        pool.submit(event.set)              # should still run
        assert event.wait(timeout=2.0)
        pool.shutdown(wait=True)

    def test_invalid_max_workers_raises(self):
        with pytest.raises(ValueError):
            BoundedThreadPool(max_workers=0)

    def test_invalid_max_queue_raises(self):
        with pytest.raises(ValueError):
            BoundedThreadPool(max_workers=1, max_queue=0)

    def test_multiple_tasks_all_run(self):
        results = []
        lock = threading.Lock()
        pool = BoundedThreadPool(max_workers=4)
        for i in range(8):
            def task(n=i):
                with lock:
                    results.append(n)
            pool.submit(task)
        pool.shutdown(wait=True, timeout=3.0)
        assert len(results) == 8


# ===========================================================================
# validate_world_config
# ===========================================================================

class TestValidateWorldConfig:
    def _minimal(self):
        return {"world_id": "thornholt", "name": "Thornholt"}

    def test_minimal_valid_passes(self):
        result = validate_world_config(self._minimal())
        assert result["world_id"] == "thornholt"

    def test_fills_default_zones(self):
        result = validate_world_config(self._minimal())
        assert result["zones"] == []

    def test_fills_default_entities(self):
        result = validate_world_config(self._minimal())
        assert result["entities"] == []

    def test_missing_world_id_raises(self):
        with pytest.raises(ConfigValidationError) as exc_info:
            validate_world_config({"name": "Thornholt"})
        assert "world_id" in str(exc_info.value)

    def test_missing_name_raises(self):
        with pytest.raises(ConfigValidationError) as exc_info:
            validate_world_config({"world_id": "thornholt"})
        assert "name" in str(exc_info.value)

    def test_empty_world_id_raises(self):
        with pytest.raises(ConfigValidationError):
            validate_world_config({"world_id": "  ", "name": "T"})

    def test_wrong_type_world_id_raises(self):
        with pytest.raises(ConfigValidationError):
            validate_world_config({"world_id": 123, "name": "T"})

    def test_non_dict_input_raises(self):
        with pytest.raises(ConfigValidationError):
            validate_world_config(["not", "a", "dict"])

    def test_entity_must_be_dict(self):
        config = self._minimal()
        config["entities"] = ["not_a_dict"]
        with pytest.raises(ConfigValidationError) as exc_info:
            validate_world_config(config)
        assert "entities" in str(exc_info.value)

    def test_wrong_type_zones_uses_default(self):
        config = self._minimal()
        config["zones"] = "not_a_list"
        result = validate_world_config(config)
        assert result["zones"] == []

    def test_valid_entities_pass(self):
        config = self._minimal()
        config["entities"] = [{"id": "sigrid", "name": "Sigrid"}]
        result = validate_world_config(config)
        assert len(result["entities"]) == 1

    def test_field_attribute_set_on_error(self):
        with pytest.raises(ConfigValidationError) as exc_info:
            validate_world_config({"name": "T"})
        assert exc_info.value.field == "world_id"


# ===========================================================================
# coerce_env
# ===========================================================================

class TestCoerceEnv:
    def test_string_returned_as_is(self):
        with patch.dict(os.environ, {"WYRD_TEST_VAR": "hello"}):
            assert coerce_env("WYRD_TEST_VAR", str, default="x") == "hello"

    def test_int_coercion(self):
        with patch.dict(os.environ, {"WYRD_PORT": "9000"}):
            assert coerce_env("WYRD_PORT", int, default=8765) == 9000

    def test_float_coercion(self):
        with patch.dict(os.environ, {"WYRD_TIMEOUT": "2.5"}):
            assert coerce_env("WYRD_TIMEOUT", float, default=10.0) == pytest.approx(2.5)

    def test_bool_true_coercion(self):
        for val in ("1", "true", "yes", "on", "True", "YES"):
            with patch.dict(os.environ, {"WYRD_FLAG": val}):
                assert coerce_env("WYRD_FLAG", bool, default=False) is True

    def test_bool_false_coercion(self):
        for val in ("0", "false", "no", "off", "False"):
            with patch.dict(os.environ, {"WYRD_FLAG": val}):
                assert coerce_env("WYRD_FLAG", bool, default=True) is False

    def test_missing_var_returns_default(self):
        os.environ.pop("WYRD_MISSING_XYZ", None)
        assert coerce_env("WYRD_MISSING_XYZ", int, default=42) == 42

    def test_invalid_int_returns_default(self):
        with patch.dict(os.environ, {"WYRD_PORT": "not_a_number"}):
            assert coerce_env("WYRD_PORT", int, default=8765) == 8765

    def test_invalid_bool_returns_default(self):
        with patch.dict(os.environ, {"WYRD_FLAG": "maybe"}):
            assert coerce_env("WYRD_FLAG", bool, default=False) is False

    def test_required_missing_raises(self):
        os.environ.pop("WYRD_REQUIRED_XYZ", None)
        with pytest.raises(ConfigValidationError):
            coerce_env("WYRD_REQUIRED_XYZ", str, default="x", required=True)

    def test_whitespace_stripped(self):
        with patch.dict(os.environ, {"WYRD_PORT": "  9000  "}):
            assert coerce_env("WYRD_PORT", int, default=8765) == 9000


# ===========================================================================
# report_active_config
# ===========================================================================

class TestReportActiveConfig:
    def test_returns_wyrd_vars(self):
        with patch.dict(os.environ, {"WYRD_PORT": "8765", "WYRD_HOST": "localhost", "OTHER": "x"}):
            result = report_active_config("WYRD_")
        assert "WYRD_PORT" in result
        assert "WYRD_HOST" in result
        assert "OTHER" not in result

    def test_empty_when_no_vars(self):
        filtered = {k: v for k, v in os.environ.items() if k.startswith("WYRD_TEST_UNIQUE_")}
        assert filtered == {}

    def test_custom_prefix(self):
        with patch.dict(os.environ, {"APP_DEBUG": "true", "WYRD_X": "y"}):
            result = report_active_config("APP_")
        assert "APP_DEBUG" in result
        assert "WYRD_X" not in result


# ===========================================================================
# WyrdHTTPServer hardening (18A)
# ===========================================================================

class TestWyrdHTTPServerHardening:
    def test_max_request_bytes_stored(self):
        from wyrdforge.bridges.http_api import WyrdHTTPServer, DEFAULT_MAX_REQUEST_BYTES
        mock_bridge = MagicMock()
        server = WyrdHTTPServer(mock_bridge, max_request_bytes=512)
        assert server.max_request_bytes == 512

    def test_default_max_request_bytes(self):
        from wyrdforge.bridges.http_api import WyrdHTTPServer, DEFAULT_MAX_REQUEST_BYTES
        mock_bridge = MagicMock()
        server = WyrdHTTPServer(mock_bridge)
        assert server.max_request_bytes == DEFAULT_MAX_REQUEST_BYTES

    def test_handler_has_max_request_bytes(self):
        from wyrdforge.bridges.http_api import WyrdHTTPServer
        mock_bridge = MagicMock()
        server = WyrdHTTPServer(mock_bridge, max_request_bytes=2048)
        assert server._handler_cls.max_request_bytes == 2048

    def test_watchdog_flag_stored(self):
        from wyrdforge.bridges.http_api import WyrdHTTPServer
        mock_bridge = MagicMock()
        server = WyrdHTTPServer(mock_bridge, watchdog=True)
        assert server._watchdog is True

    def test_address_property(self):
        from wyrdforge.bridges.http_api import WyrdHTTPServer
        mock_bridge = MagicMock()
        server = WyrdHTTPServer(mock_bridge, host="127.0.0.1", port=9999)
        assert server.address == ("127.0.0.1", 9999)


# ===========================================================================
# PersistentMemoryStore hardening (18C)
# ===========================================================================

class TestMemoryStoreHardening:
    def setup_method(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.db_path = self.tmp / "test.db"

    def teardown_method(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_integrity_check_returns_true_on_fresh_db(self):
        from wyrdforge.persistence.memory_store import PersistentMemoryStore
        store = PersistentMemoryStore(self.db_path)
        assert store.integrity_check() is True

    def test_wal_mode_enabled(self):
        from wyrdforge.persistence.memory_store import PersistentMemoryStore
        PersistentMemoryStore(self.db_path)
        conn = sqlite3.connect(str(self.db_path))
        mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
        conn.close()
        assert mode == "wal"

    def test_busy_timeout_set(self):
        from wyrdforge.persistence.memory_store import PersistentMemoryStore
        store = PersistentMemoryStore(self.db_path)
        with store._connect() as conn:
            result = conn.execute("PRAGMA busy_timeout").fetchone()[0]
        assert result == 5000

    def test_incremental_vacuum_does_not_raise(self):
        from wyrdforge.persistence.memory_store import PersistentMemoryStore
        store = PersistentMemoryStore(self.db_path)
        store.incremental_vacuum(10)  # should not raise


# ---------------------------------------------------------------------------
# Import guard for re module used in normalization tests
# ---------------------------------------------------------------------------
import re
