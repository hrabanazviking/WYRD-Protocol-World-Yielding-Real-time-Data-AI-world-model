#!/usr/bin/env python
"""
wyrdforge.inspector_tui — WYRD World Inspector TUI.

Phase 14B built this as ``tools/wyrd_tui.py``, a tool living outside
the engine. Phase E4 (roadmap §3.8) promotes it into the engine's
own supported surface: it now lives in the package, is launched by
the ``wyrd-inspect tui`` console script (or ``python -m
wyrdforge.inspector tui``), and ``tools/wyrd_tui.py`` remains as a
shim so the old invocation keeps working. Rich is an OPTIONAL
dependency (the ``inspector`` extra in pyproject.toml): the data
models and slash-command logic in this module are pure Python, and
without Rich the TUI degrades to a simple CLI — the behaviour it
has always had. The inspector's data features (state diff, entity
timeline, contradiction viewer, durable dead-letter archaeology)
live in :mod:`wyrdforge.inspector`, need no Rich at all, and are
reachable here through the /diff, /timeline, /contradictions and
/deadletters commands when the matching local store paths are
given (--journal / --memory, or an offline world for /diff).

Usage:
    wyrd-inspect tui
    wyrd-inspect tui --world configs/worlds/thornholt.yaml
    wyrd-inspect tui --host 192.168.1.50 --port 8765
    wyrd-inspect tui --offline --world configs/worlds/thornholt.yaml
    python tools/wyrd_tui.py            (legacy shim — same TUI)

Panels:
    World State     — live /world endpoint or loaded YAML summary
    Entity List     — all entities with location and status
    Memory Log      — recent memory entries from /facts
    Bond Graph      — relationship summary between entities
    Command Bar     — slash commands + live persona query

Keyboard:
    Tab / Shift-Tab — switch focus between panels
    r               — refresh all panels
    q / Ctrl-C      — quit
    /               — enter command mode
    ?               — show help overlay
"""
from __future__ import annotations

import argparse
import json
import sys
import textwrap
import time
import urllib.request
import urllib.error
from dataclasses import dataclass, field
from typing import Optional

# ---------------------------------------------------------------------------
# Rich imports — graceful fallback if not installed
# ---------------------------------------------------------------------------

try:
    from rich.console import Console
    from rich.layout import Layout
    from rich.live import Live
    from rich.panel import Panel
    from rich.table import Table
    from rich.text import Text
    from rich.prompt import Prompt
    from rich.columns import Columns
    from rich.rule import Rule
    from rich import box
    _RICH_AVAILABLE = True
except ImportError:
    _RICH_AVAILABLE = False


# ---------------------------------------------------------------------------
# Data models (pure Python — no Rich dependency)
# ---------------------------------------------------------------------------

@dataclass
class EntityInfo:
    entity_id: str
    name: str = ""
    location: str = ""
    status: str = ""
    faction: str = ""

    @classmethod
    def from_dict(cls, d: dict) -> "EntityInfo":
        return cls(
            entity_id=d.get("entity_id", "?"),
            name=d.get("name", ""),
            location=d.get("location", ""),
            status=d.get("status", ""),
            faction=d.get("faction", ""),
        )


@dataclass
class MemoryEntry:
    subject: str
    key: str
    value: str
    source: str = ""

    @classmethod
    def from_dict(cls, d: dict) -> "MemoryEntry":
        return cls(
            subject=d.get("subject_id", "?"),
            key=d.get("key", "?"),
            value=d.get("value", ""),
            source=d.get("source", ""),
        )


@dataclass
class WorldSummary:
    world_name: str = "Unknown"
    entity_count: int = 0
    location_count: int = 0
    zones: list[str] = field(default_factory=list)
    server_status: str = "unknown"   # "online" | "offline" | "error"
    last_refresh: float = 0.0


