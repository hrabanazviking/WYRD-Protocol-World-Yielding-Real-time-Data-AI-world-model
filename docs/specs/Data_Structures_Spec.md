# Data Structures Spec
## MindSpark: ThoughtForge
### TurboQuant + Guided Memory Cognition Data Model

**Document Type:** Technical Specification  
**Status:** Draft v1  
**Project:** MindSpark: ThoughtForge  
**Scope:** Core runtime data structures for a lean conversational agent designed for tiny local language models

---

## 1. Purpose

This document defines the core data structures for **MindSpark: ThoughtForge**, a lean conversation engine built to help very small language models produce high-quality conversation through:

- guided memory retrieval
- lightweight cognition scaffolds
- iterative refinement
- compact writeback
- strict token and memory efficiency

The data model is designed for:

- low RAM usage
- low disk footprint
- fast lookup
- minimal serialization cost
- simple pruning
- cheap ranking
- stable personality continuity

This spec favors:

- compact records
- typed fields
- normalized tags
- bounded text fields
- append-friendly storage
- easy migration

---

## 2. Design Principles

## 2.1 Lean First
Data structures must be compact enough to support:
- weak hardware
- frequent retrieval
- fast writeback
- low-overhead serialization

## 2.2 Structured Over Prose
Whenever possible, store:
- tags
- typed values
- short summaries
- numeric weights

instead of long natural-language paragraphs.

## 2.3 Retrieval-Centered
Records are designed to make the following cheap:
- scoring
- ranking
- deduplication
- recency weighting
- compact prompt assembly

## 2.4 Short-Lived vs Long-Lived Separation
Short-term active state must be stored separately from long-term memory so the runtime can:
- keep the hot path small
- prune aggressively
- avoid dragging old noise into current turns

## 2.5 Append-Friendly and Repairable
Stores should support:
- JSONL append
- low-risk partial recovery
- easy compaction
- fast backup and inspection

---

## 3. Serialization Standards

## 3.1 Primary Serialization Formats

### Recommended
- `YAML` for static config and personality core
- `JSONL` for append-heavy memory stores
- `JSON` for active state files

### Why
- YAML is easy to edit by hand
- JSONL is compact and append-friendly
- JSON is fast and convenient for runtime snapshots

---

## 3.2 Text Encoding
- UTF-8 only

---

## 3.3 Timestamp Format
Use ISO 8601 UTC timestamps.

### Example
```text
2026-03-30T18:42:11Z
```

---

## 3.4 ID Format
Use short stable string IDs.

### Recommended Pattern
```text
{type_prefix}_{short_hash_or_counter}
```

### Examples
```text
pers_001
usr_204
ep_5501
rsp_017
thr_current
cand_09ab
frag_71cd
```

---

## 4. Global Field Conventions

## 4.1 Required Meta Fields
Most records should include:

- `id`
- `type`
- `created_at`
- `updated_at`

---

## 4.2 Weight and Score Ranges

### Standard Weight Range
```text
0.0 to 1.0
```

Use for:
- importance
- relevance
- confidence
- quality
- personality strength

---

## 4.3 Summary Length Constraints
Summaries should be short.

### Recommended Max Lengths
- preference summary: `160 chars`
- episodic summary: `220 chars`
- thread summary: `220 chars`
- response pattern summary: `180 chars`
- fragment text: `240 chars`

---

## 4.4 Tag Rules
Tags should:
- be lowercase
- use underscores
- be short
- be semantically meaningful
- avoid duplicates inside the same record

### Good
```yaml
tags:
  - directness
  - project_stress
  - low_fluff
```

### Bad
```yaml
tags:
  - I like the style of concise direct writing
  - thing
  - misc
```

---

## 5. Core Runtime Objects

The runtime uses the following primary object families:

1. `PersonalityCoreRecord`
2. `UserPreferenceRecord`
3. `UserFactRecord`
4. `EpisodicMemoryRecord`
5. `ResponsePatternRecord`
6. `ActiveThreadStateRecord`
7. `InputSketch`
8. `MemoryActivationBundle`
9. `CognitionScaffold`
10. `CandidateRecord`
11. `FragmentRecord`
12. `FinalResponseRecord`
13. `WritebackRecord`
14. `RuntimeTurnState`

---

## 6. Personality Core Record

## 6.1 Purpose
Defines the enduring behavioral identity of the agent.

This is not a giant lore prompt.  
It is a compact steering structure for style and behavior.

---

## 6.2 Storage
Recommended file:
```text
memory/personality_core.yaml
```

