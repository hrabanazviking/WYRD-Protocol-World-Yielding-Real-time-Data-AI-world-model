# Retrieval and Scoring Spec
## MindSpark: ThoughtForge
### Lean Memory Retrieval, Ranking, and Quality Scoring for Tiny Local Language Models

**Document Type:** Technical Specification  
**Status:** Draft v1  
**Project:** MindSpark: ThoughtForge  
**Scope:** Retrieval pipelines, ranking formulas, scoring heuristics, cue construction, deduplication, thresholding, and evaluation flow for a lean conversational agent optimized for tiny local language models

---

## 1. Purpose

This document defines the retrieval and scoring system for **MindSpark: ThoughtForge**, a lean conversation engine built to help very small language models perform far above their size class through:

- compact memory retrieval
- tiny high-value activation bundles
- lightweight ranking heuristics
- salvage-first scoring
- strict thresholding
- bounded runtime work

The retrieval system determines **what the model should remember right now**.

The scoring system determines:

- which memories matter most
- which candidates are worth salvaging
- which fragments should be kept
- whether a final reply is good enough
- what should be written back into memory

This spec is designed for:
- weak hardware
- low RAM usage
- low token budgets
- predictable latency
- simple tuning

---

## 2. Design Principles

## 2.1 Retrieve Less, Retrieve Better
The system should retrieve only a tiny number of records, but make them highly relevant.

Default target:
- `3` records
Hard maximum:
- `5` records

---

## 2.2 Scoring Must Be Cheap
Prefer:
- rule-based heuristics
- shallow numeric features
- cached metadata
- lightweight embeddings if affordable

Avoid:
- heavyweight reranking models
- long cross-encoder passes
- expensive multi-stage retrieval

---

## 2.3 Cues Over Dumps
Retrieved memory should become compact cues, not long summaries or raw transcripts.

---

## 2.4 Salvage Over Rejection
Scoring should identify useful parts of imperfect outputs rather than discarding whole candidates too early.

---

## 2.5 Bounded Everything
Every retrieval and scoring stage must have hard caps:
- candidate pool size
- retrieved record count
- kept fragment count
- scoring passes
- retry count

This keeps runtime predictable.

---

## 3. System Overview

The retrieval and scoring stack has five major layers:

1. **Record Discovery**
2. **Memory Ranking**
3. **Cue Construction**
4. **Output Scoring**
5. **Writeback Selection**

Flow:

```text
Input Sketch
  ↓
Discovery Pool
  ↓
Memory Scoring
  ↓
Top-K Retrieved Records
  ↓
Cue Compression
  ↓
Generation
  ↓
Candidate / Fragment / Final Scoring
  ↓
Writeback Scoring
```

---

## 4. Retrieval Targets

The system may retrieve from these memory classes:

- `personality_core`
- `user_preference`
- `user_fact`
- `episode`
- `response_pattern`
- `active_thread_state`

Not all classes should be equally weighted in all turns.

---

## 5. Retrieval Goals by Memory Class

## 5.1 Personality Core
Goal:
- stabilize style
- stabilize behavioral tone
- enforce avoid rules

Retrieval style:
- usually always available implicitly
- do not inject large portions into prompts

---

## 5.2 User Preference
Goal:
- adapt response style to the user
- reinforce consistency
- avoid known dislikes

High priority for:
- tone-sensitive tasks
- support tasks
- editing tasks
- conversational tasks

---

## 5.3 User Fact
Goal:
- preserve continuity around durable user context
- ground the reply in known projects, goals, or constraints

High priority for:
- project discussions
- follow-up design work
- recurring technical topics

---

## 5.4 Episodic Memory
Goal:
- preserve recent continuity
- retain emotional or technical thread context
- support turn-to-turn coherence

High priority for:
- ongoing topics
- multi-turn support
- active debugging/design loops

---

## 5.5 Response Pattern
Goal:
- reuse compact successful response structures
- improve weak-model phrasing stability

