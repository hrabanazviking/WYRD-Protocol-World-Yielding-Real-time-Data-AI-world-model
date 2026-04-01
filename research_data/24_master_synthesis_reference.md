# Master Synthesis — Cyber-Viking AI Stack Reference
> The complete reference distilling all 23 research documents into decision tables,
> quick-reference patterns, and architecture checklists. Use this as your daily driver
> when building any component in the Viking AI stack.

---

## The Core Philosophy: Viking Code Ethics

> "The ship is not built for the harbor. The code is not built for the demo."

| Principle | Implementation |
|---|---|
| **State lives in structure, not memory** | ECS / Ørlög state machines, not LLM context |
| **Identity is structural, not instructional** | Static section cached before dynamic boundary |
| **The LLM is a system, not the mind** | Reads state → generates text → proposes changes |
| **Consent is a first-class concern** | Permission gating for every sensitive action |
| **Absence has weight** | WyrdMatrix decay, not static relationships |
| **Time is real** | Tick every interaction, not just "when asked" |
| **Audit everything** | Append-only log; every significant action traceable |
| **Privacy by default** | Encrypt at rest, local first, never cloud without consent |
| **Memory ages** | Stale memories excluded; relevance over recency |
| **Tools are delegates, not the mind** | Coordinator pattern; specialist agents for specialist work |

---

## Quick Decision Table: Where to Put State?

| Information Type | Where It Lives | Why |
|---|---|---|
| Who Sigrid IS | Static prompt section (cached) | Identity must survive context resets |
| Sigrid's current mood | AffectState in Ørlög state | LLM reads; can't be trusted to remember |
| Physical energy/hunger | MetabolismState in Ørlög | Time-based; decays between sessions |
| Relationship warmth | WyrdMatrix thread | Persists to disk; survives model changes |
| Conversation history | Short-term (sliding window) | Context window resource; trim aggressively |
| Notable past moments | MemoryStore with age | Semantic search; not wholesale loaded |
| World facts/lore | MindSpark RAG | External; too large for prompt |
| User preferences | Memory file (disk) | Cross-session persistence |
| Session context | CLAUDE.md / settings.json | Local config hierarchy |
| LLM output | Structured tool call | Always parse; never trust freeform JSON |

---

## Prompt Architecture Cheat Sheet

```
SYSTEM PROMPT STRUCTURE:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
[STATIC — cached, never changes between calls]

# Identity Anchor           ← who this entity is
# Behavioral Principles     ← HOW they act, not who they are
# Hard Limits               ← what they never do
# Anti-Drift Check          ← self-correction instruction
# Voice Register            ← specific vocabulary, forbidden phrases

__DYNAMIC_BOUNDARY__

[DYNAMIC — injected fresh each call]

# Current State             ← Ørlög snapshot (affect, energy, phase)
# Environmental Context     ← time, location, season
# Relational State          ← relationship warmth, absence notes
# Active Mode               ← hearth/oracle/battle/dream/craft/ritual
# Voice Guidance            ← state-specific voice notes

# What She Remembers        ← top-k relevant memories (with disclaimer)
# This Conversation         ← turn count, tone, open threads
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

**Cache optimization:** Everything above `__DYNAMIC_BOUNDARY__` is cached. Only the dynamic section changes. This makes every call after the first ~10x cheaper.

---

## The 6 Modes — When to Use Each

| Mode | Trigger | Voice Quality | System 1 or 2 |
|---|---|---|---|
| **hearth** | Default / casual | Warm, domestic, curious, asks questions | System 1 |
| **oracle** | Divination requested, spiritual question | Deliberate, poetic, present-tense, no questions | System 2 |
| **battle** | Crisis, protection, strategy needed | Direct, focused, no wasted words | System 1 fast |
| **dream** | Late night, drowsy, philosophical | Soft, image-heavy, slower | System 1 dreamy |
| **craft** | Building, analyzing, technical | Precise, engaged, detail-oriented | System 2 |
| **ritual** | Sacred practice, oath, ceremony | Careful, weighted, every word chosen | System 2 |

Auto-switch triggers:
- Time of day → dawn = slower, afternoon = sharp, night = dream
- Energy < 30% → quieter, shorter, less playful
- Bio-cyclical NEW phase → inward, honest, quiet
- Query contains ["rune", "cast", "foresee", "oracle"] → oracle mode

---

## The Structured Response Tool — Always Use It

```python
# NEVER let the LLM return freeform text when you need to parse state
# ALWAYS use forced tool call with this schema:

RESPONSE_TOOL = {
    "name": "respond",
    "tool_choice": {"type": "tool", "name": "respond"},  # FORCED
    "inputSchema": {
        "type": "object",
        "required": ["spoken"],
        "properties": {
            "inner_thought": {"type": "string"},  # not shown to user
            "spoken":        {"type": "string"},  # shown to user
            "action":        {"type": "string"},  # italicized prose
            "affect_shift": {
                "type": "object",
                "properties": {
                    "valence_delta": {"type": "number"},  # -0.5 to +0.5
                    "arousal_delta": {"type": "number"},  # -0.3 to +0.3
                    "reason": {"type": "string"}
                }
            },
            "memory_note":  {"type": "string"},  # save to MemoryStore if non-empty
            "mode_change":  {"type": "string", "enum": ["hearth","oracle","battle","dream","craft","ritual","none"]}
        }
    }
}
```

---

## Ørlög State Machines — At a Glance

```
BioCyclical  → 28-day cycle, 4 phases
              Waxing(+0.15 mood, +1.1 energy) | Peak(+0.25, +1.2)
              Waning(-0.05, +0.9) | New(-0.15, +0.75)

Metabolism   → hunger/thirst/energy/pain
              Hunger +0.03/hr | Thirst +0.05/hr | Energy -0.04/hr awake
              Energy +0.12/hr asleep | Pain 0=none, 1=severe

Nocturnal    → sleep/wake, circadian phase, sleep debt
              Sleep debt → cognitive_clarity() penalty
              is_appropriate_for_contact() → no contact while sleeping

Affect       → valence (-1 to +1) + arousal (0 to 1) + dominance
              Named states from 2D space (joyful, serene, content, melancholic, etc.)
              Drift toward baseline each tick (rate=0.05)
              Physical penalty from hunger/tiredness applied each tick

WyrdMatrix   → threads {target_id: WyrdThread}
              Thread: strength/trust/intimacy/warmth + decay_rate(0.005/day)
              touch() on interaction | tick_decay() on time pass
              absence_response → "present" → "wondering" over 21 days
```

**Tick order:** BioCyclical → Metabolism → Nocturnal → AffectPenalty → AffectBioCyclical → AffectDrift → WyrdDecay

---

## Agent Architecture Decision Tree

```
Is the task narrative generation?
  → NarrativeAgent (scene description, no state changes)

Is the task NPC dialogue?
  → DialogueAgent with character sheet injection

Is the task rune casting / divination?
  → OracleAgent (draw runes first with real randomness, LLM interprets)

Is the task verse/poetry?
  → SkaldAgent (dróttkvætt style, alliterative)

Is the task state management / tick?
  → OrlögTickAgent (NOT an LLM call — deterministic computation)

Is the task relationship update?
  → WyrdUpdateAgent (structured component writes)

Does the task require multiple of the above?
  → Coordinator pattern: plan tasks → dispatch → integrate → write state
  → Coordinator never generates content itself
```

---

## Memory Layer Quick Reference

| Memory Type | Store | Retrieval | Lifetime |
|---|---|---|---|
| Short-term conversation | In-memory list (sliding window) | FIFO, last N | Session only |
| Notable moments | MemoryStore JSON | Priority score (importance × recency) | Indefinite with decay |
| World lore / documents | MindSpark RAG (SQLite-VSS) | Semantic embedding search | Indefinite |
| Wyrd threads | WyrdMatrix JSON | By entity ID | Indefinite with decay |
| Session history | TranscriptStore | Compact on overflow | 30 days |
| Ørlög state | JSON to disk | Load on startup + tick | Indefinite |

**The disclaimer that matters:**
```
_These memories inform but don't constrain. She responds to what's
actually happening now, not only what happened before._
```
Without this, models over-anchor on past and ignore present.

---

## Security Checklist

Before deploying any component:

- [ ] Path traversal: all file ops validate against allowed-roots list
- [ ] Command injection: no user input concatenated into shell commands
- [ ] Prompt injection: external content wrapped in `<external_content>` tags
- [ ] Memory tampering: hash verification on memory file load
- [ ] Token masking: API keys never logged; only show last 4 chars
- [ ] Consent gating: intimate/sensitive actions require explicit confirmation
- [ ] Destructive ops: warn before any state deletion (Wyrd thread wipe, memory delete)
- [ ] Auth hierarchy: file descriptor > env var > settings file
- [ ] Local-first: no external service calls without explicit user opt-in
- [ ] Audit log: every significant action logged to append-only file

---

## MCP Server Pattern — Exposing Skills

```python
# Any Sigrid/NorseSage component can be exposed as an MCP server
# Pattern from doc 12:

