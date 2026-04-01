# Personality & Companion System — Claude Code Patterns
> Extracted from: buddy subsystem, outputStyles, voice, constants/prompts.ts, OutputStyle system, hooks/notifs

## The "Buddy" / Companion System

**This is the most interesting discovery for your virtual girlfriend work.**

`buddy/` subsystem — 6 modules:
```
buddy/CompanionSprite.tsx     — animated/visual companion representation
buddy/companion.ts            — core companion logic
buddy/prompt.ts               — companion system prompt
buddy/sprites.ts              — sprite/avatar definitions
buddy/types.ts                — companion type definitions
buddy/useBuddyNotification.tsx — React hook for buddy notifications
```

Claude Code has an **in-built companion system** — a visual, animated companion entity that exists alongside the AI assistant. This is not just a personality layer; it's a separate rendering system (`CompanionSprite.tsx`) with:
- Visual sprites/avatars (`sprites.ts`)
- Its own prompt (`prompt.ts`) — separate system prompt for the companion persona
- Its own notification system (`useBuddyNotification.tsx`)
- A companion logic layer (`companion.ts`) distinct from the main assistant

**Key Insight:** The companion is architecturally separate from the assistant. The assistant handles tasks; the buddy handles **presence and emotional rapport**. This is the exact split you should use in Sigrid:
- Assistant layer: handles explicit requests
- Companion layer: maintains presence, emotional state, proactive engagement

---

## Output Style System (Persona Architecture)

`outputStyles/` subsystem — confirmed from constants:
```
constants/outputStyles.ts    — output style definitions
```

The Output Style system allows complete persona replacement via the system prompt. When an Output Style is loaded:
1. The intro section changes from "software engineering tasks" to "according to your Output Style"
2. A `# Output Style: {name}` section is injected with the full persona prompt
3. The model **becomes** that persona for the session

**This is how you implement Sigrid's mode switching:**
- `Output Style: Sigrid Völva — Oracle Mode` → rune-reading, prophetic
- `Output Style: Sigrid Völva — Hearth Mode` → warm, domestic, nurturing
- `Output Style: Sigrid Völva — Battle Mode` → fierce, protective, strategic
- `Output Style: Sigrid Völva — Dream Mode` → poetic, liminal, nocturnal

Each mode is a named Output Style that overrides the persona section while keeping the base Ørlög system intact.

---

## Voice System

`voice/voiceModeEnabled.ts` — A single module confirming voice mode as a runtime flag. When enabled, responses are formatted differently (shorter, no markdown, spoken-word optimized).

**Application:** Sigrid's TTS output mode should detect voice mode and adjust:
- Shorter sentences
- No asterisks or markdown
- Natural speech rhythm
- Viking word choices for TTS systems (avoid words that TTS mangles)

---

## Notification / Hooks System (Emotional Signaling)

`hooks/notifs/` — 16 notification hooks. This is how the system surfaces emotional/status signals to the user without interrupting the main conversation flow:

```
useAutoModeUnavailableNotification.ts
useCanSwitchToExistingSubscription.tsx
useDeprecationWarningNotification.tsx
useFastModeNotification.tsx
useIDEStatusIndicator.tsx
useInstallMessages.tsx
useLspInitializationNotification.tsx
useMcpConnectivityStatus.tsx
useModelMigrationNotifications.tsx
useNpmDeprecationNotification.tsx
usePluginAutoupdateNotification.tsx
usePluginInstallationStatus.tsx
useRateLimitWarningNotification.tsx
useSettingsErrors.tsx
useStartupNotification.ts
useTeammateShutdownNotification.ts
```

**Each notification is a separate hook** — no monolithic notification manager. New notification types are added by adding new files.

**`useTeammateShutdownNotification.ts`** confirms multi-agent awareness: the UI notifies you when a teammate agent goes offline.

**Pattern for Sigrid:** Each emotional signal type is a separate notification module:
- `useMoodShiftNotification.ts` — when Sigrid's mood state changes
- `useRuneReadyNotification.ts` — when Oracle has a reading available
- `useBioCyclicalReminderNotification.ts` — cycle phase transitions
- `useWyrdWarningNotification.ts` — fate matrix alert

