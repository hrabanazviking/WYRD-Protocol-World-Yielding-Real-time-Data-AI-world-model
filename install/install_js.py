"""install_js.py — 16B: WYRD installers for JavaScript/Node-based targets.

Covers: SillyTavern, Foundry VTT, Roll20, Owlbear Rodeo, D&D Beyond, RPG Maker, Construct 3.
All installers are Python scripts that copy JS files and optionally run npm.
"""
from __future__ import annotations

from pathlib import Path

from _common import BaseInstaller, find_dir_by_markers


# ---------------------------------------------------------------------------
# SillyTavern
# ---------------------------------------------------------------------------

class SillyTavernInstaller(BaseInstaller):
    name = "SillyTavern"
    description = "WYRD extension for SillyTavern AI frontend"

    def detect_candidates(self, search_paths: list[Path]) -> list[Path]:
        return find_dir_by_markers(
            search_paths,
            ["SillyTavern"],
            require_all=False,
        ) + find_dir_by_markers(
            search_paths,
            ["public", "server.js", "package.json"],
            require_all=True,
        )

    def files_to_install(self, wyrd_root: Path) -> list[tuple[Path, str]]:
        src = wyrd_root / "integrations" / "sillytavern" / "wyrdforge"
        return [
            (src / "index.js",    "public/extensions/wyrdforge/index.js"),
            (src / "manifest.json", "public/extensions/wyrdforge/manifest.json"),
        ]

    def post_install_notes(self) -> str:
        return """\
1. Start SillyTavern and navigate to Extensions (puzzle icon).
2. Enable "WyrdForge World Context" in the extension list.
3. In the extension panel, set your WyrdHTTPServer address (default: localhost:8765).
4. Select a character in the WYRD panel — their world context will inject automatically."""


# ---------------------------------------------------------------------------
# Foundry VTT
# ---------------------------------------------------------------------------

class FoundryVTTInstaller(BaseInstaller):
    name = "Foundry VTT"
    description = "WYRD module for Foundry Virtual Tabletop (V11/V12)"

    def detect_candidates(self, search_paths: list[Path]) -> list[Path]:
        return find_dir_by_markers(
            search_paths,
            ["FoundryVTT", "foundryvtt"],
            require_all=False,
        ) + find_dir_by_markers(
            search_paths,
            ["Data", "modules", "systems"],
            require_all=True,
        )

    def files_to_install(self, wyrd_root: Path) -> list[tuple[Path, str]]:
        src = wyrd_root / "integrations" / "foundry" / "wyrdforge"
        return [
            (src / "module.json",  "Data/modules/wyrdforge/module.json"),
            (src / "wyrdforge.js", "Data/modules/wyrdforge/wyrdforge.js"),
        ]

    def post_install_notes(self) -> str:
        return """\
1. Launch Foundry VTT and open your world.
2. Go to Add-on Modules → Manage Modules.
3. Enable "WyrdForge World Context".
4. In module settings, enter your WyrdHTTPServer URL (default: http://localhost:8765).
5. WYRD context will inject into chat and NPC rolls automatically."""


# ---------------------------------------------------------------------------
# Roll20
# ---------------------------------------------------------------------------

class Roll20Installer(BaseInstaller):
    name = "Roll20"
    description = "WYRD API script for Roll20 (requires Pro subscription)"

    def detect_candidates(self, search_paths: list[Path]) -> list[Path]:
        # Roll20 is web-based; no local installation to detect
        return []

    def files_to_install(self, wyrd_root: Path) -> list[tuple[Path, str]]:
        src = wyrd_root / "integrations" / "roll20" / "wyrdforge"
        return [
            (src / "wyrdforge.js", "wyrdforge.js"),
        ]

    def post_install_notes(self) -> str:
        return """\
Roll20 API scripts are uploaded manually via the web interface:
1. Open your Roll20 campaign → API Scripts tab (Pro required).
2. Create New Script, paste the contents of wyrdforge.js.
3. Save. The script will register !wyrd-query and !wyrd-event chat commands.
4. Set your WyrdHTTPServer URL with: !wyrd-config url http://YOUR_SERVER:8765
Note: Roll20 API scripts run server-side, so the server must be publicly accessible
or use the WYRD Cloud Relay (tools/wyrd_cloud_relay/relay.py)."""


# ---------------------------------------------------------------------------
# Owlbear Rodeo
# ---------------------------------------------------------------------------