High priority for:
- repeat task shapes
- supportive replies
- technical writing modes
- editing/refinement

---

## 5.6 Active Thread State
Goal:
- represent the current working thread
- keep the model synchronized with what is still live

Very high priority when present.  
Must stay tiny.

---

## 6. Retrieval Pipeline

## 6.1 Stage 1: Discovery Pool Construction

Build a candidate pool using:
- tag lookup
- active thread state
- recent records
- optional lexical match
- optional embedding neighbor lookup

This pool should be larger than top-k, but still bounded.

### Suggested discovery limits
- tag hits: `<= 24`
- recent records: `<= 32`
- active thread records: `<= 8`
- optional embedding hits: `<= 16`

---

## 6.2 Stage 2: Scoring

Each candidate record receives a numeric retrieval score.

---

## 6.3 Stage 3: Deduplication

Collapse near-duplicate records before final top-k selection.

---

## 6.4 Stage 4: Top-K Selection

Keep only the highest-value records:
- default: `3`
- hard cap: `5`

---

## 6.5 Stage 5: Cue Construction

Convert selected records into compact prompt-ready cues.

---

## 7. Discovery Algorithms

## 7.1 Tag-Based Discovery

Use:
- `input_sketch.memory_triggers`
- topic labels
- tone labels
- thread tags
- candidate mode hints

### Pseudocode

```python
def discover_by_tags(input_sketch: InputSketch, memory_store: MemoryStore) -> list[BaseRecord]:
    query_tags = set()
    query_tags.update(input_sketch.memory_triggers)
    query_tags.add(input_sketch.topic)
    query_tags.update(input_sketch.tone_in)

    if memory_store.active_thread_state:
        query_tags.update(memory_store.active_thread_state.tags[:4])

    return memory_store.lookup_by_tags(sorted(query_tags))
```

---

## 7.2 Recent-Record Discovery

Recent records help recover continuity when tags are sparse.

### Pseudocode

```python
def discover_recent(memory_store: MemoryStore, limit: int = 32) -> list[BaseRecord]:
    return memory_store.get_recent_records(limit=limit)
```

---

## 7.3 Active Thread Discovery

Always include active thread state if it exists and is still valid.

### Pseudocode

```python
def discover_active_thread(memory_store: MemoryStore) -> list[BaseRecord]:
    thread = memory_store.active_thread_state
    if not thread:
        return []
    if thread.status != "active":
        return []
    return [thread]
```

---

## 7.4 Optional Embedding Discovery

Only use if local embedding retrieval is cheap enough for the target hardware.

### Pseudocode

```python
def discover_by_embedding(input_sketch: InputSketch, memory_store: MemoryStore, limit: int = 16) -> list[BaseRecord]:
    if not memory_store.embedding_index_enabled:
        return []
    query_vector = memory_store.embed_query(input_sketch.topic)
    return memory_store.lookup_nearest(query_vector, limit=limit)
```

---

## 8. Retrieval Scoring Dimensions

Every record may be scored using these dimensions:

- `semantic_similarity`
- `tone_similarity`
- `preference_relevance`
- `recency`
- `importance`
- `thread_boost`
- `record_type_bias`

Not every dimension applies equally to every record type.

---

## 9. Base Retrieval Score Formula

Recommended base formula:

```text
retrieval_score =
  semantic_similarity * 0.35 +
  tone_similarity * 0.20 +
  preference_relevance * 0.20 +
  recency * 0.10 +
  importance * 0.15
```

This is a stable starting point, not a law.

---

## 10. Retrieval Score Details

## 10.1 Semantic Similarity

Measures how closely the record matches the current topic and intent.

Sources:
- tag overlap
- lexical overlap
- optional embedding proximity
- category match

### Range
`0.0 - 1.0`

---

## 10.2 Tone Similarity

Measures whether the record’s emotional or stylistic context fits the current turn.

Use for:
- support tasks
- tone-sensitive editing
- warm vs direct style matching

### Range
`0.0 - 1.0`

---

## 10.3 Preference Relevance

