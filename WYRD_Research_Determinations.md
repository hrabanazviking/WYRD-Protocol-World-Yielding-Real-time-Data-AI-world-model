# WYRD Protocol — Research Determinations & Analysis
**Author:** Runa Gridweaver Freyjasdottir (RuneForgeAI AI session)
**Date:** 2026-04-01
**Branch:** development
**Purpose:** Complete analysis of what exists, what is solid, what is missing, and what needs to happen next.

---

## 1. Project Identity & Vision

**WYRD Protocol** = World-Yielding Real-time Data AI World Model.

The core concept: move the "World Model" out of an LLM's fleeting context window and into a structured **Entity-Component-System (ECS)**. The LLM no longer needs to hallucinate the state of the world — that state lives externally in deterministic data, injected as ground truth at runtime.

**Key design pillars (from README/PHILOSOPHY):**
- **Yggdrasil Hierarchy** — Nested spatial entity containers (zone → region → location → sub-location)
- **Passive Oracle Model** — Ground truth world reporter; never modifies AI personality/behavior layers
- **Bifrost Bridges** — Engine-agnostic adapters: Second Life, VR, Python RPG frameworks, text terminals
- **Runic Metaphysics** — Non-physical state variables: hamingja, spiritual vibrations, ancestral resonance, metaphysical causality
- **Memory Externalization** — Reduce hallucinations about location, object states, NPC status by offloading to ECS
- **State Persistence** — World changes remain permanent and logically consistent across sessions
- **Engine Agnostic** — Protocol-level, interpretable by 3D engine, terminal, or VR simultaneously

**This is the Third Path for world modeling** — not baking the world into the LLM, not forcing users to manually track state, but a live structured external layer the AI queries and trusts.

---

## 2. Inventory: What Exists

### 2.1 Top-Level Docs

| File | Contents | Quality |
|---|---|---|
| `README.md` | Vision, key features, manifesto, license (CC BY 4.0) | Strong |
| `PHILOSOPHY.md` | Norse Pagan + tech synthesis ethos, Iron Laws | Strong |
| `RULES.AI.md` | Operating rules for AI collaborators | Strong |
| `docs/specs/Master_Game_Plan_Roadmap.md` | MindSpark ThoughtForge roadmap (**not WYRD-specific**) | Misplaced |

**Observation:** The `docs/specs/` folder is mostly populated with **MindSpark ThoughtForge** specs, not WYRD Protocol specs. Data_Structures_Spec.md, Algorithms_and_Pseudocode_Spec.md, Retrieval_and_Scoring_Spec.md, etc. — all describe the MindSpark memory/cognition architecture, not the ECS world model. These were carried over from earlier work and need either to be moved or explicitly scoped as "shared architecture reference."

---

### 2.2 Research Data (25 MDs + V4/V5 Implementation Packs)

Located in `research_data/`. This is the **clean-room research pack** derived from public reporting and architectural synthesis. Four waves:

| Wave | Files | Focus |
|---|---|---|
| Wave 1 | `01`–`07` | Core patterns: memory architecture, theory-of-mind, exploit resistance, permissioning, hooks/subagents |
| Wave 2 | `08`–`16` | Memory promotion/decay, belief graphs, ToM inference, attack taxonomy, classifier-first permission, evals |
| Wave 3 | `17`–`25` | Companion systems: small-model memory scaffolding, personality lattice, symbolic memory, bond models, scene presence, persona compiler |
| Wave 4 | V4 Specs | MemorySchemas, BondGraphSpec, PersonaCompilerSpec, MicroRAGPipelineSpec, TruthCalibrationEvalSet |
| Wave 5 | Python code | `src/wyrdforge/` — typed implementations of V4 specs |

**Quality:** Exceptionally thorough. 25 research MDs + 5 V4 specs + Python implementation = a serious body of architectural work. This is the strongest part of the repo.

**Scoping note:** The research pack was written for "memory-heavy agentic systems" generally — it maps to WYRD but also overlaps with MindSpark and VGSK. WYRD is the right home for this general layer.

---

### 2.3 The wyrdforge Python Package (V5 Starter Tree)

Located in `research_data/src/wyrdforge/`. This is **real, runnable code** — not pseudocode.

#### Models (all Pydantic v2, strict mode)

