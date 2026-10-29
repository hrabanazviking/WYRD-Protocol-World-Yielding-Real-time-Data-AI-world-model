from __future__ import annotations

from typing import ClassVar, Literal

from wyrdforge.ecs.component import Component, register_component


@register_component
class SLObjectComponent(Component):
    """Second Life object state mirrored from protocol events."""

    _type_key: ClassVar[str] = "sl_object"
    component_type: Literal["sl_object"] = "sl_object"

    object_uuid: str = ""
    owner_id: str = ""
    creator_id: str = ""
    kind: str = "prim"
    touchable: bool = False
    sittable: bool = False
    script_detected: bool = False
