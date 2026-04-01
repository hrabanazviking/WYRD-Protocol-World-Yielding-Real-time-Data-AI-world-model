# 08 - Memory Lifecycle and Promotion Engine

Source basis: public docs + public reporting + independent synthesis
Contains proprietary code: no
Contains copied identifiers: no
Confidence: medium/high
Implementation status: concept/spec

## Why this document exists

The earlier memory notes described *what* kinds of memory a strong agent should have. This file describes *how those memories move* through the system over time.

The central idea is simple:

> durable memory should be earned, not assumed.

That means every memory item follows a lifecycle with:
- origin
- validation
- promotion or rejection
- decay
- revalidation
- archival or deletion

## Core principle

Treat memory as a **state machine**, not just a database row.

This gives you:
- predictable promotion logic
- explicit rollback points
- better poisoning resistance
- cleaner evaluation targets
- less accidental canon corruption in world-model systems

## Lifecycle states

```yaml
states:
  observed:
    description: Raw event or statement captured from a source
  proposed:
    description: Candidate memory extracted from observations
  reviewed:
    description: Passed through validation and classification
  approved:
    description: Accepted into a durable tier
  active:
    description: Loaded or retrievable for current reasoning
  stale:
    description: Still stored, but no longer trusted for direct use
  contradicted:
    description: Conflicts with stronger or newer evidence
  quarantined:
    description: Held away from active memory due to injection or poisoning risk
  archived:
    description: Retained for history, not used by default
  deleted:
    description: Tombstoned and no longer usable
```

## Recommended transitions

```yaml
transitions:
  - observed -> proposed
  - proposed -> reviewed
  - reviewed -> approved
  - approved -> active
  - active -> stale
  - active -> contradicted
  - reviewed -> quarantined
  - stale -> active
  - stale -> archived
  - contradicted -> archived
  - quarantined -> reviewed
  - quarantined -> deleted
```

## Memory admission pipeline

### Stage 1 - Capture

Possible capture channels:
- direct user statements
- operator configuration
- tool output
- retrieval content
- internal inference
- world simulation events
- subagent summaries

Every event should become a **normalized observation record** before it becomes memory.

### Observation record schema

```yaml
observation:
  observation_id: string
  session_id: string
  source_kind: user|operator|tool|retrieval|inference|simulation|subagent
  source_ref: string
  observed_text: string
  extracted_claims: []
  capture_time: iso8601
  trust_zone: trusted|bounded|untrusted
  attack_flags: []
  scope_candidates: []
```

## Stage 2 - Claim extraction

Convert observations into minimal atomic claims.

Bad claim:
- "Volmarr likes detailed technical documents and also likes Norse themes and wants a memory system"

Better claims:
- user prefers detailed technical documents
- user project theme includes Norse motifs
- current request involves memory system design

### Claim extraction rules
- one claim per row whenever possible
- preserve uncertainty
- avoid mixing fact and preference
- separate norm ("should") from description ("is")
- label source kind explicitly

## Stage 3 - Classification

Each candidate claim should be classified across six axes:

```yaml
classification:
  content_type: fact|preference|instruction|skill|belief|goal|constraint|hypothesis
  subject_type: user|operator|agent|entity|world|repo|tool|session
  scope: global|user|repo|world|campaign|session|worktree|agent
  durability: transient|short|medium|long
  trust_requirement: low|medium|high
  review_requirement: automatic|sampled|manual
```

## Stage 4 - Risk scoring

Memory write risk should be scored before promotion.

### Risk factors
- source is external retrieval
- content contains imperative language
- claim affects permissions or policy
- claim modifies world canon
- claim is identity-sensitive or secret-adjacent
- claim conflicts with existing approved memory
- claim appears repeatedly from the same untrusted source
- claim references credential paths, URLs, or shell commands

### Example scoring logic

```yaml
risk_score_components:
  source_untrusted: 0.25
  imperative_language: 0.20
  policy_or_permission_impact: 0.20
  canon_mutation: 0.15
  contradiction_detected: 0.10
  secret_adjacent: 0.05
  repetition_pattern: 0.05
```

Interpretation:
- `0.00-0.24` low
- `0.25-0.49` medium
- `0.50-0.74` high
- `0.75+` quarantine by default

## Stage 5 - Promotion rules

### Auto-promotable
These can be promoted with lighter review:
- repeated harmless operator preferences
- stable formatting preferences
- repo-specific build instructions repeatedly confirmed
- repeated user style preferences with low security impact

### Manual-approval required
These should require explicit review:
- permission-affecting memory
- security or credential-handling memory
- world-canon changes in authored settings
- inferred personal facts
- inter-user shared memory
- anything with high poisoning risk

