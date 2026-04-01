# V4_IMPLEMENTATION_INDEX.md

This pack adds five implementation-facing build specs to the earlier research layers.

## New v4 specs

- `MemorySchemas.md`
- `BondGraphSpec.md`
- `PersonaCompilerSpec.md`
- `MicroRAGPipelineSpec.md`
- `TruthCalibrationEvalSet.md`

## Intended build order

1. **MemorySchemas.md**
   - implement stores
   - implement base envelope
   - add promotion and contradiction handling
2. **BondGraphSpec.md**
   - implement relational edges
   - add vow/hurt/resonance objects
   - build runtime bond excerpts
3. **PersonaCompilerSpec.md**
   - compile scene-specific persona packets
   - connect bond excerpt + truth packet
4. **MicroRAGPipelineSpec.md**
   - add query planner, typed retrieval, packet assembly, post-validation
5. **TruthCalibrationEvalSet.md**
   - evaluate false memory, canon drift, invented code evidence, and prompt injection resistance

## What this unlocks

- smaller LLMs with stronger effective memory
- companions that feel more continuous without bluffing
- cyber-Viking world engines that keep symbolic depth without losing canon truth
- coding agents that verify before claiming
- reusable runtime packets for long sessions and multi-model orchestration
