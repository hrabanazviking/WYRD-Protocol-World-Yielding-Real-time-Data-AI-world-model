"""Tactical combat-state components — WY-T1 (Tvíheimr readiness).

Pure model work: no judgment, no resolution. These components carry the
tactically current picture Tvíheimr's presence will read — whether an
entity is in combat, whom it is engaged with, how threatening it is
graded (with source and age, so staleness is never hidden), and where
its combat stands in the begun / joined / turned / ended lifecycle.

They compose with, and do not replace, the Phase D1 combat components
(``combat.py``): Combatant/Engagement/Threat remain the remembered-fight
truth; these are the small, fast tactical snapshot attached directly to
the entities they describe.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import ClassVar, Literal

from pydantic import Field

from wyrdforge.ecs.component import Component, register_component
from wyrdforge.models.common import StrictModel


def _now() -> datetime:
    return datetime.now(timezone.utc)


ThreatGrade = Literal["none", "low", "guarded", "high", "severe", "critical"]
_GRADE_ORDER: dict[str, int] = {
    "none": 0, "low": 1, "guarded": 2, "high": 3, "severe": 4, "critical": 5,
}

CombatPhase = Literal["begun", "joined", "turned", "ended"]
_PHASE_TRANSITIONS: dict[str, frozenset[str]] = {
    "begun": frozenset({"joined", "turned", "ended"}),
    "joined": frozenset({"turned", "ended"}),
    "turned": frozenset({"joined", "turned", "ended"}),
    "ended": frozenset(),
}


def grade_rank(grade: str) -> int:
    return _GRADE_ORDER[grade]


@register_component
class InCombatComponent(Component):
    """Whether this entity is currently in combat."""

    _type_key: ClassVar[str] = "in_combat"
    component_type: Literal["in_combat"] = "in_combat"

    active: bool = False
    engagement_id: str | None = None
    entered_at: datetime | None = None

    def enter(self, engagement_id: str | None = None, *, at: datetime | None = None) -> None:
        self.active = True
        if engagement_id is not None:
            self.engagement_id = engagement_id
        self.entered_at = at if at is not None else _now()
        self.touch()

    def leave(self) -> None:
        self.active = False
        self.engagement_id = None
        self.entered_at = None
        self.touch()


@register_component
class EngagedWithComponent(Component):
    """Entity refs this entity is directly engaged with."""

    _type_key: ClassVar[str] = "engaged_with"
    component_type: Literal["engaged_with"] = "engaged_with"

    target_ids: list[str] = Field(default_factory=list)
    engagement_id: str | None = None

    def engage(self, target_id: str) -> bool:
        if target_id == self.entity_id:
            raise ValueError("an entity cannot be engaged with itself")
        if target_id in self.target_ids:
            return False
        self.target_ids.append(target_id)
        self.touch()
        return True

    def disengage(self, target_id: str) -> bool:
        if target_id in self.target_ids:
            self.target_ids.remove(target_id)
            self.touch()
            return True
        return False

    def clear(self) -> None:
        self.target_ids = []
        self.touch()

    def is_engaged_with(self, target_id: str) -> bool:
        return target_id in self.target_ids


@register_component
class ThreatLevelComponent(Component):
    """Graded threat for this entity, with source and age.

    Age is derived from ``assessed_at`` at query time, never stored, so a
    stale grade can never masquerade as a fresh one.
    """

    _type_key: ClassVar[str] = "threat_level"
    component_type: Literal["threat_level"] = "threat_level"

    grade: ThreatGrade = "none"
    source: str = ""
    assessed_at: datetime = Field(default_factory=_now)

    def set_grade(self, grade: ThreatGrade, *, source: str, at: datetime | None = None) -> None:
        self.grade = grade
        self.source = source
        self.assessed_at = at if at is not None else _now()
        self.touch()

    def age_at(self, now: datetime) -> timedelta:
        return now - self.assessed_at

    def is_at_least(self, grade: ThreatGrade) -> bool:
        return grade_rank(self.grade) >= grade_rank(grade)


class PhaseMark(StrictModel):
    phase: CombatPhase
    at: datetime
    note: str = ""


@register_component
class CombatPhaseComponent(Component):
    """Where this entity's combat stands: begun / joined / turned / ended."""

    _type_key: ClassVar[str] = "combat_phase"
    component_type: Literal["combat_phase"] = "combat_phase"

    phase: CombatPhase = "begun"
    engagement_id: str | None = None
    changed_at: datetime = Field(default_factory=_now)
    history: list[PhaseMark] = Field(default_factory=list)

    def can_transition_to(self, new_phase: str) -> bool:
        if not self.history:
            return True
        return new_phase in _PHASE_TRANSITIONS[self.phase]

    def transition_to(self, new_phase: CombatPhase, *, at: datetime | None = None, note: str = "") -> None:
        if self.history and new_phase == self.phase:
            return
        if not self.can_transition_to(new_phase):
            raise ValueError(f"combat phase cannot move {self.phase} -> {new_phase}")
        when = at if at is not None else _now()
        self.phase = new_phase
        self.changed_at = when
        self.history.append(PhaseMark(phase=new_phase, at=when, note=note))
        self.touch()

    @property
    def is_ended(self) -> bool:
        return self.phase == "ended"