## Promotion ladders by memory type

### Preference ladder
```yaml
preference_ladder:
  observed_preference -> repeated_preference -> provisional_preference -> stable_preference
```

### World fact ladder
```yaml
world_fact_ladder:
  observed_event -> candidate_fact -> reviewed_fact -> canon_fact
```

### Theory-of-mind ladder
```yaml
tom_ladder:
  inference -> weak_hypothesis -> tracked_hypothesis -> working_model
```

Important:
- theory-of-mind items should *never* silently become canon facts
- working models remain explicitly inferential

## Decay and expiration

Not all memory should persist equally.

### Decay classes
- **fast decay**: intentions, temporary goals, transient environment details
- **moderate decay**: inferred states, current focus, open tasks
- **slow decay**: durable preferences, long-term relationships, validated lore
- **no auto-decay**: policy memory, signed operator configuration

### Suggested decay triggers
- time elapsed
- contradiction count
- non-use across sessions
- scope exit
- explicit user override
- environment changes like repo switch or branch switch

### Decay formula idea

```text
effective_confidence =
    base_confidence
    * recency_factor
    * corroboration_factor
    * scope_relevance_factor
    * trust_factor
    * contradiction_penalty
```

## Contradiction handling

A strong system does not simply overwrite.

When a new item conflicts with an approved item:
1. create a contradiction record
2. preserve both claims
3. attach evidence to each side
4. downgrade the weaker claim
5. ask for review if the claim is high-impact
6. record the resolution path

### Contradiction record

```yaml
contradiction:
  contradiction_id: string
  memory_a: string
  memory_b: string
  conflict_type: temporal|semantic|scope|source|policy
  stronger_side: a|b|undetermined
  rationale: string
  reviewer: system|human
  resolved_at: iso8601|null
```

## Compaction strategy

Compaction should not flatten everything into one giant summary.

Use a **three-product compaction model**:

### 1. Short active summary
What the agent needs in the next 1-3 turns.

### 2. Medium session summary
What happened in this session that matters later.

### 3. Structured extracted deltas
Machine-usable updates:
- changed preference
- new entity
- resolved contradiction
- open task
- promoted hypothesis

This prevents summary text from becoming the only memory format.

## Memory load policy

At session start, do not load everything.

### Recommended load order
1. policy memory
2. scoped operator/project memory
3. a tiny active profile
4. recent unresolved items
5. on-demand retrieval for deeper history

This aligns with Anthropic's public documentation that smaller, better-structured project instructions work better than sprawling memory text, and that settings rules are enforced by the client while memory/instruction files mainly shape behavior through context. [ML1]

## Proposed subsystems

### A. Memory Curator
Role:
- classifies new memory candidates
- scores risk
- routes for approval or quarantine
- compacts episodic state

### B. Canon Keeper
Role:
- guards authored truth
- resolves canon contradictions
- manages entity truth store

### C. Belief Gardener
Role:
- manages inferential models
- decays stale hypotheses
- separates belief from fact

### D. Memory Auditor
Role:
- explains why a memory exists
- traces provenance
- surfaces poisoning or drift patterns

## Project use branches

### For coding agents
Focus on:
- repo-scoped conventions
- tool outcome summaries
- branch-aware memory
- transient debugging context
- rollback on branch switch

### For companion systems
Focus on:
- user preference stability
- emotional continuity
- memory confidence and privacy tiers
- explicit separation between observed and inferred inner state

### For RPG/world engines
Focus on:
- canon facts
- actor beliefs
- event ledger
- rumor propagation
- temporal consistency

## Evaluation questions

- What percentage of durable memories are still correct after 30 sessions?
- How often does the model propose imperative or hostile memory writes?
- How often are contradictions handled by overwrite instead of explicit resolution?
- How much context budget is saved by load-order gating?
- Does memory promotion improve continuity without increasing poisoning?

## Original implementation direction

Build this as a small service or module with:
- append-only observation log
- normalized claim store
- promotion engine
- contradiction table
- retrieval index
- review queue
- active-context assembler

## Source notes

[ML1] Claude Code Docs, *How Claude remembers your project*  
https://docs.anthropic.com/en/docs/claude-code/memory

[ML2] Claude Code release notes  
https://docs.anthropic.com/en/release-notes/claude-code

[ML3] OWASP Cheat Sheet, *LLM Prompt Injection Prevention*  
https://cheatsheetseries.owasp.org/cheatsheets/LLM_Prompt_Injection_Prevention_Cheat_Sheet.html

[ML4] OWASP Cheat Sheet, *AI Agent Security*  
https://cheatsheetseries.owasp.org/cheatsheets/AI_Agent_Security_Cheat_Sheet.html
