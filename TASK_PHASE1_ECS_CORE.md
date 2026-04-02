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
- [x] ecs/entity.py
- [x] ecs/component.py + registry
- [x] ecs/world.py
- [x] ecs/system.py + WorldRunner
- [x] ecs/yggdrasil.py
- [x] ecs/components/ (identity, spatial, physical, character)
- [x] ecs/systems/ (presence, state_transition)
- [x] persistence/world_store.py
- [x] loaders/world_loader.py
- [x] configs/worlds/thornholt.yaml
- [x] wyrd_world_cli.py
- [x] tests/ (4 test files — 106 tests total)
- [x] pytest — 106/106 passing
- [x] Commit + push

## Status: COMPLETE
