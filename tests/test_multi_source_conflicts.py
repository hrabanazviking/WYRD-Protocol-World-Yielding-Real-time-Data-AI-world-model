"""WY-T5 gate tests — multi-source conflict handling.

Gate: conflict fixtures resolve per the declared rule (freshest
authoritative source wins for state); no report is ever silently
overwritten — both reports stay in intake and the conflict stays on
record.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

import wyrdforge.ecs.components.tactical  # noqa: F401
from wyrdforge.ecs.world import World
from wyrdforge.events.conflicts import ConflictTracker, MultiSourceApplier, extract_claim
from wyrdforge.events.intake import EventIntake, WorldEvent

UTC = timezone.utc
T0 = datetime(2026, 11, 18, 12, 0, 0, tzinfo=UTC)


def _threat(event_id, source, grade, at_seconds, received_seconds=None):
    when = T0 + timedelta(seconds=at_seconds)
    return WorldEvent(
        event_id=event_id, source_connector=source, world_time=when,
        received_time=T0 + timedelta(seconds=at_seconds if received_seconds is None else received_seconds),
        kind="threat.assessed", participant_ids=["goblin-1"],
        payload={"subject_id": "goblin-1", "grade": grade})


def _phase(event_id, source, kind, at_seconds, received_seconds=None):
    when = T0 + timedelta(seconds=at_seconds)
    return WorldEvent(
        event_id=event_id, source_connector=source, world_time=when,
        received_time=T0 + timedelta(seconds=at_seconds if received_seconds is None else received_seconds),
        kind=kind, participant_ids=["hero"],
        payload={"subject_id": "hero", "engagement_id": "eng-1", "target_ids": ["goblin-1"]})


def _rig(authority=None):
    world = World("w")
    for eid in ("hero", "goblin-1"):
        world.create_entity(entity_id=eid)
    intake = EventIntake()
    tracker = ConflictTracker(authority=authority)
    return world, intake, tracker, MultiSourceApplier(world, intake, tracker)


def _grade(world):
    comp = world.get_component("goblin-1", "threat_level")
    return comp.grade if comp else None


class TestSimultaneousDisagreement:
    def test_freshest_received_wins_and_both_reports_kept(self):
        world, intake, tracker, applier = _rig()
        d1 = applier.submit(_threat("scout-1", "connector:scout", "high", 30, 31))
        d2 = applier.submit(_threat("warden-1", "connector:warden", "low", 30, 32))
        assert d1.applied is True
        assert d2.is_winner is True and d2.applied is True
        assert _grade(world) == "low"  # later received_time tiebreak
        assert len(intake) == 2  # no report overwritten
        conflicts = tracker.conflicts()
        assert len(conflicts) == 1
        assert set(conflicts[0].report_event_ids) == {"scout-1", "warden-1"}
        assert conflicts[0].winner_event_id == "warden-1"
        assert conflicts[0].loser_event_ids == ["scout-1"]
        assert "freshest authoritative" in conflicts[0].rule

    def test_loser_arriving_second_changes_no_state(self):
        world, intake, tracker, applier = _rig()
        applier.submit(_threat("warden-1", "connector:warden", "low", 30, 32))
        d2 = applier.submit(_threat("scout-1", "connector:scout", "high", 30, 31))
        assert d2.is_winner is False and d2.applied is False
        assert _grade(world) == "low"
        assert len(tracker.conflicts()) == 1
        assert len(intake) == 2


class TestAuthorityBeatsFreshness:
    def test_authoritative_source_wins_despite_later_rival(self):
        world, intake, tracker, applier = _rig(
            authority={"connector:warden": 10, "connector:scout": 1})
        applier.submit(_threat("warden-1", "connector:warden", "guarded", 30, 31))
        d2 = applier.submit(_threat("scout-1", "connector:scout", "critical", 30, 35))
        assert d2.is_winner is False and d2.applied is False
        assert _grade(world) == "guarded"
        conflict = tracker.conflicts()[0]
        assert conflict.winner_event_id == "warden-1"
        assert "authority" in conflict.reason


class TestLateDuplicate:
    def test_late_stale_report_is_kept_but_not_applied(self):
        world, intake, tracker, applier = _rig()
        applier.submit(_threat("scout-fresh", "connector:scout", "high", 50, 51))
        late = applier.submit(_threat("scout-late", "connector:scout", "low", 30, 60))
        assert late.is_winner is False and late.applied is False
        assert late.conflict_id is not None
        assert _grade(world) == "high"  # fresher state stands
        assert len(intake) == 2 and intake.get("scout-late") is not None
        assert tracker.current_winner("threat_level:goblin-1").event_id == "scout-fresh"

    def test_exact_duplicate_event_id_still_refused_by_intake(self):
        world, intake, tracker, applier = _rig()
        event = _threat("dup-1", "connector:scout", "high", 30)
        applier.submit(event)
        with pytest.raises(ValueError, match="duplicate event_id"):
            applier.submit(event)
        assert len(intake) == 1


class TestOrderlySupersessionAndCorroboration:
    def test_strictly_fresher_report_supersedes_without_conflict(self):
        world, intake, tracker, applier = _rig()
        applier.submit(_threat("s-1", "connector:scout", "guarded", 10, 11))
        d2 = applier.submit(_threat("w-1", "connector:warden", "severe", 40, 41))
        assert d2.is_winner is True and d2.applied is True
        assert d2.superseded_event_ids == ["s-1"] and d2.conflict_id is None
        assert tracker.conflicts() == []
        assert _grade(world) == "severe"
        assert [r.event_id for r in tracker.reports("threat_level:goblin-1")] == ["s-1", "w-1"]

    def test_same_value_from_second_source_is_corroboration(self):
        world, intake, tracker, applier = _rig()
        applier.submit(_threat("s-1", "connector:scout", "high", 30, 31))
        d2 = applier.submit(_threat("w-1", "connector:warden", "high", 30, 32))
        assert d2.corroboration is True and d2.applied is False
        assert tracker.conflicts() == []
        assert _grade(world) == "high"
        assert len(intake) == 2


class TestCombatPhaseConflict:
    def test_phase_conflict_resolves_and_state_matches_winner(self):
        world, intake, tracker, applier = _rig()
        applier.submit(_phase("p-begun", "connector:scout", "combat.begun", 30, 31))
        d2 = applier.submit(_phase("p-ended", "connector:warden", "combat.ended", 30, 32))
        assert d2.is_winner is True and d2.applied is True
        phase = world.get_component("hero", "combat_phase")
        assert phase.phase == "ended"
        in_combat = world.get_component("hero", "in_combat")
        assert in_combat.active is False
        assert len(tracker.conflicts()) == 1
        assert tracker.conflicts()[0].claim_key == "combat_phase:hero"


class TestRecordsRoundTrip:
    def test_tracker_serialization_round_trip_keeps_everything(self):
        world, intake, tracker, applier = _rig(
            authority={"connector:warden": 10})
        applier.submit(_threat("scout-1", "connector:scout", "high", 30, 31))
        applier.submit(_threat("warden-1", "connector:warden", "low", 30, 32))
        restored = ConflictTracker.from_dict(tracker.to_dict())
        assert restored.authority == {"connector:warden": 10}
        assert [r.event_id for r in restored.reports()] == ["scout-1", "warden-1"]
        assert len(restored.conflicts()) == 1
        assert restored.conflicts()[0].winner_event_id == "warden-1"
        assert restored.current_winner("threat_level:goblin-1").event_id == "warden-1"
        assert len(restored.decisions()) == 2

    def test_extract_claim_shapes(self):
        assert extract_claim(_threat("x", "connector:s", "low", 1)).claim_key == "threat_level:goblin-1"
        assert extract_claim(_phase("y", "connector:s", "combat.turned", 1)).claim_value == "turned"
