"""AgentZeroWyrdBridge — WYRD as persistent world memory for AgentZero agents.

Integrates WYRD as the world-memory backend for AgentZero agents.  The
bridge provides a ``WyrdMemoryTool`` that AgentZero can call to read world
state, plus a ``WyrdWriteTool`` for writing observations back from the agent.

AgentZero integration pattern:
    1. Create an AgentZeroWyrdBridge.
    2. Register both tools with the AgentZero agent's tool list.
    3. The agent calls ``wyrd_read`` before responding to get grounded context.
    4. The agent calls ``wyrd_write`` after acting to record what happened.

Usage::

    from wyrdforge.bridges.agentzero_bridge import AgentZeroWyrdBridge

    bridge = AgentZeroWyrdBridge(db_path="wyrd_az.db")
    read_tool = bridge.get_read_tool()
    write_tool = bridge.get_write_tool()

    # Register with AgentZero agent tools list:
    agent.tools = [read_tool, write_tool, ...other_tools]
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from wyrdforge.bridges.python_rpg import BridgeConfig, PythonRPGBridge


# ---------------------------------------------------------------------------
# Read tool
# ---------------------------------------------------------------------------

@dataclass
class WyrdReadResult:
    """Result returned by WyrdReadTool.run()."""
    persona_id: str
    context: str
    world_id: str | None


class WyrdReadTool:
    """AgentZero-compatible tool for reading WYRD world context.

    Args:
        bridge:      PythonRPGBridge instance.
        name:        Tool name. Default: ``"wyrd_read"``.
        description: Description injected into agent's tool schema.
    """

    name: str
    description: str

    def __init__(
        self,
        bridge: PythonRPGBridge,
        *,
        name: str = "wyrd_read",
        description: str = (
            "Read current WYRD world state for a persona. "
            "Returns grounded world context: entity facts, location, bond state, "
            "and recent observations. Call this before generating any character response."
        ),
    ) -> None:
        self._bridge = bridge
        self.name = name
        self.description = description

    def run(
        self,
        persona_id: str,
        message: str = "",
        *,
        location_id: str | None = None,
    ) -> WyrdReadResult:
        """Read world context for a persona.

        Args:
            persona_id:  Character to read context for.
            message:     Current agent message (improves RAG scoring).
            location_id: Optional location override.

        Returns:
            WyrdReadResult with context block.
        """
        context = self._bridge.query(
            persona_id,
            message or "What is the current state of the world?",
            location_id=location_id,
            use_turn_loop=False,
        )
        return WyrdReadResult(
            persona_id=persona_id,
            context=context,
            world_id=self._bridge.world.world_id,
        )

    def to_dict(self) -> dict[str, Any]:
        """Return AgentZero-compatible tool descriptor dict."""
        return {
            "name": self.name,
            "description": self.description,
            "parameters": {
                "type": "object",
                "properties": {
                    "persona_id": {"type": "string", "description": "Persona/character ID."},
                    "message": {"type": "string", "description": "Current message (optional)."},
                },
                "required": ["persona_id"],
            },
        }


# ---------------------------------------------------------------------------
# Write tool
# ---------------------------------------------------------------------------

@dataclass
class WyrdWriteResult:
    """Result returned by WyrdWriteTool.run()."""
    written: bool
    record_type: str


class WyrdWriteTool:
    """AgentZero-compatible tool for writing observations to WYRD memory.

    Args:
        bridge:      PythonRPGBridge instance.
        name:        Tool name. Default: ``"wyrd_write"``.
        description: Description injected into agent's tool schema.
    """

    name: str
    description: str

    def __init__(
        self,
        bridge: PythonRPGBridge,
        *,
        name: str = "wyrd_write",
        description: str = (
            "Write an observation or fact to WYRD world memory. "
            "Call after taking an action or when something notable occurs "
            "to keep the world model up to date."
        ),
    ) -> None:
        self._bridge = bridge
        self.name = name
        self.description = description

    def run(
        self,
        event_type: str,
        payload: dict[str, Any],
    ) -> WyrdWriteResult:
        """Write a world event to WYRD memory.

        Args:
            event_type: ``"observation"`` or ``"fact"``.
            payload:    Event data. For observation: ``{title, summary}``.
                        For fact: ``{subject_id, key, value}``.

        Returns:
            WyrdWriteResult indicating success.
        """
        try:
            self._bridge.push_event(event_type, payload)
            return WyrdWriteResult(written=True, record_type=event_type)
        except Exception:
            return WyrdWriteResult(written=False, record_type=event_type)

    def to_dict(self) -> dict[str, Any]:
        """Return AgentZero-compatible tool descriptor dict."""
        return {
            "name": self.name,
            "description": self.description,
            "parameters": {
                "type": "object",
                "properties": {
                    "event_type": {
                        "type": "string",
                        "enum": ["observation", "fact"],
                        "description": "Type of world event to record.",
                    },
                    "payload": {
                        "type": "object",
                        "description": "Event data (title+summary for observation; subject_id+key+value for fact).",
                    },
                },
                "required": ["event_type", "payload"],
            },
        }


# ---------------------------------------------------------------------------
# Bridge
# ---------------------------------------------------------------------------

class AgentZeroWyrdBridge:
    """WYRD integration for AgentZero agents.

    Args:
        db_path:      SQLite path for PersistentMemoryStore.
        ollama_model: Ollama model name.
        world_id:     Logical world ID. Default: ``"agentzero_world"``.
    """

    def __init__(
        self,
        *,
        db_path: str = "wyrd_agentzero.db",
        ollama_model: str = "llama3",
        world_id: str = "agentzero_world",
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

    def get_read_tool(self, *, name: str = "wyrd_read", description: str = "") -> WyrdReadTool:
        """Return a WyrdReadTool for the AgentZero agent."""
        kwargs: dict[str, Any] = {"name": name}
        if description:
            kwargs["description"] = description
        return WyrdReadTool(self._bridge, **kwargs)

    def get_write_tool(self, *, name: str = "wyrd_write", description: str = "") -> WyrdWriteTool:
        """Return a WyrdWriteTool for the AgentZero agent."""
        kwargs: dict[str, Any] = {"name": name}
        if description:
            kwargs["description"] = description
        return WyrdWriteTool(self._bridge, **kwargs)

    def get_tools(self) -> list[WyrdReadTool | WyrdWriteTool]:
        """Return both tools as a list ready to register with the agent."""
        return [self.get_read_tool(), self.get_write_tool()]

    @property
    def bridge(self) -> PythonRPGBridge:
        """The underlying PythonRPGBridge."""
        return self._bridge
