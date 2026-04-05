# WYRD Protocol — Claude Code Configuration

## Project Overview

WYRD Protocol (World-Yielding Real-time Data AI World Model) is an ECS-based external
AI world model. It moves the World Model out of the LLM context window into a deterministic
ECS layer so AI characters query ground truth instead of hallucinating world state.

- **Core engine:** `src/wyrdforge/` — ECS, Yggdrasil, Oracle, TurnLoop, PersistentMemoryStore
- **Integrations:** `integrations/` — 20+ engine bridges (Unity, Unreal, Godot, Foundry, etc.)
- **SDKs:** `sdk/` — JS/TS, C#/.NET, GDScript
- **Tools:** `tools/` — TUI editor, cloud relay
- **Tests:** `pytest` (Python), `dotnet test` (C#), `jest` (JS)

## Development Conventions

### Branch strategy
- `main` — stable releases only
- `development` — active work; all PRs target here

### Test commands
```bash
# Python (all)
python -m pytest tests/ -v

# C# xUnit (per integration)
dotnet test integrations/opensim/wyrdforge/WyrdForge.OpenSim.Tests/
dotnet test integrations/unity/wyrdforge/WyrdForge.Unity.Tests/

# JavaScript (per integration)
cd integrations/foundry/wyrdforge && npm test
```

### Running the server
```bash
python -m wyrdforge.server --port 8765
# or
python -m wyrdforge.bridges.http_api
```

### Running the chat CLI
```bash
python wyrd_chat_cli.py --world configs/worlds/thornholt.yaml --entity sigrid
```

### Running the TUI editor
```bash
python tools/wyrd_tui.py --world configs/worlds/thornholt.yaml
```

## Prima Scholar Workflow (14A)

Claude Code is configured as a **Prima Scholar** for WYRD — a research and development
assistant that understands the full WYRD architecture.

### When adding a new integration:
1. Read `ROADMAP.md` for the target phase spec
2. Read an existing similar integration (e.g. `integrations/monogame/` for C#, `integrations/defold/` for C++)
3. Follow the established patterns:
   - Pure-logic helpers in a separate file (no runtime deps)
   - Python mirror tests for C++/Lua logic; xUnit for C#; Jest for JS
   - Fire-and-forget for push operations; blocking/async for queries
   - Persona ID normalization: lowercase → replace non-alnum with `_` → collapse → strip → truncate 64
4. Write `TASK_wyrd_phase<N>.md`, commit it first, then build

### When researching world model design:
- Check `research/` for the 41 design docs (00-40)
- See `docs/` for the public-facing documentation site
- The Oracle interface (`src/wyrdforge/oracle/passive_oracle.py`) is the canonical query surface

### Key files to know:
| File | Purpose |
|---|---|
| `src/wyrdforge/ecs/world.py` | World entity store |
| `src/wyrdforge/ecs/yggdrasil.py` | Spatial hierarchy |
| `src/wyrdforge/oracle/passive_oracle.py` | 9 query types |
| `src/wyrdforge/bridges/http_api.py` | WyrdHTTPServer |
| `src/wyrdforge/runtime/turn_loop.py` | LLM conversation loop |
| `src/wyrdforge/persistence/memory_store.py` | SQLite+FTS5 memory |
| `wyrd_chat_cli.py` | Interactive CLI |
| `tools/wyrd_tui.py` | Rich TUI editor |
| `tools/wyrd_cloud_relay/relay.py` | Cloud relay server |

## Memory & Context Management

- After every completed phase: update `project_wyrd_status.md` memory file
- After every push: record HEAD commit hash in memory
- Task files (`TASK_wyrd_phase*.md`) are committed before work starts
