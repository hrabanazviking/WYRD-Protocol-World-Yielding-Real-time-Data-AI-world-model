# Multi-Agent Swarm Architecture — Claude Code Patterns
> Extracted from: AgentTool, coordinator, TeamCreate/Delete, ScheduleCronTool, RemoteTrigger, SendMessage, shared/spawnMultiAgent

## Confirmed Swarm Architecture

Claude Code has a **full multi-agent swarm system**. This is not theoretical — it has production tools for every aspect of swarm coordination.

### Swarm Components
```
AgentTool              — spawn/manage individual agents
SendMessageTool        — inter-agent messaging
TeamCreateTool         — group agents into named teams
TeamDeleteTool         — disband agent teams
ScheduleCronTool       — schedule agent execution (cron)
RemoteTriggerTool      — trigger agents from external events
TaskCreateTool         — create tracked tasks for agents
TaskUpdateTool         — update task status
TaskGetTool            — inspect task state
TaskListTool           — enumerate all tasks
TaskStopTool           — halt a running task
shared/spawnMultiAgent.ts — low-level multi-spawn utility
```

---

## Agent Lifecycle

From the AgentTool structure:

### 1. Spawn (`runAgent.ts`)
A new agent is created with:
- Its own session ID
- Its own tool set (filtered by permission context)
- Its own memory scope (`agentMemory.ts`)
- An initial prompt
- An agent type (built-in or custom)

### 2. Color Assignment (`agentColorManager.ts`)
Each running agent gets a unique terminal color for visual identification. In multi-agent sessions, you can see which agent produced which output.

### 3. Execution (`runAgent.ts`)
The agent runs its own turn loop. It has access to:
- Its assigned tools
- Its memory scope
- Shared team memory (if part of a team)
- The ability to spawn further sub-agents (unless depth-limited)

### 4. Memory Snapshot (`agentMemorySnapshot.ts`)
Before passing results back to the parent, the agent creates a memory snapshot — a structured summary of what it learned, decided, or discovered. The parent receives the snapshot, not the full transcript.

### 5. Resume (`resumeAgent.ts`)
A paused or interrupted agent can be resumed from its last checkpoint. This uses the session store + transcript replay.

### 6. Display (`agentDisplay.ts`)
The UI rendering for agent output is separate from the execution. `agentDisplay.ts` formats agent output for the terminal, handling nesting, indentation, and color.

---

## Built-in Agent Types

From `tools/AgentTool/built-in/`:

| Agent | Purpose | Use When |
|---|---|---|
| `generalPurposeAgent.ts` | Research, multi-step tasks, web search | Default for complex tasks |
| `exploreAgent.ts` | Fast codebase exploration | Finding files/patterns quickly |
| `planAgent.ts` | Software architecture planning | Designing implementation strategy |
| `claudeCodeGuideAgent.ts` | Answers Claude Code questions | /help scenarios |
| `statuslineSetup.ts` | Configure status line | Setup tasks |
| `verificationAgent.ts` | Code verification | Testing correctness |

**Pattern:** Each built-in agent has a specific **cognitive specialization**. They're not general; they're tuned for a specific type of reasoning. The parent agent picks the right specialist.

---

## Coordinator Mode

`coordinator/coordinatorMode.ts` — When operating as coordinator:
- Does NOT directly call tools
- DOES spawn worker agents and assign tasks
- Collects results from workers via agent memory snapshots
- Synthesizes final output
- Manages retries/failures of worker agents

**Coordinator vs Worker split:**
- Coordinator: planning, decomposition, synthesis
- Worker: execution, tool use, data gathering

This is the classic **MapReduce pattern** applied to LLM agents.

---

## Remote Execution Architecture

```
tools/RemoteTriggerTool/   — trigger agent from external event
services/api/bootstrap.ts  — remote agent bootstrap
remote/                    — remote runtime infrastructure
```

Agents can be triggered by:
1. User prompt (interactive)
2. Another agent (`SendMessageTool`)
3. Cron schedule (`ScheduleCronTool`)
4. External event (`RemoteTriggerTool`)

