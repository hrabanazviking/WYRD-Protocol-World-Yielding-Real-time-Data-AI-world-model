# CryEngine integration — testing honesty (E1, updated E3)

## STUB status — read this first

This integration is a **partial stub**, labelled as such in every surface
(this file, the source headers, `WyrdForgePlugin.json`,
`docs/integrations/overview.md`, and `integrations/honesty-manifest.json`):

- **Implemented + executed here (E3):** all client logic. `WyrdHelpers`
  (JSON/persona helpers) and `WyrdClientCore` (query/push/health logic
  behind an injected `IWyrdTransport`: body building, response parsing,
  silent/fallback error semantics, game-thread completion queue) are
  pure standard C++ and are compiled and run by the honest harnesses
  below. `WyrdPlugin.cpp` — the delegating shell over the core — is in
  the core harness's build, so the shipped shell at least compiles
  host-free.
- **STUB (not implemented anywhere):** the HTTP transport itself (no
  libcurl binding is bound to the core) and CryEngine plugin
  registration. With no transport bound, operations fail honestly —
  `GetLastError()` says so, and queries complete with a Failure result
  or the configured fallback — they never silently pretend to work.
- **Not verified:** anything in-engine. No CryEngine exists on the
  machine that produced E1/E3.

## Test surfaces under `tests/`

- **`tests/honest/WyrdHelpersHonestTest.cpp` — honest harness (21 checks).**
  Compiled with the shipped `Code/WyrdPlugin/WyrdHelpers.cpp` and run
  natively; tests the shipped C++ itself:

  ```
  g++ -std=c++17 -I Code/WyrdPlugin \
      tests/honest/WyrdHelpersHonestTest.cpp Code/WyrdPlugin/WyrdHelpers.cpp \
      -o /tmp/wyrd_cryengine_honest && /tmp/wyrd_cryengine_honest
  ```

- **`tests/honest/WyrdClientCoreHonestTest.cpp` — honest harness (31 checks, E3).**
  Compiled with the shipped `WyrdClientCore.cpp`, `WyrdHelpers.cpp`, and
  `WyrdPlugin.cpp`; drives the core with an in-memory fake transport and
  pins the request shapes, the completion-queue semantics, and the
  no-transport / HTTP-failure behaviour:

  ```
  g++ -std=c++17 -I Code/WyrdPlugin \
      tests/honest/WyrdClientCoreHonestTest.cpp \
      Code/WyrdPlugin/WyrdClientCore.cpp Code/WyrdPlugin/WyrdHelpers.cpp \
      Code/WyrdPlugin/WyrdPlugin.cpp \
      -o /tmp/wyrd_cryengine_core_honest && /tmp/wyrd_cryengine_core_honest
  ```

- **`tests/test_wyrdforge.py` — mirror / logic tests.** It re-implements
  the helpers' logic in Python and tests the copy. Drift between the copy
  and the shipped C++ is undetectable by that suite; it is kept only as a
  logic specification and is labelled as such in its own header.

Classification of every integration and SDK: `integrations/honesty-manifest.json`.
