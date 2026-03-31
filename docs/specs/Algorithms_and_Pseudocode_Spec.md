# Algorithms and Pseudocode Spec
## MindSpark: ThoughtForge
### Lean Runtime Logic for Guided Memory Conversation Systems

**Document Type:** Technical Specification  
**Status:** Draft v1  
**Project:** MindSpark: ThoughtForge  
**Scope:** Core algorithms, runtime flow, and pseudocode for a lean conversational agent optimized for tiny local language models

---

## 1. Purpose

This document defines the algorithmic behavior of **MindSpark: ThoughtForge**, a lean conversation engine designed to help very small language models produce strong conversational output through:

- guided memory retrieval
- lightweight cognition scaffolds
- multi-candidate micro-generation
- salvage-based refinement
- compact memory writeback
- hard efficiency limits

This spec is designed to translate directly into implementation modules.

It assumes the data structures defined in:

- `Data Structures Spec.md`

and the architecture defined in:

- `ultra_lean_personality_agent_spec.md`

---

## 2. Design Goals

The algorithms in this system must:

- remain small and fast
- avoid long internal reasoning
- avoid large prompt assembly
- operate well on weak hardware
- improve weak model outputs rather than simply rejecting them
- preserve personality consistency
- use bounded loops and bounded retrieval

The system should do the least work necessary to produce a strong reply.

---

## 3. Runtime Modules

Recommended module mapping:

```text
src/
├── input_compression.py
├── retrieval.py
├── cognition.py
├── generation.py
├── salvage.py
├── scoring.py
├── composer.py
├── writeback.py
├── pruning.py
└── runtime.py
```

---

## 4. End-to-End Turn Pipeline

## 4.1 High-Level Flow

```text
receive_input
  → compress_input
  → retrieve_memories
  → build_cognition_scaffold
  → generate_candidates
  → extract_fragments
  → score_fragments
  → compose_refined_reply
  → evaluate_reply
  → finalize_or_retry
  → create_writeback
  → persist_updates
  → return_response
```

---

## 4.2 Main Turn Algorithm

```python
def process_turn(user_text: str, runtime_state: RuntimeState) -> FinalResponseRecord:
    turn = create_turn_state(user_text)

    input_sketch = compress_input(user_text, runtime_state)
    turn.input_sketch = input_sketch

    memory_bundle = retrieve_memories(input_sketch, runtime_state.memory_store)
    turn.memory_activation_bundle = memory_bundle

    scaffold = build_cognition_scaffold(input_sketch, memory_bundle, runtime_state)
    turn.cognition_scaffold = scaffold

    candidates = generate_candidates(user_text, input_sketch, memory_bundle, scaffold, runtime_state)
    turn.candidates = candidates

    fragments = extract_and_score_fragments(candidates, input_sketch, memory_bundle, scaffold, runtime_state)
    turn.fragments = fragments

    final_response = compose_and_refine_response(
        user_text=user_text,
        input_sketch=input_sketch,
        memory_bundle=memory_bundle,
        scaffold=scaffold,
        fragments=fragments,
        runtime_state=runtime_state,
    )

    if not passes_quality_threshold(final_response, input_sketch, scaffold, runtime_state):
        final_response = fallback_repair_response(
            user_text=user_text,
            input_sketch=input_sketch,
            memory_bundle=memory_bundle,
            scaffold=scaffold,
            runtime_state=runtime_state,
        )

    turn.final_response_id = final_response.id

    writeback = create_writeback_record(
        user_text=user_text,
        input_sketch=input_sketch,
        memory_bundle=memory_bundle,
        final_response=final_response,
        runtime_state=runtime_state,
    )
    turn.writeback_id = writeback.id

    persist_writeback(writeback, runtime_state.memory_store)
    persist_turn_trace(turn, runtime_state)

    return final_response
```

---

## 5. Input Compression Algorithm

## 5.1 Purpose

Convert raw user input into a small structured sketch that is cheap to use throughout the pipeline.

This layer should not produce verbose analysis.

---

## 5.2 Inputs

- raw user text
- active thread state
- selected user preference memory
- optional recent turn metadata

---

## 5.3 Outputs

`InputSketch`

---

## 5.4 Compression Steps

1. identify dominant intent
2. identify narrow topic
3. estimate user tone
4. choose response mode
5. identify memory triggers
6. estimate urgency
7. estimate personality weighting

---

## 5.5 Pseudocode

