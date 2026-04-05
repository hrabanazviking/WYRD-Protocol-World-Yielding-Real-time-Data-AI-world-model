from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Literal

from pydantic import Field

from .common import (
    StrictModel,
    StoreName,
    EntityScope,
    MemoryContent,
    TruthMeta,
    Provenance,
    Lifecycle,
    RetrievalMeta,
    Governance,
    Audit,
)


class MemoryRecord(StrictModel):
    record_id: str
    store: StoreName
    record_type: str
    schema_version: str = "1.0.0"
    tenant_id: str
    system_id: str
    entity_scope: EntityScope
    content: MemoryContent
    truth: TruthMeta
    provenance: Provenance
    lifecycle: Lifecycle
    retrieval: RetrievalMeta = Field(default_factory=RetrievalMeta)
    governance: Governance = Field(default_factory=Governance)
    audit: Audit


class ObservationKind(str, Enum):
    UTTERANCE = "utterance"
    ACTION = "action"
    TOOL_RESULT = "tool_result"
    WORLD_EVENT = "world_event"
    CODE_EVENT = "code_event"
    EMOTION_SIGNAL = "emotion_signal"


class ObservationPayload(StrictModel):
    observation_kind: ObservationKind
    raw_excerpt: str | None = None
    normalized_claims: list[str] = Field(default_factory=list)
    participants: list[str] = Field(default_factory=list)
    observed_at: datetime
    place_id: str | None = None
    salience: float = Field(default=0.5, ge=0.0, le=1.0)
    candidate_memory_write: bool = True


class ObservationContent(MemoryContent):
    structured_payload: ObservationPayload


class ObservationRecord(MemoryRecord):
    store: Literal[StoreName.HUGIN] = StoreName.HUGIN
    record_type: Literal["observation"] = "observation"
    content: ObservationContent


class CanonicalFactPayload(StrictModel):
    fact_subject_id: str
    fact_key: str
    fact_value: str
    value_type: str = "string"
    domain: str = "general"
    support_record_ids: list[str] = Field(default_factory=list)
    supersedes_record_id: str | None = None


class CanonicalFactContent(MemoryContent):
    structured_payload: CanonicalFactPayload


class CanonicalFactRecord(MemoryRecord):
    store: Literal[StoreName.MIMIR] = StoreName.MIMIR
    record_type: Literal["canonical_fact"] = "canonical_fact"
    content: CanonicalFactContent


class EpisodeSummaryPayload(StrictModel):
    episode_id: str
    start_turn: int
    end_turn: int
    major_events: list[str] = Field(default_factory=list)
    resolved_tensions: list[str] = Field(default_factory=list)
    open_threads: list[str] = Field(default_factory=list)
    recommended_retrieval_tags: list[str] = Field(default_factory=list)


class EpisodeSummaryContent(MemoryContent):
    structured_payload: EpisodeSummaryPayload


class EpisodeSummaryRecord(MemoryRecord):
    store: Literal[StoreName.MUNIN] = StoreName.MUNIN
    record_type: Literal["episode_summary"] = "episode_summary"
    content: EpisodeSummaryContent


class SymbolicTracePayload(StrictModel):
    symbol_type: str
    rune_signature: list[str] = Field(default_factory=list)
    omen_strength: float = Field(default=0.0, ge=0.0, le=1.0)
    ritual_charge: float = Field(default=0.0, ge=0.0, le=1.0)
    mood_tags: list[str] = Field(default_factory=list)


class SymbolicTraceContent(MemoryContent):
    structured_payload: SymbolicTracePayload


class SymbolicTraceRecord(MemoryRecord):
    store: Literal[StoreName.SEIDR] = StoreName.SEIDR
    record_type: Literal["symbolic_trace"] = "symbolic_trace"
    content: SymbolicTraceContent


class ContradictionPayload(StrictModel):
    claim_a_record_id: str
    claim_b_record_id: str
    contradiction_reason: str
    preferred_record_id: str | None = None
    resolution_state: Literal["open", "resolved", "quarantined"] = "open"


class ContradictionContent(MemoryContent):
    structured_payload: ContradictionPayload


class ContradictionRecord(MemoryRecord):
    store: Literal[StoreName.WYRD] = StoreName.WYRD
    record_type: Literal["contradiction"] = "contradiction"
    content: ContradictionContent


class PolicyPayload(StrictModel):
    policy_kind: str
    rule_text: str
    applies_to_domains: list[str] = Field(default_factory=list)
    priority: int = 100


class PolicyContent(MemoryContent):
    structured_payload: PolicyPayload


class PolicyRecord(MemoryRecord):
    store: Literal[StoreName.ORLOG] = StoreName.ORLOG
    record_type: Literal["policy"] = "policy"
    content: PolicyContent
