"""backoff.py — Exponential back-off with jitter for retryable operations.

Used by bridge fire-and-forget push loops and any code that makes HTTP calls
to WyrdHTTPServer and needs graceful retry behaviour when the server is busy
or temporarily unreachable.

Usage::

    from wyrdforge.hardening.backoff import retry_with_backoff, BackoffConfig

    cfg = BackoffConfig(max_attempts=4, base_delay=0.5, max_delay=30.0)

    result = retry_with_backoff(
        lambda: requests.post(url, json=body),
        config=cfg,
        retryable=(ConnectionError, TimeoutError),
    )
"""
from __future__ import annotations

import random
import time
from dataclasses import dataclass, field
from typing import Callable, Optional, Tuple, Type


@dataclass(frozen=True)
class BackoffConfig:
    """Configuration for exponential back-off retries.

    Attributes:
        max_attempts: Total attempts including the first (default 4).
        base_delay:   Initial delay in seconds (default 0.5).
        max_delay:    Upper cap on delay in seconds (default 30.0).
        multiplier:   Exponential growth factor per retry (default 2.0).
        jitter:       Fraction of delay added as random noise (default 0.25).
                      E.g. 0.25 means ± 25 % of the computed delay.
    """

    max_attempts: int = 4
    base_delay: float = 0.5
    max_delay: float = 30.0
    multiplier: float = 2.0
    jitter: float = 0.25

    def delay_for(self, attempt: int) -> float:
        """Return the sleep duration (seconds) before *attempt* (0-based).

        Args:
            attempt: The retry attempt index (0 = first retry after initial failure).

        Returns:
            Delay in seconds, capped at *max_delay*, with jitter applied.
        """
        raw = self.base_delay * (self.multiplier ** attempt)
        capped = min(raw, self.max_delay)
        noise = capped * self.jitter * (2 * random.random() - 1)
        return max(0.0, capped + noise)


def retry_with_backoff(
    fn: Callable,
    *,
    config: BackoffConfig | None = None,
    retryable: Tuple[Type[BaseException], ...] = (Exception,),
    on_retry: Optional[Callable[[int, BaseException], None]] = None,
) -> object:
    """Call *fn* up to *config.max_attempts* times, backing off between retries.

    Args:
        fn:        Zero-argument callable to invoke.
        config:    :class:`BackoffConfig` (default: ``BackoffConfig()``).
        retryable: Exception types that trigger a retry.  Any other exception
                   propagates immediately.
        on_retry:  Optional callback ``(attempt, exc)`` called before each sleep.

    Returns:
        The return value of *fn* on success.

    Raises:
        The last retryable exception if all attempts are exhausted.
        Any non-retryable exception from *fn* immediately.
    """
    cfg = config or BackoffConfig()
    last_exc: BaseException | None = None

    for attempt in range(cfg.max_attempts):
        try:
            return fn()
        except retryable as exc:  # type: ignore[misc]
            last_exc = exc
            if attempt < cfg.max_attempts - 1:
                delay = cfg.delay_for(attempt)
                if on_retry is not None:
                    on_retry(attempt + 1, exc)
                time.sleep(delay)

    raise last_exc  # type: ignore[misc]


def compute_delays(config: BackoffConfig, n_retries: int) -> list[float]:
    """Return the theoretical delay sequence for *n_retries* retries.

    Jitter is not applied — returns the deterministic base values.
    Useful for testing and displaying estimated wait times.

    Args:
        config:   The :class:`BackoffConfig` to use.
        n_retries: Number of retries (not counting the initial attempt).

    Returns:
        List of delay values in seconds.
    """
    delays = []
    for attempt in range(n_retries):
        raw = config.base_delay * (config.multiplier ** attempt)
        delays.append(min(raw, config.max_delay))
    return delays