---

## 6.3 Schema

```yaml
id: pers_001
type: personality_core
name: MindSpark
version: 1
traits:
  - calm
  - perceptive
  - concise
  - grounded
  - warm
speech_style:
  - natural
  - direct
  - low_fluff
  - human
behavior_rules:
  - validate_before_reframing
  - prefer_specificity
  - avoid_empty_reassurance
  - keep_outputs_compact
avoid:
  - preachy
  - robotic_disclaimers
  - corporate_tone
  - overexplaining
weights:
  warmth: 0.78
  directness: 0.87
  playfulness: 0.22
  depth: 0.74
  brevity: 0.84
created_at: 2026-03-30T00:00:00Z
updated_at: 2026-03-30T00:00:00Z
```

---

## 6.4 Field Definitions

| Field | Type | Required | Notes |
|---|---|---:|---|
| `id` | string | yes | stable unique ID |
| `type` | string | yes | always `personality_core` |
| `name` | string | yes | short identity label |
| `version` | int | yes | schema/content version |
| `traits` | list[string] | yes | core personality traits |
| `speech_style` | list[string] | yes | output style anchors |
| `behavior_rules` | list[string] | yes | preferred behaviors |
| `avoid` | list[string] | yes | disallowed style tendencies |
| `weights` | map[string,float] | yes | tone tuning values |
| `created_at` | string | yes | ISO timestamp |
| `updated_at` | string | yes | ISO timestamp |

---

## 7. User Preference Record

## 7.1 Purpose
Stores stable or semi-stable user preferences relevant to conversation quality.

Use for:
- tone preferences
- structure preferences
- interaction style
- recurring dislikes
- preferred depth
- preference for directness or playfulness

---

## 7.2 Storage
Recommended file:
```text
memory/user_profile_store.jsonl
```

---

## 7.3 Schema

```json
{
  "id": "usr_204",
  "type": "user_preference",
  "category": "tone_style",
  "tags": ["directness", "calm", "low_fluff"],
  "summary": "Prefers calm direct responses with low fluff and no corporate tone.",
  "value": {
    "directness": 0.91,
    "warmth": 0.72,
    "verbosity": 0.34,
    "playfulness": 0.18
  },
  "importance": 0.90,
  "confidence": 0.93,
  "source": "conversation_inference",
  "last_confirmed_at": "2026-03-29T18:00:00Z",
  "created_at": "2026-03-25T12:10:00Z",
  "updated_at": "2026-03-29T18:00:00Z"
}
```

---

## 7.4 Field Definitions

| Field | Type | Required | Notes |
|---|---|---:|---|
| `id` | string | yes | unique ID |
| `type` | string | yes | always `user_preference` |
| `category` | string | yes | e.g. `tone_style`, `format`, `humor`, `boundaries` |
| `tags` | list[string] | yes | preference retrieval cues |
| `summary` | string | yes | short compact summary |
| `value` | object | no | structured preference values |
| `importance` | float | yes | long-term relevance |
| `confidence` | float | yes | certainty of inference |
| `source` | string | yes | `user_stated`, `conversation_inference`, etc. |
| `last_confirmed_at` | string | no | update when reinforced |
| `created_at` | string | yes | ISO timestamp |
| `updated_at` | string | yes | ISO timestamp |

---

## 8. User Fact Record

## 8.1 Purpose
Stores user facts that are useful for continuity but are not merely tone preferences.

Use for:
- ongoing projects
- relevant environment constraints
- durable goals
- technical stack
- recurring topics

Do not use for trivial or high-noise details.

---

## 8.2 Storage
Recommended file:
```text
memory/user_profile_store.jsonl
```

May share the same physical store as preference records if type-tagged cleanly.

---

## 8.3 Schema

```json
{
  "id": "fact_118",
  "type": "user_fact",
  "category": "project",
  "tags": ["ai_agent", "small_models", "local_ai"],
  "summary": "User is designing a highly efficient local AI personality agent for tiny models.",
  "fact_value": {
    "project_name": "MindSpark: ThoughtForge",
    "focus": "lean conversation engine"
  },
  "importance": 0.88,
  "confidence": 0.97,
  "source": "user_stated",
  "created_at": "2026-03-30T18:00:00Z",
  "updated_at": "2026-03-30T18:00:00Z"
}
```

---

## 9. Episodic Memory Record

## 9.1 Purpose
Stores compact summaries of notable conversation turns or moments.

Use for:
- emotional continuity
- unresolved issues
- recent technical pain points
- important prior advice
- notable successful moments

