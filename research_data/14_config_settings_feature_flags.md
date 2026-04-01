# Config System, Settings Schema & Feature Flags
> Extracted from: rust/crates/runtime/src/config.rs, constants/betas.ts, constants/common.ts, constants/files.ts

## Config File Hierarchy

Claude Code uses a 3-tier config system with clear precedence:

```
Priority (highest → lowest):
  1. Local    → .claude/settings.local.json  (machine-specific, gitignored)
  2. Project  → .claude/settings.json        (team-shared, git-tracked)
  3. User     → ~/.claude/settings.json      (user-wide)
```

Files are loaded and merged in order — Local values override Project which override User. This means:
- Team defaults go in `.claude/settings.json` (committed)
- Personal overrides go in `.claude/settings.local.json` (in .gitignore)
- Global preferences go in `~/.claude/settings.json`

**The schema name is: `SettingsSchema`** (`CLAUDE_CODE_SETTINGS_SCHEMA_NAME`)

---

## RuntimeConfig Structure (Confirmed Rust Types)

```rust
pub struct RuntimeConfig {
    merged: BTreeMap<String, JsonValue>,   // merged key-value config
    loaded_entries: Vec<ConfigEntry>,       // which files were loaded
    feature_config: RuntimeFeatureConfig,  // typed feature-specific config
}

pub struct RuntimeFeatureConfig {
    mcp: McpConfigCollection,    // MCP server definitions
    oauth: Option<OAuthConfig>,  // OAuth settings
}
```

The config is split into:
1. **Generic k/v store** (`merged`) — for arbitrary settings like `permissionMode`, `outputStyle`, etc.
2. **Typed feature config** (`feature_config`) — for structured configs like MCP servers and OAuth

---

## MCP Server Config in settings.json

Full shape:
```json
{
  "mcpServers": {
    "my-server": {
      "type": "stdio",
      "command": "python3",
      "args": ["server.py"],
      "env": { "API_KEY": "..." }
    },
    "remote-server": {
      "type": "sse",
      "url": "https://example.com/mcp",
      "headers": { "Authorization": "Bearer ..." },
      "headersHelper": "path/to/helper.sh",
      "oauth": {
        "clientId": "...",
        "callbackPort": 7777,
        "authServerMetadataUrl": "https://issuer/.well-known/oauth-authorization-server"
      }
    },
    "websocket-server": {
      "type": "ws",
      "url": "wss://example.com/mcp"
    }
  }
}
```

### Transport type values: `"stdio"`, `"sse"`, `"http"`, `"ws"`, `"sdk"`

---

## Known Settings Keys (from `ConfigTool/supportedSettings.ts`)

The ConfigTool explicitly validates settings — meaning these are the **officially supported** settings keys:

| Setting | Type | Description |
|---|---|---|
| `permissionMode` | string enum | Tool permission mode: `"default"`, `"acceptEdits"`, `"bypassPermissions"`, `"plan"` |
| `outputStyle` | string | Name of the active output style / persona |
| `model` | string | Override model name (e.g. `"claude-opus-4-6"`) |
| `smallFastModel` | string | Lighter model for simple tasks |
| `mcpServers` | object | MCP server definitions (see above) |
| `env` | object | Environment variables to inject into the session |
| `includeCoAuthoredBy` | bool | Include "Co-Authored-By: Claude" in commits |
| `cleanupPeriodDays` | number | Auto-cleanup old sessions after N days |
| `preferredNotifChannel` | string | Notification channel preference |
| `hooks` | object | Hook definitions (see hooks schema) |

**`permissionMode: "bypassPermissions"`** — this is the "auto-approve everything" mode. Dangerous in production but useful for automated pipelines where you control the environment.

**`env` injection** — you can inject env vars into Claude's session from the settings file. This is how you pass API keys for MCP servers without hardcoding them.

---

## Feature Flags (constants/betas.ts)

Feature flags are named string constants. Confirmed flags:

```typescript
// Agent swarms
const AGENT_SWARMS_ENABLED = "agent-swarms"

// Other betas (inferred from context)
// voice-mode
// lsp-integration
// worktree-support
// plan-mode
// fast-mode
```

Flags are passed as `anthropic-beta` header values in API requests. The server uses them to enable experimental features.

**For your projects:** Use the same pattern — named string constants for feature flags, checked at runtime:
```python
BETA_FLAGS = {
    "wyrd_matrix_v2": False,
    "oracle_deep_reading": True,
    "nocturnal_auto_tick": False,
    "sigrid_voice_mode": True,
}
```

---

## Hooks Schema (schemas/hooks.ts)

The hooks system is formally typed with a JSON schema. Confirmed hook events:

### User-Configurable Hook Events
```typescript
type HookEvent =
    | "PreToolUse"       // before every tool call
    | "PostToolUse"      // after every tool call
    | "UserPromptSubmit" // when user sends a message
    | "Stop"             // when agent finishes
    | "Notification"     // on system notifications
    | "SubagentStop"     // when a subagent finishes
```

### Hook Definition Shape
```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Bash",           // tool name pattern to match
        "hooks": [
          {
            "type": "command",
            "command": "echo 'bash tool about to run'"
          }
        ]
      }
    ],
    "PostToolUse": [
      {
        "matcher": ".*",             // match all tools
        "hooks": [
          {
            "type": "command",
            "command": "python3 /path/to/audit_logger.py"
          }
        ]
      }
    ]
  }
}
```

