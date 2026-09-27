# Performance Budgets

**Wave G Slice 6 (Track 3 P1+P2) · 2026-09-27 · the roadmap's budget
artifact:** every hot path gets a named budget, an owner, and a
measurement mechanism. The numbers live here; the enforcement lives
in `tests/test_performance_budgets.py`, which parses this file —
edit a budget here and the test enforces the new number. If doc and
test disagree on parsing, the test fails loudly, never silently.

```budgets
feed_replay_us_per_event: 20
memory_parse_s: 5
bridge_run_s: 30
mirror_write_s: 1
```

## The four budgets

| # | Path | Budget | Owner | Measured by |
|---|---|---|---|---|
| B1 | Feed replay — `VerdandiBridge.build_from_events` (`src/wyrdforge/bridges/verdandi_bridge.py:644`) replays nerve-feed entries into a fresh world | ≤ 20 µs/event | repo — `tests/test_performance_budgets.py` (synthetic 20k-event mixed-type feed, warmup, median of 5) | pytest, every suite run |
| B2 | Memory parse (attach phase) — `parse_memory_beliefs` (`verdandi_bridge.py:1290`), `home=`-parameterized so a synthetic tree is first-class | ≤ 5 s at current corpus size | repo — `tests/test_performance_budgets.py` (synthetic tree sized to the corpus below, warmup, median of 3) | pytest, every suite run |
| B3 | Full bridge run (replay + attach + senses + memory parse) | ≤ 30 s wall | **Verdandi-side** 1-minute heartbeat worker (`wyrd-mirror-bridge` cron) — outside this repo | existing heartbeat reporting; watched by the T4-P3 seven-day proof |
| B4 | Mirror JSON write (`wyrd_mirror.json`) | ≤ 1 s | **Verdandi-side** runner — outside this repo | existing heartbeat reporting |

B3 and B4 are the roadmap's own shape: the baselines describe the
heartbeat worker, and this slice does not smuggle Verdandi-side code
into the repo to fake measurability. They are recorded here with
owners and observation mechanisms; the repo-side measurable analogue
of the projection build is `VerdandiBridge.summary()` — reported as
context in `docs/scale-limits.md`, not enforced.

## Measured baselines

| Budget | Roadmap 2026-09-26 | Re-measured 2026-09-27 (this tree, this machine) | Verdict |
|---|---|---|---|
| B1 feed replay | ~11 µs/event | pre-fix **~330 µs/event at N=20k** (median of 5; observed 315–340) → post-fix D1-A (2026-09-27) **~24 µs/event** → deeper work (2026-09-27) **~18.3 µs/event** → timestamp unification, Volmarr-authorized (2026-09-27) **~18.8 µs/event** — see S4 log | **GREEN, thin margin** |
| B2 memory parse | comfortably inside | 0.058 s at corpus size (median of 3); 0.675 s at 10× corpus | GREEN |
| B3 full bridge run | comfortably inside the 120 s cron timeout | observed Verdandi-side (T4-P3 proof watching) | recorded |
| B4 mirror write | — | observed Verdandi-side | recorded |

### Finding SLICE6-F1 — B1 exceeds its budget on this tree (2026-09-27)

The benchmark is red: **~330 µs/event at N=20k** (median of 5;
observed 315–340 across runs), ~17× the 20 µs budget — and per-event cost grows with feed size
(~30 µs at N=100, ~40 µs at N=1k, ~56 µs at N=2k). The roadmap's
~11 µs figure was measured on the small real feed of 2026-09-26;
the per-event cost is not constant.

cProfile on the replay (3k-event synthetic feed, 2.26M calls,
1.475 s) names the target: `VerdandiBridge._add_belief` (1.124 s
cumulative of 1.466 s in `apply_event`) — specifically the
rewrite of repeat-subject beliefs (`emotional_atmosphere`,
`volmarr:delight`, `unnr:mood`, every `utterance`/`emote` rewrites
one). The mechanism is two linear scans per rewrite:
`BeliefComponent.get_belief(subject)` walks `self.beliefs`, then
`beliefs.beliefs.remove(existing)` walks it again — and
`list.remove` compares with pydantic `Belief.__eq__` per element
(280,500 `__eq__` calls in the 3k-event profile). The beliefs list
grows with every unique wish subject, so each rewrite gets slower:
quadratic total, linearly rising per-event cost.

