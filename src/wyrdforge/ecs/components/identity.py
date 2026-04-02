from __future__ import annotations

from typing import ClassVar, Literal

from pydantic import Field

from wyrdforge.ecs.component import Component, register_component


@register_component
class NameComponent(Component):
    """The name(s) by which an entity is known."""

    _type_key: ClassVar[str] = "name"
    component_type: Literal["name"] = "name"

    name: str
    aliases: list[str] = Field(default_factory=list)
    known_to: list[str] = Field(default_factory=list)  # entity_ids that know this name


@register_component
class DescriptionComponent(Component):
    """Human-readable descriptions of an entity."""

    _type_key: ClassVar[str] = "description"
    component_type: Literal["description"] = "description"

    short_desc: str = ""
    long_desc: str = ""
    tags: list[str] = Field(default_factory=list)  # semantic labels for retrieval


@register_component
class StatusComponent(Component):
    """Current state flags for an entity."""

    _type_key: ClassVar[str] = "status"
    component_type: Literal["status"] = "status"

    state: str = "idle"                              # primary state label
    flags: dict[str, bool] = Field(default_factory=dict)  # arbitrary bool flags
    notes: str = ""                                  # free-form status note
