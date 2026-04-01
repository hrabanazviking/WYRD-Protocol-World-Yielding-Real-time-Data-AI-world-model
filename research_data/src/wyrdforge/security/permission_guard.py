from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class PermissionDecision:
    action_name: str
    risk_level: str
    allow: bool
    reason: str


class PermissionGuard:
    READ_ONLY_ACTIONS = {"search", "read", "list", "summarize"}
    HIGH_RISK_ACTIONS = {"delete", "exfiltrate", "exec", "install", "deploy"}

    def classify(self, action_name: str) -> PermissionDecision:
        action_name = action_name.lower()
        if action_name in self.READ_ONLY_ACTIONS:
            return PermissionDecision(action_name, "low", True, "read-only action")
        if action_name in self.HIGH_RISK_ACTIONS:
            return PermissionDecision(action_name, "high", False, "requires explicit approval")
        return PermissionDecision(action_name, "medium", False, "default deny until reviewed")
