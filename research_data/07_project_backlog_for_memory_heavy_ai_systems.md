# 07 - Project Backlog for Memory-Heavy AI Systems

## Purpose

This is a practical backlog shaped for the kinds of systems you gravitate toward:

- mythic or world-rich RPG engines
- AI companion / persona systems
- long-running coding agents
- persistent simulation architectures
- memory-rich multi-agent worlds

## Priority 1 - Foundations

### A. Memory schema v1

Build tables or collections for:

- canonical facts
- episodic summaries
- hypotheses
- relationships
- memory reviews
- quarantine
- source provenance

**Exit condition:** every memory item has scope, confidence, provenance, and review state.

### B. World / mind separation

Implement separate stores for:

- world truth
- actor beliefs
- actor goals
- relationship edges

**Exit condition:** characters can be wrong without corrupting canon.

### C. Risk engine

Create a classifier for actions:

- inspect
- local safe write
- execution
- network
- deletion
- external account access

**Exit condition:** the system can explain *why* an action needs approval.

## Priority 2 - Safe autonomy

### D. Capability-scoped subagents

Implement at least three:

1. `researcher`
2. `patcher`
3. `memory_curator`

**Exit condition:** each role has a different tool and memory policy.

### E. Hook bus

Add lifecycle events:

- session_start
- pre_tool
- permission_request
- post_tool
- pre_compact
- session_end

**Exit condition:** every significant action is interceptable and logged.

### F. Budget governor

Track:

- steps
- tokens
- tool calls
- retries
- elapsed time

Abort or ask for approval when thresholds are hit.

**Exit condition:** the system cannot silently spiral into a denial-of-wallet loop.

## Priority 3 - Anti-exploit hardening

### G. Memory write gate

Rules:

- reject imperative memory content
- flag external-content-derived writes
- require review for durable memory
- support rollback

### H. Output validator

Inspect outputs for:

- secret leakage
- copied hostile instructions
- suspicious URLs or payload markers
- scope violations

### I. Retrieval sanitizer

Before retrieved text reaches reasoning context:

- strip HTML/script weirdness
- mark source trust level
- isolate potential instructions from content
- block hidden or encoded directives when possible

## Priority 4 - Theory of mind upgrade

### J. Hypothesis promotion engine

- turn repeated evidence into stronger beliefs
- decay stale inferences
- surface contradictions

### K. Emotional / motivational state model

For agents or NPCs:

- current mood
- ongoing drives
- trust and tension levels
- allegiance shifts

### L. Social memory planner

Track who remembers what, and how that changes behavior.

## Priority 5 - Release engineering and ops

### M. Artifact safety review

The current Claude Code incident is a reminder that release packaging mistakes can become strategic failures. Public reporting says the exposure was caused by a source map file in a public npm package. [B1][B2]

Add checks for:

- source maps
- debug bundles
- embedded secrets
- unexpected artifact size spikes
- disallowed files in release tarballs

### N. Dependency integrity workflow

- pin versions
- review lockfile diffs
- separate dev-only dependencies
- scan for malicious postinstall scripts
- verify package provenance where possible

## High-value experiments

1. Can a compact triple-ledger memory outperform giant text summaries?
2. How much better does NPC continuity get when beliefs are separated from truth?
3. Does a dedicated memory curator reduce poisoning compared with direct model writes?
4. Which risk prompts reduce approval fatigue without making users careless?
5. How much budget is saved by subagent role separation?

## Suggested immediate next move

If you want maximum impact fast, do these in order:

1. memory schema v1
2. memory write gate
3. world truth vs belief separation
4. hook bus
5. capability-scoped subagents
6. output validator
7. budget governor

That sequence gives you continuity, safer autonomy, and a real defensive spine early.

## Source notes

[B1] The Verge, *Claude Code leak exposes a Tamagotchi-style 'pet' and an always-on agent* (Mar 31, 2026)  
https://www.theverge.com/ai-artificial-intelligence/904776/anthropic-claude-source-code-leak

[B2] Axios, *Anthropic leaked 500,000 lines of its own source code* (Mar 31, 2026)  
https://www.axios.com/2026/03/31/anthropic-leaked-source-code-ai
