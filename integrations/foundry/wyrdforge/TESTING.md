# Foundry VTT integration — testing honesty (E1)

Two test files live in `tests/`:

- **`tests/honest.test.mjs` — the honest harness.** It loads the shipped
  `scripts/wyrdforge.js` verbatim as an ES module in a `vm` context (Foundry
  host globals stubbed) and exercises its real exported functions.
  Run it with:

  ```
  node --experimental-vm-modules --test tests/honest.test.mjs
  ```

  The `--experimental-vm-modules` flag is **required** — the harness uses
  `vm.SourceTextModule`, which Node refuses without it.

- **`tests/wyrdforge.test.js` — mirror / logic tests.** It inlines copies of
  the shipped functions and tests the copies. Drift between a copy and the
  shipped file is undetectable by that suite; it is kept only as a logic
  reference and is labelled as such in its own header.

Classification of every integration and SDK: `integrations/honesty-manifest.json`
(repo root of `integrations/`).
