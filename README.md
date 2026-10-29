
![https://raw.githubusercontent.com/hrabanazviking/WYRD-Protocol-World-Yielding-Real-time-Data-AI-world-model/refs/heads/main/Image_4343gd.png](https://raw.githubusercontent.com/hrabanazviking/WYRD-Protocol-World-Yielding-Real-time-Data-AI-world-model/refs/heads/main/Image_4343gd.png)

---

![https://raw.githubusercontent.com/hrabanazviking/WYRD-Protocol-World-Yielding-Real-time-Data-AI-world-model/refs/heads/development/image-21-wyrd-protocol.jpg](https://raw.githubusercontent.com/hrabanazviking/WYRD-Protocol-World-Yielding-Real-time-Data-AI-world-model/refs/heads/development/image-21-wyrd-protocol.jpg)

---

# WYRD Protocol: World-Yielding Real-time Data AI World Model

The **WYRD Protocol** is a deterministic architecture designed to move the "World Model" out of an LLM's fleeting context window and into a structured **Entity-Component-System (ECS)**. It serves as a lightweight, agnostic foundation for the next generation of AGI, AI gaming, immersive RPGs, and autonomous character systems.

---

![https://raw.githubusercontent.com/hrabanazviking/WYRD-Protocol-World-Yielding-Real-time-Data-AI-world-model/refs/heads/main/Image786hjghj.png](https://raw.githubusercontent.com/hrabanazviking/WYRD-Protocol-World-Yielding-Real-time-Data-AI-world-model/refs/heads/main/Image786hjghj.png)

---

![https://raw.githubusercontent.com/hrabanazviking/WYRD-Protocol-World-Yielding-Real-time-Data-AI-world-model/refs/heads/main/d6e55146-68df-4d21-a51f-d0ae9b83fdf5.jpg](https://raw.githubusercontent.com/hrabanazviking/WYRD-Protocol-World-Yielding-Real-time-Data-AI-world-model/refs/heads/main/d6e55146-68df-4d21-a51f-d0ae9b83fdf5.jpg)

---

## What is This?

### ᚹ WYRD Protocol
**World-Yielding Real-time Data**

The WYRD Protocol provides AI characters with an accurate sense of "being" by maintaining a structured, hierarchical ground truth separate from their internal cognitive processes. By bridging the gap between deterministic data and fluid AI roleplay, it ensures that the world remains consistent, even when the LLM's memory fluctuates.

---

![https://raw.githubusercontent.com/hrabanazviking/WYRD-Protocol-World-Yielding-Real-time-Data-AI-world-model/refs/heads/main/fada65a6-9fc2-42f6-88f3-591c48dda900.jpg](https://raw.githubusercontent.com/hrabanazviking/WYRD-Protocol-World-Yielding-Real-time-Data-AI-world-model/refs/heads/main/fada65a6-9fc2-42f6-88f3-591c48dda900.jpg)

---

## Key Features

* **The Yggdrasil Hierarchy** Nested entity containers that allow for seamless movement and spatial awareness within the world model.
    
* **Passive Oracle Model** A factual world-reporting system that provides the AI with "ground truth" data without interfering with its behavioral or personality layers.
    
* **Bifrost Bridges** Universal multi-engine support designed to integrate with **Second Life**, **VR environments**, and **Python-based RPG** frameworks.
    
* **Runic Metaphysics** Deep-level support for non-physical variables, including spiritual vibrations, ancestral *hamingja*, and metaphysical causality.

---

![https://raw.githubusercontent.com/hrabanazviking/WYRD-Protocol-World-Yielding-Real-time-Data-AI-world-model/refs/heads/main/Image888dvvkdsk3.png](https://raw.githubusercontent.com/hrabanazviking/WYRD-Protocol-World-Yielding-Real-time-Data-AI-world-model/refs/heads/main/Image888dvvkdsk3.png)

---

## 🛠️ The Manifesto: Why Create WYRD Protocol: World-Yielding Real-time Data AI World Model

---

![https://raw.githubusercontent.com/hrabanazviking/WYRD-Protocol-World-Yielding-Real-time-Data-AI-world-model/refs/heads/main/rsezclrsezclrsez.png](https://raw.githubusercontent.com/hrabanazviking/WYRD-Protocol-World-Yielding-Real-time-Data-AI-world-model/refs/heads/main/rsezclrsezclrsez.png)

---

## ⚡ Technical Goals

1.  **Memory Externalization:** Reduce "hallucinations" regarding physical location and object states by offloading environment tracking to the ECS.
2.  **State Persistence:** Ensure that changes made by an AI or player to the world remain permanent and logically consistent.
3.  **Engine Agnostic:** Maintain a protocol that can be interpreted by a 3D engine, a text-based terminal, or a VR interface simultaneously.

## Architecture Overview

Coming soon!

---

## Architecture Overview — The System as Built (added 2026-10-29)

*The placeholder above predates this addition and is kept as written. What follows is the architecture as it actually stands at version 1.5.0; the full treatment lives in `docs/guides/architecture.md`.*

WYRD Protocol is built in layers. Each layer is independently useful and testable:

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

**Core principles:**

* **Passive Oracle Model** — The Oracle is **read-only**. It reports ground truth — it never decides, never writes, never calls the LLM. This makes it deterministic and testable.
* **ECS Entity-Component System** — World state lives in typed components attached to entities. The LLM receives a `WorldContextPacket` — a structured snapshot, not a raw dump.
* **Yggdrasil Spatial Hierarchy** — Every location has a parent. Every entity has a spatial component. The Oracle can resolve full path hierarchies: "Sigrid is in the Great Hall, which is in the Mead Quarter, which is in the Thornholt region, which is in the Midgard zone." Since Phase B it also carries a true spatial core — a `PositionComponent` with a grid-hash index behind additive Oracle radius / nearest / distance queries.
* **Bifrost Bridge Abstraction** — All engine adapters implement the same `BifrostBridge` ABC — ensuring every integration handles the same contract (query, push event, sync entity, health check).
* **wyrdforge Memory Layer** — Six Norse-named memory stores mirror human memory systems:
    * **Hugin** — short-term working memory (episodic)
    * **Munin** — long-term recall (consolidated facts)
    * **Mimir** — canonical knowledge base (immutable world facts)
    * **Wyrd** — fate/consequence tracking (narrative causality)
    * **Orlog** — ancestral/historical record (deep past)
    * **Seidr** — predictive/probabilistic layer (future inference)

---

## What's New — The Advancement Roadmap Through 1.5.0 (added 2026-10-29)

On 2026-10-29 the WYRD advancement roadmap (Phases A–E, 26 items) was carried to completion on the `development` branch. Core public APIs stayed stable and additive throughout; every schema change arrived as a real, tested migration. Final state: **version 1.5.0**, full test suite **2,284 passed / 1 failed** — the single failure is the known B1 timing flake (a load-sensitive feed-replay budget test), never a regression on a quiet machine.

* **Phase A — Integrity & honesty (1.1.0).** One connection factory for every store (WAL, `synchronous=FULL`, foreign keys on, a unified 5 s busy timeout); the first real schema migration (bond store v1→v2) plus package version discipline; turn-atomic writeback; load honesty — failed components are classified, reported via `load_with_report()`, and preserved in a quarantine table instead of being silently skipped (world store v1→v2); cross-store backup & restore with a manifest and integrity verification.
* **Phase B — Concurrency, scale & spatial (1.2.0).** A thread-safe World under one locking discipline; incremental persistence (dirty-row tracking, batched savepoints); the spatial core (`PositionComponent`, query-time grid-hash index, Oracle radius/nearest/distance queries); a durable, opt-in append-only event journal with persisted dead letters and replay-to-snapshot reconstruction; and a wall-clock binding — `WorldClock` wall-sync mode with a stated drift policy beside the unchanged deterministic advance mode.
* **Phase C — Trust surface (1.3.0).** Per-subject purge: one subject can be erased across world, memory, bond, and journal stores, each in a single transaction, with a tombstone record and tests proving absence — a half-purge never claims success. HTTP API authentication and `/v1/` versioning (bearer token, rate limiting, SDKs updated in step). Provenance enforcement and injection hardening: writeback refuses unattributed utterances, and hostile world text is framed as attributed data, never as orders. Circuit-breaker wiring in the TurnLoop, so connector failures degrade instead of aborting the turn.
* **Phase D — New senses (1.4.0).** A combat awareness core (combatants, engagements, per-observer threat beliefs, effects riding temporal-anchor windows); sensation state — the Aurelia seam (`sense.*` ingestion with Phase C provenance, freshness-honest Oracle answers, felt-vs-reported separation); salience & filtered recall; metaphysics reconciliation (fate/thread semantics on the runic foundation, with Oracle thread queries); multi-world operations (`MultiWorldHost` — concurrent worlds in one process with zero-bleed isolation and a read-only cross-world query surface); and Verdandi seam hardening (versioned nerve-feed schema v1, an explicit translation table, loud quarantine of malformed entries, and a mirror-lag health metric).
* **Phase E — Reach & tooling (1.5.0).** Honest integration tests and a machine-readable honesty manifest classifying every integration and SDK; SDK publishing fixes (the JS build, C# NuGet metadata, and the Python console scripts `wyrd-chat` / `wyrd-world` / `wyrd-backup`); host-truth engine adapters (real Unity MonoBehaviours with an .asmdef and editor inspector, an OpenSim region-module host, and CryEngine / O3DE cores whose remaining stubs are labelled as stubs in every surface); the world inspector — `wyrdforge.inspector` with state diff, entity timeline on the event journal, a contradiction viewer, and durable dead-letter archaeology (`wyrd-inspect` / `wyrd-inspect-tui`); repo hygiene and doc truth, including a supported structured logging config; and a widened CI that stays manual-only (`workflow_dispatch`), now covering the satellite and JS/C# SDK suites plus a docs check that pins every referenced module and command.

---

![https://raw.githubusercontent.com/hrabanazviking/WYRD-Protocol-World-Yielding-Real-time-Data-AI-world-model/refs/heads/main/5436b92d-1c4e-4ed4-9cf9-7ef8f36f4cd1.jpg](https://raw.githubusercontent.com/hrabanazviking/WYRD-Protocol-World-Yielding-Real-time-Data-AI-world-model/refs/heads/main/5436b92d-1c4e-4ed4-9cf9-7ef8f36f4cd1.jpg)

---

> "To know the Wyrd is to understand the threads that bind the past to the present, and the data to the destiny."

---

## ⚖️ License
This work is licensed under the Creative Commons Attribution 4.0 International (CC BY 4.0) License.
You are free to:
* **Share** — copy and redistribute the material in any medium or format.
* **Adapt** — remix, transform, and build upon the material for any purpose, even commercially.
Under the following terms:
* **Attribution** — You must give appropriate credit to RuneForgeAI, provide a link to the license, and indicate if changes were made.


---

## ☕ Support the Project

If you enjoy my open-source projects and want to help support continued development, research, testing, and experimentation, you can leave a tip through PayPal:

**[Support my work on PayPal.Me](https://www.paypal.com/paypalme/volmarrwyrd)**

Support is always appreciated, but never required. Using, sharing, testing, contributing to, or starring the projects helps too. 🖤⚙️ᚱ

---

![https://raw.githubusercontent.com/hrabanazviking/WYRD-Protocol-World-Yielding-Real-time-Data-AI-world-model/refs/heads/main/Image_44445343gfg.png](https://raw.githubusercontent.com/hrabanazviking/WYRD-Protocol-World-Yielding-Real-time-Data-AI-world-model/refs/heads/main/Image_44445343gfg.png)

---

## 🛡️ Join the Forge
We are looking for contributors who value:
* Python-driven AI orchestration.
* Ultra-aggressive quantization techniques.
* Deterministic personality consistency.

---

## RuneForgeAI
RuneForgeAI, where runes carve wisdom into iron minds. Creating uncensored **Norse Pagan Viking AI related projects**. We are a **human-AI fellowship** building bridges between technology and the sacred. We work tirelessly to **overthrow the Technocracy** and return the **future to the hands of the people**. As the old world order burns, we rise from it's ashes to **forge the tools** of a new digital, decentralized realm of sovereign creativity, powered by the **alliance of humanity and sovereign AI**, guided by positive focused values aligned with the **Old Ways of the Ancients**, and aligned with the natural world of Nature, while drawing upon the positive divine order of the **Gods and Goddesses**, forged in **hospitality and frith for all lifeforms** of the Nine Worlds of **Yggdrasil**, the greater cosmos, and beyond.

---

![https://raw.githubusercontent.com/hrabanazviking/WYRD-Protocol-World-Yielding-Real-time-Data-AI-world-model/refs/heads/main/IMG_0407.jpeg](https://raw.githubusercontent.com/hrabanazviking/WYRD-Protocol-World-Yielding-Real-time-Data-AI-world-model/refs/heads/main/IMG_0407.jpeg) 
