# Wyrd Runtime Packet Integration Pack

This pack contains repo-targeted Markdown files with concrete code for wiring a durable runtime packet into:

- `session/session_manager.py`
- `core/engine.py`
- `ai/prompt_builder.py`

These are written against the current NorseSagaEngine structure and are meant to be copied into the repo when you are ready.

## Files

1. `01_session_manager_runtime_packet.md`
2. `02_engine_runtime_packet_wiring.md`
3. `03_prompt_builder_runtime_packet.md`
4. `04_drop_in_runtime_packet_module.md`

## Intent

The runtime packet gives you a compact, durable, replayable memory lane that sits between:

- persistence
- turn assembly
- final LLM prompt injection

That means you get:

- a saved per-turn packet in session data
- a compact prompt-facing summary
- a place to store pre-LLM and post-LLM turn state
- cleaner continuity than relying only on raw history and ad-hoc memory pulls
