"""Theory-of-Mind ECS components — what minds believe about other minds.

Ground truth is what the *world* knows. Theory of mind is what each
*entity* believes — including what it believes about what others believe.
That second layer is where deception, misunderstanding, dramatic irony,
and genuine social reasoning live.

Core structures:
- :class:`BeliefComponent` — what this entity believes about the world.
- :class:`MindModelComponent` — this entity's model of *other* minds:
  what A thinks B believes, wants, and intends.
- :meth:`MindModelComponent.divergence` — the false-belief check: where
  A's model of B disagrees with B's actual beliefs. Divergence is not an
  error; it is the data that makes social reasoning possible.

Fully deterministic and ECS-compatible — no LLM involvement at the
component level.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import ClassVar, Literal

from pydantic import Field

from wyrdforge.ecs.component import Component, register_component
from wyrdforge.models.common import StrictModel


def _now() -> datetime:
    return datetime.now(timezone.utc)


BeliefSource = Literal["observed", "told", "inferred", "assumed"]


class Belief(StrictModel):
    """A single belief held by an entity.

    Attributes:
        subject:    Entity ID or topic the belief is about.
        claim:      The believed proposition, in plain words.
        confidence: 0.0 (mere guess) .. 1.0 (certain).
        source:     How the belief was formed. ``assumed`` is the weakest
                   and must never be silently upgraded to ``observed``.
        formed_at:  World-time when the belief was formed.
    """

    subject: str
    claim: str
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    source: BeliefSource = "assumed"
    formed_at: datetime = Field(default_factory=_now)


@register_component
class BeliefComponent(Component):
    """What this entity believes about the world (rightly or wrongly)."""

    _type_key: ClassVar[str] = "beliefs"
    component_type: Literal["beliefs"] = "beliefs"

    beliefs: list[Belief] = Field(default_factory=list)

    def get_belief(self, subject: str) -> Belief | None:
        for b in self.beliefs:
            if b.subject == subject:
                return b
        return None

    def update_belief(self, subject: str, claim: str, confidence: float,
                      source: BeliefSource) -> Belief:
        """Add or revise a belief. Revision keeps the stronger source's
        history honest: the old belief is replaced, not merged."""
        belief = Belief(subject=subject, claim=claim,
                        confidence=confidence, source=source)
        self.beliefs = [b for b in self.beliefs if b.subject != subject]
        self.beliefs.append(belief)
        self.touch()
        return belief

    def retract_belief(self, subject: str) -> bool:
        """Drop a belief. Returns True if one was held."""
        before = len(self.beliefs)
        self.beliefs = [b for b in self.beliefs if b.subject != subject]
        if len(self.beliefs) != before:
            self.touch()
            return True
        return False


class MindModel(StrictModel):
    """Entity A's model of one other mind (entity B).

    Attributes:
        subject_id:        The entity being modeled (B).
        believed_beliefs:  What A thinks B believes.
        believed_desires:  What A thinks B wants.
        believed_intentions: What A thinks B intends to do.
        last_updated:      World-time of A's last observation of B.
    """

    subject_id: str
    believed_beliefs: list[Belief] = Field(default_factory=list)
    believed_desires: list[str] = Field(default_factory=list)
    believed_intentions: list[str] = Field(default_factory=list)
    last_updated: datetime = Field(default_factory=_now)


class DivergenceReport(StrictModel):
    """Where A's model of B disagrees with B's actual beliefs."""

    modeler_id: str
    subject_id: str
    false_beliefs: list[str] = Field(default_factory=list)   # claims A holds about B that B does not hold
    missing_beliefs: list[str] = Field(default_factory=list)  # B's actual beliefs absent from A's model
    agreement: float = 1.0  # fraction of B's beliefs A models correctly


@register_component
class MindModelComponent(Component):
    """Entity A's theory of other minds: one MindModel per known entity."""

    _type_key: ClassVar[str] = "mind_models"
    component_type: Literal["mind_models"] = "mind_models"

    models: dict[str, MindModel] = Field(default_factory=dict)

    def model_of(self, entity_id: str) -> MindModel | None:
        return self.models.get(entity_id)

    def update_model(self, entity_id: str, believed_beliefs: list[Belief] | None = None,
                     believed_desires: list[str] | None = None,
                     believed_intentions: list[str] | None = None) -> MindModel:
        """Record (or revise) A's model of another mind."""
        model = self.models.get(entity_id) or MindModel(subject_id=entity_id)
        if believed_beliefs is not None:
            model.believed_beliefs = believed_beliefs
        if believed_desires is not None:
            model.believed_desires = believed_desires
        if believed_intentions is not None:
            model.believed_intentions = believed_intentions
        model.last_updated = _now()
        self.models[entity_id] = model
        self.touch()
        return model

    def divergence(self, subject_id: str, actual: BeliefComponent) -> DivergenceReport:
        """Compare A's model of B against B's actual beliefs.

        This is the false-belief task as data: it reports exactly where
        the modeler's picture of the other mind is wrong.
        """
        model = self.models.get(subject_id)
        report = DivergenceReport(modeler_id=self.entity_id, subject_id=subject_id)
        if model is None:
            report.missing_beliefs = [b.claim for b in actual.beliefs]
            report.agreement = 0.0 if actual.beliefs else 1.0
            return report
        actual_by_subject = {b.subject: b.claim for b in actual.beliefs}
        modeled_by_subject = {b.subject: b.claim for b in model.believed_beliefs}
        for subject, claim in modeled_by_subject.items():
            if actual_by_subject.get(subject) != claim:
                report.false_beliefs.append(
                    f"about '{subject}': models '{claim}', actual is "
                    f"'{actual_by_subject.get(subject, '<no belief>')}'")
        for subject, claim in actual_by_subject.items():
            if subject not in modeled_by_subject:
                report.missing_beliefs.append(f"about '{subject}': '{claim}'")
        total = len(actual_by_subject)
        if total:
            # agreement counts beliefs A models correctly out of B's actual beliefs
            correct = sum(1 for s, c in actual_by_subject.items()
                          if modeled_by_subject.get(s) == c)
            report.agreement = round(correct / total, 3)
        return report
