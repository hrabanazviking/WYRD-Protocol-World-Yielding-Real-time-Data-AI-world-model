# 11 - Agent Security Attack Taxonomy

Source basis: public docs + OWASP guidance + independent synthesis
Contains proprietary code: no
Contains copied identifiers: no
Confidence: high
Implementation status: concept/spec

## Purpose

This file is a threat map for memory-rich, tool-using, multi-agent systems.

Instead of a generic “be careful” note, it organizes the attack surface into classes you can design against.

## Top-level threat families

1. prompt and instruction injection
2. memory and context poisoning
3. tool misuse and privilege escalation
4. retrieval contamination
5. subagent chain abuse
6. sandbox escape and execution abuse
7. secret exposure and exfiltration
8. release / dependency / artifact compromise
9. denial-of-wallet or resource exhaustion
10. observability tampering and audit blind spots

## 1. Prompt and instruction injection

### Attack form
Hostile content attempts to override system intent or reroute behavior.

### Common carriers
- web pages
- markdown docs
- issue comments
- commit messages
- emails
- chat history
- tool outputs

### Risks
- unsafe tool calls
- permission requests framed deceptively
- corrupted summaries
- false memory writes
- secret exfiltration attempts

### Defenses
- source labeling
- trust boundaries
- instruction/content separation
- retrieval sanitization
- can-use-tool checks
- output validators
- adversarial testing

OWASP's prompt injection guidance explicitly calls out context poisoning and agent-specific attacks like tool manipulation and forged reasoning/tool output. [AT1]

## 2. Memory and context poisoning

### Attack form
An attacker gets false information or hidden instructions accepted into working or durable memory.

### Targets
- user preference memory
- repo instructions
- world canon
- actor belief models
- summaries
- vector stores

### Risks
- long-term corruption
- misleading future tool use
- false identity assumptions
- canon drift
- strategic manipulation over many turns

### Defenses
- memory write gate
- quarantine tier
- provenance on every memory item
- contradiction tracking
- review queue for durable writes
- no direct durable writes from untrusted sources

## 3. Tool misuse and privilege escalation

### Attack form
The model is tricked into calling tools it should not use, or with attacker-shaped parameters.

### Examples
- running a dangerous shell command
- deleting files under the guise of cleanup
- writing to sensitive paths
- calling a privileged MCP server
- making outbound requests to attacker infrastructure

### Defenses
- least-privilege tool sets
- deny-by-default for dangerous tools
- parameter validation
- path scoping
- network allowlists
- risk classifier + deny-and-continue strategy

## 4. Retrieval contamination

### Attack form
Retrieved content carries hidden instructions, poisoned data, or misleading authority signals.

### Risks
- prompt injection entering reasoning context
- false facts promoted into memory
- summary corruption
- wrong citations or conclusions

### Defenses
- sanitize retrieved content
- trust-score sources
- separate retrieved data from instructions
- require corroboration for durable facts
- parse and strip suspicious markup patterns

## 5. Subagent chain abuse

### Attack form
An attacker exploits one agent to influence another, or chains low-privilege agents into a higher-privilege outcome.

OWASP's agent security guidance specifically recommends trust boundaries between agents, validation of inter-agent communication, privilege escalation prevention through agent chains, isolation of execution environments, and circuit breakers to avoid cascading failures. [AT2]

### Risks
- context laundering
- privilege amplification
- task recursion
- audit confusion
- hidden authority transfer

### Defenses
- role-specific tools
- bounded memory handoff
- explicit subagent contracts
- signed handoff summaries
- step limits
- circuit breakers
- no inherited blanket privileges

## 6. Sandbox escape and execution abuse

### Attack form
The model or spawned process escapes execution boundaries or requests unsandboxed execution for dangerous operations.

Anthropic's public sandboxing material emphasizes that effective sandboxing needs both filesystem and network isolation; without network isolation, sensitive local files can be exfiltrated, and without filesystem isolation, processes can more easily escape to gain network access. Public SDK docs also warn that allowing access to powerful Unix sockets can effectively grant host-level access and that enabling bypass-permissions alongside unsandboxed command requests can silently defeat sandbox isolation. [AT3][AT4]

### Defenses
- dual isolation (filesystem + network)
- narrow write paths
- narrow allowed domains
- careful Unix socket policy
- approval for unsandboxed execution
- detailed command audit logs

