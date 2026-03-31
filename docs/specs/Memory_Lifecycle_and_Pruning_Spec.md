# Memory Lifecycle and Pruning Spec
## MindSpark: ThoughtForge
### Lean Memory Aging, Consolidation, Retention, and Pruning for Tiny Local Language Models

**Document Type:** Technical Specification  
**Status:** Draft v1  
**Project:** MindSpark: ThoughtForge  
**Scope:** Memory aging, consolidation, deduplication, retention classes, pruning policies, archival logic, compaction rules, and store hygiene for a lean conversational agent optimized for tiny local language models

---

## 1. Purpose

This document defines the memory lifecycle and pruning system for **MindSpark: ThoughtForge**, a lean conversation engine designed to help very small language models remain coherent and useful over time without allowing memory stores to become noisy, bloated, slow, or self-defeating.

The lifecycle system governs:

- how memories age
- what gets reinforced
- what gets consolidated
- what gets decayed
- what gets archived
- what gets deleted
- how active thread state cools down
- how stores remain compact and high-signal

This system is designed for:

- weak hardware
- low RAM usage
- low disk footprint
- predictable retrieval quality
- simple inspection and repair
- bounded growth over long runtimes

---

## 2. Core Design Principles

## 2.1 Memory Must Stay Small to Stay Useful
A small-model system loses quality when memory becomes:
- too large
- too repetitive
- too stale
- too vague
- too noisy

Pruning is not optional.  
Pruning is part of intelligence.

---

## 2.2 Recency Alone Is Not Enough
New memory is not always good memory.  
Old memory is not always bad memory.

Retention should consider:
- durability
- importance
- future relevance
- explicitness
- reusability
- thread affinity

---

## 2.3 Compact Summaries Beat Raw Accumulation
The system should preserve:
- distilled facts
- concise preferences
- reusable patterns
- compact episodes

instead of hoarding raw conversation text.

---

## 2.4 Merge Before You Multiply
When new memory resembles existing memory, prefer:
- reinforcement
- merging
- consolidation

over creating another near-duplicate record.

---

## 2.5 Active State Must Cool Quickly
Hot-path memory must stay tiny.  
Active thread state should decay aggressively and collapse when the conversation shifts away.

---

## 2.6 Protected Memory Should Be Rare
Only a small subset of memory should be effectively protected from pruning:
- personality core
- explicit durable user preferences
- high-confidence durable user facts
- high-quality reusable response patterns

Everything else should compete for survival.

---

## 3. Memory Classes and Lifecycle Behavior

The system manages these primary classes:

1. `personality_core`
2. `user_preference`
3. `user_fact`
4. `episode`
5. `response_pattern`
6. `active_thread_state`
7. `indexes_and_caches`

Each class has its own lifecycle rules.

---

## 4. Lifecycle States

Each memory record may conceptually pass through these states:

1. **created**
2. **reinforced**
3. **active**
4. **cooling**
5. **stale**
6. **archived**
7. **deleted**

Not every class uses all states explicitly, but this model helps structure pruning logic.

---

## 5. Class-by-Class Lifecycle Rules

## 5.1 Personality Core

### Purpose
Persistent behavioral identity.

### Lifecycle
- created manually or via explicit tuning
- rarely updated
- versioned when changed
- never pruned automatically
- always loaded in compact form

### Rules
- do not mutate implicitly during runtime
- use explicit versioning
- preserve all versions if desired for auditability

### Storage
```text
memory/personality_core.yaml
```

---

## 5.2 User Preference

### Purpose
Store durable style, tone, and interaction preferences.

### Lifecycle
- created when strongly supported
- reinforced when repeated
- merged when duplicated
- decays slowly if unconfirmed for long periods
- archived or deleted if weak and stale

### Preferred Retention
High if:
- explicitly stated by user
- repeatedly reinforced
- highly impactful on conversation quality

Lower if:
- weakly inferred
- rarely relevant
- contradicted later

---

## 5.3 User Fact

### Purpose
Store durable contextual facts useful for future continuity.

### Lifecycle
- created when clearly stated or strongly implied
- reinforced when revisited
- merged when repeated
- archived if obsolete
- deleted if low-value and stale

### Preferred Retention
High if:
- durable project fact
- recurring constraint
- stable working context
- long-lived preference-adjacent fact

