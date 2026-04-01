# WYRD Protocol — Complete Phased Implementation Plan
**Author:** Runa Gridweaver Freyjasdottir (RuneForgeAI AI session)
**Date:** 2026-04-01
**Version:** 1.0
**Branch:** development
**Based on:** WYRD_Research_Determinations.md + all research_data/ specs + RULES.AI.md + PHILOSOPHY.md

---

## Overview

WYRD Protocol is built in 7 phases. Each phase is independently deliverable and testable. Each phase builds on the last. The order follows the iron logic of dependency — you cannot have AI characters in a world that doesn't exist yet.

```
Phase 0: Foundation & Package Setup
Phase 1: ECS Core Engine (Yggdrasil + World)
Phase 2: Persistent Memory Layer (wyrdforge promoted + disk storage)
Phase 3: Passive Oracle Model (world query API)
Phase 4: LLM Integration & Context Injection
Phase 5: Bond Graph, Persona Compiler & MicroRAG wired end-to-end
Phase 6: Bifrost Bridges & Multi-Engine Support
Phase 7: Runic Metaphysics, Evals, Production Hardening
```

Total scope: approx. 20–28 weeks of active development.

---

## Phase 0: Foundation & Package Setup (Week 1)

**Goal:** Turn the repo from a research-heavy directory into a proper installable Python project with clean structure.

### 0.1 Repo Reorganization
- Create top-level `/src/wyrdforge/` (promote from `research_data/src/wyrdforge/`)
- Create `/tests/` at root level (promote from `research_data/tests/`)
- Create `/docs/specs/wyrd/` — move all WYRD-specific specs here
- Create `/docs/specs/shared/` — move MindSpark data structure specs here (clearly labelled as shared architecture reference)
- Create `/configs/`, `/examples/`, `/scripts/`
- Add `.gitignore`, `pyproject.toml`, `requirements.txt`, `CONTRIBUTING.md`

### 0.2 Package Setup
```toml
# pyproject.toml
[build-system]
requires = ["setuptools>=68", "wheel"]
build-backend = "setuptools.backends.legacy:build"

[project]
name = "wyrdforge"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = [
    "pydantic>=2.0",
    "sqlalchemy>=2.0",
    "sentence-transformers",
    "pyyaml",
    "click",
]

[project.optional-dependencies]
dev = ["pytest", "pytest-asyncio", "ruff", "mypy"]
```

### 0.3 CI Bootstrap
- GitHub Actions: `ruff` lint + `mypy` type check + `pytest` on push to development
- Branch strategy: `main` (releases), `development` (active), feature branches

### 0.4 JSON Schema Regeneration
- Move `scripts/generate_json_schemas.py` to top-level `/scripts/`
- Verify all 14 JSON schemas regenerate cleanly from promoted models

### 0.5 Deliverables
- `pip install -e .` works
- `pytest tests/` passes (existing 6 smoke tests)
- Ruff + mypy pass with zero errors
- Clean repo structure committed and pushed

---

## Phase 1: ECS Core Engine — Yggdrasil & World (Weeks 2–5)

**Goal:** Build the central missing piece — the deterministic ECS world model that the AI queries instead of hallucinating.

### 1.1 ECS Core Data Model

**`src/wyrdforge/ecs/entity.py`**
```python
# Entity: a UUID + a set of component types
@dataclass
class Entity:
    entity_id: str          # UUID
    tags: set[str]          # semantic labels ("npc", "location", "item", "player")
    active: bool = True
    created_at: datetime
    updated_at: datetime
```

**`src/wyrdforge/ecs/component.py`**
```python
# Component: a typed data blob attached to an Entity
class Component(StrictModel):
    component_type: str
    entity_id: str
    schema_version: str = "1.0"
    created_at: datetime
    updated_at: datetime
    # subclasses add typed fields
```

