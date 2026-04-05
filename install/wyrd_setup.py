"""wyrd_setup.py — WYRD Protocol unified menu-driven installer.

Entry point for setting up WYRD with any supported platform or engine.

Usage::

    python install/wyrd_setup.py                   # interactive menu
    python install/wyrd_setup.py --dry-run         # preview without copying
    python install/wyrd_setup.py --check           # health-check all installs
    python install/wyrd_setup.py --update          # re-run all previous installs
    python install/wyrd_setup.py --uninstall       # remove all installed files
    python install/wyrd_setup.py --target pygame   # install a specific target
    python install/wyrd_setup.py --list            # list all available targets

Phases implemented:
  17A — interactive menu, banner, install flow, InstallLog
  17B — DiagnosticsEngine, retry loop, partial-install resume
  17C — --uninstall, --update, --check, --list, argparse CLI
"""
from __future__ import annotations

import argparse
import datetime
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Optional

# ---------------------------------------------------------------------------
# Path setup — allow running from any CWD
# ---------------------------------------------------------------------------
_INSTALL_DIR = Path(__file__).parent
sys.path.insert(0, str(_INSTALL_DIR))

from _common import (
    BaseInstaller,
    print_ok, print_err, print_info, print_step, print_header,
    test_wyrd_connection, copy_bridge_files, color,
    _GREEN, _CYAN, _BOLD, _YELLOW, _RED, _RESET,
)
from install_python import ALL_INSTALLERS as _PY
from install_js import ALL_INSTALLERS as _JS
from install_csharp import ALL_INSTALLERS as _CS
from install_native import ALL_INSTALLERS as _NATIVE
from install_cpp import ALL_INSTALLERS as _CPP


# ---------------------------------------------------------------------------
# Installer registry
# ---------------------------------------------------------------------------

GROUPS: dict[str, list[BaseInstaller]] = {
    "Python / AI":       _PY,
    "JavaScript / VTT":  _JS,
    "C# / .NET":         _CS,
    "Java / Lua / Native": _NATIVE,
    "C++ Engines":       _CPP,
}

ALL_INSTALLERS: list[BaseInstaller] = [i for group in GROUPS.values() for i in group]


# ---------------------------------------------------------------------------
# InstallLog  (17A / 17B)
# ---------------------------------------------------------------------------

class InstallLog:
    """Persistent JSON log of what WYRD has installed and where.

    Used by --update and --uninstall to avoid repeating user prompts, and
    by the self-healing retry loop to resume partial installs.

    Args:
        log_path: Path to the JSON log file (default: ``install/wyrd_install_log.json``).
    """

    def __init__(self, log_path: Optional[Path] = None) -> None:
        self.log_path = log_path or (_INSTALL_DIR / "wyrd_install_log.json")
        self._data: dict = self._load()

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def _load(self) -> dict:
        if self.log_path.exists():
            try:
                with open(self.log_path, encoding="utf-8") as f:
                    return json.load(f)
            except (json.JSONDecodeError, OSError):
                return {"installs": []}
        return {"installs": []}

    def save(self) -> None:
        """Write the current log state to disk."""
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.log_path, "w", encoding="utf-8") as f:
            json.dump(self._data, f, indent=2, default=str)

    # ------------------------------------------------------------------
    # Operations
    # ------------------------------------------------------------------

    def record_install(
        self,
        target_name: str,
        target_dir: Path,
        files: list[Path],
    ) -> None:
        """Record a successful install in the log."""
        # Remove any existing record for this target first
        self.remove_target(target_name)
        self._data.setdefault("installs", []).append({
            "target": target_name,
            "target_dir": str(target_dir),
            "files": [str(f) for f in files],
            "timestamp": datetime.datetime.now().isoformat(),
        })
        self.save()

    def get_installed(self) -> list[dict]:
        """Return all recorded install entries."""
        return list(self._data.get("installs", []))

    def was_installed(self, target_name: str) -> bool:
        """Return True if *target_name* has a log entry."""
        return any(e["target"] == target_name for e in self.get_installed())

    def get_entry(self, target_name: str) -> Optional[dict]:
        """Return the log entry for *target_name*, or None."""
        for e in self.get_installed():
            if e["target"] == target_name:
                return e
        return None

    def remove_target(self, target_name: str) -> bool:
        """Remove the log entry for *target_name*. Returns True if found."""
        before = len(self._data.get("installs", []))
        self._data["installs"] = [
            e for e in self._data.get("installs", [])
            if e["target"] != target_name
        ]
        changed = len(self._data["installs"]) < before
        if changed:
            self.save()
        return changed

    def clear(self) -> None:
        """Remove all log entries."""
        self._data = {"installs": []}
        self.save()