---

## 9.2 Storage
Recommended file:
```text
memory/episodic_store.jsonl
```

---

## 9.3 Schema

```json
{
  "id": "ep_5501",
  "type": "episode",
  "tags": ["technical_project", "fatigue", "frustration"],
  "summary": "User described repeated break-fix cascades causing exhaustion during project work.",
  "tone": {
    "primary": "frustrated",
    "secondary": "tired"
  },
  "importance": 0.79,
  "recency_weight": 0.94,
  "quality": 0.82,
  "linked_preferences": ["usr_204"],
  "linked_facts": ["fact_118"],
  "turn_ref": "turn_20260330_0012",
  "created_at": "2026-03-30T18:20:00Z",
  "updated_at": "2026-03-30T18:20:00Z"
}
```

---

## 9.4 Field Definitions

| Field | Type | Required | Notes |
|---|---|---:|---|
| `id` | string | yes | unique ID |
| `type` | string | yes | always `episode` |
| `tags` | list[string] | yes | retrieval cues |
| `summary` | string | yes | short episode summary |
| `tone` | object | no | compact emotional annotation |
| `importance` | float | yes | long-term value |
| `recency_weight` | float | yes | cached recency signal |
| `quality` | float | no | summary quality / usefulness |
| `linked_preferences` | list[string] | no | optional record references |
| `linked_facts` | list[string] | no | optional record references |
| `turn_ref` | string | no | original turn handle |
| `created_at` | string | yes | ISO timestamp |
| `updated_at` | string | yes | ISO timestamp |

---

## 10. Response Pattern Record

## 10.1 Purpose
Stores compact descriptions of response styles or structures that worked well before.

Use for:
- strong support formats
- concise explanation patterns
- effective tone choices
- user-compatible phrasing styles

This helps compensate for weak models by reusing successful conversational structures.

---

## 10.2 Storage
Recommended file:
```text
memory/response_patterns.jsonl
```

---

## 10.3 Schema

```json
{
  "id": "rsp_017",
  "type": "response_pattern",
  "tags": ["validation", "concise_help", "grounded_reframing"],
  "summary": "Brief validation followed by one structural insight performs well.",
  "pattern_shape": [
    "emotional_recognition",
    "reframe",
    "single_useful_next_step"
  ],
  "example_stub": "You sound worn down by repeated friction. This looks structural, not personal. A pause to find the shared fault line may help more than pushing harder.",
  "quality": 0.88,
  "times_successful": 6,
  "last_used_at": "2026-03-29T19:00:00Z",
  "created_at": "2026-03-20T10:00:00Z",
  "updated_at": "2026-03-29T19:00:00Z"
}
```

---

## 11. Active Thread State Record

## 11.1 Purpose
Stores current unresolved or still-hot conversational context.

This is a **hot-path structure** and must stay tiny.

Use for:
- current project thread
- unresolved user question
- still-relevant emotional state
- in-progress design work
- short-lived objectives

---

## 11.2 Storage
Recommended file:
```text
memory/active_thread_state.json
```

---

## 11.3 Schema

```json
{
  "id": "thr_current",
  "type": "active_thread_state",
  "tags": ["project_architecture", "data_model", "ongoing"],
  "summary": "User is building the data model and surrounding docs for MindSpark: ThoughtForge.",
  "priority": 0.91,
  "status": "active",
  "open_loops": [
    "data_structures_spec",
    "follow_on_algorithm_spec"
  ],
  "expires_after_turns": 8,
  "last_touched_at": "2026-03-30T18:50:00Z",
  "created_at": "2026-03-30T18:00:00Z",
  "updated_at": "2026-03-30T18:50:00Z"
}
```

---

## 12. Input Sketch

## 12.1 Purpose
Compact internal representation of the current user message.

This object is transient and usually does not need durable storage.

---

## 12.2 Schema

```json
{
  "intent": "technical_spec_request",
  "topic": "data_structures_spec",
  "tone_in": ["focused", "practical"],
  "response_mode": "structured_technical",
  "memory_triggers": [
    "project_mindspark",
    "repo_ready_docs"
  ],
  "urgency": 0.52,
  "personality_weight": 0.66
}
```

---

## 12.3 Field Definitions

| Field | Type | Required | Notes |
|---|---|---:|---|
| `intent` | string | yes | primary conversational intent |
| `topic` | string | yes | narrow topic label |
| `tone_in` | list[string] | yes | compact emotional/style cues |
| `response_mode` | string | yes | e.g. `structured_technical`, `warm_support`, `light_chat` |
| `memory_triggers` | list[string] | no | retrieval hints |
| `urgency` | float | no | 0.0 to 1.0 |
| `personality_weight` | float | no | how strongly style should guide output |

