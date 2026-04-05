"""Tests for RunicEngine and runic ECS components — Phase 7."""
from __future__ import annotations

import pytest

from wyrdforge.ecs.components.runic import (
    AncestralResonanceComponent,
    HamingjaComponent,
    RunicChargeComponent,
)
from wyrdforge.ecs.world import World
from wyrdforge.services.runic_engine import RunicEngine, RunicReport


# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------

def _world_with_entity(entity_id: str = "sigrid") -> tuple[World, RunicEngine]:
    world = World("runic_world", "Runic World")
    world.create_entity(entity_id=entity_id, tags={"character"})
    engine = RunicEngine(world)
    return world, engine


# ---------------------------------------------------------------------------
# HamingjaComponent — component basics
# ---------------------------------------------------------------------------

def test_hamingja_default_score_is_zero() -> None:
    comp = HamingjaComponent(entity_id="sigrid")
    assert comp.score == 0.0


def test_hamingja_score_clamped_high() -> None:
    comp = HamingjaComponent(entity_id="sigrid", score=1.0)
    assert comp.score == 1.0


def test_hamingja_score_clamped_low() -> None:
    comp = HamingjaComponent(entity_id="sigrid", score=-1.0)
    assert comp.score == -1.0


def test_hamingja_invalid_score_raises() -> None:
    with pytest.raises(Exception):
        HamingjaComponent(entity_id="sigrid", score=2.0)


# ---------------------------------------------------------------------------
# RunicChargeComponent — component basics
# ---------------------------------------------------------------------------

def test_runic_charge_default_charges_empty() -> None:
    comp = RunicChargeComponent(entity_id="sigrid")
    assert comp.charges == {}


def test_runic_charge_get_charge_missing_returns_zero() -> None:
    comp = RunicChargeComponent(entity_id="sigrid")
    assert comp.get_charge("fehu") == 0.0


def test_runic_charge_total_charge_empty_is_zero() -> None:
    comp = RunicChargeComponent(entity_id="sigrid")
    assert comp.total_charge() == 0.0


def test_runic_charge_total_charge_sums_values() -> None:
    comp = RunicChargeComponent(entity_id="sigrid", charges={"fehu": 0.4, "uruz": 0.3})
    assert abs(comp.total_charge() - 0.7) < 1e-9


# ---------------------------------------------------------------------------
# AncestralResonanceComponent — component basics
# ---------------------------------------------------------------------------

def test_ancestral_resonance_default_score_is_zero() -> None:
    comp = AncestralResonanceComponent(entity_id="sigrid")
    assert comp.score == 0.0


def test_ancestral_resonance_invalid_score_raises() -> None:
    with pytest.raises(Exception):
        AncestralResonanceComponent(entity_id="sigrid", score=1.5)


# ---------------------------------------------------------------------------
# RunicEngine.invoke_rune
# ---------------------------------------------------------------------------

def test_invoke_rune_creates_runic_charge_component() -> None:
    world, engine = _world_with_entity()
    engine.invoke_rune("sigrid", "fehu", strength=0.5)
    comp = world.get_component("sigrid", "runic_charge")
    assert comp is not None


def test_invoke_rune_sets_charge() -> None:
    world, engine = _world_with_entity()
    engine.invoke_rune("sigrid", "fehu", strength=0.6)
    comp = world.get_component("sigrid", "runic_charge")
    assert abs(comp.get_charge("fehu") - 0.6) < 1e-9


def test_invoke_rune_accumulates_charge() -> None:
    world, engine = _world_with_entity()
    engine.invoke_rune("sigrid", "fehu", strength=0.4)
    engine.invoke_rune("sigrid", "fehu", strength=0.3)
    comp = world.get_component("sigrid", "runic_charge")
    assert abs(comp.get_charge("fehu") - 0.7) < 1e-9


def test_invoke_rune_clamps_charge_at_one() -> None:
    world, engine = _world_with_entity()
    engine.invoke_rune("sigrid", "fehu", strength=0.8)
    engine.invoke_rune("sigrid", "fehu", strength=0.8)
    comp = world.get_component("sigrid", "runic_charge")
    assert comp.get_charge("fehu") == 1.0


