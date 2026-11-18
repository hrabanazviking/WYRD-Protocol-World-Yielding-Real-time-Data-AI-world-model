"""World-event intake with provenance — WY-T2 (Tvíheimr readiness).

Events arrive stamped (source connector, world time, received time,
kind, participants, digest) and are stored as first-class records
linked to the entities they touch — never silently folded into state.
State changes applied from an event are recorded as provenance links,
so every tactical state change (WY-T1) can be traced to the event
that caused it.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import Field

from wyrdforge.models.common import StrictModel


def _now() -> datetime:
    return datetime.now(timezone.utc)


def compute_digest(*, source_connector: str, world_time: datetime, kind: str,
                   participant_ids: list[str], payload: dict[str, Any]) -> str:
    canonical = json.dumps({
        "source_connector": source_connector,
        "world_time": world_time.astimezone(timezone.utc).isoformat(),
        "kind": kind,
        "participant_ids": list(participant_ids),
        "payload": payload,
    }, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class WorldEvent(StrictModel):
    """One stamped world event, stored as a first-class record."""

    event_id: str
    source_connector: str
    world_time: datetime
    received_time: datetime
    kind: str
    participant_ids: list[str] = Field(default_factory=list)
    payload: dict[str, Any] = Field(default_factory=dict)
    digest: str = ""

    def model_post_init(self, __context: Any) -> None:
        expected = compute_digest(
            source_connector=self.source_connector, world_time=self.world_time,
            kind=self.kind, participant_ids=self.participant_ids, payload=self.payload)
        if not self.digest:
            object.__setattr__(self, "digest", expected)
        elif self.digest != expected:
            raise ValueError(f"event {self.event_id}: digest mismatch")

    @property
    def entity_ids(self) -> list[str]:
        ids = list(self.participant_ids)
        for key in ("subject_id", "target_id"):
            value = self.payload.get(key)
            if isinstance(value, str) and value not in ids:
                ids.append(value)
        for value in self.payload.get("target_ids", []) or []:
            if isinstance(value, str) and value not in ids:
                ids.append(value)
        return ids


class StoredEvent(StrictModel):
    seq: int
    event: WorldEvent


class StateChangeRecord(StrictModel):
    """Provenance link: one state change, caused by one event."""

    event_id: str
    seq: int
    entity_id: str
    component_type: str
    change: str
    at: datetime


class EventIntake:
    """Ordered, append-only intake. Duplicates are refused, never folded."""

    def __init__(self) -> None:
        self._stored: list[StoredEvent] = []
        self._by_id: dict[str, StoredEvent] = {}
        self._changes: list[StateChangeRecord] = []
        self._next_seq = 1

    def ingest(self, event: WorldEvent) -> StoredEvent:
        if event.event_id in self._by_id:
            raise ValueError(f"duplicate event_id refused: {event.event_id}")
        stored = StoredEvent(seq=self._next_seq, event=event)
        self._next_seq += 1
        self._stored.append(stored)
        self._by_id[event.event_id] = stored
        return stored

    def ingest_many(self, events: list[WorldEvent]) -> list[StoredEvent]:
        return [self.ingest(e) for e in events]

    def __len__(self) -> int:
        return len(self._stored)

    def all(self) -> list[StoredEvent]:
        return list(self._stored)

    def get(self, event_id: str) -> StoredEvent | None:
        return self._by_id.get(event_id)

    def for_entity(self, entity_id: str) -> list[StoredEvent]:
        return [s for s in self._stored if entity_id in s.event.entity_ids]

    def of_kind(self, kind: str) -> list[StoredEvent]:
        return [s for s in self._stored if s.event.kind == kind]

    def is_complete_in_order(self, expected_ids: list[str]) -> bool:
        return [s.event.event_id for s in self._stored] == list(expected_ids) and \
            [s.seq for s in self._stored] == list(range(1, len(expected_ids) + 1))

    # -- provenance -------------------------------------------------
    def record_change(self, event_id: str, *, entity_id: str,
                      component_type: str, change: str) -> StateChangeRecord:
        stored = self._by_id.get(event_id)
        if stored is None:
            raise KeyError(f"cannot record change for unknown event {event_id}")
        rec = StateChangeRecord(event_id=event_id, seq=stored.seq, entity_id=entity_id,
                                component_type=component_type, change=change,
                                at=stored.event.world_time)
        self._changes.append(rec)
        return rec

    def changes(self) -> list[StateChangeRecord]:
        return list(self._changes)

    def trace_entity(self, entity_id: str) -> list[StateChangeRecord]:
        return [c for c in self._changes if c.entity_id == entity_id]

    def trace_component(self, entity_id: str, component_type: str) -> list[StateChangeRecord]:
        return [c for c in self._changes
                if c.entity_id == entity_id and c.component_type == component_type]

    def explain(self, entity_id: str, component_type: str) -> list[StoredEvent]:
        ids = [c.event_id for c in self.trace_component(entity_id, component_type)]
        return [self._by_id[i] for i in dict.fromkeys(ids)]

    # -- serialization ----------------------------------------------
    def to_dict(self) -> dict[str, Any]:
        return {"next_seq": self._next_seq,
                "events": [s.model_dump(mode="json") for s in self._stored],
                "changes": [c.model_dump(mode="json") for c in self._changes]}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "EventIntake":
        intake = cls()
        for raw in data.get("events", []):
            stored = StoredEvent.model_validate(raw)
            intake._stored.append(stored)
            intake._by_id[stored.event.event_id] = stored
        intake._changes = [StateChangeRecord.model_validate(c) for c in data.get("changes", [])]
        intake._next_seq = int(data.get("next_seq", len(intake._stored) + 1))
        return intake


def apply_tactical_event(world: Any, intake: EventIntake, stored: StoredEvent) -> list[StateChangeRecord]:
    """Apply one event to WY-T1 tactical components, recording provenance.

    Supported kinds: combat.begun, combat.joined, threat.assessed,
    combat.turned, combat.ended. Unknown kinds are stored by intake
    but change no state (and record no provenance).
    """
    from wyrdforge.ecs.components.tactical import (
        CombatPhaseComponent, EngagedWithComponent, InCombatComponent,
        ThreatLevelComponent,
    )

    event = stored.event
    payload = event.payload
    subject = payload.get("subject_id") or (event.participant_ids[0] if event.participant_ids else None)
    if subject is None:
        return []
    engagement_id = payload.get("engagement_id")
    targets: list[str] = list(payload.get("target_ids", []) or [])
    if payload.get("target_id"):
        targets.append(payload["target_id"])
    records: list[StateChangeRecord] = []

    def _get(cls: type, type_key: str):
        comp = world.get_component(subject, type_key)
        if comp is None:
            comp = cls(entity_id=subject)
            world.add_component(subject, comp)
        return comp

    def _rec(component_type: str, change: str) -> None:
        records.append(intake.record_change(event.event_id, entity_id=subject,
                                            component_type=component_type, change=change))

    if event.kind in ("combat.begun", "combat.joined"):
        phase_name: Literal["begun", "joined"] = "begun" if event.kind == "combat.begun" else "joined"
        in_combat = _get(InCombatComponent, "in_combat")
        in_combat.enter(engagement_id, at=event.world_time)
        _rec("in_combat", f"entered combat ({phase_name})")
        engaged = _get(EngagedWithComponent, "engaged_with")
        if engagement_id is not None:
            engaged.engagement_id = engagement_id
        for target in targets:
            if engaged.engage(target):
                _rec("engaged_with", f"engaged with {target}")
        phase = _get(CombatPhaseComponent, "combat_phase")
        if engagement_id is not None:
            phase.engagement_id = engagement_id
        phase.transition_to(phase_name, at=event.world_time, note=payload.get("note", ""))
        _rec("combat_phase", f"phase -> {phase_name}")
    elif event.kind == "threat.assessed":
        threat = _get(ThreatLevelComponent, "threat_level")
        threat.set_grade(payload["grade"], source=payload.get("source", event.source_connector),
                         at=event.world_time)
        _rec("threat_level", f"grade -> {payload['grade']}")
    elif event.kind == "combat.turned":
        phase = _get(CombatPhaseComponent, "combat_phase")
        phase.transition_to("turned", at=event.world_time, note=payload.get("note", ""))
        _rec("combat_phase", "phase -> turned")
        if payload.get("grade"):
            threat = _get(ThreatLevelComponent, "threat_level")
            threat.set_grade(payload["grade"], source=payload.get("source", event.source_connector),
                             at=event.world_time)
            _rec("threat_level", f"grade -> {payload['grade']}")
    elif event.kind == "combat.ended":
        phase = _get(CombatPhaseComponent, "combat_phase")
        phase.transition_to("ended", at=event.world_time, note=payload.get("note", ""))
        _rec("combat_phase", "phase -> ended")
        in_combat = _get(InCombatComponent, "in_combat")
        in_combat.leave()
        _rec("in_combat", "left combat (ended)")
        engaged = _get(EngagedWithComponent, "engaged_with")
        if engaged.target_ids:
            engaged.clear()
            _rec("engaged_with", "engagements cleared (ended)")
    return records
