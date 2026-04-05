"""test_setup.py — Tests for install/wyrd_setup.py (Phases 17A/17B/17C)."""
import sys
import os
import json
import tempfile
import shutil
from pathlib import Path
from unittest.mock import MagicMock, patch, call

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from wyrd_setup import (
    InstallLog,
    DiagnosticsEngine,
    WyrdSetup,
    ALL_INSTALLERS,
    GROUPS,
    _build_parser,
    main,
)
from install_python import PygameInstaller, NSEInstaller
from install_js import FoundryVTTInstaller, Roll20Installer
from install_cpp import UnrealInstaller


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_log(tmp: Path) -> InstallLog:
    return InstallLog(tmp / "wyrd_install_log.json")


# ===========================================================================
# ALL_INSTALLERS registry
# ===========================================================================

class TestInstallerRegistry:
    def test_all_installers_count(self):
        assert len(ALL_INSTALLERS) == 21

    def test_groups_cover_all(self):
        total = sum(len(v) for v in GROUPS.values())
        assert total == len(ALL_INSTALLERS)

    def test_group_names_present(self):
        assert "Python / AI" in GROUPS
        assert "JavaScript / VTT" in GROUPS
        assert "C# / .NET" in GROUPS
        assert "Java / Lua / Native" in GROUPS
        assert "C++ Engines" in GROUPS

    def test_no_duplicates_across_groups(self):
        names = [i.name for i in ALL_INSTALLERS]
        assert len(names) == len(set(names))


# ===========================================================================
# InstallLog
# ===========================================================================

