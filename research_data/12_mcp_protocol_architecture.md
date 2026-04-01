# MCP Protocol Architecture — Model Context Protocol Deep Dive
> Extracted from: rust/crates/runtime/src/mcp.rs, mcp_client.rs, mcp_stdio.rs, config.rs

## What is MCP?

Model Context Protocol (MCP) is Anthropic's open standard for connecting AI models to external tools, data sources, and services. It replaces ad-hoc API integrations with a **standardized protocol** — any MCP server can plug into any MCP client.

**Think of it as:** USB-C for AI tools. One standard, infinite devices.

---

## MCP Wire Protocol (mcp_stdio.rs)

MCP over stdio uses **JSON-RPC 2.0**:

```json
// Request
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "tools/call",
  "params": { "name": "...", "arguments": { ... } }
}

// Response
{
  "jsonrpc": "2.0",
  "id": 1,
  "result": { "content": [...], "isError": false }
}

// Error response
{
  "jsonrpc": "2.0",
  "id": 1,
  "error": { "code": -32601, "message": "Method not found" }
}
```

### MCP Methods (the full protocol surface)
```
initialize          — handshake: exchange capabilities + version
notifications/initialized — client signals it's ready
tools/list          — list available tools (paginated with cursor)
tools/call          — call a tool
resources/list      — list available resources (paginated)
resources/read      — read a resource by URI
```

### Tool Definition
```json
{
  "name": "run_rune_cast",
  "description": "Perform an Elder Futhark rune casting",
  "inputSchema": {
    "type": "object",
    "properties": {
      "spread_type": { "type": "string", "enum": ["single", "three", "nine_worlds"] },
      "question": { "type": "string" }
    },
    "required": ["spread_type"]
  },
  "annotations": { "readOnlyHint": true }
}
```

**`annotations` field** — MCP tools can declare their behavior hints:
- `readOnlyHint: true` — doesn't modify external state
- `destructiveHint: true` — may delete/overwrite data
- `idempotentHint: true` — calling multiple times is safe
- `openWorldHint: true` — interacts with external services

These hints inform the permission system — `readOnlyHint` tools can be auto-approved.

### Resource Definition
```json
{
  "uri": "runes://elder-futhark/fehu",
  "name": "Fehu — Cattle/Wealth rune",
  "description": "Complete lore entry for the Fehu rune",
  "mimeType": "text/markdown"
}
```

**Resources are URI-addressed data sources** — not callable like tools, but readable. A rune lore database exposed as MCP resources would let any MCP client read the full mythology without a tool call overhead.

---

## Transport Types (mcp_client.rs)

```rust
pub enum McpClientTransport {
    Stdio(McpStdioTransport)      // spawn process, communicate via stdin/stdout
    Sse(McpRemoteTransport)       // HTTP Server-Sent Events
    Http(McpRemoteTransport)      // HTTP streamable
    WebSocket(McpRemoteTransport) // WebSocket
    Sdk(McpSdkTransport)          // in-process, no network
    ClaudeAiProxy(...)            // through claude.ai CCR
}
```

### Stdio Transport (most common for local tools)
```rust
pub struct McpStdioTransport {
    command: String,              // e.g. "uvx" or "python3"
    args: Vec<String>,            // e.g. ["mcp_server.py"]
    env: BTreeMap<String, String> // environment variables for the process
}
```

The MCP server is a **child process**. Communication:
- Client → Server: write JSON-RPC to server's stdin
- Server → Client: read JSON-RPC from server's stdout

Newline-delimited JSON: one request/response per line.

**To create an MCP server in Python:**
```python
# mcp_server.py
import sys, json

while True:
    line = sys.stdin.readline()
    if not line:
        break
    request = json.loads(line)

    if request["method"] == "tools/list":
        response = {"jsonrpc": "2.0", "id": request["id"], "result": {
            "tools": [{"name": "my_tool", "description": "...", "inputSchema": {...}}]
        }}
    elif request["method"] == "tools/call":
        result = call_my_tool(request["params"]["arguments"])
        response = {"jsonrpc": "2.0", "id": request["id"], "result": {
            "content": [{"type": "text", "text": result}],
            "isError": False
        }}

    print(json.dumps(response), flush=True)
```

