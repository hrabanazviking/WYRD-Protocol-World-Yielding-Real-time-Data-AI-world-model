from __future__ import annotations

from typing import ClassVar, Literal

from wyrdforge.ecs.component import Component, register_component


@register_component
class SLPositionComponent(Component):
    """Second Life position state for an avatar or object.

    Positions are simulator-reported values. ``position`` is region-local;
    ``global_position`` is present only when the source event supplies it.
    """

    _type_key: ClassVar[str] = "sl_position"
    component_type: Literal["sl_position"] = "sl_position"

    region_id: str = ""
    parcel_id: str | None = None
    position: tuple[float, float, float] = (0.0, 0.0, 0.0)
    global_position: tuple[float, float, float] | None = None
    rotation: tuple[float, float, float, float] = (0.0, 0.0, 0.0, 1.0)
    sitting_on_object_id: str | None = None
