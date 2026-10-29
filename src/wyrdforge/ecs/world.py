from __future__ import annotations

import threading
from collections import defaultdict
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Iterator

from wyrdforge.ecs.component import Component
from wyrdforge.ecs.components.spatial import PositionComponent
from wyrdforge.ecs.entity import Entity, _new_id, _now

if TYPE_CHECKING:
    from wyrdforge.runtime.events import EventBus

#: Topics emitted by World when wired to an EventBus (opt-in via ``bus=``).
_WORLD_TOPICS = (
    "world.entity_created",
    "world.entity_removed",
    "world.component_added",
    "world.component_removed",
)


def _register_world_topics(bus: "EventBus") -> None:
    """Register the world.* topics once; tolerate double registration."""
    for topic in _WORLD_TOPICS:
        try:
            bus.register_topic(topic)
        except ValueError:
            pass  # already registered — another producer got here first


class World:
    """The ECS world container.

    Holds all entities and their components. Maintains indexes so that
    queries by tag or component type are O(1) set lookups rather than
    full scans.

    Thread-safety discipline (Phase B1):

    * One re-entrant lock — :attr:`lock` — guards ALL registry state:
      the entity dict, the component dict, and both indexes. Every
      public method in this class performs its state access while
      holding that lock, so a mutation (or a multi-step query) is
      atomic with respect to other threads.
    * The lock is an ``RLock`` (the EventBus's house pattern,
      ``runtime/events.py``) because compound operations nest: e.g.
      ``YggdrasilTree`` holds the world lock across a whole placement
      while calling back into ``World`` methods, and the Oracle holds
      it across a whole query while calling helpers.
    * Bus events are published AFTER the mutating method's own
      critical section, never inside it: state first, announce after.
      (A caller that itself holds ``world.lock`` across a compound
      operation — YggdrasilTree does — will therefore see nested World
      emits published under its own hold. That is the same posture as
      the bus itself, which delivers synchronously under its lock with
      re-entrant subscribers as a documented pattern; a bus subscriber
      must never block waiting on another thread's world access.)
    * Lock ordering: the world lock is the only ECS lock. Code that
      needs consistency across several World calls (YggdrasilTree,
      PassiveOracle, WorldStore.save) acquires ``world.lock`` itself;
      it must not hold any other lock that World methods could reach
      while doing so (World methods reach only the bus, and only after
      releasing this lock).
    * Returned ``Entity``/``Component`` objects are the live objects,
      exactly as before B1. The lock guarantees the *registry and
      indexes* are consistent; it cannot police a caller that mutates
      a returned component's fields directly. Structural changes must
      go through World/Yggdrasil methods (which hold the lock); the
      tree's own compound mutations in ``ecs/yggdrasil.py`` do so.
    """

    def __init__(
        self,
        world_id: str,
        world_name: str = "",
        *,
        bus: "EventBus | None" = None,
    ) -> None:
        # The lock exists before anything else: every other field is
        # guarded state, and bus registration below must not race a
        # (paranoid) early publish.
        self._lock = threading.RLock()
        self.world_id: str = world_id
        self.world_name: str = world_name or world_id
        self.created_at: datetime = _now()
        # Opt-in inner-communications wiring: bus=None preserves the exact
        # historical behavior; a bus wires this World into the EventBus.
        self._bus = bus
        if self._bus is not None:
            _register_world_topics(self._bus)

        # World identity in the registry of worlds (Roadmap Worlds, Slice 0).
        # Declared via identify(); None until then — identity is declared,
        # never assumed.
        self.identity = None

        # Primary stores
        self._entities: dict[str, Entity] = {}
        # entity_id → {component_type: Component}
        self._components: dict[str, dict[str, Component]] = defaultdict(dict)

        # Indexes for fast queries
        self._tag_index: dict[str, set[str]] = defaultdict(set)          # tag → entity_ids
        self._comp_type_index: dict[str, set[str]] = defaultdict(set)    # comp_type → entity_ids

    @property
    def lock(self) -> threading.RLock:
        """The re-entrant lock guarding all World registry state.

        Exposed (additive, Phase B1) so compound operations built on
        top of World — ``YggdrasilTree`` placements, ``PassiveOracle``
        queries, ``WorldStore.save`` snapshots — can hold one
        consistent view across several World calls. Re-entrant: World
        methods called while it is held simply re-enter.
        """
        return self._lock

    # ------------------------------------------------------------------
    # Entity operations
    # ------------------------------------------------------------------

    def create_entity(self, *, entity_id: str | None = None, tags: set[str] | None = None) -> Entity:
        """Create a new entity and add it to the world."""
        eid = entity_id or _new_id()
        with self._lock:
            if eid in self._entities:
                raise ValueError(f"Entity '{eid}' already exists in this world")
            entity = Entity(entity_id=eid, tags=set(tags or []))
            self._entities[eid] = entity
            for tag in entity.tags:
                self._tag_index[tag].add(eid)
            emit_tags = sorted(entity.tags)
        self._emit(
            "world.entity_created",
            {"entity_id": eid, "tags": emit_tags},
        )
        return entity

    def get_entity(self, entity_id: str) -> Entity | None:
        with self._lock:
            return self._entities.get(entity_id)

    def remove_entity(self, entity_id: str) -> None:
        """Remove entity and all its components. Non-destructive: raises if missing."""
        with self._lock:
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
        self._emit("world.entity_removed", {"entity_id": entity_id})

    def tag_entity(self, entity_id: str, tag: str) -> None:
        with self._lock:
            entity = self._require_entity(entity_id)
            entity.add_tag(tag)
            self._tag_index[tag].add(entity_id)

    def untag_entity(self, entity_id: str, tag: str) -> None:
        with self._lock:
            entity = self._require_entity(entity_id)
            entity.remove_tag(tag)
            self._tag_index[tag].discard(entity_id)

    def all_entities(self, *, active_only: bool = True) -> list[Entity]:
        with self._lock:
            if active_only:
                return [e for e in self._entities.values() if e.active]
            return list(self._entities.values())

    def entity_count(self) -> int:
        with self._lock:
            return len(self._entities)

    # ------------------------------------------------------------------
    # Component operations
    # ------------------------------------------------------------------

    def add_component(self, entity_id: str, component: Component) -> None:
        """Attach a component to an entity. Replaces existing component of the same type."""
        comp_type = component.component_type
        with self._lock:
            self._require_entity(entity_id)
            if component.entity_id != entity_id:
                raise ValueError(
                    f"Component entity_id '{component.entity_id}' does not match target '{entity_id}'"
                )
            self._components[entity_id][comp_type] = component
            self._comp_type_index[comp_type].add(entity_id)
        self._emit(
            "world.component_added",
            {"entity_id": entity_id, "component_type": comp_type},
        )

    def create_entity_with_component(
        self,
        *,
        entity_id: str,
        tags: set[str] | None = None,
        component: Component,
        stamp: datetime | None = None,
    ) -> Entity:
        """Create an entity and attach one component in a single pass.

        Exactly equivalent to ``create_entity(entity_id=entity_id,
        tags=tags)`` followed by ``add_component(entity_id,
        component)`` — minus the redundant re-lookup between the two.
        The component keeps whatever timestamps it was constructed
        with. Carries the same guards with the same errors: duplicate
        entity id → ``ValueError``; component ``entity_id`` mismatch →
        ``ValueError``. ``tags`` is copied, exactly like
        :meth:`create_entity`.

        ``stamp``: when provided, one shared wall-clock stamp assigned
        to both ``created_at`` and ``updated_at`` (Volmarr-authorized
        2026-09-27: the microsecond differences between the default
        factories' separate reads are implementation noise, not a
        contract). When None, the dataclass default factories do their
        own reads, exactly like :meth:`create_entity`.
        """
        with self._lock:
            if entity_id in self._entities:
                raise ValueError(f"Entity '{entity_id}' already exists in this world")
            if component.entity_id != entity_id:
                raise ValueError(
                    f"Component entity_id '{component.entity_id}' does not match target '{entity_id}'"
                )
            if stamp is None:
                entity = Entity(entity_id=entity_id, tags=set(tags or []))
            else:
                entity = Entity(
                    entity_id=entity_id, tags=set(tags or []),
                    created_at=stamp, updated_at=stamp,
                )
            self._entities[entity_id] = entity
            for tag in entity.tags:
                self._tag_index[tag].add(entity_id)
            comp_type = component.component_type
            self._components[entity_id][comp_type] = component
            self._comp_type_index[comp_type].add(entity_id)
            emit_tags = sorted(entity.tags)
        self._emit(
            "world.entity_created",
            {"entity_id": entity_id, "tags": emit_tags},
        )
        self._emit(
            "world.component_added",
            {"entity_id": entity_id, "component_type": comp_type},
        )
        return entity

    # ------------------------------------------------------------------
    # Metric position (Phase B3 — spatial core)
    # ------------------------------------------------------------------

    def get_position(self, entity_id: str) -> PositionComponent | None:
        """Return the entity's PositionComponent, or None if it has none."""
        comp = self.get_component(entity_id, "position")
        return comp if isinstance(comp, PositionComponent) else None

    def set_position(
        self,
        entity_id: str,
        x: float,
        y: float,
        z: float,
        *,
        frame_id: str | None = None,
    ) -> PositionComponent:
        """Set an entity's metric position — the World-mediated move API.

        Creates the entity's ``PositionComponent`` on first use and
        mutates it in place afterwards (under the world lock, so a
        concurrent Oracle query sees the position either entirely
        before or entirely after the move). ``frame_id=None`` leaves
        an existing component's frame unchanged; on creation it means
        the default frame. Direct field assignment on the returned
        component is also safe for queries — the Oracle's spatial
        index is rebuilt from live components at query time (see
        ``ecs/spatial_index.py``) — but this method is the contract
        callers should prefer: it is atomic and it ``touch()``es the
        component, so the move is visible to persistence timestamps
        as well as to the B2 fingerprint (which sees the changed
        coordinates either way).
        """
        created = False
        with self._lock:
            self._require_entity(entity_id)
            comp = self._components.get(entity_id, {}).get("position")
            if isinstance(comp, PositionComponent):
                comp.x = float(x)
                comp.y = float(y)
                comp.z = float(z)
                if frame_id is not None:
                    comp.frame_id = frame_id
                comp.touch()
                return comp
            comp = PositionComponent(
                entity_id=entity_id,
                x=float(x),
                y=float(y),
                z=float(z),
                frame_id=frame_id,
            )
            self._components[entity_id]["position"] = comp
            self._comp_type_index["position"].add(entity_id)
            created = True
        if created:
            self._emit(
                "world.component_added",
                {"entity_id": entity_id, "component_type": "position"},
            )
        return comp

    def get_component(self, entity_id: str, component_type: str) -> Component | None:
        with self._lock:
            return self._components.get(entity_id, {}).get(component_type)

    def get_component_typed(self, entity_id: str, component_type: str, cls: type) -> object | None:
        comp = self.get_component(entity_id, component_type)
        if comp is not None and not isinstance(comp, cls):
            raise TypeError(f"Expected {cls.__name__}, got {type(comp).__name__}")
        return comp

    def get_all_components(self, entity_id: str) -> list[Component]:
        with self._lock:
            return list(self._components.get(entity_id, {}).values())

    def has_component(self, entity_id: str, component_type: str) -> bool:
        with self._lock:
            return component_type in self._components.get(entity_id, {})

    def remove_component(self, entity_id: str, component_type: str) -> None:
        removed = False
        with self._lock:
            self._require_entity(entity_id)
            if component_type in self._components.get(entity_id, {}):
                del self._components[entity_id][component_type]
                self._comp_type_index[component_type].discard(entity_id)
                removed = True
        if removed:
            self._emit(
                "world.component_removed",
                {"entity_id": entity_id, "component_type": component_type},
            )

    # ------------------------------------------------------------------
    # Query operations
    # ------------------------------------------------------------------

    def query_by_tag(self, tag: str, *, active_only: bool = True) -> list[Entity]:
        with self._lock:
            ids = self._tag_index.get(tag, set())
            entities = [self._entities[eid] for eid in ids if eid in self._entities]
            if active_only:
                entities = [e for e in entities if e.active]
            return entities

    def query_by_tags(self, tags: set[str], *, active_only: bool = True) -> list[Entity]:
        """Return entities that have ALL of the given tags."""
        if not tags:
            return self.all_entities(active_only=active_only)
        with self._lock:
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
        with self._lock:
            ids = self._comp_type_index.get(component_type, set())
            entities = [self._entities[eid] for eid in ids if eid in self._entities]
            if active_only:
                entities = [e for e in entities if e.active]
            return entities

    def query_with_components(self, component_types: list[str], *, active_only: bool = True) -> list[Entity]:
        """Return entities that have ALL of the given component types."""
        if not component_types:
            return self.all_entities(active_only=active_only)
        with self._lock:
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
        """Yield (entity, component) pairs for all entities with this component.

        Phase B1: the pairs are materialised under the world lock and
        then yielded from that snapshot. The pre-B1 body snapshotted
        only the id set and resolved entities/components lazily during
        iteration, so a concurrent mutation could raise mid-iteration
        or yield a torn view; holding the lock across a generator's
        yields instead would let a slow consumer stall every writer
        for an unbounded time. A materialised snapshot is the sound
        middle: one consistent view, no lock held while yielding.
        """
        with self._lock:
            pairs: list[tuple[Entity, Component]] = []
            for entity_id in list(self._comp_type_index.get(component_type, set())):
                entity = self._entities.get(entity_id)
                comp = self._components.get(entity_id, {}).get(component_type)
                if entity and comp and entity.active:
                    pairs.append((entity, comp))
        yield from pairs

    # ------------------------------------------------------------------
    # World identity (Roadmap Worlds, Slice 0)
    # ------------------------------------------------------------------
    def identify(self, *, kind: str = "wyrd", reality: str = "potential",
                 description: str = "", source: str = ""):
        """Declare this world's identity in the registry of worlds.

        kind is always "wyrd" for WYRD worlds; reality is "manifest" only
        when the world models manifest entities, otherwise "potential".
        """
        from wyrdforge.ecs.components.world_identity import WorldIdentity
        with self._lock:
            self.identity = WorldIdentity(
                world_id=self.world_id,
                kind=kind,
                reality=reality,
                description=description or self.world_name,
                source=source or "WYRD Protocol ECS world",
            )
            return self.identity

    def registry_entry(self) -> dict:
        """The handshake dict for Verðandi's WorldRegistry.register()."""
        from wyrdforge.ecs.components.world_identity import UnidentifiedWorldError
        with self._lock:
            if self.identity is None:
                raise UnidentifiedWorldError(
                    f"World '{self.world_id}' has no identity — call identify() first.")
            return self.identity.registry_entry()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _emit(self, topic: str, payload: dict) -> None:
        """Publish an event envelope; never disturb world operations.

        No-op when this World is not bus-wired.  A failing bus must not
        break ECS semantics, so publish errors are swallowed.

        World methods invoke this AFTER their own critical section
        (Phase B1 — see the class docstring's lock-ordering rule).
        """
        bus = getattr(self, "_bus", None)
        if bus is None:
            return
        try:
            bus.publish(topic, payload, source="ecs.world")
        except Exception:
            pass

    def _require_entity(self, entity_id: str) -> Entity:
        with self._lock:
            entity = self._entities.get(entity_id)
            if entity is None:
                raise KeyError(f"Entity '{entity_id}' not found in world '{self.world_id}'")
            return entity

    def __repr__(self) -> str:
        with self._lock:
            return (
                f"World(id={self.world_id!r}, entities={len(self._entities)}, "
                f"component_types={len(self._comp_type_index)})"
            )
