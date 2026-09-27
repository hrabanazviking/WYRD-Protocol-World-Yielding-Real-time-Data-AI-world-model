# Contradiction Ledger

Append-only. Every divergence the live watch fires gets an entry: what the
model believed, what reality said, which domain rule applied, what changed.
Over weeks, this ledger is the empirical record of *how the model is usually
wrong* — the raw material for the monthly read that asks "what pattern of
wrongness keeps recurring?"

Companion records: the bug ledger ([docs/bug-ledger.md](bug-ledger.md))
holds the codebase's bruises; this ledger holds the mirror's corrections.
Bugs resolve; contradictions resolve too (open / resolved) — but a resolved
contradiction is never rewritten. The model *changed its mind*; it did not
*always know*.

Track: Track 7, Phase 1 (this file), fed by Phase 2 (confidence with teeth,
`src/wyrdforge/services/self_correction.py`) and announced under Phase 3
([docs/correction-announcement-contract.md](correction-announcement-contract.md)).

---

## Feed status — updated 2026-09-27

Feed wired, accumulating. The live divergence feed (the minutely
`wyrd-mirror-bridge` worker's inbound watch) is running and firing all four
kinds. Ledger appends begin when the worker wiring diffs (ledger-append step
+ reporting-contract line, specified in the Slice 8 plan) are approved — the
ledger must not invent entries for divergences it did not witness. Until
then: schema, rules, and this dated head note.

---

## Precedence rule

The load-bearing idea, stated once: **event domain — the live event wins;
value domain — memory wins.**

| Divergence kind | What it means | Domain rule applied |
|---|---|---|
| `stale_wish` | a wish's time passed unfulfilled | event-domain: the live event wins |
| `stale_mood` | the mirror's mood disagrees with live mood | event-domain: the live event wins |
| `stale_memory_belief` | a model belief contradicts a memory source | value-domain: memory wins |
| `sense_transition` | a sense changed status since last run | event-domain: the new reading wins |

"Silent correction would be the loop gaslighting itself." The divergence
fires loudly; the *correction* follows the confidence rules
(`self_correction.py`) — never an automatic rewrite of history.

---

## Entry schema

### CONTRADICTION-NNN

```markdown
### CONTRADICTION-001 — <short title>
- **Date fired:** YYYY-MM-DD HH:MM UTC (the minute the watch fired it)
- **Divergence kind:** stale_wish | stale_mood | stale_memory_belief | sense_transition
- **What the model believed:** ...
- **What reality said:** ...
- **Domain rule applied:** event-domain: the live event wins | value-domain: memory wins
- **What changed:** confidence X.XX → Y.YY | logged only (no belief stepped)
- **Status:** open | resolved YYYY-MM-DD
```

---

## Monthly read

The measurable target: 100% of fired divergences logged; a monthly read
asking "what pattern of wrongness keeps recurring?"

- **First read:** 2026-10-27 (30 days after this ledger shipped 2026-09-27).
  Re-date this note when the worker ledger-append wiring goes live — the
  30-day windows run from live feed, not from this document.
- **Standing rule:** every subsequent read is dated in the ledger head, like
  the bug ledger's triage line. A calendar note, not a hope.
- **Silence is data too:** a divergence kind with no entries after 30 days
  of live feed gets a dated quiet note naming the kind — not an empty shrug.
  An empty ledger with a dated note is an honest ledger.

---

## Entries

_No entries yet. Entries begin when the ledger-append wiring is approved.
Nothing is invented here._