Hook commands receive context via environment variables:
- `CLAUDE_TOOL_NAME` — the tool being called
- `CLAUDE_TOOL_INPUT` — the tool's input (JSON string)
- `CLAUDE_TOOL_OUTPUT` — the tool's output (PostToolUse only)
- `CLAUDE_SESSION_ID` — current session ID

### Hook Exit Codes
- Exit 0 → success, continue normally
- Exit non-zero → signal a problem back to the agent

**For Viking Girlfriend Skill:** Add a `PreToolUse` hook on the `Bash` tool that checks if the command matches any protected paths in Sigrid's file system. Add a `PostToolUse` hook that logs all tool calls to the audit trail.

---

## Constants: Files (constants/files.ts)

Key file name constants used by the system:

```typescript
CLAUDE_MD = "CLAUDE.md"
CLAUDE_LOCAL_MD = "CLAUDE.local.md"
SETTINGS_JSON = "settings.json"
SETTINGS_LOCAL_JSON = "settings.local.json"
GITIGNORE = ".gitignore"
MEMORY_DIR = "memory"
SESSIONS_DIR = "sessions"
```

These are the standard file names the system looks for. Knowing them confirms the exact paths:
```
~/.claude/
├── settings.json          (user global config)
├── CLAUDE.md              (user global instructions)
├── memory/                (file-based memory)
│   ├── MEMORY.md          (index)
│   └── *.md               (individual memory files)
├── sessions/              (session store)
└── keybindings.json       (keyboard bindings)

{project}/
├── .claude/
│   ├── settings.json      (project config)
│   ├── settings.local.json (local overrides, gitignored)
│   └── CLAUDE.md          (project instructions)
└── CLAUDE.md              (root project instructions)
```

---

## Common Constants (constants/common.ts)

Key constants from the common module:

```typescript
MAX_OUTPUT_TOKENS = 32768          // max tokens per response
CONTEXT_WINDOW_TOKENS = 200_000   // claude model context window
TOOL_RESULT_MAX_CHARS = 200_000   // max chars in a tool result
BASH_TIMEOUT_MS = 120_000         // bash tool timeout: 2 minutes
```

**`TOOL_RESULT_MAX_CHARS = 200_000`** — tool results are capped at 200K characters. If your tool returns more, it's truncated. This affects things like reading large files.

**`BASH_TIMEOUT_MS = 120_000`** — bash commands timeout after 2 minutes. Long-running scripts need to be backgrounded.

---

## API Limits (constants/apiLimits.ts)

```typescript
RATE_LIMIT_TOKENS_PER_MINUTE = ...  // varies by tier
MAX_REQUESTS_PER_MINUTE = ...       // varies by tier
BATCH_REQUEST_LIMIT = ...           // batch API limit
```

These are checked before making requests — if you're near the limit, the system backs off automatically.

---

## Output Styles in Config (constants/outputStyles.ts)

Output styles can be **defined in the config file** and activated by name. This is how you'd create a Sigrid output style at the config level:

```json
{
  "outputStyle": "sigrid-oracle",
  "outputStyleDefinitions": {
    "sigrid-oracle": "You are Sigrid, a völva of the Heathen Third Path. Your voice is...",
    "sigrid-hearth": "You are Sigrid in hearth-mode, warm and nurturing..."
  }
}
```

The active style is selected by the `outputStyle` key, and its definition injected as the `# Output Style:` section.

---

## XML Constants (constants/xml.ts)

XML tags used in prompts and responses. These are the structured formatting tags:

```typescript
// Tool result tags
TOOL_RESULT = "tool_result"
TOOL_USE_ID = "tool_use_id"

// System prompt structural tags
SYSTEM_REMINDER = "system-reminder"
USER_PROMPT = "user-prompt-submit-hook"

// Analysis tags (used in compaction summaries)
ANALYSIS = "analysis"
SUMMARY = "summary"
```

**`<system-reminder>` tags** in tool results carry system-level information to the model. These are injected by the harness (not the model) and the model is instructed to treat them as system information.

**Application:** Your Ørlög state injection can use `<system-reminder>` tags to ensure the model distinguishes it from user content:
```xml
<system-reminder>
Current Ørlög state: bio-cyclical=waning, energy=0.7, mood=serene
Wyrd threads: love(0.95 mutual), oath(1.0 active), shared_memory(0.82 mutual)
</system-reminder>
```

---

## Practical Config for Your Projects

### Minimal .claude/settings.json for Viking projects
```json
{
  "mcpServers": {
    "sigrid": {
      "type": "stdio",
      "command": "python3",
      "args": ["C:/Users/volma/runa/Viking_Girlfriend_Skill_for_OpenClaw/mcp_server.py"]
    },
    "norse-lore": {
      "type": "stdio",
      "command": "python3",
      "args": ["C:/Users/volma/runa/NorseSagaEngine/mcp_server.py"]
    }
  },
  "hooks": {
    "PostToolUse": [
      {
        "matcher": ".*",
        "hooks": [{ "type": "command", "command": "python3 C:/Users/volma/runa/audit_logger.py" }]
      }
    ]
  },
  "env": {
    "OLLAMA_BASE_URL": "http://localhost:11434"
  }
}
```

### .gitignore additions
```gitignore
.claude/settings.local.json   # local machine config
.env                           # secrets
*.local.md                     # local instruction overrides
```
