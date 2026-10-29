"""Response model types for the Passive Oracle."""
from __future__ import annotations

from datetime import datetime

from pydantic import Field

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


class PositionResult(StrictModel):
    """Metric position of an entity (Phase B3 — spatial core)."""

    entity_id: str
    x: float
    y: float
    z: float
    frame_id: str | None          # coordinate frame; None = default frame


class ProximityResult(StrictModel):
    """One entity found by a radius/nearest query (Phase B3).

    Results are returned sorted by ``(distance, entity_id)`` — the
    entity_id tie-break makes the order total and deterministic.
    """

    entity_id: str
    distance: float               # metres from the query centre
    x: float
    y: float
    z: float
    frame_id: str | None


class EngagementResult(StrictModel):
    """One engagement as the Oracle reports it (Phase D1).

    The engagement is an entity; this is its summary. ``state`` is
    the lifecycle state (skirmish / engaged / broken / ended).
    """

    engagement_id: str
    state: str
    participant_ids: list[str]
    anchor_entity_id: str | None
    label: str
    started_at: datetime
    ended_at: datetime | None


class ThreatResult(StrictModel):
    """One observer's perceived threat assessment (Phase D1).

    Perceived state, not ground truth: two observers of the same
    target may return different levels — that divergence is the
    point of the model (roadmap §6).
    """

    observer_id: str
    target_id: str
    level: float
    basis_event_ids: list[str]
    source: str
    confidence: float
    assessed_at: datetime


class CombatProximityResult(StrictModel):
    """A combatant found by a combat radius query (Phase D1).

    ``range_band`` is DERIVED from the B3 distance at query time
    (engaged / near / far) — it is computed here, never read from
    stored state, so it cannot disagree with the positions.
    """

    entity_id: str
    distance: float
    range_band: str
    x: float
    y: float
    z: float
    frame_id: str | None


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
    # Track 7: facts at confidence strictly below UNCERTAINTY_THRESHOLD (0.3)
    # render as uncertain with their confidence history instead of asserted.
    # Both defaulted — existing callers are unaffected.
    uncertain: bool = False
    confidence_history: list[float] = Field(default_factory=list)


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
    # Phase C3: attribution carried into the packet so prompt
    # rendering can present the observation as someone's words
    # (data), never as unattributed instruction. Both defaulted —
    # pre-C3 records and non-utterance kinds carry neither.
    speaker_id: str | None = None
    participants: list[str] = Field(default_factory=list)


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