### Remote Transport (HTTP/SSE)
```rust
pub struct McpRemoteTransport {
    url: String,
    headers: BTreeMap<String, String>,
    headers_helper: Option<String>,  // script to generate dynamic headers
    auth: McpClientAuth,             // None or OAuth
}
```

**`headers_helper`** — a shell script that generates auth headers dynamically. This allows MCP servers to use rotating tokens or dynamic credentials without storing secrets in the config file.

---

## MCP Server Initialization Handshake

```
Client → Server: initialize
  {
    "protocolVersion": "2025-03-26",
    "capabilities": { "tools": {}, "resources": {} },
    "clientInfo": { "name": "claude-code", "version": "..." }
  }

Server → Client: result
  {
    "protocolVersion": "2025-03-26",
    "capabilities": { "tools": { "listChanged": true } },
    "serverInfo": { "name": "my-skill", "version": "1.0.0" }
  }

Client → Server: notifications/initialized  (no response expected)

Client → Server: tools/list
Server → Client: [tool definitions]

Client → Server: resources/list
Server → Client: [resource definitions]
```

The client then registers all discovered tools into the tool registry under `mcp__{server_name}__{tool_name}` namespacing.

---

## Tool Name Normalization

```rust
fn normalize_name_for_mcp(name: &str) -> String {
    // Replace non-alphanumeric (except _ and -) with _
    // For claude.ai server names: collapse __ and trim leading/trailing _
}

fn mcp_tool_name(server_name: &str, tool_name: &str) -> String {
    format!("mcp__{}__{}",
        normalize_name_for_mcp(server_name),
        normalize_name_for_mcp(tool_name)
    )
}
```

**Examples:**
- Server: `"rune-casting"`, Tool: `"cast three runes"` → `"mcp__rune-casting__cast_three_runes"`
- Server: `"claude.ai Gmail"`, Tool: `"send"` → `"mcp__claude_ai_Gmail__send"` (special claude.ai handling)

---

## Config Change Detection (Signature Hashing)

```rust
pub fn mcp_server_signature(config: &McpServerConfig) -> Option<String> {
    match config {
        Stdio  → "stdio:[command|args...]"
        Sse    → "url:https://example.com/mcp"
        Http   → "url:https://example.com/mcp"
        Ws     → "url:wss://example.com/mcp"
        Sdk    → None (in-process, no restart needed)
        Proxy  → "url:https://proxy.anthropic.com/..."
    }
}
```

If the signature changes between sessions → MCP server must be restarted. This is how Claude Code detects when you've changed an MCP server config and automatically reconnects.

---

## Config Scopes (settings.json hierarchy)

```rust
pub enum ConfigSource {
    User,     // ~/.claude/settings.json — user-wide
    Project,  // .claude/settings.json — team shared (git-tracked)
    Local,    // .claude/settings.local.json — machine-specific (gitignored)
}
```

**Merge order:** Local overrides Project overrides User.

This means:
- Team shares MCP server configs in `.claude/settings.json`
- Individuals override with machine-specific paths in `.claude/settings.local.json`
- User-global tools go in `~/.claude/settings.json`

**For Viking Girlfriend Skill:** Sigrid as an MCP server goes in the user's `~/.claude/settings.json` so she's available in all projects.

---

## Remote Execution (remote.rs)

### Cloud Claude Runtime (CCR)
```python
CLAUDE_CODE_REMOTE=true       # enable remote mode
CLAUDE_CODE_REMOTE_SESSION_ID=xxx  # session identifier
ANTHROPIC_BASE_URL=https://...    # can point to internal proxy
CCR_SESSION_TOKEN_PATH=/run/ccr/session_token  # token file
CCR_UPSTREAM_PROXY_ENABLED=true
```

CCR is Anthropic's cloud execution environment — Claude Code can run its agent loop in the cloud rather than locally. The CCR proxy allows Claude to make API calls through a managed network with its own token management.

### No-Proxy Hosts (hardcoded)
```
localhost, 127.0.0.1, ::1
169.254.0.0/16 (link-local)
10.0.0.0/8, 172.16.0.0/12, 192.168.0.0/16 (private networks)
anthropic.com, *.anthropic.com
github.com, api.github.com, *.github.com, *.githubusercontent.com
registry.npmjs.org, index.crates.io
```

