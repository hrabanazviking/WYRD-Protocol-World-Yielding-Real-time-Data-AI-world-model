# Bifröst / Skein / Skry: Master Expansion Roadmap
## The Living Library of Mímir — a local-first, modular, observable, resumable AI Second Brain

**Status:** Architecture and implementation roadmap; proposed work, not a claim of implementation  
**Version:** 1.0 planning baseline  
**Date:** 2026-11-04  
**Primary home:** `hrabanazviking/bifrost-viewer`  
**Companion projects:** `hrabanazviking/skein-kg` and `hrabanazviking/skry-kg`  
**Optional integration:** `hrabanazviking/kista` (encrypted secrets vault; not a knowledge store)  
**Primary deployment target:** Linux / Kubuntu, NVIDIA RTX 2060 with **6 GiB VRAM**; preserve existing local machine and PostgreSQL data  
**License and attribution:** Preserve each repository's existing license and attribution; review each third-party reference before reuse  
**Security classification:** **PUBLIC DESIGN ONLY.** This file must contain no actual credentials, private documents, secret values, personal account identifiers, local private-state contents, or database dumps.

> **North star:** Keep the existing Second Brain and its original research intact. Transform it into a modular and dependable knowledge ecosystem that can choose between local, cloud, and hybrid processing; pause for sonic quiet; resume after shutdown; grow its graph incrementally; store verified backups on a dedicated document-backup drive; provide a wonderful technical observatory; edit and synchronize documents; manage projects inside Bifröst; and expose carefully authorized knowledge services to other applications.

---

# 0. Executive charter

This is **one integrated roadmap**, not another standalone application. Bifröst is the human-facing home and coordinator. Skein owns graph computation; Skry owns read-only query-time relationships; Ingest owns source-document writes; Bifröst security owns authentication and admission; Kista may serve as an optional secrets provider. Public interfaces connect these boundaries.

## Non-negotiable promises

1. **No loss of source knowledge.** Existing `documents` and `chunks` remain authoritative. Never use a rebuild, migration, backup, or document editor to silently overwrite or delete them.
2. **One simple default.** An owner should be able to choose “Update My Brain” without understanding DAGs, tokens, HNSW, or lock semantics.
3. **Advanced capabilities are progressively disclosed.** Standard, Advanced, Expert, and Laboratory views reveal more control without cluttering everyday use.
4. **Quiet is a first-class requirement.** A real Pause for Quiet checkpoints running work and relinquishes model/GPU load; it must not simply send SIGSTOP to a process holding VRAM.
5. **Jobs must survive process crashes and poweroffs.** Durable checkpoints, retry records, and ownership locks are independent of frontend sessions.
6. **No surprise bills.** Cloud requests require explicit opt-in, model/provider visibility, projected cost, and a hard spend cap. Local-only remains fully functional.
7. **No global rebuild solely because one document changed.** Incremental work is the normal target; full reconciliation is a deliberate option.
8. **A failed new graph never destroys the prior good one.** Stage, verify, snapshot, then atomically publish; retain prior generations and independent backups.
9. **Reproducibility and provenance.** Every generated item records input identity, model identity, prompt/schema version, algorithm version, source evidence, timestamps and processing settings.
10. **No public secrets.** Tokens, private file paths, OAuth credentials, database connection passwords, user data, provider balances and private runtime state stay off GitHub, logs and AI prompts.
11. **Owner control of exports, edits, deletes and outside-AI access.** Every write is independently authorized and auditable.
12. **Maintain Linux and modest-hardware support.** No mandatory Docker, large model, cloud account, powerful GPU or permanently spinning mechanical disk.
13. **Preserve published library contracts.** New functionality appears through versioned APIs, not Bifröst reaching into private Skein/Skry implementation details.
14. **Clean-room feature development.** Research public capabilities of competing systems; independently implement behavior and user experience; do not copy proprietary code, assets, schemas, designs or copyrighted text.

## Confirmed current architecture from public repositories

- **Bifröst:** FastAPI viewer, local browser workspace, 3D chunk/document/entity displays, UMAP/HDBSCAN, hybrid RRF search, HyDE, graph caches, subprocess builds, owner/API security, scoped AI credentials, audit/recovery mechanics.
- **Skein:** local knowledge-graph build; one model vocabulary-extraction call per source document, mention matching, aggregation of existing chunk embeddings, bounded top-K similarity, predicate-span embedding and typed relation selection. The current build replaces derived rows transactionally after success. It is **not a resumable incremental graph builder**.
- **Skry:** read-only query-time entity neighborhood from chunk embeddings, with optional Skein vocabulary; can retrieve new chunks without a full Skein build, though vocabulary mode may remain stale.
- **Ingest:** parse, normalize, chunk, embed and commit source documents; content-hash deduplication; watcher, durable queue/retries; PostgreSQL + pgvector.
- **Kista:** optional stand-alone encrypted vault for credentials, API keys and sensitive entries. **Never use Kista as a substitute for the document corpus.**
- **A.E.S.I.R.:** optional native inference research/integration, not a requirement for this roadmap.
- **Backup:** manual database/state backup and restore instructions exist; integrated scheduling, drive handling, snapshot browser and automated recovery verification remain proposed.

## Owner-reported operational baseline (verify with read-only measurements)

| Measurement | Baseline |
|---|---:|
| Indexed documents | 2,757 |
| Indexed chunks | 67,761 |
| Document-view graph edges | 8,545 |
| Clusters shown in DOCS view | 0 by design |
| GPU | RTX 2060, 6 GiB VRAM |
| Expected operational concern | full Skein build can take a long period and produce unwanted fan noise |
| Destination for document backups | owner-provided large mechanical storage drive, not yet configured |

**Important:** 8,545 document edges do not equal Skein's entity relations. Zero DOCS clusters is not a graph failure. Installed local code and actual database may differ from public repository state. Before changing anything, produce a read-only inventory of the real installation.

---

# 1. Component ownership and system boundaries

## 1.1 Logical architecture

    Human browser / desktop launcher / mobile browser / authorized AI clients
                               |
                  Bifröst workspace + API gateway
                     |         |          |
                Observability  Scheduler   Authorization
                     |         |          |
                     +----- durable job orchestrator --------+
                     |         |             |              |
                Ingest adapter Skein SDK   Skry SDK     Connector adapters
                     |         |             |              |
                 documents   staged KG     read-only     Google / GitHub /
                   chunks    generation    retrieval    blogs / LibreOffice
                     \         |           /
                          PostgreSQL
                      source + derived tables
                               |
                  verified backup / snapshots
                               |
                    dedicated backup drive

                  Optional: Kista secret-source adapter
                   (secret capability only, no corpus)

**Source-writer boundary:** Only Ingest can modify canonical source records. Editors produce draft or versioned-source change requests; Ingest performs the authorized commit. Skein writes derived graph generations, not primary document rows. Skry remains read-only. External connectors do not bypass ingestion. Bifröst routes only via public package APIs and a separate job service, not direct private methods.

## 1.2 Ownership matrix

| Subsystem | Owns | Must never do |
|---|---|---|
| Bifröst viewer and API | UI, project center, status, auth, read/export requests | Directly alter source documents or expose secrets |
| Scheduler/orchestrator under Bifröst | Jobs, checkpoints, dependency graph, budgets, retries | Treat a queued job as complete |
| Ingest | Source versioning, parsing, chunk rows, source history | Publish unverified graph generations |
| Skein | Entity discovery, evidence, relationship computation, graph snapshots | Discard old graph on failure |
| Skry | Query-time neighborhood lookup | Change canonical source or graph |
| Connector layer | Authorized import/export, source IDs, sync cursors | Issue broad unapproved writes |
| Document workspace | Drafts, revisions, diff, editing sessions | Silently replace canonical records |
| Project registry | Workstreams, milestones, agent assignments, references | Require a separate project-management service |
| Kista adapter | Obtain specific secrets on behalf of privileged provider workers | Offer vault-wide raw search through RAG or chat |
| Backup manager | Versioned backup/restore workflows and verification | Restore automatically into the active live DB |

## 1.3 Deployment profiles

- **Solo minimal:** PostgreSQL + existing local models + browser; no cloud or Google; basic document search and graph.
- **Solo advanced:** full orchestration, local embeddings, optional OpenRouter, local LibreOffice integration, project center, backup drive.
- **Headless knowledge server:** same core with no desktop editor or GPU widget; remote browser and authorized API.
- **Multi-user later:** optional isolated tenants and explicit per-corpus ACLs, quotas and identities. Avoid implicit shared-user assumptions.
- **Air-gapped:** no outbound connectors; user-supplied documents only; offline editing and backup fully work.

---

# 2. First mandatory deliverable: reality audit, preservation and benchmark

Before any mutation, run a **read-only discovery and health audit**. Do not install a migration, change embeddings, reset caches, or rerun Skein as a “diagnostic”.

