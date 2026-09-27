# Incident Record

Track 6 — self-healing grounded in real incidents. The system learns from
what actually happened to it — not from imagined failure modes. Where the
cause is unknown, this document says so, in plain words.

Companion record for bugs: [docs/bug-ledger.md](bug-ledger.md).
Bugs resolve (fixed / open / quarantined); incidents never close — they
*become standing law*. "The ledger entry and the standing rule are the whole
ceremony." No post-mortem theater.

---

## INCIDENT 1 — The nerve-hub disappearances

- **Date:** 2026-09-26. **Tag:** OBSERVED, cause UNPROVEN.

**What happened:** the Verdandi nerve hub disappeared three times. The
watchdog and self-repair resurrected it each time; the mirror work
continued. Duplicate reports were not counted as additional crashes.

**What is NOT established:** that memory pressure (OOM) caused these.
That hypothesis was floated and remains a hypothesis. Stating it as fact
would violate the standing rule below.

**What the incident proved (PROVEN):** detection works (noticed, not
silent); resurrection works (watchdog + self-repair); the cost of the
unknown — every future disappearance still starts from zero diagnosis.

**Standing rule:** (1) Instrument before theorizing. (2) Never fail
silently — Volmarr is looped in briefly with facts, not theories:
"hub down at HH:MM, resurrected at HH:MM, evidence attached, cause
unknown." (3) No claimed root cause until proven — five evidence bundles
with the same signature, or it stays unknown.

**Measure:** time-to-detect ≤ 1 heartbeat; time-to-resurrect ≤ 2 heartbeats
(already achieved — now requirements, not luck). Every future hub death
produces an evidence bundle, 100%, no exceptions.

---

## INCIDENT 2 — The 19:55 mid-edit read

- **Date:** 2026-09-26 19:55 EDT. **Tag:** OBSERVED → rule PROVEN by adoption.

**What happened:** the 1-minute heartbeat worker read `wyrd_bridge.py`
while it was being edited — a half-written file — and died with
`'tuple' object is not callable`. The next run read the finished file and
succeeded: self-healed in one minute, no intervention. The flaw was ours,
not the worker's: editing a live-read file in place is a race.

**Standing rule (PROVEN by adoption in Wave E):** atomic swap for any file
a running process reads — stage the new version in `/tmp`, syntax-check it
(`python -m py_compile`), then `os.rename` it over the live path. Readers
see the old file or the new file, never a half-written one.

**Generalization:** the rule covers every file the heartbeat touches
(`wyrd_bridge.py`, `wyrd_inbound.py`, cron bodies, Heilsiðr scripts).
The cron body gains it as a prohibition.

**Measure:** 0 torn-read incidents after adoption (counted from 2026-09-26
19:55; currently 0 — the target is keeping it there).

---

## INCIDENT 3 — The forge-queue corrupt file

- **Date:** 2026-09-26 (forge-queue build). **Tag:** PROVEN pattern.

**What happened:** the FIFO forge queue met a corrupt job file and did the
right thing: announced it once as unparseable, moved it to `quarantine/`,
kept the queue moving, stayed silent about it on the next drain. Never
silently dropped, never blocking, never nagging.

**Standing rule:** quarantine, don't delete; announce once, don't nag.
This is the template for Track 5's generalization — the queue proved the
pattern before the roadmap generalized it. Code home:
`~/workspace/machine-health/` (forge queue; outside this repo) —
referenced here, not duplicated.

**Measure:** after Track 5 P1, the three properties hold per state file:
corrupt input never blocks the pipeline; nothing silently dropped;
announcement fires exactly once. (Chaos-test assertions — future track.)

---

## INCIDENT 4 — The ledger's graceful degradation

- **Date:** 2026-09-26 (Wave C design). **Tag:** PROVEN design.

**What happened:** the entity ledger
(`~/.hermes/state/wyrd_entity_ledger.json`) was designed so missing or
corrupt → fresh empty maps, and the run continues. Exactly two maps
(`last_sense_status`, `reflection_seen`); nothing load-bearing lives
there. Delete it and the run loses only transition-detection and
reflection dedup for a run or two — both self-heal. Tested: the ledger
self-heal test passes on corrupt/missing file.

**Standing rule:** no load-bearing state in mutable convenience files. A
mutable file holds the *minimum* no other source provides — bloat in a
convenience file is future corruption surface. (Already stated in the
`verdandi_bridge.py` module docstring: "The ledger is a convenience, not a
foundation.")

**Measure:** audit list of every mutable runner file — load-bearing
contents must be none; degraded behavior on missing/corrupt must be
documented. 0 files where deletion breaks the run. (Full audit is Track 5/6
future work; the rule is recorded now.)

---

## Evidence-bundle format (Incident 1's measurable target)

```json
{
  "schema_version": 1,
  "incident": "hub-disappearance",
  "detected_at": "2026-09-26T20:14:00-04:00",
  "resurrected_at": "2026-09-26T20:15:00-04:00",
  "last_heartbeat_at": "2026-09-26T20:13:41-04:00",
  "mem_available_kb_before": 412000,
  "mem_available_kb_after": 398000,
  "exit_code": null,
  "exit_signal": null,
  "watchdog_log": ["hub missing at 20:14:02, respawned pid 12345"],
  "cause": "unknown",
  "cause_evidence": []
}
```

**Rules of the format:** any evidence field may be `null` — null means "not
obtainable," never invented. `cause` defaults to `"unknown"`; `cause` may
only differ from `"unknown"` when `cause_evidence` is non-empty (enforced
by `validate_evidence_bundle` in `src/wyrdforge/incident_evidence.py`).
**Storage:** runtime state, NOT the repo —
`~/.hermes/state/hub_evidence/hub-death-YYYYMMDD-HHMMSS.json`.
**Naming:** local time of detection.

---

## Documented follow-up (NOT built in this slice)

Verdandi-side future work, specified here so it is not lost: on hub
resurrection, the Verdandi-side watchdog should collect the four facts —
last heartbeat timestamp, `MemAvailable` before/after from the existing
Heilsiðr mem sense (no new measurement), process exit code/signal if
obtainable, the watchdog's own log lines — and write them in the format
above. That code lives in the Verdandi repo; local Verdandi runner changes
are never pushed to any repo, so it is specified here and built there on
Volmarr's word.
