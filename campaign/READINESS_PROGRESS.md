# WYRD Tvíheimr Readiness — Progress Ledger

Campaign branch: `yrsa/tviheimr-readiness` (off `development` @ 8b3b35a)
Venue: purplelongship, `~/forges/wyrd-readiness` · Method: Mythic Engineering (roles run sequentially by the keeper this campaign — no sub-agent spawn available on the device road)

| Slice | State | Gate evidence |
|---|---|---|
| WY-T1 Combat state components | BANKED 2026-11-18 | New module `src/wyrdforge/ecs/components/tactical.py`: `InCombatComponent`, `EngagedWithComponent`, `ThreatLevelComponent` (graded none→critical, source + derived age), `CombatPhaseComponent` (begun/joined/turned/ended, ended terminal, history kept). Tests `tests/test_tactical_combat_state.py`: schema + serialization round-trip for all four, grade ordering, derived age, self-engagement rejected, hand-built scenario reads back exactly as written. Targeted run: 63 passed (new + combat_awareness + ecs_core). Full suite: **2291 passed, 14 skipped, 6 xfailed** (venv `.venv`, PYTHONPATH=src, ulimit -n 8192 — the default 1024 fd limit causes EMFILE/SQLite-open failures across the pre-existing suite; environmental, proven by the clean re-run). |
| WY-T2 Event intake with provenance | NEXT | — |
| WY-T3 HugrGate judgment binding | pending | If HugrGate HG-T1 is not banked when reached, build against a local fixture of the verdict schemas; live binding re-proof owed. |
| WY-T4 Event awareness queries | pending | — |
| WY-T5 Multi-source conflict handling | pending | — |
| Ready for Tvíheimr gate | pending | — |

Notes:
- Clone was created fresh on the first tick (2026-11-18) from origin/development @ 8b3b35a; campaign branch created from it.
- README.md untouched. No Docker. No services. Pushes only to `yrsa/tviheimr-readiness` via explicit refspec.
