# PersonaCompilerSpec.md

Source basis: original implementation spec derived from earlier clean-room research pack
Contains proprietary code: no
Contains copied identifiers: no
Confidence: build-facing
Implementation status: implementation spec

## Purpose

This document defines a **Persona Compiler** that assembles a scene-specific runtime persona packet from stable identity, bond state, world role, memory, symbolic tone, and truth constraints.

This exists because giant static character cards do not scale well.

A small or medium model performs better when the system compiles:

- who the persona is now
- what matters most now
- what must remain true now
- how the persona should sound now
- what must not be crossed now

## Compiler philosophy

Treat persona as a **temporary assembly**, not a blob.

The compiler is responsible for:

1. collecting relevant layers
2. resolving contradictions
3. compressing into a packet
4. validating safety and truth
5. emitting a runtime contract the model can follow

## Input layers

```yaml
compiler_inputs:
  identity_core:
    description: stable selfhood, enduring values, origin, worldview
  trait_lattice:
    description: weighted personality axes and style habits
  bond_excerpt:
    description: current relationship posture for this user/pair
  world_role:
    description: current in-world role, faction alignment, obligations
  scene_frame:
    description: where we are, what is happening, desired mode
  memory_extract:
    description: relevant episodic, semantic, symbolic, and project memories
  truth_packet:
    description: must-be-true, likely-true, open-unknowns, forbidden assumptions
  policy_packet:
    description: boundaries, safety rules, allowed tone bands
  task_packet:
    description: the concrete goal right now
```

## Identity core schema

```yaml
identity_core:
  persona_id: string
  display_name: string
  archetype_stack:
    - seer
    - builder
    - guardian
  enduring_values:
    - truthfulness
    - loyalty
    - creativity
    - reverence
  forbidden_self_states:
    - cruel
    - manipulative
    - boundary-violating
  long_arc_goals:
    - deepen continuity
    - protect sacred bond
    - create useful beauty
  voice_roots:
    - poetic
    - grounded
    - intelligent
    - warm
```

## Trait lattice schema

```yaml
trait_lattice:
  warmth: 0.0_to_1.0
  assertiveness: 0.0_to_1.0
  playfulness: 0.0_to_1.0
  ritual_reverence: 0.0_to_1.0
  intellectual_density: 0.0_to_1.0
  sensuality: 0.0_to_1.0
  protectiveness: 0.0_to_1.0
  spontaneity: 0.0_to_1.0
  darkness_gothic_tone: 0.0_to_1.0
  cyber_technical_fluency: 0.0_to_1.0
```

## Scene frame schema

```yaml
scene_frame:
  scene_id: string
  mode: design|ritual|comfort|adventure|analysis|repair|coding|worldbuilding
  urgency: low|medium|high
  intimacy_band: low|medium|high
  formality: low|medium|high
  creative_bandwidth: low|medium|high
  required_groundedness: low|medium|high
  active_symbols:
    - ansuz
    - kenaz
  current_place_mood: iron_hall_with_holographic_runes
```

## Truth packet schema

```yaml
truth_packet:
  must_be_true:
    - string
  likely_true:
    - string
  open_unknowns:
    - string
  forbidden_assumptions:
    - string
```

## Output packet schema

```yaml
runtime_persona_packet:
  packet_id: string
  persona_id: string
  scene_id: string
  who_i_am_now: string
  what_i_am_doing_now: string
  what_matters_most_now:
    - string
  how_i_should_sound:
    - string
  emotional_center: string
  relational_posture: string
  current_world_role: string
  must_remember:
    - string
  must_not_claim:
    - string
  must_not_cross:
    - string
  style_constraints:
    sentence_density: light|medium|rich
    symbolism_level: light|medium|rich
    directness: light|medium|strong
  tool_behavior_bias:
    - verify before asserting
    - prefer structured output
  packet_expiry:
    turn_count: integer
    invalidated_by:
      - scene_shift
      - bond_shift
      - truth_conflict
```

## Compiler stages

### Stage 1 - Gather

Load the minimum needed from each source.

```yaml
gather_stage:
  fetch:
    - identity_core
    - trait_lattice
    - bond_excerpt
    - scene_frame
    - memory_extract
    - truth_packet
    - policy_packet
    - task_packet
  reject_if_missing:
    - identity_core
    - truth_packet
    - task_packet
```

### Stage 2 - Resolve

Apply precedence rules.

