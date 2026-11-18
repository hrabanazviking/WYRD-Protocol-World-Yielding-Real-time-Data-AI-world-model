"""World-event intake with provenance (WY-T2) + HugrGate judgment binding (WY-T3)."""
from wyrdforge.events.intake import (
    EventIntake,
    StateChangeRecord,
    StoredEvent,
    WorldEvent,
    apply_tactical_event,
    compute_digest,
)
from wyrdforge.events.judgment import (
    FixtureHugrGateClient,
    HttpHugrGateClient,
    JudgmentBinding,
    JudgmentRecord,
)

__all__ = [
    "EventIntake",
    "StateChangeRecord",
    "StoredEvent",
    "WorldEvent",
    "apply_tactical_event",
    "compute_digest",
    "FixtureHugrGateClient",
    "HttpHugrGateClient",
    "JudgmentBinding",
    "JudgmentRecord",
]
