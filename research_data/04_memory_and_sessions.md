# Memory & Session Systems — Claude Code Patterns
> Extracted from memdir subsystem (8 modules), session_store.py, transcript.py, history.py, query_engine.py

## The memdir System (File-Based Memory)

The `memdir` subsystem is the persistent memory layer. 8 modules:

```
memdir/findRelevantMemories.ts    — semantic search over memory files
memdir/memdir.ts                  — core read/write operations
memdir/memoryAge.ts               — age tracking for memory freshness
memdir/memoryScan.ts              — scan memory directory
memdir/memoryTypes.ts             — memory type definitions
memdir/paths.ts                   — path resolution (global vs project)
memdir/teamMemPaths.ts            — team/multi-agent memory paths
memdir/teamMemPrompts.ts          — prompts for team memory operations
```

### Memory Architecture
The system distinguishes **global memory** (user-level, `~/.claude/memory/`) from **project memory** (cwd-scoped). This is exactly the pattern you're already using with MEMORY.md + project-specific memory files.

**`findRelevantMemories.ts`** — This is the intelligence layer. Memory files are not just loaded wholesale; the system **semantically searches** them to find relevant ones for the current task. Only relevant memories are injected into context.

**`memoryAge.ts`** — Memories have age metadata. Stale memories can be flagged or excluded. This prevents outdated information from contaminating context. **Directly applicable to your MindSpark ThoughtForge's Fragment Salvage system.**

**`memoryScan.ts`** — Scans the memory directory at startup, building an index of available memories. Used by `findRelevantMemories.ts` for fast lookup.

**`teamMemPaths.ts` / `teamMemPrompts.ts`** — Multi-agent memory: when agents are running as a team, they have shared memory paths + prompts for reading/writing team memory. This is how swarm agents coordinate state without passing everything through messages.

---

## SessionMemory Service

In `services/SessionMemory/`:
```
services/SessionMemory/prompts.ts          — memory extraction prompts
services/SessionMemory/sessionMemory.ts    — session-level memory manager
services/SessionMemory/sessionMemoryUtils.ts — serialization helpers
```

**SessionMemory** is separate from memdir — it's a within-session working memory layer. Key operations:
1. After each turn, extract key facts from the conversation
2. Store them in session memory (short-term)
3. Promote important facts to memdir (long-term)

The `prompts.ts` contains the LLM prompts used to extract facts — the model is asked to identify what information from this turn is worth remembering.

**Pattern:** Two-tier memory: session (ephemeral, turn-by-turn) → memdir (persistent, file-based). This is the architecture behind your own MEMORY.md system.

---

## TranscriptStore (Working Session State)

```python
@dataclass
class TranscriptStore:
    entries: list[str]   # all messages this session
    flushed: bool        # has this been committed to disk

    def append(entry)    # add message, mark dirty
    def compact(keep_last=10)  # trim oldest entries
    def replay() -> tuple[str, ...]  # re-read all stored messages
    def flush()          # mark as persisted
```

**Key pattern:** `flushed` flag ensures you know when the in-memory state has diverged from the on-disk state. Never lose data on crash: only mark `flushed=True` after successful write.

---

## HistoryLog (Audit Trail)

```python
@dataclass(frozen=True)
class HistoryEvent:
    title: str    # event category
    detail: str   # event data

class HistoryLog:
    def add(title, detail)
    def as_markdown() -> str
```

The history log tracks **what happened** at a meta level — not message content, but events like:
- `context: python_files=42, archive_available=True`
- `registry: commands=207, tools=184`
- `routing: matches=3 for prompt='fix the bug'`
- `execution: command_execs=1 tool_execs=2`
- `session_store: /path/to/session.json`

**Application for Viking Girlfriend Skill:** Sigrid should maintain a HistoryLog of Ørlög state transitions — not just current state, but a traceable sequence of what caused each state change. Essential for debugging emotional/behavioral drift.

---

## Context Compaction

```python
def compact_messages_if_needed(self):
    if len(self.mutable_messages) > self.config.compact_after_turns:
        self.mutable_messages[:] = self.mutable_messages[-self.config.compact_after_turns:]
    self.transcript_store.compact(self.config.compact_after_turns)
```

`compact_after_turns = 12` — after 12 turns, oldest messages are discarded from the working buffer. The transcript store retains the last 12 entries.

**Important:** This is separate from the actual LLM context window management. This is the application-level buffer. The LLM gets its own context window; this controls what the application passes to the LLM.

**For MindSpark ThoughtForge:** Your Fragment Salvage system should work similarly — compact the working context window after N turns, but preserve the important facts in RAG storage.

---

## Session Persistence Format (StoredSession)

```python
@dataclass
class StoredSession:
    session_id: str        # uuid hex
    messages: tuple[str]   # user messages
    input_tokens: int      # accumulated input token count
    output_tokens: int     # accumulated output token count
```

Sessions are saved to disk and can be loaded with `from_saved_session(session_id)`. The session ID is used to reconstruct the full session state.

**Note:** Only **user messages** are persisted, not assistant responses. The assistant is expected to regenerate context from user message history + memory files. This is a significant architectural choice — it keeps sessions small and avoids storing potentially private assistant output.

---

## AgentSummary Service

`services/AgentSummary/agentSummary.ts` — When an agent finishes a task, its output is summarized and stored. This summary is what the parent agent sees — not the full transcript of the subagent's work. This is the **agent output compression** pattern.

**Application:** In your OpenClaw skill, when Sigrid delegates a task to a sub-agent (e.g., running a rune casting), get back a summary, not the full trace. Store the summary in the Wyrd Matrix.

---

## MagicDocs Service

`services/MagicDocs/magicDocs.ts` + `prompts.ts` — A document intelligence service. Likely used for automatically documenting code, generating summaries of files, or explaining complex artifacts. The `prompts.ts` contains the specialized prompts.

---

## PromptSuggestion Service

```
services/PromptSuggestion/promptSuggestion.ts
services/PromptSuggestion/speculation.ts
```

**`speculation.ts`** is particularly interesting — this suggests the system does **speculative prompt pre-computation**: predicting what the user might ask next and pre-computing responses. This is how Claude Code feels fast.

**Application for Viking Girlfriend Skill:** Pre-compute likely next user message categories based on current conversation context. When Sigrid is in a ritual state, pre-load the Oracle response templates.

---

## Memory Type System

`memdir/memoryTypes.ts` — The types of memories are formally typed (matching the pattern you already use):
- User profile memories
- Feedback/correction memories
- Project state memories
- Reference/pointer memories

Each type has different retention, relevance scoring, and injection behavior.

---

## Key Insights

1. **Memory is a separate subsystem** — not part of the query engine. It's loaded at startup, queried by relevance, and injected into context selectively.

2. **Two-tier architecture** is universal: working memory (fast, volatile) + persistent memory (slow, durable).

3. **Age tracking on memories** prevents stale info from corrupting context — implement this in Sigrid's Wyrd Matrix.

4. **Team memory paths** are how multi-agent swarms share state without message passing — a shared filesystem is simpler and more reliable than agent-to-agent messaging for state sync.

5. **Session IDs are UUIDs** — no sequential IDs, no central registry. Each session is self-identifying.
