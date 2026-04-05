# TASK: WYRD Protocol — Phase 11D Construct 3 Addon

**Date:** 2026-04-05
**Branch:** development
**Status:** COMPLETE

## Scope

Build the Construct 3 addon integration for WYRD Protocol (Phase 11D from ROADMAP.md).

## What Already Exists

- Phases 8A–8C (SDKs: JS/TS, C#, GDScript)
- Phases 9A–9G (AI platform bridges)
- Phases 10A–10E (TTRPG/VTT: Foundry, Roll20, FGU, Owlbear, D&D Beyond)
- Phases 11A–11C (Godot 4, RPG Maker MZ/MV, GameMaker Studio 2)
- Python tests: 526 passing

## What To Build

**Location:** `integrations/construct3/wyrdforge/`

**Files:**
1. `addon.json` — C3 addon manifest (type: plugin, single-global, defines ACEs)
2. `plugin.js` — editor-side plugin registration (properties, category, Help URL)
3. `c3runtime/plugin.js` — runtime plugin class (registers actions, conditions, expressions)
4. `c3runtime/instance.js` — runtime instance (fetch()-based HTTP client, all action handlers)
5. `lang/en-US.json` — localization strings for all ACEs and params
6. `tests/package.json` — Jest config
7. `tests/wyrdforge.test.js` — Jest tests for all pure logic functions (~40 tests)

**Actions to implement:**
- `Init(host, port, timeoutMs)` — configure WyrdHTTPServer connection
- `QueryCharacter(personaId, query)` — fetch world context for a character
- `PushObservation(title, summary)` — write a world event observation
- `PushFact(subjectId, key, value)` — write a world fact

**Conditions (triggers):**
- `OnQueryComplete` — triggers when query succeeds
- `OnQueryError` — triggers when query or push fails
- `IsReady` — true if initialized

**Expressions:**
- `LastResponse` — last successful query response string
- `LastError` — last error message string

## Pattern Reference
- Follow RPG Maker (11B) pattern: pure logic functions + inline WyrdClient using fetch()
- Tests follow same Jest pattern as RPG Maker tests
- Tests are pure-function tests; no actual C3 runtime needed

## Progress Tracker

- [x] Write TASK file (this file)
- [x] Commit + push task file
- [x] Build addon.json
- [x] Build plugin.js (editor)
- [x] Build c3runtime/plugin.js
- [x] Build c3runtime/instance.js
- [x] Build lang/en-US.json
- [x] Build tests/package.json + tests/wyrdforge.test.js
- [x] Run Jest tests (npm test)
- [x] Update ROADMAP.md (mark 11D complete)
- [x] Commit + push all files
- [x] Update memory (project_wyrd_status.md + MEMORY.md)