```python
def compress_input(user_text: str, runtime_state: RuntimeState) -> InputSketch:
    normalized = normalize_text(user_text)

    intent = classify_intent(normalized)
    topic = classify_topic(normalized)
    tone_in = classify_tone(normalized)
    response_mode = select_response_mode(intent, tone_in, runtime_state.active_thread_state)

    memory_triggers = extract_memory_triggers(
        text=normalized,
        active_thread_state=runtime_state.active_thread_state,
        recent_tags=runtime_state.recent_tag_cache,
    )

    urgency = estimate_urgency(normalized, tone_in, intent)
    personality_weight = estimate_personality_weight(intent, response_mode)

    return InputSketch(
        intent=intent,
        topic=topic,
        tone_in=tone_in,
        response_mode=response_mode,
        memory_triggers=memory_triggers,
        urgency=urgency,
        personality_weight=personality_weight,
    )
```

---

## 5.6 Heuristic Guidance

### Intent classes
Recommended initial set:
- `technical_spec_request`
- `technical_debugging`
- `emotional_support`
- `brainstorming`
- `light_conversation`
- `naming_or_branding`
- `editing_refinement`
- `planning_request`

### Tone classes
Recommended initial set:
- `neutral`
- `focused`
- `frustrated`
- `tired`
- `curious`
- `playful`
- `urgent`

### Response modes
Recommended initial set:
- `structured_technical`
- `calm_supportive`
- `concise_editorial`
- `creative_brainstorm`
- `light_natural_chat`

Keep the taxonomy small.

---

## 6. Memory Retrieval Algorithm

## 6.1 Purpose

Retrieve a tiny ranked set of memory records that are most useful for shaping the current reply.

This must remain cheap and bounded.

---

## 6.2 Retrieval Sources

- personality core
- user preference records
- user fact records
- episodic memory records
- response pattern records
- active thread state

---

## 6.3 Retrieval Strategy

1. generate lookup candidates from tags and heuristics
2. score candidate records
3. deduplicate near-duplicates
4. sort descending by score
5. keep top `k`
6. convert to compact activation cues

---

## 6.4 Retrieval Score Formula

```text
final_score =
  semantic_similarity * 0.35 +
  tone_similarity * 0.20 +
  preference_relevance * 0.20 +
  recency * 0.10 +
  importance * 0.15
```

Use cached or approximate values whenever possible.

---

## 6.5 Pseudocode

```python
def retrieve_memories(input_sketch: InputSketch, memory_store: MemoryStore) -> MemoryActivationBundle:
    candidates = []

    candidates.extend(memory_store.get_active_thread_records())
    candidates.extend(memory_store.lookup_by_tags(input_sketch.memory_triggers))
    candidates.extend(memory_store.get_recent_records(limit=32))

    unique_candidates = dedupe_records(candidates)

    scored = []
    for record in unique_candidates:
        score = score_memory_record(record, input_sketch)
        if score.final_score >= memory_store.config.min_memory_score:
            scored.append((record, score))

    scored.sort(key=lambda item: item[1].final_score, reverse=True)
    top_records = scored[:memory_store.config.max_retrieved_records]

    activated_records = []
    for record, score in top_records:
        activated_records.append(
            {
                "id": record.id,
                "type": record.type,
                "score": score.final_score,
                "cue": build_memory_cue(record),
            }
        )

    return MemoryActivationBundle(
        personality_core_id=memory_store.personality_core.id,
        activated_records=activated_records,
    )
```

---

## 6.6 Deduplication Rules

When two records are too similar:
- keep the higher-scoring one
- prefer explicit user-stated records over inferred records
- prefer compact summaries over long noisy ones
- prefer fresher records when quality is similar

---

## 7. Cognition Scaffold Algorithm

## 7.1 Purpose

Build a tiny generation scaffold that sharply constrains the weak model’s task.

This should not become a long internal planning process.

---

## 7.2 Inputs

- input sketch
- memory activation bundle
- personality core
- response pattern records

---

## 7.3 Outputs

`CognitionScaffold`

---

## 7.4 Scaffold Generation Logic

1. choose main goal
2. choose tone profile
3. choose focus list
4. choose avoid list
5. choose depth level
6. choose candidate modes

---

## 7.5 Pseudocode

