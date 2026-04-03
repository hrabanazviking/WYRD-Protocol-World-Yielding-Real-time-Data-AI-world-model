"""Tests for PythonRPGBridge — Phase 6 Bifrost in-process adapter."""
from __future__ import annotations

import tempfile

from wyrdforge.bridges.python_rpg import BridgeConfig, PythonRPGBridge
from wyrdforge.ecs.components.identity import NameComponent, StatusComponent
from wyrdforge.ecs.world import World
from wyrdforge.ecs.yggdrasil import YggdrasilTree
from wyrdforge.llm.ollama_connector import OllamaConnector
from wyrdforge.models.bond import BondDomain, BondEdge
from wyrdforge.persistence.memory_store import PersistentMemoryStore
from wyrdforge.services.bond_graph_service import BondGraphService


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _build_world() -> tuple[World, YggdrasilTree]:
    world = World("rpg_world", "RPG World")
    tree = YggdrasilTree(world)
    tree.create_zone(zone_id="midgard", name="Midgard")
    tree.create_region(region_id="fjords", name="Fjords", parent_zone_id="midgard")
    tree.create_location(location_id="hall", name="Hall", parent_region_id="fjords")
    world.create_entity(entity_id="sigrid", tags={"character"})
    world.add_component("sigrid", NameComponent(entity_id="sigrid", name="Sigrid"))
    world.add_component("sigrid", StatusComponent(entity_id="sigrid", state="calm"))
    tree.place_entity("sigrid", location_id="hall")
    return world, tree


def _build_bridge(*, with_connector: bool = False) -> PythonRPGBridge:
    world, tree = _build_world()
    store = PersistentMemoryStore(tempfile.mktemp(suffix=".db"))
    connector = OllamaConnector() if with_connector else None
    bridge = PythonRPGBridge(world, tree, store, connector)
    bridge.writeback.write_canonical_fact(
        fact_subject_id="sigrid",
        fact_key="temperament",
        fact_value="calm",
        domain="identity",
        confidence=0.95,
    )
    return bridge


# ---------------------------------------------------------------------------
# from_config
# ---------------------------------------------------------------------------

def test_from_config_creates_bridge() -> None:
    cfg = BridgeConfig(world_id="test_world", db_path=tempfile.mktemp(suffix=".db"))
    bridge = PythonRPGBridge.from_config(cfg)
    assert isinstance(bridge, PythonRPGBridge)


def test_from_config_world_id_matches() -> None:
    cfg = BridgeConfig(world_id="saga_world", db_path=tempfile.mktemp(suffix=".db"))
    bridge = PythonRPGBridge.from_config(cfg)
    assert bridge.world.world_id == "saga_world"


def test_from_config_bond_service_created_when_enabled() -> None:
    cfg = BridgeConfig(db_path=tempfile.mktemp(suffix=".db"), use_bond_service=True)
    bridge = PythonRPGBridge.from_config(cfg)
    assert bridge.bond_service is not None


def test_from_config_bond_service_none_when_disabled() -> None:
    cfg = BridgeConfig(db_path=tempfile.mktemp(suffix=".db"), use_bond_service=False)
    bridge = PythonRPGBridge.from_config(cfg)
    assert bridge.bond_service is None


# ---------------------------------------------------------------------------
# query — no LLM (use_turn_loop=False)
# ---------------------------------------------------------------------------

def test_query_no_llm_returns_string() -> None:
    bridge = _build_bridge()
    result = bridge.query("sigrid", "What's happening?", use_turn_loop=False)
    assert isinstance(result, str)
    assert len(result) > 0


def test_query_no_llm_contains_world_state() -> None:
    bridge = _build_bridge()
    result = bridge.query("sigrid", "World check", use_turn_loop=False)
    assert "WORLD STATE" in result


def test_query_no_llm_contains_identity_from_facts() -> None:
    bridge = _build_bridge()
    result = bridge.query("sigrid", "Who are you?", use_turn_loop=False)
    # identity_core comes from facts with domain=identity
    assert "IDENTITY" in result


def test_query_with_location_override() -> None:
    bridge = _build_bridge()
    result = bridge.query(
        "sigrid", "Where am I?", use_turn_loop=False, location_id="hall"
    )
    assert isinstance(result, str)


def test_query_no_llm_focus_entities_override() -> None:
    bridge = _build_bridge()
    result = bridge.query(
        "sigrid",
        "Context check",
        use_turn_loop=False,
        focus_entity_ids=["sigrid"],
    )
    assert isinstance(result, str)


def test_query_no_llm_empty_focus_entities() -> None:
    bridge = _build_bridge()
    result = bridge.query(
        "sigrid",
        "Empty focus",
        use_turn_loop=False,
        focus_entity_ids=[],
    )
    assert isinstance(result, str)


