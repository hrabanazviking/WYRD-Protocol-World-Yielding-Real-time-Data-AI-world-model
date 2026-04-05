from __future__ import annotations

from wyrdforge.ecs.components.identity import StatusComponent
from wyrdforge.ecs.system import System
from wyrdforge.ecs.world import World


class StateTransitionSystem(System):
    """Processes queued state transition requests for entities.

    Other systems or external code enqueue transitions via
    `request_transition(entity_id, new_state)`. On the next tick
    this system applies them and calls any registered callbacks.
    """

    component_interests = ["status"]

    def __init__(self) -> None:
        self._queue: list[tuple[str, str]] = []           # (entity_id, new_state)
        self._callbacks: list[callable] = []              # (entity_id, old_state, new_state) → None  # type: ignore[type-arg]

    def request_transition(self, entity_id: str, new_state: str) -> None:
        self._queue.append((entity_id, new_state))

    def on_transition(self, callback: callable) -> None:                # type: ignore[type-arg]
        """Register a callback: fn(entity_id, old_state, new_state)."""
        self._callbacks.append(callback)

    def tick(self, world: World, delta_t: float) -> None:
        pending = list(self._queue)
        self._queue.clear()
        for entity_id, new_state in pending:
            status = world.get_component(entity_id, "status")
            if status and isinstance(status, StatusComponent):
                old_state = status.state
                if old_state != new_state:
                    status.state = new_state
                    status.touch()
                    for cb in self._callbacks:
                        cb(entity_id, old_state, new_state)
