# Architecture

WYRD Protocol is built in layers. Each layer is independently useful and testable.

```
┌─────────────────────────────────────────────────────────────┐
│                    Your Game / AI Platform                   │
│          (Unity, Unreal, Foundry VTT, SillyTavern, …)       │
└────────────────────────┬────────────────────────────────────┘
                         │  HTTP JSON  (or in-process Python)
┌────────────────────────▼────────────────────────────────────┐
│                   Bifrost Bridge Layer                       │
│  SDK: wyrdforge-js · WyrdForge.Client · GDScript addon       │
│  Engine bridges: Unity · Unreal · Godot · Roblox · …        │
│  AI bridges:  SillyTavern · Voxta · Kindroid · Hermes · …   │
└────────────────────────┬────────────────────────────────────┘
                         │
┌────────────────────────▼────────────────────────────────────┐
│                  WyrdHTTPServer  (:8765)                     │
│   POST /query   POST /event   GET /world   GET /facts        │
└────────────────────────┬────────────────────────────────────┘
                         │
┌────────────────────────▼────────────────────────────────────┐
│                    Passive Oracle                            │
│  who_is_here · where_is · what_is · get_facts · …           │
│  (read-only — never writes, never hallucinates)              │
└────────────────────────┬────────────────────────────────────┘
                         │
┌───────────────┬─────────▼──────────┬───────────────────────┐
│  World (ECS)  │  Yggdrasil (Spatial) │  PersistentMemoryStore│
│  Entities     │  Zone→Region→Loc    │  SQLite + FTS5        │
│  Components   │  Path resolution    │  MemoryPromoter       │
│  Systems      │  Presence tracking  │  ContradictionDetector│
└───────────────┴────────────────────┴───────────────────────┘
```

## Core Principles

### Passive Oracle Model
The Oracle is **read-only**. It reports ground truth — it never decides, never writes,
never calls the LLM. This makes it deterministic and testable.

### ECS Entity-Component System
World state lives in typed components attached to entities. The LLM receives a
`WorldContextPacket` — a structured snapshot, not a raw dump.

### Yggdrasil Spatial Hierarchy
Every location has a parent. Every entity has a spatial component. The Oracle can
resolve full path hierarchies: "Sigrid is in the Great Hall, which is in the Mead Quarter,
which is in the Thornholt region, which is in the Midgard zone."

### Bifrost Bridge Abstraction
All engine adapters implement the same `BifrostBridge` ABC — ensuring every integration
handles the same contract (query, push event, sync entity, health check).

### wyrdforge Memory Layer
Six Norse-named memory stores mirror human memory systems:
- **Hugin** — short-term working memory (episodic)
- **Munin** — long-term recall (consolidated facts)
- **Mimir** — canonical knowledge base (immutable world facts)
- **Wyrd** — fate/consequence tracking (narrative causality)
- **Orlog** — ancestral/historical record (deep past)
- **Seidr** — predictive/probabilistic layer (future inference)
