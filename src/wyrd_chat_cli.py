#!/usr/bin/env python
"""WYRD Chat CLI — interactive conversation loop with LLM + world context.

Usage:
    python wyrd_chat_cli.py
    python wyrd_chat_cli.py --world configs/worlds/thornholt.yaml
    python wyrd_chat_cli.py --model mistral --entity gunnar

Slash commands:
    /who [location]   — list entities at a location (default: current)
    /where <entity>   — show entity's spatial location
    /facts <subject>  — show canonical facts for a subject
    /world            — print full world context packet
    /history          — show conversation turn count
    /clear            — clear conversation history
    /help             — show this help
    /exit or /quit    — exit
"""
from __future__ import annotations

import argparse
import sys
import tempfile
from pathlib import Path

# Import all component types to populate the ECS registry before loading worlds
from wyrdforge.ecs.components.character import FactionComponent, HealthComponent  # noqa: F401
from wyrdforge.ecs.components.identity import (  # noqa: F401
    DescriptionComponent,
    NameComponent,
    StatusComponent,
)
from wyrdforge.ecs.components.physical import InventoryComponent, PhysicalComponent  # noqa: F401
from wyrdforge.ecs.components.spatial import (  # noqa: F401
    ContainerComponent,
    ParentComponent,
    SpatialComponent,
)
from wyrdforge.ecs.world import World
from wyrdforge.ecs.yggdrasil import YggdrasilTree
from wyrdforge.llm.ollama_connector import OllamaConnector, OllamaUnavailableError
from wyrdforge.loaders.world_loader import load_world_from_yaml
from wyrdforge.oracle.passive_oracle import PassiveOracle
from wyrdforge.persistence.memory_store import PersistentMemoryStore
from wyrdforge.services.contradiction_detector import ContradictionDetector
from wyrdforge.services.writeback_engine import WritebackEngine
from wyrdforge.runtime.turn_loop import TurnLoop


_BANNER = """
╔══════════════════════════════════════════════════════╗
║             WYRD Protocol — Chat Runtime             ║
║      World-Yielding Real-time Data · AI World Model  ║
╚══════════════════════════════════════════════════════╝
"""

_HELP = """
Commands:
  /who [location_id]   — entities at location (default: focus entity's location)
  /where <entity_id>   — show spatial location of an entity
  /facts <subject_id>  — canonical facts for a subject
  /world               — full world context packet for current focus
  /history             — show conversation turn count
  /clear               — clear conversation history
  /help                — show this help
  /exit | /quit        — exit

Type anything else to talk to the character.
"""


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="WYRD Chat CLI")
    p.add_argument(
        "--world",
        default="configs/worlds/thornholt.yaml",
        help="Path to world YAML file",
    )
    p.add_argument(
        "--model",
        default="llama3",
        help="Ollama model name (default: llama3)",
    )
    p.add_argument(
        "--entity",
        default="",
        help="Focus entity ID for context packets",
    )
    p.add_argument(
        "--location",
        default="",
        help="Default location ID for context packets",
    )
    p.add_argument(
        "--persona",
        default="",
        help="Persona name injected into system prompt",
    )
    p.add_argument(
        "--ollama-host",
        default="localhost",
        help="Ollama server hostname",
    )
    p.add_argument(
        "--ollama-port",
        type=int,
        default=11434,
        help="Ollama server port",
    )
    p.add_argument(
        "--db",
        default="",
        help="Path to memory SQLite DB (default: temp file)",
    )
    return p.parse_args()


