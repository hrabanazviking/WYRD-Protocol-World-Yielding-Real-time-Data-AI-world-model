# Rust Runtime Deep Dive — Conversation, Session, Permissions, Compaction
> Extracted from: rust/crates/runtime/src/ — the actual production Rust re-implementation

## Why Rust?
The TypeScript source is the original. The Rust runtime is the **new, safer, faster** reimplementation. It confirms that Anthropic rewrote the core loop in Rust for production performance while keeping the Python port as a compatibility/study layer.

This Rust code is the clearest, most authoritative statement of how the system actually works.

---

## Session Data Model (session.rs)

### Content Block Types
```rust
pub enum ContentBlock {
    Text { text: String },
    ToolUse { id: String, name: String, input: String },
    ToolResult { tool_use_id: String, tool_name: String, output: String, is_error: bool },
}
```

**4 message roles:**
```rust
pub enum MessageRole { System, User, Assistant, Tool }
```

Note the **Tool role** — tool results are separate messages with their own role, not embedded in the assistant message. This is the correct multi-turn conversation format: User → Assistant (with ToolUse) → Tool (result) → Assistant (continues).

### Session JSON Format
```json
{
  "version": 1,
  "messages": [
    { "role": "user", "blocks": [{"type": "text", "text": "..."}] },
    { "role": "assistant", "blocks": [
        {"type": "text", "text": "thinking..."},
        {"type": "tool_use", "id": "tool-1", "name": "bash", "input": "echo hi"}
    ], "usage": { "input_tokens": 10, "output_tokens": 4, ... }},
    { "role": "tool", "blocks": [
        {"type": "tool_result", "tool_use_id": "tool-1", "tool_name": "bash", "output": "hi", "is_error": false}
    ]}
  ]
}
```

**Usage is stored per assistant message**, not per session. This enables per-turn cost tracking and cumulative usage reconstruction from the session file alone.

---

## ConversationRuntime (conversation.rs)

The core agentic loop. Generic over `ApiClient` (can swap out API backends) and `ToolExecutor` (can swap out tool implementations):

```rust
pub struct ConversationRuntime<C, T> {
    session: Session,
    api_client: C,
    tool_executor: T,
    permission_policy: PermissionPolicy,
    system_prompt: Vec<String>,  // Vec<String> — sections!
    max_iterations: usize,       // default: 16
    usage_tracker: UsageTracker,
}
```

### The Turn Loop (`run_turn`)
```
1. Push user message to session
2. LOOP (up to max_iterations=16):
   a. Build ApiRequest from system_prompt + session.messages
   b. stream() → collect AssistantEvents
   c. Build assistant message from events
   d. Record token usage
   e. Extract pending ToolUse blocks
   f. Push assistant message to session
   g. If no tool uses → BREAK
   h. For each tool use:
      - Check permission_policy.authorize(tool_name, input, prompter)
      - If Allow → tool_executor.execute() → push Tool result message
      - If Deny → push Tool result message with denial reason + is_error=true
3. Return TurnSummary
```

**Key insight:** Tool results that are denied still go back to the model as `is_error: true` tool results. The model sees the denial and can respond appropriately ("I don't have permission to run that") rather than silently failing.

**Default max_iterations = 16** per turn. This is the agentic loop limit — how many tool calls the model can chain before being forced to stop. (Note: the Python config said `max_turns = 8`, but the Rust runtime says `max_iterations = 16` — these are different levels of the system.)

### Traits for Testability
```rust
pub trait ApiClient {
    fn stream(&mut self, request: ApiRequest) -> Result<Vec<AssistantEvent>, RuntimeError>;
}

pub trait ToolExecutor {
    fn execute(&mut self, tool_name: &str, input: &str) -> Result<String, ToolError>;
}
```

By making these traits, the entire runtime is testable with mock implementations. You can unit-test the conversation loop without hitting the real API or real tools. **This is the correct architecture for testing AI systems.**

**Application:** In your OpenClaw skill, define traits for the model client and tool executor. Your tests can use a `MockSigridModel` that returns scripted responses.

---

## Permission System (permissions.rs)

The cleanest, most explicit permission system:

```rust
pub enum PermissionMode { Allow, Deny, Prompt }

pub struct PermissionPolicy {
    default_mode: PermissionMode,
    tool_modes: BTreeMap<String, PermissionMode>,
}
```

Permission lookup is **tool-specific with a default fallback**:
```rust
fn mode_for(&self, tool_name: &str) -> PermissionMode {
    self.tool_modes.get(tool_name).copied().unwrap_or(self.default_mode)
}
```