def test_invoke_rune_sets_dominant_rune() -> None:
    world, engine = _world_with_entity()
    engine.invoke_rune("sigrid", "fehu", strength=0.8)
    engine.invoke_rune("sigrid", "uruz", strength=0.3)
    comp = world.get_component("sigrid", "runic_charge")
    assert comp.dominant_rune == "fehu"


def test_invoke_rune_also_boosts_hamingja() -> None:
    world, engine = _world_with_entity()
    engine.invoke_rune("sigrid", "fehu", strength=0.5)
    comp = world.get_component("sigrid", "hamingja")
    assert comp is not None
    assert comp.score > 0.0


# ---------------------------------------------------------------------------
# RunicEngine.apply_hamingja_event
# ---------------------------------------------------------------------------

def test_apply_hamingja_creates_component() -> None:
    world, engine = _world_with_entity()
    engine.apply_hamingja_event("sigrid", delta=0.3)
    comp = world.get_component("sigrid", "hamingja")
    assert comp is not None


def test_apply_hamingja_positive_delta() -> None:
    world, engine = _world_with_entity()
    engine.apply_hamingja_event("sigrid", delta=0.4)
    comp = world.get_component("sigrid", "hamingja")
    assert abs(comp.score - 0.4) < 1e-9


def test_apply_hamingja_negative_delta() -> None:
    world, engine = _world_with_entity()
    engine.apply_hamingja_event("sigrid", delta=-0.5)
    comp = world.get_component("sigrid", "hamingja")
    assert abs(comp.score - (-0.5)) < 1e-9


def test_apply_hamingja_clamps_at_positive_one() -> None:
    world, engine = _world_with_entity()
    engine.apply_hamingja_event("sigrid", delta=0.8)
    engine.apply_hamingja_event("sigrid", delta=0.8)
    comp = world.get_component("sigrid", "hamingja")
    assert comp.score == 1.0


def test_apply_hamingja_tracks_peak() -> None:
    world, engine = _world_with_entity()
    engine.apply_hamingja_event("sigrid", delta=0.7)
    engine.apply_hamingja_event("sigrid", delta=-0.9)
    comp = world.get_component("sigrid", "hamingja")
    assert abs(comp.peak - 0.7) < 1e-9


def test_apply_hamingja_stores_event_id() -> None:
    world, engine = _world_with_entity()
    engine.apply_hamingja_event("sigrid", delta=0.2, event_id="evt-001")
    comp = world.get_component("sigrid", "hamingja")
    assert comp.last_event_id == "evt-001"


# ---------------------------------------------------------------------------
# RunicEngine.reinforce_resonance
# ---------------------------------------------------------------------------

def test_reinforce_resonance_creates_component() -> None:
    world, engine = _world_with_entity()
    engine.reinforce_resonance("sigrid", boost=0.3)
    comp = world.get_component("sigrid", "ancestral_resonance")
    assert comp is not None


def test_reinforce_resonance_increases_score() -> None:
    world, engine = _world_with_entity()
    engine.reinforce_resonance("sigrid", boost=0.4)
    comp = world.get_component("sigrid", "ancestral_resonance")
    assert abs(comp.score - 0.4) < 1e-9


def test_reinforce_resonance_clamps_at_one() -> None:
    world, engine = _world_with_entity()
    engine.reinforce_resonance("sigrid", boost=0.7)
    engine.reinforce_resonance("sigrid", boost=0.7)
    comp = world.get_component("sigrid", "ancestral_resonance")
    assert comp.score == 1.0


def test_reinforce_resonance_adds_fragment() -> None:
    world, engine = _world_with_entity()
    engine.reinforce_resonance("sigrid", boost=0.1, fragment="Freya's blessing")
    comp = world.get_component("sigrid", "ancestral_resonance")
    assert "Freya's blessing" in comp.memory_fragments


