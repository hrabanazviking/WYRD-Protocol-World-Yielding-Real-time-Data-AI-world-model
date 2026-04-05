#!/usr/bin/env python3
"""wyrd_world_cli.py — Interactive WYRD Protocol world explorer.

Usage:
    python wyrd_world_cli.py --world configs/worlds/thornholt.yaml
    python wyrd_world_cli.py --world configs/worlds/thornholt.yaml --save data/thornholt.db
    python wyrd_world_cli.py --load data/thornholt.db --world-id thornholt
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Ensure src/ is on path when running from repo root
sys.path.insert(0, str(Path(__file__).parent / "src"))

# Import component registrations so deserializer knows about all types
import wyrdforge.ecs.components.identity  # noqa: F401
import wyrdforge.ecs.components.spatial   # noqa: F401
import wyrdforge.ecs.components.physical  # noqa: F401
import wyrdforge.ecs.components.character # noqa: F401

from wyrdforge.ecs.components.character import FactionComponent, HealthComponent, PersonaRefComponent
from wyrdforge.ecs.components.identity import DescriptionComponent, NameComponent, StatusComponent
from wyrdforge.ecs.components.physical import InventoryComponent, PhysicalComponent
from wyrdforge.ecs.components.spatial import SpatialComponent
from wyrdforge.ecs.world import World
from wyrdforge.ecs.yggdrasil import YggdrasilTree
from wyrdforge.loaders.world_loader import load_world_from_yaml
from wyrdforge.persistence.world_store import WorldStore


def _get_name(world: World, entity_id: str) -> str:
    comp = world.get_component(entity_id, "name")
    if isinstance(comp, NameComponent):
        return comp.name
    return entity_id[:12]


def _get_desc(world: World, entity_id: str) -> str:
    comp = world.get_component(entity_id, "description")
    if isinstance(comp, DescriptionComponent):
        return comp.short_desc
    return ""


def cmd_tree(world: World, tree: YggdrasilTree, _args: list[str]) -> None:
    print("\n" + tree.describe_tree() + "\n")


def cmd_look(world: World, tree: YggdrasilTree, args: list[str]) -> None:
    if not args:
        print("Usage: look <location_id>")
        return
    loc_id = args[0]
    entity = world.get_entity(loc_id)
    if entity is None:
        print(f"  Unknown location: {loc_id}")
        return
    name = _get_name(world, loc_id)
    desc = _get_desc(world, loc_id)
    print(f"\n  [{name}]")
    if desc:
        print(f"  {desc}")
    present = tree.entities_at(loc_id)
    if present:
        print(f"\n  Present: {', '.join(_get_name(world, e.entity_id) for e in present)}")
    children = [c for c in tree.get_children(loc_id) if c.has_tag("spatial_node")]
    if children:
        print(f"  Sub-areas: {', '.join(_get_name(world, c.entity_id) for c in children)}")
    print()


def cmd_spawn(world: World, tree: YggdrasilTree, args: list[str]) -> None:
    if len(args) < 3:
        print("Usage: spawn <entity_id> <name> <location_id> [tags...]")
        return
    entity_id, name, location_id = args[0], args[1], args[2]
    extra_tags = set(args[3:]) if len(args) > 3 else set()
    try:
        entity = world.create_entity(entity_id=entity_id, tags={"character"} | extra_tags)
        world.add_component(entity_id, NameComponent(entity_id=entity_id, name=name))
        world.add_component(entity_id, StatusComponent(entity_id=entity_id, state="idle"))
        world.add_component(entity_id, HealthComponent(entity_id=entity_id))
        world.add_component(entity_id, InventoryComponent(entity_id=entity_id))
        tree.place_entity(entity_id, location_id=location_id)
        print(f"  Spawned '{name}' ({entity_id}) at {location_id}")
    except (ValueError, KeyError) as exc:
        print(f"  Error: {exc}")


def cmd_move(world: World, tree: YggdrasilTree, args: list[str]) -> None:
    if len(args) < 2:
        print("Usage: move <entity_id> <location_id> [sublocation_id]")
        return
    entity_id = args[0]
    location_id = args[1]
    sublocation_id = args[2] if len(args) > 2 else None
    try:
        tree.move_entity(entity_id, location_id=location_id, sublocation_id=sublocation_id)
        name = _get_name(world, entity_id)
        dest = sublocation_id or location_id
        print(f"  Moved '{name}' to {dest}")
    except (KeyError, ValueError) as exc:
        print(f"  Error: {exc}")


def cmd_who(world: World, tree: YggdrasilTree, args: list[str]) -> None:
    if not args:
        print("Usage: who <location_id>")
        return
    loc_id = args[0]
    present = tree.entities_at(loc_id)
    if not present:
        print(f"  Nobody at {loc_id}")
    else:
        print(f"  At {loc_id}:")
        for e in present:
            name = _get_name(world, e.entity_id)
            status = world.get_component(e.entity_id, "status")
            state = status.state if isinstance(status, StatusComponent) else "?"
            print(f"    {name} ({e.entity_id}) — {state}")


def cmd_find(world: World, tree: YggdrasilTree, args: list[str]) -> None:
    if not args:
        print("Usage: find <name_fragment>")
        return
    query = " ".join(args)
    results = tree.find_by_name(query)
    if not results:
        print(f"  No spatial nodes matching '{query}'")
    else:
        for e in results:
            print(f"  {_get_name(world, e.entity_id)} ({e.entity_id}) tags={sorted(e.tags)}")


def cmd_info(world: World, tree: YggdrasilTree, args: list[str]) -> None:
    if not args:
        print("Usage: info <entity_id>")
        return
    entity_id = args[0]
    entity = world.get_entity(entity_id)
    if entity is None:
        print(f"  Entity '{entity_id}' not found")
        return
    print(f"\n  Entity: {entity_id}")
    print(f"  Tags:   {sorted(entity.tags)}")
    print(f"  Active: {entity.active}")
    comps = world.get_all_components(entity_id)
    print(f"  Components ({len(comps)}):")
    for comp in comps:
        print(f"    [{comp.component_type}]")
        for field_name in comp.model_fields:
            if field_name in ("component_type", "entity_id", "schema_version", "created_at", "updated_at"):
                continue
            val = getattr(comp, field_name)
            if val not in (None, [], {}, ""):
                print(f"      {field_name}: {val}")
    print()


def cmd_help(_world: World, _tree: YggdrasilTree, _args: list[str]) -> None:
    print("""
  Commands:
    tree                            — Show the full Yggdrasil spatial tree
    look  <location_id>             — Describe a location and who is there
    who   <location_id>             — List entities at a location
    find  <name_fragment>           — Find spatial nodes by name
    spawn <id> <name> <loc> [tags]  — Create a character entity at a location
    move  <entity_id> <loc> [sub]   — Move entity to a new location
    info  <entity_id>               — Show all components for an entity
    save                            — Save world to DB (if --save given)
    help                            — Show this help
    quit / exit                     — Exit
