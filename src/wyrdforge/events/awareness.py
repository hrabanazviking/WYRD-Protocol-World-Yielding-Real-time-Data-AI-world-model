"""Event awareness queries — WY-T4 (Tviheimr readiness).

The read side Tviheimr's presence will use. ``what_is_happening_now``
answers from the WY-T1 tactical model plus the WY-T2 intake: active
combats, threats (with rising movement derived from the provenance
record), and notable events — every entry carrying its source and its
age at query time. Staleness is reported, never hidden: feed health is
computed from the last received event, so a quiet feed reads as quiet
and a dead feed reads as dead.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Literal

from pydantic import Field

from wyrdforge.ecs.components.tactical import grade_rank
from wyrdforge.events.intake import EventIntake
from wyrdforge.models.common import StrictModel

FeedStatus = Literal["live", "stale", "dead", "empty"]
_NOTABLE_KINDS = ("combat.", "threat.")


class ActiveCombat(StrictModel):
    entity_id: str
    engagement_id: str | None = None
    phase: str | None = None
    engaged_with: list[str] = Field(default_factory=list)
    entered_at: datetime | None = None
    age_seconds: float | None = None
    source: str = ""
    last_event_id: str | None = None


class ThreatReport(StrictModel):
    entity_id: str
    grade: str
    rank: int
    source: str
    assessed_at: datetime
    age_seconds: float
    rising: bool = False
    previous_grade: str | None = None


class NotableEvent(StrictModel):
    seq: int
    event_id: str
    kind: str
    world_time: datetime
    received_time: datetime
    source_connector: str
    age_seconds: float
    participant_ids: list[str] = Field(default_factory=list)


class AwarenessSnapshot(StrictModel):
    at: datetime
    feed_status: FeedStatus
    feed_age_seconds: float | None = None
    last_event_id: str | None = None
    last_received_time: datetime | None = None
    event_count: int = 0
    is_quiet: bool = True
    active_combats: list[ActiveCombat] = Field(default_factory=list)
    threats: list[ThreatReport] = Field(default_factory=list)
    rising_threats: list[ThreatReport] = Field(default_factory=list)
    notable_events: list[NotableEvent] = Field(default_factory=list)


class AwarenessQuery:
    """Read-only awareness over a world + its event intake."""

    def __init__(self, world: Any, intake: EventIntake, *,
                 stale_after: timedelta = timedelta(seconds=30),
                 dead_after: timedelta = timedelta(seconds=120)) -> None:
        if dead_after <= stale_after:
            raise ValueError("dead_after must exceed stale_after")
        self.world = world
        self.intake = intake
        self.stale_after = stale_after
        self.dead_after = dead_after

    # -- feed health --------------------------------------------------
    def feed_status(self, now: datetime) -> tuple[FeedStatus, float | None]:
        stored = self.intake.all()
        if not stored:
            return "empty", None
        age = (now - stored[-1].event.received_time).total_seconds()
        if age <= self.stale_after.total_seconds():
            return "live", age
        if age <= self.dead_after.total_seconds():
            return "stale", age
        return "dead", age

    # -- pieces ---------------------------------------------------------
    def _last_touch(self, entity_id: str):
        events = self.intake.for_entity(entity_id)
        return events[-1] if events else None

    def active_combats(self, now: datetime) -> list[ActiveCombat]:
        out: list[ActiveCombat] = []
        for entity in self.world.query_with_component("in_combat"):
            comp = self.world.get_component(entity.entity_id, "in_combat")
            if comp is None or not comp.active:
                continue
            phase_comp = self.world.get_component(entity.entity_id, "combat_phase")
            engaged = self.world.get_component(entity.entity_id, "engaged_with")
            last = self._last_touch(entity.entity_id)
            out.append(ActiveCombat(
                entity_id=entity.entity_id,
                engagement_id=comp.engagement_id,
                phase=phase_comp.phase if phase_comp else None,
                engaged_with=list(engaged.target_ids) if engaged else [],
                entered_at=comp.entered_at,
                age_seconds=(now - comp.entered_at).total_seconds() if comp.entered_at else None,
                source=last.event.source_connector if last else "",
                last_event_id=last.event.event_id if last else None,
            ))
        out.sort(key=lambda c: c.entity_id)
        return out

    def _grade_history(self, entity_id: str) -> list[str]:
        grades: list[str] = []
        for change in self.intake.trace_component(entity_id, "threat_level"):
            if "grade -> " in change.change:
                grades.append(change.change.split("grade -> ", 1)[1].split(" ", 1)[0])
        return grades

    def threats(self, now: datetime, *, min_grade: str = "guarded") -> list[ThreatReport]:
        out: list[ThreatReport] = []
        for entity in self.world.query_with_component("threat_level"):
            comp = self.world.get_component(entity.entity_id, "threat_level")
            if comp is None or grade_rank(comp.grade) < grade_rank(min_grade):
                continue
            history = self._grade_history(entity.entity_id)
            previous = history[-2] if len(history) >= 2 else None
            rising = previous is not None and grade_rank(comp.grade) > grade_rank(previous)
            out.append(ThreatReport(
                entity_id=entity.entity_id, grade=comp.grade, rank=grade_rank(comp.grade),
                source=comp.source, assessed_at=comp.assessed_at,
                age_seconds=comp.age_at(now).total_seconds(),
                rising=rising, previous_grade=previous,
            ))
        out.sort(key=lambda t: (-t.rank, t.entity_id))
        return out

    def notable_events(self, now: datetime, *, limit: int = 10) -> list[NotableEvent]:
        stored = [s for s in self.intake.all() if s.event.kind.startswith(_NOTABLE_KINDS)]
        out: list[NotableEvent] = []
        for s in stored[-limit:]:
            ev = s.event
            out.append(NotableEvent(
                seq=s.seq, event_id=ev.event_id, kind=ev.kind,
                world_time=ev.world_time, received_time=ev.received_time,
                source_connector=ev.source_connector,
                age_seconds=(now - ev.world_time).total_seconds(),
                participant_ids=list(ev.participant_ids),
            ))
        return out

    # -- the headline query ---------------------------------------------
    def what_is_happening_now(self, now: datetime, *, min_grade: str = "guarded",
                              notable_limit: int = 10) -> AwarenessSnapshot:
        status, feed_age = self.feed_status(now)
        stored = self.intake.all()
        combats = self.active_combats(now)
        threats = self.threats(now, min_grade=min_grade)
        rising = [t for t in threats if t.rising]
        return AwarenessSnapshot(
            at=now, feed_status=status, feed_age_seconds=feed_age,
            last_event_id=stored[-1].event.event_id if stored else None,
            last_received_time=stored[-1].event.received_time if stored else None,
            event_count=len(stored),
            is_quiet=(not combats and not threats),
            active_combats=combats, threats=threats, rising_threats=rising,
            notable_events=self.notable_events(now, limit=notable_limit),
        )