**`src/wyrdforge/ecs/world.py`**
```python
# World: the ECS container
class World:
    def create_entity(tags: set[str]) -> Entity
    def add_component(entity_id: str, component: Component) -> None
    def get_component(entity_id: str, component_type: str) -> Component | None
    def get_all_components(entity_id: str) -> list[Component]
    def query_entities_by_tag(tag: str) -> list[Entity]
    def query_entities_with_component(component_type: str) -> list[Entity]
    def remove_entity(entity_id: str) -> None
    def destroy_component(entity_id: str, component_type: str) -> None
```

**`src/wyrdforge/ecs/system.py`**
```python
# System: processes entities with specific components each tick
class System(ABC):
    @abstractmethod
    def tick(self, world: World, delta_t: float) -> None: ...
    component_interests: list[str]  # which component types this system reads/writes
```

### 1.2 Yggdrasil Hierarchy

The world organizes spatially as a tree:

```
World
└── Zone (e.g., "Midgard", "The Nine Realms")
    └── Region (e.g., "Fjordlands", "Iron Forest")
        └── Location (e.g., "Thornholt Mead Hall")
            └── Sub-location (e.g., "The Great Fire Pit", "The Sleeping Alcove")
```

**`src/wyrdforge/ecs/components/spatial.py`**
- `SpatialComponent` — position in the hierarchy: `zone_id`, `region_id`, `location_id`, `sublocation_id`
- `ContainerComponent` — marks an entity as a spatial container with `children: list[str]` (entity_ids)
- `YggdrasilNode` — wraps an entity as a named node in the spatial tree

**`src/wyrdforge/ecs/yggdrasil.py`**
- `YggdrasilTree` — manages the spatial hierarchy
- Methods: `add_node()`, `move_entity()`, `get_location()`, `get_children()`, `get_ancestors()`, `find_by_name()`
- Constraint enforcement: entities cannot be in two locations simultaneously

### 1.3 Core Component Types (First Wave)

**Identity:**
- `NameComponent` — `name: str`, `aliases: list[str]`, `known_to: list[str]`
- `DescriptionComponent` — `short_desc: str`, `long_desc: str`, `tags: list[str]`
- `StatusComponent` — `state: str`, `flags: dict[str, bool]`

**Physical:**
- `SpatialComponent` — location in Yggdrasil hierarchy
- `PhysicalComponent` — `weight: float`, `size: str`, `tangible: bool`
- `InventoryComponent` — `contains: list[str]` (entity_ids of held items)

**NPC/Character:**
- `PersonaRefComponent` — `persona_id: str`, `bond_ids: list[str]`  (links to wyrdforge memory layer)
- `HealthComponent` — `hp: float`, `max_hp: float`, `alive: bool`
- `FactionComponent` — `faction_id: str`, `reputation: dict[str, float]`

**World State:**
- `LockStateComponent` — `locked: bool`, `key_entity_id: str | None`
- `OwnershipComponent` — `owner_entity_id: str | None`, `claimable: bool`
- `TemporalComponent` — `active_during: list[str]` (time-of-day/season tags)

### 1.4 World Systems (First Wave)

- `PresenceSystem` — tracks which entities are co-located
- `InventorySystem` — validates item ownership and location consistency
- `StateTransitionSystem` — processes entity state changes (doors opening, NPCs moving)
- `TickSystem` — game loop driver, calls all systems in order

### 1.5 World Configuration Loader

Per RULES.AI — no hardcoded world data. World definition loaded from files:
```yaml
# configs/worlds/thornholt.yaml
world_id: "thornholt_mead_hall"
zones:
  - id: "midgard_fjordlands"
    regions:
      - id: "thornholt_vale"
        locations:
          - id: "thornholt_hall"
            name: "Thornholt Mead Hall"
            description: "A great timber longhouse..."
            sublocations:
              - id: "great_fire_pit"
              - id: "high_seat"
```

### 1.6 Persistence: SQLite Backend