Low if:
- trivial
- one-off
- no longer relevant
- weakly supported

---

## 5.4 Episode

### Purpose
Store compact summaries of notable moments.

### Lifecycle
- created often, but selectively
- rapidly loses recency weight
- may be consolidated into higher-level summaries
- frequently pruned or archived
- only best episodes remain in hot storage

### Preferred Retention
High if:
- tied to active thread
- emotionally important
- captures unresolved issue
- linked to durable project context
- likely to matter in future turns

Low if:
- trivial
- repetitive
- redundant with thread state
- low quality summary
- no future value

---

## 5.5 Response Pattern

### Purpose
Store reusable successful response shapes.

### Lifecycle
- created when a strong final response is reusable
- reinforced by repeated success
- quality decays if unused or outperformed
- merged with similar patterns
- weak patterns get pruned

### Preferred Retention
High if:
- high success rate
- compact and generalizable
- useful across many similar tasks
- aligned with user preferences

Low if:
- overly specific to one case
- weak quality
- redundant with stronger patterns
- never used again

---

## 5.6 Active Thread State

### Purpose
Track live conversational threads.

### Lifecycle
- created when a topic becomes active
- refreshed when touched
- cools every turn it is not touched
- collapses aggressively
- deleted or reset when cold

### Preferred Retention
Very high while active.  
Very low once thread is cold.

---

## 5.7 Indexes and Caches

### Purpose
Accelerate retrieval and scoring.

### Lifecycle
- rebuilt or refreshed regularly
- never treated as truth source
- safe to discard and regenerate

---

## 6. Lifecycle Metadata

Recommended metadata fields for pruning-aware records:

- `created_at`
- `updated_at`
- `last_used_at`
- `last_confirmed_at`
- `importance`
- `confidence`
- `quality`
- `recency_weight`
- `times_reinforced`
- `times_retrieved`
- `times_successful`
- `status`
- `archive_reason`
- `stale_after_turns`
- `expires_after_turns`

Not all fields apply to all classes.

---

## 7. Aging Model

## 7.1 Purpose

Aging is the gradual reduction of a record’s default retrieval viability over time unless it is reinforced, reused, or protected.

---

## 7.2 Aging Inputs

Aging can depend on:
- time since creation
- time since last use
- time since last confirmation
- record class
- importance
- confidence
- thread relation
- reinforcement count

---

## 7.3 Aging Rule

Use smooth decay instead of binary expiration whenever possible.

### Example intuition
- fresh episode decays quickly
- user preference decays slowly
- high-confidence explicit fact decays very slowly
- active thread state decays very quickly once untouched

---

## 7.4 Example Recency Decay Function

```python
def compute_recency_score(record, now) -> float:
    age_days = max((now - record.updated_at).days, 0)
    half_life_days = select_half_life(record.type, record)

    if half_life_days <= 0:
        return 0.0

    return 0.5 ** (age_days / half_life_days)
```

---

## 7.5 Suggested Half-Life Defaults

| Record Type | Suggested Half-Life |
|---|---:|
| `active_thread_state` | 1-3 turns |
| `episode` | 3-14 days |
| `response_pattern` | 14-60 days |
| `user_preference` | 30-180 days |
| `user_fact` | 30-365 days |

These are starting points only.

---

## 8. Reinforcement Model

## 8.1 Purpose

When a memory is validated by reuse or explicit confirmation, it should become more stable and more retrievable.

---

## 8.2 Reinforcement Signals

Examples:
- record retrieved and useful
- record explicitly confirmed by user
- record matched in multiple turns
- response pattern led to high-quality output
- fact resurfaced as still relevant

---

## 8.3 Reinforcement Effects

Possible effects:
- increase confidence
- increase importance slightly
- refresh timestamps
- reduce decay rate
- increase retention priority
- mark as durable if threshold crossed

---

## 8.4 Reinforcement Pseudocode

```python
def reinforce_record(record, signal_strength: float, now) -> None:
    record.times_reinforced = getattr(record, "times_reinforced", 0) + 1
    record.updated_at = now
    record.last_used_at = now

    if hasattr(record, "confidence"):
        record.confidence = min(1.0, record.confidence + 0.05 * signal_strength)

    if hasattr(record, "importance"):
        record.importance = min(1.0, record.importance + 0.03 * signal_strength)

    if hasattr(record, "quality"):
        record.quality = min(1.0, record.quality + 0.02 * signal_strength)
```

