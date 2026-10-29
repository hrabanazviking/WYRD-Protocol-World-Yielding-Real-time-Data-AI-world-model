# Verdandi Nerve-Feed Contract — the WYRD ↔ Verðandi Seam

*Phase D6 of the WYRD advancement roadmap (§8 / §9 D6). The prose half
of the seam contract; the machine-readable half is
`tests/fixtures/nerve_feed_contract_v1.json`, and the code half is
`wyrdforge.bridges.verdandi_bridge` (`NERVE_FEED_SCHEMA_NAME`,
`NERVE_FEED_SCHEMA_VERSION`, `NERVE_FEED_TRANSLATION_TABLE`).*

## The seam, and why it stays a seam

Verðandi is the nervous system: it owns *signals* — ephemeral,
high-rate, liveness and heartbeat; a signal's meaning expires. WYRD is
the world model: it owns *facts* — durable, queryable ground truth; a
fact's meaning persists. They connect **by contract, never by
merger**: Verðandi stays world-agnostic (it serves consumers with no
world model at all) and WYRD stays nerve-agnostic (most WYRD consumers
have no Verðandi). The bridge is the seam; the seam is the design.

The contract surfaces are exactly four:

1. **The nerve feed** (Verðandi → WYRD, append-only, replayable) —
   this document's subject.
