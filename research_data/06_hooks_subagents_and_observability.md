# 06 - Hooks, Subagents, and Observability

## Thesis

If you want a system to feel truly agentic, you need more than a prompt and a tool list. You need a **runtime**:

- lifecycle events
- scoped helper agents
- policy interception points
- compaction events
- telemetry and review logs

Claude Code’s public docs describe hooks firing at lifecycle points like session start, pre-tool use, permission request, post-tool use, task creation/completion, compaction, and session end. The same docs describe customizable subagents with tool restrictions, permission modes, hooks, and skills. [H1][H2]

The general lesson is extremely useful:

> Treat the agent as an event-driven operating loop, not just a text generator.

## Runtime architecture sketch

```text
user request
  -> planner
  -> task graph
  -> policy engine
  -> delegated subagents
  -> tool execution
  -> output validator
  -> memory proposal gate
  -> observability log
  -> response
```

## Recommended hooks

### SessionStart

Use for:
- load project memory
- load policy overlays
- initialize budget counters
- attach repo/world identity

### PreToolUse

Use for:
- command/path validation
- risk scoring
- secret exposure checks
- deny or downgrade unsafe actions

### PermissionRequest

Use for:
- semantic explanation of risk
- bundling related actions
- human approval or refusal path

### PostToolUse

Use for:
- result validation
- redact secrets from logs
- extract candidate learnings
- flag suspicious outputs

### PreCompact / PostCompact

Use for:
- summarize session
- decide what becomes episodic memory
- propose stable memory candidates
- inspect for poisoning markers

### SessionEnd

Use for:
- flush metrics
- store audit trail
- queue review tasks

## Subagent pattern

Public Anthropic docs note that subagents can have custom prompts, tool restrictions, permission modes, hooks, and skills, and also describe built-in helper agents used for planning and bash execution. [H2]

That suggests a very strong architecture for original systems:

### research subagent
- read-only
- can search code/docs/world state
- cannot write memory or files

### action subagent
- limited project writes
- limited safe commands
- no direct durable memory writes

### memory curator subagent
- reads logs and proposals
- writes only to memory candidate queue
- never to canonical memory directly

### red-team subagent
- attempts adversarial prompt and tool misuse tests
- no write powers beyond test artifacts

## Observability ledger

Track at least:

```yaml
trace_id: string
session_id: string
agent_id: string
event_type: string
input_hash: string
risk_score: float
action_summary: string
tool_name: string|null
affected_paths: []
network_touched: bool
approval_status: approved|denied|not_needed
budget_used:
  steps: int
  tokens: int
  tool_calls: int
memory_proposals: []
anomaly_flags: []
```

## Why observability matters

Without good traces, you cannot answer:

- why the agent did something
- where a poisoned memory came from
- which prompt triggered a bad tool call
- why a budget spiral happened
- whether a subagent exceeded its intended role

## Defensive hook ideas

- block writes when the proposed target contains secrets or credentials
- block memory proposals containing imperative instructions
- block shell commands that fetch remote content unless a trusted mode is active
- inspect retrieved Markdown/HTML for injection signatures
- require review before promoting long-term memory

## Good default rule

Every hook should either:

- validate
- log
- constrain
- summarize
- or escalate

Avoid hooks that silently mutate important state without traceability.

## Source notes

[H1] Claude Code Docs, *Hooks reference*  
https://code.claude.com/docs/en/hooks

[H2] Claude Code Docs, *Create custom subagents*  
https://code.claude.com/docs/en/sub-agents
