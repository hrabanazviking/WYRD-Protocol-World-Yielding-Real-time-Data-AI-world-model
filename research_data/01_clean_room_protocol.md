# 01 - Clean-Room Protocol

## Goal

Create a workflow that lets a team learn from public discussion around advanced agent systems without crossing into code appropriation or derivative reconstruction.

## Scope boundary

This protocol permits:

- extracting **general problem statements**
- extracting **design patterns**
- extracting **tradeoff classes**
- generating **fresh specs**, schemas, test plans, and evaluation ideas
- writing **new implementations** from those specs

This protocol forbids:

- copying code
- copying comments
- copying strings or memorable identifiers from proprietary internals
- paraphrasing implementation line by line
- recreating a distinctive architecture solely because a proprietary system used it

## Research workflow

### Phase 1 - Artifact intake

Input only:

- official vendor docs
- public reporting
- public talks/blog posts
- independent defensive security guidance

Output:

- a plain-language note of what problem space seems important
- a list of recurring design themes
- a list of unresolved questions

### Phase 2 - Sanitized abstraction

For every useful idea, convert notes into this template:

```md
## Pattern Name
- Problem:
- Abstract idea:
- Why it helps:
- Tradeoffs:
- Failure modes:
- Original reimplementation direction:
- Tests needed:
```

Rules:

- no vendor-specific identifiers
- no file names from proprietary systems
- no copied phrases longer than a trivial title

### Phase 3 - Spec generation

Write your own design docs:

- data model
- memory schema
- permission model
- threat model
- evaluation harness
- rollout plan

Every spec should include a section called **“Why this is our own design.”**

### Phase 4 - Separate build pass

Preferably use a different person, or at least a different pass, to generate code from the spec. The builder should work from the sanitized docs rather than from the raw research material.

## Documentation standard

Each design file should include this metadata block:

```md
Source basis: public docs + public reporting + independent synthesis
Contains proprietary code: no
Contains copied identifiers: no
Confidence: medium/high/experimental
Implementation status: concept/spec/prototype
```

## Review checklist

Before a file is approved, verify:

- Does it state a problem in generic terms?
- Does it avoid proprietary naming?
- Does it describe tradeoffs rather than mimic structure?
- Would a reader be able to build a different implementation from it?
- Does it include defensive concerns, not just “cool features”?

## What to prioritize for your style of projects

For memory-heavy RPG / world-model / AI-companion systems, the most reusable abstractions are:

1. memory tiering
2. scope-aware persistence
3. conflict resolution between instruction and observation
4. theory-of-mind state separation
5. guardrails around self-updating memory
6. permission-scoped tools
7. adversarial input handling
8. budget control for long autonomous loops

## Why this protocol is justified

Anthropic’s current public docs describe Claude Code as having two complementary memory systems, hooks at multiple lifecycle points, configurable permissions, sandboxing, and customizable subagents. Those ideas are broad enough to inspire many original systems, but they also make clear that powerful agent runtimes have broad attack surface and need disciplined scoping. [P1][P2][P3][P4]

## Source notes

[P1] Claude Code Docs, *How Claude remembers your project*  
https://code.claude.com/docs/en/memory

[P2] Claude Code Docs, *Hooks reference*  
https://code.claude.com/docs/en/hooks

[P3] Claude Code Docs, *Security*  
https://code.claude.com/docs/en/security

[P4] Claude Code Docs, *Create custom subagents*  
https://code.claude.com/docs/en/sub-agents
