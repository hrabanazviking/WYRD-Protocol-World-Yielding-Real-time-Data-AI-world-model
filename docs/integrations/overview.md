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

E3 (2026-10-29) then made the host layers truthful: Unity gained real
MonoBehaviours, `.asmdef` files, and the editor inspector; OpenSim gained
a real `IRegionModuleBase` region module in a separate deployment project;
CryEngine's client logic was implemented host-free (its transport stays a
labelled stub); O3DE's previously declaration-only helpers were
implemented (its component HTTP layer stays a labelled stub). The rows
below and the manifest state exactly what is and is not verified.

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

# CryEngine client-core honest harness (E3; also compiles WyrdPlugin.cpp)
g++ -std=c++17 -I integrations/cryengine/wyrdforge/Code/WyrdPlugin \
    integrations/cryengine/wyrdforge/tests/honest/WyrdClientCoreHonestTest.cpp \
    integrations/cryengine/wyrdforge/Code/WyrdPlugin/WyrdClientCore.cpp \
    integrations/cryengine/wyrdforge/Code/WyrdPlugin/WyrdHelpers.cpp \
    integrations/cryengine/wyrdforge/Code/WyrdPlugin/WyrdPlugin.cpp \
    -o /tmp/wyrd_cryengine_core_honest && /tmp/wyrd_cryengine_core_honest

# O3DE helpers-core honest harness (E3; compiles the shipped WyrdHelpersCore.cpp)
g++ -std=c++17 -I integrations/o3de/wyrdforge/Code/Source \
    integrations/o3de/wyrdforge/tests/honest/WyrdHelpersCoreHonestTest.cpp \
    integrations/o3de/wyrdforge/Code/Source/WyrdHelpersCore.cpp \
    -o /tmp/wyrd_o3de_honest && /tmp/wyrd_o3de_honest

# JS SDK suite (ts-jest, imports the shipped src/)
cd sdk/js && npm ci && npx jest
```

## Engine Bridges

| Engine | Language | Location | Test honesty (E1) |
|---|---|---|---|
| Unity | C# / UPM package | `integrations/unity/` | genuine-suite-elsewhere (51 xUnit for the plain-C# client, needs dotnet; E3 shipped real MonoBehaviours + .asmdef + editor inspector — the host layer is NOT compiled in Unity, no Unity exists here) |
| Unreal Engine 5 | C++ / UE plugin | `integrations/unreal/` | **EXPERIMENTAL** — host-untested (61 Python mirror/logic tests only; C++ never compiled) |
| Godot 4 | GDScript addon | `integrations/godot/` | **EXPERIMENTAL** — host-untested (25 Python mirror/logic tests only; no Godot binary) |
| RPG Maker MZ/MV | JavaScript | `integrations/rpgmaker/` | honest-executed (7 node honest tests; older Jest file is mirror/logic) |
| GameMaker Studio 2 | GML / Python | `integrations/gamemaker/` | **EXPERIMENTAL** — host-untested (23 Python mirror/logic tests only) |
| Construct 3 | JavaScript | `integrations/construct3/` | honest-executed (7 node honest tests, runtime instance; editor plugin not executed) |
| MonoGame / FNA | C# / NuGet | `integrations/monogame/` | genuine-suite-elsewhere (41 xUnit, needs dotnet) |
| Defold | C++ + Lua | `integrations/defold/` | **EXPERIMENTAL** — host-untested (46 Python mirror/logic tests only) |
| CryEngine | C++ / plugin | `integrations/cryengine/` | honest-executed for `WyrdHelpers` (21 g++ checks) + client core logic (31 g++ checks, E3); **PARTIAL STUB** — no HTTP transport (libcurl) bound and no plugin registration, so not a working in-engine plugin |
| O3DE / Lumberyard | C++ / Gem | `integrations/o3de/` | honest-executed for the helpers logic core (21 g++ checks, E3); **STUB** — the component's HTTP layer (`PostAsync`/`HealthCheck`) is TODO no-ops and the AZ adapter/component have never been compiled |
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
| OpenSim / Second Life | C# + LSL | `integrations/opensim/` | genuine-suite-elsewhere for the C# bridge core (46 xUnit, needs dotnet); E3 shipped a real `IRegionModuleBase` region module (deployment project, needs an OpenSim install to build — not compiled here); LSL side host-untested in-world |
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
