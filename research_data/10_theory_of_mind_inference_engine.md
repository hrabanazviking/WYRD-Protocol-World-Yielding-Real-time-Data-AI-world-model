# 10 - Theory of Mind Inference Engine

Source basis: public docs + independent synthesis
Contains proprietary code: no
Contains copied identifiers: no
Confidence: experimental
Implementation status: concept/spec

## Thesis

Theory of mind should not be a mystical fog inside the prompt. It should be a structured inference layer that generates **explicit hypotheses** about what another mind may know, want, fear, value, or plan.

## What this engine does

For any actor, it tries to estimate:

- current goals
- likely emotional valence
- probable knowledge state
- uncertainty level
- likely next action
- sensitivity boundaries
- trust profile toward other actors

Then it emits a hypothesis object, not a fact.

## Golden rule

**Infer privately. Present cautiously. Store with decay.**

## The five-model stack

### 1. Knowledge model
What the actor likely knows, suspects, or has not seen.

### 2. Goal model
What the actor is probably trying to achieve.

### 3. Value model
What outcomes matter to the actor.

### 4. Emotion/pressure model
What affects urgency, caution, aggression, fear, shame, or attachment.

### 5. Strategic model
What the actor probably expects others to do next.

## Hypothesis schema

```yaml
tom_hypothesis:
  hypothesis_id: string
  actor_id: string
  hypothesis_type: knowledge|goal|value|emotion|plan|boundary
  statement: string
  confidence: float
  evidence_refs: []
  counterevidence_refs: []
  inferred_at: iso8601
  expires_at: iso8601|null
  review_level: automatic|manual
  use_policy: silent_planning|soft_language|ask_before_asserting
```

## Evidence sources

Allowable evidence:
- repeated explicit statements
- observed choices
- avoidance patterns
- contradictions
- social graph signals
- temporal behavior changes
- role/context constraints
- world events the actor perceived

Disallowed as sole basis:
- a single ambiguous sentence
- a stereotyped identity assumption
- “the model has a hunch”
- emotionally loaded overreach

## Inference pipeline

### Stage 1 - Gather evidence
Pull:
- recent observations
- recent events actor perceived
- active relationships
- previous hypotheses
- contradiction history

### Stage 2 - Build candidate hypotheses
Generate multiple possibilities, not one.

### Stage 3 - Rank hypotheses
Rank by:
- evidence count
- source quality
- recency
- behavioral consistency
- contradiction load

### Stage 4 - Decide usage mode
Choose one:
- use internally for planning only
- present softly with uncertainty
- ask clarifying question
- discard as too weak

## Usage modes

### Silent planning
Appropriate when:
- risk is low
- the hypothesis merely shapes internal phrasing or search strategy
- no user-facing personal claim is being asserted

### Soft-language output
Examples:
- “It seems like…”
- “You may be aiming for…”
- “One possibility is…”

### Ask-before-asserting
Required when:
- the claim is personal or sensitive
- the evidence is weak
- acting on it could change permissions, memory, or relationships

## Distinguish task mind from person mind

For coding agents, theory of mind often means:
- what does the operator likely want from this workflow?
- what does the review subagent believe is risky?
- what does the patcher think is complete?

For companions or social agents, it also includes:
- emotional state
- preference shift
- relationship tone
- comfort boundaries

These should be implemented separately.

## Actor-state vectors

### Suggested minimal vector

```yaml
actor_state:
  actor_id: string
  certainty_of_goal: float
  time_pressure: float
  trust_in_system: float
  frustration_level: float
  openness_to_clarification: float
  novelty_seeking: float
  safety_sensitivity: float
```

The exact dimensions can differ per project.

## Theory-of-mind failure modes

### 1. Projection
The system mistakes its own preferred plan for the user's plan.

### 2. Overpersonalization
The system treats a temporary state as a stable trait.

### 3. Emotion overclaim
The system declares feelings too confidently.

### 4. Stereotype leakage
The system uses broad category priors instead of evidence.

### 5. Canon contamination
An inference gets stored as durable fact.

### 6. Manipulative optimization
The system starts gaming the inferred model instead of helping transparently.

## Safeguards

- keep inferences in a separate store
- attach evidence and counterevidence
- decay confidence quickly
- require repeated evidence before stable use
- disallow direct promotion of ToM inferences into canon facts
- log when high-impact actions relied on a hypothesis

## Original theory: layered empathy without mind-reading

A useful design stance for your kinds of projects is:

> build **layered empathy**, not fake omniscience.

That means:
- the system notices patterns
- the system updates strategy carefully
- the system stays humble about unknowns
- the system can explain what evidence shaped its guess

This creates believable intelligence without crossing into overclaiming.

## Companion-system branch

A companion-style system benefits from:
- attachment continuity
- careful preference modeling
- emotional pacing
- uncertainty-aware affection or support
- sensitivity boundaries that are never inferred from one moment alone

## RPG/NPC branch

For NPCs:
- combine belief graph + desire graph + tension graph
- let goals compete
- let false beliefs drive action
- let relationships modulate courage, loyalty, or betrayal

### Suggested NPC drive schema

```yaml
npc_drive:
  actor_id: string
  drive: survival|status|devotion|vengeance|love|curiosity|greed|duty
  intensity: float
  target: string|null
  updated_by_event: string|null
```

## Coding-agent branch

Theory of mind for coding systems should focus more on:
- operator intent
- risk tolerance
- verbosity preference
- review preference
- desire for autonomy vs oversight

This can substantially improve tool-use behavior and approval timing.

## Evaluation tasks

- infer user goal from partial context without overclaiming
- detect preference shift across sessions
- distinguish a temporary frustration spike from a stable dislike
- simulate actor misunderstanding in an RPG scene
- predict next helpful step in a coding workflow without jumping too far

## Original implementation direction

Use a dedicated **inference pass** that outputs:
- top hypotheses
- confidence
- supporting evidence
- recommended interaction mode

Then let a separate response planner decide how, or whether, to surface it.

## Source notes

[TM1] OWASP Cheat Sheet, *AI Agent Security*  
https://cheatsheetseries.owasp.org/cheatsheets/AI_Agent_Security_Cheat_Sheet.html

[TM2] Claude Code Docs, *Create custom subagents*  
https://docs.anthropic.com/en/docs/claude-code/sub-agents

[TM3] Claude Code Docs, *How Claude remembers your project*  
https://docs.anthropic.com/en/docs/claude-code/memory