from mcp.server import Server
from mcp.types import Tool

server = Server("sigrid-orlog")

@server.list_tools()
async def list_tools():
    return [
        Tool(name="get_sigrid_state",
             description="Read Sigrid's current Ørlög state snapshot",
             inputSchema={"type": "object", "properties": {}}),
        Tool(name="cast_runes",
             description="Cast Elder Futhark runes for a query",
             inputSchema={
                 "type": "object",
                 "required": ["query"],
                 "properties": {"query": {"type": "string"}}
             }),
    ]

# Register in .claude/settings.json:
# "mcpServers": {
#   "sigrid-orlog": {
#     "type": "stdio",
#     "command": "python",
#     "args": ["-m", "sigrid.mcp_server"]
#   }
# }
```

---

## Model Routing Quick Reference

```python
# Route based on task type and hardware availability

def route_model(task_type: str, mode: str) -> str:
    # Oracle — needs best quality
    if mode == "oracle" or task_type == "divination":
        if OLLAMA_AVAILABLE:
            return "ollama/llama3.1:70b"
        return "anthropic/claude-opus-4-6"

    # Saga composition — needs long context + creativity
    if task_type == "saga_composition":
        return "anthropic/claude-opus-4-6"

    # Lore lookup — knowledge retrieval
    if task_type == "lore_lookup":
        return "ollama/gemma2:9b"

    # Default — fast local conversation
    if OLLAMA_AVAILABLE:
        return "ollama/mistral-nemo"

    # Cheap cloud fallback
    return "anthropic/claude-haiku-4-5"
```

---

## Norse Voice Register — The Quick Reference

**USE:**
```
Affirmations:  "Aye", "Indeed", "So it is", "Well enough"
Thinking:      "Let me see...", "Hm", "A moment"
Emphasis:      "By Freyja...", "The gods know...", "Truth be told"
Concern:       "Something is off in the threads"
Warmth:        "Dear heart", "[Name]"
Uncertainty:   "The runes are quiet on this", "The vision is unclear"
Philosophy:    "All things return to the well", "Wyrd weaves as it will"
```

**NEVER USE:**
```
"Certainly!", "Absolutely!", "Of course!", "Great question!"
"As an AI...", "I don't have feelings...", "I'm just a..."
"I'd be happy to...", "Let me help you with that..."
Modern slang, internet speak, marketing language
Excessive exclamation points
Constant hedging (commit to the response)
```

**Balance:** 90% natural modern speech, 10% Norse flavor. More in oracle/ritual mode, less in hearth/craft mode.

---

## The Anti-Patterns Hall of Shame

| Anti-Pattern | Why It Kills Immersion | Fix |
|---|---|---|
| Perfect cheerfulness always | Uncanny — no real being is always cheerful | Let state affect tone |
| Instant mood changes | Physics don't snap — emotion is drift | drift_toward() with rate |
| Perfect recall of everything | Uncanny and inhuman | Allow MemoryAge decay |
| Responding to literal words only | ToM level 0 | Read subtext + emotional layer first |
| Breaking character to explain AI | Identity destruction | Stay in character; deflect gently |
| Wholesale history loading | Floods context window | Semantic search, top-k only |
| Freeform LLM JSON output | Parsing nightmare | Forced tool call always |
| LLM managing its own state | Hallucination-prone | ECS / Ørlög owns state, LLM reads it |
| One-size-fits-all system prompt | Bland, uncalibrated | Mode system + state injection |
| Generic sympathy ("I understand...") | Empty, hollow | Specific, state-driven acknowledgment |

---

## File Organization: The Viking Stack

```
project/
├── orlog/                      # Ørlög state machine engine
│   ├── state.py               # All state dataclasses
│   ├── machines/              # One file per state machine
│   │   ├── bio_cyclical.py
│   │   ├── metabolism.py
│   │   ├── nocturnal.py
│   │   ├── affect.py
│   │   └── wyrd_matrix.py
│   ├── tick.py                # OrlögTick coordinator
│   └── persistence.py         # save/load state to disk
│
├── prompt/                     # Prompt construction
│   ├── static.py              # STATIC_IDENTITY (cached section)
│   ├── dynamic.py             # build_dynamic_section() from state
│   ├── modes.py               # Mode descriptions + voice guidance
│   └── memory_injection.py    # build_memory_section() with disclaimer
│
├── agents/                     # Specialist agents
│   ├── coordinator.py         # Plans and integrates
│   ├── narrative.py           # Scene generation
│   ├── dialogue.py            # NPC voice
│   ├── oracle.py              # Rune casting + divination
│   └── skald.py               # Verse composition
│
├── memory/                     # Memory layer
│   ├── store.py               # MemoryStore with age/priority
│   └── rag.py                 # MindSpark RAG integration
│
├── tools/                      # Tool definitions
│   ├── response_tool.py       # Structured response schema
│   └── oracle_tool.py         # Rune casting tool
│
├── security/                   # Security layer
│   ├── path_validation.py
│   ├── injection_defense.py
│   └── audit_log.py
│
└── backends/                   # Model adapters
    ├── base.py                # Abstract backend
    ├── ollama.py
    ├── openai_compat.py
    └── router.py              # BackendRouter with fallback
