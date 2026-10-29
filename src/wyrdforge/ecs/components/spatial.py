from __future__ import annotations

import math
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
class PositionComponent(Component):
    """Metric coordinates of an entity — the spatial core (Phase B3).

    Design decision (recorded in the campaign state file): coordinates
    are a SEPARATE component, not fields on :class:`SpatialComponent`.
    Hierarchy placement (zone/region/location membership, owned by
    ``SpatialComponent`` + YggdrasilTree) and metric position are
    orthogonal facts: an entity can be placed in a location with no
    coordinates, and can carry coordinates in a free space with no
    hierarchy node. The Second Life crew's ``SLPositionComponent``
    reached the same shape independently (a position component beside,
    not inside, ``SpatialComponent``). A separate type also leaves
    ``SpatialComponent``'s serialized form untouched — no migration.

    Coordinates are 3D Euclidean, in metres, as plain floats. They are
    only comparable WITHIN one coordinate frame: ``frame_id`` names
    the frame the coordinates live in (e.g. a region or scene id);
    ``None`` is the default frame. Distance across frames is
    undefined and the Oracle refuses it (returns ``None`` / excludes
    the entity) rather than inventing a number.

    Movement contract: prefer ``World.set_position()`` (World-mediated,
    under the world lock). Direct field assignment (``pos.x = 5.0``)
    is also safe for queries: the Oracle's grid-hash index is rebuilt
    from the live components at query time (see
    ``ecs/spatial_index.py``), so no mutation path can leave a stale
    index behind — the same lesson Phase B2 learned for persistence.
    """

    _type_key: ClassVar[str] = "position"
    component_type: Literal["position"] = "position"

    x: float = 0.0
    y: float = 0.0
    z: float = 0.0
    frame_id: str | None = None

    @property
    def position(self) -> tuple[float, float, float]:
        """The coordinates as an ``(x, y, z)`` tuple, in metres."""
        return (self.x, self.y, self.z)

    def distance_to(self, other: "PositionComponent") -> float | None:
        """Euclidean distance to another position, in metres.

        Returns ``None`` when the two positions live in different
        coordinate frames — cross-frame distance is undefined, never
        approximated.
        """
        if self.frame_id != other.frame_id:
            return None
        return math.dist(self.position, other.position)

    def distance_squared_to_xyz(self, x: float, y: float, z: float) -> float:
        """Squared distance to a raw point in this component's frame."""
        dx = self.x - x
        dy = self.y - y
        dz = self.z - z
        return dx * dx + dy * dy + dz * dz


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