def _handle_slash(
    cmd: str,
    oracle: PassiveOracle,
    turn_loop: TurnLoop,
    default_location: str,
) -> None:
    parts = cmd.strip().split(maxsplit=1)
    verb = parts[0].lower()
    arg = parts[1] if len(parts) > 1 else ""

    if verb == "/help":
        print(_HELP)

    elif verb == "/who":
        loc = arg.strip() or default_location
        if not loc:
            print("  [no location — use /who <location_id>]")
            return
        entities = oracle.who_is_here(loc)
        if not entities:
            print(f"  (nobody at {loc!r})")
        else:
            for e in entities:
                name = e.name or e.entity_id
                status = f" [{e.status}]" if e.status else ""
                print(f"  • {name} ({e.entity_id}){status}")

    elif verb == "/where":
        if not arg:
            print("  Usage: /where <entity_id>")
            return
        result = oracle.where_is(arg.strip())
        if result is None:
            print(f"  Entity {arg!r} not found in world.")
        elif result.location_id is None:
            print(f"  {arg} has no spatial placement.")
        else:
            path = " → ".join(result.path) if result.path else result.location_id
            name = result.location_name or result.location_id
            print(f"  {arg} is at: {name} ({result.location_id})")
            print(f"  Path: {path}")

    elif verb == "/facts":
        if not arg:
            print("  Usage: /facts <subject_id>")
            return
        facts = oracle.get_facts(arg.strip())
        if not facts:
            print(f"  No facts for {arg!r}.")
        else:
            for f in facts:
                p = f.content.structured_payload
                print(f"  • {p.fact_key} = {p.fact_value}  (conf: {f.truth.confidence:.2f})")

    elif verb == "/world":
        packet = oracle.build_context_packet(
            focus_entity_ids=[turn_loop._focus_entity_id] if turn_loop._focus_entity_id else [],
            location_id=default_location or None,
        )
        print(packet.formatted_for_llm)

    elif verb == "/history":
        count = turn_loop.history_turn_count()
        print(f"  {count} turn(s) in history.")

    elif verb == "/clear":
        turn_loop.clear_history()
        print("  History cleared.")

    elif verb in ("/exit", "/quit"):
        # Handled by main loop
        pass

    else:
        print(f"  Unknown command: {verb!r} — type /help for commands.")


def main() -> None:
    args = _parse_args()
    print(_BANNER)

    # Load world
    world_path = Path(args.world)
    if world_path.exists():
        world, yggdrasil = load_world_from_yaml(world_path)
        print(f"  World loaded: {world.world_name} ({world.entity_count()} entities)")
    else:
        print(f"  [Warning] World file not found: {world_path} — using empty world.")
        world = World("empty_world", "Empty World")
        yggdrasil = YggdrasilTree(world)

    # Memory store
    db_path = args.db or tempfile.mktemp(suffix=".db")
    store = PersistentMemoryStore(db_path)
    engine = WritebackEngine(store)
    detector = ContradictionDetector(store)

    # Oracle
    oracle = PassiveOracle(world, store, yggdrasil=yggdrasil)

    # Connector
    connector = OllamaConnector(
        host=args.ollama_host,
        port=args.ollama_port,
        model=args.model,
    )
    available = connector.is_available()
    if available:
        print(f"  Ollama: connected at {connector.base_url} (model: {args.model})")
    else:
        print(
            f"  [Warning] Ollama not reachable at {connector.base_url}. "
            "Turns will return an error message."
        )

    # Turn loop
    default_location = args.location
    turn_loop = TurnLoop(
        oracle,
        engine,
        detector,
        connector,
        focus_entity_id=args.entity,
        location_id=default_location or None,
        persona_name=args.persona,
    )

    print(f"  DB: {db_path}")
    if args.entity:
        print(f"  Focus entity: {args.entity}")
    if default_location:
        print(f"  Location: {default_location}")
    print("\n  Type /help for commands, /exit to quit.\n")

    # REPL
    while True:
        try:
            user_input = input("You: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n  Farewell.")
            break

        if not user_input:
            continue

        if user_input.lower() in ("/exit", "/quit"):
            print("  Farewell.")
            break

        if user_input.startswith("/"):
            _handle_slash(user_input, oracle, turn_loop, default_location)
            continue

        # Execute turn
        result = turn_loop.execute_turn(user_input)
        print(f"\nWYRD: {result.assistant_response}\n")

        if result.contradictions_found:
            print(f"  [!] {result.contradictions_found} contradiction(s) detected this turn.")
        if result.error:
            print(f"  [error] {result.error}")


if __name__ == "__main__":
    main()
