# TASK: WYRD Protocol — Phase 14 Tooling & Ecosystem

**Date:** 2026-04-05
**Branch:** development
**Status:** IN PROGRESS

## Sub-phases

### 14A — Prima Scholar Claude Code Plugin
- `CLAUDE.md` — project-level Claude Code instructions for WYRD development
- `tools/prima_scholar/` — prompt templates and research workflow docs

### 14B — WYRD World Editor (TUI)
- `tools/wyrd_tui.py` — Rich-based TUI with live panels:
  world state, entity list, memory log, bond graph, command bar
- Tests: Python tests for TUI data-model helpers

### 14C — WYRD Cloud Relay
- `tools/wyrd_cloud_relay/` — FastAPI relay server:
  proxies /query /event /world /facts /health to a local WyrdHTTPServer
  Auth token, CORS, configurable upstream
- `tools/wyrd_cloud_relay/tests/test_relay.py` — Python tests

### 14D — Public Documentation Site
- `docs/` — MkDocs site:
  index, quickstart, API reference, per-platform guides, example worlds
- `mkdocs.yml` — site configuration

## Progress Tracker

- [x] Write TASK file
- [x] Commit + push task file
- [ ] 14A: CLAUDE.md + prima_scholar tools
- [ ] 14B: wyrd_tui.py + tests
- [ ] 14C: wyrd_cloud_relay + tests
- [ ] 14D: MkDocs site
- [ ] Update ROADMAP.md
- [ ] Commit + push all
- [ ] Update memory
