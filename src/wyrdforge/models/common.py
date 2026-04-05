from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class StoreName(str, Enum):
    HUGIN = "hugin_observation_store"
    MUNIN = "munin_distillation_store"
    MIMIR = "mimir_canonical_store"
    WYRD = "wyrd_graph_store"
    ORLOG = "orlog_policy_store"
    SEIDR = "seidr_symbolic_store"


class SupportClass(str, Enum):
    SUPPORTED = "supported"
    INFERRED = "inferred"
    SPECULATIVE = "speculative"
    CREATIVE = "creative"
    POLICY = "policy"


class ContradictionStatus(str, Enum):
    NONE = "none"
    CANDIDATE = "candidate"
    CONFIRMED = "confirmed"


class ApprovalState(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    QUARANTINED = "quarantined"
    REJECTED = "rejected"


class WritePolicy(str, Enum):
    EPHEMERAL = "ephemeral"
    REVIEWED = "reviewed"
    PROMOTABLE = "promotable"
    CANONICAL = "canonical"
    IMMUTABLE = "immutable"


class RetentionClass(str, Enum):
    SHORT = "short"
    MEDIUM = "medium"
    LONG = "long"
    PERMANENT = "permanent"


class DecayCurve(str, Enum):
    NONE = "none"
    LINEAR = "linear"
    EXP = "exp"
    STEP = "step"


class Sensitivity(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class RiskLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class EntityScope(StrictModel):
    primary_subjects: list[str] = Field(default_factory=list)
    secondary_subjects: list[str] = Field(default_factory=list)
    scene_id: str | None = None
    session_id: str | None = None
    world_id: str | None = None
    project_id: str | None = None


class MemoryContent(StrictModel):
    title: str
    summary: str
    body_ref: str | None = None
    structured_payload: dict[str, Any] = Field(default_factory=dict)


class TruthMeta(StrictModel):
    support_class: SupportClass = SupportClass.SUPPORTED
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    contradiction_status: ContradictionStatus = ContradictionStatus.NONE
    approval_state: ApprovalState = ApprovalState.PENDING


class Provenance(StrictModel):
    source_type: str
    source_ref: str
    source_hash: str | None = None
    extracted_at: datetime
    extracted_by: str


class Lifecycle(StrictModel):
    write_policy: WritePolicy = WritePolicy.EPHEMERAL
    retention_class: RetentionClass = RetentionClass.SHORT
    decay_curve: DecayCurve = DecayCurve.NONE
    expires_at: datetime | None = None
    last_accessed_at: datetime | None = None
    access_count: int = 0
    stale_after_days: int | None = None


class RetrievalMeta(StrictModel):
    embedding_id: str | None = None
    lexical_terms: list[str] = Field(default_factory=list)
    facets: dict[str, list[str]] = Field(default_factory=dict)
    default_priority: float = 0.0


class Governance(StrictModel):
    sensitivity: Sensitivity = Sensitivity.LOW
    memory_poison_risk: RiskLevel = RiskLevel.LOW
    allowed_for_runtime: bool = True
    allowed_for_training: bool = False
    requires_review_before_promotion: bool = True


class Audit(StrictModel):
    created_at: datetime
    updated_at: datetime
    created_by_agent: str
    updated_by_agent: str
