from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from wyrdforge.ecs.world import World
from wyrdforge.ecs.yggdrasil import YggdrasilTree


def load_world_from_yaml(path: str | Path) -> tuple[World, YggdrasilTree]:
    """Load a World and its Yggdrasil tree from a YAML config file.

    Expected YAML structure:
        world_id: "my_world"
        world_name: "My World Name"   # optional
        zones:
          - id: zone_id
            name: Zone Name
            description: "..."        # optional
            regions:
              - id: region_id
                name: Region Name
                description: "..."
                locations:
                  - id: location_id
                    name: Location Name
                    description: "..."
                    sublocations:
                      - id: sublocation_id
                        name: Sub-location Name
                        description: "..."

    Returns:
        (world, yggdrasil_tree) — world is populated, tree is ready to use.
    """
    config_path = Path(path)
    if not config_path.exists():
        raise FileNotFoundError(f"World config not found: {config_path}")

    with config_path.open("r", encoding="utf-8") as fh:
        config: dict[str, Any] = yaml.safe_load(fh)

    world_id = config.get("world_id") or config_path.stem
    world_name = config.get("world_name", world_id)
    world = World(world_id=world_id, world_name=world_name)
    tree = YggdrasilTree(world)

    for zone_def in config.get("zones", []):
        tree.create_zone(
            zone_id=zone_def["id"],
            name=zone_def["name"],
            description=zone_def.get("description", ""),
        )
        for region_def in zone_def.get("regions", []):
            tree.create_region(
                region_id=region_def["id"],
                name=region_def["name"],
                description=region_def.get("description", ""),
                parent_zone_id=zone_def["id"],
            )
            for loc_def in region_def.get("locations", []):
                tree.create_location(
                    location_id=loc_def["id"],
                    name=loc_def["name"],
                    description=loc_def.get("description", ""),
                    parent_region_id=region_def["id"],
                )
                for sub_def in loc_def.get("sublocations", []):
                    tree.create_sublocation(
                        sublocation_id=sub_def["id"],
                        name=sub_def["name"],
                        description=sub_def.get("description", ""),
                        parent_location_id=loc_def["id"],
                    )

    return world, tree