**No fix is applied in this slice.** Per the roadmap (T3-P2) and the
standing additive-only law, a fix needs a profile (have it — above),
before/after numbers, and a decision on the shape of the change
(dict-keyed beliefs vs. the list the ECS components expose). That
decision is routed as **D1** (see `docs/scale-limits.md`): A)
profile-driven perf commit, B) behavior-change mitigation, C) named
acceptance with Volmarr's sign-off. The benchmark stays red until
one of those lands — a red benchmark is a finding, never a silent
skip.

### D1-A resolution — profile-driven fix landed (2026-09-27)

Volmarr selected option A. The fix, profile-driven throughout:

1. **Primary (the quadratic):** `BeliefComponent` now stores beliefs
   in a private subject-keyed ordered dict (`_ordered`); the public
   `beliefs` list is a computed view over it. `get_belief` /
   `update_belief` / `retract_belief` are O(1); revision keeps the
   old move-to-end order; JSON shape and deserialization are
   unchanged (regression tests: `tests/test_belief_component.py`).
   The bridge's `_add_belief` delegates to `update_belief`.
2. **Secondary (measured hot paths):** the event-type → handler map
   is built once per bridge, not per event; anchor entity ids are a
   per-run counter (uuid4 was 3.7µs/anchor; ids are opaque);
   `build_from_events` defers the cyclic GC during the batch replay
   (try/finally); `_serialized_bytes` drops a redundant UTF-8
   encode (exact equivalence — `json.dumps` is ASCII-guaranteed);
   the SELF belief component is cached instead of re-fetched per
   write; anchor tag sets are built in place.
3. **Audit repair (Sólrún, same day):** the in-place `_ordered`
   mutation broke shallow-copy isolation (`model_copy()` shared the
   dict; the old list-rebind writes were copy-safe). `BeliefComponent`
   now overrides `__copy__` to give the copy its own dict —
   `update_belief` stays O(1). Pinned by
   `test_shallow_copy_isolated` in `tests/test_belief_component.py`.

Measured on the same machine, same feeds (median of 5, one warmup):

| feed | pre-fix (2026-09-27) | post-fix (2026-09-27) |
|---|---|---|
| synthetic 20k (B1) | 342.4µs/event | **24.1µs/event** (Sólrún re-run: 28.2µs — machine variance; RED either way) — still RED vs the 20µs budget |
| real nerve feed (2,085 events) | 29.0µs/event | **14.6µs/event** — GREEN |

The real feed — the production workload, replayed every minute —
is under budget. The synthetic stress mix (100% mapped heavy
events; the real feed carries many unmapped/light ones) improved
14× but stops ~4µs over the budget. Floor analysis: per-event cost
is now ~5.8µs security validation (JSON size + depth walk, both
required) + ~9.5µs anchor entity/component (required) + dispatch
and amortized belief/utterance work. Reaching 20µs on the synthetic
mix would require weakening validation, changing the anchor
architecture, or fragile hacks — none taken. B1 stays red as a
finding; the decision (accept 24µs, revise the budget via the
roadmap, or authorize deeper work) is Volmarr's.

### S3 deeper work — Volmarr authorized 2026-09-27, B1 GREEN

Volmarr authorized deeper work on validation/anchors with the
constraint: reach ≤20µs/event on the synthetic mix with no weaker
security validation, no changed public interfaces, no observable
behavior drift.

