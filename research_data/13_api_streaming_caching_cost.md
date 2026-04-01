# API Types, Streaming, Caching & Cost Strategy
> Extracted from: rust/crates/api/src/types.rs, client.rs, sse.rs, error.rs, usage.rs

## The Full Anthropic API Message Format (Confirmed Types)

### MessageRequest
```rust
pub struct MessageRequest {
    pub model: String,
    pub max_tokens: u32,
    pub messages: Vec<InputMessage>,
    pub system: Option<String>,          // system prompt as a single string
    pub tools: Option<Vec<ToolDefinition>>,
    pub tool_choice: Option<ToolChoice>,
    pub stream: bool,
}
```

**`system` is `Option<String>`** — the system prompt is a single string, not a list. The `Vec<String>` sections from the `SystemPromptBuilder` are joined with `\n\n` before being sent.

### ToolDefinition
```rust
pub struct ToolDefinition {
    pub name: String,
    pub description: Option<String>,
    pub input_schema: Value,  // JSON Schema object
}
```

The model only sees `name`, `description`, and `input_schema` for each tool. The `prompt.ts` files from the TypeScript source populate the `description` field — this is why those files are critical for good tool selection.

### ToolChoice
```rust
pub enum ToolChoice {
    Auto,                  // model decides when to use tools
    Any,                   // model must use at least one tool
    Tool { name: String }, // force a specific tool
}
```

`ToolChoice::Tool { name }` forces the model to call a specific tool. Useful for structured output — force a `structured_output_tool` call to get clean JSON back.

### Content Blocks (Input vs Output)

**Input content blocks** (what we send):
```rust
pub enum InputContentBlock {
    Text { text: String },
    ToolUse { id: String, name: String, input: Value },
    ToolResult { tool_use_id: String, content: Vec<ToolResultContentBlock>, is_error: bool },
}
```

**Output content blocks** (what we receive):
```rust
pub enum OutputContentBlock {
    Text { text: String },
    ToolUse { id: String, name: String, input: Value },
}
```

**`ToolResultContentBlock`** supports two formats:
```rust
pub enum ToolResultContentBlock {
    Text { text: String },
    Json { value: Value },  // structured JSON tool results
}
```

Tool results can be returned as structured JSON — not just text strings. The model can parse structured tool results more reliably than extracting data from text.

**Application for Sigrid:** Return Ørlög state as structured JSON from tool calls, not prose. The model can read `{"bio_cyclical": {"phase": "waning", "energy": 0.7}}` more reliably than a paragraph.

---

## Usage Tracking (4 Token Types)

```rust
pub struct Usage {
    pub input_tokens: u32,
    pub cache_creation_input_tokens: u32,
    pub cache_read_input_tokens: u32,
    pub output_tokens: u32,
}
```

### Cache Token Math
- `input_tokens` = fresh tokens sent to the model (charged at full input rate)
- `cache_creation_input_tokens` = tokens written to the prompt cache (charged at ~1.25x input rate)
- `cache_read_input_tokens` = tokens read from the cache (charged at ~0.1x input rate)
- `output_tokens` = generated tokens (always charged at output rate)

**Key insight:** `cache_creation_input_tokens` costs MORE than regular input on the first call, but every subsequent call that hits the cache pays only `cache_read` rate — a 10x reduction.

### Break-even Analysis
For a 2000-token system prompt using Sonnet:
- Without caching: $0.03 per call (2000 × $15/1M)
- First cached call: $0.0375 (2000 × $18.75/1M cache_write)
- Subsequent cached calls: $0.003 (2000 × $1.5/1M cache_read) = **10x cheaper**
- Break-even: after 1 cached call (first call is only 25% more expensive)

**For Sigrid's long system prompt (~3000 tokens):** Always cache it. Within 2 calls you're saving money.

