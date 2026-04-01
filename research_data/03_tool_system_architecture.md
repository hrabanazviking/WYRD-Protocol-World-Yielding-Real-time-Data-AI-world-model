# Tool System Architecture — Claude Code Patterns
> Extracted from tools_snapshot.json (184 tools) and tool source structure analysis.

## Complete Tool Inventory

### AgentTool (Multi-Agent Spawning)
```
tools/AgentTool/AgentTool.tsx          — main tool implementation
tools/AgentTool/UI.tsx                 — Ink UI rendering
tools/AgentTool/agentColorManager.ts   — per-agent color assignment
tools/AgentTool/agentDisplay.ts        — output display logic
tools/AgentTool/agentMemory.ts         — agent-scoped memory
tools/AgentTool/agentMemorySnapshot.ts — memory snapshotting
tools/AgentTool/agentToolUtils.ts      — shared agent utilities
tools/AgentTool/builtInAgents.ts       — agent type registry
tools/AgentTool/constants.ts
tools/AgentTool/forkSubagent.ts        — subagent forking
tools/AgentTool/loadAgentsDir.ts       — load custom agent definitions
tools/AgentTool/prompt.ts              — agent tool prompt
tools/AgentTool/resumeAgent.ts         — resume a paused agent
tools/AgentTool/runAgent.ts            — execute agent turn
```

**Built-in Agent Types:**
- `claudeCodeGuideAgent.ts` — answers questions about Claude Code itself
- `exploreAgent.ts` — fast codebase exploration
- `generalPurposeAgent.ts` — general research/multi-step tasks
- `planAgent.ts` — software architecture planning
- `statuslineSetup.ts` — status line configuration
- `verificationAgent.ts` — code verification

**Agent Memory Pattern:** Each agent gets its own `agentMemory.ts` scope — agents don't share working memory with the parent session unless explicitly passed via `agentMemorySnapshot.ts`. This is the correct pattern for your OpenClaw skill agents.

---

### Shell Execution Tools
```
tools/BashTool/
  BashTool.tsx              — main implementation
  bashCommandHelpers.ts     — command parsing helpers
  bashPermissions.ts        — permission checks for bash
  bashSecurity.ts           — security validation
  commandSemantics.ts       — command semantic analysis
  commentLabel.ts           — add labels to commands
  destructiveCommandWarning.ts — warn on destructive ops
  modeValidation.ts         — permission mode checks
  pathValidation.ts         — path safety checks
  readOnlyValidation.ts     — enforce read-only mode
  sedEditParser.ts          — parse sed-style edits
  sedValidation.ts          — validate sed usage
  shouldUseSandbox.ts       — sandbox decision logic
  toolName.ts               — tool name constants

tools/PowerShellTool/
  (mirrors BashTool structure for Windows PowerShell)
  gitSafety.ts              — Windows-specific git safety
```

**Security Architecture:** Bash security is layered:
1. `readOnlyValidation.ts` — blocks writes in read-only mode
2. `pathValidation.ts` — prevents path traversal
3. `bashSecurity.ts` — general security rules
4. `destructiveCommandWarning.ts` — warns before dangerous commands
5. `shouldUseSandbox.ts` — decides sandbox vs direct execution
6. `bashPermissions.ts` — final permission gate

Each layer is a separate file, separately testable. **Apply this layered security pattern to your cyber-security tools.**

---

### File Operation Tools
```
tools/FileReadTool/
  FileReadTool.ts
  imageProcessor.ts     — image reading (multimodal!)
  limits.ts             — file size / line limits

tools/FileEditTool/
  FileEditTool.ts
  utils.ts
  types.ts

tools/FileWriteTool/FileWriteTool.ts
tools/GlobTool/GlobTool.ts
tools/GrepTool/GrepTool.ts
```

**FileReadTool has an `imageProcessor.ts`** — confirming multimodal file reading is a first-class tool capability, not a hack. The tool accepts image files and processes them through the vision pipeline.

---

### Planning & Task Tools
```
tools/EnterPlanModeTool/   — enter structured planning mode
tools/ExitPlanModeTool/    — commit/exit plan mode
tools/EnterWorktreeTool/   — create isolated git worktree
tools/ExitWorktreeTool/    — clean up worktree
tools/TaskCreateTool/      — create a tracked task
tools/TaskGetTool/         — get task details
tools/TaskListTool/        — list all tasks
tools/TaskOutputTool/      — get task output
tools/TaskStopTool/        — stop a running task
tools/TaskUpdateTool/      — update task status
tools/TodoWriteTool/       — write todos
```

**PlanMode Pattern:** EnterPlanMode → agent reasons freely → ExitPlanMode commits the plan. The model can't take real actions during plan mode — it's a "thinking space" before execution. **Apply this to Sigrid:** "Oracle mode" where she reads runes and deliberates before advising action.

**Worktree Pattern:** Each risky operation gets an isolated git worktree. If something goes wrong, the worktree is discarded. Your NorseSagaEngine's branching system could use this pattern for experimental narrative branches.

