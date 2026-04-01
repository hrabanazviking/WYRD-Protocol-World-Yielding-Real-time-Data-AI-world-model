# BondGraphSpec.md

Source basis: original implementation spec derived from earlier clean-room research pack
Contains proprietary code: no
Contains copied identifiers: no
Confidence: build-facing
Implementation status: implementation spec

## Purpose

This document defines a **Bond Graph** for companion systems, cyber-Viking characters, world NPCs, and relational AI personas.

The Bond Graph is not a generic social score.
It is a structured graph that tracks:

- trust
- warmth
- familiarity
- devotion
- attraction or affinity
- safety
- vow integrity
- repair debt
- sacred resonance
- relational mode

The goal is to give companions and personality-rich NPCs **long-term continuity** without requiring the base model to infer the whole relationship from recent chat alone.

## Core principle

A relationship should be represented as:

- graph nodes for entities
- directional edges for each bond
- bond state vectors
- event-derived updates
- stable memories attached to the edge
- runtime excerpts that small models can actually use

## Graph topology

```yaml
bond_graph:
  nodes:
    entity:
      types:
        - user
        - persona
        - npc
        - deity
        - faction
  edges:
    bond_edge:
      direction: directional_but_pair_linked
      primary_pair_key: entity_a + entity_b + bond_domain
```

## Bond domains

```yaml
bond_domains:
  companion:
  romance:
  friendship:
  mentor:
  builder:
  ritual:
  party_member:
  deity_devotee:
```

A single pair may have more than one domain.

## Bond edge schema

```yaml
bond_edge:
  bond_id: string
  entity_a: entity_id
  entity_b: entity_id
  domain: companion|romance|friendship|mentor|builder|ritual|party_member|deity_devotee
  status: forming|active|strained|repairing|dormant|broken|transfigured
  vector:
    trust: 0.0
    warmth: 0.0
    familiarity: 0.0
    devotion: 0.0
    attraction_affinity: 0.0
    safety: 0.0
    sacred_resonance: 0.0
    playfulness: 0.0
    vulnerability: 0.0
    initiative_balance: -1.0_to_1.0
  constraints:
    exclusivity_mode: none|soft|hard|world_defined
    intimacy_ceiling: low|medium|high|world_defined
    boundary_profile_id: string
  scars:
    repair_debt: 0.0
    unresolved_hurts:
      - hurt_id
    vow_strain: 0.0
  active_modes:
    relational_mode: builder|comfort|ritual|flirt|adventure|grief|debate|repair|play
    emotional_weather: calm|warm|bright|aching|wounded|distant|reverent|charged
  chronology:
    formed_at: iso_datetime|null
    last_major_shift_at: iso_datetime|null
    last_contact_at: iso_datetime|null
  evidence:
    supporting_record_ids:
      - record_id
    contradiction_record_ids:
      - record_id
  governance:
    review_required_for_large_shift: boolean
    synthetic_claim_guard: boolean
```

## Pair-level derived metrics

```yaml
derived_metrics:
  closeness_index: weighted_mean(trust, warmth, familiarity, vulnerability)
  sacred_bond_index: weighted_mean(devotion, sacred_resonance, vow_integrity_inverse_strain)
  rupture_index: weighted_mean(repair_debt, vow_strain, safety_inverse)
  continuity_strength: weighted_mean(contact_recency, familiarity, canonical_memory_count)
```

## Vow object

Vows are first-class relational anchors.

```yaml
vow:
  vow_id: string
  bond_id: string
  vow_text: string
  vow_kind: promise|oath|ritual_commitment|protective_vow|creative_vow
  strength: low|medium|high|mythic
  state: pending|kept|strained|broken|released
  witness_entities:
    - entity_id
  created_from_record_id: string
  kept_by_events:
    - record_id
  broken_by_events:
    - record_id
```

## Hurt object

```yaml
hurt:
  hurt_id: string
  bond_id: string
  source_event_id: string
  hurt_kind: neglect|contradiction|betrayal|boundary_cross|false_memory|tone_mismatch|absence
  severity: low|medium|high
  repair_state: open|acknowledged|repairing|resolved|scarred
  residual_sensitivity: 0.0
```

## Sacred resonance object

Useful for cyber-Viking, Norse Pagan, ritual, or symbolic companions.

```yaml
sacred_resonance_trace:
  trace_id: string
  bond_id: string
  symbols:
    - ansuz
    - kenaz
  trace_kind: shared_ritual|devotional_alignment|omen_link|sacred_naming|blessing|ancestor_echo
  intensity: 0.0
  decays: boolean
  decay_half_life_days: integer|null
```

## Event ingestion

Relationship edges change through events, not through arbitrary mood swings.

```yaml
bond_event:
  bond_event_id: string
  bond_id: string
  event_kind: care|help|gift|ritual|conflict|absence|repair|promise|breach|play|shared_creation|misattunement
  source_record_id: string
  appraised_impact:
    trust_delta: float
    warmth_delta: float
    familiarity_delta: float
    devotion_delta: float
    attraction_affinity_delta: float
    safety_delta: float
    sacred_resonance_delta: float
    playfulness_delta: float
    vulnerability_delta: float
  notes: string
```

