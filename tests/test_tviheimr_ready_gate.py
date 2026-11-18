"""Ready-for-Tvíheimr gate — fixture consumer proof.

A Tvíheimr-side fixture consumer asks "what is happening now" of a live
scripted world (WY-T1 components, WY-T2 intake, WY-T3 HugrGate binding,
WY-T4 awareness, WY-T5 multi-source resolution in the loop) and receives
the tactically current answer — combat state included — with sources
and ages attached.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import wyrdforge.ecs.components.tactical  # noqa: F401
from wyrdforge.ecs.world import World
from wyrdforge.events.awareness import AwarenessQuery
from wyrdforge.events.conflicts import ConflictTracker, MultiSourceApplier
from wyrdforge.events.intake import EventIntake, WorldEvent
from wyrdforge.events.judgment import FixtureHugrGateClient, JudgmentBinding

UTC = timezone.utc
T0 = datetime(2026, 11, 18, 12, 0, 0, tzinfo=UTC)


class FixtureConsumer:
    """Stands in for Tvíheimr's presence: asks only the WY-T4 query."""

    def __init__(self, query: AwarenessQuery) -> None:
        self.query = query

    def ask(self, now):
        return self.query.what_is_happening_now(now)


def _ev(n, kind, payload, participants, source="connector:fixture"):
    when = T0 + timedelta(seconds=10 * n)
    return WorldEvent(event_id=f"fight-{n}", source_connector=source, world_time=when,
                      received_time=when + timedelta(seconds=1), kind=kind,
                      participant_ids=participants, payload=payload)


def test_fixture_consumer_gets_tactically_current_answer():
    world = World("w")
    for eid in ("hero", "ally", "goblin-1"):
        world.create_entity(entity_id=eid)
    intake = EventIntake()
    binding = JudgmentBinding(world, intake, FixtureHugrGateClient())
    consumer = FixtureConsumer(AwarenessQuery(world, intake))
    fight = [
        _ev(1, "combat.approach", {"subject_id": "hero", "target_id": "goblin-1", "threat_subject": "goblin-1", "note": "goblin approaches"}, ["hero", "goblin-1"]),
        _ev(2, "combat.begun", {"subject_id": "hero", "engagement_id": "eng-1", "target_ids": ["goblin-1"], "threat_subject": "goblin-1", "grade": "high", "note": "first blow"}, ["hero", "goblin-1"]),
        _ev(3, "combat.joined", {"subject_id": "ally", "engagement_id": "eng-1", "target_ids": ["goblin-1"], "note": "ally joins"}, ["ally", "goblin-1"]),
        _ev(4, "combat.turned", {"subject_id": "hero", "engagement_id": "eng-1", "threat_subject": "goblin-1", "note": "enemy flees"}, ["hero", "goblin-1"]),
        _ev(5, "combat.ended", {"subject_id": "hero", "engagement_id": "eng-1", "threat_subject": "goblin-1", "note": "combat ends"}, ["hero", "goblin-1"]),
        _ev(6, "combat.ended", {"subject_id": "ally", "engagement_id": "eng-1", "threat_subject": "goblin-1", "note": "ally stands down"}, ["ally", "goblin-1"]),
    ]
    snap = None
    for i, event in enumerate(fight):
        stored = intake.ingest(event)
        binding.process(stored)
        snap = consumer.ask(stored.event.received_time + timedelta(seconds=2))
        if i == 2:  # mid-fight: two active combats, source + age attached
            assert [c.entity_id for c in snap.active_combats] == ["ally", "hero"]
            assert all(c.source == "connector:fixture" for c in snap.active_combats)
            assert all(c.age_seconds is not None and c.age_seconds >= 0 for c in snap.active_combats)
            assert snap.feed_status == "live" and snap.is_quiet is False
    # End state: combat over, threats clear, every event still on record.
    assert snap is not None
    assert snap.active_combats == [] and snap.threats == []
    assert snap.event_count == 6 and snap.is_quiet is True
    assert len(snap.notable_events) == 6
    assert all(e.source_connector == "connector:fixture" for e in snap.notable_events)
    # After the feed stops the consumer is told so, not papered over.
    dead = consumer.ask(T0 + timedelta(seconds=600))
    assert dead.feed_status == "dead"


def test_fixture_consumer_with_conflicting_sources():
    world = World("w")
    for eid in ("hero", "goblin-1"):
        world.create_entity(entity_id=eid)
    intake = EventIntake()
    tracker = ConflictTracker(authority={"connector:warden": 10, "connector:scout": 1})
    applier = MultiSourceApplier(world, intake, tracker)
    consumer = FixtureConsumer(AwarenessQuery(world, intake))
    base = T0
    scout = WorldEvent(event_id="scout-1", source_connector="connector:scout",
                       world_time=base, received_time=base + timedelta(seconds=1),
                       kind="threat.assessed", participant_ids=["goblin-1"],
                       payload={"subject_id": "goblin-1", "grade": "critical"})
    warden = WorldEvent(event_id="warden-1", source_connector="connector:warden",
                        world_time=base, received_time=base + timedelta(seconds=2),
                        kind="threat.assessed", participant_ids=["goblin-1"],
                        payload={"subject_id": "goblin-1", "grade": "guarded"})
    applier.submit(scout)
    applier.submit(warden)
    snap = consumer.ask(base + timedelta(seconds=5))
    # Authoritative warden report governs the consumer's picture; the
    # scout report and the conflict both remain on record.
    assert [t.grade for t in snap.threats] == ["guarded"]
    assert len(intake) == 2 and len(tracker.conflicts()) == 1
