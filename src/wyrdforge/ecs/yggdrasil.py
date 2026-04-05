from __future__ import annotations

from wyrdforge.ecs.components.identity import NameComponent
from wyrdforge.ecs.components.spatial import (
    ContainerComponent,
    HierarchyLevel,
    ParentComponent,
    SpatialComponent,
)
from wyrdforge.ecs.entity import Entity
from wyrdforge.ecs.world import World


class YggdrasilTree:
    """Manages the spatial hierarchy of the world.

    The Yggdrasil Hierarchy nests containers:
        Zone → Region → Location → Sub-location

    Each spatial entity has a ParentComponent pointing to its parent,
    and a ContainerComponent listing its children. This service provides
    navigation, placement, and movement operations built on top of the World.

    The tree is not stored separately — it lives entirely in ECS components
    so that persistence, query, and serialization are handled uniformly.
    """

    def __init__(self, world: World) -> None:
        self._world = world

    # ------------------------------------------------------------------
    # Node creation helpers
    # ------------------------------------------------------------------

    def create_zone(self, *, zone_id: str, name: str, description: str = "") -> Entity:
        return self._create_spatial_node(
            entity_id=zone_id,
            name=name,
            description=description,
            level=HierarchyLevel.ZONE,
            parent_id=None,
            tags={"zone", "spatial_node"},
        )

    def create_region(self, *, region_id: str, name: str, description: str = "", parent_zone_id: str) -> Entity:
        return self._create_spatial_node(
            entity_id=region_id,
            name=name,
            description=description,
            level=HierarchyLevel.REGION,
            parent_id=parent_zone_id,
            tags={"region", "spatial_node"},
        )

    def create_location(
        self, *, location_id: str, name: str, description: str = "", parent_region_id: str
    ) -> Entity:
        return self._create_spatial_node(
            entity_id=location_id,
            name=name,
            description=description,
            level=HierarchyLevel.LOCATION,
            parent_id=parent_region_id,
            tags={"location", "spatial_node"},
        )

    def create_sublocation(
        self, *, sublocation_id: str, name: str, description: str = "", parent_location_id: str
    ) -> Entity:
        return self._create_spatial_node(
            entity_id=sublocation_id,
            name=name,
            description=description,
            level=HierarchyLevel.SUBLOCATION,
            parent_id=parent_location_id,
            tags={"sublocation", "spatial_node"},
        )

    # ------------------------------------------------------------------
    # Entity placement & movement
    # ------------------------------------------------------------------

    def place_entity(self, entity_id: str, *, location_id: str, sublocation_id: str | None = None) -> None:
        """Place a non-spatial entity (NPC, item, player) at a location.

        The entity gets a SpatialComponent filled from the location node's
        own hierarchy path. Optionally refined to a sublocation.
        """
        world = self._world
        world._require_entity(entity_id)
        loc_entity = world.get_entity(location_id)
        if loc_entity is None:
            raise KeyError(f"Location entity '{location_id}' not found")

        # Build hierarchy path from the location node
        loc_parent = world.get_component(location_id, "parent")
        region_id: str | None = None
        zone_id: str | None = None
        if loc_parent and isinstance(loc_parent, ParentComponent):
            region_id = loc_parent.parent_entity_id
            if region_id:
                reg_parent = world.get_component(region_id, "parent")
                if reg_parent and isinstance(reg_parent, ParentComponent):
                    zone_id = reg_parent.parent_entity_id

        spatial = SpatialComponent(
            entity_id=entity_id,
            zone_id=zone_id,
            region_id=region_id,
            location_id=location_id,
            sublocation_id=sublocation_id,
        )
        world.add_component(entity_id, spatial)

        # Register entity in the container
        target_container_id = sublocation_id or location_id
        container = world.get_component(target_container_id, "container")
        if container and isinstance(container, ContainerComponent):
            container.add_child(entity_id)
            container.touch()

    def move_entity(self, entity_id: str, *, location_id: str, sublocation_id: str | None = None) -> None:
        """Move an already-placed entity to a new location."""
        world = self._world
        # Remove from old container
        old_spatial = world.get_component(entity_id, "spatial")
        if old_spatial and isinstance(old_spatial, SpatialComponent):
            old_target = old_spatial.sublocation_id or old_spatial.location_id
            if old_target:
                old_container = world.get_component(old_target, "container")
                if old_container and isinstance(old_container, ContainerComponent):
                    old_container.remove_child(entity_id)
                    old_container.touch()
        # Place at new location
        self.place_entity(entity_id, location_id=location_id, sublocation_id=sublocation_id)

    # ------------------------------------------------------------------
    # Navigation queries
    # ------------------------------------------------------------------

    def get_location_of(self, entity_id: str) -> str | None:
        """Return the location_id where entity currently is."""
        spatial = self._world.get_component(entity_id, "spatial")
        if spatial and isinstance(spatial, SpatialComponent):
            return spatial.most_specific_id()
        return None

    def get_spatial_path(self, entity_id: str) -> list[str]:
        """Return [zone_id, region_id, location_id, sublocation_id] for entity."""
        spatial = self._world.get_component(entity_id, "spatial")
        if spatial and isinstance(spatial, SpatialComponent):
            return spatial.path()
        return []

    def get_children(self, container_entity_id: str) -> list[Entity]:
        """Return all direct children of a container node."""
        container = self._world.get_component(container_entity_id, "container")
        if not container or not isinstance(container, ContainerComponent):
            return []
        return [
            e for child_id in container.children
            if (e := self._world.get_entity(child_id)) is not None
        ]

    def get_co_located(self, entity_id: str) -> list[Entity]:
        """Return all entities sharing the same most-specific location."""
        loc_id = self.get_location_of(entity_id)
        if not loc_id:
            return []
        container = self._world.get_component(loc_id, "container")
        if not container or not isinstance(container, ContainerComponent):
            return []
        return [
            e for child_id in container.children
            if child_id != entity_id and (e := self._world.get_entity(child_id)) is not None and e.active
        ]

    def get_ancestors(self, entity_id: str) -> list[Entity]:
        """Return the chain of parent spatial nodes from entity up to zone."""
        ancestors: list[Entity] = []
        parent_comp = self._world.get_component(entity_id, "parent")
        while parent_comp and isinstance(parent_comp, ParentComponent) and parent_comp.parent_entity_id:
            parent = self._world.get_entity(parent_comp.parent_entity_id)
            if parent is None:
                break
            ancestors.append(parent)
            parent_comp = self._world.get_component(parent.entity_id, "parent")
        return ancestors

    def find_by_name(self, name: str, *, case_sensitive: bool = False) -> list[Entity]:
        """Search all spatial nodes by name."""
        results = []
        for entity, comp in self._world.iter_components("name"):
            if isinstance(comp, NameComponent) and entity.has_tag("spatial_node"):
                match_name = comp.name if case_sensitive else comp.name.lower()
                search = name if case_sensitive else name.lower()
                if search in match_name:
                    results.append(entity)
        return results

    def entities_at(self, location_id: str) -> list[Entity]:
        """All active entities placed at a given location (not spatial nodes themselves)."""
        return [
            e for e in self.get_children(location_id)
            if not e.has_tag("spatial_node")
        ]

    def describe_tree(self) -> str:
        """Return a human-readable tree view of the Yggdrasil hierarchy."""
        lines: list[str] = [f"Yggdrasil — {self._world.world_name}"]
        zones = self._world.query_by_tag("zone")
        for zone in zones:
            lines.append(f"  [Zone] {self._label(zone)}")
            for region in self.get_children(zone.entity_id):
                if not region.has_tag("spatial_node"):
                    continue
                lines.append(f"    [Region] {self._label(region)}")
                for location in self.get_children(region.entity_id):
                    if not location.has_tag("spatial_node"):
                        continue
                    lines.append(f"      [Location] {self._label(location)}")
                    for sub in self.get_children(location.entity_id):
                        if not sub.has_tag("spatial_node"):
                            continue
                        lines.append(f"        [Sub] {self._label(sub)}")
        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _label(self, entity: Entity) -> str:
        name_comp = self._world.get_component(entity.entity_id, "name")
        name = name_comp.name if isinstance(name_comp, NameComponent) else entity.entity_id  # type: ignore[union-attr]
        return f"{name} ({entity.entity_id})"

    def _create_spatial_node(
        self,
        *,
        entity_id: str,
        name: str,
        description: str,
        level: str,
        parent_id: str | None,
        tags: set[str],
    ) -> Entity:
        world = self._world
        entity = world.create_entity(entity_id=entity_id, tags=tags)

        world.add_component(entity_id, NameComponent(entity_id=entity_id, name=name))
        world.add_component(
            entity_id,
            ParentComponent(
                entity_id=entity_id,
                parent_entity_id=parent_id,
                hierarchy_level=level,
            ),
        )
        world.add_component(entity_id, ContainerComponent(entity_id=entity_id))
        if description:
            from wyrdforge.ecs.components.identity import DescriptionComponent
            world.add_component(
                entity_id, DescriptionComponent(entity_id=entity_id, short_desc=description)
            )

        # Register as child of parent container
        if parent_id:
            parent_container = world.get_component(parent_id, "container")
            if parent_container and isinstance(parent_container, ContainerComponent):
                parent_container.add_child(entity_id)
                parent_container.touch()

        return entity
