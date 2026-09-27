# Hardening Roadmap — WYRD Protocol

**Role:** Strategist · **Wave:** F · **Date:** 2026-09-26
**For:** Volmarr's eyes.

## Standing at the start

The world model works. The Verdandi expansion (Waves A–E) added senses,
persistent entities, memory-fed beliefs, and a self-reflection loop with
four anti-loop guards — all test-verified, all additive, zero new
daemons. The mirror keeps its contract: **pure projection, no drift.**

This document is not a feature list. It is the plan for making what
exists **hard to break, honest when it breaks, and self-repairing when
it does.** Seven tracks. Each one states its phases, its acceptance
criteria, its measurable targets — and its non-goals, because a
hardening plan without stated non-goals eventually becomes scope creep.

**Status: plan only. Nothing here is authorized.** No code, no cron,
no live system is touched by this document. Each track starts only on
your word.

## How claims are marked

Every statement in this roadmap carries a tag. You asked for honesty
about what is proven and what is not, so the tags are load-bearing:

- **PROVEN** — test-verified or audit-verified in this workstream.
- **OBSERVED** — seen live, described exactly, root cause unknown.
- **ASPIRATIONAL** — the goal. Not proven, not observed. Yet.

Where a target cannot be measured yet, the track says *what would make
it measurable* instead of inventing a number.

## Inherited law

These are not negotiable; they constrain every track below:

1. **Additive-only bug fixing.** Repair, never rewrite. A fix that
   deletes a working mechanism to add a fancier one is a regression
   wearing a coat.
2. **No pseudocode, ever.** Every change is fully working production
   code with tests, or it does not ship.
3. **No new daemons, no new cron jobs, no new polling.** The expansion's
   architecture proved the discipline: fold into the existing runner,
   or do not build it.
4. **The world stays disposable.** Pure projection, no drift. No
   incremental-world shortcuts, ever (the architecture doc's §2
   rejection stands permanently).
5. **Never fail silently; never invent a cause.** The standing rule
   from the 2026-09-26 work (see Track 6): when I hit something I
   can't do or don't understand, I say so in one plain sentence and
   stop. No covering scaffolding.

---

# Track 1 — Security hardening

**Objective.** The world model must be safe to hand untrusted input:
world files from other people, events from other bridges, HTTP
requests from the local network. "Local-first" is not a security
strategy; it is an excuse until the hardening is done.

## Threats, stated plainly

- **World files are code-adjacent.** `configs/worlds/*.yaml` load into
  entity graphs; a malicious or malformed file is the first attack
  surface anyone touches.
- **The HTTP bridge listens.** `WyrdHTTPServer (:8765)` and the cloud
  relay expose `/world`, `/query`, `/event`. The relay has Bearer auth
  (**PROVEN**, tested); the local bridge's exposure model is "localhost
  is a moat" — which fails the moment the machine is on a LAN someone
  else walks.
- **SQLite + FTS5 queries** (`PersistentMemoryStore`) take
  search strings; injection through search text is the classic.
- **The registry executes registered code.** `@register_component`
  classes are Python — a poisoned module on the path is a poisoned
  world.
- **Dependencies.** The `[llm]` extra (`sentence-transformers`) was
  deliberately skipped after proving it buys zero functionality.
  That instinct is now policy: every dependency must earn its place.

## Phases

### T1-P1 — Input validation at every trust boundary (first)
Every boundary where untrusted or semi-trusted bytes enter gets a
validator that fails closed:

1. **World-file load:** schema-validate every YAML world config
   against a declared schema *before* entity construction. Unknown
   fields → hard error naming the field, never silent acceptance.
2. **Event ingest:** every event pushed through the HTTP bridge or the
   Verdandi bridge gets the same treatment the `self_reflection`
   handler already models: type check, field check, depth/length
   bounds (`depth ≤ 1` is the precedent — bounds live in the type,
   not in hope).
3. **FTS5 search:** search strings are bound parameters, never string
   interpolation. Audit every raw-SQL site in the store.

