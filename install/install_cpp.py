"""install_cpp.py — 16E: WYRD guided installers for C++ engine targets.

Covers: Unreal Engine 5, CryEngine, O3DE / Amazon Lumberyard.
These engines require C++ compilation — the installer copies source files
and prints detailed integration instructions rather than installing a binary.
"""
from __future__ import annotations

from pathlib import Path

from _common import BaseInstaller, find_dir_by_markers


# ---------------------------------------------------------------------------
# Unreal Engine 5
# ---------------------------------------------------------------------------

class UnrealInstaller(BaseInstaller):
    name = "Unreal Engine 5"
    description = "WYRD UE5 plugin (C++ GameInstanceSubsystem)"

    def detect_candidates(self, search_paths: list[Path]) -> list[Path]:
        return find_dir_by_markers(
            search_paths,
            [".uproject"],
            require_all=False,
        ) + find_dir_by_markers(
            search_paths,
            ["Source", "Content", "Config"],
            require_all=True,
        ) + find_dir_by_markers(
            search_paths,
            ["Plugins", "Source"],
            require_all=True,
        )

    def files_to_install(self, wyrd_root: Path) -> list[tuple[Path, str]]:
        src = wyrd_root / "integrations" / "unreal" / "wyrdforge"
        pub = src / "Source" / "WyrdForge" / "Public"
        prv = src / "Source" / "WyrdForge" / "Private"
        return [
            (src / "WyrdForge.uplugin",         "Plugins/WyrdForge/WyrdForge.uplugin"),
            (src / "Source" / "WyrdForge" / "WyrdForge.Build.cs",
                                                 "Plugins/WyrdForge/Source/WyrdForge/WyrdForge.Build.cs"),
            (pub / "WyrdTypes.h",               "Plugins/WyrdForge/Source/WyrdForge/Public/WyrdTypes.h"),
            (pub / "WyrdHelpers.h",             "Plugins/WyrdForge/Source/WyrdForge/Public/WyrdHelpers.h"),
            (pub / "WyrdSubsystem.h",           "Plugins/WyrdForge/Source/WyrdForge/Public/WyrdSubsystem.h"),
            (prv / "WyrdHelpers.cpp",           "Plugins/WyrdForge/Source/WyrdForge/Private/WyrdHelpers.cpp"),
            (prv / "WyrdSubsystem.cpp",         "Plugins/WyrdForge/Source/WyrdForge/Private/WyrdSubsystem.cpp"),
        ]

    def post_install_notes(self) -> str:
        return """\
1. Open your .uproject in Unreal Editor.
2. Plugins → scroll to WyrdForge → Enable → restart the editor.
3. The editor will offer to rebuild the plugin — click Yes.
4. In Blueprints or C++, get the subsystem:
       UWyrdSubsystem* Wyrd = GetGameInstance()->GetSubsystem<UWyrdSubsystem>();
       Wyrd->QueryNPC("sigrid_stormborn", "What do you know?",
           FOnWyrdQueryComplete::CreateLambda([](bool bOk, FString Response){
               UE_LOG(LogTemp, Log, TEXT("WYRD: %s"), *Response);
           }));
5. Push events:
       Wyrd->PushObservation("Army sighted", "300 warriors crossing the river.");
       Wyrd->PushFact("sigrid", "location", "great_hall");
6. Configure WyrdHTTPServer URL in Project Settings → WyrdForge."""


# ---------------------------------------------------------------------------
# CryEngine
# ---------------------------------------------------------------------------