```python
def build_cognition_scaffold(
    input_sketch: InputSketch,
    memory_bundle: MemoryActivationBundle,
    runtime_state: RuntimeState,
) -> CognitionScaffold:
    goal = derive_goal(input_sketch, memory_bundle)
    tone = derive_generation_tone(input_sketch, memory_bundle, runtime_state.personality_core)
    focus = derive_focus_list(input_sketch, memory_bundle)
    avoid = derive_avoid_list(input_sketch, runtime_state.personality_core)
    depth = derive_depth(input_sketch)
    candidate_modes = derive_candidate_modes(input_sketch, memory_bundle)

    return CognitionScaffold(
        goal=goal,
        tone=tone,
        focus=focus,
        avoid=avoid,
        depth=depth,
        candidate_modes=candidate_modes,
    )
```

---

## 7.6 Example Goal Mapping

| Intent | Goal |
|---|---|
| `technical_spec_request` | produce a clear structured technical response |
| `emotional_support` | validate emotion and offer one useful stabilizing thought |
| `editing_refinement` | preserve meaning while improving clarity and force |
| `brainstorming` | generate strong options with low repetition |
| `light_conversation` | keep flow natural and engaging |

---

## 8. Candidate Generation Algorithm

## 8.1 Purpose

Generate several short candidate responses instead of relying on one long completion.

This improves salvage quality and reduces the cost of failure.

---

## 8.2 Candidate Count Strategy

Default:
- `2` candidates

Allow:
- up to `4` candidates

Dynamic rule:
- use fewer candidates for low-complexity requests
- use more only when the request benefits from multi-angle output

---

## 8.3 Prompt Assembly Principles

Prompts must be:
- short
- structured
- mode-specific
- low-noise

Prompt should include:
- intent
- topic
- target tone
- selected memory cues
- one clear goal
- one short avoid list
- strict output length target

---

## 8.4 Pseudocode

```python
def generate_candidates(
    user_text: str,
    input_sketch: InputSketch,
    memory_bundle: MemoryActivationBundle,
    scaffold: CognitionScaffold,
    runtime_state: RuntimeState,
) -> list[CandidateRecord]:
    candidate_modes = scaffold.candidate_modes[:runtime_state.config.max_candidate_count]
    candidates = []

    for mode in candidate_modes:
        prompt = build_candidate_prompt(
            user_text=user_text,
            input_sketch=input_sketch,
            memory_bundle=memory_bundle,
            scaffold=scaffold,
            mode=mode,
            runtime_state=runtime_state,
        )

        generated_text = runtime_state.model.generate(
            prompt=prompt,
            max_tokens=runtime_state.config.max_candidate_tokens,
            temperature=select_temperature(mode, input_sketch),
        )

        candidate = CandidateRecord(
            id=make_id("cand"),
            type="candidate",
            mode=mode,
            text=generated_text,
            token_estimate=estimate_tokens(generated_text),
            scores={},
            created_at=utc_now(),
        )
        candidates.append(candidate)

    return candidates
```

---

## 8.5 Temperature Guidance

Recommended defaults:
- technical/spec tasks: low
- editorial tasks: low to moderate
- brainstorming: moderate
- light chat: moderate
- supportive conversation: low to moderate

For tiny models, keep temperature restrained.

---

## 9. Candidate Scoring Algorithm

## 9.1 Purpose

Estimate which candidate responses contain the most usable material before fragment extraction.

---

## 9.2 Score Dimensions

- relevance
- clarity
- coherence
- personality fit
- specificity
- genericness penalty

---

## 9.3 Pseudocode

```python
def score_candidate(
    candidate: CandidateRecord,
    input_sketch: InputSketch,
    scaffold: CognitionScaffold,
    runtime_state: RuntimeState,
) -> dict:
    relevance = heuristic_relevance(candidate.text, input_sketch)
    clarity = heuristic_clarity(candidate.text)
    coherence = heuristic_coherence(candidate.text)
    personality_fit = heuristic_personality_fit(candidate.text, runtime_state.personality_core)
    specificity = heuristic_specificity(candidate.text)
    genericness_penalty = heuristic_genericness(candidate.text)

    final_score = (
        relevance * 0.28 +
        clarity * 0.18 +
        coherence * 0.16 +
        personality_fit * 0.16 +
        specificity * 0.14 -
        genericness_penalty * 0.08
    )

    return {
        "relevance": relevance,
        "clarity": clarity,
        "coherence": coherence,
        "personality_fit": personality_fit,
        "specificity": specificity,
        "genericness_penalty": genericness_penalty,
        "final_score": final_score,
    }
```

---

## 9.4 Important Principle

A candidate should not be thrown away simply because it contains one weak sentence.

That is why fragment extraction exists.

---

## 10. Fragment Extraction Algorithm

## 10.1 Purpose

Split candidate responses into salvageable units so useful material can be preserved even when the full candidate is imperfect.