class TestInstallLog:
    def setup_method(self):
        self.tmp = Path(tempfile.mkdtemp())

    def teardown_method(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_empty_log_returns_empty_list(self):
        log = make_log(self.tmp)
        assert log.get_installed() == []

    def test_record_and_retrieve(self):
        log = make_log(self.tmp)
        log.record_install("pygame", Path("/some/path"), [Path("/some/path/file.py")])
        entries = log.get_installed()
        assert len(entries) == 1
        assert entries[0]["target"] == "pygame"

    def test_was_installed_true(self):
        log = make_log(self.tmp)
        log.record_install("pygame", Path("/p"), [])
        assert log.was_installed("pygame") is True

    def test_was_installed_false(self):
        log = make_log(self.tmp)
        assert log.was_installed("pygame") is False

    def test_remove_target(self):
        log = make_log(self.tmp)
        log.record_install("pygame", Path("/p"), [])
        assert log.remove_target("pygame") is True
        assert log.was_installed("pygame") is False

    def test_remove_nonexistent_returns_false(self):
        log = make_log(self.tmp)
        assert log.remove_target("nonexistent") is False

    def test_persists_to_disk(self):
        log = make_log(self.tmp)
        log.record_install("foundry", Path("/f"), [Path("/f/module.json")])
        log2 = make_log(self.tmp)
        assert log2.was_installed("foundry")

    def test_get_entry_returns_dict(self):
        log = make_log(self.tmp)
        log.record_install("unity", Path("/u"), [])
        entry = log.get_entry("unity")
        assert entry is not None
        assert entry["target"] == "unity"

    def test_get_entry_none_when_missing(self):
        log = make_log(self.tmp)
        assert log.get_entry("nonexistent") is None

    def test_record_replaces_existing_entry(self):
        log = make_log(self.tmp)
        log.record_install("pygame", Path("/old"), [])
        log.record_install("pygame", Path("/new"), [])
        entries = [e for e in log.get_installed() if e["target"] == "pygame"]
        assert len(entries) == 1
        assert entries[0]["target_dir"] == str(Path("/new"))

    def test_clear_removes_all(self):
        log = make_log(self.tmp)
        log.record_install("pygame", Path("/p"), [])
        log.record_install("unity", Path("/u"), [])
        log.clear()
        assert log.get_installed() == []

    def test_corrupt_json_returns_empty(self):
        log_path = self.tmp / "wyrd_install_log.json"
        log_path.write_text("not valid json")
        log = InstallLog(log_path)
        assert log.get_installed() == []

    def test_multiple_targets_stored(self):
        log = make_log(self.tmp)
        log.record_install("pygame", Path("/p"), [])
        log.record_install("godot", Path("/g"), [])
        log.record_install("unreal", Path("/u"), [])
        assert len(log.get_installed()) == 3

    def test_timestamp_recorded(self):
        log = make_log(self.tmp)
        log.record_install("pygame", Path("/p"), [])
        entry = log.get_entry("pygame")
        assert "timestamp" in entry


# ===========================================================================
# DiagnosticsEngine
# ===========================================================================

class TestDiagnosticsEngine:
    diag = DiagnosticsEngine()

    def test_check_tool_python_available(self):
        # Python is always available (we're running in it)
        assert self.diag.check_tool("python") is True

    def test_check_tool_fake_returns_false(self):
        assert self.diag.check_tool("__wyrd_fake_tool_xyz__") is False

    def test_diagnose_missing_target_dir(self):
        result = self.diag.diagnose_failure(
            PygameInstaller(), None, Path("/nonexistent/path")
        )
        assert "does not exist" in result

    def test_diagnose_permission_error(self):
        result = self.diag.diagnose_failure(
            PygameInstaller(), PermissionError("access denied"), None
        )
        assert "permission" in result.lower() or "administrator" in result.lower()

    def test_diagnose_file_not_found(self):
        result = self.diag.diagnose_failure(
            PygameInstaller(), FileNotFoundError("no such file"), None
        )
        assert "not found" in result.lower() or "file" in result.lower()

    def test_diagnose_unknown_returns_fallback(self):
        result = self.diag.diagnose_failure(PygameInstaller(), None, None)
        assert isinstance(result, str) and len(result) > 0

    def test_suggest_fix_permission(self):
        fix = self.diag.suggest_fix("permission denied — try running as administrator")
        assert "administrator" in fix.lower() or "privilege" in fix.lower()

    def test_suggest_fix_directory_not_exist(self):
        fix = self.diag.suggest_fix("directory does not exist: /foo")
        assert "directory" in fix.lower() or "path" in fix.lower()

    def test_suggest_fix_missing_tool(self):
        fix = self.diag.suggest_fix("required tool not found in path: 'dotnet'")
        assert "dotnet" in fix.lower() or ".net" in fix.lower()

    def test_suggest_fix_node_missing(self):
        fix = self.diag.suggest_fix("required tool not found in path: 'node'")
        assert "node" in fix.lower() or "nodejs" in fix.lower()

    def test_suggest_fix_unknown(self):
        fix = self.diag.suggest_fix("something weird happened")
        assert isinstance(fix, str) and len(fix) > 0

    def test_extract_tool_from_diagnosis(self):
        tool = DiagnosticsEngine._extract_tool("required tool 'cmake' not found")
        assert tool == "cmake"

    def test_extract_tool_no_match_returns_unknown(self):
        tool = DiagnosticsEngine._extract_tool("no quotes here")
        assert tool == "unknown"


# ===========================================================================
# WyrdSetup.parse_selection
# ===========================================================================

class TestParseSelection:
    installers = ALL_INSTALLERS

    def test_all_returns_all(self):
        result = WyrdSetup.parse_selection("all", self.installers)
        assert len(result) == len(self.installers)

    def test_single_number(self):
        result = WyrdSetup.parse_selection("1", self.installers)
        assert len(result) == 1
        assert result[0] is self.installers[0]

    def test_multiple_numbers(self):
        result = WyrdSetup.parse_selection("1,2,3", self.installers)
        assert len(result) == 3

    def test_out_of_range_number_ignored(self):
        result = WyrdSetup.parse_selection("999", self.installers)
        assert result == []

    def test_name_partial_match(self):
        result = WyrdSetup.parse_selection("pygame", self.installers)
        assert any("pygame" in i.name.lower() for i in result)

    def test_category_python(self):
        result = WyrdSetup.parse_selection("python", self.installers)
        assert len(result) > 0
        for i in result:
            assert i in self.installers

    def test_category_js(self):
        result = WyrdSetup.parse_selection("js", self.installers)
        assert len(result) == 7

    def test_category_csharp(self):
        result = WyrdSetup.parse_selection("csharp", self.installers)
        assert len(result) == 4

    def test_category_native(self):
        result = WyrdSetup.parse_selection("native", self.installers)
        assert len(result) == 4

    def test_category_cpp(self):
        result = WyrdSetup.parse_selection("cpp", self.installers)
        assert len(result) == 3

    def test_empty_string_returns_empty(self):
        result = WyrdSetup.parse_selection("", self.installers)
        assert result == []

    def test_no_duplicates_in_result(self):
        result = WyrdSetup.parse_selection("1,1,1", self.installers)
        names = [i.name for i in result]
        assert len(names) == len(set(names))

    def test_semicolon_separator(self):
        result = WyrdSetup.parse_selection("1;2", self.installers)
        assert len(result) == 2

    def test_unreal_partial_match(self):
        result = WyrdSetup.parse_selection("unreal", self.installers)
        assert any("Unreal" in i.name for i in result)

    def test_case_insensitive_name(self):
        result = WyrdSetup.parse_selection("PYGAME", self.installers)
        assert any("pygame" in i.name.lower() for i in result)


# ===========================================================================
# WyrdSetup.find_wyrd_root
# ===========================================================================

class TestFindWyrdRoot:
    def test_returns_path(self):
        root = WyrdSetup.find_wyrd_root()
        assert isinstance(root, Path)

    def test_finds_repo_root(self):
        root = WyrdSetup.find_wyrd_root()
        # Should find WYRD-Protocol root (has ROADMAP.md or src/wyrdforge)
        assert (root / "ROADMAP.md").exists() or (root / "src" / "wyrdforge").exists()


# ===========================================================================
# WyrdSetup.run_check
# ===========================================================================

class TestRunCheck:
    def setup_method(self):
        self.tmp = Path(tempfile.mkdtemp())

    def teardown_method(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_empty_log_returns_empty_dict(self):
        log = make_log(self.tmp)
        setup = WyrdSetup(wyrd_root=self.tmp, log=log)
        result = setup.run_check()
        assert result == {}

    def test_all_files_present_returns_true(self):
        log = make_log(self.tmp)
        f = self.tmp / "bridge.py"
        f.write_text("x")
        log.record_install("pygame", self.tmp, [f])

        setup = WyrdSetup(wyrd_root=self.tmp, log=log)
        result = setup.run_check()
        assert result.get("pygame") is True

    def test_missing_file_returns_false(self):
        log = make_log(self.tmp)
        log.record_install("pygame", self.tmp, [self.tmp / "missing.py"])

        setup = WyrdSetup(wyrd_root=self.tmp, log=log)
        result = setup.run_check()
        assert result.get("pygame") is False

    def test_multiple_targets_checked(self):
        log = make_log(self.tmp)
        f1 = self.tmp / "a.py"; f1.write_text("x")
        f2 = self.tmp / "b.py"; f2.write_text("x")
        log.record_install("pygame", self.tmp, [f1])
        log.record_install("godot",  self.tmp, [f2])

        setup = WyrdSetup(wyrd_root=self.tmp, log=log)
        result = setup.run_check()
        assert len(result) == 2


# ===========================================================================
# WyrdSetup.run_uninstall
# ===========================================================================

class TestRunUninstall:
    def setup_method(self):
        self.tmp = Path(tempfile.mkdtemp())

    def teardown_method(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_uninstall_removes_file(self):
        log = make_log(self.tmp)
        f = self.tmp / "bridge.py"
        f.write_text("x")
        log.record_install("pygame", self.tmp, [f])

        setup = WyrdSetup(wyrd_root=self.tmp, log=log)
        setup.run_uninstall()
        assert not f.exists()

    def test_uninstall_removes_log_entry(self):
        log = make_log(self.tmp)
        log.record_install("pygame", self.tmp, [])
        setup = WyrdSetup(wyrd_root=self.tmp, log=log)
        setup.run_uninstall()
        assert not log.was_installed("pygame")

    def test_targeted_uninstall_only_removes_named(self):
        log = make_log(self.tmp)
        f1 = self.tmp / "a.py"; f1.write_text("x")
        f2 = self.tmp / "b.py"; f2.write_text("x")
        log.record_install("pygame", self.tmp, [f1])
        log.record_install("godot",  self.tmp, [f2])

        setup = WyrdSetup(wyrd_root=self.tmp, log=log)
        setup.run_uninstall(["pygame"])
        assert not f1.exists()
        assert f2.exists()
        assert log.was_installed("godot")

    def test_empty_log_does_nothing(self):
        log = make_log(self.tmp)
        setup = WyrdSetup(wyrd_root=self.tmp, log=log)
        setup.run_uninstall()  # should not raise

    def test_no_target_match_does_nothing(self):
        log = make_log(self.tmp)
        log.record_install("pygame", self.tmp, [])
        setup = WyrdSetup(wyrd_root=self.tmp, log=log)
        setup.run_uninstall(["nonexistent"])
        assert log.was_installed("pygame")


# ===========================================================================
# WyrdSetup.install_with_retry
# ===========================================================================

class TestInstallWithRetry:
    def setup_method(self):
        self.tmp = Path(tempfile.mkdtemp())

    def teardown_method(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_success_on_first_attempt(self):
        installer = MagicMock()
        installer.name = "test"
        installer.run.return_value = True
        installer.install_deps_cmd.return_value = None

        setup = WyrdSetup(wyrd_root=self.tmp, log=make_log(self.tmp))
        result = setup.install_with_retry(installer, dry_run=True, max_retries=0)
        assert result is True
        installer.run.assert_called_once()

    def test_failure_with_zero_retries(self):
        installer = MagicMock()
        installer.name = "test"
        installer.run.return_value = False
        installer.install_deps_cmd.return_value = None

        setup = WyrdSetup(wyrd_root=self.tmp, log=make_log(self.tmp))
        result = setup.install_with_retry(installer, dry_run=True, max_retries=0)
        assert result is False

    def test_exception_treated_as_failure(self):
        installer = MagicMock()
        installer.name = "test"
        installer.run.side_effect = OSError("failed")
        installer.install_deps_cmd.return_value = None

        setup = WyrdSetup(wyrd_root=self.tmp, log=make_log(self.tmp))
        with patch("builtins.input", return_value="n"):
            result = setup.install_with_retry(installer, dry_run=True, max_retries=1)
        assert result is False

    def test_retry_succeeds_on_second_attempt(self):
        installer = MagicMock()
        installer.name = "test"
        installer.run.side_effect = [False, True]
        installer.install_deps_cmd.return_value = None

        setup = WyrdSetup(wyrd_root=self.tmp, log=make_log(self.tmp))
        with patch("builtins.input", return_value="y"):
            result = setup.install_with_retry(installer, dry_run=True, max_retries=1)
        assert result is True
        assert installer.run.call_count == 2


# ===========================================================================
# CLI argument parser
# ===========================================================================

class TestCLIParser:
    def test_dry_run_flag(self):
        args = _build_parser().parse_args(["--dry-run"])
        assert args.dry_run is True

    def test_check_flag(self):
        args = _build_parser().parse_args(["--check"])
        assert args.check is True

    def test_uninstall_flag(self):
        args = _build_parser().parse_args(["--uninstall"])
        assert args.uninstall is True

    def test_update_flag(self):
        args = _build_parser().parse_args(["--update"])
        assert args.update is True

    def test_list_flag(self):
        args = _build_parser().parse_args(["--list"])
        assert args.list is True

    def test_target_flag(self):
        args = _build_parser().parse_args(["--target", "pygame"])
        assert args.target == "pygame"

    def test_wyrd_host_default(self):
        args = _build_parser().parse_args([])
        assert args.wyrd_host == "localhost"

    def test_wyrd_port_default(self):
        args = _build_parser().parse_args([])
        assert args.wyrd_port == 8765

    def test_custom_port(self):
        args = _build_parser().parse_args(["--wyrd-port", "9000"])
        assert args.wyrd_port == 9000

    def test_no_flags_defaults(self):
        args = _build_parser().parse_args([])
        assert args.dry_run is False
        assert args.check is False
        assert args.uninstall is False
        assert args.update is False
        assert args.list is False
        assert args.target is None


# ===========================================================================
# main() entry point
# ===========================================================================

class TestMain:
    def setup_method(self):
        self.tmp = Path(tempfile.mkdtemp())

    def teardown_method(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _setup_patch(self):
        """Patch WyrdSetup to use a temp log and fake wyrd_root."""
        return patch(
            "wyrd_setup.WyrdSetup",
            lambda **kw: MagicMock(
                log=make_log(self.tmp),
                wyrd_root=self.tmp,
                run_check=MagicMock(return_value={}),
                run_list=MagicMock(),
                run_uninstall=MagicMock(),
                run_update=MagicMock(),
                run_interactive=MagicMock(),
                parse_selection=WyrdSetup.parse_selection,
                _resolve_target_dir=MagicMock(return_value=None),
                install_with_retry=MagicMock(return_value=True),
            ),
        )

    def test_list_returns_0(self):
        with patch("wyrd_setup.WyrdSetup") as MockSetup:
            instance = MockSetup.return_value
            instance.run_list = MagicMock()
            rc = main(["--list"])
        assert rc == 0

    def test_check_returns_0_when_all_ok(self):
        with patch("wyrd_setup.WyrdSetup") as MockSetup:
            instance = MockSetup.return_value
            instance.run_check = MagicMock(return_value={"pygame": True})
            rc = main(["--check"])
        assert rc == 0

    def test_check_returns_1_when_failures(self):
        with patch("wyrd_setup.WyrdSetup") as MockSetup:
            instance = MockSetup.return_value
            instance.run_check = MagicMock(return_value={"pygame": False})
            rc = main(["--check"])
        assert rc == 1

    def test_uninstall_returns_0(self):
        with patch("wyrd_setup.WyrdSetup") as MockSetup:
            instance = MockSetup.return_value
            instance.run_uninstall = MagicMock()
            rc = main(["--uninstall"])
        assert rc == 0

    def test_update_returns_0(self):
        with patch("wyrd_setup.WyrdSetup") as MockSetup:
            instance = MockSetup.return_value
            instance.run_update = MagicMock()
            rc = main(["--update"])
        assert rc == 0

    def test_unknown_target_returns_1(self):
        rc = main(["--target", "__nonexistent_target_xyz__"])
        assert rc == 1
