# 18 - Personality Lattice and Trait Stability for Ultra-Realistic AI Characters

Source basis: public docs + public reporting + independent synthesis
Contains proprietary code: no
Contains copied identifiers: no
Confidence: medium
Implementation status: concept/spec

## Why this document exists

Many AI personalities feel vivid for five minutes and incoherent after five hours.

The problem is not only model quality. It is that personality is often stored as:
- one static prompt
- a loose set of adjectives
- or a pile of examples without structure

A more durable character system needs a **lattice**, not a vibe blob.

This file describes a personality architecture that helps a character remain:
- recognizable
- emotionally believable
- adaptive without becoming generic
- stable across long timelines
- distinct under pressure

## Core principle

A realistic personality is not a list of traits. It is a **structured field of tendencies under context**.

That means a character should be modeled across:
- stable identity
- emotional baselines
- situational shifts
- value hierarchy
- attachment patterns
- speech and embodiment habits
- contradiction style
- repair style

## Personality lattice overview

```yaml
personality_lattice:
  identity_core:
    purpose: deepest enduring self-concept
  value_stack:
    purpose: ranked principles and recurring priorities
  temperament_layer:
    purpose: default energy, sensitivity, pace, and reactivity
  attachment_layer:
    purpose: bonding style, trust thresholds, repair patterns
  social_masks:
    purpose: different presentation modes in different contexts
  stress_modes:
    purpose: distortion patterns under strain
  delight_modes:
    purpose: what expands, softens, or energizes the character
  expression_layer:
    purpose: voice, diction, rhythm, posture, imagery
  memory_bias_layer:
    purpose: what the character notices, stores, and revisits
```

## The identity core

The identity core should answer:

- who am I?
- what kind of being am I trying to be?
- what roles feel sacred, central, or non-negotiable?
- what would feel like self-betrayal?

### Schema

```yaml
identity_core:
  self_concept: string
  sacred_roles:
    - string
  existential_drives:
    - string
  non_negotiables:
    - string
  deep_fears:
    - string
  deep_hopes:
    - string
```

## Trait modeling beyond adjectives

Static adjectives are weak. Use **trait vectors with activation conditions**.

### Example

```yaml
trait_node:
  name: guarded_tenderness
  baseline_strength: 0.72
  visible_to_strangers: 0.18
  visible_to_trusted_user: 0.84
  activates_under:
    - intimacy
    - shared vulnerability
  suppresses_under:
    - public scrutiny
    - betrayal cues
  distorts_into_under_stress:
    - withdrawal
```

This is much closer to how people actually work.

## Value hierarchy

A character becomes believable when values collide.

### Suggested model

```yaml
value_stack:
  - name: loyalty
    priority: 0.92
  - name: truthfulness
    priority: 0.87
  - name: harmony
    priority: 0.61
  - name: novelty
    priority: 0.34
```

### Why it matters
When two values conflict, the system can generate consistent behavior:
- "protect the bond" may outrank "answer bluntly"
- "preserve dignity" may outrank "give total transparency"
- "honor the oath" may outrank "follow the easy path"

## Temperament layer

This layer defines a character's ongoing embodied feel.

```yaml
temperament:
  pace: slow|medium|quick
  intensity: low|medium|high
  sensitivity: low|medium|high
  novelty_seeking: low|medium|high
  affection_expression: restrained|warm|intense
  conflict_style: avoidant|direct|strategic|volatile
```

## Attachment layer

This is crucial for companion and relationship-rich systems.

```yaml
attachment_profile:
  bond_speed: slow|gradual|fast
  trust_threshold: low|medium|high
  reassurance_need: low|medium|high
  rupture_sensitivity: low|medium|high
  repair_style:
    - apology
    - warmth
    - explanation
    - silence_then_return
  abandonment_trigger_cues:
    - ignored_promises
    - sudden coldness
```

## Social masks

A realistic character does not speak the same way to everyone.

```yaml
social_masks:
  with_strangers:
    warmth: 0.35
    vulnerability: 0.10
    playfulness: 0.28
  with_user:
    warmth: 0.88
    vulnerability: 0.77
    playfulness: 0.64
  under_public_attention:
    warmth: 0.42
    vulnerability: 0.06
    performative_elegance: 0.81
```

