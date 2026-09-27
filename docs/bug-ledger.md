# Bug Ledger

Append-only. Every confirmed bug gets: date found, how it was observed,
reproduction, root cause, the fix, the test that pins it. The ledger is the
memory of the codebase's bruises — the code forgets nothing twice.

Companion record for operational incidents: [docs/incident-record.md](incident-record.md).
Bugs resolve (fixed / open / quarantined); incidents never close — they become
standing law. Roadmaps: Track 2 (this file), Track 6 (the incident record).

---

## Triage — updated 2026-09-26

- **Bleeding:** none — quiet.
- **Limping:** BUG-004 verification open (fix in place 2026-09-26; awaiting
  the first qualifying state change to prove a genuine reflection publishes.
  Silence is the default, so this may take days. Not a failure — a pending proof.)
- **Cosmetic backlog:** none.

Rule: silence when the list is empty. The dated line is refreshed whenever
triage changes — never silently.

---

## Entry schema

### BUG-NNN

```markdown
### BUG-001 — <short title>
- **Severity at find:** bleeding | limping | cosmetic
- **Date found:** YYYY-MM-DD (add HH:MM TZ when it matters)
- **Observed:** PROVEN | OBSERVED — exact symptom, exact error text verbatim
- **Reproduction:** steps, or the test that fails on broken code
- **Root cause:** ...
- **Fix:** what changed (commit when known) — additive
- **Pinning test:** <path::test_name> — suite result
- **Status:** fixed YYYY-MM-DD | open | quarantined (reason, owner, re-check date)
```

### AUDIT-Fn (Wave D findings that are not all bugs)

```markdown
### AUDIT-F1 — <short title> (Wave D, Sólrún)
- **Disposition:** fixed | noted (not code) | deliberately not applied (ordered out of scope)
- **Detail:** ...
```

---

## Entries

### BUG-001 — httpx AsyncClient proxy-env crash
- **Severity at find:** bleeding
- **Date found:** 2026-09-25
- **Observed:** PROVEN — `httpx` `AsyncClient` crashed on this machine's proxy env vars.
- **Reproduction:** instantiating the relay client with the machine's proxy
  environment variables set.
- **Root cause:** httpx honored proxy environment variables that break the
  client in this environment.
- **Fix:** `trust_env=False` — additive.
- **Pinning test:** relay suite, 68/68.
- **Status:** fixed 2026-09-25

### BUG-002 — every relay route returned 422
- **Severity at find:** bleeding
- **Date found:** 2026-09-25
- **Observed:** PROVEN — every cloud-relay route returned 422.
- **Reproduction:** any request against the relay routes with
  `from __future__ import annotations` plus function-local FastAPI imports.
- **Root cause:** `from __future__ import annotations` combined with
  function-local FastAPI imports — annotations resolved as strings, FastAPI
  could not build the route models.
- **Fix:** imports moved to module level with graceful fallback — additive.
- **Pinning test:** relay suite, 68/68.
- **Status:** fixed 2026-09-25

### BUG-003 — reflection seq-collision edge
- **Severity at find:** limping (design edge, guarded before it could bite)
- **Date found:** 2026-09-26
- **Observed:** PROVEN (by test) — reflection entity id is `reflection:<seq>`;
  a seq collision must never overwrite an existing reflection.
- **Reproduction:** `tests/test_verdandi_bridge_waveb.py:248`
  (`test_reflection_seq_collision_refused_not_overwritten`) — passes against
  the guard.
- **Root cause:** n/a — guarded by design; a collision means the seq source
  has a publishing bug upstream.
- **Fix:** collision refused, never overwritten — guard at
  `src/wyrdforge/bridges/verdandi_bridge.py` (~lines 794–799, 839).
- **Pinning test:**
  `tests/test_verdandi_bridge_waveb.py:248::test_reflection_seq_collision_refused_not_overwritten`
  — passes.
- **Status:** fixed 2026-09-26 (guarded by design — collision refused, never overwritten)

### BUG-004 — reflection-pass schema bug
- **Severity at find:** limping (one failed step; bridge, inbound watch, and
  sweep stayed healthy)
- **Date found:** 2026-09-26 20:49 EDT
- **Observed:** PROVEN — the cron's reflection step died with
  `AttributeError: 'list' object has no attribute 'items'`; no reflection published.
- **Reproduction:** the heartbeat cron's reflection instructions assumed the
  wrong mirror schema (treated list values as dicts).
- **Root cause:** the cron's reflection instructions assumed the wrong mirror
  schema — treated list values as dicts.
- **Fix:** corrected the instructions with the actual schema — `entities` is
  an int count; `anchors`, `utterances`, `beliefs`, `senses`,
  `memory_beliefs`, `reflections`, `sense_transitions` are lists.
- **Pinning test:** none — instruction fix, not code; verification is live.
- **Status:** fixed 2026-09-26; **VERIFICATION OPEN** — as of this writing no
  later run has proven the repaired pass published a genuine reflection.
  Tracked in triage as limping. This entry must NOT be rewritten as verified
  until a qualifying state change is observed live.

### AUDIT-F1 — cosmetic docstring numbering (Wave D, Sólrún)
- **Disposition:** fixed
- **Detail:** `wyrd_inbound.py:29-36` renumbered in Wave E. Note: that file
  lives in the Verdandi repo (`~/workspace/repos/Verdandi/`), outside this
  tree — recorded here because the audit covered the workstream, location
  stated plainly.

### AUDIT-F2 / AUDIT-F3 — report-accuracy notes (Wave D, Sólrún)
- **Disposition:** noted (not code)
- **Detail:** Sólrún's accuracy notes on reporting; no code change required
  or made.

### AUDIT-F4 — stale §9 acceptance criterion (roster) (Wave D, Sólrún)
- **Disposition:** fixed
- **Detail:** corrected in the architecture doc during Wave E.

### AUDIT-F5 — §7 cron diffs (Wave D, Sólrún)
- **Disposition:** deliberately not applied (ordered out of scope)
- **Detail:** Volmarr's order excluded the §7 cron changes; the finding is
  recorded, not applied. Re-opening needs his word.
