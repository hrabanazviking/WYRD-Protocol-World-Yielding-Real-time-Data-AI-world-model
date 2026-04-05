from __future__ import annotations

from wyrdforge.ecs.components.spatial import SpatialComponent
from wyrdforge.ecs.system import System
from wyrdforge.ecs.world import World


class PresenceSystem(System):
    """Tracks which entities are co-located.

    On each tick, builds a snapshot of location → [entity_ids] so that
    other systems and the Oracle can quickly answer "who is here?".
    """

    component_interests = ["spatial"]

    def __init__(self) -> None:
        # location_id → set of entity_ids currently there
        self.presence_map: dict[str, set[str]] = {}

    def tick(self, world: World, delta_t: float) -> None:
        self.presence_map.clear()
        for entity, comp in world.iter_components("spatial"):
            if isinstance(comp, SpatialComponent):
                loc = comp.most_specific_id()
                if loc:
                    self.presence_map.setdefault(loc, set()).add(entity.entity_id)

    def entities_at(self, location_id: str) -> set[str]:
        """Return entity_ids currently at a given location."""
        return self.presence_map.get(location_id, set())

    def location_of(self, entity_id: str) -> str | None:
        for loc_id, entities in self.presence_map.items():
            if entity_id in entities:
                return loc_id
        return None