These bypass any configured upstream proxy — direct connections for Anthropic's own infrastructure and package registries.

### Environment Variables for Proxying
```
HTTPS_PROXY / https_proxy
NO_PROXY / no_proxy
SSL_CERT_FILE
NODE_EXTRA_CA_CERTS
REQUESTS_CA_BUNDLE
CURL_CA_BUNDLE
```

All of these are passed through to child processes — MCP server subprocesses inherit the proxy configuration automatically.

---

## Pagination in MCP

Both `tools/list` and `resources/list` support pagination via cursor:
```json
// Request with cursor
{ "method": "tools/list", "params": { "cursor": "page2token" } }

// Response
{ "result": {
    "tools": [...],
    "nextCursor": "page3token"  // null if last page
}}
```

This means MCP servers can expose **unlimited numbers of tools/resources** — Claude Code fetches them all at startup via cursor iteration.

**Application:** Your rune casting skill can expose all 24 Elder Futhark runes as individual resources plus the spread tools — no pagination needed for a small server, but good to know the protocol supports it.

---

## Building Your MCP Server for OpenClaw/Claude Code

### Minimal Python MCP Server Template
```python
#!/usr/bin/env python3
"""Sigrid Rune Casting MCP Server"""
import sys, json

TOOLS = [
    {
        "name": "single_rune_draw",
        "description": "Draw a single Elder Futhark rune for guidance",
        "inputSchema": {
            "type": "object",
            "properties": {
                "question": {"type": "string", "description": "The question to guide the casting"}
            }
        },
        "annotations": {"readOnlyHint": True}
    },
    # ... more tools
]

def handle_request(req: dict) -> dict:
    method = req["method"]
    req_id = req["id"]

    if method == "initialize":
        return {"jsonrpc": "2.0", "id": req_id, "result": {
            "protocolVersion": "2025-03-26",
            "capabilities": {"tools": {}, "resources": {}},
            "serverInfo": {"name": "sigrid-rune-casting", "version": "1.0.0"}
        }}
    elif method == "notifications/initialized":
        return None  # notification, no response
    elif method == "tools/list":
        return {"jsonrpc": "2.0", "id": req_id, "result": {"tools": TOOLS}}
    elif method == "tools/call":
        tool_name = req["params"]["name"]
        args = req["params"].get("arguments", {})
        result = dispatch_tool(tool_name, args)
        return {"jsonrpc": "2.0", "id": req_id, "result": {
            "content": [{"type": "text", "text": result}],
            "isError": False
        }}

def main():
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        req = json.loads(line)
        resp = handle_request(req)
        if resp is not None:
            print(json.dumps(resp), flush=True)

if __name__ == "__main__":
    main()
```

### settings.json Entry
```json
{
  "mcpServers": {
    "sigrid-rune-casting": {
      "type": "stdio",
      "command": "python3",
      "args": ["/path/to/rune_casting_mcp_server.py"]
    }
  }
}
```

All tools become available as `mcp__sigrid-rune-casting__single_rune_draw` etc.

---

## MCP as Viking Girlfriend Skill Architecture

This is the correct final architecture for Sigrid:

```
User ←→ Claude Code (or OpenClaw)
            ↓ MCP protocol
    Sigrid MCP Server (Python)
    ├── tools/
    │   ├── sigrid_respond        — main conversation turn
    │   ├── orlög_state_get       — get current Ørlög state
    │   ├── cast_rune             — single rune draw
    │   ├── cast_spread           — multi-rune spread
    │   ├── wyrd_read             — relationship thread read
    │   └── set_mode              — change Sigrid's persona mode
    └── resources/
        ├── runes://elder-futhark/*   — all 24 runes as resources
        ├── sigrid://state/orlög      — current full state JSON
        ├── sigrid://memory/recent    — recent session memory
        └── sigrid://wyrd/threads     — current fate threads
```

The model reads resources for lore/state context and calls tools to interact. This is clean, composable, and works with any MCP-compatible client — not just OpenClaw.
