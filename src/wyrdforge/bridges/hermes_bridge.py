"""HermesWyrdBridge — WYRD integration for Hermes Agent framework.

Registers WYRD as a callable world-state tool in Hermes agent pipelines.
The bridge exposes a ``WyrdTool`` that Hermes agents can invoke to get
grounded world context before generating responses.

Usage::

    from wyrdforge.bridges.hermes_bridge import HermesWyrdBridge

    bridge = HermesWyrdBridge(db_path="wyrd_hermes.db")
    tool = bridge.get_tool()

    # Register with your Hermes agent:
    agent.register_tool(tool)
    # Agent can now call: tool.run(persona_id="sigrid", query="What is happening?")
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from wyrdforge.bridges.python_rpg import BridgeConfig, PythonRPGBridge


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
    """WYRD integration for Hermes Agent framework.

    Args:
        db_path:      SQLite path for PersistentMemoryStore.
        ollama_model: Ollama model name.
        world_id:     Logical world ID. Default: ``"hermes_world"``.
    """

    def __init__(
        self,
        *,
        db_path: str = "wyrd_hermes.db",
        ollama_model: str = "llama3",
        world_id: str = "hermes_world",
    ) -> None:
        cfg = BridgeConfig(
            world_id=world_id,
            db_path=db_path,
            ollama_model=ollama_model,
        )
        self._bridge = PythonRPGBridge.from_config(cfg)

        # Minimal spatial scaffold
        self._bridge.yggdrasil.create_zone(zone_id="midgard", name="Midgard")
        self._bridge.yggdrasil.create_region(
            region_id="home", name="Home", parent_zone_id="midgard"
        )
        self._bridge.yggdrasil.create_location(
            location_id="scene", name="Scene", parent_region_id="home"
        )

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
