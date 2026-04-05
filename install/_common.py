"""_common.py — Shared base for all WYRD per-platform install scripts.

Provides:
  - BaseInstaller ABC — interface every installer implements
  - ANSI terminal output helpers (safe on all platforms)
  - WyrdHTTPServer connection tester
  - File copy helper (dry-run aware)
  - Directory detection by sentinel file markers
"""
from __future__ import annotations

import os
import shutil
import urllib.request
import urllib.error
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Optional


# ---------------------------------------------------------------------------
# ANSI colour helpers (no external deps; fall back silently if not supported)
# ---------------------------------------------------------------------------

_ANSI = os.environ.get("TERM", "") != "dumb" and os.name != "nt" or os.environ.get("ANSICON") or os.environ.get("WT_SESSION")

_GREEN  = "\033[92m" if _ANSI else ""
_RED    = "\033[91m" if _ANSI else ""
_YELLOW = "\033[93m" if _ANSI else ""
_CYAN   = "\033[96m" if _ANSI else ""
_BOLD   = "\033[1m"  if _ANSI else ""
_RESET  = "\033[0m"  if _ANSI else ""


def color(text: str, code: str) -> str:
    """Wrap *text* in an ANSI colour code + reset."""
    if not code:
        return text
    return f"{code}{text}{_RESET}"


def print_ok(msg: str) -> None:
    print(f"  {color('✓', _GREEN)} {msg}")


def print_err(msg: str) -> None:
    print(f"  {color('✗', _RED)} {msg}")


def print_info(msg: str) -> None:
    print(f"  {color('·', _CYAN)} {msg}")


def print_step(msg: str) -> None:
    print(f"\n{color(msg, _BOLD)}")


def print_header(title: str) -> None:
    bar = "─" * (len(title) + 4)
    print(f"\n{color(bar, _CYAN)}")
    print(f"{color('  ' + title + '  ', _BOLD)}")
    print(f"{color(bar, _CYAN)}")


# ---------------------------------------------------------------------------
# WyrdHTTPServer connection test
# ---------------------------------------------------------------------------

def test_wyrd_connection(host: str = "localhost", port: int = 8765, timeout: int = 5) -> bool:
    """Return True if WyrdHTTPServer is reachable at *host*:*port*."""
    url = f"http://{host}:{port}/health"
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            return resp.status == 200
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Directory detection helpers
# ---------------------------------------------------------------------------

def find_dir_by_markers(
    search_paths: list[Path],
    markers: list[str],
    *,
    require_all: bool = False,
) -> list[Path]:
    """Return directories in *search_paths* that contain sentinel *markers*.

    Args:
        search_paths:  Directories to check (non-existent ones are skipped).
        markers:       File/dir names that must be present.
        require_all:   If True, ALL markers must be present.  Default: any one.

    Returns:
        Sorted list of matching Path objects.
    """
    matches: list[Path] = []
    for base in search_paths:
        if not base or not base.exists():
            continue
        found = [m for m in markers if (base / m).exists()]
        if require_all:
            if len(found) == len(markers):
                matches.append(base)
        else:
            if found:
                matches.append(base)
    return sorted(set(matches))


def common_search_paths() -> list[Path]:
    """Return a broad set of candidate parent directories for auto-detection."""
    home = Path.home()
    paths = [
        home,
        home / "Documents",
        home / "AppData" / "Local",
        home / "AppData" / "Roaming",
        home / "AppData" / "LocalLow",
        Path("C:/Program Files"),
        Path("C:/Program Files (x86)"),
        Path("C:/"),
    ]
    # Add common dev roots
    for name in ("projects", "dev", "runa", "games", "source"):
        paths.append(home / name)
    return [p for p in paths if p.exists()]


# ---------------------------------------------------------------------------
# File copy helper
# ---------------------------------------------------------------------------

def copy_bridge_files(
    files: list[tuple[Path, Path]],
    *,
    dry_run: bool = False,
) -> list[Path]:
    """Copy bridge files to their destination paths.

    Args:
        files:   List of (source_path, destination_path) pairs.
        dry_run: If True, print what would be copied but don't touch the filesystem.

    Returns:
        List of destination Paths that were (or would be) written.
    """
    written: list[Path] = []
    for src, dst in files:
        if dry_run:
            print_info(f"[dry-run] would copy {src.name} → {dst}")
        else:
            dst.parent.mkdir(parents=True, exist_ok=True)
            if src.is_dir():
                if dst.exists():
                    shutil.rmtree(dst)
                shutil.copytree(src, dst)
            else:
                shutil.copy2(src, dst)
            print_ok(f"Copied {src.name} → {dst}")
        written.append(dst)
    return written


