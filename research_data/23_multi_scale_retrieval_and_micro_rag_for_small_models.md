# 23 - Multi-Scale Retrieval and Micro-RAG for Smaller Models

Source basis: public docs + public reporting + independent synthesis
Contains proprietary code: no
Contains copied identifiers: no
Confidence: medium/high
Implementation status: concept/spec

## Why this document exists

Retrieval systems often fail smaller models by giving them:
- too much
- the wrong level of abstraction
- chunks without task alignment
- memory that is semantically similar but decision-useless

This file proposes a multi-scale retrieval system optimized for smaller models and long-lived character or world engines.

## Core principle

Retrieve across **scales**, not just across documents.

The model may need:
- one atomic fact
- one medium summary
- one high-level thematic frame
- one emotional cue
- one contradiction warning

A single chunk size cannot do all of that well.

## Retrieval scales

```yaml
retrieval_scales:
  atom:
    size: tiny
    examples:
      - user prefers X
      - oath is still open
      - file path changed
  note:
    size: small
    examples:
      - current state note
      - bond snapshot
      - scene frame
  episode:
    size: medium
    examples:
      - argument about architecture
      - ritual conversation
      - last debugging session
  theme:
    size: larger
    examples:
      - stable aesthetic preferences
      - long-running campaign arc
      - persistent attachment pattern
```

## Micro-RAG concept

Traditional RAG is often document-first.
Micro-RAG is **task-first and packet-first**.

### It should:
- retrieve a very small number of mixed-scale items
- compose them into a compact packet
- validate relevance before model inference

## Query decomposition

Every incoming turn should generate multiple retrieval intents.

```yaml
retrieval_intents:
  factual_need:
  identity_need:
  bond_need:
  world_need:
  symbolic_need:
  task_need:
  contradiction_check_need:
```

The system does not have to use all of them, but it should know which are active.

## Retrieval ranking beyond similarity

Use a mixed score:

```yaml
retrieval_score:
  semantic_similarity:
  decision_impact:
  recency:
  trust_score:
  contradiction_relevance:
  relationship_weight:
  scene_relevance:
```

### Design insight
The highest-similarity memory is often not the most useful memory.

## Contradiction-aware retrieval

Always allow the retriever to pull one "warning item" that says:
- current claim may conflict with canon
- relationship tone may be too warm or too cold
- this scene resembles a prior failure mode
- this requested action crosses a boundary

## Packet composition

```yaml
micro_rag_packet:
  top_atomic_facts:
    - string
  best_state_note: string
  best_episode_or_theme: string
  contradiction_warning: string
  optional_emotional_or_symbolic_cue: string
```

This keeps packet size small while preserving multiple scales.

## Retrieval for companion systems

Priority order often should be:
1. active bond state
2. recent promise or unresolved tension
3. user preference relevant to the turn
4. style/voice cue
5. episode memory if needed

## Retrieval for cyber-Viking world engines

Priority order often should be:
1. scene frame
2. world canon fact
3. unresolved oath/taboo/omen
4. faction or NPC belief note
5. timeline or map constraint

## Retrieval for coding systems

Priority order often should be:
1. current task note
2. relevant file/module summary
3. recent failed attempt or warning
4. repo policy or boundary note
5. test/verification requirement

## Why this helps smaller models

A smaller model benefits when retrieval is:
- narrow
- typed
- layered
- contradiction-aware
- task-aligned

This reduces the need for the model to discover structure inside the prompt.

## Retrieval waste

Measure how much retrieved content is ignored or irrelevant.

```yaml
retrieval_waste:
  total_tokens_retrieved:
  tokens_used_in_final_reasoning:
  irrelevant_item_count:
  misleading_item_count:
```

## Suggested implementation

```yaml
pipeline:
  - classify_intents
  - query per scale
  - rank by mixed score
  - force include one contradiction candidate if available
  - compose micro packet
  - run model
  - log which packet items mattered
```

## Learning loop

Use downstream results to tune retrieval:
- which items helped?
- which were ignored?
- which correlated with better accuracy?
- which caused drift?

This turns retrieval into a trainable subsystem.

## Original design hypotheses worth testing

1. Mixed-scale packets outperform same-size chunk retrieval for small models.
2. One contradiction-warning item materially reduces confabulation.
3. Bond-aware retrieval improves companion realism more than simply expanding history.
4. Episode-level retrieval is often more useful than document chunk retrieval in long chats.

## Red lines

- Do not retrieve by cosine similarity alone.
- Do not always maximize recall; small models choke on clutter.
- Do not hide contradictions from the model.
- Do not merge all scales into one opaque summary.
