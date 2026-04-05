# TASK: WYRD Protocol — Phase 13 Major Commercial Engine Bridges

**Date:** 2026-04-05
**Branch:** development
**Status:** IN PROGRESS

## Scope

Build all four major commercial engine integrations (Phase 13A-13D from ROADMAP.md).

## Sub-phases

### 13A — Unity Package (UPM)
```
integrations/unity/wyrdforge/
  package.json                        (UPM manifest: com.wyrdforge.wyrdforge)
  Runtime/
    WyrdUnityOptions.cs               (Serializable config POCO)
    WyrdEntityData.cs                 (Entity data + ToFacts() helper)
    WyrdManager.cs                    (MonoBehaviour singleton — documented wiring)
    WyrdNPC.cs                        (MonoBehaviour NPC component)
  WyrdForge.Unity.Tests/              (xUnit — pure C# logic, no Unity runtime)
    WyrdForge.Unity.Tests.csproj
    UnityBridgeTests.cs
  WyrdForge.Unity.sln
```
Testing: xUnit C# project (~40 tests). Depends on WyrdForge.Client (8B).

### 13B — Unreal Engine 5 Plugin
```
integrations/unreal/wyrdforge/
  WyrdForge.uplugin                   (plugin descriptor)
  Source/WyrdForge/
    WyrdForge.Build.cs                (module build rules)
    Public/
      WyrdTypes.h                     (FWyrdFact, FWyrdQueryResult, FWyrdConfig)
      WyrdSubsystem.h                 (UWyrdSubsystem — UGameInstanceSubsystem)
      WyrdHelpers.h                   (pure static helpers declaration)
    Private/
      WyrdHelpers.cpp                 (NormalizePersonaId, BuildQueryBody, etc.)
      WyrdSubsystem.cpp               (IHttpRequest impl + documented Blueprint nodes)
  tests/test_wyrdforge.py             (Python mirror tests)
```
Testing: Python mirror tests (~70 tests).

### 13C — CryEngine Plugin
```
integrations/cryengine/wyrdforge/
  WyrdForgePlugin.json                (CryEngine plugin descriptor)
  Code/WyrdPlugin/
    IWyrdSystem.h                     (interface + result types)
    WyrdHelpers.h
    WyrdHelpers.cpp                   (pure helpers — NormalizePersonaId, builders)
    WyrdPlugin.cpp                    (ICryPlugin impl, libcurl HTTP, wiring docs)
  tests/test_wyrdforge.py             (Python mirror tests)
```
Testing: Python mirror tests (~60 tests).

### 13D — O3DE Gem
```
integrations/o3de/wyrdforge/
  gem.json                            (O3DE gem manifest)
  Code/
    Include/WyrdForge/
      WyrdTypes.h                     (structs + enums)
      WyrdBusInterface.h              (EBus interface — WyrdRequestBus)
    Source/
      WyrdSystemComponent.h
      WyrdSystemComponent.cpp         (AZ::Component impl, AzFramework HTTP)
      WyrdHelpers.cpp                 (pure helpers)
  tests/test_wyrdforge.py             (Python mirror tests)
```
Testing: Python mirror tests (~60 tests).

## Progress Tracker

- [x] Write TASK file
- [x] Commit + push task file
- [ ] 13A: Build Unity package + xUnit tests → run tests
- [ ] 13B: Build Unreal plugin + Python tests → run tests
- [ ] 13C: Build CryEngine plugin + Python tests → run tests
- [ ] 13D: Build O3DE gem + Python tests → run tests
- [ ] Update ROADMAP.md
- [ ] Commit + push all
- [ ] Update memory