---

## 10.2 Extraction Unit

Preferred order:
1. sentence
2. clause
3. line segment

Sentence-level extraction should be the default.

---

## 10.3 Pseudocode

```python
def extract_fragments(candidate: CandidateRecord) -> list[FragmentRecord]:
    sentences = split_into_sentences(candidate.text)
    fragments = []

    for position, sentence in enumerate(sentences):
        text = sentence.strip()
        if not text:
            continue

        fragments.append(
            FragmentRecord(
                id=make_id("frag"),
                type="fragment",
                source_candidate_id=candidate.id,
                text=text,
                position=position,
                scores={},
                keep=False,
                created_at=utc_now(),
            )
        )

    return fragments
```

---

## 10.4 Clause Fallback

If a sentence is mixed quality:
- split by punctuation or conjunction heuristics
- score subfragments
- keep only high-value clauses

Use clause-splitting sparingly.

---

## 11. Fragment Scoring Algorithm

## 11.1 Purpose

Rank extracted fragments so the system can preserve the best parts and discard weak filler.

---

## 11.2 Score Dimensions

- relevance
- clarity
- specificity
- emotional usefulness or structural usefulness
- personality fit
- genericness penalty

---

## 11.3 Pseudocode

```python
def score_fragment(
    fragment: FragmentRecord,
    input_sketch: InputSketch,
    scaffold: CognitionScaffold,
    runtime_state: RuntimeState,
) -> dict:
    relevance = heuristic_relevance(fragment.text, input_sketch)
    clarity = heuristic_clarity(fragment.text)
    specificity = heuristic_specificity(fragment.text)
    usefulness = heuristic_usefulness(fragment.text, input_sketch, scaffold)
    personality_fit = heuristic_personality_fit(fragment.text, runtime_state.personality_core)
    genericness_penalty = heuristic_genericness(fragment.text)

    final_score = (
        relevance * 0.30 +
        clarity * 0.18 +
        specificity * 0.18 +
        usefulness * 0.20 +
        personality_fit * 0.14 -
        genericness_penalty * 0.10
    )

    return {
        "relevance": relevance,
        "clarity": clarity,
        "specificity": specificity,
        "usefulness": usefulness,
        "personality_fit": personality_fit,
        "genericness_penalty": genericness_penalty,
        "final_score": final_score,
    }
```

---

## 11.4 Keep Rule

```python
def should_keep_fragment(scores: dict, config: RuntimeConfig) -> bool:
    return scores["final_score"] >= config.min_fragment_score
```

---

## 11.5 Extraction and Scoring Pipeline

```python
def extract_and_score_fragments(
    candidates: list[CandidateRecord],
    input_sketch: InputSketch,
    memory_bundle: MemoryActivationBundle,
    scaffold: CognitionScaffold,
    runtime_state: RuntimeState,
) -> list[FragmentRecord]:
    kept_fragments = []

    for candidate in candidates:
        candidate.scores = score_candidate(candidate, input_sketch, scaffold, runtime_state)

        fragments = extract_fragments(candidate)
        for fragment in fragments:
            fragment.scores = score_fragment(fragment, input_sketch, scaffold, runtime_state)
            fragment.keep = should_keep_fragment(fragment.scores, runtime_state.config)
            if fragment.keep:
                kept_fragments.append(fragment)

    kept_fragments.sort(key=lambda frag: frag.scores["final_score"], reverse=True)
    return kept_fragments[:runtime_state.config.max_kept_fragments]
```

---

## 12. Salvage-Based Composition Algorithm

## 12.1 Purpose

Build a strong final reply from the best fragments rather than relying on any one candidate wholesale.

---

## 12.2 Composition Strategy

1. collect top fragments
2. remove redundancy
3. order by semantic flow
4. create compact refine prompt
5. generate one clean response
6. evaluate output
7. retry once if needed

---

## 12.3 Redundancy Removal

Two fragments are redundant if:
- they repeat the same point
- one is a weaker paraphrase of the other
- they share nearly identical meaning and tone

Keep the stronger one.

---

## 12.4 Pseudocode