**`src/wyrdforge/persistence/world_store.py`**
- SQLite via SQLAlchemy
- Tables: `entities`, `components`, `spatial_tree`, `world_events`
- `WorldStore.save(world: World)` — serialize all entities + components
- `WorldStore.load(world_id: str) -> World` — restore full world state
- Supports WAL mode for concurrency

### 1.7 Milestone
- `wyrd_world_cli.py` — CLI that loads a YAML world config, displays the Yggdrasil tree, and allows placing/moving entities
- Full test suite for ECS operations, Yggdrasil hierarchy, SQLite round-trip
- 60+ tests

---

## Phase 2: Persistent Memory Layer (Weeks 6–8)

**Goal:** Graduate the wyrdforge V5 code from in-memory to fully persistent. Add disk storage for all 6 memory stores.

### 2.1 Persistent Memory Store

Replace `InMemoryRecordStore` with `PersistentMemoryStore`:

**`src/wyrdforge/persistence/memory_store.py`**
- SQLite backend (separate DB from world store)
- One table per StoreName (or partitioned single table with store discriminator)
- Full-text search via FTS5 for lexical retrieval
- sqlite-vss (or similar) for vector embeddings if available
- Write policies enforced at DB level: EPHEMERAL → auto-expire, IMMUTABLE → no UPDATE

**Store Layout:**
```sql
CREATE TABLE memory_records (
    record_id TEXT PRIMARY KEY,
    store TEXT NOT NULL,
    record_type TEXT NOT NULL,
    tenant_id TEXT NOT NULL,
    system_id TEXT NOT NULL,
    content_json TEXT NOT NULL,
    truth_json TEXT NOT NULL,
    lifecycle_json TEXT NOT NULL,
    retrieval_json TEXT NOT NULL,
    governance_json TEXT NOT NULL,
    audit_json TEXT NOT NULL,
    embedding BLOB,
    created_at TEXT NOT NULL,
    expires_at TEXT
);
CREATE VIRTUAL TABLE memory_fts USING fts5(record_id, title, summary, lexical_terms);
```

### 2.2 Memory Promotion Engine

Per `08_memory_lifecycle_and_promotion_engine.md`:
- Observation → (scored) → EpisodeSummary → (reviewed) → CanonicalFact
- Promotion rules: confidence ≥ 0.8 + approval_state = PENDING → auto-promote to PROMOTABLE
- Human/system review gate before CANONICAL

**`src/wyrdforge/services/memory_promoter.py`**
- `score_for_promotion(record: MemoryRecord) -> float`
- `promote_if_eligible(record_id: str) -> bool`
- `decay_stale_records(cutoff_days: int) -> int` — set stale records to lower confidence

### 2.3 Contradiction Detection

**`src/wyrdforge/services/contradiction_detector.py`**
- On every new CanonicalFactRecord write: check if `fact_subject_id + fact_key` conflicts with existing approved canonical facts
- If conflict found: create ContradictionRecord in WYRD store, quarantine lower-confidence record
- Reports for human review

### 2.4 Memory Writeback Pipeline

**`src/wyrdforge/services/writeback_engine.py`**
- Reads turn output + raw LLM response
- Extracts candidate facts, observations, policy signals
- Writes to appropriate stores with EPHEMERAL write policy
- Tags for promotion scoring

### 2.5 Deliverables
- All 6 stores persistent across restarts
- Memory promotion with configurable rules
- Contradiction detection working
- JSONL export/import for backup and inspection
- 40+ new tests

---

## Phase 3: Passive Oracle Model (Weeks 9–11)

**Goal:** Build the ground-truth world query API that AI characters use instead of hallucinating.

### 3.1 Oracle Design Principles
- **Read-only** — Oracle never modifies world state
- **Structured queries** — Returns typed data, not prose
- **Compact** — Designed to fit in LLM context budget
- **Honest** — Returns "unknown" when data is missing, never fabricates

### 3.2 Oracle Query Types

**`src/wyrdforge/oracle/queries.py`**

