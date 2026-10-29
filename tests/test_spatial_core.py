"""Phase B3 — spatial core: PositionComponent, grid-hash index, and
the Oracle's metric-geometry queries (radius / nearest / distance).

Design under test (see ``ecs/components/spatial.py`` and
``ecs/spatial_index.py``):

* Coordinates are a SEPARATE ``PositionComponent`` (x/y/z metres, 3D
  Euclidean, optional coordinate ``frame_id``) — hierarchy placement
  (``SpatialComponent``) and metric position are orthogonal, and the
  containment queries (``get_nearby`` etc.) are untouched.
* The grid-hash index is built from the live components at query
  time, under ``world.lock``. It therefore CANNOT silently go stale:
  every mutation path — create/remove, add/replace/remove component,
  ``World.set_position``, and direct field assignment (the B2
  lesson: field mutation bypasses World methods) — is reflected in
  the very next query. The mutation-consistency tests below pin
  exactly that, path by path.
* Distances are only defined within one coordinate frame; cross-frame
  answers are ``None`` / exclusion, never an invented number.
* Ordering is total and deterministic: ``(distance, entity_id)``.
  Radius boundaries are inclusive.
"""

from __future__ import annotations

import math
import random
import tempfile
import threading
import time

import pytest

import wyrdforge.ecs.components.identity  # noqa: F401
import wyrdforge.ecs.components.spatial  # noqa: F401
from wyrdforge.ecs.components.identity import NameComponent
from wyrdforge.ecs.components.spatial import PositionComponent
from wyrdforge.ecs.spatial_index import SpatialGridIndex
from wyrdforge.ecs.world import World
from wyrdforge.ecs.yggdrasil import YggdrasilTree
from wyrdforge.oracle import PassiveOracle
from wyrdforge.persistence.memory_store import PersistentMemoryStore
from wyrdforge.persistence.world_store import WorldStore


def _oracle(world: World) -> PassiveOracle:
    store = PersistentMemoryStore(tempfile.mktemp(suffix=".db"))
    return PassiveOracle(world, store)


def _world_with(positions: dict[str, tuple[float, float, float]]) -> World:
    world = World("spatial_test", "Spatial Test")
    for eid, (x, y, z) in positions.items():
        world.create_entity(entity_id=eid)
        world.set_position(eid, x, y, z)
    return world


# ---------------------------------------------------------------------------
# Distance math
# ---------------------------------------------------------------------------

class TestDistanceMath:
    def test_pythagorean_2d_and_3d(self):
        world = _world_with({"a": (0, 0, 0), "b": (3, 4, 0), "c": (2, 3, 6)})
        oracle = _oracle(world)
        assert oracle.distance_between("a", "b") == 5.0
        assert oracle.distance_between("a", "c") == 7.0  # sqrt(4+9+36)
        assert oracle.distance_between("b", "a") == 5.0  # symmetric
        assert oracle.distance_between("a", "a") == 0.0

    def test_component_distance_to(self):
        a = PositionComponent(entity_id="a", x=1.0, y=2.0, z=3.0)
        b = PositionComponent(entity_id="b", x=1.0, y=2.0, z=4.0)
        assert a.distance_to(b) == 1.0

    def test_missing_position_is_none_not_zero(self):
        world = _world_with({"a": (0, 0, 0)})
        world.create_entity(entity_id="unpositioned")
        oracle = _oracle(world)
        assert oracle.distance_between("a", "unpositioned") is None
        assert oracle.distance_between("a", "ghost") is None
        assert oracle.get_position("unpositioned") is None
        assert oracle.get_position("ghost") is None

    def test_cross_frame_distance_is_none(self):
        world = World("frames")
        world.create_entity(entity_id="a")
        world.set_position("a", 0, 0, 0, frame_id="region-1")
        world.create_entity(entity_id="b")
        world.set_position("b", 0, 0, 0, frame_id="region-2")
        oracle = _oracle(world)
        # Same coordinates, different frames: undefined, not 0.0.
        assert oracle.distance_between("a", "b") is None
        a = world.get_position("a")
        b = world.get_position("b")
        assert a is not None and b is not None
        assert a.distance_to(b) is None


