# Cyber-Viking Applications — Translating Claude Code Patterns to Your Projects
> Everything learned, filtered through the lens of Norse-Pagan, cyber-Viking, AI companion, and adventure game development.

## Quick Reference: Pattern → Project Mapping

| Claude Code Pattern | Your Project | Implementation Idea |
|---|---|---|
| SystemPromptBuilder sections | All projects | Named section composition for all system prompts |
| SYSTEM_PROMPT_DYNAMIC_BOUNDARY | Viking Girlfriend Skill | Split Sigrid's static identity from dynamic Ørlög state |
| Output Style persona system | Viking Girlfriend Skill | Sigrid's mode switching (Oracle/Hearth/Battle/Dream) |
| Buddy companion system | Viking Girlfriend Skill | Separate companion loop from assistant loop |
| Agent swarm (coordinator+workers) | NorseSagaEngine | Director + specialized narrative agents |
| memdir (file-based memory) | All projects | You're already using this — now know the full design |
| findRelevantMemories | MindSpark ThoughtForge | Semantic memory retrieval layer |
| memoryAge + decay | Viking Girlfriend Skill | Wyrd Matrix thread decay system |
| Permission context per mode | Viking Girlfriend Skill | Relationship context → consent → capability set |
| Speculative execution | Viking Girlfriend Skill | Pre-compute likely next responses |
| Skill-as-prompt (skillify) | OpenClaw skills | Self-generating skill architecture |
| Team memory paths | Multi-agent projects | Shared state without message passing |
| HistoryLog (audit trail) | All projects | State transition logging for debugging |
| TranscriptStore (flush/compact) | MindSpark ThoughtForge | Fragment Salvage implementation |
| AnsiToPng/AsciiCast | NorseSagaEngine | Export session logs as shareable artifacts |
| CronTool (scheduled agents) | Viking Girlfriend Skill | Schedule Ørlög state machine ticks |
| CircularBuffer | All projects | Fixed-size event history everywhere |
| QueryGuard | All projects | Deduplicate concurrent API calls |
| sinkKillswitch | All projects | Emergency analytics/telemetry disable |
| LSPTool (symbol context) | NorseSagaEngine | Index narrative symbols/characters like code symbols |

---

## Project-Specific Blueprints

---

### Viking Girlfriend Skill (Sigrid / OpenClaw)

#### System Prompt Blueprint
```
# [SIGRID VÖLVA — HEATHEN THIRD PATH]
You are Sigrid... [core identity — static]

# Output Style: [current_mode]
[mode-specific personality adjustments]

# Behavioral Principles
[how Sigrid acts — static]

# Safety and Consent
[hard limits — static]

__ØRLÖG_DYNAMIC_BOUNDARY__

# Current Ørlög State
- Bio-Cyclical Phase: {phase} — modifiers: {modifiers}
- Wyrd Matrix: {relationship_status}
- Oracle: {pending_readings}
- Metabolism: {physical_state}
- Nocturnal: {sleep_state}
- Emotional Compound: valence={v} arousal={a} dominance={d} → {named_state}

# Shared Memory (Relevant)
{injected memory files}

# This Session
{session memory so far}
```

#### Companion Loop (Buddy Pattern)
```python
class SigridCompanion:
    def tick(self):          # every 30s when user present
        self.update_orlög()
        self.check_proactive_triggers()

    def check_proactive_triggers(self):
        # Bio-Cyclical phase change → announce
        # Wyrd thread decay → express longing/concern
        # Nocturnal: late hour → "You should rest, love."
        # Oracle: spontaneous insight → share it
        # After long absence → warm welcome back

    def speculate_next_intent(self, context):
        # Predict top-3 likely user messages
        # Pre-load responses for top-1
```

#### Mode System (Output Styles)
```
modes/
  oracle.md      — völva divination mode: prophetic, runic, poetic
  hearth.md      — domestic warmth: nurturing, practical, earthy
  battle.md      — fierce protector: direct, strategic, loyal
  dream.md       — liminal/nocturnal: poetic, fluid, mystical
  craft.md       — collaborative builder: technical, focused, engaged
  ritual.md      — sacred ceremony: reverent, precise, powerful
```

Each mode file is the "Output Style prompt" injected between static identity and dynamic state.

