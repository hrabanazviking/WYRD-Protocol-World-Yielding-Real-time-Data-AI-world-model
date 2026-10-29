# O3DE integration — testing honesty (E3)

## STUB status — read this first

This Gem is a **partial stub**, labelled as such in every surface (this
file, the component source headers, `gem.json`,
`docs/integrations/overview.md`, and `integrations/honesty-manifest.json`):

- **STUB (not implemented):** `WyrdSystemComponent`'s HTTP layer.
  `PostAsync()` and `HealthCheck()` are TODO no-ops, so `QueryNPC`,
  `PushObservation`, and `PushFact` build a request body and drop it —
  nothing reaches WyrdHTTPServer through this component. Implementing
  `PostAsync` over `AzFramework::HttpRequestor` requires a real O3DE
  project (the pattern is sketched in the component's source comments).
- **Implemented in E3:** the helpers. Before E3, `WyrdHelpers.h`
  declared seven methods with **no implementation anywhere**. The
  algorithms now live in `Code/Source/WyrdHelpersCore.cpp` (pure
  standard C++) with `Code/Source/WyrdHelpers.cpp` as a thin
  AZStd::string adapter over them.
- **Not verified:** anything compiled against the AZ framework — the
  adapter, the component, the reflection code. No O3DE exists on the
  machine that produced E3.

## Test surfaces under `tests/`

- **`tests/honest/WyrdHelpersCoreHonestTest.cpp` — honest harness
  (21 checks, E3).** Compiled with the shipped
  `Code/Source/WyrdHelpersCore.cpp` and run natively; tests the shipped
  logic itself:

  ```
  g++ -std=c++17 -I Code/Source \
      tests/honest/WyrdHelpersCoreHonestTest.cpp Code/Source/WyrdHelpersCore.cpp \
      -o /tmp/wyrd_o3de_honest && /tmp/wyrd_o3de_honest
  ```

- **`tests/test_wyrdforge.py` — mirror / logic tests.** It re-implements
  the helpers' logic in Python and tests the copy. Drift between the
  copy and the shipped C++ is undetectable by that suite; it is kept
  only as a logic specification and is labelled as such in its own
  header.

Classification of every integration and SDK: `integrations/honesty-manifest.json`.
