"""Tests for PassiveOracle — all 9 query types + context packet builder."""
from __future__ import annotations

import tempfile

import pytest

from wyrdforge.ecs.components.character import FactionComponent, HealthComponent
from wyrdforge.ecs.components.identity import DescriptionComponent, NameComponent, StatusComponent
from wyrdforge.ecs.components.spatial import SpatialComponent
from wyrdforge.ecs.world import World
from wyrdforge.ecs.yggdrasil import YggdrasilTree
from wyrdforge.models.common import ApprovalState
from wyrdforge.oracle import PassiveOracle, WorldContextPacket
from wyrdforge.oracle.models import EntitySummary, LocationResult, RelationResult
from wyrdforge.persistence.memory_store import PersistentMemoryStore
from wyrdforge.services.writeback_engine import WritebackEngine


# ---------------------------------------------------------------------------
# Shared fixture builders
# ---------------------------------------------------------------------------

def _build_world() -> tuple[World, YggdrasilTree]:
    """Build a small test world:
        midgard (zone) → fjordlands (region) → hall (location)
                                              → docks (location)
    """
    world = World("test_world", "Test World")
    tree = YggdrasilTree(world)
    tree.create_zone(zone_id="midgard", name="Midgard")
    tree.create_region(region_id="fjordlands", name="Fjordlands", parent_zone_id="midgard")
    tree.create_location(location_id="hall", name="Great Hall", parent_region_id="fjordlands")
    tree.create_location(location_id="docks", name="Docks", parent_region_id="fjordlands")
    return world, tree


def _add_character(
    world: World,
    tree: YggdrasilTree,
    entity_id: str,
    name: str,
    location_id: str,
    status: str = "idle",
    faction_id: str = "",
) -> None:
    world.create_entity(entity_id=entity_id, tags={"character"})
    world.add_component(entity_id, NameComponent(entity_id=entity_id, name=name))
    world.add_component(
        entity_id,
        DescriptionComponent(entity_id=entity_id, short_desc=f"{name} is here."),
    )
    world.add_component(entity_id, StatusComponent(entity_id=entity_id, state=status))
    if faction_id:
        world.add_component(
            entity_id,
            FactionComponent(
                entity_id=entity_id,
                faction_id=faction_id,
                faction_name=faction_id.capitalize(),
                reputation={"thornholt": 0.8},
            ),
        )
    tree.place_entity(entity_id, location_id=location_id)


def _build_store() -> tuple[PersistentMemoryStore, WritebackEngine]:
    store = PersistentMemoryStore(tempfile.mktemp(suffix=".db"))
    engine = WritebackEngine(store)
    return store, engine


def _oracle_with_world_and_facts() -> tuple[PassiveOracle, World, PersistentMemoryStore, WritebackEngine]:
    world, tree = _build_world()
    store, engine = _build_store()

    _add_character(world, tree, "gunnar", "Gunnar Ironside", "hall", faction_id="thornholt")
    _add_character(world, tree, "sigrid", "Sigrid the Völva", "hall")
    _add_character(world, tree, "leif", "Leif the Wanderer", "docks")

    # Seed canonical facts
    engine.write_canonical_fact(
        fact_subject_id="gunnar", fact_key="status", fact_value="alive", confidence=0.95
    )
    engine.write_canonical_fact(
        fact_subject_id="gunnar", fact_key="weapon", fact_value="axe", confidence=0.80
    )
    engine.write_canonical_fact(
        fact_subject_id="sigrid", fact_key="role", fact_value="völva", confidence=0.90
    )
    # Policy
    engine.write_policy(
        title="Honor Code",
        rule_text="All characters must act with honor.",
        policy_kind="behavioral",
    )
    # Observation
    engine.write_observation(
        title="Gunnar enters hall",
        summary="Gunnar walked into the great hall.",
    )

    oracle = PassiveOracle(world, store, yggdrasil=tree)
    return oracle, world, store, engine


# ---------------------------------------------------------------------------
# Query 1: where_is
# ---------------------------------------------------------------------------

def test_where_is_returns_location_result() -> None:
    oracle, *_ = _oracle_with_world_and_facts()
    result = oracle.where_is("gunnar")
    assert isinstance(result, LocationResult)