2. **The registry handshake** (identity/reality boundary): the mirror
   world identifies itself via `World.identify()` as
   `heimr-wyrd-unnr`, reality `manifest` — it models manifest
   entities (the self's inner life as the nerve records it), so per
   the Slice-0 rule it is manifest-tagged, not potential-tagged.
3. **The nerve socket** (WYRD → Verðandi, notifications only):
   `bridges/runa_awareness.py` and `bridges/hermes_bridge.py` publish
   WYRD-derived awareness onto the nervous system, fire-and-forget.
   Neither side stores the other's state.
4. **The mirror projection** (WYRD → consumers): `summary()`'s plain
   data. Consumers read the mirror/Oracle like any other consumer.

**The EventBus never crosses the boundary.** Verðandi does not
subscribe to WYRD's bus; WYRD does not publish onto the nerve except
through surface 3's notifications.

## The mirror doctrine

The mirror world is a **pure projection** of the nerve feed: every
run replays the recent feed (24 h window, `WYRD_BRIDGE_HORIZON_HOURS`
on the runner) into a *fresh* world. No snapshot format, no drift —
the feed is the log, the world is the reading. Events older than the
window leave the mirror (they remain in the feed); the mirror is
recent becoming (verðandi), not the whole of urðr.

Two things are deliberately *not* feed events:

- **Senses bypass the nerve.** Machine telemetry (memory headroom,
  hub state, queue depth, feed rate) is sampled by the runner and
  attached straight to `env:machine` (`attach_senses`). The feed is
  the authority for what the self *experienced*; telemetry is not
  experience, and 1,440 telemetry lines a day would drown it.
- **The mirror's own witness.** `wyrd_mirror_synced` and the
  divergence watch's output are never mapped back — the mirror does
  not watch itself watching. The self-reflection loop is throttled
  (≤ 1/minute), depth-capped at 1, and deduped by content hash over
  24 h; reflection *content* is always the thinking worker's own
  words, verbatim — no code drafts a thought.

## Feed envelope — schema `wyrd-nerve-feed`, version 1

The pre-version feed shape **is** version 1; D6 pinned it, it did not
redesign it. Each JSONL line of `nerve_feed.jsonl` is one envelope:

| Key | Written by | Meaning |
|---|---|---|
| `type` | publisher | nerve event type (string, required) |
| `data` | publisher | event payload object (required, may be empty) |
| `source` | publisher | publishing source name (optional) |
| `_seq` | nerve hub | hub sequence number, strictly increasing |
| `_ts` | nerve hub | epoch seconds when the hub stamped the event |
| `_iso` | nerve hub | ISO-8601 form of `_ts` (optional) |
| `schema` | publisher/hub | schema version (optional in v1 — **absent means 1**) |

### Versioning rules

- An entry with no `schema` key is a v1 entry. Every feed file ever
  written is v1 and keeps replaying unchanged.
- An entry may declare `"schema": 1` explicitly; it is treated
  identically.
- An entry declaring **any other version** — newer, older, or
  malformed (non-integer, bool, ≤ 0) — is **unsupported**: the bridge
  quarantines it. Quarantine means: the entry is *not mapped*, it is
  recorded verbatim in `VerdandiBridge.feed_quarantine` with the
  declared version and the refusal reason, a warning is logged, and
  the refusal is counted in `mirror_health()`. The bridge never
  guesses at a future feed's meaning — silently mis-translating
  someone's inner life is the one failure this seam must not have.
- A future v2 (if one is ever designed) is a joint change: this
  document, the fixture, the translation table, and the Verðandi
  producer move together, and the bridge learns the new version
  deliberately — never by a producer starting to emit it first.
- Within a supported version, an **unknown event type** is unmapped:
  it returns None, changes nothing, and is counted as unmapped in the
  health metric. Deliberately unmapped types (routine noise, the
  runner's own witness, retired/game families) are listed in
  `DELIBERATELY_UNMAPPED_FEED_TYPES` /
  `DELIBERATELY_UNMAPPED_FEED_PREFIXES` in the bridge module.

## Event → mutation translation table (v1)

The declarative table lives in code as
`NERVE_FEED_TRANSLATION_TABLE`; a pinning test fails if it ever
drifts from the bridge's handler map. In prose (anchor tense uses the
engine's tense vocabulary: `verdhandi` = becoming, `urdhr` = already
past):

| Event type | Mirror mutation |
|---|---|
| `mood_shift` | verdhandi anchor "mood: …" + belief `unnr:mood` about the new mood |
| `wish_made` | belief `wish:<wish_id>` "I want: \<text\>" (observed, 1.0) + verdhandi anchor |
| `wish_pursued` | verdhandi anchor "pursuing: \<text\>" |
| `wish_fulfilled` | urdhr anchor "fulfilled: \<text\>" + belief it is fulfilled |
| `wish_released` | urdhr anchor "released: \<text\>" |
| `reward` | belief `volmarr:delight` "Volmarr showed delight (…)" (observed, 1.0) + verdhandi anchor — a belief *about his observed reaction*, attributed, never absorbed |
| `shadow` | verdhandi anchor "shadow: \<signal\>" |
| `joy_struck` | verdhandi anchor "joy: \<what\>" |
| `utterance` | verdhandi anchor "\<speaker\> said: …" + `UtteranceComponent` holding the full text and named emotions (+ atmosphere belief when emotions are named) |
| `emote` | verdhandi anchor "\<speaker\> \<emote\> (…)" + the `emotional_atmosphere` belief rewritten (observed, 0.9) |
| `work_started` / `work_finished` | verdhandi / urdhr anchor "work began: …" / "work \<outcome\>: …" |
| `job_start` / `job_end` | verdhandi / urdhr anchor "job started: …" / "job ended: …" |
| `mythic_law_breach` | verdhandi anchor "law breach: \<law\> (\<file\>)" |
| `arc_opened` / `arc_closed` | verdhandi / urdhr anchor "arc opened: …" / "arc closed: …" |
| `entity.relationship_updated` | verdhandi anchor "bond: \<entity\> is \<status\> (trust …)" |
| `self_recognized` | verdhandi anchor "self-recognition: n/m aligned" |
| `self_reflection` | `ReflectionComponent` on `reflection:<seq>` (thought verbatim) + verdhandi anchor + `unnr:self-understanding` belief (inferred, 0.8); depth ≥ 2, empty thoughts, 24 h duplicates, and seq collisions are refused |

Identity firewall, both directions (unchanged by D6): nerve events
become ground truth about the self entity potential-tagged *unless*
the nerve itself recorded them as manifest — the mirror world is
manifest because it models manifest entities (see surface 2); MTOM
realities never leak across the boundary.

## Mirror-lag health metric

`VerdandiBridge.mirror_health()` returns a plain dict of measured
values (the `EventBus.snapshot()` / store `count_*()` house style —
numbers a caller can poll, not a log line):

- `feed_events_seen / _mapped / _unmapped / _refused / _torn /
  _quarantined` — every entry the bridge was presented with, by
  outcome. *Refused* = a mapped type whose handler refused the
  instance (the self-reflection guards, malformed payloads).
- `newest_feed_at` / `newest_mirrored_at` — ISO timestamps of the
  newest feed entry seen and the newest entry actually mirrored.
- `mirror_lag_seconds` — `newest_feed_at − newest_mirrored_at`
  (None until both exist). An entry seen but not mirrored holds the
  mirror's watermark back, so lag names exactly what the mirror is
  behind by.
- `newest_feed_seq` / `newest_mirrored_seq` / `mirror_lag_events` —
  the same gap in hub `_seq` numbers, present when entries carry
  `_seq` (feed-file replay does; direct `apply_event` calls do not,
  and report None rather than an invented number).
- `schema`, `schema_version`, `world_id`, `reality`, `entities` —
  the seam's identity, so a poller can tell *which* contract a
  health reading belongs to.

## Replay determinism (pinned)

Same feed window → same mirror. `build_from_events` constructs a
fresh world per replay and every handler is a pure function of
(entry, ledger), so replaying one fixture feed twice — or after
intervening unrelated state — yields identical `summary()` and
health fingerprints. This is pinned in
`tests/test_verdandi_seam_hardening.py`, including at benchmark-feed
scale. If a future change ever makes replay nondeterministic, that
test is the alarm: the whole projection doctrine rests on it.

## Shared contract tests & the Verðandi-side adoption step

The contract tests live in the WYRD repo's core suite
(`tests/test_verdandi_seam_hardening.py` +
`tests/fixtures/nerve_feed_contract_v1.json`), which the repo's CI
already runs (`pytest tests/` in `.github/workflows/ci.yml` —
manual-only `workflow_dispatch` per Volmarr's standing rule; D6 did
not touch workflow triggers). The fixture is plain JSON with no
Python-specific content so the other repo can consume it unchanged.

**Adoption step for the Verðandi repo** (`hrabanazviking/Verdandi` —
producer `nervous_system.py`, runner `wyrd_bridge.py`; recorded here
and in the campaign state files; D6 deliberately does not push to
that repo, which is outside the WYRD campaign's established push
pattern):

1. Vendor a copy of `tests/fixtures/nerve_feed_contract_v1.json`
   into the Verðandi repo's `tests/fixtures/`.
2. Add a producer test asserting the hub's stamped envelopes match
   the fixture's `envelope` shape (keys `type`/`data` required,
   `_seq`/`_ts` stamped, `schema` absent-or-1).
3. Add a runner test replaying the fixture's `cases` through the
   real bridge (the import pattern `tests/test_wyrd_bridge.py`
   already uses) and asserting each `expect` block, plus the
   `quarantine_cases` producing quarantine records — not mappings.
4. Optionally, have the hub stamp `"schema": 1` explicitly on new
   feed lines (the bridge accepts it identically) and have
   `wyrd_bridge.py`'s run surface `mirror_health()` in its witness
   payload; neither is required for correctness today — the runner's
   current `apply_event` loop is already health-tracked.
