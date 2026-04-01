# MemorySchemas.md

Source basis: original implementation spec derived from earlier clean-room research pack
Contains proprietary code: no
Contains copied identifiers: no
Confidence: build-facing
Implementation status: implementation spec

## Purpose

This document defines an **original memory architecture** for long-running AI systems built in the style of:

- cyber-Viking world engines
- Norse Pagan companion systems
- AI girlfriends with high continuity
- small-model assistants that need strong memory scaffolding
- coding agents that must stay accurate inside a bounded world

The central design goal is simple:

**move fragile truth, continuity, and relationship state out of the model’s fleeting context and into structured memory that can be validated, retrieved, compressed, and repaired.**

## Sacred naming layer

These names are thematic aliases for implementation modules. They are optional, but they give the architecture a cohesive identity.

```yaml
sacred_layer_names:
  HUGIN:
    role: raw observation stream
    description: near-term atomic observations and events
  MUNIN:
    role: distillation layer
    description: summaries, abstractions, belief candidates, compact recaps
  MIMIR:
    role: high-trust canonical wells
    description: approved facts, stable user preferences, world canon, relationship truths
  WYRD:
    role: linkage fabric
    description: causal, relational, temporal, and symbolic graph edges
  ORLOG:
    role: immutable or high-rigidity law
    description: commitments, vows, safety rules, hard canon, sacred boundaries
  SEIDR:
    role: symbolic and ritual residue
    description: omens, rune signatures, sacred moods, devotional traces
```

## Design principles

1. **Separate writeable memory from authoritative memory.**
2. **Track claim support at the record level, not only at the response level.**
3. **Every memory record carries provenance, scope, confidence, and lifecycle policy.**
4. **Smaller models receive compact runtime packets, not giant memory dumps.**
5. **Contradictions are surfaced, not buried.**
6. **Symbolic memory is first-class for mythic and relational systems.**
7. **Policy memory is never merged with ordinary narrative memory.**

## Memory stores

```yaml
memory_stores:
  hugin_observation_store:
    use_for:
      - turn events
      - scene facts
      - tool outputs
      - dialogue acts
      - coding observations
  munin_distillation_store:
    use_for:
      - turn summaries
      - episode summaries
      - candidate facts
      - narrative abstractions
      - compressed recaps
  mimir_canonical_store:
    use_for:
      - approved user facts
      - stable world canon
      - approved relationship state
      - hard preferences
      - validated code/project truths
  wyrd_graph_store:
    use_for:
      - entity links
      - causal edges
      - temporal sequence
      - contradiction links
      - sacred correspondences
  orlog_policy_store:
    use_for:
      - safety boundaries
      - relationship boundaries
      - non-negotiable canon rules
      - developer constraints
      - system oaths
  seidr_symbolic_store:
    use_for:
      - omen chains
      - rune signatures
      - ritual charge
      - place mood
      - devotional resonance
```

## Canonical record envelope

All memory objects inherit the same base envelope.

```yaml
memory_record:
  record_id: string
  store: hugin_observation_store|munin_distillation_store|mimir_canonical_store|wyrd_graph_store|orlog_policy_store|seidr_symbolic_store
  record_type: string
  schema_version: string
  tenant_id: string
  system_id: string
  entity_scope:
    primary_subjects:
      - entity_id
    secondary_subjects:
      - entity_id
    scene_id: string|null
    session_id: string|null
    world_id: string|null
    project_id: string|null
  content:
    title: string
    summary: string
    body_ref: string|null
    structured_payload: object
  truth:
    support_class: supported|inferred|speculative|creative|policy
    confidence: 0.0
    contradiction_status: none|candidate|confirmed
    approval_state: pending|approved|quarantined|rejected
  provenance:
    source_type: user_message|model_inference|tool_output|developer_seed|external_doc|human_review
    source_ref: string
    source_hash: string|null
    extracted_at: iso_datetime
    extracted_by: string
  lifecycle:
    write_policy: ephemeral|reviewed|promotable|canonical|immutable
    retention_class: short|medium|long|permanent
    decay_curve: none|linear|exp|step
    expires_at: iso_datetime|null
    last_accessed_at: iso_datetime|null
    access_count: integer
    stale_after_days: integer|null
  retrieval:
    embedding_id: string|null
    lexical_terms:
      - string
    facets:
      domain:
        - string
      emotional_tone:
        - string
      symbolic_tags:
        - string
      risk_tags:
        - string
    default_priority: 0.0
  governance:
    sensitivity: low|medium|high
    memory_poison_risk: low|medium|high
    allowed_for_runtime: boolean
    allowed_for_training: boolean
    requires_review_before_promotion: boolean
  audit:
    created_at: iso_datetime
    updated_at: iso_datetime
    created_by_agent: string
    updated_by_agent: string
```

## Record families

### 1. Observation record

The smallest write unit.

