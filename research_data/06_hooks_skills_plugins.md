# Hooks, Skills & Plugin System — Claude Code Patterns
> Extracted from: hooks subsystem (104 modules), skills subsystem (20 modules), plugins subsystem

## Hooks Architecture

The hooks system has **104 modules** across several categories. This is a React hooks pattern applied to a CLI tool — each hook encapsulates a reactive behavior.

### Permission Hooks
```
hooks/toolPermission/PermissionContext.ts
hooks/toolPermission/handlers/coordinatorHandler.ts
hooks/toolPermission/handlers/interactiveHandler.ts
hooks/toolPermission/handlers/swarmWorkerHandler.ts
hooks/toolPermission/permissionLogging.ts
```

**PermissionContext** is a React context (likely Ink-based) that holds the current permission mode. Each handler type applies different permission rules:
- `coordinatorHandler` — trusts subagents, may auto-approve more actions
- `interactiveHandler` — always prompts the user for risky actions
- `swarmWorkerHandler` — most restricted, minimal trust

**`permissionLogging.ts`** — All permission decisions are logged for audit. Every grant or denial is recorded with context.

### Suggestion Hooks
```
hooks/fileSuggestions.ts      — autocomplete file paths
hooks/unifiedSuggestions.ts   — combined suggestion aggregator
```

The suggestion system is separate from the tool system. It provides autocomplete-style hints without triggering tool calls. `unifiedSuggestions.ts` aggregates from multiple sources.

**For Viking Girlfriend Skill:** Suggestions for Sigrid's input field (if you build a custom UI) could be rune names, Norse phrases, relationship-appropriate responses.

---

## Skills System (20 Bundled Skills)

Skills are **slash command extensions** — user-invocable workflows defined as prompts with optional code logic.

```
skills/bundled/
  batch.ts              — batch processing skill
  claudeApi.ts          — Claude API usage helper
  claudeApiContent.ts   — API content formatting
  claudeInChrome.ts     — Chrome extension integration
  debug.ts              — debugging workflow
  index.ts              — skill registry
  keybindings.ts        — keybinding customization skill
  loop.ts               — recurring interval execution
  loremIpsum.ts         — lorem ipsum generator
  remember.ts           — "remember this" skill
  scheduleRemoteAgents.ts — agent scheduling skill
  simplify.ts           — code simplification review
  skillify.ts           — create new skills from description
  stuck.ts              — "I'm stuck" help skill
  updateConfig.ts       — config update skill
  verify.ts             — code verification skill
  verifyContent.ts      — content verification skill

skills/bundledSkills.ts      — skill loader/registry
skills/loadSkillsDir.ts      — load skills from directory
skills/mcpSkillBuilders.ts   — build skills from MCP servers
```

### Key Skills Deep-Dive

**`remember.ts`** — The "remember" skill. When invoked (`/remember`), the model extracts the key fact from context and writes it to the memory system. This is the human-in-the-loop memory write path.

**`skillify.ts`** — **Skills can create new skills.** Give Claude a description of a workflow and it will generate a new skill file. This is a self-extending capability system.

**`loop.ts`** — Run a skill on a recurring interval. `/loop 5m /skill-name` polls every 5 minutes. Used for monitoring, status checks, long-running workflows.

**`scheduleRemoteAgents.ts`** — Schedule agents to run on cron. The cron tool (`ScheduleCronTool`) is the infrastructure; this skill is the user-friendly wrapper.

**`stuck.ts`** — When the user says they're stuck, this skill activates a different mode: more explanatory, less action-oriented, walks through reasoning.

**`mcpSkillBuilders.ts`** — MCP servers can **expose skills**, not just tools. When an MCP server provides skill definitions, they're loaded here and become available as slash commands.

### Skill Architecture
Skills are defined as **prompts** — not code. A skill is a text prompt that gets injected into the system when the slash command is invoked. The model then executes the skill "instructions" in context.

```typescript
// Simplified skill structure
interface BundledSkill {
  name: string;          // slash command name
  description: string;   // shown to user
  prompt: string;        // injected into context when invoked
  userInvocable: boolean; // appears in /help
}
```

**Application for OpenClaw:** Your rune casting skill is already following this pattern. Each skill in `charm_crush_hall/rune_casting_openclaw_skill/` is a skill file that gets loaded when invoked. Extend this to all Sigrid's capabilities.

---

## Plugin System

`plugins/` subsystem — Plugin architecture details:

From `deferred_init.py`:
```python
plugin_init: bool  # enabled only when trusted=True
```

