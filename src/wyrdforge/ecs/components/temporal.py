"""Temporal ECS components — time awareness for the WYRD world model.

A world model without time is a photograph; with time it becomes a saga.
These components give every entity and event a place in world-time, using
the three threads of wyrd:

- **Urðr** — that which has become (past: the anchor ended before now)
- **Verðandi** — that which is becoming (present: the anchor holds now)
- **Skuld** — that which shall become (future: the anchor begins after now)

Design rules:
- Nothing inside the simulation reads wall-clock time. The deterministic
  :class:`WorldClock` is the world's "now"; systems advance it per tick.
- Anchors carry validity windows (``valid_from`` / ``valid_until``), so
  the oracle can answer "what is true *now*" versus "what was true *then*".
- Fully deterministic and ECS-compatible — no LLM involvement.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import ClassVar, Literal

from pydantic import Field

from wyrdforge.ecs.component import Component, register_component
from wyrdforge.models.common import StrictModel


def _now() -> datetime:
    return datetime.now(timezone.utc)


Tense = Literal["urdhr", "verdhandi", "skuld"]


@register_component
class TemporalAnchorComponent(Component):
    """Anchors an entity, fact, or event in world-time.

    Attributes:
        valid_from:  World-time from which this truth holds.
        valid_until: World-time until which it holds. ``None`` = open-ended
                     (still true as far as the world knows).
        observed_at: World-time when the world learned of it (distinct from
                     when it became true — a saga can learn of the past late).
        label:      Short human tag, e.g. "reign of King Hrolf".
    """

    _type_key: ClassVar[str] = "temporal_anchor"
    component_type: Literal["temporal_anchor"] = "temporal_anchor"

    valid_from: datetime = Field(default_factory=_now)
    valid_until: datetime | None = None
    observed_at: datetime = Field(default_factory=_now)
    label: str = ""

    def is_current(self, now: datetime) -> bool:
        """True when this anchor holds at world-time ``now``."""
        if self.valid_from > now:
            return False
        if self.valid_until is not None and self.valid_until <= now:
            return False
        return True

    def has_expired(self, now: datetime) -> bool:
        """True when the anchor's truth has fully passed."""
        return self.valid_until is not None and self.valid_until <= now

    def tense_at(self, now: datetime) -> Tense:
        """Which thread of wyrd this anchor sits on at world-time ``now``."""
        if self.valid_from > now:
            return "skuld"
        if self.has_expired(now):
            return "urdhr"
        return "verdhandi"

    def duration(self) -> timedelta | None:
        """How long the truth holds, or None if open-ended."""
        if self.valid_until is None:
            return None
        return self.valid_until - self.valid_from


class WorldClock(StrictModel):
    """Deterministic world-time.

    The world's "now". Systems advance it per tick via :meth:`advance`;
    nothing inside the simulation may substitute wall-clock time for it.
    """

    now: datetime = Field(default_factory=_now)

    def advance(self, seconds: float) -> datetime:
        """Move world-time forward. Negative deltas are rejected: wyrd does
        not rewind — to revisit the past, query anchors, don't move the clock."""
        if seconds < 0:
            raise ValueError("WorldClock cannot rewind; query TemporalAnchors for the past")
        self.now = self.now + timedelta(seconds=seconds)
        return self.now

    def set(self, when: datetime) -> datetime:
        """Set world-time explicitly (scenario setup / save-load only)."""
        self.now = when
        return self.now


def current_anchors(anchors: list[TemporalAnchorComponent], now: datetime) -> list[TemporalAnchorComponent]:
    """Return only the anchors that hold at world-time ``now``."""
    return [a for a in anchors if a.is_current(now)]
