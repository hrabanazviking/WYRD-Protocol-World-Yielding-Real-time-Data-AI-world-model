from __future__ import annotations

from typing import ClassVar, Literal

from pydantic import Field

from wyrdforge.ecs.component import Component, register_component


@register_component
class SLAvatarProfileComponent(Component):
    """Protocol/profile facts about a Second Life avatar.

    Only fields actually exposed by a profile or protocol event belong here;
    felt relationships belong in the BondGraph, not in this component.
    """

    _type_key: ClassVar[str] = "sl_avatar_profile"
    component_type: Literal["sl_avatar_profile"] = "sl_avatar_profile"

    avatar_uuid: str = ""
    legacy_name: str = ""
    display_name: str = ""
    account_created_on: str = ""
    payment_info_on_file: bool | None = None
    group_ids: list[str] = Field(default_factory=list)
    scripted_agent: bool = False
