"""Grid-hash (uniform spatial hash) index over PositionComponents.

Phase B3 — the index behind the Oracle's radius / nearest / distance
queries.

Consistency design — why the index is built at query time
----------------------------------------------------------
Phase B2's central lesson: component fields are mutated directly
(``HealthComponent.take_damage()`` never touches a World method), so
any index *maintained* by World methods can silently go stale the
moment a caller assigns ``pos.x = 5.0`` directly. A stale spatial
index is worse than no index: a radius query would silently miss an
entity that moved into range.

This index therefore cannot go stale BY CONSTRUCTION: it is built
from the live ``PositionComponent`` objects at query time, inside the
caller's ``world.lock`` hold (the Oracle holds the lock across a
whole query — Phase B1 discipline), used for that one query, and
discarded. Every mutation path — World create/remove, component
add/replace/remove, ``World.set_position``, and direct field
assignment — is reflected in the very next query, because the next
query rebuilds from the components themselves. There is no second
source of positional truth to diverge (the same doctrine as the
Verdandi mirror: a pure projection, rebuilt from its inputs).

Cost, honestly: building is O(P) over positioned entities only (not
over the world), a dict insert per entity. What the grid buys is the
distance math: a radius query distance-checks only entities in cells
intersecting the query sphere instead of every positioned entity,
and a nearest query expands by doubling radii over grid buckets
instead of sorting the world. ``candidates_examined`` on the index
records how many exact distance checks the last query performed, so
tests (and operators) can see the pruning is real.
"""
from __future__ import annotations

import math
from typing import Iterable

from wyrdforge.ecs.components.spatial import PositionComponent

#: Default grid cell size, in metres. 10 m suits human-scale scenes
#: (rooms, region parcels); callers with other scales pass their own.
DEFAULT_CELL_SIZE = 10.0

_CellKey = tuple[int, int, int, "str | None"]


class SpatialGridIndex:
    """A uniform grid hash over a snapshot of positioned entities.

    Built from ``(entity_id, PositionComponent)`` pairs; the pairs are
    read once at build time, so the index is a consistent snapshot of
    the positions as they were when it was built (the Oracle builds
    it while holding ``world.lock``, so that moment is a real,
    lock-defined moment of the world).
    """

    def __init__(
        self,
        entries: Iterable[tuple[str, PositionComponent]],
        *,
        cell_size: float = DEFAULT_CELL_SIZE,
    ) -> None:
        if cell_size <= 0:
            raise ValueError(f"cell_size must be positive, got {cell_size}")
        self._cell_size = float(cell_size)
        # cell key -> [(entity_id, x, y, z), ...]
        self._cells: dict[_CellKey, list[tuple[str, float, float, float]]] = {}
        # entity_id -> (x, y, z, frame_id) for direct distance lookups
        self._points: dict[str, tuple[float, float, float, str | None]] = {}
        for entity_id, comp in entries:
            point = (comp.x, comp.y, comp.z, comp.frame_id)
            self._points[entity_id] = point
            key = self._cell_key(comp.x, comp.y, comp.z, comp.frame_id)
            self._cells.setdefault(key, []).append((entity_id, comp.x, comp.y, comp.z))
        #: Exact distance checks performed by the most recent query.
        self.candidates_examined: int = 0

    # ------------------------------------------------------------------
    # Basics
    # ------------------------------------------------------------------

    def __len__(self) -> int:
        return len(self._points)

    def __contains__(self, entity_id: str) -> bool:
        return entity_id in self._points

    @property
    def cell_size(self) -> float:
        return self._cell_size

    def point_of(self, entity_id: str) -> tuple[float, float, float, str | None] | None:
        """The snapshotted ``(x, y, z, frame_id)`` of an entity, or None."""
        return self._points.get(entity_id)

    def _cell_key(self, x: float, y: float, z: float, frame_id: str | None) -> _CellKey:
        cs = self._cell_size
        return (math.floor(x / cs), math.floor(y / cs), math.floor(z / cs), frame_id)

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def within_radius(
        self,
        x: float,
        y: float,
        z: float,
        radius: float,
        *,
        frame_id: str | None = None,
    ) -> list[tuple[str, float]]:
        """Entities within ``radius`` metres of a point, in one frame.

        Returns ``(entity_id, distance)`` pairs sorted by
        ``(distance, entity_id)`` — the entity_id tie-break makes the
        order total and deterministic. The boundary is INCLUSIVE: an
        entity at exactly ``radius`` is within radius.
        """
        if radius < 0:
            raise ValueError(f"radius must be non-negative, got {radius}")
        cs = self._cell_size
        cx0 = math.floor((x - radius) / cs)
        cx1 = math.floor((x + radius) / cs)
        cy0 = math.floor((y - radius) / cs)
        cy1 = math.floor((y + radius) / cs)
        cz0 = math.floor((z - radius) / cs)
        cz1 = math.floor((z + radius) / cs)
        r2 = radius * radius
        found: list[tuple[str, float]] = []
        examined = 0
        for cx in range(cx0, cx1 + 1):
            for cy in range(cy0, cy1 + 1):
                for cz in range(cz0, cz1 + 1):
                    for eid, ex, ey, ez in self._cells.get((cx, cy, cz, frame_id), ()):
                        examined += 1
                        d2 = (ex - x) ** 2 + (ey - y) ** 2 + (ez - z) ** 2
                        if d2 <= r2:
                            found.append((eid, math.sqrt(d2)))
        self.candidates_examined = examined
        found.sort(key=lambda pair: (pair[1], pair[0]))
        return found

    def nearest(
        self,
        x: float,
        y: float,
        z: float,
        count: int,
        *,
        frame_id: str | None = None,
    ) -> list[tuple[str, float]]:
        """The ``count`` nearest entities to a point, in one frame.

        Same ordering contract as :meth:`within_radius`. Expands by
        doubling radii over the grid: a ``within_radius(R)`` result
        with at least ``count`` entries proves the true nearest
        ``count`` are among them (anything outside R is farther than
        R, hence farther than the count-th entry inside it).
        """
        if count < 0:
            raise ValueError(f"count must be non-negative, got {count}")
        if count == 0:
            self.candidates_examined = 0
            return []
        total_in_frame = sum(
            1 for point in self._points.values() if point[3] == frame_id
        )
        if total_in_frame == 0:
            self.candidates_examined = 0
            return []
        radius = self._cell_size
        while True:
            found = self.within_radius(x, y, z, radius, frame_id=frame_id)
            if len(found) >= count or len(found) >= total_in_frame:
                return found[:count]
            radius *= 2.0

    def distance_between(self, entity_id_a: str, entity_id_b: str) -> float | None:
        """Distance between two indexed entities, in metres.

        ``None`` when either entity has no position in this index or
        the two live in different coordinate frames.
        """
        a = self._points.get(entity_id_a)
        b = self._points.get(entity_id_b)
        if a is None or b is None:
            return None
        if a[3] != b[3]:
            return None
        return math.dist(a[:3], b[:3])
