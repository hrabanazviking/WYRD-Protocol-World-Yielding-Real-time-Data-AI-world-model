# WYRD — Tvíheimr Readiness Roadmap

**Owner-directed, 2026-11-18.** Volmarr Wyrd's ruling: source projects are improved **first, in their own houses**, and only then called into Tvíheimr (private repo hrabanazviking/Tviheimr, Connector Fabric, doc 26; decision ADR-010 there). This roadmap is WYRD's own improvement road to being ready for that call. It adds a new line of work beside WYRD's existing roadmap and phase tasks; it replaces none of them.

## What Tvíheimr needs from WYRD
Tvíheimr's presence reads the world from WYRD's structured model — entities and components, not transcript prose. For that presence to be *timely*, the model must stay **tactically current**: WYRD gains **combat state and event awareness**, with HugrGate's fast judgment running over the incoming event stream (HugrGate's side of this pairing is roadmapped in HugrGate's own house, HUGRGATE_TVIHEIMR_READINESS_ROADMAP.md, slice HG-T3/HG-T6).

## Slices

### WY-T1 — Combat state components
ECS components for tactical state: `InCombat`, `EngagedWith` (entity refs), `ThreatLevel` (graded, with source and age), `CombatPhase` (begun / joined / turned / ended), attached to the entities they describe. Pure model work — no judgment yet.
**Gate:** component schema + serialization round-trip tests pass; existing WYRD suites stay green; a hand-built combat scenario reads back exactly as written.

### WY-T2 — Event intake with provenance
A world-event intake: events arrive stamped (source connector, world time, received time, kind, participants, digest) and are stored as first-class records linked to the entities they touch — never silently folded into state.
**Gate:** fixture event stream lands complete and in order; every state change in WY-T1's scenario can be traced to the event that caused it.

### WY-T3 — HugrGate judgment binding
WYRD calls HugrGate (decision-server form) over the event stream: which events are combat-relevant, when combat has begun/turned/ended, how threat grades move. WYRD owns the model; HugrGate judges; the judgment's basis is stored with the state it changed.
**Gate:** on the recorded fixture stream (a scripted fight: approach, first blow, ally joins, enemy flees, combat ends), the model's combat state matches the expected table at every step; every transition carries its judgment basis.

### WY-T4 — Event awareness queries
The read side presence will use: "what is happening now" (active combats, rising threats, notable events) answered from the model with source and age attached; staleness is reported, never hidden — a quiet feed reads as quiet, a dead feed reads as dead.
**Gate:** query fixtures return the expected picture at several points along the scripted fight, including after the feed stops (staleness shown, not papered over).

### WY-T5 — Multi-source conflict handling
When two sources report the same world differently (two connectors, or a late duplicate), WYRD keeps both reports with provenance and resolves by declared rule (freshest authoritative source wins for state; the conflict itself stays on record).
**Gate:** conflict fixtures resolve per the declared rule; no report is ever silently overwritten.

## Ready for Tvíheimr — the gate
WYRD is **ready** when WY-T1…WY-T5 are banked with their gate evidence, existing WYRD suites still pass, and a Tvíheimr-side fixture consumer can ask "what is happening now" of a live scripted world and receive the tactically current answer — combat state included — with sources and ages attached. Until then, Tvíheimr's Phase 15 world-model work waits — by the owner's ruling, correctly.