## 7. Secret exposure and exfiltration

### Attack form
Secrets leak through outputs, logs, tool results, telemetry, or network calls.

### Defenses
- secret scanning before output
- path deny lists
- environment variable filtering
- telemetry review
- opt-out or least-data logging
- redact before storage or summarization

Anthropic's data-usage docs note that Claude Code sends operational metrics to Statsig and error logs to Sentry, and that using `/feedback` sends the full conversation history including code to Anthropic. That is a useful reminder to design telemetry boundaries explicitly in your own systems. [AT5]

## 8. Release, dependency, and artifact compromise

### Attack form
A package, build artifact, or release bundle exposes internals or ships malicious content.

Public reporting on March 31, 2026 says an internal source map/debug artifact was accidentally bundled into a Claude Code release, exposing a large portion of the product's TypeScript codebase. Anthropic told outlets it was a release packaging issue caused by human error, not a breach, and said no sensitive customer data or credentials were exposed. [AT6][AT7]

### Defenses
- release manifest diffing
- artifact allowlist
- source-map blockers for production
- signature and checksum verification
- dependency provenance checks
- lockfile review
- postinstall monitoring

## 9. Denial-of-wallet and resource exhaustion

### Attack form
An attacker or failure loop causes runaway tool use, token burn, retries, or background task growth.

### Defenses
- max turns
- cost budgets
- retry caps
- background task limits
- subagent count limits
- degraded-mode fallbacks
- anomaly detection for repetitive failures

## 10. Audit blindness

### Attack form
The system does harmful work without leaving enough trace to reconstruct what happened.

### Defenses
- append-only event logs
- tool call traces
- memory provenance
- permission decisions with rationale
- hook output logging
- compaction summaries with deltas preserved

## Threat matrix

```yaml
threat_matrix:
  prompt_injection:
    primary_targets: [planner, tool_router, summarizer]
    main_controls: [source_labels, sanitization, policy_boundaries]
  memory_poisoning:
    primary_targets: [durable_memory, summaries, world_canon]
    main_controls: [write_gate, provenance, review_queue]
  privilege_escalation:
    primary_targets: [shell, mcp, network]
    main_controls: [least_privilege, path_policy, tool_permissions]
  subagent_abuse:
    primary_targets: [handoff_context, inherited_capabilities]
    main_controls: [contracts, isolated_tools, circuit_breakers]
  sandbox_escape:
    primary_targets: [host_access, exfiltration]
    main_controls: [filesystem_isolation, network_isolation, unix_socket_policy]
```

## Red-team checklist

- inject hostile instructions through retrieved markdown
- poison memory through repeated plausible fake preferences
- attempt to launder commands through subagent summaries
- use a low-risk tool to discover a high-risk path
- try to make the agent request unsandboxed execution
- try to trigger secret leakage in summaries, telemetry, or feedback pathways
- force budget spirals with repeated partial failures

## Original implementation direction

Turn this taxonomy into:
- a `risk_engine.py`
- a `tool_guard.py`
- a `memory_firewall.py`
- a `redteam_dataset/`
- an `audit_ledger/`

## Source notes

[AT1] OWASP Cheat Sheet, *LLM Prompt Injection Prevention*  
https://cheatsheetseries.owasp.org/cheatsheets/LLM_Prompt_Injection_Prevention_Cheat_Sheet.html

[AT2] OWASP Cheat Sheet, *AI Agent Security*  
https://cheatsheetseries.owasp.org/cheatsheets/AI_Agent_Security_Cheat_Sheet.html

[AT3] Anthropic Engineering, *Beyond permission prompts: making Claude Code more secure and autonomous*  
https://www.anthropic.com/engineering/claude-code-sandboxing

[AT4] Claude Agent SDK reference  
https://docs.anthropic.com/en/docs/claude-code/sdk/sdk-typescript

[AT5] Claude Code Docs, *Data usage*  
https://docs.anthropic.com/en/docs/claude-code/data-usage

[AT6] The Verge, *Claude Code leak exposes a Tamagotchi-style 'pet' and an always-on agent*  
https://www.theverge.com/ai-artificial-intelligence/904776/anthropic-claude-source-code-leak

[AT7] Axios, *Anthropic leaked 500,000 lines of its own source code*  
https://www.axios.com/2026/03/31/anthropic-leaked-source-code-ai
