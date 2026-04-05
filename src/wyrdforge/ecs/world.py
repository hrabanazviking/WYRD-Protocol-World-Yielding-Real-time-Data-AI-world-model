from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from typing import Iterator

from wyrdforge.ecs.component import Component
from wyrdforge.ecs.entity import Entity, _new_id, _now


class World:
    """The ECS world container.

    Holds all entities and their components. Maintains indexes so that
    queries by tag or component type are O(1) set lookups rather than
    full scans.
    """

    def __init__(self, world_id: str, world_name: str = "") -> None:
        self.world_id: str = world_id
        self.world_name: str = world_name or world_id
        self.created_at: datetime = _now()

        # Primary stores
        self._entities: dict[str, Entity] = {}
        # entity_id → {component_type: Component}
        self._components: dict[str, dict[str, Component]] = defaultdict(dict)

        # Indexes for fast queries
        self._tag_index: dict[str, set[str]] = defaultdict(set)          # tag → entity_ids
        self._comp_type_index: dict[str, set[str]] = defaultdict(set)    # comp_type → entity_ids

    # ------------------------------------------------------------------
    # Entity operations
    # ------------------------------------------------------------------

    def create_entity(self, *, entity_id: str | None = None, tags: set[str] | None = None) -> Entity:
        """Create a new entity and add it to the world."""
        eid = entity_id or _new_id()
        if eid in self._entities:
            raise ValueError(f"Entity '{eid}' already exists in this world")
        entity = Entity(entity_id=eid, tags=set(tags or []))
        self._entities[eid] = entity
        for tag in entity.tags:
            self._tag_index[tag].add(eid)
        return entity

    def get_entity(self, entity_id: str) -> Entity | None:
        return self._entities.get(entity_id)

    def remove_entity(self, entity_id: str) -> None:
        """Remove entity and all its components. Non-destructive: raises if missing."""
        entity = self._entities.pop(entity_id, None)
        if entity is None:
            raise KeyError(f"Entity '{entity_id}' not found")
        # Remove from tag index
        for tag in entity.tags:
            self._tag_index[tag].discard(entity_id)
        # Remove all components
        for comp_type in list(self._components.get(entity_id, {}).keys()):
            self._comp_type_index[comp_type].discard(entity_id)
        self._components.pop(entity_id, None)

    def tag_entity(self, entity_id: str, tag: str) -> None:
        entity = self._require_entity(entity_id)
        entity.add_tag(tag)
        self._tag_index[tag].add(entity_id)

    def untag_entity(self, entity_id: str, tag: str) -> None:
        entity = self._require_entity(entity_id)
        entity.remove_tag(tag)
        self._tag_index[tag].discard(entity_id)

    def all_entities(self, *, active_only: bool = True) -> list[Entity]:
        if active_only:
            return [e for e in self._entities.values() if e.active]
        return list(self._entities.values())

    def entity_count(self) -> int:
        return len(self._entities)

    # ------------------------------------------------------------------
    # Component operations
    # ------------------------------------------------------------------

    def add_component(self, entity_id: str, component: Component) -> None:
        """Attach a component to an entity. Replaces existing component of the same type."""
        self._require_entity(entity_id)
        if component.entity_id != entity_id:
            raise ValueError(
                f"Component entity_id '{component.entity_id}' does not match target '{entity_id}'"
            )
        comp_type = component.component_type
        self._components[entity_id][comp_type] = component
        self._comp_type_index[comp_type].add(entity_id)

    def get_component(self, entity_id: str, component_type: str) -> Component | None:
        return self._components.get(entity_id, {}).get(component_type)

    def get_component_typed(self, entity_id: str, component_type: str, cls: type) -> object | None:
        comp = self.get_component(entity_id, component_type)
        if comp is not None and not isinstance(comp, cls):
            raise TypeError(f"Expected {cls.__name__}, got {type(comp).__name__}")
        return comp

    def get_all_components(self, entity_id: str) -> list[Component]:
        return list(self._components.get(entity_id, {}).values())

    def has_component(self, entity_id: str, component_type: str) -> bool:
        return component_type in self._components.get(entity_id, {})

    def remove_component(self, entity_id: str, component_type: str) -> None:
        self._require_entity(entity_id)
        if component_type in self._components.get(entity_id, {}):
            del self._components[entity_id][component_type]
            self._comp_type_index[component_type].discard(entity_id)

    # ------------------------------------------------------------------
    # Query operations
    # ------------------------------------------------------------------

    def query_by_tag(self, tag: str, *, active_only: bool = True) -> list[Entity]:
        ids = self._tag_index.get(tag, set())
        entities = [self._entities[eid] for eid in ids if eid in self._entities]
        if active_only:
            entities = [e for e in entities if e.active]
        return entities

    def query_by_tags(self, tags: set[str], *, active_only: bool = True) -> list[Entity]:
        """Return entities that have ALL of the given tags."""
        if not tags:
            return self.all_entities(active_only=active_only)
        ids: set[str] | None = None
        for tag in tags:
            tag_ids = self._tag_index.get(tag, set())
            ids = tag_ids if ids is None else ids & tag_ids
        if ids is None:
            return []
        entities = [self._entities[eid] for eid in ids if eid in self._entities]
        if active_only:
            entities = [e for e in entities if e.active]
        return entities

    def query_with_component(self, component_type: str, *, active_only: bool = True) -> list[Entity]:
        ids = self._comp_type_index.get(component_type, set())
        entities = [self._entities[eid] for eid in ids if eid in self._entities]
        if active_only:
            entities = [e for e in entities if e.active]
        return entities

    def query_with_components(self, component_types: list[str], *, active_only: bool = True) -> list[Entity]:
        """Return entities that have ALL of the given component types."""
        if not component_types:
            return self.all_entities(active_only=active_only)
        ids: set[str] | None = None
        for ct in component_types:
            ct_ids = self._comp_type_index.get(ct, set())
            ids = ct_ids if ids is None else ids & ct_ids
        if ids is None:
            return []
        entities = [self._entities[eid] for eid in ids if eid in self._entities]
        if active_only:
            entities = [e for e in entities if e.active]
        return entities

    def iter_components(self, component_type: str) -> Iterator[tuple[Entity, Component]]:
        """Yield (entity, component) pairs for all entities with this component."""
        for entity_id in list(self._comp_type_index.get(component_type, set())):
            entity = self._entities.get(entity_id)
            comp = self._components.get(entity_id, {}).get(component_type)
            if entity and comp and entity.active:
                yield entity, comp

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _require_entity(self, entity_id: str) -> Entity:
        entity = self._entities.get(entity_id)
        if entity is None:
            raise KeyError(f"Entity '{entity_id}' not found in world '{self.world_id}'")
        return entity

    def __repr__(self) -> str:
        return (
            f"World(id={self.world_id!r}, entities={self.entity_count()}, "
            f"component_types={len(self._comp_type_index)})"
        )
