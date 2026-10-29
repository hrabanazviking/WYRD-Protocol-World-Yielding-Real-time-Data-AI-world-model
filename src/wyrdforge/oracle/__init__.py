"""Passive Oracle Model — read-only ground-truth world query API."""
from wyrdforge.oracle.passive_oracle import PassiveOracle
from wyrdforge.oracle.models import (
    CombatProximityResult,
    EngagementResult,
    EntitySummary,
    FactSummary,
    LocationResult,
    ObservationSummary,
    PolicySummary,
    PositionResult,
    ProximityResult,
    RelationResult,
    ThreatResult,
    WorldContextPacket,
)

__all__ = [
    "PassiveOracle",
    "CombatProximityResult",
    "EngagementResult",
    "EntitySummary",
    "FactSummary",
    "LocationResult",
    "ObservationSummary",
    "PolicySummary",
    "PositionResult",
    "ProximityResult",
    "RelationResult",
    "ThreatResult",
    "WorldContextPacket",
]
