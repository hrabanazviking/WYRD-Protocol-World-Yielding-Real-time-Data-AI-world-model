# 22 - Memory Compression, Distillation, and Rehydration

Source basis: public docs + public reporting + independent synthesis
Contains proprietary code: no
Contains copied identifiers: no
Confidence: medium/high
Implementation status: concept/spec

## Why this document exists

Long-lived systems die from memory bloat as often as they die from memory loss.

The answer is not to store less. The answer is to store **better**.

This file describes how to compress memory without destroying the details that matter, and how to rehydrate compact artifacts back into useful working context when needed.

## Core principle

Memory should become:
- smaller over time
- clearer over time
- more structured over time
- easier to trust over time

Compression is not deletion. It is **shape improvement**.

## Three kinds of compression

```yaml
compression_types:
  syntactic:
    purpose: remove verbal redundancy
  semantic:
    purpose: preserve meaning in fewer units
  structural:
    purpose: transform flat history into better data structures
```

## Memory pyramid

```yaml
memory_pyramid:
  raw_events:
    description: complete captured observations
  episode_summaries:
    description: compact summaries of bounded event clusters
  thematic_summaries:
    description: cross-episode patterns and stable lessons
  canonical_facts:
    description: promoted, durable, atomic truths
  identity_models:
    description: high-value persistent models of user, world, and bond
```

A strong system gradually moves upward while keeping links downward.

## Distillation passes

### Pass 1 - Turn distillation
Convert each turn into:
- claims
- emotional signature
- open loops
- candidate memories

### Pass 2 - Episode distillation
Group related turns into episodes:
- conflict about a design choice
- ritual conversation
- major lore reveal
- repair conversation
- coding session

### Pass 3 - Theme distillation
Across many episodes, extract:
- recurring preferences
- stable world truths
- repeated user priorities
- characteristic bond patterns
- long arcs in project direction

## Compression schema

```yaml
compressed_memory:
  source_span:
    start_turn: integer
    end_turn: integer
  preserved_atoms:
    - string
  dropped_material:
    - filler
    - repetition
  confidence: 0.0
  loss_risk: low|medium|high
  rehydration_hints:
    - string
```

## Loss-aware compression

Every memory artifact should record what may have been lost.

### Common loss risks
- nuance in emotional tone
- sequence ambiguity
- who initiated what
- uncertainty markers
- humor or sarcasm context
- symbolic or sensory richness

When loss risk is high, keep links to raw events.

## Rehydration

Rehydration means expanding a compact artifact back into a working packet for a specific need.

### Rehydration is not full decompression
You do not need the whole past. You need the right *facets* of it.

### Rehydration modes

```yaml
rehydration_modes:
  factual:
    rebuild canon or task facts
  emotional:
    restore tone and relationship context
  procedural:
    restore steps, decisions, or workflows
  symbolic:
    restore mood, themes, omens, or ritual relevance
```

## Rehydration packet example

```yaml
rehydrated_packet:
  summary_anchor: string
  key_supporting_events:
    - string
  unresolved_edges:
    - string
  emotional_color: string
  current relevance: string
```

## Compression strategy for smaller models

Smaller models need compressed, typed artifacts more than larger ones.

### Recommendation
Instead of feeding old dialogue, feed:
- current state note
- compressed episode summary
- 3 to 5 atomic facts
- 1 or 2 emotional/bond cues
- unresolved loop list

## Delta summaries

Do not rewrite giant summaries each turn. Maintain deltas.

```yaml
delta_summary:
  changed_facts:
    - string
  changed_bond_state:
    - string
  newly_open_loops:
    - string
  closed_loops:
    - string
  new_risks:
    - string
```

Deltas make long-running systems more efficient and auditable.

## Compression quality metrics

```yaml
metrics:
  compression_ratio:
  factual_retention_rate:
  contradiction_after_rehydration_rate:
  emotional_retention_score:
  retrieval_hit_rate:
  token_savings:
  user_correction_rate_after_compression:
```

## Compression mistakes to avoid

### 1. Flattening everything into one mega-summary
This destroys selective retrieval.

### 2. Keeping pretty prose instead of actionable structure
Elegant summaries often perform worse than typed notes.

### 3. Mixing canon with speculation
Compression should increase separation, not blur it.

### 4. Deleting uncertainty
A compressed lie is worse than a large uncertain note.

## Suggested artifact set

```yaml
artifact_set:
  turn_delta.md
  episode_summary.md
  canon_fact_table.md
  bond_shift_log.md
  world_timeline.md
  symbolic_threads.md
```

## Original design hypotheses worth testing

1. Structured compression improves small-model performance more than context-window expansion alone.
2. Delta-based memory maintenance is more stable than repeated whole-summary rewriting.
3. Rehydration quality is a stronger predictor of downstream accuracy than raw storage volume.
4. Emotional retention can be preserved cheaply if tracked explicitly.

## Red lines

- Do not compress facts and feelings into one indistinct blob.
- Do not discard provenance during compression.
- Do not summarize away contradictions.
- Do not assume shorter is better if it removes the decision-critical edge.
