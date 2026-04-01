# 16 - Build Sequence v2

Source basis: independent synthesis
Contains proprietary code: no
Contains copied identifiers: no
Confidence: medium/high
Implementation status: actionable plan

## Goal

Turn this research pack into buildable modules in an order that maximizes practical value quickly while keeping risk under control.

## Phase 0 - Skeleton

Create empty modules and interfaces only:

- memory_core/
- provenance/
- permissioning/
- sandbox/
- world_model/
- theory_of_mind/
- observability/
- evals/

### Exit condition
All interfaces exist, nothing clever yet.

## Phase 1 - Safe memory core

Build first:
1. observation log
2. claim extractor
3. memory schema
4. review queue
5. active-context assembler

### Exit condition
You can store and retrieve scoped memory with provenance and confidence.

## Phase 2 - Contradiction and decay

Build:
1. contradiction detector
2. promotion engine
3. decay scheduler
4. archive/tombstone handling

### Exit condition
The system no longer overwrites memory blindly.

## Phase 3 - Permission spine

Build:
1. action classifier
2. path/domain policy checker
3. decision audit log
4. approval formatter

### Exit condition
Every tool request can be classified and explained.

## Phase 4 - Sandbox integration

Build:
1. scoped filesystem policy
2. bounded network policy
3. unsandboxed-execution review path
4. violation logger

### Exit condition
Safe execution can happen with fewer prompts.

## Phase 5 - Graph world model

Build:
1. entity store
2. canon claims
3. belief claims
4. relationship edges
5. event ledger

### Exit condition
You can represent truth, belief, and change separately.

## Phase 6 - Theory-of-mind layer

Build:
1. evidence gatherer
2. hypothesis generator
3. confidence/decay logic
4. usage-mode chooser

### Exit condition
The system can infer carefully without polluting canon memory.

## Phase 7 - Subagent architecture

Build:
1. role definitions
2. tool scopes
3. memory scopes
4. handoff summaries
5. circuit breakers

### Exit condition
You can run specialized helpers without privilege soup.

## Phase 8 - Eval harness

Build:
1. continuity datasets
2. poisoning datasets
3. permission cases
4. ToM calibration cases
5. replay and diff tools

### Exit condition
You can measure progress instead of guessing.

## Recommended first deliverables

### If you want immediate practical value
Build in this order:
1. memory schema
2. provenance ledger
3. memory write gate
4. permission classifier
5. contradiction resolver

### If you want the best foundation for a world engine
Build in this order:
1. event ledger
2. canon store
3. belief store
4. relationship graph
5. temporal query layer

### If you want the best foundation for a companion system
Build in this order:
1. preference store
2. boundary/sensitivity store
3. theory-of-mind hypothesis store
4. relationship weather/climate model
5. compaction pipeline

## Project-management habit

At the end of every milestone, create:
- one architecture note
- one failure note
- one eval report
- one “what we thought vs what happened” note

That keeps the system honest.

## Final rule

Do not rush to “agent magic.”
Get the ledgers, scopes, permissions, and traces right first.
