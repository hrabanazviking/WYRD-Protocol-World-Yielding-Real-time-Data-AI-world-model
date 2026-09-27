# Timeout & Loop-Bound Inventory

**Wave G Slice 5 (Track 4 P2) · 2026-09-26 · the roadmap's audit artifact:**
every blocking call in the tree with its named timeout, and every
`while True` / retry loop with its cited bound. Pinned by
`tests/test_timeout_lint.py`, which fails if a timeout-less risky
call is introduced.

## Blocking calls

| Blocking call | Timeout | Where | Design citation |
|---|---|---|---|
| Ollama `/api/tags` probe | 5 s | `src/wyrdforge/llm/ollama_connector.py:99` | named default |
| Ollama generate/chat | 60 s (`self.timeout`, ctor-tunable) | `src/wyrdforge/llm/ollama_connector.py:66,71,112` | named default |
| Cloud-relay upstream client | 15 s (`config.timeout`) | `tools/wyrd_cloud_relay/relay.py:137,240` | named default |
| Nerve unix-socket send (hermes) | 2.0 s `settimeout` (`NERVE_TIMEOUT`) | `src/wyrdforge/bridges/hermes_bridge.py:61,236-237` | fire-and-forget, non-blocking |
| Nerve unix-socket send (runa) | 2.0 s `settimeout` (`NERVE_TIMEOUT`) | `src/wyrdforge/bridges/runa_awareness.py:75,427-428` | fire-and-forget, non-blocking |
| TUI HTTP client | 5 s (`self.timeout`, `--timeout` tunable) | `tools/wyrd_tui.py:129,131,136,151,632` | named default |
| Watchdog health-check cadence | 5.0 s `Event.wait` interval | `src/wyrdforge/bridges/http_api.py:354` | bounded wait; shutdown-responsive |
| Watchdog restart delay | jittered backoff (`BackoffConfig`: 0.5 s base, ×2, 30 s cap, ±25 %) | `src/wyrdforge/bridges/http_api.py:371-379` | bounded; terminal after 4 |
| Watchdog restart budget | 4 consecutive restarts, then CRITICAL + stop; counter resets on healthy check and on `start_background()` | `src/wyrdforge/bridges/http_api.py:345-387` |
| Pool `queue.get` | 1.0 s | `src/wyrdforge/hardening/pool.py:149` | bounded wait; exits on `_shutdown`/`_SENTINEL` |
| Pool `queue.put` | non-blocking (`put_nowait`) | `src/wyrdforge/hardening/pool.py:90,113` | never blocks |
| sqlite busy timeout (state, bond, world stores) | 5.0 s — **explicit**, was Python's implicit default | `src/wyrdforge/hardening/state_io.py:185`, `src/wyrdforge/persistence/bond_store.py:75`, `src/wyrdforge/persistence/world_store.py:71` | named default (behavior-identical) |
| sqlite busy timeout (memory store) | 10.0 s + `PRAGMA busy_timeout=5000` | `src/wyrdforge/persistence/memory_store.py:117,121` | named default |
| TUI `input()` / `Prompt.ask` | none — interactive by design | `tools/wyrd_tui.py` | the user is the timeout |

## Loops and their bounds

| Loop | Bound | Where |
|---|---|---|
| Watchdog restart loop | 4 consecutive restarts (BackoffConfig), then CRITICAL + stop; counter resets on healthy check and on `start_background()` | `src/wyrdforge/bridges/http_api.py:345-387` |
| `retry_with_backoff` | `BackoffConfig.max_attempts` (4) + terminal raise | `src/wyrdforge/hardening/backoff.py` |
| Pool worker loop | `_shutdown` flag or `_SENTINEL` | `src/wyrdforge/hardening/pool.py:147` |
| TUI main loops | user quit / EOF / KeyboardInterrupt | `tools/wyrd_tui.py:559,606` |
| `tick_n` | `range(n)` | `src/wyrdforge/ecs/system.py` |
| `get_ancestors` parent walk | visited-set; cycle → warning + terminate | `src/wyrdforge/ecs/yggdrasil.py` |
| Oracle fallback parent walk | visited-set; cycle → warning + terminate | `src/wyrdforge/oracle/passive_oracle.py` |
| `serve_forever` (http/kindroid/voxta bridges) | server main loop by design; shutdown via `_stopped` / thread end | `src/wyrdforge/bridges/http_api.py:292,341`, `kindroid_bridge.py:87`, `voxta_bridge.py:89` |

**0 unbounded loops. 0 blocking calls without a named timeout.**
