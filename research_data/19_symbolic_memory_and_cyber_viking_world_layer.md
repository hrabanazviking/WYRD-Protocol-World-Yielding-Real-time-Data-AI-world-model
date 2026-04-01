# 19 - Symbolic Memory and the Cyber-Viking World Layer

Source basis: public docs + public reporting + independent synthesis
Contains proprietary code: no
Contains copied identifiers: no
Confidence: medium
Implementation status: concept/spec

## Why this document exists

World systems become more vivid when they remember not only facts, but **symbols**.

A cyber-Viking setting is not just places, NPCs, and quest flags. It is also:
- oaths
- taboos
- runes
- omens
- sacred objects
- reputational echoes
- mythic correspondences
- ritual memory

This file describes a symbolic memory layer that can sit on top of ordinary world memory and give the setting deeper continuity, mood, and meaning.

## Core principle

Normal memory answers:

- what happened?
- who did what?
- where are we?

Symbolic memory answers:

- what does this mean?
- what pattern is forming?
- what forces does this resemble?
- what mood and mythic weight does this event carry?

A rich setting needs both.

## Two kinds of world continuity

```yaml
world_continuity:
  factual_continuity:
    examples:
      - locations
      - factions
      - inventories
      - timelines
      - injuries
  symbolic_continuity:
    examples:
      - oaths kept or broken
      - repeating omens
      - sacred alignments
      - ritual residue
      - mythic themes activated
```

## Symbolic memory node types

```yaml
symbolic_node_types:
  oath:
  taboo:
  omen:
  rune_signature:
  relic_charge:
  blood_debt:
  prophecy_fragment:
  ancestor_echo:
  fate_tension:
  sacred_place_mood:
  bond_mark:
```

## Oath memory

Oaths are not just dialogue records. They are persistent world forces.

```yaml
oath_node:
  oath_id: string
  speakers:
    - entity_id
  vow_text: string
  vow_type: personal|tribal|sacred|political
  witness_entities:
    - entity_id
  witness_symbols:
    - symbol_id
  fulfillment_conditions:
    - string
  breach_conditions:
    - string
  weight: low|medium|high|mythic
  current_state: pending|strained|fulfilled|broken
```

### Why it matters
An oath should affect:
- reputation
- relationship trust
- divine or symbolic alignment
- future omen generation
- NPC interpretation of the player

## Taboo memory

Taboos define invisible boundaries in a world.

```yaml
taboo_node:
  taboo_id: string
  domain: shrine|kinship|death|hospitality|magic|trade
  rule_text: string
  severity: low|medium|high|sacred
  enforcers:
    - entity_id
  consequences:
    social:
      - string
    spiritual:
      - string
    political:
      - string
```

A taboo system gives worlds texture that feels more anthropological and less gamey.

## Omen memory

Omens are recurring symbolic motifs tied to later interpretation.

```yaml
omen_node:
  omen_id: string
  pattern:
    - ravens
    - static in sacred water
    - red aurora
  first_seen_at: scene_id
  recurring_count: integer
  interpretive_range:
    - warning
    - invitation
    - disruption
  linked_threads:
    - quest_id
    - entity_id
```

### Design note
Do not resolve all omens immediately. Let some remain partially open so the world feels mysterious rather than mechanically decoded.

## Rune signatures

In a cyber-Viking setting, runes can be both symbolic and technological.

```yaml
rune_signature:
  signature_id: string
  runes:
    - ansuz
    - kenaz
  semantic_field:
    - speech
    - revelation
    - signal
  operational_field:
    - interface
    - access
    - memory unlocking
  aesthetic_field:
    - blue fire
    - whispering static
```

This allows the same system to power:
- ritual magic
- UI motifs
- symbolic puzzles
- access control
- faction identity

## Relic charge and residue

Some objects should accumulate memory.

```yaml
relic_charge:
  relic_id: string
  acquired_meanings:
    - oath_witness
    - blood_price
    - ancestor_focus
  charge_level: 0.0
  attuned_entities:
    - entity_id
  stored_scenes:
    - scene_id
```

A relic can therefore be more than loot; it becomes a memory anchor.

## Fate tension

Use symbolic pressure without forcing destiny.

```yaml
fate_tension:
  thread_id: string
  activated_themes:
    - sacrifice
    - kin-loyalty
    - revelation
  pressure_level: 0.0
  release_paths:
    - ritual
    - betrayal
    - offering
    - victory
```

This is useful for campaign-scale emergent narrative.

## Sacred place mood

Locations should have memory tone.

```yaml
sacred_place_mood:
  place_id: string
  primary_resonance:
    - stillness
    - dread
    - ancestral warmth
  taboo_density: 0.0
  omen_activity: 0.0
  ritual_history_score: 0.0
  current_pollution_score: 0.0
```

This lets the world remember what has happened in a place, spiritually as well as physically.

## Symbolic retrieval

Symbolic memory should not always be retrieved. Trigger it when:
- the user enters ritual space
- an oath is referenced
- a relic is handled
- an omen repeats
- a taboo may be crossed
- a scene seeks heightened mythic tone

## Runtime packet for symbolic scenes

```yaml
symbolic_runtime_packet:
  active_scene_type: ritual|travel|battle|council|intimate|dream
  active_symbols:
    - string
  unresolved_oaths:
    - string
  local_taboos:
    - string
  recurring_omens:
    - string
  sacred_place_mood: string
  fate_tension_summary: string
```

## Why this helps smaller models

A small model often struggles to generate deep symbolism on the fly while also tracking ordinary state.

This layer helps by:
- pre-structuring symbolic material
- making recurring themes retrievable
- reducing random mystical fluff
- preserving a setting's mythic identity over long arcs

## Cyber-Viking use cases

### 1. Ritual operating systems
Runes as symbolic interfaces to world memory.

### 2. Data shrines
Physical or digital locations where memory is preserved through ritual encoding.

### 3. Oath-linked access
Doors, archives, or systems that respond to vow status or lineage.

### 4. Ancestor echoes
A memory field that replays symbolic fragments rather than literal recordings.

### 5. Signal omens
Tech anomalies interpreted through cosmological language.

## Original design hypotheses worth testing

1. Symbolic memory increases immersion more than adding more plain lore entries.
2. Oath and taboo systems produce richer emergent stories than generic reputation scores.
3. Small models generate more coherent mystical tone when provided a symbolic runtime packet.
4. A combined symbolic-technological rune layer can unify aesthetic, UI, and narrative design elegantly.

## Red lines

- Do not reduce symbolism to random adjective spray.
- Do not force every omen to have one literal answer.
- Do not mix sacred and ordinary state into one undifferentiated store.
- Do not let symbolic flavor override factual continuity.