Measures whether the record influences how the response should be shaped.

Highest for:
- user preferences
- response patterns
- thread state
- user facts with active constraints

### Range
`0.0 - 1.0`

---

## 10.4 Recency

Measures how fresh the record is.

Use decayed recency rather than binary freshness.

### Range
`0.0 - 1.0`

---

## 10.5 Importance

Long-lived weighting stored on the record.

Explicit user-stated preferences or durable facts should often score high here.

### Range
`0.0 - 1.0`

---

## 10.6 Thread Boost

Optional additive boost when the record is clearly part of the current live thread.

### Recommended range
`0.00 - 0.15`

---

## 10.7 Record Type Bias

Small bias term to favor some classes depending on task mode.

Example:
- technical mode may bias toward facts and thread state
- support mode may bias toward preferences and episodes

### Recommended range
`-0.10 to +0.10`

---

## 11. Retrieval Scoring by Record Type

## 11.1 User Preference Scoring

Recommended emphasis:
- preference relevance
- semantic similarity
- importance

Suggested formula:

```text
score =
  semantic_similarity * 0.25 +
  tone_similarity * 0.20 +
  preference_relevance * 0.30 +
  recency * 0.05 +
  importance * 0.20
```

---

## 11.2 User Fact Scoring

Recommended emphasis:
- semantic similarity
- importance
- thread relevance

Suggested formula:

```text
score =
  semantic_similarity * 0.40 +
  tone_similarity * 0.05 +
  preference_relevance * 0.15 +
  recency * 0.10 +
  importance * 0.20 +
  thread_boost * 0.10
```

---

## 11.3 Episode Scoring

Recommended emphasis:
- semantic similarity
- tone similarity
- recency

Suggested formula:

```text
score =
  semantic_similarity * 0.30 +
  tone_similarity * 0.25 +
  preference_relevance * 0.10 +
  recency * 0.20 +
  importance * 0.15
```

---

## 11.4 Response Pattern Scoring

Recommended emphasis:
- preference relevance
- semantic similarity
- historical success quality

Suggested formula:

```text
score =
  semantic_similarity * 0.25 +
  tone_similarity * 0.15 +
  preference_relevance * 0.30 +
  recency * 0.05 +
  importance * 0.10 +
  pattern_quality * 0.15
```

---

## 11.5 Active Thread State Scoring

Recommended emphasis:
- thread relevance
- semantic similarity
- priority

Suggested formula:

```text
score =
  semantic_similarity * 0.30 +
  tone_similarity * 0.10 +
  preference_relevance * 0.15 +
  recency * 0.10 +
  importance * 0.05 +
  thread_boost * 0.15 +
  priority * 0.15
```

---

## 12. Retrieval Score Object

Standard score object shape:

```json
{
  "record_id": "usr_204",
  "record_type": "user_preference",
  "semantic_similarity": 0.89,
  "tone_similarity": 0.82,
  "preference_relevance": 0.95,
  "recency": 0.71,
  "importance": 0.90,
  "thread_boost": 0.10,
  "record_type_bias": 0.04,
  "final_score": 0.90
}
```

---

## 13. Retrieval Scoring Pseudocode

```python
def score_memory_record(record: BaseRecord, input_sketch: InputSketch, runtime_state: RuntimeState) -> dict:
    semantic_similarity = compute_semantic_similarity(record, input_sketch)
    tone_similarity = compute_tone_similarity(record, input_sketch)
    preference_relevance = compute_preference_relevance(record, input_sketch)
    recency = compute_recency_score(record, runtime_state.clock)
    importance = getattr(record, "importance", 0.5)
    thread_boost = compute_thread_boost(record, runtime_state.active_thread_state)
    record_type_bias = compute_record_type_bias(record.type, input_sketch.response_mode)

    base = select_record_type_formula(record.type)

    final_score = base(
        semantic_similarity=semantic_similarity,
        tone_similarity=tone_similarity,
        preference_relevance=preference_relevance,
        recency=recency,
        importance=importance,
        thread_boost=thread_boost,
        record_type_bias=record_type_bias,
        record=record,
    )

    return {
        "record_id": record.id,
        "record_type": record.type,
        "semantic_similarity": semantic_similarity,
        "tone_similarity": tone_similarity,
        "preference_relevance": preference_relevance,
        "recency": recency,
        "importance": importance,
        "thread_boost": thread_boost,
        "record_type_bias": record_type_bias,
        "final_score": max(0.0, min(final_score, 1.0)),
    }
```