@dataclass
class TuiState:
    world: WorldSummary = field(default_factory=WorldSummary)
    entities: list[EntityInfo] = field(default_factory=list)
    memories: list[MemoryEntry] = field(default_factory=list)
    last_query_persona: str = ""
    last_query_response: str = ""
    command_log: list[str] = field(default_factory=list)
    error: str = ""
    # Phase E4: the offline world's snapshot at load time — the
    # baseline /diff compares a fresh reload against. A plain-data
    # wyrdforge.inspector.WorldSnapshot; typed as object here so this
    # module's data layer stays free of engine imports at module
    # scope (the snapshot is produced via wyrdforge.inspector).
    baseline_snapshot: object = None
    world_path: str = ""


@dataclass
class InspectorContext:
    """Local store paths backing the Phase E4 inspector commands.

    The TUI's live surface speaks HTTP; the inspector's four features
    read local stores. A context carries the operator-supplied paths
    (--journal / --memory); each command that needs one says so
    plainly when it is absent rather than inventing data. Stores are
    opened lazily per command and never written to.
    """

    journal_path: str = ""
    memory_path: str = ""

    def journal(self):
        from wyrdforge.persistence.event_journal import EventJournal

        return EventJournal(self.journal_path)

    def memory_store(self):
        from wyrdforge.persistence.memory_store import PersistentMemoryStore

        return PersistentMemoryStore(self.memory_path)


# ---------------------------------------------------------------------------
# HTTP client (pure stdlib — no httpx/requests needed)
# ---------------------------------------------------------------------------

