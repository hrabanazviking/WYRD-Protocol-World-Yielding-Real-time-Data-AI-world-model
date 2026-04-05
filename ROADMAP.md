# WYRD Protocol — Post-v1.0.0 Integration Roadmap

> **Base complete:** v1.0.0 on `development` — 7 phases, 432 tests.
> This document covers everything after the core engine: client SDKs, engine plugins, platform bridges, and tooling.

---

## Foundation Already In Place

| Layer | What it provides to all future plugins |
|---|---|
| `PythonRPGBridge` | Direct in-process Python integration — import and call |
| `WyrdHTTPServer` | Language-agnostic HTTP JSON API — any engine can POST /query |
| `BifrostBridge` (ABC) | Contract all future bridges must satisfy |
| `EvalHarness` | Automated quality checks for any bridge output |

Every phase below builds on one or both of these surfaces.

---

## Phase 8 — Client SDK Layer (PREREQUISITE FOR PHASES 9–13)

**Why first:** Phases 9–13 all need a thin language-appropriate client that wraps WyrdHTTPServer calls. Building these once here avoids duplicating HTTP plumbing in every plugin.

### 8A — JavaScript / TypeScript SDK (`wyrdforge-js`)
- npm package: `wyrdforge-js`
- `WyrdClient` class: `query()`, `getWorld()`, `getFacts()`, `pushEvent()`
- TypeScript types mirroring Python models (WorldContextPacket, CharacterContextResult, etc.)
- Auto-reconnect + timeout handling
- **Unlocks:** SillyTavern, Roll20, Foundry VTT, Owlbear Rodeo, Roblox (TypeScript variant), D&D Beyond extension

### 8B — C# / .NET SDK (`WyrdForge.Client`)
- NuGet package: `WyrdForge.Client`
- `WyrdClient` class matching JS API surface
- Async/await, `System.Net.Http.HttpClient` based
- Unity-compatible (no async/await in some Unity contexts — provide coroutine variant)
- **Unlocks:** Unity, Monogame, Fantasy Grounds Unity, OpenSim, CryEngine, Amazon Lumberyard/O3DE

### 8C — GDScript / Godot HTTP module
- Godot 4 addon (`addons/wyrdforge/`)
- `WyrdBridge` node: `query()`, `push_event()` as Godot signals
- Uses Godot's built-in `HTTPRequest` node — no external deps
- **Unlocks:** Godot engine integration

**Estimated scope:** 3 small libraries, ~200 lines each. Tests via mocked WyrdHTTPServer.

---

## Phase 9 — AI Companion & Agent Platform Bridges

**Priority: HIGH** — These directly serve Volmarr's active projects.

### 9A — OpenClaw Bridge
- **Approach:** Node.js plugin calling `wyrdforge-js` SDK
- OpenClaw skill receives world state injection before each LLM call
- `WyrdOpenClawPlugin`: hooks into OpenClaw's skill pipeline pre/post-turn
- VGSK's Sigrid gets WYRD bond graph, ECS location, runic state automatically
- **Dependency:** 8A

### 9B — Norse Saga Engine Bridge
- **Approach:** Python module dropped into NSE's existing skill system
- NSE NPCs become ECS entities; NSE world rooms become Yggdrasil locations
- `NSEWyrdBridge`: wraps PythonRPGBridge, maps NSE entity IDs → WYRD entity IDs
- Emotional engine state synced as HamingjaComponent values
- **Dependency:** PythonRPGBridge (already exists — minimal extra work)

### 9C — SillyTavern Extension
- **Approach:** SillyTavern extension JS file using `wyrdforge-js`
- Injects WYRD world context into SillyTavern's system prompt on each message
- Extension UI panel: character picker, world state viewer, bond editor
- **Dependency:** 8A

### 9D — Voxta Integration
- **Approach:** Voxta action/service calling WyrdHTTPServer
- World state + character context delivered to Voxta as additional context layer
- **Dependency:** WyrdHTTPServer (already exists)

