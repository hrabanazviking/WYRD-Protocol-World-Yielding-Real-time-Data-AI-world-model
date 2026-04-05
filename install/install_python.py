"""install_python.py — 16A: WYRD installers for Python-based targets.

Covers: pygame (Volmarr's fork), NorseSagaEngine, Viking Girlfriend Skill (OpenClaw).
"""
from __future__ import annotations

from pathlib import Path

from _common import BaseInstaller, find_dir_by_markers


# ---------------------------------------------------------------------------
# pygame
# ---------------------------------------------------------------------------

class PygameInstaller(BaseInstaller):
    """Install the WYRD pygame bridge into a pygame project directory."""

    name = "pygame"
    description = "WYRD bridge for pygame (github.com/hrabanazviking/pygame fork)"

    def detect_candidates(self, search_paths: list[Path]) -> list[Path]:
        return find_dir_by_markers(
            search_paths,
            ["pygame", "requirements.txt"],
            require_all=False,
        ) + find_dir_by_markers(
            search_paths,
            ["main.py", "game.py"],
            require_all=False,
        )

    def files_to_install(self, wyrd_root: Path) -> list[tuple[Path, str]]:
        bridge_dir = wyrd_root / "integrations" / "pygame" / "wyrdforge"
        return [
            (bridge_dir / "wyrd_pygame_helpers.py", "wyrd_pygame_helpers.py"),
            (bridge_dir / "wyrd_pygame_client.py",  "wyrd_pygame_client.py"),
            (bridge_dir / "wyrd_pygame_loop.py",    "wyrd_pygame_loop.py"),
        ]

    def post_install_notes(self) -> str:
        return """\
Add to your pygame project:
    from wyrd_pygame_client import WyrdPygameClient
    from wyrd_pygame_loop import WyrdPygameLoop

    client = WyrdPygameClient()          # connects to localhost:8765
    wyrd   = WyrdPygameLoop(client)

In your game loop:
    context = wyrd.on_npc_interact("guard", player_input)
    wyrd.on_scene_change("dungeon_entrance")
    wyrd.on_npc_move("goblin", "cave")

Start WyrdHTTPServer first:
    python -m wyrdforge.bridges.http_api --port 8765"""


# ---------------------------------------------------------------------------
# NorseSagaEngine
# ---------------------------------------------------------------------------

class NSEInstaller(BaseInstaller):
    """Install the WYRD NSE bridge into a NorseSagaEngine project."""

    name = "NorseSagaEngine"
    description = "WYRD bridge for Norse Saga Engine"

    def detect_candidates(self, search_paths: list[Path]) -> list[Path]:
        return find_dir_by_markers(
            search_paths,
            ["NorseSagaEngine", "yggdrasil_engine.py"],
            require_all=False,
        )

    def files_to_install(self, wyrd_root: Path) -> list[tuple[Path, str]]:
        src = wyrd_root / "src" / "wyrdforge" / "bridges" / "nse_bridge.py"
        return [(src, "wyrdforge_nse_bridge.py")]

    def post_install_notes(self) -> str:
        return """\
In your NSE project:
    from wyrdforge_nse_bridge import NSEWyrdBridge

    bridge = NSEWyrdBridge(nse_engine, db_path="wyrd_nse.db")
    bridge.sync()

    context = bridge.query_npc("sigrid", player_input)
    # Inject context into NSE's system prompt

After each NSE turn:
    bridge.push_turn_observation("Turn summary", turn_text)"""


# ---------------------------------------------------------------------------
# Viking Girlfriend Skill / OpenClaw
# ---------------------------------------------------------------------------

class VGSKInstaller(BaseInstaller):
    """Install the WYRD OpenClaw bridge into a Viking Girlfriend Skill project."""

    name = "Viking Girlfriend Skill (OpenClaw)"
    description = "WYRD bridge for VGSK / OpenClaw"

    def detect_candidates(self, search_paths: list[Path]) -> list[Path]:
        return find_dir_by_markers(
            search_paths,
            ["Viking_Girlfriend_Skill_for_OpenClaw", "openclaw.json", "skill.json"],
            require_all=False,
        )

    def files_to_install(self, wyrd_root: Path) -> list[tuple[Path, str]]:
        src = wyrd_root / "src" / "wyrdforge" / "bridges" / "openclaw_bridge.py"
        return [(src, "wyrdforge_openclaw_bridge.py")]

    def post_install_notes(self) -> str:
        return """\
In your OpenClaw skill:
    from wyrdforge_openclaw_bridge import OpenClawWyrdBridge

    bridge = OpenClawWyrdBridge()
    enriched = bridge.enrich_context(persona_id="sigrid", user_input=message)
    # Pass enriched.formatted_for_llm into your system prompt

Start WyrdHTTPServer before running the skill:
    python -m wyrdforge.bridges.http_api"""


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

ALL_INSTALLERS: list[BaseInstaller] = [
    PygameInstaller(),
    NSEInstaller(),
    VGSKInstaller(),
]