def test_reinforce_resonance_no_duplicate_fragments() -> None:
    world, engine = _world_with_entity()
    engine.reinforce_resonance("sigrid", boost=0.1, fragment="same fragment")
    engine.reinforce_resonance("sigrid", boost=0.1, fragment="same fragment")
    comp = world.get_component("sigrid", "ancestral_resonance")
    assert comp.memory_fragments.count("same fragment") == 1


# ---------------------------------------------------------------------------
# RunicEngine.add_lineage
# ---------------------------------------------------------------------------

def test_add_lineage_creates_component() -> None:
    world, engine = _world_with_entity()
    engine.add_lineage("sigrid", "grandmother")
    comp = world.get_component("sigrid", "ancestral_resonance")
    assert comp is not None


def test_add_lineage_stores_ancestor() -> None:
    world, engine = _world_with_entity()
    engine.add_lineage("sigrid", "grandmother")
    comp = world.get_component("sigrid", "ancestral_resonance")
    assert "grandmother" in comp.lineage_ids


def test_add_lineage_no_duplicates() -> None:
    world, engine = _world_with_entity()
    engine.add_lineage("sigrid", "grandmother")
    engine.add_lineage("sigrid", "grandmother")
    comp = world.get_component("sigrid", "ancestral_resonance")
    assert comp.lineage_ids.count("grandmother") == 1


# ---------------------------------------------------------------------------
# RunicEngine.tick
# ---------------------------------------------------------------------------

def test_tick_decays_runic_charge() -> None:
    world, engine = _world_with_entity()
    engine.invoke_rune("sigrid", "fehu", strength=1.0)
    engine.tick()
    comp = world.get_component("sigrid", "runic_charge")
    assert comp.get_charge("fehu") < 1.0


def test_tick_drifts_positive_hamingja_toward_zero() -> None:
    world, engine = _world_with_entity()
    engine.apply_hamingja_event("sigrid", delta=0.5)
    engine.tick()
    comp = world.get_component("sigrid", "hamingja")
    assert comp.score < 0.5


def test_tick_drifts_negative_hamingja_toward_zero() -> None:
    world, engine = _world_with_entity()
    engine.apply_hamingja_event("sigrid", delta=-0.5)
    engine.tick()
    comp = world.get_component("sigrid", "hamingja")
    assert comp.score > -0.5


def test_tick_restricted_to_entity_list() -> None:
    world = World("runic_world", "Runic World")
    world.create_entity(entity_id="a")
    world.create_entity(entity_id="b")
    engine = RunicEngine(world)
    engine.invoke_rune("a", "fehu", strength=1.0)
    engine.invoke_rune("b", "fehu", strength=1.0)
    engine.tick(entity_ids=["a"])
    comp_a = world.get_component("a", "runic_charge")
    comp_b = world.get_component("b", "runic_charge")
    assert comp_a.get_charge("fehu") < 1.0
    assert comp_b.get_charge("fehu") == 1.0


# ---------------------------------------------------------------------------
# RunicEngine.report
# ---------------------------------------------------------------------------

def test_report_no_components_returns_nones() -> None:
    world, engine = _world_with_entity()
    report = engine.report("sigrid")
    assert report.hamingja_score is None
    assert report.dominant_rune is None
    assert report.total_charge == 0.0
    assert report.resonance_score == 0.0


def test_report_after_invocation() -> None:
    world, engine = _world_with_entity()
    engine.invoke_rune("sigrid", "fehu", strength=0.7)
    report = engine.report("sigrid")
    assert report.dominant_rune == "fehu"
    assert report.total_charge > 0.0
    assert report.hamingja_score is not None and report.hamingja_score > 0.0


def test_report_rune_charges_dict() -> None:
    world, engine = _world_with_entity()
    engine.invoke_rune("sigrid", "fehu", strength=0.5)
    engine.invoke_rune("sigrid", "uruz", strength=0.3)
    report = engine.report("sigrid")
    assert "fehu" in report.rune_charges
    assert "uruz" in report.rune_charges


def test_report_entity_id_correct() -> None:
    world, engine = _world_with_entity("gunnar")
    report = engine.report("gunnar")
    assert report.entity_id == "gunnar"
