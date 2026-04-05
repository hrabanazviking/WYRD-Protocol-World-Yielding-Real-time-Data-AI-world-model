# TASK: Phase 2 — Persistent Memory Layer

**Date:** 2026-04-02
**Branch:** development
**Scope:** Graduate wyrdforge memory from in-memory to SQLite-backed. Add promotion engine,
contradiction detection, and writeback pipeline.

## File Targets

### New source files
- `src/wyrdforge/persistence/memory_store.py`   — PersistentMemoryStore (SQLite + FTS5)
- `src/wyrdforge/services/memory_promoter.py`   — Promotion engine (EPHEMERAL → CANONICAL)
- `src/wyrdforge/services/contradiction_detector.py` — Contradiction detection on fact writes
- `src/wyrdforge/services/writeback_engine.py`  — Turn output → memory store writes
- `configs/memory_promotion.yaml`               — Promotion thresholds config

### New test files
- `tests/test_persistent_memory.py`    — PersistentMemoryStore (save/load/search/promote)
- `tests/test_memory_promoter.py`      — Promotion scoring and eligibility
- `tests/test_contradiction_detector.py` — Conflict detection and quarantine
- `tests/test_writeback_engine.py`     — Writeback pipeline

## Checklist
- [x] Write this task file
- [ ] persistence/memory_store.py
- [ ] services/memory_promoter.py
- [ ] services/contradiction_detector.py
- [ ] services/writeback_engine.py
- [ ] configs/memory_promotion.yaml
- [ ] All 4 test files (40+ tests)
- [ ] pytest all passing
- [ ] Commit + push

## Status: IN PROGRESS
