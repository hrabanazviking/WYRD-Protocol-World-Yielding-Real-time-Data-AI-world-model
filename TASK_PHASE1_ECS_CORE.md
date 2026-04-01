# TASK: Phase 1 — ECS Core Engine (Yggdrasil + World)

**Date:** 2026-04-01
**Branch:** development
**Scope:** Build the central missing piece — the deterministic ECS world model.

## File Targets

### New source files
- `src/wyrdforge/ecs/__init__.py`
- `src/wyrdforge/ecs/entity.py`           — Entity dataclass (UUID, tags, active)
- `src/wyrdforge/ecs/component.py`        — Component base (Pydantic), registry
- `src/wyrdforge/ecs/world.py`            — World container + indexes
- `src/wyrdforge/ecs/system.py`           — System ABC
- `src/wyrdforge/ecs/yggdrasil.py`        — Spatial tree service
- `src/wyrdforge/ecs/components/__init__.py`
- `src/wyrdforge/ecs/components/identity.py`   — Name, Description, Status
- `src/wyrdforge/ecs/components/spatial.py`    — SpatialComponent, ParentComponent
- `src/wyrdforge/ecs/components/physical.py`   — Physical, Inventory
- `src/wyrdforge/ecs/components/character.py`  — PersonaRef, Health, Faction
- `src/wyrdforge/ecs/systems/__init__.py`
- `src/wyrdforge/ecs/systems/presence.py`      — PresenceSystem
- `src/wyrdforge/ecs/systems/state_transition.py`
- `src/wyrdforge/persistence/__init__.py`
- `src/wyrdforge/persistence/world_store.py`   — SQLite backend (stdlib sqlite3)
- `src/wyrdforge/loaders/__init__.py`
- `src/wyrdforge/loaders/world_loader.py`      — YAML world config loader
- `configs/worlds/thornholt.yaml`              — Demo world config
- `wyrd_world_cli.py`                          — Interactive CLI (argparse)

### New test files
- `tests/test_ecs_core.py`
- `tests/test_yggdrasil.py`
- `tests/test_world_store.py`
- `tests/test_world_loader.py`

## Checklist
- [x] Write this task file
- [ ] ecs/entity.py
- [ ] ecs/component.py + registry
- [ ] ecs/world.py
- [ ] ecs/system.py
- [ ] ecs/yggdrasil.py
- [ ] ecs/components/ (identity, spatial, physical, character)
- [ ] ecs/systems/ (presence, state_transition)
- [ ] persistence/world_store.py
- [ ] loaders/world_loader.py
- [ ] configs/worlds/thornholt.yaml
- [ ] wyrd_world_cli.py
- [ ] tests/ (all 4 test files, 60+ tests)
- [ ] pytest passing
- [ ] Commit + push

## Status: IN PROGRESS