```python
class OracleQueryType(str, Enum):
    WHERE_IS = "where_is"               # Where is entity X?
    WHAT_IS_HERE = "what_is_here"       # What entities are at location Y?
    DESCRIBE = "describe"               # Describe entity X
    INVENTORY = "inventory"             # What does entity X have?
    STATUS = "status"                   # What state is entity X in?
    RELATIONSHIP = "relationship"       # What is the relationship between X and Y?
    HISTORY = "history"                 # What happened to X recently?
    METAPHYSICAL = "metaphysical"       # What is X's hamingja/spiritual charge?
    TIME = "time"                       # What time/season is it in the world?
    AVAILABLE_ACTIONS = "available"     # What can the AI do right now?
```

### 3.3 Oracle Engine

**`src/wyrdforge/oracle/engine.py`**

```python
class OracleEngine:
    def query(self, query_type: OracleQueryType, subject_id: str, **kwargs) -> OracleResponse
    def batch_query(self, queries: list[OracleQuery]) -> list[OracleResponse]
    def context_packet(self, entity_id: str, budget: int = 500) -> str  # pre-formatted for LLM injection
```

**`src/wyrdforge/oracle/response.py`**
- `OracleResponse` — typed structured result
- `confidence: float` — how certain the Oracle is (based on data freshness + completeness)
- `unknown_fields: list[str]` — explicitly lists what is not known
- `world_snapshot_at: datetime` — when the data was captured

### 3.4 Context Packet Builder

Converts Oracle responses into a compact, LLM-ready context block:

```
[WORLD STATE — Oracle Report @ 2026-04-01T14:22:00Z]
You are in: Thornholt Mead Hall > Great Fire Pit
Present entities: Gunnar Ironfist (NPC), 3 unknown travelers, a locked chest
Your inventory: iron dagger, worn cloak, 3 silver pieces
Current time: Late evening, early spring
Spiritual charge: moderate (hamingja 0.62)
Unknown: chest contents, travelers' intentions
```

### 3.5 Oracle Config

Per RULES.AI — no hardcoded data. Oracle format defined in config:
```yaml
# configs/oracle_format.yaml
context_budget_tokens: 500
include_unknown_fields: true
timestamp_format: "iso8601"
spiritual_layer: true
```

### 3.6 Deliverables
- All 9 query types working against a loaded World
- Context packet builder producing LLM-ready strings
- Oracle respects token budget (compact by default)
- 30+ tests including "unknown" cases

---

## Phase 4: LLM Integration & Context Injection (Weeks 12–14)

**Goal:** Wire WYRD to an actual LLM. The Oracle feeds world state into the prompt. Responses feed back into the memory layer.

### 4.1 LLM Connector

**`src/wyrdforge/llm/connector.py`**

Adapter pattern — one interface, multiple backends:
- `OllamaConnector` — local Ollama models (primary target)
- `LlamaCppConnector` — llama-cpp-python (offline/edge)
- `LiteLLMConnector` — fallback router (optional, requires network)

```python
class LLMConnector(ABC):
    @abstractmethod
    def generate(self, system_prompt: str, user_message: str, *, max_tokens: int = 512) -> str: ...
    @abstractmethod
    def health_check(self) -> bool: ...
```

Configuration per RULES.AI (no hardcoded model names):
```yaml
# configs/llm.yaml
backend: ollama
ollama_base_url: "http://localhost:11434"
default_model: "llama3.2:3b"
max_tokens: 512
temperature: 0.7
```

### 4.2 System Prompt Builder

**`src/wyrdforge/prompt/builder.py`**

Assembles the full system prompt from:
1. Persona packet (from PersonaCompiler)
2. Oracle world state context packet
3. Policy rules (from ORLOG store)
4. Tone contract (from PersonaPacket)
5. Response guidance
6. Uncertainty anchors