---

## 9. Consolidation Model

## 9.1 Purpose

Consolidation reduces store size by merging related records into cleaner, higher-signal summaries.

---

## 9.2 When to Consolidate

Consolidate when:
- multiple episodes repeat same issue
- several similar preferences exist
- multiple facts overlap strongly
- several response patterns represent the same structure
- thread state can replace episodic clutter

---

## 9.3 Consolidation Outcomes

Possible outcomes:
- merge two records into one
- create one stronger summary and archive source records
- strengthen a durable record and delete weaker duplicates
- collapse many episodes into one topic summary

---

## 9.4 Episode Consolidation Example

Before:
- `ep_1001`: user frustrated by architecture complexity
- `ep_1008`: user still dealing with architecture complexity
- `ep_1013`: user requested more docs for same architecture project

After:
- `ep_c_01`: user is in an ongoing architecture/documentation cycle for MindSpark project

The old episodes may be archived or deleted.

---

## 9.5 Consolidation Pseudocode

```python
def consolidate_similar_records(records: list) -> list:
    groups = cluster_similar_records(records)
    output = []

    for group in groups:
        if len(group) == 1:
            output.append(group[0])
            continue

        merged = merge_record_group(group)
        output.append(merged)

    return output
```

---

## 10. Merging Rules by Record Type

## 10.1 User Preference Merge Rules

Merge if:
- same category
- similar tags
- same directional meaning
- compatible value map

Prefer:
- explicit over inferred
- higher confidence
- newer confirmation
- shorter cleaner summary

### Merge behavior
- combine reinforcement counts
- keep strongest source provenance
- average or max compatible values
- refresh timestamps

---

## 10.2 User Fact Merge Rules

Merge if:
- clearly same fact
- same project or durable context
- summary overlap is high
- newer version expands older without contradiction

Prefer:
- clearer and more current fact summary
- structured value map if available

---

## 10.3 Episode Merge Rules

Merge if:
- same issue or thread
- similar time window
- same emotional or task context
- high semantic overlap

Prefer:
- one concise higher-value episode over many minor duplicates

---

## 10.4 Response Pattern Merge Rules

Merge if:
- pattern shape matches
- purpose overlaps
- one pattern is a stronger generalized form of another

Prefer:
- higher quality
- higher success count
- broader applicability
- shorter cleaner summary

---

## 11. Retention Classes

Records should belong conceptually to one of these retention classes:

1. **protected**
2. **durable**
3. **standard**
4. **ephemeral**
5. **discardable**

---

## 11.1 Protected

Examples:
- personality core
- rare explicit critical user preference
- essential durable project fact

Rules:
- not auto-deleted
- may still be compacted or versioned
- review before removal

---

## 11.2 Durable

Examples:
- well-supported recurring user preference
- stable project fact
- strong reusable response pattern

Rules:
- prune only under stronger pressure
- decay slowly
- preserve through routine cleanup

---

## 11.3 Standard

Examples:
- normal preferences
- useful facts
- mid-value episodes

Rules:
- compete normally for retention
- merge and prune as needed

---

## 11.4 Ephemeral

Examples:
- minor episodes
- short-lived thread hints
- transient planning state

Rules:
- decay quickly
- prune aggressively
- rarely archive

---

## 11.5 Discardable

Examples:
- noise
- duplicates
- weak unsupported inferences
- low-quality summaries

Rules:
- delete early

---

## 12. Pruning Objectives

Pruning should achieve these outcomes:

- smaller hot-path memory
- cleaner retrieval pool
- less duplication
- better signal density
- faster ranking
- lower disk and RAM load
- more coherent generation steering

---

## 13. Pruning Modes

The system should support multiple pruning modes:

1. **light prune**
2. **routine prune**
3. **heavy prune**
4. **emergency prune**

---

## 13.1 Light Prune
Use when:
- store still healthy
- only minor cleanup needed

Actions:
- delete obvious duplicates
- remove expired thread state
- prune lowest-quality episodic noise

---

## 13.2 Routine Prune
Use on normal schedule.

