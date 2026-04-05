"""BifrostBridge — abstract base class for all engine adapters.

Every bridge wraps the same WYRD stack and exposes engine-appropriate
surface area. Concrete bridges override ``query`` and optionally
``event`` to push world events back into the ECS.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


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

    def push_event(self, event_type: str, payload: dict[str, Any]) -> None:
        """Push a world event from the external engine into WYRD.

        Default implementation is a no-op.  Override to integrate
        engine events with the ECS World or WritebackEngine.

        Args:
            event_type:  Short string label (e.g. ``"location_change"``).
            payload:     Arbitrary data dict from the engine.
        """

    def teardown(self) -> None:
        """Release any resources held by the bridge.

        Called when the bridge is no longer needed.  Default is a no-op.
        """
