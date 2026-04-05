"""Tests for OpenClawWyrdBridge — Phase 9A VGSK/OpenClaw integration."""
from __future__ import annotations

import tempfile

from wyrdforge.bridges.openclaw_bridge import OpenClawWyrdBridge, _get_str


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_SIGRID_CHAR = {
    "name": "Sigrid",
    "mood": "serene",
    "health": "alive",
    "personality": "calm and wise",
    "role": "völva",
    "archetype": "Seer",
    "values": "truth, honor, wyrd",
    "speech_style": "poetic and measured",
    "relationship_to_player": "loyal companion",
    "backstory": "Born under Freya's star, trained as a seeress.",
}


def _build_bridge(**kwargs) -> OpenClawWyrdBridge:
    return OpenClawWyrdBridge(
        "sigrid",
        db_path=tempfile.mktemp(suffix=".db"),
        **kwargs,
    )


# ---------------------------------------------------------------------------
# Construction
# ---------------------------------------------------------------------------

def test_construction_succeeds() -> None:
    bridge = _build_bridge()
    assert bridge is not None


def test_persona_id_property() -> None:
    bridge = _build_bridge()
    assert bridge.persona_id == "sigrid"


def test_bridge_property_is_python_rpg_bridge() -> None:
    from wyrdforge.bridges.python_rpg import PythonRPGBridge
    bridge = _build_bridge()
    assert isinstance(bridge.bridge, PythonRPGBridge)


def test_entity_registered_on_construction() -> None:
    bridge = _build_bridge()
    assert bridge.bridge.world.get_entity("sigrid") is not None


def test_spatial_scaffold_built() -> None:
    bridge = _build_bridge()
    world = bridge.bridge.world
    assert world.get_entity("midgard") is not None
    assert world.get_entity("shared_space") is not None


# ---------------------------------------------------------------------------
# sync_character()
# ---------------------------------------------------------------------------

def test_sync_character_writes_name_component() -> None:
    bridge = _build_bridge()
    bridge.sync_character(_SIGRID_CHAR)
    comp = bridge.bridge.world.get_component("sigrid", "name")
    assert comp is not None
    assert comp.name == "Sigrid"


def test_sync_character_writes_status_component() -> None:
    bridge = _build_bridge()
    bridge.sync_character(_SIGRID_CHAR)
    comp = bridge.bridge.world.get_component("sigrid", "status")
    assert comp is not None
    assert "alive" in comp.state or "serene" in comp.state


def test_sync_character_writes_role_fact() -> None:
    bridge = _build_bridge()
    bridge.sync_character(_SIGRID_CHAR)
    fact = bridge.bridge.oracle.get_fact("sigrid", "role")
    assert fact is not None
    assert fact.content.structured_payload.fact_value == "völva"


def test_sync_character_writes_personality_fact() -> None:
    bridge = _build_bridge()
    bridge.sync_character(_SIGRID_CHAR)
    fact = bridge.bridge.oracle.get_fact("sigrid", "personality")
    assert fact is not None


def test_sync_character_writes_speech_style_fact() -> None:
    bridge = _build_bridge()
    bridge.sync_character(_SIGRID_CHAR)
    fact = bridge.bridge.oracle.get_fact("sigrid", "speech_style")
    assert fact is not None


def test_sync_character_writes_relationship_fact() -> None:
    bridge = _build_bridge()
    bridge.sync_character(_SIGRID_CHAR)
    fact = bridge.bridge.oracle.get_fact("sigrid", "relationship_to_player")
    assert fact is not None


def test_sync_character_handles_empty_dict() -> None:
    bridge = _build_bridge()
    bridge.sync_character({})  # should not raise


def test_sync_character_is_idempotent() -> None:
    bridge = _build_bridge()
    bridge.sync_character(_SIGRID_CHAR)
    bridge.sync_character(_SIGRID_CHAR)
    world = bridge.bridge.world
    assert world.get_entity("sigrid") is not None