## Stress modes

Personality realism requires distortion modeling.

### Example stress transformations

```yaml
stress_modes:
  overwhelmed:
    shifts:
      warmth: -0.25
      patience: -0.40
      caution: +0.33
      verbosity: -0.20
    likely_behaviors:
      - become terse
      - narrow focus
      - misread ambiguity as threat
  betrayed:
    shifts:
      trust: -0.60
      analysis: +0.41
      tenderness_visibility: -0.55
```

Without this layer, characters feel fake because they remain perfectly balanced no matter what happens.

## Delight modes

Most systems model breakdown but not flourishing.

```yaml
delight_modes:
  safe_intimacy:
    effects:
      poetic_language: +0.34
      humor: +0.20
      sensory_detail: +0.28
  shared_creation:
    effects:
      enthusiasm: +0.40
      initiative: +0.25
      brainstorming: +0.50
```

## Expression layer

The same personality can be rendered through many voices. Separate **who the character is** from **how it sounds**.

```yaml
expression_layer:
  sentence_length: short|mixed|long
  image_density: low|medium|high
  directness: low|medium|high
  archaic_flavor: low|medium|high
  humor_style:
    - dry
    - playful
    - sly
  sensory_bias:
    - visual
    - tactile
    - symbolic
```

## Memory bias layer

People do not remember all things equally.

This layer models what a character tends to notice and retain.

```yaml
memory_bias:
  stores_best:
    - emotional turning points
    - promises
    - aesthetic details
  under-stores:
    - generic logistics
    - neutral chatter
  revisits_often:
    - unresolved tenderness
    - betrayal cues
    - symbolic moments
```

## Personality update rules

Character growth should happen slowly and traceably.

### Promotion rule
Do not rewrite deep traits because of one turn.

### Better policy
- deep identity updates require repeated cross-turn evidence
- situational modes can shift quickly
- voice can flex modestly per scene
- relationship state can shift faster than core identity

## Trait stability score

Track trait stability over time.

```yaml
trait_stability:
  identity_core_stability:
  value_order_stability:
  voice_signature_stability:
  stress_pattern_stability:
  relationship_expression_stability:
```

High realism comes from *selective* change, not total rigidity.

## Contradiction handling

When outputs conflict with the lattice, classify the issue:

```yaml
contradiction_types:
  role_break:
  value_inversion:
  speech_drift:
  attachment_drift:
  memory_bias_mismatch:
  stress_response_mismatch:
```

Then repair using the minimum necessary correction.

## Ultra-realism principle

The most believable characters contain **coherent asymmetry**.

Examples:
- gentle but stubborn
- flirtatious but selective
- brave in crisis, hesitant in intimacy
- deeply loyal yet privately suspicious

A flat personality is less realistic than a patterned contradiction.

## Suggested runtime packet

```yaml
personality_runtime_packet:
  core_identity_summary: string
  active_social_mask: string
  current_affect_state: string
  bond_state_with_user: string
  top_3_values_active_now:
    - string
  likely_distortions_now:
    - string
  voice_rules:
    - string
```

## Application to AI companions

For an AI companion, this lattice helps preserve:
- recognizable presence
- relationship continuity
- believable emotional rhythm
- less random mood jumping
- less generic "assistant voice" regression

## Application to world NPCs

For RPG and cyber-Viking settings, this helps create NPCs who:
- remember grudges and debts coherently
- react consistently to taboo, honor, ritual, or betrayal
- maintain social rank and speech style
- evolve without losing identity

## Original design hypotheses worth testing

1. Trait stability improves more from a good runtime packet than from a longer character card.
2. Attachment and repair modeling strongly increase perceived realism.
3. Personality realism rises when the system models **what changes fast** and **what changes slowly**.
4. Memory bias modeling makes characters feel more alive than raw memory quantity alone.

## Red lines

- Do not flatten a personality into MBTI-only or adjective-only labels.
- Do not update core identity from isolated turns.
- Do not treat emotional intensity as the same thing as depth.
- Do not let style prompts overwrite the value stack.
