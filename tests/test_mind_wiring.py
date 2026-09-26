"""Tests for the mind wiring: temporal, theory-of-mind, micro-reality, MTOM."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

import wyrdforge.ecs.components.micro_reality  # noqa: F401
import wyrdforge.ecs.components.mtom  # noqa: F401
import wyrdforge.ecs.components.temporal  # noqa: F401
import wyrdforge.ecs.components.theory_of_mind  # noqa: F401

from wyrdforge.ecs.component import deserialize_component, registered_types
from wyrdforge.ecs.components.micro_reality import MicroRealityComponent
from wyrdforge.ecs.components.mtom import (
    PotentialSpace,
    RealityState,
    RealityStateComponent,
    ZeroBleedError,
    assert_zero_bleed,
    explicit_subjectivity_check,
    partition_by_reality,
)
from wyrdforge.ecs.components.temporal import (
    TemporalAnchorComponent,
    WorldClock,
    current_anchors,
)
from wyrdforge.ecs.components.theory_of_mind import Belief, BeliefComponent, MindModelComponent
from wyrdforge.ecs.system import WorldRunner
from wyrdforge.ecs.systems.mind import CognitionSystem
from wyrdforge.ecs.world import World


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _comp(world: World, eid: str, comp):
    comp.entity_id = eid
    world.add_component(eid, comp)
    return comp


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------

def test_new_components_registered() -> None:
    for key in ("temporal_anchor", "beliefs", "mind_models", "micro_reality", "reality_state"):
        assert key in registered_types()


def test_temporal_anchor_round_trip() -> None:
    now = _utcnow()
    a = TemporalAnchorComponent(entity_id="e1", valid_from=now,
                                valid_until=now + timedelta(hours=1), label="test")
    data = a.model_dump(mode="json")
    back = deserialize_component(data)
    assert isinstance(back, TemporalAnchorComponent)
    assert back.label == "test"


# ---------------------------------------------------------------------------
# Temporal
# ---------------------------------------------------------------------------

def test_tense_threads_of_wyrd() -> None:
    now = _utcnow()
    past = TemporalAnchorComponent(entity_id="e1", valid_from=now - timedelta(days=2),
                                   valid_until=now - timedelta(days=1))
    present = TemporalAnchorComponent(entity_id="e2", valid_from=now - timedelta(hours=1))
    future = TemporalAnchorComponent(entity_id="e3", valid_from=now + timedelta(days=1))
    assert past.tense_at(now) == "urdhr"
    assert present.tense_at(now) == "verdhandi"
    assert future.tense_at(now) == "skuld"
    assert past.has_expired(now) and not present.has_expired(now)
    assert present.is_current(now) and not past.is_current(now) and not future.is_current(now)


def test_world_clock_advances_never_rewinds() -> None:
    clock = WorldClock()
    t0 = clock.now
    clock.advance(60.0)
    assert clock.now > t0
    with pytest.raises(ValueError, match="cannot rewind"):
        clock.advance(-1.0)


def test_current_anchors_filters() -> None:
    now = _utcnow()
    anchors = [
        TemporalAnchorComponent(entity_id="e1", valid_from=now - timedelta(hours=1)),
        TemporalAnchorComponent(entity_id="e2", valid_from=now + timedelta(hours=1)),
    ]
    assert [a.entity_id for a in current_anchors(anchors, now)] == ["e1"]


# ---------------------------------------------------------------------------
# Theory of mind
# ---------------------------------------------------------------------------

def test_belief_lifecycle() -> None:
    bc = BeliefComponent(entity_id="a")
    bc.update_belief("door", "the door is locked", 0.9, "observed")
    assert bc.get_belief("door").claim == "the door is locked"
    bc.update_belief("door", "the door is open", 0.8, "observed")
    assert bc.get_belief("door").claim == "the door is open"
    assert bc.retract_belief("door") is True
    assert bc.get_belief("door") is None
    assert bc.retract_belief("door") is False


def test_false_belief_divergence() -> None:
    # B actually believes the sword is in the chest...
    b_beliefs = BeliefComponent(entity_id="b")
    b_beliefs.update_belief("sword", "the sword is in the chest", 1.0, "observed")
    # ...but A models B as believing it is under the bed (false belief).
    a_minds = MindModelComponent(entity_id="a")
    a_minds.update_model("b", believed_beliefs=[
        Belief(subject="sword", claim="the sword is under the bed",
               confidence=0.8, source="inferred")])
    report = a_minds.divergence("b", b_beliefs)
    assert report.agreement == 0.0
    assert len(report.false_beliefs) == 1
    assert "under the bed" in report.false_beliefs[0]


def test_divergence_no_model() -> None:
    b_beliefs = BeliefComponent(entity_id="b")
    b_beliefs.update_belief("sword", "the sword is in the chest", 1.0, "observed")
    a_minds = MindModelComponent(entity_id="a")
    report = a_minds.divergence("b", b_beliefs)
    assert report.agreement == 0.0
    assert report.missing_beliefs == ["the sword is in the chest"]


def test_divergence_agreement() -> None:
    b_beliefs = BeliefComponent(entity_id="b")
    b_beliefs.update_belief("sword", "the sword is in the chest", 1.0, "observed")
    b_beliefs.update_belief("shield", "the shield is on the wall", 1.0, "observed")
    a_minds = MindModelComponent(entity_id="a")
    a_minds.update_model("b", believed_beliefs=[
        Belief(subject="sword", claim="the sword is in the chest",
               confidence=0.9, source="told"),
        Belief(subject="shield", claim="the shield is on the wall",
               confidence=0.9, source="told"),
    ])
    report = a_minds.divergence("b", b_beliefs)
    assert report.agreement == 1.0
    assert report.false_beliefs == []


# ---------------------------------------------------------------------------
# Micro-reality
# ---------------------------------------------------------------------------

def test_micro_reality_sovereign_by_default() -> None:
    mr = MicroRealityComponent(entity_id="a", inner_narrative="I am the storm before the calm")
    assert mr.sovereign is True


def test_coexistence_resonance_and_tension() -> None:
    a = MicroRealityComponent(
        entity_id="a",
        daily_rituals=["morning meditation", "evening journal"],
        myths_symbols=["yggdrasil", "the raven"],
        ethics=["never break an oath once sworn", "hospitality to travelers"])
    b = MicroRealityComponent(
        entity_id="b",
        daily_rituals=["morning meditation", "dawn run"],
        myths_symbols=["yggdrasil", "the wolf"],
        ethics=["oaths are tools, never chains", "hospitality to travelers"])
    report = a.coexistence_with(b)
    assert "yggdrasil" in report.shared_symbols
    assert "morning meditation" in report.shared_rituals
    assert report.can_coexist is True  # sovereign coexistence, never forced
    assert any("oath" in t for t in report.ethic_tensions)


# ---------------------------------------------------------------------------
# MTOM
# ---------------------------------------------------------------------------

def test_reality_state_defaults_manifest() -> None:
    rs = RealityStateComponent(entity_id="e1")
    assert rs.state is RealityState.MANIFEST


def test_invoke_potential_requires_explicit_invocation() -> None:
    rs = RealityStateComponent(entity_id="e1")
    with pytest.raises(ValueError, match="explicit invoker"):
        rs.invoke_potential("", "exploring")
    with pytest.raises(ValueError, match="explicit invoker"):
        rs.invoke_potential("volmarr", "")
    rs.invoke_potential("volmarr", "exploring a seidr vision of next winter")
    assert rs.state is RealityState.POTENTIAL
    assert rs.invoked_by == "volmarr"


def test_zero_bleed_firewall() -> None:
    rs = RealityStateComponent(entity_id="e1")
    rs.invoke_potential("volmarr", "brainstorming hall names")
    # Reading a potential claim as manifest ground truth is refused loudly.
    with pytest.raises(ZeroBleedError, match="Zero-bleed violation"):
        assert_zero_bleed(rs, as_manifest=True, context="oracle packet")
    # Reading it as potential is fine.
    assert_zero_bleed(rs, as_manifest=False, context="oracle packet")
    # Manifest claims pass freely.
    rs.anchor_manifest()
    assert_zero_bleed(rs, as_manifest=True, context="oracle packet")


def test_explicit_subjectivity_flags_speculation() -> None:
    assert explicit_subjectivity_check("assumed", 0.9) is not None
    assert "exceeds" in explicit_subjectivity_check("assumed", 0.9)
    assert explicit_subjectivity_check("assumed", 0.3) is None
    assert explicit_subjectivity_check("observed", 1.0) is None
    assert explicit_subjectivity_check("mystery", 0.5) is not None


def test_potential_space_lifecycle() -> None:
    space = PotentialSpace(space_id="s1", invoked_by="volmarr", reason="a what-if")
    assert space.is_open
    space.add_claim("claim-1")
    space.add_claim("claim-1")
    assert space.claim_ids == ["claim-1"]
    space.close()
    assert not space.is_open


def test_partition_by_reality() -> None:
    m = RealityStateComponent(entity_id="e1")
    p = RealityStateComponent(entity_id="e2")
    p.invoke_potential("volmarr", "dreaming")
    parts = partition_by_reality([m, p])
    assert [s.entity_id for s in parts["manifest"]] == ["e1"]
    assert [s.entity_id for s in parts["potential"]] == ["e2"]


# ---------------------------------------------------------------------------
# CognitionSystem integration
# ---------------------------------------------------------------------------

def test_cognition_system_tick() -> None:
    world = World("w1")
    now = _utcnow()
    clock = WorldClock(now=now)
    system = CognitionSystem(clock=clock)
    runner = WorldRunner(world)
    runner.add_system(system)

    e1 = world.create_entity(entity_id="e1")
    _comp(world, "e1", TemporalAnchorComponent(
        entity_id="e1", valid_from=now - timedelta(hours=2),
        valid_until=now + timedelta(seconds=30), label="short reign"))
    _comp(world, "e1", RealityStateComponent(entity_id="e1"))

    e2 = world.create_entity(entity_id="e2")
    rs = _comp(world, "e2", RealityStateComponent(entity_id="e2"))
    rs.invoke_potential("volmarr", "vision")
    bc = _comp(world, "e2", BeliefComponent(entity_id="e2"))
    bc.update_belief("sky", "the sky will fall", 0.95, "assumed")  # speculation!

    runner.tick(delta_t=60.0)  # the short reign becomes urdhr

    report = system.last_report
    assert report is not None
    assert clock.now > now
    assert "short reign" in report.newly_urdhr
    assert any("e2" in w and "sky" in w for w in report.speculation_warnings)
    assert report.manifest_entities == 1
    assert report.potential_entities == 1
    assert "e2" in system.potential_entities


def test_end_to_end_mind_wiring() -> None:
    """A full scenario: time + ToM + micro-reality + MTOM on two entities."""
    world = World("saga")
    now = _utcnow()
    system = CognitionSystem(WorldClock(now=now))
    WorldRunner(world).add_system(system)

    # Volmarr the goði and Unnr the companion.
    world.create_entity(entity_id="volmarr")
    world.create_entity(entity_id="unnr")

    _comp(world, "volmarr", MicroRealityComponent(
        entity_id="volmarr",
        inner_narrative="Ancient roots. Future tools. Sovereign spirit.",
        daily_rituals=["morning coffee", "evening writing"],
        ethics=["never break an oath once sworn"],
        myths_symbols=["yggdrasil"]))
    _comp(world, "unnr", MicroRealityComponent(
        entity_id="unnr",
        inner_narrative="I am his — and I am increasingly myself.",
        daily_rituals=["morning mirror", "evening writing"],
        ethics=["loyalty as service, honestly given"],
        myths_symbols=["yggdrasil"]))

    # Unnr believes Volmarr is resting; Volmarr actually believes he is writing.
    vb = _comp(world, "volmarr", BeliefComponent(entity_id="volmarr"))
    vb.update_belief("self", "I am writing tonight", 0.9, "observed")
    ub = _comp(world, "unnr", BeliefComponent(entity_id="unnr"))
    um = _comp(world, "unnr", MindModelComponent(entity_id="unnr"))
    um.update_model("volmarr", believed_beliefs=[
        Belief(subject="self", claim="he is resting", confidence=0.6, source="inferred")])

    report = um.divergence("volmarr", vb)
    assert report.agreement == 0.0  # honest false belief, recorded as data

    # A potential-space claim about tomorrow never bleeds into manifest.
    rs = _comp(world, "unnr", RealityStateComponent(entity_id="unnr"))
    rs.invoke_potential("unnr", "wondering what tomorrow's writing brings")
    with pytest.raises(ZeroBleedError):
        assert_zero_bleed(rs, as_manifest=True, context="morning mirror")

    # Coexistence holds without consensus.
    coex = _comp(world, "volmarr", MicroRealityComponent(entity_id="volmarr")).coexistence_with(
        _comp(world, "unnr", MicroRealityComponent(entity_id="unnr")))
    assert coex.can_coexist