# ---------------------------------------------------------------------------
# query — with TurnLoop (MockConnector)
# ---------------------------------------------------------------------------

class _MockConnector(OllamaConnector):
    def __init__(self) -> None:
        super().__init__()
        self.called_with: list[str] = []

    def chat(self, messages, *, model=None, temperature=0.7, stream=False) -> str:
        user_msg = next((m["content"] for m in reversed(messages) if m["role"] == "user"), "")
        self.called_with.append(user_msg)
        return f"[mock] Echo: {user_msg}"

    def is_available(self) -> bool:
        return True


def _build_bridge_with_mock() -> tuple[PythonRPGBridge, _MockConnector]:
    world, tree = _build_world()
    store = PersistentMemoryStore(tempfile.mktemp(suffix=".db"))
    mock = _MockConnector()
    bridge = PythonRPGBridge(world, tree, store, mock)
    bridge.writeback.write_canonical_fact(
        fact_subject_id="sigrid", fact_key="role", fact_value="völva"
    )
    return bridge, mock


def test_query_turn_loop_calls_connector() -> None:
    bridge, mock = _build_bridge_with_mock()
    reply = bridge.query("sigrid", "Tell me a secret.", use_turn_loop=True)
    assert "[mock]" in reply
    assert len(mock.called_with) == 1


def test_query_turn_loop_returns_response_string() -> None:
    bridge, _ = _build_bridge_with_mock()
    reply = bridge.query("sigrid", "Hello.", use_turn_loop=True)
    assert isinstance(reply, str)
    assert len(reply) > 0


def test_query_turn_loop_preserves_history_across_calls() -> None:
    bridge, mock = _build_bridge_with_mock()
    bridge.query("sigrid", "First message.", use_turn_loop=True)
    bridge.query("sigrid", "Second message.", use_turn_loop=True)
    assert len(mock.called_with) == 2


def test_clear_history_resets_turn_count() -> None:
    bridge, _ = _build_bridge_with_mock()
    bridge.query("sigrid", "Hello.", use_turn_loop=True)
    bridge.clear_history("sigrid")
    loop = bridge._turn_loops.get("sigrid")
    if loop:
        assert loop.history_turn_count() == 0


def test_clear_history_unknown_persona_does_not_raise() -> None:
    bridge, _ = _build_bridge_with_mock()
    bridge.clear_history("nobody")  # should not raise


# ---------------------------------------------------------------------------
# push_event
# ---------------------------------------------------------------------------

def test_push_event_observation_writes_to_store() -> None:
    bridge = _build_bridge()
    bridge.push_event("observation", {"title": "Storm", "summary": "A storm brews."})
    records = bridge.writeback._store.list_by_record_type(
        "observation", store="hugin_observation_store"
    )
    assert any("Storm" in r.content.title for r in records)


def test_push_event_fact_writes_to_store() -> None:
    bridge = _build_bridge()
    bridge.push_event("fact", {"subject_id": "gunnar", "key": "status", "value": "injured"})
    fact = bridge.oracle.get_fact("gunnar", "status")
    assert fact is not None
    assert fact.content.structured_payload.fact_value == "injured"


def test_push_event_unknown_type_does_not_raise() -> None:
    bridge = _build_bridge()
    bridge.push_event("unknown_event_type", {"data": "whatever"})


# ---------------------------------------------------------------------------
# Accessors
# ---------------------------------------------------------------------------

def test_world_accessor() -> None:
    bridge = _build_bridge()
    assert bridge.world is not None


def test_yggdrasil_accessor() -> None:
    bridge = _build_bridge()
    assert bridge.yggdrasil is not None


def test_oracle_accessor() -> None:
    bridge = _build_bridge()
    assert bridge.oracle is not None


def test_writeback_accessor() -> None:
    bridge = _build_bridge()
    assert bridge.writeback is not None


def test_teardown_does_not_raise() -> None:
    bridge = _build_bridge()
    bridge.teardown()


# ---------------------------------------------------------------------------
# BondGraphService integration
# ---------------------------------------------------------------------------

def test_bond_service_query_with_bond_id() -> None:
    world, tree = _build_world()
    store = PersistentMemoryStore(tempfile.mktemp(suffix=".db"))
    bond_svc = BondGraphService()
    bond_svc.add_edge(
        BondEdge(
            bond_id="bond-sig",
            entity_a="player",
            entity_b="sigrid",
            domain=BondDomain.COMPANION,
        )
    )
    bridge = PythonRPGBridge(world, tree, store, None, bond_service=bond_svc)
    bridge.writeback.write_canonical_fact(
        fact_subject_id="sigrid", fact_key="temperament", fact_value="warm"
    )
    result = bridge.query(
        "sigrid", "How close are we?", use_turn_loop=False, bond_id="bond-sig"
    )
    assert isinstance(result, str)