**Change 1 — fused envelope walk** (`_walk_envelope` in
`src/wyrdforge/hardening/input_validation.py`): the two-pass
`_serialized_within_cap` + `check_depth` sequence was replaced by a
single traversal that accumulates a conservative serialized-size upper
bound while recording the first depth violation's parent-link chain.
Contract preserved exactly: valid payloads pass unchanged; over-depth
reports the same field path; oversized / non-serializable / cyclic
inputs are rejected the same way; the size error keeps precedence over
the depth error; exotic values that defeat the bound fall back to the
exact `json.dumps` measurement. Two bugs were caught by differential
testing before landing (root-depth sentinel; missing final bound
check) — both fixed, both covered by regression tests.

Measured: `validate_event_envelope` 3.16 → 2.36µs/event (saves
0.8µs). Differential proof: 0 mismatches across 6,000 randomized
adversarial payloads (nested, cyclic, alias-shared, deep, oversized,
exotic, invalid keys, huge integers, boundary sizes) plus targeted
hostile cases — old two-pass vs new fused walk agree on every
accept/reject and every error field/reason.

**Change 2 — fused anchor registration**
(`World.create_entity_with_component` in `src/wyrdforge/ecs/world.py`;
`VerdandiBridge._add_anchor` in
`src/wyrdforge/bridges/verdandi_bridge.py`): entity creation and the
single component registration are one method, eliminating the
redundant entity re-lookup between `create_entity` and
`add_component`. The entity and component timestamps use the SAME
Pydantic default factories as before (four separate wall-clock reads)
— the timestamp unification was REVERTED per the anchor-semantics
review: the microsecond-level timestamp values are observable and the
task forbids observable drift. Observable behavior preserved: same
entity IDs, same tags/indexes, same component registration and
validation, same timestamp semantics, duplicate-ID and
entity-ID-mismatch guards unchanged.

**Change 3 — 27 regression tests** (`tests/test_validation_envelope_floor.py`):
fused-walk valid/reject/fallback contracts, the two-pass differential,
and the fused anchor contracts.

Measured on the same machine, same feeds (median of 5, one warmup):

| feed | pre-deeper (2026-09-27) | post-deeper (2026-09-27) |
|---|---|---|
| synthetic 20k (B1) | 28.94µs/event — RED | **~18.3µs/event** (observed 17.0–20.0; pytest B1 5/8 passes — machine-noise flakes at the boundary) — **GREEN but thin margin**; see note below |
| real nerve feed (2,112 events) | 14.6µs/event | **10.65µs/event** — GREEN |

B1 now runs ~8% under its budget. The residual cost is the required
floor: security validation (cannot weaken), Pydantic component
validation (cannot weaken), entity/component registration (required
architecture), and four wall-clock timestamp reads per anchor
(required by the no-observable-drift constraint — unifying them would
save ~2µs but changes microsecond-level timestamp values).

**Note on B1 reliability:** with the timestamp semantics preserved,
B1 measures 17–19µs on a quiet machine but flakes when the VM is
under load (5/8 pytest passes; failures at 20.0–20.4µs). The code
path itself is stable; the margin is thin. If Volmarr authorizes the
timestamp unification (one `now()` read assigned to all four anchor
timestamp fields — no code depends on the microsecond differences),
B1 drops to ~16µs with comfortable headroom (10/11 passes).

Full suite: **1554 passed, 2 skipped, 6 xfailed, 0 failed**
(2026-09-27).

### S4 timestamp unification — Volmarr authorized 2026-09-27

Volmarr explicitly authorized option (a) from the S3 decision gate:
unify the anchor timestamps. One `datetime.now(timezone.utc)` read per
anchor, assigned to all four timestamp fields (entity
`created_at`/`updated_at`, component `created_at`/`updated_at`) — was
four separate default-factory reads.

**The change** (`VerdandiBridge._add_anchor` in
`src/wyrdforge/bridges/verdandi_bridge.py`;
`World.create_entity_with_component` in `src/wyrdforge/ecs/world.py`
gained an optional `stamp` parameter):

- `_add_anchor` reads `now = datetime.now(timezone.utc)` once, passes
  it as `created_at`/`updated_at` to `TemporalAnchorComponent(...)`
  and as `stamp=now` to `create_entity_with_component`.