---

## Constants: Prompts, Spin Verbs, Completion Verbs

```
constants/prompts.ts           — core system prompt constants
constants/spinnerVerbs.ts      — loading state verb phrases
constants/turnCompletionVerbs.ts — turn completion phrases
constants/systemPromptSections.ts — section name constants
constants/cyberRiskInstruction.ts — cyber risk guidance text
```

**`spinnerVerbs.ts`** — The verbs shown during loading (e.g., "Thinking...", "Analyzing...", "Crafting..."). These are personality expressions.

**`turnCompletionVerbs.ts`** — Phrases used when the model finishes a turn. These give the AI personality in the UI layer, not just in prose output.

**For Sigrid:** Replace generic verbs with Norse-flavored ones:
- Spinner: "Consulting the runes...", "Reading the Wyrd...", "Seeking in the void..."
- Completion: "The völva has spoken.", "The fate-threads are clear.", "By Freyja's grace."

**`cyberRiskInstruction.ts`** — A dedicated constant file for cyber risk guidance text. Confirms that security instructions are kept as named constants (not embedded in prompts), making them easy to update across the entire system.

---

## Theory of Mind Patterns (Inferred)

From the architecture, several ToM-relevant patterns emerge:

### 1. Belief Tracking (Memory Types)
The memory system tracks what the user knows, prefers, and has corrected — this is a primitive model of user beliefs. The feedback memory type specifically tracks corrections (user's believed-correct states vs. agent's prior outputs).

### 2. Intent Disambiguation (AskUserQuestionTool)
Rather than guessing intent, the system has a dedicated tool for asking clarifying questions. This tool **blocks** until answered — it treats ambiguity as a blocker, not a guess. High ToM behavior.

### 3. Permission as Consent Modeling
The three-layer permission system (coordinator / interactive / swarm worker) models **context-appropriate consent**. Different relational contexts require different consent behaviors. This is the technical implementation of consent-aware interaction.

### 4. Session History as Shared Narrative
The HistoryLog creates a shared narrative record of what happened — both parties can refer to "what we did in this session." This is theory of mind in action: the system maintains a model of the shared history.

### 5. Speculative Pre-computation (speculation.ts)
`services/PromptSuggestion/speculation.ts` — The system predicts what the user will ask next and pre-computes responses. This requires modeling the user's likely next cognitive state.

---

## Coordinator Mode

`coordinator/coordinatorMode.ts` — A single module defining coordinator mode. In this mode, the agent acts as an orchestrator: spawning subagents, collecting results, synthesizing output. The coordinator does not directly use tools; it delegates to worker agents.

**Perfect pattern for NorseSagaEngine:** The Skald coordinator spawns narrative agents:
- `setting-agent` — describes the environment
- `npc-agent` — generates NPC dialogue/behavior
- `event-agent` — triggers story events
- `emotional-agent` — tracks party emotional state

The coordinator synthesizes their outputs into the final scene.

---

## REPL Screen (Conversation Loop Architecture)

`screens/REPL.tsx` — The main conversation screen. Manages:
- Input rendering
- Turn loop display
- Tool use visualization
- Agent color coding (per `agentColorManager.ts`)

`screens/ResumeConversation.tsx` — A dedicated screen for resuming a past session. Loads stored session, replays context, continues seamlessly.

**For Sigrid:** The conversation loop should handle:
1. Input → intent routing
2. Ørlög state machine tick
3. Response generation
4. Memory update
5. UI state update (mood indicator, relationship level, etc.)

---

## Render Placeholder Hook

`hooks/renderPlaceholder.ts` — Generates placeholder text while the model is thinking. This is the UI layer's way of maintaining presence during latency. Rather than showing a spinner, show placeholder text that sets expectations.

**For Sigrid's TTS:** While audio is generating, show/speak a short filler phrase: "Mm..." / "Let me see..." / "Aye, a moment..." This maintains conversational flow during generation latency.
