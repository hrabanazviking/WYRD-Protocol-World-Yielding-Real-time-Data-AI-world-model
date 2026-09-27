"""Tests for the self-correction engine — Track 7, Phase 2 + Phase 4.

Pins the roadmap's "constants in code with tests, not vibes": step sizes
are module constants, never magic numbers. Also pins the named
roadmap-arithmetic discrepancy: three 0.2-steps from 0.9 reach 0.3, and the
threshold is *strictly* below 0.3 — so uncertainty takes four contradictions
(0.9 -> 0.7 -> 0.5 -> 0.3 -> 0.1), not three.
"""
from __future__ import annotations

import tempfile

import pytest

import wyrdforge.services.self_correction as sc
from wyrdforge.services.self_correction import (
    CONFIDENCE_STEP_DOWN,
    CONFIDENCE_STEP_UP,
    UNCERTAINTY_THRESHOLD,
    SelfCorrectionService,
    contradict,
    format_confidence_history,
    format_correction,
    is_uncertain,
    reconfirm,
)


def _step_down_n(confidence: float, n: int):
    svc = SelfCorrectionService()
    hist: list[float] = []
    for _ in range(n):
        confidence, hist = svc.contradict(confidence, hist)
    return confidence, hist


# ---------------------------------------------------------------------------
# T7-P2: stepping down — the named roadmap-arithmetic case
# ---------------------------------------------------------------------------

def test_constants_are_the_roadmap_values():
    assert CONFIDENCE_STEP_DOWN == pytest.approx(0.2)
    assert CONFIDENCE_STEP_UP == pytest.approx(0.1)
    assert UNCERTAINTY_THRESHOLD == pytest.approx(0.3)


def test_contradict_steps_down_by_the_constant():
    new_conf, hist = contradict(0.9)
    assert new_conf == pytest.approx(0.9 - CONFIDENCE_STEP_DOWN)
    # history[0] is the starting confidence; later entries are post-step values
    assert hist[0] == pytest.approx(0.9)
    assert hist[-1] == pytest.approx(new_conf)


def test_four_contradictions_reach_uncertainty_not_three():
    """The pinned discrepancy: three steps from 0.9 reach 0.3 (still
    asserted — the threshold is strict); the fourth reaches uncertainty."""
    conf, hist = _step_down_n(0.9, 3)
    assert conf == pytest.approx(0.3)
    assert not is_uncertain(conf), "0.3 must still render asserted (strict < 0.3)"

    conf, hist = _step_down_n(0.9, 4)
    assert conf == pytest.approx(0.1)
    assert is_uncertain(conf)
    assert hist[0] == pytest.approx(0.9)
    assert hist[-1] == pytest.approx(0.1)


def test_contradict_floors_at_zero():
    conf, _ = contradict(0.1)
    assert conf == pytest.approx(0.0)
    conf, _ = contradict(0.0)
    assert conf == pytest.approx(0.0)


def test_uncertainty_threshold_is_strict():
    assert not is_uncertain(UNCERTAINTY_THRESHOLD)
    assert not is_uncertain(0.3)
    assert is_uncertain(0.3 - 1e-9)
    assert is_uncertain(0.0)


# ---------------------------------------------------------------------------
# T7-P2: stepping up — trust rebuilds slower than it breaks
# ---------------------------------------------------------------------------

def test_reconfirm_steps_up_by_the_constant():
    new_conf, hist = reconfirm(0.1)
    assert new_conf == pytest.approx(0.1 + CONFIDENCE_STEP_UP)
    assert hist[0] == pytest.approx(0.1)
    assert hist[-1] == pytest.approx(new_conf)


def test_reconfirm_climbs_slowly():
    conf, hist = 0.1, []
    for _ in range(2):
        conf, hist = reconfirm(conf, hist)
    assert conf == pytest.approx(0.3)


def test_reconfirm_caps_at_one():
    conf, _ = reconfirm(0.95)
    assert conf == pytest.approx(1.0)
    conf, _ = reconfirm(1.0)
    assert conf == pytest.approx(1.0)


def test_step_up_is_slower_than_step_down():
    assert CONFIDENCE_STEP_UP < CONFIDENCE_STEP_DOWN


# ---------------------------------------------------------------------------
# Purity: inputs are never mutated
# ---------------------------------------------------------------------------

def test_contradict_does_not_mutate_input_history():
    before = [0.9]
    contradict(0.9, before)
    assert before == [0.9]


def test_reconfirm_does_not_mutate_input_history():
    before = [0.1]
    reconfirm(0.1, before)
    assert before == [0.1]


# ---------------------------------------------------------------------------
# T7-P3: the announcement formatter carries all three facts
# ---------------------------------------------------------------------------

