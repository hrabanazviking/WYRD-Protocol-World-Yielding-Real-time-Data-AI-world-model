# TASK: WYRD Protocol Phase 17 — Unified Menu-Driven Installer

**Date started:** 2026-04-05
**Branch:** development
**Status:** IN PROGRESS

## Scope

Single entry-point `install/wyrd_setup.py` that:
- Shows ASCII banner and welcome
- Auto-detects WyrdHTTPServer status
- Presents numbered menu of all 21 integration targets (grouped by category)
- User selects targets ("1,3,5" or "all" or "python")
- Runs the matching Phase 16 installers
- Writes wyrd_install_log.json (partial-install resume)
- Self-heals: diagnoses failures, offers retry, resumes from log
- --uninstall, --update, --check flags (17C)

## File Inventory

```
install/
    wyrd_setup.py         — 17A/17B/17C: WyrdSetup, InstallLog, DiagnosticsEngine
    tests/
        test_setup.py     — ~70 pytest tests
```

## Key Classes

InstallLog:
  - load() / save(data) — reads/writes wyrd_install_log.json
  - record_install(target_name, target_dir, files, timestamp)
  - get_installed() -> list[dict]
  - remove_target(target_name)
  - was_installed(target_name) -> bool

DiagnosticsEngine:
  - diagnose_failure(installer, exc, target_dir) -> str
  - suggest_fix(diagnosis) -> str
  - check_tool(name) -> bool  (python/node/dotnet/java/gradle/cmake)

WyrdSetup:
  - all_installers — flat list of all 21 BaseInstaller instances
  - grouped_installers — dict of category → list[installer]
  - parse_selection(raw, installers) -> list[BaseInstaller]
  - find_wyrd_root() -> Path
  - install_with_retry(installer, target_dir, dry_run, max_retries=2) -> bool
  - run_interactive(dry_run=False)
  - run_check() -> dict[str, bool]
  - run_uninstall(targets=None)
  - run_update(targets=None)

## Sub-phase Status

| Sub-phase | Deliverable | Status |
|---|---|---|
| 17A | WyrdSetup, InstallLog, banner, menu, install flow | pending |
| 17B | DiagnosticsEngine, retry loop, partial-install resume | pending |
| 17C | --uninstall, --update, --check + argparse CLI | pending |
| — | tests/test_setup.py (~70 tests) | pending |
| — | ROADMAP.md update, commit, push, memory update | pending |

## Next Steps (if session breaks)

1. Read this file
2. Check ls install/ for wyrd_setup.py existence
3. Run python -m pytest install/tests/test_setup.py -v
4. Complete in order: InstallLog → DiagnosticsEngine → WyrdSetup → CLI → tests