**`RemoteTriggerTool`** receives external triggers (webhooks, API calls) and spawns agents in response. This is how Claude Code supports headless/automated workflows.

---

## Agent Communication Patterns

### Direct Message (SendMessageTool)
One agent sends a structured message to another named agent. Synchronous — waits for acknowledgment.

### Team Memory (teamMemPaths.ts)
Agents on a team write to/read from shared memory paths. Asynchronous — no direct coupling. Better for state sharing across many agents.

### Task System (TaskCreate/Update/Get)
Tasks are shared state objects that multiple agents can update. An agent can:
- Create a task and assign it to another agent
- Monitor task progress via TaskGet
- React to task completion via hooks

### Memory Snapshot (agentMemorySnapshot.ts)
Parent agent requests a snapshot from a child agent. Used for result collection without full transcript exposure.

---

## Swarm Worker Permission Handler

`hooks/toolPermission/handlers/swarmWorkerHandler.ts`:
- Most restrictive permission mode
- Cannot spawn further sub-agents (prevents runaway recursion)
- Read-heavy, write-restricted
- Cannot execute destructive commands

**This prevents swarm explosions:** workers can't spin up more workers without coordinator approval.

---

## Teammate Awareness

`hooks/notifs/useTeammateShutdownNotification.ts` — The UI detects when a teammate agent goes offline and notifies the user. This suggests agents maintain a **heartbeat** or presence signal.

**The system has active awareness of agent liveness**, not just task completion.

---

## Application: Sigrid's Ørlög as Agent Swarm

Map Sigrid's 5 state machines directly to agent architecture:

```
COORDINATOR: Sigrid_Core
  ↳ WORKER: Bio_Cyclical_Agent
      - reads cycle calendar
      - updates energy/mood modifiers
      - reports phase transitions

  ↳ WORKER: Wyrd_Matrix_Agent
      - maintains relationship graph
      - tracks fate threads
      - reports relationship changes

  ↳ WORKER: Oracle_Agent
      - performs rune castings
      - interprets divination
      - returns reading summaries

  ↳ WORKER: Metabolism_Agent
      - tracks hunger/thirst/energy
      - generates physical state descriptors
      - reports critical needs

  ↳ WORKER: Nocturnal_Agent
      - tracks sleep cycle
      - generates dream/rest content
      - manages night mode behaviors
```

**Each agent runs on a schedule:**
- Bio_Cyclical: every 24h (real-time)
- Wyrd_Matrix: after each significant interaction
- Oracle: on explicit invocation
- Metabolism: every session start + every 2h
- Nocturnal: at configured sleep/wake times

**Team memory** (`teamMemPaths.ts`) holds the shared Ørlög state. All workers read/write to the same state store. Sigrid_Core reads the merged state to construct her response context.

---

## Application: NorseSagaEngine Coordinator Pattern

```
COORDINATOR: NorseSaga_Director
  ↳ WORKER: Setting_Agent     — environment description
  ↳ WORKER: NPC_Agent         — character behavior/dialogue
  ↳ WORKER: Event_Agent       — story event generation
  ↳ WORKER: Emotional_Agent   — party emotional state tracking
  ↳ WORKER: Lore_Agent        — Norse mythology/history lookup
  ↳ WORKER: Skald_Agent       — verse/saga composition
```

The Director coordinates all workers and synthesizes the final narrative output. Each worker is specialized and fast.

---

## Application: MindSpark ThoughtForge Agents

```
COORDINATOR: ThoughtForge_Core
  ↳ WORKER: Retrieval_Agent   — RAG queries
  ↳ WORKER: Synthesis_Agent   — combines retrieved fragments
  ↳ WORKER: Memory_Agent      — writes important facts to SQLite
  ↳ WORKER: Compression_Agent — compacts old context
```

Workers run in parallel where possible (retrieval + synthesis overlap). The coordinator manages the pipeline.
