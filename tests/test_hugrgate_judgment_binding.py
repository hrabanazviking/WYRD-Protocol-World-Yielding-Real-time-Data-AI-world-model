"""WY-T3 gate tests — HugrGate judgment binding.

Gate: on the recorded fixture stream (a scripted fight: approach,
first blow, ally joins, enemy flees, combat ends), the model's combat
state matches the expected table at every step; every transition
carries its judgment basis.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import wyrdforge.ecs.components.tactical  # noqa: F401
from wyrdforge.ecs.world import World
from wyrdforge.events.intake import EventIntake, WorldEvent
from wyrdforge.events.judgment import FixtureHugrGateClient, HttpHugrGateClient, JudgmentBinding

UTC = timezone.utc
T0 = datetime(2026, 11, 18, 12, 0, 0, tzinfo=UTC)


def _ev(n, kind, payload, participants):
    when = T0 + timedelta(seconds=10 * n)
    return WorldEvent(event_id=f"fight-{n}", source_connector="connector:fixture", world_time=when, received_time=when + timedelta(seconds=1), kind=kind, participant_ids=participants, payload=payload)


def _fight():
    return [
        _ev(1, "combat.approach", {"subject_id": "hero", "target_id": "goblin-1", "threat_subject": "goblin-1", "note": "goblin approaches"}, ["hero", "goblin-1"]),
        _ev(2, "combat.begun", {"subject_id": "hero", "engagement_id": "eng-1", "target_ids": ["goblin-1"], "threat_subject": "goblin-1", "grade": "high", "note": "first blow"}, ["hero", "goblin-1"]),
        _ev(3, "combat.joined", {"subject_id": "ally", "engagement_id": "eng-1", "target_ids": ["goblin-1"], "note": "ally joins"}, ["ally", "goblin-1"]),
        _ev(4, "combat.turned", {"subject_id": "hero", "engagement_id": "eng-1", "threat_subject": "goblin-1", "note": "enemy flees"}, ["hero", "goblin-1"]),
        _ev(5, "combat.ended", {"subject_id": "hero", "engagement_id": "eng-1", "threat_subject": "goblin-1", "note": "combat ends"}, ["hero", "goblin-1"]),
    ]


def _world():
    world = World("w")
    for eid in ("hero", "ally", "goblin-1"):
        world.create_entity(entity_id=eid)
    return world


def _snapshot(world):
    def comp(eid, key):
        return world.get_component(eid, key)
    hero_phase = comp("hero", "combat_phase")
    gob_threat = comp("goblin-1", "threat_level")
    return {
        "hero_in_combat": bool(comp("hero", "in_combat") and comp("hero", "in_combat").active),
        "hero_phase": hero_phase.phase if hero_phase else None,
        "hero_engaged": list(comp("hero", "engaged_with").target_ids) if comp("hero", "engaged_with") else [],
        "ally_in_combat": bool(comp("ally", "in_combat") and comp("ally", "in_combat").active),
        "goblin_threat": gob_threat.grade if gob_threat else None,
    }


EXPECTED = [
    {"hero_in_combat": False, "hero_phase": None, "hero_engaged": [], "ally_in_combat": False, "goblin_threat": "guarded"},
    {"hero_in_combat": True, "hero_phase": "begun", "hero_engaged": ["goblin-1"], "ally_in_combat": False, "goblin_threat": "high"},
    {"hero_in_combat": True, "hero_phase": "begun", "hero_engaged": ["goblin-1"], "ally_in_combat": True, "goblin_threat": "high"},
    {"hero_in_combat": True, "hero_phase": "turned", "hero_engaged": ["goblin-1"], "ally_in_combat": True, "goblin_threat": "low"},
    {"hero_in_combat": False, "hero_phase": "ended", "hero_engaged": [], "ally_in_combat": True, "goblin_threat": "none"},
]


class TestScriptedFightGate:
    def test_state_matches_expected_table_at_every_step(self):
        world, intake = _world(), EventIntake()
        binding = JudgmentBinding(world, intake, FixtureHugrGateClient())
        stored = intake.ingest_many(_fight())
        for step, stored_event in enumerate(stored):
            binding.process(stored_event)
            assert _snapshot(world) == EXPECTED[step], f"step {step + 1}"

    def test_every_transition_carries_judgment_basis(self):
        world, intake = _world(), EventIntake()
        binding = JudgmentBinding(world, intake, FixtureHugrGateClient())
        binding.process_many(intake.ingest_many(_fight()))
        records = binding.records()
        assert [r.effect for r in records] == ["none", "begun", "joined", "turned", "ended"]
        assert all(r.basis and r.judge for r in records)
        assert all(r.relevant for r in records)
        judged = {r.event_id for r in records}
        assert all(c.event_id in judged for c in intake.changes())
        assert len(intake.changes()) >= 8

    def test_irrelevant_event_changes_nothing_but_is_recorded(self):
        world, intake = _world(), EventIntake()
        binding = JudgmentBinding(world, intake, FixtureHugrGateClient())
        ev = _ev(9, "weather.rain", {"subject_id": "hero"}, ["hero"])
        rec = binding.process(intake.ingest(ev))
        assert rec.relevant is False and rec.applied is False
        assert _snapshot(world)["hero_phase"] is None

    def test_records_round_trip(self):
        world, intake = _world(), EventIntake()
        binding = JudgmentBinding(world, intake, FixtureHugrGateClient())
        binding.process_many(intake.ingest_many(_fight()))
        back = JudgmentBinding.from_records(world, intake, FixtureHugrGateClient(), binding.to_dict())
        assert back.to_dict() == binding.to_dict()


class TestHttpClientShape:
    def test_posts_judge_spec_and_parses_basis(self):
        seen = {}

        def transport(url, body):
            seen["url"] = url
            seen["body"] = body
            return {"value": "begun", "probability": 0.73, "backend": "keyword", "model": "keyword-1.0"}

        client = HttpHugrGateClient("http://127.0.0.1:8387", transport=transport)
        intake = EventIntake()
        stored = intake.ingest(_fight()[1])
        verdict = client.judge(stored)
        assert seen["url"].endswith("/judge")
        assert seen["body"]["spec"]["options"] == ["begun", "joined", "turned", "ended", "none"]
        assert verdict["effect"] == "begun" and verdict["backend"] == "keyword"
        assert "keyword" in verdict["basis"]
