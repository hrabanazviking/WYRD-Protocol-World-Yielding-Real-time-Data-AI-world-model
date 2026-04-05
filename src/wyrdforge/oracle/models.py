"""Response model types for the Passive Oracle."""
from __future__ import annotations

from datetime import datetime

from wyrdforge.models.common import StrictModel


class LocationResult(StrictModel):
    """Spatial position of an entity."""

    entity_id: str
    location_id: str | None          # most specific node (subloc if present, else loc)
    location_name: str | None
    zone_id: str | None
    region_id: str | None
    path: list[str]                  # [zone, region, location, sublocation] — non-None IDs


class EntitySummary(StrictModel):
    """Compact snapshot of a single ECS entity."""

    entity_id: str
    name: str | None
    description: str | None
    status: str | None
    tags: list[str]
    location_id: str | None          # most specific location ID


class RelationResult(StrictModel):
    """Faction membership and co-presence of an entity."""

    entity_id: str
    faction_id: str | None
    faction_name: str | None
    faction_reputations: dict[str, float]   # faction_id → -1.0..1.0
    co_located_entity_ids: list[str]


class FactSummary(StrictModel):
    """Condensed form of a CanonicalFactRecord for context packets."""

    record_id: str
    subject_id: str
    fact_key: str
    fact_value: str
    confidence: float
    domain: str


class PolicySummary(StrictModel):
    """Condensed form of a PolicyRecord for context packets."""

    record_id: str
    title: str
    rule_text: str
    policy_kind: str
    priority: int


class ObservationSummary(StrictModel):
    """Condensed form of an ObservationRecord for context packets."""

    record_id: str
    title: str
    summary: str
    observed_at: datetime


class WorldContextPacket(StrictModel):
    """LLM-ready context bundle.

    Aggregates ECS world state + memory layer content into a single
    structured object. Serialize to JSON or use ``formatted_for_llm``
    directly as a prompt-injection block.
    """

    query_timestamp: datetime
    world_id: str | None
    focus_entities: list[EntitySummary]
    location_context: LocationResult | None
    present_entities: list[EntitySummary]
    canonical_facts: dict[str, list[FactSummary]]   # subject_id → facts
    active_policies: list[PolicySummary]
    recent_observations: list[ObservationSummary]
    open_contradiction_count: int
    formatted_for_llm: str                           # pre-rendered text block
