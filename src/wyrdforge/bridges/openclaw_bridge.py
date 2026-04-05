"""OpenClawWyrdBridge — WYRD integration for OpenClaw / VGSK.

Injects WYRD world context into OpenClaw's PromptSynthesizer before each
LLM call.  Works as a pre-turn hook: call `enrich_system_prompt()` with
the base system prompt, receive the enriched version with WYRD context
appended.

Designed specifically for Viking Girlfriend Skill (VGSK) where Sigrid is
the persona, but works with any OpenClaw skill that uses a PromptSynthesizer.

Usage::

    from wyrdforge.bridges.openclaw_bridge import OpenClawWyrdBridge

    bridge = OpenClawWyrdBridge(
        persona_id="sigrid",
        db_path="wyrd_vgsk.db",
    )
    bridge.sync_character(sigrid_character_dict)  # pull Sigrid's state in

    # Before each PromptSynthesizer.build_messages() call:
    enriched_system = bridge.enrich_system_prompt(base_system_prompt, player_input)
    # Pass enriched_system into the existing VGSK turn pipeline
"""
from __future__ import annotations

import logging
from typing import Any

from wyrdforge.bridges.python_rpg import BridgeConfig, PythonRPGBridge
from wyrdforge.ecs.components.identity import NameComponent, StatusComponent
from wyrdforge.ecs.components.runic import HamingjaComponent
from wyrdforge.models.micro_rag import QueryMode
from wyrdforge.models.persona import PersonaMode

logger = logging.getLogger(__name__)

# WYRD context is injected under this section header in the system prompt
_WYRD_SECTION_HEADER = "\n\n[WYRD WORLD CONTEXT]\n"
_WYRD_SECTION_FOOTER = "\n[/WYRD WORLD CONTEXT]\n"