class CryEngineInstaller(BaseInstaller):
    name = "CryEngine"
    description = "WYRD CryEngine plugin (C++, IWyrdSystem interface)"

    def detect_candidates(self, search_paths: list[Path]) -> list[Path]:
        return find_dir_by_markers(
            search_paths,
            ["cryengine", "CryEngine"],
            require_all=False,
        ) + find_dir_by_markers(
            search_paths,
            ["Code", "Assets", "libs"],
            require_all=True,
        )

    def files_to_install(self, wyrd_root: Path) -> list[tuple[Path, str]]:
        src = wyrd_root / "integrations" / "cryengine" / "wyrdforge" / "Code" / "WyrdPlugin"
        return [
            (src / "IWyrdSystem.h",   "Code/WyrdPlugin/IWyrdSystem.h"),
            (src / "WyrdHelpers.cpp", "Code/WyrdPlugin/WyrdHelpers.cpp"),
            (src / "WyrdPlugin.cpp",  "Code/WyrdPlugin/WyrdPlugin.cpp"),
        ]

    def post_install_notes(self) -> str:
        return """\
1. Add the WyrdPlugin directory to your CryEngine project's Code/ folder.
2. Register the plugin in your CMakeLists.txt:
       add_subdirectory(Code/WyrdPlugin)
3. Add libcurl as a dependency (WyrdPlugin.cpp uses it for HTTP):
       target_link_libraries(WyrdPlugin PRIVATE libcurl)
4. Build the project with CMake.
5. In your game code:
       #include "Code/WyrdPlugin/IWyrdSystem.h"
       IWyrdSystem* wyrd = GetIWyrdSystem();
       wyrd->QueryNPC("sigrid", "What do you see?",
           [](const WyrdQueryResult& r){ /* use r.response */ });
       wyrd->PushObservation("Battle", "Warriors attack the gate.");
6. Set WYRD_SERVER_URL environment variable or call wyrd->SetConfig(config)."""


# ---------------------------------------------------------------------------
# O3DE / Amazon Lumberyard
# ---------------------------------------------------------------------------

class O3DEInstaller(BaseInstaller):
    name = "O3DE / Amazon Lumberyard"
    description = "WYRD O3DE Gem (C++ AZ::Component + EBus)"

    def detect_candidates(self, search_paths: list[Path]) -> list[Path]:
        return find_dir_by_markers(
            search_paths,
            ["o3de", "lumberyard", "Lumberyard"],
            require_all=False,
        ) + find_dir_by_markers(
            search_paths,
            ["Gems", "Code", "project.json"],
            require_all=True,
        )

    def files_to_install(self, wyrd_root: Path) -> list[tuple[Path, str]]:
        src = wyrd_root / "integrations" / "o3de" / "wyrdforge"
        code = src / "Code"
        return [
            (src / "gem.json",                           "Gems/WyrdForge/gem.json"),
            (code / "Include" / "WyrdForge" / "WyrdTypes.h",
                                                          "Gems/WyrdForge/Code/Include/WyrdForge/WyrdTypes.h"),
            (code / "Source" / "WyrdHelpers.h",          "Gems/WyrdForge/Code/Source/WyrdHelpers.h"),
            (code / "Source" / "WyrdSystemComponent.h",  "Gems/WyrdForge/Code/Source/WyrdSystemComponent.h"),
            (code / "Source" / "WyrdSystemComponent.cpp","Gems/WyrdForge/Code/Source/WyrdSystemComponent.cpp"),
        ]

    def post_install_notes(self) -> str:
        return """\
1. Copy the WyrdForge Gem into your O3DE project's Gems/ directory.
2. Register the gem with your project:
       <o3de_root>/scripts/o3de.py register --gem-path Gems/WyrdForge
3. Enable the gem in your project.json:
       "gem_names": ["WyrdForge", ...]
4. Run CMake to regenerate the build:
       cmake -B build -S . -G "Visual Studio 17 2022"
5. Build the project.
6. In C++ using the EBus:
       #include <WyrdForge/WyrdTypes.h>
       WyrdRequestBus::Broadcast(&WyrdRequestBus::Events::QueryNPC,
           "sigrid", "What do you see?");
7. Listen for results on WyrdNotificationBus::Handler::OnQueryComplete."""


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

ALL_INSTALLERS: list[BaseInstaller] = [
    UnrealInstaller(),
    CryEngineInstaller(),
    O3DEInstaller(),
]
