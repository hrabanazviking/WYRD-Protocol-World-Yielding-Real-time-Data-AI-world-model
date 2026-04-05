"""install_native.py — 16D: WYRD installers for Java/Lua/native targets.

Covers: Minecraft (Fabric), Roblox (Luau), Godot 4, Defold.
"""
from __future__ import annotations

from pathlib import Path

from _common import BaseInstaller, find_dir_by_markers


# ---------------------------------------------------------------------------
# Minecraft (Fabric)
# ---------------------------------------------------------------------------

class MinecraftInstaller(BaseInstaller):
    name = "Minecraft (Fabric)"
    description = "WYRD Fabric mod for Minecraft 1.21.1"

    def detect_candidates(self, search_paths: list[Path]) -> list[Path]:
        return find_dir_by_markers(
            search_paths,
            [".minecraft", "mods"],
            require_all=False,
        ) + find_dir_by_markers(
            search_paths,
            ["mods", "config", "saves"],
            require_all=True,
        )

    def files_to_install(self, wyrd_root: Path) -> list[tuple[Path, str]]:
        # The compiled jar would be in build/libs/ after `gradle build`
        # We ship the source + build script; user must compile or download release jar
        src = wyrd_root / "integrations" / "minecraft" / "wyrdforge"
        return [
            (src / "build.gradle",       "wyrdforge-mod/build.gradle"),
            (src / "gradle.properties",  "wyrdforge-mod/gradle.properties"),
            (src / "fabric.mod.json",    "wyrdforge-mod/fabric.mod.json"),
        ]

    def post_install_notes(self) -> str:
        return """\
Option A — Build from source:
  1. Install Java 17+ and Gradle.
  2. cd wyrdforge-mod && gradle build
  3. Copy build/libs/wyrdforge-*.jar to your .minecraft/mods/ folder.

Option B — Download release jar:
  1. Grab wyrdforge-fabric-1.21.1.jar from the WYRD GitHub releases.
  2. Drop it into .minecraft/mods/

In-game:
  /wyrd-health           — check WyrdHTTPServer connection
  /wyrd-sync <player>    — sync player entity to WYRD
  /wyrd <character> <q>  — query WYRD for NPC context

Set server URL in config/wyrdforge.json (created on first run)."""


# ---------------------------------------------------------------------------
# Roblox
# ---------------------------------------------------------------------------

class RobloxInstaller(BaseInstaller):
    name = "Roblox"
    description = "WYRD Luau bridge for Roblox Studio (ServerScriptService)"

    def detect_candidates(self, search_paths: list[Path]) -> list[Path]:
        return find_dir_by_markers(
            search_paths,
            ["Roblox", "RobloxStudio"],
            require_all=False,
        ) + find_dir_by_markers(
            search_paths,
            ["LocalPlayer", "ServerScriptService"],
            require_all=False,
        )

    def files_to_install(self, wyrd_root: Path) -> list[tuple[Path, str]]:
        src = wyrd_root / "integrations" / "roblox" / "wyrdforge"
        return [
            (src / "WyrdConfig.lua",       "WyrdConfig.lua"),
            (src / "WyrdMapper.lua",       "WyrdMapper.lua"),
            (src / "WyrdBridge.lua",       "WyrdBridge.lua"),
            (src / "WyrdRemoteSetup.lua",  "WyrdRemoteSetup.lua"),
            (src / "WyrdClientBridge.lua", "WyrdClientBridge.lua"),
        ]

    def post_install_notes(self) -> str:
        return """\
In Roblox Studio:
  1. Place WyrdBridge.lua and WyrdRemoteSetup.lua in ServerScriptService.
     (These run server-side and have HttpService access.)
  2. Place WyrdClientBridge.lua in StarterPlayerScripts.
  3. Edit WyrdConfig.lua: set Host to your WyrdHTTPServer public address.
     (Roblox servers can't reach localhost — use the WYRD Cloud Relay.)
  4. Enable HTTP in Game Settings → Security → Allow HTTP Requests.

Server scripts call WyrdBridge:Query(personaId, userInput).
Client scripts call WyrdClientBridge:Query(personaId, userInput) via RemoteFunction.

Recommended: deploy tools/wyrd_cloud_relay/relay.py on a public server."""