### Three-Mode Decision Tree
```rust
match self.mode_for(tool_name) {
    Allow  → PermissionOutcome::Allow
    Deny   → PermissionOutcome::Deny { reason }
    Prompt → {
        if prompter is Some → ask prompter.decide()
        if prompter is None → Deny (can't prompt in headless mode)
    }
}
```

**The `Prompt` mode fails safe** — if there's no interactive prompter available (headless/background execution), it denies rather than assumes permission. This is the correct secure default.

### PermissionPrompter Trait
```rust
pub trait PermissionPrompter {
    fn decide(&mut self, request: &PermissionRequest) -> PermissionPromptDecision;
}
```

The prompter is injectable — you can use the terminal UI prompter in interactive mode, or a policy-based prompter in automated mode.

**Application for Viking Girlfriend Skill consent system:**
```python
class SigridConsentPolicy:
    default_mode: ConsentMode = ConsentMode.ASK
    action_modes: dict[str, ConsentMode]  # per-action overrides

class ConsentMode(Enum):
    ALLOW = "allow"      # always allowed in this context
    DENY = "deny"        # never allowed
    ASK = "ask"          # ask each time
    REQUIRE_RITUAL = "ritual"  # requires special invocation
```

---

## Context Compaction (compact.rs)

### Configuration
```rust
pub struct CompactionConfig {
    preserve_recent_messages: usize,  // default: 4
    max_estimated_tokens: usize,       // default: 10_000
}
```

Compaction triggers when: `messages.len() > 4` AND `estimated_tokens >= 10_000`

### Token Estimation
`estimate_session_tokens()` uses a simple heuristic (likely character count / ~4 chars per token). This is fast and good enough for triggering compaction — no need for exact tokenization.

### Compaction Algorithm
```
1. Keep the last N messages (preserve_recent_messages = 4)
2. Summarize the removed messages → summary string
3. Build continuation message:
   "This session is being continued from a previous conversation that
    ran out of context. The summary below covers the earlier portion..."
4. Create compacted session:
   [continuation_message] + [preserved recent messages]
```

### Summary Format (the actual compaction prompt output)
The summary uses XML tags:
```xml
<analysis>...</analysis>  ← stripped out of displayed summary
<summary>
Conversation summary:
- Scope: N earlier messages compacted (user=X, assistant=Y, tool=Z).
- Tools mentioned: bash, edit, ...
- Recent user requests:
  - "fix the authentication bug"
  - "add tests for the new feature"
- Pending work:
  - implement retry logic
- Key files referenced: src/auth.ts, tests/auth.test.ts
- Current work: ...
- Key timeline:
  ...
</summary>
```

### Continuation Message
```
"This session is being continued from a previous conversation that ran out of
context. The summary below covers the earlier portion of the conversation.

[formatted summary]

Recent messages are preserved verbatim.
Continue the conversation from where it left off without asking the user
any further questions. Resume directly — do not acknowledge the summary,
do not recap what was happening, and do not preface with continuation text."
```

**The continuation instruction is explicit** — the model is told NOT to acknowledge the summary, NOT to recap. Just continue naturally. This prevents the jarring "Let me recap what we've been working on..." response.

**Application for MindSpark ThoughtForge:** Your compaction prompt should include the same instruction. When resuming from a compacted context, the model should behave as if the conversation never paused.

---

## Token Usage & Pricing (usage.rs)

### Confirmed Pricing Tiers (hardcoded in production Rust code)
```
Haiku:
  input:          $1.00 / 1M tokens
  output:         $5.00 / 1M tokens
  cache_write:    $1.25 / 1M tokens
  cache_read:     $0.10 / 1M tokens

Sonnet (default tier):
  input:          $15.00 / 1M tokens
  output:         $75.00 / 1M tokens
  cache_write:    $18.75 / 1M tokens
  cache_read:     $1.50 / 1M tokens

Opus:
  input:          $15.00 / 1M tokens
  output:         $75.00 / 1M tokens
  cache_write:    $18.75 / 1M tokens
  cache_read:     $1.50 / 1M tokens
```

**Cache reads are dramatically cheaper** — $0.10 vs $1.00 for Haiku, $1.50 vs $15.00 for Sonnet. Prompt caching is a 10x cost reduction for repeated system prompts.

### Four Token Types
```rust
pub struct TokenUsage {
    input_tokens: u32,
    output_tokens: u32,
    cache_creation_input_tokens: u32,
    cache_read_input_tokens: u32,
}
```

