"""Tests for ECS core: Entity, Component, World, System, WorldRunner."""
from __future__ import annotations

import pytest

# Register all component types before any tests run
import wyrdforge.ecs.components.character  # noqa: F401
import wyrdforge.ecs.components.identity   # noqa: F401
import wyrdforge.ecs.components.physical   # noqa: F401
import wyrdforge.ecs.components.spatial    # noqa: F401

from wyrdforge.ecs.component import deserialize_component, get_component_class, registered_types
from wyrdforge.ecs.components.character import FactionComponent, HealthComponent, PersonaRefComponent
from wyrdforge.ecs.components.identity import DescriptionComponent, NameComponent, StatusComponent
from wyrdforge.ecs.components.physical import InventoryComponent, PhysicalComponent
from wyrdforge.ecs.components.spatial import ContainerComponent, ParentComponent, SpatialComponent
from wyrdforge.ecs.entity import Entity
from wyrdforge.ecs.system import System, WorldRunner
from wyrdforge.ecs.world import World


# ---------------------------------------------------------------------------
# Entity tests
# ---------------------------------------------------------------------------

def test_entity_creates_with_defaults() -> None:
    e = Entity()
    assert e.entity_id
    assert e.active is True
    assert e.tags == set()


def test_entity_add_remove_tag() -> None:
    e = Entity()
    e.add_tag("npc")
    assert e.has_tag("npc")
    e.remove_tag("npc")
    assert not e.has_tag("npc")


def test_entity_deactivate_reactivate() -> None:
    e = Entity()
    e.deactivate()
    assert not e.active
    e.reactivate()
    assert e.active


def test_entity_repr_contains_id_prefix() -> None:
    e = Entity(entity_id="abc12345-0000-0000-0000-000000000000")
    assert "abc12345" in repr(e)


# ---------------------------------------------------------------------------
# Component registry tests
# ---------------------------------------------------------------------------

def test_all_core_components_registered() -> None:
    types = registered_types()
    for expected in ["name", "description", "status", "spatial", "parent", "container",
                     "physical", "inventory", "persona_ref", "health", "faction"]:
        assert expected in types, f"'{expected}' not registered"


def test_get_component_class_returns_correct_type() -> None:
    assert get_component_class("name") is NameComponent
    assert get_component_class("health") is HealthComponent
    assert get_component_class("spatial") is SpatialComponent


def test_get_component_class_raises_for_unknown() -> None:
    with pytest.raises(KeyError):
        get_component_class("nonexistent_type_xyz")


def test_deserialize_component_roundtrip() -> None:
    original = NameComponent(entity_id="ent-1", name="Gunnar", aliases=["Iron Fist"])
    data = original.model_dump()
    restored = deserialize_component(data)
    assert isinstance(restored, NameComponent)
    assert restored.name == "Gunnar"
    assert restored.aliases == ["Iron Fist"]


def test_deserialize_raises_without_component_type() -> None:
    with pytest.raises(ValueError):
        deserialize_component({"entity_id": "x"})


# ---------------------------------------------------------------------------
# World tests
# ---------------------------------------------------------------------------

def _make_world() -> World:
    return World(world_id="test", world_name="Test World")


def test_world_create_entity() -> None:
    world = _make_world()
    entity = world.create_entity(tags={"npc"})
    assert entity.entity_id in world._entities
    assert world.entity_count() == 1


def test_world_create_entity_with_explicit_id() -> None:
    world = _make_world()
    entity = world.create_entity(entity_id="gunnar", tags={"npc"})
    assert entity.entity_id == "gunnar"


def test_world_create_entity_duplicate_raises() -> None:
    world = _make_world()
    world.create_entity(entity_id="dup")
    with pytest.raises(ValueError):
        world.create_entity(entity_id="dup")


def test_world_remove_entity() -> None:
    world = _make_world()
    entity = world.create_entity()
    world.remove_entity(entity.entity_id)
    assert world.entity_count() == 0


