# TASK: WYRD Protocol — Phase 12C Roblox Bridge (Luau ModuleScript)

**Date:** 2026-04-05
**Branch:** development
**Status:** IN PROGRESS

## Scope

Build the Roblox integration for WYRD Protocol (Phase 12C from ROADMAP.md).
Luau ModuleScript + HttpService → WyrdHTTPServer.
NPC dialogue scripts call `WyrdBridge:Query(npcId, playerMessage)`.

## Roblox HTTP Constraint

Roblox HttpService is server-side only (Script, not LocalScript).
Client-side NPCs need RemoteEvents to send requests to the server, which then
calls WyrdHTTPServer and fires results back to the client via RemoteEvents.

## Structure

```
integrations/roblox/wyrdforge/
  WyrdConfig.lua            (Config table — host, port, timeout, enabled)
  WyrdMapper.lua            (Pure helpers: normalizePersonaId, buildQueryBody,
                             buildObservationBody, buildFactBody, parseResponse,
                             escapeJson, toFacts)
  WyrdBridge.lua            (Server ModuleScript — main API:
                             WyrdBridge:Init(config), :Query(personaId, input),
                             :PushObservation(title, summary),
                             :PushFact(subjectId, key, value),
                             :SyncNpc(npcId, facts),
                             :Health() → bool)
  WyrdRemoteSetup.lua       (Server Script — creates RemoteEvents/RemoteFunctions
                             so client LocalScripts can trigger WYRD queries)
  WyrdClientBridge.lua      (LocalScript helper — calls RemoteEvents to reach
                             the server-side WyrdBridge)
  tests/
    test_wyrdforge.py       (Python mirror tests for pure Luau logic)
```

## Key Design

**WyrdMapper** — pure module, no Roblox service dependencies:
- `normalizePersonaId(name)` — lowercase, replace non-alnum with `_`, collapse, strip, truncate 64
- `escapeJson(s)` — escape string for embedding in JSON
- `buildQueryBody(personaId, userInput)` → JSON string
- `buildObservationBody(title, summary)` → JSON string
- `buildFactBody(subjectId, key, value)` → JSON string
- `toFacts(npcName, npcId, placeId, customFacts)` → array of {key, value}
- `parseResponse(body)` → string (extracts "response" field, fallback text)

**WyrdBridge** — server ModuleScript, uses HttpService:
- `:Init(config?)` — sets up config, validates HttpService access
- `:Query(personaId, input)` — POST /query, returns response string
- `:PushObservation(title, summary)` — POST /event fire-and-forget
- `:PushFact(subjectId, key, value)` — POST /event fire-and-forget
- `:SyncNpc(npcId, facts)` — calls PushFact for each fact
- `:Health()` — GET /health → boolean
- Internal `_post(path, body)` — `HttpService:RequestAsync()`

**WyrdRemoteSetup** — Server Script:
- Creates `Workspace.WyrdEvents` folder
- Creates `RemoteFunction` "WyrdQuery" → server calls WyrdBridge:Query
- Creates `RemoteEvent` "WyrdObservation" → server calls PushObservation
- Documents usage pattern in comments

**WyrdClientBridge** — LocalScript:
- `:Query(personaId, input)` → InvokeServer on WyrdQuery RemoteFunction
- `:PushObservation(title, summary)` → FireServer on WyrdObservation RemoteEvent

## Testing Strategy

Python mirror tests for all pure-logic Luau functions in WyrdMapper:
- TestEscapeJson — special chars, control chars, None/empty
- TestNormalizePersonaId — 15 cases
- TestBuildQueryBody — 7 cases
- TestBuildObservationBody — 4 cases
- TestBuildFactBody — 5 cases
- TestToFacts — 7 cases
- TestParseResponse — 7 cases

## Progress Tracker

- [x] Write TASK file
- [x] Commit + push task file
- [ ] Build WyrdConfig.lua
- [ ] Build WyrdMapper.lua
- [ ] Build WyrdBridge.lua
- [ ] Build WyrdRemoteSetup.lua
- [ ] Build WyrdClientBridge.lua
- [ ] Write tests/test_wyrdforge.py
- [ ] Run pytest
- [ ] Update ROADMAP.md
- [ ] Commit + push
- [ ] Update memory