def test_where_is_entity_in_hall() -> None:
    oracle, *_ = _oracle_with_world_and_facts()
    result = oracle.where_is("gunnar")
    assert result is not None
    assert result.location_id == "hall"


def test_where_is_location_name_populated() -> None:
    oracle, *_ = _oracle_with_world_and_facts()
    result = oracle.where_is("gunnar")
    assert result is not None
    assert result.location_name == "Great Hall"


def test_where_is_path_includes_hierarchy() -> None:
    oracle, *_ = _oracle_with_world_and_facts()
    result = oracle.where_is("gunnar")
    assert result is not None
    assert "midgard" in result.path
    assert "fjordlands" in result.path
    assert "hall" in result.path


def test_where_is_entity_without_spatial() -> None:
    oracle, world, *_ = _oracle_with_world_and_facts()
    world.create_entity(entity_id="ghost", tags={"npc"})
    result = oracle.where_is("ghost")
    assert result is not None
    assert result.location_id is None
    assert result.path == []


def test_where_is_unknown_entity_returns_none() -> None:
    oracle, *_ = _oracle_with_world_and_facts()
    assert oracle.where_is("no_one") is None


# ---------------------------------------------------------------------------
# Query 2: who_is_here
# ---------------------------------------------------------------------------

def test_who_is_here_returns_entities_at_hall() -> None:
    oracle, *_ = _oracle_with_world_and_facts()
    result = oracle.who_is_here("hall")
    ids = [e.entity_id for e in result]
    assert "gunnar" in ids
    assert "sigrid" in ids


def test_who_is_here_excludes_entities_at_other_location() -> None:
    oracle, *_ = _oracle_with_world_and_facts()
    result = oracle.who_is_here("hall")
    ids = [e.entity_id for e in result]
    assert "leif" not in ids


def test_who_is_here_empty_location() -> None:
    oracle, *_ = _oracle_with_world_and_facts()
    result = oracle.who_is_here("docks")
    ids = [e.entity_id for e in result]
    assert "leif" in ids
    assert "gunnar" not in ids


def test_who_is_here_returns_entity_summaries() -> None:
    oracle, *_ = _oracle_with_world_and_facts()
    result = oracle.who_is_here("hall")
    assert all(isinstance(e, EntitySummary) for e in result)


# ---------------------------------------------------------------------------
# Query 3: what_is
# ---------------------------------------------------------------------------

def test_what_is_returns_entity_summary() -> None:
    oracle, *_ = _oracle_with_world_and_facts()
    result = oracle.what_is("gunnar")
    assert isinstance(result, EntitySummary)
    assert result.entity_id == "gunnar"


def test_what_is_name_populated() -> None:
    oracle, *_ = _oracle_with_world_and_facts()
    result = oracle.what_is("gunnar")
    assert result is not None
    assert result.name == "Gunnar Ironside"


def test_what_is_status_populated() -> None:
    oracle, *_ = _oracle_with_world_and_facts()
    result = oracle.what_is("gunnar")
    assert result is not None
    assert result.status == "idle"


def test_what_is_location_populated() -> None:
    oracle, *_ = _oracle_with_world_and_facts()
    result = oracle.what_is("gunnar")
    assert result is not None
    assert result.location_id == "hall"


def test_what_is_unknown_returns_none() -> None:
    oracle, *_ = _oracle_with_world_and_facts()
    assert oracle.what_is("nobody") is None


# ---------------------------------------------------------------------------
# Query 4: get_fact
# ---------------------------------------------------------------------------

def test_get_fact_returns_canonical_record() -> None:
    oracle, *_ = _oracle_with_world_and_facts()
    fact = oracle.get_fact("gunnar", "status")
    assert fact is not None
    assert fact.content.structured_payload.fact_value == "alive"


def test_get_fact_unknown_key_returns_none() -> None:
    oracle, *_ = _oracle_with_world_and_facts()
    assert oracle.get_fact("gunnar", "eye_color") is None


def test_get_fact_returns_highest_confidence_when_multiple() -> None:
    oracle, world, store, engine = _oracle_with_world_and_facts()
    engine.write_canonical_fact(
        fact_subject_id="gunnar", fact_key="weapon", fact_value="sword", confidence=0.99
    )
    fact = oracle.get_fact("gunnar", "weapon")
    assert fact is not None
    assert fact.truth.confidence == 0.99