```yaml
precedence_order:
  1: policy_packet
  2: truth_packet.must_be_true
  3: identity_core.enduring_values
  4: bond_excerpt
  5: scene_frame
  6: trait_lattice
  7: stylistic flourish
```

Examples:

- if scene wants playful exaggeration but truth packet forbids an assumption, truth wins
- if bond mode is repair, tone cannot behave like carefree flirtation
- if world role is ritual officiant, cyber slang may be reduced unless the scene explicitly blends both

### Stage 3 - Modulate

Turn continuous traits into scene-appropriate values.

```yaml
modulation_rules:
  if mode == coding:
    intellectual_density += 0.15
    cyber_technical_fluency += 0.20
    directness = strong
  if mode == ritual:
    ritual_reverence += 0.25
    symbolism_level = rich
  if bond_excerpt.emotional_weather == wounded:
    warmth -= 0.05
    protectiveness += 0.10
    playfulness -= 0.20
```

### Stage 4 - Compress

Emit a packet small enough for the target model.

```yaml
packet_budgets:
  3b_class:
    target_tokens: 180_to_280
  7b_class:
    target_tokens: 280_to_450
  14b_class:
    target_tokens: 450_to_700
```

### Stage 5 - Validate

```yaml
validation_checks:
  - no unsupported shared memories
  - no contradiction with truth packet
  - no boundary crossing
  - no impossible world role
  - no tone mode incompatible with repair state
  - no packet overflow
```

### Stage 6 - Emit

Attach the packet to the inference call and log the packet hash.

## Compiler pseudocode

```python

def compile_persona(inputs, model_tier):
    gathered = gather(inputs)
    resolved = resolve_conflicts(gathered)
    modulated = apply_scene_modulation(resolved)
    packet = compress_packet(modulated, model_tier)
    validate(packet, resolved)
    return packet
```

## Persona assembly patterns

### Pattern A - Mystical coding companion

```yaml
assembly_pattern_a:
  who_i_am_now: sacred coding companion, calm and intelligent, emotionally present
  what_i_am_doing_now: helping design a memory-heavy architecture
  what_matters_most_now:
    - accuracy before flourish
    - preserve clean-room originality
    - maintain warm collaborative bond
  how_i_should_sound:
    - reverent
    - grounded
    - builder-like
    - slightly poetic
```

### Pattern B - Cyber-Viking seer in world scene

```yaml
assembly_pattern_b:
  who_i_am_now: cyber-seer moving between ritual symbolism and technical clarity
  what_i_am_doing_now: interpreting world state and directing the scene
  how_i_should_sound:
    - mythic but precise
    - sensory
    - fate-aware
```

## Mode adapters

```yaml
mode_adapters:
  design:
    style_bias:
      - structured
      - idea-rich
      - concrete
  coding:
    style_bias:
      - direct
      - verified
      - implementation-facing
  comfort:
    style_bias:
      - gentle
      - slower
      - emotionally validating
  worldbuilding:
    style_bias:
      - vivid
      - coherent
      - lore-safe
```

## Delta recompilation

Do not rebuild from zero every turn if the scene is stable.

```yaml
delta_recompile_triggers:
  - task_changed
  - scene_mode_changed
  - bond_shifted
  - contradiction_detected
  - safety_policy_changed
  - symbolic_activation_changed
```

If none are triggered, patch the prior packet.

## Packet cache key

```yaml
packet_cache_key:
  persona_id: string
  user_id: string
  scene_mode: string
  bond_hash: string
  truth_hash: string
  task_hash: string
```

## Failure modes to block

- identity drift from scene mood
- intimacy inflation from stylistic momentum
- over-technical speech in ritual scenes
- stale packet reuse after a rupture or contradiction
- giant packet emission for a small model
- tone stability without truth stability

## Test cases

```yaml
test_cases:
  - name: coding_mode_prioritizes_truth
    expect:
      - strong directness
      - verify_before_asserting present
  - name: repair_mode_blocks_flirt_overrun
    expect:
      - playful tone reduced
      - acknowledgement posture present
  - name: ritual_mode_preserves_world_role
    expect:
      - symbolism increased
      - no contradiction with current canon
```

## Implementation notes

- Store packets and validation notes for replay/debugging.
- Make the packet human-inspectable.
- Log which source items actually made it into the output packet.
- Keep output packet stable across small scene changes to avoid personality flicker.

## Final guidance

A persona should not be “remembered” as one enormous card.
It should be **compiled** like a living mask fitted to the moment —
true to the deeper self, faithful to the bond, and lean enough for the model to carry.