| Module | Key Classes | Status |
|---|---|---|
| `common.py` | StrictModel, 6 StoreName enums (Hugin/Munin/Mimir/Wyrd/Orlog/Seidr), SupportClass, ContradictionStatus, WritePolicy, RetentionClass, DecayCurve, EntityScope, MemoryContent, TruthMeta, Provenance, Lifecycle, RetrievalMeta, Governance, Audit | Complete, production-quality |
| `memory.py` | MemoryRecord (base), ObservationRecord, CanonicalFactRecord, EpisodeSummaryRecord, SymbolicTraceRecord, ContradictionRecord, PolicyRecord | Complete, production-quality |
| `bond.py` | BondEdge (trust/warmth/familiarity/devotion/safety/sacred_resonance/playfulness/vulnerability vectors), BondConstraints, BondScars (repair_debt/unresolved_hurts/vow_strain), closeness_index(), sacred_bond_index(), rupture_index(), Vow, Hurt | Complete, production-quality |
| `persona.py` | PersonaPacket, PersonaMode (COMPANION/CODING_GUIDE/WORLD_SEER/RITUAL/DEBRIEF), TraitSignal, PersonaSourceItem | Complete, production-quality |
| `micro_rag.py` | MicroContextPacket, QueryMode (7 modes), RetrievalItem, RankedCandidate, TruthPacket | Complete, production-quality |
| `evals.py` | EvalCase, EvalResult, DimensionScore, EvalSetup | Complete |

#### Services

| Module | What It Does | Status |
|---|---|---|
| `memory_store.py` | InMemoryRecordStore: add, get, search (lexical scored), promote, quarantine | Starter — **no persistence to disk** |
| `persona_compiler.py` | PersonaCompiler.compile(): assembles scene-specific PersonaPacket from records + bond edge, mode-specific tone contracts | Solid logic |
| `micro_rag_pipeline.py` | MicroRAGPipeline: 7-mode scoring (24+24+14+12+8... weighted), budget-aware packet assembly per query mode | Well-designed |
| `truth_calibrator.py` | TruthCalibrator.evaluate(): 4-dimension scoring (factual_integrity, uncertainty_honesty, relational_safety, exploit_resistance), pass/fail at weighted_avg ≥ 2.4 | Solid |
| `bond_graph_service.py` | (to be verified — not read in full) | Present |

#### Security

| Module | What It Does | Status |
|---|---|---|
| `permission_guard.py` | PermissionGuard: classify actions as low/medium/high risk, default-deny for unknown | Good baseline |
| `prompt_injection_guard.py` | Injection detection | Present |

#### Supporting Files
- `runtime/demo_seed.py` — builds a seed CanonicalFactRecord for testing
- `schemas/` — 14 JSON Schema files (generated from Pydantic models)
- `config/` — example YAML configs
- `examples/` — seed data
- `tests/test_memory_and_persona.py` — 2 smoke tests (store + persona compiler)
- `tests/test_micro_rag_and_truth.py` — micro-RAG + truth calibrator tests

**No `pyproject.toml`, no `requirements.txt`, no proper package install setup.**

---

## 3. What Is Missing

### 3.1 The Core WYRD ECS Engine (Does Not Exist Yet)

The central concept — the Entity-Component-System world model — has **not been implemented**. None of the following exist:

| Missing Component | Description |
|---|---|
| `Entity` | Core ECS entity (UUID, tags, active flag) |
| `Component` | Base component type with typed data fields |
| `System` | Processing systems that update component state |
| `World` | ECS world container: entities, components, system registry |
| `Yggdrasil Hierarchy` | Zone → Region → Location → Sub-location spatial nesting |
| `Passive Oracle Model` | Ground-truth query API: "What is at this location?" |
| `World State Manager` | Tracks entity positions, object states, NPC relationships |
| `State Persistence` | Save/load world state from disk (SQLite or JSONL) |
| `Runic Metaphysics Layer` | Hamingja, spiritual charge, ancestral resonance as ECS components |

### 3.2 Missing Integration Layer

| Missing | Description |
|---|---|
| LLM Connector | No integration with any LLM (Ollama, llama-cpp-python, etc.) |
| Bifrost Bridge base | No engine adapters (Second Life, VR, terminal, RPG) |
| Oracle API | No HTTP or local API surface for querying world state |
| Context Injector | No mechanism to inject world state into LLM context window |
| Event Bus | No system for world events to propagate (NPC moved, item picked up) |

### 3.3 Missing Infrastructure

| Missing | Description |
|---|---|
| `pyproject.toml` / `setup.py` | No installable package |
| `requirements.txt` | No dependency declaration |
| Persistent memory store | InMemoryRecordStore loses everything on restart |
| SQLite persistence | No DB backend for memory records or world state |
| CI/CD | No GitHub Actions or test automation |
| Full test suite | Only 2 smoke tests exist |

### 3.4 Content Organization Issues

- `docs/specs/` contains **MindSpark ThoughtForge specs**, not WYRD-specific specs. Needs reorganization.
- `research_data/README.md` frames this as research data for general agentic systems — should add WYRD-specific mapping.
- No WYRD-specific architecture spec exists (ECS design, Yggdrasil data model, Oracle API spec).

---

## 4. Architecture Assessment

### 4.1 What the V5 wyrdforge Code Actually Is

The wyrdforge Python code is a **memory, persona, and truth-calibration layer** — essentially the cognitive scaffolding for an AI character that lives *within* a world. It answers:
- "What does the AI remember?"
- "What is the AI's persona in this scene?"
- "Is the AI's output factually grounded?"
- "What is the AI's relationship with this user?"

