# Claude Code Architecture Overview
> Research from claw-code leak analysis. Not copy-pasted code — extracted architectural patterns for learning.

## Repository Structure

The original TypeScript source (1902 files) was compiled into a Python port mirror + a Rust runtime harness.

### Language Layers
| Layer | Language | Role |
|---|---|---|
| Original source | TypeScript (React/Ink) | Full CLI UI + agent logic |
| Ported mirror | Python | Architecture study / parity testing |
| New runtime harness | Rust | Fast, safe re-implementation of core runtime |

---

## Top-Level Modules (root TypeScript files)
```
QueryEngine.ts    — turn-loop brain: prompt → tool dispatch → output
Task.ts           — single-task execution unit
Tool.ts           — base tool interface
commands.ts       — slash-command registry
context.ts        — workspace context assembly
cost-tracker.ts   — token budget tracking
costHook.ts       — hook into cost events
dialogLaunchers.tsx — interactive dialog flows
history.ts        — session history log
ink.ts            — terminal UI (Ink/React)
interactiveHelpers.tsx — REPL interaction utilities
main.tsx          — entrypoint
projectOnboardingState.ts — first-run state machine
query.ts          — prompt routing helpers
replLauncher.tsx  — REPL mode launcher
setup.ts          — workspace setup (trusted/untrusted)
tasks.ts          — task list management
tools.ts          — tool registry
```

---

## Subsystems (35 top-level directories)

| Subsystem | Module Count | Key Purpose |
|---|---|---|
| `utils` | 564 | Enormous shared utilities library |
| `services` | 130 | API clients, analytics, memory, AI features |
| `hooks` | 104 | React hooks: UI state, notifications, permissions |
| `commands` | 207 entries | All slash commands |
| `tools` | 184 entries | All callable tools |
| `components` | — | UI components (Ink/React) |
| `screens` | 3 | Doctor, REPL, ResumeConversation |
| `assistant` | 1 | sessionHistory.ts |
| `bootstrap` | 1 | state.ts — initial app state |
| `buddy` | 6 | **AI Companion system** (see doc 07) |
| `coordinator` | 1 | coordinatorMode.ts — multi-agent coordinator |
| `memdir` | 8 | **File-based memory system** |
| `skills` | 20 | Bundled skill definitions |
| `state` | 6 | AppState, store, selectors |
| `types` | 11 | Shared type definitions |
| `schemas` | 1 | hooks.ts schema |
| `migrations` | — | Config/data migrations |
| `plugins` | — | Plugin system |
| `keybindings` | — | Keyboard binding system |
| `outputStyles` | — | Output style/persona system |
| `voice` | 1 | voiceModeEnabled.ts |
| `vim` | — | Vim mode support |
| `remote` | — | Remote agent infrastructure |
| `upstreamproxy` | — | Proxy support |
| `native-ts` | — | Native TypeScript bridges |
| `ink` | — | Ink terminal rendering |
| `entrypoints` | — | Multiple CLI entry points |
| `moreright` | — | Extended right-panel UI |
| `bridge` | — | IPC bridge layer |
| `server` | — | Local HTTP server |
| `query` | — | Query processing subsystem |
| `tasks` | — | Task scheduling subsystem |
| `context` | — | Context management |
| `constants` | 21 | All constant definitions |

---

## Boot Sequence (Startup Steps)
From `setup.py` / `WorkspaceSetup.startup_steps()`:

1. **Start top-level prefetch side effects** — MDM raw read, keychain prefetch, project scan (all parallel)
2. **Build workspace context** — discover cwd, count files, check git status
3. **Load mirrored command snapshot** — 207 commands from JSON snapshot
4. **Load mirrored tool snapshot** — 184 tools from JSON snapshot
5. **Prepare parity audit hooks** — cross-check Python port against TypeScript archive
6. **Apply trust-gated deferred init** — if trusted: plugin_init, skill_init, mcp_prefetch, session_hooks

### Trust Model
- `trusted=True` enables: plugins, skills, MCP prefetch, session hooks
- `trusted=False` runs in sandboxed read-only mode
- Permission denials are tracked per-session and passed to the query engine

---

## QueryEngine Turn Loop (`QueryEngineConfig`)
```python
max_turns: int = 8
max_budget_tokens: int = 2000
compact_after_turns: int = 12
structured_output: bool = False
structured_retry_limit: int = 2
```

**Turn flow:**
1. Route prompt → score against command + tool name tokens
2. Infer permission denials (destructive tools gated)
3. Execute matched commands
4. Execute matched tools
5. Stream events: message_start → command_match → tool_match → permission_denial → message_delta → message_stop
6. Compact message history if > compact_after_turns
7. Persist session (TranscriptStore flush → save_session)

**Stop reasons:** `completed`, `max_turns_reached`, `max_budget_reached`

---

## Routing Algorithm (`PortRuntime.route_prompt`)
Simple but effective token scoring:
```python
tokens = {token.lower() for token in prompt.replace('/', ' ').replace('-', ' ').split()}
# Score each tool/command by token overlap with: name + source_hint + responsibility
# Return top 5, balanced: at least 1 command + 1 tool if available
```
**Pattern idea for Viking Girlfriend Skill:** Use similar token-weighted routing to dispatch to different Ørlög state machine branches based on user input analysis.

---

## Session Persistence
- Sessions stored with: `session_id`, `messages[]`, `input_tokens`, `output_tokens`
- TranscriptStore separates mutable working messages from persisted transcript
- `.flush()` marks transcript as clean before persistence
- `.compact(keep_last=N)` trims oldest entries to manage context size

---

## Key Architectural Insight
The system is **not monolithic** — it's a collection of small, single-responsibility modules wired together at runtime. The 1902 TypeScript files average ~50-100 lines each. Each tool, command, service, and hook is its own file. This is worth emulating in your OpenClaw skill architecture.