---

## 14. Retrieval Thresholding

## 14.1 Minimum Retrieval Score

Suggested default:
```yaml
min_memory_score: 0.45
```

Records below threshold should normally be dropped.

---

## 14.2 Dynamic Threshold Adjustment

Raise threshold slightly when:
- active thread state is strong
- retrieval pool is crowded
- task is simple and specific

Lower threshold slightly when:
- very sparse memory store
- cold start
- ambiguous query with little matching context

---

## 15. Deduplication Rules

## 15.1 Purpose

Prevent near-identical records from wasting slots in top-k.

---

## 15.2 Duplicate Signals

Records are likely duplicates if they share:
- very similar tags
- same category
- same linked topic
- same summary meaning
- high semantic overlap

---

## 15.3 Preference Deduplication

Prefer:
1. explicit user-stated over inferred
2. higher confidence over lower confidence
3. newer confirmation over older
4. compact summary over verbose one

---

## 15.4 Episode Deduplication

Prefer:
1. higher importance
2. better quality summary
3. fresher record when otherwise similar

---

## 15.5 Deduplication Pseudocode

```python
def dedupe_records(records: list[BaseRecord]) -> list[BaseRecord]:
    deduped = []
    seen_groups = []

    for record in records:
        matched_group = None
        for group in seen_groups:
            if records_are_duplicates(record, group[0]):
                matched_group = group
                break

        if matched_group is None:
            seen_groups.append([record])
        else:
            matched_group.append(record)

    for group in seen_groups:
        deduped.append(select_best_duplicate(group))

    return deduped
```

---

## 16. Cue Construction

## 16.1 Purpose

Convert retrieved records into prompt-efficient cue strings.

This is where retrieval becomes generation-ready.

---

## 16.2 Cue Rules

Cues should be:
- short
- direct
- prompt-friendly
- semantically dense
- low-noise

Avoid:
- narrative summaries
- timestamps
- unnecessary qualifiers
- metadata dumps

---

## 16.3 Cue Length Target

Recommended:
- `5–12 words`

Maximum:
- `18 words`

---

## 16.4 Cue Examples

### Good
- prefers direct low-fluff responses
- current work centers on lean small-model AI
- brief validation plus one structural insight works well
- active thread: building core project docs

### Bad
- The user has repeatedly shown in many conversations that they tend to favor responses that are direct and not padded.

---

## 16.5 Cue Construction Pseudocode

```python
def build_memory_cue(record: BaseRecord) -> str:
    if record.type == "user_preference":
        return compress_preference_summary(record.summary)

    if record.type == "user_fact":
        return compress_fact_summary(record.summary)

    if record.type == "episode":
        return compress_episode_summary(record.summary)

    if record.type == "response_pattern":
        return compress_pattern_summary(record.summary)

    if record.type == "active_thread_state":
        return f"active thread: {compress_thread_summary(record.summary)}"

    return compress_generic_summary(record.summary)
```

---

## 17. Activation Bundle Construction

## 17.1 Purpose

Construct the small memory object passed into cognition and prompt building.

---

## 17.2 Selection Rules

Prefer mix diversity across:
- one preference
- one thread/fact
- one pattern/episode

Do not fill all slots with the same memory class unless clearly justified.

---

## 17.3 Activation Bundle Pseudocode

