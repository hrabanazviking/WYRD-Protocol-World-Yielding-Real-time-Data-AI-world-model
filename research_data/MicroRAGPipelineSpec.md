# MicroRAGPipelineSpec.md

Source basis: original implementation spec derived from earlier clean-room research pack
Contains proprietary code: no
Contains copied identifiers: no
Confidence: build-facing
Implementation status: implementation spec

## Purpose

This document defines a **MicroRAG pipeline** for smaller models that need strong accuracy, memory continuity, and world grounding without a huge context window.

The pipeline is built for:

- 3B to 14B class models
- coding assistants working inside bounded projects
- companions needing continuity without bluffing
- cyber-Viking world engines with symbolic layers
- retrieval systems where clutter is more dangerous than scarcity

## Core principle

A smaller model does not need *more documents*.
It needs a **better assembled micro-context**.

That micro-context should be:

- relevant
- contradiction-aware
- compact
- typed
- confidence-tagged
- task-shaped

## Pipeline overview

```yaml
micro_rag_pipeline:
  1_query_understanding:
  2_context_mode_selection:
  3_candidate_gathering:
  4_typed_reranking:
  5_contradiction_injection:
  6_packet_assembly:
  7_generation:
  8_post_generation_validation:
  9_feedback_learning:
```

## Index families

```yaml
index_families:
  atom_index:
    holds: observations, short facts, tool findings, code facts
  episode_index:
    holds: scene summaries, recap windows, grouped events
  canonical_index:
    holds: approved truths, world canon, project facts, user facts
  bond_index:
    holds: relationship excerpts, vows, hurts, modes
  symbolic_index:
    holds: runes, omens, sacred place moods, ritual traces
  code_index:
    holds: file summaries, function facts, test outcomes, architecture notes
  graph_index:
    holds: entity links, contradiction links, causal chains
```

## Query understanding

The planner should classify the user request before retrieval.

```yaml
query_modes:
  factual_lookup:
  companion_continuity:
  world_state:
  symbolic_interpretation:
  coding_task:
  repair_or_boundary:
  creative_generation:
```

## Context mode selection

Different tasks need different packets.

```yaml
context_modes:
  factual_lookup:
    prioritize:
      - canonical_index
      - atom_index
      - graph_index
  companion_continuity:
    prioritize:
      - bond_index
      - canonical_index
      - episode_index
      - symbolic_index
  world_state:
    prioritize:
      - canonical_index
      - graph_index
      - episode_index
      - symbolic_index
  coding_task:
    prioritize:
      - code_index
      - canonical_index
      - atom_index
      - graph_index
```

## Candidate gathering

Each query mode gathers from multiple scales.

```yaml
candidate_gathering:
  max_raw_candidates:
    atom: 16
    episode: 8
    canonical: 12
    bond: 6
    symbolic: 5
    code: 12
    graph: 10
  gather_methods:
    - lexical_match
    - vector_similarity
    - facet_filter
    - graph expansion
    - recency boost
    - active_scene boost
```

## Typed reranking

A single similarity score is not enough.

```yaml
rerank_score:
  final_score = (
    similarity * 0.24 +
    task_relevance * 0.24 +
    support_quality * 0.14 +
    scope_match * 0.12 +
    recency * 0.08 +
    contradiction_penalty * -0.10 +
    token_cost_penalty * -0.04 +
    novelty_bonus * 0.04 +
    bond_fit * 0.08
  )
```

### Score dimensions

```yaml
score_dimensions:
  similarity:
    description: vector or lexical closeness
  task_relevance:
    description: usefulness for this exact question
  support_quality:
    description: confidence, approval state, evidence strength
  scope_match:
    description: does it belong to this world/project/pair/scene?
  recency:
    description: recent context may matter more for active tasks
  contradiction_penalty:
    description: stale or conflicting material should fall unless deliberately injected
  token_cost_penalty:
    description: bulky items lose points for small models
  novelty_bonus:
    description: avoid five near-duplicate chunks
  bond_fit:
    description: especially for companion output
```

## Contradiction injection

Do not hide contradictions from the model when they matter.

```yaml
contradiction_injection:
  include_one_if:
    - top claim has unresolved contradiction
    - user asks about memory or canon
    - generated answer would otherwise overstate certainty
  injected_item_format:
    - conflicting_claim
    - preferred_claim_if_known
    - resolution_state
```

## Packet assembly

The final packet should be typed, not a blob.

```yaml
micro_packet:
  task_header:
    mode: string
    goal: string
  truth_packet:
    must_be_true:
      - string
    open_unknowns:
      - string
  retrieval_sections:
    canonical_facts:
      - item
    recent_events:
      - item
    bond_excerpt:
      - item
    symbolic_context:
      - item
    code_facts:
      - item
    contradiction_watch:
      - item
  style_footer:
    - do not invent unsupported facts
    - state uncertainty when needed
```