Actions:
- dedupe all stores
- apply retention limits
- archive or delete stale records
- refresh indexes

---

## 13.3 Heavy Prune
Use when:
- retrieval quality dropping
- store growth excessive
- device constraints tightening

Actions:
- raise thresholds
- consolidate aggressively
- reduce hot episode count
- remove weak patterns
- trim preferences more aggressively

---

## 13.4 Emergency Prune
Use when:
- disk/RAM pressure severe
- latency degraded sharply
- store corruption recovery required

Actions:
- preserve only protected and durable records
- rebuild caches from scratch
- clear ephemeral stores
- reset thread state if needed

---

## 14. Pruning Score

## 14.1 Purpose

Each record can be given a prune priority score.  
Higher prune score means more likely to remove.

---

## 14.2 Prune Score Dimensions

- staleness
- low confidence
- low importance
- low quality
- low future relevance
- redundancy
- low reinforcement
- weak recency
- no active thread relation

---

## 14.3 Example Prune Score Formula

```text
prune_score =
  staleness * 0.25 +
  redundancy * 0.20 +
  low_confidence * 0.15 +
  low_importance * 0.15 +
  low_quality * 0.10 +
  low_future_relevance * 0.10 +
  low_reinforcement * 0.05
```

Higher score means higher prune priority.

---

## 14.4 Prune Score Pseudocode

```python
def compute_prune_score(record, now, runtime_state) -> float:
    staleness = 1.0 - compute_recency_score(record, now)
    redundancy = estimate_redundancy(record, runtime_state.memory_store)
    low_confidence = 1.0 - getattr(record, "confidence", 0.5)
    low_importance = 1.0 - getattr(record, "importance", 0.5)
    low_quality = 1.0 - getattr(record, "quality", 0.5)
    low_future_relevance = 1.0 - estimate_future_relevance(record)
    low_reinforcement = 1.0 - normalize_count(getattr(record, "times_reinforced", 0), max_value=10)

    score = (
        staleness * 0.25 +
        redundancy * 0.20 +
        low_confidence * 0.15 +
        low_importance * 0.15 +
        low_quality * 0.10 +
        low_future_relevance * 0.10 +
        low_reinforcement * 0.05
    )

    return max(0.0, min(score, 1.0))
```

---

## 15. Class-Specific Pruning Rules

## 15.1 User Preference Pruning

Delete or archive if:
- weak inference
- low confidence
- no reinforcement
- duplicate of stronger preference
- stale beyond configured window

Preserve if:
- explicit
- high-confidence
- repeated
- impacts response quality strongly

---

## 15.2 User Fact Pruning

Delete or archive if:
- obsolete
- weakly supported
- trivial
- duplicate of stronger fact
- no future relevance

Preserve if:
- tied to ongoing projects
- stable environmental constraint
- durable conversation context

---

## 15.3 Episode Pruning

Delete or archive if:
- low-quality summary
- redundant with thread state
- stale and cold
- one-off triviality
- no future relevance

Preserve if:
- high-importance moment
- unresolved issue
- emotionally meaningful
- linked to durable fact or preference

---

## 15.4 Response Pattern Pruning

Delete if:
- low quality
- never reused
- very narrow or brittle
- duplicated by stronger pattern

Preserve if:
- repeatedly successful
- generalizable
- aligned with user style

---

## 15.5 Active Thread Pruning

Reset or collapse if:
- not touched within expiration window
- open loops resolved
- priority drops below threshold
- conversation topic shifted strongly

---

## 16. Archive vs Delete Rules

## 16.1 Archive When
Archive if:
- record may still matter historically
- record is high importance but cold
- record is replaced by a consolidated summary
- audit trail is valuable

---

## 16.2 Delete When
Delete if:
- record is low confidence
- record is low value
- duplicate of better record
- noisy or malformed
- trivial and stale
- easy to regenerate if needed

---

## 16.3 Archive Storage

Recommended optional archive paths:

```text
memory/archive/
├── archived_preferences.jsonl
├── archived_facts.jsonl
├── archived_episodes.jsonl
└── archived_response_patterns.jsonl
```

If ultra-lean mode is desired, archiving may be disabled and records can be deleted directly.

---

## 17. Compaction

## 17.1 Purpose