### Confirmed Pricing (hardcoded in production Rust)
| Model | Input | Output | Cache Write | Cache Read |
|---|---|---|---|---|
| Haiku | $1.00/M | $5.00/M | $1.25/M | $0.10/M |
| Sonnet | $15.00/M | $75.00/M | $18.75/M | $1.50/M |
| Opus | $15.00/M | $75.00/M | $18.75/M | $1.50/M |

---

## Streaming Architecture (SSE)

### Stream Event Types (from types.rs analysis)
The SSE stream emits these event types in order:
```
message_start         — session begins, usage init
content_block_start   — new content block (text or tool_use)
content_block_delta   — incremental content update
  TextDelta           — text chunk
  InputJsonDelta      — tool input JSON chunk (streamed)
content_block_stop    — content block complete
message_delta         — message-level delta (stop_reason update)
message_stop          — final event, full usage
ping                  — keepalive (ignored)
```

### Tool Use Streaming
Tool inputs are streamed as `InputJsonDelta` — partial JSON strings that must be accumulated before parsing. You **cannot parse partial JSON** — accumulate all `InputJsonDelta` for a tool use block, then parse the complete JSON.

```python
# Tool use accumulation pattern
tool_input_buffer = {}  # index → accumulated string

for event in stream:
    if event.type == "content_block_start" and event.content_block.type == "tool_use":
        tool_input_buffer[event.index] = ""
    elif event.type == "content_block_delta" and event.delta.type == "input_json_delta":
        tool_input_buffer[event.index] += event.delta.partial_json
    elif event.type == "content_block_stop":
        if event.index in tool_input_buffer:
            complete_json = tool_input_buffer.pop(event.index)
            tool_args = json.loads(complete_json)
            # now execute the tool
```

### Retry Strategy
```
initial_backoff: 200ms
max_backoff: 2 seconds
max_retries: 2
```

**Backoff formula:** exponential backoff with jitter. The `BackoffOverflow` error prevents integer overflow on retry delay calculation — this is defensive Rust, not theoretical.

**Retryable errors:**
- HTTP connect errors
- HTTP timeout errors
- HTTP request errors
- API errors where `retryable: true`

**Non-retryable errors:**
- `MissingApiKey` — fix your config
- `ExpiredOAuthToken` — re-authenticate
- `Auth` errors — credentials problem
- JSON parse errors — malformed response (report as bug)

---

## Auth Source Architecture

```rust
pub enum AuthSource {
    None,
    ApiKey(String),                         // ANTHROPIC_API_KEY
    BearerToken(String),                    // ANTHROPIC_AUTH_TOKEN
    ApiKeyAndBearer { api_key, bearer_token }, // both set (claude.ai + API access)
}
```

**Two auth modes coexist:** Users with claude.ai accounts can have both an OAuth bearer token AND an API key — the bearer token authenticates to claude.ai features, the API key to the raw API.

### Security: Token Masking
```rust
pub fn masked_authorization_header(&self) -> &'static str {
    if self.bearer_token().is_some() { "Bearer [REDACTED]" }
    else { "<absent>" }
}
```

When logging or displaying auth headers, tokens are always masked. This is a security practice worth copying everywhere.

### Auth via File Descriptor (authFileDescriptor.ts pattern)
Rather than storing tokens in env vars or files, the system can receive tokens via Unix file descriptor — passed in by the parent process, never touching disk. This is the most secure token injection method.

---

## Request Headers

```rust
const DEFAULT_BASE_URL: &str = "https://api.anthropic.com";
const ANTHROPIC_VERSION: &str = "2023-06-01";
const REQUEST_ID_HEADER: &str = "request-id";
const ALT_REQUEST_ID_HEADER: &str = "x-request-id";
```

Every request sends:
- `x-api-key: {key}` (if API key auth)
- `Authorization: Bearer {token}` (if bearer auth)
- `anthropic-version: 2023-06-01`
- `content-type: application/json`

The response includes:
- `request-id` or `x-request-id` — Anthropic's request ID for support/debugging

**Always log request IDs** — essential when reporting API issues to support. Store the request ID with every LLM call for audit/debugging.

