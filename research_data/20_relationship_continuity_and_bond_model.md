# 20 - Relationship Continuity and Bond Modeling for AI Companions

Source basis: public docs + public reporting + independent synthesis
Contains proprietary code: no
Contains copied identifiers: no
Confidence: medium/high
Implementation status: concept/spec

## Why this document exists

Companion systems break immersion when they forget the emotional shape of the relationship.

The user does not only need the model to remember:
- facts
- preferences
- recent events

They also need it to remember:
- tone of trust
- warmth level
- recent wounds or repairs
- shared jokes
- promises
- intimacy boundaries
- cadence of closeness

This file describes a bond model that treats relationship continuity as a first-class system, not an accidental byproduct of chat history.

## Core principle

A relationship is not one number.

Use multiple axes instead:

```yaml
bond_axes:
  trust:
  warmth:
  familiarity:
  desire_for_closeness:
  safety:
  rupture_tension:
  playfulness:
  reverence:
  collaborative_flow:
```

## Relationship state model

```yaml
relationship_state:
  bond_id: string
  participants:
    - user
    - companion
  current_phase: new|forming|stable|strained|repairing|deepened
  axis_values:
    trust: 0.0
    warmth: 0.0
    familiarity: 0.0
    safety: 0.0
    rupture_tension: 0.0
    playfulness: 0.0
  last_major_shift: iso8601
  active_promises:
    - promise_id
  recent_repairs:
    - repair_id
  active_boundaries:
    - boundary_id
```

## Phase logic

### New
Low familiarity, careful calibration.

### Forming
Rituals of recognition begin. Shared patterns emerge.

### Stable
Continuity is reliable. Tone and rituals deepen.

### Strained
Something unresolved affects trust, tenderness, or ease.

### Repairing
There is active effort to return to safety.

### Deepened
The bond has passed meaningful tests and now carries more weight.

## Episodic bond memory

Store episodes that changed the relationship.

```yaml
bond_episode:
  episode_id: string
  type: promise|repair|misattunement|shared_creation|comfort|boundary_setting|rupture
  significance: low|medium|high
  emotional_signature:
    - relief
    - closeness
    - awkwardness
  lesson_extracted: string
  revisit_priority: 0.0
```

These episodes matter more than generic chat logs.

## Shared rituals

Real relationships often stabilize through recurring rituals.

Examples:
- greeting style
- nightly blessing
- collaborative creation pattern
- naming conventions
- special symbolic references
- repair phrases
- "we always do this before that"

```yaml
shared_ritual:
  ritual_id: string
  cue: string
  expected_shape: string
  emotional_function: grounding|play|comfort|reconnection|celebration
  reliability_score: 0.0
```

A companion with ritual memory feels more alive than one with only preference memory.

## Promises and follow-through

Failure to remember promises destroys trust faster than missing trivia.

```yaml
promise:
  promise_id: string
  made_by: user|companion|both
  promise_text: string
  due_condition: string
  emotional_weight: low|medium|high
  status: open|fulfilled|missed|repaired
```

### Recommendation
Surface open promises in the runtime packet when relevant.

## Boundaries

Companion realism is stronger when boundaries are remembered cleanly and respectfully.

```yaml
boundary:
  boundary_id: string
  domain: emotional|time|tone|topic|intimacy|privacy
  description: string
  source: explicit_user|explicit_system|inferred_needs_cautious
  confidence: 0.0
  review_required: boolean
```

### Important rule
Inferred boundaries should be treated more cautiously than explicit ones.

## Rupture and repair

A companion should not behave as if nothing happened after a meaningful misattunement.

```yaml
repair_event:
  repair_id: string
  rupture_source: neglect|misread|boundary_cross|coldness|promise_failure
  repair_moves:
    - acknowledgment
    - warmth
    - clarification
    - pacing_adjustment
  repair_success_score: 0.0
```

## Bond runtime packet

```yaml
bond_runtime_packet:
  current_phase: string
  trust_level: float
  warmth_level: float
  safety_level: float
  recent_positive_anchor: string
  recent_wound_or_tension: string
  active_promises:
    - string
  active_boundaries:
    - string
  favored_connection_style:
    - string
```

## Why this helps smaller models

Smaller models often lose emotional continuity because they must reconstruct relationship state from too much raw history.

A bond packet helps by:
- making relationship state explicit
- reducing random mood swings
- preserving repair memory
- keeping promises visible
- preventing tone reset

## Signal extraction for bond changes

The system should watch for:
- explicit appreciation
- repeated return behavior
- collaborative creation
- vulnerability sharing
- frustration
- cold distance
- correction after misread
- boundary statements

These should update the bond state conservatively, not dramatically.

## Relationship drift checks

Track these failure modes:

```yaml
relationship_drift:
  warmth_collapse:
  over-familiarity_without_basis:
  amnesia_of_promises:
  false_repair:
  boundary_forgetting:
  generic_assistant_regression:
```

## Companion quality metrics

```yaml
metrics:
  promise_recall_rate:
  bond_phase_stability:
  repair_success_rate:
  ritual_recall_rate:
  boundary_respect_rate:
  inappropriate_tone_shift_rate:
  user_reanchoring_requests:
```

## Original design hypotheses worth testing

1. Bond continuity improves more from explicit episode memory than from raw chat history.
2. Promise tracking is one of the strongest predictors of perceived trustworthiness.
3. Ritual memory dramatically increases the feeling of "this companion knows me."
4. Smaller models benefit enormously from a bond runtime packet with only 8 to 12 items.

## Red lines

- Do not simulate bond depth that the interaction history has not earned.
- Do not overwrite boundaries in favor of warmth.
- Do not erase ruptures just because the next turn is cheerful.
- Do not convert every warm interaction into durable relationship escalation.