class OpenClawWyrdBridge:
    """WYRD pre-turn context injector for OpenClaw skills.

    Args:
        persona_id:      OpenClaw persona ID (e.g. ``"sigrid"``).
        db_path:         SQLite path for WYRD PersistentMemoryStore.
        ollama_model:    Ollama model name (only used if use_turn_loop=True).
        ollama_host:     Ollama server host.
        ollama_port:     Ollama server port.
        world_id:        Logical world ID. Default: ``"openclaw_world"``.
        inject_identity: Whether to include the [IDENTITY] section in injection.
        inject_bond:     Whether to include bond state in injection.
        max_context_chars: Truncate injected block to this many characters.
                           0 = no truncation.
    """

    def __init__(
        self,
        persona_id: str,
        *,
        db_path: str = "wyrd_openclaw.db",
        ollama_model: str = "llama3",
        ollama_host: str = "localhost",
        ollama_port: int = 11434,
        world_id: str = "openclaw_world",
        inject_identity: bool = True,
        inject_bond: bool = True,
        max_context_chars: int = 2000,
    ) -> None:
        self._persona_id = persona_id
        self._inject_identity = inject_identity
        self._inject_bond = inject_bond
        self._max_context_chars = max_context_chars

        cfg = BridgeConfig(
            world_id=world_id,
            db_path=db_path,
            ollama_model=ollama_model,
            ollama_host=ollama_host,
            ollama_port=ollama_port,
            use_bond_service=True,
        )
        self._bridge = PythonRPGBridge.from_config(cfg)

        # Build minimal spatial scaffold
        self._bridge.yggdrasil.create_zone(zone_id="midgard", name="Midgard")
        self._bridge.yggdrasil.create_region(
            region_id="home_region", name="Home Region", parent_zone_id="midgard"
        )
        self._bridge.yggdrasil.create_location(
            location_id="shared_space",
            name="Shared Space",
            parent_region_id="home_region",
        )
        self._bridge.world.create_entity(
            entity_id=persona_id, tags={"character", "persona"}
        )
        self._bridge.yggdrasil.place_entity(persona_id, location_id="shared_space")

    # ------------------------------------------------------------------
    # Character sync
    # ------------------------------------------------------------------

    def sync_character(self, char_data: dict[str, Any]) -> None:
        """Sync an OpenClaw/VGSK character dict into WYRD.

        Reads name, mood, status, personality traits, and any structured
        attributes from `char_data` and writes them as WYRD facts/components.

        Args:
            char_data: Character state dict from VGSK (e.g. from sigrid.yaml).
        """
        world = self._bridge.world
        wb = self._bridge.writeback
        eid = self._persona_id

        # Name component
        name = _get_str(char_data, ["name", "character_name"], eid)
        existing_name = world.get_component(eid, "name")
        if existing_name is None:
            world.add_component(eid, NameComponent(entity_id=eid, name=name))
        else:
            existing_name.name = name

        # Status component
        mood = _get_str(char_data, ["mood", "current_mood", "emotional_state"], "")
        health = _get_str(char_data, ["health", "wellbeing"], "well")
        state = f"{mood} / {health}" if mood else health
        existing_status = world.get_component(eid, "status")
        if existing_status is None:
            world.add_component(eid, StatusComponent(entity_id=eid, state=state))
        else:
            existing_status.state = state

        # Canonical facts
        fact_fields = [
            ("personality", "identity", 0.9),
            ("archetype", "identity", 0.85),
            ("role", "identity", 0.9),
            ("occupation", "background", 0.8),
            ("backstory", "background", 0.7),
            ("values", "identity", 0.85),
            ("speech_style", "voice", 0.8),
            ("relationship_to_player", "bond", 0.9),
        ]
        for field, domain, confidence in fact_fields:
            value = _get_str(char_data, [field], "")
            if value:
                try:
                    wb.write_canonical_fact(
                        fact_subject_id=eid,
                        fact_key=field,
                        fact_value=value,
                        domain=domain,
                        confidence=confidence,
                    )
                except Exception as exc:
                    logger.debug("OpenClawBridge: fact write failed %s.%s: %s", eid, field, exc)

    def sync_bond_state(
        self,
        *,
        closeness: float = 0.5,
        trust: float = 0.5,
        domain: str = "companion",
    ) -> None:
        """Write current bond/relationship state as WYRD facts.

        Args:
            closeness: Closeness index in [0.0, 1.0].
            trust:     Trust index in [0.0, 1.0].
            domain:    Bond domain label.
        """
        wb = self._bridge.writeback
        wb.write_canonical_fact(
            fact_subject_id=self._persona_id,
            fact_key="bond_closeness",
            fact_value=f"{closeness:.2f}",
            domain="bond",
            confidence=0.95,
        )
        wb.write_canonical_fact(
            fact_subject_id=self._persona_id,
            fact_key="bond_trust",
            fact_value=f"{trust:.2f}",
            domain="bond",
            confidence=0.95,
        )

    def push_turn_event(self, summary: str, *, title: str = "Turn event") -> None:
        """Write a turn outcome as a WYRD observation.

        Call after each completed VGSK turn to keep WYRD's memory in sync.

        Args:
            summary: Full text of what happened this turn.
            title:   Short event label.
        """
        self._bridge.push_event("observation", {"title": title, "summary": summary})

    # ------------------------------------------------------------------
    # Context injection — main API
    # ------------------------------------------------------------------

    def enrich_system_prompt(
        self,
        base_system_prompt: str,
        player_input: str = "",
        *,
        location_id: str | None = "shared_space",
        bond_id: str | None = None,
    ) -> str:
        """Enrich an OpenClaw system prompt with WYRD world context.

        Builds a CharacterContextResult for the persona and appends
        the WYRD context block to the base system prompt.

        Args:
            base_system_prompt: The existing system prompt from VGSK.
            player_input:       Current player message (improves RAG scoring).
            location_id:        Override location for context building.
            bond_id:            Bond edge ID if bond state is desired.

        Returns:
            Enriched system prompt with WYRD context injected.
        """
        try:
            result = self._bridge._char_ctx.build(
                persona_id=self._persona_id,
                user_id="player",
                query=player_input or "What is happening?",
                mode=QueryMode.COMPANION_CONTINUITY,
                persona_mode=PersonaMode.COMPANION,
                focus_entity_ids=[self._persona_id],
                location_id=location_id,
                bond_id=bond_id,
            )
            context_block = self._build_injection_block(result.formatted_for_llm)
            return base_system_prompt + context_block
        except Exception as exc:
            logger.warning("OpenClawBridge: context enrichment failed: %s", exc)
            return base_system_prompt

    def _build_injection_block(self, formatted: str) -> str:
        """Trim and wrap the WYRD context block for injection."""
        if self._max_context_chars > 0 and len(formatted) > self._max_context_chars:
            formatted = formatted[: self._max_context_chars] + "\n... [truncated]"
        return _WYRD_SECTION_HEADER + formatted + _WYRD_SECTION_FOOTER

    # ------------------------------------------------------------------
    # Accessors
    # ------------------------------------------------------------------

    @property
    def bridge(self) -> PythonRPGBridge:
        """The underlying PythonRPGBridge."""
        return self._bridge

    @property
    def persona_id(self) -> str:
        """The active persona ID."""
        return self._persona_id


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_str(d: dict[str, Any], keys: list[str], default: str = "") -> str:
    """Try multiple keys; return first non-empty string found."""
    for key in keys:
        val = d.get(key, "")
        if isinstance(val, str) and val.strip():
            return val.strip()
        if isinstance(val, dict):
            for v in val.values():
                if isinstance(v, str) and v.strip():
                    return v.strip()
    return default
