from __future__ import annotations

from typing import ClassVar, Literal

from pydantic import Field

from wyrdforge.ecs.component import Component, register_component


class HierarchyLevel:
    """Constants for Yggdrasil hierarchy depth labels."""
    WORLD = "world"
    ZONE = "zone"
    REGION = "region"
    LOCATION = "location"
    SUBLOCATION = "sublocation"
    OBJECT = "object"    # non-spatial container (e.g., chest, bag)


@register_component
class SpatialComponent(Component):
    """Positions an entity within the Yggdrasil spatial hierarchy.

    An entity is placed at exactly one node in the tree. To move it,
    update this component's location_id (and optionally sublocation_id).
    YggdrasilTree validates consistency.
    """

    _type_key: ClassVar[str] = "spatial"
    component_type: Literal["spatial"] = "spatial"

    zone_id: str | None = None
    region_id: str | None = None
    location_id: str | None = None
    sublocation_id: str | None = None

    def most_specific_id(self) -> str | None:
        """Return the deepest non-None location ID."""
        return self.sublocation_id or self.location_id or self.region_id or self.zone_id

    def path(self) -> list[str]:
        """Return the hierarchy path as a list of IDs, from zone to most specific."""
        parts = [self.zone_id, self.region_id, self.location_id, self.sublocation_id]
        return [p for p in parts if p is not None]


@register_component
class ParentComponent(Component):
    """Links an entity to its parent in the Yggdrasil tree.

    Used to build the spatial hierarchy: a sublocation's parent is a location,
    a location's parent is a region, etc.
    """

    _type_key: ClassVar[str] = "parent"
    component_type: Literal["parent"] = "parent"

    parent_entity_id: str | None = None
    hierarchy_level: str = HierarchyLevel.OBJECT  # zone/region/location/sublocation/object


@register_component
class ContainerComponent(Component):
    """Marks an entity as a spatial container with children.

    Children are entity_ids of entities whose parent is this entity.
    Updated by YggdrasilTree as entities are placed/moved.
    """

    _type_key: ClassVar[str] = "container"
    component_type: Literal["container"] = "container"

    children: list[str] = Field(default_factory=list)   # entity_ids
    capacity: int | None = None                          # None = unlimited
    container_type: str = "spatial"                      # spatial | inventory | conceptual

    def add_child(self, entity_id: str) -> None:
        if entity_id not in self.children:
            self.children.append(entity_id)

    def remove_child(self, entity_id: str) -> None:
        if entity_id in self.children:
            self.children.remove(entity_id)

    def is_full(self) -> bool:
        if self.capacity is None:
            return False
        return len(self.children) >= self.capacity
