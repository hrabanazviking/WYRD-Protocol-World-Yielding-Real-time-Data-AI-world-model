"""NSEWyrdBridge — WYRD integration for Norse Saga Engine.

Maps NSE's YggdrasilEngine state into WYRD's ECS:
    - NSE characters (from `_characters` / `get_npcs_at_location()`)
      → WYRD entities with NameComponent, StatusComponent, HamingjaComponent
    - NSE location (`get_current_location_display()` / `get_mead_hall_location_id()`)
      → Yggdrasil zone/location
    - NSE turn output (observations, character facts)
      → WYRD WritebackEngine facts/observations
    - WYRD CharacterContext output
      → enriched system prompt injected into NSE's turn loop

Drop-in usage::

    from wyrdforge.bridges.nse_bridge import NSEWyrdBridge

    # nse_engine is a live YggdrasilEngine instance
    bridge = NSEWyrdBridge(nse_engine, db_path="wyrd_nse.db")
    bridge.sync()   # pull NSE state into WYRD

    # Query Sigrid via WYRD before the NSE turn
    enriched_context = bridge.get_context_for_npc("sigrid")
    # Pass enriched_context.formatted_for_llm into NSE's system prompt
"""
from __future__ import annotations

import logging
from typing import Any

from wyrdforge.bridges.python_rpg import BridgeConfig, PythonRPGBridge
from wyrdforge.ecs.components.identity import NameComponent, StatusComponent
from wyrdforge.ecs.components.runic import HamingjaComponent
from wyrdforge.models.micro_rag import QueryMode
from wyrdforge.models.persona import PersonaMode
from wyrdforge.runtime.character_context import CharacterContextResult

logger = logging.getLogger(__name__)


