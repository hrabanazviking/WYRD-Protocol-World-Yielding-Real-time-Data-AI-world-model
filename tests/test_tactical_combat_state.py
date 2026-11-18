"""WY-T1 gate tests — tactical combat-state components.

Gate: component schema + serialization round-trip tests pass; existing
WYRD suites stay green; a hand-built combat scenario reads back exactly
as written.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

import wyrdforge.ecs.components.tactical  # noqa: F401  (registry)
from wyrdforge.ecs.component import deserialize_component
from wyrdforge.ecs.components.tactical import (
    CombatPhaseComponent,
    EngagedWithComponent,
    InCombatComponent,
    ThreatLevelComponent,
    grade_rank,
)
from wyrdforge.ecs.world import World

UTC = timezone.utc
T0 = datetime(2026, 11, 18, 12, 0, 0, tzinfo=UTC)


def _roundtrip(comp):
    data = comp.model_dump(mode="json")
    back = deserialize_component(data)
    assert type(back) is type(comp)
    assert back.model_dump(mode="json") == data
    return back


class TestSchemasAndRoundTrip:
    def test_all_four_round_trip(self):
        _roundtrip(InCombatComponent(entity_id="hero", active=True, engagement_id="eng-1", entered_at=T0))
        ew = EngagedWithComponent(entity_id="hero", engagement_id="eng-1")
        ew.engage("goblin-1")
        ew.engage("goblin-2")
        _roundtrip(ew)
        _roundtrip(ThreatLevelComponent(entity_id="goblin-1", grade="high", source="connector:roll20", assessed_at=T0))
        cp = CombatPhaseComponent(entity_id="hero", engagement_id="eng-1")
        cp.transition_to("begun", at=T0)
        cp.transition_to("joined", at=T0 + timedelta(seconds=5))
        _roundtrip(cp)

    def test_threat_grade_ordering(self):
        assert grade_rank("none") < grade_rank("low") < grade_rank("critical")
        comp = ThreatLevelComponent(entity_id="x", grade="high", source="s", assessed_at=T0)
        assert comp.is_at_least("guarded") and not comp.is_at_least("severe")

    def test_threat_age_is_derived(self):
        comp = ThreatLevelComponent(entity_id="x", grade="low", source="s", assessed_at=T0)
        assert comp.age_at(T0 + timedelta(seconds=90)) == timedelta(seconds=90)

    def test_self_engagement_rejected(self):
        with pytest.raises(ValueError):
            EngagedWithComponent(entity_id="a").engage("a")

    def test_ended_is_terminal(self):
        cp = CombatPhaseComponent(entity_id="a")
        cp.transition_to("begun", at=T0)
        cp.transition_to("ended", at=T0 + timedelta(seconds=10))
        with pytest.raises(ValueError):
            cp.transition_to("joined", at=T0 + timedelta(seconds=20))


class TestHandBuiltScenario:
    def test_scenario_reads_back_exactly_as_written(self):
        world = World("w")
        for eid in ("hero", "ally", "goblin-1"):
            world.create_entity(entity_id=eid)
        hero_in = InCombatComponent(entity_id="hero")
        hero_in.enter("eng-1", at=T0)
        world.add_component("hero", hero_in)
        hero_ew = EngagedWithComponent(entity_id="hero", engagement_id="eng-1")
        hero_ew.engage("goblin-1")
        world.add_component("hero", hero_ew)
        world.add_component("hero", ThreatLevelComponent(
            entity_id="hero", grade="guarded", source="connector:test", assessed_at=T0))
        hero_phase = CombatPhaseComponent(entity_id="hero", engagement_id="eng-1")
        hero_phase.transition_to("begun", at=T0)
        hero_phase.transition_to("joined", at=T0 + timedelta(seconds=30), note="ally joins")
        world.add_component("hero", hero_phase)
        world.add_component("goblin-1", ThreatLevelComponent(
            entity_id="goblin-1", grade="high", source="connector:test", assessed_at=T0))

        in_c = world.get_component("hero", "in_combat")
        assert isinstance(in_c, InCombatComponent)
        assert in_c.active is True and in_c.engagement_id == "eng-1" and in_c.entered_at == T0
        ew = world.get_component("hero", "engaged_with")
        assert isinstance(ew, EngagedWithComponent)
        assert ew.target_ids == ["goblin-1"] and ew.is_engaged_with("goblin-1")
        tl = world.get_component("hero", "threat_level")
        assert isinstance(tl, ThreatLevelComponent)
        assert tl.grade == "guarded" and tl.source == "connector:test"
        assert tl.age_at(T0 + timedelta(minutes=2)) == timedelta(minutes=2)
        ph = world.get_component("hero", "combat_phase")
        assert isinstance(ph, CombatPhaseComponent)
        assert ph.phase == "joined"
        assert [m.phase for m in ph.history] == ["begun", "joined"]
        gob = world.get_component("goblin-1", "threat_level")
        assert isinstance(gob, ThreatLevelComponent) and gob.grade == "high"