class WyrdRelayClient:
    """Thin stdlib HTTP client for WyrdHTTPServer.

    Phase C2: requests go to the versioned ``/v1`` surface by
    default (``api_prefix=""`` selects the server's unversioned
    alias routes).  ``api_token`` — or the ``WYRD_API_TOKEN``
    environment variable when no token is passed — is sent as a
    Bearer header for servers with auth configured.
    """

    def __init__(self, host: str = "localhost", port: int = 8765,
                 timeout: int = 5, api_token: str | None = None,
                 api_prefix: str = "/v1"):
        import os
        self.base_url = f"http://{host}:{port}"
        self.api_prefix = api_prefix
        self.timeout  = timeout
        if api_token is None:
            api_token = os.environ.get("WYRD_API_TOKEN", "")
        self.api_token = api_token or ""

    def _url(self, path: str) -> str:
        return self.base_url + self.api_prefix + path

    def _headers(self) -> dict:
        if self.api_token:
            return {"Authorization": f"Bearer {self.api_token}"}
        return {}

    def _get(self, path: str) -> dict | None:
        try:
            req = urllib.request.Request(
                self._url(path), headers=self._headers(), method="GET",
            )
            with urllib.request.urlopen(
                req, timeout=self.timeout
            ) as resp:
                return json.loads(resp.read().decode())
        except Exception:
            return None

    def _post(self, path: str, body: dict) -> dict | None:
        try:
            data = json.dumps(body).encode()
            req  = urllib.request.Request(
                self._url(path),
                data=data,
                headers={"Content-Type": "application/json",
                         **self._headers()},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                return json.loads(resp.read().decode())
        except Exception:
            return None

    def health(self) -> bool:
        return self._get("/health") is not None

    def world(self) -> dict | None:
        return self._get("/world")

    def facts(self, subject_id: str) -> list[dict]:
        data = self._get(f"/facts?subject_id={subject_id}")
        if isinstance(data, list):
            return data
        if isinstance(data, dict):
            return data.get("facts", [])
        return []

    def query(self, persona_id: str, user_input: str) -> str:
        result = self._post("/query", {
            "persona_id": persona_id,
            "user_input": user_input,
            "use_turn_loop": False,
        })
        if result and "response" in result:
            return result["response"]
        return "(no response)"

    def push_event(self, event_type: str, payload: dict) -> bool:
        result = self._post("/event", {
            "event_type": event_type,
            "payload": payload,
        })
        return result is not None


# ---------------------------------------------------------------------------
# TUI state helpers (pure, no Rich)
# ---------------------------------------------------------------------------

def normalize_persona_id(name: str) -> str:
    """Normalize a name to a WYRD persona_id."""
    import re
    if not name:
        return ""
    result = re.sub(r'[^a-z0-9_]', '_', name.lower())
    result = re.sub(r'_+', '_', result).strip('_')
    return result[:64]


def parse_world_response(data: dict) -> tuple[WorldSummary, list[EntityInfo]]:
    """Parse a /world response into WorldSummary + EntityInfo list."""
    summary = WorldSummary()
    entities = []

    if not data:
        summary.server_status = "offline"
        return summary, entities

    summary.server_status = "online"
    summary.last_refresh   = time.time()
    summary.world_name     = data.get("world_name", data.get("name", "World"))

    raw_entities = data.get("entities", [])
    summary.entity_count = len(raw_entities)

    for e in raw_entities:
        entities.append(EntityInfo.from_dict(e))

    zones = data.get("zones", data.get("hierarchy", {}).get("zones", []))
    if isinstance(zones, list):
        summary.zones = [z.get("name", z) if isinstance(z, dict) else z
                         for z in zones]
    summary.location_count = data.get("location_count", 0)

    return summary, entities


def parse_facts_response(data: list[dict]) -> list[MemoryEntry]:
    """Parse a /facts response into MemoryEntry list."""
    return [MemoryEntry.from_dict(d) for d in data]


def format_uptime(seconds: float) -> str:
    """Format seconds since last refresh."""
    if seconds < 60:
        return f"{int(seconds)}s ago"
    return f"{int(seconds // 60)}m ago"


def build_command_help() -> list[tuple[str, str]]:
    return [
        ("/who <location>",    "list entities at location"),
        ("/where <entity>",    "show entity's location"),
        ("/facts <subject>",   "show facts for subject"),
        ("/query <persona> <text>", "query WYRD for world context"),
        ("/push obs <title> <summary>", "push observation event"),
        ("/refresh",           "refresh all panels"),
        ("/world",             "show world summary"),
        ("/diff",              "diff offline world vs its load-time snapshot (E4)"),
        ("/timeline <entity>", "entity timeline from the durable journal (E4)"),
        ("/contradictions [--all]", "view contradiction records (E4)"),
        ("/deadletters",       "durable dead-letter archaeology (E4)"),
        ("/clear",             "clear command log"),
        ("/help",              "show this help"),
        ("/quit",              "exit TUI"),
    ]


def handle_tui_command(
    cmd: str,
    state: TuiState,
    client: Optional["WyrdRelayClient"],
    inspector: Optional["InspectorContext"] = None,
) -> str:
    """
    Process a TUI slash command. Returns a string to append to command log.
    Pure logic — no Rich or I/O side effects.

    Phase E4: the optional ``inspector`` context (keyword-only in
    effect — existing 3-argument callers are unchanged) backs the
    /diff, /timeline, /contradictions and /deadletters commands with
    the wyrdforge.inspector data surfaces over local stores.
    """
    parts = cmd.strip().split(maxsplit=1)
    if not parts:
        return ""
    verb = parts[0].lower()
    arg  = parts[1].strip() if len(parts) > 1 else ""

    if verb in ("/quit", "/exit", "/q"):
        return "__QUIT__"

    if verb == "/help":
        lines = [f"  {c}  — {d}" for c, d in build_command_help()]
        return "Commands:\n" + "\n".join(lines)

    if verb == "/clear":
        state.command_log.clear()
        return "(log cleared)"

    if verb == "/refresh":
        if client:
            data = client.world()
            if data:
                state.world, state.entities = parse_world_response(data)
                return f"Refreshed: {state.world.entity_count} entities"
            return "(server offline)"
        return "(offline mode)"

    if verb == "/world":
        w = state.world
        return (f"World: {w.world_name} | "
                f"Entities: {w.entity_count} | "
                f"Locations: {w.location_count} | "
                f"Status: {w.server_status}")

    if verb == "/who":
        loc = arg or "(all)"
        matches = [e for e in state.entities
                   if not arg or loc.lower() in e.location.lower()]
        if not matches:
            return f"Nobody at {loc!r}"
        lines = [f"  • {e.name or e.entity_id} ({e.entity_id}) @ {e.location}"
                 for e in matches]
        return f"At {loc}:\n" + "\n".join(lines)

    if verb == "/where":
        if not arg:
            return "Usage: /where <entity_id>"
        matches = [e for e in state.entities
                   if arg.lower() in e.entity_id.lower()
                   or arg.lower() in (e.name or "").lower()]
        if not matches:
            return f"Entity {arg!r} not found"
        e = matches[0]
        return f"{e.name or e.entity_id} ({e.entity_id}) is at: {e.location or '(unknown)'}"

    if verb == "/facts":
        if not arg:
            return "Usage: /facts <subject_id>"
        if client:
            raw = client.facts(arg)
            state.memories = parse_facts_response(raw)
            if not state.memories:
                return f"No facts for {arg!r}"
            lines = [f"  {m.key} = {m.value}" for m in state.memories[:20]]
            return f"Facts for {arg}:\n" + "\n".join(lines)
        return "(offline mode — no server)"

    if verb == "/query":
        sub_parts = arg.split(maxsplit=1)
        if not sub_parts:
            return "Usage: /query <persona_id> <text>"
        persona = sub_parts[0]
        text    = sub_parts[1] if len(sub_parts) > 1 else ""
        if client:
            resp = client.query(persona, text)
            state.last_query_persona  = persona
            state.last_query_response = resp
            return f"[{persona}] {resp[:200]}"
        return "(offline mode — no server)"

    if verb == "/push":
        sub_parts = arg.split(maxsplit=2)
        if len(sub_parts) < 3 or sub_parts[0] != "obs":
            return "Usage: /push obs <title> <summary>"
        title, summary = sub_parts[1], sub_parts[2]
        if client:
            ok = client.push_event("observation", {"title": title, "summary": summary})
            return f"Pushed observation: {title!r} — {'ok' if ok else 'failed'}"
        return "(offline mode)"

    # -- Phase E4 inspector commands (wyrdforge.inspector surfaces) --

    if verb == "/diff":
        if state.baseline_snapshot is None or not state.world_path:
            return ("(diff needs an offline world: launch with "
                    "--offline --world <yaml>, or use "
                    "wyrd-inspect snapshot + wyrd-inspect diff)")
        from wyrdforge import inspector as _insp

        _summary, _entities, fresh = _load_offline_world(state.world_path)
        if fresh is None:
            return "(diff failed: the offline world no longer loads)"
        return _insp.format_diff(
            _insp.diff_snapshots(state.baseline_snapshot, fresh)
        )

    if verb == "/timeline":
        if not arg:
            return "Usage: /timeline <entity_id>"
        if inspector is None or not inspector.journal_path:
            return "(timeline needs the durable journal: launch with --journal <journal.db>)"
        from wyrdforge import inspector as _insp

        entries = _insp.entity_timeline(inspector.journal(), arg)
        return _insp.format_timeline(entries, arg)

    if verb == "/contradictions":
        if inspector is None or not inspector.memory_path:
            return "(contradictions need the memory store: launch with --memory <memory.db>)"
        from wyrdforge import inspector as _insp

        views = _insp.contradiction_views(
            inspector.memory_store(), include_resolved=(arg == "--all")
        )
        return _insp.format_contradictions(views)

    if verb == "/deadletters":
        if inspector is None or not inspector.journal_path:
            return "(dead-letter archaeology needs the journal: launch with --journal <journal.db>)"
        from wyrdforge import inspector as _insp

        report = _insp.dead_letter_archaeology(inspector.journal())
        return _insp.format_dead_letters(report)

    return f"Unknown command: {verb!r} (type /help)"


# ---------------------------------------------------------------------------
# Rich TUI renderer
# ---------------------------------------------------------------------------

def _build_layout() -> "Layout":
    layout = Layout(name="root")
    layout.split_column(
        Layout(name="header", size=3),
        Layout(name="body"),
        Layout(name="footer", size=6),
    )
    layout["body"].split_row(
        Layout(name="left"),
        Layout(name="right"),
    )
    layout["left"].split_column(
        Layout(name="world_state", ratio=2),
        Layout(name="entity_list", ratio=3),
    )
    layout["right"].split_column(
        Layout(name="memory_log", ratio=3),
        Layout(name="query_panel", ratio=2),
    )
    return layout


def _render_header(state: TuiState) -> "Panel":
    status_color = {"online": "green", "offline": "red", "error": "yellow",
                    "unknown": "dim"}.get(state.world.server_status, "dim")
    status = Text(f"● {state.world.server_status.upper()}", style=status_color)
    title  = Text(" WYRD World Editor  ", style="bold cyan")
    world  = Text(f"  {state.world.world_name}", style="bold white")
    return Panel(Columns([title, world, status]), style="cyan")


def _render_world_state(state: TuiState) -> "Panel":
    w = state.world
    t = Table(show_header=False, box=None, padding=(0, 1))
    t.add_column("key",   style="bold dim",   no_wrap=True)
    t.add_column("value", style="white")
    t.add_row("World",     w.world_name)
    t.add_row("Entities",  str(w.entity_count))
    t.add_row("Locations", str(w.location_count))
    t.add_row("Zones",     ", ".join(w.zones[:5]) or "—")
    t.add_row("Refreshed",
              format_uptime(time.time() - w.last_refresh)
              if w.last_refresh else "never")
    if state.error:
        t.add_row("Error", Text(state.error[:60], style="red"))
    return Panel(t, title="[bold]World State[/bold]", border_style="blue")


def _render_entity_list(state: TuiState) -> "Panel":
    t = Table(box=box.SIMPLE_HEAVY, show_header=True, header_style="bold cyan")
    t.add_column("ID",       style="dim",    max_width=18)
    t.add_column("Name",     style="white",  max_width=16)
    t.add_column("Location", style="green",  max_width=20)
    t.add_column("Status",   style="yellow", max_width=12)
    for e in state.entities[:20]:
        t.add_row(
            e.entity_id[:18],
            e.name[:16] or "—",
            e.location[:20] or "—",
            e.status[:12] or "—",
        )
    if not state.entities:
        t.add_row("—", "(no entities)", "—", "—")
    return Panel(t, title="[bold]Entities[/bold]", border_style="green")


def _render_memory_log(state: TuiState) -> "Panel":
    t = Table(box=box.SIMPLE, show_header=True, header_style="bold magenta")
    t.add_column("Subject", style="dim",     max_width=16)
    t.add_column("Key",     style="magenta", max_width=14)
    t.add_column("Value",   style="white",   max_width=30)
    for m in state.memories[:15]:
        t.add_row(m.subject[:16], m.key[:14], m.value[:30])
    if not state.memories:
        t.add_row("—", "(use /facts <id>)", "—")
    return Panel(t, title="[bold]Memory Log[/bold]", border_style="magenta")


def _render_query_panel(state: TuiState) -> "Panel":
    lines = []
    if state.last_query_persona:
        lines.append(Text(f"Persona: {state.last_query_persona}", style="bold cyan"))
        for line in textwrap.wrap(state.last_query_response or "(no response)", width=50):
            lines.append(Text(line, style="white"))
    else:
        lines.append(Text("Type /query <persona_id> <text>", style="dim"))
    # Command log (last 4 entries)
    lines.append(Text(""))
    for entry in state.command_log[-4:]:
        for line in textwrap.wrap(entry, width=50):
            lines.append(Text(line[:50], style="dim"))

    from rich.console import Group
    return Panel(Group(*lines), title="[bold]Query / Log[/bold]", border_style="yellow")


def _render_footer() -> "Panel":
    keys = (
        "[bold]Tab[/bold] switch panel  "
        "[bold]r[/bold] refresh  "
        "[bold]/[/bold] command  "
        "[bold]?[/bold] help  "
        "[bold]q[/bold] quit"
    )
    return Panel(Text.from_markup(keys), style="dim")


def _render_all(layout: "Layout", state: TuiState) -> None:
    layout["header"].update(_render_header(state))
    layout["world_state"].update(_render_world_state(state))
    layout["entity_list"].update(_render_entity_list(state))
    layout["memory_log"].update(_render_memory_log(state))
    layout["query_panel"].update(_render_query_panel(state))
    layout["footer"].update(_render_footer())


# ---------------------------------------------------------------------------
# Offline world loader
# ---------------------------------------------------------------------------

def _load_offline_world(world_path: str):
    """Load a world YAML directly (offline mode, no server needed).

    Returns ``(WorldSummary, list[EntityInfo], WorldSnapshot | None)``
    — Phase E4 adds the snapshot (the /diff baseline) to the pair
    this loader has always returned.
    """
    try:
        import sys as _sys
        # Bare-checkout support: this module lives in src/wyrdforge/,
        # so src/ is two levels up. (When the package is installed
        # the insert is a harmless no-op.)
        _sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent.parent))

        from wyrdforge.ecs.components.character import FactionComponent, HealthComponent  # noqa
        from wyrdforge.ecs.components.identity import (  # noqa
            DescriptionComponent, NameComponent, StatusComponent)
        from wyrdforge.ecs.components.physical import InventoryComponent, PhysicalComponent  # noqa
        from wyrdforge.ecs.components.spatial import (  # noqa
            ContainerComponent, ParentComponent, SpatialComponent)
        from wyrdforge.ecs.world import World
        from wyrdforge.loaders.world_loader import load_world_from_yaml

        world = World()
        load_world_from_yaml(world_path, world)
        entities = []
        for eid, ent in world.entities.items():
            name_c  = ent.get_component("NameComponent")
            stat_c  = ent.get_component("StatusComponent")
            spat_c  = ent.get_component("SpatialComponent")
            fact_c  = ent.get_component("FactionComponent")
            entities.append(EntityInfo(
                entity_id=eid,
                name=name_c.name if name_c else "",
                location=spat_c.location_id if spat_c else "",
                status=stat_c.status if stat_c else "",
                faction=fact_c.faction if fact_c else "",
            ))

        summary = WorldSummary(
            world_name=world_path.split("/")[-1].replace(".yaml", ""),
            entity_count=len(entities),
            server_status="offline (local)",
            last_refresh=time.time(),
        )
        from wyrdforge.inspector import snapshot_world

        return summary, entities, snapshot_world(world)
    except Exception as e:
        s = WorldSummary(server_status="error", world_name="(load failed)")
        return s, [], None