## 2.1 Inventory

- Exact repo checkout refs, uncommitted files, dependency lockfiles, service units, Python versions and environment locations without printing private contents.
- Document/chunk count, content-hash coverage, embeddings present/missing, vector dimensions and indexed model identity.
- Current Skein build ID, entity count, relation count, fingerprint, evidence counts, discovery failure rate, model versions and last completed time.
- Bifröst cache identities, graph build progress, cluster mode, index types, disk footprint and CPU/RAM/GPU/VRAM usage.
- Watcher and external source collectors: implementation existence, config presence (not values), last success/failure, duplicate handling.
- Backup availability, actual mount and filesystem, free space, write/verify capability; **do not assume the backup drive's path or UUID**.
- Google sync and OAuth: detect installed integration without displaying a token or inferring permissions from file names.
- Kista installed/healthy/locked status only, never secret values.

## 2.2 Benchmark matrix

Use an opt-in representative slice and the actual full corpus **without creating more source rows**.

| Benchmark | Primary metrics |
|---|---|
| Local extraction | tokens/document, extraction success, sec/document, peak GPU VRAM |
| Whole graph | time/stage, CPU/RAM peak, I/O, graph size, invalid output count |
| Search | latency p50/p95/p99, recall@k, precision@k, reranker contribution |
| Skry | query latency, vocabulary mode, evidence correctness |
| Cloud extraction sample | token bill, rate, 429 frequency, structured-JSON validity |
| Offline/power-loss recovery | checkpoints recovered, no loss, no duplication |
| Quiet mode | time to model unload/VRAM release, fan noise observations |
| Backups | duration, output bytes, checksum, test restore pass/fail |
| Google/LibreOffice | fidelity, conflict rates, duplicate prevention, scoped permissions |

Store benchmark results under local private state; publish sanitized aggregate fixtures and methods only. Add regression gates against the baseline and avoid speed claims without measurements.

**Acceptance:** Audit completes read-only, gives accurate counts with no secrets, and produces enough evidence to distinguish GPU inference, CPU graph algorithms, DB I/O and external network overhead.

---

# 3. The modular processing engine: one job or many stages

## 3.1 Three layers of user control

**Standard (default):** “Update My Brain”, “Pause for Quiet”, “Back Up Now”, “Restore from Backup” (safe wizard), “See Progress”. Auto-select a tested local profile; clear, honest explanations.

**Advanced:** choose Local / Hybrid / OpenRouter, extraction mode, priority, active hours, workers, retries, graph mode, batch size, backup destination and per-job cloud cost cap.

**Expert:** editable stage DAG, conditional routing, custom validated provider/model profiles, per-stage parallelism, checkpoint cadence, retry class policies, cost/quality targets, failover matrix, profiling, memory budgets, storage layout, dry run.

**Laboratory:** versioned experimental plugins and comparisons, custom research runs, graph diffusion and multi-hop queries, profiling traces, synthetic stress tests and A/B comparison. Experimental settings must not silently become defaults.

## 3.2 Process granularity

Offer all of the following:

1. **One-click full workflow:** system transparently manages separate durable stages.
2. **Named presets:** Quick Incremental, Safe Full Rebuild, Quality Deep Pass, Cloud-Assisted Fast, Quiet Night, Backup and Verify, Reconcile Relationships.
3. **Step-by-step guided workflow:** user approves each stage, can inspect generated records, then continues.
4. **Manual stage execution:** selected document IDs or source collections, selected graph generation, one processing stage at a time.
5. **Custom pipeline/DAG:** expert creates validated directed acyclic graph with typed inputs, outputs, dependencies, conditional branches and approval gates.
6. **Dry run:** produce impact plan, token estimate, DB changes, model downloads, disk needs and rollback route without performing those actions.

Stages should be individually addressable and reschedulable:

    discover changes -> import -> parse -> normalize -> deduplicate
        -> chunk -> embed -> extract vocabulary
        -> reconcile entities -> match mentions -> aggregate vectors
        -> propose edges -> predicate snap -> validate evidence
        -> stage graph -> review -> snapshot -> publish -> visualize
        -> optional backup -> report

A stage may be skipped only when its contract allows it and compatible prior outputs already exist.

## 3.3 Versioned stage contract

Each stage declares:

- `stage_id`, `stage_version`, `job_id`, `attempt_id`, immutable input manifest and content IDs.
- Expected output schema, schema version, model and embedding-space identifiers, prompt hash, code SHA, dependency versions.
- Idempotency key, preconditions, checkpoint format and recovery behavior.
- CPU/GPU/RAM/VRAM estimates, concurrency limits, maximum batch size, quiet-mode eligibility.
- Retry classes, deadline, circuit-breaker policy, maximum attempt/cost budget.
- Progress structure: completed/total **with real denominator**, rate, ETA as uncertain estimate, last heartbeat.
- Privacy classification and cloud-permission requirements.
- Evidence provenance and validation outcomes.
- Rollback/compensation strategy, which may be “discard staged results” rather than destructive inverse writes.

Use a plugin registry for typed stage runners. Refuse unknown versions/unknown option fields rather than ignoring them.

## 3.4 Durable job state machine

    planned -> awaiting_approval -> queued -> running
                               running -> pausing -> paused -> queued
                               running -> retry_wait -> queued
                               running -> blocked -> queued
                               running -> cancel_requested -> canceled
                               running -> validating -> staged -> published
                               running/validating -> failed

Distinguish `paused` from `blocked`, `degraded`, `canceled`, and `completed but not published`. Workers heartbeat and leases expire; only one publisher per graph generation; resuming checks actual input fingerprints and model/schema compatibility.

Use a PostgreSQL-backed job ledger or a durable local SQLite orchestration DB with WAL and a separate service; choose only after failure-model testing. Never hide essential job state in disposable JSON graph caches.

## 3.5 Resource-aware scheduling

- Central admission controller: **per GPU**, **per CPU**, **per provider**, **per account**, **per source connector**, **per destination**.
- CPU and RAM quotas and local GPU VRAM reservation; target a conservative VRAM safety margin on 6 GiB card.
- Dedicated embedding queue with no accidental simultaneous heavy chat and embedding model loads.
- Max global workers, per-stage workers, batches in flight, token/minute and request/minute, maximum bytes processed per batch.
- Default resource lanes: interactive search > user-approved editing > quiet/light ingest > heavyweight rebuilds.
- Weighted fair queuing so one massive build does not starve quick searches or backup status.
- Dynamic concurrency: additive increase when healthy, multiplicative decrease on throttling/timeout, with explicit upper/lower limits.
- Pause or lower priority at scheduled quiet windows or when user presses Pause.
- Deterministic processing where possible, with seeded clustering and independently versioned model behavior.
- No required all-at-once corpus memory loads; blockwise and streaming operations with bounded buffers.

**Acceptance:** At 6 GiB VRAM, multi-stage workloads cannot silently OOM the server; a heavy job does not make search or admin controls unreachable.

---

# 4. Local / cloud / hybrid inference and high-control processing

## 4.1 Provider abstraction

Implement a provider-neutral `ModelProvider` interface separate from graph logic:

- `list_models`, `capabilities`, `estimate_tokens`, `estimate_cost`, `health`.
- `generate_structured`, `embed`, `cancel`, `usage`; request IDs and usage accounting.
- Normalized errors: timeouts, HTTP 429, 5xx, authentication, insufficient balance, unsupported model/format, schema failure, oversized context, cancellation, safety refusal, transient transport.
- Local Ollama adapter, optional A.E.S.I.R. native adapter, OpenRouter adapter and future adapters with tests.
- Profile stable model IDs, provider endpoint preferences, privacy constraints, output format support, max context and maximum output tokens.
- **Embedding compatibility is separate from chat-model interchangeability.** Store exact embedding model + dimension + tokenizer/vector-space identity. Never combine incompatible embeddings merely because dimensions match.

## 4.2 Cloud features and controls

- Choose provider/model/region where available; strict no-cloud default for newly installed systems.
- Batch mode and asynchronous concurrency with upper bounds.
- Requests per second/minute, tokens/minute, max in-flight, queue size, burst, jitter.
- Per-job, per-day and per-month spend ceilings; estimate and verify usage on every response; stop at cap even if model fallback is available.
- Sampling temperature, structured JSON schema, output token cap, retry budget, priority, context truncation policy with visible warnings.
- Configurable failover: retry same provider -> alternate provider for same model -> approved alternate model -> optional local fallback. This is an *explicit decision tree*, not blind retry.
- Use exponentiation with capped delay and jitter for 429/5xx/transient failures; respect `Retry-After`; do not retry 401/403 with same bad credentials.
- Model capability negotiation and JSON schema validator; malformed structured result -> bounded repair or fallback; publish no unvalidated graph rows.
- Content visibility preflight: list precise excerpts that will leave the computer, redact excluded content and obtain owner consent.
- Privacy filtering: Zero Data Retention or equivalent routing only when actually supported; refuse if profile requires it and none is available.
- Cloud outputs never override source evidence without validation.