**Acceptance.** A fuzz corpus of 200 malformed inputs (torn YAML,
over-deep JSON, 10 MB single events, SQL metacharacters in search
strings) runs against all three boundaries; zero crashes, zero silent
acceptance, every rejection naming the offending field.
**Measurable target:** 200/200 handled, 0 unhandled exceptions, and the
corpus lives in `tests/` so it re-runs on every change.
**What would make it measurable sooner:** the corpus itself — write it
first, before the validators.

### T1-P2 — Auth and exposure review
1. Confirm Bearer auth on **every** HTTP surface, not just the relay;
   document which port binds to what interface in one place.
2. Default-deny CORS; any widened origin is a named, dated decision in
   the docs.
3. `trust_env=False` for all HTTP clients (the cloud-relay proxy-env
   crash of 2026-09-25 is the precedent — **PROVEN** real bug, fixed).

**Acceptance.** A port-scan + auth-probe script in `tests/` proves:
no unauthenticated write path, no route without a test.
**Measurable target:** 0 unauthenticated write endpoints reachable.

### T1-P3 — Dependency and secret hygiene
1. `pip-audit` (or equivalent) on the venvs; every flagged CVE gets a
   named disposition (patched, pinned, accepted-with-reason).
2. Repo-wide secret scan (no tokens, no keys, no `.env` committed);
   the GitHub token lives in the Secure Vault and stays there —
   nothing in this track changes that.
3. Every dependency in `pyproject.toml` carries a one-line
   justification comment. Anything unjustified is a removal
   candidate.

**Acceptance.** Clean audit output committed to the repo as a dated
record; secret scan clean.
**Measurable target:** 0 high-severity CVEs unaddressed; 0 secrets in
tree.

## Track 1 non-goals
- No new auth *system* (no OAuth server, no user management). Bearer
  tokens and localhost defaults are the model; the goal is proving the
  existing model, not replacing it.
- No sandboxing of component code. Registered components are trusted
  code; the boundary is at *input*, not at *execution*.
- No threat model for nation-state actors. The adversary is a bad
  file, a curious LAN neighbor, and our own carelessness.

---

# Track 2 — Systematic bug correction

**Objective.** Bugs are found the same way every time, fixed the same
way every time, and stay fixed. No more "I think I saw this before."

## Phases

### T2-P1 — The bug ledger
One file, `docs/bug-ledger.md`, append-only. Every confirmed bug gets:
date found, how it was observed, reproduction, root cause, the fix,
the test that pins it. The ledger is the memory of the codebase's
bruises — the code forgets nothing twice.

**Precedent (PROVEN):** the 2026-09-25 cloud-relay fixes —
(1) `httpx` `AsyncClient` crashing on proxy env vars, (2) every route
422ing from `from __future__ import annotations` + function-local
FastAPI imports. Both were real bugs, both got fixes *and* tests
(68/68 relay tests), both would be the ledger's first entries,
backfilled.

**Acceptance.** Ledger exists with the two relay bugs, the F1–F5 audit
findings, and the seq-collision edge backfilled; every future fix adds
an entry or the fix doesn't ship.
**Measurable target:** 100% of post-roadmap fixes have ledger entries
(auditable by `git log` vs. ledger dates).