```python
def build_activation_bundle(
    scored_records: list[tuple[BaseRecord, dict]],
    personality_core_id: str,
    max_records: int = 5,
) -> MemoryActivationBundle:
    selected = select_diverse_top_records(scored_records, max_records=max_records)

    activated_records = []
    for record, score in selected:
        activated_records.append({
            "id": record.id,
            "type": record.type,
            "score": score["final_score"],
            "cue": build_memory_cue(record),
        })

    return MemoryActivationBundle(
        personality_core_id=personality_core_id,
        activated_records=activated_records,
    )
```

---

## 18. Candidate Scoring

## 18.1 Purpose

Score first-pass candidate outputs to estimate which contain the most salvageable value.

Candidates are not all-or-nothing.

---

## 18.2 Candidate Score Dimensions

- `relevance`
- `clarity`
- `coherence`
- `personality_fit`
- `specificity`
- `genericness_penalty`

Optional:
- `format_fit`
- `goal_fit`

---

## 18.3 Candidate Score Formula

Suggested starting formula:

```text
candidate_score =
  relevance * 0.28 +
  clarity * 0.18 +
  coherence * 0.16 +
  personality_fit * 0.16 +
  specificity * 0.14 +
  goal_fit * 0.08 -
  genericness_penalty * 0.10
```

---

## 18.4 Candidate Score Object

```json
{
  "relevance": 0.86,
  "clarity": 0.80,
  "coherence": 0.78,
  "personality_fit": 0.77,
  "specificity": 0.74,
  "goal_fit": 0.79,
  "genericness_penalty": 0.11,
  "final_score": 0.79
}
```

---

## 18.5 Candidate Scoring Pseudocode

```python
def score_candidate(
    text: str,
    input_sketch: InputSketch,
    scaffold: CognitionScaffold,
    runtime_state: RuntimeState,
) -> dict:
    relevance = heuristic_relevance(text, input_sketch)
    clarity = heuristic_clarity(text)
    coherence = heuristic_coherence(text)
    personality_fit = heuristic_personality_fit(text, runtime_state.personality_core)
    specificity = heuristic_specificity(text)
    goal_fit = heuristic_goal_fit(text, scaffold)
    genericness_penalty = heuristic_genericness(text)

    final_score = (
        relevance * 0.28 +
        clarity * 0.18 +
        coherence * 0.16 +
        personality_fit * 0.16 +
        specificity * 0.14 +
        goal_fit * 0.08 -
        genericness_penalty * 0.10
    )

    return {
        "relevance": relevance,
        "clarity": clarity,
        "coherence": coherence,
        "personality_fit": personality_fit,
        "specificity": specificity,
        "goal_fit": goal_fit,
        "genericness_penalty": genericness_penalty,
        "final_score": max(0.0, min(final_score, 1.0)),
    }
```

---

## 19. Fragment Scoring

## 19.1 Purpose

Score extracted fragments so the best pieces can survive even if the original candidate is mixed quality.

---

## 19.2 Fragment Score Dimensions

- `relevance`
- `clarity`
- `specificity`
- `usefulness`
- `personality_fit`
- `genericness_penalty`

---

## 19.3 Fragment Score Formula

Suggested formula:

```text
fragment_score =
  relevance * 0.30 +
  clarity * 0.18 +
  specificity * 0.18 +
  usefulness * 0.20 +
  personality_fit * 0.14 -
  genericness_penalty * 0.10
```

---

## 19.4 Fragment Score Object

```json
{
  "relevance": 0.90,
  "clarity": 0.89,
  "specificity": 0.85,
  "usefulness": 0.88,
  "personality_fit": 0.78,
  "genericness_penalty": 0.04,
  "final_score": 0.86
}
```

---

## 19.5 Fragment Keep Threshold

Suggested default:
```yaml
min_fragment_score: 0.54
```

Higher threshold:
- technical docs
- editing tasks
- highly specific work

Lower threshold:
- brainstorming
- light chat
- emotionally sensitive tasks where imperfect but sincere phrasing may still help

---

## 20. Final Response Scoring

## 20.1 Purpose

Determine whether the refined response is strong enough to return without another pass.

---

## 20.2 Final Score Dimensions