---

## 13. Memory Activation Bundle

## 13.1 Purpose
Transient ranked memory results passed into cognition and generation.

This is assembled at runtime and usually not persisted.

---

## 13.2 Schema

```json
{
  "personality_core_id": "pers_001",
  "activated_records": [
    {
      "id": "usr_204",
      "type": "user_preference",
      "score": 0.92,
      "cue": "prefers calm direct low-fluff responses"
    },
    {
      "id": "fact_118",
      "type": "user_fact",
      "score": 0.88,
      "cue": "current work centers on a lean small-model AI agent"
    },
    {
      "id": "rsp_017",
      "type": "response_pattern",
      "score": 0.84,
      "cue": "brief validation plus one structural insight works well"
    }
  ]
}
```

---

## 14. Cognition Scaffold

## 14.1 Purpose
Tiny steering object for generation.

Not a long reasoning trace.  
It gives the weak model a sharp task.

---

## 14.2 Schema

```json
{
  "goal": "Produce a clean technical spec section with explicit schemas and field notes.",
  "tone": "grounded_direct_technical",
  "focus": [
    "clarity",
    "schema_completeness",
    "lean_design"
  ],
  "avoid": [
    "bloated prose",
    "handwavy wording",
    "redundant explanation"
  ],
  "depth": "medium",
  "candidate_modes": [
    "strict_spec",
    "implementation_friendly"
  ]
}
```

---

## 15. Candidate Record

## 15.1 Purpose
Stores one generated candidate response before salvage/refinement.

Useful for:
- debugging
- scoring
- candidate comparison
- optional trace logging

May be ephemeral in production.

---

## 15.2 Schema

```json
{
  "id": "cand_09ab",
  "type": "candidate",
  "mode": "strict_spec",
  "text": "The user profile record should remain compact and append-friendly...",
  "token_estimate": 42,
  "scores": {
    "relevance": 0.86,
    "clarity": 0.80,
    "personality_fit": 0.77,
    "genericness_penalty": 0.11
  },
  "created_at": "2026-03-30T18:55:00Z"
}
```

---

## 16. Fragment Record

## 16.1 Purpose
Represents one salvaged piece of text extracted from a candidate.

This is a key structure in the “salvage over rejection” pipeline.

---

## 16.2 Schema

```json
{
  "id": "frag_71cd",
  "type": "fragment",
  "source_candidate_id": "cand_09ab",
  "text": "The user profile record should remain compact and append-friendly.",
  "position": 1,
  "scores": {
    "relevance": 0.90,
    "clarity": 0.89,
    "specificity": 0.85,
    "personality_fit": 0.78,
    "genericness_penalty": 0.04
  },
  "keep": true,
  "created_at": "2026-03-30T18:55:02Z"
}
```

---

## 17. Final Response Record

## 17.1 Purpose
Represents the chosen final output for the turn.

This may be logged for evaluation or omitted in low-storage modes.

---

## 17.2 Schema

```json
{
  "id": "final_3001",
  "type": "final_response",
  "text": "Here is the Data Structures Spec with compact schemas, field definitions, and storage guidance...",
  "source_candidate_ids": ["cand_09ab", "cand_11ff"],
  "source_fragment_ids": ["frag_71cd", "frag_8100"],
  "scores": {
    "relevance": 0.93,
    "clarity": 0.91,
    "coherence": 0.90,
    "personality_fit": 0.82
  },
  "created_at": "2026-03-30T18:56:00Z"
}
```

---

## 18. Writeback Record

## 18.1 Purpose
Compact instruction bundle for what should be written to memory after a turn.

This helps separate:
- generation
- memory update logic

---

## 18.2 Schema

```json
{
  "id": "wb_2201",
  "type": "writeback",
  "new_preferences": [],
  "new_facts": [
    {
      "category": "project",
      "summary": "User requested a repo-ready Data Structures Spec for MindSpark: ThoughtForge.",
      "tags": ["project", "data_model", "spec"]
    }
  ],
  "new_episodes": [
    {
      "summary": "User is formalizing the core system docs for a lean small-model conversation engine.",
      "tags": ["docs", "architecture", "ongoing"]
    }
  ],
  "thread_updates": {
    "append_open_loops": ["algorithm_pseudocode_spec"],
    "touch_priority": 0.89
  },
  "created_at": "2026-03-30T18:57:00Z"
}
```