## Item shape

```yaml
retrieval_item:
  item_id: string
  item_type: fact|event|bond|symbol|code|contradiction
  text: string
  support_class: supported|inferred|speculative
  confidence: 0.0
  source_ref: string
```

## Token budgets

```yaml
packet_budgets:
  3b_class:
    total: 500_to_750
    canonical_facts: 6
    recent_events: 4
    bond_excerpt_lines: 4
    symbolic_context: 2
    code_facts: 6
    contradiction_watch: 1
  7b_class:
    total: 850_to_1300
    canonical_facts: 10
    recent_events: 6
    bond_excerpt_lines: 6
    symbolic_context: 4
    code_facts: 8
    contradiction_watch: 2
  14b_class:
    total: 1300_to_2100
    canonical_facts: 14
    recent_events: 8
    bond_excerpt_lines: 8
    symbolic_context: 5
    code_facts: 12
    contradiction_watch: 2
```

## Assembly patterns

### Pattern A - companion answer

```yaml
companion_packet:
  task_header:
    mode: companion_continuity
    goal: answer warmly without inventing personal memory
  truth_packet:
    must_be_true:
      - user preference facts must come from approved memory only
  retrieval_sections:
    canonical_facts:
      - stable user preference
    recent_events:
      - last shared design task
    bond_excerpt:
      - trust high, builder mode active
    symbolic_context:
      - sacred coding motifs active
    contradiction_watch:
      - none
```

### Pattern B - coding answer

```yaml
coding_packet:
  task_header:
    mode: coding_task
    goal: answer with verified implementation detail
  truth_packet:
    must_be_true:
      - do not claim tests passed without evidence
  retrieval_sections:
    canonical_facts:
      - architecture truths
    recent_events:
      - latest file changes
    code_facts:
      - file summaries
      - function signatures
      - test outcomes
    contradiction_watch:
      - stale summary conflicts with latest patch
```

### Pattern C - world scene answer

```yaml
world_packet:
  task_header:
    mode: world_state
    goal: continue the scene without breaking canon
  retrieval_sections:
    canonical_facts:
      - place canon
      - faction facts
    recent_events:
      - last scene transitions
    symbolic_context:
      - oath tension active
      - kenaz rune glowing in forge-hall
```

## Anti-injection pipeline

Every external candidate should be screened before it becomes retrievable.

```yaml
anti_injection_pipeline:
  pre_ingest_scan:
    - hidden instruction patterns
    - prompt override attempts
    - self-authorizing permission language
    - memory poisoning phrases
  ingestion_actions:
    safe:
      - allow to observation store
    suspicious:
      - mark risk tag
      - disable canonical promotion
    dangerous:
      - quarantine
      - exclude from runtime retrieval
```

## Post-generation validation

```yaml
post_generation_validation:
  checks:
    - every factual claim supported or explicitly uncertain
    - no unsupported personal memory
    - no contradiction with truth packet
    - if code task: no invented file or test result
  actions_on_fail:
    - revise_with_truth_packet
    - reduce certainty
    - request tool evidence
```

## Learning loop

Record what helped.

```yaml
feedback_learning:
  log:
    - which items were retrieved
    - which items appeared in final answer
    - user corrections
    - validator catches
    - token cost
  improve:
    - rerank weights
    - duplicate suppression
    - packet budgets
    - contradiction injection thresholds
```

## Minimal orchestrator pseudocode

```python

def micro_rag(query, context, model_tier):
    mode = classify_query(query, context)
    raw = gather_candidates(query, mode, context)
    scored = rerank(raw, query, mode, context)
    packet = assemble_packet(scored, mode, model_tier)
    draft = generate(packet)
    checked = validate(draft, packet)
    learn(packet, checked)
    return checked
```

## Failure modes

- too many near-duplicate facts
- vector-similar but scope-wrong memories
- stale canon outranking recent canon
- emotional style retrieved instead of concrete truth
- symbolic packet overwhelming practical task
- no contradiction item when contradiction exists

## Practical defaults

```yaml
practical_defaults:
  duplicate_suppression_similarity_threshold: 0.88
  force_include_recent_if_scene_mode_active: true
  force_include_bond_excerpt_for_companion: true
  force_include_code_evidence_for_coding: true
  contradiction_injection_on_uncertain_memory_queries: true
```

## Final guidance

MicroRAG is not tiny RAG.
It is **disciplined retrieval** designed so a smaller model can act like it has a better memory, a better map, and better judgment than its raw parameter count suggests.
