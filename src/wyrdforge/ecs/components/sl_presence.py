from __future__ import annotations

from datetime import datetime
from typing import ClassVar, Literal

from wyrdforge.ecs.component import Component, register_component


@register_component
class SLPresenceComponent(Component):
    """Second Life presence flags mirrored from protocol events."""

    _type_key: ClassVar[str] = "sl_presence"
    component_type: Literal["sl_presence"] = "sl_presence"

    online: bool = False
    in_region: bool = False
    idle: bool = False
    afk: bool = False
    typing: bool = False
    muted: bool = False
    blocked: bool = False
    last_seen_at: datetime | None = None
