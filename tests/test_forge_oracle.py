"""Forge tests — PassiveOracle degradation (slice 10).

When the memory/belief layer raises, build_context_packet must not raise:
it logs a single warning and returns a valid WorldContextPacket whose
world-identity fields (ECS-derived) stay intact while memory-derived lists
come back empty.  A healthy-path regression test proves the seam did not
change normal behaviour.
"""
from __future__ import annotations

import logging
import tempfile

import pytest

from wyrdforge.ecs.components.identity import NameComponent
from wyrdforge.ecs.world import World
from wyrdforge.ecs.yggdrasil import YggdrasilTree
from wyrdforge.oracle.models import WorldContextPacket
from wyrdforge.oracle.passive_oracle import PassiveOracle
from wyrdforge.persistence.memory_store import PersistentMemoryStore
from wyrdforge.services.writeback_engine import WritebackEngine


def _build_world() -> tuple[World, YggdrasilTree]:
    world = World("degrade_world", "Degradation Test World")
    tree = YggdrasilTree(world)
    tree.create_zone(zone_id="midgard", name="Midgard")
    tree.create_region(region_id="fjords", name="Fjords", parent_zone_id="midgard")
    tree.create_location(location_id="hall", name="Great Hall", parent_region_id="fjords")
    world.create_entity(entity_id="gunnar", tags={"character"})
    world.add_component("gunnar", NameComponent(entity_id="gunnar", name="Gunnar"))
    tree.place_entity("gunnar", location_id="hall")
    return world, tree


def _build_oracle() -> tuple[PassiveOracle, PersistentMemoryStore]:
    world, tree = _build_world()
    store = PersistentMemoryStore(tempfile.mktemp(suffix=".db"))
    return PassiveOracle(world, store, yggdrasil=tree), store


def _raise(exc_type: type[Exception] = RuntimeError):
    def _boom(*args, **kwargs):
        raise exc_type("store is down")
    return _boom


@pytest.fixture
def broken_store_oracle(monkeypatch) -> PassiveOracle:
    """Oracle whose memory store raises on every read."""
    oracle, store = _build_oracle()
    monkeypatch.setattr(store, "list_by_record_type", _raise(RuntimeError))
    monkeypatch.setattr(store, "all", _raise(RuntimeError))
    monkeypatch.setattr(store, "search", _raise(RuntimeError))
    return oracle


# ---------------------------------------------------------------------------
# Degradation
# ---------------------------------------------------------------------------

def test_memory_failure_returns_valid_packet_no_raise(
    broken_store_oracle: PassiveOracle,
) -> None:
    packet = broken_store_oracle.build_context_packet(
        focus_entity_ids=["gunnar"], location_id="hall",
    )
    assert isinstance(packet, WorldContextPacket)


def test_memory_failure_empties_memory_derived_lists(
    broken_store_oracle: PassiveOracle,
) -> None:
    packet = broken_store_oracle.build_context_packet(
        focus_entity_ids=["gunnar"], location_id="hall",
    )
    assert packet.recent_observations == []
    assert packet.canonical_facts == {}
    assert packet.active_policies == []
    assert packet.open_contradiction_count == 0


def test_world_identity_fields_intact_on_degradation(
    broken_store_oracle: PassiveOracle,
) -> None:
    packet = broken_store_oracle.build_context_packet(
        focus_entity_ids=["gunnar"], location_id="hall",
    )
    assert packet.world_id == "degrade_world"
    assert [e.entity_id for e in packet.focus_entities] == ["gunnar"]
    assert packet.focus_entities[0].name == "Gunnar"
    assert packet.location_context is not None
    assert packet.location_context.location_id == "hall"
    assert "gunnar" in [e.entity_id for e in packet.present_entities]
    # The rendered block still exists so the prompt builder has something.
    assert "WORLD STATE" in packet.formatted_for_llm


def test_degradation_logs_single_warning(
    broken_store_oracle: PassiveOracle, caplog,
) -> None:
    with caplog.at_level(logging.WARNING, logger="wyrdforge.oracle.passive_oracle"):
        broken_store_oracle.build_context_packet(
            focus_entity_ids=["gunnar"], location_id="hall",
        )
    warnings = [
        r for r in caplog.records
        if r.levelno == logging.WARNING
        and r.name == "wyrdforge.oracle.passive_oracle"
    ]
    assert len(warnings) == 1
    assert "memory layer failed" in warnings[0].getMessage()


def test_degradation_also_covers_include_flags_off(
    broken_store_oracle: PassiveOracle,
) -> None:
    packet = broken_store_oracle.build_context_packet(
        focus_entity_ids=[],
        include_policies=False,
        include_observations=False,
    )
    assert isinstance(packet, WorldContextPacket)
    assert packet.recent_observations == []


# ---------------------------------------------------------------------------
# Healthy-path regression: the seam must not change normal behaviour
# ---------------------------------------------------------------------------

def test_healthy_store_still_populates_memory_content() -> None:
    oracle, store = _build_oracle()
    engine = WritebackEngine(store)
    engine.process_turn(
        user_input="hello",
        response_text="hi",
        facts=[{"fact_subject_id": "gunnar", "fact_key": "mood",
                "fact_value": "alert", "confidence": 0.9}],
    )
    packet = oracle.build_context_packet(
        focus_entity_ids=["gunnar"], location_id="hall",
    )
    assert len(packet.recent_observations) == 1
    assert "gunnar" in packet.canonical_facts
    facts = packet.canonical_facts["gunnar"]
    assert facts[0].fact_key == "mood"
    assert facts[0].fact_value == "alert"
