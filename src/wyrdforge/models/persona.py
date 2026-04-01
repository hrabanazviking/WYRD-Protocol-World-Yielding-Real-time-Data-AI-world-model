from __future__ import annotations

from enum import Enum

from pydantic import Field

from .common import StrictModel


class PersonaMode(str, Enum):
    COMPANION = "companion"
    CODING_GUIDE = "coding_guide"
    WORLD_SEER = "world_seer"
    RITUAL = "ritual"
    DEBRIEF = "debrief"


class TraitSignal(StrictModel):
    trait_name: str
    weight: float = Field(default=0.5, ge=0.0, le=1.0)
    supporting_record_ids: list[str] = Field(default_factory=list)


class PersonaSourceItem(StrictModel):
    record_id: str
    item_type: str
    text: str
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)


class PersonaPacket(StrictModel):
    persona_id: str
    user_id: str
    mode: PersonaMode
    tone_contract: list[str] = Field(default_factory=list)
    identity_core: list[str] = Field(default_factory=list)
    active_traits: list[TraitSignal] = Field(default_factory=list)
    relationship_excerpt: list[str] = Field(default_factory=list)
    truth_anchor_points: list[str] = Field(default_factory=list)
    uncertainty_points: list[str] = Field(default_factory=list)
    symbolic_context: list[str] = Field(default_factory=list)
    response_guidance: list[str] = Field(default_factory=list)
    source_items: list[PersonaSourceItem] = Field(default_factory=list)
    token_budget_hint: int = 800
