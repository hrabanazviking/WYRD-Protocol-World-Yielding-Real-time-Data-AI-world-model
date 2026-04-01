from __future__ import annotations

from enum import Enum

from pydantic import Field

from .common import StrictModel


class QueryMode(str, Enum):
    FACTUAL_LOOKUP = "factual_lookup"
    COMPANION_CONTINUITY = "companion_continuity"
    WORLD_STATE = "world_state"
    SYMBOLIC_INTERPRETATION = "symbolic_interpretation"
    CODING_TASK = "coding_task"
    REPAIR_OR_BOUNDARY = "repair_or_boundary"
    CREATIVE_GENERATION = "creative_generation"


class RetrievalItem(StrictModel):
    item_id: str
    item_type: str
    text: str
    support_class: str = "supported"
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    source_ref: str
    lexical_terms: list[str] = Field(default_factory=list)
    facets: dict[str, list[str]] = Field(default_factory=dict)
    token_cost: int = 80


class RankedCandidate(RetrievalItem):
    final_score: float = 0.0
    similarity: float = 0.0
    task_relevance: float = 0.0
    support_quality: float = 0.0
    scope_match: float = 0.0
    recency: float = 0.0
    contradiction_penalty: float = 0.0
    token_cost_penalty: float = 0.0
    novelty_bonus: float = 0.0
    bond_fit: float = 0.0


class TruthPacket(StrictModel):
    must_be_true: list[str] = Field(default_factory=list)
    open_unknowns: list[str] = Field(default_factory=list)
    forbidden_assumptions: list[str] = Field(default_factory=list)


class MicroContextPacket(StrictModel):
    mode: QueryMode
    goal: str
    truth_packet: TruthPacket = Field(default_factory=TruthPacket)
    canonical_facts: list[RankedCandidate] = Field(default_factory=list)
    recent_events: list[RankedCandidate] = Field(default_factory=list)
    bond_excerpt: list[RankedCandidate] = Field(default_factory=list)
    symbolic_context: list[RankedCandidate] = Field(default_factory=list)
    code_context: list[RankedCandidate] = Field(default_factory=list)
    contradiction_items: list[RankedCandidate] = Field(default_factory=list)
    packet_budget_used: int = 0
