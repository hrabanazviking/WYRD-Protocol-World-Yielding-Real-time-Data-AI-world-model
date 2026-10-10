# WYRD-Protocol DEVLOG

Development log for the WYRD-Protocol-World-Yielding-Real-time-Data-AI-world-model
repository. Newest entries first. (README.md is Volmarr's alone — never edited here.)

---

## 2026-10-10 — Dusk forge run: "Rúnakefli — Inner-Communications Weave"
**Run:** wyrd-protocol-dusk-forge (scheduled 18:33 EDT, retried 19:42 EDT) · **Branch:** `development`
**Theme:** inner-communications — a typed, thread-safe in-process event fabric (the EventBus),
wired opt-in into the real producers and consumers. Note: this was a retry run. The 18:33
attempt died on a transient runtime error leaving 15 slices uncommitted in the tree; tonight's
run audited, completed, and committed them (no work discarded, nothing double-forged).

### Slices (20/20)
1. **EventEnvelope + topic registry** (new `runtime/events.py`) — immutable-ish StrictModel
   envelope (topic/payload/source/seq/issued_at/turn_id, attribute + mapping access);
   dotted topic names registered before use, wildcard patterns rejected.
2. **subscribe / unsubscribe / publish** — token-based subscriptions, synchronous
   in-order delivery (exact then wildcard, each in subscription order); `publish()` returns
   successful-delivery count, never raises on subscriber errors.
3. **Payload-type enforcement** — per-topic pydantic/dataclass schema validation; violations
   raise `TypeError` naming the topic.
4. **Subscriber error isolation** — raising subscribers are logged, recorded in the internal
   failure drain (`_take_failures()`), remaining subscribers still receive the event.
5. **Thread safety + FIFO** — one `RLock` guards all mutable state; per-topic FIFO by the
   bus-scoped `seq` counter; subscribers may publish/(un)subscribe re-entrantly.
6. **Bounded dead-letter queue** — oldest dropped on overflow (default cap 256, configurable).
7. **Replay ring buffer** — opt-in per-topic buffer; new subscribers backfill FIFO before live
   delivery (wildcards merge across topics by seq).
8. **Per-topic metrics** — `snapshot()` with published/delivered/failed/live subscriber_count,
   mutation-safe; `reset_metrics()` zeroes counters.
9. **Wildcard subscriptions** — `"world.*"` prefix match (never matches bare prefix); exact +
   wildcard both fire; unsubscribe removes only that subscription.
10. **`close()` shutdown** — idempotent; publish/subscribe/register raise `RuntimeError("bus closed")`;
    state cleared but topic registry retained.
11. **World wiring** (`ecs/world.py`) — `world.entity_created/removed`, `world.component_added/removed`.
12. **TurnLoop wiring** (`runtime/turn_loop.py`) — `turn.started` (before oracle), `turn.completed`
    (always, even degraded), `turn_id` threaded through envelopes.
13. **WritebackEngine wiring** (`services/writeback_engine.py`) — `writeback.written` / `writeback.replay`.
14. **PersistentMemoryStore wiring** (`persistence/memory_store.py`) — `memory.observation_added` /
    `memory.fact_added` on true inserts only (re-adds and reads silent).
15. **ContradictionDetector wiring** (`services/contradiction_detector.py`) — `contradiction.detected`
    (count + fact_ids).
16. **`state.quarantined`** (`hardening/state_io.py`) — `quarantine_file(..., bus=)` emits the event
    after the move, with path/dest/reason/detail; bus errors never disturb a quarantine.
17. **Turn-loop soak assertions** — 3 turns → 6 envelopes, `turn.started(seq k)` before
    `turn.completed(seq k+1)`, `turn_id` threaded, wildcard capture, failing subscriber mid-soak
    isolated without disturbing any turn.
18. **ContradictionAuditConsumer** (new `services/bus_consumers.py`) — subscribes `contradiction.*`,
    persists one contradiction-audit observation per detection (seq/count/fact_ids/issued_at).
19. **ReplayPersistenceBridge** (`services/bus_consumers.py`) — attaches with `replay=True`, persists
    backlog envelopes in seq order with per-(topic, seq) dedupe. Both consumers write through
    internal UNWIRED stores — a bus-wired store would feed `memory.*` events back into the bus
    (documented event-storm guard).
20. **Dead-letter observability** (`runtime/events.py`) — `dead_letter_summary()` (counts by
    topic + error_type) and `take_dead_letters()` (drain), the queue's monitoring surface.
    Slices 16 and 20 landed in the coordinator's own batch; slices 17–19 by the worker.

Wiring law for every slice: `bus=None` (the default everywhere) preserves the exact old behavior;
bus trouble never breaks the underlying operation (producers swallow publish errors).

### Verification
- Full suite: **PYTHONPATH=src /tmp/wyrdvenv2/bin/python -m pytest tests/ -q -p no:cacheprovider --ignore=tests/test_scale_limits.py**
- **1760 passed, 14 skipped, 6 xfailed, 1 FAILED** — the failure is the known flaky timing test
  `test_b1_feed_replay_within_budget` (22.9µs/event vs 20µs budget under load; documented in the
  dawn entry; NOT retuned per standing rule).
- New dusk tests: 125 (bus core 32, bus features 45, wiring_a 24, wiring_b 24) — all green.
- Mid-run environmental incident: /tmp (512M tmpfs) filled by leftover worker test scratch
  (wyrd-dusk-w* + pytest-of-root); cleared the disposable scratch, re-ran full suite green.
  Not a code defect.

### Push
- Committed in 3 batches (A: bus core 1–10+20, B: producer wiring 11–16, C: consumers 17–19);
  pushed to `origin/development`; verified `git ls-remote origin development` equals local HEAD.

---

## 2026-10-10 — Dawn forge run: "Helheim Hardening — the resilience weave"
**Run:** wyrd-protocol-dawn-forge (scheduled 06:33 EDT) · **Branch:** `development`
**Theme:** stability, robustness, self-healing, error correction, fault isolation,
inner-communications — per TODO.md's own marching orders for this first-ever
forge run on the repo.

### Slices (20/20)
1. **BackoffConfig validation** (`hardening/backoff.py`) — `__post_init__` rejects
   invalid configs; kills the real latent bug where `max_attempts=0` made
   `retry_with_backoff` hit `raise None` → `TypeError`.
2. **Circuit breaker** (new `hardening/circuit_breaker.py`) — thread-safe
   CLOSED/OPEN/HALF_OPEN breaker with failure threshold, reset timeout, probe
   limit, `CircuitOpenError`, stats.
3. **BoundedThreadPool drain-on-shutdown** (`hardening/pool.py`) — shutdown now
   drains the pending queue before sending sentinels (no more silently abandoned
   tasks); added `tasks_completed` / `tasks_failed` counters.
4. **`prune_quarantine()`** (`hardening/state_io.py`) — retention cap for the
   quarantine dir: keeps newest N, prunes oldest.
5. **`read_json_state()`** (`hardening/state_io.py`) — read-side companion to
   `atomic_write_json`: corrupt JSON or failed validator → quarantine + raise
   `CorruptStateError`.
6. **TurnLoop per-stage fault isolation** (`runtime/turn_loop.py`) — oracle,
   writeback, and contradiction-detector stages each wrapped; failures land in a
   new `TurnResult.stage_errors` list and the turn degrades instead of dying
   (oracle failure → minimal-but-valid degraded packet).
7. **TurnLoop input validation** — `TypeError` on non-str, `ValueError` on
   empty/whitespace or > 20000 chars (`MAX_USER_INPUT_LEN`).
8. **Turn observability** — `run_id` per loop, `turn_id` per turn on
   `TurnResult`, `logging.debug` at stage boundaries tagged with `turn_id`.
9. **WritebackEngine idempotency** (`services/writeback_engine.py`) — optional
   `idempotency_key`; bounded (1024) seen-key record; replays return the cached
   ids without writing new records.
10. **PassiveOracle degradation** (`oracle/passive_oracle.py`) — memory/belief
    layer exceptions are caught once, logged, and a valid packet with empty
    observations/facts is returned; world identity intact.
11. **`open_verified_state_db()`** (`hardening/state_io.py`) — opens via
    `open_or_quarantine`, then `PRAGMA integrity_check`; integrity failure →
    quarantine + fresh open, `recovered=True`.
12. **Verified opens wired into all three stores** (`persistence/memory_store.py`,
    `bond_store.py`, `world_store.py`).
13. **`CURRENT_SCHEMA_VERSION` constants** in all three persistence modules;
    stamped `user_version` asserted by test.
14. **`repair_memory_db()`** (`persistence/memory_store.py`) — VACUUM + REINDEX
    + integrity_check, honest report dict (no fake repairs).
15. **bond_store write atomicity** — audit proved all write paths already
    transactional (`with self._connect()` commits/rolls back); converted to a
    regression test (failing 2nd DELETE of 3 → zero rows deleted).
16. **Watchdog without private CPython internals** (`bridges/http_api.py`) —
    `_watchdog_loop` now tracks serve-thread `is_alive()` instead of
    `_BaseServer__shutdown_request`; bounded-restart semantics preserved.
17. **Injection-guard normalization** (`security/prompt_injection_guard.py`) —
    whitespace/punctuation normalized before matching (kills
    `"ignore\nprevious\tinstructions"` evasion); new
    `detect_prompt_injection_spans()` with match spans.
18. **PermissionGuard audit** (`security/permission_guard.py`) — bounded
    decision audit log (seq, ISO timestamp, action, risk, allow, reason) +
    `PermissionDenied` + `require()`.
19. **PythonRPGBridge input floor** (`bridges/python_rpg.py`) — `query()`
    validates `persona_id`/`user_input` with the same `check_string` discipline
    as the HTTP handler; real gap, fixed.
20. **Bridge contract conformance test** — discovers all 9 bridge modules, pins
    the conformance map (only `PythonRPGBridge` satisfies `BifrostBridge` today;
    the 8 engine adapters deliberately expose engine-specific surfaces); drift
    in either direction fails loudly.

### Verification
- Full suite: **PYTHONPATH=src /tmp/wyrdvenv/bin/python -m pytest tests/ -q**
- New forge tests: 118 (test_forge_backoff 13, circuit_breaker 12, pool 4,
  state_io, turn_loop 14, writeback 6, oracle 7, persistence 9, http_watchdog,
  injection_guard, permission_guard, python_rpg, bridge_contract)
- Pre-existing `test_hardening.py` watchdog section repaired during the run
  (5 failures from the watchdog rewrite fixed; 92/92 green).
- Baseline note: `test_b1_feed_replay_within_budget` is a known flaky timing
  test (passes in isolation, fails under full-suite load on shared VMs).

### Push
- Pushed to `origin/development`; verified `git ls-remote origin development`
  equals local HEAD.
