# 14 - Project Branches for World Engines, Companion Systems, and Coding Agents

Source basis: independent synthesis
Contains proprietary code: no
Contains copied identifiers: no
Confidence: experimental
Implementation status: concept/spec

## Purpose

This document takes the generic research pack and forks it into three concrete build branches that match the kinds of systems you like to create.

The branches are:

1. world engine / RPG simulation
2. companion / persona continuity system
3. coding / builder agent

Each branch shares the same core primitives:
- policy layer
- memory lifecycle
- belief graph
- permission engine
- eval harness

But each branch weights them differently.

---

## Branch A - World Engine / RPG Simulation

### Primary design goal
Maintain coherent canon while allowing every actor to be limited, biased, wrong, manipulative, or misled.

### Most important data layers
- canon ledger
- belief ledger
- relationship graph
- event history
- quest/task state
- location state
- faction memory

### Suggested modules
- `world_canon_store`
- `actor_belief_store`
- `event_recorder`
- `relationship_engine`
- `rumor_propagation_engine`
- `quest_state_machine`
- `lore_review_queue`

### Special memory rules
- authored lore gets higher authority than inferred updates
- rumors stay in belief space until validated
- prophecies should be modeled as uncertainty-bearing constructs
- divine or occult information may be true, symbolic, partial, or deceptive

### Useful original theory
Use a **three-truth model**:
- mundane truth
- hidden truth
- believed truth

That lets mysteries exist without flattening the world.

### Example queries
- what does the seer believe will happen?
- what does the village think happened?
- what actually happened?
- who changed allegiance after the oath-break?

### High-value features
- time-sliced state queries
- causality reconstruction
- belief propagation
- tension and devotion meters
- memory decay for ordinary NPCs, stronger memory for important actors

---

## Branch B - Companion / Persona Continuity System

### Primary design goal
Preserve emotional continuity and preference alignment without turning inference into invasive certainty.

### Most important data layers
- user preference memory
- boundaries and sensitivities
- interaction-style preferences
- recurring topics
- trust and comfort state
- theory-of-mind hypothesis store
- shared-history summaries

### Suggested modules
- `preference_memory`
- `boundary_guard`
- `interaction_style_router`
- `emotional_continuity_engine`
- `tom_hypothesis_store`
- `shared_history_compactor`

### Special memory rules
- inferred emotional states decay fast
- stable preferences require repeated evidence
- sensitive inferences need soft usage or clarification
- no one-off personal guesses should become durable memory

### Useful original theory
Use **relationship weather**, not rigid bond scores.

Track dimensions like:
- warmth
- openness
- tension
- trust
- playfulness
- fatigue

These fluctuate, while deeper attachment structures move slowly.

### Example queries
- what style of answer is most comforting/helpful right now?
- has the user shown a stable preference or a situational need?
- should the system infer, ask, or stay neutral here?

### High-value features
- uncertainty-aware empathy
- topic-based continuity
- explicit privacy tiers
- memory rollback and review
- style continuity without overpersonalization

---

## Branch C - Coding / Builder Agent

### Primary design goal
Get real work done with high autonomy inside bounded technical risk.

### Most important data layers
- repo conventions
- branch/session memory
- task state
- tool histories
- approval outcomes
- failure loops
- artifact metadata

### Suggested modules
- `repo_memory`
- `task_planner`
- `permission_classifier`
- `sandbox_manager`
- `tool_trace_ledger`
- `subagent_router`
- `artifact_release_checker`

### Special memory rules
- branch and repo scope matter strongly
- stale debugging context should decay quickly
- tool outputs need sanitization before summarization or memory promotion
- durable memory should prefer build instructions and repeated operator corrections

### Useful original theory
Use a **friction ladder**:
- no friction for safe observation
- light friction for bounded mutation
- structural friction for risky execution
- hard friction for external or destructive side effects

### Example queries
- can this action be done safely in sandbox?
- should the system ask approval or deny-and-continue?
- what repeated repo facts should be promoted?

### High-value features
- branch-aware memory
- review-aware patching
- approval rationale formatting
- budget governor
- post-task compaction

---

## Shared “world-tree” architecture idea

A useful original synthesis for all three branches is a tree of scopes:

```yaml
scope_tree:
  global:
    children: [user, organization, world, repo]
  user:
    children: [session, preference, relationship]
  world:
    children: [campaign, faction, location, actor]
  repo:
    children: [branch, task, agent]
```

This helps with:
- inheritance
- isolation
- retrieval gating
- compaction
- explanation

## Cross-branch shared services

- provenance ledger
- contradiction resolver
- memory review queue
- risk engine
- observability spine
- structured compactor

## Which branch to build first?

### Fastest path to usable results
1. coding agent branch
2. companion continuity branch
3. world-engine belief graph branch

### Most powerful long-term merge
Create one shared core and keep domain plugins separate.

## Source notes

This file is primarily original synthesis built from the abstractions in the rest of the pack.
