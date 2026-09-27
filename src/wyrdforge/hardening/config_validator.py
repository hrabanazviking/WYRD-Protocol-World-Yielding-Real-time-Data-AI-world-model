"""config_validator.py — canonical world-config schema validator + env-var coercer.

Validates world YAML configs on load against the schema the loader and
the canonical world files actually use, and coerces environment variable
overrides to the correct Python types with clear error messages.

Canonical schema (Track 1, P1):

    world_id, world_name, [description], [zones]
      zone:        id, name, [description], [regions]
        region:   id, name, [description], [locations]
          location:     id, name, [description], [sublocations]
            sublocation: id, name, [description]

Unknown fields are hard errors naming the dotted path — a typo'd key
that silently defaulted is how a world loses a zone unnoticed.

Usage::

    from wyrdforge.hardening.config_validator import (
        validate_world_config,
        coerce_env,
        ConfigValidationError,
    )

    # Validate a loaded YAML dict
    try:
        validate_world_config(config_dict)
    except ConfigValidationError as e:
        print(f"Bad config at {e.field}: {e.reason}")

    # Type-safe env var reading
    port = coerce_env("WYRD_PORT", int, default=8765)
    debug = coerce_env("WYRD_DEBUG", bool, default=False)
"""
from __future__ import annotations

import logging
import os
from typing import Any, Optional, Type, TypeVar

from wyrdforge.hardening.input_validation import (
    MAX_CHILDREN_PER_LEVEL,
    MAX_DESCRIPTION_CHARS,
    MAX_ID_CHARS,
    InputValidationError,
    check_id,
    check_string,
)

logger = logging.getLogger(__name__)

T = TypeVar("T")


class ConfigValidationError(InputValidationError):
    """Raised when a world config dict fails schema validation.

    Kept for backward compatibility — it *is* an
    :class:`InputValidationError` naming the offending field.
    """

    def __init__(self, message: str, field: Optional[str] = None) -> None:
        self.message = message
        super().__init__(field or "$", message)


# ---------------------------------------------------------------------------
# Canonical world config schema (Track 1, P1)
# ---------------------------------------------------------------------------

#: (level_key, children_key) — sublocations are the leaves.
_LEVELS: tuple[tuple[str, str | None], ...] = (
    ("zones", "regions"),
    ("regions", "locations"),
    ("locations", "sublocations"),
    ("sublocations", None),
)

_CHILDREN_OF = dict(_LEVELS)


def _missing(path: str, key: str) -> None:
    raise InputValidationError(f"{path}.{key}", "required field is missing")


def _validate_node(node: Any, *, path: str, children_key: str | None) -> None:
    """Validate one zone/region/location/sublocation node."""
    if not isinstance(node, dict):
        raise InputValidationError(
            path, f"must be a mapping, got {type(node).__name__}"
        )
    if "id" in node:
        check_id(node["id"], field=f"{path}.id")
    else:
        _missing(path, "id")
    if "name" in node:
        check_string(node["name"], field=f"{path}.name",
                     max_len=MAX_ID_CHARS, allow_empty=False)
    else:
        _missing(path, "name")
    if "description" in node:
        check_string(node["description"], field=f"{path}.description",
                     max_len=MAX_DESCRIPTION_CHARS)
    allowed = {"id", "name", "description"}
    if children_key is not None:
        allowed.add(children_key)
    for key in node:
        if key not in allowed:
            raise InputValidationError(
                f"{path}.{key}",
                f"unknown field {key!r} (expected one of {sorted(allowed)})",
            )
    if children_key is not None and children_key in node:
        children = node[children_key]
        if not isinstance(children, list):
            raise InputValidationError(
                f"{path}.{children_key}",
                f"must be a list, got {type(children).__name__}",
            )
        if len(children) > MAX_CHILDREN_PER_LEVEL:
            raise InputValidationError(
                f"{path}.{children_key}",
                f"exceeds {MAX_CHILDREN_PER_LEVEL} entries ({len(children)})",
            )
        for i, child in enumerate(children):
            _validate_node(
                child,
                path=f"{path}.{children_key}[{i}]",
                children_key=_CHILDREN_OF[children_key],
            )