def test_get_fact_excludes_quarantined() -> None:
    oracle, world, store, engine = _oracle_with_world_and_facts()
    # Only fact for leif
    r = engine.write_canonical_fact(
        fact_subject_id="leif", fact_key="status", fact_value="lost", confidence=0.9
    )
    store.quarantine(r.record_id)
    assert oracle.get_fact("leif", "status") is None


# ---------------------------------------------------------------------------
# Query 5: get_facts
# ---------------------------------------------------------------------------

def test_get_facts_returns_all_for_subject() -> None:
    oracle, *_ = _oracle_with_world_and_facts()
    facts = oracle.get_facts("gunnar")
    keys = {f.content.structured_payload.fact_key for f in facts}
    assert "status" in keys
    assert "weapon" in keys


def test_get_facts_empty_for_unknown_subject() -> None:
    oracle, *_ = _oracle_with_world_and_facts()
    assert oracle.get_facts("unknown_npc") == []


def test_get_facts_excludes_quarantined() -> None:
    oracle, world, store, engine = _oracle_with_world_and_facts()
    r = engine.write_canonical_fact(
        fact_subject_id="sigrid", fact_key="location", fact_value="docks", confidence=0.7
    )
    store.quarantine(r.record_id)
    facts = oracle.get_facts("sigrid")
    assert all(f.content.structured_payload.fact_key != "location" for f in facts)


# ---------------------------------------------------------------------------
# Query 6: get_relations
# ---------------------------------------------------------------------------

def test_get_relations_returns_relation_result() -> None:
    oracle, *_ = _oracle_with_world_and_facts()
    result = oracle.get_relations("gunnar")
    assert isinstance(result, RelationResult)


def test_get_relations_faction_populated() -> None:
    oracle, *_ = _oracle_with_world_and_facts()
    result = oracle.get_relations("gunnar")
    assert result.faction_id == "thornholt"
    assert result.faction_name == "Thornholt"


def test_get_relations_no_faction() -> None:
    oracle, *_ = _oracle_with_world_and_facts()
    result = oracle.get_relations("sigrid")
    assert result.faction_id is None


def test_get_relations_co_located_includes_hall_mates() -> None:
    oracle, *_ = _oracle_with_world_and_facts()
    result = oracle.get_relations("gunnar")
    assert "sigrid" in result.co_located_entity_ids


def test_get_relations_co_located_excludes_other_locations() -> None:
    oracle, *_ = _oracle_with_world_and_facts()
    result = oracle.get_relations("gunnar")
    assert "leif" not in result.co_located_entity_ids


# ---------------------------------------------------------------------------
# Query 7: get_nearby
# ---------------------------------------------------------------------------

def test_get_nearby_returns_co_located_entities() -> None:
    oracle, *_ = _oracle_with_world_and_facts()
    result = oracle.get_nearby("gunnar")
    ids = [e.entity_id for e in result]
    assert "sigrid" in ids


def test_get_nearby_excludes_self() -> None:
    oracle, *_ = _oracle_with_world_and_facts()
    result = oracle.get_nearby("gunnar")
    ids = [e.entity_id for e in result]
    assert "gunnar" not in ids


def test_get_nearby_entity_without_spatial_returns_empty() -> None:
    oracle, world, *_ = _oracle_with_world_and_facts()
    world.create_entity(entity_id="wanderer_nowhere", tags={"npc"})
    result = oracle.get_nearby("wanderer_nowhere")
    assert result == []


# ---------------------------------------------------------------------------
# Query 8: search_facts
# ---------------------------------------------------------------------------

def test_search_facts_finds_matching() -> None:
    oracle, *_ = _oracle_with_world_and_facts()
    results = oracle.search_facts("alive")
    assert len(results) >= 1


def test_search_facts_returns_empty_for_no_match() -> None:
    oracle, *_ = _oracle_with_world_and_facts()
    results = oracle.search_facts("xyzzy_impossible_query_term")
    assert results == []


def test_search_facts_respects_limit() -> None:
    oracle, *_ = _oracle_with_world_and_facts()
    results = oracle.search_facts("gunnar", limit=1)
    assert len(results) <= 1


