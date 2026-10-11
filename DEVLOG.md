# WYRD-Protocol DEVLOG

Development log for the WYRD-Protocol-World-Yielding-Real-time-Data-AI-world-model
repository. Newest entries first. (README.md is Volmarr's alone — never edited here.)

---

## 2026-10-11 — Dusk forge run: "Gullinbursti — the Swift and True"
**Run:** wyrd-protocol-dusk-forge (scheduled 18:33 EDT) · **Branch:** `development`
**Theme:** EFFICIENCY + ERROR CORRECTION / ACCURACY — the third weave after
Helheim Hardening (resilience) and Rúnakefli (inner-communications).
Wedge SWIFT: measured efficiency gains on the hot paths the new bus fabric
rides. Wedge TRUE: a bug-hunt driven by property and edge tests; four real
bugs found and fixed in-slice. Per TODO.md's own marching orders: "Check for
any ways to make WYRD run more efficiently" + "Do extensive bug hunting and
bug fixing."

### Slices (20/20)
**Efficiency (1–10):**
1. **Detector conflict-scan SQL pushdown** (`persistence/memory_store.py`,
   `services/contradiction_detector.py`) — new
   `find_canonical_facts(subject_id, fact_key)` / `find_canonical_facts_many(pairs)`
   push the subject+key filter into SQL via indexed columns +
   `json_extract(data_json,'$.content.structured_payload.…')` instead of
   deserializing the whole canonical store per check. Differential test on
   500 seeded facts: identical results, **6.7× faster**. Bound params only
   (hostile-input test: `' OR '1'='1` matches nothing, table intact).
2. **`find_open_contradictions` SQL pushdown** — new
   `find_open_contradictions()` in one SQL round-trip (was: full-table
   deserialization + Python filter). Identical results on seeded store.
3. **Replay backfill fast path** (`runtime/events.py`) — honest measured
   deviation: `heapq.merge` was ~2× *slower* than extend+sort on CPython
   (Timsort detects the k pre-sorted runs in C). Shipped the measured-fastest
   real path: skip the sort entirely when exactly one per-topic buffer matches
   (13×/8.6× at n=4096), else extend+sort with a C-speed
   `operator.attrgetter("seq")` key (1.46× over the old lambda). Differential
   test pins backfill order identical to the old path.
4. **Replay delivery outside the bus lock** — replayed envelopes were
   delivered while holding the bus RLock: a slow replay subscriber blocked
   ALL bus traffic. Now collected under lock, delivered after release.
   Thread test: concurrent publish latency **0.0ms during a ~1000ms slow
   replay** (was ~1000ms). Replay-before-live ordering preserved for the
   subscribing thread; `_record_failure` bookkeeping stays lock-serialized.
5. **Precomputed wildcard prefixes** — `_wildcards` entries are now
   `(token, pattern, prefix, fn)`; `publish()` no longer recomputes
   `_wildcard_prefix` per wildcard per publish. Behavior identical.
6. **`publish_many` batch API** — one lock acquisition for N envelopes; a
   `_sub_version` generation counter invalidates the per-batch delivery-target
   cache on re-entrant subscription changes, preserving exact N-publish
   semantics (validation order, schema, metrics, buffers, isolation).
   **1.27–1.31×** vs N publishes (2000 items, 12 wildcards).
7. **Search scoring without full deserialization** (`persistence/memory_store.py`)
   — `search()` scored by deserializing every candidate; now scores from
   FTS5 columns (title/summary/lexical_terms) + confidence column +
   `json_extract(default_priority)`, deserializing only the final top-`limit`
   records. Differential test: identical rankings across 12 query/filter
   variants + LIKE fallback.
8. **Thread-local connection cache** (`memory_store._connect`) — every op
   opened a new SQLite connection + 4 PRAGMAs; now one cached connection per
   thread (same PRAGMAs, WAL-safe). White-box: 200 ops open exactly 1
   connection; **41× on acquisition, ~1.8× on a 200-op read mix**; 2-writer /
   6-reader soak green.
9. **Batched contradiction checking** — new
   `ContradictionDetector.check_many(records)` groups by (subject, key) and
   uses the multi-key SQL query (slice 1) instead of N round-trips:
   18 → 13 round-trips on a 6-record/5-conflict batch (residual is inherent:
   conflict writes + quarantines). Same conflicts, same emit semantics as
   sequential calls; in-batch quarantines tracked in a local id-set.
10. **Performance non-regression budgets** — new B5 (bus publish throughput,
    ≤40µs/event, measured ~7.5µs) and B6 (wildcard replay merge, ≤15ms/10k
    events, measured ~1.85ms) budgets in `tests/test_performance_budgets.py`.
    B1 untouched per standing rule.
**Error correction / accuracy (11–19):**
11. **Re-entrant publish FIFO — BUG FOUND + FIXED.** A subscriber publishing
    to the *same* topic from inside its callback caused later subscribers to
    observe `[seq 2, seq 1]` — a real per-topic FIFO inversion. Fix: same-topic
    re-entrant publishes are deferred and drained in FIFO order before the
    outer `publish()` returns (fresh seq/buffer/metrics at drain time, so seq
    order always matches delivery order). Cross-topic re-entrancy byte-identical
    to before. Nested 2-level re-entrancy keeps FIFO; all pre-existing bus tests
    green.
12. **Replay/live interleaving audit — clean, pinned.** Concurrent test:
    every envelope delivered exactly once; buffered pre-subscribe envelopes
    keep seq order; live events may interleave with replay (documented, not a
    violation); events published after `subscribe()` returns always follow the
    backfill.
13. **Dead-letter cap exactness — clean, pinned.** 300 failing deliveries →
    exactly 256 retained, newest kept oldest-first (seqs 45..300); boundary
    (exactly 256) and cap-0 cases pinned; summary/drain coherent.
14. **`truth_calibrator` — BUG FOUND + FIXED.** An empty `forbidden_assumptions`
    entry is a substring of every text → forced factual integrity to **0 on
    every evaluation**; empty/whitespace entries now skipped as degenerate.
    `evaluate(case, None)` died with a bare `AttributeError` → now a clear
    `TypeError` at the boundary.
15. **`self_correction` — BUG FOUND + FIXED.** `contradict(NaN)` returned
    `(1.0, [nan, 1.0])` — **NaN silently promoted to maximum certainty** and
    seeded into the confidence history; `is_uncertain(NaN)` returned False.
    NaN/inf now raise `ValueError`, non-numeric raises `TypeError`.
16. **Eval harness scoring audit — clean, pinned.** Fake-oracle differential
    pins exact check counts, failure attribution, partial credit (n−k)/n,
    zero-check runs (`checks_run=0 → passed=True, score=1.0`), `summary()`
    counts incl. empty lists. Noted for a future slice: the harness has no
    xfail machinery (pass/fail only).
17. **Search ranking determinism** — score ties now break by `record_id`
    ascending; stable across runs and insertion orders (seeded test).
18. **Normalization idempotence — BUG FOUND + FIXED.** The 2000-input seeded
    fuzzer found a real non-idempotence: the 64-char truncation cutting at an
    underscore boundary left a trailing `_` that a second `normalize` strips
    (`normalize(normalize(x)) != normalize(x)`). The cut edge is now
    `rstrip("_")` — output is always a fixpoint; also pinned ≥512-char
    pre-truncation, bytes/None inputs, unicode/RTL/zero-width/zalgo/injection
    corpus.
19. **EventBus randomized-op fuzz** (new `tests/test_dusk_fuzz_bus.py`) —
    2000-op seeded fuzz (4 seeds × 500 ops) green: no escaping exceptions,
    metrics coherence, per-(subscriber, topic) FIFO across re-entrancy/batches/
    replays, DLQ cap respected, post-close ops raise correctly. Non-vacuous:
    1,935 envelopes, 12,728 delivery attempts, 526 isolated failures.
20. **This DEVLOG entry.**

Five workers in own worktrees/branches (A: 1,2,9 · B: 3,4,5,6 · C: 7,8,10,17 ·
D: 14,15,16,18 · E: 11,12,13,19), merged into `development` by the
coordinator (no conflicts); B's events.py changes merged before E's audits
pinned the new behavior. Worker C's final report text was lost in delivery —
its commit `be693e8` message carried the full slice record and was verified
against the code before merging.

### Verification
- Full suite: **PYTHONPATH=src …/bin/python -m pytest tests/ -q -p no:cacheprovider --ignore=tests/test_scale_limits.py**
- **1847 passed, 14 skipped, 6 xfailed, 1 FAILED** — the failure is the known
  flaky timing test `test_b1_feed_replay_within_budget` (documented in both
  prior forge entries; NOT retuned per standing rule). It failed twice and
  passed twice this run — still flaky, unrelated to tonight's changes (the
  VerdandiBridge timing path touches none of them).
- New dusk tests: 74 (efficiency_a 12, efficiency_b 15, efficiency_c 16+,
  accuracy_d 33, correctness_e 10, fuzz_bus 4) — all green. All benchmarks
  are real measured numbers, no fakes.

### Push
- Merged in 5 worker batches + this entry; pushed `development` to origin;
  verified `git ls-remote origin development` equals local HEAD
  (`d9b23b74fc8eef4be10c43c1b8b3bcf6f7696b43`). No force-push; README.md
  untouched; no remote edits to merge (origin unchanged since run start).

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
