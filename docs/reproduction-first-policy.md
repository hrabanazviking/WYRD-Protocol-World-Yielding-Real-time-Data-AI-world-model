# Reproduction-First Policy (Track 2, P2)

**Roadmap:** Hardening roadmap, Track 2 — Systematic bug correction, phase P2.
**Companion:** [docs/triage-cadence.md](triage-cadence.md) (how the queue is
worked). **Governed artifact:** [docs/bug-ledger.md](bug-ledger.md).

The rule, verbatim from the roadmap:

> **No fix without a failing test first.** The test fails on the broken code,
> passes on the fixed code, and the commit contains both.

A fix without a pinning test is not a fix — it is a hope. The pinning test is
named in the bug's ledger entry (`Pinning test` field); the commit that lands
the fix lands the test in the same commit.

---

## The workflow

The forge's procedure for every bug fix, in order:

### Step 1 — Write the failing test

Write the test against the **broken** code, before touching the fix. The test
must fail for the right reason: it demonstrates the bug, not an adjacent
accident. If you cannot write a failing test, you do not understand the bug
yet — keep investigating.

### Step 2 — Confirm it red

Run the test and confirm it fails on the broken code. Record the failure
verbatim in the ledger entry's `Observed` field. A test that never ran red is
not evidence — it is decoration.

### Step 3 — Fix and commit together

Fix **additively** (narrow patches, no reinterpretations, no drive-by
refactors). Confirm the test green and the full suite clean — green except
quarantined-with-reason items, per the roadmap's measurable target. Append the
`BUG-NNN` ledger entry — with the pinning test and the suite result — and
commit the fix, the test, and the ledger entry together. One commit, one
proven claim.

---

## The standing exemplar: quarantined, not forgotten

`tests/test_phase19_load.py` holds the standing example of the honest
alternative to a fix: **quarantine with a dated note.**

- Six tests fail non-deterministically under 50-thread bursts against the
  stdlib test HTTP server (`ConnectionResetError` under contention).
  Environmental — not a world-model defect.
- The 6 tests carry `@pytest.mark.xfail(strict=False)` markers. `strict=False`
  is deliberate: a *new* failure mode surfaces as an xfail, not as silence.
- Ledger entry [BUG-005](bug-ledger.md): reason (flaky concurrent-load
  timing), **owner: `forge`**, **re-check: 2026-10-26**.
- Hygiene: reviewed with `pytest tests/test_phase19_load.py -rX` on the
  re-check date and at every slice boundary; any xfail whose reason no longer
  matches `ConnectionResetError` timing flakiness **re-opens the bug**.

Quarantine is a named state with an owner and a re-check date — never a
parking lot.

---

## The monthly review

The quarantine list is reviewed **monthly** — a calendar note, not a hope:

- **Next review:** 2026-10-26, by `forge` (the BUG-005 re-check date).
- **Standing rule:** every review is dated in the ledger, and the next
  review date is named at review time. A quarantine without a future
  re-check date is a violation — `tests/test_doc_policies.py` fails the
  suite on it.

---

## Exceptions, named

The rule is strict, and its exceptions are named in advance — everything
else goes through the workflow:

1. **Pure-documentation slices** (this one included): a policy doc cannot
   have a failing test for a bug that does not exist. The acceptance is the
   machinery test (`tests/test_doc_policies.py`) proving the docs say what
   the roadmap ordered.
2. **Performance floor findings with Volmarr's sign-off** (Slice 6's anchor
   timestamp unification): where the "fix" is a named acceptance of a
   measured floor rather than a behavior change, the acceptance carries his
   explicit authorization, dated, in the performance history.

No other exceptions. When in doubt, write the test first.