class OwlbearInstaller(BaseInstaller):
    name = "Owlbear Rodeo"
    description = "WYRD extension for Owlbear Rodeo 2 VTT"

    def detect_candidates(self, search_paths: list[Path]) -> list[Path]:
        # Owlbear is web-based; no local installation
        return []

    def files_to_install(self, wyrd_root: Path) -> list[tuple[Path, str]]:
        src = wyrd_root / "integrations" / "owlbear" / "wyrdforge"
        return [
            (src / "manifest.json", "manifest.json"),
            (src / "wyrdforge.js",  "wyrdforge.js"),
        ]

    def install_deps_cmd(self, target_dir: Path) -> list[str] | None:
        if (target_dir / "package.json").exists():
            return ["npm", "install"]
        return None

    def post_install_notes(self) -> str:
        return """\
1. Host the extension files on a public HTTPS URL (e.g. GitHub Pages, Vercel).
2. In Owlbear Rodeo, go to Extensions → Add Extension.
3. Paste the URL of your hosted manifest.json.
4. Configure the WyrdHTTPServer URL in the extension panel.
Note: Owlbear extensions run in the browser, so use the WYRD Cloud Relay
for a publicly accessible endpoint."""


# ---------------------------------------------------------------------------
# D&D Beyond
# ---------------------------------------------------------------------------

class DnDBeyondInstaller(BaseInstaller):
    name = "D&D Beyond"
    description = "WYRD browser extension for D&D Beyond (Chrome/Firefox)"

    def detect_candidates(self, search_paths: list[Path]) -> list[Path]:
        # Look for Chrome/Firefox extension dev folders
        return find_dir_by_markers(
            search_paths,
            ["dndbeyond", "dnd_beyond"],
            require_all=False,
        )

    def files_to_install(self, wyrd_root: Path) -> list[tuple[Path, str]]:
        src = wyrd_root / "integrations" / "dndbeyond" / "wyrdforge"
        return [
            (src / "manifest.json",  "manifest.json"),
            (src / "content.js",     "content.js"),
            (src / "background.js",  "background.js"),
            (src / "wyrdforge.js",   "wyrdforge.js"),
        ]

    def post_install_notes(self) -> str:
        return """\
Chrome (developer mode):
  1. Go to chrome://extensions/
  2. Enable Developer Mode (top right).
  3. Load Unpacked → select the wyrdforge extension folder.
  4. Navigate to D&D Beyond — the WYRD panel will appear in the sidebar.

Firefox:
  1. Go to about:debugging → This Firefox → Load Temporary Add-on.
  2. Select the manifest.json in the wyrdforge folder.

Configure the WyrdHTTPServer URL in the extension popup settings."""


# ---------------------------------------------------------------------------
# RPG Maker MZ/MV
# ---------------------------------------------------------------------------

class RPGMakerInstaller(BaseInstaller):
    name = "RPG Maker MZ/MV"
    description = "WYRD plugin for RPG Maker MZ and MV"

    def detect_candidates(self, search_paths: list[Path]) -> list[Path]:
        return find_dir_by_markers(
            search_paths,
            ["js/plugins", "data/System.json"],
            require_all=True,
        ) + find_dir_by_markers(
            search_paths,
            ["js/plugins"],
            require_all=False,
        )

    def files_to_install(self, wyrd_root: Path) -> list[tuple[Path, str]]:
        src = wyrd_root / "integrations" / "rpgmaker" / "wyrdforge"
        return [
            (src / "WyrdForge.js", "js/plugins/WyrdForge.js"),
        ]

    def post_install_notes(self) -> str:
        return """\
1. Open your RPG Maker project.
2. Go to Tools → Plugin Manager.
3. Add plugin "WyrdForge" (it will appear in the list).
4. Configure WyrdServer_Host and WyrdServer_Port parameters.
5. Use the plugin commands in events:
   WyrdQuery <persona_id> <text>   → stores result in game variable
   WyrdEvent observation <title> <summary>"""


# ---------------------------------------------------------------------------
# Construct 3
# ---------------------------------------------------------------------------

class Construct3Installer(BaseInstaller):
    name = "Construct 3"
    description = "WYRD addon for Construct 3 game engine"

    def detect_candidates(self, search_paths: list[Path]) -> list[Path]:
        return find_dir_by_markers(
            search_paths,
            ["construct3", "c3p", ".c3p"],
            require_all=False,
        )

    def files_to_install(self, wyrd_root: Path) -> list[tuple[Path, str]]:
        src = wyrd_root / "integrations" / "construct3" / "wyrdforge"
        return [
            (src / "addon.json",    "addon.json"),
            (src / "wyrdforge.js",  "wyrdforge.js"),
            (src / "instance.js",   "instance.js"),
        ]

    def post_install_notes(self) -> str:
        return """\
1. In Construct 3, go to Menu → View → Addon Manager.
2. Click Install new addon → select the wyrdforge addon folder.
3. The WyrdForge plugin will appear in the object list.
4. Add a WyrdForge object to your project.
5. Configure Host and Port in the object properties.
6. Use actions: Query NPC, Push Observation, Push Fact."""


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

ALL_INSTALLERS: list[BaseInstaller] = [
    SillyTavernInstaller(),
    FoundryVTTInstaller(),
    Roll20Installer(),
    OwlbearInstaller(),
    DnDBeyondInstaller(),
    RPGMakerInstaller(),
    Construct3Installer(),
]
