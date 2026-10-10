"""Forge tests: PermissionGuard audit trail and require() enforcement.

Proves every classify() decision is recorded with a monotonic seq and an
ISO timestamp in a bounded log, and that require() fails closed by raising
PermissionDenied on deny while returning the decision on allow.
"""
from __future__ import annotations

from datetime import datetime

import pytest

from wyrdforge.security.permission_guard import (
    PermissionDenied,
    PermissionGuard,
)


# ---------------------------------------------------------------------------
# classify behavior (unchanged contract)
# ---------------------------------------------------------------------------

def test_classify_read_only_allows() -> None:
    decision = PermissionGuard().classify("read")
    assert decision.allow is True
    assert decision.risk_level == "low"


def test_classify_high_risk_denies() -> None:
    decision = PermissionGuard().classify("delete")
    assert decision.allow is False
    assert decision.risk_level == "high"


def test_classify_unknown_denies_by_default() -> None:
    decision = PermissionGuard().classify("do_something_new")
    assert decision.allow is False
    assert decision.risk_level == "medium"


# ---------------------------------------------------------------------------
# Audit trail
# ---------------------------------------------------------------------------

def test_classify_appends_audit_record() -> None:
    guard = PermissionGuard()
    guard.classify("read")
    log = guard.audit_log()
    assert len(log) == 1
    record = log[0]
    assert record.seq == 1
    assert record.action_name == "read"
    assert record.risk_level == "low"
    assert record.allow is True
    assert record.reason == "read-only action"
    # decided_at must be a parseable ISO timestamp.
    datetime.fromisoformat(record.decided_at)


def test_audit_seq_is_monotonic() -> None:
    guard = PermissionGuard()
    for action in ("read", "delete", "list", "exec"):
        guard.classify(action)
    seqs = [r.seq for r in guard.audit_log()]
    assert seqs == [1, 2, 3, 4]


def test_audit_log_returns_detached_copy() -> None:
    guard = PermissionGuard()
    guard.classify("read")
    log = guard.audit_log()
    log.clear()
    log.append("junk")
    assert len(guard.audit_log()) == 1


def test_audit_log_is_bounded() -> None:
    guard = PermissionGuard()
    for i in range(PermissionGuard.AUDIT_LOG_MAXLEN + 50):
        guard.classify(f"action_{i}")
    log = guard.audit_log()
    assert len(log) == PermissionGuard.AUDIT_LOG_MAXLEN
    # The deque keeps the *newest* records; seqs stay monotonic.
    seqs = [r.seq for r in log]
    assert seqs == sorted(seqs)
    assert seqs[0] == 51


def test_denial_is_recorded_in_audit_log() -> None:
    guard = PermissionGuard()
    with pytest.raises(PermissionDenied):
        guard.require("delete")
    log = guard.audit_log()
    assert len(log) == 1
    record = log[0]
    assert record.action_name == "delete"
    assert record.allow is False
    assert record.risk_level == "high"
    datetime.fromisoformat(record.decided_at)


# ---------------------------------------------------------------------------
# require() enforcement
# ---------------------------------------------------------------------------

def test_require_high_risk_raises_permission_denied() -> None:
    guard = PermissionGuard()
    with pytest.raises(PermissionDenied) as exc_info:
        guard.require("exfiltrate")
    assert "exfiltrate" in str(exc_info.value)
    assert exc_info.value.decision.risk_level == "high"


def test_require_read_only_returns_decision_with_allow_true() -> None:
    guard = PermissionGuard()
    decision = guard.require("read")
    assert decision.allow is True
    assert decision.action_name == "read"


def test_require_unknown_action_raises() -> None:
    guard = PermissionGuard()
    with pytest.raises(PermissionDenied):
        guard.require("launch_missiles")


def test_require_is_case_insensitive() -> None:
    guard = PermissionGuard()
    decision = guard.require("READ")
    assert decision.allow is True
    assert guard.audit_log()[0].action_name == "read"