- `relevance`
- `clarity`
- `coherence`
- `personality_fit`
- `usefulness`
- `goal_fit`
- `genericness_penalty`

---

## 20.3 Final Score Formula

Suggested formula:

```text
final_response_score =
  relevance * 0.24 +
  clarity * 0.18 +
  coherence * 0.18 +
  personality_fit * 0.14 +
  usefulness * 0.16 +
  goal_fit * 0.10 -
  genericness_penalty * 0.10
```

---

## 20.4 Final Score Threshold

Suggested default:
```yaml
min_final_score: 0.68
```

Raise threshold for:
- polished technical docs
- final copywriting
- formal outputs

Lower slightly for:
- casual brainstorming
- low-power degraded mode
- conversational support tasks where warmth matters more than polish

---

## 20.5 Final Response Score Object

```json
{
  "relevance": 0.93,
  "clarity": 0.91,
  "coherence": 0.90,
  "personality_fit": 0.82,
  "usefulness": 0.89,
  "goal_fit": 0.87,
  "genericness_penalty": 0.04,
  "final_score": 0.89
}
```

---

## 21. Genericness Scoring

## 21.1 Purpose

Penalize output that sounds broad, empty, templated, or low-information.

This is critical for tiny models.

---

## 21.2 Signals of Genericness

- “a lot of people”
- “it’s normal”
- “everything will be okay”
- “as an AI”
- vague moralizing
- repeated abstractions
- obvious filler
- padded disclaimers
- broad universal claims with no grounding

---

## 21.3 Genericness Heuristic Pseudocode

```python
def heuristic_genericness(text: str) -> float:
    penalty = 0.0
    lowered = text.lower()

    generic_phrases = [
        "a lot of people",
        "it's normal",
        "as an ai",
        "everything will be okay",
        "in today's world",
        "many individuals",
    ]

    for phrase in generic_phrases:
        if phrase in lowered:
            penalty += 0.15

    if estimate_specific_noun_density(text) < 0.08:
        penalty += 0.10

    if estimate_repetition(text) > 0.20:
        penalty += 0.10

    if estimate_empty_modifier_density(text) > 0.18:
        penalty += 0.08

    return min(penalty, 1.0)
```

---

## 22. Personality Fit Scoring

## 22.1 Purpose

Ensure generated text stays aligned with the desired behavioral identity.

---

## 22.2 Positive Signals

- directness
- natural phrasing
- low fluff
- grounded tone
- stable warmth
- task-appropriate brevity

---

## 22.3 Negative Signals

- preachiness
- corporate tone
- robotic disclaimers
- excessive hedging
- overexplaining
- abrupt tone mismatch

---

## 22.4 Personality Fit Heuristic Pseudocode

```python
def heuristic_personality_fit(text: str, personality_core: PersonalityCoreRecord) -> float:
    score = 0.5

    if is_direct(text):
        score += 0.15
    if is_low_fluff(text):
        score += 0.15
    if sounds_natural(text):
        score += 0.10
    if tone_matches_personality(text, personality_core):
        score += 0.10
    if violates_avoid_list(text, personality_core.avoid):
        score -= 0.25

    return max(0.0, min(score, 1.0))
```

---

## 23. Relevance Scoring

## 23.1 Purpose

Measure how directly the content addresses the current request.

---

## 23.2 Signals

- explicit topic alignment
- task completion evidence
- term overlap
- structural match to requested output
- requested action actually performed

---

## 23.3 Relevance Heuristic Pseudocode

```python
def heuristic_relevance(text: str, input_sketch: InputSketch) -> float:
    score = 0.0

    if text_mentions_topic(text, input_sketch.topic):
        score += 0.35

    if matches_response_mode(text, input_sketch.response_mode):
        score += 0.20

    if addresses_intent(text, input_sketch.intent):
        score += 0.25

    if includes_request_specific_content(text, input_sketch):
        score += 0.20

    return min(score, 1.0)
```

---

## 24. Usefulness Scoring

## 24.1 Purpose