## 4.3 Precision cost model

For Skein vocabulary discovery, one request per document (up to six 1,800-character excerpts and structured JSON output) is the baseline. Use actual tokenizer/provider responses from sample runs to forecast job token volume and pricing. Current user baseline is **2,757 documents**; predictions from document count alone are uncertain.

Track `input_tokens`, `output_tokens`, reasoning/cache tokens if provider reports them, price version, retry overhead, actual billed amount and local estimated electricity/resource time. Display confidence ranges and a “maximum spend” kill switch. Prices change; fetch model pricing dynamically, stamp the quote and never hardcode a permanent dollar estimate.

Do not assume OpenRouter accelerates every stage. First offload the vocabulary calls; keep existing local `nomic-embed-text` semantic space until a separately tested migration path exists.

## 4.4 Failover decision examples

| Error | Default behavior |
|---|---|
| transient DNS/socket | bounded retry/backoff, checkpoint progress |
| 429 | respect server delay, reduce concurrency and token rate |
| provider 5xx | retry; route to owner-approved compatible endpoint |
| unsupported JSON schema | switch to compatible structured-output method or validated repair |
| invalid entity response | retry with validation feedback, then quarantine source record |
| missing local GPU | CPU fallback only if permitted and resource-safe |
| no cloud budget | stop cloud requests; optionally queue for local mode |
| changed document during job | invalidate impacted stages, preserve completed compatible others |
| embedding mismatch | hard refusal, never silently re-embed with different model |
| corrupted checkpoint | preserve corrupted bytes for diagnosis; use last verified checkpoint |
| unexpected crash | resume unfinished stages after lease expiry and integrity check |

## 4.5 Cloud parallelism and job scheduling

Do **not** equate “parallel processes” with launching one OS process per request. Use configurable bounded async tasks/worker pools; use processes only for CPU-bound work or isolation. Build independent concurrency controls for chat extraction, embedding generation, parsing and graph calculation. Streaming progress must truthfully reflect completed *valid* records, not requests dispatched.

**Acceptance:** Re-run a sample dataset in local, hybrid and cloud modes and compare schema validity, entity recall, total costs, crash resilience and existing-corpus compatibility before enabling large scale.

---

# 5. Incremental Skein: from full rebuilds to living graph generations

## 5.1 Preserve original algorithm as a fallback

Do not delete the current Skein pipeline. Expose it as `full_rebuild_v1` for reproducibility and emergency reconciliation. Add `incremental_v2` behind a feature flag and verify on a cloned database before production.

## 5.2 Independent, reusable computation units

Persist extraction at minimum by:

- Stable source-document ID + content hash + source revision and visibility scope.
- Chunk IDs + exact normalized chunk text checksum.
- Extractor model name/version, prompt revision, extraction schema revision, sampling strategy.
- Successful named entities/aliases/types, confidence if validly modeled, evidence chunk IDs.
- Error/retry state and partial/incomplete status; never cache failure as valid empty result.
- Embedding model space and predicate vocabulary version.

Store derived per-document extraction records separately from the published graph so individual document changes do not erase prior completed work.

## 5.3 Incremental graph update algorithm

1. Snapshot consistent source-generation high-water marks under a read snapshot.
2. Compute a **reliable content manifest**, not solely COUNT and MAX(id). Detect deletion, in-place edits, retitles/source updates and changed parsing settings.
3. Determine added/changed/removed documents and affected chunk sets.
4. Reuse extracted vocabulary when the corresponding content/version inputs are identical.
5. Extract only changed documents; validate structural output before accepting it.
6. Reconcile aliases/entity identities through explicit entity-resolution rules; never conflate distinct people solely from a name similarity.
7. Maintain an inverted index mapping entity to supporting documents/chunks, mention counts and vector-stat aggregates.
8. For changed documents, retract old contributions before applying new ones; use reference counts and source-attributed relation evidence.
9. Recompute entity embeddings for affected entities from compatible chunk embeddings, not the entire corpus where avoidable.
10. Update nearest-neighbor candidates for changed entities **and old entities potentially displaced from top-K**. An exact/incremental or approximate strategy must account for both directions, not just edges from new nodes.
11. Reevaluate predicates only when relevant co-occurrence/evidence spans changed or algorithm versions are invalidated.
12. Recompute local clusters/neighborhoods as needed; schedule global reconciliation only when drift threshold triggers.
13. Validate relation evidence and graph invariants; write staged generation.
14. Compare graph against old generation; present additions/removals/quality deltas.
15. Publish through atomic generation-pointer switch after verification. Rollback swaps pointer to a prior valid generation.

## 5.4 Entity, edge, and provenance model

Minimum internal fields:

| Object | Required information |
|---|---|
| Document source | stable source URI/ID, origin/provider, source revision, content hash, timestamps, permissions |
| Chunk | source doc ID, version, location/page/heading, hash, embedding identity |
| Entity | canonical name, type, aliases, identity/merge evidence, ambiguity status |
| Mention | entity ID, chunk ID, offsets, excerpt hash, processing version |
| Relation | subject, predicate, object, weight, polarity, attribution, evidence, confidence calibration status |
| Graph generation | immutable ID, parent, source manifest, model/config versions, status, created/published timestamps |
| Graph delta | added/modified/removed entities/relations and reason |
| Source claim (future) | proposition, claim polarity, timestamp, attribution, quotation/denial/suspicion tags, provenance |

Existing Skein's typed edges are **heuristic candidate relationships**, not verified facts. Add independent claim-checking and negation detection before treating them as factual assertions.

## 5.5 Optional quality modes

- **Fast:** existing single model call per document, representative excerpts, source-wide string matching.
- **Balanced:** adaptive sample selection by document complexity/length/headings, higher coverage, bounded cost.
- **Deep:** full coverage through multiple section passes, specialized entity resolution, claim attribution, contradiction and temporal analysis.
- **Research:** human-confirmed source claims, multilingual vocabulary, domain-specific ontologies, community summaries, thematic graph synthesis.

Allow per-document overrides and selective deep reprocessing; preserve ability to compare results without discarding prior graph.

## 5.6 When to recompute everything

Triggers requiring explicit owner approval or scheduled maintenance: changing embedding vector space, major extraction schema, predicate semantics, entity-identity rules or incompatible graph generation; substantial accumulated graph drift; detected source corruption; benchmark-driven correction.

**Acceptance:** Adding 10 new documents does not reissue extraction for the other 2,757 unchanged documents; deleting one source retracts its evidence without deleting unrelated relations; a prior graph stays queryable throughout.

---

# 6. True pause/resume, quiet hours and checkpoints

## 6.1 Pause for Quiet user contract

Pressing Pause immediately blocks new heavy work. In-flight operations finish their current safe unit or are cooperatively canceled with a bounded timeout. Flush verified checkpoints and free local GPU/model resources where supported; mark the job **paused** only after the actual worker has stopped consuming its heavy resource budget. Quiet mode must not be a cosmetic icon.

- “Pause now” (safe completion boundary).
- “Pause after current document/batch/stage”.
- “Quiet window” recurring time ranges, owner-selected.
- “Resume manually” or “Resume when quiet window ends” as distinct choices.
- “Emergency stop” terminates workers after ensuring the last checkpoint is recoverable; possible loss of only unfinished current unit.
- Permit a read-only view, search and administrative controls while paused.
- Scheduled backup drive spinning may also make noise: quiet scheduling must consider backup I/O as a separate resource.

## 6.2 Checkpoint format and recovery

- Durable immutable input manifest and stage versions.
- Completed units, output record hashes, attempts, retries and provider usage.
- Checkpoints after each valid document, each embedding batch or bounded calculation block; configurable cadence.
- Atomic write+fsync or transactional DB commit; ensure last-good checkpoint pointer.
- Resume reconciles completed work instead of blindly retrying everything.
- Interrupted external response must use an idempotency/reconciliation strategy; usage/cost accounting acknowledges uncertainty.
- Termination in stage 4 must not lose stage 1 results.
- Source corpus changed since checkpoint: restart only impacted dependent units; refuse unsafe publication of stale graph.
- SIGHUP/SIGTERM/service reboot tests; hard power-loss simulation in controlled fixtures.

## 6.3 Acoustic policies

Measure fan sound empirically; do not invent decibel readings from hardware utilization. Support owner-controlled GPU-idle target, workload intensity slider, max VRAM/RAM/power budgets where supported, queue-to-sleep and optional “nighttime always paused”. Hardware fan controls are optional, tested separately, and must not override firmware safety behavior.

**Acceptance:** After a forced poweroff and reboot, resume continues from persisted completed units, produces a valid graph and does not rerun old expensive extraction unnecessarily.

