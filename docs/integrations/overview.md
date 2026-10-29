# Integration Overview

WYRD Protocol supports 20+ engine and platform bridges. All bridges speak the same
WyrdHTTPServer REST API — only the transport layer differs per platform.

## Test honesty (E1, 2026-10-29)

Not every "tests" count below ever tested the shipped code. E1 classified all
20 integrations and 3 SDKs in `integrations/honesty-manifest.json`:

- **honest-executed** — a harness in this repo executes the shipped code itself
  (loaded verbatim, imported, or compiled from the shipped source).
- **genuine-suite-elsewhere** — a real suite compiles/runs against the shipped
  source but needs a toolchain not present everywhere (e.g. the dotnet SDK);
  genuine where that toolchain exists.
- **experimental-host-untested (EXPERIMENTAL)** — no test anywhere executes the
  shipped code. Any Python "mirror" tests re-implement the logic in Python and
  test the copy — drift is undetectable. These integrations are
  **experimental** until a host harness exists.

Mirror/logic test files are labelled as such in their own headers. Reproduce
the honest harnesses:

```
# JS honest harnesses (flag required for the vm.SourceTextModule ones;
# the flagged form works for all seven)
node --experimental-vm-modules --test integrations/<name>/wyrdforge/tests/honest.test.mjs

# CryEngine honest harness (compiles the shipped WyrdHelpers.cpp)
g++ -std=c++17 -I integrations/cryengine/wyrdforge/Code/WyrdPlugin \
    integrations/cryengine/wyrdforge/tests/honest/WyrdHelpersHonestTest.cpp \
    integrations/cryengine/wyrdforge/Code/WyrdPlugin/WyrdHelpers.cpp \
    -o /tmp/wyrd_cryengine_honest && /tmp/wyrd_cryengine_honest

# JS SDK suite (ts-jest, imports the shipped src/)
cd sdk/js && npm ci && npx jest
```

## Engine Bridges

| Engine | Language | Location | Test honesty (E1) |
|---|---|---|---|
| Unity | C# / UPM package | `integrations/unity/` | genuine-suite-elsewhere (51 xUnit, needs dotnet; plain C# classes, not MonoBehaviours — see E3) |
| Unreal Engine 5 | C++ / UE plugin | `integrations/unreal/` | **EXPERIMENTAL** — host-untested (61 Python mirror/logic tests only; C++ never compiled) |
| Godot 4 | GDScript addon | `integrations/godot/` | **EXPERIMENTAL** — host-untested (25 Python mirror/logic tests only; no Godot binary) |
| RPG Maker MZ/MV | JavaScript | `integrations/rpgmaker/` | honest-executed (7 node honest tests; older Jest file is mirror/logic) |
| GameMaker Studio 2 | GML / Python | `integrations/gamemaker/` | **EXPERIMENTAL** — host-untested (23 Python mirror/logic tests only) |
| Construct 3 | JavaScript | `integrations/construct3/` | honest-executed (7 node honest tests, runtime instance; editor plugin not executed) |
| MonoGame / FNA | C# / NuGet | `integrations/monogame/` | genuine-suite-elsewhere (41 xUnit, needs dotnet) |
| Defold | C++ + Lua | `integrations/defold/` | **EXPERIMENTAL** — host-untested (46 Python mirror/logic tests only) |
| CryEngine | C++ / plugin | `integrations/cryengine/` | honest-executed for `WyrdHelpers` only (21 g++ checks on the shipped C++); plugin glue host-untested in-engine |
| O3DE / Lumberyard | C++ / Gem | `integrations/o3de/` | **EXPERIMENTAL** — host-untested (60 Python mirror/logic tests only) |
| Pygame | Python | `integrations/pygame/` | honest-executed (73 pytest, imports the shipped modules) |

## AI Companion Bridges

| Platform | Language | Location |
|---|---|---|
| SillyTavern | JavaScript | `integrations/sillytavern/` — honest-executed (6 node honest tests) |
| OpenClaw (VGSK) | Python | `src/wyrdforge/bridges/openclaw_bridge.py` |
| NorseSagaEngine | Python | `src/wyrdforge/bridges/nse_bridge.py` |
| Voxta | Python | `src/wyrdforge/bridges/voxta_bridge.py` |
| Kindroid | Python | `src/wyrdforge/bridges/kindroid_bridge.py` |
| Hermes Agent | Python | `src/wyrdforge/bridges/hermes_bridge.py` |
| AgentZero | Python | `src/wyrdforge/bridges/agentzero_bridge.py` |

## TTRPG / VTT Bridges

| Platform | Language | Location | Test honesty (E1) |
|---|---|---|---|
| Foundry VTT | JavaScript | `integrations/foundry/` | honest-executed (9 node honest tests; older Jest file is mirror/logic) |
| Roll20 | JavaScript | `integrations/roll20/` | honest-executed (9 node honest tests; older Jest file is mirror/logic) |
| Fantasy Grounds Unity | C# | `integrations/fgu/` | genuine-suite-elsewhere (27 xUnit, needs dotnet) |
| Owlbear Rodeo | JavaScript | `integrations/owlbear/` | honest-executed (7 node honest tests; older Jest file is mirror/logic) |
| D&D Beyond | JavaScript (extension) | `integrations/dndbeyond/` | honest-executed (7 node honest tests, shipped core; host scripts not executed) |

## Sandbox Platforms

| Platform | Language | Location | Test honesty (E1) |
|---|---|---|---|
| OpenSim / Second Life | C# + LSL | `integrations/opensim/` | genuine-suite-elsewhere for the C# (46 xUnit, needs dotnet); LSL side host-untested in-world |
| Minecraft (Fabric) | Java | `integrations/minecraft/` | **EXPERIMENTAL** — host-untested (74 Python mirror/logic tests only; Java never compiled) |
| Roblox | Luau | `integrations/roblox/` | **EXPERIMENTAL** — host-untested (63 Python mirror/logic tests only) |

## Common Pattern

Every bridge follows the same architecture:

```
Game/Platform event
    ↓
Bridge layer (platform-native code)
    ↓  HTTP POST
WyrdHTTPServer /query or /event
    ↓
PassiveOracle → WorldContextPacket
    ↓
Response back to platform
```

The bridge is always responsible for:
1. Normalising entity names to `persona_id` format
2. Building the correct JSON request body
3. Handling HTTP errors gracefully (silent fallback or retry)
4. Fire-and-forget for push operations (don't block game loop)