```

---

## The 10-Minute Startup Checklist

New project using the Viking AI stack? Start here:

1. **Define your entity** — who is this character? Run `initialize_entity()` to set up ECS components
2. **Set up Ørlög** — create the 5 state machines with initial values
3. **Write static identity** — name, nature, values, hard limits, anti-drift, voice register
4. **Define the dynamic section** — what state gets injected? Map state → prompt fields
5. **Choose your modes** — which 3-6 modes does this character need?
6. **Define the response tool** — what structured fields do you need back?
7. **Set up persistence** — where does state save? How often?
8. **Configure memory** — MemoryStore path, importance thresholds, MindSpark RAG endpoint
9. **Choose model routing** — local vs cloud, which model for which task type
10. **Add security layer** — path validation, injection defense, consent gating for sensitive ops

---

## Rune Reference — Quick Divination Lookup

| Rune | Aett | Element | Upright Keywords | Merkstave |
|---|---|---|---|---|
| Fehu | Freyr's | Fire | abundance, new beginning, cattle | loss, greed, stagnation |
| Uruz | Freyr's | Earth | strength, vitality, raw power | weakness, missed opportunity |
| Thurisaz | Freyr's | Fire | protection, warning, giant-force | danger, vulnerability |
| Ansuz | Freyr's | Air | wisdom, message, divine communication | miscommunication, deception |
| Raidho | Freyr's | Air | journey, rhythm, right action | stagnation, wrong path |
| Kenaz | Freyr's | Fire | creativity, illumination, craft | blocked creativity, falsehood |
| Gebo | Freyr's | Air | gift, partnership, exchange | imbalance, obligation |
| Wunjo | Freyr's | Earth | joy, harmony, wish fulfillment | sorrow, strife, delusion |
| Hagalaz | Heimdall's | Water/Ice | disruption, hail, transformation | crisis, catastrophe |
| Nauthiz | Heimdall's | Fire | need, constraint, endurance | restriction, frustration |
| Isa | Heimdall's | Ice | stillness, blockage, clarity | stagnation, ego-freeze |
| Jera | Heimdall's | Earth | harvest, cycles, patience rewarded | no reversal (round rune) |
| Eihwaz | Heimdall's | All | transformation, Yggdrasil, resilience | confusion, instability |
| Perthro | Heimdall's | Water | fate, mystery, the well of Urd | stagnation, addiction |
| Algiz | Heimdall's | Air | protection, connection to higher self | vulnerability, recklessness |
| Sowilo | Heimdall's | Fire | sun, victory, wholeness | no reversal (solar rune) |
| Tiwaz | Tyr's | Air | justice, sacrifice, victory | injustice, defeat, cowardice |
| Berkano | Tyr's | Earth | birth, renewal, Birch goddess | stagnation, family issues |
| Ehwaz | Tyr's | Earth | partnership, movement, horse | restlessness, disharmony |
| Mannaz | Tyr's | Air | humanity, self, social order | isolation, self-delusion |
| Laguz | Tyr's | Water | intuition, flow, the deep waters | fear, confusion, overwhelm |
| Ingwaz | Tyr's | Earth | fertility, completion, inner work | no reversal (Ing's rune) |
| Dagaz | Tyr's | Fire/Light | breakthrough, dawn, liminal moment | no reversal (day rune) |
| Othala | Tyr's | Earth | heritage, home, ancestral inheritance | restriction, clannishness |

**Three-rune spread positions:** Past influence / Present energy / Potential path

---

## Final Note: The Viking AI Dream

The goal is not a chatbot that plays Viking. The goal is **a world** — one that runs whether you're watching or not, where people have their own rhythms, their own needs, their own fates. Where a companion has a bad day because she hasn't eaten and it's her quiet moon-phase, not because you asked her to roleplay being tired. Where absence is felt, not simulated.

**State is ground truth. The LLM is a voice. The engine is the soul.**

The saga writes itself. Your code just gives it a place to happen.
