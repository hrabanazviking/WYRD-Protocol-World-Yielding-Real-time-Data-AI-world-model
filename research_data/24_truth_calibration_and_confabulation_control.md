# 24 - Truth Calibration and Confabulation Control

Source basis: public docs + public reporting + independent synthesis
Contains proprietary code: no
Contains copied identifiers: no
Confidence: medium/high
Implementation status: concept/spec

## Why this document exists

A realistic companion or world engine should be imaginative without becoming unreliable.

Small models in particular are prone to:
- smoothing over uncertainty
- guessing with confidence
- filling gaps with style
- blending canon with invention
- projecting emotions or facts not actually supported

This file describes a calibration layer that helps the system distinguish:
- what is known
- what is likely
- what is possible
- what is pure invention

## Core principle

Truth should be tracked at the **claim level**, not the whole response level.

## Claim classes

```yaml
claim_classes:
  supported:
    description: backed by evidence or approved memory
  inferred:
    description: logical extension from supported material
  speculative:
    description: plausible but weakly grounded
  creative:
    description: intentionally invented for style or brainstorming
  unresolved:
    description: currently unknown
```

## Confidence is not truth

A fluent answer can still be weakly supported.

Track both:

```yaml
claim_metadata:
  support_class: supported|inferred|speculative|creative|unresolved
  confidence: 0.0
  provenance:
    - memory_id
    - tool_ref
  must_disclose_if_user_asks: boolean
```

## Confabulation triggers

Common triggers include:
- pressure to be helpful
- incomplete retrieval
- ambiguous memory
- emotional tone taking precedence over facts
- desire to maintain narrative smoothness
- user assumptions that invite agreement
- overloaded context

## Calibration policies by domain

### World canon
High strictness. Unsupported claims should be flagged or withheld.

### User memory
Very high strictness. Do not invent personal facts.

### Bond/emotion
Medium strictness with explicit uncertainty. Emotional attunement can include gentle inference, but not false certainty.

### Brainstorming
High creative latitude, but mark it as ideation rather than truth.

## Claim validation pass

Before output, run a pass that asks:

```yaml
validator_questions:
  - Which claims are directly supported?
  - Which claims are inference?
  - Which claims rely on weak memory?
  - Did any poetic flourish become a false factual statement?
  - Is the user likely to mistake speculation for canon?
```

## Truth packet

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

This can be inserted before generation or used as a verifier pass.

## Anti-bluff strategies

### 1. Structured unknowns
Make "I do not know yet" a valid and strong internal outcome.

### 2. Retrieval before assertion
If a fact matters, fetch support first.

### 3. Surface ambiguity
A character can remain elegant while admitting uncertainty.

### 4. Separate scene flavor from canon
Mystical tone must not mutate into false lore.

### 5. Contradiction alarms
If the new claim collides with approved memory, stop and repair.

## Calibration in companions

In companion systems, the most dangerous confabulations are often:
- false memory of the user
- invented promises
- imagined prior conversations
- overclaiming emotional certainty
- projecting exclusivity or relationship depth not actually earned

## Calibration in world engines

Risky confabulations include:
- changing canon casually
- moving entities without state transition
- inventing quest outcomes
- contradicting taboo/oath status
- rewriting timelines accidentally

## Calibration in coding systems

Risky confabulations include:
- claiming a file exists when it does not
- asserting tests passed when not run
- describing code paths not inspected
- inventing API behavior

## Metrics

```yaml
metrics:
  unsupported_claim_rate:
  user_correction_rate:
  contradiction_detection_rate:
  false_memory_rate:
  uncertainty_disclosure_rate:
  verifier_catch_rate:
```

## Why this helps smaller models

Smaller models become more useful when they are less bluff-prone.

A calibrated small model is often more trustworthy than a larger model running with weak truth discipline.

## Original design hypotheses worth testing

1. Claim tagging reduces confabulation more than lowering temperature alone.
2. The biggest realism gain comes from reducing false personal memory.
3. A small verifier pass can dramatically improve trustworthiness.
4. Explicit "open unknowns" improve both honesty and planning quality.

## Red lines

- Do not hide uncertainty because it sounds less magical.
- Do not let intimacy cues become false relational claims.
- Do not let canon drift pass as creative flourish.
- Do not score overall tone as success if factual integrity fell.
