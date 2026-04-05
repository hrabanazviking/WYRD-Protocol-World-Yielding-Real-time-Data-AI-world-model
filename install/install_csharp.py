"""install_csharp.py — 16C: WYRD installers for C#/.NET-based targets.

Covers: Unity, MonoGame/FNA, Fantasy Grounds Unity, OpenSim.
"""
from __future__ import annotations

from pathlib import Path

from _common import BaseInstaller, find_dir_by_markers


# ---------------------------------------------------------------------------
# Unity
# ---------------------------------------------------------------------------

class UnityInstaller(BaseInstaller):
    name = "Unity"
    description = "WYRD UPM package for Unity 2022.3+"

    def detect_candidates(self, search_paths: list[Path]) -> list[Path]:
        return find_dir_by_markers(
            search_paths,
            ["Assets", "ProjectSettings", "Packages"],
            require_all=True,
        ) + find_dir_by_markers(
            search_paths,
            ["Assets", "ProjectSettings"],
            require_all=True,
        )

    def files_to_install(self, wyrd_root: Path) -> list[tuple[Path, str]]:
        src = wyrd_root / "integrations" / "unity" / "wyrdforge"
        return [
            (src / "package.json",              "Packages/com.wyrdforge.wyrdforge/package.json"),
            (src / "Runtime" / "WyrdUnityOptions.cs", "Packages/com.wyrdforge.wyrdforge/Runtime/WyrdUnityOptions.cs"),
            (src / "Runtime" / "WyrdEntityData.cs",   "Packages/com.wyrdforge.wyrdforge/Runtime/WyrdEntityData.cs"),
            (src / "Runtime" / "WyrdManager.cs",      "Packages/com.wyrdforge.wyrdforge/Runtime/WyrdManager.cs"),
            (src / "Runtime" / "WyrdNPC.cs",          "Packages/com.wyrdforge.wyrdforge/Runtime/WyrdNPC.cs"),
        ]

    def post_install_notes(self) -> str:
        return """\
1. Open your Unity project.
2. The WyrdForge package will appear in the Package Manager automatically
   (it's in the Packages/ folder which Unity monitors).
3. Add a WyrdManager component to a GameObject in your scene.
4. Configure host, port, and options in the Inspector.
5. Attach WyrdNPC components to NPC GameObjects.
6. Call WyrdManager.Instance.QueryAsync("npc_id", "input") from any script."""

    def install_deps_cmd(self, target_dir: Path) -> list[str] | None:
        # Unity resolves packages automatically — no external command needed
        return None


# ---------------------------------------------------------------------------
# MonoGame / FNA
# ---------------------------------------------------------------------------

class MonoGameInstaller(BaseInstaller):
    name = "MonoGame / FNA"
    description = "WYRD NuGet package for MonoGame and FNA projects"

    def detect_candidates(self, search_paths: list[Path]) -> list[Path]:
        return find_dir_by_markers(
            search_paths,
            [".csproj", "Content"],
            require_all=True,
        ) + find_dir_by_markers(
            search_paths,
            ["Game1.cs", "Program.cs"],
            require_all=False,
        )

    def files_to_install(self, wyrd_root: Path) -> list[tuple[Path, str]]:
        src = wyrd_root / "integrations" / "monogame" / "wyrdforge"
        runtime = src / "Runtime"
        return [
            (runtime / "WyrdClient.cs",      "WyrdForge/WyrdClient.cs"),
            (runtime / "WyrdEntityData.cs",  "WyrdForge/WyrdEntityData.cs"),
            (runtime / "WyrdOptions.cs",     "WyrdForge/WyrdOptions.cs"),
        ]

    def install_deps_cmd(self, target_dir: Path) -> list[str] | None:
        return ["dotnet", "add", "package", "WyrdForge.Client"]

    def post_install_notes(self) -> str:
        return """\
Add to your Game class:
    using WyrdForge;

    private WyrdClient _wyrd;

    protected override void Initialize()
    {
        _wyrd = new WyrdClient("localhost", 8765);
        base.Initialize();
    }

    protected override void Update(GameTime gameTime)
    {
        // Fire-and-forget NPC location update:
        _wyrd.PushFact("guard", "status", "patrolling");
    }"""


# ---------------------------------------------------------------------------
# Fantasy Grounds Unity
# ---------------------------------------------------------------------------

class FGUInstaller(BaseInstaller):
    name = "Fantasy Grounds Unity"
    description = "WYRD extension for Fantasy Grounds Unity"

    def detect_candidates(self, search_paths: list[Path]) -> list[Path]:
        return find_dir_by_markers(
            search_paths,
            ["Fantasy Grounds", "FantasyGrounds"],
            require_all=False,
        ) + find_dir_by_markers(
            search_paths,
            ["extensions", "campaigns", "rulesets"],
            require_all=True,
        )

    def files_to_install(self, wyrd_root: Path) -> list[tuple[Path, str]]:
        src = wyrd_root / "integrations" / "fgu"
        return [
            (src / "WyrdForge.ext",  "extensions/WyrdForge.ext"),
            (src / "wyrdforge.lua",  "extensions/wyrdforge/wyrdforge.lua"),
        ]

    def post_install_notes(self) -> str:
        return """\
1. Ensure the WyrdForge.ext file is in your Fantasy Grounds extensions/ folder.
2. Launch Fantasy Grounds Unity.
3. Create or open a campaign.
4. Go to Settings → Extensions → enable WyrdForge.
5. Configure the WyrdHTTPServer URL in the WYRD panel (default: http://localhost:8765).
6. NPC context will be available in the chat via /wyrd commands."""


# ---------------------------------------------------------------------------
# OpenSim / Second Life
# ---------------------------------------------------------------------------

class OpenSimInstaller(BaseInstaller):
    name = "OpenSim / Second Life"
    description = "WYRD region module for OpenSimulator + LSL NPC script"

    def detect_candidates(self, search_paths: list[Path]) -> list[Path]:
        return find_dir_by_markers(
            search_paths,
            ["OpenSim", "opensim"],
            require_all=False,
        ) + find_dir_by_markers(
            search_paths,
            ["bin", "OpenSim.ini", "Regions"],
            require_all=False,
        )

    def files_to_install(self, wyrd_root: Path) -> list[tuple[Path, str]]:
        src = wyrd_root / "integrations" / "opensim" / "wyrdforge"
        return [
            (src / "WyrdForgeModule.dll",  "bin/WyrdForgeModule.dll"),
            (src / "wyrd_npc.lsl",         "wyrd_npc.lsl"),
        ]

    def post_install_notes(self) -> str:
        return """\
1. Copy WyrdForgeModule.dll to your OpenSim bin/ directory.
2. Add to OpenSim.ini [Modules] section:
       WyrdForgeModule = true
       WyrdForge_ServerUrl = http://localhost:8765
3. Restart OpenSim. The module registers region commands: wyrd-query, wyrd-event.
4. In-world: attach wyrd_npc.lsl to NPC objects to enable automatic context queries.
5. For Second Life: use the WYRD Cloud Relay with a public endpoint."""


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

ALL_INSTALLERS: list[BaseInstaller] = [
    UnityInstaller(),
    MonoGameInstaller(),
    FGUInstaller(),
    OpenSimInstaller(),
]
