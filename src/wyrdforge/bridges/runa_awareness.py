"""RunaSpatialAwareness — Bridge from Yggdrasil to Runa's consciousness.

Exposes spatial queries from the WYRD world model so Runa can answer:
    "Where am I?"
    "Who is nearby?"
    "How do I get from here to there?"
    "What's the state of the world?"

This module is the spatial nervous system — when Runa needs to know about
physical or conceptual location in a world, this is where she looks.

Architecture:
    ┌────────────────────┐
    │ RunaSpatialAwareness│ ←  Call these methods from Hermes skills/tools
    ├────────────────────┤
    │  PassiveOracle     │ ←  Read-only world truth queries
    │  YggdrasilTree     │ ←  Spatial hierarchy traversal
    │  PersistentMemory  │ ←  Canonical facts & policies
    └────────────────────┘

Usage::

    from wyrdforge.bridges.runa_awareness import RunaSpatialAwareness

    awareness = RunaSpatialAwareness(
        world=world,
        memory_store=store,
        yggdrasil=ygg,
    )

    # Where is an entity?
    loc = awareness.where("runa")
    # → {"entity_id": "runa", "location": "midgard:village:market", "path": [...]}

    # What entities are at a location?
    entities = awareness.what_at("midgard:village:market")
    # → [{"entity_id": "runa", "name": "Runa", ...}, ...]

    # Find a path between locations
    path = awareness.pathfind("midgard:home:scene", "midgard:village:market")
    # → ["midgard", "midgard:home", "midgard:home:scene", "midgard:village", ...]

    # Full world state for context injection
    state = awareness.world_state()
    # → {"entities": 42, "locations": 150, "zones": 3, ...}

    # Nerve bridge — emit spatial awareness events to Verðandi
    awareness.bridge_movement("runa", "midgard:village:market", "midgard:home:scene")

Author: Runa Gridweaver Freyjasdottir
Created: 2026-05-14 (T2-5)
"""
from __future__ import annotations

import json
import logging
import os
import socket
import time
from pathlib import Path
from typing import Any, Optional

from wyrdforge.ecs.world import World
from wyrdforge.ecs.yggdrasil import YggdrasilTree
from wyrdforge.oracle.passive_oracle import PassiveOracle
from wyrdforge.persistence.memory_store import PersistentMemoryStore

logger = logging.getLogger("wyrdforge.runa_awareness")

# ─── Verðandi Nerve Socket ──────────────────────────────────────────────
NERVE_SOCKET_PATH = os.environ.get(
    "RUNA_NERVE_SOCKET",
    str(Path.home() / ".hermes" / "state" / "runa.sock"),
)
NERVE_TIMEOUT = 2.0


