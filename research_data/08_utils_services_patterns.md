# Utils & Services — Deep Patterns from 564+ Utility Modules
> Extracted from: utils subsystem (564 modules), services subsystem (130 modules)

## Utils Subsystem (564 modules) — Key Discoveries

### Data Structures
```
utils/CircularBuffer.ts   — fixed-size circular buffer
utils/Cursor.ts           — position tracking cursor
utils/QueryGuard.ts       — query rate limiting / deduplication
utils/array.ts            — array utility functions
```

**CircularBuffer** is used for keeping the last N events without growing memory — used for terminal scrollback, event history, streaming chunks.

**QueryGuard** — prevents duplicate concurrent queries. If the same query is already in-flight, return the pending promise instead of spawning a new one. Critical for preventing redundant API calls.

### Shell & Process
```
utils/Shell.ts           — shell command execution
utils/ShellCommand.ts    — shell command builder
utils/abortController.ts — AbortController management
utils/activityManager.ts — track active processes/operations
```

**activityManager.ts** — tracks all in-progress operations. When the user presses Ctrl+C, the activity manager cancels all pending work cleanly.

### Agent Utilities
```
utils/agentContext.ts         — current agent context access
utils/agentId.ts              — agent ID generation
utils/agentSwarmsEnabled.ts   — feature flag: swarms on/off
utils/agenticSessionSearch.ts — search across agentic sessions
utils/analyzeContext.ts       — analyze current context state
utils/advisor.ts              — advisor mode utilities
```

**`agentSwarmsEnabled.ts`** — swarm mode is behind a feature flag. It can be disabled entirely. This is important: **swarms are opt-in**, not the default. Regular single-agent mode is the default.

**`agenticSessionSearch.ts`** — can search across multiple agentic sessions. This suggests sessions are indexed and searchable — not just stored linearly.

### API & Network
```
utils/api.ts            — API client utilities
utils/apiPreconnect.ts  — preconnect to API on startup
utils/auth.ts           — authentication helpers
utils/authFileDescriptor.ts — auth via file descriptor (secure token passing)
utils/attribution.ts    — track request attribution
```

**`apiPreconnect.ts`** — pre-establishes TCP connections to the API server during the startup prefetch phase. By the time the first real request fires, the connection is already warm. This is why Claude Code feels fast.

**`authFileDescriptor.ts`** — passes auth tokens via Unix file descriptor rather than environment variables or files. More secure: the token never touches the filesystem.

### Visual & Terminal
```
utils/ansiToPng.ts    — convert ANSI terminal output to PNG
utils/ansiToSvg.ts    — convert ANSI terminal output to SVG
utils/asciicast.ts    — record/play terminal sessions (asciicast format)
utils/appleTerminalBackup.ts — Apple Terminal state backup
```

**`ansiToPng.ts` / `ansiToSvg.ts`** — the terminal output can be exported as images. Useful for sharing session screenshots programmatically.