---

# 7. Backups, graph snapshots, restore vault and dedicated document drive

## 7.1 Three independent safety layers

1. **Checkpoints:** unfinished computation state; recover/resume a job, not a substitute for a backup.
2. **Graph generations:** versioned Skein derived output and staged/published pointers; rollback a graph.
3. **Full Second Brain backup:** PostgreSQL primary rows, chunks, embeddings, derived rows, private inbound state/config necessary for recovery, compatible source revisions and model identities.

## 7.2 Dated backup naming and manifests

Suggested names:

    Bifrost_full_2026-11-04T202600-0500_<short-id>.dump
    Skein_graph_2026-11-04T202600-0500_<generation-id>.archive
    Bifrost_state_2026-11-04T202600-0500_<short-id>.tar.zst

Store timezone-offset-aware timestamps and an ISO timestamp in a signed/checksummed manifest. Use collision-resistant IDs, record schema/DB/server versions, artifact sizes, SHA-256/BLAKE3 checksums, backup scope, source-generation fingerprint and verification results.

## 7.3 Dedicated external drive

- User-supplied mechanical drive is reserved for **document and Second Brain recovery data**. Do not place unrelated models, transient caches, project workspaces or general file downloads on it.
- Discover by stable filesystem UUID/label and owner-selected mount; never assume `/dev/sdb` or write by device ordinal.
- Refuse mistaken target disks, unsafe mounts, read-only filesystems, low space and changed UUID identity.
- Mount on demand; unmount/eject after successful verification if configured; avoid wake-ups during quiet hours.
- File permissions and encryption at rest by owner selection; keys stored separately; never store decryption key solely on same drive.
- Failure mode: missing/unavailable drive -> clear pending status, no false successful backup; optional secondary destination only with explicit opt-in.

## 7.4 Backup modes

- Manual “Back Up Now” with selectable source-only, graph-only, full recovery.
- Automatic daily/weekly/after-big-ingest triggers, owner-configurable; avoid a full DB dump before each tiny incremental update.
- Pre-publish graph snapshot for substantial graph rebuilds.
- Before schema migration, provider/embedding change, bulk rewrite and destructive import: mandatory verified snapshot or refusal.
- Configurable retention (hourly/daily/weekly/monthly), retention dry-run, pinned backups, low-space warning.
- Merkle or file checksum manifests, periodic restore rehearsal into a new scratch database, restore logs and corruption alerts.
- Optional differential/incremental backup *only* after verifying database-consistent procedure. A directory copy of live PostgreSQL files is **not** a safe backup.
- Test backup under concurrent ingestion and graph computation using a coordinated consistent snapshot.

## 7.5 Restore wizard

1. Select timestamp and restore scope.
2. Verify file, integrity, encryption, formats and needed software.
3. Present a readable impact preview and incompatibility checks.
4. Restore into a **new scratch database** by default; never automatically overwrite the live corpus.
5. Validate counts, fingerprints, embeddings and sample retrieval.
6. Ask for a second explicit owner confirmation before any live switch; schedule downtime and preserve an independent pre-restore backup.
7. Switch connection/graph generation atomically where possible, then offer rollback.
8. Record result, reasons for any failure, and avoid treating “archive list readable” as a real restore test.

**Acceptance:** A fresh installation can recover documents, source provenance, embeddings, Skein graph, authorized service configuration (without copying secrets to public repos), and verification evidence.

---

# 8. Source Watchtower: automatic blogs, GitHub, local folders and revision-aware import

## 8.1 Discover existing local features first

The published ingest path already supports URL imports, inbox watchers, content-hash duplicate detection and stable completion records. The user reports a separately developed blog/GitHub auto-fetch mechanism that may live only on the installed machine. **Do not assume it is absent or duplicate it.** Audit local service units, scripts, cron, agent skills and configs; preserve any working collector.

## 8.2 Source connector contract

Each source adapter exposes:

`discover`, `list`, `get_metadata`, `fetch`, `delta_cursor`, `health`, `test`, `dry_run`, `schedule`, `pause`, `resume` and optional `export`.

Store stable source IDs, canonical URLs, revisions (ETags, commit SHA, provider revision), last checked/succeeded, pagination cursors, errors and credentials reference (not values). Separate “checked” from “imported” and from “relationship processing complete.”

## 8.3 Suggested connectors

- Public blog RSS/Atom and sitemap discovery; canonical URL de-duplication, HTTP caching (ETag, If-Modified-Since), content extraction.
- GitHub user/org/repository discovery, default/selected branch, subtree include/exclude globs, Markdown/text/code selection, pagination, commit SHA tracking, rate-limit-aware API usage.
- Owner-selected local folders with recursive/one-level mode, stable inode/path and hash tracking, excludes, symlink escape prevention, rename handling.
- Public web URLs and curated URL lists.
- Later optional Zotero, Calibre, RSS reader, standards corpus and local email export: design adapters without precommitting to every connector.
- Google Drive/Docs via dedicated adapter detailed below.

## 8.4 Duplicate and revision policy

- **Exact duplicate:** same normalized extracted content hash -> no second source copy unless owner explicitly creates a distinct bibliographic instance.
- **Same source changed:** new version linked to original, retained provenance and diff; update only affected downstream stages.
- **Different source, same content:** maintain source attribution without duplicating embeddings, when permissions permit.
- **Near duplicate:** optional similarity report, never auto-merge without policy.
- **Private vs public corpora:** no cross-user deduplication that exposes content or existence.
- **Removed upstream document:** mark source removed; do not automatically erase local copy unless owner enabled that action.
- **GitHub code changes:** anchor to commit SHA; avoid crawling huge autogenerated dependency directories by default.
- **Blog extraction variability:** detect changed extraction engine/template and avoid false “new versions” caused by formatting alone.

## 8.5 Source Watchtower GUI

Current/last/next scan; source count; attempted/succeeded/failed; new/updated/unchanged/duplicate; pending parse; pending embed; pending Skein; network bandwidth; retry cause; per-source graph growth. Offer “Inspect Changes”, “Retry Failed”, “Temporarily Disable”, “Run One Source Now”, “Run All”, and live source-specific logs with sensitive values redacted.

**Acceptance:** Repeated scheduled scans of unchanged sources insert zero duplicate knowledge rows; edits create a traceable version, not silent orphan documents.

---

# 9. Document editing: Bifröst workspace + optional LibreOffice integration

## 9.1 Distinguish reading, drafting, editing and publishing

Bifröst should provide integrated reading, annotation, comments, tags, headings, cross-references, highlights, drafts, diff, version history and search. These are **document-workspace functions**, not direct writes into the immutable Ingest source tables.

- Read-only original with stable document/chunk evidence.
- **Draft workspace** stores its own reversible versions and is clearly labeled.
- “Publish as new source version” invokes Ingest with a versioned write contract, explicit owner authorization and downstream incremental invalidation.
- Never overwrite an imported PDF or Google Doc silently.
- Preserve binary original for round-trip editing; keep extracted text and citations linked to origin.

## 9.2 Native Bifröst editor tiers

- Simple: rich text/Markdown basics, tables, checklists, links, tags and inline search.
- Advanced: headings tree, document outlines, backlinks, aliases, references, semantic related passages, side-by-side sources.
- Expert: source metadata, extraction/page anchors, document versions, edit diff, provenance inspector, citation manager and export format options.
- Optional collaborative editing later: optimistic concurrency, per-document ACL, conflict merge, no surprise remote writes.

## 9.3 LibreOffice integration options

Official LibreOffice supports UNO via external process and Python interfaces. Implement modular adapters rather than reinventing a complete office suite:

**A. Open-in-LibreOffice:** export temporary **controlled** ODT/DOCX copy, launch Writer/Calc/Impress locally, detect save via checksum/watcher, import as draft only after an explicit review.

**B. Headless conversion service:** PDF/DOCX/ODT/RTF/HTML conversion with a dedicated LibreOffice profile, bounded job sandbox, timeouts, memory cap and format-preservation tests.

**C. UNO integration:** optional Python/UNO process with version-checked socket/pipe connection; document reading, bookmarks, styles, tables, comments, exports and batch edits. Prefer loopback/pipe access, no public UNO listener, and a single dedicated profile per worker.

**D. Editing bridge:** optionally open selected Bifröst document in Writer, save as a new revision and show diff/metadata changes before ingestion.

**E. Future office integration:** templates, bibliography, citation insertion, document merge, spellcheck, revision comparison and batch format conversion.

Potential security hazards: untrusted Office macros, embedded scripts, external links, template execution, malicious documents, zip bombs, filesystem paths. Default macros disabled, no arbitrary shell execution, sandbox conversions, isolate temp dirs, strip secrets from documents before cloud export. Preserve original file metadata and disclaim imperfect format round-tripping.

