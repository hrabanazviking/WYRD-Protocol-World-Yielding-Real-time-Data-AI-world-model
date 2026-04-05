# Integration Overview

WYRD Protocol supports 20+ engine and platform bridges. All bridges speak the same
WyrdHTTPServer REST API — only the transport layer differs per platform.

## Engine Bridges

| Engine | Language | Location | Tests |
|---|---|---|---|
| Unity | C# / UPM package | `integrations/unity/` | 51 xUnit |
| Unreal Engine 5 | C++ / UE plugin | `integrations/unreal/` | 61 Python |
| Godot 4 | GDScript addon | `integrations/godot/` | — |
| RPG Maker MZ/MV | JavaScript | `integrations/rpgmaker/` | 38 Jest |
| GameMaker Studio 2 | GML / Python | `integrations/gamemaker/` | Python |
| Construct 3 | JavaScript | `integrations/construct3/` | 42 Jest |
| MonoGame / FNA | C# / NuGet | `integrations/monogame/` | 41 xUnit |
| Defold | C++ + Lua | `integrations/defold/` | 46 Python |
| CryEngine | C++ / plugin | `integrations/cryengine/` | 61 Python |
| O3DE / Lumberyard | C++ / Gem | `integrations/o3de/` | 60 Python |

## AI Companion Bridges

| Platform | Language | Location |
|---|---|---|
| SillyTavern | JavaScript | `integrations/sillytavern/` |
| OpenClaw (VGSK) | Python | `src/wyrdforge/bridges/openclaw_bridge.py` |
| NorseSagaEngine | Python | `src/wyrdforge/bridges/nse_bridge.py` |
| Voxta | Python | `src/wyrdforge/bridges/voxta_bridge.py` |
| Kindroid | Python | `src/wyrdforge/bridges/kindroid_bridge.py` |
| Hermes Agent | Python | `src/wyrdforge/bridges/hermes_bridge.py` |
| AgentZero | Python | `src/wyrdforge/bridges/agentzero_bridge.py` |

## TTRPG / VTT Bridges

| Platform | Language | Location | Tests |
|---|---|---|---|
| Foundry VTT | JavaScript | `integrations/foundry/` | 37 Jest |
| Roll20 | JavaScript | `integrations/roll20/` | 38 Jest |
| Fantasy Grounds Unity | C# | `integrations/fgu/` | 27 xUnit |
| Owlbear Rodeo | JavaScript | `integrations/owlbear/` | 39 Jest |
| D&D Beyond | JavaScript (extension) | `integrations/dndbeyond/` | 40 Jest |

## Sandbox Platforms

| Platform | Language | Location | Tests |
|---|---|---|---|
| OpenSim / Second Life | C# + LSL | `integrations/opensim/` | 46 xUnit |
| Minecraft (Fabric) | Java | `integrations/minecraft/` | 74 Python |
| Roblox | Luau | `integrations/roblox/` | 63 Python |

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