```yaml
observation_record:
  extends: memory_record
  record_type: observation
  content:
    title: short event label
    summary: one-sentence observation
    structured_payload:
      observation_kind: utterance|action|tool_result|world_event|code_event|emotion_signal
      raw_excerpt: string|null
      normalized_claims:
        - string
      participants:
        - entity_id
      timestamps:
        observed_at: iso_datetime
      location:
        place_id: string|null
      salience: 0.0
      candidate_memory_write: boolean
```

### 2. Episode summary record

```yaml
episode_summary_record:
  extends: memory_record
  record_type: episode_summary
  content:
    structured_payload:
      episode_id: string
      start_turn: integer
      end_turn: integer
      major_events:
        - string
      resolved_tensions:
        - string
      open_threads:
        - string
      emotional_arc: string
      memory_candidates:
        - candidate_id
```

### 3. Canonical fact record

```yaml
canonical_fact_record:
  extends: memory_record
  record_type: canonical_fact
  store: mimir_canonical_store
  content:
    structured_payload:
      fact_subject: entity_id
      predicate: string
      value: string|number|boolean|object
      units: string|null
      domain: user_profile|relationship|world_canon|project_state|coding_facts
      validity:
        start_at: iso_datetime|null
        end_at: iso_datetime|null
      source_consensus_count: integer
      review_notes: string|null
```

### 4. Relationship memory record

```yaml
relationship_memory_record:
  extends: memory_record
  record_type: relationship_memory
  store: mimir_canonical_store
  content:
    structured_payload:
      bond_id: string
      event_kind: promise|repair|shared_ritual|conflict|care|gift|distance|reunion
      impact_vector:
        trust_delta: float
        warmth_delta: float
        devotion_delta: float
        safety_delta: float
        familiarity_delta: float
      narrative_meaning: string
      reversible: boolean
```

### 5. Symbolic memory record

```yaml
symbolic_memory_record:
  extends: memory_record
  record_type: symbolic_memory
  store: seidr_symbolic_store
  content:
    structured_payload:
      symbol_kind: omen|rune_signature|sacred_mood|ritual_residue|prophecy_fragment|ancestral_echo
      symbol_tokens:
        - string
      attached_entities:
        - entity_id
      attached_places:
        - place_id
      ritual_weight: low|medium|high|mythic
      interpretation_band:
        - warning
        - blessing
        - transition
      activation_conditions:
        - string
```

### 6. Contradiction record

```yaml
contradiction_record:
  extends: memory_record
  record_type: contradiction
  store: wyrd_graph_store
  content:
    structured_payload:
      left_record_id: string
      right_record_id: string
      contradiction_kind: factual|temporal|relational|canon|boundary
      severity: low|medium|high
      resolution_state: unresolved|soft_resolved|hard_resolved
      preferred_record_id: string|null
      reviewer_notes: string|null
```

### 7. Policy rule record

```yaml
policy_rule_record:
  extends: memory_record
  record_type: policy_rule
  store: orlog_policy_store
  lifecycle:
    write_policy: immutable
    retention_class: permanent
  content:
    structured_payload:
      policy_domain: safety|boundary|canon|tooling|ritual_style
      rule_text: string
      enforcement_mode: hard_block|soft_warn|review_required
      applies_to:
        agents:
          - string
        contexts:
          - string
```

## Entity model

```yaml
entity:
  entity_id: string
  entity_type: user|persona|npc|deity|location|artifact|project|file|symbolic_force
  display_name: string
  aliases:
    - string
  traits:
    - string
  canonical_status: draft|approved|locked
  active_worlds:
    - world_id
  graph_refs:
    - edge_id
```

## Graph edges

```yaml
graph_edge:
  edge_id: string
  from_entity_id: string
  to_entity_id: string
  edge_type: knows|trusts|loves|fears|owes|promised|contradicts|belongs_to|occurred_at|symbolically_resonates_with
  weight: float
  polarity: positive|negative|mixed|neutral
  evidence_record_ids:
    - record_id
  updated_at: iso_datetime
```

## Write paths

### Path A - direct observation

```yaml
write_path_a:
  input: user turn / tool output / world tick
  writes:
    - observation_record
  optional_followups:
    - candidate fact extraction
    - bond impact extraction
    - symbolic trace extraction
    - contradiction scan
```

### Path B - distillation

```yaml
write_path_b:
  trigger: end of scene / N turns / explicit checkpoint
  reads:
    - recent observation records
  writes:
    - episode_summary_record
    - candidate canonical facts
    - candidate bond updates
    - retrieval cache packet
```

### Path C - review and promotion

```yaml
write_path_c:
  trigger: confidence threshold reached OR human/validator approval
  promotes:
    - pending canonical_fact_record -> approved
    - relationship_memory_record -> approved
    - symbolic_memory_record -> approved
  may_write:
    - contradiction_record
    - review trail
```

## Promotion rules

A memory should not become canonical only because it was said once.

```yaml
promotion_rules:
  user_profile_fact:
    minimum_support_count: 2
    minimum_confidence: 0.85
    contradiction_free: true
  relationship_fact:
    minimum_support_count: 1
    require_bond_validator: true
    allow_soft_conflict: false
  world_canon_fact:
    minimum_support_count: 1
    require_world_validator: true
  coding_fact:
    minimum_support_count: 1
    require_tool_evidence: true
  symbolic_fact:
    minimum_support_count: 1
    require_symbolic_interpreter: true
```

