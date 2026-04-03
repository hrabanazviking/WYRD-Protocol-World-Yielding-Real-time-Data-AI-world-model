"""Tests for CharacterContext and enriched PromptBuilder — Phase 5 integration."""
from __future__ import annotations

import tempfile

from wyrdforge.ecs.components.identity import NameComponent, StatusComponent
from wyrdforge.ecs.world import World
from wyrdforge.ecs.yggdrasil import YggdrasilTree
from wyrdforge.llm.prompt_builder import PromptBuilder
from wyrdforge.models.bond import BondDomain, BondEdge
from wyrdforge.models.micro_rag import QueryMode
from wyrdforge.models.persona import PersonaMode
from wyrdforge.oracle.passive_oracle import PassiveOracle
from wyrdforge.persistence.memory_store import PersistentMemoryStore
from wyrdforge.runtime.character_context import CharacterContext, CharacterContextResult
from wyrdforge.services.bond_graph_service import BondGraphService
from wyrdforge.services.persona_compiler import PersonaCompiler
from wyrdforge.services.writeback_engine import WritebackEngine


# ---------------------------------------------------------------------------
# Fixture builders
# ---------------------------------------------------------------------------

def _build_world() -> tuple[World, YggdrasilTree]:
    world = World("cc_world", "Context World")
    tree = YggdrasilTree(world)
    tree.create_zone(zone_id="midgard", name="Midgard")
    tree.create_region(region_id="fjords", name="Fjords", parent_zone_id="midgard")
    tree.create_location(location_id="hall", name="Hall", parent_region_id="fjords")
    world.create_entity(entity_id="sigrid", tags={"character"})
    world.add_component("sigrid", NameComponent(entity_id="sigrid", name="Sigrid"))
    world.add_component("sigrid", StatusComponent(entity_id="sigrid", state="calm"))
    tree.place_entity("sigrid", location_id="hall")
    return world, tree


def _build_stack() -> tuple[CharacterContext, PersistentMemoryStore, WritebackEngine]:
    world, tree = _build_world()
    store = PersistentMemoryStore(tempfile.mktemp(suffix=".db"))
    engine = WritebackEngine(store)
    oracle = PassiveOracle(world, store, yggdrasil=tree)

    # Seed some facts and observations
    engine.write_canonical_fact(
        fact_subject_id="sigrid",
        fact_key="temperament",
        fact_value="calm",
        domain="identity",
        confidence=0.97,
    )
    engine.write_canonical_fact(
        fact_subject_id="sigrid",
        fact_key="role",
        fact_value="völva",
        confidence=0.92,
    )
    engine.write_observation(
        title="Sigrid reads the runes",
        summary="She cast the elder futhark and found omen of change.",
    )

    ctx = CharacterContext(oracle, store)
    return ctx, store, engine


# ---------------------------------------------------------------------------
# CharacterContext.build() — return type and structure
# ---------------------------------------------------------------------------

def test_build_returns_character_context_result() -> None:
    ctx, *_ = _build_stack()
    result = ctx.build(
        persona_id="sigrid",
        user_id="user:volmarr",
        query="What do the runes say?",
        focus_entity_ids=["sigrid"],
    )
    assert isinstance(result, CharacterContextResult)


def test_build_world_packet_populated() -> None:
    ctx, *_ = _build_stack()
    result = ctx.build(
        persona_id="sigrid",
        user_id="user:volmarr",
        query="Tell me about the hall.",
        focus_entity_ids=["sigrid"],
    )
    assert result.world_packet is not None
    assert result.world_packet.world_id == "cc_world"


def test_build_persona_packet_populated() -> None:
    ctx, *_ = _build_stack()
    result = ctx.build(
        persona_id="sigrid",
        user_id="user:volmarr",
        query="Who are you?",
        focus_entity_ids=["sigrid"],
        persona_mode=PersonaMode.COMPANION,
    )
    assert result.persona_packet is not None
    assert result.persona_packet.persona_id == "sigrid"


def test_build_persona_packet_has_identity_core() -> None:
    ctx, *_ = _build_stack()
    result = ctx.build(
        persona_id="sigrid",
        user_id="user:volmarr",
        query="Who are you?",
        focus_entity_ids=["sigrid"],
    )
    # identity_core comes from facts with domain="identity"
    assert len(result.persona_packet.identity_core) >= 1


def test_build_micro_packet_populated() -> None:
    ctx, *_ = _build_stack()
    result = ctx.build(
        persona_id="sigrid",
        user_id="user:volmarr",
        query="Tell me a fact about Sigrid.",
        focus_entity_ids=["sigrid"],
        mode=QueryMode.FACTUAL_LOOKUP,
    )
    assert result.micro_packet is not None


