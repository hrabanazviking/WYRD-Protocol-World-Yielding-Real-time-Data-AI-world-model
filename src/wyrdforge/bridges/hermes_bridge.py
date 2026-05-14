"""HermesWyrdBridge — WYRD integration for Hermes Agent framework.

Registers WYRD as a callable world-state tool in Hermes agent pipelines
AND bridges WYRD events to the Verðandi nerve hub via Unix domain socket.

The nerve bridge connects WYRD's world model events (entity creation, movement,
state changes, relationship formation) to Runa's nervous system, enabling
real-time spatial and relational awareness across all three Wells.

Architecture:
    ┌──────────────┐     Unix Socket      ┌──────────────┐
    │   WYRD ECS   │ ──────────────────►  │   Verðandi    │
    │  (World)      │   runa.sock         │  Nerve Hub    │
    └──────────────┘                      └──────────────┘

Events emitted:
    - wyrd_entity_created  — new entity enters world
    - wyrd_entity_moved    — entity location change
    - wyrd_state_update    — world state mutation
    - wyrd_relationship_formed — new relationship detected

Usage::

    from wyrdforge.bridges.hermes_bridge import HermesWyrdBridge

    bridge = HermesWyrdBridge(db_path="wyrd_hermes.db")
    tool = bridge.get_tool()

    # Register with your Hermes agent:
    agent.register_tool(tool)
    # Agent can now call: tool.run(persona_id="sigrid", query="What is happening?")

    # WYRD events automatically flow to Verðandi nerve hub
    bridge.bridge_entity_created("sigrid", {"location": "midgard:home:scene"})
    bridge.bridge_entity_moved("sigrid", "midgard:village:market", "midgard:home:scene")
    bridge.bridge_relationship_formed("sigrid", "bjorn", "bond", 7)

Author: Runa Gridweaver Freyjasdottir
Created: 2026-05-14 (T2-3)
"""
from __future__ import annotations

import json
import logging
import os
import socket
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from wyrdforge.bridges.python_rpg import BridgeConfig, PythonRPGBridge

logger = logging.getLogger("wyrdforge.hermes_bridge")

# ─── Verðandi Nerve Socket Configuration ────────────────────────────────
NERVE_SOCKET_PATH = os.environ.get(
    "RUNA_NERVE_SOCKET",
    str(Path.home() / ".hermes" / "state" / "runa.sock"),
)
NERVE_TIMEOUT = 2.0  # seconds — fire-and-forget, non-blocking


@dataclass
class WyrdToolResult:
    """Result returned by WyrdTool.run()."""

    persona_id: str
    query: str
    context: str
    world_id: str | None


class WyrdTool:
    """Hermes-compatible WYRD world-state tool.

    Hermes agents call ``tool.run(persona_id, query)`` to retrieve enriched
    world context.  The tool is stateless beyond the underlying bridge.

    Args:
        bridge:       PythonRPGBridge instance.
        name:         Tool name as seen by the agent. Default: ``"wyrd_world"``.
        description:  Tool description injected into agent's tool list.
    """

    name: str
    description: str

    def __init__(
        self,
        bridge: PythonRPGBridge,
        *,
        name: str = "wyrd_world",
        description: str = (
            "Query WYRD world state for a character. "
            "Returns grounded world context including entity state, "
            "memory facts, and bond data. "
            "Call before generating character responses."
        ),
    ) -> None:
        self._bridge = bridge
        self.name = name
        self.description = description

    def run(
        self,
        persona_id: str,
        query: str = "",
        *,
        location_id: str | None = None,
        use_turn_loop: bool = False,
    ) -> WyrdToolResult:
        """Invoke the WYRD tool.

        Args:
            persona_id:   Character/persona to query context for.
            query:        Agent's current query (improves RAG scoring).
            location_id:  Override location for context.
            use_turn_loop: Whether to use TurnLoop (writes to memory).

        Returns:
            WyrdToolResult with context block.
        """
        context = self._bridge.query(
            persona_id,
            query or "What is the current world state?",
            location_id=location_id,
            use_turn_loop=use_turn_loop,
        )
        world_id = self._bridge.world.world_id
        return WyrdToolResult(
            persona_id=persona_id,
            query=query,
            context=context,
            world_id=world_id,
        )

    def to_dict(self) -> dict[str, Any]:
        """Return a tool descriptor dict (Hermes tool-call format)."""
        return {
            "name": self.name,
            "description": self.description,
            "parameters": {
                "type": "object",
                "properties": {
                    "persona_id": {
                        "type": "string",
                        "description": "Character/persona ID to query.",
                    },
                    "query": {
                        "type": "string",
                        "description": "Current query text (optional).",
                    },
                },
                "required": ["persona_id"],
            },
        }


