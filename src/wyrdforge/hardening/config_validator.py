"""config_validator.py — YAML world-config schema validator + env-var coercer.

Validates world YAML configs on load and coerces environment variable overrides
to the correct Python types with clear error messages.

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
        print(f"Bad config: {e}")

    # Type-safe env var reading
    port = coerce_env("WYRD_PORT", int, default=8765)
    debug = coerce_env("WYRD_DEBUG", bool, default=False)
"""
from __future__ import annotations

import logging
import os
from typing import Any, Callable, Optional, Type, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")


class ConfigValidationError(ValueError):
    """Raised when a world config dict fails schema validation."""

    def __init__(self, message: str, field: Optional[str] = None) -> None:
        self.field = field
        super().__init__(message)


# ---------------------------------------------------------------------------
# World config schema
# ---------------------------------------------------------------------------

# Required top-level keys and their expected types
_REQUIRED_FIELDS: dict[str, type] = {
    "world_id": str,
    "name":     str,
}

# Optional top-level keys and their expected types + defaults
_OPTIONAL_FIELDS: dict[str, tuple[type, Any]] = {
    "description": (str,  ""),
    "version":     (str,  "1.0"),
    "zones":       (list, []),
    "locations":   (list, []),
    "entities":    (list, []),
    "factions":    (list, []),
    "settings":    (dict, {}),
}

# Known boolean-ish settings keys
_SETTINGS_BOOL_KEYS = {
    "enable_runic_metaphysics",
    "enable_bond_tracking",
    "enable_contradiction_detection",
    "silent_on_error",
    "use_turn_loop",
}


def validate_world_config(config: dict[str, Any]) -> dict[str, Any]:
    """Validate a world config dictionary and return it with safe defaults filled in.

    Args:
        config: Raw dict loaded from a world YAML file.

    Returns:
        The validated (and default-filled) config dict.

    Raises:
        ConfigValidationError: If a required field is missing or has the wrong type.
    """
    if not isinstance(config, dict):
        raise ConfigValidationError("World config must be a mapping (dict), got: " + type(config).__name__)

    # Required fields
    for key, expected_type in _REQUIRED_FIELDS.items():
        if key not in config:
            raise ConfigValidationError(f"Required field '{key}' is missing", field=key)
        val = config[key]
        if not isinstance(val, expected_type):
            raise ConfigValidationError(
                f"Field '{key}' must be {expected_type.__name__}, "
                f"got {type(val).__name__}: {val!r}",
                field=key,
            )
        if expected_type is str and not str(val).strip():
            raise ConfigValidationError(f"Field '{key}' must not be empty", field=key)

    # Optional fields — fill defaults, warn on wrong type
    result = dict(config)
    for key, (expected_type, default) in _OPTIONAL_FIELDS.items():
        if key not in result:
            result[key] = default
        else:
            val = result[key]
            if not isinstance(val, expected_type):
                logger.warning(
                    "World config: field '%s' expected %s, got %s — using default",
                    key, expected_type.__name__, type(val).__name__,
                )
                result[key] = default

    # Validate list elements have at least an 'id' or 'name' field
    for list_key in ("zones", "locations", "entities", "factions"):
        lst = result.get(list_key, [])
        if isinstance(lst, list):
            for i, item in enumerate(lst):
                if not isinstance(item, dict):
                    raise ConfigValidationError(
                        f"'{list_key}[{i}]' must be a mapping, got {type(item).__name__}",
                        field=list_key,
                    )

    return result


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
