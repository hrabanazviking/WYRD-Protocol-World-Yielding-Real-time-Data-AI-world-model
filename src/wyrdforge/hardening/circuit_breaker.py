"""circuit_breaker.py — Fail-fast circuit breaker for flaky dependencies.

Back-off (``backoff.py``) spaces out retries; a circuit breaker decides
whether retrying is even worth attempting. When a downstream dependency
(database, model server, bridge endpoint) fails *failure_threshold* times
in a row, the breaker opens and calls fail immediately with
:class:`CircuitOpenError` — no thread waits on a doomed call, no queue of
retries piles up behind a dead service. After *reset_timeout* seconds the
breaker half-opens and lets *half_open_probes* trial calls through; if
they succeed the circuit closes, if any fails it opens again.

Why a separate module instead of folding this into backoff: backoff is a
caller-side pacing policy ("how long do I wait between attempts"),
the breaker is a shared, thread-safe gate ("should anyone attempt at
all right now"). One breaker instance guards one dependency and is
shared across all threads that call it.

Usage::

    from wyrdforge.hardening.circuit_breaker import CircuitBreaker, CircuitOpenError

    breaker = CircuitBreaker(failure_threshold=3, reset_timeout=30.0)

    try:
        result = breaker.call(query_model_server, prompt)
    except CircuitOpenError:
        result = cached_fallback(prompt)   # degrade gracefully
"""
from __future__ import annotations

import enum
import threading
import time
from typing import Any, Callable, Dict, Optional


class CircuitState(enum.Enum):
    """The three states of a circuit breaker."""

    CLOSED = "closed"  # calls flow normally; failures are counted
    OPEN = "open"  # calls fail fast with CircuitOpenError
    HALF_OPEN = "half_open"  # trial calls (probes) are let through


class CircuitOpenError(Exception):
    """Raised by :meth:`CircuitBreaker.call` when the circuit is open.

    The wrapped callable was NOT invoked — failing fast is the point.
    Catch this at the call site and degrade to a fallback.
    """