def test_world_remove_entity_missing_raises() -> None:
    world = _make_world()
    with pytest.raises(KeyError):
        world.remove_entity("ghost")


def test_world_add_and_get_component() -> None:
    world = _make_world()
    entity = world.create_entity(entity_id="e1")
    comp = NameComponent(entity_id="e1", name="Sigrid")
    world.add_component("e1", comp)
    result = world.get_component("e1", "name")
    assert isinstance(result, NameComponent)
    assert result.name == "Sigrid"


def test_world_add_component_wrong_entity_raises() -> None:
    world = _make_world()
    world.create_entity(entity_id="e1")
    comp = NameComponent(entity_id="e2", name="Wrong")
    with pytest.raises(ValueError):
        world.add_component("e1", comp)


def test_world_add_component_missing_entity_raises() -> None:
    world = _make_world()
    comp = NameComponent(entity_id="ghost", name="Ghost")
    with pytest.raises(KeyError):
        world.add_component("ghost", comp)


def test_world_remove_component() -> None:
    world = _make_world()
    world.create_entity(entity_id="e1")
    world.add_component("e1", NameComponent(entity_id="e1", name="Runa"))
    world.remove_component("e1", "name")
    assert world.get_component("e1", "name") is None


def test_world_has_component() -> None:
    world = _make_world()
    world.create_entity(entity_id="e1")
    assert not world.has_component("e1", "name")
    world.add_component("e1", NameComponent(entity_id="e1", name="Runa"))
    assert world.has_component("e1", "name")


def test_world_get_all_components() -> None:
    world = _make_world()
    world.create_entity(entity_id="e1")
    world.add_component("e1", NameComponent(entity_id="e1", name="Runa"))
    world.add_component("e1", HealthComponent(entity_id="e1"))
    comps = world.get_all_components("e1")
    assert len(comps) == 2
    types = {c.component_type for c in comps}
    assert "name" in types and "health" in types


def test_world_query_by_tag() -> None:
    world = _make_world()
    world.create_entity(entity_id="e1", tags={"npc"})
    world.create_entity(entity_id="e2", tags={"player"})
    world.create_entity(entity_id="e3", tags={"npc", "merchant"})
    npcs = world.query_by_tag("npc")
    assert len(npcs) == 2
    assert all(e.has_tag("npc") for e in npcs)


def test_world_query_by_tags_intersection() -> None:
    world = _make_world()
    world.create_entity(entity_id="e1", tags={"npc", "merchant"})
    world.create_entity(entity_id="e2", tags={"npc"})
    result = world.query_by_tags({"npc", "merchant"})
    assert len(result) == 1
    assert result[0].entity_id == "e1"


def test_world_query_with_component() -> None:
    world = _make_world()
    world.create_entity(entity_id="e1")
    world.create_entity(entity_id="e2")
    world.add_component("e1", HealthComponent(entity_id="e1"))
    result = world.query_with_component("health")
    assert len(result) == 1
    assert result[0].entity_id == "e1"


def test_world_query_with_components_intersection() -> None:
    world = _make_world()
    world.create_entity(entity_id="e1")
    world.create_entity(entity_id="e2")
    world.add_component("e1", HealthComponent(entity_id="e1"))
    world.add_component("e1", NameComponent(entity_id="e1", name="X"))
    world.add_component("e2", HealthComponent(entity_id="e2"))
    result = world.query_with_components(["health", "name"])
    assert len(result) == 1
    assert result[0].entity_id == "e1"


def test_world_tag_untag_entity() -> None:
    world = _make_world()
    world.create_entity(entity_id="e1", tags={"npc"})
    world.tag_entity("e1", "merchant")
    assert len(world.query_by_tag("merchant")) == 1
    world.untag_entity("e1", "merchant")
    assert len(world.query_by_tag("merchant")) == 0