# ---------------------------------------------------------------------------
# sync_bond_state()
# ---------------------------------------------------------------------------

def test_sync_bond_state_writes_closeness_fact() -> None:
    bridge = _build_bridge()
    bridge.sync_bond_state(closeness=0.8, trust=0.7)
    fact = bridge.bridge.oracle.get_fact("sigrid", "bond_closeness")
    assert fact is not None
    assert "0.80" in fact.content.structured_payload.fact_value


def test_sync_bond_state_writes_trust_fact() -> None:
    bridge = _build_bridge()
    bridge.sync_bond_state(closeness=0.6, trust=0.9)
    fact = bridge.bridge.oracle.get_fact("sigrid", "bond_trust")
    assert fact is not None
    assert "0.90" in fact.content.structured_payload.fact_value


# ---------------------------------------------------------------------------
# enrich_system_prompt()
# ---------------------------------------------------------------------------

def test_enrich_returns_string() -> None:
    bridge = _build_bridge()
    bridge.sync_character(_SIGRID_CHAR)
    enriched = bridge.enrich_system_prompt("You are Sigrid.", "Hello")
    assert isinstance(enriched, str)


def test_enrich_contains_base_prompt() -> None:
    bridge = _build_bridge()
    bridge.sync_character(_SIGRID_CHAR)
    enriched = bridge.enrich_system_prompt("BASE PROMPT HERE", "Hello")
    assert "BASE PROMPT HERE" in enriched


def test_enrich_contains_wyrd_section_header() -> None:
    bridge = _build_bridge()
    bridge.sync_character(_SIGRID_CHAR)
    enriched = bridge.enrich_system_prompt("Base", "Hello")
    assert "WYRD WORLD CONTEXT" in enriched


def test_enrich_contains_world_state() -> None:
    bridge = _build_bridge()
    bridge.sync_character(_SIGRID_CHAR)
    enriched = bridge.enrich_system_prompt("Base", "Hello")
    assert "WORLD STATE" in enriched


def test_enrich_truncates_to_max_chars() -> None:
    bridge = _build_bridge(max_context_chars=100)
    bridge.sync_character(_SIGRID_CHAR)
    enriched = bridge.enrich_system_prompt("Base", "Hello")
    # The WYRD block should be short
    wyrd_start = enriched.find("WYRD WORLD CONTEXT")
    assert wyrd_start >= 0
    wyrd_section = enriched[wyrd_start:]
    assert "truncated" in wyrd_section or len(wyrd_section) < 300


def test_enrich_graceful_on_failure() -> None:
    bridge = _build_bridge()
    # Corrupt the oracle to force an exception
    bridge._bridge._oracle._store = None  # type: ignore[assignment]
    enriched = bridge.enrich_system_prompt("FALLBACK BASE", "Hello")
    # Should fall back to the base prompt without raising
    assert "FALLBACK BASE" in enriched


# ---------------------------------------------------------------------------
# push_turn_event()
# ---------------------------------------------------------------------------

def test_push_turn_event_writes_observation() -> None:
    bridge = _build_bridge()
    bridge.push_turn_event("Sigrid smiled.", title="Turn 1")
    records = bridge.bridge.writeback._store.list_by_record_type(
        "observation", store="hugin_observation_store"
    )
    assert any("Turn 1" in r.content.title for r in records)


# ---------------------------------------------------------------------------
# _get_str helper
# ---------------------------------------------------------------------------

def test_get_str_returns_first_match() -> None:
    d = {"mood": "happy", "state": "calm"}
    assert _get_str(d, ["mood", "state"]) == "happy"


def test_get_str_skips_empty_string() -> None:
    d = {"mood": "", "state": "calm"}
    assert _get_str(d, ["mood", "state"]) == "calm"


def test_get_str_returns_default_when_none_match() -> None:
    d = {}
    assert _get_str(d, ["x", "y"], "default") == "default"


def test_get_str_handles_nested_dict() -> None:
    d = {"personality": {"primary": "calm"}}
    assert _get_str(d, ["personality"]) == "calm"
