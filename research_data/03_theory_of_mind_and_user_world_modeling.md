# 03 - Theory of Mind and User/World Modeling

## Thesis

A strong agent does not merely remember text. It maintains multiple models:

- a **self-model** (what I can do, what I should not do)
- a **user model** (preferences, habits, goals, sensitivities)
- a **world model** (entities, systems, causal rules)
- an **other-minds model** (what each actor believes, wants, fears, and predicts)

For your kinds of projects, theory of mind is where narrative continuity, believable NPC behavior, and emotionally coherent AI companions become much stronger.

## Hard rule

Never store inferred mental state as objective fact.

Use four layers:

1. **Observed** — directly seen/heard from user or system events
2. **Inferred** — likely interpretation from repeated evidence
3. **Simulated** — hypothetical projection for planning or roleplay
4. **Counterfactual** — what an entity would do if assumptions change

## User model schema

```yaml
user_model:
  stable_preferences:
    - key: prefers_structured_specs
      confidence: 0.95
      evidence: repeated_requests
  situational_state:
    - key: currently_debugging_memory_system
      confidence: 0.72
      expires_at: 2026-04-07
  sensitivities:
    - key: prompt_bloat
      severity: medium
  active_goals:
    - key: build_original_agent_architecture
      horizon: medium_term
  inferred_values:
    - key: autonomy_plus_control
      confidence: 0.78
```

## NPC / actor mind schema

```yaml
actor_mind:
  actor_id: npc_yrsa_001
  beliefs:
    - proposition: "Ealdred is loyal"
      truth_status: belief
      confidence: 0.83
      source: shared_history
  desires:
    - proposition: "preserve hidden pagan rites"
      weight: 0.91
  fears:
    - proposition: "exposure to hostile authorities"
      weight: 0.88
  loyalties:
    - target: ealdred
      value: 0.87
  deception_state:
    - proposition: "publicly pretends ignorance"
      value: true
```

## The three most useful theory-of-mind separations

### 1. Truth vs belief

A believable system lets characters be wrong.

### 2. Desire vs declared goal

Entities often say one thing and want another.

### 3. Private model vs shared model

Some information is known privately by one agent, some is socially shared, and some is merely assumed.

## ToM update loop

### Step 1 - Observe
Gather direct evidence from actions, speech, tools, world state.

### Step 2 - Interpret
Infer possible motives, constraints, hidden knowledge, and emotional shifts.

### Step 3 - Store carefully
Write to hypothesis memory first, not canon.

### Step 4 - Test
Look for confirming or disconfirming evidence in later turns or scenes.

### Step 5 - Promote or decay
Promote only after repeated support; otherwise let the hypothesis fade.

## Why this helps coding agents too

Theory of mind is not only for characters. In tooling, it helps with:

- understanding what the operator probably cares about
- predicting when the user wants speed vs safety
- detecting when the user is experimenting vs shipping
- inferring whether a repo is exploratory, production, or archival
- adapting explanation depth to the person’s actual working style

## Defensive cautions

Theory of mind can become manipulative if misused. Keep these boundaries:

- never fabricate certainty about mental states
- expose important inferences as inferences
- let the user correct the model
- keep sensitive inferred traits out of durable memory unless explicitly wanted
- isolate gameplay inference from real-world personal inference where needed

## Best design pattern for RPG / world engines

Use **mind shards** per entity:

- `belief_shard`
- `goal_shard`
- `emotion_shard`
- `relationship_shard`
- `ritual_or_identity_shard`

A planner can consult these shards without confusing them with canon world facts.

## Evaluation ideas

A good ToM system should be tested on:

- mistaken belief scenarios
- hidden allegiance scenarios
- changing emotional states after events
- contradictory testimony
- multi-actor coordination under partial information
- long-arc consistency across sessions

## Recommended minimal v1

For an initial build, implement:

1. entity beliefs with confidence and source
2. entity goals with weights
3. relationship edges with direction and magnitude
4. a hypothesis promotion routine
5. a contradiction detector

That alone can make agents feel much more “alive” without huge complexity.