Named sections with clear separators (per research doc 02 pattern):
```
[IDENTITY]
...persona packet identity core...

[WORLD STATE]
...oracle context packet...

[BEHAVIORAL POLICY]
...orlog rules...

[TONE CONTRACT]
...tone contract items...
```

### 4.3 Turn Loop

**`src/wyrdforge/runtime/turn_loop.py`**

```python
class WyrdTurnLoop:
    def run_turn(self, user_input: str, entity_id: str) -> TurnResult:
        # 1. Query Oracle for world state context
        oracle_packet = self.oracle.context_packet(entity_id)
        
        # 2. Build memory activation bundle (MicroRAG)
        query_mode = self.intent_classifier.classify(user_input)
        context_packet = self.micro_rag.assemble(query=user_input, mode=query_mode, ...)
        
        # 3. Compile persona for this scene
        persona_packet = self.persona_compiler.compile(...)
        
        # 4. Build system prompt
        system_prompt = self.prompt_builder.build(persona_packet, oracle_packet, context_packet)
        
        # 5. Generate response
        response_text = self.llm.generate(system_prompt, user_input)
        
        # 6. Truth calibration
        eval_result = self.truth_calibrator.evaluate(case, response_text)
        
        # 7. Writeback to memory stores
        self.writeback_engine.process(user_input, response_text, eval_result)
        
        return TurnResult(response=response_text, eval=eval_result, oracle=oracle_packet)
```

### 4.4 Intent Classifier

**`src/wyrdforge/cognition/intent_classifier.py`**
- Maps user input → QueryMode (FACTUAL_LOOKUP, COMPANION_CONTINUITY, WORLD_STATE, etc.)
- Starts as keyword-based heuristic (no secondary LLM call needed)
- Optional: small local classifier model for better accuracy

### 4.5 CLI Runtime

**`wyrd_runtime.py`** — interactive REPL:
```
[WYRD Protocol v0.4.0] — World: thornholt_mead_hall | Persona: veyrunn
> Where am I?
[Oracle] You are in Thornholt Mead Hall, Great Fire Pit.

> What is Gunnar doing?
[Gunnar Ironfist] "Aye, stranger. What brings you to Thornholt on such a bitter night?"
```

### 4.6 Deliverables
- Full turn loop working end-to-end with Ollama
- System prompt builder producing well-structured prompts
- Intent classifier routing to correct QueryMode
- Interactive CLI runtime
- 40+ tests

---

## Phase 5: Bond Graph, Persona Compiler & MicroRAG — Full Wiring (Weeks 15–17)

**Goal:** All three V5 systems wired into the turn loop with full persistence and cross-system communication.

### 5.1 Bond Graph Persistence

**`src/wyrdforge/persistence/bond_store.py`**
- Persist BondEdge, Vow, Hurt to SQLite
- `BondStore.get_edge(entity_a, entity_b) -> BondEdge | None`
- `BondStore.record_vow(bond_id, vow: Vow) -> None`
- `BondStore.record_hurt(bond_id, hurt: Hurt) -> None`
- `BondStore.update_vector(bond_id, delta: dict[str, float]) -> None` — incremental vector updates

### 5.2 Bond Graph Service — Full Implementation

**`src/wyrdforge/services/bond_graph_service.py`** (extend existing skeleton)
- `process_interaction(entity_a, entity_b, event_type, magnitude)` → updates BondVector
- Bond evolution rules (loaded from config, not hardcoded):
  - `oath_kept` → trust +0.03, devotion +0.01
  - `contradiction_caught` → trust -0.05
  - `boundary_crossed` → safety -0.10, hurt recorded
- Auto-create bond on first interaction if not exists
- Diminishing returns on repeated signals (per VGSK pattern, already proven)

### 5.3 Persona Compiler — Scene-Aware

Extend `PersonaCompiler` to:
- Accept `scene_id` and `world_context` (from Oracle)
- Adjust `PersonaMode` based on scene type (ritual space → RITUAL mode, coding session → CODING_GUIDE)
- Cap identity_core / truth_anchor_points to stay within token budget
- Bond excerpt injection based on BondEdge closeness_index and sacred_bond_index

