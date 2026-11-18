"""HugrGate judgment binding — WY-T3 (Tvíheimr readiness).

WYRD owns the model; HugrGate judges. For each stored world event
(WY-T2), the binding asks a judgment client — the HugrGate
decision-server form (HG-T1, POST /judge) in live use, or a local
fixture implementing the same verdict schema — whether the event is
combat-relevant, what combat effect it carries
(begun/joined/turned/ended/none), and how threat grades move. The
judged effect is applied to the WY-T1 tactical components through the
WY-T2 provenance path, and every judgment is stored as a
JudgmentRecord carrying its basis (judge, backend, model, probability,
rule/basis text), so every transition can be traced to both its event
and the judgment that authorised it.
"""
from __future__ import annotations

import json
import urllib.request
from typing import Any, Literal, Protocol

from pydantic import Field

from wyrdforge.events.intake import EventIntake, StateChangeRecord, StoredEvent, apply_tactical_event
from wyrdforge.models.common import StrictModel

Effect = Literal["none", "begun", "joined", "turned", "ended"]

_KIND_EFFECT: dict[str, str] = {
    "combat.begun": "begun", "combat.joined": "joined",
    "combat.turned": "turned", "combat.ended": "ended",
    "combat.approach": "none", "threat.assessed": "none",
}


class JudgmentRecord(StrictModel):
    """One judgment over one event, with its basis. Stored, never hidden."""

    event_id: str
    seq: int
    relevant: bool
    effect: Effect = "none"
    threat_grade: str | None = None
    threat_subject: str | None = None
    basis: str
    judge: str
    backend: str = ""
    model: str = ""
    probability: float | None = None
    applied: bool = False


class JudgmentClient(Protocol):
    name: str

    def judge(self, stored: StoredEvent) -> dict[str, Any]: ...


class FixtureHugrGateClient:
    """Local fixture of the HugrGate verdict schema (deterministic)."""

    name = "fixture:hugrgate-verdict-schema"

    def judge(self, stored: StoredEvent) -> dict[str, Any]:
        event = stored.event
        effect = _KIND_EFFECT.get(event.kind, "none")
        relevant = event.kind.startswith("combat.") or event.kind == "threat.assessed"
        grade = event.payload.get("grade")
        basis_kind = event.kind
        if event.kind == "combat.approach":
            grade = grade or "guarded"
            basis_kind = "combat.approach: approach spotted, combat not yet begun"
        elif event.kind == "combat.turned" and "flee" in str(event.payload.get("note", "")).lower():
            grade = grade or "low"
            basis_kind = "combat.turned: enemy flees, threat falls"
        elif event.kind == "combat.ended":
            grade = grade or "none"
            basis_kind = "combat.ended: combat over, threat cleared"
        return {
            "value": effect, "relevant": relevant, "effect": effect,
            "threat_grade": grade,
            "threat_subject": event.payload.get("threat_subject") or event.payload.get("target_id"),
            "probability": 1.0, "backend": "fixture", "model": "fixture-1.0",
            "basis": f"fixture-rules:{basis_kind}",
        }


