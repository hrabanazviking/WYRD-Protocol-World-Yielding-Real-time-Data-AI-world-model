"""Tests for YAML world config loader and demo world."""
from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

import wyrdforge.ecs.components.character  # noqa: F401
import wyrdforge.ecs.components.identity   # noqa: F401
import wyrdforge.ecs.components.physical   # noqa: F401
import wyrdforge.ecs.components.spatial    # noqa: F401

from wyrdforge.ecs.components.identity import NameComponent
from wyrdforge.ecs.components.spatial import ContainerComponent, ParentComponent
from wyrdforge.loaders.world_loader import load_world_from_yaml

_MINIMAL_YAML = """
world_id: mini
world_name: "Mini World"
zones:
  - id: zone_a
    name: Zone A
    description: "A test zone"
    regions:
      - id: region_a
        name: Region A
        description: "A test region"
        locations:
          - id: loc_a
            name: Location A
            description: "A test location"
            sublocations:
              - id: sub_a
                name: Sub A
                description: "A test sub-location"
"""


def _write_yaml(content: str) -> Path:
    tmp = Path(tempfile.mktemp(suffix=".yaml"))
    tmp.write_text(content, encoding="utf-8")
    return tmp


# ---------------------------------------------------------------------------
# Minimal YAML tests
# ---------------------------------------------------------------------------

def test_loader_returns_world_and_tree() -> None:
    path = _write_yaml(_MINIMAL_YAML)
    world, tree = load_world_from_yaml(path)
    assert world.world_id == "mini"
    assert tree is not None


def test_loader_world_name() -> None:
    path = _write_yaml(_MINIMAL_YAML)
    world, _ = load_world_from_yaml(path)
    assert world.world_name == "Mini World"


def test_loader_zone_created() -> None:
    path = _write_yaml(_MINIMAL_YAML)
    world, _ = load_world_from_yaml(path)
    zone = world.get_entity("zone_a")
    assert zone is not None
    assert zone.has_tag("zone")


def test_loader_region_created() -> None:
    path = _write_yaml(_MINIMAL_YAML)
    world, _ = load_world_from_yaml(path)
    region = world.get_entity("region_a")
    assert region is not None
    assert region.has_tag("region")


def test_loader_location_created() -> None:
    path = _write_yaml(_MINIMAL_YAML)
    world, _ = load_world_from_yaml(path)
    loc = world.get_entity("loc_a")
    assert loc is not None
    assert loc.has_tag("location")


def test_loader_sublocation_created() -> None:
    path = _write_yaml(_MINIMAL_YAML)
    world, _ = load_world_from_yaml(path)
    sub = world.get_entity("sub_a")
    assert sub is not None
    assert sub.has_tag("sublocation")


def test_loader_name_components_assigned() -> None:
    path = _write_yaml(_MINIMAL_YAML)
    world, _ = load_world_from_yaml(path)
    name_comp = world.get_component("loc_a", "name")
    assert isinstance(name_comp, NameComponent)
    assert name_comp.name == "Location A"


def test_loader_parent_hierarchy() -> None:
    path = _write_yaml(_MINIMAL_YAML)
    world, _ = load_world_from_yaml(path)
    region_parent = world.get_component("region_a", "parent")
    assert isinstance(region_parent, ParentComponent)
    assert region_parent.parent_entity_id == "zone_a"
    loc_parent = world.get_component("loc_a", "parent")
    assert isinstance(loc_parent, ParentComponent)
    assert loc_parent.parent_entity_id == "region_a"
    sub_parent = world.get_component("sub_a", "parent")
    assert isinstance(sub_parent, ParentComponent)
    assert sub_parent.parent_entity_id == "loc_a"


def test_loader_container_children() -> None:
    path = _write_yaml(_MINIMAL_YAML)
    world, _ = load_world_from_yaml(path)
    zone_container = world.get_component("zone_a", "container")
    assert isinstance(zone_container, ContainerComponent)
    assert "region_a" in zone_container.children
    loc_container = world.get_component("loc_a", "container")
    assert isinstance(loc_container, ContainerComponent)
    assert "sub_a" in loc_container.children


def test_loader_missing_file_raises() -> None:
    with pytest.raises(FileNotFoundError):
        load_world_from_yaml("/nonexistent/path/world.yaml")


def test_loader_uses_filename_as_world_id_when_missing() -> None:
    yaml_content = "zones: []\n"
    path = _write_yaml(yaml_content)
    world, _ = load_world_from_yaml(path)
    assert world.world_id == path.stem


# ---------------------------------------------------------------------------
# Demo world (thornholt) tests
# ---------------------------------------------------------------------------

def test_thornholt_loads_successfully() -> None:
    world, tree = load_world_from_yaml("configs/worlds/thornholt.yaml")
    assert world.world_id == "thornholt"


def test_thornholt_has_midgard_zone() -> None:
    world, _ = load_world_from_yaml("configs/worlds/thornholt.yaml")
    zone = world.get_entity("midgard")
    assert zone is not None
    assert zone.has_tag("zone")


def test_thornholt_has_mead_hall_location() -> None:
    world, _ = load_world_from_yaml("configs/worlds/thornholt.yaml")
    hall = world.get_entity("thornholt_hall")
    assert hall is not None
    assert hall.has_tag("location")


def test_thornholt_has_sublocations() -> None:
    world, _ = load_world_from_yaml("configs/worlds/thornholt.yaml")
    for sub_id in ["great_fire_pit", "high_seat", "mead_benches", "sleeping_alcoves", "weapons_rack"]:
        sub = world.get_entity(sub_id)
        assert sub is not None, f"Missing sublocation: {sub_id}"
        assert sub.has_tag("sublocation")


def test_thornholt_has_forge() -> None:
    world, _ = load_world_from_yaml("configs/worlds/thornholt.yaml")
    forge = world.get_entity("thornholt_forge")
    assert forge is not None


def test_thornholt_describe_tree_non_empty() -> None:
    world, tree = load_world_from_yaml("configs/worlds/thornholt.yaml")
    output = tree.describe_tree()
    assert "Thornholt" in output
    assert "Midgard" in output


def test_thornholt_spatial_nodes_queryable_by_tag() -> None:
    world, _ = load_world_from_yaml("configs/worlds/thornholt.yaml")
    zones = world.query_by_tag("zone")
    regions = world.query_by_tag("region")
    locations = world.query_by_tag("location")
    sublocations = world.query_by_tag("sublocation")
    assert len(zones) >= 1
    assert len(regions) >= 2
    assert len(locations) >= 3
    assert len(sublocations) >= 5


def test_thornholt_find_by_name() -> None:
    world, tree = load_world_from_yaml("configs/worlds/thornholt.yaml")
    results = tree.find_by_name("forge")
    assert any("forge" in r.entity_id for r in results)


def test_thornholt_entity_count_reasonable() -> None:
    world, _ = load_world_from_yaml("configs/worlds/thornholt.yaml")
    # Should have at minimum: 1 zone + 2 regions + 4+ locations + 9+ sublocations
    assert world.entity_count() >= 16