# ---------------------------------------------------------------------------
# DiagnosticsEngine  (17B)
# ---------------------------------------------------------------------------

class DiagnosticsEngine:
    """Diagnoses install failures and suggests fixes.

    Used by the retry loop when an installer's ``run()`` raises or returns False.
    """

    _TOOL_CMDS = {
        "python":  ["python", "--version"],
        "node":    ["node", "--version"],
        "npm":     ["npm", "--version"],
        "dotnet":  ["dotnet", "--version"],
        "java":    ["java", "-version"],
        "gradle":  ["gradle", "--version"],
        "cmake":   ["cmake", "--version"],
        "git":     ["git", "--version"],
    }

    def check_tool(self, name: str) -> bool:
        """Return True if *name* is available in PATH."""
        cmd = self._TOOL_CMDS.get(name, [name, "--version"])
        try:
            result = subprocess.run(
                cmd, capture_output=True, timeout=5
            )
            return result.returncode == 0
        except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
            return False

    def diagnose_failure(
        self,
        installer: BaseInstaller,
        exc: Optional[Exception],
        target_dir: Optional[Path],
    ) -> str:
        """Return a human-readable diagnosis for a failed install."""
        lines: list[str] = []

        if target_dir and not target_dir.exists():
            lines.append(f"Target directory does not exist: {target_dir}")

        if exc is not None:
            msg = str(exc).lower()
            if "permission" in msg or "access" in msg:
                lines.append("Permission denied — try running as administrator or check folder permissions.")
            elif "no such file" in msg or "not found" in msg:
                lines.append("A source file was not found — ensure WYRD-Protocol is fully cloned.")
            elif "timeout" in msg:
                lines.append("Network timeout — check your internet connection.")
            else:
                lines.append(f"Unexpected error: {exc}")

        dep_cmd = installer.install_deps_cmd(target_dir or Path("."))
        if dep_cmd:
            tool = dep_cmd[0]
            if not self.check_tool(tool):
                lines.append(f"Required tool not found in PATH: {tool!r} — please install it first.")

        return "\n".join(lines) if lines else "Unknown failure — check the output above for details."

    def suggest_fix(self, diagnosis: str) -> str:
        """Return a one-line fix suggestion based on a diagnosis string."""
        diag = diagnosis.lower()
        if "permission" in diag:
            return "Run the installer as administrator, or manually copy the files with elevated privileges."
        if "not found in path" in diag:
            tool = self._extract_tool(diagnosis)
            if tool == "dotnet":
                return "Install .NET SDK from https://dotnet.microsoft.com/download"
            if tool in ("node", "npm"):
                return "Install Node.js from https://nodejs.org/"
            if tool == "java":
                return "Install Java 17+ from https://adoptium.net/"
            if tool == "gradle":
                return "Install Gradle from https://gradle.org/install/"
            if tool == "cmake":
                return "Install CMake from https://cmake.org/download/"
            return f"Install {tool!r} and ensure it is in your PATH."
        if "directory does not exist" in diag:
            return "Create the target directory first, or choose a different path."
        if "source file" in diag:
            return "Re-clone WYRD-Protocol: git clone https://github.com/hrabanazviking/WYRD-Protocol-World-Yielding-Real-time-Data-AI-world-model.git"
        return "Review the error above and retry."

    @staticmethod
    def _extract_tool(diagnosis: str) -> str:
        """Extract a tool name from a diagnosis string."""
        import re
        m = re.search(r"'([^']+)'", diagnosis)
        return m.group(1) if m else "unknown"


# ---------------------------------------------------------------------------
# WyrdSetup  (17A / 17B / 17C)
# ---------------------------------------------------------------------------