### T2-P2 — Reproduction-first policy
The rule, in your words' spirit: **no fix without a failing test
first.** The test fails on the broken code, passes on the fixed code,
and the commit contains both. The 5–6 pre-existing
`test_heartbeat_integration.py` failures (`FileNotFoundError` for a
`/home/hatch/Verdandi` path that doesn't exist here) are the standing
counter-example: known-broken, environment-coupled, and still open.
They get one of two dispositions — fixed or quarantined with a named
reason — not a third year of red.

**Acceptance.** Full suite runs; every failure is either fixed or
carries a dated quarantine note with owner and re-check date.
**Measurable target:** test suite green except quarantined-with-reason
items; quarantine list reviewed monthly (a calendar note, not a hope).

### T2-P3 — Fix cadence and triage
Bugs are triaged weekly into: **bleeding** (breaks the mirror or the
bridge — fixed same day), **limping** (degraded but honest — fixed
this week), **cosmetic** (ledger + backlog). The triage list lives in
the bug ledger's head section so there is exactly one place to look.

**Acceptance.** A written triage note, dated, once a week while any
non-cosmetic bug is open; silence when the list is empty (the
reporting contract's discipline — quiet when healthy — applies here
too).

## Track 2 non-goals
- Not a rewrite of anything. Additive-only, per inherited law.
- Not zero bugs. The goal is *known* bugs with *known* states, fixed in
  priority order — not the fantasy of a bug-free system.
- Not a public issue tracker migration. The ledger is a file in the
  repo; GitHub Issues remain your call.

---

# Track 3 — Profile-first efficiency

**Objective.** The 1-minute heartbeat worker must never be the reason
the forge is slow. Optimize from measurement, never from instinct —
and never trade the mirror's honesty for speed.

## The measured baseline (PROVEN, 2026-09-26)
- Feed replay cost: **~11µs/event.**
- Full run (replay + attach + senses + memory parse): comfortably
  inside the 120s cron timeout.
- The attach phase is bounded file reads: `~/MEMORY.md` + bank
  (~2k lines of markdown), people pages, one ledger JSON.

## Phases

### T3-P1 — Budgets, written down
Every hot path gets a named budget in `docs/performance-budgets.md`:
- Feed replay: ≤ 20µs/event (measured 11; budget leaves headroom).
- Full bridge run: ≤ 30s wall (timeout is 120s; the budget is a
  quarter of it — the day the run takes half the timeout is the day
  something is wrong, and the budget says so before the timeout does).
- Mirror JSON write: ≤ 1s.
- Memory parse (attach phase): ≤ 5s at current corpus size.

**Acceptance.** Budgets file exists; a `pytest` benchmark module
measures each path and fails the suite when a budget is exceeded.
**Measurable target:** all four budgets green on the current machine;
any budget breach blocks the commit (test, not policy).

### T3-P2 — Profile before touching
No optimization work begins without a profile showing where the time
goes. `cProfile` on the bridge run, flame graph optional, the
numbers mandatory. The rule is one sentence: **the profile names the
target, or there is no target.**

**Acceptance.** Each optimization commit links its profile output in
the message. Reviewers (you, or the audit wave) can verify the target
was real.
**Measurable target:** 100% of perf commits cite a profile. What would
make the *gains* measurable: before/after numbers in the bug-ledger
style — same machine, same feed size, three runs each.

### T3-P3 — Scale testing the honest way
The corpus grows (828 KB docs and counting; the feed grows every
minute). The question is not "is it fast today" but "where does it
bend." Synthetic scale tests: 10× feed size, 10× memory corpus,
2× horizon — measure where each budget breaks, and write down the
breaking point.

**Acceptance.** A `docs/scale-limits.md` stating, in numbers, where
each budget fails under synthetic load.
**Measurable target:** every hot path has a known breaking point.
What would make the *response* measurable: for each breaking point,
either a fix, a mitigation (e.g., horizon trim, corpus cap), or a
named acceptance of the limit with your sign-off.

## Track 3 non-goals
- No premature abstraction "for performance." Per your Project Laws:
  no cleverness without measurement.
- No trading correctness for speed. The pure-projection rebuild is
  never "optimized" into an incremental cache — that trade was
  rejected in the architecture (§2) and the rejection is permanent.
- No new performance infrastructure (no APM agent, no metrics
  daemon). Benchmarks in `tests/`; numbers in docs.

---

# Track 4 — Rock stability

**Objective.** The system stays up, stays honest about being down, and
comes back without you having to notice first. Stability is not "never
fails" — it is "failure is bounded, announced, and recovered."

## Phases

### T4-P1 — Bounded retries, everywhere a retry exists
Audit every retry in the codebase and the worker scripts. Each retry
gets: a **count** (never infinite), a **backoff** (with jitter, so two
restarting things don't march in lockstep), and a **terminal state**
(what happens when the retries run out — announced, not looped).

**Precedent:** the reporting contract already forbids retry-in-a-loop
for the heartbeat worker. This phase extends that discipline to every
helper, relay, and client in the tree.

**Acceptance.** `grep -rn "retry\|while True" src/` returns a list
where every entry cites its bound; unbounded loops are bugs filed in
the ledger (Track 2).
**Measurable target:** 0 unbounded retry loops in the tree.

### T4-P2 — Timeouts on every wait
Every network call, every subprocess, every lock acquisition gets an
explicit timeout. A wait without a timeout is a hang with good
intentions.

**Acceptance.** Audit list of all blocking calls with their timeouts,
in `docs/timeouts.md`.
**Measurable target:** 0 blocking calls without a named timeout.
What would make it measurable automatically: a lint test that fails
on `requests.get(` / `subprocess.run(` / `httpx.` calls without a
`timeout=` argument.

### T4-P3 — The seven-day proof
The stability claim is proven by observation, not by argument. After
P1–P2 land: seven consecutive days where (a) every heartbeat run
either succeeds or announces its failure exactly once, (b) no silent
gaps in `wyrd_mirror_synced` cadence beyond the designed quiet
minutes, (c) every announced failure has a ledger entry.

**Acceptance.** A dated seven-day log, kept by the existing reporting
(not a new monitor — the worker already reports; we read its reports).
**Measurable target:** 7/7 days, 0 silent failures, 0 unannounced
recoveries. If a failure occurs and is announced and recovered, the
week still counts — *honest* failure is the pass condition, not
*absent* failure.

## Track 4 non-goals
- Not five-nines. This is a one-VM forge, not a data center. The
  target is *honest* uptime, not a marketing number.
- Not automatic failover to another machine. Recovery means restart
  and resume on this box, with the announcement intact.
- Not masking real incidents as "stability." If the hub dies again
  (Track 6, Incident 1), the stability track reports it — it does not
  hide it behind a green dashboard.

---

# Track 5 — Corrupt-state detection and repair

**Objective.** State files corrupt — disks hiccup, edits land
mid-read, writes tear. The system must *detect* corruption, *quarantine*
it (never silently drop it), and *repair or degrade* without human
intervention where safe, with announcement where not.

## Phases

### T5-P1 — The quarantine pattern, generalized
**Precedent (PROVEN):** the forge queue's corrupt-job handling —
an unparseable job file is **announced once**, moved to
`quarantine/`, and the queue moves on; the file is never silently
dropped, never blocks the queue, and the next drain is silent about
it (queue.md:42,101,181–182). This pattern is correct. This phase
makes it the standard for every state file in the system:

1. `wyrd_mirror.json` — torn write → keep last good copy, announce,
   rewrite next run.
2. The entity ledger — already self-heals (Track 6, Incident 4); this
   phase adds the announcement so the heal is visible, not silent.
3. `nerve_feed.jsonl` — already skips malformed lines
   (`wyrd_bridge.py` JSONDecodeError guard); this phase adds a
   counter so "3 torn lines this week" is a fact, not a feeling.

**Acceptance.** Every state file in `~/.hermes/state/` has a named
corrupt-handling behavior in `docs/state-files.md`: what "corrupt"
means for it, what happens, what is announced, where the quarantined
copy goes.
**Measurable target:** a chaos test — corrupt each state file in turn
(missing, empty, torn JSON, wrong schema) — and every case degrades
or heals per its documented behavior. 0 cases that crash the runner.

### T5-P2 — Atomic writes everywhere
**Precedent (PROVEN):** the queue's "all writes are temp-file +
atomic rename — readers never see torn JSON" (queue.md:39), and the
atomic-swap standing rule from the 19:55 incident (Track 6,
Incident 2): stage in `/tmp`, syntax-check, rename over.

This phase audits every writer: does it write temp-then-rename? The
ones that don't, do after this phase. No exceptions for "it's just a
small file" — small files tear too.

**Acceptance.** Writer audit in `docs/state-files.md`; every writer
temp-file + rename.
**Measurable target:** 0 direct-overwrite writers in the tree
(`grep` for `open(.*["']w["'])` on state paths, each either converted
or justified).

### T5-P3 — Schema versions and migrations
State files grow schemas (the ledger may gain a third map someday;
the mirror JSON already grew `senses` and `memory_beliefs` sections).
Every versioned state file carries a `schema_version`; the reader
knows every version it can read, migrates forward when it can, and
quarantines-with-announcement when it can't.

**Acceptance.** Version fields on the ledger and mirror JSON; a
migration test for each known old version.
**Measurable target:** 0 "unknown schema" crashes — every unknown
version takes the quarantine path instead.

## Track 5 non-goals
- Not a database. JSON files with atomic writes and quarantine are
  the model; if a state file outgrows that, the answer is a *designed*
  migration to SQLite, not an accidental one.
- Not silent repair. Repair is announced; the one thing worse than
  corrupt state is corrupt state that *fixed itself without telling
  you* — that's how you lose the evidence of the real bug underneath.
- Not checksums-everywhere on day one. Torn-write detection comes
  from atomic renames + JSON parse; checksums are P4 if the chaos
  tests show a gap.

---

# Track 6 — Self-healing grounded in real incidents

**Objective.** The system learns from what actually happened to it —
not from imagined failure modes. Four real incidents from the
2026-09-26 workstream, each with its standing rule. Nothing here is
invented; where the cause is unknown, the document says so, in plain
words.

## The incident record

### INCIDENT 1 — The nerve-hub disappearances (OBSERVED, cause UNPROVEN)
On September 26, 2026, the Verdandi nerve hub disappeared **three
times**. The watchdog and self-repair resurrected it each time; the
mirror work continued. **The cause is still unproven.** It is *not*
established that memory pressure (OOM) caused these disappearances —
that hypothesis was floated and it remains a hypothesis. Stating it as
fact would be exactly the kind of covered-up limit your standing rule
forbids.

**What the incident actually proved (PROVEN):**
- Detection works: the disappearances were noticed, not silent.
- Resurrection works: watchdog + self-repair brought the hub back.
- The cost of the unknown: every future disappearance still starts
  from zero diagnosis.

**The standing rule it produces:**
1. **Instrument before theorizing.** The hub's death must leave
   evidence: last heartbeat timestamp, memory readings before/after
   (`MemAvailable` from the existing Heilsiðr mem sense — no new
   measurement), process exit code/signal if obtainable, watchdog
   log lines. A death with no evidence is a death we learn nothing
   from.
2. **Never fail silently.** You are looped in briefly when it
   happens (the alignment record already commits to this) — not
   with a theory, with the facts: "hub down at HH:MM, resurrected at
   HH:MM, evidence attached, cause unknown."
3. **No claimed root cause until proven.** The day we have evidence
   (exit signal 9 under recorded memory pressure, a pattern across
   five incidents, a core dump), the ledger entry says so. Until
   then: unknown.

**Measurable targets:**
- Time-to-detect ≤ 1 heartbeat; time-to-resurrect ≤ 2 heartbeats
  (both already achieved; now they are *requirements*, not luck).
- Every future hub death produces an evidence bundle (the four items
  above) — 100%, no exceptions.
- What would make the *cause* measurable: five evidence bundles with
  the same signature. Until then, no claim.

### INCIDENT 2 — The 19:55 mid-edit read (OBSERVED → rule PROVEN by adoption)
On September 26, 2026 at 19:55 EDT, the 1-minute heartbeat worker read
`wyrd_bridge.py` **while it was being edited** — a half-written file —
and died with `'tuple' object is not callable`. The next run read the
finished file and succeeded: **the system self-healed in one minute
with no intervention.** But the incident exposed the real flaw: editing
a file in place that a running worker reads every sixty seconds is a
race, and the race was ours, not the worker's.

**The standing rule it produced (PROVEN by adoption in Wave E):**
**Atomic swap for any file a running process reads.** Stage the new
version in `/tmp`, syntax-check it (`py_compile` for Python), then
`os.rename` it over the live path. Readers see the old file or the
new file — never a half-written one. Wave E's own docstring fix was
performed this way and the suites re-ran green.

**Generalization (this track's work):**
1. The rule extends to *every* file the heartbeat touches:
   `wyrd_bridge.py`, `wyrd_inbound.py`, the cron body files, the
   Heilsiðr scripts. One rule, all live files.
2. The cron-body documentation gains the rule as a prohibition so the
   next editor — human or agent — meets it before the race, not after.

**Measurable targets:**
- 0 torn-read incidents after adoption (counted from 2026-09-26
  19:55 forward; the count is currently 0 and the target is keeping
  it there).
- What would make *compliance* measurable: the edit-path checklist in
  the cron docs, checked by the audit wave on every future edit.

### INCIDENT 3 — The forge-queue corrupt file (PROVEN pattern)
The FIFO forge queue met a corrupt job file and did the right thing:
**announced it once as unparseable, moved it to `quarantine/`, kept
the queue moving, stayed silent about it on the next drain.**
Never silently dropped, never blocking, never nagging.

**The standing rule it produced:** *quarantine, don't delete; announce
once, don't nag.* This is now the template for Track 5's P1 — the
queue proved the pattern before the roadmap generalized it.

**Measurable targets:**
- The pattern's three properties hold for every state file after
  Track 5 P1: (1) corrupt input never blocks the pipeline,
  (2) nothing is silently dropped, (3) the announcement fires exactly
  once. Each property is a chaos-test assertion.

### INCIDENT 4 — The ledger's graceful degradation (PROVEN design)
The entity ledger (`~/.hermes/state/wyrd_entity_ledger.json`) was
designed so that **missing or corrupt → fresh empty maps, and the run
continues.** Exactly two maps (`last_sense_status`,
`reflection_seen`); nothing load-bearing lives there; delete it and
you lose only transition-detection and reflection dedup for a run or
two, and both self-heal. Tested: the Verdandi suite's ledger
self-heal test passes on corrupt/missing file.

**The standing rule it produced:** *no load-bearing state in mutable
convenience files.* If a file can be deleted without breaking the
system, the system is honest about what it can lose. If it can't be
deleted safely, it doesn't belong in a convenience file.

**Generalization (this track's work):**
1. Audit every mutable file the runner touches against this rule.
   Anything load-bearing that lives in a convenience file gets
   either promoted (to a real store with real guarantees) or
   re-designed (so it isn't load-bearing anymore).
2. The "exactly two maps" minimalism is the model: a mutable file
   should hold the *minimum* that no other source provides. Bloat
   in a convenience file is future corruption surface.

**Measurable targets:**
- The audit list: every mutable runner file, its load-bearing
  contents (must be none), its degraded behavior on
  missing/corrupt (must be documented).
- 0 files where deletion breaks the run.

## Track 6 non-goals
- Not a post-mortem theater. No incident review meetings, no
  five-whys documents for their own sake. The ledger entry and the
  standing rule are the whole ceremony.
- Not "fixing" Incident 1's unknown cause by assertion. The
  discipline *is* the fix: evidence first, claims later.
- Not retroactive. The four incidents above are the seed set; future
  incidents join the record the same way — observed exactly, cause
  marked honestly.

---

# Track 7 — Self-correction when the model's picture is wrong

**Objective.** A world model that cannot notice it is wrong is a
confident liar. The mirror must detect divergence between its picture
and reality, say so loudly, and correct — without ever silently
rewriting what it believed.

## The mechanism that already exists (PROVEN, Waves A–E)

The divergence watch (`wyrd_inbound.py`) already fires four kinds:

| Kind | What it means | Who wins |
|---|---|---|
| `stale_wish` | a wish's time passed unfulfilled | the live event (reality) |
| `stale_mood` | the mirror's mood disagrees with live mood | the live event |
| `stale_memory_belief` | a model belief contradicts a memory source | **memory** (value domain) |
| `sense_transition` | a sense changed status since last run | the new reading |

The precedence rule is the load-bearing idea: **event domain — the
live event wins; value domain — memory wins.** When memory contradicts
the model, the model loses *loudly* — a `wyrd_divergence` event names
the belief and the contradicting source. Silent correction would be
the loop gaslighting itself (architecture §4).

## Phases

### T7-P1 — The contradiction ledger
Every fired divergence gets a ledger entry: what the model believed,
what reality said, which domain rule applied, what changed. Over
weeks, this ledger is the empirical record of *how the model is
usually wrong* — which is the most valuable dataset the self-
correction work can have.

**Acceptance.** Ledger exists; every divergence kind has at least one
real entry within 30 days of the watch going live (or a dated note
explaining the quiet — silence is data too).
**Measurable target:** 100% of fired divergences logged; a monthly
read of the ledger asking "what pattern of wrongness keeps
recurring?"

### T7-P2 — Confidence with teeth
Beliefs carry confidence (0..1) today, but nothing *uses* it. This
phase gives confidence consequences:
1. A belief contradicted by reality loses confidence by a fixed step
   (0.2) — not to zero in one blow (one contradiction can be noise),
   but downward, visibly.
2. A belief at confidence < 0.3 stops being asserted as fact in
   `build_context_packet` — it is reported as *uncertain*, with its
   history.
3. A belief re-confirmed by events regains confidence slowly (0.1) —
   trust rebuilds slower than it breaks, on purpose.

**Acceptance.** Contradiction tests: contradict a belief three times,
watch it step down 0.9 → 0.7 → 0.5 → uncertain; re-confirm it,
watch it climb back slowly.
**Measurable target:** the step sizes are constants in code with
tests, not vibes. What would make the *right* step sizes measurable:
the contradiction ledger (P1) — after 90 days, the recurring-
wrongness patterns tell us whether 0.2 is too harsh or too gentle.

### T7-P3 — The correction announcement contract
When the model corrects itself, it says so — once, plainly, in the
existing reporting voice:
- What it believed, what reality showed, what it believes now.
- Never a rewrite of history: the old belief stays in the ledger
  with its confidence history. The model *changed its mind*; it did
  not *always know*.

**Acceptance.** The reporting contract gains the correction line;
three live corrections observed and each carrying all three facts.
**Measurable target:** 0 silent belief changes in a 30-day window
(audited against the contradiction ledger).

### T7-P4 — The honest limit, restated as law
The reflection loop's output is the worker's *account* of the self —
self-reported, never automatic capture (final doc §5 said this first).
Track 7's corrections inherit that limit: when the model says "I was
wrong about my mood," it means the *worker's account* was wrong, and
the correction is a better account — not an objective transcript.
This is not a flaw to fix; it is the boundary of what a self-model
can honestly claim. The roadmap does not try to cross it.

**Acceptance.** The limit is stated in the module docstring where
corrections happen, not just in this roadmap.
**Measurable target:** none — some things are laws, not metrics.

## Track 7 non-goals
- Not automatic belief rewriting from divergences. The divergence
  fires loudly; the *correction* follows the confidence rules (P2).
  Automatic rewrite would be the loop editing its own memory — the
  architecture forbids the heartbeat writing the memory tree, and
  this track does not route around that.
- Not a "truth" score for the whole mirror. Aggregate correctness
  metrics invite gaming; per-belief confidence with history is the
  honest unit.
- Not crossing the self-report boundary (P4). The mirror holds the
  worker's account, and the roadmap says so where it matters.

---

# How the tracks sequence

No track depends on another track's *completion*, but they share a
natural order. If you approve them in waves:

1. **Track 2 (bugs) + Track 6 (incidents)** first — they are mostly
   writing: the ledgers, the audits, the standing rules. Cheap,
   high-value, and they make every later track auditable.
2. **Track 5 (corrupt-state) + Track 1 (security)** next — the
   trust boundaries. The fuzz corpus (T1-P1) and the chaos tests
   (T5-P1) are the same testing muscle.
3. **Track 4 (stability) + Track 3 (efficiency)** next — budgets,
   bounds, and the seven-day proof. These need the system to be
   *known* (Tracks 2/6) before they can prove it *stable*.
4. **Track 7 (self-correction)** last — it needs the contradiction
   ledger fed by live divergences, which needs the watch running,
   which needs your §7 cron approval. Track 7 is the crown; it goes
   on last because it depends on everything being honest first.

Each wave starts on your word. Nothing here starts itself.

# What "done" looks like

Not a version number. A set of facts, each checkable:

- The bug ledger exists and every fix since has an entry (T2).
- The fuzz corpus and chaos tests run green (T1, T5).
- Every retry is bounded, every wait has a timeout (T4).
- The performance budgets hold and the scale limits are written
  down (T3).
- Four incident standing rules are in the code's docstrings and the
  cron docs, and the hub-death evidence bundle exists (T6).
- Beliefs step down when contradicted and corrections are announced
  (T7).
- And underneath all of it, unchanged: the world is still rebuilt
  fresh every run. Pure projection, no drift. The mirror keeps its
  contract.

*The forge is untouched — no code, no cron, no feed. Seven tracks,
each starting on your word. — Strategist, Wave F*
