# TASK: Phase 0 — Foundation & Package Setup

**Date:** 2026-04-01
**Branch:** development
**Scope:** Turn WYRD Protocol from a research-heavy directory into a proper installable Python project with clean structure, CI, and passing tests.

## Checklist

- [x] Write this task file
- [x] Promote `research_data/src/wyrdforge/` → `src/wyrdforge/`
- [x] Promote `research_data/tests/` → `tests/`
- [x] Promote `research_data/config/` → `configs/`
- [x] Promote `research_data/examples/` → `examples/`
- [x] Promote `research_data/scripts/` → `scripts/`
- [x] Reorganize `docs/specs/` → `docs/specs/wyrd/` (WYRD-specific) + `docs/specs/shared/` (MindSpark/shared)
- [x] Create `pyproject.toml`
- [x] Create `requirements.txt`
- [x] Create `.gitignore`
- [x] Create `.github/workflows/ci.yml`
- [x] Fix `datetime.UTC` → `timezone.utc` for Python 3.10 compat
- [x] Verify `pip install -e .` works
- [x] Verify `pytest tests/` — 4/4 passing
- [x] Commit + push as "phase0: foundation and package setup"

## Status: COMPLETE

## Key Paths

| Item | Path |
|---|---|
| Source package | `src/wyrdforge/` |
| Tests | `tests/` |
| Configs | `configs/` |
| Examples | `examples/` |
| Scripts | `scripts/` |
| WYRD specs | `docs/specs/wyrd/` |
| Shared specs | `docs/specs/shared/` |
| pyproject.toml | repo root |

## Notes
- Keep `research_data/` intact (the research MDs stay there — they're reference material)
- Only the Python source tree, tests, configs, examples, scripts are promoted
- `research_data/src/wyrdforge/schemas/` → `src/wyrdforge/schemas/`
- Do NOT delete research_data/ — it's valuable reference