_BANNER = r"""
 __        ____   ___  ____     ____  ____   ___ _____ ___   ____ ___  _
 \ \      / /\ \ / / \|  _ \   |  _ \|  _ \ / _ \_   _/ _ \ / ___/ _ \| |
  \ \ /\ / /  \ V /| |_) | _ _ | |_) | |_) | | | || || | | | |  | | | | |
   \ V  V /    | | |  _ <| | | |  _ <|  __/| |_| || || |_| | |__| |_| | |___
    \_/\_/     |_| |_| \_\_| |_|_| \_\_|    \___/ |_| \___/ \____\___/|_____|

      World-Yielding Real-time Data  ·  AI World Model Protocol
      github.com/hrabanazviking/WYRD-Protocol-World-Yielding-Real-time-Data-AI-world-model
"""


class WyrdSetup:
    """Orchestrates the full WYRD install experience.

    Args:
        wyrd_root:  Root directory of the WYRD-Protocol repository.
        log:        :class:`InstallLog` instance (created automatically if not given).
        diagnostics: :class:`DiagnosticsEngine` instance.
    """

    def __init__(
        self,
        wyrd_root: Optional[Path] = None,
        log: Optional[InstallLog] = None,
        diagnostics: Optional[DiagnosticsEngine] = None,
    ) -> None:
        self.wyrd_root = wyrd_root or self.find_wyrd_root()
        self.log = log or InstallLog()
        self.diagnostics = diagnostics or DiagnosticsEngine()

    # ------------------------------------------------------------------
    # Public modes
    # ------------------------------------------------------------------

    def run_interactive(self, *, dry_run: bool = False) -> None:
        """17A — Full interactive install flow."""
        self._show_banner()
        self._show_wyrd_status()

        print_step("Select integrations to install:")
        self._show_menu()

        raw = input(
            "\n  Enter numbers, names, category, or 'all'  (e.g. 1,3 or pygame or all): "
        ).strip()

        selected = self.parse_selection(raw, ALL_INSTALLERS)
        if not selected:
            print_err("No valid targets selected. Exiting.")
            return

        print_step(f"Installing {len(selected)} target(s) …")
        for installer in selected:
            target_dir = self._resolve_target_dir(installer)
            ok = self.install_with_retry(installer, target_dir, dry_run=dry_run)
            if ok and not dry_run and target_dir:
                files = [target_dir / rel for _, rel in installer.files_to_install(self.wyrd_root)]
                self.log.record_install(installer.name, target_dir, files)

        print_ok("\nAll done. Run 'python install/wyrd_setup.py --check' to verify installs.")

    def run_check(self) -> dict[str, bool]:
        """17C — Health-check all previously installed integrations."""
        print_header("WYRD Installation Health Check")
        installed = self.log.get_installed()
        if not installed:
            print_info("No recorded installs found in wyrd_install_log.json.")
            return {}

        results: dict[str, bool] = {}
        for entry in installed:
            name = entry["target"]
            target_dir = Path(entry["target_dir"])
            files = [Path(f) for f in entry.get("files", [])]

            all_present = all(f.exists() for f in files) if files else target_dir.exists()
            results[name] = all_present

            if all_present:
                print_ok(f"{name}  —  files present in {target_dir}")
            else:
                missing = [f for f in files if not f.exists()]
                print_err(f"{name}  —  {len(missing)} file(s) missing from {target_dir}")

        # WyrdHTTPServer ping
        print()
        if test_wyrd_connection():
            print_ok("WyrdHTTPServer reachable at localhost:8765")
        else:
            print_info("WyrdHTTPServer not running  (start: python -m wyrdforge.bridges.http_api)")

        return results

    def run_uninstall(self, targets: Optional[list[str]] = None) -> None:
        """17C — Remove installed bridge files."""
        print_header("WYRD Uninstall")
        installed = self.log.get_installed()
        if not installed:
            print_info("Nothing recorded in wyrd_install_log.json.")
            return

        to_remove = installed
        if targets:
            names_lower = {t.lower() for t in targets}
            to_remove = [e for e in installed if e["target"].lower() in names_lower]

        if not to_remove:
            print_info("No matching installs found.")
            return

        for entry in to_remove:
            name = entry["target"]
            files = [Path(f) for f in entry.get("files", [])]
            removed = 0
            for f in files:
                if f.exists():
                    try:
                        f.unlink()
                        removed += 1
                    except OSError as e:
                        print_err(f"Could not remove {f}: {e}")
            self.log.remove_target(name)
            print_ok(f"Uninstalled {name}  ({removed} file(s) removed)")

    def run_update(self, targets: Optional[list[str]] = None) -> None:
        """17C — Re-run installers for all previously installed targets."""
        print_header("WYRD Update")
        installed = self.log.get_installed()
        if not installed:
            print_info("Nothing recorded in wyrd_install_log.json.")
            return

        entries = installed
        if targets:
            names_lower = {t.lower() for t in targets}
            entries = [e for e in installed if e["target"].lower() in names_lower]

        for entry in entries:
            name = entry["target"]
            target_dir = Path(entry["target_dir"])
            installer = self._find_installer_by_name(name)
            if installer is None:
                print_err(f"No installer found for '{name}' — skipping.")
                continue
            print_step(f"Updating {name} …")
            ok = self.install_with_retry(installer, target_dir)
            if ok:
                files = [target_dir / rel for _, rel in installer.files_to_install(self.wyrd_root)]
                self.log.record_install(installer.name, target_dir, files)

    def run_list(self) -> None:
        """17C — Print all available targets."""
        print_header("Available WYRD Integration Targets")
        n = 1
        for group, installers in GROUPS.items():
            print(f"\n  {color(group, _CYAN)}")
            for inst in installers:
                installed_mark = color(" ✓", _GREEN) if self.log.was_installed(inst.name) else "  "
                print(f"  {installed_mark} {n:2}. {inst.name:<35} {inst.description}")
                n += 1

    # ------------------------------------------------------------------
    # Install with retry + diagnostics (17B)
    # ------------------------------------------------------------------

    def install_with_retry(
        self,
        installer: BaseInstaller,
        target_dir: Optional[Path] = None,
        *,
        dry_run: bool = False,
        max_retries: int = 2,
    ) -> bool:
        """Run installer.run() with up to *max_retries* retry attempts.

        On failure: diagnoses the error, suggests a fix, and asks whether to retry.
        """
        last_exc: Optional[Exception] = None
        for attempt in range(max_retries + 1):
            try:
                ok = installer.run(self.wyrd_root, target_dir, dry_run=dry_run)
                if ok:
                    return True
                last_exc = None
            except Exception as e:
                last_exc = e

            if attempt < max_retries:
                diag = self.diagnostics.diagnose_failure(installer, last_exc, target_dir)
                fix  = self.diagnostics.suggest_fix(diag)
                print_err(f"\n  Install failed: {diag}")
                print_info(f"  Suggested fix: {fix}")
                raw = input("  Retry? [y/N] ").strip().lower()
                if raw != "y":
                    break
            else:
                diag = self.diagnostics.diagnose_failure(installer, last_exc, target_dir)
                print_err(f"  Install failed after {max_retries + 1} attempt(s): {diag}")

        return False

    # ------------------------------------------------------------------
    # Selection parsing (17A)
    # ------------------------------------------------------------------

    @staticmethod
    def parse_selection(raw: str, installers: list[BaseInstaller]) -> list[BaseInstaller]:
        """Parse a user selection string into a list of installers.

        Accepted formats:
        - ``"all"`` — all installers
        - ``"1,3,5"`` — by 1-based number
        - ``"pygame"`` — by name (case-insensitive partial match)
        - ``"python"`` — by category keyword

        Args:
            raw:        The raw user input string.
            installers: The full flat list of :class:`BaseInstaller` instances.

        Returns:
            Deduplicated list of matching installers (preserving order).
        """
        raw = raw.strip().lower()
        if not raw:
            return []

        # "all"
        if raw == "all":
            return list(installers)

        # Category keywords
        category_map: dict[str, list[str]] = {
            "python": ["pygame", "NorseSagaEngine", "Viking Girlfriend Skill (OpenClaw)"],
            "js":     [i.name for i in _JS],
            "javascript": [i.name for i in _JS],
            "vtt":    [i.name for i in _JS],
            "csharp": [i.name for i in _CS],
            "dotnet": [i.name for i in _CS],
            "native": [i.name for i in _NATIVE],
            "cpp":    [i.name for i in _CPP],
            "c++":    [i.name for i in _CPP],
        }
        if raw in category_map:
            wanted = {n.lower() for n in category_map[raw]}
            return [i for i in installers if i.name.lower() in wanted]

        selected: list[BaseInstaller] = []
        seen: set[str] = set()

        for token in raw.replace(";", ",").split(","):
            token = token.strip()
            if not token:
                continue

            # Numeric
            if token.isdigit():
                idx = int(token) - 1
                if 0 <= idx < len(installers):
                    inst = installers[idx]
                    if inst.name not in seen:
                        selected.append(inst)
                        seen.add(inst.name)
                continue

            # Name match (case-insensitive partial)
            for inst in installers:
                if token in inst.name.lower() and inst.name not in seen:
                    selected.append(inst)
                    seen.add(inst.name)

        return selected

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def find_wyrd_root() -> Path:
        """Locate the WYRD-Protocol repository root.

        Searches upward from this file's location for a directory containing
        ``src/wyrdforge`` or ``ROADMAP.md``.
        """
        candidate = _INSTALL_DIR
        for _ in range(6):
            if (candidate / "src" / "wyrdforge").exists():
                return candidate
            if (candidate / "ROADMAP.md").exists():
                return candidate
            candidate = candidate.parent
        return _INSTALL_DIR.parent  # best guess

    def _find_installer_by_name(self, name: str) -> Optional[BaseInstaller]:
        name_lower = name.lower()
        for inst in ALL_INSTALLERS:
            if inst.name.lower() == name_lower or name_lower in inst.name.lower():
                return inst
        return None

    def _show_banner(self) -> None:
        print(color(_BANNER, _CYAN))

    def _show_wyrd_status(self) -> None:
        print_step("Checking WyrdHTTPServer …")
        if test_wyrd_connection():
            print_ok("WyrdHTTPServer is running at localhost:8765")
        else:
            print_info(
                "WyrdHTTPServer is not running.\n"
                "  Start it with:  python -m wyrdforge.bridges.http_api\n"
                "  (You can install first and start it later.)"
            )

    def _show_menu(self) -> None:
        n = 1
        for group, installers in GROUPS.items():
            print(f"\n  {color(group, _CYAN)}")
            for inst in installers:
                installed_mark = color(" ✓", _GREEN) if self.log.was_installed(inst.name) else "  "
                print(f"  {installed_mark} {n:2}. {inst.name}")
                n += 1
        print()
        print_info("Category shortcuts: python  js  csharp  native  cpp  all")

    def _resolve_target_dir(self, installer: BaseInstaller) -> Optional[Path]:
        """Auto-detect or ask for the target dir for *installer*."""
        from _common import common_search_paths
        candidates = installer.detect_candidates(common_search_paths())
        if candidates:
            print_info(f"Auto-detected: {candidates[0]}")
            return candidates[0]
        return None  # installer.run() will prompt the user


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="wyrd_setup",
        description="WYRD Protocol unified installer",
    )
    p.add_argument("--dry-run",    action="store_true", help="Preview without copying files")
    p.add_argument("--check",      action="store_true", help="Health-check all recorded installs")
    p.add_argument("--uninstall",  action="store_true", help="Remove all installed WYRD bridge files")
    p.add_argument("--update",     action="store_true", help="Re-run all previously recorded installs")
    p.add_argument("--list",       action="store_true", help="List all available integration targets")
    p.add_argument("--target",     metavar="NAME",      help="Install a specific target by name")
    p.add_argument("--wyrd-host",  default="localhost",  help="WyrdHTTPServer host (default: localhost)")
    p.add_argument("--wyrd-port",  type=int, default=8765, help="WyrdHTTPServer port (default: 8765)")
    return p


def main(argv: Optional[list[str]] = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    setup = WyrdSetup()

    if args.list:
        setup.run_list()
        return 0

    if args.check:
        results = setup.run_check()
        failed = sum(1 for ok in results.values() if not ok)
        return 1 if failed else 0

    if args.uninstall:
        targets = [args.target] if args.target else None
        setup.run_uninstall(targets)
        return 0

    if args.update:
        targets = [args.target] if args.target else None
        setup.run_update(targets)
        return 0

    if args.target:
        selected = setup.parse_selection(args.target, ALL_INSTALLERS)
        if not selected:
            print_err(f"No installer found for target: {args.target!r}")
            return 1
        for installer in selected:
            target_dir = setup._resolve_target_dir(installer)
            ok = setup.install_with_retry(installer, target_dir, dry_run=args.dry_run)
            if ok and not args.dry_run and target_dir:
                files = [target_dir / rel for _, rel in installer.files_to_install(setup.wyrd_root)]
                setup.log.record_install(installer.name, target_dir, files)
        return 0

    # Default: interactive
    setup.run_interactive(dry_run=args.dry_run)
    return 0


if __name__ == "__main__":
    sys.exit(main())
