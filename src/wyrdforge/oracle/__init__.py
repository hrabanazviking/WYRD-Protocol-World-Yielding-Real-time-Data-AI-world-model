"""Passive Oracle Model — read-only ground-truth world query API."""
from wyrdforge.oracle.passive_oracle import PassiveOracle
from wyrdforge.oracle.models import (
    EntitySummary,
    FactSummary,
    LocationResult,
    ObservationSummary,
    PolicySummary,
    RelationResult,
    WorldContextPacket,
)

__all__ = [
    "PassiveOracle",
    "EntitySummary",
    "FactSummary",
    "LocationResult",
    "ObservationSummary",
    "PolicySummary",
    "RelationResult",
    "WorldContextPacket",
]
