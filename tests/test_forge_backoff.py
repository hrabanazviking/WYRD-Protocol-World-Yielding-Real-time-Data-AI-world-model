"""Forge tests: BackoffConfig validation (Helheim Hardening).

Covers the ``__post_init__`` fail-fast validation on BackoffConfig —
the latent bug it kills (max_attempts=0 -> loop never runs ->
``raise None`` -> TypeError) and the retry_with_backoff single-attempt
contract.
"""
from __future__ import annotations

import pytest

from wyrdforge.hardening.backoff import BackoffConfig, retry_with_backoff


# ---------------------------------------------------------------------------
# Invalid configurations raise ValueError at construction
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "kwargs",
    [
        {"max_attempts": 0},      # the latent `raise None` -> TypeError bug
        {"max_attempts": -3},
        {"max_attempts": "3"},    # non-int
        {"max_attempts": True},   # bool is not a real attempt count
        {"base_delay": -0.1},
        {"base_delay": 5.0, "max_delay": 1.0},  # max_delay < base_delay
        {"multiplier": 0.99},
        {"multiplier": 0.0},
        {"jitter": -0.1},
        {"jitter": 1.1},
    ],
)
def test_invalid_configs_raise_value_error(kwargs):
    with pytest.raises(ValueError):
        BackoffConfig(**kwargs)


# ---------------------------------------------------------------------------
# Valid configurations are untouched
# ---------------------------------------------------------------------------

def test_valid_defaults_unchanged():
    cfg = BackoffConfig()
    assert cfg == BackoffConfig(
        max_attempts=4, base_delay=0.5, max_delay=30.0, multiplier=2.0, jitter=0.25
    )


@pytest.mark.parametrize(
    "kwargs",
    [
        {"max_attempts": 1},
        {"base_delay": 0.0},                    # no delay is legal
        {"base_delay": 2.0, "max_delay": 2.0},  # cap == base is legal
        {"multiplier": 1.0},                    # linear retry is legal
        {"jitter": 0.0},
        {"jitter": 1.0},
    ],
)
def test_boundary_configs_are_valid(kwargs):
    BackoffConfig(**kwargs)  # must not raise


def test_max_attempts_zero_now_fails_fast_not_with_type_error():
    """Regression: max_attempts=0 used to build fine and then explode with
    ``TypeError: exceptions must derive from BaseException`` (``raise
    None``) inside retry_with_backoff. The config is now rejected at
    construction, so that path is unreachable."""
    with pytest.raises(ValueError, match="max_attempts"):
        BackoffConfig(max_attempts=0)


# ---------------------------------------------------------------------------
# retry_with_backoff single-attempt contract
# ---------------------------------------------------------------------------

def test_single_attempt_calls_fn_once_and_reraises_original():
    calls: list[int] = []
    original = ConnectionError("server is down")

    def flaky():
        calls.append(1)
        raise original

    cfg = BackoffConfig(max_attempts=1, base_delay=0.0, jitter=0.0)
    with pytest.raises(ConnectionError) as exc_info:
        retry_with_backoff(flaky, config=cfg, retryable=(ConnectionError,))
    assert exc_info.value is original  # the SAME object, not a copy
    assert len(calls) == 1  # exactly one call, no retries
