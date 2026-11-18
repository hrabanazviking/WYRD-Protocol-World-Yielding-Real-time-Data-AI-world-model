"""Multi-source conflict handling — WY-T5 (Tvíheimr readiness).

When two sources report the same world differently (two connectors, or
a late duplicate arriving after the claim has moved on), WYRD keeps
BOTH reports with provenance and resolves by a declared rule. No report
is ever silently overwritten: every report stays in the WY-T2 intake,
every disagreement at or before the current claim time is recorded as
a :class:`ConflictRecord`, and state reflects the winner only.

Declared resolution rule (in order):
  1. Higher declared source authority wins (sources not declared rank 0).
  2. Fresher ``world_time`` wins.
  3. Later ``received_time`` wins.
  4. Lexicographically larger ``event_id`` wins (deterministic last tiebreak).

A strictly fresher differing report from any source is an orderly
supersession, not a conflict: the older report stays on record and the
decision names it superseded. A differing report whose ``world_time``
is at or before an existing report's ``world_time`` for the same claim
IS a conflict (simultaneous disagreement or late/stale contradiction).
A same-value report is corroboration: kept, never a conflict, and it
changes no state.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import Field

from wyrdforge.events.intake import EventIntake, StoredEvent, WorldEvent, apply_tactical_event
from wyrdforge.models.common import StrictModel

RULE_TEXT = (
    "freshest authoritative source wins for state: "
    "(1) higher declared authority, (2) fresher world_time, "
    "(3) later received_time, (4) larger event_id; "
    "the conflict itself stays on record and no report is overwritten"
)

_PHASE_KINDS = ("combat.begun", "combat.joined", "combat.turned", "combat.ended")


class Claim(StrictModel):
    claim_key: str
    claim_value: str
    subject_id: str | None = None


def extract_claim(event: WorldEvent) -> Claim | None:
    """The single state claim an event makes, if it makes one."""
    payload = event.payload
    if "claim_key" in payload and "claim_value" in payload:
        return Claim(claim_key=str(payload["claim_key"]),
                     claim_value=str(payload["claim_value"]),
                     subject_id=payload.get("subject_id"))
    subject = payload.get("subject_id") or (event.participant_ids[0] if event.participant_ids else None)
    if subject is None:
        return None
    if event.kind == "threat.assessed" and "grade" in payload:
        return Claim(claim_key=f"threat_level:{subject}", claim_value=str(payload["grade"]),
                     subject_id=subject)
    if event.kind in _PHASE_KINDS:
        return Claim(claim_key=f"combat_phase:{subject}", claim_value=event.kind.split(".", 1)[1],
                     subject_id=subject)
    return None


class ReportRecord(StrictModel):
    seq: int
    event_id: str
    source_connector: str
    claim_key: str
    claim_value: str
    world_time: datetime
    received_time: datetime


class ConflictRecord(StrictModel):
    conflict_id: str
    claim_key: str
    report_event_ids: list[str] = Field(default_factory=list)
    winner_event_id: str
    loser_event_ids: list[str] = Field(default_factory=list)
    rule: str = RULE_TEXT
    reason: str = ""


class ResolutionDecision(StrictModel):
    event_id: str
    claim_key: str | None = None
    claim_value: str | None = None
    is_winner: bool = True
    applied: bool = False
    corroboration: bool = False
    conflict_id: str | None = None
    superseded_event_ids: list[str] = Field(default_factory=list)
    reason: str = ""


class ConflictTracker:
    """Keeps every report per claim and resolves winners by the declared rule."""

    def __init__(self, authority: dict[str, int] | None = None) -> None:
        self.authority: dict[str, int] = dict(authority or {})
        self._reports: list[ReportRecord] = []
        self._by_event: dict[str, ReportRecord] = {}
        self._conflicts: list[ConflictRecord] = []
        self._decisions: list[ResolutionDecision] = []
        self._conflict_count = 0

    def authority_of(self, source_connector: str) -> int:
        return self.authority.get(source_connector, 0)

    def _rank(self, report: ReportRecord) -> tuple:
        return (self.authority_of(report.source_connector), report.world_time,
                report.received_time, report.event_id)

    def _winner(self, claim_key: str) -> ReportRecord | None:
        reports = [r for r in self._reports if r.claim_key == claim_key]
        return max(reports, key=self._rank) if reports else None

    def reports(self, claim_key: str | None = None) -> list[ReportRecord]:
        if claim_key is None:
            return list(self._reports)
        return [r for r in self._reports if r.claim_key == claim_key]

    def conflicts(self) -> list[ConflictRecord]:
        return list(self._conflicts)

    def decisions(self) -> list[ResolutionDecision]:
        return list(self._decisions)

    def current_winner(self, claim_key: str) -> ReportRecord | None:
        return self._winner(claim_key)

    def consider(self, stored: StoredEvent) -> ResolutionDecision:
        event = stored.event
        claim = extract_claim(event)
        if claim is None:
            decision = ResolutionDecision(event_id=event.event_id, is_winner=True,
                                          reason="event makes no state claim; stored only")
            self._decisions.append(decision)
            return decision
        prior = [r for r in self._reports if r.claim_key == claim.claim_key]
        prior_winner = self._winner(claim.claim_key)
        report = ReportRecord(seq=stored.seq, event_id=event.event_id,
                              source_connector=event.source_connector,
                              claim_key=claim.claim_key, claim_value=claim.claim_value,
                              world_time=event.world_time, received_time=event.received_time)
        self._reports.append(report)
        self._by_event[event.event_id] = report
        winner = self._winner(claim.claim_key)
        assert winner is not None
        is_winner = winner.event_id == event.event_id
        corroboration = prior_winner is not None and prior_winner.claim_value == claim.claim_value
        # Conflict: a differing report already stands at or after this
        # report's world_time — simultaneous disagreement, or this is a
        # late/stale report contradicting a fresher (or equal-time) one.
        differing = [r for r in prior if r.claim_value != claim.claim_value]
        conflict_peers = [r for r in differing if r.world_time >= event.world_time]
        conflict_id: str | None = None
        reason_parts: list[str] = []
        if is_winner:
            if prior_winner is not None and prior_winner.event_id != event.event_id:
                reason_parts.append(f"supersedes {prior_winner.event_id}")
            reason_parts.append("winner by " + self._why_winner(report, prior))
        else:
            reason_parts.append(f"winner is {winner.event_id} by " + self._why_winner(winner, self._reports))
        if conflict_peers:
            self._conflict_count += 1
            conflict_id = f"conflict-{self._conflict_count}"
            involved = [r.event_id for r in conflict_peers] + [event.event_id]
            losers = [eid for eid in involved if eid != winner.event_id]
            peer = conflict_peers[0]
            self._conflicts.append(ConflictRecord(
                conflict_id=conflict_id, claim_key=claim.claim_key,
                report_event_ids=involved, winner_event_id=winner.event_id,
                loser_event_ids=losers,
                reason=f"{report.source_connector} reported {claim.claim_value!r} "
                       f"against {peer.source_connector} {peer.claim_value!r} "
                       f"for {claim.claim_key}; resolved: {'; '.join(reason_parts)}"))
        superseded = []
        if is_winner and prior_winner is not None and prior_winner.event_id != event.event_id \
                and not conflict_peers:
            superseded = [prior_winner.event_id]
        decision = ResolutionDecision(
            event_id=event.event_id, claim_key=claim.claim_key, claim_value=claim.claim_value,
            is_winner=is_winner, corroboration=bool(corroboration),
            conflict_id=conflict_id, superseded_event_ids=superseded,
            reason="; ".join(reason_parts))
        self._decisions.append(decision)
        return decision

    def _why_winner(self, winner: ReportRecord, others: list[ReportRecord]) -> str:
        rivals = [r for r in others if r.claim_key == winner.claim_key
                  and r.event_id != winner.event_id and r.claim_value != winner.claim_value]
        if not rivals:
            return "sole report for the claim"
        best_rival = max(rivals, key=self._rank)
        if self.authority_of(winner.source_connector) != self.authority_of(best_rival.source_connector):
            return (f"authority {winner.source_connector}="
                    f"{self.authority_of(winner.source_connector)} over "
                    f"{best_rival.source_connector}={self.authority_of(best_rival.source_connector)}")
        if winner.world_time != best_rival.world_time:
            return "freshest world_time"
        if winner.received_time != best_rival.received_time:
            return "later received_time tiebreak"
        return "larger event_id tiebreak"

    # -- serialization ------------------------------------------------
    def to_dict(self) -> dict[str, Any]:
        return {"authority": dict(self.authority),
                "reports": [r.model_dump(mode="json") for r in self._reports],
                "conflicts": [c.model_dump(mode="json") for c in self._conflicts],
                "decisions": [d.model_dump(mode="json") for d in self._decisions],
                "conflict_count": self._conflict_count}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ConflictTracker":
        tracker = cls(authority=data.get("authority"))
        tracker._reports = [ReportRecord.model_validate(r) for r in data.get("reports", [])]
        tracker._by_event = {r.event_id: r for r in tracker._reports}
        tracker._conflicts = [ConflictRecord.model_validate(c) for c in data.get("conflicts", [])]
        tracker._decisions = [ResolutionDecision.model_validate(d) for d in data.get("decisions", [])]
        tracker._conflict_count = int(data.get("conflict_count", len(tracker._conflicts)))
        return tracker


class MultiSourceApplier:
    """Ingest + resolve + apply: state reflects the winner only, and a
    winning report that replaces an already-applied differing winner is
    applied on top (threat grades and phase moves are re-settable); a
    losing report is stored and recorded, never applied."""

    def __init__(self, world: Any, intake: EventIntake, tracker: ConflictTracker) -> None:
        self.world = world
        self.intake = intake
        self.tracker = tracker

    def submit(self, event: WorldEvent) -> ResolutionDecision:
        stored = self.intake.ingest(event)
        decision = self.tracker.consider(stored)
        claim = extract_claim(event)
        if claim is None:
            apply_tactical_event(self.world, self.intake, stored)
            decision.applied = True
            return decision
        if not decision.is_winner:
            decision.applied = False
            return decision
        if decision.corroboration:
            # Same value as an existing report: state already says this.
            decision.applied = False
            return decision
        apply_tactical_event(self.world, self.intake, stored)
        decision.applied = True
        return decision
