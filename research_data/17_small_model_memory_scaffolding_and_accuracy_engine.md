# 17 - Small-Model Memory Scaffolding and Accuracy Engine

Source basis: public docs + public reporting + independent synthesis
Contains proprietary code: no
Contains copied identifiers: no
Confidence: medium/high
Implementation status: concept/spec

## Why this document exists

Large models hide many weaknesses behind brute-force recall and broad priors. Smaller models do not have that luxury.

For the kinds of systems this pack targets, a small model becomes much more useful when the stack does four things well:

1. retrieves the *right* memory at the *right time*
2. compresses context into stable working notes
3. keeps uncertainty visible instead of bluffing
4. routes the model through narrow, purpose-built reasoning passes instead of one giant prompt

This file describes a memory-first architecture whose purpose is not to make a small model "act bigger," but to make it **more accurate, more grounded, and less drift-prone** within a bounded domain.

## Core claim

A small model can feel dramatically smarter when the system around it is stronger.

Accuracy gains usually come less from "more tokens" and more from:

- better retrieval
- cleaner state
- narrower tasks
- structured intermediate artifacts
- strong memory hygiene
- explicit uncertainty channels

## Design goal

Build a stack where a 3B–8B model can operate as if it has:

- stable continuity
- bounded world knowledge
- persistent user understanding
- clean task state
- explicit canon
- anti-drift constraints

The system does not ask the small model to remember everything. It asks it to **reason over curated memory surfaces**.

## The seven-layer scaffolding stack

```yaml
layers:
  1_input_gate:
    purpose: normalize user input and detect intent, risk, and retrieval needs
  2_state_snapshot:
    purpose: build a compact working summary of current world, task, and relationship state
  3_memory_retrieval:
    purpose: fetch only the highest-value memory slices for the current turn
  4_reasoning_workspace:
    purpose: let the model think over structured notes rather than raw history
  5_validator:
    purpose: check outputs against canon, constraints, and confidence rules
  6_memory_writer:
    purpose: write new memory only when justified
  7_distiller:
    purpose: compress the turn into better artifacts for future use
```

## Accuracy objectives

A strong memory scaffold should improve:

- factual consistency
- world continuity
- persona stability
- relationship continuity
- instruction retention
- tool-use precision
- refusal to invent unsupported details

## Small-model failure modes this stack is meant to fight

### 1. Scope flooding
The model sees too much and cannot decide what matters.

### 2. Local forgetting
The model loses track of a detail from three turns ago that is crucial now.

### 3. Confidence inflation
The model guesses instead of signaling uncertainty.

### 4. Identity drift
The model forgets who the user is, who it is, or what tone/role was established.

### 5. Canon corruption
World facts blur with speculation, jokes, or one-off improvisation.

### 6. Style over truth
The model produces good vibes while quietly becoming less accurate.

## Retrieval surface design

Do not retrieve "all relevant memory." Retrieve **memory slices matched to the active problem**.

### Recommended memory surfaces

```yaml
memory_surfaces:
  policy_surface:
    contents: rules, boundaries, operator policy, safety constraints
    retrieval_mode: always_on_minimal
  identity_surface:
    contents: user profile, companion identity, relationship framing, voice constraints
    retrieval_mode: high_priority
  world_surface:
    contents: canon entities, locations, factions, timelines, metaphysics
    retrieval_mode: intent_triggered
  task_surface:
    contents: current goals, open loops, unfinished plans, branch state
    retrieval_mode: immediate
  evidence_surface:
    contents: citations, retrieved passages, observed facts, tool outputs
    retrieval_mode: required_for_truth_claims
  emotion_surface:
    contents: current mood estimate, user needs, recent tension/repair state
    retrieval_mode: selective
  style_surface:
    contents: aesthetic guidance, diction, form, formatting rules
    retrieval_mode: lightweight
```

## Retrieval budget discipline

Smaller models need stricter retrieval budgets than larger ones.

### Budget rule
For a small model, each token must justify its existence.

### Practical policy
- retrieve at most 3 to 7 memory slices per turn for standard chat
- keep each slice atomic and scannable
- prefer summaries with links back to source memory
- separate hard facts from soft guidance
- rank by *decision impact*, not similarity alone

## Working memory packet

Before inference, build a single packet like this:

```yaml
working_packet:
  active_goal: string
  user_need_now: string
  must_remember:
    - atomic_item
  world_canon_needed:
    - atomic_item
  unresolved_questions:
    - atomic_item
  trust_anchored_evidence:
    - atomic_item
  style_constraints:
    - atomic_item
  uncertainty_flags:
    - atomic_item
```

This packet should be short enough that the model can truly attend to it.

## Accuracy ladder

Use different reasoning depths depending on difficulty.

