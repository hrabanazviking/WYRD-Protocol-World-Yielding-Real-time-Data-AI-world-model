from __future__ import annotations

from typing import ClassVar, Literal

from pydantic import Field

from wyrdforge.ecs.component import Component, register_component


@register_component
class PhysicalComponent(Component):
    """Physical properties of a tangible entity."""

    _type_key: ClassVar[str] = "physical"
    component_type: Literal["physical"] = "physical"

    weight: float = 0.0          # in kg
    size: str = "medium"         # tiny / small / medium / large / massive
    tangible: bool = True        # False for spirits, concepts, etc.
    material: str = ""           # iron, wood, cloth, bone, etc.
    condition: str = "intact"    # intact / worn / damaged / broken / destroyed


@register_component
class InventoryComponent(Component):
    """Items carried or held by an entity."""

    _type_key: ClassVar[str] = "inventory"
    component_type: Literal["inventory"] = "inventory"

    contains: list[str] = Field(default_factory=list)   # entity_ids of held items
    capacity_kg: float | None = None                     # None = unlimited carry
    capacity_slots: int | None = None                    # None = unlimited slots

    def add_item(self, entity_id: str) -> None:
        if entity_id not in self.contains:
            self.contains.append(entity_id)

    def remove_item(self, entity_id: str) -> bool:
        if entity_id in self.contains:
            self.contains.remove(entity_id)
            return True
        return False

    def has_item(self, entity_id: str) -> bool:
        return entity_id in self.contains
