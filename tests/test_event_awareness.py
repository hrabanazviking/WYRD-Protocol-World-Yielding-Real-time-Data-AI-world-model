"""WY-T4 gate tests — event awareness queries.

Gate: query fixtures return the expected picture at several points
along the scripted fight, including after the feed stops (staleness
shown, not papered over).
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import wyrdforge.ecs.components.tactical  # noqa: F401
from wyrdforge.ecs.world import World
from wyrdforge.events.awareness import AwarenessQuery
from wyrdforge.events.intake import EventIntake, WorldEvent
from wyrdforge.events.judgment import FixtureHugrGateClient, JudgmentBinding

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


def _rig():
    world = World("w")
    for eid in ("hero", "ally", "goblin-1"):
        world.create_entity(entity_id=eid)
    intake = EventIntake()
    binding = JudgmentBinding(world, intake, FixtureHugrGateClient())
    return world, intake, binding, AwarenessQuery(world, intake)


def _run_steps(n):
    world, intake, binding, query = _rig()
    events = _fight()
    snaps = []
    for i in range(n):
        stored = intake.ingest(events[i])
        binding.process(stored)
        now = stored.event.received_time + timedelta(seconds=2)
        snaps.append(query.what_is_happening_now(now))
    return world, intake, query, snaps


class TestPictureAlongTheFight:
    def test_approach_no_combat_yet_but_threat_visible(self):
        _, _, _, snaps = _run_steps(1)
        snap = snaps[0]
        assert snap.feed_status == "live" and snap.event_count == 1
        assert snap.active_combats == []
        assert [t.entity_id for t in snap.threats] == ["goblin-1"]
        assert snap.threats[0].grade == "guarded" and snap.threats[0].source
        assert snap.threats[0].age_seconds >= 0

    def test_begun_shows_active_combat_and_rising_threat(self):
        _, _, _, snaps = _run_steps(2)
        snap = snaps[1]
        assert [c.entity_id for c in snap.active_combats] == ["hero"]
        combat = snap.active_combats[0]
        assert combat.phase == "begun" and combat.engaged_with == ["goblin-1"]
        assert combat.source == "connector:fixture" and combat.last_event_id == "fight-2"
        threat = snap.threats[0]
        assert threat.grade == "high" and threat.rising is True and threat.previous_grade == "guarded"
        assert [t.entity_id for t in snap.rising_threats] == ["goblin-1"]
        assert snap.is_quiet is False

    def test_joined_adds_ally_combat(self):
        _, _, _, snaps = _run_steps(3)
        assert sorted(c.entity_id for c in snaps[2].active_combats) == ["ally", "hero"]

    def test_turned_threat_falls_not_rising(self):
        _, _, _, snaps = _run_steps(4)
        snap = snaps[3]
        hero = [c for c in snap.active_combats if c.entity_id == "hero"][0]
        assert hero.phase == "turned"
        assert snap.threats == [] or snap.threats[0].grade == "low"
        assert snap.rising_threats == []

    def test_ended_no_active_hero_combat(self):
        _, _, _, snaps = _run_steps(5)
        snap = snaps[4]
        assert [c.entity_id for c in snap.active_combats] == ["ally"]
        assert snap.threats == []
        assert [e.event_id for e in snap.notable_events] == ["fight-1", "fight-2", "fight-3", "fight-4", "fight-5"]
        assert all(e.source_connector == "connector:fixture" for e in snap.notable_events)


class TestStalenessNeverHidden:
    def test_empty_feed_reads_empty_not_quiet_live(self):
        _, _, query, _ = _run_steps(0)
        snap = query.what_is_happening_now(T0)
        assert snap.feed_status == "empty" and snap.event_count == 0 and snap.is_quiet is True

    def test_after_feed_stops_stale_then_dead(self):
        _, intake, query, _ = _run_steps(5)
        last = intake.all()[-1].event.received_time
        stale = query.what_is_happening_now(last + timedelta(seconds=60))
        assert stale.feed_status == "stale" and stale.feed_age_seconds == 60
        dead = query.what_is_happening_now(last + timedelta(seconds=600))
        assert dead.feed_status == "dead" and dead.feed_age_seconds == 600
        # the picture is still shown, but its staleness is on its face
        assert dead.threats == [] and dead.event_count == 5

    def test_threat_age_grows_with_query_time(self):
        _, _, query, snaps = _run_steps(2)
        later = query.what_is_happening_now(snaps[1].at + timedelta(seconds=90))
        assert later.threats[0].age_seconds > snaps[1].threats[0].age_seconds + 80

    def test_snapshot_round_trip(self):
        _, _, _, snaps = _run_steps(2)
        snap = snaps[1]
        from wyrdforge.events.awareness import AwarenessSnapshot
        assert AwarenessSnapshot.model_validate(snap.model_dump(mode="json")).model_dump(mode="json") == snap.model_dump(mode="json")
