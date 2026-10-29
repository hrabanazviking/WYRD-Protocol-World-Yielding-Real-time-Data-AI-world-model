# Status: parked research pack — re-home pending (2026-10-29, Phase E5)

This directory is **not part of the WYRD engine**. It is a clean-room
research pack (see `00_INDEX.md` / `README.md`) plus a divergent V5
starter copy of the codebase under `src/wyrdforge/` (a
models/runtime/schemas/security/services subset — no ECS, Oracle,
or persistence).
Nothing in the engine's `src/` or `tests/` references this directory,
and the starter copy here is **not** the shipped code: the real
engine lives in the repository's top-level `src/wyrdforge/`.

The WYRD advancement roadmap (§9 E5) calls for this directory to be
re-homed to its own project. That move is **blocked pending a
destination decision**: no destination project/repo exists yet, and
the content is preserved here, byte-for-byte, until one is named.
Do not cite this directory as WYRD's architecture or implementation,
and do not build on the starter copy.
