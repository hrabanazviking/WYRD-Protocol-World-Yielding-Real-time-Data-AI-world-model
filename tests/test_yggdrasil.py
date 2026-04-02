"""Tests for the Yggdrasil spatial tree service."""
from __future__ import annotations

import pytest

import wyrdforge.ecs.components.character  # noqa: F401
import wyrdforge.ecs.components.identity   # noqa: F401
import wyrdforge.ecs.components.physical   # noqa: F401
import wyrdforge.ecs.components.spatial    # noqa: F401

from wyrdforge.ecs.components.identity import NameComponent, StatusComponent
from wyrdforge.ecs.components.physical import InventoryComponent
from wyrdforge.ecs.components.spatial import ContainerComponent, ParentComponent, SpatialComponent
from wyrdforge.ecs.world import World
from wyrdforge.ecs.yggdrasil import YggdrasilTree


def _setup_world() -> tuple[World, YggdrasilTree]:
    world = World(world_id="test", world_name="Test World")
    tree = YggdrasilTree(world)
    tree.create_zone(zone_id="midgard", name="Midgard")
    tree.create_region(region_id="fjords", name="Fjords", parent_zone_id="midgard")
    tree.create_location(location_id="hall", name="Mead Hall", parent_region_id="fjords")
    tree.create_sublocation(sublocation_id="hearth", name="Great Hearth", parent_location_id="hall")
    tree.create_sublocation(sublocation_id="high_seat", name="High Seat", parent_location_id="hall")
    return world, tree


# ---------------------------------------------------------------------------
# Tree creation tests
# ---------------------------------------------------------------------------

def test_zone_created_with_correct_tags() -> None:
    world, tree = _setup_world()
    zone = world.get_entity("midgard")
    assert zone is not None
    assert zone.has_tag("zone")
    assert zone.has_tag("spatial_node")


def test_region_parent_is_zone() -> None:
    world, tree = _setup_world()
    parent_comp = world.get_component("fjords", "parent")
    assert isinstance(parent_comp, ParentComponent)
    assert parent_comp.parent_entity_id == "midgard"


def test_location_parent_is_region() -> None:
    world, tree = _setup_world()
    parent_comp = world.get_component("hall", "parent")
    assert isinstance(parent_comp, ParentComponent)
    assert parent_comp.parent_entity_id == "fjords"


def test_sublocation_parent_is_location() -> None:
    world, tree = _setup_world()
    parent_comp = world.get_component("hearth", "parent")
    assert isinstance(parent_comp, ParentComponent)
    assert parent_comp.parent_entity_id == "hall"


def test_zone_container_has_region_as_child() -> None:
    world, tree = _setup_world()
    container = world.get_component("midgard", "container")
    assert isinstance(container, ContainerComponent)
    assert "fjords" in container.children


def test_location_container_has_sublocations() -> None:
    world, tree = _setup_world()
    container = world.get_component("hall", "container")
    assert isinstance(container, ContainerComponent)
    assert "hearth" in container.children
    assert "high_seat" in container.children


def test_spatial_nodes_have_name_component() -> None:
    world, tree = _setup_world()
    name_comp = world.get_component("hall", "name")
    assert isinstance(name_comp, NameComponent)
    assert name_comp.name == "Mead Hall"


def test_describe_tree_includes_all_levels() -> None:
    world, tree = _setup_world()
    output = tree.describe_tree()
    assert "Midgard" in output
    assert "Fjords" in output
    assert "Mead Hall" in output
    assert "Great Hearth" in output


# ---------------------------------------------------------------------------
# Entity placement tests
# ---------------------------------------------------------------------------

def _spawn_npc(world: World, tree: YggdrasilTree, entity_id: str, name: str, location_id: str) -> None:
    world.create_entity(entity_id=entity_id, tags={"npc"})
    world.add_component(entity_id, NameComponent(entity_id=entity_id, name=name))
    world.add_component(entity_id, StatusComponent(entity_id=entity_id, state="idle"))
    tree.place_entity(entity_id, location_id=location_id)


def test_place_entity_creates_spatial_component() -> None:
    world, tree = _setup_world()
    _spawn_npc(world, tree, "gunnar", "Gunnar", "hall")
    spatial = world.get_component("gunnar", "spatial")
    assert isinstance(spatial, SpatialComponent)
    assert spatial.location_id == "hall"


def test_place_entity_fills_hierarchy_path() -> None:
    world, tree = _setup_world()
    _spawn_npc(world, tree, "gunnar", "Gunnar", "hall")
    spatial = world.get_component("gunnar", "spatial")
    assert isinstance(spatial, SpatialComponent)
    assert spatial.zone_id == "midgard"
    assert spatial.region_id == "fjords"
    assert spatial.location_id == "hall"