# ---------------------------------------------------------------------------
# Radius queries
# ---------------------------------------------------------------------------

class TestRadius:
    def test_inclusion_exclusion_and_boundary(self):
        world = _world_with({
            "centre": (0, 0, 0),
            "inside": (1, 0, 0),
            "on_boundary": (3, 4, 0),   # exactly 5.0 away
            "outside": (5.1, 0, 0),
        })
        oracle = _oracle(world)
        found = oracle.within_radius("centre", 5.0)
        assert [r.entity_id for r in found] == ["inside", "on_boundary"]
        assert found[0].distance == 1.0
        assert found[1].distance == 5.0  # boundary is inclusive

    def test_point_query(self):
        world = _world_with({"a": (0, 0, 0), "b": (10, 0, 0)})
        oracle = _oracle(world)
        found = oracle.within_radius_of_point(9.0, 0, 0, 2.0)
        assert [(r.entity_id, r.distance) for r in found] == [("b", 1.0)]
        # The centre entity itself is NOT excluded from point queries.
        found = oracle.within_radius_of_point(0, 0, 0, 0.0)
        assert [r.entity_id for r in found] == ["a"]

    def test_centre_without_position_has_no_neighbourhood(self):
        world = _world_with({"a": (0, 0, 0)})
        world.create_entity(entity_id="unpositioned")
        oracle = _oracle(world)
        assert oracle.within_radius("unpositioned", 100.0) == []
        assert oracle.nearest("unpositioned", 3) == []

    def test_negative_radius_rejected(self):
        world = _world_with({"a": (0, 0, 0)})
        oracle = _oracle(world)
        with pytest.raises(ValueError):
            oracle.within_radius("a", -1.0)
        with pytest.raises(ValueError):
            oracle.within_radius_of_point(0, 0, 0, -0.5)

    def test_frames_isolate_radius_queries(self):
        world = World("frames")
        for eid, frame in (("a", "r1"), ("b", "r1"), ("c", "r2")):
            world.create_entity(entity_id=eid)
            world.set_position(eid, 0, 0, 0, frame_id=frame)
        oracle = _oracle(world)
        assert [r.entity_id for r in oracle.within_radius("a", 1.0)] == ["b"]
        assert [r.entity_id for r in oracle.within_radius_of_point(0, 0, 0, 1.0, frame_id="r2")] == ["c"]
        assert [r.entity_id for r in oracle.within_radius_of_point(0, 0, 0, 1.0)] == []

    def test_inactive_entities_do_not_participate(self):
        world = _world_with({"a": (0, 0, 0), "b": (1, 0, 0)})
        world.get_entity("b").deactivate()
        oracle = _oracle(world)
        assert oracle.within_radius("a", 5.0) == []
        assert oracle.get_position("b") is not None  # position exists; queries filter active


# ---------------------------------------------------------------------------
# Nearest queries
# ---------------------------------------------------------------------------

