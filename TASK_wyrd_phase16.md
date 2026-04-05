# TASK: WYRD Protocol Phase 16 — Per-Platform Install Scripts

**Date started:** 2026-04-05
**Branch:** development
**Status:** IN PROGRESS

## Scope

Build one installer per integration target, all Python, grouped into 5 module files
(one per sub-phase). Every installer: detects the target, copies bridge files, installs
deps, runs a health check, prints clear success/failure + next steps.

## File Inventory

```
install/
    __init__.py
    _common.py               — shared base class, ANSI output, path detection, connection test
    install_python.py        — 16A: pygame, NSE, VGSK
    install_js.py            — 16B: SillyTavern, Foundry, Roll20, Owlbear, DnDBeyond, RPGMaker, Construct3
    install_csharp.py        — 16C: Unity, MonoGame, FGU, OpenSim
    install_native.py        — 16D: Minecraft, Roblox, Godot, Defold
    install_cpp.py           — 16E: Unreal, CryEngine, O3DE
    tests/
        __init__.py
        test_common.py       — tests for _common.py utilities
        test_installers.py   — tests for all installer classes (detection, file lists, notes)
```

## Design

Each installer is a class inheriting `BaseInstaller`:
  - `name: str` — target name
  - `description: str` — one-liner
  - `bridge_src_dir(wyrd_root: Path) -> Path` — WYRD source location
  - `detect_candidates(search_paths: list[Path]) -> list[Path]` — auto-detect
  - `files_to_install(wyrd_root: Path) -> list[tuple[Path, str]]` — (src_path, rel_dst)
  - `install_deps_cmd(target_dir: Path) -> list[str] | None` — shell command or None
  - `post_install_notes() -> str` — what to do after install
  - `run(wyrd_root, target_dir=None, dry_run=False, wyrd_host="localhost", wyrd_port=8765)`

_common.py provides:
  - `BaseInstaller` ABC
  - `color(text, code)` — ANSI, safe on all terminals
  - `print_ok/err/info/step(msg)`
  - `test_wyrd_connection(host, port, timeout=5) -> bool`
  - `copy_bridge_files(files, target_dir, dry_run=False) -> list[Path]`
  - `find_dir_by_markers(search_paths, markers) -> list[Path]` — detect by sentinel files

## Sub-phase Status

| Sub-phase | Deliverable | Status |
|---|---|---|
| 16A | install/_common.py + install_python.py (pygame, NSE, VGSK) | pending |
| 16B | install_js.py (ST, Foundry, Roll20, Owlbear, DnDBeyond, RPGMaker, Construct3) | pending |
| 16C | install_csharp.py (Unity, MonoGame, FGU, OpenSim) | pending |
| 16D | install_native.py (Minecraft, Roblox, Godot, Defold) | pending |
| 16E | install_cpp.py (Unreal, CryEngine, O3DE) | pending |
| 16F | tests/ (~90 tests) | pending |
| — | ROADMAP.md update | pending |
| — | git commit + push | pending |
| — | memory update | pending |

## Next Steps (if session breaks)

1. Read this file
2. `ls install/` to see what exists
3. Run `python -m pytest install/tests/ -v` to see what passes
4. Complete missing files in order: _common → python → js → csharp → native → cpp → tests
