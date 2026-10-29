"""BifrostBridge — abstract base class for all engine adapters.

Every bridge wraps the same WYRD stack and exposes engine-appropriate
surface area. Concrete bridges override ``query`` and optionally
``event`` to push world events back into the ECS.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from wyrdforge.hardening.input_validation import (
    InputValidationError,
    validate_event_envelope,
)

#: JSON-shaped scalar types (None is checked separately). Tuples count
#: as array-shaped, matching the envelope walk's treatment.
_JSON_SCALARS = (str, int, float, bool)


def _require_json_shaped(payload: dict) -> None:
    """Refuse any non-JSON-shaped value inside *payload* (Phase C3).

    The envelope check bounds size and depth, but its size measure
    (``json.dumps(..., default=str)``) tolerates exotic values — an
    ``object()`` or a ``set`` would serialize as a repr string. At
    the in-process Bifrost boundary that tolerance is a hole: bridge
    payloads must be plain JSON data (dicts with string keys, lists /
    tuples, str / int / float / bool, None). The walk is iterative
    and shares the envelope's depth bound, since the envelope check
    has already refused over-deep payloads before this runs.
    """
    stack: list = [payload]
    while stack:
        value = stack.pop()
        if value is None or isinstance(value, _JSON_SCALARS):
            continue
        if isinstance(value, dict):
            for key, child in value.items():
                if not isinstance(key, str):
                    raise InputValidationError(
                        "payload",
                        f"object keys must be strings, got {type(key).__name__}",
                    )
                stack.append(child)
            continue
        if isinstance(value, (list, tuple)):
            stack.extend(value)
            continue
        raise InputValidationError(
            "payload",
            f"value of type {type(value).__name__} is not JSON-shaped",
        )


class BifrostBridge(ABC):
    """Abstract base for Bifrost engine adapters.

    Subclasses must implement :meth:`query`.  Optionally override
    :meth:`push_event` to accept incoming world events from the engine.
    """

    # ------------------------------------------------------------------
    # Required
    # ------------------------------------------------------------------

    @abstractmethod
    def query(
        self,
        persona_id: str,
        user_input: str,
        **kwargs: Any,
    ) -> str:
        """Send a query to the WYRD stack and return the response text.

        Args:
            persona_id:  ID of the active character/persona.
            user_input:  Player or engine text input.
            **kwargs:    Bridge-specific overrides (location_id, bond_id, …).

        Returns:
            The character's response as a plain string.
        """

    # ------------------------------------------------------------------
    # Optional
    # ------------------------------------------------------------------

    @staticmethod
    def validate_event(event_type: Any, payload: Any) -> dict:
        """Validate one bridge event at the Bifrost boundary (Phase C3).

        The shared envelope check every ingest door uses
        (``hardening.input_validation.validate_event_envelope``):
        ``event_type`` must be a non-empty string within the length
        bound, ``payload`` must be a dict whose serialized form fits
        the byte cap and whose nesting fits the depth cap — which
        also refuses non-JSON-shaped values (objects, sets, cycles),
        since their serialized size is unmeasurable. Raises
        ``InputValidationError`` (a ``ValueError``) naming the field;
        fail closed, nothing is written for a refused event.

        Returns the payload unchanged. Whether an event TYPE is
        known is the concrete bridge's own policy, exactly as at the
        HTTP door.
        """
        validate_event_envelope(event_type, payload)
        _require_json_shaped(payload)
        return payload

    def push_event(self, event_type: str, payload: dict[str, Any]) -> None:
        """Push a world event from the external engine into WYRD.

        Default implementation validates the event (Phase C3 — the
        Bifrost boundary fails closed on malformed input) and is
        otherwise a no-op.  Override to integrate engine events with
        the ECS World or WritebackEngine; overrides MUST route
        through :meth:`validate_event` first, as
        ``PythonRPGBridge.push_event`` does.

        Args:
            event_type:  Short string label (e.g. ``"location_change"``).
            payload:     Arbitrary data dict from the engine.
        """
        self.validate_event(event_type, payload)

    def teardown(self) -> None:
        """Release any resources held by the bridge.

        Called when the bridge is no longer needed.  Default is a no-op.
        """