- `create_entity_with_component(..., stamp=None)`: when a stamp is
  provided the entity gets `created_at=updated_at=stamp` (no
  default-factory reads); when None, the dataclass default factories
  do their own reads — exactly the old behavior for other callers.
- Volmarr's authorization covers the semantic change: the microsecond
  differences between the four old reads were implementation noise,
  not a contract — no code depends on them differing, no tests assert
  they differ. The meaning ("when the anchor was created") is
  preserved. `valid_from` / `valid_until` / `observed_at` (the domain
  time of the anchor) are untouched.

**Regression tests** (`tests/test_validation_envelope_floor.py`): the
two tests that pinned the old four-read behavior were rewritten to pin
the new contract — `test_stamp_unifies_entity_timestamps`
(`entity.created_at is stamp and entity.updated_at is stamp`; the
identity pins that no extra datetimes were constructed),
`test_no_stamp_uses_default_factories` (without a stamp the old
wall-clock behavior is preserved), and
`test_anchor_unifies_timestamps` (all four anchor timestamps are the
identical object, bracketing the `_add_anchor` call).

**Measured** (same methodology — median of 5, one warmup):

| feed | pre-unification (S3, 2026-09-27) | post-unification (2026-09-27) |
|---|---|---|
| synthetic 20k (B1) | 20.6µs/event on the loud run (four reads) | **~18.8µs/event** median on quiet runs (observed 17–23 across runs; pytest B1 9/10 invocations green) — **GREEN, thin margin** |
| real nerve feed (2,115 events) | 10.65µs/event | **11.72µs/event** — GREEN |

The unification saved the predicted ~2µs (the S3 profile: 89,344
`datetime.now()` calls, 0.038s = 1.9µs/event — the per-anchor clock
cost is now one read, not four). The remaining floor is the required
work: security validation, Pydantic component validation,
entity/component registration. Honest note: machine variance on this
VM tonight (±2–3µs — memory flapping, hub restarts, minute-crons)
dominates the remaining margin, so B1 sits under budget without the
headroom the quiet-machine projection suggested. The code path is
stable; the margin is the machine's.

Full suite: **1555 passed, 2 skipped, 6 xfailed, 0 failed**
(2026-09-27) — B1 passes in-suite.

## Corpus size the memory budget is tied to

B2's "current corpus size" (real tree, 2026-09-27):

- `~/MEMORY.md`: 107 lines / 75 bullets
- `~/memory/bank/*.md`: 4 files, 1,908 lines / 1,896 bullets
- daily logs: last 7 days only (5 logs present, 1,364 bullets)
- `~/memory/people/*.md`: 4 `PERSON_ROSTER` pages parsed (of 13 files)

The synthetic tree (`tests/perf_fixtures.py::build_memory_tree`,
`scale=1`) reproduces these counts. **Re-baseline rule:** when the
real corpus doubles on any axis, re-measure B2 and record the new
baseline here — the budget (5 s) does not move silently, and the
corpus does not grow silently past it.

## T3-P2 — profile before touching (the rule, stated in full)

Track 3 Phase 2's acceptance is this policy, not code:

> No optimization work begins without a profile showing where the
> time goes. `cProfile` on the target path, numbers mandatory, flame
> graph optional. Every optimization commit links its profile output
> in the commit message, with before/after numbers — same machine,
> same feed size, three runs each. **The profile names the target,
> or there is no target.**

There are no optimization commits in this slice, so the rule is
stated and pinned, not exercised. When SLICE6-F1's D1 resolves to
option A, the resulting commit cites the profile above and carries
before/after numbers in the bug-ledger style.

## Deliberately not optimized

The pure-projection rebuild — `build_from_events` replaying into a
*fresh* world, no snapshot, no incremental cache, no drift — is
**never** "optimized" into a cache. That trade was rejected in the
architecture and the rejection is permanent. Speed never buys the
mirror's honesty.
