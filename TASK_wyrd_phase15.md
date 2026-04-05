# TASK: WYRD Protocol Phase 15 — pygame Bridge

**Date started:** 2026-04-05
**Branch:** development
**Status:** IN PROGRESS

## Scope

Build a WYRD bridge for pygame (Volmarr's fork: github.com/hrabanazviking/pygame).
Unlike Java/C++/Lua bridges, pygame is Python — so this IS the production code,
not a mirror. Tests run directly against the bridge module (mocked HTTP).

## Sub-phases

| Sub-phase | Deliverable | Status |
|---|---|---|
| 15A | `wyrd_pygame_helpers.py` — pure logic (normalize, escape, builders, parser) | pending |
| 15A | `wyrd_pygame_client.py` — WyrdPygameClient (stdlib urllib, fire-and-forget threading) | pending |
| 15B | `wyrd_pygame_loop.py` — WyrdPygameLoop event hook helpers | pending |
| 15B | `integrations/pygame/wyrdforge/__init__.py` | pending |
| 15C | `integrations/pygame/wyrdforge/tests/test_wyrdforge.py` — ~55+ pytest tests | pending |
| — | ROADMAP.md update (15A-15C complete) | pending |
| — | git commit + push | pending |
| — | memory files update | pending |

## File Inventory

```
integrations/pygame/
    __init__.py
    wyrdforge/
        __init__.py
        wyrd_pygame_helpers.py
        wyrd_pygame_client.py
        wyrd_pygame_loop.py
        tests/
            __init__.py
            test_wyrdforge.py
```

## Design Notes

- `wyrd_pygame_helpers.py` — zero deps; normalize_persona_id, escape_json, build_query_body,
  build_observation_body, build_fact_body, parse_response, to_facts
- `wyrd_pygame_client.py` — uses urllib.request only (no httpx/requests dep); blocking query,
  fire-and-forget push via threading.Thread(daemon=True)
- `wyrd_pygame_loop.py` — WyrdPygameLoop wraps WyrdPygameClient with named hooks:
  on_npc_interact(entity_id, player_input) → str
  on_scene_change(location_id) → None
  on_npc_move(entity_id, new_location) → None
- No pygame import required for core bridge or tests (pygame is optional dep for loop hooks)
- Silent fallback when server unreachable (silent_on_error=True default)

## Test Targets

- TestNormalizePersonaId (12)
- TestEscapeJson (8)
- TestBuildQueryBody (6)
- TestBuildObservationBody (4)
- TestBuildFactBody (4)
- TestParseResponse (5)
- TestToFacts (4)
- TestWyrdPygameClientInit (4)
- TestWyrdPygameClientQuery (6) — mock urllib
- TestWyrdPygameClientPushFireAndForget (3)
- TestWyrdPygameClientHealthCheck (3)
- TestWyrdPygameLoopOnNpcInteract (4)
- TestWyrdPygameLoopOnSceneChange (3)
- TestWyrdPygameLoopOnNpcMove (3)

Total target: ~69 tests

## Next Steps (if session breaks)

1. Read this file
2. Check which files exist in integrations/pygame/wyrdforge/
3. Run `python -m pytest integrations/pygame/wyrdforge/tests/ -v` to see what passes
4. Complete missing sub-phases in order: 15A helpers → 15A client → 15B loop → 15C tests
5. Update ROADMAP.md, commit, push, update memory