class NSEWyrdBridge:
    """WYRD bridge for Norse Saga Engine.

    Wraps a live `YggdrasilEngine` instance and maps its state into the
    WYRD ECS on each `sync()` call.  Character queries are routed through
    `CharacterContext.build()` to produce enriched context blocks.

    Args:
        nse_engine:   Live YggdrasilEngine instance.
        db_path:      SQLite path for WYRD PersistentMemoryStore.
        ollama_model: Ollama model name for LLM calls (optional).
        ollama_host:  Ollama server host.
        ollama_port:  Ollama server port.
    """

    def __init__(
        self,
        nse_engine: Any,
        *,
        db_path: str = "wyrd_nse.db",
        ollama_model: str = "llama3",
        ollama_host: str = "localhost",
        ollama_port: int = 11434,
    ) -> None:
        self._nse = nse_engine

        cfg = BridgeConfig(
            world_id="nse_world",
            db_path=db_path,
            ollama_model=ollama_model,
            ollama_host=ollama_host,
            ollama_port=ollama_port,
            use_bond_service=True,
        )
        self._bridge = PythonRPGBridge.from_config(cfg)
        self._synced_ids: set[str] = set()

        # Build the minimal spatial hierarchy NSE expects
        self._bridge.yggdrasil.create_zone(zone_id="midgard", name="Midgard")
        self._bridge.yggdrasil.create_region(
            region_id="viken", name="Viken", parent_zone_id="midgard"
        )

    # ------------------------------------------------------------------
    # Sync
    # ------------------------------------------------------------------

    def sync(self) -> None:
        """Pull current NSE world state into WYRD.

        - Registers all loaded characters as WYRD entities.
        - Syncs the current NSE location as a Yggdrasil location.
        - Writes character facts (name, role, status) to WYRD memory.
        - Writes the current NSE location observation to WYRD memory.
        """
        self._sync_location()
        self._sync_characters()
        logger.debug("NSEWyrdBridge: sync complete")

    # ------------------------------------------------------------------
    # Character context
    # ------------------------------------------------------------------

    def get_context_for_npc(
        self,
        npc_id: str,
        *,
        player_input: str = "",
        query_mode: QueryMode = QueryMode.COMPANION_CONTINUITY,
        persona_mode: PersonaMode = PersonaMode.COMPANION,
    ) -> CharacterContextResult:
        """Build a WYRD CharacterContextResult for an NSE NPC.

        The returned `result.formatted_for_llm` can be injected directly
        into NSE's system prompt to give the NPC grounded world state.

        Args:
            npc_id:       NSE character ID (typically the name, lowercased).
            player_input: Current player message (for RAG scoring).
            query_mode:   MicroRAG scoring mode.
            persona_mode: PersonaCompiler compilation mode.

        Returns:
            CharacterContextResult ready for prompt injection.
        """
        location_id = self._current_location_id()
        return self._bridge._char_ctx.build(
            persona_id=npc_id,
            user_id="player",
            query=player_input or "What is happening?",
            mode=query_mode,
            persona_mode=persona_mode,
            focus_entity_ids=[npc_id],
            location_id=location_id,
        )

    def query_npc(
        self,
        npc_id: str,
        player_input: str,
        *,
        use_turn_loop: bool = False,
    ) -> str:
        """Query an NPC through WYRD and return the response.

        When `use_turn_loop=False` (default for NSE integration), returns the
        formatted context block rather than an LLM response — NSE's own LLM
        then uses this enriched context.  Set `use_turn_loop=True` to use
        WYRD's TurnLoop directly (bypasses NSE's LLM entirely).

        Args:
            npc_id:       NSE character ID.
            player_input: Player message.
            use_turn_loop: Whether to call WYRD's LLM vs return context only.

        Returns:
            Response string or formatted context block.
        """
        return self._bridge.query(
            npc_id,
            player_input,
            location_id=self._current_location_id(),
            use_turn_loop=use_turn_loop,
        )

    def push_turn_observation(self, title: str, summary: str) -> None:
        """Write an NSE turn outcome as a WYRD observation.

        Call this after each NSE turn to keep WYRD's memory in sync.

        Args:
            title:   Short event label (e.g. "Sigrid speaks of the runes").
            summary: Full text of what happened this turn.
        """
        self._bridge.push_event("observation", {"title": title, "summary": summary})

    # ------------------------------------------------------------------
    # Internal sync helpers
    # ------------------------------------------------------------------

    def _sync_location(self) -> None:
        """Sync the current NSE location into Yggdrasil."""
        try:
            loc_id = _normalize_id(self._current_location_display())
            loc_name = self._current_location_display()
        except Exception:
            loc_id = "mead_hall"
            loc_name = "The Mead Hall"

        tree = self._bridge.yggdrasil
        world = self._bridge.world
        if not world.get_entity(loc_id):
            try:
                tree.create_location(
                    location_id=loc_id,
                    name=loc_name,
                    parent_region_id="viken",
                )
            except Exception as exc:
                logger.debug("NSEWyrdBridge: could not create location %s: %s", loc_id, exc)

        self._bridge.writeback.write_observation(
            title=f"Scene: {loc_name}",
            summary=f"The current scene is {loc_name}.",
        )

    def _sync_characters(self) -> None:
        """Register NSE characters as WYRD ECS entities."""
        try:
            characters: list[dict[str, Any]] = self._nse._load_all_characters()
        except Exception:
            try:
                characters = getattr(self._nse, "_characters", []) or []
            except Exception:
                return

        for char in characters:
            char_id = _nse_char_id(char)
            if not char_id:
                continue

            # Register entity if new
            if char_id not in self._synced_ids:
                world = self._bridge.world
                if not world.get_entity(char_id):
                    world.create_entity(entity_id=char_id, tags={"character", "nse_npc"})

                name = _nse_str(char, "name", char_id)
                world.add_component(char_id, NameComponent(entity_id=char_id, name=name))
                self._synced_ids.add(char_id)

            # Sync status
            self._sync_char_status(char, char_id)
            # Sync canonical facts
            self._sync_char_facts(char, char_id)

    def _sync_char_status(self, char: dict[str, Any], char_id: str) -> None:
        """Update or create StatusComponent from NSE character data."""
        world = self._bridge.world
        mood = _nse_str(char, "mood", "")
        health = _nse_str(char, "health", "alive")
        status = f"{mood} / {health}" if mood else health
        existing = world.get_component(char_id, "status")
        if existing is None:
            world.add_component(char_id, StatusComponent(entity_id=char_id, state=status))
        else:
            existing.state = status

    def _sync_char_facts(self, char: dict[str, Any], char_id: str) -> None:
        """Write NSE character attributes as WYRD canonical facts."""
        wb = self._bridge.writeback
        fact_fields = {
            "role": ("identity", 0.9),
            "class": ("identity", 0.85),
            "personality": ("identity", 0.8),
            "archetype": ("identity", 0.75),
            "occupation": ("background", 0.8),
            "backstory": ("background", 0.7),
        }
        for field, (domain, confidence) in fact_fields.items():
            value = _nse_str(char, field, "")
            if value:
                try:
                    wb.write_canonical_fact(
                        fact_subject_id=char_id,
                        fact_key=field,
                        fact_value=value,
                        domain=domain,
                        confidence=confidence,
                    )
                except Exception as exc:
                    logger.debug(
                        "NSEWyrdBridge: could not write fact %s.%s: %s", char_id, field, exc
                    )

    def _current_location_id(self) -> str | None:
        try:
            return _normalize_id(self._current_location_display())
        except Exception:
            return None

    def _current_location_display(self) -> str:
        try:
            return self._nse.get_current_location_display()
        except Exception:
            return "Mead Hall"

    # ------------------------------------------------------------------
    # Accessors
    # ------------------------------------------------------------------

    @property
    def bridge(self) -> PythonRPGBridge:
        """The underlying PythonRPGBridge."""
        return self._bridge


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _normalize_id(s: str) -> str:
    """Convert display name → stable snake_case ID."""
    return s.lower().strip().replace(" ", "_").replace("-", "_")[:64]


def _nse_char_id(char: dict[str, Any]) -> str:
    """Extract a stable entity ID from an NSE character dict."""
    for key in ("id", "name", "character_id"):
        val = char.get(key, "")
        if isinstance(val, str) and val.strip():
            return _normalize_id(val)
    return ""


def _nse_str(char: dict[str, Any], key: str, default: str = "") -> str:
    """Safely extract a string field from an NSE character dict."""
    val = char.get(key, default)
    if isinstance(val, str):
        return val.strip()
    if isinstance(val, dict):
        # Some NSE fields are nested dicts — take the first string value
        for v in val.values():
            if isinstance(v, str):
                return v.strip()
    return default
