# TASK: WYRD Protocol Phase 18 — Robustness & Self-Healing Pass

**Date started:** 2026-04-05
**Branch:** development
**Status:** IN PROGRESS

## Scope

Systematic hardening sweep across server, bridges, memory, and config.
Read existing code first — only add what's missing, don't rewrite what works.

## Sub-phases

| Sub-phase | Target | Status |
|---|---|---|
| 18A | WyrdHTTPServer: timeouts, watchdog thread, structured errors, request size limit | pending |
| 18B | Bridge utilities: exponential backoff helper, unicode normalization guard, thread pool cap | pending |
| 18C | PersistentMemoryStore: WAL mode, integrity check on startup, auto-vacuum | pending |
| 18D | Config/startup: YAML schema validator, env var type coercion, safe defaults reporter | pending |
| — | tests/test_hardening.py — tests for all new hardening code | pending |
| — | ROADMAP.md update, commit, push, memory update | pending |

## Strategy

- Read each target file before touching it
- Add hardening as new functions/methods/parameters — don't delete existing logic
- New code lives in dedicated modules where possible:
    src/wyrdforge/hardening/backoff.py        — 18B exponential backoff
    src/wyrdforge/hardening/normalization.py  — 18B unicode persona_id guard
    src/wyrdforge/hardening/pool.py           — 18B thread pool cap
    src/wyrdforge/hardening/config_validator.py — 18D YAML schema + env coercion
  Plus targeted edits to http_api.py and memory_store.py

## Next Steps (if session breaks)

1. Read this file
2. ls src/wyrdforge/hardening/ — check what exists
3. python -m pytest tests/test_hardening.py -v
4. Continue in order: 18A → 18B → 18C → 18D → tests