class TestNearest:
    def test_ordering_and_count(self):
        world = _world_with({
            "centre": (0, 0, 0),
            "far": (9, 0, 0),
            "near": (1, 0, 0),
            "mid": (5, 0, 0),
        })
        oracle = _oracle(world)
        found = oracle.nearest("centre", 2)
        assert [(r.entity_id, r.distance) for r in found] == [("near", 1.0), ("mid", 5.0)]
        # Asking for more than exist returns all of them (centre excluded).
        found = oracle.nearest("centre", 99)
        assert [r.entity_id for r in found] == ["near", "mid", "far"]

    def test_centre_excluded_before_counting(self):
        # The centre is its own nearest neighbour; nearest(n) must
        # still return n OTHERS.
        world = _world_with({"c": (0, 0, 0), "a": (1, 0, 0), "b": (2, 0, 0), "d": (3, 0, 0)})
        oracle = _oracle(world)
        assert [r.entity_id for r in oracle.nearest("c", 3)] == ["a", "b", "d"]

    def test_ties_break_by_entity_id(self):
        world = _world_with({
            "centre": (0, 0, 0),
            "zeta": (1, 0, 0),
            "alpha": (-1, 0, 0),
            "mid": (0, 1, 0),
        })
        oracle = _oracle(world)
        found = oracle.nearest("centre", 3)
        assert [r.entity_id for r in found] == ["alpha", "mid", "zeta"]
        assert all(r.distance == 1.0 for r in found)
        found = oracle.within_radius("centre", 1.0)
        assert [r.entity_id for r in found] == ["alpha", "mid", "zeta"]

    def test_nearest_to_point_and_zero_count(self):
        world = _world_with({"a": (0, 0, 0), "b": (2, 0, 0)})
        oracle = _oracle(world)
        assert [r.entity_id for r in oracle.nearest_to_point(3, 0, 0, 1)] == ["b"]
        assert oracle.nearest_to_point(0, 0, 0, 0) == []
        assert oracle.nearest("a", 0) == []
        with pytest.raises(ValueError):
            oracle.nearest("a", -1)
        with pytest.raises(ValueError):
            oracle.nearest_to_point(0, 0, 0, -2)


# ---------------------------------------------------------------------------
# Index consistency under every mutation path
# ---------------------------------------------------------------------------

class TestIndexConsistency:
    def test_create_and_remove_entity(self):
        world = _world_with({"a": (0, 0, 0), "b": (1, 0, 0)})
        oracle = _oracle(world)
        assert [r.entity_id for r in oracle.within_radius("a", 5.0)] == ["b"]
        world.create_entity(entity_id="c")
        world.set_position("c", 2, 0, 0)
        assert [r.entity_id for r in oracle.within_radius("a", 5.0)] == ["b", "c"]
        world.remove_entity("b")
        assert [r.entity_id for r in oracle.within_radius("a", 5.0)] == ["c"]
        assert oracle.distance_between("a", "b") is None

    def test_component_add_replace_remove(self):
        world = World("consistency")
        world.create_entity(entity_id="a")
        world.set_position("a", 0, 0, 0)
        world.create_entity(entity_id="b")
        oracle = _oracle(world)
        assert oracle.within_radius("a", 5.0) == []  # b has no position yet
        world.add_component("b", PositionComponent(entity_id="b", x=1.0))
        assert [r.entity_id for r in oracle.within_radius("a", 5.0)] == ["b"]
        # Replace: b teleports out of range.
        world.add_component("b", PositionComponent(entity_id="b", x=100.0))
        assert oracle.within_radius("a", 5.0) == []
        assert oracle.distance_between("a", "b") == 100.0
        world.remove_component("b", "position")
        assert oracle.distance_between("a", "b") is None
        assert oracle.get_position("b") is None

    def test_world_set_position_moves(self):
        world = _world_with({"a": (0, 0, 0), "b": (50, 0, 0)})
        oracle = _oracle(world)
        assert oracle.within_radius("a", 5.0) == []
        world.set_position("b", 2, 0, 0)
        assert [(r.entity_id, r.distance) for r in oracle.within_radius("a", 5.0)] == [("b", 2.0)]

    def test_direct_field_mutation_is_seen(self):
        """THE B2 lesson, pinned for the index: assigning fields on the
        live component bypasses every World method. A maintained index
        would silently go stale here; the query-time index cannot."""
        world = _world_with({"a": (0, 0, 0), "b": (50, 0, 0)})
        oracle = _oracle(world)
        assert oracle.within_radius("a", 5.0) == []
        pos = world.get_position("b")
        assert pos is not None
        pos.x = 1.0  # no World method, no event, no lock
        assert [(r.entity_id, r.distance) for r in oracle.within_radius("a", 5.0)] == [("b", 1.0)]
        pos.x = 500.0
        assert oracle.within_radius("a", 5.0) == []
        assert oracle.distance_between("a", "b") == 500.0

    def test_grid_candidates_are_pruned(self):
        """The grid must actually prune: a small radius query in a
        spread-out world distance-checks far fewer entities than a
        full scan would."""
        entries = []
        world = World("pruning")
        for i in range(400):
            eid = f"e{i}"
            world.create_entity(entity_id=eid)
            # One entity per 100 m cell along a line: maximally spread.
            world.set_position(eid, i * 100.0, 0, 0)
            entries.append((eid, world.get_position(eid)))
        index = SpatialGridIndex(entries)  # type: ignore[arg-type]
        found = index.within_radius(0, 0, 0, 5.0)
        assert [eid for eid, _ in found] == ["e0"]
        assert index.candidates_examined <= 2  # vs 400 for a full scan
        assert len(index) == 400