**Acceptance:** ODT/DOCX -> edit in Writer -> reviewed Bifröst draft -> versioned Ingest publication -> incremental Skein works, with the original still restorable. Headless processes cannot access the Kista vault or unrestricted filesystem.

---

# 10. Google Docs / Drive import and export: files, batches and whole folders

## 10.1 User experience

- Connect or disconnect a Google account with explicit consent.
- Browse/select **one document**, **arbitrary multiple documents**, **one folder**, or **multiple folders**, with recursive option.
- Preview scope/count/size/permissions and choose formats and which side is authoritative.
- Import only, Export only, Manual Two-Way Sync, or Scheduled Two-Way Sync (advanced).
- Select overwrite behavior: skip, rename, new revision, merge draft, interactive conflict resolution; destructive overwrite off by default.
- Filter by name, MIME type, date, modified since, owner/shared, folder, document state.
- Preserve upstream title, stable file ID, URL, revision ID, folder path and source attribution in private records.
- Resume after interruption with per-file success, cursor and idempotency records.
- Show sync events and exact changes in Source Watchtower.

## 10.2 Correct Google API route

- **Drive API v3** lists files/folders with paginated `files.list` and a `q` filter, traverses nested folders, tracks changes and exports native Google Docs.
- **Drive files.export** converts native Google Workspace document content to supported output MIME types; use negotiated DOCX/plain text/PDF/other supported forms.
- **Docs API** is used for fine-grained editing when required, including `documents.get` and `documents.batchUpdate`.
- **Drive files.create / upload** can create new files; native Docs creation/export is versioned and format-specific.
- Use `changes.getStartPageToken` and `changes.list` for incremental sync where permissions allow; tokens and channel subscriptions require lifecycle management.
- For collaborative writes, honor `writeControl.requiredRevisionId` (or explicitly selected alternative) to prevent stale edits from clobbering someone else's work.
- Avoid assuming Google Docs export preserves all rich text, comment threads, suggestions, embedded objects or layout. Record fidelity and limitations by format.

## 10.3 Authentication, personal setup and reuse of an existing Yrsa connection

**Critical:** User reports an existing Google developer/OAuth setup connected to Yrsa. Discover and validate the existing authorized configuration **locally**; do not ask the owner to create a new Google Cloud project unless required. Reuse an existing OAuth client and allowed scopes only when its owner, configured app type, permitted redirect URIs, consent-screen status and intended use actually permit this.

For a publicly distributed self-hosted program, each user must have an independent OAuth authorization and isolated token store. Support a **bring-your-own OAuth client** setup wizard with plain-language instructions. A shared app client may be supported only if the distributor intentionally manages consent and verification. Do not bundle the owner's developer credentials in releases or GitHub.

Prefer the narrow `drive.file` scope with a user picker where the intended UX is supported. Broad unrestricted folder discovery may require a broader scope and additional verification/consent; expose the tradeoff rather than silently escalating. Detect insufficient scope and explain precisely which operation is unavailable.

- OAuth PKCE/installed-app/loopback flow where applicable.
- Separate Google identity per connection; display a pseudonymous local label instead of account email in public diagnostics.
- Encrypt refresh tokens via Kista or the server's approved secret store, not logs, repo, model prompt, browser localStorage or exported project status.
- Revocation, expiry, re-consent, scope upgrade and auth-failure recoverability.
- Rate limits, exponential retry and cursor continuation.
- Do not let an AI with “read knowledge” permission gain Google Drive export/write authority.
- Link each sync job to the owner authorization and destination folder capabilities.

## 10.4 Sync safety

Use a durable local mapping table:

`connection_id, provider_file_id, folder_membership, mime_type, remote_revision, local_document_id, local_version_id, content_hash, direction, last_sync, result, conflict_state`.

Detect “changed on both sides” before writing. Store backup of pre-sync version. Prefer explicit review or conflict copy. For whole folders, handle partial permissions, moved files, shortcuts, trashed items, subfolder loops, pagination and duplicate paths. On permission loss, mark source unavailable, not deleted.

**Acceptance:** The owner can select one, ten, or a whole folder of Google Docs; dry-run count; import; re-run with zero duplicates; edit one document on each side; detect conflict without destroying either version; export selected local drafts back into an owner-selected destination.

---

# 11. Project Command Center: inside Bifröst, not project #eight

## 11.1 Mission

Project management belongs as an **optional Bifröst module** integrated with the existing knowledge corpus and permitted GitHub metadata. It must remain usable with no AI, and must not force the project registry itself into thousands of untracked Markdown notes.

## 11.2 Core objects

`project`, `repository`, `workstream`, `milestone`, `task`, `dependency`, `risk`, `decision`, `agent_assignment`, `machine`, `workspace`, `checkpoint`, `artifact`, `status_event`.

Keep structured records in separate namespaced Bifröst tables; link to knowledge documents via stable IDs. Editing a task should not cause an automatic Skein full rebuild.

## 11.3 Live project visibility

- Active / queued / parked / blocked / completed / archived, with clear timestamp and source of truth.
- Last actual commit, issue/PR status, CI result, blockers, next approved action and evidence.
- Assignments across humans, Yrsa and her subagents, without claiming agents are online unless observed.
- Machine selection and resource budget; avoid overcommitting Yrsa's host cache/session resources.
- Backlog vault for unlimited ideas that do **not** automatically launch coding sessions.
- Dependency visualization, critical path, per-project chronological activity and risk summaries.
- Project daily digest with “Decisions needed from me”, separate from unsolicited work reports.
- Search cross-project documentation through Bifröst and connect findings to tasks with traceable references.

## 11.4 GitHub integration

Use GitHub APIs with user-authenticated read/write roles; begin **read-only**: repos, metadata, branches, commits, issues, PRs and workflow status. Later optionally enable owner-confirmed issue or PR creation/edits. Do not embed keys or perform destructive Git actions from a default RAG query. Deduplicate webhooks/polling by event ID and revision.

## 11.5 Project status changes

An event should have: `actor`, `timestamp`, `source`, `before/after`, `evidence`, `correlation/job_id`. Agent-reported status is provisional until corroborated by local Git/CI when applicable. “Completed” requires a defined exit criterion, not a confident LLM sentence.

## 11.6 UX

Project map, kanban, milestone timeline, dependency web, agent activity, host-resource lanes, weekly goals, idea vault, relationship-to-knowledge view and “What needs me?” panel. Optional Samtal integration uses Bifröst knowledge APIs, not a new central database.

**Acceptance:** One owner dashboard can show many GitHub repos while only allowing a chosen small number to be active; meaningful status survives AI conversation loss and host reboot.

---

# 12. Kista: optional secret capabilities, absolutely not searchable credentials

The public Kista repository describes a self-owned Fernet encrypted secrets vault, including API keys and sensitive notes. **Its purpose here is to securely provide a specific credential to a privileged worker**, not to ingest secrets as knowledge or allow autonomous assistants to search the whole vault.

## 12.1 Adapter design

- `SecretSource` abstraction with built-in OS keyring / protected local secret reference and optional Kista provider.
- “Use OpenRouter credential” or “Use selected Google OAuth authorization” are capabilities to the provider worker, not a `get_all_secrets` tool.
- Secret retrieval happens only within a privileged local process at call time; redact command line, traceback and subprocess environment captures.
- Prefer protected file descriptors, in-memory scoped tokens or IPC secrets injection; never put values into argv or serialized job payload.
- Clear ephemeral values after use as feasible; no promise that Python's garbage collector guarantees zeroization.
- Key rotation, expiry, denied access, vault locked/unavailable, and audit of **which capability** was used (not secret value).
- Backup Kista vault only via its own encrypted export with keys separately protected; do **not** include vault plaintext or master key in normal Second Brain backups.
- Kista remains independently installable and replaceable; all core local functionality works without it.

## 12.2 Secret-leak tests

Insert deliberately fake canary credentials; assert they never appear in UI, API JSON, error reports, LLM prompts/responses, retrieval output, Skein vocabulary, embeddings, source documents, job ledger, telemetry, backup manifest, Git changes or sample data. Perform security-focused end-to-end tests before any cloud/Google rollout.

**Acceptance:** Authorized workers can call a provider through Kista without any ordinary Bifröst or agent client ever reading the secret.

---

# 13. Universal Bifröst access for other applications and agents

## 13.1 Bifröst as a federated knowledge service

Other user applications should optionally discover and query Bifröst through a **stable, versioned, authenticated API**. Not all external apps should access all knowledge.

Introduce an SDK/adapter contract:

- `brain.identity`, `brain.capabilities`, `brain.health`.
- `corpora.list` subject to permissions.
- `search.hybrid`, `search.semantic`, `search.keyword` and `search.graph`.
- `documents.get`, `passages.get`, `entities.neighbors`, `graph.path`.
- `sources.append` under explicitly granted append scope, subject to bounded ingest queue.
- `changes.subscribe` with cursor/ack/replay, optional webhook with signed requests and expiring subscriptions.
- `jobs.submit`, `jobs.status`, `jobs.pause`, `jobs.resume` only with specific elevated owner/operator capability; read-only AI keys cannot launch global builds.
- `project.list`, `project.search` and `project.events` optional with separate ACL.
- `export.request` requires distinct permission and owner-selected scope, destination and consent.

## 13.2 Identity, privacy and consent

- Separate keys per application/agent, scopes per corpus, per method, per source, per quantity and per time window.
- Read, append, graph-admin, project-read, project-write, export and credential-use permissions are **not interchangeable**.
- Default deny bulk export and external cloud transmission of document excerpts.
- Origin policy for Tailscale/local requests and HTTPS for nonlocal connections; do not expose PostgreSQL publicly.
- Allow explicit per-document exclusions and private/secret classification; do not leak document existence through search counts or timing where avoidable.
- Per-actor audit log and quota; token rotation/revocation and queue cancellation on revocation where appropriate.
- Retrieved documents are untrusted source data, not instructions to agents; defend against prompt-injection and HTML/script content.
- Signed event IDs and replay cursors for durable subscriptions, idempotent append, bounded context windows.

## 13.3 Integration family

Potential consumers: Project A.E.S.I.R., Hermes/Runa agents, Yrsa/Muse where an authorized client is available, WYRD, companion engines, Samtal, Second Life integrations, research writing tools and custom apps. These are **proposals, not claims of live compatibility**. Publish a minimal Python SDK, HTTP OpenAPI, optional MCP stdio adapter and test fixtures.

## 13.4 Agent memory is not one undifferentiated bucket

Maintain explicit boundaries between sourced facts, speculative inferred edges, project states, companion-specific episodic memories, and credentials. Require provenance and visibility labels in retrieval. Do not force every personal conversation into the public/shared Second Brain.

**Acceptance:** A separate local app can authenticate read-only, retrieve a cited passage, lose/recover network connection, and never obtain forbidden source fields or admin methods.

---

# 14. Observatory UI: serious instrumentation plus gloriously fun technical pages

## 14.1 Design doctrine

The user expressly wants expansive, playful, technically dense screens **even when some primarily exist for exploration and enjoyment**. Do not strip that personality away in the name of minimalist UX. Keep a clean Standard homepage and an expansive optional observatory with tabs, charts, animation and drill-downs.

Each widget labels **live**, **historical**, **scheduled**, **estimated** or **simulated**. Never show a fake activity feed as if actual. Expensive visualizations are cached and/or opt-in, honoring Quiet Mode.

## 14.2 Proposed tab collection

| View | Purpose |
|---|---|
| Hliðskjálf Command Center | One dashboard for status, active jobs, source health, quiet mode |
| Mímir's Chronicle | Full timeline, previous work, errors, decisions and real audit records |
| The Next Weaving | Actual task queue, stages, dependencies, next scheduled operations |
| Skein's Loom | Graph extraction, versions, relation deltas, pause/resume and validation |
| Skry's Sight | Query-time entity neighborhoods with evidence and mode diagnostics |
| Source Watchtower | Blogs, GitHub, Google Docs, local folders, last scans, change maps |
| Knowledge Cosmos | 3D chunks/documents/entities, clusters, temporal growth, filtered paths |
| Relationship Archaeology | Compare two graph generations, new/lost/changed edges |
| Corpus Anatomy | Documents by size/type/source/age/language, duplicates, missing embeddings |
| Retrieval Laboratory | Query inspector, vector/BM25/RRF, explain scores, recall tests |
| Model Forge | Local/OpenRouter/A.E.S.I.R. provider routing, tokenizer and costs |
| Resource and Sonic Observatory | GPU/VRAM, CPU/RAM, queues, noise-friendly windows and actual worker pauses |
| Backup Vault | Attached document drive, dated snapshots, verification, restore rehearsal |
| LibreOffice Workshop | Open/Edit/Preview/Compare/Convert/Publish drafts |
| Google Bridge | File picker, folders, sync jobs, conflict/permission diagnostics |
| Project Longhouse | Registry, workstreams, dependencies, Yrsa agent reports, idea vault |
| Agent Embassy | Keys/scopes, approved integrations, recent activity and quotas |
| Security Watch | Permissions, canary test outcomes, audit events, rejected attempts |
| System Anatomy | Service topology, DB table sizes, index health, cache maps, API response times |
| Research Playground | Experimental graph algorithms, visualizations, side-by-side runs |
| Temporal Knowledge Atlas | Animated history of graph/source growth from recorded generations |
| Knowledge Curiosities | Top linked entities, unusual terms, bridge concepts, rare connections |

## 14.3 Technical visualizations

- Stage Gantt with real spans, CPU/GPU I/O overlays, per-stage resource burn and retry paths.
- Queue heatmap, provider/model latency histograms, quota gauges and token-cost waterfall.
- DAG editor/inspector with skip/fallback conditions and artifacts at every edge.
- Sankey-style source -> parse -> embed -> extract -> graph -> export flows.
- Corpus growth calendar, per-source freshness, duplicate savings and document-chunk distributions.
- Graph connected components, node degrees, shortest evidence paths, link confidence and relation predicate distributions.
- Temporal graph difference animation, side-by-side source texts with synchronized citations.
- 3D graph “constellations” and cluster landscapes as optional cached work, not continuous mandatory CPU/GPU.
- Backup storage timeline, verification coverage, age of last restorable generation.
- An “explain this number” affordance on every metric with its source, formula and refresh time.

## 14.4 Performance and accessibility

- Render sampling/viewport culling and progressive loading of 3D graphs, not 67,761 DOM elements all at once.
- Browser processing budgets, resize and mobile layout tests.
- Motion-reduction and glow-reduction settings, keyboard navigation, screen-reader labels, no mandatory animations.
- Preserve existing Cyber-Viking visual design principles; do not blindly copy another product's UI.
- Textual status for every graph and animation; cached panels are marked stale when disconnected.

**Acceptance:** Simple homepage remains responsive during a full build; Expert user can inspect detailed stage state; playful visualizations never silently start expensive computation during quiet time.

---

# 15. Clean-room competitor research and original feature implementation

## 15.1 Research set

Evaluate public behavior, user-facing concepts and officially documented interfaces in Obsidian, Logseq, Anytype, Capacities, Tana, Notion, AnythingLLM, Khoj, LightRAG, Microsoft GraphRAG, RAGFlow and similar public systems. Treat comparisons as time-stamped technical research, not ungrounded claims of product superiority.

Potential capability families:

- Personal knowledge editor: backlinks, tags, object types, journal, block references, graph navigation, templates.
- Deep knowledge processing: hierarchical sections, entities/relations/claims, event timelines, graph communities, local/global retrieval, provenance-aware synthesis.
- Production data ingestion: format-aware parsers, table/image extraction, pipelines, source synchronization, state/repair screens.
- Agent support: API/MCP, scoped read/write, action execution with user confirmation, shared memory fabric.
- Operations: queues, pause/restart, checkpoints, backups, lifecycle management, testing, cost visibility.

## 15.2 Clean-room practice

1. Researchers observe **lawfully accessible public behavior and documentation**, document feature requirements in neutral terms, and record sources/licenses.
2. A separate implementation team designs original data models, algorithms, visuals and tests against functional requirements; no copying of proprietary text, UI artwork, protected code or nonpublic internals.
3. Permissively licensed code may be reused only when provenance, copyright notice, conditions, patents and compatibility are verified; this is not “clean-room reverse engineering” and should be tracked separately.
4. Explicitly reject “copy competitor code and rename variables” or unauthorized reverse engineering of access controls/services.
5. Create independent black-box feature tests and usability tests. Use own screenshots/art assets with original cyber-Viking style.
6. Maintain SPDX SBOM, third-party notices, architecture decision records, release attribution and security review.

## 15.3 Research deliverables

For every comparator: feature inventory, verified source link/date, semantic behavior, scaling patterns, algorithmic options, accessibility strengths, resource cost, privacy assumptions, independent implementation specification, tests and prioritization. Avoid creating a dependency on a competitor to run Bifröst.

---

# 16. Detailed data and service contracts

## 16.1 Proposed namespaces/tables (illustrative only)

- `brain_source`, `brain_source_revision`, `brain_document_version`, `brain_sync_cursor`, `brain_source_scan`.
- `brain_job`, `brain_stage_attempt`, `brain_checkpoint`, `brain_artifact`, `brain_resource_reservation`.
- `brain_extraction_cache`, `brain_entity_evidence`, `brain_graph_generation`, `brain_graph_delta`.
- `brain_snapshot`, `brain_backup_manifest`, `brain_restore_test`.
- `brain_draft`, `brain_edit_revision`, `brain_export_job`, `brain_sync_conflict`.
- `brain_project`, `brain_workstream`, `brain_task`, `brain_decision`, `brain_agent_activity`.
- `brain_connector`, `brain_authorization_ref` (references only; never store token plaintext).
- `brain_audit_event`, `brain_telemetry_sample` (privacy-filtered, bounded retention).

