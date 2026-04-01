# TASK: Phase 0 — Foundation & Package Setup

**Date:** 2026-04-01
**Branch:** development
**Scope:** Turn WYRD Protocol from a research-heavy directory into a proper installable Python project with clean structure, CI, and passing tests.

## Checklist

- [x] Write this task file
- [ ] Promote `research_data/src/wyrdforge/` → `src/wyrdforge/`
- [ ] Promote `research_data/tests/` → `tests/`
- [ ] Promote `research_data/config/` → `configs/`
- [ ] Promote `research_data/examples/` → `examples/`
- [ ] Promote `research_data/scripts/` → `scripts/`
- [ ] Reorganize `docs/specs/` → `docs/specs/wyrd/` (WYRD-specific) + `docs/specs/shared/` (MindSpark/shared)
- [ ] Create `pyproject.toml`
- [ ] Create `requirements.txt`
- [ ] Create `.gitignore` (if not exists or update)
- [ ] Create `.github/workflows/ci.yml`
- [ ] Verify `pip install -e .` works
- [ ] Verify `pytest tests/` passes
- [ ] Commit + push as "phase0: foundation and package setup"

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