Estimate practical conversational value beyond mere correctness.

Usefulness often means:
- helpful insight
- clear next step
- stable framing
- actionable content
- compact implementation value

---

## 24.2 Usefulness Heuristic Pseudocode

```python
def heuristic_usefulness(text: str, input_sketch: InputSketch, scaffold: CognitionScaffold) -> float:
    score = 0.0

    if offers_meaningful_next_step(text):
        score += 0.25
    if provides_specific useful information(text):
        score += 0.35
    if aligns_with_goal(text, scaffold.goal):
        score += 0.25
    if avoids_empty filler(text):
        score += 0.15

    return min(score, 1.0)
```

---

## 24.3 Note

Implementation should rename helper functions into valid Python identifiers.  
The pseudocode here is conceptual.

---

## 25. Clarity and Coherence Scoring

## 25.1 Clarity Signals

- short controlled sentences
- low ambiguity
- low grammar noise
- low pronoun confusion
- readable structure

## 25.2 Coherence Signals

- logical progression
- no contradictions
- no abrupt shift
- stable local flow

These can remain lightweight heuristic scores.

---

## 26. Writeback Scoring

## 26.1 Purpose

Decide what deserves memory persistence after the turn.

Not everything should be remembered.

---

## 26.2 Writeback Targets

- durable preference
- durable fact
- compact episode
- thread update
- response pattern reinforcement

---

## 26.3 Writeback Scoring Dimensions

- `durability`
- `novelty`
- `confidence`
- `importance`
- `future_relevance`

---

## 26.4 Preference Writeback Formula

Suggested formula:

```text
preference_writeback_score =
  durability * 0.30 +
  novelty * 0.20 +
  confidence * 0.25 +
  importance * 0.10 +
  future_relevance * 0.15
```

---

## 26.5 Episode Writeback Formula

Suggested formula:

```text
episode_writeback_score =
  novelty * 0.20 +
  confidence * 0.15 +
  importance * 0.25 +
  future_relevance * 0.20 +
  thread_relevance * 0.20
```

---

## 26.6 Pattern Learning Score

Suggested formula:

```text
pattern_learning_score =
  final_response_quality * 0.45 +
  pattern_reusability * 0.30 +
  future_relevance * 0.25
```

---

## 27. Writeback Thresholds

Suggested defaults:

```yaml
min_preference_writeback_score: 0.72
min_episode_writeback_score: 0.58
min_pattern_learning_score: 0.78
```

---

## 28. Quality Tiers

## 28.1 Purpose

Classify outputs and records into tiers for easier decision logic.

---

## 28.2 Suggested Tiers

| Score Range | Tier |
|---|---|
| `0.85 - 1.00` | excellent |
| `0.70 - 0.84` | strong |
| `0.55 - 0.69` | usable |
| `0.40 - 0.54` | weak |
| `< 0.40` | reject |

---

## 28.3 Usage

- retrieve only `usable+`
- keep fragments that are `usable+`
- return final outputs that are `strong+`
- learn patterns mainly from `strong+` and `excellent`

---

## 29. Top-K Diversity Selection

## 29.1 Purpose

Prevent top-k retrieval from collapsing into a single memory type.

---

## 29.2 Diversity Rules

Prefer selected sets that include:
- at least one preference or personality cue
- at least one fact/thread/episode continuity cue
- at least one pattern cue if relevant

---

## 29.3 Diversity Pseudocode

```python
def select_diverse_top_records(
    scored_records: list[tuple[BaseRecord, dict]],
    max_records: int = 5,
) -> list[tuple[BaseRecord, dict]]:
    selected = []
    used_types = set()

    for record, score in scored_records:
        if len(selected) >= max_records:
            break

        if record.type not in used_types:
            selected.append((record, score))
            used_types.add(record.type)

    for record, score in scored_records:
        if len(selected) >= max_records:
            break
        if (record, score) not in selected:
            selected.append((record, score))

    return selected
```

---

## 30. Configurable Parameters

