from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Literal

from pydantic import Field

from .common import StrictModel


class BondDomain(str, Enum):
    COMPANION = "companion"
    ROMANCE = "romance"
    FRIENDSHIP = "friendship"
    MENTOR = "mentor"
    BUILDER = "builder"
    RITUAL = "ritual"
    PARTY_MEMBER = "party_member"
    DEITY_DEVOTEE = "deity_devotee"


class BondStatus(str, Enum):
    FORMING = "forming"
    ACTIVE = "active"
    STRAINED = "strained"
    REPAIRING = "repairing"
    DORMANT = "dormant"
    BROKEN = "broken"
    TRANSFIGURED = "transfigured"


class BondVector(StrictModel):
    trust: float = Field(default=0.5, ge=0.0, le=1.0)
    warmth: float = Field(default=0.5, ge=0.0, le=1.0)
    familiarity: float = Field(default=0.1, ge=0.0, le=1.0)
    devotion: float = Field(default=0.0, ge=0.0, le=1.0)
    attraction_affinity: float = Field(default=0.0, ge=0.0, le=1.0)
    safety: float = Field(default=0.8, ge=0.0, le=1.0)
    sacred_resonance: float = Field(default=0.0, ge=0.0, le=1.0)
    playfulness: float = Field(default=0.2, ge=0.0, le=1.0)
    vulnerability: float = Field(default=0.1, ge=0.0, le=1.0)
    initiative_balance: float = Field(default=0.0, ge=-1.0, le=1.0)


class BondConstraints(StrictModel):
    exclusivity_mode: str = "none"
    intimacy_ceiling: str = "medium"
    boundary_profile_id: str = "default"


class BondScars(StrictModel):
    repair_debt: float = Field(default=0.0, ge=0.0, le=1.0)
    unresolved_hurts: list[str] = Field(default_factory=list)
    vow_strain: float = Field(default=0.0, ge=0.0, le=1.0)


class BondActiveModes(StrictModel):
    relational_mode: str = "builder"
    emotional_weather: str = "calm"


class BondChronology(StrictModel):
    formed_at: datetime | None = None
    last_major_shift_at: datetime | None = None
    last_contact_at: datetime | None = None


class BondEvidence(StrictModel):
    supporting_record_ids: list[str] = Field(default_factory=list)
    contradiction_record_ids: list[str] = Field(default_factory=list)


class BondGovernance(StrictModel):
    review_required_for_large_shift: bool = True
    synthetic_claim_guard: bool = True


class BondEdge(StrictModel):
    bond_id: str
    entity_a: str
    entity_b: str
    domain: BondDomain
    status: BondStatus = BondStatus.FORMING
    vector: BondVector = Field(default_factory=BondVector)
    constraints: BondConstraints = Field(default_factory=BondConstraints)
    scars: BondScars = Field(default_factory=BondScars)
    active_modes: BondActiveModes = Field(default_factory=BondActiveModes)
    chronology: BondChronology = Field(default_factory=BondChronology)
    evidence: BondEvidence = Field(default_factory=BondEvidence)
    governance: BondGovernance = Field(default_factory=BondGovernance)

    def closeness_index(self) -> float:
        return round((self.vector.trust + self.vector.warmth + self.vector.familiarity + self.vector.vulnerability) / 4.0, 4)

    def sacred_bond_index(self) -> float:
        vow_integrity_inverse_strain = 1.0 - self.scars.vow_strain
        return round((self.vector.devotion + self.vector.sacred_resonance + vow_integrity_inverse_strain) / 3.0, 4)

    def rupture_index(self) -> float:
        inverse_safety = 1.0 - self.vector.safety
        return round((self.scars.repair_debt + self.scars.vow_strain + inverse_safety) / 3.0, 4)


class VowState(str, Enum):
    PENDING = "pending"
    KEPT = "kept"
    STRAINED = "strained"
    BROKEN = "broken"
    RELEASED = "released"


class Vow(StrictModel):
    vow_id: str
    bond_id: str
    vow_text: str
    vow_kind: str
    strength: str = "medium"
    state: VowState = VowState.PENDING
    witness_entities: list[str] = Field(default_factory=list)
    created_from_record_id: str
    kept_by_events: list[str] = Field(default_factory=list)
    broken_by_events: list[str] = Field(default_factory=list)


class Hurt(StrictModel):
    hurt_id: str
    bond_id: str
    source_event_id: str
    hurt_kind: Literal["neglect", "contradiction", "betrayal", "boundary_cross", "false_memory", "tone_mismatch", "absence"]
    severity: Literal["low", "medium", "high", "mythic"]
    notes: str = ""