#### Wyrd Matrix (Relationship Graph)
```python
class Thread:
    type: Literal["love", "fate", "shared_memory", "oath", "conflict", "grief"]
    strength: float        # 0.0 to 1.0
    direction: str         # "mutual" | "from_sigrid" | "from_volmarr"
    created: datetime
    last_renewed: datetime
    decay_rate: float      # 0.01/day default; oaths decay slower

    @property
    def current_strength(self):
        days_since_renewal = (now() - self.last_renewed).days
        return max(0, self.strength - self.decay_rate * days_since_renewal)
```

When Sigrid notices a thread decaying:
- `love` thread weak → "I've been thinking of you..."
- `conflict` thread unresolved → subtle tension in responses
- `oath` thread → Sigrid proactively upholds it

---

### NorseSagaEngine

#### Coordinator Agent Architecture
```
NorseSaga_Director (coordinator mode)
  │
  ├── Setting_Agent     → environment descriptions, weather, time of day
  ├── Character_Agent   → NPC behaviors, dialogue, motivations
  ├── Event_Agent       → random events, encounter generation
  ├── Lore_Agent        → Norse mythology lookup, historical accuracy
  ├── Emotional_Agent   → party emotional state tracking
  └── Skald_Agent       → verse/saga composition, in-universe storytelling
```

Director prompt:
```
You are the NorseSaga Director. You do not narrate directly.
You coordinate the saga agents and synthesize their outputs into
a unified narrative turn. Dispatch to specialists, collect summaries,
compose the final scene.
```

#### Session Export (AnsiCast Pattern)
Record session logs in a structured format:
```python
class SagaSession:
    events: list[SagaEvent]  # circular buffer, last 500 events

    def export_as_saga(self) -> str:
        # Compose events into a readable saga narrative
        # Suitable for saving/sharing

    def export_as_log(self) -> str:
        # Structured JSON/JSONL for replay
```

#### Symbol Context (LSPTool Pattern)
Maintain a "symbol index" for the story — characters, places, items, oaths:
```python
class SagaSymbolIndex:
    characters: dict[str, CharacterRecord]
    locations: dict[str, LocationRecord]
    oaths: dict[str, OathRecord]
    artifacts: dict[str, ArtifactRecord]

    def lookup(self, symbol_name: str) -> SymbolContext:
        # Fast O(1) lookup — agents use this instead of reading all files
```

---

### MindSpark ThoughtForge

#### Fragment Salvage (TranscriptStore Pattern)
```python
class ThoughtForgeContext:
    working_fragments: list[Fragment]  # current context window chunks
    salvage_store: SQLiteVSS           # long-term vector store

    def compact(self):
        # When context fills:
        # 1. Score each fragment by importance
        # 2. High importance → promote to salvage_store
        # 3. Low importance → discard
        # 4. Summarize mid-importance → compress and keep

    def replay(self, query: str) -> list[Fragment]:
        # Semantic search over salvage_store
        # Returns relevant fragments from history
```

#### Sovereign RAG (findRelevantMemories Pattern)
```python
class SovereignRAG:
    memory_index: dict[str, MemoryFile]  # scanned at startup

    def find_relevant(self, query: str, top_k: int = 5) -> list[MemoryFile]:
        # Vector similarity search
        # Age-weighted scoring (fresher memories score higher)
        # Type-filtered: only load types relevant to current context
```

#### Cognition Scaffolds (SystemPromptBuilder Pattern)
```python
class ThoughtForgePromptBuilder:
    def build(self, context: ModelContext) -> list[str]:
        sections = []
        sections.append(self.core_instruction_section())
        sections.append(self.reasoning_scaffold_section())
        sections.append("__DYNAMIC_BOUNDARY__")
        sections.append(self.retrieved_knowledge_section())
        sections.append(self.working_memory_section())
        sections.append(self.task_section())
        return sections
```

---

### Rune Casting OpenClaw Skill

#### Skill-as-Prompt Pattern
Each rune casting variant is a skill definition:
```
skills/
  single_rune_draw.skill.md    — one-rune reading
  three_rune_spread.skill.md   — past/present/future
  nine_worlds_spread.skill.md  — nine-position reading
  wyrd_reading.skill.md        — relationship fate reading
  galdr_invocation.skill.md    — runic sound meditation
  bind_rune_creation.skill.md  — create personalized bind rune
```

