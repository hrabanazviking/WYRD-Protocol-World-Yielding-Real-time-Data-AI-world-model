"""test_installers.py — Tests for all WYRD platform installer classes.

Tests cover: detection logic, file lists, dep commands, post-install notes.
No files are actually copied; no processes are run.
"""
import sys
import os
import tempfile
import shutil
from pathlib import Path

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from install_python import PygameInstaller, NSEInstaller, VGSKInstaller, ALL_INSTALLERS as PY_INSTALLERS
from install_js import (
    SillyTavernInstaller, FoundryVTTInstaller, Roll20Installer,
    OwlbearInstaller, DnDBeyondInstaller, RPGMakerInstaller, Construct3Installer,
    ALL_INSTALLERS as JS_INSTALLERS,
)
from install_csharp import UnityInstaller, MonoGameInstaller, FGUInstaller, OpenSimInstaller, ALL_INSTALLERS as CS_INSTALLERS
from install_native import MinecraftInstaller, RobloxInstaller, GodotInstaller, DefoldInstaller, ALL_INSTALLERS as NATIVE_INSTALLERS
from install_cpp import UnrealInstaller, CryEngineInstaller, O3DEInstaller, ALL_INSTALLERS as CPP_INSTALLERS


# Fake wyrd root (just needs to be a Path; files don't need to exist for list tests)
FAKE_ROOT = Path("/fake/wyrd-root")


# ===========================================================================
# Registry completeness
# ===========================================================================

class TestRegistries:
    def test_python_registry_has_3(self):
        assert len(PY_INSTALLERS) == 3

    def test_js_registry_has_7(self):
        assert len(JS_INSTALLERS) == 7

    def test_csharp_registry_has_4(self):
        assert len(CS_INSTALLERS) == 4

    def test_native_registry_has_4(self):
        assert len(NATIVE_INSTALLERS) == 4

    def test_cpp_registry_has_3(self):
        assert len(CPP_INSTALLERS) == 3

    def test_total_installers(self):
        total = len(PY_INSTALLERS) + len(JS_INSTALLERS) + len(CS_INSTALLERS) + len(NATIVE_INSTALLERS) + len(CPP_INSTALLERS)
        assert total == 21

    def test_all_have_names(self):
        all_inst = PY_INSTALLERS + JS_INSTALLERS + CS_INSTALLERS + NATIVE_INSTALLERS + CPP_INSTALLERS
        for inst in all_inst:
            assert inst.name
            assert isinstance(inst.name, str)

    def test_all_have_descriptions(self):
        all_inst = PY_INSTALLERS + JS_INSTALLERS + CS_INSTALLERS + NATIVE_INSTALLERS + CPP_INSTALLERS
        for inst in all_inst:
            assert inst.description
            assert isinstance(inst.description, str)

    def test_all_names_unique(self):
        all_inst = PY_INSTALLERS + JS_INSTALLERS + CS_INSTALLERS + NATIVE_INSTALLERS + CPP_INSTALLERS
        names = [i.name for i in all_inst]
        assert len(names) == len(set(names))


# ===========================================================================
# Pygame installer
# ===========================================================================

