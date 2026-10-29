# CryEngine integration — testing honesty (E1)

Two test surfaces live under `tests/`:

- **`tests/honest/WyrdHelpersHonestTest.cpp` — the honest harness.** It is
  compiled together with the shipped `Code/WyrdPlugin/WyrdHelpers.cpp`
  (pure standard C++, no CryEngine dependency) and run natively, so it
  tests the shipped C++ itself. Build and run:

  ```
  g++ -std=c++17 -I Code/WyrdPlugin \
      tests/honest/WyrdHelpersHonestTest.cpp Code/WyrdPlugin/WyrdHelpers.cpp \
      -o /tmp/wyrd_cryengine_honest && /tmp/wyrd_cryengine_honest
  ```

  Scope limit, stated plainly: the plugin glue (`WyrdPlugin.cpp`) needs
  CryEngine and is **not** executed anywhere — in-engine, this integration
  remains host-untested.

- **`tests/test_wyrdforge.py` — mirror / logic tests.** It re-implements
  the helpers' logic in Python and tests the copy. Drift between the copy
  and the shipped C++ is undetectable by that suite; it is kept only as a
  logic specification and is labelled as such in its own header.

Classification of every integration and SDK: `integrations/honesty-manifest.json`.
