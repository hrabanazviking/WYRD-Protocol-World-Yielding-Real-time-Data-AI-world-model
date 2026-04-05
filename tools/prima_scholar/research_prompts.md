# Prima Scholar — WYRD Research Prompt Library

A collection of reusable Claude Code prompts for WYRD Protocol development and research.
Invoke with `/research <prompt-name>` or paste directly.

---

## World Design Prompts

### new-entity
```
Design a new WYRD ECS entity for <NAME>.
Include: NameComponent, IdentityComponent, SpatialComponent (location: <LOCATION_ID>),
HealthComponent (if mortal), FactionComponent (if affiliated), custom components if needed.
Output as a YAML entity block compatible with configs/worlds/*.yaml.
```

### new-location
```
Design a new Yggdrasil location node for <NAME> (type: zone|region|location|sub_location).
Include: id, name, description, parent_id, any child_ids.
Output as a YAML location block.
```

### spread-reading
```
Perform a 3-rune Elder Futhark reading for <CHARACTER> on the question: <QUESTION>.
Use the Oracle's context data. Map each rune to a WorldContextPacket field.
Interpret: past influence → current state → future vector.
Ground the reading in what WYRD actually knows about this character.
```

---

## Integration Design Prompts

### new-bridge
```
Design a WyrdForge integration bridge for <TARGET_PLATFORM>.
Target: <describe the platform, scripting language, HTTP capabilities>
Based on the existing pattern in integrations/<CLOSEST_EXISTING>/.
Output: file structure, key classes/functions, HTTP wire-up pattern, test strategy.
```

### review-bridge
```
Review the integration at integrations/<PLATFORM>/wyrdforge/ for:
1. Persona ID normalization correctness
2. JSON body builder correctness (valid JSON, all fields present)
3. Fire-and-forget pattern for push operations
4. Error handling / silent fallback
5. Test coverage gaps
Output: issues found (with file:line), suggested fixes.
```

---

## Debugging Prompts

### trace-query
```
Trace a /query request for persona_id=<ID>, user_input=<INPUT> through the full stack:
WyrdHTTPServer → PassiveOracle → WorldContextPacket → PromptBuilder → OllamaConnector → response.
Identify which files handle each step and what data transforms happen.
```

### debug-memory
```
The PersistentMemoryStore is behaving unexpectedly: <DESCRIBE SYMPTOM>.
Check: SQLite schema (persistence/memory_store.py), FTS5 index, MemoryPromoter thresholds,
ContradictionDetector logic. Output: likely cause, specific lines to check, suggested fix.
```

---

## Architecture Prompts

### explain-oracle
```
Explain the PassiveOracle's 9 query types to someone familiar with ECS but new to WYRD.
For each: what it queries, what it returns, when an AI would use it.
```

### explain-yggdrasil
```
Explain the Yggdrasil spatial hierarchy (Zone → Region → Location → Sub-location).
Include: how entities are placed, how the oracle resolves paths, how the TUI displays it.
Use the thornholt world as an example.
```

### explain-bifrost
```
Explain the BifrostBridge abstraction and how it enables engine-agnostic integration.
Walk through: BifrostBridge ABC → PythonRPGBridge → WyrdHTTPServer → SDK layer.
Then explain how a new engine integration fits into this chain.
```

---

## Code Generation Prompts

### gen-world-yaml
```
Generate a WYRD world YAML for a <SETTING> (e.g. "Viking mead hall", "space station").
Include: 2 zones, 4 regions, 8 locations, 6 named NPC entities with components,
3 items of note. Follow the schema in configs/worlds/thornholt.yaml exactly.
```

### gen-tests
```
Generate Python pytest tests for the functions in <FILE_PATH>.
Follow the pattern in integrations/minecraft/wyrdforge/tests/test_wyrdforge.py:
class-based, one method per case, descriptive names, no mocking of pure functions.
Target: <N> tests covering normal cases, edge cases, and error paths.
```