```python
def compose_and_refine_response(
    user_text: str,
    input_sketch: InputSketch,
    memory_bundle: MemoryActivationBundle,
    scaffold: CognitionScaffold,
    fragments: list[FragmentRecord],
    runtime_state: RuntimeState,
) -> FinalResponseRecord:
    selected = dedupe_fragments(fragments)[:runtime_state.config.max_fragments_for_refine]

    refine_prompt = build_refine_prompt(
        user_text=user_text,
        input_sketch=input_sketch,
        memory_bundle=memory_bundle,
        scaffold=scaffold,
        fragments=selected,
    )

    generated_text = runtime_state.model.generate(
        prompt=refine_prompt,
        max_tokens=runtime_state.config.max_final_response_tokens,
        temperature=runtime_state.config.refine_temperature,
    )

    final_scores = score_final_response(generated_text, input_sketch, scaffold, runtime_state)

    return FinalResponseRecord(
        id=make_id("final"),
        type="final_response",
        text=generated_text,
        source_candidate_ids=list({frag.source_candidate_id for frag in selected}),
        source_fragment_ids=[frag.id for frag in selected],
        scores=final_scores,
        created_at=utc_now(),
    )
```

---

## 12.5 Core Principle

The system should preserve:
- useful insight
- strong phrasing
- emotional correctness
- structural clarity

and discard:
- generic filler
- weak disclaimers
- empty generalizations
- repetition

---

## 13. Final Response Scoring Algorithm

## 13.1 Purpose

Determine whether the refined response is good enough to return.

---

## 13.2 Quality Dimensions

- relevance
- clarity
- coherence
- personality fit
- usefulness
- low genericness

---

## 13.3 Pseudocode

```python
def score_final_response(
    text: str,
    input_sketch: InputSketch,
    scaffold: CognitionScaffold,
    runtime_state: RuntimeState,
) -> dict:
    relevance = heuristic_relevance(text, input_sketch)
    clarity = heuristic_clarity(text)
    coherence = heuristic_coherence(text)
    personality_fit = heuristic_personality_fit(text, runtime_state.personality_core)
    usefulness = heuristic_usefulness(text, input_sketch, scaffold)
    genericness_penalty = heuristic_genericness(text)

    final_score = (
        relevance * 0.26 +
        clarity * 0.18 +
        coherence * 0.18 +
        personality_fit * 0.16 +
        usefulness * 0.18 -
        genericness_penalty * 0.08
    )

    return {
        "relevance": relevance,
        "clarity": clarity,
        "coherence": coherence,
        "personality_fit": personality_fit,
        "usefulness": usefulness,
        "genericness_penalty": genericness_penalty,
        "final_score": final_score,
    }
```

---

## 13.4 Pass Threshold

```python
def passes_quality_threshold(
    final_response: FinalResponseRecord,
    input_sketch: InputSketch,
    scaffold: CognitionScaffold,
    runtime_state: RuntimeState,
) -> bool:
    return final_response.scores["final_score"] >= runtime_state.config.min_final_score
```

---

## 14. Fallback Repair Algorithm

## 14.1 Purpose

Provide a minimal second-pass rescue if refinement still fails.

This should be short and cheap.

---

## 14.2 When to Use

Use only when:
- the refined response is too generic
- the refined response missed the user’s intent
- the refined response violates personality constraints
- the refined response is structurally poor

---

## 14.3 Fallback Strategy

1. discard weak refined reply
2. rebuild a stripped-down prompt
3. generate one compact direct answer
4. skip multi-candidate loop
5. return if acceptable

---

## 14.4 Pseudocode

```python
def fallback_repair_response(
    user_text: str,
    input_sketch: InputSketch,
    memory_bundle: MemoryActivationBundle,
    scaffold: CognitionScaffold,
    runtime_state: RuntimeState,
) -> FinalResponseRecord:
    repair_prompt = build_repair_prompt(
        user_text=user_text,
        input_sketch=input_sketch,
        memory_bundle=memory_bundle,
        scaffold=scaffold,
    )

    repaired_text = runtime_state.model.generate(
        prompt=repair_prompt,
        max_tokens=runtime_state.config.max_final_response_tokens,
        temperature=runtime_state.config.repair_temperature,
    )

    final_scores = score_final_response(repaired_text, input_sketch, scaffold, runtime_state)

    return FinalResponseRecord(
        id=make_id("final"),
        type="final_response",
        text=repaired_text,
        source_candidate_ids=[],
        source_fragment_ids=[],
        scores=final_scores,
        created_at=utc_now(),
    )
```

---

## 15. Writeback Algorithm

## 15.1 Purpose

Store only useful memory updates after the turn finishes.

This layer must be selective.

---

## 15.2 Writeback Targets

- new or reinforced user preferences
- durable user facts
- compact episodic summary
- active thread updates
- response pattern reinforcement

---

## 15.3 Writeback Logic