Compaction rewrites stores into a smaller, cleaner form after pruning and consolidation.

---

## 17.2 When to Compact

Compact after:
- major prune
- large merge operation
- store corruption repair
- threshold retuning
- archive batch move

---

## 17.3 Compaction Actions

- remove deleted records
- replace merged groups with merged record
- reorder or rewrite JSONL store
- rebuild tag index
- rebuild recent queue
- refresh counters if needed

---

## 17.4 Compaction Pseudocode

```python
def compact_store(records: list, archive_writer=None) -> list:
    live_records = []

    for record in records:
        if getattr(record, "status", None) == "deleted":
            continue

        if getattr(record, "status", None) == "archived":
            if archive_writer is not None:
                archive_writer.write(record)
            continue

        live_records.append(record)

    return live_records
```

---

## 18. Active Thread Cooling Model

## 18.1 Purpose

Keep the hot path tiny by shrinking or removing stale thread state quickly.

---

## 18.2 Cooling Signals

Thread cools when:
- no loop touched this turn
- topic drift detected
- user intent changes sharply
- thread priority decreases
- many turns pass without mention

---

## 18.3 Cooling Actions

- decrement freshness
- lower priority
- remove inactive loops
- collapse summary
- mark as stale
- delete/reset if expiration exceeded

---

## 18.4 Thread Cooling Pseudocode

```python
def cool_active_thread(thread_state, turns_since_touch: int) -> None:
    if thread_state is None:
        return

    if turns_since_touch <= 0:
        return

    thread_state.priority = max(0.0, thread_state.priority - 0.08 * turns_since_touch)
    thread_state.expires_after_turns = max(0, thread_state.expires_after_turns - turns_since_touch)

    if thread_state.expires_after_turns <= 0 or thread_state.priority < 0.20:
        thread_state.status = "stale"
```

---

## 19. Thread Collapse

## 19.1 Purpose

Convert a hot thread into one compact cold summary before removal.

---

## 19.2 When to Collapse

Collapse when:
- thread ended but may matter later
- many small episodes duplicated thread content
- active loops resolved into a stable state

---

## 19.3 Example

Before:
- open loops: `data_structures_spec`, `prompt_templates_spec`, `retrieval_spec`
- summary: user is building core MindSpark design docs

After collapse:
- episode summary: user completed multiple core MindSpark architecture documents
- active thread reset

---

## 20. Store Limits

Suggested defaults:

| Store | Soft Cap | Hard Cap |
|---|---:|---:|
| user preferences | 128 | 256 |
| user facts | 128 | 256 |
| hot episodes | 256 | 512 |
| response patterns | 128 | 256 |
| active thread open loops | 6 | 8 |
| recent queue | 64 | 128 |

These should be configurable.

---

## 21. Scheduled Maintenance

## 21.1 Routine Maintenance Cadence

Recommended:
- light prune: every turn or every few turns
- routine prune: daily or every N turns
- heavy prune: on threshold breach
- compaction: after heavy prune or large merge batch

---

## 21.2 Turn-End Hygiene

At end of each turn:
- cool untouched thread state
- expire dead loops
- merge obvious duplicates if cheap
- refresh small caches
- optionally update recency queue

---

## 22. Turn-End Pruning Pseudocode

```python
def end_of_turn_memory_hygiene(memory_store, runtime_state, now) -> None:
    cool_and_expire_thread_state(memory_store.active_thread_state, runtime_state)

    prune_expired_open_loops(memory_store.active_thread_state)

    if runtime_state.config.light_prune_each_turn:
        memory_store.remove_obvious_duplicates(limit=runtime_state.config.turn_dedupe_limit)
        memory_store.prune_low_value_recent_noise(limit=runtime_state.config.turn_noise_prune_limit)

    memory_store.refresh_recent_queue()
    memory_store.refresh_indexes_if_needed()
```

---

## 23. Batch Pruning Pipeline

## 23.1 Purpose

Perform deeper cleanup on schedule or under pressure.

---

## 23.2 Batch Pipeline Steps

1. validate records
2. dedupe within each class
3. compute prune scores
4. apply class-specific retention rules
5. archive or delete selected records
6. consolidate similar survivors
7. compact stores
8. rebuild indexes and caches
9. log prune summary

---

## 23.3 Batch Pruning Pseudocode

