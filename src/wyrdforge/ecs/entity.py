from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _new_id() -> str:
    return str(uuid.uuid4())


@dataclass
class Entity:
    """A unique node in the world — identified by UUID, labelled by tags."""

    entity_id: str = field(default_factory=_new_id)
    tags: set[str] = field(default_factory=set)
    active: bool = True
    created_at: datetime = field(default_factory=_now)
    updated_at: datetime = field(default_factory=_now)

    def add_tag(self, tag: str) -> None:
        self.tags.add(tag)
        self.updated_at = _now()

    def remove_tag(self, tag: str) -> None:
        self.tags.discard(tag)
        self.updated_at = _now()

    def has_tag(self, tag: str) -> bool:
        return tag in self.tags

    def deactivate(self) -> None:
        self.active = False
        self.updated_at = _now()

    def reactivate(self) -> None:
        self.active = True
        self.updated_at = _now()

    def __repr__(self) -> str:
        tags_str = ", ".join(sorted(self.tags)) if self.tags else "—"
        return f"Entity({self.entity_id[:8]}…, tags=[{tags_str}], active={self.active})"