1. inspect current turn
2. detect useful durable information
3. detect successful response structure
4. create compact summaries
5. avoid trivial noise
6. produce structured writeback bundle

---

## 15.4 Pseudocode

```python
def create_writeback_record(
    user_text: str,
    input_sketch: InputSketch,
    memory_bundle: MemoryActivationBundle,
    final_response: FinalResponseRecord,
    runtime_state: RuntimeState,
) -> WritebackRecord:
    new_preferences = infer_preference_updates(user_text, input_sketch, runtime_state)
    new_facts = infer_fact_updates(user_text, input_sketch, runtime_state)
    new_episode = summarize_episode(user_text, input_sketch, final_response, runtime_state)
    thread_updates = build_thread_updates(input_sketch, final_response, runtime_state)
    response_pattern_update = infer_response_pattern_update(final_response, input_sketch, runtime_state)

    return WritebackRecord(
        id=make_id("wb"),
        type="writeback",
        new_preferences=new_preferences,
        new_facts=new_facts,
        new_episodes=[new_episode] if new_episode else [],
        thread_updates=thread_updates,
        response_pattern_update=response_pattern_update,
        created_at=utc_now(),
    )
```

---

## 15.5 Noise Rejection Rule

Do not write back:
- trivial pleasantries
- one-off wording noise
- weak inferred preferences
- redundant facts
- low-value episode summaries

---

## 16. Persistence Algorithm

## 16.1 Purpose

Apply writeback updates to the persistent stores without bloating them.

---

## 16.2 Persistence Strategy

1. validate writeback bundle
2. merge duplicate preferences
3. merge duplicate facts
4. append episode if useful
5. update active thread state
6. reinforce or create response patterns
7. refresh indexes

---

## 16.3 Pseudocode

```python
def persist_writeback(writeback: WritebackRecord, memory_store: MemoryStore) -> None:
    validate_writeback(writeback)

    for pref in writeback.new_preferences:
        memory_store.merge_or_append_preference(pref)

    for fact in writeback.new_facts:
        memory_store.merge_or_append_fact(fact)

    for episode in writeback.new_episodes:
        if is_useful_episode(episode):
            memory_store.append_episode(episode)

    memory_store.apply_thread_updates(writeback.thread_updates)

    if writeback.response_pattern_update:
        memory_store.apply_response_pattern_update(writeback.response_pattern_update)

    memory_store.refresh_indexes()
```

---

## 17. Active Thread State Algorithm

## 17.1 Purpose

Maintain small, high-value short-term state for ongoing conversational threads.

---

## 17.2 Update Rules

- add newly active loop if relevant
- remove resolved loop
- refresh touched timestamp
- decay stale loops
- enforce max loop count
- collapse thread summary when needed

---

## 17.3 Pseudocode

```python
def apply_thread_updates(thread_state: ActiveThreadStateRecord, updates: dict, config: RuntimeConfig) -> ActiveThreadStateRecord:
    if "append_open_loops" in updates:
        thread_state.open_loops.extend(updates["append_open_loops"])

    if "remove_open_loops" in updates:
        thread_state.open_loops = [
            loop for loop in thread_state.open_loops
            if loop not in updates["remove_open_loops"]
        ]

    thread_state.open_loops = dedupe_list(thread_state.open_loops)
    thread_state.open_loops = thread_state.open_loops[:config.max_open_loops]

    if "touch_priority" in updates:
        thread_state.priority = max(thread_state.priority, updates["touch_priority"])

    thread_state.last_touched_at = utc_now()
    thread_state.updated_at = utc_now()
    return thread_state
```

---

## 17.4 Expiration Rule

Each turn:
- decrement implicit freshness
- if no touch and expired, collapse or clear thread state

---

## 18. Response Pattern Reinforcement Algorithm

## 18.1 Purpose

Learn compact high-performing response shapes from successful turns.

---

## 18.2 Reinforcement Logic

If the final response:
- scores well
- matches a useful structure
- is not overly specific to a one-off situation

then:
- reinforce matching pattern
- or create a new compact pattern record

---

## 18.3 Pseudocode

```python
def infer_response_pattern_update(
    final_response: FinalResponseRecord,
    input_sketch: InputSketch,
    runtime_state: RuntimeState,
):
    if final_response.scores["final_score"] < runtime_state.config.min_pattern_learning_score:
        return None

    pattern_shape = infer_pattern_shape(final_response.text, input_sketch)
    if not pattern_shape:
        return None

    return {
        "pattern_shape": pattern_shape,
        "summary": summarize_pattern_shape(pattern_shape, input_sketch),
        "quality_delta": 0.03,
        "last_used_at": utc_now(),
    }
```