### 9E — Kindroid Bridge
- **Approach:** Webhook-based; Kindroid sends messages to WYRD HTTP endpoint
- WYRD enriches context, returns formatted system prompt injection
- **Dependency:** WyrdHTTPServer (already exists)

### 9F — Hermes Agent Bridge
- **Approach:** Python tool/plugin for Hermes agent framework
- Registers WYRD as a world-state tool callable by the agent
- **Dependency:** PythonRPGBridge (already exists)

### 9G — AgentZero Bridge
- **Approach:** AgentZero memory/context tool wrapping PythonRPGBridge
- WYRD becomes the persistent world memory backend for AgentZero agents
- **Dependency:** PythonRPGBridge (already exists)

---

## Phase 10 — TTRPG / Virtual Tabletop Bridges

**Priority: MEDIUM** — Large potential user base; TTRPG players are prime WYRD users.

### 10A — Foundry VTT Module
- **Approach:** Foundry module (`module.json`) using `wyrdforge-js`
- Auto-syncs Foundry scene entities → WYRD ECS on scene load
- GM panel: live world state, memory log, contradiction alerts
- NPC chat using WYRD CharacterContext fed to configured LLM
- **Dependency:** 8A

### 10B — Roll20 API Script
- **Approach:** Roll20 API script (Node.js environment) using `wyrdforge-js`
- Character sheet data → WYRD canonical facts on sheet update
- Campaign log entries → WYRD observations
- **Dependency:** 8A

### 10C — Fantasy Grounds Unity Extension
- **Approach:** C# extension for FGU calling `WyrdForge.Client`
- NPC records → WYRD entities; campaign journal → WYRD memory store
- **Dependency:** 8B

### 10D — Owlbear Rodeo Extension
- **Approach:** Owlbear extension (React/JS) using `wyrdforge-js`
- Token metadata → WYRD entity components
- Room change → Yggdrasil location update via push_event
- **Dependency:** 8A

### 10E — D&D Beyond
- **Approach:** Browser extension (Chrome/Firefox) + WyrdHTTPServer
- Scrapes character sheet data → WYRD facts via content script
- **Complexity note:** D&D Beyond has no public plugin API; this is a browser extension only — fragile and dependent on their DOM structure. Lower reliability than other VTT targets.
- **Dependency:** 8A

---

## Phase 11 — Indie Game Engine Bridges

**Priority: MEDIUM** — Broader ecosystem reach; Godot especially strategic (open source, Python-friendly community).

### 11A — Godot 4 Plugin
- **Approach:** GDScript addon + optional GDExtension for performance
- `WyrdBridge` autoload singleton; `WyrdEntity` node component
- Godot signals for world events → WYRD push_event
- Inspector panel: live entity state, memory log
- **Dependency:** 8C

### 11B — RPG Maker MZ/MV Plugin
- **Approach:** RPG Maker JS plugin using `wyrdforge-js`
- Map events → Yggdrasil location changes
- Event script calls → `WYRD.query(characterId, playerInput)`
- **Dependency:** 8A

### 11C — GameMaker Extension
- **Approach:** GameMaker extension using `wyrdforge-js` (GMS2 uses Node.js for extensions) or HTTP via GML's `http_get_request()`
- GML async HTTP → WyrdHTTPServer
- **Dependency:** WyrdHTTPServer (already exists)

### 11D — Construct 3 Addon
- **Approach:** Construct 3 plugin (JS) using `wyrdforge-js`
- Event sheet actions: "WYRD Query Character", "WYRD Push Event"
- **Dependency:** 8A

### 11E — MonoGame / FNA NuGet Package
- **Approach:** C# NuGet extension using `WyrdForge.Client`
- Thin game-loop integration: `WyrdSystem.Update()` in game update loop
- **Dependency:** 8B

### 11F — Defold Extension
- **Approach:** Defold native extension (Lua + C++) calling WyrdHTTPServer
- Lua API: `wyrd.query(persona_id, input, callback)`
- **Dependency:** WyrdHTTPServer (already exists)