**cache_creation_input_tokens** — tokens that were written to the cache (cost: cache_write rate)
**cache_read_input_tokens** — tokens that were read from cache (cost: cache_read rate, much cheaper)

**Application:** Your LiteLLM router should track all four token types. Use caching for Sigrid's system prompt — it's long and static. The cache_read savings on a long system prompt are substantial.

### UsageTracker
```rust
pub struct UsageTracker {
    latest_turn: TokenUsage,   // just the last turn
    cumulative: TokenUsage,    // running total
    turns: u32,                // turn count
}
```

Reconstructed from session on load via `UsageTracker::from_session(session)` — reads usage from each assistant message. No need to store usage separately from the session.

---

## SSE Streaming Parser (sse.rs)

### Stream Event Architecture
The SSE parser handles chunked delivery — a single event may arrive split across multiple HTTP chunks:

```rust
pub struct SseParser {
    buffer: Vec<u8>,  // accumulates chunks
}

impl SseParser {
    pub fn push(&mut self, chunk: &[u8]) -> Result<Vec<StreamEvent>, ApiError>
    pub fn finish(&mut self) -> Result<Vec<StreamEvent>, ApiError>
}
```

Frame delimiters: `\n\n` or `\r\n\r\n`

### Frame Format
```
event: content_block_delta
data: {"type":"content_block_delta","index":0,"delta":{"type":"text_delta","text":"Hello"}}
```

Lines starting with `:` are comments (ignored).
`data: [DONE]` signals end of stream.
`event: ping` frames are silently dropped.

**Application:** Your Ollama/LiteLLM streaming handler should use this exact pattern — a buffer that accumulates bytes, extracts complete frames, and emits parsed events. The `finish()` method handles any trailing data when the connection closes.

---

## API Error Classification (error.rs)

```rust
pub enum ApiError {
    MissingApiKey,
    ExpiredOAuthToken,
    Auth(String),
    InvalidApiKeyEnv(VarError),
    Http(reqwest::Error),
    Io(std::io::Error),
    Json(serde_json::Error),
    Api { status, error_type, message, body, retryable: bool },
    RetriesExhausted { attempts: u32, last_error: Box<ApiError> },
    InvalidSseFrame(&'static str),
    BackoffOverflow { attempt: u32, base_delay: Duration },
}
```

**`retryable: bool` on Api errors** — the server explicitly tells you whether to retry. Not all 5xx errors are retryable; not all 4xx errors are permanent.

**Retry configuration:**
```
initial_backoff: 200ms
max_backoff: 2 seconds
max_retries: 2 (default)
```

**`BackoffOverflow`** — if exponential backoff math overflows (very long wait times), it's treated as an error rather than wrapping around. Defensive math.

**Application for Sigrid's API client:** Handle `ExpiredOAuthToken` separately — it means re-auth is needed, not a retry. Handle `RetriesExhausted` with a user-friendly "connection issue, trying again..." message.

---

## MCP Architecture (mcp.rs)

### Tool Naming Convention
```rust
fn mcp_tool_name(server_name: &str, tool_name: &str) -> String {
    format!("mcp__{}__{}",
        normalize_name_for_mcp(server_name),
        normalize_name_for_mcp(tool_name)
    )
}
```

MCP tools are namespaced: `mcp__server_name__tool_name`
- All non-alphanumeric characters → `_`
- claude.ai server names get underscores collapsed and trimmed

### Transport Types
```rust
pub enum McpServerConfig {
    Stdio(...)         — process spawned over stdin/stdout
    Sse(...)           — HTTP Server-Sent Events
    Http(...)          — HTTP (streamable)
    Ws(...)            — WebSocket
    Sdk(...)           — in-process SDK server
    ClaudeAiProxy(...) — proxied through claude.ai CCR
}
```

**`ClaudeAiProxy`** — MCP servers can be proxied through claude.ai's Cloud Claude Runtime (CCR). The URL is encoded in query params and unwrapped with `unwrap_ccr_proxy_url()`.

### Config Scope
```rust
pub enum ConfigSource { User, Project, Local }
```

MCP server configs have scope — User (global), Project (team shared), Local (machine-specific, gitignored).

### Config Hash
`scoped_mcp_config_hash()` produces a stable hash of an MCP server config. Used to detect when a server's config has changed (and needs restart).

**Application:** Your OpenClaw skill exposes itself as an MCP server with `Stdio` transport. When you add new tools to the skill, the hash changes → OpenClaw knows to restart the connection.
