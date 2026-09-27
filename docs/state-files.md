# State files — corrupt-handling contract

**Standing rules:** Incident 3's quarantine pattern (announce once, move
aside, keep going — `docs/incident-record.md`); Incident 4's
no-load-bearing-state rule (a convenience file holds no state the run
cannot lose); the 19:55 atomic-swap rule (stage in `/tmp`,
syntax-check, rename over); inherited law — never fail silently, never
invent a cause.

**How to read this file.** Per file: what "corrupt" means → what
happens → what is announced → where the quarantined copy goes. Then the
writer audit, the atomic-write rule, the schema-version design, the
cross-repo follow-ups, and the load-bearing audit.

## The quarantine pattern (the law, once)

1. **Detect** — the file exists but cannot be opened, read, or migrated.
2. **Announce once** — one `logging.warning` per path per process
   (never nag on the next run).
3. **Move aside** — the bytes go to `<parent>/quarantine/` with a
   timestamped name; nothing is ever silently dropped.
4. **Keep going** — a fresh, valid file takes its place and the run
   continues. Corrupt input never blocks the pipeline.

## Files this repo writes (SQLite)

All three stores share one mechanism: `PRAGMA journal_mode=WAL` for
atomicity, and a guarded constructor via
`wyrdforge.hardening.state_io.open_or_quarantine` (schema version 1).

### world-store DB (`*.db`, caller-chosen path)

- **Corrupt means:** the file is not a SQLite database (garbage bytes,
  truncated header), SQLite cannot open it at all (e.g. a directory
  sits at the path), or it claims `PRAGMA user_version` newer than 1.
- **What happens:** the file is quarantined; a fresh DB is created and
  stamped v1; the constructor returns normally. A torn *page* mid-run
  still raises `sqlite3.DatabaseError` at the failing operation — loud,
  announced, unhandled by design.
- **Announced:** one warning naming the path, the reason
  (`not-a-database` / `unknown-version`), and the quarantine
  destination.
- **Quarantine goes to:** `<dbdir>/quarantine/<stem>-YYYYMMDD-HHMMSS.db`
  (with `-wal` / `-shm` companions when present).

### memory-store DBs (`wyrd_*.db`, one per bridge)

- Same corrupt definition, same behavior, same announcement, same
  quarantine layout as the world-store DB.

### bond-store DB (caller-chosen path)

- Same corrupt definition, same behavior, same announcement, same
  quarantine layout as the world-store DB.

### Schema versions & migrations

- The three stores carry `PRAGMA user_version` (integer), current = 1.
  Every DB created before this slice reads as v0; the 0→1 step is
  "stamp, no DDL" (the `CREATE TABLE IF NOT EXISTS` schemas are
  unchanged).
- Migrations are forward-only callables registered per store; the
  machinery is proven by synthetic migrations in the test suite.
- A DB with `user_version` newer than the code knows takes the
  quarantine path with an explicit message ("schema vN newer than this
  code knows (vM) — quarantined, running fresh"). The data is
  preserved, never misread, never silently ignored. Target: 0
  unknown-schema crashes.
- Versions live on the stores, never on the world object — the world is
  a pure projection, rebuilt fresh every run (inherited law).
- The per-component `schema_version` strings (`"1.0"` vs `"1.0.0"`) are
  cosmetic inconsistencies, left as-is; `WorldStore.load` already skips
  unknown component *types* gracefully (forward compat, tested).

## Files this repo reads (Verdandi-side runtime)

The bridge degrades gracefully on bad input; this slice makes the
degrade *announced*. Reader behavior is unchanged — only counters and
statuses were added.

### `hub.state` (sweep state file)

- **Corrupt means:** missing, empty, or an unknown token.
- **What happens:** `("warn", None)` — liveness unverified is a raised
  eyebrow, not a crash.
- **Announced:** the `warn` status itself surfaces in the mirror's
  `hub_liveness` sense — the degrade *is* the announcement.
- **Quarantine:** n/a — a single token file; nothing worth preserving.

### forge-queue job JSONs (`~/.hermes/state/forge-queue/*.json`)

- **Corrupt means:** unparseable JSON, or valid JSON that is not a
  queued/running job dict.
- **What happens:** skipped in the depth count (unchanged).
- **Announced:** NEW — the per-run `forge_queue_torn_jobs` sense counts
  torn files, so the skip is visible in the mirror instead of silent.
- **Quarantine:** n/a on the reader side; writer-side quarantine is the
  forge queue's own proven pattern (not this repo's file to move).

