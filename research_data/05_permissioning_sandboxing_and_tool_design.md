# 05 - Permissioning, Sandboxing, and Tool Design

## Thesis

Powerful agents fail in two opposite ways:

- too many prompts → users approve everything blindly
- too few prompts → the agent becomes effectively unsupervised

Anthropic’s March 25, 2026 engineering post says Claude Code users approve **93%** of permission prompts, and presents auto mode as an attempt to reduce approval fatigue without abandoning safety. It contrasts manual approval, sandboxing, and a full “dangerously skip permissions” mode. [T1]

Claude Code’s public security docs also say the system is read-only by default, can restrict writes to the working directory subtree, and uses sandboxed bash plus allowlisting to reduce risk. [T2]

## Design principle

The right question is not “Should the agent have permissions?”

It is:

> “Which capabilities should be granted, under what scope, for how long, and with what review path?”

## Recommended permission modes

### 1. Inspect mode

- read files in allowed scope
- no writes
- no shell
- no network

Use for research, planning, retrieval, audits.

### 2. Draft mode

- write only in staging/scratch area
- no direct commit
- shell only for safe local analysis
- no network

Use for patch proposals and speculative edits.

### 3. Controlled execution mode

- limited shell allowlist
- write only in project subtree
- network off unless explicitly enabled
- destructive actions blocked

Use for tests, formatting, code generation.

### 4. Maintainer mode

- broader writes
- selected install/update commands
- explicit confirmation for risky actions
- all actions logged

Use for trusted operator workflows.

### 5. Break-glass mode

- time-limited elevated permissions
- explicit operator awareness
- visible banner/warning
- mandatory audit log

Use only when a human understands the risk.

## Capability token pattern

Instead of global permissions, issue short-lived capability grants:

```yaml
capability_token:
  subject: subagent_test_runner
  scope:
    paths: ["/repo/tests/*", "/repo/src/*"]
    commands: ["pytest", "python -m pytest", "ruff check"]
    network: false
    delete: false
  expires_at: 2026-04-01T03:00:00Z
```

This reduces damage radius and makes reasoning about tool power much cleaner.

## Tool scoping rules

For each tool, define:

- allowed operations
- allowed paths
- blocked patterns
- allowed command forms
- side-effect class
- approval policy

OWASP’s agent security guidance explicitly recommends minimum tools, per-tool permission scoping, separate tool sets by trust level, and explicit authorization for sensitive actions. [T3]

## Sandboxing strategy

A good sandbox controls:

- filesystem visibility
- write scope
- process spawn rights
- network egress
- environment variables
- secret mounts
- clipboard/system integration

Anthropic’s docs publicly describe sandboxed bash with filesystem and network isolation as a way to reduce permission prompts while keeping boundaries. [T2]

## Action classification matrix

### Low risk
- read file
- grep/search
- parse log
- compute diff

### Medium risk
- write to project file
- run tests
- format code
- create branch/worktree

### High risk
- delete files
- install packages
- open network connection
- execute arbitrary shell
- deploy or publish
- export data

### Critical risk
- read secrets
- modify auth or payment code
- access external accounts
- alter CI/CD or release settings

Require human confirmation for high/critical by default.

## UX rule

Prompt less often, but make the prompts **matter more**.

This means:

- bundle related safe actions
- keep prompts semantic, not low-level
- explain why the action is needed
- show exact scope and risk
- let users allow repeated safe actions narrowly

## Best practice for memory-heavy world engines

Use different agent roles with different permissions:

- `lore_researcher` → inspect only
- `state_compactor` → read + write memory DB only
- `code_patcher` → project writes, no network
- `deployment_agent` → unavailable except in break-glass mode

Public Anthropic docs on subagents emphasize tool restrictions and separate contexts, which is a strong public signal that role-based compartmentalization is valuable. [T4]

## Source notes

[T1] Anthropic Engineering, *Claude Code auto mode: a safer way to skip permissions*  
https://www.anthropic.com/engineering/claude-code-auto-mode

[T2] Claude Code Docs, *Security*  
https://code.claude.com/docs/en/security

[T3] OWASP Cheat Sheet, *AI Agent Security Cheat Sheet*  
https://cheatsheetseries.owasp.org/cheatsheets/AI_Agent_Security_Cheat_Sheet.html

[T4] Claude Code Docs, *Create custom subagents*  
https://code.claude.com/docs/en/sub-agents
