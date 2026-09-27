# Triage Cadence (Track 2, P3)

**Roadmap:** Hardening roadmap, Track 2 — Systematic bug correction, phase P3.
**Companion:** [docs/reproduction-first-policy.md](reproduction-first-policy.md)
(how a bug earns a fix). **Governed artifact:** [docs/bug-ledger.md](bug-ledger.md).

---

## The three tiers

Verbatim from the roadmap:

- **Bleeding** — breaks the mirror or the bridge. Fixed **same day**.
- **Limping** — degraded but honest. Fixed **this week**.
- **Cosmetic** — ledger + backlog.

Track 2's non-goal stands: this is not zero bugs. It is known bugs with known
states, in priority order.

---

## One place to look

The triage list lives in [docs/bug-ledger.md](bug-ledger.md)'s head section
(`## Triage — updated <date>`), and **only there**. This document holds the
*procedure*; the list itself never appears here. A second triage list is a
second source of truth, and a second source of truth is a lie waiting to
happen.

---

## The weekly cadence

While any non-cosmetic bug is open: a **written triage note, dated, once a
week**. The dated line is refreshed whenever triage changes — never silently.

The cadence is fulfilled by the forge's normal operations — every slice
build, every audit, and the heartbeat worker that already touches the ledger
head re-affirms or updates the triage line. **No new cron, no new daemon:**
the constraint is architectural. The forge already runs on a heartbeat; a
separate triage timer would be machinery for its own sake, and machinery for
its own sake is how daemons breed.

---

## Silence when empty

When no non-cosmetic bug is open, the ledger head says "quiet" and the
cadence says nothing. The reporting contract's discipline — quiet when
healthy — applies to triage notes too. There is never a perfunctory "still
nothing" commit; an empty queue is the goal, not an event.

---

## The bleeding escalation lane

A bleeding bug found between cadence points does not wait for the weekly
note: it is **fixed same day** and the triage line is updated at fix time.
The cadence is a floor, not a gate.