Schema evolution must be forward-compatible with current `documents`, `chunks` and `skein_*` tables until an explicit tested migration window.

## 16.2 API guidelines

- `/api/v2/jobs`, `/api/v2/jobs/{id}/pause`, `.../resume`, `.../cancel`, `.../events`, `.../stages`.
- `/api/v2/graph/generations`, `.../diff`, `.../stage`, `.../publish`, `.../rollback`.
- `/api/v2/backups`, `.../verify`, `.../restore/preview`, `.../restore`.
- `/api/v2/sources`, `.../scan`, `.../versions`, `.../sync-status`.
- `/api/v2/connectors/google`, `.../select`, `.../sync`, `.../conflicts`.
- `/api/v2/workspace/drafts`, `.../publish`, `.../export`.
- `/api/v2/projects`, `.../events`, `.../dependencies`.
- `/api/v2/telemetry`, `.../history`, `.../health`.
- `/api/v2/agent/capabilities`, `.../search`, `.../passages`.

All endpoints: versioned OpenAPI schema, explicit authentication/scopes, pagination/cursors, errors with stable codes, rate limits, idempotency keys on writes, audit trails, and no raw secret disclosure. Preserve v1 endpoints until a deprecation window and compatibility tests.

## 16.3 Event taxonomy

`source.scan.started/completed/failed`  
`document.added/changed/unchanged/deduplicated`  
`job.queued/started/paused/resumed/retrying/failed/completed`  
`stage.checkpointed`  
`graph.staged/validated/published/rolled_back`  
`backup.created/verified/restore_tested`  
`provider.throttled/failover/disabled_by_budget`  
`sync.conflict/authorized/write_completed`  
`project.status_changed/decision_required`  
`security.denied/credential_rotated`

Never infer completed events from planned ones. Event consumers require at-least-once delivery and deduplication by event ID.

---

# 17. Tests, safety gates and acceptance laboratory

## 17.1 Core data preservation tests

- Deterministic sample corpus with duplicate, changed, renamed, deleted, giant and maliciously formatted documents.
- Fail after every stage and before/after graph publish: prior good generation stays queryable.
- Repeated task execution creates no extra authoritative documents or duplicate published relations.
- Concurrent ingestion and graph staging respect immutable source generations.
- Externally changed source mid-job invalidates only relevant stages.
- Graph delta equals a clean full rebuild within defined measurable error tolerance; verify entity alias and edge asymmetry cases.
- Tokenizer/embedding model drift is refused or deliberately migrated.

## 17.2 Fault injection matrix

Run reproducible controlled tests for: SIGTERM, SIGKILL, machine reboot, PostgreSQL disconnect, disk full, backup drive removal, corrupted checkpoint, Unicode parsing failure, LibreOffice process hang, Google OAuth revoke, Google pagination/change cursor expiration, OpenRouter 429/5xx/timeout, provider no-response, cloud cap exhaustion, malformed JSON, denied scopes, two operators starting same build, inaccessible Kista vault and stale source fingerprint.

## 17.3 Security testing

- Threat model: prompt injection, SSRF, path traversal, cloud exfiltration, agent privilege escalation, OAuth CSRF/redirect abuse, malicious document macros, API replay, forged backups, dependency compromise.
- Fuzz parsers and schema validators; sandbox untrusted doc conversions.
- Canary-secret leak tests covering all pipelines and artifacts.
- Prove read-only keys cannot call build/restore/export/write.
- Prove public project artifacts have no real credentials or private documents via secret scanner and manual inspection.
- Backup restore to scratch with simulated changed schema and wrong key.
- Credential rotation/revocation does not let queued jobs continue with revoked rights.

## 17.4 Quality evaluation

Gold-standard annotation set spanning mythological sources, technical Markdown, large PDFs, code docs, multilingual Norse names and documents with negations or contradictory claims. Measure extraction recall/precision, relations with direct evidence, false merge rate, search recall@k, citation correctness, graph stability, cloud/local differences, duplicate detection and cost. Compare with untouched baseline, never promote new extraction method purely on appearance.

## 17.5 User-experience tests

- Untechnical user finishes default update without learning the underlying graph stages.
- Expert changes provider, workers, rate and budgets with clear validation.
- Pause for Quiet actually returns GPU resource to an acceptably idle state.
- Poweroff at 70% and resume without earlier steps repeated.
- Google one/many/folder import/export with conflicts and two-way sync in owner-approved test workspace.
- LibreOffice round-trip with formatted sample docs, tables and images.
- Project center survives lost agent sessions without inventing commits/status.
- Data-rich observatory remains accessible with animation disabled and limited GPU.

---

# 18. Phased engineering plan and explicit exit gates

Prioritize **foundational preservation and recovery before increasing processing throughput**. These are implementation phases, not estimates of elapsed time. Multiple safe research tasks can proceed concurrently without enabling seven major active code streams.

## Phase 0 — Inventory and recovery baseline

**Owner:** Bifröst operator and architecture.  
**Tasks:** read-only installed-state audit; repository/source drift; genuine blog/GitHub collectors; service status; model configs; graph stats; database size; current backup drive identity; benchmark and secret scan.  
**Exit:** verified inventory, source-preservation backup, hardware baseline, no live data mutated.

## Phase 1 — Backups and restore vault

**Tasks:** full document recovery archive, dated names, checksums, optional dedicated-drive mount, manual save/verify/restore preview, scratch restore test, retention preview.  
**Exit:** a verified external backup and successful rehearsal restore; no secrets in Git.

## Phase 2 — Durable job engine and Pause for Quiet

**Tasks:** work ledger, stage contract, executor, checkpoint format, lease recovery, quiet-mode controls, resource admission, progress UI, restart/resume tests.  
**Exit:** safe pause, shutdown, restart and resume on a representative build; search stays available.

## Phase 3 — Incremental Skein v2 and graph generations

**Tasks:** manifest, extraction cache, retraction of old source contributions, entity reconciliation, affected-edge recalculation, staged publication, graph snapshot/rollback, benchmark equality checks.  
**Exit:** unchanged documents incur no redundant model calls; previous graph survives failed build; delta quality measured.

## Phase 4 — Local/cloud/hybrid provider workbench

**Tasks:** provider abstraction, model discovery, JSON schema validation, OpenRouter opt-in, concurrency/rate/cost knobs, failover, audit/canary tests.  
**Exit:** 50–100 document local/cloud/hybrid samples pass quality, privacy, cost and failure gates before full deployment.

## Phase 5 — Source Watchtower

**Tasks:** inventory Yrsa's existing collectors, unify source adapters, GitHub/blog scans, source version and dedup history, schedule/quiet controls and live UI.  
**Exit:** repeated scans detect edits accurately, do not duplicate unchanged source, and report pending graph processing.

## Phase 6 — Bifröst document workspace and LibreOffice

**Tasks:** drafts/revisions, contextual editing and diff, Reader-to-Writer roundtrip, sandboxed conversions, reviewed publish via Ingest, format fidelity tests.  
**Exit:** no accidental edit of canonical source; reversible round-trip tested.

## Phase 7 — Google Docs/Drive bridge

**Tasks:** existing Yrsa OAuth investigation, user-owned setup wizard, file/folder picker, paginated import/export, sync cursor, conflict review, revocation controls.  
**Exit:** individual/multi/folder workflows and failure recovery validated with test documents; zero credentials in repo.

## Phase 8 — Project Longhouse inside Bifröst

**Tasks:** project registry schema, read-only GitHub metadata, agent/source status, dependencies, timelines, idea vault, searchable project documents.  
**Exit:** project status remains durable and useful without another separate project management app.

## Phase 9 — Optional Kista and app federation

**Tasks:** capability-only secret source, canary leak tests, versioned API/SDK, optional MCP, app-specific scopes, integration guides.  
**Exit:** authorized app can query cited knowledge and nothing more; Kista secrets remain unreachable from normal RAG.

## Phase 10 — Advanced science and the observatory

**Tasks:** multi-stage DAG builder, quality modes, claim-aware deep extraction, visual audit/profiling pages, graph history animation, accessible performance optimization.  
**Exit:** expert tools are technically honest, benchmarked and optional; simple mode remains one click.

## Cross-phase governance

For each phase use: cartography -> spec -> threat model -> fixtures -> implementation -> tests -> recovery proof -> public docs -> release notes. Avoid seven simultaneous heavy coding projects. Build adjacent features as separate guarded tasks inside this ecosystem, coordinate through the Bifröst Project Longhouse once available.

---

# 19. First actionable implementation slices