def validate_world_config(config: dict[str, Any]) -> dict[str, Any]:
    """Validate a world config dictionary against the canonical schema.

    Args:
        config: Raw dict loaded from a world YAML file.

    Returns:
        The validated config dict (unchanged on success).

    Raises:
        InputValidationError: On unknown fields, wrong types, missing
            required fields (``world_id``, ``world_name``, every
            node's ``id``/``name``), or bound violations. The error
            names the dotted field path.

    Note: a *direct* call requires ``world_id`` and ``world_name``.
    The loader normalizes its historical defaults (filename stem,
    ``world_name`` falling back to ``world_id``) onto a copy before
    calling this, so existing valid worlds keep loading.
    """
    try:
        return _validate_world_config(config)
    except InputValidationError as exc:
        if isinstance(exc, ConfigValidationError):
            raise
        # The shared checkers raise the base class; the config door
        # speaks ConfigValidationError (which *is* an
        # InputValidationError — callers of either name are satisfied).
        raise ConfigValidationError(exc.reason, field=exc.field) from exc


def _validate_world_config(config: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(config, dict):
        raise InputValidationError(
            "$", f"world config must be a mapping, got {type(config).__name__}"
        )
    if "world_id" not in config:
        _missing("$", "world_id")
    check_id(config["world_id"], field="world_id")
    if "world_name" not in config:
        _missing("$", "world_name")
    check_string(config["world_name"], field="world_name",
                 max_len=MAX_ID_CHARS, allow_empty=False)

    allowed_top = {"world_id", "world_name", "description", "zones"}
    for key in config:
        if key not in allowed_top:
            raise InputValidationError(
                f"$.{key}",
                f"unknown field {key!r} (expected one of {sorted(allowed_top)})",
            )
    if "description" in config:
        check_string(config["description"], field="$.description",
                     max_len=MAX_DESCRIPTION_CHARS)
    if "zones" in config:
        zones = config["zones"]
        if not isinstance(zones, list):
            raise InputValidationError(
                "$.zones", f"must be a list, got {type(zones).__name__}"
            )
        if len(zones) > MAX_CHILDREN_PER_LEVEL:
            raise InputValidationError(
                "$.zones",
                f"exceeds {MAX_CHILDREN_PER_LEVEL} entries ({len(zones)})",
            )
        for i, zone in enumerate(zones):
            _validate_node(zone, path=f"$.zones[{i}]",
                           children_key="regions")
    return config


# ---------------------------------------------------------------------------
# Environment variable coercion
# ---------------------------------------------------------------------------

_BOOL_TRUE  = {"1", "true", "yes", "on"}
_BOOL_FALSE = {"0", "false", "no", "off"}


def coerce_env(
    key: str,
    type_fn: Type[T],
    *,
    default: T,
    required: bool = False,
) -> T:
    """Read an environment variable and coerce it to *type_fn*.

    Supported types: ``str``, ``int``, ``float``, ``bool``.

    Args:
        key:      Environment variable name.
        type_fn:  Target Python type.
        default:  Value to return when the variable is not set.
        required: If True, raise :class:`ConfigValidationError` when not set.

    Returns:
        The coerced value, or *default* if the variable is absent.

    Raises:
        ConfigValidationError: If *required* and the variable is absent, or if
                               the value cannot be coerced to *type_fn*.
    """
    raw = os.environ.get(key)

    if raw is None:
        if required:
            raise ConfigValidationError(
                f"Required environment variable '{key}' is not set", field=key
            )
        return default

    raw = raw.strip()

    try:
        if type_fn is bool:
            if raw.lower() in _BOOL_TRUE:
                return True  # type: ignore[return-value]
            if raw.lower() in _BOOL_FALSE:
                return False  # type: ignore[return-value]
            raise ValueError(f"Cannot interpret {raw!r} as bool")
        if type_fn is int:
            return int(raw)  # type: ignore[return-value]
        if type_fn is float:
            return float(raw)  # type: ignore[return-value]
        return type_fn(raw)  # type: ignore[return-value]
    except (ValueError, TypeError) as exc:
        logger.warning(
            "Environment variable '%s=%s' cannot be coerced to %s: %s — using default %r",
            key, raw, type_fn.__name__, exc, default,
        )
        return default


def report_active_config(prefix: str = "WYRD_") -> dict[str, str]:
    """Return all environment variables whose names start with *prefix*.

    Useful for logging the effective runtime configuration.

    Args:
        prefix: Variable name prefix to filter on.

    Returns:
        Dict of matching env var names → values.
    """
    return {k: v for k, v in os.environ.items() if k.startswith(prefix)}
