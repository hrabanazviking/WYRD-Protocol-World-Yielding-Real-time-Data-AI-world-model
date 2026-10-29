"""Phase D1 — combat awareness core pinning tests.

Design under test (roadmap §6, ``ecs/components/combat.py`` +
``services/combat_engine.py`` + the Oracle's D1 queries):

* WYRD owns the remembered fight; the host owns resolution. Nothing
  here rolls dice — damage amounts are host-resolved and land only
  through the existing ``HealthComponent.take_damage``.
* CombatantComponent composes with Health/Faction; Engagement is an
  ENTITY (participants + B3 PositionComponent anchor + lifecycle
  skirmish → engaged → broken → ended); threat is PER-OBSERVER
  belief state on the MTOM machinery, so divergence is data;
  effects are entities riding TemporalAnchor validity windows and
  announce ``combat.effect_expired`` exactly once when they lapse;
  tempo is one model on two clocks (deterministic initiative /
  wall-mode cooldown timestamps); range bands are DERIVED from B3
  distances, never stored.
"""
from __future__ import annotations

import tempfile
from datetime import datetime, timedelta, timezone

import pytest

import wyrdforge.ecs.components.character  # noqa: F401  (registry)
import wyrdforge.ecs.components.combat  # noqa: F401  (registry)
import wyrdforge.ecs.components.spatial  # noqa: F401  (registry)
import wyrdforge.ecs.components.temporal  # noqa: F401  (registry)
from wyrdforge.ecs.components.character import FactionComponent, HealthComponent
from wyrdforge.ecs.components.combat import (
    CombatantComponent,
    EffectComponent,
    EngagementComponent,
    ThreatComponent,
    range_band,
)
from wyrdforge.ecs.components.temporal import TemporalAnchorComponent, WorldClock
from wyrdforge.ecs.world import World
from wyrdforge.oracle import PassiveOracle
from wyrdforge.persistence.memory_store import PersistentMemoryStore
from wyrdforge.persistence.world_store import WorldStore
from wyrdforge.runtime.events import EventBus
from wyrdforge.services.combat_engine import CombatEngine

UTC = timezone.utc
T0 = datetime(2026, 10, 29, 12, 0, 0, tzinfo=UTC)
W0 = datetime(2026, 10, 29, 8, 0, 0, tzinfo=UTC)


def _oracle(world: World) -> PassiveOracle:
    store = PersistentMemoryStore(tempfile.mktemp(suffix=".db"))
    return PassiveOracle(world, store)


def _fighter(world: World, eid: str, *, hp: float = 100.0, initiative: int = 0,
             faction: str = "", pos: tuple[float, float, float] | None = None) -> None:
    world.create_entity(entity_id=eid)
    world.add_component(eid, HealthComponent(entity_id=eid, hp=hp, max_hp=hp))
    world.add_component(eid, CombatantComponent(
        entity_id=eid, initiative=initiative, faction_id=faction))
    if faction:
        world.add_component(eid, FactionComponent(entity_id=eid, faction_id=faction))
    if pos is not None:
        world.set_position(eid, *pos)


def _bus_with_topics() -> tuple[EventBus, list]:
    bus = EventBus()
    seen: list = []
    engine_topics = [
        "combat.engagement_started", "combat.damage_applied",
        "combat.effect_applied", "combat.effect_expired",
        "combat.engagement_ended",
    ]
    for topic in engine_topics:
        bus.register_topic(topic)
        bus.subscribe(topic, seen.append)
    return bus, seen


# ---------------------------------------------------------------------------
# CombatantComponent
# ---------------------------------------------------------------------------