""")


def run_repl(world: World, tree: YggdrasilTree, store: WorldStore | None, world_id: str) -> None:
    COMMANDS = {
        "tree":  cmd_tree,
        "look":  cmd_look,
        "who":   cmd_who,
        "find":  cmd_find,
        "spawn": cmd_spawn,
        "move":  cmd_move,
        "info":  cmd_info,
        "help":  cmd_help,
    }
    entity_count = world.entity_count()
    print(f"\n  WYRD Protocol — {world.world_name}")
    print(f"  {entity_count} entities loaded. Type 'help' for commands.\n")

    while True:
        try:
            line = input("wyrd> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n  Farewell.")
            break
        if not line:
            continue
        parts = line.split()
        cmd, args = parts[0].lower(), parts[1:]
        if cmd in ("quit", "exit", "q"):
            print("  Farewell.")
            break
        elif cmd == "save":
            if store is None:
                print("  No --save path specified. Start with --save <path> to enable saving.")
            else:
                store.save(world)
                print(f"  World saved to {store._db_path}")
        elif cmd in COMMANDS:
            COMMANDS[cmd](world, tree, args)
        else:
            print(f"  Unknown command '{cmd}'. Type 'help' for commands.")


def main() -> None:
    parser = argparse.ArgumentParser(description="WYRD Protocol world explorer")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--world", metavar="YAML", help="Load world from YAML config")
    group.add_argument("--load", metavar="DB", help="Load world from SQLite DB")
    parser.add_argument("--world-id", metavar="ID", help="World ID (required with --load)")
    parser.add_argument("--save", metavar="DB", help="Save world to SQLite DB on 'save' command")
    args = parser.parse_args()

    store: WorldStore | None = None
    if args.save:
        store = WorldStore(args.save)

    if args.world:
        world, tree = load_world_from_yaml(args.world)
        if store:
            store.save(world)
    else:
        if not args.world_id:
            parser.error("--world-id is required when using --load")
        if not store:
            store = WorldStore(args.load)
        world = store.load(args.world_id)
        tree = YggdrasilTree(world)

    run_repl(world, tree, store, world.world_id)


if __name__ == "__main__":
    main()