# ---------------------------------------------------------------------------
# Containment behaviour is unchanged — the two models stay separate
# ---------------------------------------------------------------------------

class TestContainmentUnchanged:
    def _placed_world(self) -> tuple[World, YggdrasilTree]:
        world = World("mixed", "Mixed")
        tree = YggdrasilTree(world)
        tree.create_zone(zone_id="z", name="Z")
        tree.create_region(region_id="r", name="R", parent_zone_id="z")
        tree.create_location(location_id="hall", name="Hall", parent_region_id="r")
        tree.create_location(location_id="yard", name="Yard", parent_region_id="r")
        return world, tree

    def test_get_nearby_is_containment_not_geometry(self):
        world, tree = self._placed_world()
        for eid, loc, pos in (
            ("roommate", "hall", (1000.0, 0, 0)),  # same room, geometrically far
            ("neighbour", "yard", (1.0, 0, 0)),    # next room, geometrically near
            ("hero", "hall", (0.0, 0, 0)),
        ):
            world.create_entity(entity_id=eid)
            world.add_component(eid, NameComponent(entity_id=eid, name=eid))
            tree.place_entity(eid, location_id=loc)
            world.set_position(eid, *pos)
        store = PersistentMemoryStore(tempfile.mktemp(suffix=".db"))
        oracle = PassiveOracle(world, store, yggdrasil=tree)
        # Containment: get_nearby sees the roommate, NOT the neighbour.
        assert [s.entity_id for s in oracle.get_nearby("hero")] == ["roommate"]
        # Geometry: within_radius sees the neighbour, NOT the roommate.
        assert [r.entity_id for r in oracle.within_radius("hero", 5.0)] == ["neighbour"]


# ---------------------------------------------------------------------------
# Persistence: round-trip + B2 dirty detection
# ---------------------------------------------------------------------------

class TestPersistence:
    def test_position_round_trip_and_dirty_detection(self, tmp_path):
        store = WorldStore(tmp_path / "world.db")
        world = _world_with({"a": (1, 2, 3), "b": (4, 5, 6)})
        world.set_position("a", 1, 2, 3, frame_id="region-9")
        first = store.save_with_report(world)
        assert first.components_written == 2

        loaded = store.load(world.world_id)
        pa = loaded.get_position("a")
        pb = loaded.get_position("b")
        assert pa is not None and (pa.x, pa.y, pa.z, pa.frame_id) == (1.0, 2.0, 3.0, "region-9")
        assert pb is not None and (pb.x, pb.y, pb.z, pb.frame_id) == (4.0, 5.0, 6.0, None)

        # No-change save writes nothing (baseline seeded by the load).
        noop = store.save_with_report(loaded)
        assert noop.components_written == 0 and noop.entities_written == 0

        # A position change — via direct field mutation, the hardest
        # path — is detected dirty by the B2 fingerprint and written
        # as exactly one component row.
        pa.x = 99.0
        dirty = store.save_with_report(loaded)
        assert dirty.components_written == 1
        reloaded = store.load(world.world_id)
        pa2 = reloaded.get_position("a")
        assert pa2 is not None and pa2.x == 99.0

        # And via the mediated API after a fresh load.
        reloaded.set_position("b", 40, 50, 60)
        dirty2 = store.save_with_report(reloaded)
        assert dirty2.components_written == 1
        final = store.load(world.world_id)
        pb2 = final.get_position("b")
        assert pb2 is not None and pb2.position == (40.0, 50.0, 60.0)


