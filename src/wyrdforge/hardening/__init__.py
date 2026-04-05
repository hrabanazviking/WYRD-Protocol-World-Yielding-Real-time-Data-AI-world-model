"""wyrdforge.hardening — Robustness utilities for WYRD Protocol.

Modules:
    backoff          — Exponential back-off with jitter for retryable operations
    normalization    — Unicode-safe persona_id normalisation guard
    pool             — Bounded daemon-thread pool (caps concurrent push operations)
    config_validator — YAML world-config schema validator + env-var type coercer
"""