# ---------------------------------------------------------------------------
# Godot 4
# ---------------------------------------------------------------------------

class GodotInstaller(BaseInstaller):
    name = "Godot 4"
    description = "WYRD GDScript addon for Godot 4"

    def detect_candidates(self, search_paths: list[Path]) -> list[Path]:
        return find_dir_by_markers(
            search_paths,
            ["project.godot"],
            require_all=False,
        ) + find_dir_by_markers(
            search_paths,
            ["addons", "scenes", "scripts"],
            require_all=True,
        )

    def files_to_install(self, wyrd_root: Path) -> list[tuple[Path, str]]:
        src = wyrd_root / "integrations" / "godot" / "wyrdforge"
        return [
            (src / "addons" / "wyrdforge" / "plugin.cfg",       "addons/wyrdforge/plugin.cfg"),
            (src / "addons" / "wyrdforge" / "wyrd_bridge.gd",   "addons/wyrdforge/wyrd_bridge.gd"),
            (src / "addons" / "wyrdforge" / "wyrd_client.gd",   "addons/wyrdforge/wyrd_client.gd"),
            (src / "addons" / "wyrdforge" / "wyrd_npc.gd",      "addons/wyrdforge/wyrd_npc.gd"),
        ]

    def post_install_notes(self) -> str:
        return """\
1. Open your Godot 4 project.
2. Go to Project → Project Settings → Plugins.
3. Enable the "WyrdForge" plugin.
4. A WyrdBridge autoload will be registered automatically.
5. In any GDScript:
       var context = await WyrdBridge.query("sigrid", "What do you know?")
       var _void   = WyrdBridge.push_observation("Dragon spotted", "Near the mountain.")
       var _void2  = WyrdBridge.push_fact("sigrid", "location", "great_hall")
6. Configure host/port via Project Settings → WyrdForge section."""


# ---------------------------------------------------------------------------
# Defold
# ---------------------------------------------------------------------------

class DefoldInstaller(BaseInstaller):
    name = "Defold"
    description = "WYRD native extension for Defold (C++ + Lua)"

    def detect_candidates(self, search_paths: list[Path]) -> list[Path]:
        return find_dir_by_markers(
            search_paths,
            ["game.project"],
            require_all=False,
        ) + find_dir_by_markers(
            search_paths,
            ["game.project", "main"],
            require_all=True,
        )

    def files_to_install(self, wyrd_root: Path) -> list[tuple[Path, str]]:
        src = wyrd_root / "integrations" / "defold" / "wyrdforge"
        return [
            (src / "ext.manifest",             "wyrdforge/ext.manifest"),
            (src / "src" / "wyrdforge.cpp",    "wyrdforge/src/wyrdforge.cpp"),
            (src / "src" / "wyrdforge_lua.cpp","wyrdforge/src/wyrdforge_lua.cpp"),
            (src / "wyrdforge.lua",            "wyrdforge/wyrdforge.lua"),
        ]

    def post_install_notes(self) -> str:
        return """\
1. Copy the wyrdforge/ directory into your Defold project root.
2. Open game.project and add the extension:
       [native_extension]
       app_manifest = wyrdforge/ext.manifest
3. Build the project (Defold will compile the native extension).
4. In Lua scripts:
       local wyrd = require("wyrdforge.wyrdforge")
       wyrd.init("localhost", 8765)
       local result = wyrd.query("sigrid", "What do you see?")
       wyrd.push_observation("Battle begun", "Warriors storm the gate.")
       wyrd.push_fact("sigrid", "location", "great_hall")"""


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

ALL_INSTALLERS: list[BaseInstaller] = [
    MinecraftInstaller(),
    RobloxInstaller(),
    GodotInstaller(),
    DefoldInstaller(),
]
