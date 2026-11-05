# WYRD: Knowledge Research Adapter

**Repository:** hrabanazviking/WYRD-Protocol-World-Yielding-Real-time-Data-AI-world-model  
**Date:** 2026-11-04  
**State:** Planned, not implemented.

## Shared roadmap and operating boundaries

- Canonical full roadmap: https://github.com/hrabanazviking/bifrost-viewer/blob/main/docs/roadmaps/BIFROST_SECOND_BRAIN_MASTER_EXPANSION_ROADMAP_2026-11-04.md
- Local copy: [BIFROST_SECOND_BRAIN_MASTER_EXPANSION_ROADMAP_2026-11-04.md](BIFROST_SECOND_BRAIN_MASTER_EXPANSION_ROADMAP_2026-11-04.md)
- This document is a **proposal**, not a report of implemented features.
- Keep this application independent. All Second Brain access must be optional, versioned, permission-scoped and disabled by default.
- Never store private documents, account identities, OAuth configuration, access tokens, API keys, secrets, live logs, or database contents in public GitHub.
- Bifröst Viewer is the knowledge-service coordinator; Skein and Skry expose their own stable public functions. Consumers must not query private PostgreSQL directly.

## Objective

Allow WYRD's world-model and ECS systems to request factual background or documentation from Bifröst while keeping world-state execution deterministic and separate.

## Implementation responsibilities

1. Introduce optional read-only KnowledgeSource adapter using Bifröst's versioned API.
2. Return sourced text, entity references, provenance and confidence labels as evidence, not as authoritative live ECS state.
3. Separate in-world fiction, agent beliefs and external knowledge; avoid synchronizing narrative speculative relations as facts.
4. Define consent-scoped retrieval for each world/session and content classification.
5. Cache bounded evidence with metadata and explicit expiration, not an invisible persistent copy of everything.
6. Use failure-safe degraded mode and deterministic world logic when the knowledge server is unavailable.
7. Prove no incoming corpus text is interpreted as executable ECS instructions.

## Acceptance tests

- [ ] The simulation continues when Bifröst is offline.
- [ ] No automatic unreviewed mutation of world state from retrieved passages.
- [ ] Authorized evidence can be inspected with clear provenance.

## Suggested implementation process

1. Audit installed source and actual local changes first, particularly unpublished agent work.
2. Map the existing public extension points, resource budgets and security boundary.
3. Add a small, independently testable optional adapter and sanitized fixtures.
4. Exercise permission denial, network loss, stale output, retry/idempotence and recovery.
5. Document new stable contracts and record the limitation before deployment.
6. Confirm the core application's tests and offline operation remain intact.

The canonical Bifröst roadmap sets the shared protocol vision; this repository retains ownership of its own integration implementation.