Plugins require **trusted mode** — they're not loaded in sandboxed environments. This suggests plugins have elevated permissions (can register new tools, modify system behavior).

From the `services/` directory, plugins likely integrate via:
- Tool registration (adding new tools to the tool registry)
- Skill registration (adding new slash commands)
- Hook injection (adding new reactive behaviors)
- MCP server connections

**Anti-gravity Plugin Pattern:** Your `anti-gravity-githublocal-NorseSaga-Engine` uses a similar model. Plugins that extend the core engine are loaded conditionally based on trust/environment.

---

## Schemas: hooks.ts

`schemas/hooks.ts` — Defines the JSON schema for user-configured hooks. Hooks (as users configure them in settings) have a validated schema — not arbitrary shell commands, but structured hook definitions with typed fields.

From the context, hook types include:
- `PreToolUseHook` — runs before a tool call
- `PostToolUseHook` — runs after a tool call
- `UserPromptSubmitHook` — runs when user submits input
- `StopHook` — runs when the agent stops
- `NotificationHook` — runs on system events

**This is how users add custom behavior without modifying core code.** Each hook type is a pipeline intercept point.

---

## Migrations System

`migrations/` subsystem — Handles config/data format migrations. When the app updates and the schema changes, migrations run automatically at startup to upgrade stored data.

**Pattern:** Your MindSpark ThoughtForge's SQLite schema should have a migrations system. When you add new columns or change the vector index format, migration files handle the upgrade path.

---

## Constants Deep-Dive

The `constants/` subsystem (21 modules) reveals what the engineers considered worth naming:

```
constants/apiLimits.ts          — rate limits, token limits
constants/betas.ts              — feature flag names for beta features
constants/common.ts             — shared constants
constants/cyberRiskInstruction.ts — cyber risk guidance (named constant!)
constants/errorIds.ts           — error identifier strings
constants/figures.ts            — UI figures/icons
constants/files.ts              — file name constants (CLAUDE.md, etc.)
constants/github-app.ts         — GitHub app constants
constants/keys.ts               — keyboard key constants
constants/messages.ts           — user-facing message strings
constants/oauth.ts              — OAuth flow constants
constants/outputStyles.ts       — output style definitions
constants/product.ts            — product identity constants
constants/prompts.ts            — prompt constant strings
constants/spinnerVerbs.ts       — loading verb phrases
constants/system.ts             — system-level constants
constants/systemPromptSections.ts — prompt section name constants
constants/toolLimits.ts         — per-tool limits
constants/tools.ts              — tool name constants
constants/turnCompletionVerbs.ts — turn-end phrases
constants/xml.ts                — XML tag constants
```

**`constants/xml.ts`** — XML tags used in prompts/responses. Anthropic uses XML tags heavily for structured prompting. Named constants for tag names prevents typos and enables refactoring.

**`constants/betas.ts`** — Feature flags as named constants. Each beta feature has a constant that gates its behavior. **Apply this to your projects:** use named feature flags for experimental Ørlög features.

**`constants/figures.ts`** — UI icons/symbols as constants. For a cyber-Viking UI, this would be rune symbols, Norse icons, etc.

---

## The Keybindings System

`keybindings/` subsystem — Full keyboard binding system:
- User-configurable key bindings via `~/.claude/keybindings.json`
- Support for chord bindings (multi-key sequences)
- IDE-style rebinding

**For Sigrid's UI:** If you build a TUI for the Viking Girlfriend Skill, implement custom keybindings using this pattern. Norse-themed shortcuts: `Alt+R` for rune reading, `Alt+O` for Oracle mode, etc.

---

## Summary of Learnable Patterns

| Pattern | Source | Application |
|---|---|---|
| Skill-as-prompt | `skills/bundled/*.ts` | OpenClaw skill definitions |
| Skillify (self-extending) | `skillify.ts` | Sigrid can create new skills |
| Loop skill | `loop.ts` | Scheduled Ørlög state ticks |
| Permission context per mode | `toolPermission/handlers/` | Sigrid consent system |
| Hooks as pipeline intercepts | `schemas/hooks.ts` | Pre/post tool hooks for Viking tools |
| Named constants for prompts | `constants/prompts.ts` | All Sigrid prompt strings as constants |
| Feature flags | `constants/betas.ts` | Experimental Ørlög features |
| Migrations | `migrations/` | MindSpark schema upgrades |
| MCP skill builders | `mcpSkillBuilders.ts` | Expose Sigrid as MCP skills |
