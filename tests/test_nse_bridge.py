"""Tests for NSEWyrdBridge — Phase 9B Norse Saga Engine integration."""
from __future__ import annotations

import tempfile
from typing import Any
from unittest.mock import MagicMock, PropertyMock

from wyrdforge.bridges.nse_bridge import NSEWyrdBridge, _normalize_id, _nse_char_id, _nse_str
from wyrdforge.runtime.character_context import CharacterContextResult


# ---------------------------------------------------------------------------
# Minimal NSE engine mock
# ---------------------------------------------------------------------------

def _mock_nse(
    *,
    location: str = "The Mead Hall",
    characters: list[dict[str, Any]] | None = None,
) -> MagicMock:
    """Return a mock YggdrasilEngine with minimal surface area."""
    engine = MagicMock()
    engine.get_current_location_display.return_value = location
    engine.get_mead_hall_location_id.return_value = "mead_hall"
    engine._load_all_characters.return_value = characters or [
        {
            "name": "Sigrid",
            "role": "völva",
            "personality": "calm and wise",
            "mood": "serene",
            "health": "alive",
        },
        {
            "name": "Gunnar",
            "role": "warrior",
            "class": "Berserker",
            "health": "wounded",
        },
    ]
    engine._characters = engine._load_all_characters.return_value
    return engine


def _build_bridge(nse_engine: MagicMock | None = None) -> NSEWyrdBridge:
    engine = nse_engine or _mock_nse()
    return NSEWyrdBridge(engine, db_path=tempfile.mktemp(suffix=".db"))


# ---------------------------------------------------------------------------
# Construction
# ---------------------------------------------------------------------------

def test_construction_succeeds() -> None:
    bridge = _build_bridge()
    assert bridge is not None


def test_bridge_property_returns_python_rpg_bridge() -> None:
    from wyrdforge.bridges.python_rpg import PythonRPGBridge
    bridge = _build_bridge()
    assert isinstance(bridge.bridge, PythonRPGBridge)


def test_world_id_is_nse_world() -> None:
    bridge = _build_bridge()
    assert bridge.bridge.world.world_id == "nse_world"


# ---------------------------------------------------------------------------
# sync() — entity registration
# ---------------------------------------------------------------------------

def test_sync_registers_character_entities() -> None:
    bridge = _build_bridge()
    bridge.sync()
    world = bridge.bridge.world
    # sigrid and gunnar should be registered
    assert world.get_entity("sigrid") is not None
    assert world.get_entity("gunnar") is not None


def test_sync_registers_name_components() -> None:
    bridge = _build_bridge()
    bridge.sync()
    world = bridge.bridge.world
    name_comp = world.get_component("sigrid", "name")
    assert name_comp is not None
    assert name_comp.name == "Sigrid"


def test_sync_registers_status_components() -> None:
    bridge = _build_bridge()
    bridge.sync()
    world = bridge.bridge.world
    status = world.get_component("sigrid", "status")
    assert status is not None
    assert "alive" in status.state or "serene" in status.state


def test_sync_writes_canonical_facts() -> None:
    bridge = _build_bridge()
    bridge.sync()
    fact = bridge.bridge.oracle.get_fact("sigrid", "role")
    assert fact is not None
    assert fact.content.structured_payload.fact_value == "völva"


def test_sync_writes_personality_fact() -> None:
    bridge = _build_bridge()
    bridge.sync()
    fact = bridge.bridge.oracle.get_fact("sigrid", "personality")
    assert fact is not None


def test_sync_is_idempotent() -> None:
    bridge = _build_bridge()
    bridge.sync()
    bridge.sync()  # second sync should not raise or duplicate
    world = bridge.bridge.world
    # Entity exists exactly once
    assert world.get_entity("sigrid") is not None


def test_sync_with_empty_character_list() -> None:
    bridge = _build_bridge(_mock_nse(characters=[]))
    bridge.sync()  # should not raise