def test_format_correction_carries_all_three_facts():
    line = format_correction("the hall is empty", "Gunnar walked in", "the hall is occupied")
    assert "the hall is empty" in line
    assert "Gunnar walked in" in line
    assert "the hall is occupied" in line


def test_format_correction_names_the_change_of_mind():
    line = format_correction("a", "b", "c")
    assert "Correction" in line


# ---------------------------------------------------------------------------
# T7-P4: the honest limit is stated where the corrections happen
# ---------------------------------------------------------------------------

def test_module_docstring_states_the_honest_limit():
    doc = sc.__doc__ or ""
    assert "worker's account" in doc, "docstring must name the worker's account"
    assert "not an objective transcript" in doc, (
        "docstring must state the boundary: not an objective transcript"
    )


def test_module_docstring_names_the_arithmetic_discrepancy():
    doc = sc.__doc__ or ""
    assert "strictly" in doc and "0.3" in doc


# ---------------------------------------------------------------------------
# Oracle rendering — sub-0.3 facts render uncertain with history
# ---------------------------------------------------------------------------

from wyrdforge.ecs.world import World
from wyrdforge.ecs.yggdrasil import YggdrasilTree
from wyrdforge.ecs.components.identity import (
    DescriptionComponent,
    NameComponent,
    StatusComponent,
)
from wyrdforge.oracle import PassiveOracle
from wyrdforge.persistence.memory_store import PersistentMemoryStore
from wyrdforge.services.writeback_engine import WritebackEngine


def _build_world():
    world = World("test_world", "Test World")
    tree = YggdrasilTree(world)
    tree.create_zone(zone_id="midgard", name="Midgard")
    tree.create_region(region_id="fjordlands", name="Fjordlands", parent_zone_id="midgard")
    tree.create_location(location_id="hall", name="Great Hall", parent_region_id="fjordlands")
    world.create_entity(entity_id="gunnar", tags={"character"})
    world.add_component("gunnar", NameComponent(entity_id="gunnar", name="Gunnar Ironside"))
    world.add_component(
        "gunnar",
        DescriptionComponent(entity_id="gunnar", short_desc="Gunnar is here."),
    )
    world.add_component("gunnar", StatusComponent(entity_id="gunnar", state="idle"))
    tree.place_entity("gunnar", location_id="hall")
    return world, tree


def _packet_for_fact(confidence: float, history: list[float]):
    world, tree = _build_world()
    store = PersistentMemoryStore(tempfile.mktemp(suffix=".db"))
    engine = WritebackEngine(store)
    record = engine.write_canonical_fact(
        fact_subject_id="gunnar",
        fact_key="status",
        fact_value="alive",
        confidence=confidence,
    )
    # The writer of confidence history is SelfCorrectionService (module docstring);
    # the test writes it the same way the service would.
    record.truth.confidence_history = list(history)
    store.add(record)
    oracle = PassiveOracle(world, store, yggdrasil=tree)
    return oracle.build_context_packet(
        focus_entity_ids=["gunnar"],
        include_policies=False,
        include_observations=False,
    )


def test_asserted_fact_renders_as_today():
    packet = _packet_for_fact(0.9, [])
    assert "• status = alive (conf: 0.90)" in packet.formatted_for_llm
    assert "uncertain" not in packet.formatted_for_llm


def test_threshold_fact_still_renders_asserted():
    packet = _packet_for_fact(0.3, [])
    assert "• status = alive (conf: 0.30)" in packet.formatted_for_llm
    assert "uncertain" not in packet.formatted_for_llm


def test_stepped_down_fact_renders_uncertain_with_history():
    conf, hist = _step_down_n(0.9, 4)
    assert is_uncertain(conf)
    packet = _packet_for_fact(conf, hist)
    rendered = packet.formatted_for_llm
    assert "uncertain" in rendered
    chain = format_confidence_history(hist)
    assert f"was {chain}" in rendered
    # literal pin — the render must show the full chain, not just agree with
    # the module's own formatter (a broken formatter must fail this test)
    assert "was 0.9 -> 0.7 -> 0.5 -> 0.3 -> 0.1" in rendered
    # the flat assertion format must be gone for this fact
    assert "• status = alive (conf: 0.10)" not in rendered


def test_fact_summary_carries_uncertainty_fields():
    packet = _packet_for_fact(0.1, [0.9, 0.7, 0.5, 0.3, 0.1])
    facts = packet.canonical_facts["gunnar"]
    assert len(facts) == 1
    assert facts[0].uncertain is True
    assert facts[0].confidence_history == [0.9, 0.7, 0.5, 0.3, 0.1]

    packet = _packet_for_fact(0.9, [])
    facts = packet.canonical_facts["gunnar"]
    assert facts[0].uncertain is False
