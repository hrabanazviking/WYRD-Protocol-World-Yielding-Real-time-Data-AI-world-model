# WyrdForge for Unity — package notes (E3)

UPM package `com.wyrdforge.wyrdforge`: a WYRD Protocol bridge for Unity.
NPC dialogue and entity state are grounded in a deterministic ECS world
model served by WyrdHTTPServer (`POST /query`, `POST /event`, `GET /health`
— the server's unversioned routes; it also serves the same surface under
`/v1/`).

## What is in the package

| Path | What it is |
|---|---|
| `Runtime/WyrdManager.cs`, `WyrdEntityData.cs`, `WyrdNPC.cs`, `WyrdUnityOptions.cs` | The plain-C# client. No Unity dependency — usable and unit-testable outside Unity. |
| `Runtime/WyrdManagerBehaviour.cs` | **Real MonoBehaviour** (E3): attach to a GameObject, configure connection settings in the Inspector; wraps `WyrdManager`, publishes it as `WyrdManager.Instance`, offers coroutine query/health helpers. |
| `Runtime/WyrdNPCBehaviour.cs` | **Real MonoBehaviour** (E3): attach to an NPC GameObject; builds a `WyrdEntityData` from its Inspector fields and registers it on Start (when the manager's AutoRegisterNPCs is on). |
| `Runtime/WyrdForge.Runtime.asmdef` | Runtime assembly definition (assembly `WyrdForge.Runtime`). |
| `Editor/WyrdManagerBehaviourEditor.cs` | The **editor inspector** (E3): a custom Inspector for WyrdManagerBehaviour — connection settings, live status (base URL, last health result, registered entities, last error), and health-check / test-query actions. |
| `Editor/WyrdForge.Editor.asmdef` | Editor assembly definition (assembly `WyrdForge.Editor`, Editor platform only, references the runtime assembly). |

## .meta files

This repository ships **no `.meta` files** for the package. That is
deliberate: Unity generates a `.meta` file (with a fresh GUID) for every
script, folder, and `.asmdef` the first time it imports the package, and
generated GUIDs should be created by your Unity install, not copied from
a repo. Import the package, let Unity generate the `.meta` files, and
commit them with your project as usual.

## Honesty — what is verified and what is not

- The plain-C# client is covered by a genuine xUnit suite
  (`WyrdForge.Unity.Tests/`, which Compile-Includes the four plain
  Runtime files) — where the dotnet SDK exists. Run it with
  `dotnet test` in that folder.
- The MonoBehaviours, the `.asmdef` files, and the editor inspector were
  authored in E3 on a machine with **no Unity installation and no dotnet
  SDK**. They have **not been compiled in Unity and their in-engine
  behaviour is unverified**. They are written against the stable Unity
  API surface (MonoBehaviour lifecycle, coroutines, CustomEditor) and
  keep every network call inside the already-tested plain-C# client,
  but the first Unity import is a real verification step, not a formality.
- Classification: `genuine-suite-elsewhere` in
  `integrations/honesty-manifest.json`, with this scope stated there too.
