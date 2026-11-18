"""World-event intake (WY-T2) + HugrGate judgment binding (WY-T3) + awareness queries (WY-T4) + multi-source conflicts (WY-T5)."""
from wyrdforge.events.intake import (
    EventIntake,
    StateChangeRecord,
    StoredEvent,
    WorldEvent,
    apply_tactical_event,
    compute_digest,
)
from wyrdforge.events.awareness import (
    ActiveCombat,
    AwarenessQuery,
    AwarenessSnapshot,
    NotableEvent,
    ThreatReport,
)
from wyrdforge.events.conflicts import (
    Claim,
    ConflictRecord,
    ConflictTracker,
    MultiSourceApplier,
    ReportRecord,
    ResolutionDecision,
    extract_claim,
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
    "ActiveCombat",
    "AwarenessQuery",
    "AwarenessSnapshot",
    "NotableEvent",
    "ThreatReport",
    "Claim",
    "ConflictRecord",
    "ConflictTracker",
    "MultiSourceApplier",
    "ReportRecord",
    "ResolutionDecision",
    "extract_claim",
]
