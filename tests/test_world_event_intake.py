"""WY-T2 gate tests — event intake with provenance.

Gate: fixture event stream lands complete and in order; every state
change in WY-T1's scenario can be traced to the event that caused it.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

import wyrdforge.ecs.components.tactical  # noqa: F401
from wyrdforge.ecs.world import World
from wyrdforge.events.intake import EventIntake, WorldEvent, apply_tactical_event

UTC = timezone.utc
T0 = datetime(2026, 11, 18, 12, 0, 0, tzinfo=UTC)


def _ev(n, kind, payload, participants, at=None):
    when = at if at is not None else T0 + timedelta(seconds=10 * n)
    return WorldEvent(event_id=f"ev-{n}", source_connector="connector:fixture",
                      world_time=when, received_time=when + timedelta(seconds=1),
                      kind=kind, participant_ids=participants, payload=payload)


def _fixture_stream():
    return [
        _ev(1, "combat.begun", {"subject_id": "hero", "engagement_id": "eng-1",
                                "target_ids": ["goblin-1"]}, ["hero", "goblin-1"]),
        _ev(2, "threat.assessed", {"subject_id": "hero", "grade": "guarded",
                                   "source": "connector:fixture"}, ["hero"]),
        _ev(3, "threat.assessed", {"subject_id": "goblin-1", "grade": "high",
                                   "source": "connector:fixture"}, ["goblin-1"]),
        _ev(4, "combat.joined", {"subject_id": "hero", "engagement_id": "eng-1",
                                 "note": "ally joins"}, ["hero", "ally"]),
    ]


class TestIntake:
    def test_stream_lands_complete_and_in_order(self):
        intake = EventIntake()
        stored = intake.ingest_many(_fixture_stream())
        assert [s.seq for s in stored] == [1, 2, 3, 4]
        assert intake.is_complete_in_order(["ev-1", "ev-2", "ev-3", "ev-4"])
        assert len(intake.for_entity("goblin-1")) == 2
        assert len(intake.of_kind("threat.assessed")) == 2

    def test_digest_verified_and_round_trip(self):
        ev = _fixture_stream()[0]
        assert len(ev.digest) == 64
        back = WorldEvent.model_validate(ev.model_dump(mode="json"))
        assert back.digest == ev.digest and back.model_dump(mode="json") == ev.model_dump(mode="json")
        bad = ev.model_dump(mode="json")
        bad["payload"] = {"subject_id": "tampered"}
        with pytest.raises(ValueError):
            WorldEvent.model_validate(bad)

    def test_duplicate_refused_never_folded(self):
        intake = EventIntake()
        intake.ingest(_fixture_stream()[0])
        with pytest.raises(ValueError):
            intake.ingest(_fixture_stream()[0])
        assert len(intake) == 1

    def test_intake_serialization_round_trip(self):
        intake = EventIntake()
        intake.ingest_many(_fixture_stream())
        back = EventIntake.from_dict(intake.to_dict())
        assert back.is_complete_in_order(["ev-1", "ev-2", "ev-3", "ev-4"])
        assert back.to_dict() == intake.to_dict()


class TestTraceability:
    def test_every_state_change_traces_to_its_event(self):
        world = World("w")
        for eid in ("hero", "ally", "goblin-1"):
            world.create_entity(entity_id=eid)
        intake = EventIntake()
        for stored in intake.ingest_many(_fixture_stream()):
            apply_tactical_event(world, intake, stored)

        in_c = world.get_component("hero", "in_combat")
        assert in_c.active is True and in_c.engagement_id == "eng-1"
        ew = world.get_component("hero", "engaged_with")
        assert ew.target_ids == ["goblin-1"]
        tl = world.get_component("hero", "threat_level")
        assert tl.grade == "guarded" and tl.source == "connector:fixture"
        ph = world.get_component("hero", "combat_phase")
        assert ph.phase == "joined"
        assert [m.phase for m in ph.history] == ["begun", "joined"]
        gob = world.get_component("goblin-1", "threat_level")
        assert gob.grade == "high"

        # Every component state on hero traces to a causing event.
        for comp_type, expected_event in (
            ("in_combat", "ev-1"), ("engaged_with", "ev-1"),
            ("threat_level", "ev-2"), ("combat_phase", "ev-4"),
        ):
            causes = intake.explain("hero", comp_type)
            assert causes, f"no provenance for {comp_type}"
            assert expected_event in [s.event.event_id for s in causes]
        gob_causes = intake.explain("goblin-1", "threat_level")
        assert [s.event.event_id for s in gob_causes] == ["ev-3"]
        # No orphan changes: every record names a stored event.
        stored_ids = {s.event.event_id for s in intake.all()}
        assert all(c.event_id in stored_ids for c in intake.changes())
        assert len(intake.changes()) >= 6