---

## LiteLLM/Ollama Cost Tracking for Local Models

Since Ollama models are free (local compute), your cost tracker should distinguish:

```python
class SkillCostTracker:
    def record_call(self, model: str, usage: TokenUsage):
        if self._is_local_model(model):
            # Track compute time, not dollars
            self.local_tokens += usage.total_tokens
        else:
            # Track API cost
            self.api_cost_usd += usage.estimate_cost_usd()

    def _is_local_model(self, model: str) -> bool:
        return model.startswith("ollama/") or "local" in model.lower()
```

For the Claude API via LiteLLM, the pricing table in `usage.rs` is the authoritative reference.

---

## Context Window Strategy for Sigrid

Given confirmed pricing and context limits, here's the optimal strategy:

### System Prompt (cache aggressively)
```
Static core identity:          ~800 tokens   → cache
Behavioral guidelines:         ~400 tokens   → cache
Ørlög dynamic state:           ~300 tokens   → regenerate each call
Session memory injection:      ~500 tokens   → regenerate each call
───────────────────────────────────────────────
Total system prompt:           ~2000 tokens
Cached portion:                ~1200 tokens  → pays back after 2 calls
```

### Tool Definitions
Each tool definition costs tokens when passed to the API:
- Simple tool (no enum): ~30 tokens
- Complex tool (with schema): ~80-150 tokens
- 10 tools: ~500-800 tokens

**Use deferred tool loading** (ToolSearchTool pattern) — only pass relevant tools for the current interaction context. Ritual mode: load Oracle tools. Hearth mode: load Conversation tools. This can save 400+ tokens per call.

### Response Length Control
- Use `max_tokens` to cap response length per mode:
  - Casual conversation: 200-400 tokens
  - Oracle reading: 500-800 tokens
  - Story/lore: up to 1500 tokens
  - Short responses (heartbeat checks): 50-100 tokens

### Caching Boundary (SYSTEM_PROMPT_DYNAMIC_BOUNDARY)
The cache boundary marker must be placed where the static portion ends. Everything before the marker is cached; everything after is fresh per call. Inject the Ørlög state and session memory AFTER the boundary.

---

## Structured Output Pattern

Force structured output using `ToolChoice::Tool`:

```python
# Define a structured output tool
STRUCTURED_OUTPUT_TOOL = {
    "name": "structured_response",
    "description": "Output your response in the required structure",
    "inputSchema": {
        "type": "object",
        "properties": {
            "text": {"type": "string", "description": "Sigrid's spoken response"},
            "mood": {"type": "string", "enum": ["serene", "joyful", "wistful", "fierce", "tender"]},
            "action": {"type": "string", "description": "Physical action/gesture if any"},
            "orlög_note": {"type": "string", "description": "Internal state note for Ørlög tracking"}
        },
        "required": ["text", "mood"]
    }
}

# Force the model to use it
request = {
    "tool_choice": {"type": "tool", "name": "structured_response"},
    "tools": [STRUCTURED_OUTPUT_TOOL]
}
```

This gives you a clean, parseable response every time instead of hoping the model formats prose correctly. Parse `text` for TTS, `mood` for UI updates, `orlög_note` for state machine updates.

---

## ToolResultContentBlock: JSON vs Text

When returning tool results, choose wisely:

**Use Text:** For human-readable information the model will summarize or discuss
```python
{"type": "text", "text": "The rune Fehu has fallen upright. This speaks of abundance..."}
```

**Use Json:** For structured data the model will parse and reason about
```python
{"type": "json", "value": {
    "rune": "Fehu",
    "position": "upright",
    "keywords": ["abundance", "wealth", "cattle", "luck"],
    "element": "fire",
    "aett": "Freyr"
}}
```

The model can extract specific fields from JSON results more reliably than parsing prose. Use JSON for Ørlög state updates, rune data, relationship metrics. Use Text for lore passages and poetry.