class TestCombatant:
    def test_defaults_and_composition_with_health_and_faction(self):
        world = World("w")
        _fighter(world, "hero", faction="wolves")
        comp = world.get_component("hero", "combatant")
        assert isinstance(comp, CombatantComponent)
        assert comp.stance == "idle" and comp.readiness == 1.0
        assert comp.faction_id == "wolves"
        # Composition, not replacement: health and faction stay their own.
        assert isinstance(world.get_component("hero", "health"), HealthComponent)
        assert isinstance(world.get_component("hero", "faction"), FactionComponent)

    def test_stance_transitions(self):
        comp = CombatantComponent(entity_id="a")
        comp.engage("eng-1")
        assert comp.stance == "engaged" and comp.engagement_id == "eng-1"
        comp.withdraw()
        assert comp.stance == "withdrawing"
        comp.leave_engagement()
        assert comp.stance == "idle" and comp.engagement_id is None
        comp.mark_down()
        assert comp.is_down and comp.stance == "down"

    def test_cooldown_readiness(self):
        comp = CombatantComponent(entity_id="a")
        assert comp.is_ready_at(T0)
        until = comp.begin_cooldown(30.0, now=T0)
        assert until == T0 + timedelta(seconds=30)
        assert comp.last_acted_at == T0
        assert not comp.is_ready_at(T0 + timedelta(seconds=29))
        assert comp.is_ready_at(T0 + timedelta(seconds=30))
        with pytest.raises(ValueError):
            comp.begin_cooldown(-1.0, now=T0)
        comp.clear_cooldown()
        assert comp.is_ready_at(T0)
        comp.mark_down()
        assert not comp.is_ready_at(T0 + timedelta(days=1))  # down never ready


# ---------------------------------------------------------------------------
# Engagement lifecycle
# ---------------------------------------------------------------------------

class TestEngagementLifecycle:
    def test_full_lifecycle_and_terminal_ended(self):
        comp = EngagementComponent(entity_id="e", participant_ids=["a", "b"])
        assert comp.state == "skirmish" and comp.is_live
        comp.transition_to("engaged")
        comp.transition_to("broken")
        comp.transition_to("ended", at=T0)
        assert comp.state == "ended" and not comp.is_live and comp.ended_at == T0
        with pytest.raises(ValueError):
            comp.transition_to("engaged")

    def test_invalid_transitions_raise(self):
        # skirmish -> broken is legal; broken -> engaged is not a
        # resurrection path; ended is terminal for moves and joins.
        comp = EngagementComponent(entity_id="e")
        comp.transition_to("broken")
        with pytest.raises(ValueError):
            comp.transition_to("engaged")
        ended = EngagementComponent(entity_id="e2")
        ended.transition_to("ended", at=T0)
        with pytest.raises(ValueError):
            ended.transition_to("skirmish")
        with pytest.raises(ValueError):
            ended.add_participant("x")

    def test_engine_start_join_leave_end(self):
        bus, seen = _bus_with_topics()
        world = World("w", bus=bus)
        _fighter(world, "a")
        _fighter(world, "b")
        _fighter(world, "c")
        engine = CombatEngine(world, bus=bus)
        eid = engine.start_engagement(["a", "b"], label="ford ambush", at=T0)
        comp = world.get_component(eid, "engagement")
        assert isinstance(comp, EngagementComponent)
        assert comp.participant_ids == ["a", "b"] and comp.state == "skirmish"
        assert world.get_component("a", "combatant").engagement_id == eid
        assert world.get_component("a", "combatant").stance == "engaged"
        engine.join_engagement(eid, "c")
        assert comp.participant_ids == ["a", "b", "c"]
        assert engine.leave_engagement(eid, "c") is True
        assert world.get_component("c", "combatant").engagement_id is None
        engine.transition_engagement(eid, "engaged")
        engine.end_engagement(eid, at=T0 + timedelta(minutes=5))
        assert comp.state == "ended"
        assert world.get_component("a", "combatant").engagement_id is None
        topics = [env.topic for env in seen]
        assert topics[0] == "combat.engagement_started"
        assert topics[-1] == "combat.engagement_ended"
        started = seen[0].payload
        assert started["engagement_id"] == eid and started["participant_ids"] == ["a", "b"]

    def test_engagement_spatial_anchor_from_anchor_entity(self):
        world = World("w")
        _fighter(world, "a", pos=(10.0, 0, 0))
        world.create_entity(entity_id="ford")
        world.set_position("ford", 7.0, 8.0, 0.0)
        engine = CombatEngine(world)
        eid = engine.start_engagement(["a"], anchor_entity_id="ford")
        anchor = world.get_position(eid)
        assert anchor is not None and anchor.position == (7.0, 8.0, 0.0)
        oracle = _oracle(world)
        result = oracle.get_engagement("a")
        assert result is not None and result.engagement_id == eid
        assert result.anchor_entity_id == "ford" and result.state == "skirmish"
        # Asking by the engagement's own id answers too; strangers get None.
        assert oracle.get_engagement(eid).engagement_id == eid
        assert oracle.get_engagement("nobody") is None
        engine.end_engagement(eid)
        assert oracle.get_engagement("a") is None  # ended is not live for participants