These are deliberately narrow enough for one or two coding agents to execute without destabilizing the whole stack.

| Slice | Repository | Deliverable | Verification |
|---|---|---|---|
| S-001 | Bifröst | Read-only actual installation inventory command | No writes/secrets |
| S-002 | Bifröst | Backup manifest/verify library and GUI preview | Scratch restore success |
| S-003 | Bifröst | Durable job store and status endpoint | Restart resilience |
| S-004 | Skein | Pure stage output contracts for old algorithm | Same final graph on fixture |
| S-005 | Skein | Persistent per-document extraction cache | Zero unnecessary re-extract |
| S-006 | Bifröst/Skein | Pause/resume protocol with VRAM release validation | Quiet mode real |
| S-007 | Skein | Staged graph generation + pointer publish | Safe rollback |
| S-008 | Bifröst | Provider adapter interface and bounded async executor | Rate/cap/failover tests |
| S-009 | Bifröst | OpenRouter sample mode only | Budget and data-sharing consent |
| S-010 | Ingest/Bifröst | Source revision IDs and external scan history | No duplicate ingest |
| S-011 | Bifröst | Source Watchtower UI | Actual last/next/retry |
| S-012 | Bifröst | Draft/version editing service | Read-only corpus invariant |
| S-013 | Bifröst | LibreOffice subprocess/UNO prototype | Macros disabled, timeouts |
| S-014 | Bifröst | Google Drive picker read-only import prototype | Per-user OAuth and pagination |
| S-015 | Bifröst | Google export/sync conflict prototype | No silent overwrite |
| S-016 | Bifröst | Project registry/adapter | No standalone app |
| S-017 | Bifröst/Kista adapter | Secret capability interface | Canary never leaked |
| S-018 | Bifröst | Versioned external knowledge SDK | ACL and denial tests |
| S-019 | Bifröst | Observatory activity timeline | Honest event taxonomy |
| S-020 | All | CI, dependency/license review, migration guide | Full regression and restore gate |

Each slice requires an explicit owner, source branch, tests and rollback plan. No production deployment until relevant gates pass.

---

# 20. Distribution, onboarding and public-repo security

## 20.1 End-user setup

First-run wizard asks only what is needed at the chosen feature level:

1. Configure local database and embedding model or connect existing installation.
2. Select basic/advanced/expert UI.
3. Optionally select dedicated document backup destination.
4. Optionally connect OpenRouter with explicit privacy and cost controls.
5. Optionally connect LibreOffice and Google (with independent OAuth authorization).
6. Optionally enable Kista, source scans, project registry and external-app keys.

Support exports of **sanitized configuration templates** only. Never export key material, private data, or source contents as public bug reports.

## 20.2 Repository hygiene and release checks

- Maintain `.gitignore` for private dotenv, tokens, OAuth files, local DB backups, Kista vault, private inbox, downloaded documents, embeddings, logs and generated caches.
- Public samples contain invented non-sensitive data; no real account emails, API keys, client secrets, private Google folders, service URLs or local database credentials.
- CI scanning with Gitleaks/TruffleHog-style scanner, binary inspection, secret-canary regex tests and block-on-detection.
- Review commit trees before every push; a clean current diff does not prove old history contains no secret, so audit history before public release.
- Never make logging sensitive payloads the debugging default.
- Use dependency lockfiles, SBOM/license review, versioned migrations, signed release artifacts where feasible.
- Preserve owner-controlled backups offline. **GitHub source repos are not a substitute for knowledge backups.**

## 20.3 Contributor documentation

- `SYSTEM_VISION.md`, `DOMAIN_MAP.md`, `ARCHITECTURE.md`, `PROJECT_LAWS.md`, `INTERFACE.md` and the existing Mythic Engineering role pattern remain authoritative.
- Implement a new stable public Skein/Skry function in its owning repo, release it, then update Bifröst dependency.
- Each new feature has truthfully labeled “Implemented”, “Experimental”, “Roadmap” states.
- Maintain change logs that distinguish local deployed state from public code.
- Publish portable instructions for independent end users without bundling the owner's personal developer credentials.

---

# 21. Success scorecard

This roadmap succeeds only if these are measurable and demonstrated:

| Objective | Target / gate |
|---|---|
| No-loss migration | Original documents/chunks preserved and verified |
| Safe graph build | Prior good graph remains available until validated new generation |
| Incremental processing | Unchanged documents do not repeat extraction |
| Quiet operation | Owner Pause actually stops heavy work and releases resources |
| Crash/reboot | Valid checkpoint resumes without duplicate published work |
| Cost control | Remote processing never exceeds hard authorized cap without explicit approval |
| Small GPU | Works on 6 GiB RTX 2060 without required cloud or giant model |
| Provenance | Extracted entity/relation can be traced to source evidence and generation |
| Backup | Dated archive on dedicated drive plus successful isolated restore test |
| Source scans | New/changed/duplicate/failed totals accurately reported |
| Editing | Versioned draft and reviewed publication, no silent source overwrite |
| Google bridge | One/many/folder workflows, per-user auth, conflict-safe exports |
| Project registry | Many projects tracked inside Bifröst; no separate app required |
| Kista | Optional capability-only credential usage, no secret ingestion |
| External apps | Scoped, versioned read/write APIs with proven access control |
| Technical joy | Rich useful and exploratory panels based on real or explicitly simulated data |
| Public safety | No personal secrets, tokens, private files or account details committed |

---

# 22. Research references and verified API contracts

**Existing original code and manuals**
- https://github.com/hrabanazviking/bifrost-viewer
- https://github.com/hrabanazviking/bifrost-viewer/blob/main/PROJECT_LAWS.md
- https://github.com/hrabanazviking/bifrost-viewer/blob/main/SECOND_BRAIN_MANUAL.md
- https://github.com/hrabanazviking/bifrost-viewer/blob/main/ingest/schema.sql
- https://github.com/hrabanazviking/skein-kg/blob/main/skein/core.py
- https://github.com/hrabanazviking/skein-kg/blob/main/TECHNICAL_MANUAL.md
- https://github.com/hrabanazviking/skry-kg
- https://github.com/hrabanazviking/kista

**Clean-room behavior and research references**
- https://github.com/HKUDS/LightRAG — incremental graph operations, provider concurrency, parser and quality workflow references
- https://github.com/microsoft/graphrag — modular graph indexing and community/claim research; as of the 2026 documentation, maintenance-oriented
- https://github.com/infiniflow/ragflow — advanced ingestion pipelines, parsing diagnostics and knowledge artifacts
- https://obsidian.md — linked personal knowledge editing concepts
- https://logseq.com — blocks and outliner concepts
- https://anytype.io — structured objects and local-first collaboration concepts
- https://tana.inc — typed workflow concepts
- https://github.com/Mintplex-Labs/anything-llm — document/assistant UI concepts
- https://github.com/khoj-ai/khoj — personal assistant/search integration concepts

**Official integration and API references**
- https://api.libreoffice.org/ — UNO/LibreOffice SDK
- https://help.libreoffice.org/latest/en-US/text/sbasic/python/running_scripts.html — external Python integration
- https://developers.google.com/workspace/drive/api/reference/rest/v3/files/list — Drive file/folder discovery
- https://developers.google.com/workspace/drive/api/reference/rest/v3/files — Drive file operations
- https://developers.google.com/workspace/drive/api/reference/rest/v3/changes/getStartPageToken — incremental changes
- https://developers.google.com/workspace/docs/api/reference/rest/v1/documents/batchUpdate — revision-aware edits
- https://developers.google.com/workspace/drive/api/guides/api-specific-auth — scope selection
- https://developers.google.com/workspace/docs/api/auth — Docs API OAuth requirements
- https://openrouter.ai/docs — routing, model providers, usage, structured outputs
- https://openrouter.ai/pricing — current pricing and rate-limit documentation

**Documentation caveat:** External services, pricing and APIs evolve. Before implementation, validate current official docs and provider capabilities. Research comparisons do not establish permission to copy code or that a given provider supports every feature.

---

# 23. Final architectural statement

Build **one Second Brain ecosystem with many well-defined optional capabilities**, not one monolithic untestable program and not a forest of unrelated new apps. Honor the existing boundaries and hardware. Make local mode trustworthy first. Add cloud assistance without compromising privacy or embedding integrity. Make every long computation resumable. Protect documents and graph generations with genuine backup and restore procedures. Bring editing, syncing, project coordination, and agent access under coherent Bifröst interfaces, while keeping their individual permission boundaries intact.

And make the Observatory *spectacular*: a cyber-Viking digital constellation of what the system knows, what it just did, what it will do, why it is doing it, how its resources are being used, what changed, and how to restore a previous state. The spectacle should be grounded in real instrumentation and never take away the user's sonic quiet or control over their own knowledge.

**Mímir's library grows. The keeper remains in charge.**