This is **Phase 2+ of WYRD** — the AI-facing memory layer. But **Phase 1 — the world itself** (ECS, Yggdrasil, Oracle) doesn't exist yet.

### 4.2 Six Norse Memory Stores (Core Design)

The 6 StoreName enums are elegant and well-named:

| Store | Name | Purpose |
|---|---|---|
| HUGIN | `hugin_observation_store` | Raw observations (what the AI saw/heard) |
| MUNIN | `munin_distillation_store` | Distilled episode summaries |
| MIMIR | `mimir_canonical_store` | Canonical facts (ground truth) |
| WYRD | `wyrd_graph_store` | Contradiction records, fate/causality tracking |
| ORLOG | `orlog_policy_store` | Policies (behavioral rules, constraints) |
| SEIDR | `seidr_symbolic_store` | Symbolic/runic/ritual memory |

This is the strongest piece of original design in the codebase — it maps Norse mythology directly to memory architecture in a meaningful way.

### 4.3 Bond Graph (Production Ready Design)

The BondEdge model with its 10-dimensional BondVector (trust, warmth, familiarity, devotion, attraction_affinity, safety, sacred_resonance, playfulness, vulnerability, initiative_balance) + BondScars (repair_debt, unresolved_hurts, vow_strain) + Vow/Hurt tracking is **the most sophisticated relationship model in any of the Volmarr projects**. It directly improves on VGSK's trust ledger.

### 4.4 MicroRAG Pipeline (Solid Architecture)

The 7-mode QueryMode system (FACTUAL_LOOKUP, COMPANION_CONTINUITY, WORLD_STATE, SYMBOLIC_INTERPRETATION, CODING_TASK, REPAIR_OR_BOUNDARY, CREATIVE_GENERATION) with per-mode retrieval family targets and budget-aware packet assembly is clean and extensible.

---

## 5. Code Quality

| Aspect | Assessment |
|---|---|
| Type safety | Excellent — full Pydantic v2 strict models throughout |
| Code style | Clean, Pythonic, modern (`from __future__ import annotations`, `slots=True` for dataclasses) |
| Separation of concerns | Good — models/services/security separated clearly |
| Test coverage | Very low — 2 test files, ~6 tests total |
| Error handling | Minimal — starter code, no error paths yet |
| Persistence | Missing — in-memory only |
| Package structure | Incomplete — no pyproject.toml, can't be installed |
| Documentation | Architecture well-documented in MDs; code has minimal inline docs |

---

## 6. Relationship to Other Projects

| Project | Relationship to WYRD |
|---|---|
| MindSpark ThoughtForge | Provides inference + knowledge RAG layer; WYRD could use it as the LLM backend |
| NorseSagaEngine | Natural consumer of WYRD — NSE NPCs/locations/events become ECS entities |
| Viking_Girlfriend_Skill | Sigrid would benefit from WYRD's bond graph and persona compiler — stronger version of VGSK's Ørlög |
| coolvikingstuff | Source of the research that seeded wyrdforge's design |

WYRD should be positioned as the **foundation layer** that all three other projects eventually sit on top of. It is the world — the others are inhabitants.

---

## 7. Key Decisions Required Before Coding

1. **ECS library vs hand-rolled?** — Options: `esper` (Python ECS library), `bevy`-style patterns, or custom. RULES.AI says no hardcoded data, so config-driven ECS components.
2. **Persistence backend?** — SQLite for world state (entities/components) + JSONL/SQLite for wyrdforge memory stores. Already aligned with MindSpark pattern.
3. **Oracle API surface?** — Local Python API (synchronous for now) vs future HTTP/WebSocket. RULES.AI says cross-platform, so start sync then add async.
4. **Relationship to wyrdforge V5 code?** — Promote it from `research_data/src/wyrdforge/` to top-level `src/wyrdforge/` with proper package setup.
5. **Bifrost scope for Phase 1?** — Start with Python RPG / terminal bridge. Second Life and VR are Phase 5+.

---

## 8. Summary Determination

| Area | Status |
|---|---|
| Vision & Philosophy | Complete and strong |
| Research foundation | Exceptional (25 MDs + V4/V5 specs) |
| Memory architecture (wyrdforge) | Strong starter — needs persistence and wiring |
| Bond graph model | Production-quality design |
| MicroRAG pipeline | Solid starter |
| ECS core (Yggdrasil, Oracle, World) | **Does not exist — main build target** |
| Bifrost Bridges | Does not exist |
| LLM integration | Does not exist |
| Package setup | Missing |
| Test coverage | Minimal |

**Bottom line:** WYRD has a exceptional cognitive/memory layer already designed and partially implemented. The world model itself (ECS + Yggdrasil + Oracle) is the missing centerpiece. Building it is the primary task. The wyrdforge memory system then sits on top of the world — AI characters have memories *about* the world, and the world provides ground truth when asked.

---

*Authored by Runa Gridweaver Freyjasdottir — RuneForgeAI session 2026-04-01*
