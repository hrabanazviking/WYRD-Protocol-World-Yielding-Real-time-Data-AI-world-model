from __future__ import annotations

from typing import ClassVar, Literal

from pydantic import Field

from wyrdforge.ecs.component import Component, register_component


@register_component
class PersonaRefComponent(Component):
    """Links an entity to its wyrdforge memory layer persona and bonds.

    This is the bridge between the ECS world model and the AI character layer.
    """

    _type_key: ClassVar[str] = "persona_ref"
    component_type: Literal["persona_ref"] = "persona_ref"

    persona_id: str = ""             # references wyrdforge PersonaPacket
    bond_ids: list[str] = Field(default_factory=list)  # active BondEdge IDs
    is_ai_controlled: bool = False   # True if an LLM drives this character
    llm_model: str = ""              # which model/backend drives this character


@register_component
class HealthComponent(Component):
    """Life / vitality state of a character entity."""

    _type_key: ClassVar[str] = "health"
    component_type: Literal["health"] = "health"

    hp: float = 100.0
    max_hp: float = 100.0
    alive: bool = True
    wounded: bool = False
    wound_notes: str = ""

    def take_damage(self, amount: float) -> None:
        self.hp = max(0.0, self.hp - amount)
        if self.hp == 0.0:
            self.alive = False
        elif self.hp < self.max_hp * 0.5:
            self.wounded = True

    def heal(self, amount: float) -> None:
        if not self.alive:
            return
        self.hp = min(self.max_hp, self.hp + amount)
        if self.hp >= self.max_hp * 0.5:
            self.wounded = False

    def hp_fraction(self) -> float:
        if self.max_hp == 0.0:
            return 0.0
        return round(self.hp / self.max_hp, 4)


@register_component
class FactionComponent(Component):
    """Faction membership and reputation for a character entity."""

    _type_key: ClassVar[str] = "faction"
    component_type: Literal["faction"] = "faction"

    faction_id: str = ""
    faction_name: str = ""
    reputation: dict[str, float] = Field(default_factory=dict)  # faction_id → -1.0..1.0

    def get_reputation(self, faction_id: str) -> float:
        return self.reputation.get(faction_id, 0.0)

    def set_reputation(self, faction_id: str, value: float) -> None:
        self.reputation[faction_id] = max(-1.0, min(1.0, value))

    def adjust_reputation(self, faction_id: str, delta: float) -> None:
        current = self.get_reputation(faction_id)
        self.set_reputation(faction_id, current + delta)
