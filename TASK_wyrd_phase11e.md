# TASK: WYRD Protocol — Phase 11E MonoGame/FNA NuGet Package

**Date:** 2026-04-05
**Branch:** development
**Status:** IN PROGRESS

## Scope

Build the MonoGame/FNA NuGet integration for WYRD Protocol (Phase 11E from ROADMAP.md).
Thin game-loop integration using WyrdForge.Client (C# SDK from Phase 8B).

## What Already Exists

- Phase 8B: WyrdForge.Client C# SDK (sdk/csharp/) — WyrdClient, WyrdClientOptions, all Models
- Phase 10C: FGU C# integration (integrations/fgu/) — pattern reference for C#/xUnit structure
- Phase 11D: Construct 3 addon (complete)
- Python tests: 526 passing

## What To Build

**Location:** `integrations/monogame/wyrdforge/`

**Structure:**
```
WyrdForge.MonoGame.sln
WyrdForge.MonoGame/
  WyrdForge.MonoGame.csproj   (net8.0, refs WyrdForge.Client — no MonoGame dep)
  WyrdSystem.cs               (WyrdSystem, WyrdSystemOptions, WyrdQueryResult)
  WyrdEntity.cs               (WyrdEntity — game object → WYRD ECS bridge)
WyrdForge.MonoGame.Tests/
  WyrdForge.MonoGame.Tests.csproj  (xUnit)
  WyrdSystemTests.cs
.gitignore
```

**Key API:**
- `WyrdSystem.Update(TimeSpan elapsed)` — game loop hook (no MonoGame dep; call with gameTime.ElapsedGameTime)
- `WyrdSystem.QueueQuery(personaId, query, onComplete)` — fire-and-forget, callback runs on Update
- `WyrdSystem.QueryAsync(...)` — full async for out-of-loop use
- `WyrdSystem.PushObservation(title, summary)` — fire-and-forget
- `WyrdSystem.PushFact(subjectId, key, value)` — fire-and-forget
- `WyrdSystem.RegisterEntity(WyrdEntity)` / `SyncEntityAsync(entityId)` / `SyncAllEntitiesAsync()`
- `WyrdSystem.NormalizePersonaId(name)` — static helper
- `WyrdEntity` — Id, Name, LocationId, Tags, CustomFacts, ToFacts()

**Target:** ~30 xUnit tests

## Progress Tracker

- [x] Write TASK file
- [x] Commit + push task file
- [ ] Build .sln + .csproj files
- [ ] Build WyrdSystem.cs
- [ ] Build WyrdEntity.cs
- [ ] Build WyrdSystemTests.cs
- [ ] Run dotnet test
- [ ] Update ROADMAP.md (mark 11E complete)
- [ ] Commit + push
- [ ] Update memory
