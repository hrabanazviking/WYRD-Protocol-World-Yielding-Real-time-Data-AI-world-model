# TASK: WYRD Protocol — Phase 12B Minecraft Bridge (Fabric mod)

**Date:** 2026-04-05
**Branch:** development
**Status:** IN PROGRESS

## Scope

Build the Minecraft integration for WYRD Protocol (Phase 12B from ROADMAP.md).
Java Fabric mod using Java 11+ HttpClient → WyrdHTTPServer.
Chat events → WYRD query/response pipeline. Entity NBT data → WYRD entity facts.

## Structure

```
integrations/minecraft/wyrdforge/
  src/main/java/com/wyrdforge/
    WyrdForgeMod.java           (Fabric mod entry point, @Mod annotation stub)
    WyrdHttpClient.java         (Java HttpClient wrapper for WyrdHTTPServer)
    EntityMapper.java           (Entity/Player → WYRD persona ID + facts)
    ChatCommandHandler.java     (Chat command parser: /wyrd /wyrd-sync /wyrd-health)
    WyrdModConfig.java          (Config POJOs: WyrdModConfig, ChatCommandResult, QueryResult)
  tests/
    test_wyrdforge.py           (Python tests for pure logic — same pattern as Defold/GameMaker)
  build.gradle                  (Fabric mod build file)
  gradle.properties             (Minecraft + Fabric versions)
  fabric.mod.json               (Fabric mod manifest)
  .gitignore
```

## Key Design

**WyrdHttpClient** — wraps Java 11 `java.net.http.HttpClient`:
- `queryContext(personaId, query)` → `QueryResult`
- `syncEntity(personaId, List<Fact>)` → fire-and-forget per fact via `pushFact`
- `pushObservation(title, summary)` → fire-and-forget
- `pushFact(subjectId, key, value)` → fire-and-forget
- `healthCheck()` → boolean
- Timeout: configurable (default 10s)

**EntityMapper** — pure static helpers:
- `toPersonaId(entityName)` — lowercase, replace non-alphanumeric with `_`, collapse, strip, truncate 64
- `toFacts(entityName, entityId, worldName, customFacts)` — yields Fact records

**ChatCommandHandler** — pure static parser:
- `/wyrd-health` → HEALTH
- `/wyrd-sync <name>` → SYNC + personaId
- `/wyrd <persona_id> [query text]` → QUERY + personaId + query

**WyrdForgeMod** — Fabric mod entry point:
- `@Mod("wyrdforge")` annotation (stub)
- `onInitialize()` — registers server chat command listener
- Documents how to wire Fabric's `ServerChatEvents.ALLOW_CHAT` / `CommandRegistrationCallback`

## Testing Strategy

Pure logic Python mirror tests (no JVM needed for CI):
- `TestNormalizePersonaId` — 15+ cases
- `TestBuildRequestBodies` — query, observation, fact
- `TestChatCommandParsing` — all command types, edge cases
- `TestToFacts` — fact list generation

## Progress Tracker

- [x] Write TASK file
- [x] Commit + push task file
- [ ] Build build.gradle + gradle.properties + fabric.mod.json
- [ ] Build WyrdModConfig.java (config + result types)
- [ ] Build EntityMapper.java
- [ ] Build ChatCommandHandler.java
- [ ] Build WyrdHttpClient.java
- [ ] Build WyrdForgeMod.java
- [ ] Write tests/test_wyrdforge.py
- [ ] Run pytest
- [ ] Update ROADMAP.md
- [ ] Commit + push
- [ ] Update memory