def test_sync_with_characters_missing_fields() -> None:
    bridge = _build_bridge(_mock_nse(characters=[{"name": "Ghost"}]))
    bridge.sync()
    world = bridge.bridge.world
    assert world.get_entity("ghost") is not None


# ---------------------------------------------------------------------------
# sync() — location
# ---------------------------------------------------------------------------

def test_sync_creates_location_node() -> None:
    bridge = _build_bridge(_mock_nse(location="The Great Hall"))
    bridge.sync()
    entity = bridge.bridge.world.get_entity("the_great_hall")
    assert entity is not None


def test_sync_writes_location_observation() -> None:
    bridge = _build_bridge(_mock_nse(location="Longship Deck"))
    bridge.sync()
    records = bridge.bridge.writeback._store.list_by_record_type(
        "observation", store="hugin_observation_store"
    )
    assert any("Longship" in r.content.title for r in records)


def test_sync_graceful_when_location_raises() -> None:
    engine = _mock_nse()
    engine.get_current_location_display.side_effect = RuntimeError("no location")
    bridge = NSEWyrdBridge(engine, db_path=tempfile.mktemp(suffix=".db"))
    bridge.sync()  # should not raise


# ---------------------------------------------------------------------------
# get_context_for_npc()
# ---------------------------------------------------------------------------

def test_get_context_returns_result() -> None:
    bridge = _build_bridge()
    bridge.sync()
    result = bridge.get_context_for_npc("sigrid")
    assert isinstance(result, CharacterContextResult)


def test_get_context_has_world_state() -> None:
    bridge = _build_bridge()
    bridge.sync()
    result = bridge.get_context_for_npc("sigrid", player_input="Who are you?")
    assert "WORLD STATE" in result.formatted_for_llm


def test_get_context_identity_includes_facts() -> None:
    bridge = _build_bridge()
    bridge.sync()
    result = bridge.get_context_for_npc("sigrid")
    assert "IDENTITY" in result.formatted_for_llm


def test_get_context_unknown_npc_still_returns_result() -> None:
    bridge = _build_bridge()
    bridge.sync()
    result = bridge.get_context_for_npc("nobody")
    assert isinstance(result, CharacterContextResult)


# ---------------------------------------------------------------------------
# query_npc()
# ---------------------------------------------------------------------------

def test_query_npc_returns_string() -> None:
    bridge = _build_bridge()
    bridge.sync()
    result = bridge.query_npc("sigrid", "Greetings", use_turn_loop=False)
    assert isinstance(result, str)
    assert len(result) > 0


# ---------------------------------------------------------------------------
# push_turn_observation()
# ---------------------------------------------------------------------------

def test_push_turn_observation_writes_to_store() -> None:
    bridge = _build_bridge()
    bridge.sync()
    bridge.push_turn_observation("Sigrid speaks", "She spoke of the Norns.")
    records = bridge.bridge.writeback._store.list_by_record_type(
        "observation", store="hugin_observation_store"
    )
    assert any("Sigrid speaks" in r.content.title for r in records)


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------

def test_normalize_id_lowercases() -> None:
    assert _normalize_id("The Mead Hall") == "the_mead_hall"


def test_normalize_id_replaces_hyphens() -> None:
    assert _normalize_id("long-hall") == "long_hall"


def test_normalize_id_truncates_at_64() -> None:
    long = "a" * 100
    assert len(_normalize_id(long)) == 64


def test_nse_char_id_uses_name() -> None:
    char = {"name": "Sigrid Völva"}
    assert _nse_char_id(char) == "sigrid_v\u00f6lva"


def test_nse_char_id_empty_dict_returns_empty() -> None:
    assert _nse_char_id({}) == ""


def test_nse_str_returns_stripped_value() -> None:
    char = {"role": "  völva  "}
    assert _nse_str(char, "role") == "völva"


def test_nse_str_returns_default_when_missing() -> None:
    assert _nse_str({}, "role", "unknown") == "unknown"


def test_nse_str_handles_dict_value() -> None:
    char = {"personality": {"primary": "calm"}}
    result = _nse_str(char, "personality")
    assert result == "calm"