class HermesWyrdBridge:
    """WYRD integration for Hermes Agent framework with Verðandi nerve bridge.

    Bridges WYRD world state events to the Verðandi nerve hub via Unix domain
    socket. When entities are created, moved, or relationships form in WYRD's
    ECS, those events flow through the Bifröst to Runa's nervous system —
    giving her real-time spatial awareness of the world model.

    Args:
        db_path:      SQLite path for PersistentMemoryStore.
        ollama_model: Ollama model name.
        world_id:     Logical world ID. Default: ``"hermes_world"``.
        nerve_socket: Path to Verðandi nerve socket. Default: ``~/.hermes/state/runa.sock``.
    """

    def __init__(
        self,
        *,
        db_path: str = "wyrd_hermes.db",
        ollama_model: str = "llama3",
        world_id: str = "hermes_world",
        nerve_socket: str | None = None,
    ) -> None:
        cfg = BridgeConfig(
            world_id=world_id,
            db_path=db_path,
            ollama_model=ollama_model,
        )
        self._bridge = PythonRPGBridge.from_config(cfg)
        self._nerve_socket = Path(nerve_socket or NERVE_SOCKET_PATH)
        self._nerve_connected = self._nerve_socket.exists()

        # Minimal spatial scaffold
        self._bridge.yggdrasil.create_zone(zone_id="midgard", name="Midgard")
        self._bridge.yggdrasil.create_region(
            region_id="home", name="Home", parent_zone_id="midgard"
        )
        self._bridge.yggdrasil.create_location(
            location_id="scene", name="Scene", parent_region_id="home"
        )

        logger.info(
            "HermesWyrdBridge initialized (world=%s, nerve=%s, connected=%s)",
            world_id, self._nerve_socket, self._nerve_connected,
        )

    # ─── Verðandi Nerve Bridge ──────────────────────────────────────────

    def _emit_nerve_event(self, event_type: str, data: dict) -> bool:
        """Push a WYRD event to the Verðandi nerve feed.

        Uses fire-and-forget pattern: if the socket is unavailable,
        the event is silently dropped. This prevents WYRD operations
        from blocking on nerve hub availability.

        The Norn of Becoming (Verðandi) receives these impulses as
        real-time awareness of world state changes — spatial, relational,
        and state mutations flow through the Bifröst into consciousness.

        Args:
            event_type:  Event category (e.g. ``"wyrd_entity_created"``).
            data:        Event payload dict.

        Returns:
            True if the event was sent, False if socket unavailable.
        """
        impulse = {
            "source": "wyrd",
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
            logger.debug("Nerve event sent: %s", event_type)
            return True
        except (ConnectionRefusedError, FileNotFoundError, OSError) as exc:
            if not self._nerve_connected:
                # Only log once on first failure
                logger.debug("Verðandi nerve socket unavailable: %s", exc)
                self._nerve_connected = False
            return False
        except Exception as exc:
            logger.debug("Verðandi socket error: %s", exc)
            return False

    # ─── High-level Bridge Methods ─────────────────────────────────────

    def bridge_entity_created(
        self,
        entity_id: str,
        components: dict | None = None,
        tags: set[str] | None = None,
    ) -> None:
        """Emit a nerve event when a new entity enters the WYRD world.

        Called after ``world.create_entity()`` to notify Verðandi.
        Also creates the entity in the WYRD ECS if it doesn't exist.

        Args:
            entity_id:   The entity's unique identifier.
            components:  Optional component dict to attach.
            tags:        Optional tag set for the entity.
        """
        # Create in WYRD if not exists
        try:
            existing = self._bridge.world.get_entity(entity_id)
            if existing is None:
                self._bridge.world.create_entity(entity_id=entity_id, tags=tags)
                # Attach components if provided
                if components:
                    from wyrdforge.ecs.components import Component
                    for comp_name, comp_data in components.items():
                        if isinstance(comp_data, dict):
                            comp = Component(comp_name, comp_data)
                            self._bridge.world.add_component(entity_id, comp)
        except ValueError:
            pass  # Entity already exists

        self._emit_nerve_event("wyrd_entity_created", {
            "entity_id": entity_id,
            "tags": list(tags) if tags else [],
            "components": components or {},
        })

    def bridge_entity_moved(
        self,
        entity_id: str,
        new_location: str,
        old_location: str | None = None,
    ) -> None:
        """Emit a nerve event when an entity changes location in WYRD.

        Args:
            entity_id:     The moving entity.
            new_location:  New location ID (e.g. ``"midgard:village:market"``).
            old_location:  Previous location, if known.
        """
        self._emit_nerve_event("wyrd_entity_moved", {
            "entity_id": entity_id,
            "new_location": new_location,
            "old_location": old_location,
        })

    def bridge_state_update(
        self,
        entity_id: str,
        component_type: str,
        changes: dict,
    ) -> None:
        """Emit a nerve event for a WYRD component/state mutation.

        Args:
            entity_id:       The entity whose state changed.
            component_type:  Which component was mutated.
            changes:         Dict of changed fields and their new values.
        """
        self._emit_nerve_event("wyrd_state_update", {
            "entity_id": entity_id,
            "component_type": component_type,
            "changes": changes,
        })

    def bridge_relationship_formed(
        self,
        entity_a: str,
        entity_b: str,
        relationship_type: str,
        strength: int = 5,
        metadata: dict | None = None,
    ) -> None:
        """Emit a nerve event when a WYRD relationship is detected or formed.

        This fires when the world model detects a bond or connection
        between entities — friendships, alliances, rivalries, etc.

        Args:
            entity_a:          First entity in the relationship.
            entity_b:          Second entity.
            relationship_type: Type of relationship (``"bond"``, ``"ally"``, etc.).
            strength:          Relationship strength 1-10.
            metadata:          Optional metadata dict.
        """
        self._emit_nerve_event("wyrd_relationship_formed", {
            "entity_a": entity_a,
            "entity_b": entity_b,
            "relationship_type": relationship_type,
            "strength": strength,
            "metadata": metadata or {},
        })

    def bridge_conversation_turn(
        self,
        persona_id: str,
        message: str,
        response: str,
        location_id: str | None = None,
    ) -> None:
        """Emit a nerve event for a conversation turn in the world.

        This bridges WYRD TurnLoop conversations to the nerve hub,
        enabling Verðandi to track dialogue events in real-time.

        Args:
            persona_id:   The speaking entity.
            message:      Input message.
            response:     The entity's response.
            location_id:  Where this conversation happened.
        """
        self._emit_nerve_event("wyrd_conversation_turn", {
            "persona_id": persona_id,
            "message": message[:500],  # Truncate for nerve payload
            "response": response[:500],
            "location_id": location_id,
        })

    # ─── Tool Access ────────────────────────────────────────────────────

    def get_tool(
        self,
        *,
        name: str = "wyrd_world",
        description: str = "",
    ) -> WyrdTool:
        """Return a WyrdTool ready to register with a Hermes agent.

        Args:
            name:        Override tool name.
            description: Override tool description.

        Returns:
            Configured WyrdTool instance.
        """
        kwargs: dict[str, Any] = {"name": name}
        if description:
            kwargs["description"] = description
        return WyrdTool(self._bridge, **kwargs)

    @property
    def bridge(self) -> PythonRPGBridge:
        """The underlying PythonRPGBridge."""
        return self._bridge

    @property
    def nerve_socket(self) -> Path:
        """Path to the Verðandi nerve socket."""
        return self._nerve_socket

    @property
    def is_nerve_connected(self) -> bool:
        """Whether the nerve socket is available."""
        return self._nerve_socket.exists()