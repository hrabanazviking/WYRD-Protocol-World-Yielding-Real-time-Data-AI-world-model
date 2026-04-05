from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, ClassVar

from pydantic import Field

from wyrdforge.models.common import StrictModel


def _now() -> datetime:
    return datetime.now(timezone.utc)


class Component(StrictModel):
    """Base class for all ECS components.

    Subclasses must override `component_type` with a Literal value.
    Register each subclass with @register_component so the World can
    deserialize components from storage by type name.
    """

    component_type: str
    entity_id: str
    schema_version: str = "1.0"
    created_at: datetime = Field(default_factory=_now)
    updated_at: datetime = Field(default_factory=_now)

    # Subclasses declare their own type key here for the registry
    _type_key: ClassVar[str] = ""

    def touch(self) -> None:
        """Update the updated_at timestamp."""
        self.updated_at = _now()


# ---------------------------------------------------------------------------
# Component registry — maps type-name strings → Component subclasses
# ---------------------------------------------------------------------------

_REGISTRY: dict[str, type[Component]] = {}


def register_component(cls: type[Component]) -> type[Component]:
    """Class decorator that registers a Component subclass by its type key."""
    key = cls._type_key or cls.model_fields.get("component_type", None)
    if key is None:
        raise TypeError(f"{cls.__name__} must set _type_key or have a Literal component_type default")
    if isinstance(key, str):
        _REGISTRY[key] = cls
    return cls


def get_component_class(type_name: str) -> type[Component]:
    """Look up a Component subclass by type name."""
    if type_name not in _REGISTRY:
        raise KeyError(f"No component registered for type '{type_name}'. Did you @register_component it?")
    return _REGISTRY[type_name]


def registered_types() -> list[str]:
    """Return all registered component type names."""
    return list(_REGISTRY.keys())


def deserialize_component(data: dict[str, Any]) -> Component:
    """Reconstruct a Component from a raw dict (e.g., from JSON storage)."""
    type_name = data.get("component_type")
    if not type_name:
        raise ValueError("Cannot deserialize component: missing 'component_type' field")
    cls = get_component_class(type_name)
    return cls.model_validate(data)
