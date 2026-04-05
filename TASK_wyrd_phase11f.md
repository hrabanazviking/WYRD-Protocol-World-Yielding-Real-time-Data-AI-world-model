# TASK: WYRD Protocol — Phase 11F Defold Extension

**Date:** 2026-04-05
**Branch:** development
**Status:** IN PROGRESS

## Scope

Build the Defold native extension for WYRD Protocol (Phase 11F from ROADMAP.md).
Lua + C++ extension calling WyrdHTTPServer. No SDK dependency — uses WyrdHTTPServer directly.

## Structure

```
integrations/defold/wyrdforge/
  ext.manifest                 — Defold extension manifest (name + platform stubs)
  src/
    wyrdforge.cpp              — C++ native extension: normalize_persona_id,
                                 build_query_body, build_event_body + Lua bindings
  lua/
    wyrdforge.lua              — Full Lua API module (uses Defold http + json builtins)
  api/
    wyrdforge.script_api       — Defold editor script_api for autocomplete
  tests/
    test_wyrdforge.py          — Python tests for pure C++ logic functions
```

## Lua API
- `wyrd.init(host, port)` — configure server
- `wyrd.set_enabled(bool)` — toggle
- `wyrd.query(persona_id, user_input, callback)` — async query, callback(ok, response, err)
- `wyrd.push_observation(title, summary, callback)` — write world event
- `wyrd.push_fact(subject_id, key, value, callback)` — write world fact
- `wyrd.health(callback)` — health check

## C++ native functions (via wyrdforge.*)
- `wyrdforge.normalize_persona_id(name)` → string
- `wyrdforge.build_query_body(persona_id, user_input)` → JSON string
- `wyrdforge.build_event_body(event_type, payload_json)` → JSON string

## Progress Tracker

- [x] Write TASK file
- [x] Commit + push task file
- [ ] Build ext.manifest
- [ ] Build src/wyrdforge.cpp
- [ ] Build lua/wyrdforge.lua
- [ ] Build api/wyrdforge.script_api
- [ ] Build tests/test_wyrdforge.py
- [ ] Run pytest
- [ ] Update ROADMAP.md
- [ ] Commit + push
- [ ] Update memory