# ---------------------------------------------------------------------------
# Main TUI loop
# ---------------------------------------------------------------------------

def run_tui(args: argparse.Namespace) -> None:
    if not _RICH_AVAILABLE:
        # Graceful degradation (the module's standing contract):
        # without Rich there is no Console to print with — the
        # pre-E4 code constructed Console() BEFORE this check, so
        # the fallback raised NameError instead of degrading
        # (defect found and fixed in E4; pinned by
        # tests/test_world_inspector.py).
        print("Rich is not installed. Install with: "
              "pip install wyrdforge[inspector]")
        print("Falling back to simple CLI mode.\n")
        _run_simple_cli(args)
        return

    console = Console()

    # Initialise state
    state  = TuiState()
    client: Optional[WyrdRelayClient] = None
    inspector = InspectorContext(
        journal_path=getattr(args, "journal", "") or "",
        memory_path=getattr(args, "memory", "") or "",
    )

    if not args.offline:
        client = WyrdRelayClient(args.host, args.port)
        if client.health():
            data = client.world()
            state.world, state.entities = parse_world_response(data or {})
        else:
            state.world.server_status = "offline"
            state.error = f"WyrdHTTPServer not reachable at {args.host}:{args.port}"

    if args.offline or args.world:
        if args.world:
            state.world_path = args.world
            (state.world, state.entities,
             state.baseline_snapshot) = _load_offline_world(args.world)

    layout = _build_layout()
    _render_all(layout, state)

    with Live(layout, console=console, refresh_per_second=2, screen=True) as live:
        while True:
            try:
                _render_all(layout, state)
                live.refresh()

                cmd = Prompt.ask("[bold cyan]»[/bold cyan]",
                                 console=console, default="")
                if not cmd:
                    continue

                if cmd.strip().lower() in ("q", "quit", "exit"):
                    break

                if cmd.strip() == "r":
                    cmd = "/refresh"

                if cmd.startswith("/"):
                    result = handle_tui_command(cmd, state, client, inspector)
                    if result == "__QUIT__":
                        break
                    if result:
                        state.command_log.append(result)
                else:
                    # Bare text → quick query using last persona or default
                    persona = state.last_query_persona or "player"
                    result  = handle_tui_command(f"/query {persona} {cmd}", state, client, inspector)
                    state.command_log.append(result)

            except KeyboardInterrupt:
                break

    console.print("\n[cyan]Farewell from the WYRD World Editor.[/cyan]")


