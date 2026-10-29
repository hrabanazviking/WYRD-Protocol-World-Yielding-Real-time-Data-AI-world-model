# WyrdForge OpenSim region module — deployment (E3)

This folder is the **real OpenSim region module** for WyrdForge, added in
E3. Before E3 the integration shipped only a host-free bridge class and
its csproj told deployers to "implement IRegionModuleBase when
deploying". That implementation now ships:

- `WyrdForgeRegionModuleHost.cs` — implements `INonSharedRegionModule`
  (the `IRegionModuleBase` contract: `Name`, `Initialise`, `Close`,
  `AddRegion`, `RemoveRegion`, `RegionLoaded`, plus the non-shared
  marker `ReplaceableInterface`). It is annotated for OpenSim's
  Mono.Addins region-module loader (`/OpenSim/RegionModules`).
- **Non-shared, deliberately**: one module instance per region, so the
  wrapped bridge (and its HTTP client) lives and dies with its region,
  and per-Scene event subscriptions unwind cleanly on region removal.
- Wiring: `AddRegion` subscribes `OnMakeRootAgent` (syncs entering
  avatars to WYRD, honouring `AutoSyncAvatars`) and `OnChatFromClient`
  (dispatches `/wyrd`, `/wyrd-sync`, `/wyrd-health` via the bridge's
  parser, honouring `EnableChatCommands`, and says replies back with
  `Scene.SimChat`). `RemoveRegion` unsubscribes both. All network work
  is fire-and-forget with failures logged to the simulator console —
  an event handler never throws into OpenSim.

## Structure: why a separate project

`WyrdForge.OpenSim` (the sibling project) is the host-free bridge core:
it references only the WyrdForge C# client, so its xUnit suite compiles
and runs with nothing but the dotnet SDK. The OpenSim assemblies
(`OpenSim.Framework`, `OpenSim.Region.Framework`, `OpenMetaverse`,
`Nini`, `Mono.Addins`) exist only inside an OpenSim installation, so
the dependency is isolated in this deployment project — the standard
structure for OpenSim modules. This project is **not** in
`WyrdForge.OpenSim.sln`, so the solution stays buildable without OpenSim.

## Build and deploy

```sh
# Point OpenSimBin at your OpenSim installation's bin/ directory:
dotnet build WyrdForge.OpenSim.RegionModule.csproj -p:OpenSimBin=/path/to/opensim/bin
```

Copy the build output — `WyrdForge.OpenSim.RegionModule.dll`,
`WyrdForge.OpenSim.dll`, `WyrdForge.Client.dll` — into that same `bin/`
directory, then add to `OpenSim.ini`:

```ini
[WyrdForge]
Host = localhost
Port = 8765
; TimeoutMs = 10000
; AutoSyncAvatars = true
; EnableChatCommands = true
```

Restart the simulator (or the region). The module announces itself on
the console at Initialise and again per region at RegionLoaded.

The LSL side (`../lsl/wyrdforge_npc.lsl`) is independent of this module
and unchanged: it talks to WyrdHTTPServer directly via `llHTTPRequest`.

## Honesty — what is verified and what is not

- The bridge core is covered by a genuine xUnit suite
  (`WyrdForge.OpenSim.Tests/`, ProjectReference to the core) — where the
  dotnet SDK exists.
- This host project was authored in E3 on a machine with **no OpenSim
  installation and no dotnet SDK**. It has **not been compiled** and
  **not been run in a region**. It is written against the stable
  OpenSim 0.9.x module API, but the first build against a real
  OpenSim `bin/` — and the first in-world exercise — are genuine
  verification steps, not formalities.
- Classification: `genuine-suite-elsewhere` in
  `integrations/honesty-manifest.json`, with this scope stated there too.