def test_world_active_only_filter() -> None:
    world = _make_world()
    world.create_entity(entity_id="e1", tags={"npc"})
    e2 = world.create_entity(entity_id="e2", tags={"npc"})
    e2.deactivate()
    active = world.query_by_tag("npc", active_only=True)
    assert len(active) == 1
    all_entities = world.query_by_tag("npc", active_only=False)
    assert len(all_entities) == 2


def test_world_component_replace_on_duplicate() -> None:
    world = _make_world()
    world.create_entity(entity_id="e1")
    world.add_component("e1", NameComponent(entity_id="e1", name="Old"))
    world.add_component("e1", NameComponent(entity_id="e1", name="New"))
    comp = world.get_component("e1", "name")
    assert isinstance(comp, NameComponent)
    assert comp.name == "New"


def test_world_iter_components() -> None:
    world = _make_world()
    world.create_entity(entity_id="e1")
    world.create_entity(entity_id="e2")
    world.add_component("e1", HealthComponent(entity_id="e1", hp=80.0))
    world.add_component("e2", HealthComponent(entity_id="e2", hp=60.0))
    pairs = list(world.iter_components("health"))
    assert len(pairs) == 2


# ---------------------------------------------------------------------------
# Component domain logic tests
# ---------------------------------------------------------------------------

def test_health_take_damage() -> None:
    h = HealthComponent(entity_id="e1", hp=100.0, max_hp=100.0)
    h.take_damage(60.0)
    assert h.hp == 40.0
    assert h.wounded is True


def test_health_death() -> None:
    h = HealthComponent(entity_id="e1", hp=10.0, max_hp=100.0)
    h.take_damage(10.0)
    assert h.alive is False


def test_health_heal_caps_at_max() -> None:
    h = HealthComponent(entity_id="e1", hp=50.0, max_hp=100.0)
    h.heal(200.0)
    assert h.hp == 100.0


def test_inventory_add_remove() -> None:
    inv = InventoryComponent(entity_id="e1")
    inv.add_item("sword_01")
    assert inv.has_item("sword_01")
    removed = inv.remove_item("sword_01")
    assert removed is True
    assert not inv.has_item("sword_01")


def test_inventory_remove_missing_returns_false() -> None:
    inv = InventoryComponent(entity_id="e1")
    assert inv.remove_item("nonexistent") is False


def test_faction_reputation_clamped() -> None:
    faction = FactionComponent(entity_id="e1")
    faction.set_reputation("clan_iron", 2.5)
    assert faction.get_reputation("clan_iron") == 1.0
    faction.set_reputation("clan_iron", -3.0)
    assert faction.get_reputation("clan_iron") == -1.0


def test_container_add_remove_child() -> None:
    c = ContainerComponent(entity_id="loc1")
    c.add_child("npc1")
    c.add_child("npc2")
    assert "npc1" in c.children
    c.remove_child("npc1")
    assert "npc1" not in c.children


def test_container_capacity_check() -> None:
    c = ContainerComponent(entity_id="loc1", capacity=1)
    c.add_child("npc1")
    assert c.is_full() is True


# ---------------------------------------------------------------------------
# System / WorldRunner tests
# ---------------------------------------------------------------------------

class _CounterSystem(System):
    component_interests = ["name"]

    def __init__(self) -> None:
        self.tick_count = 0

    def tick(self, world: World, delta_t: float) -> None:
        self.tick_count += 1


def test_world_runner_ticks_system() -> None:
    world = _make_world()
    runner = WorldRunner(world)
    system = _CounterSystem()
    runner.add_system(system)
    runner.tick()
    runner.tick()
    assert system.tick_count == 2


def test_world_runner_tick_n() -> None:
    world = _make_world()
    runner = WorldRunner(world)
    system = _CounterSystem()
    runner.add_system(system)
    runner.tick_n(5)
    assert system.tick_count == 5


def test_world_runner_remove_system() -> None:
    world = _make_world()
    runner = WorldRunner(world)
    system = _CounterSystem()
    runner.add_system(system)
    runner.remove_system(system)
    runner.tick()
    assert system.tick_count == 0