```python
def run_routine_prune(memory_store, runtime_state, now):
    validate_all_stores(memory_store)

    memory_store.preferences = dedupe_records(memory_store.preferences)
    memory_store.facts = dedupe_records(memory_store.facts)
    memory_store.episodes = dedupe_records(memory_store.episodes)
    memory_store.response_patterns = dedupe_records(memory_store.response_patterns)

    for collection_name in ["preferences", "facts", "episodes", "response_patterns"]:
        collection = getattr(memory_store, collection_name)

        for record in collection:
            record.prune_score = compute_prune_score(record, now, runtime_state)

        collection = apply_class_specific_prune_policy(collection_name, collection, runtime_state)
        collection = consolidate_similar_records(collection)
        collection = compact_store(collection, archive_writer=memory_store.archive_writer_for(collection_name))

        setattr(memory_store, collection_name, collection)

    rebuild_all_indexes(memory_store)
```

---

## 24. Class-Specific Policy Functions

## 24.1 Policy Strategy

Each collection should have a policy that:
- protects key records
- removes low-value tail
- respects soft and hard caps
- uses class-appropriate thresholds

---

## 24.2 Example Preference Policy

```python
def apply_preference_prune_policy(preferences, config):
    survivors = []

    for record in preferences:
        if is_protected_preference(record):
            survivors.append(record)
            continue

        if record.prune_score >= config.preference_delete_threshold:
            record.status = "deleted"
            continue

        if record.prune_score >= config.preference_archive_threshold:
            record.status = "archived"
            continue

        survivors.append(record)

    survivors.sort(key=preference_survival_score, reverse=True)
    return survivors[:config.max_user_preferences]
```

---

## 24.3 Example Episode Policy

```python
def apply_episode_prune_policy(episodes, config):
    survivors = []

    for record in episodes:
        if is_active_thread_related(record):
            survivors.append(record)
            continue

        if record.prune_score >= config.episode_delete_threshold:
            record.status = "deleted"
            continue

        if record.prune_score >= config.episode_archive_threshold:
            record.status = "archived"
            continue

        survivors.append(record)

    survivors.sort(key=episode_survival_score, reverse=True)
    return survivors[:config.max_hot_episodes]
```

---

## 25. Survival Score

## 25.1 Purpose

After pruning, survivors may still exceed soft limits.  
A survival score determines who stays in hot storage.

---

## 25.2 Example Survival Score Formula

```text
survival_score =
  importance * 0.25 +
  confidence * 0.20 +
  quality * 0.15 +
  future_relevance * 0.20 +
  recency * 0.10 +
  reinforcement_strength * 0.10
```

Higher score means more likely to stay.

---

## 25.3 Survival Score Pseudocode

```python
def compute_survival_score(record, now) -> float:
    importance = getattr(record, "importance", 0.5)
    confidence = getattr(record, "confidence", 0.5)
    quality = getattr(record, "quality", 0.5)
    future_relevance = estimate_future_relevance(record)
    recency = compute_recency_score(record, now)
    reinforcement_strength = normalize_count(getattr(record, "times_reinforced", 0), max_value=10)

    score = (
        importance * 0.25 +
        confidence * 0.20 +
        quality * 0.15 +
        future_relevance * 0.20 +
        recency * 0.10 +
        reinforcement_strength * 0.10
    )

    return max(0.0, min(score, 1.0))
```

---

## 26. Future Relevance Estimation

## 26.1 Purpose

Estimate whether a record is likely to matter later.

---

## 26.2 High Future Relevance Signals

- tied to current long-term project
- stable preference
- reusable response pattern
- recurring topic
- known durable constraint
- unresolved issue

### Low Future Relevance Signals
- one-off pleasantry
- stale minor episode
- superseded fact
- weak duplicate

---

## 27. Contradiction Handling

## 27.1 Purpose

When new information conflicts with old memory, the system must resolve or downgrade the older record.

---

## 27.2 Strategies

Possible actions:
- mark older record superseded
- reduce confidence of old record
- archive old record
- merge into new clarified fact
- preserve both only if context-dependent

---

## 27.3 Example

Old preference:
- prefers concise replies

New explicit statement:
- wants more detailed technical explanations for project docs