# ---------------------------------------------------------------------------
# Concurrency: Oracle snapshot consistency under World-mediated moves
# ---------------------------------------------------------------------------

class TestConcurrentMoves:
    def test_queries_stay_consistent_under_concurrent_moves(self):
        world = World("concurrent")
        ids = [f"e{i}" for i in range(40)]
        for i, eid in enumerate(ids):
            world.create_entity(entity_id=eid)
            world.set_position(eid, float(i), 0, 0)
        oracle = _oracle(world)
        errors: list[BaseException] = []
        stop = threading.Event()

        def mover(seed: int) -> None:
            rng = random.Random(seed)
            try:
                while not stop.is_set():
                    eid = rng.choice(ids)
                    world.set_position(eid, rng.uniform(-50, 50), rng.uniform(-50, 50), 0)
            except BaseException as exc:  # noqa: BLE001
                errors.append(exc)

        def reader() -> None:
            try:
                while not stop.is_set():
                    found = oracle.within_radius("e0", 30.0)
                    dists = [r.distance for r in found]
                    assert dists == sorted(dists)
                    assert len({r.entity_id for r in found}) == len(found)
                    assert all(0.0 <= d <= 30.0 for d in dists)
                    near = oracle.nearest_to_point(0, 0, 0, 5)
                    ndists = [r.distance for r in near]
                    assert ndists == sorted(ndists)
            except BaseException as exc:  # noqa: BLE001
                errors.append(exc)

        threads = [threading.Thread(target=mover, args=(i,)) for i in range(3)]
        threads += [threading.Thread(target=reader) for _ in range(3)]
        for t in threads:
            t.start()
        time.sleep(0.6)
        stop.set()
        for t in threads:
            t.join(timeout=10)
        assert not errors, f"concurrent move/query errors: {errors!r}"


# ---------------------------------------------------------------------------
# Scale sanity: a few thousand positioned entities
# ---------------------------------------------------------------------------

class TestScaleSanity:
    def test_three_thousand_entities_grid_vs_brute_force(self):
        rng = random.Random(20261029)
        n = 3000
        world = World("scale")
        truth: dict[str, tuple[float, float, float]] = {}
        for i in range(n):
            eid = f"e{i}"
            point = (rng.uniform(0, 256), rng.uniform(0, 256), rng.uniform(0, 30))
            truth[eid] = point
            world.create_entity(entity_id=eid)
            world.set_position(eid, *point)
        oracle = _oracle(world)

        # Radius query agrees exactly with a brute-force scan.
        cx, cy, cz, radius = 128.0, 128.0, 15.0, 20.0
        started = time.perf_counter()
        found = oracle.within_radius_of_point(cx, cy, cz, radius)
        elapsed_ms = (time.perf_counter() - started) * 1e3
        expected = sorted(
            (
                (eid, math.dist(point, (cx, cy, cz)))
                for eid, point in truth.items()
                if math.dist(point, (cx, cy, cz)) <= radius
            ),
            key=lambda pair: (pair[1], pair[0]),
        )
        assert [(r.entity_id, r.distance) for r in found] == [
            (eid, pytest.approx(d)) for eid, d in expected
        ]
        assert len(found) > 0

        # Nearest query agrees with brute force too.
        found_near = oracle.nearest_to_point(cx, cy, cz, 10)
        expected_near = sorted(
            ((eid, math.dist(point, (cx, cy, cz))) for eid, point in truth.items()),
            key=lambda pair: (pair[1], pair[0]),
        )[:10]
        assert [r.entity_id for r in found_near] == [eid for eid, _ in expected_near]

        # Generous wall-clock guard (this VM is shared and loaded);
        # the measured number is recorded in the campaign state file.
        assert elapsed_ms < 5000, f"radius query over {n} entities took {elapsed_ms:.1f} ms"
        print(f"\nB3 scale: {n} positioned entities, radius query {elapsed_ms:.1f} ms, "
              f"{len(found)} hits")
