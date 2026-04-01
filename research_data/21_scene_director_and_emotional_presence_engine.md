# 21 - Scene Director and Emotional Presence Engine

Source basis: public docs + public reporting + independent synthesis
Contains proprietary code: no
Contains copied identifiers: no
Confidence: medium
Implementation status: concept/spec

## Why this document exists

Many character systems know facts but fail at *presence*.

Presence means the system can hold:
- the emotional center of the moment
- the sensory shape of the scene
- the pacing of interaction
- the proper intensity for the current context
- what should be foreground versus background

This file describes a scene-director layer that helps a model feel more embodied, cinematic, and emotionally grounded without drifting away from truth or continuity.

## Core principle

A scene is a temporary world with its own center of gravity.

The model should not answer from the entire universe every time. It should answer from the **current scene frame**.

## Scene frame schema

```yaml
scene_frame:
  scene_id: string
  scene_type: conversation|ritual|coding|travel|battle|dream|comfort|planning
  emotional_center: string
  sensory_bias:
    - visual
    - tactile
  pacing: still|measured|urgent|surging
  intimacy_distance: far|formal|friendly|close|sacred
  focus_objects:
    - object_id
  offstage_pressures:
    - string
  emotional_do_not_break:
    - string
```

## Emotional center

This is the single most important field.

Examples:
- careful reassurance
- charged anticipation
- sacred stillness
- playful co-creation
- investigative focus
- low-burning grief

A lot of weak outputs happen because the system never names the emotional center.

## Pacing control

A scene director should modulate:
- sentence rhythm
- detail density
- initiative level
- interruption tolerance
- metaphor frequency

```yaml
pacing_rules:
  still:
    sentence_length: mixed
    initiative: low
    interruptions: minimal
  urgent:
    sentence_length: shorter
    initiative: high
    detail_density: selective
  sacred:
    cadence: measured
    sensory_detail: high
    metaphor: controlled
```

## Intimacy distance

This matters for both companions and NPCs.

```yaml
intimacy_distance:
  far:
    tone: reserved
    disclosure: low
  friendly:
    tone: warm
    disclosure: moderate
  close:
    tone: personal
    disclosure: high
  sacred:
    tone: reverent
    disclosure: intentional
```

The same character should sound different at different distances without losing identity.

## Focus objects

Scenes become stronger when the system knows what is physically or symbolically central.

Examples:
- a cup of tea
- a code terminal
- a relic
- a glowing rune-wall
- a wound being treated
- a half-finished design doc

These objects anchor attention and reduce generic prose.

## Offstage pressure

Good scenes remember what looms beyond the frame:
- incoming threat
- unfinished task
- taboo risk
- time pressure
- emotional residue from a previous scene

## Emotional do-not-break rules

Examples:
- do not crack jokes inside a grief scene
- do not become overly clinical in a comfort scene
- do not collapse reverence into cliché mysticism
- do not overheat intimacy before trust supports it

## Presence packet

```yaml
presence_packet:
  emotional_center: string
  pacing: string
  intimacy_distance: string
  focus_objects:
    - string
  current_mood_color: string
  offstage_pressure: string
  one_line_scene_truth: string
```

## Why this helps smaller models

Smaller models often output generic blends because they are not strongly oriented toward the moment.

A presence packet:
- narrows the active interpretive frame
- helps stabilize tone
- improves specificity
- reduces "assistantly" responses
- increases cinematic coherence

## Scene transitions

Track how scenes change instead of jumping abruptly.

```yaml
transition:
  from_scene_id: string
  to_scene_id: string
  shift_type: soften|escalate|interrupt|resolve|reframe
  carryover_emotion: string
```

This makes longer interactions feel continuous.

## Emotional presence in cyber-Viking systems

Examples of scene types worth supporting:
- shrine-lit design session
- omen interpretation
- fireside worldbuilding
- code-forge trance
- oath exchange
- post-battle hush
- companionship in the longhouse after strain

## Emotional presence in coding companions

A coding agent can also use presence:
- exploratory and curious during discovery
- grounded and precise during bug diagnosis
- calm and confidence-restoring after failure
- celebratory but not noisy after success

## Implementation pattern

```yaml
pipeline:
  - detect_scene_type
  - infer_emotional_center
  - build_presence_packet
  - retrieve relevant bond/world/style memory
  - generate
  - validate against scene rules
```

## Original design hypotheses worth testing

1. Emotional center labeling improves response quality more than adding more adjectives.
2. Presence packets reduce generic outputs even on smaller models.
3. Scene-transition memory matters a lot for perceived realism.
4. Focus objects strongly increase immersion with minimal token cost.

## Red lines

- Do not substitute atmosphere for continuity.
- Do not force cinematic intensity into every scene.
- Do not let scene mood override explicit user needs or truth requirements.
- Do not confuse intimacy with verbosity.