def _run_simple_cli(args: argparse.Namespace) -> None:
    """Minimal fallback when Rich is not installed."""
    print("WYRD World Inspector — simple mode (install rich for full TUI: "
          "pip install wyrdforge[inspector])")
    client = WyrdRelayClient(args.host, args.port) if not args.offline else None
    state  = TuiState()
    inspector = InspectorContext(
        journal_path=getattr(args, "journal", "") or "",
        memory_path=getattr(args, "memory", "") or "",
    )
    if getattr(args, "world", ""):
        state.world_path = args.world
        (state.world, state.entities,
         state.baseline_snapshot) = _load_offline_world(args.world)

    if client and client.health():
        data = client.world()
        state.world, state.entities = parse_world_response(data or {})
        print(f"Connected: {state.world.world_name} ({state.world.entity_count} entities)")
    else:
        print("Server offline. Type /help for commands.")

    while True:
        try:
            cmd = input("» ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if not cmd:
            continue
        result = handle_tui_command(cmd if cmd.startswith("/") else f"/query player {cmd}",
                                    state, client, inspector)
        if result == "__QUIT__":
            break
        if result:
            print(result)


# ---------------------------------------------------------------------------
# Argument parsing
# ---------------------------------------------------------------------------

def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="WYRD World Inspector TUI")
    p.add_argument("--host",    default="localhost", help="WyrdHTTPServer host")
    p.add_argument("--port",    type=int, default=8765, help="WyrdHTTPServer port")
    p.add_argument("--world",   default="", help="Path to world YAML (offline mode)")
    p.add_argument("--offline", action="store_true",
                   help="Offline mode — load world YAML directly without server")
    p.add_argument("--timeout", type=int, default=5, help="HTTP timeout seconds")
    p.add_argument("--journal", default="",
                   help="Path to a B4 event journal DB (enables /timeline, /deadletters)")
    p.add_argument("--memory",  default="",
                   help="Path to a memory store DB (enables /contradictions)")
    return p.parse_args(argv)


def run_from_args(args: argparse.Namespace) -> None:
    """Entry point for wyrdforge.inspector's ``tui`` subcommand.

    ``args`` is the inspector CLI's namespace (host/port/world/
    offline/timeout/journal/memory) — the same attribute names this
    module's own parser produces.
    """
    run_tui(args)


def main(argv: list[str] | None = None) -> None:
    """Console entry point (``wyrd-inspect-tui``) and module main."""
    run_tui(_parse_args(argv))


if __name__ == "__main__":
    main()
