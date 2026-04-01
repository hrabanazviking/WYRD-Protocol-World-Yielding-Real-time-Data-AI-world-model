# v5 implementation subtree

This pack extends v4 with a **drop-in Python starter tree** for memory-heavy, relationship-aware, small-model AI systems.

## What is inside

- `src/wyrdforge/models/` — typed Pydantic models based on the v4 specs
- `src/wyrdforge/services/` — starter services for memory, bond graph logic, persona compilation, micro-RAG, and truth calibration
- `src/wyrdforge/schemas/` — generated JSON Schemas for API/storage validation
- `config/` — example YAML configs
- `examples/` — tiny seed data for testing the pipeline
- `tests/` — smoke tests that exercise the starter flow
- `scripts/generate_json_schemas.py` — regeneration script

## Merge note

Your live repository is not mounted in this environment, so this is packaged as a **merge-ready subtree** rather than patched directly into your repo.

## Suggested destination

```text
src/wyrdforge/
config/
examples/
tests/
```

## Suggested next move

Wire these services into:

- your canonical memory persistence layer
- your entity / world graph
- your LLM routing layer
- your runtime packet assembly before generation
- your eval harness and regression tests