class RunaSpatialAwareness:
    """Bridge between Yggdrasil spatial hierarchy and Runa's recall.

    Provides a high-level API for spatial queries that can be called
    from Hermes skills, tools, or direct Python imports. When spatial
    events occur (entity movement, proximity changes, location queries),
    this module can optionally bridge them to the Verðandi nerve hub
    for real-time awareness.

    Args:
        world:        The ECS World containing entities and components.
        memory_store:  PersistentMemoryStore for canonical facts.
        yggdrasil:    Optional YggdrasilTree for richer spatial queries.
        nerve_socket: Path to Verðandi nerve socket. If None, nerve
                      bridge is disabled.
    """

    def __init__(
        self,
        world: World,
        memory_store: PersistentMemoryStore | None = None,
        *,
        yggdrasil: YggdrasilTree | None = None,
        nerve_socket: str | Path | None = None,
    ) -> None:
        self._world = world
        self._store = memory_store
        self._ygg = yggdrasil

        # Oracle requires a memory_store — use a minimal in-memory store if not provided
        if memory_store is None:
            try:
                memory_store = PersistentMemoryStore(db_path=":memory:")
            except Exception:
                logger.warning("Could not create in-memory store; oracle queries will be limited")
                memory_store = None

        self._oracle = PassiveOracle(
            world=world,
            memory_store=memory_store,
            yggdrasil=yggdrasil,
        )

        # Nerve bridge — defaults to NERVE_SOCKET_PATH; set nerve_socket="" to disable
        if nerve_socket is not None and nerve_socket == "":
            self._nerve_socket = None  # explicitly disabled
        else:
            self._nerve_socket = Path(nerve_socket or NERVE_SOCKET_PATH)
        self._nerve_enabled = self._nerve_socket is not None and self._nerve_socket.exists()

        logger.info(
            "RunaSpatialAwareness initialized (world=%s, ygg=%s, nerve=%s)",
            world.world_id if hasattr(world, 'world_id') else '?',
            "yes" if yggdrasil else "no",
            "enabled" if self._nerve_enabled else "disabled",
        )

    # ─── Core Spatial Queries ───────────────────────────────────────────

    def where(self, entity_id: str) -> dict[str, Any] | None:
        """Where is an entity? Returns location hierarchy.

        Args:
            entity_id: The entity to locate.

        Returns:
            Dict with location info, or None if entity not found.
            Keys: entity_id, location_id, location_name, zone_id,
                  region_id, path
        """
        result = self._oracle.where_is(entity_id)
        if result is None:
            return None
        return result.model_dump()

    def what_at(self, location_id: str) -> list[dict[str, Any]]:
        """What entities are at a location?

        Args:
            location_id: The location to query.

        Returns:
            List of entity summary dicts at that location.
        """
        entities = self._oracle.who_is_here(location_id)
        return [e.model_dump() for e in entities]

    def what_is(self, entity_id: str) -> dict[str, Any] | None:
        """Full snapshot of an entity — name, status, tags, location, components.

        Args:
            entity_id: The entity to describe.

        Returns:
            Dict with full entity info, or None if not found.
        """
        result = self._oracle.what_is(entity_id)
        if result is None:
            return None
        return result.model_dump()

    def nearby(self, entity_id: str) -> list[dict[str, Any]]:
        """What other entities share this entity's location?

        Args:
            entity_id: The entity whose co-located neighbors to find.

        Returns:
            List of entity summary dicts sharing the same location.
        """
        entities = self._oracle.get_nearby(entity_id)
        return [e.model_dump() for e in entities]

    def get_relations(self, entity_id: str) -> dict[str, Any] | None:
        """Get faction membership and co-presence for an entity.

        Args:
            entity_id: The entity to query.

        Returns:
            Dict with faction info, reputations, and co-located entities.
        """
        result = self._oracle.get_relations(entity_id)
        if result is None:
            return None
        return result.model_dump()

    # ─── Pathfinding ──────────────────────────────────────────────────────

    def pathfind(self, from_id: str, to_id: str) -> list[str]:
        """Find the path between two entities or locations via Yggdrasil.

        Uses entity spatial path if available, otherwise falls back to
        Yggdrasil ancestor traversal. Returns an ordered list of location
        IDs from root to destination.

        Args:
            from_id: Starting entity or location ID.
            to_id:   Destination entity or location ID.

        Returns:
            Ordered list of location IDs forming the path.
            Returns empty list if no path found.
        """
        # If from_id is an entity, resolve to its location
        from_loc = self._resolve_location(from_id)
        to_loc = self._resolve_location(to_id)

        if from_loc is None or to_loc is None:
            logger.warning("pathfind: cannot resolve locations for %s → %s", from_id, to_id)
            return []

        # Find common ancestor and construct path
        from_path = self._get_ancestry(from_loc)
        to_path = self._get_ancestry(to_loc)

        if not from_path or not to_path:
            return [from_loc, to_loc] if from_loc and to_loc else []

        # Find common ancestor
        common_ancestor = None
        for node in from_path:
            if node in to_path:
                common_ancestor = node
                break

        if common_ancestor is None:
            # No common ancestor — return direct hop
            return [from_loc, to_loc]

        # Build path: from → ancestor → to
        path_up = []
        for node in from_path:
            path_up.append(node)
            if node == common_ancestor:
                break

        path_down = []
        found_ancestor = False
        for node in to_path:
            if node == common_ancestor:
                found_ancestor = True
                continue
            if found_ancestor:
                path_down.append(node)

        return path_up + path_down

    def _resolve_location(self, entity_or_loc_id: str) -> str | None:
        """Resolve an entity ID to its location, or return the location ID directly."""
        # Try as entity first
        loc_result = self._oracle.where_is(entity_or_loc_id)
        if loc_result and loc_result.location_id:
            return loc_result.location_id

        # Try as location in Yggdrasil
        if self._ygg:
            try:
                loc_entity = self._world.get_entity(entity_or_loc_id)
                if loc_entity and loc_entity.has_tag("spatial_node"):
                    return entity_or_loc_id
            except Exception:
                pass

        # Assume it's a location ID
        return entity_or_loc_id

    def _get_ancestry(self, location_id: str) -> list[str]:
        """Get the ancestry path from root to this location."""
        if self._ygg is None:
            return [location_id]

        try:
            ancestors = self._ygg.get_ancestors(location_id)
            return [a.entity_id for a in reversed(ancestors)] + [location_id]
        except Exception:
            return [location_id]

    # ─── World State ──────────────────────────────────────────────────────

    def world_state(self) -> dict[str, Any]:
        """Full world state snapshot for context injection.

        Returns a structured summary of the current world including
        entity count, location hierarchy, and active components.
        """
        entities = self._world.all_entities(active_only=True)
        entity_count = len(entities)

        # Count systems if available
        systems_count = len(getattr(self._world, '_systems', []))

        # Build location tree from Yggdrasil if available
        location_tree = None
        zones = 0
        regions = 0
        locations = 0
        if self._ygg:
            try:
                location_tree = self._ygg.describe_tree()
                # Count spatial nodes
                for e in entities:
                    if e.has_tag("spatial_node"):
                        # Classify by hierarchy level
                        spatial = self._world.get_component(e.entity_id, "spatial")
                        if hasattr(spatial, 'hierarchy_level'):
                            level = spatial.hierarchy_level
                            if level and level.value == "zone":
                                zones += 1
                            elif level and level.value == "region":
                                regions += 1
                            elif level and level.value in ("location", "sublocation"):
                                locations += 1
            except Exception:
                location_tree = None

        # Build entity index
        entity_index = {}
        for e in entities[:50]:  # Cap at 50 for performance
            name_comp = self._world.get_component(e.entity_id, "name")
            name = name_comp.content.get("name") if name_comp and hasattr(name_comp, 'content') else None
            entity_index[e.entity_id] = {
                "id": e.entity_id,
                "name": name,
                "tags": list(e.tags) if hasattr(e, 'tags') else [],
                "active": getattr(e, 'active', True),
            }

        return {
            "world_id": getattr(self._world, 'world_id', 'unknown'),
            "entity_count": entity_count,
            "active_systems": systems_count,
            "zones": zones,
            "regions": regions,
            "locations": locations,
            "location_tree": location_tree,
            "entities": entity_index,
            "yggdrasil_enabled": self._ygg is not None,
            "nerve_bridge_enabled": self._nerve_enabled,
        }

    def context_packet(self, focus_entity: str) -> dict[str, Any] | None:
        """Build an LLM-ready context packet for a focus entity.

        Combines spatial state, nearby entities, facts, and policies
        into a single structured context block suitable for injection
        into a prompt.

        Args:
            focus_entity: The entity to build context around.

        Returns:
            WorldContextPacket dict, or None if entity not found.
        """
        try:
            packet = self._oracle.build_context_packet(focus_entity=focus_entity)
            return packet.model_dump()
        except Exception as exc:
            logger.warning("context_packet failed for %s: %s", focus_entity, exc)
            return None

    # ─── Spatial Facts ───────────────────────────────────────────────────

    def get_facts(self, subject_id: str) -> list[dict[str, Any]]:
        """Get all canonical facts for a subject.

        Args:
            subject_id: The entity to query facts about.

        Returns:
            List of fact summary dicts.
        """
        facts = self._oracle.get_facts(subject_id=subject_id)
        return [f.model_dump() for f in facts]

    def search_facts(self, query: str, *, limit: int = 10) -> list[dict[str, Any]]:
        """Full-text search across all canonical facts.

        Args:
            query: Search query string.
            limit: Maximum number of results.

        Returns:
            List of matching fact summary dicts.
        """
        facts = self._oracle.search_facts(query=query, limit=limit)
        return [f.model_dump() for f in facts]

    # ─── Nerve Bridge Methods ─────────────────────────────────────────────

    def _emit_nerve(self, event_type: str, data: dict) -> bool:
        """Push a spatial awareness event to the Verðandi nerve hub.

        Fire-and-forget: if the socket is unavailable, the event is
        silently dropped. Non-blocking, 2s timeout.
        """
        if not self._nerve_enabled or self._nerve_socket is None:
            return False

        impulse = {
            "source": "spatial_awareness",
            "event": event_type,
            "timestamp": time.time(),
            "data": data,
        }
        payload = json.dumps(impulse).encode("utf-8")

        try:
            sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            sock.settimeout(NERVE_TIMEOUT)
            sock.connect(str(self._nerve_socket))
            sock.sendall(payload + b"\n")
            sock.close()
            return True
        except (ConnectionRefusedError, FileNotFoundError, OSError):
            self._nerve_enabled = False
            return False
        except Exception:
            return False

    def bridge_movement(
        self,
        entity_id: str,
        new_location: str,
        old_location: str | None = None,
    ) -> bool:
        """Emit a spatial awareness event when an entity moves.

        Args:
            entity_id:     The moving entity.
            new_location:  Where they went.
            old_location:  Where they were (if known).

        Returns:
            True if nerve event was sent, False if socket unavailable.
        """
        return self._emit_nerve("spatial_movement", {
            "entity_id": entity_id,
            "new_location": new_location,
            "old_location": old_location,
        })

    def bridge_proximity(
        self,
        entity_a: str,
        entity_b: str,
        location_id: str,
        distance: str = "same_location",
    ) -> bool:
        """Emit a proximity event when two entities are near each other.

        Args:
            entity_a:    First entity.
            entity_b:    Second entity.
            location_id: Where they're co-located.
            distance:    Proximity description.

        Returns:
            True if nerve event was sent.
        """
        return self._emit_nerve("spatial_proximity", {
            "entity_a": entity_a,
            "entity_b": entity_b,
            "location_id": location_id,
            "distance": distance,
        })

    def bridge_location_query(
        self,
        entity_id: str,
        query_type: str,
        result_summary: str,
    ) -> bool:
        """Emit an event when Runa performs a spatial query.

        Args:
            entity_id:       Entity queried about.
            query_type:      Type of query ("where", "what_at", etc.)
            result_summary:  Brief human-readable result.
        """
        return self._emit_nerve("spatial_query", {
            "entity_id": entity_id,
            "query_type": query_type,
            "result_summary": result_summary,
        })

    # ─── Convenience Accessors ────────────────────────────────────────────

    @property
    def world(self) -> World:
        """The underlying ECS World."""
        return self._world

    @property
    def oracle(self) -> PassiveOracle:
        """The underlying PassiveOracle."""
        return self._oracle

    @property
    def yggdrasil(self) -> YggdrasilTree | None:
        """The YggdrasilTree, if configured."""
        return self._ygg

    @property
    def is_nerve_enabled(self) -> bool:
        """Whether the Verðandi nerve bridge is active."""
        return self._nerve_enabled