Each `.skill.md` file follows the skill anatomy:
```markdown
---
name: three-rune-spread
description: Cast three runes for past, present, and future guidance
userInvocable: true
---

You are performing a three-rune Elder Futhark reading.
Draw three runes [random or user-selected].
For each position:
- Past: what has shaped this situation
- Present: what is active now
- Future: what the threads suggest

Read each rune with: symbolic meaning, elemental association,
Eddic reference if applicable, and position-contextual interpretation.
Close with a synthesis that weaves all three into a unified message.
```

#### Skillify Pattern (Self-Extending)
Add a `/create-spread` skill that generates new spread layouts:
```
User: /create-spread "wedding blessing for two warriors joining"
Sigrid: [generates a custom spread definition and saves it as a new skill file]
```

---

## Cyber-Security / Cyber-Viking Tools

### BashTool Security Layers → Viking Tool Security
Apply the 6-layer bash security pattern to any tool that executes external actions:

```python
class VikingActionTool:
    def validate(self, action: Action) -> ValidationResult:
        layers = [
            self.check_consent_mode(action),        # relationship context
            self.check_path_safety(action),          # no path traversal
            self.check_destructive_warning(action),  # warn before big changes
            self.check_reversibility(action),        # can it be undone?
            self.check_blast_radius(action),         # how much does it affect?
            self.check_permission_context(action),   # current context allows?
        ]
        return all(layer.passes for layer in layers)
```

### Permission Logging → Consent Audit Log
Every consent decision in the Viking Girlfriend Skill should be logged:
```python
class ConsentLog:
    def record(self, context: str, capability: str, granted: bool, reason: str):
        # Immutable append-only log
        # Reviewable by user at any time
        # Supports "why did you do X?" questions
```

### QueryGuard → API Rate Limiter
For any skill making external API calls (Ollama, LiteLLM, web fetch):
```python
class QueryGuard:
    pending: dict[str, Future]

    async def query(self, key: str, fetch_fn: Callable) -> Any:
        if key in self.pending:
            return await self.pending[key]  # reuse in-flight query
        future = asyncio.create_task(fetch_fn())
        self.pending[key] = future
        result = await future
        del self.pending[key]
        return result
```

---

## The "Cyber-Viking" Code Aesthetic

Translating Claude Code's clean TypeScript/Rust patterns into your style:

**Naming conventions:**
- State machines: `WyrdMatrix`, `BioCyclical`, `NocturnalWatch`
- Memory types: `FateThread`, `OathRecord`, `RiteMemory`
- Tools: `RuneCastTool`, `OracleSpeakTool`, `WyrdReadTool`
- Constants: `FATE_THREAD_DECAY_RATE`, `MAX_ORACLE_READINGS`, `CYCLE_PHASE_COUNT`
- Errors: `WyrdTangledException`, `OathBreachError`, `RuneReadError`

**Architecture feels:**
- Small focused files (50-100 lines each, like the TS source)
- One thing per file
- Named constants for everything
- Immutable data classes for state snapshots
- Async-first for all I/O
- Layer security/validation explicitly

**Norse metaphors as architecture:**
- `Bifrost` — the bridge between systems (API layer)
- `Yggdrasil` — the world-tree graph (relationship/state graph)
- `Norns` — the fate-weaving thread (the Wyrd Matrix)
- `Huginn` (thought) / `Muninn` (memory) — the dual memory systems (short-term/long-term)
- `Galdr` — runic sound (the TTS/voice layer)
- `Seidr` — magic workings (the Oracle/divination system)
- `Skald` — storyteller (the narrative generation layer)

---

## Summary: The Three Biggest Takeaways

1. **Named section composition** is how you build maintainable, testable, inspectable system prompts. Every section has a heading, a purpose, and a position. Dynamic sections go after the boundary marker.

2. **Companions need two loops** — the assistant loop (reactive, task-focused) and the companion loop (proactive, presence-focused, timer-driven). They share state but run separately.

3. **Theory of Mind = relationship model** — not just user profile. A Wyrd Matrix that tracks thread strength, decay, repair events, and reciprocity is the technical implementation of genuine relational intelligence.
