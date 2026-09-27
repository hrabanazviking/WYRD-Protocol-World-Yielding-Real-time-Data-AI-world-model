# Scale Limits

**Wave G Slice 6 (Track 3 P3) · 2026-09-27 · the roadmap's honest
scale record:** synthetic scale tests — 10× feed size, 10× memory
corpus, 2× horizon — measure where each budget breaks, in numbers.
The machinery lives in `tests/test_scale_limits.py` (fails if a
scale run *errors*, never if one is merely slow); this doc holds the
judgment. **Zero breaking points silently accepted:** every one gets
a fix, a mitigation, or a named pending item below.

All measurements on this machine, 2026-09-27, fixtures in
`tests/perf_fixtures.py` (seeded, deterministic).

## S1 — 100,000-event feed (10× the B1 benchmark feed)

`VerdandiBridge.build_from_events` over 100k mixed-type synthetic
events (every mapped handler exercised):

| Feed size | Wall | Per-event | vs 20 µs budget |
|---|---|---|---|
| 20 events | 0.61 ms | 30.5 µs | **breached** |
| 75 events | 2.18 ms | 29.1 µs | **breached** |
| 2,000 events | 0.111 s | 55.7 µs | breached ×2.8 |
| 20,000 events | 6.6 s | 331 µs | breached ×17 |
| 100,000 events | 167.8 s | 1,678 µs | breached ×84 |

**Breaking point: below N=20.** The 20 µs/event budget is exceeded
at *every* measured feed size — even 20 events run at ~30 µs/event.
Two components: a ~30 µs/event floor (bridge construction and
per-event fixed costs amortized over the run), then quadratic growth
as the beliefs list lengthens (the 100k run costs ~25× the 20k run —
quadratic, as predicted). Root cause is the same as finding
SLICE6-F1 (`docs/performance-budgets.md`): the repeat-subject belief
rewrite is two linear scans per event with pydantic `__eq__` per
element.

**Disposition: pending D1 — SLICE6-D1.** Not fixed in this slice.
Routed to Volmarr with the plan's three named options, no assumed
answer:
- **A)** Fix in code — profile-driven perf commit under the T3-P2
  rule (profile already in hand: `docs/performance-budgets.md`
  SLICE6-F1; before/after numbers, same machine, three runs each).
- **B)** Mitigate with a named, dated, announced behavior change
  (e.g. cap the replay window, bound the beliefs list) — the
  pure-projection rebuild is never "optimized" into an incremental
  cache; that rejection is permanent and not on the table.
- **C)** Accept the limit as a named fact, with his sign-off,
  recorded here.

## S2 — 10× memory corpus

`parse_memory_beliefs` over a synthetic tree at 10× the current
corpus (~19k bank bullets, ~13.6k daily bullets, 10× person pages):

| Corpus | Parse (median of 3) | vs 5 s budget |
|---|---|---|
| 1× (current) | 0.058 s | GREEN — 86× headroom |
| 10× | 0.675 s | GREEN — 7.4× headroom |

**Breaking point: none found up to 10×.** Growth is roughly linear
in bullet count; linear extrapolation puts the 5 s budget at roughly
~70× the current corpus — an extrapolation, not a measurement. The
corpus would have to grow seventy-fold to threaten the budget; the
re-baseline rule in `docs/performance-budgets.md` (re-measure when
the corpus doubles) will catch it decades before that.

**Disposition:** no action needed. Recorded headroom is the
roadmap's asked-for fact.

## S3 — 2× horizon analogue (repo side)

The roadmap's "2× horizon" is the 24h Verdandi-side projection
horizon — **observed in the mirror, not repo-benchmarked**; this
repo cannot fake measurability of the heartbeat worker. The
repo-side analogue is world anchor density: `summary()` (the mirror
projection build) over worlds built from 2k vs 4k events:

| Anchors | `summary()` wall |
|---|---|
| ~2,000 (1×) | 0.023 s |
| ~4,000 (2×) | 0.017 s |

**Breaking point: none** — noise-level, no budget attached (context,
not enforcement, per the budgets doc). The projection build is not
the bottleneck anywhere near current or 2× density.

## Pending items

- **SLICE6-D1** (from S1 / SLICE6-F1): feed-replay budget breached
  at every measured scale. Awaiting Volmarr's routing: fix (A),
  mitigate (B), or named acceptance (C). The B1 benchmark test
  stays red until this resolves.
- *None other.* The memory-parse and projection paths hold with
  measured headroom; no silent acceptances.
