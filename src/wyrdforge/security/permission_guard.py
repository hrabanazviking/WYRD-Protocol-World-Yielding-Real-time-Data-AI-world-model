"""permission_guard.py — classify action risk and keep an audit trail.

Why the audit log exists: classification decisions gate dangerous actions,
so every decision must be reconstructible after the fact — which action was
asked, what risk it carried, whether it was allowed, why, and exactly when.
The log is a bounded deque (maxlen 256): forensic enough to answer "why was
X denied?" without growing forever on a long-running server. Sequence
numbers are monotonic per guard instance, so the log has a total order even
when two decisions land in the same timestamp.

``require()`` is the enforcement point: it classifies and raises
:class:`PermissionDenied` on deny, so callers fail closed by default instead
of checking a boolean and forgetting the branch.
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from datetime import datetime, timezone
from itertools import count
from typing import Deque


class PermissionDenied(Exception):
    """Raised by :meth:`PermissionGuard.require` when an action is denied.

    Carries the original :class:`PermissionDecision` so handlers can log or
    report the risk level and reason without re-classifying.
    """

    def __init__(self, action_name: str, decision: "PermissionDecision") -> None:
        self.action_name = action_name
        self.decision = decision
        super().__init__(
            f"permission denied for action '{action_name}': {decision.reason}"
        )


@dataclass(slots=True)
class PermissionDecision:
    action_name: str
    risk_level: str
    allow: bool
    reason: str


@dataclass(slots=True)
class PermissionAuditRecord:
    """One classification decision, as kept in the bounded audit log.

    Attributes:
        seq:         Monotonic sequence number (per guard instance).
        decided_at:  ISO-8601 UTC timestamp of the decision.
        action_name: Lowercased action that was classified.
        risk_level:  ``"low"`` / ``"medium"`` / ``"high"``.
        allow:       Whether the action was allowed.
        reason:      Human-readable rationale.
    """

    seq: int
    decided_at: str
    action_name: str
    risk_level: str
    allow: bool
    reason: str


class PermissionGuard:
    READ_ONLY_ACTIONS = {"search", "read", "list", "summarize"}
    HIGH_RISK_ACTIONS = {"delete", "exfiltrate", "exec", "install", "deploy"}

    #: Forensic window: enough to answer "why was X denied?" after the fact,
    #: bounded so a long-running server never grows the log forever.
    AUDIT_LOG_MAXLEN = 256

    def __init__(self) -> None:
        self._audit: Deque[PermissionAuditRecord] = deque(maxlen=self.AUDIT_LOG_MAXLEN)
        self._seq = count(1)

    def classify(self, action_name: str) -> PermissionDecision:
        """Classify *action_name* and append the decision to the audit log.

        Returns:
            The :class:`PermissionDecision`.  The matching
            :class:`PermissionAuditRecord` (with seq and timestamp) is
            appended to the bounded audit log as a side effect.
        """
        action_name = action_name.lower()
        if action_name in self.READ_ONLY_ACTIONS:
            decision = PermissionDecision(action_name, "low", True, "read-only action")
        elif action_name in self.HIGH_RISK_ACTIONS:
            decision = PermissionDecision(action_name, "high", False, "requires explicit approval")
        else:
            decision = PermissionDecision(action_name, "medium", False, "default deny until reviewed")
        self._audit.append(
            PermissionAuditRecord(
                seq=next(self._seq),
                decided_at=datetime.now(timezone.utc).isoformat(),
                action_name=decision.action_name,
                risk_level=decision.risk_level,
                allow=decision.allow,
                reason=decision.reason,
            )
        )
        return decision

    def audit_log(self) -> list[PermissionAuditRecord]:
        """Return a snapshot copy of the audit log (oldest decision first).

        The copy is detached: mutating it does not affect the guard.
        """
        return list(self._audit)

    def require(self, action_name: str) -> PermissionDecision:
        """Classify *action_name*; raise :class:`PermissionDenied` on deny.

        Args:
            action_name: The action to authorize.

        Returns:
            The :class:`PermissionDecision` when the action is allowed.

        Raises:
            PermissionDenied: When the action is denied — the guard fails
                closed so callers cannot forget the deny branch.
        """
        decision = self.classify(action_name)
        if not decision.allow:
            raise PermissionDenied(action_name, decision)
        return decision