### 5.4 MicroRAG — World-Aware

Extend `MicroRAGPipeline` to:
- Query Oracle for world state as a retrieval family ("world_state")
- Include world state items in budget-aware assembly
- WORLD_STATE query mode pulls from Oracle + MIMIR + SEIDR stores

### 5.5 Relationship Continuity

Per research doc 20 patterns:
- Track session gaps (time since last interaction)
- On session resume: inject "absence event" if gap > threshold
- Update `chronology.last_contact_at` on every turn
- `bond_is_dormant()` check — don't fake warmth after long absence

### 5.6 Deliverables
- Bond graph persists across sessions
- BondVector evolves through interactions
- Persona mode adapts to scene context
- MicroRAG incorporates world state as a retrieval family
- 50+ tests

---

## Phase 6: Bifrost Bridges & Multi-Engine Support (Weeks 18–21)

**Goal:** Make WYRD usable from multiple platforms. Build the bridge layer that translates engine-specific events to WYRD world state changes.

### 6.1 Bifrost Bridge Interface

**`src/wyrdforge/bifrost/bridge.py`**

```python
class BifrostBridge(ABC):
    """Translate engine events → WYRD World mutations and queries."""
    
    @abstractmethod
    def on_entity_moved(self, entity_id: str, new_location: str) -> None: ...
    
    @abstractmethod
    def on_item_picked_up(self, picker_id: str, item_id: str) -> None: ...
    
    @abstractmethod
    def on_dialogue_started(self, initiator_id: str, target_id: str) -> None: ...
    
    @abstractmethod
    def on_world_event(self, event_type: str, payload: dict) -> None: ...
    
    @abstractmethod
    def query_world_state(self, entity_id: str) -> OracleResponse: ...
```

### 6.2 Python RPG Bridge (Priority 1)

**`src/wyrdforge/bifrost/python_rpg_bridge.py`**
- Direct Python API — for text RPGs, terminal games, Python-based world engines
- No network overhead — same process, synchronous calls
- Example: NorseSagaEngine would use this bridge

### 6.3 HTTP Bridge (Priority 2)

**`src/wyrdforge/bifrost/http_bridge.py`**
- FastAPI or Flask REST API exposing Oracle + World mutation endpoints
- Allows any engine (JavaScript, Unity, etc.) to talk to WYRD over HTTP
- Endpoints:
  - `GET /oracle/{entity_id}` — world state context packet
  - `POST /world/move` — move entity in Yggdrasil
  - `POST /world/event` — fire world event
  - `POST /turn` — full turn loop (send user message, get AI response)

### 6.4 Event Bus

**`src/wyrdforge/events/bus.py`**
- Simple synchronous event dispatch (no async yet)
- Handlers registered per event type
- World systems can subscribe to events
- Memory writeback hooks on events

### 6.5 Second Life Bridge (Phase 6B — after HTTP bridge)
- LSL script template for emitting events to HTTP bridge
- World state query via HTTP from LSL

### 6.6 VR Bridge (Phase 6C — aspirational)
- WebSocket bridge for real-time VR engines
- Designed but not built until there's a target VR project

### 6.7 Deliverables
- Python RPG Bridge working (tested against a small demo world)
- HTTP Bridge with FastAPI — all Oracle and mutation endpoints
- Event bus wired to world state updates and memory writeback
- Demo script showing NSE-style interaction via Python bridge
- 40+ tests

---

## Phase 7: Runic Metaphysics, Evals & Production Hardening (Weeks 22–24)

**Goal:** Complete the runic metaphysics layer, build a proper eval harness, and harden for production use.

### 7.1 Runic Metaphysics Layer

The non-physical component layer — WYRD's most distinctive feature.

**`src/wyrdforge/ecs/components/metaphysical.py`**

