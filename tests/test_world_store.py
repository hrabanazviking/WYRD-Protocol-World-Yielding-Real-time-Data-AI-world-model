"""Tests for SQLite WorldStore persistence."""
from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

import wyrdforge.ecs.components.character  # noqa: F401
import wyrdforge.ecs.components.identity   # noqa: F401
import wyrdforge.ecs.components.physical   # noqa: F401
import wyrdforge.ecs.components.spatial    # noqa: F401

from wyrdforge.ecs.components.character import HealthComponent
from wyrdforge.ecs.components.identity import NameComponent, StatusComponent
from wyrdforge.ecs.components.spatial import SpatialComponent
from wyrdforge.ecs.world import World
from wyrdforge.ecs.yggdrasil import YggdrasilTree
from wyrdforge.persistence.world_store import WorldStore


def _temp_store() -> tuple[WorldStore, Path]:
    tmp = tempfile.mktemp(suffix=".db")
    return WorldStore(tmp), Path(tmp)


def _build_test_world() -> World:
    world = World(world_id="save_test", world_name="Save Test World")
    tree = YggdrasilTree(world)
    tree.create_zone(zone_id="midgard", name="Midgard")
    tree.create_region(region_id="fjords", name="Fjords", parent_zone_id="midgard")
    tree.create_location(location_id="hall", name="Mead Hall", parent_region_id="fjords")
    tree.create_sublocation(sublocation_id="hearth", name="Hearth", parent_location_id="hall")
    # Add a character
    world.create_entity(entity_id="gunnar", tags={"npc", "warrior"})
    world.add_component("gunnar", NameComponent(entity_id="gunnar", name="Gunnar Ironfist"))
    world.add_component("gunnar", HealthComponent(entity_id="gunnar", hp=80.0))
    world.add_component("gunnar", StatusComponent(entity_id="gunnar", state="drinking"))
    tree.place_entity("gunnar", location_id="hall")
    return world


# ---------------------------------------------------------------------------
# Basic save/load tests
# ---------------------------------------------------------------------------

def test_store_creates_db_file() -> None:
    store, path = _temp_store()
    world = _build_test_world()
    store.save(world)
    assert path.exists()


def test_list_worlds_after_save() -> None:
    store, _ = _temp_store()
    world = _build_test_world()
    store.save(world)
    worlds = store.list_worlds()
    assert "save_test" in worlds


def test_load_world_id_and_name() -> None:
    store, _ = _temp_store()
    world = _build_test_world()
    store.save(world)
    loaded = store.load("save_test")
    assert loaded.world_id == "save_test"
    assert loaded.world_name == "Save Test World"


def test_load_world_entity_count() -> None:
    store, _ = _temp_store()
    world = _build_test_world()
    store.save(world)
    loaded = store.load("save_test")
    assert loaded.entity_count() == world.entity_count()


def test_load_entity_tags_preserved() -> None:
    store, _ = _temp_store()
    world = _build_test_world()
    store.save(world)
    loaded = store.load("save_test")
    gunnar = loaded.get_entity("gunnar")
    assert gunnar is not None
    assert gunnar.has_tag("npc")
    assert gunnar.has_tag("warrior")


def test_load_component_data_preserved() -> None:
    store, _ = _temp_store()
    world = _build_test_world()
    store.save(world)
    loaded = store.load("save_test")
    name_comp = loaded.get_component("gunnar", "name")
    assert isinstance(name_comp, NameComponent)
    assert name_comp.name == "Gunnar Ironfist"


def test_load_health_component_value() -> None:
    store, _ = _temp_store()
    world = _build_test_world()
    store.save(world)
    loaded = store.load("save_test")
    health = loaded.get_component("gunnar", "health")
    assert isinstance(health, HealthComponent)
    assert health.hp == 80.0


def test_load_status_component_state() -> None:
    store, _ = _temp_store()
    world = _build_test_world()
    store.save(world)
    loaded = store.load("save_test")
    status = loaded.get_component("gunnar", "status")
    assert isinstance(status, StatusComponent)
    assert status.state == "drinking"


def test_load_spatial_component_preserved() -> None:
    store, _ = _temp_store()
    world = _build_test_world()
    store.save(world)
    loaded = store.load("save_test")
    spatial = loaded.get_component("gunnar", "spatial")
    assert isinstance(spatial, SpatialComponent)
    assert spatial.location_id == "hall"
    assert spatial.zone_id == "midgard"


def test_load_tag_index_rebuilt() -> None:
    store, _ = _temp_store()
    world = _build_test_world()
    store.save(world)
    loaded = store.load("save_test")
    npcs = loaded.query_by_tag("npc")
    assert any(e.entity_id == "gunnar" for e in npcs)


def test_load_component_index_rebuilt() -> None:
    store, _ = _temp_store()
    world = _build_test_world()
    store.save(world)
    loaded = store.load("save_test")
    entities_with_health = loaded.query_with_component("health")
    assert any(e.entity_id == "gunnar" for e in entities_with_health)


# ---------------------------------------------------------------------------
# Save/load round-trip with mutations
# ---------------------------------------------------------------------------

def test_save_after_mutation_updates_state() -> None:
    store, _ = _temp_store()
    world = _build_test_world()
    store.save(world)
    # Mutate
    health = world.get_component("gunnar", "health")
    assert isinstance(health, HealthComponent)
    health.take_damage(30.0)
    store.save(world)
    loaded = store.load("save_test")
    loaded_health = loaded.get_component("gunnar", "health")
    assert isinstance(loaded_health, HealthComponent)
    assert loaded_health.hp == 50.0


def test_save_removes_deleted_entity() -> None:
    store, _ = _temp_store()
    world = _build_test_world()
    store.save(world)
    world.remove_entity("gunnar")
    store.save(world)
    loaded = store.load("save_test")
    assert loaded.get_entity("gunnar") is None


# ---------------------------------------------------------------------------
# Error / utility tests
# ---------------------------------------------------------------------------

def test_load_missing_world_raises() -> None:
    store, _ = _temp_store()
    with pytest.raises(KeyError):
        store.load("does_not_exist")


def test_integrity_check_passes_on_fresh_db() -> None:
    store, _ = _temp_store()
    world = _build_test_world()
    store.save(world)
    assert store.integrity_check() is True


def test_delete_world_removes_from_list() -> None:
    store, _ = _temp_store()
    world = _build_test_world()
    store.save(world)
    store.delete_world("save_test")
    assert "save_test" not in store.list_worlds()


def test_multiple_worlds_in_same_store() -> None:
    store, _ = _temp_store()
    w1 = World(world_id="world_a", world_name="World A")
    w2 = World(world_id="world_b", world_name="World B")
    store.save(w1)
    store.save(w2)
    worlds = store.list_worlds()
    assert "world_a" in worlds
    assert "world_b" in worlds


def test_inactive_entity_persists_active_flag() -> None:
    store, _ = _temp_store()
    world = _build_test_world()
    gunnar = world.get_entity("gunnar")
    assert gunnar is not None
    gunnar.deactivate()
    store.save(world)
    loaded = store.load("save_test")
    loaded_gunnar = loaded.get_entity("gunnar")
    assert loaded_gunnar is not None
    assert loaded_gunnar.active is False
