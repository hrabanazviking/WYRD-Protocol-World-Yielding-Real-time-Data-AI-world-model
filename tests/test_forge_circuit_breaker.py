"""Forge tests: CircuitBreaker (Helheim Hardening).

Covers the CLOSED -> OPEN -> HALF_OPEN -> CLOSED state machine, fail-fast
semantics (open calls never invoke the wrapped callable), probe handling,
stats(), and constructor validation.
"""
from __future__ import annotations

import threading
import time

import pytest

from wyrdforge.hardening.circuit_breaker import (
    CircuitBreaker,
    CircuitOpenError,
    CircuitState,
)


def _boom():
    raise RuntimeError("dependency exploded")


def _ok(value="fine"):
    return value


# ---------------------------------------------------------------------------
# Constructor validation
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "kwargs",
    [
        {"failure_threshold": 0},
        {"failure_threshold": -1},
        {"failure_threshold": "3"},
        {"reset_timeout": -0.1},
        {"half_open_probes": 0},
        {"half_open_probes": True},
    ],
)
def test_invalid_constructor_args_raise_value_error(kwargs):
    with pytest.raises(ValueError):
        CircuitBreaker(**kwargs)


# ---------------------------------------------------------------------------
# The state machine
# ---------------------------------------------------------------------------

def test_opens_after_threshold_failures():
    breaker = CircuitBreaker(failure_threshold=3, reset_timeout=60.0)
    assert breaker.state is CircuitState.CLOSED
    for _ in range(2):
        with pytest.raises(RuntimeError):
            breaker.call(_boom)
        assert breaker.state is CircuitState.CLOSED
    with pytest.raises(RuntimeError):
        breaker.call(_boom)
    assert breaker.state is CircuitState.OPEN
    assert breaker.stats()["open_count"] == 1


def test_open_calls_raise_without_invoking_fn():
    breaker = CircuitBreaker(failure_threshold=1, reset_timeout=60.0)
    with pytest.raises(RuntimeError):
        breaker.call(_boom)
    assert breaker.state is CircuitState.OPEN

    invoked: list[bool] = []
    with pytest.raises(CircuitOpenError):
        breaker.call(lambda: invoked.append(True))
    assert invoked == []  # the callable was NEVER invoked
    assert breaker.stats()["total_rejected"] == 1


def test_original_exception_propagates_unchanged():
    breaker = CircuitBreaker(failure_threshold=5, reset_timeout=60.0)
    original = ValueError("very specific failure")
    with pytest.raises(ValueError) as exc_info:
        breaker.call(lambda: (_ for _ in ()).throw(original))
    assert exc_info.value is original


def test_success_resets_consecutive_failure_count():
    breaker = CircuitBreaker(failure_threshold=3, reset_timeout=60.0)
    for _ in range(2):
        with pytest.raises(RuntimeError):
            breaker.call(_boom)
    assert breaker.call(_ok) == "fine"  # success resets the count
    for _ in range(2):
        with pytest.raises(RuntimeError):
            breaker.call(_boom)
    assert breaker.state is CircuitState.CLOSED  # 2+2, never 3 in a row


def test_half_opens_after_reset_timeout_and_closes_after_probes():
    breaker = CircuitBreaker(
        failure_threshold=1, reset_timeout=0.05, half_open_probes=2
    )
    with pytest.raises(RuntimeError):
        breaker.call(_boom)
    assert breaker.state is CircuitState.OPEN

    time.sleep(0.08)  # let reset_timeout elapse
    assert breaker.state is CircuitState.HALF_OPEN  # timed transition

    assert breaker.call(_ok) == "fine"   # probe 1 ok...
    assert breaker.state is CircuitState.HALF_OPEN  # ...but 2 required
    assert breaker.call(_ok) == "fine"   # probe 2 ok
    assert breaker.state is CircuitState.CLOSED


def test_failed_probe_reopens_circuit():
    breaker = CircuitBreaker(
        failure_threshold=1, reset_timeout=0.05, half_open_probes=2
    )
    with pytest.raises(RuntimeError):
        breaker.call(_boom)
    time.sleep(0.08)
    assert breaker.state is CircuitState.HALF_OPEN

    with pytest.raises(RuntimeError):
        breaker.call(_boom)  # probe fails -> dependency still down
    assert breaker.state is CircuitState.OPEN
    assert breaker.stats()["open_count"] == 2


def test_stats_snapshot():
    breaker = CircuitBreaker(failure_threshold=2, reset_timeout=60.0, name="db")
    breaker.call(_ok)
    with pytest.raises(RuntimeError):
        breaker.call(_boom)
    with pytest.raises(RuntimeError):
        breaker.call(_boom)  # trips open
    with pytest.raises(CircuitOpenError):
        breaker.call(_ok)  # rejected

    stats = breaker.stats()
    assert stats["name"] == "db"
    assert stats["state"] == "open"
    assert stats["total_calls"] == 3  # the rejected call is not a call
    assert stats["total_successes"] == 1
    assert stats["total_failures"] == 2
    assert stats["total_rejected"] == 1
    assert stats["consecutive_failures"] == 0  # reset when tripped
    assert stats["open_count"] == 1
    assert stats["last_failure_at"] is not None


def test_thread_safe_under_concurrent_failures():
    breaker = CircuitBreaker(failure_threshold=10, reset_timeout=60.0)
    gate = threading.Barrier(20)
    runtime_errors: list[BaseException] = []
    open_errors: list[BaseException] = []
    lock = threading.Lock()

    def hammer():
        gate.wait(timeout=5.0)  # release all threads at once
        try:
            breaker.call(_boom)
        except RuntimeError as exc:
            with lock:
                runtime_errors.append(exc)
        except CircuitOpenError as exc:
            # Arrived after the trip: failed fast, correctly.
            with lock:
                open_errors.append(exc)

    threads = [threading.Thread(target=hammer) for _ in range(20)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=10.0)
        assert not t.is_alive()

    # Every thread got exactly one deterministic outcome — none lost,
    # none swallowed, none raised something unexpected.
    assert len(runtime_errors) + len(open_errors) == 20
    assert breaker.state is CircuitState.OPEN
    stats = breaker.stats()
    assert stats["total_failures"] == len(runtime_errors)
    assert stats["total_rejected"] == len(open_errors)
    assert stats["open_count"] == 1  # tripped exactly once, never double-counted