---

## Phase 12 — Sandbox Platform Bridges

**Priority: MEDIUM-LOW** — High reach but high technical complexity; sandboxed scripting environments have strict limits.

### 12A — OpenSim / Second Life Bridge
- **Approach:** OpenSim module (C#) + LSL script communicating via HTTP-in to WyrdHTTPServer
- LSL `llHTTPRequest()` → WyrdHTTPServer → character response → `llSay()`
- Full Second Life dream: WYRD-grounded NPC residents
- **Dependency:** 8B (for OpenSim server-side), WyrdHTTPServer (for LSL scripts)

### 12B — Minecraft Bridge (Fabric/Forge mod)
- **Approach:** Java mod using `OkHttp` or `HttpClient` → WyrdHTTPServer
- Entity NBT data → WYRD entity facts
- Chat events → WYRD query/response pipeline
- **Complexity note:** Java environment, separate runtime. Moderately complex.
- **Dependency:** WyrdHTTPServer (already exists)

### 12C — Roblox Module
- **Approach:** Roblox ModuleScript (Luau) + HttpService → WyrdHTTPServer
- NPC dialogue scripts call `WyrdBridge:Query(npcId, playerMessage)`
- **Complexity note:** Roblox HttpService only available on server-side scripts; client NPCs need RemoteEvents.
- **Dependency:** WyrdHTTPServer (already exists)

---

## Phase 13 — Major Commercial Engine Bridges

**Priority: LOW-MEDIUM** — Largest potential scale; highest technical cost. Best done after Phases 9–11 establish proven patterns.

### 13A — Unity Package
- **Approach:** Unity Package Manager package using `WyrdForge.Client`
- `WyrdManager` MonoBehaviour singleton
- `WyrdNPC` component: entity_id, auto-registers with WYRD on Start()
- Unity Editor panel: live world state inspector, memory log
- **Dependency:** 8B

### 13B — Unreal Engine Plugin
- **Approach:** UE5 plugin (C++) calling WyrdHTTPServer via UE's `IHttpRequest`
- `UWyrdSubsystem` game subsystem
- Blueprint-callable nodes: "Wyrd Query NPC", "Wyrd Push Event"
- **Complexity:** Highest of all targets. UE plugin development requires careful packaging.
- **Dependency:** WyrdHTTPServer (already exists)

### 13C — CryEngine Plugin
- **Approach:** C++ plugin using libcurl → WyrdHTTPServer
- `IWyrdSystem` interface registered with CryEngine's plugin system
- **Dependency:** WyrdHTTPServer (already exists)

### 13D — Amazon Lumberyard / O3DE Gem
- **Approach:** O3DE Gem (C#/C++) using `WyrdForge.Client` or direct HTTP
- `WyrdSystemComponent` registered as O3DE component
- **Dependency:** 8B or WyrdHTTPServer

---

## Phase 14 — Tooling & Ecosystem

### 14A — Prima Scholar Plugin (Claude Code)
- Install and configure for WYRD dev workflow
- Document how to use it for WYRD research and spec work

### 14B — WYRD World Editor (CLI → TUI)
- Extend `wyrd_chat_cli.py` into a full TUI (Textual or Rich-based)
- Live world state panel, memory browser, entity inspector, bond graph viewer

### 14C — WYRD Cloud Relay (optional)
- Thin relay server for plugins running on clients that can't reach a local WyrdHTTPServer
- Enables cloud-hosted WYRD for non-local setups (Roblox, hosted Foundry, etc.)

### 14D — Public Documentation Site
- Docusaurus or MkDocs site
- API reference, quickstart guides per platform, example worlds

---

## Recommended Build Order

```
Phase 8 (SDK layer)
    │
    ├─── Phase 9 (AI companions/agents)  ← HIGHEST VALUE for Volmarr's existing projects
    │         9B (NSE) and 9A (OpenClaw) first — they're nearly free given PythonRPGBridge
    │
    ├─── Phase 10 (TTRPG/VTT)           ← Foundry VTT first — largest user base
    │
    ├─── Phase 11 (Indie engines)        ← Godot first — biggest open-source community
    │
    ├─── Phase 12 (Sandbox platforms)    ← OpenSim first (Second Life dream)
    │
    └─── Phase 13 (Major engines)        ← Unity first, then Unreal
             └─── Phase 14 (Tooling)
```

---

## Complexity & Effort Tiers

| Tier | Targets | Reason |
|---|---|---|
| **Near-zero** (wrap existing bridges) | NSE, Hermes, AgentZero, Voxta, Kindroid | PythonRPGBridge or HTTP already works |
| **Low** (thin JS/C# client) | SillyTavern, Roll20, Owlbear, RPG Maker, Gamemaker, Defold, Roblox | SDK call + thin plugin wrapper |
| **Medium** (engine plugin system) | Godot, Foundry VTT, Construct 3, FGU, OpenSim, Monogame | Engine-specific plugin architecture |
| **High** (native integration + editor tooling) | Unity, Minecraft | C#/Java with editor panels |
| **Very High** (C++ engine plugins) | Unreal, CryEngine, O3DE | C++ plugin systems, complex packaging |
| **Fragile** (no official API) | D&D Beyond | Browser extension scraping — DOM-dependent |

---

## Tracking

| Phase | Status | Target |
|---|---|---|
| 8A — JS/TS SDK | complete | sdk/js/ |
| 8B — C# SDK | complete | sdk/csharp/ |
| 8C — GDScript module | complete | sdk/gdscript/ |
| 9A — OpenClaw | complete | src/wyrdforge/bridges/openclaw_bridge.py |
| 9B — NSE | complete | src/wyrdforge/bridges/nse_bridge.py |
| 9C — SillyTavern | complete | integrations/sillytavern/wyrdforge/ |
| 9D — Voxta | complete | src/wyrdforge/bridges/voxta_bridge.py |
| 9E — Kindroid | complete | src/wyrdforge/bridges/kindroid_bridge.py |
| 9F — Hermes Agent | complete | src/wyrdforge/bridges/hermes_bridge.py |
| 9G — AgentZero | complete | src/wyrdforge/bridges/agentzero_bridge.py |
| 10A — Foundry VTT | complete | integrations/foundry/wyrdforge/ |
| 10B — Roll20 | complete | integrations/roll20/wyrdforge/ |
| 10C — Fantasy Grounds Unity | complete | integrations/fgu/ |
| 10D — Owlbear Rodeo | complete | integrations/owlbear/wyrdforge/ |
| 10E — D&D Beyond | complete | integrations/dndbeyond/wyrdforge/ |
| 11A — Godot 4 | complete | integrations/godot/wyrdforge/ |
| 11B — RPG Maker | complete | integrations/rpgmaker/wyrdforge/ |
| 11C — GameMaker | complete | integrations/gamemaker/wyrdforge/ |
| 11D — Construct 3 | complete | integrations/construct3/wyrdforge/ |
| 11E — MonoGame | complete | integrations/monogame/wyrdforge/ |
| 11F — Defold | complete | integrations/defold/wyrdforge/ |
| 12A — OpenSim/SL | complete | integrations/opensim/wyrdforge/ |
| 12B — Minecraft | complete | integrations/minecraft/wyrdforge/ |
| 12C — Roblox | complete | integrations/roblox/wyrdforge/ |
| 13A — Unity | complete | integrations/unity/wyrdforge/ |
| 13B — Unreal Engine | complete | integrations/unreal/wyrdforge/ |
| 13C — CryEngine | complete | integrations/cryengine/wyrdforge/ |
| 13D — O3DE/Lumberyard | complete | integrations/o3de/wyrdforge/ |
| 14A — Prima Scholar | pending | |
| 14B — WYRD TUI Editor | pending | |
| 14C — WYRD Cloud Relay | pending | |
| 14D — Docs site | pending | |
