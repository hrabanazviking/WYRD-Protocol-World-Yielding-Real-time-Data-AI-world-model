"""
Tests for Godot 4 WyrdForge plugin logic (Phase 11A).
Validates Python equivalents of GDScript pure functions:
  - normalize_persona_id (game integration version)
  - push_world_event summary builder
  - scene_location_id resolution
  - entity registry logic
"""
from __future__ import annotations

import json


# ---------------------------------------------------------------------------
# Python equivalents of wyrd_bridge.gd (game integration) pure functions
# ---------------------------------------------------------------------------

def normalize_persona_id(name: str) -> str:
    result = name.lower()
    out = []
    last_underscore = False
    for c in result:
        if c.isalnum() or c == "_":
            out.append(c)
            last_underscore = (c == "_")
        elif not last_underscore:
            out.append("_")
            last_underscore = True
    s = "".join(out).strip("_")
    return s[:64]


def build_world_event_summary(event_name: str, data: dict) -> tuple[str, str]:
    """Returns (title, summary) for push_observation."""
    parts = [f"{k}={v}" for k, v in data.items()]
    summary = ", ".join(parts) if parts else event_name
    return event_name, summary


def resolve_scene_location(scene_name: str, scene_location_map: dict) -> str:
    """Resolve a Godot scene name to a Yggdrasil location_id."""
    return scene_location_map.get(scene_name, normalize_persona_id(scene_name))


def build_location_sync_body(location_id: str) -> dict:
    """Build the WYRD /event body for syncing current scene location."""
    return {
        "event_type": "fact",
        "payload": {"subject_id": "__world__", "key": "current_location", "value": location_id},
    }


def get_registered_personas(entity_registry: list) -> list[str]:
    """Return persona IDs from the entity registry (simulated)."""
    return [e["persona_id"] for e in entity_registry if e.get("persona_id")]


# ---------------------------------------------------------------------------
# Tests: normalize_persona_id (same contract as SDK, re-verified here)
# ---------------------------------------------------------------------------

class TestNormalizePersonaId:

    def test_lowercases(self):
        assert normalize_persona_id("Sigrid") == "sigrid"

    def test_spaces_to_underscore(self):
        assert normalize_persona_id("Erik Red") == "erik_red"

    def test_collapses_underscores(self):
        assert normalize_persona_id("a  b") == "a_b"

    def test_truncates_at_64(self):
        assert len(normalize_persona_id("x" * 100)) == 64

    def test_empty(self):
        assert normalize_persona_id("") == ""

    def test_numbers(self):
        assert normalize_persona_id("Player1") == "player1"

    def test_hyphens(self):
        assert normalize_persona_id("goblin-lord") == "goblin_lord"


# ---------------------------------------------------------------------------
# Tests: build_world_event_summary
# ---------------------------------------------------------------------------

class TestBuildWorldEventSummary:

    def test_title_is_event_name(self):
        title, _ = build_world_event_summary("combat_start", {})
        assert title == "combat_start"

    def test_summary_contains_data_fields(self):
        _, summary = build_world_event_summary("combat_start", {"attacker": "sigrid", "target": "goblin"})
        assert "attacker=sigrid" in summary
        assert "target=goblin" in summary

    def test_empty_data_returns_event_name(self):
        _, summary = build_world_event_summary("level_up", {})
        assert summary == "level_up"

    def test_multiple_fields(self):
        _, summary = build_world_event_summary("x", {"a": "1", "b": "2", "c": "3"})
        assert summary.count("=") == 3


# ---------------------------------------------------------------------------
# Tests: resolve_scene_location
# ---------------------------------------------------------------------------

class TestResolveSceneLocation:

    def test_uses_map_when_present(self):
        scene_map = {"MeadHall": "hall", "Forest": "deep_forest"}
        assert resolve_scene_location("MeadHall", scene_map) == "hall"

    def test_normalizes_when_not_in_map(self):
        assert resolve_scene_location("Dark Forest", {}) == "dark_forest"

    def test_empty_scene_name(self):
        result = resolve_scene_location("", {})
        assert isinstance(result, str)

    def test_map_takes_priority(self):
        scene_map = {"x": "custom_id"}
        assert resolve_scene_location("x", scene_map) == "custom_id"

    def test_normalization_for_complex_name(self):
        result = resolve_scene_location("Main_Menu_V2", {})
        assert result == "main_menu_v2"


# ---------------------------------------------------------------------------
# Tests: build_location_sync_body
# ---------------------------------------------------------------------------

class TestBuildLocationSyncBody:

    def test_event_type_is_fact(self):
        body = build_location_sync_body("hall")
        assert body["event_type"] == "fact"

    def test_subject_id_is_world(self):
        body = build_location_sync_body("hall")
        assert body["payload"]["subject_id"] == "__world__"

    def test_key_is_current_location(self):
        body = build_location_sync_body("forest")
        assert body["payload"]["key"] == "current_location"

    def test_value_is_location_id(self):
        body = build_location_sync_body("deep_forest")
        assert body["payload"]["value"] == "deep_forest"

    def test_serializes_to_json(self):
        assert json.dumps(build_location_sync_body("hall"))


# ---------------------------------------------------------------------------
# Tests: get_registered_personas
# ---------------------------------------------------------------------------

class TestGetRegisteredPersonas:

    def test_returns_empty_for_empty_registry(self):
        assert get_registered_personas([]) == []

    def test_returns_persona_ids(self):
        registry = [{"persona_id": "sigrid"}, {"persona_id": "gunnar"}]
        assert get_registered_personas(registry) == ["sigrid", "gunnar"]

    def test_skips_entries_without_persona_id(self):
        registry = [{"persona_id": "sigrid"}, {"name": "orphan"}]
        assert get_registered_personas(registry) == ["sigrid"]

    def test_multiple_entities(self):
        registry = [{"persona_id": f"entity_{i}"} for i in range(5)]
        result = get_registered_personas(registry)
        assert len(result) == 5
