"""Parent-chain cycle guards — Wave G Slice 5 (Track 4 P1).

Proves: (1) cyclic parent data terminates both parent walks instead of
hanging; (2) acyclic chains walk exactly as before (zero valid-path
behavior change).

Attack path: the world loader (loaders/world_loader.py) wires
parent links from YAML with no cycle check, and Slice 3's schema
validation does not reject cyclic hierarchies — so a hand-crafted
file (or direct component writes) can build A->B->A. Before this
slice, both walks below looped forever on such data.
"""
from __future__ import annotations

import logging
import threading

import pytest

from wyrdforge.ecs.components.spatial import HierarchyLevel, ParentComponent
from wyrdforge.ecs.world import World
from wyrdforge.ecs.yggdrasil import YggdrasilTree
from wyrdforge.oracle.passive_oracle import PassiveOracle


def _world_with_parents(links: dict[str, str]) -> World:
    """Build a world whose parent links are exactly ``links`` (child -> parent).

    Direct component writes — the same mechanism a hand-crafted world
    file's parent ids take once loaded.
    """
    world = World("cycle_world", "Cycle World")
    for entity_id in set(links) | set(links.values()):
        world.create_entity(entity_id=entity_id, tags={"spatial_node"})
    for child_id, parent_id in links.items():
        world.add_component(
            child_id,
            ParentComponent(
                entity_id=child_id,
                parent_entity_id=parent_id,
                hierarchy_level=HierarchyLevel.OBJECT,
            ),
        )
    return world


def _run_bounded(fn, timeout: float = 5.0):
    """Run *fn* in a thread; fail (don't hang the suite) if it overruns."""
    box: dict = {}
    thread = threading.Thread(
        target=lambda: box.setdefault("result", fn()), daemon=True
    )
    thread.start()
    thread.join(timeout=timeout)
    assert not thread.is_alive(), "parent walk did not terminate (cycle guard missing?)"
    return box["result"]


# ---------------------------------------------------------------------------
# YggdrasilTree.get_ancestors
# ---------------------------------------------------------------------------

class TestGetAncestorsCycleGuard:
    def test_terminates_on_two_cycle(self):
        world = _world_with_parents({"a": "b", "b": "a"})
        tree = YggdrasilTree(world)
        ancestors = _run_bounded(lambda: tree.get_ancestors("a"))
        ids = [e.entity_id for e in ancestors]
        # Walk stops at the revisited id instead of looping forever.
        assert len(ids) <= 2
        assert set(ids) <= {"a", "b"}

    def test_terminates_on_self_cycle(self):
        world = _world_with_parents({"a": "a"})
        tree = YggdrasilTree(world)
        ancestors = _run_bounded(lambda: tree.get_ancestors("a"))
        assert [e.entity_id for e in ancestors] == []

    def test_warns_naming_the_cycle(self, caplog):
        world = _world_with_parents({"a": "b", "b": "a"})
        tree = YggdrasilTree(world)
        with caplog.at_level(logging.WARNING, logger="wyrdforge.ecs.yggdrasil"):
            tree.get_ancestors("a")
        assert any("cycle" in r.message for r in caplog.records)

    def test_acyclic_chain_unchanged(self, caplog):
        world = _world_with_parents({"a": "b", "b": "c"})
        tree = YggdrasilTree(world)
        with caplog.at_level(logging.WARNING, logger="wyrdforge.ecs.yggdrasil"):
            ancestors = tree.get_ancestors("a")
        # [immediate_parent, ..., zone] — identical to pre-guard behavior.
        assert [e.entity_id for e in ancestors] == ["b", "c"]
        # No warning on valid paths: the guard is a no-op for acyclic data.
        assert not caplog.records

    def test_missing_parent_still_terminates(self):
        world = World("cycle_world", "Cycle World")
        world.create_entity(entity_id="a", tags={"spatial_node"})
        # "ghost" is never created — get_entity returns None.
        world.add_component(
            "a",
            ParentComponent(
                entity_id="a",
                parent_entity_id="ghost",
                hierarchy_level=HierarchyLevel.OBJECT,
            ),
        )
        tree = YggdrasilTree(world)
        assert tree.get_ancestors("a") == []


# ---------------------------------------------------------------------------
# PassiveOracle fallback parent walk (yggdrasil=None)
# ---------------------------------------------------------------------------

class TestOracleFallbackWalkCycleGuard:
    def _oracle(self, world: World) -> PassiveOracle:
        return PassiveOracle(world, None, yggdrasil=None)

    def test_terminates_on_two_cycle(self):
        world = _world_with_parents({"a": "b", "b": "a"})
        oracle = self._oracle(world)
        result = _run_bounded(
            lambda: oracle._build_location_result_for_node("a")
        )
        assert len(result.path) <= 3  # bounded: no infinite chain

    def test_warns_naming_the_cycle(self, caplog):
        world = _world_with_parents({"a": "b", "b": "a"})
        oracle = self._oracle(world)
        with caplog.at_level(logging.WARNING, logger="wyrdforge.oracle.passive_oracle"):
            oracle._build_location_result_for_node("a")
        assert any("cycle" in r.message for r in caplog.records)

    def test_acyclic_chain_unchanged(self, caplog):
        world = _world_with_parents({"a": "b", "b": "c"})
        oracle = self._oracle(world)
        with caplog.at_level(logging.WARNING, logger="wyrdforge.oracle.passive_oracle"):
            result = oracle._build_location_result_for_node("a")
        # chain [b, c] reversed + node appended — identical to pre-guard.
        assert result.path == ["c", "b", "a"]
        assert not caplog.records