Suggested defaults:

```yaml
min_memory_score: 0.45
max_retrieved_records: 5
preferred_retrieved_records: 3

min_candidate_score: 0.40
min_fragment_score: 0.54
min_final_score: 0.68

min_preference_writeback_score: 0.72
min_episode_writeback_score: 0.58
min_pattern_learning_score: 0.78

max_discovery_tag_hits: 24
max_discovery_recent_hits: 32
max_discovery_embedding_hits: 16
max_kept_fragments: 8
```

---

## 31. End-to-End Retrieval Pseudocode

```python
def retrieve_and_rank(
    input_sketch: InputSketch,
    memory_store: MemoryStore,
    runtime_state: RuntimeState,
) -> MemoryActivationBundle:
    pool = []
    pool.extend(discover_active_thread(memory_store))
    pool.extend(discover_by_tags(input_sketch, memory_store))
    pool.extend(discover_recent(memory_store, limit=runtime_state.config.max_discovery_recent_hits))

    if runtime_state.config.embedding_retrieval_enabled:
        pool.extend(discover_by_embedding(
            input_sketch,
            memory_store,
            limit=runtime_state.config.max_discovery_embedding_hits,
        ))

    pool = dedupe_records(pool)

    scored = []
    for record in pool:
        score = score_memory_record(record, input_sketch, runtime_state)
        if score["final_score"] >= runtime_state.config.min_memory_score:
            scored.append((record, score))

    scored.sort(key=lambda item: item[1]["final_score"], reverse=True)

    return build_activation_bundle(
        scored_records=scored,
        personality_core_id=memory_store.personality_core.id,
        max_records=runtime_state.config.max_retrieved_records,
    )
```

---

## 32. Testing Retrieval and Scoring

## 32.1 Retrieval Tests

- does a project-specific request retrieve the right fact?
- does a tone-sensitive request retrieve the right preference?
- does active thread state outrank stale episodic memory?
- do duplicates collapse correctly?
- does top-k remain diverse?

---

## 32.2 Scoring Tests

- does generic filler receive a penalty?
- does a direct specific sentence score higher than a vague one?
- do high-quality fragments survive mixed candidates?
- do strong final responses pass threshold?
- do weak final responses fail threshold?

---

## 32.3 Writeback Tests

- does trivial chat avoid durable writeback?
- do durable preferences cross threshold only with strong evidence?
- do strong reusable patterns get reinforced?

---

## 33. Failure Modes

| Failure Mode | Cause | Fix |
|---|---|---|
| wrong memories retrieved | weak discovery tags or poor scoring weights | improve tag extraction and retune weights |
| too many similar memories | dedupe too weak | tighten duplicate detection |
| generic candidates survive | genericness penalty too low | raise penalty weight |
| useful fragments discarded | fragment threshold too high | lower fragment threshold slightly |
| final replies too strict or too weak | min_final_score mis-set | tune per response mode |
| over-remembering noise | writeback thresholds too low | raise writeback thresholds |

---

## 34. Recommended Implementation Order

1. implement discovery pool construction
2. implement base retrieval scoring
3. implement deduplication
4. implement cue construction
5. implement candidate scoring
6. implement fragment scoring
7. implement final response scoring
8. implement writeback scoring
9. add type-specific formulas
10. tune thresholds on real workloads

---

## 35. Recommended Next Spec

After this document, the clean next spec is:

1. **Memory Lifecycle and Pruning Spec**
2. **Runtime Config Spec**
3. **MVP Build Order Checklist**
4. **Latency and Token Budget Tuning Guide**
5. **Evaluation and Benchmarking Spec**

---

## 36. Final Guiding Principle

Retrieval and scoring in MindSpark: ThoughtForge should not behave like a bloated enterprise memory stack.

It should:
- discover only what might matter
- rank it cheaply
- compress it into tiny cues
- salvage useful output aggressively
- reject only when necessary
- remember only what will matter later

That is how tiny models stay fast, coherent, and surprisingly capable on weak local hardware.