# ---------------------------------------------------------------------------
# BaseInstaller ABC
# ---------------------------------------------------------------------------

class BaseInstaller(ABC):
    """Abstract base class for all WYRD platform installers.

    Subclass this and implement the abstract properties / methods.
    """

    # ------------------------------------------------------------------
    # Identity (class-level attributes; set in each subclass)
    # ------------------------------------------------------------------

    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable target name (e.g. ``'Foundry VTT'``)."""

    @property
    @abstractmethod
    def description(self) -> str:
        """One-line description shown in the menu."""

    # ------------------------------------------------------------------
    # Detection
    # ------------------------------------------------------------------

    @abstractmethod
    def detect_candidates(self, search_paths: list[Path]) -> list[Path]:
        """Return candidate installation directories found in *search_paths*.

        Returns an empty list if nothing is detected.
        """

    # ------------------------------------------------------------------
    # Files
    # ------------------------------------------------------------------

    @abstractmethod
    def files_to_install(self, wyrd_root: Path) -> list[tuple[Path, str]]:
        """Return a list of ``(absolute_source_path, relative_destination)`` pairs.

        The destination is relative to the target directory chosen by the user.
        """

    # ------------------------------------------------------------------
    # Dependencies
    # ------------------------------------------------------------------

    def install_deps_cmd(self, target_dir: Path) -> list[str] | None:  # noqa: UP007
        """Return the shell command to install dependencies, or None.

        The command is run in *target_dir*.  Return ``None`` if no deps are needed.
        """
        return None

    # ------------------------------------------------------------------
    # Post-install
    # ------------------------------------------------------------------

    @abstractmethod
    def post_install_notes(self) -> str:
        """Return a multi-line string of next steps to show after install."""

    # ------------------------------------------------------------------
    # Run
    # ------------------------------------------------------------------

    def run(
        self,
        wyrd_root: Path,
        target_dir: Optional[Path] = None,
        *,
        dry_run: bool = False,
        wyrd_host: str = "localhost",
        wyrd_port: int = 8765,
    ) -> bool:
        """Execute the full install flow.

        1. Detect or accept *target_dir*.
        2. Resolve files to install.
        3. Copy files (or dry-run).
        4. Run deps command if any.
        5. Test WyrdHTTPServer connection.
        6. Print post-install notes.

        Returns True on success, False if any step failed.
        """
        print_header(f"WYRD × {self.name} Installer")

        # --- detect ---
        if target_dir is None:
            print_step("Detecting installation directory …")
            candidates = self.detect_candidates(common_search_paths())
            if candidates:
                target_dir = candidates[0]
                print_ok(f"Found: {target_dir}")
            else:
                print_err(f"Could not auto-detect {self.name} installation.")
                raw = input("  Enter path manually (or blank to abort): ").strip()
                if not raw:
                    print_err("Aborted.")
                    return False
                target_dir = Path(raw)

        if not target_dir.exists() and not dry_run:
            print_err(f"Target directory does not exist: {target_dir}")
            return False

        # --- files ---
        print_step("Resolving files …")
        pairs = self.files_to_install(wyrd_root)
        resolved: list[tuple[Path, Path]] = [
            (src, target_dir / rel_dst) for src, rel_dst in pairs
        ]
        for src, dst in resolved:
            print_info(f"{src.name}  →  {dst}")

        # --- copy ---
        print_step("Copying bridge files …")
        copy_bridge_files(resolved, dry_run=dry_run)

        # --- deps ---
        cmd = self.install_deps_cmd(target_dir)
        if cmd:
            print_step("Installing dependencies …")
            if dry_run:
                print_info(f"[dry-run] would run: {' '.join(cmd)}")
            else:
                import subprocess
                result = subprocess.run(cmd, cwd=target_dir)
                if result.returncode != 0:
                    print_err("Dependency install failed.")
                    return False
                print_ok("Dependencies installed.")

        # --- health check ---
        print_step("Testing WyrdHTTPServer connection …")
        if test_wyrd_connection(wyrd_host, wyrd_port):
            print_ok(f"WyrdHTTPServer is reachable at {wyrd_host}:{wyrd_port}")
        else:
            print_info(
                f"WyrdHTTPServer not reachable at {wyrd_host}:{wyrd_port} "
                "(start it with: python -m wyrdforge.bridges.http_api)"
            )

        # --- notes ---
        print_step("Next steps:")
        for line in self.post_install_notes().strip().splitlines():
            print_info(line)

        print_ok(f"{self.name} install complete.")
        return True