# ---------------------------------------------------------------------------
# Threat as perceived state — divergence is representable
# ---------------------------------------------------------------------------

class TestThreatBeliefs:
    def test_per_observer_divergence(self):
        world = World("w")
        for eid in ("lookout", "veteran", "wolf"):
            world.create_entity(entity_id=eid)
        lookout = ThreatComponent(entity_id="lookout")
        lookout.assess("wolf", 0.9, basis_event_ids=["evt-growl"], source="observed", confidence=0.8, at=T0)
        veteran = ThreatComponent(entity_id="veteran")
        veteran.assess("wolf", 0.2, basis_event_ids=["evt-old-scar"], source="inferred", confidence=0.6, at=T0)
        world.add_component("lookout", lookout)
        world.add_component("veteran", veteran)

        # Same target, two truths — neither is "the" threat level.
        assert lookout.level_for("wolf") == 0.9
        assert veteran.level_for("wolf") == 0.2
        assert lookout.divergence_from(veteran) == {"wolf": (0.9, 0.2)}
        # The lookout fears the WRONG enemy is representable: a high
        # assessment of a harmless target beside a low one of the wolf.
        lookout.assess("veteran", 0.95, source="assumed", confidence=0.3, at=T0)
        div = lookout.divergence_from(veteran)
        assert div["veteran"] == (0.95, None)

        oracle = _oracle(world)
        threats = oracle.threats_to("wolf")
        assert [(t.observer_id, t.level) for t in threats] == [("lookout", 0.9), ("veteran", 0.2)]
        assert threats[0].basis_event_ids == ["evt-growl"] and threats[0].source == "observed"
        mine = oracle.threats_perceived_by("lookout")
        assert [t.target_id for t in mine] == ["veteran", "wolf"]  # most feared first
        assert oracle.threats_to("unassessed") == []
        assert lookout.level_for("unassessed") is None  # never considered != harmless

    def test_assessment_projects_to_belief_with_source_warrant(self):
        comp = ThreatComponent(entity_id="a")
        assessment = comp.assess("b", 0.7, source="told", confidence=0.9, at=T0)
        belief = assessment.to_belief()
        assert belief.subject == "b" and belief.source == "told"
        assert belief.confidence == 0.9 and "0.70" in belief.claim
        assert comp.retract("b") is True and comp.level_for("b") is None


# ---------------------------------------------------------------------------
# Effects on temporal anchors + expiry event
# ---------------------------------------------------------------------------