---

### Multi-Agent Coordination
```
tools/SendMessageTool/     — send message to another agent
tools/TeamCreateTool/      — create a named agent team
tools/TeamDeleteTool/      — delete an agent team
tools/ScheduleCronTool/    — schedule recurring agent tasks
  CronCreateTool.ts
  CronDeleteTool.ts
  CronListTool.ts
tools/RemoteTriggerTool/   — trigger a remote agent
```

**Swarm Architecture Confirmed:** Claude Code has a full swarm/team system. Agents can:
- Send messages to each other (`SendMessageTool`)
- Be organized into named teams (`TeamCreateTool`)
- Be scheduled on cron (`ScheduleCronTool`)
- Be triggered remotely (`RemoteTriggerTool`)

**Application for Viking Girlfriend Skill:** Sigrid's Ørlög state machines map perfectly to an agent team:
- `bio-cyclical-agent` — tracks physical rhythms
- `wyrd-matrix-agent` — manages fate/relationship graph
- `oracle-agent` — runs divination logic
- `metabolism-agent` — hunger/energy tracking
- `nocturnal-agent` — sleep cycle management

Each is a separate agent that sends state updates to a coordinator.

---

### Knowledge & Research Tools
```
tools/WebFetchTool/
  WebFetchTool.ts
  preapproved.ts        — pre-approved domains list
  utils.ts

tools/WebSearchTool/WebSearchTool.ts
tools/LSPTool/
  LSPTool.ts
  formatters.ts
  schemas.ts
  symbolContext.ts      — code symbol context extraction

tools/BriefTool/
  BriefTool.ts
  attachments.ts
  upload.ts             — file attachment upload
```

**LSPTool** provides Language Server Protocol integration — the agent can query code symbols, types, references directly from the LSP. This is how it understands code structure without reading every file.

---

### Skill & Config Tools
```
tools/SkillTool/SkillTool.ts       — invoke a skill
tools/ConfigTool/
  ConfigTool.ts
  supportedSettings.ts   — validated settings list
tools/ToolSearchTool/ToolSearchTool.ts — search deferred tools
```

**ToolSearchTool** is the tool for loading deferred tools. Claude doesn't get all tools at once — tools are loaded lazily based on relevance. This is a **context window optimization**: only relevant tools take up space.

---

### Interaction Tools
```
tools/AskUserQuestionTool/   — ask user a question (blocks until answered)
tools/REPLTool/
  constants.ts
  primitiveTools.ts    — base REPL operations
tools/NotebookEditTool/      — Jupyter notebook editing
tools/SleepTool/             — wait/delay
tools/SyntheticOutputTool/   — generate synthetic output for testing
tools/McpAuthTool/           — MCP server authentication
tools/ListMcpResourcesTool/  — list MCP resources
tools/ReadMcpResourceTool/   — read MCP resource
tools/MCPTool/
  classifyForCollapse.ts  — decide when to collapse MCP output
```

---

## Tool Anatomy Pattern
Every tool follows the same structure:
```
tools/{ToolName}/
  {ToolName}.ts(x)   — core logic + tool definition
  UI.tsx             — Ink terminal rendering component
  prompt.ts          — tool description for the model
  constants.ts       — tool-specific constants
  [utils.ts]         — shared helpers
  [types.ts]         — types
  [schemas.ts]       — input/output schemas
```

**The `prompt.ts` file is especially important** — it's the description the model sees when deciding whether to use this tool. Well-crafted `prompt.ts` files = more accurate tool selection.

**Cyber-Viking Application:** When building tools for your OpenClaw skills, follow this exact anatomy. Each tool gets its own directory with: logic, UI, prompt description, constants. The prompt.ts is your tool's "calling card" to the model.

---

## Permission Architecture
```
tools/BashTool/bashPermissions.ts
hooks/toolPermission/PermissionContext.ts
hooks/toolPermission/handlers/
  coordinatorHandler.ts   — coordinator agent permissions
  interactiveHandler.ts   — interactive user permissions
  swarmWorkerHandler.ts   — swarm worker permissions
hooks/toolPermission/permissionLogging.ts
```

**Three permission modes for three contexts:** coordinator, interactive, swarm worker. Each has different trust levels. The permission context is passed down to `filter_tools_by_permission_context()` which removes blocked tools from the tool list before the model sees them.

**Application:** This pattern maps to Sigrid's consent system — different interaction contexts (casual chat vs. intimate moment vs. ritual) should expose different capability sets.

---

## shared/ Utilities
```
tools/shared/gitOperationTracking.ts  — track git ops for audit
tools/shared/spawnMultiAgent.ts       — spawn multiple agents
```

`spawnMultiAgent.ts` is the core multi-agent spawning utility shared across team/swarm tools.

---

## Tool Count Summary
- **184 total tool entries** in tools_snapshot.json
- **207 total command entries** in commands_snapshot.json
- Original TypeScript archive had **1902 files** across 35 subsystems