class CircuitBreaker:
    """Thread-safe circuit breaker guarding one dependency.

    Args:
        failure_threshold: Consecutive failures that trip CLOSED -> OPEN (>= 1).
        reset_timeout:     Seconds an open circuit waits before allowing
                           probe calls (HALF_OPEN). Must be >= 0.
        half_open_probes:  Consecutive successful probes that close a
                           half-open circuit (>= 1). A single failed probe
                           re-opens the circuit immediately.
        name:              Optional label for logs/stats.

    Any exception raised by the wrapped callable counts as a failure —
    the breaker does not classify error types; use the ``retryable=``
    tuple of :func:`wyrdforge.hardening.backoff.retry_with_backoff` for
    that. The original exception always propagates to the caller; the
    breaker only *counts* it.
    """

    def __init__(
        self,
        failure_threshold: int = 3,
        reset_timeout: float = 30.0,
        half_open_probes: int = 1,
        name: Optional[str] = None,
    ) -> None:
        if isinstance(failure_threshold, bool) or not isinstance(
            failure_threshold, int
        ):
            raise ValueError("failure_threshold must be an int")
        if failure_threshold < 1:
            raise ValueError("failure_threshold must be >= 1")
        if reset_timeout < 0:
            raise ValueError("reset_timeout must be >= 0")
        if isinstance(half_open_probes, bool) or not isinstance(
            half_open_probes, int
        ):
            raise ValueError("half_open_probes must be an int")
        if half_open_probes < 1:
            raise ValueError("half_open_probes must be >= 1")

        self._failure_threshold = failure_threshold
        self._reset_timeout = float(reset_timeout)
        self._half_open_probes = half_open_probes
        self._name = name or "circuit"

        self._lock = threading.Lock()
        self._state = CircuitState.CLOSED
        self._consecutive_failures = 0
        self._consecutive_probe_successes = 0
        self._opened_at: Optional[float] = None
        # Lifetime counters — never reset, so stats() tells the story.
        self._total_calls = 0
        self._total_successes = 0
        self._total_failures = 0
        self._total_rejected = 0
        self._open_count = 0
        self._last_failure_at: Optional[float] = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @property
    def state(self) -> CircuitState:
        """Current state. Reading it also performs the timed OPEN->HALF_OPEN
        transition, so the reported state is never stale."""
        with self._lock:
            self._maybe_half_open_locked()
            return self._state

    def call(self, fn: Callable, *args: Any, **kwargs: Any) -> Any:
        """Invoke *fn(*args, **kwargs)* through the breaker.

        Raises:
            CircuitOpenError: The circuit is open — *fn* was not invoked.
            Exception: Whatever *fn* raised. Failures are counted; the
                original exception propagates unchanged.
        """
        with self._lock:
            self._maybe_half_open_locked()
            if self._state is CircuitState.OPEN:
                self._total_rejected += 1
                raise CircuitOpenError(
                    f"circuit {self._name!r} is OPEN — failing fast"
                )
            self._total_calls += 1

        # The call itself runs outside the lock — a slow dependency must
        # not serialize every thread behind this breaker.
        try:
            result = fn(*args, **kwargs)
        except Exception:
            self._on_failure()
            raise
        else:
            self._on_success()
            return result

    def stats(self) -> Dict[str, Any]:
        """Snapshot of breaker health. Safe to call from any thread."""
        with self._lock:
            self._maybe_half_open_locked()
            return {
                "name": self._name,
                "state": self._state.value,
                "consecutive_failures": self._consecutive_failures,
                "total_calls": self._total_calls,
                "total_successes": self._total_successes,
                "total_failures": self._total_failures,
                "total_rejected": self._total_rejected,
                "open_count": self._open_count,
                "last_failure_at": self._last_failure_at,
            }

    def reset(self) -> None:
        """Force the breaker back to CLOSED, clearing failure counts.

        For operator intervention and tests — not part of the normal
        state machine.
        """
        with self._lock:
            self._state = CircuitState.CLOSED
            self._consecutive_failures = 0
            self._consecutive_probe_successes = 0
            self._opened_at = None

    # ------------------------------------------------------------------
    # Internal — all *_locked helpers require self._lock
    # ------------------------------------------------------------------

    def _maybe_half_open_locked(self) -> None:
        """Timed transition: an open circuit whose reset_timeout has elapsed
        becomes half-open, allowing probe calls through."""
        if self._state is CircuitState.OPEN and self._opened_at is not None:
            if time.monotonic() - self._opened_at >= self._reset_timeout:
                self._state = CircuitState.HALF_OPEN
                self._consecutive_probe_successes = 0

    def _trip_open_locked(self) -> None:
        self._state = CircuitState.OPEN
        self._opened_at = time.monotonic()
        self._consecutive_failures = 0
        self._consecutive_probe_successes = 0
        self._open_count += 1

    def _on_success(self) -> None:
        with self._lock:
            self._total_successes += 1
            if self._state is CircuitState.HALF_OPEN:
                self._consecutive_probe_successes += 1
                if self._consecutive_probe_successes >= self._half_open_probes:
                    self._state = CircuitState.CLOSED
                    self._consecutive_failures = 0
                    self._consecutive_probe_successes = 0
            elif self._state is CircuitState.CLOSED:
                self._consecutive_failures = 0

    def _on_failure(self) -> None:
        with self._lock:
            now = time.monotonic()
            self._total_failures += 1
            self._last_failure_at = now
            if self._state is CircuitState.HALF_OPEN:
                # A failed probe means the dependency is still down.
                self._trip_open_locked()
            elif self._state is CircuitState.CLOSED:
                self._consecutive_failures += 1
                if self._consecutive_failures >= self._failure_threshold:
                    self._trip_open_locked()
            # A failure recorded while OPEN is impossible: open circuits
            # never invoke fn, so there is nothing to count.