class HttpHugrGateClient:
    """Live binding to HugrGate's decision-server form (HG-T1)."""

    name = "hugrgate-decision-server"

    def __init__(self, base_url: str = "http://127.0.0.1:8387", *, timeout: float = 10.0, transport=None) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self._transport = transport

    def _post_judge(self, body: dict[str, Any]) -> dict[str, Any]:
        if self._transport is not None:
            return self._transport(self.base_url + "/judge", body)
        raw = json.dumps(body).encode("utf-8")
        req = urllib.request.Request(self.base_url + "/judge", data=raw, headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(req, timeout=self.timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))

    def judge(self, stored: StoredEvent) -> dict[str, Any]:
        event = stored.event
        candidate = _KIND_EFFECT.get(event.kind, "none")
        body = {
            "state": {"kind": event.kind, "effect": candidate, "note": str(event.payload.get("note", "")), "signal": f"{event.kind} {candidate}"},
            "spec": {"type": "categorical", "options": ["begun", "joined", "turned", "ended", "none"]},
            "backend": "keyword",
        }
        result = self._post_judge(body)
        value = str(result.get("value", candidate))
        if value not in ("begun", "joined", "turned", "ended", "none"):
            value = candidate
        grade = event.payload.get("grade")
        if event.kind == "combat.approach":
            grade = grade or "guarded"
        elif event.kind == "combat.ended":
            grade = "none"
        elif event.kind == "combat.turned" and "flee" in str(event.payload.get("note", "")).lower():
            grade = grade or "low"
        return {
            "value": value, "relevant": value != "none" or event.kind.startswith("combat."),
            "effect": value, "threat_grade": grade,
            "threat_subject": event.payload.get("threat_subject") or event.payload.get("target_id"),
            "probability": result.get("probability"),
            "backend": str(result.get("backend", "")), "model": str(result.get("model", "")),
            "basis": f"hugrgate:/judge backend={result.get('backend')} model={result.get('model')} p={result.get('probability')}",
        }


class JudgmentBinding:
    """Applies judged effects to the model, storing every judgment."""

    def __init__(self, world: Any, intake: EventIntake, client: JudgmentClient) -> None:
        self.world = world
        self.intake = intake
        self.client = client
        self._records: list[JudgmentRecord] = []

    def records(self) -> list[JudgmentRecord]:
        return list(self._records)

    def judgment_for(self, event_id: str) -> JudgmentRecord | None:
        for rec in self._records:
            if rec.event_id == event_id:
                return rec
        return None

    def process(self, stored: StoredEvent) -> JudgmentRecord:
        verdict = self.client.judge(stored)
        effect = verdict.get("effect", "none")
        rec = JudgmentRecord(event_id=stored.event.event_id, seq=stored.seq, relevant=bool(verdict.get("relevant", False)), effect=effect, threat_grade=verdict.get("threat_grade"), threat_subject=verdict.get("threat_subject"), basis=str(verdict.get("basis", "")), judge=getattr(self.client, "name", "unknown"), backend=str(verdict.get("backend", "")), model=str(verdict.get("model", "")), probability=verdict.get("probability"))
        self._records.append(rec)
        if not rec.relevant:
            return rec
        applied = False
        if effect in ("begun", "joined", "turned", "ended"):
            before = len(self.intake.changes())
            apply_tactical_event(self.world, self.intake, stored)
            applied = len(self.intake.changes()) > before
        if rec.threat_grade is not None and rec.threat_subject is not None:
            self._apply_threat(stored, rec)
            applied = True
        rec.applied = applied
        return rec

    def _apply_threat(self, stored: StoredEvent, rec: JudgmentRecord) -> StateChangeRecord:
        from wyrdforge.ecs.components.tactical import ThreatLevelComponent
        subject = rec.threat_subject
        comp = self.world.get_component(subject, "threat_level")
        if comp is None:
            comp = ThreatLevelComponent(entity_id=subject)
            self.world.add_component(subject, comp)
        comp.set_grade(rec.threat_grade, source=f"hugrgate-judgment:{stored.event.event_id}", at=stored.event.world_time)
        return self.intake.record_change(stored.event.event_id, entity_id=subject, component_type="threat_level", change=f"grade -> {rec.threat_grade} (judgment: {rec.basis})")

    def process_many(self, stored_events: list[StoredEvent]) -> list[JudgmentRecord]:
        return [self.process(s) for s in stored_events]

    def to_dict(self) -> dict[str, Any]:
        return {"records": [r.model_dump(mode="json") for r in self._records]}

    @classmethod
    def from_records(cls, world: Any, intake: EventIntake, client: JudgmentClient, data: dict[str, Any]) -> "JudgmentBinding":
        binding = cls(world, intake, client)
        binding._records = [JudgmentRecord.model_validate(r) for r in data.get("records", [])]
        return binding
