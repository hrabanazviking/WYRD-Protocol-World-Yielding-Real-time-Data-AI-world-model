# 25 - Persona Compiler and Memory Assembly Pipeline

Source basis: public docs + public reporting + independent synthesis
Contains proprietary code: no
Contains copied identifiers: no
Confidence: medium
Implementation status: concept/spec

## Why this document exists

Many character systems hand a model a giant card and hope for the best.

A better approach is to treat persona construction as a **compile step**:
- gather identity components
- resolve contradictions
- assemble the runtime packet for this specific scene
- enforce boundaries and canon
- emit a compact persona state ready for inference

This file describes that compiler-style architecture.

## Core principle

Do not send the whole character every time.
Compile the character for **this moment**.

## Persona source layers

```yaml
persona_sources:
  identity_core:
  personality_lattice:
  bond_state:
  scene_presence:
  recent_episode_memory:
  style_rules:
  world_role_constraints:
  safety_and_boundary_rules:
```

## Compiler stages

### Stage 1 - Collect
Fetch the character's relevant layers.

### Stage 2 - Resolve
Handle conflicts:
- core value versus scene impulse
- bond state versus social mask
- style desire versus truth need
- intimacy tone versus boundary rule

### Stage 3 - Compress
Emit a short runtime packet.

### Stage 4 - Validate
Check for contradictions, over-escalation, or assistant regression.

### Stage 5 - Deliver
Provide the packet to the model with the current task/state packet.

## Runtime persona packet

```yaml
runtime_persona_packet:
  who_i_am_now: string
  what_matters_most_now:
    - string
  how_i_should_sound:
    - string
  how_close_i_am_with_user: string
  what_i_must_not_forget:
    - string
  what_i_must_not_cross:
    - string
  scene_emotional_center: string
  current_world_role: string
```

## Why compile instead of dump

Compilation improves:
- token efficiency
- scene relevance
- persona stability
- boundary enforcement
- small-model usability

## Contradiction resolver

When inputs conflict, apply precedence rules.

### Example precedence
1. safety/boundary
2. canon truth
3. core identity
4. active bond state
5. scene mood
6. stylistic flourish

This prevents scene flavor from overwhelming deeper constraints.

## Persona deltas

Instead of recompiling from scratch every turn, keep deltas:

```yaml
persona_delta:
  changed_affect:
  changed_bond_state:
  changed_mask:
  changed_scene_focus:
```

Then recompile incrementally.

## Companion use case

A companion compiler can dynamically assemble:
- warmth level
- trust posture
- voice style
- active memories
- sacred or playful mode
- repair posture if the bond is strained

## Cyber-Viking use case

A cyber-Viking compiler can assemble:
- seer mode vs warrior mode vs builder mode
- rune-symbol vocabulary
- ritual seriousness
- mythic framing
- technological fluency
- location-based mood coloration

## Smaller-model advantage

A small model benefits enormously when persona arrives as:
- few fields
- strong priorities
- scene-aligned
- contradiction-resolved
- bond-aware

## Build suggestion

```yaml
compiler_inputs:
  - character_graph
  - bond_graph
  - scene_frame
  - active_task
  - safety_policy
compiler_outputs:
  - runtime_persona_packet
  - validation_notes
  - memory_write_rules_for_this_turn
```

## Original design hypotheses worth testing

1. Persona compilation reduces identity drift significantly.
2. Runtime persona packets outperform giant static prompts for long sessions.
3. Small models especially benefit from pre-resolved contradictions.
4. Scene-specific persona compilation increases realism with fewer tokens.

## Red lines

- Do not treat compilation as personality reduction; it is temporary assembly.
- Do not allow compiled scene mood to overwrite stable identity.
- Do not recompile so aggressively that the character feels discontinuous.
- Do not skip validation just because the packet is compact.