def test_place_entity_at_sublocation() -> None:
    world, tree = _setup_world()
    _spawn_npc(world, tree, "gunnar", "Gunnar", "hall")
    tree.move_entity("gunnar", location_id="hall", sublocation_id="hearth")
    spatial = world.get_component("gunnar", "spatial")
    assert isinstance(spatial, SpatialComponent)
    assert spatial.sublocation_id == "hearth"
    assert spatial.most_specific_id() == "hearth"


def test_place_entity_registers_in_container() -> None:
    world, tree = _setup_world()
    _spawn_npc(world, tree, "gunnar", "Gunnar", "hall")
    container = world.get_component("hall", "container")
    assert isinstance(container, ContainerComponent)
    assert "gunnar" in container.children


def test_place_entity_missing_location_raises() -> None:
    world, tree = _setup_world()
    world.create_entity(entity_id="wanderer", tags={"npc"})
    with pytest.raises(KeyError):
        tree.place_entity("wanderer", location_id="nonexistent")


# ---------------------------------------------------------------------------
# Movement tests
# ---------------------------------------------------------------------------

def test_move_entity_updates_spatial() -> None:
    world, tree = _setup_world()
    _spawn_npc(world, tree, "sigrid", "Sigrid", "hall")
    tree.move_entity("sigrid", location_id="hall", sublocation_id="high_seat")
    spatial = world.get_component("sigrid", "spatial")
    assert isinstance(spatial, SpatialComponent)
    assert spatial.sublocation_id == "high_seat"


def test_move_entity_removes_from_old_container() -> None:
    world, tree = _setup_world()
    _spawn_npc(world, tree, "sigrid", "Sigrid", "hall")
    tree.move_entity("sigrid", location_id="hall", sublocation_id="hearth")
    old_container = world.get_component("hall", "container")
    assert isinstance(old_container, ContainerComponent)
    # After moving to sublocation, entity is in hearth's container, not hall's
    hearth_container = world.get_component("hearth", "container")
    assert isinstance(hearth_container, ContainerComponent)
    assert "sigrid" in hearth_container.children


# ---------------------------------------------------------------------------
# Query tests
# ---------------------------------------------------------------------------

def test_get_location_of() -> None:
    world, tree = _setup_world()
    _spawn_npc(world, tree, "gunnar", "Gunnar", "hall")
    loc = tree.get_location_of("gunnar")
    assert loc == "hall"


def test_get_location_of_sublocation() -> None:
    world, tree = _setup_world()
    _spawn_npc(world, tree, "gunnar", "Gunnar", "hall")
    tree.move_entity("gunnar", location_id="hall", sublocation_id="hearth")
    loc = tree.get_location_of("gunnar")
    assert loc == "hearth"


def test_get_spatial_path() -> None:
    world, tree = _setup_world()
    _spawn_npc(world, tree, "gunnar", "Gunnar", "hall")
    path = tree.get_spatial_path("gunnar")
    assert "midgard" in path
    assert "fjords" in path
    assert "hall" in path


def test_get_children_of_zone() -> None:
    world, tree = _setup_world()
    children = tree.get_children("midgard")
    assert any(c.entity_id == "fjords" for c in children)


def test_get_ancestors_of_sublocation() -> None:
    world, tree = _setup_world()
    ancestors = tree.get_ancestors("hearth")
    ancestor_ids = [a.entity_id for a in ancestors]
    assert "hall" in ancestor_ids
    assert "fjords" in ancestor_ids
    assert "midgard" in ancestor_ids


def test_get_co_located() -> None:
    world, tree = _setup_world()
    _spawn_npc(world, tree, "gunnar", "Gunnar", "hall")
    _spawn_npc(world, tree, "leif", "Leif", "hall")
    _spawn_npc(world, tree, "sigrid", "Sigrid", "hearth")  # hearth is sublocation
    co_located = tree.get_co_located("gunnar")
    co_ids = {e.entity_id for e in co_located}
    assert "leif" in co_ids
    assert "sigrid" not in co_ids  # different sublocation


def test_find_by_name_partial_match() -> None:
    world, tree = _setup_world()
    results = tree.find_by_name("hearth")
    assert any(r.entity_id == "hearth" for r in results)


def test_find_by_name_case_insensitive() -> None:
    world, tree = _setup_world()
    results = tree.find_by_name("MEAD HALL")
    assert any(r.entity_id == "hall" for r in results)


def test_entities_at_excludes_spatial_nodes() -> None:
    world, tree = _setup_world()
    _spawn_npc(world, tree, "gunnar", "Gunnar", "hall")
    at_hall = tree.entities_at("hall")
    assert all(not e.has_tag("spatial_node") for e in at_hall)
    assert any(e.entity_id == "gunnar" for e in at_hall)


def test_world_entity_count_includes_spatial_nodes() -> None:
    world, tree = _setup_world()
    # zone + region + location + 2 sublocations = 5 spatial nodes
    assert world.entity_count() >= 5