**`asciicast.ts`** — sessions can be recorded in [asciinema](https://asciinema.org/) format for playback and sharing.

### Attachments & Media
```
utils/attachments.ts  — handle file attachments
utils/ansiToPng.ts    — ANSI to image (for attachment export)
```

### Argument & Context
```
utils/argumentSubstitution.ts — substitute arguments in templates
utils/analyzeContext.ts       — context state analysis
utils/agentContext.ts         — agent-specific context access
```

**`argumentSubstitution.ts`** — a template substitution system. Skills and commands can have `{{argument}}` placeholders that get filled at invocation time. This is how parameterized skills work.

---

## Services Subsystem (130 modules) — Deep Analysis

### AgentSummary
```
services/AgentSummary/agentSummary.ts
```
After an agent completes work, its output is summarized using the model. The summary is compact and structured. Parent agents see summaries, not full transcripts.

**Pattern:** Create a `summarize(transcript) → structured_summary` function for every agent type. The summary format is defined per agent type.

### MagicDocs
```
services/MagicDocs/magicDocs.ts
services/MagicDocs/prompts.ts
```
Automated documentation generation service. Takes code/content and generates documentation. The `prompts.ts` contains the specialized prompts for different documentation types.

**For NorseSagaEngine:** A `SagaDocs` service that auto-generates lore documentation from game session logs. Feed in battle events → get a saga verse.

### PromptSuggestion (Speculative Execution)
```
services/PromptSuggestion/promptSuggestion.ts
services/PromptSuggestion/speculation.ts
```

**`speculation.ts`** — pre-computes likely next prompts. Based on conversation context, speculates on what the user will ask next and starts computing responses. If correct, the response is instant.

**Algorithm (inferred):**
1. After each user message, analyze likely follow-up categories
2. Pre-send a "speculative" API request with the most likely follow-up
3. Cache the response
4. If user sends matching follow-up → return cached response instantly
5. If not → discard cache, respond normally

**Application for Sigrid:** After Sigrid gives a rune reading, likely follow-ups include "what does this mean for love?" or "what action should I take?". Pre-compute responses to the top 3 likely follow-ups.

### SessionMemory
```
services/SessionMemory/prompts.ts
services/SessionMemory/sessionMemory.ts
services/SessionMemory/sessionMemoryUtils.ts
```

**Two-phase memory:**
1. **Extract**: after each turn, use a specialized prompt to identify memorable facts
2. **Store**: write extracted facts to session memory
3. **Promote**: important facts from session memory are promoted to long-term memdir

The extraction prompts in `prompts.ts` are specialized per information type. Different prompts extract different categories of facts from the conversation.

### Analytics & Tracking
```
services/analytics/config.ts
services/analytics/datadog.ts                  — Datadog metrics
services/analytics/firstPartyEventLogger.ts   — internal event logging
services/analytics/firstPartyEventLoggingExporter.ts
services/analytics/growthbook.ts              — A/B testing / feature flags
services/analytics/index.ts
services/analytics/metadata.ts
services/analytics/sink.ts                    — analytics destination abstraction
services/analytics/sinkKillswitch.ts          — emergency analytics disable
```

**`sinkKillswitch.ts`** — analytics can be globally disabled with a killswitch. Privacy-respecting applications need this.

**`growthbook.ts`** — Anthropic uses [GrowthBook](https://www.growthbook.io/) for A/B testing and feature flags. Features are rolled out gradually via GrowthBook experiments.

**`firstPartyEventLogger.ts`** vs external — there's a distinction between first-party telemetry (to Anthropic's own systems) and third-party telemetry (Datadog). They're handled separately.

### API Clients
```
services/api/adminRequests.ts  — admin API endpoints
services/api/bootstrap.ts      — API bootstrap/init
services/api/claude.ts         — Claude API client
services/api/client.ts         — base HTTP client
services/api/dumpPrompts.ts    — debug: dump full prompts
services/api/emptyUsage.ts     — zero-token usage object
services/api/errorUtils.ts     — error handling utilities
services/api/errors.ts         — error type definitions
```

**`dumpPrompts.ts`** — a debug utility that dumps the full prompt being sent to the API. This was the key file that revealed the system prompt structure in earlier leaks. It exists as a service for development/debugging purposes.

**`emptyUsage.ts`** — a zero-value UsageSummary object used as initial state. Named constants for common default objects.

---

## Rust Runtime Utilities

From `rust/crates/runtime/src/`:

```
bash.rs          — shell command execution (Rust)
bootstrap.rs     — startup bootstrapping
compact.rs       — context compaction logic
config.rs        — config loading
conversation.rs  — conversation state management
file_ops.rs      — file operations
json.rs          — JSON utilities
mcp.rs           — MCP server communication
mcp_client.rs    — MCP client implementation
mcp_stdio.rs     — MCP stdio transport
oauth.rs         — OAuth flow
permissions.rs   — permission checking
prompt.rs        — system prompt builder (analyzed in doc 02)
remote.rs        — remote execution
session.rs       — session management
sse.rs           — Server-Sent Events streaming
usage.rs         — token usage tracking
```

**`compact.rs`** — the Rust implementation of context compaction. When the context window fills, `compact.rs` summarizes older content to make room for new content. This is separate from the Python `compact_messages_if_needed()` — it's a deeper, model-aware compaction.

**`sse.rs`** — Server-Sent Events for streaming. The streaming API uses SSE; this module handles parsing the stream. Each chunk is an event; the `message_delta` event contains text tokens; `message_stop` signals completion.

**`mcp_stdio.rs`** — MCP servers communicate over stdio (standard input/output). The Rust runtime handles spawning MCP server processes and communicating via pipes.

**`oauth.rs`** — full OAuth2 flow implementation in Rust. Used for authenticating with external services (GitHub, Google, etc.) from within the terminal.

---

## Key Performance Patterns

| Pattern | File | Insight |
|---|---|---|
| API preconnect | `apiPreconnect.ts` | Warm TCP connections at startup |
| Speculative execution | `speculation.ts` | Pre-compute likely next responses |
| Query deduplication | `QueryGuard.ts` | Never fire the same query twice concurrently |
| Circular buffers | `CircularBuffer.ts` | O(1) fixed-size event history |
| Lazy tool loading | `ToolSearchTool` | Only load tool schemas when needed |
| Snapshot over transcript | `agentMemorySnapshot.ts` | Compress agent results before returning |
| Prefetch parallelism | `setup.ts` / `prefetch.py` | All startup I/O runs in parallel |

**These patterns collectively explain why Claude Code is fast despite running an LLM.** The code around the LLM is highly optimized.

---

## Patterns for MindSpark ThoughtForge

| MindSpark Component | Analogous Claude Code Pattern |
|---|---|
| Sovereign RAG | `findRelevantMemories.ts` — semantic memory retrieval |
| TurboQuant | `compact.rs` — model-aware compression |
| Cognition Scaffolds | `SystemPromptBuilder` — named section composition |
| Fragment Salvage | `memoryAge.ts` + `TranscriptStore.compact()` |
| Memory-Enforced Loop | `QueryEngineConfig.max_turns` + turn loop |
| Setup wizard | `setup.ts` startup sequence |