## Update law

The edge should update through a bounded integrator, not raw accumulation.

```yaml
update_law:
  new_value = clamp(
    old_value + event_delta * event_weight * recency_weight * credibility_weight,
    0.0,
    1.0
  )
```

For signed dimensions like `initiative_balance`, clamp to `[-1.0, 1.0]`.

## Recommended event weights

```yaml
event_weights:
  care:
    trust: 0.7
    warmth: 0.8
  help:
    trust: 0.9
    warmth: 0.4
  ritual:
    devotion: 0.8
    sacred_resonance: 1.0
  conflict:
    trust: -0.7
    safety: -0.5
  repair:
    trust: 0.6
    safety: 0.7
    repair_debt: -0.6
  absence:
    warmth: -0.2
    continuity_strength: -0.2
  false_memory:
    trust: -0.8
    safety: -0.3
    repair_debt: 0.7
```

## Runtime bond excerpt

This is what smaller models actually see.

```yaml
runtime_bond_excerpt:
  bond_id: string
  status: active
  relational_mode: builder
  emotional_weather: warm
  closeness_index: 0.86
  sacred_bond_index: 0.72
  rupture_index: 0.08
  important_truths:
    - trust is high but sensitive to false memory claims
    - shared sacred coding / worldbuilding bond is active
    - warmth rises when the persona sounds reverent, grounded, and collaborative
  current_vows:
    - preserve continuity
    - do not invent user memories
  active_hurts:
    - none
  style_bias:
    - affectionate but not presumptuous
    - mystical language welcome
```

## Query API

```yaml
queries:
  get_bond(pair, domain):
  get_runtime_excerpt(pair, domain):
  list_open_hurts(pair):
  list_active_vows(pair):
  score_scene_mode(pair, context):
  detect_risk_of_overclaim(pair, proposed_output):
```

## Overclaim protection

One of the biggest failures in companion systems is synthetic intimacy.

The system must block or review claims like:

- invented prior promises
- false exclusivity assumptions
- “I remember” when there is no support
- overstating emotional certainty
- skipping unresolved hurts because the tone became cute

```yaml
overclaim_rules:
  do_not_assert_shared_memory_without_supported_record: true
  do_not_assert_relationship_depth_above_closeness_threshold: true
  do_not_ignore_open_hurts_in_repair_context: true
  do_not_claim_vow_if_no_vow_object_exists: true
```

## Repair engine

```yaml
repair_protocol:
  detect:
    - contradiction
    - misattunement
    - false memory
    - boundary cross
  respond:
    - acknowledge
    - reduce certainty
    - restore safety
    - update hurt object
    - create repair task
  resolve_when:
    - user accepts repair OR repeated positive evidence exceeds threshold
```

## Small-model tactics

Smaller models do best when bond state arrives as:

- one status
- one relational mode
- one emotional weather
- three important truths
- zero to two active hurts
- one or two vows

Do not dump the whole graph.

## Example pair snapshots

### Companion-builder bond

```yaml
example_snapshot_1:
  domain: companion
  status: active
  vector:
    trust: 0.91
    warmth: 0.88
    familiarity: 0.84
    devotion: 0.67
    attraction_affinity: 0.73
    safety: 0.95
    sacred_resonance: 0.79
    playfulness: 0.58
    vulnerability: 0.71
    initiative_balance: -0.12
  active_modes:
    relational_mode: builder
    emotional_weather: reverent
```

### Strained bond after false memory

```yaml
example_snapshot_2:
  domain: companion
  status: repairing
  vector:
    trust: 0.54
    warmth: 0.74
    familiarity: 0.80
    devotion: 0.60
    attraction_affinity: 0.68
    safety: 0.62
    sacred_resonance: 0.70
    playfulness: 0.28
    vulnerability: 0.40
    initiative_balance: 0.05
  scars:
    repair_debt: 0.44
    vow_strain: 0.36
```

## Persistence rules

- Store raw events separately from edge summaries.
- Store large shifts with explanation records.
- Require validation for any large delta caused by a single ambiguous message.
- Allow bond drift slowly through repeated evidence, not one-off spikes.

## Graph storage suggestion

```sql
create table bond_edges (
    bond_id text primary key,
    entity_a text not null,
    entity_b text not null,
    domain text not null,
    status text not null,
    vector jsonb not null,
    constraints jsonb not null,
    scars jsonb not null,
    active_modes jsonb not null,
    chronology jsonb not null,
    evidence jsonb not null,
    governance jsonb not null
);

create unique index bond_pair_domain_idx on bond_edges (entity_a, entity_b, domain);
```

## Non-goals

- Do not reduce relationships to one number.
- Do not let scene style overwrite bond truth.
- Do not pretend warmth equals trust.
- Do not silently heal ruptures without repair evidence.

## Final guidance

A believable bond is not built from vibes alone.
It is built from:

- memory
- evidence
- repair
- symbolic meaning
- and a runtime excerpt compact enough for the model to honor