---

## 19. Pruning Algorithm

## 19.1 Purpose

Keep memory stores small, fast, and high-signal.

---

## 19.2 Prune Targets

- stale episodic memory noise
- low-confidence inferred preferences
- weak response patterns
- redundant records
- cold thread state

---

## 19.3 Prune Strategy

1. score stale records for prune priority
2. preserve protected classes
3. compact duplicates
4. archive or delete low-value noise
5. rebuild indexes

---

## 19.4 Pseudocode

```python
def prune_memory_store(memory_store: MemoryStore, config: RuntimeConfig) -> None:
    memory_store.prune_preferences(
        max_records=config.max_user_preferences,
        preserve_explicit=True,
    )

    memory_store.prune_facts(
        preserve_high_importance=True,
    )

    memory_store.prune_episodes(
        max_hot_records=config.max_hot_episodes,
        min_quality=config.min_episode_quality,
    )

    memory_store.prune_response_patterns(
        max_records=config.max_response_patterns,
        min_quality=config.min_pattern_quality,
    )

    memory_store.prune_thread_state()
    memory_store.refresh_indexes()
```

---

## 20. Heuristic Functions

## 20.1 Design Note

The system should rely heavily on cheap heuristics rather than heavyweight evaluation models.

These functions may be rule-based, regex-based, shallow model-based, or embedding-assisted depending on budget.

---

## 20.2 Recommended Heuristic Set

- `heuristic_relevance`
- `heuristic_clarity`
- `heuristic_coherence`
- `heuristic_specificity`
- `heuristic_usefulness`
- `heuristic_genericness`
- `heuristic_personality_fit`

Keep them simple and tunable.

---

## 20.3 Example Genericness Heuristic

Signals of genericness:
- “a lot of people”
- “it’s normal”
- “everything will be okay”
- “as an AI”
- overbroad filler
- weak disclaimers
- repeated abstractions with no actionable content

Pseudocode:

```python
def heuristic_genericness(text: str) -> float:
    penalty = 0.0

    generic_phrases = [
        "a lot of people",
        "it's normal",
        "as an ai",
        "everything will be okay",
        "in today's world",
    ]

    lowered = text.lower()
    for phrase in generic_phrases:
        if phrase in lowered:
            penalty += 0.15

    if estimate_specific_noun_density(text) < 0.08:
        penalty += 0.10

    if estimate_repetition(text) > 0.20:
        penalty += 0.10

    return min(penalty, 1.0)
```

---

## 20.4 Example Personality Fit Heuristic

Signals of fit:
- directness
- low fluff
- natural language
- tone alignment
- avoidance of disallowed style

Pseudocode:

```python
def heuristic_personality_fit(text: str, personality_core: PersonalityCoreRecord) -> float:
    score = 0.5

    if is_direct(text):
        score += 0.15
    if is_low_fluff(text):
        score += 0.15
    if sounds_natural(text):
        score += 0.10
    if violates_avoid_list(text, personality_core.avoid):
        score -= 0.25

    return max(0.0, min(score, 1.0))
```

---

## 21. Prompt Construction Algorithms

## 21.1 Candidate Prompt Builder

```python
def build_candidate_prompt(
    user_text: str,
    input_sketch: InputSketch,
    memory_bundle: MemoryActivationBundle,
    scaffold: CognitionScaffold,
    mode: str,
    runtime_state: RuntimeState,
) -> str:
    cues = select_top_memory_cues(memory_bundle, limit=3)

    return f"""You are composing one short reply.

User request: {user_text}
Intent: {input_sketch.intent}
Topic: {input_sketch.topic}
Mode: {mode}
Tone: {scaffold.tone}
Goal: {scaffold.goal}
Focus: {", ".join(scaffold.focus[:3])}
Avoid: {", ".join(scaffold.avoid[:3])}
Memory cues: {"; ".join(cues)}

Reply briefly and specifically.
"""
```

---

## 21.2 Refine Prompt Builder

```python
def build_refine_prompt(
    user_text: str,
    input_sketch: InputSketch,
    memory_bundle: MemoryActivationBundle,
    scaffold: CognitionScaffold,
    fragments: list[FragmentRecord],
) -> str:
    fragment_lines = "\n".join([f"- {frag.text}" for frag in fragments[:5]])

    return f"""Using these useful fragments:
{fragment_lines}

Write one clean response.

Intent: {input_sketch.intent}
Tone: {scaffold.tone}
Goal: {scaffold.goal}
Avoid: {", ".join(scaffold.avoid[:3])}

Keep it concise, specific, and natural.
"""
```