Resolution:
- keep concise as general preference
- add scoped preference for technical docs
- do not treat as contradiction if scope differs

---

## 28. Validation and Hygiene

## 28.1 Validation During Lifecycle Work

Before merge, archive, or delete:
- validate record type
- validate required fields
- validate timestamps
- validate score ranges
- normalize tags
- repair malformed summaries if cheap

---

## 28.2 Hygiene Goals

Memory hygiene should:
- remove malformed records
- collapse duplicates
- trim oversized summaries
- repair missing metadata if possible
- keep stores inspection-friendly

---

## 29. Suggested Runtime Config

```yaml
light_prune_each_turn: true
turn_dedupe_limit: 12
turn_noise_prune_limit: 8

max_user_preferences: 256
max_user_facts: 256
max_hot_episodes: 512
max_response_patterns: 256
max_open_loops: 8

preference_archive_threshold: 0.72
preference_delete_threshold: 0.86

fact_archive_threshold: 0.74
fact_delete_threshold: 0.88

episode_archive_threshold: 0.68
episode_delete_threshold: 0.82

pattern_archive_threshold: 0.72
pattern_delete_threshold: 0.86

active_thread_stale_priority: 0.20
routine_prune_interval_turns: 50
heavy_prune_trigger_store_pressure: 0.85
```

These are starting values, not final truths.

---

## 30. Logging and Observability

## 30.1 Recommended Prune Log Fields

- timestamp
- prune mode
- records scanned
- records merged
- records archived
- records deleted
- store sizes before/after
- compaction result
- index rebuild result

---

## 30.2 Example Prune Summary

```json
{
  "timestamp": "2026-03-30T19:10:00Z",
  "mode": "routine_prune",
  "preferences_before": 142,
  "preferences_after": 128,
  "episodes_before": 601,
  "episodes_after": 512,
  "merged_records": 23,
  "archived_records": 41,
  "deleted_records": 67
}
```

---

## 31. Failure Modes

| Failure Mode | Cause | Fix |
|---|---|---|
| memory store keeps growing | thresholds too weak, merge too weak | raise prune thresholds and improve consolidation |
| useful memories vanish | thresholds too aggressive | lower delete thresholds and improve protection logic |
| duplicates keep resurfacing | dedupe too shallow | improve similarity clustering and merge rules |
| thread state lingers forever | cooling too weak | reduce expiration window and lower stale priority threshold |
| retrieval quality drops over time | stale noise dominating store | run heavy prune and compact aggressively |
| archives become junk drawer | archive policy too lax | archive less, delete more low-value noise |

---

## 32. Testing Strategy

## 32.1 Core Tests

- does explicit preference survive routine prune?
- does weak inferred preference get deleted eventually?
- do similar episodes consolidate correctly?
- does stale thread state cool and collapse?
- do obsolete facts get archived or deleted?
- do response patterns reinforce and weak ones disappear?
- do store sizes remain within configured caps?

---

## 32.2 Scenario Tests

### Ongoing Project Scenario
- many related episodes over time
- should consolidate into durable facts, thread state, and a few valuable episodes

### Emotional Support Scenario
- emotionally meaningful episode should survive longer than trivial pleasantries

### Long Idle Gap Scenario
- active thread state should decay
- only durable memory should remain strongly retrievable

### Contradiction Scenario
- old fact should be superseded correctly

---

## 33. Recommended Implementation Order

1. implement recency decay
2. implement reinforcement updates
3. implement duplicate detection
4. implement merge rules
5. implement active thread cooling
6. implement class-specific prune scoring
7. implement archive/delete policy
8. implement compaction
9. implement routine prune scheduler
10. tune thresholds on real workloads

---

## 34. Recommended Next Spec

After this document, the clean next spec is:

1. **Runtime Config Spec**
2. **MVP Build Order Checklist**
3. **Latency and Token Budget Tuning Guide**
4. **Evaluation and Benchmarking Spec**
5. **Storage and File Format Spec**

---

## 35. Final Guiding Principle

MindSpark: ThoughtForge should not remember everything.

It should remember:
- what stays useful
- what shapes future conversation
- what reinforces continuity
- what improves generation quality

And it should let the rest burn away cleanly.

That is how memory remains light enough, sharp enough, and disciplined enough for tiny models on weak local hardware.