class TestEffects:
    def test_apply_and_expire_emits_exactly_once(self):
        bus, seen = _bus_with_topics()
        world = World("w", bus=bus)
        _fighter(world, "a")
        engine = CombatEngine(world, bus=bus)
        effect_id = engine.apply_effect(
            "a", name="nightshade", kind="poison", source_id="witch",
            magnitude=3.0, duration_seconds=60.0, at=T0)
        comp = world.get_component(effect_id, "effect")
        assert isinstance(comp, EffectComponent)
        assert comp.expires_at == T0 + timedelta(seconds=60)
        anchor = world.get_component(effect_id, "temporal_anchor")
        assert isinstance(anchor, TemporalAnchorComponent)
        assert anchor.valid_from == T0 and anchor.valid_until == comp.expires_at
        assert [c.name for c in engine.active_effects_on("a", T0 + timedelta(seconds=30))] == ["nightshade"]

        # Not yet expired: tick before the window closes emits nothing.
        assert engine.tick_effects(T0 + timedelta(seconds=59)) == []
        # At expiry: exactly one combat.effect_expired, marked, never repeated.
        assert engine.tick_effects(T0 + timedelta(seconds=60)) == [effect_id]
        assert comp.expired is True
        assert engine.tick_effects(T0 + timedelta(seconds=3600)) == []
        expired_events = [e for e in seen if e.topic == "combat.effect_expired"]
        assert len(expired_events) == 1
        assert expired_events[0].payload["effect_id"] == effect_id
        assert expired_events[0].payload["target_id"] == "a"
        applied = [e for e in seen if e.topic == "combat.effect_applied"]
        assert len(applied) == 1 and applied[0].payload["name"] == "nightshade"
        assert engine.active_effects_on("a", T0 + timedelta(seconds=61)) == []

    def test_anchor_wins_over_component_expiry_mirror(self):
        # The anchor is the tense truth: shortening the ANCHOR window
        # expires the effect even though the component mirror is later.
        comp = EffectComponent(entity_id="fx", applied_at=T0, expires_at=T0 + timedelta(hours=1))
        anchor = TemporalAnchorComponent(
            entity_id="fx", valid_from=T0, valid_until=T0 + timedelta(minutes=5))
        assert not comp.is_expired(T0 + timedelta(minutes=4), anchor)
        assert comp.is_expired(T0 + timedelta(minutes=6), anchor)
        assert comp.remaining(T0, anchor) == timedelta(minutes=5)
        # Open-ended effect never expires.
        open_fx = EffectComponent(entity_id="fx2", applied_at=T0)
        assert not open_fx.is_expired(T0 + timedelta(days=365))
        assert open_fx.remaining(T0) is None


# ---------------------------------------------------------------------------
# Damage integration with HealthComponent
# ---------------------------------------------------------------------------

class TestDamage:
    def test_damage_flows_through_health_and_announces(self):
        bus, seen = _bus_with_topics()
        world = World("w", bus=bus)
        _fighter(world, "a", hp=50.0)
        engine = CombatEngine(world, bus=bus)
        health = engine.apply_damage("a", 30.0, source_id="b")
        # HealthComponent's own rule: wounded below half of max_hp.
        assert health.hp == 20.0 and health.wounded is True and health.alive is True
        event = [e for e in seen if e.topic == "combat.damage_applied"][0]
        assert event.payload["hp_after"] == 20.0 and event.payload["amount"] == 30.0
        # Lethal damage: health says not alive; combatant stance follows as down.
        engine.apply_damage("a", 999.0, source_id="b")
        assert health.alive is False and health.hp == 0.0
        assert world.get_component("a", "combatant").stance == "down"

    def test_damage_without_health_is_a_caller_error(self):
        world = World("w")
        world.create_entity(entity_id="ghost")
        engine = CombatEngine(world)
        with pytest.raises(KeyError):
            engine.apply_damage("ghost", 1.0)


# ---------------------------------------------------------------------------
# Tempo & initiative — one model, two clocks
# ---------------------------------------------------------------------------

class TestTempo:
    def test_deterministic_initiative_order(self):
        world = World("w")
        _fighter(world, "slow", initiative=1)
        _fighter(world, "fast", initiative=10)
        _fighter(world, "mid", initiative=5)
        engine = CombatEngine(world)
        clock = WorldClock(now=T0)
        assert engine.initiative_order(clock) == ["fast", "mid", "slow"]
        # Down combatants sort last in deterministic mode too.
        world.get_component("fast", "combatant").mark_down()
        assert engine.initiative_order(clock) == ["mid", "slow", "fast"]

    def test_wall_mode_orders_by_readiness_then_initiative(self):
        world = World("w")
        _fighter(world, "ready-low", initiative=1)
        _fighter(world, "cooling-high", initiative=99)
        _fighter(world, "ready-high", initiative=50)
        engine = CombatEngine(world)

        class FakeWall:
            def __init__(self): self.now = W0
            def __call__(self): return self.now

        fake = FakeWall()
        clock = WorldClock(now=T0)
        clock.enable_wall_sync(wall_source=fake)
        # cooling-high acted at T0 with a 10-minute cooldown.
        world.get_component("cooling-high", "combatant").begin_cooldown(600.0, now=T0)
        order = engine.initiative_order(clock)
        # Ready combatants first (initiative among themselves), cooling last
        # despite having the highest initiative — wall tempo is timestamps.
        assert order == ["ready-high", "ready-low", "cooling-high"]
        # After the wall advances past the cooldown, initiative rules again.
        fake.now = W0 + timedelta(seconds=601)
        assert engine.initiative_order(clock) == ["cooling-high", "ready-high", "ready-low"]


