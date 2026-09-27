from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

import yaml

from wyrdforge.ecs.world import World
from wyrdforge.ecs.yggdrasil import YggdrasilTree
from wyrdforge.hardening.config_validator import (
    ConfigValidationError,
    validate_world_config,
)
from wyrdforge.hardening.input_validation import (
    MAX_WORLD_DEPTH,
    MAX_WORLD_FILE_BYTES,
    InputValidationError,
    check_depth,
)


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

    # Pre-parse cap: the only thing that must hold before the parser
    # runs. Small-file bombs (deep bracket nesting, alias webs) are
    # caught after parsing by the iterative depth gate and the
    # schema's unknown-field rejection below.
    if config_path.stat().st_size > MAX_WORLD_FILE_BYTES:
        raise ConfigValidationError(
            f"world file size exceeds {MAX_WORLD_FILE_BYTES} bytes "
            f"({config_path.stat().st_size})",
            field="$",
        )

    try:
        with config_path.open("r", encoding="utf-8") as fh:
            config = yaml.safe_load(fh)
    except yaml.YAMLError as exc:
        raise ConfigValidationError(
            f"world file {config_path.name}: invalid YAML document: {exc}",
            field="$",
        ) from exc
    except UnicodeDecodeError as exc:
        raise ConfigValidationError(
            f"world file {config_path.name}: not valid UTF-8: {exc}",
            field="$",
        ) from exc

    if not isinstance(config, dict):
        raise ConfigValidationError(
            f"world config must be a mapping, got {type(config).__name__}",
            field="$",
        )

    # Iterative depth gate before anything recurses over the document
    # (deepcopy, schema walk). Bracket-nesting bombs die here with the
    # file named — not as a bare RecursionError deep in the stdlib.
    try:
        check_depth(config, max_depth=MAX_WORLD_DEPTH, field="$")
    except InputValidationError as exc:
        raise ConfigValidationError(
            f"world file {config_path.name}: {exc.reason}",
            field=exc.field,
        ) from exc

    # Historical loader defaults: filename stem for a missing world_id,
    # world_name falling back to world_id. Normalized onto a copy so
    # the raw document is untouched; the validator then enforces the
    # canonical schema on the normalized form.
    normalized = copy.deepcopy(config)
    normalized["world_id"] = normalized.get("world_id") or config_path.stem
    normalized["world_name"] = normalized.get("world_name",
                                              normalized["world_id"])
    validate_world_config(normalized)

    world_id = normalized["world_id"]
    world_name = normalized["world_name"]
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
