from __future__ import annotations

from typing import ClassVar, Literal

from wyrdforge.ecs.component import Component, register_component


@register_component
class SLRegionComponent(Component):
    """Second Life region/simulator state."""

    _type_key: ClassVar[str] = "sl_region"
    component_type: Literal["sl_region"] = "sl_region"

    region_uuid: str = ""
    estate_id: int | None = None
    estate_name: str = ""
    maturity_rating: str = ""
    region_handle: int | None = None
    grid_x: int | None = None
    grid_y: int | None = None
    time_dilation: float | None = None
    simulator_fps: float | None = None
    agent_count: int = 0
    damage_allowed: bool | None = None


@register_component
class SLParcelComponent(Component):
    """Second Life parcel state."""

    _type_key: ClassVar[str] = "sl_parcel"
    component_type: Literal["sl_parcel"] = "sl_parcel"

    region_id: str = ""
    parcel_local_id: int = 0
    owner_id: str = ""
    group_id: str = ""
    area_sqm: int = 0
    category: str = ""
    voice_enabled: bool | None = None
    public_access: bool | None = None
    damage_allowed: bool | None = None