class TestPygameInstaller:
    inst = PygameInstaller()

    def test_name(self):
        assert "pygame" in self.inst.name.lower()

    def test_files_to_install_has_3_files(self):
        files = self.inst.files_to_install(FAKE_ROOT)
        assert len(files) == 3

    def test_files_include_helpers(self):
        files = self.inst.files_to_install(FAKE_ROOT)
        names = [Path(rel).name for _, rel in files]
        assert "wyrd_pygame_helpers.py" in names

    def test_files_include_client(self):
        files = self.inst.files_to_install(FAKE_ROOT)
        names = [Path(rel).name for _, rel in files]
        assert "wyrd_pygame_client.py" in names

    def test_files_include_loop(self):
        files = self.inst.files_to_install(FAKE_ROOT)
        names = [Path(rel).name for _, rel in files]
        assert "wyrd_pygame_loop.py" in names

    def test_post_notes_mentions_client(self):
        notes = self.inst.post_install_notes()
        assert "WyrdPygameClient" in notes

    def test_detect_no_crash_on_empty(self):
        result = self.inst.detect_candidates([])
        assert isinstance(result, list)

    def test_detect_finds_pygame_dir(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            (d / "pygame").mkdir()
            result = self.inst.detect_candidates([d])
            assert d in result


# ===========================================================================
# NSE installer
# ===========================================================================

class TestNSEInstaller:
    inst = NSEInstaller()

    def test_name(self):
        assert "NorseSaga" in self.inst.name or "Norse" in self.inst.name

    def test_files_to_install_has_1_file(self):
        files = self.inst.files_to_install(FAKE_ROOT)
        assert len(files) == 1

    def test_file_is_nse_bridge(self):
        files = self.inst.files_to_install(FAKE_ROOT)
        assert "nse_bridge" in str(files[0][0])

    def test_post_notes_mentions_bridge(self):
        notes = self.inst.post_install_notes()
        assert "NSEWyrdBridge" in notes

    def test_detect_empty_returns_list(self):
        result = self.inst.detect_candidates([])
        assert isinstance(result, list)


# ===========================================================================
# VGSK installer
# ===========================================================================

class TestVGSKInstaller:
    inst = VGSKInstaller()

    def test_files_to_install_has_1_file(self):
        files = self.inst.files_to_install(FAKE_ROOT)
        assert len(files) == 1

    def test_file_is_openclaw_bridge(self):
        files = self.inst.files_to_install(FAKE_ROOT)
        assert "openclaw" in str(files[0][0]).lower()

    def test_post_notes_mentions_openclaw(self):
        notes = self.inst.post_install_notes()
        assert "OpenClaw" in notes or "openclaw" in notes.lower()


# ===========================================================================
# SillyTavern installer
# ===========================================================================

class TestSillyTavernInstaller:
    inst = SillyTavernInstaller()

    def test_files_include_index_js(self):
        files = self.inst.files_to_install(FAKE_ROOT)
        names = [Path(rel).name for _, rel in files]
        assert "index.js" in names

    def test_files_include_manifest(self):
        files = self.inst.files_to_install(FAKE_ROOT)
        names = [Path(rel).name for _, rel in files]
        assert "manifest.json" in names

    def test_post_notes_mentions_extensions(self):
        notes = self.inst.post_install_notes()
        assert "Extension" in notes or "extension" in notes

    def test_detect_finds_sillytavern_dir(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            (d / "SillyTavern").mkdir()
            result = self.inst.detect_candidates([d])
            assert d in result


# ===========================================================================
# Foundry VTT installer
# ===========================================================================

class TestFoundryVTTInstaller:
    inst = FoundryVTTInstaller()

    def test_files_include_module_json(self):
        files = self.inst.files_to_install(FAKE_ROOT)
        names = [Path(rel).name for _, rel in files]
        assert "module.json" in names

    def test_dest_in_data_modules(self):
        files = self.inst.files_to_install(FAKE_ROOT)
        for _, rel in files:
            assert "modules" in rel or "Data" in rel

    def test_post_notes_mentions_modules(self):
        notes = self.inst.post_install_notes()
        assert "Module" in notes or "module" in notes


# ===========================================================================
# Roll20 installer
# ===========================================================================

class TestRoll20Installer:
    inst = Roll20Installer()

    def test_detect_returns_empty(self):
        # Roll20 is web-based — can never auto-detect
        with tempfile.TemporaryDirectory() as tmp:
            result = self.inst.detect_candidates([Path(tmp)])
            assert result == []

    def test_files_include_js(self):
        files = self.inst.files_to_install(FAKE_ROOT)
        assert any(rel.endswith(".js") for _, rel in files)

    def test_post_notes_mentions_api(self):
        notes = self.inst.post_install_notes()
        assert "API" in notes or "script" in notes.lower()

    def test_post_notes_mentions_cloud_relay(self):
        notes = self.inst.post_install_notes()
        assert "Relay" in notes or "relay" in notes


# ===========================================================================
# Owlbear installer
# ===========================================================================

class TestOwlbearInstaller:
    inst = OwlbearInstaller()

    def test_detect_returns_empty(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = self.inst.detect_candidates([Path(tmp)])
            assert result == []

    def test_files_include_manifest(self):
        files = self.inst.files_to_install(FAKE_ROOT)
        names = [Path(rel).name for _, rel in files]
        assert "manifest.json" in names

    def test_npm_install_cmd_when_package_json_present(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            (d / "package.json").write_text("{}")
            cmd = self.inst.install_deps_cmd(d)
            assert cmd is not None
            assert "npm" in cmd

    def test_no_deps_cmd_when_no_package_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            cmd = self.inst.install_deps_cmd(Path(tmp))
            assert cmd is None


# ===========================================================================
# D&D Beyond installer
# ===========================================================================

class TestDnDBeyondInstaller:
    inst = DnDBeyondInstaller()

    def test_files_include_manifest(self):
        files = self.inst.files_to_install(FAKE_ROOT)
        names = [Path(rel).name for _, rel in files]
        assert "manifest.json" in names

    def test_files_include_content_js(self):
        files = self.inst.files_to_install(FAKE_ROOT)
        names = [Path(rel).name for _, rel in files]
        assert "content.js" in names

    def test_post_notes_mentions_chrome(self):
        notes = self.inst.post_install_notes()
        assert "Chrome" in notes or "chrome" in notes


# ===========================================================================
# RPG Maker installer
# ===========================================================================

class TestRPGMakerInstaller:
    inst = RPGMakerInstaller()

    def test_file_goes_to_plugins(self):
        files = self.inst.files_to_install(FAKE_ROOT)
        for _, rel in files:
            assert "plugins" in rel.lower()

    def test_post_notes_mentions_plugin_manager(self):
        notes = self.inst.post_install_notes()
        assert "Plugin Manager" in notes or "plugin" in notes.lower()

    def test_detect_finds_project_with_plugins_dir(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            (d / "js" / "plugins").mkdir(parents=True)
            result = self.inst.detect_candidates([d])
            assert d in result


# ===========================================================================
# Construct 3 installer
# ===========================================================================

class TestConstruct3Installer:
    inst = Construct3Installer()

    def test_files_include_addon_json(self):
        files = self.inst.files_to_install(FAKE_ROOT)
        names = [Path(rel).name for _, rel in files]
        assert "addon.json" in names

    def test_post_notes_mentions_addon_manager(self):
        notes = self.inst.post_install_notes()
        assert "Addon" in notes or "addon" in notes.lower()


# ===========================================================================
# Unity installer
# ===========================================================================

class TestUnityInstaller:
    inst = UnityInstaller()

    def test_files_go_to_packages(self):
        files = self.inst.files_to_install(FAKE_ROOT)
        for _, rel in files:
            assert rel.startswith("Packages/")

    def test_files_include_package_json(self):
        files = self.inst.files_to_install(FAKE_ROOT)
        names = [Path(rel).name for _, rel in files]
        assert "package.json" in names

    def test_detect_finds_unity_project(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            (d / "Assets").mkdir()
            (d / "ProjectSettings").mkdir()
            result = self.inst.detect_candidates([d])
            assert d in result

    def test_no_deps_cmd(self):
        with tempfile.TemporaryDirectory() as tmp:
            assert self.inst.install_deps_cmd(Path(tmp)) is None

    def test_post_notes_mentions_wyrd_manager(self):
        notes = self.inst.post_install_notes()
        assert "WyrdManager" in notes


# ===========================================================================
# MonoGame installer
# ===========================================================================

class TestMonoGameInstaller:
    inst = MonoGameInstaller()

    def test_deps_cmd_is_dotnet_add(self):
        with tempfile.TemporaryDirectory() as tmp:
            cmd = self.inst.install_deps_cmd(Path(tmp))
            assert cmd is not None
            assert "dotnet" in cmd
            assert "add" in cmd
            assert "package" in cmd

    def test_post_notes_mentions_wyrd_client(self):
        notes = self.inst.post_install_notes()
        assert "WyrdClient" in notes

    def test_files_go_to_wyrdforge_dir(self):
        files = self.inst.files_to_install(FAKE_ROOT)
        for _, rel in files:
            assert rel.startswith("WyrdForge/")


# ===========================================================================
# FGU installer
# ===========================================================================

class TestFGUInstaller:
    inst = FGUInstaller()

    def test_files_go_to_extensions(self):
        files = self.inst.files_to_install(FAKE_ROOT)
        for _, rel in files:
            assert "extension" in rel.lower()

    def test_post_notes_mentions_extensions(self):
        notes = self.inst.post_install_notes()
        assert "extension" in notes.lower() or "Extension" in notes


# ===========================================================================
# OpenSim installer
# ===========================================================================

class TestOpenSimInstaller:
    inst = OpenSimInstaller()

    def test_files_include_dll(self):
        files = self.inst.files_to_install(FAKE_ROOT)
        names = [Path(rel).name for _, rel in files]
        assert any(n.endswith(".dll") for n in names)

    def test_files_include_lsl(self):
        files = self.inst.files_to_install(FAKE_ROOT)
        names = [Path(rel).name for _, rel in files]
        assert any(n.endswith(".lsl") for n in names)

    def test_post_notes_mentions_opensim_ini(self):
        notes = self.inst.post_install_notes()
        assert "OpenSim.ini" in notes


# ===========================================================================
# Minecraft installer
# ===========================================================================

class TestMinecraftInstaller:
    inst = MinecraftInstaller()

    def test_post_notes_mentions_fabric(self):
        notes = self.inst.post_install_notes()
        assert "Fabric" in notes or "fabric" in notes

    def test_post_notes_mentions_mods(self):
        notes = self.inst.post_install_notes()
        assert "mods" in notes.lower()

    def test_detect_finds_minecraft_dir(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            (d / ".minecraft").mkdir()
            result = self.inst.detect_candidates([d])
            assert d in result


# ===========================================================================
# Roblox installer
# ===========================================================================

class TestRobloxInstaller:
    inst = RobloxInstaller()

    def test_files_include_bridge(self):
        files = self.inst.files_to_install(FAKE_ROOT)
        names = [Path(rel).name for _, rel in files]
        assert "WyrdBridge.lua" in names

    def test_files_include_client_bridge(self):
        files = self.inst.files_to_install(FAKE_ROOT)
        names = [Path(rel).name for _, rel in files]
        assert "WyrdClientBridge.lua" in names

    def test_post_notes_mentions_cloud_relay(self):
        notes = self.inst.post_install_notes()
        assert "Relay" in notes or "relay" in notes

    def test_post_notes_mentions_server_script_service(self):
        notes = self.inst.post_install_notes()
        assert "ServerScriptService" in notes


# ===========================================================================
# Godot installer
# ===========================================================================

class TestGodotInstaller:
    inst = GodotInstaller()

    def test_files_go_to_addons(self):
        files = self.inst.files_to_install(FAKE_ROOT)
        for _, rel in files:
            assert rel.startswith("addons/")

    def test_detect_finds_project_godot(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            (d / "project.godot").write_text("[gd_resource]")
            result = self.inst.detect_candidates([d])
            assert d in result

    def test_post_notes_mentions_plugin(self):
        notes = self.inst.post_install_notes()
        assert "plugin" in notes.lower() or "Plugin" in notes


# ===========================================================================
# Defold installer
# ===========================================================================

class TestDefoldInstaller:
    inst = DefoldInstaller()

    def test_files_include_ext_manifest(self):
        files = self.inst.files_to_install(FAKE_ROOT)
        names = [Path(rel).name for _, rel in files]
        assert "ext.manifest" in names

    def test_post_notes_mentions_game_project(self):
        notes = self.inst.post_install_notes()
        assert "game.project" in notes

    def test_detect_finds_game_project(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            (d / "game.project").write_text("[project]")
            result = self.inst.detect_candidates([d])
            assert d in result


# ===========================================================================
# Unreal installer
# ===========================================================================

class TestUnrealInstaller:
    inst = UnrealInstaller()

    def test_files_go_to_plugins(self):
        files = self.inst.files_to_install(FAKE_ROOT)
        for _, rel in files:
            assert rel.startswith("Plugins/WyrdForge/")

    def test_files_include_uplugin(self):
        files = self.inst.files_to_install(FAKE_ROOT)
        names = [Path(rel).name for _, rel in files]
        assert "WyrdForge.uplugin" in names

    def test_post_notes_mentions_subsystem(self):
        notes = self.inst.post_install_notes()
        assert "Subsystem" in notes or "subsystem" in notes

    def test_detect_finds_uproject(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            (d / "Source").mkdir()
            (d / "Content").mkdir()
            (d / "Config").mkdir()
            result = self.inst.detect_candidates([d])
            assert d in result


# ===========================================================================
# CryEngine installer
# ===========================================================================

class TestCryEngineInstaller:
    inst = CryEngineInstaller()

    def test_files_go_to_code(self):
        files = self.inst.files_to_install(FAKE_ROOT)
        for _, rel in files:
            assert rel.startswith("Code/")

    def test_files_include_interface_header(self):
        files = self.inst.files_to_install(FAKE_ROOT)
        names = [Path(rel).name for _, rel in files]
        assert "IWyrdSystem.h" in names

    def test_post_notes_mentions_cmake(self):
        notes = self.inst.post_install_notes()
        assert "CMake" in notes or "cmake" in notes.lower()

    def test_post_notes_mentions_libcurl(self):
        notes = self.inst.post_install_notes()
        assert "libcurl" in notes


# ===========================================================================
# O3DE installer
# ===========================================================================

class TestO3DEInstaller:
    inst = O3DEInstaller()

    def test_files_go_to_gems(self):
        files = self.inst.files_to_install(FAKE_ROOT)
        for _, rel in files:
            assert rel.startswith("Gems/WyrdForge/")

    def test_files_include_gem_json(self):
        files = self.inst.files_to_install(FAKE_ROOT)
        names = [Path(rel).name for _, rel in files]
        assert "gem.json" in names

    def test_post_notes_mentions_ebus(self):
        notes = self.inst.post_install_notes()
        assert "EBus" in notes or "Bus" in notes

    def test_post_notes_mentions_cmake(self):
        notes = self.inst.post_install_notes()
        assert "cmake" in notes.lower() or "CMake" in notes