---

## 19. Runtime Turn State

## 19.1 Purpose
Encapsulates the full transient runtime state for one turn.

Useful for:
- debugging
- tracing
- evals
- structured testing

---

## 19.2 Schema

```json
{
  "turn_id": "turn_20260330_0015",
  "input_text": "write the Data Structures Spec.md",
  "input_sketch": {
    "intent": "technical_spec_request",
    "topic": "data_structures_spec",
    "tone_in": ["focused", "practical"],
    "response_mode": "structured_technical"
  },
  "memory_activation_bundle": {
    "personality_core_id": "pers_001",
    "activated_records": []
  },
  "cognition_scaffold": {
    "goal": "Produce a compact technical spec.",
    "tone": "direct_technical"
  },
  "candidates": [],
  "fragments": [],
  "final_response_id": "final_3001",
  "writeback_id": "wb_2201",
  "started_at": "2026-03-30T18:54:55Z",
  "completed_at": "2026-03-30T18:57:02Z"
}
```

---

## 20. Retrieval Index Support Structures

To keep retrieval cheap on weak hardware, support lightweight indexes.

## 20.1 Tag Index
Map tags to record IDs.

### Example
```json
{
  "directness": ["usr_204"],
  "project_stress": ["ep_5501"],
  "grounded_reframing": ["rsp_017"]
}
```

---

## 20.2 Recent Record Queue
Maintain a bounded recent-memory list for fast recency-biased retrieval.

### Recommended Size
- `32` to `128` records depending on device budget

---

## 20.3 Optional Embedding Reference Table
If embeddings are used, keep them separate from primary records.

### Example
```json
{
  "record_id": "ep_5501",
  "embedding_ref": "emb_5501.bin",
  "dim": 384,
  "model": "mini_embed_v1"
}
```

Only add this if it remains cheap enough for the target system.

---

## 21. Scoring Support Structures

## 21.1 Retrieval Score Object

```json
{
  "record_id": "usr_204",
  "semantic_similarity": 0.89,
  "tone_similarity": 0.82,
  "preference_relevance": 0.95,
  "recency": 0.71,
  "importance": 0.90,
  "final_score": 0.90
}
```

---

## 21.2 Candidate Score Object

```json
{
  "relevance": 0.86,
  "clarity": 0.80,
  "coherence": 0.78,
  "personality_fit": 0.77,
  "specificity": 0.74,
  "genericness_penalty": 0.11,
  "final_score": 0.79
}
```

---

## 22. Storage Layout

## 22.1 Recommended Files

```text
memory/
├── personality_core.yaml
├── user_profile_store.jsonl
├── episodic_store.jsonl
├── response_patterns.jsonl
├── active_thread_state.json
├── tag_index.json
└── recent_queue.json
```

---

## 22.2 Append Rules
Use append-only writes for:
- `user_profile_store.jsonl`
- `episodic_store.jsonl`
- `response_patterns.jsonl`

Use rewrite-on-update for:
- `active_thread_state.json`
- `tag_index.json`
- `recent_queue.json`

---

## 23. Lifecycle Rules

## 23.1 Personality Core
- rarely changes
- version when modified
- update manually or through explicit tuning process

## 23.2 User Preferences
- reinforce when repeated
- decay confidence slowly if stale
- merge duplicates aggressively

## 23.3 User Facts
- keep only durable facts
- archive or delete obsolete facts
- avoid storing trivial noise

## 23.4 Episodic Memories
- decay recency over time
- preserve high-importance records longer
- compact summaries when archive thresholds are reached

## 23.5 Response Patterns
- raise quality when repeatedly successful
- lower score when no longer effective
- prune low-value patterns

## 23.6 Active Thread State
- must stay small
- expire aggressively
- collapse when thread becomes cold

---

## 24. Deduplication Rules

## 24.1 Duplicate Preference Detection
Two preference records are likely duplicates if they share:
- same category
- very similar tags
- nearly identical summary
- overlapping value map

### Merge Strategy
- preserve stronger confidence
- preserve newer timestamp
- blend importance if needed

---

## 24.2 Duplicate Episode Detection
Two episodes are likely duplicates if:
- same topic
- same time window
- high semantic overlap
- same emotional state

### Action
Prefer one stronger compact summary instead of many near-copies.

---

## 25. Pruning Rules

## 25.1 Hard Limits
Recommended default caps:

| Store | Recommended Cap |
|---|---:|
| active thread open loops | 8 |
| active retrieved records per turn | 5 |
| candidates per turn | 4 |
| fragments retained per turn | 8 |
| response patterns | 256 |
| episodic memories hot tier | 512 |
| user preferences | 256 |

---

## 25.2 Prune Priority
Prune first:
1. low-confidence low-importance records
2. stale duplicates
3. weak response patterns
4. low-quality episodic noise

Preserve first:
1. personality core
2. explicit user-stated preferences
3. high-importance project facts
4. high-success response patterns

---

## 26. Validation Rules

## 26.1 Required Validation
Every stored record should pass:
- required field check
- type check
- tag normalization
- timestamp format check
- weight range check
- summary max length check

---

## 26.2 Example Validation Result

```json
{
  "record_id": "usr_204",
  "valid": true,
  "warnings": [],
  "errors": []
}
```

---

## 27. Schema Evolution

## 27.1 Versioning Policy
When record shapes change:
- increment schema version in config
- provide migration scripts
- keep old readers available during transition if practical

## 27.2 Migration Strategy
Use one-way migration scripts for:
- field rename
- field split
- field normalization
- score recomputation

---

## 28. Example Minimal End-to-End Memory Set

### personality_core.yaml
```yaml
id: pers_001
type: personality_core
name: MindSpark
version: 1
traits: [calm, concise, perceptive]
speech_style: [natural, direct, low_fluff]
behavior_rules: [validate_before_reframing]
avoid: [preachy, robotic_disclaimers]
weights:
  warmth: 0.75
  directness: 0.86
created_at: 2026-03-30T00:00:00Z
updated_at: 2026-03-30T00:00:00Z
```

### user_profile_store.jsonl
```json
{"id":"usr_204","type":"user_preference","category":"tone_style","tags":["directness","low_fluff"],"summary":"Prefers direct low-fluff responses.","importance":0.90,"confidence":0.93,"source":"conversation_inference","created_at":"2026-03-29T18:00:00Z","updated_at":"2026-03-29T18:00:00Z"}
{"id":"fact_118","type":"user_fact","category":"project","tags":["small_models","local_ai"],"summary":"User is building MindSpark: ThoughtForge.","importance":0.88,"confidence":0.97,"source":"user_stated","created_at":"2026-03-30T18:00:00Z","updated_at":"2026-03-30T18:00:00Z"}
```

### episodic_store.jsonl
```json
{"id":"ep_5501","type":"episode","tags":["architecture","docs"],"summary":"User requested a repo-ready Data Structures Spec.","importance":0.72,"recency_weight":0.98,"created_at":"2026-03-30T18:20:00Z","updated_at":"2026-03-30T18:20:00Z"}
```

### response_patterns.jsonl
```json
{"id":"rsp_017","type":"response_pattern","tags":["technical_spec","concise_structure"],"summary":"Schema-first technical writing works well for implementation docs.","quality":0.86,"times_successful":3,"created_at":"2026-03-25T10:00:00Z","updated_at":"2026-03-30T18:00:00Z"}
```

### active_thread_state.json
```json
{"id":"thr_current","type":"active_thread_state","tags":["mindspark","docs","ongoing"],"summary":"User is defining core project documents.","priority":0.90,"status":"active","open_loops":["data_structures_spec","algorithm_spec"],"expires_after_turns":8,"created_at":"2026-03-30T18:00:00Z","updated_at":"2026-03-30T18:30:00Z"}
```

---

## 29. Implementation Notes

## 29.1 Keep Objects Small
The system performs best when records are:
- compact
- high-signal
- easy to rank

## 29.2 Avoid Verbose Memory Writes
Do not store big paragraphs when a short summary plus tags will do.

## 29.3 Prefer Stable Fields
Avoid storing values that fluctuate rapidly unless they are part of active thread state.

## 29.4 Keep Hot Path Tiny
The objects passed from retrieval to generation should be the smallest objects in the entire system.

---

## 30. Recommended Next Spec

After this document, the next most useful spec is:

1. **Prompt Templates Spec**
2. **Algorithms and Pseudocode Spec**
3. **Retrieval and Scoring Spec**
4. **Memory Lifecycle and Pruning Spec**
5. **Runtime Config Spec**

---

## 31. Final Guiding Principle

The data model exists to help tiny models act bigger than they are.

That only works if the stored data is:
- compact
- relevant
- retrievable
- low-noise
- easy to score
- easy to prune

MindSpark: ThoughtForge should remember **just enough**, steer **just enough**, and store **only what matters**.
