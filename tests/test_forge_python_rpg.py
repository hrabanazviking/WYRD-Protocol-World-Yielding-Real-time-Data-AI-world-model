"""Forge tests: PythonRPGBridge.query() input floor.

Proves query() enforces the same input discipline as the HTTP handler —
non-empty persona_id/user_input, bounded by MAX_ID_CHARS /
MAX_QUERY_INPUT_CHARS — raising InputValidationError before any world or
LLM work begins.
"""
from __future__ import annotations

import tempfile

import pytest

from wyrdforge.bridges.python_rpg import PythonRPGBridge
from wyrdforge.ecs.components.identity import NameComponent, StatusComponent
from wyrdforge.ecs.world import World
from wyrdforge.ecs.yggdrasil import YggdrasilTree
from wyrdforge.hardening.input_validation import (
    MAX_ID_CHARS,
    MAX_QUERY_INPUT_CHARS,
    InputValidationError,
)
from wyrdforge.persistence.memory_store import PersistentMemoryStore


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _build_bridge() -> PythonRPGBridge:
    world = World("rpg_floor_world", "RPG Floor World")
    tree = YggdrasilTree(world)
    tree.create_zone(zone_id="midgard", name="Midgard")
    tree.create_region(region_id="fjords", name="Fjords", parent_zone_id="midgard")
    tree.create_location(location_id="hall", name="Hall", parent_region_id="fjords")
    world.create_entity(entity_id="sigrid", tags={"character"})
    world.add_component("sigrid", NameComponent(entity_id="sigrid", name="Sigrid"))
    world.add_component("sigrid", StatusComponent(entity_id="sigrid", state="calm"))
    tree.place_entity("sigrid", location_id="hall")
    store = PersistentMemoryStore(tempfile.mktemp(suffix=".db"))
    return PythonRPGBridge(world, tree, store, None)


# ---------------------------------------------------------------------------
# Empty / missing inputs
# ---------------------------------------------------------------------------

def test_empty_persona_id_raises() -> None:
    bridge = _build_bridge()
    with pytest.raises(InputValidationError) as exc_info:
        bridge.query("", "Hello", use_turn_loop=False)
    assert exc_info.value.field == "persona_id"


def test_whitespace_persona_id_raises() -> None:
    bridge = _build_bridge()
    with pytest.raises(InputValidationError):
        bridge.query("   ", "Hello", use_turn_loop=False)


def test_empty_user_input_raises() -> None:
    bridge = _build_bridge()
    with pytest.raises(InputValidationError) as exc_info:
        bridge.query("sigrid", "", use_turn_loop=False)
    assert exc_info.value.field == "user_input"


def test_none_persona_id_raises() -> None:
    bridge = _build_bridge()
    with pytest.raises(InputValidationError):
        bridge.query(None, "Hello", use_turn_loop=False)  # type: ignore[arg-type]


def test_none_user_input_raises() -> None:
    bridge = _build_bridge()
    with pytest.raises(InputValidationError):
        bridge.query("sigrid", None, use_turn_loop=False)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Overlong inputs
# ---------------------------------------------------------------------------

def test_overlong_persona_id_raises() -> None:
    bridge = _build_bridge()
    with pytest.raises(InputValidationError) as exc_info:
        bridge.query("x" * (MAX_ID_CHARS + 1), "Hello", use_turn_loop=False)
    assert exc_info.value.field == "persona_id"


def test_overlong_user_input_raises() -> None:
    bridge = _build_bridge()
    with pytest.raises(InputValidationError) as exc_info:
        bridge.query("sigrid", "x" * (MAX_QUERY_INPUT_CHARS + 1), use_turn_loop=False)
    assert exc_info.value.field == "user_input"


def test_max_length_inputs_pass() -> None:
    # Boundary: exactly at the cap is legal (the HTTP handler uses the
    # same check_string bounds, so the floor matches the door).
    bridge = _build_bridge()
    result = bridge.query(
        "s" * MAX_ID_CHARS, "x" * MAX_QUERY_INPUT_CHARS, use_turn_loop=False
    )
    assert isinstance(result, str)


# ---------------------------------------------------------------------------
# Valid input passes through
# ---------------------------------------------------------------------------

def test_valid_input_returns_response() -> None:
    bridge = _build_bridge()
    result = bridge.query("sigrid", "Hello", use_turn_loop=False)
    assert isinstance(result, str)
    assert len(result) > 0
