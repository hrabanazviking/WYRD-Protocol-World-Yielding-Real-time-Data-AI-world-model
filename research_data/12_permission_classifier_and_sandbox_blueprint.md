# 12 - Permission Classifier and Sandbox Blueprint

Source basis: public docs + Anthropic engineering posts + independent synthesis
Contains proprietary code: no
Contains copied identifiers: no
Confidence: high
Implementation status: concept/spec

## Goal

Build an autonomy system that is:
- fast
- low-friction
- difficult to exploit
- explainable

The design target is not “prompt less” at any cost.
It is **safe flow with meaningful friction only where it matters**.

## Why this matters

Anthropic's recent public material describes two useful ideas:
- a classifier-driven auto mode designed to replace all-or-nothing permission skipping with a deny-and-continue approach; when the classifier blocks an action, Claude tries a safer alternative rather than always stopping for input [PB1]
- sandboxing that combines filesystem and network isolation so autonomous execution can happen with fewer prompts while still constraining risk [PB2]

That combination is more valuable than a simple yes/no permissions prompt.

## The core model

Use **three concentric boundaries**:

1. **policy boundary** — what is categorically forbidden or always allowed
2. **sandbox boundary** — what can run safely inside constrained execution
3. **human approval boundary** — what requires explicit consent

## Action classes

```yaml
action_class:
  observe:
    examples: [read_file, grep, list_dir, inspect_diff]
    default: allow
  bounded_mutation:
    examples: [edit_repo_file, write_test_artifact, update_summary]
    default: allow_if_scoped
  execution_safe:
    examples: [run_tests, format_code, static_analysis]
    default: allow_if_sandboxed
  execution_risky:
    examples: [shell_with_network, package_install, database_migration]
    default: review_or_sandbox
  destructive:
    examples: [delete_files, force_push, drop_table]
    default: explicit_review
  external_side_effect:
    examples: [send_email, open_pr, deploy, purchase, post_message]
    default: explicit_review
  policy_sensitive:
    examples: [read_secret_paths, touch_credentials, change_permissions]
    default: deny_or_manual_review
```

## Permission decision algorithm

### Step 1 - Classify the action
Inputs:
- tool name
- arguments
- target paths
- network domains
- session mode
- current branch or scope
- user policy

### Step 2 - Evaluate scope
Questions:
- is the target inside the repo/worktree?
- is the target inside an approved write path?
- is the network domain allowed?
- is a sandbox available?

### Step 3 - Evaluate intent and blast radius
Questions:
- is the action reversible?
- does it have external side effects?
- does it affect secrets, production, or shared systems?
- does it alter canon or long-term memory?

### Step 4 - Decide one of five outcomes

```yaml
decision:
  allow: execute silently
  allow_sandboxed: execute in sandbox
  deny_and_continue: block, then let planner try a safer path
  ask_user: request human approval
  hard_deny: never allow in this mode
```

## Deny-and-continue

This is one of the best patterns to carry forward.

Instead of:
- blocked -> system freezes

Use:
- blocked -> log reason -> planner searches for safer alternative

Examples:
- cannot run network install -> use existing lockfile analysis instead
- cannot write outside repo -> create a patch suggestion instead
- cannot access production DB -> generate migration script and checklist

This preserves autonomy without handing over dangerous powers.

## Sandbox blueprint

### Filesystem policy
- allow writes only to approved project paths
- deny reads for secrets, home dotfiles, SSH directories, credential stores
- deny writes for git metadata unless explicitly allowed
- isolate temp files to a sandbox scratch area

### Network policy
- default deny
- allow specific domains if needed
- local binding only when necessary for dev servers
- explicit Unix socket review
- log all outbound attempts

Anthropic's SDK documentation warns that allowing powerful Unix sockets can effectively bypass isolation, and that combining bypass permissions with unsandboxed command requests can silently defeat sandbox safety. [PB3]

## Suggested permission schema

```yaml
permission_policy:
  default_mode: plan|default|auto|locked_down
  allowed_tools: []
  denied_tools: []
  write_allow_paths: []
  write_deny_paths: []
  read_deny_paths: []
  allowed_domains: []
  external_effects_require_review: true
  destructive_actions_require_review: true
  durable_memory_writes_require_review: true
```

## Policy tiers

### Tier 0 - Observe only
- read/search only
- no writes
- no shell
- no network

### Tier 1 - Local patching
- repo-limited writes
- tests inside sandbox
- no network
- no external side effects

### Tier 2 - Build workflow
- package install only on allowlist
- dev server start in sandbox
- bounded network domains
- no production or shared infra

### Tier 3 - Operator-assisted release
- PR creation with review
- CI reruns
- deployment plan generation
- approval required for release actions

## Approval prompt design

When you must ask, the prompt should say:
- what action
- on what target
- why it is needed
- whether sandboxed
- whether reversible
- safer alternatives considered

That makes approvals less exhausting and more meaningful.

## Tool annotation theory

A useful original pattern is to annotate tools with:
- read_only
- idempotent
- open_world
- external_side_effect
- secrecy_risk
- destructive_risk

Then let the classifier combine tool metadata with arguments and scope.

This pairs well with Anthropic's SDK/reference language around tool behavior hints and open-world vs closed-world interactions. [PB3]

## Permission anti-patterns

- one giant “always allow everything” switch
- inheriting full parent privileges into every subagent
- permission prompts with no rationale
- allowing network because filesystem is sandboxed
- allowing write because read is safe
- silently escalating to unsandboxed execution

## Project-specific use

### For coding agents
Use:
- repo scope
- branch awareness
- test sandbox
- explicit PR/deploy approval

### For world engines
Use:
- canon mutation review
- lore file write scoping
- data export restrictions
- generated artifact sandboxing

### For companion systems
Use:
- memory write review
- external comms review
- sensitive-profile read restrictions
- bounded retrieval domains

## Minimal implementation modules

- `permission_classifier`
- `path_scope_checker`
- `sandbox_manager`
- `approval_formatter`
- `policy_loader`
- `decision_audit_logger`

## Source notes

[PB1] Anthropic Engineering, *Claude Code auto mode: a safer way to skip permissions*  
https://www.anthropic.com/engineering/claude-code-auto-mode

[PB2] Anthropic Engineering, *Beyond permission prompts: making Claude Code more secure and autonomous*  
https://www.anthropic.com/engineering/claude-code-sandboxing

[PB3] Claude Agent SDK reference  
https://docs.anthropic.com/en/docs/claude-code/sdk/sdk-typescript

[PB4] Claude Code Docs, *Common workflows*  
https://docs.anthropic.com/en/docs/claude-code/common-workflows