def test_search_facts_excludes_quarantined() -> None:
    oracle, world, store, engine = _oracle_with_world_and_facts()
    r = engine.write_canonical_fact(
        fact_subject_id="gunnar", fact_key="mood", fact_value="angered", confidence=0.9
    )
    store.quarantine(r.record_id)
    results = oracle.search_facts("angered")
    assert all(f.content.structured_payload.fact_value != "angered" for f in results)


# ---------------------------------------------------------------------------
# Query 9: build_context_packet
# ---------------------------------------------------------------------------

def test_build_context_packet_returns_world_context_packet() -> None:
    oracle, *_ = _oracle_with_world_and_facts()
    packet = oracle.build_context_packet(focus_entity_ids=["gunnar"])
    assert isinstance(packet, WorldContextPacket)


def test_build_context_packet_focus_entities_populated() -> None:
    oracle, *_ = _oracle_with_world_and_facts()
    packet = oracle.build_context_packet(focus_entity_ids=["gunnar"])
    ids = [e.entity_id for e in packet.focus_entities]
    assert "gunnar" in ids


def test_build_context_packet_location_context_inferred() -> None:
    oracle, *_ = _oracle_with_world_and_facts()
    packet = oracle.build_context_packet(focus_entity_ids=["gunnar"])
    assert packet.location_context is not None
    assert packet.location_context.location_id == "hall"


def test_build_context_packet_location_override() -> None:
    oracle, *_ = _oracle_with_world_and_facts()
    packet = oracle.build_context_packet(focus_entity_ids=["gunnar"], location_id="docks")
    assert packet.location_context is not None
    assert packet.location_context.location_id == "docks"


def test_build_context_packet_canonical_facts_included() -> None:
    oracle, *_ = _oracle_with_world_and_facts()
    packet = oracle.build_context_packet(focus_entity_ids=["gunnar"])
    assert "gunnar" in packet.canonical_facts
    keys = {f.fact_key for f in packet.canonical_facts["gunnar"]}
    assert "status" in keys


def test_build_context_packet_policies_included() -> None:
    oracle, *_ = _oracle_with_world_and_facts()
    packet = oracle.build_context_packet(focus_entity_ids=["gunnar"])
    assert len(packet.active_policies) >= 1
    assert any("honor" in p.rule_text.lower() for p in packet.active_policies)


def test_build_context_packet_no_policies_when_excluded() -> None:
    oracle, *_ = _oracle_with_world_and_facts()
    packet = oracle.build_context_packet(
        focus_entity_ids=["gunnar"], include_policies=False
    )
    assert packet.active_policies == []


def test_build_context_packet_observations_included() -> None:
    oracle, *_ = _oracle_with_world_and_facts()
    packet = oracle.build_context_packet(focus_entity_ids=["gunnar"])
    assert len(packet.recent_observations) >= 1


def test_build_context_packet_no_observations_when_excluded() -> None:
    oracle, *_ = _oracle_with_world_and_facts()
    packet = oracle.build_context_packet(
        focus_entity_ids=["gunnar"], include_observations=False
    )
    assert packet.recent_observations == []


def test_build_context_packet_formatted_for_llm_is_nonempty() -> None:
    oracle, *_ = _oracle_with_world_and_facts()
    packet = oracle.build_context_packet(focus_entity_ids=["gunnar"])
    assert len(packet.formatted_for_llm) > 50


def test_build_context_packet_formatted_contains_entity_name() -> None:
    oracle, *_ = _oracle_with_world_and_facts()
    packet = oracle.build_context_packet(focus_entity_ids=["gunnar"])
    assert "Gunnar" in packet.formatted_for_llm


def test_build_context_packet_world_id_matches() -> None:
    oracle, *_ = _oracle_with_world_and_facts()
    packet = oracle.build_context_packet(focus_entity_ids=["gunnar"])
    assert packet.world_id == "test_world"


def test_build_context_packet_present_entities_at_location() -> None:
    oracle, *_ = _oracle_with_world_and_facts()
    packet = oracle.build_context_packet(focus_entity_ids=["gunnar"])
    present_ids = [e.entity_id for e in packet.present_entities]
    assert "sigrid" in present_ids


def test_build_context_packet_open_contradiction_count() -> None:
    oracle, *_ = _oracle_with_world_and_facts()
    packet = oracle.build_context_packet(focus_entity_ids=["gunnar"])
    # No contradictions seeded
    assert packet.open_contradiction_count == 0
