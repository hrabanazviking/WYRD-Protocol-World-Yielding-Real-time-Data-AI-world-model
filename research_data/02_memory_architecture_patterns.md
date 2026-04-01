# 02 - Memory Architecture Patterns

## Thesis

For advanced agents, memory should not be one big bag of text. The strongest pattern is a **tiered memory system** where each layer has a different job, lifespan, validation threshold, and risk profile.

Public Anthropic documentation describes Claude Code as using two complementary memory systems: persistent instruction files written by the user, and auto memory written by the system based on corrections and preferences. Both are loaded at session start, but are treated as context rather than enforced truth. Auto memory is scoped per working tree, while instruction files can be scoped to project, user, or organization. [M1]

That public pattern points toward a strong general lesson:

> Split **normative memory** (“how to behave”) from **descriptive memory** (“what we have learned”).

## Recommended memory stack

### 1. Constitutional / policy memory

**What it stores**

- non-negotiable rules
- safety policy
- identity constraints
- tone or ritual framing if relevant to the application
- legal / security boundaries

**Properties**

- human-authored only
- versioned
- signed / integrity-checked
- rare updates
- not writable by the model

### 2. Operator / project memory

**What it stores**

- project conventions
- folder expectations
- test commands
- workflow preferences
- repo-specific assumptions

**Properties**

- human-authored or human-reviewed
- scoped to repo, world, campaign, or application instance
- loaded every session

This is analogous to the public “CLAUDE.md” concept but should be implemented in your own way. Anthropic’s docs explicitly say smaller, more specific, better-structured instructions work better than long vague files. [M1]

### 3. Stable learned memory

**What it stores**

- validated preferences
- durable world facts
- trusted entity traits
- repeatable build facts
- persistent user preferences

**Properties**

- machine-suggested, human-approvable
- each entry includes provenance, timestamp, confidence, and review status
- can expire or be revalidated

### 4. Episodic memory

**What it stores**

- session summaries
- recent actions
- recent outcomes
- recent corrections
- temporary intentions

**Properties**

- high churn
- compactable
- useful for continuity
- lower trust than reviewed stable memory

### 5. Hypothesis memory

**What it stores**

- inferences
- theory-of-mind guesses
- uncertain user goals
- possible NPC motives
- predicted next steps

**Properties**

- must never be presented as fact
- always tagged as inference
- automatically decays unless confirmed

### 6. Quarantine memory

**What it stores**

- suspicious retrieved text
- injection-like phrases
- failed memory proposals
- contradictory claims
- possible poisoning attempts

**Properties**

- isolated from main context
- viewable for debugging
- never auto-promoted

## Minimum metadata for every memory item

```yaml
memory_id: string
memory_type: policy|project|stable|episodic|hypothesis|quarantine
subject: string
predicate: string
object: string
scope: global|repo|world|character|user|session|worktree
source_kind: user|system|tool|retrieval|inference
provenance_ref: string
confidence: 0.0-1.0
review_status: pending|approved|rejected|expired
created_at: iso8601
last_validated_at: iso8601|null
expires_at: iso8601|null
sensitivity: public|internal|secret
poison_risk: low|medium|high
```

## Memory write gate

A safe system does **not** let the model write directly into durable memory without a gate.

### Recommended gate logic

1. candidate memory is proposed
2. classify the memory type
3. check if it came from an untrusted source
4. assign poisoning risk
5. reject if it contains instructions rather than facts
6. require review for high-impact durable writes
7. record rationale

## Memory compaction

Anthropic’s public docs note that startup memory consumes context budget and that long files reduce adherence. [M1] That suggests a general design rule:

- **compact aggressively**
- keep startup memory terse
- store detail externally
- retrieve detail on demand

### Good compaction strategy

- keep a short canonical summary
- keep linked deeper notes outside the base prompt
- collapse repetitive episodes into patterns
- track uncertainty instead of overspecifying

## Memory poisoning defense

OWASP explicitly calls out **memory poisoning** as a core agent risk. [M2] Defenses should include:

- source labels on every memory item
- trust zones (human-authored vs retrieved vs inferred)
- no unsanitized writes from web/docs/email/tool output
- review queue for durable writes
- isolation between users, repos, and campaigns
- reversible memory operations
- anomaly detection for repeated instruction-like memory proposals

## Design pattern for simulation projects

For RPGs, world engines, and companion systems, use a **triple ledger**:

### World ledger
- objective or canon facts
- locations, factions, items, laws, historical events

### Mind ledger
- what each entity believes
- false beliefs allowed
- confidence per belief
- source of belief

### Relationship ledger
- attitude, trust, fear, loyalty, devotion, grudges, debt, attraction
- directional and time-sensitive

This lets you model “what is true” separately from “what someone thinks is true.”

## Practical next build

If you want a powerful but lean first version, implement these tables first:

1. `memory_items`
2. `memory_sources`
3. `memory_reviews`
4. `entity_beliefs`
5. `relationship_states`
6. `memory_compactions`
7. `memory_quarantine`

## Source notes

[M1] Claude Code Docs, *How Claude remembers your project*  
https://code.claude.com/docs/en/memory

[M2] OWASP Cheat Sheet, *AI Agent Security Cheat Sheet*  
https://cheatsheetseries.owasp.org/cheatsheets/AI_Agent_Security_Cheat_Sheet.html