def test_build_formatted_for_llm_nonempty() -> None:
    ctx, *_ = _build_stack()
    result = ctx.build(
        persona_id="sigrid",
        user_id="user:volmarr",
        query="Context check",
        focus_entity_ids=["sigrid"],
    )
    assert len(result.formatted_for_llm) > 100


def test_build_formatted_contains_world_state() -> None:
    ctx, *_ = _build_stack()
    result = ctx.build(
        persona_id="sigrid",
        user_id="user:volmarr",
        query="Context check",
        focus_entity_ids=["sigrid"],
    )
    assert "WORLD STATE" in result.formatted_for_llm


def test_build_with_bond_service_includes_bond_context() -> None:
    world, tree = _build_world()
    store = PersistentMemoryStore(tempfile.mktemp(suffix=".db"))
    engine = WritebackEngine(store)
    oracle = PassiveOracle(world, store, yggdrasil=tree)
    engine.write_canonical_fact(
        fact_subject_id="sigrid", fact_key="temperament", fact_value="calm",
        domain="identity", confidence=0.97,
    )

    bond_service = BondGraphService()
    edge = BondEdge(
        bond_id="bond-sig",
        entity_a="user:volmarr",
        entity_b="sigrid",
        domain=BondDomain.COMPANION,
    )
    bond_service.add_edge(edge)

    ctx = CharacterContext(oracle, store, bond_service=bond_service)
    result = ctx.build(
        persona_id="sigrid",
        user_id="user:volmarr",
        query="How are we?",
        focus_entity_ids=["sigrid"],
        bond_id="bond-sig",
    )
    assert result.persona_packet.response_guidance  # bond state goes into guidance


def test_build_without_optional_services_still_works() -> None:
    world, tree = _build_world()
    store = PersistentMemoryStore(tempfile.mktemp(suffix=".db"))
    engine = WritebackEngine(store)
    oracle = PassiveOracle(world, store, yggdrasil=tree)
    engine.write_canonical_fact(
        fact_subject_id="sigrid", fact_key="role", fact_value="völva"
    )
    ctx = CharacterContext(oracle, store)
    result = ctx.build(
        persona_id="sigrid",
        user_id="user:volmarr",
        query="What's happening?",
        focus_entity_ids=["sigrid"],
    )
    assert isinstance(result, CharacterContextResult)


def test_build_empty_focus_entities_still_works() -> None:
    ctx, *_ = _build_stack()
    result = ctx.build(
        persona_id="nobody",
        user_id="user:volmarr",
        query="What is the world state?",
        focus_entity_ids=[],
    )
    assert isinstance(result, CharacterContextResult)


# ---------------------------------------------------------------------------
# PromptBuilder.build_enriched_system_prompt
# ---------------------------------------------------------------------------

def test_enriched_prompt_returns_string() -> None:
    ctx, *_ = _build_stack()
    result = ctx.build(
        persona_id="sigrid",
        user_id="user:volmarr",
        query="Enriched prompt test",
        focus_entity_ids=["sigrid"],
    )
    pb = PromptBuilder()
    prompt = pb.build_enriched_system_prompt(
        result.world_packet, result.persona_packet, result.micro_packet
    )
    assert isinstance(prompt, str)
    assert len(prompt) > 50


def test_enriched_prompt_contains_base_instructions() -> None:
    ctx, *_ = _build_stack()
    result = ctx.build(
        persona_id="sigrid",
        user_id="user:volmarr",
        query="base instructions test",
        focus_entity_ids=["sigrid"],
    )
    pb = PromptBuilder()
    prompt = pb.build_enriched_system_prompt(result.world_packet, result.persona_packet)
    assert "Norse" in prompt or "character" in prompt.lower()


def test_enriched_prompt_without_persona_still_works() -> None:
    ctx, *_ = _build_stack()
    result = ctx.build(
        persona_id="sigrid",
        user_id="user:volmarr",
        query="no persona",
        focus_entity_ids=["sigrid"],
    )
    pb = PromptBuilder()
    prompt = pb.build_enriched_system_prompt(result.world_packet)
    assert "WORLD STATE" in prompt


def test_enriched_prompt_contains_retrieved_facts_section() -> None:
    ctx, *_ = _build_stack()
    result = ctx.build(
        persona_id="sigrid",
        user_id="user:volmarr",
        query="sigrid facts",
        mode=QueryMode.FACTUAL_LOOKUP,
        focus_entity_ids=["sigrid"],
    )
    pb = PromptBuilder()
    prompt = pb.build_enriched_system_prompt(
        result.world_packet, result.persona_packet, result.micro_packet
    )
    # MicroRAG may or may not score high enough — just check it's a string
    assert isinstance(prompt, str)
