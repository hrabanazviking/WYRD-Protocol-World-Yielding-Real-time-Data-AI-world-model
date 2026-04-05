"""Runic Metaphysics ECS components — Hamingja, Runic Charge, Ancestral Resonance.

These components implement the spiritual/metaphysical layer of the WYRD world
model.  They are fully deterministic and ECS-compatible — no LLM involvement
at the component level.

Hamingja:  Norse concept of personal luck/soul-force.  Drifts based on actions
           and environmental resonance.  Ranges [-1.0, 1.0].

RunicCharge: Accumulated symbolic energy from rune invocations.  Each named
             rune has an independent charge in [0.0, 1.0] that decays over
             time unless reinforced.

AncestralResonance: Degree to which an entity is connected to its ancestral
                    line.  Affects how strongly it can draw on ancestral memory
                    fragments.  Range [0.0, 1.0].
"""
from __future__ import annotations

from typing import ClassVar, Literal

from pydantic import Field

from wyrdforge.ecs.component import Component, register_component


@register_component
class HamingjaComponent(Component):
    """Personal luck/soul-force for an entity.

    Attributes:
        score:          Current hamingja value in [-1.0, 1.0].
                        Positive = fortunate, negative = wyrd-cursed.
        peak:           Historical maximum (used for resonance calculations).
        drift_rate:     How fast score drifts per engine tick (0.0 = frozen).
        last_event_id:  Record ID of the last event that changed the score.
    """

    _type_key: ClassVar[str] = "hamingja"
    component_type: Literal["hamingja"] = "hamingja"

    score: float = Field(default=0.0, ge=-1.0, le=1.0)
    peak: float = Field(default=0.0, ge=-1.0, le=1.0)
    drift_rate: float = Field(default=0.01, ge=0.0, le=1.0)
    last_event_id: str | None = None


@register_component
class RunicChargeComponent(Component):
    """Accumulated runic charge per named rune.

    Attributes:
        charges:  Map of rune_name → charge in [0.0, 1.0].
                  Example: ``{"fehu": 0.8, "uruz": 0.3}``.
        decay_rate: Fraction of charge lost per engine tick (0.0 = no decay).
        dominant_rune: Rune with the highest current charge, or None.
    """

    _type_key: ClassVar[str] = "runic_charge"
    component_type: Literal["runic_charge"] = "runic_charge"

    charges: dict[str, float] = Field(default_factory=dict)
    decay_rate: float = Field(default=0.05, ge=0.0, le=1.0)
    dominant_rune: str | None = None

    def get_charge(self, rune_name: str) -> float:
        """Return the current charge for a rune (0.0 if not present)."""
        return self.charges.get(rune_name, 0.0)

    def total_charge(self) -> float:
        """Sum of all rune charges."""
        return sum(self.charges.values())


@register_component
class AncestralResonanceComponent(Component):
    """Ancestral connection strength.

    Attributes:
        score:          Overall resonance in [0.0, 1.0].
        lineage_ids:    IDs of ancestral entities in the same world.
        memory_fragments: Short text fragments inherited from ancestors.
        last_communion: ISO timestamp of last resonance reinforcement.
    """

    _type_key: ClassVar[str] = "ancestral_resonance"
    component_type: Literal["ancestral_resonance"] = "ancestral_resonance"

    score: float = Field(default=0.0, ge=0.0, le=1.0)
    lineage_ids: list[str] = Field(default_factory=list)
    memory_fragments: list[str] = Field(default_factory=list)
    last_communion: str | None = None
