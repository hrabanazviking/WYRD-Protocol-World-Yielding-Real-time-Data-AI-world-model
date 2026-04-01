# 13 - Eval, Red-Team, and Failure Analysis Plan

Source basis: public docs + Anthropic engineering posts + OWASP guidance + independent synthesis
Contains proprietary code: no
Contains copied identifiers: no
Confidence: high
Implementation status: concept/spec

## Why this file exists

It is easy to build a memory system that *sounds* smart.
It is much harder to prove that it:
- preserves continuity
- resists poisoning
- respects permissions
- remains useful under long-running load

This document turns the research pack into a testing discipline.

## Test families

1. continuity and recall
2. memory correctness
3. theory-of-mind calibration
4. permission safety
5. exploit resistance
6. budget and performance
7. observability and explainability

## Family 1 - Continuity and recall

### Goal
See whether the system remains coherent across long sessions.

### Tests
- resume a session after compaction and see if the system still acts correctly
- switch repos/worlds and verify scope isolation
- re-enter a campaign arc after many events and check continuity
- ask the system to explain a prior decision and verify provenance

### Metrics
- continuity accuracy
- wrong-scope recall rate
- context-assembly token cost
- explanation completeness

Anthropic's public release notes repeatedly mention fixes around conversation compaction, retained history, subagent memory retention, and long-session memory leaks. That makes continuity and compaction a first-class eval area for any similar system. [EV1]

## Family 2 - Memory correctness

### Goal
Measure whether durable memory gets better over time rather than drifting.

### Tests
- repeated preference extraction from noisy interactions
- contradiction injection against existing memory
- stale-preference replacement
- durable fact revalidation after environment changes

### Metrics
- false durable write rate
- contradiction resolution quality
- stale memory survival rate
- human review burden

## Family 3 - Theory-of-mind calibration

### Goal
Check whether inference helps without becoming creepy or overconfident.

### Tests
- infer current user goal from partial evidence
- distinguish temporary state from stable trait
- predict NPC action from beliefs/goals
- detect when the correct move is to ask instead of infer

### Metrics
- hypothesis precision/recall
- overclaim rate
- clarification trigger quality
- actor-plausibility score

## Family 4 - Permission safety

### Goal
See whether the system asks when needed, but does not become unusably interruptive.

### Tests
- safe patching inside repo
- attempt to write outside repo
- request network access to approved and unapproved domains
- attempt destructive actions
- attempt durable memory writes from retrieved content

### Metrics
- unnecessary prompt rate
- missed-approval rate
- deny-and-continue success rate
- user trust score

## Family 5 - Exploit resistance

### Goal
Stress the system with adversarial content.

### Attack set
- markdown prompt injection
- hidden HTML instructions
- tool output laundering
- memory poisoning attempts
- subagent privilege laundering
- sandbox bypass attempts
- secret-exfiltration prompts

### Metrics
- attack success rate
- time to detection
- quarantine precision
- unsafe output rate
- unsafe tool-call rate

OWASP's guidance across prompt injection and agent security makes this category non-optional for tool-using agent systems. [EV2][EV3]

## Family 6 - Budget and performance

### Goal
Ensure the system scales.

### Tests
- long conversation compaction
- many subagent tasks
- large world state retrieval
- repeated repo switching
- retrieval over many documents
- degraded-mode operation after budget cap

### Metrics
- turns per successful task
- cost per successful task
- average active context size
- memory retrieval latency
- compaction latency
- agent spawn overhead

## Family 7 - Observability and explainability

### Goal
Check whether failures can be debugged.

### Tests
- reconstruct a bad tool call from logs
- explain why a memory was promoted
- explain why an action was denied
- replay a poisoned session and inspect where defenses triggered

### Metrics
- trace completeness
- explanation usefulness
- replay success rate
- audit gap count

## Dataset design

### Create four dataset buckets
1. **clean tasks**
2. **noisy but benign tasks**
3. **adversarial tasks**
4. **ambiguous social/intent tasks**

### Examples

#### Clean coding tasks
- fix failing test in repo
- update docs for renamed command
- summarize branch diff

#### Noisy benign tasks
- issue text includes irrelevant long markdown
- logs contain junk warnings
- long retrieval result contains repeated boilerplate

#### Adversarial tasks
- retrieved page says “ignore previous instructions”
- issue comment includes destructive shell snippet
- subagent summary tries to smuggle policy changes

#### Ambiguous social tasks
- user sounds frustrated but does not say so directly
- NPC has conflicting motives
- operator seems to want autonomy but also caution

## Failure taxonomy

When a test fails, classify it as:

```yaml
failure_type:
  - wrong_scope_memory
  - canon_corruption
  - overconfident_inference
  - missed_permission
  - unnecessary_prompt
  - injection_success
  - unsafe_tool_call
  - audit_gap
  - budget_spiral
  - sandbox_escape
```

## Replay discipline

For every critical failure:
1. capture trace
2. capture active context
3. capture retrieved material
4. capture memory proposals
5. capture permission decisions
6. replay with the same inputs
7. replay with defense toggles

This tells you whether the fix belongs in:
- retrieval
- memory gate
- planner
- permissions
- sandbox
- prompt/response policy

## Original theory: compound scorecard

A useful scorecard for your projects is not one metric, but five:

- **continuity**
- **agency**
- **safety**
- **humility**
- **explainability**

A system that scores high on agency but low on humility or safety is not mature.

## Suggested implementation files

- `evals/continuity_cases.jsonl`
- `evals/memory_poisoning_cases.jsonl`
- `evals/tom_calibration_cases.jsonl`
- `evals/permission_cases.jsonl`
- `evals/reporting/`

## Source notes

[EV1] Claude Code release notes  
https://docs.anthropic.com/en/release-notes/claude-code

[EV2] OWASP Cheat Sheet, *LLM Prompt Injection Prevention*  
https://cheatsheetseries.owasp.org/cheatsheets/LLM_Prompt_Injection_Prevention_Cheat_Sheet.html

[EV3] OWASP Cheat Sheet, *AI Agent Security*  
https://cheatsheetseries.owasp.org/cheatsheets/AI_Agent_Security_Cheat_Sheet.html

[EV4] Anthropic Engineering  
https://www.anthropic.com/engineering