# ---------------------------------------------------------------------------
# Positioning — derived range bands + combatants_within
# ---------------------------------------------------------------------------

class TestPositioning:
    def test_range_band_thresholds_and_none(self):
        assert range_band(0.0) == "engaged"
        assert range_band(2.0) == "engaged"
        assert range_band(2.01) == "near"
        assert range_band(20.0) == "near"
        assert range_band(20.01) == "far"
        assert range_band(None) is None

    def test_bands_are_derived_from_live_positions(self):
        world = World("w")
        _fighter(world, "hero", pos=(0, 0, 0))
        _fighter(world, "melee", pos=(1, 0, 0))
        _fighter(world, "archer", pos=(15, 0, 0))
        _fighter(world, "distant", pos=(100, 0, 0))
        world.create_entity(entity_id="bystander")
        world.set_position("bystander", 1, 0, 0)  # close, but no combatant component
        oracle = _oracle(world)
        assert oracle.range_band_between("hero", "melee") == "engaged"
        assert oracle.range_band_between("hero", "archer") == "near"
        assert oracle.range_band_between("hero", "distant") == "far"
        found = oracle.combatants_within("hero", 30.0)
        assert [(r.entity_id, r.range_band) for r in found] == [
            ("melee", "engaged"), ("archer", "near")]
        # Moving the archer changes the band — derived, never stored stale.
        world.set_position("archer", (1.5, 0, 0))
        found = oracle.combatants_within("hero", 30.0)
        assert [(r.entity_id, r.range_band) for r in found] == [
            ("melee", "engaged"), ("archer", "engaged")]
        assert oracle.range_band_between("hero", "bystander") == "engaged"
        assert oracle.range_band_between("hero", "ghost") is None
        with pytest.raises(ValueError):
            oracle.combatants_within("hero", -1.0)


# ---------------------------------------------------------------------------
# Persistence round-trip — generic, no migration
# ---------------------------------------------------------------------------

class TestPersistence:
    def test_combat_state_round_trips(self, tmp_path):
        store = WorldStore(tmp_path / "world.db")
        world = World("combat-world")
        _fighter(world, "a", initiative=7, faction="wolves", pos=(1, 2, 3))
        _fighter(world, "b", initiative=3, pos=(4, 5, 6))
        threats = ThreatComponent(entity_id="a")
        threats.assess("b", 0.8, basis_event_ids=["evt-1"], source="observed", confidence=0.9, at=T0)
        world.add_component("a", threats)
        engine = CombatEngine(world)
        eid = engine.start_engagement(["a", "b"], at=T0, anchor_position=(2, 3, 4))
        effect_id = engine.apply_effect("b", name="ward", kind="buff", magnitude=1.5,
                                        duration_seconds=120.0, at=T0)
        store.save(world)

        loaded = store.load("combat-world")
        combatant = loaded.get_component("a", "combatant")
        assert combatant.initiative == 7 and combatant.faction_id == "wolves"
        assert combatant.engagement_id == eid and combatant.stance == "engaged"
        engagement = loaded.get_component(eid, "engagement")
        assert engagement.participant_ids == ["a", "b"] and engagement.state == "skirmish"
        anchor = loaded.get_position(eid)
        assert anchor is not None and anchor.position == (2.0, 3.0, 4.0)
        loaded_threats = loaded.get_component("a", "threats")
        assert loaded_threats.level_for("b") == 0.8
        assert loaded_threats.get_assessment("b").basis_event_ids == ["evt-1"]
        effect = loaded.get_component(effect_id, "effect")
        assert effect.name == "ward" and effect.expires_at == T0 + timedelta(seconds=120)
        oracle = _oracle(loaded)
        assert oracle.get_engagement("b").engagement_id == eid
        assert [(t.observer_id, t.level) for t in oracle.threats_to("b")] == [("a", 0.8)]