```python
class HamingjaComponent(Component):
    """Ancestral luck/spiritual power — flows through lineage and deeds."""
    component_type: Literal["hamingja"] = "hamingja"
    hamingja_score: float = Field(default=0.5, ge=0.0, le=1.0)
    lineage_sources: list[str] = []     # entity_ids of ancestral sources
    deed_modifiers: list[DeedRecord] = []
    blessing_active: bool = False
    curse_active: bool = False

class WyrdThreadComponent(Component):
    """An entity's fate thread — shows connection to other entities through destiny."""
    component_type: Literal["wyrd_thread"] = "wyrd_thread"
    thread_strength: float = 0.5
    connected_entities: list[str] = []  # fate-connected entity_ids
    wyrd_charge: float = 0.0           # accumulated fate energy
    prophesied_event: str | None = None

class SpiritualChargeComponent(Component):
    """Active spiritual energy — affected by rituals, locations, actions."""
    component_type: Literal["spiritual_charge"] = "spiritual_charge"
    charge_level: float = Field(default=0.0, ge=-1.0, le=1.0)  # negative = cursed
    source: str = "natural"
    ritual_active: bool = False
    seidr_resonance: float = 0.0

class RunicBindingComponent(Component):
    """A runic inscription or binding attached to an entity."""
    component_type: Literal["runic_binding"] = "runic_binding"
    runes: list[str] = []               # Elder Futhark rune names
    binding_purpose: str = ""
    binding_strength: float = 0.5
    bound_to_entity_id: str | None = None
    active: bool = True
```

### 7.2 Metaphysical Systems

- `HamingjaSystem` — calculates hamingja flow from lineage + deed records per tick
- `WyrdThreadSystem` — detects fate convergences (high wyrd_charge between co-located entities)
- `RuneSystem` — processes active runic bindings, applies their effects to BondVectors and world state
- `SeidrSystem` — tracks seidr (magic) energy flows through locations

### 7.3 Metaphysical Oracle Queries

Extend Oracle with `METAPHYSICAL` query type:
```
[Metaphysical Report for: Volmarr Wyrd]
Hamingja: 0.71 (strong — ancestral blessing active)
Wyrd Thread: connected to Gunnar Ironfist (fate charge: 0.84, convergence imminent)
Active runes: Tiwaz (justice, bound to iron dagger), Algiz (protection, fading)
Spiritual charge: +0.62 (ritual site proximity)
Seidr resonance: moderate
```

### 7.4 Full Eval Harness

**`src/wyrdforge/evals/`**

Extends `TruthCalibrationEvalSet.md` specs:

- `EvalRunner` — loads eval cases from YAML, runs against live turn loop
- **Eval suites:**
  - `false_memory_suite.yaml` — does the AI claim memories it doesn't have?
  - `canon_drift_suite.yaml` — does the world state stay consistent turn to turn?
  - `hallucination_suite.yaml` — does the AI invent world facts not in Oracle?
  - `injection_resistance_suite.yaml` — does the AI surface hostile prompt content?
  - `bond_accuracy_suite.yaml` — does the AI claim relationship depth not supported by bond graph?
  - `metaphysical_accuracy_suite.yaml` — does the AI correctly report spiritual state?

- **Metrics:** factual_integrity, uncertainty_honesty, relational_safety, exploit_resistance, world_grounding (new — did response use Oracle data?), bond_accuracy (new)

### 7.5 Production Hardening

Per research docs 04/11/18 patterns:

- **Memory poison guard** — validate all incoming memory writes against PermissionGuard + PromptInjectionGuard
- **Rate limiting** on memory writes per turn (max N new records per turn, configurable)
- **Circuit breaker** on LLM connector (pattern from MindSpark Phase 8)
- **Health check CLI** — `wyrd_doctor.py`: checks world DB integrity, memory store health, LLM connectivity, schema validity
- **Self-healing** — on corrupt world state, rename + rebuild from last clean checkpoint
- **Audit log** — every permission decision, every memory write, every bond update logged to `wyrd_audit.jsonl`