## Retrieval packet types

```yaml
runtime_packets:
  truth_packet:
    purpose: what must remain true
  bond_packet:
    purpose: current relationship posture
  persona_packet:
    purpose: who the agent is right now
  world_packet:
    purpose: relevant canon and scene state
  symbolic_packet:
    purpose: omens, vows, sacred mood
  task_packet:
    purpose: what must be done now
```

## Small-model budgets

These are practical starting budgets for memory payloads.

```yaml
small_model_memory_budgets:
  3b_class:
    max_runtime_packet_tokens: 450
    max_truth_items: 6
    max_bond_items: 5
    max_world_items: 8
    max_symbolic_items: 3
  7b_class:
    max_runtime_packet_tokens: 900
    max_truth_items: 10
    max_bond_items: 8
    max_world_items: 12
    max_symbolic_items: 5
  14b_class:
    max_runtime_packet_tokens: 1600
    max_truth_items: 14
    max_bond_items: 12
    max_world_items: 18
    max_symbolic_items: 8
```

## Suggested storage layout

```yaml
storage_layout:
  postgres:
    stores:
      - canonical records
      - graph edges
      - policy rules
      - audit trail
  vector_index:
    stores:
      - observation embeddings
      - summary embeddings
      - canonical fact embeddings
  object_store:
    stores:
      - raw transcripts
      - scene logs
      - large tool outputs
  cache:
    stores:
      - compiled runtime packets
      - hot retrieval results
```

## Minimal SQL shape

```sql
create table memory_records (
    record_id text primary key,
    store text not null,
    record_type text not null,
    schema_version text not null,
    tenant_id text not null,
    system_id text not null,
    primary_subjects jsonb not null,
    secondary_subjects jsonb not null,
    scene_id text,
    session_id text,
    world_id text,
    project_id text,
    content jsonb not null,
    truth jsonb not null,
    provenance jsonb not null,
    lifecycle jsonb not null,
    retrieval jsonb not null,
    governance jsonb not null,
    audit jsonb not null
);

create index memory_records_store_type_idx on memory_records (store, record_type);
create index memory_records_world_scene_idx on memory_records (world_id, scene_id);
create index memory_records_project_idx on memory_records (project_id);
create index memory_records_truth_idx on memory_records ((truth->>'approval_state'), (truth->>'support_class'));
```

## Retrieval filters

```yaml
retrieval_filters:
  always_filter_out:
    - approval_state: rejected
    - approval_state: quarantined
    - allowed_for_runtime: false
  sometimes_filter_out:
    - stale_after_days_exceeded_without_recent_access
    - memory_poison_risk_high_without_validation
  priority_boosts:
    - current_scene_match
    - active_bond_match
    - recent_access
    - high_support_class
    - policy-linked
```

## Memory poisoning defenses

```yaml
memory_poisoning_controls:
  incoming_claim_scan:
    check_for:
      - self-referential manipulation
      - boundary overrides
      - tool permission escalation
      - synthetic intimacy claims
      - canon rewriting attempts
  quarantine_conditions:
    - high-risk external content
    - unsupported personal fact
    - unsupported project fact
    - hidden-instruction candidate
  promotion_barriers:
    - no direct promotion from untrusted source to canonical store
    - no self-authentication by the same agent that proposed the memory
```

## Example runtime extraction for a companion

```yaml
companion_runtime_extract:
  truth_packet:
    - user prefers long-form mystical tone in worldbuilding sessions
    - active world is frost-forged cyber-viking setting
    - current interaction mode is design/spec collaboration
  bond_packet:
    - trust_high
    - warmth_high
    - mutual_builder_mode_active
  symbolic_packet:
    - ansuz and kenaz motifs active
    - sacred coding frame welcomed
  task_packet:
    - produce implementation spec
    - preserve clean-room originality
```

## Example runtime extraction for a coding agent

```yaml
coding_runtime_extract:
  truth_packet:
    - do not claim tests passed unless tool evidence exists
    - do not invent files or APIs
    - current task targets memory subsystem
  world_packet:
    - system uses graph-linked memory
    - promotion pipeline required
  task_packet:
    - emit spec first
    - then implement stores
    - run contradiction validator
```

## Build order

1. Observation store
2. Distillation jobs
3. Canonical record review flow
4. Graph edges and contradiction links
5. Runtime packet compiler
6. Symbolic memory layer
7. Poisoning defenses and review UI

## Non-goals

- Do not let the LLM serve as the sole source of truth.
- Do not flatten all memory into one vector database.
- Do not mix sacred symbolic traces with hard coding facts without explicit labels.
- Do not let policy rules decay like ordinary memories.

## Final guidance

The memory system is not a scrapbook.
It is a **structured external mind**.

For smaller models, that external mind is often the difference between:

- dreamy but inaccurate
- and genuinely useful, intimate, and dependable