### `nerve_feed.jsonl`

- **Corrupt means:** torn lines (unparseable JSON, or valid JSON without
  a numeric `_ts`).
- **What happens:** skipped; the rate is still computed from good lines
  (unchanged).
- **Announced:** NEW — the per-run `nerve_feed_torn_lines` sense counts
  torn lines. The append-only log itself is never quarantined.
- **Quarantine:** n/a.

### memory `.md` files (`~/MEMORY.md`, bank, people pages)

- **Corrupt means:** missing/unreadable, or malformed frontmatter.
- **What happens:** empty beliefs / skipped page (unchanged).
- **Announced:** silent by design — the mirror reads the curated surface
  and a missing page is ordinary. This is the explicit exception to the
  announce rule.
- **Quarantine:** n/a — plain text; nothing to preserve.

## The atomic-write rule

- **SQLite + WAL** is the mechanism for the three stores — atomicity is
  the journal's job, not temp+rename. The guarded open closes the real
  gap: a corrupt file used to crash the *constructor* before any write.
- **`atomic_write_json`** (`wyrdforge.hardening.state_io`) is the
  blessed path for any *future* JSON state writer in this repo:
  temp file in the same directory, flush + fsync, `os.replace()` over
  the destination. Readers see the old file or the new file — never a
  half-written one.
- Standing rule: any future JSON state writer uses it. No exceptions
  for "it's just a small file" — small files tear too.
- **Writer audit (full):** `WorldStore` — SQLite+WAL, keep (guarded
  open added). `PersistentMemoryStore` — SQLite+WAL+busy_timeout, keep
  (guarded open added). `PersistentBondStore` — SQLite+WAL, keep
  (guarded open added; `integrity_check()` added for parity). Zero
  JSON/plaintext state-file writers exist in this repo (verified by
  audit) — 0 direct-overwrite writers, proven.

## Cross-repo follow-ups (Verdandi side — specified, not built)

The JSON writers live in the Verdandi repo; this slice specifies their
required behaviors here, the same standing arrangement as Incident 1's
hub-evidence collection. They are **not** built in this slice.

- **`wyrd_mirror.json` writer:** torn write → keep the last good copy,
  announce, rewrite next run.
- **`wyrd_entity_ledger.json`:** keep Incident 4's self-heal, add the
  announcement so the heal is visible, not silent.
- **`nerve_feed.jsonl` reader (Verdandi side):** torn-line counter,
  mirroring this repo's reader-side counter.
- **Schema versions:** `schema_version` fields on the mirror JSON and
  the ledger when their schemas next change.

## Load-bearing audit — 0 files where deletion breaks the run

| File | Load-bearing? | Delete consequence |
|------|---------------|--------------------|
| world-store `*.db` | No — pure projection; the store is an explicit save/load convenience for the CLI | saved worlds gone; CLI `load` raises `KeyError` (loud, not silent) |
| memory-store `wyrd_*.db` | No — per-bridge memory cache | degraded recall, announced by empty results |
| bond-store `*.db` | No — re-derivable from conversation | degraded bond queries |
| `wyrd_entity_ledger.json` | No (Incident 4, PROVEN) — two accrual maps only | transition-detection + reflection dedup lost for a run or two, self-heals |
| `wyrd_mirror.json` | No — pure projection, rebuilt every minute | next run rewrites it |
| `nerve_feed.jsonl` | No — replay is best-effort over a 24h horizon | gap in replayable history |

The standing rule holds and is evidenced, not just asserted: no
load-bearing state lives in a mutable convenience file.