---

## 21.3 Repair Prompt Builder

```python
def build_repair_prompt(
    user_text: str,
    input_sketch: InputSketch,
    memory_bundle: MemoryActivationBundle,
    scaffold: CognitionScaffold,
) -> str:
    cues = select_top_memory_cues(memory_bundle, limit=2)

    return f"""Write one direct response.

User request: {user_text}
Intent: {input_sketch.intent}
Tone: {scaffold.tone}
Goal: {scaffold.goal}
Memory cues: {"; ".join(cues)}

Avoid generic wording. Keep it clean and useful.
"""
```

---

## 22. Configurable Runtime Parameters

Suggested initial config:

```yaml
max_retrieved_records: 5
min_memory_score: 0.45

max_candidate_count: 3
max_candidate_tokens: 96
max_final_response_tokens: 180

max_kept_fragments: 8
max_fragments_for_refine: 5

min_fragment_score: 0.54
min_final_score: 0.68
min_pattern_learning_score: 0.78

max_open_loops: 8
max_user_preferences: 256
max_hot_episodes: 512
max_response_patterns: 256

min_episode_quality: 0.45
min_pattern_quality: 0.55

refine_temperature: 0.35
repair_temperature: 0.20
```

---

## 23. Complexity Targets

The system is designed for bounded work per turn.

## 23.1 Per-Turn Bounds

- retrieval candidates: bounded
- top retrieved records: `<= 5`
- candidate generations: `<= 4`
- kept fragments: `<= 8`
- refine passes: `<= 1`
- repair pass: `<= 1`

This keeps latency predictable.

---

## 23.2 Big-O Notes

If using lightweight indexing:

- retrieval candidate lookup: approximately `O(k)`
- scoring retrieved records: `O(n)` with bounded `n`
- fragment scoring: `O(f)` with bounded `f`
- composition: effectively constant-time for practical runtime

The real cost is model inference, so the architecture minimizes prompt length and generation length.

---

## 24. Testing Algorithms

## 24.1 Core Tests

- compression stability
- retrieval relevance
- retrieval dedupe behavior
- candidate scoring consistency
- fragment salvage effectiveness
- quality threshold behavior
- writeback selectivity
- pruning correctness

---

## 24.2 Example Test Cases

### Input Compression
- same user input should yield stable intent/topic labels

### Retrieval
- directness-related query should pull directness preference record

### Salvage
- candidate with one weak opening and one strong insight should preserve the strong insight

### Final Threshold
- weak generic reply should fail threshold
- concise relevant reply should pass

### Writeback
- trivial greeting should not generate durable fact writes

---

## 25. Failure Modes and Responses

| Failure Mode | Likely Cause | Algorithmic Response |
|---|---|---|
| generic final reply | weak fragments or weak refine prompt | run repair prompt with stricter anti-generic wording |
| too much latency | too many candidates or tokens | lower candidate count and token caps |
| personality drift | weak fit scoring | increase personality-fit weight |
| poor continuity | weak retrieval or noisy memory | prune memory and strengthen thread state updates |
| repetitive outputs | redundant fragments | improve fragment dedupe and response-pattern diversity |
| over-storing noise | weak writeback filter | tighten writeback thresholds |

---

## 26. Recommended Implementation Order

1. implement input compression
2. implement retrieval and scoring
3. implement cognition scaffold generation
4. implement candidate prompt builder
5. implement candidate generation
6. implement fragment extraction and scoring
7. implement refine composition
8. implement final quality scoring
9. implement writeback creation
10. implement persistence and pruning
11. add response pattern learning
12. tune thresholds on real conversations

---

## 27. Minimal Viable Runtime

A true MVP can be built with only:

- `compress_input`
- `retrieve_memories`
- `build_cognition_scaffold`
- `generate_candidates`
- `extract_and_score_fragments`
- `compose_and_refine_response`
- `create_writeback_record`

Everything else can be layered in afterward.

---

## 28. Final Guiding Principle

MindSpark: ThoughtForge should not waste compute trying to make a tiny model behave like a giant one.

Instead, it should:
- narrow the task
- retrieve the right memory
- guide the model with a tiny scaffold
- generate a few short candidates
- salvage the strongest pieces
- refine once
- store only what matters

That is how a tiny model becomes useful, coherent, and surprisingly strong on weak hardware.
