# Claude Code Leak Research — Index
> Source: github.com/hrabanazviking/claw-code (fork of instructkr/claw-code)
> Purpose: Learn architectural patterns and ideas. All implementations in this codebase are original.
> Date researched: 2026-03-31

## What Was Studied
- 1902 original TypeScript source files (mapped via snapshot JSONs)
- 35 subsystems fully inventoried
- 184 tools + 207 commands catalogued
- Rust runtime implementation read in full (prompt.rs especially)
- Python port mirror analyzed for architecture patterns

---

## Research Files

| # | File | Contents |
|---|---|---|
| 01 | `01_architecture_overview.md` | Full system architecture, boot sequence, turn loop, routing algorithm, session persistence |
| 02 | `02_system_prompt_engineering.md` | System prompt builder, named sections, dynamic boundary, CLAUDE.md loading, actual section text |
| 03 | `03_tool_system_architecture.md` | All 184 tools analyzed, tool anatomy pattern, agent tools, security layers, multi-agent tools |
| 04 | `04_memory_and_sessions.md` | memdir system, SessionMemory service, TranscriptStore, HistoryLog, compaction, session persistence |
| 05 | `05_personality_companion_system.md` | Buddy/companion system, Output Style personas, voice mode, notification hooks, ToM patterns |
| 06 | `06_hooks_skills_plugins.md` | All 20 bundled skills analyzed, permission hooks, plugin architecture, constants deep-dive |
| 07 | `07_multi_agent_swarm_architecture.md` | Full swarm system, agent lifecycle, coordinator mode, remote execution, communication patterns |
| 08 | `08_utils_services_patterns.md` | 564 utils catalogued, services deep-dive, performance patterns, Rust runtime utilities |
| 09 | `09_theory_of_mind_personality.md` | ToM architecture synthesis, companion loop design, Wyrd Matrix thread model, circumplex affect model |
| 10 | `10_cyber_viking_applications.md` | All patterns mapped to your projects: Sigrid, NorseSagaEngine, MindSpark, OpenClaw rune skill |
| 11 | `11_rust_runtime_deep_dive.md` | Session JSON format, ConversationRuntime generics, turn loop (max 16 iter), permission policy, pricing |
| 12 | `12_mcp_protocol_architecture.md` | JSON-RPC 2.0 wire format, all MCP methods, 6 transport types, OAuth flow, Sigrid-as-MCP blueprint |
| 13 | `13_api_streaming_caching_cost.md` | MessageRequest structure, 4 token types, cache break-even, streaming event sequence, cost optimization |
| 14 | `14_config_settings_feature_flags.md` | 3-tier config hierarchy, hooks schema (6 events), feature flags, settings keys, constants reference |
| 15 | `15_norse_mythology_data_structures.md` | Nine Worlds graph, all 24 Elder Futhark runes as dataclasses, Norn architecture, deity database, Yggdrasil |
| 16 | `16_ai_companion_psychology.md` | Circumplex affect, attachment theory, SDT, ToM levels, Gottman repair, Dual Process, SigridMind class |
| 17 | `17_local_model_integration.md` | LiteLLM routing, Ollama model tiers, Axolotl fine-tune config, TTS stack, Norse pronunciation dictionary |
| 18 | `18_cybersecurity_patterns.md` | 6-layer bash security, injection defenses, memory tamper detection, encryption at rest, audit logging |
| 19 | `19_prompt_engineering_cookbook.md` | 15 recipes: identity anchor, structured output tool, mode switching, anti-drift, Norse voice register |
| 20 | `20_wyrd_protocol_ecs_worldmodel.md` | ECS world model, all component definitions, WyrdMatrix, OrlögSystem, initialize_sigrid() entity |
| 21 | `21_orlog_engine_full_design.md` | Complete original Ørlög Engine: all 5 state machines with full code, tick loop, prompt builder, memory layer |
| 22 | `22_norsesagaengine_agent_architecture.md` | NSE as multi-agent coordinator: NarrativeAgent, DialogueAgent, OracleAgent, SkaldAgent, EventSystem |
| 23 | `23_mindspark_phase7_8_architecture.md` | MindSpark Phase 7 (setup wizard, backend adapters, chat interface) + Phase 8 (diagnostics, circuit breaker) |
| 24 | `24_master_synthesis_reference.md` | Master reference: decision tables, mode guide, security checklist, anti-patterns, rune lookup, file structure |

---

## Top 10 Highest-Value Discoveries

1. **SystemPromptBuilder** — named section composition with `SYSTEM_PROMPT_DYNAMIC_BOUNDARY` marker separating static identity from dynamic state

2. **Output Style system** — complete persona replacement via a named section; the model identity IS the output style, not a modifier on top

3. **Buddy/Companion subsystem** — separate from assistant; has its own sprite, prompt, notification hook, and behavior loop

4. **Agent swarm architecture** — full production swarm: coordinator mode, worker agents, team memory, scheduled cron agents, remote triggers

5. **`speculation.ts`** — speculative pre-computation of likely next responses; ToM as a performance optimization

6. **`memoryAge.ts`** — memories have age and decay; stale memories are excluded from context automatically

7. **`findRelevantMemories.ts`** — memory is semantically searched, not loaded wholesale; only relevant memories consume context window

8. **`CompanionSprite.tsx`** — visual companion presence is architecturally separate from text output

9. **`skillify.ts`** — skills can create new skills; self-extending capability system

10. **`permissionLogging.ts`** — every permission decision is logged for audit; consent is a first-class architectural concern

---

## Key Constants Worth Noting
```
MAX_INSTRUCTION_FILE_CHARS = 4,000   (per CLAUDE.md file)
MAX_TOTAL_INSTRUCTION_CHARS = 12,000 (total across all CLAUDE.md files)
max_turns = 8 (default)
compact_after_turns = 12
max_budget_tokens = 2,000 (app-level, separate from LLM context window)
FRONTIER_MODEL_NAME = "Claude Opus 4.6"
```

---

## Files NOT in This Research
The Python port is a **mirror** — it reflects the structure but not the full implementation of the original TypeScript. The actual LLM call logic, full streaming implementation, and complete tool implementations exist in the TypeScript archive that is not in this repo. What IS here gives us the architecture skeleton and enough to reconstruct the patterns.
