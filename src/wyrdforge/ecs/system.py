from __future__ import annotations

from abc import ABC, abstractmethod

from wyrdforge.ecs.world import World


class System(ABC):
    """Base class for all ECS systems.

    A System processes entities that have specific component types on each tick.
    Systems read and write component data but never create or destroy entities
    directly — use World methods for structural changes.
    """

    # Declare which component types this system is interested in.
    # Used by the WorldRunner to skip ticking if no matching entities exist.
    component_interests: list[str] = []

    @abstractmethod
    def tick(self, world: World, delta_t: float) -> None:
        """Process all relevant entities for one simulation step.

        Args:
            world:   The ECS world to operate on.
            delta_t: Time elapsed since last tick, in seconds.
        """
        ...

    def on_attach(self, world: World) -> None:
        """Called when this system is added to a WorldRunner. Override if needed."""

    def on_detach(self, world: World) -> None:
        """Called when this system is removed from a WorldRunner. Override if needed."""


class WorldRunner:
    """Manages a list of systems and drives the tick loop."""

    def __init__(self, world: World) -> None:
        self._world = world
        self._systems: list[System] = []

    def add_system(self, system: System) -> None:
        self._systems.append(system)
        system.on_attach(self._world)

    def remove_system(self, system: System) -> None:
        self._systems.remove(system)
        system.on_detach(self._world)

    def tick(self, delta_t: float = 1.0) -> None:
        """Run one tick across all systems in registration order."""
        for system in self._systems:
            system.tick(self._world, delta_t)

    def tick_n(self, n: int, delta_t: float = 1.0) -> None:
        """Run n ticks."""
        for _ in range(n):
            self.tick(delta_t)
