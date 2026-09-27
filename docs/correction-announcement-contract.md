# Correction Announcement Contract

Track 7, Phase 3. When the model corrects itself, it says so — once,
plainly, in the existing reporting voice. This document is the contract the
worker's reporting gains; the announcement formatter lives in
`src/wyrdforge/services/self_correction.py::format_correction`.

## The three-facts rule

Every correction announcement carries all three facts, in this order:

1. **What it believed** — the old belief, as stated.
2. **What reality showed** — the divergence, as fired.
3. **What it believes now** — the corrected belief, with its confidence.

The canonical format:

```
Correction: believed '<X>'; reality showed '<Y>'; now believes '<Z>'.
```

## The discipline

- **Once, plainly.** One announcement per correction. No editorializing,
  no hedging, no second telling. The reporting voice stays the reporting
  voice — the contract does not invent a new channel.
- **Changed its mind, did not always know.** Never a rewrite of history:
  the old belief stays in the contradiction ledger
  ([docs/contradiction-ledger.md](contradiction-ledger.md)) with its full
  confidence history. An announcement that erases the old belief is not a
  correction — it is a cover-up, and it fails this contract.
- **Uncertainty is announced too.** When a belief steps below the
  uncertainty threshold (`UNCERTAINTY_THRESHOLD = 0.3`, strictly below), the
  announcement says what it believed, what contradicted it, and that the
  belief is now held as *uncertain* — with the confidence history, not as
  a flat number.

## The audit rule

**0 silent belief changes in a 30-day window**, audited against the
contradiction ledger: every confidence step the ledger records must have
its announcement, and every announcement must have its ledger entry. The
ledger is the ground truth; the announcements are the voice. They must
agree, entry for entry.

## The worker line

When the worker wiring is approved, the minutely `wyrd-mirror-bridge`
worker's reporting contract gains exactly this line type (specified here,
installed by no one until Volmarr confirms):

```
wyrd_correction: believed <X>; reality showed <Y>; now believes <Z>
```

Reported through the existing per-minute reporting — not a new channel, not
a new schedule. The format is mechanical from `format_correction`; the
worker diff is a call, not a design.
