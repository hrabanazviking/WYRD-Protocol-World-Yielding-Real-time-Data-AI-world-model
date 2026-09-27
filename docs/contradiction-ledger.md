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

Wiring live, accumulating. The ledger-append step runs in the minutely
`wyrd-mirror-bridge` worker — the wiring live since 2026-09-27 (approved by
Volmarr): every new `wyrd_divergence` event becomes a `CONTRADICTION-NNN`
entry below; `wyrd_divergence_resolved` closes it. The ledger witnesses only
what the wiring saw — nothing is invented here.

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

- **First read:** 2026-10-27 (30 days after the ledger went live 2026-09-27).
  The 30-day windows run from live feed.
- **Standing rule:** every subsequent read is dated in the ledger head, like
  the bug ledger's triage line. A calendar note, not a hope.
- **Silence is data too:** a divergence kind with no entries after 30 days
  of live feed gets a dated quiet note naming the kind — not an empty shrug.
  An empty ledger with a dated note is an honest ledger.

---

## Entries

_Entries begin 2026-09-27, when the ledger-append wiring went live. Nothing is invented here._
