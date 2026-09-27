"""wyrdforge.hardening — Robustness utilities for WYRD Protocol.

Input validation is fail-closed, never silent: hostile or malformed
input is rejected with an error naming the field, at the boundary
where it arrives — never deep in the machinery.

Modules:
    input_validation — Shared fail-closed input checks (Track 1, P1):
                       InputValidationError, depth/string checks, the
                       event-envelope shared by both ingest doors,
                       per-type event schemas, FTS5 search bounds
    backoff          — Exponential back-off with jitter for retryable operations
    normalization    — Unicode-safe persona_id normalisation guard
    pool             — Bounded daemon-thread pool (caps concurrent push operations)
    config_validator — Canonical world-config schema validator + env-var type coercer
    state_io         — Corrupt-state detection and repair (Track 5): quarantine,
                       guarded SQLite opens, schema versions, atomic JSON writes
"""

from wyrdforge.hardening.input_validation import (
    InputValidationError,
    check_depth,
    check_string,
    validate_event_envelope,
    validate_event_payload,
    validate_search_query,
)

__all__ = [
    "InputValidationError",
    "check_depth",
    "check_string",
    "validate_event_envelope",
    "validate_event_payload",
    "validate_search_query",
]
