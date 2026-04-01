# 09 - World Model and Belief Graph Spec

Source basis: public docs + independent synthesis
Contains proprietary code: no
Contains copied identifiers: no
Confidence: medium/high
Implementation status: concept/spec

## Purpose

This file turns the earlier world-model idea into a concrete structural spec.

The main design decision:

> store **truth**, **belief**, **relationship**, and **event** as different graph layers.

That separation is the difference between:
- a believable world
- and a giant inconsistent blob of notes

## The four ledgers

### 1. Canon ledger
Objective or authored truths the system currently accepts.

Examples:
- settlement exists at a location
- character has a known parent
- project repo uses pytest
- user prefers markdown artifacts

### 2. Belief ledger
What each actor thinks is true.

Examples:
- NPC believes the jarl betrayed them
- subagent believes tests are passing
- user-model believes current goal is debugging
- companion believes the user is tired

### 3. Relationship ledger
Edges between entities.

Examples:
- trusts
- fears
- serves
- mentors
- rival_of
- depends_on
- has_access_to

### 4. Event ledger
Time-indexed record of things that happened.

Examples:
- battle occurred
- patch was applied
- memory review approved
- shell command failed
- secret was exposed
- oath was sworn

## Why the split matters

Without a belief ledger:
- lies are impossible
- rumors become canon
- mistaken agents look omniscient
- persuasion has no structure
- dramatic irony disappears

Without an event ledger:
- change has no causal history
- reconciling contradictions becomes guesswork
- memory compaction destroys explainability

## Entity schema

```yaml
entity:
  entity_id: string
  entity_type: user|agent|npc|org|repo|file|artifact|place|object|system
  name: string
  aliases: []
  scope: global|world|campaign|repo|session
  status: active|inactive|archived
  authored: bool
  created_at: iso8601
  tags: []
```

## Canon claim schema

```yaml
canon_claim:
  claim_id: string
  subject_id: string
  predicate: string
  object_value: any
  object_type: entity|scalar|text|number|bool|json
  confidence: float
  provenance_ref: string
  temporal_bounds:
    start: iso8601|null
    end: iso8601|null
  review_state: pending|approved|rejected
  supersedes: string|null
```

## Belief claim schema

```yaml
belief_claim:
  belief_id: string
  believer_id: string
  subject_id: string
  predicate: string
  object_value: any
  certainty: float
  valence: positive|negative|neutral|mixed
  source_kind: observation|rumor|inference|deception|memory
  source_ref: string
  believed_since: iso8601
  expires_at: iso8601|null
  linked_canon_claim: string|null
```

## Relationship edge schema

```yaml
relationship_edge:
  edge_id: string
  source_id: string
  target_id: string
  relation_type: trusts|distrusts|fears|desires|allied_with|rival_of|obeys|protects|mentors|owns|depends_on
  strength: float
  asymmetry: bool
  evidence_refs: []
  updated_at: iso8601
```

## Event schema

```yaml
event:
  event_id: string
  event_type: speech|action|combat|movement|tool_call|memory_write|review|error|ritual|discovery
  actors: []
  objects: []
  location_id: string|null
  start_time: iso8601
  end_time: iso8601|null
  summary: string
  causal_parents: []
  effects:
    canon_updates: []
    belief_updates: []
    relationship_updates: []
    task_updates: []
```

## Derived views

The graph should support derived views rather than forcing every task to query raw tables.

### Useful derived views
- **current truth view**: latest approved canon claims
- **actor mind view**: all beliefs/goals/relationships for one actor
- **time slice view**: state of the world at a given time
- **rumor spread view**: how a false or partial belief propagated
- **trust map**: weighted relation graph
- **permission map**: which agents/tools have what powers

## Belief update model

When a new event arrives, update each actor separately.

### Belief update steps
1. determine whether the actor observed the event directly
2. determine perceptual fidelity
3. apply actor biases or prior beliefs
4. produce belief delta
5. adjust trust edges if deception or confirmation occurs

This gives you agents that interpret reality differently.

## Temporal modeling rule

Claims should preferably be **time-bounded** rather than overwritten.

Bad:
- `king = dead`

Better:
- `king.status = alive` from day 1 to day 89
- `king.status = dead` from day 90 onward

This is essential for:
- world history
- backtracking
- debugging
- replay systems
- “what did this actor know at this time?” queries

## Project-use interpretation

### Coding agent version
Entities:
- repo
- branch
- file
- subagent
- issue
- command
- test suite

Beliefs:
- subagent thinks patch is correct
- reviewer thinks risk is high
- operator believes current branch is safe

Events:
- patch applied
- tests failed
- approval denied
- context compacted

### Companion version
Entities:
- user
- assistant
- topics
- routines
- people
- goals

Beliefs:
- user likely wants a concise answer
- assistant infers user feels frustrated
- assistant suspects a preference shift

Relationships:
- trust
- comfort
- sensitivity
- attachment
- tension

### World/RPG version
Entities:
- gods
- factions
- villages
- artifacts
- PCs/NPCs
- quests
- locations

Beliefs:
- villagers think the draugr is in the barrow
- seer suspects the jarl is cursed
- rival clan believes the treaty is broken

Relationships:
- blood ties
- oath bonds
- feuds
- loyalties
- seduction
- debt
- devotion

## Consistency rules

### Rule 1
Canon claims must not be invalidated by belief updates alone.

### Rule 2
A belief may contradict canon.

### Rule 3
Relationship changes should usually point to a causal event.

### Rule 4
High-impact canon changes should preserve their predecessor claim.

### Rule 5
When compaction occurs, preserve graph deltas, not just prose summaries.

## Suggested storage strategy

A practical hybrid:
- relational store for canonical structured claims
- graph index for relationship traversal
- vector or lexical retrieval for long-form descriptions and lore text
- append-only event log for replay/debugging

## Query examples

### What does actor X believe right now?
- belief claims by believer
- current goals
- strongest relationships
- unresolved contradictions

### What changed after event Y?
- event effects
- superseded canon claims
- relationship delta
- new hypotheses

### Why did actor Z choose action A?
- fetch recent beliefs
- fetch goals and fears
- fetch trust edges
- fetch triggering event chain

## Original implementation direction

Build a **belief graph API** with five functions:
- `record_event`
- `propose_canon_change`
- `update_actor_belief`
- `query_state(time, scope)`
- `explain_decision(actor, event)`

## Tests to run

- Can two actors hold opposite beliefs while the world stays coherent?
- Can a rumor spread and later be disproven without corrupting canon?
- Can the system answer “what did this actor know at that moment?”
- Does compaction preserve the ability to reconstruct causality?

## Source notes

[WG1] OWASP Cheat Sheet, *AI Agent Security*  
https://cheatsheetseries.owasp.org/cheatsheets/AI_Agent_Security_Cheat_Sheet.html

[WG2] Claude Code Docs, *Create custom subagents*  
https://docs.anthropic.com/en/docs/claude-code/sub-agents

[WG3] Claude Code Docs, *How Claude remembers your project*  
https://docs.anthropic.com/en/docs/claude-code/memory
