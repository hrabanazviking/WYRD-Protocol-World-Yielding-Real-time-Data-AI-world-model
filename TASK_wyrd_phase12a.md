# TASK: WYRD Protocol — Phase 12A OpenSim / Second Life Bridge

**Date:** 2026-04-05
**Branch:** development
**Status:** IN PROGRESS

## Scope

Build the OpenSim/Second Life integration for WYRD Protocol (Phase 12A from ROADMAP.md).
Two components: C# OpenSim region module + LSL in-world NPC script.

## Structure

```
integrations/opensim/wyrdforge/
  WyrdForge.OpenSim.sln
  WyrdForge.OpenSim/
    WyrdForge.OpenSim.csproj       (net8.0, refs WyrdForge.Client)
    WyrdForgeRegionModule.cs       (OpenSim region module — IRegionModuleBase pattern)
    AvatarRecord.cs                (AvatarRecord + AvatarMapper — pure data mapping)
    ChatCommandParser.cs           (/wyrd /wyrd-sync /wyrd-health command parser)
  WyrdForge.OpenSim.Tests/
    WyrdForge.OpenSim.Tests.csproj (xUnit)
    OpenSimTests.cs                (~30 xUnit tests)
  lsl/
    wyrdforge_npc.lsl              (LSL in-world NPC object script)
  .gitignore
```

## Key Design

**C# module** — WyrdForgeRegionModule wraps WyrdForge.Client:
- `QueryContextAsync(personaId, query)` → WyrdContextResult
- `SyncAvatarAsync(AvatarRecord)` → WyrdSyncResult
- `DispatchChatCommandAsync(message)` → string reply or null
- OpenSim region event wiring documented in comments (wire to OnChatFromClient, OnMakeRootAgent, etc.)

**LSL script** — wyrdforge_npc.lsl:
- Touch → `llHTTPRequest()` POST /query with avatar name as persona_id
- `http_response` → `llSay()` the WYRD response
- `/wyrd-config` listen channel for host/port configuration
- `llJsonGetValue()` for response parsing (LSL17+)
- Graceful fallback if server unreachable

## Progress Tracker

- [x] Write TASK file
- [x] Commit + push task file
- [ ] Build .sln + .csproj files
- [ ] Build AvatarRecord.cs + ChatCommandParser.cs
- [ ] Build WyrdForgeRegionModule.cs
- [ ] Build OpenSimTests.cs
- [ ] Run dotnet test
- [ ] Build lsl/wyrdforge_npc.lsl
- [ ] Update ROADMAP.md
- [ ] Commit + push
- [ ] Update memory