```yaml
accuracy_ladder:
  tier_1_fast:
    use_when: simple friendly replies, low-risk continuity
    steps:
      - retrieve packet
      - answer
      - validate obvious contradictions
  tier_2_grounded:
    use_when: world facts, memory-sensitive continuity, project planning
    steps:
      - retrieve packet
      - build mini-outline
      - answer
      - validate against canon and constraints
  tier_3_verified:
    use_when: technical claims, safety-sensitive responses, lore-critical state change
    steps:
      - retrieve packet
      - gather evidence surface
      - draft
      - verifier pass
      - repair if needed
```

## The note-taking trick that helps small models

Instead of asking the model to remember everything in chat history, make it continuously maintain three notes:

```yaml
notes:
  state_note:
    purpose: what is happening right now
  canon_note:
    purpose: what is true in the world or relationship
  open_loops_note:
    purpose: what remains unresolved or promised
```

A small model can perform much better when it reasons over these notes than when it is forced to reconstruct everything from long dialogue.

## Structured uncertainty

Never let a small model hide uncertainty behind elegant prose.

### Require these output annotations internally
- supported
- inferred
- guessed
- stylistic flourish
- unresolved

These labels do not always need to be shown to the end user, but the system should track them.

## Memory write discipline

Small models should be conservative writers.

### Never auto-write durable memory from:
- retrieved external text
- emotional escalation
- user sarcasm or roleplay ambiguity
- one-time speculative statements
- model inference about user identity unless repeatedly supported

### Prefer promotion only after:
- repeated confirmation
- explicit user statement
- cross-turn consistency
- trust-zone approval

## Accuracy boosters that matter more than model size

### Booster 1 - Canon-first generation
Pull canon facts before generating new prose.

### Booster 2 - Claim-level validation
Check each substantive claim against evidence or stored canon.

### Booster 3 - Memory slot typing
A preference should not live in the same slot type as a world fact or safety rule.

### Booster 4 - Contradiction hooks
When the model proposes something that conflicts with canon, route it into repair.

### Booster 5 - Summary distillation
Keep a progressively refined summary tree instead of bloated flat history.

## Example architecture for a companion or character engine

```yaml
companion_stack:
  model_core: small_llm
  preprocessor:
    - intent_router
    - affect_estimator
    - risk_estimator
  memory_system:
    - policy_memory
    - identity_memory
    - bond_memory
    - episodic_memory
    - semantic_world_memory
  runtime_notes:
    - state_note
    - bond_note
    - open_loops_note
  validators:
    - canon_checker
    - boundary_checker
    - contradiction_checker
    - hallucination_checker
  writers:
    - observation_writer
    - summary_distiller
    - promotion_engine
```

## Example architecture for a cyber-Viking world engine

```yaml
world_engine_stack:
  model_core: small_llm
  surfaces:
    - cosmology_memory
    - faction_memory
    - ritual_symbol_memory
    - quest_state_memory
    - npc_belief_memory
  special_notes:
    - current_scene_tableau
    - active_portents
    - unresolved_oaths
    - player_reputation_snapshot
  validators:
    - canon_guard
    - timeline_guard
    - metaphysics_guard
```

## Metrics that actually matter

Track these instead of vague "quality" scores:

```yaml
metrics:
  canon_consistency_rate:
  contradiction_rate:
  unsupported_claim_rate:
  memory_retrieval_precision:
  memory_retrieval_waste:
  identity_drift_rate:
  promise_fulfillment_rate:
  repair_success_rate:
  user_correction_frequency:
```

## Implementation sketch

```yaml
pipeline:
  - ingest_turn
  - classify_turn
  - retrieve_minimal_packet
  - generate_state_note
  - run_model
  - validate_claims
  - repair_if_needed
  - decide_memory_writes
  - distill_turn
```

## Original design hypotheses worth testing

1. Small models benefit more from **state notes** than from longer raw context.
2. Bond continuity in companion systems depends more on **retrieval precision** than on model size.
3. A separate **uncertainty channel** reduces confident confabulation more effectively than merely lowering temperature.
4. Semantic world memory plus contradiction repair lets smaller models sustain long campaigns surprisingly well.
5. The best "small model upgrade" is often a stronger note and validation layer, not a bigger backbone.

## Red lines

- Do not claim smaller models become equivalent to frontier models.
- Do not treat memory as truth without provenance.
- Do not bloat retrieval just because storage is cheap.
- Do not let style directives override canon or safety.

## Build targets

Short-term build targets:
- working packet generator
- state note writer
- contradiction checker
- conservative memory writer
- retrieval budget scorer

Mid-term build targets:
- multi-surface retrieval
- uncertainty tracking
- claim-level validator
- compact canon graphs

Long-term build targets:
- self-repair loops
- adaptive retrieval budgets
- memory quality scoring by downstream accuracy