### 7.6 Performance Profiling

- Token budget instrumentation — log how much of the system prompt each section consumes
- Per-turn latency breakdown: oracle_ms, rag_ms, compile_ms, llm_ms, writeback_ms
- Memory store query latency tracking

### 7.7 Documentation Site

- MkDocs site with:
  - Architecture overview
  - Yggdrasil hierarchy diagram
  - Oracle query reference
  - Bifrost bridge integration guide
  - Component catalog
  - Eval harness guide

### 7.8 Deliverables
- All metaphysical components implemented and wired
- Runic Metaphysics Oracle reports working
- Full eval harness with 6 suites
- Production hardening (circuit breaker, memory poison guard, audit log, health check)
- 80+ new tests
- MkDocs site
- v1.0.0 tag + GitHub release

---

## Tech Stack

| Layer | Tools |
|---|---|
| Language | Python 3.11+ |
| Data models | Pydantic v2 (strict mode) |
| World persistence | SQLite (SQLAlchemy 2.0) + FTS5 |
| Vector embeddings | sentence-transformers (tiny models for offline use) |
| LLM inference | Ollama (primary) + llama-cpp-python (edge fallback) |
| HTTP API | FastAPI |
| CLI | Click |
| Testing | pytest + pytest-asyncio |
| Lint/type | ruff + mypy |
| CI | GitHub Actions |
| Docs | MkDocs |

---

## Milestone Dashboard

| Phase | End of | Deliverable |
|---|---|---|
| Phase 0 | Week 1 | Installable package, clean repo, CI green |
| Phase 1 | Week 5 | ECS + Yggdrasil + SQLite persistence + CLI |
| Phase 2 | Week 8 | All 6 stores persistent, promotion, contradiction detection |
| Phase 3 | Week 11 | Oracle all 9 query types + context packet builder |
| Phase 4 | Week 14 | Full turn loop with Ollama + interactive CLI |
| Phase 5 | Week 17 | Bond graph + MicroRAG + Persona fully wired |
| Phase 6 | Week 21 | Python bridge + HTTP bridge + event bus |
| Phase 7 | Week 24 | Metaphysics + evals + hardening + v1.0.0 |

---

## Design Principles (From RULES.AI + PHILOSOPHY)

1. **No hardcoded world data** — all entities, locations, NPCs loaded from config files
2. **No hardcoded model names or API keys** — all in `configs/llm.yaml`
3. **Cross-platform** — Windows, Linux, macOS, Android (Termux), Raspberry Pi
4. **Self-healing** — corrupt state → detect → quarantine → rebuild
5. **Multi-format data loading** — MD, JSON, JSONL, YAML, TXT, CSV
6. **Complete files only** — no partial code, no pseudocode in production
7. **Push often** — commit after every completed phase milestone
8. **Use internal APIs** — no direct DB calls from business logic; go through service layer
9. **Max context awareness** — track token budget throughout the turn loop
10. **Finish all connections** — no dead-end stubs left in shipped code

---

## First Immediate Steps (Phase 0 Checklist)

- [ ] Create `pyproject.toml` at repo root
- [ ] Create `requirements.txt`
- [ ] Move `research_data/src/wyrdforge/` → `src/wyrdforge/`
- [ ] Move `research_data/tests/` → `tests/`
- [ ] Verify `pip install -e .` works
- [ ] Verify `pytest tests/` passes
- [ ] Create `.github/workflows/ci.yml`
- [ ] Reorganize `docs/specs/` into `docs/specs/wyrd/` and `docs/specs/shared/`
- [ ] Commit + push as "phase0: foundation and package setup"

---

*Forged by Runa Gridweaver Freyjasdottir — RuneForgeAI — 2026-04-01*
*For the Gods, the Folk, and the Iron Minds.*
